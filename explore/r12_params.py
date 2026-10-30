"""
Round 12: the elbow (knee) of every remaining parameter, on the jumps defined by the joint
search (explore/r12_joint.py). Each curve is drawn over the range given below; the knee is
the Kneedle point (explore/elbow.knee). Run after the main pipeline (r03 to r10).

  statistics
    sample      spread of the overshoot over 20 redraws of the random-slot set,
                vs its size (% of all slots, 0.1-5)
    resamples   spread over 40 repeats of the 2.5% bound of the overshoot range,
                vs the number of resamples (10-1,000)
    bins        share of the calibration error (outcome - price) at random slots explained by
                the bin means, vs the number of price bins (2-100)
  groups
    crowd       overshoot of the jumps with at least k traders, vs k (1-30)
    money       overshoot of the jumps with at least $x in their slot, vs x (log scale, $1-$100k)
    wallet_min  wallets kept vs the minimum number of single-trader jumps per wallet (2-50)
    control_bins  F2: the controlled 4+ vs 1 trader gap vs the number of quantile bins of each
                continuous control (2-10)
    offset_hi   F4: overshoot of crowd jumps whose offset is at least x, vs x (0-1.5)
    offset_lo   F4: overshoot of crowd jumps whose offset is below x, vs x (0-1)
  betting (F5)
    band        spread of the per-bet returns vs the band edge e (bets only on jumps that
                start inside [e, 1 - e]; 0-0.2)
    trim        trimmed mean return vs the share trimmed at each end (0-10%)
  market structure (F6)
    min_slots   markets kept vs the minimum number of slots with trades (5-200)
    vr_lag      median variance ratio vs its lag q (2-16)
    spread_win  share of windows with trades on both sides vs the window (10 s - 10 min)
    tag_min     tags kept vs the minimum number of markets per tag (10-2,000, log scale)
  crypto (F8)
    moved       share of related markets that moved vs the threshold (log-odds 0.01-1)
    cx_points   error of a path drawn with n points vs the 120-point path, vs n (divisors of 120)
    cx_min_trades  crypto markets kept vs the minimum number of trades (1-100)
  next trades sign (F10)
    follow_up   overshoot of jumps with a new trade within x minutes vs x (1-60)

Outputs local_data/r12/params_curves.csv and params_knees.csv.
Usage: python explore/r12_params.py [name ...]
"""
import glob
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "explore")
from r02_persistence import MARKETS as MARKETS_FILE, outcomes  # noqa: E402
from r03_robustness import cat_baseline, overshoot_cat  # noqa: E402
from elbow import knee  # noqa: E402

OUT = "local_data/r12"
MIN_N = 1000          # a point of a share-of-jumps curve needs at least this many jumps
MAIN = "local_data/r03_big_moves_main.parquet"


def big():
    return pd.read_parquet(MAIN)


def randoms():
    r = pd.concat([pd.read_parquet(f) for f in glob.glob("local_data/r03_events/1800/r*.parquet")], ignore_index=True)
    r["outcome"] = r.market.map(outcomes())
    r = r[r.outcome.notna()].copy()
    tags = pd.read_csv("local_data/market_tags.csv", dtype=str)
    from r02_persistence import category
    r["cat"] = r.market.map(pd.Series(category(tags.tags).values, index=tags.market_id.astype(int).values)).fillna("other")
    return r


def share(x, col="oc"):
    return x[col].sum() / x.absdp.sum()


def shares(sets, xs, col="oc"):
    """Overshoot share (%) of each subset, keeping only the points with at least MIN_N jumps."""
    keep = [i for i, z in enumerate(sets) if len(z) >= MIN_N]
    return np.asarray(xs)[keep], np.array([share(sets[i], col) * 100 for i in keep])


# ---------------------------------------------------------------- statistics

def c_sample(b, r, reps=20):
    rng = np.random.default_rng(1)
    x = np.array([.1, .25, .5, .75, 1, 1.5, 2, 3, 4, 5])
    y = []
    for s in x:
        v = [overshoot_cat(b, b.p_close, cat_baseline(r.iloc[rng.integers(0, len(r), int(len(r) * s / 5))])).sum()
             / b.absdp.sum() for _ in range(reps)]
        y.append(np.nanstd(v) * 100)
    return x, np.array(y)


def c_resamples(b, reps=40):
    g = b.groupby("market")[["oc", "absdp"]].sum()
    a, d = g.oc.values, g.absdp.values
    rng = np.random.default_rng(0)
    x = np.array([10, 20, 30, 50, 75, 100, 150, 200, 300, 500, 750, 1000])
    y = []
    for n in x:
        lows = [np.percentile(a[i].sum(1) / d[i].sum(1), 2.5)
                for i in (rng.integers(0, len(g), (n, len(g))) for _ in range(reps))]
        y.append(np.std(lows) * 100)
    return x, np.array(y)


def c_bins(r):
    err = (r.outcome - r.vwap).values
    sst = ((err - err.mean()) ** 2).sum()
    x = np.array([2, 3, 4, 5, 8, 10, 15, 20, 25, 30, 40, 50, 100])
    y = []
    for k in x:
        b = pd.cut(r.vwap, np.linspace(0, 1, k + 1), include_lowest=True)
        m = pd.Series(err).groupby([r.cat.values, b.values], observed=True).transform("mean").values
        y.append(1 - ((err - m) ** 2).sum() / sst)
    return x, np.array(y)


# ---------------------------------------------------------------- groups

def c_crowd(b):
    x = np.arange(1, 31)
    return shares([b[b.takers >= k] for k in x], x)


def c_money(b):
    x = np.array([1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000, 100000])
    return shares([b[b.usd >= v] for v in x], x)


def c_wallet_min(b):
    n = b[b.takers == 1].groupby("taker1").size()
    x = np.arange(2, 51)
    return x, np.array([(n >= k).sum() for k in x])


def c_offset(kind):
    import r07_siblings as rs
    s = pd.concat([pd.read_parquet(f, columns=["mv_market", "t_close", "p_before", "p_close"])
                   for f in glob.glob(rs.SRC + "sib/s*.parquet")], ignore_index=True)
    s["d"] = (s.p_close - s.p_before).where(s.p_close.notna(), 0.0)
    s["n"] = s.p_close.notna()
    g = s.groupby(["mv_market", "t_close"])[["d", "n"]].sum().reset_index().rename(columns={"mv_market": "market"})
    t = pd.read_parquet("local_data/r04_tradable.parquet", columns=["market", "t_close", "y_pre", "p_close", "absdp", "takers", "oq"])
    mk = pd.read_parquet("local_data/markets_final.parquet", columns=["id", "neg_risk"])
    mk = mk[pd.to_numeric(mk.id, errors="coerce").notna()].assign(market=lambda z: z.id.astype(int)).drop_duplicates("market")
    t = t.merge(mk[["market", "neg_risk"]], on="market")
    x = t[(t.neg_risk == 1) & t.oq.notna()].merge(g, on=["market", "t_close"])
    x = x[(x.n > 0)]
    from r02_persistence import K_CROWD
    x = x[x.takers >= K_CROWD]
    x["phi"] = -x.d / (x.p_close - x.y_pre)
    if kind == "hi":
        v = np.round(np.arange(0, 1.51, .05), 2)
        return shares([x[x.phi >= c] for c in v], v, "oq")
    v = np.round(np.arange(0.05, 1.01, .05), 2)
    return shares([x[x.phi < c] for c in v], v, "oq")


def c_control_bins(t):
    import r05_event_markets as em
    x = np.arange(2, 11)
    y = []
    for k in x:
        em.CONTROL_BINS = int(k)
        res, _ = em.part_a(t, quiet=True, boot=False)
        r = res[res.factor == "takers"]
        y.append(-r[r.level.str.endswith("+")].effect.iloc[0] * 100)
    return x, np.array(y)


# ---------------------------------------------------------------- betting (F5)

def fade_moves():
    import r06_fade as rf
    t = pd.read_parquet("local_data/r04_tradable.parquet")
    t = t[t.oq.notna() & t.oqe.notna()].merge(rf.micro_moves(), on=["market", "t_close"], how="inner")
    t = t[t.fade_px.notna() & t.follow_px.notna()].copy()
    return rf.add_returns(t, rf.calib())


def c_band(t):
    x = np.round(np.arange(0, 0.201, 0.01), 2)
    return x * 100, np.array([t[t.y_pre.between(e, 1 - e)].n_taker.std() for e in x])


def c_trim(t, band):
    t = t[t.y_pre.between(band, 1 - band)]
    x = np.array([0, .25, .5, 1, 1.5, 2, 2.5, 3, 4, 5, 7.5, 10])
    y = []
    for q in x:
        lo, hi = t.n_taker.quantile([q / 100, 1 - q / 100])
        y.append(t.n_taker.clip(lo, hi).mean() * 100)
    return x, np.array(y)


# ---------------------------------------------------------------- market structure (F6)

def micro():
    return pd.concat([pd.read_parquet(f) for f in glob.glob("local_data/r06/micro/k*.parquet")], ignore_index=True)


def c_min_slots(m):
    x = np.array([5, 10, 15, 20, 25, 30, 40, 50, 60, 80, 100, 150, 200])
    return x, np.array([(m.bars >= k).sum() for k in x])


def c_vr_lag(m, min_slots):
    m = m[m.vr_n >= min_slots]
    x = np.array([2, 3, 4, 6, 8, 12, 16])
    return x, np.array([m[f"vr{q}"].median() for q in x])


def c_spread_win(m):
    x = np.array([10, 30, 60, 120, 300, 600])
    return x, np.array([m[f"spread_n_{w}"].sum() / m[f"spread_w_{w}"].sum() for w in x])


def c_tag_min_jumps(b):
    t = pd.read_csv("local_data/market_tags.csv", dtype=str)
    t = t[t.market_id.astype(int).isin(b.market.unique())]
    n = t.tags.str.split(";").explode()
    n = n[~n.isin(["all", "hide-from-new", "games"])].value_counts()
    x = np.array([10, 20, 50, 100, 150, 200, 300, 500, 750, 1000, 1500, 2000])
    return x, np.array([(n >= k).sum() for k in x])


def c_tag_min():
    t = pd.read_csv("local_data/market_tags.csv", dtype=str)
    n = t.tags.str.split(";").explode().value_counts()
    x = np.array([10, 20, 50, 100, 150, 200, 300, 500, 750, 1000, 1500, 2000])
    return x, np.array([(n >= k).sum() for k in x])


# ---------------------------------------------------------------- crypto (F8)

def c_moved():
    import r05_updown as ud
    info = ud.market_info()
    big_ = ud.load_moves(info)
    paths = ud.load_paths(info)
    t1, t0 = big_.t_close.values, big_.t_close.values - 60
    other = big_.asset.map(ud.OTHER).values
    a, _ = ud.price_at(paths, other, big_.dur.values, big_.end.values, t1)
    b, _ = ud.price_at(paths, other, big_.dur.values, big_.end.values, t0)
    d = np.abs(ud.logit(a) - ud.logit(b))
    d = d[np.isfinite(d)]
    x = np.array([0.01, 0.02, 0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.75, 1.0])
    return x, np.array([(d >= c).mean() * 100 for c in x])


def c_cx_points():
    p = pd.concat([pd.read_parquet(f) for f in glob.glob("local_data/r12/cxfine/cxfine_*.parquet")], ignore_index=True)
    P = p.filter(regex=r"^p\d+$").values.astype(float)
    P = P[np.isfinite(P).all(1)]
    x = np.array([4, 5, 6, 8, 10, 12, 15, 20, 24, 30, 40, 60, 120])
    y = []
    for n in x:
        idx = (np.arange(1, n + 1) * (120 // n)) - 1          # every (120/n)-th point, the last one kept
        coarse = P[:, idx]
        filled = np.repeat(coarse, 120 // n, axis=1)           # each point holds until the next
        y.append(np.abs(filled - P).mean() * 100)
    return x, np.array(y)


def c_cx_min_trades():
    p = pd.concat([pd.read_parquet(f, columns=["n_window"]) for f in glob.glob("local_data/r12/cxfine/cxfine_*.parquet")])
    x = np.array([1, 2, 5, 10, 15, 20, 30, 50, 75, 100])
    return x, np.array([(p.n_window >= k).sum() for k in x])


# ---------------------------------------------------------------- outcome and Kyle's lambda gap

def c_outcome():
    """Event markets only: the crypto up/down markets have their own curve (c_cx_outcome)."""
    mk = pd.read_parquet("local_data/markets_final.parquet", columns=["id", "outcome_prices"])
    t = pd.read_csv("local_data/market_tags.csv", dtype=str)
    ud = set(t[t.tags.str.contains("up-or-down", na=False)].market_id)
    mk = mk[~mk.id.astype(str).isin(ud)]
    f = pd.to_numeric(mk.outcome_prices.str.strip("[]").str.split(",").str[0].str.strip(" '\""), errors="coerce")
    x = np.array([.5, .6, .7, .8, .9, .95, .97, .98, .99, .995, .999, .9999, 1.0])
    return x, np.array([(np.maximum(f, 1 - f) >= v).sum() for v in x])


def c_gap():
    from r02_persistence import BAR
    g = pd.concat([pd.read_parquet(f) for f in glob.glob("local_data/r12/full/g/g*.parquet")])
    s = g[g.slot == BAR].groupby("gap").n.sum().sort_index()
    c = s.cumsum() / s.sum()
    x = np.array([0.5, 1, 1.5, 2, 3, 4, 6, 8, 12, 18, 24, 36, 48])
    return x, np.array([c[c.index <= h * 3600 / BAR].iloc[-1] * 100 for h in x])


# ---------------------------------------------------------------- crypto statistics and groups (F8)

def cx_moves():
    """All crypto moves with an outcome (any size) and the jumps (CX_MIN_PTS)."""
    import r05_updown as ud
    info = ud.market_info()
    big_ = ud.load_moves(info)
    e = pd.concat([pd.read_parquet(f) for f in glob.glob(ud.EVENTS)], ignore_index=True).merge(info, on="market")
    e["outcome"] = e.market.map(outcomes())
    return e[e.outcome.notna()], big_, info


def c_cx_crowd(big_):
    x = np.arange(1, 31)
    return shares([big_[big_.takers >= k] for k in x], x)


def c_cx_bins(e):
    err = (e.outcome - e.y_pre).values
    sst = ((err - err.mean()) ** 2).sum()
    x = np.array([2, 3, 4, 5, 8, 10, 15, 20, 25, 30, 40, 50, 100])
    y = []
    for k in x:
        b = pd.cut(e.y_pre, np.linspace(0, 1, k + 1), include_lowest=True)
        m = pd.Series(err).groupby([e.asset.values, e.dur.values, b.values], observed=True).transform("mean").values
        y.append(1 - ((err - m) ** 2).sum() / sst)
    return x, np.array(y)


def c_cx_outcome(info):
    mk = pd.read_parquet(MARKETS_FILE, columns=["id", "outcome_prices"])
    mk = mk[pd.to_numeric(mk.id, errors="coerce").isin(info.market)]
    f = pd.to_numeric(mk.outcome_prices.str.strip("[]").str.split(",").str[0].str.strip(" \'\""), errors="coerce")
    x = np.array([.5, .6, .7, .8, .9, .95, .97, .98, .99, .995, .999, .9999, 1.0])
    return x, np.array([(np.maximum(f, 1 - f) >= v).sum() for v in x])


# ---------------------------------------------------------------- F10

def c_follow_up(b):
    x = np.array([1, 2, 3, 5, 7.5, 10, 15, 20, 30, 45])
    return shares([b[b.entry_delay <= v * 60] for v in x], x)


def main(names):
    rows, knees = [], []

    def add(name, x, y, what, log_x=False, fit_sqrt=False):
        xx = x                     # one rule for every curve: a linear axis
        if fit_sqrt:               # Monte Carlo noise falls as c / sqrt(M): take the knee of the fitted curve
            c = np.sum(y / np.sqrt(x)) / np.sum(1 / x)
            k = knee(xx, c / np.sqrt(np.asarray(x, float)))
        else:
            k = knee(xx, y)
        rows.append(pd.DataFrame({"curve": name, "x": x, "y": y}))
        knees.append({"curve": name, "knee": x[k], "what": what})
        print(f"{name:14s} knee {x[k]:g}; " + ", ".join(f"{a:g}:{v:.4g}" for a, v in zip(x, y)), flush=True)

    todo = set(names) or {"stats", "groups", "f2", "f4", "f5", "f6", "f8", "f10", "other", "cx"}
    b = big()
    if "stats" in todo:
        r = randoms()
        add("sample", *c_sample(b, r), "spread of the overshoot, points")
        add("resamples", *c_resamples(b), "spread of the range's lower end, points", fit_sqrt=True)
        add("bins", *c_bins(r), "share of the calibration error explained")
    if "groups" in todo:
        add("crowd", *c_crowd(b), "overshoot of jumps with at least k traders, %")
        add("money", *c_money(b), "overshoot of jumps with at least $x, %", log_x=True)
        add("wallet_min", *c_wallet_min(b), "wallets kept")
    if "f2" in todo:
        t = pd.read_parquet("local_data/r04_tradable.parquet")
        add("control_bins", *c_control_bins(t), "4+ vs 1 trader gap, all else fixed, points")
    if "f4" in todo:
        add("offset_hi", *c_offset("hi"), "overshoot of crowd jumps offset by at least x, %")
        add("offset_lo", *c_offset("lo"), "overshoot of crowd jumps offset by less than x, %")
    if "f5" in todo:
        t = fade_moves()
        x, y = c_band(t)
        add("band", x, y, "spread of the returns per $")
        from r02_persistence import BET_BAND
        band = BET_BAND             # the band curve is flat: no band is used
        add("trim", *c_trim(t, band), "trimmed mean return, cents per $")
    if "f6" in todo:
        m = micro()
        x, y = c_min_slots(m)
        add("min_slots", x, y, "markets kept")
        add("vr_lag", *c_vr_lag(m, x[knee(x, y)]), "median variance ratio")
        add("spread_win", *c_spread_win(m), "windows with both sides, share", log_x=True)
        add("tag_min", *c_tag_min(), "tags kept", log_x=True)
        add("tag_min_jumps", *c_tag_min_jumps(b), "tags kept (markets with jumps)", log_x=True)
    if "f8" in todo:
        add("moved", *c_moved(), "related markets that moved, %")
        add("cx_points", *c_cx_points(), "error of the coarser path, points")
        add("cx_min_trades", *c_cx_min_trades(), "crypto markets kept")
    if "cx" in todo:
        e, big_, info = cx_moves()
        add("cx_crowd", *c_cx_crowd(big_), "crypto: overshoot of jumps with at least k traders, %")
        add("cx_bins", *c_cx_bins(e), "crypto: share of the calibration error explained")
        add("cx_resamples", *c_resamples(big_), "crypto: spread of the range's lower end, points", fit_sqrt=True)
        add("cx_outcome", *c_cx_outcome(info), "crypto markets with a clear outcome")
    if "other" in todo:
        add("outcome", *c_outcome(), "markets with a clear outcome")
        add("kyle_gap", *c_gap(), "consecutive slots within the gap, %")
    if "f10" in todo:
        add("follow_up", *c_follow_up(b), "overshoot of jumps with a trade within x minutes, %")
    tag = "_".join(sorted(names)) if names else "all"
    pd.concat(rows).to_csv(f"{OUT}/params_curves_{tag}.csv", index=False)
    pd.DataFrame(knees).to_csv(f"{OUT}/params_knees_{tag}.csv", index=False)


if __name__ == "__main__":
    main(sys.argv[1:])
