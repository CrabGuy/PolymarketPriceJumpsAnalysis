"""
Stage 1: one pass over the trades file, regrouped into per-market buckets.

Reads a range of row groups, drops recurring up/down markets, flags book sweeps while all
fills of a transaction are still together (one taker, one transaction, one market, at
least 3 fills, YES range of at least 0.05), and writes compact rows to
tmp/buckets/b<k>_<start>.parquet, where k = market id mod N_BUCKETS.

Columns: market (int32), ts (int64 s), yes (float32), usd (float32), up (int8, +1 if the
taker pushed YES up), taker (uint64 hash), sweep (int8), fills (int16 = fills in the tx).

Usage: python s1_bucket.py <first_row_group> <last_row_group_exclusive>
Python 3.8 compatible (server).
"""
import os
import sys
import time

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

TRADES = "data/trades_final.parquet"
TAGS = "data/market_tags.csv"
OUT = "tmp/buckets"
N_BUCKETS = 32
FLUSH_ROWS = 400_000
COLS = ["market_id", "timestamp", "price", "usd_amount", "nonusdc_side",
        "taker_direction", "taker", "transaction_hash"]


def excluded_markets():
    t = pd.read_csv(TAGS, dtype=str)
    bad = t.tags.str.contains("recurring|up-or-down", na=False)
    return set(t.market_id[bad].astype(int))


def transform(df, skip):
    df = df[~df.market.isin(skip)]
    if df.empty:
        return df
    is_t1 = (df.nonusdc_side == "token1").values
    price = df.price.values
    yes = np.where(is_t1, price, 1 - price).astype("float32")
    buy = (df.taker_direction == "BUY").values
    up = np.where(is_t1 == buy, 1, -1).astype("int8")
    taker = pd.util.hash_array(df.taker.values.astype(object)).astype("uint64")
    out = pd.DataFrame({"market": df.market.values.astype("int32"),
                        "ts": df.timestamp.values.astype("int64"),
                        "yes": yes, "usd": df.usd_amount.values.astype("float32"),
                        "up": up, "taker": taker})
    key = [df.transaction_hash.values, out.taker.values, out.market.values]
    g = pd.DataFrame({"tx": key[0], "tk": key[1], "mk": key[2], "yes": yes})
    grp = g.groupby(["tx", "tk", "mk"], sort=False).yes
    fills = grp.transform("size").values
    rng = (grp.transform("max") - grp.transform("min")).values
    out["fills"] = np.minimum(fills, 32000).astype("int16")
    out["sweep"] = ((fills >= 3) & (rng >= 0.05)).astype("int8")
    return out


def main(a, b):
    os.makedirs(OUT, exist_ok=True)
    skip = excluded_markets()
    pf = pq.ParquetFile(TRADES)
    b = min(b, pf.metadata.num_row_groups)
    buf = {k: [] for k in range(N_BUCKETS)}
    nbuf = {k: 0 for k in range(N_BUCKETS)}
    writers = {}
    kept = total = 0
    t0 = time.time()

    def flush(k):
        if not buf[k]:
            return
        tb = pa.Table.from_pandas(pd.concat(buf[k], ignore_index=True), preserve_index=False)
        if k not in writers:
            writers[k] = pq.ParquetWriter(f"{OUT}/b{k:02d}_{a:05d}.parquet", tb.schema, compression="zstd")
        writers[k].write_table(tb)
        buf[k], nbuf[k] = [], 0

    for rg in range(a, b):
        df = pf.read_row_group(rg, columns=COLS).to_pandas()
        total += len(df)
        df["market"] = pd.to_numeric(df.market_id, errors="coerce").fillna(-1).astype("int64")
        out = transform(df, skip)
        kept += len(out)
        if len(out):
            bk = (out.market.values % N_BUCKETS)
            for k, part in out.groupby(bk, sort=False):
                buf[k].append(part)
                nbuf[k] += len(part)
                if nbuf[k] >= FLUSH_ROWS:
                    flush(k)
        if (rg - a) % 200 == 0:
            el = time.time() - t0
            print(f"rg {rg} ({rg - a + 1}/{b - a}) kept {kept:,}/{total:,} rows, {el:.0f}s", flush=True)
    for k in range(N_BUCKETS):
        flush(k)
    for w in writers.values():
        w.close()
    print(f"done rg {a}-{b}: kept {kept:,} of {total:,} rows in {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]), int(sys.argv[2]))
