"""
Round 5, part 3: explaining the two round-4 matrix-profile results.

A. Post-move paths (local_data/r04_motif_windows.parquet + r04_motif_L.npy: 20k windows of
   55 five-minute log-odds points around big moves, with each window's matrix-profile value,
   i.e. its z-normalised distance to the most similar window from another event).
   Round 4 found that typical windows (low profile) don't overshoot and unusual ones do.
   Here: describe each window by simple features (how much of the move it gives back over
   the next 4 h, how rough the path is, how many 5-min steps have a price change), check how
   much of the profile value they explain, and whether the overshoot gradient survives
   within groups of windows that give back the same amount.

B. Bitcoin 15-minute chain (local_data/r04_btc_profile.parquet, r04_btc_T.npy). One value
   per market: the profile value of the window that covers exactly that market. Features:
   crossings of 50%, price range, final distance from 50%, trades in the window. Then
   - how much of the profile value the features explain (least squares R^2);
   - persistence: correlation between a market's profile value and the next markets' (lags
     1 to 96 = one day), against shuffled order;
   - calendar: weekday vs weekend, hour of the week, and the Federal Reserve (FOMC)
     decision windows (statement time 14:00 New York time).

Usage: python explore/r05_mp_explained.py
"""
import numpy as np
import pandas as pd

OUT = "local_data/r05/"
MOVE_AT = 7
# FOMC statement days (Federal Reserve calendar), Sep 2025 - May 2026
FOMC = ["2025-09-17", "2025-10-29", "2025-12-10", "2026-01-28", "2026-03-18", "2026-04-29"]


def r2(X, y):
    X = np.column_stack([np.ones(len(y)), X])
    b, *_ = np.linalg.lstsq(X, y, rcond=None)
    return 1 - ((y - X @ b) ** 2).sum() / ((y - y.mean()) ** 2).sum()


def part_a():
    w = pd.read_parquet("local_data/r04_motif_windows.parquet")
    L = np.load("local_data/r04_motif_L.npy")                 # log-odds, oriented so the move is up
    post = L[:, MOVE_AT:]
    move = L[:, MOVE_AT] - L[:, MOVE_AT - 1]
    steps = np.diff(post, axis=1)
    w["giveback"] = -(post[:, -1] - post[:, 0]) / np.abs(move)          # share of the move given back by +4 h
    w["roughness"] = np.abs(steps).sum(1) / np.abs(move)                  # path length after the move, in moves
    w["active"] = (np.abs(steps) > 1e-6).sum(1)
    w = w[w.oc.notna() & np.isfinite(w.giveback)].copy()
    feats = ["giveback", "roughness", "active"]
    Xf = np.column_stack([w.giveback.clip(-3, 3), np.log1p(w.roughness), w.active])
    print(f"[A] {len(w):,} post-move windows; R^2 of profile value on {feats}: {r2(Xf, w.profile.values):.3f}")
    for f in feats:
        print(f"    Spearman(profile, {f}) = {w.profile.corr(w[f], method='spearman'):.3f}")
    w["dec"] = pd.qcut(w.profile, 10, labels=False) + 1
    w["gb_q"] = pd.qcut(w.giveback.rank(method="first"), 5, labels=["gives back least", "2", "3", "4", "gives back most"])
    w["prof_half"] = np.where(w.profile <= w.profile.median(), "typical half", "unusual half")
    sh = lambda x: x.oc.sum() / x.absdp.sum()
    by_dec = w.groupby("dec").apply(lambda x: pd.Series({"overshoot": sh(x), "giveback": x.giveback.median(),
                                                         "roughness": x.roughness.median(), "active": x.active.median()}))
    within = w.groupby(["gb_q", "prof_half"], observed=True).apply(sh).unstack()
    print("by profile decile:\n", by_dec.round(3).to_string())
    print("overshoot within give-back quintiles (typical vs unusual half of the profile):\n", within.round(3).to_string())
    by_dec.to_csv(OUT + "r05_mp_moves_by_decile.csv")
    within.to_csv(OUT + "r05_mp_moves_within.csv")
    return w


def part_b():
    df = pd.read_parquet("local_data/r04_btc_profile.parquet")
    T = np.load("local_data/r04_btc_T.npy")
    al = df[df.aligned].copy()
    idx = al.index.values
    W = np.stack([T[i:i + 30] for i in idx])
    p = 1 / (1 + np.exp(-W))
    side = np.sign(p - 0.5)
    al["crossings"] = (np.diff(side, axis=1) != 0).sum(1)
    al["range"] = p.max(1) - p.min(1)
    al["final_dist"] = np.abs(p[:, -1] - 0.5)
    al["vol"] = np.abs(np.diff(W, axis=1)).sum(1)
    al = al.reset_index(drop=True)
    X = np.column_stack([al.crossings, al.range, al.final_dist, np.log1p(al.vol)])
    print(f"\n[B] {len(al):,} bitcoin 15-min markets; R^2 of profile on crossings, range, final distance, path length: "
          f"{r2(X, al.profile.values):.3f}; crossings alone: {r2(al[['crossings']].values, al.profile.values):.3f}")
    for f in ("crossings", "range", "final_dist", "vol"):
        print(f"    Spearman(profile, {f}) = {al.profile.corr(al[f], method='spearman'):.3f}")
    # persistence across consecutive markets (on the continuous 15-min grid, gaps stay gaps)
    slot = ((al.start - al.start.min()).dt.total_seconds() // 900).astype(int)
    s = pd.Series(al.profile.values, index=slot.values).reindex(range(slot.max() + 1))
    z = (s - s.mean()) / s.std()
    lags = [1, 2, 4, 8, 16, 32, 48, 96, 672]
    ac = {l: z.autocorr(l) for l in lags}
    rng = np.random.default_rng(3)
    null = [pd.Series(rng.permutation(z.values)).autocorr(1) for _ in range(200)]
    print("    autocorrelation of the profile value by lag (markets):", {k: round(v, 3) for k, v in ac.items()},
          f"| shuffled lag-1: {np.nanmean(null):.3f} ± {np.nanstd(null):.3f}")
    # calendar
    al["weekend"] = al.start.dt.dayofweek >= 5
    al["top"] = al.profile >= al.profile.quantile(0.95)
    ny = al.start.dt.tz_localize("UTC").dt.tz_convert("America/New_York")
    al["ny_hour"] = ny.dt.hour
    al["fomc"] = ny.dt.strftime("%Y-%m-%d").isin(FOMC) & (ny.dt.hour == 14)
    al["us_open"] = (~al.weekend) & (ny.dt.hour == 9) & (ny.dt.minute >= 30)
    al["us_data"] = (~al.weekend) & (ny.dt.hour == 8) & (ny.dt.minute >= 30)
    base = al.top.mean()
    rows = []
    for name, m in (("weekend", al.weekend), ("weekday", ~al.weekend), ("US data time 8:30-9:00 NY, weekdays", al.us_data),
                    ("US stock open 9:30-10:00 NY, weekdays", al.us_open), ("FOMC statement hour (14-15 NY)", al.fomc)):
        rows.append({"when": name, "markets": int(m.sum()), "share in top 5%": al.top[m].mean(),
                     "ratio to all": al.top[m].mean() / base, "median crossings": al.crossings[m].median(),
                     "mean crossings": al.crossings[m].mean()})
    cal = pd.DataFrame(rows)
    print(cal.round(3).to_string(index=False))
    how = al.assign(dow=al.start.dt.dayofweek, h=al.start.dt.hour).groupby(["dow", "h"]).top.mean().unstack() / base
    al.to_parquet(OUT + "r05_btc_markets.parquet", index=False)
    cal.to_csv(OUT + "r05_btc_calendar.csv", index=False)
    how.to_csv(OUT + "r05_btc_hour_of_week.csv")
    pd.Series(ac).to_csv(OUT + "r05_btc_autocorr.csv")
    return al, cal, ac


if __name__ == "__main__":
    part_a()
    part_b()
