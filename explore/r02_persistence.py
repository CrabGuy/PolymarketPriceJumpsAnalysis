"""
Every parameter of the analysis, the shared helpers, and the main result (section 4.1 of the
report): after a price jump the price goes too far.

Input: the moves table from remote/s2_events.py (local_data/r02_events/e*.parquet), every slot
with trades from remote/s3_events.py (local_data/r03_events/<BAR>/r*.parquet), the markets file
(final outcomes) and the tags.

A price jump: a slot whose VWAP price is at least MIN_PTS away from the previous slot with
trades, inside the market's window. The final outcome O (1 if YES won, 0 if NO; markets with a
clear outcome only) is compared with the price p right after the jump. Prices are not perfectly
calibrated even at quiet moments, so the calibration error b(p) is subtracted: the mean of
(O - price) over every slot with trades inside the market windows (no sample), per category and
price bin (N_BINS equal bins, as in reliability diagrams). For a jump j with direction d_j:
  o_j = -[(O_j - p_j) - b(p_j)] * d_j,      overshoot = sum(o_j) / sum(|p_j - p_pre_j|)
95% ranges: percentiles 2.5 and 97.5 over N_RESAMPLES resamples of whole markets.

Prints and writes local_data/r02_summary.csv (all jumps, by category, by year, by trader group
and money in the slot) and local_data/r02_big_moves.parquet.
Usage: python explore/r02_persistence.py
"""
import glob
import os

import numpy as np
import pandas as pd

MARKETS = os.environ.get("PM_MARKETS", "local_data/markets_final.parquet")   # data files (the server runs set these)
TAGS = os.environ.get("PM_TAGS", "local_data/market_tags.csv")
# What a price jump is: knees of the joint elbow search (explore/r12_joint.py); the server stages
# use the same values (remote/s2_events.py, s3_events.py, s6_micro.py)
MIN_PTS = 0.15       # a price jump: at least 15 points
BAR = 1800           # slot length in seconds (30 minutes)
LIFE_CUT_START = 0.07  # share of each market's life left out at the start
LIFE_CUT_END = 0.045   # share left out at the end
EDGE = 0.03          # settled = the price left [EDGE, 1 - EDGE] for good
CLIP = 0.02          # prices clipped to [CLIP, 1 - CLIP] before log-odds (flat curve: kept as a stated guard)
N_NEXT = 5           # next trades: how many
T_NEXT = 2700        # next trades: within this many seconds
OUTCOME_Q = 0.995    # resolved YES if the first outcome price is above this, NO if below 1 - it (elbow)
# Statistics (from the literature; consegna.md, section 1)
N_RESAMPLES = 1000   # market resamples for every 95% range (Efron and Tibshirani 1993, sec. 12.6)
N_BINS = 10          # equal price bins of the calibration error b(p) (Naeini, Cooper and Hauskrecht 2015)
BINS = np.linspace(0, 1, N_BINS + 1)
# Groups and thresholds (knees, explore/r12_params.py)
K_CROWD = 5          # a "crowd" jump has at least this many traders
TG_EDGES = [0, 1, K_CROWD - 1, np.inf]                       # trader groups: 1 / a few / a crowd
TG_LABELS = ["1", f"2-{K_CROWD - 1}", f"{K_CROWD}+"]
FEW, CROWD = TG_LABELS[1], TG_LABELS[2]
MONEY_X = 200        # "big money": at least this many dollars traded in the jump's slot
BET_BAND = 0.0       # bets only on jumps that start inside [BET_BAND, 1 - BET_BAND] (flat curve: none)
TRIM = 0.025         # bets: share of returns brought to the limit at each end
# Crypto up/down markets (explore/r12_joint.py cx, r12_params.py)
CX_SLOT = 60         # slot length in seconds
CX_MIN_PTS = 0.18
CX_CLIP = 0.03       # prices clipped to [CX_CLIP, 1 - CX_CLIP]
CX_K_CROWD = 6       # a crowd jump has at least this many traders
CX_TG_EDGES = [0, 1, CX_K_CROWD - 1, np.inf]
CX_TG_LABELS = ["1", f"2-{CX_K_CROWD - 1}", f"{CX_K_CROWD}+"]
CX_OUTCOME_Q = 0.6   # crypto prices settle at exactly 0, 1 or a split
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


def outcomes(q=None):
    mk = pd.read_parquet(MARKETS, columns=["id", "outcome_prices"])
    first = mk.outcome_prices.str.strip("[]").str.split(",").str[0].str.strip(" '\"")
    y = pd.to_numeric(first, errors="coerce")
    q = OUTCOME_Q if q is None else q
    out = pd.Series(np.where(y > q, 1.0, np.where(y < 1 - q, 0.0, np.nan)),
                    index=pd.to_numeric(mk.id, errors="coerce"))
    return out[~out.index.duplicated()]


def random_slots():
    """Every slot with trades inside the market windows (remote/s3_events.py, r*.parquet): the
    data of the calibration error b(p)."""
    return pd.concat([pd.read_parquet(f) for f in sorted(glob.glob(f"local_data/r03_events/{BAR}/r*.parquet"))],
                     ignore_index=True)


def with_cat(df):
    tags = pd.read_csv(TAGS, dtype=str)
    cats = pd.Series(category(tags.tags).values, index=tags.market_id.astype(int).values)
    return df.assign(cat=df.market.map(cats[~cats.index.duplicated()]).fillna("other"))


def cat_baseline(rnd, bins=None):
    """Calibration error b(p): mean (outcome - price) per (category, price bin) over all slots."""
    bins = BINS if bins is None else bins
    rnd = rnd.assign(bin=pd.cut(rnd.vwap, bins))
    return rnd.groupby(["cat", "bin"], observed=True).apply(lambda x: (x.outcome - x.vwap).mean())


def overshoot_cat(e, p, cb, bins=None):
    """Overshoot (probability points) still present if the price is p, with b(p) from cat_baseline."""
    bins = BINS if bins is None else bins
    b = cb.reindex(pd.MultiIndex.from_arrays([e.cat.values, pd.cut(p, bins)])).astype(float).values
    return -((e.outcome - p) - b) * e.sgn


def calibration():
    """b(p) of the event markets: every slot with trades, with an outcome, per category."""
    r = random_slots()
    r["outcome"] = r.market.map(outcomes())
    return cat_baseline(with_cat(r[r.outcome.notna()]))


def boot_share(x, col, n=N_RESAMPLES, seed=0, den="absdp"):
    """95% range of sum(col) / sum(den), resampling whole markets n times."""
    g = x.groupby("market")[[col, den]].sum()
    a, d = g[col].values, g[den].values
    idx = np.random.default_rng(seed).integers(0, len(g), size=(n, len(g)))
    return np.percentile(a[idx].sum(1) / d[idx].sum(1), [2.5, 97.5])


def share(df, col="overshoot", n_boot=N_RESAMPLES, seed=0):
    """Overshoot share = sum(col) / sum(|dp|), with its 95% range."""
    lo, hi = boot_share(df, col, n_boot, seed)
    return df[col].sum() / df.absdp.sum(), lo, hi


def load(events_dir="local_data/r02_events"):
    e = pd.concat([pd.read_parquet(f) for f in glob.glob(f"{events_dir}/e*.parquet")], ignore_index=True)
    e = with_cat(e[e.basis == BASIS].copy())
    e["year"] = pd.to_datetime(e.t_close, unit="s").dt.year
    e["outcome"] = e.market.map(outcomes())
    L_pre = np.log(np.clip(e.y_pre, CLIP, 1 - CLIP) / (1 - np.clip(e.y_pre, CLIP, 1 - CLIP)))
    e["p_close"] = sigmoid(L_pre + e.move)
    e = e[e.outcome.notna()].copy()
    e["sgn"] = np.sign(e.move)
    e["overshoot"] = overshoot_cat(e, e.p_close, calibration())
    e["absdp"] = (e.p_close - e.y_pre).abs()
    return e


def main():
    e = load()
    big = e[e.absdp >= MIN_PTS].copy()
    big["tg"] = pd.cut(big.takers, TG_EDGES, labels=TG_LABELS).astype(str)
    big["money"] = np.where(big.usd >= MONEY_X, f">= {MONEY_X}", f"< {MONEY_X}")
    rows = []

    def add(kind, level, x):
        m, lo, hi = share(x)
        rows.append(dict(split=kind, level=str(level), share=m, lo=lo, hi=hi, jumps=len(x), markets=x.market.nunique()))

    add("all", "all", big)
    for col in ("cat", "year", "tg"):
        for v, x in big.groupby(col):
            add(col, v, x)
    for (mo, tg), x in big.groupby(["money", "tg"]):
        add("money x tg", f"{mo} / {tg}", x)
    res = pd.DataFrame(rows)
    res.to_csv("local_data/r02_summary.csv", index=False)
    big.to_parquet("local_data/r02_big_moves.parquet", index=False)
    pd.set_option("display.width", 200)
    print(f"{len(big):,} price jumps in {big.market.nunique():,} markets")
    print(res.round(4).to_string(index=False))
    return big, res


if __name__ == "__main__":
    main()
