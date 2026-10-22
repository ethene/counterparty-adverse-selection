"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-20
References:
  - Hyperliquid L2 book + node_fills_by_block S3 archive; Zenodo 18184441 (Albers et al. 2026).
  - Glosten, Harris (1988); Hasbrouck (2007). Empirical Market Microstructure (own
    trade size as a price-impact / inventory regressor).
  - Kyle (1985). Continuous Auctions and Insider Trading (order size and information).
  - Benjamini, Hochberg (1995). FDR control (multiple-testing across cells).
"""

# ---------------------------------------------------------------------------
# OBJECT - OWN-SIZE / STYLE as a control on per-counterparty toxicity.
#
# HONEST SCOPE (post-audit 2026-06-20). The supported claim is NARROW and is
# stated that way throughout: trade size, sign and taker side do NOT LINEARLY
# explain the per-counterparty markout cross-section, and the per-wallet markout
# dispersion is statistically distinguishable from a size-bucket null. This is
# NOT a "structural exclusion" of own-size/style as a confound. The earlier
# "structural control / structurally excluded" framing OVERCLAIMED: the linear
# own-size regressors explain only R^2 ~ 0.0003 of markout variance, so the high
# share_retained (~0.99) is a TAUTOLOGY of the near-zero R^2 - residualizing on
# something that explains ~0 variance cannot move the markout, so a high retain
# ratio is mechanically guaranteed and carries NO evidentiary weight. The
# load-bearing evidence is therefore (i) the permutation nulls (observed residual
# share clears both the plain-label and the SIZE-MATCHED placebo at the p-floor)
# and (ii) the out-of-sample leave-one-out per-taker R^2 (loo_taker_r2_*), NOT
# the retain ratio. A NON-LINEAR control block (size deciles + signed-size
# deciles + size^2 + size x side) is added so the size argument is non-vacuous:
# it reaches R^2 ~ 0.005 (about 20x the linear fit) and the share still retains
# ~0.89, which IS a real (non-tautological) statement.
#
# Pipeline (all numpy, all VECTORIZED - NO per-trade bootstrap loops):
#   1. own size in coin units    = notional / entry_px
#      signed own size           = sign_taker * size   (sign_taker = +1 if bought)
#      |size|                    = size  (always >= 0; magnitude leg)
#      Regress per-fill book-mid markout (mo10_mid, mo60_mid) on
#        [1, signed_size, |size|, taker_side]  via a single ridge-stabilised OLS
#      (closed-form normal equations - one matrix solve, not a loop). Residualize.
#      ALSO fit a NON-LINEAR own-size control (deciles + size^2 + size x side) and
#      residualize on it - reported as a separate robustness block, not a swap.
#   2. Between-wallet (per-counterparty) variance share on the size-residualized
#      markout, RAW vs RESIDUAL, reusing i2_walletfe.py / i3_depth_control.py:
#        between_share = Var(per-wallet means) / Var(obs) over wallets with >= K obs
#                        (IN-SAMPLE, with a ~1/K noise floor - disclosed in JSON)
#        loo_taker_r2  = leave-one-out per-taker-mean R^2 (out-of-sample identity,
#                        the actual load-bearing OOS number)
#      Report identity share RAW vs size-residualized AND vs the NON-LINEAR
#      residual; significance rests on the permutation null + LOO R^2, not retain.
#   3. TWO placebos (both with the p-floor 1/(N_PERM+1) convention):
#      (a) SIZE-MATCHED permutation placebo - permute the markout values WITHIN
#          size deciles, so the size<->markout relationship is preserved but the
#          wallet<->markout association is destroyed. The observed between-wallet
#          residual share must beat this size-matched null; a wallet that is just a
#          size bucket cannot.
#      (b) POST-FILL (t+epsilon) re-mark placebo - re-baseline the markout to the
#          first book snapshot a few seconds AFTER the fill (the t+EPS leg) instead
#          of the entry mid: post-fill markout = mo60_mid - moEPS_mid (both legs are
#          measured off the SAME entry mid, so their difference is the signed mid
#          move from t+EPS to t+60, i.e. the markout re-based at t+EPS). A purely
#          MECHANICAL own-impact artifact lives in the [t, t+EPS] window and does
#          NOT persist once the baseline is pushed past it; genuine slow information
#          does persist. So the per-wallet share on the post-fill re-mark separates
#          mechanical own-impact (collapses) from real information (survives).
#
# GUARDS carried from the shared scripts: no-lookahead is inherited from the
# pre-joined entry/horizon mid columns (i4_midmarkout.py); sign convention
# (positive = taker profited = maker adverse-selected) is inherited unchanged;
# label-permutation placebo with p-floor 1/(N_PERM+1); OOS identity scored by
# WALLET (leave-one-out per-taker mean), never by row; whale-drop robustness
# (top-N wallets by notional removed); BH-FDR across coin x horizon x K cells;
# deterministic SEED declared below.
#
# REPRODUCIBILITY: no hardcoded absolute paths (HERE + env/argparse data-root),
# only os.path.basename in the JSON, numpy + stdlib only. Reads ONE shared
# intermediate (quickwin_markouts_mid.npz). No raw parse, no order-book rebuild.
#
# Run (bare python3 is BLOCKED on this machine):
#   uv run --no-project --with-requirements requirements.txt python3 identity/own_size_control.py
# DO NOT run the full compute as part of writing - py_compile only.
# ---------------------------------------------------------------------------

import argparse
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

# THE THREE OBJECTS THIS FILE SHARES WITH THE DEPTH CONTROL, TAKEN FROM IT RATHER THAN
# WRITTEN OUT A SECOND TIME. Until 2026-08-13 the ridge-stabilised OLS, the between-wallet
# variance share and the decile design block stood in both files, independently spelled and
# identical in behaviour, and the docstring of the share in this file said so in words
# without doing anything about it. Two spellings of one procedure agree until one of them
# is edited, and nothing in this tree compares two functions, so the day one is edited is
# the day the size control and the depth control quietly stop residualising the same way --
# which is the ONE property the pair of them exists to hold. The three came across only
# after they were measured rather than read: 69 cases for the fit, 45 for the share and 58
# for the design block, on inputs picked where linear algebra actually breaks (a singular
# matrix, more columns than rows, a constant response, twelve orders of magnitude either
# way, non-finite entries, an empty input, more bins than observations), with ZERO
# disagreements, on a comparator that caught every planted defect it was shown. The ridge
# constant travels with the code that reads it, for the same reason: a shared function
# reading a local copy of its own constant is the duplicate put back by the other door.
# i3_depth_control.py is declared an INPUT of this artifact, so an edit there marks these
# results stale; a producer hash alone cannot see across an import.
#
# The ridge constant is deliberately NOT on this import list. It had a copy here, that copy
# is gone, and the reason it is not replaced by an import is that nothing in this file reads
# it any more -- the only line that ever did was inside the fit. An imported name no caller
# uses is the duplicate walking back in through the other door, so the constant now lives in
# exactly one place, beside the arithmetic that spends it.
#
# _decile_dummies keeps its leading underscore, which now reads oddly for a name two files
# share. Renaming it would touch every call site in both, and this move is owed a proof that
# no number changed; a rename that changes no meaning is risk bought with no return. It is
# written down here instead of quietly left to look like an oversight.
from i3_depth_control import (
    ols_fit_residuals,
    between_wallet_share,
    _decile_dummies,
)

# -------------------- deterministic seed (shared data contract) --------------------
# Taken from the declaration instead of repeated here. The value is unchanged
# (settings.MASTER_SEED is 20260620), so binding it moves no number.
SEED = H.MASTER_SEED
np.random.seed(SEED)

# -------------------- paths (no hardcoded absolute paths) --------------------
HERE = os.path.dirname(os.path.abspath(__file__))


# The single environment name this file honours; see _resolve_data_root below.
DATA_ROOT_ENV = ("CAP_DATA_ROOT",)


def _resolve_data_root():
    """Data root: --data-root, then CAP_DATA_ROOT, else the directory the code is in.

    The resolution itself is panel_io.data_root, so the one module that knows where
    the panels live answers here too. The environment name is NARROWED to the single
    CAP_DATA_ROOT this file has always spoken rather than left at panel_io's full
    list: honouring four further names would let a machine that happens to export one
    of them feed this script a different panel, and that is a change of behaviour and
    not of code. check_first.py narrows the same way for the same reason.

    Only os.path.basename is written into the result JSON so no machine path ever
    leaks into the artifact.
    """
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--data-root", default=None)
    args, _ = ap.parse_known_args()
    return P.data_root(explicit=args.data_root, env_names=DATA_ROOT_ENV)


DATA_ROOT = _resolve_data_root()
# The file name stays a literal in the join. build.py derives this script's input edge
# by folding the argument of np.load to its last literal component, so replacing the
# name with a call would fold to nothing and delete the edge; panel_io's own docstring
# is where that trade is argued.
MID_NPZ_PATH = os.path.join(DATA_ROOT, "quickwin_markouts_mid.npz")
RESULTS_PATH = os.path.join(HERE, "own_size_control_results.json")

# -------------------- configuration --------------------
COIN_CODES = H.coin_labels("quickwin")     # the map belongs to the FILE, not the project

# Every column name is asked for by ROLE and never typed, so none of them can state a
# window that settings.py does not decide. The headline column is the one the study
# scores on; the companion is the long window reported beside it; the post-fill re-mark
# re-bases the companion leg on the SHORTEST rung of the ladder, which is what "a few
# seconds after the fill" means in this file.
#
# Asked of panel_io rather than of settings.py directly, which adds one thing and moves
# no name: the LENS stops being a choice made here. P.score_col("mid", h) reads the
# lens off the panel this file opens, so asking the book-mid panel for a trade-print
# column is refused instead of raising a bare KeyError deep in numpy. The four strings
# are the ones this file already used -- panel_io's own self-check asserts
# score_col("mid", h) equals settings.headline_mid_col(h) rung by rung.
HORIZON_COLS = (P.score_col("mid"), P.score_col("mid", H.COMPANION_HORIZON_S))
PLACEBO_BASELINE_COL = P.score_col("mid", H.LADDER_S[0])   # t+EPS leg, EPS = shortest rung
PLACEBO_LONG_COL = P.score_col("mid", H.COMPANION_HORIZON_S)   # long leg of the re-mark
EPS_S = H.LADDER_S[0]                      # the re-mark baseline, in seconds
K_LIST = H.PERSISTENCE_FLOOR_FILLS         # min obs per wallet for the between-wallet
                                           # share. The declared pair is (cell, small-
                                           # sample check) = (50, 100) and that is the
                                           # pair this file wants; it applies it over the
                                           # whole ranking window rather than per half,
                                           # which is why the comment says so out loud
N_PERM = H.N_PERM                          # permutation null draws (both placebos), taken
                                           # from the declaration. The budget sets the
                                           # floor 1/(N_PERM+1), and EVERY p in this file
                                           # sits on that floor because the observed share
                                           # lies outside the null range entirely, so each
                                           # p is reported with a flag saying it is the
                                           # budget speaking. The floor's VALUE is
                                           # therefore the whole of what the budget buys:
                                           # settings.min_perm_draws sizes it so that ONE
                                           # cell can clear alpha/m on its own, which the
                                           # earlier 200-draw floor of 0.00498 could not do
                                           # against this file's own 20-cell family
                                           # (0.05/20 = 0.0025) nor against the 48-cell
                                           # cross-month family (0.00104) the declaration
                                           # is sized for.
N_SIZE_BINS = 10                           # size deciles for the size-matched placebo
# RIDGE_LAMBDA stood here at 1e-6 and now lives with the fit that reads it, in
# i3_depth_control.py, at the same value.
WHALE_DROP_K = H.WHALE_DROP_K              # whale check: drop top-K wallets by NOTIONAL;
                                           # the count is declared, the criterion is
                                           # this file's
GAP_MAX_MS = 5000.0                        # join-quality gate (matches i4 build tolerance)


# THE RIDGE-STABILISED FIT AND THE BETWEEN-WALLET SHARE STOOD HERE and are imported from
# i3_depth_control.py at the top of this file. The share's own docstring used to say it was
# "identical object to i3_depth_control.between_wallet_share", which was true and was the
# problem: a sentence cannot keep two functions equal, and the equality is what makes RAW
# and residual comparable across the size control and the depth control at all.


def loo_taker_r2(values, taker, K):
    """Leave-one-out per-taker-mean R^2 (out-of-sample identity lift).

    For each eligible obs predict it by the mean of that taker's OTHER obs (the
    own value is left out, so the predictor is not mechanically in-sample). A
    positive LOO R^2 means wallet identity predicts the markout out of sample.
    Vectorized: per-group sum/count via bincount, leave-one-out by subtraction.
    """
    if values.size == 0:
        return float("nan"), 0
    uniq, inv = np.unique(taker, return_inverse=True)
    cnt = np.bincount(inv, minlength=uniq.size)
    elig = cnt >= K
    keep = elig[inv]
    if keep.sum() < 3:
        return float("nan"), 0
    v = values[keep]
    inv_k = inv[keep]
    u2, inv2 = np.unique(inv_k, return_inverse=True)
    s = np.bincount(inv2, weights=v, minlength=u2.size)
    c = np.bincount(inv2, minlength=u2.size)
    grp_sum = s[inv2]
    grp_cnt = c[inv2]
    denom = grp_cnt - 1.0
    with np.errstate(invalid="ignore", divide="ignore"):
        loo_pred = np.where(denom > 0,
                            (grp_sum - v) / np.where(denom > 0, denom, np.nan),
                            np.nan)
    ok = ~np.isnan(loo_pred)
    if ok.sum() < 3:
        return float("nan"), 0
    vv = v[ok]
    pp = loo_pred[ok]
    ss_res = float(np.sum((vv - pp) ** 2))
    ss_tot = float(np.sum((vv - vv.mean()) ** 2))
    r2 = (1.0 - ss_res / ss_tot) if ss_tot > 0 else float("nan")
    return r2, int(ok.sum())


# -------------------- size-matched permutation placebo --------------------
def size_matched_placebo(values, taker, size, K, rng, n_perm=N_PERM,
                         n_bins=N_SIZE_BINS, cell=""):
    """Null: shuffle the markout WITHIN size deciles, recompute the between share.

    Permuting within size bins preserves the size<->markout relationship (the bin a
    fill sits in is fixed) but destroys the wallet<->markout association. The
    observed between-wallet share must beat this size-matched null for identity to
    carry information a pure size bucket does not. Returns the n_perm null shares.

    Efficiency: the eligible-wallet bucket index and the size-bin index are computed
    ONCE; each draw shuffles values within bins (a single vectorized gather over a
    per-bin random key) then two bincounts - NO per-trade loop.

    `cell` names which (coin, horizon, K) block is drawing and appears only in the
    progress line. This file runs for 115 minutes by its own artifact and printed
    nothing between its banner and its table, so a run that had stopped looked exactly
    like a run that was working.
    """
    t_cell = artifact.start_clock()
    if values.size == 0:
        return np.full(n_perm, np.nan, dtype=np.float64)
    uniq, inv = np.unique(taker, return_inverse=True)
    cnt = np.bincount(inv, minlength=uniq.size)
    elig = cnt >= K
    if elig.sum() < 2:
        return np.full(n_perm, np.nan, dtype=np.float64)
    keep = elig[inv]
    v = values[keep].astype(np.float64)
    sz = size[keep].astype(np.float64)
    # dense wallet bucket over eligible rows (group structure fixed across draws)
    _, bucket = np.unique(inv[keep], return_inverse=True)
    n_buckets = int(bucket.max()) + 1
    c = np.bincount(bucket, minlength=n_buckets).astype(np.float64)

    # size-decile bin index over the eligible rows (rank-based, equal-count bins)
    n = sz.size
    order = np.argsort(sz, kind="stable")
    ranks = np.empty(n, dtype=np.float64)
    ranks[order] = np.arange(n, dtype=np.float64)
    bin_idx = np.minimum((ranks / max(n, 1) * n_bins).astype(np.int64), n_bins - 1)

    perms = np.empty(n_perm, dtype=np.float64)
    for i in range(n_perm):
        # within-bin shuffle WITHOUT a python loop over bins: stable-sort the rows
        # by (bin, random key) and read v in that order; because the bin component
        # dominates, this permutes values only WITHIN each bin.
        key = bin_idx.astype(np.float64) + rng.random(n)
        shuf = np.argsort(key, kind="stable")
        vp = v[shuf]
        s = np.bincount(bucket, weights=vp, minlength=n_buckets)
        means = s / c
        var_tot = float(np.var(vp))
        perms[i] = (float(np.var(means)) / var_tot) if var_tot > 0 else np.nan
        artifact.progress(f"own-size size-matched {cell}", i + 1, n_perm, t_cell)
    return perms


# -------------------- plain label-permutation null (for residual share) --------------------
def label_perm_placebo(values, taker, K, rng, n_perm=N_PERM, cell=""):
    """Plain label-permutation null: shuffle markout across eligible rows.

    Used for the size-residualized between-wallet share. Group buckets are fixed;
    each draw is one full shuffle + two bincounts (vectorized, no per-trade loop).

    `cell` names which block is drawing, for the progress line, and enters no number.
    """
    t_cell = artifact.start_clock()
    if values.size == 0:
        return np.full(n_perm, np.nan, dtype=np.float64)
    uniq, inv = np.unique(taker, return_inverse=True)
    cnt = np.bincount(inv, minlength=uniq.size)
    elig = cnt >= K
    if elig.sum() < 2:
        return np.full(n_perm, np.nan, dtype=np.float64)
    keep = elig[inv]
    v = values[keep].astype(np.float64)
    _, bucket = np.unique(inv[keep], return_inverse=True)
    n_buckets = int(bucket.max()) + 1
    c = np.bincount(bucket, minlength=n_buckets).astype(np.float64)
    perms = np.empty(n_perm, dtype=np.float64)
    for i in range(n_perm):
        vp = rng.permutation(v)
        s = np.bincount(bucket, weights=vp, minlength=n_buckets)
        means = s / c
        var_tot = float(np.var(vp))
        perms[i] = (float(np.var(means)) / var_tot) if var_tot > 0 else np.nan
        artifact.progress(f"own-size label-perm {cell}", i + 1, n_perm, t_cell)
    return perms


def _perm_pvalue(observed, perms, cell):
    """One-sided permutation p-value (observed >= null) with floor 1/(N+1).

    The counting now belongs to stats.permutation_p and this function is the adapter.
    Nothing it returns moves, and the three ways it could have moved are worth naming,
    because each is a real disagreement elsewhere in this tree that happens not to be
    one here: the module divides by the USABLE draw count and so did this (a permutation
    of a degenerate cell returns NaN and is dropped, not counted); the module counts a
    draw as extreme at `>= observed - tol` and so did this; and both floor the p at
    1/(usable + 1) rather than reporting a zero.

    The tolerance is passed as an ABSOLUTE 1e-12 rather than taken from the module's
    default, which is relative to the scale of the comparison. That keeps this file's
    arithmetic exactly, and it is a declared departure rather than a silent one: the
    returned block records tolerance_rule as "absolute, stated by the caller". The
    module argues the relative rule is the better instrument, and adopting it here would
    move the p on any cell where a draw sits within a whisker of the observed share --
    a measured change, owed its own recompute, not part of a consolidation.

    `cell` names the quantity and its coordinates. It is required rather than optional
    so the returned block says which cell produced the number.

    Returns (p, null_mean, block). The first two are NaN on a cell with no test, which
    the callers already read as NaN; the module says None, and the two are not the same
    to a caller that goes on to compare the value against 0.05.
    """
    block = stats.permutation_p(observed, perms, side="greater", abs_tol=1e-12,
                                n_requested=int(np.asarray(perms).size), cell=cell)
    p = float("nan") if block["p"] is None else float(block["p"])
    null_mean = (float("nan") if block["null_mean"] is None
                 else float(block["null_mean"]))
    return p, null_mean, block


# -------------------- BH-FDR (hand-rolled, numpy-only) --------------------
# The Benjamini-Hochberg step-up that used to be defined here is stats.benjamini_hochberg.
# The move costs no q: stats._legacy_bh_vectorised is a copy of the spelling that stood
# here, and that module's self-test runs the two against each other on 200 random
# families including ties and untestable cells and asserts identical values. What the
# module adds is the cutoff the q-values were judged against, which no local copy
# returned and which "survives the correction" cannot be read without.


# -------------------- size / sign helpers --------------------
def derive_signed_size(notional, entry_px, taker_side):
    """own size (coin units), |size|, signed own size, sign_taker.

    size       = notional / entry_px         (coin units; notional is quote units)
    sign_taker = +1 if taker bought (taker_side==1) else -1   (matches build/i4)
    signed     = sign_taker * size
    Rows with a non-positive / non-finite entry_px yield nan size and drop later.
    """
    with np.errstate(invalid="ignore", divide="ignore"):
        size = np.where((entry_px > 0) & np.isfinite(entry_px),
                        notional / entry_px, np.nan)
    sign_taker = np.where(taker_side == 1, 1.0, -1.0)
    signed = sign_taker * size
    return size, np.abs(size), signed, sign_taker


# THE DECILE DESIGN BLOCK STOOD HERE and is imported from i3_depth_control.py. The two
# copies were byte-identical below the docstring, and the equal-count bucketing they share
# is what makes the non-linear control in this file and the one in the depth control the
# same control rather than two things with one name.


def nonlinear_size_design(size, abs_size, signed_size, taker_side, n_bins=10):
    """NON-LINEAR own-size control design matrix (no intercept column here).

    Columns: |size| deciles (drop-first) + signed-size deciles (drop-first)
             + size^2 + (size x taker_side) interaction. ols_fit_residuals adds the
    intercept. This is a strictly richer control than the linear [signed,|size|,
    side] block, so its R^2 upper-bounds the linear one; it converts the vacuous
    linear "retain ~ 1 because R^2 ~ 0" argument into a real one.
    """
    Dabs = _decile_dummies(abs_size, n_bins=n_bins)
    Dsgn = _decile_dummies(signed_size, n_bins=n_bins)
    sq = (abs_size ** 2).reshape(-1, 1)
    inter = (size * taker_side.astype(np.float64)).reshape(-1, 1)
    return np.column_stack([Dabs, Dsgn, sq, inter])


# -------------------- per-group analysis --------------------
def analyse_group(z_cols, sel, label, horizon_col):
    """Own-size control for one coin group (or pooled), one horizon.

    z_cols : dict of full-length arrays loaded from the npz.
    sel    : boolean row mask for this group.
    Returns a result dict (cells per K). Pure vectorized work; no bootstrap loop.
    """
    out = {"coin": label, "horizon": horizon_col}

    mo = z_cols[horizon_col][sel].astype(np.float64)
    notional = z_cols["notional"][sel].astype(np.float64)
    entry_px = z_cols["entry_px"][sel].astype(np.float64)
    taker_side = z_cols["taker_side"][sel].astype(np.int8)
    taker = z_cols["taker_id"][sel].astype(np.int64)
    gap_entry = z_cols["gap_entry_ms"][sel].astype(np.float64)

    # post-fill re-mark legs (same entry mid, so the difference re-bases at t+EPS)
    mo_eps = z_cols[PLACEBO_BASELINE_COL][sel].astype(np.float64)
    mo_long = z_cols[PLACEBO_LONG_COL][sel].astype(np.float64)
    postfill = mo_long - mo_eps   # signed mid move from t+EPS to t+60 (markout re-based)

    size, abs_size, signed_size, _ = derive_signed_size(notional, entry_px, taker_side)

    # nan-aware row mask: need markout, size legs, controls, and an in-tolerance join
    finite = (np.isfinite(mo) & np.isfinite(size) & np.isfinite(signed_size)
              & np.isfinite(taker_side.astype(np.float64))
              & np.isfinite(gap_entry) & (gap_entry <= GAP_MAX_MS))
    n_total = int(mo.size)
    out["n_obs_total"] = n_total
    out["n_obs_used"] = int(np.sum(finite))
    out["nan_drop_fraction"] = (float(np.mean(~finite)) if n_total else float("nan"))
    if finite.sum() < 50:
        out["note"] = "too few finite rows for the own-size control fit"
        out["cells"] = []
        return out

    y = mo[finite]
    tk = taker[finite]
    X = np.column_stack([signed_size[finite], abs_size[finite],
                         taker_side[finite].astype(np.float64)])

    # (1) OLS of markout on [signed_size, |size|, taker_side]; residualize (LINEAR)
    beta, resid, r2_size = ols_fit_residuals(y, X)
    out["ols_own_size"] = {
        "predictors": ["intercept", "signed_size", "abs_size", "taker_side"],
        "beta": [float(b) for b in beta],
        "r2_own_size": r2_size,
        "note": "R^2 of own signed size, |size| and taker side on the raw mid "
                "markout. This LINEAR fit explains essentially no markout variance "
                "(R^2 ~ 0.0003), so a high share_retained on the linear residual is "
                "a TAUTOLOGY of the near-zero R^2 (residualizing on ~0 variance "
                "cannot move the markout) and is NOT evidence. The supported claim "
                "is the narrow one: size/sign/side do not LINEARLY explain the "
                "per-counterparty markout cross-section.",
    }

    # (1b) NON-LINEAR own-size control: deciles + size^2 + size x side. Strictly
    # richer than the linear block, so its R^2 upper-bounds it; residualizing on it
    # and re-measuring retain converts the vacuous linear argument into a real one.
    Xnl = nonlinear_size_design(size[finite], abs_size[finite],
                                signed_size[finite],
                                taker_side[finite].astype(np.float64),
                                n_bins=N_SIZE_BINS)
    _, resid_nl, r2_nl = ols_fit_residuals(y, Xnl)
    out["ols_own_size_nonlinear"] = {
        "predictors": ["intercept", "abs_size_deciles(drop-first)",
                       "signed_size_deciles(drop-first)", "abs_size^2",
                       "size_x_taker_side"],
        "n_design_cols": int(Xnl.shape[1]),
        "r2_own_size_nonlinear": r2_nl,
        "note": "R^2 of a NON-LINEAR own-size control (size + signed-size deciles, "
                "size^2, size x side) on the raw markout. Much larger than the "
                "linear R^2, so the retain ratio on THIS residual (reported per cell "
                "as share_retained_nonlinear) is a non-tautological statement that "
                "identity dispersion survives a real size control.",
    }

    # post-fill re-mark, restricted to rows where BOTH legs are valid
    pf_ok = finite & np.isfinite(postfill)
    y_pf = postfill[pf_ok]
    tk_pf = taker[pf_ok]
    out["postfill_remark"] = {
        "baseline_leg": PLACEBO_BASELINE_COL,
        "long_leg": PLACEBO_LONG_COL,
        "baseline_s": EPS_S,
        "long_s": H.COMPANION_HORIZON_S,
        "n_obs_used": int(pf_ok.sum()),
        "definition": f"post-fill markout = ({PLACEBO_LONG_COL} - "
                      f"{PLACEBO_BASELINE_COL}): mid move from t+{EPS_S}s to "
                      f"t+{H.COMPANION_HORIZON_S}s, both measured off the entry mid, so "
                      "it re-bases the markout a few seconds AFTER the fill. A mechanical "
                      "own-impact artifact does NOT persist post-fill; genuine "
                      "information does.",
    }

    # (2)/(3) between-wallet share RAW vs RESIDUAL, plus both placebos, per K
    cells = []
    for K in K_LIST:
        raw_share, n_w_raw, n_o_raw = between_wallet_share(y, tk, K)
        res_share, n_w_res, n_o_res = between_wallet_share(resid, tk, K)
        res_nl_share, _, _ = between_wallet_share(resid_nl, tk, K)
        raw_loo, _ = loo_taker_r2(y, tk, K)
        res_loo, _ = loo_taker_r2(resid, tk, K)

        # plain label-permutation null on the size-residualized share (the decisive
        # number: does identity survive own-size residualization beyond label chance)
        rng_res = np.random.default_rng(SEED + 17 * K)
        perms_res = label_perm_placebo(resid, tk, K, rng_res, n_perm=N_PERM,
                                       cell=f"residual {label} {horizon_col} K={K}")
        p_res, perm_res_mean, blk_res = _perm_pvalue(
            res_share, perms_res,
            ("between_wallet_share_label_perm", label, horizon_col, K))

        # placebo (a): SIZE-MATCHED null on the size-residualized share
        rng_sm = np.random.default_rng(SEED + 101 * K)
        perms_sm = size_matched_placebo(resid, tk, size[finite], K, rng_sm,
                                        n_perm=N_PERM, n_bins=N_SIZE_BINS,
                                        cell=f"{label} {horizon_col} K={K}")
        p_sm, perm_sm_mean, blk_sm = _perm_pvalue(
            res_share, perms_sm,
            ("between_wallet_share_size_matched", label, horizon_col, K))

        # placebo (b): POST-FILL re-mark between-wallet share + its own label null
        pf_share, n_w_pf, n_o_pf = between_wallet_share(y_pf, tk_pf, K)
        rng_pf = np.random.default_rng(SEED + 211 * K)
        perms_pf = label_perm_placebo(y_pf, tk_pf, K, rng_pf, n_perm=N_PERM,
                                      cell=f"post-fill {label} {horizon_col} K={K}")
        p_pf, perm_pf_mean, blk_pf = _perm_pvalue(
            pf_share, perms_pf,
            ("postfill_between_wallet_share_label_perm", label, horizon_col, K))

        retained = ((res_share / raw_share)
                    if (raw_share == raw_share and raw_share > 0
                        and res_share == res_share) else float("nan"))
        retained_nl = ((res_nl_share / raw_share)
                       if (raw_share == raw_share and raw_share > 0
                           and res_nl_share == res_nl_share) else float("nan"))

        # ~1/K in-sample noise floor on the between-wallet share: with K obs per
        # wallet, sampling noise alone inflates Var(per-wallet means) by ~ within-
        # wallet-variance / K, so the share carries an upward in-sample bias of
        # roughly 1/K even under pure noise. Reported so the share is not read as a
        # clean effect size; significance rests on the perm null + LOO R^2 instead.
        noise_floor = 1.0 / float(K)

        # IDENTITY SURVIVES THE LINEAR CONTROL + BEATS THE SIZE-BUCKET NULL. NOTE
        # this is NOT "structural exclusion": the linear retain is tautological
        # (R^2 ~ 0). The boolean only asserts (i) the size-residualized share beats
        # its plain label null AND its SIZE-MATCHED placebo at p<=0.05, and (ii) the
        # NON-LINEAR retain (the non-vacuous one) holds >= 0.5 of the raw share.
        identity_beats_size_null = bool(
            res_share == res_share and res_share > 0
            and p_res == p_res and p_res <= 0.05
            and p_sm == p_sm and p_sm <= 0.05
            and retained_nl == retained_nl and retained_nl >= 0.5)

        cell = {
            "K": K,
            "n_wallets": n_w_raw,
            "n_obs_eligible": n_o_raw,
            "between_share_raw": raw_share,
            "between_share_size_residual": res_share,
            "between_share_nonlinear_residual": res_nl_share,
            "share_retained_fraction": retained,
            "share_retained_nonlinear": retained_nl,
            "between_share_in_sample_noise_floor": noise_floor,
            "loo_taker_r2_raw": raw_loo,
            "loo_taker_r2_size_residual": res_loo,
            "label_perm_p_residual": p_res,
            "label_perm_residual_mean": perm_res_mean,
            "size_matched_placebo_p": p_sm,
            "size_matched_placebo_mean": perm_sm_mean,
            "postfill_between_share": pf_share,
            "postfill_label_perm_p": p_pf,
            "postfill_label_perm_mean": perm_pf_mean,
            "postfill_n_wallets": n_w_pf,
            "p_floor": H.p_floor(N_PERM),
            # Each of the three p-values above is reported with a flag saying whether it
            # is a measurement or the budget's smallest expressible value. A floored p
            # says only that no draw beat the observed share.
            "label_perm_p_residual_is_floor": bool(H.p_is_floored(p_res, N_PERM))
            if p_res == p_res else False,
            "size_matched_placebo_p_is_floor": bool(H.p_is_floored(p_sm, N_PERM))
            if p_sm == p_sm else False,
            "postfill_label_perm_p_is_floor": bool(H.p_is_floored(p_pf, N_PERM))
            if p_pf == p_pf else False,
            "identity_beats_size_null": identity_beats_size_null,
            # The three procedures behind the three p-values above, each stating its
            # own draw counts, how many draws it dropped, the tolerance it applied and
            # the cell it drew from. A p-value with no draw count beside it cannot be
            # read: 0.0005 from 2000 draws and 0.0005 from 2000 draws of which 1600
            # failed are the same digits and different evidence.
            "procedures": {"label_perm_residual": blk_res,
                           "size_matched_placebo": blk_sm,
                           "postfill_label_perm": blk_pf},
            "disclosure": "between_share_* and share_retained_* are IN-SAMPLE with "
                          "a ~1/K noise floor (between_share_in_sample_noise_floor); "
                          "the linear retain (~0.99) is a tautology of the ~0 linear "
                          "R^2. Load-bearing evidence = the permutation nulls "
                          "(label_perm_p_residual, size_matched_placebo_p) and the "
                          "OUT-OF-SAMPLE leave-one-out per-taker R^2 "
                          "(loo_taker_r2_size_residual), NOT the retain ratio. "
                          "share_retained_nonlinear is the non-tautological retain.",
        }
        cells.append(cell)
        print(f"[own-size] {label:<6} {horizon_col:<8} K={K:>3} "
              f"betwRaw={_fmt(raw_share)} betwResid={_fmt(res_share)} "
              f"retainLin={_fmt(retained)} retainNL={_fmt(retained_nl)} "
              f"looResid={_fmt(res_loo)} p_res={_fmt(p_res)} "
              f"p_sizematch={_fmt(p_sm)} postfill={_fmt(pf_share)} "
              f"p_pf={_fmt(p_pf)} beats_null={identity_beats_size_null}")
    out["cells"] = cells
    return out


def _fmt(v):
    if v is None:
        return "n/a"
    if isinstance(v, float) and v != v:
        return "nan"
    return f"{v:+.4f}" if isinstance(v, float) else str(v)


# -------------------- whale-drop robustness --------------------
def whale_mask(z_cols, sel, drop_k=WHALE_DROP_K):
    """Boolean keep-mask within `sel` that drops the top-K wallets by total notional.

    Whale-robustness mirror of i3_nonrecoverability_oos.whale_robust_check: rank
    wallets by summed notional, drop the top-K, keep the rest. Vectorized.
    """
    taker = z_cols["taker_id"][sel].astype(np.int64)
    notional = z_cols["notional"][sel].astype(np.float64)
    uniq, inv = np.unique(taker, return_inverse=True)
    tot = np.bincount(inv, weights=notional, minlength=uniq.size)
    if uniq.size <= drop_k:
        return np.ones(taker.size, dtype=bool)
    whales = np.argsort(tot)[::-1][:drop_k]
    is_whale = np.zeros(uniq.size, dtype=bool)
    is_whale[whales] = True
    return ~is_whale[inv]


# -------------------- main --------------------
# What every number in this file was computed under: the KEYWORDS for
# settings.fingerprint, not the block. artifact.write builds the block once and puts it
# in _meta, where a census can find it by one predicate; it used to be built inside the
# payload's scope object and copied a second time into _meta, which is a record living
# in two places and is the defect artifact.py exists to end.
#
# n_perm is passed even though it now equals the declaration, because
# settings.fingerprint states a migrating value only when the caller CONFIRMS what its
# run used; omitted, it would fall into declared_not_confirmed and this artifact would
# stop asserting its own budget. The note is BUILT from the values and never typed,
# because a caption naming a setting the run did not use is the same defect as a field
# name that does, and this one had already gone stale.
SETTINGS_USED = dict(
    h=H.HEADLINE_HORIZON_S, lens="mid",
    master_seed=SEED,
    n_perm=N_PERM,
    n_boot=None,
    rank_floor_fills=list(K_LIST),
    persistence_floor_fills=None,
    horizons_scored_s=[H.HEADLINE_HORIZON_S, H.COMPANION_HORIZON_S],
    postfill_baseline_s=EPS_S,
    whale_drop_criterion="notional",
    p_floor=H.p_floor(N_PERM),
    overrides_note=(
        f"n_perm {N_PERM} is settings.N_PERM: the floor is "
        f"{H.p_floor(N_PERM):.6f} and every p in this file sits on it, which "
        f"now clears both this file's own corrected rank-one threshold "
        f"({H.FDR_ALPHA}/20 = {H.FDR_ALPHA / 20:.4f}) and the 48-cell "
        f"cross-month one ({H.FDR_ALPHA / 48:.5f}); rank_floor_fills "
        f"{tuple(K_LIST)} not the declared single {H.RANK_FLOOR_FILLS}, the "
        "pair being settings.PERSISTENCE_FLOOR_FILLS applied over the WHOLE "
        "ranking window here rather than per half; no bootstrap is drawn, so "
        "n_boot does not apply; whales are dropped by NOTIONAL; the seed is "
        "settings.MASTER_SEED unchanged; both the headline and the companion "
        "window are scored, and the post-fill re-mark re-bases the companion "
        f"leg at t+{EPS_S}s; the permutation tolerance is an ABSOLUTE 1e-12 "
        "passed to stats.permutation_p, not that module's default, which is "
        "relative to the scale of the comparison"),
)


def main():
    started = artifact.start_clock()
    # panel_io owns both refusals: the missing FILE message names the producer that
    # writes it, since the panel is a gitignored intermediate a fresh clone does not
    # carry, and the missing COLUMN message names what was asked and what the file
    # holds. Neither prints a directory, so no account name can reach a pasted log.
    P.require_present("mid", MID_NPZ_PATH, env_names=DATA_ROOT_ENV)

    z = np.load(MID_NPZ_PATH, allow_pickle=False)
    need = (set(HORIZON_COLS) | {PLACEBO_BASELINE_COL, PLACEBO_LONG_COL,
            "notional", "entry_px", "taker_side", "taker_id", "coin",
            "gap_entry_ms"})
    P.require_columns(z, "mid", *sorted(need))

    # load just the needed columns once
    z_cols = {c: np.asarray(z[c]) for c in need}
    coin = z_cols["coin"].astype(np.int8)

    print(f"[own-size] rows={coin.size:,} horizons={list(HORIZON_COLS)} "
          f"controls=[signed_size,abs_size,taker_side] K_list={K_LIST} "
          f"n_perm={N_PERM} size_bins={N_SIZE_BINS} seed={SEED}")

    results = {
        "object": "OWN-SIZE CONTROL - per-counterparty markout dispersion vs a "
                  "size/sign/side control. SUPPORTED CLAIM (narrow): trade size, "
                  "sign and taker side do NOT LINEARLY explain the per-counterparty "
                  "markout cross-section (own-size R^2 ~ 0.0003), and the identity "
                  "dispersion is statistically distinguishable from a size-bucket "
                  "null (size-matched placebo p <= 1/(N_PERM+1)). This is NOT a "
                  "structural exclusion of own-size/style as a confound.",
        "caveats": {
            "linear_retain_is_tautological": "The linear own-size R^2 ~ 0.0003, so "
                "share_retained_fraction (~0.99) is a TAUTOLOGY of the near-zero R^2 "
                "(residualizing on ~0 explained variance cannot move the markout) "
                "and carries NO evidentiary weight. Do not cite it as exclusion.",
            "between_share_is_in_sample": "between_share_* and share_retained_* are "
                "computed IN-SAMPLE (per-wallet means reused in numerator and "
                "denominator) and carry a ~1/K upward noise floor "
                "(between_share_in_sample_noise_floor). They are descriptive, not a "
                "clean effect size.",
            "load_bearing_evidence": "Significance rests on (1) the permutation "
                "nulls - observed residual share clears both the plain-label null "
                "(label_perm_p_residual) and the SIZE-MATCHED placebo "
                "(size_matched_placebo_p), which BOTH land exactly on the "
                f"{H.p_floor(N_PERM):.6f} floor: that says no draw beat the observed "
                "share and not how small the p is - and (2) the OUT-OF-SAMPLE "
                "leave-one-out per-taker R^2 (loo_taker_r2_size_residual 0.092 to 0.097 "
                "on BTC at the headline window), NOT the retain ratio.",
            "what_the_budget_changed": (
                f"Every p here is floored, and was floored at the earlier 200-draw budget "
                f"too, because the observed share sits outside the null range entirely. "
                f"What moved is the floor's VALUE, from 0.004975 to "
                f"{H.p_floor(N_PERM):.6f}, and with it what a single cell may claim. A "
                f"lone significant cell must clear alpha/m unaided: {H.FDR_ALPHA}/20 = "
                f"{H.FDR_ALPHA / 20:.4f} for this file's own family and {H.FDR_ALPHA}/48 "
                f"= {H.FDR_ALPHA / 48:.5f} for the cross-month family the declared budget "
                f"is sized for. The old floor sat ABOVE both, so no cell here could have "
                f"been asserted on its own however strong the effect. Note what this does "
                f"NOT change: the BH verdict was already reject-all at 200 draws, because "
                f"20 p-values tied at one floor clear the step-up procedure at the largest "
                f"rank. That homogeneity was the budget's, not the data's."),
            "nonlinear_control_added": "A NON-LINEAR control (size + signed-size "
                "deciles, size^2, size x side) reaches R^2 of 0.005 to 0.016 at the "
                "headline window, which is 20 to 60 times the linear fit; the share "
                "still retains 0.79 to 0.93 of the raw share on that residual "
                "(share_retained_nonlinear) - that retain IS non-tautological.",
        },
        # This file's own descriptive object block. It is NOT the canonical scope
        # record: that one is the population / window / coins triple in
        # _meta.scope, which artifact.write requires and which a census reads by one
        # predicate. This block is the superset a reader of the numbers wants.
        "scope": {
            "canonical_scope_at": "_meta.scope",
            "settings_fingerprint_at": "_meta.settings_fingerprint",
            "markout_source": "mid (book-mid markout)",
            "input_npz": os.path.basename(MID_NPZ_PATH),
            "horizon_cols": list(HORIZON_COLS),
            "horizons_s": [H.HEADLINE_HORIZON_S, H.COMPANION_HORIZON_S],
            "control_cols": ["signed_size", "abs_size", "taker_side"],
            "nonlinear_control_cols": ["abs_size_deciles", "signed_size_deciles",
                                       "abs_size^2", "size_x_taker_side"],
            "size_definition": "size(coin units) = notional / entry_px; "
                               "signed_size = sign_taker * size; sign_taker=+1 if "
                               "taker bought (taker_side==1) else -1",
            "K_list": list(K_LIST),
            "n_perm": N_PERM,
            "n_size_bins": N_SIZE_BINS,
            "p_floor": H.p_floor(N_PERM),
            "p_floor_note": (
                f"{N_PERM} draws cannot express a p below {H.p_floor(N_PERM):.6f}; each "
                "cell carries label_perm_p_residual_is_floor, "
                "size_matched_placebo_p_is_floor and postfill_label_perm_p_is_floor "
                "saying which of its p-values are measurements and which are that floor"),
            "gap_max_ms": GAP_MAX_MS,
            "seed": SEED,
            "reuses": "i2_walletfe / i3_depth_control between-wallet share; "
                      "i3_nonrecoverability_oos BH-FDR + whale-drop; "
                      "i4_midmarkout pre-joined mid markouts (no-lookahead inherited)",
            "question": "Do trade size, sign and taker side LINEARLY explain the "
                        "per-counterparty markout cross-section, and is the "
                        "between-wallet dispersion distinguishable from a size-bucket "
                        "null? (Answered: no to the first, yes to the second.) The "
                        "earlier 'structural exclusion' framing is retracted - see "
                        "caveats.linear_retain_is_tautological.",
            "placebos": {
                "size_matched": "permute the markout WITHIN size deciles - the "
                                "between share must beat a null that preserves the "
                                "size<->markout link but breaks wallet identity.",
                "postfill_remark": f"re-base the markout to t+{EPS_S}s "
                                   f"({PLACEBO_LONG_COL} - {PLACEBO_BASELINE_COL}): "
                                   "a mechanical own-impact artifact does NOT persist "
                                   "post-fill, genuine information does.",
            },
            "verdict_rule": "identity_beats_size_null = size-residualized between "
                            "share > 0 AND beats its plain label null (p<=0.05) AND "
                            "beats its SIZE-MATCHED null (p<=0.05) AND the "
                            "NON-LINEAR retain (share_retained_nonlinear, the "
                            "non-tautological one) holds >= 50% of the raw share. "
                            "This asserts only that identity survives the LINEAR "
                            "control and beats the size-bucket placebo - NOT "
                            "structural exclusion of the style confound.",
        },
        "by_coin": [],
        "pooled": None,
        "issues": [],
    }

    # per-coin + pooled, per horizon
    for code, label in COIN_CODES.items():
        sel = coin == code
        if sel.sum() == 0:
            results["issues"].append(f"{label}: no rows")
            continue
        for hcol in HORIZON_COLS:
            results["by_coin"].append(analyse_group(z_cols, sel, label, hcol))
            # whale-robustness mirror at this coin x horizon
            keep = whale_mask(z_cols, sel, drop_k=WHALE_DROP_K)
            sub = {c: z_cols[c][sel][keep] for c in z_cols}
            sub_sel = np.ones(next(iter(sub.values())).shape[0], dtype=bool)
            wr = analyse_group(sub, sub_sel, f"{label}_noWhale", hcol)
            results["by_coin"].append(wr)

    pooled_blocks = []
    for hcol in HORIZON_COLS:
        sel = np.ones(coin.size, dtype=bool)
        pooled_blocks.append(analyse_group(z_cols, sel, "POOLED", hcol))
    results["pooled"] = pooled_blocks

    # ---- BH-FDR across all (coin x horizon x K) cells on the residual label p ----
    cell_pointers = []
    pvals = []
    for blk in results["by_coin"] + (results["pooled"] or []):
        for cell in blk.get("cells", []):
            cell_pointers.append(cell)
            pvals.append(cell.get("label_perm_p_residual", float("nan")))
    # The correction comes from stats.py. The move costs no q: stats._legacy_bh_vectorised
    # is the spelling that stood in this file, and the self-test there runs the two
    # against each other on 200 random families including ties and untestable cells. What
    # the module adds is the CUTOFF, which the local copy did not return and without
    # which "survives the correction" is not a statement a reader can check.
    fdr = stats.benjamini_hochberg(
        pvals, alpha=H.FDR_ALPHA,
        family="label_perm_p_residual across every coin x horizon x K cell "
               "(per-coin, no-whale and pooled)")
    for cell, q in zip(cell_pointers, fdr["q"]):
        cell["label_perm_p_residual_bh_q"] = (float("nan") if q is None else float(q))
        # A q is p * m / rank, so a q on the permutation floor means the p was floored
        # and the cell held the largest rank. It inherits the budget, not the effect.
        cell["label_perm_p_residual_bh_q_at_p_floor"] = (
            False if q is None else bool(H.p_is_floored(q, N_PERM)))
    results["_fdr"] = dict(fdr, q=None,
                           q_note="the q-values are on the cells, under "
                                  "label_perm_p_residual_bh_q; this block holds the "
                                  "procedure, the family and the cutoff applied to them")

    results["_meta"] = {
        "input_npz": os.path.basename(MID_NPZ_PATH),
        "seed": SEED,
    }

    # The population is counted from what the run actually loaded -- the row count of
    # the npz it opened -- rather than described from the constants, because a scope
    # taken from constants describes the run the file was written for and not the one
    # that produced these numbers.
    # i3_depth_control.py IS AN INPUT AND NOT A NEIGHBOUR. A results file records the hash
    # of the script named as its producer and of nothing else, so the fit, the share and the
    # design block this run imports from that file are invisible to both freshness gates:
    # editing the ridge there would leave every recorded hash in this tree matching while
    # this artifact reported residual shares computed another way. That is the price of
    # having one home instead of two copies, and naming the home as an input is what pays
    # it -- the gate compares that file's bytes against what this run read, and an edit
    # there marks these results stale exactly as an edit here does.
    artifact.write(
        os.path.basename(RESULTS_PATH), results,
        script=__file__,
        inputs=[MID_NPZ_PATH, "i3_depth_control.py"],
        scope={
            "population": (
                f"{int(coin.size)} taker fills; between-wallet share computed at "
                f"every fill floor in {list(K_LIST)}, per coin, per coin with the "
                f"top {WHALE_DROP_K} wallets by notional dropped, and pooled, at "
                f"each of {list(HORIZON_COLS)}"),
            "window": (f"the ten-day window carried by "
                       f"{os.path.basename(MID_NPZ_PATH)}; this file re-marks nothing "
                       f"and cuts no halves, so it has no window of its own"),
            "coins": sorted(COIN_CODES.values()),
        },
        settings=SETTINGS_USED,
        started=started,
        out_dir=os.path.dirname(RESULTS_PATH) or HERE)

    _print_summary(results)


def _print_summary(results):
    print("\n" + "=" * 96)
    print("OWN-SIZE CONTROL - PER-COUNTERPARTY MARKOUT DISPERSION vs A SIZE/SIGN/SIDE CONTROL")
    print("=" * 96)
    sc = results["scope"]
    print(f"  markout={sc['markout_source']} lin_controls={sc['control_cols']}")
    print(f"  nonlin_controls={sc['nonlinear_control_cols']}")
    print(f"  {sc['n_perm']} permutations (p-floor={sc['p_floor']:.5f}); "
          f"{sc['n_size_bins']} size-deciles; seed={sc['seed']}.")
    print("  A p AT that floor means no draw beat the observed share: the budget "
          "speaking, not a")
    print("  measurement, and a floored p cannot clear a corrected threshold below it.")
    print("-" * 96)
    print("  CLAIM (narrow): size/sign/side do NOT LINEARLY explain the per-counterparty")
    print("  markout (own-size R^2 ~ 0.0003), and the dispersion beats a size-bucket null.")
    print("  This is NOT structural exclusion - the LINEAR retain (~0.99) is a tautology of")
    print("  the ~0 R^2. Load-bearing = the perm nulls (p_res, p_szm) + the OOS LOO R^2.")
    print("  retainNL (non-linear-residual retain) is the non-tautological retain.")
    print("  Placebos: (a) size-matched within-decile shuffle, (b) post-fill re-mark.")
    print("-" * 96)
    header = (f"  {'group':<14} {'horizon':<8} {'K':>4} {'betwRaw':>8} {'betwRes':>8} "
              f"{'retLin':>7} {'retNL':>7} {'looRes':>8} {'p_res':>7} {'q_res':>7} "
              f"{'p_szm':>7} {'postfl':>8} {'p_pf':>7} {'beatN':>5}")
    blocks = list(results["by_coin"])
    if results.get("pooled"):
        blocks += list(results["pooled"])
    print(header)
    for g in blocks:
        if not g.get("cells"):
            print(f"  {g['coin']:<14} {g.get('horizon', ''):<8} "
                  f"{'-':>4} {g.get('note', 'no cells')}")
            continue
        r2 = g["ols_own_size"]["r2_own_size"]
        r2nl = g.get("ols_own_size_nonlinear", {}).get("r2_own_size_nonlinear")
        print(f"  -- {g['coin']} {g['horizon']}: own-size OLS R^2(lin)={_fmt(r2)} "
              f"R^2(nl)={_fmt(r2nl)} "
              f"(n_used={g['n_obs_used']:,}, nan_drop={_fmt(g['nan_drop_fraction'])})")
        for c in g["cells"]:
            print(f"  {g['coin']:<14} {g['horizon']:<8} {c['K']:>4} "
                  f"{_fmt(c['between_share_raw']):>8} "
                  f"{_fmt(c['between_share_size_residual']):>8} "
                  f"{_fmt(c['share_retained_fraction']):>7} "
                  f"{_fmt(c.get('share_retained_nonlinear')):>7} "
                  f"{_fmt(c['loo_taker_r2_size_residual']):>8} "
                  f"{_fmt(c['label_perm_p_residual']):>7} "
                  f"{_fmt(c.get('label_perm_p_residual_bh_q')):>7} "
                  f"{_fmt(c['size_matched_placebo_p']):>7} "
                  f"{_fmt(c['postfill_between_share']):>8} "
                  f"{_fmt(c['postfill_label_perm_p']):>7} "
                  f"{str(c['identity_beats_size_null']):>5}")
    print("-" * 96)
    print("  READING: retLin (~0.99) is a TAUTOLOGY of the ~0 linear R^2 - ignore it. The")
    print("  real evidence is looRes (OOS leave-one-out per-taker R^2) > 0 and the residual")
    print("  share beating both p_res (plain) and p_szm (size-matched) nulls, plus retNL")
    print("  (retain under a real non-linear size control) staying high. A post-fill share")
    print("  (postfl) that stays positive and significant (p_pf) means the signal is NOT a")
    print("  mechanical own-impact artifact of the entry instant but persists past the fill.")
    if results.get("issues"):
        print("-" * 88)
        for msg in results["issues"]:
            print(f"  [!] {msg}")
    print("=" * 88)
    print(f"  results -> {os.path.basename(RESULTS_PATH)}")


if __name__ == "__main__":
    main()
