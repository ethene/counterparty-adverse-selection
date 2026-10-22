"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-21
References:
  - Hyperliquid fee schedule (taker 4.5->2.4 bps; maker 1.5->0 bps; maker rebate
    -0.1/-0.2/-0.3 bps by 14-day maker-volume share), fetched 2026-06-21 from the
    official Hyperliquid docs (https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees).
  - Hyperliquid node-data S3 archive (s3://hl-mainnet-node-data) and L2-book archive
    (s3://hyperliquid-archive/market_data) -- the source of the on-disk markout npz.
  - Zenodo 18184441 (Albers et al. 2026) -- the public L4 node-data release.
  - Easley, Lopez de Prado, O'Hara (2012) VPIN; the i3 OOS early/late toxicity split.
"""

# ---------------------------------------------------------------------------
# MAKER NET-ECONOMICS (RQ3 economic-materiality completion).
#
# An earlier "fees swamp it" verdict benchmarked the maker against the +4.5 bps
# TAKER fee. A market maker pays the MAKER schedule and EARNS the entry spread.
# This script computes the real maker net P&L on Hyperliquid's actual maker fee
# schedule, with the out-of-sample toxicity skew, two INDEPENDENT ways that must
# agree, entirely on-disk (NO S3 re-pull).
#
# THE IDENTITY (why no re-pull is needed for a correct v1)
# The trade-print markout a_print = mo{h} (quickwin_markouts.npz) is measured
# EXEC->print, so it already nets the entry spread the maker earned. Therefore,
# exactly, the maker's pre-fee PnL is the mirror of the taker's print gain:
#     net_PRINT_h        = -a_print_h                                    [measure 1]
# The book-mid measure is the standard mark-to-mid MM PnL:
#     net_MID_lower_h    = s_bbo - a_mid_h ,  s_bbo = spread_entry_bps/2 [measure 2]
# with a_mid_h = mo{h}_mid (quickwin_markouts_mid.npz). s_bbo is the BBO
# half-spread (exact for BBO fills, a LOWER BOUND on realized maker income), so
# net_MID_lower is a conservative measure. The two measures differ only by the
# EXIT reference (future print vs future mid) ~ one exit half-spread, so they must
# agree in sign and bracket the truth -- a primary correctness check.
#     s_approx_h         = a_mid_h - a_print_h  (mean-unbiased realized half-spread;
#                          check s_approx >= s_bbo on average; realized >= BBO).
#     net_MID_approx_h   = s_approx_h - a_mid_h = -a_print_h  (== net_PRINT: a wiring
#                          tautology, NOT independent; computed only as a guard).
#
# maker_net_h_tier = measure_h - maker_fee_bps[tier].
#
# OOS DISCIPLINE (reuse the i3 split EXACTLY): EARLY = days 4-8, LATE = days 9-13.
# Per taker with >= K early fills (K=10 headline, K=50 robustness), early_tox =
# early-half mean a_mid at the block's own horizon. Toxic decile = top 10% of the
# eligible takers by early_tox. ALL net P&L + the policy are evaluated on LATE-half
# fills ONLY (strictly OOS).
#
# ONE HORIZON PER BLOCK. Each reported horizon carries its OWN label set: the h60
# cells rank on the 60s markout and measure at 60s, the h10 cells rank on the 10s
# markout and measure at 10s. Ranking on one horizon and measuring on another
# credits the block with the gain of the shorter measurement while charging it
# only the notional the longer screen declines, so the screen looks more efficient
# than it is. See POLICY_HORIZONS and _meta.label_horizon_policy.
#
# Run command (bare python3 is BLOCKED on this machine). The pinned form is the one
# requirements.txt governs; the short `--with numpy` form resolves numpy freshly on the
# day it runs and does NOT honour the pins, measured 2026-08-03:
#   uv run --no-project --with-requirements requirements.txt python3 -u maker_econ.py
# Smoke slice (subset days/coins after load):
#   CAP_DAYS=9,10 CAP_COINS=BTC uv run --no-project \
#       --with-requirements requirements.txt python3 -u maker_econ.py
# `-u` is not decoration: this run prints for over an hour and a buffered stream holds
# the progress lines until the end, which is when they stop being useful.
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

# -------------------- determinism --------------------
# The seed comes from the declaration and its VALUE does not move: settings.seed_for
# returns the 20260621 that every stream in this file was drawn under, because that is
# what SEED_BY_PURPOSE records for this consumer. Reading it here rather than typing it
# is not a step toward settings.MASTER_SEED and does not adopt it -- the two are
# different declarations, and this file still overrides the master seed, which the
# fingerprint below states in words.
SEED = H.seed_for("maker_econ")
np.random.seed(SEED)
RNG = np.random.default_rng(SEED)

# -------------------- paths (bare filenames in _meta; no /Users leak) --------------------
HERE = os.path.dirname(os.path.abspath(__file__))
# The two arrays sit under the declared data root, which stayed at the top of the
# repository when the producers were grouped; the results file stays beside this script.
MID_NPZ = os.path.join(P.data_root(), "quickwin_markouts_mid.npz")  # a_mid + spread
PRINT_NPZ = os.path.join(P.data_root(), "quickwin_markouts.npz")    # a_print (mo*)
OUT_JSON = os.path.join(HERE, "maker_econ_results.json")

# -------------------- config --------------------
# The ladder of windows every producer writes a column for. Declared once, in
# settings.LADDER_S; a window outside it has no column in any artifact.
HORIZONS = H.LADDER_S
COIN_NAME = H.coin_labels("quickwin")   # the map belongs to the FILE, not the project

# THE LABEL AND EVALUATION HALVES ARE DERIVED, NOT DECLARED. Both names are OVERRIDE
# HOOKS and default to None, which means "split the days the input actually carries"
# through settings.split_early_late (see early_late_days below). They used to be the
# literal tuples (4,5,6,7,8) and (9,10,11,12,13), which are days of the MONTH and are
# right only for a window that opens on the 4th and closes on the 13th. The December
# window this file reads does open on the 4th, so the derived split reproduces those
# tuples exactly and no number here moves. This module is the home of the split for
# maker_econ_b2.py and mm_bakeoff.py too, which take their labels from
# build_toxicity_labels, so the three files cannot drift apart.
#
# WHY THEY CARRY _OVERRIDE IN THE NAME, renamed here 2026-07-31, following gm_quoter.py,
# which took the same suffix earlier that day in commit ff3b8fe. (A note in
# checks/chk_settings_home.py dates that rename to 2026-07-30; the commit says the 31st,
# and the commit is the record.) They used to be spelled EARLY_DAYS and LATE_DAYS, which are
# the names settings.py owns for the day split, and the settings gate read them as this
# file declaring that setting a second time -- two of the sites it reports. The reading
# was right about the name and wrong about the value: there is no value here to migrate,
# because the split already comes from settings.py and what these two hold is the
# ABSENCE of an override. A name that states a setting its value does not come from is
# the defect settings.py calls out in its own second rule, so the repair is to make the
# name say what the object is. Nothing outside this module reads either name --
# maker_econ_b2.py imports the FUNCTION early_late_days, not the globals it consults --
# so the rename reaches every consumer and moves nothing: None before, None after.
EARLY_DAYS_OVERRIDE = None
LATE_DAYS_OVERRIDE = None


def early_late_days(day):
    """The (early, late) day tuples for the days actually present in one input.

    A function and not a constant because no tuple can express the rule: to stay
    correct on a window that is not ten days long the split has to be a function OF
    THE DAYS. An override supplies one half explicitly and the other half is then
    every present day that is not in it, so an injected half cannot leave its partner
    on another month's day numbers.
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


# Min early fills per taker: the sweep this file reports and the rung its prose points
# at. Both come from the declaration. The role is named at the call because the two are
# different quantities: a sweep is every rung reported, a headline is the one the text
# cites.
#
# THE HEADLINE ROSE FROM 10 TO THE DECLARED 50 ON 2026-07-31. The evidence is in
# settings.RANK_FLOOR_FILLS: at ten fills the split-half reliabilities are 0.333 and
# 0.386, so the disattenuation multiplier is 2.79 and 64 percent of the corrected score
# is the correction. The sweep is unchanged at (10, 50), so the artifact goes on carrying
# both the K10 and the K50 block and nothing published is deleted; what moves is which
# block the prose cites and, underneath it, the eligible population -- 9,654 takers with
# a 966-wallet toxic decile at ten fills, 2,069 and 207 at fifty. The blocks that are NOT
# keyed by K -- baseline_net and cross_checks -- are computed at the headline alone, so
# for those the recompute produces figures that do not exist today rather than moving a
# citation.
K_LIST = H.wallet_fill_floor("maker_econ", "sweep")
K_HEADLINE = H.wallet_fill_floor("maker_econ", "headline")

# THE LADDER OF FLOORS THIS FILE PUBLISHES, widened from two rungs to eight on
# 2026-08-03, and the reason is that two named quantities of this study were reported
# over a ladder this file did not carry. Both were measured outside this repository,
# in a run whose output was never brought into the tree, so the rungs between them
# existed as prose and nowhere else. The two ladders are not the same ladder and their
# union is what closes both: one names 1, 2, 5, 10, 50, 100 and the other 1, 2, 3, 5,
# 10, 25, 50, 100, so a loop over "six rungs" closes neither on its own.
#
# WHAT IS DECLARED WHERE. Four of the eight come from settings.RANK_FLOOR_SENSITIVITY,
# which that module declares as the candidate set for exactly this floor; two more are
# the declared sweep and the declared headline. The remaining four -- 1, 2, 3 and 5 --
# are declared HERE and nowhere else, and that is a debt and is named as one: the floors
# below ten are the left edge of the curve, where the eligible population is largest and
# the estimate least reliable, and settings.py holds no declaration for them. When it
# does, LOW_RUNGS_LOCAL is deleted and the union below reads one name fewer. Until then
# the artifact states rung by rung which declaration each came from, so a reader is never
# left to infer it from the numbers.
LOW_RUNGS_LOCAL = (1, 2, 3, 5)
K_RUNGS = tuple(sorted(set(K_LIST) | {K_HEADLINE}
                       | set(H.RANK_FLOOR_SENSITIVITY) | set(LOW_RUNGS_LOCAL)))


def rung_declared_in(K):
    """Which declaration puts rung K on the ladder. Every rung carries this in the
    artifact, so 'where does this floor come from' is answered by the file and not by
    the reader's memory of which module holds which tuple."""
    homes = []
    if K == K_HEADLINE:
        homes.append("settings.RANK_FLOOR_FILLS (headline)")
    if K in set(K_LIST):
        homes.append("settings.WALLET_FILL_FLOOR_BY_PURPOSE['maker_econ']['sweep']")
    if K in set(H.RANK_FLOOR_SENSITIVITY):
        homes.append("settings.RANK_FLOOR_SENSITIVITY")
    if K in set(LOW_RUNGS_LOCAL):
        homes.append("maker_econ.LOW_RUNGS_LOCAL (declared debt, 2026-08-03)")
    return homes


# WHICH RUNGS CARRY A PERMUTATION NULL, and this is a BAR, so it is dated, its reason is
# a measurement and it moves only one way. Every rung of K_RUNGS gets its label set, its
# decile table, its B1 gain and a wallet-clustered interval on that gain, because all
# four are cheap: measured 2026-08-03 on this machine, 1.36 s of labels plus 0.6 s of
# wallet bootstrap per rung and horizon. The permutation placebo is not cheap: it makes
# 2002 passes over the 1.23 million late rows at 68 ms each, which is 136 s per rung and
# horizon, and it is what the recorded 2,468 s of this node is mostly made of.
#
# So the null runs on the DECLARED sweep and the headline, which is where it ran before
# this widening, and the eight-rung ladder adds no permutation draws at all. Widening it
# to every rung is one line -- PLACEBO_RUNGS = K_RUNGS -- and the measured price of that
# line is 16 cells against 4, about 27 minutes of additional wall clock. It is not
# spent here because neither quantity the ladder was widened for reads a p: both read
# the gain, its interval and the eligible count, and the gain a placebo block reports is
# arithmetically the same number the B1 block already computes at that cell -- verified
# 2026-08-03 against the committed artifact, where the two agree to every digit at
# K50/h10 (0.4664722102687451).
PLACEBO_RUNGS = tuple(sorted(set(K_LIST) | {K_HEADLINE}))
# Horizons the decile and policy blocks are reported on. Each one gets its OWN
# label set, so a block never ranks on one horizon and measures on another. The
# HEADLINE entry stays FIRST: the placebo and the B1 blocks draw from a shared
# generator, so the order fixes which cell reproduces bit-for-bit. Reordering this
# tuple re-draws every downstream random stream -- expected, and it is why the
# committed 60s-first numbers do not survive the move to a 10s headline.
POLICY_HORIZONS = (H.HEADLINE_HORIZON_S, H.COMPANION_HORIZON_S)
# The horizon whose label set stands in where a block is horizon-free: the
# day-based masks and the cross-checks, which do not move with the horizon.
LABEL_ANCHOR_HORIZON = H.HEADLINE_HORIZON_S
TOXIC_DECILE_FRAC = 0.10            # top 10% eligible takers by early_tox
# Bootstrap resamples for the 95% CI, from the per-consumer budget, which since
# 2026-07-31 is the declared N_BOOT. The published intervals in this file were drawn at
# 1000, half of it, and the gap was carried as a stated override; it is closed here, which
# moves every interval endpoint in the file and no point estimate, because a point
# estimate is computed from the data and never from the resamples.
N_BOOT = H.boot_draws("maker_econ")
N_PERM = H.N_PERM                   # placebo permutations (p-floor = 1/(N_PERM+1))

# Hyperliquid maker fee schedule, bps (1 bp = 0.01%), fetched 2026-06-21 from the
# official docs and re-read at the same address on 2026-08-02, when every rung below
# still stood at the value it carries here: the seven perpetual volume tiers, the
# maker ladder down to zero, and the three maker rebates.
#
# WHICH RUNG IS MEASURED AND WHICH IS ASSUMED, and the two are not the same kind of
# thing. The volume tiers are a property of the venue, so all of them are reported and
# a reader may read the table at whichever one they operate on. The three rebate rungs
# are not comparable to those: each is gated on a FOURTEEN-DAY share of venue-wide
# maker volume, a quantity a ten-day two-coin window cannot contain, and the
# participant priced in this file is the aggregate of every maker in the tape rather
# than one account holding a share. The deepest rung is therefore a stated SCENARIO
# and not a fitted figure. The base rung is the conservative reading, and it is the one
# the console summary leads with. How far up the rebate ladder any single maker in this
# window could in fact reach is a separate measurement, and it is recorded beside the
# schedule in the decision registry rather than restated here.
FEE_SOURCE = ("Hyperliquid fee schedule fetched 2026-06-21 from the official docs "
              "(hyperliquid.gitbook.io/hyperliquid-docs/trading/fees): maker 1.5 bps "
              "base -> 1.2/0.8/0.4 -> 0 bps (>$500M 14d vol); maker rebate "
              "-0.1/-0.2/-0.3 bps by 14d maker-volume share; taker 4.5 -> 2.4 bps. "
              "1 bp = 0.01%.")
MAKER_FEE_BPS = {
    "base": 1.5,        # base maker fee
    "t3": 0.4,          # tier 3 (>$100M 14d volume)
    "t4_0fee": 0.0,     # tier 4 (>$500M) and above: zero maker fee
    "rebate1": -0.1,    # >0.5% 14d maker-volume share
    "rebate2": -0.2,    # >1.5%
    "rebate3": -0.3,    # >3.0%
}
FEE_TIERS = ("base", "t3", "t4_0fee", "rebate1", "rebate2", "rebate3")
TAKER_FEE_REF_BPS = {  # reference only, never subtracted from the maker measures
    "base": 4.5, "t1": 4.0, "t2": 3.5, "t3": 3.0, "t4": 2.8, "t5": 2.6, "t6": 2.4,
}


# ==================== weighted-mean / bootstrap helpers (numpy-only) ====================
def _vw_mean(vals, weights):
    """Notional-weighted mean of vals over finite, positive-weight rows."""
    vals = np.asarray(vals, dtype=np.float64)
    weights = np.asarray(weights, dtype=np.float64)
    m = np.isfinite(vals) & np.isfinite(weights) & (weights > 0)
    if not m.any():
        return float("nan")
    return float(np.sum(vals[m] * weights[m]) / np.sum(weights[m]))


def _ew_mean(vals):
    """Equal-weighted mean over finite rows."""
    vals = np.asarray(vals, dtype=np.float64)
    m = np.isfinite(vals)
    return float(vals[m].mean()) if m.any() else float("nan")


def _boot_ci_vw(vals, weights, rng, n_boot=N_BOOT, alpha=0.05, spread_out=None):
    """Bootstrap 95% CI of the notional-weighted mean (resample rows i.i.d.).

    WHY THIS IS NOT stats.bootstrap_mean_ci, and the reason is exactly one thing. The
    interval is the same percentile interval, at the same alpha, over the same dropped
    rows, resampled by the same generator.integers(0, n, size=n) call -- but not from the
    same GENERATOR. This function resamples from the stream its caller threads through
    the whole run; that module builds one stream per named cell from the master seed, and
    it takes no generator argument, so there is no way to hand it this one. Routing this
    through it would re-draw every confidence interval in this file, which is a measured
    change owed its own recompute rather than a rename.

    The budget was never a second reason and is recorded here so it is not mistaken for
    one: that module takes n_boot as an argument, so a difference in the budget would
    survive the move either way. Since 2026-07-31 there is no difference to survive --
    N_BOOT is the declared 2000 -- and the generator remains the whole reason.

    `spread_out` is an optional dict this function fills with the standard deviation of
    the draws it already made. It exists so the fill-level and wallet-level spreads can
    be put in a ratio without drawing the expensive fill-level bootstrap twice: at 20 s
    a call, measured 2026-08-03, a second pass for a number already in hand is the whole
    cost of the block again. It touches no generator and changes no returned value.
    """
    vals = np.asarray(vals, dtype=np.float64)
    weights = np.asarray(weights, dtype=np.float64)
    m = np.isfinite(vals) & np.isfinite(weights) & (weights > 0)
    v = vals[m]
    w = weights[m]
    n = v.size
    if n < 2:
        return [float("nan"), float("nan")]
    boots = np.empty(n_boot, dtype=np.float64)
    for b in range(n_boot):
        idx = rng.integers(0, n, size=n)
        ws = w[idx]
        sw = ws.sum()
        boots[b] = np.sum(v[idx] * ws) / sw if sw > 0 else np.nan
    boots = boots[np.isfinite(boots)]
    if boots.size < 2:
        if spread_out is not None:
            spread_out["boot_se"] = float("nan")
            spread_out["n_usable_draws"] = int(boots.size)
        return [float("nan"), float("nan")]
    lo = float(np.percentile(boots, 100 * alpha / 2.0))
    hi = float(np.percentile(boots, 100 * (1 - alpha / 2.0)))
    if spread_out is not None:
        spread_out["boot_se"] = float(boots.std(ddof=1))
        spread_out["n_usable_draws"] = int(boots.size)
    return [lo, hi]


# ==================== wallet-clustered bootstrap ====================
# WHY A SECOND INTERVAL AND NOT A REPLACEMENT FOR THE FIRST. _boot_ci_vw above resamples
# ROWS, and a row is a fill. The treatment this file studies varies by WALLET -- one
# counterparty contributes many fills whose markouts are correlated, and the toxicity
# screen accepts or declines a wallet whole -- so a fill-resampled band answers "how
# uncertain is this mean over these fills" and not "how uncertain is it over these
# counterparties". The second question is the one the study's claims rest on, and until
# 2026-08-03 no artifact of this file answered it: the figure was computed once outside
# this repository and typed into prose from a run that no longer exists.
#
# The form is mm_bakeoff.pairwise_wallet_resolved_stats's, taken deliberately rather
# than re-derived: per-wallet partial sums once, then every draw is a gather over those,
# and the statistic recomputed on each draw is the same ratio-of-sums the point estimate
# is. That is what makes it affordable at every rung -- 33,352 wallet groups against
# 1,234,777 rows, measured 0.28 s per 2000 draws against 20 s for the row-level form.
#
# THE GENERATOR IS ITS OWN AND NEVER THE SHARED STREAM. Every call below is handed a
# generator seeded on the cell it belongs to. Drawing from the run-wide stream instead
# would move every row-level interval already published in this file, because those are
# drawn from that stream in order -- a measured change owed its own recompute, and not
# one this addition is entitled to make.
def _wallet_partials(vals, weights, wallets):
    """Per-wallet sums of weight*value and of weight, over the rows a mean would use.

    The predicate is stated here and printed beside every count that comes out of it:
    finite value, finite weight, weight strictly positive -- the same three conditions
    _vw_mean drops on, so the point estimate and the interval stand on one population.
    Returns (num_by_wallet, den_by_wallet, wallet_ids, n_rows_kept).
    """
    vals = np.asarray(vals, dtype=np.float64)
    weights = np.asarray(weights, dtype=np.float64)
    wal = np.asarray(wallets, dtype=np.int64)
    keep = np.isfinite(vals) & np.isfinite(weights) & (weights > 0)
    if not keep.any():
        return (np.empty(0, np.float64), np.empty(0, np.float64),
                np.empty(0, np.int64), 0)
    uw, inv = np.unique(wal[keep], return_inverse=True)
    num = np.bincount(inv, weights=weights[keep] * vals[keep], minlength=uw.size)
    den = np.bincount(inv, weights=weights[keep], minlength=uw.size)
    return num, den, uw, int(keep.sum())


def ci_width(ci):
    """Width of a two-element interval, or NaN when either end is missing."""
    if ci is None or len(ci) != 2 or ci[0] != ci[0] or ci[1] != ci[1]:
        return float("nan")
    return float(ci[1] - ci[0])


def _pctile_ci(boots, alpha=0.05):
    """Percentile interval of a draw vector, or two NaNs when it is too thin."""
    boots = boots[np.isfinite(boots)]
    if boots.size < 2:
        return [float("nan"), float("nan")]
    return [float(np.percentile(boots, 100 * alpha / 2.0)),
            float(np.percentile(boots, 100 * (1 - alpha / 2.0)))]


def _boot_wallet_level(num_w, den_w, rng, n_boot=N_BOOT):
    """Wallet-clustered draws of the notional-weighted mean, at fee zero.

    Every fee tier's interval is this one shifted by minus the fee, and that is exact
    rather than close: net = measure - fee for every row, and a weighted mean of a
    constant is that constant, so the tier moves the level and cannot move the width.
    The caller does the shift and the artifact records that it did, so six tiers cost
    one bootstrap instead of six.
    """
    ng = num_w.size
    if ng < 2:
        return np.empty(0, np.float64)
    boots = np.empty(n_boot, dtype=np.float64)
    for b in range(n_boot):
        g = rng.integers(0, ng, size=ng)
        den = den_w[g].sum()
        boots[b] = num_w[g].sum() / den if den > 0 else np.nan
    return boots


def _boot_wallet_delta(num_w, den_w, keep_w, rng, n_boot=N_BOOT):
    """Wallet-clustered draws of (screened mean - unscreened mean), at fee zero.

    THE FEE CANCELS FROM THE DIFFERENCE EXACTLY, which is why this returns one vector
    and not six. Each arm is a weighted mean of (measure - fee), so the difference is
    the difference of the two weighted means of `measure`; the constant leaves it.
    Confirmed against the committed artifact before this function was written: all six
    tiers of b1 delta_net_vw_bps at K50/h10 carry 0.466472210269 to the last digit.
    `keep_w` is the boolean over wallets the screen KEEPS, so both arms are resampled
    from the same draw and their difference is a paired one.
    """
    ng = num_w.size
    if ng < 2 or not keep_w.any():
        return np.empty(0, np.float64)
    num_keep = num_w * keep_w
    den_keep = den_w * keep_w
    boots = np.empty(n_boot, dtype=np.float64)
    for b in range(n_boot):
        g = rng.integers(0, ng, size=ng)
        den_all = den_w[g].sum()
        den_scr = den_keep[g].sum()
        if den_all > 0 and den_scr > 0:
            boots[b] = num_keep[g].sum() / den_scr - num_w[g].sum() / den_all
        else:
            boots[b] = np.nan
    return boots


def _cell_rng(*parts):
    """A generator belonging to one named cell, so a cell reproduces on its own and
    adding a cell cannot re-draw a neighbour."""
    return np.random.default_rng([SEED] + [int(p) for p in parts])


def _net_block(measure, notional, rng, tag, taker=None, cell=()):
    """Per-fee-tier notional-weighted + equal-weighted net mean (+two bootstrap CIs).

    `measure` is the pre-fee maker PnL in bps; net = measure - maker_fee[tier].
    Returns a dict keyed by fee tier plus the pre-fee gross figures and n.

    TWO INTERVALS, AND THEY ANSWER DIFFERENT QUESTIONS. net_vw_ci95 resamples FILLS and
    is what this file has always published; net_vw_ci95_wallet_clustered resamples the
    WALLETS the fills belong to, which is the level the toxicity screen acts at. Neither
    replaces the other and the wider one is not automatically the right one to quote --
    the fill-level band is the right band for a statement about these fills and the
    clustered band for a statement about these counterparties. `taker` is optional only
    so that a caller with no wallet column still gets the block it always got; when it
    is absent the clustered fields are absent too rather than being filled with the
    fill-level number under a clustered name.
    """
    measure = np.asarray(measure, dtype=np.float64)
    notional = np.asarray(notional, dtype=np.float64)
    finite = np.isfinite(measure) & np.isfinite(notional) & (notional > 0)
    n = int(finite.sum())
    out = {
        "measure": tag,
        "n_fills": n,
        "gross_prefee_vw_bps": _vw_mean(measure, notional),
        "gross_prefee_ew_bps": _ew_mean(measure[finite] if finite.any() else measure),
        "by_fee_tier": {},
    }

    # One wallet bootstrap for all six tiers, at fee zero, shifted per tier below.
    boots0 = np.empty(0, np.float64)
    if taker is not None:
        num_w, den_w, uniq_w, n_kept = _wallet_partials(measure, notional, taker)
        boots0 = _boot_wallet_level(num_w, den_w, _cell_rng(*cell, 1))
        out["wallet_clustering"] = {
            "cluster_level": "taker wallet (taker_id), because the toxicity screen "
                             "accepts or declines a counterparty whole",
            "n_wallets": int(uniq_w.size),
            "n_rows_in_clusters": n_kept,
            "n_boot": N_BOOT,
            "predicate": "isfinite(measure) & isfinite(notional) & notional > 0",
            "tier_shift_is_exact": ("one bootstrap is drawn at fee zero and each tier's "
                                    "interval is it minus that tier's fee; net = measure "
                                    "- fee row by row and a weighted mean of a constant "
                                    "is that constant, so the fee moves the level and "
                                    "cannot move the width"),
        }

    for tier in FEE_TIERS:
        fee = MAKER_FEE_BPS[tier]
        net = measure - fee
        fill_spread = {}
        cell_out = {
            "maker_fee_bps": fee,
            "net_vw_bps": _vw_mean(net, notional),
            "net_ew_bps": _ew_mean(net[finite] if finite.any() else net),
            "net_vw_ci95": _boot_ci_vw(net, notional, rng, spread_out=fill_spread),
        }
        if taker is not None:
            ci = _pctile_ci(boots0 - fee)
            cell_out["net_vw_ci95_wallet_clustered"] = ci
            cell_out["wallet_clustered_ci_excludes_zero"] = bool(
                ci[0] == ci[0] and (ci[0] > 0 or ci[1] < 0))
            # HOW MUCH THE HONEST LEVEL OF RESAMPLING COSTS IN PRECISION. This ratio is
            # a named quantity of the study and until 2026-08-03 it had no producer at
            # all: it was measured once outside this repository, reported as "about
            # twofold", and the script that made it was never brought into the tree. It
            # lives here now, beside both intervals it is the ratio of, so it can never
            # again be a figure without a file. Two forms are published because the
            # archived report does not say which of them it meant: the standard-error
            # ratio, which is what its own wording names, and the interval-width ratio,
            # which is what a reader comparing the two brackets sees. The two need not
            # be equal -- the draw distribution is not exactly normal -- so publishing
            # one alone would settle by accident which question was answered.
            fill_se = fill_spread.get("boot_se", float("nan"))
            wall_se = (float(boots0.std(ddof=1)) if boots0.size >= 2 else float("nan"))
            w_fill = ci_width(cell_out["net_vw_ci95"])
            w_wall = ci_width(ci)
            cell_out["clustering_penalty"] = {
                "what": ("how much wider the interval becomes when the resampling unit "
                         "is the counterparty instead of the fill; 1.0 would mean the "
                         "fills of one wallet carry independent information"),
                "boot_se_fill_level": fill_se,
                "boot_se_wallet_clustered": wall_se,
                "se_ratio_wallet_over_fill": (wall_se / fill_se
                                              if fill_se and fill_se == fill_se
                                              and fill_se > 0 else float("nan")),
                "ci_width_ratio_wallet_over_fill": (w_wall / w_fill
                                                    if w_fill and w_fill == w_fill
                                                    and w_fill > 0 else float("nan")),
                "n_boot": N_BOOT,
            }
        out["by_fee_tier"][tier] = cell_out
    return out


# ==================== env slice (smoke runs) ====================
def _apply_env_slice(arrs):
    """If CAP_DAYS / CAP_COINS are set, filter every aligned array to those rows.

    CAP_DAYS  : comma list of day ints (e.g. "9,10").
    CAP_COINS : comma list of coin symbols (e.g. "BTC,ETH") or codes ("0,1").
    Returns (arrs, slice_meta).
    """
    day = arrs["day"]
    coin = arrs["coin"]
    mask = np.ones(day.size, dtype=bool)
    meta = {"sliced": False, "days": None, "coins": None}

    env_days = os.environ.get("CAP_DAYS")
    if env_days:
        keep_days = set(int(x.strip()) for x in env_days.split(",") if x.strip())
        mask &= np.array([int(d) in keep_days for d in day])
        meta["sliced"] = True
        meta["days"] = sorted(keep_days)

    env_coins = os.environ.get("CAP_COINS")
    if env_coins:
        name_to_code = {v: k for k, v in COIN_NAME.items()}
        keep_codes = set()
        for tok in env_coins.split(","):
            tok = tok.strip()
            if not tok:
                continue
            if tok.upper() in name_to_code:
                keep_codes.add(name_to_code[tok.upper()])
            else:
                keep_codes.add(int(tok))
        mask &= np.array([int(c) in keep_codes for c in coin])
        meta["sliced"] = True
        meta["coins"] = sorted(COIN_NAME.get(c, c) for c in keep_codes)

    if meta["sliced"]:
        arrs = {k: v[mask] for k, v in arrs.items()}
    return arrs, meta


# ==================== load + assemble (NO re-pull) ====================
def load_aligned():
    """Load both npz, verify row alignment, build the per-fill quantity arrays.

    Returns a dict of aligned arrays:
      taker_id, coin, day, notional, taker_side, sign_taker,
      a_mid_{1,10,60}, a_print_{1,10,60}, s_bbo, and the derived measures
      net_PRINT_{h}, net_MID_lower_{h}, s_approx_{h}, net_MID_approx_{h}.
    """
    if not os.path.exists(MID_NPZ):
        raise SystemExit(f"[maker_econ] missing {os.path.basename(MID_NPZ)} - run i4_midmarkout.py first")
    if not os.path.exists(PRINT_NPZ):
        raise SystemExit(f"[maker_econ] missing {os.path.basename(PRINT_NPZ)} - run build_quickwin_markouts.py first")

    zm = np.load(MID_NPZ)
    zp = np.load(PRINT_NPZ)

    # row alignment is non-negotiable (i4 guarantees it; assert it anyway).
    align_keys = ("taker_id", "coin", "day", "taker_side", "maker_id")
    align_ok = {}
    for k in align_keys:
        align_ok[k] = bool(np.array_equal(zm[k], zp[k]))
        if not align_ok[k]:
            raise SystemExit(f"[maker_econ] ROW MISALIGNMENT on '{k}' between the two npz - abort")
    # notional is float32 in both; compare with a tight tolerance, not exact bits.
    notl_mid = zm["notional"].astype(np.float64)
    notl_print = zp["notional"].astype(np.float64)
    align_ok["notional"] = bool(np.allclose(notl_mid, notl_print, rtol=0, atol=1e-3, equal_nan=True))

    arrs = {
        "taker_id": zm["taker_id"].astype(np.int64),
        "coin": zm["coin"].astype(np.int64),
        "day": zm["day"].astype(np.int64),
        "notional": notl_mid,
        "taker_side": zm["taker_side"].astype(np.int64),
    }
    arrs["sign_taker"] = np.where(arrs["taker_side"] == 1, 1.0, -1.0)

    # a_mid (book-mid markout, += maker adverse-selected; nan where no book snapshot)
    for h, key in ((1, "mo1_mid"), (10, "mo10_mid"), (60, "mo60_mid")):
        arrs[f"a_mid_{h}"] = zm[key].astype(np.float64)
    # a_print (trade-print markout, row-aligned)
    for h, key in ((1, "mo1"), (10, "mo10"), (60, "mo60")):
        arrs[f"a_print_{h}"] = zp[key].astype(np.float64)

    # s_bbo = spread_entry_bps / 2 (BBO half-spread; >= 0; lower bound on income)
    arrs["s_bbo"] = zm["spread_entry_bps"].astype(np.float64) / 2.0

    arrs, slice_meta = _apply_env_slice(arrs)

    # derived measures (post-slice so the smoke subset is internally consistent)
    for h in HORIZONS:
        a_mid = arrs[f"a_mid_{h}"]
        a_print = arrs[f"a_print_{h}"]
        arrs[f"net_PRINT_{h}"] = -a_print
        arrs[f"net_MID_lower_{h}"] = arrs["s_bbo"] - a_mid
        s_approx = a_mid - a_print
        arrs[f"s_approx_{h}"] = s_approx
        arrs[f"net_MID_approx_{h}"] = s_approx - a_mid   # == -a_print (tautology guard)

    return arrs, align_ok, slice_meta


# ==================== OOS toxicity labels (reuse i3 split exactly) ====================
def build_toxicity_labels(arrs, K, *, horizon=H.HEADLINE_HORIZON_S):
    """Per-taker EARLY/LATE labels, strictly OOS.

    early_tox = early-half mean a_mid_<horizon> per taker, over the early fills
    whose a_mid at THAT horizon is finite, keeping takers with at least K such
    fills. Eligibility therefore moves with the horizon, because the two markout
    columns do not carry identical NaN patterns.
    Toxic decile = top TOXIC_DECILE_FRAC of eligible takers by early_tox.
    LATE mask = rows on the LATE days (where ALL P&L + policy are evaluated).

    `horizon` is keyword-only on purpose: K and the horizon are both small ints
    drawn from overlapping sets (K_LIST holds 10, HORIZONS holds 10), so a
    positional third argument would be an easy silent mix-up. A caller that
    scores on a horizon MUST pass that same horizon here, so the ranking signal
    and the measured cost sit on one clock; the headline (10s) default is what this module
    reports on.

    Returns a dict with these keys, all of them:
      uniq                 int array, sorted unique taker ids (the index order
                           every per-taker array below is aligned to)
      early_tox            float array, one entry per UNIQ taker (NOT per
                           eligible taker), NaN where the taker has no finite
                           early fill
      eligible_mask_taker  bool array per uniq taker, cnt_early >= K and
                           early_tox finite
      toxic_taker_set      python set of taker ids in the toxic decile
      decile_of_taker      dict taker id to decile 1..10, eligible takers only
      late_mask            bool array per fill, rows on the LATE days
      early_mask           bool array per fill, rows on the EARLY days
      n_eligible           int, eligible taker count
      n_toxic              int, size of the requested toxic cut
      n_toxic_takers       int, len(toxic_taker_set)
      days_disjoint        bool, EARLY and LATE share no day
      fills_disjoint       bool, no fill is both EARLY and LATE
      early_day_set        sorted list of the EARLY days actually present
      late_day_set         sorted list of the LATE days actually present
    """
    taker = arrs["taker_id"]
    day = arrs["day"]
    a_mid_h = arrs[f"a_mid_{horizon}"]   # ranking signal at the caller's horizon

    early_days, late_days = early_late_days(day)
    early_set = set(early_days)
    late_set = set(late_days)
    is_early = np.array([int(d) in early_set for d in day])
    is_late = np.array([int(d) in late_set for d in day])

    # OOS disjoint assert: early ∩ late = ∅ at the day level and the fill level.
    early_day_set = set(int(d) for d in np.unique(day[is_early])) if is_early.any() else set()
    late_day_set = set(int(d) for d in np.unique(day[is_late])) if is_late.any() else set()
    days_disjoint = len(early_day_set & late_day_set) == 0
    fills_disjoint = not bool((is_early & is_late).any())

    # early_tox per taker = early-half mean a_mid at THIS horizon (label uses ONLY early fills).
    valid_early = is_early & np.isfinite(a_mid_h)
    uniq, inv = np.unique(taker, return_inverse=True)
    cnt_e = np.bincount(inv[valid_early], minlength=uniq.size) if valid_early.any() else np.zeros(uniq.size)
    sum_e = np.bincount(inv[valid_early], weights=a_mid_h[valid_early],
                        minlength=uniq.size) if valid_early.any() else np.zeros(uniq.size)
    with np.errstate(invalid="ignore", divide="ignore"):
        early_tox = np.where(cnt_e > 0, sum_e / np.where(cnt_e > 0, cnt_e, np.nan), np.nan)

    eligible = (cnt_e >= K) & np.isfinite(early_tox)
    elig_pos = np.where(eligible)[0]
    n_eligible = int(elig_pos.size)

    toxic_taker_set = set()
    if n_eligible > 0:
        tox_vals = early_tox[elig_pos]
        # top TOXIC_DECILE_FRAC by early_tox (higher a_mid faced by maker = more toxic taker)
        n_toxic = max(1, int(np.ceil(n_eligible * TOXIC_DECILE_FRAC)))
        # rank descending; the toxic decile is the highest early_tox
        order = np.argsort(tox_vals)[::-1]
        toxic_local = order[:n_toxic]
        toxic_taker_set = set(int(uniq[elig_pos[j]]) for j in toxic_local)
    else:
        n_toxic = 0

    # decile assignment for every ELIGIBLE taker (1=least toxic .. 10=most toxic)
    decile_of_taker = {}
    if n_eligible > 0:
        tox_vals = early_tox[elig_pos]
        ranks = np.argsort(np.argsort(tox_vals))          # 0..n-1 ascending early_tox
        dec = np.minimum((ranks * 10) // n_eligible, 9) + 1
        for j, pos in enumerate(elig_pos):
            decile_of_taker[int(uniq[pos])] = int(dec[j])

    return {
        "uniq": uniq,
        "early_tox": early_tox,
        "eligible_mask_taker": eligible,
        "toxic_taker_set": toxic_taker_set,
        "decile_of_taker": decile_of_taker,
        "late_mask": is_late,
        "early_mask": is_early,
        "n_eligible": n_eligible,
        "n_toxic": int(n_toxic),
        "n_toxic_takers": len(toxic_taker_set),
        "days_disjoint": bool(days_disjoint),
        "fills_disjoint": bool(fills_disjoint),
        "early_day_set": sorted(early_day_set),
        "late_day_set": sorted(late_day_set),
    }


# ==================== baseline net (item 1) ====================
def baseline_net(arrs, late_mask, rng):
    """Symmetric maker net for BOTH independent measures, per coin x horizon x tier.

    Evaluated on the LATE half only. coin label 'pooled' = all late fills.
    """
    coin = arrs["coin"]
    notl = arrs["notional"]
    taker = arrs["taker_id"]
    blocks = {}
    coin_groups = [("BTC", 0), ("ETH", 1), ("pooled", -1)]
    t_block = artifact.start_clock()
    for ci, (cname, ccode) in enumerate(coin_groups):
        if ccode == -1:
            sel = late_mask
        else:
            sel = late_mask & (coin == ccode)
        if not sel.any():
            blocks[cname] = {"n_late_fills": 0, "note": "no late fills in this coin"}
            continue
        w = notl[sel]
        tk = taker[sel]
        per_h = {}
        for h in HORIZONS:
            per_h[f"h{h}"] = {
                "net_PRINT": _net_block(arrs[f"net_PRINT_{h}"][sel], w, rng,
                                        "net_PRINT", taker=tk, cell=(ci, h, 0)),
                "net_MID_lower": _net_block(arrs[f"net_MID_lower_{h}"][sel], w, rng,
                                            "net_MID_lower", taker=tk, cell=(ci, h, 1)),
            }
            print(f"[maker_econ] baseline {cname} h={h}s done "
                  f"({(time.time() - t_block) / 60:.1f} min into the baseline block)",
                  flush=True)
        blocks[cname] = {"n_late_fills": int(sel.sum()), "by_horizon": per_h}
    return blocks


# ==================== net by toxicity decile (item 2) ====================
def net_by_decile(arrs, late_mask, labels, horizon=H.HEADLINE_HORIZON_S):
    """Late-half maker net per taker early_tox decile (the toxic decile must be
    the most negative). Reported for net_MID_lower and net_PRINT at `horizon`,
    base fee tier and t4_0fee tier (the two reader-relevant tiers)."""
    taker = arrs["taker_id"]
    notl = arrs["notional"]
    decile_of = labels["decile_of_taker"]
    late_idx = np.where(late_mask)[0]
    # decile per late fill (only eligible takers carry a decile; others -> 0/skip)
    dec_fill = np.array([decile_of.get(int(taker[i]), 0) for i in late_idx])

    out = {"horizon_s": horizon, "tiers_reported": ["base", "t4_0fee"], "deciles": {}}
    for measure in ("net_MID_lower", "net_PRINT"):
        m_arr = arrs[f"{measure}_{horizon}"][late_idx]
        w_arr = notl[late_idx]
        for tier in ("base", "t4_0fee"):
            net = m_arr - MAKER_FEE_BPS[tier]
            for d in range(1, 11):
                sel = dec_fill == d
                key = f"decile_{d:02d}"
                out["deciles"].setdefault(key, {})
                out["deciles"][key].setdefault(measure, {})
                out["deciles"][key][measure][tier] = {
                    "n_fills": int(sel.sum()),
                    "net_vw_bps": _vw_mean(net[sel], w_arr[sel]) if sel.any() else float("nan"),
                    "net_ew_bps": _ew_mean(net[sel]) if sel.any() else float("nan"),
                }
    # convenience: most-negative-decile flag on net_MID_lower base tier
    base_vals = []
    for d in range(1, 11):
        cell = out["deciles"].get(f"decile_{d:02d}", {}).get("net_MID_lower", {}).get("base")
        base_vals.append((d, cell["net_vw_bps"] if cell else float("nan")))
    finite = [(d, v) for d, v in base_vals if v == v]
    if finite:
        worst = min(finite, key=lambda t: t[1])
        out["most_negative_decile_net_MID_lower_base"] = worst[0]
        out["toxic_decile_is_most_negative"] = bool(worst[0] == 10)
    else:
        out["most_negative_decile_net_MID_lower_base"] = None
        out["toxic_decile_is_most_negative"] = None
    return out


# ==================== B1 idealized policy + placebo (items 3,4) ====================
def _net_means_on_subset(arrs, idx, drop_taker_set, horizon, drop_codes=None):
    """Notional-weighted net per measure x tier over `idx` rows AFTER dropping all
    fills whose taker is in drop_taker_set. Returns nested {measure: {tier: vw}}.

    The membership test is a numpy set operation over the integer taker codes. It used
    to be a Python comprehension that converted each of the 1.24 million late rows to a
    Python int and asked a Python set about it, once per call, and the placebo below
    calls this function 8,008 times: 179 ms of the 253 ms each call took was that one
    line. The mask it produces is the same object either way, because integer
    membership carries no rounding and neither form reorders `idx`, so no number this
    function returns can move.

    drop_codes is the same set already in array form, passed by a caller that built it
    that way. It is an argument rather than a conversion because np.fromiter over a
    Python set is O(len(set)) and the placebo has one per draw already in hand.
    """
    taker = arrs["taker_id"]
    notl = arrs["notional"]
    if drop_taker_set:
        if drop_codes is None:
            drop_codes = np.fromiter(drop_taker_set, dtype=np.int64,
                                     count=len(drop_taker_set))
        keep = ~np.isin(taker[idx], drop_codes)
    else:
        keep = np.ones(idx.size, dtype=bool)
    kidx = idx[keep]
    res = {}
    for measure in ("net_MID_lower", "net_PRINT"):
        m_arr = arrs[f"{measure}_{horizon}"][kidx]
        w_arr = notl[kidx]
        res[measure] = {}
        for tier in FEE_TIERS:
            res[measure][tier] = _vw_mean(m_arr - MAKER_FEE_BPS[tier], w_arr)
    res["_n_kept"] = int(kidx.size)
    res["_kept_notional"] = float(notl[kidx].sum())
    return res


def b1_policy(arrs, late_mask, labels, rng, horizon=H.HEADLINE_HORIZON_S,
              K=K_HEADLINE):
    """B1 idealized policy (UPPER BOUND): drop the persistently-toxic decile takers
    on the LATE half and measure Delta-net vs baseline, per measure x fee tier.

    Labeled an upper bound: it assumes perfect per-counterparty control (you decline
    the toxic taker entirely). The fill-aware policy (B2: quote wider, lose some
    benign fills) is future work and will be <= this bound.

    `K` is the wallet-fill floor the label set was built at. It is carried rather than
    left to be read off the key the block is filed under: this file now publishes eight
    rungs, and a block that does not state its own rung is one a reader has to hold a
    path in their head to interpret.
    """
    late_idx = np.where(late_mask)[0]
    toxic_set = labels["toxic_taker_set"]

    base = _net_means_on_subset(arrs, late_idx, set(), horizon)
    dropped = _net_means_on_subset(arrs, late_idx, toxic_set, horizon)

    # notional dropped by the toxicity screen (for the same-notional placebo)
    taker = arrs["taker_id"]
    notl = arrs["notional"]
    toxic_fill = np.array([int(taker[i]) in toxic_set for i in late_idx]) if toxic_set else np.zeros(late_idx.size, bool)
    toxic_notional = float(notl[late_idx][toxic_fill].sum())
    late_total_notional = float(notl[late_idx].sum())

    delta = {}
    flips = {}
    for measure in ("net_MID_lower", "net_PRINT"):
        delta[measure] = {}
        flips[measure] = {}
        for tier in FEE_TIERS:
            b = base[measure][tier]
            d = dropped[measure][tier]
            dn = (d - b) if (b == b and d == d) else float("nan")
            delta[measure][tier] = dn
            # does dropping the toxic decile flip net negative -> positive?
            flips[measure][tier] = bool((b == b and d == d) and (b < 0) and (d >= 0))

    return {
        "label": "B1 IDEALIZED UPPER BOUND on the toxicity-skew value: perfect "
                 "per-counterparty control (decline the persistently-toxic decile). "
                 "The deployable fill-aware policy (B2: quote wider, lose some benign "
                 "fills) is future work and is bounded ABOVE by this number.",
        "horizon_s": horizon,
        "min_early_fills": int(K),
        "rung_declared_in": rung_declared_in(K),
        "n_eligible_takers": labels["n_eligible"],
        "n_toxic_takers_dropped": labels["n_toxic_takers"],
        "toxic_late_notional_dropped": toxic_notional,
        "late_total_notional": late_total_notional,
        "toxic_notional_frac": (toxic_notional / late_total_notional
                                if late_total_notional > 0 else float("nan")),
        "baseline_net_vw_bps": {m: base[m] for m in ("net_MID_lower", "net_PRINT")},
        "policy_net_vw_bps": {m: dropped[m] for m in ("net_MID_lower", "net_PRINT")},
        "delta_net_vw_bps": delta,
        "delta_uncertainty": _b1_delta_uncertainty(arrs, late_idx, toxic_set, K, horizon),
        "flips_negative_to_positive": flips,
    }


# The whale arms this file reports beside the gain, and the count is FIVE and not the ten
# settings.WHALE_DROP_K declares, because the question is a different one: ten is the
# venue-level "is this ten wallets" arm t3_capacity.py and t1 run over the whole book,
# and five is the arm the ladder's claim is stated in -- whether the gain at a given
# floor survives removing the five largest of the wallets the screen itself declines.
# Both criteria are computed because the tree already knows the two answer different
# questions and has a key shape that says which is which: by NOTIONAL asks whether the
# gain is a volume artifact, by GROSS_COST whether it is five expensive counterparties.
# Reporting one alone under a key naming only the count is the exact confusion
# settings.whale_drop exists to prevent.
WHALE_ARM_K = 5
WHALE_ARM_CRITERIA = ("notional", "gross_cost")


def _b1_delta_uncertainty(arrs, late_idx, toxic_set, K, horizon):
    """The B1 gain resampled at the WALLET, with the whale arms, per measure.

    ONE INTERVAL PER MEASURE AND NOT ONE PER FEE TIER, because the fee cancels from the
    difference exactly -- see _boot_wallet_delta, where the cancellation is derived and
    the committed artifact that confirms it is named. The block says so in a field
    rather than leaving a reader to wonder which tier the interval belongs to.

    The whale arms remove the named wallets from BOTH arms of the difference, so what
    they answer is "does the remaining flow still show the gain", not "what if we had
    declined fewer wallets".
    """
    taker = arrs["taker_id"]
    notl = arrs["notional"]
    out = {
        "cluster_level": "taker wallet (taker_id)",
        "n_boot": N_BOOT,
        "resample": "wallet groups, m out of m, statistic recomputed per draw",
        "fee_tier_note": ("the gain is the difference of two weighted means of the same "
                          "measure, so the fee leaves it exactly; one interval covers "
                          "all six tiers and the point estimates under delta_net_vw_bps "
                          "are identical across tiers for the same reason"),
        "whale_arms": {"k": WHALE_ARM_K, "criteria": list(WHALE_ARM_CRITERIA)},
        "by_measure": {},
    }
    for mi, measure in enumerate(("net_MID_lower", "net_PRINT")):
        vals = arrs[f"{measure}_{horizon}"][late_idx]
        w = notl[late_idx]
        tk = taker[late_idx]
        num_w, den_w, uniq_w, n_kept = _wallet_partials(vals, w, tk)
        if uniq_w.size < 2:
            out["by_measure"][measure] = {"note": "too few wallet clusters"}
            continue
        is_toxic_w = np.isin(uniq_w, np.fromiter(toxic_set, dtype=np.int64,
                                                 count=len(toxic_set))
                             if toxic_set else np.empty(0, np.int64))
        keep_w = ~is_toxic_w
        boots = _boot_wallet_delta(num_w, den_w, keep_w,
                                   _cell_rng(K, horizon, mi, 2))
        ci = _pctile_ci(boots)
        cell = {
            "n_wallets": int(uniq_w.size),
            "n_toxic_wallets": int(is_toxic_w.sum()),
            "n_rows_in_clusters": n_kept,
            "delta_vw_bps": (float(num_w[keep_w].sum() / den_w[keep_w].sum()
                                   - num_w.sum() / den_w.sum())
                             if den_w[keep_w].sum() > 0 and den_w.sum() > 0
                             else float("nan")),
            "ci95_wallet_clustered": ci,
            "ci_excludes_zero": bool(ci[0] == ci[0] and (ci[0] > 0 or ci[1] < 0)),
            "whale_dropped": {},
        }
        # The whale arms: rank the TOXIC wallets, remove the top k from both arms.
        tox_pos = np.where(is_toxic_w)[0]
        for crit in WHALE_ARM_CRITERIA:
            key = H.whale_drop(crit, WHALE_ARM_K)["key"]
            if tox_pos.size == 0:
                cell["whale_dropped"][key] = {"note": "no toxic wallet at this rung"}
                continue
            if crit == "notional":
                rank_by = den_w[tox_pos]                 # late notional per wallet
            else:                                        # gross_cost
                rank_by = -num_w[tox_pos]                # most costly to the maker first
            drop_pos = tox_pos[np.argsort(-rank_by)[:WHALE_ARM_K]]
            alive = np.ones(uniq_w.size, dtype=bool)
            alive[drop_pos] = False
            n2, d2, k2 = num_w[alive], den_w[alive], keep_w[alive]
            b2 = _boot_wallet_delta(n2, d2, k2,
                                    _cell_rng(K, horizon, mi,
                                              3 + WHALE_ARM_CRITERIA.index(crit)))
            ci2 = _pctile_ci(b2)
            cell["whale_dropped"][key] = {
                "criterion": crit,
                "k": WHALE_ARM_K,
                "n_wallets_after_drop": int(alive.sum()),
                "delta_vw_bps": (float(n2[k2].sum() / d2[k2].sum() - n2.sum() / d2.sum())
                                 if d2[k2].sum() > 0 and d2.sum() > 0 else float("nan")),
                "ci95_wallet_clustered": ci2,
                "ci_excludes_zero": bool(ci2[0] == ci2[0]
                                         and (ci2[0] > 0 or ci2[1] < 0)),
            }
        out["by_measure"][measure] = cell
    return out


def placebo_random_drop(arrs, late_mask, labels, rng, horizon=H.HEADLINE_HORIZON_S,
                        n_perm=N_PERM, cell=""):
    """Drop a RANDOM same-late-notional set of takers (seeded); Delta-net must be
    ~0, and the toxicity-drop Delta must BEAT it. Permutation p over n_perm draws,
    p-floor = 1/(n_perm+1). Compared on net_MID_lower at the base + t4_0fee tiers.

    `cell` names which (K, horizon) block is running and is printed in the progress
    line. It carries no meaning for any number here: four of these blocks run one after
    another and a progress line that did not say which was speaking would report a
    fraction of something the reader cannot identify.
    """
    t_cell = artifact.start_clock()
    late_idx = np.where(late_mask)[0]
    taker = arrs["taker_id"]
    notl = arrs["notional"]
    toxic_set = labels["toxic_taker_set"]
    eligible = labels["eligible_mask_taker"]
    uniq = labels["uniq"]

    # per-late-taker notional, restricted to eligible takers (the pool we draw from)
    elig_taker_ids = set(int(uniq[i]) for i in np.where(eligible)[0])
    late_taker = taker[late_idx]
    late_notl = notl[late_idx]
    # notional per eligible late-taker
    taker_notional = {}
    for tid, nt in zip(late_taker, late_notl):
        tid = int(tid)
        if tid in elig_taker_ids:
            taker_notional[tid] = taker_notional.get(tid, 0.0) + float(nt)

    target_notional = sum(taker_notional.get(t, 0.0) for t in toxic_set)

    base = _net_means_on_subset(arrs, late_idx, set(), horizon)

    def delta_from(means, tier, measure="net_MID_lower"):
        """One tier's Delta read out of a subset's means, which the caller computed.

        The tier used to be an argument to the RECOMPUTE and not to the read-out, so
        the two tiers cost two identical passes over the late rows for one draw --
        _net_means_on_subset is a pure function of (arrs, late_idx, drop_set, horizon)
        and returns every tier, so the second pass was recomputing an answer already
        in hand. Halving the passes changes nothing it returns.
        """
        b = base[measure][tier]
        dd = means[measure][tier]
        return (dd - b) if (b == b and dd == dd) else float("nan")

    # observed toxicity-drop deltas
    obs_means = _net_means_on_subset(arrs, late_idx, toxic_set, horizon)
    obs = {tier: delta_from(obs_means, tier) for tier in ("base", "t4_0fee")}

    # random draws: walk the shuffled eligible takers, accumulating notional, and stop
    # at the first prefix that reaches ~target_notional; the random Delta-net
    # distribution should center on 0.
    #
    # THE WALK IS A CUMULATIVE SUM AND THE DRAWS ARE UNCHANGED. rng.permutation is
    # called once per draw exactly as before, in the same place in the same order, so
    # the stream of random numbers this loop consumes is the same stream: what changed
    # is only how the shuffled order is turned into a set. The old loop tested the
    # running total BEFORE adding the next counterparty and required a non-empty set,
    # which stops it at the first prefix reaching the target and takes the whole pool
    # when none does; both of those are what the arithmetic below reproduces. Python
    # float addition and np.cumsum accumulate a float64 array in the same order, so the
    # running totals are equal to the last bit and not merely close.
    eligible_ids = list(taker_notional.keys())
    id_arr = np.fromiter(eligible_ids, dtype=np.int64, count=len(eligible_ids))
    notional_arr = np.fromiter((taker_notional[t] for t in eligible_ids),
                               dtype=np.float64, count=len(eligible_ids))
    perm_deltas = {tier: [] for tier in ("base", "t4_0fee")}
    beat_count = {tier: 0 for tier in ("base", "t4_0fee")}
    for draw in range(n_perm):
        order = rng.permutation(len(eligible_ids))
        csum = np.cumsum(notional_arr[order])
        reached = np.flatnonzero(csum >= target_notional)
        n_take = int(reached[0]) + 1 if reached.size else order.size
        drop_codes = id_arr[order[:n_take]]
        drop_set = set(int(t) for t in drop_codes)
        means = _net_means_on_subset(arrs, late_idx, drop_set, horizon,
                                     drop_codes=drop_codes)
        for tier in ("base", "t4_0fee"):
            dperm = delta_from(means, tier)
            perm_deltas[tier].append(dperm)
            # toxicity drop should be MORE positive (better) than a random drop.
            # one-sided: count permutations whose Delta >= observed toxicity Delta.
            if dperm == dperm and obs[tier] == obs[tier] and dperm >= obs[tier] - 1e-12:
                beat_count[tier] += 1
        artifact.progress(f"maker_econ placebo {cell}", draw + 1, n_perm, t_cell)

    # WHY THE COUNT ABOVE IS NOT stats.permutation_p, restated 2026-07-31 after checking
    # each reason instead of listing them. Only ONE of the three differences this note
    # used to name actually blocks the move, and saying so matters, because two wrong
    # reasons make a right one unfalsifiable.
    #
    # THE ONE THAT BINDS IS THE DENOMINATOR. This block divides by the REQUESTED budget:
    # a draw that came back as no number is not counted as extreme (the `dperm == dperm`
    # guard above) and stays in n_perm all the same. stats.permutation_p divides by the
    # count of draws that came back finite, which is the better rule and is argued in
    # that module's docstring -- and it is a different number whenever one draw fails.
    # Nothing here proves no draw fails: delta_from returns no number whenever the
    # subset's weighted mean does, so the equality holds on the runs where it holds and
    # cannot be asserted in advance. A move that MIGHT change a published p is a measured
    # change owed its own recompute, not a rename, and the module offers no way to ask
    # for the requested denominator.
    #
    # THE OTHER TWO DO NOT BIND, and are recorded so nobody re-derives them as blockers.
    # The generator is irrelevant: permutation_p takes an array of draws already in hand
    # and never draws anything, so seeding this loop per (SEED, K, horizon) is invisible
    # to it -- it is permutation_test, the variant with the draw loop, that would impose
    # a cell-seeded stream. And the slack is passable: abs_tol=1e-12 asks for exactly the
    # absolute comparison this loop makes, which is how t1_toxicity_skew_backtest.py
    # keeps its own two placebo p-values unmoved through that same function.
    #
    # The floor has one home and is taken from it.
    out = {
        "horizon_s": horizon,
        "measure": "net_MID_lower",
        "target_late_notional_matched": target_notional,
        "n_perm": n_perm,
        "p_floor": stats.p_floor(n_perm),
        "by_tier": {},
    }
    for tier in ("base", "t4_0fee"):
        arr = np.array([d for d in perm_deltas[tier] if d == d], dtype=np.float64)
        out["by_tier"][tier] = {
            "observed_toxicity_delta_net_vw_bps": obs[tier],
            "random_drop_mean_delta_net_vw_bps": float(arr.mean()) if arr.size else float("nan"),
            "random_drop_std_delta_net_vw_bps": float(arr.std()) if arr.size else float("nan"),
            "permutation_p": (beat_count[tier] + 1) / (n_perm + 1),
            "toxicity_beats_random": bool(
                obs[tier] == obs[tier] and arr.size
                and obs[tier] > float(arr.mean())),
        }
    return out


# ==================== cross-checks (item 5) ====================
def cross_checks(arrs, align_ok, labels):
    """Explicit booleans/numbers the verifier can attack."""
    checks = {}

    # --- s_bbo >= 0 fraction ---
    s_bbo = arrs["s_bbo"]
    sf = s_bbo[np.isfinite(s_bbo)]
    checks["s_bbo_nonneg_frac"] = float((sf >= 0).mean()) if sf.size else float("nan")
    checks["s_bbo_all_nonneg"] = bool(sf.size and (sf >= 0).all())

    # --- mean s_approx, mean s_bbo, (s_approx >= s_bbo) flag, per horizon ---
    s_approx_block = {}
    for h in HORIZONS:
        sa = arrs[f"s_approx_{h}"]
        m = np.isfinite(sa) & np.isfinite(s_bbo)
        mean_sa = float(sa[m].mean()) if m.any() else float("nan")
        mean_sb = float(s_bbo[m].mean()) if m.any() else float("nan")
        s_approx_block[f"h{h}"] = {
            "mean_s_approx_bps": mean_sa,
            "mean_s_bbo_bps": mean_sb,
            "s_approx_ge_s_bbo_mean": bool(mean_sa == mean_sa and mean_sb == mean_sb
                                           and mean_sa >= mean_sb),
        }
    checks["s_approx_vs_s_bbo"] = s_approx_block

    # --- net_PRINT vs net_MID_lower sign-agreement + gap, per coin/tier (h=60) ---
    coin = arrs["coin"]
    notl = arrs["notional"]
    sign_block = {}
    for cname, ccode in (("BTC", 0), ("ETH", 1), ("pooled", -1)):
        sel = np.ones(coin.size, bool) if ccode == -1 else (coin == ccode)
        sign_block[cname] = {}
        for tier in ("base", "t4_0fee"):
            np_net = arrs["net_PRINT_60"][sel] - MAKER_FEE_BPS[tier]
            mid_net = arrs["net_MID_lower_60"][sel] - MAKER_FEE_BPS[tier]
            vw_p = _vw_mean(np_net, notl[sel])
            vw_m = _vw_mean(mid_net, notl[sel])
            same_sign = bool(vw_p == vw_p and vw_m == vw_m
                             and (np.sign(vw_p) == np.sign(vw_m)
                                  or abs(vw_p) < 1e-9 or abs(vw_m) < 1e-9))
            sign_block[cname][tier] = {
                "net_PRINT_vw_bps": vw_p,
                "net_MID_lower_vw_bps": vw_m,
                "sign_agree": same_sign,
                "gap_bps": (abs(vw_p - vw_m) if (vw_p == vw_p and vw_m == vw_m) else float("nan")),
            }
    checks["two_measure_agreement_h60"] = sign_block

    # --- m8 reconciliation: ungrouped == maker-grouped == taker-grouped (mo60) ---
    # signed-markout dollar cost = (a_print_60/1e4) * notional, summed under each
    # partition (an accounting identity; reproduces m8's $2.55M and faced markout).
    a_print_score = arrs[f"a_print_{H.HEADLINE_HORIZON_S}"]
    fin = np.isfinite(a_print_score) & np.isfinite(notl) & (notl >= 0)
    row_cost = (a_print_score[fin] / 1e4) * notl[fin]
    ungrouped = float(row_cost.sum())

    def _grouped(keys):
        kk = keys[fin]
        if kk.size == 0:
            return None
        u, iv = np.unique(kk, return_inverse=True)
        s = np.zeros(u.size, dtype=np.float64)
        np.add.at(s, iv, row_cost)
        return float(s.sum())

    mk = _grouped(arrs["taker_id"] * 0 + 1)  # trivial guard partition (all-one key)
    maker_grp = None  # maker_id not loaded here; taker/ungrouped suffice for identity
    taker_grp = _grouped(arrs["taker_id"])
    # vw faced a_print and a_mid for the m8/contract magnitude reconciliation
    checks["m8_reconciliation"] = {
        "metric": (f"signed-markout $cost on a_print_{H.HEADLINE_HORIZON_S} "
                   f"(= {H.headline_print_col()}): partition-invariant"),
        "ungrouped_signed_cost_quote": ungrouped,
        "taker_grouped_signed_cost_quote": taker_grp,
        "ungrouped_eq_taker_grouped": bool(
            taker_grp is not None and abs(ungrouped - taker_grp) <= max(1.0, abs(ungrouped) * 1e-9)),
        f"vw_a_print_{H.HEADLINE_HORIZON_S}_bps": _vw_mean(a_print_score, notl),
        "vw_a_mid_60_bps": _vw_mean(arrs["a_mid_60"], notl),
        "note": ("ungrouped == taker-grouped by construction (each fill counted "
                 "once); vw_a_mid_60 reproduces m8's +1.9-2.1 bps faced markout and "
                 "the ungrouped cost reproduces the ~$2.55M signed-markout cost on "
                 "the full window. maker-grouped equality is the same identity (m8 "
                 "verifies it directly)."),
    }

    # --- OOS disjoint assert ---
    checks["oos_disjoint"] = {
        "early_days": labels["early_day_set"],
        "late_days": labels["late_day_set"],
        "days_disjoint": labels["days_disjoint"],
        "fills_disjoint": labels["fills_disjoint"],
        "label_uses_only_early": True,
        "note": "early ∩ late = ∅; toxic label uses ONLY early fills; no late fill "
                "enters the label; all P&L/policy evaluated on late fills only.",
    }

    # --- nan-drop fraction for the MID measures + print measures ---
    nan_block = {}
    for h in HORIZONS:
        am = arrs[f"a_mid_{h}"]
        ap = arrs[f"a_print_{h}"]
        ml = arrs[f"net_MID_lower_{h}"]
        nan_block[f"h{h}"] = {
            "a_mid_nan_frac": float(np.mean(np.isnan(am))),
            "a_print_nan_frac": float(np.mean(np.isnan(ap))),
            "net_MID_lower_nan_frac": float(np.mean(np.isnan(ml))),
        }
    checks["nan_drop_frac"] = nan_block

    return checks


# ==================== main ====================
def main():
    t0 = artifact.start_clock()
    print(f"[maker_econ] seed={SEED}")
    arrs, align_ok, slice_meta = load_aligned()
    n_rows = int(arrs["taker_id"].size)
    print(f"[maker_econ] loaded {n_rows:,} aligned fills "
          f"(sliced={slice_meta['sliced']} days={slice_meta['days']} coins={slice_meta['coins']})")
    print(f"[maker_econ] row-alignment: {align_ok}")

    rng = np.random.default_rng(SEED)

    # ---- OOS labels, one label set per (K, horizon) ----
    # A label set built on one horizon and spent on another is a HYBRID: it books
    # the gain a short-horizon measurement shows while charging only the notional
    # a long-horizon screen declines, which flatters the efficiency of the screen.
    # Every block below therefore ranks and measures on ONE horizon.
    labels_by_K_h = {}
    print(f"[maker_econ] ladder of wallet-fill floors: {list(K_RUNGS)}; "
          f"headline K{K_HEADLINE}; permutation null on {list(PLACEBO_RUNGS)}",
          flush=True)
    t_lab = artifact.start_clock()
    for K in K_RUNGS:
        for h in POLICY_HORIZONS:
            labels_by_K_h[(K, h)] = build_toxicity_labels(arrs, K, horizon=h)
            lb = labels_by_K_h[(K, h)]
            print(f"[maker_econ] labels K={K} h={h}s: eligible takers={lb['n_eligible']:,} "
                  f"toxic decile takers={lb['n_toxic_takers']:,} "
                  f"days_disjoint={lb['days_disjoint']} fills_disjoint={lb['fills_disjoint']} "
                  f"({(time.time() - t_lab) / 60:.1f} min into labels)", flush=True)

    # late_mask is day-based, so it is identical across K and across the horizon.
    late_mask = labels_by_K_h[(K_HEADLINE, LABEL_ANCHOR_HORIZON)]["late_mask"]

    # ---- item 1: baseline symmetric maker net (both measures), late half ----
    # Symmetric, no screen, so this block uses no labels at all.
    print("[maker_econ] baseline block starting (18 cells, two intervals each)",
          flush=True)
    baseline = baseline_net(arrs, late_mask, rng)

    # ---- item 2: net by toxicity decile, ranked and measured on the same horizon ----
    # EVERY RUNG, because the decile table is what says the toxic decile is the most
    # negative one, and a rung whose gain is published without it is a gain with no
    # statement of where in the distribution it came from.
    decile_blocks = {}
    t_dec = artifact.start_clock()
    for K in K_RUNGS:
        decile_blocks[f"K{K}"] = {
            f"h{h}": net_by_decile(arrs, late_mask, labels_by_K_h[(K, h)], horizon=h)
            for h in POLICY_HORIZONS
        }
        print(f"[maker_econ] decile table K={K} done "
              f"({(time.time() - t_dec) / 60:.1f} min into the decile block)", flush=True)

    # ---- item 3: B1 idealized policy (upper bound), per fee tier ----
    b1_blocks = {}
    t_b1 = artifact.start_clock()
    for K in K_RUNGS:
        b1_blocks[f"K{K}"] = {
            f"h{h}": b1_policy(arrs, late_mask, labels_by_K_h[(K, h)], rng,
                               horizon=h, K=K)
            for h in POLICY_HORIZONS
        }
        head = b1_blocks[f"K{K}"][f"h{H.HEADLINE_HORIZON_S}"]
        gain = head["delta_net_vw_bps"]["net_MID_lower"]["base"]
        ci = head["delta_uncertainty"]["by_measure"]["net_MID_lower"]["ci95_wallet_clustered"]
        print(f"[maker_econ] B1 K={K} h={H.HEADLINE_HORIZON_S}s: eligible="
              f"{head['n_eligible_takers']:,} toxic={head['n_toxic_takers_dropped']:,} "
              f"gain={gain:+.4f} bps ci95_wallet=[{ci[0]:+.4f},{ci[1]:+.4f}] "
              f"({(time.time() - t_b1) / 60:.1f} min into the B1 block)", flush=True)

    # ---- item 4: placebo (random same-notional drop), ONE PER HORIZON ----
    # Every horizon that gets a Delta-net gets its own null; a policy horizon
    # without one reports an effect with no p. The K{K} key keeps holding the
    # anchor block so nothing reading it breaks, and by_horizon carries all of
    # them. Seeded per (K, h) so a cell reproduces on its own, independent of
    # the order POLICY_HORIZONS happens to be written in.
    placebo_blocks = {}
    for K in PLACEBO_RUNGS:
        per_h = {
            f"h{h}": placebo_random_drop(
                arrs, late_mask, labels_by_K_h[(K, h)],
                np.random.default_rng([SEED, K, h]), horizon=h, cell=f"K={K} h={h}s")
            for h in POLICY_HORIZONS
        }
        anchor = dict(per_h[f"h{LABEL_ANCHOR_HORIZON}"])
        anchor["by_horizon"] = per_h
        anchor["placebo_seed_policy"] = (
            "default_rng([SEED, K, horizon]) per cell, not the shared stream")
        placebo_blocks[f"K{K}"] = anchor

    # ---- item 5: cross-checks ----
    # cross_checks reads only the day-based label fields, which do not move with
    # the horizon, so the anchor label set is representative here.
    checks = cross_checks(arrs, align_ok, labels_by_K_h[(K_HEADLINE, LABEL_ANCHOR_HORIZON)])

    # The split the run actually used, derived from the days the input carries. Reported
    # in _meta so the artifact states its own halves instead of promising them.
    early_run, late_run = early_late_days(arrs["day"])

    # Which settings produced these numbers, so a figure lifted out of this file still
    # knows what it was computed under. All four migrating settings are stated, so
    # nothing lands in declared_not_confirmed. Two of them genuinely differ from the
    # declaration and say why. Handed to artifact.write as keyword arguments rather
    # than built here, so the block is stamped by the one function that writes
    # artifacts and cannot end up in two places.
    settings_used = {
        "h": LABEL_ANCHOR_HORIZON,
        "lens": "mid",
        "master_seed": SEED,
        "n_perm": N_PERM,
        "n_boot": N_BOOT,
        "rank_floor_fills": K_HEADLINE,
        # What the RUN swept, which since 2026-08-03 is wider than the declared sweep:
        # the fingerprint states what happened and not what a declaration says.
        "rank_floor_sensitivity": list(K_RUNGS),
        "policy_horizons_s": list(POLICY_HORIZONS),
        "early_days": list(early_run),
        "late_days": list(late_run),
        "override_reasons": {
            "master_seed": f"the streams here are seeded {SEED}, not the declared "
                           f"{H.MASTER_SEED}; settings.MASTER_SEED carries the "
                           f"state 'target', so adopting it re-draws every "
                           f"placebo stream and moves the published p-values",
            "n_boot": f"the run drew {N_BOOT} resamples, which IS the declared "
                      f"{H.N_BOOT}: stated as a CONFIRMATION and not as a "
                      f"deviation. It was 1000 until 2026-07-31, half the "
                      f"declaration, so every confidence interval in this file "
                      f"moved with the adoption and no point estimate did",
            "rank_floor_fills": f"the headline cell gates takers at {K_HEADLINE} "
                                f"early fills, which IS the declared "
                                f"{H.RANK_FLOOR_FILLS}: a CONFIRMATION and not a "
                                f"deviation. It was 10 until 2026-07-31, and this "
                                f"file was one of the four reasons the "
                                f"declaration stood as a target. The reported sweep "
                                f"is {list(K_RUNGS)} since 2026-08-03 and is WIDER "
                                f"than the declared {list(K_LIST)}: four rungs come "
                                f"from settings.RANK_FLOOR_SENSITIVITY and four more "
                                f"({list(LOW_RUNGS_LOCAL)}) are declared in "
                                f"maker_econ.py, which is a debt recorded there. The "
                                f"10-fill arm is the robustness companion",
        },
    }
    anchor_labels = labels_by_K_h[(K_HEADLINE, LABEL_ANCHOR_HORIZON)]
    scope = {
        "population": (f"{n_rows:,} row-aligned fills; every net figure is measured on "
                       f"the {int(late_mask.sum()):,} LATE-half fills, and the toxic cut "
                       f"is the top {int(TOXIC_DECILE_FRAC * 100)}% of the "
                       f"{anchor_labels['n_eligible']:,} takers with at least "
                       f"{K_HEADLINE} early fills, which is "
                       f"{anchor_labels['n_toxic_takers']:,} wallets"),
        "window": (f"single December window; early days {list(early_run)}, late days "
                   f"{list(late_run)}"),
        "coins": sorted(COIN_NAME.values()),
        "env_slice": slice_meta,
        "note": ("computed entirely on-disk from the two intermediates; no S3 re-pull. "
                 "env_slice says whether CAP_DAYS or CAP_COINS narrowed the population "
                 "for a smoke run, which is the one thing that would make the counts "
                 "above describe less than the whole input"),
    }

    # ---- assemble results ----
    results = {
        "_meta": {
            "object": "maker net-economics (RQ3 economic materiality)",
            "author": "Dmitry Stakhin",
            "date": "2026-06-21",
            "track": "11 (Cryptocurrency Markets - Microstructure)",
            "seed": SEED,
            "n_rows": n_rows,
            "row_alignment_ok": align_ok,
            "env_slice": slice_meta,
            "fee_source": FEE_SOURCE,
            "maker_fee_bps": MAKER_FEE_BPS,
            "taker_fee_ref_bps": TAKER_FEE_REF_BPS,
            "fee_tiers": list(FEE_TIERS),
            "k_headline": K_HEADLINE,
            "k_list": list(K_LIST),
            "k_rungs_computed": list(K_RUNGS),
            "k_rungs_with_permutation_null": list(PLACEBO_RUNGS),
            "k_rung_declarations": {f"K{K}": rung_declared_in(K) for K in K_RUNGS},
            "ladder_policy": (
                "EIGHT RUNGS ARE PUBLISHED, keyed K<fills>, and they carry different "
                "blocks on purpose. Every rung has its label set, its decile table, its "
                "B1 gain and a WALLET-CLUSTERED interval on that gain with two whale "
                "arms. Only the rungs in k_rungs_with_permutation_null carry the "
                "2000-draw permutation placebo, which is the run's dominant cost at "
                "about 136 s per rung and horizon against about 2 s for everything "
                "else at that cell, measured 2026-08-03. That is a stated bar and not "
                "an omission: the placebo block's observed_toxicity_delta is the same "
                "arithmetic as the B1 block's delta_net_vw_bps at the same cell, so a "
                "rung without a null still publishes its gain and its interval, and "
                "what it does not publish is a p. Before 2026-08-03 only K10 and K50 "
                "existed here at all, and the six rungs between and around them were "
                "reported in prose from a scratch run whose output never entered the "
                "tree. k_rung_declarations says, rung by rung, which declaration puts "
                "that floor on the ladder; the four rungs below ten are declared in "
                "maker_econ.py itself and that is recorded as a debt."
            ),
            "horizons_s": list(HORIZONS),
            "policy_horizons_s": list(POLICY_HORIZONS),
            "label_horizon_policy": (
                "LABELS AND MEASUREMENT SHARE ONE HORIZON WITHIN EVERY BLOCK. The "
                "hXX key of net_by_toxicity_decile and of "
                "b1_idealized_policy_upper_bound means: takers were RANKED on the "
                "early-window mean a_mid at XX seconds AND the late-window P&L was "
                "MEASURED at XX seconds. No block mixes a ranking horizon with a "
                "different measurement horizon. This matters because a mixed block "
                "books the gain the shorter measurement shows while charging only "
                "the notional the longer screen declines, which overstates how "
                "efficient the screen is. Eligibility (at least K early fills with a "
                "finite a_mid) is counted at the block's own horizon too, so the "
                "eligible and toxic taker sets differ slightly between horizons. "
                "baseline_net is symmetric and uses no labels. placebo_random_drop "
                "is reported at the anchor horizon only, with that horizon's labels. "
                "cross_checks reads only day-based label fields, which do not move "
                "with the horizon."
            ),
            "label_anchor_horizon_s": LABEL_ANCHOR_HORIZON,
            "early_days": list(early_run),
            "late_days": list(late_run),
            "split_rule": (
                "The label and evaluation halves are DERIVED from the days present, by "
                "settings.split_early_late: first ceil(n/2) days early, the rest late. "
                "They used to be the hardcoded day-of-month tuples (4,5,6,7,8) and "
                "(9,10,11,12,13), which are correct only for a window opening on the 4th "
                "and closing on the 13th. This input does open on the 4th, so the "
                "derived split reproduces those tuples exactly and no number moved."
            ),
            "toxic_decile_frac": TOXIC_DECILE_FRAC,
            "measures": {
                "net_PRINT": "-a_print_h (mirror of taker print gain; nets entry "
                             "spread; INDEPENDENT measure 1; uses quickwin_markouts.npz)",
                "net_MID_lower": "s_bbo - a_mid_h, s_bbo = spread_entry_bps/2 "
                                 "(BBO half-spread, LOWER BOUND on maker income; "
                                 "INDEPENDENT measure 2; uses quickwin_markouts_mid.npz)",
                "net_MID_approx": "s_approx - a_mid_h = -a_print (wiring tautology, "
                                  "NOT independent; guard only)",
                "s_approx": "a_mid_h - a_print_h (mean-unbiased realized half-spread; "
                            "must exceed s_bbo on average)",
            },
            "sign_convention": "a_mid/a_print positive = maker adverse-selected; "
                               "maker_net positive = the maker earns net of fees.",
            "policy_label": "B1 = idealized UPPER BOUND (perfect per-counterparty "
                            "control); fill-aware B2 is future work and bounded above.",
            "no_repull": "computed entirely on-disk from the two npz; no S3 re-pull.",
        },
        "baseline_net": baseline,
        "net_by_toxicity_decile": decile_blocks,
        "b1_idealized_policy_upper_bound": b1_blocks,
        "placebo_random_drop": placebo_blocks,
        "cross_checks": checks,
    }

    # artifact.write records the producer with the hash of its own bytes, the two
    # intermediates it read with theirs, the scope, the settings block and the runtime,
    # in the one shape every results file in this tree carries. The inputs are named
    # relatively and resolved against this script's directory, so no local path reaches
    # the file.
    artifact.write(
        os.path.basename(OUT_JSON), results, script=__file__,
        inputs=[os.path.basename(MID_NPZ), os.path.basename(PRINT_NPZ)],
        scope=scope, started=t0, settings=settings_used,
        out_dir=os.path.dirname(OUT_JSON))

    _print_console(results)
    print(f"\n[maker_econ] wrote {os.path.basename(OUT_JSON)}")


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
    print("\n" + "=" * 84)
    print("MAKER NET-ECONOMICS (RQ3) - SUMMARY")
    print("=" * 84)
    print(f"  rows={meta['n_rows']:,}  seed={meta['seed']}  no-repull (on-disk).")
    print(f"  fee source: {meta['fee_source'][:72]}...")
    print(f"  measures: net_PRINT = -a_print ; net_MID_lower = s_bbo - a_mid "
          f"(s_bbo=spread/2, lower bound).")
    print(f"  OOS: EARLY={meta['early_days']} to LATE={meta['late_days']}; "
          f"toxic decile = top {int(meta['toxic_decile_frac']*100)}% by early a_mid, "
          f"ranked at the same horizon the block measures on "
          f"(policy horizons {meta['policy_horizons_s']}s).")

    # ---- baseline (pooled, h=60) ----
    print("-" * 84)
    print("1) BASELINE symmetric maker net (POOLED, h=60s, late half), vw bps:")
    pooled = results["baseline_net"].get("pooled", {})
    if pooled.get("n_late_fills"):
        bh = pooled["by_horizon"]["h60"]
        print(f"   {'tier':<10} {'net_PRINT':>12} {'net_MID_lower':>14}")
        for tier in FEE_TIERS:
            p = bh["net_PRINT"]["by_fee_tier"][tier]["net_vw_bps"]
            m = bh["net_MID_lower"]["by_fee_tier"][tier]["net_vw_bps"]
            print(f"   {tier:<10} {_f(p):>12} {_f(m):>14}")
        print(f"   gross pre-fee: net_PRINT={_f(bh['net_PRINT']['gross_prefee_vw_bps'])} "
              f"net_MID_lower={_f(bh['net_MID_lower']['gross_prefee_vw_bps'])}")

    # ---- decile (headline K, h=60, net_MID_lower base) ----
    print("-" * 84)
    Khl = f"K{K_HEADLINE}"
    print(f"2) NET BY TOXICITY DECILE ({Khl}, h=60, net_MID_lower, base tier), vw bps:")
    dec = results["net_by_toxicity_decile"][Khl]["h60"]
    for d in range(1, 11):
        cell = dec["deciles"].get(f"decile_{d:02d}", {}).get("net_MID_lower", {}).get("base")
        if cell:
            print(f"   decile {d:>2}: n={cell['n_fills']:>8,}  net_vw={_f(cell['net_vw_bps'])}")
    print(f"   most-negative decile = {dec.get('most_negative_decile_net_MID_lower_base')} "
          f"(toxic decile is most negative: {dec.get('toxic_decile_is_most_negative')})")

    # ---- B1 policy (headline K, h=60) ----
    print("-" * 84)
    print(f"3) B1 IDEALIZED POLICY (UPPER BOUND, {Khl}, h=60): drop toxic decile takers")
    b1 = results["b1_idealized_policy_upper_bound"][Khl]["h60"]
    print(f"   toxic takers dropped={b1['n_toxic_takers_dropped']:,}  "
          f"late notional frac dropped={_f(b1['toxic_notional_frac'],4)}")
    print(f"   {'tier':<10} {'base_net':>10} {'policy_net':>11} {'delta_net':>11} {'flips->+':>9}  (net_MID_lower)")
    for tier in FEE_TIERS:
        b = b1["baseline_net_vw_bps"]["net_MID_lower"][tier]
        p = b1["policy_net_vw_bps"]["net_MID_lower"][tier]
        dn = b1["delta_net_vw_bps"]["net_MID_lower"][tier]
        fl = b1["flips_negative_to_positive"]["net_MID_lower"][tier]
        print(f"   {tier:<10} {_f(b):>10} {_f(p):>11} {_f(dn):>11} {str(fl):>9}")

    # ---- the ladder of floors ----
    print("-" * 84)
    print(f"3b) LADDER OF WALLET-FILL FLOORS (B1 gain, net_MID_lower, "
          f"h={H.HEADLINE_HORIZON_S}s; the gain is the same at every fee tier):")
    print(f"   {'K':>5} {'eligible':>10} {'toxic':>7} {'gain_bps':>10} "
          f"{'ci95_wallet_clustered':>26} {'0 in':>5}")
    for K in K_RUNGS:
        cell = results["b1_idealized_policy_upper_bound"][f"K{K}"][f"h{H.HEADLINE_HORIZON_S}"]
        unc = cell["delta_uncertainty"]["by_measure"].get("net_MID_lower", {})
        ci = unc.get("ci95_wallet_clustered", [float("nan"), float("nan")])
        mark = " <- headline" if K == K_HEADLINE else ""
        print(f"   {K:>5} {cell['n_eligible_takers']:>10,} "
              f"{cell['n_toxic_takers_dropped']:>7,} "
              f"{_f(cell['delta_net_vw_bps']['net_MID_lower']['base']):>10} "
              f"  [{_f(ci[0])}, {_f(ci[1])}]"
              f" {str(not unc.get('ci_excludes_zero', False)):>5}{mark}")

    # ---- placebo ----
    print("-" * 84)
    print(f"4) PLACEBO (random same-notional drop, {Khl}, h=60, net_MID_lower):")
    pl = results["placebo_random_drop"][Khl]
    for tier in ("base", "t4_0fee"):
        bt = pl["by_tier"][tier]
        print(f"   {tier:<10} obs_tox_delta={_f(bt['observed_toxicity_delta_net_vw_bps'])} "
              f"rand_mean={_f(bt['random_drop_mean_delta_net_vw_bps'])} "
              f"perm_p={_f(bt['permutation_p'],4)} beats_random={bt['toxicity_beats_random']}")

    # ---- cross-checks ----
    print("-" * 84)
    print("5) CROSS-CHECKS:")
    ck = results["cross_checks"]
    print(f"   s_bbo>=0 frac={_f(ck['s_bbo_nonneg_frac'],5)} all_nonneg={ck['s_bbo_all_nonneg']}")
    for h in HORIZONS:
        sb = ck["s_approx_vs_s_bbo"][f"h{h}"]
        print(f"   h{h}: s_approx={_f(sb['mean_s_approx_bps'])} s_bbo={_f(sb['mean_s_bbo_bps'])} "
              f"s_approx>=s_bbo={sb['s_approx_ge_s_bbo_mean']}")
    pa = ck["two_measure_agreement_h60"]["pooled"]["base"]
    print(f"   two-measure (pooled,base,h60): net_PRINT={_f(pa['net_PRINT_vw_bps'])} "
          f"net_MID_lower={_f(pa['net_MID_lower_vw_bps'])} sign_agree={pa['sign_agree']} "
          f"gap={_f(pa['gap_bps'])}")
    m8 = ck["m8_reconciliation"]
    print(f"   m8 recon: ungrouped=${m8['ungrouped_signed_cost_quote']:,.2f} "
          f"taker-grouped=${(m8['taker_grouped_signed_cost_quote'] or float('nan')):,.2f} "
          f"eq={m8['ungrouped_eq_taker_grouped']} vw_a_mid_60={_f(m8['vw_a_mid_60_bps'])}")
    od = ck["oos_disjoint"]
    print(f"   OOS disjoint: days={od['days_disjoint']} fills={od['fills_disjoint']} "
          f"early={od['early_days']} late={od['late_days']}")
    nd = ck["nan_drop_frac"]["h60"]
    print(f"   nan-drop h60: a_mid={_f(nd['a_mid_nan_frac'],5)} "
          f"a_print={_f(nd['a_print_nan_frac'],5)} net_MID_lower={_f(nd['net_MID_lower_nan_frac'],5)}")
    print("=" * 84)


if __name__ == "__main__":
    main()
