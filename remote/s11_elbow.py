"""
Stage 11: inputs for the elbow (knee) checks of the parameters that need the trades.

Same slots, window and price jumps as s2_events.py / s3_events.py, but with the slot length
and the settle band varied one at a time (the other parameters at their main values:
15-minute slots, band [0.05, 0.95], 10% of the life left out at each end, jumps of 10 points
or more). Configurations (column `cfg`):
  b<seconds>   slot length 60 s to 2 h, band 0.05
  e<edge>      band [edge, 1 - edge] for the settle moment, 15-minute slots
Per configuration: every price jump (market, t_close, y_pre, vwap, takers, the next active
slot's vwap `nxt`) and a 2% random sample of the slots in the window (for the baseline).
For the main configuration only: the first NEXT_N trades after each jump's slot, within
NEXT_MAX seconds (seconds after the close, YES price, dollars), for the next-trades check.

Writes tmp/elbow/j<k>.parquet (jumps), r<k>.parquet (random slots), x<k>.parquet (next trades).
Usage: python s11_elbow.py <bucket> [<bucket> ...]
Python 3.8 compatible (server).
"""
import glob
import os
import sys
import time

import numpy as np
import pandas as pd

import s2_events as s2

SLOTS = (60, 120, 300, 600, 900, 1200, 1800, 2700, 3600, 7200)
EDGES = (0.01, 0.02, 0.03, 0.05, 0.10, 0.15, 0.20)
MIN_PTS = 0.13
SAMPLE = 0.02
NEXT_N = 20
NEXT_MAX = 4 * 3600
OUT = "tmp/elbow"


def slots(d, bar_s):
    b = d.ts.values // bar_s
    x = d.assign(bar=b, pv=d.yes * d.usd)
    bars = x.groupby(["market", "bar"], sort=False).agg(
        yes=("yes", "last"), pv=("pv", "sum"), usd=("usd", "sum"), takers=("taker", "nunique")).reset_index()
    bars["vwap"] = np.where(bars.usd > 0, bars.pv / bars.usd.where(bars.usd > 0), bars.yes)
    bars["t_close"] = (bars.bar + 1) * bar_s
    return bars


def window(bars, edge):
    """s2_events.window with the band [edge, 1 - edge]."""
    t, m = bars.t_close, bars.market
    inside = (bars.yes >= edge) & (bars.yes <= 1 - edge)
    first, last = t.groupby(m).transform("min"), t.groupby(m).transform("max")
    last_in = t.where(inside).groupby(m).transform("max")
    ends_out = ~inside.groupby(m).transform("last").astype(bool)
    end = np.where(ends_out & last_in.notna(), last_in, last)
    pad = s2.LIFE_CUT * (end - first)
    return bars[(t >= first + pad) & (t <= end - pad)].reset_index(drop=True)


def jumps(w, cfg, rng):
    mk, v = w.market.values, w.vwap.values
    same_prev = np.r_[False, mk[1:] == mk[:-1]]
    same_next = np.r_[mk[1:] == mk[:-1], False]
    y_pre = np.r_[np.nan, v[:-1]]
    nxt = np.where(same_next, np.r_[v[1:], np.nan], np.nan)
    p = np.clip(v, 0.01, 0.99)
    ev = same_prev & (np.abs(p - y_pre) >= MIN_PTS)
    j = pd.DataFrame({"cfg": cfg, "market": mk[ev], "t_close": w.t_close.values[ev], "y_pre": y_pre[ev],
                      "vwap": v[ev], "nxt": nxt[ev], "takers": w.takers.values[ev]})
    pick = rng.random(len(w)) < SAMPLE
    r = pd.DataFrame({"cfg": cfg, "market": mk[pick], "vwap": v[pick]})
    return j, r


def next_trades(d, j):
    key = d.market.values.astype("int64") * 10**10 + d.ts.values
    q = j.market.values.astype("int64") * 10**10 + j.t_close.values
    i0 = np.searchsorted(key, q, side="left")
    idx = np.minimum(i0[:, None] + np.arange(NEXT_N), len(d) - 1)
    ok = (d.market.values[idx] == j.market.values[:, None]) & \
         (d.ts.values[idx] < j.t_close.values[:, None] + NEXT_MAX) & (i0[:, None] + np.arange(NEXT_N) < len(d))
    out = {"market": j.market.values, "t_close": j.t_close.values}
    for i in range(NEXT_N):
        out[f"dt{i}"] = np.where(ok[:, i], d.ts.values[idx[:, i]] - j.t_close.values, -1).astype("int32")
        out[f"y{i}"] = np.where(ok[:, i], d.yes.values[idx[:, i]], np.nan).astype("float32")
        out[f"u{i}"] = np.where(ok[:, i], d.usd.values[idx[:, i]], np.nan).astype("float32")
    return pd.DataFrame(out)


def process(k):
    files = sorted(glob.glob(f"{s2.SRC}/b{k:02d}_*.parquet"))
    if not files:
        return None
    d = pd.concat([pd.read_parquet(f, columns=["market", "ts", "yes", "usd", "taker"]) for f in files],
                  ignore_index=True)
    d = d.sort_values(["market", "ts"], kind="mergesort").reset_index(drop=True)
    rng = np.random.default_rng(k)
    js, rs, x = [], [], None
    for bar_s in SLOTS:
        bars = slots(d, bar_s)
        edges = EDGES if bar_s == s2.BAR else (s2.EDGE,)
        for edge in edges:
            cfg = f"b{bar_s}" if edge == s2.EDGE else f"e{edge:g}"
            j, r = jumps(window(bars, edge), cfg, rng)
            js.append(j)
            rs.append(r)
            if bar_s == s2.BAR and edge == s2.EDGE:
                x = next_trades(d, j)
                js.append(j.assign(cfg=f"e{edge:g}"))
                rs.append(r.assign(cfg=f"e{edge:g}"))
    j, r = pd.concat(js, ignore_index=True), pd.concat(rs, ignore_index=True)
    for c in ("y_pre", "vwap", "nxt"):
        j[c] = j[c].astype("float32")
    r["vwap"] = r.vwap.astype("float32")
    return j, r, x


def main(buckets):
    os.makedirs(OUT, exist_ok=True)
    for k in buckets:
        t0 = time.time()
        res = process(k)
        if res is None:
            continue
        for name, x in zip("jrx", res):
            x.to_parquet(f"{OUT}/{name}{k:02d}.parquet", index=False)
        print(f"bucket {k}: {len(res[0]):,} jumps over all configurations, {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main([int(x) for x in sys.argv[1:]])
