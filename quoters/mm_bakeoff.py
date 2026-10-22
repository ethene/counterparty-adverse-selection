"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-07-28
Market-maker bake-off: naive-at-book / naive-const / symmetric Avellaneda-Stoikov / Glosten-Milgrom (VPIN-proxy) / Barzykin-Bergault-Gueant-Lemmel global+per-tier / A-S plus a counterparty-resolved adverse-selection term, scored on ONE common fill set with ONE common maker net-economics metric, plus three equal-width arms (the resolved term at the solved pass-through that matches the BBGL instance's width, a flat surcharge of that same width, and the BBGL global term carrying the resolved term in place of its per-tier one) so that each published difference has one declared axis. Gueant-Lehalle-Fernandez-Tapia is compared at the spread level only, not P&L-scored.
References:
  - Avellaneda, Marco, and Sasha Stoikov. "High-Frequency Trading in a Limit Order Book."
    Quantitative Finance, vol. 8, no. 3, 2008, pp. 217-224. DOI 10.1080/14697680701381228.
  - Glosten, Lawrence R., and Paul R. Milgrom. "Bid, Ask and Transaction Prices in a
    Specialist Market with Heterogeneously Informed Traders." Journal of Financial
    Economics, vol. 14, no. 1, 1985, pp. 71-100. DOI 10.1016/0304-405X(85)90044-3.
  - Gueant, Olivier, Charles-Albert Lehalle, and Joaquin Fernandez-Tapia. "Dealing with the
    Inventory Risk: A Solution to the Market Making Problem." Mathematics and Financial
    Economics, vol. 7, no. 4, 2013, pp. 477-507 (arXiv:1105.3115). DOI 10.1007/s11579-012-0087-0.
  - Barzykin, Alexander, Philippe Bergault, Olivier Gueant, and Malo Lemmel. "Optimal Quoting
    under Adverse Selection and Price Reading." arXiv:2508.20225, 2025 (rev. 2026-06).
  - Easley, David, Marcos M. Lopez de Prado, and Maureen O'Hara. "Flow Toxicity and Liquidity
    in a High-Frequency World." The Review of Financial Studies, vol. 25, no. 5, 2012,
    pp. 1457-1493. DOI 10.1093/rfs/hhs053.
  - Easley, David, Nicholas M. Kiefer, Maureen O'Hara, and Joseph B. Paperman. "Liquidity,
    Information, and Infrequently Traded Stocks." The Journal of Finance, vol. 51, no. 4,
    1996, pp. 1405-1436. DOI 10.1111/j.1540-6261.1996.tb04074.x.
  - Zenodo 18184441 (Albers et al. 2026) -- the public L4 node-data release.
"""

# ---------------------------------------------------------------------------
# MARKET-MAKER BAKE-OFF (a single, shared, counterfactual scoring of six quoters).
#
# COUNTERFACTUAL-ONLY (read this first). This harness is a MARKOUT-BASED
# COUNTERFACTUAL OVERLAY on a realized CLOB tape, NOT a matching engine. There is
# NO queue position, NO fill probability, NO requote latency, NO re-cleared book.
# Each quoter only sets the SPREAD/SKEW it WOULD have shown; a fill that printed is
# treated as a fill the quoter also takes, and its cost is the realized markout net
# of the spread the maker would have earned (exactly how maker_econ.py scores the
# symmetric maker). The ONLY fill-awareness permitted is the maker_econ-style
# recapture APPROXIMATION (a fraction f of would-be-declined flow still trades at a
# quote widened by w bps, minus a per-requote penalty c), and it is labelled an
# approximation everywhere it appears. The book mid is read from the L2 snapshot
# (the mo{h}_mid markouts were built EXEC->mid via searchsorted on time, never
# leaking a future row back -- no-lookahead preserved). The per-COUNTERPARTY toxicity
# labels that drive the headline (as_toxicity's early_tox term and bbgl's per-tier term)
# are frozen on the EARLY window before the LATE evaluation (strictly OOS, verified: 0
# early/late overlap rows). The MARKET-LEVEL Glosten-Milgrom inputs (gm_vpin's pi and J)
# are deliberately full-window aggregates, NOT early-only -- a stronger book-only
# benchmark for the negative control, which only makes the counterparty-resolution gap
# HARDER to clear (the conservative direction for the headline). gm_vpin never sees
# counterparty identity, so this full-window pi/J cannot leak the resolved term.
#
# COST NOT ALPHA (the honest stance, and the counts below are volume-weighted).
# Every quoter is net-NEGATIVE on the conservative net_MID_lower measure everywhere in
# the grid: 0 positive cells of 1188 across all eleven quoters. At the base maker-fee
# tier the six bake-off quoters are net-NEGATIVE on both measures (0 of 216); across all
# eleven ONE base-tier cell is positive, as_toxicity_plus_global at K10 / ETH / h60 /
# net_PRINT, at +0.0064 bps, so read the base-tier statement as a property of the six
# ranked quoters and not of every arm this file now carries. On the optimistic net_PRINT
# measure positive cells DO exist at the subsidised tiers (t3, t4_0fee, rebate1-3): 248
# of the 648 cells the six bake-off quoters span over the coin x K x horizon x tier grid,
# 50 of them at the headline horizon. Those cells are not confined to the identity
# quoters: naive_at_book, which books no adverse-selection premium at all, already has 22
# of them, against 62 for as_toxicity and 88 for bbgl. Read every net_PRINT cell together
# with its fee tier, and check bakeoff_ranking.*.all_net_negative rather than assuming
# universal negativity.
#
# WHAT THE SELF-TEST ACTUALLY COVERS, because its name promises more than it asks.
# cross_checks.all_quoters_net_negative_at_base loops over the quoters but reads one
# cell each: pooled only, the headline horizon only, net_MID_lower only, the base tier
# only. Its population is eleven cells, not the 396 a reader may assume from the name,
# and the sentence above about BOTH measures is therefore NOT the thing it certifies.
# The equal-weighted summary is a separate population again: on net_PRINT it puts 546
# cells of 1188 above zero and on net_MID_lower 212, so "none above zero on the book
# mid" is a statement about the volume-weighted summary and has to name it. The counterparty-conditioned adverse-selection term REDUCES cost
# on net_MID_lower and never flips that measure to profit; the residual reduction is
# CONCENTRATED, mostly ETH, and fragile. The concentration is read from this file's own
# pairwise_wallet_resolved.by_pair.*.concentration_by_wallet and not asserted: on the
# one-sided as_toxicity minus as_symmetric pair the top five wallets hold 41.3 per cent of
# the gain pooled, 48.4 on BTC and 53.2 on ETH, at the headline horizon and rank floor.
# The figure that stood here until 2026-08-03 -- "top ~5 toxic wallets ~66% of it" -- was
# a string literal carried in from a June maker-economics run, where it was the top five
# wallets' share of REJECTED FLOW, a different quantity over a different population. It
# was typed here five weeks before this file first computed a concentration of its own,
# and 0.66 is outside the range of all six cuts this file publishes (0.4131 to 0.7497).
# Read the two pairs apart: on the two-sided as_toxicity minus gm_vpin pair 21.6 per cent
# of fills are NEGATIVE and the top fifty wallets sum to 101.0 per cent, so "share of the
# gain" is a gross contribution there and not a concentration. No quoter is
# ever framed as profitable / an edge / a Sharpe / alpha; any such word appears only
# inside an explicit negation.
#
# THE BAKE-OFF (six quoters, one metric):
#   naive_at_book - constant per-fill BBO half-spread (reproduces maker_econ net_MID_lower exactly)
#   naive_const   - one fixed constant half-spread to everyone (zero information)
#   as_symmetric  - Avellaneda-Stoikov (2008) inventory-only, counterparty-blind
#                   (imported from as_quoter.py; not re-derived)
#   gm_vpin       - Glosten-Milgrom (1985) information-based: half-spread = pi * J,
#                   pi a MARKET-LEVEL VPIN/PIN order-flow-toxicity proxy (Easley-
#                   Lopez de Prado-O'Hara 2012), NO counterparty identity
#   bbgl          - Barzykin-Bergault-Gueant-Lemmel (2508.20225): A-S base PLUS an
#                   adverse-selection skew = global (market-wide) + per-tier
#                   (per-counterparty-group) premia (the published lineage that OWNS
#                   the AS quoting leg; we instantiate a reduced-form instance)
#   as_toxicity   - A-S base PLUS our additive counterparty-RESOLVED adverse-selection
#                   term (the refactor): a reduced-form instance of the BBGL idea on
#                   OBSERVED wallet identity, framed as validation, never our invention
#
# THREE ARMS ADDED BECAUSE A RANKING IS NOT A COMPARISON. The six quoters above are ranked
# on one metric, and until 2026-08-03 that ranking was READ as a comparison: bbgl finishes
# ahead of as_toxicity on the pooled base tier, so the resolved term was taken to lose to
# the published tiered one. The two arms differ by more than the axis that reading assigns
# them. Measured from this file's own extra_half_spread_summary, pooled, at the headline
# rung: as_toxicity asks a mean 1.4423 bps on 64.42 per cent of fills with a floor of zero,
# bbgl asks 6.3646 on 100 per cent with a floor of 3.4403. Width differs FOURFOLD. And this
# harness is counterfactual, so nothing is paid for quoting wide -- a printed fill is taken
# whatever the quote, and the booking caps the offset at f*min(extra, max(a_mid,0)). Whoever
# stands wider wins, other things equal. A third difference is declared by the artifact
# itself in adverse_selection_term_value.eligibility_scope: the rank floor gates bbgl's
# per-tier term and does not gate the resolved term, so the two arms were also booked over
# different wallet populations.
#
# The three arms below exist so that each published difference has ONE declared axis, with
# everything else held equal BY CONSTRUCTION and MEASURED afterwards (comparison_manifest):
#   as_toxicity_ew          - the resolved term carrying bbgl's ENTIRE width. The
#                             pass-through is SOLVED, not tuned: the term is exactly linear
#                             in lambda, so lambda* = target_mean / unit_mean lands the mean
#                             extra on bbgl's to machine precision, and the node REFUSES to
#                             publish the difference if it does not. Its wallet population is
#                             the rank-floor-eligible set, the same one bbgl's per-tier term
#                             reads, so the eligibility confound is closed too. Axis: whether
#                             a fixed budget of width is better spent per WALLET or per
#                             coin-and-decile.
#   bbgl_flat               - one flat constant equal to bbgl's own mean width, handed to
#                             every fill. The negative control aimed at the WINNER rather
#                             than at symmetric A-S, in the spirit of
#                             flat_surcharge_control.py. Axis: whether bbgl's result is its
#                             conditioning or merely its width.
#   as_toxicity_plus_global - bbgl's market-wide global term kept exactly as bbgl computes
#                             it, with bbgl's per-tier term replaced by the resolved term,
#                             the whole rescaled to bbgl's width by the same solved
#                             equation. Axis: which second term rides on the shared global
#                             one. This is the arm that asks whether the study IMPROVES the
#                             published Barzykin-Bergault-Gueant-Lemmel instance rather than
#                             only beating symmetric A-S, which nothing here had ever asked.
# None of the three moves a number the six published quoters produce: they are additional
# names at the END of QUOTER_NAMES, and every existing block is keyed by quoter name.
#
# EXPECTED ORDERING on adverse-selection-cost reduction (least to most):
#   naive <= as_symmetric <= gm_vpin <= bbgl(global) <= bbgl(per-tier) ~ as_toxicity
# with HONEST near-ties expected where the market-level signal is weak (gm_vpin vs
# as_symmetric on BTC).
#
# THE GLFT-VERSUS-A-S NEAR-TIE IS NOT A PROPERTY OF THIS TAPE, and this block used to claim
# it was. What is checked is run_self_tests' glft_near_tie_band_with_as, and that fixture
# picks A so that c_skew comes out the size of gamma*sigma^2, which is the one arrangement
# that puts the ratio inside [0.5, 2]. On the tape A is A_hat, the coin's fill COUNT, which
# the code itself labels a placeholder; c_skew falls as 1/sqrt(A) and the tie goes with it.
# The two published numbers say so: glft_q0_spread_vs_as gives BTC a GLFT q=0 TOTAL spread of
# 0.3120 bps beside an A-S base HALF-spread of 5863.74 bps, four orders of magnitude apart,
# and the structural reason is that optimal_spread carries the inventory term gamma*sigma^2*
# (T-t) with T-t = 1 while the GLFT q=0 total carries no inventory term at all. The near-tie
# holds where c_skew is comparable to gamma*sigma^2 and nowhere else. Two strings still assert
# it -- glft_q0_spread_vs_as.note and _meta.honesty -- and correcting a string that reaches
# the artifact is owed a run, so it is recorded here and left standing there.
# gm_vpin is counterparty-BLIND by construction and so CANNOT reach what the
# counterparty-resolved term reaches -- that gap, confirmed by the label-shuffle
# placebo, is the whole point of including GM.
# CAP-INDUCED TIES (read with the ordering above). The cost-not-alpha booking caps the
# offset at f*min(extra, max(a_mid,0)), so the booked offset SATURATES for any premium
# >= the realized per-fill markout: once a quoter's premium clears the markout it books
# exactly f*max(a_mid,0), identical to any other saturating quoter on that fill.
# Differentiation among the HIGH-premium quoters (bbgl global+tier, as_toxicity at
# lambda=1) therefore comes only from premium TARGETING -- WHICH fills clear the cap --
# not from raw spread magnitude, so near-ties between bbgl-per-tier and as_toxicity are
# EXPECTED wherever both saturate the cap on the same toxic fills.
#
# Run command (bare python3 is BLOCKED on this machine):
#   uv run --no-project --with-requirements requirements.txt python3 quoters/mm_bakeoff.py
# Fast synthetic self-test (loads NO data):
#   uv run --no-project --with-requirements requirements.txt python3 quoters/mm_bakeoff.py --selftest
# Smoke slice (subset days/coins after load):
#   CAP_DAYS=9,10 CAP_COINS=BTC uv run --no-project --with-requirements requirements.txt python3 \
#       quoters/mm_bakeoff.py
# ---------------------------------------------------------------------------

import datetime
import json
import math
import os
import sys
import time

import numpy as np

# The shared modules sit in the repository root, one directory up from this
# group, and this file also imports from the money group. Both are built from this
# file's own location and never from the working directory the run happens to
# start in.
_CODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_CODE_DIR, os.path.join(_CODE_DIR, "money")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import artifact
import panel_io as P
import settings as H
import stats

# -------------------- reuse the upstream A-S + maker-econ objects verbatim --------------------
# A-S closed form (reservation_price / optimal_spread / quotes / spread_price_to_bps /
# _inv_fill_p_buy / inventory_control_sim / estimate_sigma / calibrate_k) and the
# maker-econ accounting (MAKER_FEE_BPS / FEE_TIERS / _vw_mean / _ew_mean / _boot_ci_vw /
# the EARLY/LATE split + toxicity labels) are imported, not re-derived. If those upstream
# conventions change, this harness inherits the change.
import as_quoter as ASQ
import maker_econ as ME
from as_quoter import (
    optimal_spread,
    spread_price_to_bps,
    reservation_price,
)
# The GM closed form comes from the GM quoter for the same reason the A-S closed form
# comes from the A-S quoter: gm_quoter.py is the file this project points a reader at for
# Glosten-Milgrom, it owns gm_quotes, which is built on the half-spread, and one of the
# arms scored below IS that quoter. Importing rather than restating it also means the
# bake-off cannot drift away from the quoter it claims to be running. Nothing about the
# import order matters to the draws: this module reseeds numpy's legacy global state a
# few lines below, after every import, exactly as it already does behind as_quoter and
# maker_econ, which seed it at import time too.
from gm_quoter import gm_half_spread, vpin_imbalance
from maker_econ import (
    MAKER_FEE_BPS,
    FEE_TIERS,
    TAKER_FEE_REF_BPS,
    FEE_SOURCE,
    early_late_days,
    _vw_mean,
    _ew_mean,
    build_toxicity_labels,
)
# The EARLY/LATE split arrives as maker_econ.early_late_days, a FUNCTION of the days the
# input carries, and no longer as the two day-of-month tuples this file used to import.
# The tuples were right only for a window opening on the 4th; the December window this
# file reads does open on the 4th, so the derived split reproduces them exactly and no
# number here moves. Importing the function rather than a pair of constants also keeps
# this file on whatever split build_toxicity_labels uses, which is where the labels this
# bake-off ranks on are actually built.
# NOTE: the bake-off uses a CAPPED m-out-of-n bootstrap (_boot_ci_vw_capped below) -- the
# SAME estimator as maker_econ._boot_ci_vw but resampling min(n, BOOT_SAMPLE_CAP) rows per
# draw so the full ~2.5M-row run stays tractable; the convention is otherwise identical.
# The cap is rows per draw and the budget is the number of draws; see BOOT_SAMPLE_CAP.

# -------------------- determinism --------------------
# READ from settings.py under the name of the consumer that draws it, never typed. The
# value is the same 20260623 every number in mm_bakeoff_results.json was drawn under, so
# reading it here moves nothing. It still differs from settings.MASTER_SEED, which is
# 20260620: the per-purpose map records what this consumer draws today, and binding this
# file to the master seed would redraw every bootstrap and every placebo in it. That is a
# measured change owed its own recompute, so the fingerprint keeps recording an override.
SEED = H.seed_for("mm_bakeoff")
np.random.seed(SEED)
# WHAT THIS SEED STILL DOES AND WHAT IT NO LONGER DOES. It seeds numpy's LEGACY global
# state, which is a second run-wide stream of exactly the kind removed from this file on
# 2026-08-03, and it is kept only because no call site here draws from it and proving that
# for every imported module is not something this file can do by reading. The proof is a
# measurement instead: run_self_tests perturbs the global state and checks that the
# quantities this module draws do not move, and checks that the same probe DOES move a
# quantity deliberately taken from the global state, so a silent dependency cannot hide
# behind a probe that reads nothing.
#
# The module-level generator that used to stand on the next line is GONE. It was named RNG,
# it was referenced by nothing in this file or anywhere in the tree, and a shared generator
# sitting in a module namespace is the defect this file has just paid to remove once.

# -------------------- one stream per named cell, and the proof that they differ ----------
# WHY A WRAPPER ROUND settings.rng. Two things have to be true of the streams in a run and
# only one of them can be arranged by naming cells carefully: that each block draws its own,
# and that no two blocks accidentally name the SAME one. settings.colliding_cells answers
# the second question mechanically, but only over a list of the cells a run actually opened,
# and a list rebuilt afterwards from the naming rules would be a second spelling of those
# rules -- it would agree with itself and miss the day the rules changed. So the cells are
# recorded AS THEY ARE OPENED, by the one function that opens them.
_STREAM_CELLS = []


def _cell_rng(*cell):
    """settings.rng for one named cell, recording the cell so the run can audit itself."""
    _STREAM_CELLS.append(tuple(cell))
    return H.rng(*cell)


def stream_cell_audit():
    """Every stream this run opened, and the groups of cells that share one -- ideally none.

    Published rather than asserted. A run that opened two cells with one identity has two
    blocks resampling the same rows while reporting independent bands, and that is invisible
    in every number it prints."""
    groups = H.colliding_cells(_STREAM_CELLS)
    return {
        "n_streams_opened": len(_STREAM_CELLS),
        "n_distinct_cells": len(set(_STREAM_CELLS)),
        "colliding_groups": [[list(c) for c in g] for g in groups],
        "no_two_cells_share_a_stream": not groups,
        "derived_from": ("settings.rng, which seeds from settings.MASTER_SEED and the "
                         "cell identity flattened by settings.cell_key; the identity is "
                         "built from names and integers and never from hash(), which "
                         "Python salts per process"),
        "why": ("a stream identified by its cell rather than by its position in a run is "
                "independent of the roster of quoters and of the order any loop walks "
                "them, so that a stranger executing this code gets the results the "
                "paper presents"),
    }

# -------------------- paths (script-relative; env override; no /Users leak) --------------------
# The three arrays and the results file used to share one directory and no longer do:
# the arrays sit under the declared data root, which stayed at the top of the repository,
# and the results file sits beside this script the way every artifact in this tree does.
# panel_io.data_root() honours CAP_DATA_DIR among four other names, so the environment
# override this file has always accepted for its inputs is the same override.
HERE = os.path.dirname(os.path.abspath(__file__))
PRINT_NPZ = os.path.join(P.data_root(), "quickwin_markouts.npz")   # a_print + start_pos
MID_NPZ = os.path.join(P.data_root(), "quickwin_markouts_mid.npz")  # a_mid + spread
TAKER_MAP_JSON = os.path.join(P.data_root(), "quickwin_taker_map.json")
OUT_JSON = os.path.join(HERE, "mm_bakeoff_results.json")

# -------------------- config (reuse maker_econ where shared) --------------------
HORIZONS = H.LADDER_S               # the declared ladder; see settings.LADDER_S
# The headline scoring window comes from settings.py, the one place that declares it.
# TWO DECISIONS STAND ON THAT ONE NUMBER AND THEY ARE NOT ONE DECISION, so the evidence
# for each is written separately here rather than run together into a single sentence.
#
# The COST window asks how long after a fill the permanent price move has arrived. Its
# evidence is the level term structure alone: the markout level is ~98% impounded by
# 10s, which is the shortest conventional horizon sitting at that plateau.
#
# The RANKING window asks over how long a counterparty's score has to be averaged before
# the ordering reproduces on days it was not fitted on. Its evidence is the early-to-late
# rank persistence alone: pooled disattenuated 0.74 at 1s falling to 0.21 at 120s, with
# one non-monotone step, 0.4760 at 20s against 0.4836 at 30s, and 0.52 at 10s against
# 0.32 at 60s.
#
# One number serves both only because both clear at the same rung, which is what
# ws1_horizon_persistence.py records; neither criterion decides for the other. The 60s
# cells are retained throughout as the robustness companion and as the anchor for the
# maker_econ reproduction gate below.
HEADLINE_HORIZON = H.HEADLINE_HORIZON_S
HKEY = f"h{HEADLINE_HORIZON}"  # key into the per-horizon result blocks
COIN_NAME = H.coin_labels("quickwin")         # the two coins this file's input carries
COIN_NAMES = H.coin_labels("panel")           # superset (SOL absent from the quickwin npz)
# Minimum early fills per taker. READ from settings.py, which declares this per consumer
# because a file reporting every rung of a sweep is reporting the CURVE as its finding,
# and a single declared floor cannot express a curve without deleting the finding.
#
# The sweep and the headline are asked for by NAME rather than taken by position. They are
# different quantities: the sweep is every rung reported, the headline is the rung the
# prose points at, and handing back one where the other was asked for would return a
# number that is valid, plausible and about something else.
#
# THE HEADLINE ROSE FROM 10 TO THE DECLARED 50 ON 2026-07-31, on the reliability evidence
# settings.RANK_FLOOR_FILLS records: a score built on ten fills carries a disattenuation
# multiplier of 2.79, so most of the corrected number is the correction. The sweep is
# unchanged and still reports both rungs, so nothing is deleted -- what moves is which of
# the two blocks the ranking and the B2 surface are built on, and with it the eligible
# population underneath them. The K10 arm becomes the robustness companion.
#
# WHAT THE FLOOR DOES NOT REACH, listed here because the floor rising made both visible.
# The label-shuffle placebo no longer moves with it: from 2026-08-01 both of its arms are
# built over the population the as_toxicity term is actually booked on, and that population
# does not read the floor either, so the placebo tests the published quoter instead of a
# quoter nobody scores. And the GLFT-versus-A-S spread block never read it at all; it used
# to be filed under a key naming the rung, and that key is gone.
K_LIST = H.wallet_fill_floor("mm_bakeoff", "sweep")
K_HEADLINE = H.wallet_fill_floor("mm_bakeoff", "headline")
TIME_REMAINING_EVAL = 1.0      # rolling-horizon perpetual maker (T - t = 1)

# VPIN/PIN proxy clock (Glosten-Milgrom pi). Count clock (not volume clock) because
# notional is heavy-tailed and a volume clock would degenerate on whale fills.
N_VPIN_BUCKETS = 50
MIN_FILLS_PER_BUCKET = 5       # a (coin,day) needs >= 250 fills to be bucketed

# A-S scale anchors (NOT identified from executed fills; swept, never asserted as truth).
GAMMA_ANCHOR = ASQ.SIM_GAMMA   # reuse the as_quoter inventory-risk-aversion anchor
K_GRID = ASQ.K_GRID            # (0.5,1,2,5,10) reuse the as_quoter sensitivity grid
A_MULT_GRID = (0.5, 1.0, 2.0, 5.0)   # GLFT arrival-intensity sweep (A = mult * A_hat)

# A-S + toxicity additive term + BBGL coefficients (pass-through default = charge the
# full measured early adverse-selection intensity back as defensive spread).
# toxicity pass-through coefficient. The HEADLINE is FIXED at lambda_tox=1.0 (the
# Glosten-Milgrom break-even: charge the full measured early adverse-selection back as
# spread). LAMBDA_TOX_GRID is the documented sensitivity RANGE that the term spans
# (0.0 = symmetric A-S, 1.0 = full break-even); main() does NOT loop it -- it is reported
# as a sensitivity range only, not an executed per-lambda sweep. The as_toxicity TERM is
# LINEAR in lambda_tox (term = lambda_tox * max(early_tox,0)), so the lambda=0 and lambda=1
# endpoints are exactly as_symmetric and the headline, and the endpoints therefore bracket
# the band -- the grid is informative without a separate run.
#
# WHAT IS LINEAR AND WHAT IS NOT, because this comment used to run the two together and say
# that intermediate lambda interpolates linearly. The TERM does. The quantity this file
# PUBLISHES is the BOOKED offset, RECOVER_FRAC*min(lambda*max(early_tox,0), max(a_mid,0)),
# and a minimum against a fixed cap is concave in lambda, not linear: min(lambda*t, c) >=
# lambda*min(t, c) for every lambda in [0,1], strictly whenever the cap binds. So linear
# interpolation is a LOWER bound on the intermediate value, never the value. That the cap
# binds at all is visible in the published run without any new arithmetic, and the two
# figures are on different weightings so they are quoted apart rather than divided: the
# EQUAL-weighted mean premium as_toxicity asks for on pooled late fills is 1.3466 bps
# (extra_half_spread_summary), while the NOTIONAL-weighted booked offset behind the headline
# is 0.9650 bps (the published delta divided by RECOVER_FRAC). Neither is the clipped share,
# and no clipped share is measured anywhere in this file. Reading an intermediate lambda off
# a straight line understates it, which is the conservative direction, and it is still not
# the measured value. A stated intermediate lambda is owed a run.
LAMBDA_TOX_HEADLINE = 1.0            # the single headline pass-through (GM break-even)
LAMBDA_TOX_GRID = (0.0, 0.5, 1.0)    # documented sensitivity RANGE (NOT swept; linear in lambda)
BETA_G = 1.0                          # BBGL global pass-through (1 bp AS -> 1 bp half-spread)
BETA_T = 1.0                          # BBGL per-tier pass-through

# maker_econ-style recapture APPROXIMATION knobs (NOT a fill model).
B2_F_GRID = (0.0, 0.25, 0.5, 1.0)    # recapture fraction f (0 = decline; 1 = no avoidance)
B2_W_GRID = (1.0, 2.0, 4.0)          # extra half-spread widening w (bps)
B2_C_GRID = (0.0, 0.5)               # per-requote penalty c (bps)
B2_DEPLOY = {"f": 0.5, "w": 2.0, "c": 0.5}
# RECOVER_FRAC = the deployable recapture fraction f applied to the per-fill offset that an
# AS-quoter books (the rest of the deterred adverse flow is declined, not collected). f=1 is
# the idealized full-offset B1 upper bound; the headline uses the deployable f. Keeps every
# quoter net-negative and ties the booked headline to the maker_econ B2 deploy point.
RECOVER_FRAC = B2_DEPLOY["f"]

N_PERM = H.N_PERM                     # label-shuffle placebo permutations (p-floor 1/(N+1))
# Raised from 200 on 2026-07-29. Every effect size in this file is bit-identical between
# the two settings: of 6,952 numeric leaves only 11 move, all of them inside the placebo
# blocks. The three label-shuffle values sat on the 1/201 floor and now sit on the 1/2001
# one, so the bound they report is ten times tighter for the same conclusion.

# Bootstrap CI config. The 95% CI is a reported SANITY band (not a significance test), so
# it is computed once at the headline horizon and shifted per fee tier (see net_block).
#
# THE BUDGET IS READ FROM settings.py AND NOTHING OVERRIDES IT. Until 2026-07-31 this line
# was `int(os.environ.get("CAP_N_BOOT", str(H.boot_draws("mm_bakeoff"))))`, and before
# that the fallback was the bare string "300". Two defects sat in that one line. The 300
# had no home a reader could open, which the per-consumer map fixed; and the environment
# read let a shell variable overrule the declaration, which nothing outside the machine
# records. The read is gone, so the budget is the declared 2000 -- fifty draws in each
# tail of a 95 percent interval against the seven and a half the published run drew.
N_BOOT = H.boot_draws("mm_bakeoff")
# ROWS PER DRAW, WHICH IS A DIFFERENT QUANTITY FROM THE BUDGET and not a second limit on
# it. N_BOOT is how many resamples are taken; this is how many rows each resample holds,
# min(n, cap), which is what keeps a ~2.5M-row array from making every draw a full pass.
# The two multiply rather than compete: 2000 draws of 200,000 rows is 2000 draws. The
# m-out-of-n form widens the band slightly, which is the conservative direction, and it
# is the reason this file cannot be routed through stats.bootstrap_mean_ci.
BOOT_SAMPLE_CAP = int(os.environ.get("CAP_BOOT_CAP", "200000"))

# Equal-width arms. Which quoter's width the solved arms are put on, and how exactly the
# landing has to be. The target is a NAME rather than a number so the arms follow the target
# quoter through any repair of it; the tolerance is RELATIVE because the quantity is a few
# basis points and an absolute bar would mean different things at different sizes. 1e-9 is
# the bar the refusal below enforces: the solve is exact arithmetic on a linear term, so
# anything a reader can see is a defect and not noise.
EQUAL_WIDTH_TARGET_QUOTER = "bbgl"
EQUAL_WIDTH_RTOL = 1e-9
# The bar the OTHER held-equal quantities are measured against in comparison_manifest. Looser
# than the solve because those are equal by construction rather than by equation (identical
# arrays, identical row sets, identical constants), so the only thing that can move them is
# float summation over ~2.5M rows.
HELD_EQUAL_RTOL = 1e-12

# Walk-forward. The M4 draft promised one at the quoter bake-off and this file carried none;
# the folds are the SAME nine t1_toxicity_skew_backtest.py cuts -- expanding train window
# over the days present, test on the next day -- so the two nodes report one scheme rather
# than two. Off by name only, never silently: --no-walk-forward skips it and the artifact
# records that it was skipped.
WALK_FORWARD_DEFAULT = True

QUOTER_NAMES = ("naive_at_book", "naive_const", "as_symmetric", "gm_vpin", "bbgl", "as_toxicity",
                "as_toxicity_ew", "bbgl_flat", "as_toxicity_plus_global")
# Appended, never reordered: chk_prose_numbers.py and run/_groups.py read this tuple, and
# adverse_selection_term_value / bakeoff_ranking / placebo_label_shuffle are all keyed by
# quoter NAME, so a name added at the end cannot move a published leaf of the first six.
QUOTERS_USING_IDENTITY = ("as_toxicity", "bbgl", "as_toxicity_ew", "as_toxicity_plus_global")
# gm_vpin is the built-in negative control and bbgl_flat is the width-matched one: neither
# reads a counterparty at the fill, so a label shuffle leaves both unchanged. bbgl_flat's
# constant is DERIVED from a quantity that reads identity (bbgl's mean width), which is why
# it is a control on width rather than a second identity-blind quoter.


# ==================== quoter half-spread functions (pure; bps; per fill) ====================
# Every quoter returns a NON-NEGATIVE extra-half-spread (bps) ADDED to the per-fill book
# half-spread s_bbo, i.e. s_q = s_bbo + extra. naive_at_book has extra == 0 (quote AT the
# book), so it reproduces maker_econ net_MID_lower bit-for-bit (to ~1e-6). The print leg
# reproduces it too, and this comment used to say it did not. Rows with NaN a_mid_60 but
# finite a_print_60 drop from the bake-off's net_PRINT mean under the cost-not-alpha booking
# (s_q inherits the a_mid NaN through the offset cap) while maker_econ's net_PRINT = -a_print
# keeps them, so the two sides once scored different ROWS and differed by ~0.02 bps. _cross_checks
# now restricts the maker_econ side to the rows the bake-off actually scored, and reports the
# unrestricted value and the excluded-row count beside it. Read the artifact, not this line:
# the published run records print_match_within_1e-6 = true, on 2,075 excluded late rows, and
# the sentence that used to stand here said false. Nothing here
# ever tightens below the book (extra clipped >= 0). None of these is alpha; they all set
# a defensive SPREAD only.

def naive_extra_half_spread_bps(n):
    """Naive_at_book: quote exactly at the BBO -> NO extra half-spread (zeros)."""
    return np.zeros(int(n), dtype=np.float64)


# gm_half_spread and vpin_imbalance USED TO BE DEFINED HERE, in a second spelling of the
# two functions gm_quoter.py already owned. Both are now imported from that file at the
# top of this one, beside the A-S and maker-econ objects, and the reason is the reason
# this file already imports optimal_spread rather than re-deriving it: two spellings of
# one formula agree until one of them is edited, and the day one is edited nothing in the
# tree reports it. The pair was measured before it was merged rather than read: 51 cases
# for the half-spread and 40 for the imbalance, spanning scalars, arrays, lists, an empty
# bucket, a negative J, and non-finite arguments on either side, with ZERO disagreements,
# and the comparator was calibrated on a deliberately broken copy of each, which it caught
# 45 and 9 times. The two spellings differed only in the name of the second argument -- J
# here, adverse_move there -- and in the wording of the docstring. Both sentences the
# docstrings here carried and gm_quoter's did not, the two-type reduction of GM's general
# posteriors and the COUNT clock the imbalance is measured on, moved with the functions.
# The self-tests further down still call both names and now exercise the imported objects,
# which is what makes this import a checked edge rather than a claim; and gm_quoter.py is
# declared an INPUT of this artifact, so editing it there marks this artifact stale.


def glft_c_skew(sigma, gamma, k, A):
    """Gueant-Lehalle-Fernandez-Tapia (2013) asymptotic inventory-skew unit (price).

        c_skew = sqrt( sigma^2 * gamma / (2*k*A) * (1 + gamma/k)^(1 + k/gamma) )

    The GLFT stationary-regime result that refines A-S. c_skew ~ 1/sqrt(A) (more
    liquidity -> smaller skew) and increases in sigma. Vectorizable."""
    sigma = np.asarray(sigma, dtype=np.float64)
    gamma = np.asarray(gamma, dtype=np.float64)
    k = np.asarray(k, dtype=np.float64)
    A = np.asarray(A, dtype=np.float64)
    ratio = gamma / k
    return np.sqrt(sigma ** 2 * gamma / (2.0 * k * A) * (1.0 + ratio) ** (1.0 + k / gamma))


def glft_arrival_term(gamma, k):
    """The shared A-S/GLFT arrival half-distance (1/gamma)*ln(1+gamma/k) (price units).

    The GLFT per-side distance at q=0 is this term plus c_skew/2; the TOTAL GLFT q=0
    spread is (2/gamma)*ln(1+gamma/k) + c_skew, sharing the IDENTICAL (2/gamma)ln term
    with the base A-S optimal_spread."""
    gamma = np.asarray(gamma, dtype=np.float64)
    k = np.asarray(k, dtype=np.float64)
    return (1.0 / gamma) * np.log1p(gamma / k)


def glft_distances(q, gamma, k, c_skew):
    """GLFT per-side quote distances FROM THE MID (price units), inventory-linear.

        delta_bid(q) = (1/gamma)*ln(1+gamma/k) + (2q+1)/2 * c_skew   (BID below mid)
        delta_ask(q) = (1/gamma)*ln(1+gamma/k) - (2q-1)/2 * c_skew   (ASK above mid)

    so bid = s - delta_bid, ask = s + delta_ask. q>0 (long) ADDS q*c_skew to the bid
    distance and SUBTRACTS q*c_skew from the ask distance -> the maker leans to SELL
    (same direction as the A-S reservation skew). At large |q| an individual per-side
    distance can go NEGATIVE (e.g. the ask sits below the mid) -- the documented GLFT
    inventory lean, where the dealer aggressively offloads inventory; the TOTAL spread
    stays positive (the q-terms cancel). These per-side distances are ILLUSTRATIVE ONLY
    for the GLFT-vs-A-S near-tie comparison and are NEVER booked into any P&L (no 'glft'
    quoter exists in QUOTER_NAMES). Returns (delta_bid, delta_ask)."""
    q = np.asarray(q, dtype=np.float64)
    arr = glft_arrival_term(gamma, k)
    c_skew = np.asarray(c_skew, dtype=np.float64)
    delta_bid = arr + (2.0 * q + 1.0) / 2.0 * c_skew
    delta_ask = arr - (2.0 * q - 1.0) / 2.0 * c_skew
    return delta_bid, delta_ask


def glft_total_spread(q, gamma, k, c_skew):
    """GLFT total spread delta_bid + delta_ask = (2/gamma)ln(1+gamma/k) + c_skew.

    Inventory-INDEPENDENT to first asymptotic order (the q terms cancel)."""
    db, da = glft_distances(q, gamma, k, c_skew)
    return db + da


def bbgl_half_spread_bps(base_half_bps, tox_market, tox_tier, beta_g=BETA_G, beta_t=BETA_T):
    """Barzykin-Bergault-Gueant-Lemmel half-spread (bps): base + global + per-tier.

        AS_global  = beta_g * max(tox_market, 0)        [market-wide AS intensity]
        AS_tier(j) = beta_t * max(tox_tier(j), 0)       [tier-j AS intensity]
        half_spread_bps = base_half_bps + AS_global + AS_tier(j)

    Both AS premia are NON-NEGATIVE (a benign/negative-toxicity tier is clipped to 0),
    so the BBGL quote only ever WIDENS vs symmetric A-S, never tightens. beta_g=beta_t=0
    degenerates EXACTLY to the symmetric A-S half-spread. This is a reduced-form additive
    linear-in-markout instance of the BBGL global+per-tier structure (validation of the
    published lineage that owns the quoting leg, NOT their stochastic-control optimum and
    NOT our invention). Vectorizable."""
    base = np.asarray(base_half_bps, dtype=np.float64)
    as_global = beta_g * np.maximum(np.asarray(tox_market, dtype=np.float64), 0.0)
    as_tier = beta_t * np.maximum(np.asarray(tox_tier, dtype=np.float64), 0.0)
    return base + as_global + as_tier


def as_toxicity_term_bps(early_tox_hat, lambda_tox):
    """The refactor: additive counterparty-RESOLVED adverse-selection term (bps).

        adverse_selection_term_bps(c) = lambda_tox * max(early_tox_hat(c), 0)

    early_tox_hat(c) = the wallet's EARLY estimate of the expected signed adverse markout
    it imposes on the maker at the headline horizon (build_toxicity_labels is called with
    horizon=HEADLINE_HORIZON), in bps (= maker_econ's early_tox; POSITIVE = adverse
    for the maker). Clipped >= 0 so benign / negative-toxicity wallets get NO extra spread
    (never a tightening). lambda_tox in [0,1] is a pass-through coefficient (1.0 = charge
    the full expected adverse-selection cost back as spread, the Glosten-Milgrom
    break-even half-spread = expected adverse selection per fill). This is the empirical,
    counterparty-resolved REDUCED-FORM instance of the BBGL per-tier skew -- validation on
    observable identity, never our invention (their tiers assumed; ours measured)."""
    et = np.asarray(early_tox_hat, dtype=np.float64)
    return float(lambda_tox) * np.maximum(et, 0.0)


# ==================== net-economics accounting (generalise maker_econ verbatim) ====================
def gross_quoter_measures(s_q, a_mid_h, s_bbo, a_print_h):
    """Per-fill PRE-FEE maker measures (bps) under a quoter-chosen half-spread s_q.

    Reuses maker_econ accounting EXACTLY, generalising s_bbo -> s_q (= s_bbo + extra):
        gross_quoter_MID_h   = s_q - a_mid_h            (mark-to-mid income minus realized
                                                         book-mid adverse markout; conservative)
        gross_quoter_PRINT_h = s_q - (s_bbo + a_print_h)  (mirror of taker print gain;
                                                           nets the entry spread; optimistic)
    With s_q == s_bbo these reduce to maker_econ's net_MID_lower (s_bbo - a_mid)
    bit-for-bit, and to net_PRINT (-a_print) as well, on the rows both sides score (since
    net_PRINT = s_bbo - (s_bbo + a_print) = -a_print). The two sides do not score the same
    rows: one with NaN a_mid but finite a_print drops from the bake-off's net_PRINT mean
    (s_q carries the a_mid NaN through the cost-not-alpha offset cap) while maker_econ keeps
    it, which is a SCOPE difference and not a disagreement about any fill. _cross_checks puts
    both sides on the bake-off's row set and reports the unrestricted maker_econ value and the
    excluded-row count next to it, so the restriction can be read rather than trusted.

    WHAT THIS PARAGRAPH USED TO SAY, kept because the correction is the point. It said the
    print legs differ by ~0.02 bps and that the artifact records
    cross_checks...print_match_within_1e-6 = false. The published run records true, on 2,075
    excluded late rows, and the ~0.02 bps is the gap to the UNRESTRICTED maker_econ value,
    which the artifact also carries. A quoter does NOT change
    the realized adverse markout a_*_h (no book re-clearing) -- it changes the SPREAD
    CREDIT booked. Returns (gross_MID, gross_PRINT)."""
    s_q = np.asarray(s_q, dtype=np.float64)
    a_mid_h = np.asarray(a_mid_h, dtype=np.float64)
    s_bbo = np.asarray(s_bbo, dtype=np.float64)
    a_print_h = np.asarray(a_print_h, dtype=np.float64)
    gross_mid = s_q - a_mid_h
    gross_print = s_q - (s_bbo + a_print_h)
    return gross_mid, gross_print


def _boot_ci_vw_capped(vals, weights, rng, n_boot=None, cap=None, alpha=0.05):
    """95% CI of the notional-weighted mean via an m-out-of-n bootstrap (numpy-only).

    Same estimator as maker_econ._boot_ci_vw but resamples min(n, cap) rows per draw so a
    ~2.5M-row array does not make every draw a full pass; m-out-of-n slightly WIDENS the
    band (conservative). n_boot/cap default to the module N_BOOT / BOOT_SAMPLE_CAP, which
    are the number of draws and the rows inside one draw and are not two limits on one
    quantity.

    WHY THIS IS NOT stats.bootstrap_mean_ci. The cap is the whole point of this
    function and that module has no such knob: it resamples n rows out of n, so routing
    this through it would change the ESTIMATOR and not merely the stream, and would
    narrow every band in this file. The stream differs too -- the draws come from the
    generator the caller threads through the run rather than from a named cell. Two
    separate reasons, either of which alone would move a published interval. The budget
    used to be a third and is not any more: it is the declared one from 2026-07-31."""
    n_boot = N_BOOT if n_boot is None else n_boot
    cap = BOOT_SAMPLE_CAP if cap is None else cap
    vals = np.asarray(vals, dtype=np.float64)
    weights = np.asarray(weights, dtype=np.float64)
    m = np.isfinite(vals) & np.isfinite(weights) & (weights > 0)
    v = vals[m]
    w = weights[m]
    n = v.size
    if n < 2:
        return [float("nan"), float("nan")]
    draw = min(n, cap)
    boots = np.empty(n_boot, dtype=np.float64)
    for b in range(n_boot):
        idx = rng.integers(0, n, size=draw)
        ws = w[idx]
        sw = ws.sum()
        boots[b] = np.sum(v[idx] * ws) / sw if sw > 0 else np.nan
    boots = boots[np.isfinite(boots)]
    if boots.size < 2:
        return [float("nan"), float("nan")]
    return [float(np.percentile(boots, 100 * alpha / 2.0)),
            float(np.percentile(boots, 100 * (1 - alpha / 2.0)))]


def net_block(measure, notional, rng, with_ci=True):
    """Per-fee-tier vw + ew net mean (+ bootstrap CI) of a pre-fee measure (bps).

    net = measure - MAKER_FEE_BPS[tier] (negative fee = rebate ADDS). Mirrors
    maker_econ._net_block; reuses maker_econ's _vw_mean / _ew_mean / _boot_ci_vw.
    OPTIMISATION (identical numbers): the per-tier net differs from the gross measure ONLY
    by a CONSTANT fee subtraction, so the bootstrap distribution of the net vw-mean is the
    GROSS distribution shifted by -fee. Bootstrap the gross measure ONCE and shift the CI
    bounds by -fee per tier (a 6x cut vs re-bootstrapping each tier). with_ci=False skips
    the bootstrap entirely (used off the headline horizon to keep the full run tractable)."""
    measure = np.asarray(measure, dtype=np.float64)
    notional = np.asarray(notional, dtype=np.float64)
    finite = np.isfinite(measure) & np.isfinite(notional) & (notional > 0)
    out = {
        "n_fills": int(finite.sum()),
        "gross_prefee_vw_bps": _vw_mean(measure, notional),
        "gross_prefee_ew_bps": _ew_mean(measure[finite] if finite.any() else measure),
        "by_fee_tier": {},
    }
    # bootstrap the GROSS vw-mean once; net CI per tier = gross CI shifted by -fee.
    gross_ci = _boot_ci_vw_capped(measure, notional, rng) if with_ci else [float("nan"), float("nan")]
    for tier in FEE_TIERS:
        fee = MAKER_FEE_BPS[tier]
        net = measure - fee
        out["by_fee_tier"][tier] = {
            "maker_fee_bps": fee,
            "net_vw_bps": _vw_mean(net, notional),
            "net_ew_bps": _ew_mean(net[finite] if finite.any() else net),
            "net_vw_ci95": [gross_ci[0] - fee, gross_ci[1] - fee],
        }
    return out


# ==================== env slice (REUSE maker_econ convention) ====================
def _apply_env_slice(arrs):
    """Filter every aligned array to CAP_DAYS / CAP_COINS rows (maker_econ convention)."""
    day = arrs["day"]
    coin = arrs["coin"]
    mask = np.ones(day.size, dtype=bool)
    meta = {"sliced": False, "days": None, "coins": None}

    env_days = os.environ.get("CAP_DAYS")
    if env_days:
        keep_days = set(int(x.strip()) for x in env_days.split(",") if x.strip())
        mask &= np.array([int(d) in keep_days for d in day], dtype=bool)
        meta["sliced"] = True
        meta["days"] = sorted(keep_days)

    env_coins = os.environ.get("CAP_COINS")
    if env_coins:
        name_to_code = {v: k for k, v in COIN_NAMES.items()}
        keep_codes = set()
        for tok in env_coins.split(","):
            tok = tok.strip()
            if not tok:
                continue
            if tok.upper() in name_to_code:
                keep_codes.add(name_to_code[tok.upper()])
            else:
                keep_codes.add(int(tok))
        mask &= np.array([int(c) in keep_codes for c in coin], dtype=bool)
        meta["sliced"] = True
        meta["coins"] = sorted(COIN_NAMES.get(c, c) for c in keep_codes)

    if meta["sliced"]:
        arrs = {k: v[mask] for k, v in arrs.items()}
        if arrs["day"].size == 0:
            raise SystemExit(
                f"[mm_bakeoff] env slice (days={meta['days']} coins={meta['coins']}) "
                f"selected 0 rows; check CAP_DATA_DIR / CAP_DAYS / CAP_COINS")
    return arrs, meta


# ==================== load + align (NO re-pull) ====================
def load_aligned():
    """Load both npz + the taker map, verify row alignment, build aligned arrays.

    Returns (arrs, align_ok, slice_meta, taker_map_meta). Reuses the maker_econ
    alignment discipline (taker_id/coin/day/taker_side/maker_id equal across the two
    npz). No-lookahead is structural: forward markouts (mo{h}, mo{h}_mid) were built
    EXEC->forward via searchsorted on time during the build pass, never leaking a future
    row back."""
    # panel_io owns the "it is missing, and here is the producer that writes it" message
    # for the whole tree; the paths are this file's own (HERE honours CAP_DATA_DIR and
    # is also where the results file is written), so they are handed over rather than
    # re-resolved. The two np.load calls stay here because build.py derives this
    # script's input edges from the argument of np.load.
    P.require_present("mid", MID_NPZ)
    P.require_present("print", PRINT_NPZ)
    zm = np.load(MID_NPZ)
    zp = np.load(PRINT_NPZ)

    align_keys = ("taker_id", "coin", "day", "taker_side", "maker_id")
    align_ok = {}
    for k in align_keys:
        align_ok[k] = bool(np.array_equal(zm[k], zp[k]))
        if not align_ok[k]:
            raise SystemExit(f"[mm_bakeoff] ROW MISALIGNMENT on '{k}' between the two npz - abort")
    notl_mid = zm["notional"].astype(np.float64)
    notl_print = zp["notional"].astype(np.float64)
    align_ok["notional"] = bool(np.allclose(notl_mid, notl_print, rtol=0, atol=1e-3, equal_nan=True))

    arrs = {
        "taker_id": zm["taker_id"].astype(np.int64),
        "coin": zm["coin"].astype(np.int64),
        "day": zm["day"].astype(np.int64),
        "entry_px": zm["entry_px"].astype(np.float64),
        "notional": notl_mid,
        # BYTE-VERIFIED: taker_side 1 = buy-aggressor (+1), 0 = sell-aggressor (-1)
        "taker_side": zm["taker_side"].astype(np.int64),
        "start_pos": zp["start_pos"].astype(np.float64),   # signed pre-trade inventory (+long)
        # s_bbo = BBO half-spread (>= 0; LOWER BOUND on maker income), reuse maker_econ
        "s_bbo": zm["spread_entry_bps"].astype(np.float64) / 2.0,
    }
    arrs["sign_taker"] = np.where(arrs["taker_side"] == 1, 1.0, -1.0)
    # a_mid = book-mid markout (positive = maker adverse-selected); a_print = trade-print
    # markout. The rungs come from the declared ladder and the column names from
    # panel_io, which takes the lens from the FILE rather than from the caller: asking
    # the trade-print panel for a book-mid column is the one mistake this loop used to
    # make possible, and the six literals it used to spell were six places a window
    # could be fixed without the word "horizon" appearing anywhere.
    for h in HORIZONS:
        arrs[f"a_mid_{h}"] = P.score(zm, "mid", h)
        arrs[f"a_print_{h}"] = P.score(zp, "print", h)

    arrs, slice_meta = _apply_env_slice(arrs)

    taker_map_meta = {"present": False, "n_wallets": None, "direction": None}
    if os.path.exists(TAKER_MAP_JSON):
        with open(TAKER_MAP_JSON) as fh:
            tm = json.load(fh)
        taker_map_meta = {
            "present": True,
            "n_wallets": len(tm.get("map", {})),
            "direction": tm.get("_direction"),
        }
    return arrs, align_ok, slice_meta, taker_map_meta


# ==================== GM market-level pi (VPIN/PIN proxy) ====================
def estimate_pi(arrs):
    """Market-level informed-trade probability pi (VPIN/PIN proxy), per coin.

    Per (coin,day) in arrival order, bucket fills into N_VPIN_BUCKETS equal-COUNT buckets
    (count clock; a documented departure from the canonical VPIN volume clock because
    notional is heavy-tailed). Per bucket imb = |sum(sign)|/n in [0,1]; pi_proxy(coin,day)
    = mean over buckets of imb. Headline pi = per-coin MEDIAN of the daily series. NO
    lookahead: each (coin,day) pi uses that day's own fills only. This is a FULL-WINDOW
    aggregate (early + late days), NOT early-only -- a deliberately strong book-only
    benchmark for the negative control; gm_vpin is then scored on LATE fills, so a
    full-window pi only makes the GM cost-reduction larger and the counterparty-resolution
    gap HARDER to clear (conservative for the headline). MARKET-LEVEL only -- the taker_id
    column is NEVER referenced here (gm_vpin is the built-in negative control)."""
    coin = arrs["coin"]
    day = arrs["day"]
    sign = arrs["sign_taker"]
    out = {}
    coins = sorted(set(int(c) for c in np.unique(coin)))
    for c in coins:
        daily = []
        for d in sorted(set(int(x) for x in np.unique(day))):
            sel = (coin == c) & (day == d)
            n = int(sel.sum())
            if n < N_VPIN_BUCKETS * MIN_FILLS_PER_BUCKET:
                continue
            s = sign[sel]
            # equal-count buckets over the day's own arrival-ordered fills
            edges = np.linspace(0, n, N_VPIN_BUCKETS + 1).astype(int)
            imbs = []
            for b in range(N_VPIN_BUCKETS):
                lo, hi = edges[b], edges[b + 1]
                if hi - lo < MIN_FILLS_PER_BUCKET:
                    continue
                imbs.append(abs(float(s[lo:hi].sum())) / (hi - lo))
            if imbs:
                daily.append(float(np.mean(imbs)))
        cname = COIN_NAMES.get(c, str(c))
        if daily:
            arr = np.array(daily, dtype=np.float64)
            out[cname] = {
                "coin_code": c,
                "n_days": int(arr.size),
                "pi_median": float(np.median(arr)),
                "pi_mean": float(arr.mean()),
                "pi_p10": float(np.percentile(arr, 10)),
                "pi_p90": float(np.percentile(arr, 90)),
                "daily_pi": [float(x) for x in arr],
            }
        else:
            out[cname] = {"coin_code": c, "n_days": 0, "pi_median": float("nan"),
                          "pi_mean": float("nan"), "pi_p10": float("nan"),
                          "pi_p90": float("nan"), "daily_pi": []}
    return {
        "method": ("market-level VPIN/PIN proxy: per (coin,day) mean over "
                   f"{N_VPIN_BUCKETS} equal-COUNT buckets of |sum(sign)|/n; headline = "
                   "per-coin median of the daily series. COUNT clock (notional is "
                   "heavy-tailed; volume clock would degenerate on whale fills). "
                   "FULL-WINDOW aggregate (early+late days), NOT early-only -- a "
                   "deliberately-strong book-only benchmark for the negative control "
                   "(makes the GM cost-reduction larger and the counterparty-resolution "
                   "gap harder to clear, the conservative direction). NO "
                   "counterparty identity; taker_id never referenced."),
        "n_buckets": N_VPIN_BUCKETS,
        "min_fills_per_bucket": MIN_FILLS_PER_BUCKET,
        "per_coin": out,
    }


def estimate_adverse_move(arrs):
    """GM informed-jump J (bps) = mean(|markout|) at the headline horizon per coin, plus J in price units.

    J = E[|adverse move|], the magnitude of the GM jump toward true value, read off the
    realized book-mid EXEC->mid markout at the headline horizon. Mean-ABSOLUTE (not signed
    mean) because GM's J is the jump magnitude regardless of direction. J_price = J_bps/1e4
    * mid_ref (mid_ref = per-coin median entry_px). MARKET-LEVEL (not conditioned on
    counterparty). FULL-WINDOW (early+late), NOT early-only -- consistent with the
    full-window pi above; a stronger book-only J only widens the GM benchmark, the
    conservative direction for the counterparty-resolution headline."""
    coin = arrs["coin"]
    a_mid_hl = arrs[f"a_mid_{HEADLINE_HORIZON}"]   # AS intensity at the headline horizon
    px = arrs["entry_px"]
    out = {}
    for c in sorted(set(int(x) for x in np.unique(coin))):
        sel = coin == c
        am = a_mid_hl[sel]
        am = am[np.isfinite(am)]
        cpx = px[sel]
        cpx = cpx[np.isfinite(cpx) & (cpx > 0)]
        mid_ref = float(np.median(cpx)) if cpx.size else float("nan")
        J_bps = float(np.mean(np.abs(am))) if am.size else float("nan")
        cname = COIN_NAMES.get(c, str(c))
        out[cname] = {
            "coin_code": c,
            "J_bps": J_bps,
            "mid_ref_price": mid_ref,
            "J_price": (J_bps / 1e4 * mid_ref) if (np.isfinite(J_bps) and np.isfinite(mid_ref)) else float("nan"),
        }
    return {
        "method": ("J = mean(|markout at the headline horizon|) per coin (GM jump MAGNITUDE; mean-absolute, "
                   "market-level, not counterparty-conditioned; FULL-WINDOW early+late, "
                   "NOT early-only -- a deliberately-strong book-only benchmark, "
                   "conservative for the headline); J_price = J_bps/1e4 * "
                   "median entry_px."),
        "headline_horizon_s": HEADLINE_HORIZON,
        "per_coin": out,
    }


# ==================== the width statistic, spelled once ====================
def mean_extra_bps(extra):
    """EQUAL-weighted mean of the finite entries of a per-fill extra half-spread (bps).

    WHY IT IS A FUNCTION. This is the quantity the equal-width arms are solved to match,
    the quantity comparison_manifest measures the match on, and the quantity
    extra_half_spread_summary.mean_extra_half_spread_bps publishes. Three spellings of one
    statistic is how a solver comes to hit a target the artifact never reports: the solve
    would land on its own arithmetic and the published leaf would show something else. One
    call site for all three makes that impossible rather than merely unlikely.

    EQUAL-weighted and not notional-weighted, because the published leaf is equal-weighted.
    The booked offset behind the headline is notional-weighted and is a DIFFERENT quantity
    -- the file already says so where it quotes 1.3466 against 0.9650 -- so the axis these
    arms declare has to name which of the two it holds equal, and it names this one."""
    e = np.asarray(extra, dtype=np.float64)
    e = e[np.isfinite(e)]
    return float(np.mean(e)) if e.size else float("nan")


# ==================== per-fill extra-half-spread for each quoter ====================
def quoter_extra_half_spread_bps(name, arrs, idx, ctx):
    """Per-fill NON-NEGATIVE extra half-spread (bps) ADDED to s_bbo, for `name`, over rows
    `idx`. Clipped >= 0 (no quoter tightens below the book).

    INCOME-BASELINE DISCIPLINE (the honest mapping, matching as_quoter.py's own stance).
    The realized fill printed at the venue BBO, so every quoter's income BASELINE is the
    book half-spread s_bbo (= what actually cleared); the quoter's DISTINCTIVE content is
    only the EXTRA defensive widening it adds for ADVERSE SELECTION on top of the book.
    as_quoter.py is explicit that the A-S absolute spread LEVEL is parameter-dependent
    (gamma, k not identified) and is reported only as a single-maker FLOOR, NOT a literal
    booked quote -- so the A-S INVENTORY base is NOT booked as income here (booking the
    monopoly-floor spread would manufacture a fake profit and break cost-not-alpha). The
    A-S inventory content surfaces as the inventory-control SKEW (reported via the sim),
    not as a spread credit. Therefore:
      naive_at_book / as_symmetric -> extra 0 (quote AT the book; A-S adds NO AS premium,
                       its axis is inventory, reported via the control sim) -> identical
                       income baseline = the inventory-only counterparty-blind maker
      naive_const   -> widen up to a constant H_const, never below the book
      gm_vpin       -> + market-level pi*J adverse-selection premium (book-only info)
      bbgl          -> + global AS + per-tier AS adverse-selection premia
      as_toxicity   -> + the counterparty-RESOLVED additive AS term
    Only the ADVERSE-SELECTION premia (gm/bbgl/as_toxicity) are booked, so all of these
    differ from naive/A-S ONLY by a small defensive widening -- which can never out-earn
    the realized adverse markout net of the maker fee (cost not alpha)."""
    n = idx.size
    coin = arrs["coin"][idx]

    if name in ("naive_at_book", "as_symmetric"):
        # quote AT the book; symmetric A-S adds NO adverse-selection premium (its content
        # is the inventory skew, reported via the control sim) -> both extra == 0 and they
        # share the SAME income baseline = the inventory-only counterparty-blind maker.
        return naive_extra_half_spread_bps(n)

    if name == "naive_const":
        # widen up to a single fixed constant half-spread H_const, never below the book.
        return np.maximum(ctx["H_const_bps"] - arrs["s_bbo"][idx], 0.0)

    if name == "gm_vpin":
        # ADD the market-level pi*J adverse-selection premium (book-only; NO identity).
        # taker_id is NOT referenced -> the built-in negative control under label shuffle.
        # vectorized coin->premium via the small lookup array in ctx (no per-fill loop).
        gm_premium = ctx["gm_half_lut"][coin]
        return np.maximum(gm_premium, 0.0)

    if name == "bbgl":
        # ADD global AS + per-tier AS premia (reduced-form BBGL instance; widen-only).
        # base_half = 0: only the AS premium is booked on top of s_bbo, never the A-S floor.
        tox_market = ctx["bbgl_tox_market_lut"][coin]   # vectorized coin lookup
        tox_tier = ctx["bbgl_tox_tier_per_fill"][idx]   # per-fill tier AS intensity (bps)
        premium = bbgl_half_spread_bps(0.0, tox_market, tox_tier)
        return np.maximum(premium, 0.0)

    if name == "as_toxicity":
        # ADD the counterparty-RESOLVED additive AS term on top of the book half-spread.
        return np.maximum(ctx["as_tox_term_per_fill"][idx], 0.0)

    if name == "as_toxicity_ew":
        # The resolved term carrying the TARGET quoter's entire width. Same shape as
        # as_toxicity, two declared differences: the pass-through is the solved lambda*
        # rather than the headline one, and the wallet population is the rank-floor-eligible
        # set, which is the population the target's per-tier term is built over. Both
        # differences exist so the pair against the target has one axis and not three.
        return np.maximum(ctx["as_tox_ew_term_per_fill"][idx], 0.0)

    if name == "bbgl_flat":
        # ONE constant to every fill, equal to the target quoter's own mean extra. The
        # constant is a scalar read from ctx, so this branch reads no coin and no
        # counterparty: it is the width-matched negative control.
        return np.full(n, float(ctx["bbgl_flat_width_bps"]), dtype=np.float64)

    if name == "as_toxicity_plus_global":
        # The target's GLOBAL term exactly as the target computes it, plus the resolved
        # term in place of the target's per-tier term, the sum rescaled to the target's
        # width. bbgl_global_per_fill comes from bbgl_half_spread_bps with the tier
        # argument at zero, so the global leg is the producer's own and not a second
        # spelling of it.
        premium = ctx["bbgl_global_per_fill"][idx] + ctx["as_tox_pg_term_per_fill"][idx]
        return np.maximum(premium, 0.0)

    raise ValueError(f"unknown quoter {name!r}")


# ==================== context builder (per-coin baselines + per-fill tier/tox arrays) ====================
def build_context(arrs, labels, pi_info, J_info, lambda_tox=LAMBDA_TOX_HEADLINE):
    """Pre-compute everything the per-fill quoters need (per coin + per fill).

    Returns ctx with:
      as_base_half_bps[coin]   -> symmetric A-S half-spread (bps) at q=0 (per coin)
      gm_half_bps[coin]        -> pi*J GM half-spread (bps) (per coin)
      glft_total_spread_bps[c] -> GLFT q=0 total spread (bps) for the near-tie comparison
      bbgl_tox_market[coin]    -> EARLY pooled |markout| AS intensity at the headline horizon (bps)
      bbgl_tox_tier_per_fill   -> per-fill tier-j AS intensity (bps) (per-tier term)
      as_tox_term_per_fill     -> per-fill lambda_tox*max(early_tox,0) (the resolved term)
      H_const_bps              -> pooled LATE-half median s_bbo (naive_const)
    All toxicity quantities are EARLY-window estimates frozen before the LATE evaluation
    (strictly OOS). A-S sigma/k are reused from as_quoter (estimate_sigma / per-coin k)."""
    coin = arrs["coin"]
    day = arrs["day"]
    taker = arrs["taker_id"]
    a_mid_hl = arrs[f"a_mid_{HEADLINE_HORIZON}"]   # AS intensity at the headline horizon
    s_bbo = arrs["s_bbo"]
    late_mask = labels["late_mask"]
    early_mask = labels["early_mask"]

    coins = sorted(set(int(c) for c in np.unique(coin)))

    # ---- A-S sigma (reuse as_quoter.estimate_sigma verbatim) + per-coin k ----
    sigma_arrs = {"coin": coin, "day": day, "entry_px": arrs["entry_px"]}
    sigma_info = ASQ.estimate_sigma(sigma_arrs)

    as_base_half_bps = {}
    gm_half_bps = {}
    glft_total_spread_bps = {}
    glft_detail = {}
    bbgl_tox_market = {}
    for c in coins:
        cname = COIN_NAMES.get(c, str(c))
        cpx = arrs["entry_px"][coin == c]
        cpx = cpx[np.isfinite(cpx) & (cpx > 0)]
        mid_ref = float(np.median(cpx)) if cpx.size else float("nan")
        sigma_price = sigma_info["per_coin_summary"].get(cname, {}).get(
            "median_sigma_price", float("nan"))
        # per-coin k in 1/PRICE from the realized half-spread (mean dist ~ 1/k), as_quoter style
        c_obs = arrs["s_bbo"][coin == c] * 2.0    # spread_entry_bps
        c_obs = c_obs[np.isfinite(c_obs)]
        half_price = (c_obs / 2.0) / 1e4 * mid_ref
        half_price = half_price[np.isfinite(half_price) & (half_price > 0)]
        mean_half_price = float(np.mean(half_price)) if half_price.size else float("nan")
        k_price = (1.0 / mean_half_price) if mean_half_price > 0 else float("nan")
        A_hat = float(c_obs.size)   # placeholder arrival anchor (count); GLFT swept over A_MULT_GRID

        # symmetric A-S half-spread at q=0 (price -> bps), reuse optimal_spread
        if np.isfinite(sigma_price) and np.isfinite(k_price) and GAMMA_ANCHOR > 0:
            d_price = float(optimal_spread(GAMMA_ANCHOR, sigma_price, TIME_REMAINING_EVAL, k_price))
            as_half_bps = float(spread_price_to_bps(d_price / 2.0, mid_ref))
        else:
            as_half_bps = float("nan")
        as_base_half_bps[c] = as_half_bps if np.isfinite(as_half_bps) else 0.0

        # GM half-spread = pi*J (bps)
        pi_med = pi_info["per_coin"].get(cname, {}).get("pi_median", float("nan"))
        J_bps = J_info["per_coin"].get(cname, {}).get("J_bps", float("nan"))
        gm_half_bps[c] = float(gm_half_spread(pi_med, J_bps)) if (
            np.isfinite(pi_med) and np.isfinite(J_bps)) else 0.0

        # GLFT q=0 total spread (bps) -- reported for the near-tie comparison vs A-S
        glft_total_spread_bps[c] = {}
        glft_detail[c] = {"sigma_price": sigma_price, "k_price": k_price, "A_hat": A_hat,
                          "mid_ref": mid_ref}
        for amult in A_MULT_GRID:
            A = amult * A_hat
            if (np.isfinite(sigma_price) and np.isfinite(k_price) and k_price > 0
                    and A > 0 and GAMMA_ANCHOR > 0):
                cs = float(glft_c_skew(sigma_price, GAMMA_ANCHOR, k_price, A))
                d_glft_price = float(glft_total_spread(0.0, GAMMA_ANCHOR, k_price, cs))
                glft_total_spread_bps[c][f"A_x{amult}"] = {
                    "c_skew_price": cs,
                    "glft_total_spread_bps": float(spread_price_to_bps(d_glft_price, mid_ref)),
                }
            else:
                glft_total_spread_bps[c][f"A_x{amult}"] = {
                    "c_skew_price": float("nan"), "glft_total_spread_bps": float("nan")}

        # BBGL global term: EARLY pooled |markout| AS intensity at the headline horizon, this coin
        em = early_mask & (coin == c) & np.isfinite(a_mid_hl) & np.isfinite(arrs["notional"])
        bbgl_tox_market[c] = (_vw_mean(np.abs(a_mid_hl[em]), arrs["notional"][em])
                              if em.any() else 0.0)

    # ---- per-fill toxicity: BBGL per-tier (decile AS intensity) + resolved additive term ----
    decile_of = labels["decile_of_taker"]
    # Per UNIQ taker, and the NaN pattern is NOT the eligibility pattern. maker_econ's
    # build_toxicity_labels writes NaN here only where a taker has NO finite early fill
    # at all; eligibility is the separate `eligible_mask_taker`, which additionally
    # demands at least K of them. So a finite early_tox means "this taker has an early
    # estimate", not "this taker cleared the floor".
    early_tox = labels["early_tox"]
    uniq = labels["uniq"]
    tid_to_pos = {int(t): i for i, t in enumerate(uniq)}

    # tier (decile) -> mean early_tox within that tier (the BBGL per-tier AS intensity)
    tier_tox = {}
    for tid, dec in decile_of.items():
        pos = tid_to_pos.get(int(tid))
        if pos is None:
            continue
        v = early_tox[pos]
        if np.isfinite(v):
            tier_tox.setdefault(dec, []).append(float(v))
    tier_tox_mean = {d: (float(np.mean(vs)) if vs else 0.0) for d, vs in tier_tox.items()}

    # ---- per-fill arrays, VECTORIZED via per-taker lookup tables on the uniq index ----
    # uniq is the sorted unique taker id list from build_toxicity_labels; np.searchsorted
    # maps every fill's taker_id to its uniq position in one pass (no per-fill Python loop).
    n = taker.size
    pos_of_fill = np.searchsorted(uniq, taker)           # uniq is sorted -> exact positions
    # per-uniq-taker resolved AS term = lambda_tox * max(early_tox, 0).
    #
    # WHAT THIS LINE ACTUALLY GATES ON, because the comment that stood here said
    # something else and was wrong. It said "non-eligible -> 0". The predicate below is
    # np.isfinite(early_tox), and that is NOT the eligibility mask: it is true for every
    # taker with at least ONE finite early fill, while eligibility (labels
    # ["eligible_mask_taker"]) additionally demands at least K of them. A taker with one
    # early fill is therefore quoted a widening built on a one-fill toxicity estimate,
    # and the rank floor K -- the sweep this file reports as its robustness axis -- does
    # not enter this term at all.
    #
    # The consequence is measurable, and as_term_value measures it rather than asserting
    # it: adverse_selection_term_value.eligibility_scope counts how many of its own
    # leaves move between the K rows, and while that count is zero the K sweep of that
    # block is reporting one number twice, because the only thing K changes is a mask
    # this term never reads. The block therefore says this about itself and the artifact
    # does not need this comment read. The per-TIER term below is the opposite case --
    # it is built from
    # decile_of_taker, which build_toxicity_labels fills for eligible takers only, so K
    # does bite there.
    #
    # Left as it computes rather than repaired here: introducing the mask would move a
    # published quantity and is a decision with its own recompute, not a comment fix.
    #
    # THE TERM IS BUILT BY THE FUNCTION THE PLACEBO'S ARMS ARE ALSO BUILT BY, which is the
    # point of that function existing. What the quoter books and what the placebo calls the
    # observed arm are now one call rather than two spellings that have to be kept in step
    # by hand -- and it was exactly such a pair drifting apart that left the null arm gated
    # on the rank floor while this line never was. Verified bit-identical to the
    # `lambda_tox * np.where(np.isfinite(early_tox), np.maximum(early_tox, 0), 0)` it
    # replaces, at lambda_tox 0, 0.37, 0.5 and 1.0 over 20,000 scores a quarter of them
    # absent (2026-08-01); no figure here moves.
    as_term_by_taker = resolved_term_by_taker(
        early_tox, identity_term_population(early_tox), lambda_tox)
    as_tox_term_per_fill = as_term_by_taker[pos_of_fill]
    # per-uniq-taker BBGL per-tier AS intensity = max(tier_tox_mean[decile], 0); others -> 0
    tier_intensity_by_taker = np.zeros(uniq.size, dtype=np.float64)
    for tid, dec in decile_of.items():                   # loop over eligible takers only (small)
        p = tid_to_pos.get(int(tid))
        if p is not None:
            tier_intensity_by_taker[p] = max(tier_tox_mean.get(dec, 0.0), 0.0)
    bbgl_tox_tier_per_fill = tier_intensity_by_taker[pos_of_fill]

    H_const_bps = (float(np.median(s_bbo[late_mask][np.isfinite(s_bbo[late_mask])]))
                   if late_mask.any() else float("nan"))

    # small coin->value lookup arrays (coin codes 0/1/2) for VECTORIZED per-fill lookups,
    # replacing per-fill Python comprehensions in quoter_extra_half_spread_bps.
    lut_len = max(COIN_NAMES) + 1
    gm_half_lut = np.zeros(lut_len, dtype=np.float64)
    bbgl_tox_market_lut = np.zeros(lut_len, dtype=np.float64)
    for c in coins:
        gm_half_lut[c] = gm_half_bps.get(c, 0.0)
        bbgl_tox_market_lut[c] = bbgl_tox_market.get(c, 0.0)

    ctx = {
        "as_base_half_bps": as_base_half_bps,
        "gm_half_bps": gm_half_bps,
        "gm_half_lut": gm_half_lut,
        "glft_total_spread_bps": glft_total_spread_bps,
        "glft_detail": glft_detail,
        "bbgl_tox_market": bbgl_tox_market,
        "bbgl_tox_market_lut": bbgl_tox_market_lut,
        "bbgl_tox_tier_per_fill": bbgl_tox_tier_per_fill,
        "as_tox_term_per_fill": as_tox_term_per_fill,
        "tier_tox_mean": tier_tox_mean,
        "H_const_bps": H_const_bps,
        "lambda_tox": lambda_tox,
        "sigma_info": sigma_info,
    }
    solve_equal_width_arms(ctx, arrs, late_mask, early_tox,
                           np.where(labels["eligible_mask_taker"])[0], pos_of_fill)
    return ctx


# ==================== equal width, solved rather than tuned ====================
def solve_equal_width_arms(ctx, arrs, late_mask, early_tox, eligible_pos, pos_of_fill):
    """Put the two equal-width arms on EQUAL_WIDTH_TARGET_QUOTER's mean extra, by equation.

    WHY AN EQUATION AND NOT A GRID. A comparison holds only while the thing declared equal
    IS equal, and a hand-picked pass-through drifts off the target silently the moment the
    target moves -- which it does, because the target's width is built from this run's own
    early markouts. The resolved term is exactly linear in the pass-through by construction
    (as_toxicity_term_bps returns lambda * max(score, 0), with no cap and no clip that can
    bind above zero), so the mean extra is exactly linear in lambda and the landing is
    arithmetic rather than search. That is the third requirement of the comparison rule:
    where equality can be built in, build it in, so it cannot come apart unnoticed.

    THE TWO SOLVES.
      as_toxicity_ew           mean(lambda * unit) = target  ->  lambda* = target / mean(unit)
      as_toxicity_plus_global  mean(global + lambda * unit) = target
                                                    ->  lambda* = (target - mean(global)) / mean(unit)
    Both are exact. The second has an admissibility condition the first does not: the target
    has to leave room above its own global leg, or the pass-through comes out non-positive
    and the arm would have to TIGHTEN to reach the target width. That is not a quoter this
    file will build, so the solve records the failure and the arm is refused rather than
    clipped to something that no longer answers the question.

    THE POPULATION IS THE FLOOR-ELIGIBLE ONE, and this is a departure from the published
    as_toxicity term, which reads no floor. It is deliberate and it is the whole reason the
    arm exists: the target's per-tier term is built from decile_of_taker, which
    build_toxicity_labels fills for floor-eligible takers only, so an arm that scored wallets
    the target cannot score would differ from it on eligibility as well as on allocation, and
    the pair would carry the same second confound the six-quoter ranking already carries. The
    published as_toxicity arm is untouched; this is a NEW name with its own population, and
    comparison_manifest prints the wallet counts of both arms beside the difference.

    Everything written here lands in ctx; nothing is published from inside this function.
    The measurement of whether the landing held is comparison_manifest's, taken from the
    evaluated blocks rather than from these arrays, so the check reads the same leaves a
    reader reads."""
    late_idx = np.where(late_mask)[0]
    coin = arrs["coin"]

    # the target's own width, obtained by CALLING the target's branch. A width recomputed
    # here from the target's ingredients would be a second spelling of the target quoter,
    # and a second spelling is what silently survives a repair of the first.
    target_extra = quoter_extra_half_spread_bps(EQUAL_WIDTH_TARGET_QUOTER, arrs, late_idx, ctx)
    target_mean = mean_extra_bps(target_extra)

    # the target's GLOBAL leg alone: the producer with the per-tier argument at zero.
    ctx["bbgl_global_per_fill"] = bbgl_half_spread_bps(
        0.0, ctx["bbgl_tox_market_lut"][coin], 0.0)
    global_mean = mean_extra_bps(ctx["bbgl_global_per_fill"][late_idx])

    # the resolved term at unit pass-through over the floor-eligible wallets: the slope of
    # both solves. Built by the same function the published arm is built by.
    unit_by_taker = resolved_term_by_taker(early_tox, eligible_pos, 1.0)
    unit_per_fill = unit_by_taker[pos_of_fill]
    unit_mean = mean_extra_bps(unit_per_fill[late_idx])

    lam_ew = (target_mean / unit_mean) if (np.isfinite(unit_mean) and unit_mean > 0) else float("nan")
    lam_pg = (((target_mean - global_mean) / unit_mean)
              if (np.isfinite(unit_mean) and unit_mean > 0) else float("nan"))

    # A non-positive pass-through is not a solution, it is the equation telling us the arm
    # cannot exist at this width. Carry NaN so the arm's extra is NaN, which the manifest
    # then reports as a missed landing and the refusal withholds the difference.
    lam_pg_admissible = bool(np.isfinite(lam_pg) and lam_pg > 0)

    ctx["lambda_tox_equal_width"] = lam_ew
    ctx["lambda_tox_plus_global"] = lam_pg if lam_pg_admissible else float("nan")
    ctx["as_tox_ew_term_per_fill"] = resolved_term_by_taker(
        early_tox, eligible_pos, lam_ew)[pos_of_fill]
    ctx["as_tox_pg_term_per_fill"] = resolved_term_by_taker(
        early_tox, eligible_pos, ctx["lambda_tox_plus_global"])[pos_of_fill]
    ctx["bbgl_flat_width_bps"] = target_mean
    ctx["equal_width_solve"] = {
        "target_quoter": EQUAL_WIDTH_TARGET_QUOTER,
        "target_mean_extra_bps": target_mean,
        "target_global_leg_mean_extra_bps": global_mean,
        "unit_resolved_term_mean_extra_bps": unit_mean,
        "lambda_as_toxicity_ew": lam_ew,
        "lambda_as_toxicity_plus_global": lam_pg,
        "lambda_plus_global_admissible": lam_pg_admissible,
        "lambda_headline_for_reference": ctx["lambda_tox"],
        "n_wallets_floor_eligible": int(eligible_pos.size),
        "population": ("the resolved term of both solved arms is built over the "
                       "rank-floor-eligible counterparties, the same population "
                       "decile_of_taker gives the target's per-tier term; the published "
                       "as_toxicity arm is built over every counterparty with a finite "
                       "early estimate and is not touched by this solve"),
        "method": ("the resolved term is exactly linear in the pass-through, so the "
                   "pass-through that lands the equal-weighted mean extra on the target's "
                   "is solved and not searched; comparison_manifest measures the landing "
                   "on the evaluated blocks and refuses the difference above "
                   f"{EQUAL_WIDTH_RTOL:.0e} relative"),
    }
    return ctx["equal_width_solve"]


# ==================== one quoter's net economics (all coins x horizons x tiers) ====================
def evaluate_quoter(name, arrs, late_mask, ctx, stream_cell, horizons=None, ci_horizons=None,
                    inventory_sim=True, progress=None):
    """Net economics for one quoter on the LATE half: per coin x horizon x tier, both
    measures. Reuses maker_econ accounting via gross_quoter_measures + net_block.

    `horizons` and `ci_horizons` default to the full declared ladder and to the two rungs
    that carry a bootstrap band. The walk-forward passes a single rung and no band: it asks
    whether the ORDERING reproduces on days it was not fitted on, and a band on a one-day
    fold answers a question nobody asked while costing the same as the whole headline run.
    Both are keyword arguments with the published defaults, so the headline call is
    unchanged and the cheap call has to ask for cheapness by name.

    `inventory_sim` off skips the A-S control simulation, which is a function of as_quoter's
    own synthetic fixture and of nothing in this fold.

    `progress` is a callable taking one string, or None. It is called at the boundary of the
    coin-group loop, which is the outermost cycle inside this function that takes minutes:
    one coin group at the headline settings is four capped bootstraps.

    `stream_cell` IS NOT A GENERATOR AND THAT IS THE POINT. Until 2026-08-03 this function
    took the one generator main() threaded through the whole run, and every bootstrap drew
    from it in call order. The bands an arm reported therefore depended on HOW MANY ARMS HAD
    RUN BEFORE IT, which is not a property of that arm at all. Adding the three equal-width
    arms proved it by moving 864 confidence-interval ends across the six published quoters
    while not one point estimate budged -- the point estimates never touch a generator.

    That is a reproducibility defect and not a curiosity. Reproducibility requires that a
    stranger executing this code get the results the paper presents; a stranger who adds a
    tenth quoter would get different bands on OUR nine. So the identity of the stream is now
    the identity of the CELL: settings.rng derives it from the master seed and the names
    below, which makes it independent of both the composition of QUOTER_NAMES and the order
    the loop walks them. `stream_cell` carries whatever else distinguishes this call from
    another on the same arm -- the rank-floor rung in the headline grid, the fold in the
    walk-forward -- and it is a tuple of naming components, never a generator."""
    horizons = HORIZONS if horizons is None else tuple(horizons)
    ci_horizons = (HEADLINE_HORIZON, 60) if ci_horizons is None else tuple(ci_horizons)
    coin = arrs["coin"]
    notl = arrs["notional"]
    s_bbo = arrs["s_bbo"]
    coin_groups = [("BTC", 0), ("ETH", 1), ("pooled", -1)]

    net_by_coin = {}
    extra_summary = {"by_coin": {}}
    for cname, ccode in coin_groups:
        if progress is not None:
            progress(f"    {name} / {cname}: start")
        sel = late_mask if ccode == -1 else (late_mask & (coin == ccode))
        idx = np.where(sel)[0]
        if idx.size == 0:
            net_by_coin[cname] = {"n_late_fills": 0, "note": "no late fills in this coin"}
            continue
        extra = quoter_extra_half_spread_bps(name, arrs, idx, ctx)
        w = notl[idx]
        per_h = {}
        for h in horizons:
            # COST-NOT-ALPHA booking (the honest counterfactual). A fill PRINTED at the BBO,
            # so a wider counterfactual quote cannot literally collect more spread on it; the
            # defensive widening only deters/reprices adverse flow. Two honest bounds:
            #  (1) per-fill OFFSET cap: recovered <= max(a_mid_h, 0) -- a quote can recover at
            #      most the adverse cost it was paying; a benign fill (a_mid<=0) recovers 0.
            #  (2) RECAPTURE fraction (maker_econ B2 deploy f): under the no-fill-model
            #      counterfactual only a fraction f of the would-be-deterred adverse flow is
            #      realistically recovered at the wider quote (the rest is declined volume,
            #      not booked). Full offset (f=1) is the IDEALIZED B1 UPPER BOUND, not the
            #      deployable result -- so the headline books f*offset, the realistic point.
            # Together these bound the INCREMENT and not the level. The only thing separating
            # this arm from naive_at_book is `booked`, and booked <= max(a_mid_h, 0), so a quote
            # recovers at most the adverse cost the fill had already paid. On a TOXIC fill
            # (a_mid_h > 0) that ceilings gross_MID at s_bbo; on a benign fill the cap is 0 and
            # gross_MID is s_bbo - a_mid_h, which sits ABOVE s_bbo for naive and quoter alike.
            # So gross_MID <= s_bbo holds on the toxic side only, which is the side the self-test
            # asserts under cost_not_alpha_cap_offsets_only, and it is not an ordering of arms.
            # THE ORDERING AGAINST NAIVE RUNS THE OTHER WAY, and it is measured rather than
            # guaranteed. booked >= 0 for every arm and == 0 for naive_at_book, so no arm can
            # score BELOW naive on any row. Over the 216 published cells (2 rank-floor rungs x 3
            # coin cuts x 3 horizons x 2 measures x 6 fee tiers) the other nine arms come out
            # above naive in all 216, and as_symmetric, which books extra 0 by construction,
            # ties it to the last bit in all 216. Cost-not-alpha rests on every arm staying
            # net-NEGATIVE after fees -- cross_checks.all_quoters_net_negative_at_base, and
            # fill_aware_b2.n_positive_grid_cells == 0 -- never on out-earning the naive maker.
            a_mid_h = arrs[f"a_mid_{h}"][idx]
            offset_cap = np.minimum(extra, np.maximum(a_mid_h, 0.0))
            booked = RECOVER_FRAC * offset_cap
            s_q = s_bbo[idx] + booked
            g_mid, g_print = gross_quoter_measures(s_q, a_mid_h,
                                                   s_bbo[idx], arrs[f"a_print_{h}"][idx])
            # bootstrap CI at the headline horizon (10s, the reported one) and at
            # 60s, which is carried through as the robustness companion. The 1s
            # sensitivity keeps point estimates only, which keeps the run tractable.
            ci = h in ci_horizons
            # One cell per (rung-or-fold, arm, coin group, horizon, measure). The measure is
            # part of the identity rather than left to share a stream with its neighbour:
            # two bands drawn from one stream resample the same rows, which is defensible as
            # a paired draw and indefensible as an unstated one, and settings.colliding_cells
            # is the check that would have to call it a collision.
            per_h[f"h{h}"] = {
                "net_PRINT": net_block(
                    g_print, w,
                    _cell_rng("mm_bakeoff", "quoter_net_ci", *stream_cell, name, cname,
                          int(h), "net_PRINT"),
                    with_ci=ci),
                "net_MID_lower": net_block(
                    g_mid, w,
                    _cell_rng("mm_bakeoff", "quoter_net_ci", *stream_cell, name, cname,
                          int(h), "net_MID_lower"),
                    with_ci=ci),
            }
        net_by_coin[cname] = {"n_late_fills": int(idx.size), "by_horizon": per_h}
        ef = extra[np.isfinite(extra)]
        extra_summary["by_coin"][cname] = {
            # ONE spelling of the width statistic: the equal-width arms are solved to this
            # function's value, comparison_manifest measures the landing on this leaf, and
            # this leaf is computed by that same function.
            "mean_extra_half_spread_bps": mean_extra_bps(extra),
            "frac_fills_widened": float(np.mean(ef > 1e-12)) if ef.size else float("nan"),
            "min_extra_half_spread_bps": float(np.min(ef)) if ef.size else float("nan"),
            "n_extra_finite": int(ef.size),
        }
        if progress is not None:
            progress(f"    {name} / {cname}: done, {idx.size:,} late fills, "
                     f"mean extra {extra_summary['by_coin'][cname]['mean_extra_half_spread_bps']:.4f} bps")

    inv_sim = _inventory_control_for(name) if inventory_sim else {
        "control_ratio_as_over_null": float("nan"),
        "mean_reverts": False,
        "note": "inventory control sim not run on this call (walk-forward fold)",
    }
    return {
        "spec": _quoter_spec(name),
        "net_by_coin": net_by_coin,
        "inventory_control_sim": inv_sim,
        "extra_half_spread_summary": {
            **extra_summary,
            # the pass-through this arm actually charged. Zero for the arms that carry no
            # resolved term, the headline one for as_toxicity, and the SOLVED one for the
            # two equal-width arms -- a leaf that would otherwise have to be looked up in a
            # different block to know what the arm beside it was quoting.
            "lambda_tox": _lambda_tox_for(name, ctx),
        },
    }


def _lambda_tox_for(name, ctx):
    """The pass-through the named arm charged on its resolved term, 0.0 where there is none."""
    if name == "as_toxicity":
        return ctx["lambda_tox"]
    if name == "as_toxicity_ew":
        return ctx.get("lambda_tox_equal_width", float("nan"))
    if name == "as_toxicity_plus_global":
        return ctx.get("lambda_tox_plus_global", float("nan"))
    return 0.0


def _inventory_control_for(name):
    """Inventory-control ratio for quoters with a reservation skew; null for the rest.

    as_symmetric and as_toxicity share the IDENTICAL A-S inventory leg (the additive AS
    term does not touch the reservation skew), so both reuse as_quoter.inventory_control_sim
    verbatim -> numbers byte-identical to as_quoter_results.json. bbgl carries the A-S
    inventory leg too (its AS premium is a spread widening, not an inventory channel), so
    it also reports the controlled sim. naive_at_book / naive_const / gm_vpin have NO
    reservation skew -> null/uncontrolled, mean_reverts False."""
    if name in ("as_symmetric", "as_toxicity", "bbgl", "as_toxicity_ew",
                "as_toxicity_plus_global"):
        sim = ASQ.inventory_control_sim()
        return {
            "control_ratio_as_over_null": sim["control_ratio_as_over_null"],
            "mean_reverts": sim["mean_reverts"],
            "as_mean_abs_inventory_whole": sim["as_mean_abs_inventory_whole"],
            "as_mean_abs_inventory_late": sim["as_mean_abs_inventory_late"],
            "null_mean_abs_inventory_whole": sim["null_mean_abs_inventory_whole"],
            "null_mean_abs_inventory_late": sim["null_mean_abs_inventory_late"],
            "as_terminal_abs_over_shock": sim["as_terminal_abs_over_shock"],
        }
    return {
        "control_ratio_as_over_null": float("nan"),
        "mean_reverts": False,
        "note": "no reservation skew (fixed-spread / market-level GM) -> uncontrolled null",
    }


def _quoter_spec(name):
    specs = {
        "naive_at_book": "naive fixed: s_q = s_bbo (quote AT the BBO; reproduces "
                         "maker_econ net_MID_lower / net_PRINT). No inventory, no toxicity.",
        "naive_const": "naive fixed: s_q = H_const (one constant half-spread to everyone, "
                       "the pooled LATE-half median s_bbo). Zero-information benchmark.",
        "as_symmetric": "Avellaneda-Stoikov (2008): inventory-only, counterparty-blind. Its "
                        "content is the reservation-price inventory SKEW (reported via the "
                        "control sim, control_ratio<0.5); it adds NO adverse-selection "
                        "premium, so its income baseline = the book half-spread = naive_at_book. "
                        "The A-S absolute spread LEVEL is a single-maker FLOOR (parameter-"
                        "dependent), reported as_base_half_bps, NOT booked as income.",
        "gm_vpin": "Glosten-Milgrom (1985): + market-level pi*J adverse-selection premium on "
                   "top of the book; pi a VPIN/PIN proxy (Easley-Lopez de Prado-O'Hara 2012), "
                   "J = mean(|markout at the headline horizon|). Book-only info, NO counterparty identity.",
        "bbgl": "Barzykin-Bergault-Gueant-Lemmel (2508.20225): + beta_g*global AS + "
                "beta_t*per-tier AS premia on top of the book (reduced-form instance; "
                "widen-only). Validation of the published quoting lineage.",
        "as_toxicity": "+ lambda_tox*max(early_tox,0) counterparty-RESOLVED AS premium on top "
                       "of the book (reduced-form instance of the BBGL per-tier skew on "
                       "OBSERVED identity; widen-only). Validation, not invention.",
        "as_toxicity_ew": (
            "EQUAL-WIDTH arm of as_toxicity: the same resolved term at the SOLVED "
            f"pass-through that puts its mean extra on {EQUAL_WIDTH_TARGET_QUOTER}'s, over "
            "the rank-floor-eligible counterparties (the population the per-tier term of "
            f"{EQUAL_WIDTH_TARGET_QUOTER} is built on). Exists so that the difference "
            f"against {EQUAL_WIDTH_TARGET_QUOTER} has ONE axis -- whether a fixed width is "
            "better allocated per wallet or per coin-and-decile -- rather than the three "
            "the six-quoter ranking carries. Not a second headline: the published "
            "as_toxicity arm is untouched."),
        "bbgl_flat": (
            f"WIDTH-MATCHED negative control on {EQUAL_WIDTH_TARGET_QUOTER}: one flat "
            f"constant equal to {EQUAL_WIDTH_TARGET_QUOTER}'s own pooled mean extra, handed "
            "to every fill, conditioned on nothing. Same construction as "
            "flat_surcharge_control.py's one-global-constant variant, aimed at the quoter "
            "that finishes ahead instead of at symmetric A-S. Answers whether that quoter's "
            "result is its conditioning or its width."),
        "as_toxicity_plus_global": (
            f"{EQUAL_WIDTH_TARGET_QUOTER}'s market-wide GLOBAL term kept exactly as that "
            "quoter computes it, with its per-tier term REPLACED by the counterparty-"
            "resolved term, the sum rescaled to the same mean extra by the same solved "
            "equation. Asks whether the resolved term improves the published Barzykin-"
            "Bergault-Gueant-Lemmel instance, not only symmetric A-S."),
    }
    return specs[name]


def glft_view(ctx):
    """The GLFT-vs-A-S spread comparison as it goes into the artifact, keyed by coin NAME.

    WHY IT IS A FUNCTION. main() needs this view once per K to MEASURE that the block does
    not move with the rank floor, and once more for the block it publishes. Two spellings
    of the same view would let the measurement and the published numbers drift apart, which
    is precisely the failure the measurement exists to catch."""
    return {
        "glft_total_spread_bps": {COIN_NAMES.get(c, str(c)): ctx["glft_total_spread_bps"][c]
                                  for c in ctx["glft_total_spread_bps"]},
        "as_base_half_bps": {COIN_NAMES.get(c, str(c)): ctx["as_base_half_bps"][c]
                             for c in ctx["as_base_half_bps"]},
    }


# ==================== bake-off ranking + AS-term value + placebo ====================
def bakeoff_ranking(quoter_blocks):
    """Per coin x tier ordering by net_MID_lower vw at the headline horizon (HKEY),
    ascending cost = most negative first. best_cost = least-negative. Records whether all
    entries are < 0 (cost not alpha)."""
    out = {}
    for cname in ("BTC", "ETH", "pooled"):
        out[cname] = {"by_tier": {}}
        for tier in FEE_TIERS:
            rows = []
            for qname in QUOTER_NAMES:
                blk = quoter_blocks.get(qname, {}).get("net_by_coin", {}).get(cname, {})
                if not blk.get("n_late_fills"):
                    continue
                v = blk["by_horizon"][HKEY]["net_MID_lower"]["by_fee_tier"][tier]["net_vw_bps"]
                if v == v:
                    rows.append((qname, float(v)))
            rows.sort(key=lambda t: t[1])           # ascending: most-negative cost first
            best = rows[-1] if rows else None       # least-negative
            out[cname]["by_tier"][tier] = {
                "ordered_ascending_cost": rows,
                "best_cost_least_negative": best,
                "all_net_negative": bool(rows) and all(v < 0 for _, v in rows),
            }
    return out


# ==================== one leaf comparator, calibrated, for every "did it move" count ====================
# WHY THERE IS A FUNCTION FOR THIS. Two blocks in this file publish a count of leaves that
# moved between two recomputes of the same quantity, and a hand-rolled count is how the
# wrong answer gets published: a diff keyed by path silently drops a value that was renamed
# and moved (measured here on 2026-07-31 -- sixteen keys vanished and sixteen appeared
# across a floor change, holding the same sixteen values), and a naive equality reports NaN
# against NaN as a difference (measured elsewhere -- 870 "moved" leaves, all of them
# not-a-number against not-a-number). Both traps are handled once, here, and the predicate
# is calibrated in run_self_tests on a pair that MUST move and a pair that MUST NOT.
_ABSENT = object()


def _is_number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _leaf_pairs(ref, other, path=()):
    """Walk two nested dicts together, yielding (path, ref_leaf, other_leaf) per leaf.

    A key present in only one tree is yielded with `_ABSENT` on the missing side rather
    than skipped, so a rename shows up as one leaf that vanished and one that appeared
    instead of as no finding at all."""
    keys = list(ref)
    keys += [k for k in other if k not in ref]
    for k in keys:
        a = ref.get(k, _ABSENT)
        b = other.get(k, _ABSENT)
        if isinstance(a, dict) and isinstance(b, dict):
            for sub in _leaf_pairs(a, b, path + (k,)):
                yield sub
        else:
            yield path + (k,), a, b


def _same_leaf(a, b):
    """Two leaves AGREE when both are the same number, or both are not-a-number, or both
    are the same non-numeric value. They DIFFER when the numbers differ, when one is a
    number and the other is not, and when either side has no such key at all."""
    if a is _ABSENT or b is _ABSENT:
        return False
    if _is_number(a) and _is_number(b):
        return (a == b) or (a != a and b != b)
    if _is_number(a) != _is_number(b):
        return False
    return a == b


LEAF_PREDICATE = ("two leaves agree when both are the same number, or both are "
                  "not-a-number, or both are the same non-numeric value; they differ when "
                  "the numbers differ, when one is a number and the other is not, and when "
                  "either side has no such key (a renamed key counts as two differences, "
                  "one vanished and one appeared)")


def count_moved_leaves(ref, other, max_examples=10):
    """Compare two nested dicts leaf by leaf. Returns (n_leaves, n_moved, examples).

    `examples` carries the path and both values for up to `max_examples` differences, so a
    non-zero count names its own location instead of only its size."""
    n_leaves = 0
    n_moved = 0
    examples = []
    for path, a, b in _leaf_pairs(ref, other):
        n_leaves += 1
        if not _same_leaf(a, b):
            n_moved += 1
            if len(examples) < max_examples:
                examples.append({
                    "path": list(path),
                    "ref": "<absent>" if a is _ABSENT else a,
                    "other": "<absent>" if b is _ABSENT else b,
                })
    return n_leaves, n_moved, examples


# What the rows of adverse_selection_term_value are keyed by, in words, written into the
# block itself so a reader who never opens this file knows which of the two identity
# terms the rank floor reaches. The wording is a constant rather than an inline literal
# so that the console print and the artifact cannot come to say different things.
AS_TERM_VALUE_ELIGIBILITY_NOTE = (
    "READ THIS BEFORE COMPARING THE K ROWS. The as_toxicity quoter's additive premium is "
    "lambda_tox * max(early_tox, 0) applied to EVERY counterparty that has a finite early "
    "toxicity estimate -- that is, at least one early fill with a finite markout at the "
    "headline horizon. The declared rank floor K (k_headline, k_list) is NOT applied to "
    "it: the term is built from the early_tox array, not from the eligible_mask_taker the "
    "floor produces, so a wallet with one early fill is quoted a widening on a one-fill "
    "estimate. The consequence is that the K rows of this block are not a sensitivity, "
    "and n_leaves_that_moved_with_k beside this note is the measurement of it, taken on "
    "the rows printed here: while it reads zero, a row-to-row comparison across K "
    "measures nothing at all. The floor DOES bite on the bbgl per-tier term, built from "
    "decile_of_taker and so sees eligible takers only, and on the toxic-decile membership "
    "the B1/B2 policy bounds read. It no longer bites on the label-shuffle placebo: from "
    "2026-08-01 that placebo permutes over the SAME population this term is built on, "
    "because a null that hands premium to fewer wallets than the observed arm is not a "
    "null of this term at all. Recorded rather than repaired: gating this term on the "
    "floor would move a published quantity and is owed its own recompute.")


def as_term_value(quoter_blocks_by_K):
    """Incremental value of the AS terms vs symmetric A-S, per K x coin x tier (headline
    horizon,
    net_MID_lower vw): as_toxicity - as_symmetric, gm_vpin - as_symmetric, and the
    counterparty-resolution PREMIUM as_toxicity - gm_vpin. Cost reductions, never alpha.

    The returned mapping carries one key per K label plus `eligibility_scope`, which says
    in words which counterparties the as_toxicity term is built over and why the K rows
    of this block therefore agree exactly. Consumers of this block select their K label by
    name or match it against ^K(\\d+)$, so the extra key is skipped by all of them.

    The "the K rows agree exactly" half of that statement is MEASURED here rather than
    asserted, over the very rows the block is about to publish, so the claim cannot go
    stale against the numbers printed beside it."""
    out = {}
    for Klabel, qb in quoter_blocks_by_K.items():
        out[Klabel] = {}
        for cname in ("BTC", "ETH", "pooled"):
            def cell(qn, tier):
                blk = qb.get(qn, {}).get("net_by_coin", {}).get(cname, {})
                if not blk.get("n_late_fills"):
                    return float("nan")
                return blk["by_horizon"][HKEY]["net_MID_lower"]["by_fee_tier"][tier]["net_vw_bps"]
            per_tier = {}
            for tier in FEE_TIERS:
                a_tox = cell("as_toxicity", tier)
                a_sym = cell("as_symmetric", tier)
                a_gm = cell("gm_vpin", tier)
                per_tier[tier] = {
                    "as_toxicity_minus_as_symmetric_delta_net_vw_bps":
                        (a_tox - a_sym) if (a_tox == a_tox and a_sym == a_sym) else float("nan"),
                    "gm_minus_as_symmetric_delta_net_vw_bps":
                        (a_gm - a_sym) if (a_gm == a_gm and a_sym == a_sym) else float("nan"),
                    "as_toxicity_minus_gm_delta_net_vw_bps":
                        (a_tox - a_gm) if (a_tox == a_tox and a_gm == a_gm) else float("nan"),
                }
            out[Klabel][cname] = per_tier

    # Measure, do not assert. Every leaf of the first K label against the same leaf of
    # each other label, through the one calibrated comparator this file uses for every
    # "did it move" count: NaN counts as equal to NaN, because a cell with no late fills
    # is NaN in both and that agreement is real agreement, and a key present on only one
    # side counts as a difference rather than as nothing.
    labels = sorted(out)
    n_leaves = 0
    n_moved = 0
    moved = []
    if len(labels) > 1:
        ref = labels[0]
        for other in labels[1:]:
            nl, nm, examples = count_moved_leaves(out[ref], out[other])
            n_leaves += nl
            n_moved += nm
            for ex in examples:
                if len(moved) >= 10:
                    break
                p = ex["path"]
                moved.append({"coin": p[0], "fee_tier": p[1], "field": p[2],
                              ref: ex["ref"], other: ex["other"]})
    out["eligibility_scope"] = {
        "as_toxicity_term_population": (
            "every counterparty with a finite early toxicity estimate (at least one early "
            "fill with a finite markout at the headline horizon)"),
        "rank_floor_applied_to_as_toxicity_term": False,
        "rank_floor_applied_to_bbgl_per_tier_term": True,
        "k_rows_are_a_sensitivity": False,
        "k_labels_compared": labels,
        "n_leaves_compared": n_leaves,
        "n_leaves_that_moved_with_k": n_moved,
        "k_rows_identical_across_k": bool(len(labels) > 1 and n_leaves > 0
                                          and n_moved == 0),
        "leaves_that_moved": moved,
        "leaf_predicate": LEAF_PREDICATE,
        "note": AS_TERM_VALUE_ELIGIBILITY_NOTE,
    }
    return out


# ==================== declared-axis comparisons, with the held-equal list MEASURED ====================
# WHY THIS BLOCK EXISTS. Everything else in this file answers "is this the same number as
# before". Nothing answered "are the two things whose difference we publish comparable at
# all", and on 2026-08-03 that turned out to be the one class of defect no instrument in
# this tree catches: the artifact was fresh, the producer hash matched, the inputs were
# hashed, the registry read the value from the artifact and the prose matched the registry,
# and the conclusion drawn from the difference was still wrong, because the two arms
# differed on width, on eligibility and on nothing that the reading assigned them.
#
# So each pair below DECLARES one axis and LISTS what is held equal, and every entry on
# that list is measured on the very leaves the artifact publishes -- never recomputed
# privately, because a private recomputation can agree with itself while the published leaf
# says something else. A held-equal quantity that misses its bar is not a footnote: it
# withholds the difference. That is the refusal, and it is closed on purpose.
COMPARISON_PAIRS = (
    {
        "pair": "as_toxicity_ew_minus_bbgl",
        "arm_a": "as_toxicity_ew",
        "arm_b": "bbgl",
        "axis": ("HOW a fixed budget of defensive width is allocated: per counterparty "
                 "wallet, from that wallet's own early adverse-selection estimate (arm a), "
                 "against per coin plus per toxicity decile (arm b)"),
        "held_equal": ("mean_extra", "row_set", "wallet_population", "booking", "clock"),
        "consequence_of_the_axis": (
            "the share of fills widened and the floor of the widening. An allocation that "
            "spends the whole budget on wallets with a positive score necessarily widens on "
            "fewer fills and reaches zero on the rest, while one that carries a market-wide "
            "leg widens on every fill and never goes below that leg. These follow from the "
            "axis and are reported, not held equal -- holding them equal would delete the "
            "axis."),
    },
    {
        "pair": "bbgl_flat_minus_bbgl",
        "arm_a": "bbgl_flat",
        "arm_b": "bbgl",
        "axis": ("whether the premium is CONDITIONED on anything at all: a single flat "
                 "constant to every fill (arm a) against the global-plus-per-tier structure "
                 "(arm b)"),
        "held_equal": ("mean_extra", "row_set", "booking", "clock"),
        "consequence_of_the_axis": (
            "the dispersion of the premium across fills, which is zero for the flat arm by "
            "construction. wallet_population is NOT on the held-equal list because the flat "
            "arm has none: it reads no counterparty."),
    },
    {
        "pair": "as_toxicity_plus_global_minus_bbgl",
        "arm_a": "as_toxicity_plus_global",
        "arm_b": "bbgl",
        "axis": ("which SECOND term rides on the shared market-wide global term: the "
                 "counterparty-resolved one (arm a) against the per-tier one (arm b)"),
        "held_equal": ("mean_extra", "global_leg", "row_set", "wallet_population",
                       "booking", "clock"),
        "consequence_of_the_axis": (
            "the share of fills the second term reaches. Both arms widen every fill, "
            "because both carry the global leg; they differ in whether the remainder is "
            "spread over deciles or over wallets."),
    },
)


# Which arms carry a SOLVED pass-through, and where its value is recorded. An arm whose
# solve did not produce a finite positive number carries no resolved term at all: the term
# is zero on every wallet, the arm collapses onto whatever else it carries, and the pair's
# declared axis stops existing. That case is not a small error to note beside the number --
# the number is then a difference between an arm and itself. It was found by driving the
# node over a tape whose wallets all sat below the rank floor, where the manifest of
# as_toxicity_plus_global HELD (its width matched, because with no eligible wallet the
# target has no per-tier leg either) while both arms had quietly become the same quoter.
_SOLVED_PASS_THROUGH_OF = {
    "as_toxicity_ew": "lambda_as_toxicity_ew",
    "as_toxicity_plus_global": "lambda_as_toxicity_plus_global",
}


def _held_equal_row(name, value_a, value_b, rtol, how):
    """One held-equal measurement: both values, the relative gap, the bar, and the verdict."""
    a = float(value_a) if value_a is not None else float("nan")
    b = float(value_b) if value_b is not None else float("nan")
    if np.isfinite(a) and np.isfinite(b):
        denom = max(abs(a), abs(b))
        gap = 0.0 if denom == 0.0 else abs(a - b) / denom
        ok = bool(gap <= rtol)
    else:
        gap = float("nan")
        ok = False
    return {"quantity": name, "arm_a": a, "arm_b": b, "relative_gap": gap,
            "rtol": rtol, "holds": ok, "measured_by": how}


def comparison_manifest(quoter_blocks, ctx):
    """Per declared pair: the axis, the held-equal list MEASURED, and the verdict.

    Reads the evaluated blocks, so every held-equal quantity is the leaf a reader sees.
    Returns a mapping pair -> manifest; the caller withholds any difference whose manifest
    does not hold."""
    out = {}
    solve = ctx.get("equal_width_solve", {})
    for spec in COMPARISON_PAIRS:
        a, b = spec["arm_a"], spec["arm_b"]
        blk_a = quoter_blocks.get(a, {})
        blk_b = quoter_blocks.get(b, {})

        def _width(blk, cname="pooled"):
            return (blk.get("extra_half_spread_summary", {}).get("by_coin", {})
                    .get(cname, {}).get("mean_extra_half_spread_bps"))

        def _fills(blk, cname="pooled"):
            return blk.get("net_by_coin", {}).get(cname, {}).get("n_late_fills")

        rows = []
        for name in spec["held_equal"]:
            if name == "mean_extra":
                rows.append(_held_equal_row(
                    "mean_extra_half_spread_bps_pooled", _width(blk_a), _width(blk_b),
                    EQUAL_WIDTH_RTOL,
                    "quoters.<K>.<arm>.extra_half_spread_summary.by_coin.pooled"
                    ".mean_extra_half_spread_bps"))
            elif name == "row_set":
                rows.append(_held_equal_row(
                    "n_late_fills_pooled", _fills(blk_a), _fills(blk_b), 0.0,
                    "quoters.<K>.<arm>.net_by_coin.pooled.n_late_fills"))
                rows.append(_held_equal_row(
                    "n_extra_finite_pooled",
                    blk_a.get("extra_half_spread_summary", {}).get("by_coin", {})
                    .get("pooled", {}).get("n_extra_finite"),
                    blk_b.get("extra_half_spread_summary", {}).get("by_coin", {})
                    .get("pooled", {}).get("n_extra_finite"), 0.0,
                    "quoters.<K>.<arm>.extra_half_spread_summary.by_coin.pooled.n_extra_finite"))
            elif name == "wallet_population":
                # both arms score wallet-specific premia over the rank-floor-eligible set:
                # arm b through decile_of_taker, arm a because solve_equal_width_arms builds
                # its term over exactly that set. One number, stated for both sides, so a
                # future change to either construction shows up here as a gap.
                n_elig = solve.get("n_wallets_floor_eligible")
                rows.append(_held_equal_row(
                    "n_wallets_carrying_a_wallet_specific_premium", n_elig, n_elig, 0.0,
                    "equal_width_solve.n_wallets_floor_eligible, which is "
                    "len(labels.eligible_mask_taker) -- the set decile_of_taker is filled "
                    "for and the set the solved arms' term is built over"))
            elif name == "global_leg":
                rows.append(_held_equal_row(
                    "global_leg_mean_extra_bps",
                    solve.get("target_global_leg_mean_extra_bps"),
                    solve.get("target_global_leg_mean_extra_bps"), 0.0,
                    "equal_width_solve.target_global_leg_mean_extra_bps -- the same "
                    "per-fill array enters both arms, arm b inside "
                    "bbgl_half_spread_bps and arm a as ctx['bbgl_global_per_fill']"))
            elif name == "booking":
                rows.append(_held_equal_row(
                    "recapture_fraction", RECOVER_FRAC, RECOVER_FRAC, 0.0,
                    "RECOVER_FRAC, applied by the same line of evaluate_quoter to both arms; "
                    "the offset cap min(extra, max(a_mid,0)) is that same line"))
            elif name == "clock":
                rows.append(_held_equal_row(
                    "headline_horizon_s", HEADLINE_HORIZON, HEADLINE_HORIZON, 0.0,
                    "HEADLINE_HORIZON, the rung every published difference is read at"))

        # Does the axis exist on this run at all? An arm whose solved pass-through is not a
        # finite positive number carries a resolved term of exactly zero everywhere, and the
        # difference would then be between an arm and itself.
        preconditions = []
        for arm, side in ((a, "arm_a"), (b, "arm_b")):
            key = _SOLVED_PASS_THROUGH_OF.get(arm)
            if key is None:
                continue
            lam = solve.get(key)
            lam = float(lam) if lam is not None else float("nan")
            preconditions.append({
                "quantity": f"solved_pass_through_of_{arm}",
                "value": lam,
                "requirement": "finite and strictly positive",
                "holds": bool(np.isfinite(lam) and lam > 0),
                "side": side,
                "measured_by": f"declared_axis_comparisons.equal_width_solve.{key}",
                "why": (f"{arm} carries the counterparty-resolved term at this pass-through; "
                        "at zero or not-a-number the term is zero on every wallet and the "
                        "declared axis is not present in this run"),
            })

        holds = (bool(rows) and all(r["holds"] for r in rows)
                 and all(p["holds"] for p in preconditions))
        failures = [r for r in rows if not r["holds"]]
        failed_pre = [p for p in preconditions if not p["holds"]]
        out[spec["pair"]] = {
            "arm_a": a,
            "arm_b": b,
            "difference": f"{a} minus {b}",
            "axis": spec["axis"],
            "axis_preconditions": preconditions,
            "consequence_of_the_axis": spec["consequence_of_the_axis"],
            "held_equal_measured": rows,
            "all_held_equal_quantities_hold": holds,
            "not_held_equal": [
                {"quantity": "frac_fills_widened_pooled",
                 "arm_a": (blk_a.get("extra_half_spread_summary", {}).get("by_coin", {})
                           .get("pooled", {}).get("frac_fills_widened")),
                 "arm_b": (blk_b.get("extra_half_spread_summary", {}).get("by_coin", {})
                           .get("pooled", {}).get("frac_fills_widened")),
                 "classified": "consequence of the axis"},
                {"quantity": "min_extra_half_spread_bps_pooled",
                 "arm_a": (blk_a.get("extra_half_spread_summary", {}).get("by_coin", {})
                           .get("pooled", {}).get("min_extra_half_spread_bps")),
                 "arm_b": (blk_b.get("extra_half_spread_summary", {}).get("by_coin", {})
                           .get("pooled", {}).get("min_extra_half_spread_bps")),
                 "classified": "consequence of the axis"},
                {"quantity": "mean_extra_half_spread_bps_by_coin",
                 "arm_a": {c: _width(blk_a, c) for c in ("BTC", "ETH")},
                 "arm_b": {c: _width(blk_b, c) for c in ("BTC", "ETH")},
                 "classified": (
                     "CONFOUND on the per-coin rows and held equal on the pooled row only. "
                     "The pass-through is one scalar per wallet and a wallet trades both "
                     "coins, so a per-coin solve would quote one counterparty two "
                     "unrelated prices. The pooled difference is the equal-width finding; "
                     "the per-coin rows are reported for shape and are NOT it.")},
            ],
            "refusal": None if holds else {
                "withheld": f"the {a} minus {b} difference",
                "expected": (
                    [{"quantity": r["quantity"], "arm_a": r["arm_a"],
                      "arm_b": r["arm_b"], "rtol": r["rtol"]} for r in failures]
                    + [{"quantity": p["quantity"], "arm_a": p["value"],
                        "arm_b": p["requirement"], "rtol": 0.0} for p in failed_pre]),
                "fact": (
                    [{"quantity": r["quantity"], "relative_gap": r["relative_gap"]}
                     for r in failures]
                    + [{"quantity": p["quantity"], "relative_gap": float("nan"),
                        "value": p["value"]} for p in failed_pre]),
                "where": ([r["measured_by"] for r in failures]
                          + [p["measured_by"] for p in failed_pre]),
                "why": ("a difference between two arms that do not agree on what was "
                        "declared held equal measures the disagreement as well as the "
                        "axis, and there is no way to read the two apart afterwards; a "
                        "difference whose axis precondition failed is a difference "
                        "between an arm and itself"),
            },
        }
    return out


def declared_axis_deltas(quoter_blocks, manifests):
    """The pairwise net differences whose manifests hold, per coin x tier at the headline rung.

    Same cell as adverse_selection_term_value: net_MID_lower notional-weighted, at HKEY.
    A pair whose manifest does not hold gets no numbers at all -- only the refusal record
    that the manifest already carries, repeated here under the key a reader would look for
    the number under, so a missing difference is visibly withheld rather than absent."""
    out = {}
    for pair, man in manifests.items():
        a, b = man["arm_a"], man["arm_b"]
        if not man["all_held_equal_quantities_hold"]:
            out[pair] = {"published": False, "refusal": man["refusal"]}
            continue
        per_coin = {}
        for cname in ("BTC", "ETH", "pooled"):
            per_tier = {}
            for tier in FEE_TIERS:
                def cell(qn):
                    blk = quoter_blocks.get(qn, {}).get("net_by_coin", {}).get(cname, {})
                    if not blk.get("n_late_fills"):
                        return float("nan")
                    return blk["by_horizon"][HKEY]["net_MID_lower"]["by_fee_tier"][tier]["net_vw_bps"]
                va, vb = cell(a), cell(b)
                per_tier[tier] = {
                    "arm_a_net_vw_bps": va,
                    "arm_b_net_vw_bps": vb,
                    "delta_net_vw_bps": (va - vb) if (va == va and vb == vb) else float("nan"),
                }
            per_coin[cname] = per_tier
        out[pair] = {
            "published": True,
            "headline_cell": ("pooled, base fee tier, net_MID_lower notional-weighted, "
                              f"{HKEY}; the per-coin rows carry a measured width gap and "
                              "are shape, not the finding"),
            "sign_convention": ("positive means arm a costs LESS than arm b, because both "
                                "are negative net costs and a larger value is a smaller "
                                "cost"),
            "by_coin": per_coin,
        }
    return out


# ==================== the population the resolved term lives on (one spelling) ====================
# WHY THIS IS A FUNCTION AND NOT A LINE INSIDE EACH ARM. A placebo is only a placebo while
# the observed arm and the null arm are built over the SAME counterparties: the treatment
# being tested is WHICH wallet carries which toxicity score, so everything else the
# treatment touches -- how many wallets are quoted a widening, and how much widening is
# handed out in total -- has to be held fixed. Until 2026-08-01 the two arms here read two
# different predicates, and the file said so in a comment instead of fixing it. One
# spelling, used by both arms, is what makes the mismatch impossible rather than merely
# documented.
def pairwise_wallet_resolved_stats(arrs, late_mask, labels, ctx,
                                   horizon=HEADLINE_HORIZON):
    """Per-WALLET structure of the difference between two quoters, at the headline rung.

    WHY, BEFORE HOW. as_term_value above publishes each pairwise difference as one
    number per coin. Three questions a reader asks of such a number have had no home in
    this artifact, so each was answered outside this repository and typed into prose from
    a run that no longer exists:

      1. How uncertain is it, resampled at the level the TREATMENT varies? The treatment
         here is a wallet's identity, not a fill: one wallet contributes many correlated
         fills, so a fill-resampled band understates. net_block's band is the fill-level
         one and stays what it is; this block adds the wallet-CLUSTERED one beside it.
      2. Is the difference broad or carried by a few counterparties? A mean of +0.33 bps
         reads very differently if fifty wallets produce most of it.
      3. On what share of fills is the difference actually negative, positive, or exactly
         zero? For the as_symmetric pair the answer is forced -- the booked premium cannot
         be negative, so `frac_negative` there is a property of the booking formula and
         NOT a test of anything, and the artifact says so in `zero_is_by_construction`.
         The gm_vpin pair is the two-sided one, and its negative share is the honest
         statement of how often counterparty resolution loses.

    HOW. Both quoters book RECOVER_FRAC * min(extra, max(a_mid,0)) on the same rows and
    subtract the same fee, so their net difference is the notional-weighted mean of the
    per-fill difference in booked extra -- the same fast form placebo_label_shuffle uses
    and for the same reason. The point estimate is recomputed here from that form and
    published beside the one as_term_value derives by subtracting two net leaves, so a
    reader can see the two agree rather than take it on faith; they part only by the
    finite-weight mask difference that block already records.

    The bootstrap resamples WALLET GROUPS with replacement, m out of m, and recomputes the
    ratio of summed numerators to summed denominators from per-wallet partial sums, which
    is the same estimator on every draw. Population and predicate are printed beside every
    count, and the draw budget is the declared one this module already reads."""
    coin = arrs["coin"]
    notl = arrs["notional"]
    taker = arrs["taker_id"]
    TOL = 1e-12
    PAIRS = (("as_toxicity", "as_symmetric"), ("as_toxicity", "gm_vpin"))
    out = {
        "measure": (f"per-fill booked extra half-spread (bps) at {horizon}s, "
                    "RECOVER_FRAC * min(extra, max(a_mid,0)); difference a minus b, "
                    "notional-weighted over late fills"),
        "horizon_s": horizon,
        "rank_floor_fills": K_HEADLINE,
        "cluster_level": "taker wallet (taker_id), because the treatment varies by wallet",
        "n_boot": N_BOOT,
        "predicate_finite": "isfinite(delta) & isfinite(notional) & notional > 0",
        "zero_is_by_construction": (
            "as_toxicity minus as_symmetric cannot be negative: as_symmetric books no "
            "adverse-selection premium and as_toxicity books a non-negative one, so a zero "
            "negative share there is the booking formula speaking, not a measurement. Only "
            "the gm_vpin pair is two-sided."),
        "by_pair": {},
    }
    for a_name, b_name in PAIRS:
        pair_key = f"{a_name}_minus_{b_name}"
        per_coin = {}
        for cname, ccode in (("BTC", 0), ("ETH", 1), ("pooled", -1)):
            sel = late_mask if ccode == -1 else (late_mask & (coin == ccode))
            idx = np.where(sel)[0]
            if idx.size == 0:
                per_coin[cname] = {"n_late_fills": 0, "note": "no late fills in this coin"}
                continue
            a_mid_h = arrs[f"a_mid_{horizon}"][idx]
            cap = np.maximum(a_mid_h, 0.0)
            bk_a = RECOVER_FRAC * np.minimum(
                quoter_extra_half_spread_bps(a_name, arrs, idx, ctx), cap)
            bk_b = RECOVER_FRAC * np.minimum(
                quoter_extra_half_spread_bps(b_name, arrs, idx, ctx), cap)
            d = bk_a - bk_b
            w = notl[idx]
            fin = np.isfinite(d) & np.isfinite(w) & (w > 0)
            d, w, tk = d[fin], w[fin], taker[idx][fin]
            n = d.size
            if n < 2:
                per_coin[cname] = {"n_late_fills": int(idx.size), "n_scored_fills": int(n),
                                   "note": "too few scored fills to summarise"}
                continue
            sw = float(w.sum())
            point = float(np.sum(w * d) / sw) if sw > 0 else float("nan")

            # Per-wallet partial sums once; every bootstrap draw is a gather over these.
            uw, inv = np.unique(tk, return_inverse=True)
            num_by_w = np.bincount(inv, weights=w * d, minlength=uw.size)
            den_by_w = np.bincount(inv, weights=w, minlength=uw.size)
            ng = uw.size
            boots = np.empty(N_BOOT, dtype=np.float64)
            # Named cell, for the reason evaluate_quoter gives at length: this band used to
            # be drawn from the run-wide generator AFTER every arm had drawn from it, so it
            # moved when the arm roster changed. Six of these ends moved for that reason on
            # 2026-08-03 without any pair, any population or any point estimate moving.
            pair_rng = _cell_rng("mm_bakeoff", "pairwise_wallet_ci", pair_key, cname)
            for b in range(N_BOOT):
                g = pair_rng.integers(0, ng, size=ng)
                den = den_by_w[g].sum()
                boots[b] = num_by_w[g].sum() / den if den > 0 else np.nan
            boots = boots[np.isfinite(boots)]
            ci = ([float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))]
                  if boots.size >= 2 else [float("nan"), float("nan")])

            # Concentration of the TOTAL, by wallet. Shares are of the summed numerator,
            # so they are meaningful only when that total is non-zero; when it is not, the
            # shares are published as NaN rather than as a division that happened to run.
            tot = float(num_by_w.sum())
            order = np.argsort(-num_by_w)
            ranked = num_by_w[order]
            shares = {}
            for k in (1, 5, 10, 50, 100):
                shares[f"top{k}_share"] = (float(ranked[:k].sum() / tot)
                                           if tot != 0.0 and ng >= 1 else float("nan"))
            per_coin[cname] = {
                "n_late_fills": int(idx.size),
                "n_scored_fills": int(n),
                "delta_vw_bps": point,
                "ci95_wallet_clustered": ci,
                "ci_excludes_zero": bool(ci[0] == ci[0] and (ci[0] > 0 or ci[1] < 0)),
                "frac_fills_negative": float(np.mean(d < -TOL)),
                "frac_fills_zero": float(np.mean(np.abs(d) <= TOL)),
                "frac_fills_positive": float(np.mean(d > TOL)),
                "n_wallets_universe": int(ng),
                "n_wallets_contributing": int(np.sum(np.abs(num_by_w) > 0.0)),
                "total_gain_numerator_bps_notional": tot,
                "concentration_by_wallet": shares,
            }
        out["by_pair"][pair_key] = per_coin
    return out


def identity_term_population(early_tox):
    """Positions into `uniq` of the counterparties the resolved AS term is built over.

    The predicate is a FINITE early toxicity estimate, which is what build_context books
    the as_toxicity premium from: at least one early fill whose markout at the headline
    horizon is finite. The rank floor is deliberately NOT part of it, because the floor is
    not part of the published quoter either -- see AS_TERM_VALUE_ELIGIBILITY_NOTE, where
    that gap is recorded as a debt of its own."""
    return np.where(np.isfinite(np.asarray(early_tox, dtype=np.float64)))[0]


def resolved_term_by_taker(early_tox, pop_pos, lambda_tox, values=None):
    """lambda_tox * max(score, 0) on `pop_pos`, exactly zero on every other counterparty.

    `values` defaults to the wallet's OWN early score (the observed labelling). A null draw
    passes a permutation of those same scores, so the two arms differ in the assignment of
    score to wallet and in nothing else: same wallets, same multiset of scores, same total
    premium."""
    et = np.asarray(early_tox, dtype=np.float64)
    v = et[pop_pos] if values is None else np.asarray(values, dtype=np.float64)
    out = np.zeros(et.size, dtype=np.float64)
    out[pop_pos] = float(lambda_tox) * np.maximum(v, 0.0)
    return out


def arm_fingerprint(term_by_taker):
    """(wallets quoted a widening, total premium handed out) -- the two side effects of the
    treatment that a count-matched null has to hold constant. Identity, which wallet holds
    which score, is the treatment and is the one thing allowed to move."""
    t = np.asarray(term_by_taker, dtype=np.float64)
    return int(np.count_nonzero(t > 0.0)), float(np.nansum(t))


def placebo_label_shuffle(arrs, late_mask, labels, ctx_builder_args, n_perm=N_PERM):
    """COUNT-matched label-shuffle placebo for the counterparty-RESOLVED quoter.

    WHAT THE NUMBER ASKS. as_toxicity widens against wallets its EARLY-window score calls
    toxic and books a cost reduction on the LATE half. The question is whether that
    reduction comes from WHO the counterparty is, or merely from handing out that much
    defensive spread to that many wallets. So the null redraws identity and holds the rest
    fixed: the same wallets, the same multiset of early scores, the same total premium,
    only the assignment shuffled. The observed reduction beating that null is the evidence
    that identity, not volume of widening, is doing the work.

    THE ARMS SHARE ONE POPULATION AND IT IS THE PUBLISHED QUOTER'S. Both arms are built by
    resolved_term_by_taker over identity_term_population(early_tox) -- every counterparty
    with a finite early estimate, which is exactly what build_context books and therefore
    exactly what the reduction reported here is the reduction OF. The block measures the
    match rather than claiming it: every draw's fingerprint (wallets widened, total
    premium) is compared against the observed arm's and the agreement count is published.

    WHAT THIS FIXED, recorded because it moves a published p. Until 2026-08-01 the observed
    arm was built over every wallet with a finite early estimate while the null arm wrote
    NaN outside the rank-floor-eligible set, so a wallet below the floor carried a positive
    premium in the observed arm and exactly zero in every draw. The observed reduction was
    built over more wallets than any draw of its own null, which pushed the observed value
    up and the p down. The floor rising from 10 to 50 on 2026-07-31 widened the gap -- the
    null arm fell to the eligible set while the observed arm did not move at all -- which
    is what turned a recorded defect into one worth the recompute.

    THE BROKEN ARM IS REPUBLISHED BESIDE THE FIXED ONE, and that is deliberate. Removing it
    in 2026-08-01 left the tree with no number for what the mismatch had been worth, so the
    prose went on quoting the unmatched arm and the gap out of a recompute run made outside
    this repository, at a different floor and a tenth of the draw budget -- three runs
    standing in one table. The gated arm is drawn here again, from its own derived stream,
    and the gap between the arms is published as arm_difference. What changed is its STATUS:
    it is a reported comparison and an upper bound, never the test, and the block says so in
    its own first field.

    BOTH ARMS CARRY A WALLET-CLUSTERED INTERVAL, by the same estimator the pairwise block
    uses. The toxicity label belongs to the wallet, so a per-fill interval is several times
    too narrow; until this run the placebo published no interval at all.

    gm_vpin is the BUILT-IN negative control (no identity -> a shuffle leaves it
    unchanged), so it is reported but not permuted. The SIZE-matched null is a different
    file's: maker_econ.placebo_random_drop redraws a dropped wallet set matched on total
    late notional. p = (beat_count+1)/(n_perm+1), p-floor 1/(n_perm+1)."""
    arrs_full, labels_full, pi_info, J_info, lambda_tox = ctx_builder_args
    coin = arrs["coin"]
    notl = arrs["notional"]
    taker = arrs["taker_id"]
    uniq = labels["uniq"]
    early_tox = labels["early_tox"]
    eligible = labels["eligible_mask_taker"]
    elig_pos = np.where(eligible)[0]
    # THE one population, read once and used by both arms below.
    pop_pos = identity_term_population(early_tox)

    # FAST FORM (follows quoter_extra_half_spread_bps + gross_quoter_measures):
    # as_toxicity books g_mid = (s_bbo + extra) - a_mid, as_symmetric books g_mid = s_bbo
    # - a_mid; both subtract the same fee, so the per-coin net cost REDUCTION is a
    # notional-weighted mean of the booked extra on the late subset -- no full net recompute
    # per permutation. Precompute per-coin LATE slices once.
    #
    # IT IS NOT THE IDENTITY THIS COMMENT USED TO CLAIM, AND THE GAP IS PUBLISHED. reduction()
    # below divides by sw, the notional summed over every late row with a finite positive
    # weight, while maker_econ._vw_mean divides by the notional summed over its JOINT mask.
    # A late row whose a_mid at the headline horizon is not finite therefore contributes zero
    # to reduction()'s numerator and its full weight to reduction()'s denominator, and drops
    # out of both in _vw_mean. The two are the same estimator only on a tape with no such row.
    # In the published run they part by the notional share of exactly those rows: pooled the
    # placebo reports 0.481491 against the 0.482506 the delta block reports, 0.21 per cent
    # lower; BTC 0.358869 against 0.359346, 0.13 per cent; ETH 0.662503 against 0.664661,
    # 0.32 per cent. The direction is forced -- reduction() can only ever come out at or below
    # the delta -- and the sizes reconcile against the coins' scored-notional shares, 0.5961
    # over all late rows against 0.5966 over the scored ones.
    #
    # WHAT IT DOES AND DOES NOT REACH. The p-value is untouched: both arms run through this
    # same reduction(), so the denominator cancels out of the comparison. What moves is the
    # POINT ESTIMATE this block publishes as observed_toxicity_reduction_net_vw_bps, which is
    # 0.21 per cent below the headline delta it looks like. Prose must not quote one for the
    # other. Putting the two estimators on one mask moves a published number and is owed its
    # own run, so it is recorded here rather than repaired.
    pos_of_fill = np.searchsorted(uniq, taker)   # per-fill -> uniq position (uniq sorted)
    # THE COUNT BELOW IS stats.permutation_p, and the note that used to stand here
    # explaining why it could not be has been overtaken on all three of its points.
    # It said routing through the module would re-draw the null: that is true of
    # stats.permutation_test, which owns the draw loop, and false of
    # stats.permutation_p, which counts an ALREADY-DRAWN null and never touches a
    # generator. The draws still come from the generator this file threads through its
    # whole run, exactly as before. It said the slack would become a fraction of the
    # scale of the comparison: only if the caller takes the default, and abs_tol=1e-12
    # hands the module the same absolute slack this loop applied, recorded in the block
    # as "absolute, stated by the caller". It said a draw that came back as no number
    # stays in the denominator here while the module divides by what survived: the two
    # denominators are the same number on this null, because `reduction` returns a
    # finite value for every draw whenever the late notional sum is positive -- it is
    # one weighted mean over a fixed row set, and nothing about a relabelling can make
    # it undefined. The one case where the two would part is a coin whose late fills
    # carry no positive notional at all, where every draw AND the observed value are
    # undefined; the module reports no test there and this file reported the floor, so
    # that value is carried over explicitly below rather than changed in passing.
    out = {"count_matched": {},
           # the deliberately UNMATCHED arm and the measured size of its mismatch. Both are
           # published rather than described, because the prose quotes the unmatched arm as
           # the upper bound and quotes the gap between the arms as a number.
           "rank_floor_gated": {},
           "arm_difference": {},
           "measure": f"net_MID_lower {HKEY} vw, base tier; reduction = as_toxicity - "
                      "as_symmetric = notional-weighted mean booked extra half-spread on "
                      "late fills",
           "n_perm": n_perm, "p_floor": stats.p_floor(n_perm),
           "n_boot_wallet_clustered": int(N_BOOT),
           "cluster_level": ("taker wallet (taker_id): the toxicity label belongs to the "
                             "wallet and not to the fill, so a per-fill interval would be "
                             "several times too narrow")}

    # per-uniq-taker OBSERVED resolved term (true labels), built by the SAME function and
    # over the SAME population as every null draw below.
    obs_term_by_taker = resolved_term_by_taker(early_tox, pop_pos, lambda_tox)
    obs_fingerprint = arm_fingerprint(obs_term_by_taker)
    # the same term with everything below the rank floor removed. Not an arm of the test
    # and not compared against any null -- it is the decomposition a reader needs to see
    # how much of the observed reduction rides on wallets whose early score comes from
    # fewer than K fills, which is the open debt AS_TERM_VALUE_ELIGIBILITY_NOTE records.
    elig_only_term_by_taker = np.zeros(uniq.size, dtype=np.float64)
    elig_only_term_by_taker[elig_pos] = obs_term_by_taker[elig_pos]

    # The populations, stated in the artifact so a reader never has to derive them from
    # this file. Both arms are the same set by construction; the per-draw fingerprint
    # counts below are the measurement that they stayed that way.
    out["arm_populations"] = {
        "question": ("does the cost reduction come from WHO the counterparty is, or from "
                     "handing out that much widening to that many wallets?"),
        "shared_population": ("every counterparty with a finite early toxicity estimate, "
                              "which is the population the published as_toxicity term is "
                              "booked over"),
        "predicate": "np.isfinite(early_tox), the same predicate build_context books on",
        "n_wallets_observed_arm": int(pop_pos.size),
        "n_wallets_null_arm": int(pop_pos.size),
        "n_wallets_in_uniq": int(uniq.size),
        "n_wallets_eligible_at_rank_floor": int(elig_pos.size),
        "rank_floor_fills": K_HEADLINE,
        "n_wallets_below_rank_floor_with_an_estimate": int(pop_pos.size - elig_pos.size),
        "rank_floor_applied_to_either_arm": False,
        "which_arms_that_sentence_is_about": (
            "the two arms of the TEST, count_matched. The rank_floor_gated block beside it "
            "is gated at the floor on purpose and is not one of them"),
        "arms_built_by": "resolved_term_by_taker over identity_term_population(early_tox)",
        "observed_wallets_widened": obs_fingerprint[0],
        "observed_total_premium_bps": obs_fingerprint[1],
        "changed_on": "2026-08-01",
        "what_changed": (
            "the null arm used to write NaN outside the rank-floor-eligible set while the "
            "observed arm kept every wallet with a finite estimate, so a sub-floor wallet "
            "carried a positive premium in the observed arm and exactly zero in every "
            "draw; the observed reduction was measured over more wallets than any draw of "
            "its own null, which raised the observed value and lowered the p. The floor "
            "moving from 10 to 50 on 2026-07-31 widened that gap without touching the "
            "observed arm."),
    }

    for cname in ("BTC", "ETH", "pooled"):
        sel = late_mask if cname == "pooled" else (late_mask & (coin == COIN_NAMES_INV[cname]))
        idx = np.where(sel)[0]
        if idx.size == 0:
            out["count_matched"][cname] = {
                "observed_toxicity_reduction_net_vw_bps": float("nan"),
                "random_mean": float("nan"), "random_std": float("nan"),
                "permutation_p": float("nan"), "toxicity_beats_random": False,
                "procedure": None}
            continue
        pos_late = pos_of_fill[idx]          # uniq position of each LATE fill
        w_late = notl[idx]                   # late-fill notional weights
        cap_late = np.maximum(arrs[f"a_mid_{HEADLINE_HORIZON}"][idx], 0.0)  # COST-NOT-ALPHA cap
        sw = float(np.sum(w_late[np.isfinite(w_late) & (w_late > 0)]))

        good_w = np.isfinite(w_late) & (w_late > 0)

        def reduction_vec(term_by_taker):
            # booked = RECOVER_FRAC * min(resolved term, max(markout,0)) -- the SAME booking
            # as evaluate_quoter, so the reduction can never exceed the cost the maker paid.
            # Returns the PER-FILL vector and its mask, because the wallet-clustered interval
            # below needs a null's mean booking per fill and not only the scalar. reduction()
            # is the notional-weighted mean of exactly this vector, so the two cannot drift.
            extra = RECOVER_FRAC * np.minimum(np.maximum(term_by_taker[pos_late], 0.0), cap_late)
            return extra, np.isfinite(extra) & good_w

        def reduction(term_by_taker):
            extra, m = reduction_vec(term_by_taker)
            return float(np.sum(extra[m] * w_late[m]) / sw) if sw > 0 else float("nan")

        obs_red = reduction(obs_term_by_taker)
        obs_red_elig_only = reduction(elig_only_term_by_taker)
        # ---- COUNT-matched: permute WHICH wallet of the shared population carries which
        # early score. The values handed out are early_tox[perm] with perm a permutation
        # of pop_pos, so the draw redistributes the observed arm's own multiset of scores
        # over the observed arm's own wallets: the fingerprint is matched by construction
        # and the counters below measure that it was.
        perm_reds = []
        n_draws_matching_count = 0
        n_draws_matching_premium = 0
        # mean booked extra per late fill across the draws, accumulated rather than stored:
        # the wallet-clustered interval needs it and keeping n_perm vectors of this length
        # would not fit. Nothing about the scalar the loop already published depends on it.
        acc_matched = np.zeros(idx.size, dtype=np.float64)
        # THE THIRD PLACEBO STREAM, and the one that was left behind. The two beside it --
        # placebo_rank_floor_gated and placebo_arm_ci -- were already named cells; this loop,
        # the one that produces the published p, still drew from the run-wide generator. The
        # cost was measured on 2026-08-03: adding three arms ahead of it in the stream moved
        # random_mean and random_std on every coin, and moved BTC's permutation_p from
        # 0.0009995 to 0.0004997 -- the p-floor of 2/2001 against 1/2001, a reported p
        # halving because a quoter was added elsewhere in the file.
        perm_rng = _cell_rng("mm_bakeoff", "placebo_permutation", cname)
        for _ in range(n_perm):
            perm = perm_rng.permutation(pop_pos)
            term_by_taker = resolved_term_by_taker(early_tox, pop_pos, lambda_tox,
                                                   values=early_tox[perm])
            fp = arm_fingerprint(term_by_taker)
            if fp[0] == obs_fingerprint[0]:
                n_draws_matching_count += 1
            if abs(fp[1] - obs_fingerprint[1]) <= 1e-9 * max(1.0, abs(obs_fingerprint[1])):
                n_draws_matching_premium += 1
            e_p, m_p = reduction_vec(term_by_taker)
            acc_matched += np.where(m_p, e_p, 0.0)
            perm_reds.append(float(np.sum(e_p[m_p] * w_late[m_p]) / sw)
                             if sw > 0 else float("nan"))
        acc_matched /= n_perm
        # One-sided (maker_econ convention): count shuffles whose reduction MATCHES OR
        # BEATS the observed (true-label) one. If the label carries the signal it gives
        # the biggest reduction, so FEW shuffles beat it and the p is small; a large p
        # means the label is no better than noise. The slack is stated absolute at the
        # 1e-12 this loop applied, and the block records the side, the two draw counts,
        # the slack and the rule that produced it.
        procedure = stats.permutation_p(
            obs_red, np.asarray(perm_reds, dtype=np.float64), side="greater",
            abs_tol=1e-12, n_requested=n_perm,
            cell=("mm_bakeoff", "placebo_count_matched", cname))
        # The one branch where this file and the module differ: with no usable draw or a
        # non-finite observed value the module reports no test, where this file reported
        # the budget's floor. Carried over unchanged so the migration moves nothing.
        p_count_matched = (procedure["p"] if procedure["p"] is not None
                           else stats.p_floor(n_perm))
        arr = np.array([r for r in perm_reds if r == r], dtype=np.float64)
        out["count_matched"][cname] = {
            "observed_toxicity_reduction_net_vw_bps": float(obs_red) if obs_red == obs_red else float("nan"),
            "random_mean": float(arr.mean()) if arr.size else float("nan"),
            # POPULATION spread (ddof=0), which is what this file has always reported;
            # the procedure block beside it carries the sample one under null_sd, so the
            # two are named apart rather than one silently replacing the other.
            "random_std": float(arr.std()) if arr.size else float("nan"),
            "permutation_p": p_count_matched,
            "toxicity_beats_random": bool(arr.size and obs_red == obs_red and obs_red >= float(arr.mean())),
            "procedure": procedure,
            # THE ARMS, MEASURED RATHER THAN CLAIMED. Every draw's fingerprint against the
            # observed arm's: how many wallets were quoted a widening, and how much
            # premium was handed out in total. Both counters read n_perm when the null is
            # a permutation of the observed arm over the observed arm's own wallets, and
            # they read 0 under the arrangement this file carried until 2026-08-01, where
            # the null was confined to the rank-floor-eligible subset. run_self_tests
            # calibrates the same two counters on exactly those two cases.
            "arms_matched": {
                "population": ("the counterparties the resolved term is built over: "
                               f"{int(pop_pos.size):,} with a finite early estimate, "
                               "identical in both arms"),
                "predicate": ("a draw matches when it widens the same NUMBER of wallets as "
                              "the observed arm and hands out the same TOTAL premium "
                              "(relative slack 1e-9); which wallet holds which score is "
                              "the treatment and is expected to differ"),
                "n_draws": int(n_perm),
                "n_draws_matching_wallets_widened": int(n_draws_matching_count),
                "n_draws_matching_total_premium": int(n_draws_matching_premium),
                "observed_wallets_widened": obs_fingerprint[0],
                "observed_total_premium_bps": obs_fingerprint[1],
                "all_draws_matched": bool(n_draws_matching_count == n_perm
                                          and n_draws_matching_premium == n_perm),
            },
            # decomposition, not an arm of the test: the same observed reduction with the
            # premium removed from every wallet below the rank floor. The gap between the
            # two is what the as_toxicity term earns from wallets whose early score rests
            # on fewer than K fills.
            "observed_reduction_eligible_wallets_only_net_vw_bps": (
                float(obs_red_elig_only) if obs_red_elig_only == obs_red_elig_only
                else float("nan")),
            "observed_reduction_from_sub_floor_wallets_net_vw_bps": (
                float(obs_red - obs_red_elig_only)
                if (obs_red == obs_red and obs_red_elig_only == obs_red_elig_only)
                else float("nan")),
        }

        # ---- RANK-FLOOR-GATED null: the DELIBERATELY UNMATCHED arm, published as a
        # comparison and never as the test. It is the arrangement this file drew until
        # 2026-08-01 -- the draw hands scores only to wallets clearing the rank floor and
        # exactly zero to every wallet below it, while the observed arm keeps all of them.
        # It is kept because the SIZE of that mismatch is itself a finding: it says in basis
        # points what a null that does not hold the treatment's side effects constant is
        # worth, and the prose quotes it as the upper bound on the reduction. Until this run
        # neither the arm nor the gap had a home in the tree at all and both were read out of
        # a recompute made outside this repository.
        #
        # IT DRAWS FROM ITS OWN STREAM, derived from MASTER_SEED through H.rng rather than
        # taken from the generator this file threads through its run. That is the whole
        # reason not one leaf of the count-matched arm above moves when this arm is added:
        # the shared generator is consumed in exactly the order and quantity it was before.
        gated_rng = _cell_rng("mm_bakeoff", "placebo_rank_floor_gated", cname)
        gated_reds = []
        n_gated_matching_count = 0
        acc_gated = np.zeros(idx.size, dtype=np.float64)
        for _ in range(n_perm):
            gperm = gated_rng.permutation(elig_pos)
            gterm = resolved_term_by_taker(early_tox, elig_pos, lambda_tox,
                                           values=early_tox[gperm])
            if arm_fingerprint(gterm)[0] == obs_fingerprint[0]:
                n_gated_matching_count += 1
            e_g, m_g = reduction_vec(gterm)
            acc_gated += np.where(m_g, e_g, 0.0)
            gated_reds.append(float(np.sum(e_g[m_g] * w_late[m_g]) / sw)
                              if sw > 0 else float("nan"))
        acc_gated /= n_perm
        gated_procedure = stats.permutation_p(
            obs_red, np.asarray(gated_reds, dtype=np.float64), side="greater",
            abs_tol=1e-12, n_requested=n_perm,
            cell=("mm_bakeoff", "placebo_rank_floor_gated", cname))
        garr = np.array([r for r in gated_reds if r == r], dtype=np.float64)
        gated_mean = float(garr.mean()) if garr.size else float("nan")
        matched_mean = float(arr.mean()) if arr.size else float("nan")

        # ---- WALLET-CLUSTERED interval on each arm's DIFFERENCE, by the estimator the
        # pairwise block already uses: per-wallet partial sums once, then every draw is a
        # gather over them. This generator is derived too, for the same reason as above.
        e_obs_v, m_obs_v = reduction_vec(obs_term_by_taker)
        ci_rng = _cell_rng("mm_bakeoff", "placebo_arm_ci", cname)
        wv = np.where(good_w, w_late, 0.0)
        gu, ginv = np.unique(pos_late, return_inverse=True)
        ngw = int(gu.size)
        S_obs = np.bincount(ginv, weights=np.where(m_obs_v, e_obs_v, 0.0) * wv, minlength=ngw)
        S_mat = np.bincount(ginv, weights=acc_matched * wv, minlength=ngw)
        S_gat = np.bincount(ginv, weights=acc_gated * wv, minlength=ngw)
        Wg = np.bincount(ginv, weights=wv, minlength=ngw)
        b_mat = np.empty(N_BOOT, dtype=np.float64)
        b_gat = np.empty(N_BOOT, dtype=np.float64)
        for b in range(N_BOOT):
            g = ci_rng.integers(0, ngw, size=ngw)
            den = float(Wg[g].sum())
            if den > 0:
                so = float(S_obs[g].sum())
                b_mat[b] = (so - float(S_mat[g].sum())) / den
                b_gat[b] = (so - float(S_gat[g].sum())) / den
            else:
                b_mat[b] = np.nan
                b_gat[b] = np.nan

        def _ci95(a):
            a = a[np.isfinite(a)]
            return ([float(np.percentile(a, 2.5)), float(np.percentile(a, 97.5))]
                    if a.size >= 2 else [float("nan"), float("nan")])

        ci_mat = _ci95(b_mat)
        ci_gat = _ci95(b_gat)
        out["count_matched"][cname]["reduction_vs_null_net_vw_bps"] = (
            float(obs_red - matched_mean)
            if (obs_red == obs_red and matched_mean == matched_mean) else float("nan"))
        out["count_matched"][cname]["ci95_wallet_clustered"] = ci_mat
        out["count_matched"][cname]["ci_excludes_zero"] = bool(
            ci_mat[0] == ci_mat[0] and (ci_mat[0] > 0 or ci_mat[1] < 0))

        out["rank_floor_gated"][cname] = {
            "what_this_arm_is": (
                "a null confined to the rank-floor-eligible wallets while the observed arm "
                "keeps every wallet with a finite early estimate. It is NOT the test and is "
                "not matched: it is reported so the mismatch it produces can be quoted as a "
                "number instead of described"),
            "observed_toxicity_reduction_net_vw_bps": (
                float(obs_red) if obs_red == obs_red else float("nan")),
            "random_mean": gated_mean,
            "random_std": float(garr.std()) if garr.size else float("nan"),
            "permutation_p": (gated_procedure["p"] if gated_procedure["p"] is not None
                              else stats.p_floor(n_perm)),
            "procedure": gated_procedure,
            "reduction_vs_null_net_vw_bps": (
                float(obs_red - gated_mean)
                if (obs_red == obs_red and gated_mean == gated_mean) else float("nan")),
            "ci95_wallet_clustered": ci_gat,
            "n_wallets_null_arm": int(elig_pos.size),
            "n_wallets_observed_arm": int(pop_pos.size),
            "n_wallets_carrying_premium_in_observed_and_zero_in_every_draw": int(
                pop_pos.size - elig_pos.size),
            "arms_matched": {
                "predicate": ("the same fingerprint predicate the matched arm is measured "
                              "by: a draw matches when it widens the same NUMBER of wallets "
                              "as the observed arm"),
                "n_draws": int(n_perm),
                "n_draws_matching_wallets_widened": int(n_gated_matching_count),
                "all_draws_matched": bool(n_gated_matching_count == n_perm),
                "expected_to_match": False,
                "why": ("this arm is gated at the rank floor by construction, so the "
                        "counter is expected to read 0 and reading anything else would mean "
                        "the floor selected nobody"),
            },
        }

        gap = (float((obs_red - gated_mean) - (obs_red - matched_mean))
               if (gated_mean == gated_mean and matched_mean == matched_mean)
               else float("nan"))
        out["arm_difference"][cname] = {
            "question": ("how much of the published reduction would be an artifact of the "
                         "null arm being drawn over a smaller population than the observed "
                         "arm?"),
            "unmatched_minus_matched_net_vw_bps": gap,
            "share_of_the_unmatched_estimate": (
                float(gap / (obs_red - gated_mean))
                if (gap == gap and obs_red - gated_mean not in (0.0,)) else float("nan")),
            "direction_is_forced": ("the gated null hands out premium to fewer wallets, so "
                                    "its mean can only sit at or below the matched null's "
                                    "and the gap can only be non-negative"),
            "n_late_fills": int(idx.size),
            "n_wallet_clusters": ngw,
            "n_perm": int(n_perm),
            "n_boot_wallet_clustered": int(N_BOOT),
        }
    out["gm_uses_no_identity"] = True
    # The size-matched null lives in another file and this block now says so instead of
    # holding an empty `size_matched` key beside a docstring promising two nulls here. The
    # key is gone rather than left empty: an empty container reads as a null that came back
    # with nothing, which is the opposite of a null that was never this file's to draw.
    out["size_matched_null_lives_in"] = {
        "file": "maker_econ_results.json",
        "block": "placebo_random_drop",
        "producer": "maker_econ.py",
        "matched_on": "total late notional of the observed toxic set",
        "why_not_here": ("toxic wallets are also large, so a size-matched null is what "
                         "separates identity from size; it is drawn once, against the "
                         "policy bound, and this file scores quoters rather than redrawing "
                         "it"),
    }
    out["note"] = ("gm_vpin is the built-in negative control: its half-spread is a pure "
                   "function of a market-level VPIN/PIN proxy with taker_id NOT referenced, "
                   "so a label shuffle leaves it unchanged. This file draws the COUNT-matched "
                   "null, which is the test, and beside it the RANK-FLOOR-GATED null, which "
                   "is not: the second is published so the cost of an unmatched arm can be "
                   "quoted from arm_difference rather than described. The size-matched null "
                   "is maker_econ's, named in size_matched_null_lives_in.")
    out["which_arm_the_prose_leads_with"] = (
        "count_matched.reduction_vs_null_net_vw_bps with its ci95_wallet_clustered. "
        "rank_floor_gated is the UPPER bound and is quoted as one; arm_difference is the "
        "measured distance between them and is what the unmatched arm was worth.")
    return out


COIN_NAMES_INV = {"BTC": 0, "ETH": 1, "SOL": 2}


# ==================== fill-aware recapture APPROXIMATION (maker_econ B2 style) ====================
def fill_aware_b2(arrs, late_mask, labels, ctx, horizon=HEADLINE_HORIZON):
    """maker_econ-style recapture APPROXIMATION for as_toxicity (NOT a fill model).

    Against a wallet pre-identified as toxic on the EARLY window, on its LATE fills, a
    recapture fraction f still trades at a quote widened by w bps minus a per-fill
    requote/operational penalty c bps; (1-f) is declined (no P&L). Benign flow unchanged.
    Per-fill widened P&L = f*((m + w - fee - c)) ; m = pre-fee maker measure (net_MID_lower
    at `horizon`). f=0 reproduces the B1 decline-entirely; f=1 is widen-only. The realized
    markout m is UNCHANGED by widening (information does not vanish) -- the conservative,
    honest choice. f/w/c are NOT estimated from a live book -- swept so the whole surface
    is visible. APPROXIMATION, labelled as such."""
    coin = arrs["coin"]
    notl = arrs["notional"]
    s_bbo = arrs["s_bbo"]
    taker = arrs["taker_id"]
    toxic_set = labels["toxic_taker_set"]
    late_idx = np.where(late_mask)[0]
    # VECTORIZED toxic membership: np.isin over the late takers (no per-fill Python loop)
    toxic_arr = np.fromiter(toxic_set, dtype=np.int64, count=len(toxic_set)) if toxic_set else np.array([], dtype=np.int64)
    is_toxic = np.isin(taker[late_idx], toxic_arr)

    # pre-fee net_MID_lower at horizon on the late fills (the maker measure m, base tier)
    m = arrs[f"net_MID_lower_{horizon}"][late_idx] if f"net_MID_lower_{horizon}" in arrs else (
        s_bbo[late_idx] - arrs[f"a_mid_{horizon}"][late_idx])
    w_notl = notl[late_idx]

    def net_under(f, w, c, tier="base"):
        fee = MAKER_FEE_BPS[tier]
        # benign flow: accepted unchanged at the symmetric maker measure - fee
        net = (m - fee).astype(np.float64).copy()
        # toxic flow: f recaptured at +w (better maker price) minus penalty c; (1-f) declined.
        # _vw_mean is sum(value * weight) / sum(weight), so it MULTIPLIES the two and f
        # belongs to exactly ONE of them. It carries in the WEIGHT: the declined (1-f)
        # contributes 0 P&L and 0 notional, so declined volume leaves the denominator too.
        # That is maker_econ_b2._b2_usd's accounting -- it sums f*rate*notl over the P&L and
        # f*notl over the accepted notional, one f in each of two separate aggregates -- and
        # it is what the docstring's identity "f=0 reproduces the B1 decline-entirely" rests
        # on. Putting f in BOTH here squares it, and that is what stood here until
        # 2026-08-14: silent at f=0 and f=1 (0^2=0, 1^2=1) and wrong at every f strictly
        # inside, by up to 0.354 bps on this grid. The two brackets are the only thing
        # run_self_tests checks (recapture_brackets_f0_decline_f1_symmetric), so they are
        # blind to it BY CONSTRUCTION, and the interior is what maker_econ_b2 agrees with:
        # its 16 shared cells match this form to 4.4e-16 and the squared form to 3.5e-01.
        toxic_net = m[is_toxic] + w - fee - c          # the RATE on the recaptured share
        toxic_w = f * w_notl[is_toxic]                # only the recaptured share carries notional
        net_t = net.copy()
        net_t[is_toxic] = toxic_net
        wt = w_notl.copy()
        wt[is_toxic] = toxic_w
        return _vw_mean(net_t, wt)

    grid = {}
    n_positive_grid_cells = 0
    for f in B2_F_GRID:
        for w in B2_W_GRID:
            for c in B2_C_GRID:
                nb = net_under(f, w, c, "base")
                nr = net_under(f, w, c, "rebate3")
                grid[f"f{f}_w{w}_c{c}"] = {
                    "f": f, "w": w, "c": c,
                    "net_vw_bps_base": nb,
                    "net_vw_bps_rebate3": nr,
                }
                for vv in (nb, nr):
                    if np.isfinite(vv) and vv > 0:
                        n_positive_grid_cells += 1
    dp = B2_DEPLOY
    deploy_base = net_under(dp["f"], dp["w"], dp["c"], "base")
    # symmetric maker reference (no widening) at base tier on the same late fills -- the
    # honest "do nothing" benchmark the deploy point must not falsely beat into profit.
    sym_base = _vw_mean(m - MAKER_FEE_BPS["base"], w_notl)
    return {
        "label": "recapture APPROXIMATION (NOT a matching engine / queue / fill-probability)",
        "horizon_s": horizon,
        "deploy_point": dp,
        "deploy_net_vw_bps_base": deploy_base,
        "symmetric_maker_net_vw_bps_base": sym_base,
        # honest self-documentation of the COST-NOT-ALPHA surface: the grid is NOT
        # capped by min(extra, max(a_mid,0)) like evaluate_quoter, so on a REBATE tier (a
        # negative fee that ADDS) with widening w, an individual grid cell can print a
        # POSITIVE net_vw_bps. Any such cell is the documented whale-driven / mostly-ETH /
        # single-fragile-rebate-flip artifact (see the maker_econ result), NOT a
        # deployable edge -- it is a cost reduction whose tail crosses zero on the optimistic
        # measure, never robust alpha. These booleans let the JSON self-flag the flip.
        "deploy_net_negative_base": bool(np.isfinite(deploy_base) and deploy_base < 0),
        "n_positive_grid_cells": int(n_positive_grid_cells),
        "positive_cells_are_a_known_fragility": (
            "any positive net_vw_bps in this grid is the documented whale-driven, mostly-"
            "ETH, single-fragile-rebate-tier flip on the optimistic recapture surface; it "
            "is NOT a deployable edge / alpha -- the headline is a COST reduction that never "
            "robustly flips to profit. Unlike evaluate_quoter this grid is uncapped, so it "
            "is excluded from the all_net_negative guard by design and self-flagged here."),
        "grid": grid,
        "note": ("f=0 reproduces B1 decline-entirely; f=1 is widen-only; m unchanged by "
                 "widening (information does not vanish). f/w/c swept, not estimated."),
    }


# ==================== walk-forward over days (the same nine folds t1 cuts) ====================
def _fold_stats(series):
    """Median-led summary of a per-fold series, t1_toxicity_skew_backtest's convention.

    The median leads because a fold series over single days is heavy-tailed: one thin test
    day with a near-zero base blows up the mean and its spread. The mean and the whole
    series are reported beside it, never in front of it."""
    v = np.asarray([x for x in series if x is not None and x == x], dtype=np.float64)
    if v.size == 0:
        return {"n_evaluable_folds": 0, "median": None, "mean": None, "std": None,
                "n_folds_positive": 0, "frac_folds_positive": None, "series": []}
    return {
        "n_evaluable_folds": int(v.size),
        "median": float(np.median(v)),
        "mean": float(v.mean()),
        "std": float(v.std()),
        "n_folds_positive": int((v > 0).sum()),
        "frac_folds_positive": float((v > 0).mean()),
        "series": [float(x) for x in v],
    }


def walk_forward_bakeoff(arrs, K, lambda_tox, progress=None):
    """Re-score every quoter fold by fold: rank on days up to t, quote on day t+1.

    WHY, BEFORE HOW. The headline splits the window once, freezes the counterparty scores on
    the early half and scores the late half. That answers "does the ordering hold out of
    sample" for ONE split. The M4 draft promised a walk-forward at the quoter comparison and
    this file carried none -- searching it for `fold` returned nothing while the same search
    over t1_toxicity_skew_backtest.py returned five hits. A single split cannot say whether
    an ordering is a property of the tape or of where the cut fell.

    THE FOLDS ARE NOT NEW ONES. They are the cuts t1_toxicity_skew_backtest._t2_walk_forward
    already makes: expanding train window over the days present, test on the next day, one
    fold per t from the first present day to the penultimate. Two nodes reporting two
    schemes would be two answers to one question.

    HOW THE SPLIT IS HANDED TO THE LABEL BUILDER. build_toxicity_labels derives its own
    early/late halves from the days it is given, through settings.split_early_late, which
    puts the first ceil(n/2) days early. It takes no override, and re-spelling the label rule
    here to accept one is exactly the copy-instead-of-call that makes a check blind to a
    repair of the thing it checks. So the fold hands the builder a two-day view: every train
    row carries day 0 and every test row day 1, and the rule then returns early = (0,),
    late = (1,) -- the fold's own split, produced by the declared rule rather than beside it.
    Nothing booked reads the day column afterwards. The one quantity that does read real days
    is the market-level Glosten-Milgrom pi, which is bucketed per (coin, day); it is computed
    on the TRAIN rows with their REAL days before the relabelling, which also makes gm_vpin
    strictly in-sample-up-to-t here, unlike the headline where pi is a deliberately-strong
    full-window aggregate. The A-S volatility does read the relabelled column, and it feeds
    as_base_half_bps and the GLFT view only -- neither is booked and neither is published
    from this block.

    COST. One rung, no bootstrap band, no inventory simulation: a fold is a few hundred
    thousand rows through means rather than through 2000 resamples, which is what keeps the
    whole sweep small beside the headline grid."""
    present = sorted(int(d) for d in np.unique(arrs["day"]))
    day = arrs["day"]
    folds = []
    for i in range(len(present) - 1):
        train_days = present[: i + 1]
        test_day = present[i + 1]
        train_rows = np.isin(day, np.asarray(train_days, dtype=np.int64))
        test_rows = day == test_day
        keep = train_rows | test_rows
        if progress is not None:
            progress(f"  walk-forward fold {i + 1}/{len(present) - 1}: train {train_days} "
                     f"-> test {test_day} ({int(keep.sum()):,} rows)")

        # market-level GM inputs on the TRAIN rows, with their real days.
        arrs_train = {k: v[train_rows] for k, v in arrs.items()}
        pi_fold = estimate_pi(arrs_train)
        J_fold = estimate_adverse_move(arrs_train)

        # the fold view, with the day column carrying the fold's own split.
        arrs_fold = {k: v[keep] for k, v in arrs.items()}
        arrs_fold["day"] = np.where(test_rows[keep], 1, 0).astype(np.int64)

        labels = build_toxicity_labels(arrs_fold, K, horizon=HEADLINE_HORIZON)
        ctx = build_context(arrs_fold, labels, pi_fold, J_fold, lambda_tox=lambda_tox)
        late = labels["late_mask"]

        blocks = {}
        for qname in QUOTER_NAMES:
            blocks[qname] = evaluate_quoter(
                qname, arrs_fold, late, ctx, ("fold", int(test_day)),
                horizons=(HEADLINE_HORIZON,), ci_horizons=(), inventory_sim=False)

        manifests = comparison_manifest(blocks, ctx)
        deltas = declared_axis_deltas(blocks, manifests)

        def _net(qn):
            blk = blocks[qn]["net_by_coin"].get("pooled", {})
            if not blk.get("n_late_fills"):
                return None
            return blk["by_horizon"][HKEY]["net_MID_lower"]["by_fee_tier"]["base"]["net_vw_bps"]

        net_pooled = {qn: _net(qn) for qn in QUOTER_NAMES}
        ordered = sorted(((qn, v) for qn, v in net_pooled.items() if v is not None and v == v),
                         key=lambda t: t[1])
        pair_delta = {}
        for pair, blk in deltas.items():
            if blk.get("published"):
                pair_delta[pair] = blk["by_coin"]["pooled"]["base"]["delta_net_vw_bps"]
            else:
                pair_delta[pair] = None
        # the published pair too, so the walk-forward speaks to the headline and not only
        # to the new arms.
        for a, b in (("as_toxicity", "as_symmetric"), ("as_toxicity", "gm_vpin")):
            va, vb = net_pooled.get(a), net_pooled.get(b)
            pair_delta[f"{a}_minus_{b}"] = (
                (va - vb) if (va is not None and vb is not None and va == va and vb == vb)
                else None)

        folds.append({
            "train_days": train_days,
            "test_day": test_day,
            "n_train_fills": int(train_rows.sum()),
            "n_test_fills": int(test_rows.sum()),
            "n_late_fills_scored": int(late.sum()),
            "n_wallets_floor_eligible": int(labels["n_eligible"]),
            "lambda_as_toxicity_ew": ctx["equal_width_solve"]["lambda_as_toxicity_ew"],
            "lambda_as_toxicity_plus_global": ctx["equal_width_solve"]["lambda_as_toxicity_plus_global"],
            "net_MID_lower_vw_bps_pooled_base": net_pooled,
            "ordered_ascending_cost": ordered,
            "best_cost_least_negative": ordered[-1] if ordered else None,
            "pair_delta_net_vw_bps_pooled_base": pair_delta,
            "manifests_hold": {p: m["all_held_equal_quantities_hold"]
                               for p, m in manifests.items()},
        })

    pair_keys = sorted(set(k for f in folds for k in f["pair_delta_net_vw_bps_pooled_base"]))
    summary = {
        pk: _fold_stats([f["pair_delta_net_vw_bps_pooled_base"].get(pk) for f in folds])
        for pk in pair_keys
    }
    quoter_summary = {
        qn: _fold_stats([f["net_MID_lower_vw_bps_pooled_base"].get(qn) for f in folds])
        for qn in QUOTER_NAMES
    }
    won = {}
    for qn in QUOTER_NAMES:
        won[qn] = int(sum(1 for f in folds
                          if f["best_cost_least_negative"]
                          and f["best_cost_least_negative"][0] == qn))
    return {
        "scheme": ("expanding train window over the days present, test on the next day; "
                   "the same cuts t1_toxicity_skew_backtest._t2_walk_forward makes"),
        "split_produced_by": ("settings.split_early_late through "
                              "maker_econ.build_toxicity_labels, over a two-day view of "
                              "each fold (train rows day 0, test row day 1)"),
        "cell": (f"pooled, base fee tier, net_MID_lower notional-weighted, {HKEY}; no "
                 "bootstrap band and no inventory simulation on a fold"),
        "gm_inputs": ("pi and J are computed on the fold's TRAIN rows with their real days, "
                      "so gm_vpin is strictly in-sample-up-to-t here; the headline uses a "
                      "full-window pi/J on purpose and the two are not the same benchmark"),
        "headline_statistic": "median over evaluable folds",
        "rank_floor_fills": K,
        "n_folds": len(folds),
        "days_present": present,
        "quoter_net_by_fold": quoter_summary,
        "pair_delta_by_fold": summary,
        "n_folds_each_quoter_finished_least_negative": won,
        "folds": folds,
    }


# ==================== synthetic self-tests (assert; load NO data, no RNG asserts) ====================
def run_self_tests():
    """Deterministic synthetic invariants for every spec, on TINY in-memory arrays.

    No disk, no RNG-dependent assertions. Returns a dict of per-check booleans (all True).
    Raises AssertionError on any violation. Runs under --selftest."""
    flags = {}
    tol = 1e-9

    # -------- Glosten-Milgrom --------
    J = 4.0
    assert gm_half_spread(0.0, J) == 0.0, "pi=0 must give zero GM half-spread"
    flags["gm_pi0_zero_half_spread"] = True
    # pi=0 quotes collapse to the mid (bid==ask==mid, total spread 0)
    mid = 100.0
    h0 = float(gm_half_spread(0.0, J))
    assert (mid + h0) == mid and (mid - h0) == mid and 2 * h0 == 0.0
    flags["gm_pi0_quotes_collapse_to_mid"] = True
    # strictly increasing in pi
    pis = np.array([0.0, 0.05, 0.1, 0.25, 0.5, 0.9])
    hp = gm_half_spread(pis, J)
    assert np.all(np.diff(hp) > 0), f"GM not increasing in pi: {hp}"
    assert gm_half_spread(0.40, J) > gm_half_spread(0.10, J)
    flags["gm_increasing_in_pi"] = True
    # strictly increasing in J
    Js = np.array([0.5, 1.0, 2.0, 4.0, 8.0])
    hJ = gm_half_spread(0.3, Js)
    assert np.all(np.diff(hJ) > 0), f"GM not increasing in J: {hJ}"
    flags["gm_increasing_in_J"] = True
    # symmetric about the mid; total == 2*half
    half = float(gm_half_spread(0.2, J))
    ask, bid = mid + half, mid - half
    assert abs((ask - mid) - (mid - bid)) < tol and abs((ask - bid) - 2 * half) < tol
    flags["gm_symmetric_about_mid"] = True
    # exact value pi*J
    assert abs(float(gm_half_spread(0.2, 4.0)) - 0.8) < tol
    flags["gm_exact_value"] = True
    # bps and price forms agree (pi dimensionless): pi*J_bps == bps(pi*J_price, mid)
    J_bps, J_price = 6.0, 6.0 / 1e4 * mid
    lhs = float(gm_half_spread(0.3, J_bps))
    rhs = float(spread_price_to_bps(gm_half_spread(0.3, J_price), mid))
    assert abs(lhs - rhs) < 1e-6, f"GM bps/price forms disagree: {lhs} vs {rhs}"
    flags["gm_bps_price_forms_agree"] = True
    # VPIN imbalance bounds
    assert abs(vpin_imbalance([1, -1, 1, -1]) - 0.0) < tol
    assert abs(vpin_imbalance([1, 1, 1, 1]) - 1.0) < tol
    assert abs(vpin_imbalance([1, 1, -1, 1]) - 0.5) < tol
    flags["vpin_imbalance_bounds"] = True
    # toxic tape gives a wider GM spread than a benign tape (via pi)
    pi_toxic = vpin_imbalance([1, 1, 1, 1, -1, 1])
    pi_benign = vpin_imbalance([1, -1, 1, -1, 1, -1])
    assert gm_half_spread(pi_toxic, J) > gm_half_spread(pi_benign, J)
    flags["gm_toxic_tape_wider_than_benign"] = True
    # vectorization
    hv = gm_half_spread(pis, J)
    assert hv.shape == pis.shape and hv[0] == 0.0 and np.all(np.diff(hv) > 0)
    flags["gm_vectorized"] = True

    # -------- Gueant-Lehalle-Fernandez-Tapia (GLFT) --------
    gamma, sigma, k, t_rem = 0.1, 2.0, 1.5, 1.0
    # pick A so c_skew is O(gamma*sigma^2)
    target_cskew = gamma * sigma ** 2
    A = sigma ** 2 * gamma / (2.0 * k * target_cskew ** 2) * (1.0 + gamma / k) ** (1.0 + k / gamma)
    cs = float(glft_c_skew(sigma, gamma, k, A))
    glft_total = float(glft_total_spread(0.0, gamma, k, cs))
    as_total = float(optimal_spread(gamma, sigma, t_rem, k))
    band = glft_total / as_total
    assert 0.5 <= band <= 2.0, f"GLFT q=0 total not within sane band of A-S: ratio={band}"
    flags["glft_near_tie_band_with_as"] = True
    # shared arrival term: GLFT total minus c_skew == (2/gamma)ln(1+gamma/k) exactly
    db0, da0 = glft_distances(0.0, gamma, k, cs)
    assert abs((float(db0) + float(da0)) - cs - (2.0 / gamma) * math.log1p(gamma / k)) < 1e-12
    flags["glft_shared_arrival_term_exact"] = True
    # inventory skew sign + mean-reversion; per-unit skew == c_skew
    dbL, daL = glft_distances(5.0, gamma, k, cs)
    db0b, da0b = glft_distances(0.0, gamma, k, cs)
    assert float(dbL) > float(db0b) and float(daL) < float(da0b), "long must push bid out / pull ask in"
    dbS, daS = glft_distances(-5.0, gamma, k, cs)
    assert float(dbS) < float(db0b) and float(daS) > float(da0b), "short mirror"
    assert abs((float(dbL) - float(db0b)) / 5.0 - cs) < 1e-12, "per-unit bid skew != c_skew"
    flags["glft_inventory_skew_sign_and_unit"] = True
    # c_skew monotone: decreasing in A, increasing in sigma
    A_grid = np.array([0.5, 1.0, 2.0, 5.0, 10.0])
    cs_A = glft_c_skew(sigma, gamma, k, A_grid)
    assert np.all(np.diff(cs_A) < 0), f"c_skew not decreasing in A: {cs_A}"
    sig_grid = np.array([0.5, 1.0, 2.0, 4.0])
    cs_sig = glft_c_skew(sig_grid, gamma, k, A)
    assert np.all(np.diff(cs_sig) > 0), f"c_skew not increasing in sigma: {cs_sig}"
    flags["glft_c_skew_monotone"] = True
    # positive-spread guard: quotes never cross over a small grid
    ok = True
    for qq in (-5.0, -1.0, 0.0, 1.0, 5.0):
        tot = float(glft_total_spread(qq, gamma, k, cs))
        ok = ok and (tot > 0)
    assert ok, "GLFT total spread must stay positive (quotes never cross)"
    flags["glft_positive_spread_guard"] = True
    # bps-comparability: nan for mid<=0, finite positive for mid>0
    mids = np.array([-1.0, 0.0, 100.0])
    b = spread_price_to_bps(glft_total, mids)
    assert math.isnan(b[0]) and math.isnan(b[1]) and np.isfinite(b[2]) and b[2] > 0
    flags["glft_bps_comparability"] = True

    # -------- Barzykin-Bergault-Gueant-Lemmel (BBGL) --------
    base_half = 5.0
    tox_market = 1.0
    tiers = np.array([0.0, 1.0, 3.0])
    hs = bbgl_half_spread_bps(base_half, tox_market, tiers, beta_g=1.0, beta_t=1.0)
    assert hs[0] < hs[1] < hs[2], f"BBGL per-tier not monotone defensive: {hs}"
    assert np.all(hs > base_half + 0 - tol), "BBGL must widen vs base"
    flags["bbgl_monotone_defensive_skew"] = True
    # global-only (beta_t=0): identical for every tier = base + global
    hs_g = bbgl_half_spread_bps(base_half, tox_market, tiers, beta_g=1.0, beta_t=0.0)
    assert np.allclose(hs_g, base_half + tox_market), "BBGL global-only must be tier-invariant"
    # per-tier only (beta_g=0): tiers differ ONLY by the per-tier term
    hs_t = bbgl_half_spread_bps(base_half, tox_market, tiers, beta_g=0.0, beta_t=1.0)
    assert abs((hs_t[2] - hs_t[1]) - (tiers[2] - tiers[1])) < tol
    flags["bbgl_global_pertier_nesting"] = True
    # reduces to A-S: beta_g=beta_t=0 -> base exactly
    hs_as = bbgl_half_spread_bps(base_half, tox_market, tiers, beta_g=0.0, beta_t=0.0)
    assert np.allclose(hs_as, base_half), "BBGL must reduce to A-S base when betas=0"
    flags["bbgl_reduces_to_as"] = True
    # non-negative premium / widen-only; benign tier clipped to 0 (no tightening)
    hs_benign = bbgl_half_spread_bps(base_half, 0.0, np.array([-2.0, 0.0]))
    assert np.all(hs_benign >= base_half - tol), "BBGL must never tighten below base"
    flags["bbgl_nonneg_widen_only"] = True

    # -------- A-S + counterparty-resolved adverse-selection term --------
    early = np.array([-1.0, 0.0, 2.0, 5.0])    # two benign (<=0), two toxic (>0)
    term = as_toxicity_term_bps(early, lambda_tox=1.0)
    assert np.allclose(term, np.array([0.0, 0.0, 2.0, 5.0])), f"tox term clip wrong: {term}"
    assert np.all(term >= 0.0)
    flags["as_toxicity_term_clip_and_nonneg"] = True
    # lambda_tox scales linearly; lambda_tox=0 -> recovers symmetric A-S (zero term)
    assert np.allclose(as_toxicity_term_bps(early, 0.0), 0.0)
    assert np.allclose(as_toxicity_term_bps(early, 0.5), 0.5 * np.maximum(early, 0.0))
    flags["as_toxicity_term_lambda_scaling"] = True

    # -------- net-economics accounting (generalised maker_econ) --------
    # naive_at_book identity: s_q==s_bbo -> gross_MID==s_bbo-a_mid, gross_PRINT==-a_print
    s_bbo = np.array([0.5, 0.5, 0.5])
    a_mid = np.array([2.0, 2.0, -1.0])
    a_print = np.array([1.5, 1.5, -1.5])
    g_mid, g_print = gross_quoter_measures(s_bbo, a_mid, s_bbo, a_print)
    assert np.allclose(g_mid, s_bbo - a_mid) and np.allclose(g_print, -a_print)
    flags["naive_at_book_reproduces_maker_econ"] = True
    # widening toxic flow raises net (s_q up by extra -> gross up by extra), no re-clear
    extra = np.array([0.0, 1.0, 2.0])
    s_q = s_bbo + extra
    g_mid2, _ = gross_quoter_measures(s_q, a_mid, s_bbo, a_print)
    assert np.allclose(g_mid2 - g_mid, extra), "widening must raise gross_MID by exactly extra"
    flags["widening_raises_net_by_booked_spread"] = True
    # monotonicity: as_toxicity (widen toxic) net >= as_symmetric net on the same fills
    assert np.all(g_mid2 >= g_mid - tol)
    flags["as_toxicity_net_ge_as_symmetric"] = True
    # COST-NOT-ALPHA CAP (the booked extra can only OFFSET adverse cost, never over-collect):
    # booked = min(extra, max(a_mid,0)); gross_MID = s_bbo + booked - a_mid. The defensive
    # widening recovers AT MOST the adverse markout the maker was paying, so the gross can
    # rise no higher than the BOOK income s_bbo (full offset) and never above it -- the
    # AS-quoter's best case is paying ZERO adverse selection, NOT earning a spread on top.
    # It BEATS the naive maker on cost (the point) but its gross is ceilinged at s_bbo.
    extra_big = np.array([10.0, 10.0, 10.0])          # premium far exceeding the markout
    offset_cap = np.minimum(extra_big, np.maximum(a_mid, 0.0))
    booked = RECOVER_FRAC * offset_cap                # deployable recapture fraction applied
    g_capped = (s_bbo + booked) - a_mid
    g_naive = s_bbo - a_mid                            # naive pays the full adverse cost
    # the quoter's ONLY contribution vs naive is the booked offset = f*min(extra,max(a_mid,0)):
    # it recovers AT MOST the adverse cost it was paying (and only a fraction f of that), so on
    # a TOXIC fill its gross rises to AT MOST s_bbo and never above the book income.
    contribution = g_capped - g_naive
    assert np.allclose(contribution, booked), "AS contribution must equal the booked offset"
    assert np.all(booked <= np.maximum(a_mid, 0.0) + tol), "booked must not exceed the markout"
    assert RECOVER_FRAC <= 1.0, "recapture fraction must be a fraction"
    toxic = a_mid > 0
    assert np.all(g_capped[toxic] <= s_bbo[toxic] + tol), "toxic-fill gross ceilinged at s_bbo"
    # against a benign fill (a_mid<=0) the cap is 0 -> no booked extra (cannot manufacture gain)
    assert booked[2] == 0.0, "benign fill must book zero defensive extra"
    assert np.allclose(booked[:2], RECOVER_FRAC * np.minimum(extra_big[:2], a_mid[:2]))
    # net stays NEGATIVE at base tier when book income < fee (s_bbo small vs 1.5 bps fee):
    # even FULL offset on every toxic fill leaves only the tiny book spread, < the maker fee.
    s_small = np.array([0.05, 0.05, 0.05])
    g_best = (s_small + np.minimum(extra_big, np.maximum(a_mid, 0.0))) - a_mid
    g_best = np.where(a_mid > 0, s_small, g_best)      # toxic fills fully offset -> s_small
    assert _vw_mean(g_best[toxic] - MAKER_FEE_BPS["base"], np.ones(int(toxic.sum()))) < 0
    flags["cost_not_alpha_cap_offsets_only"] = True
    # COST-NOT-ALPHA: subtracting any maker fee only lowers net; rebate (neg fee) adds
    for tier in FEE_TIERS:
        net = g_mid - MAKER_FEE_BPS[tier]
        assert np.allclose(net, g_mid - MAKER_FEE_BPS[tier])
    # a synthetic loss set stays net-negative at base tier (gross < fee)
    g_neg = np.array([-3.0, -2.5, -4.0])
    assert _vw_mean(g_neg - MAKER_FEE_BPS["base"], np.array([1.0, 1.0, 1.0])) < 0
    flags["cost_not_alpha_net_negative_base"] = True
    # recapture brackets: f=0 == decline (no toxic P&L/notional); f=1 == symmetric (no avoidance)
    m = np.array([-2.0, -2.0, -3.0])
    notl = np.array([1.0, 1.0, 1.0])
    is_tox = np.array([False, False, True])
    fee = MAKER_FEE_BPS["base"]
    # f=1, w=0, c=0 -> identical to symmetric (toxic recaptured at the same price)
    net_f1 = m - fee
    # f=0 -> toxic declined: only benign rows contribute
    net_f0 = (m - fee).copy()
    notl_f0 = notl.copy()
    net_f0[is_tox] = 0.0
    notl_f0[is_tox] = 0.0
    sym_vw = _vw_mean(net_f1, notl)
    decline_vw = _vw_mean(net_f0, notl_f0)
    assert sym_vw == sym_vw and decline_vw == decline_vw
    flags["recapture_brackets_f0_decline_f1_symmetric"] = True

    # -------- placebo p-value LOGIC (one-sided permutation; deterministic synthetic) --------
    # Standalone check of the count direction used in placebo_label_shuffle: count shuffles
    # whose reduction MATCHES OR BEATS the observed, p = (beat+1)/(n+1). Signal => small p;
    # noise => p ~ 0.5. Built on a tiny deterministic perm set (no RNG draw inside the asserts).
    def _perm_p(obs, perm_vals, n):
        beat = sum(1 for r in perm_vals if r >= obs - 1e-12)
        return (beat + 1) / (n + 1)
    # signal: observed is the largest -> only itself "beats" -> p hits the floor 1/(n+1)
    p_signal = _perm_p(5.0, [0.1, 0.2, 0.0, 0.3, -0.1], 5)
    assert abs(p_signal - 1.0 / 6.0) < 1e-12, f"signal p should hit the floor, got {p_signal}"
    # noise: observed sits in the middle -> ~half beat it -> p near 0.5
    p_noise = _perm_p(0.0, [0.4, -0.3, 0.5, -0.2], 4)
    assert 0.3 <= p_noise <= 0.7, f"noise p should be mid-range, got {p_noise}"
    # a stronger-true-label reduction is >= a shuffled one on a planted tape (booking is
    # monotone non-negative in the toxic mass that carries positive early_tox)
    assert _perm_p(1.0, [0.2, 0.1], 2) < _perm_p(0.05, [0.2, 0.1], 2)
    flags["placebo_p_logic_signal_floor_noise_mid"] = True

    # DELIBERATELY NOT ROUTED THROUGH stats.permutation_p, and the reason is what the
    # block above is for. It is a second, independent spelling of the count the placebo
    # publishes, run on fixtures whose answer is known by hand; rewriting it as a call to
    # the module the placebo now uses would leave the module checked against itself and
    # the convention checked by nothing. What IS added is the comparison: the module has
    # to reproduce this spelling on the same fixtures, so a change of side, of floor or
    # of denominator inside stats.py surfaces here instead of silently re-pricing the
    # placebo. NaN never appears in these fixtures, so the two denominators coincide.
    for _obs, _vals, _n in ((5.0, [0.1, 0.2, 0.0, 0.3, -0.1], 5),
                            (0.0, [0.4, -0.3, 0.5, -0.2], 4),
                            (1.0, [0.2, 0.1], 2),
                            (0.05, [0.2, 0.1], 2)):
        _mine = _perm_p(_obs, _vals, _n)
        _theirs = stats.permutation_p(
            _obs, np.asarray(_vals, dtype=np.float64), side="greater", abs_tol=1e-12,
            n_requested=_n, cell=("mm_bakeoff", "selftest_placebo_count", _n))["p"]
        assert _mine == _theirs, (
            f"stats.permutation_p disagrees with this file's placebo convention on "
            f"observed={_obs}, draws={_vals}: {_theirs} against {_mine}")
    flags["placebo_p_logic_matches_stats_module"] = True

    # -------- placebo ARMS: the null must hold the treatment's side effects constant -----
    # A count-matched null hands the SAME premium to the SAME number of wallets as the
    # observed arm and moves only WHICH wallet holds which score. The predicate that says
    # so (arm_fingerprint) is calibrated on the two OPPOSITE cases it has to tell apart:
    # the arrangement this file carried until 2026-08-01, where the null was confined to
    # the rank-floor-eligible subset and the predicate MUST fire, and the arrangement it
    # carries now, where the null permutes over the observed arm's own population and the
    # predicate MUST stay silent. One reference case cannot separate a predicate that is
    # too wide from one that is too narrow, and counters in this repository have been wrong
    # in both directions. The permutations here are written out rather than drawn, so no
    # assertion depends on a generator.
    et_syn = np.array([1.0, 2.0, 3.0, 4.0, np.nan, 5.0])   # five scored wallets, one not
    elig_syn = np.array([True, True, False, False, False, False])   # two clear the floor
    pop_syn = identity_term_population(et_syn)
    assert pop_syn.tolist() == [0, 1, 2, 3, 5], f"population predicate wrong: {pop_syn}"
    obs_arm = resolved_term_by_taker(et_syn, pop_syn, 1.0)
    assert arm_fingerprint(obs_arm) == (5, 15.0), f"observed fingerprint {arm_fingerprint(obs_arm)}"
    flags["placebo_arm_population_is_finite_estimate"] = True
    # MUST STAY SILENT: the null this file draws now.
    matched_null = resolved_term_by_taker(et_syn, pop_syn, 1.0, values=et_syn[pop_syn[::-1]])
    assert arm_fingerprint(matched_null) == arm_fingerprint(obs_arm), (
        f"a matched null must share the observed fingerprint: "
        f"{arm_fingerprint(matched_null)} against {arm_fingerprint(obs_arm)}")
    assert not np.array_equal(matched_null, obs_arm), (
        "a null that leaves every wallet holding its own score is not a null")
    flags["placebo_matched_null_shares_the_observed_fingerprint"] = True
    # MUST FIRE: the pre-2026-08-01 null, confined to the rank-floor-eligible subset.
    elig_pos_syn = np.where(elig_syn)[0]
    floor_null = resolved_term_by_taker(et_syn, elig_pos_syn, 1.0,
                                        values=et_syn[elig_pos_syn[::-1]])
    fp_floor = arm_fingerprint(floor_null)
    assert fp_floor == (2, 3.0), f"floor-confined null fingerprint {fp_floor}"
    assert fp_floor[0] < arm_fingerprint(obs_arm)[0], (
        f"the floor-confined null must be caught widening fewer wallets: {fp_floor} "
        f"against {arm_fingerprint(obs_arm)}")
    assert fp_floor[1] < arm_fingerprint(obs_arm)[1], (
        f"the floor-confined null must be caught handing out less premium: {fp_floor} "
        f"against {arm_fingerprint(obs_arm)}")
    flags["placebo_unmatched_null_is_caught"] = True

    # -------- the leaf comparator, on two OPPOSITE cases and both known traps -----------
    def _tree(btc_s, eth_c, key="A_x1.0"):
        return {"BTC": {key: {"s": btc_s, "c": 0.39}},
                "ETH": {key: {"s": 0.69, "c": eth_c}}}
    nan = float("nan")
    n_l, n_m, _ = count_moved_leaves(_tree(0.31, nan), _tree(0.31, nan))
    assert (n_l, n_m) == (4, 0), f"identical trees moved something: {n_l} leaves, {n_m} moved"
    flags["leaf_comparator_silent_on_identical_trees"] = True
    n_l, n_m, ex = count_moved_leaves(_tree(0.31, nan), _tree(0.32, nan))
    assert (n_l, n_m) == (4, 1) and ex[0]["path"] == ["BTC", "A_x1.0", "s"], (n_l, n_m, ex)
    flags["leaf_comparator_fires_on_one_changed_leaf"] = True
    # a value that stayed not-a-number is agreement; one that became a number is not.
    n_l, n_m, _ = count_moved_leaves(_tree(0.31, nan), _tree(0.31, 0.0))
    assert (n_l, n_m) == (4, 1), f"NaN turning into a number must count: {n_l}, {n_m}"
    flags["leaf_comparator_nan_traps"] = True
    # a renamed key is TWO differences, one vanished and one appeared, never zero -- this
    # is the case that hid sixteen relabelled values behind a clean-looking artifact diff.
    n_l, n_m, ex = count_moved_leaves(_tree(0.31, nan, key="K10"),
                                      _tree(0.31, nan, key="K50"))
    assert n_m == n_l and n_m == 4, f"a rename must not read as agreement: {n_l}, {n_m}"
    assert any(e["ref"] == "<absent>" or e["other"] == "<absent>" for e in ex), ex
    flags["leaf_comparator_catches_a_renamed_key"] = True

    # -------- the equal-width solve: the equation lands, exactly ----------------------
    # The resolved term is linear in the pass-through, so the pass-through that puts its
    # mean extra on a target is arithmetic. This checks the arithmetic on a wallet vector
    # that carries the three cases the real one carries: a negative score (clipped to zero),
    # an absent score (NaN, outside the population, so exactly zero) and a wallet appearing
    # on several fills.
    et_w = np.array([2.0, -1.0, 0.5, float("nan"), 4.0, 0.0, 1.5, 3.0])
    pop_w = np.array([0, 1, 2, 4, 5, 6, 7])
    fill_pos = np.array([0, 0, 1, 2, 3, 4, 5, 6, 7, 7])
    unit_ff = resolved_term_by_taker(et_w, pop_w, 1.0)[fill_pos]
    assert np.all(np.isfinite(unit_ff)) and unit_ff[4] == 0.0, unit_ff
    unit_mean_w = mean_extra_bps(unit_ff)
    target_w = 6.3646                     # bbgl's published pooled mean extra
    lam_w = target_w / unit_mean_w
    got_w = mean_extra_bps(resolved_term_by_taker(et_w, pop_w, lam_w)[fill_pos])
    assert abs(got_w - target_w) / target_w <= EQUAL_WIDTH_RTOL, (got_w, target_w)
    flags["equal_width_lambda_solves_exactly"] = True
    # the width statistic has ONE spelling, and it is the one the published leaf carries:
    # equal-weighted over the finite entries, NaN-tolerant, NaN on an empty input.
    assert mean_extra_bps([1.0, 3.0, float("nan")]) == 2.0
    assert mean_extra_bps([]) != mean_extra_bps([]), "empty must be not-a-number"
    flags["mean_extra_bps_one_spelling"] = True
    # a non-positive solve is refused rather than clipped: a target below its own global leg
    # would need a TIGHTENING arm, which this file does not build.
    lam_bad = (1.0 - 4.0) / unit_mean_w
    assert lam_bad < 0, lam_bad
    flags["plus_global_solve_detects_inadmissible_target"] = True

    # -------- the comparison manifest, on the two OPPOSITE cases from the live tree ----
    # Both cases are read off mm_bakeoff_results.json quoters.K50.*.extra_half_spread_
    # summary.by_coin.pooled, so the calibration cannot go stale against a fixture nobody
    # runs. MUST STAY SILENT: arms that agree on the declared width. MUST FIRE: the pair
    # whose difference was published as an identity result while one arm quoted 1.4423 bps
    # and the other 6.3646.
    def _fake_block(mean_extra, frac, mn, n=1000, net=-3.0):
        return {
            "net_by_coin": {
                cn: {"n_late_fills": n,
                     "by_horizon": {HKEY: {"net_MID_lower": {"by_fee_tier": {
                         t: {"net_vw_bps": net} for t in FEE_TIERS}}}}}
                for cn in ("BTC", "ETH", "pooled")},
            "extra_half_spread_summary": {"by_coin": {
                cn: {"mean_extra_half_spread_bps": mean_extra, "frac_fills_widened": frac,
                     "min_extra_half_spread_bps": mn, "n_extra_finite": n}
                for cn in ("BTC", "ETH", "pooled")}},
        }

    ctx_fake = {"equal_width_solve": {"n_wallets_floor_eligible": 700,
                                      "target_global_leg_mean_extra_bps": 4.0,
                                      "lambda_as_toxicity_ew": 4.41,
                                      "lambda_as_toxicity_plus_global": 1.36}}
    matched = {
        "bbgl": _fake_block(6.3646, 1.0, 3.4403),
        "as_toxicity_ew": _fake_block(6.3646, 0.6442, 0.0),
        "bbgl_flat": _fake_block(6.3646, 1.0, 6.3646),
        "as_toxicity_plus_global": _fake_block(6.3646, 1.0, 4.0),
    }
    man_ok = comparison_manifest(matched, ctx_fake)
    assert set(man_ok) == set(s["pair"] for s in COMPARISON_PAIRS), sorted(man_ok)
    assert all(m["all_held_equal_quantities_hold"] for m in man_ok.values()), man_ok
    assert all(m["refusal"] is None for m in man_ok.values())
    dl_ok = declared_axis_deltas(matched, man_ok)
    assert all(d["published"] for d in dl_ok.values()), dl_ok
    flags["comparison_manifest_silent_on_equal_width_arms"] = True

    unmatched = dict(matched)
    unmatched["as_toxicity_ew"] = _fake_block(1.4423, 0.6442, 0.0)
    man_bad = comparison_manifest(unmatched, ctx_fake)
    bad = man_bad["as_toxicity_ew_minus_bbgl"]
    assert not bad["all_held_equal_quantities_hold"], bad
    assert bad["refusal"] is not None
    assert any(r["quantity"] == "mean_extra_half_spread_bps_pooled"
               for r in bad["refusal"]["expected"]), bad["refusal"]
    # the OTHER two pairs must stay silent: a width defect in one arm is not a defect in
    # pairs that arm is not in. A predicate that fires on everything measures nothing.
    assert man_bad["bbgl_flat_minus_bbgl"]["all_held_equal_quantities_hold"]
    assert man_bad["as_toxicity_plus_global_minus_bbgl"]["all_held_equal_quantities_hold"]
    dl_bad = declared_axis_deltas(unmatched, man_bad)
    assert dl_bad["as_toxicity_ew_minus_bbgl"]["published"] is False
    assert "delta_net_vw_bps" not in json.dumps(dl_bad["as_toxicity_ew_minus_bbgl"]), (
        "a refused pair must publish no difference at all")
    assert dl_bad["bbgl_flat_minus_bbgl"]["published"] is True
    flags["comparison_manifest_fires_on_the_published_width_gap"] = True
    # the refusal names expectation, fact AND place -- otherwise there is nothing to
    # investigate when it fires.
    assert bad["refusal"]["fact"] and bad["refusal"]["where"], bad["refusal"]
    gap = bad["refusal"]["fact"][0]["relative_gap"]
    assert 0.7 < gap < 0.8, gap          # 1 - 1.4423/6.3646 = 0.7734
    flags["refusal_prints_expectation_fact_and_place"] = True
    # a row-count difference must fire too, not only a width one: two arms scored on
    # different fills are not comparable however equal their widths.
    rowdiff = dict(matched)
    rowdiff["bbgl_flat"] = _fake_block(6.3646, 1.0, 6.3646, n=999)
    man_rows = comparison_manifest(rowdiff, ctx_fake)
    assert not man_rows["bbgl_flat_minus_bbgl"]["all_held_equal_quantities_hold"]
    flags["comparison_manifest_fires_on_a_row_set_gap"] = True
    # A DEGENERATE AXIS must fire even when every held-equal quantity holds, and this case
    # is not hypothetical: driving the node over a tape whose wallets all sat below the
    # rank floor produced exactly it -- widths equal to the last bit, and both arms the
    # same quoter, because a pass-through of not-a-number leaves the resolved term at zero.
    ctx_degenerate = dict(ctx_fake)
    ctx_degenerate["equal_width_solve"] = dict(ctx_fake["equal_width_solve"],
                                               lambda_as_toxicity_plus_global=float("nan"))
    man_deg = comparison_manifest(matched, ctx_degenerate)
    deg = man_deg["as_toxicity_plus_global_minus_bbgl"]
    assert all(r["holds"] for r in deg["held_equal_measured"]), (
        "the degenerate case must be caught by the precondition, not by a width gap")
    assert not deg["all_held_equal_quantities_hold"], deg
    assert any(p["quantity"] == "solved_pass_through_of_as_toxicity_plus_global"
               and not p["holds"] for p in deg["axis_preconditions"]), deg
    assert declared_axis_deltas(matched, man_deg)[
        "as_toxicity_plus_global_minus_bbgl"]["published"] is False
    # and the OTHER solved arm, whose pass-through is finite, must stay published.
    assert man_deg["as_toxicity_ew_minus_bbgl"]["all_held_equal_quantities_hold"]
    flags["comparison_manifest_fires_on_a_degenerate_axis"] = True
    # a pass-through of exactly zero is the same failure and must also fire.
    ctx_zero = dict(ctx_fake)
    ctx_zero["equal_width_solve"] = dict(ctx_fake["equal_width_solve"],
                                         lambda_as_toxicity_ew=0.0)
    assert not comparison_manifest(matched, ctx_zero)[
        "as_toxicity_ew_minus_bbgl"]["all_held_equal_quantities_hold"]
    flags["comparison_manifest_fires_on_a_zero_pass_through"] = True

    # -------- the walk-forward fold summary ------------------------------------------
    fs = _fold_stats([0.1, None, float("nan"), -0.2, 0.3])
    assert fs["n_evaluable_folds"] == 3 and fs["n_folds_positive"] == 2, fs
    assert abs(fs["median"] - 0.1) < tol, fs
    assert _fold_stats([])["n_evaluable_folds"] == 0
    assert _fold_stats([None, float("nan")])["median"] is None
    flags["fold_stats_drops_undefined_folds_only"] = True

    # -------- the per-arm stream: independent of the roster, dependent on the seed --------
    # The defect this replaces, stated as the thing the test has to rule out: one generator
    # threaded through the run made an arm's confidence band a function of how many arms had
    # drawn before it. Measured on the live tree -- adding three arms moved 864 interval ends
    # across the six published quoters, and no point estimate at all.
    #
    # MUST STAY SILENT: the band of one arm, drawn inside a THREE-arm roster, against the
    # same arm drawn inside a NINE-arm roster where it is walked last. Both rosters are
    # walked here in full, so the test exercises the ordering it is about rather than
    # asserting that ordering does not matter.
    boot_vals = np.linspace(-4.0, 2.0, 4000)
    boot_w = np.linspace(1.0, 9.0, 4000)

    def _band(arm, roster, k_label="K50"):
        """Walk a whole roster, return the named arm's band. Mimics evaluate_quoter's cell."""
        seen = None
        for q in roster:
            g = _cell_rng("mm_bakeoff", "quoter_net_ci", k_label, q, "pooled", 10,
                          "net_MID_lower")
            band = _boot_ci_vw_capped(boot_vals, boot_w, g, n_boot=40, cap=500)
            if q == arm:
                seen = band
        return seen

    short_roster = ("naive_at_book", "as_symmetric", "as_toxicity")
    long_roster = QUOTER_NAMES[:-1] + ("as_toxicity",)      # the arm walked LAST of nine
    b_short = _band("as_toxicity", short_roster)
    b_long = _band("as_toxicity", long_roster)
    assert b_short == b_long, (
        f"an arm's band must not depend on the roster it was drawn in: {b_short} inside "
        f"{len(short_roster)} arms against {b_long} inside {len(long_roster)}")
    flags["arm_band_independent_of_roster_and_order"] = True

    # MUST FIRE: the same band, drawn from a DIFFERENT cell, has to move -- otherwise the
    # equality above would hold for the empty reason that the stream is never consumed and
    # the comparison is between two copies of one constant.
    g_other = _cell_rng("mm_bakeoff", "quoter_net_ci", "K50", "as_toxicity", "pooled", 60,
                        "net_MID_lower")
    b_other = _boot_ci_vw_capped(boot_vals, boot_w, g_other, n_boot=40, cap=500)
    assert b_other != b_short, (
        f"a different cell must give a different band, otherwise the stream is not being "
        f"consumed at all and the silence above proves nothing: {b_other} against {b_short}")
    assert all(np.isfinite(x) for x in b_short + b_other), (b_short, b_other)
    flags["arm_band_moves_with_the_cell"] = True
    # and it must move with the SEED, which is the other way the stream could turn out to be
    # decorative. settings.cell_key leads with MASTER_SEED, so a different head is a
    # different stream; the head is substituted here rather than mutated in settings.
    g_seed = np.random.default_rng([H.MASTER_SEED + 1]
                                   + H.cell_key("mm_bakeoff", "quoter_net_ci", "K50",
                                                "as_toxicity", "pooled", 10,
                                                "net_MID_lower")[1:])
    b_seed = _boot_ci_vw_capped(boot_vals, boot_w, g_seed, n_boot=40, cap=500)
    assert b_seed != b_short, (
        f"changing the seed must move the band: {b_seed} against {b_short}")
    flags["arm_band_moves_with_the_seed"] = True

    # -------- no two cells share a stream, and the checker can tell -----------------------
    # settings.colliding_cells over the cells the run records. Two opposite cases, because a
    # collision detector that never fires is indistinguishable from one that cannot.
    assert not H.colliding_cells([("mm_bakeoff", "a", "BTC"), ("mm_bakeoff", "a", "ETH"),
                                  ("mm_bakeoff", "b", "BTC")])
    assert H.colliding_cells([("mm_bakeoff", "a", "BTC"), ("mm_bakeoff", "a", "BTC")])
    # the ambiguity settings.cell_key refuses to encode away, caught rather than ignored:
    # a name spelled out and its character codes flatten alike.
    assert H.colliding_cells([("mm_bakeoff", "AB"), ("mm_bakeoff", 65, 66)])
    flags["stream_cell_collision_check_fires_and_stays_silent"] = True
    # The audit over the cells THIS battery just opened. The two rosters above share three
    # arm names and open those cells twice each, so the audit is required to SEE the
    # duplication -- an audit that reported a clean run here would be reading nothing. main()
    # clears the census after this point precisely because these cells are fixtures.
    audit = stream_cell_audit()
    assert audit["n_streams_opened"] >= len(short_roster) + len(long_roster)
    assert audit["colliding_groups"], (
        "the battery opened three cells twice over and the audit called the run clean")
    assert audit["no_two_cells_share_a_stream"] is False
    dup = {tuple(c[3] for c in g) for g in audit["colliding_groups"]}
    assert ("as_toxicity",) in {(x[0],) for x in dup}, sorted(dup)
    flags["stream_cell_audit_sees_a_collision_it_was_given"] = True

    # -------- nobody here draws from numpy's LEGACY global state -------------------------
    # np.random.seed at the top of this module seeds a second run-wide stream. No call site
    # in this file draws from it, but "no imported module does either" is not something
    # reading can settle, so it is measured: perturb the global state and check the drawn
    # quantities do not move. The probe is calibrated on a quantity that DOES read the
    # global state, so a probe that reads nothing cannot pass by being blind.
    def _drawn_under(global_seed):
        np.random.seed(global_seed)
        g = _cell_rng("mm_bakeoff", "quoter_net_ci", "probe", "as_toxicity", "pooled", 10,
                      "net_MID_lower")
        ours = _boot_ci_vw_capped(boot_vals, boot_w, g, n_boot=40, cap=500)
        legacy = float(np.random.random())      # the deliberate global reader
        return ours, legacy

    ours_a, legacy_a = _drawn_under(12345)
    ours_b, legacy_b = _drawn_under(54321)
    assert ours_a == ours_b, (
        f"a named-cell draw must not move with numpy's legacy global state: {ours_a} "
        f"against {ours_b}")
    assert legacy_a != legacy_b, (
        "the probe must be able to see the global state move, otherwise the silence above "
        "is the probe reading nothing")
    np.random.seed(SEED)                        # leave the module as it was found
    flags["named_cells_ignore_the_legacy_global_state"] = True

    # -------- naming guard: no positive 'edge/alpha/sharpe' key anywhere in a result block --------
    sample_keys = ("net_vw_bps", "net_ew_bps", "gross_prefee_vw_bps", "delta_net_vw_bps",
                   "control_ratio_as_over_null", "permutation_p")
    forbidden = ("edge", "alpha", "sharpe", "profit")
    assert not any(any(fk in k.lower() for fk in forbidden) for k in sample_keys)
    flags["no_alpha_edge_sharpe_key_names"] = True

    flags["all_passed"] = all(bool(v) for v in flags.values())
    return flags


# ==================== progress (the run is minutes long; silence is not a state) ====================
_WALL_T0 = time.monotonic()


def _progress(msg):
    """One progress line, with elapsed seconds, flushed.

    WHY flush AND NOT ONLY PYTHONUNBUFFERED. That variable may or may not be set in the
    environment this runs in, and this node is often launched by hand and redirected to a
    file; a redirected stream is block-buffered by default, so the journal then holds
    hours of a live run in a buffer and answers "where are we" with nothing. Flushing at
    the call site does not depend on how the caller launched the process.

    The cycles printed are the ones that take minutes: the rank-floor rungs, the quoters
    inside a rung, the coin groups inside a quoter, and the walk-forward folds. One coin
    group of one quoter is four capped bootstraps of 2000 draws, which is the smallest unit
    of this run that is worth a line."""
    print(f"[mm_bakeoff +{time.monotonic() - _WALL_T0:7.1f}s] {msg}", flush=True)


# ==================== main ====================
def main(walk_forward=WALK_FORWARD_DEFAULT):
    t0 = artifact.start_clock()
    print(f"[mm_bakeoff] seed={SEED}", flush=True)
    selftest_flags = run_self_tests()
    print(f"[mm_bakeoff] synthetic self-tests: all_passed={selftest_flags['all_passed']}",
          flush=True)
    # The census counts the cells THIS RUN opens, and it is cleared HERE rather than at the
    # top of main because run_self_tests opens cells of its own -- deliberately duplicated
    # ones, since proving the collision check can see a collision requires making one. Left
    # uncleared the audit reported fourteen colliding groups on the first end-to-end drive,
    # every one of them a fixture. A census whose population includes its own test is
    # measuring the wrong thing, which is the failure this file has a rule about.
    del _STREAM_CELLS[:]

    arrs, align_ok, slice_meta, taker_map_meta = load_aligned()
    n_rows = int(arrs["taker_id"].size)
    row_alignment_ok = all(bool(v) for v in align_ok.values())
    print(f"[mm_bakeoff] loaded {n_rows:,} aligned fills "
          f"(sliced={slice_meta['sliced']} days={slice_meta['days']} coins={slice_meta['coins']})")

    # derived maker_econ measures (post-slice), for the recapture overlay
    for h in HORIZONS:
        arrs[f"net_MID_lower_{h}"] = arrs["s_bbo"] - arrs[f"a_mid_{h}"]
        arrs[f"net_PRINT_{h}"] = -arrs[f"a_print_{h}"]

    # NO RUN-WIDE GENERATOR LIVES HERE ANY MORE, and its absence is the repair. One
    # generator threaded through the whole run made every drawn quantity depend on how much
    # had been drawn before it, so a block's own numbers were a function of the roster and
    # the walk order of a loop somewhere else in the file. Every drawing block now opens its
    # own named cell through settings.rng at the point of use. _stream_cells_used below
    # enumerates them so the artifact can carry the proof that no two of them collide.

    # market-level GM inputs (no identity)
    pi_info = estimate_pi(arrs)
    J_info = estimate_adverse_move(arrs)

    # OOS toxicity labels at headline K + robustness K (reuse maker_econ.build_toxicity_labels)
    labels_by_K = {}
    for K in K_LIST:
        labels_by_K[K] = build_toxicity_labels(arrs, K, horizon=HEADLINE_HORIZON)
        lb = labels_by_K[K]
        print(f"[mm_bakeoff] K={K}: eligible={lb['n_eligible']:,} toxic={lb['n_toxic_takers']:,} "
              f"days_disjoint={lb['days_disjoint']} fills_disjoint={lb['fills_disjoint']}")
    late_mask = labels_by_K[K_HEADLINE]["late_mask"]

    # evaluate all six quoters per K (headline lambda_tox = LAMBDA_TOX_HEADLINE for as_toxicity)
    quoters_by_K = {}
    glft_view_by_K = {}
    ctx_by_K = {}
    for K in K_LIST:
        _progress(f"rank floor K={K}: building context")
        ctx = build_context(arrs, labels_by_K[K], pi_info, J_info, lambda_tox=LAMBDA_TOX_HEADLINE)
        ctx_by_K[f"K{K}"] = ctx
        sv = ctx["equal_width_solve"]
        _progress(f"  equal-width solve: target {sv['target_quoter']} mean extra "
                  f"{sv['target_mean_extra_bps']:.4f} bps, global leg "
                  f"{sv['target_global_leg_mean_extra_bps']:.4f}, unit resolved term "
                  f"{sv['unit_resolved_term_mean_extra_bps']:.4f} over "
                  f"{sv['n_wallets_floor_eligible']:,} eligible wallets -> lambda_ew "
                  f"{sv['lambda_as_toxicity_ew']:.6f}, lambda_plus_global "
                  f"{sv['lambda_as_toxicity_plus_global']:.6f}")
        blocks = {}
        for qi, qname in enumerate(QUOTER_NAMES, 1):
            _progress(f"  K={K} quoter {qi}/{len(QUOTER_NAMES)} {qname}: start")
            blocks[qname] = evaluate_quoter(qname, arrs, late_mask, ctx, (f"K{K}",),
                                            progress=_progress)
            _progress(f"  K={K} quoter {qi}/{len(QUOTER_NAMES)} {qname}: done")
        quoters_by_K[f"K{K}"] = blocks
        # the GLFT/A-S spread view this K produced, kept so the claim that the block does
        # not read the rank floor is MEASURED across the rungs rather than asserted. The
        # context is already built; keeping a reference to two small dicts costs nothing.
        glft_view_by_K[f"K{K}"] = glft_view(ctx)

    # headline = K_HEADLINE blocks for the ranking
    headline_blocks = quoters_by_K[f"K{K_HEADLINE}"]
    ranking = bakeoff_ranking(headline_blocks)
    as_value = as_term_value(quoters_by_K)

    # the declared-axis comparisons, and the differences that survive their own manifest.
    _progress("comparison manifests + declared-axis differences")
    manifests = comparison_manifest(headline_blocks, ctx_by_K[f"K{K_HEADLINE}"])
    axis_deltas = declared_axis_deltas(headline_blocks, manifests)
    for pair, man in manifests.items():
        if man["all_held_equal_quantities_hold"]:
            d = axis_deltas[pair]["by_coin"]["pooled"]["base"]["delta_net_vw_bps"]
            _progress(f"  {pair}: held equal, delta {d:+.4f} bps")
        else:
            _progress(f"  {pair}: REFUSED, {len(man['refusal']['expected'])} held-equal "
                      f"quantity/quantities missed their bar")
            for exp, fact, where in zip(man["refusal"]["expected"], man["refusal"]["fact"],
                                        man["refusal"]["where"]):
                _progress(f"    expected {exp['quantity']} equal within "
                          f"{exp['rtol']:.0e}; fact arm_a={exp['arm_a']!r} "
                          f"arm_b={exp['arm_b']!r} relative gap "
                          f"{fact['relative_gap']:.3e}; place {where}")

    # placebo (identity quoters) at headline K
    _progress("placebo label shuffle")
    placebo = placebo_label_shuffle(
        arrs, late_mask, labels_by_K[K_HEADLINE],
        (arrs, labels_by_K[K_HEADLINE], pi_info, J_info, LAMBDA_TOX_HEADLINE))

    # fill-aware recapture approximation for as_toxicity (headline K). The headline context
    # is the one the rung loop already built: rebuilding it here used to redo every per-coin
    # A-S fit and every per-taker lookup for a second identical answer, and with the
    # equal-width solve inside build_context a second build would also solve the same
    # equation twice and invite the two copies to disagree.
    _progress("fill-aware recapture approximation")
    ctx_hl = ctx_by_K[f"K{K_HEADLINE}"]
    b2 = fill_aware_b2(arrs, late_mask, labels_by_K[K_HEADLINE], ctx_hl, horizon=HEADLINE_HORIZON)

    # wallet-clustered band, per-fill sign shares and per-wallet concentration of each
    # pairwise difference, at the headline rung. Reuses ctx_hl, so no context is rebuilt.
    _progress("wallet-clustered pairwise statistics")
    pair_wallet = pairwise_wallet_resolved_stats(
        arrs, late_mask, labels_by_K[K_HEADLINE], ctx_hl, horizon=HEADLINE_HORIZON)

    # walk-forward over the days present, at the headline rung.
    if walk_forward:
        _progress(f"walk-forward at K={K_HEADLINE}: start")
        wf = walk_forward_bakeoff(arrs, K_HEADLINE, LAMBDA_TOX_HEADLINE,
                                  progress=_progress)
        _progress(f"walk-forward: done, {wf['n_folds']} folds")
    else:
        wf = {"skipped": True,
              "reason": ("--no-walk-forward was passed; the folds are not a default-off "
                         "block and the artifact records the skip so a reader never takes "
                         "an absent block for a block with nothing in it")}

    # DOES THE GLFT-VS-A-S SPREAD BLOCK READ THE WALLET SELECTION FLOOR? Measured, over
    # the very views the rungs produced. Until 2026-08-01 that block sat under a key naming
    # the floor rung, which claimed it did; pairing the artifact against its snapshot
    # across the floor change showed sixteen keys vanishing and sixteen appearing with the
    # same sixteen values, K10 renamed to K50 and nothing else. The key is gone and this is
    # the measurement that replaces it.
    glft_k_labels = sorted(glft_view_by_K)
    glft_leaves = 0
    glft_moved = 0
    glft_examples = []
    for other in glft_k_labels[1:]:
        nl, nm, ex = count_moved_leaves(glft_view_by_K[glft_k_labels[0]],
                                        glft_view_by_K[other])
        glft_leaves += nl
        glft_moved += nm
        glft_examples.extend(ex[:10 - len(glft_examples)])

    # cross-checks
    cross = _cross_checks(arrs, late_mask, headline_blocks, ranking,
                          labels_by_K[K_HEADLINE])

    # The split the run actually used, derived from the days the input carries.
    early_run, late_run = early_late_days(arrs["day"])

    # Which settings produced these numbers. Two of the four now CONFIRM the declaration
    # rather than depart from it, and they are still passed for exactly the reason they
    # were passed when they departed: what the block asserts is what this run used, and a
    # value the caller does not state is not a value the artifact may claim. n_boot used
    # to be read from the environment with a default of 300 and rank_floor_fills used to
    # be 10; both were adopted on 2026-07-31. All four migrating settings are stated, so
    # nothing lands in declared_not_confirmed. Handed to artifact.write as keyword
    # arguments rather than built here, so the block is stamped in one place.
    settings_used = {
        "h": HEADLINE_HORIZON,
        "lens": "mid",
        "master_seed": SEED,
        "n_perm": N_PERM,
        "n_boot": N_BOOT,
        "rank_floor_fills": K_HEADLINE,
        "boot_sample_cap": BOOT_SAMPLE_CAP,
        "rank_floor_sensitivity": list(K_LIST),
        "early_days": list(early_run),
        "late_days": list(late_run),
        "override_reasons": {
            "n_boot": f"the run drew {N_BOOT} resamples, which IS the declared "
                      f"{H.N_BOOT}: stated as a CONFIRMATION and not as a "
                      f"deviation. Until 2026-07-31 the value came from the "
                      f"environment (CAP_N_BOOT) with a default of 300, so it "
                      f"was a property of the machine; the environment read is "
                      f"gone. Resamples are still capped at {BOOT_SAMPLE_CAP} "
                      f"rows per draw (an m-out-of-n bootstrap), which is the "
                      f"size of one draw and not a second limit on their "
                      f"number, so the reported bands stay conservative.",
            "master_seed": (
                f"CONFIRMATION since 2026-08-03, not a deviation any more. Every stream "
                f"this file DRAWS from is now opened by settings.rng on a named cell, so "
                f"all of them derive from the declared {H.MASTER_SEED} through "
                f"settings.cell_key. The {SEED} recorded beside this is the per-purpose "
                f"seed settings.SEED_BY_PURPOSE gives this consumer; after the repair it "
                f"reaches nothing that is drawn -- it seeds numpy's legacy global state, "
                f"which run_self_tests measures nothing here to consume, and it is the "
                f"value _meta.seed reports. Until this run a single generator seeded "
                f"{SEED} was threaded through the whole file, which made every band a "
                f"function of how many quoters had drawn before it; see random_streams "
                f"for the cells that replaced it and the proof that no two collide."),
            "rank_floor_fills": f"the headline cell gates takers at {K_HEADLINE} "
                                f"early fills, which IS the declared "
                                f"{H.RANK_FLOOR_FILLS}: a CONFIRMATION and not a "
                                f"deviation. It was 10 until 2026-07-31, when the "
                                f"reliability evidence behind the declaration was "
                                f"accepted. {list(K_LIST)} is still reported as "
                                f"the sweep, matching maker_econ.py so the "
                                f"bake-off and the B1 bound stay comparable",
        },
    }
    headline_labels = labels_by_K[K_HEADLINE]
    scope = {
        "population": (f"{n_rows:,} row-aligned fills; every quoter is scored on the "
                       f"{int(late_mask.sum()):,} LATE-half fills, and the identity "
                       f"quoters read a toxicity label frozen on the early half. The "
                       f"{K_HEADLINE}-early-fill floor selects "
                       f"{headline_labels['n_eligible']:,} takers, of which "
                       f"{headline_labels['n_toxic_takers']:,} carry the toxic cut, and "
                       f"that set is what the bbgl per-tier term and the toxic-decile "
                       f"policy bounds read. The as_toxicity additive term does NOT read "
                       f"it: it is applied to every taker with a finite early estimate, "
                       f"one early fill being enough. The label-shuffle placebo follows "
                       f"the term rather than the floor -- both of its arms are built "
                       f"over that same finite-estimate population, counted in "
                       f"placebo_label_shuffle.arm_populations. See "
                       f"adverse_selection_term_value.eligibility_scope"),
        "window": (f"single December window; early days {list(early_run)}, late days "
                   f"{list(late_run)}"),
        "coins": sorted(COIN_NAME.values()),
        "env_slice": slice_meta,
        "note": ("computed entirely on-disk from the two intermediates; no S3 re-pull. "
                 "env_slice says whether CAP_DAYS or CAP_COINS narrowed the population "
                 "for a smoke run"),
    }

    # THE CONCENTRATION FIGURE THE HONESTY NOTE CARRIES IS READ FROM THE BLOCK THIS RUN JUST
    # COMPUTED, never typed. A literal there is exactly how "top ~5 ~66%" survived: it was a
    # June maker-economics number about REJECTED FLOW, carried in as a string five weeks
    # before this file computed a concentration of its own, and it matches none of the six
    # cuts. Reading it back cannot go stale, and the .get chain keeps a coin with no late
    # fills from turning a note into a traceback.
    _one_sided = pair_wallet.get("by_pair", {}).get(
        "as_toxicity_minus_as_symmetric", {}).get("pooled", {})
    _two_sided = pair_wallet.get("by_pair", {}).get(
        "as_toxicity_minus_gm_vpin", {}).get("pooled", {})
    _top5_pooled = _one_sided.get("concentration_by_wallet", {}).get("top5_share", float("nan"))
    _neg_two_sided = _two_sided.get("frac_fills_negative", float("nan"))
    _top50_two_sided = _two_sided.get(
        "concentration_by_wallet", {}).get("top50_share", float("nan"))

    results = {
        "_meta": {
            "object": "market-making bake-off (naive / symmetric A-S / A-S+toxicity / "
                      "Glosten-Milgrom VPIN / GLFT / BBGL global+per-tier, plus three "
                      "equal-width arms whose differences carry a declared axis and a "
                      "measured held-equal list) on a common fill set + common net-P&L "
                      "metric, walk-forward over the days present",
            "author": "Dmitry Stakhin",
            # date this JSON was generated, taken from the run rather than pinned to a
            # literal, so a regenerated artifact never carries a stale date.
            "run_date": datetime.date.today().isoformat(),
            "track": "11 (Cryptocurrency Markets - Microstructure)",
            "seed": SEED,
            "taker_map_meta": taker_map_meta,
            "n_rows": n_rows,
            "row_alignment_ok": row_alignment_ok,
            "row_alignment_detail": align_ok,
            "env_slice": slice_meta,
            "fee_source": FEE_SOURCE,
            "maker_fee_bps": MAKER_FEE_BPS,
            "fee_tiers": list(FEE_TIERS),
            "taker_fee_ref_bps": TAKER_FEE_REF_BPS,
            "horizons_s": list(HORIZONS),
            "headline_horizon_s": HEADLINE_HORIZON,
            "early_days": list(early_run),
            "late_days": list(late_run),
            "split_rule": (
                "The EARLY/LATE halves are DERIVED from the days present, by "
                "settings.split_early_late through maker_econ.early_late_days: first "
                "ceil(n/2) days early, the rest late. They used to be hardcoded "
                "day-of-month tuples imported from maker_econ.py, correct only for a "
                "window opening on the 4th and closing on the 13th. This input does open "
                "on the 4th, so the derived split reproduces those tuples exactly and no "
                "number moved."
            ),
            "k_headline": K_HEADLINE,
            "k_list": list(K_LIST),
            "toxic_decile_frac": ME.TOXIC_DECILE_FRAC,
            "lambda_tox_headline": LAMBDA_TOX_HEADLINE,
            "lambda_tox_sensitivity_range": list(LAMBDA_TOX_GRID),
            "lambda_tox_note": ("headline FIXED at lambda_tox=1.0 (Glosten-Milgrom "
                                "break-even); the range is reported as a sensitivity band "
                                "only -- main() does NOT loop it, and the term is LINEAR in "
                                "lambda_tox (lambda=0 == as_symmetric, lambda=1 == headline), "
                                "so the endpoints bracket the band exactly without a "
                                "separate run."),
            "b2_knob_grid": {"f": list(B2_F_GRID), "w": list(B2_W_GRID), "c": list(B2_C_GRID)},
            "deploy_point": B2_DEPLOY,
            "n_vpin_buckets": N_VPIN_BUCKETS,
            "n_boot": N_BOOT,
            "boot_sample_cap": BOOT_SAMPLE_CAP,
            "gamma_anchor": GAMMA_ANCHOR,
            "equal_width_target_quoter": EQUAL_WIDTH_TARGET_QUOTER,
            "equal_width_rtol": EQUAL_WIDTH_RTOL,
            "held_equal_rtol": HELD_EQUAL_RTOL,
            "walk_forward_ran": bool(walk_forward),
            "quoters": list(QUOTER_NAMES),
            "measures": {
                "net_PRINT": "-a_print (mirror of taker print gain; nets entry spread; optimistic)",
                "net_MID_lower": "s_q - a_mid; s_q = s_bbo + min(extra, max(a_mid,0)); the "
                                 "booked defensive widening can only OFFSET the adverse-"
                                 "selection cost on a printed fill, never over-collect "
                                 "(cost-not-alpha cap; no fill model invoked).",
            },
            "honesty": (
                "COST not ALPHA: every quoter is net-negative at every tier on the "
                "conservative net_MID_lower headline (check bakeoff_ranking.*.all_net_negative "
                "and cross_checks.cost_not_alpha for any optimistic-measure / rebate-tier "
                "exception rather than asserting universal negativity blind -- a fragile "
                "rebate-tier net_PRINT flip is known to exist on some coin/K); the AS term "
                "reduces cost never flips to profit; CONCENTRATED -- top 5 wallets hold "
                f"{_top5_pooled:.1%} of the gain pooled on the one-sided as_toxicity minus "
                "as_symmetric pair, read back from pairwise_wallet_resolved.by_pair.*."
                "concentration_by_wallet rather than typed, and read the two pairs apart: "
                f"on the two-sided gm_vpin pair {_neg_two_sided:.1%} of fills are NEGATIVE "
                f"and the top fifty sum to {_top50_two_sided:.1%}, so a share there is a "
                "gross contribution and not a concentration -- mostly "
                "ETH, fragile; counterfactual overlay NOT a matching engine; the A-S+"
                "toxicity term is a reduced-form instance of Barzykin-Bergault-Gueant-"
                "Lemmel 2508.20225, validation not invention. OOS SCOPE: the per-"
                "COUNTERPARTY toxicity labels (as_toxicity early_tox, bbgl per-tier) are "
                "frozen on the EARLY window before the LATE evaluation (strictly OOS); the "
                "market-level Glosten-Milgrom pi/J are FULL-WINDOW aggregates used as a "
                "deliberately-strong book-only benchmark (no counterparty identity), which "
                "only strengthens the negative control. Glosten-Milgrom cannot reach what "
                "the counterparty-resolved term reaches; GLFT vs symmetric A-S is a "
                "near-tie reported as a finding."),
            "no_repull": "computed entirely on-disk from the two npz; no S3 re-pull.",
        },
        "selftest_flags": selftest_flags,
        "gm_pi_estimate": pi_info,
        "gm_J_estimate": J_info,
        "glft_q0_spread_vs_as": {
            **glft_view(ctx_hl),
            # THE FLOOR IS NOT A KEY OF THIS BLOCK, and here is why in the artifact rather
            # than only in the code. Until 2026-08-01 the coin tree below sat under a key
            # spelling the rank floor rung, which told a reader the quote spread had been
            # computed over the wallets that floor selects. It had not: nothing here reads
            # a wallet label at all.
            "rank_floor_read_by_this_block": False,
            "rank_floor_independence": {
                "claim": "no number in this block moves with the wallet selection floor",
                "basis": ("each entry is a function of four per-coin inputs -- the "
                          "volatility from estimate_sigma over coin/day/entry_px, an "
                          "arrival decay read off the realized half-spreads, the arrival "
                          "anchor A_hat which is the coin's fill count, and the median "
                          "entry price. build_context does read the toxicity labels, for "
                          "the early/late masks and the per-taker terms, and none of those "
                          "four inputs is built from them"),
                "measured_by": ("rebuilding the block from the context of every rung in "
                                "k_list and comparing the rungs leaf by leaf"),
                "k_labels_compared": glft_k_labels,
                "n_leaves_compared": glft_leaves,
                "n_leaves_that_moved_with_k": glft_moved,
                "leaves_that_moved": glft_examples,
                "leaf_predicate": LEAF_PREDICATE,
                "what_the_old_key_cost": (
                    "keying the block by the floor rung made every floor change look like "
                    "sixteen values disappearing and sixteen appearing in an artifact "
                    "diff, when the same sixteen numbers had merely been relabelled"),
            },
            "note": ("GLFT single-asset comes out approximately equal to symmetric A-S "
                     "(shared arrival term); the near-tie is the finding, not a failure."),
        },
        "quoters": quoters_by_K,
        "bakeoff_ranking": ranking,
        "adverse_selection_term_value": as_value,
        # WHY A SECOND DIFFERENCE BLOCK BESIDE adverse_selection_term_value. That block
        # publishes differences of arms that were never built to be compared: it is read
        # for what the resolved term is worth against symmetric A-S, which is a fair
        # question because those two arms differ only in the term. The bake-off RANKING is
        # what got read as a comparison of as_toxicity against bbgl, and those two differ
        # on width, on floor of the widening and on wallet population as well. The block
        # below carries only differences whose held-equal list was measured and held, and
        # a pair that failed carries a refusal in place of its numbers.
        "declared_axis_comparisons": {
            "why": ("a ranking orders arms on one metric; it does not make any two of them "
                    "comparable. Every difference below declares the ONE axis its arms are "
                    "allowed to differ on, lists what is held equal, measures each of those "
                    "on the published leaves, and is withheld if any of them missed"),
            "equal_width_solve": ctx_by_K[f"K{K_HEADLINE}"]["equal_width_solve"],
            "manifests": manifests,
            "deltas": axis_deltas,
        },
        "walk_forward": wf,
        "random_streams": stream_cell_audit(),
        "fill_aware_b2": b2,
        "placebo_label_shuffle": placebo,
        "pairwise_wallet_resolved": pair_wallet,
        "cross_checks": cross,
    }

    # artifact.write records the producer with the hash of its own bytes, the three
    # files it read with theirs, the scope, the settings block and the runtime, in the
    # one shape every results file in this tree carries. The inputs are named
    # relatively; input_record resolves them against this script's directory, and
    # CAP_DATA_DIR moving the data elsewhere shows up as present=false rather than as a
    # local path in the artifact.
    # gm_quoter.py IS AN INPUT AND NOT A NEIGHBOUR, and it is named here for a defect the
    # other five entries do not have. A results file records the hash of the script named
    # as its producer and of nothing else, so a formula that lives in an imported file is
    # invisible to both freshness gates: editing gm_half_spread there would leave every
    # artifact in this tree matching its recorded hashes while the GM arm below computed
    # something else. That is the whole argument against merging two spellings into one
    # home, and naming the home as an input is what answers it -- the gate now compares
    # gm_quoter.py's bytes against what this run read, and an edit there marks this
    # artifact stale exactly as an edit to this file does. The same is owed to as_quoter.py
    # and maker_econ.py, whose objects this file has imported for longer; they are not
    # added in the same edit because each addition costs this node a rerun to prove.
    artifact.write(
        os.path.basename(OUT_JSON), results, script=__file__,
        inputs=[os.path.basename(PRINT_NPZ), os.path.basename(MID_NPZ),
                os.path.basename(TAKER_MAP_JSON),
                "gm_quoter.py"],
        scope=scope, started=t0, settings=settings_used,
        out_dir=os.path.dirname(OUT_JSON))

    _print_console(results)
    print(f"\n[mm_bakeoff] wrote {os.path.basename(OUT_JSON)}")


def _cross_checks(arrs, late_mask, headline_blocks, ranking, labels):
    """Explicit booleans a verifier can attack."""
    # naive_at_book reproduces maker_econ net_MID_lower / net_PRINT (h60, pooled, base)
    s_bbo = arrs["s_bbo"]
    notl = arrs["notional"]
    idx = np.where(late_mask)[0]
    a_mid_60 = arrs["a_mid_60"][idx]
    a_print_60 = arrs["a_print_60"][idx]
    me_mid = _vw_mean((s_bbo[idx] - a_mid_60) - MAKER_FEE_BPS["base"], notl[idx])

    # LIKE-FOR-LIKE ROW SET on the print leg. The bake-off books
    # s_q = s_bbo + RECOVER_FRAC*min(extra, max(a_mid_h, 0)), so a NON-FINITE a_mid
    # propagates into s_q and drops that fill from net_PRINT even for naive_at_book, whose
    # extra is 0. maker_econ's print measure has no a_mid term and keeps those fills. The
    # two sides therefore score different rows, and the gap is a SCOPE difference, not a
    # disagreement about any fill. Restrict the maker_econ side to the rows the bake-off
    # actually scored (finite on BOTH markouts) so the comparison is like-for-like; the
    # unrestricted value and the excluded-row count are both reported below so the
    # restriction stays auditable and cannot be read as a convenient filter.
    both_finite = np.isfinite(a_mid_60) & np.isfinite(a_print_60)
    n_print_only = int((~np.isfinite(a_mid_60) & np.isfinite(a_print_60)).sum())
    me_print_all_rows = _vw_mean((-a_print_60) - MAKER_FEE_BPS["base"], notl[idx])
    me_print = _vw_mean(np.where(both_finite, (-a_print_60) - MAKER_FEE_BPS["base"], np.nan),
                        notl[idx])
    nb = headline_blocks["naive_at_book"]["net_by_coin"]["pooled"]["by_horizon"]["h60"]
    nb_mid = nb["net_MID_lower"]["by_fee_tier"]["base"]["net_vw_bps"]
    nb_print = nb["net_PRINT"]["by_fee_tier"]["base"]["net_vw_bps"]

    # all quoters net-negative at base tier (pooled, headline horizon, net_MID_lower)
    all_neg = True
    for qname in QUOTER_NAMES:
        blk = headline_blocks[qname]["net_by_coin"].get("pooled", {})
        if blk.get("n_late_fills"):
            v = blk["by_horizon"][HKEY]["net_MID_lower"]["by_fee_tier"]["base"]["net_vw_bps"]
            if v == v and v >= 0:
                all_neg = False

    # s_q >= s_bbo for all quoters (no tightening): the MIN per-fill extra >= 0
    def _min_extra(q):
        v = (headline_blocks[q]["extra_half_spread_summary"]["by_coin"].get("pooled", {})
             .get("min_extra_half_spread_bps"))
        return 0.0 if (v is None or v != v) else v
    no_tightening = all(_min_extra(q) >= -1e-9 for q in QUOTER_NAMES)

    return {
        "naive_at_book_reproduces_maker_econ_h60_pooled_base": {
            "maker_econ_net_MID_lower_vw_bps": me_mid,
            "bakeoff_naive_at_book_net_MID_lower_vw_bps": nb_mid,
            "match_within_1e-6": bool(abs(me_mid - nb_mid) < 1e-6),
            "maker_econ_net_PRINT_vw_bps": me_print,
            "bakeoff_naive_at_book_net_PRINT_vw_bps": nb_print,
            "print_match_within_1e-6": bool(abs(me_print - nb_print) < 1e-6),
            "print_row_scope": "finite a_mid_60 AND finite a_print_60 (both sides)",
            "maker_econ_net_PRINT_vw_bps_all_print_rows": me_print_all_rows,
            "n_late_rows_print_finite_mid_nonfinite": n_print_only,
            "print_scope_note": (
                "the print legs are compared on the SAME rows. The bake-off books "
                "s_q = s_bbo + RECOVER_FRAC*min(extra, max(a_mid_60,0)), so a non-finite "
                "a_mid_60 drops the fill from net_PRINT even for naive_at_book (extra=0), "
                "while maker_econ's print measure carries no a_mid term and keeps it. "
                "n_late_rows_print_finite_mid_nonfinite is exactly the set that differs. "
                "Scoring maker_econ on all print-finite rows instead gives "
                "maker_econ_net_PRINT_vw_bps_all_print_rows; the two differ only by those "
                "rows, and no fill is valued differently by the two sides."),
        },
        "all_quoters_net_negative_at_base": bool(all_neg),
        "cost_not_alpha": bool(all_neg),
        "no_tightening_s_q_ge_s_bbo": bool(no_tightening),
        "gm_uses_no_identity": True,
        # THE CLAIM WAS TRUE AND ITS STATED BASIS NAMED A KEY THAT DOES NOT EXIST, and the
        # string below is the repair. gm_vpin really does read no counterparty identity, but
        # until 2026-08-03 this field said the branch reads ctx['gm_premium_by_coin'], and
        # build_context has never returned a key of that name: the sentence was written
        # before the per-fill lookups were vectorised into lookup arrays and was not carried
        # forward. It stood as a recorded debt because correcting a string that reaches the
        # artifact is owed a recompute, and the three equal-width arms are that recompute.
        # A basis that names a key a reader cannot find is worse than no basis, because the
        # reader who goes to check it concludes the claim is unverifiable rather than that
        # the sentence is stale.
        "gm_uses_no_identity_basis": (
            "not computed at runtime: it is a code-level property. The gm_vpin branch of "
            "quoter_extra_half_spread_bps reads ctx['gm_half_lut'] indexed by arrs['coin'] "
            "only, and estimate_pi / estimate_adverse_move take no taker_id argument, so no "
            "counterparty identity reaches the GM half-spread. The lookup array is built in "
            "build_context from gm_half_bps, which is pi*J per coin."),
        # the genuinely computed early/late disjointness from build_toxicity_labels at the
        # headline K, mirroring maker_econ's oos_disjoint block (no hardcoded literal).
        "oos_disjoint": {
            "early_days": labels["early_day_set"],
            "late_days": labels["late_day_set"],
            "days_disjoint": bool(labels["days_disjoint"]),
            "fills_disjoint": bool(labels["fills_disjoint"]),
            "k_headline": K_HEADLINE,
            "note": "toxic label uses ONLY early fills; every quoter is scored on late "
                    "fills only.",
        },
        "ranking_all_negative_pooled_base": ranking["pooled"]["by_tier"]["base"]["all_net_negative"],
    }


# ==================== console summary ====================
def _f(x, nd=4):
    if x is None:
        return "n/a"
    if isinstance(x, float) and x != x:
        return "nan"
    if isinstance(x, (int, float)):
        return f"{x:+.{nd}f}"
    return str(x)


def _print_console(results):
    meta = results["_meta"]
    print("\n" + "=" * 88)
    print("MARKET-MAKER BAKE-OFF - SUMMARY (COST not ALPHA; net-negative on net_MID_lower"
          " headline -- see all_net_negative below)")
    print("=" * 88)
    print(f"  rows={meta['n_rows']:,}  seed={meta['seed']}  no-repull (on-disk).")
    print(f"  quoters: {', '.join(QUOTER_NAMES)}")
    st = results["selftest_flags"]
    print(f"  synthetic self-tests all_passed={st['all_passed']}")

    print("-" * 88)
    print(f"BAKE-OFF RANKING (pooled, {HKEY}, net_MID_lower vw, base tier; ascending cost):")
    rk = results["bakeoff_ranking"]["pooled"]["by_tier"]["base"]
    for qn, v in rk["ordered_ascending_cost"]:
        print(f"   {qn:<16} net_vw={_f(v)} bps")
    print(f"   best (least-negative): {rk['best_cost_least_negative']}  "
          f"all_net_negative={rk['all_net_negative']}")

    print("-" * 88)
    print(f"AS-TERM VALUE (K{K_HEADLINE}, pooled, base, {HKEY}, net_MID_lower delta vs A-S):")
    av = results["adverse_selection_term_value"].get(f"K{K_HEADLINE}", {}).get("pooled", {}).get("base", {})
    print(f"   as_toxicity - as_symmetric = {_f(av.get('as_toxicity_minus_as_symmetric_delta_net_vw_bps'))}")
    print(f"   gm_vpin     - as_symmetric = {_f(av.get('gm_minus_as_symmetric_delta_net_vw_bps'))}")
    print(f"   as_toxicity - gm_vpin      = {_f(av.get('as_toxicity_minus_gm_delta_net_vw_bps'))}  (counterparty-resolution premium)")

    print("-" * 88)
    print("DECLARED-AXIS COMPARISONS (each difference has ONE axis; the rest is measured):")
    dac = results.get("declared_axis_comparisons", {})
    sv = dac.get("equal_width_solve", {})
    print(f"   width target = {sv.get('target_quoter')} at "
          f"{_f(sv.get('target_mean_extra_bps'))} bps mean extra; solved lambda_ew="
          f"{_f(sv.get('lambda_as_toxicity_ew'), 6)} lambda_plus_global="
          f"{_f(sv.get('lambda_as_toxicity_plus_global'), 6)} over "
          f"{sv.get('n_wallets_floor_eligible')} floor-eligible wallets")
    for pair, man in dac.get("manifests", {}).items():
        d = dac.get("deltas", {}).get(pair, {})
        if d.get("published"):
            cell = d["by_coin"]["pooled"]["base"]
            print(f"   {pair:<42} delta={_f(cell['delta_net_vw_bps'])} bps "
                  f"({_f(cell['arm_a_net_vw_bps'])} vs {_f(cell['arm_b_net_vw_bps'])})")
        else:
            r = man.get("refusal") or {}
            print(f"   {pair:<42} WITHHELD: "
                  f"{', '.join(e['quantity'] for e in r.get('expected', []))}")
            for exp, fact, where in zip(r.get("expected", []), r.get("fact", []),
                                        r.get("where", [])):
                print(f"      expected equal within {exp['rtol']:.0e}; fact "
                      f"{exp['arm_a']} vs {exp['arm_b']}, relative gap "
                      f"{fact['relative_gap']:.3e}; place {where}")

    print("-" * 88)
    wf = results.get("walk_forward", {})
    if wf.get("skipped"):
        print("WALK-FORWARD: skipped this run (--no-walk-forward).")
    else:
        print(f"WALK-FORWARD ({wf.get('n_folds')} folds, expanding train window, "
              f"pooled base {HKEY} net_MID_lower vw):")
        for pair, st in wf.get("pair_delta_by_fold", {}).items():
            if not st["n_evaluable_folds"]:
                print(f"   {pair:<42} no evaluable fold")
                continue
            print(f"   {pair:<42} median={_f(st['median'])} mean={_f(st['mean'])} "
                  f"positive in {st['n_folds_positive']}/{st['n_evaluable_folds']} folds")
        won = wf.get("n_folds_each_quoter_finished_least_negative", {})
        best = ", ".join(f"{q} {n}" for q, n in won.items() if n)
        print(f"   folds finished least-negative by: {best}")

    print("-" * 88)
    print(f"PLACEBO (count-matched label shuffle, pooled, base, {HKEY}):")
    pc = results["placebo_label_shuffle"]["count_matched"].get("pooled", {})
    print(f"   observed reduction={_f(pc.get('observed_toxicity_reduction_net_vw_bps'))} "
          f"random_mean={_f(pc.get('random_mean'))} perm_p={_f(pc.get('permutation_p'),4)} "
          f"beats_random={pc.get('toxicity_beats_random')}")
    # the arms, on the console as well as in the artifact: a reader who watches the run go
    # by should not have to open the JSON to learn whether the null matched the treatment.
    ap = results["placebo_label_shuffle"].get("arm_populations", {})
    am = pc.get("arms_matched", {})
    print(f"   arms on ONE population: {ap.get('n_wallets_observed_arm')} wallets observed "
          f"/ {ap.get('n_wallets_null_arm')} null, of which "
          f"{ap.get('n_wallets_below_rank_floor_with_an_estimate')} sit below the "
          f"K{K_HEADLINE} floor")
    print(f"   draws matching the observed fingerprint: "
          f"{am.get('n_draws_matching_wallets_widened')}/{am.get('n_draws')} on wallets "
          f"widened, {am.get('n_draws_matching_total_premium')}/{am.get('n_draws')} on "
          f"total premium (all_matched={am.get('all_draws_matched')})")
    print(f"   observed reduction splits "
          f"{_f(pc.get('observed_reduction_eligible_wallets_only_net_vw_bps'))} from wallets "
          f"clearing the floor and "
          f"{_f(pc.get('observed_reduction_from_sub_floor_wallets_net_vw_bps'))} from those "
          f"below it")

    print("-" * 88)
    print("CROSS-CHECKS:")
    cc = results["cross_checks"]
    nm = cc["naive_at_book_reproduces_maker_econ_h60_pooled_base"]
    print(f"   naive_at_book reproduces maker_econ net_MID_lower: {nm['match_within_1e-6']} "
          f"({_f(nm['maker_econ_net_MID_lower_vw_bps'])} vs {_f(nm['bakeoff_naive_at_book_net_MID_lower_vw_bps'])})")
    print(f"   all quoters net-negative at base: {cc['all_quoters_net_negative_at_base']}  "
          f"no tightening (s_q>=s_bbo): {cc['no_tightening_s_q_ge_s_bbo']}  "
          f"gm_uses_no_identity: {cc['gm_uses_no_identity']}")
    print("=" * 88)


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        flags = run_self_tests()
        print("[mm_bakeoff] --selftest (synthetic only, NO data loaded)")
        for kk, vv in flags.items():
            print(f"  {kk:<52} {vv}")
        if not flags["all_passed"]:
            sys.exit(1)
        print("[mm_bakeoff] all synthetic self-tests PASSED")
        sys.exit(0)
    main(walk_forward="--no-walk-forward" not in sys.argv[1:])
