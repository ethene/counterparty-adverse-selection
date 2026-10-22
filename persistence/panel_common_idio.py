"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-20
References:
  - Hyperliquid node-data S3 archive (node_fills_by_block/hourly), s3://hl-mainnet-node-data.
  - Zenodo 18184441 (Albers et al. 2026) repeat-counterparty structure.
  - Kline, P., Saggio, R., Solvsten, M. (2020). "Leave-out estimation of variance
    components." Econometrica 88(5), 1859-1898. (Split-half / split-sample spirit of
    the bias correction; same noise-cancellation logic as i2_walletfe.py.)
  - Menkhoff, L., Sarno, L., Schmeling, M., Schrimpf, A. (2016). "Information flows in
    foreign exchange markets: dissecting customer currency trades." Journal of Finance
    71(2), 601-634. (Decomposing order-flow toxicity into common vs counterparty-specific.)
  - Korajczyk, R., Sadka, R. (2008). Common vs idiosyncratic components of liquidity.
  - Spearman-Brown reliability (used ONLY as a >0 diagnostic gate, NOT to rescale the
    headline share). The corrected idiosyncratic SHARE is bias-corrected by the
    cross-wallet half-mean covariance estimator (disjoint A/B fills cancel the noise),
    not by any disattenuation of the share.
"""

# ===========================================================================
# OBJECT PANEL/COMMON-IDIO -- the SCIENCE PAYOFF of the multi-period panel.
#
# The December run established that per-counterparty 60s toxicity has a stable,
# label-real idiosyncratic component (i2 one-way wallet FE) that persists across
# an early/late split (ks2). That was all WITHIN ONE 10-day window. This object
# uses the PANEL -- {BTC, ETH, SOL} x three 10-day windows (periods 202508,
# 202510, 202512) -- to do the thing a single window cannot: separate a wallet's
# toxicity into a COMMON (market-wide, period-varying) component and an
# IDIOSYNCRATIC (wallet-specific, stable-across-periods) component, and report
# the idiosyncratic SHARE as the identification payoff.
#
# SCOPE vs ARTIFACT. Three windows is what this decomposition READS, not what the
# data holds: panel_markouts.npz carries eight windows and 26,035,902 rows, and
# CANONICAL_PERIODS below pins the load so the committed result keeps reproducing.
# The three-window subset is 10,455,129 rows. Name the first figure for coverage
# and the second for any number produced here.
#
# THE PANEL MODEL. For wallet i active in period t (>= 1 fill in that cell), let
# ybar_{i,t} be the wallet's mean 10s markout in that period. Write
#
#       ybar_{i,t}  =  mu  +  c_t  +  a_i  +  u_{i,t}                       (1)
#
#   c_t  = COMMON period effect (market-wide toxicity that shifts every wallet in
#          a window the same way: a quiet August vs a volatile October-crash
#          window vs December). This is the part you could in principle read off
#          the aggregate flow without resolving counterparties.
#   a_i  = IDIOSYNCRATIC wallet effect, STABLE across periods (the part only
#          on-chain identity resolution makes observable -- the central claim).
#   u_{i,t} = wallet-x-period noise (finite-sample mean over that cell's fills,
#          plus any genuinely transient wallet behaviour).
#
# We restrict to wallets active in >= 2 periods (MIN_PERIODS), because a_i can
# only be told apart from u_{i,t} when a wallet is seen more than once.
#
# THE DECOMPOSITION (variance components of the per-cell means):
#   (a) COMMON share      = Var(c_t) / Var(ybar)  -- estimated by the period
#       fixed-effect: c_hat_t = (period mean of ybar over its cells) - grand mean.
#       Its weighted variance is the common (between-period) component.
#   (b) IDIOSYNCRATIC share = Var(a_i) / Var(ybar) AFTER removing the period FE.
#       The NAIVE between-wallet variance of the period-demeaned cell means is
#       UPWARD-biased for Var(a_i) by E[Var(u)/n_periods_i] exactly as in i2; we
#       therefore ALSO report a SPLIT-HALF bias-corrected estimate where each
#       wallet's FILLS (not cells) are split A/B, both halves are period-demeaned,
#       and the cross-wallet covariance Cov(aHat_A, aHat_B) cancels the within
#       noise (the i2 covariance-cancels-noise trick, lifted to the panel after
#       period demeaning).
#   (c) WITHIN share      = the residual u (noise), = 1 - common - idio on the
#       corrected scale, reported with the naive within for transparency.
#
# THE IDENTIFICATION PAYOFF + ITS RELIABILITY. The headline is the IDIOSYNCRATIC
# share. IMPORTANT -- the corrected idiosyncratic share is
#       corrected_idio_share = corrected_idio_var / total_var ,
# where corrected_idio_var is bias-corrected by the CROSS-WALLET HALF-MEAN
# COVARIANCE estimator (Cov(aHat_A, aHat_B) over disjoint A/B fills, so the
# within-cell sampling noise cancels). The share is NEVER divided by a reliability
# / NEVER Spearman-Brown disattenuated. The split-half reliability below is a
# DIAGNOSTIC ONLY and feeds the rel>0 identification gate; it does not rescale the
# headline share. We attach, exactly as ks2/i2 do:
#   * SPLIT-HALF RELIABILITY of the period-demeaned per-wallet score (odd/even
#     within-wallet split, Spearman of the two half-scores across wallets), with a
#     Spearman-Brown step that maps the half-length Spearman to a full-length
#     reliability NUMBER -- reported as a DIAGNOSTIC of how much of the per-wallet
#     spread is signal vs noise and as the >0 gate, NOT applied to the share. To
#     match the covariance correction it is AVERAGED over the same N_SPLIT_SEEDS
#     random splits rather than read from a single split;
#   * a LABEL-PERMUTATION NULL: shuffle the wallet labels (break the wallet<->score
#     link) and recompute the corrected idiosyncratic signal variance; the
#     observed value must sit in the right tail. One-sided p with the 1/(N+1)
#     floor convention (i2 / ks2);
#   * WHALE-DROP: drop the top N_DROP_WHALES wallets by total fill count and
#     re-estimate, so the share is not a handful of bots;
#   * BH-FDR across the {BTC, ETH, SOL, pooled} x K family for the permutation
#     p-values (the ks2 hand-rolled Benjamini-Hochberg).
#
# HONEST READ. 'idiosyncratic_component_identified' is set TRUE for a cell ONLY
# when (i) the corrected idiosyncratic share is positive and materially above the
# common share's noise floor, (ii) the split-half reliability is comfortably > 0,
# and (iii) the label-permutation p clears 0.05 (BH-q across the family). The
# markout reference here is the TRADE-PRINT mo10 (sign: positive = taker profited
# = maker adversely selected); the MAGNITUDE of a_i mixes adverse selection with
# bid-ask bounce / earned spread exactly as i2 flags, so this object decomposes
# the VARIANCE STRUCTURE (common vs idiosyncratic) and does NOT claim the
# idiosyncratic magnitude is all adverse selection -- that attribution waits on
# the book-mid follow-on. What the panel adds over i2 is the SEPARATION of the
# wallet-stable part from the market-wide-common part, which a single window
# cannot do.
#
# GUARDS (shared data contract): reads ONLY panel_markouts.npz (taker_id, coin,
# period, mo10, notional, ...); vectorized (bincount / np.add.at, analytic where
# possible, no per-trade x1000 python loops); declared seeds in a header constant;
# permutation p-floor 1/(N_PERM+1); BH-FDR across cells; per coin AND pooled; NO
# hardcoded /Users paths (HERE + env/argparse data-root); only os.path.basename
# written into the result JSON; numpy + stdlib only.
#
# Run command (bare python3 is BLOCKED on this machine):
#   uv run --no-project --with-requirements requirements.txt python3 persistence/panel_common_idio.py
# Optional: --data-root <dir> to point at an alternate npz directory (smoke).
# ===========================================================================

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

# -------------------- configuration (declared seeds + panel constants) --------------------
# Every setting that settings.py declares is READ from there, not re-typed, so this
# file cannot disagree with the declaration. Each value was compared against what this
# file used to carry, and all of them were identical except the permutation budget,
# which was 200 against a declared 2000. That one moved every p-value in the artifact
# and is recorded below with what the move did and did not change.
SEED = H.MASTER_SEED                     # 20260620, the one master seed
# 20240601, the odd/even reliability seed, kept separate from the master seed because
# it seeds a different estimator. It used to be BOUND HERE AND USED NOWHERE: the
# reliability was drawn over the master seed's split_seeds while _meta reported this
# value as reliability_seed_base, so the artifact named a seed the run had not used --
# the exact defect settings.py rule 2 is about, and it survived because a dead name
# reads like a live one. It now seeds the reliability, as it does in the two sibling
# files that estimate the same quantity (ks2_persistence_10day.py, panel_persistence.py).
RNG_RELIABILITY = H.RELIABILITY_SEED

HERE = os.path.dirname(os.path.abspath(__file__))
PANEL_NPZ_NAME = "panel_markouts.npz"
TAKER_MAP_NAME = "quickwin_taker_map.json"
OUT_NAME = "panel_common_idio_results.json"

# npz int8 coin code -> label, asked for BY ARTIFACT: the panel file carries
# {0,1,2} while quickwin carries {0,1}, and a code valid in both relabels BTC as
# ETH without raising, so the map belongs to the file and is never typed here.
COIN_CODES = H.coin_labels("panel")      # {0: BTC, 1: ETH, 2: SOL}

# The three fixed 10-day windows, period = int YYYYMM (the panel schema 'period').
PANEL_PERIODS = (202508, 202510, 202512)
# Pins the paper's Aug/Oct/Dec 3-window panel: panel_markouts.npz was later rebuilt from
# 3 to 8 windows, so main() restricts the loaded fills to these three so a re-run
# reproduces the committed panel_common_idio_results.json.
CANONICAL_PERIODS = (202508, 202510, 202512)

MIN_PERIODS = 2                          # wallet must be active in >= this many periods
K_LIST = H.PERSISTENCE_FLOOR_FILLS       # (50, 100) min TOTAL fills per wallet
N_SPLIT_SEEDS = 5                        # independent A/B splits to average the correction
# The label-permutation budget, read from the declaration rather than typed. It used
# to be a literal 200, and that literal set the p-value floor at 1/201 = 0.00498 --
# which is where every one of the 24 distinct significance values in this file's
# artifact sat, so the artifact could say only "no draw reached the observed value"
# and nothing about how far past the null the observed value lay.
#
# WHAT THE RAISE BUYS AND WHAT IT DOES NOT. It buys resolution: the floor drops to
# 1/2001 = 0.0005, which is what settings.min_perm_draws() computes from the level,
# the family size and the margin. It does NOT buy support for a MAGNITUDE. Measured
# before the change on the 200-draw artifact: the observed corrected idiosyncratic
# variance sits 6 to 21 times the null's own MAXIMUM and 18 to 74 null standard
# deviations above the null mean, so no permutation budget will ever put a draw past
# it and every p will keep landing on whatever floor the budget sets. A p at the floor
# is a statement that the effect is not zero. The size of the effect is carried by the
# corrected share and needs an interval on that share, not more draws.
N_PERM = H.N_PERM
N_DROP_WHALES = H.WHALE_DROP_K           # 10; drop top-N wallets by fill count
FDR_ALPHA = H.FDR_ALPHA                  # 0.05 BH level across the cell family

# H.fingerprint asserts a MIGRATING declaration only when the caller states what its
# run used, so these are here to CONFIRM what was used and not to contradict it: the
# master seed and the permutation budget are both the declared values. They are still
# passed because a fingerprint that only carries what settings.py declares says nothing
# about the run. This object bootstraps nothing and ranks on no fill floor.
SETTINGS_OVERRIDES = {"master_seed": SEED,
                      "n_perm": N_PERM, "p_floor": H.p_floor(N_PERM),
                      "n_split_seeds": N_SPLIT_SEEDS,
                      "min_periods_per_wallet": MIN_PERIODS,
                      "settings_not_used": ["n_boot", "rank_floor_fills"]}

# -------------------- window-bearing field names, built and never typed ----------
# settings.FIELD_SUFFIX_STYLE = "explicit". This file reads ONE markout column, the
# headline trade print, so no key here ever meant two windows at once - but every
# variance and share it reports would change with the window, and none of them said
# which window or which reference price. The 2-7% idiosyncratic share is quoted in
# prose; a reader lifting it needs to know it is the 10 s trade print and not the
# 60 s one or a book mid, and the file's own honesty note turns on exactly that
# distinction (a trade-print magnitude carries the maker's earned spread inside it).
#
# THE RULE APPLIED HERE. A field is suffixed when its value is a LEVEL, VARIANCE or
# SHARE of the markout, plus the split-half RELIABILITY - which is suffixed because
# it is the one correlation this project has already quoted at the wrong window
# (0.43-0.54 belongs to the 60 s print, 0.78-0.90 to the headline). Test-machinery
# fields are NOT suffixed: a p-value, a q-value, a wallet count and the null's own
# moments describe the test rather than the markout, and each sits inside a block
# whose sibling fields state the window.
LENS = "print"                           # node_fills trade print, never a book mid


def _f(base):
    """The name of one window-bearing field at the headline horizon and lens."""
    return H.field_name(base, H.HEADLINE_HORIZON_S, lens=LENS)


K_GRAND_MEAN = _f("grand_mean_bps")
K_TOTAL_VAR = _f("total_var")
K_COMMON_VAR = _f("common_var")
K_IDIO_NAIVE_VAR = _f("idio_naive_var")
K_WITHIN_VAR = _f("within_var")
K_COMMON_SHARE = _f("common_share")
K_IDIO_NAIVE_SHARE = _f("idio_naive_share")
K_WITHIN_NAIVE_SHARE = _f("within_naive_share")
K_PERIOD_FE = _f("period_fe_bps")
K_CORR_IDIO_VAR = _f("corrected_idio_var")
K_CORR_IDIO_VAR_SD = _f("corrected_idio_var_seed_std")
K_CORR_IDIO_SHARE = _f("corrected_idio_share")
K_PER_SEED_IDIO_VAR = _f("per_seed_idio_var")
K_RELIABILITY = _f("reliability")
K_R_HALF = _f("r_half")

# The whale-drop arm names its criterion, not just its count: "drop_top10_by_
# fill_count". Dropping the ten largest by fill count asks whether the share is a
# handful of bots; dropping by notional asks whether it is a volume artifact. The
# two are different questions with different answers, so the key states which.
WHALE_KEY = H.whale_drop("fill_count", N_DROP_WHALES)["key"]

# Honesty note carried into the JSON and echoed in the printed table.
INTERPRETATION_HELD = (
    "The markout reference is the TRADE-PRINT mo10, not a book mid, so the "
    "MAGNITUDE of the idiosyncratic wallet effect a_i mixes adverse selection "
    "with bid-ask bounce and the maker's earned spread (same caveat as "
    "i2_walletfe.py). This object decomposes the VARIANCE STRUCTURE into a "
    "market-wide-COMMON (period) component and a wallet-stable IDIOSYNCRATIC "
    "component; it does NOT claim the idiosyncratic magnitude is all adverse "
    "selection. The book-mid attribution of the magnitude is a documented "
    "follow-on. What the panel adds over i2 is the SEPARATION of the wallet-stable "
    "part from the market-wide-common part, impossible within a single window."
)

# Honest framing of the headline vs the pooled number and of the common leg. BUILT
# from the cells this run computed, never typed: the typed version of this note said
# the per-coin share was "roughly 2-7%" and SOL's per-cell variance "~4.5x BTC's",
# and by the time it was checked the cells read 1.0% to 29.8% and 5.0x to 13.0x. A
# note that quotes a number it does not compute goes stale in silence, and this one is
# the note a reader lifts the headline from.
HEADLINE_NOTE_FRAME = (
    "HEADLINE = the PER-COIN split-half-corrected idiosyncratic share, and it is not "
    "one number: {percoin}. The POOLED cross-coin figure ({pooled}) is a pooling / "
    "DENOMINATOR artifact and not the headline, though only against the coin whose "
    "own variance is smallest -- at the {kmin}-fill floor it sits between two of the "
    "three per-coin shares rather than below all of them. The mechanism is the shared "
    "denominator: SOL's total per-cell variance is {solbtc} of BTC's. Overlap works "
    "the same way and the population has to be named with it, because the populations "
    "disagree by a factor of four: {panel_one_coin} of the {n_panel:,} wallets in the "
    "three-window panel touch exactly one coin, but only {cell_one_coin} of the "
    "{n_cell:,} wallets that actually enter the pooled cell at the {kmin}-fill floor "
    "do. Report the per-coin shares with the fill floor named beside them; treat the "
    "pooled share as a diluted lower bound only."
)

CLAIM_NOTE = (
    "The claim is that a STATISTICALLY SEPARABLE / IDENTIFIED wallet-idiosyncratic "
    "component of per-counterparty toxicity exists (positive after the cross-wallet "
    "covariance bias correction, reliability>0, label-permutation p in the right "
    "tail with BH-FDR control). The MAGNITUDE is a small share BECAUSE roughly half "
    "of the total per-cell variance is irreducible within-cell sampling noise (the "
    "'within' component); a small identified share does NOT imply economic "
    "dominance and we do NOT claim the idiosyncratic part dominates toxicity."
)

COMMON_LEG_NOTE = (
    "LIMITATION: the COMMON (period) leg is estimated on only THREE windows "
    "(202508/202510/202512), so Var(c_t) is under-identified and is EXCLUDED from "
    "the identification gate. The gate keys on the idiosyncratic leg only; the "
    "common share is reported for transparency, not claimed to be identified."
)


# ==================== rank / correlation helpers (numpy-only, lifted from ks2/i2) ====================
def _rankdata(a):
    """Average-rank of a 1-D array (ties shared), matching the ks2/i2/i3 ranker."""
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
    """Spearman rank correlation; NaN when < 3 points or a constant rank vector."""
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    n = x.size
    if n < 3 or y.size != n:
        return float("nan")
    rx, ry = _rankdata(x), _rankdata(y)
    rx -= rx.mean()
    ry -= ry.mean()
    denom = np.sqrt((rx * rx).sum() * (ry * ry).sum())
    return float("nan") if denom == 0 else float((rx * ry).sum() / denom)


# The Benjamini-Hochberg step-up that used to be hand-rolled here, lifted from ks2, is
# stats.benjamini_hochberg. It costs no q: stats._legacy_bh_loop is this exact spelling,
# and that module's self-test runs the two against each other on 200 random families
# with ties and untestable cells and asserts identical values. What the module adds is
# the cutoff the q-values were judged against.


# ==================== panel cell builders ====================
def _cell_means(taker_id, period, y):
    """Per-(wallet, period) mean of y, plus the period fixed effect.

    Returns aligned arrays over the (wallet, period) CELLS that exist:
        cell_wallet   int64  dense wallet label (0..G-1)
        cell_period   int64  the YYYYMM period of the cell
        cell_pidx     int64  dense period index (0..P-1) for the FE
        cell_mean     f64    mean y over the cell's fills
        cell_nfills   int64  number of fills in the cell
    and, separately:
        wallet_ids    int64  raw wallet id per dense label
        period_ids    int64  raw YYYYMM per dense period index
        period_fe     f64    c_hat_p = (cell-weighted? NO -- cell-equal) period mean
                             of cell means minus grand mean of cell means
    The period FE is the COMMON component: the average toxicity level of a window,
    estimated as the mean of the per-cell means in that period. Using the cell
    means (one point per wallet-period) rather than raw fills weights every active
    wallet equally inside a period, which matches the random-effects target where
    a_i and c_t are wallet/period effects, not fill effects.
    """
    taker_id = np.asarray(taker_id, dtype=np.int64)
    period = np.asarray(period, dtype=np.int64)
    y = np.asarray(y, dtype=np.float64)

    # composite (wallet, period) key -> dense cell label
    wallet_ids, w_inv = np.unique(taker_id, return_inverse=True)
    period_ids, p_inv = np.unique(period, return_inverse=True)
    n_p = period_ids.size
    composite = w_inv.astype(np.int64) * n_p + p_inv.astype(np.int64)
    cell_key, c_inv = np.unique(composite, return_inverse=True)
    n_cells = cell_key.size

    s = np.bincount(c_inv, weights=y, minlength=n_cells)
    c = np.bincount(c_inv, minlength=n_cells).astype(np.float64)
    cell_mean = s / c
    cell_nfills = c.astype(np.int64)

    cell_wallet = (cell_key // n_p).astype(np.int64)          # dense wallet label
    cell_pidx = (cell_key % n_p).astype(np.int64)             # dense period index
    cell_period = period_ids[cell_pidx].astype(np.int64)

    # COMMON period FE = period mean of the per-cell means, minus the grand mean.
    grand = float(cell_mean.mean())
    p_sum = np.bincount(cell_pidx, weights=cell_mean, minlength=n_p)
    p_cnt = np.bincount(cell_pidx, minlength=n_p).astype(np.float64)
    period_mean = np.full(n_p, np.nan, dtype=np.float64)
    nz = p_cnt > 0
    period_mean[nz] = p_sum[nz] / p_cnt[nz]
    period_fe = period_mean - grand

    return {
        "cell_wallet": cell_wallet,
        "cell_period": cell_period,
        "cell_pidx": cell_pidx,
        "cell_mean": cell_mean,
        "cell_nfills": cell_nfills,
        "wallet_ids": wallet_ids,
        "period_ids": period_ids.astype(np.int64),
        "period_fe": period_fe,
        "period_mean": period_mean,
        "grand_mean": grand,
        "n_periods": int(n_p),
    }


def _wallet_period_count(cell_wallet, n_wallets):
    """Number of distinct periods each dense wallet appears in (>=1 cell each)."""
    return np.bincount(cell_wallet, minlength=n_wallets).astype(np.int64)


# ==================== naive common / idiosyncratic / within decomposition ====================
def naive_panel_decomposition(cells):
    """Naive variance-components on the per-cell means: common vs idiosyncratic.

    Operates over the CELLS (one per active wallet-period). Let m_{i,t} = cell mean.
        total_var   = Var(m) over cells (population variance about the grand mean).
        common_var  = cell-weighted variance of the period FE c_hat_t (between
                      periods); this is the COMMON component Var(c_t).
        After subtracting the period FE, r_{i,t} = m_{i,t} - c_hat_t. The NAIVE
        between-wallet variance of the wallet means of r is the upward-biased
        idiosyncratic component Var(a_i):
            idio_naive = cell-weighted variance of rbar_i about 0.
        within_var  = total - common - idio_naive (the residual u, by identity).

    Shares are each component / total_var. The idiosyncratic share is STATED
    upward-biased; the split-half correction lives in the corrected block.
    """
    m = cells["cell_mean"]
    pidx = cells["cell_pidx"]
    cw = cells["cell_wallet"]
    n_cells = m.size
    grand = float(m.mean())
    total_var = float(((m - grand) ** 2).mean())

    # COMMON: weighted variance of period FE across cells.
    fe_per_cell = cells["period_fe"][pidx]                    # c_hat_t broadcast to cells
    common_var = float((fe_per_cell ** 2).mean())             # FE already mean-zero-ish

    # period-demeaned cell residual
    r = m - fe_per_cell

    # IDIOSYNCRATIC (naive): between-wallet variance of wallet means of r.
    n_wallets = int(cw.max()) + 1 if cw.size else 0
    w_sum = np.bincount(cw, weights=r, minlength=n_wallets)
    w_cnt = np.bincount(cw, minlength=n_wallets).astype(np.float64)
    rbar = np.full(n_wallets, np.nan, dtype=np.float64)
    nzw = w_cnt > 0
    rbar[nzw] = w_sum[nzw] / w_cnt[nzw]
    # cell-weighted variance of rbar_i about its (near-zero) cell-weighted mean
    rbar_cell = rbar[cw]
    rbar_grand = float(rbar_cell.mean())
    idio_naive = float(((rbar_cell - rbar_grand) ** 2).mean())

    within_var = total_var - common_var - idio_naive

    def _share(x):
        return x / total_var if total_var > 0 else float("nan")

    return {
        "n_cells": int(n_cells),
        "n_periods_present": int(np.unique(pidx).size),
        K_GRAND_MEAN: grand,
        K_TOTAL_VAR: total_var,
        K_COMMON_VAR: common_var,
        K_IDIO_NAIVE_VAR: idio_naive,
        K_WITHIN_VAR: within_var,
        K_COMMON_SHARE: _share(common_var),
        K_IDIO_NAIVE_SHARE: _share(idio_naive),
        K_WITHIN_NAIVE_SHARE: _share(within_var),
        K_PERIOD_FE: {int(cells["period_ids"][k]): float(cells["period_fe"][k])
                      for k in range(cells["period_ids"].size)},
        "bias_note": (f"{K_IDIO_NAIVE_VAR} = Var(a_i) + E[Var(u)/n_i] is "
                      "UPWARD-biased; the split-half-corrected idiosyncratic "
                      "variance (noise cancelled in the cross-wallet covariance) "
                      "is in split_half_corrected"),
    }


# ==================== split-half bias-corrected idiosyncratic variance ====================
def _period_demeaned_halfmeans(taker_id, period, y, is_A, period_fe_lookup,
                               n_wallets, w_dense_inv, p_dense_inv):
    """Per-wallet period-demeaned half-means for half A (or its complement).

    Each FILL carries (dense wallet label, dense period index). We subtract the
    COMMON period FE from each fill's y (the FE is shared, estimated on all fills),
    then average the period-demeaned residual within each wallet over the half's
    fills. Returns (mean_per_wallet, count_per_wallet) over dense wallet labels.
    Vectorized: two weighted bincounts.
    """
    fe = period_fe_lookup[p_dense_inv]                        # c_hat_t per fill
    resid = (y - fe)
    sel = is_A
    s = np.bincount(w_dense_inv[sel], weights=resid[sel], minlength=n_wallets)
    c = np.bincount(w_dense_inv[sel], minlength=n_wallets).astype(np.float64)
    mean = np.full(n_wallets, np.nan, dtype=np.float64)
    nz = c > 0
    mean[nz] = s[nz] / c[nz]
    return mean, c


def split_half_corrected_idio(taker_id, period, y, cells, total_var, seeds):
    """Bias-corrected idiosyncratic variance via cross-wallet half-mean covariance.

    Lifts the i2 covariance-cancels-noise estimator to the PANEL, after period
    demeaning. For each seed: split the FILLS A/B (vectorized coin flip), subtract
    the COMMON period FE from every fill, form per-wallet period-demeaned half-means
    aHat_A_i, aHat_B_i, and take their cross-wallet sample covariance. Because the
    two halves use disjoint fills, the within-cell noise in aHat_A and aHat_B is
    independent and cancels, so Cov(aHat_A, aHat_B) is (essentially) unbiased for
    Var(a_i) -- the STABLE idiosyncratic wallet variance net of the common period
    component. Average over seeds and quote the mean. The denominator is the same
    total_var as the naive block so the corrected share is comparable.

    The period FE is estimated ON ALL FILLS (not per half) so both halves are
    demeaned by the identical c_hat_t; this keeps the common component out of both
    halves symmetrically and does not leak wallet identity between halves.
    """
    taker_id = np.asarray(taker_id, dtype=np.int64)
    period = np.asarray(period, dtype=np.int64)
    y = np.asarray(y, dtype=np.float64)

    # dense wallet / period indices for the fills, consistent with `cells`.
    wallet_ids = cells["wallet_ids"]
    period_ids = cells["period_ids"]
    w_dense_inv = np.searchsorted(wallet_ids, taker_id)
    p_dense_inv = np.searchsorted(period_ids, period)
    n_wallets = wallet_ids.size
    period_fe_lookup = cells["period_fe"]

    cov_estimates = []
    for s in seeds:
        rng = np.random.default_rng(s)
        is_A = rng.random(y.size) < 0.5
        meanA, cA = _period_demeaned_halfmeans(
            taker_id, period, y, is_A, period_fe_lookup, n_wallets,
            w_dense_inv, p_dense_inv)
        meanB, cB = _period_demeaned_halfmeans(
            taker_id, period, y, ~is_A, period_fe_lookup, n_wallets,
            w_dense_inv, p_dense_inv)
        ok = (cA > 0) & (cB > 0) & np.isfinite(meanA) & np.isfinite(meanB)
        if int(ok.sum()) < 3:
            continue
        cov_AB = float(np.cov(meanA[ok], meanB[ok], ddof=1)[0, 1])
        cov_estimates.append(cov_AB)

    if not cov_estimates:
        return {
            K_CORR_IDIO_VAR: float("nan"),
            K_CORR_IDIO_SHARE: float("nan"),
            K_PER_SEED_IDIO_VAR: [],
            "n_seeds_used": 0,
        }
    cov_arr = np.asarray(cov_estimates, dtype=np.float64)
    idio_var = float(cov_arr.mean())
    return {
        K_CORR_IDIO_VAR: idio_var,
        K_CORR_IDIO_VAR_SD: (float(cov_arr.std(ddof=1))
                             if cov_arr.size > 1 else 0.0),
        K_CORR_IDIO_SHARE: (idio_var / total_var if total_var > 0
                            else float("nan")),
        K_PER_SEED_IDIO_VAR: [float(c) for c in cov_arr],
        "n_seeds_used": int(cov_arr.size),
        "note": (f"{K_CORR_IDIO_VAR} = mean over seeds of Cov(aHat_A, aHat_B) "
                 "across wallets, both halves period-demeaned by the SAME common "
                 "FE; the within-cell noise cancels in the cross-wallet covariance"),
    }


# ==================== split-half reliability of the period-demeaned score ====================
def split_half_reliability(taker_id, period, y, cells, rng):
    """Spearman-Brown reliability of the period-demeaned per-wallet score.

    Odd/even within-wallet split of the FILLS (the ks2 reliability trick), then
    period-demean each fill by the COMMON FE, average within wallet per half,
    correlate the two half-scores across wallets (Spearman), and Spearman-Brown the
    half-length Spearman up to a full-length reliability NUMBER. This is a
    DIAGNOSTIC of how much of the per-wallet (idiosyncratic) spread is signal vs
    sampling noise and the input to the rel>0 identification gate. It is NOT applied
    to the corrected idiosyncratic share (the share is bias-corrected by the
    cross-wallet covariance estimator, not disattenuated). Returns (reliability,
    n_wallets, r_half) for one split; the caller averages it over the split seeds.
    """
    taker_id = np.asarray(taker_id, dtype=np.int64)
    period = np.asarray(period, dtype=np.int64)
    y = np.asarray(y, dtype=np.float64)
    n = y.size
    if n == 0:
        return float("nan"), 0, float("nan")

    wallet_ids = cells["wallet_ids"]
    period_ids = cells["period_ids"]
    period_fe_lookup = cells["period_fe"]
    n_wallets = wallet_ids.size

    # randomize before halving (ks2 style), then odd/even within wallet
    order = rng.permutation(n)
    tid = taker_id[order]
    per = period[order]
    yy = y[order]
    w_inv = np.searchsorted(wallet_ids, tid)
    p_inv = np.searchsorted(period_ids, per)
    resid = yy - period_fe_lookup[p_inv]                      # period-demeaned fill

    # within-wallet running position -> odd/even half assignment
    o2 = np.argsort(w_inv, kind="stable")
    inv_s = w_inv[o2]
    counts = np.bincount(w_inv, minlength=n_wallets)
    starts = np.zeros(n_wallets, dtype=np.int64)
    starts[1:] = np.cumsum(counts)[:-1]
    within = np.arange(inv_s.size) - starts[inv_s]
    half_sorted = (within % 2)                                # 0 -> A, 1 -> B
    half_id = np.empty(n, dtype=np.int64)
    half_id[o2] = half_sorted

    is_a = half_id == 0
    sA = np.bincount(w_inv[is_a], weights=resid[is_a], minlength=n_wallets)
    cA = np.bincount(w_inv[is_a], minlength=n_wallets).astype(np.float64)
    sB = np.bincount(w_inv[~is_a], weights=resid[~is_a], minlength=n_wallets)
    cB = np.bincount(w_inv[~is_a], minlength=n_wallets).astype(np.float64)
    ok = (cA > 0) & (cB > 0)
    if int(ok.sum()) < 3:
        return float("nan"), int(ok.sum()), float("nan")
    xa = sA[ok] / cA[ok]
    xb = sB[ok] / cB[ok]
    r_half = spearman(xa, xb)
    if not np.isfinite(r_half):
        return float("nan"), int(ok.sum()), float("nan")
    rel = 2 * r_half / (1 + r_half) if (1 + r_half) != 0 else float("nan")
    return float(rel), int(ok.sum()), float(r_half)


def split_half_reliability_multiseed(taker_id, period, y, cells, seeds):
    """Seed-averaged split-half reliability over N_SPLIT_SEEDS odd/even splits.

    A single split's reliability varies by 0.01-0.03 from seed to seed, so it is
    averaged rather than read off one split. The seeds come from RNG_RELIABILITY and
    NOT from the master seed's split_seeds, which is what the covariance correction
    draws over. Sharing the two streams was the earlier arrangement and it bought
    nothing: averaging removes the same jitter whichever splits it averages, while
    sharing left the declared reliability seed unused and made this file's reliability
    the one of the three that was not drawn from the seed all three name. Returns
    (mean_reliability, n_wallets from the first valid split, mean_r_half, n_seeds_used).
    """
    rels, rhalfs, nwals = [], [], []
    for s in seeds:
        rel, n_rel, r_half = split_half_reliability(
            taker_id, period, y, cells, np.random.default_rng(s))
        if np.isfinite(rel):
            rels.append(rel)
            rhalfs.append(r_half)
            nwals.append(n_rel)
    if not rels:
        return float("nan"), 0, float("nan"), 0
    return (float(np.mean(rels)), int(nwals[0]), float(np.mean(rhalfs)),
            int(len(rels)))


# ==================== label-permutation null on the corrected idiosyncratic variance ====================
def permutation_null_idio(taker_id, period, y, cells, observed_idio_var,
                          n_perm, seed):
    """Shuffle wallet labels and recompute the corrected idiosyncratic variance.

    Breaking the wallet<->score link should collapse the corrected idiosyncratic
    signal variance to ~0. We permute which FILL carries which wallet label (the
    per-wallet sizes / the period structure of the fills are preserved as a
    multiset only via the y-stream; the point is to destroy any real wallet<->y
    association). For each shuffle we form one A/B split (fixed across shuffles)
    and the period-demeaned cross-wallet covariance. One-sided p (observed >= null)
    with the 1/(n_perm+1) floor (i2 / ks2 convention).

    Vectorized: the A/B half-assignment and the period FE per fill are precomputed
    ONCE; each permutation is then a relabel + four weighted bincounts.
    """
    taker_id = np.asarray(taker_id, dtype=np.int64)
    period = np.asarray(period, dtype=np.int64)
    y = np.asarray(y, dtype=np.float64)
    n = y.size

    wallet_ids = cells["wallet_ids"]
    period_ids = cells["period_ids"]
    n_wallets = wallet_ids.size
    if n_wallets < 3 or not np.isfinite(observed_idio_var):
        return {"p_value": float("nan"), "n_perm_valid": 0,
                "null_mean": float("nan"), "null_std": float("nan"),
                "null_p95": float("nan"), "null_max": float("nan"),
                "procedure": None}

    p_inv = np.searchsorted(period_ids, period)
    fe = cells["period_fe"][p_inv]
    resid = y - fe                                            # period-demeaned, fixed

    rng = np.random.default_rng(seed)
    is_A = rng.random(n) < 0.5
    wA = is_A.astype(np.float64)
    wB = 1.0 - wA
    rA = resid * wA
    rB = resid * wB

    # dense wallet label buffer to shuffle in place (counts preserved)
    buf = np.searchsorted(wallet_ids, taker_id).astype(np.int64)
    null_vals = np.empty(n_perm, dtype=np.float64)
    for i in range(n_perm):
        rng.shuffle(buf)
        cA = np.bincount(buf, weights=wA, minlength=n_wallets)
        cB = np.bincount(buf, weights=wB, minlength=n_wallets)
        sA = np.bincount(buf, weights=rA, minlength=n_wallets)
        sB = np.bincount(buf, weights=rB, minlength=n_wallets)
        ok = (cA > 0) & (cB > 0)
        if int(ok.sum()) < 3:
            null_vals[i] = np.nan
            continue
        meanA = sA[ok] / cA[ok]
        meanB = sB[ok] / cB[ok]
        null_vals[i] = float(np.cov(meanA, meanB, ddof=1)[0, 1])

    finite_null = null_vals[np.isfinite(null_vals)]
    if finite_null.size == 0:
        return {"p_value": float("nan"), "n_perm_valid": 0,
                "null_mean": float("nan"), "null_std": float("nan"),
                "null_p95": float("nan"), "null_max": float("nan"),
                "procedure": None}
    # THE COUNTING IS stats.permutation_p AND THE ARITHMETIC IS UNCHANGED. The
    # denominator was already the module's -- both divide by the count of draws that
    # came back finite, and this file is one of the six in the tree that did so before
    # the module existed. The only thing that had to be said out loud is the slack: the
    # module counts `draw >= observed - tol` with tol scaled to the comparison by
    # default, this comparison carries NONE, and abs_tol=0.0 states that rather than
    # inheriting it. The cost of no slack is recorded and unpaid: a permutation that
    # happens to reproduce the observed grouping recomputes the covariance through a
    # different summation order and can land one unit in the last place below it, so it
    # counts as not extreme and the p is biased DOWN, towards significance, on exactly
    # the cells with the thinnest evidence. Adopting a slack would move every p here and
    # is owed its own recompute.
    # The FULL draw array is handed over, NaNs and all, rather than the pre-filtered
    # one: the module drops them itself, divides by what survived, and the block then
    # records how many draws failed instead of leaving the gap invisible.
    procedure = stats.permutation_p(observed_idio_var, null_vals, side="greater",
                                    abs_tol=0.0, n_requested=n_perm,
                                    cell=("panel_common_idio", "idio_var_label_perm"))
    p_value = procedure["p"]
    return {
        "p_value": float(p_value),
        "p_value_floor": 1.0 / (finite_null.size + 1),
        "n_perm_valid": int(finite_null.size),
        "null_mean": float(finite_null.mean()),
        "null_std": (float(finite_null.std(ddof=1))
                     if finite_null.size > 1 else 0.0),
        "null_p95": float(np.percentile(finite_null, 95)),
        "null_max": float(finite_null.max()),
        "observed_outside_null": bool(observed_idio_var
                                      > np.percentile(finite_null, 95)),
        "procedure": procedure,
    }


# ==================== per-slice driver ====================
def _restrict_to_multiperiod(taker_id, period, y, min_periods, K):
    """Keep fills of wallets active in >= min_periods periods AND with >= K total fills.

    Returns (taker_id, period, y) filtered, plus coverage diagnostics. The
    multi-period restriction is what makes a_i separable from u_{i,t}.
    """
    taker_id = np.asarray(taker_id, dtype=np.int64)
    period = np.asarray(period, dtype=np.int64)
    y = np.asarray(y, dtype=np.float64)

    uniq, inv = np.unique(taker_id, return_inverse=True)
    n_w = uniq.size
    # distinct periods per wallet
    # (encode wallet,period pairs, count distinct periods per wallet)
    per_uniq, per_inv = np.unique(period, return_inverse=True)
    n_p = per_uniq.size
    pair = inv.astype(np.int64) * n_p + per_inv.astype(np.int64)
    pair_u = np.unique(pair)
    w_of_pair = (pair_u // n_p).astype(np.int64)
    n_periods_per_wallet = np.bincount(w_of_pair, minlength=n_w).astype(np.int64)
    # total fills per wallet
    fills_per_wallet = np.bincount(inv, minlength=n_w).astype(np.int64)

    keep_wallet = (n_periods_per_wallet >= min_periods) & (fills_per_wallet >= K)
    keep_fill = keep_wallet[inv]
    cov = {
        "n_wallets_total": int(n_w),
        "n_wallets_multiperiod_geK": int(keep_wallet.sum()),
        "n_fills_total": int(taker_id.size),
        "n_fills_kept": int(keep_fill.sum()),
        "median_periods_per_kept_wallet": (
            float(np.median(n_periods_per_wallet[keep_wallet]))
            if keep_wallet.any() else float("nan")),
        "median_fills_per_kept_wallet": (
            float(np.median(fills_per_wallet[keep_wallet]))
            if keep_wallet.any() else float("nan")),
    }
    return taker_id[keep_fill], period[keep_fill], y[keep_fill], cov


def _drop_top_whales(taker_id, period, y, n_drop):
    """Drop the top-n_drop wallets by total fill count; return filtered fills."""
    uniq, inv, counts = (lambda u, i: (u, i, np.bincount(i, minlength=u.size)))(
        *np.unique(taker_id, return_inverse=True))
    if uniq.size <= n_drop + 3:
        return taker_id, period, y, 0
    whales = np.argsort(counts)[::-1][:n_drop]
    whale_mask = np.zeros(uniq.size, dtype=bool)
    whale_mask[whales] = True
    keep = ~whale_mask[inv]
    return taker_id[keep], period[keep], y[keep], int(n_drop)


def run_slice_at_K(taker_id, period, y, K, split_seeds, rel_seeds, perm_seed,
                   n_perm, drop_whales=False, n_drop=N_DROP_WHALES):
    """Full panel common/idiosyncratic decomposition for one slice at one K.

    Restricts to multi-period wallets with >= K total fills, builds the per-cell
    means + period FE, runs the naive decomposition, the split-half-corrected
    idiosyncratic variance, the split-half reliability, and the label-permutation
    null. If drop_whales, the top-n_drop wallets by fill count are removed FIRST.
    Returns a populated dict (NaNs rather than raising on a thin set).

    THREE STREAMS, NAMED, because each answers a different question and mixing them
    hides which one an answer moved with: split_seeds (from the master seed) drive the
    covariance bias correction, rel_seeds (from the reliability seed) drive the
    reliability diagnostic, and perm_seed drives the label-permutation null.
    """
    if drop_whales:
        taker_id, period, y, n_dropped = _drop_top_whales(
            taker_id, period, y, n_drop)
    else:
        n_dropped = 0

    tid, per, yy, cov = _restrict_to_multiperiod(
        taker_id, period, y, MIN_PERIODS, K)
    cov["n_whales_dropped"] = n_dropped
    out = {"K": int(K), "coverage": cov}

    if cov["n_wallets_multiperiod_geK"] < 3 or tid.size < 6:
        out["naive"] = {"note": f"fewer than 3 multi-period wallets with >= {K} fills"}
        out["split_half_corrected"] = {K_CORR_IDIO_VAR: float("nan"),
                                       K_CORR_IDIO_SHARE: float("nan")}
        out["reliability"] = {K_RELIABILITY: float("nan"), "n_wallets": 0,
                              K_R_HALF: float("nan")}
        out["placebo"] = {"p_value": float("nan")}
        out["idiosyncratic_component_identified"] = False
        return out

    cells = _cell_means(tid, per, yy)
    naive = naive_panel_decomposition(cells)
    corrected = split_half_corrected_idio(
        tid, per, yy, cells, naive[K_TOTAL_VAR], split_seeds)
    # Averaged over the reliability seed's own splits, not the master seed's.
    rel, n_rel, r_half, n_rel_seeds = split_half_reliability_multiseed(
        tid, per, yy, cells, rel_seeds)
    placebo = permutation_null_idio(
        tid, per, yy, cells, corrected[K_CORR_IDIO_VAR],
        n_perm=n_perm, seed=perm_seed)

    out["naive"] = naive
    out["split_half_corrected"] = corrected
    out["reliability"] = {K_RELIABILITY: rel, "n_wallets": n_rel,
                          K_R_HALF: r_half, "reliability_seeds": list(rel_seeds),
                          "n_seeds_used": n_rel_seeds,
                          "method": ("Spearman-Brown on period-demeaned odd/even "
                                     "split, averaged over the reliability seed's "
                                     "own splits (settings.RELIABILITY_SEED), not "
                                     "over the master seed's; DIAGNOSTIC / >0 gate "
                                     "only, NOT applied to the corrected share")}
    out["placebo"] = placebo

    # HONEST per-cell read (the BH-q gate is applied across the family in main).
    idio_share = corrected.get(K_CORR_IDIO_SHARE, float("nan"))
    common_share = naive.get(K_COMMON_SHARE, float("nan"))
    p_val = placebo.get("p_value", float("nan"))
    cell_ok = bool(
        np.isfinite(idio_share) and idio_share > 0.0
        and np.isfinite(rel) and rel > 0.0
        and np.isfinite(p_val) and p_val <= 0.05)
    out["idiosyncratic_component_identified"] = cell_ok
    out["read_inputs"] = {
        K_CORR_IDIO_SHARE: idio_share,
        K_COMMON_SHARE: common_share,
        K_RELIABILITY: rel,
        "placebo_p": p_val,
        "rule": (f"TRUE requires {K_CORR_IDIO_SHARE}>0 AND {K_RELIABILITY}>0 AND "
                 "placebo p<=0.05 (BH-q across the family applied in _meta)"),
    }
    return out


# ==================== the headline note, computed from the cells ====================
def _wallets_on_one_coin(taker_id, coin, restrict_to=None):
    """(wallets, of them on exactly one coin) over a named wallet population.

    restrict_to is a sorted array of wallet ids, so the caller states the population
    instead of leaving it to be guessed. The panel-wide count and the count over the
    wallets that survive the cell restriction are different quantities and the note
    that quotes either has to say which.
    """
    taker_id = np.asarray(taker_id, dtype=np.int64)
    coin = np.asarray(coin, dtype=np.int64)
    if restrict_to is not None:
        sel = np.isin(taker_id, restrict_to)
        taker_id, coin = taker_id[sel], coin[sel]
    if taker_id.size == 0:
        return 0, 0
    uniq, inv = np.unique(taker_id, return_inverse=True)
    n_codes = int(coin.max()) + 1
    pairs = np.unique(inv.astype(np.int64) * n_codes + coin)
    n_coins = np.bincount((pairs // n_codes).astype(np.int64), minlength=uniq.size)
    return int(uniq.size), int((n_coins == 1).sum())


def _headline_note(results, taker_id, coin, period, y):
    """The headline note with every number in it read off this run's own cells."""
    def share(slice_name, K):
        return results[slice_name]["by_K"][str(K)]["full"][
            "split_half_corrected"].get(K_CORR_IDIO_SHARE, float("nan"))

    def total_var(slice_name, K):
        return results[slice_name]["by_K"][str(K)]["full"]["naive"].get(
            K_TOTAL_VAR, float("nan"))

    kmin = min(K_LIST)
    percoin = "; ".join(
        f"at the {K}-fill floor " + ", ".join(
            f"{share(s, K):.1%} on {s}" for s in ("BTC", "ETH", "SOL"))
        for K in K_LIST)
    pooled = ", ".join(f"{share('pooled', K):.1%} at {K} fills" for K in K_LIST)
    solbtc = " and ".join(
        f"{total_var('SOL', K) / total_var('BTC', K):.1f}x at the {K}-fill floor"
        for K in K_LIST)

    n_panel, one_panel = _wallets_on_one_coin(taker_id, coin)
    kept_tid, _, _, _ = _restrict_to_multiperiod(taker_id, period, y,
                                                 MIN_PERIODS, kmin)
    n_cell, one_cell = _wallets_on_one_coin(taker_id, coin,
                                            restrict_to=np.unique(kept_tid))
    return HEADLINE_NOTE_FRAME.format(
        percoin=percoin, pooled=pooled, kmin=kmin, solbtc=solbtc,
        panel_one_coin=f"{one_panel / max(1, n_panel):.1%}", n_panel=n_panel,
        cell_one_coin=f"{one_cell / max(1, n_cell):.1%}", n_cell=n_cell)


# ==================== I/O + main ====================
def _load_panel_npz(data_root):
    # The root stays whatever --data-root / CAP_DATA_ROOT resolved to; only the name of
    # the file and the "it is missing, run this" message move into panel_io, which names
    # panel_persistence.py --build as the producer where this function said only "build
    # it first". The load stays here because build.py derives this script's input edge
    # from the argument of np.load.
    path = os.path.join(P.data_root(data_root), PANEL_NPZ_NAME)
    P.require_present("panel", path)
    z = np.load(path, allow_pickle=False)
    return z, path


def main():
    ap = argparse.ArgumentParser(
        description="Panel common-vs-idiosyncratic decomposition of per-counterparty "
                    "10s toxicity across the three 10-day windows.")
    ap.add_argument(
        "--data-root", default=os.environ.get("CAP_DATA_ROOT", HERE),
        help="directory holding %s / %s / output (default: this script's dir or "
             "$CAP_DATA_ROOT)." % (PANEL_NPZ_NAME, OUT_NAME))
    args = ap.parse_args()
    started = artifact.start_clock()
    data_root = os.path.abspath(args.data_root)

    z, npz_path = _load_panel_npz(data_root)
    taker_id = z["taker_id"].astype(np.int64)
    coin = z["coin"].astype(np.int8)
    period = z["period"].astype(np.int64)               # NEW panel column, YYYYMM
    # Through panel_io: the window comes from settings.py and the lens from the FILE, so
    # this read cannot pick a book-mid column out of a trade-print panel by accident.
    mo_score = P.score(z, "panel")     # trade-print headline markout, bps

    # ---- pin to the paper's canonical Aug/Oct/Dec windows (CANONICAL_PERIODS) ----
    # panel_markouts.npz was rebuilt from 3 to 8 windows; this decomposition consumes
    # every period in the npz, so restrict the loaded fills to the three canonical windows
    # so a re-run reproduces the committed results. Idempotent: a no-op when the npz
    # already holds only those three.
    _keep = np.isin(period, np.asarray(CANONICAL_PERIODS, dtype=np.int64))
    if not bool(_keep.all()):
        taker_id = taker_id[_keep]
        coin = coin[_keep]
        period = period[_keep]
        mo_score = mo_score[_keep]

    # Keep only fills with a finite 10s markout (cannot enter a variance otherwise).
    valid = np.isfinite(mo_score)
    taker_id = taker_id[valid]
    coin = coin[valid]
    period = period[valid]
    mo_score = mo_score[valid]

    # Two deterministic seed schedules, one per declared seed. The master seed drives
    # the A/B splits of the covariance bias correction and every permutation null; the
    # reliability seed drives the odd/even splits of the reliability diagnostic alone.
    # They are drawn from separate generators rather than from one stream so that
    # inserting a cell cannot shift the other schedule.
    base = np.random.default_rng(SEED)
    split_seeds = [int(s) for s in base.integers(0, 2**31 - 1, size=N_SPLIT_SEEDS)]
    rel_base = np.random.default_rng(RNG_RELIABILITY)
    rel_seeds = [int(s) for s in rel_base.integers(0, 2**31 - 1, size=N_SPLIT_SEEDS)]

    taker_map_path = os.path.join(data_root, TAKER_MAP_NAME)
    n_takers_mapped = 0
    if os.path.exists(taker_map_path):
        try:
            with open(taker_map_path) as fh:
                obj = json.load(fh)
                n_takers_mapped = len(obj.get("map", obj)) if isinstance(obj, dict) else 0
        except (ValueError, OSError):
            n_takers_mapped = 0

    periods_present = sorted(int(p) for p in np.unique(period))

    results = {
        "_meta": {
            "object": ("panel common-vs-idiosyncratic variance decomposition of "
                       f"per-counterparty {H.HEADLINE_HORIZON_S}s toxicity "
                       f"(trade-print {H.headline_print_col()})"),
            "horizon_s": H.HEADLINE_HORIZON_S,
            "input_npz": os.path.basename(npz_path),
            "out_file": OUT_NAME,
            "model": ("ybar_{i,t} = mu + c_t + a_i + u_{i,t}; common = Var(c_t), "
                      "idiosyncratic = Var(a_i) after period demeaning, within = Var(u)"),
            "estimator": ("period FE for the common component; naive between-wallet "
                          "variance of period-demeaned cell means (upward-biased) plus "
                          "a split-half cross-wallet covariance bias correction "
                          "Cov(aHat_A, aHat_B) (KSS-style, noise cancels) for the "
                          "idiosyncratic component"),
            "panel_periods_expected": list(PANEL_PERIODS),
            "panel_periods_present": periods_present,
            "coin_codes": COIN_CODES,
            "min_periods": MIN_PERIODS,
            "K_list": list(K_LIST),
            "master_seed": SEED,
            "reliability_seed_base": RNG_RELIABILITY,
            "split_seeds": split_seeds,
            "reliability_seeds": rel_seeds,
            "seed_streams": ("split_seeds drive the covariance bias correction and "
                             "come from master_seed; reliability_seeds drive the "
                             "reliability diagnostic and come from "
                             "reliability_seed_base; the permutation nulls draw "
                             "their own seeds from master_seed"),
            "n_split_seeds": N_SPLIT_SEEDS,
            "n_perm": N_PERM,
            "p_floor": 1.0 / (N_PERM + 1),
            "n_drop_whales": N_DROP_WHALES,
            "fdr_alpha": FDR_ALPHA,
            "markout_sign": ("positive = taker profited = maker adversely selected "
                             "(build convention)"),
            "n_takers_mapped": n_takers_mapped,
            "n_fills_valid": int(taker_id.size),
            "interpretation_held": INTERPRETATION_HELD,
            # Filled after the cells exist, because every number in it is read off
            # them rather than typed. See _headline_note.
            "headline_note": None,
            "claim_note": CLAIM_NOTE,
            "common_leg_note": COMMON_LEG_NOTE,
            "share_correction_method": (f"{K_CORR_IDIO_SHARE} = {K_CORR_IDIO_VAR} "
                                        f"/ {K_TOTAL_VAR}; {K_CORR_IDIO_VAR} is "
                                        "bias-corrected by the cross-wallet "
                                        "half-mean covariance estimator, NOT by "
                                        "Spearman-Brown disattenuation. Reliability "
                                        "is a diagnostic / >0 gate only."),
            "field_suffix_style": H.FIELD_SUFFIX_STYLE,
            "field_suffix_note": (
                "Every level, variance, share and reliability below carries "
                f"_{H.HEADLINE_HORIZON_S}s_{LENS}: the window it was measured on "
                "and the reference price it was measured against. Counts, p-values "
                "and q-values do not, because they describe the test rather than "
                "the markout."),
            # The settings this run computed under, as the KEYWORDS for
            # settings.fingerprint rather than as the block. artifact.write builds the
            # block once and puts it in _meta, so the record has one home; this key is
            # popped before the write and never reaches the file under this name.
            #
            # n_perm is passed to CONFIRM the declared budget rather than to depart from
            # it: settings.py marks N_PERM a migrating declaration, so a fingerprint
            # states it only when the caller says what its run used. The p-value floor
            # 1/(N+1) is stated beside it, because a p reported at the floor has to be
            # readable as the floor.
            "settings_fingerprint_kwargs": dict(
                h=H.HEADLINE_HORIZON_S, lens=LENS,
                markout_column=H.headline_print_col(),
                windows_analysed=list(CANONICAL_PERIODS),
                **SETTINGS_OVERRIDES),
        }
    }

    slices = {"BTC": coin == 0, "ETH": coin == 1, "SOL": coin == 2,
              "pooled": np.ones(coin.size, dtype=bool)}

    # collect (cell-label, placebo p) for the BH-FDR family across slices x K.
    family = []          # list of (slice, K, p_value, ref-to-cell-dict)

    for sname, smask in slices.items():
        tid = taker_id[smask]
        per = period[smask]
        y = mo_score[smask]
        slice_block = {
            "n_fills": int(tid.size),
            "n_wallets_total": int(np.unique(tid).size) if tid.size else 0,
            "periods_present": sorted(int(p) for p in np.unique(per)) if per.size else [],
            "by_K": {},
        }
        for K in K_LIST:
            perm_seed = int(base.integers(0, 2**31 - 1))
            full = run_slice_at_K(
                tid, per, y, K, split_seeds, rel_seeds, perm_seed, N_PERM,
                drop_whales=False)

            # whale-robustness: same K, top-10 wallets by fill count removed first.
            wperm_seed = int(base.integers(0, 2**31 - 1))
            whale = run_slice_at_K(
                tid, per, y, K, split_seeds, rel_seeds, wperm_seed, N_PERM,
                drop_whales=True, n_drop=N_DROP_WHALES)

            cell = {
                "full": full,
                # settings.whale_drop makes the CRITERION part of the key: dropping
                # the ten largest by fill count answers "is this ten bots?", by
                # notional it answers "is this a volume artifact". Different
                # questions, so the artifact may not say "top 10" without saying
                # top 10 by what. This block drops by fill count.
                WHALE_KEY: {
                    "coverage": whale["coverage"],
                    K_COMMON_SHARE: whale["naive"].get(
                        K_COMMON_SHARE, float("nan")),
                    K_IDIO_NAIVE_SHARE: whale["naive"].get(
                        K_IDIO_NAIVE_SHARE, float("nan")),
                    K_CORR_IDIO_SHARE: whale["split_half_corrected"].get(
                        K_CORR_IDIO_SHARE, float("nan")),
                    K_CORR_IDIO_VAR: whale["split_half_corrected"].get(
                        K_CORR_IDIO_VAR, float("nan")),
                    K_RELIABILITY: whale["reliability"].get(
                        K_RELIABILITY, float("nan")),
                    "placebo_p_value": whale["placebo"].get("p_value", float("nan")),
                    "idiosyncratic_component_identified": whale.get(
                        "idiosyncratic_component_identified", False),
                },
            }
            slice_block["by_K"][str(K)] = cell
            family.append((sname, K, full["placebo"].get("p_value"), full))
        results[sname] = slice_block

    # ---- BH-FDR over the placebo p-values across the {slices} x {K} family ----
    # The step-up correction comes from stats.py rather than from the copy that stood
    # in this file. It costs no q: stats._legacy_bh_loop is that copy, and the self-test
    # there runs the two against each other on 200 random families with ties and
    # untestable cells. What the module adds is the CUTOFF the q-values were judged
    # against, which the local copy did not return.
    bh = stats.benjamini_hochberg(
        [p for (_, _, p, _) in family], alpha=FDR_ALPHA,
        family="panel idiosyncratic placebo p-values across "
               "{BTC,ETH,SOL,pooled} x K")
    bh_q = bh["q"]
    n_survive = 0
    for (sname, K, p, cell_ref), q in zip(family, bh_q):
        cell_ref["placebo_q_value_bh"] = q
        survives = bool(q is not None and q <= FDR_ALPHA)
        # tighten the honest per-cell read with the FDR-corrected q.
        prior = bool(cell_ref.get("idiosyncratic_component_identified", False))
        idio_share = cell_ref.get("split_half_corrected", {}).get(
            K_CORR_IDIO_SHARE, float("nan"))
        rel = cell_ref.get("reliability", {}).get(K_RELIABILITY, float("nan"))
        fdr_ok = bool(
            np.isfinite(idio_share) and idio_share > 0.0
            and np.isfinite(rel) and rel > 0.0 and survives)
        cell_ref["idiosyncratic_component_identified_fdr"] = fdr_ok
        if fdr_ok:
            n_survive += 1

    fdr_summary = dict(
        bh, q=None,
        q_note="the q-values are on the cells, under placebo_q_value_bh; this block "
               "holds the procedure, the family and the cutoff applied to them",
        n_cells_idiosyncratic_identified_fdr=n_survive,
        n_perm=N_PERM,
        p_floor=1.0 / (N_PERM + 1),
    )
    results["_meta"]["fdr_summary"] = fdr_summary
    results["_meta"]["headline_note"] = _headline_note(
        results, taker_id, coin, period, mo_score)

    # The scope is read off the run: the fill count and the wallet count this pass
    # actually mapped, the windows the loader kept, and the coin slices that were not
    # empty. The fingerprint block moves out of the payload's _meta and into the one
    # _meta artifact.write owns, so it has a single home.
    settings_used = results["_meta"].pop("settings_fingerprint_kwargs")
    out_path = artifact.write(
        OUT_NAME, results,
        script=__file__,
        # Both files this run opened. The taker map is recorded even when it is absent
        # -- artifact.input_record writes present=false rather than raising -- because
        # "the wallet count came from a map that was not there" is a fact about the
        # numbers and n_takers_mapped silently reads 0 without it.
        inputs=[npz_path, taker_map_path],
        scope={
            "population": (
                f"{int(taker_id.size)} taker fills and {n_takers_mapped} wallets, "
                f"restricted to wallets active in at least {MIN_PERIODS} windows; "
                f"every cell repeated at each fill floor in {list(K_LIST)}"),
            "window": f"{len(CANONICAL_PERIODS)} ten-day windows: "
                      f"{sorted(CANONICAL_PERIODS)}",
            "coins": sorted(k for k in ("BTC", "ETH", "SOL") if k in results),
        },
        settings=settings_used,
        started=started,
        out_dir=data_root)

    _print_summary(results, out_path)


# -------------------- printed summary --------------------
def _fmt(x, nd=4):
    return f"{x:.{nd}f}" if isinstance(x, float) and np.isfinite(x) else "n/a"


def _print_summary(results, out_path):
    meta = results["_meta"]
    print("=" * 100)
    print("PANEL COMMON-vs-IDIOSYNCRATIC DECOMPOSITION of per-counterparty 10s toxicity")
    print("=" * 100)
    print(f"  model        : {meta['model']}")
    print(f"  valid fills  : {meta['n_fills_valid']:,}   "
          f"periods present: {meta['panel_periods_present']}")
    print("  common = Var(period FE) ; idiosyncratic = Var(a_i) net of period FE")
    print("  (split-half corrected, noise cancels) ; within = residual.")
    print("  +ve markout = taker profited = maker adversely selected.")
    print("-" * 100)
    print("  INTERPRETATION HELD: trade-print mo10, so the idiosyncratic MAGNITUDE")
    print("  mixes adverse selection with bid-ask bounce / earned spread. This is a")
    print("  decomposition of the VARIANCE STRUCTURE (common vs idiosyncratic), not a")
    print("  claim that the idiosyncratic size is all adverse selection.")
    print("=" * 100)

    hdr = (f"  {'slice':<7} {'K':>4} {'wal':>6} {'med_per':>7} {'com_sh':>8} "
           f"{'idio_naive':>10} {'idio_corr':>10} {'reliab':>7} {'p_perm':>8} "
           f"{'q_bh':>7} {'IDENT':>6}")
    print(hdr)
    print("-" * len(hdr))
    for sname in ("BTC", "ETH", "SOL", "pooled"):
        blk = results.get(sname)
        if not isinstance(blk, dict):
            continue
        for K in K_LIST:
            cell = blk.get("by_K", {}).get(str(K))
            if cell is None:
                continue
            full = cell["full"]
            cov = full.get("coverage", {})
            naive = full.get("naive", {})
            corr = full.get("split_half_corrected", {})
            rel = full.get("reliability", {})
            plac = full.get("placebo", {})
            ident = full.get("idiosyncratic_component_identified_fdr",
                             full.get("idiosyncratic_component_identified", False))
            print(
                f"  {sname:<7} {K:>4} "
                f"{cov.get('n_wallets_multiperiod_geK', 0):>6} "
                f"{_fmt(cov.get('median_periods_per_kept_wallet'), 1):>7} "
                f"{_fmt(naive.get(K_COMMON_SHARE), 4):>8} "
                f"{_fmt(naive.get(K_IDIO_NAIVE_SHARE), 4):>10} "
                f"{_fmt(corr.get(K_CORR_IDIO_SHARE), 4):>10} "
                f"{_fmt(rel.get(K_RELIABILITY), 3):>7} "
                f"{_fmt(plac.get('p_value'), 4):>8} "
                f"{_fmt(full.get('placebo_q_value_bh'), 4):>7} "
                f"{('YES' if ident else 'no'):>6}")
    print("-" * len(hdr))
    fdr = meta.get("fdr_summary", {})
    print(f"  BH-FDR: {fdr.get('n_cells_idiosyncratic_identified_fdr', 0)} of "
          f"{fdr.get('family_size', 0)} cells identify a real idiosyncratic "
          f"component (q<={fdr.get('alpha')}); p-floor={_fmt(fdr.get('p_floor'), 5)}")
    print(f"  com_sh={K_COMMON_SHARE} | idio_corr={K_CORR_IDIO_SHARE} "
          f"(= {K_CORR_IDIO_VAR}/{K_TOTAL_VAR}, cross-wallet")
    print("  covariance bias-corrected, NOT Spearman-Brown disattenuated) | "
          "reliab=seed-averaged Spearman-Brown (DIAGNOSTIC / >0 gate only).")
    print("  IDENT = idiosyncratic component identified (corrected share>0 AND "
          "reliability>0 AND BH-q<=0.05).")
    # Printed from the computed note rather than restated, so the screen and the
    # artifact cannot drift apart -- they did, and the screen was the stale one.
    for line in (meta.get("headline_note") or "").split(". "):
        if line.strip():
            print(f"  {line.strip().rstrip('.')}.")
    print("  The COMMON (period) leg on only 3 windows is under-identified and is "
          "EXCLUDED from the gate. A small identified")
    print("  share does NOT imply economic dominance.")
    print("=" * 100)
    print(f"  results -> {os.path.basename(out_path)}")


if __name__ == "__main__":
    main()
