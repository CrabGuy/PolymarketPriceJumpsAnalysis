"""
Stage 9: which move filters matter? Big moves (15-min VWAP bars, no limit on the time since
the previous active bar) under several filter variants, from one load per bucket:

  base         markets with 100+ trades; bars after end_date dropped; if the price ends
               outside [0.05, 0.95], bars from 6 h before it last left the band dropped;
               price before the move within [0.05, 0.95]
  no_min       any number of trades
  no_endcut    bars after end_date kept
  no_pad       cut at the last bar inside the band (no 6 h pad)
  no_ends      neither the end_date cut nor the pad (cut only after the price leaves the
               band for good)
  no_band      price before the move anywhere in (0, 1)

Per variant: tmp/events9/<variant>/e<k>.parquet (moves) and r<k>.parquet (5% random bars
after the variant's cuts, for the calibration baseline).
Usage: python s9_variants.py <bucket> [<bucket> ...]
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
BAND = 0.05
VARIANTS = {
    "base": dict(min_trades=100, endcut=True, pad=6, edge=BAND),
    "no_min": dict(min_trades=1, endcut=True, pad=6, edge=BAND),
    "no_endcut": dict(min_trades=100, endcut=False, pad=6, edge=BAND),
    "no_pad": dict(min_trades=100, endcut=True, pad=0, edge=BAND),
    "no_ends": dict(min_trades=100, endcut=False, pad=0, edge=BAND),
    "no_band": dict(min_trades=100, endcut=True, pad=6, edge=0.0),
}


def cuts(bars, end_ts, endcut, pad):
    out = {}
    for m, g in bars.groupby("market", sort=False):
        y, t = g.vwap.values, g.t_close.values
        lim = end_ts.get(m, np.inf) if endcut else np.inf
        inside = (y >= BAND) & (y <= 1 - BAND)
        if len(y) and not inside[-1] and inside.any():
            lim = min(lim, t[np.flatnonzero(inside)[-1]] - pad * 3600)
        out[m] = lim
    return pd.Series(out)


def process(k, end_ts):
    files = sorted(glob.glob(f"{s2.SRC}/b{k:02d}_*.parquet"))
    d = pd.concat([pd.read_parquet(f, columns=["market", "ts", "yes", "usd", "taker"]) for f in files],
                  ignore_index=True)
    n_per = d.market.value_counts()
    d = d.sort_values(["market", "ts"], kind="mergesort").reset_index(drop=True)
    d["bar"] = d.ts // BAR
    d["pv"] = d.yes * d.usd
    g = d.groupby(["market", "bar"], sort=False)
    allbars = g.agg(yes=("yes", "last"), pv=("pv", "sum"), n=("yes", "size"), usd=("usd", "sum"),
                    takers=("taker", "nunique")).reset_index()
    allbars["vwap"] = np.where(allbars.usd > 0, allbars.pv / allbars.usd.where(allbars.usd > 0), allbars.yes)
    allbars["t_close"] = (allbars.bar + 1) * BAR
    key = d.market.values.astype("int64") * 10**10 + d.ts.values
    res = {}
    for name, v in VARIANTS.items():
        keep = n_per[n_per >= v["min_trades"]].index
        bars = allbars[allbars.market.isin(keep)].reset_index(drop=True)
        bars["cut"] = bars.market.map(cuts(bars, end_ts, v["endcut"], v["pad"])).values
        bars = bars[bars.t_close <= bars.cut].reset_index(drop=True)
        gap_saved, edge_saved = s2.MAX_GAP_BARS, s2.EDGE
        s2.MAX_GAP_BARS, s2.EDGE = 10**9, v["edge"]
        e = s2.moves(bars, "vwap")
        s2.MAX_GAP_BARS, s2.EDGE = gap_saved, edge_saved
        e = e[e.move.abs() >= 0.4].reset_index(drop=True)
        q = e.market.values.astype("int64") * 10**10 + e.t_close.values
        i0 = np.searchsorted(key, q, side="left")
        idx = np.minimum(i0[:, None] + np.arange(ENTRY_N), len(d) - 1)
        ok = (d.market.values[idx] == e.market.values[:, None]) & \
             (d.ts.values[idx] < e.t_close.values[:, None] + ENTRY_MAX) & \
             (i0[:, None] + np.arange(ENTRY_N) < len(d))
        usd = np.where(ok, d.usd.values[idx], 0.0)
        pv = np.where(ok, d.yes.values[idx] * d.usd.values[idx], 0.0)
        e["entry_vwap"] = np.where(usd.sum(1) > 0, pv.sum(1) / np.maximum(usd.sum(1), 1e-12), np.nan)
        e = e[["market", "t_close", "y_pre", "move", "takers", "usd", "entry_vwap"]]
        for c in e.columns:
            if e[c].dtype == "float64":
                e[c] = e[c].astype("float32")
        rng = np.random.default_rng(k)
        rnd = bars.loc[rng.random(len(bars)) < SAMPLE, ["market", "t_close", "vwap"]].copy()
        rnd["vwap"] = rnd.vwap.astype("float32")
        res[name] = (e, rnd)
    return res


def main(buckets):
    mk = pd.read_parquet(s2.MARKETS, columns=["id", "end_date"])
    mk = mk[pd.to_numeric(mk.id, errors="coerce").notna()]
    secs = (mk.end_date - pd.Timestamp(0, tz="UTC")).dt.total_seconds()
    end_ts = pd.Series(secs.values, index=mk.id.astype(int).values)
    end_ts = end_ts[~end_ts.index.duplicated()]
    for name in VARIANTS:
        os.makedirs(f"{OUT}/{name}", exist_ok=True)
    for k in buckets:
        t0 = time.time()
        res = process(k, end_ts)
        for name, (e, rnd) in res.items():
            e.to_parquet(f"{OUT}/{name}/e{k:02d}.parquet", index=False)
            rnd.to_parquet(f"{OUT}/{name}/r{k:02d}.parquet", index=False)
        print(f"bucket {k}: " + ", ".join(f"{n} {len(r[0]):,}" for n, r in res.items()) + f"  ({time.time() - t0:.0f}s)",
              flush=True)


if __name__ == "__main__":
    main([int(x) for x in sys.argv[1:]])
