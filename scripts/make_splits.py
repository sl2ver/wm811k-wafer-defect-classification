"""Stage 3a: clean the labeled wafers and build the main (group) and reference (random) splits.

Usage (from project root):
    .venv\\Scripts\\python scripts\\make_splits.py

Cleaning (decided at checkpoint 2): drop the 14 label-conflict groups, maps with
< 100 dies, then keep one map per exact-duplicate group. Main split: 70/15/15
over connected components of lots linked by cross-lot near-copies (<= NEAR_PX),
stratified by class. Reference split: wafer-level stratified random 70/15/15.

Writes data/processed/labeled_clean.pkl (not in git) and outputs/splits/split_summary.json.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedGroupKFold, train_test_split

from explore_data import CLASSES, NEAR_PX, SEED, load, lot_components, near_duplicate_pairs, value_counts

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed" / "labeled_clean.pkl"
OUT = ROOT / "outputs" / "splits"
MIN_DIES = 100
N_FOLDS = 20  # folds 0-2 -> test, 3-5 -> val, 6-19 -> train  (15/15/70)
SPLITS = ("train", "val", "test")


def clean(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    lab = df[df["label"].notna()]
    conflict = lab.groupby("hash")["label"].transform("nunique") > 1
    step1 = lab[~conflict]
    degenerate = step1["n_die"] < MIN_DIES
    step2 = step1[~degenerate]
    duplicate = step2["hash"].duplicated(keep="first")
    kept = step2[~duplicate].copy()
    log = {
        "labeled": len(lab), "removed_label_conflict_rows": int(conflict.sum()),
        "removed_lt100_die_rows": int(degenerate.sum()), "removed_duplicate_rows": int(duplicate.sum()),
        "kept": len(kept),
    }
    return kept, log


def main_split(kept: pd.DataFrame) -> pd.Series:
    sgkf = StratifiedGroupKFold(n_splits=N_FOLDS, shuffle=True, random_state=SEED)
    fold = np.empty(len(kept), dtype=int)
    for k, (_, te) in enumerate(sgkf.split(kept, kept["label"], groups=kept["component"])):
        fold[te] = k
    return pd.Series(np.select([fold < 3, fold < 6], ["test", "val"], "train"), index=kept.index)


def random_split(kept: pd.DataFrame) -> pd.Series:
    tr, rest = train_test_split(kept.index, test_size=0.3, stratify=kept["label"], random_state=SEED)
    va, te = train_test_split(rest, test_size=0.5, stratify=kept.loc[rest, "label"], random_state=SEED)
    return pd.Series("train", index=kept.index).mask(kept.index.isin(va), "val").mask(kept.index.isin(te), "test")


def leakage(kept: pd.DataFrame, split: pd.Series, pairs: pd.DataFrame) -> dict:
    sa, sb = split.loc[pairs["a"]].values, split.loc[pairs["b"]].values
    cross = sa != sb
    lots_multi = split.groupby(kept["lotName"]).nunique() > 1
    return {
        "near_copy_pairs_across_splits": int(cross.sum()),
        "near_copy_pairs_train_test": int((cross & (((sa == "train") & (sb == "test")) | ((sa == "test") & (sb == "train")))).sum()),
        "exact_pairs_across_splits": int((cross & (pairs["px"].values == 0)).sum()),
        "lots_in_more_than_one_split": int(lots_multi.sum()),
    }


def describe(kept: pd.DataFrame, split: pd.Series) -> dict:
    return {
        "rows": {s: int((split == s).sum()) for s in SPLITS},
        "share": {s: round(float((split == s).mean()), 4) for s in SPLITS},
        "class_counts": {s: {c: int(((split == s) & (kept["label"] == c)).sum()) for c in CLASSES} for s in SPLITS},
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    PROCESSED.parent.mkdir(parents=True, exist_ok=True)
    df = load()
    kept, clean_log = clean(df)
    pairs = near_duplicate_pairs(kept)
    cross_lot = kept.loc[pairs["a"], "lotName"].values != kept.loc[pairs["b"], "lotName"].values
    kept["component"] = lot_components(kept, pairs[cross_lot])
    comp_sizes = kept["component"].value_counts()
    kept["split_main"] = main_split(kept)
    kept["split_random"] = random_split(kept)

    s = {
        "source": "scripts/make_splits.py", "seed": SEED, "near_px": NEAR_PX, "min_dies": MIN_DIES,
        "cleaning": clean_log,
        "class_counts_kept": value_counts(kept["label"]),
        "near_copy_pairs_after_cleaning": len(pairs), "exact_pairs_after_cleaning": int((pairs["px"] == 0).sum()),
        "components": {"count": int(comp_sizes.size), "largest": int(comp_sizes.iloc[0]),
                       "largest_share": round(float(comp_sizes.iloc[0] / len(kept)), 4),
                       "multi_lot": int((kept.groupby("component")["lotName"].nunique() > 1).sum())},
        "main": {**describe(kept, kept["split_main"]), "leakage": leakage(kept, kept["split_main"], pairs)},
        "random": {**describe(kept, kept["split_random"]), "leakage": leakage(kept, kept["split_random"], pairs)},
    }
    (OUT / "split_summary.json").write_text(json.dumps(s, indent=2, ensure_ascii=False), encoding="utf-8")
    cols = ["waferMap", "label", "lotName", "waferIndex", "h", "w", "n_die", "n_defect", "hash", "component",
            "split_main", "split_random"]
    kept[cols].to_pickle(PROCESSED, protocol=5)
    print(json.dumps(s, indent=1, ensure_ascii=False))
    print(f"[saved] {PROCESSED} ({PROCESSED.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
