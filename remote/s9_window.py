"""
Stage 9: price jumps with no end pad, plus where each one falls in its market's life, so that
cuts at the start and the end of a market (fixed hours, a share of the lifetime, or a share
of the trades) can be compared afterwards.

Same 15-minute VWAP slots and moves as s3_events.py (moves of at least s2.MIN_MOVE = 0.15 in
log-odds, so that any later threshold is a subset), but the only cut is the settle moment:
slots after the last slot whose price is inside [0.05, 0.95] are dropped when the market ends
outside the band (judged on the slot's last trade, as the old 6 h cut). Per move: the slot's cumulative trade count in its market (`rank`).
Per market (m<k>): first and last trade time, settle time (NaN if it never settles), and the
trade counts in total and up to the settle moment. A 5% random sample of slots carries the
same `rank`, for a baseline under the same cuts.

Writes tmp/events9/e<k>.parquet (moves), r<k>.parquet (random slots), m<k>.parquet (markets).
Usage: python s9_window.py <bucket> [<bucket> ...]
Python 3.8 compatible (server).
"""
import glob
import os
import sys
import time

import numpy as np
import pandas as pd

import s2_events as s2

BAR = 900
ENTRY_N = 5
ENTRY_MAX = 3600
SAMPLE = 0.05
OUT = "tmp/events9"


def process(k):
    files = sorted(glob.glob(f"{s2.SRC}/b{k:02d}_*.parquet"))
    if not files:
        return None
    d = pd.concat([pd.read_parquet(f, columns=["market", "ts", "yes", "usd", "taker"]) for f in files],
                  ignore_index=True)
    d = d.sort_values(["market", "ts"], kind="mergesort").reset_index(drop=True)
    d["bar"] = d.ts // BAR
    d["pv"] = d.yes * d.usd
    bars = d.groupby(["market", "bar"], sort=False).agg(
        yes=("yes", "last"), pv=("pv", "sum"), n=("yes", "size"), usd=("usd", "sum"),
        takers=("taker", "nunique")).reset_index()
    bars["vwap"] = np.where(bars.usd > 0, bars.pv / bars.usd.where(bars.usd > 0), bars.yes)
    bars["t_close"] = (bars.bar + 1) * BAR
    bars["rank"] = bars.groupby("market", sort=False).n.cumsum()

    settle = {}
    for m, g in bars.groupby("market", sort=False):
        y, t = g.yes.values, g.t_close.values      # last trade, as the old 6 h cut
        inside = (y >= s2.EDGE) & (y <= 1 - s2.EDGE)
        settle[m] = t[np.flatnonzero(inside)[-1]] if not inside[-1] and inside.any() else np.nan
    settle = pd.Series(settle)
    mk = d.groupby("market", sort=False).agg(t_first=("ts", "min"), t_last=("ts", "max"),
                                             n_total=("ts", "size")).reset_index()
    mk["t_settle"] = mk.market.map(settle).values
    bars["cut"] = bars.market.map(settle).fillna(np.inf).values
    mk["n_settle"] = mk.market.map(bars[bars.t_close <= bars.cut].groupby("market").n.sum()).fillna(0).astype("int64")
    bars = bars[bars.t_close <= bars.cut].reset_index(drop=True)

    e = s2.moves(bars, "vwap")
    key = d.market.values.astype("int64") * 10**10 + d.ts.values
    q = e.market.values.astype("int64") * 10**10 + e.t_close.values
    i0 = np.searchsorted(key, q, side="left")
    idx = np.minimum(i0[:, None] + np.arange(ENTRY_N), len(d) - 1)
    ok = (d.market.values[idx] == e.market.values[:, None]) & \
         (d.ts.values[idx] < e.t_close.values[:, None] + ENTRY_MAX) & \
         (i0[:, None] + np.arange(ENTRY_N) < len(d))
    usd = np.where(ok, d.usd.values[idx], 0.0)
    pv = np.where(ok, d.yes.values[idx] * d.usd.values[idx], 0.0)
    e["entry_vwap"] = np.where(usd.sum(1) > 0, pv.sum(1) / np.maximum(usd.sum(1), 1e-12), np.nan)
    e = e[["market", "t_close", "y_pre", "yes", "move", "n", "usd", "takers", "entry_vwap", "rank"]]
    for c in ("y_pre", "yes", "move", "usd", "entry_vwap"):
        e[c] = e[c].astype("float32")

    rng = np.random.default_rng(k)
    rnd = bars.loc[rng.random(len(bars)) < SAMPLE, ["market", "t_close", "vwap", "rank"]].copy()
    rnd["vwap"] = rnd.vwap.astype("float32")
    return e, rnd, mk


def main(buckets):
    os.makedirs(OUT, exist_ok=True)
    for k in buckets:
        t0 = time.time()
        res = process(k)
        if res is None:
            continue
        for name, x in zip("erm", res):
            x.to_parquet(f"{OUT}/{name}{k:02d}.parquet", index=False)
        print(f"bucket {k}: {len(res[0]):,} moves, {len(res[2]):,} markets, {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main([int(x) for x in sys.argv[1:]])
