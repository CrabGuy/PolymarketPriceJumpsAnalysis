"""
Stage 6: market microstructure per market, and side-specific execution prices per big move.

Input: tmp/buckets (event-market trades, stage 1) and tmp/events3/900/e<k>.parquet (the
15-min moves of stage 3). Per market, only trades inside the stage-2 window (the middle of
the market's life) are used.

Per market -> tmp/micro/k<k>.parquet:
  trades, usd, takers        totals before the cut
  gini, hhi, top1, top10     concentration of taker volume across wallets: Gini of USD per
                             taker, Herfindahl (sum of squared shares), largest wallet's share,
                             share of the top 10% of wallets
  bars                       active 15-min bars
  kyle_lambda, kyle_r2, kyle_n
                             OLS slope of a bar's log-odds change (VWAP basis, previous active
                             bar at most 2 h earlier) on its signed taker flow in $1,000:
                             Kyle's lambda, as estimated on Polymarket by Tsang & Yang
  vr4                        variance ratio of 4-bar to 1-bar log-odds changes over the
                             sequence of active bars (< 1 = changes reverse, > 1 = they drift)
  roll                       Roll (1984) spread from trade-to-trade YES price changes
  spread_med, spread_n       median gap between taker-buy and taker-sell YES VWAP within the
                             same minute, over minutes with both
  two_sided                  mean over bars of 1 - |B - S| / (B + S), B/S = taker buy/sell USD

Per big move -> tmp/micro/x<k>.parquet (market, t_close, plus):
  fade_px, fade_n, fade_delay      VWAP of the first ENTRY_N trades after the bar close (within
                                   ENTRY_MAX) whose taker traded AGAINST the move (sold YES
                                   after an up move): what a taker fading the move got
  follow_px, follow_n, follow_delay   the same for trades WITH the move
  fade_usd_15m, fade_usd_1h, follow_usd_1h   USD traded on that side after the close

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
LAMBDA_GAP_BARS = 8          # Kyle's lambda: consecutive active bars at most 2 h apart
BAR = 900
ENTRY_N = 5
ENTRY_MAX = 3600
MIN_BARS_KYLE = 20
MIN_BARS_VR = 40


def concentration(dc):
    tv = dc.groupby(["market", "taker"], sort=False).usd.sum().reset_index()
    tv = tv[tv.usd > 0].sort_values(["market", "usd"], kind="mergesort").reset_index(drop=True)
    g = tv.groupby("market", sort=False)
    n = g.usd.transform("size").values
    S = g.usd.transform("sum").values
    r = g.cumcount().values + 1
    tv["ix"] = r * tv.usd.values
    tv["sh2"] = (tv.usd.values / S) ** 2
    tv["top10"] = np.where(n - r + 1 <= np.ceil(0.1 * n), tv.usd.values, 0.0)
    a = tv.groupby("market").agg(takers=("usd", "size"), S=("usd", "sum"), mx=("usd", "max"),
                                 ix=("ix", "sum"), hhi=("sh2", "sum"), top10=("top10", "sum"))
    out = pd.DataFrame(index=a.index)
    out["takers"] = a.takers
    out["gini"] = 2 * a.ix / (a.takers * a.S) - (a.takers + 1) / a.takers
    out["hhi"] = a.hhi
    out["top1"] = a.mx / a.S
    out["top10"] = a.top10 / a.S
    return out


def group_ols(m, x, y, min_n):
    df = pd.DataFrame({"m": m, "x": x, "y": y, "xx": x * x, "xy": x * y, "yy": y * y})
    s = df.groupby("m").agg(n=("x", "size"), x=("x", "sum"), y=("y", "sum"), xx=("xx", "sum"),
                            xy=("xy", "sum"), yy=("yy", "sum"))
    sxx = s.xx - s.x ** 2 / s.n
    sxy = s.xy - s.x * s.y / s.n
    syy = s.yy - s.y ** 2 / s.n
    ok = (s.n >= min_n) & (sxx > 0) & (syy > 0)
    return pd.DataFrame({"kyle_lambda": np.where(ok, sxy / sxx.where(sxx > 0), np.nan),
                         "kyle_r2": np.where(ok, sxy ** 2 / (sxx * syy).where(ok), np.nan),
                         "kyle_n": s.n}, index=s.index)


def market_stats(d, bars):
    w = bars.groupby("market")[["start", "cut"]].first()
    lo, hi = d.market.map(w.start).values - BAR, d.market.map(w.cut).values
    dc = d[(d.ts.values >= lo) & (d.ts.values < hi)]       # trades in the window's bars
    res = pd.DataFrame(index=w.index)
    tot = dc.groupby("market").agg(trades=("usd", "size"), usd=("usd", "sum"))
    res = res.join(tot).join(concentration(dc))
    res["bars"] = bars.groupby("market").size()

    # Kyle's lambda and the variance ratio on 15-min bars (VWAP basis)
    L = s2.logit(bars.vwap.values)
    mk = bars.market.values
    same = np.r_[False, mk[1:] == mk[:-1]]
    close = same & np.r_[False, np.diff(bars.bar.values) <= LAMBDA_GAP_BARS]
    dL = np.where(same, L - np.r_[np.nan, L[:-1]], np.nan)
    k = close & np.isfinite(dL)
    res = res.join(group_ols(mk[k], bars.flow.values[k] / 1000.0, dL[k], MIN_BARS_KYLE))
    b = pd.DataFrame({"m": mk[same], "d": dL[same]})
    b["c"] = b.groupby("m").d.cumsum()
    b["r4"] = b.c - b.groupby("m").c.shift(4)
    v1 = b.groupby("m").d.agg(["var", "size"])
    v4 = b.groupby("m").r4.var()
    res["vr4"] = (v4 / (4 * v1["var"])).where(v1["size"] >= MIN_BARS_VR)
    # USD-weighted: 2 * sum(min(B, S)) / sum(B + S) over the market's bars
    tw = pd.DataFrame({"m": bars.market.values, "mn": np.minimum(bars.buy.values, bars.sell.values),
                       "tot": (bars.buy + bars.sell).values}).groupby("m").sum()
    res["two_sided"] = 2 * tw.mn / tw.tot.where(tw.tot > 0)

    # Roll spread on trade-to-trade YES changes
    m2 = dc.market.values
    p = dc.yes.values.astype("float64")
    dp = np.where(np.r_[False, m2[1:] == m2[:-1]], p - np.r_[np.nan, p[:-1]], np.nan)
    lag = np.where(np.r_[False, m2[1:] == m2[:-1]], np.r_[np.nan, dp[:-1]], np.nan)
    ok = np.isfinite(dp) & np.isfinite(lag)
    cv = pd.DataFrame({"m": m2[ok], "a": dp[ok], "b": lag[ok], "ab": dp[ok] * lag[ok]}).groupby("m").agg(
        n=("a", "size"), a=("a", "sum"), b=("b", "sum"), ab=("ab", "sum"))
    cov = (cv.ab - cv.a * cv.b / cv.n) / (cv.n - 1).where(cv.n > 1)
    res["roll"] = 2 * np.sqrt((-cov).clip(lower=0))

    # buy-sell gap within the same minute
    q = dc.assign(minute=dc.ts // 60).groupby(["market", "minute", "up"], sort=False).agg(
        pv=("pv", "sum"), usd=("usd", "sum")).reset_index()
    q["px"] = q.pv / q.usd.where(q.usd > 0)
    w = q.pivot_table(index=["market", "minute"], columns="up", values="px").dropna()
    if len(w) and (1 in w.columns) and (-1 in w.columns):
        gap = (w[1] - w[-1]).groupby(level=0)
        res["spread_med"] = gap.median()
        res["spread_n"] = gap.size()
    for c in res.columns:
        if res[c].dtype == "float64":
            res[c] = res[c].astype("float32")
    return res.reset_index().rename(columns={"index": "market"})


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


def process(k, end_ts):
    files = sorted(glob.glob(f"{s2.SRC}/b{k:02d}_*.parquet"))
    if not files:
        return None, None
    d = pd.concat([pd.read_parquet(f, columns=["market", "ts", "yes", "usd", "up", "taker"]) for f in files],
                  ignore_index=True)
    n_per = d.market.value_counts()
    d = d[d.market.isin(n_per[n_per >= s2.MIN_TRADES].index)]
    d = d.sort_values(["market", "ts"], kind="mergesort").reset_index(drop=True)
    d["bar"] = d.ts // BAR
    d["pv"] = d.yes * d.usd
    d["flow"] = d.usd * d.up
    d["buy"] = np.where(d.up.values > 0, d.usd.values, 0.0)
    d["sell"] = np.where(d.up.values < 0, d.usd.values, 0.0)
    g = d.groupby(["market", "bar"], sort=False)
    bars = g.agg(yes=("yes", "last"), pv=("pv", "sum"), usd=("usd", "sum"), flow=("flow", "sum"),
                 buy=("buy", "sum"), sell=("sell", "sum")).reset_index()
    bars["vwap"] = np.where(bars.usd > 0, bars.pv / bars.usd.where(bars.usd > 0), bars.yes)
    bars["t_close"] = (bars.bar + 1) * BAR
    bars = s2.window(bars)
    ms = market_stats(d, bars)
    ef = f"tmp/events3/900/e{k:02d}.parquet"
    xp = None
    if os.path.exists(ef):
        e = pd.read_parquet(ef, columns=["market", "t_close", "move"])
        xp = move_prices(d, e)
    return ms, xp


def main(buckets):
    os.makedirs(OUT, exist_ok=True)
    mk = pd.read_parquet(s2.MARKETS, columns=["id", "end_date"])
    mk = mk[pd.to_numeric(mk.id, errors="coerce").notna()]
    secs = (mk.end_date - pd.Timestamp(0, tz="UTC")).dt.total_seconds()
    end_ts = pd.Series(secs.values, index=mk.id.astype(int).values)
    end_ts = end_ts[~end_ts.index.duplicated()]
    for k in buckets:
        t0 = time.time()
        ms, xp = process(k, end_ts)
        if ms is None:
            continue
        ms.to_parquet(f"{OUT}/k{k:02d}.parquet", index=False)
        if xp is not None:
            xp.to_parquet(f"{OUT}/x{k:02d}.parquet", index=False)
        print(f"micro bucket {k}: {len(ms):,} markets, {0 if xp is None else len(xp):,} moves, "
              f"{time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main([int(x) for x in sys.argv[1:]])
