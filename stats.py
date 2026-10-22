#!/usr/bin/env python3
"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-07-30
References: Benjamini, Y., Hochberg, Y. (1995). "Controlling the False Discovery Rate:
A Practical and Powerful Approach to Multiple Testing." JRSS-B 57(1), 289-300.
Phipson, B., Smyth, G. K. (2010). "Permutation P-values Should Never Be Zero."
Statistical Applications in Genetics and Molecular Biology 9(1), Article 39.
Efron, B., Tibshirani, R. (1993). An Introduction to the Bootstrap. Chapman & Hall,
chapter 13 (the percentile interval). The budgets and the seed these procedures run
under are declared in settings.py, whose own references are listed there.

ONE PLACE OWNS THE THREE STATISTICAL PROCEDURES THIS WORK REPORTS, SO "DO TWO SCRIPTS
USE THE SAME TEST" IS A QUESTION YOU ANSWER BY RUNNING SOMETHING.

Why this module exists. Counted 30 July over the tracked .py files, and the POPULATION is
stated with every count because censuses of this tree have already disagreed with each
other by counting different things. Excluding this module, settings.py and checks/: 24
files compute a permutation p-value of their own, 6 define their own Benjamini-Hochberg
and 3 more import one of those 6, and 39 construct their own random generator. Nothing at
all calls settings.rng, which has no consumer today.

  The 24 is worth pinning down, because a narrower predicate returns 16 and 16 is the
  number the project plan quotes. The gap is not a mistake in either count. Files holding
  a `def` whose NAME carries "perm" or "placebo" number 20; drop the three under probes/
  and settings.py itself and 16 is left. The other 8 of the 24 compute the p inline
  without wrapping it in a function, so no predicate over function names can see them,
  and that is exactly why the count matters: the procedure written without a name is the
  one no reader finds. Two of those 8 also escaped a first pass of this census, because
  m9_crossasset.py divides by `n_shuffles + 1.0` and follow_the_informed_oos.py writes
  `(1 + count) / (1 + n)` with the one in front. Same arithmetic, three spellings.

WHAT THE 24 ACTUALLY DISAGREE ABOUT. The differences are of two kinds and the whole value
of this module is in keeping them apart.

  A REAL difference states a different null hypothesis, and both spellings are correct
  answers to different questions. Two such differences exist in the tree.

    Which side. 13 files count null draws at or above the observed value (one-sided:
    wallet identity carries MORE signal than chance), 10 count draws whose ABSOLUTE value
    reaches the observed absolute value (two-sided: two rankings agree or disagree more
    than chance), and probes/probe_G_horizon.py does one of each at its two sites. A
    one-sided p on a genuinely two-sided question is half the honest number, so this
    cannot be standardised away. It is the `side` argument.

    What is held fixed while the labels move. 21 files shuffle labels across the whole
    eligible sample. Three state a MATCHED null instead: own_size_control.py permutes
    within size deciles, follow_the_informed_oos.py within activity quantile bins, and
    t1_toxicity_skew_backtest.py draws a notional-stratified set. That is the point of
    those three -- they ask whether wallet identity carries anything the bucket does not
    already carry, and the two nulls give different answers on the same data by
    construction. The self-test below demonstrates that on a fixture. It is the `strata`
    argument.

  An INCIDENTAL difference is one spelling of one question, and one spelling is simply
  better. Four exist, and this module fixes each one way and says which way.

    The +1. All 24 have it -- p = (count + 1) / (N + 1), never count / N -- so there is
    no disagreement to fix here, only a rule to keep. A p of exactly zero is not a small
    probability, it is the statement that the budget ran out, and Phipson and Smyth
    (2010) is the reference for why the observed labelling counts as one draw of its own
    null.

    WHICH N goes in the denominator. 18 files divide by the REQUESTED budget; 6
    (i2_walletfe, i3_depth_control, own_size_control, panel_common_idio,
    follow_the_informed_oos, probes/probe_F_hlp_liq) divide by the count of draws that
    came back finite. The second is right and this module does it. A permutation of a
    degenerate cell returns NaN, and dividing by a budget that includes draws which
    produced no statistic claims a resolution the run did not have: with 2000 requested
    and 400 usable, the honest floor is 1/401 = 0.0025 against a claimed 1/2001 = 0.0005,
    a factor of five on the smallest number the procedure can express. Both counts are
    returned, so an artifact records the gap instead of hiding it.

    The comparison tolerance. 11 files count `null >= observed - tol` and 13 count
    `null >= observed`. A tolerance is right, and not for floating-point hygiene: a
    permutation that reproduces the observed grouping recomputes the statistic through a
    different summation order and lands one unit in the last place below it. Without the
    tolerance that draw counts as NOT extreme, so the p is biased DOWN, towards
    significance, exactly on the cells where the evidence is thinnest. An exact tie
    counts either way, which is the obvious wrong reason to keep a tolerance and is why
    the self-test demonstrates it on an ulp instead.

    What KIND of tolerance is the part this module got wrong first and fixed second. Ten
    of the 11 write 1e-12 and maker_econ_b2.py writes 1e-9, and the obvious reading --
    that the odd one out is a typo three orders too loose -- is backwards. Its statistic
    is a dollar delta of about 1.65 million, where one unit in the last place is 2.3e-10:
    1e-9 is 4.3 of them and 1e-12 is 0.004 of one, so at that magnitude the majority
    spelling cannot change any comparison at all and the minority spelling is the only
    one doing anything. An ABSOLUTE tolerance is therefore the wrong instrument for a
    tree whose statistics run from a correlation bounded by one to a sum of dollars in
    the millions. The rule here is relative to the scale of the comparison, so it is the
    same few thousand ulps at either end; see EXTREME_REL_TOL.

    What a failed draw becomes. 22 files drop a NaN draw. Two (temp_perm_decomp.py and
    probes/probe_G_horizon.py) substitute 0.0 for it. Substituting is the one incidental
    difference here that moves a number in a stated direction: a null centred near zero
    gains mass at its centre, so for a positive observed statistic the count of extreme
    draws falls and the p falls with it. The self-test measures how far on a fixture.
    This module drops the draw and reports how many it dropped.

WHAT THIS MODULE DOES NOT DO. It does not choose a statistic and it does not know what
any number means. The caller passes the statistic, because what is being permuted is the
substance of each test and belongs with the script that owns the question. This module
owns the counting, the floor, the correction and the generator.

EVERY FUNCTION RETURNS THE PROCEDURE, NOT ONLY THE NUMBER. A p-value with no draw count
beside it cannot be read: 0.0005 from a budget of 2000 and 0.0005 from a budget of 2000
of which 1600 failed are the same digits and different evidence. So each return value
carries the counts, the floor, the side, the cell and the method string, and a producer
hands that block straight to artifact.write, which is how a results file comes to record
its procedure and not just its result.

Usage:

    import stats

    perm = stats.permutation_test(
        observed=rho, null_statistic=lambda rng: spearman(x, rng.permutation(y)),
        n_draws=settings.N_PERM, cell=("early_late_rank_persistence", "BTC", 50),
        side="two_sided")
    ci = stats.bootstrap_ci(x.size, lambda idx: float(x[idx].mean()),
                            cell=("mean_markout", "BTC"), n_boot=settings.N_BOOT)
    fam = stats.benjamini_hochberg([c["p"] for c in cells])

Self-test, since this repository has no separate test directory:

    uv run --no-project --with-requirements requirements.txt python3 stats.py
"""
import math
import os
import sys

import numpy as np

# The module's own directory, so settings.py is importable however the producer was
# launched. No path this module builds leaves the repository and none is ever recorded;
# checks/chk_no_abs_paths.py enforces that across the tree.
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import settings  # noqa: E402  (the path above has to be set first)

# Re-exported rather than re-implemented. The floor and the "is this p a measurement or
# the budget's smallest expressible value" test already live in settings.py beside the
# budget that determines them, and a second copy here would be the defect this module
# exists to remove.
p_floor = settings.p_floor
p_is_floored = settings.p_is_floored

# The comparison slack, argued in the module docstring, and RELATIVE on purpose.
#
# The first version of this module wrote 1e-12 as an ABSOLUTE constant, copying the
# spelling most of the tree uses. That is wrong, and measuring the tree is what showed
# it. A slack is meant to be a few units in the last place, and an absolute constant is
# a different number of them at every magnitude. Measured 30 July on the two extremes
# this work actually spans:
#
#   statistic                        magnitude    1e-12 is        1e-9 is
#   Spearman rho                     1            4504 ulp        4.5e6 ulp
#   maker_econ_b2 delta, US dollars  1.65e6       0.0043 ulp      4.3 ulp
#
# So at dollar scale an absolute 1e-12 cannot even be represented: `d >= obs - 1e-12`
# is bit-identical to `d >= obs`, and the tolerance silently does nothing in the one
# file whose statistic is largest. This also settles what looked like a typo. Eleven
# files write 1e-12 and maker_econ_b2.py writes 1e-9, three orders looser, and the
# obvious reading is that 1e-9 is the mistake. The arithmetic says the opposite: its
# statistic is a dollar delta of about 1.65 million, 1e-9 is 4.3 ulp there, and 1e-9 is
# the only one of the two spellings that does anything at that magnitude.
#
# The rule that serves both: scale the slack by the largest magnitude in the comparison
# -- the observed value or the largest null draw -- so it is the same number of ulps for
# rho and for dollars, and the caller never has to know the units. A caller who wants an
# absolute slack passes abs_tol and says so.
EXTREME_REL_TOL = 1e-12


def _slack(observed, draws, rel_tol, abs_tol):
    """The absolute comparison slack for one test, from the scale of what it compares.

    Anchored on the largest magnitude in play rather than on the observed value alone,
    because an observed statistic near zero would otherwise get a slack near zero --
    the tolerance would vanish exactly where the statistic is smallest. Both arrays are
    already finite-filtered by the caller. An all-zero comparison gets a slack of zero,
    which is right: there is no rounding to absorb.
    """
    if abs_tol is not None:
        return float(abs_tol)
    scale = abs(float(observed)) if np.isfinite(observed) else 0.0
    if draws is not None and len(draws):
        scale = max(scale, float(np.max(np.abs(draws))))
    return float(rel_tol) * scale

# The two nulls the tree actually states. A third would be a new hypothesis and belongs
# here with the sentence that says what it means, not inside one script.
SIDES = ("greater", "less", "two_sided")

# Percentile is the only interval method in the tree: every bootstrap in every script
# takes the 2.5 and 97.5 percentiles of the resampled statistic. Named so the artifact
# records the method rather than leaving a reader to infer it from two numbers, and so
# that a future bias-corrected interval arrives as a declared second value rather than
# as a silent change of meaning under the same key.
CI_METHOD = "percentile"


# =====================================================================
# 1. THE GENERATOR: ONE STREAM PER NAMED CELL, FROM ONE HEAD SEED
# =====================================================================

def rng(*cell):
    """The generator for one named cell. The only way this module gets randomness.

    A PASS-THROUGH to settings.rng, deliberately, and this is the second version of this
    function. The first re-encoded the cell before handing it over, because settings.rng
    flattened a string into character codes with nothing marking where a component ended
    and drew the same stream for rng("AB") and rng(65, 66). settings.py has since closed
    that ambiguity at the source, by REFUSING a cell that names nothing rather than by
    re-encoding it, and once it is closed there the re-encoding here is worse than
    useless: it would make stats.permutation_test(cell=("ws2", "auc_placebo", 10)) draw a
    different stream from settings.rng("ws2", "auc_placebo", 10), so two scripts naming
    one cell would get two nulls depending on which of them went through this module.
    That is the very divergence this module exists to remove, so the flattening stays in
    exactly one place and this function adds nothing to it.

    Why a cell and not a seed. A single global generator makes every result depend on
    the ORDER the cells were computed in, so inserting a coin changes an earlier number.
    A literal seed per script has the opposite defect: two scripts drawing the same
    stream look independent and are not. The argument is settings.rng's, not this
    module's, which is why the stream is still built there.

    The cell NAMES the quantity as well as its coordinates. cell=("BTC", 50) seeds the
    permutation of the rank persistence and the bootstrap of the mean markout from one
    stream; ("rank_persistence", "BTC", 50) and ("mean_markout", "BTC", 50) do not.
    Reusing one stream for two procedures is not wrong, but it is an unstated coupling,
    and the cost of stating it is one string.
    """
    if not cell:
        raise ValueError(
            "a generator needs a cell identity. Pass at least the name of the quantity "
            "being computed, so two procedures in one script do not share a stream "
            "without saying so")
    return settings.rng(*cell)


# =====================================================================
# 2. PERMUTATION: THE COUNT, THE FLOOR, AND WHAT WAS HELD FIXED
# =====================================================================

def shuffled(labels, generator, strata=None):
    """One relabelling draw. `strata` is the whole real difference between the nulls.

    strata=None permutes the labels across the entire sample: the null is "wallet
    identity carries no signal at all".

    strata=<array> permutes them only WITHIN each stratum: the null is "wallet identity
    carries nothing beyond what the stratum already carries". Fifteen procedures in this
    tree want the first and own_size_control.py wants the second, and neither is a
    stricter setting of the other -- they answer different questions and can disagree in
    both directions on the same data.

    The within-stratum draw is done by sorting on (stratum, uniform key) rather than by
    looping over strata, so the cost is one sort per draw regardless of how many strata
    there are. The stratum component dominates the key, so the order within a stratum is
    the only thing the random part decides, which is what makes the permutation
    stratum-preserving. A stratum of size one contributes a fixed point and no
    randomness, which is correct and is why the count of such strata is worth knowing
    before reading a within-stratum p.
    """
    values = np.asarray(labels)
    if strata is None:
        return generator.permutation(values)
    strata = np.asarray(strata)
    if strata.shape[0] != values.shape[0]:
        raise ValueError(
            f"strata has {strata.shape[0]} rows against {values.shape[0]} labels; a "
            "within-stratum permutation needs one stratum per row")
    # Dense stratum index, so the sort key is bounded by the stratum count rather than
    # by whatever the caller's stratum labels happen to be.
    _, dense = np.unique(strata, return_inverse=True)
    key = dense.astype(np.float64) + generator.random(values.shape[0])
    return values[np.argsort(key, kind="stable")]


def _extreme_count(observed, draws, side, tol):
    """How many null draws are at least as extreme as the observed value."""
    if side == "greater":
        return int(np.sum(draws >= observed - tol))
    if side == "less":
        return int(np.sum(draws <= observed + tol))
    if side == "two_sided":
        return int(np.sum(np.abs(draws) >= abs(observed) - tol))
    raise ValueError(f"side must be one of {SIDES}, got {side!r}")


def permutation_p(observed, null_draws, *, side="greater", rel_tol=EXTREME_REL_TOL,
                  abs_tol=None, n_requested=None, cell=None):
    """The p-value of an already-computed null, plus everything needed to read it.

    Use this when the caller builds its null in one vectorised operation, which most of
    this tree does. permutation_test below is the same procedure with the draw loop
    included, for callers whose statistic cannot be vectorised.

    observed     the statistic on the real labelling.
    null_draws   the statistic under each relabelling. NaN entries are DROPPED and
                 counted, never replaced: a draw substituted by zero adds mass at the
                 centre of the null and pushes a one-sided p down, towards significance.
    side         see SIDES; a one-sided p on a two-sided question is half the honest one.
    rel_tol      comparison slack as a FRACTION of the scale of the comparison, so the
                 same declaration is the same number of ulps for a correlation and for a
                 dollar sum. See EXTREME_REL_TOL for what an absolute constant costs.
    abs_tol      an absolute slack instead, for a caller who knows its own units.
    n_requested  the budget asked for, when it differs from len(null_draws).

    The returned p is (extreme + 1) / (usable + 1), and it is the USABLE count in the
    denominator on purpose: see the module docstring. n_draws_requested and
    n_draws_usable are both returned so an artifact records the difference.
    """
    if side not in SIDES:
        raise ValueError(f"side must be one of {SIDES}, got {side!r}")
    draws = np.asarray(null_draws, dtype=np.float64).ravel()
    requested = int(len(draws) if n_requested is None else n_requested)
    usable = draws[np.isfinite(draws)]
    n_usable = int(usable.size)
    tol = _slack(observed, usable, rel_tol, abs_tol)

    block = {
        "procedure": "label permutation",
        "side": side,
        "n_draws_requested": requested,
        "n_draws_usable": n_usable,
        "n_draws_dropped": int(requested - n_usable),
        # Both the slack applied and the rule that produced it, because an absolute
        # number alone cannot be checked against a statistic whose units are elsewhere.
        "tolerance_absolute": float(tol),
        "tolerance_relative": None if abs_tol is not None else float(rel_tol),
        "tolerance_rule": ("absolute, stated by the caller" if abs_tol is not None
                           else "relative to the largest magnitude in the comparison"),
        "cell": list(cell) if cell is not None else None,
        "method": ("permutation p = (draws at least as extreme + 1) / (usable draws + 1);"
                   " the observed labelling counts as one draw of its own null, so p is "
                   "floored at 1/(usable + 1) and is never zero"),
    }
    if n_usable == 0 or not np.isfinite(observed):
        block.update({"observed": _finite_or_none(observed), "p": None,
                      "p_floor": None, "p_is_floored": False,
                      "n_at_least_as_extreme": 0,
                      "null_mean": None, "null_sd": None,
                      "note": "no usable draw, or the observed statistic is not finite; "
                              "this cell has no test rather than a large p"})
        return block

    n_extreme = _extreme_count(float(observed), usable, side, float(tol))
    floor = 1.0 / (n_usable + 1.0)
    p = (n_extreme + 1.0) / (n_usable + 1.0)
    block.update({
        "observed": float(observed),
        "p": float(p),
        "p_floor": float(floor),
        # True says no draw reached the observed value, so p is the smallest number this
        # budget can express and the true p is unknown below it. It is not a measurement
        # and prose must not read it as one.
        "p_is_floored": bool(abs(p - floor) <= 1e-12),
        "n_at_least_as_extreme": int(n_extreme),
        "null_mean": float(np.mean(usable)),
        "null_sd": float(np.std(usable, ddof=1)) if n_usable > 1 else 0.0,
        "null_p95": float(np.percentile(usable, 95)),
    })
    return block


def permutation_test(observed, null_statistic, *, n_draws, cell, side="greater",
                     rel_tol=EXTREME_REL_TOL, abs_tol=None):
    """Draw the null with this module's generator, then count it.

    null_statistic(generator) -> float is called n_draws times with ONE generator, so the
    draws are successive states of a single stream rather than n_draws streams seeded
    apart. The caller decides what the relabelling is; `shuffled` above is the primitive
    for the two nulls this tree states.

    The generator comes from the cell, which is why a re-run of one cell reproduces its
    p exactly and two cells do not share a null. The cell is recorded in the returned
    block, so an artifact says which stream produced the number.
    """
    if int(n_draws) < 1:
        raise ValueError(f"n_draws must be at least 1, got {n_draws}")
    generator = rng(*cell)
    draws = np.empty(int(n_draws), dtype=np.float64)
    for i in range(int(n_draws)):
        value = null_statistic(generator)
        draws[i] = float(value) if value is not None else np.nan
    return permutation_p(observed, draws, side=side, rel_tol=rel_tol, abs_tol=abs_tol,
                         n_requested=int(n_draws), cell=cell)


def budget_check(n_draws, family_size, alpha=None):
    """Can a p from this budget clear its multiplicity correction at rank one.

    The failure this catches is silent and is live in this tree today. Benjamini-Hochberg
    compares the smallest p in a family against alpha/m. A permutation budget of 200 has
    a floor of 1/201 = 0.00498; against a family of 48 at the 0.05 level the rank-one bar
    is 0.00104. No p from that budget can clear it AT ANY EFFECT SIZE, and the run does
    not complain: it reports a p at its floor and the correction rejects it.

    Returns the two numbers and the verdict rather than raising, because a script may
    legitimately report an uncorrected p; what it may not do is report a corrected one
    without knowing this.
    """
    alpha = settings.FDR_ALPHA if alpha is None else float(alpha)
    floor = 1.0 / (int(n_draws) + 1.0)
    rank1 = alpha / max(int(family_size), 1)
    return {
        "n_draws": int(n_draws),
        "family_size": int(family_size),
        "alpha": float(alpha),
        "p_floor": float(floor),
        "rank1_threshold": float(rank1),
        "floor_can_clear_rank1": bool(floor <= rank1),
        "min_draws_for_family": int(settings.min_perm_draws(
            family_size=max(int(family_size), 1), alpha=alpha, quantum=1)),
        "note": ("a budget whose floor sits above the rank-one threshold cannot produce "
                 "a significant corrected result however strong the effect is"),
    }


# =====================================================================
# 3. BOOTSTRAP: THE PERCENTILE INTERVAL, WITH ITS RESOLUTION STATED
# =====================================================================

def bootstrap_ci(n, statistic, *, cell, n_boot=None, alpha=0.05):
    """A percentile confidence interval for any statistic of a resampled row index.

    n           number of rows in the sample being resampled.
    statistic   statistic(index_array) -> float. An index rather than the values, so one
                function covers a plain mean, a notional-weighted mean, a Spearman on a
                PAIR of vectors and a Gini -- all of which this tree bootstraps, and
                three of which cannot be expressed as a function of one value vector.
    cell        the named cell, as for the permutation. One stream per cell.
    alpha       0.05 gives the 2.5 and 97.5 percentiles, which is what every bootstrap
                in this tree already reports.

    The interval is the PERCENTILE interval and the returned block says so. It is not
    bias-corrected, and for a skewed statistic on a small sample that matters; naming
    the method is what lets a reviewer weigh it instead of guessing which one was used.

    draws_per_tail is returned because it is the resolution of the endpoint and the one
    number that says whether the budget was adequate. A 95% interval puts n_boot * 0.025
    draws in each tail: at the declared 2000 that is 50, and at the 300 one script
    defaults to it is seven and a half, meaning the endpoint is decided by about eight
    draws and moves visibly between seeds.
    """
    n_boot = int(settings.N_BOOT if n_boot is None else n_boot)
    if int(n) < 2:
        return _empty_ci(n_boot, alpha, cell,
                         "fewer than two rows: a resample cannot vary")
    if n_boot < 1:
        raise ValueError(f"n_boot must be at least 1, got {n_boot}")

    generator = rng(*cell)
    point = statistic(np.arange(int(n)))
    draws = np.empty(n_boot, dtype=np.float64)
    for b in range(n_boot):
        value = statistic(generator.integers(0, int(n), size=int(n)))
        draws[b] = float(value) if value is not None else np.nan
    usable = draws[np.isfinite(draws)]

    block = {
        "procedure": "bootstrap confidence interval",
        "method": CI_METHOD,
        "method_note": ("percentile interval: the alpha/2 and 1-alpha/2 percentiles of "
                        "the resampled statistic, resampling rows with replacement. Not "
                        "bias-corrected"),
        "alpha": float(alpha),
        "n_rows": int(n),
        "n_boot_requested": n_boot,
        "n_boot_usable": int(usable.size),
        "draws_per_tail": float(usable.size * alpha / 2.0),
        "cell": list(cell),
        "point": _finite_or_none(point),
    }
    if usable.size < 2:
        block.update({"lo": None, "hi": None,
                      "note": "fewer than two usable resamples; no interval"})
        return block
    lo, hi = np.percentile(usable, [100.0 * alpha / 2.0, 100.0 * (1.0 - alpha / 2.0)])
    block.update({
        "lo": float(lo),
        "hi": float(hi),
        "excludes_zero": bool(lo > 0.0 or hi < 0.0),
        "boot_mean": float(np.mean(usable)),
        "boot_sd": float(np.std(usable, ddof=1)),
    })
    return block


def bootstrap_mean_ci(values, *, cell, n_boot=None, alpha=0.05, weights=None):
    """The common case: an interval for a mean, weighted or not.

    Rows where the value or the weight is not finite, or where the weight is not
    positive, are dropped BEFORE resampling and the count of what survived is returned.
    Dropping inside each resample instead would make the effective sample size vary
    between draws, which widens the interval for a reason that has nothing to do with
    the sampling variability it is meant to measure.
    """
    v = np.asarray(values, dtype=np.float64).ravel()
    if weights is None:
        keep = np.isfinite(v)
        v = v[keep]
        w = None
    else:
        w = np.asarray(weights, dtype=np.float64).ravel()
        if w.size != v.size:
            raise ValueError(f"{w.size} weights against {v.size} values")
        keep = np.isfinite(v) & np.isfinite(w) & (w > 0)
        v, w = v[keep], w[keep]

    if w is None:
        def statistic(idx):
            return float(np.mean(v[idx]))
    else:
        def statistic(idx):
            ws = w[idx]
            total = ws.sum()
            return float(np.sum(v[idx] * ws) / total) if total > 0 else np.nan

    block = bootstrap_ci(v.size, statistic, cell=cell, n_boot=n_boot, alpha=alpha)
    block["n_dropped_not_finite"] = int(np.asarray(values).size - v.size)
    block["weighted"] = weights is not None
    return block


def _empty_ci(n_boot, alpha, cell, note):
    return {"procedure": "bootstrap confidence interval", "method": CI_METHOD,
            "alpha": float(alpha), "n_boot_requested": int(n_boot),
            "n_boot_usable": 0, "draws_per_tail": 0.0, "cell": list(cell),
            "point": None, "lo": None, "hi": None, "note": note}


# =====================================================================
# 4. MULTIPLICITY: BENJAMINI-HOCHBERG, WITH THE THRESHOLD RETURNED
# =====================================================================

def benjamini_hochberg(pvals, *, alpha=None, family=None):
    """Step-up FDR correction over a family of cells.

    Six scripts define this and they agree: sort ascending, q_(i) = p_(i) * m / i,
    enforce monotonicity by a running minimum from the largest p downward, clip to one,
    carry NaN through without counting it in m. The self-test below runs the two
    spellings the tree uses against this one on random families including ties and NaN,
    so the consolidation is shown to move no number rather than assumed to.

    What none of the six returns is the THRESHOLD, and that is the reason this function
    exists rather than one of them being imported. A verdict without its bar cannot be
    read at all: "significant after correction" means nothing until the number the p was
    compared against is on the page, and it is not a constant -- it depends on the family
    size, which differs across this work from 4 to 448 for the same alpha.

    Returns the q-values aligned to the input, the rejection flags, the family size, the
    applied cutoff, and the rank-one bar alpha/m, which is the number a single cell has
    to clear ON ITS OWN and the one the permutation budget in settings.py is sized for.

    `family` names what the family IS -- the set of cells the correction is taken over.
    It goes into the block because the same p corrected over a family of 4 and over one
    of 448 gives two different verdicts, and an artifact that records only the verdict
    cannot be checked.
    """
    alpha = settings.FDR_ALPHA if alpha is None else float(alpha)
    p = np.array([np.nan if v is None else float(v) for v in pvals], dtype=np.float64)
    testable = p[~np.isnan(p)]
    if testable.size and (testable.min() < 0.0 or testable.max() > 1.0):
        raise ValueError(
            "a p-value outside [0, 1] reached the correction; the usual cause is a "
            "count divided by a budget rather than by a budget plus one")

    q = np.full(p.size, np.nan, dtype=np.float64)
    rejected = np.zeros(p.size, dtype=bool)
    valid = np.where(~np.isnan(p))[0]
    m = int(valid.size)

    block = {
        "procedure": "Benjamini-Hochberg step-up FDR",
        "method": ("sort ascending, q_(i) = p_(i) * m / i, running minimum from the "
                   "largest p downward, clipped to 1; NaN p-values are carried through "
                   "and excluded from the family size"),
        "alpha": float(alpha),
        "family": family,
        "family_size": m,
        "n_cells": int(p.size),
        "n_not_testable": int(p.size - m),
    }
    if m == 0:
        block.update({"q": [None] * p.size, "rejected": [False] * p.size,
                      "n_rejected": 0, "threshold": None,
                      "rank1_threshold": None,
                      "note": "no testable cell in this family"})
        return block

    order = valid[np.argsort(p[valid], kind="stable")]
    ranks = np.arange(1, m + 1, dtype=np.float64)
    scaled = p[order] * m / ranks
    scaled = np.minimum.accumulate(scaled[::-1])[::-1]
    q[order] = np.clip(scaled, 0.0, 1.0)

    # The step-up rejection stated as the procedure states it: the largest rank k whose
    # own p clears k*alpha/m, and everything ranked at or below k is rejected. Reported
    # as well as q <= alpha, which is equivalent, because the CUTOFF is what a reader
    # needs and only this form produces it.
    passes = np.where(p[order] <= ranks * alpha / m)[0]
    if passes.size:
        k = int(passes[-1]) + 1
        rejected[order[:k]] = True
        threshold = float(k * alpha / m)
    else:
        k = 0
        # Nothing was rejected, so no cutoff was applied. The bar the best cell failed is
        # the rank-one bar, and that is the honest thing to report as the threshold.
        threshold = float(alpha / m)

    block.update({
        "q": [None if np.isnan(v) else float(v) for v in q],
        "rejected": [bool(v) for v in rejected],
        "n_rejected": int(k),
        "threshold": threshold,
        "threshold_meaning": ("the p-value cutoff actually applied: the largest rank k "
                              "with p_(k) <= k*alpha/m, times alpha/m. With no rejection "
                              "it is the rank-one bar the best cell failed"),
        "rank1_threshold": float(alpha / m),
        "smallest_p": float(np.nanmin(p)),
        "largest_p_rejected": float(p[order[k - 1]]) if k else None,
    })
    return block


def _finite_or_none(x):
    """A float for JSON, or None where the value is not a number.

    NaN is not valid JSON and json.dump writes the bare token NaN, which a strict reader
    rejects and a lenient one silently turns into a float. None says the same thing in a
    form every reader agrees about.
    """
    try:
        value = float(x)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


# =====================================================================
# 5. DESCRIPTIVE AND CONCENTRATION STATISTICS
#
# Seven procedures that four scripts each carried a private copy of: m11_concentration.py
# and m8_makerside.py held gini, hhi, top_k_share, top_pct_share and the quantile summary,
# m5_termstructure.py and m7_size.py held safe_mean and weighted_mean. Compared before the
# move, pair by pair, on the syntax tree with the docstring removed: all seven pairs are
# identical. Five are identical byte for byte as well; gini differed by one comment line
# and the quantile summary by a line break and a trailing comment. So nothing here states
# a second opinion about how a quantity is computed, which is the only reason a duplicate
# is worth keeping, and the copies are replaced by an import.
#
# The quantile summary arrives under the longer of its two names. m8_makerside.py called
# it describe, and that word is already taken in this tree: artifact.py:536 defines a
# describe() that reports on a results FILE, not on a vector. Two homonyms one import
# apart is how a reader ends up calling the wrong one.
# =====================================================================

def safe_mean(values):
    """Mean of the finite entries; NaN if none are finite."""
    v = np.asarray(values, dtype=np.float64)
    v = v[np.isfinite(v)]
    return float(v.mean()) if v.size else float("nan")


def weighted_mean(values, weights):
    """Notional-weighted mean over finite, positive-weight entries; NaN if none.

    Each row is weighted by its notional, so a curve or a bucket mean reflects dollars
    at risk rather than trade count. Rows with a non-finite value, a non-finite weight,
    or a non-positive weight are dropped, which matters where the notional is itself
    skewed: inside the top 1% of fills the equal-weight mean and this one differ a lot.
    """
    v = np.asarray(values, dtype=np.float64)
    w = np.asarray(weights, dtype=np.float64)
    ok = np.isfinite(v) & np.isfinite(w) & (w > 0)
    if not np.any(ok):
        return float("nan")
    wsum = w[ok].sum()
    if wsum <= 0:
        return float("nan")
    return float(np.sum(v[ok] * w[ok]) / wsum)


def gini(values):
    """Gini coefficient of a non-negative vector.

    The Lorenz / Gini construction needs non-negative weights with a positive total.
    Callers pass the appropriate non-negative subset (e.g. positive dollar cost, or
    per-dollar markout shifted to be non-negative). Returns NaN if the vector is empty
    or the total is non-positive.
    """
    v = np.sort(np.asarray(values, dtype=np.float64))
    n = v.size
    if n == 0:
        return float("nan")
    total = v.sum()
    if total <= 0:
        return float("nan")
    # G = (2 * sum(i * v_i) / (n * sum v)) - (n + 1) / n, with i = 1..n
    idx = np.arange(1, n + 1, dtype=np.float64)
    return float((2.0 * np.sum(idx * v)) / (n * total) - (n + 1.0) / n)


def hhi(values):
    """Herfindahl-Hirschman index of shares (sum of squared shares).

    Computed on positive values only (shares must be non-negative and sum to 1). Ranges
    from 1/n (perfectly even) to 1 (one unit holds everything). Returns NaN if the
    positive total is non-positive.
    """
    v = np.asarray(values, dtype=np.float64)
    v = v[v > 0]
    total = v.sum()
    if v.size == 0 or total <= 0:
        return float("nan")
    shares = v / total
    return float(np.sum(shares * shares))


def top_k_share(sorted_desc, total, k):
    """Share of total held by the top-k highest values.

    sorted_desc : value vector already sorted high-to-low, as an array.
    total       : reference total, so that 'full' and 'drop-top-k' can use a consistent
                  base when the caller wants that.
    Returns NaN if total is non-positive or the vector is empty.
    """
    if total <= 0 or sorted_desc.size == 0:
        return float("nan")
    kk = int(min(k, sorted_desc.size))
    return float(sorted_desc[:kk].sum() / total)


def top_pct_share(sorted_desc, total, pct):
    """Share of total held by the top `pct` fraction of units.

    pct = 0.01 gives the top 1%. At least one unit is always counted. Returns NaN if
    total is non-positive or the vector is empty.
    """
    if total <= 0 or sorted_desc.size == 0:
        return float("nan")
    k = max(1, int(np.ceil(sorted_desc.size * pct)))
    return float(sorted_desc[:k].sum() / total)


def describe_quantiles(values):
    """Min / quartiles / mean of a finite vector, as plain floats.

    frac_positive is the share of entries above zero, which on the maker side reads as
    the share of counterparties that are adverse-selected.
    """
    v = np.asarray(values, dtype=np.float64)
    v = v[np.isfinite(v)]
    if v.size == 0:
        return {"n": 0, "mean": float("nan"), "min": float("nan"),
                "p25": float("nan"), "p50": float("nan"),
                "p75": float("nan"), "p99": float("nan"),
                "max": float("nan"), "frac_positive": float("nan")}
    return {
        "n": int(v.size),
        "mean": float(v.mean()),
        "min": float(v.min()),
        "p25": float(np.percentile(v, 25)),
        "p50": float(np.percentile(v, 50)),
        "p75": float(np.percentile(v, 75)),
        "p99": float(np.percentile(v, 99)),
        "max": float(v.max()),
        "frac_positive": float(np.mean(v > 0)),
    }


# =====================================================================
# 6. RANK AND CORRELATION
#
# The two pieces every Spearman in this tree is built from. Three scripts carried a
# private rankdata -- checks/chk_closedpnl.py, m4_realizedpnl.py and m6_inventory.py --
# and two of those three carried a private Pearson as well. The three rankdata spellings
# differ by the parameter name and two comments and by nothing else, which was checked by
# RUNNING all three against each other rather than by reading them: nine fixtures,
# including the empty array, an all-tied vector, a vector 200 long with runs of four
# ties, and a vector holding NaN. Zero disagreements.
#
# ONE NAME IN THIS TREE COVERS FIVE DIFFERENT BODIES, so the check above is not
# ceremony. Counted by name, `_rankdata` is defined eleven times; counted by content it
# resolves to five distinct bodies. Only the three named above are consolidated here.
# The others keep their own definitions until they are measured the same way.
#
# NaN is not filtered and gets sorted to the end, so a vector holding NaN receives the
# HIGHEST ranks for its missing entries. Every caller in this tree filters to the finite
# subset before it gets here. Stated rather than fixed, because changing it would change
# published numbers for anyone who does not filter, and no such caller exists today.
# =====================================================================

def rankdata(a):
    """Ranks 1..n with ties averaged, in the input's own order.

    The sort is stable (mergesort), so the rank a tied run receives does not depend on
    the order numpy happened to visit it in, and two runs of the same data give the same
    array bit for bit. An empty input returns an empty float64 array rather than raising,
    which is what lets a caller rank an empty cut without a special case.
    """
    a = np.asarray(a, dtype=np.float64)
    n = a.size
    if n == 0:
        return np.empty(0, dtype=np.float64)
    order = np.argsort(a, kind="mergesort")
    ranks = np.empty(n, dtype=np.float64)
    sa = a[order]
    # positions 0..n-1 map to raw ranks 1..n; average within each tied run
    i = 0
    while i < n:
        j = i + 1
        while j < n and sa[j] == sa[i]:
            j += 1
        avg = (i + j - 1) / 2.0 + 1.0
        ranks[order[i:j]] = avg
        i = j
    return ranks


def pearson_r(x, y):
    """Pearson correlation of two aligned 1-D arrays; NaN if undefined.

    Undefined has two causes and both return NaN: fewer than two points, and one side
    being constant, which makes the denominator zero. Feed it two rankdata outputs and
    it is Spearman.
    """
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    if x.size < 2:
        return float("nan")
    xc = x - x.mean()
    yc = y - y.mean()
    denom = np.sqrt(np.sum(xc * xc) * np.sum(yc * yc))
    if denom <= 0:
        return float("nan")          # one side is constant -> correlation undefined
    return float(np.sum(xc * yc) / denom)


# =====================================================================
# SELF-TEST
#
# In this module rather than in a test directory, because the repository has none and a
# reader cloning it runs what is in front of them. Every check either states a number
# it expects or shows the two sides it compares; a check that would pass on any data is
# not a check, so the arguments that matter are run on a fixture with a KNOWN answer and
# on a fixture with a known NON-answer.
# =====================================================================

def _legacy_bh_loop(pvals):
    """The BH spelling in ks2_persistence_10day.py and panel_common_idio.py."""
    p = np.array([np.nan if (v is None) else float(v) for v in pvals], dtype=np.float64)
    q = np.full(p.size, np.nan, dtype=np.float64)
    finite = np.where(~np.isnan(p))[0]
    m = finite.size
    if m == 0:
        return [None] * p.size
    order = finite[np.argsort(p[finite], kind="stable")]
    prev = 1.0
    for rank in range(m, 0, -1):
        idx = order[rank - 1]
        prev = min(prev, p[idx] * m / rank)
        q[idx] = min(prev, 1.0)
    return [None if np.isnan(v) else float(v) for v in q]


def _legacy_bh_vectorised(pvals):
    """The BH spelling in i3_nonrecoverability_oos, own_size_control, panel_build."""
    p = np.asarray(pvals, dtype=np.float64)
    q = np.full(p.size, np.nan, dtype=np.float64)
    valid = np.where(~np.isnan(p))[0]
    m = valid.size
    if m == 0:
        return q
    pv = p[valid]
    order = np.argsort(pv, kind="stable")
    ranks = np.arange(1, m + 1, dtype=np.float64)
    q_sorted = np.clip(np.minimum.accumulate((pv[order] * m / ranks)[::-1])[::-1], 0, 1)
    q_valid = np.empty(m, dtype=np.float64)
    q_valid[order] = q_sorted
    q[valid] = q_valid
    return q


def _self_test():
    failures = []

    def check(name, ok, detail=""):
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" -- {detail}" if detail else ""))
        if not ok:
            failures.append(name)

    def group_gap(y, labels):
        """|mean(y | label 1) - mean(y | label 0)|, the fixture statistic throughout."""
        a, b = y[labels == 1], y[labels == 0]
        if a.size == 0 or b.size == 0:
            return np.nan
        return abs(float(a.mean()) - float(b.mean()))

    print("-- 1. the floor: no p is ever zero, and a floored p says so --")
    block = permutation_p(10.0, np.zeros(500), side="greater")
    check("a null no draw of which reaches the observed value gives the floor, not 0",
          block["p"] == block["p_floor"] and block["p_is_floored"],
          f"p = {block['p']:.6f} = 1/501")
    block2 = permutation_p(0.0, np.zeros(500), side="greater")
    check("a null every draw of which ties the observed value gives p = 1",
          abs(block2["p"] - 1.0) < 1e-12,
          "the tolerance counts a tied draw as extreme, which is what stops the p "
          "being biased towards significance on tied cells")
    # An EXACT tie counts as extreme with or without the tolerance, which is worth
    # stating because it is the obvious wrong reason to keep the tolerance. What the
    # tolerance is for is the draw that reproduces the observed grouping and recomputes
    # the statistic through a different summation order, landing one unit in the last
    # place BELOW it. That draw is arithmetically the observed value and is counted as
    # not extreme without the tolerance.
    ulp_below = np.full(500, np.nextafter(1.0, 0.0))
    with_tol = permutation_p(1.0, ulp_below, side="greater")
    without = permutation_p(1.0, ulp_below, side="greater", abs_tol=0.0)
    check("a draw an ulp below the observed value counts, and does not without the "
          "tolerance",
          abs(with_tol["p"] - 1.0) < 1e-12 and without["p"] == without["p_floor"],
          f"p = {with_tol['p']:.4f} with the tolerance against "
          f"{without['p']:.6f} without it, a factor of "
          f"{with_tol['p'] / without['p']:.0f}, and the difference falls entirely on "
          f"the side of significance")

    # The same fixture moved to the magnitude one file in this tree actually works at:
    # a dollar delta of about 1.65 million. An ABSOLUTE 1e-12 there is 0.004 of one unit
    # in the last place, so it cannot change any comparison; the relative rule is the
    # same number of ulps at both magnitudes. This is the defect the first version of
    # this module shipped with, found by measuring the tree rather than by reading it.
    big = 1.65e6
    big_below = np.full(500, np.nextafter(big, 0.0))
    rel = permutation_p(big, big_below, side="greater")
    absolute = permutation_p(big, big_below, side="greater", abs_tol=1e-12)
    check("the slack scales with the statistic, where an absolute 1e-12 is a no-op",
          abs(rel["p"] - 1.0) < 1e-12 and absolute["p"] == absolute["p_floor"],
          f"at a magnitude of {big:.3g} the relative rule gives a slack of "
          f"{rel['tolerance_absolute']:.3e} ({rel['tolerance_absolute'] / np.spacing(big):.0f} ulp) "
          f"and p = {rel['p']:.4f}; an absolute 1e-12 is "
          f"{1e-12 / np.spacing(big):.4f} ulp and gives {absolute['p']:.6f}")

    print("-- 2. NON-EMPTINESS: a null effect is not called significant --")
    null_ps = []
    for trial in range(12):
        g = rng("selftest_null_arm", trial)
        y = g.normal(size=600)
        labels = (g.random(600) < 0.5).astype(int)
        res = permutation_test(
            group_gap(y, labels),
            lambda gen, y=y, labels=labels: group_gap(y, shuffled(labels, gen)),
            n_draws=400, cell=("selftest_null", trial), side="greater")
        null_ps.append(res["p"])
    n_small = sum(1 for p in null_ps if p < 0.05)
    check("on 12 fixtures with no effect at all, at most one p falls under 0.05",
          n_small <= 1,
          f"{n_small} of 12; median p = {float(np.median(null_ps)):.3f}, and a "
          f"procedure that answered 'significant' here would answer it on anything")

    print("-- 3. NON-EMPTINESS: a strong effect IS called significant --")
    strong_ps = []
    for trial in range(6):
        g = rng("selftest_signal_arm", trial)
        labels = (g.random(600) < 0.5).astype(int)
        y = g.normal(size=600) + 1.5 * labels          # a gap of 1.5 sd
        res = permutation_test(
            group_gap(y, labels),
            lambda gen, y=y, labels=labels: group_gap(y, shuffled(labels, gen)),
            n_draws=400, cell=("selftest_signal", trial), side="greater")
        strong_ps.append(res["p"])
    check("every one of 6 fixtures with a 1.5 sd gap reports the floor",
          all(abs(p - 1.0 / 401.0) < 1e-12 for p in strong_ps),
          f"p = {strong_ps[0]:.6f} on each, against {float(np.median(null_ps)):.3f} "
          f"on the null arm")

    print("-- 4. REPRODUCIBILITY: one cell repeats, two cells differ --")
    g = rng("selftest_repro_fixture", 0)
    y = g.normal(size=400)
    labels = (g.random(400) < 0.5).astype(int)
    obs = group_gap(y, labels)

    def run(cell):
        return permutation_test(
            obs, lambda gen: group_gap(y, shuffled(labels, gen)),
            n_draws=300, cell=cell, side="greater")

    a, b, c = run(("repro", "BTC")), run(("repro", "BTC")), run(("repro", "ETH"))
    check("the same cell twice gives the same p and the same null",
          a["p"] == b["p"] and a["null_mean"] == b["null_mean"],
          f"p = {a['p']:.6f} twice, null mean {a['null_mean']:.8f} twice")
    check("a different cell gives a different null",
          a["null_mean"] != c["null_mean"],
          f"null mean {a['null_mean']:.6f} against {c['null_mean']:.6f}")
    # The ambiguity that used to let rng("AB") and rng(65, 66) share a stream is closed
    # in settings.py, by refusing a cell that names nothing. Asserted here rather than
    # assumed, because this module hands its cell straight through: if the refusal were
    # ever relaxed, two differently-named cells would quietly share a null again and
    # every p in this module would inherit that.
    refused = False
    try:
        rng(65, 66)
    except ValueError:
        refused = True
    check("a cell that names nothing is refused at the source, not re-encoded here",
          refused and np.array_equal(rng("demo", 1).random(3),
                                     settings.rng("demo", 1).random(3)),
          "and a named cell draws the same stream through this module as through "
          "settings.rng directly, so routing a script through here moves no number")

    print("-- 5. THE REAL DIFFERENCE: what the shuffle holds fixed --")
    # A fixture where the whole effect lives in the stratum. Wallet identity carries
    # nothing the size bucket does not already carry, so the honest answer is "not
    # significant" and only the within-stratum null gives it.
    g = rng("selftest_strata_fixture", 0)
    stratum = np.repeat(np.arange(10), 60)
    y = stratum * 1.0 + g.normal(size=600) * 0.25
    labels = (stratum >= 5).astype(int)            # the label IS the stratum, coarsened
    obs = group_gap(y, labels)
    whole = permutation_test(
        obs, lambda gen: group_gap(y, shuffled(labels, gen)),
        n_draws=400, cell=("strata_demo", "whole"), side="greater")
    within = permutation_test(
        obs, lambda gen: group_gap(y, shuffled(labels, gen, strata=stratum)),
        n_draws=400, cell=("strata_demo", "within"), side="greater")
    check("the whole-sample null calls the stratum effect significant",
          whole["p_is_floored"], f"p = {whole['p']:.6f}")
    check("the within-stratum null does not, on the same data and statistic",
          within["p"] > 0.5,
          f"p = {within['p']:.4f} against {whole['p']:.6f}: the two nulls are two "
          f"questions, which is why side and strata are parameters and not a house style")
    drawn = shuffled(labels, rng("strata_shape", 0), strata=stratum)
    per_stratum_same = all(
        int(labels[stratum == s].sum()) == int(drawn[stratum == s].sum())
        for s in range(10))
    check("a within-stratum draw preserves each stratum's label count",
          per_stratum_same,
          "which is what makes it a null about identity beyond the stratum")

    print("-- 6. THE INCIDENTAL DIFFERENCES, measured --")
    g = rng("selftest_nan_fixture", 0)
    null = g.normal(size=2000)
    null[g.random(2000) < 0.6] = np.nan            # 60% of the draws fail
    observed = 1.0
    dropped = permutation_p(observed, null, side="greater", n_requested=2000)
    substituted = permutation_p(observed, np.nan_to_num(null, nan=0.0),
                                side="greater", n_requested=2000)
    check("a failed draw is dropped and counted, not replaced by zero",
          dropped["n_draws_dropped"] > 0
          and dropped["p"] > substituted["p"],
          f"dropping gives p = {dropped['p']:.5f} on {dropped['n_draws_usable']} "
          f"usable draws; substituting zero gives {substituted['p']:.5f}, lower by "
          f"{(1 - substituted['p'] / dropped['p']) * 100:.0f}%, because the "
          f"substituted mass sits at the centre of the null")
    check("the denominator is the usable count, and both counts are recorded",
          abs(dropped["p_floor"] - 1.0 / (dropped["n_draws_usable"] + 1)) < 1e-15
          and dropped["n_draws_requested"] == 2000,
          f"floor 1/{dropped['n_draws_usable'] + 1} = {dropped['p_floor']:.5f}, not "
          f"1/2001 = {1 / 2001:.5f}: a factor of "
          f"{dropped['p_floor'] * 2001:.1f} on the smallest expressible p")

    print("-- 7. one-sided against two-sided, on a statistic that can go either way --")
    g = rng("selftest_sides", 0)
    null = g.normal(size=1000)
    one = permutation_p(-1.7, null, side="greater")
    two = permutation_p(-1.7, null, side="two_sided")
    check("a large negative statistic is not significant one-sided and is two-sided",
          one["p"] > 0.9 and two["p"] < 0.2,
          f"greater: p = {one['p']:.3f}; two_sided: p = {two['p']:.3f}")

    print("-- 8. Benjamini-Hochberg: the same q as the tree, plus the threshold --")
    agree = True
    for trial in range(200):
        g = rng("selftest_bh", trial)
        size = int(g.integers(1, 40))
        p_list = list(np.round(g.random(size), 3))       # ties on purpose
        for i in range(size):
            if g.random() < 0.15:
                p_list[i] = None                         # untestable cells
        mine = benjamini_hochberg(p_list)["q"]
        loop = _legacy_bh_loop(p_list)
        vec = _legacy_bh_vectorised([np.nan if v is None else v for v in p_list])
        for i in range(size):
            a_ = mine[i]
            b_ = loop[i]
            c_ = None if np.isnan(vec[i]) else float(vec[i])
            if (a_ is None) != (b_ is None) or (a_ is None) != (c_ is None):
                agree = False
            elif a_ is not None and not (abs(a_ - b_) < 1e-12 and abs(a_ - c_) < 1e-12):
                agree = False
    check("both spellings in the tree give identical q on 200 random families",
          agree, "ties and untestable cells included; the consolidation moves no number")

    fam = benjamini_hochberg([0.001, 0.004, 0.01, 0.2, 0.9], alpha=0.05,
                             family="a self-test family of five")
    check("the correction returns the cutoff it applied, not only the verdict",
          fam["n_rejected"] == 3 and abs(fam["threshold"] - 3 * 0.05 / 5) < 1e-15
          and abs(fam["rank1_threshold"] - 0.01) < 1e-15,
          f"3 of 5 rejected at a cutoff of {fam['threshold']:.3f}; the rank-one bar "
          f"is {fam['rank1_threshold']:.3f}")
    quiet = benjamini_hochberg([0.2, 0.3, 0.4, 0.9], alpha=0.05)
    check("a family with nothing in it rejects nothing",
          quiet["n_rejected"] == 0 and quiet["threshold"] == 0.05 / 4,
          f"threshold reported as the rank-one bar {quiet['threshold']:.4f}")
    check("NaN cells are carried through and left out of the family size",
          benjamini_hochberg([0.01, None, 0.02])["family_size"] == 2)
    try:
        benjamini_hochberg([0.5, 1.4])
        check("a p outside [0, 1] is refused", False, "it was accepted")
    except ValueError:
        check("a p outside [0, 1] is refused", True,
              "the usual cause is a count divided by the budget rather than budget + 1")

    print("-- 9. the budget check, on the two budgets this tree actually runs --")
    small = budget_check(200, 48)
    declared = budget_check(settings.N_PERM, 48)
    check("a budget of 200 cannot clear the rank-one bar for a family of 48",
          not small["floor_can_clear_rank1"],
          f"floor {small['p_floor']:.5f} against a bar of "
          f"{small['rank1_threshold']:.5f}; six scripts run this budget today")
    check("the declared budget can",
          declared["floor_can_clear_rank1"],
          f"floor {declared['p_floor']:.6f} against {declared['rank1_threshold']:.5f} "
          f"at N_PERM = {settings.N_PERM}")

    print("-- 10. bootstrap: measured coverage, and a width that is not trivially wide --")
    # A 95% interval is NOT required to contain the truth on any one sample, so a check
    # that demands it on one fixture is a coin toss dressed as a test. The first attempt
    # here did exactly that and failed on a sample whose mean sat 2.2 standard errors off
    # -- the interval was right and the check was wrong. What is checkable is the RATE
    # over many fixtures, together with the width, because an interval that always
    # contained the truth by being enormous would pass a coverage test on its own.
    covered, widths, analytic = 0, [], []
    n_fix, n_rows = 40, 200
    for trial in range(n_fix):
        g = rng("selftest_coverage", trial)
        sample = g.normal(loc=0.0, scale=1.0, size=n_rows)
        ci = bootstrap_mean_ci(sample, cell=("coverage", trial), n_boot=600)
        covered += int(ci["lo"] <= 0.0 <= ci["hi"])
        widths.append(ci["hi"] - ci["lo"])
        analytic.append(2 * 1.96 * float(sample.std(ddof=1)) / math.sqrt(n_rows))
    ratio = float(np.median(widths)) / float(np.median(analytic))
    check(f"the interval covers the true mean on {covered} of {n_fix} fixtures",
          33 <= covered <= n_fix,
          f"nominal coverage is 95%, so 38 of 40 is the expectation and anything "
          f"below 33 would say the interval is too narrow")
    check("and it is not passing by being wide: its width matches the analytic one",
          0.85 <= ratio <= 1.15,
          f"median bootstrap width is {ratio:.3f} times 2 * 1.96 * se, so coverage is "
          f"bought by calibration and not by size")
    shifted = [bootstrap_mean_ci(
        rng("selftest_coverage", trial).normal(loc=0.0, scale=1.0, size=n_rows) + 1.0,
        cell=("shifted", trial), n_boot=600) for trial in range(n_fix)]
    check("a mean a full standard deviation from zero excludes zero on every fixture",
          all(b["excludes_zero"] for b in shifted),
          f"{n_fix} of {n_fix}, against {n_fix - covered} of {n_fix} for the "
          f"unshifted samples: the interval answers differently to the two cases")

    values = rng("selftest_boot_fixture", 0).normal(loc=3.0, scale=1.0, size=500)
    ci = bootstrap_mean_ci(values, cell=("selftest_boot", "mean3"), n_boot=800)
    again = bootstrap_mean_ci(values, cell=("selftest_boot", "mean3"), n_boot=800)
    other = bootstrap_mean_ci(values, cell=("selftest_boot", "other_cell"), n_boot=800)
    check("the interval reproduces on its cell and differs on another",
          (ci["lo"], ci["hi"]) == (again["lo"], again["hi"])
          and (ci["lo"], ci["hi"]) != (other["lo"], other["hi"]),
          f"same cell [{again['lo']:.6f}, {again['hi']:.6f}]; other cell "
          f"[{other['lo']:.6f}, {other['hi']:.6f}]")
    check("the interval states its method and the resolution of its endpoint",
          ci["method"] == "percentile" and ci["draws_per_tail"] == 800 * 0.025,
          f"{ci['draws_per_tail']:.0f} draws decide each endpoint at n_boot = 800; "
          f"the declared budget {settings.N_BOOT} gives {settings.N_BOOT * 0.025:.0f}")
    weighted = bootstrap_mean_ci(np.array([1.0, 2.0, 3.0, 100.0]),
                                 weights=np.array([1.0, 1.0, 1.0, 1e-9]),
                                 cell=("selftest_boot", "weighted"), n_boot=400)
    check("a weighted mean is bootstrapped through the same procedure",
          weighted["weighted"] and weighted["point"] < 4.0,
          f"point {weighted['point']:.4f}: the 100 carries a weight of 1e-9")

    print("-- 11. refusals --")
    for name, call in (
        ("a cell with no components", lambda: rng()),
        ("a float in the cell identity", lambda: rng("x", 0.5)),
        ("an empty string in the cell identity", lambda: rng("x", "")),
        ("an unknown side", lambda: permutation_p(1.0, [0.0], side="bigger")),
        ("a budget below one draw",
         lambda: permutation_test(1.0, lambda gen: 0.0, n_draws=0, cell=("x",))),
        ("mismatched strata",
         lambda: shuffled(np.zeros(5), rng("x", 1), strata=np.zeros(4))),
    ):
        try:
            call()
            check(f"{name} is refused", False, "it was accepted")
        except (ValueError, TypeError):
            check(f"{name} is refused", True)

    empty = permutation_p(1.0, [np.nan, np.nan], side="greater")
    check("a cell with no usable draw reports no test rather than a large p",
          empty["p"] is None and empty["n_draws_usable"] == 0,
          "a p of 1.0 would read as 'tested and found nothing'")

    print("-" * 78)
    print(f"  VERDICT: {'PASS' if not failures else 'FAIL ' + ', '.join(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    print("=" * 78)
    print("  stats.py self-test -- the permutation, the bootstrap and the correction")
    print("=" * 78)
    sys.exit(_self_test())
