"""
Stage 2: per bucket, find every sizeable price move and measure whether it persists.

For each market: 15-min bars from the bucket rows, then only the middle of the market's life
is kept (window()): its life runs from the first bar to the settle moment (the last bar
inside [0.05, 0.95] when the market ends outside the band, else its last bar), and the first
and last LIFE_CUT of it are left out (round 9; was: the last 6 h before the settle moment).
A move is a bar whose price (log-odds) differs from the previous active bar's by at least
MIN_MOVE; the analysis keeps moves of 10 points or more (price jumps).
(Round 8: the minimum of 100 trades per market, the end_date cut, the limit of 2 h since
the previous active bar and the [0.05, 0.95] band on the starting price were tested one by
one and removed: none changed the results by more than 2 points; explore/r08_filters.py.)
For each move:
  retained_h = (L(t+h) - L_pre) / (L_close - L_pre),  h = 1 h, 6 h, 24 h,
(NaN if t+h is past the cut).
Two price bases (column `basis`): "last" = the bar's last trade, "vwap" = its
volume-weighted average price, which is robust to a sweep's extreme last fill. L(t+h) is
the same basis at the latest active bar closing at or before t+h.
Features of the move bar: usd, trades, distinct takers, sweep share of usd, largest
trade share, signed-flow agreement with the move, pre price, size, hour.

Writes tmp/events/e<k>.parquet and tmp/events/m<k>.parquet (per-market coverage).
Usage: python s2_events.py <bucket> [<bucket> ...]
Python 3.8 compatible (server).
"""
import glob
import os
import sys
import time

import numpy as np
import pandas as pd

MARKETS = "data/markets_final.parquet"
SRC = "tmp/buckets"
OUT = "tmp/events"
BAR = 900
MIN_TRADES = 1                 # no minimum (was 100)
MIN_MOVE = 0.15
MAX_GAP_BARS = 10**9           # no limit on the time since the previous active bar (was 8 = 2 h)
EDGE = 0.05                    # "settled" = the price left [EDGE, 1 - EDGE] for good
PRE_EDGE = 0.0                 # no band on the price before the move (was EDGE)
LIFE_CUT = 0.10                # share of the life left out at each end (was: the last 6 h)
HORIZONS = {"1h": 3600, "6h": 6 * 3600, "24h": 24 * 3600}


def logit(p):
    p = np.clip(p, 0.01, 0.99)
    return np.log(p / (1 - p))


def sigmoid(x):
    return 1 / (1 + np.exp(-x))


def window(bars):
    """Keep the bars inside each market's window (see the docstring); sets `start` and `cut`
    (the window's first and last allowed bar close; later prices stop at `cut`)."""
    t, m = bars.t_close, bars.market
    inside = (bars.yes >= EDGE) & (bars.yes <= 1 - EDGE)
    first, last = t.groupby(m).transform("min"), t.groupby(m).transform("max")
    last_in = t.where(inside).groupby(m).transform("max")
    ends_out = ~inside.groupby(m).transform("last").astype(bool)
    end = np.where(ends_out & last_in.notna(), last_in, last)
    pad = LIFE_CUT * (end - first)
    bars["start"], bars["cut"] = first + pad, end - pad
    return bars[(t >= bars.start) & (t <= bars.cut)].reset_index(drop=True)


def process(k, end_ts):
    files = sorted(glob.glob(f"{SRC}/b{k:02d}_*.parquet"))
    if not files:
        return None, None
    d = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    n_per = d.market.value_counts()
    d = d[d.market.isin(n_per[n_per >= MIN_TRADES].index)]
    d = d.sort_values(["market", "ts"], kind="mergesort").reset_index(drop=True)
    d["bar"] = d.ts // BAR
    d["sw_usd"] = d.usd * d.sweep
    d["flow"] = d.usd * d.up
    d["pv"] = d.yes * d.usd

    g = d.groupby(["market", "bar"], sort=False)
    bars = g.agg(yes=("yes", "last"), pv=("pv", "sum"), n=("yes", "size"), usd=("usd", "sum"),
                 sw_usd=("sw_usd", "sum"), max_usd=("usd", "max"), flow=("flow", "sum"),
                 takers=("taker", "nunique")).reset_index()
    bars["vwap"] = np.where(bars.usd > 0, bars.pv / bars.usd.where(bars.usd > 0), bars.yes)
    bars["t_close"] = (bars.bar + 1) * BAR

    bars = window(bars)

    # Two price bases: the bar's last trade, and its volume-weighted average (robust to a
    # sweep's extreme last fill). Moves and later prices use the same basis.
    e = pd.concat([moves(bars, "yes"), moves(bars, "vwap")], ignore_index=True)

    e["sweep_share"] = e.sw_usd / e.usd.where(e.usd > 0)
    e["max_share"] = e.max_usd / e.usd.where(e.usd > 0)
    e["flow_agree"] = e.flow / e.usd.where(e.usd > 0) * np.sign(e.move)
    e["hour"] = (e.t_close // 3600) % 24
    e["days_to_end"] = (e.market.map(end_ts).values - e.t_close.values) / 86400
    keep = ["basis", "market", "t_close", "y_pre", "yes", "move", "n", "usd", "takers", "sweep_share",
            "max_share", "flow_agree", "hour", "days_to_end", "ret_1h", "ret_6h", "ret_24h"]
    e = e[keep]
    for c in e.columns:
        if e[c].dtype == "float64":
            e[c] = e[c].astype("float32")

    cov = bars.groupby("market").agg(active_bars=("n", "size"), trades=("n", "sum"), usd=("usd", "sum"),
                                     t0=("t_close", "min"), t1=("t_close", "max")).reset_index()
    cov["moves"] = cov.market.map(e[e.basis == "last"].market.value_counts()).fillna(0).astype(int)
    return e, cov


def moves(bars, col):
    """Moves on one price basis; the price at t+h is that basis at the latest active bar
    closing at or before t+h (same market, before the cut)."""
    L = logit(bars[col].values)
    mk, bar = bars.market.values, bars.bar.values
    same = mk[1:] == mk[:-1]
    prev_ok = np.r_[False, same & (np.diff(bar) <= MAX_GAP_BARS)]
    L_pre = np.r_[np.nan, L[:-1]]
    y_pre = np.r_[np.nan, bars[col].values[:-1]]
    move = L - L_pre
    ev = prev_ok & (np.abs(np.nan_to_num(move)) >= MIN_MOVE) & (y_pre >= PRE_EDGE) & (y_pre <= 1 - PRE_EDGE)
    e = bars[ev].copy()
    e["basis"] = "last" if col == "yes" else col
    e["yes"] = bars[col].values[ev]
    e["L_pre"], e["y_pre"], e["move"] = L_pre[ev], y_pre[ev], move[ev]
    key = mk.astype("int64") * 10**10 + bars.t_close.values
    for name, h in HORIZONS.items():
        q = e.market.values.astype("int64") * 10**10 + e.t_close.values + h
        i = np.searchsorted(key, q, side="right") - 1
        ok = (e.t_close.values + h) <= e.cut.values
        e["ret_" + name] = np.where(ok, (L[i] - e.L_pre.values) / e.move.values, np.nan)
    return e


def main(buckets):
    os.makedirs(OUT, exist_ok=True)
    mk = pd.read_parquet(MARKETS, columns=["id", "end_date"])
    mk = mk[pd.to_numeric(mk.id, errors="coerce").notna()]
    secs = (mk.end_date - pd.Timestamp(0, tz="UTC")).dt.total_seconds()
    end_ts = pd.Series(secs.values, index=mk.id.astype(int).values)
    end_ts = end_ts[~end_ts.index.duplicated()]
    for k in buckets:
        t0 = time.time()
        e, cov = process(k, end_ts)
        if e is None:
            print(f"bucket {k}: no files", flush=True)
            continue
        e.to_parquet(f"{OUT}/e{k:02d}.parquet", index=False)
        cov.to_parquet(f"{OUT}/m{k:02d}.parquet", index=False)
        print(f"bucket {k}: {len(cov):,} markets, {len(e):,} moves, {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main([int(x) for x in sys.argv[1:]])
