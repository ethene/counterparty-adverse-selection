#!/usr/bin/env python3
"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-08-25
References: Hyperliquid Level-4 order-book data, Zenodo 18184441 (Albers et al. 2026);
the Hyperliquid maker fee schedule as recorded by money/maker_econ.py; Avellaneda and
Stoikov (2008) Quantitative Finance 8(3) 217-224; Glosten and Milgrom (1985) Journal of
Financial Economics 14(1) 71-100; Barzykin, Bergault, Gueant and Lemmel, arXiv:2508.20225;
Easley, Lopez de Prado and O'Hara (2012) Review of Financial Studies 25(5) 1457-1493. The
numbers drawn are read from quoters/mm_bakeoff_results.json and none is computed here.

THE HEADLINE FINDING IS A PROPERTY OF THE REFERENCE PRICE, AND THIS FIGURE SAYS SO.

The report concludes that none of the quoting rules it scores is profitable. That
conclusion is true of the measure the report leads with and false of the other measure
the same run publishes, on the same rules and the same fills. A reader who is not told
this can only find it by opening a 1.2 MB artifact and walking 2,376 leaves. The figure
puts the two measures on one pair of axes so that the dependence is visible instead of
being available.

WHAT THE TWO MEASURES ARE, PHYSICALLY. Both score the same executed fill. They differ in
the price the maker's result is measured against, and in nothing else.

  net_MID_lower = s_q - a_mid    The maker credits itself the half-spread it quoted and
                                 pays the move of the BOOK MID over the horizon, where
                                 the entry mid is taken strictly BEFORE the fill. The
                                 fill's own footprint on the price is therefore charged
                                 to the maker, which is what being on the other side of
                                 an informed trade costs.

  net_PRINT     = -a_print       The clock starts at the fill's OWN execution price and
                                 the horizon reference is the last trade print. The move
                                 from the pre-trade mid to the traded price is outside
                                 the measurement, so the maker is charged only for what
                                 happens after the trade has printed.

The distance between them is a level, not a drift, and this file measures it rather than
asserting it: pooled at the ten-second horizon it is 1.5794 bps. Subtract the two pre-fee
grosses and the quoted half-spread cancels, so on any set of fills both measures score the
distance is a property of the tape and not of the rule that quoted. It is very nearly
that: across the eleven rules it varies by 1.3e-06 bps at the headline horizon. The
residue is not noise and the run bounds it rather than tolerating it. The two measures do
not score exactly the same rows -- a fill with a finite print markout but no book-mid
markout drops from the book-mid mean and not from the other -- and on the rows they do not
share the half-spread has nothing to cancel against. The unshared rows number 5, 9 and 413
of about 1,232,000 at one, ten and sixty seconds, and the spread across rules follows that
ordering exactly: 9.6e-09, 1.3e-06 and 1.1e-04 bps. The guard below computes the width
those unshared rows can account for and refuses to draw if the observed spread exceeds it.

Read across the horizon ladder the gap is 1.76, 1.58 and 1.61 bps at one, ten and sixty
seconds. It does not grow with the horizon, which is the signature of a difference in
where the clock starts rather than a difference in how the price drifts. For scale, the
venue's entire maker fee schedule spans 1.8 bps from the base rung to the deepest rebate.
Choosing the reference price is worth almost as much as the whole fee schedule is.

WHY THE REPORT LEADS WITH THE BOOK MID. The work books the counterparty premium as a COST
the maker bears and not as revenue it collects, and the conservative measure is the one
consistent with that stance: it charges the maker for the price move its own fill was part
of. The code carries the same stance in the accounting rather than only in the prose. The
booked offset is capped at min(extra, max(a_mid, 0)), so a defensive premium can at most
return the maker to its book income on a toxic fill and can never lift it above, and the
run refuses to publish unless every rule is net-negative on this measure at the base fee
rung. That cap is why the tier ladder below is a rigid translation: moving a rung changes
the fee and nothing else, so the whole bundle slides without reordering.

WHAT THE PICTURE SHOWS, PANEL BY PANEL. The left panel is the slice the report leads with,
pooled across both coins at the ten-second horizon and the fifty-fill selection rung, with
the six fee rungs on the horizontal axis. Each measure is drawn as a band spanning the
worst and best of the eleven rules with its median inside, so the reader sees a bundle and
not eleven lines. The optimistic bundle crosses zero between the second and third rung.
The conservative bundle never does, and its best cell at the deepest rebate is still
0.6358 bps under water. The right panel answers the obvious objection, that the left panel
is one slice of many: it counts, over the WHOLE grid of 1,188 cells per measure, how many
sit above zero at each fee rung. On the trade print the count runs 1, 95, 136, 150, 150,
150 and totals 682. On the book mid it is zero at every rung, and that zero is the claim
that the conclusion holds on all three horizons, all three populations and both selection
rungs, not merely on the headline slice.

THERE IS A SECOND AXIS OF THE SAME KIND, AND IT IS THE STRONGER ONE. Positivity on the
trade print also depends on the fee rung, and more sharply than it depends on the
reference price. Of the 682 positive cells, 586 -- 86 per cent -- sit where the venue
charges the maker nothing or pays it: 136 at the zero-fee rung and 150 at each of the
three rebate rungs. That is why the fee ladder is the horizontal axis of both panels
rather than a caveat in the caption: the figure is about two dependencies, not one.

The remaining 96 divide in a way worth stating precisely, because the loose version of it
is wrong. Exactly ONE positive cell sits at the base rung, which is what an ordinary maker
pays. The other 95 sit at the 0.4 bps rung, and that rung is a real and attainable one --
saying that only one positive cell survives at a genuine venue rung would be false. The
correct statement has three parts: one at the entry rung, 95 at the discounted rung, and
86 per cent of all positives needing zero fee or a rebate.

Reaching the rebate rungs is not a modelling choice a reader can make. They require a
fourteen-day share of venue turnover that six maker addresses out of 9,367 attained in
this window, as money/maker_econ.py records beside the schedule itself.

THE GRID IS NOT 1,188 INDEPENDENT MEASUREMENTS, and the file checks this rather than
asserting it. The third population, pooled, is the union of the other two: its fill count
equals the BTC and ETH counts added, exactly, at all three horizons, and the run refuses
to draw if that stops being true. So a third of the cells are re-aggregations of the other
two thirds. Every count is therefore published twice, once over all three populations and
once over the 792 cells of the two disjoint ones. The conclusion does not depend on which:
the book mid has 0 positive cells of 792 as well as 0 of 1,188.

THE COUNTS ARE TAKEN OVER A NAMED POPULATION WITH A NAMED PREDICATE. The population is
every leaf at quoters[K][rule].net_by_coin[coin].by_horizon[h][measure].by_fee_tier[tier],
which is 11 rules x 2 selection rungs x 3 populations x 3 horizons x 6 fee rungs = 1,188
per measure. The predicate is net_vw_bps > 0, the notional-weighted measure the report
quotes. The equal-weighted column of the same leaves is counted beside it and disagrees in
a way worth carrying: 546 positive on the trade print and 212 on the book mid, so the book
mid does produce positive cells per fill even though it produces none per dollar. Both
counts are written to the results file. Reporting only the first would state the
conclusion more strongly than the artifact supports.

A COUNT THIS FILE PUBLISHES THAT DISAGREES WITH A COUNT ALREADY IN THE TREE. The header of
quoters/mm_bakeoff.py states 244 positive net_PRINT cells of 648 over its own six-rule
grid, 46 of them at the headline horizon, with 22 belonging to naive_at_book, 58 to
as_toxicity and 88 to bbgl. Recomputed here on the committed artifact over exactly that
six-rule population the figures are 248, 50, 22, 62 and 88. The four extra cells are all
as_toxicity at the ten-second horizon, and running this same count on each commit that
touched the artifact dates the move precisely: the count was 244 up to the commit before
the entry mid was moved to a snapshot taken strictly before the fill, and 248 from that
commit onward. Charging the maker from a pre-trade mid lifted two cells above zero on each
selection rung. The recomputed counts and the four addresses are written to the results
file so that the disagreement is a measurement a reader can re-run rather than a remark.

DRAWN AT THE SIZE IT IS PRINTED. The canvas is 5.53 inches wide because that is the width
of the single text column of the report, and 3.3 inches tall so that it does not push the
paragraph it supports onto the next page. Every point size below is the size a reader of
the page sees. The zero line is drawn heavier than the grid in both panels, because which
side of it a bar falls on is the entire content of the figure.

THIS FILE COMPUTES NO NEW QUANTITY OF THE MARKET. It reads one committed artifact, costs
under a second, and takes no command line. Redrawing it never means recomputing the node
that produced the numbers.
"""

import json
import os
import sys
from collections import Counter

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# artifact.py and settings.py sit in the repository root, one directory up from this
# group, so the path is built from this file's own location and never from the working
# directory the run happens to start in.
_CODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CODE_DIR not in sys.path:
    sys.path.insert(0, _CODE_DIR)

import artifact
import settings as H

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_JSON = os.path.join(HERE, "mm_bakeoff_results.json")
OUT_PNG = os.path.join(HERE, "mm_bakeoff_reference.png")
OUT_JSON = os.path.join(HERE, "mm_bakeoff_reference_figure_results.json")

T0 = artifact.start_clock()

# The printed geometry, in one place, because a size named twice is a size that drifts.
WIDTH_IN, HEIGHT_IN, DPI_OUT = 5.53, 3.3, 200
PT_LABEL, PT_TITLE, PT_LEGEND, PT_NOTE = 7.5, 8.5, 7, 6.8
plt.rcParams.update({"font.size": PT_LABEL,
                     "axes.labelsize": PT_LABEL,
                     "axes.titlesize": PT_TITLE,
                     "xtick.labelsize": PT_LABEL,
                     "ytick.labelsize": PT_LABEL,
                     "legend.fontsize": PT_LEGEND})

# ---------------------------------------------------------------------------
# Which cell of the artifact is drawn. Every coordinate is READ, not typed.
# ---------------------------------------------------------------------------
H_HEADLINE = H.HEADLINE_HORIZON_S
H_KEY = f"h{int(H_HEADLINE)}"
# mm_bakeoff.py names its two reference prices net_PRINT and net_MID_lower; settings.py
# names the headline lens "mid". The mapping between the two vocabularies lives here
# because this is the only file that has to speak both.
LENS_TO_MEASURE = {"mid": "net_MID_lower", "print": "net_PRINT"}
HEADLINE_MEASURE = LENS_TO_MEASURE[H.HEADLINE_LENS]
OTHER_MEASURE = LENS_TO_MEASURE["print" if H.HEADLINE_LENS == "mid" else "mid"]
MEASURES = (OTHER_MEASURE, HEADLINE_MEASURE)   # optimistic first, conservative second
HEADLINE_POP = "pooled"
STAT = "net_vw_bps"           # the notional-weighted column the report quotes
COMPANION_STAT = "net_ew_bps"  # counted beside it, never drawn

R = json.load(open(SRC_JSON, encoding="utf-8"))
QUOTERS = R["quoters"]
SRC_META = R["_meta"]

# The selection rung the report leads with is the deeper of the two the run carries; both
# rungs are counted, only the deeper one is drawn.
K_KEYS = sorted(QUOTERS)                                   # K10, K50
K_HEADLINE = max(K_KEYS, key=lambda k: int(k[1:]))         # K50
RULES = sorted(QUOTERS[K_HEADLINE])
# The fee ladder is read in the order the artifact writes it, richest rung first, so the
# horizontal axis runs from what the venue charges to what it pays.
_probe = QUOTERS[K_HEADLINE][RULES[0]]["net_by_coin"][HEADLINE_POP]["by_horizon"][H_KEY]
TIERS = list(_probe[MEASURES[0]]["by_fee_tier"])
TIER_FEE = {t: _probe[MEASURES[0]]["by_fee_tier"][t]["maker_fee_bps"] for t in TIERS}
HORIZONS = sorted(QUOTERS[K_HEADLINE][RULES[0]]["net_by_coin"][HEADLINE_POP]["by_horizon"])
POPULATIONS = sorted(QUOTERS[K_HEADLINE][RULES[0]]["net_by_coin"])
# A rung whose maker fee is negative is one the venue PAYS the maker to quote on; a rung
# at or below zero is one where the maker is not charged at all. The second set is the one
# the count of subsidised cells is taken over, and both are derived from the fee rather
# than from the rung names, which are the artifact's spelling and not a definition.
REBATE_TIERS = [t for t in TIERS if TIER_FEE[t] < 0.0]
SUBSIDISED_TIERS = [t for t in TIERS if TIER_FEE[t] <= 0.0]
CHARGED_TIERS = [t for t in TIERS if TIER_FEE[t] > 0.0]

# The third population is the union of the other two, so the grid is not as many
# independent measurements as it has cells. That is checked here and not assumed: if the
# fill counts stop adding up, the population split below would be describing something
# else and the counts taken over it would mean something else.
DISJOINT_POPULATIONS = [p for p in POPULATIONS if p != HEADLINE_POP]
for _h in HORIZONS:
    _parts = sum(QUOTERS[K_HEADLINE][RULES[0]]["net_by_coin"][p]["by_horizon"][_h]
                 [HEADLINE_MEASURE]["n_fills"] for p in DISJOINT_POPULATIONS)
    _whole = (QUOTERS[K_HEADLINE][RULES[0]]["net_by_coin"][HEADLINE_POP]["by_horizon"]
              [_h][HEADLINE_MEASURE]["n_fills"])
    if _parts != _whole:
        raise SystemExit(
            f"[reference] at {_h} the {HEADLINE_POP} population holds {_whole:,} fills "
            f"while {DISJOINT_POPULATIONS} hold {_parts:,} between them, so it is not "
            "their union and the independent-cell count below would be wrong; "
            "nothing is drawn")


def leaf(k, rule, pop, horizon, measure, tier):
    """The one address every number in this file comes from, spelled once."""
    return (QUOTERS[k][rule]["net_by_coin"][pop]["by_horizon"][horizon]
            [measure]["by_fee_tier"][tier])


def walk(rules=None, ks=None):
    """Every cell of the grid, as (k, rule, population, horizon, measure, tier, leaf).

    The walk is the population of every count this file publishes, so it is written once
    and every counter consumes it. A count taken by a second walk is a count that can
    disagree with the first one after an edit to either.
    """
    for k in (ks or K_KEYS):
        for rule in (rules or RULES):
            for pop in POPULATIONS:
                for horizon in HORIZONS:
                    for measure in MEASURES:
                        for tier in TIERS:
                            yield k, rule, pop, horizon, measure, tier, leaf(
                                k, rule, pop, horizon, measure, tier)


# ---------------------------------------------------------------------------
# The counts. Population and predicate are printed beside every one of them.
# ---------------------------------------------------------------------------
CELLS = list(walk())


def tally(rows, stat):
    """Every count this file publishes, over one row set and one summary statistic.

    Both the row set and the statistic are parameters rather than constants, because the
    two choices they stand for are exactly the two a reader must be told about: whether
    the pooled population is counted alongside the two it is built from, and whether a
    cell is summarised per dollar or per fill. Writing the counter once means the two
    answers cannot drift apart in the way two hand-written counters would.
    """
    pos = [c for c in rows if c[6][stat] > 0.0]
    return {
        "cells": len(rows),
        "positive": len(pos),
        "max": max(c[6][stat] for c in rows),
        "min": min(c[6][stat] for c in rows),
        "cells_per_fee_tier": len(rows) // len(TIERS),
        "positive_by_fee_tier": {t: sum(1 for c in pos if c[5] == t) for t in TIERS},
        "positive_on_rebate_tiers": sum(1 for c in pos if c[5] in REBATE_TIERS),
        "positive_on_subsidised_tiers": sum(1 for c in pos if c[5] in SUBSIDISED_TIERS),
        "positive_on_charged_tiers": sum(1 for c in pos if c[5] in CHARGED_TIERS),
        "positive_by_rule": dict(Counter(c[1] for c in pos).most_common()),
        "positive_by_horizon": {h: sum(1 for c in pos if c[3] == h) for h in HORIZONS},
        "positive_by_selection_rung": {k: sum(1 for c in pos if c[0] == k)
                                       for k in K_KEYS},
        "positive_by_population": {p: sum(1 for c in pos if c[2] == p)
                                   for p in POPULATIONS},
    }


ROWSETS = {
    "all_populations": lambda c: True,
    "disjoint_populations_only": lambda c: c[2] in DISJOINT_POPULATIONS,
}
counts = {
    m: {name: {stat: tally([c for c in CELLS if c[4] == m and keep(c)], stat)
               for stat in (STAT, COMPANION_STAT)}
        for name, keep in ROWSETS.items()}
    for m in MEASURES}
# The counts the panels draw and the prose quotes, named once so the two cannot diverge.
HEADLINE_COUNT = {m: counts[m]["all_populations"][STAT] for m in MEASURES}

# A predicate whose zero goes into a conclusion is calibrated on two opposite cases from
# this same artifact before that zero is believed. The case it must catch: the trade-print
# leaf of bbgl_flat at the deepest rebate on the headline slice, which is above zero. The
# case it must let pass: the same leaf on the book mid, which is not. Both are read from
# the file rather than typed, so the calibration cannot outlive the numbers it calibrates.
_best_rule = max(RULES, key=lambda r: leaf(
    K_HEADLINE, r, HEADLINE_POP, H_KEY, OTHER_MEASURE, TIERS[-1])[STAT])
_must_fire = leaf(K_HEADLINE, _best_rule, HEADLINE_POP, H_KEY, OTHER_MEASURE, TIERS[-1])
_must_stay_silent = leaf(K_HEADLINE, _best_rule, HEADLINE_POP, H_KEY,
                         HEADLINE_MEASURE, TIERS[-1])
CALIBRATION = {
    "predicate": f"{STAT} > 0",
    "must_fire": {"address": f"{K_HEADLINE}.{_best_rule}.{HEADLINE_POP}.{H_KEY}."
                             f"{OTHER_MEASURE}.{TIERS[-1]}",
                  "value": _must_fire[STAT], "fired": bool(_must_fire[STAT] > 0.0)},
    "must_stay_silent": {"address": f"{K_HEADLINE}.{_best_rule}.{HEADLINE_POP}.{H_KEY}."
                                    f"{HEADLINE_MEASURE}.{TIERS[-1]}",
                         "value": _must_stay_silent[STAT],
                         "fired": bool(_must_stay_silent[STAT] > 0.0)},
}
if not (CALIBRATION["must_fire"]["fired"]
        and not CALIBRATION["must_stay_silent"]["fired"]):
    raise SystemExit(
        f"[reference] the positivity predicate failed its calibration: "
        f"{CALIBRATION}; a count taken with an uncalibrated predicate is not published")

# ---------------------------------------------------------------------------
# The distance between the two measures, measured rather than asserted, with the residue
# BOUNDED rather than tolerated.
#
# Subtracting the two pre-fee grosses cancels the quoted half-spread, so on rows both
# measures score the distance cannot depend on which rule quoted. The two measures do not
# score identical rows, though, and on the unshared ones nothing cancels. So the run does
# not demand an exact match, which would refuse on arithmetic it can explain; it computes
# what the unshared rows can account for and refuses only above that. The bound is the
# share of rows the two measures do not share, times the widest mean extra half-spread any
# rule asks, both read from this artifact. It is an order-of-magnitude bound and not an
# inequality: it assumes the unshared rows carry ordinary notional, and a handful of very
# large prints among them could carry more.
# ---------------------------------------------------------------------------
def block(rule, horizon, measure):
    """The per-horizon block of one rule under one reference price, pooled."""
    return (QUOTERS[K_HEADLINE][rule]["net_by_coin"][HEADLINE_POP]
            ["by_horizon"][horizon][measure])


GAP_BY_HORIZON = {
    h: {r: block(r, h, OTHER_MEASURE)["gross_prefee_vw_bps"]
        - block(r, h, HEADLINE_MEASURE)["gross_prefee_vw_bps"] for r in RULES}
    for h in HORIZONS}
GAP_SPREAD = {h: max(v.values()) - min(v.values()) for h, v in GAP_BY_HORIZON.items()}

# The widest mean extra half-spread on the board, which is the most any two rules can
# disagree about what they quoted on a row.
WIDEST_EXTRA_BPS = max(
    QUOTERS[K_HEADLINE][r]["extra_half_spread_summary"]["by_coin"][HEADLINE_POP]
    ["mean_extra_half_spread_bps"] for r in RULES)
UNSHARED_ROWS = {h: abs(block(RULES[0], h, HEADLINE_MEASURE)["n_fills"]
                        - block(RULES[0], h, OTHER_MEASURE)["n_fills"])
                 for h in HORIZONS}
ROWS_SCORED = {h: block(RULES[0], h, HEADLINE_MEASURE)["n_fills"] for h in HORIZONS}
GAP_BOUND = {h: WIDEST_EXTRA_BPS * UNSHARED_ROWS[h] / ROWS_SCORED[h] for h in HORIZONS}
_over = {h: (GAP_SPREAD[h], GAP_BOUND[h]) for h in HORIZONS
         if GAP_SPREAD[h] > GAP_BOUND[h]}
if _over:
    raise SystemExit(
        f"[reference] the distance between the two reference prices varies across rules "
        f"by more than the rows they do not share can account for, at {sorted(_over)}: "
        f"observed against bound {_over}. The two measures would then differ by "
        "something other than where the clock starts, and nothing is drawn")
GAP_HEADLINE = float(np.mean(list(GAP_BY_HORIZON[H_KEY].values())))
FEE_LADDER_SPAN = float(max(TIER_FEE.values()) - min(TIER_FEE.values()))

# ---------------------------------------------------------------------------
# The six-rule counts the producer's own header states, recomputed on this artifact.
# ---------------------------------------------------------------------------
HEADER_CLAIM = {"population": "the six rules mm_bakeoff.py's header names, trade print "
                              "only, over 2 selection rungs x 3 populations x 3 "
                              "horizons x 6 fee rungs",
                "positive_cells": 244, "cells": 648, "at_headline_horizon": 46,
                "naive_at_book": 22, "as_toxicity": 58, "bbgl": 88}
HEADER_SIX = ["naive_at_book", "naive_const", "as_symmetric", "gm_vpin", "bbgl",
              "as_toxicity"]
_six = [c for c in walk(rules=HEADER_SIX) if c[4] == OTHER_MEASURE]
_six_pos = [c for c in _six if c[6][STAT] > 0.0]
HEADER_RECOMPUTED = {
    "positive_cells": len(_six_pos), "cells": len(_six),
    "at_headline_horizon": sum(1 for c in _six_pos if c[3] == H_KEY),
    **{r: sum(1 for c in _six_pos if c[1] == r)
       for r in ("naive_at_book", "as_toxicity", "bbgl")},
}
HEADER_DISAGREES = sorted(k for k, v in HEADER_CLAIM.items()
                          if k in HEADER_RECOMPUTED and HEADER_RECOMPUTED[k] != v)

# The four cells that account for the whole difference, taken by DIFFING the artifact
# across the commit that moved it rather than by guessing which addresses look likely.
# The first attempt at this block selected them by their fee rung and coin and returned
# six, because a fifth and sixth cell at neighbouring addresses were already above zero
# before the change and had no business in a list of cells that crossed it.
#
# The before-values and the two commit names are history and cannot be recomputed from
# the file on disk, so they are recorded as data. What CAN be checked is checked: the
# after-value at each address is read from today's artifact and refused if it disagrees
# with the recorded one, which keeps this block from outliving the numbers it describes.
FLIPPED_CELLS = [
    {"selection_rung": "K10", "rule": "as_toxicity", "population": "BTC",
     "horizon": "h10", "measure": "net_PRINT", "fee_tier": "rebate1",
     "before": -0.008244577659338835, "after": 0.02291115306021028},
    {"selection_rung": "K10", "rule": "as_toxicity", "population": "ETH",
     "horizon": "h10", "measure": "net_PRINT", "fee_tier": "t4_0fee",
     "before": -0.020293288130089935, "after": 0.03432855608760622},
    {"selection_rung": "K50", "rule": "as_toxicity", "population": "BTC",
     "horizon": "h10", "measure": "net_PRINT", "fee_tier": "rebate1",
     "before": -0.008244577659338835, "after": 0.02291115306021028},
    {"selection_rung": "K50", "rule": "as_toxicity", "population": "ETH",
     "horizon": "h10", "measure": "net_PRINT", "fee_tier": "t4_0fee",
     "before": -0.020293288130089935, "after": 0.03432855608760622},
]
COMMIT_BEFORE, COMMIT_AFTER = "2d6d4c7", "cb8fe74"
for _cell in FLIPPED_CELLS:
    _now = leaf(_cell["selection_rung"], _cell["rule"], _cell["population"],
                _cell["horizon"], _cell["measure"], _cell["fee_tier"])[STAT]
    if abs(_now - _cell["after"]) > 1e-12 or not (_cell["before"] < 0.0 < _now):
        raise SystemExit(
            f"[reference] the recorded crossing at {_cell} no longer matches the "
            f"artifact, which now reads {_now!r}; the block describing which cells "
            "crossed zero is stale and nothing is drawn")

# ---------------------------------------------------------------------------
# Panel A: the headline slice, one band per measure across the fee ladder.
# ---------------------------------------------------------------------------
X = np.arange(len(TIERS), dtype=float)
BAND = {}
for m in MEASURES:
    vals = np.array([[leaf(K_HEADLINE, r, HEADLINE_POP, H_KEY, m, t)[STAT]
                      for t in TIERS] for r in RULES], dtype=float)
    BAND[m] = {"min": vals.min(axis=0), "max": vals.max(axis=0),
               "median": np.median(vals, axis=0)}

COLOUR = {OTHER_MEASURE: "#c2570a", HEADLINE_MEASURE: "#1f5fa8"}
LABEL = {OTHER_MEASURE: "trade print (optimistic)",
         HEADLINE_MEASURE: "book mid (reported)"}

fig, (axA, axB) = plt.subplots(
    1, 2, figsize=(WIDTH_IN, HEIGHT_IN), layout="constrained",
    gridspec_kw={"width_ratios": [1.35, 1.0]})

# The rungs where the maker is charged nothing are shaded in BOTH panels, because the
# dependence on the fee rung is the second finding this figure carries and the sharper of
# the two: 86 per cent of the positive cells live inside this shading. The boundary is
# placed from the fee itself, halfway between the last charged rung and the first free
# one, so it moves if the schedule does.
_first_free = TIERS.index(SUBSIDISED_TIERS[0])
for _ax in (axA, axB):
    _ax.axvspan(_first_free - 0.5, len(TIERS) - 0.5, color="#7a7a7a", alpha=0.07,
                linewidth=0.0, zorder=1)

for m in MEASURES:
    axA.fill_between(X, BAND[m]["min"], BAND[m]["max"], color=COLOUR[m], alpha=0.22,
                     linewidth=0.0, zorder=2)
    axA.plot(X, BAND[m]["max"], color=COLOUR[m], linewidth=1.0, linestyle=(0, (3, 2)),
             zorder=3)
    axA.plot(X, BAND[m]["min"], color=COLOUR[m], linewidth=1.0, linestyle=(0, (3, 2)),
             zorder=3)
    axA.plot(X, BAND[m]["median"], color=COLOUR[m], linewidth=1.6, marker="o",
             markersize=2.8, label=LABEL[m], zorder=4)

axA.axhline(0.0, color="#111111", linewidth=1.3, zorder=5)
# The fee rungs are labelled by what the venue charges, without a plus sign: six signed
# labels on a two-inch panel collide, and the sign that matters is the minus.
TICK_TEXT = [f"{TIER_FEE[t]:g}" for t in TIERS]
axA.set_xticks(X)
axA.set_xticklabels(TICK_TEXT)
axA.set_xlabel("maker fee, bps  (1.5 = base; negative = paid)", fontsize=PT_LABEL)
axA.set_ylabel("net maker result, bps of notional", fontsize=PT_LABEL)
axA.set_title(f"eleven rules, {int(H_HEADLINE)} s, both coins pooled", fontsize=PT_TITLE)
axA.grid(axis="y", color="#cccccc", linewidth=0.4, zorder=0)
axA.set_axisbelow(True)
axA.margins(x=0.03)
# Headroom for the one line a reader needs in order to read the band correctly.
_lo, _hi = axA.get_ylim()
axA.set_ylim(_lo, _hi + 0.14 * (_hi - _lo))
axA.annotate("band: worst to best of the eleven; line: median",
             xy=(0.03, 0.955), xycoords="axes fraction", fontsize=PT_NOTE,
             color="#444444", va="top")
# The shading is a second statement and needs its own words, at the bottom of the panel
# where the bands are not.
axA.annotate("shaded: no fee, or the venue pays",
             xy=((_first_free - 0.5 + len(TIERS) - 0.5) / 2.0, 0.03),
             xycoords=("data", "axes fraction"), fontsize=PT_NOTE, color="#555555",
             ha="center", va="bottom")

# ---------------------------------------------------------------------------
# Panel B: the whole grid, counted. The zero of the book-mid series is the claim that the
# left panel is not a special slice.
# ---------------------------------------------------------------------------
W = 0.38
for i, m in enumerate(MEASURES):
    heights = [HEADLINE_COUNT[m]["positive_by_fee_tier"][t] for t in TIERS]
    axB.bar(X + (i - 0.5) * W, heights, width=W, color=COLOUR[m], alpha=0.85,
            linewidth=0.0, label=LABEL[m], zorder=3)
    for x, hgt in zip(X, heights):
        axB.annotate(f"{hgt:d}", xy=(x + (i - 0.5) * W, hgt), xytext=(0, 1.5),
                     textcoords="offset points", ha="center", va="bottom",
                     fontsize=PT_NOTE, color=COLOUR[m])

axB.axhline(0.0, color="#111111", linewidth=1.3, zorder=5)
axB.set_xticks(X)
axB.set_xticklabels(TICK_TEXT)
axB.set_xlabel("maker fee, bps", fontsize=PT_LABEL)
axB.set_ylabel(f"cells above zero (by notional), of "
               f"{HEADLINE_COUNT[MEASURES[0]]['cells_per_fee_tier']:d}",
               fontsize=PT_LABEL)
axB.set_title(f"all {HEADLINE_COUNT[MEASURES[0]]['cells']:,} cells per measure",
              fontsize=PT_TITLE)
axB.grid(axis="y", color="#cccccc", linewidth=0.4, zorder=0)
axB.set_axisbelow(True)
axB.set_ylim(0, HEADLINE_COUNT[MEASURES[0]]["cells_per_fee_tier"] * 1.14)
axB.margins(x=0.06)
# A series that is zero everywhere draws nothing, so the panel says in words what the
# absent bars mean. Without this the reader sees one series and cannot tell that the
# other one was drawn and came out flat.
axB.annotate("book mid: none at any rung", xy=(0.5, 0.96), xycoords="axes fraction",
             fontsize=PT_NOTE, color=COLOUR[HEADLINE_MEASURE], ha="center", va="top")

# One legend for both panels, below them, so neither panel spends plotting area on it and
# the counts on the right are read with the same key as the bands on the left.
handles, labels = axA.get_legend_handles_labels()
fig.legend(handles, labels, loc="outside lower center", ncols=2, frameon=False,
           handlelength=1.8, borderaxespad=0.1)

fig.savefig(OUT_PNG, dpi=DPI_OUT)
plt.close(fig)

# ---------------------------------------------------------------------------
# The results file: every number drawn, plus the ones the caption needs.
# ---------------------------------------------------------------------------
results = {
    "what_this_answers": (
        "whether the report's conclusion that no quoting rule is profitable is a "
        "property of the rules or of the choices the result is measured under. It is a "
        "property of the choices, and there are two of them. On the book mid no cell of "
        f"the {HEADLINE_COUNT[HEADLINE_MEASURE]['cells']:,}-cell grid is above zero on "
        f"the notional-weighted column, and on the trade print "
        f"{HEADLINE_COUNT[OTHER_MEASURE]['positive']:,} of them are. Of those, "
        f"{HEADLINE_COUNT[OTHER_MEASURE]['positive_on_subsidised_tiers']:,} need a fee "
        "rung at or below zero, so the fee schedule is the second and sharper "
        "dependence"),
    "figure": os.path.basename(OUT_PNG),
    "grid": {
        "rules": RULES, "selection_rungs": K_KEYS, "populations": POPULATIONS,
        "horizons": HORIZONS, "fee_tiers": TIERS, "maker_fee_bps_by_tier": TIER_FEE,
        "rebate_tiers": REBATE_TIERS, "subsidised_tiers": SUBSIDISED_TIERS,
        "charged_tiers": CHARGED_TIERS,
        "cells_per_measure": HEADLINE_COUNT[MEASURES[0]]["cells"],
        "address": ("quoters[K][rule].net_by_coin[coin].by_horizon[h][measure]"
                    ".by_fee_tier[tier]"),
        "cells_are_not_independent": {
            "why": (f"the {HEADLINE_POP} population is the union of "
                    f"{DISJOINT_POPULATIONS}, verified here by fill count at every "
                    "horizon rather than assumed, so a third of the cells are "
                    "re-aggregations of the other two thirds"),
            "disjoint_populations": DISJOINT_POPULATIONS,
            "cells_over_disjoint_populations_only": (
                counts[MEASURES[0]]["disjoint_populations_only"][STAT]["cells"]),
        },
    },
    "counts_by_measure": counts,
    "how_to_read_the_counts": (
        "two choices decide every count here and both are spelled out rather than "
        f"defaulted. The row set is either all {len(POPULATIONS)} populations or only "
        f"the {len(DISJOINT_POPULATIONS)} disjoint ones, and the summary statistic is "
        f"either {STAT}, weighted by notional, or {COMPANION_STAT}, weighted per fill. "
        "The headline claim uses all populations and the notional weighting. It does "
        "not depend on the first choice and it does depend on the second: the book mid "
        f"has {counts[HEADLINE_MEASURE]['all_populations'][STAT]['positive']} positive "
        f"cells by notional but "
        f"{counts[HEADLINE_MEASURE]['all_populations'][COMPANION_STAT]['positive']} per "
        "fill, so any sentence about it has to name which"),
    "predicate_calibration": CALIBRATION,
    "distance_between_the_two_measures": {
        "definition": ("pre-fee gross on the trade print minus pre-fee gross on the "
                       "book mid, pooled, notional-weighted"),
        "by_horizon_bps": {h: float(np.mean(list(v.values())))
                           for h, v in GAP_BY_HORIZON.items()},
        "spread_across_rules_bps": GAP_SPREAD,
        "spread_bound_from_unshared_rows_bps": GAP_BOUND,
        "unshared_rows": UNSHARED_ROWS,
        "rows_scored": ROWS_SCORED,
        "widest_mean_extra_half_spread_bps": WIDEST_EXTRA_BPS,
        "headline_bps": GAP_HEADLINE,
        "fee_ladder_span_bps": FEE_LADDER_SPAN,
        "reading": (
            "the distance does not grow with the horizon, so it is a difference in "
            "where the measurement starts and not a difference in drift. At the "
            f"headline horizon it is {GAP_HEADLINE:.4f} bps against a fee schedule "
            f"spanning {FEE_LADDER_SPAN:.1f} bps end to end. It is the same for every "
            f"rule to within {GAP_SPREAD[H_KEY]:.1e} bps there, and the residue is "
            "accounted for: the two reference prices score row sets differing by "
            f"{UNSHARED_ROWS[H_KEY]} of {ROWS_SCORED[H_KEY]:,} fills, and on those rows "
            "the quoted half-spread has nothing to cancel against. The spread across "
            "rules stays under that allowance at all three horizons and tracks the "
            "number of unshared rows in the same order"),
    },
    "headline_slice_drawn": {
        "selection_rung": K_HEADLINE, "population": HEADLINE_POP, "horizon": H_KEY,
        "statistic": STAT,
        "by_measure": {m: {"min_by_tier": dict(zip(TIERS, BAND[m]["min"].tolist())),
                           "median_by_tier": dict(zip(TIERS, BAND[m]["median"].tolist())),
                           "max_by_tier": dict(zip(TIERS, BAND[m]["max"].tolist()))}
                       for m in MEASURES},
    },
    "producer_header_count_recomputed": {
        "why": ("the header of mm_bakeoff.py states a count of positive trade-print "
                "cells over its own six-rule grid. It is recomputed here on the "
                "committed artifact, over exactly the population the header names, so "
                "that the two counts can be compared rather than assumed to agree"),
        "stated_in_mm_bakeoff_header": HEADER_CLAIM,
        "recomputed_here": HEADER_RECOMPUTED,
        "fields_that_disagree": HEADER_DISAGREES,
        "cells_that_crossed_zero": FLIPPED_CELLS,
        "crossed_between_commits": {"before": COMMIT_BEFORE, "after": COMMIT_AFTER,
                                    "what_changed": "the entry mid became a snapshot "
                                                    "taken strictly before the fill"},
        "how_the_four_were_identified": (
            "by diffing every one of the 1,296 leaves of this artifact across the two "
            "commits and keeping those whose sign changed, not by selecting addresses "
            "that looked likely. Selecting by fee rung and coin returns six, two of "
            "which were already above zero beforehand"),
        "reading": ("the header's 244 and 46 belong to the artifact as it stood before "
                    "the entry mid was moved; the four cells above crossed zero at that "
                    "commit and have stayed above it since, which is 58 to 62 for "
                    "as_toxicity and 46 to 50 at the headline horizon. The header's 22 "
                    "for naive_at_book and 88 for bbgl still hold"),
    },
    "where_the_positive_cells_sit": {
        "at_the_base_rung": HEADLINE_COUNT[OTHER_MEASURE]["positive_by_fee_tier"][TIERS[0]],
        "at_the_discounted_rung": (
            HEADLINE_COUNT[OTHER_MEASURE]["positive_by_fee_tier"][CHARGED_TIERS[-1]]),
        "on_rungs_the_venue_charges_for": (
            HEADLINE_COUNT[OTHER_MEASURE]["positive_on_charged_tiers"]),
        "on_rungs_at_or_below_zero_fee": (
            HEADLINE_COUNT[OTHER_MEASURE]["positive_on_subsidised_tiers"]),
        "on_the_three_rebate_rungs": (
            HEADLINE_COUNT[OTHER_MEASURE]["positive_on_rebate_tiers"]),
        "share_needing_zero_fee_or_a_rebate": (
            HEADLINE_COUNT[OTHER_MEASURE]["positive_on_subsidised_tiers"]
            / HEADLINE_COUNT[OTHER_MEASURE]["positive"]),
        "reading": (
            "positivity on the trade print is mostly a subsidised-rung phenomenon, and "
            "the statement has to be made in three parts because the two-part version "
            "of it is false. One positive cell sits at the base rung an ordinary maker "
            f"pays. {HEADLINE_COUNT[OTHER_MEASURE]['positive_by_fee_tier'][CHARGED_TIERS[-1]]} "
            f"sit at the {TIER_FEE[CHARGED_TIERS[-1]]} bps rung, which is a real and "
            "attainable rung of the schedule, so saying that only one positive cell "
            "survives at a genuine venue rung would be wrong. The remaining "
            f"{HEADLINE_COUNT[OTHER_MEASURE]['positive_on_subsidised_tiers']} need the "
            "venue to charge nothing or to pay. Reaching the rebate rungs is not a "
            "modelling choice: money/maker_econ.py records that six maker addresses of "
            "9,367 in this window reached the turnover share the deepest rung asks for"),
    },
    "caption_this_figure_needs": (
        "Net maker result on one common set of late-window fills, under the two "
        "reference prices the same run publishes. Left: the reported slice, both coins "
        f"pooled at {int(H_HEADLINE)} s and the {K_HEADLINE[1:]}-fill selection rung, "
        "each band spanning the worst and best of the eleven quoting rules across the "
        "venue's six maker fee rungs. Right: how many cells of the whole grid sit above "
        "zero at each rung. ALL COUNTS ARE NOTIONAL-WEIGHTED; the equal-weighted column "
        "of the same cells gives "
        f"{counts[OTHER_MEASURE]['all_populations'][COMPANION_STAT]['positive']} and "
        f"{counts[HEADLINE_MEASURE]['all_populations'][COMPANION_STAT]['positive']} "
        "instead, so the book mid is not free of positive cells per fill. The grid holds "
        f"{HEADLINE_COUNT[MEASURES[0]]['cells']:,} cells per reference price but not that "
        f"many independent measurements: the pooled population is the union of "
        f"{' and '.join(DISJOINT_POPULATIONS)}, and over the "
        f"{counts[MEASURES[0]]['disjoint_populations_only'][STAT]['cells']} cells of "
        "those two alone the counts are "
        f"{counts[OTHER_MEASURE]['disjoint_populations_only'][STAT]['positive']} and "
        f"{counts[HEADLINE_MEASURE]['disjoint_populations_only'][STAT]['positive']}. "
        "Shading marks the rungs where the maker is charged nothing or paid; "
        f"{HEADLINE_COUNT[OTHER_MEASURE]['positive_on_subsidised_tiers']} of the "
        f"{HEADLINE_COUNT[OTHER_MEASURE]['positive']} positive cells lie inside it. No "
        "uncertainty band is drawn: the artifact carries a bootstrap interval per cell "
        "and 2,376 of them cannot be shown at this size."),
}

scope_block = {
    "population": (
        f"{HEADLINE_COUNT[MEASURES[0]]['cells']:,} scored cells per reference "
        f"price, being "
        f"{len(RULES)} quoting rules x {len(K_KEYS)} counterparty-selection rungs x "
        f"{len(POPULATIONS)} populations x {len(HORIZONS)} horizons x {len(TIERS)} maker "
        f"fee rungs, every one of them read from mm_bakeoff_results.json. The fills "
        f"underneath are that file's own: " + str(SRC_META["scope"]["population"])[:220]),
    "window": SRC_META["scope"]["window"],
    "coins": SRC_META["scope"]["coins"],
}

settings_used = dict(
    h=H_HEADLINE,
    lens=H.HEADLINE_LENS,
    master_seed=None, n_perm=None, n_boot=None,
    overrides_note=(
        "this file draws and computes no new quantity of the market: every net figure "
        "is read from mm_bakeoff_results.json, and the only things computed here are "
        "counts, minima, maxima and medians over those figures, all of them "
        "deterministic. No random stream is drawn, so no seed, no permutation count and "
        "no bootstrap count applies, and each is stated as not applying rather than "
        "left to be read as the declaration. The horizon and the reference price are "
        "read from settings.py at run time and are never typed here; both reference "
        "prices are counted because the whole question is what changes between them"),
)

artifact.write(os.path.basename(OUT_JSON), results,
               script=__file__, inputs=[SRC_JSON], scope=scope_block,
               settings=settings_used, started=T0,
               out_dir=os.path.dirname(OUT_JSON))

print(f"[reference] wrote {os.path.basename(OUT_PNG)} and {os.path.basename(OUT_JSON)}")
print(f"[reference] predicate {STAT} > 0 calibrated: fires on "
      f"{CALIBRATION['must_fire']['address']} ({CALIBRATION['must_fire']['value']:+.4f}), "
      f"silent on {CALIBRATION['must_stay_silent']['address']} "
      f"({CALIBRATION['must_stay_silent']['value']:+.4f})")
for m in MEASURES:
    for rowset in ROWSETS:
        vw, ew = counts[m][rowset][STAT], counts[m][rowset][COMPANION_STAT]
        print(f"[reference] {m:14} {rowset:26} {vw['positive']:4d} of "
              f"{vw['cells']:,} cells above zero by notional, {ew['positive']:4d} per "
              f"fill; best cell {vw['max']:+.4f} bps")
print(f"[reference] the two measures stand {GAP_HEADLINE:.4f} bps apart at "
      f"{int(H_HEADLINE)} s, alike across all {len(RULES)} rules to "
      f"{GAP_SPREAD[H_KEY]:.1e} bps against an allowance of {GAP_BOUND[H_KEY]:.1e} from "
      f"{UNSHARED_ROWS[H_KEY]} unshared rows; the fee schedule spans "
      f"{FEE_LADDER_SPAN:.1f} bps")
_print = HEADLINE_COUNT[OTHER_MEASURE]
print(f"[reference] of {_print['positive']} positive trade-print cells, "
      f"{_print['positive_by_fee_tier'][TIERS[0]]} sit at the base rung, "
      f"{_print['positive_by_fee_tier'][CHARGED_TIERS[-1]]} at the "
      f"{TIER_FEE[CHARGED_TIERS[-1]]} bps rung, and "
      f"{_print['positive_on_subsidised_tiers']} "
      f"({100.0 * _print['positive_on_subsidised_tiers'] / _print['positive']:.0f} per "
      f"cent) need zero fee or a rebate")
print(f"[reference] {HEADLINE_POP} is the union of {DISJOINT_POPULATIONS}, verified by "
      f"fill count at every horizon, so the independent grid is "
      f"{counts[MEASURES[0]]['disjoint_populations_only'][STAT]['cells']} cells per "
      "measure")
if HEADER_DISAGREES:
    print(f"[reference] mm_bakeoff.py's header count disagrees on {HEADER_DISAGREES}: "
          f"stated {[HEADER_CLAIM[k] for k in HEADER_DISAGREES]}, recomputed "
          f"{[HEADER_RECOMPUTED[k] for k in HEADER_DISAGREES]}")
