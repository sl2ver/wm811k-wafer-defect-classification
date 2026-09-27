"""Download WM-811K (LSWMD.pkl) from Kaggle and check that it loads.

Usage (from project root):
    .venv\\Scripts\\python scripts\\download_data.py

Skips the download if data/raw/LSWMD.pkl already exists; always re-checks
size, SHA-256 and DataFrame shape.
"""
import hashlib
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
PKL = RAW_DIR / "LSWMD.pkl"
HANDLE = "qingyi/wm811k-wafer-map"
EXPECTED_BYTES = 2_095_505_977  # Kaggle API file metadata (checked 2026-09-27)
EXPECTED_SHA256 = "1d04fccb3dd3176b276878b926b20fead7e077c5751e4d353ea9741a5e7b5c65"  # first download, 2026-09-27
EXPECTED_SHAPE = (811_457, 6)  # widely reported in literature; verified here

# Keep kagglehub's cache off C: (little free space there).
os.environ.setdefault("KAGGLEHUB_CACHE", str(ROOT / ".tmp" / "kagglehub"))

import kagglehub  # noqa: E402  (must come after KAGGLEHUB_CACHE is set)
import pandas as pd  # noqa: E402
import psutil  # noqa: E402


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 24), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ok = True
    if PKL.exists():
        print(f"[skip] {PKL} already exists")
    else:
        t0 = time.perf_counter()
        kagglehub.dataset_download(HANDLE, output_dir=str(RAW_DIR))
        print(f"[download] {HANDLE} -> {RAW_DIR} ({time.perf_counter() - t0:.1f} s)")

    size = PKL.stat().st_size
    print(f"[size] {size:,} B (expected {EXPECTED_BYTES:,}) {'OK' if size == EXPECTED_BYTES else 'MISMATCH'}")
    ok &= size == EXPECTED_BYTES
    digest = sha256(PKL)
    print(f"[sha256] {digest} {'OK' if digest == EXPECTED_SHA256 else 'MISMATCH'}")
    ok &= digest == EXPECTED_SHA256

    t0 = time.perf_counter()
    df = pd.read_pickle(PKL)
    load_s = time.perf_counter() - t0
    peak_gb = psutil.Process().memory_info().peak_wset / 1e9  # Windows peak working set
    print(f"[load] pandas {pd.__version__}, {load_s:.1f} s, peak RAM {peak_gb:.2f} GB")
    print(f"[shape] {df.shape} (expected {EXPECTED_SHAPE}) {'OK' if df.shape == EXPECTED_SHAPE else 'MISMATCH'}")
    ok &= df.shape == EXPECTED_SHAPE
    print("[columns]", {c: str(t) for c, t in df.dtypes.items()})
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
