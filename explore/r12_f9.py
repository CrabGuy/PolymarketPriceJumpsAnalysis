"""
Round 12: the elbow of every parameter of the pattern search (F9), from 1-minute price paths
(remote/s4_paths.py finemoves: each jump's price at every minute from 60 min before to 8 h
after its slot's close; copied to local_data/r12/fine/).

Part A (paths), curves and knees:
  step     mean |error| (points) of a path sampled every a minutes (each value held until
           the next) against the 1-minute path, vs a (1-30)
  after    mean |price t minutes after the close - price at the close| (points), vs t (0-480)
  before   mean |price t minutes before the close - price at the close| (points), vs t (0-60)
  changes  windows kept vs the minimum number of post-jump steps with a price change
  hours    share of the paths that leave the settle band within the path, among jumps with at
           least H hours of window left, vs H (0-24)
Part B (search), with the part A values in explore/r02_persistence.py:
  writes the paths at the chosen step and span to local_data/r04_paths/moves_*.parquet (read
  by explore/r04_motifs.py and the report figures), then
  radius   the r-th percentile of the surrogates' matrix profile, vs r (1-50)
  sample   spread of the share of real paths with a close match over 5 draws, vs the number
           of jumps drawn (1,000-30,000)

Outputs local_data/r12/f9_curves_<part>.csv, f9_knees_<part>.csv.
Usage: python explore/r12_f9.py A|B
"""
import glob
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "explore")
from r02_persistence import EDGE, F9_AFTER, F9_BEFORE, F9_STEP  # noqa: E402
from elbow import knee  # noqa: E402

FINE = "local_data/r12/fine"
OUT = "local_data/r12"
ZERO = 60                     # index of the slot's close in the 1-minute paths (offsets -60 .. 480)


def fine():
    p = pd.concat([pd.read_parquet(f) for f in sorted(glob.glob(f"{FINE}/fine_*.parquet"))], ignore_index=True)
    P = p.filter(regex=r"^p\d+$").values.astype(float)
    ok = np.isfinite(P[:, ZERO])
    return p.loc[ok, ["market", "t_close"]].reset_index(drop=True), P[ok]


def held(P, a):
    """The path sampled every a minutes from the close (both ways), each value held until the next."""
    idx = np.arange(P.shape[1])
    last = ZERO + ((idx - ZERO) // a) * a                    # the latest sample time at or before each minute
    last = np.clip(last, 0, P.shape[1] - 1)
    return P[:, last]


def hours_left(p):
    m = pd.concat([pd.read_parquet(f, columns=["market", "t1"]) for f in glob.glob("local_data/r02_events/m*.parquet")])
    t1 = m.drop_duplicates("market").set_index("market").t1
    return (t1.reindex(p.market.values).values - p.t_close.values) / 3600


def part_a():
    p, P = fine()
    rows, knees = [], []

    def add(name, x, y, what):
        k = knee(np.asarray(x, float), np.asarray(y, float))
        rows.append(pd.DataFrame({"curve": name, "x": x, "y": y}))
        knees.append({"curve": name, "knee": x[k], "what": what})
        print(f"{name:8s} knee {x[k]:g}; " + ", ".join(f"{a:g}:{v:.4g}" for a, v in zip(x, y)), flush=True)

    A = np.array([1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30])
    add("step", A, np.array([np.nanmean(np.abs(held(P, a) - P)) * 100 for a in A]), "error of the sampled path, points")
    T = np.arange(0, 481, 10)
    add("after", T, np.array([np.nanmean(np.abs(P[:, ZERO + t] - P[:, ZERO])) * 100 for t in T]),
        "distance from the price at the close, points")
    B = np.arange(0, 61, 5)
    add("before", B, np.array([np.nanmean(np.abs(P[:, ZERO - t] - P[:, ZERO])) * 100 for t in B]),
        "distance from the price at the close, points")
    a = F9_STEP
    post = P[:, ZERO:ZERO + F9_AFTER + 1:a]
    changes = (np.abs(np.diff(post, axis=1)) > 1e-9).sum(1)
    C = np.arange(0, post.shape[1])
    add("changes", C, np.array([(changes >= c).sum() for c in C]), "paths kept")
    left = hours_left(p)
    span = P[:, ZERO:ZERO + F9_AFTER + 1]
    leaves = ((span < EDGE) | (span > 1 - EDGE)).any(1)
    H = np.array([0, 0.5, 1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 24])
    add("hours", H, np.array([leaves[left >= h].mean() * 100 for h in H]), "paths that run into the settle band, %")
    pd.concat(rows).to_csv(f"{OUT}/f9_curves_A.csv", index=False)
    pd.DataFrame(knees).to_csv(f"{OUT}/f9_knees_A.csv", index=False)


def write_paths():
    """Paths at F9_STEP from F9_BEFORE before to F9_AFTER after the close, as explore/r04_motifs.py reads them."""
    os.makedirs("local_data/r04_paths", exist_ok=True)
    for f in sorted(glob.glob(f"{FINE}/fine_*.parquet")):
        p = pd.read_parquet(f)
        P = p.filter(regex=r"^p\d+$").values
        cols = ZERO + np.arange(-F9_BEFORE, F9_AFTER + 1, F9_STEP)
        out = pd.DataFrame(P[:, cols].astype("float32"), columns=[f"p{i}" for i in range(len(cols))])
        out.insert(0, "t_close", p.t_close.values)
        out.insert(0, "market", p.market.values)
        out.to_parquet(f"local_data/r04_paths/moves_{f[-10:-8]}.parquet", index=False)


def part_b():
    write_paths()
    import r04_motifs as rm
    rows, knees = [], []

    def add(name, x, y, what):
        k = knee(np.asarray(x, float), np.asarray(y, float))
        rows.append(pd.DataFrame({"curve": name, "x": x, "y": y}))
        knees.append({"curve": name, "knee": x[k], "what": what})
        print(f"{name:8s} knee {x[k]:g}; " + ", ".join(f"{a:g}:{v:.4g}" for a, v in zip(x, y)), flush=True)

    p, L = rm.load(rm.N_SAMPLE)
    groups = pd.factorize(p.event.fillna(p.market.astype(str)))[0]
    Zs, _ = rm.znorm(rm.surrogate(L, np.random.default_rng(rm.SEED + 1)))
    Ps, _ = rm.set_profile(Zs, groups)
    R = np.array([1, 2, 3, 4, 5, 7.5, 10, 15, 20, 25, 30, 40, 50])
    add("radius", R, np.percentile(Ps, R), "surrogate profile percentile")
    sizes = np.array([1000, 2000, 3000, 5000, 7500, 10000, 15000])
    y = []
    rng = np.random.default_rng(3)
    for n in sizes:
        v = []
        for _ in range(5):
            pick = rng.choice(len(L), size=min(n, len(L)), replace=False)
            Z, _ = rm.znorm(L[pick])
            P_, _ = rm.set_profile(Z, groups[pick])
            Zs_, _ = rm.znorm(rm.surrogate(L[pick], rng))
            Ps_, _ = rm.set_profile(Zs_, groups[pick])
            v.append(np.mean(P_ <= np.percentile(Ps_, rm.F9_RADIUS_PCT)) * 100)
        y.append(np.std(v))
        print(f"  sample {n}: spread {np.std(v):.3f}", flush=True)
    add("sample", sizes, np.array(y), "spread of the match share, points")
    pd.concat(rows).to_csv(f"{OUT}/f9_curves_B.csv", index=False)
    pd.DataFrame(knees).to_csv(f"{OUT}/f9_knees_B.csv", index=False)


if __name__ == "__main__":
    {"A": part_a, "B": part_b}[sys.argv[1]]()
