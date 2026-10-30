"""
Round 5, part 4: momentum in crypto up/down markets, explored fully.

Input (remote/s1x_bucket.py -> s4_paths.py cx / cxmoves):
  local_data/r05/events_cx/e*.parquet   1-min price jumps (VWAP basis, >= 13 points, cut
                                        only at the settle moment: the 10% window of the
                                        event markets changes these results, see
                                        explore/r09_crypto.py; next trades within 5 min) in every
                                        bitcoin/ether/solana/xrp 15-min market and every
                                        bitcoin/ether 5-min and 1-hour market
  local_data/r05/cx_paths/cx_*.parquet  each market's YES price at 30 evenly spaced times
                                        over its window (last trade at or before each time)
Overshoot as in round 4 (outcome-based, share of the move), with the calibration
baseline from the pre-move prices of each (asset, market length).

  1  by asset, market length and number of takers
  2  by month (Sep 2025 - May 2026), hour of day, weekend, minutes left, move size
  3  confirmation by related markets: did the same coin's market of another length, and
     the other coin's market of the same length, move the same way in the same minute?
     (Their price change over the move's 1-min bar, read from their 30-point paths.)
  4  what a trader could do: follow (or fade) the move at the next trades, hold to the end.

Usage: python explore/r05_updown.py [raw]
"""
import glob
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "explore")
from r02_persistence import MIN_PTS, outcomes, sigmoid  # noqa: E402
from r03_robustness import BINS  # noqa: E402

OUT = "local_data/r05/"
DUR = {"5M": 5, "15M": 15, "1H": 60}
OTHER = {"bitcoin": "ethereum", "ethereum": "bitcoin", "solana": "bitcoin", "xrp": "bitcoin"}
EVENTS = OUT + "events_cx/60/e*.parquet"
PATHS = OUT + "cx_paths/cx_*.parquet"
CONF = 0.1             # a related market "moved" if its log-odds changed by at least this


def share(x, col):
    return x[col].sum() / x.absdp.sum()


def boot(x, col, n=200):
    g = x.groupby("market").agg(a=(col, "sum"), b=("absdp", "sum"))
    rng = np.random.default_rng(4)
    a, b = g.a.values, g.b.values
    r = [a[i].sum() / b[i].sum() for i in (rng.integers(0, len(g), len(g)) for _ in range(n))]
    return np.percentile(r, [2.5, 97.5])


def market_info():
    t = pd.read_csv("local_data/market_tags.csv", dtype=str)
    t = t[t.tags.str.contains("up-or-down", na=False)]
    info = pd.DataFrame({"market": t.market_id.astype(int).values,
                         "dur": t.tags.str.extract(r"(?:^|;)(5M|15M|1H)(?:;|$)", expand=False).values,
                         "asset": t.tags.str.extract(r"(?:^|;)(bitcoin|ethereum|solana|xrp)(?:;|$)", expand=False).values})
    info = info.dropna()
    mk = pd.read_parquet("local_data/markets_final.parquet", columns=["id", "end_date"])
    mk = mk[pd.to_numeric(mk.id, errors="coerce").notna()].assign(market=lambda x: x.id.astype(int)).drop_duplicates("market")
    info = info.merge(mk[["market", "end_date"]], on="market")
    info["end"] = (info.end_date - pd.Timestamp(0, tz="UTC")).dt.total_seconds().astype("int64")
    info["dur_s"] = info.dur.map(DUR) * 60
    info["start"] = info.end - info.dur_s
    return info.drop(columns="end_date")


def load_paths(info):
    p = pd.concat([pd.read_parquet(f) for f in glob.glob(PATHS)], ignore_index=True)
    p = p.merge(info, on="market")
    p = p[p.dur_min == p.dur_s // 60]
    return p.drop_duplicates(["asset", "dur", "end"]).set_index(["asset", "dur", "end"])


def price_at(paths, asset, dur, end, t):
    """Each related market's last price at or before time t, read from its 30-point path."""
    key = pd.MultiIndex.from_arrays([asset, dur, end])
    sub = paths.reindex(key)
    P = sub.filter(regex=r"^p\d+$").values
    start = sub.start.values
    step = sub.dur_s.values / 30
    i = np.floor((t - start) / step).astype("float64")        # i-th point (1..30) is at start + i*step
    ok = np.isfinite(i) & (i >= 1) & (i <= 30)
    j = np.where(ok, i - 1, 0).astype(int)
    v = P[np.arange(len(P)), j] if len(P) else np.array([])
    return np.where(ok, v, np.nan), sub.n_window.values


def logit(p):
    p = np.clip(p, 0.01, 0.99)
    return np.log(p / (1 - p))


def load_moves(info, min_pts=MIN_PTS, min_logit=0.0):
    e = pd.concat([pd.read_parquet(f) for f in glob.glob(EVENTS)], ignore_index=True)
    e = e.merge(info, on="market")
    e["outcome"] = e.market.map(outcomes())
    e = e[e.outcome.notna()].copy()
    e["L_pre"] = logit(e.y_pre)
    e["p_close"] = sigmoid(e.L_pre + e.move)
    e["sgn"] = np.sign(e.move)
    e["absdp"] = (e.p_close - e.y_pre).abs()
    e["tg"] = pd.cut(e.takers, [0, 1, 3, np.inf], labels=["1", "2-3", "4+"])
    e["min_left"] = (e.end - e.t_close) / 60
    e["stage"] = pd.cut(e.min_left / (e.dur_s / 60), [-1e-9, 0.25, 0.5, 0.75, 1.0001],
                        labels=["last quarter", "third", "second", "first quarter"])
    e["month"] = pd.to_datetime(e.t_close, unit="s").dt.to_period("M").astype(str)
    e["hour"] = pd.to_datetime(e.t_close, unit="s").dt.hour
    e["weekend"] = pd.to_datetime(e.t_close, unit="s").dt.dayofweek >= 5
    base = e.assign(bin=pd.cut(e.y_pre, BINS)).groupby(["asset", "dur", "bin"], observed=True).apply(
        lambda x: (x.outcome - x.y_pre).mean())

    def osh(p):
        b = pd.Series(list(zip(e.asset, e.dur, pd.cut(p, BINS)))).map(base).astype(float).values
        return -((e.outcome - p) - b) * e.sgn

    e["oc"] = osh(e.p_close)
    e["oe"] = osh(e.entry_vwap)
    big = e[(e.absdp >= min_pts) & (e.move.abs() >= min_logit) & e.oc.notna()].copy()
    return big


def confirm(big, paths):
    t1, t0 = big.t_close.values, big.t_close.values - 60
    cols = {}
    # the same coin, other market lengths
    for d2, sec in (("5M", 300), ("15M", 900), ("1H", 3600)):
        end2 = (np.ceil(t1 / sec) * sec).astype("int64")
        a1, _ = price_at(paths, big.asset.values, np.full(len(big), d2), end2, t1)
        a0, _ = price_at(paths, big.asset.values, np.full(len(big), d2), end2, t0)
        d = (logit(a1) - logit(a0)) * big.sgn.values
        cols[f"same coin {d2}"] = np.where(big.dur.values == d2, np.nan, d)
    # the other coin, same market length
    other = big.asset.map(OTHER).values
    b1, _ = price_at(paths, other, big.dur.values, big.end.values, t1)
    b0, _ = price_at(paths, other, big.dur.values, big.end.values, t0)
    cols["other coin"] = (logit(b1) - logit(b0)) * big.sgn.values
    c = pd.DataFrame(cols, index=big.index)
    big = big.join(c)
    # one summary per move: the same coin's other market length (the faster one when there is a choice)
    same = big["same coin 5M"].where(big.dur != "5M", big["same coin 15M"])
    big["same coin"] = same

    def lab(x):
        return np.select([x.isna(), x >= CONF, x <= -CONF], ["no data", "moved with it", "moved against"], "did not move")

    big["conf_same"] = lab(big["same coin"])
    big["conf_other"] = lab(big["other coin"])
    return big


def main():
    info = market_info()
    big = load_moves(info)
    print(f"big 1-min moves: {len(big):,} in {big.market.nunique():,} markets "
          f"({pd.to_datetime(big.t_close.min(), unit='s'):%Y-%m-%d} to {pd.to_datetime(big.t_close.max(), unit='s'):%Y-%m-%d})")
    # 1. asset x length x takers
    rows = []
    for (a, d, tg), x in big.groupby(["asset", "dur", "tg"], observed=True):
        lo, hi = boot(x, "oc")
        rows.append({"asset": a, "dur": d, "takers": tg, "moves": len(x), "markets": x.market.nunique(),
                     "close": share(x, "oc"), "lo": lo, "hi": hi,
                     "next trades": share(x[x.oe.notna()], "oe"), "median delay s": x.entry_delay.median()})
    r1 = pd.DataFrame(rows)
    print("\n[1] overshoot by coin, market length, takers:")
    print(r1.round(3).to_string(index=False))
    # 2. stability and timing (15-min markets, all coins)
    q = big[big.dur == "15M"]
    tabs = {}
    for name, key in (("month", "month"), ("hour", "hour"), ("weekend", "weekend"), ("stage", "stage")):
        tabs[name] = q.groupby([key, "tg"], observed=True).apply(
            lambda x: share(x, "oc") if len(x) >= 300 else np.nan).unstack()
        print(f"\n[2] 15-min markets by {name} (overshoot at close; columns = takers):")
        print(tabs[name].round(3).to_string())
    big["size"] = pd.cut(big.absdp, [0.1, 0.15, 0.25, 0.4, 1], labels=["10-15", "15-25", "25-40", ">40"])
    tabs["size"] = big.groupby(["size", "tg"], observed=True).apply(share, "oc").unstack()
    print("\n[2] by jump size (points):\n", tabs["size"].round(3).to_string())
    # 3. confirmation
    paths = load_paths(info)
    big = confirm(big, paths)
    rows = []
    for which in ("conf_same", "conf_other"):
        for (c, tg), x in big.groupby([which, "tg"], observed=True):
            if c == "no data":
                continue
            lo, hi = boot(x, "oc")
            rows.append({"related market": "same coin, other length" if which == "conf_same" else "other coin, same length",
                         "it": c, "takers": tg, "moves": len(x), "close": share(x, "oc"), "lo": lo, "hi": hi,
                         "next trades": share(x[x.oe.notna()], "oe")})
    r3 = pd.DataFrame(rows)
    print("\n[3] overshoot by what the related market did in the same minute:")
    print(r3.round(3).to_string(index=False))
    print("share of moves confirmed by the same coin's other market, by takers:")
    print(pd.crosstab(big.tg, big.conf_same, normalize="index").round(3).to_string())
    # 4. follow the move at the next trades, hold to the end (per $ staked; raw, before fees)
    f = big[big.entry_vwap.notna()].copy()
    stake = np.where(f.sgn > 0, f.entry_vwap, 1 - f.entry_vwap)
    f["follow"] = f.sgn * (f.outcome - f.entry_vwap) / stake
    r4 = f.groupby(["dur", "tg"], observed=True).apply(lambda x: pd.Series({
        "moves": len(x), "follow return per $": x.follow.mean(), "win rate": (x.follow > 0).mean()})).reset_index()
    r4m = f[f.dur == "15M"].groupby(["month", "tg"], observed=True).follow.mean().unstack()
    print("\n[4] follow the move at the next trades, hold to the end (raw, per $):")
    print(r4.round(3).to_string(index=False))
    print(r4m.round(3).to_string())

    r1.to_csv(OUT + "r05_ud_asset.csv", index=False)
    for k, v in tabs.items():
        v.to_csv(OUT + f"r05_ud_by_{k}.csv")
    r3.to_csv(OUT + "r05_ud_confirm.csv", index=False)
    r4.to_csv(OUT + "r05_ud_follow.csv", index=False)
    r4m.to_csv(OUT + "r05_ud_follow_month.csv")
    big.to_parquet(OUT + "r05_ud_moves.parquet", index=False)
    return big


def raw_tables():
    """Overshoot without a calibration baseline (price vs final outcome only), at the bar
    close and at the next trades, with market-resampled 95% intervals. In up/down markets
    the pre-move calibration of 5-min markets is odd at extreme prices (+-0.11), which
    distorts the baseline version; the raw version is the cleaner read here."""
    b = pd.read_parquet(OUT + "r05_ud_moves.parquet")
    b = b[b.entry_vwap.notna()].copy()
    b["raw_c"] = b.sgn * (b.p_close - b.outcome)
    b["raw_e"] = b.sgn * (b.entry_vwap - b.outcome)
    rows = []
    for keys, x in b.groupby(["dur", "tg"], observed=True):
        if len(x) < 500:
            continue
        c, e = boot(x, "raw_c"), boot(x, "raw_e")
        rows.append({"dur": keys[0], "takers": keys[1], "moves": len(x), "close": share(x, "raw_c"), "close lo": c[0],
                     "close hi": c[1], "next": share(x, "raw_e"), "next lo": e[0], "next hi": e[1],
                     "median delay s": x.entry_delay.median()})
    by_len = pd.DataFrame(rows)
    rows = []
    for keys, x in b[b.conf_other != "no data"].groupby(["conf_other", "tg"], observed=True):
        c, e = boot(x, "raw_c"), boot(x, "raw_e")
        rows.append({"other coin": keys[0], "takers": keys[1], "moves": len(x), "close": share(x, "raw_c"),
                     "close lo": c[0], "close hi": c[1], "next": share(x, "raw_e"), "next lo": e[0], "next hi": e[1]})
    conf = pd.DataFrame(rows)
    mon = b[b.dur == "15M"].groupby(["month", "tg"], observed=True).apply(
        lambda x: share(x, "raw_c") if len(x) >= 300 else np.nan).unstack()
    print(by_len.round(3).to_string(index=False))
    print(conf.round(3).to_string(index=False))
    print(mon.round(3).to_string())
    by_len.to_csv(OUT + "r05_ud_raw_len.csv", index=False)
    conf.to_csv(OUT + "r05_ud_raw_confirm.csv", index=False)
    mon.to_csv(OUT + "r05_ud_raw_month.csv")


if __name__ == "__main__":
    if sys.argv[1:] == ["raw"]:
        raw_tables()
    else:
        main()
        raw_tables()
