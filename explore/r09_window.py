"""
Round 9: how cutting the start and the end of each market's life changes the results.

Input: local_data/r09/events9 (remote/s9_window.py): jumps with no end pad, the slot's
cumulative trade count, and per market its first and last trade, its settle moment (the last
slot inside [0.05, 0.95] when it ends outside) and its trade counts.
A market's life runs from its first trade to its settle moment (its last trade if it never
settles). Windows compared (a slot is kept if it lies inside):
  no cut            everything up to the settle moment
  6 h end (now)     up to 6 h before the settle moment (markets that settle)
  X% time           drop the first and the last X% of the life
  X% trades         drop the slots in the first and the last X% of the market's trades
The calibration baseline (random slots, per category) uses the same window each time.
Each window is shown for two jump rules: |log-odds change| >= 0.4 (now) and >= 10 points.

Output: local_data/r09_window.csv. Usage: python explore/r09_window.py
"""
import glob
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "explore")
from r02_persistence import category, outcomes, sigmoid  # noqa: E402
from r03_robustness import cat_baseline, overshoot_cat  # noqa: E402

SRC = "local_data/r09/events9"
EXAMPLE = 254049
RULES = {"logit 0.4": (0.4, 0), "10 pts": (0, 10)}


def read(prefix):
    return pd.concat([pd.read_parquet(f) for f in glob.glob(f"{SRC}/{prefix}*.parquet")], ignore_index=True)


def windows(x, mk):
    """Boolean masks of the slots kept by each window."""
    m = mk.reindex(x.market.values)
    t0, t1 = m.t_first.values, np.where(np.isnan(m.t_settle.values), m.t_last.values, m.t_settle.values)
    life, t = t1 - t0, x.t_close.values
    frac = (t - t0) / np.maximum(life, 1)
    pos = x["rank"].values / m.n_settle.values        # share of the market's trades done by the slot's end
    w ={"no cut": np.ones(len(x), bool),
         "6 h end (now)": ~(t > m.t_settle.values - 6 * 3600)}
    for p in (5, 10, 20):
        w[f"{p}% time"] = (frac >= p / 100) & (frac <= 1 - p / 100)
    w["10% time start, 6 h end"] = (frac >= .1) & w["6 h end (now)"]
    for p in (5, 10):
        w[f"{p}% trades"] = (pos >= p / 100) & (pos <= 1 - p / 100)
    return w


def ratio(x, col):
    return x[col].sum() / x.absdp.sum()


def main():
    tags = pd.read_csv("local_data/market_tags.csv", dtype=str)
    cats = pd.Series(category(tags.tags).values, index=tags.market_id.astype(int).values)
    out_ = outcomes()
    mk = read("m").set_index("market")
    e, rnd = read("e"), read("r")
    e["outcome"], rnd["outcome"] = e.market.map(out_), rnd.market.map(out_)
    e, rnd = e[e.outcome.notna()].copy(), rnd[rnd.outcome.notna()].copy()
    e["cat"] = e.market.map(cats).fillna("other")
    rnd["cat"] = rnd.market.map(cats).fillna("other")
    L_pre = np.log(np.clip(e.y_pre, .01, .99) / (1 - np.clip(e.y_pre, .01, .99)))
    e["p_close"] = sigmoid(L_pre + e.move)
    e["absdp"] = (e.p_close - e.y_pre).abs()
    e["sgn"] = np.sign(e.move)
    e["tg"] = pd.cut(e.takers, [0, 1, 3, np.inf], labels=["1", "2-3", "4+"])
    we, wr = windows(e, mk), windows(rnd, mk)
    rows = []
    for wname in we:
        cb = cat_baseline(rnd[wr[wname]])
        x0 = e[we[wname]].copy()
        x0["oc"] = overshoot_cat(x0, x0.p_close, cb)
        x0["oe"] = overshoot_cat(x0, x0.entry_vwap, cb)
        for rname, (lo, pts) in RULES.items():
            x = x0[(x0.move.abs() >= lo) & (x0.absdp >= pts / 100)]
            t = x[x.entry_vwap.notna()]
            r = {"window": wname, "rule": rname, "jumps": len(x), "markets": x.market.nunique(),
                 "sports_share": x.cat.isin(["sports", "esports"]).mean(),
                 "example": int((x.market == EXAMPLE).sum()), "close_all": ratio(x, "oc"), "next_all": ratio(t, "oe")}
            for g, s in x.groupby("tg", observed=True):
                r[f"close_{g}"] = ratio(s, "oc")
                r[f"next_{g}"] = ratio(t[t.tg == g], "oe")
            rows.append(r)
    out = pd.DataFrame(rows)
    out.to_csv("local_data/r09_window.csv", index=False)
    pd.set_option("display.width", 250)
    for rname in RULES:
        print(f"\n{rname}:")
        print(out[out.rule == rname].drop(columns="rule").round(3).to_string(index=False))


if __name__ == "__main__":
    main()
