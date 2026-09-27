"""Run the whole pipeline in order (about 4-5 hours on a Quadro P2000; CNN training dominates).

Usage (from project root):
    .venv\\Scripts\\python scripts\\run_all.py

Steps: download + check data -> exploration -> cleaning and splits -> baselines ->
split-seed diagnostic -> CNN runs (main CE, main weighted CE, random-split CE,
shuffled-label control) -> evaluation. Stops at the first failing step.
"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STEPS = [
    ["download_data.py"],
    ["explore_data.py"],
    ["make_splits.py"],
    ["baseline.py"],
    ["split_variance.py"],
    ["train_cnn.py", "--split", "main", "--loss", "ce"],
    ["train_cnn.py", "--split", "main", "--loss", "weighted"],
    ["train_cnn.py", "--split", "random", "--loss", "ce"],
    ["train_cnn.py", "--split", "main", "--loss", "ce", "--shuffle-labels", "--epochs", "5"],
    ["evaluate_cnn.py"],
]


def main():
    t0 = time.perf_counter()
    for step in STEPS:
        t1 = time.perf_counter()
        print(f"\n=== {' '.join(step)}", flush=True)
        subprocess.run([sys.executable, str(ROOT / "scripts" / step[0]), *step[1:]], cwd=ROOT, check=True)
        print(f"=== done in {time.perf_counter() - t1:.0f} s", flush=True)
    print(f"\nall steps done in {(time.perf_counter() - t0) / 60:.0f} min")


if __name__ == "__main__":
    main()
