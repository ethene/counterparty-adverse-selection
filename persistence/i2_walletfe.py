"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-19
References:
  - Hyperliquid node-data S3 archive; Zenodo 18184441 (Albers et al. 2026).
  - Kline, P., Saggio, R., Solvsten, M. (2020). "Leave-out estimation of variance
    components." Econometrica 88(5), 1859-1898. (KSS leave-out bias correction --
    here implemented in its split-half / split-sample spirit, kept deliberately
    simple and exactly unbiased rather than the full leave-one-out machinery.)
  - Spearman-Brown reliability; classical errors-in-variables disattenuation
    (the same noise-cancellation logic used in ks2_persistence_10day.py).
"""

# ---------------------------------------------------------------------------
# OBJECT I2 -- ONE-WAY COUNTERPARTY (taker_id) FIXED-EFFECTS VARIANCE DECOMP.
#
# Question: of the cross-sectional variance in per-trade 10s markout, what share
# is a STABLE per-wallet (idiosyncratic-to-the-counterparty) component vs
# within-wallet noise? Write the random-effects form
#
#       y_ij = mu + alpha_i + eps_ij                                      (1)
#
# for trade j of wallet i, where alpha_i is the stable per-wallet level and
# eps_ij is within-wallet noise. The object of interest is the idiosyncratic
# (signal) share Var(alpha) / Var(y).
#
# THE BIAS. The naive between-wallet estimator -- the variance of the per-wallet
# means ybar_i across wallets -- is UPWARD-biased for Var(alpha):
#
#       Var(ybar_i) = Var(alpha) + E[ sigma_eps^2 / n_i ]                 (2)
#
# The second term is pure sampling noise and is large when wallets have few
# trades. So the naive idiosyncratic share OVERSTATES how much of the spread is
# a stable per-wallet effect. We report it, and we STATE it is upward-biased.
#
# THE CORRECTION (split-half, KSS-style spirit, exact and simple). Randomly
# split each wallet's trades into two disjoint halves A and B (fixed seed).
# Their half-means are
#
#       ybarA_i = mu + alpha_i + epsbarA_i ,  ybarB_i = mu + alpha_i + epsbarB_i
#
# The noise terms epsbarA_i and epsbarB_i are independent (disjoint trades), so
#
#       Cov( ybarA_i , ybarB_i )  =  Var(alpha)                           (3)
#
# the sampling noise cancels in the cross-wallet COVARIANCE. That covariance is
# therefore an (essentially) unbiased estimate of the true signal variance. The
# bias-corrected idiosyncratic share is Cov(A,B) / Var(y_total). We average the
# estimator over a few independent random splits (seeds) and quote one.
#
# PLACEBO. Shuffling the taker_id labels destroys the real per-wallet structure
# while preserving the marginal distribution of y. Under shuffled labels the
# corrected signal covariance should collapse to ~0. We run settings.N_PERM shuffles
# and report a permutation p-value with the floor 1/(N_PERM+1) stated beside it, so
# the per-wallet component is shown to be real, not a sampling artefact of the
# grouping itself.
#
# WHAT THE BUDGET CAN AND CANNOT SAY, and why it is not a runtime choice. A budget
# of N draws cannot express a p below 1/(N+1), so the budget sets a FLOOR under
# every p this file reports. Every p carries a *_is_floor flag from
# settings.p_is_floored: True means "no draw beat the observed value", which is a
# statement about the BUDGET, not a measurement of how small the p is. All eighteen
# placebo p-values here sit on that floor, and all eighteen sat on the lower budget's
# floor before it: at both 200 and 2000 draws not one shuffle reached the observed
# covariance, and observed_outside_null is True in all nine cells. Raising the budget
# tenfold therefore bought a smaller floor and no measurement -- which is the point,
# because the floor is what the correction reads.
#
# That is exactly why the floor's VALUE decides the verdict. A Benjamini-Hochberg
# family of 48 cells compares its smallest rank against 0.05/48 = 0.00104. The
# 200-draw floor of 0.00498 sits ABOVE that threshold, so at 200 draws no p from
# this file could clear the correction at any rank, however strong the effect --
# and it would have failed silently, by reporting a floored p that the correction
# then rejected. settings.N_PERM is computed from the level and the family size for
# that reason (settings.min_perm_draws), and taking it from there rather than
# typing a number is what makes the floor a consequence of the correction instead
# of a consequence of how long the script was allowed to run.
#
# CRITICAL HONESTY -- INTERPRETATION IS HELD. The markout reference price is a
# TRADE-PRINT VWAP, not a book mid. A non-zero, stable per-wallet markout
# therefore mixes (a) genuine adverse selection against the maker with (b)
# bid-ask bounce and the maker's earned half-spread, because each fill's signed
# print-to-print move embeds the spread the taker crossed. This script ESTIMATES
# the variance decomposition; it does NOT yet claim the per-wallet variance is
# all adverse selection. That decomposition of MAGNITUDE into adverse-selection
# vs spread is HELD pending the I4 book-mid check. What I2 does establish is the
# STRUCTURAL fact -- a stable, label-real per-wallet component exists -- which is
# logically prior to (and unaffected by) the spread-vs-AS attribution of its size.
#
# numpy-only, seeded from settings.MASTER_SEED. No plotting. DO NOT run as part of
# writing.
# ---------------------------------------------------------------------------

import os
import sys

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

# ---------------------------------------------------------------------------
# Paths / config
# ---------------------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
# Located through panel_io, so the one module that knows where the panels live answers
# here too. The environment list is EMPTY on purpose: this file has never honoured a
# data-root override, and adopting panel_io's five names would let a machine that
# happens to export one of them feed this script a different panel. With no name
# honoured the answer is the directory the code sits in, which is what it was.
# The file name stays a literal inside the join, because build.py derives this script's
# input edge by folding the argument of np.load to its last literal component and a
# call there would fold to nothing.
DATA_ROOT_ENV = ()
NPZ_PATH = os.path.join(P.data_root(env_names=DATA_ROOT_ENV),
                        "quickwin_markouts.npz")
OUT_PATH = os.path.join(HERE, "i2_walletfe_results.json")

# int8 code -> symbol. The map is a property of the FILE, not of the project
# (quickwin_markouts.npz carries {0, 1}; panel_markouts.npz carries {0, 1, 2}), so it
# is asked for by artifact name and never written out here.
COIN_NAME = H.coin_labels("quickwin")

SEED = H.MASTER_SEED                     # the one seed, taken from the declaration. Its
                                          # value is arbitrary -- no integer is more
                                          # correct -- so what is defended is that there is
                                          # exactly ONE across the tree, which is what lets
                                          # a p-value differing between two scripts differ
                                          # because the STATISTIC differs. The previous
                                          # literal 20260619 sat one apart from the
                                          # declared 20260620 and bought nothing for it.
                                          # This seed draws the A/B split schedule, so
                                          # moving it moves every corrected share while
                                          # leaving the naive decomposition, the coverage
                                          # and every p untouched -- those do not read the
                                          # seed. What moves is split noise, not the
                                          # estimate. The file reports the spread ACROSS
                                          # THE FIVE SPLITS of one schedule
                                          # (corrected_signal_var_seed_std); that is a
                                          # narrower quantity than the spread across
                                          # schedules, and no script here measures the
                                          # wider one
K_VALUES = H.wallet_fill_floor("i2_walletfe", "sweep")
                                          # min trades per wallet for inclusion, read
                                          # from the declaration, which holds the
                                          # (30, 50, 100) the published run used. The
                                          # ladder is still wider and looser than
                                          # settings.RANK_FLOOR_FILLS (50) -- 30 sits
                                          # below every rung of the declared
                                          # sensitivity ladder -- so it remains an
                                          # override against that constant, which the
                                          # fingerprint states in words
N_SPLIT_SEEDS = 5                        # independent random A/B splits to average over
N_PERM = H.N_PERM                        # label-permutation shuffles for the placebo,
                                          # taken from the declaration rather than sized
                                          # by runtime. Each shuffle is an O(n) relabel of
                                          # ~2.5M trades over 18 (slice x K x full/whale)
                                          # calls, so the budget is what this script costs;
                                          # it is set anyway by the requirement that the
                                          # floor 1/(N_PERM+1) clear a corrected threshold
                                          # (see the header), because a cheaper budget
                                          # cannot produce a correctable p at any effect
                                          # size. The floor is reported beside every p.
N_DROP_WHALES = H.WHALE_DROP_K           # whale-robustness: drop top-N wallets by trade
                                          # count. The COUNT is the declared one; the
                                          # criterion (trade count) is this file's, and
                                          # settings.whale_drop names both in the key

# Honesty note carried into the JSON and echoed in the printed table.
INTERPRETATION_HELD = (
    "The markout reference is a TRADE-PRINT VWAP, not a book mid, so the MAGNITUDE "
    "of the per-wallet fixed effect is entangled with bid-ask bounce and the "
    "maker's earned spread. This decomposition is a measurement of the variance "
    "structure; the adverse-selection INTERPRETATION of its magnitude is HELD "
    "pending the I4 book-mid check. I2 establishes only that a stable, label-real "
    "per-wallet component EXISTS, not that its size is all adverse selection."
)


# ---------------------------------------------------------------------------
# Grouping helpers
# ---------------------------------------------------------------------------
def compact_labels(taker_id):
    """Map raw wallet ids to 0..G-1 dense labels.

    Returns (uniq, inv, counts): the unique ids, the per-trade group label, and
    the number of trades per group. All downstream math uses `inv`/`counts`.
    """
    uniq, inv = np.unique(taker_id, return_inverse=True)
    counts = np.bincount(inv, minlength=uniq.size)
    return uniq, inv.astype(np.int64), counts


def group_means(inv, y, n_groups):
    """Per-group mean of y over labels `inv` (groups assumed all non-empty)."""
    s = np.bincount(inv, weights=y, minlength=n_groups)
    c = np.bincount(inv, minlength=n_groups).astype(np.float64)
    return s / c


# ---------------------------------------------------------------------------
# (1) Naive (upward-biased) decomposition on the eligible wallet set
# ---------------------------------------------------------------------------
def naive_decomposition(inv_e, y_e, n_groups_e):
    """Raw between/within decomposition restricted to eligible wallets.

    inv_e      : dense 0..n_groups_e-1 labels for the retained trades.
    y_e        : per-trade markout for the retained trades.
    n_groups_e : number of eligible wallets.

    total_var      = Var(y) over the retained trades (population variance).
    between_var    = trade-count-weighted variance of the per-wallet means about
                     the grand mean -- this is the between component of the ANOVA
                     identity total = between + within, and it is the NAIVE
                     (upward-biased) estimate of Var(alpha).
    within_var     = mean within-wallet variance (the residual of the identity).
    naive_idio_share = between_var / total_var (STATED upward-biased).

    The identity used is the standard weighted one:
        sum_ij (y_ij - ybar)^2 = sum_i n_i (ybar_i - ybar)^2
                                  + sum_ij (y_ij - ybar_i)^2
    dividing by N gives total_var = between_var + within_var.
    """
    n_trades = y_e.size
    grand_mean = float(y_e.mean())
    total_var = float(((y_e - grand_mean) ** 2).mean())

    counts = np.bincount(inv_e, minlength=n_groups_e).astype(np.float64)
    means = group_means(inv_e, y_e, n_groups_e)
    between_ss = float(np.sum(counts * (means - grand_mean) ** 2))
    between_var = between_ss / n_trades

    # within = total - between (exact ANOVA identity); compute directly too as a check.
    resid = y_e - means[inv_e]
    within_var = float((resid ** 2).mean())

    naive_share = between_var / total_var if total_var > 0 else float("nan")
    return {
        "n_trades": int(n_trades),
        "n_wallets": int(n_groups_e),
        "grand_mean_bps": grand_mean,
        "total_var": total_var,
        "naive_between_var": between_var,
        "within_var": within_var,
        "between_plus_within": between_var + within_var,   # == total_var (identity check)
        "naive_idiosyncratic_share": naive_share,
        "bias_note": ("naive_between_var = Var(alpha) + E[sigma_eps^2 / n_i] is "
                      "UPWARD-biased for the true signal variance; corrected "
                      "estimate is in split_half_corrected"),
    }


# ---------------------------------------------------------------------------
# (2) Split-half bias-corrected signal variance
# ---------------------------------------------------------------------------
def _assign_halves(inv_e, counts_e, n_groups_e, rng):
    """Randomly split each wallet's trades into two disjoint halves A / B.

    Returns a boolean mask `is_A` over the retained trades drawn by a single
    vectorized per-trade coin flip (fixed seed via `rng`). Each trade lands in A
    or B independently, so the two halves use disjoint trades and the within-half
    noise terms epsbarA_i, epsbarB_i remain independent -- which is the ONLY
    property the bias correction (equation (3)) relies on. The wallets that fail
    to populate both halves are dropped downstream by the `(cA > 0) & (cB > 0)`
    guard, so the estimator is unchanged in spirit; this just replaces the old
    O(n log n) sort-and-floor split with an O(n) mask. With K >= 30 trades per
    wallet the chance a wallet lands entirely in one half is ~2 * 2^-30, i.e.
    effectively zero, so the connected set is identical in practice.
    """
    return rng.random(inv_e.size) < 0.5


def split_half_corrected(inv_e, y_e, counts_e, n_groups_e, total_var, seeds):
    """Bias-corrected signal variance via the cross-wallet half-mean covariance.

    For each seed: split trades A/B, form per-wallet half-means meanA_i, meanB_i,
    and take the SAMPLE COVARIANCE of (meanA, meanB) across wallets. Because the
    two halves use disjoint trades, the noise cancels and this covariance is an
    unbiased estimate of Var(alpha) (equation (3) in the header). Average over
    `seeds` and quote the mean.

    Wallets are weighted EQUALLY in the cross-wallet covariance (one point per
    wallet), which matches the random-effects target Var(alpha) over the wallet
    population. total_var (the denominator) is the per-trade variance from the
    naive block, so the corrected share is comparable to the naive share.
    """
    cov_estimates = []
    var_A_estimates = []
    var_B_estimates = []
    for s in seeds:
        rng = np.random.default_rng(s)
        is_A = _assign_halves(inv_e, counts_e, n_groups_e, rng)

        # per-wallet half means (every eligible wallet has >=1 trade in each half)
        cA = np.bincount(inv_e[is_A], minlength=n_groups_e).astype(np.float64)
        cB = np.bincount(inv_e[~is_A], minlength=n_groups_e).astype(np.float64)
        sA = np.bincount(inv_e[is_A], weights=y_e[is_A], minlength=n_groups_e)
        sB = np.bincount(inv_e[~is_A], weights=y_e[~is_A], minlength=n_groups_e)
        ok = (cA > 0) & (cB > 0)
        if ok.sum() < 3:
            continue
        meanA = sA[ok] / cA[ok]
        meanB = sB[ok] / cB[ok]
        # sample covariance across wallets (ddof=1), equal weight per wallet
        cov_AB = float(np.cov(meanA, meanB, ddof=1)[0, 1])
        cov_estimates.append(cov_AB)
        var_A_estimates.append(float(np.var(meanA, ddof=1)))
        var_B_estimates.append(float(np.var(meanB, ddof=1)))

    if not cov_estimates:
        return {
            "corrected_signal_var": float("nan"),
            "corrected_idiosyncratic_share": float("nan"),
            "per_seed_signal_var": [],
            "n_seeds_used": 0,
        }

    cov_arr = np.asarray(cov_estimates, dtype=np.float64)
    signal_var = float(cov_arr.mean())
    # report a single quoted estimate (the seed-average) plus the spread for honesty
    corrected_share = signal_var / total_var if total_var > 0 else float("nan")
    return {
        "corrected_signal_var": signal_var,                       # quoted estimate
        "corrected_signal_var_seed_std": float(cov_arr.std(ddof=1)) if cov_arr.size > 1 else 0.0,
        "corrected_idiosyncratic_share": corrected_share,
        "per_seed_signal_var": [float(c) for c in cov_arr],
        "mean_halfmean_var_A": float(np.mean(var_A_estimates)),   # for reference (still noisy)
        "mean_halfmean_var_B": float(np.mean(var_B_estimates)),
        "n_seeds_used": int(cov_arr.size),
        "note": ("corrected_signal_var = mean over seeds of Cov(halfA_mean, "
                 "halfB_mean) across wallets; the half-mean variances themselves "
                 "are still noise-inflated and are shown only for reference"),
    }


# ---------------------------------------------------------------------------
# (3) Coverage of the connected / eligible set
# ---------------------------------------------------------------------------
def coverage_block(counts, eligible_mask, total_trades_all):
    """Wallets retained, trades they cover, and the median trades/wallet at K."""
    elig_counts = counts[eligible_mask]
    if elig_counts.size == 0:
        return {"n_wallets_retained": 0, "trades_covered": 0,
                "trades_covered_frac": 0.0, "median_trades_per_wallet": float("nan")}
    trades_covered = int(elig_counts.sum())
    return {
        "n_wallets_retained": int(eligible_mask.sum()),
        "trades_covered": trades_covered,
        "trades_covered_frac": (float(trades_covered / total_trades_all)
                                if total_trades_all > 0 else float("nan")),
        "median_trades_per_wallet": float(np.median(elig_counts)),
        "min_trades_per_wallet": int(elig_counts.min()),
        "max_trades_per_wallet": int(elig_counts.max()),
    }


# ---------------------------------------------------------------------------
# (4) Label-permutation placebo
# ---------------------------------------------------------------------------
def _cov_corrected(labels, n_groups, wA, wB, yA, yB):
    """Corrected signal covariance Cov(meanA, meanB) across wallets, vectorized.

    `labels` is the dense per-trade wallet label vector. wA/wB are the A/B count
    weights (1 in the half, 0 otherwise) and yA/yB are y masked into A/B. Four
    weighted bincounts give per-wallet half sums and counts in a single O(n) pass
    each, with no boolean-mask gathers. This is identical math to forming
    meanA_i = sum_A y / count_A and meanB_i likewise and taking their sample
    covariance over wallets present in both halves -- just written as weighted
    bincounts so it is fast enough for the permutation loop.
    """
    cA = np.bincount(labels, weights=wA, minlength=n_groups)
    cB = np.bincount(labels, weights=wB, minlength=n_groups)
    sA = np.bincount(labels, weights=yA, minlength=n_groups)
    sB = np.bincount(labels, weights=yB, minlength=n_groups)
    ok = (cA > 0) & (cB > 0)
    if int(ok.sum()) < 3:
        return float("nan")
    meanA = sA[ok] / cA[ok]
    meanB = sB[ok] / cB[ok]
    return float(np.cov(meanA, meanB, ddof=1)[0, 1])


def _signal_var_one_split(inv_e, y_e, counts_e, n_groups_e, rng):
    """Single-split corrected signal covariance, used inside the permutation loop.

    Uses one A/B split (cheap) -- under the null the expectation is ~0 regardless
    of how many splits are averaged, so one split per shuffle is sufficient to
    build the null distribution. The split is a vectorized per-trade coin flip
    (same object as _assign_halves), then the covariance is formed by weighted
    bincounts via _cov_corrected.
    """
    is_A = _assign_halves(inv_e, counts_e, n_groups_e, rng)
    wA = is_A.astype(np.float64)
    wB = 1.0 - wA
    return _cov_corrected(inv_e, n_groups_e, wA, wB, y_e * wA, y_e * wB)


def permutation_placebo(y_all, labels_all, counts_full, K, observed_signal_var,
                        n_perm, seed):
    """Shuffle wallet labels across the eligible trades and recompute the
    corrected signal covariance to build a null.

    The shuffle reassigns each trade to a wallet by permuting the per-trade label
    vector (keeping the wallet-size MULTISET identical: counts are preserved, only
    membership is randomized). The inputs `labels_all`/`counts_full` are ALREADY
    the dense eligible labels / counts of the connected set: every wallet here has
    count >= K, and a relabel-permutation cannot change any wallet's count, so the
    eligible set is invariant across permutations and no per-permutation
    re-densification is needed. Each permutation is therefore O(n): permute the
    dense label vector once, then form the corrected covariance with bincount.
    A one-sided p-value (observed >= null) is returned with the 1/(n_perm+1) floor
    convention from ks2_persistence_10day.py.

    Because permuting which TRADE carries which label leaves the per-wallet sizes
    unchanged but breaks any real y<->wallet association, the null covariance is
    centred on 0; the observed estimate sitting in the right tail certifies the
    per-wallet component is real.
    """
    rng = np.random.default_rng(seed)
    null_vals = np.empty(n_perm, dtype=np.float64)
    n_all = labels_all.size
    n_groups_full = counts_full.size
    if n_groups_full < 3:
        return {"p_value": float("nan"), "n_perm_valid": 0,
                "null_mean": float("nan"), "null_std": float("nan"),
                "null_p95": float("nan"), "null_max": float("nan")}

    # Fixed A/B half-assignment + weight vectors, drawn ONCE. The placebo varies
    # only the wallet labels (the y<->wallet association); the half-split is held
    # fixed across shuffles, which is sufficient because under the null the
    # expected covariance is 0 for ANY fixed disjoint split. Precomputing wA/wB/
    # yA/yB outside the loop turns each permutation into four weighted bincounts.
    is_A = rng.random(n_all) < 0.5
    wA = is_A.astype(np.float64)
    wB = 1.0 - wA
    yA = y_all * wA
    yB = y_all * wB

    # Reused label buffer: shuffle in place each iteration (no per-perm allocation).
    buf = np.array(labels_all, dtype=np.int64, copy=True)
    n_valid = 0
    for p in range(n_perm):
        # permute which trade carries which (dense) eligible label: O(n), counts preserved
        rng.shuffle(buf)
        v = _cov_corrected(buf, n_groups_full, wA, wB, yA, yB)
        null_vals[p] = v
        if v == v:
            n_valid += 1

    finite_null = null_vals[np.isfinite(null_vals)]

    # THE COUNTING IS stats.permutation_p AND THE NUMBER DOES NOT MOVE. The three
    # things that could have moved it are each the same on both sides, and each is a
    # real disagreement somewhere else in this tree, which is why they are named:
    #
    #   the side is one-sided at `null >= observed`, and stays one-sided;
    #   the slack is ZERO -- this test has never subtracted a tolerance before
    #     comparing, so it is passed as an explicit abs_tol of 0.0 rather than taking
    #     the module's default, which is relative to the scale of the comparison and
    #     would count a draw a whisker below the observed value as reaching it;
    #   the denominator is the count of draws that came back FINITE, which is what
    #     this function already divided by. _cov_corrected returns no number when
    #     fewer than three wallets land in both halves of a shuffle, and such a draw
    #     is dropped rather than replaced -- dividing by the requested budget instead
    #     would claim a resolution the run did not have.
    #
    # Nothing here is ±inf: _cov_corrected returns np.cov of finite half-means over at
    # least three wallets, so the module's finite filter and this file's select the
    # same draws.
    block = stats.permutation_p(
        observed_signal_var, null_vals, side="greater", abs_tol=0.0,
        n_requested=int(n_perm), cell=("i2_walletfe_label_permutation", int(K)))
    if block["p"] is None:
        return {"p_value": float("nan"), "n_perm_valid": int(finite_null.size),
                "null_mean": float("nan"), "null_std": float("nan"),
                "null_p95": float("nan"), "null_max": float("nan"),
                "permutation_procedure": block}
    # The floor is set by the draws that actually returned a finite covariance, which
    # is what the reported p is divided by, so the flag is computed on that count and
    # not on the requested n_perm. Both counts reach the artifact through the block.
    return {
        "p_value": float(block["p"]),
        "p_value_floor": block["p_floor"],
        "p_value_is_floor": bool(block["p_is_floored"]),
        "p_value_floor_note": (
            "p_value_is_floor True means no permutation beat the observed value, so the "
            "number is the budget's smallest expressible p and not a measurement of how "
            "small the p is"),
        "n_perm_valid": int(block["n_draws_usable"]),
        "null_mean": float(block["null_mean"]),
        "null_std": float(block["null_sd"]),
        "null_p95": float(block["null_p95"]),
        "null_max": float(finite_null.max()),
        "observed_outside_null": bool(observed_signal_var > block["null_p95"]),
        "permutation_procedure": block,
    }


# ---------------------------------------------------------------------------
# Slice driver: full I2 pipeline for one (taker_id, y) slice at one K
# ---------------------------------------------------------------------------
def run_slice_at_K(taker_id, y, K, split_seeds, perm_seed, n_perm,
                   drop_whales=False, n_drop=N_DROP_WHALES):
    """Run the naive + corrected decomposition, coverage, and placebo at one K.

    If drop_whales is True, the top `n_drop` wallets BY TRADE COUNT are removed
    before any decomposition (whale-robustness). Returns a dict; an empty/too-thin
    eligible set yields a populated dict with NaNs rather than raising.
    """
    total_trades_all = int(taker_id.size)
    uniq, inv, counts = compact_labels(taker_id)

    if drop_whales and uniq.size > n_drop:
        # rank wallets by trade count, drop the top n_drop, then re-grade everything
        whales = np.argsort(counts)[::-1][:n_drop]
        whale_mask = np.zeros(uniq.size, dtype=bool)
        whale_mask[whales] = True
        keep_trade = ~whale_mask[inv]
        taker_id = taker_id[keep_trade]
        # rebuild grouping on the survivors
        uniq, inv, counts = compact_labels(taker_id)
        y = y[keep_trade]

    eligible = counts >= K
    cov = coverage_block(counts, eligible, total_trades_all)

    out = {"K": int(K), "coverage": cov}

    if eligible.sum() < 3:
        out["naive"] = {"note": f"fewer than 3 wallets with >= {K} trades"}
        out["split_half_corrected"] = {"corrected_signal_var": float("nan"),
                                       "corrected_idiosyncratic_share": float("nan")}
        out["placebo"] = {"p_value": float("nan")}
        return out

    # restrict to eligible wallets and DENSIFY labels to 0..G_e-1
    keep = eligible[inv]
    y_e = y[keep].astype(np.float64)
    lab_e = inv[keep]
    uniq_e, inv_e = np.unique(lab_e, return_inverse=True)
    inv_e = inv_e.astype(np.int64)
    n_groups_e = uniq_e.size
    counts_e = np.bincount(inv_e, minlength=n_groups_e)

    naive = naive_decomposition(inv_e, y_e, n_groups_e)
    corrected = split_half_corrected(inv_e, y_e, counts_e, n_groups_e,
                                     naive["total_var"], split_seeds)

    # placebo: shuffle labels over the FULL (eligible-trade) pool. We permute the
    # eligible-wallet labels of the retained trades; counts_e is the size multiset.
    placebo = permutation_placebo(
        y_e, inv_e, counts_e, K, corrected["corrected_signal_var"],
        n_perm=n_perm, seed=perm_seed)

    out["naive"] = naive
    out["split_half_corrected"] = corrected
    out["placebo"] = placebo
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    t0 = artifact.start_clock()
    # panel_io owns both refusals. The missing-FILE message names the producer that
    # writes the panel, which a fresh clone does not carry, and it names no directory,
    # so the account name of whoever runs this cannot reach a pasted log. The
    # missing-COLUMN message names what was asked and what the file holds.
    P.require_present("print", NPZ_PATH, env_names=DATA_ROOT_ENV)

    data = np.load(NPZ_PATH)
    P.require_columns(data, "print", "taker_id", "coin", "day",
                      P.score_col("print"))
    taker_id = data["taker_id"].astype(np.int64)
    coin = data["coin"].astype(np.int8)
    # The scoring column is asked for by ROLE. P.score returns it as float64 at the
    # declared window through the panel's own lens, which is the trade print here, so
    # the window this file scores on can no longer be fixed by a line that does not
    # mention a window. The name and the dtype are what this file already read.
    mo_score = P.score(data, "print")            # signed taker markout, bps
    # Read only to state the window in the artifact's scope; it enters no computation.
    # It is filtered with everything else so the window describes the rows that
    # actually reached the decomposition.
    day = data["day"].astype(np.int64)

    # Keep only trades with a finite 10s markout; everything else cannot enter a
    # variance. (No other filtering -- I2 is a decomposition of the markout that
    # exists, not a re-selection of the sample.)
    valid = np.isfinite(mo_score)
    day = day[valid]
    taker_id = taker_id[valid]
    coin = coin[valid]
    mo_score = mo_score[valid]

    # deterministic seed schedule derived from the master seed -------------------
    base = np.random.default_rng(SEED)
    split_seeds = [int(s) for s in base.integers(0, 2**31 - 1, size=N_SPLIT_SEEDS)]
    # one permutation seed per (slice, K); drawn from the same master stream so the
    # whole run is reproducible from SEED alone.

    slices = {name: coin == code for code, name in COIN_NAME.items()}
    slices["pooled"] = np.ones(coin.size, bool)

    # What every number in this file was computed under. n_perm is passed even though
    # it now equals the declaration, because settings.fingerprint states a migrating
    # value only when the caller CONFIRMS what its run used; left out, it would go to
    # declared_not_confirmed and the artifact would stop asserting its own budget. The
    # note is BUILT from the values rather than typed: it went stale once already, and
    # a caption stating a setting the run did not use is the same defect as a field
    # name that does. artifact.write is the single place that stamps it.
    settings_used = dict(
        h=H.HEADLINE_HORIZON_S, lens="print",
        master_seed=SEED,
        n_perm=N_PERM,
        rank_floor_fills=list(K_VALUES),
        n_boot=None,
        whale_drop_criterion="fill_count",
        p_floor=H.p_floor(N_PERM),
        overrides_note=(
            (f"master_seed {SEED} not settings.MASTER_SEED {H.MASTER_SEED}; "
             if SEED != H.MASTER_SEED else
             f"master_seed {SEED} is settings.MASTER_SEED unchanged; ")
            + (f"n_perm {N_PERM} is the declared budget, so every p is floored at "
               f"{H.p_floor(N_PERM):.6f} and a floored p clears a 48-cell "
               f"corrected threshold of {H.FDR_ALPHA / 48:.5f}; "
               if N_PERM == H.N_PERM else
               f"n_perm {N_PERM} not the declared {H.N_PERM}, so every p is "
               f"floored at {H.p_floor(N_PERM):.5f}; ")
            + f"rank_floor_fills {tuple(K_VALUES)} not the declared single "
              f"{H.RANK_FLOOR_FILLS}; no bootstrap is drawn here, so n_boot does "
              f"not apply; whales are dropped by FILL COUNT, which answers 'is "
              f"this a few hyperactive accounts' and not 'is this a volume "
              f"artifact'"),
            )

    results = {
        "_meta": {
            "object": ("I2 one-way counterparty (taker_id) fixed-effects variance "
                       f"decomposition of {H.headline_print_col()}"),
            "horizon_s": H.HEADLINE_HORIZON_S,
            "model": "y_ij = mu + alpha_i + eps_ij ; target = Var(alpha)/Var(y)",
            "estimator": ("naive between-wallet variance (upward-biased) plus a "
                          "split-half cross-wallet covariance bias correction "
                          "(KSS-style spirit): Cov(halfA_mean, halfB_mean) across "
                          "wallets is unbiased for Var(alpha) because half noise "
                          "is independent"),
            "master_seed": SEED,
            "split_seeds": split_seeds,
            "n_split_seeds": N_SPLIT_SEEDS,
            "n_perm": N_PERM,
            "K_values": list(K_VALUES),
            "n_drop_whales": N_DROP_WHALES,
            "n_trades_valid": int(taker_id.size),
            "interpretation_held": INTERPRETATION_HELD,
        }
    }

    for sname, smask in slices.items():
        tid = taker_id[smask]
        y = mo_score[smask]
        slice_block = {"n_trades": int(tid.size),
                       "n_wallets_total": int(np.unique(tid).size),
                       "by_K": {}}
        for K in K_VALUES:
            # per-(slice, K) permutation seed, deterministic from the master stream
            perm_seed = int(base.integers(0, 2**31 - 1))
            main_res = run_slice_at_K(
                tid, y, K, split_seeds, perm_seed, N_PERM,
                drop_whales=False)

            # whale-robustness: same K, top-10 wallets by trade count removed
            whale_seed = int(base.integers(0, 2**31 - 1))
            whale_res = run_slice_at_K(
                tid, y, K, split_seeds, whale_seed, N_PERM,
                drop_whales=True, n_drop=N_DROP_WHALES)

            # The whale arm drops the top wallets BY FILL COUNT. The old key name
            # "drop_top10_wallets" stated the count and hid the criterion, and dropping
            # the ten largest by count answers a different question from dropping the
            # ten largest by notional. settings.whale_drop names both in the key.
            whale_key = H.whale_drop("fill_count", N_DROP_WHALES)["key"]
            slice_block["by_K"][str(K)] = {
                "full": main_res,
                whale_key: {
                    "coverage": whale_res["coverage"],
                    "naive_idiosyncratic_share": whale_res["naive"].get(
                        "naive_idiosyncratic_share", float("nan")),
                    "corrected_idiosyncratic_share": whale_res[
                        "split_half_corrected"].get(
                        "corrected_idiosyncratic_share", float("nan")),
                    "corrected_signal_var": whale_res[
                        "split_half_corrected"].get(
                        "corrected_signal_var", float("nan")),
                    "placebo_p_value": whale_res["placebo"].get(
                        "p_value", float("nan")),
                    "placebo_p_value_floor": whale_res["placebo"].get(
                        "p_value_floor", float("nan")),
                    "placebo_p_value_is_floor": bool(
                        whale_res["placebo"].get("p_value_is_floor", False)),
                },
            }
        results[sname] = slice_block

    # What the numbers cover. The unit of analysis is the WALLET: rows are reduced to
    # per-wallet means and a wallet enters a cell at that cell's fill floor, so the
    # population names the rows read and the floors that admit a wallet.
    days = np.unique(day)
    scope = {
        "population": (f"{taker_id.size:,} rows of the trade-print panel with a finite "
                       "markout, decomposed per wallet; this is a decomposition of the "
                       "markout that exists rather than a re-selection of the sample, "
                       f"and the cells run over {list(K_VALUES)} fills"),
        "window": (f"{days.size} days present in the input, day-of-month "
                   f"{days.min()}-{days.max()}; this file makes no early-and-late "
                   "split, so every day present enters every cell"),
        "coins": [COIN_NAME[c] for c in sorted(COIN_NAME)],
    }

    # The output name and directory still come from the module-level OUT_PATH, so a
    # caller that redirects that constant redirects the whole write, as before.
    artifact.write(os.path.basename(OUT_PATH), results,
                   script=__file__, inputs=[NPZ_PATH], scope=scope,
                   settings=settings_used, started=t0,
                   out_dir=os.path.dirname(OUT_PATH))

    print_summary(results)
    print(f"\n[i2] wrote {os.path.basename(OUT_PATH)}")


# ---------------------------------------------------------------------------
# Printed table
# ---------------------------------------------------------------------------
def _fmt(x, nd=4):
    return f"{x:.{nd}f}" if isinstance(x, float) and np.isfinite(x) else "n/a"


def print_summary(results):
    meta = results["_meta"]
    print("=" * 92)
    print("I2 -- ONE-WAY COUNTERPARTY (taker_id) FIXED-EFFECTS VARIANCE DECOMPOSITION "
          f"of {H.headline_print_col()}")
    print("=" * 92)
    print(f"valid trades : {meta['n_trades_valid']:,}")
    print(f"model        : {meta['model']}")
    print("naive between-wallet share is UPWARD-biased; corrected share uses the")
    print("split-half cross-wallet covariance (noise cancels) as Var(alpha).")
    print("-" * 92)
    print("INTERPRETATION HELD: markout reference is a TRADE-PRINT VWAP, not a book mid,")
    print("so the FE MAGNITUDE mixes adverse selection with bid-ask bounce / earned")
    print("spread. I2 shows a stable per-wallet component EXISTS; the adverse-selection")
    print("reading of its size waits on the I4 book-mid check.")
    print("=" * 92)

    whale_key = H.whale_drop("fill_count", N_DROP_WHALES)["key"]
    hdr = (f"{'slice':<7} {'K':>4} {'wallets':>8} {'trd_cov':>9} {'med/w':>6} "
           f"{'naive_sh':>9} {'corr_sh':>9} {'sig_var':>10} {'p_perm':>8} "
           f"{'floor?':>6} {'dropfc_sh':>10}")
    print(hdr)
    print("-" * len(hdr))
    for sname in tuple(COIN_NAME.values()) + ("pooled",):
        if sname not in results:
            continue
        by_K = results[sname]["by_K"]
        for K in K_VALUES:
            blk = by_K.get(str(K))
            if blk is None:
                continue
            full = blk["full"]
            cov = full["coverage"]
            naive = full.get("naive", {})
            corr = full.get("split_half_corrected", {})
            plac = full.get("placebo", {})
            drop = blk[whale_key]
            print(
                f"{sname:<7} {K:>4} {cov['n_wallets_retained']:>8,} "
                f"{cov['trades_covered']:>9,} "
                f"{_fmt(cov['median_trades_per_wallet'], 0):>6} "
                f"{_fmt(naive.get('naive_idiosyncratic_share'), 4):>9} "
                f"{_fmt(corr.get('corrected_idiosyncratic_share'), 4):>9} "
                f"{_fmt(corr.get('corrected_signal_var'), 4):>10} "
                f"{_fmt(plac.get('p_value'), 4):>8} "
                f"{('FLOOR' if plac.get('p_value_is_floor') else ''):>6} "
                f"{_fmt(drop.get('corrected_idiosyncratic_share'), 4):>10}"
            )
    print("-" * len(hdr))
    print("naive_sh = naive between/total (upward-biased) | corr_sh = corrected "
          "(split-half) idiosyncratic share")
    print(f"sig_var  = corrected signal variance Var(alpha) | p_perm = label-shuffle "
          f"placebo p (floor 1/{N_PERM + 1} = {H.p_floor(N_PERM):.5f})")
    print("floor?   = FLOOR means no draw beat the observed value, so p is the "
          f"{N_PERM}-draw budget's smallest expressible value, not a measurement")
    print(f"dropfc_sh = corrected share after dropping the top {N_DROP_WHALES} wallets "
          "BY FILL COUNT (whale-robustness); key in the json is "
          f"{whale_key}")
    print("=" * 92)


if __name__ == "__main__":
    main()
