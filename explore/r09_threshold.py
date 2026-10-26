"""
Round 9: how the price-jump threshold changes the results.

The current rule (|log-odds change| >= 0.4) also flags moves of 1-2 points near 0 or 1,
such as 5% -> 3.5%. This script compares that rule with thresholds in price points and with
the two combined, on the stage-3 moves (15-minute VWAP slots, 6 h end pad), all of which
are at least 0.15 in log-odds, so every rule below is a subset of them.
For each rule: jumps, markets, share by trader group, the size of a typical jump, the
overshoot at the close and at the next trades (category baseline), and the jumps it keeps in
the example market.

Input: local_data/r03_events/900 (remote/s3_events.py). Output: local_data/r09_threshold.csv.
Usage: python explore/r09_threshold.py
"""
import glob
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "explore")
from r02_persistence import category, outcomes  # noqa: E402
from r03_robustness import EV, cat_baseline, load, overshoot_cat  # noqa: E402

EXAMPLE = 254049
RULES = {  # name: (min |log-odds change|, min |price change| in points)
    "logit 0.4 (now)": (0.4, 0), "logit 0.7": (0.7, 0), "logit 1.0": (1.0, 0),
    "5 pts": (0, 5), "10 pts": (0, 10), "15 pts": (0, 15), "20 pts": (0, 20),
    "logit 0.4 + 5 pts": (0.4, 5), "logit 0.4 + 10 pts": (0.4, 10),
}


def ratio(x, col):
    return x[col].sum() / x.absdp.sum()


def main():
    e = load(900)
    tags = pd.read_csv("local_data/market_tags.csv", dtype=str)
    rnd = pd.concat([pd.read_parquet(f) for f in glob.glob(f"{EV}/900/r*.parquet")], ignore_index=True)
    rnd["outcome"] = rnd.market.map(outcomes())
    rnd = rnd[rnd.outcome.notna()]
    rnd["cat"] = rnd.market.map(pd.Series(category(tags.tags).values, index=tags.market_id.astype(int).values)).fillna("other")
    cb = cat_baseline(rnd)
    e["oc"] = overshoot_cat(e, e.p_close, cb)
    e["oe"] = overshoot_cat(e, e.entry_vwap, cb)
    rows = []
    for name, (lo, pts) in RULES.items():
        x = e[(e.move.abs() >= lo) & (e.absdp >= pts / 100)]
        t = x[x.entry_vwap.notna()]
        r = {"rule": name, "jumps": len(x), "markets": x.market.nunique(),
             "median_pts": 100 * x.absdp.median(), "edge_share": ((x.y_pre < .1) | (x.y_pre > .9)).mean(),
             "example": int((x.market == EXAMPLE).sum()), "close_all": ratio(x, "oc"), "next_all": ratio(t, "oe")}
        for g, s in x.groupby("tg", observed=True):
            r[f"share_{g}"] = len(s) / len(x)
            r[f"close_{g}"] = ratio(s, "oc")
            r[f"next_{g}"] = ratio(t[t.tg == g], "oe")
        rows.append(r)
    out = pd.DataFrame(rows)
    out.to_csv("local_data/r09_threshold.csv", index=False)
    pd.set_option("display.width", 250)
    print(out.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
