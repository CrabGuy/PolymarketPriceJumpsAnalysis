"""
Stage 13: descriptive counts for the report: trades, dollars and distinct markets per market and
calendar month, from the regrouped trades (tmp/buckets: event markets; tmp/buckets_cx: crypto
up/down markets). The categories are added locally from the tags.

Writes tmp/counts/<src>_<k>.parquet (market, month, trades, usd).
Usage: python s13_counts.py <bucket> [<bucket> ...]
Python 3.8 compatible (server).
"""
import glob
import os
import sys
import time

import pandas as pd

SRCS = {"events": "tmp/buckets", "cx": "tmp/buckets_cx"}
OUT = "tmp/counts"


def main(buckets):
    os.makedirs(OUT, exist_ok=True)
    for k in buckets:
        for name, src in SRCS.items():
            t0 = time.time()
            files = sorted(glob.glob(f"{src}/b{k:02d}_*.parquet"))
            if not files:
                continue
            d = pd.concat([pd.read_parquet(f, columns=["market", "ts", "usd"]) for f in files], ignore_index=True)
            d["month"] = pd.to_datetime(d.ts, unit="s").dt.strftime("%Y-%m")
            g = d.groupby(["market", "month"]).agg(trades=("ts", "size"), usd=("usd", "sum")).reset_index()
            g.to_parquet(f"{OUT}/{name}_{k:02d}.parquet", index=False)
            print(f"{name} bucket {k}: {len(d):,} trades, {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main([int(x) for x in sys.argv[1:]])
