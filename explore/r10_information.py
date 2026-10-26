"""
Round 10: does a price jump carry information (news) or is it one trader's noise?

Input: the main jumps (local_data/r03_big_moves_900.parquet, r03_tradable_900.parquet from
explore/r03_robustness.py) and the market list (event_id, neg_risk).

Signs of information that are known at the time of the jump (or within minutes):
  crowd      4+ different traders took liquidity in the jump's 15 minutes
  money      $1,000 or more traded in those 15 minutes
  co-jump    another market of the same event also jumped in the same 15 minutes
  follow-up  someone traded again within 5 minutes after the slot
Score = how many of the four a jump has (0-4). Per score: share of jumps, overshoot at the
close and at the next trades (category baseline, ratio of sums, market bootstrap), and the
share of the jump still in the price 1 h later (median).

After the fact: "news-like" = 4+ traders and the next trades keep at
least half the jump; "noise-like" = one trader and the next trades give back at least half.
More generally, by what the next trades did (reversed it fully / gave back more than half /
kept more than half / went further) and by trader group. Only the overshoot at the close is
read from this split: the next-trade price is the one the split was made on, so its own
overshoot is biased by the selection (price noise).

Also by time: weekday vs weekend, and the hour of the day (UTC).
Outputs local_data/r10_score.csv, r10_classes.csv, r10_reaction.csv, r10_time.csv, r10_signals.csv.
Usage: python explore/r10_information.py
"""
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "explore")
from r05_siblings import boot_share, share  # noqa: E402

SIGNALS = ("crowd", "money", "co-jump", "follow-up")
REACTIONS = ["reversed it fully", "gave back over half", "kept over half", "went further"]


def load():
    e = pd.read_parquet("local_data/r03_big_moves_900.parquet")
    t = pd.read_parquet("local_data/r03_tradable_900.parquet", columns=["market", "t_close", "oe"])
    e = e.merge(t, on=["market", "t_close"], how="left")
    info = pd.read_parquet("local_data/markets_final.parquet", columns=["id", "event_id", "neg_risk"])
    info = info[pd.to_numeric(info.id, errors="coerce").notna()]
    info = info.assign(id=info.id.astype(int)).drop_duplicates("id").set_index("id")
    e["event"] = e.market.map(info.event_id)
    e["neg_risk"] = e.market.map(info.neg_risk).fillna(0).astype(bool)
    same = e.dropna(subset=["event"]).groupby(["event", "t_close"]).market.transform("size")
    e["co_jump"] = (same.reindex(e.index).fillna(1) > 1)
    e["crowd"] = e.takers >= 4
    e["money"] = e.usd >= 1000
    e["follow-up"] = e.entry_delay <= 300
    e["co-jump"] = e.co_jump
    e["score"] = e[list(SIGNALS)].sum(axis=1)
    e["kept_next"] = (e.entry_vwap - e.y_pre) / (e.p_close - e.y_pre)
    e["tg"] = e.tg.astype(str)
    return e


def row(x):
    lo, hi = boot_share(x, "oc")
    t = x[x.oe.notna()]
    return {"jumps": len(x), "share": np.nan, "markets": x.market.nunique(), "close": share(x, "oc"),
            "close_lo": lo, "close_hi": hi, "next_trades": share(t, "oe") if len(t) else np.nan,
            "kept_1h_median": x.ret_1h.median(), "median_usd": x.usd.median()}


def table(e, by):
    out = pd.DataFrame({k: row(x) for k, x in e.groupby(by, observed=True)}).T
    out["share"] = out.jumps / len(e)
    return out


def main():
    e = load()
    print(f"{len(e):,} jumps; signals: " + ", ".join(f"{s} {e[s].mean():.0%}" for s in SIGNALS))
    pd.set_option("display.width", 220)

    sig = pd.DataFrame({s: {**row(e[e[s]]), "without": share(e[~e[s]], "oc")} for s in SIGNALS}).T
    print("\n[each sign: jumps with it vs without]\n" + sig.round(3).to_string())
    sig.to_csv("local_data/r10_signals.csv")

    sc = table(e, "score")
    print("\n[number of signs]\n" + sc.round(3).to_string())
    sc.to_csv("local_data/r10_score.csv")
    print("\n[number of signs, by trader group]")
    print(pd.DataFrame({g: table(e[e.tg == g], "score").close for g in ("1", "2-3", "4+")}).round(3).to_string())
    print("\n[co-jump, neg-risk vs not]")
    print(table(e, ["neg_risk", "co_jump"]).round(3).to_string())

    t = e[e.kept_next.notna()]
    cls = np.select([(t.takers >= 4) & (t.kept_next >= .5), (t.takers == 1) & (t.kept_next < .5)],
                    ["news-like", "noise-like"], "other")
    c = table(t.assign(cls=cls), "cls")
    print(f"\n[after the fact, {len(t):,} jumps with next trades]\n" + c.round(3).to_string())
    c.to_csv("local_data/r10_classes.csv")
    t = t.assign(reaction=pd.cut(t.kept_next, [-np.inf, 0, .5, 1, np.inf], labels=REACTIONS))
    r = table(t, ["reaction", "tg"])
    print("\n[by what the next trades did]\n" + r.round(3).to_string())
    print("share of each reaction:", t.reaction.value_counts(normalize=True).round(3).to_dict())
    print("share with next trades within 1 h, by group:",
          e.groupby("tg").kept_next.apply(lambda v: v.notna().mean()).round(2).to_dict())
    r.to_csv("local_data/r10_reaction.csv")

    when = pd.to_datetime(e.t_close - 1, unit="s")
    e["weekend"] = when.dt.dayofweek >= 5
    e["hours"] = pd.cut(when.dt.hour, [0, 6, 12, 18, 24], right=False, labels=["00-06", "06-12", "12-18", "18-24"])
    tm = pd.concat({"weekend": table(e, ["weekend", "tg"]), "hours": table(e, ["hours", "tg"])})
    print("\n[time (UTC)]\n" + tm.round(3).to_string())
    tm.to_csv("local_data/r10_time.csv")


if __name__ == "__main__":
    main()
