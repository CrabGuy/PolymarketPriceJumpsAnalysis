"""
Round 4, part 2B: matrix profile of the continuous bitcoin 15-minute up/down series.

Every bitcoin "Up or Down" 15-minute market is turned into 30 YES prices evenly spaced over
its 15-minute window (remote/s4_paths.py, mode "ud"). Markets follow each other back to
back, so concatenating them in time order gives one continuous series (gaps, and markets
with fewer than MIN_TRADES trades in their window, become NaN). stumpy.stump is run on it
with m = 30 (one market length), z-normalised (shapes).
Every market's path runs from about 0.5 towards 0 or 1 (resolution convergence), which is
the trivial shape. So the analysis looks at
  - discords: 15-min stretches unlike any other, with their dates and hours;
  - when anomalies happen: share of the top 1% profile values by hour of day (UTC),
    against the share of all windows in that hour;
  - motifs: the most repeated stretches, reported for completeness.

Usage: python explore/r04_btc_chain.py
"""
import glob
import time

import numpy as np
import pandas as pd
import stumpy

M = 30
MIN_TRADES = 10


def build():
    p = pd.concat([pd.read_parquet(f) for f in glob.glob("local_data/r04_paths/ud_*.parquet")], ignore_index=True)
    tags = pd.read_csv("local_data/market_tags.csv", dtype=str)
    btc = set(tags.market_id[tags.tags.str.contains(r"(?:^|;)bitcoin(?:;|$)", na=False)
                             & tags.tags.str.contains(r"(?:^|;)15M(?:;|$)", na=False)].astype(int))
    p = p[p.market.isin(btc) & (p.dur_min == 15)]
    mk = pd.read_parquet("local_data/markets_final.parquet", columns=["id", "end_date", "question"])
    mk = mk[pd.to_numeric(mk.id, errors="coerce").notna()].assign(market=lambda x: x.id.astype(int))
    p = p.merge(mk[["market", "end_date", "question"]], on="market").sort_values("end_date").reset_index(drop=True)
    p = p.drop_duplicates("end_date")
    # put every market on the 15-minute grid; missing markets become NaN gaps
    grid = pd.date_range(p.end_date.min(), p.end_date.max(), freq="15min")
    p = p.set_index("end_date").reindex(grid)
    P = p.filter(regex=r"^p\d+$").values.astype("float64")
    P[(p.n_window.fillna(0) < MIN_TRADES).values] = np.nan
    L = np.log(np.clip(P, 0.01, 0.99) / (1 - np.clip(P, 0.01, 0.99)))
    T = L.ravel()
    t_index = np.repeat(grid.values, M) + np.tile(np.arange(M) * 30, len(grid)).astype("timedelta64[s]") - np.timedelta64(15, "m")
    return p, T, t_index


def main():
    p, T, t_index = build()
    print(f"{p.market.notna().sum():,} markets on a grid of {len(p):,} slots "
          f"({p.index.min():%Y-%m-%d} to {p.index.max():%Y-%m-%d}); usable points {np.isfinite(T).mean():.1%}")
    t0 = time.time()
    mp = stumpy.stump(T, M)
    print(f"stumpy.stump on {len(T):,} points (m={M}): {time.time() - t0:.0f}s")
    P = mp[:, 0].astype(float)
    I = mp[:, 1].astype(int)
    ok = np.isfinite(P)
    start = pd.to_datetime(t_index[:len(P)])
    df = pd.DataFrame({"start": start, "profile": P, "nn": I}).loc[ok]
    df["hour"] = df.start.dt.hour
    df["aligned"] = (df.index % M) == 0                       # window = exactly one market

    thr = df.profile.quantile(0.99)
    top = df[df.profile >= thr]
    by_hour = pd.DataFrame({"all windows": df.hour.value_counts(normalize=True),
                            "top 1% anomalies": top.hour.value_counts(normalize=True)}).sort_index()
    by_hour["ratio"] = by_hour["top 1% anomalies"] / by_hour["all windows"]
    print("\nwhen the anomalous stretches happen (UTC hour; ratio > 1 = over-represented):")
    print(by_hour.round(3).to_string())

    # discords: non-overlapping top windows
    disc, taken = [], np.zeros(len(P), bool)
    for i in np.argsort(-np.where(ok, P, -np.inf)):
        if len(disc) == 10 or not np.isfinite(P[i]):
            break
        if taken[max(0, i - M):i + M].any():
            continue
        taken[i] = True
        slot = p.index[i // M]
        disc.append(dict(start=start[i], profile=P[i], market_end=slot,
                         question=p.question.iloc[i // M], trades_in_window=p.n_window.iloc[i // M]))
    disc = pd.DataFrame(disc)
    print("\ntop discords:")
    print(disc.to_string(index=False))

    order = np.argsort(np.where(ok, P, np.inf))[:5]
    print("\ntop motif pairs:", [(str(start[i]), str(start[I[i]]), round(P[i], 3)) for i in order])

    df.to_parquet("local_data/r04_btc_profile.parquet")
    disc.to_csv("local_data/r04_btc_discords.csv", index=False)
    by_hour.to_csv("local_data/r04_btc_by_hour.csv")
    np.save("local_data/r04_btc_T.npy", T)
    return p, T, mp, df, disc, by_hour


if __name__ == "__main__":
    main()
