"""
Stage 1 for recurring up/down markets: a random 10% sample (market id mod 10 == 0) of the
markets tagged up-or-down, plus all bitcoin 15-minute up/down markets (a continuous
series for matrix profiles), regrouped into tmp/buckets_ud with the same columns and sweep
flags as s1_bucket.py (whose code is reused).

Usage: python s1u_bucket.py <first_row_group> <last_row_group_exclusive>
Python 3.8 compatible (server).
"""
import sys

import pandas as pd

import s1_bucket as s1

s1.OUT = "tmp/buckets_ud"
_t = pd.read_csv(s1.TAGS, dtype=str)
_ud = _t[_t.tags.str.contains("up-or-down", na=False)]
KEEP = {m for m in _ud.market_id.astype(int) if m % 10 == 0}
# plus every bitcoin 15-minute market, so they form one continuous series in time
_btc15 = _ud.tags.str.contains(r"(?:^|;)bitcoin(?:;|$)") & _ud.tags.str.contains(r"(?:^|;)15M(?:;|$)")
KEEP |= set(_ud.market_id[_btc15].astype(int))
_transform = s1.transform
s1.transform = lambda df, skip: _transform(df[df.market.isin(KEEP)], set())
s1.excluded_markets = lambda: set()

if __name__ == "__main__":
    print(f"sampled up/down markets: {len(KEEP):,}", flush=True)
    s1.main(int(sys.argv[1]), int(sys.argv[2]))
