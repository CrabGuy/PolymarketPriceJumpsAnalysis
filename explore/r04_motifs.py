"""
Round 4, part 2A: recurring reaction shapes (motifs) and anomalous reactions (discords)
after big moves, across all non-recurring markets.

Each price jump (15-min bars, VWAP, >= 10 points) gives a 55-point window of log-odds:
5-min steps from 35 min before the move bar closes to about 4 h after
(remote/s4_paths.py, mode "moves"). On a random sample of windows, the matrix profile of
the set is computed: each window's z-normalised Euclidean distance (the stumpy distance)
to its nearest neighbour **from a different event** (same-event matches would be trivial
or mechanically linked). The distance code is checked against stumpy.mass.

Only jumps with at least 6 h of the market's window left (round 9: the window now scales
with the market, so short markets would otherwise reach their resolution inside the path).
Trivial matches: windows that are flat apart from the jump (illiquid, no later trades)
match each other exactly, so windows need price changes in at least 8 of the 47
post-move steps.
Motifs: greedy, like stumpy.motifs. Take the window with the smallest profile value, call
every window within radius R of it a member, remove them, repeat.
Null: each window keeps its pre-move part and its move step, but the post-move steps are
shuffled. Motif sizes at the same radius are compared with the real ones.
Discords: the windows with the largest profile values.

Usage: python explore/r04_motifs.py [n_sample]
"""
import glob
import sys

import numpy as np
import pandas as pd
import stumpy

M = 55
MOVE_AT = 7           # first post-move point (index of offset 0 is 7: the move bar's last step)
N_SAMPLE = 20000
N_MOTIFS = 8
SEED = 0
PATHS = "local_data/r04_paths"
MIN_ACTIVE_STEPS = 8


def znorm(W):
    mu, sd = W.mean(1, keepdims=True), W.std(1, keepdims=True)
    return (W - mu) / sd, sd.ravel()


def set_profile(Z, groups, chunk=2000):
    """Nearest-neighbour z-normalised distance of each row, excluding rows of the same group."""
    m = Z.shape[1]
    n = len(Z)
    P = np.full(n, np.inf)
    I = np.full(n, -1)
    for s in range(0, n, chunk):
        C = Z[s:s + chunk] @ Z.T / m                       # Pearson correlation
        D = np.sqrt(np.maximum(2 * m * (1 - C), 0))
        D[groups[s:s + chunk, None] == groups[None, :]] = np.inf
        I[s:s + chunk] = D.argmin(1)
        P[s:s + chunk] = D[np.arange(len(D)), I[s:s + chunk]]
    return P, I


def motif_sets(Z, P, R, k=N_MOTIFS, chunk=4000):
    free = np.ones(len(Z), bool)
    m = Z.shape[1]
    out = []
    for _ in range(k):
        cand = np.where(free, P, np.inf)
        i = int(np.argmin(cand))
        if not np.isfinite(cand[i]):
            break
        d = np.sqrt(np.maximum(2 * m * (1 - Z @ Z[i] / m), 0))
        members = np.flatnonzero(free & (d <= R))
        out.append((i, members))
        free[members] = False
    return out


def surrogate(L, rng):
    S = L.copy()
    inc = np.diff(L[:, MOVE_AT:], axis=1)
    for r in range(len(S)):
        inc[r] = rng.permutation(inc[r])
    S[:, MOVE_AT + 1:] = L[:, [MOVE_AT]] + np.cumsum(inc, axis=1)
    return S


def load(n_sample):
    p = pd.concat([pd.read_parquet(f) for f in glob.glob(f"{PATHS}/moves_*.parquet")], ignore_index=True)
    t = pd.read_parquet("local_data/r03_big_moves_900.parquet")
    # the 4 h path must stay inside the market's window: otherwise short markets (games) run
    # into their resolution after the jump, and those paths all match each other trivially.
    # ret_6h is set only when the window has 6 h left after the jump (remote/s2_events.py).
    t = t[t.ret_6h.notna()]
    info = pd.read_parquet("local_data/markets_final.parquet", columns=["id", "event_id"])
    info = info[pd.to_numeric(info.id, errors="coerce").notna()]
    ev = pd.Series(info.event_id.values, index=info.id.astype(int).values)
    p = p.merge(t[["market", "t_close", "tg", "sgn", "outcome", "oc", "cat", "absdp"]], on=["market", "t_close"], how="inner")
    p["event"] = p.market.map(ev[~ev.index.duplicated()])
    P = p.filter(regex=r"^p\d+$").values.astype("float64")
    ok = np.isfinite(P).all(1)
    p, P = p[ok].reset_index(drop=True), P[ok]
    L = np.log(np.clip(P, 0.01, 0.99) / (1 - np.clip(P, 0.01, 0.99)))
    # orient every window so the move goes up (shape, not direction)
    L = L * p.sgn.values[:, None]
    # Trivial-match filter: a window that is flat apart from the jump (no trades after it)
    # matches every other such window exactly. Require the price to change in at least
    # MIN_ACTIVE_STEPS of the post-move 5-min steps.
    active = (np.abs(np.diff(L[:, MOVE_AT:], axis=1)) > 1e-6).sum(1)
    keep = (L.std(1) > 1e-3) & (active >= MIN_ACTIVE_STEPS)
    print(f"windows with at least {MIN_ACTIVE_STEPS} active post-move steps: {keep.sum():,} of {len(keep):,}")
    p, L = p[keep].reset_index(drop=True), L[keep]
    rng = np.random.default_rng(SEED)
    pick = rng.choice(len(p), size=min(n_sample, len(p)), replace=False)
    return p.iloc[pick].reset_index(drop=True), L[pick]


def describe(L):
    """Simple shape numbers for a set of oriented windows (log-odds)."""
    pre, mv = L[:, MOVE_AT - 3], L[:, MOVE_AT]
    size = mv - pre
    keep_30m = (L[:, MOVE_AT + 6] - pre) / size
    keep_4h = (L[:, -1] - pre) / size
    run_up = (L[:, MOVE_AT - 3] - L[:, 0]) / size
    return {"kept after 30 min": np.median(keep_30m), "kept after 4 h": np.median(keep_4h),
            "run-up before (share of move)": np.median(run_up)}


def main(n_sample=N_SAMPLE):
    p, L = load(n_sample)
    Z, _ = znorm(L)
    groups = pd.factorize(p.event.fillna(p.market.astype(str)))[0]

    # check the distance against stumpy.mass on a few windows
    T = L[:50].ravel()
    for q in (0, 7, 33):
        dp = stumpy.mass(L[q], T)[::M]
        mine = np.sqrt(np.maximum(2 * M * (1 - Z[:50] @ Z[q] / M), 0))
        assert np.allclose(dp, mine, atol=1e-4), "distance mismatch with stumpy.mass"
    print("distance check vs stumpy.mass: ok")

    P, I = set_profile(Z, groups)
    rng = np.random.default_rng(SEED + 1)
    Ls = surrogate(L, rng)
    Zs, _ = znorm(Ls)
    Ps, _ = set_profile(Zs, groups)
    R = np.percentile(Ps, 5)                                   # a radius rarely reached by chance
    print(f"{len(L):,} windows from {p.market.nunique():,} markets; profile median real {np.median(P):.2f} "
          f"vs surrogate {np.median(Ps):.2f}; radius R = surrogate 5th pct = {R:.2f}")
    print(f"share of windows with a cross-event match within R: real {np.mean(P <= R):.3f} vs surrogate {np.mean(Ps <= R):.3f}")

    real_sets = motif_sets(Z, P, R)
    sur_sets = motif_sets(Zs, Ps, R)
    rows = []
    for rank, (i, mem) in enumerate(real_sets):
        sub = p.iloc[mem]
        d = describe(L[mem])
        rows.append(dict(rank=rank + 1, members=len(mem), surrogate_members=len(sur_sets[rank][1]) if rank < len(sur_sets) else 0,
                         markets=sub.market.nunique(), share_1taker=(sub.tg == "1").mean(),
                         overshoot=sub.oc.sum() / sub.absdp.sum(), **d))
    mot = pd.DataFrame(rows)
    print("\nmotifs (greedy, radius R):")
    print(mot.round(3).to_string(index=False))

    order = np.argsort(-P)
    disc = p.iloc[order[:200]].assign(profile=P[order[:200]])
    dd = describe(L[order[:200]])
    print(f"\ntop-200 discords: share 1 taker {(disc.tg == '1').mean():.2f} (all {(p.tg == '1').mean():.2f}); "
          f"overshoot {disc.oc.sum() / disc.absdp.sum():.3f} (all {p.oc.sum() / p.absdp.sum():.3f}); shape {dd}")
    print("categories of discords:", disc.cat.value_counts().head(6).to_dict())

    np.save("local_data/r04_motif_L.npy", L)
    np.save("local_data/r04_motif_P.npy", P)
    np.save("local_data/r04_motif_Ps.npy", Ps)
    p.assign(profile=P).to_parquet("local_data/r04_motif_windows.parquet", index=False)
    mot.to_csv("local_data/r04_motifs.csv", index=False)
    import pickle
    with open("local_data/r04_motif_sets.pkl", "wb") as f:
        pickle.dump({"real": real_sets, "sur": sur_sets, "R": R}, f)
    return p, L, P, Ps, mot


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else N_SAMPLE)
