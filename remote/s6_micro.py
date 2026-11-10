"""
Stage 6: the prices a bettor against each price jump would actually have paid (section 4.5).

Input: tmp/buckets (event-market trades, stage 1) and tmp/events3/<BAR>/e<k>.parquet (the jumps of
stage 3). For every jump, after the slot closes:
  fade_px, fade_n, fade_delay      VWAP of the first ENTRY_N trades (within ENTRY_MAX) whose taker
                                   traded AGAINST the jump (sold YES after an up jump): what a
                                   bettor crossing the spread against the jump paid
  follow_px, follow_n, follow_delay   the same for trades WITH the jump (the other side of the spread)
  fade_usd_15m, fade_usd_1h, follow_usd_1h   $ traded on that side after the close

Writes tmp/micro/x<k>.parquet (market, t_close, plus the columns above).
Usage: python s6_micro.py <bucket> [<bucket> ...]
Python 3.8 compatible (server).
"""
import glob
import os
import sys
import time

import numpy as np
import pandas as pd

import s2_events as s2

OUT = "tmp/micro"
BAR = s2.BAR
ENTRY_N = 5                    # next trades: how many (as s3_events, elbow)
ENTRY_MAX = 2700               # next trades: within this many seconds


def side_entry(ds, mkt, t):
    """First ENTRY_N trades of one side at or after t (same market, within ENTRY_MAX)."""
    key = ds.market.values.astype("int64") * 10**10 + ds.ts.values
    q = mkt.astype("int64") * 10**10 + t
    i0 = np.searchsorted(key, q, side="left")
    n = len(ds)
    idx = np.minimum(i0[:, None] + np.arange(ENTRY_N), max(n - 1, 0))
    ok = (i0[:, None] + np.arange(ENTRY_N) < n) & (ds.market.values[idx] == mkt[:, None]) & \
         (ds.ts.values[idx] < t[:, None] + ENTRY_MAX)
    usd = np.where(ok, ds.usd.values[idx], 0.0)
    pv = np.where(ok, ds.yes.values[idx] * ds.usd.values[idx], 0.0)
    px = np.where(usd.sum(1) > 0, pv.sum(1) / np.maximum(usd.sum(1), 1e-12), np.nan)
    delay = np.where(ok[:, 0], ds.ts.values[idx[:, 0]] - t, np.nan)
    cum = np.r_[0.0, np.cumsum(ds.usd.values.astype("float64"))]
    u15 = cum[np.searchsorted(key, q + 900, side="left")] - cum[i0]
    u60 = cum[np.searchsorted(key, q + 3600, side="left")] - cum[i0]
    return px, ok.sum(1), delay, u15, u60


def move_prices(d, e):
    out = e[["market", "t_close"]].copy()
    for c in ("fade_px", "fade_n", "fade_delay", "follow_px", "follow_n", "follow_delay",
              "fade_usd_15m", "fade_usd_1h", "follow_usd_1h"):
        out[c] = np.nan
    up = np.sign(e.move.values)
    sides = {1: d[d.up.values == 1].reset_index(drop=True), -1: d[d.up.values == -1].reset_index(drop=True)}
    for s in (1, -1):
        sel = up == s
        if not sel.any():
            continue
        mkt, t = e.market.values[sel], e.t_close.values[sel].astype("int64")
        px, n, dl, u15, u60 = side_entry(sides[-s], mkt, t)
        out.loc[sel, "fade_px"], out.loc[sel, "fade_n"], out.loc[sel, "fade_delay"] = px, n, dl
        out.loc[sel, "fade_usd_15m"], out.loc[sel, "fade_usd_1h"] = u15, u60
        px, n, dl, u15, u60 = side_entry(sides[s], mkt, t)
        out.loc[sel, "follow_px"], out.loc[sel, "follow_n"], out.loc[sel, "follow_delay"] = px, n, dl
        out.loc[sel, "follow_usd_1h"] = u60
    for c in out.columns[2:]:
        out[c] = out[c].astype("float32")
    return out


def main(buckets):
    os.makedirs(OUT, exist_ok=True)
    for k in buckets:
        t0 = time.time()
        files = sorted(glob.glob(f"{s2.SRC}/b{k:02d}_*.parquet"))
        ef = f"tmp/events3/{BAR}/e{k:02d}.parquet"
        if not files or not os.path.exists(ef):
            continue
        d = pd.concat([pd.read_parquet(f, columns=["market", "ts", "yes", "usd", "up"]) for f in files],
                      ignore_index=True)
        d = d.sort_values(["market", "ts"], kind="mergesort").reset_index(drop=True)
        xp = move_prices(d, pd.read_parquet(ef, columns=["market", "t_close", "move"]))
        xp.to_parquet(f"{OUT}/x{k:02d}.parquet", index=False)
        print(f"micro bucket {k}: {len(xp):,} jumps, {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main([int(x) for x in sys.argv[1:]])
