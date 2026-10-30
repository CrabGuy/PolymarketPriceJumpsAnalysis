"""
Round 5, part 5: matrix profiles across the crypto up/down markets.

Input: local_data/r05/cx_paths/cx_*.parquet (each market's YES price at 30 evenly spaced
times over its window) and local_data/r05/r05_ud_moves.parquet (from r05_updown.py).

  A  Chains: for each coin, its 15-minute markets back to back on one 15-minute grid
     (30 points per market, log-odds; markets with fewer than MIN_TRADES trades -> NaN),
     as in round 4 for bitcoin.
  B  AB-join with stumpy.stump(T_A, m=30, T_B, ignore_trivial=False): for every 15-min
     window of coin A, the most similar window anywhere in coin B's history. "Synchrony" =
     share of A's market windows whose nearest B window is the same 15 minutes (+-1 point).
     Null: B's markets shuffled in time (block shuffle), same computation.
     Also each market's same-time distance (A's path vs B's path in the same 15 minutes):
     small = the two coins' markets moved together, large = they decoupled.
  C  Lead-lag: correlation between 30-s log-odds changes of coin A and coin B in the same
     window, at lags of -3..+3 steps (positive lag = A moves first). Also the bitcoin 5-min
     market against the bitcoin 15-min market over the same 30-s steps.
  D  Link to the momentum result: bitcoin 15-min crowd moves (4+ takers), split by how
     coupled bitcoin and ether were in that 15-min window.

Usage: python explore/r05_crypto_mp.py
"""
import glob
import sys
import time

import numpy as np
import pandas as pd
import stumpy

sys.path.insert(0, "explore")
from r05_updown import market_info, logit  # noqa: E402
from r02_persistence import CX_MIN_TRADES, CX_POINTS  # noqa: E402

OUT = "local_data/r05/"
M = CX_POINTS
MIN_TRADES = CX_MIN_TRADES
COINS = ["bitcoin", "ethereum", "solana", "xrp"]


def chains():
    info = market_info()
    p = pd.concat([pd.read_parquet(f) for f in glob.glob(OUT + "cx_paths/cx_*.parquet")], ignore_index=True)
    p = p.merge(info, on="market")
    p = p[p.dur_min == p.dur_s // 60]
    q = p[p.dur == "15M"]
    grid = np.arange(q.end.min(), q.end.max() + 1, 900)
    C, N = {}, {}
    for c in COINS:
        s = q[q.asset == c].drop_duplicates("end").set_index("end").reindex(grid)
        P = s.filter(regex=r"^p\d+$").values.astype("float64")
        P[(s.n_window.fillna(0) < MIN_TRADES).values] = np.nan
        C[c] = logit(P)
        N[c] = s.n_window.values
    b5 = p[(p.dur == "5M") & (p.asset == "bitcoin")].drop_duplicates("end").set_index("end")
    return grid, C, N, b5


def synchrony(TA, TB, n_markets):
    mp = stumpy.stump(TA.ravel(), M, TB.ravel(), ignore_trivial=False)
    P = mp[:, 0].astype(float)
    I = mp[:, 1].astype(int)
    al = np.arange(0, n_markets * M, M)
    al = al[al < len(P)]
    ok = np.isfinite(P[al])
    same = np.abs(I[al] - al) <= 1
    return same[ok].mean(), ok.sum(), P, I


def same_time_distance(A, B):
    """z-normalised distance between A's and B's path in the same 15 minutes, per market."""
    def z(X):
        sd = X.std(1, keepdims=True)
        return (X - X.mean(1, keepdims=True)) / np.where(sd > 1e-6, sd, np.nan)
    za, zb = z(A), z(B)
    return np.sqrt(((za - zb) ** 2).sum(1))


def lead_lag(A, B, lags=range(-3, 4)):
    dA, dB = np.diff(A, axis=1), np.diff(B, axis=1)
    out = {}
    for k in lags:
        if k >= 0:
            x, y = dA[:, :dA.shape[1] - k], dB[:, k:]
        else:
            x, y = dA[:, -k:], dB[:, :dB.shape[1] + k]
        ok = np.isfinite(x) & np.isfinite(y)
        out[k] = np.corrcoef(x[ok], y[ok])[0, 1]
    return pd.Series(out)


def main():
    grid, C, N, b5 = chains()
    n = len(grid)
    print(f"15-min grid: {n:,} slots ({pd.to_datetime(grid[0], unit='s'):%Y-%m-%d} to {pd.to_datetime(grid[-1], unit='s'):%Y-%m-%d})")
    for c in COINS:
        print(f"  {c}: {np.isfinite(C[c][:, 0]).sum():,} usable markets, median trades per market {np.nanmedian(N[c]):.0f}")
    # B. AB-joins (bitcoin against each other coin) + block-shuffled null
    rng = np.random.default_rng(5)
    rows = []
    for c in COINS[1:]:
        t0 = time.time()
        s, k, P, I = synchrony(C["bitcoin"], C[c], n)
        perm = rng.permutation(n)
        s0, _, _, _ = synchrony(C["bitcoin"], C[c][perm], n)
        rows.append({"pair": f"bitcoin vs {c}", "markets": k, "synchrony": s, "shuffled": s0,
                     "seconds": time.time() - t0})
        print(rows[-1])
    syn = pd.DataFrame(rows)
    # same-time distances and lead-lag for every coin pair
    pairs = [("bitcoin", "ethereum"), ("bitcoin", "solana"), ("bitcoin", "xrp"), ("ethereum", "solana"),
             ("ethereum", "xrp"), ("solana", "xrp")]
    d_same = pd.DataFrame({f"{a}-{b}": same_time_distance(C[a], C[b]) for a, b in pairs}, index=grid)
    print("\nmedian same-time distance (lower = moved together; independent shapes would give about",
          f"{np.sqrt(2 * M):.1f}):")
    print(d_same.median().round(2).to_string())
    ll = pd.DataFrame({f"{a} leads {b}": lead_lag(C[a], C[b]) for a, b in pairs})
    # bitcoin 5-min vs 15-min on the shared 30-s steps: 5-min point 3j sits at the 15-min point j
    A15, A5 = [], []
    for i, end in enumerate(grid):
        if not np.isfinite(C["bitcoin"][i]).all():
            continue
        parts = [b5.reindex([end - 600, end - 300, end])]
        sub = parts[0]
        if sub.p0.isna().any():
            continue
        v = sub.filter(regex=r"^p\d+$").values[:, 2::3].ravel()       # 10 points per 5-min market, at 30-s steps
        A5.append(logit(v.astype(float)))
        A15.append(C["bitcoin"][i])
    if A5:
        A5, A15 = np.array(A5), np.array(A15)
        # changes inside each 5-min market only (the 5-min markets restart at 50% every 5 minutes)
        m5 = np.ones(29, bool)
        m5[[9, 19]] = False
        d5, d15 = np.diff(A5, axis=1)[:, m5], np.diff(A15, axis=1)[:, m5]
        out = {}
        for k in range(-3, 4):
            if k >= 0:
                x, y = d5[:, :d5.shape[1] - k], d15[:, k:]
            else:
                x, y = d5[:, -k:], d15[:, :d15.shape[1] + k]
            ok = np.isfinite(x) & np.isfinite(y)
            out[k] = np.corrcoef(x[ok], y[ok])[0, 1]
        ll["bitcoin 5-min leads bitcoin 15-min"] = pd.Series(out)
        print(f"\nbitcoin 5-min vs 15-min windows compared: {len(A5):,}")
    print("\nlead-lag: correlation of 30-s changes, positive lag = first coin moves first:")
    print(ll.round(3).to_string())
    syn.to_csv(OUT + "r05_cx_synchrony.csv", index=False)
    d_same.to_parquet(OUT + "r05_cx_same_time.parquet")
    ll.to_csv(OUT + "r05_cx_leadlag.csv")
    np.save(OUT + "r05_cx_T.npy", np.stack([C[c] for c in COINS]))
    np.save(OUT + "r05_cx_grid.npy", grid)
    import os
    if os.path.exists(OUT + "r05_ud_moves.parquet"):
        link_moves(d_same)


def link_moves(d_same=None):
    """D. bitcoin 15-min moves by how coupled bitcoin and ether were in that window."""
    if d_same is None:
        d_same = pd.read_parquet(OUT + "r05_cx_same_time.parquet")
    mv = pd.read_parquet(OUT + "r05_ud_moves.parquet")
    mv = mv[(mv.asset == "bitcoin") & (mv.dur == "15M")]
    mv["d_same"] = mv.end.map(d_same["bitcoin-ethereum"])
    mv["coupling"] = pd.qcut(mv.d_same, 4, labels=["moved together", "2", "3", "decoupled"])
    sh = lambda x, c: x[c].sum() / x.absdp.sum()
    link = mv.groupby(["coupling", "tg"], observed=True).apply(lambda x: pd.Series({
        "moves": len(x), "close": sh(x, "oc"), "next trades": sh(x[x.oe.notna()], "oe")})).unstack()
    print("\nbitcoin 15-min moves by bitcoin-ether coupling in that window:")
    print(link.round(3).to_string())
    link.to_csv(OUT + "r05_cx_coupling_moves.csv")
    return link


if __name__ == "__main__":
    main()
