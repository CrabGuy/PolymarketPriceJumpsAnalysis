"""
Report: extra descriptive numbers for report/REPORT.md (no new analysis, only counts and
shares on tables the rounds already produced).

  1. How many event markets have price jumps ("spikes"), overall and by category, and how
     the moves are spread across markets.
  2. Who makes them: share of price jumps by number of distinct takers, money in the bar.
  3. How often the next trades undo most of a move, by number of takers.
  4. Up/down crypto markets: how many big 1-minute moves and markets.

Inputs: local_data/r02_events (all moves, both price bases), local_data/r03_big_moves_main,
local_data/r03_tradable_main, local_data/r05/r05_ud_moves.parquet.
Output: printed tables, and local_data/report_stats.csv (category table).

Usage: python explore/report_stats.py
"""
import glob
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "explore")
from r02_persistence import MIN_PTS, category  # noqa: E402


def logit(p):
    p = np.clip(p, 0.01, 0.99)
    return np.log(p / (1 - p))


def main():
    # 1. price jumps per market (VWAP basis, >= 10 points, any resolution)
    cov = pd.concat([pd.read_parquet(f) for f in glob.glob("local_data/r02_events/m*.parquet")])
    e = pd.concat([pd.read_parquet(f, columns=["basis", "market", "y_pre", "move", "takers", "usd"])
                   for f in glob.glob("local_data/r02_events/e*.parquet")])
    e = e[e.basis == "vwap"]
    big = e[(1 / (1 + np.exp(-(logit(e.y_pre) + e.move))) - e.y_pre).abs() >= MIN_PTS]
    per = big.market.value_counts()
    tags = pd.read_csv("local_data/market_tags.csv", dtype=str)
    cat = pd.Series(category(tags.tags).values, index=tags.market_id.astype(int).values)
    cat = cat[~cat.index.duplicated()]
    cov["cat"] = cov.market.map(cat).fillna("other")
    cov["big"] = cov.market.map(per).fillna(0)
    print(f"markets with trades: {len(cov):,}; with >= 1 price jump: {(cov.big > 0).sum():,} "
          f"({(cov.big > 0).mean():.1%}); price jumps: {len(big):,}")
    print(f"price jumps per market with any: median {per.median():.0f}, mean {per.mean():.1f}, "
          f"90th pct {per.quantile(.9):.0f}; markets with 10+: {(per >= 10).sum():,}; "
          f"top 10% of these markets hold {per.sort_values(ascending=False).head(len(per) // 10).sum() / per.sum():.0%} of moves")
    cov["moves_per_100_bars"] = cov.big / cov.active_bars * 100
    tab = cov.groupby("cat").agg(markets=("market", "size"), with_spike=("big", lambda x: (x > 0).mean()),
                                 big_moves=("big", "sum"),
                                 median_if_any=("big", lambda x: x[x > 0].median()),
                                 per_100_active_bars=("moves_per_100_bars", "median"))
    tab = tab.sort_values("with_spike", ascending=False)
    print(tab.round(3).to_string())
    tab.to_csv("local_data/report_stats.csv")
    for lo, hi in [(100, 500), (500, 5000), (5000, np.inf)]:
        s = cov[(cov.trades >= lo) & (cov.trades < hi)]
        print(f"  markets with {lo}-{hi} trades: {len(s):,}, with a spike {(s.big > 0).mean():.1%}")

    # 2. who makes the price jumps (clean-outcome sample used for every finding)
    b = pd.read_parquet("local_data/r03_big_moves_main.parquet")
    print(f"\nanalysis sample: {len(b):,} price jumps in {b.market.nunique():,} markets")
    print("share by takers:", b.tg.value_counts(normalize=True).round(3).to_dict())
    print("median $ in the move's bar by takers:", b.groupby("tg", observed=True).usd.median().round(0).to_dict())
    print(f"median $ overall {b.usd.median():.0f}; share under $100 {(b.usd < 100).mean():.1%}; "
          f"share over $1k {(b.usd > 1000).mean():.1%}")
    print(f"median move size in probability points {b.absdp.median() * 100:.1f}; "
          f"up moves {(b.sgn > 0).mean():.1%}")
    print("single-trader moves made of one trade:", f"{((b.takers == 1) & (b.n == 1)).sum() / (b.takers == 1).sum():.1%}")

    # 3. how often the next trades undo most of the move
    t = pd.read_parquet("local_data/r03_tradable_main.parquet")
    t = t[t.entry_vwap.notna()].copy()
    t["kept"] = (logit(t.entry_vwap) - t.L_pre) / t.move
    t["undone_half"] = t.kept < 0.5
    t["undone_all"] = t.kept <= 0
    g = t.groupby("tg", observed=True).agg(moves=("kept", "size"), kept_median=("kept", "median"),
                                           more_than_half_undone=("undone_half", "mean"),
                                           fully_undone=("undone_all", "mean"),
                                           delay_median_s=("entry_delay", "median"))
    print("\nat the next trades (first 8 trades after the slot, within 1 h):")
    print(g.round(3).to_string())

    # 4. up/down
    try:
        u = pd.read_parquet("local_data/r05/r05_ud_moves.parquet")
        print(f"\nup/down: {len(u):,} big 1-min moves in {u.market.nunique():,} markets; "
              f"by coin {u.asset.value_counts().to_dict()}; by length {u.dur.value_counts().to_dict()}")
    except Exception as ex:  # optional
        print("up/down table not read:", ex)


if __name__ == "__main__":
    main()
