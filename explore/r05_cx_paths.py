"""
The crypto price paths at CX_POINTS points per market (section 5, F8 and F9).

remote/s4_paths.py cxfine writes each crypto up/down market's YES price at 120 evenly spaced
times over its window (copied to local_data/r12/cxfine/). This keeps every 120 / CX_POINTS-th
point (the last price of each of CX_POINTS equal parts of the window) and writes the same
layout with p0..p{CX_POINTS-1}. Read by r05_updown.py (whether a jump is matched in the related
markets) and r05_crypto_mp.py.

Input: local_data/r12/cxfine/cxfine_<k>.parquet. Output: local_data/r05/cx_paths/cx_<k>.parquet.
Usage: python explore/r05_cx_paths.py
"""
import glob
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "explore")
from r02_persistence import CX_POINTS  # noqa: E402

SRC = "local_data/r12/cxfine"
OUT = "local_data/r05/cx_paths"
FINE = 120                     # points per market in the cxfine paths


def main():
    os.makedirs(OUT, exist_ok=True)
    idx = np.arange(1, CX_POINTS + 1) * (FINE // CX_POINTS) - 1
    files = sorted(glob.glob(f"{SRC}/cxfine_*.parquet"))
    for f in files:
        p = pd.read_parquet(f)
        P = p[[f"p{i}" for i in range(FINE)]].values[:, idx].astype("float32")
        out = pd.DataFrame(P, columns=[f"p{i}" for i in range(CX_POINTS)])
        out.insert(0, "n_window", p["n_window"].values)
        out.insert(0, "dur_min", p["dur_min"].values)
        out.insert(0, "market", p["market"].values)
        k = os.path.basename(f)[len("cxfine_"):-len(".parquet")]
        out.to_parquet(f"{OUT}/cx_{k}.parquet", index=False)
    print(f"{len(files)} files -> {OUT}")


if __name__ == "__main__":
    main()
