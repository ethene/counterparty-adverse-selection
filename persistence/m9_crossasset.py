"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-19
References: Hyperliquid node-data S3 archive; Zenodo 18184441 (Albers et al. 2026).
"""

# ---------------------------------------------------------------------------
# OBJECT M9 — CROSS-ASSET TOXICITY PORTABILITY
#
# Question: is a wallet that is toxic in BTC also toxic in ETH? If counterparty
# toxicity is a property of the TRADER (their information / horizon / model)
# rather than of the asset, then a wallet's per-fill adverse-selection cost in
# BTC should predict its cost in ETH. A maker that has only ever seen a wallet
# in one coin could then pre-emptively widen against it in the other.
#
# This object is CEX-hard: it needs a single persistent wallet identity observed
# across two markets, which centralized venues do not expose. On Hyperliquid the
# on-chain taker address is the same primitive in every coin, so the same wallet
# can be tracked from BTC to ETH directly.
#
# We restrict to wallets active in BOTH coins with at least K trades in EACH
# coin and measure each wallet's mean signed taker markout in BTC and in ETH
# separately, then report the cross-coin rank correlation of those two toxicity
# vectors. The headline is the Spearman correlation; Pearson is shown alongside
# for comparison. mo10 is the primary horizon (the headline cross-asset number),
# mo60 a robustness one.
#
# IMPORTANT — the cross-coin Spearman is NOT a single stable magnitude. As the
# per-coin trade floor K rises, each wallet's mean markout is averaged over more
# fills, so the per-wallet toxicity estimate carries less measurement noise and
# the cross-coin rank correlation climbs MONOTONICALLY. On mo10 it runs roughly
# 0.16 (K=10) -> 0.24 (K=20) -> 0.52 (K=50) -> 0.72 (K=100) -> 0.77 (K=200).
# That is noise-averaging, not a portability "coefficient": a high number at
# large K reflects cleaner per-wallet estimates on the shrinking panel of very
# active wallets, not a stronger trader-level property. We therefore report the
# FULL K-curve (K in {10, 20, 50, 100, 200}) rather than quoting one cell, and
# read the QUALITATIVE result (positive, monotone, far outside the null) instead
# of any one magnitude such as 0.52.
#
# The PRE-REGISTERED headline cell is K=50 on mo10; the rest of the K-sweep is a
# MONOTONICITY check, not a set of independent confirmations. Significance is
# judged by a label-permutation placebo: the BTC->ETH wallet pairing is shuffled
# (fixed seed, 2000 shuffles) and the observed Spearman is ranked against the
# shuffled null. Whale robustness drops the top-10 wallets by total trade count
# and confirms the sign of the correlation is unchanged. A per-object
# Benjamini-Hochberg FDR block is reported over the placebo p-values of all cells
# (mirroring i3) so the many-cell sweep is multiplicity-controlled.
#
# IMPORTANT — the K-cells are CORRELATED NESTED THRESHOLDS on the SAME wallets
# (the K=200 panel is a subset of the K=100 panel, which is a subset of the K=50
# panel, ...), so "10/10 cells reject the null after BH" is NOT ten independent
# pieces of evidence. The cells re-ask one question on near-identical, deeply
# overlapping samples and their placebo p-values are floored at 1/(2000+1); the
# joint rejection conveys roughly ONE cell of evidence. We therefore LEAD with the
# pre-registered K=50 cell and read the K-sweep only as a monotonicity / noise-
# averaging check, never as ten confirmations to be summed.
#
# numpy-only. No SciPy: Spearman is Pearson on ranks (average ranks for ties),
# Pearson is the plain product-moment correlation, and the placebo is a manual
# permutation loop. Nothing is plotted; the per-wallet vectors are summarised
# into the JSON so a later figure step can redraw the scatter.
#
# Sign convention (from the build script): mo* is the SIGNED taker markout in
# basis points, positive = taker profited = maker adverse-selected. So a higher
# per-wallet mean = a more toxic counterparty.
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
# Located by panel_io rather than joined here, so the one place that knows where
# the markout panels live is the one place that has to change if they move.
NPZ_PATH = os.path.join(P.data_root(), "quickwin_markouts.npz")
OUT_PATH = os.path.join(HERE, "m9_crossasset_results.json")

# The scored window comes from settings.py; the 60s column stays beside it as the
# retained robustness companion, named so nothing downstream has to guess which is
# which. Result keys are built from these two, so if the declared window ever moves,
# the keys move with it instead of keeping a stale name over new numbers.
HEADLINE_COL = H.headline_print_col()
CONTRAST_COL = H.companion_print_col()

# The pre-registered cell names its column and its wallet floor, and both halves are
# built, so the cell that the text calls the headline and the cell the code looks up
# can never come apart.
HEADLINE_K = 50
PRE_REGISTERED_CELL = f"{HEADLINE_COL}_K{HEADLINE_K}"

COIN_BTC = 0
COIN_ETH = 1
COIN_NAME = {COIN_BTC: "BTC", COIN_ETH: "ETH"}   # int8 code -> symbol

# Minimum trade counts per coin required for a wallet to enter the dual-coin
# panel. Reported as a FULL curve so the noise-averaging trend is visible and no
# single cell is quoted as "the" portability coefficient. READ from settings.py, which
# declares the ladder per consumer because the curve IS this file's finding and a scalar
# floor cannot express it. The rungs are the same five, so no cell moves.
K_VALUES = H.wallet_fill_floor("m9_crossasset", "sweep")

# Permutation placebo: fixed seed and shuffle count. The p-value floor is
# 1 / (n_shuffles + 1) because the observed statistic is counted as one draw. The seed is
# READ from settings.py and is the same 20260619 this file has always drawn from.
SEED = H.seed_for("m9_crossasset")
N_SHUFFLES = 2000

# Whale-robustness: number of highest-total-trade-count wallets to drop.
N_WHALES_DROP = 10


# ---------------------------------------------------------------------------
# Correlation primitives (numpy-only, no SciPy)
# ---------------------------------------------------------------------------
def _rankdata_average(a):
    """Rank a 1-D array with ties resolved by AVERAGE rank (as SciPy does).

    Ranks are 1..n. Tied values receive the mean of the ranks they span, so the
    rank vector has the same total whether or not there are ties. Used to turn
    Pearson into Spearman.
    """
    a = np.asarray(a, dtype=np.float64)
    n = a.size
    if n == 0:
        return np.empty(0, dtype=np.float64)
    order = np.argsort(a, kind="mergesort")      # stable, so ties group cleanly
    ranks = np.empty(n, dtype=np.float64)
    sorted_a = a[order]
    # positional ranks 1..n in sorted order
    pos = np.arange(1, n + 1, dtype=np.float64)
    # average ranks within each run of equal values
    i = 0
    while i < n:
        j = i + 1
        while j < n and sorted_a[j] == sorted_a[i]:
            j += 1
        ranks[order[i:j]] = pos[i:j].mean()
        i = j
    return ranks


def pearson(x, y):
    """Plain product-moment correlation of two equal-length finite vectors.

    Returns NaN if either vector has zero variance or fewer than 2 points.
    """
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    n = x.size
    if n < 2 or y.size != n:
        return float("nan")
    xc = x - x.mean()
    yc = y - y.mean()
    denom = np.sqrt(np.sum(xc * xc) * np.sum(yc * yc))
    if denom <= 0:
        return float("nan")
    return float(np.sum(xc * yc) / denom)


def spearman(x, y):
    """Spearman rank correlation = Pearson on average-rank-transformed inputs."""
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    if x.size < 2 or y.size != x.size:
        return float("nan")
    return pearson(_rankdata_average(x), _rankdata_average(y))


# The Benjamini-Hochberg correction used to be written out here, one of six copies of
# one procedure in this tree. It is now stats.benjamini_hochberg and this file holds no
# copy, because six spellings of one correction is six chances for one of them to drift
# and no way to answer "do two scripts apply the same test" other than by reading both.
#
# The consolidation moves no number here, and that is a property of this particular copy
# rather than a general claim. The spelling this file carried was the common one leaf for
# leaf: sort ascending, q_(i) = p_(i) * m / i, running minimum from the largest p
# downward, clip to [0, 1], carry a non-finite p through without counting it in m. The
# only difference is that mergesort was named where the module names "stable", and those
# are the same sort. What the module adds is the THRESHOLD -- the bar the correction
# actually applied, and the rank-one bar alpha/m a single cell has to clear on its own --
# which the local copy never returned and which a reader cannot supply, because it
# depends on the family size and this work's families run from 4 cells to 448.


def spearman_from_ranks(rx, ry):
    """Spearman when the rank vectors are precomputed (Pearson on the ranks).

    Used in the permutation loop so the rank transform of the fixed BTC vector
    is computed once and only the ETH side is reshuffled. Shuffling a rank
    vector is a permutation of the SAME values, so its mean/variance are
    invariant and the per-shuffle work is just one Pearson on ranks.
    """
    return pearson(rx, ry)


# ---------------------------------------------------------------------------
# Per-wallet aggregation within one coin
# ---------------------------------------------------------------------------
def per_wallet_mean(taker_id, value):
    """Mean of `value` per wallet within a single coin slice.

    taker_id : int array of wallet codes for this coin's trades.
    value    : the per-trade quantity to average (a markout, in bps).

    Returns (wallet_ids, wallet_count, wallet_mean), aligned and sorted by
    wallet id. Only finite values contribute to the per-wallet mean and to the
    per-wallet count, so a wallet's "trade count" here means trades with a
    usable markout at this horizon.
    """
    if taker_id.size == 0:
        z = np.empty(0, dtype=np.float64)
        return np.empty(0, dtype=np.int64), z, z.copy()
    uniq, inv = np.unique(taker_id, return_inverse=True)
    count = np.zeros(uniq.size, dtype=np.float64)
    total = np.zeros(uniq.size, dtype=np.float64)
    val = np.asarray(value, dtype=np.float64)
    finite = np.isfinite(val)
    np.add.at(count, inv[finite], 1.0)
    np.add.at(total, inv[finite], val[finite])
    mean = np.full(uniq.size, np.nan, dtype=np.float64)
    nz = count > 0
    mean[nz] = total[nz] / count[nz]
    return uniq, count, mean


# ---------------------------------------------------------------------------
# Dual-coin panel construction
# ---------------------------------------------------------------------------
def build_dual_panel(btc_ids, btc_count, btc_mean,
                     eth_ids, eth_count, eth_mean, k):
    """Wallets present in BOTH coins with >= k trades in EACH coin.

    Intersects the two per-coin wallet sets, applies the per-coin count floor,
    and returns aligned arrays for the surviving wallets:
        ids, btc_mean_sel, eth_mean_sel, btc_count_sel, eth_count_sel
    All vectors are ordered by wallet id and carry only finite means.
    """
    # qualifying wallets in each coin (count floor + finite mean)
    btc_ok = btc_ids[(btc_count >= k) & np.isfinite(btc_mean)]
    eth_ok = eth_ids[(eth_count >= k) & np.isfinite(eth_mean)]
    common = np.intersect1d(btc_ok, eth_ok, assume_unique=True)
    if common.size == 0:
        z = np.empty(0, dtype=np.float64)
        return (np.empty(0, dtype=np.int64), z, z.copy(),
                z.copy(), z.copy())

    # map common ids back to their per-coin rows (ids are sorted by np.unique)
    btc_pos = np.searchsorted(btc_ids, common)
    eth_pos = np.searchsorted(eth_ids, common)
    return (common,
            btc_mean[btc_pos], eth_mean[eth_pos],
            btc_count[btc_pos], eth_count[eth_pos])


# ---------------------------------------------------------------------------
# Permutation placebo
# ---------------------------------------------------------------------------
def permutation_pvalue(btc_vec, eth_vec, observed_spearman, seed, n_shuffles):
    """Two-sided permutation p for the cross-coin Spearman.

    The null is "no wallet-level link between BTC and ETH toxicity". We hold the
    BTC vector fixed and shuffle which ETH value is paired with which wallet,
    recomputing Spearman each time. The p-value is the fraction of shuffles whose
    |Spearman| is at least the observed |Spearman|, with the observed statistic
    counted as one draw (so p is floored at 1 / (n_shuffles + 1)).

    Returns (p_value, p_floor, null_mean, null_std, procedure). Shuffling is done on
    the average-rank-transformed ETH vector, which is an identical permutation of the
    Spearman computation but far cheaper per draw.

    THE COUNTING IS stats.permutation_p AND THE ARITHMETIC IS UNCHANGED. The three
    things that decide a permutation p are handed over exactly as this function set
    them: TWO-SIDED on |Spearman|, since the null is "no link" and a link of either
    sign refutes it; an ABSOLUTE slack of zero, which is what this file applied, rather
    than the module's default slack scaled to the size of the comparison; and a
    denominator of the draws that came back finite, which here is the whole budget.
    The last equality holds by construction: spearman_from_ranks is undefined only when
    a side has zero spread, and permuting ry reorders the same rank values, so its
    spread is the same on every draw as on the observed pairing -- if the observed
    statistic is finite, so is every draw, and the non-finite case returns above.
    """
    n = btc_vec.size
    if n < 2 or not np.isfinite(observed_spearman):
        return (float("nan"), 1.0 / (n_shuffles + 1), float("nan"), float("nan"), None)

    rng = np.random.default_rng(seed)
    rx = _rankdata_average(btc_vec)        # fixed BTC ranks
    ry = _rankdata_average(eth_vec)        # ETH ranks to be permuted

    null = np.empty(n_shuffles, dtype=np.float64)
    for s in range(n_shuffles):
        perm = rng.permutation(n)
        null[s] = spearman_from_ranks(rx, ry[perm])
    procedure = stats.permutation_p(observed_spearman, null, side="two_sided",
                                    abs_tol=0.0, n_requested=n_shuffles,
                                    cell=("m9_crossasset", "portability_placebo"))
    p_floor = 1.0 / (n_shuffles + 1)
    # The one case the module reports as "no test" and this function reported as the
    # floor: unreachable by the argument above, carried over rather than left to raise.
    p_value = procedure["p"] if procedure["p"] is not None else p_floor
    null = null[np.isfinite(null)]
    null_mean = float(null.mean()) if null.size else float("nan")
    # Kept local: the block reports 0.0 for the spread of a single usable draw where
    # this file reports NaN, and the two differ on a budget of one.
    null_std = float(null.std(ddof=1)) if null.size > 1 else float("nan")
    return float(p_value), float(p_floor), null_mean, null_std, procedure


# ---------------------------------------------------------------------------
# Whale-robustness
# ---------------------------------------------------------------------------
def drop_top_whales(ids, btc_vec, eth_vec, total_count, n_drop):
    """Recompute the cross-coin Spearman after dropping the biggest wallets.

    total_count : per-wallet BTC+ETH trade count, used to rank "whales".
    Drops the n_drop highest-total-count wallets and returns
    (spearman_after, n_dropped, n_kept). Ties at the cutoff are broken by id
    order via a stable sort so the drop set is deterministic.
    """
    n = ids.size
    if n == 0:
        return float("nan"), 0, 0
    kk = int(min(n_drop, n))
    # stable descending sort on total trade count
    order = np.argsort(-np.asarray(total_count, dtype=np.float64), kind="mergesort")
    drop_idx = order[:kk]
    keep_mask = np.ones(n, dtype=bool)
    keep_mask[drop_idx] = False
    btc_keep = btc_vec[keep_mask]
    eth_keep = eth_vec[keep_mask]
    return spearman(btc_keep, eth_keep), kk, int(keep_mask.sum())


# ---------------------------------------------------------------------------
# One window (the headline column or its companion), one K
# ---------------------------------------------------------------------------
def analyse_horizon_k(btc_ids, btc_count, btc_mean,
                      eth_ids, eth_count, eth_mean, k, horizon_name):
    """Full portability result for one markout horizon and one K threshold."""
    (ids, btc_vec, eth_vec,
     btc_cnt_sel, eth_cnt_sel) = build_dual_panel(
        btc_ids, btc_count, btc_mean, eth_ids, eth_count, eth_mean, k)

    n_dual = ids.size
    if n_dual < 2:
        return {
            "horizon": horizon_name,
            "K": k,
            "n_dual_coin_wallets": int(n_dual),
            "note": "too few dual-coin wallets for a correlation",
            "spearman": float("nan"),
            "pearson": float("nan"),
            "placebo_p": float("nan"),
            "placebo_p_floor": 1.0 / (N_SHUFFLES + 1),
            "placebo_procedure": None,
            "whale_robust": {},
        }

    sp = spearman(btc_vec, eth_vec)
    pr = pearson(btc_vec, eth_vec)

    p_value, p_floor, null_mean, null_std, placebo_procedure = permutation_pvalue(
        btc_vec, eth_vec, sp, SEED, N_SHUFFLES)

    total_count = btc_cnt_sel + eth_cnt_sel
    sp_no_whales, n_dropped, n_kept = drop_top_whales(
        ids, btc_vec, eth_vec, total_count, N_WHALES_DROP)

    # sign holds if both correlations are finite and share a sign
    sign_holds = bool(
        np.isfinite(sp) and np.isfinite(sp_no_whales)
        and (np.sign(sp) == np.sign(sp_no_whales)) and (sp != 0.0))

    return {
        "horizon": horizon_name,
        "K": k,
        "n_dual_coin_wallets": int(n_dual),
        "spearman": float(sp),
        "pearson": float(pr),
        "btc_toxicity_mean_bps": float(np.mean(btc_vec)),
        "eth_toxicity_mean_bps": float(np.mean(eth_vec)),
        "placebo": {
            "n_shuffles": N_SHUFFLES,
            "seed": SEED,
            "p_value": p_value,
            "p_floor": p_floor,
            "null_spearman_mean": null_mean,
            "null_spearman_std": null_std,
            "procedure": placebo_procedure,
        },
        "placebo_p": p_value,
        "placebo_p_floor": p_floor,
        "whale_robust": {
            "n_whales_dropped": n_dropped,
            "n_kept": n_kept,
            "spearman_after_drop": float(sp_no_whales),
            "sign_holds": sign_holds,
        },
    }


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
def main():
    t0 = artifact.start_clock()
    # panel_io raises when the file is absent and names the producer to run, so the
    # "is it there" test and the "what do I do about it" message live in one place
    # instead of once per script.
    # panel_io names the producer to run when the file is absent, so that message
    # is written once for the whole tree; the load itself stays here because
    # build.py derives this script's input edge from the argument of np.load.
    P.require_present("print", NPZ_PATH)
    data = np.load(NPZ_PATH)
    taker_id = data["taker_id"].astype(np.int64)
    coin = data["coin"].astype(np.int8)
    # Both columns through panel_io, which takes the lens from the FILE and refuses a
    # window off the declared ladder, so neither read can quietly pick the wrong price.
    mo_head = P.score(data, "print")                      # signed taker markout, bps
    mo_contrast = P.score(data, "print", H.COMPANION_HORIZON_S)   # robustness companion
    # Read only to state the window in the artifact's scope; it enters no computation.
    day = data["day"].astype(np.int64)

    btc_sel = coin == COIN_BTC
    eth_sel = coin == COIN_ETH

    results = {
        "_meta": {
            "object": "M9 cross-asset toxicity portability (BTC <-> ETH)",
            "n_trades_total": int(taker_id.size),
            "n_trades_btc": int(btc_sel.sum()),
            "n_trades_eth": int(eth_sel.sum()),
            "headline": ("Spearman rank correlation of per-wallet mean markout, "
                         "BTC vs ETH, over wallets active in both coins; the "
                         f"pre-registered headline cell is {HEADLINE_COL} at K=50, "
                         "with the rest of the K-sweep read as a monotonicity "
                         "check, not as independent confirmations"),
            "headline_horizon": HEADLINE_COL,
            "headline_K": HEADLINE_K,
            "pre_registered_cell": PRE_REGISTERED_CELL,
            "magnitude_caveat": (
                "the cross-coin Spearman is NOT a stable magnitude: it rises "
                f"monotonically with K ({HEADLINE_COL} ~0.16 @K10 -> 0.24 -> 0.52 "
                "-> 0.72 -> 0.77 @K200) as per-wallet means are averaged over more "
                "fills (noise-averaging). Read the full K-curve and the qualitative "
                "sign, not any single cell such as 0.52"),
            "toxicity_measure": "per-wallet mean signed taker markout (bps); "
                                "positive = taker profited = maker adverse-selected",
            "horizons": [HEADLINE_COL, CONTRAST_COL],
            "K_values": list(K_VALUES),
            "seed": SEED,
            "n_shuffles": N_SHUFFLES,
            "n_whales_dropped": N_WHALES_DROP,
            "whale_drop_criterion": H.whale_drop("fill_count",
                                                 N_WHALES_DROP)["criterion"],
        },
        "results": {},
    }

    # What the numbers cover. The unit of analysis is the WALLET here, and a wallet
    # enters only where it is active in both coins, so the population states the
    # per-coin fill floor that admits it rather than the row count of the input.
    days = np.unique(day)
    scope = {
        "population": (f"{taker_id.size:,} fills of the trade-print panel reduced to "
                       "per-wallet mean markouts; a wallet enters a cell only when "
                       f"it clears that cell's per-coin fill floor in BOTH coins, "
                       f"and the pre-registered cell floors at K={HEADLINE_K}"),
        "window": (f"{days.size} days present in the input, day-of-month "
                   f"{days.min()}-{days.max()}; the calendar dates of the window "
                   "are declared by its producer, build_quickwin_markouts.py"),
        "coins": [COIN_NAME[c] for c in sorted(COIN_NAME)],
    }
    results["_meta"]["horizons_reported_s"] = [H.HEADLINE_HORIZON_S,
                                               H.COMPANION_HORIZON_S]
    results["_meta"]["rank_floor_note"] = (
        f"the pre-registered cell floors at K={HEADLINE_K} fills PER COIN, which is "
        f"the declared wallet floor; the other cells of the K-sweep are a "
        f"monotonicity check at {list(K_VALUES)} and are not the headline")

    # headline window first, then the robustness companion
    for horizon_name, value in ((HEADLINE_COL, mo_head),
                                (CONTRAST_COL, mo_contrast)):
        # per-wallet means computed once per coin per horizon
        btc_ids, btc_count, btc_mean = per_wallet_mean(
            taker_id[btc_sel], value[btc_sel])
        eth_ids, eth_count, eth_mean = per_wallet_mean(
            taker_id[eth_sel], value[eth_sel])

        for k in K_VALUES:
            block = analyse_horizon_k(
                btc_ids, btc_count, btc_mean,
                eth_ids, eth_count, eth_mean, k, horizon_name)
            results["results"][f"{horizon_name}_K{k}"] = block

    # ----- per-object Benjamini-Hochberg FDR over every cell's placebo p -----
    # (mirrors i3: control the false-discovery rate across the full sweep of
    # horizon x K cells instead of reading each placebo p in isolation)
    cell_names = list(results["results"].keys())
    raw_p = [results["results"][c].get("placebo_p", float("nan"))
             for c in cell_names]
    # The correction is stats.benjamini_hochberg and the level comes with it from
    # settings.FDR_ALPHA, so neither the procedure nor the level is typed in this file.
    # `family` names what the family IS, because the same p corrected over ten cells and
    # over 448 gives two different verdicts and an artifact recording only the verdict
    # cannot be checked.
    bh = stats.benjamini_hochberg(
        raw_p, family="cross-asset portability cells: horizon x wallet-fill floor")
    alpha = float(bh["alpha"])
    # None is what the module returns for a cell with no testable p; NaN is what this
    # file's own keys have always carried for that case, and the two say the same thing.
    q_vals = np.array([np.nan if v is None else float(v) for v in bh["q"]],
                      dtype=np.float64)
    fdr_cells = {}
    for c, p_raw, q in zip(cell_names, raw_p, q_vals):
        q_f = float(q) if np.isfinite(q) else float("nan")
        results["results"][c]["bh_fdr_q"] = q_f
        results["results"][c]["bh_fdr_reject_0p05"] = bool(
            np.isfinite(q) and q <= alpha)
        fdr_cells[c] = {
            "placebo_p": float(p_raw) if np.isfinite(p_raw) else float("nan"),
            "bh_fdr_q": q_f,
            "reject_at_0p05": bool(np.isfinite(q) and q <= alpha),
        }
    results["bh_fdr"] = {
        "method": "Benjamini-Hochberg step-up over placebo p-values",
        "procedure": bh["procedure"],
        "procedure_note": bh["method"],
        "n_cells": len(cell_names),
        "alpha": alpha,
        # The family size is the count of cells that HAD a testable p, which is what the
        # correction divided by, and it is not the same as n_cells whenever a cell is
        # degenerate. Both are reported so a reader can see when they part.
        "family": bh["family"],
        "family_size": bh["family_size"],
        "n_not_testable": bh["n_not_testable"],
        # The bar, which the local copy of this correction never returned. "Significant
        # after correction" cannot be read without it, and it is not a constant: it falls
        # with the family size, so it has to travel beside the verdict.
        "threshold": bh["threshold"],
        "threshold_meaning": bh["threshold_meaning"],
        "rank1_threshold": bh["rank1_threshold"],
        "n_reject_at_0p05": int(sum(
            1 for v in fdr_cells.values() if v["reject_at_0p05"])),
        "cells": fdr_cells,
        "pre_registered_cell": PRE_REGISTERED_CELL,
        "interpretation_note": (
            "The K-cells are CORRELATED NESTED THRESHOLDS on the SAME wallets "
            "(higher K is a strict subsample of lower K), so 'all cells reject "
            "the null after BH' is NOT independent confirmation. The cells "
            "re-ask one question on deeply overlapping samples, and the placebo "
            "p-values are floored at 1/(N_SHUFFLES+1); the joint rejection "
            "conveys roughly ONE cell of evidence, not one per cell. Lead with "
            f"the pre-registered {PRE_REGISTERED_CELL} cell and treat the K-sweep "
            "as a monotonicity / noise-averaging check (the Spearman RISES with K), "
            "not as cells to be summed."),
    }

    # The output name and directory still come from the module-level OUT_PATH, so a
    # caller that redirects that constant redirects the whole write, as before. One
    # stamped value genuinely differs from the declaration -- the placebo is seeded
    # with this module's own literal -- and two agree with it: the shuffle budget and
    # the K=50 floor of the pre-registered cell. All three are passed, because a
    # migrating declaration is only asserted when the caller states what its run used,
    # and a value that agrees is worth asserting for exactly that reason. Nothing is
    # bootstrapped here, so the bootstrap budget stays in declared_not_confirmed.
    artifact.write(os.path.basename(OUT_PATH), results,
                   script=__file__, inputs=[NPZ_PATH], scope=scope,
                   settings={"h": H.HEADLINE_HORIZON_S, "lens": "print",
                             "master_seed": SEED, "n_perm": N_SHUFFLES,
                             "rank_floor_fills": HEADLINE_K},
                   started=t0, out_dir=os.path.dirname(OUT_PATH))

    print_summary(results)
    print(f"\n[m9] wrote {os.path.basename(OUT_PATH)}")


# ---------------------------------------------------------------------------
# Printed summary
# ---------------------------------------------------------------------------
def _fmt(x, nd=4):
    return f"{x:.{nd}f}" if isinstance(x, float) and np.isfinite(x) else "n/a"


def print_summary(results):
    print("=" * 78)
    print("M9 — CROSS-ASSET TOXICITY PORTABILITY (BTC <-> ETH)")
    print("=" * 78)
    meta = results["_meta"]
    print(f"trades total : {meta['n_trades_total']:,}  "
          f"(BTC {meta['n_trades_btc']:,} / ETH {meta['n_trades_eth']:,})")
    print("Headline = Spearman rank corr of per-wallet mean markout, BTC vs ETH.")
    print(f"Headline horizon = {HEADLINE_COL} ({CONTRAST_COL} = robustness).")
    print("Positive markout = taker profited = maker adverse-selected.")
    print("NOTE: Spearman is NOT a stable magnitude - it climbs with K as")
    print("per-wallet means average out noise. Read the K-CURVE, not one cell.\n")

    header = (f"{'cell':<12} {'n_dual':>8} {'spearman':>10} {'pearson':>9} "
              f"{'placebo_p':>10} {'bh_q':>8} {'sp_no_whale':>12} {'sign_ok':>8}")
    print(header)
    print("-" * len(header))
    # headline window first, then the robustness companion
    order = []
    for horizon in (HEADLINE_COL, CONTRAST_COL):
        for k in K_VALUES:
            order.append(f"{horizon}_K{k}")
    for cell in order:
        b = results["results"].get(cell)
        if b is None:
            continue
        wr = b.get("whale_robust", {})
        sp_nw = wr.get("spearman_after_drop", float("nan"))
        sign_ok = wr.get("sign_holds", False)
        print(f"{cell:<12} {b['n_dual_coin_wallets']:>8,} "
              f"{_fmt(b['spearman']):>10} {_fmt(b['pearson']):>9} "
              f"{_fmt(b['placebo_p']):>10} {_fmt(b.get('bh_fdr_q'), 4):>8} "
              f"{_fmt(sp_nw):>12} {str(bool(sign_ok)):>8}")

    # explicit K-curve readout for the headline horizon
    print(f"\n{HEADLINE_COL} K-curve (Spearman, headline horizon) - monotone "
          "noise-averaging:")
    curve = []
    for k in K_VALUES:
        b = results["results"].get(f"{HEADLINE_COL}_K{k}")
        if b is not None:
            curve.append(f"K{k}={_fmt(b['spearman'], 3)}")
    print("  " + "  ->  ".join(curve))

    bh = results.get("bh_fdr", {})
    pre = results["_meta"].get("pre_registered_cell", PRE_REGISTERED_CELL)
    pre_block = results["results"].get(pre, {})
    print(f"\nPre-registered headline cell = {pre}: "
          f"spearman={_fmt(pre_block.get('spearman'), 3)} "
          f"placebo_p={_fmt(pre_block.get('placebo_p'), 5)} "
          f"bh_q={_fmt(pre_block.get('bh_fdr_q'), 4)}")
    print(f"BH-FDR over {bh.get('n_cells', 0)} cells (alpha 0.05): "
          f"{bh.get('n_reject_at_0p05', 0)} cells reject. NOTE: these cells are "
          "CORRELATED NESTED K-thresholds on the SAME wallets, so the joint "
          "reject is ~ONE cell of evidence, not one per cell. The K-sweep is a "
          "monotonicity check (Spearman rises with K = noise-averaging), not "
          "independent confirmation.")
    print("placebo_p floor = 1 / (n_shuffles + 1) = "
          f"{_fmt(1.0 / (N_SHUFFLES + 1), 5)} "
          f"(seed {meta['seed']}, {meta['n_shuffles']} shuffles)")
    # The criterion is read from the block rather than written into the sentence, so
    # the printed line and the artifact can never name different criteria.
    print("sign_ok = cross-coin Spearman keeps its sign after dropping the "
          f"top-{meta['n_whales_dropped']} wallets by "
          f"{meta['whale_drop_criterion'].replace('_', ' ')}")
    print("=" * 78)


if __name__ == "__main__":
    main()
