"""Intervention: do the models use the 25x27 outline (515 vs 516 dies) as a Center shortcut?

Usage (from project root):
    .venv\\Scripts\\python scripts\\outline_intervention.py

In the 25x27 product almost every Center wafer uses one die outline (515 dies) and
almost every 'none' wafer another (516 dies); the two outlines differ in 19 edge cells.
Every TEST wafer of this product on either outline gets the other outline (removed
cells -> off-wafer, added cells -> good die), and the final CNN's and the RF baseline's
predictions are compared before and after. Writes outputs/cnn/outline_intervention.json.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from baseline import models, wafer_features
from explore_data import CLASSES, SEED
from train_cnn import SmallCNN, resize, to_input

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed" / "labeled_clean.pkl"
CNN_DIR = ROOT / "outputs" / "cnn"
OUT = CNN_DIR / "outline_intervention.json"
OUTLINES = (515, 516)


def swap(m: np.ndarray, target: np.ndarray) -> np.ndarray:
    out = m.copy()
    out[~target] = 0
    out[target & (m == 0)] = 1
    return out


def cnn_predict(maps: list, final: dict, bias: np.ndarray) -> np.ndarray:
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = SmallCNN().to(dev)
    model.load_state_dict(torch.load(CNN_DIR / final["run"] / "model.pt", map_location=dev))
    model.eval()
    x = torch.from_numpy(np.stack([resize(m) for m in maps])).to(dev)
    with torch.no_grad():
        logp = torch.cat([torch.log_softmax(model(to_input(x[i:i + 1024])), 1) for i in range(0, len(x), 1024)])
    return (logp.cpu().numpy() + (bias if final["variant"] == "calibrated" else 0)).argmax(1)


def main():
    torch.manual_seed(SEED)
    df = pd.read_pickle(PROCESSED)
    results = json.loads((CNN_DIR / "results.json").read_text(encoding="utf-8"))
    final = results["final"]
    bias = np.array([results["runs"][final["run"]]["calibration_bias"][c] for c in CLASSES])

    product = df[(df["h"] == 25) & (df["w"] == 27)]
    masks = {n: product.loc[product["n_die"] == n, "waferMap"].iloc[0] > 0 for n in OUTLINES}
    test = product[(product["split_main"] == "test") & product["n_die"].isin(OUTLINES)]
    swapped = [swap(m, masks[OUTLINES[1] if n == OUTLINES[0] else OUTLINES[0]])
               for m, n in zip(test["waferMap"], test["n_die"])]
    assert all(int((s > 0).sum()) == (OUTLINES[1] if n == OUTLINES[0] else OUTLINES[0])
               for s, n in zip(swapped, test["n_die"]))

    pred = {"cnn": (cnn_predict(list(test["waferMap"]), final, bias), cnn_predict(swapped, final, bias))}
    train = df[df["split_main"] == "train"]
    rf = models()["rf_balanced"][0].fit(np.array([wafer_features(m) for m in train["waferMap"]], dtype=np.float32),
                                        train["label"].map({c: i for i, c in enumerate(CLASSES)}).to_numpy())
    pred["rf"] = tuple(rf.predict(np.array([wafer_features(m) for m in maps], dtype=np.float32))
                       for maps in (list(test["waferMap"]), swapped))

    center = CLASSES.index("Center")
    out = {"source": "scripts/outline_intervention.py", "final_model": {k: final[k] for k in ("run", "variant")},
           "outline_cells_differing": int((masks[OUTLINES[0]] != masks[OUTLINES[1]]).sum()), "groups": {}}
    for (n, label), idx in test.groupby(["n_die", "label"]).indices.items():
        if label not in ("Center", "none") or len(idx) < 5:
            continue
        key = f"{label} on {n}-die outline -> {OUTLINES[1] if n == OUTLINES[0] else OUTLINES[0]}"
        out["groups"][key] = {"n": len(idx), **{
            model: {"pred_center_before": round(float((b[idx] == center).mean()), 4),
                    "pred_center_after": round(float((a[idx] == center).mean()), 4),
                    "pred_unchanged": round(float((b[idx] == a[idx]).mean()), 4),
                    "after_counts": {CLASSES[k]: int(v) for k, v in zip(*np.unique(a[idx], return_counts=True))}}
            for model, (b, a) in pred.items()}}
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
