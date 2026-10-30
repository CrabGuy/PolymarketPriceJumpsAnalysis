"""
Round 6, part C: which markets see single traders over-push the price?

Input: local_data/r06/micro/k*.parquet (stage 6, one row per event market: concentration of
taker volume and microstructure measures, all before the resolution cut),
local_data/r03_big_moves_main.parquet (every big 30-min move) and the tags.

Per market:
  one-trader rate    big moves made by a single taker per 100 active 30-min bars
  one-trader share   share of the market's big moves made by a single taker
  overshoot (1)      overshoot of its single-taker moves (ratio of sums; calibration by
                     question type, as in rounds 4-5)
Measures (stage 6): Gini and Herfindahl of taker volume, top wallet's share, top 10% share,
Kyle's lambda (log-odds change per $1k of signed flow, 30-min bars), variance ratio VR(4)
(< 1 = changes reverse), Roll spread, median buy-sell gap in the same minute,
two-sidedness of taker flow, plus size (takers, trades, $).

  1  Spearman correlations between each measure and the one-trader rate / share / overshoot,
     raw and partial (controlling for log takers, log $ and log bars, rank-based).
  2  Markets where it happens a lot (top quarter of the one-trader rate) vs never (no
     single-taker big move), markets with 100+ active bars: medians and rank effect size.
  3  Logistic regression of "a lot" vs the rest on standardized (rank-normal) measures plus
     category: which measures matter when all are in together.
  4  Overshoot of single-taker and crowd moves by quintile of Gini, lambda, VR(4), spread.
  5  The same across tags (200+ markets): medians, rates, and correlations across tags.

Usage: python explore/r06_concentration.py
"""
import glob
import sys

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, "explore")
from r02_persistence import category  # noqa: E402
from r04_types import osh, market_info  # noqa: E402
from r06_fade import calib  # noqa: E402

OUT = "local_data/r06/"
MEASURES = ["gini", "hhi", "top1", "top10", "kyle_lambda", "vr4", "roll", "spread_med", "two_sided",
            "log_takers", "log_usd", "log_trades"]
CONTROLS = ["log_takers", "log_usd", "log_bars"]
TARGETS = ["rate1", "share1", "os1"]
NAMES = {"gini": "Gini of taker $", "hhi": "Herfindahl of taker $", "top1": "top wallet's share",
         "top10": "top 10% wallets' share", "kyle_lambda": "Kyle's lambda", "vr4": "variance ratio VR(4)",
         "roll": "Roll spread", "spread_med": "buy-sell gap (1 min)", "two_sided": "two-sidedness",
         "log_takers": "takers (log)", "log_usd": "money traded (log)", "log_trades": "trades (log)",
         "rate1": "one-trader moves per 100 bars", "share1": "share of moves by one trader",
         "os1": "overshoot of one-trader moves"}


MIN_BARS = 20           # markets need this many active bars (override: --min-bars N, dry run)


def load():
    mk = pd.concat([pd.read_parquet(f) for f in glob.glob(OUT + "micro/k*.parquet")], ignore_index=True)
    mk = mk[(mk.bars >= MIN_BARS) & (mk.usd > 0)].copy()
    mk["log_takers"] = np.log10(mk.takers)
    mk["log_usd"] = np.log10(mk.usd)
    mk["log_trades"] = np.log10(mk.trades)
    mk["log_bars"] = np.log10(mk.bars)
    info = market_info()
    big = pd.read_parquet("local_data/r03_big_moves_main.parquet").join(info, on="market")
    big["oq"] = osh(big, big.p_close, calib(), "qtype")
    big = big[big.oq.notna()]
    one = big[big.tg == "1"]
    g = big.groupby("market")
    mk = mk.set_index("market")
    mk["moves"] = g.size()
    mk["moves1"] = one.groupby("market").size()
    mk[["moves", "moves1"]] = mk[["moves", "moves1"]].fillna(0)
    mk["rate1"] = 100 * mk.moves1 / mk.bars
    mk["share1"] = (mk.moves1 / mk.moves).where(mk.moves >= 3)
    s1 = one.groupby("market").agg(oq=("oq", "sum"), absdp=("absdp", "sum"), n=("oq", "size"))
    mk["os1"] = (s1.oq / s1.absdp).where(s1.n >= 3)
    mk["os1_num"], mk["os1_den"] = s1.oq, s1.absdp
    tags = pd.read_csv("local_data/market_tags.csv", dtype=str)
    cat = pd.Series(category(tags.tags).values, index=tags.market_id.astype(int).values)
    mk["cat"] = cat[~cat.index.duplicated()].reindex(mk.index).fillna("other")
    mk = mk.join(info[["qtype"]])
    return mk.reset_index(), big


def partial_spearman(d, x, y, controls):
    z = d[[x, y] + controls].dropna().rank()
    C = np.column_stack([np.ones(len(z))] + [z[c].values for c in controls])
    res = {}
    for v in (x, y):
        b, *_ = np.linalg.lstsq(C, z[v].values, rcond=None)
        res[v] = z[v].values - C @ b
    return np.corrcoef(res[x], res[y])[0, 1], len(z)


def correlations(mk):
    rows = []
    for m in MEASURES:
        for tg in TARGETS:
            d = mk[list(dict.fromkeys([m, tg] + CONTROLS))].dropna()
            rho, p = stats.spearmanr(d[m], d[tg])
            ctr = [c for c in CONTROLS if c != m]
            prho, n = partial_spearman(mk, m, tg, ctr)
            rows.append({"measure": m, "target": tg, "markets": len(d), "spearman": rho, "partial": prho})
    res = pd.DataFrame(rows)
    print("\n[1] Spearman correlation with each target (partial = controlling for size):")
    print(res.pivot(index="measure", columns="target", values=["spearman", "partial"]).round(3).to_string())
    return res


def stability(mk):
    """Partial correlations with the one-trader rate within each year (of the end date) and
    each category: does the pattern hold everywhere?"""
    info = pd.read_parquet("local_data/markets_final.parquet", columns=["id", "end_date"])
    info = info[pd.to_numeric(info.id, errors="coerce").notna()]
    yr = pd.Series(info.end_date.dt.year.values, index=info.id.astype(int).values)
    mk = mk.assign(year=yr[~yr.index.duplicated()].reindex(mk.index).values)
    rows = []
    for split in ("year", "cat"):
        for v, d in mk.groupby(split):
            if len(d) < 1000:
                continue
            r = {"split": split, "value": v, "markets": len(d)}
            for m in ("roll", "kyle_lambda", "gini", "top1"):
                r[m] = partial_spearman(d, m, "rate1", [c for c in CONTROLS if c != m])[0]
            rows.append(r)
    res = pd.DataFrame(rows)
    print("\n[stability] partial correlation with the one-trader rate:")
    print(res.round(3).to_string(index=False))
    return res


def high_vs_never(mk):
    """Markets with 100+ bars and at least 3 big moves: 'a lot' = top quarter of the
    one-trader rate, 'never' = big moves but none by a single trader."""
    d = mk[(mk.bars >= 100) & (mk.moves >= 3)].copy()
    q75 = d.rate1.quantile(0.75)
    d["group"] = np.where(d.rate1 >= q75, "a lot", np.where(d.moves1 == 0, "never", "in between"))
    rows = []
    for m in MEASURES + ["log_bars"]:
        a, b = d.loc[d.group == "a lot", m].dropna(), d.loc[d.group == "never", m].dropna()
        u = stats.mannwhitneyu(a, b)
        rows.append({"measure": m, "median (a lot)": a.median(), "median (never)": b.median(),
                     "median (in between)": d.loc[d.group == "in between", m].median(),
                     # probability that a random "a lot" market has a higher value than a "never" one
                     "P(a lot > never)": u.statistic / (len(a) * len(b)), "p": u.pvalue})
    res = pd.DataFrame(rows)
    print(f"\n[2] markets with 100+ bars: {d.group.value_counts().to_dict()}; 'a lot' = one-trader rate >= {q75:.2f} per 100 bars")
    print(res.round(3).to_string(index=False))
    mix = pd.crosstab(d.cat, d.group, normalize="index").round(3)
    print(mix.to_string())
    return res, d


def rank_normal(x):
    r = x.rank(pct=True) - 0.5 / x.notna().sum()
    return pd.Series(stats.norm.ppf(r.clip(1e-6, 1 - 1e-6)), index=x.index)


def logit_fit(X, y, iters=50):
    b = np.zeros(X.shape[1])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-X @ b))
        W = p * (1 - p)
        H = X.T @ (X * W[:, None]) + 1e-6 * np.eye(X.shape[1])
        step = np.linalg.solve(H, X.T @ (y - p))
        b += step
        if np.abs(step).max() < 1e-8:
            break
    se = np.sqrt(np.diag(np.linalg.inv(H)))
    return b, se


def logistic(d):
    use = ["gini", "top1", "kyle_lambda", "vr4", "roll", "two_sided", "log_takers", "log_usd", "log_bars"]
    x = d[use + ["cat", "group"]].dropna()
    y = (x.group == "a lot").astype(float).values
    Z = np.column_stack([rank_normal(x[c]).values for c in use])
    cats = sorted(x.cat.unique())
    D = np.column_stack([(x.cat == c).astype(float).values for c in cats if c != "other"])
    X = np.column_stack([np.ones(len(x)), Z, D])
    b, se = logit_fit(X, y)
    names = ["const"] + use + [f"category: {c}" for c in cats if c != "other"]
    res = pd.DataFrame({"term": names, "coef": b, "se": se, "odds ratio per sd": np.exp(b), "z": b / se})
    print(f"\n[3] logistic regression, {len(x):,} markets, {y.mean():.1%} 'a lot':")
    print(res.round(3).to_string(index=False))
    return res


def by_quintile(mk, big):
    rows = []
    mv = big.merge(mk[["market", "gini", "kyle_lambda", "vr4", "spread_med", "two_sided", "log_takers"]], on="market")
    for m in ["gini", "kyle_lambda", "vr4", "spread_med", "two_sided", "log_takers"]:
        q = pd.qcut(mk[m], 5, labels=False, duplicates="drop")
        mv["q"] = mv.market.map(pd.Series(q.values, index=mk.market))
        for (qq, tg), x in mv.dropna(subset=["q"]).groupby(["q", "tg"], observed=True):
            rows.append({"measure": m, "quintile": int(qq) + 1, "takers": tg, "moves": len(x),
                         "overshoot": x.oq.sum() / x.absdp.sum(),
                         "median value": mk.loc[q == qq, m].median()})
    res = pd.DataFrame(rows)
    piv = res.pivot_table(index=["measure", "quintile"], columns="takers", values="overshoot")
    print("\n[4] overshoot by market quintile of each measure (1 = lowest):")
    print(piv.round(3).to_string())
    return res


def tags(mk, big):
    t = pd.read_csv("local_data/market_tags.csv", dtype=str)
    t = t.assign(market=t.market_id.astype(int), tag=t.tags.str.split(";")).explode("tag")
    t = t[~t.tag.isin(["all", "hide-from-new", "games"])][["market", "tag"]].drop_duplicates()
    d = mk.merge(t, on="market")
    cnt = d.groupby("tag").market.nunique()
    d = d[d.tag.isin(cnt[cnt >= 200].index)]
    one = big[big.tg == "1"].merge(t, on="market")
    crowd = big[big.tg == "4+"].merge(t, on="market")
    g = d.groupby("tag")
    res = pd.DataFrame({
        "markets": g.market.nunique(),
        "gini": g.gini.median(), "top1": g.top1.median(), "kyle_lambda": g.kyle_lambda.median(),
        "vr4": g.vr4.median(), "two_sided": g.two_sided.median(), "takers": g.takers.median(),
        "rate1": 100 * g.moves1.sum() / g.bars.sum(),
        "share1": g.moves1.sum() / g.moves.sum(),
    })
    o1 = one[one.market.isin(d.market)].groupby("tag")
    oc = crowd[crowd.market.isin(d.market)].groupby("tag")
    res["os1"] = o1.oq.sum() / o1.absdp.sum()
    res["os_crowd"] = oc.oq.sum() / oc.absdp.sum()
    res = res.dropna(subset=["os1"])
    rows = []
    for m in ["gini", "top1", "kyle_lambda", "vr4", "two_sided", "takers"]:
        for tg in ["rate1", "share1", "os1", "os_crowd"]:
            x = res[[m, tg]].dropna()
            rho, p = stats.spearmanr(x[m], x[tg])
            rows.append({"measure": m, "target": tg, "tags": len(x), "spearman": rho, "p": p})
    cor = pd.DataFrame(rows)
    print(f"\n[5] tags with 200+ markets: {len(res)}")
    print(res.sort_values("rate1", ascending=False).round(3).head(25).to_string())
    print(cor.pivot(index="measure", columns="target", values="spearman").round(2).to_string())
    return res, cor


def main():
    mk, big = load()
    print(f"markets: {len(mk):,} (20+ active bars); with a big move: {(mk.moves > 0).sum():,}; "
          f"with a one-trader move: {(mk.moves1 > 0).sum():,}")
    print(mk[MEASURES + TARGETS].describe().T.round(3).to_string())
    cor = correlations(mk)
    if MIN_BARS != 20:                       # filter test: print only
        print(cor.round(3).to_string())
        return
    st = stability(mk)
    st.to_csv(OUT + "r06_conc_stability.csv", index=False)
    hv, d = high_vs_never(mk)
    lg = logistic(d)
    qt = by_quintile(mk, big)
    tg, tgc = tags(mk, big)
    cor.to_csv(OUT + "r06_conc_corr.csv", index=False)
    hv.to_csv(OUT + "r06_conc_high_vs_never.csv", index=False)
    lg.to_csv(OUT + "r06_conc_logit.csv", index=False)
    qt.to_csv(OUT + "r06_conc_quintiles.csv", index=False)
    tg.to_csv(OUT + "r06_conc_tags.csv")
    tgc.to_csv(OUT + "r06_conc_tags_corr.csv", index=False)
    mk.to_parquet(OUT + "r06_markets.parquet", index=False)


if __name__ == "__main__":
    if "--min-bars" in sys.argv:
        MIN_BARS = int(sys.argv[sys.argv.index("--min-bars") + 1])
    main()
