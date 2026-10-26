"""
Round 8, part 1: does each move filter change the results?

Input: local_data/r08_variants/<variant>/ from remote/s9_variants.py: big moves (15-min VWAP,
|Δ log-odds| >= 0.4, no limit on the time since the previous trade) under the base filters
and with one filter removed at a time (see that script). For every variant, the same
method: calibration baseline = mean (outcome - price) by 5-point bin from the variant's own
random bars, overshoot share (ratio of sums) at the bar close and at the next 5 trades, by
number of distinct traders, 90% intervals from resampling markets. Also by category, to
see where a change comes from.
Output local_data/r08_filters.csv and r08_filters_cat.csv.
Usage: python explore/r08_filters.py
"""
import glob
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "explore")
from r02_persistence import category, outcomes, sigmoid  # noqa: E402
from r07_basis import share  # noqa: E402

SRC = "local_data/r08_variants/"
VARIANTS = ["base", "no_min", "no_endcut", "no_pad", "no_ends", "no_band"]
BINS = np.linspace(0, 1, 21)


def load(v, out, cat):
    e = pd.concat([pd.read_parquet(f) for f in glob.glob(f"{SRC}{v}/e*.parquet")], ignore_index=True)
    r = pd.concat([pd.read_parquet(f) for f in glob.glob(f"{SRC}{v}/r*.parquet")], ignore_index=True)
    r["outcome"] = r.market.map(out)
    r = r[r.outcome.notna()]
    base = (r.outcome - r.vwap).groupby(pd.cut(r.vwap, BINS, include_lowest=True), observed=False).mean()
    e["outcome"] = e.market.map(out)
    e = e[e.outcome.notna()].copy()
    L_pre = np.log(np.clip(e.y_pre, .01, .99) / (1 - np.clip(e.y_pre, .01, .99)))
    e["p_close"] = sigmoid(L_pre + e.move)
    e["absdp"] = (e.p_close - e.y_pre).abs()
    e["sgn"] = np.sign(e.move)
    e["tg"] = pd.cut(e.takers, [0, 1, 3, np.inf], labels=["1", "2-3", "4+"]).astype(str)
    e["cat"] = e.market.map(cat).fillna("other")

    def osh(p):
        return -((e.outcome - p) - pd.cut(p, BINS, include_lowest=True).map(base).astype(float)) * e.sgn

    e["oc"] = osh(e.p_close)
    e["oe"] = np.where(e.entry_vwap.notna(), osh(e.entry_vwap.fillna(0.5)), np.nan)
    return e


def main():
    out = outcomes()
    tags = pd.read_csv("local_data/market_tags.csv", dtype=str)
    cat = pd.Series(category(tags.tags).values, index=tags.market_id.astype(int).values)
    cat = cat[~cat.index.duplicated()]
    rows, crow = [], []
    for v in VARIANTS:
        e = load(v, out, cat)
        print(f"{v}: {len(e):,} big moves, {e.market.nunique():,} markets", flush=True)
        for tg, x in [("all", e)] + list(e.groupby("tg")):
            for col, when in (("oc", "close"), ("oe", "next trades")):
                s, lo, hi = share(x, col)
                rows.append({"variant": v, "takers": tg, "when": when, "moves": int(x[col].notna().sum()),
                             "markets": x.market.nunique(), "overshoot": s, "lo": lo, "hi": hi})
        for c, x in e.groupby("cat"):
            crow.append({"variant": v, "cat": c, "moves": len(x), "close": x.oc.sum() / x.absdp.sum()})
    res = pd.DataFrame(rows)
    res.to_csv("local_data/r08_filters.csv", index=False)
    print(res.pivot_table(index=["variant", "when"], columns="takers", values="overshoot", sort=False).round(3).to_string())
    print(res[res.takers == "all"].pivot_table(index="variant", columns="when", values="moves", sort=False).to_string())
    c = pd.DataFrame(crow)
    c.to_csv("local_data/r08_filters_cat.csv", index=False)
    print(c.pivot_table(index="cat", columns="variant", values="close")[VARIANTS].round(3).to_string())
    print(c.pivot_table(index="cat", columns="variant", values="moves")[VARIANTS].to_string())


if __name__ == "__main__":
    main()
