"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-20
References: Avellaneda, Stoikov (2008) High-frequency trading in a limit order book;
           Glosten, Milgrom (1985) adverse selection; Hyperliquid node-data S3;
           Zenodo 18184441 (Albers et al. 2026).
"""

# ---------------------------------------------------------------------------
# OBJECT T1 + T2 - COUNTERPARTY-TOXICITY-SKEWED MARKET-MAKING BACKTEST.
#
# A counterparty-aware maker is compared against a SYMMETRIC Avellaneda-Stoikov-
# style baseline (one that quotes the same spread to every wallet, conditioning
# only on inventory, never on counterparty identity). The aware maker ranks each
# wallet by realized toxicity on an EARLY window, then on a LATER window widens
# or declines against the wallets it pre-identified as toxic.
#
# HONEST FRAMING (NON-NEGOTIABLE - this is the whole point of the object). The
# gross volume-weighted mean 60s taker markout in this window is ~0.56 bps, which
# sits BELOW the perpetual taker-fee floor of ~2.5-4.5 bps (plus funding). A NET
# trading edge is therefore IMPOSSIBLE on this flow and is NEVER claimed anywhere
# in this object - not in the json, not in the printout, not in the docstring.
# The ONLY defensible deliverable is the RELATIVE REDUCTION in the markout-
# measured adverse-selection COST that a counterparty-aware maker achieves versus
# a symmetric maker. Every number below is a cost or a cost-reduction, never an
# alpha, a P&L, or a Sharpe. Skewing also forgoes BENIGN (non-toxic) volume, and
# that given-up volume is reported beside every cost reduction so the tradeoff is
# explicit - declining toxic flow is not free.
#
# What this object is and is NOT:
#   - It IS a counterfactual on REALIZED markout: given the trades that actually
#     printed, how much adverse-selection cost would a maker who declined/widened
#     against pre-identified toxic wallets have avoided?
#   - It is NOT a live fill model. There is no limit-order-book simulation, no
#     queue position, no fill probability, no requote latency. Declining a toxic
#     wallet is modelled as not paying that wallet's realized markout cost (and
#     forgoing its notional), NOT as a re-cleared book. So this is VALIDATION /
#     ILLUSTRATION of the cost-reduction mechanism, not a powered live-performance
#     claim. Stated in the json caveats and the printout.
#
# Design:
#   T1. OOS early/late split. Rank counterparties by toxicity (per-wallet mean
#       mo10) on the EARLY half (days 4-8, >= MIN_RANK_TRADES early trades to be
#       ranked). EVALUATE on the LATE half (days 9-13). The split is by TIME, so
#       no wallet's late data informs its own ranking. Two makers run on the late
#       flow:
#         SYMMETRIC baseline - faces all late flow, pays the realized
#           adverse-selection cost = sum(mo10/1e4 * notional) over late trades.
#         SKEW maker - against wallets in the top toxicity quantile on the early
#           half it avoids a fraction of their flow. Policies tried:
#             (a) decline_top_decile  - drop 100% of top-10% wallets' late flow
#             (b) widen_top_decile_50 - avoid 50% of top-10% wallets' late flow
#             (c) decline_top_quartile / widen variants (panel)
#       Reported per policy: late-half cost, cost REDUCTION vs symmetric, and the
#       BENIGN (non-toxic, i.e. negative- or zero-cost) volume given up.
#   T2. Walk-forward. Instead of one split, roll the train window day by day:
#       rank on all days up to and including t, evaluate on day t+1. LEAD on the
#       MEDIAN fold reduction (the series is heavy-tailed; the mean is blown up by
#       outlier folds with a near-zero symmetric base) and report the mean and the
#       full per-fold series alongside it so OOS deterioration is visible (L13/L14
#       discipline). Report whether the median reduction persists or decays.
#   Robustness:
#     - Label-permutation (COUNT-matched) placebo: shuffle the toxicity ranking
#       (seed 20260619, N_PLACEBO = 2000 shuffles, p-floor 1/2001 ~ 0.0005). The
#       null draws a RANDOM set of the same NUMBER of wallets. A real reduction must
#       beat a random-ranking maker; report placebo p = fraction of shuffles whose
#       reduction >= observed. WEAKNESS this null does NOT control for: toxic wallets
#       are ALSO large, so a count-matched random set turns away far less notional
#       than the toxic set; its mean reduction (~6.9% pooled/BTC) understates the
#       pure-size baseline and inflates how much of the headline looks toxicity-
#       specific.
#     - SIZE-MATCHED placebo (adversarial-audit fix): draw random wallet sets matched
#       on TOTAL LATE NOTIONAL of the observed toxic set, by stratified sampling
#       within total-notional deciles (greedy nearest-notional top-up to hit the
#       target), N_SIZE_PLACEBO draws. This null turns away the SAME dollar volume
#       as the toxicity screen, so its reduction is the PURE-SIZE baseline (avoiding
#       big wallets lowers cost regardless of who they are). Report its mean (~30.4%)
#       / p95 (~56.6%) and the p-value of the observed (toxicity-ranked) reduction
#       vs THIS null (~0.002). That p is a MONTE CARLO TAIL PROBABILITY under the
#       draw procedure declared here and nothing wider: it is the share of this
#       null's draws that reached the observed reduction. It does NOT establish the
#       statistical significance of wallet identity. What the gap between the
#       observed reduction and the size-matched mean measures is how much of the cut
#       is left once the same dollar volume is turned away at random.
#       BASELINE-BY-SIZE-ALONE: ranking wallets by total late notional (no toxicity)
#       and declining the top decile is also reported as a single deterministic
#       size-only screen (~44.9%), to show where pure size lands without randomness.
#     - JOINT-MATCHED placebo (external-referee fix, 2026-08-30): each of the two nulls
#       above holds ONE axis and lets the other run. The count-matched one fixes how MANY
#       wallets are declined and lets the notional go where it will; the size-matched one
#       fixes how MUCH notional, to within its own stratified-draw miss, and lets the count
#       run from 66 to 2004 wallets where the observed set holds 206. Clearing both of them
#       SEPARATELY is not clearing one null that holds both AT ONCE, because a set is free
#       to satisfy either constraint by breaking the other, and the joint constraint is what
#       the objection actually names. This third null draws sets holding EXACTLY the
#       observed number of wallets AND a total late notional within JOINT_PLACEBO_TOL_PCT of
#       the observed set's, by a swap walk that never leaves that region. It constrains
#       MORE than either neighbour, and the measurement of where that puts it is the
#       opposite of what was expected: its draws sit HIGHER, not lower. On this run its mean
#       reduction is 34.64 per cent pooled on the declared lens against the size-matched
#       null's 28.55, and above it on three of the four other cells that produced both.
#       Holding the count as well as the volume forces every draw to RESEMBLE the toxic set,
#       and sets that resemble it recover more of its cost reduction, so this null stands
#       NEARER the observed value. Clearing it is therefore a stronger result and not a
#       weaker one.
#       It does NOT replace either of the other two. All three are published side by side,
#       because each holds a different thing constant and answers a different objection.
#       WHAT IT COSTS TO BE THAT STRICT, measured on 2026-08-30 and not hidden: there is no
#       closed form for a draw from that region, so the sets come from a swap walk, and on
#       this data that walk does NOT forget where it started. The reason is the size of the
#       set's OWN largest members and the absence of anything to put in their place: each
#       cell publishes the reading at joint_matched_placebo.region_freedom, whose
#       top_members says what share of the target the biggest members carry and how many
#       wallets of the whole pool sit within the band of each. The block runs those eight
#       starts, requires them to agree about the
#       TAIL -- the only thing the published fraction reads -- and REFUSES to publish any
#       number where they do not. On the run of 2026-08-30 that refuses one cell of the six,
#       BTC on the declared book-mid lens, where the share of draws reaching the observed
#       reduction runs from nought to ninety-one per cent depending on the start; the other
#       five, BTC on the print lens included, pass with every start at zero.
#     - Whale robustness: drop the 10 single largest-notional wallets and
#       re-evaluate, confirming the reduction is not just declining one/two giants.
#
#   FILL-MODEL EXTENSION (NOTED, NOT IMPLEMENTED HERE). The standing "no fill model"
#   objection is answered by a minimal fill model: recapture a fraction f of the
#   declined toxic notional at a WIDENED quote (so a share of the avoided flow still
#   trades, at a worse price for the taker / better for the maker) and charge a
#   per-requote penalty. That converts the cost-reduction counterfactual into a
#   net-of-recapture number. It is a planned extension and is NOT run here.
#
#   NON-POSITIVE-BASE GUARD (adversarial-verification fix). A reduction percentage
#   is reported ONLY where the symmetric maker actually PAID a positive adverse-
#   selection cost (sym_cost > 0). When sym_cost <= 0 the symmetric maker was net
#   PAID by the flow, so avoided/sym is a signed-sum artefact that can exceed 100%
#   and would smuggle an alpha claim through a cost ratio; in that regime the json
#   reports the dollar levels plus a flag 'reduction_undefined_nonpositive_base'
#   and NO percentage. Where defined, the displayed reduction is capped at 100%.
#
#   HEADLINE SCOPE, derived 2026-08-27. Which slices are defensible headlines is
#   READ OFF THIS RUN by _headline_grounds, not declared: a slice is demoted where
#   dropping the largest wallets leaves a non-positive symmetric base, or where
#   its walk-forward median reduction is below zero. The demotion that stood here
#   until 2026-08-27 was a literal sentence keyed on a coin's name, and both of
#   the grounds it stated had gone stale unnoticed because nothing re-read them.
#
# numpy-only, fixed seed, vectorized (bincount / masks / cumulative sums - no
# per-trade Python loops over the millions of rows). Reads ONE shared intermediate
# (quickwin_markouts.npz) produced by the expensive orchestrator pass; only the v1
# fields are used (taker_id, coin, day, mo10, mo60, notional, taker_side) so it
# runs unchanged on the v2 superset.
#
#   TWO LENSES, BOTH PUBLISHED (2026-08-03). The whole object runs twice, once against
#   the trade print and once against the book mid, and every block lives under
#   <slice>.by_measure.<lens>. Until that date it ran on the print alone and said so
#   nowhere in a key: the lens was an argument to np.load, so a reader could not see
#   which reference price a cost had been measured against. The two are far apart --
#   volume-weighted mean 10s markout 2.2388 bps on the mid, 0.5208 on the print -- and
#   the reason is structural rather than noise: the print already contains the spread
#   the maker earned, so a cost measured on it is a cost net of income. The book mid is
#   what settings.HEADLINE_LENS declares and what adverse selection is defined against
#   here, so it leads; the print stays because the maker is genuinely paid at the print
#   and because earlier versions of this study quote it.
#
# Run command (bare python3 is BLOCKED on this machine). The pinned form is the one
# requirements.txt governs; the short `--with numpy` form does NOT honour the pins,
# measured 2026-08-03:
#   uv run --no-project --with-requirements requirements.txt python3 -u \
#       t1_toxicity_skew_backtest.py
# ---------------------------------------------------------------------------

import os
import sys
import time

import numpy as np

# artifact.py, settings.py and the other shared modules sit in the
# repository root, one directory up from this group, so the path is built
# from this file's own location and never from the working directory the
# run happens to start in.
_CODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CODE_DIR not in sys.path:
    sys.path.insert(0, _CODE_DIR)

import artifact
import panel_io as P
import settings as H
import stats

# -------------------- configuration --------------------
HERE = os.path.dirname(os.path.abspath(__file__))
# Located by panel_io rather than joined here, so the one place that knows where
# the markout panels live is the one place that has to change if they move.
NPZ_PATH = os.path.join(P.data_root(), "quickwin_markouts.npz")
# The book-mid panel of the SAME fills in the same row order, read since 2026-08-03 so
# that this object publishes both lenses instead of having one wired into its input.
MID_NPZ_PATH = P.panel_path("mid")
RESULTS_PATH = os.path.join(HERE, "t1_backtest_results.json")

COIN_CODES = H.coin_labels("quickwin")   # the map belongs to the FILE, not the project

# THE RANKING AND EVALUATION HALVES ARE DERIVED, NOT DECLARED. Both names are
# OVERRIDE HOOKS and default to None, which means "split the days the input actually
# carries" through settings.split_early_late (see _early_late_masks). They used to be
# the literal tuples (4,5,6,7,8) and (9,10,11,12,13), which are days of the MONTH and
# are right only for a window opening on the 4th and closing on the 13th. This input
# does open on the 4th, so the derived split reproduces those tuples exactly and no
# number here moves.
#
# WHY THEY CARRY _OVERRIDE IN THE NAME, renamed here 2026-07-31, following gm_quoter.py,
# which took the same suffix earlier that day in commit ff3b8fe.
# They used to be spelled EARLY_DAYS and LATE_DAYS, which are
# the names settings.py owns for the day split, and the settings gate read them as this
# file declaring that setting a second time -- two of the sites it reports. The reading
# was right about the name and wrong about the value: there is no value here to migrate,
# because the split already comes from settings.py and what these two hold is the
# ABSENCE of an override. A name that states a setting its value does not come from is
# the defect settings.py calls out in its own second rule, so the repair is to make the
# name say what the object is. Nothing else in the tree reads either name: they are used
# only by _early_late_days below, so the rename moves nothing -- None before, None after.
EARLY_DAYS_OVERRIDE = None
LATE_DAYS_OVERRIDE = None

MIN_RANK_TRADES = H.RANK_FLOOR_FILLS  # min early-window trades for a wallet to be ranked
HEADLINE_HORIZON = H.HEADLINE_HORIZON_S   # the headline markout drives the cost
COMPANION_HORIZON = H.COMPANION_HORIZON_S  # reported alongside, never the headline

PER_TAKER_FEE_BPS = (2.5, 4.5)      # perpetual taker fee band for the honest comparison

# Skew policies on the late-half flow. Each = (label, top-quantile of toxic
# wallets to act against, fraction of THAT flow the maker avoids). avoid_frac = 1.0
# is a hard decline; 0.5 is a soft widen that turns away half the flow.
SKEW_POLICIES = (
    ("decline_top_decile",    0.10, 1.0),
    ("widen_top_decile_50",   0.10, 0.5),
    ("decline_top_quartile",  0.25, 1.0),
    ("widen_top_quartile_50", 0.25, 0.5),
)
HEADLINE_POLICY = "decline_top_decile"

N_PLACEBO = H.N_PERM                # COUNT-matched label-permutation shuffles (p-floor 1/2001 ~ 0.0005)
N_SIZE_PLACEBO = H.perm_draws("t1_size_matched_placebo")
                                    # SIZE-matched random draws (notional-stratified),
                                    # READ from settings.py. The budget is the same 1000
                                    # this file has always drawn, so no placebo p moves;
                                    # settings.PERM_DRAWS_BY_PURPOSE records beside it
                                    # that 1000 leaves no margin over the corrected
                                    # threshold, which is a separate question from where
                                    # the number lives
SIZE_PLACEBO_DECILES = 10           # notional strata for the size-matched draw

# ---- the JOINT-matched null, added 2026-08-30 -------------------------------------
# TOLERANCE ON THE VOLUME AXIS, in per cent of the target notional. A joint null cannot
# hold the notional EXACTLY and no declaration can make it: wallet notionals are real
# numbers, and a subset of a FIXED size will not sum to an arbitrary target to the cent.
# So the volume axis is held to a band, and the band is declared here rather than chosen
# inside the sampler.
#
# WHY ONE PER CENT. It is set against the neighbouring null's OWN miss on the same axis,
# measured on this tree on 2026-08-30 and not assumed. The size-matched draw's total
# notional misses its target by a p95 of 6.1185 per cent on the pooled cell of the
# declared lens -- the SMALLEST miss of the six published cells -- and by 57.7974 per cent
# on the BTC cell, which is the largest. One per cent is therefore six times stricter than
# the neighbour where the neighbour is at its best, and fifty-eight times stricter where it
# is at its worst, on the very axis that neighbour is named after.
JOINT_PLACEBO_TOL_PCT = 1.0

# HOW THE SWAP WALK IS STEPPED, IN ATTEMPTED SWAPS AND NOT IN ACCEPTED ONES. The
# distinction is the correctness of the sampler and not a tuning choice. The walk is a
# Metropolis chain with a symmetric proposal and an acceptance of one inside the region and
# zero outside, so its stationary distribution is UNIFORM over the region only when the
# chain is read at fixed TIMES. Reading it after a fixed number of ACCEPTED moves reads it
# at a stopping time instead, and the post-jump distribution weights every set by its own
# acceptance probability, which favours the sets sitting in the middle of the tolerance
# band. Measured on the pooled cell of the declared lens on 2026-08-30, that alone moved the
# null's mean reduction from 37.5 to 33.5 per cent -- in the direction that makes the null
# easier and the observed result look better.
#
# THE LENGTHS ARE NOT WHAT DECIDES THIS NULL, and that too is measured rather than assumed.
# Lengthening the step from a thousand attempts to forty thousand moved the pooled mean by
# less than a percentage point and did not close the disagreement between starts on BTC at
# all. What buys evidence here is more STARTS, not longer runs, so the budget is spent on
# JOINT_PLACEBO_CHAINS chains rather than on one long one.
JOINT_PLACEBO_BURN_ATTEMPTS = 20000
JOINT_PLACEBO_STEP_ATTEMPTS = 4000

# HOW OFTEN A MOVE SWAPS TWO WALLETS FOR TWO INSTEAD OF ONE FOR ONE. This is not a tuning
# knob either: under single swaps alone the largest wallet of a set is FROZEN for the whole
# chain, because a wallet worth 45.7 per cent of the target cannot be replaced by any single
# other wallet without leaving a band one per cent wide. Measured on the BTC cell on
# 2026-08-30, every one of a thousand draws of a chain carried the same largest wallet, at
# 45.7 per cent of the target from one start and 69.3 from another. A move that removes two
# and admits two has a second degree of freedom to absorb the difference, and it unfreezes:
# the same cell then ranged over 38.7 to 45.7 per cent within one chain. Both proposals are
# symmetric, so the mixture is symmetric and the stationary distribution is unchanged.
JOINT_PLACEBO_PAIR_PROB = 0.5

# HOW MANY INDEPENDENT STARTS, and why there is more than one. The region is measurably NOT
# connected under these moves on this data: the observed set's own largest members carry most
# of its notional and the pool holds nothing to swap them for one for one, which is published
# per cell at joint_matched_placebo.region_freedom, and eight chains from
# eight independent random starts disagree about the null on every cell of the declared
# lens. This comment blamed a pool wallet worth 142.6 per cent of the target until 2026-08-30;
# that wallet exceeds the target plus the band, so it can sit in no admissible set and is not
# in the observed set either, and it was never the obstacle. A single chain's draws are therefore a property of where it started. Eight starts
# make that visible and let the block refuse the cells where it matters; they do not make
# the sampler uniform, and nothing here claims they do.
JOINT_PLACEBO_CHAINS = 8

# THE BAR THE STARTS HAVE TO CLEAR, in binomial standard deviations. Each chain's share of
# draws reaching the observed reduction has to sit within this many standard deviations of
# the share pooled over the chains; where the pooled share is zero, every chain has to be
# zero. Three sigma is the conventional bar and it is calibrated on two live cells rather
# than chosen, and BOTH CASES CARRY THEIR ADDRESS so neither can go stale unnoticed again:
# every cell publishes joint_matched_placebo.chain_agreement, holding per_chain_tail_fractions
# for the eight shares this bar is applied to, pooled_tail_fraction for the centre it measures
# them against, allowed_departure for the bar in the same units, and agree for the verdict.
# Read the pair there. On the run of 2026-08-30 it is five cells passing with every chain at
# zero against one failing, BTC on the declared book-mid lens, whose shares run from nought
# to 0.912. This comment carried "zero to 39 per cent" and "the BTC cell" until that date,
# with no address to check either against, and both had gone stale: the spread is more than
# twice as wide as the number said -- 91.2 per cent against 39, a ratio of 2.338 -- and BTC
# on the PRINT lens is not the failing cell at all: it passes with every chain at zero like
# the other four. The test is on the TAIL and not on
# the null's location, because the location is start-dependent on every cell here while the
# tail is what the published tail fraction counts. That fraction is NOT called a p-value:
# the region's distribution is not established here, so the number is a property of the
# draws and the block says so in its own claim.
JOINT_PLACEBO_CHAIN_AGREEMENT_SIGMA = 3.0

# Safety cap on the greedy walk INTO the region from a random starting set. It is a cap and
# not a budget: the entry takes a few hundred swaps on every cell of this tree, and the cap
# exists so that a region that turned out to be unreachable ends the run with a stated
# refusal instead of a loop that never returns.
JOINT_PLACEBO_ENTRY_ATTEMPT_CAP = 400000

# How many candidate swaps the greedy entry draws from the generator at a time. It is a
# batch size and not a limit: the loop stops the moment the set lands inside the band, and
# on this tree entry takes between 42 and 2059 swaps, so it never reaches the end of a
# first batch. It is declared here rather than left inline because the notebook redraws
# this null from the same stream, and a batch of a different size would ask the generator
# for a different count and walk a different chain. Nothing published depends on its
# value; everything published depends on the two copies agreeing.
JOINT_PLACEBO_ENTRY_BLOCK = 4096

# THE BUDGET. These draws become a published TAIL FRACTION, floored the way a permutation
# p is floored, so the budget is the one min_perm_draws() sizes
# for that job and it is taken through settings.N_PERM, exactly as the count-matched null
# above takes it. It is deliberately NOT an entry in settings.PERM_DRAWS_BY_PURPOSE: that
# map is for draws answering a different question, and settings.perm_draws says so in the
# message it raises.
N_JOINT_PLACEBO = N_PLACEBO

PLACEBO_POLICY = "decline_top_decile"   # policy the placebo null is built around

# THE WHALE CHECK HERE DROPS BY NOTIONAL, and that is a different question from the
# one t3_capacity.py asks. Dropping the largest wallets by NOTIONAL answers "is this
# reduction a volume artifact"; dropping them by COST answers "is this ten wallets".
# This file has always dropped by notional and used to write the result under a key
# naming only the count, so the two files' whale checks looked interchangeable and
# were not. settings.whale_drop builds a key that states both.
WHALE_DROP_K = H.WHALE_DROP_K
WHALE_DROP_CRITERION = "notional"
WHALE_DROP_KEY = H.whale_drop(WHALE_DROP_CRITERION, WHALE_DROP_K)["key"]

# READ from settings.py, which declares 20260619 for this purpose, so every placebo
# stream is the one the published p-values were drawn from and nothing moves. The value
# is kept at its own number on purpose and is recorded as an override in the settings
# fingerprint: settings.MASTER_SEED is 20260620 and carries the state "target", so
# adopting THAT re-draws every placebo stream and moves every published placebo number.
# That is a measured change owed its own recompute, not a side effect of a renaming pass.
RNG_SEED = H.seed_for("t1_toxicity_skew_backtest")

FEE_NOTE = (
    f"COST REDUCTION, NOT NET ALPHA. The gross volume-weighted mean "
    f"{H.HEADLINE_HORIZON_S}s markout on "
    "this flow (~0.52 bps observed at 10s, ~0.56 at 60s) is BELOW the perpetual "
    "taker-fee floor "
    "(~2.5-4.5 bps) plus funding, so a net trading edge is impossible and is never "
    "claimed. Every figure here is a maker COST or a relative reduction in that "
    "cost from counterparty-aware screening, never a profit."
)
SCOPE_NOTE = (
    "Counterfactual on REALIZED markout, not a live fill model: no limit-order-book "
    "simulation, no queue/fill-probability, no requote. Declining a wallet = not "
    "paying its realized markout cost and forgoing its notional. Single December "
    "window, trade-print reference (a cost, not an information edge). This is "
    "VALIDATION / ILLUSTRATION of the cost-reduction mechanism, not a powered "
    "live-performance claim."
)


# -------------------- helpers --------------------
def _early_late_days(day):
    """The (early, late) day tuples for the days actually in front of us.

    With neither override set the days present go through settings.split_early_late,
    a function OF THE DAYS, so the split is right on a window of any length. An
    override supplies one half explicitly; the other half is then every present day
    that is not in it, so an injected half cannot leave its partner on another
    month's day numbers.
    """
    present = sorted(int(d) for d in np.unique(np.asarray(day, dtype=np.int64)))
    if EARLY_DAYS_OVERRIDE is None and LATE_DAYS_OVERRIDE is None:
        return H.split_early_late(present)
    early = tuple(d for d in present
                  if EARLY_DAYS_OVERRIDE is not None
                  and d in set(int(x) for x in EARLY_DAYS_OVERRIDE))
    if LATE_DAYS_OVERRIDE is None:
        late = tuple(d for d in present if d not in set(early))
    else:
        late = tuple(d for d in present
                     if d in set(int(x) for x in LATE_DAYS_OVERRIDE))
    if not early:
        early = tuple(d for d in present if d not in set(late))
    return early, late


def _early_late_masks(day):
    """Row masks for the derived early and late halves. One place builds them, so no
    two blocks of this file can end up on different splits."""
    d = np.asarray(day, dtype=np.int64)
    early_days, late_days = _early_late_days(d)
    return (np.isin(d, np.asarray(early_days, dtype=np.int64)),
            np.isin(d, np.asarray(late_days, dtype=np.int64)))


def _safe_div(num, den):
    """num / den, returning 0.0 when the denominator is non-finite or zero."""
    if den is None or not np.isfinite(den) or den == 0.0:
        return 0.0
    return float(num / den)


def _reduction_frac(avoided_cost, sym_cost):
    """Cost reduction as a fraction of the symmetric baseline, GUARDED against a
    non-positive base.

    A reduction percentage is only meaningful when the symmetric maker actually
    PAID a positive adverse-selection cost. When sym_cost <= 0 the symmetric maker
    was net PAID by the flow (or broke even), so avoided_cost/sym_cost is a signed-
    sum artefact that can exceed 100% or flip sign and would smuggle an alpha claim
    in through a cost ratio. In that regime we return (None, True): no fraction is
    defined and the caller reports the dollar levels plus a flag instead.

    Where defined (sym_cost > 0) the fraction is clipped to [.., 1.0] so a displayed
    reduction never exceeds 100% of the cost that was actually there to avoid.
    Returns (fraction_or_None, undefined_nonpositive_base_flag)."""
    if sym_cost is None or not np.isfinite(sym_cost) or sym_cost <= 0.0:
        return None, True
    frac = float(avoided_cost / sym_cost)
    if frac > 1.0:
        frac = 1.0
    return frac, False


def _pct_or_none(frac, ndigits=3):
    """Render a reduction fraction as a percentage, or None when the fraction is
    undefined (non-positive symmetric base). Keeps the json honest: an undefined
    reduction is the JSON null, never a fabricated number."""
    if frac is None:
        return None
    return round(frac * 100.0, ndigits)


def _cost_of(cost_rows, mask=None):
    """Total signed adverse-selection cost over selected rows (a maker LOSS when
    positive). cost_rows is the per-trade (mo/1e4)*notional already computed."""
    if mask is None:
        return float(np.sum(cost_rows))
    return float(np.sum(cost_rows[mask]))


def _rank_by_markout(taker_id, mo_score, early_mask):
    """Per-wallet EARLY-window mean markout on whichever column the caller hands in,
    over wallets with >= MIN_RANK_TRADES early trades.

    THE LENS IS THE CALLER'S AND IS NOT A PROPERTY OF THIS FUNCTION, which is why the
    name no longer says "print". Until 2026-08-03 this file ran on the trade-print
    column alone: main() passed settings.headline_print_col() and nothing else, while
    settings.HEADLINE_LENS declares the book mid, so the object's lens was wired into
    its input rather than stated in a key and a reader had no way to see which of the
    two columns a figure came off. Since that date main() runs the whole object twice,
    once per lens, and every block sits under by_measure.<lens>. The two columns are
    not interchangeable: the volume-weighted mean 10s markout is 2.2388 bps on the
    book mid against 0.5208 on the trade print, measured in i4_midmarkout_results.json,
    because the print already contains the spread the maker earned.

    Returns (wallet_ids, score) where score is the mean markout; higher = costlier to
    the maker. Only wallets clearing the trade floor are returned, so a wallet must
    have a real early track record before it can be screened. The ranking uses EARLY
    rows ONLY, so no late-half data informs a wallet's score.
    """
    tid = np.asarray(taker_id, dtype=np.int64)
    mo = np.asarray(mo_score, dtype=np.float64)
    valid = early_mask & np.isfinite(mo)

    e_tid = tid[valid]
    e_mo = mo[valid]
    if e_tid.size == 0:
        return np.empty(0, np.int64), np.empty(0, np.float64)

    uniq, inv = np.unique(e_tid, return_inverse=True)
    csum = np.bincount(inv, weights=e_mo, minlength=uniq.size)
    ccnt = np.bincount(inv, minlength=uniq.size)
    keep = ccnt >= MIN_RANK_TRADES
    ids = uniq[keep]
    score = csum[keep] / np.maximum(ccnt[keep], 1)
    return ids.astype(np.int64), score.astype(np.float64)


def _top_quantile_mask(ranked_ids, ranked_score, top_quantile):
    """Boolean over ranked_ids selecting the top_quantile of wallets this backtest
    screens against, ordered by the score _rank_by_markout returns on the lens the
    caller is running.

    THE CUT IS SIZED WITH floor AND THE DECLARED CUT IS SIZED WITH ceil, which is the
    second place this selection departs from the declared one. On 2 069 ranked
    counterparties ceil takes 207 and floor takes 206, so the two sets differ by the
    single counterparty sitting on the boundary. That is one wallet and it is not
    nothing: it is why the same phrase, spelled in two files, named two sets.

    Returns a mask aligned to ranked_ids. With ties at the cutoff the higher-scoring
    wallets are taken first (stable sort on -score)."""
    n = ranked_ids.size
    if n == 0:
        return np.zeros(0, dtype=bool)
    n_top = max(1, int(np.floor(n * top_quantile)))
    order = np.argsort(-ranked_score, kind="stable")
    screened = np.zeros(n, dtype=bool)
    screened[order[:n_top]] = True
    return screened


def _late_skew_cost(late_tid, late_cost_rows, late_notional,
                    screened_ids, avoid_frac):
    """Late-half cost and forgone-flow accounting for a skew maker that avoids
    avoid_frac of the flow from wallets in toxic_ids.

    Vectorized: a per-trade boolean 'is_toxic_wallet' is built with np.isin, then
    the avoided cost and avoided notional are the (avoid_frac-scaled) sums over
    those rows. No per-trade Python loop.

    Returns a dict with the skew maker's residual cost, the cost it avoided, the
    notional it gave up, and a split of that given-up notional into the toxic part
    (cost-positive intent) and the benign part (rows whose own realized cost was
    <= 0, i.e. flow that was NOT adverse and is pure lost volume)."""
    sym_cost = _cost_of(late_cost_rows)
    sym_notional = float(np.sum(late_notional))

    if screened_ids.size == 0:
        red_frac, undefined_base = _reduction_frac(0.0, sym_cost)
        return {
            "symmetric_cost_usd": sym_cost,
            "skew_cost_usd": sym_cost,
            "cost_avoided_usd": 0.0,
            "cost_reduction_frac": red_frac,
            "reduction_undefined_nonpositive_base": undefined_base,
            "notional_given_up_usd": 0.0,
            "notional_given_up_frac": 0.0,
            "benign_notional_given_up_usd": 0.0,
            "benign_share_of_given_up": 0.0,
            "n_late_trades_touched": 0,
        }

    in_screened = np.isin(late_tid, screened_ids)         # per-trade membership, vectorized
    avoided_cost = avoid_frac * _cost_of(late_cost_rows, in_screened)
    avoided_notional = avoid_frac * float(np.sum(late_notional[in_screened]))

    # benign portion of the given-up flow: toxic-wallet rows whose OWN realized
    # cost was <= 0 (the maker would NOT have been adversely selected on them).
    # This is the volume the skew maker sacrifices with no cost benefit.
    benign_rows = in_screened & (late_cost_rows <= 0.0)
    benign_notional = avoid_frac * float(np.sum(late_notional[benign_rows]))

    skew_cost = sym_cost - avoided_cost
    red_frac, undefined_base = _reduction_frac(avoided_cost, sym_cost)
    return {
        "symmetric_cost_usd": sym_cost,
        "skew_cost_usd": skew_cost,
        "cost_avoided_usd": avoided_cost,
        "cost_reduction_frac": red_frac,
        "reduction_undefined_nonpositive_base": undefined_base,
        "notional_given_up_usd": avoided_notional,
        "notional_given_up_frac": _safe_div(avoided_notional, sym_notional),
        "benign_notional_given_up_usd": benign_notional,
        "benign_share_of_given_up": _safe_div(benign_notional, avoided_notional),
        "n_late_trades_touched": int(in_screened.sum()),
    }


# -------------------- T1: single early/late split --------------------
def _t1_split(taker_id, day, mo_score, notional, late_cost_rows, cell=None):
    """T1 result block for one slice: rank on EARLY, evaluate every skew policy on
    LATE, plus the placebo and whale-robustness checks for the headline policy.

    cell is the (slice, lens) pair this block is being computed for. It carries no
    arithmetic: it is passed down so that the joint null's refusal can NAME the cell it is
    refusing, instead of describing an unidentified one. It defaults to None so that a
    caller with nothing to say about its cell still runs."""
    early_mask, late_mask = _early_late_masks(day)

    ranked_ids, ranked_score = _rank_by_markout(taker_id, mo_score, early_mask)

    late_tid = taker_id[late_mask]
    late_cost = late_cost_rows[late_mask]
    late_not = notional[late_mask]

    sym_cost = _cost_of(late_cost)
    sym_notional = float(np.sum(late_not))

    block = {
        "n_ranked_wallets": int(ranked_ids.size),
        "n_late_trades": int(late_mask.sum()),
        "symmetric_late_cost_usd": round(sym_cost, 2),
        "symmetric_late_notional_usd": round(sym_notional, 2),
        "policies": {},
    }

    for label, quant, avoid_frac in SKEW_POLICIES:
        screened_mask = _top_quantile_mask(ranked_ids, ranked_score, quant)
        screened_ids = ranked_ids[screened_mask]
        res = _late_skew_cost(late_tid, late_cost, late_not, screened_ids, avoid_frac)
        block["policies"][label] = {
            "top_quantile": quant,
            "avoid_fraction": avoid_frac,
            "n_toxic_wallets": int(screened_ids.size),
            "symmetric_cost_usd": round(res["symmetric_cost_usd"], 2),
            "skew_cost_usd": round(res["skew_cost_usd"], 2),
            "cost_avoided_usd": round(res["cost_avoided_usd"], 2),
            "cost_reduction_pct": _pct_or_none(res["cost_reduction_frac"]),
            "reduction_undefined_nonpositive_base": res["reduction_undefined_nonpositive_base"],
            "notional_given_up_usd": round(res["notional_given_up_usd"], 2),
            "notional_given_up_pct": round(res["notional_given_up_frac"] * 100.0, 3),
            "benign_notional_given_up_usd": round(res["benign_notional_given_up_usd"], 2),
            "benign_share_of_given_up_pct": round(res["benign_share_of_given_up"] * 100.0, 3),
        }

    block["placebo"] = _t1_placebo(
        ranked_ids, late_tid, late_cost, late_not, sym_cost)
    block["size_matched_placebo"] = _t1_size_matched_placebo(
        ranked_ids, ranked_score, late_tid, late_cost, late_not, sym_cost)
    # The third null, which holds the two axes the two above hold one each. It is added
    # BESIDE them and replaces neither: dropping the null a result passes in favour of the
    # null it also passes would be choosing the test by its answer.
    block["joint_matched_placebo"] = _t1_joint_matched_placebo(
        ranked_ids, ranked_score, late_tid, late_cost, late_not, sym_cost, cell=cell)
    # The key states the count AND the criterion, because dropping the largest
    # wallets by notional and by cost are different checks with different answers.
    block[f"whale_robustness_{WHALE_DROP_KEY}"] = _t1_whale_robust(
        taker_id, day, mo_score, notional, late_cost_rows, late_mask, early_mask)
    return block


def _t1_placebo(ranked_ids, late_tid, late_cost, late_not, sym_cost):
    """Label-permutation placebo for the headline policy. The OBSERVED reduction
    ranks wallets by real toxicity; the null shuffles which wallets are labelled
    'toxic' (same count, random identity) and recomputes the reduction. A real
    reduction must beat the random-ranking maker.

    p = fraction of shuffles whose cost reduction >= observed (p-floor
    1/(N_PLACEBO+1)). The number of 'toxic' wallets is held fixed at the headline
    policy's count so the placebo turns away the SAME amount of flow, isolating the
    value of WHO is screened from how much is screened."""
    quant = dict((lab, q) for lab, q, _ in SKEW_POLICIES)[PLACEBO_POLICY]
    avoid_frac = dict((lab, a) for lab, _, a in SKEW_POLICIES)[PLACEBO_POLICY]
    n = ranked_ids.size
    out = {
        "policy": PLACEBO_POLICY,
        "n_shuffles": N_PLACEBO,
        "seed": RNG_SEED,
        # The floor has one home. stats.p_floor re-exports settings.p_floor, whose body
        # is 1.0 / (n_perm + 1) -- the expression that stood here, over the same operand
        # in the same order, so the float is the same float and not merely the same
        # value. What the move buys is that a budget and its smallest expressible p can
        # no longer be changed apart.
        "p_floor": stats.p_floor(N_PLACEBO),
    }
    if n == 0 or not np.isfinite(sym_cost) or sym_cost <= 0.0:
        out.update({"observed_reduction_pct": None, "placebo_mean_reduction_pct": None,
                    "placebo_p": None,
                    "reduction_undefined_nonpositive_base": (n != 0),
                    "note": ("no ranked wallets" if n == 0 else
                             "undefined_nonpositive_base: symmetric cost <= 0, "
                             "no reduction percentage is defined")})
        return out

    n_top = max(1, int(np.floor(n * quant)))

    # The null draws a RANDOM set of n_top wallets (same count as the real toxic
    # set) and recomputes the reduction, isolating the value of WHO is screened
    # from how MUCH flow is turned away. The observed reduction it is compared
    # against is recomputed cleanly by the caller (_observed_headline_reduction)
    # and the p-value is finalised there, so this helper only builds the null.
    rng = np.random.default_rng(RNG_SEED)
    placebo_reductions = np.empty(N_PLACEBO, dtype=np.float64)
    for b in range(N_PLACEBO):
        perm_idx = rng.choice(n, size=n_top, replace=False)
        perm_ids = ranked_ids[perm_idx]
        in_screened = np.isin(late_tid, perm_ids)
        avoided = avoid_frac * _cost_of(late_cost, in_screened)
        # sym_cost > 0 is guaranteed here (guarded above); cap each shuffle's
        # reduction at 100% so the null and the observed statistic share the floor.
        frac, _ = _reduction_frac(avoided, sym_cost)
        placebo_reductions[b] = frac

    out["placebo_mean_reduction_pct"] = round(float(placebo_reductions.mean()) * 100.0, 4)
    out["placebo_p95_reduction_pct"] = round(
        float(np.percentile(placebo_reductions, 95)) * 100.0, 4)
    out["_placebo_reductions"] = placebo_reductions  # consumed by caller, then dropped
    return out


def _wallet_totals(ranked_ids, late_tid, values):
    """Total of a per-trade column per ranked wallet, aligned to ranked_ids.

    Vectorized: sum `values` over rows grouped by taker, then look up each ranked
    wallet. Wallets with no late rows get 0.

    ONE BODY, TWO QUESTIONS. This used to be written only for notional. The joint null
    below needs the same grouping over the per-trade COST, and the honest way to have it
    is to ask this function rather than to retype its five lines with one name changed:
    a copied body is the defect this tree records under "a check that reprints the rule
    is blind to a change in the rule". The arithmetic is untouched, so no number moved
    when the notional caller became a one-line delegation."""
    n = ranked_ids.size
    if n == 0:
        return np.zeros(0, dtype=np.float64)
    uniq, inv = np.unique(late_tid, return_inverse=True)
    by_wallet = np.bincount(inv, weights=values, minlength=uniq.size)
    # map ranked_ids -> their total via searchsorted into uniq
    pos = np.searchsorted(uniq, ranked_ids)
    pos = np.clip(pos, 0, uniq.size - 1)
    present = (uniq[pos] == ranked_ids)
    out = np.where(present, by_wallet[pos], 0.0)
    return out.astype(np.float64)


def _wallet_notional(ranked_ids, late_tid, late_not):
    """Total LATE notional per ranked wallet, aligned to ranked_ids.

    This is the size axis the size-matched null is built on, and the axis the toxic set
    is 'also large' along."""
    return _wallet_totals(ranked_ids, late_tid, late_not)


def _wallet_late_cost(ranked_ids, late_tid, late_cost):
    """Total LATE adverse-selection cost per ranked wallet, aligned to ranked_ids.

    The joint null scores thousands of draws, and scoring each one by np.isin over every
    late trade would walk the whole trade array once per draw. Grouping the cost by wallet
    once turns each draw into a sum over its own wallets. It is the SAME sum in a different
    order, and the two orders are compared on the observed set before any draw is counted
    -- see wallet_path_vs_row_path_rel_gap."""
    return _wallet_totals(ranked_ids, late_tid, late_cost)


def _draw_size_matched_set(rng, ranked_not, target_notional, deciles):
    """Draw a random wallet-index set whose TOTAL late notional matches
    target_notional, by stratified sampling within notional deciles.

    Strategy: bucket ranked wallets into `deciles` strata by their own late
    notional. Shuffle wallets WITHIN each stratum (preserving the size profile of
    the toxic set is approximated by drawing across all strata in random order),
    then greedily add wallets until the accumulated notional reaches the target.
    The last wallet may overshoot; the draw stops at the first wallet that meets or
    crosses the target so each draw turns away ~the same dollar volume as the toxic
    set. Returns a boolean mask over ranked wallets.

    This isolates the PURE-SIZE effect: the set is selected to match how-much
    (notional), NOT who (toxicity), so its cost reduction is what avoiding that much
    volume buys with no information about counterparty toxicity."""
    n = ranked_not.size
    if n == 0 or target_notional <= 0.0:
        return np.zeros(n, dtype=bool)

    # rank wallets by notional, split into `deciles` strata, draw a random order
    # that visits strata in random sequence and wallets within a stratum at random.
    order_by_size = np.argsort(ranked_not, kind="stable")
    strata = np.array_split(order_by_size, deciles)
    visit = []
    stratum_order = rng.permutation(len(strata))
    for s in stratum_order:
        idx = strata[s].copy()
        rng.shuffle(idx)
        visit.append(idx)
    draw_order = np.concatenate(visit) if visit else np.empty(0, dtype=np.int64)

    csum = np.cumsum(ranked_not[draw_order])
    # first position whose cumulative notional meets/exceeds the target
    hit = int(np.searchsorted(csum, target_notional, side="left"))
    hit = min(hit, draw_order.size - 1)
    # stop at whichever of (just-before, at-hit) leaves the accumulated notional
    # CLOSEST to the target, so the draw is centred on the target rather than
    # always overshooting (an upward bias would inflate the null's reduction).
    if hit > 0:
        over = csum[hit] - target_notional
        under = target_notional - csum[hit - 1]
        if under < over:
            hit -= 1
    chosen = draw_order[: hit + 1]
    mask = np.zeros(n, dtype=bool)
    mask[chosen] = True
    return mask


def _t1_size_matched_placebo(ranked_ids, ranked_score, late_tid, late_cost,
                             late_not, sym_cost):
    """SIZE-MATCHED null + a deterministic size-only baseline for the headline policy.

    The COUNT-matched placebo (_t1_placebo) controls for HOW MANY wallets are
    screened but not for HOW MUCH notional, and toxic wallets are also large, so it
    understates the pure-size baseline. This null instead draws random wallet sets
    whose TOTAL late notional matches the observed toxic set's, recomputes the
    reduction per draw, and reports the mean / p95 of that pure-size distribution
    plus the Monte Carlo tail probability of the observed (toxicity-ranked) reduction
    against it: the share of draws from THIS declared procedure that reached it. That
    tail is not a significance verdict on wallet identity. The gap between the observed
    reduction and this size-matched mean is what is left of the cut once the same
    dollar volume is turned away at random.

    Also reports a single deterministic SIZE-ONLY screen: rank wallets by total late
    notional (no toxicity at all) and decline the same top decile by NUMBER of
    wallets. Because that concentrates on the very largest wallets it turns away MORE
    notional than the toxic set and is an UPPER BOUND on what pure size buys (not the
    same dollar volume as the size-matched null - that role belongs to the random
    draw, whose mean ~30-34% is the like-for-like pure-size baseline)."""
    quant = dict((lab, q) for lab, q, _ in SKEW_POLICIES)[PLACEBO_POLICY]
    avoid_frac = dict((lab, a) for lab, _, a in SKEW_POLICIES)[PLACEBO_POLICY]
    n = ranked_ids.size
    out = {
        "policy": PLACEBO_POLICY,
        "n_draws": N_SIZE_PLACEBO,
        "n_notional_strata": SIZE_PLACEBO_DECILES,
        # THE SEED THE STREAM WAS ACTUALLY MADE WITH, which until 2026-08-30 this key
        # did not hold: it wrote RNG_SEED while the generator below is built from
        # RNG_SEED + 1, so a reader who took the recorded number literally drew a
        # different stream from the one that produced these numbers. The arithmetic did
        # not move -- the generator was always RNG_SEED + 1 -- only the record of it.
        # The +1 is written as the same expression the generator takes, so the two
        # cannot drift apart again.
        "seed": RNG_SEED + 1,
        # Same one home as the count-matched block above, and the same expression:
        # stats.p_floor is settings.p_floor is 1.0 / (n_perm + 1). Bit-identical.
        "p_floor": stats.p_floor(N_SIZE_PLACEBO),
        "matched_on": "total late notional of the observed toxic set",
    }
    if n == 0 or not np.isfinite(sym_cost) or sym_cost <= 0.0:
        out.update({
            "target_toxic_notional_usd": None,
            "size_matched_mean_reduction_pct": None,
            "size_matched_p95_reduction_pct": None,
            "size_only_top_decile_by_notional_reduction_pct": None,
            "observed_reduction_pct": None,
            "toxicity_vs_size_matched_p": None,
            "toxicity_beats_size_matched": False,
            "reduction_undefined_nonpositive_base": (n != 0),
            "note": ("no ranked wallets" if n == 0 else
                     "undefined_nonpositive_base: symmetric cost <= 0, no reduction "
                     "percentage is defined"),
        })
        return out

    ranked_not = _wallet_notional(ranked_ids, late_tid, late_not)

    # observed toxic set: top-quantile by toxicity score
    screened_mask = _top_quantile_mask(ranked_ids, ranked_score, quant)
    screened_ids = ranked_ids[screened_mask]
    target_notional = float(np.sum(ranked_not[screened_mask]))
    in_screened_obs = np.isin(late_tid, screened_ids)
    obs_avoided = avoid_frac * _cost_of(late_cost, in_screened_obs)
    obs_frac, _ = _reduction_frac(obs_avoided, sym_cost)

    # deterministic size-only baseline: top decile by notional, no toxicity
    n_top = max(1, int(np.floor(n * quant)))
    size_order = np.argsort(-ranked_not, kind="stable")
    size_only_ids = ranked_ids[size_order[:n_top]]
    in_size_only = np.isin(late_tid, size_only_ids)
    size_only_avoided = avoid_frac * _cost_of(late_cost, in_size_only)
    size_only_frac, _ = _reduction_frac(size_only_avoided, sym_cost)

    # size-matched random null
    rng = np.random.default_rng(RNG_SEED + 1)   # distinct stream from count-matched
    size_reductions = np.empty(N_SIZE_PLACEBO, dtype=np.float64)
    drawn_notional = np.empty(N_SIZE_PLACEBO, dtype=np.float64)
    for b in range(N_SIZE_PLACEBO):
        mask = _draw_size_matched_set(rng, ranked_not, target_notional,
                                      SIZE_PLACEBO_DECILES)
        draw_ids = ranked_ids[mask]
        drawn_notional[b] = float(np.sum(ranked_not[mask]))
        in_draw = np.isin(late_tid, draw_ids)
        avoided = avoid_frac * _cost_of(late_cost, in_draw)
        frac, _ = _reduction_frac(avoided, sym_cost)
        size_reductions[b] = frac

    # The counting belongs to stats.permutation_p and this call is the same test it
    # was: one-sided at `draw >= observed - tol`, the +1 floor, and the denominator the
    # count of usable draws -- which here equals the budget, because _reduction_frac
    # returns a finite fraction whenever the symmetric base is positive and that is
    # guarded above, so no draw of this null can come back NaN.
    #
    # The tolerance is passed as an ABSOLUTE 1e-12, the value this file already used,
    # rather than the module's default, which scales with the comparison. That is a
    # declared departure -- the returned block records tolerance_rule as "absolute,
    # stated by the caller" -- and taking the default instead would move the p on any
    # cell where a draw sits within a whisker of the observed reduction.
    perm = stats.permutation_p(obs_frac, size_reductions, side="greater",
                               abs_tol=1e-12, n_requested=N_SIZE_PLACEBO,
                               cell=("t1_size_matched_placebo", PLACEBO_POLICY))
    p_val = perm["p"]

    # NAME REPAIR, 2026-08-30, AND ONLY THE NAME. stats.permutation_p stamps every block it
    # returns with its own name, "label permutation", and that name is right for the caller
    # it was written for and wrong for this one. A label permutation holds the number of
    # objects EXACTLY and shuffles which of them carry the label -- that is the count-matched
    # placebo above, and there the stamped name stands. This null holds the NOTIONAL and lets
    # the count run: _draw_size_matched_set stops at the first wallet whose cumulative
    # notional lands nearest the target, so a draw takes however many wallets that took, and
    # nothing here holds that number. The counting is untouched and not one number moves --
    # the tail count, the +1 floor and the usable denominator are the same arithmetic this
    # file has always run, and a Monte Carlo tail over independent draws of a declared
    # procedure is a p and stays a p. What could not stand is a field naming a procedure
    # this is not. Written beside the write the way the joint null's is, so the name and the
    # block it describes cannot drift apart.
    perm["procedure"] = (
        "notional-matched stratified draw, counted -- NOT a label permutation. Each draw "
        "takes wallets across notional strata until its TOTAL LATE NOTIONAL lands nearest "
        "the observed toxic set's, so the notional is the axis held and the NUMBER of "
        "wallets is not held at all: it is whatever the draw needed and it varies from draw "
        "to draw. The p is a Monte Carlo tail over independent draws of THIS procedure. "
        "This field read 'label permutation' until 2026-08-30, the name stats.permutation_p "
        "writes for every caller, and it was wrong for this null: a label permutation holds "
        "the count exactly and shuffles the labels, which is the count-matched placebo "
        "beside this one and not this draw. Only the name moved on that date; the counting "
        "and every number it produced are unchanged.")

    out.update({
        "size_matched_procedure": perm,
        "target_toxic_notional_usd": round(target_notional, 2),
        "mean_drawn_notional_usd": round(float(drawn_notional.mean()), 2),
        "size_matched_mean_reduction_pct": round(float(size_reductions.mean()) * 100.0, 4),
        "size_matched_p95_reduction_pct": round(
            float(np.percentile(size_reductions, 95)) * 100.0, 4),
        "size_only_top_decile_by_notional_reduction_pct": _pct_or_none(size_only_frac, 4),
        "size_only_note": ("UPPER bound on pure size: top decile by NUMBER of wallets "
                           "ranked on notional concentrates on the largest wallets and "
                           "turns away more notional than the toxic set; the like-for-"
                           "like pure-size baseline is the size-matched RANDOM mean."),
        "observed_reduction_pct": round(obs_frac * 100.0, 4) if obs_frac is not None else None,
        "toxicity_vs_size_matched_p": round(p_val, 6),
        "toxicity_beats_size_matched": bool(p_val <= 0.05),
        "reduction_undefined_nonpositive_base": False,
        "note": ("observed toxicity-ranked reduction is the cost cut from declining "
                 "WHO is toxic; size-matched mean is the cost cut from declining the "
                 "same HOW-MUCH (notional) at random; the gap is what remains of the "
                 "cut once the same dollar volume is turned away at random. "
                 "toxicity_vs_size_matched_p beside it is a MONTE CARLO TAIL "
                 "PROBABILITY under the draw procedure this block declares -- the "
                 "share of those draws reaching the observed value -- and NOT a test "
                 "of the statistical significance of wallet identity. "
                 "toxicity_beats_size_matched is that tail read against 0.05 and "
                 "carries no wider claim. Until 2026-08-30 this note called the gap "
                 "'significant at toxicity_vs_size_matched_p' and 'the marginal value "
                 "of toxicity', which asserted more than the draws support; only the "
                 "wording moved on that date and no number with it."),
    })
    return out


def _joint_member_substitutability(ranked_not, screened_mask, target_notional, tol_abs,
                                   top_k=3):
    """HOW MUCH ROOM THE REGION LEAVES THE WALK, measured on the wallets that decide it.

    Added 2026-08-30, because until then this file explained its own refusals by an object
    that is not in the problem. The story was that one pool wallet worth 142.6 per cent of
    the target blocks the walk. It blocks nothing: being larger than the target plus the
    band it can sit in no admissible set at all, and it is not in the observed toxic set
    either. What actually decides a draw is measured here.

    WHAT IS COUNTED. A draw holds the observed set's wallet COUNT exactly and its notional
    to within the band, so a SINGLE swap moves the total by the difference between the
    wallet it drops and the one it admits, and is admissible only when that difference fits
    the band. For each of the largest members this counts the wallets of the whole ranked
    pool lying within the band of it -- ITSELF INCLUDED, so a count of one means no other
    wallet in the pool can take its place one for one. Beside it goes the share of the
    target those members carry, which is the same quantity for the null's degeneracy: where
    the largest members carry most of the target, every admissible draw is a near-copy of
    the observed set, and the null grows stricter and less informative together.

    WHAT IT DOES NOT SAY, stated because the neighbouring text once overstated exactly this.
    A count of one is NOT a proof that the member is stuck. The walk also proposes PAIRED
    swaps, two out and two in, and those carry a second degree of freedom; measured on
    2026-08-30, a paired swap dropping the largest member exists for every partner choice on
    every cell of this tree. It is rare rather than impossible -- about two ordered pairs sit
    in the band for the first partner on the BTC cell of the declared lens against about 130
    on the ETH cell -- and rarity is what the chains show when they disagree.

    The count is over the whole ranked pool rather than over non-members alone, so it is the
    same predicate for a member and for a hypothetical replacement, and its floor is one by
    construction. Cost is one pass per member reported.
    """
    members = np.where(screened_mask)[0]
    if (members.size == 0 or not np.isfinite(target_notional)
            or target_notional <= 0.0):
        return {"note": "no screened members, or no positive target notional, so the "
                        "region has no reading on this cell"}
    order = members[np.argsort(-ranked_not[members], kind="stable")]
    shown = order[:int(top_k)]
    rows = []
    for rank, i in enumerate(shown, 1):
        rows.append({
            "rank": rank,
            "share_of_target_pct": round(
                float(ranked_not[i]) / target_notional * 100.0, 3),
            "one_for_one_swaps_in_band": int(
                np.sum(np.abs(ranked_not - ranked_not[i]) <= tol_abs)),
        })
    return {
        "top_members": rows,
        "top_members_reported": int(shown.size),
        "top_members_share_of_target_pct": round(
            float(np.sum(ranked_not[shown])) / target_notional * 100.0, 3),
        # A wallet above the band cannot be in any admissible set, so it is outside the
        # problem rather than an obstacle inside it. Recorded because the reading that
        # replaced it was wrong about this for six weeks.
        "pool_wallets_above_band": int(
            np.sum(ranked_not > target_notional + tol_abs)),
        "n_ranked_wallets": int(ranked_not.size),
        "note": ("one_for_one_swaps_in_band counts the wallets of the whole ranked pool "
                 "within the band of that member, itself included, so one means no other "
                 "wallet can replace it in a single swap. The paired move is wider and can "
                 "displace these members, rarely; this count bounds the single-swap move "
                 "set and not the walk. Read it beside chain_agreement, which is where the "
                 "consequence shows."),
    }


def _joint_region_reading(sel_idx, ranked_not, target_notional, n_required, tol_abs):
    """What the joint region says about ONE candidate wallet set, both axes read apart.

    The region is an INTERSECTION of two conditions and this reading keeps them separate,
    so a set that is refused says which axis refused it rather than only that it was
    refused. The count axis is exact: a set holds the same NUMBER of wallets as the
    observed toxic set or it is out. The notional axis is a band, for the reason
    JOINT_PLACEBO_TOL_PCT states -- a subset of a fixed size cannot be made to sum to an
    arbitrary target exactly -- and the band is that constant applied to the target.

    Returns a dict; in_region is the conjunction, and both single-axis verdicts stay
    beside it so a refusal can name the axis and both numbers."""
    idx = np.asarray(sel_idx, dtype=np.int64)
    n_w = int(idx.size)
    total = float(np.sum(ranked_not[idx])) if n_w else 0.0
    dev = total - float(target_notional)
    count_held = bool(n_w == int(n_required))
    volume_held = bool(abs(dev) <= float(tol_abs))
    dev_pct = (dev / target_notional * 100.0) if target_notional > 0 else None
    return {
        "n_wallets": n_w,
        "n_wallets_required": int(n_required),
        "count_held": count_held,
        "total_notional_usd": round(total, 2),
        "target_notional_usd": round(float(target_notional), 2),
        "notional_dev_usd": round(dev, 2),
        "notional_dev_pct": None if dev_pct is None else round(dev_pct, 6),
        "tolerance_pct": JOINT_PLACEBO_TOL_PCT,
        "volume_held": volume_held,
        "in_region": bool(count_held and volume_held),
    }


def _walk_joint_matched_sets(rng, ranked_not, target_notional, n_required, tol_abs,
                             n_draws, burn_attempts, step_attempts, pair_prob):
    """ONE chain of wallet sets from the region that holds BOTH axes at once.

    THE MOVE, AND WHY IT IS TWO MOVES RATHER THAN ONE. A step proposes either a SINGLE
    swap -- drop one uniformly chosen member, admit one uniformly chosen non-member -- or
    a PAIRED swap of two for two, with pair_prob deciding which. It is taken only if the
    resulting set is still in the region. Both proposals are SYMMETRIC: the chance of
    proposing S' from S equals the chance of proposing S from S', because members and
    non-members are drawn uniformly on both sides. A mixture of symmetric proposals is
    symmetric, so with an acceptance of one inside the region and zero outside the chain is
    reversible and its stationary distribution is UNIFORM over the region. The wallet count
    cannot move at all, because every move removes as many wallets as it admits.

    THE PAIRED MOVE IS NOT AN OPTIMISATION, IT IS THE ONLY THING THAT MOVES THE LARGE
    WALLETS, and this was measured on 2026-08-30 rather than reasoned about. Under single
    swaps alone the largest wallet in the set is FROZEN for the whole chain: on the BTC cell
    of the declared lens, all one thousand draws of a chain carried the same largest wallet,
    at 45.7 per cent of the target on one start and at 69.3 per cent on another. The reason
    is arithmetic. A wallet worth 45.7 per cent of the target cannot be taken out and
    replaced by any single other wallet without moving the total far outside a band of one
    per cent, so every such proposal is refused, every time. Removing two and admitting two
    gives the move a second degree of freedom to absorb the difference, and it unfreezes:
    on the same cell the largest wallet then ranged over 38.7 to 45.7 per cent within one
    chain.

    WHY THE STEP IS COUNTED IN ATTEMPTS. See JOINT_PLACEBO_STEP_ATTEMPTS. Snapshotting after
    a fixed number of ACCEPTED moves reads the chain at a stopping time, and the post-jump
    distribution is not the stationary one: it weights each set by that set's own acceptance
    probability. Measured on the pooled cell, that alone moved the null's mean reduction from
    37.5 to 33.5 per cent, in the direction that makes the null easier.

    WHAT THIS DOES NOT PROVE, AND ON THIS DATA DOES NOT HOLD. Uniformity is a limit property
    and it needs the region to be connected under the moves in use. On this data it is NOT
    established, and the measurement says so: even with the paired move, eight chains started
    at eight independent random sets disagree about where the null sits. So a single chain's
    draws are a property of where that chain started, and no amount of running one chain
    longer repairs it -- lengthening the step forty-fold left the chains in the same
    disagreement. That is why this null is drawn from JOINT_PLACEBO_CHAINS independent starts
    and why the block refuses to publish any number on a cell where those starts do not agree
    about the tail. What the surviving cells assert is therefore narrower than uniformity and
    is stated in those words in the artifact: over that many independent starts, no draw
    reached the observed reduction.

    THE CHAIN DOES NOT START AT THE OBSERVED SET, deliberately. Starting at the very
    labelling the null is compared against would make the first draws a neighbourhood of it.
    Each chain starts at a uniformly random set of the right size and walks into the region
    by greedy single swaps that strictly reduce the notional miss, then burns in.

    Returns (snapshots, diagnostics); snapshots is a list of index arrays into ranked_not
    and is empty when the chain never entered the region."""
    n = int(ranked_not.size)
    k = int(n_required)
    diag = {
        "n_ranked_wallets": n,
        "n_wallets_required": k,
        "burn_attempts": int(burn_attempts),
        "step_attempts_between_draws": int(step_attempts),
        "pair_probability": float(pair_prob),
        "entered_feasible_region": False,
        "entry_attempts": 0,
        "entry_dev_pct": None,
        "attempted_single_swaps": 0,
        "accepted_single_swaps": 0,
        "attempted_paired_swaps": 0,
        "accepted_paired_swaps": 0,
        "single_swap_acceptance_rate": None,
        "paired_swap_acceptance_rate": None,
        "max_running_total_drift_usd": 0.0,
    }
    if (n == 0 or k <= 1 or k >= n - 1 or not np.isfinite(target_notional)
            or target_notional <= 0.0):
        diag["note"] = ("no paired move is possible on this cell: the chain needs at least "
                        "two members and two non-members and a positive target notional")
        return [], diag

    nl = ranked_not.tolist()          # plain floats: the inner loop is scalar arithmetic
    target = float(target_notional)
    tol = float(tol_abs)

    # ---- entry: a uniformly random set of the right size, walked in greedily ----
    start = rng.permutation(n)
    sel = start[:k].tolist()
    out = start[k:].tolist()
    cur = float(np.sum(ranked_not[np.asarray(sel, dtype=np.int64)]))
    entry_attempts = 0
    while abs(cur - target) > tol and entry_attempts < JOINT_PLACEBO_ENTRY_ATTEMPT_CAP:
        block = min(JOINT_PLACEBO_ENTRY_BLOCK,
                    JOINT_PLACEBO_ENTRY_ATTEMPT_CAP - entry_attempts)
        ia = rng.integers(0, k, size=block).tolist()
        jb = rng.integers(0, n - k, size=block).tolist()
        for t in range(block):
            entry_attempts += 1
            a = ia[t]; b = jb[t]
            i = sel[a]; j = out[b]
            new = cur - nl[i] + nl[j]
            if abs(new - target) < abs(cur - target):
                sel[a] = j; out[b] = i; cur = new
                if abs(cur - target) <= tol:
                    break
    diag["entry_attempts"] = int(entry_attempts)
    diag["entered_feasible_region"] = bool(abs(cur - target) <= tol)
    diag["entry_dev_pct"] = round((cur - target) / target * 100.0, 6)
    if not diag["entered_feasible_region"]:
        diag["note"] = (f"the greedy entry did not reach the region in {entry_attempts} "
                        f"attempts; the closest set missed the target notional by "
                        f"{diag['entry_dev_pct']} per cent against a tolerance of "
                        f"{JOINT_PLACEBO_TOL_PCT} per cent")
        return [], diag

    # ---- the walk itself ----
    att1 = acc1 = att2 = acc2 = 0
    max_drift = 0.0
    snapshots = []
    for leg, n_att in enumerate([int(burn_attempts)] + [int(step_attempts)] * int(n_draws)):
        a1 = rng.integers(0, k, size=n_att).tolist()
        b1 = rng.integers(0, n - k, size=n_att).tolist()
        a2 = rng.integers(0, k, size=n_att).tolist()
        b2 = rng.integers(0, n - k, size=n_att).tolist()
        u = rng.random(n_att).tolist()
        for t in range(n_att):
            if u[t] < pair_prob:
                p = a1[t]; q = a2[t]; r = b1[t]; s = b2[t]
                if p == q or r == s:
                    continue      # the proposal collapses to a single swap or to nothing;
                                  # spending it as a self-loop keeps the kernel symmetric
                att2 += 1
                ip = sel[p]; iq = sel[q]; jr = out[r]; js = out[s]
                new = cur - nl[ip] - nl[iq] + nl[jr] + nl[js]
                if -tol <= new - target <= tol:
                    sel[p] = jr; sel[q] = js; out[r] = ip; out[s] = iq
                    cur = new; acc2 += 1
            else:
                att1 += 1
                p = a1[t]; r = b1[t]
                i = sel[p]; j = out[r]
                new = cur - nl[i] + nl[j]
                if -tol <= new - target <= tol:
                    sel[p] = j; out[r] = i; cur = new; acc1 += 1
        # Re-anchor the running total on an exact recomputation, and record how far the
        # incremental one had drifted. A running sum updated a few million times is the
        # obvious place for float error to accumulate into the acceptance test itself.
        idx = np.asarray(sel, dtype=np.int64)
        exact = float(np.sum(ranked_not[idx]))
        max_drift = max(max_drift, abs(exact - cur))
        cur = exact
        if leg > 0:
            snapshots.append(idx)

    diag.update({
        "attempted_single_swaps": int(att1),
        "accepted_single_swaps": int(acc1),
        "attempted_paired_swaps": int(att2),
        "accepted_paired_swaps": int(acc2),
        "single_swap_acceptance_rate": round(acc1 / att1, 6) if att1 else None,
        "paired_swap_acceptance_rate": round(acc2 / att2, 6) if att2 else None,
        "max_running_total_drift_usd": round(max_drift, 6),
    })
    return snapshots, diag


def _joint_chain_agreement(tail_counts, n_per_chain, level_sigma):
    """Do the independent chains agree about the TAIL, which is the only thing the
    published fraction reads?

    WHY THE TEST IS ON THE TAIL AND NOT ON THE MEAN. The published statistic counts how many
    draws reached the observed value -- it is floored the way a permutation p is floored,
    and it is deliberately NOT called one, because the distribution these draws come from
    is not established. The
    null's LOCATION -- its mean, its 95th percentile -- is descriptive, and on this data it
    is measurably start-dependent on every cell, by a few percentage points. Requiring the
    chains to agree about the location would refuse every cell for a disagreement the
    published number does not depend on. Requiring them to agree about the TAIL refuses
    exactly the cells whose published number would be an accident of where one chain started.

    THE BAR. Each chain's tail fraction has to sit within level_sigma binomial standard
    deviations of the fraction pooled over all chains. Where the pooled fraction is zero the
    rule degenerates to the only sensible reading: every chain must be zero, because one
    chain finding draws above the observed value while another finds none is precisely the
    disagreement this test exists to catch.

    WHAT IT CANNOT SEE, said plainly. It compares chains against each other. If every chain
    is trapped in the same part of the region it will agree with itself and pass, and this
    reading will not know. It is evidence and not a proof of uniformity, and the artifact
    says so where it reports the fraction."""
    counts = [int(c) for c in tail_counts]
    m = len(counts)
    n_c = int(n_per_chain)
    if m == 0 or n_c == 0:
        return {"chains": m, "draws_per_chain": n_c, "agree": False,
                "note": "no chain produced draws"}
    fracs = [c / n_c for c in counts]
    pooled = float(sum(counts)) / (m * n_c)
    if pooled <= 0.0:
        agree = all(c == 0 for c in counts)
        allowed = 0.0
    else:
        allowed = level_sigma * (pooled * (1.0 - pooled) / n_c) ** 0.5
        agree = all(abs(f - pooled) <= allowed + 1e-12 for f in fracs)
    worst = max(abs(f - pooled) for f in fracs)
    return {
        "chains": m,
        "draws_per_chain": n_c,
        "per_chain_tail_counts": counts,
        "per_chain_tail_fractions": [round(f, 6) for f in fracs],
        "pooled_tail_fraction": round(pooled, 6),
        "allowed_departure": round(allowed, 6),
        "largest_departure": round(worst, 6),
        "sigma_bar": float(level_sigma),
        "agree": bool(agree),
        "note": ("every chain's share of draws reaching the observed reduction has to sit "
                 "within the stated number of binomial standard deviations of the share "
                 "pooled over the chains; where the pooled share is zero every chain has "
                 "to be zero. This compares the chains against each other and cannot see a "
                 "region every chain is equally trapped in."),
    }


def _joint_placebo_calibration(ranked_ids, ranked_not, screened_mask, target_notional,
                               n_required, tol_abs):
    """Three cases from the LIVE data of this very cell, run every time the null is built.

    A null that reports "no draw reached the observed reduction" says nothing until the
    predicate deciding what a draw IS has been shown able to refuse. So the region test is
    handed one set it must accept and two it must refuse, one per axis, and the outcome is
    written beside the null rather than checked once when the code was written.

    THE SILENT CASE IS A TAUTOLOGY TODAY AND IS KEPT ANYWAY. The target notional is DEFINED
    as the observed toxic set's own total, so that set misses it by exactly zero and the
    case cannot fail on this tree. It is not there to fail today: it is there to fail on the
    day the target stops being that total -- if it were ever rounded, or read from a
    neighbouring artifact, or taken at a different horizon -- which is the edit that would
    otherwise move every draw of this null without moving anything a reader can see.

    The two firing cases are not tautologies. The volume case holds the count exactly and
    breaks the notional; the count case holds the notional to well inside the band and
    breaks the count. Both sets are built out of this cell's own ranked wallets."""
    n = int(ranked_ids.size)
    obs_idx = np.where(screened_mask)[0]

    # must stay silent: the observed toxic set itself
    silent = _joint_region_reading(obs_idx, ranked_not, target_notional, n_required, tol_abs)
    silent["case"] = "the observed toxic set itself"
    silent["expected"] = "accepted"
    silent["as_expected"] = bool(silent["in_region"])

    # must fire on the VOLUME axis: the same NUMBER of wallets, taken as the smallest by
    # late notional. The count is exact by construction, so only the notional can refuse.
    small_idx = np.argsort(ranked_not, kind="stable")[:n_required]
    vol = _joint_region_reading(small_idx, ranked_not, target_notional, n_required, tol_abs)
    vol["case"] = ("the same NUMBER of wallets, taken as the smallest by late notional")
    vol["expected"] = "refused on the notional axis"
    vol["as_expected"] = bool(vol["count_held"] and not vol["volume_held"]
                              and not vol["in_region"])

    # must fire on the COUNT axis: the observed set less its smallest-notional member. The
    # notional it drops is a rounding of the target, so the notional axis stays held and
    # the count axis is the only one left to refuse.
    if obs_idx.size > 1:
        drop_at = int(np.argmin(ranked_not[obs_idx]))
        kept = np.delete(obs_idx, drop_at)
        cnt = _joint_region_reading(kept, ranked_not, target_notional, n_required, tol_abs)
        cnt["dropped_wallet_notional_usd"] = round(float(ranked_not[obs_idx][drop_at]), 2)
    else:
        cnt = {"case": None, "in_region": None}
    cnt["case"] = "the observed toxic set less its smallest-notional member"
    cnt["expected"] = "refused on the count axis"
    cnt["as_expected"] = bool(cnt.get("volume_held") and not cnt.get("count_held", True)
                              and not cnt.get("in_region", True))

    return {
        "must_stay_silent": silent,
        "must_fire_on_notional": vol,
        "must_fire_on_count": cnt,
        "calibrated": bool(silent["as_expected"] and vol["as_expected"]
                           and cnt["as_expected"]),
        "note": ("the region test is exercised on three sets built from this cell's own "
                 "ranked wallets every run: one it must accept and one per axis it must "
                 "refuse. calibrated false is a refusal, not a warning."),
    }


def _t1_joint_matched_placebo(ranked_ids, ranked_score, late_tid, late_cost,
                              late_not, sym_cost, cell=None):
    """JOINT-matched null: the same NUMBER of wallets AND the same late NOTIONAL at once.

    WHY A THIRD NULL. The two above each hold one axis and let the other run. The
    count-matched placebo fixes how MANY wallets are declined and lets the notional go
    where it will, so its draws turn away far less volume than the toxic set. The
    size-matched placebo fixes how MUCH notional, to within its own stratified-draw miss,
    and lets the count run -- measured on this tree it draws between 66 and 2004 wallets
    where the observed set holds 206. Clearing both of those separately is not clearing one
    null that holds both AT ONCE, because a set is free to satisfy either constraint by
    breaking the other, and it is the joint constraint that the objection actually names.

    WHAT IS HELD AND HOW EXACTLY. The wallet count is held EXACTLY -- every move of the
    sampler removes as many wallets as it admits. The total late notional is held to within
    JOINT_PLACEBO_TOL_PCT of the observed toxic set's, which is six times tighter than the
    size-matched null's own p95 miss at its best cell and fifty-eight times tighter at its
    worst. Both are measured on every draw and the spread is written into the artifact, so
    the claim that the axes were held is a reading and not an assertion.

    WHERE THIS NULL SITS RELATIVE TO ITS NEIGHBOUR, measured on this run rather than
    reasoned about, because reasoning got it backwards. The expectation written into the
    first version of this file was that constraining both axes would NARROW the null and
    LOWER its upper tail, since the size-matched null reaches its target notional however it
    likes -- with a handful of giants, or with a thousand small wallets -- and that spread
    was supposed to be what lifts its p95. The run says the opposite. The joint null's mean
    reduction sits ABOVE the size-matched null's on four of the five cells that produce
    both: 34.64 against 28.55 pooled on the declared lens, 53.48 against 41.76 pooled on the
    print, 10.78 against 10.12 and 51.66 against 41.18 on ETH; on the fifth, BTC on the
    print, the two are level at 39.24 against 39.87.

    The mechanism is the constraint read the right way round. Holding the wallet COUNT as
    well as the volume forces every draw to RESEMBLE the observed toxic set -- the same
    number of wallets carrying the same dollars, so wallets of the same typical size -- and
    a set that resembles it recovers more of its cost reduction. The neighbour's freedom to
    take five giants or a thousand minnows is freedom to be UNLIKE the toxic set, and being
    unlike it is what puts a draw low. So this null stands NEARER the observed value than
    either single-axis null, and a reduction that clears it has cleared a harder bar. The
    count-matched null sits lowest of the three, at 5.1 to 8.3 per cent, because it holds
    neither the volume nor the resemblance.

    THE HARD PART IS DRAWING FROM THAT REGION AT ALL, and this is the part that decides
    whether a cell gets a number. There is no closed form for a uniform draw from "subsets
    of exactly this many wallets whose notional sums into a band", so the sets come from a
    Markov chain over swaps. On this data that chain does NOT reach a distribution
    independent of where it started, and the reason was WRITTEN WRONG HERE UNTIL 2026-08-30.
    This paragraph used to blame an outside giant: one pool wallet is worth 142.6 per cent of
    the target on the BTC cell of the declared lens, and the text said a set built around one
    large wallet cannot be walked into a set built around a different one. Measured, that
    wallet is not in the problem at all. It is larger than the target plus the band, so it
    cannot sit in ANY admissible set, and it is not a member of the observed toxic set either
    -- there is exactly one such wallet on that cell and zero on every other. It blocks
    nothing, because it never appears.

    THE MEASURED REASON IS THE SET'S OWN LARGEST MEMBERS AND THE ABSENCE OF REPLACEMENTS FOR
    THEM. The reading is published per cell at region_freedom in this block, and on the BTC
    cell of the declared lens it says: the biggest member carries 69.3 per cent of the target,
    the three biggest carry 92.7, and the number of wallets in the whole pool of 1234 lying
    within the band of the biggest is ONE -- itself. The same count for the second biggest is
    also one. So a single swap cannot exchange either of them for anything, and a draw's
    identity is settled by which large wallets its chain entered with.

    THAT IS A RARITY AND NOT AN IMPOSSIBILITY, which is the second thing the old text got
    wrong by overstating. The paired move has a second degree of freedom, and a paired swap
    that drops the largest member exists for every one of the 122 partner choices on that
    cell; there are only about two ordered pairs in the band for the first of them, against
    about 130 on the ETH cell, so the move is proposed and refused almost always rather than
    being unavailable. The chains show exactly that: measured on 2026-08-30, the largest
    wallet of a chain's first and last draw is the same number in several of the eight, and
    the eight sit at different values -- 69.3 in one, 40.4 in three, 43.8 in two, about 20 in
    two -- with tails of 0, 0.912, 0.02, 0.044 and four zeros. Lengthening one chain
    forty-fold did not close the disagreement.

    AND THE STRICTNESS OF THIS NULL AND ITS DEGENERACY GROW TOGETHER, which is the caveat a
    reader is owed rather than a footnote. What makes the joint null stand nearer the observed
    value is that a draw must resemble the observed set; where the largest members carry most
    of the target, "resemble" collapses towards "be a near-copy of", and the null compares the
    observed set with slightly rearranged versions of itself. The measure of that is in the
    same region_freedom block: the largest member holds 19.3 per cent of the target on the
    pooled cell, where the null is meaningful, 35.7 on ETH, and 69.3 on the BTC cell of the
    declared lens, where it does not survive its own agreement test at all.

    SO THE NULL IS DRAWN FROM JOINT_PLACEBO_CHAINS INDEPENDENT STARTS AND THE BLOCK REFUSES
    WHERE THEY DISAGREE. What the chains are required to agree about is the TAIL -- how many
    draws reach the observed reduction -- because that is the only thing the published
    fraction reads. They are NOT required to agree about where the null sits, because on this
    data they do not, and the between-chain spread of the mean is published beside the
    fraction rather than smoothed away. A cell whose starts disagree about the tail gets no
    number at all: on the run of 2026-08-30 that is one cell of the six, BTC on the declared
    book-mid lens, where the share of draws reaching the observed reduction runs from nought
    to ninety-one per cent depending on the start. BTC on the print lens is not that cell and
    passes with every start at zero, as do the four others; which cells refuse on any given
    run is read from their own refused flag, not from this sentence.

    AND THE PUBLISHED FRACTION IS NOT CALLED A P-VALUE, since 2026-08-30. It was, under the
    key toxicity_vs_joint_matched_p, while this same docstring and the block's own claim key
    said uniformity over the region is not established -- so the file asserted a probability
    under a distribution it declared unknown in the neighbouring key. The arithmetic was never the
    problem and has not changed: it counts the draws that reached the observed value and
    floors the ratio. What changed is that the number now says what it is,
    joint_matched_tail_fraction_floored, a property of these draws.

    WHAT A SURVIVING CELL ASSERTS, in the words that are true of it. Not "the observed
    reduction is above the uniform null over the region" -- uniformity is not established
    here. It asserts that over JOINT_PLACEBO_CHAINS independent starts, holding both axes,
    no draw reached the observed reduction. That is weaker than uniformity and stronger than
    either single-axis null.

    REFUSAL. This block does not print a difference it cannot stand behind. If the observed
    toxic set does not itself lie in the region, if the region test fails its own
    calibration, if a chain never entered the region, if any draw left either axis, or if
    the chains disagree about the tail, the block reports the refusal with the cell named and
    both numbers, and no reduction and no tail fraction are written. The pattern is the one
    probes/flat_surcharge_control.py uses: a control that has not established its own
    baseline has no baseline."""
    quant = dict((lab, q) for lab, q, _ in SKEW_POLICIES)[PLACEBO_POLICY]
    avoid_frac = dict((lab, a) for lab, _, a in SKEW_POLICIES)[PLACEBO_POLICY]
    n = ranked_ids.size
    cell_name = list(cell) if cell is not None else None
    per_chain = N_JOINT_PLACEBO // JOINT_PLACEBO_CHAINS
    n_used = per_chain * JOINT_PLACEBO_CHAINS
    out = {
        "policy": PLACEBO_POLICY,
        "cell": cell_name,
        "n_draws": n_used,
        "n_chains": JOINT_PLACEBO_CHAINS,
        "n_draws_per_chain": per_chain,
        "seed": RNG_SEED + 2,
        # The third stream of this file, and derived rather than typed: RNG_SEED is the
        # count-matched null's, RNG_SEED + 1 the size-matched null's, so this is the next
        # free offset. A fresh literal here would be a seed with no home. The chain index
        # goes into the entropy beside it, so adding a chain cannot collide with either
        # neighbour's stream.
        #
        # THE NUMBER ABOVE IS NOT A WHOLE STREAM HERE, which is why the shape is stated
        # beside it. The two neighbouring blocks each record the scalar their one
        # generator was built from, and after the size-matched block's record was
        # repaired on 2026-08-30 a reader is entitled to expect the same of this one.
        # It is not the same: this null makes one generator PER CHAIN from a two-element
        # entropy, and the recorded scalar is only its first element.
        #
        # WHAT THE SCALAR ALONE REPRODUCES WAS MEASURED, not reasoned about, because
        # reasoning got it wrong first: numpy pads a SeedSequence's entropy with zeros,
        # so default_rng(seed) and default_rng([seed, 0]) are the SAME stream to the bit
        # -- their first four state words agree -- and the scalar therefore reproduces
        # chain 0 exactly. Every other chain needs the list. The first draft of this key
        # said the scalar draws something else, which was true of seven chains and false
        # of the one a reader would try first.
        "seed_entropy": ("numpy.random.default_rng([seed, chain]) -- one generator per "
                         "chain, the chain index 0..n_chains-1 as the second entropy "
                         "element. Passing the recorded scalar alone reproduces chain 0 "
                         "and only chain 0, because numpy pads the entropy with zeros; "
                         "chains 1 upward need the two-element list"),
        "tail_fraction_floor": stats.p_floor(n_used),
        "tolerance_pct": JOINT_PLACEBO_TOL_PCT,
        "matched_on": ("the NUMBER of wallets in the observed toxic set, held exactly, AND "
                       "the total late notional of that set, held to within "
                       f"{JOINT_PLACEBO_TOL_PCT} per cent -- both axes at once"),
        "stricter_than_size_matched_note": (
            "This null constrains MORE than size_matched_placebo beside it, holding both "
            "axes where that one holds the volume alone. It does NOT follow that its upper "
            "tail is lower, and measured on this run it is not: the joint null's mean "
            "reduction sits ABOVE the size-matched null's on four of the five cells that "
            "produce both, and level with it on the fifth. Holding the wallet COUNT as well "
            "as the volume forces every draw to RESEMBLE the observed toxic set -- the same "
            "number of wallets carrying the same dollars -- and a set that resembles it "
            "recovers more of its cost reduction, while the neighbour is free to reach the "
            "same notional through a handful of giants or a thousand minnows and be UNLIKE "
            "the toxic set. So this null stands NEARER the observed value, and clearing it "
            "is a stronger result rather than a weaker one. Read the two distributions side "
            "by side before reading either number, and note that the two numbers are not "
            "of one kind: the neighbour publishes a p-value, this block publishes the "
            "share of its own draws that reached the observed value."),
    }
    if n == 0 or not np.isfinite(sym_cost) or sym_cost <= 0.0:
        out.update({
            "target_toxic_notional_usd": None,
            "n_toxic_wallets": None,
            "joint_matched_mean_reduction_pct": None,
            "joint_matched_p95_reduction_pct": None,
            "joint_matched_max_reduction_pct": None,
            "observed_reduction_pct": None,
            "joint_matched_tail_fraction_floored": None,
            "no_draw_reached_observed": None,
            "reduction_undefined_nonpositive_base": (n != 0),
            "refused": False,
            "note": ("no ranked wallets" if n == 0 else
                     "undefined_nonpositive_base: symmetric cost <= 0, no reduction "
                     "percentage is defined"),
        })
        return out

    ranked_not = _wallet_notional(ranked_ids, late_tid, late_not)
    ranked_cost = _wallet_late_cost(ranked_ids, late_tid, late_cost)

    screened_mask = _top_quantile_mask(ranked_ids, ranked_score, quant)
    screened_ids = ranked_ids[screened_mask]
    n_required = int(screened_ids.size)
    target_notional = float(np.sum(ranked_not[screened_mask]))
    tol_abs = target_notional * JOINT_PLACEBO_TOL_PCT / 100.0

    # observed reduction by the ROW path the neighbouring blocks use
    in_screened_obs = np.isin(late_tid, screened_ids)
    obs_avoided = avoid_frac * _cost_of(late_cost, in_screened_obs)
    obs_frac, _ = _reduction_frac(obs_avoided, sym_cost)
    # the same quantity by the per-wallet path the draws are scored on, so the two are
    # known to agree before a single draw is compared against the observed value
    obs_avoided_wallet = avoid_frac * float(np.sum(ranked_cost[screened_mask]))
    scale = max(abs(obs_avoided), abs(obs_avoided_wallet), 1.0)
    path_gap = abs(obs_avoided - obs_avoided_wallet) / scale

    observed_reading = _joint_region_reading(np.where(screened_mask)[0], ranked_not,
                                             target_notional, n_required, tol_abs)
    calib = _joint_placebo_calibration(ranked_ids, ranked_not, screened_mask,
                                       target_notional, n_required, tol_abs)

    out.update({
        "target_toxic_notional_usd": round(target_notional, 2),
        "n_toxic_wallets": n_required,
        "n_ranked_wallets": int(n),
        # The largest wallet of the POOL, which is not the same quantity as the largest
        # MEMBER beside it in region_freedom and must not be read as one: on the BTC cell of
        # the declared lens this is 142.6 per cent of the target and belongs to a wallet
        # that is in no admissible set and in no draw.
        "largest_wallet_share_of_target_pct": round(
            float(ranked_not.max()) / target_notional * 100.0, 3),
        "observed_set_reading": observed_reading,
        "region_freedom": _joint_member_substitutability(
            ranked_not, screened_mask, target_notional, tol_abs),
        "predicate_calibration": calib,
        "wallet_path_vs_row_path_rel_gap": float(path_gap),
    })

    refusals = []
    if not observed_reading["in_region"]:
        refusals.append(
            f"the observed toxic set is not in the admissible region: it holds "
            f"{observed_reading['n_wallets']} wallets against the required "
            f"{observed_reading['n_wallets_required']}, and its total late notional is "
            f"{observed_reading['total_notional_usd']} against a target of "
            f"{observed_reading['target_notional_usd']} with a band of "
            f"{JOINT_PLACEBO_TOL_PCT} per cent")
    if not calib["calibrated"]:
        refusals.append(
            "the region test failed its own calibration on this cell: "
            + "; ".join(f"{k} read in_region={calib[k].get('in_region')} against the "
                        f"expectation {calib[k].get('expected')!r}"
                        for k in ("must_stay_silent", "must_fire_on_notional",
                                  "must_fire_on_count")
                        if not calib[k].get("as_expected")))
    if refusals:
        out.update(_joint_refusal(cell_name, refusals))
        return out

    # ---- the chains ----
    chain_blocks = []
    all_idx = []
    for c in range(JOINT_PLACEBO_CHAINS):
        rng = np.random.default_rng([RNG_SEED + 2, c])
        snaps, diag = _walk_joint_matched_sets(
            rng, ranked_not, target_notional, n_required, tol_abs, per_chain,
            JOINT_PLACEBO_BURN_ATTEMPTS, JOINT_PLACEBO_STEP_ATTEMPTS,
            JOINT_PLACEBO_PAIR_PROB)
        chain_blocks.append({"chain": c, "n_draws": len(snaps), "sampler": diag})
        all_idx.extend(snaps)
    out["chains"] = chain_blocks

    short = [b["chain"] for b in chain_blocks if b["n_draws"] != per_chain]
    if short:
        out.update(_joint_refusal(cell_name, [
            f"chains {short} did not deliver their {per_chain} draws: "
            + "; ".join(str(chain_blocks[c]["sampler"].get("note", "the chain did not "
                                                           "enter the region"))
                        for c in short)]))
        return out

    # ---- read both axes and the statistic off every draw ----
    draw_counts = np.array([int(s.size) for s in all_idx], dtype=np.int64)
    draw_notional = np.array([float(np.sum(ranked_not[s])) for s in all_idx])
    draw_dev_pct = (draw_notional - target_notional) / target_notional * 100.0
    reductions = np.empty(n_used, dtype=np.float64)
    for b, s in enumerate(all_idx):
        avoided = avoid_frac * float(np.sum(ranked_cost[s]))
        frac, _ = _reduction_frac(avoided, sym_cost)
        reductions[b] = frac

    # The count cannot move under a swap, so its min and max are a guard against a future
    # sampler that moves it, not a discovery about this one; the notional spread is a real
    # reading and is the evidence that the band held.
    axes = {
        "count_held_exactly": bool(int(draw_counts.min()) == n_required
                                   == int(draw_counts.max())),
        "draw_n_wallets_min": int(draw_counts.min()),
        "draw_n_wallets_max": int(draw_counts.max()),
        "draw_notional_dev_pct_min": round(float(draw_dev_pct.min()), 6),
        "draw_notional_dev_pct_max": round(float(draw_dev_pct.max()), 6),
        "draw_notional_dev_abs_p95_pct": round(
            float(np.percentile(np.abs(draw_dev_pct), 95)), 6),
        "all_draws_inside_tolerance": bool(
            np.all(np.abs(draw_dev_pct) <= JOINT_PLACEBO_TOL_PCT + 1e-9)),
        "mean_drawn_notional_usd": round(float(draw_notional.mean()), 2),
    }
    out["axes_held"] = axes

    # ---- do the independent starts agree about the tail ----
    tail_counts = []
    for c in range(JOINT_PLACEBO_CHAINS):
        r = reductions[c * per_chain:(c + 1) * per_chain]
        tail_counts.append(int(np.sum(r >= obs_frac - 1e-12)))
        chain_blocks[c].update({
            "mean_reduction_pct": round(float(r.mean()) * 100.0, 4),
            "p95_reduction_pct": round(float(np.percentile(r, 95)) * 100.0, 4),
            "max_reduction_pct": round(float(r.max()) * 100.0, 4),
            "draws_at_or_above_observed": tail_counts[-1],
            "largest_wallet_in_draws_share_of_target_pct": [
                round(float(ranked_not[s].max()) / target_notional * 100.0, 3)
                for s in (all_idx[c * per_chain], all_idx[(c + 1) * per_chain - 1])
            ],
        })
    agreement = _joint_chain_agreement(tail_counts, per_chain,
                                       JOINT_PLACEBO_CHAIN_AGREEMENT_SIGMA)
    chain_means = np.array([b["mean_reduction_pct"] for b in chain_blocks])
    agreement["chain_mean_reduction_min_pct"] = round(float(chain_means.min()), 4)
    agreement["chain_mean_reduction_max_pct"] = round(float(chain_means.max()), 4)
    agreement["chain_mean_reduction_spread_pct"] = round(
        float(chain_means.max() - chain_means.min()), 4)
    agreement["location_note"] = (
        "The chains are NOT required to agree about where the null sits, and on this data "
        "they do not: the spread above is real and is a property of the region rather than "
        "of the budget. Only the tail is tested, because only the tail is what the "
        "published tail fraction counts.")
    out["chain_agreement"] = agreement

    if not (axes["count_held_exactly"] and axes["all_draws_inside_tolerance"]):
        out.update(_joint_refusal(cell_name, [
            f"a draw left the admissible region: the wallet count ran from "
            f"{axes['draw_n_wallets_min']} to {axes['draw_n_wallets_max']} against a "
            f"required {n_required}, and the notional miss ran from "
            f"{axes['draw_notional_dev_pct_min']} to "
            f"{axes['draw_notional_dev_pct_max']} per cent against a band of "
            f"{JOINT_PLACEBO_TOL_PCT} per cent"]))
        return out

    if not agreement["agree"]:
        out.update(_joint_refusal(cell_name, [
            f"the {JOINT_PLACEBO_CHAINS} independent starts do not agree about the tail: "
            f"the share of draws reaching the observed reduction of "
            f"{round(obs_frac * 100.0, 4)} per cent runs "
            f"{agreement['per_chain_tail_fractions']} across the chains against a pooled "
            f"{agreement['pooled_tail_fraction']}, and the largest departure "
            f"{agreement['largest_departure']} exceeds the allowed "
            f"{agreement['allowed_departure']}. The region is not connected under the "
            f"moves in use on this cell, so a number here would be a property of where "
            f"one chain happened to start"]))
        return out

    # Same counting as both neighbours: one-sided, the +1 floor, the denominator the count
    # of usable draws. The absolute 1e-12 is passed rather than the module's scale-relative
    # default, for the same reason and with the same record of whose choice it was.
    perm = stats.permutation_p(obs_frac, reductions, side="greater",
                               abs_tol=1e-12, n_requested=n_used,
                               cell=tuple(["t1_joint_matched_placebo", PLACEBO_POLICY]
                                          + (cell_name or [])))
    tail_frac = perm["p"]

    # THE COUNTING IS THE SAME COUNTING AND ONLY ITS NAME CHANGES HERE. stats.permutation_p
    # counts the draws that reached the observed value and floors the ratio, which is
    # exactly the arithmetic wanted, so the call stands and not one number moves. What
    # cannot stand is the NAME. A p-value is a probability under a known null distribution,
    # and this very block states in its own claim key below that uniformity over the region
    # is not established on this data -- so the file was contradicting itself, publishing a
    # probability whose distribution it declared unknown in the neighbouring key. The
    # returned block is therefore re-keyed for THIS null alone. The two single-axis nulls
    # keep their p untouched: their draws are independent and the distribution of their
    # procedure under the null is defined, so their p is a p.
    #
    # Two of the block's self-descriptions are rewritten with it, because both were also
    # about a procedure this is not: these draws are not a label permutation, they are a
    # swap walk over the admissible region.
    procedure = dict(perm)
    procedure["procedure"] = ("swap walk over the joint region, counted -- NOT a label "
                              "permutation and NOT a draw from an established null")
    procedure["method"] = (
        "tail fraction = (draws reaching the observed value + 1) / (usable draws + 1); "
        "the observed set counts as one draw of its own null, so the fraction is floored "
        "at 1/(usable + 1) and is never zero. It is NOT a p-value and must not be read as "
        "one: the draws come from a chain whose distribution over the region is not "
        "established on this data, so this fraction is a property of THESE draws and no "
        "probability is claimed for it")
    procedure["tail_fraction_floored"] = procedure.pop("p")
    procedure["tail_fraction_floor"] = procedure.pop("p_floor")
    procedure["tail_fraction_at_floor"] = procedure.pop("p_is_floored")

    out.update({
        "joint_matched_procedure": procedure,
        "joint_matched_mean_reduction_pct": round(float(reductions.mean()) * 100.0, 4),
        "joint_matched_p95_reduction_pct": round(
            float(np.percentile(reductions, 95)) * 100.0, 4),
        "joint_matched_max_reduction_pct": round(float(reductions.max()) * 100.0, 4),
        "observed_reduction_pct": round(obs_frac * 100.0, 4) if obs_frac is not None else None,
        "n_draws_at_or_above_observed": int(perm["n_at_least_as_extreme"]),
        # NAME REPAIR, 2026-08-30. These two keys were "toxicity_vs_joint_matched_p" and
        # "toxicity_beats_joint_matched", and both said something this null cannot say. A
        # p-value is a probability under a known distribution; the claim key below states
        # that uniformity over the region is NOT established here, so what the arithmetic
        # yields is the share of THESE draws that reached the observed value, floored by
        # the +1 that counts the observed set as a draw of its own null. The first key is
        # therefore renamed and its number is untouched.
        #
        # THE SECOND KEY IS REPLACED AND NOT RENAMED, and the difference is the point. Its
        # first repair read "tail fraction at or below five per cent", which puts the
        # significance threshold back in through the door this repair closed: a reader
        # cannot tell that from p <= 0.05, and the whole claim here is that the two are not
        # the same thing. What stands instead carries no threshold at all -- whether ANY
        # draw reached the observed value, which is a fact about the sample. On the two
        # branches where the null was never built it is null rather than false, because
        # false would assert that some draw did reach it and nothing measured that.
        "joint_matched_tail_fraction_floored": round(tail_frac, 6),
        "no_draw_reached_observed": bool(int(perm["n_at_least_as_extreme"]) == 0),
        "reduction_undefined_nonpositive_base": False,
        "refused": False,
        "claim": (f"over {JOINT_PLACEBO_CHAINS} independent starts holding both axes, "
                  f"{int(perm['n_at_least_as_extreme'])} of {n_used} draws reached the "
                  f"observed reduction of {round(obs_frac * 100.0, 4)} per cent, and the "
                  f"largest reduction any draw reached was "
                  f"{round(float(reductions.max()) * 100.0, 4)} per cent. That count and "
                  f"that maximum are the whole of what this block asserts. This is NOT a "
                  f"statement that the draws are uniform over the region -- uniformity is "
                  f"not established on this data -- and so the fraction beside it is NOT a "
                  f"p-value: it is the share of these draws, with the observed set counted "
                  f"as one of them. What was tested instead is in chain_agreement, and a "
                  f"cell whose independent starts disagree about the tail is refused "
                  f"outright and carries no reduction and no fraction at all -- which "
                  f"cells those are on this run is read from their own refused flag, not "
                  f"asserted here."),
        "note": ("the observed toxicity-ranked reduction is compared against sets that "
                 "decline the SAME NUMBER of wallets and the SAME dollar volume at once, "
                 "so neither how-many nor how-much is free to explain it. What is left is "
                 "WHO. Read this tail fraction beside the two single-axis p-values rather "
                 "than instead of them, and read it as the different kind of number it "
                 "is: those two are p-values under nulls whose draws are independent and "
                 "whose distribution is defined, this one is a count of draws from a walk "
                 "over a region. Each of the three holds a different thing constant, and "
                 "the three answer three different objections."),
    })
    return out


def _joint_refusal(cell_name, reasons):
    """The closed refusal of the joint null: no reduction, no tail fraction, and the reason
    stated.

    Modelled on probes/flat_surcharge_control.py, which does not print its residual until
    it has reproduced the published baseline. The principle is the same one: a null whose
    admissible region has not been established has no region, and a difference reported
    against it would be a difference against something unnamed. So the numbers are withheld
    rather than hedged, and what is written instead is the cell and both sides of whatever
    did not hold."""
    return {
        "refused": True,
        "refusal_reasons": list(reasons),
        "joint_matched_mean_reduction_pct": None,
        "joint_matched_p95_reduction_pct": None,
        "joint_matched_max_reduction_pct": None,
        "observed_reduction_pct": None,
        "joint_matched_tail_fraction_floored": None,
        "no_draw_reached_observed": None,
        "note": (f"REFUSED on cell {cell_name}: no reduction and no tail fraction are "
                 f"reported for this null on this cell. " + " | ".join(reasons)),
    }

def _t1_whale_robust(taker_id, day, mo_score, notional, late_cost_rows,
                     late_mask, early_mask):
    """Drop the WHALE_DROP_K single largest-notional wallets (over ALL rows) and
    re-run the headline policy, to confirm the reduction is not just declining one
    or two giant wallets. Re-ranks toxicity AFTER excluding the whales so the
    screen does not depend on them either."""
    quant = dict((lab, q) for lab, q, _ in SKEW_POLICIES)[HEADLINE_POLICY]
    avoid_frac = dict((lab, a) for lab, _, a in SKEW_POLICIES)[HEADLINE_POLICY]

    tid = np.asarray(taker_id, dtype=np.int64)
    nt = np.asarray(notional, dtype=np.float64)

    # rank wallets by total notional over all rows; the top-K are the whales
    uniq, inv = np.unique(tid, return_inverse=True)
    wallet_notional = np.bincount(inv, weights=nt, minlength=uniq.size)
    k = min(WHALE_DROP_K, uniq.size)
    whale_ids = uniq[np.argsort(-wallet_notional, kind="stable")[:k]]
    not_whale = ~np.isin(tid, whale_ids)

    # re-rank on early rows excluding whales
    e_mask = early_mask & not_whale
    ranked_ids, ranked_score = _rank_by_markout(taker_id, mo_score, e_mask)
    screened_mask = _top_quantile_mask(ranked_ids, ranked_score, quant)
    screened_ids = ranked_ids[screened_mask]

    # evaluate on late rows excluding whales
    l_mask = late_mask & not_whale
    late_tid = tid[l_mask]
    late_cost = late_cost_rows[l_mask]
    late_not = nt[l_mask]
    res = _late_skew_cost(late_tid, late_cost, late_not, screened_ids, avoid_frac)

    return {
        "policy": HEADLINE_POLICY,
        "whale_criterion": WHALE_DROP_CRITERION,
        "n_whales_dropped": int(k),
        "whale_wallet_ids": [int(x) for x in whale_ids.tolist()],
        "n_ranked_wallets_no_whales": int(ranked_ids.size),
        "symmetric_cost_no_whales_usd": round(res["symmetric_cost_usd"], 2),
        "skew_cost_no_whales_usd": round(res["skew_cost_usd"], 2),
        "cost_reduction_no_whales_pct": _pct_or_none(res["cost_reduction_frac"]),
        "reduction_undefined_nonpositive_base": res["reduction_undefined_nonpositive_base"],
        "notional_given_up_no_whales_pct": round(res["notional_given_up_frac"] * 100.0, 3),
    }


# -------------------- T2: walk-forward --------------------
def _t2_walk_forward(taker_id, day, mo_score, notional, late_cost_rows):
    """Walk-forward over days: rank toxicity on all days <= t, evaluate the
    headline policy on day t+1, for every t from the first ranking day to the
    penultimate present day. Reports the per-fold reduction series so OOS
    deterioration is visible, plus the average reduction.

    The first fold needs at least one EARLY-style ranking day before it; we start
    ranking once at least the first two present days exist (rank on day[0..t],
    test day[t+1]). Each fold's ranking is strictly in-sample-up-to-t; the test day
    never informs its own ranking."""
    quant = dict((lab, q) for lab, q, _ in SKEW_POLICIES)[HEADLINE_POLICY]
    avoid_frac = dict((lab, a) for lab, _, a in SKEW_POLICIES)[HEADLINE_POLICY]

    present = sorted(int(d) for d in np.unique(day))
    folds = []
    reductions = []
    given_up = []

    for i in range(len(present) - 1):
        train_days = present[: i + 1]
        test_day = present[i + 1]

        train_mask = np.isin(day, np.asarray(train_days, dtype=np.int64))
        ranked_ids, ranked_score = _rank_by_markout(taker_id, mo_score, train_mask)
        screened_mask = _top_quantile_mask(ranked_ids, ranked_score, quant)
        screened_ids = ranked_ids[screened_mask]

        test_mask = day == test_day
        late_tid = taker_id[test_mask]
        late_cost = late_cost_rows[test_mask]
        late_not = notional[test_mask]
        res = _late_skew_cost(late_tid, late_cost, late_not, screened_ids, avoid_frac)

        fold = {
            "train_days": train_days,
            "test_day": test_day,
            "n_ranked_wallets": int(ranked_ids.size),
            "n_toxic_wallets": int(screened_ids.size),
            "symmetric_cost_usd": round(res["symmetric_cost_usd"], 2),
            "skew_cost_usd": round(res["skew_cost_usd"], 2),
            "cost_reduction_pct": _pct_or_none(res["cost_reduction_frac"]),
            "reduction_undefined_nonpositive_base": res["reduction_undefined_nonpositive_base"],
            "notional_given_up_pct": round(res["notional_given_up_frac"] * 100.0, 3),
        }
        folds.append(fold)
        # only folds with a DEFINED reduction (positive symmetric base, ranked
        # wallets present) enter the summary statistics; an undefined fold cannot
        # be averaged into a reduction without smuggling a non-positive-base artefact.
        if (ranked_ids.size > 0 and not res["reduction_undefined_nonpositive_base"]
                and res["cost_reduction_frac"] is not None):
            reductions.append(res["cost_reduction_frac"])
            given_up.append(res["notional_given_up_frac"])

    red = np.asarray(reductions, dtype=np.float64)
    gup = np.asarray(given_up, dtype=np.float64)

    # deterioration verdict: split the fold series in half and compare the MEDIAN
    # reduction of the earlier vs later folds. A reduction that PERSISTS keeps a
    # similar level late; one that DECAYS falls toward zero (or flips negative).
    persistence = _persistence_verdict(red)

    # LEAD on the MEDIAN fold reduction. The per-fold series is heavy-tailed (a few
    # folds with a tiny symmetric base blow up the mean and its std), so the median
    # is the robust headline; the mean and the full series are reported alongside
    # it, never in front of it.
    fold_series_pct = [
        round(x * 100.0, 3) for x in reductions
    ]
    return {
        "policy": HEADLINE_POLICY,
        "n_folds": len(folds),
        "n_evaluable_folds": int(red.size),
        "headline_statistic": "median_cost_reduction_pct",
        "median_cost_reduction_pct": round(float(np.median(red)) * 100.0, 3) if red.size else None,
        "mean_cost_reduction_pct": round(float(red.mean()) * 100.0, 3) if red.size else None,
        "std_cost_reduction_pct": round(float(red.std()) * 100.0, 3) if red.size else None,
        "fold_reduction_series_pct": fold_series_pct,
        "mean_notional_given_up_pct": round(float(gup.mean()) * 100.0, 3) if gup.size else None,
        "persistence": persistence,
        "folds": folds,
    }


def _persistence_verdict(reductions):
    """Earlier-vs-later split of the walk-forward reduction series.

    Compares the MEDIAN reduction over the first vs the second half of evaluable
    folds (the series is heavy-tailed, so the median is the robust statistic; the
    half means are reported alongside but the verdict keys on the median). The
    verdict is a description of the observed series only - never a forward-looking
    promise."""
    n = reductions.size
    if n < 2:
        return {
            "early_half_median_pct": None, "late_half_median_pct": None,
            "early_half_mean_pct": None, "late_half_mean_pct": None,
            "verdict": "too few folds to assess persistence",
        }
    h = n // 2
    early = reductions[:h]
    late = reductions[h:]
    e_med = float(np.median(early)) if early.size else float("nan")
    l_med = float(np.median(late)) if late.size else float("nan")
    e_mean = float(early.mean()) if early.size else float("nan")
    l_mean = float(late.mean()) if late.size else float("nan")
    if not (np.isfinite(e_med) and np.isfinite(l_med)):
        verdict = "indeterminate"
    elif l_med <= 0:
        verdict = "DECAYS to <= 0 out of sample (median reduction not sustained)"
    elif l_med >= 0.5 * e_med:
        verdict = "PERSISTS out of sample (late folds keep most of the median reduction)"
    else:
        verdict = "DECAYS but stays positive (median reduction shrinks out of sample)"
    return {
        "early_half_median_pct": round(e_med * 100.0, 3),
        "late_half_median_pct": round(l_med * 100.0, 3),
        "early_half_mean_pct": round(e_mean * 100.0, 3),
        "late_half_mean_pct": round(l_mean * 100.0, 3),
        "verdict": verdict,
    }


# -------------------- slice driver --------------------
def _observed_headline_reduction(taker_id, day, mo_score, notional, late_cost_rows):
    """Recompute the headline-policy observed reduction cleanly so the placebo p
    is anchored to the exact same quantity (avoids the self-reference in the
    placebo helper). Returns (observed_reduction_frac, sym_cost)."""
    quant = dict((lab, q) for lab, q, _ in SKEW_POLICIES)[PLACEBO_POLICY]
    avoid_frac = dict((lab, a) for lab, _, a in SKEW_POLICIES)[PLACEBO_POLICY]
    early_mask, late_mask = _early_late_masks(day)
    ranked_ids, ranked_score = _rank_by_markout(taker_id, mo_score, early_mask)
    screened_mask = _top_quantile_mask(ranked_ids, ranked_score, quant)
    screened_ids = ranked_ids[screened_mask]
    late_tid = taker_id[late_mask]
    late_cost = late_cost_rows[late_mask]
    late_not = notional[late_mask]
    res = _late_skew_cost(late_tid, late_cost, late_not, screened_ids, avoid_frac)
    return res["cost_reduction_frac"], res["symmetric_cost_usd"]


def _slice_result(taker_id, coin_mask, day, mo_comp, mo_score, notional, cell=None):
    """Full T1+T2 block for one slice (a coin, or pooled).

    cell names the (slice, lens) pair, for the refusal messages of the joint null. Nothing
    is computed from it."""
    tid = np.asarray(taker_id, dtype=np.int64)[coin_mask]
    d = np.asarray(day, dtype=np.int64)[coin_mask]
    m_score = np.asarray(mo_score, dtype=np.float64)[coin_mask]
    m_comp = np.asarray(mo_comp, dtype=np.float64)[coin_mask]
    nt = np.asarray(notional, dtype=np.float64)[coin_mask]

    # per-trade realized adverse-selection cost at the HEADLINE horizon
    # = (mo_score/1e4)*notional.
    # rows with a non-finite markout or notional carry zero cost and zero weight.
    finite = np.isfinite(m_score) & np.isfinite(nt)
    cost_rows = np.where(finite, (np.nan_to_num(m_score) / 1e4) * np.nan_to_num(nt), 0.0)

    # companion-horizon cost rows (reported alongside, same machinery)
    finite_comp = np.isfinite(m_comp) & np.isfinite(nt)
    cost_rows_comp = np.where(finite_comp, (np.nan_to_num(m_comp) / 1e4) * np.nan_to_num(nt), 0.0)

    t1 = _t1_split(tid, d, m_score, nt, cost_rows, cell=cell)

    # anchor the placebo p to the cleanly recomputed observed reduction
    obs_red, sym_cost = _observed_headline_reduction(tid, d, m_score, nt, cost_rows)
    pb = t1["placebo"]
    pb_reductions = pb.pop("_placebo_reductions", None)
    if obs_red is not None and pb_reductions is not None and sym_cost > 0.0:
        pb["observed_reduction_pct"] = round(obs_red * 100.0, 4)
        # Same test, counted by stats.permutation_p: one-sided, +1 floor, denominator
        # the usable draw count. It equals the budget here for the same reason as the
        # size-matched arm -- the branch is entered only when sym_cost > 0, and
        # _reduction_frac returns a finite fraction in that regime -- so no draw is
        # dropped and the p is the number this file has always reported. The absolute
        # 1e-12 is passed rather than the module's scale-relative default, and the
        # returned block records that it was the caller's choice.
        perm = stats.permutation_p(obs_red, pb_reductions, side="greater",
                                   abs_tol=1e-12, n_requested=N_PLACEBO,
                                   cell=("t1_count_matched_placebo", PLACEBO_POLICY))
        pb["placebo_p"] = perm["p"]
        pb["procedure"] = perm
        pb["beats_random_ranking"] = bool(pb["placebo_p"] <= 0.05)
    else:
        # non-positive symmetric base -> the reduction itself is undefined, so
        # there is nothing to place a p-value on. Report null, not a number.
        pb["observed_reduction_pct"] = None
        pb["placebo_p"] = None
        pb["beats_random_ranking"] = False
        pb["reduction_undefined_nonpositive_base"] = True

    # The companion window as a sensitivity block (headline policy only).
    t1_comp = _t1_split_headline_only(tid, d, m_comp, nt, cost_rows_comp)

    t2 = _t2_walk_forward(tid, d, m_score, nt, cost_rows)

    # NAME REPAIR, 2026-07-30. These two blocks used to be written as
    # "t1_early_late_split" and "t1_early_late_split_10s_horizon". The first carried
    # the 10s HEADLINE and said nothing about its window; the second carried the 60s
    # COMPANION under a key that says 10s. So the only key in this file that named a
    # window named the WRONG one, and a reader taking the plainest-looking block got
    # the headline while a reader taking the explicit-looking block got the companion.
    # Both names are now built by settings.field_name from the window that actually
    # produced the block. No value moved: the same numbers are under truthful names.
    return {
        H.field_name("t1_early_late_split", HEADLINE_HORIZON): t1,
        H.field_name("t1_early_late_split", COMPANION_HORIZON): t1_comp,
        "t2_walk_forward": t2,
    }


def _headline_grounds(by_measure):
    """Is this slice a defensible headline? Read the answer off the numbers.

    Two grounds demote a slice, and BOTH ARE MEASURED HERE rather than asserted
    from the slice's name:

      whale-fragile -- dropping the largest wallets leaves a non-positive
        symmetric base, at which point no reduction percentage is defined;
      out of sample negative -- the walk-forward median reduction is below zero.

    DERIVED, 2026-08-27, and the reason is worth keeping. The demotion this file
    used to carry was a literal sentence hung on a coin's name, and nothing ever
    re-read the grounds it stated. Both went stale in silence: on the tree of
    2026-08-27 the whale-dropped symmetric base is POSITIVE on every lens and
    the flag beside it reads false, and no walk-forward fold of that slice is
    negative on any lens. A caution that cannot notice its own grounds have gone
    is not a caution but a sentence. This function reads them every run, records
    what it read, and lets the slice keep or lose its status on that reading.
    """
    lens = by_measure.get(H.HEADLINE_LENS, {})
    split = lens.get(H.field_name("t1_early_late_split", HEADLINE_HORIZON), {})
    whale = split.get(f"whale_robustness_{WHALE_DROP_KEY}", {})
    wf = lens.get("t2_walk_forward", {})
    folds = wf.get("fold_reduction_series_pct") or []

    whale_fragile = bool(whale.get("reduction_undefined_nonpositive_base", False))
    oos_median = wf.get("median_cost_reduction_pct")
    oos_negative = oos_median is not None and oos_median < 0.0

    return {
        "lens_read": H.HEADLINE_LENS,
        "whale_fragile": whale_fragile,
        "symmetric_cost_no_whales_usd": whale.get("symmetric_cost_no_whales_usd"),
        "out_of_sample_negative": oos_negative,
        "walk_forward_median_pct": oos_median,
        "walk_forward_negative_folds": int(sum(1 for f in folds if f < 0.0)),
        "walk_forward_folds": len(folds),
        "cautionary": whale_fragile or oos_negative,
    }


def _t1_split_headline_only(taker_id, day, mo, notional, cost_rows):
    """Lightweight T1 for the COMPANION window: headline policy only, no placebo and
    no whale check (those run on the headline window). Keeps the json honest about
    which window drives the claim while still showing the companion sensitivity."""
    quant = dict((lab, q) for lab, q, _ in SKEW_POLICIES)[HEADLINE_POLICY]
    avoid_frac = dict((lab, a) for lab, _, a in SKEW_POLICIES)[HEADLINE_POLICY]
    early_mask, late_mask = _early_late_masks(day)
    ranked_ids, ranked_score = _rank_by_markout(taker_id, mo, early_mask)
    screened_mask = _top_quantile_mask(ranked_ids, ranked_score, quant)
    screened_ids = ranked_ids[screened_mask]
    late_tid = taker_id[late_mask]
    late_cost = cost_rows[late_mask]
    late_not = notional[late_mask]
    res = _late_skew_cost(late_tid, late_cost, late_not, screened_ids, avoid_frac)
    return {
        "policy": HEADLINE_POLICY,
        "n_toxic_wallets": int(screened_ids.size),
        "symmetric_cost_usd": round(res["symmetric_cost_usd"], 2),
        "skew_cost_usd": round(res["skew_cost_usd"], 2),
        "cost_reduction_pct": _pct_or_none(res["cost_reduction_frac"]),
        "reduction_undefined_nonpositive_base": res["reduction_undefined_nonpositive_base"],
        "notional_given_up_pct": round(res["notional_given_up_frac"] * 100.0, 3),
    }


# -------------------- main --------------------
def main():
    started = artifact.start_clock()
    # panel_io raises when the file is absent and names the producer to run, so the
    # "is it there" test and the "what do I do about it" message live in one place
    # instead of once per script.
    # panel_io names the producer to run when the file is absent, so that message
    # is written once for the whole tree; the load itself stays here because
    # build.py derives this script's input edge from the argument of np.load.
    P.require_present("print", NPZ_PATH)
    z = np.load(NPZ_PATH, allow_pickle=False)
    taker_id = z["taker_id"].astype(np.int64)
    coin = z["coin"].astype(np.int64)
    day = z["day"].astype(np.int64)
    notional = z["notional"].astype(np.float64)
    # taker_side is a v1 field; read it if present (not load-bearing for the cost
    # counterfactual, which keys on realized markout, but recorded for provenance).
    has_side = "taker_side" in z.files

    # THE SECOND LENS, added 2026-08-03. The same fills in the same row order, scored
    # against the BOOK MID instead of the trade print. It is loaded rather than derived
    # because there is nothing to derive it from: the print markout has the earned
    # spread inside it and the mid markout does not, and the difference is the spread
    # itself, which this panel measures and that one does not carry.
    #
    # ROW ALIGNMENT IS ASSERTED AND NOT ASSUMED. i4_midmarkout.py builds the mid panel
    # row by row from the print panel and records row_aligned_to_print_npz in its own
    # artifact, but a claim in a neighbour's results file is that neighbour's claim.
    # Four key columns are compared here, and a mismatch aborts rather than producing
    # a cost figure whose two lenses describe different fills.
    P.require_present("mid", MID_NPZ_PATH)
    z_mid = np.load(MID_NPZ_PATH, allow_pickle=False)
    align_ok = {}
    for k in ("taker_id", "coin", "day", "taker_side"):
        if k in z.files and k in z_mid.files:
            align_ok[k] = bool(np.array_equal(z[k], z_mid[k]))
            if not align_ok[k]:
                raise SystemExit(
                    f"[t1] ROW MISALIGNMENT on {k!r} between "
                    f"{os.path.basename(NPZ_PATH)} and {os.path.basename(MID_NPZ_PATH)}"
                    f" - the two lenses would describe different fills; abort")
    align_ok["notional"] = bool(np.allclose(
        notional, z_mid["notional"].astype(np.float64), rtol=0, atol=1e-3,
        equal_nan=True))

    # headline lens FIRST: settings.HEADLINE_LENS declares the book mid, and the order
    # here is what the console summary and every by_measure dict inherit.
    lens_columns = {
        "mid": (P.score(z_mid, "mid"), P.score(z_mid, "mid", COMPANION_HORIZON)),
        "print": (P.score(z, "print"), P.score(z, "print", COMPANION_HORIZON)),
    }
    if H.HEADLINE_LENS not in lens_columns:
        raise SystemExit(f"[t1] settings.HEADLINE_LENS is {H.HEADLINE_LENS!r} and this "
                         f"file computes {sorted(lens_columns)}; one of the two is wrong")

    present_days = sorted(int(d) for d in np.unique(day))
    early_present, late_present = _early_late_days(day)
    early_present, late_present = list(early_present), list(late_present)

    results = {
        "_meta": {
            "object": "T1+T2 - counterparty-toxicity-skewed market-making backtest "
                      "(cost reduction vs a symmetric Avellaneda-Stoikov baseline)",
            "framing": "COST REDUCTION ONLY, NEVER NET ALPHA",
            "headline_horizon_s": HEADLINE_HORIZON,
            "companion_horizon_s": COMPANION_HORIZON,
            "headline_lens": H.HEADLINE_LENS,
            "lenses_computed": list(lens_columns),
            "lens_policy": (
                "BOTH LENSES ARE PUBLISHED AND NEITHER IS WIRED INTO THE INPUT, since "
                "2026-08-03. Every T1 and T2 block sits under <slice>.by_measure.<lens>, "
                "where lens is 'mid' (the book mid, which settings.HEADLINE_LENS "
                "declares and which this file leads with) or 'print' (the trade print, "
                "which is what this object ran on and published alone until that date). "
                "The two are not a rounding apart: the volume-weighted mean 10s markout "
                "is 2.2388 bps on the mid against 0.5208 on the print, because the "
                "print already contains the spread the maker earned, so a cost measured "
                "on it is a cost net of income. The mid is the declared lens because "
                "adverse selection is defined in this study against the book mid; the "
                "print figure is legitimate on its own terms -- the maker is paid at "
                "the print -- and it stays in this file so the earlier versions of this "
                "study that quote it go on reproducing. THE KEYS MOVED: what used to be "
                "<slice>.t1_early_late_split_10s and .t1_early_late_split_60s and "
                ".t2_walk_forward, all three on the PRINT lens without saying so, is "
                "now <slice>.by_measure.print.<same name>. Nothing is repeated at the "
                "old path on purpose: a path that does not name its lens is the defect "
                "this change exists to remove, and leaving one would let a reader take "
                "the mid figure from a key that used to hold the print one."
            ),
            "row_alignment_print_vs_mid": align_ok,
            # Which settings produced these numbers, so a figure lifted out of this
            # file still knows what it was computed under. These are the KEYWORDS for
            # settings.fingerprint rather than the block: artifact.write builds the
            # block once, from this key, and puts it in _meta under the canonical name,
            # so the record has one home. All four migrating settings are stated, so
            # nothing lands in declared_not_confirmed.
            "settings_fingerprint_kwargs": dict(
                h=HEADLINE_HORIZON,
                # The fingerprint carries ONE lens and this file now computes two, so
                # the field states the one the artifact leads with, which since
                # 2026-08-03 is the declared book mid. It read "print" until that date
                # and disagreed with headline_lens in the same block, which was the
                # honest record of a real gap and not a mis-stamping. The gap is closed
                # by computing both rather than by relabelling one: _meta.lenses_computed
                # names them and _meta.lens_policy says where each block lives.
                lens=H.HEADLINE_LENS,
                master_seed=RNG_SEED,
                n_perm=N_PLACEBO,
                n_boot=None,
                rank_floor_fills=MIN_RANK_TRADES,
                size_matched_placebo_draws=N_SIZE_PLACEBO,
                whale_drop_criterion=WHALE_DROP_CRITERION,
                early_days=early_present,
                late_days=late_present,
                override_reasons={
                    "master_seed": f"every random stream here is derived from {RNG_SEED}, "
                                   f"not from the declared {H.MASTER_SEED}. Derived and "
                                   f"not equal: the count-matched null takes {RNG_SEED} "
                                   f"itself, the size-matched null {RNG_SEED + 1}, and "
                                   f"the joint null {RNG_SEED + 2} with the chain index "
                                   f"beside it in the entropy, and each block records the "
                                   f"number its own generator was built from. This key "
                                   f"read 'every random stream here is seeded {RNG_SEED}' "
                                   f"until 2026-08-30, which was true of one stream of "
                                   f"three. settings.MASTER_SEED carries the state "
                                   f"'target', so adopting it re-draws all three streams "
                                   f"and moves every published placebo number",
                    "n_boot": "no bootstrap runs in this file; the intervals here are "
                              "permutation and stratified-draw nulls, so the declared "
                              "bootstrap budget does not apply",
                    "whale_drop_criterion": "this file drops the largest wallets by "
                                            "NOTIONAL, answering 'is the reduction a "
                                            "volume artifact'; t3_capacity.py drops by "
                                            "COST, answering 'is it ten wallets'",
                },
            ),
            "early_days": early_present,
            "late_days": late_present,
            "split_rule": (
                "The ranking and evaluation halves are DERIVED from the days present, "
                "by settings.split_early_late: first ceil(n/2) days early, the rest "
                "late. They used to be the hardcoded day-of-month tuples (4,5,6,7,8) "
                "and (9,10,11,12,13), which are correct only for a window opening on "
                "the 4th and closing on the 13th. This input does open on the 4th, so "
                "the derived split reproduces those tuples exactly and no number moved."
            ),
            "present_days": present_days,
            "min_rank_trades": MIN_RANK_TRADES,
            "skew_policies": [
                {"label": lab, "top_quantile": q, "avoid_fraction": a}
                for lab, q, a in SKEW_POLICIES
            ],
            "headline_policy": HEADLINE_POLICY,
            "markout_sign": "signed taker markout bps; positive = taker profited = "
                            "maker adverse-selected; positive cost = maker loss",
            "oos_split": "by TIME - ranking on EARLY days, evaluation on LATE days; "
                         "no wallet's late data informs its own ranking",
            "placebo_count_matched": f"label-permutation of the toxicity ranking, "
                       f"{N_PLACEBO} shuffles, seed {RNG_SEED}; the null draws a RANDOM "
                       f"set of the SAME NUMBER of wallets. A real reduction must beat "
                       f"a random-ranking maker (placebo p <= 0.05). WEAKNESS: does NOT "
                       f"control for notional - toxic wallets are also large, so this "
                       f"null turns away far less volume and its mean (~6.9%) "
                       f"understates the pure-size baseline.",
            "placebo_size_matched": f"draw {N_SIZE_PLACEBO} random wallet sets matched "
                       f"on TOTAL LATE NOTIONAL of the observed toxic set "
                       f"({SIZE_PLACEBO_DECILES} notional strata, seed {RNG_SEED + 1}); "
                       f"this null turns away the SAME dollar volume, so its reduction "
                       f"(mean ~30.4% / p95 ~56.6%) is the PURE-SIZE baseline. The "
                       f"Monte Carlo tail probability of the observed toxicity-ranked "
                       f"reduction against THIS null (~0.002) is the share of its draws "
                       f"that reached the observed value under the procedure declared "
                       f"here. It is NOT a demonstration that wallet identity is "
                       f"statistically significant: the draws control HOW-MUCH and the "
                       f"tail says only how rarely they reached the observed cut. "
                       f"A deterministic size-only screen "
                       f"(decline top decile by notional, no toxicity) ~44.9% is also "
                       f"reported.",
            "placebo_joint_matched": (
                f"draw {N_JOINT_PLACEBO} wallet sets holding BOTH axes at once, over "
                f"{JOINT_PLACEBO_CHAINS} independent starts (seed {RNG_SEED + 2}, the "
                f"chain index in the entropy beside it): exactly the observed number of "
                f"wallets, and a total late notional within {JOINT_PLACEBO_TOL_PCT} per "
                f"cent of the observed toxic set's. The two nulls above hold one axis each "
                f"and let the other run, and passing them separately is not passing one "
                f"null that holds both, because a set can satisfy either constraint by "
                f"breaking the other. The sets come from a swap walk that never leaves the "
                f"region, stepped in ATTEMPTED swaps so the chain is read at fixed times, "
                f"and mixing single swaps with paired ones because single swaps alone "
                f"freeze the largest wallet of a set for the whole chain. THE WALK DOES "
                f"NOT FORGET ITS START ON THIS DATA and nothing here pretends otherwise: "
                f"the starts disagree about where the null sits on every cell, the spread "
                f"is published in each block's chain_agreement, and a cell whose starts "
                f"disagree about the TAIL gets NO number at all. "
                f"AND THIS NULL PUBLISHES NO P-VALUE ON ANY CELL, which the two above do: "
                f"a p-value is a probability under a known null distribution, and this "
                f"one's draws come from a walk whose distribution over the region is not "
                f"established, as every block of it says in its own claim. What is "
                f"published instead is joint_matched_tail_fraction_floored, the share of "
                f"the draws that reached the observed reduction with the observed set "
                f"counted as one of them, and THREE PLAIN FACTS beside it that carry no "
                f"threshold: n_draws_at_or_above_observed of n_draws, the largest reduction "
                f"any draw reached at joint_matched_max_reduction_pct, and the observed "
                f"value itself at observed_reduction_pct. Until 2026-08-30 the fraction was "
                f"written under a key ending in _p and beside a flag reading "
                f"toxicity_beats_joint_matched, which read as the verdict of a test that "
                f"was never run; no threshold reading replaces it, because a flag saying "
                f"'at or below five per cent' would be that same verdict under another "
                f"name. The counting is unchanged and no number moved with the names. "
                f"WHY THE STARTS DISAGREE IS MEASURED AND IS PUBLISHED AT region_freedom: "
                f"the observed set's own largest members carry most of its notional and the "
                f"pool holds nothing to swap them for one for one, so a draw is largely "
                f"settled by which large wallets its chain entered with. That is also the "
                f"caveat this null owes a reader, because the two grow together: the same "
                f"resemblance that makes it stricter than either single-axis null makes it "
                f"degenerate where the largest member is large, since every admissible draw "
                f"is then a near-copy of the observed set. "
                f"IT SITS HIGHER THAN THE SIZE-MATCHED NULL, NOT LOWER, measured on this "
                f"run: holding the count as well as the volume forces every draw to "
                f"resemble the observed toxic set, and a set that resembles it recovers "
                f"more of its reduction, so this null stands nearer the observed value than "
                f"either single-axis one. What a surviving cell "
                f"asserts is that over {JOINT_PLACEBO_CHAINS} independent starts holding "
                f"both axes, no draw reached the observed reduction -- weaker than a "
                f"uniform null over the region, stronger than either single-axis null. "
                f"Every block also records the outcome of three calibration cases the "
                f"region test is run against on that cell's own wallets. It REPLACES "
                f"NEITHER of the other two."
            ),
            "fill_model_extension_note": (
                "The 'no fill model' objection can be answered by a minimal "
                "fill model: recapture a fraction f of declined toxic notional at a "
                "widened quote plus a per-requote penalty. NOT implemented here - this "
                "object stays a realized-markout counterfactual."
            ),
            "whale_robustness": (
                f"drop the {WHALE_DROP_K} largest wallets by {WHALE_DROP_CRITERION}, "
                f"re-rank and re-evaluate the headline policy. The block key states "
                f"both the count and the criterion (whale_robustness_"
                f"{WHALE_DROP_KEY}), because dropping by notional answers 'is the "
                f"reduction a volume artifact' while dropping by cost answers 'is it "
                f"ten wallets' -- t3_capacity.py drops by cost and this file drops by "
                f"notional, and under a key naming only the count the two checks "
                f"looked interchangeable."
            ),
            "headline_scope_note": (
                "Which slices are defensible headlines is DERIVED from the numbers "
                "of this very run and is not declared at this key. Each slice "
                "carries a headline_grounds block saying what was read and which "
                "ground, if any, fired; the two lists below are filled from those "
                "blocks after the slice walk. Until 2026-08-27 this key held a "
                "literal sentence keyed on a coin's name, and both of the grounds "
                "it stated had gone stale without anything noticing, because "
                "nothing re-read them."
            ),
            "defensible_headline_slices": [],   # filled after the slice walk
            "cautionary_slices": [],            # filled after the slice walk
            "taker_side_present": has_side,
            "rng_seed": RNG_SEED,
            "fee_note": FEE_NOTE,
            "scope_note": SCOPE_NOTE,
            "taker_fee_band_bps": list(PER_TAKER_FEE_BPS),
            "npz_path": os.path.basename(NPZ_PATH),
        }
    }

    slices = [(name, coin == code) for code, name in COIN_CODES.items()]
    slices.append(("pooled", np.ones(coin.shape, dtype=bool)))
    t_lens = artifact.start_clock()
    for name, mask in slices:
        if mask.sum() == 0:
            results[name] = {"note": "no rows for this coin"}
            continue
        by_measure = {}
        for lens, (mo_score, mo_comp) in lens_columns.items():
            by_measure[lens] = _slice_result(taker_id, mask, day, mo_comp, mo_score,
                                             notional, cell=(name, lens))
            print(f"[t1] {name} lens={lens}: T1+T2 done "
                  f"({(time.time() - t_lens) / 60:.1f} min into the slice walk)",
                  flush=True)
        # Status is DERIVED from this run's own numbers, never from the name of
        # the slice. See _headline_grounds for what is read and why.
        grounds = _headline_grounds(by_measure)
        head = {"headline_status": ("CAUTIONARY - not a headline slice"
                                    if grounds["cautionary"]
                                    else "defensible headline slice"),
                "headline_grounds": grounds}
        results[name] = {**head, "by_measure": by_measure}

    # Fill the two scope lists from what this run measured, in slice order.
    for _nm, _blk in results.items():
        if _nm.startswith("_") or not isinstance(_blk, dict):
            continue
        _g = _blk.get("headline_grounds")
        if _g is None:
            continue
        _key = "cautionary_slices" if _g["cautionary"] else "defensible_headline_slices"
        results["_meta"][_key].append(_nm)

    settings_used = results["_meta"].pop("settings_fingerprint_kwargs")
    artifact.write(
        os.path.basename(RESULTS_PATH), results,
        script=__file__,
        inputs=[NPZ_PATH, MID_NPZ_PATH],
        scope={
            "population": (
                f"{int(taker_id.size)} taker fills and "
                f"{int(np.unique(taker_id).size)} wallets; the toxicity ranking is "
                f"built on wallets with at least {MIN_RANK_TRADES} fills in the early "
                f"half and evaluated on the late half, per coin and pooled, and the "
                f"whole of that once per lens -- the ranking is rebuilt on each "
                f"reference price rather than carried across, so the screened wallet "
                f"set is a property of the lens too and not only the cost is"),
            "lenses": list(lens_columns),
            "window": (
                f"days {present_days[0]}-{present_days[-1]}, split by "
                f"settings.split_early_late into ranking days {early_present} and "
                f"evaluation days {late_present}"),
            "coins": sorted(COIN_CODES.values()),
        },
        settings=settings_used,
        started=started)

    _print_summary(results)


def _fmt_pct(v, width=8, dec=2):
    """Format a percentage that may be None (undefined non-positive base) as the
    literal token 'undef' instead of crashing the format spec."""
    if v is None:
        return f"{'undef':>{width}}"
    return f"{v:>{width}.{dec}f}%"


def _print_summary(results):
    lo, hi = PER_TAKER_FEE_BPS
    meta = results["_meta"]
    print("=" * 82)
    print("OBJECT T1+T2 - COUNTERPARTY-TOXICITY-SKEWED MARKET-MAKING BACKTEST")
    print("=" * 82)
    print("  DELIVERABLE = relative REDUCTION in adverse-selection COST, NOT net alpha.")
    print(f"  Ranking on EARLY days {meta['early_days']} -> evaluation on "
          f"LATE days {meta['late_days']} (split derived from the days present).")
    print(f"  Headline horizon {meta['headline_horizon_s']}s; headline policy "
          f"'{meta['headline_policy']}'.")
    print(f"  DEFENSIBLE HEADLINE = {meta['defensible_headline_slices']}; "
          f"CAUTIONARY = {meta['cautionary_slices']} "
          f"(read off this run, not declared).")
    print("-" * 82)

    # pooled + BTC are the headline; ETH prints last under a cautionary banner. Every
    # slice is printed once PER LENS, because the two are different costs and a summary
    # that showed one of them would put the reader back where the by_measure key was
    # added to get them out of: reading a figure without knowing its reference price.
    hl_block = H.field_name("t1_early_late_split", HEADLINE_HORIZON)
    for key in ("pooled", "BTC", "ETH"):
        r = results.get(key)
        if r is None or "by_measure" not in r:
            continue
        for lens, t1_all in r["by_measure"].items():
            if hl_block not in t1_all:
                continue
            cautionary = bool(r.get("headline_grounds", {}).get("cautionary"))
            if cautionary:
                print("  !! CAUTIONARY SUB-RESULT - NOT A HEADLINE !!")
            t1 = t1_all[hl_block]
            tag = "CAUTIONARY" if cautionary else "headline"
            tag = f"{tag}, lens={lens}" + (" <- declared" if lens == H.HEADLINE_LENS else "")
            print(f"  [{key}] ({tag})  symmetric late cost = "
                  f"${t1['symmetric_late_cost_usd']:,.2f}  over "
                  f"{t1['n_late_trades']:,} late trades; "
                  f"{t1['n_ranked_wallets']:,} ranked wallets")
            print(f"    {'policy':<22} {'cost-red%':>9} {'gave-up%':>9} "
                  f"{'benign%ofGU':>12} {'#toxic':>7}")
            for label, _, _ in SKEW_POLICIES:
                p = t1["policies"][label]
                flag = "  [undef base]" if p.get("reduction_undefined_nonpositive_base") else ""
                print(f"    {label:<22} {_fmt_pct(p['cost_reduction_pct'], 8)} "
                      f"{p['notional_given_up_pct']:>8.2f}% "
                      f"{p['benign_share_of_given_up_pct']:>11.2f}% "
                      f"{p['n_toxic_wallets']:>7,}{flag}")
            pb = t1["placebo"]
            sm = t1["size_matched_placebo"]
            wh = t1[f"whale_robustness_{WHALE_DROP_KEY}"]
            pp = pb.get("placebo_p")
            obs = pb.get("observed_reduction_pct")
            pmean = pb.get("placebo_mean_reduction_pct")
            print(f"    COUNT-matched placebo ({pb.get('n_shuffles')} shuffles, p-floor "
                  f"{pb.get('p_floor'):.4g}): observed reduction "
                  f"{('undef' if obs is None else format(obs, '.3f') + '%')} vs "
                  f"random-ranking mean "
                  f"{('undef' if pmean is None else format(pmean, '.3f') + '%')}  "
                  f"(p={pp if pp is None else round(pp, 4)}, "
                  f"beats_random={pb.get('beats_random_ranking')})")
            sm_mean = sm.get("size_matched_mean_reduction_pct")
            sm_p95 = sm.get("size_matched_p95_reduction_pct")
            sm_p = sm.get("toxicity_vs_size_matched_p")
            sm_so = sm.get("size_only_top_decile_by_notional_reduction_pct")
            print(f"    SIZE-matched placebo ({sm.get('n_draws')} draws, matched on toxic "
                  f"notional): pure-size null mean "
                  f"{('undef' if sm_mean is None else format(sm_mean, '.3f') + '%')} / p95 "
                  f"{('undef' if sm_p95 is None else format(sm_p95, '.3f') + '%')}; "
                  f"top-decile-by-notional (upper bound) "
                  f"{('undef' if sm_so is None else format(sm_so, '.3f') + '%')}")
            print(f"      => observed toxicity reduction "
                  f"{('undef' if obs is None else format(obs, '.3f') + '%')} sits ABOVE the "
                  f"~{('n/a' if sm_mean is None else format(sm_mean, '.1f'))}% pure-size "
                  f"baseline; toxicity vs size-matched null p="
                  f"{sm_p if sm_p is None else round(sm_p, 4)} "
                  f"(tail<=0.05={sm.get('toxicity_beats_size_matched')}) "
                  f"=> a Monte Carlo tail under this null, not a significance "
                  f"verdict on identity")
            jm = t1.get("joint_matched_placebo", {})
            if jm:
                jm_mean = jm.get("joint_matched_mean_reduction_pct")
                jm_p95 = jm.get("joint_matched_p95_reduction_pct")
                jm_max = jm.get("joint_matched_max_reduction_pct")
                jm_tail = jm.get("joint_matched_tail_fraction_floored")
                if jm.get("refused"):
                    print(f"    JOINT-matched placebo: REFUSED - "
                          f"{'; '.join(jm.get('refusal_reasons', []))}")
                else:
                    ax = jm.get("axes_held", {})
                    ag = jm.get("chain_agreement", {})
                    sm_p95_here = sm.get("size_matched_p95_reduction_pct")
                    print(f"    JOINT-matched placebo ({jm.get('n_draws')} draws, "
                          f"{jm.get('n_toxic_wallets')} wallets held exactly + notional "
                          f"within {jm.get('tolerance_pct')}%): null mean "
                          f"{('undef' if jm_mean is None else format(jm_mean, '.3f') + '%')}"
                          f" / p95 "
                          f"{('undef' if jm_p95 is None else format(jm_p95, '.3f') + '%')}"
                          f" / max "
                          f"{('undef' if jm_max is None else format(jm_max, '.3f') + '%')}"
                          f"  (tail fraction "
                          f"{jm_tail if jm_tail is None else round(jm_tail, 4)}, which is "
                          f"NOT a p-value; no draw reached the observed="
                          f"{jm.get('no_draw_reached_observed')})")
                    print(f"      axes held: count "
                          f"{ax.get('draw_n_wallets_min')}-{ax.get('draw_n_wallets_max')} "
                          f"of a required {jm.get('n_toxic_wallets')}; notional miss "
                          f"{ax.get('draw_notional_dev_pct_min')}% to "
                          f"{ax.get('draw_notional_dev_pct_max')}%; region test calibrated="
                          f"{jm.get('predicate_calibration', {}).get('calibrated')}; "
                          f"starts agree on the tail={ag.get('agree')} "
                          f"(per-chain tail counts {ag.get('per_chain_tail_counts')})")
                    print(f"      the null's LOCATION is start-dependent and is reported as "
                          f"such: chain means run {ag.get('chain_mean_reduction_min_pct')}% "
                          f"to {ag.get('chain_mean_reduction_max_pct')}% over "
                          f"{jm.get('n_chains')} starts")
                    sm_mean_here = sm.get("size_matched_mean_reduction_pct")
                    print(f"      against the size-matched null on this cell: mean "
                          f"{('undef' if sm_mean_here is None else format(sm_mean_here, '.3f') + '%')}"
                          f" -> {('undef' if jm_mean is None else format(jm_mean, '.3f') + '%')}, "
                          f"p95 {('undef' if sm_p95_here is None else format(sm_p95_here, '.3f') + '%')}"
                          f" -> {('undef' if jm_p95 is None else format(jm_p95, '.3f') + '%')}. "
                          f"Holding the COUNT as well as the volume makes every draw RESEMBLE "
                          f"the toxic set, so this null generally stands NEARER the observed "
                          f"value, not further from it")
            wh_red = wh.get("cost_reduction_no_whales_pct")
            full_red = t1["policies"][HEADLINE_POLICY]["cost_reduction_pct"]
            wh_undef = " [undef base: drop-whale symmetric cost <= 0]" if wh.get(
                "reduction_undefined_nonpositive_base") else ""
            print(f"    whale check (drop top-{wh['n_whales_dropped']} "
                  f"by {wh['whale_criterion']}): "
                  f"reduction {('undef' if wh_red is None else format(wh_red, '.2f') + '%')} "
                  f"(vs {('undef' if full_red is None else format(full_red, '.2f') + '%')} "
                  f"full){wh_undef}")
            t2 = t1_all["t2_walk_forward"]
            per = t2["persistence"]
            med = t2.get("median_cost_reduction_pct")
            mean = t2.get("mean_cost_reduction_pct")
            std = t2.get("std_cost_reduction_pct")
            e_med = per.get("early_half_median_pct")
            l_med = per.get("late_half_median_pct")
            print(f"    walk-forward ({t2['n_evaluable_folds']} folds): MEDIAN reduction "
                  f"{('n/a' if med is None else format(med, '.2f') + '%')} (primary); "
                  f"mean {('n/a' if mean is None else format(mean, '.2f') + '%')} +/- "
                  f"{('n/a' if std is None else format(std, '.2f') + '%')}")
            print(f"      early-half median {e_med}% -> late-half median {l_med}%  "
                  f"=> {per['verdict']}")
            print(f"      fold series: {t2.get('fold_reduction_series_pct')}")
            print("-" * 82)

    print("  HONEST FRAMING (cost reduction, not alpha):")
    print(f"    gross vol-weighted mean 60s markout on this flow is sub-1 bps, BELOW")
    print(f"    the perp taker-fee band ~{lo}-{hi} bps (plus funding) -> NO net edge")
    print(f"    is possible or claimed. The numbers above are COST reductions only,")
    print(f"    and skewing forgoes benign volume (the 'gave-up%' column).")
    print(f"  WHO vs HOW-MUCH (size-matched reframe): toxic wallets are ALSO large, so")
    print(f"    the headline reduction is NOT all toxicity. A SIZE-MATCHED null that")
    print(f"    turns away the SAME notional at random already gives ~30% (pure-size")
    print(f"    baseline). The toxicity-ranked screen sits ABOVE that baseline and")
    print(f"    beats the size-matched null at p~0.002, so the MARGINAL value is WHO")
    print(f"    (toxicity) over and above HOW-MUCH (size) - real, but materially")
    print(f"    smaller than the raw headline percentage implies.")
    print(f"  SCOPE: counterfactual on realized markout, no LOB/fill simulation;")
    print(f"    single December window; VALIDATION/ILLUSTRATION, not a powered claim.")
    print(f"    A fill-model extension (recapture fraction f at a widened quote +")
    print(f"    requote penalty) answers the no-fill-model objection; not run here.")
    print(f"  A slice is CAUTIONARY only where THIS RUN measured it so;")
    print(f"    a reduction is reported only where the symmetric base is positive")
    print(f"    (sym_cost > 0). Where it is not, the json carries 'undef' + the flag")
    print(f"    'reduction_undefined_nonpositive_base', never a >100% percentage.")
    print("-" * 82)
    print(f"  results -> {RESULTS_PATH}")
    print("=" * 82)


if __name__ == "__main__":
    main()
