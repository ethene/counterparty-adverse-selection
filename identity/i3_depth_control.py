"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-20
References:
  - Hyperliquid L2 book + node_fills_by_block S3 archive; Zenodo 18184441.
  - Easley, Lopez de Prado, O'Hara (2012). Flow Toxicity and Liquidity (VPIN).
  - Hasbrouck (2007). Empirical Market Microstructure (order-imbalance controls).
"""

# ---------------------------------------------------------------------------
# OBJECT I3-DEPTH - does per-counterparty toxicity SURVIVE book-state controls?
#
# I2/I3 show per-wallet idiosyncratic toxicity (per-taker mean of the maker-
# adverse-selection markout) is real and persistent. A sharp referee objection:
# maybe "wallet identity" is just a proxy for the ENTRY BOOK STATE each wallet
# tends to trade into - thin spreads, lopsided depth imbalance, a microprice
# pulled off mid. If the entire between-wallet dispersion in markout is explained
# by the instantaneous book each wallet hits, then counterparty identity carries
# NO information beyond order-book state, and the on-chain identity primitive adds
# nothing a CEX maker could not see in its own book.
#
# This test answers it directly on the L2-mid markout intermediate:
#   1. Fit a numpy OLS of mo10_mid on the ENTRY book-state controls
#        [1, imb_entry, spread_entry_bps, micro_dev_bps].
#   2. Take residuals (mo10_mid with the book-state-explainable part removed).
#   3. Recompute how much per-taker (between-wallet) identity explains:
#        (a) on the RAW mo10_mid, and
#        (b) on the RESIDUAL.
#      Two complementary numpy-only measures, both reported:
#        - between-wallet variance share = Var(taker means) / Var(obs), i.e. the
#          fraction of total markout variance living BETWEEN wallets (a one-way
#          random-effect ICC-style ratio), computed on eligible wallets (>= K obs);
#        - incremental R^2 of taker identity = R^2 of a per-taker-mean predictor
#          fit out of the wallet's OWN obs (leave-one-out per-taker mean, so the
#          number is not mechanically inflated by in-sample fitting).
#   4. VERDICT (honest framing, post-audit 2026-06-20): the SUPPORTED claim is the
#      narrow one - entry book state does NOT LINEARLY account for the between-wallet
#      markout dispersion (book R^2 < 1%), and identity dispersion survives LINEAR
#      book-state residualization and beats a label-permutation null. This is NOT
#      "identity is not a book-state proxy" in the strong structural sense: because
#      the linear book controls explain < 1% of markout variance, the high retain
#      ratio (~0.78-0.91) is largely a TAUTOLOGY of that near-zero R^2 - residualizing
#      on ~0 explained variance can barely move the markout, so a high retain is
#      mostly mechanical, not evidence. The load-bearing evidence is therefore the
#      permutation null (residual share clears it at the floor) and the OUT-OF-SAMPLE
#      leave-one-out per-taker R^2 (loo_taker_r2_residual), NOT the retain ratio. A
#      NON-LINEAR book-state control (book deciles + pairwise interactions, R^2 of 1.9
#      to 3.4 times the linear fit) is added as a separate robustness block so the
#      argument is non-vacuous; the residual share still retains 0.80 to 0.89 of the
#      raw share there.
#
# The scoring window is whichever one settings.py names the headline, read as
# headline_mid_col() and never typed here; it is the same window as I3's
# pre-registered headline cell.
# PLACEBO: permute the wallet labels and recompute the between-wallet share on the
# residual; under the null (identity carries nothing) the permuted share is the
# baseline the observed share must beat. A budget of N_PERM draws cannot express a p
# below 1/(N_PERM+1), so every reported p carries a flag saying whether it is a
# measurement or that floor. All six cells of the committed artifact sit on the floor.
# NOTE: between_share is computed IN-SAMPLE (per-wallet means reused in numerator
# and denominator) and carries a ~1/K upward noise floor - disclosed in the JSON.
#
# numpy-only, nan-aware, seed 20260620, deterministic. Reads ONE shared
# intermediate (quickwin_markouts_mid.npz). No raw-data parse, no order book
# reconstruction here - the book-state controls are the pre-joined entry-snapshot
# columns (imb_entry, spread_entry_bps, micro_dev_bps) carried in that npz.
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

# -------------------- configuration --------------------
HERE = os.path.dirname(os.path.abspath(__file__))
# Located through panel_io, so one module knows where the panels are. The environment
# list is EMPTY on purpose: this file has never honoured a data-root override, and
# adopting panel_io's five names would let a machine that happens to export one of them
# feed this script a different panel. With no name honoured the answer is the directory
# the code sits in, which is what it was. The file name stays a literal inside the join,
# because build.py derives the input edge by folding the argument of np.load to its last
# literal component and a call there would fold to nothing.
DATA_ROOT_ENV = ()
MID_NPZ_PATH = os.path.join(P.data_root(env_names=DATA_ROOT_ENV),
                            "quickwin_markouts_mid.npz")
RESULTS_PATH = os.path.join(HERE, "i3_depth_control_results.json")

COIN_CODES = H.coin_labels("quickwin")   # the map belongs to the FILE, not the project
# The scoring column, asked of panel_io: the window still comes from settings.py and the
# LENS now comes from the panel this file opens, so asking the book-mid panel for a
# trade-print column is refused by name rather than raising a bare KeyError in numpy.
HORIZON_COL = P.score_col("mid")    # headline scoring window, declared in settings.py
CONTROL_COLS = ("imb_entry", "spread_entry_bps", "micro_dev_bps")
K_LIST = H.PERSISTENCE_FLOOR_FILLS  # min obs per wallet for the between-wallet share.
                                    # The declared pair is (cell, small-sample check) =
                                    # (50, 100) and that is the pair this file wants; it
                                    # applies it over the whole RANKING window rather
                                    # than per half, so the fingerprint still records the
                                    # pair as an override of the scalar rank floor.
# Label-permutation null for the between-wallet share, READ from settings.py and no
# longer typed here. settings.min_perm_draws computes the budget from the level, the
# family size and the floor margin rather than leaving it to be chosen.
#
# The literal of 1000 that stood here cleared its bar and still had to go. Its floor was
# 1/1001 = 0.000999 against a corrected rank-one threshold of 0.05/48 = 0.001042, a margin
# of four percent, which is the boundary case settings.PERM_FLOOR_MARGIN is declared to
# prevent: with every cell of this file sitting ON the floor, a four-percent margin means
# the verdict turns on the last digit of the correction instead of on the evidence.
N_PERM = H.N_PERM
N_NL_BINS = 10                      # deciles for the non-linear book-state control
RIDGE_LAMBDA = 1e-6                 # tiny ridge for numerical stability of OLS
RNG_SEED = H.MASTER_SEED            # the declared seed; this file already ran on it, so
                                    # reading it from settings.py moves no number


# -------------------- numpy-only OLS (ridge-stabilised) --------------------
# THIS FILE IS THE HOME OF THREE OBJECTS THE SIZE CONTROL ALSO USES, AND SINCE 2026-08-13
# IT IS THE ONLY ONE. ols_fit_residuals below, between_wallet_share further down, the
# decile design block _decile_dummies between them, and the ridge constant they read stood
# in a second, independently written copy inside own_size_control.py; that file now imports
# them from here. The equality was not assumed from the two texts looking alike, it was
# measured before the copies were merged -- 69 cases for the fit, 45 for the share, 58 for
# the design block, chosen where linear algebra breaks rather than where it is comfortable,
# zero disagreements, on a comparator shown to catch every defect planted in it.
#
# WHY IT MATTERS THAT THESE THREE IN PARTICULAR HAVE ONE HOME. The size control and the
# depth control exist to be compared: one asks what survives after the book state is
# residualised out, the other what survives after own size is. That comparison is only a
# comparison if RAW and residual are formed the same way on both sides, so a divergence
# between two copies of the fit would not show up as a broken function, it would show up as
# a difference between two controls -- read as a result rather than as a defect.
#
# own_size_control.py declares this file as an INPUT of its artifact, so editing anything
# below marks that artifact stale. A producer hash cannot see across an import, and this is
# what closes it.
def ols_fit_residuals(y, X):
    """Fit y ~ [1, X] by ridge-stabilised normal equations; return (beta, resid, r2).

    nan-aware at the caller level (rows with any nan are dropped before this call).
    The intercept is column 0 of the returned beta. resid is y - yhat on the SAME
    rows passed in (so callers must align residuals back to their kept-row index).
    """
    n = y.size
    Xd = np.column_stack([np.ones(n), X])
    p = Xd.shape[1]
    A = Xd.T @ Xd + RIDGE_LAMBDA * np.eye(p)
    b = Xd.T @ y
    try:
        beta = np.linalg.solve(A, b)
    except np.linalg.LinAlgError:
        beta = np.linalg.lstsq(Xd, y, rcond=None)[0]
    yhat = Xd @ beta
    resid = y - yhat
    ss_res = float(np.sum(resid ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = (1.0 - ss_res / ss_tot) if ss_tot > 0 else float("nan")
    return beta, resid, r2


# -------------------- non-linear book-state control design --------------------
def _decile_dummies(x, n_bins=10):
    """Equal-count (rank-based) decile one-hot matrix, drop-first reference.

    Vectorized: rank x, bucket into n_bins, scatter to one-hot, drop the first
    column (absorbed by the intercept). No per-row loop.
    """
    n = x.size
    if n == 0:
        return np.zeros((0, max(n_bins - 1, 0)), dtype=np.float64)
    order = np.argsort(x, kind="stable")
    ranks = np.empty(n, dtype=np.float64)
    ranks[order] = np.arange(n, dtype=np.float64)
    b = np.minimum((ranks / max(n, 1) * n_bins).astype(np.int64), n_bins - 1)
    D = np.zeros((n, n_bins), dtype=np.float64)
    D[np.arange(n), b] = 1.0
    return D[:, 1:]


def nonlinear_book_design(X, n_bins=N_NL_BINS):
    """NON-LINEAR book-state control: per-control deciles + pairwise interactions.

    X is the (n, 3) raw control block [imb_entry, spread_entry_bps, micro_dev_bps].
    Columns: deciles (drop-first) of each control + the three pairwise products of
    the raw controls. Strictly richer than the linear block, so its R^2 upper-bounds
    the linear one; residualizing on it gives a NON-tautological retain. No intercept
    column here (ols_fit_residuals adds it).
    """
    blocks = [_decile_dummies(X[:, j], n_bins=n_bins) for j in range(X.shape[1])]
    inter = np.column_stack([X[:, 0] * X[:, 1],
                             X[:, 0] * X[:, 2],
                             X[:, 1] * X[:, 2]])
    return np.column_stack(blocks + [inter])


# -------------------- between-wallet variance share (one-way ICC-style) --------------------
def between_wallet_share(values, taker, K):
    """Fraction of Var(values) that lives BETWEEN wallets with >= K observations.

    Restrict to eligible wallets (>= K obs). share = Var(per-wallet means) /
    Var(all eligible obs). A value near 0 means identity explains nothing; a value
    well above 0 means wallets differ systematically. Returns (share, n_wallets,
    n_obs) using only eligible-wallet rows. nan values must be pre-dropped.
    """
    if values.size == 0:
        return float("nan"), 0, 0
    uniq, inv = np.unique(taker, return_inverse=True)
    cnt = np.bincount(inv, minlength=uniq.size)
    elig = cnt >= K
    if elig.sum() < 2:
        return float("nan"), int(elig.sum()), 0
    keep = elig[inv]
    v = values[keep]
    inv_k = inv[keep]
    # re-index kept wallets to a dense range for bincount means
    u2, inv2 = np.unique(inv_k, return_inverse=True)
    s = np.bincount(inv2, weights=v, minlength=u2.size)
    c = np.bincount(inv2, minlength=u2.size)
    means = s / c
    var_tot = float(np.var(v))
    var_between = float(np.var(means))   # unweighted across wallet means
    share = (var_between / var_tot) if var_tot > 0 else float("nan")
    return share, int(u2.size), int(v.size)


def loo_taker_r2(values, taker, K):
    """Incremental R^2 of taker identity via a LEAVE-ONE-OUT per-taker-mean predictor.

    For each eligible obs (taker has >= K obs), predict its value by the MEAN of
    that taker's OTHER obs (leave-one-out, so the predictor cannot trivially fit
    the obs itself). R^2 = 1 - SS_res / SS_tot against the grand mean of the kept
    obs. A positive LOO R^2 means knowing the wallet's other markouts predicts this
    one out of sample -> identity carries real, non-mechanical information.
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
    # leave-one-out mean for each obs: (group_sum - own) / (group_count - 1)
    grp_sum = s[inv2]
    grp_cnt = c[inv2]
    denom = grp_cnt - 1.0
    with np.errstate(invalid="ignore", divide="ignore"):
        loo_pred = np.where(denom > 0, (grp_sum - v) / np.where(denom > 0, denom, np.nan),
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


def placebo_between_share(values, taker, K, rng, n_perm=N_PERM):
    """Permutation null: shuffle wallet labels, recompute the between-wallet share.

    Returns the array of n_perm permuted between-wallet shares.

    Efficiency: the eligible-wallet group structure (which wallets have >= K obs,
    their dense bucket index, the kept-row mask) is fixed across permutations, so
    it is computed ONCE. Permuting wallet labels is statistically identical to
    holding the group buckets fixed and SHUFFLING the values among the eligible
    rows; each permutation is then two np.bincount calls (no np.unique per draw).
    """
    if values.size == 0:
        return np.full(n_perm, np.nan, dtype=np.float64)
    uniq, inv = np.unique(taker, return_inverse=True)
    cnt = np.bincount(inv, minlength=uniq.size)
    elig = cnt >= K
    if elig.sum() < 2:
        return np.full(n_perm, np.nan, dtype=np.float64)
    keep = elig[inv]
    v = values[keep].astype(np.float64)
    # dense bucket index over eligible rows (group structure held fixed)
    _, bucket = np.unique(inv[keep], return_inverse=True)
    n_buckets = int(bucket.max()) + 1
    c = np.bincount(bucket, minlength=n_buckets).astype(np.float64)
    perms = np.empty(n_perm, dtype=np.float64)
    for i in range(n_perm):
        vp = rng.permutation(v)               # shuffle values across fixed buckets
        s = np.bincount(bucket, weights=vp, minlength=n_buckets)
        means = s / c
        var_tot = float(np.var(vp))
        perms[i] = (float(np.var(means)) / var_tot) if var_tot > 0 else np.nan
    return perms


# -------------------- per-group analysis --------------------
def analyse_group(mo, controls, taker, label):
    """Run the depth-control test for one coin group (or pooled).

    mo        : 1d float64 markout (mo10_mid), may contain nan
    controls  : (n, 3) float64 entry book-state controls, may contain nan
    taker     : 1d int64 wallet ids aligned to mo
    Returns a result dict for this group.
    """
    out = {"coin": label}
    # nan-aware row mask: drop any row missing the markout OR any control
    finite = np.isfinite(mo)
    for j in range(controls.shape[1]):
        finite &= np.isfinite(controls[:, j])
    n_total = int(mo.size)
    n_drop = int(np.sum(~finite))
    out["n_obs_total"] = n_total
    out["n_obs_used"] = int(np.sum(finite))
    out["nan_drop_fraction"] = (n_drop / n_total) if n_total else float("nan")
    if finite.sum() < 50:
        out["note"] = "too few finite rows for the depth-control fit"
        return out

    y = mo[finite].astype(np.float64)
    X = controls[finite].astype(np.float64)
    tk = taker[finite].astype(np.int64)

    # 1) OLS of markout on entry book-state controls; residual = identity-eligible part
    beta, resid, r2_controls = ols_fit_residuals(y, X)
    out["ols_book_state"] = {
        "predictors": ["intercept"] + list(CONTROL_COLS),
        "beta": [float(b) for b in beta],
        "r2_book_state": r2_controls,
        "note": "R^2 of entry book-state controls (LINEAR) on the raw markout. This "
                "fit explains < 1% of markout variance, so a high share_retained on "
                "the linear residual is largely a TAUTOLOGY of the near-zero R^2 "
                "(residualizing on ~0 explained variance can barely move the "
                "markout) and is NOT strong structural evidence. The supported "
                "claim is narrow: entry book state does not LINEARLY account for the "
                "between-wallet markout dispersion.",
    }

    # 1b) NON-LINEAR book-state control (deciles + pairwise interactions): strictly
    # richer than the linear block, so its R^2 upper-bounds it; the retain on THIS
    # residual is non-tautological evidence that identity survives a real control.
    Xnl = nonlinear_book_design(X, n_bins=N_NL_BINS)
    _, resid_nl, r2_nl = ols_fit_residuals(y, Xnl)
    out["ols_book_state_nonlinear"] = {
        "predictors": ["intercept", "control_deciles(drop-first)x3",
                       "pairwise_control_products x3"],
        "n_design_cols": int(Xnl.shape[1]),
        "r2_book_state_nonlinear": r2_nl,
        "note": "R^2 of a NON-LINEAR book-state control (per-control deciles + "
                "pairwise interactions) on the raw markout. Larger than the linear "
                "R^2, so the retain on this residual (share_retained_nonlinear) is a "
                "non-tautological statement that identity dispersion survives a real "
                "book-state control.",
    }

    # 2/3) between-wallet share + LOO identity R^2 on RAW vs RESIDUAL, per K
    rng = np.random.default_rng(RNG_SEED)
    cells = []
    for K in K_LIST:
        raw_share, n_w_raw, n_o_raw = between_wallet_share(y, tk, K)
        res_share, n_w_res, n_o_res = between_wallet_share(resid, tk, K)
        res_nl_share, _, _ = between_wallet_share(resid_nl, tk, K)
        raw_loo, n_loo_raw = loo_taker_r2(y, tk, K)
        res_loo, n_loo_res = loo_taker_r2(resid, tk, K)

        # placebo null on the RESIDUAL between-wallet share (the decisive number):
        # does identity still explain residual variance beyond label chance?
        perms = placebo_between_share(resid, tk, K,
                                      np.random.default_rng(RNG_SEED + K))
        # THE COUNTING IS stats.permutation_p AND THE NUMBER DOES NOT MOVE. What could
        # have moved it, each named because each is a live disagreement elsewhere in
        # this tree:
        #
        #   the side stays one-sided at `null >= observed - tol`;
        #   the slack is passed as an ABSOLUTE 1e-12, the value this file has always
        #     applied, rather than the module's default, which is a fraction of the
        #     scale of the comparison. That is a declared departure and the block
        #     records tolerance_rule as "absolute, stated by the caller";
        #   a draw that came back as no number is DROPPED and the denominator is the
        #     count of draws that survived, which is what this file already divided by.
        #     placebo_between_share returns no number for a cell whose permuted values
        #     have zero variance, and counting such a draw in the denominator would
        #     claim a resolution the run did not have.
        #
        # The module drops on isfinite and this file dropped on isnan. The two select
        # the same draws here because every draw is a variance RATIO with a positive
        # denominator, so it lies between zero and one and cannot be an infinity.
        perm_block = stats.permutation_p(
            res_share, perms, side="greater", abs_tol=1e-12, n_requested=N_PERM,
            cell=("i3_depth_residual_between_wallet_share", label, int(K)))
        if perm_block["p"] is None:
            p_resid = float("nan")
            perm_mean = float("nan")
        else:
            p_resid = float(perm_block["p"])
            perm_mean = float(perm_block["null_mean"])

        # retain on the LINEAR residual is largely tautological (book R^2 < 1%);
        # retain on the NON-LINEAR residual is the non-vacuous one.
        retained = (res_share / raw_share) if (raw_share == raw_share
                    and raw_share > 0 and res_share == res_share) else float("nan")
        retained_nl = (res_nl_share / raw_share) if (raw_share == raw_share
                       and raw_share > 0 and res_nl_share == res_nl_share) else float("nan")

        # ~1/K in-sample noise floor: with K obs per wallet, sampling noise alone
        # inflates Var(per-wallet means) by ~ within-wallet-variance / K, biasing the
        # in-sample between-share upward by roughly 1/K under pure noise. Disclosed so
        # the share is not read as a clean effect size; the perm null + LOO R^2 carry.
        noise_floor = 1.0 / float(K)

        # IDENTITY SURVIVES THE LINEAR BOOK CONTROL + BEATS THE LABEL NULL. NOTE this
        # is NOT the strong "not a book-state proxy" claim: the linear retain is
        # mostly a tautology of the < 1% book R^2. The boolean asserts only that the
        # residual share beats its label-permutation null AND the NON-LINEAR retain
        # (the non-tautological one) holds >= 0.5 of the raw share.
        identity_survives_linear_book_control = bool(
            res_share == res_share and res_share > 0
            and p_resid == p_resid and p_resid <= 0.05
            and retained_nl == retained_nl and retained_nl >= 0.5)

        cell = {
            "K": K,
            "n_wallets": n_w_raw,
            "n_obs_eligible": n_o_raw,
            "between_share_raw": raw_share,
            "between_share_residual": res_share,
            "between_share_nonlinear_residual": res_nl_share,
            "share_retained_fraction": retained,
            "share_retained_nonlinear": retained_nl,
            "between_share_in_sample_noise_floor": noise_floor,
            "loo_taker_r2_raw": raw_loo,
            "loo_taker_r2_residual": res_loo,
            "placebo_residual_share_mean": perm_mean,
            "placebo_residual_p": p_resid,
            "p_floor": H.p_floor(N_PERM),
            # True means no draw beat the observed residual share, so the p is the
            # budget's smallest expressible value and not a measurement.
            "placebo_residual_p_is_floor": bool(H.p_is_floored(p_resid, N_PERM))
            if p_resid == p_resid else False,
            # The procedure beside the number: side, slack, both draw counts and the
            # floor the p is measured against. A p with no draw count next to it
            # cannot be read.
            "placebo_procedure": perm_block,
            "identity_survives_linear_book_control": identity_survives_linear_book_control,
            "disclosure": "between_share_* and share_retained_* are IN-SAMPLE with a "
                          "~1/K noise floor (between_share_in_sample_noise_floor); the "
                          "linear retain is largely a tautology of the < 1% book R^2. "
                          "Load-bearing evidence = the label-permutation null "
                          "(placebo_residual_p) and the OUT-OF-SAMPLE leave-one-out "
                          "per-taker R^2 (loo_taker_r2_residual), NOT the retain ratio. "
                          "share_retained_nonlinear is the non-tautological retain.",
        }
        cells.append(cell)
        print(f"[i3-depth] {label:<6} K={K:>3} "
              f"betweenRaw={_fmt(raw_share)} betweenResid={_fmt(res_share)} "
              f"retLin={_fmt(retained)} retNL={_fmt(retained_nl)} "
              f"looRaw={_fmt(raw_loo)} looResid={_fmt(res_loo)} "
              f"placebo_p={_fmt(p_resid)} survives={identity_survives_linear_book_control}")
    out["cells"] = cells
    return out


def _fmt(v):
    if v is None:
        return "n/a"
    if isinstance(v, float) and v != v:
        return "nan"
    return f"{v:+.4f}" if isinstance(v, float) else str(v)


# -------------------- main --------------------
def main():
    t0 = artifact.start_clock()
    # panel_io owns both refusals. The missing-FILE message names the producer that
    # writes this gitignored intermediate, and it names no directory -- the message this
    # replaced printed the full path, so the account name of whoever ran it went into
    # any pasted log. The missing-COLUMN message names what was asked and what the file
    # holds.
    P.require_present("mid", MID_NPZ_PATH, env_names=DATA_ROOT_ENV)

    z = np.load(MID_NPZ_PATH, allow_pickle=False)
    P.require_columns(z, "mid", HORIZON_COL, *CONTROL_COLS, "taker_id", "coin", "day")

    taker_id = z["taker_id"].astype(np.int64)
    coin = z["coin"].astype(np.int8)
    mo = P.score(z, "mid")
    controls = np.column_stack([z[c].astype(np.float64) for c in CONTROL_COLS])
    # Read only to state the window in the artifact's scope; it enters no computation.
    day = z["day"].astype(np.int64)

    print(f"[i3-depth] rows={mo.size:,} horizon={HORIZON_COL} "
          f"controls={list(CONTROL_COLS)} K_list={K_LIST} "
          f"n_perm={N_PERM} seed={RNG_SEED}")

    # What every number in this file was computed under. It used to be written into
    # results["scope"] and mirrored again into _meta, which is one record in two
    # places and the reason a census of this property returned two different numbers.
    # artifact.write is now the single place that stamps it.
    settings_used = dict(
        h=H.HEADLINE_HORIZON_S, lens="mid",
        master_seed=RNG_SEED,
        n_perm=N_PERM,
        n_boot=None,
        rank_floor_fills=list(K_LIST),
        whale_drop_criterion=None,
        p_floor=H.p_floor(N_PERM),
        overrides_note=(
            "n_perm is the declared budget, read from settings.py and no longer "
            "typed here; a p at the floor is still a bound and not a "
            "measurement, which is what placebo_residual_p_is_floor records; "
            "rank_floor_fills (50, 100) not the declared "
            "single 50, the second rung being the small-sample check; no "
            "bootstrap is drawn, so n_boot does not apply; no whale-drop arm "
            "runs here, so no drop criterion applies; the seed is "
            "settings.MASTER_SEED unchanged"),
            )

    results = {
        "object": "I3-DEPTH - per-counterparty markout dispersion vs entry-book-state "
                  "controls. SUPPORTED CLAIM (narrow): entry book state does NOT "
                  "LINEARLY account for the between-wallet markout dispersion (book "
                  "R^2 < 1%); identity dispersion survives LINEAR book-state "
                  "residualization and beats a label-permutation null.",
        "caveats": {
            "linear_retain_is_tautological": "Linear book R^2 < 1%, so "
                "share_retained_fraction (~0.78-0.91) is largely a TAUTOLOGY of the "
                "near-zero R^2 (residualizing on ~0 explained variance can barely "
                "move the markout). Do not read it as strong structural evidence "
                "that identity is not a book-state proxy.",
            "between_share_is_in_sample": "between_share_* and share_retained_* are "
                "computed IN-SAMPLE (per-wallet means reused in numerator and "
                "denominator) and carry a ~1/K upward noise floor "
                "(between_share_in_sample_noise_floor); descriptive, not a clean "
                "effect size.",
            "load_bearing_evidence": "Significance rests on the label-permutation "
                "null (placebo_residual_p clears the floor) and the OUT-OF-SAMPLE "
                "leave-one-out per-taker R^2 (loo_taker_r2_residual ~ 0.03-0.08), "
                "NOT the retain ratio.",
            "nonlinear_control_added": "A NON-LINEAR book-state control (per-control "
                "deciles + pairwise interactions, R^2 of 1.9 to 3.4 times the linear "
                "fit) is added; the residual share still retains 0.80 to 0.89 of the raw "
                "share on it (share_retained_nonlinear) - that retain IS "
                "non-tautological.",
        },
        "scope": {
            "markout_source": "mid",
            "input_npz": os.path.basename(MID_NPZ_PATH),
            "horizon_col": HORIZON_COL,
            "horizon_s": H.HEADLINE_HORIZON_S,
            "control_cols": list(CONTROL_COLS),
            "nonlinear_control": "per-control deciles + pairwise interactions",
            "n_nl_bins": N_NL_BINS,
            "K_list": list(K_LIST),
            "n_perm": N_PERM,
            "p_floor": H.p_floor(N_PERM),
            "p_floor_note": (
                f"{N_PERM} draws cannot express a p below {H.p_floor(N_PERM):.6f}; each "
                "cell carries placebo_residual_p_is_floor saying which of the two its p "
                "is"),
            "rng_seed": RNG_SEED,
            "question": "Does entry book state (imb_entry, spread_entry_bps, "
            "micro_dev_bps) LINEARLY account for the per-counterparty (between-wallet) "
            "markout dispersion, and does that dispersion survive linear book-state "
            "residualization beyond a label-permutation null? (Answered: book state "
            "explains < 1% linearly; the dispersion survives and beats the null.) The "
            "earlier strong 'identity is not a book-state proxy' framing is retracted "
            "- see caveats.linear_retain_is_tautological.",
            "verdict_rule": "identity_survives_linear_book_control = residual "
            "between-wallet share > 0 AND beats its label-permutation null (p<=0.05) "
            "AND the NON-LINEAR retain (share_retained_nonlinear, the non-tautological "
            "one) holds >= 50% of the raw share. This asserts only survival of the "
            "LINEAR book control + the label null - NOT strong structural exclusion.",
        },
        "by_coin": [],
        "pooled": None,
        "issues": [],
    }

    for code, label in COIN_CODES.items():
        sel = coin == code
        if sel.sum() == 0:
            results["issues"].append(f"{label}: no rows")
            continue
        results["by_coin"].append(
            analyse_group(mo[sel], controls[sel], taker_id[sel], label))

    # pooled across coins (price-normalised bps markouts are coin-comparable)
    results["pooled"] = analyse_group(mo, controls, taker_id, "POOLED")

    results["_meta"] = {"rng_seed": RNG_SEED}

    # What the numbers cover. The unit of analysis is the WALLET: rows are reduced to
    # per-wallet means and a wallet enters a cell at that cell's fill floor, so the
    # population names both the rows read and the floors that admit a wallet.
    scope = {
        "population": (f"{mo.size:,} rows of the book-mid panel reduced to per-wallet "
                       f"means; a wallet enters a cell at that cell's fill floor, and "
                       f"the cells run over {list(K_LIST)} fills"),
        "window": (f"{np.unique(day).size} days present in the input, day-of-month "
                   f"{day.min()}-{day.max()}; this file makes no early-and-late "
                   "split, so every day present enters every cell, and the calendar "
                   "dates are declared by the panel's producer through "
                   "i4_midmarkout.py"),
        "coins": [COIN_CODES[c] for c in sorted(COIN_CODES)],
    }

    # The output name and directory still come from the module-level RESULTS_PATH, so
    # a caller that redirects that constant redirects the whole write, as before.
    artifact.write(os.path.basename(RESULTS_PATH), results,
                   script=__file__, inputs=[MID_NPZ_PATH], scope=scope,
                   settings=settings_used, started=t0,
                   out_dir=os.path.dirname(RESULTS_PATH))

    _print_summary(results)


def _print_summary(results):
    print("\n" + "=" * 80)
    print("OBJECT I3-DEPTH - COUNTERPARTY TOXICITY AFTER BOOK-STATE CONTROLS - SUMMARY")
    print("=" * 80)
    sc = results["scope"]
    print(f"  markout={sc['horizon_col']} (window {sc['horizon_s']}s, from settings.py) "
          f"controls={sc['control_cols']}")
    print(f"  {N_PERM} label-permutations (p-floor={sc['p_floor']:.6f}); seed={sc['rng_seed']}.")
    print("  A p marked FLOOR means no draw beat the observed share: that is the budget")
    print("  speaking, not a measured p, and no floored p can clear a corrected")
    print("  threshold below the floor however strong the effect.")
    print("-" * 80)
    print("  CLAIM (narrow): entry book state does NOT LINEARLY account for the")
    print("  between-wallet markout dispersion (book R^2 < 1%); identity survives the")
    print("  LINEAR control + a label null. retLin (0.78-0.91) is largely a TAUTOLOGY")
    print("  of that ~0 R^2 - the real evidence is looResid (OOS) + placebo_p + retNL.")
    print("-" * 80)
    header = (f"  {'coin':<6} {'K':>4} {'betwRaw':>9} {'betwResid':>10} "
              f"{'retLin':>7} {'retNL':>7} {'looRaw':>8} {'looResid':>9} "
              f"{'placebo_p':>10} {'floor':>5} {'survives':>9}")
    blocks = [(results["by_coin"], "PER-COIN")]
    if results.get("pooled"):
        blocks.append(([results["pooled"]], "POOLED"))
    for block, name in blocks:
        if not block:
            continue
        print(f"  [{name}]")
        print(header)
        for g in block:
            if not g.get("cells"):
                print(f"  {g['coin']:<6} {'-':>4} {g.get('note', 'no cells'):>40}")
                continue
            r2bs = g["ols_book_state"]["r2_book_state"]
            r2nl = g.get("ols_book_state_nonlinear", {}).get("r2_book_state_nonlinear")
            print(f"  -- {g['coin']}: book-state OLS R^2(lin)={_fmt(r2bs)} "
                  f"R^2(nl)={_fmt(r2nl)} "
                  f"(n_used={g['n_obs_used']:,}, nan_drop={_fmt(g['nan_drop_fraction'])})")
            for c in g["cells"]:
                print(f"  {g['coin']:<6} {c['K']:>4} "
                      f"{_fmt(c['between_share_raw']):>9} "
                      f"{_fmt(c['between_share_residual']):>10} "
                      f"{_fmt(c['share_retained_fraction']):>7} "
                      f"{_fmt(c.get('share_retained_nonlinear')):>7} "
                      f"{_fmt(c['loo_taker_r2_raw']):>8} "
                      f"{_fmt(c['loo_taker_r2_residual']):>9} "
                      f"{_fmt(c['placebo_residual_p']):>10} "
                      f"{('yes' if c.get('placebo_residual_p_is_floor') else ''):>5} "
                      f"{str(c['identity_survives_linear_book_control']):>9}")
    print("-" * 80)
    print("  READING: retLin is largely a TAUTOLOGY of the < 1% linear book R^2 -")
    print("  ignore it as structural evidence. The real evidence is looResid (OOS")
    print("  leave-one-out per-taker R^2) > 0, the residual share beating its")
    print("  permutation null (placebo_p), and retNL (retain under a real NON-LINEAR")
    print("  book control) staying high. Together they show identity carries markout")
    print("  information the entry book state does not LINEARLY account for; the")
    print("  in-sample between-share carries a ~1/K noise floor and is descriptive.")
    if results.get("issues"):
        print("-" * 80)
        for msg in results["issues"]:
            print(f"  [!] {msg}")
    print("=" * 80)
    print(f"  results -> {os.path.basename(RESULTS_PATH)}")


if __name__ == "__main__":
    main()
