"""
Round 6, parts A and B: does fading big moves survive real trading prices, and does it pay
more on moves the rest of the event did not confirm?

Input: local_data/r04_tradable.parquet (big 30-min moves with the next-trades price, question
type and overshoot), local_data/r06/micro/x*.parquet (stage 6: side-specific prices after
each move) and local_data/r05/r05_sib_moves.parquet (round-5 sibling groups).

Fade = bet against the move right after the bar closes and hold to resolution. Entry prices:
  mid     average of the next 8 trades, both sides (round 5)
  taker   average of the next 8 trades on the fader's side (after an up move: trades whose
          taker sold YES): what a fader crossing the spread got. Pessimistic.
  maker   average of the next 8 trades on the other side (after an up move: takers buying
          YES), i.e. what a resting order against the move would have been filled at.
          Optimistic: it assumes the order was first in the queue.
Return per $ staked = sgn * (entry - outcome) / stake, stake = 1 - entry (up moves, buying
NO) or entry (down moves, buying YES). "Net" subtracts the usual mispricing at that price and
question type (the calibration baseline), leaving the part due to the move itself.

  A  returns by entry price, number of takers, year, delay and money; the spread paid; and
     how much money traded on the fader's side within 1 h (capacity).
  B  the same, split by what the event's other outcomes did in the move's 30 minutes.

Usage: python explore/r06_fade.py
"""
import glob
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "explore")
from r02_persistence import outcomes  # noqa: E402
from r04_types import osh, baseline, market_info  # noqa: E402

OUT = "local_data/r06/"
N_BOOT = 300


def calib():
    info = market_info()
    rnd = pd.concat([pd.read_parquet(f) for f in glob.glob("local_data/r03_events/1800/r*.parquet")], ignore_index=True)
    rnd["outcome"] = rnd.market.map(outcomes())
    rnd = rnd[rnd.outcome.notna()].join(info, on="market")
    return baseline(rnd, "qtype")


def micro_moves():
    return pd.concat([pd.read_parquet(f) for f in glob.glob(OUT + "micro/x*.parquet")], ignore_index=True)


def add_returns(t, cb):
    for name, col in (("mid", "entry_vwap"), ("taker", "fade_px"), ("maker", "follow_px")):
        p = t[col].astype(float)
        stake = np.where(t.sgn > 0, 1 - p, p)
        t[f"r_{name}"] = t.sgn * (p - t.outcome) / stake
        t[f"n_{name}"] = osh(t, p, cb, "qtype") / stake
    t["spread"] = (t.follow_px - t.fade_px) * t.sgn
    return t


def boot(x, col, n=N_BOOT, seed=1):
    g = x.groupby("market")[col].agg(["sum", "size"])
    rng = np.random.default_rng(seed)
    s, c = g["sum"].values, g["size"].values
    out = [s[i].sum() / c[i].sum() for i in (rng.integers(0, len(g), len(g)) for _ in range(n))]
    return np.percentile(out, [2.5, 97.5])


def summarize(t, keys, label):
    rows = []
    groups = list(t.groupby(keys, observed=True)) if keys else []
    for key, x in groups + [("all", t)]:
        r = {"group": key if not isinstance(key, tuple) else " / ".join(map(str, key)), "moves": len(x),
             "markets": x.market.nunique(), "spread (cents)": 100 * x.spread.median()}
        for name in ("mid", "taker", "maker"):
            r[f"{name} raw"] = x[f"r_{name}"].mean()
            r[f"{name} net"] = x[f"n_{name}"].mean()
        lo, hi = boot(x, "n_taker")
        r["taker net lo"], r["taker net hi"] = lo, hi
        lo, hi = boot(x, "r_taker")
        r["taker raw lo"], r["taker raw hi"] = lo, hi
        r["taker win rate"] = (x.r_taker > 0).mean()
        rows.append(r)
    res = pd.DataFrame(rows)
    print(f"\n[{label}]")
    print(res.round(3).to_string(index=False))
    return res


def capacity(t):
    """Money that traded on the fader's side within 1 h, and the profit if one had taken
    part of it at the taker price (an upper bound: the fader would compete with those trades)."""
    years = (t.t_close.max() - t.t_close.min()) / (365.25 * 86400)
    rows = []
    for cap in (100, 1000, 10000, np.inf):
        size = np.minimum(t.fade_usd_1h.fillna(0), cap)
        rows.append({"cap per move ($)": cap, "staked per year ($)": size.sum() / years,
                     "profit per year raw ($)": (size * t.r_taker).sum() / years,
                     "profit per year net ($)": (size * t.n_taker).sum() / years})
    res = pd.DataFrame(rows)
    q = t.fade_usd_1h.quantile([.25, .5, .75, .9]).round(0).to_dict()
    print(f"\n[A] fader-side $ within 1 h after the move, quartiles: {q}; years covered {years:.1f}")
    print(res.round(0).to_string(index=False))
    return res


def main():
    cb = calib()
    t = pd.read_parquet("local_data/r04_tradable.parquet")
    t = t[t.oq.notna() & t.oqe.notna()]
    t = t.merge(micro_moves(), on=["market", "t_close"], how="inner")
    t = t[t.fade_px.notna() & t.follow_px.notna()].copy()
    # Bets only on moves starting between 5% and 95%: near 0 or 1 the stake of the opposite
    # side is a few cents, and returns per $ explode (+-50x), swamping every average.
    t = t[t.y_pre.between(0.05, 0.95)].copy()
    t = add_returns(t, cb)
    t["fast"] = np.where(t.fade_delay <= 300, "fader trade within 5 min", "later")
    t["money"] = pd.cut(t.usd, [0, 100, 1000, np.inf], labels=["<$100", "$100-1k", ">$1k"])
    t["fader $ 1h"] = pd.cut(t.fade_usd_1h, [-1, 100, 1000, np.inf], labels=["<$100", "$100-1k", ">$1k"])
    print(f"moves with prices on both sides: {len(t):,} in {t.market.nunique():,} markets")
    a = summarize(t, "tg", "A by takers")
    ay = summarize(t, ["year", "tg"], "A by year and takers")
    af = summarize(t, "fast", "A by delay")
    am = summarize(t, "money", "A by money in the move bar")
    ac = summarize(t, "fader $ 1h", "A by money traded on the fader's side within 1 h")
    cap = capacity(t)
    pd.concat([a.assign(split="takers"), ay.assign(split="year x takers"), af.assign(split="delay"),
               am.assign(split="money in bar"), ac.assign(split="fader-side $ in 1 h")]).to_csv(
        OUT + "r06_fade_prices.csv", index=False)
    cap.to_csv(OUT + "r06_fade_capacity.csv", index=False)

    if "--siblings" not in sys.argv:
        t.to_parquet(OUT + "r06_fade_moves.parquet", index=False)
        return
    # B (optional): by what the event's other outcomes did, from round 5's sibling groups
    s = pd.read_parquet("local_data/r05/r05_sib_moves.parquet")[["market", "t_close", "group"]]
    b = t.merge(s, on=["market", "t_close"])
    b["confirmed"] = np.where(b.group.isin(["isolated", "not offset"]), "unconfirmed",
                              np.where(b.group == "offset", "confirmed", "partly"))
    print(f"\nexclusive-event moves with prices: {len(b):,}")
    bg = summarize(b, ["group", "tg"], "B by sibling group and takers")
    bc = summarize(b, ["confirmed"], "B unconfirmed vs confirmed")
    bct = summarize(b, ["confirmed", "tg"], "B by confirmation and takers")
    by = summarize(b[b.confirmed == "unconfirmed"], "year", "B unconfirmed moves by year")
    pd.concat([bg.assign(split="group x takers"), bc.assign(split="confirmation"),
               bct.assign(split="confirmation x takers"), by.assign(split="unconfirmed by year")]).to_csv(
        OUT + "r06_fade_siblings.csv", index=False)
    t.to_parquet(OUT + "r06_fade_moves.parquet", index=False)


if __name__ == "__main__":
    main()
