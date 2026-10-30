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
from r02_persistence import BAR, LIFE_CUT, share  # noqa: E402

OUT = "report/plots/"
LD = "local_data/"
TGS = ("1", "2-3", "4+")
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
    # the 30-minute slots the price jumps are found on (as remote/s2_events.py): dollar-weighted
    # average price of the slot's trades, stamped at the slot's end
    s = s.assign(bar=s.ts // BAR, pv=s.yes * s.usd_amount)
    g = s.groupby("bar").agg(pv=("pv", "sum"), usd=("usd_amount", "sum"), last=("yes", "last"))
    g["vwap"] = (g.pv / g.usd.where(g.usd > 0)).fillna(g["last"])
    g["t"] = pd.to_datetime((g.index + 1) * BAR, unit="s")
    return g.reset_index(drop=True)


NEWS = [("2025-02-13 17:00", "13 Feb: Tim Cook teases\n\"the newest member\nof the family\""),
        ("2025-02-17 12:00", "16-17 Feb: reports that\nthe phone gets\na new name"),
        ("2025-02-19 16:00", "19 Feb: Apple\nannounces\nthe iPhone 16e")]


def ex1_example():
    """The example market: the average price of every 30-minute slot with trades, with its
    price jumps (from one slot to the next) in the accent colour and the news dates."""
    s, b = example_data()
    bars = example_bars(s)
    fig, ax = plt.subplots(figsize=(9.5, 4.6))
    ax.plot(bars.t, bars.vwap, color=HL_MED, lw=0.8, zorder=1)
    ax.scatter(bars.t, bars.vwap, s=14, color=IRIS, lw=0, zorder=2,
               label="30-minute average price (one dot per 30 minutes with trades)")
    bars["t0"], bars["v0"] = bars.t.shift(), bars.vwap.shift()
    for r in b.merge(bars[["t", "t0", "v0"]], on="t").itertuples():
        ax.plot([r.t0, r.t], [r.v0, r.p_close * 100], color=LOVE, lw=2.4, zorder=3)
        ax.scatter([r.t], [r.p_close * 100], s=30, color=LOVE, lw=0, zorder=4)
    ax.plot([], [], color=LOVE, lw=2.4, marker="o", ms=5, label="price jumps")
    # the window kept (as remote/s2_events.window): the first and last LIFE_CUT of the life, which
    # runs from the first slot to the last slot inside 5-95% (the market ends outside it)
    inside = bars["last"].between(5, 95)
    t0, t1 = bars.t.iloc[0], bars.t[inside].iloc[-1]
    pad = (t1 - t0) * LIFE_CUT
    for a, z in ((t0 - pd.Timedelta(hours=3), t0 + pad), (t1 - pad, bars.t.iloc[-1] + pd.Timedelta(hours=3))):
        ax.axvspan(a, z, color=HL_MED, alpha=0.6, lw=0, zorder=0)
    ax.fill_between([], [], color=HL_MED, alpha=0.6, label=f"left out: first and last {LIFE_CUT:.0%} of the market's life")
    for t, txt in NEWS:
        t = pd.Timestamp(t)
        ax.axvline(t, color=SUBTLE, lw=0.8, ls=":", zorder=0)
        ax.text(t + pd.Timedelta(hours=1.5), 97, txt, va="top", fontsize=8, color=SUBTLE)
    ax.set_xlim(t0 - pd.Timedelta(hours=3), bars.t.iloc[-1] + pd.Timedelta(hours=3))
    ax.set_ylim(0, 100)
    pct(ax)
    date_axis(ax)
    ax.legend(loc="lower right", fontsize=8.5)
    ax.set_ylabel("price of YES")
    ax.set_title(f"\"Will Apple launch another iPhone on February 19?\" (2025): {len(b)} price jumps, resolved YES",
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
            f"price jump: {pre:.0f}% → {post:.0f}%\n(30-minute averages; no news found)", fontsize=9, color=LOVE)
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
    ax.set_ylabel("price of YES")
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
             ("30-min slots\nper market\n(price, $, traders)", IRIS),
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
    rnd = pd.concat([pd.read_parquet(f) for f in glob.glob(LD + "r03_events/1800/r*.parquet")], ignore_index=True)
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
    ax.plot(mid, rr.values, color=MUTED, lw=2, label="at random moments (the usual bias)")
    for sgn, c, lab in ((1, UP, "right after an UP jump"), (-1, DOWN, "right after a DOWN jump")):
        x = b[b.sgn == sgn]
        g = x.groupby(pd.cut(x.p_close, bins), observed=False).agg(y=("outcome", "mean"), n=("outcome", "size"))
        ok = (g.n >= 300).values
        ax.plot(mid[ok], g.y.values[ok] * 100, "o-", color=c, lw=2, ms=7, label=lab)
    i = 5                                                       # annotate the 55-65% bin
    up = b[(b.sgn > 0) & b.p_close.between(bins[i], bins[i + 1])].outcome.mean() * 100
    dn = b[(b.sgn < 0) & b.p_close.between(bins[i], bins[i + 1])].outcome.mean() * 100
    ax.annotate(f"jumped UP to ~60%:\nYES won only {up:.0f}% of the time", xy=(mid[i], up), xytext=(64, 22),
                fontsize=9, color=TEXT, arrowprops=dict(arrowstyle="-", color=UP, lw=0.8))
    ax.annotate(f"fell DOWN to ~60%:\nYES won {dn:.0f}% of the time", xy=(mid[i], dn), xytext=(18, 76),
                fontsize=9, color=TEXT, arrowprops=dict(arrowstyle="-", color=DOWN, lw=0.8))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    pct(ax)
    pct(ax, "x")
    ax.set_xlabel("price of YES right after the jump (or at a random moment)")
    ax.set_ylabel("how often YES actually won")
    ax.set_title("After a jump, the price is too far in the jump's direction")
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
        ax.set_xlabel("overshoot, % of the jump")
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
    ax.set_ylabel("overshoot, % of the jump")
    ax.set_title("The more traders behind a jump, the less it overshoots")
    save(fig, "f2_traders")


def f2_money():
    b = pd.read_parquet(LD + "r02_big_moves.parquet")
    b = b.assign(tg=pd.cut(b.takers, [0, 1, 3, np.inf], labels=list(TGS)),
                 ug=pd.cut(b.usd, [0, 50, 500, np.inf], labels=["under $50", "$50-500", "over $500"]))
    v, lo, hi = {}, {}, {}
    for tg, s in b.groupby("tg", observed=True):
        r = [share(c, n_boot=150) for _, c in s.groupby("ug", observed=False)]
        v[tg], lo[tg], hi[tg] = [a[0] for a in r], [a[1] for a in r], [a[2] for a in r]
    fig, ax = plt.subplots(figsize=(7.5, 4.3))
    bars_tg(ax, np.arange(3), v, lo, hi)
    ax.set_xticks(np.arange(3), ["under $50", "$50-500", "over $500"])
    ax.set_xlabel("money traded in the jump's 30 minutes")
    ax.set_ylabel("overshoot, % of the jump")
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
        ax.set_xticks(np.arange(3), [f"≥ {t * 100:.0f} points" for t in s.threshold], fontsize=9)
        ax.set_title(f"{bm}-minute slots", fontsize=11)
        ax.set_xlabel("minimum jump to count as a price jump", fontsize=9)
        pct(ax)
    axes[0].set_ylabel("overshoot, % of the jump")
    axes[0].set_ylim(0, 56)
    axes[2].legend(*axes[0].get_legend_handles_labels(), loc="upper right", ncol=3, fontsize=8, columnspacing=0.8)
    fig.suptitle("Same ordering for every way of defining a price jump", fontweight="bold", color=TEXT)
    save(fig, "f2_robustness")


def f2_controlled():
    f = pd.read_csv(LD + "r05/r05_factor_effects.csv")
    f = f[f.factor == "takers"].set_index("level")
    t = pd.read_parquet(LD + "r04_tradable.parquet")
    t = t[t.oq.notna()]
    raw = t.groupby("tg", observed=True).apply(lambda x: x.oq.sum() / x.absdp.sum())
    fig, ax = plt.subplots(figsize=(7, 3.8))
    y = np.array([1, 0])
    for i, tg in enumerate(("2-3", "4+")):
        gap = (raw[tg] - raw["1"]) * 100
        ax.barh(y[i] + 0.18, gap, 0.32, color=MUTED, label="raw difference" if i == 0 else None)
        e = f.loc[tg]
        ax.barh(y[i] - 0.18, e.effect * 100, 0.32, color=TG[tg],
                label="with every other factor held fixed" if i == 0 else None)
        ax.errorbar(e.effect * 100, y[i] - 0.18, xerr=[[(e.effect - e.lo) * 100], [(e.hi - e.effect) * 100]],
                    fmt="none", ecolor=TEXT, lw=1)
        ax.text(-0.6, y[i] + 0.18, f"{gap:.0f}", va="center", ha="right", fontsize=9, color=BASE, weight="bold")
        ax.text(-0.6, y[i] - 0.18, f"{e.effect * 100:.0f}", va="center", ha="right", fontsize=9, color=BASE, weight="bold")
    ax.set_yticks(y, ["2-3 traders\nvs 1 trader", "4+ traders\nvs 1 trader"])
    ax.axvline(0, color=TEXT, lw=1)
    ax.set_xlim(-30, 2)
    ax.set_xlabel("difference in overshoot, percentage points of the jump")
    ax.legend(loc="upper left", fontsize=9)
    ax.grid(axis="y", visible=False)
    ax.set_title("Holding category, money, price, timing, year... fixed\nbarely changes the gap")
    save(fig, "f2_controlled")
    print(f"f2_controlled raw gaps: 2-3 {(raw['2-3'] - raw['1']) * 100:.1f}, 4+ {(raw['4+'] - raw['1']) * 100:.1f}")


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
    x = (np.arange(P.shape[1]) - 7) * 5
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.axvspan(-BAR // 60, 0, color=HL_MED, alpha=0.6, lw=0)
    busy = d.entry_delay.values <= 600
    for tg in TGS:
        s = (d.tg.values == tg) & busy
        kept = (d.sgn.values[s, None] * (P[s] - d.y_pre.values[s, None])).sum(0) / d.absdp.values[s].sum() * 100
        fair = 100 - d.oc.values[s].sum() / d.absdp.values[s].sum() * 100
        ax.plot(x, kept, color=TG[tg], lw=2.4, label=f"{TG_LABEL[tg]} ({s.sum():,} jumps)")
        ax.plot([x[-1] + 6, x[-1] + 16], [fair, fair], color=TG[tg], lw=4, solid_capstyle="butt")
        print(f"f2_average {tg}: close {kept[7]:.0f} +10min {kept[9]:.0f} +4h {kept[-1]:.0f} fair {fair:.0f}")
    ax.text(x[-1] + 11, 112, "outcome\njustifies", ha="center", fontsize=8, color=SUBTLE)
    ax.axhline(0, color=SUBTLE, lw=1)
    ax.axhline(100, color=SUBTLE, lw=0.8, ls=":")
    ax.set_xlim(x[0], x[-1] + 20)
    ax.set_ylim(-10, 125)
    pct(ax)
    ax.set_xlabel("minutes from the end of the jump's 30-minute slot")
    ax.set_ylabel("share of the jump still in the price")
    ax.set_title("The average price jump (markets that traded again within 10 minutes)")
    ax.legend(loc="lower right", bbox_to_anchor=(0.88, 0.06), fontsize=9)
    save(fig, "f2_average-move")


def f2_two_moves(d, P):
    x = (np.arange(P.shape[1]) - 7) * 5
    picks = [(518038, 1737451800, "One trader, $244: undone within two minutes",
              "Will Aryna Sabalenka win the Australian Open?\n21 Jan 2025, 09:30 UTC", TG["1"]),
             (1006468, 1769765400, "88 traders, $27.4k: the jump held",
              "Will Carlos Alcaraz win the 2026 Australian Open?\n30 Jan 2026, 09:30 UTC", TG["4+"])]
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
    axes[0].set_ylabel("price of YES (5-min average)")
    save(fig, "f2_two-moves")


# ---------------------------------------------------------------- F3

def f3_decay():
    c = pd.read_csv(LD + "r03_curves_catbase.csv", index_col=[0, 1]).loc["tg"]
    cols = ["close", "next trades", "1h", "6h", "24h"]
    labels = ["bar close", "next trades\n(minutes later)", "+1 hour", "+6 hours", "+24 hours"]
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
    ax.set_ylabel("overshoot still in the price, % of the jump")
    ax.legend(fontsize=9)
    ax.set_title("A lone trader's overshoot vanishes at the next trades;\na crowd's fades over hours")
    save(fig, "f3_decay")


# ---------------------------------------------------------------- F4

def f4_versions():
    """F4: overshoot by what the other candidates did in the move's 30 minutes (neg-risk events),
    at the close and at the next trades."""
    r = pd.read_csv(LD + "r07/sib_versions.csv")
    r = r[r.neg_risk == 1]
    groups = ["isolated", "not offset", "partly offset", "offset"]
    labels = ["no other\ncandidate traded", "others traded,\nno offset", "partly offset\n(25-75%)", "offset\n(75%+)"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), sharey=True)
    for ax, tg in zip(axes, ("1", "4+")):
        x = np.arange(4)
        s = r[(r.version == "all trades") & (r.takers.astype(str) == tg)].set_index("group").reindex(groups)
        ax.bar(x, s.close * 100, 0.55, color=TG[tg], label="at the end of the 30 minutes")
        ax.errorbar(x, s.close * 100, yerr=[(s.close - s.lo) * 100, (s.hi - s.close) * 100], fmt="none", ecolor=TEXT, lw=1)
        ax.scatter(x, s["next trades"] * 100, marker="D", s=55, color=SUBTLE, zorder=3, label="at the next trades")
        for i, n in enumerate(s.moves):
            ax.text(i, -17, f"{n:,.0f} jumps", ha="center", fontsize=8, color=SUBTLE)
        ax.axhline(0, color=TEXT, lw=1)
        ax.set_xticks(x, labels, fontsize=9)
        ax.set_title(f"jumps made by {TG_LABEL[tg]}", fontsize=11)
        pct(ax)
    axes[0].set_ylabel("overshoot, % of the jump")
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
    m = f[f.split == "money in bar"].set_index("group").loc[["<$100", "$100-1k", ">$1k"]]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10.5, 4.3), sharey=True)
    x = np.arange(3)
    for ax, d, cols, labels, title in (
            (a1, t, [TG[k] for k in TGS], [TG_LABEL[k] for k in TGS], "By who made the jump"),
            (a2, m, [IRIS] * 3, ["under $100", "$100-1k", "over $1k"], "By money behind the jump")):
        ax.bar(x, d.trimmed * 100, 0.55, color=cols)
        ax.errorbar(x, d.trimmed * 100, yerr=[(d.trimmed - d["trimmed lo"]) * 100, (d["trimmed hi"] - d.trimmed) * 100],
                    fmt="none", ecolor=TEXT, lw=1)
        ax.axhline(0, color=TEXT, lw=1)
        ax.set_xticks(x, labels)
        ax.set_title(title, fontsize=11)
        ax.set_ylim(-11, 21)
    for i, sp in enumerate(t["spread (cents)"]):
        a1.text(i, 18.5, f"spread {sp:.1f}¢", ha="center", fontsize=8.5, color=SUBTLE)
    a2.set_xlabel("money traded in the jump's 30 minutes")
    a1.set_ylabel("return per $1 bet against the jump (cents),\nafter the spread, extremes trimmed")
    fig.suptitle("Betting against price jumps: loses after lone pushes, pays after crowd and big-money jumps",
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
    r = r.assign(lab=[f"{order[d]} markets, {TG_LABEL[str(t)]}" for d, t in zip(r.dur, r.takers)])
    fig, ax = plt.subplots(figsize=(8.5, 4.6))
    y = np.arange(len(r))[::-1]
    for yi, (_, s) in zip(y, r.iterrows()):
        ax.annotate("", xy=(s.next * 100, yi), xytext=(s.close * 100, yi),
                    arrowprops=dict(arrowstyle="->", color=MUTED, lw=1.5))
        ax.scatter(s.close * 100, yi, s=70, color=TG[str(s.takers)], zorder=3)
        ax.scatter(s.next * 100, yi, s=60, marker="D", color=SUBTLE, zorder=3)
    ax.scatter([], [], s=70, color=MUTED, label="at the end of the 1-minute bar (colour = traders)")
    ax.scatter([], [], s=60, marker="D", color=SUBTLE, label="at the next trades (1-2 s later for crowds)")
    ax.axvline(0, color=TEXT, lw=1)
    ax.set_yticks(y, r.lab, fontsize=9)
    pct(ax, "x")
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", visible=True)
    ax.set_xlabel("overshoot, % of the jump (negative = the price kept going)")
    ax.legend(loc="upper left", fontsize=8.5)
    ax.set_title("Crypto up/down: within the minute crowds run on,\nbut the next trades have already caught up")
    save(fig, "f8_close-vs-next")


def f8_confirmation():
    c = pd.read_csv(LD + "r05/r05_ud_confirm.csv")
    c = c[c["related market"] == "other coin, same length"]
    order = ["moved against", "did not move", "moved with it"]
    labels = ["other coin's market\nmoved the other way", "other coin's market\ndid not move", "other coin's market\nmoved the same way"]
    fig, ax = plt.subplots(figsize=(8, 4.6))
    x = np.arange(3)
    for k, tg in enumerate(TGS):
        s = c[c.takers.astype(str) == tg].set_index("it").loc[order]
        ax.errorbar(x + (k - 1) * 0.06, s.close * 100, yerr=[(s.close - s.lo) * 100, (s.hi - s.close) * 100],
                    fmt="o-", color=TG[tg], lw=2.2, ms=8, capsize=0, label=f"{TG_LABEL[tg]}, end of the minute")
    s = c[c.takers.astype(str) == "4+"].set_index("it").loc[order]
    ax.plot(x, s["next trades"] * 100, "D--", color=SUBTLE, lw=1.5, label="4+ traders, next trades")
    ax.axhline(0, color=TEXT, lw=1)
    ax.set_xticks(x, labels)
    pct(ax)
    ax.set_ylabel("overshoot, % of the jump")
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
        ax.bar(x, s.overshoot * 100, 0.55, color=[TG[k] for k in TGS], label="at the end of the 30 minutes")
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
    axes[0].set_ylabel("overshoot, % of the jump")
    axes[1].legend(loc="upper right", fontsize=8.5)
    fig.suptitle("Sports and esports: the same pattern as every other market",
                 fontweight="bold", color=TEXT)
    save(fig, "sp_groups")


def sp_sport():
    t = pd.read_csv(LD + "r07/sports_sport.csv")
    t = t[(t.sport != "other") & (t.moves >= 1500)].sort_values("overshoot")
    fig, ax = plt.subplots(figsize=(8, 5))
    y = np.arange(len(t))
    ax.barh(y + 0.18, t.overshoot * 100, 0.34, color=MUTED, label="end of the 30 minutes")
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
    return [TG["1"] if k == "1" else TG["2-3"] if k in ("2", "3") else TG["4+"] for k in labels]


def elbow_panel(ax, c, k, now, title, xlabel, ylabel, yscale=1, ypct=False, xfmt="{:g}"):
    """One parameter's curve (local_data/r11_curves_all.csv) with its knee, the value used now
    (dashed) and, where it changed in round 11, the value used before (dotted)."""
    s = c[c.curve == k.curve]
    ax.plot(s.x, s.y * yscale, "-", color=IRIS, lw=2)
    ax.plot(s.x, s.y * yscale, "o", color=IRIS, ms=3.5)
    y = s.y * yscale
    flat = ypct and y.max() - y.min() < 1          # under a point over the whole range: no knee
    if not flat:
        ky = s.loc[s.x == k.knee, "y"].iloc[0] * yscale
        ax.plot([k.knee], [ky], "o", ms=11, mfc="none", mec=ROSE, mew=2.2)
    ax.axvline(now, color=TEXT, lw=1.1, ls="--")
    if now != k.chosen:
        ax.axvline(k.chosen, color=MUTED, lw=1.1, ls=":")
    f = xfmt.format
    lab = "flat: under 1 point" if flat else f"knee {f(k.knee)}"
    lab += f"\nused {f(now)}" + (f" (was {f(k.chosen)})" if now != k.chosen else "")
    rising = y.iloc[-1] > y.iloc[0]
    ax.text(0.97, 0.05 if rising else 0.95, lab, transform=ax.transAxes, ha="right", va="bottom" if rising else "top",
            fontsize=8.5, color=TEXT, bbox=dict(boxstyle="round,pad=0.25", fc=BASE, ec="none", alpha=0.9))
    ax.set_title(title, fontsize=10)
    ax.set_xlabel(xlabel, fontsize=8.5)
    ax.set_ylabel(ylabel, fontsize=8.5)
    ax.tick_params(labelsize=8)
    if ypct:
        if y.max() - y.min() < 4:          # a flat result: show it on a 6-point scale, not zoomed in
            mid = (y.max() + y.min()) / 2
            ax.set_ylim(mid - 3, mid + 3)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0f}%"))
        ax.yaxis.set_major_locator(plt.MaxNLocator(5, integer=True))


# values used after round 11, where they changed (the knees file keeps the old ones as `chosen`)
NOW = {"threshold": 13, "threshold_os": 13, "cut_start": 5, "cut_start_os": 5, "cut_end": 5,
       "cut_end_os": 5, "slot": 30, "slot_os": 30, "next_n": 8}
JUMPS_K, OS_PCT = "price jumps (thousands)", "overshoot, % of the jump"
ELBOWS = [  # curve, title, x label, y label, y scale, y in %
    ("threshold", "Jump threshold: jumps", "minimum jump, points", JUMPS_K, 1e-3, False),
    ("threshold_os", "Jump threshold: result", "minimum jump, points", OS_PCT, 100, True),
    ("cut_start", "Start cut: jumps", "% of life left out at the start", JUMPS_K, 1e-3, False),
    ("cut_start_os", "Start cut: result", "% of life left out at the start", OS_PCT, 100, True),
    ("cut_end", "End cut: jumps", "% of life left out at the end", JUMPS_K, 1e-3, False),
    ("cut_end_os", "End cut: result", "% of life left out at the end", OS_PCT, 100, True),
    ("slot", "Slot length: jumps", "slot length, minutes", JUMPS_K, 1e-3, False),
    ("slot_os", "Slot length: result", "slot length, minutes", OS_PCT, 100, True),
    ("edge", "Settle band: jumps", "band edge, points from 0% or 100%", JUMPS_K, 1e-3, False),
    ("next_n", "Next trades: how many", "trades averaged", "overshoot at the\nnext trades, %", 100, True),
    ("next_max", "Next trades: how long to wait", "minutes allowed", "jumps with next trades, %", 100, True),
    ("takers", "Trader groups", "exact number of traders", "overshoot, % of the jump", 100, True),
    ("bins", "Baseline price bins", "number of bins", "overshoot, % of the jump", 100, True),
    ("sample", "Random sample for the baseline", "% of slots sampled", "spread of the overshoot,\npoints", 100, False),
    ("boot", "Resamples for the ranges", "resamples", "spread of the range's\nlower end, points", 100, False),
]


def m_elbows():
    c = pd.read_csv(LD + "r11_curves_all.csv")
    kn = pd.read_csv(LD + "r11_knees_all.csv").set_index("curve")
    fig, axes = plt.subplots(4, 4, figsize=(14, 12))
    for ax, (name, title, xl, yl, ys, yp) in zip(axes.flat, ELBOWS):
        k = kn.loc[name].copy()
        k["curve"] = name
        elbow_panel(ax, c, k, NOW.get(name, k.chosen), title, xl, yl, ys, yp)
    for ax in axes.flat[len(ELBOWS):]:
        ax.axis("off")
    fig.suptitle("The elbow method for every parameter: circle = knee, dashed = value used, dotted = value before",
                 fontsize=13, weight="bold", color=TEXT)
    save(fig, "m_elbows")


def f2_counts():
    t = pd.read_csv(LD + "r11_traders.csv", dtype={"traders": str})
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(10, 7), sharex=True, gridspec_kw={"height_ratios": [1, 1.1]})
    x = np.arange(len(t))
    col = count_colours(t.traders)
    a1.bar(x, t.share * 100, 0.7, color=col)
    for i, (sh, n) in enumerate(zip(t.share, t.jumps)):
        a1.text(i, sh * 100 + 1.2, f"{sh:.1%}\n{n:,}" if sh >= .01 else f"{sh:.1%}", ha="center", fontsize=7.5, color=TEXT)
    a1.set_ylim(0, 82)
    pct(a1)
    a1.set_ylabel("share of price jumps")
    a1.set_title("How many traders make a price jump, and how much it overshoots")
    a2.bar(x, t.overshoot * 100, 0.7, color=col)
    a2.errorbar(x, t.overshoot * 100, yerr=[(t.overshoot - t.lo) * 100, (t.hi - t.overshoot) * 100],
                fmt="none", ecolor=TEXT, lw=1)
    a2.axhline(0, color=SUBTLE, lw=1)
    pct(a2)
    a2.set_ylabel("overshoot, % of the jump")
    a2.set_xticks(x, t.traders)
    a2.set_xlabel("number of different traders who took liquidity in the jump's 30 minutes")
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


def f2_accuracy():
    a = pd.read_csv(LD + "r11_accuracy.csv", dtype={"group": str})
    a = a[a.by == "k"]
    fig, ax = plt.subplots(figsize=(10, 4.6))
    x = np.arange(len(a))
    ax.plot(x, a.expected_after * 100, "--", color=MUTED, lw=1.8)
    ax.plot(x, a.expected_before * 100, ":", color=MUTED, lw=1.8)
    ax.text(x[-1] + 0.15, a.expected_after.iloc[-1] * 100, "if the price after\nthe jump were right",
            va="center", fontsize=8.5, color=SUBTLE)
    ax.text(x[-1] + 0.15, a.expected_before.iloc[-1] * 100, "if the price before\nthe jump were right",
            va="center", fontsize=8.5, color=SUBTLE)
    ax.errorbar(x, a.right * 100, yerr=[(a.right - a.lo) * 100, (a.hi - a.right) * 100], fmt="none", ecolor=TEXT, lw=1)
    ax.scatter(x, a.right * 100, s=60, c=count_colours(a.group), zorder=3)
    ax.text(x[-1] + 0.15, a.right.iloc[-1] * 100, "actual", va="center", fontsize=8.5, color=TEXT, weight="bold")
    ax.set_xticks(x, a.group)
    ax.set_xlim(-0.5, len(a) + 1.6)
    ax.set_ylim(35, 66)
    pct(ax)
    ax.set_xlabel("number of different traders in the jump's 30 minutes")
    ax.set_ylabel("jumps that pointed toward\nthe final outcome, %")
    ax.set_title("Jumps point the right way more often than the old price implied, less than the new one")
    save(fig, "f2_accuracy")


ALL = {"ex1": ex1_example, "ex2": ex2_overshoot, "spikes": bg_spikes, "pipeline": bg_pipeline,
       "f1_hero": f1_hero, "f1_splits": f1_splits, "f1_tags": f1_tags,
       "f2_traders": f2_traders, "f2_money": f2_money, "f2_robustness": f2_robustness,
       "f2_controlled": f2_controlled, "f2_wallets": f2_wallets, "f3": f3_decay,
       "f5": f5_fade, "f6": f6_structure, "f6_tags": f6_tags, "f8": f8_close_next, "f8_conf": f8_confirmation,
       "sp_groups": sp_groups, "sp_sport": sp_sport, "f4_versions": f4_versions,
       "f10_reaction": f10_reaction, "m_elbows": m_elbows, "f2_counts": f2_counts,
       "f3_giveback": f3_giveback, "f2_accuracy": f2_accuracy}


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
