# Saltare alle conclusioni: i salti di prezzo su Polymarket

Quando su Polymarket il prezzo fa un salto improvviso, quanta parte del salto è giustificata?
Il progetto prende ogni salto di prezzo in 766 milioni di trade su Polymarket (da novembre 2022
a maggio 2026) e lo confronta con il modo in cui il mercato si è poi risolto.

**Leggi il report: [report/REPORT.pdf](report/REPORT.pdf)** (anche in [Markdown](report/REPORT.md)).
I numeri sono congelati al tag `numeri-finali`.

## Risultati principali
Un salto di prezzo è uno slot di 30 minuti il cui prezzo medio (pesato per i dollari) dista
almeno 15 punti da quello dello slot precedente con trade, nella parte centrale della vita del
mercato (il primo 7% e l'ultimo 4,5% sono esclusi). L'overshoot è la parte del salto che l'esito
non ha giustificato, al netto dell'errore di calibrazione dei prezzi misurato su tutti gli slot.
- **Dopo un salto di prezzo il prezzo va oltre il dovuto, in media del 37,6% del salto**, in
  ogni categoria e in ogni anno dal 2023.
- **Conta soprattutto quanti trader fanno il salto.** Due salti su tre sono fatti da un solo
  trader: il loro overshoot è del 43%, ma l'eccesso viene quasi tutto restituito già dai trade
  successivi. I salti fatti da una folla (5 o più trader) hanno un overshoot del 14%, ma
  l'eccesso dura ore.
- **Il risultato non dipende da come si definisce un salto**: con slot di 5, 30 o 60 minuti e
  soglie di 10, 15 o 20 punti l'ordine tra i gruppi di trader non cambia mai. Vale anche a
  parità di soldi e nello sport e negli esport.
- **Salto per salto**, la parte restituita dai trade successivi ha due picchi: molti salti di un
  trader restano come sono, altri vengono annullati del tutto.
- **Scommettere contro i salti**: contro quelli di un trader singolo si perde a causa dello
  spread; contro quelli di una folla, o con almeno $200, resta un piccolo margine prima delle
  commissioni.
- Nei mercati crypto "up or down" compare lo stesso schema alla fine del minuto, ma scompare
  pochi secondi dopo.

## Come sono scelti i valori
I parametri della definizione di salto e i gruppi sono scelti con il metodo del gomito (regola
Kneedle, Satopää et al. 2011), cercando insieme quelli che dipendono l'uno dall'altro finché
nessun valore cambia. I valori statistici vengono dalla letteratura: 10 fasce di uguale ampiezza
per l'errore di calibrazione (Naeini, Cooper e Hauskrecht 2015), 1.000 ricampionamenti di mercati
interi per gli intervalli al 95% (Efron e Tibshirani 1993), la banda di Silverman (1986) per la
curva della restituzione. La tabella completa è nella sezione 3 del report.

## Contenuto
| Cartella | Contenuto |
|---|---|
| `report/` | `REPORT.pdf` e `REPORT.md`; i grafici in PNG (`plots/`) e in PDF vettoriale senza titolo (`plots_pdf/`) |
| `remote/` | Script di estrazione che girano accanto ai dati grezzi: raggruppano i trade per mercato, costruiscono gli slot di 30 minuti, trovano i salti di prezzo e scrivono tabelle compatte |
| `explore/` | Script di analisi che girano su quelle tabelle, la ricerca dei parametri e gli script dei grafici e del PDF |

Tutti i valori dei parametri sono in `explore/r02_persistence.py` (gli script di estrazione
riportano gli stessi valori).

| Sezione del report | Script |
|---|---|
| 1. Dati | `remote/s1_bucket.py` (raggruppa i trade), `s13_counts.py` (trade per mese e mercato), `explore/report_stats.py` |
| 2. Salti, trade successivi, errore di calibrazione | `remote/s2_events.py`, `s3_events.py` (slot, finestra di vita, salti, tutti gli slot per l'errore di calibrazione), `p7_extract.py` (mercato d'esempio); `explore/r02_persistence.py`, `r13_calibration.py` (curva dell'errore di calibrazione e confronti) |
| 3. Parametri | `remote/s12_grid.py`; `explore/elbow.py` (il ginocchio), `r12_joint.py`, `r12_params.py` |
| 4.1-4.2 Overshoot e gruppi di trader | `explore/r02_persistence.py`, `r03_robustness.py`, `r11_traders.py`, `r07_sports.py`, `r18_groups.py` (gruppi di trader per categoria e anno) |
| 4.3-4.4 Restituzione e direzione | `explore/r03_robustness.py`, `r11_traders.py` (`r11_traders.py curve` per la curva) |
| 4.5 Scommettere contro i salti | `remote/s6_micro.py`; `explore/r06_fade.py`, `r08_fade_robust.py` |
| 5. Mercati crypto | `explore/r05_keep_cx.py` (quali mercati), `remote/s1x_bucket.py`, `s4_paths.py cxmoves`; `explore/r05_updown.py` |
| Grafici e PDF | `explore/report_figures.py`, `report_style.py`, `report_pdf.py` |

## Come riprodurre
I dati grezzi non sono inclusi. Gli script si aspettano un dataset di Polymarket con
`data/trades_final.parquet` (una riga per esecuzione: orario, prezzo, importo, wallet di maker e
taker, token), `data/markets_final.parquet` (una riga per mercato: token, prezzi di esito, data
di fine, evento, `neg_risk`) e `data/market_tags.csv` (le etichette dei mercati).

1. **Estrazione** (`remote/`, Python 3.8+ con numpy, pandas, pyarrow; le uscite vanno in `tmp/`).
   In ordine: `s1_bucket.py` (raggruppa i trade in 32 bucket per mercato) e `s1x_bucket.py` (lo
   stesso per i mercati crypto up/down elencati in `tmp/keep_cx.txt`, scritto prima da
   `explore/r05_keep_cx.py`); `s12_grid.py events|cx` su ogni bucket (i dati della ricerca dei
   parametri), poi `r12_joint.py events|cx` accanto alla griglia (con `r02_persistence.py` ed
   `elbow.py`); quindi `s2_events.py`, `s3_events.py 1800|300|3600`, `s4_paths.py cxmoves`,
   `s6_micro.py`, `s13_counts.py` e `p7_extract.py <id del mercato>` per il mercato d'esempio. La
   docstring di ogni script ne descrive ingressi, uscite e uso.
2. **Analisi** (`explore/`, Python 3.10+ con numpy, pandas, scipy, matplotlib). Copiare le uscite
   dell'estrazione in `local_data/` (i nomi delle cartelle sono nella docstring di ogni script) ed
   eseguire dalla radice del repository, in ordine: `r02_persistence.py`, `r03_robustness.py`,
   `r06_fade.py`, `r08_fade_robust.py`, `r07_sports.py`, `r18_groups.py`, `r11_traders.py` e `r11_traders.py curve`,
   `r05_updown.py`, `r12_params.py`, `r13_calibration.py`, `report_stats.py`, `report_figures.py`
   (scrive i grafici). `report_pdf.py report/REPORT.md` crea il PDF (richiede i pacchetti
   `markdown` e `latex2mathml` e Microsoft Edge).

## Crediti
Tema dei grafici: [Rosé Pine Dawn for matplotlib](https://github.com/h4pZ/rose-pine-matplotlib)
(licenza MIT, vedi `explore/LICENSE-rose-pine.txt`).

**Lavori correlati:** Tsang & Yang, "Political Shocks and Price Discovery in Prediction Markets"
e "The Anatomy of Polymarket" (arXiv 2603.03152, 2603.03136); Akey, Vincent, Harvie &
Martineau, "Who Wins and Who Loses in Prediction Markets? Evidence from Polymarket" (CEPR DP
21615, 2026); Roll (1984).
