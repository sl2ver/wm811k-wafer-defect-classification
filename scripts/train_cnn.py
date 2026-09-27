"""Stage 4: small CNN on 64x64 wafer maps.

Usage (from project root):
    .venv\\Scripts\\python scripts\\train_cnn.py --split main --loss ce
    .venv\\Scripts\\python scripts\\train_cnn.py --split main --loss weighted
    .venv\\Scripts\\python scripts\\train_cnn.py --split random --loss ce
    .venv\\Scripts\\python scripts\\train_cnn.py --split main --loss ce --shuffle-labels --epochs 5

Maps are resized anisotropically to 64x64 by block max (nearest when enlarging; a
cell stays defective if any source die in it is defective when shrinking), so the
elliptical maps become round and 1-die lines survive. Inputs: 2 channels (wafer,
defect). Training uses random flips / 90-degree rotations. The epoch with the best
validation macro-F1 is kept.

Each run writes outputs/cnn/<split>_<loss>[_shuffled]/: history.json, and (git-ignored)
probs.npz (val/test softmax) and model.pt.
"""
import argparse
import json
import os
import time
from pathlib import Path

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")  # deterministic cuBLAS

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import torch  # noqa: E402
import torch.nn as nn  # noqa: E402
import torch.nn.functional as F  # noqa: E402

from baseline import scores  # noqa: E402
from explore_data import CLASSES, SEED  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed" / "labeled_clean.pkl"
MAPS64 = ROOT / "data" / "processed" / "maps64.npy"
OUT = ROOT / "outputs" / "cnn"
SIZE = 64
BATCH = 256


def resize(m: np.ndarray, size: int = SIZE) -> np.ndarray:
    """Anisotropic resize by block max over the value order 0 (off) < 1 (good) < 2 (bad)."""
    h, w = m.shape
    rows, cols = np.arange(size) * h // size, np.arange(size) * w // size
    return np.maximum.reduceat(np.maximum.reduceat(m, rows, axis=0), cols, axis=1)


def load_maps(df: pd.DataFrame) -> np.ndarray:
    if MAPS64.exists():
        maps = np.load(MAPS64)
        if len(maps) == len(df):
            return maps
    maps = np.stack([resize(m) for m in df["waferMap"]]).astype(np.uint8)
    np.save(MAPS64, maps)
    return maps


class SmallCNN(nn.Module):
    def __init__(self, n_classes: int = len(CLASSES)):
        super().__init__()

        def block(cin, cout):
            return nn.Sequential(
                nn.Conv2d(cin, cout, 3, padding=1, bias=False), nn.BatchNorm2d(cout), nn.ReLU(inplace=True),
                nn.Conv2d(cout, cout, 3, padding=1, bias=False), nn.BatchNorm2d(cout), nn.ReLU(inplace=True),
                nn.MaxPool2d(2))

        self.features = nn.Sequential(block(2, 32), block(32, 64), block(64, 128), block(128, 128))
        self.head = nn.Sequential(nn.Dropout(0.3), nn.Linear(128, n_classes))

    def forward(self, x):
        return self.head(self.features(x).mean(dim=(2, 3)))  # global average pool (deterministic backward)


def to_input(batch_u8: torch.Tensor) -> torch.Tensor:
    return torch.stack([(batch_u8 > 0), (batch_u8 == 2)], dim=1).float()


def augment(x: torch.Tensor, gen: torch.Generator) -> torch.Tensor:
    """Random element of the 8 flips/rotations per sample."""
    k = torch.randint(0, 8, (len(x),), generator=gen, device=x.device)
    out = torch.empty_like(x)
    for t in range(8):
        sel = k == t
        if sel.any():
            v = torch.rot90(x[sel], t % 4, dims=(2, 3))
            out[sel] = torch.flip(v, dims=(3,)) if t >= 4 else v
    return out


@torch.no_grad()
def predict(model: nn.Module, maps: torch.Tensor) -> np.ndarray:
    model.eval()
    probs = [F.softmax(model(to_input(maps[i:i + 1024])), dim=1) for i in range(0, len(maps), 1024)]
    return torch.cat(probs).cpu().numpy()


def macro_f1(y: np.ndarray, p: np.ndarray) -> float:
    k = len(CLASSES)
    return float(scores(np.bincount(y * k + p, minlength=k * k).reshape(k, k))["macro_f1"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["main", "random"], default="main")
    ap.add_argument("--loss", choices=["ce", "weighted"], default="ce")
    ap.add_argument("--epochs", type=int, default=20)
    ap.add_argument("--patience", type=int, default=5)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--shuffle-labels", action="store_true")
    args = ap.parse_args()

    torch.manual_seed(SEED)
    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.benchmark = False
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    name = f"{args.split}_{args.loss}" + ("_shuffled" if args.shuffle_labels else "")
    out = OUT / name
    out.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    df = pd.read_pickle(PROCESSED)
    maps = load_maps(df)
    y = df["label"].map({c: i for i, c in enumerate(CLASSES)}).to_numpy()
    split = df[f"split_{args.split}"].to_numpy()
    idx = {s: np.flatnonzero(split == s) for s in ("train", "val", "test")}
    y_train = y[idx["train"]].copy()
    if args.shuffle_labels:
        y_train = np.random.default_rng(SEED).permutation(y_train)
    print(f"[data] {name}: maps {maps.shape} ready in {time.perf_counter() - t0:.0f} s; device {dev}")

    x = {s: torch.from_numpy(maps[i]).to(dev) for s, i in idx.items()}
    yt = torch.from_numpy(y_train).to(dev)
    counts = np.bincount(y_train, minlength=len(CLASSES))
    weight = torch.tensor(len(y_train) / (len(CLASSES) * np.maximum(counts, 1)), dtype=torch.float32, device=dev)
    criterion = nn.CrossEntropyLoss(weight=weight if args.loss == "weighted" else None)

    model = SmallCNN().to(dev)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    steps = args.epochs * -(-len(y_train) // BATCH)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=args.lr, total_steps=steps)
    gen = torch.Generator(device=dev).manual_seed(SEED)
    perm_rng = np.random.default_rng(SEED)

    history, best, best_f1, stale = [], None, -1.0, 0
    for epoch in range(1, args.epochs + 1):
        model.train()
        t1, total = time.perf_counter(), 0.0
        order = torch.from_numpy(perm_rng.permutation(len(y_train))).to(dev)
        for b in range(0, len(order), BATCH):
            sel = order[b:b + BATCH]
            loss = criterion(model(augment(to_input(x["train"][sel]), gen)), yt[sel])
            opt.zero_grad(set_to_none=True)
            loss.backward()
            opt.step()
            sched.step()
            total += loss.item() * len(sel)
        val_f1 = macro_f1(y[idx["val"]], predict(model, x["val"]).argmax(1))
        history.append({"epoch": epoch, "train_loss": round(total / len(y_train), 5), "val_macro_f1": round(val_f1, 4),
                        "seconds": round(time.perf_counter() - t1, 1)})
        print(f"[epoch {epoch:2d}] loss {history[-1]['train_loss']:.4f} val macro-F1 {val_f1:.4f} "
              f"({history[-1]['seconds']} s)", flush=True)
        if val_f1 > best_f1:
            best_f1, stale = val_f1, 0
            best = {k: v.detach().clone() for k, v in model.state_dict().items()}
        else:
            stale += 1
            if stale >= args.patience:
                break

    model.load_state_dict(best)
    torch.save(best, out / "model.pt")
    probs = {s: predict(model, x[s]) for s in ("val", "test")}
    np.savez_compressed(out / "probs.npz", val_ids=df.index[idx["val"]].to_numpy(), val=probs["val"],
                        test_ids=df.index[idx["test"]].to_numpy(), test=probs["test"])
    summary = {"source": "scripts/train_cnn.py", "run": name, "args": vars(args), "seed": SEED, "size": SIZE,
               "batch": BATCH, "params": sum(p.numel() for p in model.parameters()),
               "best_epoch": max(history, key=lambda h: h["val_macro_f1"])["epoch"], "best_val_macro_f1": round(best_f1, 4),
               "total_seconds": round(time.perf_counter() - t0, 1), "history": history}
    (out / "history.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(f"[done] {name}: best epoch {summary['best_epoch']} val macro-F1 {best_f1:.4f} total {summary['total_seconds']} s")


if __name__ == "__main__":
    main()
