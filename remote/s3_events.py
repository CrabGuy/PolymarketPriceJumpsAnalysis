"""
Stage 3: round-3 moves with tradability, the mover's identity, and a random baseline.

Same bars, window and moves as s2_events.py (imported from there), VWAP basis only, with a
configurable bar size. Extra columns per move:
  entry_vwap   volume-weighted YES price of the first ENTRY_N trades after the bar closes
               (at most 1 h later): the next price an outsider could have traded at
  entry_n, entry_delay   how many trades that used, and seconds to the first one
  taker1       hash of the only taker when the move bar had exactly one, else 0
Also, for the main bar size (s2.BAR) only: a 5% random sample of all active bars (market, t_close, vwap)
for a calibration baseline at random moments.

Writes tmp/events3/<bar>/e<k>.parquet and tmp/events3/<bar>/r<k>.parquet.
Usage: python s3_events.py <bar_seconds> <bucket> [<bucket> ...]
Python 3.8 compatible (server).
"""
import glob
import os
import sys
import time

import numpy as np
import pandas as pd

import s2_events as s2

ENTRY_N = 8                    # round 11, elbow (was 5)
ENTRY_MAX = 3600
SAMPLE = 0.05
OUT_ROOT = "tmp/events3"


def process(k, end_ts, bar_s):
    files = sorted(glob.glob(f"{s2.SRC}/b{k:02d}_*.parquet"))
    if not files:
        return None, None
    d = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    n_per = d.market.value_counts()
    d = d[d.market.isin(n_per[n_per >= s2.MIN_TRADES].index)]
    d = d.sort_values(["market", "ts"], kind="mergesort").reset_index(drop=True)
    d["bar"] = d.ts // bar_s
    d["sw_usd"] = d.usd * d.sweep
    d["flow"] = d.usd * d.up
    d["pv"] = d.yes * d.usd

    g = d.groupby(["market", "bar"], sort=False)
    bars = g.agg(yes=("yes", "last"), pv=("pv", "sum"), n=("yes", "size"), usd=("usd", "sum"),
                 sw_usd=("sw_usd", "sum"), max_usd=("usd", "max"), flow=("flow", "sum"),
                 takers=("taker", "nunique"), taker_first=("taker", "first")).reset_index()
    bars["vwap"] = np.where(bars.usd > 0, bars.pv / bars.usd.where(bars.usd > 0), bars.yes)
    bars["t_close"] = (bars.bar + 1) * bar_s
    bars = s2.window(bars)

    saved = s2.MAX_GAP_BARS
    s2.MAX_GAP_BARS = max(1, int(round(saved * 900 / bar_s)))   # rescaled to the bar size (no limit since round 8)
    e = s2.moves(bars, "vwap")
    s2.MAX_GAP_BARS = saved

    # Next tradable price: the first ENTRY_N trades at or after the bar close, same market.
    key = d.market.values.astype("int64") * 10**10 + d.ts.values
    q = e.market.values.astype("int64") * 10**10 + e.t_close.values
    i0 = np.searchsorted(key, q, side="left")
    idx = np.minimum(i0[:, None] + np.arange(ENTRY_N), len(d) - 1)
    ok = (d.market.values[idx] == e.market.values[:, None]) & \
         (d.ts.values[idx] < e.t_close.values[:, None] + ENTRY_MAX) & \
         (i0[:, None] + np.arange(ENTRY_N) < len(d))
    usd = np.where(ok, d.usd.values[idx], 0.0)
    pv = np.where(ok, d.yes.values[idx] * d.usd.values[idx], 0.0)
    e["entry_n"] = ok.sum(1)
    e["entry_vwap"] = np.where(usd.sum(1) > 0, pv.sum(1) / np.maximum(usd.sum(1), 1e-12), np.nan)
    e["entry_delay"] = np.where(ok[:, 0], d.ts.values[idx[:, 0]] - e.t_close.values, np.nan)
    e["taker1"] = np.where(e.takers == 1, e.taker_first.values, 0).astype("uint64")

    e["sweep_share"] = e.sw_usd / e.usd.where(e.usd > 0)
    e["flow_agree"] = e.flow / e.usd.where(e.usd > 0) * np.sign(e.move)
    e["days_to_end"] = (e.market.map(end_ts).values - e.t_close.values) / 86400
    keep = ["market", "t_close", "y_pre", "yes", "move", "n", "usd", "takers", "sweep_share",
            "flow_agree", "days_to_end", "ret_1h", "ret_6h", "ret_24h",
            "entry_vwap", "entry_n", "entry_delay", "taker1"]
    e = e[keep]
    for c in e.columns:
        if e[c].dtype == "float64":
            e[c] = e[c].astype("float32")

    rnd = None
    if bar_s == s2.BAR:
        rng = np.random.default_rng(k)
        pick = rng.random(len(bars)) < SAMPLE
        rnd = bars.loc[pick, ["market", "t_close", "vwap"]].copy()
        rnd["vwap"] = rnd.vwap.astype("float32")
    return e, rnd


def main(bar_s, buckets):
    out = f"{OUT_ROOT}/{bar_s}"
    os.makedirs(out, exist_ok=True)
    mk = pd.read_parquet(s2.MARKETS, columns=["id", "end_date"])
    mk = mk[pd.to_numeric(mk.id, errors="coerce").notna()]
    secs = (mk.end_date - pd.Timestamp(0, tz="UTC")).dt.total_seconds()
    end_ts = pd.Series(secs.values, index=mk.id.astype(int).values)
    end_ts = end_ts[~end_ts.index.duplicated()]
    for k in buckets:
        t0 = time.time()
        e, rnd = process(k, end_ts, bar_s)
        if e is None:
            continue
        e.to_parquet(f"{out}/e{k:02d}.parquet", index=False)
        if rnd is not None:
            rnd.to_parquet(f"{out}/r{k:02d}.parquet", index=False)
        print(f"bar {bar_s} bucket {k}: {len(e):,} moves, {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]), [int(x) for x in sys.argv[2:]])
