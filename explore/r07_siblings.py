"""
Round 7, part 3: is F4 (moves the other candidates offset stick) a neg-risk mechanic?

Background. In a neg-risk event (markets_final.neg_risk = 1; every trade of such a market
goes through the NEGRISK exchange contract, checked 100% on 2023-26 data) the candidates are
linked: a NO share in one candidate converts into YES shares of all the others. This gives
liquidity to low-probability candidates. No transaction in the data spans two markets, so
conversions are not trades; but scripts can watch one candidate and trade the others within
seconds, which would make an "offset" mechanical instead of confirmation by other traders.
User trades in other candidates (even right after a big move) are information and stay.

Inputs (remote/s8_wallets.py, copied to local_data/r11/w8/):
  wallets.parquet  per taker wallet: trades, trades within 2 s of a trade in another market of
                   the same event ("fast"), own multi-market legs; also for neg-risk only.
  sib/s*.parquet   per (big move, sibling): p_before, p_close (all trades), and p_close
                   without script trades (noauto<th>) or with users only (users<th>), th =
                   0.05 / 0.1 / 0.3 = the share of a wallet's trades that are its own
                   multi-candidate legs (it traded another candidate within 2 s before),
                   which labels it a script. The plain reaction share (anyone's trade within
                   2 s) has no gap between groups in busy events and was dropped.
  latency.parquet  sibling trades in the move bar by seconds after the latest mover trade.
Moves and their overshoot (oq at the close, oqe at the next trades, question-type
baseline) come from local_data/r04_tradable.parquet, as in round 5.

Versions of the offset: all trades (round 5), without scripts' fast reactions, users only.
Events: neg-risk (as in round 5) and, as a control, non-neg-risk events whose YES prices
also sum to 0.8-1.2 (mostly older multi-candidate events with no conversion mechanism).
Outputs local_data/r07/sib_*.csv.
Usage: python explore/r07_siblings.py
"""
import glob
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "explore")
from r05_siblings import GROUPS, boot_share, share  # noqa: E402
from r02_persistence import OFFSET_HI, OFFSET_LO, TG_EDGES, TG_LABELS  # noqa: E402

SRC = "local_data/r13/w8/"
OUT = "local_data/r07/"
VERSIONS = {"all trades": "p_close", "without scripts' fast trades": "p_close_noauto10",
            "users only": "p_close_users10", "without scripts (cut 0.05)": "p_close_noauto05",
            "without scripts (cut 0.3)": "p_close_noauto30"}


def wallets():
    w = pd.read_parquet(SRC + "wallets.parquet")
    nr = w[w.n_nr >= 20].copy()
    nr["fast_share"] = nr.fast_nr / nr.n_nr
    nr["share"] = nr.own_nr / nr.n_nr        # own multi-candidate legs: the script label
    bins = [0, 1e-9, .01, .05, .1, .2, .3, .5, .7, 1.0001]
    h = pd.cut(nr.share, bins, right=False).value_counts().sort_index()
    hf = pd.cut(nr.fast_share, [0, .1, .2, .3, .4, .5, .6, .7, .8, .9, 1.0001], right=False).value_counts().sort_index()
    print(f"wallets with 20+ neg-risk trades: {len(nr):,}")
    print("cross-market reaction share (any wallet's trade in another candidate within 2 s): no gap")
    print(hf.to_string())
    print("own multi-candidate legs (the wallet itself traded another candidate within 2 s):")
    print(h.to_string())
    hf.rename("wallets").to_csv(OUT + "sib_wallet_hist_fast.csv")
    tot_n = w.n_nr.sum()
    rows = []
    for th in (0.05, 0.1, 0.3):
        a = nr[nr.share >= th]
        rows.append({"cut": th, "script wallets": len(a), "share of wallets": len(a) / len(nr),
                     "share of neg-risk trades": a.n_nr.sum() / tot_n, "share of $ (all events)": a.usd.sum() / w.usd.sum(),
                     "median markets": a.markets.median(), "median trades": a.n_nr.median(),
                     "their trades that are own multi-market legs": a.own_nr.sum() / max(a.fast_nr.sum(), 1)})
        print(f"cut {th}: {len(a):,} script wallets ({len(a) / len(nr):.2%}) making {a.n_nr.sum() / tot_n:.1%} of neg-risk trades")
    pd.DataFrame(rows).to_csv(OUT + "sib_wallet_cuts.csv", index=False)
    h.rename("wallets").to_csv(OUT + "sib_wallet_hist.csv")
    return nr


def moves():
    """Offset group of every big move with siblings, once per sibling-price version. One pass:
    per (move, version) the sum of the siblings' price changes in the bar and whether any traded."""
    s = pd.concat([pd.read_parquet(f, columns=["mv_market", "t_close", "p_before", *VERSIONS.values()])
                   for f in glob.glob(SRC + "sib/s*.parquet")], ignore_index=True)
    for k, col in enumerate(VERSIONS.values()):
        s[f"d{k}"] = (s[col] - s.p_before).where(s[col].notna(), 0.0)
        s[f"n{k}"] = s[col].notna()
    g = s.groupby(["mv_market", "t_close"])[[f"{c}{k}" for k in range(len(VERSIONS)) for c in "dn"]].sum()
    g = g.reset_index().rename(columns={"mv_market": "market"})
    t = pd.read_parquet("local_data/r04_tradable.parquet",
                        columns=["market", "t_close", "y_pre", "p_close", "absdp", "tg", "oq", "oqe"])
    mk = pd.read_parquet("local_data/markets_final.parquet", columns=["id", "neg_risk"])
    mk = mk[pd.to_numeric(mk.id, errors="coerce").notna()].assign(market=lambda x: x.id.astype(int)).drop_duplicates("market")
    t = t.merge(mk[["market", "neg_risk"]], on="market", how="left")
    x = t[t.oq.notna() & t.oqe.notna()].merge(g, on=["market", "t_close"], how="inner")
    dp = x.p_close - x.y_pre
    base = x[["market", "t_close", "neg_risk", "tg", "absdp", "oq", "oqe"]]
    out = {}
    for k, name in enumerate(VERSIONS):
        offset = -x[f"d{k}"] / dp
        out[name] = base.assign(group=np.select([x[f"n{k}"] == 0, offset < OFFSET_LO, offset < OFFSET_HI], GROUPS[:3], GROUPS[3]))
    return out


def main():
    wallets()
    lat = pd.read_parquet(SRC + "latency.parquet")
    lat_nr = lat[lat.nr].pivot_table(index="bin", columns="kind", values="n", aggfunc="sum").fillna(0)
    print("\nneg-risk sibling trades in the move bar, by seconds after the latest mover trade:")
    print(lat_nr.to_string())
    lat.to_csv(OUT + "sib_latency.csv", index=False)

    vs = moves()
    rows = []
    for name, x in vs.items():
        for nr, xs in x.groupby("neg_risk"):
            for (grp, tg), y in list(xs.groupby(["group", "tg"], observed=True)) + \
                    [((grp, "all"), y) for grp, y in xs.groupby("group")]:
                if len(y) < 30:
                    continue
                lo, hi = boot_share(y, "oq")
                rows.append({"version": name, "neg_risk": int(nr), "group": grp, "takers": tg, "moves": len(y),
                             "markets": y.market.nunique(), "close": share(y, "oq"), "lo": lo, "hi": hi,
                             "next trades": share(y, "oqe")})
    res = pd.DataFrame(rows)
    res.to_csv(OUT + "sib_versions.csv", index=False)
    for name in VERSIONS:
        for nr in (1, 0):
            r = res[(res.version == name) & (res.neg_risk == nr)]
            if r.empty:
                continue
            print(f"\n[{name}, neg_risk={nr}]  moves {vs[name][vs[name].neg_risk == nr].shape[0]:,}")
            print(r.pivot_table(index="group", columns="takers", values="close").reindex(GROUPS).round(3).to_string())
    # group sizes moving between versions
    a, b = vs["all trades"], vs["without scripts' fast trades"]
    m = a[a.neg_risk == 1][["market", "t_close", "group"]].merge(
        b[b.neg_risk == 1][["market", "t_close", "group"]], on=["market", "t_close"], suffixes=("_all", "_noscript"))
    ct = pd.crosstab(m.group_all, m.group_noscript)
    print("\nneg-risk moves: group with all trades (rows) vs without scripts' fast trades (columns):")
    print(ct.to_string())
    ct.to_csv(OUT + "sib_group_switch.csv")

    # F2 (number of traders) in neg-risk vs other markets
    bm = pd.read_parquet("local_data/r02_big_moves.parquet")
    mk = pd.read_parquet("local_data/markets_final.parquet", columns=["id", "neg_risk"])
    nrm = pd.Series(mk.neg_risk.values, index=pd.to_numeric(mk.id, errors="coerce"))
    bm["neg_risk"] = bm.market.map(nrm[~nrm.index.duplicated()])
    bm["tg"] = pd.cut(bm.takers, TG_EDGES, labels=TG_LABELS).astype(str)
    f2 = bm.groupby(["neg_risk", "tg"]).apply(lambda x: pd.Series({
        "moves": len(x), "overshoot": x.overshoot.sum() / x.absdp.sum()})).reset_index()
    print("\nF2 by neg-risk:")
    print(f2.round(3).to_string(index=False))
    f2.to_csv(OUT + "sib_f2_by_negrisk.csv", index=False)


if __name__ == "__main__":
    main()
