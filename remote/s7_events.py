"""
Stage 7: two variants of the stage-3 moves (15-minute bars), per bucket of tmp/buckets.

Round 9: superseded. The main window (s2_events.window) keeps the games, so F7 now uses the
stage-3 jumps; the modes below were run under the old 6 h end cut.
mode "sports"  sports and esports markets only (tag regex SPORTS), VWAP basis, with a cut
               suited to games. The probe (p7_probe.py) showed that for game markets
               end_date is about the kickoff, trading peaks in the hour after it, and the
               price leaves [0.05, 0.95] for good about 1-2 h after it. The stage-2 cuts
               (bars after end_date; 6 h before the price leaves the band) therefore removed
               every live game. Here:
                 - no end_date cut;
                 - cut = close of the last bar whose price is inside [0.05, 0.95], when the
                   market ends outside the band (no pad). The decisive bar that takes the
                   price out of the band is dropped (resolution convergence).
               Extra columns per move: res_ts (cut time), kickoff (end_date when the
               resolution comes 0-6 h after it, else NaN), live (bar closes after the
               kickoff; without a kickoff, within 3 h of res_ts), hours_to_res.
               Superseded (round 8): kickoff, live and hours_to_res are not used, because
               end_date is not a reliable kickoff (esports often settle before it). Drop
               them the next time this script is changed for another reason.
mode "basis"   all event markets, the usual stage-2 cuts, moves measured on the
               equal-weighted MEAN trade price of each bar instead of the VWAP, and the
               next-trades price as the plain mean of the first 5 trades (entry_mean).
mode "gap"     all event markets, the usual cuts and VWAP basis, but NO limit on the time
               since the previous active bar (stage 2 required at most 2 h). Each move
               carries gap_h, the hours since the previous active bar, so any limit can be
               applied afterwards.

Both write tmp/events7/<mode>/e<k>.parquet (moves) and r<k>.parquet (5% random active bars,
for a calibration baseline on the same price basis).
Usage: python s7_events.py <mode> <bucket> [<bucket> ...]
Python 3.8 compatible (server).
"""
import glob
import os
import sys
import time

import numpy as np
import pandas as pd

import s2_events as s2

TAGS = "data/market_tags.csv"
SPORTS = "esports|counter-strike|dota|league-of-legends|valorant|sports|nba|nfl|soccer|tennis|mlb|nhl|ufc|f1|golf|cricket|ncaa"
BAR = s2.BAR
ENTRY_N = 5                    # as s3_events (elbow)
ENTRY_MAX = 2700
SAMPLE = 0.05
LIVE_H = 3
OUT = "tmp/events7"


def sports_markets():
    t = pd.read_csv(TAGS, dtype=str)
    return set(t.market_id[t.tags.str.contains(SPORTS, na=False)].astype(int))


def sports_cut(bars, end_ts):
    res, kick = {}, {}
    for m, g in bars.groupby("market", sort=False):
        y, t = g.vwap.values, g.t_close.values
        inside = (y >= s2.EDGE) & (y <= 1 - s2.EDGE)
        r = t[np.flatnonzero(inside)[-1]] if len(y) and not inside[-1] and inside.any() else np.inf
        res[m] = r
        e = end_ts.get(m, np.nan)
        kick[m] = e if np.isfinite(r) and 0 <= r - e <= 6 * 3600 else np.nan
    return pd.Series(res), pd.Series(kick)


def process(k, end_ts, mode, keep):
    files = sorted(glob.glob(f"{s2.SRC}/b{k:02d}_*.parquet"))
    d = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    if keep is not None:
        d = d[d.market.isin(keep)]
    n_per = d.market.value_counts()
    d = d[d.market.isin(n_per[n_per >= s2.MIN_TRADES].index)]
    d = d.sort_values(["market", "ts"], kind="mergesort").reset_index(drop=True)
    d["bar"] = d.ts // BAR
    d["sw_usd"] = d.usd * d.sweep
    d["flow"] = d.usd * d.up
    d["pv"] = d.yes * d.usd
    g = d.groupby(["market", "bar"], sort=False)
    bars = g.agg(yes=("yes", "last"), mean=("yes", "mean"), pv=("pv", "sum"), n=("yes", "size"), usd=("usd", "sum"),
                 sw_usd=("sw_usd", "sum"), max_usd=("usd", "max"), flow=("flow", "sum"),
                 takers=("taker", "nunique"), taker_first=("taker", "first")).reset_index()
    bars["vwap"] = np.where(bars.usd > 0, bars.pv / bars.usd.where(bars.usd > 0), bars.yes)
    bars["t_close"] = (bars.bar + 1) * BAR
    if mode == "sports":
        res, kick = sports_cut(bars, end_ts)
        bars["cut"] = bars.market.map(res).values
        basis = "vwap"
    else:
        bars = s2.window(bars)
        basis = "mean" if mode == "basis" else "vwap"
    bars = bars[bars.t_close <= bars.cut].reset_index(drop=True)
    same = np.r_[False, bars.market.values[1:] == bars.market.values[:-1]]
    bars["gap_h"] = np.where(same, np.r_[0, np.diff(bars.bar.values)] * BAR / 3600, np.nan).astype("float32")
    saved = s2.MAX_GAP_BARS
    if mode == "gap":
        s2.MAX_GAP_BARS = 10**9
    e = s2.moves(bars, basis)
    s2.MAX_GAP_BARS = saved

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
    e["entry_mean"] = np.where(ok.sum(1) > 0, np.where(ok, d.yes.values[idx], 0).sum(1) / np.maximum(ok.sum(1), 1), np.nan)
    e["entry_delay"] = np.where(ok[:, 0], d.ts.values[idx[:, 0]] - e.t_close.values, np.nan)
    e["taker1"] = np.where(e.takers == 1, e.taker_first.values, 0).astype("uint64")
    e["sweep_share"] = e.sw_usd / e.usd.where(e.usd > 0)
    e["days_to_end"] = (e.market.map(end_ts).values - e.t_close.values) / 86400
    cols = ["market", "t_close", "y_pre", "yes", "move", "n", "usd", "takers", "sweep_share", "days_to_end",
            "ret_1h", "ret_6h", "ret_24h", "entry_vwap", "entry_mean", "entry_n", "entry_delay", "taker1"]
    if mode == "sports":
        e["res_ts"] = e.market.map(res).values
        e["kickoff"] = e.market.map(kick).values
        e["hours_to_res"] = (e.res_ts - e.t_close) / 3600
        e["live"] = np.where(np.isfinite(e.kickoff), e.t_close > e.kickoff,
                             np.isfinite(e.res_ts) & (e.hours_to_res <= LIVE_H)).astype("int8")
        cols += ["res_ts", "kickoff", "hours_to_res", "live"]
    if mode == "gap":
        cols += ["gap_h"]
    e = e[cols]
    for c in e.columns:
        if e[c].dtype == "float64":
            e[c] = e[c].astype("float32")

    rng = np.random.default_rng(k)
    pick = rng.random(len(bars)) < SAMPLE
    rnd = bars.loc[pick, ["market", "t_close", basis]].rename(columns={basis: "price"}).copy()
    if mode == "sports":
        rnd["live"] = np.where(np.isfinite(rnd.market.map(kick).values), rnd.t_close.values > rnd.market.map(kick).values,
                               (rnd.market.map(res).values - rnd.t_close.values) <= LIVE_H * 3600).astype("int8")
    rnd["price"] = rnd.price.astype("float32")
    cov = bars.groupby("market").agg(active_bars=("n", "size"), trades=("n", "sum")).reset_index()
    cov["moves_04"] = cov.market.map(e[e.move.abs() >= 0.4].market.value_counts()).fillna(0).astype(int)
    return e, rnd, cov


def main(mode, buckets):
    out = f"{OUT}/{mode}"
    os.makedirs(out, exist_ok=True)
    mk = pd.read_parquet(s2.MARKETS, columns=["id", "end_date"])
    mk = mk[pd.to_numeric(mk.id, errors="coerce").notna()]
    secs = (mk.end_date - pd.Timestamp(0, tz="UTC")).dt.total_seconds()
    end_ts = pd.Series(secs.values, index=mk.id.astype(int).values)
    end_ts = end_ts[~end_ts.index.duplicated()]
    keep = sports_markets() if mode == "sports" else None
    for k in buckets:
        t0 = time.time()
        e, rnd, cov = process(k, end_ts, mode, keep)
        e.to_parquet(f"{out}/e{k:02d}.parquet", index=False)
        rnd.to_parquet(f"{out}/r{k:02d}.parquet", index=False)
        cov.to_parquet(f"{out}/m{k:02d}.parquet", index=False)
        print(f"{mode} bucket {k}: {len(cov):,} markets, {len(e):,} moves, {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main(sys.argv[1], [int(x) for x in sys.argv[2:]])
