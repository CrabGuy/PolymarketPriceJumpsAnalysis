"""
Round 8, part 2: betting against big moves, with returns that a few huge wins can't drive.

Returns per $1 are heavy-tailed: betting against a move to 6% buys at 6 cents and can win
about 15 times the stake. So the mean return is reported next to a trimmed mean: returns
clipped at the 1st and 99th percentile of all bets (the same cut points for every group).
Input local_data/r06/r06_fade_moves.parquet (explore/r06_fade.py: taker entry = first 5
trades on the bettor's side; n_taker = return per $ net of the usual mispricing).
95% intervals from resampling markets (300). Output local_data/r08_fade_robust.csv.
Usage: python explore/r08_fade_robust.py
"""
import numpy as np
import pandas as pd


def boot(x, col, n=300, seed=0):
    g = x.groupby("market")[col].agg(["sum", "size"])
    a, c = g["sum"].values, g["size"].values
    i = np.random.default_rng(seed).integers(0, len(g), size=(n, len(g)))
    r = a[i].sum(1) / c[i].sum(1)
    return np.percentile(r, [2.5, 97.5])


def main():
    t = pd.read_parquet("local_data/r06/r06_fade_moves.parquet")
    lo_c, hi_c = t.n_taker.quantile([0.01, 0.99])
    t["trim"] = t.n_taker.clip(lo_c, hi_c)
    t["money"] = pd.cut(t.usd, [0, 100, 1000, np.inf], labels=["<$100", "$100-1k", ">$1k"]).astype(str)
    rows = []
    for split, col in (("takers", "tg"), ("money in bar", "money")):
        for k, x in list(t.groupby(col)) + [("all", t)]:
            m_lo, m_hi = boot(x, "n_taker")
            t_lo, t_hi = boot(x, "trim")
            rows.append({"split": split, "group": k, "moves": len(x), "mean": x.n_taker.mean(), "mean lo": m_lo,
                         "mean hi": m_hi, "trimmed": x.trim.mean(), "trimmed lo": t_lo, "trimmed hi": t_hi,
                         "median": x.n_taker.median(), "win rate": (x.n_taker > 0).mean(),
                         "spread (cents)": x.spread.median() * 100})
    res = pd.DataFrame(rows)
    print(f"clip points: {lo_c:.2f} / {hi_c:.2f} per $")
    print(res.round(3).to_string(index=False))
    res.to_csv("local_data/r08_fade_robust.csv", index=False)


if __name__ == "__main__":
    main()
