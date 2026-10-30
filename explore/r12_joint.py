"""
Round 12: joint elbow search for the parameters that define a price jump, and for the
next-trades price, on every market (remote/s12_grid.py on all 32 buckets, run on the server).

Parameters that depend on each other are searched together, by coordinate-wise fixed point:
each one is set to the knee of its curve with all the others at their current knees, and the
loop repeats until no knee moves. The knee is the Kneedle point (explore/elbow.knee):
the point of the curve farthest from the chord between its ends, both axes scaled to [0, 1].

  jump definition (curve: number of price jumps)
    slot      slot length, minutes                 1 - 120
    theta     jump threshold, points                5 - 50
    cut_start share of the life left out at the start, %   0 - 30
    cut_end   share of the life left out at the end, %     0 - 30
    edge      settle band edge, points              1 - 20
    clip      price clip before jumps are measured, points   0.1 - 5
  next trades (at the jump definition found above)
    n_next    trades averaged (curve: overshoot at the next trades)   1 - 16
    t_next    minutes allowed (curve: share of jumps with next trades) 1 - 180 (crypto 0.25 - 15)
The same is done for the crypto up/down markets (mode cx, slot 15 s - 5 min).
Also: two-dimensional grids of the number of jumps over (slot, theta) and (cut_end, edge),
with the knee of each row and column, to show how each knee depends on the other parameter.

Outputs local_data/r12/<mode>_fixed.csv (the knee path), <mode>_curves.csv (each curve at the
fixed point), <mode>_grid_slot_theta.csv, <mode>_grid_cut_edge.csv, <mode>_next.csv.
Usage: python explore/r12_joint.py [events|cx]
On the server, on every market (the grid is too large to copy): PM_GRID=tmp/grid PM_OUT=tmp/joint
PM_MARKETS=<markets_final.parquet> PM_TAGS=<market_tags.csv> python r12_joint.py events (with
r02_persistence.py, r03_robustness.py and elbow.py next to it); only the small CSVs come back.
"""
import glob
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "explore")
from r02_persistence import TAGS, category, outcomes  # noqa: E402
from r03_robustness import cat_baseline, overshoot_cat  # noqa: E402
from elbow import knee  # noqa: E402

SRC = os.environ.get("PM_GRID", "local_data/r12/grid")     # the server run reads tmp/grid and writes tmp/joint
OUT = os.environ.get("PM_OUT", "local_data/r12")
EDGES = (0.01, 0.02, 0.03, 0.05, 0.10, 0.15, 0.20)
CLIPS = (0.001, 0.0025, 0.005, 0.01, 0.02, 0.03, 0.05)
CUTS = np.arange(0, 30.5, 0.5) / 100
THETAS = np.arange(5, 51) / 100
START = {"events": dict(slot=1800, theta=0.13, cut_start=0.05, cut_end=0.05, edge=0.05, clip=0.01),   # any start:
         "cx": dict(slot=60, theta=0.13, cut_start=0.0, cut_end=0.0, edge=0.05, clip=0.01)}      # it converges
N_GRID = np.arange(1, 17)
T_GRID = {"events": np.array([1, 2, 5, 10, 15, 20, 30, 45, 60, 90, 120, 180]),
          "cx": np.array([0.25, 0.5, 1, 2, 3, 5, 7.5, 10, 15])}


def read(mode, c):
    return pd.concat([pd.read_parquet(f) for f in sorted(glob.glob(f"{SRC}/{mode}/{c}*.parquet"))], ignore_index=True)


class Grid:
    """Jumps under any parameter set, with cached positions in the market's life."""

    def __init__(self, mode):
        self.mode = mode
        self.j = {s: x.reset_index(drop=True) for s, x in read(mode, "j").groupby("slot")}
        self.r = {s: x.reset_index(drop=True) for s, x in read(mode, "r").groupby("slot")}
        self.m = {s: x.set_index("market") for s, x in read(mode, "m").groupby("slot")}
        self.slots = sorted(self.j)
        self._pos = {}

    def pos(self, kind, slot, edge):
        key = (kind, slot, edge)
        if key not in self._pos:
            x = (self.j if kind == "j" else self.r)[slot]
            m = self.m[slot].reindex(x.market.values)
            t0 = m.t_first.values
            t1 = np.where(np.isnan(m[f"settle_{edge:g}"].values), m.t_last.values, m[f"settle_{edge:g}"].values)
            t = x.t_close.values
            self._pos[key] = ((t - t0) / np.maximum(t1 - t0, 1), t <= t1)
        return self._pos[key]

    def mask(self, kind, P):
        f, before = self.pos(kind, P["slot"], P["edge"])
        return before & (f >= P["cut_start"]) & (f <= 1 - P["cut_end"])

    def jumps(self, P):
        x = self.j[P["slot"]]
        p = np.clip(x.vwap.values, P["clip"], 1 - P["clip"])
        keep = self.mask("j", P) & (np.abs(p - x.y_pre.values) >= P["theta"])
        out = x[keep].copy()
        out["p_close"] = p[keep]
        return out

    def count(self, P):
        x = self.j[P["slot"]]
        p = np.clip(x.vwap.values, P["clip"], 1 - P["clip"])
        return int((self.mask("j", P) & (np.abs(p - x.y_pre.values) >= P["theta"])).sum())

    def randoms(self, P):
        return self.r[P["slot"]][self.mask("r", P)]


def axes(g):
    return {"slot": np.array(g.slots), "theta": THETAS, "cut_start": CUTS, "cut_end": CUTS,
            "edge": np.array(EDGES), "clip": np.array(CLIPS)}


SCALE = {"slot": 1 / 60, "theta": 100, "cut_start": 100, "cut_end": 100, "edge": 100, "clip": 100}


def curve(g, P, name, values):
    return np.array([g.count({**P, name: v}) for v in values])


def fixed_point(g, start, max_iter=10):
    P, path = dict(start), [dict(start, iteration=0)]
    ax = axes(g)
    for it in range(1, max_iter + 1):
        old = dict(P)
        for name, values in ax.items():
            y = curve(g, P, name, values)
            P[name] = values[knee(values * SCALE[name], y)]
        path.append(dict(P, iteration=it))
        print(f"iteration {it}: " + ", ".join(f"{k}={v * SCALE[k]:g}" for k, v in P.items()), flush=True)
        if P == old:
            break
    return P, pd.DataFrame(path)


def grids(g, P):
    ax = axes(g)
    st = pd.DataFrame([{"slot": s / 60, "theta": t * 100, "jumps": g.count({**P, "slot": s, "theta": t})}
                       for s in ax["slot"] for t in ax["theta"]])
    ce = pd.DataFrame([{"cut_end": c * 100, "edge": e * 100, "jumps": g.count({**P, "cut_end": c, "edge": e})}
                       for c in ax["cut_end"] for e in ax["edge"]])
    return st, ce


def row_knees(df, row, col):
    """Knee of `col` for each value of `row` (curve: jumps)."""
    out = {}
    for v, s in df.groupby(row):
        s = s.sort_values(col)
        out[v] = s[col].values[knee(s[col].values, s.jumps.values)]
    return pd.Series(out, name=f"knee_{col}")


def with_outcome(x):
    out = outcomes()
    tags = pd.read_csv(TAGS, dtype=str)
    cats = pd.Series(category(tags.tags).values, index=tags.market_id.astype(int).values)
    x = x.assign(outcome=x.market.map(out))
    x = x[x.outcome.notna()].copy()
    x["cat"] = x.market.map(cats).fillna("other")
    return x


def entry(x, n, max_s):
    y = np.stack([x[f"y{i}"].values for i in range(n)], 1)
    u = np.stack([x[f"u{i}"].values for i in range(n)], 1)
    dt = np.stack([x[f"dt{i}"].values for i in range(n)], 1)
    u = np.where((dt >= 0) & (dt < max_s), np.nan_to_num(u), 0)
    return np.where(u.sum(1) > 0, (np.nan_to_num(y) * u).sum(1) / np.maximum(u.sum(1), 1e-12), np.nan)


def next_search(g, P, x_all, tgrid, start_n=8, start_t=60):
    """Fixed point over (n_next, t_next) at the jump definition P, plus the curves there."""
    j = with_outcome(g.jumps(P))
    j["absdp"] = (j.p_close - j.y_pre).abs()
    j["sgn"] = np.sign(j.p_close - j.y_pre)
    rnd = with_outcome(g.randoms(P))
    cb = cat_baseline(rnd)
    x = j.merge(x_all[x_all.slot == P["slot"]], on=["slot", "market", "t_close"])
    n, t = start_n, start_t
    def os_curve(t_min):
        ys = []
        for k in N_GRID:
            e = entry(x, k, t_min * 60)
            ok = ~np.isnan(e)
            ys.append(overshoot_cat(x[ok], e[ok], cb).sum() / x.absdp[ok].sum())
        return np.array(ys)
    def cov_curve(k):
        return np.array([(~np.isnan(entry(x, k, tm * 60))).mean() for tm in tgrid])
    for _ in range(10):
        old = (n, t)
        n = int(N_GRID[knee(N_GRID, os_curve(t))])
        t = float(tgrid[knee(tgrid, cov_curve(n))])
        if (n, t) == old:
            break
    return n, t, os_curve(t), cov_curve(n)


def main(mode):
    os.makedirs(OUT, exist_ok=True)
    g = Grid(mode)
    P, path = fixed_point(g, START[mode])
    path.to_csv(f"{OUT}/{mode}_fixed.csv", index=False)
    rows = []
    for name, values in axes(g).items():
        y = curve(g, P, name, values)
        k = knee(values * SCALE[name], y)
        rows += [{"curve": name, "x": v * SCALE[name], "y": c, "knee": values[k] * SCALE[name]} for v, c in zip(values, y)]
    st, ce = grids(g, P)
    st.to_csv(f"{OUT}/{mode}_grid_slot_theta.csv", index=False)
    ce.to_csv(f"{OUT}/{mode}_grid_cut_edge.csv", index=False)
    print("theta knee by slot:", row_knees(st, "slot", "theta").to_dict())
    print("slot knee by theta:", row_knees(st, "theta", "slot").to_dict())
    print("cut_end knee by edge:", row_knees(ce, "edge", "cut_end").to_dict())
    print("edge knee by cut_end:", row_knees(ce, "cut_end", "edge").to_dict())

    x_all = read(mode, "x")
    tgrid = T_GRID[mode]
    nxt = []
    for s in sorted(x_all.slot.unique()):
        n, t, osc, cov = next_search(g, {**P, "slot": s}, x_all, tgrid,
                                     start_t=60 if mode == "events" else 5)
        nxt.append({"slot": s / 60, "n_next": n, "t_next": t})
        if s == P["slot"]:
            rows += [{"curve": "n_next", "x": k, "y": v, "knee": n} for k, v in zip(N_GRID, osc)]
            rows += [{"curve": "t_next", "x": k, "y": v, "knee": t} for k, v in zip(tgrid, cov)]
        print(f"next trades at slot {s / 60:g} min: n = {n}, t = {t:g} min", flush=True)
    pd.DataFrame(nxt).to_csv(f"{OUT}/{mode}_next.csv", index=False)
    pd.DataFrame(rows).to_csv(f"{OUT}/{mode}_curves.csv", index=False)
    print("fixed point:", {k: v * SCALE[k] for k, v in P.items()})


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "events")
