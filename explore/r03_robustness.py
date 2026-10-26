"""
Round 3: stress-test findings F1-F3 (overshoot of big moves; the number of traders; a
single trader's big push).

Input: local_data/r03_events/<bar>/e*.parquet and r*.parquet from remote/s3_events.py.
1. Baseline: calibration at random active moments (5% sample of bars) vs before moves.
2. Tradability: overshoot remaining at the next tradable price (VWAP of the first 5 trades
   after the bar closes) and the raw profit of fading the move there, held to resolution:
   sign(move) * (p_entry - outcome) per share, in cents (no fees, no baseline).
3. Dynamics: overshoot remaining at close, entry, +1 h, +6 h, +24 h (same moves throughout).
4. Wallets: concentration of single-trader moves, and persistence of a wallet's overshoot
   between the first and second half of its history (vs a shuffled null).
5. Definition: bar size 5/15/60 min and jump threshold 5/10/15 points.
6. Category baselines: calibration measured per category at random moments (crypto YES is
   about 8 points overpriced, sports about 0). Overshoot, the takers effect, up/down
   asymmetry and the time profile are recomputed with it. These are the reported numbers.

Usage: python explore/r03_robustness.py
"""
import glob
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "explore")
from r02_persistence import MIN_PTS, category, outcomes, sigmoid  # noqa: E402

BARS = (300, 900, 3600)
EV = "local_data/r03_events"


def baseline_table(p, outcome, bins):
    return pd.Series(outcome - p).groupby(pd.cut(p, bins), observed=False).mean()


def load(bar):
    e = pd.concat([pd.read_parquet(f) for f in glob.glob(f"{EV}/{bar}/e*.parquet")], ignore_index=True)
    e["outcome"] = e.market.map(outcomes())
    e = e[e.outcome.notna()].copy()
    tags = pd.read_csv("local_data/market_tags.csv", dtype=str)
    e["cat"] = e.market.map(pd.Series(category(tags.tags).values, index=tags.market_id.astype(int).values)).fillna("other")
    e["year"] = pd.to_datetime(e.t_close, unit="s").dt.year
    e["L_pre"] = np.log(np.clip(e.y_pre, .01, .99) / (1 - np.clip(e.y_pre, .01, .99)))
    e["p_close"] = sigmoid(e.L_pre + e.move)
    e["absdp"] = (e.p_close - e.y_pre).abs()
    e["sgn"] = np.sign(e.move)
    e["tg"] = pd.cut(e.takers, [0, 1, 3, np.inf], labels=["1", "2-3", "4+"])
    return e


def overshoot(e, p, base):
    """Overshoot (probability points) still present if the price is p."""
    b = pd.cut(p, BINS).map(base).astype(float)
    return -((e.outcome - p) - b) * e.sgn


def cat_baseline(rnd):
    """Calibration error (outcome - price) per (category, 5-point price bin), random moments."""
    rnd = rnd.assign(bin=pd.cut(rnd.vwap, BINS))
    return rnd.groupby(["cat", "bin"], observed=True).apply(lambda x: (x.outcome - x.vwap).mean())


def overshoot_cat(e, p, cb):
    b = cb.reindex(pd.MultiIndex.from_arrays([e.cat.values, pd.cut(p, BINS)])).astype(float).values
    return -((e.outcome - p) - b) * e.sgn


def ratio(x, col):
    return x[col].sum() / x.absdp.sum()


BINS = np.linspace(0, 1, 21)


def main():
    out = {}
    rnd = pd.concat([pd.read_parquet(f) for f in glob.glob(f"{EV}/900/r*.parquet")], ignore_index=True)
    rnd["outcome"] = rnd.market.map(outcomes())
    rnd = rnd[rnd.outcome.notna()]
    base_rand = baseline_table(rnd.vwap.values, rnd.outcome.values, BINS)

    e = load(900)
    base_pre = baseline_table(e.y_pre.values, e.outcome.values, BINS)
    print("calibration error (outcome - p), random moments vs pre-move, by price:")
    print(pd.DataFrame({"random": base_rand, "pre-move": base_pre}).dropna().iloc[1:-1:2].round(3).to_string())

    big = e[e.absdp >= MIN_PTS].copy()
    big["os_close_pre"] = overshoot(big, big.p_close, base_pre)
    big["os_close"] = overshoot(big, big.p_close, base_rand)
    print(f"\n[1] overshoot share, pre-move baseline {ratio(big, 'os_close_pre'):.3f} | random baseline {ratio(big, 'os_close'):.3f}")
    print("    by takers (random baseline):", big.groupby("tg", observed=True).apply(lambda x: round(ratio(x, "os_close"), 3)).to_dict())

    # 2. tradability
    t = big[big.entry_vwap.notna()].copy()
    t["os_entry"] = overshoot(t, t.entry_vwap, base_rand)
    t["pnl"] = t.sgn * (t.entry_vwap - t.outcome) * 100          # cents per share, raw
    t["pnl_dollar"] = t.pnl / 100 / np.where(t.sgn > 0, 1 - t.entry_vwap, t.entry_vwap)  # per $ staked
    print(f"\n[2] moves with an entry price within 1 h: {len(t):,} of {len(big):,}; median delay {t.entry_delay.median():.0f}s")
    g2 = t.groupby("tg", observed=True).apply(lambda x: pd.Series({
        "overshoot_close": ratio(x, "os_close"), "overshoot_entry": ratio(x, "os_entry"),
        "fade_cents_per_share": x.pnl.mean(), "fade_return_per_$": x.pnl_dollar.mean(), "moves": len(x)}))
    print(g2.round(3).to_string())
    out["trad"] = g2

    # 3. dynamics on moves with every horizon available
    dyn = t.dropna(subset=["ret_1h", "ret_6h", "ret_24h"]).copy()
    cols = {"close": "os_close", "entry": "os_entry"}
    for h in ("1h", "6h", "24h"):
        dyn["os_" + h] = overshoot(dyn, sigmoid(dyn.L_pre + dyn["ret_" + h] * dyn.move), base_rand)
        cols[h] = "os_" + h
    curve = dyn.groupby("tg", observed=True).apply(lambda x: pd.Series({k: ratio(x, c) for k, c in cols.items()}))
    curve.loc["all"] = {k: ratio(dyn, c) for k, c in cols.items()}
    print(f"\n[3] overshoot remaining over time ({len(dyn):,} moves with all horizons):")
    print(curve.round(3).to_string())
    out["curve"] = curve

    # 4. wallets behind single-trader moves
    w = big[(big.takers == 1) & (big.taker1 > 0)].copy()
    cnt = w.taker1.value_counts()
    top1 = cnt.head(max(1, len(cnt) // 100)).sum() / len(w)
    top10 = cnt.head(max(1, len(cnt) // 10)).sum() / len(w)
    print(f"\n[4] single-trader big moves: {len(w):,} by {len(cnt):,} wallets; top 1% of wallets make {top1:.1%}, top 10% make {top10:.1%}")
    rest = w[~w.taker1.isin(cnt.head(max(1, len(cnt) // 100)).index)]
    print(f"    overshoot share without the top 1% wallets: {ratio(rest, 'os_close'):.3f} (all: {ratio(w, 'os_close'):.3f})")
    rep = w[w.taker1.isin(cnt[cnt >= 10].index)].sort_values("t_close")
    rep["half"] = rep.groupby("taker1").cumcount() < rep.groupby("taker1").taker1.transform("size") / 2
    per = rep.groupby(["taker1", "half"]).apply(lambda x: ratio(x, "os_close")).unstack()
    per = per.dropna()
    r_obs = per.corr().iloc[0, 1]
    rng = np.random.default_rng(0)
    null = []
    for _ in range(200):
        sh = rep.copy()
        sh["taker1"] = rng.permutation(sh.taker1.values)
        sh = sh.sort_values("t_close")
        sh["half"] = sh.groupby("taker1").cumcount() < sh.groupby("taker1").taker1.transform("size") / 2
        p2 = sh.groupby(["taker1", "half"]).apply(lambda x: ratio(x, "os_close")).unstack().dropna()
        null.append(p2.corr().iloc[0, 1])
    print(f"    wallets with 10+ such moves: {len(per):,}; first-half vs second-half overshoot correlation "
          f"{r_obs:.3f} (shuffled null: {np.mean(null):.3f} ± {np.std(null):.3f})")
    out["wallet_corr"] = (r_obs, np.mean(null), np.std(null), len(per))
    per.to_csv("local_data/r03_wallet_halves.csv")

    # 5. definition robustness
    rows = []
    for bar in BARS:
        eb = e if bar == 900 else load(bar)
        for thr in (0.05, 0.10, 0.15):
            x = eb[eb.absdp >= thr].copy()
            x["os"] = overshoot(x, x.p_close, base_rand)
            r = {"bar_min": bar // 60, "threshold": thr, "moves": len(x), "markets": x.market.nunique(), "all": ratio(x, "os")}
            for tg, s in x.groupby("tg", observed=True):
                r[f"takers {tg}"] = ratio(s, "os")
            rows.append(r)
    rob = pd.DataFrame(rows)
    print("\n[5] overshoot share by bar size and threshold:")
    print(rob.round(3).to_string(index=False))
    rob.to_csv("local_data/r03_robustness.csv", index=False)
    # 6. category baselines (reported numbers)
    tags = pd.read_csv("local_data/market_tags.csv", dtype=str)
    rnd["cat"] = rnd.market.map(pd.Series(category(tags.tags).values, index=tags.market_id.astype(int).values)).fillna("other")
    cb = cat_baseline(rnd)
    big["oc"] = overshoot_cat(big, big.p_close, cb)
    t["oc"], t["oe"] = overshoot_cat(t, t.p_close, cb), overshoot_cat(t, t.entry_vwap, cb)
    t["dir"] = np.where(t.sgn > 0, "up", "down")
    print(f"\n[6] category baseline: overshoot {ratio(big, 'oc'):.3f}; by takers",
          big.groupby("tg", observed=True).apply(lambda x: round(ratio(x, "oc"), 3)).to_dict())
    print(big.groupby(["cat", "tg"], observed=True).apply(lambda x: round(ratio(x, "oc"), 3)).unstack().to_string())
    print(t.groupby(["cat", "dir"]).apply(lambda x: round(ratio(x, "oe"), 3)).unstack().to_string())
    dyn = t.dropna(subset=["ret_1h", "ret_6h", "ret_24h"]).copy()
    cols = {"close": "oc", "next trades": "oe"}
    for h in ("1h", "6h", "24h"):
        dyn["oc_" + h] = overshoot_cat(dyn, sigmoid(dyn.L_pre + dyn["ret_" + h] * dyn.move), cb)
        cols[h] = "oc_" + h
    curves = {}
    for name, grp in (("tg", "tg"), ("dir", "dir")):
        c = dyn.groupby(grp, observed=True).apply(lambda x: pd.Series({k: ratio(x, v) for k, v in cols.items()}))
        curves[name] = c
        print(c.round(3).to_string())
    curves["tg"].loc["all"] = {k: ratio(dyn, v) for k, v in cols.items()}
    pd.concat(curves).to_csv("local_data/r03_curves_catbase.csv")
    cb.rename("err").reset_index().astype({"bin": str}).to_csv("local_data/r03_cat_baseline.csv", index=False)

    big.to_parquet("local_data/r03_big_moves_900.parquet", index=False)
    t.to_parquet("local_data/r03_tradable_900.parquet", index=False)
    curve.to_csv("local_data/r03_curve.csv")
    return out


if __name__ == "__main__":
    main()
