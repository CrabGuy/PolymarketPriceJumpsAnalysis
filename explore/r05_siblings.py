"""
Round 5, part 2: do the other outcomes of the same event follow a big move?

In a multi-outcome event whose outcomes exclude each other (Polymarket "neg risk" events,
e.g. "Who will win the election?" with one market per candidate), news about one outcome
should move the others the opposite way, so the YES prices keep summing to about 1. A
move pushed by trading flow alone leaves the others where they were.

Input: local_data/r05/sib/s*.parquet (remote/s5_siblings.py: every sibling's last price
before and at the end of the move bar, its trades in the bar, and its price 1 h / 6 h /
24 h later) and local_data/r04_tradable.parquet (the moves, with overshoot net of the
question-type calibration: oq at the close, oqe at the next trades).

Per move:
  offset      -(sum of the siblings' price changes in the move bar) / (the move's price
              change): 1 = the rest of the event moved fully the other way, 0 = nothing.
  answered    at least one sibling traded in the move bar.
  groups      "isolated" (no sibling traded in the bar), "not offset" (siblings traded but
              offset < 0.25), "partly offset" (0.25-0.75), "offset" (>= 0.75).
Only events where the YES prices summed to 0.8-1.2 just before the move (so the sum
constraint really holds) and where every sibling had a price.
Then: overshoot by group and number of takers, and who closes the gap afterwards (the
moving market coming back, or the siblings catching up) at 1 h, 6 h and 24 h.

Usage: python explore/r05_siblings.py
"""
import glob

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "explore")
from r02_persistence import N_RESAMPLES  # noqa: E402

OUT = "local_data/r05/"
GROUPS = ["isolated", "not offset", "partly offset", "offset"]


def share(x, col):
    return x[col].sum() / x.absdp.sum()


def boot_share(x, col, n=N_RESAMPLES):
    g = x.groupby("market").agg(a=(col, "sum"), b=("absdp", "sum"))
    rng = np.random.default_rng(2)
    a, b = g.a.values, g.b.values
    r = []
    for _ in range(n):
        i = rng.integers(0, len(g), len(g))
        r.append(a[i].sum() / b[i].sum())
    return np.percentile(r, [2.5, 97.5])


def load():
    s = pd.concat([pd.read_parquet(f) for f in glob.glob(OUT + "sib/s*.parquet")], ignore_index=True)
    s["d_bar"] = s.p_close - s.p_before
    for h in ("1h", "6h", "24h"):
        s["d_" + h] = s["p_" + h] - s.p_close
    agg = s.groupby(["mv_market", "t_close"]).agg(
        n_sib=("sib", "size"), n_priced=("p_before", "count"), sum_before=("p_before", "sum"),
        sib_traded=("n_bar", lambda x: (x > 0).sum()), sib_d_bar=("d_bar", "sum"),
        sib_d_1h=("d_1h", "sum"), sib_d_6h=("d_6h", "sum"), sib_d_24h=("d_24h", "sum")).reset_index()
    agg = agg.rename(columns={"mv_market": "market"})
    t = pd.read_parquet("local_data/r04_tradable.parquet")
    mk = pd.read_parquet("local_data/markets_final.parquet", columns=["id", "neg_risk"])
    mk = mk[pd.to_numeric(mk.id, errors="coerce").notna()].assign(market=lambda x: x.id.astype(int)).drop_duplicates("market")
    t = t.merge(mk[["market", "neg_risk"]], on="market", how="left")
    t = t.merge(agg, on=["market", "t_close"], how="inner")
    t = t[t.oq.notna() & t.oqe.notna()].copy()
    t["dp"] = t.p_close - t.y_pre
    t["event_sum"] = t.sum_before + t.y_pre
    t["offset"] = -t.sib_d_bar / t.dp
    t["group"] = np.select([t.sib_traded == 0, t.offset < 0.25, t.offset < 0.75], GROUPS[:3], GROUPS[3])
    return t


def main():
    t = load()
    print(f"moves in multi-market events with sibling data: {len(t):,}")
    ex = t[(t.neg_risk == 1) & (t.n_priced == t.n_sib) & t.event_sum.between(0.8, 1.2)].copy()
    print(f"exclusive events (neg risk, all siblings priced, sum 0.8-1.2): {len(ex):,} moves, "
          f"{ex.market.nunique():,} markets, median {ex.n_sib.median():.0f} siblings")
    print("group sizes:", ex.group.value_counts().to_dict())
    print("by takers:", pd.crosstab(ex.tg, ex.group, normalize="index").round(3).to_string(), sep="\n")

    rows = []
    for (g, tg), x in list(ex.groupby(["group", "tg"], observed=True)) + [((g, "all"), x) for g, x in ex.groupby("group")]:
        lo, hi = boot_share(x, "oq")
        rows.append({"group": g, "takers": tg, "moves": len(x), "markets": x.market.nunique(),
                     "close": share(x, "oq"), "lo": lo, "hi": hi, "next trades": share(x, "oqe")})
    res = pd.DataFrame(rows)
    res["group"] = pd.Categorical(res.group, GROUPS)
    res = res.sort_values(["takers", "group"])
    print("\novershoot by how much of the move the rest of the event offset in the same bar:")
    print(res.round(3).to_string(index=False))

    # who closes the gap afterwards: the mover reverting, or the siblings catching up
    rows = []
    sig = np.sign(ex.dp)
    for g, x in ex.groupby("group"):
        sx = np.sign(x.dp)
        r = {"group": g, "moves": len(x), "gap at close": (x.dp + x.sib_d_bar).abs().mean()}
        for h, col in (("1h", "ret_1h"), ("6h", "ret_6h"), ("24h", "ret_24h")):
            ok = x[col].notna() & x["sib_d_" + h].notna()
            y = x[ok]
            p_h = 1 / (1 + np.exp(-(y.L_pre + y[col] * y.move)))
            mover_back = (-(p_h - y.p_close) * np.sign(y.dp)).sum() / y.absdp.sum()
            sib_follow = (-y["sib_d_" + h] * np.sign(y.dp)).sum() / y.absdp.sum()
            r[f"mover gives back {h}"] = mover_back
            r[f"siblings follow {h}"] = sib_follow
        rows.append(r)
    gap = pd.DataFrame(rows)
    gap["group"] = pd.Categorical(gap.group, GROUPS)
    gap = gap.sort_values("group")
    print("\nafter the bar, as a share of the move: how much the mover gives back vs how much the siblings follow:")
    print(gap.round(3).to_string(index=False))

    # non-exclusive events (nested deadlines, ladders): siblings that move the SAME way confirm
    ne = t[(t.neg_risk == 0) & (t.n_priced == t.n_sib)].copy()
    ne["same"] = np.sign(ne.sib_d_bar) == np.sign(ne.dp)
    ne["grp2"] = np.where(ne.sib_traded == 0, "isolated", np.where(ne.same, "siblings same way", "siblings other way"))
    r2 = ne.groupby(["grp2", "tg"], observed=True).apply(lambda x: pd.Series({"moves": len(x), "close": share(x, "oq"),
                                                                           "next trades": share(x, "oqe")})).unstack()
    print(f"\nnon-exclusive events ({len(ne):,} moves): overshoot by sibling behaviour")
    print(r2.round(3).to_string())

    res.to_csv(OUT + "r05_sib_overshoot.csv", index=False)
    gap.to_csv(OUT + "r05_sib_gap.csv", index=False)
    r2.to_csv(OUT + "r05_sib_nonexclusive.csv")
    ex.to_parquet(OUT + "r05_sib_moves.parquet", index=False)
    return ex, res, gap


if __name__ == "__main__":
    main()
