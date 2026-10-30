"""
Stage 8: who trades the other candidates of an event, and are they scripts?

Pass 1 (repartition): trades of markets that belong to events with 2+ markets are read from
tmp/buckets and rewritten to tmp/w8/p<j>.parquet, partitioned by event (code mod NPART), so
that every event's markets sit in one file.

Pass 2 (wallet behaviour): within each event, trades sorted by time. For each trade, the gap
since the latest trade in ANOTHER market of the same event ("cross-market reaction" if
<= FAST seconds) and whether that trade was by the same wallet (its own multi-market leg).
Per taker wallet: trades, fast trades, own legs, the same for neg-risk events only, events,
markets and dollars. Each partition's totals go to tmp/w8/wpart_*.parquet (keeps memory
under the 8 GB cap) and are summed into tmp/w8/wallets.parquet.

Pass 3 (siblings, version 2 of s5_siblings.py): for each (big move, sibling) pair in
tmp/sib_pairs.parquet, the sibling's trades in the move's 15-min bar are labelled
  mover     the taker also took liquidity in the moving market in that bar
  auto_th   the taker is a script: the share of its trades that are its OWN multi-market
            legs (it traded another market of the same event within FAST s before) is >= th
            (th = 0.05, 0.1, 0.3; neg-risk share in neg-risk events, all-events share
            otherwise; 20+ trades), and the trade came within FAST s after a trade in the
            moving market. (A first version used the plain cross-market reaction share,
            which in busy events is high by chance for ordinary users: no gap between
            groups. Own legs separate cleanly: 94% of wallets have none.)
  other     everything else (users, slow liquidity providers)
and the sibling's last price at the end of the bar is recorded on several subsets:
  p_close (all trades), p_close_noauto<th> (without auto_th trades),
  p_close_users<th> (without auto_th wallets at any latency and without mover wallets).
Also p_before and trade counts per label. -> tmp/w8/sib/s<j>.parquet
And a latency histogram of sibling trades after the nearest earlier mover trade in the bar,
by wallet type. -> tmp/w8/latency.parquet

Usage: python s8_wallets.py
Python 3.8 compatible (server).
"""
import glob
import os
import time

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

MARKETS = "data/markets_final.parquet"
SRC = "tmp/buckets"
OUT = "tmp/w8"
NPART = 16
CHUNK = 150_000                 # (move, sibling) pairs per pass-3 chunk
FAST = 2
BAR = 1800                      # the main slot length (s2_events.BAR)
MIN_N = 20
THS = (0.05, 0.1, 0.3)
LAT_BINS = [-0.5, 0.5, 1.5, 2.5, 5.5, 10.5, 30.5, 60.5, 300.5, 900.5]


def events():
    mk = pd.read_parquet(MARKETS, columns=["id", "event_id", "neg_risk"])
    mk = mk[pd.to_numeric(mk.id, errors="coerce").notna()].copy()
    mk["market"] = mk.id.astype(int)
    mk = mk.drop_duplicates("market")
    n = mk.groupby("event_id").market.transform("size")
    mk = mk[n >= 2].copy()
    mk["ev"] = pd.factorize(mk.event_id)[0].astype("int32")
    return mk.set_index("market")[["ev", "neg_risk"]]


def pass1(ev):
    os.makedirs(OUT, exist_ok=True)
    writers = {}
    t0 = time.time()
    for f in sorted(glob.glob(f"{SRC}/b*.parquet")):
        d = pd.read_parquet(f, columns=["market", "ts", "yes", "usd", "taker"])
        d = d[d.market.isin(ev.index)]
        d["ev"] = ev.ev.reindex(d.market.values).values.astype("int32")
        for j, part in d.groupby(d.ev % NPART, sort=False):
            tb = pa.Table.from_pandas(part.reset_index(drop=True), preserve_index=False)
            if j not in writers:
                writers[j] = pq.ParquetWriter(f"{OUT}/p{j:02d}.parquet", tb.schema, compression="zstd")
            writers[j].write_table(tb)
    for w in writers.values():
        w.close()
    print(f"pass 1 done in {time.time() - t0:.0f}s", flush=True)


def reaction(d):
    """d sorted by (ev, ts, market). Gap since the latest trade in another market of the
    same event, and whether that trade had the same taker."""
    ev, mk, ts, tk = d.ev.values, d.market.values, d.ts.values, d.taker.values
    new_run = np.r_[True, (ev[1:] != ev[:-1]) | (mk[1:] != mk[:-1])]
    run = np.cumsum(new_run) - 1
    last_idx = np.flatnonzero(np.r_[new_run[1:], True])            # last row of each run
    prev_run = run - 1
    ok = (prev_run >= 0)
    pi = np.where(ok, last_idx[np.maximum(prev_run, 0)], 0)
    ok &= ev[pi] == ev
    gap = np.where(ok, ts - ts[pi], np.inf)
    same = ok & (tk[pi] == tk)
    return gap, same


def pass2(ev):
    nr = ev.neg_risk
    rows = []
    t0 = time.time()
    for f in sorted(glob.glob(f"{OUT}/p*.parquet")):
        d = pd.read_parquet(f)
        d = d.sort_values(["ev", "ts", "market"], kind="mergesort").reset_index(drop=True)
        gap, same = reaction(d)
        d["fast"] = gap <= FAST
        d["own"] = d.fast & same
        d["nr"] = nr.reindex(d.market.values).values == 1
        d["fast_nr"] = d.fast & d.nr
        d["own_nr"] = d.own & d.nr
        g = d.groupby("taker")
        a = pd.DataFrame({"n": g.size().astype("float32"), "fast": g.fast.sum().astype("float32"),
                          "own": g.own.sum().astype("float32"), "events": g.ev.nunique().astype("float32"),
                          "markets": g.market.nunique().astype("float32"), "usd": g.usd.sum().astype("float32"),
                          "n_nr": g.nr.sum().astype("float32"), "fast_nr": g.fast_nr.sum().astype("float32"),
                          "own_nr": g.own_nr.sum().astype("float32")})
        a.reset_index().to_parquet(f"{OUT}/wpart_{os.path.basename(f)}", index=False)
        print(f"pass 2 {os.path.basename(f)}: {len(d):,} trades, {len(a):,} wallets, {time.time() - t0:.0f}s", flush=True)
        del d, g, a
    w = pd.concat([pd.read_parquet(f) for f in sorted(glob.glob(f"{OUT}/wpart_*.parquet"))], ignore_index=True)
    w = w.groupby("taker").sum()                      # a wallet appears in several partitions
    w.index.name = "taker"
    w = w.reset_index()
    for c in w.columns:
        if c != "taker":
            w[c] = w[c].astype("float32")
    w.to_parquet(f"{OUT}/wallets.parquet", index=False)
    print(f"wallets: {len(w):,}", flush=True)
    return w


def last_price(sel, rows_pair, rows_ts, rows_yes, n_pairs):
    """Last price per pair among selected rows (rows sorted by pair, ts)."""
    out = np.full(n_pairs, np.nan, dtype="float32")
    if sel.any():
        p, y = rows_pair[sel], rows_yes[sel]
        last = np.r_[p[1:] != p[:-1], True]
        out[p[last]] = y[last]
    return out


def sib_chunk(pk, d, key, share_nr, share_all, tk_index):
    """Sibling prices by trader kind for one chunk of (move, sibling) pairs."""
    hist = []
    t = pk.t_close.values.astype("int64")

    def rng(mkt):
        base = mkt.astype("int64") * 10**10
        lo = np.searchsorted(key, base + t - BAR, side="right")
        hi = np.searchsorted(key, base + t, side="right")
        return lo, hi

    def expand(lo, hi):
        n = hi - lo
        pid = np.repeat(np.arange(len(pk)), n)
        idx = np.repeat(lo, n) + (np.arange(n.sum()) - np.repeat(np.cumsum(n) - n, n))
        return pid, idx

    # p_before: last sibling trade at or before the start of the bar
    base = pk.sib.values.astype("int64") * 10**10
    ib = np.searchsorted(key, base + t - BAR, side="right") - 1
    okb = (ib >= 0) & (d.market.values[np.maximum(ib, 0)] == pk.sib.values)
    out = pk[["mv_market", "t_close", "sib"]].copy()
    out["p_before"] = np.where(okb, d.yes.values[np.maximum(ib, 0)], np.nan).astype("float32")

    # mover trades in the bar (unique per move, but pairs repeat the move: fine)
    mlo, mhi = rng(pk.mv_market.values)
    mpid, midx = expand(mlo, mhi)
    mov = pd.DataFrame({"pid": mpid, "ts": d.ts.values[midx], "taker": d.taker.values[midx]})
    # sibling trades in the bar
    slo, shi = rng(pk.sib.values)
    spid, sidx = expand(slo, shi)
    sib = pd.DataFrame({"pid": spid, "ts": d.ts.values[sidx], "taker": d.taker.values[sidx],
                        "yes": d.yes.values[sidx], "row": np.arange(len(spid))})
    mv = mov[["pid", "taker"]].drop_duplicates().assign(mover=True)
    sib = sib.merge(mv, on=["pid", "taker"], how="left")
    sib["mover"] = sib.mover.fillna(False).astype(bool)
    sib = sib.sort_values("row").reset_index(drop=True)
    # latency since the latest earlier mover trade in the same bar
    m2 = mov[["pid", "ts"]].drop_duplicates().sort_values("ts")
    s2_ = sib[["row", "pid", "ts"]].sort_values("ts")
    lat = pd.merge_asof(s2_, m2.rename(columns={"ts": "mts"}), left_on="ts", right_on="mts", by="pid",
                        direction="backward")
    sib["lat"] = pd.Series(lat.ts.values - lat.mts.values, index=lat.row.values).reindex(sib.row.values).values
    wi = tk_index.get_indexer(sib.taker.values)
    nrp = pk.nr.values[sib.pid.values]
    sh = np.where(wi >= 0, np.where(nrp, share_nr[np.maximum(wi, 0)], share_all[np.maximum(wi, 0)]), np.nan)
    sib["share"] = sh
    sib = sib.sort_values(["pid", "ts"], kind="mergesort")
    P, T, Y = sib.pid.values, sib.ts.values, sib.yes.values
    fast_after = sib.lat.values <= FAST
    out["n_bar"] = np.bincount(P, minlength=len(pk)).astype("int32")
    out["n_mover"] = np.bincount(P, weights=sib.mover.values, minlength=len(pk)).astype("int32")
    out["p_close"] = last_price(np.ones(len(sib), bool), P, T, Y, len(pk))
    for th in THS:
        auto = np.nan_to_num(sib.share.values, nan=0) >= th
        tag = f"{int(round(th * 100)):02d}"
        out["n_auto" + tag] = np.bincount(P, weights=auto & fast_after, minlength=len(pk)).astype("int32")
        out["p_close_noauto" + tag] = last_price(~(auto & fast_after), P, T, Y, len(pk))
        out["p_close_users" + tag] = last_price(~auto & ~sib.mover.values, P, T, Y, len(pk))
    auto10 = np.nan_to_num(sib.share.values, nan=0) >= 0.1
    kind = np.where(sib.mover.values, "mover wallet", np.where(auto10, "script", "other"))
    hb = pd.cut(sib.lat, LAT_BINS)
    hist.append(pd.DataFrame({"kind": kind, "bin": hb.astype(str).values, "nr": pk.nr.values[P]})
                .groupby(["nr", "kind", "bin"]).size().rename("n").reset_index())
    hist.append(pd.DataFrame({"nr": pk.nr.values[P[np.isnan(sib.lat.values)]], "kind": kind[np.isnan(sib.lat.values)],
                              "bin": "before any mover trade"}).groupby(["nr", "kind", "bin"]).size().rename("n").reset_index())
    return out, hist, len(sib)


def pass3(ev, w):
    os.makedirs(f"{OUT}/sib", exist_ok=True)
    pairs = pd.read_parquet("tmp/sib_pairs.parquet")
    pairs = pairs[pairs.mv_market.isin(ev.index)].copy()
    pairs["ev"] = ev.ev.reindex(pairs.mv_market.values).values
    pairs["nr"] = ev.neg_risk.reindex(pairs.mv_market.values).values == 1
    share_nr = (w.own_nr / w.n_nr.where(w.n_nr >= MIN_N)).values
    share_all = (w.own / w.n.where(w.n >= MIN_N)).values
    tk_index = pd.Index(w.taker.values)
    hist = []
    t0 = time.time()
    for f in sorted(glob.glob(f"{OUT}/p*.parquet")):
        j = int(os.path.basename(f)[1:3])
        pj = pairs[pairs.ev % NPART == j].reset_index(drop=True)
        if pj.empty:
            continue
        d = pd.read_parquet(f, columns=["market", "ts", "yes", "taker"])
        d = d.sort_values(["market", "ts"], kind="mergesort").reset_index(drop=True)
        key = d.market.values.astype("int64") * 10**10 + d.ts.values
        for c, s0 in enumerate(range(0, len(pj), CHUNK)):
            pk = pj.iloc[s0:s0 + CHUNK].reset_index(drop=True)
            out, h, nsib = sib_chunk(pk, d, key, share_nr, share_all, tk_index)
            out.to_parquet(f"{OUT}/sib/s{j:02d}_{c:03d}.parquet", index=False)
            hist += h
            print(f"pass 3 part {j} chunk {c}: {len(pk):,} pairs, {nsib:,} sibling trades in bars, "
                  f"{time.time() - t0:.0f}s", flush=True)
    pd.concat(hist).groupby(["nr", "kind", "bin"]).n.sum().reset_index().to_parquet(f"{OUT}/latency.parquet", index=False)


def main():
    ev = events()
    print(f"markets in multi-market events: {len(ev):,}; events {ev.ev.nunique():,}", flush=True)
    if not glob.glob(f"{OUT}/p*.parquet"):
        pass1(ev)
    w = pass2(ev) if not os.path.exists(f"{OUT}/wallets.parquet") else pd.read_parquet(f"{OUT}/wallets.parquet")
    pass3(ev, w)


if __name__ == "__main__":
    main()
