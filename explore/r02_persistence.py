"""
Round 2: do big price moves overshoot, and does it depend on how they were made?

Input: the moves table from remote/s2_events.py (local_data/r02_events/e*.parquet), the
markets file (final outcomes) and tags. Uses the VWAP price basis (robust to a sweep's
extreme last fill) and price jumps: moves of at least MIN_PTS (16 probability points).

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

# Every value below was set by the elbow method (explore/r12_joint.py, explore/r12_params.py); the
# server stages use the same values (remote/s2_events.py, s3_events.py).
MIN_PTS = 0.16       # a price jump: at least 16 points
BAR = 1800           # slot length in seconds (30 minutes)
LIFE_CUT_START = 0.075  # share of each market's life left out at the start
LIFE_CUT_END = 0.045    # share left out at the end
EDGE = 0.03          # settled = the price left [EDGE, 1 - EDGE] for good
CLIP = 0.02          # prices are clipped to [CLIP, 1 - CLIP] before jumps and log-odds are computed
N_NEXT = 7           # next trades: how many
T_NEXT = 2700        # next trades: within this many seconds
OUTCOME_Q = 0.995    # a market resolved YES if its first outcome price is above this, NO if below 1 - it
# Statistics and groups (explore/r12_params.py)
SAMPLE_SHARE = 0.01  # share of slots drawn at random for the usual-error baseline
N_RESAMPLES = 150    # market resamples for every uncertainty range
N_BINS = 20          # price bins of the usual-error baseline
K_CROWD = 5          # a "crowd" jump has at least this many traders
TG_EDGES = [0, 1, K_CROWD - 1, np.inf]                       # trader groups: 1 / a few / a crowd
TG_LABELS = ["1", f"2-{K_CROWD - 1}", f"{K_CROWD}+"]
FEW, CROWD = TG_LABELS[1], TG_LABELS[2]
MONEY_X = 200        # "big money": at least this many dollars traded in the jump's slot
WALLET_MIN = 8       # wallets need this many single-trader jumps for the persistence check (F2)
CONTROL_BINS = 3     # quantile bins of each continuous control in the F2 regression
OFFSET_LO, OFFSET_HI = 0.55, 1.0   # F4: below LO = not offset, LO-HI = partly, from HI = offset
BET_BAND = 0.0       # F5: bets only on jumps that start inside [BET_BAND, 1 - BET_BAND] (flat curve: none)
TRIM = 0.025         # F5: share of returns trimmed at each end
MIN_SLOTS = 50       # F6: markets need this many slots with trades
VR_LAG = 6           # F6: variance ratio lag, in slots
SPREAD_WIN = 120     # F6: buy-sell gap window, seconds
TAG_MIN = 200        # F6: tags need this many markets
TAG_MIN_JUMPS = 200  # F1: tags need this many markets with price jumps
FOLLOW_UP = 1200     # F10: a new trade within this many seconds of the slot's close
# Crypto up/down (F8), from explore/r12_joint.py (mode cx) and r12_params.py
CX_MIN_PTS = 0.18
CX_MOVED = 0.75      # a related market "moved" if its log-odds changed by at least this
CX_POINTS = 30       # points per market in the crypto chains (F9)
CX_MIN_TRADES = 50   # crypto markets need this many trades in their window (F9)
# Pattern search (F9), from explore/r12_f9.py
F9_STEP = 10         # minutes between the points of a path
F9_BEFORE = 30       # minutes of path before the slot's close
F9_AFTER = 120       # minutes of path after it
F9_MIN_CHANGES = 3   # a path needs price changes in at least this many post-jump steps
F9_HOURS_LEFT = 2    # a jump needs at least this many hours of the market's window left
F9_RADIUS_PCT = 15   # match radius = this percentile of the surrogates' matrix profile
F9_SAMPLE = 10**9    # no sampling: every path that passes the filters is used
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


def random_slots():
    """The random slots of the usual-error baseline: a SAMPLE_SHARE draw of all used slots. The
    server keeps a 5% draw (remote/s3_events.SAMPLE); a fixed sub-draw of it gives SAMPLE_SHARE."""
    r = pd.concat([pd.read_parquet(f) for f in sorted(glob.glob(f"local_data/r03_events/{BAR}/r*.parquet"))],
                  ignore_index=True)
    keep = np.random.default_rng(0).random(len(r)) < SAMPLE_SHARE / 0.05
    return r[keep].reset_index(drop=True)


def outcomes():
    mk = pd.read_parquet("local_data/markets_final.parquet", columns=["id", "outcome_prices"])
    first = mk.outcome_prices.str.strip("[]").str.split(",").str[0].str.strip(" '\"")
    y = pd.to_numeric(first, errors="coerce")
    out = pd.Series(np.where(y > OUTCOME_Q, 1.0, np.where(y < 1 - OUTCOME_Q, 0.0, np.nan)),
                    index=pd.to_numeric(mk.id, errors="coerce"))
    return out[~out.index.duplicated()]


def load(events_dir="local_data/r02_events"):
    e = pd.concat([pd.read_parquet(f) for f in glob.glob(f"{events_dir}/e*.parquet")], ignore_index=True)
    e = e[e.basis == BASIS].copy()
    tags = pd.read_csv("local_data/market_tags.csv", dtype=str)
    e["cat"] = e.market.map(pd.Series(category(tags.tags).values, index=tags.market_id.astype(int).values)).fillna("other")
    e["year"] = pd.to_datetime(e.t_close, unit="s").dt.year
    e["outcome"] = e.market.map(outcomes())
    L_pre = np.log(np.clip(e.y_pre, CLIP, 1 - CLIP) / (1 - np.clip(e.y_pre, CLIP, 1 - CLIP)))
    e["p_close"] = sigmoid(L_pre + e.move)
    e = e[e.outcome.notna()]

    bins = np.linspace(0, 1, 21)
    base = e.groupby(pd.cut(e.y_pre, bins), observed=False).apply(lambda x: (x.outcome - x.y_pre).mean())
    e["baseline"] = pd.cut(e.p_close, bins).map(base).astype(float)
    e["overshoot"] = -((e.outcome - e.p_close) - e.baseline) * np.sign(e.move)
    e["absdp"] = (e.p_close - e.y_pre).abs()
    return e, base


def share(df, n_boot=N_RESAMPLES, seed=0):
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
        "distinct takers": pd.cut(e.takers, TG_EDGES, labels=TG_LABELS),
        "sweep share of money": pd.cut(e.sweep_share.fillna(0), [-.01, 0, .5, 1.01], labels=["0", "<50%", ">=50%"]),
        "money in the move (USD)": pd.cut(e.usd, [0, 50, 500, 5000, np.inf], labels=["<50", "50-500", "500-5k", ">5k"]),
        "net flow vs move": pd.cut(e.flow_agree, [-1.01, 0, 0.99, 1.01], labels=["against", "mixed", "all with"]),
        "price before": pd.cut(e.y_pre, [0, .2, .4, .6, .8, 1], labels=["<.2", ".2-.4", ".4-.6", ".6-.8", ">.8"]),
        "time to end date": pd.cut(e.days_to_end, [-np.inf, 1, 7, 30, np.inf], labels=["<1d", "1-7d", "7-30d", ">30d"]),
    }


def main():
    e, base = load()
    big = e[e.absdp >= MIN_PTS].copy()
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
