"""
Round 13: how the calibration error b(p) is measured, and how many resamples the ranges need.
Comparisons asked by the thesis supervisors (consegna.md, section 3); nothing here feeds the report's
numbers, which come from r02_persistence.calibration() (10 equal bins, every slot).

  bins       overshoot (all jumps and by trader group) with b(p) in 10, 15 and 20 equal price bins
             and without bins (isotonic regression of the outcome on the price per category, the
             CORP reliability diagram of Dimitriadis, Gneiting and Jordan 2021); the fewest slots in
             a category x bin cell
  sample     b(p) from the old 0.5% random draw of the slots vs from every slot; and from every slot
             except the slots that are price jumps (event-study estimation window without the event)
  resamples  the 95% ranges of the main numbers with 150 and with 1,000 market resamples
  crypto     the same bins and isotonic check on the crypto up/down markets, and the overshoot with
             and without b(p)
  curve      the b(p) used by the report (10 bins, every slot), all event markets together and per
             category: mean price, share of YES outcomes, b(p), 95% range from resampling markets
             (the data of the figure m_calibration)

Inputs: local_data/r03_big_moves_main.parquet (the jumps), local_data/r03_events/<BAR>/r*.parquet
(every slot), local_data/fin/r_sample5/ (the old 5% draw, from which the 0.5% was taken),
local_data/r05/r05_ud_moves.parquet and local_data/r05/events_cx/<CX_SLOT>/r*.parquet (crypto).
Outputs local_data/r13_bins.csv, r13_sample.csv, r13_resamples.csv, r13_crypto.csv, r13_curve.csv.
Usage: python explore/r13_calibration.py [bins|sample|resamples|crypto|curve ...]
"""
import glob
import sys

import numpy as np
import pandas as pd
from scipy.optimize import isotonic_regression

sys.path.insert(0, "explore")
from r02_persistence import (BAR, BINS, CX_SLOT, MIN_PTS, N_RESAMPLES, TG_LABELS, cat_baseline, outcomes,  # noqa: E402
                             overshoot_cat, random_slots, with_cat)

OUT = "local_data/"


def jumps():
    b = pd.read_parquet(OUT + "r03_big_moves_main.parquet",
                        columns=["market", "t_close", "p_close", "y_pre", "outcome", "sgn", "absdp", "cat", "tg"])
    b["tg"] = b.tg.astype(str)
    return b


def slots(r=None):
    r = random_slots() if r is None else r
    r["outcome"] = r.market.map(outcomes())
    return with_cat(r[r.outcome.notna()].copy())


def iso_baseline(r, key="cat"):
    """b(p) without bins: per group, the isotonic (PAV) fit of the outcome on the price minus the price."""
    fits = {}
    for k, x in r.groupby(key):
        g = x.groupby("vwap").outcome.agg(["sum", "size"])
        p = g.index.values.astype(float)
        fit = isotonic_regression(g["sum"].values / g["size"].values, weights=g["size"].values.astype(float)).x
        fits[k] = (p, fit)
    return fits


def overshoot_iso(e, p, fits, key="cat"):
    b = np.full(len(e), np.nan)
    p = np.asarray(p, float)
    for k, (px, fit) in fits.items():
        m = (e[key] == k).values & np.isfinite(p)
        i = np.clip(np.searchsorted(px, p[m], side="right") - 1, 0, len(px) - 1)
        b[m] = fit[i] - p[m]
    return -((e.outcome.values - p) - b) * e.sgn.values


def summary(b, col):
    row = {"all": b[col].sum() / b.absdp.sum()}
    for tg in TG_LABELS:
        x = b[b.tg == tg]
        row[tg] = x[col].sum() / x.absdp.sum()
    return row


def c_bins(b, r):
    rows = []
    for n in (10, 15, 20):
        bins = np.linspace(0, 1, n + 1)
        cb = cat_baseline(r, bins)
        b["o"] = overshoot_cat(b, b.p_close, cb, bins)
        cells = r.groupby(["cat", pd.cut(r.vwap, bins)], observed=True).size()
        rows.append({"b(p)": f"{n} fasce", **summary(b, "o"), "min slots per cell": int(cells.min()),
                     "cell": " / ".join(map(str, cells.idxmin()))})
    b["o"] = overshoot_iso(b, b.p_close, iso_baseline(r))
    rows.append({"b(p)": "isotonica (senza fasce)", **summary(b, "o"), "min slots per cell": np.nan, "cell": ""})
    out = pd.DataFrame(rows)
    print(out.round(4).to_string(index=False))
    out.to_csv(OUT + "r13_bins.csv", index=False)


def c_sample(b, r):
    old = pd.concat([pd.read_parquet(f) for f in sorted(glob.glob(OUT + "fin/r_sample5/r*.parquet"))], ignore_index=True)
    old = old[np.random.default_rng(0).random(len(old)) < 0.005 / 0.05].reset_index(drop=True)   # the old 0.5% draw
    old = slots(old)
    key = pd.MultiIndex.from_frame(r[["market", "t_close"]])
    jumpkey = pd.MultiIndex.from_frame(b[["market", "t_close"]])
    no_jumps = r[~key.isin(jumpkey)]
    rows = []
    for name, data in (("campione 0,5% (prima)", old), ("tutti gli slot", r), ("tutti tranne gli slot dei salti", no_jumps)):
        cb = cat_baseline(data)
        b["o"] = overshoot_cat(b, b.p_close, cb)
        rows.append({"slot usati per b(p)": name, "slots": len(data), **summary(b, "o")})
    out = pd.DataFrame(rows)
    print(out.round(4).to_string(index=False))
    out.to_csv(OUT + "r13_sample.csv", index=False)


def ranges(o, d, n, seed=0):
    idx = np.random.default_rng(seed).integers(0, len(o), size=(n, len(o)))
    bs = o[idx].sum(1) / d[idx].sum(1)
    return np.percentile(bs, [2.5, 97.5])


def c_resamples(b, r):
    b["o"] = overshoot_cat(b, b.p_close, cat_baseline(r))
    rows = []
    for name, x in [("tutti", b)] + [(f"{tg} trader", b[b.tg == tg]) for tg in TG_LABELS]:
        g = x.groupby("market")[["o", "absdp"]].sum()
        o, d = g.o.values, g.absdp.values
        r150, r1000 = ranges(o, d, 150), ranges(o, d, 1000)
        rows.append({"gruppo": name, "overshoot": o.sum() / d.sum(), "lo 150": r150[0], "hi 150": r150[1],
                     "lo 1000": r1000[0], "hi 1000": r1000[1],
                     "spostamento max (punti)": 100 * np.abs(r1000 - r150).max()})
    out = pd.DataFrame(rows)
    print(out.round(4).to_string(index=False))
    out.to_csv(OUT + "r13_resamples.csv", index=False)


def c_crypto():
    import r05_updown as ud
    info = ud.market_info()
    e = ud.load_moves(info)
    r = pd.concat([pd.read_parquet(f) for f in glob.glob(f"{OUT}r05/events_cx/{CX_SLOT}/r*.parquet")], ignore_index=True)
    r = r.merge(info[["market", "asset", "dur"]], on="market")
    from r02_persistence import CX_OUTCOME_Q
    r["outcome"] = r.market.map(outcomes(CX_OUTCOME_Q))
    r = r[r.outcome.notna()].copy()
    r["key"] = r.asset + " " + r.dur
    e["key"] = e.asset + " " + e.dur
    e = e.rename(columns={"tg": "tgc"})
    rows = []
    e["raw"] = -(e.outcome - e.p_close) * e.sgn
    labels = sorted(e.tgc.astype(str).unique(), key=lambda s: int(s.split("-")[0].rstrip("+")))

    def summ(col):
        out = {"all": e[col].sum() / e.absdp.sum()}
        for tg in labels:
            x = e[(e.tgc.astype(str) == tg) & (e.dur == "15M")]
            out[f"{tg} (15 min)"] = x[col].sum() / x.absdp.sum()
        return out
    rows.append({"b(p)": "nessuno (prima)", **summ("raw")})
    for n in (8, 10, 15, 20):
        bins = np.linspace(0, 1, n + 1)
        cb = r.assign(bin=pd.cut(r.vwap, bins)).groupby(["key", "bin"], observed=True).apply(
            lambda x: (x.outcome - x.vwap).mean())
        b_ = cb.reindex(pd.MultiIndex.from_arrays([e.key.values, pd.cut(e.p_close, bins)])).astype(float).values
        e["o"] = -((e.outcome - e.p_close) - b_) * e.sgn
        cells = r.groupby(["key", pd.cut(r.vwap, bins)], observed=True).size()
        rows.append({"b(p)": f"{n} fasce, tutti gli slot", **summ("o"), "min slots per cell": int(cells.min())})
    e["o"] = overshoot_iso(e, e.p_close, iso_baseline(r, "key"), "key")
    rows.append({"b(p)": "isotonica, tutti gli slot", **summ("o")})
    out = pd.DataFrame(rows)
    print(f"crypto jumps {len(e):,}, crypto slots {len(r):,}")
    print(out.round(4).to_string(index=False))
    out.to_csv(OUT + "r13_crypto.csv", index=False)


def c_curve(b, r):
    """b(p) per price bin with a 95% range (resampling whole markets), all markets and per category."""
    r = r.assign(bin=pd.cut(r.vwap, BINS, labels=False), err=r.outcome - r.vwap)
    rows = []
    rng = np.random.default_rng(0)
    for name, x in [("tutti", r)] + list(r.groupby("cat")):
        m_id, m = np.unique(x.market.values, return_inverse=True)
        nb = len(BINS) - 1
        key = m * nb + x.bin.values
        cnt = np.bincount(key, minlength=len(m_id) * nb).reshape(len(m_id), nb)
        err = np.bincount(key, weights=x.err.values, minlength=len(m_id) * nb).reshape(len(m_id), nb)
        pr = np.bincount(key, weights=x.vwap.values, minlength=len(m_id) * nb).reshape(len(m_id), nb)
        bs = []
        for _ in range(0, N_RESAMPLES, 50):
            w = np.stack([np.bincount(rng.integers(0, len(m_id), len(m_id)), minlength=len(m_id)) for _ in range(50)])
            bs.append((w @ err) / np.maximum(w @ cnt, 1))
        bs = np.concatenate(bs)
        lo, hi = np.percentile(bs, [2.5, 97.5], axis=0)
        for k in range(nb):
            rows.append({"group": name, "bin": k, "from": BINS[k], "to": BINS[k + 1], "slots": int(cnt[:, k].sum()),
                         "markets": int((cnt[:, k] > 0).sum()), "mean price": pr[:, k].sum() / cnt[:, k].sum(),
                         "yes share": (err[:, k].sum() + pr[:, k].sum()) / cnt[:, k].sum(),
                         "b": err[:, k].sum() / cnt[:, k].sum(), "lo": lo[k], "hi": hi[k]})
    out = pd.DataFrame(rows)
    print(out[out.group == "tutti"].round(4).to_string(index=False))
    out.to_csv(OUT + "r13_curve.csv", index=False)


def main(names):
    names = names or ["bins", "sample", "resamples", "crypto", "curve"]
    if set(names) - {"crypto"}:
        b, r = jumps(), slots()
        assert (b.absdp >= MIN_PTS).all()
        print(f"{len(b):,} jumps; {len(r):,} slots with an outcome (slot {BAR // 60} min)")
    for n in names:
        print(f"\n[{n}]")
        if n == "crypto":
            c_crypto()
        else:
            {"bins": c_bins, "sample": c_sample, "resamples": c_resamples, "curve": c_curve}[n](b, r)


if __name__ == "__main__":
    main(sys.argv[1:])
