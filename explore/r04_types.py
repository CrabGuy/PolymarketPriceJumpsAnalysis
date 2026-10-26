"""
Round 4, part 1: overshoot by question type, tag and market duration.

Question types come from the question text (first rule that matches):
  mention    "Will X say ...", "mention"
  matchup    "A vs. B" (games, esports, fights)
  count      ranges and counts ("46-49 times", "exactly 6", "5+ times", "or more")
  price      a dollar threshold ("above $680", "FDV above $50M")
  winner     who wins / is elected / nominated / "next X"
  deadline   something happens "by" / "before" a date, "this week", "end of"
  other
Calibration baselines are per question type (random moments). Timing is also expressed
relative to the market's scheduled lifetime (created_at to end_date), since 10 minutes is
a large share of a short market.

Input: local_data/r03_big_moves_900.parquet, r03_tradable_900.parquet and the random
sample in local_data/r03_events/900/r*.parquet.
Usage: python explore/r04_types.py
"""
import glob
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "explore")
from r02_persistence import outcomes, sigmoid  # noqa: E402
from r03_robustness import BINS  # noqa: E402

TYPES = [
    ("mention", r"\bsays?\b|\bsaid\b|\bmention"),
    ("matchup", r"\bvs\.?\s|\bv\.\s"),
    ("count", r"\d+\s*[-–]\s*\d+|exactly \d|\d+\+|\d+ or more|or more times|how many|\btimes\b"),
    ("price", r"\$\s?\d"),
    ("winner", r"\bwins?\b|\bwinner\b|\bnext (prime minister|president|ceo|pope|leader|coin)|nominat|elected"),
    ("deadline", r"\bby\b|\bbefore\b|this week|end of|\bin (2024|2025|2026)\b"),
]
LIFE_BINS = [0, 1, 7, 30, np.inf]
LIFE_LABELS = ["<1 day", "1-7 days", "7-30 days", ">30 days"]


def market_info():
    mk = pd.read_parquet("local_data/markets_final.parquet", columns=["id", "question", "created_at", "end_date"])
    mk = mk[pd.to_numeric(mk.id, errors="coerce").notna()].copy()
    mk["market"] = mk.id.astype(int)
    q = mk.question.fillna("").str.lower()
    mk["qtype"] = "other"
    done = pd.Series(False, index=mk.index)
    for name, pat in TYPES:
        hit = q.str.contains(pat, regex=True) & ~done
        mk.loc[hit, "qtype"] = name
        done |= hit
    mk["life_days"] = (mk.end_date - mk.created_at).dt.total_seconds() / 86400
    return mk.drop_duplicates("market").set_index("market")[["qtype", "life_days", "question"]]


def baseline(rnd, key):
    rnd = rnd.assign(bin=pd.cut(rnd.vwap, BINS))
    return rnd.groupby([key, "bin"], observed=True).apply(lambda x: (x.outcome - x.vwap).mean())


def osh(e, p, cb, key):
    b = pd.Series(list(zip(e[key], pd.cut(p, BINS)))).map(cb).astype(float).values
    return -((e.outcome - p) - b) * e.sgn


def share(x, col):
    return x[col].sum() / x.absdp.sum()


def main():
    info = market_info()
    rnd = pd.concat([pd.read_parquet(f) for f in glob.glob("local_data/r03_events/900/r*.parquet")], ignore_index=True)
    rnd["outcome"] = rnd.market.map(outcomes())
    rnd = rnd[rnd.outcome.notna()].join(info, on="market")
    cb = baseline(rnd, "qtype")
    print("calibration (outcome - price) at random moments by question type:",
          rnd.groupby("qtype").apply(lambda x: round((x.outcome - x.vwap).mean(), 3)).to_dict())

    t = pd.read_parquet("local_data/r03_tradable_900.parquet").join(info, on="market")
    big = pd.read_parquet("local_data/r03_big_moves_900.parquet").join(info, on="market")
    for d in (t, big):
        d["oq"] = osh(d, d.p_close, cb, "qtype")
        d["life"] = pd.cut(d.life_days, LIFE_BINS, labels=LIFE_LABELS)
        d["dir"] = np.where(d.sgn > 0, "up", "down")
    t["oqe"] = osh(t, t.entry_vwap, cb, "qtype")
    t["delay_share"] = t.entry_delay / (t.life_days * 86400)

    rows = []
    for qt, x in t.groupby("qtype"):
        r = {"qtype": qt, "markets": x.market.nunique(), "moves": len(x),
             "close": share(x, "oq"), "next trades": share(x, "oqe")}
        for tg in ("1", "4+"):
            s = x[x.tg == tg]
            r[f"close, {tg} taker"] = share(s, "oq")
            r[f"next, {tg} taker"] = share(s, "oqe")
        for dr in ("up", "down"):
            s = x[x.dir == dr]
            r[f"next, {dr}"] = share(s, "oqe")
        rows.append(r)
    by_type = pd.DataFrame(rows).set_index("qtype")
    print("\novershoot by question type (type-specific baseline):")
    print(by_type.round(3).to_string())

    rows = []
    for lf, x in t.groupby("life", observed=True):
        r = {"lifetime": lf, "markets": x.market.nunique(), "moves": len(x),
             "median delay to next trades (% of life)": x.delay_share.median() * 100,
             "close": share(x, "oq"), "next trades": share(x, "oqe")}
        for tg in ("1", "2-3", "4+"):
            s = x[x.tg == tg]
            r[f"close {tg}"] = share(s, "oq")
            r[f"next {tg}"] = share(s, "oqe")
        rows.append(r)
    by_life = pd.DataFrame(rows).set_index("lifetime")
    print("\nby market lifetime:")
    print(by_life.round(3).to_string())

    # top tags (finer than categories), at least 300 markets with big moves
    tags = pd.read_csv("local_data/market_tags.csv", dtype=str)
    tags = tags.assign(market=tags.market_id.astype(int), tag=tags.tags.str.split(";")).explode("tag")
    tags = tags[~tags.tag.isin(["all", "hide-from-new", "games"])]
    tb = big[["market", "oq", "absdp", "tg"]].merge(tags[["market", "tag"]], on="market")
    cnt = tb.groupby("tag").market.nunique()
    keep = cnt[cnt >= 300].index
    tag_tab = tb[tb.tag.isin(keep)].groupby("tag").apply(lambda x: pd.Series({
        "markets": x.market.nunique(), "overshoot": share(x, "oq"),
        "1 taker": share(x[x.tg == "1"], "oq"), "4+ takers": share(x[x.tg == "4+"], "oq")}))
    tag_tab["ordering holds"] = tag_tab["1 taker"] > tag_tab["4+ takers"]
    print(f"\ntags with 300+ markets: {len(tag_tab)}; ordering 1 > 4+ holds in {tag_tab['ordering holds'].mean():.0%}")
    print(tag_tab.sort_values("overshoot").round(3).to_string())

    by_type.to_csv("local_data/r04_by_type.csv")
    by_life.to_csv("local_data/r04_by_life.csv")
    tag_tab.to_csv("local_data/r04_by_tag.csv")
    t.to_parquet("local_data/r04_tradable.parquet", index=False)
    return by_type, by_life, tag_tab


if __name__ == "__main__":
    main()
