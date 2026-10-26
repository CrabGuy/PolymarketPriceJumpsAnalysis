"""
Round 7, part 1: big moves in sports and esports markets over their whole life.

Input: local_data/r07/sports/ from remote/s7_events.py (mode "sports"): 15-min VWAP moves
with no 6 h pad, cut only after the price leaves [0.05, 0.95] for good.

Overshoot as in rounds 2-3 (outcome-based, ratio of sums), with a calibration baseline
per (category, 5-point price bin) from a 5% sample of random active bars.
Splits: by number of traders, by category (sports / esports) and by sport, at the close and
at the next trades. No live / pre-game split: the data has no kickoff times, and the end
date is not a reliable stand-in (round 8). Coverage: how many sports/esports markets have
big moves.

Outputs local_data/r07/sports_*.csv.
Usage: python explore/r07_sports.py
"""
import glob
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "explore")
from r02_persistence import category, outcomes, sigmoid  # noqa: E402
from r03_robustness import cat_baseline, overshoot_cat  # noqa: E402
from r05_siblings import boot_share, share  # noqa: E402

SRC = "local_data/r07/sports/"
OUT = "local_data/r07/"
SPORT = [("soccer", r"soccer|epl|premier-league|la-liga|serie-a|bundesliga|ligue-1|champions-league|mls|football-club"),
         ("basketball", r"nba|basketball|ncaab|wnba|euroleague"), ("american football", r"nfl|ncaaf|cfb"),
         ("baseball", r"mlb|baseball|kbo|npb"), ("hockey", r"nhl|hockey|khl"), ("tennis", r"tennis|atp|wta"),
         ("cricket", r"cricket|ipl"), ("combat", r"ufc|mma|boxing"),
         ("esports: counter-strike", r"counter-strike|cs2|csgo"), ("esports: league of legends", r"league-of-legends|lol"),
         ("esports: dota", r"dota"), ("esports: valorant", r"valorant")]
TGS = ("1", "2-3", "4+")


def load():
    e = pd.concat([pd.read_parquet(f) for f in glob.glob(SRC + "e*.parquet")], ignore_index=True)
    r = pd.concat([pd.read_parquet(f) for f in glob.glob(SRC + "r*.parquet")], ignore_index=True)
    cov = pd.concat([pd.read_parquet(f) for f in glob.glob(SRC + "m*.parquet")], ignore_index=True)
    tags = pd.read_csv("local_data/market_tags.csv", dtype=str)
    tags = tags[tags.market_id.astype(int).isin(cov.market)].drop_duplicates("market_id")
    idx = tags.market_id.astype(int).values
    cat = pd.Series(np.where(category(tags.tags).values == "esports", "esports", "sports"), index=idx)
    sport = pd.Series(category(tags.tags.str.lower(), SPORT).values, index=idx)
    out = outcomes()
    for x in (e, r, cov):
        x["cat"] = x.market.map(cat).fillna("sports")
        x["sport"] = x.market.map(sport).fillna("other")
    r["outcome"] = r.market.map(out)
    base = cat_baseline(r[r.outcome.notna()].rename(columns={"price": "vwap"}))
    e["outcome"] = e.market.map(out)
    e = e[e.outcome.notna()].copy()
    e["sgn"] = np.sign(e.move)
    L_pre = np.log(np.clip(e.y_pre, .01, .99) / (1 - np.clip(e.y_pre, .01, .99)))
    e["p_close"] = sigmoid(L_pre + e.move)
    e["absdp"] = (e.p_close - e.y_pre).abs()
    e["tg"] = pd.cut(e.takers, [0, 1, 3, np.inf], labels=list(TGS)).astype(str)
    e["oc"] = overshoot_cat(e, e.p_close, base)
    e["oe"] = np.where(e.entry_vwap.notna(), overshoot_cat(e, e.entry_vwap.fillna(0.5), base), np.nan)
    return e, cov


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
    e, cov = load()
    big = e[e.move.abs() >= 0.4].copy()
    print(f"sports/esports: {len(cov):,} markets with trades; with a big move: {(cov.moves_04 > 0).sum():,} "
          f"({(cov.moves_04 > 0).mean():.1%})")
    c = cov.groupby("cat").agg(markets=("market", "size"), with_spike=("moves_04", lambda x: (x > 0).mean()),
                               median_if_any=("moves_04", lambda x: x[x > 0].median()), big_moves=("moves_04", "sum"))
    print(c.round(3).to_string())
    c.to_csv(OUT + "sports_coverage.csv")
    print(f"\nbig moves with a clean outcome: {len(big):,} in {big.market.nunique():,} markets; "
          f"by cat {big.cat.value_counts().to_dict()}")

    res = {}
    res["all_tg"] = table(big, ["tg"])
    res["cat_tg"] = table(big, ["cat", "tg"])
    res["sport"] = table(big, ["sport"])
    for k, v in res.items():
        print(f"\n[{k}]")
        print(v.round(3).to_string(index=False))
        v.to_csv(OUT + f"sports_{k}.csv", index=False)
    print(f"\nall sports/esports big moves: overshoot {share(big, 'oc'):.3f}; next trades {share(big[big.oe.notna()], 'oe'):.3f}")


if __name__ == "__main__":
    main()
