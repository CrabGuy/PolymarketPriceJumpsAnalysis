"""
Extract the full trade history (bucket rows) of a few markets, for the report's example plot.
Writes tmp/ex/<market>.parquet with the bucket columns (market, ts, yes, usd, up, taker hash,
fills, sweep).

Usage: python p7_extract.py <market_id> [<market_id> ...]
Python 3.8 compatible (server).
"""
import glob
import os
import sys

import pandas as pd

N_BUCKETS = 32


def main(ids):
    os.makedirs("tmp/ex", exist_ok=True)
    for m in ids:
        files = sorted(glob.glob(f"tmp/buckets/b{m % N_BUCKETS:02d}_*.parquet"))
        d = pd.concat([pd.read_parquet(f, filters=[("market", "==", m)]) for f in files], ignore_index=True)
        d = d.sort_values("ts").reset_index(drop=True)
        d.to_parquet(f"tmp/ex/{m}.parquet", index=False)
        print(f"market {m}: {len(d):,} trades", flush=True)


if __name__ == "__main__":
    main([int(x) for x in sys.argv[1:]])
