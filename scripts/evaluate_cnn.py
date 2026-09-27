"""Stage 4b: evaluate the CNN runs (raw argmax and val-calibrated) against the baselines.

Usage (from project root):
    .venv\\Scripts\\python scripts\\evaluate_cnn.py

Calibration: per-class additive biases on the log-probabilities, fitted on the
validation split only (coordinate ascent, 'none' fixed at 0). Objective: highest
validation macro-F1 among bias settings whose validation recall is >= VAL_RECALL_FLOOR
for every class (the 0.50 success floor plus a 0.10 margin for val-to-test variance).

Final model = the main-split run/variant with the highest validation macro-F1 among
those whose every-class validation recall is >= 0.50. Test is read for all runs but
never used for any choice.

Reads outputs/cnn/*/probs.npz, data/processed/labeled_clean.pkl, outputs/baseline/results.json.
Writes outputs/cnn/results.json, figures, and (git-ignored) outputs/cnn/test_predictions.parquet.
"""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from baseline import evaluate, plot_confusion, scores  # noqa: E402
from explore_data import CLASSES, GRID, INK, INK2, SEED, SERIES, SERIES2, draw_map, wafer_legend  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed" / "labeled_clean.pkl"
CNN = ROOT / "outputs" / "cnn"
BASELINE = ROOT / "outputs" / "baseline" / "results.json"
VAL_RECALL_FLOOR = 0.60
SUCCESS_RECALL_FLOOR = 0.50
BIAS_GRID = np.linspace(-4, 4, 33)
NONE = CLASSES.index("none")
K = len(CLASSES)


def confusion(y: np.ndarray, p: np.ndarray) -> np.ndarray:
    return np.bincount(y * K + p, minlength=K * K).reshape(K, K)


def calibrate(logp: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, float]:
    def objective(b):
        s = scores(confusion(y, (logp + b).argmax(1)))
        return s["macro_f1"] if s["recall"].min() >= VAL_RECALL_FLOOR else s["recall"].min() - 1.0

    bias, best = np.zeros(K), objective(np.zeros(K))
    for _ in range(3):
        for c in [c for c in range(K) if c != NONE]:
            for v in BIAS_GRID:
                trial = bias.copy()
                trial[c] = v
                o = objective(trial)
                if o > best + 1e-12:
                    best, bias = o, trial
    return bias, best


def plot_recall(base: dict, final: dict, base_name: str, final_name: str, path: Path):
    y = np.arange(K)[::-1]
    fig, ax = plt.subplots(figsize=(8.6, 5.2))
    for off, (res, color, label) in zip((0.18, -0.18), ((base, SERIES2, base_name), (final, SERIES, final_name))):
        r = np.array([res["per_class"][c]["recall"] for c in CLASSES])
        lo = np.array([res["per_class"][c]["recall_ci95"][0] for c in CLASSES])
        hi = np.array([res["per_class"][c]["recall_ci95"][1] for c in CLASSES])
        ax.barh(y + off, r, height=0.34, color=color, label=label)
        ax.errorbar(r, y + off, xerr=[r - lo, hi - r], fmt="none", ecolor=INK2, elinewidth=0.8, capsize=2)
    ax.axvline(SUCCESS_RECALL_FLOOR, color=INK2, linewidth=1)
    ax.text(SUCCESS_RECALL_FLOOR, K - 0.35, " 성공 기준 0.50", color=INK2, fontsize=8.5, va="bottom")
    ax.set_yticks(y, [f"{c} ({final['per_class'][c]['support']:,})" for c in CLASSES])
    ax.set_xlim(0, 1.02)
    ax.set_xlabel("recall (주 분할 test, 막대 끝 선 = 성분 부트스트랩 95 % 신뢰구간)", color=INK2)
    ax.set_title("클래스별 recall: 베이스라인 대 최종 CNN", loc="left", fontsize=11, color=INK)
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.13), ncol=2, fontsize=9)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.tick_params(length=0)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_errors(df: pd.DataFrame, pred: pd.DataFrame, path: Path, n_pairs: int = 6, per_pair: int = 8):
    wrong = pred[pred["label"] != pred["pred"]]
    pairs = wrong.groupby(["label", "pred"]).size().sort_values(ascending=False).head(n_pairs)
    rng = np.random.default_rng(SEED)
    fig, axes = plt.subplots(len(pairs), per_pair, figsize=(per_pair * 1.25 + 2.0, len(pairs) * 1.45 + 0.8))
    for r, ((t, p), n) in enumerate(pairs.items()):
        ids = wrong.loc[(wrong["label"] == t) & (wrong["pred"] == p), "id"].to_numpy()
        pick = sorted(rng.choice(ids, min(per_pair, len(ids)), replace=False))
        for k in range(per_pair):
            ax = axes[r, k]
            if k < len(pick):
                draw_map(ax, df.at[pick[k], "waferMap"], str(pick[k]))
            else:
                ax.axis("off")
        axes[r, 0].set_ylabel(f"정답 {CLASSES[t]}\n→ 예측 {CLASSES[p]}\n({n}장)", rotation=0, ha="right", va="center",
                              fontsize=8.5, color=INK, labelpad=8)
    fig.suptitle(f"최종 CNN의 가장 잦은 오분류 {len(pairs)}쌍 (주 분할 test, 쌍마다 무작위 {per_pair}장, seed {SEED})",
                 y=0.995, fontsize=10.5)
    wafer_legend(fig, 0.97)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main():
    df = pd.read_pickle(PROCESSED)
    y_all = df["label"].map({c: i for i, c in enumerate(CLASSES)})
    base = json.loads(BASELINE.read_text(encoding="utf-8"))
    rng = np.random.default_rng(SEED)
    results, preds = {"source": "scripts/evaluate_cnn.py", "val_recall_floor": VAL_RECALL_FLOOR, "runs": {}}, []

    for run_dir in sorted(p for p in CNN.iterdir() if (p / "probs.npz").exists()):
        z = np.load(run_dir / "probs.npz")
        logp = {s: np.log(np.clip(z[s], 1e-12, 1)) for s in ("val", "test")}
        ids = {s: z[f"{s}_ids"] for s in ("val", "test")}
        y = {s: y_all.loc[ids[s]].to_numpy() for s in ("val", "test")}
        groups = {s: df.loc[ids[s], "component"].to_numpy() for s in ("val", "test")}
        bias, _ = calibrate(logp["val"], y["val"])
        run = {"history": json.loads((run_dir / "history.json").read_text(encoding="utf-8"))["history"],
               "calibration_bias": dict(zip(CLASSES, np.round(bias, 3).tolist()))}
        for variant, b in (("raw", np.zeros(K)), ("calibrated", bias)):
            p = {s: (logp[s] + b).argmax(1) for s in ("val", "test")}
            run[variant] = {s: evaluate(y[s], p[s], groups[s], rng) for s in ("val", "test")}
            adj = np.exp(logp["test"] + b)
            adj /= adj.sum(1, keepdims=True)  # probabilities consistent with this variant's prediction
            preds.append(pd.DataFrame({"run": run_dir.name, "variant": variant, "id": ids["test"], "label": y["test"],
                                       "pred": p["test"], **{f"p_{c}": adj[:, i] for i, c in enumerate(CLASSES)}}))
        results["runs"][run_dir.name] = run
        for variant in ("raw", "calibrated"):
            v, t = run[variant]["val"], run[variant]["test"]
            print(f"[{run_dir.name:22s} {variant:10s}] val macro-F1 {v['macro_f1']:.4f} min recall "
                  f"{min(x['recall'] for x in v['per_class'].values()):.3f} | test macro-F1 {t['macro_f1']:.4f} "
                  f"{t['macro_f1_ci95']} min recall {min(x['recall'] for x in t['per_class'].values()):.3f}")

    # final model: chosen on validation only, among main-split, non-shuffled runs
    candidates = [(name, variant) for name, run in results["runs"].items()
                  if name.startswith("main_") and not name.endswith("_shuffled") for variant in ("raw", "calibrated")
                  if min(x["recall"] for x in run[variant]["val"]["per_class"].values()) >= SUCCESS_RECALL_FLOOR]
    if not candidates:
        candidates = [(n, v) for n in results["runs"] if n.startswith("main_") and not n.endswith("_shuffled")
                      for v in ("raw", "calibrated")]
    final = max(candidates, key=lambda nv: results["runs"][nv[0]][nv[1]]["val"]["macro_f1"])
    ft = results["runs"][final[0]][final[1]]["test"]

    base_main = base["splits"]["split_main"]
    base_best = max(["logreg", "logreg_balanced", "rf", "rf_balanced"], key=lambda m: base_main[m]["test"]["macro_f1"])
    bt = base_main[base_best]["test"]
    results["final"] = {"run": final[0], "variant": final[1], "test": ft}
    results["baseline_bar"] = {"model": base_best, "test_macro_f1": bt["macro_f1"], "test_macro_f1_ci95": bt["macro_f1_ci95"]}
    results["success"] = {
        "macro_f1_ge_0.80": ft["macro_f1"] >= 0.80,
        "all_recall_ge_0.50": all(x["recall"] >= SUCCESS_RECALL_FLOOR for x in ft["per_class"].values()),
        "beats_best_baseline": ft["macro_f1"] > bt["macro_f1"],
        "ci_overlaps_best_baseline": ft["macro_f1_ci95"][0] <= bt["macro_f1_ci95"][1],
    }
    random_name = final[0].replace("main_", "random_", 1)
    if random_name in results["runs"]:
        rt = results["runs"][random_name][final[1]]["test"]
        results["leakage_gap"] = {"random_run": random_name, "random_test_macro_f1": rt["macro_f1"],
                                  "main_test_macro_f1": ft["macro_f1"], "gap": round(rt["macro_f1"] - ft["macro_f1"], 4)}
    (CNN / "results.json").write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
    pred = pd.concat(preds, ignore_index=True)
    pred.to_parquet(CNN / "test_predictions.parquet", index=False)

    final_pred = pred[(pred["run"] == final[0]) & (pred["variant"] == final[1])]
    plot_confusion(np.array(ft["confusion"]), f"최종 CNN ({final[0]}, {final[1]}) · 주 분할 test · 행 기준 %"
                   f" · macro-F1 {ft['macro_f1']:.3f}", CNN / "confusion_final.png")
    plot_recall(bt, ft, f"베이스라인 {base_best} (test 최고)", f"최종 CNN ({final[0]}, {final[1]})",
                CNN / "recall_final_vs_baseline.png")
    plot_errors(df, final_pred, CNN / "errors_final.png")
    print(json.dumps({k: results[k] for k in ("baseline_bar", "success")}, ensure_ascii=False))
    print(f"[final] {final}; test macro-F1 {ft['macro_f1']:.4f} {ft['macro_f1_ci95']}; "
          f"leakage gap {results.get('leakage_gap')}")


if __name__ == "__main__":
    main()
