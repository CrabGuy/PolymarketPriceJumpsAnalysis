# Jumping to Conclusions: Polymarket Price Jumps Analysis

When a Polymarket price jumps, how much of the jump is real? This project looks at every
sharp price jump in 766 million Polymarket trades (November 2022 to May 2026) and checks
each one against how the market finally resolved.

**Read the report: [report/REPORT.md](report/REPORT.md)**

## Main results
- **Big moves overshoot by about a third.** Judged by the final outcome, about two thirds of
  a sharp jump is justified; the rest is taken back later. This holds in every year and
  almost every category.
- **The number of traders behind a move matters most.** A jump made by a single trader goes
  about a third too far, and the next trades undo most of it within minutes. A jump made by
  four or more traders goes less than a fifth too far.
- **No easy money.** Once the bid-ask spread is paid, betting against big moves has no
  reliable edge.
- **Lone pushes happen where the order book is thin**, so that a few dollars can move the
  price.
- In races with several candidates, a crowd's move that the other candidates offset is right
  at once. Sports and esports prices are close to right by the next trades, and the crypto
  "up or down" markets show the same pattern within seconds.

## What's in here
| Folder | Contents |
|---|---|
| `report/` | `REPORT.md` (the full write-up: findings, method, parameters, glossary) and its plots |
| `remote/` | Extraction scripts that run next to the raw data: regroup trades by market, build 15-minute slots, find big moves, and write compact tables |
| `explore/` | Analysis scripts that run on those tables, one per finding, plus the figure scripts (`report_figures.py`, `report_style.py`) |

Section 8 of the report maps every finding to its scripts, and section 6 lists every
algorithm and parameter.

## Reproducing
The raw data is not included. The scripts expect a Polymarket dataset with
`data/trades_final.parquet` (one row per fill: time, price, size, maker and taker wallets,
token), `data/markets_final.parquet` (one row per market: tokens, outcome prices, end date,
event, `neg_risk`) and `data/market_tags.csv` (market tags).

1. **Extraction** (`remote/`, Python 3.8+ with numpy, pandas, pyarrow). In order:
   `s1_bucket.py` (regroup trades into 32 buckets by market; `s1u_bucket.py` and
   `s1x_bucket.py` do the same for the crypto up/down markets), `s2_events.py`,
   `s3_events.py 900|300|3600`, `s4_paths.py moves|cx|cxmoves`, `s6_micro.py`,
   `s7_events.py sports`, then `s8_wallets.py` (its input pairs come from
   `explore/r08_pairs.py`) and `p7_extract.py <market id>` for the example market. Each script's
   docstring gives its inputs, outputs and usage. Outputs go to `tmp/`.
2. **Analysis** (`explore/`, Python 3.10+ with numpy, pandas, scipy, matplotlib, stumpy).
   Copy the extraction outputs into `local_data/` (folder names are in each script's
   docstring), then run from the repository root, in order: `r02_persistence.py`,
   `r03_robustness.py`, `r04_types.py`, `r05_event_markets.py`, `r08_pairs.py` and
   `r07_siblings.py`, `r06_fade.py`, `r08_fade_robust.py`, `r06_concentration.py`,
   `r07_sports.py`, `r05_updown.py`, `r04_motifs.py`, `r04_btc_chain.py`, `r05_crypto_mp.py`,
   and finally `report_stats.py` and `report_figures.py` (writes `report/plots/`).

## Credits
Plot theme: [Rosé Pine Dawn for matplotlib](https://github.com/h4pZ/rose-pine-matplotlib) (MIT license, see `explore/LICENSE-rose-pine.txt`).
Related work is listed at the end of the report.
