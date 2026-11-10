"""
Price jumps with the next trades, how the overshoot fades over time, and whether the result
depends on how a jump is defined (sections 4.2-4.3 of the report).

Input: local_data/r03_events/<bar>/e*.parquet (remote/s3_events.py: jumps with the next-trades
price) and every slot with trades for b(p) (r02_persistence.calibration()).
  1  the main jumps (BAR slots, MIN_PTS) with their overshoot at the slot's close (oc)
  2  next trades: the VWAP of the first N_NEXT trades after the slot closes (within T_NEXT); the
     overshoot still in that price (oe)
  3  over time: the overshoot at the close, at the next trades, and 1 h, 6 h and 24 h later, on
     the jumps that have all of them, by trader group
  4  wallets behind single-trader jumps (how many distinct wallets)
  5  definition: slots of 5 / 30 / 60 minutes and thresholds of MIN_PTS -5 / 0 / +5 points
The same b(p) (category x price bin, every 30-minute slot) is used throughout.

Outputs local_data/r03_big_moves_main.parquet, r03_tradable_main.parquet, r03_curves_catbase.csv,
r03_robustness.csv, r03_cat_baseline.csv.
Usage: python explore/r03_robustness.py
"""
import glob
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "explore")
from r02_persistence import (BAR, CLIP, MIN_PTS, TG_EDGES, TG_LABELS, calibration, outcomes,  # noqa: E402
                             overshoot_cat, sigmoid, with_cat)

BARS = (300, BAR, 3600)
THRESHOLDS = (MIN_PTS - 0.05, MIN_PTS, MIN_PTS + 0.05)   # robustness check around the threshold
EV = "local_data/r03_events"


def load(bar):
    e = pd.concat([pd.read_parquet(f) for f in glob.glob(f"{EV}/{bar}/e*.parquet")], ignore_index=True)
    e["outcome"] = e.market.map(outcomes())
    e = with_cat(e[e.outcome.notna()].copy())
    e["year"] = pd.to_datetime(e.t_close, unit="s").dt.year
    e["L_pre"] = np.log(np.clip(e.y_pre, CLIP, 1 - CLIP) / (1 - np.clip(e.y_pre, CLIP, 1 - CLIP)))
    e["p_close"] = sigmoid(e.L_pre + e.move)
    e["absdp"] = (e.p_close - e.y_pre).abs()
    e["sgn"] = np.sign(e.move)
    e["tg"] = pd.cut(e.takers, TG_EDGES, labels=TG_LABELS)
    return e


def ratio(x, col):
    return x[col].sum() / x.absdp.sum()


def main():
    cb = calibration()
    e = load(BAR)
    big = e[e.absdp >= MIN_PTS].copy()
    big["oc"] = overshoot_cat(big, big.p_close, cb)
    print(f"[1] {len(big):,} jumps in {big.market.nunique():,} markets; overshoot {ratio(big, 'oc'):.4f}; by trader group",
          big.groupby("tg", observed=True).apply(lambda x: round(ratio(x, "oc"), 4)).to_dict())

    # 2. next trades
    t = big[big.entry_vwap.notna()].copy()
    t["oe"] = overshoot_cat(t, t.entry_vwap, cb)
    print(f"\n[2] jumps with next trades: {len(t):,} of {len(big):,}; median delay {t.entry_delay.median():.0f} s; "
          f"by trader group: " + str(t.groupby("tg", observed=True).entry_delay.median().to_dict()))

    # 3. over time, on the jumps with every horizon
    dyn = t.dropna(subset=["ret_1h", "ret_6h", "ret_24h"]).copy()
    cols = {"close": "oc", "next trades": "oe"}
    for h in ("1h", "6h", "24h"):
        dyn["oc_" + h] = overshoot_cat(dyn, sigmoid(dyn.L_pre + dyn["ret_" + h] * dyn.move), cb)
        cols[h] = "oc_" + h
    curve = dyn.groupby("tg", observed=True).apply(lambda x: pd.Series({k: ratio(x, v) for k, v in cols.items()}))
    curve.loc["all"] = {k: ratio(dyn, v) for k, v in cols.items()}
    curve["jumps"] = dyn.groupby("tg", observed=True).size().reindex(curve.index).fillna(len(dyn))
    curve["median delay s"] = dyn.groupby("tg", observed=True).entry_delay.median().reindex(curve.index)
    print(f"\n[3] overshoot over time ({len(dyn):,} jumps with every horizon):")
    print(curve.round(4).to_string())
    pd.concat({"tg": curve}).to_csv("local_data/r03_curves_catbase.csv")

    # 4. wallets
    w = big[(big.takers == 1) & (big.taker1 > 0)]
    print(f"\n[4] single-trader jumps: {len(w):,} by {w.taker1.nunique():,} wallets")

    # 5. definition
    rows = []
    for bar in BARS:
        eb = e if bar == BAR else load(bar)
        for thr in THRESHOLDS:
            x = eb[eb.absdp >= thr].copy()
            x["os"] = overshoot_cat(x, x.p_close, cb)
            r = {"bar_min": bar // 60, "threshold": round(thr, 2), "moves": len(x), "markets": x.market.nunique(),
                 "all": ratio(x, "os")}
            for tg, s in x.groupby("tg", observed=True):
                r[f"takers {tg}"] = ratio(s, "os")
            rows.append(r)
    rob = pd.DataFrame(rows)
    print("\n[5] overshoot by slot length and threshold:")
    print(rob.round(4).to_string(index=False))
    rob.to_csv("local_data/r03_robustness.csv", index=False)

    cb.rename("err").reset_index().astype({"bin": str}).to_csv("local_data/r03_cat_baseline.csv", index=False)
    big.to_parquet("local_data/r03_big_moves_main.parquet", index=False)
    t.to_parquet("local_data/r03_tradable_main.parquet", index=False)


if __name__ == "__main__":
    main()
