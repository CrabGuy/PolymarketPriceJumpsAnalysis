"""
Build tmp/sib_pairs.parquet for the server (remote/s8_wallets.py, pass 3): one row per
(big move, other market of the same event), from local_data/r03_big_moves_main.parquet and
the markets' event ids. Written to local_data/r05/sib_pairs.parquet, then uploaded.
Usage: python explore/r08_pairs.py
"""
import pandas as pd


def main():
    b = pd.read_parquet("local_data/r03_big_moves_main.parquet", columns=["market", "t_close"])
    mk = pd.read_parquet("local_data/markets_final.parquet", columns=["id", "event_id"])
    mk = mk[pd.to_numeric(mk.id, errors="coerce").notna()].assign(market=lambda x: x.id.astype(int))
    mk = mk.drop_duplicates("market")[["market", "event_id"]]
    n = mk.groupby("event_id").market.transform("size")
    mk = mk[n >= 2]
    p = b.merge(mk, on="market").merge(mk.rename(columns={"market": "sib"}), on="event_id")
    p = p[p.sib != p.market].rename(columns={"market": "mv_market"})[["mv_market", "t_close", "sib"]]
    p = p.astype({"mv_market": "int32", "t_close": "int64", "sib": "int32"})
    p.to_parquet("local_data/r05/sib_pairs.parquet", index=False)
    print(f"{len(p):,} pairs from {p[['mv_market', 't_close']].drop_duplicates().shape[0]:,} moves")


if __name__ == "__main__":
    main()
