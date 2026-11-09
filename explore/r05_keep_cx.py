"""
The crypto up/down markets studied in section 5 (F8, F9): the list of market ids that
remote/s1x_bucket.py reads from tmp/keep_cx.txt.

Kept: markets tagged up-or-down that are
  - 15-minute markets (tag 15M) on bitcoin, ethereum, solana or xrp, or
  - 5-minute or 1-hour markets (tags 5M, 1H) on bitcoin or ethereum.
The asset and the length are read from the market tags.

Input: local_data/market_tags.csv. Output: local_data/r05/keep_cx.txt (one market id per line,
sorted), to be copied to tmp/keep_cx.txt next to the extraction scripts before s1x_bucket.py.
Usage: python explore/r05_keep_cx.py
"""
import os

import pandas as pd

TAGS = "local_data/market_tags.csv"
OUT = "local_data/r05/keep_cx.txt"
ASSETS_15M = ("bitcoin", "ethereum", "solana", "xrp")
ASSETS_SHORT_LONG = ("bitcoin", "ethereum")     # the 5-minute and 1-hour markets


def keep_ids(tags):
    u = tags[tags.tags.str.contains("up-or-down", na=False)]
    dur = u.tags.str.extract(r"(?:^|;)(5M|15M|1H|4h|daily)(?:;|$)", expand=False)
    asset = u.tags.str.extract(r"(?:^|;)(bitcoin|ethereum|solana|xrp)(?:;|$)", expand=False)
    keep = u[((dur == "15M") & asset.isin(ASSETS_15M)) | (dur.isin(["5M", "1H"]) & asset.isin(ASSETS_SHORT_LONG))]
    return sorted(set(keep.market_id.astype(int)))


def main():
    ids = keep_ids(pd.read_csv(TAGS, dtype=str))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        f.write("\n".join(map(str, ids)))
    print(f"crypto up/down markets: {len(ids):,} -> {OUT}")


if __name__ == "__main__":
    main()
