"""
Stage 4: fixed-length price paths for motif/discord search, and up/down moves.

Modes
  moves <buckets...>     non-recurring markets (tmp/buckets): for every big move
                         (VWAP basis, s2.BAR bars, jumps of >= 15 points, same window as s3),
                         the YES price at the end of 55 five-minute steps, from 35 min
                         before to 4 h after the move bar closes (forward-filled VWAP).
                         -> tmp/paths/moves_<k>.parquet (market, t_close, p0..p54)
  ud <buckets...>        up/down sample (tmp/buckets_ud): each market's YES price at 30
                         evenly spaced points across its trading window (the last 5 min,
                         15 min, 1 h, 4 h or day before end_date, by tag), forward-filled.
                         -> tmp/paths/ud_<k>.parquet (market, dur_min, n_window, p0..p29)
  udmoves <buckets...>   up/down moves via s3 with the crypto parameters CX (slot, cuts,
                         settle band, next trades) -> tmp/events3/<slot>/
  cx, cxmoves            the same as ud / udmoves on the full crypto set (tmp/buckets_cx,
                         from s1x_bucket.py) -> tmp/paths/cx_<k>.parquet, tmp/events_cx/60/
  finemoves <buckets...> as moves, at 1-minute steps from 60 min before to 8 h after the
                         slot's close (for the elbow choice of step and span)
                         -> tmp/paths/fine_<k>.parquet
  cxfine <buckets...>    as cx, with 120 points per market -> tmp/paths/cxfine_<k>.parquet
Usage: python s4_paths.py <mode> <bucket> [<bucket> ...]
Python 3.8 compatible (server).
"""
import glob
import os
import sys
import time

import numpy as np
import pandas as pd

import s2_events as s2
import s3_events as s3

STEP = 300
MIN_PTS = 0.15                       # a price jump: at least 15 points (elbow)
CX = dict(slot=60, min_pts=0.18, cut_start=0.18, cut_end=0.075, edge=0.03, clip=0.03, next_n=5, next_max=120)  # crypto (elbow)
OFFSETS = np.arange(-7, 48)          # 5-min steps relative to the move bar close
N_UD = 30
DUR = {"5M": 5, "15M": 15, "1H": 60, "4h": 240, "daily": 1440}
UD_SRC = "tmp/buckets_ud"


def end_times():
    mk = pd.read_parquet(s2.MARKETS, columns=["id", "end_date"])
    mk = mk[pd.to_numeric(mk.id, errors="coerce").notna()]
    secs = (mk.end_date - pd.Timestamp(0, tz="UTC")).dt.total_seconds()
    s = pd.Series(secs.values, index=mk.id.astype(int).values)
    return s[~s.index.duplicated()]


def load_trades(src, k):
    files = sorted(glob.glob(f"{src}/b{k:02d}_*.parquet"))
    if not files:
        return None
    d = pd.concat([pd.read_parquet(f, columns=["market", "ts", "yes", "usd"]) for f in files], ignore_index=True)
    return d.sort_values(["market", "ts"], kind="mergesort").reset_index(drop=True)


def asof(key_sorted, values, q):
    """values at the last key <= q (NaN if none)."""
    i = np.searchsorted(key_sorted, q, side="right") - 1
    out = values[np.maximum(i, 0)].astype("float64")
    out[i < 0] = np.nan
    return out, np.maximum(i, 0)


def move_paths(k, end_ts):
    e, _ = s3.process(k, end_ts, s2.BAR)
    if e is None:
        return None
    e = e[(s2.sigmoid(s2.logit(e.y_pre) + e.move) - e.y_pre).abs() >= MIN_PTS]
    d = load_trades(s2.SRC, k)
    d["bin"] = d.ts // STEP
    d["pv"] = d.yes * d.usd
    b = d.groupby(["market", "bin"], sort=False).agg(pv=("pv", "sum"), usd=("usd", "sum"), yes=("yes", "last")).reset_index()
    b["vwap"] = np.where(b.usd > 0, b.pv / b.usd.where(b.usd > 0), b.yes)
    key = b.market.values.astype("int64") * 10**10 + b.bin.values
    mk = b.market.values
    base = (e.t_close.values // STEP).astype("int64")
    q = e.market.values.astype("int64")[:, None] * 10**10 + (base[:, None] + OFFSETS[None, :] - 1)
    vals, idx = asof(key, b.vwap.values, q.ravel())
    same = mk[idx] == np.repeat(e.market.values, len(OFFSETS))
    vals[~same] = np.nan
    P = vals.reshape(len(e), len(OFFSETS)).astype("float32")
    out = pd.DataFrame(P, columns=[f"p{i}" for i in range(P.shape[1])])
    out.insert(0, "t_close", e.t_close.values)
    out.insert(0, "market", e.market.values)
    return out


def ud_paths(k, end_ts, dur_of):
    d = load_trades(UD_SRC, k)
    if d is None:
        return None
    d = d[d.market.isin(dur_of.index)]
    rows = []
    key = d.market.values.astype("int64") * 10**10 + d.ts.values
    mkts = d.market.unique()
    dur = dur_of.reindex(mkts).values * 60
    end = end_ts.reindex(mkts).values
    ok = np.isfinite(dur) & np.isfinite(end)
    mkts, dur, end = mkts[ok], dur[ok], end[ok]
    t = end[:, None] - dur[:, None] + dur[:, None] * (np.arange(1, N_UD + 1)[None, :] / N_UD)
    q = mkts.astype("int64")[:, None] * 10**10 + t.astype("int64")
    vals, idx = asof(key, d.yes.values, q.ravel())
    same = d.market.values[idx] == np.repeat(mkts, N_UD)
    vals[~same] = np.nan
    P = vals.reshape(len(mkts), N_UD).astype("float32")
    lo = mkts.astype("int64") * 10**10 + (end - dur).astype("int64")
    hi = mkts.astype("int64") * 10**10 + end.astype("int64")
    n_win = np.searchsorted(key, hi, side="right") - np.searchsorted(key, lo, side="left")
    out = pd.DataFrame(P, columns=[f"p{i}" for i in range(N_UD)])
    out.insert(0, "n_window", n_win)
    out.insert(0, "dur_min", (dur / 60).astype(int))
    out.insert(0, "market", mkts)
    return out


def main(mode, buckets):
    global UD_SRC, STEP, OFFSETS, N_UD
    os.makedirs("tmp/paths", exist_ok=True)
    end_ts = end_times()
    if mode in ("cx", "cxmoves"):
        UD_SRC = "tmp/buckets_cx"
        s3.OUT_ROOT = "tmp/events_cx"
        mode = {"cx": "ud", "cxmoves": "udmoves"}[mode]
        tag = "cx"
    else:
        tag = mode
    if mode == "finemoves":
        STEP, OFFSETS = 60, np.arange(-60, 481)
        mode, tag = "moves", "fine"
    if mode == "cxfine":
        N_UD = 120
        UD_SRC = "tmp/buckets_cx"
        mode, tag = "ud", "cxfine"
    if mode == "udmoves":
        s2.SRC = UD_SRC
        s2.LIFE_CUT_START, s2.LIFE_CUT_END, s2.EDGE, s2.CLIP = CX["cut_start"], CX["cut_end"], CX["edge"], CX["clip"]
        s3.ENTRY_N, s3.ENTRY_MAX = CX["next_n"], CX["next_max"]
        s3.main(CX["slot"], buckets)
        return
    dur_of = None
    if mode == "ud":
        t = pd.read_csv("data/market_tags.csv", dtype=str)
        t = t[t.tags.str.contains("up-or-down", na=False)]
        dtag = t.tags.str.extract(r"(?:^|;)(5M|15M|1H|4h|daily)(?:;|$)", expand=False)
        dur_of = pd.Series(dtag.map(DUR).values, index=t.market_id.astype(int).values).dropna()
    for k in buckets:
        t0 = time.time()
        out = move_paths(k, end_ts) if mode == "moves" else ud_paths(k, end_ts, dur_of)
        if out is None:
            continue
        out.to_parquet(f"tmp/paths/{tag}_{k:02d}.parquet", index=False)
        print(f"{tag} bucket {k}: {len(out):,} paths, {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main(sys.argv[1], [int(x) for x in sys.argv[2:]])
