"""
Round 12: joint elbow search for the parameters that define a price jump, and for the
next-trades price, on every market (remote/s12_grid.py on all 32 buckets, run on the server).

All eight parameters depend on each other and are searched together, by coordinate-wise fixed
point: each one is set to the knee of its curve with all the others at their current values,
and the loop repeats until no value moves. The knee is the Kneedle point after the checks of
explore/elbow.find: a flat curve keeps the parameter at NEUTRAL (or its current value, when it
cannot be dropped), and peaks, straight curves and knees at an end of the range are flagged.

  slot      slot length, minutes                          1 - 120
            curve: number of jumps
  theta     jump threshold, points                        5 - 50     curve: number of jumps
  cut_start share of the life left out at the start, %    0 - 30     curve: number of jumps
  cut_end   share of the life left out at the end, %      0 - 30     curve: number of jumps
  edge      settle band edge, points                      1 - 20     curve: number of jumps
  clip      price clip before jumps are measured, points  0.1 - 5    curve: number of jumps
  n_next    next trades averaged                          1 - 16     curve: overshoot at the next trades
  t_next    minutes allowed for them                      1 - 180 (crypto 0.25 - 15)
                                                                     curve: share of jumps with next trades
The same is done for the crypto up/down markets (mode cx, slot 15 s - 5 min).
Also: two-dimensional grids of the number of jumps over (slot, theta) and (cut_end, edge),
with the knee of each row and column, to show how each knee depends on the other parameter.

Outputs local_data/r12/<mode>_fixed.csv (the knee path), <mode>_curves.csv (each curve at the
fixed point), <mode>_grid_slot_theta.csv (jumps and reversal share), <mode>_grid_cut_edge.csv.
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
from elbow import find  # noqa: E402

SRC = os.environ.get("PM_GRID", "local_data/r12/grid")     # the server run reads tmp/grid and writes tmp/joint
OUT = os.environ.get("PM_OUT", "local_data/r12")
EDGES = (0.01, 0.02, 0.03, 0.05, 0.10, 0.15, 0.20)
CLIPS = (0.001, 0.0025, 0.005, 0.01, 0.02, 0.03, 0.05)
CUTS = np.arange(0, 30.5, 0.5) / 100
THETAS = np.arange(5, 51) / 100
START = {"events": dict(slot=1800, theta=0.15, cut_start=0.07, cut_end=0.045, edge=0.03, clip=0.02, n_next=5, t_next=45),
         "cx": dict(slot=60, theta=0.18, cut_start=0.0, cut_end=0.075, edge=0.03, clip=0.03, n_next=5, t_next=2)}
NEUTRAL = {"cut_start": 0.0, "cut_end": 0.0}   # a flat curve drops the parameter; the clip stays as a log-odds guard
N_GRID = np.arange(1, 17)
T_GRID = {"events": np.array([1, 2, 5, 10, 15, 20, 30, 45, 60, 90, 120, 180]),
          "cx": np.array([0.25, 0.5, 1, 2, 3, 5, 7.5, 10, 15])}


def read(mode, c, **kw):
    return pd.concat([pd.read_parquet(f, **kw) for f in sorted(glob.glob(f"{SRC}/{mode}/{c}*.parquet"))],
                     ignore_index=True)


class Grid:
    """Jumps under any parameter set, with cached positions in the market's life."""

    def __init__(self, mode):
        self.mode = mode
        self.j = {s: x.reset_index(drop=True) for s, x in read(mode, "j").groupby("slot")}
        self.r = {s: x.reset_index(drop=True) for s, x in read(mode, "r").groupby("slot")}
        self.m = {s: x.set_index("market") for s, x in read(mode, "m").groupby("slot")}
        self.slots = sorted(self.j)
        self._pos, self._x = {}, {}
        self.out = outcomes()
        tags = pd.read_csv(TAGS, dtype=str)
        self.cats = pd.Series(category(tags.tags).values, index=tags.market_id.astype(int).values)

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

    def next_trades(self, slot):
        """(pos, y, u, dt) for j[slot]: pos is each move's row in the next-trade arrays (-1: none
        stored). One slot length is kept in memory at a time."""
        if slot not in self._x:
            self._x.clear()
            x = read(self.mode, "x", filters=[("slot", "==", int(slot))]).drop(columns="slot")
            x["row"] = np.arange(len(x), dtype="int64")
            pos = self.j[slot][["market", "t_close"]].merge(x[["market", "t_close", "row"]],
                                                            on=["market", "t_close"], how="left")["row"]
            self._x[slot] = (pos.fillna(-1).to_numpy("int64"),) + tuple(
                x[[f"{c}{k}" for k in range(16)]].to_numpy("float32") for c in ("y", "u", "dt"))
        return self._x[slot]

    def entry(self, P, n, t_min):
        """Next-trades price (VWAP of the first n trades within t_min minutes) of jumps(P), and the jumps."""
        pos, y, u, dt = self.next_trades(P["slot"])
        x = self.jumps(P)
        r = pos[x.index.values]
        e = np.full(len(x), np.nan)
        ok = r >= 0
        y, u, dt = y[r[ok], :n], u[r[ok], :n], dt[r[ok], :n]
        u = np.where((dt >= 0) & (dt < t_min * 60), np.nan_to_num(u), 0)
        e[ok] = np.where(u.sum(1) > 0, (np.nan_to_num(y) * u).sum(1) / np.maximum(u.sum(1), 1e-12), np.nan)
        return e, x

    def reversal(self, P, n, t_min):
        """Share of the jumps whose next-trades price is back by more than half the jump."""
        e, x = self.entry(P, n, t_min)
        dp = x.p_close.values - x.y_pre.values
        ok = ~np.isnan(e)
        return float((((x.p_close.values - e) * np.sign(dp))[ok] > 0.5 * np.abs(dp[ok])).mean())

    def with_outcome(self, x):
        x = x.assign(outcome=x.market.map(self.out))
        x = x[x.outcome.notna()].copy()
        x["cat"] = x.market.map(self.cats).fillna("other")
        return x


def axes(g, mode):
    return {"slot": np.array(g.slots), "theta": THETAS, "cut_start": CUTS, "cut_end": CUTS,
            "edge": np.array(EDGES), "clip": np.array(CLIPS), "n_next": N_GRID, "t_next": T_GRID[mode]}


SCALE = {"slot": 1 / 60, "theta": 100, "cut_start": 100, "cut_end": 100, "edge": 100, "clip": 100,
         "n_next": 1, "t_next": 1}
WHAT = {"n_next": "overshoot at the next trades", "t_next": "share with next trades"}


def overshoot_next(g, P, n, t_min):
    """Overshoot share (%) measured at the next-trades price instead of the slot price."""
    e, x = g.entry(P, n, t_min)
    x = x.assign(e=e, absdp=(x.p_close - x.y_pre).abs(), sgn=np.sign(x.p_close - x.y_pre))
    x = g.with_outcome(x[~np.isnan(e)])
    cb = cat_baseline(g.with_outcome(g.randoms(P)))
    return 100 * overshoot_cat(x, x.e.values, cb).sum() / x.absdp.sum()


def curve(g, P, name, values):
    if name == "n_next":
        return np.array([overshoot_next(g, P, int(v), P["t_next"]) for v in values])
    if name == "t_next":
        return np.array([(~np.isnan(g.entry(P, P["n_next"], v)[0])).mean() for v in values])
    return np.array([g.count({**P, name: v}) for v in values])


def pick(name, values, y, current):
    """The value find() gives, and its kind; a flat curve drops the parameter (NEUTRAL) or keeps it."""
    i, kind = find(values * SCALE[name], y)
    if kind == "flat":
        return NEUTRAL.get(name, current), kind
    return values[i], kind


def fixed_point(g, mode, max_iter=10):
    P, path = dict(START[mode]), [dict(START[mode], iteration=0)]
    ax = axes(g, mode)
    for it in range(1, max_iter + 1):
        old, kinds = dict(P), {}
        for name, values in ax.items():
            P[name], kinds[name] = pick(name, values, curve(g, P, name, values), P[name])
        P["n_next"] = int(P["n_next"])
        path.append(dict(P, iteration=it))
        print(f"iteration {it}: " + ", ".join(f"{k}={v * SCALE[k]:g} ({kinds[k]})" for k, v in P.items()), flush=True)
        if P == old:
            break
    return P, kinds, pd.DataFrame(path)


def grids(g, P, mode):
    ax = axes(g, mode)
    st = pd.DataFrame([{"slot": s / 60, "theta": t * 100, "jumps": g.count({**P, "slot": s, "theta": t}),
                        "reversal": g.reversal({**P, "slot": s, "theta": t}, P["n_next"], P["t_next"])}
                       for s in ax["slot"] for t in ax["theta"]])
    ce = pd.DataFrame([{"cut_end": c * 100, "edge": e * 100, "jumps": g.count({**P, "cut_end": c, "edge": e})}
                       for c in ax["cut_end"] for e in ax["edge"]])
    return st, ce


def row_knees(df, row, col, y="jumps"):
    """Value find() gives for `col` (curve: y) at each value of `row`."""
    out = {}
    for v, s in df.groupby(row):
        s = s.sort_values(col)
        i, kind = find(s[col].values, s[y].values)
        out[v] = f"{s[col].values[i]:g} ({kind})"
    return pd.Series(out, name=f"knee_{col}")


def main(mode):
    os.makedirs(OUT, exist_ok=True)
    g = Grid(mode)
    P, kinds, path = fixed_point(g, mode)
    path.to_csv(f"{OUT}/{mode}_fixed.csv", index=False)
    rows = []
    for name, values in axes(g, mode).items():
        y = curve(g, P, name, values)
        rows += [{"curve": name, "x": v * SCALE[name], "y": c, "knee": P[name] * SCALE[name], "kind": kinds[name]}
                 for v, c in zip(values, y)]
    pd.DataFrame(rows).to_csv(f"{OUT}/{mode}_curves.csv", index=False)
    st, ce = grids(g, P, mode)
    st.to_csv(f"{OUT}/{mode}_grid_slot_theta.csv", index=False)
    ce.to_csv(f"{OUT}/{mode}_grid_cut_edge.csv", index=False)
    print("theta knee by slot:", row_knees(st, "slot", "theta").to_dict())
    print("slot knee by theta (reversal):", row_knees(st, "theta", "slot", "reversal").to_dict())
    print("cut_end knee by edge:", row_knees(ce, "edge", "cut_end").to_dict())
    print("edge knee by cut_end:", row_knees(ce, "cut_end", "edge").to_dict())
    print("fixed point:", {k: v * SCALE[k] for k, v in P.items()}, kinds)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "events")
