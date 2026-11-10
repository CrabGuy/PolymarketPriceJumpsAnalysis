"""
Betting against price jumps (section 4.5 of the report): buy the other side right after the
slot closes, at a price that was actually paid, and hold to resolution.

Input: local_data/r03_tradable_main.parquet (jumps with next trades, explore/r03_robustness.py)
and local_data/r06/micro/x*.parquet (remote/s6_micro.py: side-specific prices after each jump).
Entry price ("taker"): the VWAP of the next N_NEXT trades on the bettor's side (after an up jump,
trades whose taker sold YES), i.e. what a bettor crossing the spread paid. Return per $1 staked
= sgn * (p - outcome) / stake, stake = 1 - p (up jumps, buying NO) or p (down jumps, buying YES).
"Net" subtracts the calibration error b(p) at the entry price (the same b(p) as everywhere,
category x price bin), leaving the part due to the jump itself: n = overshoot at p / stake.
Spread = (price on the other side - price on the bettor's side) * sgn.

Output local_data/r06/r06_fade_moves.parquet (read by explore/r08_fade_robust.py).
Usage: python explore/r06_fade.py
"""
import glob
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "explore")
from r02_persistence import BET_BAND, calibration, overshoot_cat  # noqa: E402

OUT = "local_data/r06/"


def micro_moves():
    return pd.concat([pd.read_parquet(f) for f in glob.glob(OUT + "micro/x*.parquet")], ignore_index=True)


def main():
    cb = calibration()
    t = pd.read_parquet("local_data/r03_tradable_main.parquet")
    t = t.merge(micro_moves(), on=["market", "t_close"], how="inner")
    t = t[t.fade_px.notna() & t.follow_px.notna() & t.y_pre.between(BET_BAND, 1 - BET_BAND)].copy()
    p = t.fade_px.astype(float)
    stake = np.where(t.sgn > 0, 1 - p, p)
    t["r_taker"] = t.sgn * (p - t.outcome) / stake
    t["n_taker"] = overshoot_cat(t, p, cb) / stake
    t["spread"] = (t.follow_px - t.fade_px) * t.sgn
    print(f"jumps with prices on both sides: {len(t):,} in {t.market.nunique():,} markets")
    print(t.groupby("tg", observed=True).agg(jumps=("n_taker", "size"), net=("n_taker", "mean"),
                                             spread=("spread", "median")).round(4).to_string())
    t.to_parquet(OUT + "r06_fade_moves.parquet", index=False)


if __name__ == "__main__":
    main()
