"""
Crypto up/down markets (section 5 of the report): the same overshoot, with their own parameters.

Input (remote/s1x_bucket.py -> s4_paths.py cxmoves):
  local_data/r05/events_cx/<CX_SLOT>/e*.parquet  crypto price jumps (CX_SLOT-second slots, VWAP,
                                                  with the next-trades price) in every bitcoin /
                                                  ether / solana / xrp up/down market
  local_data/r05/events_cx/<CX_SLOT>/r*.parquet  every crypto slot with trades inside the windows
The calibration error b(p) is measured as for the event markets, on every slot with trades, per
(coin, market length) and price bin (the same N_BINS equal bins). The overshoot at the slot's
close and at the next trades, by market length and trader group (CX_TG_LABELS), with 95% ranges
from N_RESAMPLES resamples of whole markets.

Outputs local_data/r05/r05_ud_len.csv and r05_ud_moves.parquet.
Usage: python explore/r05_updown.py
"""
import glob
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "explore")
from r02_persistence import (BINS, CX_CLIP, CX_MIN_PTS, CX_OUTCOME_Q, CX_SLOT, CX_TG_EDGES, CX_TG_LABELS,  # noqa: E402
                             boot_share, outcomes, sigmoid)

OUT = "local_data/r05/"
DUR = {"5M": 5, "15M": 15, "1H": 60}
EVENTS = OUT + f"events_cx/{CX_SLOT}/e*.parquet"
SLOTS = OUT + f"events_cx/{CX_SLOT}/r*.parquet"


def market_info():
    t = pd.read_csv("local_data/market_tags.csv", dtype=str)
    t = t[t.tags.str.contains("up-or-down", na=False)]
    info = pd.DataFrame({"market": t.market_id.astype(int).values,
                         "dur": t.tags.str.extract(r"(?:^|;)(5M|15M|1H)(?:;|$)", expand=False).values,
                         "asset": t.tags.str.extract(r"(?:^|;)(bitcoin|ethereum|solana|xrp)(?:;|$)", expand=False).values})
    return info.dropna().drop_duplicates("market")


def logit(p):
    p = np.clip(p, CX_CLIP, 1 - CX_CLIP)
    return np.log(p / (1 - p))


def calibration(info):
    """b(p) of the crypto markets: mean (outcome - price) over every slot, per (coin, length, bin)."""
    r = pd.concat([pd.read_parquet(f) for f in glob.glob(SLOTS)], ignore_index=True).merge(info, on="market")
    r["outcome"] = r.market.map(outcomes(CX_OUTCOME_Q))
    r = r[r.outcome.notna()]
    print(f"crypto slots with an outcome: {len(r):,} in {r.market.nunique():,} markets")
    return r.assign(bin=pd.cut(r.vwap, BINS)).groupby(["asset", "dur", "bin"], observed=True).apply(
        lambda x: (x.outcome - x.vwap).mean())


def load_moves(info):
    e = pd.concat([pd.read_parquet(f) for f in glob.glob(EVENTS)], ignore_index=True).merge(info, on="market")
    e["outcome"] = e.market.map(outcomes(CX_OUTCOME_Q))
    e = e[e.outcome.notna()].copy()
    e["L_pre"] = logit(e.y_pre)
    e["p_close"] = sigmoid(e.L_pre + e.move)
    e["sgn"] = np.sign(e.move)
    e["absdp"] = (e.p_close - e.y_pre).abs()
    e["tg"] = pd.cut(e.takers, CX_TG_EDGES, labels=CX_TG_LABELS)
    return e[e.absdp >= CX_MIN_PTS].copy()


def main():
    info = market_info()
    cb = calibration(info)
    big = load_moves(info)

    def osh(p):
        b = cb.reindex(pd.MultiIndex.from_arrays([big.asset.values, big.dur.values, pd.cut(p, BINS)])).astype(float).values
        return -((big.outcome - p) - b) * big.sgn

    big["oc"], big["oe"] = osh(big.p_close), osh(big.entry_vwap)
    big = big[big.oc.notna()]
    print(f"crypto jumps: {len(big):,} in {big.market.nunique():,} markets "
          f"({pd.to_datetime(big.t_close.min(), unit='s'):%Y-%m-%d} to {pd.to_datetime(big.t_close.max(), unit='s'):%Y-%m-%d})")
    rows = []
    for (d, tg), x in big.groupby(["dur", "tg"], observed=True):
        n = x[x.oe.notna()]
        c, e = boot_share(x, "oc"), boot_share(n, "oe")
        rows.append({"dur": d, "takers": tg, "jumps": len(x), "markets": x.market.nunique(),
                     "close": x.oc.sum() / x.absdp.sum(), "close lo": c[0], "close hi": c[1],
                     "with next": len(n), "next": n.oe.sum() / n.absdp.sum(), "next lo": e[0], "next hi": e[1],
                     "median delay s": n.entry_delay.median()})
    r = pd.DataFrame(rows)
    pd.set_option("display.width", 200)
    print(r.round(4).to_string(index=False))
    r.to_csv(OUT + "r05_ud_len.csv", index=False)
    big.to_parquet(OUT + "r05_ud_moves.parquet", index=False)


if __name__ == "__main__":
    main()
