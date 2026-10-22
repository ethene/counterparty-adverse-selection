"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-08-03
References:
  - Glosten, Milgrom (1985). Bid, Ask and Transaction Prices in a Specialist Market
    (the break-even half-spread equals expected adverse selection per fill).
  - Avellaneda, Stoikov (2008). High-frequency trading in a limit order book
    (the symmetric reservation quoter this control is measured against).
  - Bergault, Guéant and co-authors, arXiv:2508.20225 (2025, rev. 2026-06): tiered
    counterparty premia, of which the term measured here is the reduced form.
"""

# ---------------------------------------------------------------------------
# OBJECT - what does counterparty IDENTITY buy, once width is held constant.
#
# The study's quoter charges each counterparty a premium proportional to that
# wallet's own early adverse-selection estimate. Against a symmetric quoter it
# gains, and the gain is the number the report leads the quoting section with.
# The obvious objection is that the gain is not identity at all but simply a
# WIDER QUOTE: charge everybody the same average premium and you might collect
# the same money without knowing who anybody is.
#
# This file answers that by building the flat counterfactual at the SAME
# notional-weighted average width and reporting what is left over. The residual
# is the part of the gain that resolving identity actually buys. It is the
# strongest negative control in the study, and it is deliberately built to be
# unkind to the study's own claim.
#
# WHY IT LIVES HERE NOW. Until 2026-08-03 this control ran only as a scratch
# script kept with an audit trail outside the repository, so the number it
# produced could not be recomputed by anyone cloning this tree, and it went stale
# without any gate noticing: the entry-price repair of 2026-08-02 moved the
# published delta from 0.4825 to 0.5231, while the flat constant fitted to the
# OLD width, and the residual and its share were still quoted against a
# denominator this study no longer publishes. A control that cannot be re-run is
# a claim, not a control.
#
# WHAT THIS FILE DOES NOT DO. It does not re-derive the bake-off. It recomputes
# the published delta independently and REFUSES to report a residual unless that
# recomputation lands on the published value. An independent recomputation that
# agrees is evidence the two procedures are one; a residual reported without that
# agreement would be a number against an unknown baseline.
#
# THE RANK FLOOR, settled by measurement rather than by reading. The published
# delta is filed under the headline floor's block, yet mm_bakeoff states that the
# as_toxicity term is booked over a population that does not read the floor. Both
# constructions are therefore computed here and the artifact records WHICH ONE
# reproduces the published value, so the question is answered by the data and
# stays answered when either side moves.
#
# HOW UNCERTAIN THE RESIDUAL IS, added 2026-08-14. Until this run the five residuals
# below were point estimates with nothing beside them: no interval, no resampling, no
# statement of how far they sit from zero. That was checked against every version of
# this file rather than assumed -- the quantity had never carried a band at all. A
# residual reported alone invites the reader to treat 0.0393 basis points as a measured
# effect, and the measurement here is that it is barely separable from nothing.
#
# THE RESAMPLING IS BY WALLET AND NOT BY FILL, for the reason mm_bakeoff.py already
# states at pairwise_wallet_resolved_stats: the premium is a property of the
# COUNTERPARTY, one counterparty contributes many correlated fills, and an interval
# drawn over fills would treat those fills as independent evidence. The estimator is the
# one that block uses -- per-wallet partial sums of numerator and denominator, resampled
# m out of m with replacement, ratio of the summed parts on every draw.
#
# WHY THE FLAT WIDTH IS REFITTED INSIDE EVERY DRAW. The flat counterfactual is not a
# constant this study picked; it is DEFINED as the notional-weighted average premium of
# the very rows the residual is taken over, so it is a function of the sample rather
# than a parameter standing beside it. A resample holding different wallets has a
# different average premium, and the arm it has to be measured against is the flat arm
# at THAT width: equality of width is the one thing this comparison holds fixed, and a
# draw that breaks it is a draw of some other comparison.
#
# THAT CHOICE NARROWS THE INTERVAL RATHER THAN WIDENING IT, and the direction was
# measured on 2026-08-14 because it is the opposite of what was expected. Freezing the
# width at its full-sample value was expected to understate the spread, on the ground
# that it treats a fitted quantity as known. It overstates it on all five residuals, by
# factors of 3.0 to 4.4: on the headline one the standard deviation across draws is
# 0.0219 basis points with the width refitted and 0.0755 with it frozen. The mechanism
# is visible in the same run and is not a story about it -- the drawn width runs from
# 1.08 to 2.66 basis points around a full-sample 1.74, so a frozen counterfactual meets
# most draws at a width those draws do not have, and the difference then carries the
# width gap along with identity. Both are published, the frozen one under a name that
# says what it holds fixed.
#
# THE PREMIUM IS NOT RESAMPLED. It is estimated on the disjoint EARLY half and held
# still, exactly as the bake-off holds its quoter still: what is being measured is the
# spread of the late-half outcome under a fixed quoting rule, not the spread of the
# rule.
#
# COST. numpy only. Reads ONE shared intermediate (quickwin_markouts_mid.npz),
# no raw parse and no order-book rebuild. No kindred pure reader in this tree had
# ever recorded its own run time, which is why every estimate of this node's cost
# was a floor with nothing under it; this one records its elapsed seconds. The
# resampling took the node from half a second to about a minute, measured, and the
# console prints a line as each block finishes so the run is followable.
# ---------------------------------------------------------------------------

import json
import os
import sys

import numpy as np

# The shared modules sit in the repository root, one directory up from this
# group, and this file also imports from the quoters group. Both are built from this
# file's own location and never from the working directory the run happens to
# start in.
_CODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_CODE_DIR, os.path.join(_CODE_DIR, "quoters")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import artifact
import mm_bakeoff as MB
import panel_io as P
import settings as H

HERE = os.path.dirname(os.path.abspath(__file__))

# The two coins carry integer codes in the shared intermediate, and the map is READ
# from settings rather than spelled here. It was spelled here until 2026-08-03 with a
# comment saying the settings map answers a different question; that was wrong. The map
# is keyed by artifact store, this file reads the quickwin store, and the neighbouring
# controls take it exactly this way: i3_book_comparator.py:140 and step1_inventory.py:71.
# A literal beside a declaration is a number that can drift without anyone editing it twice.
COINS = tuple(sorted((code, symbol) for symbol, code in H.coin_codes("quickwin").items()))

OUT_NAME = "flat_surcharge_control_results.json"
MID_NPZ = "quickwin_markouts_mid.npz"

# The booked offset is RECOVER_FRAC * min(premium, max(a_mid, 0)) per fill, and both
# the fraction and the saturation come from the quoter being controlled. They are
# imported rather than restated: a constant retyped here would keep its old value
# through a repair of the original and the control would then measure a quoter
# nobody runs.
RECOVER_FRAC = MB.RECOVER_FRAC
LAMBDA_TOX = 1.0                 # full pass-through, the published headline setting
HEADLINE_FLOOR = MB.K_HEADLINE   # fills a wallet needs in the early half to be scored

# Where the published delta lives. Named once, read once, and printed beside every
# comparison so a reader never has to guess which cell is meant.
PUBLISHED_FILE = "mm_bakeoff_results.json"
PUBLISHED_KEY = ("adverse_selection_term_value", "K50", "pooled", "base",
                 "as_toxicity_minus_as_symmetric_delta_net_vw_bps")

# Agreement bar for the reproduction. Relative, because the quantity is a small
# number of basis points and an absolute bar would mean different things at
# different sizes. 1e-6 is far below any published precision and far above float
# summation noise over 2.5M rows.
REPRODUCTION_RTOL = 1e-6

# ---- the resampling ------------------------------------------------------------
# The declared budget, read from settings and never from the environment. boot_draws()
# refuses a purpose it has no entry for and its own message names this route: a consumer
# that takes the declaration itself reads N_BOOT. Adding an entry to that map would say
# this file needs a budget of its own, and it does not -- it draws the declared one.
N_BOOT = H.N_BOOT

# Tail mass per side. Passed as the TAIL and not derived from a coverage, for the reason
# settings.draws_per_tail spells out: 1 - 0.95 is 0.05000000000000004 in binary, and the
# budget's own reasoning is written in the tail.
CI_TAIL = 0.025

# Extra streams the headline interval's ENDPOINT is re-drawn on. Not a second estimate of
# the residual -- the point estimate is computed from the data and no resample touches it
# -- but a measurement of how far the 2.5 per cent endpoint moves between streams, which
# is the only way to know whether "excludes zero" is a property of the data or of the
# seed. Six is enough to see an endpoint straddle zero; it is not a distribution.
SEED_SWEEP_STREAMS = 6

# What counts as zero for the calibration case that must contain it. That case is zero by
# construction -- the arm is compared against itself -- so what is left in the draws is
# float summation noise from two different accumulation orders: measured on 2026-08-14,
# the largest absolute difference over 2000 draws was 2.3e-15 basis points. 1e-9 sits six
# orders above that noise and six orders below the smallest residual this file publishes
# (0.0056 bps), so it cannot be met by a real effect and cannot be missed by rounding.
CALIBRATION_ZERO_TOL_BPS = 1e-9

# Agreement bar between the resampler's own point estimate and the residual published in
# the block above. The two are computed by different routes -- the published one sums
# per-fill offsets, the resampler sums per-wallet partial sums and a sorted-by-saturation
# prefix -- so they differ by summation order alone. Measured on 2026-08-14: the largest
# relative gap over the five residuals was 1.5e-14.
RESAMPLER_AGREEMENT_RTOL = 1e-9


def _dig(doc, path):
    cur = doc
    for part in path:
        cur = cur[part]
    return cur


def _early_tox(taker_idx, n_wallets, early_mask, a_mid, floor):
    """Per-wallet early adverse-selection estimate, clipped at zero.

    floor = 0 keeps every wallet with at least one finite early observation, which is
    the population the quoter's term is booked over if it does not read the rank
    floor. floor > 0 keeps only wallets with at least that many, which is the
    population if it does. Both are returned to the caller so the artifact can say
    which one the published number stands on instead of assuming it.
    """
    valid = early_mask & np.isfinite(a_mid)
    count = np.bincount(taker_idx[valid], minlength=n_wallets)
    total = np.bincount(taker_idx[valid], weights=a_mid[valid], minlength=n_wallets)
    keep = count > max(floor - 1, 0) if floor else count > 0
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = np.where(keep, total / np.where(count > 0, count, np.nan), np.nan)
    per_wallet = np.where(np.isfinite(mean), np.maximum(mean, 0.0), 0.0)
    return per_wallet[taker_idx], int(keep.sum())


# Every stream this run opens, recorded AS IT IS OPENED by the one function that opens
# them. mm_bakeoff.py keeps the same list for the same reason: whether two blocks
# resampled the same rows while reporting independent bands is a question a run can
# answer about itself, and a list rebuilt afterwards from the naming rules would agree
# with those rules rather than with what ran.
_STREAM_CELLS = []


def _stream(cell):
    """settings.rng for one named cell, recording the cell so the run can audit itself.

    No literal seed appears in this file. The generator is derived from
    settings.MASTER_SEED and the cell identity through settings.cell_key, so two blocks
    collide only if they were given the same name, and settings.colliding_cells says
    whether any did.
    """
    _STREAM_CELLS.append(tuple(cell))
    return H.rng(*cell)


class ResampledArm:
    """One population, one premium, one segmentation of the flat counterfactual.

    WHAT IT HOLDS. Everything a bootstrap draw needs reduced to per-WALLET partial sums,
    so that a draw is a gather and two dot products rather than a pass over 1.2M fills:

        den_by_w        notional of the wallet's booked fills
        booked_by_w     notional-weighted min(premium, saturation), the resolved arm
        premium_by_w    notional-weighted premium, per segment -- the width is fitted
                        from these two inside every draw
        the saturation-sorted fills, per segment, which is the only part of the flat
        arm that cannot be pre-summed

    WHY THE FLAT ARM NEEDS THE SORTED FILLS. Its per-fill term is min(W, saturation) and
    W changes on every draw, so it is not a per-wallet constant. But it splits exactly:

        sum_i c_i * min(W, s_i) = sum_{s_i <= W} c_i * s_i  +  W * sum_{s_i > W} c_i

    which is a prefix and a suffix of the fills sorted by saturation, at the position
    searchsorted puts W. Both sums are taken with the draw's own multiplicity, so the
    identity is exact rather than an approximation to it: it is the same arithmetic the
    published block does per fill, reordered.

    FILLS WITH ZERO SATURATION ARE DROPPED FROM THAT SORT and from nothing else. The
    premium is non-negative by construction (as_toxicity_term_bps clips at zero) so every
    fitted width is non-negative, and min(W, 0) is zero for every one of them: those fills
    contribute nothing to either arm. They stay in den_by_w and premium_by_w, because they
    do carry notional and they do carry a premium, and dropping them there would change
    both the denominator and the width.
    """

    def __init__(self, rows, premium, segment_code, segment_names,
                 taker_idx, notional_all, saturation_all):
        u = notional_all[rows]
        s = saturation_all[rows]
        p = premium[rows]
        if float(p.min()) < 0.0:
            raise ValueError(
                "the premium carries a negative value, so a fitted width could be "
                "negative and the zero-saturation fills dropped below would stop being "
                "irrelevant to both arms; as_toxicity_term_bps clips at zero and "
                "something upstream of it has changed")
        wallets, w_idx = np.unique(taker_idx[rows], return_inverse=True)
        self.n_wallets = int(wallets.size)
        self.n_rows = int(rows.size)
        self.ones = np.ones(self.n_wallets)
        self.den_by_w = np.bincount(w_idx, weights=u, minlength=self.n_wallets)
        self.booked_by_w = np.bincount(w_idx, weights=u * np.minimum(p, s),
                                       minlength=self.n_wallets)
        self.segment_names = list(segment_names)
        self.segments = []
        for code in sorted(set(int(c) for c in np.unique(segment_code))):
            in_seg = segment_code == code
            pos = in_seg & (s > 0.0)
            order = np.argsort(s[pos], kind="stable")
            self.segments.append({
                "premium_by_w": np.bincount(w_idx[in_seg], weights=(u * p)[in_seg],
                                            minlength=self.n_wallets),
                "den_by_w": np.bincount(w_idx[in_seg], weights=u[in_seg],
                                        minlength=self.n_wallets),
                "wallet": w_idx[pos][order],
                "notional": u[pos][order],
                "saturation": s[pos][order],
                "notional_saturation": (u * s)[pos][order],
            })
        if len(self.segments) != len(self.segment_names):
            raise ValueError(
                f"{len(self.segments)} segments were built and "
                f"{len(self.segment_names)} names given; a segment reported under the "
                "wrong name is worse than one reported under none")

    def widths(self, m):
        """The notional-weighted average premium of the resample, per segment."""
        return [float((m @ sg["premium_by_w"]) / (m @ sg["den_by_w"]))
                for sg in self.segments]

    def _flat_notional_sum(self, m, widths):
        total = 0.0
        for sg, w in zip(self.segments, widths):
            drawn = m[sg["wallet"]]
            k = int(np.searchsorted(sg["saturation"], w, side="right"))
            total += (float(drawn[:k] @ sg["notional_saturation"][:k])
                      + w * float(drawn[k:] @ sg["notional"][k:]))
        return total

    def measures(self, m, widths=None):
        """(resolved arm, flat arm, widths) in bps on one resample.

        `widths` given holds the flat arm at a width the resample did not produce, which
        is the comparison this file publishes under width_held_fixed and does not lead
        with.
        """
        den = float(m @ self.den_by_w)
        w = self.widths(m) if widths is None else list(widths)
        return (RECOVER_FRAC * float(m @ self.booked_by_w) / den,
                RECOVER_FRAC * self._flat_notional_sum(m, w) / den,
                w)


def wallet_bootstrap(n_wallets, cell, per_draw, n_boot=N_BOOT):
    """Draw n_boot wallet resamples from ONE named stream and evaluate per_draw on each.

    per_draw(m) takes the multiplicity vector of the draw and returns a mapping of name
    to value. Several quantities off ONE draw rather than one quantity per draw, which is
    what lets a calibration case and the quantity it calibrates see the same resamples
    instead of merely the same budget.
    """
    gen = _stream(cell)
    collected = None
    for b in range(n_boot):
        drawn = gen.integers(0, n_wallets, size=n_wallets)
        m = np.bincount(drawn, minlength=n_wallets).astype(np.float64)
        values = per_draw(m)
        if collected is None:
            collected = {k: np.empty(n_boot, dtype=np.float64) for k in values}
        for k, v in values.items():
            collected[k][b] = v
    return collected


def percentile_interval(draws, tail=CI_TAIL):
    """The two endpoints and how many draws were dropped for not being finite.

    The count is published rather than swallowed: an interval taken over 1900 of 2000
    draws is a different interval from one taken over all of them, and silence about
    that is the same defect as a count printed without its predicate.
    """
    finite = draws[np.isfinite(draws)]
    dropped = int(draws.size - finite.size)
    if finite.size < 2:
        return [float("nan"), float("nan")], dropped
    return ([float(np.percentile(finite, 100.0 * tail)),
             float(np.percentile(finite, 100.0 * (1.0 - tail)))], dropped)


def _excludes_zero(ci):
    return bool(ci[0] == ci[0] and (ci[0] > 0.0 or ci[1] < 0.0))


def _covers_zero(ci, tol=0.0):
    """Zero inside the interval, or both endpoints within tol of it."""
    if ci[0] != ci[0]:
        return False
    return bool((ci[0] <= 0.0 <= ci[1])
                or (abs(ci[0]) <= tol and abs(ci[1]) <= tol))


def calibrate(arm_resolved, arm_flat_against_itself, cell, n_boot=N_BOOT):
    """The instrument on two opposite cases of this tree, both drawn from ONE stream.

    WHY. An interval that has never been shown to exclude zero and never been shown to
    contain it says nothing when it does either. One reference case cannot tell a band
    that is too wide from one that is too narrow, so both are needed and they have to be
    cases whose answer is known BEFORE the draw rather than read off it.

    MUST CONTAIN ZERO -- the flat arm against itself. The per-wallet premium is replaced
    by the single constant this file fits, everything else is left alone, and the width
    is refitted inside every draw exactly as in the live block. The refitted width of a
    constant premium is that constant on every resample, so the two arms are one arm and
    the difference is zero on every draw. It is a strong case and not a trivial one,
    because it fails loudly in the way that matters: if the resolved arm were drawn on
    one resample and the flat arm fitted on another, or if the width were refitted in one
    arm and frozen in the other, this difference would stop being zero. The level itself
    is published from the SAME draws to show that the resampling did move -- a difference
    of zero over draws that never moved would certify nothing.

    MUST EXCLUDE ZERO -- the booked gain of the resolved quoter over the same population,
    the same wallet universe and the same draws. Its per-fill term is
    RECOVER_FRAC * min(premium, max(a_mid, 0)), which is non-negative on every fill by
    construction and strictly positive on a majority of them, so its population value
    cannot be zero and a band containing zero would be a band too wide to say anything.

    A FAILURE HERE WITHHOLDS THE INTERVALS. The same rule this file already applies to
    the residual itself: a control that has not reproduced its baseline has no baseline,
    and an interval whose instrument has not been shown to work is not a bound on
    anything.
    """
    def per_draw(m):
        true_bps, flat_bps, _ = arm_flat_against_itself.measures(m)
        gain_bps, _, _ = arm_resolved.measures(m)
        return {"self_difference": true_bps - flat_bps,
                "self_level": flat_bps,
                "resolved_gain": gain_bps}

    drawn = wallet_bootstrap(arm_resolved.n_wallets, cell, per_draw, n_boot=n_boot)
    silent_ci, silent_dropped = percentile_interval(drawn["self_difference"])
    level_ci, _ = percentile_interval(drawn["self_level"])
    firing_ci, firing_dropped = percentile_interval(drawn["resolved_gain"])
    silent_pass = _covers_zero(silent_ci, CALIBRATION_ZERO_TOL_BPS)
    firing_pass = _excludes_zero(firing_ci)
    return {
        "why": ("an interval never shown to exclude zero and never shown to contain it "
                "says nothing when it does either, and one case cannot tell a band that "
                "is too wide from one that is too narrow"),
        "n_boot": int(n_boot),
        "both_cases_share_one_stream": True,
        "must_contain_zero": {
            "case": ("the flat arm against itself: the per-wallet premium replaced by "
                     "the constant this file fits, the width still refitted inside every "
                     "draw, everything else untouched"),
            "expected": ("zero on every draw, because the refitted width of a constant "
                         "premium is that constant and the two arms are one arm"),
            "catches": ("a resolved arm and a flat arm drawn on different resamples, and "
                        "a width refitted in one arm but frozen in the other"),
            "ci95_bps": silent_ci,
            "max_abs_over_draws_bps": float(np.max(np.abs(drawn["self_difference"]))),
            "tolerance_bps": CALIBRATION_ZERO_TOL_BPS,
            "n_draws_dropped_non_finite": silent_dropped,
            "level_ci95_bps_same_draws": level_ci,
            "level_means": ("the flat arm's own level across the SAME draws; it moves, "
                            "which is what makes a difference of zero evidence rather "
                            "than a resampling that never resampled"),
            "passed": bool(silent_pass),
        },
        "must_exclude_zero": {
            "case": ("the booked gain of the resolved quoter over the same population, "
                     "the same wallet universe and the same draws"),
            "expected": ("an interval entirely above zero: the per-fill term "
                         "RECOVER_FRAC * min(premium, max(a_mid, 0)) is non-negative by "
                         "construction and strictly positive on a majority of fills"),
            "catches": "a band too wide to say anything, and a draw that never varies",
            "ci95_bps": firing_ci,
            "n_draws_dropped_non_finite": firing_dropped,
            "passed": bool(firing_pass),
        },
        "both_passed": bool(silent_pass and firing_pass),
    }


def residual_record(address, published_residual, arm, cell, n_boot=N_BOOT):
    """One published residual with an interval, its procedure and its own agreement check.

    The point estimate is recomputed here by the resampler's own route -- per-wallet
    partial sums and a saturation-sorted prefix -- and compared against the residual the
    block above published by summing per-fill offsets. The two differ by summation order
    alone, so an agreement failure means the interval belongs to some other quantity than
    the number it is printed beside, and the record says so instead of carrying on.
    """
    point_true, point_flat, point_widths = arm.measures(arm.ones)
    point = point_true - point_flat
    gap = abs(point - published_residual) / abs(published_residual)

    def per_draw(m):
        true_bps, flat_bps, widths = arm.measures(m)
        _, flat_frozen, _ = arm.measures(m, widths=point_widths)
        values = {"residual": true_bps - flat_bps,
                  "residual_width_held_fixed": true_bps - flat_frozen}
        for name, w in zip(arm.segment_names, widths):
            values[f"width_{name}"] = w
        return values

    drawn = wallet_bootstrap(arm.n_wallets, cell, per_draw, n_boot=n_boot)
    ci, dropped = percentile_interval(drawn["residual"])
    ci_frozen, _ = percentile_interval(drawn["residual_width_held_fixed"])
    residuals = drawn["residual"]
    widths_moved = {}
    for name, full in zip(arm.segment_names, point_widths):
        col = drawn[f"width_{name}"]
        widths_moved[name] = {
            "full_sample_bps": float(full),
            "mean_over_draws_bps": float(np.mean(col)),
            "sd_over_draws_bps": float(np.std(col)),
            "min_over_draws_bps": float(np.min(col)),
            "max_over_draws_bps": float(np.max(col)),
        }
    return {
        "address": address,
        "published_residual_bps": float(published_residual),
        "resampler_point_bps": float(point),
        "relative_gap_against_published": float(gap),
        "agrees_with_published": bool(gap <= RESAMPLER_AGREEMENT_RTOL),
        "n_wallets_resampled": int(arm.n_wallets),
        "n_rows": int(arm.n_rows),
        "ci95_wallet_clustered_width_refit": ci,
        "ci_excludes_zero": _excludes_zero(ci),
        "ci_excludes_zero_read_with": (
            "identity_residual_uncertainty.endpoint_reliability, which measures whether "
            "this flag changes hands between streams. It is a percentile landing on one "
            "side of zero or the other, and lifted on its own it reads as a settled "
            "verdict; frac_draws_at_or_below_zero beside it is the quantity that moves "
            "smoothly and is the one to quote"),
        "frac_draws_at_or_below_zero": float(np.mean(residuals <= 0.0)),
        "sd_over_draws_bps": float(np.std(residuals)),
        "n_draws_dropped_non_finite": dropped,
        "ci95_wallet_clustered_width_held_fixed": ci_frozen,
        "sd_over_draws_width_held_fixed_bps": float(
            np.std(drawn["residual_width_held_fixed"])),
        "width_refit_inside_draw": widths_moved,
        "stream_cell": list(cell),
    }


def main():
    started = artifact.start_clock()
    data_root = P.data_root()
    npz_path = os.path.join(data_root, MID_NPZ)

    z = np.load(npz_path)
    taker = z["taker_id"].astype(np.int64)
    coin = z["coin"].astype(np.int64)
    day = z["day"].astype(np.int64)
    notional = z["notional"].astype(np.float64)
    a_mid = z[f"mo{H.HEADLINE_HORIZON_S}_mid"].astype(np.float64)

    early_days, late_days = H.split_early_late(sorted(set(int(d) for d in np.unique(day))))
    is_early = np.isin(day, list(early_days))
    is_late = np.isin(day, list(late_days))

    uniq, taker_idx = np.unique(taker, return_inverse=True)
    booked_rows = is_late & np.isfinite(a_mid) & np.isfinite(notional) & (notional > 0)
    weights = notional[booked_rows]
    weight_sum = float(weights.sum())
    saturation = np.maximum(a_mid, 0.0)

    def booked_gain(premium, rows=booked_rows, w=weights, sw=weight_sum):
        """Notional-weighted mean booked offset in bps over the rows it is booked on."""
        offset = RECOVER_FRAC * np.minimum(premium[rows], saturation[rows])
        return float(np.sum(offset * w) / sw)

    # ---- the two candidate constructions of the premium ------------------------
    tox_unfloored, n_unfloored = _early_tox(taker_idx, uniq.size, is_early, a_mid, 0)
    tox_floored, n_floored = _early_tox(taker_idx, uniq.size, is_early, a_mid, HEADLINE_FLOOR)
    premium_unfloored = MB.as_toxicity_term_bps(tox_unfloored, LAMBDA_TOX)
    premium_floored = MB.as_toxicity_term_bps(tox_floored, LAMBDA_TOX)

    gain_unfloored = booked_gain(premium_unfloored)
    gain_floored = booked_gain(premium_floored)

    # ---- which one reproduces what the study publishes -------------------------
    # Beside its own producer in the quoters group, not beside this control. The file
    # name stays the last component of the join, because that is what build.py folds
    # this script's input edge out of.
    with open(os.path.join(_CODE_DIR, "quoters", PUBLISHED_FILE),
              encoding="utf-8") as fh:
        published_doc = json.load(fh)
    published = float(_dig(published_doc, PUBLISHED_KEY))

    candidates = {"no_rank_floor": gain_unfloored, f"rank_floor_{HEADLINE_FLOOR}": gain_floored}
    gaps = {k: abs(v - published) / abs(published) for k, v in candidates.items()}
    matching = [k for k, g in gaps.items() if g <= REPRODUCTION_RTOL]
    reproduced = len(matching) == 1
    chosen = matching[0] if reproduced else None
    true_gain = candidates[chosen] if reproduced else None

    print(f"published delta   {published:.10f}  ({PUBLISHED_FILE}: "
          f"{'.'.join(PUBLISHED_KEY)})", flush=True)
    for name, value in candidates.items():
        print(f"  recomputed {name:<18} {value:.10f}   relative gap {gaps[name]:.3e}", flush=True)
    if not reproduced:
        print("  NEITHER construction reproduces the published value within "
              f"{REPRODUCTION_RTOL:.0e}; no residual is reported below.", flush=True)

    payload = {
        "reproduction": {
            "published": published,
            "published_address": f"{PUBLISHED_FILE}#{'.'.join(PUBLISHED_KEY)}",
            "recomputed": candidates,
            "relative_gap": gaps,
            "rtol": REPRODUCTION_RTOL,
            "reproduced": reproduced,
            "construction_that_reproduces": chosen,
            "n_wallets_scored": {"no_rank_floor": n_unfloored,
                                 f"rank_floor_{HEADLINE_FLOOR}": n_floored},
            "means": ("A residual below is a comparison against this recomputed value. "
                      "If reproduced is false the control has no baseline and its "
                      "numbers are not to be quoted."),
        }
    }

    if reproduced:
        # ---- variant 1: ONE global constant at the same notional-weighted width ----
        premium = premium_unfloored if chosen == "no_rank_floor" else premium_floored
        global_width = float(np.sum(premium[booked_rows] * weights) / weight_sum)
        gain_global = booked_gain(np.full(premium.size, global_width))

        # ---- variant 2: a constant per coin, then pooled ---------------------------
        flat_per_coin = np.zeros(premium.size)
        per_coin_width = {}
        for code, name in COINS:
            sel = booked_rows & (coin == code)
            if not sel.any():
                continue
            width = float(np.sum(premium[sel] * notional[sel]) / np.sum(notional[sel]))
            flat_per_coin[coin == code] = width
            per_coin_width[name] = width
        gain_per_coin = booked_gain(flat_per_coin)

        # ---- per-coin slices, where the two variants coincide by construction ------
        by_coin = {}
        for code, name in COINS:
            sel = booked_rows & (coin == code)
            if not sel.any():
                continue
            w = notional[sel]
            sw = float(w.sum())
            width = float(np.sum(premium[sel] * w) / sw)
            true_c = float(np.sum(RECOVER_FRAC * np.minimum(premium[sel], saturation[sel]) * w) / sw)
            flat_c = float(np.sum(
                RECOVER_FRAC * np.minimum(np.full(w.size, width), saturation[sel]) * w) / sw)
            by_coin[name] = {"width_bps": width, "true_gain_bps": true_c,
                             "flat_same_width_gain_bps": flat_c,
                             "identity_residual_bps": true_c - flat_c,
                             "identity_share_pct": 100.0 * (true_c - flat_c) / true_c}

        payload["pooled"] = {
            "true_gain_bps": true_gain,
            "one_global_constant": {
                "width_bps": global_width,
                "flat_same_width_gain_bps": gain_global,
                "identity_residual_bps": true_gain - gain_global,
                "width_share_pct": 100.0 * gain_global / true_gain,
                "identity_share_pct": 100.0 * (true_gain - gain_global) / true_gain,
            },
            "per_coin_constants": {
                "width_bps": per_coin_width,
                "flat_same_width_gain_bps": gain_per_coin,
                "identity_residual_bps": true_gain - gain_per_coin,
                "width_share_pct": 100.0 * gain_per_coin / true_gain,
                "identity_share_pct": 100.0 * (true_gain - gain_per_coin) / true_gain,
            },
        }
        payload["by_coin"] = by_coin

        # ---- the same split under the rank floor the study declares ----------------
        # WHY THIS BLOCK EXISTS, added 2026-08-05. The premium above is booked on every
        # wallet carrying a finite early estimate, floor or no floor: mm_bakeoff's
        # identity_term_population says so in as many words and records it as an open
        # debt. The rest of this study scores at a floor of fifty early fills, on the
        # stated ground that a thinner wallet cannot support a toxicity verdict at all.
        # A reader who meets the floor where the scoring is described and then meets
        # this split is therefore reading two populations under one declaration, and
        # the difference is not small: the identity share is 7.52 per cent over the
        # 32 578 wallets the quoter actually charges and 1.79 per cent over the 2 069
        # the study is willing to score. Publishing both is the only honest move, since
        # they answer different questions rather than disagreeing about one.
        floored_width = float(np.sum(premium_floored[booked_rows] * weights) / weight_sum)
        floored_flat = booked_gain(np.full(premium_floored.size, floored_width))
        payload["pooled_at_rank_floor"] = {
            "rank_floor_fills": HEADLINE_FLOOR,
            "n_wallets_scored": n_floored,
            "true_gain_bps": gain_floored,
            "one_global_constant": {
                "width_bps": floored_width,
                "flat_same_width_gain_bps": floored_flat,
                "identity_residual_bps": gain_floored - floored_flat,
                "width_share_pct": 100.0 * floored_flat / gain_floored,
                "identity_share_pct": 100.0 * (gain_floored - floored_flat) / gain_floored,
            },
            "means": ("The counterparty premium restricted to wallets with at least "
                      f"{HEADLINE_FLOOR} early fills, split the same way as the block "
                      "above. This is NOT the published quoter, which reads no floor; "
                      "it is what the published quoter would buy if it were confined to "
                      "the counterparties this study claims to be able to rank."),
        }
        print(f"  at rank floor {HEADLINE_FLOOR:<6} flat {floored_flat:.7f}"
              f"   residual {gain_floored - floored_flat:+.7f}"
              f"   width {100.0 * floored_flat / gain_floored:.2f}%"
              f"   identity {100.0 * (gain_floored - floored_flat) / gain_floored:.2f}%"
              f"   on {n_floored} wallets", flush=True)

        payload["reporting_rule"] = (
            "Report the flat counterfactual as the LEADING number and the residual "
            "beside it, never the residual alone: the finding is that most of the gain "
            "is width and only the remainder is identity. Both the one-constant and the "
            "per-coin variants are published because they answer slightly different "
            "questions and a reader who sees one will ask for the other.")

        for label, block in (("one global constant", payload["pooled"]["one_global_constant"]),
                             ("per-coin constants", payload["pooled"]["per_coin_constants"])):
            print(f"  {label:<20} flat {block['flat_same_width_gain_bps']:.7f}"
                  f"   residual {block['identity_residual_bps']:+.7f}"
                  f"   width {block['width_share_pct']:.2f}%"
                  f"   identity {block['identity_share_pct']:.2f}%", flush=True)

        # ================= how uncertain those five residuals are =================
        # Nothing above this line moves. Every arm below is built from the same rows,
        # the same premium and the same saturation the block above used, and the
        # resampler recomputes each point estimate by its own route and refuses to
        # publish an interval whose point estimate does not land on the one already
        # printed. An interval attached to a different quantity than the number it sits
        # beside is worse than no interval, because it reads as a bound on that number.
        rows_all = np.where(booked_rows)[0]
        one_segment = np.zeros(rows_all.size, dtype=np.int64)
        coin_names = [name for code, name in COINS
                      if bool((booked_rows & (coin == code)).any())]

        arm_one_constant = ResampledArm(rows_all, premium, one_segment, ["pooled"],
                                        taker_idx, notional, saturation)
        arm_per_coin = ResampledArm(rows_all, premium, coin[rows_all], coin_names,
                                    taker_idx, notional, saturation)
        arm_at_floor = ResampledArm(rows_all, premium_floored, one_segment, ["pooled"],
                                    taker_idx, notional, saturation)
        # The calibration's silent case: the same population with the premium replaced by
        # the constant this file fits, so the resolved arm and the flat arm are one arm.
        arm_flat_against_itself = ResampledArm(
            rows_all, np.full(premium.size, global_width), one_segment, ["pooled"],
            taker_idx, notional, saturation)
        if arm_flat_against_itself.n_wallets != arm_one_constant.n_wallets:
            raise AssertionError(
                "the calibration arm and the arm it calibrates resample different "
                "wallet universes, so one draw does not feed both and the case "
                "calibrates nothing")

        calibration = calibrate(arm_one_constant, arm_flat_against_itself,
                                ("flat_surcharge_control", "interval_calibration"))
        silent = calibration["must_contain_zero"]
        firing = calibration["must_exclude_zero"]
        print(f"  calibration  must contain zero: ci95 "
              f"[{silent['ci95_bps'][0]:+.3e}, {silent['ci95_bps'][1]:+.3e}]"
              f"   largest |difference| over draws {silent['max_abs_over_draws_bps']:.3e}"
              f"   level moved [{silent['level_ci95_bps_same_draws'][0]:.5f}, "
              f"{silent['level_ci95_bps_same_draws'][1]:.5f}]"
              f"   {'PASS' if silent['passed'] else 'FAIL'}", flush=True)
        print(f"  calibration  must exclude zero: ci95 "
              f"[{firing['ci95_bps'][0]:+.7f}, {firing['ci95_bps'][1]:+.7f}]"
              f"   {'PASS' if firing['passed'] else 'FAIL'}", flush=True)

        uncertainty = {
            "object": ("a 95 per cent interval around each published identity residual, "
                       "resampled at the level the premium varies -- the counterparty -- "
                       "with the flat counterfactual refitted inside every draw"),
            "procedure": {
                "estimator": ("the ratio of summed per-wallet partial sums on every "
                              "draw: the resolved arm's booked offset over the notional "
                              "of the drawn wallets, minus the flat arm's booked offset "
                              "at the width those same drawn wallets imply"),
                "cluster_level": ("taker wallet (taker_id). The premium is a property of "
                                  "the counterparty and one counterparty carries many "
                                  "correlated fills, so a fill-resampled band would "
                                  "count those fills as independent evidence"),
                "resample": "m wallets out of m, with replacement",
                "n_boot": int(N_BOOT),
                "interval": "95 per cent percentile",
                "tail_mass_per_side": CI_TAIL,
                "draws_per_tail": H.draws_per_tail(N_BOOT, CI_TAIL),
                "seed": ("settings.rng -- settings.MASTER_SEED flattened with the cell "
                         "identity by settings.cell_key. No literal seed stands in this "
                         "file and no value is read from the environment"),
                "master_seed": int(H.MASTER_SEED),
                "predicate_finite": ("the population is the file's own booked rows: late "
                                     "half, finite book-mid markout, finite and strictly "
                                     "positive notional. The resampler adds no predicate "
                                     "of its own, and how many draws it dropped for not "
                                     "being finite is printed beside every interval"),
                "premium_refit_inside_draw": False,
                "premium_means": ("the per-wallet premium is estimated on the disjoint "
                                  "EARLY half and held still, the way the bake-off holds "
                                  "its quoter still: what is measured is the spread of "
                                  "the late-half outcome under a fixed quoting rule, not "
                                  "the spread of the rule"),
                "width_refit_inside_draw": True,
                "width_means": ("the flat width is not a constant chosen by this study "
                                "but the notional-weighted average premium of the rows "
                                "the residual is taken over, so it is a function of the "
                                "sample. A draw holding different wallets has a "
                                "different average premium and has to meet the flat arm "
                                "at THAT width; equality of width is the one thing this "
                                "comparison holds fixed, and a draw that breaks it is a "
                                "draw of some other comparison"),
                "width_held_fixed_is_published_too": (
                    "under ci95_wallet_clustered_width_held_fixed, and it is WIDER rather "
                    "than narrower -- measured, and the opposite of what was expected of "
                    "it. Freezing the width meets most draws at a width they do not have, "
                    "so that difference carries the width gap along with identity. It is "
                    "published as the comparison this file does not lead with"),
            },
            "calibration": calibration,
        }

        if calibration["both_passed"]:
            residual_cells = (
                ("pooled.one_global_constant.identity_residual_bps",
                 payload["pooled"]["one_global_constant"]["identity_residual_bps"],
                 arm_one_constant, ("flat_surcharge_control", "identity_residual_ci",
                                    "pooled", "one_global_constant")),
                ("pooled.per_coin_constants.identity_residual_bps",
                 payload["pooled"]["per_coin_constants"]["identity_residual_bps"],
                 arm_per_coin, ("flat_surcharge_control", "identity_residual_ci",
                                "pooled", "per_coin_constants")),
                ("pooled_at_rank_floor.one_global_constant.identity_residual_bps",
                 payload["pooled_at_rank_floor"]["one_global_constant"]
                        ["identity_residual_bps"],
                 arm_at_floor, ("flat_surcharge_control", "identity_residual_ci",
                                "pooled_at_rank_floor", "one_global_constant")),
            )
            per_coin_cells = tuple(
                (f"by_coin.{name}.identity_residual_bps",
                 payload["by_coin"][name]["identity_residual_bps"],
                 ResampledArm(np.where(booked_rows & (coin == code))[0], premium,
                              np.zeros(int((booked_rows & (coin == code)).sum()),
                                       dtype=np.int64),
                              [name], taker_idx, notional, saturation),
                 ("flat_surcharge_control", "identity_residual_ci", "by_coin", name))
                for code, name in COINS if name in payload["by_coin"])

            records = []
            for address, published_residual, arm, cell in residual_cells + per_coin_cells:
                record = residual_record(address, published_residual, arm, cell)
                records.append(record)
                lo, hi = record["ci95_wallet_clustered_width_refit"]
                print(f"  interval  {address:<58} {record['resampler_point_bps']:+.7f}"
                      f"   ci95 [{lo:+.7f}, {hi:+.7f}]"
                      f"   excludes zero {'yes' if record['ci_excludes_zero'] else 'NO '}"
                      f"   draws at or below zero "
                      f"{100.0 * record['frac_draws_at_or_below_zero']:5.2f}%"
                      f"   {'AGREES' if record['agrees_with_published'] else 'DISAGREES'}",
                      flush=True)

            disagreeing = [r["address"] for r in records if not r["agrees_with_published"]]
            if disagreeing:
                raise AssertionError(
                    f"the resampler's own point estimate does not land on the published "
                    f"residual for {disagreeing}, so its interval is a bound on some "
                    f"other quantity than the number it would be printed beside")

            # ---- is the verdict a property of the data or of the stream ----------------
            def residual_only(m, arm=arm_one_constant):
                true_bps, flat_bps, _ = arm.measures(m)
                return {"residual": true_bps - flat_bps}

            headline = records[0]
            streams = [{
                "stream_cell": headline["stream_cell"],
                "ci95_bps": headline["ci95_wallet_clustered_width_refit"],
                "excludes_zero": headline["ci_excludes_zero"],
                "frac_draws_at_or_below_zero": headline["frac_draws_at_or_below_zero"],
                "declared": True,
            }]
            for k in range(SEED_SWEEP_STREAMS):
                cell = ("flat_surcharge_control", "identity_residual_ci_seed_sweep",
                        "pooled", "one_global_constant", k)
                drawn = wallet_bootstrap(arm_one_constant.n_wallets, cell, residual_only)
                ci, _ = percentile_interval(drawn["residual"])
                streams.append({
                    "stream_cell": list(cell),
                    "ci95_bps": ci,
                    "excludes_zero": _excludes_zero(ci),
                    "frac_draws_at_or_below_zero": float(np.mean(drawn["residual"] <= 0.0)),
                    "declared": False,
                })
            lower = np.array([s["ci95_bps"][0] for s in streams])
            shares = np.array([s["frac_draws_at_or_below_zero"] for s in streams])
            n_excluding = int(sum(1 for s in streams if s["excludes_zero"]))
            stable = n_excluding in (0, len(streams))
            uncertainty["endpoint_reliability"] = {
                "why": ("the headline interval's lower endpoint sits within a thousandth "
                        "of a basis point of zero, so whether it EXCLUDES zero can be a "
                        "property of the stream rather than of the data. Measured rather "
                        "than assumed, on streams that differ in nothing but their "
                        "declared cell identity"),
                "address": headline["address"],
                "n_streams": len(streams),
                "n_streams_excluding_zero": n_excluding,
                "verdict_is_stable_across_streams": bool(stable),
                "lower_endpoint_bps": {
                    "mean": float(np.mean(lower)), "sd": float(np.std(lower)),
                    "min": float(np.min(lower)), "max": float(np.max(lower))},
                "frac_draws_at_or_below_zero": {
                    "min": float(np.min(shares)), "max": float(np.max(shares))},
                "streams": streams,
                "means": ("the quantity to report is frac_draws_at_or_below_zero, which "
                          "is a share and moves smoothly, and NOT the binary flag, which "
                          "is a percentile landing on one side of zero or the other. "
                          "Quoting the flag would be quoting the seed"
                          if not stable else
                          "every stream agrees on the verdict, so the flag is a property "
                          "of the data at this budget"),
                "applies_to_the_other_four": (
                    "the sweep is run on the headline residual only. The other four "
                    "share this estimator, this budget and this wallet universe, so the "
                    "spread measured here is the order their endpoints would move by as "
                    "well -- but that is an inference from a shared construction and NOT "
                    "a measurement on each of them, and it is written down as such "
                    "rather than left to be read as one. What is measured for all five "
                    "is frac_draws_at_or_below_zero, which needs no sweep to read"),
            }

            uncertainty["by_residual"] = records
            uncertainty["reporting_rule"] = (
                "Report the interval WITH the residual, never the residual alone, and "
                "report the share of draws at or below zero rather than the binary "
                "verdict where the sweep shows that verdict changing hands between "
                "streams. The finding this uncertainty carries is not that the residual "
                "is large or small but that it is barely separable from zero, which is "
                "the same direction as the point estimate: most of the gain is width.")
        else:
            uncertainty["refusal"] = (
                "the instrument failed a calibration case, so no interval is published. "
                "An interval whose instrument has not been shown to both exclude zero "
                "and contain it is not a bound on anything, and the same rule this file "
                "applies to a control that has not reproduced its baseline applies here.")

        uncertainty["stream_audit"] = {
            "n_streams_opened": len(_STREAM_CELLS),
            "n_distinct_cells": len(set(_STREAM_CELLS)),
            "colliding_groups": [[list(c) for c in group]
                                 for group in H.colliding_cells(_STREAM_CELLS)],
            "no_two_cells_share_a_stream": not H.colliding_cells(_STREAM_CELLS),
            "means": ("two blocks given one cell identity resample the same wallets "
                      "while reporting independent bands, and that is invisible in every "
                      "number they print"),
        }
        payload["identity_residual_uncertainty"] = uncertainty

    # What this run USED, and the two resampling declarations appear only when a run
    # actually drew: a reproduction that failed publishes no interval, and stamping a
    # draw budget into that artifact would make it assert something about itself that
    # did not happen. The two are CONFIRMATIONS of the declaration rather than
    # deviations from it, which is why each carries a reason saying so -- the same shape
    # mm_bakeoff.py uses for the same pair.
    settings_used = {"h": H.HEADLINE_HORIZON_S, "lens": "mid",
                     "rank_floor_fills": [HEADLINE_FLOOR]}
    if reproduced:
        settings_used.update({
            "n_boot": N_BOOT,
            "master_seed": H.MASTER_SEED,
            "override_reasons": {
                "n_boot": (f"the run drew {N_BOOT} resamples, which IS the declared "
                           f"{H.N_BOOT}: stated as a confirmation and not as a "
                           f"deviation. settings.boot_draws() has no entry for this "
                           f"file because it needs no budget of its own, and its own "
                           f"message names this route"),
                "master_seed": (f"every stream is derived from the declared "
                                f"{H.MASTER_SEED} through settings.rng and the cell "
                                f"identity, so the seed is confirmed rather than "
                                f"overridden; no literal seed stands in this file"),
            },
        })

    artifact.write(
        OUT_NAME,
        payload,
        script=__file__,
        inputs=[npz_path, os.path.join(_CODE_DIR, "quoters", PUBLISHED_FILE)],
        scope={
            "population": (f"late-half fills with a finite {H.HEADLINE_HORIZON_S}s book-mid "
                           "markout and positive notional; the premium each wallet is "
                           "charged is estimated on the disjoint early half"),
            "window": {"early": sorted(early_days), "late": sorted(late_days)},
            "coins": ["BTC", "ETH"],
        },
        started=started,
        settings=settings_used,
        extra_meta={
            "object": ("flat-surcharge control: what the counterparty-resolved premium "
                       "buys over a flat premium of the same notional-weighted width"),
            "supersedes": ("a scratch script held outside this repository with the audit "
                           "trail of 2026-07-29, whose numbers were fitted to the width "
                           "the study published before the entry-price repair of "
                           "2026-08-02 and are not comparable to these"),
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
