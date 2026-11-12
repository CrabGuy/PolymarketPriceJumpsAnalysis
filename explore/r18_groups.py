"""
Overshoot at the slot's close by trader group (1 / 2-4 / 5+), within each category and
within each year: does the order "one trader > a few > a crowd" hold everywhere?

Input: local_data/r02_big_moves.parquet (explore/r02_persistence.py: the report's jumps with
their overshoot, category, year and trader group; frozen values, b(p) on every slot).
The overshoot is the report's ratio of sums; ranges are 95%, from 1,000 market resamples.

Writes local_data/r18_groups.csv (split, level, group, jumps, markets, overshoot, lo, hi), the
table behind the figure f2_categories (explore/report_figures.py, section 4.2 of the report).
Usage: python explore/r18_groups.py
"""
import sys

import pandas as pd

sys.path.insert(0, "explore")
from r02_persistence import TG_LABELS, share  # noqa: E402


def table(big):
    rows = []
    for split in ("cat", "year"):
        for level, x in big.groupby(split):
            for tg in ["all"] + TG_LABELS:
                y = x if tg == "all" else x[x.tg == tg]
                m, lo, hi = share(y)
                rows.append(dict(split=split, level=str(level), group=tg, jumps=len(y),
                                 markets=y.market.nunique(), overshoot=m * 100, lo=lo * 100, hi=hi * 100))
    return pd.DataFrame(rows)


def main():
    big = pd.read_parquet("local_data/r02_big_moves.parquet")
    t = table(big)
    t.to_csv("local_data/r18_groups.csv", index=False)
    pd.set_option("display.width", 200)
    print(t.round(1).to_string(index=False))


if __name__ == "__main__":
    main()
