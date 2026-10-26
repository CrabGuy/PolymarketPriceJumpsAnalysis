# Jumping to Conclusions: Polymarket Price Jumps Analysis

*An exploratory analysis of 766 million Polymarket trades, November 2022 to May 2026*

---

## Contents

1. [In short](#1-in-short)
2. [The data and two ideas](#2-the-data-and-two-ideas)
3. [The findings](#3-the-findings)
   - [F1. Big moves overshoot by about a third](#f1-big-moves-overshoot-by-about-a-third)
   - [F2. Moves made by many traders stick; moves made by one trader don't](#f2-moves-made-by-many-traders-stick-moves-made-by-one-trader-dont)
   - [F3. A lone trader's push is undone within minutes](#f3-a-lone-traders-push-is-undone-within-minutes)
   - [F4. In a race, a crowd's move that the other candidates offset is right at once](#f4-in-a-race-a-crowds-move-that-the-other-candidates-offset-is-right-at-once)
   - [F5. Betting against big moves doesn't reliably pay](#f5-betting-against-big-moves-doesnt-reliably-pay)
   - [F6. Lone pushes happen in thin markets](#f6-lone-pushes-happen-in-thin-markets)
   - [F7. Sports and esports: close to right by the next trades](#f7-sports-and-esports-close-to-right-by-the-next-trades)
   - [F8. Crypto "up or down" markets: the same pattern, over within seconds](#f8-crypto-up-or-down-markets-the-same-pattern-over-within-seconds)
   - [F9. Searching for recurring patterns](#f9-searching-for-recurring-patterns)
4. [What did not work](#4-what-did-not-work)
5. [Limitations](#5-limitations)
6. [Reference: methods and parameters](#6-reference-methods-and-parameters)
7. [Glossary](#7-glossary)
8. [Where the code is](#8-where-the-code-is)

---

## 1. In short

On Polymarket, people bet on events by buying shares that pay $1 if the event happens, so a
share's price is the market's probability for the event. We looked at every sharp price
jump in 766 million trades and asked one question: **judging by how the market finally
resolved, how much of the jump was justified?**

**About two thirds.** The other third is an **overshoot**: noise that the market later takes
back. This holds in every year and almost every category.

What tells real moves from noise is **how many different traders made them**:
- A jump made by one trader goes about a third too far, and the next trades, minutes later,
  undo most of it.
- A jump made by four or more traders goes less than a fifth too far.
- Lone pushes are common where the order book is thin, so that a few dollars can move the
  price.

The overshoot doesn't add up to easy money: once the bid-ask spread is paid, betting against
big moves has no reliable edge. Sports and esports show the efficient side of the market: by
the next trades, their prices are close to right.

---

## 2. The data and two ideas

### The data

We used every Polymarket trade from November 2022 to May 2026: 766 million trades in about
one million markets, each with a time, a price, a dollar amount and the two wallets
involved. The heavy work ran on a server; small summary tables were analysed on a PC.

![The data pipeline](plots/bg_pipeline.png)

Most of the report covers **event markets**: elections, sports, economy, culture, and so on.
That is 438,920 markets. The recurring crypto "up or down" markets ("Will bitcoin be up in
the next 15 minutes?") behave differently and are covered in [F8](#f8-crypto-up-or-down-markets-the-same-pattern-over-within-seconds).

### Idea 1: a big move

Here is a real market: *"Will the US attack Iran by February 15?"* (2024), a small market with
421 trades. On 28 January a drone attack killed three US soldiers in Jordan, and the price
jumped. In early February the US struck Iran-backed groups in Iraq and Syria, not Iran
itself, and the market resolved **NO**.

![A real market with its big moves](plots/ex1_example-market.png)

The trades are grouped into 15-minute slots, and each slot gets its average price: each dot
is one slot with trades. A **big move** (red) is a slot whose price is at least **0.4 in
log-odds** away from the previous slot with trades. That is about 10 percentage points around
50%, and smaller steps near 0% or 100%, where prices move in small increments; this is why
some red steps near the bottom look small.

One stretch is left out: the last 6 hours before a market settles at 0% or 100%. Every market
makes that final run-up, so it would only measure the obvious.

**How common are big moves?** Most active markets have some:

![How many markets have big moves](plots/bg_spikes-by-category.png)

Two facts about these moves matter for everything that follows.

**They involve little money.** The median big move has $7 traded in its 15 minutes, and
82% have less than $100. A price can jump on a few dollars because, in most markets, few
orders sit near the current price. A small order runs through them and reaches prices far
away.

**Most are made by a single trader "taking liquidity".** Some traders post an order and wait
("I'll sell at 30%"): they are the *makers*. Others accept a posted order immediately: they
are the *takers*, and only takers move the price. So for each big move we count the
different wallets that took liquidity in its 15 minutes. In 73% of big moves there is just
one, and that trader spent a median of $4.

### Idea 2: overshoot

Zoom in on 28 January. In one transaction, a single trader bought everything on offer: fills
at 6%, 23%, 29% and even $0.27 at 95%, $23 in total. The 15-minute average jumped from 5% to
25%. The next trades, under an hour later, were back at 12%, so two thirds of the jump was
given back.

![The same market, up close](plots/ex2_example-overshoot.png)

The part of a jump that turns out to be unjustified is the **overshoot**. One market can't
measure it, but thousands can:
1. Take all moves that ended at, say, 60%.
2. If those prices were right, YES should win 60% of the time.
3. If YES wins only 53% of the time, the prices were 7 points too high.
4. Against a 20-point move (40% → 60%), that is an overshoot of 7 / 20 = **35% of the move**.

Prices are slightly off even at quiet moments (YES tends to be a little overpriced), so
that usual error is measured at random moments and subtracted first. An overshoot of 0%
means the moves were exactly right; a negative one means the price didn't go far enough.

```python
# outcome = 1 if YES won, else 0;  p_close = price after the move, p_pre = before it
baseline  = usual_error_at(p_close)                  # mean (outcome - price) at random moments
overshoot = -((outcome - p_close) - baseline) * sign(move)
overshoot_share = overshoot.sum() / abs(p_close - p_pre).sum()   # over many moves
```

Uncertainty ranges come from resampling whole markets.

**A note on averaging.** Each 15-minute price is volume-weighted: a trade counts in
proportion to its dollars. Weighting only acts *within* a slot, so a slot traded by one
wallet simply gets that wallet's average fill. Re-measuring everything with plain averages,
every trade counting equally, gives the same results: single-trader moves overshoot 37% either
way, and crowd moves 16% against 20%.

---

## 3. The findings

### F1. Big moves overshoot by about a third

Across 1.05 million big moves in 158,000 markets, the price right after a big move is on
average **too extreme by 31% of the move** (range 30.7-31.3%).

The plot shows it without any formula. For moves that ended at a given price (x-axis), it
shows how often YES actually won (y-axis):
- after an **up** move to about 60%, YES won only 47% of the time;
- after a **down** move to about 60%, YES won 60% of the time;
- at random moments, a 60% price won 57% of the time.

After a jump, the price sits too far in the direction of the jump.

![After a jump, the price is too far](plots/f1_hero.png)

It is close to a third in every year, at any distance from the market's end, and in every
category except esports (17%). It is lower only for moves starting above 80% (25%), where
prices move in small steps:

![Overshoot by category, year, price and time left](plots/f1_splits.png)

The size varies by topic. Across 205 tags it ranges from about 12% to 43%. Stock and crypto
price markets, tennis and several esports titles are at the low end; elections, earnings,
macro data and big sports events at the high end.

![Overshoot by tag](plots/f1_tags.png)

---

### F2. Moves made by many traders stick; moves made by one trader don't

The best predictor of overshoot is **how many different traders took liquidity in the
move's 15 minutes**.

![Overshoot by number of traders](plots/f2_traders.png)

Two real moves show the contrast:
- **Left:** on the Sunday before the 2024 US election, one trader paid $12,000 in 30 fills and
  pushed "Democratic" from 42% to 70%. Ten minutes later the price was back at 43%.
- **Right:** on 20 May 2024, sixty traders moved "Ethereum ETF approved by May 31?" from 20% to
  53% on news that the regulator was changing course. The move held, and the ETF was
  approved.

![Two real moves](plots/f2_two-moves.png)

The pattern is robust:
- **At the same money.** In every money band, one trader's moves overshoot the most. Above
  $500 the gap is widest: 43% for one trader against 12% for four or more.

  ![By money and number of traders](plots/f2_money.png)

- **For every definition of a big move:** 5-, 15- or 60-minute slots, and jumps of at least
  about 6, 10 or 15 points.

  ![Robustness](plots/f2_robustness.png)

- **With everything else held fixed.** A regression holds category, question type, money,
  price level, time to the end, market lifetime, year and direction fixed at once. Crowd
  moves still overshoot 13 points less than single-trader moves, against 17 points raw.

  ![With all other factors held fixed](plots/f2_controlled.png)

- **It's not a handful of wallets.** The 762,000 single-trader moves come from 187,000
  wallets. A wallet's overshoot in the first half of its history barely predicts the second
  half.

  ![Wallets](plots/f2_wallets.png)

**What it means.** Agreement between several independent traders is a much better sign of
information than the size of a move.

---

### F3. A lone trader's push is undone within minutes

Following the same moves over time:
- **One trader:** the overshoot falls from 36% to **7% at the very next trades**.
- **Four or more traders:** it starts lower (24%) but lingers. It is still 19% at the next
  trades and 12% after an hour, and is gone within a day.

![How the overshoot fades](plots/f3_decay.png)

"Next trades" means the first five trades after the 15 minutes. They come a median of 2½
minutes after crowd moves and 16 minutes after single-trader moves, which happen in quieter
markets.

**What it means.** A lone trader's push is mostly temporary *price impact*: one order walks
the price through a thin book, and the next traders bring it back. A crowd's smaller
overshoot is a slower over-reaction.

---

### F4. In a race, a crowd's move that the other candidates offset is right at once

Many questions on Polymarket are races: who wins an election, which team wins a league.
Each candidate is its own market, and exactly one of them will win. Most of these races are
**neg-risk** events (a flag in the data): a NO share in one candidate can be converted into
YES shares of all the others. This links the candidates' prices, so that their YES prices add
up to about 100%, and it gives liquidity even to the long shots.

So when one candidate jumps, the others should fall by about as much in total. For each of
the 240,000 big moves in neg-risk events, we checked what the other candidates did in the
same 15 minutes. They either **offset** the move (moved the other way by at least 75% of it),
**partly** offset it (25-75%), did **not** offset it, or did not trade at all.

![Other candidates](plots/f4_versions.png)

- A **crowd's move** (4+ traders) that the others offset is right at once: −3% at the end of
  the 15 minutes (range −10% to +4%). Without the offset it overshoots by 31%, and by 50% if
  no other candidate traded.
- For a **lone trader's** move the offset makes no difference: about a third either way.
- By the **next trades** the difference is gone: crowd moves are 10-13% too far, offset or not.

**What it means.** In a race, a crowd move that the rest of the field confirms by repricing
is right at once. A move the rest of the field ignores goes too far until the next trades
correct it. Outside neg-risk events (175,000 moves), offset moves are no better (32% against
26% overshoot), but there the markets of an event need not exclude each other, so an "offset"
means little.

---

### F5. Betting against big moves doesn't reliably pay

If moves overshoot, betting against them should pay. Each test bet buys the opposite side
right after the move, at the price a bettor would actually have paid, and holds it to the
end. Returns are measured per $1 staked, net of the usual pricing error. Bets are placed
only when the move started between 5% and 95%, because below that the opposite side costs a
few cents and a single win pays 20 times the stake.

Even so, a few very large wins dominate the plain averages. With the most extreme 1% at each
end trimmed:

![Betting against big moves](plots/f5_fade.png)

- **After single-trader moves, betting against them loses** about 7 cents per $1. The fast
  snap-back happens, but the bid-ask spread (a median 3.6 cents) eats it.
- **After crowd moves, it about breaks even** (+1 cent, not significantly different from 0).
- **Only moves with over $1,000 behind them leave a small edge** (+4.5 cents per $1, range
  0.5-8.4).

**What it means.** The overshoot is real, but most of it can't be captured by someone who
reacts to it and pays the spread.

---

### F6. Lone pushes happen in thin markets

Some markets see single-trader big moves all the time, others never. For each of 107,000
markets with at least 20 active slots, standard market-structure measures were computed:
- how concentrated trading is among wallets (Gini, Herfindahl, the biggest wallet's share);
- how far $1,000 of net buying moves the price (Kyle's lambda);
- the bid-ask spread (Roll's estimator, and the buy-sell price gap within a minute);
- how balanced buying and selling are.

![Thin books, not concentration](plots/f6_structure.png)

- **How often one trader can push the price depends on how thin the book is.** With market
  size held fixed, it correlates with the spread (+0.44) and with the price impact per
  dollar (+0.33).
- **Concentration among a few wallets plays no part** (Gini −0.09).
- **This holds in every category.**
- **How far the push goes doesn't depend on the market:** one-trader moves overshoot 35-44%
  in every fifth of the markets, on every measure (right panel).

Across 222 tags the link is strong (+0.79). Mention markets, Netflix, earnings and equities
are at the top; football leagues and world elections at the bottom.

![By tag](plots/f6_tags.png)

---

### F7. Sports and esports: close to right by the next trades

Game markets lose most of their big moves to the 6-hour cut at the end, because for many of
them those hours are the game itself. So sports and esports were also analysed over their
whole life, with nothing cut before the price settles: 729,000 big moves in 227,000 markets.
The data has no kickoff times, so moves before and during a game are not told apart.

![Sports and esports by number of traders](plots/sp_groups.png)

- **At the end of the 15 minutes,** lone pushes overshoot as everywhere else (33% in sports,
  36% in esports), and crowd moves look as if they fell short (−17% and −22%): the 15-minute
  average still includes trades from before the jump, so after a fast move it lags behind.
- **By the next trades, every group is within about ±4% of right.** For crowd moves those
  trades come under a minute later.

The same holds in every sport:

![By sport](plots/sp_sport.png)

**What it means.** In game markets, whatever caused a big move, the price is close to right
by the next trades. Lone pushes there are undone quickly, and crowd moves are absorbed in
under a minute.

---

### F8. Crypto "up or down" markets: the same pattern, over within seconds

These recurring markets (bitcoin, ether, solana and xrp, over 5 minutes, 15 minutes or 1
hour) hold 59% of all trades. Measured on 1-minute slots: 533,397 big moves in 121,100
markets.

![Close vs next trades](plots/f8_close-vs-next.png)

At the end of the minute the familiar pattern appears: lone pushes go too far (+8% to +16%)
and crowd moves keep going (−15% to −30%). By the next trade, one or two seconds later,
every group is within about ±7%: nothing is left to exploit.

A related market decides the direction. A crowd move in bitcoin's market keeps going when
ether's market moved the same way in that minute (−32%), and reverses when it moved the other
way (+23%).

![Confirmation by the other coin](plots/f8_confirmation.png)

---

### F9. Searching for recurring patterns

We also looked for recurring shapes with *matrix profiles*, a standard pattern-search tool
for time series. Price paths after big moves show **no recurring shape beyond chance**: 5.5%
of real paths have a close match elsewhere, against 5.0% of shuffled ones. In the chain of
bitcoin's 15-minute markets, the unusual stretches are "whipsaw" markets where the price
crosses 50% about six times. Comparing the coins' chains shows that their markets move
together, with bitcoin and ether about 30 seconds ahead of solana and xrp. All of this is
real but has plain explanations, and none of it is tradable.

---

## 4. What did not work

- **Recurring price shapes across markets.** Real matches were no more common than chance.
- **"Price moved without money" anomalies.** Mostly bid-ask bounce: trades alternating
  between the buy and the sell side.
- **"More trades means more reversal".** An artefact of using the last trade price: a sweep's
  last fill is its most extreme price. Fixed by using 15-minute averages.
- **"Bet against crypto YES spikes".** It was just crypto YES being about 8 points overpriced
  in general. Fixed by measuring the usual error per category.
- **Concentration (Gini) as the cause of lone pushes.** With size and price impact held
  fixed, it adds nothing.
- **Bitcoin anomalies clustering at US data-release hours.** This did not hold up.
- **Splitting game markets into before and during the game.** The data has no kickoff
  times, and the end date is not a reliable stand-in (esports matches often settle hours
  before it), so no such split is made.

---

## 5. Limitations

- **"Next trades" is an average of real trades, not a guaranteed price.** F5 uses
  side-specific prices, but fees and queue position are not modelled.
- **The usual-error correction is estimated from the data**, per category or question type.
  Other ways of estimating it move the levels by 1-3 points without changing any comparison.
- **Most moves are small in money.** The findings describe how prices behave, not a large
  pool of money.
- **Approximate labels.** Categories and question types come from text rules.
- **No external data.** There are no news timestamps or live scores, so "confirmation" always
  means other Polymarket prices.

---

## 6. Reference: methods and parameters

### 6.1 Data and big moves

| Step | Choice |
|---|---|
| Markets | all event markets with trades; recurring crypto up/down markets analysed separately (F8) |
| YES price per trade | `price` if the traded token is token 1, else `1 - price` |
| Slots | **15 min** (main); 5 and 60 min as checks; **1 min** for crypto up/down |
| Slot price | volume-weighted average (VWAP); checked against the plain average of trades |
| Price scale | log-odds `log(p / (1 - p))`, p clipped to [0.01, 0.99] |
| **Big move** | a slot whose price is ≥ **0.4** log-odds from the previous slot with trades (checks: 0.25 and 0.6) |
| End of a market | the last **6 h** before the price leaves [5%, 95%] for good are left out (F7: nothing left out) |
| Outcome | first outcome price > 0.99 → YES, < 0.01 → NO, otherwise the market is left out |
| Categories, question types | first match of a text rule on the tags / question |

### 6.2 Overshoot and statistics

| Item | Choice |
|---|---|
| Usual error (baseline) | mean (outcome - price) in 20 price bins of 5 points, at random moments (a 5% sample of slots); pooled for F1, per category for F2-F3, per question type for F4-F5, sports / esports for F7, per coin and length for F8 |
| Overshoot | `-((outcome - p) - baseline(p)) × sign(move)` at any later price p; shared as Σ overshoot / Σ \|move\| |
| Next trades | the first **5 trades** after the slot, within **1 h** (5 min for crypto) |
| Trader groups | distinct taker wallets in the move's slot: **1 / 2-3 / 4+** |
| Uncertainty | resampling whole markets, 200-300 times |
| All factors at once (F2) | weighted least squares, weight \|move\|; dummies for traders, question type, category, money, price band, time to end, lifetime, year, direction |
| Wallets (F2) | wallets with ≥ 10 single-trader moves; overshoot in the first vs second half of their history |
| Betting against moves (F5) | entry = first 5 trades on the bettor's side within 1 h; return per $ = sign × (entry - outcome) / stake; moves starting between 5% and 95%; returns trimmed at the 1st and 99th percentile |
| Market structure (F6) | markets with ≥ 20 active slots; Kyle's lambda = slope of the slot's price change on net buying (consecutive slots ≤ 2 h apart, ≥ 20 slots); Roll spread; Spearman correlations controlling for traders, money and slots |
| Other candidates (F4) | neg-risk events (`neg_risk` = 1); offset = −(sum of the other candidates' price changes in the slot) / the move; groups: none traded, < 25%, 25-75%, ≥ 75% |
| Crypto (F8) | other coin = ether for bitcoin, bitcoin for the others; "moved" = ≥ 0.1 log-odds in the same minute |

### 6.3 Pattern search (F9)

| Search | Series | Window | Distance | Chance comparison |
|---|---|---|---|---|
| After big moves | 55 five-minute prices per move (−35 min to +4 h), 20,000 moves | 55 | z-normalised; matches must be in another event; paths need ≥ 8 price changes | post-move steps shuffled |
| Bitcoin chain | bitcoin 15-min markets back to back, 30 points each (673,620 points) | 30 | z-normalised, `stumpy.stump` | profile vs 200 shuffles |
| Coin pairs | the 4 coins' 15-min chains, AB-joins | 30 | `stumpy.stump(T_A, 30, T_B)` | other coin shuffled in time |

### 6.4 Computing and plots

- **Server:** each extraction step runs on 2 threads within 8 GB of memory. Regrouping the
  766 million trades takes one pass of about 30 minutes.
- **Plots:** Python with numpy, pandas, scipy, stumpy and matplotlib, in the Rose Pine Dawn
  theme. The trader groups have fixed colours: 1 trader = rose-red, 2-3 = gold, 4+ = pine blue.

---

## 7. Glossary

| Term | Meaning |
|---|---|
| **YES price** | Price of the share that pays $1 if the event happens; read as a probability |
| **Log-odds** | `log(p / (1 - p))`; a step of 0.4 is about 10 points around 50% |
| **Slot** | A 15-minute window in which trades are grouped |
| **Big move** | A slot whose price is ≥ 0.4 log-odds from the previous slot with trades |
| **Maker / taker** | The maker posted an order and waited; the taker accepted it, moving the price ("taking liquidity") |
| **Overshoot** | The part of a move that the final outcome did not justify, beyond the usual error, as a % of the move |
| **Next trades** | The first five trades after a move |
| **Neg-risk event** | A Polymarket race whose candidates exclude each other; a NO share in one converts into YES shares of all the others, which links their prices and gives the long shots liquidity |
| **Spread** | The gap between the price to buy and the price to sell |
| **Kyle's lambda** | How far $1,000 of net buying moves the price |
| **Gini / Herfindahl** | Measures of how concentrated trading is among wallets |
| **Matrix profile** | For every window of a series, the distance to its most similar other window |

---

## 8. Where the code is

| Step | Scripts |
|---|---|
| Server extraction | `remote/s1_bucket.py` (regroup trades), `s2_events.py` / `s3_events.py` (slots and moves), `s4_paths.py` (price paths), `s6_micro.py` (market structure), `s7_events.py` (sports; plain averages), `s8_wallets.py` (wallets and other candidates), `p7_extract.py` (example market) |
| F1-F3 | `explore/r02_persistence.py`, `r03_robustness.py`, `r04_types.py`, `r07_basis.py` |
| F2 regression | `explore/r05_event_markets.py` |
| F4 | `explore/r08_pairs.py`, `r07_siblings.py` |
| F5, F6 | `explore/r06_fade.py`, `r08_fade_robust.py`, `r06_concentration.py` |
| F7, F8 | `explore/r07_sports.py`, `r05_updown.py` |
| F9 | `explore/r04_motifs.py`, `r04_btc_chain.py`, `r05_crypto_mp.py` |
| Filter checks | `remote/s9_variants.py`, `explore/r08_filters.py` |
| This report | `explore/report_stats.py`, `report_figures.py`, `report_style.py` |

**Related work:** Tsang & Yang, "Political Shocks and Price Discovery in Prediction Markets"
and "The Anatomy of Polymarket" (arXiv 2603.03152, 2603.03136); Akey, Vincent, Harvie &
Martineau, "Who Wins and Who Loses in Prediction Markets? Evidence from Polymarket" (CEPR DP
21615, 2026); Roll (1984).
