"""
The report's figures, in the Rose Pine Dawn theme (explore/report_style.py) with one fixed colour
per trader group, Italian labels and decimal commas. Each figure is written twice:
report/plots/<name>.png (with its title, for report/REPORT.md) and report/plots_pdf/<name>.pdf
(vector, without the main title, for the thesis, where the caption replaces it). Every figure is
drawn from tables the analysis scripts saved; nothing here changes a result.

  ex1_example-market   a real market with its price jumps                         section 2
  m_calibration        the calibration error b(p) by price bin, with 95% ranges     section 2
  bg_pipeline          from trades to slots, jumps and next trades, and measures    section 2
  t_dataset            a few rows of the trades and markets tables                  section 1
  d_stats              trades and markets per month and per category                section 1
  m_definition         the elbow curves of the jump definition (event markets)      section 3
  m_params             the elbow curves of the other parameters                     section 3
  m_crypto             the elbow curves of the jump definition (crypto markets)     section 5
  f1_hero              price right after a jump vs how often YES won                section 4.1
  f2_trader-counts     jumps and overshoot by exact number of traders               section 4.2
  f2_robustness        the same order for every slot length and threshold           section 4.2
  f3_giveback-curve    how much of a lone trader's jump the next trades give back   section 4.3
  f3_decay             the overshoot over time, by trader group                     section 4.3
  f2_accuracy          how often jumps point toward the outcome                     section 4.4
  f5_fade              betting against price jumps                                  section 4.5

Usage: python explore/report_figures.py [name ...]   (no names = all)
"""
import glob
import locale
import os
import sys

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, "explore")
from report_style import (BASE, MUTED, SUBTLE, TEXT, HL_MED, LOVE, GOLD, ROSE, PINE, FOAM, IRIS,  # noqa: E402
                          TG, TG_LABEL, UP, DOWN)
from r02_persistence import (BAR, BINS, CROWD, EDGE, FEW, K_CROWD, LIFE_CUT_END,  # noqa: E402
                             LIFE_CUT_START, MONEY_X, TG_LABELS, boot_share, category)

locale.setlocale(locale.LC_NUMERIC, "it_IT.UTF-8")
plt.rcParams["axes.formatter.use_locale"] = True
plt.rcParams["pdf.fonttype"] = 42          # text stays text in the PDF files
SLOT = BAR // 60      # slot length in minutes, for labels
OUT, OUT_PDF = "report/plots/", "report/plots_pdf/"
LD = "local_data/"
TGS = tuple(TG_LABELS)
EXAMPLE = 523331      # "Will Apple launch another iPhone on February 19?" (2025)
CAT_IT = {"crypto": "crypto", "culture": "cultura", "economy": "economia", "elections": "elezioni",
          "esports": "esport", "geopolitics": "geopolitica", "other": "altro", "politics": "politica",
          "sports": "sport"}


def it(s):
    """English number format -> Italian (1,234.5 -> 1.234,5)."""
    return s.translate(str.maketrans(",.", ".,"))


def it_counts(labels):
    return [str(k).replace("over", "oltre") for k in labels]


def save(fig, name, title_ax=None):
    """PNG with the title (report); vector PDF without the main title (thesis)."""
    fig.tight_layout()
    fig.savefig(OUT + name + ".png")
    if fig._suptitle is not None:
        fig._suptitle.set_text("")
    for ax in ([title_ax] if title_ax is not None else fig.axes if len(fig.axes) == 1 else []):
        ax.set_title("")
    fig.tight_layout()
    fig.savefig(OUT_PDF + name + ".pdf")
    plt.close(fig)


def pct(ax, axis="y", fmt="{:.0f}%"):
    f = plt.FuncFormatter(lambda v, _: it(fmt.format(v)))
    (ax.yaxis if axis == "y" else ax.xaxis).set_major_formatter(f)


def bars_tg(ax, x, vals, lo=None, hi=None, width=0.25, labels=True):
    for k, tg in enumerate(TGS):
        xs = np.asarray(x) + (k - 1) * width
        v = np.asarray(vals[tg]) * 100
        ax.bar(xs, v, width * 0.92, color=TG[tg], label=TG_LABEL[tg] if labels else None)
        if lo is not None:
            ax.errorbar(xs, v, yerr=[v - np.asarray(lo[tg]) * 100, np.asarray(hi[tg]) * 100 - v],
                        fmt="none", ecolor=TEXT, lw=1)


# ---------------------------------------------------------------- data and method

def example_data():
    # full trade history of the example market (remote/p7_extract.py)
    s = pd.read_parquet(LD + f"r07/example_{EXAMPLE}.parquet").rename(columns={"usd": "usd_amount"})
    s["yes"] = s.yes * 100
    s["t"] = pd.to_datetime(s.ts, unit="s")
    b = pd.read_parquet(LD + "r03_big_moves_main.parquet", filters=[("market", "==", EXAMPLE)])
    b["t"] = pd.to_datetime(b.t_close, unit="s")
    return s, b


def date_axis(ax):
    loc = mdates.AutoDateLocator(minticks=4, maxticks=7)
    ax.xaxis.set_major_locator(loc)
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(loc))


def example_bars(s):
    # the slots the price jumps are found on (as remote/s2_events.py): dollar-weighted average
    # price of the slot's trades, stamped at the slot's end
    s = s.assign(bar=s.ts // BAR, pv=s.yes * s.usd_amount)
    g = s.groupby("bar").agg(pv=("pv", "sum"), usd=("usd_amount", "sum"), last=("yes", "last"))
    g["vwap"] = (g.pv / g.usd.where(g.usd > 0)).fillna(g["last"])
    g["t"] = pd.to_datetime((g.index + 1) * BAR, unit="s")
    return g.reset_index(drop=True)


NEWS = [("2025-02-13 17:00", "13 feb: Tim Cook annuncia\n\"il nuovo membro\ndella famiglia\""),
        ("2025-02-17 12:00", "16-17 feb: indiscrezioni\nsul nuovo nome\ndel telefono"),
        ("2025-02-19 16:00", "19 feb: Apple\npresenta\nl'iPhone 16e")]


def ex1_example():
    s, b = example_data()
    bars = example_bars(s)
    fig, ax = plt.subplots(figsize=(9.5, 4.6))
    ax.plot(bars.t, bars.vwap, color=HL_MED, lw=0.8, zorder=1)
    ax.scatter(bars.t, bars.vwap, s=14, color=IRIS, lw=0, zorder=2,
               label=f"prezzo medio di ogni slot di {SLOT} minuti con trade")
    bars["t0"], bars["v0"] = bars.t.shift(), bars.vwap.shift()
    for r in b.merge(bars[["t", "t0", "v0"]], on="t").itertuples():
        ax.plot([r.t0, r.t], [r.v0, r.p_close * 100], color=LOVE, lw=2.4, zorder=3)
        ax.scatter([r.t], [r.p_close * 100], s=30, color=LOVE, lw=0, zorder=4)
    ax.plot([], [], color=LOVE, lw=2.4, marker="o", ms=5, label="salti di prezzo")
    inside = bars["last"].between(EDGE * 100, 100 - EDGE * 100)
    t0, t1 = bars.t.iloc[0], bars.t[inside].iloc[-1]
    a0, a1 = t0 + (t1 - t0) * LIFE_CUT_START, t1 - (t1 - t0) * LIFE_CUT_END
    for a, z in ((t0 - pd.Timedelta(hours=3), a0), (a1, bars.t.iloc[-1] + pd.Timedelta(hours=3))):
        ax.axvspan(a, z, color=HL_MED, alpha=0.6, lw=0, zorder=0)
    ax.fill_between([], [], color=HL_MED, alpha=0.6,
                    label=it(f"parti escluse: primo {LIFE_CUT_START * 100:g}% e ultimo {LIFE_CUT_END * 100:g}% della vita del mercato"))
    for t, txt in NEWS:
        t = pd.Timestamp(t)
        ax.axvline(t, color=SUBTLE, lw=0.8, ls=":", zorder=0)
        ax.text(t + pd.Timedelta(hours=1.5), 97, txt, va="top", fontsize=8, color=SUBTLE)
    ax.set_xlim(t0 - pd.Timedelta(hours=3), bars.t.iloc[-1] + pd.Timedelta(hours=3))
    ax.set_ylim(0, 100)
    pct(ax)
    date_axis(ax)
    ax.legend(loc="lower right", fontsize=8.5)
    ax.set_ylabel("prezzo di YES")
    ax.set_title(f"\"Will Apple launch another iPhone on February 19?\" (2025): {len(b)} salti di prezzo, esito YES",
                 fontsize=11)
    save(fig, "ex1_example-market")


def m_calibration():
    """b(p): mean (outcome - price) per price bin over every slot, all event markets (with 95% range),
    and per category (explore/r13_calibration.py curve)."""
    c = pd.read_csv(LD + "r13_curve.csv")
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4.4), sharey=True)
    a = c[c.group == "tutti"]
    x = a["mean price"] * 100
    a1.axhline(0, color=SUBTLE, lw=1)
    a1.errorbar(x, a.b * 100, yerr=[(a.b - a.lo) * 100, (a.hi - a.b) * 100], fmt="o-", color=IRIS, ecolor=TEXT,
                lw=2, ms=6, capsize=3)
    for e in BINS[1:-1]:
        a1.axvline(e * 100, color=HL_MED, lw=0.6, zorder=0)
    a1.set_title("Tutti i mercati su eventi (intervalli di confidenza al 95%)", fontsize=10.5)
    cols = dict(zip(sorted(c.group.unique().tolist()), [IRIS, GOLD, ROSE, PINE, FOAM, LOVE, MUTED, SUBTLE, TEXT, HL_MED]))
    a2.axhline(0, color=SUBTLE, lw=1)
    for g, d in c[c.group != "tutti"].groupby("group"):
        a2.plot(d["mean price"] * 100, d.b * 100, "o-", ms=3.5, lw=1.4, color=cols[g], label=CAT_IT.get(g, g))
    a2.legend(fontsize=8, ncol=5, loc="upper center", bbox_to_anchor=(0.5, -0.2))
    a2.set_title("Per categoria (il b(p) usato nei calcoli)", fontsize=10.5)
    for ax in (a1, a2):
        ax.set_xlim(0, 100)
        pct(ax, "x")
        pct(ax, "y", "{:.0f}")
        ax.set_xlabel("prezzo medio dello slot (fasce di 10 punti)")
    a1.set_ylabel("errore di calibrazione b(p), punti\n(esito − prezzo, media sugli slot)")
    fig.suptitle("L'errore di calibrazione: in ogni fascia di prezzo YES vince un po' meno di quanto dice il prezzo",
                 fontweight="bold", color=TEXT, fontsize=11.5)
    save(fig, "m_calibration")


def bg_pipeline():
    big = pd.read_parquet(LD + "r03_big_moves_main.parquet", columns=["market", "entry_vwap"])
    slots = sum(pd.read_parquet(f, columns=["market"]).shape[0] for f in glob.glob(LD + f"r03_events/{BAR}/r*.parquet"))
    steps = [("trade\n766 milioni\n(un'esecuzione per riga:\norario, prezzo, $, wallet)", MUTED),
             (f"slot di {SLOT} minuti\nper mercato\n" + it(f"{slots / 1e6:.1f}") +
              " milioni con trade\n(prezzo medio pesato per i $,\n$ e trader diversi)", IRIS),
             (it(f"salti di prezzo\n≥ 15 punti tra due slot\n{len(big):,} in {big.market.nunique():,} mercati\n"
                 f"+ trade successivi\n(5 trade entro 45 min)"), LOVE),
             ("misure\novershoot (con b(p)),\nrestituzione, direzione,\nscommesse contro i salti", PINE)]
    fig, ax = plt.subplots(figsize=(11, 2.3))
    ax.set_axis_off()
    w, gap = 2.3, 0.45
    for i, (txt, c) in enumerate(steps):
        x0 = i * (w + gap)
        ax.add_patch(plt.Rectangle((x0, 0), w, 1, facecolor=BASE, edgecolor=c, lw=2))
        ax.text(x0 + w / 2, 0.5, txt, ha="center", va="center", fontsize=9, color=TEXT)
        if i < len(steps) - 1:
            ax.annotate("", xy=(x0 + w + gap - 0.04, 0.5), xytext=(x0 + w + 0.04, 0.5),
                        arrowprops=dict(arrowstyle="->", color=SUBTLE, lw=1.4))
    ax.text(w + gap + w / 2, -0.06, "tutti gli slot → errore di calibrazione b(p)", ha="center", va="top",
            fontsize=8.5, color=SUBTLE)
    ax.set_xlim(-0.05, len(steps) * (w + gap) - gap + 0.05)
    ax.set_ylim(-0.25, 1.05)
    ax.set_title("Dai trade alle misure", fontsize=11)
    save(fig, "bg_pipeline")


def short(x, n=6):
    x = str(x)
    return x if len(x) <= 2 * n + 1 else x[:n] + "…" + x[-4:]


def t_dataset():
    """A few rows of the two tables (a public sample of trades; the markets file), as a picture."""
    s = pd.read_parquet(LD + "sample_trades.parquet")      # 500,000 trades of trades_final.parquet
    s = s[s.market_id == s.market_id.iloc[1000]].iloc[:4]
    tr = pd.DataFrame({"timestamp": pd.to_datetime(s.timestamp, unit="s").dt.strftime("%Y-%m-%d %H:%M:%S"),
                       "market_id": s.market_id, "maker": s.maker.map(short), "taker": s.taker.map(short),
                       "taker_direction": s.taker_direction, "nonusdc_side": s.nonusdc_side,
                       "price": s.price.map(lambda v: it(f"{v:.3f}")), "usd_amount": s.usd_amount.map(lambda v: it(f"{v:,.2f}")),
                       "transaction_hash": s.transaction_hash.map(short)})
    mk = pd.read_parquet(LD + "markets_final.parquet")
    mk = mk[mk.id.astype(str).isin([str(EXAMPLE), str(s.market_id.iloc[0])])].head(2)
    mt = pd.DataFrame({"id": mk.id, "question": mk.question.str.slice(0, 48),
                       "answer1 / 2": mk.answer1 + " / " + mk.answer2,
                       "outcome_prices": mk.outcome_prices.map(lambda v: "[" + ", ".join(
                           it(f"{float(z.strip(' ' + chr(39))):.4f}") for z in v.strip("[]").split(",")) + "]"),
                       "created_at": mk.created_at.dt.strftime("%Y-%m-%d"), "end_date": mk.end_date.dt.strftime("%Y-%m-%d"),
                       "volume ($)": mk.volume.map(lambda v: it(f"{v:,.0f}")), "neg_risk": mk.neg_risk})
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(13, 3.6), gridspec_kw={"height_ratios": [1.25, 1]})
    for ax, d, title in ((a1, tr, "trades_final.parquet (una riga per esecuzione; 17 colonne, qui 9)"),
                         (a2, mt, "markets_final.parquet (una riga per mercato; 20 colonne, qui 8)")):
        ax.set_axis_off()
        tb = ax.table(cellText=d.astype(str).values, colLabels=list(d.columns), loc="center", cellLoc="left")
        tb.auto_set_font_size(False)
        tb.set_fontsize(7.5)
        tb.auto_set_column_width(list(range(d.shape[1])))
        for (r, _), cell in tb.get_celld().items():
            cell.set_edgecolor(HL_MED)
            cell.set_facecolor(HL_MED if r == 0 else BASE)
        ax.set_title(title, fontsize=9.5, loc="left", fontweight="normal", color=TEXT)
    fig.suptitle("Il dataset: alcune righe d'esempio (wallet e hash abbreviati)", fontweight="bold", color=TEXT, fontsize=11)
    fig.tight_layout()
    fig.savefig(OUT + "t_dataset.png")
    fig._suptitle.set_text("")
    fig.savefig(OUT_PDF + "t_dataset.pdf")
    plt.close(fig)


def d_stats():
    """Trades per month (event and crypto up/down markets) and trades and markets per category."""
    c = pd.concat([pd.read_parquet(f).assign(src="crypto" if os.path.basename(f).startswith("cx") else "eventi")
                   for f in glob.glob(LD + "fin/counts/*.parquet")], ignore_index=True)
    tags = pd.read_csv(LD + "market_tags.csv", dtype=str)
    cats = pd.Series(category(tags.tags).values, index=tags.market_id.astype(int).values)
    c["cat"] = c.market.map(cats[~cats.index.duplicated()]).fillna("other").map(CAT_IT)
    c.loc[c.src == "crypto", "cat"] = "crypto up/down"
    m = c.groupby(["month", "src"]).trades.sum().unstack().fillna(0) / 1e6
    k = c.groupby("cat").agg(trades=("trades", "sum"), markets=("market", "nunique")).sort_values("trades")
    print(f"trades {c.trades.sum():,} in {c.market.nunique():,} markets; by source "
          f"{c.groupby('src').trades.sum().to_dict()}; months {m.index.min()} to {m.index.max()}")
    print(k.to_string())
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.3), gridspec_kw={"width_ratios": [1.6, 1]})
    x = np.arange(len(m))
    a1.bar(x, m.get("eventi", 0), color=IRIS, label="mercati su eventi")
    a1.bar(x, m.get("crypto", 0), bottom=m.get("eventi", 0), color=GOLD, label="mercati crypto up/down")
    step = max(1, len(m) // 10)
    a1.set_xticks(x[::step], [s[2:4] + "/" + s[5:] for s in m.index[::step]], fontsize=8)
    a1.set_ylabel("trade al mese (milioni)")
    a1.set_xlabel("mese (aa/mm)")
    a1.legend(fontsize=8.5, loc="upper left")
    a1.set_title("Trade per mese", fontsize=10.5)
    y = np.arange(len(k))
    a2.barh(y, k.trades / 1e6, color=[GOLD if i == "crypto up/down" else IRIS for i in k.index], height=0.65)
    for i, (tv, mv) in enumerate(zip(k.trades, k.markets)):
        a2.text(tv / 1e6 + 3, i, it(f"{mv:,} mercati"), va="center", fontsize=8, color=SUBTLE)
    a2.set_yticks(y, k.index, fontsize=9)
    a2.set_xlim(0, k.trades.max() / 1e6 * 1.45)
    a2.set_xlabel("trade (milioni)")
    a2.grid(axis="y", visible=False)
    a2.set_title("Trade e mercati per categoria", fontsize=10.5)
    fig.suptitle(it(f"I mercati analizzati: {c.trades.sum() / 1e6:,.0f} milioni di trade (gli altri mercati "
                    "ricorrenti up/down non sono studiati)"), fontweight="bold", color=TEXT, fontsize=11.5)
    save(fig, "d_stats")


# ---------------------------------------------------------------- elbow curves

KIND_TEXT = {"knee": "ginocchio = {}", "flat": "piatta (nessun effetto): {}", "none": "nessun ginocchio: {}",
             "peak": "picco (nessun ginocchio): {}", "valley": "punto più basso = {}",
             "knee before the valley": "ginocchio = {} (prima che la curva risalga)",
             "knee before the peak": "ginocchio = {} (prima che la curva scenda)"}


def elbow_panel(ax, x, y, k, title, xlabel, ylabel, ypct=False, logx=False, kind="knee", used=None, unit=""):
    """One parameter's curve with the value used, marked by a circle and a line; a curve without a
    knee says so, with the value kept (`used`: a number, or "dropped")."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    if used == "dropped":
        label, k = KIND_TEXT[kind].format("parametro eliminato"), None
    elif kind.startswith("knee") or kind == "valley":
        label = KIND_TEXT[kind].format(f"{k:g}{unit}")
    else:
        label = KIND_TEXT[kind].format(f"{k:g}{unit} mantenuto")
    ax.plot(x, y, "-", color=IRIS, lw=2)
    ax.plot(x, y, "o", color=IRIS, ms=3.2)
    if k is not None:
        ky = y[np.argmin(np.abs(x - k))]
        ax.plot([k], [ky], "o", ms=11, mfc="none", mec=ROSE if kind.startswith("knee") or kind == "valley" else MUTED, mew=2.2)
        ax.axvline(k, color=TEXT, lw=1, ls="--")
    rising = y[-1] > y[0]
    ty, va = (0.5, "center") if kind in ("flat", "none", "peak") else (0.05, "bottom") if rising else (0.95, "top")
    ax.text(0.97, ty, it(label), transform=ax.transAxes, ha="right", va=va, fontsize=8.5, color=TEXT,
            bbox=dict(boxstyle="round,pad=0.25", fc=BASE, ec="none", alpha=0.9))
    if logx:
        ax.set_xscale("log")
    ax.set_title(title, fontsize=10)
    ax.set_xlabel(xlabel, fontsize=8.5)
    ax.set_ylabel(ylabel, fontsize=8.5)
    ax.tick_params(labelsize=8)
    if ypct:
        fmt = "{:.1f}%" if y.max() - y.min() < 5 else "{:.0f}%"
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: it(fmt.format(v))))


JUMPS_K = "salti di prezzo (migliaia)"
DEFINITION = [  # curve, title, x label, y label, y scale, y in %, unit
    ("slot", "Durata dello slot", "minuti", JUMPS_K, 1e-3, False, " min"),
    ("theta", "Soglia del salto", "punti", JUMPS_K, 1e-3, False, " punti"),
    ("cut_start", "Taglio all'inizio della vita", "% della vita", JUMPS_K, 1e-3, False, "%"),
    ("cut_end", "Taglio alla fine della vita", "% della vita", JUMPS_K, 1e-3, False, "%"),
    ("edge", "Banda di chiusura", "punti da 0% o 100%", JUMPS_K, 1e-3, False, " punti"),
    ("clip", "Limite dei prezzi", "punti da 0% o 100%", JUMPS_K, 1e-3, False, " punti"),
    ("n_next", "Trade successivi: quanti", "trade nella media", "overshoot ai trade successivi", 1, True, ""),
    ("t_next", "Trade successivi: entro quanto", "minuti concessi", "salti con trade successivi", 100, True, " min"),
]


def definition_panels(mode, name, title):
    c = pd.read_csv(LD + f"r12/full/{mode}_curves.csv")
    fig, axes = plt.subplots(2, 4, figsize=(14, 6.6))
    for ax, (cv, t, xl, yl, ys, yp, unit) in zip(axes.flat, DEFINITION):
        d = c[c.curve == cv]
        kind = d.kind.iloc[0]
        elbow_panel(ax, d.x, d.y * ys, d.knee.iloc[0], t, xl, yl, yp, kind=kind, unit=unit,
                    used="dropped" if kind == "flat" and d.knee.iloc[0] == 0 else None)
    fig.suptitle(title, fontsize=13, weight="bold", color=TEXT)
    save(fig, name)


def m_definition():
    definition_panels("events", "m_definition", "Che cos'è un salto di prezzo: ogni parametro dalla sua curva, "
                      "gli altri ai loro valori")


def m_crypto():
    definition_panels("cx", "m_crypto", "Mercati crypto up/down: la stessa ricerca")


PARAMS = [  # curve, title, x label, y label, y in %, log x (display only: every knee is found on a linear axis), unit
    ("crowd", "Folla: almeno K trader", "K", "overshoot dei salti", True, False, " trader"),
    ("money", "Grandi somme: almeno $X nello slot", "$ nello slot (scala log.)", "overshoot dei salti", True, True, " $"),
    ("band", "Scommesse: salti che partono in [e, 1 − e]", "e, punti", "dispersione dei rendimenti", False, False, ""),
    ("trim", "Scommesse: quota riportata al limite", "% per lato", "rendimento medio, cent. per $", False, False, "%"),
    ("outcome", "Esito chiaro: prezzo finale oltre Q", "Q", "mercati", False, False, ""),
    ("cx_crowd", "Crypto: folla, almeno K trader", "K", "overshoot dei salti", True, False, " trader"),
    ("cx_outcome", "Crypto: esito chiaro oltre Q", "Q", "mercati", False, False, ""),
]
USED = {"band": "dropped"}


def m_params():
    c = pd.read_csv(LD + "r12/params_curves.csv")
    kk = pd.read_csv(LD + "r12/params_knees.csv").set_index("curve")
    fig, axes = plt.subplots(2, 4, figsize=(14, 6.4))
    for ax, (cv, t, xl, yl, yp, lg, unit) in zip(axes.flat, PARAMS):
        d = c[c.curve == cv]
        elbow_panel(ax, d.x, d.y, kk.knee[cv], t, xl, yl, yp, lg, kind=kk.kind[cv], used=USED.get(cv), unit=unit)
    for ax in axes.flat[len(PARAMS):]:
        ax.axis("off")
    fig.suptitle("Gli altri parametri, ciascuno dalla sua curva", fontsize=13, weight="bold", color=TEXT)
    save(fig, "m_params")


# ---------------------------------------------------------------- results

def f1_hero():
    """How often YES won, by the price right after a jump (up / down) and at every slot, in the
    price bins of b(p), with 95% ranges from resampling markets."""
    from r02_persistence import random_slots, outcomes
    b = pd.read_parquet(LD + "r03_big_moves_main.parquet")
    rnd = random_slots()
    rnd["outcome"] = rnd.market.map(outcomes())
    rnd = rnd[rnd.outcome.notna()]
    mid = (BINS[:-1] + BINS[1:]) / 2 * 100
    fig, ax = plt.subplots(figsize=(7.2, 6))
    ax.plot([0, 100], [0, 100], color=HL_MED, lw=1.2, ls=":")
    rr = rnd.groupby(pd.cut(rnd.vwap, BINS), observed=False).outcome.mean() * 100
    ax.plot(mid, rr.values, color=MUTED, lw=2, label="in tutti gli slot (errore di calibrazione)")
    res = {}
    for sgn, c, lab in ((1, UP, "subito dopo un salto in SU"), (-1, DOWN, "subito dopo un salto in GIÙ")):
        x = b[b.sgn == sgn].assign(one=1.0, bin=lambda d: pd.cut(d.p_close, BINS, labels=False))
        pts = []
        for k, g in x.groupby("bin"):
            lo, hi = boot_share(g, "outcome", den="one")
            pts.append((mid[int(k)], g.outcome.mean() * 100, lo * 100, hi * 100, len(g)))
        p = np.array(pts)
        ax.errorbar(p[:, 0], p[:, 1], yerr=[p[:, 1] - p[:, 2], p[:, 3] - p[:, 1]], fmt="o-", color=c, ecolor=c,
                    lw=2, ms=7, capsize=2, label=lab)
        res[sgn] = pd.DataFrame(p, columns=["mid", "yes", "lo", "hi", "n"])
    i = 5                                                       # the 50-60% bin
    up = res[1].set_index("mid").yes[mid[i]]
    dn = res[-1].set_index("mid").yes[mid[i]]
    ax.annotate(it(f"salto in SU fino al 50-60%:\nYES ha vinto solo il {up:.0f}% delle volte"), xy=(mid[i], up), xytext=(60, 22),
                fontsize=9, color=TEXT, arrowprops=dict(arrowstyle="-", color=UP, lw=0.8))
    ax.annotate(it(f"salto in GIÙ fino al 50-60%:\nYES ha vinto il {dn:.0f}% delle volte"), xy=(mid[i], dn), xytext=(12, 76),
                fontsize=9, color=TEXT, arrowprops=dict(arrowstyle="-", color=DOWN, lw=0.8))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    pct(ax)
    pct(ax, "x")
    ax.set_xlabel("prezzo di YES subito dopo il salto (o in uno slot qualsiasi)")
    ax.set_ylabel("quanto spesso YES ha vinto davvero")
    ax.set_title("Dopo un salto il prezzo è spostato troppo nella sua direzione")
    ax.legend(loc="upper left", fontsize=9)
    save(fig, "f1_hero")
    print(f"f1_hero: 50-60% bin, YES won after up jumps {up:.1f}%, after down jumps {dn:.1f}%, every slot {rr.iloc[i]:.1f}%; "
          f"fewest jumps in a point: {min(r.n.min() for r in res.values()):.0f}")


def count_colours(labels):
    def group(k):
        n = int(k.split("-")[0].split(" ")[0]) if k[0].isdigit() else 10 ** 6
        return TG["1"] if n == 1 else TG[FEW] if n < K_CROWD else TG[CROWD]
    return [group(k) for k in labels]


def f2_counts():
    t = pd.read_csv(LD + "r11_traders.csv", dtype={"traders": str})
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(10, 7), sharex=True, gridspec_kw={"height_ratios": [1, 1.1]})
    x = np.arange(len(t))
    col = count_colours(t.traders)
    a1.bar(x, t.share * 100, 0.7, color=col)
    for i, (sh, n) in enumerate(zip(t.share, t.jumps)):
        a1.text(i, sh * 100 + 1.2, it(f"{sh:.1%}\n{n:,}" if sh >= .01 else f"{sh:.1%}"), ha="center", fontsize=7.5, color=TEXT)
    a1.set_ylim(0, 82)
    pct(a1)
    a1.set_ylabel("quota dei salti di prezzo")
    a1.set_title("Quanti trader fanno un salto di prezzo, e quanto è il suo overshoot")
    a2.bar(x, t.overshoot * 100, 0.7, color=col)
    a2.errorbar(x, t.overshoot * 100, yerr=[(t.overshoot - t.lo) * 100, (t.hi - t.overshoot) * 100],
                fmt="none", ecolor=TEXT, lw=1)
    a2.axhline(0, color=SUBTLE, lw=1)
    pct(a2)
    a2.set_ylabel("overshoot, % del salto")
    a2.set_xticks(x, it_counts(t.traders))
    a2.set_xlabel(f"numero di trader diversi che hanno preso liquidità nei {SLOT} minuti del salto")
    save(fig, "f2_trader-counts", title_ax=a1)


def f2_robustness():
    r = pd.read_csv(LD + "r03_robustness.csv")
    fig, axes = plt.subplots(1, 3, figsize=(11, 4), sharey=True)
    for ax, bm in zip(axes, (5, SLOT, 60)):
        s = r[r.bar_min == bm].sort_values("threshold")
        v = {tg: s[f"takers {tg}"].values for tg in TGS}
        bars_tg(ax, np.arange(3), v, labels=(bm == 5))
        ax.set_xticks(np.arange(3), [f"≥ {t * 100:.0f} punti" for t in s.threshold], fontsize=9)
        ax.set_title(f"slot di {bm} minuti", fontsize=11)
        ax.set_xlabel("soglia minima del salto", fontsize=9)
        pct(ax)
    axes[0].set_ylabel("overshoot, % del salto")
    axes[0].set_ylim(0, 56)
    axes[2].legend(*axes[0].get_legend_handles_labels(), loc="upper right", ncol=3, fontsize=8, columnspacing=0.8)
    fig.suptitle("Lo stesso ordine per ogni definizione di salto di prezzo", fontweight="bold", color=TEXT)
    save(fig, "f2_robustness")


def f3_giveback_curve():
    c = pd.read_csv(LD + "r11_giveback_curve.csv")
    x, y = c.giveback.values * 100, c.density.values
    fig, ax = plt.subplots(figsize=(10, 4.3))
    ax.fill_between(x, y, color=TG["1"], alpha=0.25, lw=0)
    ax.plot(x, y, color=TG["1"], lw=2.2)
    for v in (0, 100):
        ax.axvline(v, color=SUBTLE, lw=1, ls=":")
    top = y.max() * 1.02
    ax.text(-4, top, "i trade successivi\nsono andati oltre", ha="right", va="top", fontsize=8.5, color=SUBTLE)
    ax.text(4, top, "i trade successivi hanno\nlasciato il salto com'era", ha="left", va="top", fontsize=8.5, color=SUBTLE)
    ax.text(104, top * 0.75, "hanno restituito tutto\nil salto o di più", ha="left", va="top", fontsize=8.5, color=SUBTLE)
    ax.set_xlim(-100, 200)
    ax.set_ylim(0, top * 1.05)
    pct(ax, "x")
    ax.set_xlabel("quota del salto restituita dai trade successivi")
    ax.set_ylabel("densità dei salti di un trader singolo")
    ax.set_yticks([])
    ax.set_title("Salti di un trader singolo: quanto restituiscono i trade successivi (curva smussata)")
    save(fig, "f3_giveback-curve")


def f3_decay():
    c = pd.read_csv(LD + "r03_curves_catbase.csv", index_col=[0, 1]).loc["tg"]
    cols = ["close", "next trades", "1h", "6h", "24h"]
    labels = ["fine dello slot", "trade successivi\n(minuti dopo)", "+1 ora", "+6 ore", "+24 ore"]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    x = np.arange(len(cols))
    for tg in TGS:
        v = c.loc[tg, cols].values.astype(float) * 100
        ax.plot(x, v, "o-", color=TG[tg], lw=2.4, ms=8, label=TG_LABEL[tg])
        ax.text(x[0] - 0.08, v[0], f"{v[0]:.0f}%", ha="right", va="center", fontsize=9, color=TG[tg])
        dy = -3.2 if tg == "1" else 1.2
        ax.text(x[1] + 0.08, v[1] + dy, f"{v[1]:.0f}%", fontsize=9, color=TG[tg])
    ax.axhline(0, color=SUBTLE, lw=1)
    ax.set_xticks(x, labels)
    ax.set_xlim(-0.5, len(cols) - 0.6)
    pct(ax)
    ax.set_ylabel("overshoot ancora nel prezzo, % del salto")
    ax.legend(fontsize=9)
    ax.set_title("L'overshoot di un trader singolo sparisce ai trade successivi;\nquello di una folla cala nell'arco di ore")
    save(fig, "f3_decay")


def f2_accuracy():
    a = pd.read_csv(LD + "r11_accuracy.csv", dtype={"group": str})
    a = a[a.by == "k"]
    fig, ax = plt.subplots(figsize=(10, 4.6))
    x = np.arange(len(a))
    ax.plot(x, a.expected_after * 100, "--", color=MUTED, lw=1.8)
    ax.plot(x, a.expected_before * 100, ":", color=MUTED, lw=1.8)
    ax.text(x[-1] + 0.15, a.expected_after.iloc[-1] * 100, "se fosse giusto il prezzo\ndopo il salto",
            va="center", fontsize=8.5, color=SUBTLE)
    ax.text(x[-1] + 0.15, a.expected_before.iloc[-1] * 100, "se fosse giusto il prezzo\nprima del salto",
            va="center", fontsize=8.5, color=SUBTLE)
    ax.errorbar(x, a.right * 100, yerr=[(a.right - a.lo) * 100, (a.hi - a.right) * 100], fmt="none", ecolor=TEXT, lw=1)
    ax.scatter(x, a.right * 100, s=60, c=count_colours(a.group), zorder=3)
    ax.text(x[-1] + 0.15, a.right.iloc[-1] * 100, "osservato", va="center", fontsize=8.5, color=TEXT, weight="bold")
    ax.set_xticks(x, it_counts(a.group))
    ax.set_xlim(-0.5, len(a) + 1.6)
    ax.set_ylim(35, 68)
    pct(ax)
    ax.set_xlabel(f"numero di trader diversi nei {SLOT} minuti del salto")
    ax.set_ylabel("salti nella direzione\ndell'esito finale, %")
    ax.set_title("I salti indovinano la direzione più spesso di quanto dicesse il prezzo di prima,\nmeno di quanto dica quello di dopo")
    save(fig, "f2_accuracy")


def f5_fade():
    """Winsorized return per $1 of betting against price jumps (explore/r08_fade_robust.py)."""
    f = pd.read_csv(LD + "r08_fade_robust.csv")
    t = f[f.split == "takers"].set_index("group").loc[list(TGS)]
    m = f[f.split == "money in bar"].set_index("group").loc[["below", "above"]]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10.5, 4.3), sharey=True, gridspec_kw=dict(width_ratios=[3, 2]))
    for ax, d, cols, labels, title in (
            (a1, t, [TG[k] for k in TGS], [TG_LABEL[k] for k in TGS], "Per chi ha fatto il salto"),
            (a2, m, [IRIS] * 2, [f"meno di ${MONEY_X:,.0f}", f"${MONEY_X:,.0f} o più"], "Per dollari scambiati nel salto")):
        x = np.arange(len(d))
        ax.bar(x, d.trimmed * 100, 0.55, color=cols)
        ax.errorbar(x, d.trimmed * 100, yerr=[(d.trimmed - d["trimmed lo"]) * 100, (d["trimmed hi"] - d.trimmed) * 100],
                    fmt="none", ecolor=TEXT, lw=1)
        ax.axhline(0, color=TEXT, lw=1)
        ax.set_xticks(x, labels)
        ax.set_title(title, fontsize=11)
        ax.set_ylim(-14, 21)
    for i, sp in enumerate(t["spread (cents)"]):
        a1.text(i, 18.5, it(f"spread {sp:.1f}¢"), ha="center", fontsize=8.5, color=SUBTLE)
    a2.set_xlabel(f"dollari scambiati nei {SLOT} minuti del salto")
    a1.set_ylabel("guadagno per $1 puntato contro il salto\n(centesimi, al netto dello spread)")
    fig.suptitle("Scommettere contro i salti: si perde con i trader singoli, si guadagna con folle e grandi somme",
                 fontweight="bold", color=TEXT, fontsize=11.5)
    save(fig, "f5_fade")


ALL = {"ex1": ex1_example, "m_calibration": m_calibration, "pipeline": bg_pipeline, "t_dataset": t_dataset,
       "d_stats": d_stats, "m_definition": m_definition, "m_params": m_params, "m_crypto": m_crypto,
       "f1_hero": f1_hero, "f2_counts": f2_counts, "f2_robustness": f2_robustness,
       "f3_giveback_curve": f3_giveback_curve, "f3": f3_decay, "f2_accuracy": f2_accuracy, "f5": f5_fade}


def main(names):
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(OUT_PDF, exist_ok=True)
    for n in names or list(ALL):
        ALL[n]()


if __name__ == "__main__":
    main(sys.argv[1:])
