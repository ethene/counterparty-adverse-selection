"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-19
References: Easley, Lopez de Prado, O'Hara (2012) VPIN; Hyperliquid node-data S3; Zenodo 18184441.
"""

# ---------------------------------------------------------------------------
# OBJECT I3 - OUT-OF-SAMPLE NON-RECOVERABILITY OF PER-COUNTERPARTY TOXICITY.
#
# The persistence result (KS2) shows per-counterparty idiosyncratic toxicity is
# real and stable across an early/late split. That is an IN-SAMPLE dispersion
# statement. This test upgrades it to an OUT-OF-SAMPLE NON-RECOVERABILITY claim:
#
#   A market maker who knows ONLY anonymous trade-flow metrics (VPIN-style bulk
#   classification, signed flow imbalance, mean size, trade intensity) - the
#   information an off-chain CEX counterparty can compute - cannot recover the
#   wallet's future (LATE-half) toxicity. The wallet's own history (its EARLY-half
#   mean markout, i.e. the counterparty "fixed effect" that only on-chain identity
#   resolution makes observable) adds out-of-sample predictive lift that the
#   anonymous metrics do NOT capture.
#
# Design (per coin, then pooled; both windows settings.py names -- the headline one
# and the long companion, in that order of importance and the reverse order of
# reporting):
#   1. EARLY = days 4-8, LATE = days 9-13 (the validated persistence split).
#   2. Per wallet with >= K trades in BOTH halves (K in {50,100}):
#        history FE        = wallet EARLY-half mean markout (the identity signal)
#        anonymous metrics = wallet EARLY-half aggregate of:
#          (a) VPIN-style toxicity (bulk-volume classification, equal-vol buckets)
#          (b) signed trade-flow imbalance (rolling-window |buy-sell| / total)
#          (c) mean notional / size
#          (d) trade intensity (trades per unit time across the EARLY half)
#   3. TARGET = wallet LATE-half mean markout.
#        model A = anonymous metrics only
#        model B = anonymous metrics + history FE
#      Report the INCREMENTAL out-of-sample lift of B over A:
#        incremental OOS R^2  and  incremental Spearman (pred vs actual).
#      OOS = wallets are split into a fit fold and an eval fold; both models are
#      fit on the fit fold, scored on the held-out eval fold, k-fold averaged.
#   4. PLACEBO: permute the wallet labels on the history FE column (break the
#      identity link) and re-run; the incremental lift must vanish. Permutation
#      p over >= N_PERM shuffles, p-floor = 1/(N_PERM+1).
#   5. ROBUSTNESS: rank-based (Spearman) alongside OLS R^2; whale check (drop the
#      top-k wallets by total notional, confirm the sign of the lift holds).
#      Observed numbers are reported FIRST; any disattenuated value comes second.
#
# HONEST SCOPE: the anonymous comparators implemented here are TRADE-BASED ONLY.
# A wallet's VPIN, flow imbalance, size and intensity are all derivable from the
# trade tape alone with NO order book. The full order-book version of the
# comparator family (true OFI, queue position, book-depth VPIN) requires book
# reconstruction, which is a separate heavy step. So this test bounds
# non-recoverability against the trade-only information set; it does NOT yet rule
# out recovery from book microstructure. State this plainly wherever I3 is cited.
#
# numpy-only, no order book, reads ONE shared intermediate (quickwin_markouts.npz)
# produced by the expensive orchestrator pass. Do not parse raw data here.
# ---------------------------------------------------------------------------

import argparse
import json
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

# This object is scored at two windows on purpose: the headline one and the long
# companion kept for robustness. Both come from settings.py, so neither window is
# declared here and the pair cannot drift from the single source.

# -------------------- configuration --------------------
HERE = os.path.dirname(os.path.abspath(__file__))
# Located by panel_io rather than joined here, so the one place that knows where the
# markout panels live is the one place that has to change if they move.
NPZ_PATH = os.path.join(P.data_root(), "quickwin_markouts.npz")
MID_NPZ_PATH = os.path.join(P.data_root(), "quickwin_markouts_mid.npz")
TAKER_MAP_PATH = os.path.join(P.data_root(), "quickwin_taker_map.json")
RESULTS_PATH = os.path.join(HERE, "i3_results.json")
MID_RESULTS_PATH = os.path.join(HERE, "i3_nonrecoverability_mid_results.json")

COIN_CODES = H.coin_labels("quickwin")   # the map belongs to the FILE, not the project
# WHERE THE CUT BETWEEN THE HALVES COMES FROM. The two tuples are no longer typed: the
# cut is settings.split_early_late, applied to the span this file's inputs carry. What
# stays local is the SPAN, day-of-month 4 through 13, because that is a property of
# quickwin_markouts.npz and of nothing else; what moves to settings.py is WHERE the span
# divides, which is a project-wide decision and had no business being decided here.
#
# The rule reproduces the tuples this file used to type. Both inputs were opened and
# their day columns carry exactly 4..13, so split_early_late returns (4,5,6,7,8) and
# (9,10,11,12,13); no number in either results file moves. The tuples stay REQUESTS
# rather than the resolved halves, which is the distinction the block near present_days
# keeps: a day whose raw archive failed to download is absent from the input, and this
# file reports the truncation instead of quietly analysing a shorter half.
INPUT_DAY_SPAN = range(4, 14)       # day-of-month span of the quickwin intermediates
EARLY_DAYS, LATE_DAYS = H.split_early_late(INPUT_DAY_SPAN)
HORIZONS = (H.COMPANION_HORIZON_S, H.HEADLINE_HORIZON_S)
                                    # companion window first, then the headline one;
                                    # the order is the reporting order and nothing else.
                                    # It used to read "headline 60s first" here, which
                                    # has been wrong since the window was consolidated.
K_LIST = H.PERSISTENCE_FLOOR_FILLS  # min trades per wallet in EACH half; the declared
                                    # pair, because a wallet needs the count twice here
N_VPIN_BUCKETS = 50                 # equal-volume buckets for VPIN
VPIN_WINDOW = 50                    # rolling buckets for the VPIN running estimate
IMB_WINDOW = 25                     # rolling trades for signed-flow imbalance
N_FOLDS = 5                         # k-fold wallet split for OOS scoring
# Label-permutation null for the incremental lift, READ from settings.py and no longer
# typed here. A p reported AT the floor says only that no draw beat the observed lift, so
# every p carries a *_is_floor flag saying which of the two it is.
#
# The literal of 1000 that stood here cleared its bar and still had to go. Its floor was
# 1/1001 = 0.000999 against a corrected rank-one threshold of 0.05/48 = 0.001042, a margin
# of four percent. settings.PERM_FLOOR_MARGIN exists to forbid exactly that: a budget
# clearing the correction by four percent leaves every floored p on the boundary, where
# the verdict is decided by the last digit of the correction and not by the data.
N_PERM = H.N_PERM
WHALE_DROP_K = H.WHALE_DROP_K       # drop top-k wallets by NOTIONAL for the whale check;
                                    # the count is declared, the criterion is this file's
RIDGE_LAMBDA = 1e-6                 # tiny ridge for numerical stability of OLS
RNG_SEED = H.seed_for("i3_nonrecoverability_oos")
                                    # this run's seed, READ from settings.py and no
                                    # longer typed. The value is the same 20260619 this
                                    # file has always drawn from, so no number here
                                    # moves; settings.MASTER_SEED is 20260620, so the
                                    # fingerprint still records this as an override
FDR_ALPHA = H.FDR_ALPHA             # Benjamini-Hochberg FDR level over the cell family
# Pre-registered HEADLINE cell. The family of 12 cells (coin x horizon x K) is a
# robustness panel; this single cell is the one the claim stands on, registered
# BEFORE reading the placebo p-values so it cannot be cherry-picked.
HEADLINE_CELL = {"coin": "POOLED", "horizon_s": H.HEADLINE_HORIZON_S, "K": 50}


# -------------------- rank / correlation helpers (numpy-only) --------------------
def _rankdata(a):
    a = np.asarray(a, dtype=np.float64)
    order = np.argsort(a, kind="stable")
    ranks = np.empty(a.size, dtype=np.float64)
    sa = a[order]
    i, n = 0, a.size
    while i < n:
        j = i + 1
        while j < n and sa[j] == sa[i]:
            j += 1
        ranks[order[i:j]] = (i + j - 1) / 2.0 + 1.0
        i = j
    return ranks


def spearman(x, y):
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    n = x.size
    if n < 3:
        return float("nan")
    rx, ry = _rankdata(x), _rankdata(y)
    rx -= rx.mean()
    ry -= ry.mean()
    denom = np.sqrt((rx * rx).sum() * (ry * ry).sum())
    return float("nan") if denom == 0 else float((rx * ry).sum() / denom)


# -------------------- multiple-testing correction --------------------
# The correction is stats.benjamini_hochberg and is no longer written here. The copy
# that stood at this spot was the vectorised spelling of it -- sort ascending, raw
# q_i = p_i * m / rank, running minimum from the largest p downward, clipped to [0, 1],
# NaN carried through and left out of the family size -- and stats.py keeps that exact
# copy as _legacy_bh_vectorised so the two are run against each other on 200 random
# families with ties and untestable cells in its self-test. Measured on this file's own
# two families as well, twelve cells each, before the copy was removed: the q-values are
# bit-identical, so the consolidation moves no number here.
#
# What the module adds is the CUTOFF, which the local copy never returned. "Survives the
# correction" cannot be read without the bar it was judged against, and the bar is not a
# constant: it is alpha/m at rank one, and this work's families run from 4 cells to 448
# at one alpha. So the call site below keeps the block rather than only its q-values, and
# records the threshold beside the verdict.
#
# Nothing outside this file called the removed function. panel_analyze.py imports this
# module and its comment still says it uses the imported correction, but the code beneath
# that comment calls stats.benjamini_hochberg itself; the stale sentence is in a file this
# pass does not own.


# -------------------- linear model (numpy-only ridge-stabilised OLS) --------------------
def _fit_predict(x_fit, y_fit, x_eval):
    """Fit y ~ [1, X] on the fit fold, predict on the eval fold.

    Tiny ridge keeps the normal equations solvable when a predictor is degenerate
    on a fold. Returns predictions on x_eval (shape n_eval).
    """
    n_fit = x_fit.shape[0]
    Xf = np.column_stack([np.ones(n_fit), x_fit])
    Xe = np.column_stack([np.ones(x_eval.shape[0]), x_eval])
    p = Xf.shape[1]
    A = Xf.T @ Xf + RIDGE_LAMBDA * np.eye(p)
    b = Xf.T @ y_fit
    try:
        beta = np.linalg.solve(A, b)
    except np.linalg.LinAlgError:
        beta = np.linalg.lstsq(Xf, y_fit, rcond=None)[0]
    return Xe @ beta


def _oos_predictions(X, y, folds):
    """K-fold out-of-sample predictions for every wallet (each scored from a model
    fit on the OTHER folds). Returns the stacked held-out predictions and the
    matching held-out targets in fold order."""
    preds, actual = [], []
    for f in range(folds.max() + 1):
        eval_mask = folds == f
        fit_mask = ~eval_mask
        if fit_mask.sum() < (X.shape[1] + 2) or eval_mask.sum() < 1:
            # too few wallets to fit on this fold-out; fall back to fit-mean
            yhat = np.full(int(eval_mask.sum()), y[fit_mask].mean() if fit_mask.any() else 0.0)
        else:
            yhat = _fit_predict(X[fit_mask], y[fit_mask], X[eval_mask])
        preds.append(yhat)
        actual.append(y[eval_mask])
    return np.concatenate(preds), np.concatenate(actual)


def _oos_r2(actual, pred):
    """Out-of-sample R^2 against the actual mean (can be negative)."""
    actual = np.asarray(actual, dtype=np.float64)
    pred = np.asarray(pred, dtype=np.float64)
    ss_res = float(np.sum((actual - pred) ** 2))
    ss_tot = float(np.sum((actual - actual.mean()) ** 2))
    if ss_tot <= 0:
        return float("nan")
    return 1.0 - ss_res / ss_tot


# -------------------- anonymous trade-flow predictors (NO order book) --------------------
def _vpin_series(notional, is_buy):
    """VPIN-style toxicity via bulk-volume classification on equal-volume buckets.

    Easley, Lopez de Prado, O'Hara (2012): partition the volume axis into equal-
    volume buckets, classify each bucket's buy vs sell volume, VPIN = rolling mean
    of |V_buy - V_sell| / (V_buy + V_sell). Here, with no aggressor sign assumed,
    classification uses the recorded taker side (is_buy). Trade-tape-only by
    construction. Returns ONE running-VPIN value per TRADE (carried forward from
    the bucket the trade falls in), so it can be averaged to the wallet level.
    """
    n = notional.size
    out = np.full(n, np.nan, dtype=np.float64)
    if n == 0:
        return out
    total_vol = float(notional.sum())
    if total_vol <= 0:
        return out
    bucket_target = total_vol / N_VPIN_BUCKETS
    if bucket_target <= 0:
        return out
    cum = np.cumsum(notional)
    # bucket index of each trade by cumulative volume (cap at last bucket)
    bidx = np.minimum((cum / bucket_target).astype(np.int64), N_VPIN_BUCKETS - 1)
    n_buckets = int(bidx.max()) + 1
    buy_vol = np.bincount(bidx, weights=notional * is_buy, minlength=n_buckets)
    sell_vol = np.bincount(bidx, weights=notional * (1 - is_buy), minlength=n_buckets)
    tot = buy_vol + sell_vol
    with np.errstate(invalid="ignore", divide="ignore"):
        oi = np.abs(buy_vol - sell_vol) / np.where(tot > 0, tot, np.nan)
    # rolling mean of bucket order-imbalance -> running VPIN per bucket
    vpin_bucket = np.full(n_buckets, np.nan, dtype=np.float64)
    for k in range(n_buckets):
        lo = max(0, k - VPIN_WINDOW + 1)
        win = oi[lo:k + 1]
        win = win[~np.isnan(win)]
        if win.size:
            vpin_bucket[k] = float(win.mean())
    out = vpin_bucket[bidx]
    return out


def _rolling_signed_imbalance(is_buy):
    """Signed trade-flow imbalance over a rolling window of trades.

    imb_t = (sum buys - sum sells) / window, over the last IMB_WINDOW trades
    (expanding until the window fills). Trade-tape-only. Returns one value per
    trade; the wallet-level predictor is the mean of |imb| (toxic flow is
    persistently one-sided, so magnitude is the informative aggregate)."""
    n = is_buy.size
    if n == 0:
        return np.empty(0, dtype=np.float64)
    signed = (2 * is_buy - 1).astype(np.float64)      # +1 buy, -1 sell
    csum = np.cumsum(signed)
    out = np.empty(n, dtype=np.float64)
    for t in range(n):
        lo = max(0, t - IMB_WINDOW + 1)
        s = csum[t] - (csum[lo - 1] if lo > 0 else 0.0)
        out[t] = s / (t - lo + 1)
    return out


def _aggregate_features(taker_id, day, notional, is_buy, mo,
                        early_days, late_days, K):
    """Build the aligned per-wallet arrays for eligible wallets.

    Returns (wallet_ids, X_anon[n,4], hist_fe[n], target[n], tot_notional[n]).
    All anonymous features and the history FE are computed on the EARLY half;
    the target is the LATE-half mean markout.
    """
    early_set = set(early_days)
    late_set = set(late_days)
    valid = ~np.isnan(mo)
    is_early = np.array([d in early_set for d in day]) & valid
    is_late = np.array([d in late_set for d in day]) & valid

    uniq, inv = np.unique(taker_id, return_inverse=True)
    cnt_e = np.bincount(inv[is_early], minlength=uniq.size)
    cnt_l = np.bincount(inv[is_late], minlength=uniq.size)
    eligible = (cnt_e >= K) & (cnt_l >= K)
    elig_pos = np.where(eligible)[0]
    if elig_pos.size < (N_FOLDS + 2):
        return None

    # EARLY-half tape, ordered (stable) by wallet then by day so the rolling
    # anonymous predictors run along each wallet's own EARLY sequence.
    e_idx = np.where(is_early)[0]
    # order by (wallet, day) to keep each wallet's stream contiguous & time-ordered
    order = np.lexsort((day[e_idx], inv[e_idx]))
    e_idx = e_idx[order]
    e_inv = inv[e_idx]
    e_notional = notional[e_idx].astype(np.float64)
    e_is_buy = is_buy[e_idx].astype(np.float64)
    e_day = day[e_idx].astype(np.float64)
    e_mo = mo[e_idx].astype(np.float64)

    # per-wallet anonymous predictors (computed per wallet stream)
    n_w = uniq.size
    f_vpin = np.full(n_w, np.nan)
    f_imb = np.full(n_w, np.nan)
    f_size = np.full(n_w, np.nan)
    f_intensity = np.full(n_w, np.nan)
    hist_fe = np.full(n_w, np.nan)
    tot_notional = np.zeros(n_w)

    # iterate over contiguous wallet groups in the EARLY stream
    boundaries = np.where(np.diff(e_inv) != 0)[0] + 1
    starts = np.concatenate([[0], boundaries])
    ends = np.concatenate([boundaries, [e_inv.size]])
    for s, en in zip(starts, ends):
        w = e_inv[s]
        if not eligible[w]:
            continue
        seg_not = e_notional[s:en]
        seg_buy = e_is_buy[s:en]
        seg_day = e_day[s:en]
        seg_mo = e_mo[s:en]
        vpin = _vpin_series(seg_not, seg_buy)
        imb = _rolling_signed_imbalance(seg_buy.astype(np.int64))
        f_vpin[w] = float(np.nanmean(vpin)) if np.isfinite(vpin).any() else 0.0
        f_imb[w] = float(np.mean(np.abs(imb))) if imb.size else 0.0
        f_size[w] = float(np.mean(seg_not)) if seg_not.size else 0.0
        span = (seg_day.max() - seg_day.min()) + 1.0
        f_intensity[w] = seg_not.size / span if span > 0 else float(seg_not.size)
        hist_fe[w] = float(np.mean(seg_mo))
        tot_notional[w] = float(seg_not.sum())

    # LATE-half target: wallet mean markout
    l_idx = np.where(is_late)[0]
    l_inv = inv[l_idx]
    l_mo = mo[l_idx].astype(np.float64)
    s_sum = np.bincount(l_inv, weights=l_mo, minlength=n_w)
    s_cnt = np.bincount(l_inv, minlength=n_w)
    with np.errstate(invalid="ignore", divide="ignore"):
        target = np.where(s_cnt > 0, s_sum / np.where(s_cnt > 0, s_cnt, np.nan), np.nan)

    # also add LATE notional to whale ranking (whales = biggest overall players)
    l_not = notional[l_idx].astype(np.float64)
    tot_notional += np.bincount(l_inv, weights=l_not, minlength=n_w)

    keep = eligible & ~np.isnan(hist_fe) & ~np.isnan(target) \
        & ~np.isnan(f_vpin) & ~np.isnan(f_imb) & ~np.isnan(f_size) & ~np.isnan(f_intensity)
    pos = np.where(keep)[0]
    if pos.size < (N_FOLDS + 2):
        return None

    X_anon = np.column_stack([f_vpin[pos], f_imb[pos], f_size[pos], f_intensity[pos]])
    return (uniq[pos].astype(np.int64), X_anon, hist_fe[pos], target[pos],
            tot_notional[pos])


# -------------------- the incremental-lift test --------------------
def _standardise(X):
    """Column standardise (zero degenerate columns) for stable OLS."""
    mu = X.mean(axis=0)
    sd = X.std(axis=0)
    sd_safe = np.where(sd > 0, sd, 1.0)
    Xs = (X - mu) / sd_safe
    Xs[:, sd == 0] = 0.0
    return Xs


def incremental_lift(X_anon, hist_fe, target, rng):
    """Incremental OOS R^2 and Spearman of model B (anon + FE) over model A (anon).

    Both models are k-fold scored out-of-sample across wallets. Returns a dict.
    """
    n = target.size
    folds = rng.permutation(n) % N_FOLDS
    Xa = _standardise(X_anon)
    fe = hist_fe.reshape(-1, 1)
    fe_s = _standardise(fe)
    Xb = np.column_stack([Xa, fe_s])

    predA, actA = _oos_predictions(Xa, target, folds)
    predB, actB = _oos_predictions(Xb, target, folds)
    # actA and actB are the same wallets in the same fold order
    r2_a = _oos_r2(actA, predA)
    r2_b = _oos_r2(actB, predB)
    sp_a = spearman(actA, predA)
    sp_b = spearman(actB, predB)
    return {
        "n_wallets": int(n),
        "oos_r2_anon": r2_a,
        "oos_r2_anon_plus_fe": r2_b,
        "incremental_oos_r2": (r2_b - r2_a) if (r2_a == r2_a and r2_b == r2_b) else float("nan"),
        "oos_spearman_anon": sp_a,
        "oos_spearman_anon_plus_fe": sp_b,
        "incremental_spearman": (sp_b - sp_a) if (sp_a == sp_a and sp_b == sp_b) else float("nan"),
        "_folds": folds,
        "_Xa": Xa,
        "_target": target,
    }


def placebo_pvalue(Xa, target, hist_fe, observed_incr_r2, folds, rng, n_perm=N_PERM):
    """Permutation null: shuffle the wallet labels on the history FE, re-fit model
    B, and recompute the incremental OOS R^2. p = fraction of permutations whose
    incremental lift >= the observed one. p-floor = 1/(n_perm+1).

    WHY THIS COUNT IS NOT stats.permutation_p, and it is the only count in this file's
    group that is not. Two of the three things that could differ are the same on both
    sides: the side is one-sided at `null >= observed - tol`, and the slack is the
    absolute 1e-12 this test has always applied, which the module accepts as abs_tol.

    The third is a real disagreement about WHAT A FAILED DRAW IS, and it is a different
    denominator rather than a different spelling. A draw whose model B returns no R^2
    becomes minus infinity here and STAYS IN THE DENOMINATOR, which is the requested
    budget; the module DROPS such a draw and divides by the count that came back finite.
    On a run where every draw succeeds the two give the identical p, and every run of
    this file so far is such a run -- the held-out targets are the same in the permuted
    fit as in the observed one, so the total sum of squares is the same positive number
    and the only route to no R^2 is a fold whose ridge solve produced no number. But
    "identical whenever nothing fails" is not the same property as identical, and the
    module offers no argument for keeping a failed draw in the denominator, so adopting
    it would be a change of policy carried inside a change of code.

    That decision is worth taking on its own and is not taken here. What the module DOES
    own for this file is the multiplicity correction and the budget check, both called
    below, so the two procedures that cross cell boundaries have one home each.
    """
    if observed_incr_r2 != observed_incr_r2:
        return float("nan")
    predA, actA = _oos_predictions(Xa, target, folds)
    r2_a = _oos_r2(actA, predA)
    cnt = 0
    for _ in range(n_perm):
        fe_perm = rng.permutation(hist_fe).reshape(-1, 1)
        fe_s = _standardise(fe_perm)
        Xb = np.column_stack([Xa, fe_s])
        predB, actB = _oos_predictions(Xb, target, folds)
        r2_b = _oos_r2(actB, predB)
        incr = (r2_b - r2_a) if (r2_b == r2_b and r2_a == r2_a) else -np.inf
        if incr >= observed_incr_r2 - 1e-12:
            cnt += 1
    return (cnt + 1) / (n_perm + 1)


def whale_robust_check(X_anon, hist_fe, target, tot_notional, observed_incr_r2, rng):
    """Drop the top-k wallets by total notional and confirm the incremental lift
    is POSITIVE and keeps its (positive) sign. Returns (incr_r2_no_whales, flag).

    The flag is the honest robustness verdict, and it is only ever a string/bool a
    reader can trust for the claim:
      True    -> the incremental lift is positive AND stays positive without whales
                 (genuinely whale-robust support for the FE).
      False   -> the FULL-sample incremental lift is positive but flips/dies once
                 whales are dropped (positive lift NOT robust).
      "n/a"   -> the full-sample incremental lift is <= 0 (or undefined), so there
                 is no positive lift to be robust about. A negative-lift cell must
                 NOT read as supporting the non-recoverability claim, so we refuse
                 to emit a bare True/False that could be misread as support.
    """
    # No positive lift to defend -> the whale check is not applicable.
    if observed_incr_r2 != observed_incr_r2 or observed_incr_r2 <= 0:
        return float("nan"), "n/a"
    if target.size <= WHALE_DROP_K + N_FOLDS + 2:
        return float("nan"), "n/a"
    drop = np.argsort(tot_notional)[::-1][:WHALE_DROP_K]
    keep = np.ones(target.size, dtype=bool)
    keep[drop] = False
    res = incremental_lift(X_anon[keep], hist_fe[keep], target[keep], rng)
    incr = res["incremental_oos_r2"]
    # robust only if the no-whale lift is itself POSITIVE (same sign as the
    # positive full-sample lift). A no-whale lift <= 0 means whales carried it.
    robust = bool(incr == incr and incr > 0)
    return incr, robust


# -------------------- side flag (real field preferred, proxy fallback) --------------------
def _derive_is_buy(start_pos, is_open, taker_id, day):
    """FALLBACK trade-tape-only BUY/SELL flag for the anonymous flow predictors.

    Used ONLY when the intermediate does not carry an explicit taker side. When
    present, npz["taker_side"] (1 = buy "B", 0 = sell "A") is the real aggressor
    flag and is used directly (see main()); this proxy is the backstop.

    The proxy uses start_pos (signed position before the trade) and is_open (open
    vs close). A consistent trade-tape-only convention: a wallet whose signed
    position increases is buying, decreases is selling. We approximate the
    per-trade side by the sign of the change in start_pos along each wallet's
    time-ordered stream; the final trade of a stream inherits the previous sign.
    This is a SIDE PROXY, not the true aggressor flag, and only feeds the
    anonymous comparator (whose whole point is to be the weak,
    recoverable-from-tape baseline). Documented as such.
    """
    n = start_pos.size
    is_buy = np.ones(n, dtype=np.int64)   # default buy
    order = np.lexsort((day, taker_id))
    sp = start_pos[order]
    tid = taker_id[order]
    same = np.concatenate([[False], tid[1:] == tid[:-1]])
    d = np.zeros(n, dtype=np.float64)
    d[1:] = sp[1:] - sp[:-1]
    d[~same] = 0.0                        # first trade of each wallet: unknown
    sign = np.where(d > 0, 1, np.where(d < 0, 0, -1))
    # carry-forward last known sign within each wallet; unknown leading -> buy(1)
    last = 1
    out_ord = np.empty(n, dtype=np.int64)
    for i in range(n):
        if not same[i]:
            last = 1
        if sign[i] != -1:
            last = sign[i]
        out_ord[i] = last
    is_buy[order] = out_ord
    return is_buy


# -------------------- main --------------------
def main(source="trade"):
    t0 = artifact.start_clock()
    # --source selects the markout reference series. 'trade' (default) reads the
    # trade-print markouts from quickwin_markouts.npz and writes i3_results.json
    # (UNCHANGED legacy behaviour). 'mid' reads the L2 mid-price markouts
    # (mo*_mid) from quickwin_markouts_mid.npz and writes the separate
    # i3_nonrecoverability_mid_results.json, leaving the trade output untouched.
    # The two column names are asked for by ROLE (headline, companion), never typed, so
    # neither can drift from settings.py. The local names say role for the same reason:
    # a variable called mo60_key would state a window that only settings.py decides.
    # The two arms differ only in which panel they read, so the arm is now one name --
    # the panel kind -- and every window, lens and path below follows from it rather
    # than being spelled twice.
    kind = "mid" if source == "mid" else "print"
    npz_path = MID_NPZ_PATH if source == "mid" else NPZ_PATH
    results_path = MID_RESULTS_PATH if source == "mid" else RESULTS_PATH
    companion_key = P.score_col(kind, H.COMPANION_HORIZON_S)
    headline_key = P.score_col(kind)

    # panel_io names the producer to run when the file is absent, so that message is
    # written once for the whole tree. Which arm reads which file is declared to build.py
    # by hand in build_declarations.py, because the fold takes one branch of this
    # selection and would otherwise leave the book-mid half of the question invisible.
    P.require_present(kind, npz_path)
    z = np.load(npz_path, allow_pickle=False)
    # One refusal before any of the work, worded the same way as everywhere else, naming
    # the column asked for and the columns the file holds.
    P.require_columns(z, kind, "taker_id", "coin", "day", "notional", "is_open",
                      "start_pos", companion_key, headline_key)
    taker_id = z["taker_id"].astype(np.int64)
    coin = z["coin"].astype(np.int8)
    day = z["day"].astype(np.int64)
    # The two scored columns as float64, each read through the panel's own lens, so the
    # arm cannot ask the book-mid panel for a trade-print column or the reverse.
    mo_by_h = {H.COMPANION_HORIZON_S: P.score(z, kind, H.COMPANION_HORIZON_S),
               H.HEADLINE_HORIZON_S: P.score(z, kind)}
    notional = z["notional"].astype(np.float64)
    is_open = z["is_open"].astype(np.int64)
    start_pos = z["start_pos"].astype(np.float64)

    # quickwin_taker_map.json is a WRAPPER: {"_direction": ..., "map": {hex: int}}.
    # It used to be the flat {hex: int} dict, and the count below still read len() of
    # the top level, so a re-run reported 2 mapped counterparties instead of 45,849.
    # The committed artifact carried the correct figure only because it predates the
    # format change. Unwrap explicitly, tolerating either shape.
    taker_map = {}
    if os.path.exists(TAKER_MAP_PATH):
        with open(TAKER_MAP_PATH) as fh:
            _raw = json.load(fh)
        taker_map = _raw.get("map", _raw) if isinstance(_raw, dict) else {}

    rng = np.random.default_rng(RNG_SEED)

    # Resolve the days ACTUALLY present in the intermediate. The configured
    # EARLY/LATE windows are REQUESTS; days 11-13 (etc.) may be missing if their
    # raw archives failed to download. Report the resolved-present days, not the
    # hardcoded request, so the metadata never claims a half it did not analyse.
    present_days = set(int(d) for d in np.unique(day))
    early_present = sorted(d for d in EARLY_DAYS if d in present_days)
    late_present = sorted(d for d in LATE_DAYS if d in present_days)
    truncation_issues = []
    if len(early_present) < len(EARLY_DAYS):
        missing = sorted(set(EARLY_DAYS) - present_days)
        truncation_issues.append(
            f"EARLY half TRUNCATED: requested {list(EARLY_DAYS)}, resolved "
            f"{early_present}; missing days {missing} absent from intermediate.")
    if len(late_present) < len(LATE_DAYS):
        missing = sorted(set(LATE_DAYS) - present_days)
        truncation_issues.append(
            f"LATE half TRUNCATED: requested {list(LATE_DAYS)}, resolved "
            f"{late_present}; missing days {missing} absent from intermediate. "
            f"A short late half is underpowered; read incremental cells with care.")

    # Buy/sell flag for the anonymous VPIN / signed-imbalance predictors. Prefer
    # the REAL aggressor side from the intermediate (taker_side: 1 = buy "B",
    # 0 = sell "A"); fall back to the start_pos-sign proxy only if absent.
    if "taker_side" in z.files:
        is_buy_all = (z["taker_side"].astype(np.int64) != 0).astype(np.int64)
        side_source = "taker_side (real aggressor flag from intermediate)"
    else:
        is_buy_all = _derive_is_buy(start_pos, is_open, taker_id, day)
        side_source = "start_pos-sign proxy (taker_side absent)"
    print(f"[i3] buy/sell flag source: {side_source}")

    # What every number in this file was computed under, with an explicit override for
    # each setting the run does not take from the declaration. It used to be written
    # into results["scope"] and mirrored again into _meta, which is one record in two
    # places; artifact.write is now the single place that stamps it.
    settings_used = dict(
        h=H.HEADLINE_HORIZON_S,
        lens=("mid" if source == "mid" else "print"),
        master_seed=RNG_SEED,
        n_perm=N_PERM,
        n_boot=None,
        rank_floor_fills=None,
        horizons_scored_s=list(HORIZONS),
        # BUILT from the tuples the run resolved, never typed. The string that stood
        # here read "day-of-month tuples 4-8 / 9-13", which stopped being true when the
        # cut moved to settings.split_early_late a few lines below INPUT_DAY_SPAN: the
        # numbers it named were still right, and the source it named was not. A caption
        # inside the fingerprint is what a reader consults to learn what a run was
        # computed under, so one that names the wrong source is worse than none.
        early_late_split=(f"settings.split_early_late over the input day span "
                          f"{min(INPUT_DAY_SPAN)}-{max(INPUT_DAY_SPAN)}: early "
                          f"{list(EARLY_DAYS)}, late {list(LATE_DAYS)}"),
        whale_drop_criterion="notional",
        p_floor=H.p_floor(N_PERM),
        overrides_note=(
            "master_seed 20260619 not settings.MASTER_SEED 20260620; n_perm is "
            "the declared budget, read from settings.py and no longer typed "
            "here, and a p at the floor is still a bound rather than a "
            "measurement, which placebo_p_is_floor records; no bootstrap "
            "is drawn, so n_boot does not apply; eligibility is the per-half floor "
            "settings.PERSISTENCE_FLOOR_FILLS (50, 100), not the ranking-window "
            "RANK_FLOOR_FILLS, so that field is not applicable here; the SPAN of days "
            "is local because it is a property of the quickwin intermediates and of "
            "nothing else, while the CUT inside that span is settings.split_early_late "
            "and is no longer a pair of typed tuples; whales are dropped by NOTIONAL, "
            "which answers 'is this a "
            "volume artifact'; the headline window carries the claim and the long "
            "companion is reported beside it, first only in print order"),)

    results = {
        "object": "I3 - out-of-sample non-recoverability of per-counterparty toxicity",
        "scope": {
            "early_days_requested": list(EARLY_DAYS),
            "late_days_requested": list(LATE_DAYS),
            "early_days": early_present,   # ACTUAL resolved days in the npz
            "late_days": late_present,     # ACTUAL resolved days in the npz
            "horizons_s": list(HORIZONS), "K_list": list(K_LIST),
            "n_folds": N_FOLDS, "n_perm": N_PERM, "p_floor": H.p_floor(N_PERM),
            "p_floor_note": (
                f"a budget of {N_PERM} draws cannot express a p below "
                f"{H.p_floor(N_PERM):.6f}; every placebo_p carries placebo_p_is_floor "
                "saying whether it is a measurement or the budget's floor"),
            "whale_drop_k": WHALE_DROP_K, "n_vpin_buckets": N_VPIN_BUCKETS,
            "comparator_scope": "TRADE-TAPE-ONLY anonymous metrics (VPIN by bulk-"
            "volume classification, rolling signed-flow imbalance, mean size, trade "
            "intensity). NO order book. The full OFI/queue/book-VPIN comparator "
            "needs book reconstruction (a later heavy step); I3 bounds "
            "non-recoverability against the trade-only information set only.",
            "claim": "history FE (wallet EARLY-half mean markout, observable only "
            "via on-chain identity resolution) adds OUT-OF-SAMPLE lift over "
            "anonymous trade-flow metrics; placebo (label-shuffled FE) must kill it.",
            "n_takers_mapped": len(taker_map),
            "side_source": side_source,
            "markout_source": source,   # 'trade' (trade-print) or 'mid' (L2 mid)
        },
        "by_coin": [],
        "pooled": [],
        "issues": list(truncation_issues),
    }
    if truncation_issues:
        for msg in truncation_issues:
            print(f"[i3] WARNING: {msg}")

    # groups: each coin separately, then pooled (coin==-1 sentinel = all rows)
    groups = [(0, "BTC"), (1, "ETH"), (-1, "POOLED")]

    for code, label in groups:
        if code == -1:
            sel = np.ones(taker_id.size, dtype=bool)
        else:
            sel = coin == code
        if sel.sum() == 0:
            results["issues"].append(f"{label}: no rows")
            continue

        g_taker = taker_id[sel]
        g_day = day[sel]
        g_not = notional[sel]
        g_isbuy = is_buy_all[sel]

        for h in HORIZONS:
            g_mo = mo_by_h[h][sel]
            for K in K_LIST:
                built = _aggregate_features(
                    g_taker, g_day, g_not, g_isbuy, g_mo,
                    early_present, late_present, K)
                row = {"coin": label, "horizon_s": h, "K": K}
                if built is None:
                    row.update({
                        "n_wallets": 0,
                        "incremental_oos_r2": None,
                        "incremental_spearman": None,
                        "placebo_p": None,
                        "placebo_p_is_floor": False,
                        "whale_robust": "n/a",
                        "interpretation": None,
                        "note": "too few eligible wallets for OOS folds",
                    })
                    (results["pooled"] if code == -1 else results["by_coin"]).append(row)
                    continue

                wallet_ids, X_anon, hist_fe, target, tot_not = built
                lift = incremental_lift(X_anon, hist_fe, target,
                                        np.random.default_rng(RNG_SEED + K + h))
                folds = lift.pop("_folds")
                Xa = lift.pop("_Xa")
                _ = lift.pop("_target")

                p_perm = placebo_pvalue(
                    Xa, target, hist_fe, lift["incremental_oos_r2"],
                    folds, np.random.default_rng(RNG_SEED * 3 + K + h))
                incr_no_whale, whale_verdict = whale_robust_check(
                    X_anon, hist_fe, target, tot_not,
                    lift["incremental_oos_r2"],
                    np.random.default_rng(RNG_SEED * 7 + K + h))

                # disattenuation: the FE is itself a noisy estimate of the latent
                # wallet toxicity. The observed incremental Spearman is reported
                # FIRST; a reliability-corrected value is reported SECOND. Without
                # an in-loop split-half reliability here we expose the hook only.
                row.update({
                    "n_wallets": int(lift["n_wallets"]),
                    "oos_r2_anon": lift["oos_r2_anon"],
                    "oos_r2_anon_plus_fe": lift["oos_r2_anon_plus_fe"],
                    "incremental_oos_r2": lift["incremental_oos_r2"],
                    "oos_spearman_anon": lift["oos_spearman_anon"],
                    "oos_spearman_anon_plus_fe": lift["oos_spearman_anon_plus_fe"],
                    "incremental_spearman": lift["incremental_spearman"],
                    "placebo_p": p_perm,
                    # Is this p a measurement, or the smallest value the budget can
                    # express? A reader cannot tell from the number alone, and the
                    # difference decides whether the cell can clear a corrected
                    # threshold at all.
                    "placebo_p_is_floor": bool(H.p_is_floored(p_perm, N_PERM))
                    if (p_perm is not None and p_perm == p_perm) else False,
                    "incremental_oos_r2_no_whales": incr_no_whale,
                    "whale_robust": whale_verdict,
                })

                # Per-cell honesty note: a NEGATIVE (or near-zero) incremental R^2
                # with a POSITIVE incremental Spearman is an UNDERPOWERED /
                # INCONCLUSIVE cell, NOT evidence that toxicity is recoverable.
                # R^2 is a squared-error (level) metric that a short late half and
                # a few outliers destabilise; the rank lift still ordering wallets
                # correctly says the identity signal has not vanished. Flag it so a
                # reader cannot read a negative incremental R^2 as "recoverable".
                incr_r2 = row["incremental_oos_r2"]
                incr_sp = row["incremental_spearman"]
                short_late = len(late_present) < len(LATE_DAYS)
                if (incr_r2 is not None and incr_r2 == incr_r2 and incr_r2 <= 0
                        and incr_sp is not None and incr_sp == incr_sp
                        and incr_sp > 0):
                    row["interpretation"] = (
                        "INCONCLUSIVE/UNDERPOWERED, not a recoverability finding: "
                        f"incremental R^2 {incr_r2:+.4f} <= 0 while incremental "
                        f"Spearman {incr_sp:+.4f} > 0. The positive rank lift means "
                        "the wallet-history FE still orders future toxicity out of "
                        "sample; the non-positive R^2 is a level-fit artefact"
                        + (" amplified by a TRUNCATED/short late half"
                           if short_late else "")
                        + ". Do NOT read this cell as evidence that toxicity is "
                        "recoverable from the anonymous trade tape.")
                else:
                    row["interpretation"] = None

                (results["pooled"] if code == -1 else results["by_coin"]).append(row)

                print(f"[i3] {label:<6} h={h:>2}s K={K:>3} "
                      f"n={row['n_wallets']:>5} "
                      f"incrR2={_fmt(row['incremental_oos_r2'])} "
                      f"incrSp={_fmt(row['incremental_spearman'])} "
                      f"placebo_p={_fmt(p_perm)} "
                      f"whale_ok={row['whale_robust']}")
                if row.get("interpretation"):
                    print(f"[i3]   -> INCONCLUSIVE cell (incrR2<=0 & incrSp>0): "
                          f"underpowered, NOT a recoverability finding.")

    # ----------------------------------------------------------------------
    # MULTIPLE-TESTING CORRECTION over the FULL family of cells.
    #
    # I3 reports significance across a family of coin x horizon x K cells, each
    # with its own placebo p-value. Reading the significant cells without an FDR
    # correction is a referee-kill: with several placebo_p near 1.0 in the same
    # family, some cell will look significant by chance. We apply Benjamini-
    # Hochberg over EVERY cell that produced a testable placebo p (None/NaN cells
    # are excluded from the family size m), attach bh_qvalue + survives_fdr to
    # each, then summarise how many and which survive.
    # ----------------------------------------------------------------------
    all_cells = results["by_coin"] + results["pooled"]
    family_p = []
    for r in all_cells:
        p = r.get("placebo_p")
        family_p.append(float("nan") if (p is None or p != p) else float(p))
    fdr = stats.benjamini_hochberg(
        family_p, alpha=FDR_ALPHA,
        family="i3 non-recoverability cells: coin (BTC, ETH, POOLED) x horizon x "
               "wallet floor K, per-coin and pooled")
    qvals = np.array([np.nan if v is None else float(v) for v in fdr["q"]],
                     dtype=np.float64)
    m_tested = int(fdr["family_size"])
    survivors = []
    for r, q in zip(all_cells, qvals):
        if q != q:                     # NaN -> no testable placebo p for this cell
            r["bh_qvalue"] = None
            r["survives_fdr"] = False
        else:
            r["bh_qvalue"] = float(q)
            # A q is p * m / rank, so a q sitting on the permutation floor means the p was
            # floored AND the cell held the largest rank. Flagged for the same reason the p
            # is: it is a property of the budget, not of the effect.
            r["bh_qvalue_at_p_floor"] = bool(H.p_is_floored(q, N_PERM))
            r["survives_fdr"] = bool(q <= FDR_ALPHA)
            if r["survives_fdr"]:
                survivors.append({"coin": r["coin"], "horizon_s": r["horizon_s"],
                                  "K": r["K"], "placebo_p": r.get("placebo_p"),
                                  "placebo_p_is_floor": bool(r.get("placebo_p_is_floor")),
                                  "bh_qvalue": float(q)})

    # Pre-registered HEADLINE cell: locate it and report whether it survives FDR.
    headline = None
    for r in all_cells:
        if (r["coin"] == HEADLINE_CELL["coin"]
                and r["horizon_s"] == HEADLINE_CELL["horizon_s"]
                and r["K"] == HEADLINE_CELL["K"]):
            headline = r
            break
    headline_block = {
        "pre_registered_cell": dict(HEADLINE_CELL),
        "rationale": "Pre-registered BEFORE reading placebo p-values: the pooled "
        "10s K=50 cell is the single cell the non-recoverability claim stands on; "
        "the remaining 11 cells are a robustness panel, not independent confirmations.",
        "found": headline is not None,
        "placebo_p": (headline.get("placebo_p") if headline else None),
        "placebo_p_is_floor": (bool(headline.get("placebo_p_is_floor"))
                               if headline else False),
        "bh_qvalue": (headline.get("bh_qvalue") if headline else None),
        "survives_fdr": (bool(headline.get("survives_fdr")) if headline else False),
        "incremental_oos_r2": (headline.get("incremental_oos_r2") if headline else None),
        "incremental_spearman": (headline.get("incremental_spearman") if headline else None),
    }

    # Survivors BY WINDOW AND BY K, counted from the cells rather than asserted. The
    # previous note here read "the inconclusive 60s and K=100 cells fail BH-FDR and the
    # strong 10s cells survive", which the committed artifact contradicts: four of the six
    # long-companion cells survive and two headline cells do not. A caption that states a
    # pattern goes stale the moment the numbers move, so the pattern is computed.
    by_window = {}
    for r in all_cells:
        key = f"h{r['horizon_s']}s_K{r['K']}"
        slot = by_window.setdefault(key, {"n_cells": 0, "n_survivors": 0,
                                          "n_p_at_floor": 0})
        slot["n_cells"] += 1
        slot["n_survivors"] += int(bool(r.get("survives_fdr")))
        slot["n_p_at_floor"] += int(bool(r.get("placebo_p_is_floor")))
    n_floored = sum(1 for r in all_cells if r.get("placebo_p_is_floor"))

    results["family"] = {
        "method": "Benjamini-Hochberg FDR over the cell family (coin x horizon x K)",
        "procedure": fdr["procedure"],
        "procedure_note": fdr["method"],
        "fdr_alpha": FDR_ALPHA,
        # The BAR the q-values were judged against. The local correction this file used
        # to carry returned q and nothing else, so "survives_fdr" below stood without
        # the number it was compared to. The threshold is not a constant: it falls with
        # the family size, and the same p corrected over 4 cells and over 448 gives two
        # verdicts. rank1_threshold is what a single cell has to clear on its own, and
        # it is the quantity the permutation budget in settings.py is sized for.
        "threshold": fdr["threshold"],
        "threshold_meaning": fdr["threshold_meaning"],
        "rank1_threshold": fdr["rank1_threshold"],
        "smallest_p": fdr["smallest_p"],
        # Whether a p from this budget could clear the rank-one bar AT ALL. A budget
        # too small for its family fails silently, by reporting a floored p that the
        # correction then rejects however strong the effect is.
        "budget_check": stats.budget_check(N_PERM, m_tested, alpha=FDR_ALPHA),
        "n_cells_total": len(all_cells),
        "n_cells_tested": m_tested,        # cells with a non-null placebo p (family size m)
        "n_cells_untestable": len(all_cells) - m_tested,
        "n_survivors": len(survivors),
        "survivors": survivors,
        "survivors_by_window_and_K": by_window,
        "n_cells_with_p_at_floor": n_floored,
        "note": "Cells with a null/NaN placebo p (too few wallets, or no positive "
        "lift) are excluded from the family size m and never 'survive'. Which windows "
        "and which K survive is NOT asserted here: read survivors_by_window_and_K, "
        "which is counted from the cells of this run. n_cells_with_p_at_floor is how "
        f"many cells report the {N_PERM}-draw floor {H.p_floor(N_PERM):.6f} rather than "
        "a measured p; for those cells the p says only that no draw beat the observed "
        "lift, and the q inherits that.",
    }
    results["headline"] = headline_block

    results["_meta"] = {"rng_seed": RNG_SEED, "markout_source": source}

    # What the numbers cover. Eligibility is the PER-HALF floor, not the ranking-window
    # floor, so the population names it; the window names the two disjoint halves by
    # the days actually resolved in the input rather than the days requested.
    scope = {
        "population": (f"{len(taker_map):,} mapped counterparties over the fills of "
                       f"the {'book-mid' if source == 'mid' else 'trade-print'} panel; "
                       "a wallet enters a cell only when it clears that cell's "
                       "per-half fill floor in BOTH halves, and the folds are cut "
                       "over wallets so no wallet is scored on its own rows"),
        "window": (f"early days {list(early_present)} against late days "
                   f"{list(late_present)}, resolved from the days actually present "
                   "in the input rather than the day-of-month tuples requested"),
        "coins": [COIN_CODES[c] for c in sorted(COIN_CODES)],
    }

    # The output name and directory still come from the results_path this run chose,
    # so a caller that redirects the module constant redirects the whole write.
    artifact.write(os.path.basename(results_path), results,
                   script=__file__, inputs=[npz_path, TAKER_MAP_PATH], scope=scope,
                   settings=settings_used, started=t0,
                   out_dir=os.path.dirname(results_path))

    _print_summary(results, results_path)


def _fmt(v):
    if v is None:
        return "n/a"
    if isinstance(v, float) and v != v:
        return "nan"
    return f"{v:+.4f}" if isinstance(v, float) else str(v)


def _print_summary(results, results_path=RESULTS_PATH):
    print("\n" + "=" * 80)
    print("OBJECT I3 - OOS NON-RECOVERABILITY OF PER-COUNTERPARTY TOXICITY - SUMMARY")
    print("=" * 80)
    print("  comparator info set = TRADE-TAPE-ONLY (VPIN / flow-imbalance / size /")
    print("  intensity). NO order book. Book-VPIN/OFI/queue version is a later step.")
    print("-" * 80)
    sc = results.get("scope", {})
    early_res = sc.get("early_days", list(EARLY_DAYS))
    late_res = sc.get("late_days", list(LATE_DAYS))
    print(f"  EARLY days {early_res} -> LATE days {late_res} "
          f"(resolved-present, not requested); "
          f"{N_FOLDS}-fold wallet OOS; {N_PERM} placebo shuffles "
          f"(p-floor={H.p_floor(N_PERM):.6f}).")
    print("  A p AT the floor means no draw beat the observed lift - a statement about")
    print("  the budget, not a measured p. The 'floor' column marks those cells.")
    if results.get("issues"):
        for msg in results["issues"]:
            print(f"  [!] {msg}")
    print("-" * 80)
    header = (f"  {'coin':<6} {'h(s)':>4} {'K':>4} {'n_wal':>6} "
              f"{'incrR2':>9} {'incrSp':>9} {'placebo_p':>10} {'floor':>5} "
              f"{'whale_ok':>9} {'flag':>6}")
    any_inconclusive = False
    for block, name in ((results["by_coin"], "PER-COIN"), (results["pooled"], "POOLED")):
        if not block:
            continue
        print(f"  [{name}]")
        print(header)
        for r in block:
            flag = "INCONC" if r.get("interpretation") else ""
            if flag:
                any_inconclusive = True
            print(f"  {r['coin']:<6} {r['horizon_s']:>4} {r['K']:>4} "
                  f"{r.get('n_wallets', 0):>6} "
                  f"{_fmt(r.get('incremental_oos_r2')):>9} "
                  f"{_fmt(r.get('incremental_spearman')):>9} "
                  f"{_fmt(r.get('placebo_p')):>10} "
                  f"{('yes' if r.get('placebo_p_is_floor') else ''):>5} "
                  f"{str(r.get('whale_robust', False)):>9} "
                  f"{flag:>6}")
    print("-" * 80)
    print("  READING: incremental lift > 0 with a small placebo_p (<= ~0.05) and a")
    print("  whale-robust sign means the wallet history FE carries OOS information")
    print("  the anonymous trade-flow metrics do NOT recover -> toxicity is")
    print("  NON-RECOVERABLE from the trade tape, observable only via on-chain")
    print("  counterparty identity. A near-zero lift or large placebo_p means the")
    print("  anonymous metrics already capture it (recoverable). Observed numbers")
    print("  reported first; any disattenuated value would be the second figure.")
    print("  whale_ok: True = positive lift survives dropping top-k whales; False =")
    print("  positive lift dies/flips without whales; n/a = no positive lift to test.")
    if any_inconclusive:
        print("-" * 80)
        print("  [!] INCONC cells: incremental R^2 <= 0 BUT incremental Spearman > 0.")
        print("      These are UNDERPOWERED / INCONCLUSIVE (level-fit unstable on a")
        print("      short or noisy late half) - the positive rank lift shows the")
        print("      identity signal has NOT vanished. Do NOT read a negative")
        print("      incremental R^2 here as evidence toxicity is recoverable.")

    fam = results.get("family")
    if fam:
        print("-" * 80)
        print(f"  MULTIPLE-TESTING (Benjamini-Hochberg FDR, alpha={fam['fdr_alpha']}):")
        print(f"    family = {fam['n_cells_tested']} testable of "
              f"{fam['n_cells_total']} cells "
              f"({fam['n_cells_untestable']} untestable, excluded from m).")
        print(f"    survivors (q <= {fam['fdr_alpha']}): {fam['n_survivors']}")
        for s in fam["survivors"]:
            print(f"      - {s['coin']:<6} h={s['horizon_s']:>2}s K={s['K']:>3} "
                  f"placebo_p={_fmt(s['placebo_p'])} q={_fmt(s['bh_qvalue'])}")
        if not fam["survivors"]:
            print("      (none)")
    hl = results.get("headline")
    if hl:
        print("-" * 80)
        c = hl["pre_registered_cell"]
        verdict = "SURVIVES" if hl["survives_fdr"] else "does NOT survive"
        print(f"  PRE-REGISTERED HEADLINE: {c['coin']} h={c['horizon_s']}s "
              f"K={c['K']} -> {verdict} FDR "
              f"(placebo_p={_fmt(hl['placebo_p'])}, q={_fmt(hl['bh_qvalue'])}, "
              f"incrR2={_fmt(hl['incremental_oos_r2'])}, "
              f"incrSp={_fmt(hl['incremental_spearman'])}).")
        print("  The remaining 11 cells are a ROBUSTNESS PANEL, not independent claims.")
    print("=" * 80)
    print(f"  results -> {os.path.basename(results_path)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="I3 OOS non-recoverability test.")
    ap.add_argument("--source", choices=("trade", "mid"), default="trade",
                    help="markout reference: 'trade' (default, reads "
                         "quickwin_markouts.npz -> i3_results.json) or 'mid' "
                         "(reads quickwin_markouts_mid.npz mo*_mid -> "
                         "i3_nonrecoverability_mid_results.json).")
    args = ap.parse_args()
    main(source=args.source)
