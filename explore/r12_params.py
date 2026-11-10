"""
The elbow (knee) of every parameter the report uses besides the definition of a jump
(explore/r12_joint.py), on the jumps that definition gives. Each curve is drawn over the range
below; the knee comes from explore/elbow.find (Kneedle, after the flat and turning-point checks).
Run after r02, r03, r05_updown and r06.

  crowd       overshoot of the jumps with at least k traders, vs k (1-30): the crowd K_CROWD
  money       overshoot of the jumps with at least $x in their slot, vs x ($1-$100k): MONEY_X
  band        spread of the per-bet returns vs the band edge e (bets only on jumps that start
              inside [e, 1 - e]; 0-0.2): BET_BAND
  trim        winsorized mean return vs the share brought to the limit at each end (0-10%): TRIM
  outcome     event markets with a clear outcome vs the threshold Q: OUTCOME_Q
  cx_crowd    crypto: overshoot of the jumps with at least k traders: CX_K_CROWD
  cx_outcome  crypto markets with a clear outcome vs Q: CX_OUTCOME_Q
A point of a share-of-jumps curve needs at least MIN_N jumps (a stated value).

Outputs local_data/r12/params_curves.csv and params_knees.csv.
Usage: python explore/r12_params.py
"""
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "explore")
from r02_persistence import BET_BAND, MARKETS as MARKETS_FILE  # noqa: E402
from elbow import find  # noqa: E402

OUT = "local_data/r12"
MIN_N = 1000          # a point of a share-of-jumps curve needs at least this many jumps (stated)


def shares(sets, xs, col="oc"):
    """Overshoot share (%) of each subset, keeping only the points with at least MIN_N jumps."""
    keep = [i for i, z in enumerate(sets) if len(z) >= MIN_N]
    return np.asarray(xs)[keep], np.array([sets[i][col].sum() / sets[i].absdp.sum() * 100 for i in keep])


def c_crowd(b):
    x = np.arange(1, 31)
    return shares([b[b.takers >= k] for k in x], x)


def c_money(b):
    x = np.array([1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000, 100000])
    return shares([b[b.usd >= v] for v in x], x)


def c_band(t):
    x = np.round(np.arange(0, 0.201, 0.01), 2)
    return x * 100, np.array([t[t.y_pre.between(e, 1 - e)].n_taker.std() for e in x])


def c_trim(t):
    t = t[t.y_pre.between(BET_BAND, 1 - BET_BAND)]
    x = np.array([0, .25, .5, 1, 1.5, 2, 2.5, 3, 4, 5, 7.5, 10])
    y = []
    for q in x:
        lo, hi = t.n_taker.quantile([q / 100, 1 - q / 100])
        y.append(t.n_taker.clip(lo, hi).mean() * 100)
    return x, np.array(y)


def c_outcome(updown, crypto):
    """Event markets: every market but the crypto up/down ones; crypto: only those."""
    mk = pd.read_parquet(MARKETS_FILE, columns=["id", "outcome_prices"])
    mk = mk[pd.to_numeric(mk.id, errors="coerce").isin(updown) == crypto]
    f = pd.to_numeric(mk.outcome_prices.str.strip("[]").str.split(",").str[0].str.strip(" '\""), errors="coerce")
    x = np.array([.5, .6, .7, .8, .9, .95, .97, .98, .99, .995, .999, .9999, 1.0])
    return x, np.array([(np.maximum(f, 1 - f) >= v).sum() for v in x])


def main():
    rows, knees = [], []

    def add(name, x, y, what):
        k, kind = find(x, y)
        rows.append(pd.DataFrame({"curve": name, "x": x, "y": y}))
        knees.append({"curve": name, "knee": x[k], "kind": kind, "what": what})
        print(f"{name:11s} {kind} {x[k]:g}; " + ", ".join(f"{a:g}:{v:.4g}" for a, v in zip(x, y)), flush=True)

    b = pd.read_parquet("local_data/r03_big_moves_main.parquet")
    add("crowd", *c_crowd(b), "overshoot of jumps with at least k traders, %")
    add("money", *c_money(b), "overshoot of jumps with at least $x, %")
    t = pd.read_parquet("local_data/r06/r06_fade_moves.parquet")
    add("band", *c_band(t), "spread of the returns per $")
    add("trim", *c_trim(t), "winsorized mean return, cents per $")
    tags = pd.read_csv("local_data/market_tags.csv", dtype=str)
    ud = set(tags.market_id[tags.tags.str.contains("up-or-down", na=False)].astype(int))
    add("outcome", *c_outcome(ud, False), "event markets with a clear outcome")
    cx = pd.read_parquet("local_data/r05/r05_ud_moves.parquet")
    add("cx_crowd", *c_crowd(cx), "crypto: overshoot of jumps with at least k traders, %")
    add("cx_outcome", *c_outcome(ud, True), "crypto markets with a clear outcome")
    pd.concat(rows).to_csv(f"{OUT}/params_curves.csv", index=False)
    pd.DataFrame(knees).to_csv(f"{OUT}/params_knees.csv", index=False)


if __name__ == "__main__":
    main()
