"""Figures for the 7-page portfolio (sized 1:1 in inches for the slide, so font points are true).

Usage (from project root):
    .venv\\Scripts\\python portfolio\\make_figures.py

Reads outputs/*.json, .tmp/cnn_biased_split/results.json (pre-fix split, for the
before/after figure) and data/raw/LSWMD.pkl (wafer maps). Writes portfolio/fig/*.png.
Font: Pretendard (user-installed OTF; see portfolio/README section in README.md).
"""
import json
import os
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.colors import ListedColormap  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from explore_data import CLASSES  # noqa: E402

FIG = ROOT / "portfolio" / "fig"
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#ffffff"
BLUE, ORANGE, GRAY = "#2a78d6", "#eb6834", "#8f8e8a"
WAFER = ListedColormap([SURFACE, "#d6d5d0", "#184f95"])
DPI = 200


def register_fonts():
    """Pretendard is installed per user (not in C:/Windows/Fonts), so register the files explicitly."""
    user_fonts = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/Windows/Fonts"
    found = 0
    for p in sorted(list(user_fonts.glob("Pretendard-*.ttf")) + list(user_fonts.glob("Pretendard-*.otf"))):
        font_manager.fontManager.addfont(str(p))
        found += 1
    return found


N_FONTS = register_fonts()
plt.rcParams.update({
    "font.family": "Pretendard" if N_FONTS else "Malgun Gothic", "axes.unicode_minus": False, "font.size": 11,
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "text.color": INK, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "axes.edgecolor": GRID, "axes.linewidth": 0.8,
})


def quiet(ax, grid_axis="x"):
    ax.grid(axis=grid_axis, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left" if grid_axis == "x" else "bottom"):
        ax.spines[side].set_visible(False)
    ax.tick_params(length=0)


def draw_map(ax, m, title="", size=11):
    ax.imshow(m, cmap=WAFER, vmin=0, vmax=2, interpolation="nearest")
    ax.set_xticks([])
    ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_visible(False)
    if title:
        ax.set_title(title, fontsize=size, color=INK2, pad=3)


def save(fig, name):
    fig.savefig(FIG / name, dpi=DPI)
    plt.close(fig)
    print("[saved]", name)


def fig_cover(maps, examples):
    fig, axes = plt.subplots(1, 9, figsize=(11.9, 1.6))
    for ax, c in zip(axes, CLASSES):
        draw_map(ax, maps[examples[c][0]], c, size=11)
    fig.subplots_adjust(left=0.005, right=0.995, top=0.8, bottom=0.02, wspace=0.18)
    save(fig, "p1_wafer_strip.png")


def fig_leakage(maps, conflicts, leak):
    # (a) leakage rate by split rule: the main evidence, drawn large
    fig, ax = plt.subplots(figsize=(5.6, 2.9))
    names = ["무작위 분할", "lot 단위 분할", "lot+복사본 묶음 (채택)", "원본 분할"]
    keys = ["random_stratified", "group_lot", "group_lot_near_copy_component", "original_trianTestLabel"]
    y = np.arange(len(names))[::-1]
    for off, (metric, color, label) in zip((0.19, -0.19), (
            ("test_with_train_near_copy_defect", GRAY, "불량 웨이퍼 전체"),
            ("test_with_train_near_copy_center", BLUE, "Center"))):
        vals = [100 * leak[k][metric] for k in keys]
        ax.barh(y + off, vals, height=0.34, color=color, label=label)
        for yi, v in zip(y + off, vals):
            ax.text(v + 0.6, yi, f"{v:.1f}%" if v else "0%", va="center", ha="left", color=INK2, fontsize=11)
    ax.set_yticks(y, names, fontsize=12)
    ax.set_xlim(0, 52)
    ax.xaxis.set_major_formatter(matplotlib.ticker.StrMethodFormatter("{x:.0f}%"))
    fig.text(0.01, 0.975, "test 웨이퍼 중 학습 쪽에 10픽셀 이내 복사본이 있는 비율", fontsize=12.5, color=INK,
             va="top", weight="bold")
    ax.legend(frameon=False, loc="lower right", fontsize=11)
    quiet(ax)
    fig.subplots_adjust(left=0.33, right=0.98, top=0.84, bottom=0.14)
    save(fig, "p3_leakage.png")

    # (b) the same map carrying two labels across the original Training/Test split
    fig = plt.figure(figsize=(5.6, 1.55))
    gs = fig.add_gridspec(1, 4, left=0.01, right=0.99, top=0.66, bottom=0.03, wspace=0.55)
    for k, group in enumerate(conflicts[:4]):
        sub = gs[k].subgridspec(1, 2, wspace=0.3)
        for j, (idx, label, split, _) in enumerate(group[:2]):
            ax = fig.add_subplot(sub[j])
            draw_map(ax, maps[idx], f"{label}\n({split})", size=8)
    fig.text(0.01, 0.985, "같은 맵, 다른 라벨: 원본 Training/Test 사이 복사본 14쌍 중 4쌍", fontsize=12.5,
             color=INK, va="top", weight="bold")
    save(fig, "p3_pairs.png")


def fig_recall(bt, ft):
    fig, ax = plt.subplots(figsize=(5.6, 4.4))
    y = np.arange(len(CLASSES))[::-1]
    for off, (res, color, label) in zip((0.19, -0.19), ((bt, GRAY, "베이스라인 (특징 23개 + 랜덤 포레스트)"),
                                                          (ft, BLUE, "CNN (최종)"))):
        r = np.array([res["per_class"][c]["recall"] for c in CLASSES])
        lo = np.array([res["per_class"][c]["recall_ci95"][0] for c in CLASSES])
        hi = np.array([res["per_class"][c]["recall_ci95"][1] for c in CLASSES])
        ax.barh(y + off, r, height=0.34, color=color, label=label)
        ax.errorbar(r, y + off, xerr=[r - lo, hi - r], fmt="none", ecolor=INK2, elinewidth=0.8, capsize=2)
        for yi, v in zip(y + off, r):
            ax.text(1.03, yi, f"{v:.2f}", va="center", ha="left", color=INK2, fontsize=10.5)
    ax.axvline(0.5, color=INK2, linewidth=1)
    ax.text(0.505, len(CLASSES) - 0.45, "기준 0.50", color=INK2, fontsize=10.5, va="bottom")
    ax.set_yticks(y, [f"{c} ({ft['per_class'][c]['support']:,})" for c in CLASSES], fontsize=11)
    ax.set_xlim(0, 1.13)
    ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.set_xlabel("test recall (가는 선: 95% 신뢰구간)", fontsize=11)
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.42, -0.17), ncol=2, fontsize=10.5)
    quiet(ax)
    fig.subplots_adjust(left=0.28, right=0.99, top=0.97, bottom=0.22)
    save(fig, "p4_recall.png")


def fig_e11(before, after):
    fig, ax = plt.subplots(figsize=(5.5, 3.0))
    groups = ["수정 전 분할\n(큰 덩어리가 test에 고정)", "수정 후 분할\n(fold 배정을 무작위로)"]
    x = np.arange(2)
    for off, (key, color, label) in zip((-0.19, 0.19), (("rf", GRAY, "베이스라인"), ("cnn", BLUE, "CNN"))):
        vals = [before[key], after[key]]
        ax.bar(x + off, vals, width=0.34, color=color, label=label)
        for xi, v in zip(x + off, vals):
            ax.text(xi, v + 0.02, f"{v:.2f}", ha="center", va="bottom", color=INK2, fontsize=11)
    ax.set_xticks(x, groups, fontsize=11)
    ax.set_ylim(0, 1.15)
    ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.set_ylabel("Loc test recall", fontsize=11)
    ax.legend(frameon=False, loc="upper center", fontsize=10.5, ncol=2)
    quiet(ax, grid_axis="y")
    fig.subplots_adjust(left=0.14, right=0.98, top=0.95, bottom=0.26)
    save(fig, "p5_e11.png")


def main():
    FIG.mkdir(parents=True, exist_ok=True)
    print(f"[fonts] Pretendard files registered: {N_FONTS}")
    eda = json.loads((ROOT / "outputs/eda/summary.json").read_text(encoding="utf-8"))
    base = json.loads((ROOT / "outputs/baseline/results.json").read_text(encoding="utf-8"))
    cnn = json.loads((ROOT / "outputs/cnn/results.json").read_text(encoding="utf-8"))
    biased = json.loads((ROOT / ".tmp/cnn_biased_split/results.json").read_text(encoding="utf-8"))
    bt = base["splits"]["split_main"]["rf_balanced"]["test"]
    ft = cnn["final"]["test"]

    ids = {examples[0] for examples in eda["example_ids"].values()}
    ids |= {m[0] for g in eda["duplicates"]["label_conflicts"][:4] for m in g[:2]}
    raw = pd.read_pickle(ROOT / "data/raw/LSWMD.pkl")
    maps = raw.loc[sorted(ids), "waferMap"].to_dict()
    del raw

    fig_cover(maps, eda["example_ids"])
    fig_leakage(maps, eda["duplicates"]["label_conflicts"], eda["split_leakage"])
    fig_recall(bt, ft)
    # Loc recall before the split-procedure fix (biased split; RF value from LOG 17:12 run) and after
    before = {"rf": 0.624, "cnn": biased["final"]["test"]["per_class"]["Loc"]["recall"]}
    after = {"rf": bt["per_class"]["Loc"]["recall"], "cnn": ft["per_class"]["Loc"]["recall"]}
    fig_e11(before, after)
    print(json.dumps({"e11_before": before, "e11_after": after}))


if __name__ == "__main__":
    main()
