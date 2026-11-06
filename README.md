# Saltare alle conclusioni: i price jump su Polymarket

Quando su Polymarket il prezzo fa un salto improvviso, quanto di quel salto è giustificato?
Il progetto prende ogni price jump in 766 milioni di trade su Polymarket (da novembre 2022 a
maggio 2026) e lo confronta con il modo in cui il mercato si è poi risolto.

**Leggi il report: [report/REPORT.pdf](report/REPORT.pdf)** (anche in [Markdown](report/REPORT.md))

## Risultati principali
Un price jump è uno slot di 20 minuti il cui prezzo medio (pesato per i dollari) dista almeno
15 punti da quello dello slot precedente con trade, nella parte centrale della vita del
mercato (il primo 6,5% e l'ultimo 5,5% sono esclusi). Questi valori, e tutti gli altri
parametri, sono stati scelti con il metodo del gomito, cercando insieme i parametri che
dipendono l'uno dall'altro (sezione 3 del report). I mercati crypto "up or down" hanno valori
propri.
- **Dopo un price jump il prezzo va troppo lontano, in media del 36% del jump**, in ogni
  categoria e in ogni anno.
- **Conta soprattutto quanti trader fanno il jump.** Due jump su tre sono fatti da un solo
  trader: vanno troppo lontano del 43%, ma l'eccesso viene quasi tutto restituito già dai trade
  successivi. I jump fatti da una folla (4 o più trader) vanno troppo lontano del 17%, ma
  l'eccesso dura ore.
- **Il risultato non dipende da come si definisce un jump**: con slot di 5, 20 o 60 minuti e
  soglie di 10, 15 o 20 punti l'ordine tra i gruppi di trader non cambia mai. Vale anche a
  parità di soldi, a parità di tutto il resto, e nello sport e negli esport.
- **Jump per jump**, la parte restituita dai trade successivi ha due picchi: molti jump di un
  trader restano come sono, altri vengono annullati del tutto.
- **Scommettere contro i jump**: contro quelli di un trader singolo si perde per colpa dello
  spread; contro quelli di una folla, o con almeno $100, resta un piccolo margine prima delle
  commissioni.
- Nei mercati crypto "up or down" compare lo stesso schema alla fine dei 30 secondi, ma sparisce
  pochi secondi dopo.

## Contenuto
| Cartella | Contenuto |
|---|---|
| `report/` | `REPORT.pdf` e `REPORT.md` (il report: contesto, definizioni con formule ed esempi, parametri, risultati) e i suoi grafici |
| `remote/` | Script di estrazione che girano accanto ai dati grezzi: raggruppano i trade per mercato, costruiscono gli slot di 20 minuti, trovano i price jump e scrivono tabelle compatte |
| `explore/` | Script di analisi che girano su quelle tabelle, uno per risultato, la ricerca dei parametri (`elbow.py`, `r12_*.py`) e gli script dei grafici e del PDF (`report_figures.py`, `report_style.py`, `report_pdf.py`) |

Tutti i valori dei parametri sono in `explore/r02_persistence.py` (gli script di estrazione
riportano gli stessi valori).

| Sezione del report | Script |
|---|---|
| Estrazione | `remote/s1_bucket.py` (raggruppa i trade), `s2_events.py` / `s3_events.py` (slot, finestra di vita e jump), `s4_paths.py` (percorsi dei prezzi, jump crypto), `s6_micro.py` (struttura del mercato), `s7_events.py` (medie semplici), `s8_wallets.py` (wallet), `p7_extract.py` (mercato di esempio) |
| 3. Parametri | `remote/s12_grid.py`; `explore/elbow.py` (il ginocchio), `r12_joint.py`, `r12_params.py`, `r12_f9.py` |
| 4.1-4.2 Overshoot e gruppi di trader | `explore/r02_persistence.py`, `r03_robustness.py`, `r04_types.py`, `r07_basis.py`, `r05_event_markets.py` (a parità di tutto il resto), `r07_sports.py` (sport ed esport) |
| 4.3-4.4 Restituzione e accuratezza | `explore/r03_robustness.py` (andamento nel tempo), `r11_traders.py` (`r11_traders.py curve` per la curva della restituzione) |
| 4.5 Scommettere contro i jump | `explore/r06_fade.py`, `r08_fade_robust.py` |
| 5. Mercati crypto | `explore/r05_updown.py` |
| Grafici e PDF | `explore/report_stats.py`, `report_figures.py`, `report_style.py`, `report_pdf.py` |

Gli altri script di `explore/` (`r07_siblings.py`, `r08_pairs.py`, `r06_concentration.py`,
`r04_motifs.py`, `r04_btc_chain.py`, `r05_crypto_mp.py`, `r10_information.py`) coprono analisi
fatte durante il progetto ma non incluse in questo report: jump tra candidati dello stesso
evento, struttura del mercato, pattern ricorrenti con il matrix profile, informazione portata
da un jump.

## Come riprodurre
I dati grezzi non sono inclusi. Gli script si aspettano un dataset di Polymarket con
`data/trades_final.parquet` (una riga per esecuzione: orario, prezzo, importo, wallet di maker e
taker, token), `data/markets_final.parquet` (una riga per mercato: token, prezzi di esito, data
di fine, evento, `neg_risk`) e `data/market_tags.csv` (le etichette dei mercati).

1. **Estrazione** (`remote/`, Python 3.8+ con numpy, pandas, pyarrow). In ordine:
   `s1_bucket.py` (raggruppa i trade in 32 bucket per mercato; `s1u_bucket.py` e
   `s1x_bucket.py` fanno lo stesso per i mercati crypto up/down); `s12_grid.py events|cx` su
   ogni bucket (i dati della ricerca dei parametri); poi `s2_events.py`,
   `s3_events.py 1200|300|3600`, `s6_micro.py`, `s4_paths.py finemoves|cxmoves|cxfine`,
   `s7_events.py basis`, `s8_wallets.py` (le coppie in ingresso vengono da
   `explore/r08_pairs.py`) e `p7_extract.py <id del mercato>` per il mercato di esempio. La
   docstring di ogni script ne descrive ingressi, uscite e uso. Le uscite vanno in `tmp/`.
2. **Analisi** (`explore/`, Python 3.10+ con numpy, pandas, scipy, matplotlib, stumpy).
   Copiare le uscite dell'estrazione in `local_data/` (i nomi delle cartelle sono nella
   docstring di ogni script) ed eseguire dalla radice del repository. La ricerca dei
   parametri: `r12_joint.py events` e `r12_joint.py cx` (definizione del jump, accanto alle
   uscite della griglia), poi, dopo i risultati, `r12_params.py`, `r12_f9.py A` e
   `r12_f9.py B` (da ripetere finché nessun valore si sposta). I risultati, in ordine:
   `r02_persistence.py`, `r03_robustness.py`, `r04_types.py`, `r05_event_markets.py`,
   `r08_pairs.py` e `r07_siblings.py`, `r06_fade.py`, `r08_fade_robust.py`,
   `r06_concentration.py`, `r07_sports.py`, `r05_updown.py`, `r04_motifs.py`,
   `r04_btc_chain.py`, `r05_crypto_mp.py`, `r05_mp_explained.py`, `r07_basis.py`,
   `r10_information.py`, `r11_traders.py` e `r11_traders.py curve`, infine `report_stats.py`
   e `report_figures.py` (scrive i grafici). `report_pdf.py report/REPORT.md` crea il PDF
   (richiede i pacchetti `markdown` e `latex2mathml` e Microsoft Edge).

## Crediti
Tema dei grafici: [Rosé Pine Dawn for matplotlib](https://github.com/h4pZ/rose-pine-matplotlib)
(licenza MIT, vedi `explore/LICENSE-rose-pine.txt`).

**Lavori correlati:** Tsang & Yang, "Political Shocks and Price Discovery in Prediction Markets"
e "The Anatomy of Polymarket" (arXiv 2603.03152, 2603.03136); Akey, Vincent, Harvie &
Martineau, "Who Wins and Who Loses in Prediction Markets? Evidence from Polymarket" (CEPR DP
21615, 2026); Roll (1984).
