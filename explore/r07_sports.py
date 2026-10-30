"""
Round 7 (updated round 9): price jumps in sports and esports markets.

Input: the main jumps (local_data/r03_big_moves_main.parquet and r03_tradable_main.parquet from
explore/r03_robustness.py): 30-min VWAP slots, jumps of 13 points or more, the first and last
5% of each market's life left out. Since round 9 the window scales with the market, so the
games keep their jumps and the separate whole-life run (remote/s7_events.py "sports") is no
longer used.

Overshoot as in F2 (category baseline, ratio of sums), at the close and at the next trades.
Splits: by number of traders, by category (sports / esports) and by sport. No live /
pre-game split: the data has no kickoff times, and the end date is not a reliable stand-in.

Outputs local_data/r07/sports_*.csv.
Usage: python explore/r07_sports.py
"""
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "explore")
from r02_persistence import category  # noqa: E402
from r05_siblings import boot_share, share  # noqa: E402

OUT = "local_data/r07/"
SPORT = [("soccer", r"soccer|epl|premier-league|la-liga|serie-a|bundesliga|ligue-1|champions-league|mls|football-club"),
         ("basketball", r"nba|basketball|ncaab|wnba|euroleague"), ("american football", r"nfl|ncaaf|cfb"),
         ("baseball", r"mlb|baseball|kbo|npb"), ("hockey", r"nhl|hockey|khl"), ("tennis", r"tennis|atp|wta"),
         ("cricket", r"cricket|ipl"), ("combat", r"ufc|mma|boxing"),
         ("esports: counter-strike", r"counter-strike|cs2|csgo"), ("esports: league of legends", r"league-of-legends|lol"),
         ("esports: dota", r"dota"), ("esports: valorant", r"valorant")]
TGS = ("1", "2-3", "4+")


def load():
    e = pd.read_parquet("local_data/r03_big_moves_main.parquet")
    e = e[e.cat.isin(["sports", "esports"])].copy()
    t = pd.read_parquet("local_data/r03_tradable_main.parquet", columns=["market", "t_close", "oe"])
    e = e.merge(t, on=["market", "t_close"], how="left")
    tags = pd.read_csv("local_data/market_tags.csv", dtype=str)
    tags = tags[tags.market_id.astype(int).isin(e.market)].drop_duplicates("market_id")
    e["sport"] = e.market.map(pd.Series(category(tags.tags.str.lower(), SPORT).values,
                                        index=tags.market_id.astype(int).values)).fillna("other")
    e["tg"] = e.tg.astype(str)
    return e


def table(e, by, col="oc"):
    rows = []
    for k, x in e.groupby(by, observed=True):
        if x.market.nunique() < 50:
            continue
        lo, hi = boot_share(x, col)
        k = k if isinstance(k, tuple) else (k,)
        rows.append(dict(zip(by, k), moves=len(x), markets=x.market.nunique(), overshoot=share(x, col), lo=lo, hi=hi,
                         next_trades=share(x[x.oe.notna()], "oe"), median_usd=x.usd.median(),
                         median_delay_s=x.entry_delay.median()))
    return pd.DataFrame(rows)


def main():
    big = load()
    print(f"sports/esports jumps with a clean outcome: {len(big):,} in {big.market.nunique():,} markets; "
          f"by cat {big.cat.value_counts().to_dict()}")
    res = {"all_tg": table(big, ["tg"]), "cat_tg": table(big, ["cat", "tg"]), "sport": table(big, ["sport"])}
    for k, v in res.items():
        print(f"\n[{k}]")
        print(v.round(3).to_string(index=False))
        v.to_csv(OUT + f"sports_{k}.csv", index=False)
    print(f"\nall sports/esports jumps: overshoot {share(big, 'oc'):.3f}; next trades {share(big[big.oe.notna()], 'oe'):.3f}")


if __name__ == "__main__":
    main()
