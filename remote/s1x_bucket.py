"""
Stage 1 for the full crypto up/down set: every bitcoin, ethereum, solana and xrp 15-minute
market, plus every bitcoin and ethereum 5-minute and 1-hour market (the market ids are listed
in tmp/keep_cx.txt). Same columns and sweep flags as s1_bucket.py (whose code is reused),
written to tmp/buckets_cx. Only row groups whose newest trade is after FROM_TS are read
(these markets start in June 2025).

Usage: python s1x_bucket.py <first_row_group> <last_row_group_exclusive>
       python s1x_bucket.py first        (prints the first row group to read)
       python s1x_bucket.py auto         (reads from that row group to the end)
Python 3.8 compatible (server).
"""
import sys

import pyarrow.parquet as pq

import s1_bucket as s1

FROM_TS = 1748736000          # 2025-06-01 00:00 UTC
s1.OUT = "tmp/buckets_cx"
KEEP = {int(x) for x in open("tmp/keep_cx.txt").read().split()}
_transform = s1.transform
s1.transform = lambda df, skip: _transform(df[df.market.isin(KEEP)], set())
s1.excluded_markets = lambda: set()


def first_row_group():
    md = pq.ParquetFile(s1.TRADES).metadata
    col = [md.row_group(0).column(j).path_in_schema for j in range(md.num_columns)].index("timestamp")
    for rg in range(md.num_row_groups):
        st = md.row_group(rg).column(col).statistics
        if st is not None and st.has_min_max and st.max >= FROM_TS:
            return rg, md.num_row_groups
    return md.num_row_groups, md.num_row_groups


if __name__ == "__main__":
    if sys.argv[1] in ("first", "auto"):
        a, b = first_row_group()
        print("first row group, total:", a, b, flush=True)
        if sys.argv[1] == "auto":
            print(f"crypto up/down markets: {len(KEEP):,}", flush=True)
            s1.main(a, b)
    else:
        print(f"crypto up/down markets: {len(KEEP):,}", flush=True)
        s1.main(int(sys.argv[1]), int(sys.argv[2]))
