"""
Report figures (report/plots/*.png), all in the Rose Pine Dawn theme (explore/report_style.py)
with one fixed colour per trader group. Every figure is drawn from tables the rounds already
saved; nothing here changes a result.

Opening
  ex1_example-market        a real market's price with its price jumps marked
  ex2_example-overshoot     the same market, one move annotated (jump, given back, outcome)
  bg_spikes-by-category     how many markets have price jumps, and how many
  bg_pipeline               the data pipeline
F1  f1_hero                 price right after a jump vs how often YES won (up / down / random)
    f1_splits               overshoot by category, year, price band, time to end
    f1_tags                 the 10 lowest and 10 highest tags
F2  f2_traders, f2_money, f2_robustness, f2_controlled, f2_wallets, f2_two-moves, f2_average-move
F3  f3_decay
F4  f4_versions
F5  f5_fade
F6  f6_structure, f6_tags
F7  sp_groups, sp_sport (sports and esports, whole life)
F8  f8_close-vs-next, f8_confirmation

Usage: python explore/report_figures.py [name ...]   (no names = all)
"""
import glob
import os
import sys

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, "explore")
from report_style import (BASE, MUTED, SUBTLE, TEXT, HL_MED, LOVE, GOLD, ROSE, PINE, FOAM, IRIS,  # noqa: E402
                          TG, TG_LABEL, UP, DOWN)
from r02_persistence import (BAR, CROWD, EDGE, FEW, K_CROWD, LIFE_CUT_END, LIFE_CUT_START, MONEY_X,  # noqa: E402
                             TG_EDGES, TG_LABELS, F9_BEFORE, F9_STEP, CX_SLOT, CX_TG_LABELS, CONTROL_BINS, CX_MOVED, OFFSET_LO, OFFSET_HI,
                             random_slots, share)
SLOT = BAR // 60      # slot length in minutes, for labels
import locale  # noqa: E402
locale.setlocale(locale.LC_NUMERIC, "it_IT.UTF-8")
plt.rcParams["axes.formatter.use_locale"] = True


def it(s):
    """English number format -> Italian (1,234.5 -> 1.234,5)."""
    return s.translate(str.maketrans(",.", ".,"))


def it_counts(labels):
    return [str(k).replace("over", "oltre") for k in labels]

OUT = "report/plots/"
LD = "local_data/"
TGS = tuple(TG_LABELS)
CX_TGS = tuple(CX_TG_LABELS)                     # crypto trader groups (F8), from their own knee
CX_TG = dict(zip(CX_TGS, (LOVE, GOLD, PINE)))
CX_TG_LABEL = {k: "1 trader" if k == "1" else f"{k} traders" for k in CX_TGS}
CX_CROWD = CX_TGS[2]
EXAMPLE = 523331      # "Will Apple launch another iPhone on February 19?" (2025)


def save(fig, name):
    fig.tight_layout()
    fig.savefig(OUT + name + ".png")
    plt.close(fig)


def pct(ax, axis="y"):
    fmt = plt.FuncFormatter(lambda v, _: f"{v:.0f}%")
    (ax.yaxis if axis == "y" else ax.xaxis).set_major_formatter(fmt)


# ---------------------------------------------------------------- opening

def example_data():
    # full trade history of the example market (remote/p7_extract.py): 599 trades
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
    # the slot slots the price jumps are found on (as remote/s2_events.py): dollar-weighted
    # average price of the slot's trades, stamped at the slot's end
    s = s.assign(bar=s.ts // BAR, pv=s.yes * s.usd_amount)
    g = s.groupby("bar").agg(pv=("pv", "sum"), usd=("usd_amount", "sum"), last=("yes", "last"))
    g["vwap"] = (g.pv / g.usd.where(g.usd > 0)).fillna(g["last"])
    g["t"] = pd.to_datetime((g.index + 1) * BAR, unit="s")
    return g.reset_index(drop=True)


NEWS = [("2025-02-13 17:00", "13 feb: Tim Cook annuncia\n\"il nuovo membro\ndella famiglia\""),
        ("2025-02-17 12:00", "16-17 feb: indiscrezioni\nsul nuovo nome\ndel telefono"),
        ("2025-02-19 16:00", "19 feb: Apple\npresenta\nl'iPhone 16e")]


def ex1_example():
    """The example market: the average price of every slot slot with trades, with its
    price jumps (from one slot to the next) in the accent colour and the news dates."""
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
    # the window kept (as remote/s2_events.window): the first LIFE_CUT_START and the last LIFE_CUT_END
    # of the life, which runs from the first slot to the last slot inside the settle band
    inside = bars["last"].between(EDGE * 100, 100 - EDGE * 100)
    t0, t1 = bars.t.iloc[0], bars.t[inside].iloc[-1]
    a0, a1 = t0 + (t1 - t0) * LIFE_CUT_START, t1 - (t1 - t0) * LIFE_CUT_END
    for a, z in ((t0 - pd.Timedelta(hours=3), a0), (a1, bars.t.iloc[-1] + pd.Timedelta(hours=3))):
        ax.axvspan(a, z, color=HL_MED, alpha=0.6, lw=0, zorder=0)
    ax.fill_between([], [], color=HL_MED, alpha=0.6, label=it(f"parti escluse: primo {LIFE_CUT_START * 100:g}% e ultimo {LIFE_CUT_END * 100:g}% della vita del mercato"))
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


def ex2_overshoot():
    s, b = example_data()
    sat = b[(b.t >= "2025-02-15 07:00") & (b.t <= "2025-02-15 14:00") & (b.sgn > 0)]
    r = sat.iloc[0]                                               # Saturday morning: the lone sweep
    t0, t1 = pd.Timestamp("2025-02-15 06:00"), pd.Timestamp("2025-02-16 12:00")
    w = s[(s.t >= t0) & (s.t <= t1)]
    sweep = w[w.t == pd.Timestamp("2025-02-15 07:51:36")]
    fig, ax = plt.subplots(figsize=(9.5, 4.6))
    ax.axvspan(sweep.t.iloc[0] - pd.Timedelta(minutes=6), sweep.t.iloc[0] + pd.Timedelta(minutes=9), color=HL_MED,
               alpha=0.7, lw=0)
    ax.scatter(w.t, w.yes, s=12 + np.sqrt(w.usd_amount) * 6, color=IRIS, alpha=0.75, lw=0, label="trades (size = $)")
    pre, post = r.y_pre * 100, r.p_close * 100
    eve = w[(w.t >= "2025-02-15 18:00") & (w.t < "2025-02-15 19:00")].yes.median()
    mon = s[s.t >= "2025-02-17 00:00"].yes.iloc[0]
    ax.annotate(f"07:51, one trader, one transaction:\n${sweep.usd_amount.sum():.0f} in {len(sweep)} fills, "
                f"from {sweep.yes.min():.0f}% up to {sweep.yes.max():.0f}%",
                xy=(sweep.t.iloc[0], sweep.yes.max()), xytext=(t0 + pd.Timedelta(hours=1), 88),
                fontsize=9, color=LOVE, arrowprops=dict(arrowstyle="->", color=LOVE, lw=0.8))
    ax.text(pd.Timestamp("2025-02-15 11:30"), post + 5,
            f"price jump: {pre:.0f}% → {post:.0f}%\n({SLOT}-minute averages; no news found)", fontsize=9, color=LOVE)
    ax.text(pd.Timestamp("2025-02-15 19:30"), eve + 6,
            f"evening: other traders sell it back to {eve:.0f}%\n(Monday morning: {mon:.0f}%)", fontsize=9, color=TEXT)
    ax.axhline(99.4, color=PINE, lw=2.5)
    ax.text(t1, 94.5, "final outcome: YES (four days later, for a different reason)", ha="right", color=PINE,
            fontsize=8.5)
    ax.set_ylim(0, 100)
    ax.set_xlim(t0, t1)
    pct(ax)
    date_axis(ax)
    ax.legend(loc="lower right", fontsize=9)
    ax.set_ylabel("prezzo di YES")
    ax.set_title("Saturday 15 February up close: a lone trader's sweep, mostly given back within a day")
    save(fig, "ex2_example-overshoot")


def bg_spikes():
    tab = pd.read_csv(LD + "report_stats.csv", index_col=0).drop("other")
    tab = tab.sort_values("with_spike")
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 4.2), sharey=True, gridspec_kw=dict(width_ratios=[1.6, 1]))
    y = np.arange(len(tab))
    a1.barh(y, tab.with_spike * 100, color=IRIS, height=0.62)
    for i, (v, n) in enumerate(zip(tab.with_spike, tab.markets)):
        a1.text(v * 100 + 1.5, i, f"{v:.0%} of {n:,}", va="center", fontsize=9, color=TEXT)
    a1.set_yticks(y, tab.index)
    a1.set_xlim(0, 105)
    pct(a1, "x")
    a1.set_xlabel("markets with at least one price jump")
    a1.grid(axis="y", visible=False)
    a1.set_title("How many markets have price jumps")
    a2.barh(y, tab.median_if_any, color=FOAM, height=0.62)
    for i, v in enumerate(tab.median_if_any):
        a2.text(v + 0.15, i, f"{v:.0f}", va="center", fontsize=9, color=TEXT)
    a2.set_xlabel("price jumps per market (median,\nmarkets that have any)")
    a2.set_xlim(0, tab.median_if_any.max() * 1.25)
    a2.grid(axis="y", visible=False)
    a2.set_title("How many each")
    save(fig, "bg_spikes-by-category")


def bg_pipeline():
    mk = pd.read_parquet(LD + "r03_big_moves_main.parquet", columns=["market"]).market
    steps = [("766M trades\n32 GB\n(server)", MUTED),
             ("regroup by market\n32 buckets,\none pass, ~30 min", MUTED),
             (f"{SLOT}-min slots\nper market\n(price, $, traders)", IRIS),
             (f"price jumps\n{len(mk) / 1e6:.2f}M\nin {mk.nunique() / 1e3:.0f}k markets", IRIS),
             ("compare with the\nfinal outcome\n= overshoot", LOVE),
             ("small tables to the PC:\nstatistics, plots,\nmatrix profiles", PINE)]
    fig, ax = plt.subplots(figsize=(11, 1.8))
    ax.set_axis_off()
    w, gap = 1.55, 0.35
    for i, (txt, c) in enumerate(steps):
        x0 = i * (w + gap)
        ax.add_patch(plt.Rectangle((x0, 0), w, 1, facecolor=BASE, edgecolor=c, lw=2))
        ax.text(x0 + w / 2, 0.5, txt, ha="center", va="center", fontsize=9, color=TEXT)
        if i < len(steps) - 1:
            ax.annotate("", xy=(x0 + w + gap - 0.03, 0.5), xytext=(x0 + w + 0.03, 0.5),
                        arrowprops=dict(arrowstyle="->", color=SUBTLE, lw=1.4))
    ax.set_xlim(-0.05, len(steps) * (w + gap) - gap + 0.05)
    ax.set_ylim(-0.1, 1.1)
    save(fig, "bg_pipeline")


# ---------------------------------------------------------------- F1

def outcomes_random():
    from r02_persistence import outcomes
    rnd = random_slots()
    rnd["outcome"] = rnd.market.map(outcomes())
    return rnd[rnd.outcome.notna()]


def f1_hero():
    b = pd.read_parquet(LD + "r03_big_moves_main.parquet")
    rnd = outcomes_random()
    bins = np.arange(0.05, 0.96, 0.1)
    mid = (bins[:-1] + bins[1:]) / 2 * 100
    fig, ax = plt.subplots(figsize=(7.2, 6))
    ax.plot([0, 100], [0, 100], color=HL_MED, lw=1.2, ls=":")
    rr = rnd.groupby(pd.cut(rnd.vwap, bins), observed=False).outcome.mean() * 100
    ax.plot(mid, rr.values, color=MUTED, lw=2, label="in momenti casuali (errore abituale)")
    for sgn, c, lab in ((1, UP, "subito dopo un salto in SU"), (-1, DOWN, "subito dopo un salto in GIÙ")):
        x = b[b.sgn == sgn]
        g = x.groupby(pd.cut(x.p_close, bins), observed=False).agg(y=("outcome", "mean"), n=("outcome", "size"))
        ok = (g.n >= 300).values
        ax.plot(mid[ok], g.y.values[ok] * 100, "o-", color=c, lw=2, ms=7, label=lab)
    i = 5                                                       # annotate the 55-65% bin
    up = b[(b.sgn > 0) & b.p_close.between(bins[i], bins[i + 1])].outcome.mean() * 100
    dn = b[(b.sgn < 0) & b.p_close.between(bins[i], bins[i + 1])].outcome.mean() * 100
    ax.annotate(f"salto in SU fino a ~60%:\nYES ha vinto solo il {up:.0f}% delle volte", xy=(mid[i], up), xytext=(64, 22),
                fontsize=9, color=TEXT, arrowprops=dict(arrowstyle="-", color=UP, lw=0.8))
    ax.annotate(f"salto in GIÙ fino a ~60%:\nYES ha vinto il {dn:.0f}% delle volte", xy=(mid[i], dn), xytext=(18, 76),
                fontsize=9, color=TEXT, arrowprops=dict(arrowstyle="-", color=DOWN, lw=0.8))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    pct(ax)
    pct(ax, "x")
    ax.set_xlabel("prezzo di YES subito dopo il salto (o in un momento casuale)")
    ax.set_ylabel("quanto spesso YES ha vinto davvero")
    ax.set_title("Dopo un salto il prezzo è spostato troppo nella sua direzione")
    ax.legend(loc="upper left", fontsize=9)
    save(fig, "f1_hero")
    print(f"f1_hero: 55-65% bin, YES won after up moves {up:.1f}%, after down moves {dn:.1f}%, random {rr.iloc[i]:.1f}%")


def f1_splits():
    s = pd.read_csv(LD + "r02_summary.csv")
    allv = s[(s.grouping == "all") & (s.scope == "all")].share.iloc[0] * 100
    cat = s[(s.grouping == "all") & s.scope.str.startswith("cat=") & (s.scope != "cat=other")]
    yr = s[(s.grouping == "all") & s.scope.str.startswith("year=")]
    pb = s[(s.grouping == "price before") & (s.scope == "all")]
    te = s[(s.grouping == "time to end date") & (s.scope == "all")]
    panels = [("by category", cat.scope.str[4:], cat.share, None, None),
              ("by year", yr.scope.str[5:], yr.share, None, None),
              ("by price before the jump", pb.level.replace({"<.2": "under 20%", ".2-.4": "20-40%", ".4-.6": "40-60%",
                                                             ".6-.8": "60-80%", ">.8": "over 80%"}), pb.share, pb.lo, pb.hi),
              ("by time left until the end date", te.level.replace({"<1d": "under 1 day", "1-7d": "1-7 days",
                                                                    "7-30d": "1-4 weeks", ">30d": "over a month"}),
               te.share, te.lo, te.hi)]
    fig, axes = plt.subplots(2, 2, figsize=(10, 6.5))
    for ax, (title, lab, v, lo, hi), c in zip(axes.ravel(), panels, (IRIS, FOAM, GOLD, ROSE)):
        y = np.arange(len(lab))[::-1]
        ax.barh(y, v * 100, color=c, height=0.6)
        if lo is not None:
            ax.errorbar(v * 100, y, xerr=[(v - lo) * 100, (hi - v) * 100], fmt="none", ecolor=SUBTLE, lw=1)
        ax.axvline(allv, color=TEXT, lw=1.2, ls="--")
        ax.set_yticks(y, list(lab))
        ax.set_xlim(0, 52)
        pct(ax, "x")
        ax.grid(axis="y", visible=False)
        ax.set_title(title, fontsize=11)
    fig.suptitle(f"Overshoot is over 30% everywhere (dashed line = all markets, {allv:.0f}%)",
                 fontweight="bold", color=TEXT)
    for ax in axes[1]:
        ax.set_xlabel("overshoot, % del salto")
    save(fig, "f1_splits")


def f1_tags():
    t = pd.read_csv(LD + "r04_by_tag.csv").sort_values("overshoot")
    n = len(t)
    t = pd.concat([t.head(10), t.tail(10)])
    fig, ax = plt.subplots(figsize=(7.5, 6.4))
    y = np.arange(len(t))
    ax.barh(y, t.overshoot * 100, color=[PINE] * 10 + [LOVE] * 10, height=0.65)
    ax.set_yticks(y, [f"{a}  ({int(m):,})" for a, m in zip(t.tag, t.markets)], fontsize=9)
    ax.axhline(9.5, color=HL_MED, lw=1)
    pct(ax, "x")
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("overshoot, % of the jump   (markets with price jumps in brackets)")
    ax.set_title(f"The 10 lowest and 10 highest of {n} tags")
    save(fig, "f1_tags")


# ---------------------------------------------------------------- F2

def bars_tg(ax, x, vals, lo=None, hi=None, width=0.25, labels=True):
    for k, tg in enumerate(TGS):
        xs = np.asarray(x) + (k - 1) * width
        v = np.asarray(vals[tg]) * 100
        ax.bar(xs, v, width * 0.92, color=TG[tg], label=TG_LABEL[tg] if labels else None)
        if lo is not None:
            ax.errorbar(xs, v, yerr=[v - np.asarray(lo[tg]) * 100, np.asarray(hi[tg]) * 100 - v],
                        fmt="none", ecolor=TEXT, lw=1)


def f2_traders():
    s = pd.read_csv(LD + "r02_summary.csv")
    t = s[(s.grouping == "distinct takers") & (s.scope == "all")].set_index("level")
    fig, ax = plt.subplots(figsize=(6.5, 4))
    x = np.arange(3)
    v = t.loc[list(TGS)]
    ax.bar(x, v.share * 100, 0.6, color=[TG[k] for k in TGS])
    ax.errorbar(x, v.share * 100, yerr=[(v.share - v.lo) * 100, (v.hi - v.share) * 100], fmt="none", ecolor=TEXT, lw=1)
    for i, (sh, n) in enumerate(zip(v.share, v.moves)):
        ax.text(i + 0.12, sh * 100 + 1.2, f"{sh:.0%}", ha="left", fontsize=11, color=TEXT, weight="bold")
        ax.text(i, 1.5, f"{n / 1000:.0f}k jumps", ha="center", fontsize=8.5, color=BASE)
    ax.set_xticks(x, [TG_LABEL[k] for k in TGS])
    ax.set_ylim(0, 48)
    pct(ax)
    ax.set_ylabel("overshoot, % del salto")
    ax.set_title("The more traders behind a jump, the less it overshoots")
    save(fig, "f2_traders")


def f2_money():
    b = pd.read_parquet(LD + "r02_big_moves.parquet")
    b = b.assign(tg=pd.cut(b.takers, TG_EDGES, labels=list(TGS)),
                 ug=pd.cut(b.usd, [0, MONEY_X, np.inf], labels=["below", "above"]))
    v, lo, hi = {}, {}, {}
    for tg, s in b.groupby("tg", observed=True):
        r = [share(c) for _, c in s.groupby("ug", observed=False)]
        v[tg], lo[tg], hi[tg] = [a[0] for a in r], [a[1] for a in r], [a[2] for a in r]
    fig, ax = plt.subplots(figsize=(7.5, 4.3))
    bars_tg(ax, np.arange(2), v, lo, hi)
    ax.set_xticks(np.arange(2), [f"under ${MONEY_X:,.0f}", f"${MONEY_X:,.0f} or more"])
    for tg in TGS:
        print(f"f2_money {tg}: " + ", ".join(f"{x:.3f}" for x in v[tg]))
    ax.set_xlabel(f"money traded in the jump's {SLOT} minutes")
    ax.set_ylabel("overshoot, % del salto")
    pct(ax)
    ax.legend(ncol=3, loc="upper left", fontsize=9)
    ax.set_ylim(0, 62)
    ax.set_title("At the same money, one trader's jumps overshoot most")
    save(fig, "f2_money")


def f2_robustness():
    r = pd.read_csv(LD + "r03_robustness.csv")
    fig, axes = plt.subplots(1, 3, figsize=(11, 4), sharey=True)
    for ax, bm in zip(axes, (5, BAR // 60, 60)):
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


def f2_controlled():
    f = pd.read_csv(LD + "r05/r05_factor_effects.csv")
    f = f[f.factor == "takers"].set_index("level")
    t = pd.read_parquet(LD + "r04_tradable.parquet")
    t = t[t.oq.notna()]
    raw = t.groupby("tg", observed=True).apply(lambda x: x.oq.sum() / x.absdp.sum())
    fig, ax = plt.subplots(figsize=(7, 3.8))
    y = np.array([1, 0])
    for i, tg in enumerate(TGS[1:]):
        gap = (raw[tg] - raw["1"]) * 100
        ax.barh(y[i] + 0.18, gap, 0.32, color=MUTED, label="raw difference" if i == 0 else None)
        e = f.loc[tg]
        ax.barh(y[i] - 0.18, e.effect * 100, 0.32, color=TG[tg],
                label="with every other factor held fixed" if i == 0 else None)
        ax.errorbar(e.effect * 100, y[i] - 0.18, xerr=[[(e.effect - e.lo) * 100], [(e.hi - e.effect) * 100]],
                    fmt="none", ecolor=TEXT, lw=1)
        ax.text(-0.6, y[i] + 0.18, f"{gap:.0f}", va="center", ha="right", fontsize=9, color=BASE, weight="bold")
        ax.text(-0.6, y[i] - 0.18, f"{e.effect * 100:.0f}", va="center", ha="right", fontsize=9, color=BASE, weight="bold")
    ax.set_yticks(y, [f"{TG_LABEL[k]}\nvs 1 trader" for k in TGS[1:]])
    ax.axvline(0, color=TEXT, lw=1)
    ax.set_xlim(-30, 2)
    ax.set_xlabel("difference in overshoot, percentage points of the jump")
    ax.legend(loc="upper left", fontsize=9)
    ax.grid(axis="y", visible=False)
    ax.set_title("Holding category, money, price, timing, year... fixed\nbarely changes the gap")
    save(fig, "f2_controlled")
    print(f"f2_controlled raw gaps: {FEW} {(raw[FEW] - raw['1']) * 100:.1f}, {CROWD} {(raw[CROWD] - raw['1']) * 100:.1f}")


def f2_wallets():
    w = pd.read_csv(LD + "r03_wallet_halves.csv")
    a, b = w.iloc[:, 1].clip(-2, 2) * 100, w.iloc[:, 2].clip(-2, 2) * 100
    r = np.corrcoef(a, b)[0, 1]
    fig, ax = plt.subplots(figsize=(5.8, 5.4))
    ax.scatter(a, b, s=7, color=LOVE, alpha=0.35, lw=0)
    ax.axhline(0, color=SUBTLE, lw=0.8)
    ax.axvline(0, color=SUBTLE, lw=0.8)
    pct(ax)
    pct(ax, "x")
    ax.grid(axis="x", visible=True)
    ax.set_xlabel("wallet's overshoot, first half of its jumps")
    ax.set_ylabel("same wallet, second half")
    ax.set_title(f"A wallet's past overshoot barely predicts its future\n({len(w):,} wallets, correlation {r:.2f})")
    save(fig, "f2_wallets")


def paths():
    p = pd.concat([pd.read_parquet(f) for f in glob.glob(LD + "r04_paths/moves_*.parquet")], ignore_index=True)
    b = pd.read_parquet(LD + "r03_big_moves_main.parquet",
                        columns=["market", "t_close", "oc", "y_pre", "absdp", "sgn", "tg", "takers", "usd"])
    d = p.merge(b, on=["market", "t_close"])
    ent = pd.read_parquet(LD + "r03_tradable_main.parquet", columns=["market", "t_close", "entry_delay"])
    d = d.merge(ent, on=["market", "t_close"], how="left")
    P = d.filter(regex=r"^p\d+$").values.astype(float)
    ok = np.isfinite(P).all(1) & d.oc.notna().values
    return d[ok].reset_index(drop=True), P[ok]


def f2_average(d, P):
    """Only moves whose market traded again within 10 min: in markets that go quiet the
    forward-filled price holds the moved level until the next trade, hiding the snap-back."""
    x = (np.arange(P.shape[1]) - F9_BEFORE // F9_STEP) * F9_STEP
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.axvspan(-BAR // 60, 0, color=HL_MED, alpha=0.6, lw=0)
    busy = d.entry_delay.values <= 600
    for tg in TGS:
        s = (d.tg.values == tg) & busy
        kept = (d.sgn.values[s, None] * (P[s] - d.y_pre.values[s, None])).sum(0) / d.absdp.values[s].sum() * 100
        fair = 100 - d.oc.values[s].sum() / d.absdp.values[s].sum() * 100
        ax.plot(x, kept, color=TG[tg], lw=2.4, label=f"{TG_LABEL[tg]} ({s.sum():,} jumps)")
        ax.plot([x[-1] + 6, x[-1] + 16], [fair, fair], color=TG[tg], lw=4, solid_capstyle="butt")
        print(f"f2_average {tg}: close {kept[F9_BEFORE // F9_STEP]:.0f} end {kept[-1]:.0f} fair {fair:.0f}")
    ax.text(x[-1] + 11, 112, "outcome\njustifies", ha="center", fontsize=8, color=SUBTLE)
    ax.axhline(0, color=SUBTLE, lw=1)
    ax.axhline(100, color=SUBTLE, lw=0.8, ls=":")
    ax.set_xlim(x[0], x[-1] + 20)
    ax.set_ylim(-10, 125)
    pct(ax)
    ax.set_xlabel(f"minutes from the end of the jump's {SLOT}-minute slot")
    ax.set_ylabel("share of the jump still in the price")
    ax.set_title("The average price jump (markets that traded again within 10 minutes)")
    ax.legend(loc="lower right", bbox_to_anchor=(0.88, 0.06), fontsize=9)
    save(fig, "f2_average-move")


def f2_two_moves(d, P):
    x = (np.arange(P.shape[1]) - F9_BEFORE // F9_STEP) * F9_STEP
    picks = [(518038, 1737451200, "One trader, $244: undone within two minutes",
              "Will Aryna Sabalenka win the Australian Open?\n21 Jan 2025, 09:20 UTC", TG["1"]),
             (542539, 1755872400, "147 traders, $141.8k: the jump held",
              "No change in Fed interest rates after the\nSeptember 2025 meeting? 22 Aug 2025, 14:20 UTC", TG[CROWD])]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2))
    for ax, (m, tc, title, sub, col) in zip(axes, picks):
        i = np.flatnonzero((d.market.values == m) & (d.t_close.values == tc))[0]
        ax.axvspan(-BAR // 60, 0, color=HL_MED, alpha=0.6, lw=0)
        ax.plot(x, P[i] * 100, color=col, lw=2.4, drawstyle="steps-post")
        ax.set_title(title, fontsize=10.5)
        top = P[i].max() < 0.7          # the question goes where the line isn't
        ax.text(0.02, 0.97 if top else 0.03, sub, transform=ax.transAxes, va="top" if top else "bottom",
                fontsize=8.5, color=SUBTLE)
        ax.set_xlabel("minutes from the end of the jump's slot")
        ax.set_ylim(0, 100)
        pct(ax)
    axes[0].set_ylabel(f"price of YES (every {F9_STEP} min)")
    save(fig, "f2_two-moves")


# ---------------------------------------------------------------- F3

def f3_decay():
    c = pd.read_csv(LD + "r03_curves_catbase.csv", index_col=[0, 1]).loc["tg"]
    cols = ["close", "next trades", "1h", "6h", "24h"]
    labels = ["fine dello slot", "trade successivi\n(minuti dopo)", "+1 ora", "+6 ore", "+24 ore"]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    x = np.arange(len(cols))
    for tg in TGS:
        v = c.loc[tg, cols].values * 100
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


# ---------------------------------------------------------------- F4

def f4_versions():
    """F4: overshoot by what the other candidates did in the move's slot (neg-risk events),
    at the close and at the next trades."""
    r = pd.read_csv(LD + "r07/sib_versions.csv")
    r = r[r.neg_risk == 1]
    groups = ["isolated", "not offset", "partly offset", "offset"]
    labels = ["no other\ncandidate traded", "others traded,\nno offset", f"partly offset\n({OFFSET_LO:.0%}-{OFFSET_HI:.0%})", f"offset\n({OFFSET_HI:.0%}+)"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), sharey=True)
    for ax, tg in zip(axes, ("1", CROWD)):
        x = np.arange(4)
        s = r[(r.version == "all trades") & (r.takers.astype(str) == tg)].set_index("group").reindex(groups)
        ax.bar(x, s.close * 100, 0.55, color=TG[tg], label=f"at the end of the {SLOT} minutes")
        ax.errorbar(x, s.close * 100, yerr=[(s.close - s.lo) * 100, (s.hi - s.close) * 100], fmt="none", ecolor=TEXT, lw=1)
        ax.scatter(x, s["next trades"] * 100, marker="D", s=55, color=SUBTLE, zorder=3, label="at the next trades")
        for i, n in enumerate(s.moves):
            ax.text(i, -17, f"{n:,.0f} jumps", ha="center", fontsize=8, color=SUBTLE)
        ax.axhline(0, color=TEXT, lw=1)
        ax.set_xticks(x, labels, fontsize=9)
        ax.set_title(f"jumps made by {TG_LABEL[tg]}", fontsize=11)
        pct(ax)
    axes[0].set_ylabel("overshoot, % del salto")
    axes[1].legend(fontsize=8, loc="upper right")
    axes[0].set_ylim(-20, 80)
    fig.suptitle("A crowd's jump that the other candidates offset is right at once",
                 fontweight="bold", color=TEXT)
    save(fig, "f4_versions")


# ---------------------------------------------------------------- F5

def f5_fade():
    """Trimmed return per $1 of betting against price jumps (explore/r08_fade_robust.py)."""
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
        a1.text(i, 18.5, f"spread {sp:.1f}¢".replace(".", ","), ha="center", fontsize=8.5, color=SUBTLE)
    a2.set_xlabel(f"dollari scambiati nei {SLOT} minuti del salto")
    a1.set_ylabel("guadagno per $1 puntato contro il salto\n(centesimi, al netto dello spread)")
    fig.suptitle("Scommettere contro i salti: si perde con i trader singoli, si guadagna con folle e grandi somme",
                 fontweight="bold", color=TEXT, fontsize=11.5)
    save(fig, "f5_fade")


# ---------------------------------------------------------------- F6

def f6_structure():
    c = pd.read_csv(LD + "r06/r06_conc_corr.csv")
    c = c[c.target == "rate1"].set_index("measure")
    names = {"roll": "Roll spread", "kyle_lambda": "price impact per $ (Kyle's lambda)", "spread_med": "buy-sell gap",
             "vr4": "variance ratio", "two_sided": "two-sided flow", "gini": "Gini of $ per wallet",
             "hhi": "Herfindahl of $ per wallet", "top1": "largest wallet's share", "top10": "top 10% wallets' share"}
    c = c.loc[[k for k in names if k in c.index]].sort_values("partial")
    kind = {"roll": PINE, "kyle_lambda": PINE, "spread_med": PINE, "gini": LOVE, "hhi": LOVE, "top1": LOVE, "top10": LOVE}
    q = pd.read_csv(LD + "r06/r06_conc_quintiles.csv")
    q = q[q.takers.astype(str) == "1"]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11.5, 4.6), gridspec_kw=dict(width_ratios=[1.25, 1]))
    y = np.arange(len(c))
    a1.barh(y, c.partial, color=[kind.get(k, MUTED) for k in c.index], height=0.62)
    a1.set_yticks(y, [names[k] for k in c.index], fontsize=9)
    a1.axvline(0, color=TEXT, lw=1)
    a1.grid(axis="y", visible=False)
    a1.grid(axis="x", visible=True)
    a1.set_xlabel("rank correlation with how often one trader makes a price jump\n(controlling for market size)", fontsize=9)
    a1.set_title("How OFTEN: thin books (pine), not concentration (love)", fontsize=11)
    for meas, col, lab in (("kyle_lambda", PINE, "price impact per $"), ("gini", LOVE, "Gini of $ per wallet"),
                           ("log_takers", MUTED, "number of traders")):
        s = q[q.measure == meas].sort_values("quintile")
        a2.plot(s.quintile, s.overshoot * 100, "o-", color=col, lw=2.2, label=lab)
    a2.set_xticks([1, 2, 3, 4, 5], ["lowest", "2", "3", "4", "highest"])
    a2.set_ylim(0, 60)
    pct(a2)
    a2.set_xlabel("fifth of markets on the measure")
    a2.set_ylabel("overshoot of one-trader jumps")
    a2.legend(fontsize=9, loc="lower right")
    a2.set_title("How FAR: about 40% everywhere", fontsize=11)
    save(fig, "f6_structure")


def f6_tags():
    t = pd.read_csv(LD + "r06/r06_conc_tags.csv")
    fig, ax = plt.subplots(figsize=(7.5, 5))
    ax.scatter(t.kyle_lambda, t.rate1, s=np.sqrt(t.markets) * 2.5, color=PINE, alpha=0.5, lw=0.5, edgecolor=BASE)
    for tag in ("mention-markets", "netflix", "earnings", "equities", "premier-league", "world-elections"):
        r = t[t.tag == tag]
        if len(r):
            off = {"world-elections": (5, 10), "premier-league": (-70, 8), "netflix": (6, -12)}.get(tag, (5, 2))
            ax.annotate(tag, (r.kyle_lambda.iloc[0], r.rate1.iloc[0]), xytext=off, textcoords="offset points",
                        fontsize=8.5, color=TEXT)
    ax.set_xscale("log")
    ax.set_xlabel("median price impact per $1k in the tag (log scale)")
    ax.set_ylabel("one-trader price jumps per 100 slots with trades")
    rho = t[["kyle_lambda", "rate1"]].rank().corr().iloc[0, 1]
    ax.set_title(f"Across {len(t)} tags: easy-to-push markets get lone pushes (rank corr. {rho:+.2f})", fontsize=11)
    save(fig, "f6_tags")


# ---------------------------------------------------------------- F7

def f8_close_next():
    r = pd.read_csv(LD + "r05/r05_ud_raw_len.csv")
    r = r[r.moves >= 1000]
    order = {"5M": "5-min", "15M": "15-min", "1H": "1-hour"}
    r = r.assign(lab=[f"{order[d]} markets, {CX_TG_LABEL[str(t)]}" for d, t in zip(r.dur, r.takers)])
    fig, ax = plt.subplots(figsize=(8.5, 4.6))
    y = np.arange(len(r))[::-1]
    for yi, (_, s) in zip(y, r.iterrows()):
        ax.annotate("", xy=(s.next * 100, yi), xytext=(s.close * 100, yi),
                    arrowprops=dict(arrowstyle="->", color=MUTED, lw=1.5))
        ax.scatter(s.close * 100, yi, s=70, color=CX_TG[str(s.takers)], zorder=3)
        ax.scatter(s.next * 100, yi, s=60, marker="D", color=SUBTLE, zorder=3)
    ax.scatter([], [], s=70, color=MUTED, label=f"at the end of the {CX_SLOT}-second slot (colour = traders)")
    ax.scatter([], [], s=60, marker="D", color=SUBTLE, label="at the next trades (1-2 s later for crowds)")
    ax.axvline(0, color=TEXT, lw=1)
    ax.set_yticks(y, r.lab, fontsize=9)
    pct(ax, "x")
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", visible=True)
    ax.set_xlabel("overshoot, % of the jump (negative = the price kept going)")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=2, fontsize=8.5)
    ax.set_title("Crypto up/down: within the slot crowds run on,\nbut the next trades have already caught up")
    save(fig, "f8_close-vs-next")


def f8_confirmation():
    c = pd.read_csv(LD + "r05/r05_ud_confirm.csv")
    c = c[c["related market"] == "other coin, same length"]
    order = ["moved against", "did not move", "moved with it"]
    labels = ["other coin's market\nmoved the other way", "other coin's market\ndid not move", "other coin's market\nmoved the same way"]
    fig, ax = plt.subplots(figsize=(8, 4.6))
    x = np.arange(3)
    for k, tg in enumerate(CX_TGS):
        s = c[c.takers.astype(str) == tg].set_index("it").loc[order]
        ax.errorbar(x + (k - 1) * 0.06, s.close * 100, yerr=[(s.close - s.lo) * 100, (s.hi - s.close) * 100],
                    fmt="o-", color=CX_TG[tg], lw=2.2, ms=8, capsize=0, label=f"{CX_TG_LABEL[tg]}, end of the minute")
    s = c[c.takers.astype(str) == CX_CROWD].set_index("it").loc[order]
    ax.plot(x, s["next trades"] * 100, "D--", color=SUBTLE, lw=1.5, label=f"{CX_TG_LABEL[CX_CROWD]}, next trades")
    ax.axhline(0, color=TEXT, lw=1)
    ax.set_xticks(x, labels)
    pct(ax)
    ax.set_ylabel("overshoot, % del salto")
    ax.legend(fontsize=8.5, loc="upper right")
    ax.set_title("Confirmed by the other coin: the jump keeps going; contradicted: it reverses", fontsize=11)
    save(fig, "f8_confirmation")


# ---------------------------------------------------------------- sports

def sp_groups():
    t = pd.read_csv(LD + "r07/sports_cat_tg.csv")
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.4), sharey=True)
    for ax, cat in zip(axes, ("sports", "esports")):
        s = t[t.cat == cat].set_index("tg").loc[list(TGS)]
        x = np.arange(3)
        ax.bar(x, s.overshoot * 100, 0.55, color=[TG[k] for k in TGS], label=f"at the end of the {SLOT} minutes")
        ax.errorbar(x, s.overshoot * 100, yerr=[(s.overshoot - s.lo) * 100, (s.hi - s.overshoot) * 100],
                    fmt="none", ecolor=TEXT, lw=1)
        ax.scatter(x, s.next_trades * 100, marker="D", s=60, color=SUBTLE, zorder=3, label="at the next trades")
        for i, (n, dl) in enumerate(zip(s.moves, s.median_delay_s)):
            ax.text(i, -4, f"{n / 1000:.0f}k jumps\nnext trades\n~{dl / 60:.0f} min later" if dl >= 90 else
                    f"{n / 1000:.0f}k jumps\nnext trades\n~{dl:.0f} s later", ha="center", va="top", fontsize=8, color=SUBTLE)
        ax.axhline(0, color=TEXT, lw=1)
        ax.set_xticks(x, [TG_LABEL[k] for k in TGS])
        ax.set_title(cat.capitalize(), fontsize=11)
        ax.set_ylim(-20, 50)
        pct(ax)
    axes[0].set_ylabel("overshoot, % del salto")
    axes[1].legend(loc="upper right", fontsize=8.5)
    fig.suptitle("Sports and esports: the same pattern as every other market",
                 fontweight="bold", color=TEXT)
    save(fig, "sp_groups")


def sp_sport():
    t = pd.read_csv(LD + "r07/sports_sport.csv")
    t = t[(t.sport != "other") & (t.moves >= 1500)].sort_values("overshoot")
    fig, ax = plt.subplots(figsize=(8, 5))
    y = np.arange(len(t))
    ax.barh(y + 0.18, t.overshoot * 100, 0.34, color=MUTED, label=f"end of the {SLOT} minutes")
    ax.barh(y - 0.18, t.next_trades * 100, 0.34, color=FOAM, label="next trades")
    ax.set_yticks(y, [f"{s}  ({n / 1000:.0f}k)" for s, n in zip(t.sport, t.moves)], fontsize=9)
    ax.axvline(0, color=TEXT, lw=1)
    pct(ax, "x")
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", visible=True)
    ax.set_xlabel("overshoot, % of the jump (all traders; price jumps in brackets)")
    ax.legend(fontsize=8.5, loc="lower right")
    ax.set_title("By sport: overshoot at the close, and what is left at the next trades", fontsize=11)
    save(fig, "sp_sport")


# ---------------------------------------------------------------- F10

def f10_reaction():
    r = pd.read_csv(LD + "r10_reaction.csv", index_col=[0, 1], dtype={"Unnamed: 1": str})
    r.index = r.index.set_levels([r.index.levels[0], r.index.levels[1].astype(str)])
    reac = ["reversed it fully", "gave back over half", "kept over half", "went further"]
    v = {tg: [r.loc[(k, tg), "close"] for k in reac] for tg in TGS}
    lo = {tg: [r.loc[(k, tg), "close_lo"] for k in reac] for tg in TGS}
    hi = {tg: [r.loc[(k, tg), "close_hi"] for k in reac] for tg in TGS}
    shares = r.groupby(level=0).jumps.sum() / r.jumps.sum()
    fig, ax = plt.subplots(figsize=(9, 4.6))
    x = np.arange(len(reac))
    bars_tg(ax, x, v, lo, hi)
    ax.axhline(0, color=SUBTLE, lw=1)
    ax.axhline(100, color=SUBTLE, lw=0.8, ls=":")
    ax.text(x[-1] + 0.45, 101.5, "the whole jump was unjustified", ha="right", fontsize=8.5, color=SUBTLE)
    ax.text(x[-1] + 0.45, 1.5, "the jump was right", ha="right", fontsize=8.5, color=SUBTLE)
    ax.set_xticks(x, [f"{k}\n({shares[k]:.0%} of jumps)" for k in reac])
    ax.set_xlabel("what the next trades (within the hour) did to the jump")
    ax.set_ylim(-25, 135)
    pct(ax)
    ax.set_ylabel("overshoot at the close, % of the jump")
    ax.legend(loc="upper right", fontsize=9)
    ax.set_title("The next trades show whether a jump was sensible, whoever made it")
    save(fig, "f10_reaction")


# ---------------------------------------------------------------- round 11: parameters, traders

def count_colours(labels):
    def group(k):
        n = int(k.split("-")[0].split(" ")[0]) if k[0].isdigit() else 10 ** 6
        return TG["1"] if n == 1 else TG[FEW] if n < K_CROWD else TG[CROWD]
    return [group(k) for k in labels]


KIND_TEXT = {"knee": "ginocchio = {:g}", "edge": "ginocchio al bordo: {:g}", "flat": "piatta (nessun effetto): {}",
             "peak": "picco (nessun ginocchio): {}", "valley": "punto più basso = {:g}", "straight": "retta (nessun ginocchio): {}",
             "knee before the valley": "ginocchio = {:g} (prima che la curva risalga)",
             "knee before the peak": "ginocchio = {:g} (prima che la curva scenda)"}


def elbow_panel(ax, x, y, k, title, xlabel, ylabel, ypct=False, logx=False, kind="knee", used=None):
    """One parameter's curve with the value used, marked by a circle and a line; a curve without a
    proper knee (elbow.find) says so, with the value kept (`used`: a number, or "dropped")."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    if used == "dropped":
        label, k = KIND_TEXT[kind].format("eliminato"), None
    elif used is not None:
        label, k = KIND_TEXT[kind].format(f"{used:g} mantenuto"), used
    else:
        label = KIND_TEXT[kind].format(k if kind.startswith("knee") or kind in ("edge", "valley") else f"{k:g} mantenuto")
    ax.plot(x, y, "-", color=IRIS, lw=2)
    ax.plot(x, y, "o", color=IRIS, ms=3.2)
    if k is not None:
        ky = y[np.argmin(np.abs(x - k))]
        ax.plot([k], [ky], "o", ms=11, mfc="none", mec=ROSE if kind.startswith("knee") or kind in ("edge", "valley") else MUTED, mew=2.2)
        ax.axvline(k, color=TEXT, lw=1, ls="--")
    rising = y[-1] > y[0]
    label = it(label)
    ax.text(0.97, 0.05 if rising else 0.95, label, transform=ax.transAxes, ha="right",
            va="bottom" if rising else "top", fontsize=8.5, color=TEXT,
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
DEFINITION = [  # curve, title, x label, y label, y scale, y in %
    ("slot", "Durata dello slot", "minuti", JUMPS_K, 1e-3, False),
    ("theta", "Soglia del salto", "punti", JUMPS_K, 1e-3, False),
    ("cut_start", "Taglio all'inizio della vita", "% della vita", JUMPS_K, 1e-3, False),
    ("cut_end", "Taglio alla fine della vita", "% della vita", JUMPS_K, 1e-3, False),
    ("edge", "Banda di chiusura", "punti da 0% o 100%", JUMPS_K, 1e-3, False),
    ("clip", "Limite dei prezzi", "punti da 0% o 100%", JUMPS_K, 1e-3, False),
    ("n_next", "Trade successivi: quanti", "trade nella media", "overshoot ai trade successivi", 1, True),
    ("t_next", "Trade successivi: entro quanto", "minuti concessi", "salti con trade successivi", 100, True),
]


def definition_panels(mode, name, title):
    c = pd.read_csv(LD + f"r12/full/{mode}_curves.csv")
    fig, axes = plt.subplots(2, 4, figsize=(14, 6.6))
    for ax, (cv, t, xl, yl, ys, yp) in zip(axes.flat, DEFINITION):
        d = c[c.curve == cv]
        kind = d.kind.iloc[0]
        elbow_panel(ax, d.x, d.y * ys, d.knee.iloc[0], t, xl, yl, yp, kind=kind,
                    used="dropped" if kind == "flat" and d.knee.iloc[0] == 0 else None)
    fig.suptitle(title, fontsize=13, weight="bold", color=TEXT)
    save(fig, name)


def m_definition():
    definition_panels("events", "m_definition", "Che cos'è un salto di prezzo: ogni parametro dalla sua curva, "
                      "gli altri ai loro valori")


def m_crypto():
    definition_panels("cx", "m_crypto", "Crypto up/down markets: the same search")


def m_grid():
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.8))
    for ax, (f, row, col, rl, cl) in zip(axes, (("slot_theta", "slot", "theta", "slot length, minutes", "jump threshold, points"),
                                               ("cut_edge", "edge", "cut_end", "settle band, points", "cut at the end, % of life"))):
        g = pd.read_csv(LD + f"r12/full/events_grid_{f}.csv")
        m = g.pivot(index=row, columns=col, values="jumps")
        rv = g.pivot(index=row, columns=col, values="reversal") if "reversal" in g else m   # slot: reversal share
        im = ax.imshow(np.log10(m.values), aspect="auto", origin="lower", cmap="Purples",
                       extent=[-0.5, m.shape[1] - 0.5, -0.5, m.shape[0] - 0.5])
        kc, kr = [], []
        for i, (_, r) in enumerate(m.iterrows()):          # knee of each row: the best column for that row
            kc.append(knee_idx(m.columns.values, r.values))
        for j in range(m.shape[1]):                         # knee of each column: the best row for that column
            kr.append(knee_idx(m.index.values, rv.iloc[:, j].values))
        ax.plot(kc, np.arange(m.shape[0]), "o-", color=ROSE, lw=1.8, ms=4, label=f"knee of {cl.split(',')[0]} for each row")
        ax.plot(np.arange(m.shape[1]), kr, "s--", color=PINE, lw=1.4, ms=3,
                label=f"knee of {rl.split(',')[0]} for each column" + (" (reversal share)" if row == "slot" else ""))
        step = max(1, m.shape[1] // 8)
        ax.set_xticks(np.arange(0, m.shape[1], step), [f"{v:g}" for v in m.columns.values[::step]], fontsize=8)
        ax.set_yticks(np.arange(m.shape[0]), [f"{v:g}" for v in m.index.values], fontsize=8)
        ax.set_xlabel(cl, fontsize=9)
        ax.set_ylabel(rl, fontsize=9)
        ax.grid(False)
        ax.legend(fontsize=7.5, loc="upper right")
        fig.colorbar(im, ax=ax, label="price jumps (log10)", shrink=0.85)
    fig.suptitle("Parameters that depend on each other: the knee of one barely moves with the other",
                 fontsize=12, weight="bold", color=TEXT)
    save(fig, "m_grid")


def knee_idx(x, y):
    from elbow import find
    return find(np.asarray(x, float), np.asarray(y, float))[0]


PARAMS = [  # curve, title, x label, y label, y in %, log x (display only: every knee is found on a linear axis)
    ("outcome", "Resolved: final price beyond Q", "Q", "markets", False, False),
    ("sample", "Random sample for the baseline", "% of slots", "spread of the overshoot, points", False, False),
    ("resamples", "Resamples for the ranges", "resamples", "spread of the range, points", False, False),
    ("bins", "Price bins of the baseline", "bins", "calibration error explained", False, False),
    ("crowd", "Crowd: at least K traders", "K", "overshoot", True, False),
    ("money", "Big money: at least $X", "$ in the slot", "overshoot", True, True),
    ("wallet_min", "F2: wallets with at least m lone jumps", "m", "wallets", False, False),
    ("control_bins", "F2: bins of each control", "bins", "crowd gap, all else fixed", False, False),
    ("offset_lo", "F4: 'not offset' below", "offset", "crowd overshoot", True, False),
    ("offset_hi", "F4: 'offset' from", "offset", "crowd overshoot", True, False),
    ("band", "F5: bets inside [e, 1 - e]", "e, points", "spread of returns", False, False),
    ("trim", "F5: share trimmed at each end", "%", "trimmed mean, cents per $", False, False),
    ("min_slots", "F6: markets with at least n slots", "n", "markets", False, False),
    ("kyle_gap", "F6: Kyle's lambda, slots at most g apart", "hours", "pairs of slots kept, %", False, False),
    ("vr_lag", "F6: variance ratio lag", "slots", "median variance ratio", False, False),
    ("spread_win", "F6: buy-sell window", "seconds", "windows with both sides", False, False),
    ("tag_min", "F6: tags with at least n markets", "n", "tags", False, False),
    ("tag_min_jumps", "F1: tags with at least n markets with jumps", "n", "tags", False, False),
    ("moved", "F8: related market moved", "log-odds", "moved, %", False, False),
    ("cx_crowd", "F8: crypto crowd, at least K traders", "K", "overshoot", True, False),
    ("cx_bins", "F8: crypto baseline bins", "bins", "calibration error explained", False, False),
    ("cx_resamples", "F8: crypto resamples", "resamples", "spread of the range, points", False, False),
    ("cx_outcome", "F8: crypto resolved beyond Q", "Q", "markets", False, False),
    ("follow_up", "F10: a trade within x minutes", "minutes", "overshoot", True, False),
    ("step", "F9: minutes between path points", "minutes", "error of the path, points", False, False),
    ("before", "F9: path start before the close", "minutes", "distance from the close, points", False, False),
    ("after", "F9: path end after the close", "minutes", "distance from the close, points", False, False),
    ("changes", "F9: price changes in the path", "at least", "paths kept", False, False),
    ("hours", "F9: hours of window left", "at least", "paths running into the settle band, %", False, False),
    ("radius", "F9: match radius percentile", "percentile", "surrogate profile", False, False),
    ("cx_points", "F9: points per crypto market", "points", "error, points", False, False),
    ("cx_min_trades", "F9: crypto markets with at least n trades", "n", "markets", False, False),
]
USED = {"band": "dropped", "cx_min_trades": "dropped", "control_bins": CONTROL_BINS, "moved": CX_MOVED}   # no knee


def m_params():
    c = pd.read_csv(LD + "r12/params_curves_all.csv")
    kk = pd.read_csv(LD + "r12/params_knees_all.csv").set_index("curve")
    kn = kk.knee
    todo = [p for p in PARAMS if p[0] in kn.index]
    rows = int(np.ceil(len(todo) / 4))
    fig, axes = plt.subplots(rows, 4, figsize=(14, 3.0 * rows))
    for ax, (cv, t, xl, yl, yp, lg) in zip(axes.flat, todo):
        d = c[c.curve == cv]
        elbow_panel(ax, d.x, d.y, kn[cv], t, xl, yl, yp, lg, kind=kk.kind[cv], used=USED.get(cv))
    for ax in axes.flat[len(todo):]:
        ax.axis("off")
    fig.suptitle("Every other parameter, from its curve", fontsize=13, weight="bold", color=TEXT)
    fig.tight_layout(rect=(0, 0, 1, 0.985))      # room for the title (save() would undo it)
    fig.savefig(OUT + "m_params.png")
    plt.close(fig)


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
    save(fig, "f2_trader-counts")


def f3_giveback():
    g = pd.read_csv(LD + "r11_giveback.csv", index_col=0)["next trades"] * 100
    lab = ["< -50"] + [f"{int(round(float(i.split('..')[0]) * 100))}" for i in g.index[1:-1]] + ["> 150"]
    fig, ax = plt.subplots(figsize=(10, 4.3))
    x = np.arange(len(g))
    ax.bar(x, g.values, 0.85, color=TG["1"])
    zero, full = lab.index("0"), lab.index("100")
    ax.axvline(zero - 0.5, color=SUBTLE, lw=1, ls=":")
    ax.axvline(full - 0.5, color=SUBTLE, lw=1, ls=":")
    top = g.max() * 1.05
    ax.text(zero - 0.7, top, "the next trades\nwent further", ha="right", va="top", fontsize=8.5, color=SUBTLE)
    ax.text(full - 0.3, top, "gave back all of it\nor more", ha="left", va="top", fontsize=8.5, color=SUBTLE)
    ax.set_xticks(x, lab, fontsize=8, rotation=0)
    ax.set_xlabel("share of the jump the next trades gave back, % (each bar: 10 points, e.g. '20' = 20-30%)")
    pct(ax)
    ax.set_ylabel("share of single-trader jumps")
    ax.set_title("Single-trader jumps: how much the next trades gave back")
    save(fig, "f3_giveback")


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
    ax.text(104, top * 0.45, "hanno restituito tutto\nil salto o di più", ha="left", va="top", fontsize=8.5, color=SUBTLE)
    ax.set_xlim(-100, 200)
    ax.set_ylim(0, top * 1.05)
    pct(ax, "x")
    ax.set_xlabel("quota del salto restituita dai trade successivi")
    ax.set_ylabel("% dei salti di un trader singolo\nper punto restituito")
    ax.set_title("Salti di un trader singolo: quanto restituiscono i trade successivi (curva smussata)")
    save(fig, "f3_giveback-curve")


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


ALL = {"ex1": ex1_example, "ex2": ex2_overshoot, "spikes": bg_spikes, "pipeline": bg_pipeline,
       "f1_hero": f1_hero, "f1_splits": f1_splits, "f1_tags": f1_tags,
       "f2_traders": f2_traders, "f2_money": f2_money, "f2_robustness": f2_robustness,
       "f2_controlled": f2_controlled, "f2_wallets": f2_wallets, "f3": f3_decay,
       "f5": f5_fade, "f6": f6_structure, "f6_tags": f6_tags, "f8": f8_close_next, "f8_conf": f8_confirmation,
       "sp_groups": sp_groups, "sp_sport": sp_sport, "f4_versions": f4_versions,
       "f10_reaction": f10_reaction, "m_definition": m_definition,
       "m_crypto": m_crypto, "m_grid": m_grid, "m_params": m_params, "f2_counts": f2_counts,
       "f3_giveback": f3_giveback, "f3_giveback_curve": f3_giveback_curve, "f2_accuracy": f2_accuracy}


def main(names):
    os.makedirs(OUT, exist_ok=True)
    names = names or list(ALL) + ["paths"]
    for n in names:
        if n == "paths":
            d, P = paths()
            f2_two_moves(d, P)
        else:
            ALL[n]()


if __name__ == "__main__":
    main(sys.argv[1:])
