"""Stage 2: exploratory statistics, data-quality checks and figures for WM-811K (LSWMD.pkl).

Usage (from project root):
    .venv\\Scripts\\python scripts\\explore_data.py

Prints every number, writes them to outputs/eda/summary.json and saves
figures under outputs/eda/.
"""
import hashlib
import json
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import ListedColormap  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from sklearn.model_selection import GroupShuffleSplit, train_test_split  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PKL = ROOT / "data" / "raw" / "LSWMD.pkl"
OUT = ROOT / "outputs" / "eda"
CLASSES = ["Center", "Donut", "Edge-Loc", "Edge-Ring", "Loc", "Near-full", "Random", "Scratch", "none"]
DEFECTS = CLASSES[:-1]
SEED = 0
N_EXAMPLES = 8
NEAR_PX = 10  # two same-shape maps differing in <= NEAR_PX dies count as near-copies

# Chart tokens (light surface)
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
SERIES, SERIES2 = "#2a78d6", "#eb6834"
# Wafer map values: 0 = outside wafer, 1 = normal die, 2 = defective die
WAFER_COLORS = [SURFACE, "#d6d5d0", "#184f95"]
WAFER_CMAP = ListedColormap(WAFER_COLORS)

plt.rcParams.update({
    "font.family": "Malgun Gothic", "axes.unicode_minus": False, "font.size": 10,
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "text.color": INK, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "axes.edgecolor": GRID, "axes.linewidth": 0.8,
})


def first_str(v):
    """failureType / trianTestLabel are nested arrays like [['Loc']]; empty when missing."""
    a = np.asarray(v).ravel()
    return str(a[0]) if a.size else None


def map_hash(m: np.ndarray) -> str:
    return hashlib.blake2b(np.asarray(m.shape, np.int32).tobytes() + m.tobytes(), digest_size=16).hexdigest()


def value_counts(s: pd.Series) -> dict:
    return {str(k): int(v) for k, v in s.value_counts(dropna=False).items()}


def load() -> pd.DataFrame:
    df = pd.read_pickle(PKL)
    df["label"] = df["failureType"].map(first_str)
    df["split"] = df["trianTestLabel"].map(first_str)
    df["h"] = df["waferMap"].map(lambda m: m.shape[0])
    df["w"] = df["waferMap"].map(lambda m: m.shape[1])
    df["n_die"] = df["waferMap"].map(lambda m: int((m > 0).sum()))
    df["n_defect"] = df["waferMap"].map(lambda m: int((m == 2).sum()))
    df["hash"] = df["waferMap"].map(map_hash)
    return df


def near_duplicate_pairs(lab: pd.DataFrame, max_px: int = NEAR_PX) -> pd.DataFrame:
    """All same-shape labeled pairs (a < b) whose maps differ in <= max_px pixels."""
    out = []
    for (h, w), idx in lab.groupby(["h", "w"]).groups.items():
        if len(idx) < 2:
            continue
        ids = np.asarray(idx)
        maps = np.stack(lab.loc[ids, "waferMap"].to_list())
        x = np.concatenate([(maps == v).reshape(len(ids), -1) for v in (0, 1, 2)], axis=1).astype(np.float32)
        for s in range(0, len(ids), 2048):
            mismatch = h * w - x[s:s + 2048] @ x.T  # pixels that differ
            ii, jj = np.nonzero(mismatch <= max_px + 0.5)
            keep = ii + s < jj
            ii, jj = ii[keep], jj[keep]
            out.append(np.column_stack([ids[ii + s], ids[jj], np.rint(mismatch[ii, jj]).astype(int)]))
    return pd.DataFrame(np.concatenate(out), columns=["a", "b", "px"])


def lot_components(lab: pd.DataFrame, pairs: pd.DataFrame) -> pd.Series:
    """Connected components of lots linked by near-copy pairs (union-find)."""
    parent = {lot: lot for lot in lab["lotName"].unique()}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in zip(lab.loc[pairs["a"], "lotName"].values, lab.loc[pairs["b"], "lotName"].values):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    return lab["lotName"].map(find)


def leak_share(is_test: pd.Series, pairs: pd.DataFrame, subset: pd.Series) -> float:
    """Share of test wafers in `subset` that have a train wafer among their near-copy pairs."""
    a_test, b_test = is_test.loc[pairs["a"]].values, is_test.loc[pairs["b"]].values
    leaked = set(pairs["a"].values[a_test & ~b_test]) | set(pairs["b"].values[b_test & ~a_test])
    test_ids = is_test.index[is_test & subset]
    return round(len(leaked & set(test_ids)) / len(test_ids), 4)


def summarize(df: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    lab = df[df["label"].notna()]
    s = {"source": "scripts/explore_data.py", "seed": SEED, "near_px": NEAR_PX}

    # --- rows and labels
    s["rows"] = {
        "total": len(df), "labeled": len(lab), "unlabeled": int(df["label"].isna().sum()),
        "index_is_range": isinstance(df.index, pd.RangeIndex) and df.index[0] == 0 and df.index[-1] == len(df) - 1,
    }
    s["label_values_raw"] = value_counts(df["label"])
    s["split_values_raw"] = value_counts(df["split"])
    s["class_counts"] = {c: int((lab["label"] == c).sum()) for c in CLASSES}
    s["class_by_split"] = {c: value_counts(lab.loc[lab["label"] == c, "split"]) for c in CLASSES}
    s["split_by_labeled"] = {
        "labeled": value_counts(lab["split"]),
        "unlabeled": value_counts(df.loc[df["label"].isna(), "split"]),
    }

    # --- map shapes
    shape_all = df["h"].astype(str) + "x" + df["w"].astype(str)
    shape_lab = shape_all[lab.index]
    per_shape = shape_lab.value_counts()
    rare = shape_lab.isin(per_shape[per_shape < 10].index)
    train_shapes = set(shape_lab[lab["split"] == "Training"])
    aspect = lab["h"] / lab["w"]
    s["shapes"] = {
        "distinct_all": int(shape_all.nunique()), "distinct_labeled": int(per_shape.size),
        "labeled_h_min_median_max": [int(lab["h"].min()), float(lab["h"].median()), int(lab["h"].max())],
        "labeled_w_min_median_max": [int(lab["w"].min()), float(lab["w"].median()), int(lab["w"].max())],
        "labeled_top10": {k: int(v) for k, v in per_shape.head(10).items()},
        "labeled_in_shapes_with_lt10_members": int(rare.sum()),
        "defect_share_in_rare_shapes": round(float((lab.loc[rare, "label"] != "none").mean()), 4),
        "defect_share_all_labeled": round(float((lab["label"] != "none").mean()), 4),
        "median_h_by_class": {c: float(lab.loc[lab["label"] == c, "h"].median()) for c in CLASSES},
        "labeled_aspect_h_over_w_outside_0.9_1.1": int(((aspect < 0.9) | (aspect > 1.1)).sum()),
        "test_wafers_with_shape_absent_from_training": int(
            ((lab["split"] == "Test") & ~shape_lab.isin(train_shapes)).sum()),
        "center_share_in_25x27": round(float((shape_lab[lab["label"] == "Center"] == "25x27").mean()), 4),
    }

    # --- pixels
    values, dtypes = Counter(), Counter()
    for m in df["waferMap"]:
        dtypes[str(m.dtype)] += 1
        values.update(np.unique(m).tolist())
    density = lab["n_defect"] / lab["n_die"]
    s["pixels"] = {
        "value_counts_maps_containing": {str(int(k)): int(v) for k, v in sorted(values.items())},
        "dtypes": dict(dtypes),
        "maps_without_die": int((df["n_die"] == 0).sum()),
        "dieSize_equals_n_die": int((df["dieSize"] == df["n_die"]).sum()),
        "maps_all_dies_defective_by_label": value_counts(df.loc[df["n_defect"] == df["n_die"], "label"]),
        "maps_without_defect_by_label": value_counts(df.loc[df["n_defect"] == 0, "label"]),
        "labeled_maps_lt100_dies": {str(i): [int(df.at[i, "h"]), int(df.at[i, "w"]), int(df.at[i, "n_die"]),
                                             df.at[i, "label"]] for i in lab.index[lab["n_die"] < 100]},
        "defect_density_by_class_p5_median_p95": {
            c: [round(float(q), 4) for q in density[lab["label"] == c].quantile([0.05, 0.5, 0.95])] for c in CLASSES
        },
        "none_with_density_gt_0.2": int(((lab["label"] == "none") & (density > 0.2)).sum()),
    }

    # --- lots
    per_lot = df.groupby("lotName").size()
    lab_per_lot = df["label"].notna().groupby(df["lotName"]).agg(["sum", "size"])
    lab_split_per_lot = lab.groupby("lotName")["split"].nunique()
    same_class_in_lot = lab.groupby(["lotName", "label"])["label"].transform("size")
    s["lots"] = {
        "distinct_all": int(per_lot.size), "distinct_labeled": int(lab["lotName"].nunique()),
        "wafers_per_lot_min_median_max": [int(per_lot.min()), float(per_lot.median()), int(per_lot.max())],
        "waferIndex_min_max": [float(df["waferIndex"].min()), float(df["waferIndex"].max())],
        "waferIndex_all_integer": bool((df["waferIndex"] % 1 == 0).all()),
        "duplicated_lot_waferIndex": int(df.duplicated(["lotName", "waferIndex"]).sum()),
        "lots_fully_labeled": int((lab_per_lot["sum"] == lab_per_lot["size"]).sum()),
        "lots_partially_labeled": int(((lab_per_lot["sum"] > 0) & (lab_per_lot["sum"] < lab_per_lot["size"])).sum()),
        "lots_unlabeled": int((lab_per_lot["sum"] == 0).sum()),
        "labeled_lots_in_both_train_and_test": int((lab_split_per_lot > 1).sum()),
        "share_with_same_class_lotmate": {
            c: round(float((same_class_in_lot[lab["label"] == c] >= 2).mean()), 4) for c in DEFECTS},
        "share_with_same_class_lotmate_all_defects": round(
            float((same_class_in_lot[lab["label"] != "none"] >= 2).mean()), 4),
    }

    # --- exact duplicates (same shape and bytes)
    dup_all = df["hash"].duplicated(keep=False)
    size_lab = lab.groupby("hash")["hash"].transform("size")
    labd = lab[size_lab > 1]
    cross = labd.groupby("hash")["split"].nunique()
    cross = cross[cross > 1].index
    n_labels = labd.groupby("hash")["label"].nunique()
    conflict_hashes = n_labels[n_labels > 1].index
    conflict_groups = [sorted(labd.index[labd["hash"] == h].tolist()) for h in conflict_hashes]
    unlabeled_hashes = set(df.loc[df["label"].isna(), "hash"])
    test_copies = lab[lab["hash"].isin(cross) & (lab["split"] == "Test")]
    s["duplicates"] = {
        "distinct_maps_all": int(df["hash"].nunique()),
        "rows_in_duplicate_groups_all": int(dup_all.sum()),
        "maps_without_defect_all": int((df["n_defect"] == 0).sum()),
        "labeled_duplicate_groups": int(labd["hash"].nunique()), "labeled_rows_in_duplicate_groups": len(labd),
        "groups_spanning_training_and_test": len(cross),
        "test_rows_copied_from_training": len(test_copies),
        "test_rows_copied_from_training_by_class": value_counts(test_copies["label"]),
        "label_conflict_groups": len(conflict_groups),
        "label_conflicts": [[[i, lab.at[i, "label"], lab.at[i, "split"], lab.at[i, "lotName"]] for i in g]
                            for g in conflict_groups],
        "labeled_rows_with_unlabeled_twin_by_split": value_counts(lab.loc[lab["hash"].isin(unlabeled_hashes), "split"]),
    }

    # --- near-copies and split leakage
    pairs = near_duplicate_pairs(lab)
    cross_lot = lab.loc[pairs["a"], "lotName"].values != lab.loc[pairs["b"], "lotName"].values
    has_nonexact_cross = set(pairs.loc[cross_lot & (pairs["px"] > 0), ["a", "b"]].values.ravel())
    comp = lot_components(lab, pairs[cross_lot])
    comp_sizes = comp.value_counts()
    s["near_copies"] = {
        "pairs_le_near_px": len(pairs), "exact_pairs": int((pairs["px"] == 0).sum()),
        "cross_lot_pairs": int(cross_lot.sum()),
        "wafers_with_nonexact_cross_lot_near_copy_by_class": {
            c: int(lab.loc[list(has_nonexact_cross), "label"].eq(c).sum()) for c in CLASSES},
        "lot_components": int(comp_sizes.size), "largest_component_wafers": int(comp_sizes.iloc[0]),
        "largest_component_share": round(float(comp_sizes.iloc[0] / len(lab)), 4),
    }

    splits = {
        "random_stratified": pd.Series(lab.index.isin(train_test_split(
            lab.index, test_size=0.2, stratify=lab["label"], random_state=SEED)[1]), index=lab.index),
    }
    for name, groups in (("group_lot", lab["lotName"]), ("group_lot_near_copy_component", comp)):
        _, te = next(GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=SEED).split(lab, groups=groups))
        splits[name] = pd.Series(np.isin(np.arange(len(lab)), te), index=lab.index)
    splits["original_trianTestLabel"] = lab["split"] == "Test"
    exact = pairs[pairs["px"] == 0]
    s["split_leakage"] = {
        name: {
            "test_share": round(float(t.mean()), 4),
            "test_with_train_near_copy_all": leak_share(t, pairs, pd.Series(True, index=lab.index)),
            "test_with_train_near_copy_defect": leak_share(t, pairs, lab["label"] != "none"),
            "test_with_train_near_copy_center": leak_share(t, pairs, lab["label"] == "Center"),
            "test_with_train_exact_copy_all": leak_share(t, exact, pd.Series(True, index=lab.index)),
            "test_defect_with_same_class_lotmate_in_train": round(_lotmate_leak(lab, t), 4),
        }
        for name, t in splits.items()
    }

    rng = np.random.default_rng(SEED)
    s["example_ids"] = {
        c: sorted(rng.choice(lab.index[lab["label"] == c], N_EXAMPLES, replace=False).tolist()) for c in CLASSES
    }
    return s, pairs


def _lotmate_leak(lab: pd.DataFrame, is_test: pd.Series) -> float:
    """Share of test defect wafers whose lot has a same-class wafer in train."""
    train_keys = set(zip(lab.loc[~is_test, "lotName"], lab.loc[~is_test, "label"]))
    test_def = lab[is_test & (lab["label"] != "none")]
    return float(np.mean([k in train_keys for k in zip(test_def["lotName"], test_def["label"])]))


def style(ax, grid_axis="x"):
    ax.grid(axis=grid_axis, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left" if grid_axis == "x" else "bottom"):
        ax.spines[side].set_visible(False)
    ax.tick_params(length=0)


def hbar(ax, names, values, title):
    y = np.arange(len(names))[::-1]
    ax.barh(y, values, height=0.55, color=SERIES)
    ax.set_yticks(y, names)
    ax.set_title(title, loc="left", fontsize=11, color=INK)
    ax.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(4))
    ax.xaxis.set_major_formatter(matplotlib.ticker.StrMethodFormatter("{x:,.0f}"))
    for yi, v in zip(y, values):
        ax.text(v, yi, f" {v:,}", va="center", ha="left", color=INK2, fontsize=9)
    ax.set_xlim(0, max(values) * 1.18)
    style(ax)


def draw_map(ax, m, title, fontsize=6):
    ax.imshow(m, cmap=WAFER_CMAP, vmin=0, vmax=2, interpolation="nearest")
    ax.set_xticks([])
    ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.set_title(title, fontsize=fontsize, color=INK2, pad=2)


def wafer_legend(fig, y):
    fig.legend(handles=[Patch(color=WAFER_COLORS[i], label=t, ec=GRID) for i, t in
                        enumerate(["웨이퍼 밖 (0)", "정상 다이 (1)", "불량 다이 (2)"])],
               loc="upper center", bbox_to_anchor=(0.5, y), ncol=3, frameon=False, fontsize=9)


def plot_distribution(s: dict):
    fig, (a, b) = plt.subplots(1, 2, figsize=(11, 4.2), gridspec_kw={"width_ratios": [1, 1.3]})
    cc = s["class_counts"]
    hbar(a, ["라벨 없음", "none (정상)", "결함 8종 합계"],
         [s["rows"]["unlabeled"], cc["none"], sum(cc[c] for c in DEFECTS)],
         f"전체 {s['rows']['total']:,}장의 구성")
    order = sorted(DEFECTS, key=lambda c: -cc[c])
    hbar(b, order, [cc[c] for c in order], "결함 패턴 8종 (라벨 있는 웨이퍼)")
    fig.tight_layout()
    fig.savefig(OUT / "class_distribution.png", dpi=150)
    plt.close(fig)


def plot_sizes(df: pd.DataFrame):
    lab = df[df["label"].notna()]
    shape_counts = lab.groupby(["w", "h"]).size().reset_index(name="n")
    fig, (a, b) = plt.subplots(1, 2, figsize=(11, 4.4))
    a.scatter(shape_counts["w"], shape_counts["h"], s=4 + 400 * shape_counts["n"] / shape_counts["n"].max(),
              color=SERIES, alpha=0.45, linewidths=0)
    a.set_xlabel("맵 폭 W (다이 칸 수)")
    a.set_ylabel("맵 높이 H (다이 칸 수)")
    a.set_title(f"맵 크기 {len(shape_counts)}종 (라벨 있는 웨이퍼, 원 크기 ∝ 장수)", loc="left", fontsize=11, color=INK)
    b.hist(lab["n_die"], bins=80, color=SERIES)
    b.set_xlabel("웨이퍼 한 장의 다이 수 (값 > 0 인 칸)")
    b.set_ylabel("웨이퍼 수")
    b.set_title("다이 수 분포 (라벨 있는 웨이퍼)", loc="left", fontsize=11, color=INK)
    for ax in (a, b):
        ax.xaxis.set_major_formatter(matplotlib.ticker.StrMethodFormatter("{x:,.0f}"))
        ax.yaxis.set_major_formatter(matplotlib.ticker.StrMethodFormatter("{x:,.0f}"))
        ax.grid(color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        ax.tick_params(length=0)
    fig.tight_layout()
    fig.savefig(OUT / "map_sizes.png", dpi=150)
    plt.close(fig)


def plot_examples(df: pd.DataFrame, s: dict):
    fig, axes = plt.subplots(len(CLASSES), N_EXAMPLES, figsize=(N_EXAMPLES * 1.25 + 1.6, len(CLASSES) * 1.3 + 0.6))
    for r, c in enumerate(CLASSES):
        for k, idx in enumerate(s["example_ids"][c]):
            draw_map(axes[r, k], df.at[idx, "waferMap"], str(idx))
        axes[r, 0].set_ylabel(f"{c}\n(n={s['class_counts'][c]:,})", rotation=0, ha="right", va="center",
                              fontsize=9, color=INK, labelpad=8)
    fig.suptitle(f"클래스별 무작위 예시 {N_EXAMPLES}장 (seed {SEED}, 숫자 = 행 번호)", y=0.995, fontsize=11)
    wafer_legend(fig, 0.975)
    fig.tight_layout(rect=(0, 0, 1, 0.955))
    fig.savefig(OUT / "class_examples.png", dpi=150)
    plt.close(fig)


def plot_conflicts(df: pd.DataFrame, s: dict):
    groups = s["duplicates"]["label_conflicts"]
    per_row = 4
    rows = -(-len(groups) // per_row)
    fig, axes = plt.subplots(rows, per_row * 2, figsize=(per_row * 2 * 1.35, rows * 1.75 + 0.7))
    for ax in axes.ravel():
        ax.axis("off")
    for g, members in enumerate(groups):
        for k, (idx, label, split, _) in enumerate(members[:2]):
            ax = axes[g // per_row, (g % per_row) * 2 + k]
            ax.axis("on")
            draw_map(ax, df.at[idx, "waferMap"], f"{idx}\n{label} ({split})", fontsize=7)
    fig.suptitle(f"픽셀까지 같은 맵인데 라벨이 다른 쌍 {len(groups)}개 (왼쪽·오른쪽이 한 쌍)", y=0.995, fontsize=11)
    wafer_legend(fig, 0.965)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(OUT / "duplicate_label_conflicts.png", dpi=150)
    plt.close(fig)


def plot_leakage(s: dict):
    names = {"random_stratified": "무작위 (계층화)", "group_lot": "lot 단위 그룹",
             "group_lot_near_copy_component": "lot + 근사 복사본 연결 성분", "original_trianTestLabel": "원본 분할"}
    keys = list(names)
    y = np.arange(len(keys))[::-1]
    fig, ax = plt.subplots(figsize=(9, 3.6))
    for off, (metric, color, label) in zip((0.17, -0.17), (
            ("test_with_train_near_copy_defect", SERIES, "결함 웨이퍼 전체"),
            ("test_with_train_near_copy_center", SERIES2, "Center"))):
        vals = [100 * s["split_leakage"][k][metric] for k in keys]
        ax.barh(y + off, vals, height=0.3, color=color, label=label)
        for yi, v in zip(y + off, vals):
            ax.text(v, yi, f" {v:.1f}%", va="center", ha="left", color=INK2, fontsize=9)
    ax.set_yticks(y, [names[k] for k in keys])
    ax.xaxis.set_major_formatter(matplotlib.ticker.StrMethodFormatter("{x:.0f}%"))
    ax.set_xlim(0, max(100 * s["split_leakage"][k]["test_with_train_near_copy_center"] for k in keys) * 1.2)
    ax.set_title(f"평가(test) 웨이퍼 중 학습 쪽에 {NEAR_PX}픽셀 이내로 같은 맵이 있는 비율 (80/20, seed {SEED})",
                 loc="left", fontsize=11, color=INK)
    ax.legend(frameon=False, loc="lower right", fontsize=9)
    style(ax)
    fig.tight_layout()
    fig.savefig(OUT / "split_leakage.png", dpi=150)
    plt.close(fig)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    df = load()
    s, _ = summarize(df)
    (OUT / "summary.json").write_text(json.dumps(s, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in s.items() if k != "example_ids"}, indent=1, ensure_ascii=False))
    plot_distribution(s)
    plot_sizes(df)
    plot_examples(df, s)
    plot_conflicts(df, s)
    plot_leakage(s)
    print(f"[saved] {OUT}")


if __name__ == "__main__":
    main()
