"""
Round 2: do big price moves overshoot, and does it depend on how they were made?

Input: the moves table from remote/s2_events.py (local_data/r02_events/e*.parquet), the
markets file (final outcomes) and tags. Uses the VWAP price basis (robust to a sweep's
extreme last fill) and moves of at least 0.4 log-odds.

Metric (no horizon, no ratios of small numbers): the final outcome (1 if YES won, else 0,
markets with a clear 0/1 resolution only) is compared with the price right after the move.
  err_post = outcome - p_close
Prices are not perfectly calibrated (YES is overpriced at every level), so the error
expected at that price level is subtracted. It is estimated from the prices just before
all moves (any size), in 5-point bins:
  excess = err_post - baseline(p_close)
Signed by the move direction, -excess * sign(move) is the **overshoot** in probability
points: how far the move went beyond what the outcome justified. The overshoot share =
sum(overshoot) / sum(|p_close - p_pre|).

Generality: every effect is recomputed within each category and each year.
Confidence intervals: bootstrap over markets.

Usage: python explore/r02_persistence.py
"""
import glob
import sys

import numpy as np
import pandas as pd

MIN_MOVE = 0.4
BASIS = "vwap"
CATS = [  # first match wins
    ("esports", "esports|counter-strike|dota|league-of-legends|valorant"),
    ("sports", "sports|nba|nfl|soccer|tennis|mlb|nhl|ufc|f1|golf|cricket|ncaa"),
    ("elections", "elections|election|primaries|presidential"),
    ("politics", "politics|trump|congress|senate|courts|biden"),
    ("crypto", "crypto|bitcoin|ethereum|solana|airdrop|token"),
    ("economy", "economy|fed|inflation|interest-rates|stocks|business|finance"),
    ("geopolitics", "geopolitics|world|ukraine|russia|israel|middle-east|china|war"),
    ("culture", "culture|pop-culture|movies|music|awards|tech|ai|science|weather"),
]


def category(tags, table=CATS):
    s = pd.Series("other", index=tags.index)
    done = pd.Series(False, index=tags.index)
    for name, pat in table:
        hit = tags.str.contains(pat, na=False) & ~done
        s[hit] = name
        done |= hit
    return s


def sigmoid(x):
    return 1 / (1 + np.exp(-x))


def outcomes():
    mk = pd.read_parquet("local_data/markets_final.parquet", columns=["id", "outcome_prices"])
    first = mk.outcome_prices.str.strip("[]").str.split(",").str[0].str.strip(" '\"")
    y = pd.to_numeric(first, errors="coerce")
    out = pd.Series(np.where(y > 0.99, 1.0, np.where(y < 0.01, 0.0, np.nan)),
                    index=pd.to_numeric(mk.id, errors="coerce"))
    return out[~out.index.duplicated()]


def load(events_dir="local_data/r02_events"):
    e = pd.concat([pd.read_parquet(f) for f in glob.glob(f"{events_dir}/e*.parquet")], ignore_index=True)
    e = e[e.basis == BASIS].copy()
    tags = pd.read_csv("local_data/market_tags.csv", dtype=str)
    e["cat"] = e.market.map(pd.Series(category(tags.tags).values, index=tags.market_id.astype(int).values)).fillna("other")
    e["year"] = pd.to_datetime(e.t_close, unit="s").dt.year
    e["outcome"] = e.market.map(outcomes())
    L_pre = np.log(np.clip(e.y_pre, .01, .99) / (1 - np.clip(e.y_pre, .01, .99)))
    e["p_close"] = sigmoid(L_pre + e.move)
    e = e[e.outcome.notna()]

    bins = np.linspace(0, 1, 21)
    base = e.groupby(pd.cut(e.y_pre, bins), observed=False).apply(lambda x: (x.outcome - x.y_pre).mean())
    e["baseline"] = pd.cut(e.p_close, bins).map(base).astype(float)
    e["overshoot"] = -((e.outcome - e.p_close) - e.baseline) * np.sign(e.move)
    e["absdp"] = (e.p_close - e.y_pre).abs()
    return e, base


def share(df, n_boot=200, seed=0):
    """Overshoot share = sum(overshoot)/sum(|dp|), 90% CI by resampling markets."""
    g = df.groupby("market")[["overshoot", "absdp"]].sum()
    o, d = g.overshoot.values, g.absdp.values
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(g), size=(n_boot, len(g)))
    bs = o[idx].sum(1) / d[idx].sum(1)
    return o.sum() / d.sum(), np.percentile(bs, 5), np.percentile(bs, 95)


def groupings(e):
    return {
        "direction": pd.Series(np.where(e.move > 0, "up", "down"), index=e.index),
        "distinct takers": pd.cut(e.takers, [0, 1, 3, np.inf], labels=["1", "2-3", "4+"]),
        "sweep share of money": pd.cut(e.sweep_share.fillna(0), [-.01, 0, .5, 1.01], labels=["0", "<50%", ">=50%"]),
        "money in the move (USD)": pd.cut(e.usd, [0, 50, 500, 5000, np.inf], labels=["<50", "50-500", "500-5k", ">5k"]),
        "net flow vs move": pd.cut(e.flow_agree, [-1.01, 0, 0.99, 1.01], labels=["against", "mixed", "all with"]),
        "price before": pd.cut(e.y_pre, [0, .2, .4, .6, .8, 1], labels=["<.2", ".2-.4", ".4-.6", ".6-.8", ">.8"]),
        "time to end date": pd.cut(e.days_to_end, [-np.inf, 1, 7, 30, np.inf], labels=["<1d", "1-7d", "7-30d", ">30d"]),
    }


def main():
    e, base = load()
    big = e[e.move.abs() >= MIN_MOVE].copy()
    m, lo, hi = share(big)
    print(f"{len(big):,} moves in {big.market.nunique():,} markets; overshoot share {m:.3f} [{lo:.3f}, {hi:.3f}]")
    rows = [dict(grouping="all", level="all", scope="all", share=m, lo=lo, hi=hi, moves=len(big),
                 markets=big.market.nunique())]
    for scope_col in ("cat", "year"):
        for sv, s in big.groupby(scope_col):
            if s.market.nunique() >= 50:
                rows.append(dict(grouping="all", level="all", scope=f"{scope_col}={sv}", share=share(s, 0)[0]
                                 if False else s.overshoot.sum() / s.absdp.sum(), lo=np.nan, hi=np.nan,
                                 moves=len(s), markets=s.market.nunique()))
    for gname, gser in groupings(big).items():
        big["_g"] = gser
        for lvl, sub in big.groupby("_g", observed=True):
            m, lo, hi = share(sub)
            rows.append(dict(grouping=gname, level=str(lvl), scope="all", share=m, lo=lo, hi=hi,
                             moves=len(sub), markets=sub.market.nunique()))
            for scope_col in ("cat", "year"):
                for sv, s in sub.groupby(scope_col):
                    if s.market.nunique() >= 50:
                        rows.append(dict(grouping=gname, level=str(lvl), scope=f"{scope_col}={sv}",
                                         share=s.overshoot.sum() / s.absdp.sum(), lo=np.nan, hi=np.nan,
                                         moves=len(s), markets=s.market.nunique()))
    res = pd.DataFrame(rows)
    res.to_csv("local_data/r02_summary.csv", index=False)
    big.drop(columns="_g").to_parquet("local_data/r02_big_moves.parquet", index=False)
    print(res[res.scope == "all"].round(3).to_string(index=False))
    return big, res, base


if __name__ == "__main__":
    main()
