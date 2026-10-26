"""
Round 7, part 2: does the volume-weighted bar price (VWAP) create the single-trader effect?

Question: one big trade dominates a bar's VWAP, so is a single trader's
"move" an artefact of volume weighting? Within a bar the VWAP weighs each trade by its
size; across bars the weights don't interact. To check, moves are re-measured on the
equal-weighted MEAN trade price of each bar (remote/s7_events.py mode "basis",
local_data/r07/basis/) and compared with the VWAP basis (local_data/r03_events/900/), with
the same method on both:
  - calibration baseline from random active bars on the same basis, pooled, 5-point bins
  - overshoot share (ratio of sums) at the bar close and at the next 5 trades
    (VWAP basis: their VWAP; mean basis: their plain mean)
  - by number of distinct traders, 90% intervals from resampling markets.
Outputs local_data/r07/basis_compare.csv.
Usage: python explore/r07_basis.py
"""
import glob
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "explore")
from r02_persistence import outcomes, sigmoid  # noqa: E402

BINS = np.linspace(0, 1, 21)


def load(src, price_col, entry_col):
    out = outcomes()
    e = pd.concat([pd.read_parquet(f) for f in glob.glob(src + "e*.parquet")], ignore_index=True)
    r = pd.concat([pd.read_parquet(f) for f in glob.glob(src + "r*.parquet")], ignore_index=True)
    r = r.rename(columns={price_col: "price"})
    r["outcome"] = r.market.map(out)
    r = r[r.outcome.notna()]
    base = (r.outcome - r.price).groupby(pd.cut(r.price, BINS), observed=False).mean()
    e["outcome"] = e.market.map(out)
    e = e[e.outcome.notna() & (e.move.abs() >= 0.4)].copy()
    L_pre = np.log(np.clip(e.y_pre, .01, .99) / (1 - np.clip(e.y_pre, .01, .99)))
    e["p_close"] = sigmoid(L_pre + e.move)
    e["absdp"] = (e.p_close - e.y_pre).abs()
    e["sgn"] = np.sign(e.move)
    e["tg"] = pd.cut(e.takers, [0, 1, 3, np.inf], labels=["1", "2-3", "4+"]).astype(str)

    def osh(p):
        return -((e.outcome - p) - pd.cut(p, BINS).map(base).astype(float)) * e.sgn

    e["oc"] = osh(e.p_close)
    e["oe"] = np.where(e[entry_col].notna(), osh(e[entry_col].fillna(0.5)), np.nan)
    return e


def share(x, col, n=200):
    x = x[x[col].notna()]
    g = x.groupby("market").agg(a=(col, "sum"), b=("absdp", "sum"))
    a, b = g.a.values, g.b.values
    i = np.random.default_rng(0).integers(0, len(g), size=(n, len(g)))
    bs = a[i].sum(1) / b[i].sum(1)
    return a.sum() / b.sum(), np.percentile(bs, 5), np.percentile(bs, 95)


def main():
    rows = []
    for name, src, pc, ec in (("VWAP (volume-weighted)", "local_data/r03_events/900/", "vwap", "entry_vwap"),
                              ("plain mean of trades", "local_data/r07/basis/", "price", "entry_mean")):
        e = load(src, pc, ec)
        for tg, x in [("all", e)] + list(e.groupby("tg")):
            for col, when in (("oc", "bar close"), ("oe", "next trades")):
                v, lo, hi = share(x, col)
                rows.append({"basis": name, "takers": tg, "when": when, "moves": int(x[col].notna().sum()),
                             "markets": x.market.nunique(), "overshoot": v, "lo": lo, "hi": hi})
        print(f"{name}: {len(e):,} big moves in {e.market.nunique():,} markets")
    res = pd.DataFrame(rows)
    print(res.round(3).to_string(index=False))
    res.to_csv("local_data/r07/basis_compare.csv", index=False)


if __name__ == "__main__":
    main()
