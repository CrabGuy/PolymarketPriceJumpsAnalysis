"""
Stage 12: inputs for the joint elbow search of the parameters that define a price jump.

For every slot length in SLOTS (event markets) or CX_SLOTS (crypto up/down), the slots of
s2_events (VWAP price, last trade, distinct takers) and, with no window applied, everything
needed to apply any threshold, start/end cut, settle band and price clip locally:
  j  every move of at least MIN_PTS between consecutive slots with trades (market, t_close,
     raw previous VWAP y_pre, raw VWAP, takers, usd)
  r  a SAMPLE share of all slots (market, t_close, vwap), for the baseline
  m  per market and slot length: first and last slot close, and for each settle band edge in
     EDGES the settle moment (the last slot whose last trade is inside [edge, 1 - edge], when
     the market's last slot is outside it; NaN otherwise)
  g  the number of gaps between consecutive slots with trades, by gap length in slots
  x  for the slot lengths in NEXT_SLOTS (CX_NEXT_SLOTS) and moves of at least NEXT_MIN_PTS:
     the first NEXT_N trades after the slot's close within NEXT_MAX seconds (dt, YES, $)

Writes tmp/grid/<mode>/{j,r,m,g,x}<k>.parquet.
Usage: python s12_grid.py <events|cx> <bucket> [<bucket> ...]
Python 3.8 compatible (server).
"""
import glob
import os
import sys
import time

import numpy as np
import pandas as pd

import s2_events as s2

EDGES = (0.01, 0.02, 0.03, 0.05, 0.10, 0.15, 0.20)
MIN_PTS = 0.05
SAMPLE = 0.02
NEXT_N = 16
NEXT_MIN_PTS = 0.08
MODES = {
    "events": dict(src="tmp/buckets", slots=(60, 120, 300, 600, 900, 1200, 1800, 2700, 3600, 5400, 7200),
                   next_slots=(900, 1200, 1800, 2700, 3600), next_max=3 * 3600),
    "cx": dict(src="tmp/buckets_cx", slots=(15, 30, 60, 120, 300),
               next_slots=(30, 60, 120), next_max=900),
}


def slots(d, bar_s):
    x = d.assign(bar=d.ts.values // bar_s, pv=d.yes * d.usd)
    b = x.groupby(["market", "bar"], sort=False).agg(
        yes=("yes", "last"), pv=("pv", "sum"), usd=("usd", "sum"), takers=("taker", "nunique")).reset_index()
    b["vwap"] = np.where(b.usd > 0, b.pv / b.usd.where(b.usd > 0), b.yes)
    b["t_close"] = (b.bar + 1) * bar_s
    return b


def market_times(b, bar_s):
    t, m = b.t_close, b.market
    out = pd.DataFrame({"t_first": t.groupby(m).min(), "t_last": t.groupby(m).max()})
    last_out = {}
    for e in EDGES:
        inside = (b.yes >= e) & (b.yes <= 1 - e)
        last_in = t.where(inside).groupby(m).max()
        ends_out = ~inside.groupby(m).last().astype(bool)
        out[f"settle_{e:g}"] = last_in.where(ends_out)
    out["slot"] = bar_s
    return out.reset_index()


def moves(b, bar_s, rng):
    mk, v = b.market.values, b.vwap.values
    prev = np.r_[False, mk[1:] == mk[:-1]]
    y_pre = np.r_[np.nan, v[:-1]]
    ev = prev & (np.abs(v - y_pre) >= MIN_PTS)
    j = pd.DataFrame({"slot": bar_s, "market": mk[ev], "t_close": b.t_close.values[ev],
                      "y_pre": y_pre[ev].astype("float32"), "vwap": v[ev].astype("float32"),
                      "takers": b.takers.values[ev].astype("int32"), "usd": b.usd.values[ev].astype("float32")})
    pick = rng.random(len(b)) < SAMPLE
    r = pd.DataFrame({"slot": bar_s, "market": mk[pick], "t_close": b.t_close.values[pick],
                      "vwap": v[pick].astype("float32")})
    gaps = np.diff(b.bar.values)[mk[1:] == mk[:-1]]
    g = pd.Series(np.minimum(gaps, 500)).value_counts().rename_axis("gap").reset_index(name="n")
    g["slot"] = bar_s
    return j, r, g


def next_trades(d, j, max_s):
    j = j[np.abs(j.vwap - j.y_pre) >= NEXT_MIN_PTS]
    key = d.market.values.astype("int64") * 10**10 + d.ts.values
    q = j.market.values.astype("int64") * 10**10 + j.t_close.values
    i0 = np.searchsorted(key, q, side="left")
    idx = np.minimum(i0[:, None] + np.arange(NEXT_N), len(d) - 1)
    ok = (d.market.values[idx] == j.market.values[:, None]) & \
         (d.ts.values[idx] < j.t_close.values[:, None] + max_s) & (i0[:, None] + np.arange(NEXT_N) < len(d))
    out = {"slot": j.slot.values, "market": j.market.values, "t_close": j.t_close.values}
    for i in range(NEXT_N):
        out[f"dt{i}"] = np.where(ok[:, i], d.ts.values[idx[:, i]] - j.t_close.values, -1).astype("int32")
        out[f"y{i}"] = np.where(ok[:, i], d.yes.values[idx[:, i]], np.nan).astype("float32")
        out[f"u{i}"] = np.where(ok[:, i], d.usd.values[idx[:, i]], np.nan).astype("float32")
    return pd.DataFrame(out)


def process(mode, k):
    cfg = MODES[mode]
    files = sorted(glob.glob(f"{cfg['src']}/b{k:02d}_*.parquet"))
    if not files:
        return None
    d = pd.concat([pd.read_parquet(f, columns=["market", "ts", "yes", "usd", "taker"]) for f in files],
                  ignore_index=True)
    d = d.sort_values(["market", "ts"], kind="mergesort").reset_index(drop=True)
    rng = np.random.default_rng(k)
    out = {c: [] for c in "jrmgx"}
    for bar_s in cfg["slots"]:
        b = slots(d, bar_s)
        j, r, g = moves(b, bar_s, rng)
        out["j"].append(j)
        out["r"].append(r)
        out["g"].append(g)
        out["m"].append(market_times(b, bar_s))
        if bar_s in cfg["next_slots"]:
            out["x"].append(next_trades(d, j, cfg["next_max"]))
    return {c: pd.concat(v, ignore_index=True) for c, v in out.items()}


def main(mode, buckets):
    dst = f"tmp/grid/{mode}"
    os.makedirs(dst, exist_ok=True)
    for k in buckets:
        t0 = time.time()
        res = process(mode, k)
        if res is None:
            continue
        for c, x in res.items():
            x.to_parquet(f"{dst}/{c}{k:02d}.parquet", index=False)
        print(f"{mode} bucket {k}: {len(res['j']):,} moves over all slot lengths, {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main(sys.argv[1], [int(x) for x in sys.argv[2:]])
