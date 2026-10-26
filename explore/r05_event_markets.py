"""
Round 5, part 1: the overshoot pattern in event markets, explored fully.

Input: local_data/r04_tradable.parquet (big 15-min moves, VWAP basis, |move| >= 0.4, with
the next-trades price, question type and lifetime; built by r03_robustness.py and
r04_types.py) and local_data/r03_big_moves_900.parquet. Overshoot uses the question-type
calibration baseline (column oq at the close, oqe at the next trades).

  A  all factors at once: weighted least squares of each move's overshoot share (weight =
     its price change, so the fitted levels match the ratio of sums) on number of takers,
     question type, category, money in the bar, price level, time to end, market lifetime,
     year and direction. 95% intervals by resampling markets (200 times).
     -> how much of the taker effect survives every control, and which factor moves
        overshoot the most.
  B  how fast it goes away, by question type and number of takers (close, next trades,
     1 h, 6 h, 24 h).
  C  by quarter: is the effect shrinking as the market matures?
  D  what a trader could do: fade every big move at the next trades and hold to
     resolution, by number of takers and year: raw, and net of the usual mispricing at that
     price and question type (calibration baseline). Before fees.

Usage: python explore/r05_event_markets.py
"""
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "explore")
from r02_persistence import sigmoid  # noqa: E402
from r04_types import osh, baseline, market_info  # noqa: E402
from r02_persistence import outcomes  # noqa: E402

OUT = "local_data/r05/"
N_BOOT = 200


def share(x, col):
    return x[col].sum() / x.absdp.sum()


def factors(t):
    f = pd.DataFrame(index=t.index)
    f["takers"] = t.tg.astype(str)
    f["question type"] = t.qtype
    f["category"] = t.cat
    f["money in bar"] = pd.cut(t.usd, [0, 100, 1000, 10000, np.inf], labels=["<$100", "$100-1k", "$1k-10k", ">$10k"]).astype(str)
    f["price before"] = pd.cut(t.y_pre, [0, .2, .4, .6, .8, 1], labels=["<20%", "20-40%", "40-60%", "60-80%", ">80%"]).astype(str)
    f["time to end"] = pd.cut(t.days_to_end, [-np.inf, 1, 7, 30, np.inf], labels=["<1 day", "1-7 days", "7-30 days", ">30 days"]).astype(str)
    f["market lifetime"] = t.life.astype(str)
    f["year"] = t.year.clip(lower=2023).astype(str).replace("2023", "2022-23")
    f["direction"] = t.dir
    return f.astype(object).where(f.notna(), "unknown").replace("nan", "unknown")


REF = {"takers": "1", "question type": "other", "category": "other", "money in bar": "<$100",
       "price before": "40-60%", "time to end": ">30 days", "market lifetime": ">30 days",
       "year": "2024", "direction": "down"}


def design(f):
    cols, names = [np.ones(len(f))], [("const", "")]
    for c in f.columns:
        for lv in sorted(f[c].unique()):
            if lv == REF[c]:
                continue
            cols.append((f[c].values == lv).astype(float))
            names.append((c, lv))
    return np.column_stack(cols), names


def wls(X, y, w):
    sw = np.sqrt(w)
    beta, *_ = np.linalg.lstsq(X * sw[:, None], y * sw, rcond=None)
    return beta


def part_a(t):
    f = factors(t)
    ok = ~(f == "unknown").any(axis=1).values
    t, f = t[ok], f[ok]
    X, names = design(f)
    y = (t.oq / t.absdp).values
    w = t.absdp.values
    beta = wls(X, y, w)
    mk = t.market.values
    uniq = np.unique(mk)
    pos = pd.Series(np.arange(len(t))).groupby(mk).apply(np.array)
    rng = np.random.default_rng(0)
    boots = []
    for _ in range(N_BOOT):
        pick = np.concatenate(pos.loc[rng.choice(uniq, len(uniq))].values)
        boots.append(wls(X[pick], y[pick], w[pick]))
    boots = np.array(boots)
    res = pd.DataFrame({"factor": [n[0] for n in names], "level": [n[1] for n in names], "effect": beta,
                        "lo": np.percentile(boots, 2.5, axis=0), "hi": np.percentile(boots, 97.5, axis=0)})
    # raw (unadjusted) gaps for the takers factor, for comparison
    raw = t.groupby("tg", observed=True).apply(lambda x: share(x, "oq"))
    # how much each factor moves overshoot: spread between its highest and lowest adjusted level
    rows = []
    for c in f.columns:
        r = res[res.factor == c]
        lv = np.append(r.effect.values, 0.0)          # the reference level is 0
        rows.append({"factor": c, "levels": len(lv), "spread": lv.max() - lv.min()})
    spread = pd.DataFrame(rows).sort_values("spread", ascending=False)
    print(f"[A] {len(t):,} moves, {len(uniq):,} markets, {X.shape[1]} terms")
    print("raw overshoot by takers:", raw.round(3).to_dict())
    print(res[res.factor == "takers"].round(3).to_string(index=False))
    print("\nadjusted spread between the highest and lowest level of each factor:")
    print(spread.round(3).to_string(index=False))
    res.to_csv(OUT + "r05_factor_effects.csv", index=False)
    spread.to_csv(OUT + "r05_factor_spread.csv", index=False)
    return res, spread


def part_b(t, cb):
    dyn = t.dropna(subset=["ret_1h", "ret_6h", "ret_24h"]).copy()
    cols = {"close": "oq", "next trades": "oqe"}
    for h in ("1h", "6h", "24h"):
        dyn["oq_" + h] = osh(dyn, sigmoid(dyn.L_pre + dyn["ret_" + h] * dyn.move), cb, "qtype")
        cols[h] = "oq_" + h
    rows = []
    for (qt, tg), x in dyn.groupby(["qtype", "tg"], observed=True):
        rows.append({"qtype": qt, "takers": tg, "moves": len(x), **{k: share(x, v) for k, v in cols.items()}})
    for tg, x in dyn.groupby("tg", observed=True):
        rows.append({"qtype": "all", "takers": tg, "moves": len(x), **{k: share(x, v) for k, v in cols.items()}})
    cur = pd.DataFrame(rows)
    # half-life proxy: share of the close overshoot left at the next trades and at 1 h
    cur["left at next trades"] = cur["next trades"] / cur["close"]
    cur["left at 1h"] = cur["1h"] / cur["close"]
    print(f"\n[B] decay by question type and takers ({len(dyn):,} moves with all horizons):")
    print(cur.round(3).to_string(index=False))
    cur.to_csv(OUT + "r05_decay_by_type.csv", index=False)
    return cur


def part_c(t):
    t = t.assign(q=pd.to_datetime(t.t_close, unit="s").dt.to_period("Q").astype(str))
    rows = []
    for q, x in t.groupby("q"):
        r = {"quarter": q, "moves": len(x), "markets": x.market.nunique(), "close": share(x, "oq"),
             "next trades": share(x, "oqe")}
        for tg in ("1", "2-3", "4+"):
            s = x[x.tg == tg]
            r[f"close {tg}"] = share(s, "oq") if len(s) >= 200 else np.nan
            r[f"next {tg}"] = share(s, "oqe") if len(s) >= 200 else np.nan
        rows.append(r)
    res = pd.DataFrame(rows)
    print("\n[C] by quarter:")
    print(res.round(3).to_string(index=False))
    res.to_csv(OUT + "r05_by_quarter.csv", index=False)
    return res


def part_d(t):
    """Fade every big move at the next trades, hold to resolution. Raw (no calibration, no fees)."""
    t = t.copy()
    # return per $ staked: buying the side opposite to the move at the next-trade price
    stake = np.where(t.sgn > 0, 1 - t.entry_vwap, t.entry_vwap)
    t["ret"] = t.sgn * (t.entry_vwap - t.outcome) / stake
    t["ret_raw"] = t.ret
    t["ret_adj"] = t.oqe / stake          # net of the usual mispricing at that price and type
    t["fast"] = t.entry_delay <= 300
    rows = []
    for key, x in list(t.groupby("tg", observed=True)) + [("all", t)]:
        for fast, s in (("any delay", x), ("next trade within 5 min", x[x.fast])):
            b = boot_mean(s)
            ba = boot_mean(s.assign(ret=s.ret_adj))
            rows.append({"takers": key, "entry": fast, "moves": len(s), "return per $": s.ret.mean(),
                         "lo": b[0], "hi": b[1], "win rate": (s.ret > 0).mean(),
                         "net of calibration": s.ret_adj.mean(), "adj lo": ba[0], "adj hi": ba[1]})
    res = pd.DataFrame(rows)
    yr = t.groupby(["year", "tg"], observed=True)[["ret", "ret_adj"]].mean().unstack()
    print("\n[D] fade at the next trades, hold to resolution (raw):")
    print(res.round(3).to_string(index=False))
    print(yr.round(3).to_string())
    res.to_csv(OUT + "r05_fade.csv", index=False)
    yr.to_csv(OUT + "r05_fade_by_year.csv")
    return res


def boot_mean(x, n=200):
    g = x.groupby("market").ret.agg(["sum", "size"])
    rng = np.random.default_rng(1)
    s, c = g["sum"].values, g["size"].values
    out = []
    for _ in range(n):
        i = rng.integers(0, len(g), len(g))
        out.append(s[i].sum() / c[i].sum())
    return np.percentile(out, [2.5, 97.5])


def main():
    import glob
    t = pd.read_parquet("local_data/r04_tradable.parquet")
    t = t[t.oq.notna() & t.oqe.notna()].copy()
    info = market_info()
    rnd = pd.concat([pd.read_parquet(f) for f in glob.glob("local_data/r03_events/900/r*.parquet")], ignore_index=True)
    rnd["outcome"] = rnd.market.map(outcomes())
    rnd = rnd[rnd.outcome.notna()].join(info, on="market")
    cb = baseline(rnd, "qtype")
    part_a(t)
    part_b(t, cb)
    part_c(t)
    part_d(t)


if __name__ == "__main__":
    main()
