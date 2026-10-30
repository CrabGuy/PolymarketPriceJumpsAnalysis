"""
Round 11: price jumps by the exact number of traders, how far single-trader jumps are given
back, and whether single-trader jumps point the right way.

Input: local_data/r03_big_moves_main.parquet (explore/r03_robustness.py), the main price jumps.
  traders   jumps and overshoot at the close (category baseline, 95% range by resampling
            markets) for each exact number of distinct takers in the jump's slot, 1 to 10,
            then 11-20, 21-50 and over 50
  giveback  single-trader jumps: share of the jump given back, g = (p_close - p) / (p_close - p_pre),
            at the next trades (p = their VWAP) and 1 h and 24 h later (from the log-odds
            ratio ret_h: g = 1 - ret_h); histogram in 10-point bins
  accuracy  share of jumps that point toward the final outcome (up and YES won, or down and
            NO won), against the share expected if the price after the jump were right
            (p_close for up jumps, 1 - p_close for down jumps) and if the price before it were
            right (same with p_pre); per trader group and per exact number of traders

Outputs local_data/r11_traders.csv, r11_giveback.csv, r11_accuracy.csv.
Usage: python explore/r11_traders.py
"""
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "explore")
from r05_siblings import boot_share  # noqa: E402
from r02_persistence import N_RESAMPLES  # noqa: E402

COUNTS = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 50, np.inf]
COUNT_LABELS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11-20", "21-50", "over 50"]
GB_BINS = np.r_[-np.inf, np.arange(-.5, 1.51, .1), np.inf]


def by_count(b):
    b = b.assign(k=pd.cut(b.takers, COUNTS, labels=COUNT_LABELS))
    rows = []
    for k, x in b.groupby("k", observed=True):
        lo, hi = boot_share(x, "oc")
        rows.append({"traders": k, "jumps": len(x), "share": len(x) / len(b),
                     "overshoot": x.oc.sum() / x.absdp.sum(), "lo": lo, "hi": hi})
    return pd.DataFrame(rows)


def giveback(b):
    s = b[b.takers == 1]
    g = {"next trades": ((s.p_close - s.entry_vwap) / (s.p_close - s.y_pre)).dropna(),
         "1 hour later": (1 - s.ret_1h).dropna(), "1 day later": (1 - s.ret_24h).dropna()}
    out = pd.DataFrame({k: pd.cut(v, GB_BINS, right=False).value_counts(normalize=True).sort_index() for k, v in g.items()})
    out.index = [f"{i.left:.1f}..{i.right:.1f}" for i in out.index]
    for k, v in g.items():
        print(f"{k}: {len(v):,} jumps, median give-back {v.median():.0%}, gave back >= half {np.mean(v >= .5):.0%}, "
              f"all or more {np.mean(v >= 1):.0%}, went further {np.mean(v < 0):.0%}")
    return out


def accuracy(b):
    up = b.sgn > 0
    b = b.assign(right=np.where(up, b.outcome == 1, b.outcome == 0),
                 exp_after=np.where(up, b.p_close, 1 - b.p_close),
                 exp_before=np.where(up, b.y_pre, 1 - b.y_pre),
                 k=pd.cut(b.takers, COUNTS, labels=COUNT_LABELS))
    rows = []
    for key in ("tg", "k"):
        for g, x in b.groupby(key, observed=True):
            m = x.groupby("market")[["right", "exp_after", "exp_before"]].sum()
            n = x.groupby("market").size()
            rng = np.random.default_rng(3)
            bs = []
            for _ in range(N_RESAMPLES):
                i = rng.integers(0, len(m), len(m))
                bs.append(m.right.values[i].sum() / n.values[i].sum())
            rows.append({"by": key, "group": str(g), "jumps": len(x), "right": x.right.mean(),
                         "lo": np.percentile(bs, 2.5), "hi": np.percentile(bs, 97.5),
                         "expected_after": x.exp_after.mean(), "expected_before": x.exp_before.mean()})
    return pd.DataFrame(rows)


def main():
    b = pd.read_parquet("local_data/r03_big_moves_main.parquet")
    pd.set_option("display.width", 200)
    t = by_count(b)
    print(t.round(3).to_string(index=False))
    t.to_csv("local_data/r11_traders.csv", index=False)
    g = giveback(b)
    print(g.round(3).to_string())
    g.to_csv("local_data/r11_giveback.csv")
    a = accuracy(b)
    print(a.round(3).to_string(index=False))
    a.to_csv("local_data/r11_accuracy.csv", index=False)


if __name__ == "__main__":
    main()
