"""Diagnostic: how much do test numbers move with the split seed and with the twin-grouping rule?

Usage (from project root):
    .venv\\Scripts\\python scripts\\split_variance.py

For seeds 0-9, re-draws the main split (same cleaned data, same 70/15/15
StratifiedGroupKFold rule) under two grouping rules and scores the RF (class_weight)
baseline on each test part:
  - "twin"   : components from make_splits.twin_pairs (rule in use since checkpoint 3)
  - "plain10": components from same-orientation pairs within NEAR_PX dies (rule before)
Also counts twin pairs whose two labels differ, and, for the plain10 split, test
defect wafers whose twin sits in train under a different label.
Seed 0 / "twin" is the split actually used. Writes outputs/splits/split_seed_variance.json.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from baseline import models, scores, wafer_features
from explore_data import CLASSES, NEAR_PX, lot_components, value_counts
from make_splits import main_split, twin_pairs

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed" / "labeled_clean.pkl"
OUT = ROOT / "outputs" / "splits" / "split_seed_variance.json"
SEEDS = range(10)
K = len(CLASSES)


def summarize(runs: list[dict]) -> dict:
    f1 = np.array([r["test_macro_f1"] for r in runs])
    rec = {c: np.array([r["test_recall"][c] for r in runs]) for c in CLASSES}
    return {"macro_f1_mean_std_min_max": [round(float(f1.mean()), 4), round(float(f1.std(ddof=1)), 4),
                                          float(f1.min()), float(f1.max())],
            "recall_mean_std_min_max": {c: [round(float(v.mean()), 4), round(float(v.std(ddof=1)), 4),
                                            float(v.min()), float(v.max())] for c, v in rec.items()},
            "seeds_with_all_recall_ge_0.50": int(sum(min(r["test_recall"].values()) >= 0.5 for r in runs))}


def main():
    df = pd.read_pickle(PROCESSED)
    X = np.array([wafer_features(m) for m in df["waferMap"]], dtype=np.float32)
    y = df["label"].map({c: i for i, c in enumerate(CLASSES)}).to_numpy()

    pairs = twin_pairs(df)
    cross_lot = df.loc[pairs["a"], "lotName"].values != df.loc[pairs["b"], "lotName"].values
    plain = (pairs["transform"] == "identity").values & (pairs["px"] <= NEAR_PX).values
    components = {"twin": df["component"],
                  "plain10": lot_components(df, pairs[cross_lot & plain])}
    la, lb = df.loc[pairs["a"], "label"].values, df.loc[pairs["b"], "label"].values
    differ = la != lb
    out = {"source": "scripts/split_variance.py", "model": "rf_balanced", "seeds": list(SEEDS),
           "twin_pairs": len(pairs), "twin_pairs_label_differs": int(differ.sum()),
           "twin_pairs_label_differs_by_kind": {
               "plain_le_10px": int((differ & plain).sum()), "relative_or_transformed": int((differ & ~plain).sum())},
           "twin_label_disagreements": value_counts(pd.Series(
               ["/".join(sorted(p)) for p in zip(la[differ], lb[differ])], dtype=object))}

    for rule, comp in components.items():
        runs = []
        for seed in SEEDS:
            split = main_split(df.assign(component=comp), seed).to_numpy()
            tr, te = split == "train", split == "test"
            model = models()["rf_balanced"][0].fit(X[tr], y[tr])
            s = scores(np.bincount(y[te] * K + model.predict(X[te]), minlength=K * K).reshape(K, K))
            run = {"seed": seed, "test_macro_f1": round(float(s["macro_f1"]), 4),
                   "test_recall": {c: round(float(s["recall"][i]), 4) for i, c in enumerate(CLASSES)}}
            if rule == "plain10":  # test defect wafers whose twin is in train with another label
                sa, sb = split[df.index.get_indexer(pairs["a"])], split[df.index.get_indexer(pairs["b"])]
                test_side = np.where(sa == "test", pairs["a"], pairs["b"])
                crossing = differ & (((sa == "test") & (sb == "train")) | ((sa == "train") & (sb == "test")))
                hit = df.loc[np.unique(test_side[crossing])]
                run["test_wafers_with_other_label_twin_in_train"] = value_counts(hit["label"])
            runs.append(run)
            print(f"[{rule:7s} seed {seed}] macro-F1 {run['test_macro_f1']:.4f} Loc {run['test_recall']['Loc']:.3f} "
                  f"Scratch {run['test_recall']['Scratch']:.3f}", flush=True)
        out[rule] = {"runs": runs, **summarize(runs)}
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k not in ("twin", "plain10")}, ensure_ascii=False))
    for rule in components:
        print(rule, json.dumps({k: v for k, v in out[rule].items() if k != "runs"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
