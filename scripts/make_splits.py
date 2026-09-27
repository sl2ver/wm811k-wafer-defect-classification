"""Stage 3a: clean the labeled wafers and build the main (group) and reference (random) splits.

Usage (from project root):
    .venv\\Scripts\\python scripts\\make_splits.py

Cleaning (decided at checkpoint 2): drop the 14 label-conflict groups, maps with
< 100 dies, then keep one map per exact-duplicate group. Main split: 70/15/15
over connected components of lots linked by cross-lot "twins", stratified by class.
Twins (rule tightened at checkpoint 3): two maps that, under any of the 8 flips /
rotations, differ in <= max(NEAR_PX, REL_PX * larger defect count) dies.
Reference split: wafer-level stratified random 70/15/15.

Writes data/processed/labeled_clean.pkl (not in git) and outputs/splits/split_summary.json.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedGroupKFold, train_test_split

from explore_data import CLASSES, NEAR_PX, SEED, load, lot_components, value_counts

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed" / "labeled_clean.pkl"
OUT = ROOT / "outputs" / "splits"
MIN_DIES = 100
REL_PX = 0.1  # retest twins: a few more failing dies on the same physical wafer
N_FOLDS = 20  # folds 0-2 -> test, 3-5 -> val, 6-19 -> train  (15/15/70)
SPLITS = ("train", "val", "test")
# transforms that keep an (h, w) map at (h, w), and those that turn a (w, h) map into (h, w)
SAME_SHAPE = {"identity": lambda m: m, "flip_ud": lambda m: m[:, ::-1, :], "flip_lr": lambda m: m[:, :, ::-1],
              "rot180": lambda m: m[:, ::-1, ::-1]}
SWAP_SHAPE = {"transpose": lambda m: m.transpose(0, 2, 1), "rot90": lambda m: np.rot90(m, 1, axes=(1, 2)),
              "rot270": lambda m: np.rot90(m, 3, axes=(1, 2)), "anti_transpose": lambda m: m[:, ::-1, ::-1].transpose(0, 2, 1)}


def onehot(maps: np.ndarray) -> np.ndarray:
    return np.concatenate([(maps == v).reshape(len(maps), -1) for v in (0, 1, 2)], axis=1).astype(np.float32)


def match(xa, nda, xb, ndb, hw: int, same: bool):
    """Index pairs (i of a, j of b) whose maps differ in <= max(NEAR_PX, REL_PX * larger defect count) dies."""
    ii_all, jj_all, px_all = [], [], []
    for s in range(0, len(xa), 2048):
        mismatch = hw - xa[s:s + 2048] @ xb.T
        limit = np.maximum(NEAR_PX, REL_PX * np.maximum.outer(nda[s:s + 2048], ndb))
        ii, jj = np.nonzero(mismatch <= limit + 0.5)
        px = np.rint(mismatch[ii, jj]).astype(int)
        ii = ii + s
        keep = ii != jj if same else np.ones(len(ii), bool)
        ii_all.append(ii[keep]), jj_all.append(jj[keep]), px_all.append(px[keep])
    return np.concatenate(ii_all), np.concatenate(jj_all), np.concatenate(px_all)


def twin_pairs(kept: pd.DataFrame) -> pd.DataFrame:
    """All twin pairs (a < b) over the 8 flips / rotations, keeping the closest transform per pair."""
    groups = {k: np.asarray(v) for k, v in kept.groupby(["h", "w"]).groups.items()}
    stack = lambda ids: np.stack(kept.loc[ids, "waferMap"].to_list())  # noqa: E731
    rows = []
    for (h, w), ids in groups.items():
        maps, nd = stack(ids), kept.loc[ids, "n_defect"].to_numpy(float)
        xa = onehot(maps)
        jobs = [(name, ids, nd, t(maps), True) for name, t in SAME_SHAPE.items()]
        if (w, h) in groups and (h, w) <= (w, h):  # each (h, w) / (w, h) pair once; square maps against themselves
            pids = groups[(w, h)]
            pmaps, pnd = stack(pids), kept.loc[pids, "n_defect"].to_numpy(float)
            jobs += [(name, pids, pnd, t(pmaps), h == w) for name, t in SWAP_SHAPE.items()]
        for name, bids, bnd, bmaps, same in jobs:
            ii, jj, px = match(xa, nd, onehot(np.ascontiguousarray(bmaps)), bnd, h * w, same)
            rows.append(pd.DataFrame({"a": ids[ii], "b": bids[jj], "px": px, "transform": name}))
    pairs = pd.concat(rows, ignore_index=True)
    pairs["a"], pairs["b"] = np.minimum(pairs["a"], pairs["b"]), np.maximum(pairs["a"], pairs["b"])
    return pairs.sort_values("px", kind="stable").drop_duplicates(["a", "b"]).reset_index(drop=True)


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


def main_split(kept: pd.DataFrame, seed: int = SEED) -> pd.Series:
    sgkf = StratifiedGroupKFold(n_splits=N_FOLDS, shuffle=True, random_state=seed)
    fold = np.empty(len(kept), dtype=int)
    for k, (_, te) in enumerate(sgkf.split(kept, kept["label"], groups=kept["component"])):
        fold[te] = k
    # SGKF places the largest, most class-skewed groups greedily into the same fold numbers
    # whatever the seed (shuffle only reorders ties), so draw which folds become test/val at random.
    fold = np.random.default_rng(seed).permutation(N_FOLDS)[fold]
    return pd.Series(np.select([fold < 3, fold < 6], ["test", "val"], "train"), index=kept.index)


def random_split(kept: pd.DataFrame) -> pd.Series:
    tr, rest = train_test_split(kept.index, test_size=0.3, stratify=kept["label"], random_state=SEED)
    va, te = train_test_split(rest, test_size=0.5, stratify=kept.loc[rest, "label"], random_state=SEED)
    return pd.Series("train", index=kept.index).mask(kept.index.isin(va), "val").mask(kept.index.isin(te), "test")


def leakage(kept: pd.DataFrame, split: pd.Series, pairs: pd.DataFrame) -> dict:
    sa, sb = split.loc[pairs["a"]].values, split.loc[pairs["b"]].values
    cross = sa != sb
    lots_multi = split.groupby(kept["lotName"]).nunique() > 1
    train_test = cross & (((sa == "train") & (sb == "test")) | ((sa == "test") & (sb == "train")))
    plain = (pairs["transform"].values == "identity") & (pairs["px"].values <= NEAR_PX)
    return {
        "twin_pairs_across_splits": int(cross.sum()),
        "twin_pairs_train_test": int(train_test.sum()),
        "plain_le_near_px_pairs_across_splits": int((cross & plain).sum()),
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
    pairs = twin_pairs(kept)
    cross_lot = kept.loc[pairs["a"], "lotName"].values != kept.loc[pairs["b"], "lotName"].values
    kept["component"] = lot_components(kept, pairs[cross_lot])
    comp_sizes = kept["component"].value_counts()
    kept["split_main"] = main_split(kept)
    kept["split_random"] = random_split(kept)

    s = {
        "source": "scripts/make_splits.py", "seed": SEED, "near_px": NEAR_PX, "rel_px": REL_PX,
        "min_dies": MIN_DIES, "cleaning": clean_log,
        "class_counts_kept": value_counts(kept["label"]),
        "twin_pairs_after_cleaning": {
            "total": len(pairs), "cross_lot": int(cross_lot.sum()), "exact": int((pairs["px"] == 0).sum()),
            "plain_le_near_px": int(((pairs["transform"] == "identity") & (pairs["px"] <= NEAR_PX)).sum()),
            "plain_relative_only": int(((pairs["transform"] == "identity") & (pairs["px"] > NEAR_PX)).sum()),
            "by_transform_not_identity": value_counts(pairs.loc[pairs["transform"] != "identity", "transform"]),
        },
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
