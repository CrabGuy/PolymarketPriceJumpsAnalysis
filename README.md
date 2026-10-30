# Jumping to Conclusions: Polymarket Price Jumps Analysis

When a Polymarket price jumps, how much of the jump is real? This project looks at every
sharp price jump in 766 million Polymarket trades (November 2022 to May 2026) and checks
each one against how the market finally resolved.

**Read the report: [report/REPORT.pdf](report/REPORT.pdf)** (also as [Markdown](report/REPORT.md))

## Main results
A price jump here is a 30-minute average price at least 13 points away from the previous
one, in the middle of a market's life (the first and last 5% are left out). These values
and every other parameter were chosen with the elbow method (section 2 of the report), and
every quantity is defined by a formula (section 6.1).
- **Price jumps overshoot by over a third.** Judged by the final outcome, just under two
  thirds of a jump is justified; the rest is taken back later. This holds in every year and
  every category.
- **The number of traders behind a jump matters most.** A jump made by a single trader goes
  about 40% too far, and the next trades undo most of it within minutes. A jump made by four
  or more traders goes less than a fifth too far, and that part lingers for hours.
- **Lone pushes happen where the order book is thin**, so that a few dollars can move the
  price.
- **Betting against jumps:** after the bid-ask spread, betting against lone pushes loses
  money; betting against crowd jumps and jumps with over $1,000 behind them leaves a small
  edge before fees.
- In races with several candidates, a crowd's jump that the other candidates offset is right
  at once. Sports and esports show the same pattern as other markets, and the crypto "up or
  down" markets show it within seconds.
- Tentatively: what the next trades do to a jump tells a sensible jump from noise better than
  anything known at the moment of the jump.

## What's in here
| Folder | Contents |
|---|---|
| `report/` | `REPORT.pdf` and `REPORT.md` (the full write-up: findings, method, parameters, glossary) and its plots |
| `remote/` | Extraction scripts that run next to the raw data: regroup trades by market, build 30-minute slots, find price jumps, and write compact tables |
| `explore/` | Analysis scripts that run on those tables, one per finding, plus the figure scripts (`report_figures.py`, `report_style.py`) |

Section 8 of the report maps every finding to its scripts, and section 6 gives every
formula and parameter.

## Reproducing
The raw data is not included. The scripts expect a Polymarket dataset with
`data/trades_final.parquet` (one row per fill: time, price, size, maker and taker wallets,
token), `data/markets_final.parquet` (one row per market: tokens, outcome prices, end date,
event, `neg_risk`) and `data/market_tags.csv` (market tags).

1. **Extraction** (`remote/`, Python 3.8+ with numpy, pandas, pyarrow). In order:
   `s1_bucket.py` (regroup trades into 32 buckets by market; `s1u_bucket.py` and
   `s1x_bucket.py` do the same for the crypto up/down markets), `s2_events.py`,
   `s3_events.py 1800|300|3600`, `s4_paths.py moves|cx|cxmoves`, `s6_micro.py`, then
   `s8_wallets.py` (its input pairs come from `explore/r08_pairs.py`) and
   `p7_extract.py <market id>` for the example market. `s7_events.py basis` and
   `s9_window.py` feed the definition checks only, and `s11_elbow.py`
   the elbow checks of the parameters. Each script's
   docstring gives its inputs, outputs and usage. Outputs go to `tmp/`.
2. **Analysis** (`explore/`, Python 3.10+ with numpy, pandas, scipy, matplotlib, stumpy).
   Copy the extraction outputs into `local_data/` (folder names are in each script's
   docstring), then run from the repository root, in order: `r02_persistence.py`,
   `r03_robustness.py`, `r04_types.py`, `r05_event_markets.py`, `r08_pairs.py` and
   `r07_siblings.py`, `r06_fade.py`, `r08_fade_robust.py`, `r06_concentration.py`,
   `r07_sports.py`, `r05_updown.py`, `r04_motifs.py`, `r04_btc_chain.py`, `r05_crypto_mp.py`,
   `r10_information.py`, `r11_traders.py`, and finally `report_stats.py` and `report_figures.py` (writes
   `report/plots/`). `r11_elbow.py` draws the elbow curves of every parameter; the `r09_*.py` scripts
   are earlier checks of jump thresholds and start/end cuts.

## Credits
Plot theme: [Rosé Pine Dawn for matplotlib](https://github.com/h4pZ/rose-pine-matplotlib) (MIT license, see `explore/LICENSE-rose-pine.txt`).
Related work is listed at the end of the report.
