"""
Round 9b: how the share of each market's life left out at the start and the end changes the
results, and where in a market's life the behaviour of price jumps changes.

Input: local_data/r09/events9 (remote/s9_window.py), as explore/r09_window.py. Jumps of 10
points or more. A market's life runs from its first trade to its settle moment (its last trade
if it never settles); frac = position of the slot's close in that life (0 = open, 1 = settle).

Part 1 (sweep): cut X% at both ends, at the start only and at the end only, for X from 0 to
30%. The calibration baseline (random slots, per category) uses the same window each time.
Part 2 (bands): jumps grouped by frac band (first 1%, 1-2%, ..., last 1%), each measured
against the baseline of random slots in the same band, plus simple descriptors (hours since
the open / to the settle moment, share of sports, share starting near 50%, share starting
below 10% or above 90%).

Outputs local_data/r09_sweep.csv, local_data/r09_bands.csv.
Usage: python explore/r09_sweep.py
"""
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "explore")
from r03_robustness import cat_baseline, overshoot_cat  # noqa: E402
from r05_siblings import boot_share  # noqa: E402
from r09_window import ratio, read  # noqa: E402
from r02_persistence import category, outcomes, sigmoid  # noqa: E402

MIN_PTS = 0.10
CUTS = (0, 0.5, 1, 2, 3, 5, 7.5, 10, 15, 20, 25, 30)
BANDS = (0, .01, .02, .05, .10, .20, .35, .50, .65, .80, .90, .95, .98, .99, 1.0001)


def position(x, mk):
    m = mk.reindex(x.market.values)
    t0 = m.t_first.values
    t1 = np.where(np.isnan(m.t_settle.values), m.t_last.values, m.t_settle.values)
    t = x.t_close.values
    x["frac"] = (t - t0) / np.maximum(t1 - t0, 1)
    x["h_open"], x["h_end"] = (t - t0) / 3600, (t1 - t) / 3600
    x["life_d"] = (t1 - t0) / 86400


def measure(x, rnd_kept, ci=False):
    cb = cat_baseline(rnd_kept)
    x = x.copy()
    x["oc"] = overshoot_cat(x, x.p_close, cb)
    x["oe"] = overshoot_cat(x, x.entry_vwap, cb)
    t = x[x.entry_vwap.notna()]
    r = {"jumps": len(x), "markets": x.market.nunique(), "close_all": ratio(x, "oc"), "next_all": ratio(t, "oe")}
    for g in ("1", "2-3", "4+"):
        r[f"close_{g}"] = ratio(x[x.tg == g], "oc")
        r[f"next_{g}"] = ratio(t[t.tg == g], "oe")
        if ci:
            r[f"close_{g}_lo"], r[f"close_{g}_hi"] = boot_share(x[x.tg == g], "oc")
    return r


def main():
    tags = pd.read_csv("local_data/market_tags.csv", dtype=str)
    cats = pd.Series(category(tags.tags).values, index=tags.market_id.astype(int).values)
    out_ = outcomes()
    mk = read("m").set_index("market")
    e, rnd = read("e"), read("r")
    e["outcome"], rnd["outcome"] = e.market.map(out_), rnd.market.map(out_)
    e, rnd = e[e.outcome.notna()].copy(), rnd[rnd.outcome.notna()].copy()
    e["cat"], rnd["cat"] = e.market.map(cats).fillna("other"), rnd.market.map(cats).fillna("other")
    L_pre = np.log(np.clip(e.y_pre, .01, .99) / (1 - np.clip(e.y_pre, .01, .99)))
    e["p_close"] = sigmoid(L_pre + e.move)
    e["absdp"] = (e.p_close - e.y_pre).abs()
    e = e[e.absdp >= MIN_PTS].copy()
    e["sgn"] = np.sign(e.move)
    e["tg"] = pd.cut(e.takers, [0, 1, 3, np.inf], labels=["1", "2-3", "4+"]).astype(str)
    position(e, mk)
    position(rnd, mk)

    rows = []
    for side in ("both", "start", "end"):
        for c in CUTS:
            if side != "both" and c == 0:
                continue
            p = c / 100
            lo, hi = (p, 1 - p) if side == "both" else (p, 1) if side == "start" else (0, 1 - p)
            ke = (e.frac >= lo) & (e.frac <= hi)
            kr = (rnd.frac >= lo) & (rnd.frac <= hi)
            rows.append({"side": side, "cut_pct": c, **measure(e[ke], rnd[kr], ci=side == "both")})
    sw = pd.DataFrame(rows)
    sw.to_csv("local_data/r09_sweep.csv", index=False)

    e["band"] = pd.cut(e.frac, BANDS, right=False)
    rnd["band"] = pd.cut(rnd.frac, BANDS, right=False)
    rows = []
    for b, x in e.groupby("band", observed=True):
        r = {"band": f"{b.left * 100:g}-{min(b.right, 1) * 100:g}%", **measure(x, rnd[rnd.band == b])}
        r.update(med_pts=x.absdp.median() * 100, med_h_open=x.h_open.median(), med_h_end=x.h_end.median(),
                 med_life_d=x.life_d.median(), sports=x.cat.isin(["sports", "esports"]).mean(),
                 from_mid=x.y_pre.between(.45, .55).mean(), from_edge=(~x.y_pre.between(.1, .9)).mean(),
                 one_trader=(x.tg == "1").mean())
        rows.append(r)
    bands = pd.DataFrame(rows)
    bands.to_csv("local_data/r09_bands.csv", index=False)

    pd.set_option("display.width", 250)
    for side in ("both", "start", "end"):
        print(f"\ncut at {side}:")
        print(sw[sw.side == side].drop(columns="side").round(3).to_string(index=False))
    print("\nby position in the market's life:")
    print(bands.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
