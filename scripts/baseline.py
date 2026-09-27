"""Stage 3b: baselines on both splits.

Usage (from project root):
    .venv\\Scripts\\python scripts\\baseline.py

Models: majority class; hand-crafted features + logistic regression / random forest
(with and without class weighting); shuffled-label control; map-size-only control.
Metrics on test with a cluster (component) bootstrap 95 % CI.
Reads data/processed/labeled_clean.pkl (make_splits.py); writes outputs/baseline/.
"""
import json
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import ndimage  # noqa: E402
from sklearn.dummy import DummyClassifier  # noqa: E402
from sklearn.ensemble import RandomForestClassifier  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.pipeline import make_pipeline  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

from explore_data import CLASSES, GRID, INK, INK2, SEED, SURFACE  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed" / "labeled_clean.pkl"
OUT = ROOT / "outputs" / "baseline"
N_BOOT = 1000
RING_EDGES = [0, 0.2, 0.4, 0.6, 0.8, 0.9, np.inf]  # normalized elliptical radius
N_SECTORS = 8
NONE = CLASSES.index("none")
SPLITS = ("split_main", "split_random")

plt.rcParams.update({"font.family": "Malgun Gothic", "axes.unicode_minus": False, "font.size": 10,
                     "figure.facecolor": SURFACE, "savefig.facecolor": SURFACE, "text.color": INK})

_geometry = {}


def geometry(h: int, w: int):
    """Normalized elliptical radius and angle of every cell (the wafer fills its map box as an ellipse)."""
    if (h, w) not in _geometry:
        yy, xx = np.mgrid[0:h, 0:w]
        dy, dx = (yy + 0.5 - h / 2) / (h / 2), (xx + 0.5 - w / 2) / (w / 2)
        _geometry[(h, w)] = (np.sqrt(dy ** 2 + dx ** 2), np.arctan2(dy, dx), yy * 3 // h, xx * 3 // w)
    return _geometry[(h, w)]


def frac(bad: np.ndarray, sel: np.ndarray) -> float:
    n = sel.sum()
    return float(bad[sel].sum() / n) if n else 0.0


def wafer_features(m: np.ndarray) -> list[float]:
    h, w = m.shape
    r, theta, gy, gx = geometry(h, w)
    die, bad = m > 0, m == 2
    f = [frac(bad, die)]
    f += [frac(bad, die & (r >= a) & (r < b)) for a, b in zip(RING_EDGES[:-1], RING_EDGES[1:])]
    outer = die & (r >= 0.8)
    sector = ((theta + np.pi) / (2 * np.pi) * N_SECTORS).astype(int) % N_SECTORS
    sec = [frac(bad, outer & (sector == k)) for k in range(N_SECTORS)]
    f += [max(sec), min(sec), float(np.std(sec))]
    f += [frac(bad, die & (gy == i) & (gx == j)) for i in range(3) for j in range(3)]
    cc, n = ndimage.label(bad, structure=np.ones((3, 3)))
    if n:
        sizes = np.bincount(cc.ravel())[1:]
        ys, xs = np.nonzero(cc == sizes.argmax() + 1)
        cov = np.cov(np.vstack([ys, xs])) + np.eye(2) / 12 if len(ys) > 1 else np.eye(2) / 12
        ev = np.linalg.eigvalsh(cov)
        f += [n / die.sum(), sizes.max() / die.sum(), float(np.sqrt(ev[1] / ev[0])), float(r[ys, xs].mean())]
    else:
        f += [0.0, 0.0, 1.0, 0.0]
    return f


FEATURE_NAMES = (["density"] + [f"ring_{a}_{b}" for a, b in zip(RING_EDGES[:-1], RING_EDGES[1:])]
                 + ["edge_sector_max", "edge_sector_min", "edge_sector_std"]
                 + [f"grid_{i}{j}" for i in range(3) for j in range(3)]
                 + ["n_components_per_die", "largest_cc_frac", "largest_cc_elongation", "largest_cc_radius"])


def scores(cm: np.ndarray) -> dict:
    tp = np.diag(cm).astype(float)
    support, predicted = cm.sum(1), cm.sum(0)
    recall = np.divide(tp, support, out=np.zeros_like(tp), where=support > 0)
    precision = np.divide(tp, predicted, out=np.zeros_like(tp), where=predicted > 0)
    f1 = np.divide(2 * precision * recall, precision + recall, out=np.zeros_like(tp), where=(precision + recall) > 0)
    return {"macro_f1": f1.mean(), "defect8_macro_f1": np.delete(f1, NONE).mean(), "balanced_acc": recall.mean(),
            "accuracy": tp.sum() / cm.sum(), "recall": recall, "precision": precision, "f1": f1}


def evaluate(y: np.ndarray, p: np.ndarray, groups: np.ndarray, rng: np.random.Generator) -> dict:
    k = len(CLASSES)
    cm = np.bincount(y * k + p, minlength=k * k).reshape(k, k)
    point = scores(cm)
    # cluster bootstrap: resample components (wafers in a component are correlated)
    g_codes, g_idx = np.unique(groups, return_inverse=True)
    per_group = np.zeros((len(g_codes), k * k))
    np.add.at(per_group, (g_idx, y * k + p), 1)
    boot = {"macro_f1": [], "defect8_macro_f1": [], "balanced_acc": [], "recall": []}
    for _ in range(N_BOOT):
        s = scores(per_group[rng.integers(0, len(g_codes), len(g_codes))].sum(0).reshape(k, k))
        for key in boot:
            boot[key].append(s[key])
    ci = {key: np.percentile(np.array(v), [2.5, 97.5], axis=0) for key, v in boot.items()}
    out = {key: round(float(point[key]), 4) for key in ("macro_f1", "defect8_macro_f1", "balanced_acc", "accuracy")}
    out.update({f"{key}_ci95": [round(float(x), 4) for x in ci[key]] for key in ("macro_f1", "defect8_macro_f1",
                                                                                  "balanced_acc")})
    out["per_class"] = {c: {"recall": round(float(point["recall"][i]), 4),
                            "recall_ci95": [round(float(ci["recall"][0][i]), 4), round(float(ci["recall"][1][i]), 4)],
                            "precision": round(float(point["precision"][i]), 4), "f1": round(float(point["f1"][i]), 4),
                            "support": int(cm[i].sum())} for i, c in enumerate(CLASSES)}
    out["confusion"] = cm.tolist()
    return out


def models():
    rf = dict(n_estimators=300, min_samples_leaf=2, n_jobs=-1, random_state=SEED)
    lr = dict(max_iter=3000)
    return {
        "majority": (DummyClassifier(strategy="most_frequent"), "features"),
        "logreg": (make_pipeline(StandardScaler(), LogisticRegression(**lr)), "features"),
        "logreg_balanced": (make_pipeline(StandardScaler(), LogisticRegression(class_weight="balanced", **lr)),
                            "features"),
        "rf": (RandomForestClassifier(**rf), "features"),
        "rf_balanced": (RandomForestClassifier(class_weight="balanced_subsample", **rf), "features"),
        "rf_balanced_shuffled_labels": (RandomForestClassifier(class_weight="balanced_subsample", **rf), "features"),
        "rf_balanced_map_size_only": (RandomForestClassifier(class_weight="balanced_subsample", **rf), "size"),
    }


def plot_confusion(cm: np.ndarray, title: str, path: Path):
    norm = cm / np.maximum(cm.sum(1, keepdims=True), 1)
    fig, ax = plt.subplots(figsize=(7.6, 6.4))
    ax.imshow(norm, cmap=matplotlib.colors.LinearSegmentedColormap.from_list("b", ["#fcfcfb", "#104281"]),
              vmin=0, vmax=1)
    for i in range(len(CLASSES)):
        for j in range(len(CLASSES)):
            if cm[i, j]:
                ax.text(j, i, f"{100 * norm[i, j]:.0f}", ha="center", va="center", fontsize=8,
                        color="white" if norm[i, j] > 0.55 else INK)
    ax.set_xticks(range(len(CLASSES)), CLASSES, rotation=45, ha="right")
    ax.set_yticks(range(len(CLASSES)), [f"{c} ({cm[i].sum():,})" for i, c in enumerate(CLASSES)])
    ax.set_xlabel("예측", color=INK2)
    ax.set_ylabel("정답 (test 장수)", color=INK2)
    ax.set_title(title, loc="left", fontsize=10.5)
    for sp in ax.spines.values():
        sp.set_color(GRID)
    ax.tick_params(length=0)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    df = pd.read_pickle(PROCESSED)
    X = np.array([wafer_features(m) for m in df["waferMap"]], dtype=np.float32)
    X_size = df[["h", "w", "n_die"]].to_numpy(dtype=np.float32)
    y = df["label"].map({c: i for i, c in enumerate(CLASSES)}).to_numpy()
    groups = df["component"].to_numpy()
    print(f"[features] {X.shape} in {time.perf_counter() - t0:.0f} s")

    results = {"source": "scripts/baseline.py", "seed": SEED, "n_boot": N_BOOT, "features": FEATURE_NAMES,
               "splits": {}}
    predictions = []
    for split in SPLITS:
        tr, va, te = (df[split] == s for s in ("train", "val", "test"))
        results["splits"][split] = {}
        for name, (model, inputs) in models().items():
            t1 = time.perf_counter()
            Xs = X if inputs == "features" else X_size
            y_fit = y[tr]
            if name.endswith("shuffled_labels"):
                y_fit = np.random.default_rng(SEED).permutation(y_fit)
            model.fit(Xs[tr], y_fit)
            p_va, p_te = model.predict(Xs[va]), model.predict(Xs[te])
            rng = np.random.default_rng(SEED)
            results["splits"][split][name] = {
                "val": evaluate(y[va], p_va, groups[va], rng), "test": evaluate(y[te], p_te, groups[te], rng),
                "fit_seconds": round(time.perf_counter() - t1, 1),
            }
            predictions.append(pd.DataFrame({"id": df.index[te], "split": split, "model": name,
                                             "label": y[te], "pred": p_te}))
            r = results["splits"][split][name]
            print(f"[{split}] {name:30s} val macro-F1 {r['val']['macro_f1']:.4f} | test macro-F1 "
                  f"{r['test']['macro_f1']:.4f} {r['test']['macro_f1_ci95']} ({r['fit_seconds']} s)")

    # best non-control baseline by validation macro-F1 on the main split
    candidates = ["logreg", "logreg_balanced", "rf", "rf_balanced"]
    best = max(candidates, key=lambda m: results["splits"]["split_main"][m]["val"]["macro_f1"])
    results["best_by_val_main"] = best
    (OUT / "results.json").write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
    pd.concat(predictions).to_parquet(OUT / "test_predictions.parquet", index=False)
    for split, tag in (("split_main", "주 분할"), ("split_random", "무작위 분할")):
        r = results["splits"][split][best]["test"]
        plot_confusion(np.array(r["confusion"]), f"{best} · {tag} test · 행 기준 비율(%) · macro-F1 {r['macro_f1']:.3f}",
                       OUT / f"confusion_{best}_{split}.png")
    print(f"[best by val] {best}; total {time.perf_counter() - t0:.0f} s; saved {OUT}")


if __name__ == "__main__":
    main()
