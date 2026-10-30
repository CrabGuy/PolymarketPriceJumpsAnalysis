"""
Round 11: the elbow (knee) method for every tunable parameter of the analysis.

For each parameter, a curve of what the parameter controls is drawn over a range of values,
and the knee is the point farthest from the straight line joining the curve's two ends, once
both axes are scaled to [0, 1] (the "Kneedle" rule, Satopaa et al. 2011). Past the knee,
moving the parameter further changes the curve much less than before.

Local curves (this script):
  threshold   price jumps kept vs the jump threshold (4-40 points)          local_data/r09/events9
  cut_start   price jumps kept vs the share of life left out at the start   local_data/r09/events9
  cut_end     price jumps kept vs the share of life left out at the end     local_data/r09/events9
  takers      overshoot vs the exact number of traders (1-15)               r03_big_moves_main
  boot        Monte Carlo error of the uncertainty range vs resamples       r03_big_moves_main
  sample      spread of the overshoot vs the size of the random sample      r03_events/1800
  bins        overshoot vs the number of price bins of the baseline         r03_events/1800
Server curves (remote/s11_elbow.py, local_data/r11/elbow; skipped if absent):
  slot        share of jumps the next slot reverses vs the slot length
  edge        price jumps kept vs the settle band
  next_n      overshoot at the next trades vs how many trades are averaged
  next_max    share of jumps with next trades vs the time allowed

The saved curves (local_data/r11_curves_all.csv, r11_knees_all.csv, merged from the local and
the server runs) were drawn before the switch to the knee values, with the other parameters
at the old values (15-min slots, 10 points, 10% cut, 5 next trades; inputs r03_*_900 and
r03_events/900). A rerun now reads the new main tables, so its curves start from the knees.
Outputs local_data/r11_curves_<names>.csv (long format) and local_data/r11_knees_<names>.csv.
Usage: python explore/r11_elbow.py [name ...]
"""
import glob
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "explore")
from r02_persistence import BAR, category, outcomes  # noqa: E402
from r03_robustness import cat_baseline, overshoot_cat  # noqa: E402
from r09_window import read  # noqa: E402

SERVER = "local_data/r11/elbow"


def knee(x, y):
    """Index of the point farthest from the chord between the ends, axes scaled to [0, 1]."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    xn = (x - x.min()) / (x.max() - x.min())
    yn = (y - y.min()) / (y.max() - y.min())
    dx, dy = xn[-1] - xn[0], yn[-1] - yn[0]
    dist = np.abs(dy * (xn - xn[0]) - dx * (yn - yn[0])) / np.hypot(dx, dy)
    return int(np.argmax(dist))


def cats():
    tags = pd.read_csv("local_data/market_tags.csv", dtype=str)
    return pd.Series(category(tags.tags).values, index=tags.market_id.astype(int).values)


def life_frac(x, mk):
    m = mk.reindex(x.market.values)
    t0 = m.t_first.values
    t1 = np.where(np.isnan(m.t_settle.values), m.t_last.values, m.t_settle.values)
    return (x.t_close.values - t0) / np.maximum(t1 - t0, 1)


def window_jumps():
    """All jumps of local_data/r09/events9 (no cut but the settle moment) and its random
    slots, with outcome, category, overshoot inputs and the position in the market's life."""
    out, cat = outcomes(), cats()
    mk = read("m").set_index("market")
    e, r = read("e"), read("r")
    e, r = e[e.market.map(out).notna()].copy(), r[r.market.map(out).notna()].copy()
    for x in (e, r):
        x["outcome"], x["cat"] = x.market.map(out), x.market.map(cat).fillna("other")
        x["frac"] = life_frac(x, mk)
    e["p_close"] = np.clip(1 / (1 + np.exp(-(np.log(np.clip(e.y_pre, .01, .99) / (1 - np.clip(e.y_pre, .01, .99)))
                                            + e.move))), .01, .99)
    e["absdp"] = np.abs(e.p_close - e.y_pre)
    e["sgn"] = np.sign(e.move)
    return e, r


def in_window(f, start, end):
    return (f >= start / 100) & (f <= 1 - end / 100)


def overshoot_in(e, r, start, end):
    """Overshoot at the close of the jumps (>= 10 points) inside the window, baseline from
    the random slots inside the same window."""
    x = e[in_window(e.frac, start, end) & (e.absdp >= .10)]
    oc = overshoot_cat(x, x.p_close, cat_baseline(r[in_window(r.frac, start, end)]))
    return oc.sum() / x.absdp.sum()


def c_threshold(e, r):
    w = e[in_window(e.frac, 10, 10)]
    oc = overshoot_cat(w, w.p_close, cat_baseline(r[in_window(r.frac, 10, 10)]))
    x = np.arange(4, 41)
    kept = np.array([(w.absdp >= t / 100).sum() for t in x])
    os_ = np.array([oc[w.absdp >= t / 100].sum() / w.absdp[w.absdp >= t / 100].sum() for t in x])
    return x, kept, os_


def c_cut(e, r, side):
    j = e[e.absdp >= .10]
    x = np.arange(0, 30.5, .5)
    cut = {"start": lambda c: (c, 0), "end": lambda c: (0, c), "both": lambda c: (c, c)}[side]
    kept = np.array([in_window(j.frac, *cut(c)).sum() for c in x])
    os_ = np.array([overshoot_in(e, r, *cut(c)) for c in x])
    return x, kept, os_


def big():
    return pd.read_parquet("local_data/r03_big_moves_main.parquet")


def c_takers(b):
    x = np.arange(1, 11)          # over 10 traders, under 1,200 jumps per count
    y = [b.loc[b.takers == k, "oc"].sum() / b.loc[b.takers == k, "absdp"].sum() for k in x]
    return x, np.array(y)


def c_boot(b, reps=40):
    g = b.groupby("market")[["oc", "absdp"]].sum()
    a, d = g.oc.values, g.absdp.values
    rng = np.random.default_rng(0)
    x = np.array([10, 20, 30, 50, 75, 100, 150, 200, 300, 500, 750, 1000])
    y = []
    for n in x:
        lows = []
        for _ in range(reps):
            i = rng.integers(0, len(g), (n, len(g)))
            lows.append(np.percentile(a[i].sum(1) / d[i].sum(1), 2.5))
        y.append(np.std(lows))
    return x, np.array(y)


def random_slots():
    r = pd.concat([pd.read_parquet(f) for f in glob.glob("local_data/r03_events/1800/r*.parquet")], ignore_index=True)
    r["outcome"] = r.market.map(outcomes())
    r = r[r.outcome.notna()].copy()
    r["cat"] = r.market.map(cats()).fillna("other")
    return r


def c_sample(b, r, reps=20):
    rng = np.random.default_rng(1)
    x = np.array([.1, .25, .5, .75, 1, 1.5, 2, 3, 4, 5])
    y = []
    for s in x:
        v = []
        for _ in range(reps):
            sub = r.iloc[rng.integers(0, len(r), int(len(r) * s / 5))]   # drawn with replacement
            oc = overshoot_cat(b, b.p_close, cat_baseline(sub))
            v.append(oc.sum() / b.absdp.sum())
        y.append(np.nanstd(v))
    return x, np.array(y)


def c_bins(b, r):
    x = np.array([2, 4, 5, 10, 20, 25, 40, 50, 100])
    y = []
    for k in x:
        bins = np.linspace(0, 1, k + 1)
        base = r.assign(bin=pd.cut(r.vwap, bins)).groupby(["cat", "bin"], observed=True).apply(
            lambda z: (z.outcome - z.vwap).mean())
        bb = base.reindex(pd.MultiIndex.from_arrays([b.cat.values, pd.cut(b.p_close, bins)])).astype(float).values
        oc = -((b.outcome - b.p_close) - bb) * b.sgn
        y.append(oc.sum() / b.absdp.sum())
    return x, np.array(y)


def server():
    out, cat = outcomes(), cats()
    j, r, x = ([pd.read_parquet(f) for f in sorted(glob.glob(f"{SERVER}/{p}*.parquet"))] for p in "jrx")
    j, r, x = pd.concat(j, ignore_index=True), pd.concat(r, ignore_index=True), pd.concat(x, ignore_index=True)
    for d in (j, r):
        d["outcome"], d["cat"] = d.market.map(out), d.market.map(cat).fillna("other")
    j["p_close"] = j.vwap.clip(.01, .99)
    j["absdp"] = (j.p_close - j.y_pre).abs()
    j["sgn"] = np.sign(j.p_close - j.y_pre)
    return j, r[r.outcome.notna()], x


def c_slot(j, r):
    """Per slot length: price jumps with an outcome, and their overshoot at the close
    (baseline from random slots of the same length)."""
    x, kept, os_ = [], [], []
    for cfg in sorted({c for c in j.cfg.unique() if c.startswith("b")}, key=lambda c: int(c[1:])):
        s = j[(j.cfg == cfg) & j.outcome.notna()]
        oc = overshoot_cat(s, s.p_close, cat_baseline(r[r.cfg == cfg]))
        x.append(int(cfg[1:]) / 60)
        kept.append(len(s))
        os_.append(oc.sum() / s.absdp.sum())
    return np.array(x), np.array(kept), np.array(os_)


def c_edge(j):
    s = j[j.cfg.str.startswith("e")]
    y = s.groupby(s.cfg.str[1:].astype(float)).size()
    return y.index.values * 100, y.values


def next_entry(x, n, max_s):
    y = np.stack([x[f"y{i}"].values for i in range(n)], 1)
    u = np.stack([x[f"u{i}"].values for i in range(n)], 1)
    dt = np.stack([x[f"dt{i}"].values for i in range(n)], 1)
    ok = (dt >= 0) & (dt < max_s)
    u = np.where(ok, u, 0)
    return np.where(u.sum(1) > 0, (np.nan_to_num(y) * u).sum(1) / np.maximum(u.sum(1), 1e-12), np.nan)



def c_next_n(m, cb):
    x = np.arange(1, 21)
    y = []
    for n in x:
        p = next_entry(m, n, 3600)
        ok = ~np.isnan(p)
        t = m[ok]
        y.append(overshoot_cat(t, p[ok], cb).sum() / t.absdp.sum())
    return x, np.array(y)


def c_next_max(m):
    x = np.array([1, 2, 5, 10, 15, 20, 30, 45, 60, 90, 120, 180, 240])
    return x, np.array([(~np.isnan(next_entry(m, 5, s * 60))).mean() for s in x])


def main(names):
    curves, knees = [], []

    def add(name, x, y, chosen, what):
        k = knee(x, y)
        curves.append(pd.DataFrame({"curve": name, "x": x, "y": y}))
        knees.append({"curve": name, "knee": x[k], "chosen": chosen, "what": what})
        print(f"{name:10s} knee at {x[k]:g} (chosen {chosen:g}); " + ", ".join(f"{a:g}:{b:.4g}" for a, b in zip(x, y)))

    todo = names or ["threshold", "cut", "takers", "boot", "sample", "bins", "server"]
    if {"threshold", "cut"} & set(todo):
        e, r9 = window_jumps()
        if "threshold" in todo:
            x, kept, os_ = c_threshold(e, r9)
            add("threshold", x, kept, 10, "price jumps kept (window 10%)")
            add("threshold_os", x, os_, 10, "overshoot at the close")
        for side in ("start", "end", "both"):
            if "cut" in todo:
                x, kept, os_ = c_cut(e, r9, side)
                add(f"cut_{side}", x, kept, 10, f"price jumps kept, {side} cut only")
                add(f"cut_{side}_os", x, os_, 10, f"overshoot at the close, {side} cut only")
    if {"takers", "boot", "sample", "bins", "server"} & set(todo):
        b = big()
        r = random_slots()
        if "takers" in todo:
            add("takers", *c_takers(b), 4, "overshoot at the close")
        if "boot" in todo:
            add("boot", *c_boot(b), 200, "Monte Carlo spread of the 2.5% bound")
        if "sample" in todo:
            add("sample", *c_sample(b, r), 5, "spread of the overshoot over subsamples")
        if "bins" in todo:
            add("bins", *c_bins(b, r), 20, "overshoot at the close")
        if "server" in todo and glob.glob(f"{SERVER}/j*.parquet"):
            j, rs, x = server()
            sx, kept, os_ = c_slot(j, rs)
            add("slot", sx, kept, 15, "price jumps kept")
            add("slot_os", sx, os_, 15, "overshoot at the close")
            add("edge", *c_edge(j), 5, "price jumps kept")
            m = j[(j.cfg == f"b{BAR}") & j.outcome.notna()].merge(x, on=["market", "t_close"])
            add("next_n", *c_next_n(m, cat_baseline(rs[rs.cfg == f"b{BAR}"])), 5, "overshoot at the next trades")
            add("next_max", *c_next_max(m), 60, "share of jumps with next trades")
    if curves:
        tag = "_".join(names) if names else "all"
        pd.concat(curves).to_csv(f"local_data/r11_curves_{tag}.csv", index=False)
        pd.DataFrame(knees).to_csv(f"local_data/r11_knees_{tag}.csv", index=False)


if __name__ == "__main__":
    main(sys.argv[1:])
