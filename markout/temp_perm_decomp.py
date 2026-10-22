"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-20
References: Huang & Stoll (1996) RFS realized-spread / two-way decomposition;
  Hasbrouck (1991 JF, 1993 RFS) permanent-vs-transitory price-impact / VAR-VMA;
  Glosten & Harris (1988); Hyperliquid L2-book archive; Zenodo 18184441 (Albers et al. 2026).
"""

# ===========================================================================
# CORRECTION (adversarial verify, 2026-06-20) — READ BEFORE USING THIS OUTPUT
# ---------------------------------------------------------------------------
# The Huang-Stoll / Hasbrouck "permanent vs transient own-impact" LABEL below is
# NOT supported on this December BTC/ETH book-mid sample: mid-impact GROWS
# monotonically with horizon (mean |mo1|~1.4 bps, |mo10|~2.9, |mo60|~6.5; ~88% of
# fills have |mo60|>|mo1|), and fill-level corr(permanent, temporary) = -0.96. So
# temporary = mo1_mid - mo60_mid is dominated by continued price discovery (drift),
# NOT by reverting own-impact, and a realized-spread reversion decomposition does
# not apply here. The "loads_on_permanent_not_temporary" field is therefore an
# OVER-LABEL and must not be cited as a permanent-vs-transient information split.
# What IS valid and usable: the odd/even SPLIT-SAMPLE block — the per-counterparty
# mean 60s book-mid markout persists out-of-half (Spearman ~0.19 pooled / ~0.30 ETH,
# p at the permutation floor 1/2001). That is split-half persistence of the toxicity
# score and CORROBORATES ks2_persistence_10day; it is not an independent finding.
# ===========================================================================

# ---------------------------------------------------------------------------
# OBJECT TEMP/PERM - Huang-Stoll / Hasbrouck temporary-vs-permanent decomposition
# of each fill's BOOK-MID price impact, then per-counterparty loadings on the
# PERMANENT (information) component versus the TEMPORARY (transient own-impact)
# component.
#
# WHY THIS IS NEW (relative to m5 and i5, both read first):
#   * m5_termstructure.py reports the RAW signed mid/print markout curve at 1s,
#     10s, 60s and asks whether the curve RISES or FALLS. It never splits a single
#     fill into an additive permanent + temporary pair; it reads the curve shape.
#   * i5_exclusion.py tests a permanence RATIO mo60/mo1 by an extend/reduce Kyle
#     partition. It is a between-group ratio test, not a per-fill decomposition and
#     not a per-counterparty loading.
#   This object goes beyond both: it writes each fill as
#       signed_mid_move(h) = PERMANENT + (reverting part at horizon h),
#   in the Huang-Stoll (1996) realized-spread sense and the Hasbrouck (1991)
#   permanent/transitory sense, and then asks which of the two legs the ESTABLISHED
#   per-counterparty toxicity ranking (the i3/ks2 wallet score) actually loads on.
#
# THE DECOMPOSITION (per fill i), on the L2-BOOK MID, all in basis points and all
# already SIGNED so that POSITIVE = taker profited = maker adversely selected
# (the build convention: mo*_mid = +sign_taker * (mid(t+h)-mid(t))/mid(t) * 1e4):
#
#   permanent_i  = mo60_mid_i
#       The long-horizon (>= 60s) signed mid move. In Hasbrouck's random-walk
#       reading this is the INFORMATION component: the part of the post-fill mid
#       move that does NOT revert, i.e. the permanent price impact the fill carried.
#
#   temporary_i  = mo1_mid_i - mo60_mid_i
#       Huang-Stoll realized-spread logic: the realized (transient) half-spread is
#       the EFFECTIVE early impact minus the PERMANENT impact. mo1_mid is the early
#       (1s) signed mid move - the effective impact right after the fill - and the
#       part of it that has DECAYED away by 60s is exactly mo1_mid - mo60_mid. A
#       POSITIVE temporary means the early mid overshot the eventual permanent move
#       and then mean-reverted (classic transient own-impact / liquidity pressure);
#       a temporary near zero means the early move was already permanent.
#
#   (sanity identity, by construction: permanent_i + temporary_i = mo1_mid_i.)
#
# A 10s "intermediate" decomposition (permanent = mo60, temporary10 = mo10 - mo60)
# is also reported so the reader can see how much reversion is already gone by 10s.
#
# THE PER-COUNTERPARTY CLAIM (the point of the object):
#   The ESTABLISHED per-counterparty toxicity score - the wallet's mean 60s mid
#   markout, the same statistic ks2/i3 rank wallets by - should line up with the
#   PERMANENT loading and NOT with the TEMPORARY loading. A toxic counterparty is
#   one whose flow carries information (permanent impact on the maker), not one who
#   merely pays for immediacy and then lets the mid snap back (temporary impact).
#   So we predict:
#       rank_corr(toxicity, permanent_loading)  strongly POSITIVE,
#       rank_corr(toxicity, temporary_loading)  near zero / not positive,
#   and PERMANENT must beat TEMPORARY by a margin that survives a permutation null.
#
# THE IDENTITY GUARD (load-bearing honesty): the permanent loading IS the wallet
# mean mo60, which is also (essentially) the toxicity score, so a same-sample rank
# correlation of toxicity vs the permanent loading is close to a tautology (~1).
# To make the comparison a REAL test we split each wallet's fills ODD/EVEN by
# arrival and score the toxicity on one half while building the permanent/temporary
# loadings on the OTHER half (the same odd/even reliability trick ks2 uses). The
# SPLIT-SAMPLE rank correlations are the headline; the naive same-sample ones are
# reported alongside and explicitly flagged as mechanically inflated for the
# permanent leg. Under the split, "permanent wins, temporary does not" is a
# falsifiable statement about out-of-half persistence, not an algebraic identity.
#
# GUARDS carried over from the shared scripts:
#   * reads ONLY the row-aligned mid intermediate quickwin_markouts_mid.npz (the
#     no-lookahead entry/horizon join + ns->ms + sign were already applied by
#     i4_midmarkout.py; we do NOT re-parse raw books);
#   * established toxicity score = per-wallet mean mo60_mid for wallets with
#     >= K fills (taker_means / K convention from ks2_persistence_10day.py);
#   * permutation null on the wallet labels (shuffle toxicity vs loadings linkage),
#     two-sided, p floored at 1/(N_PERM+1);
#   * whale-drop robustness (drop the top wallets by fill count, re-check the sign
#     of the permanent-minus-temporary correlation gap);
#   * per coin AND pooled; declared seed constant; numpy + stdlib only;
#   * NO hardcoded user paths (HERE + env/argparse data-root override); only
#     os.path.basename is written into the result JSON.
#
# Run command (bare python3 is BLOCKED on this machine):
#   uv run --no-project --with-requirements requirements.txt python3 markout/temp_perm_decomp.py
# Optional smoke slice: --data-root <dir> to point at an alternate npz directory.
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

# -------------------- configuration --------------------
# Every setting settings.py declares is READ from there, not re-typed. Each was
# compared against the literal this file used to carry and all of them are
# identical, so adopting the declaration moves no number in this artifact.
SEED = H.MASTER_SEED                # 20260620, the one master seed

HERE = os.path.dirname(os.path.abspath(__file__))
MID_NPZ_NAME = "quickwin_markouts_mid.npz"
TAKER_MAP_NAME = "quickwin_taker_map.json"
OUT_NAME = "temp_perm_results.json"

# npz int8 coin code -> label, asked for BY ARTIFACT: this file reads the QUICKWIN
# mid intermediate, which carries {0, 1} and no SOL. The panel file carries
# {0, 1, 2}, and a code valid in both would relabel a coin without raising, so the
# map belongs to the file rather than to the project.
COIN_CODES = H.coin_labels("quickwin")   # {0: BTC, 1: ETH}

# Per-wallet eligibility thresholds (min fills), matching ks2's K_POOL family.
K_LIST = H.PERSISTENCE_FLOOR_FILLS   # (50, 100)

# Min fills a wallet needs IN EACH odd/even half for the split-sample test (so the
# toxicity half-mean and the loading half-means are both non-degenerate). The split
# halves are ~K/2 each, so we ask for at least this many per half. READ from settings.py
# under this file's own name, because it is a property of THIS test and no other file has
# an opinion on it -- the declaration keeps the per-consumer entry rather than folding it
# into RANK_FLOOR_FILLS, which is a floor on a different window. The value is the same
# 20, so no wallet enters or leaves the test.
K_HALF_MIN = H.wallet_fill_floor("temp_perm_decomp", "each_split_half")

N_PERM = H.N_PERM                   # 2000 wallet-label permutation draws
P_FLOOR = H.p_floor(N_PERM)
N_DROP_WHALES = H.WHALE_DROP_K      # 10 top wallets by fill count, robustness

# Join-quality gate: i4_midmarkout writes a |snapshot - target| gap per horizon.
# We keep a fill for a horizon only if BOTH the entry gap and that horizon's gap
# are within tolerance, so a loosely-joined snapshot cannot fake impact.
GAP_MAX_MS = 5000.0

# Decomposition-validity gate. A permanent/transient split is only meaningful when
# the temporary leg is a genuine REVERTING component (mean temporary > 0: the early
# move overshoots the eventual move and then snaps back) AND the two legs are not
# mechanically the same quantity negated. On this December book-mid sample mid
# impact grows monotonically with horizon, so temporary = mo1 - mo60 < 0 (no
# reversion) and the fill-level corr(permanent, temporary) ~ -0.96. Any slice whose
# corr is more negative than this threshold is NOT an independent decomposition, so
# the permanent-vs-temporary verdict flags are forced False.
CORR_PERM_TEMP_MAX = -0.5

# -------------------- the windows each leg is built from, and its field names -----
# settings.FIELD_SUFFIX_STYLE = "explicit": a field whose value depends on the
# scoring window states that window. This file is the hardest case in the tree,
# because two of its three legs are DIFFERENCES of two windows and settings.
# field_name can only express a single one. So the tokens are composed here, from
# the settings values and never from typed digits, and each window is validated by
# asking settings for its column (which raises for a window no artifact carries).
#
# WHY IT MATTERS HERE MORE THAN ANYWHERE. The words "permanent" and "temporary"
# read as concepts, so nothing in a key like mean_temporary_loading_bps said that
# it is a 1 s move minus a 60 s move measured against the book mid. The correction
# at the top of this file exists because that label was wrong; a reader lifting the
# 0.19 rank correlation out of this artifact has to be able to see that it belongs
# to the 60 s book-mid window and NOT to the study's 10 s headline.
PERM_H = H.COMPANION_HORIZON_S       # 60 s: the long window the "permanent" leg is
EARLY_H = min(H.LADDER_S)            # 1 s: the early effective-impact window
MID_H = H.HEADLINE_HORIZON_S         # 10 s: the intermediate reversion window
LENS = "mid"                         # L2-book mid, never the trade print
for _h in (PERM_H, EARLY_H, MID_H):  # raises if a window has no book-mid column
    H.headline_mid_col(_h)

# NOTE ON THE SCORE THIS OBJECT RANKS ON. The toxicity score here is the per-wallet
# mean markout at PERM_H = 60 s, because the decomposition defines its permanent leg
# at the long window. The study's headline window is 10 s, so this object's ranking
# is NOT the headline ranking, and its rank correlations are not comparable to the
# headline persistence figures cell for cell. Every field name below says so.


def _leg(*horizons):
    """The window token of one leg: '60s', or '1s_minus_60s' for a difference."""
    return "_minus_".join(f"{int(h)}s" for h in horizons)


LEG_PERM = _leg(PERM_H)                  # "60s"
LEG_TEMP = _leg(EARLY_H, PERM_H)         # "1s_minus_60s"
LEG_TEMP10 = _leg(MID_H, PERM_H)         # "10s_minus_60s"


def _f(base, leg):
    """A window-bearing field name: base, the leg's window(s), then the lens."""
    return f"{base}_{leg}_{LENS}"


K_MEAN_PERM = _f("mean_permanent_loading_bps", LEG_PERM)
K_STD_PERM = _f("std_permanent_loading_bps", LEG_PERM)
K_MEAN_TEMP = _f("mean_temporary_loading_bps", LEG_TEMP)
K_STD_TEMP = _f("std_temporary_loading_bps", LEG_TEMP)
K_MEAN_TEMP10 = _f("mean_temporary10_loading_bps", LEG_TEMP10)
K_STD_TEMP10 = _f("std_temporary10_loading_bps", LEG_TEMP10)
K_RC_PERM = _f("rank_corr_toxicity_vs_permanent", LEG_PERM)
K_RC_TEMP = _f("rank_corr_toxicity_vs_temporary", LEG_TEMP)
K_RC_TEMP10 = _f("rank_corr_toxicity_vs_temporary10", LEG_TEMP10)
K_RC_PERM_SPLIT = _f("rank_corr_toxicityA_vs_permB", LEG_PERM)
K_RC_TEMP_SPLIT = _f("rank_corr_toxicityA_vs_tempB", LEG_TEMP)
K_GAP = _f("perm_minus_temp_gap", f"{LEG_PERM}_vs_{LEG_TEMP}")
K_FILL_CORR = _f("fill_corr_permanent_temporary", f"{LEG_PERM}_vs_{LEG_TEMP}")
K_MEAN_PERM_FILL = _f("mean_permanent_fill_bps", LEG_PERM)
K_MEAN_TEMP_FILL = _f("mean_temporary_fill_bps", LEG_TEMP)
K_FULL_GAP = _f("full_gap", f"{LEG_PERM}_vs_{LEG_TEMP}")
K_DROPPED_GAP = _f("dropped_gap", f"{LEG_PERM}_vs_{LEG_TEMP}")
# The whale arm names its criterion, not only its count: dropping the ten largest
# by FILL COUNT asks whether the gap is a handful of bots, by notional it would ask
# whether it is a volume artifact. Different questions, so the key says which.
WHALE_KEY = H.whale_drop("fill_count", N_DROP_WHALES)["key"]


# ==================== rank / correlation helpers (numpy-only) ====================
def _rankdata(a):
    """Average-rank of a 1-D array (ties shared), matching the i3/ks2 ranker."""
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


# ==================== per-fill decomposition ====================
def decompose_fills(mo1_mid, mo10_mid, mo60_mid):
    """Huang-Stoll / Hasbrouck per-fill permanent + temporary split (bps, signed).

    permanent  = mo60_mid                      (long-horizon, non-reverting; info)
    temporary  = mo1_mid - mo60_mid            (early effective impact that decays)
    temporary10= mo10_mid - mo60_mid           (reversion still present at 10s)

    All three legs are NaN unless the constituent markouts are finite. Returns
    (permanent, temporary, temporary10) float64 arrays aligned with the input.
    """
    p = np.asarray(mo60_mid, dtype=np.float64)
    e1 = np.asarray(mo1_mid, dtype=np.float64)
    e10 = np.asarray(mo10_mid, dtype=np.float64)
    temporary = e1 - p
    temporary10 = e10 - p
    return p, temporary, temporary10


# ==================== per-wallet loadings ====================
def _group_mean(values, inv, n_groups):
    """Per-group mean over finite values (groups indexed by inv in [0, n_groups))."""
    v = np.asarray(values, dtype=np.float64)
    finite = np.isfinite(v)
    ssum = np.zeros(n_groups, dtype=np.float64)
    cnt = np.zeros(n_groups, dtype=np.float64)
    np.add.at(ssum, inv[finite], v[finite])
    np.add.at(cnt, inv[finite], 1.0)
    out = np.full(n_groups, np.nan, dtype=np.float64)
    nz = cnt > 0
    out[nz] = ssum[nz] / cnt[nz]
    return out, cnt


def per_wallet_loadings(taker_id, permanent, temporary, temporary10, mo60_mid, K):
    """Per-counterparty permanent / temporary loadings + established toxicity score.

    For wallets with >= K fills (the ks2 K convention) return, aligned across
    wallets:
        toxicity        = wallet mean mo60_mid  (the i3/ks2 per-counterparty score)
        perm_loading    = wallet mean permanent (== toxicity by construction)
        temp_loading    = wallet mean temporary (1s - 60s reversion)
        temp10_loading  = wallet mean temporary10
        fills           = wallet total fill count (the >= K gate)
    Returns a dict of arrays restricted to eligible wallets (plus the wallet ids).
    """
    taker_id = np.asarray(taker_id, dtype=np.int64)
    if taker_id.size == 0:
        return None
    uniq, inv = np.unique(taker_id, return_inverse=True)
    n_w = uniq.size

    fills = np.zeros(n_w, dtype=np.int64)
    np.add.at(fills, inv, 1)

    tox, _ = _group_mean(mo60_mid, inv, n_w)
    perm, _ = _group_mean(permanent, inv, n_w)
    temp, _ = _group_mean(temporary, inv, n_w)
    temp10, _ = _group_mean(temporary10, inv, n_w)

    elig = (fills >= K) & np.isfinite(tox) & np.isfinite(perm) \
        & np.isfinite(temp) & np.isfinite(temp10)
    pos = np.where(elig)[0]
    if pos.size < 3:
        return None
    return {
        "wallet_ids": uniq[pos].astype(np.int64),
        "toxicity": tox[pos],
        "perm_loading": perm[pos],
        "temp_loading": temp[pos],
        "temp10_loading": temp10[pos],
        "fills": fills[pos],
        "n_wallets": int(pos.size),
    }


# ==================== split-sample (identity-breaking) loadings ====================
def per_wallet_split_loadings(taker_id, permanent, temporary, mo60_mid, K_half,
                              rng):
    """Odd/even-split per-wallet toxicity vs loadings (breaks the algebraic identity).

    Each wallet's fills are randomly halved (the ks2 reliability trick). The
    ESTABLISHED toxicity score is the wallet mean mo60_mid on HALF A; the permanent
    and temporary LOADINGS are wallet means on HALF B. A wallet enters only if both
    halves have >= K_half finite fills for the relevant column. Because toxicity
    (half A) and the permanent loading (half B) come from disjoint fills, their
    rank correlation is no longer a tautology - it measures out-of-half persistence
    of the permanent leg, the honest version of the claim.

    Returns aligned arrays: toxicity_A, perm_B, temp_B (plus n_wallets, wallet_ids).
    """
    taker_id = np.asarray(taker_id, dtype=np.int64)
    n = taker_id.size
    if n == 0:
        return None
    # randomize, then assign each wallet's fills alternately to half A / half B by
    # within-wallet running index (odd/even) - balanced halves, ks2 style.
    order = rng.permutation(n)
    tid = taker_id[order]
    p = np.asarray(permanent, dtype=np.float64)[order]
    t = np.asarray(temporary, dtype=np.float64)[order]
    m60 = np.asarray(mo60_mid, dtype=np.float64)[order]

    uniq, inv = np.unique(tid, return_inverse=True)
    n_w = uniq.size
    # within-wallet running position (stable group order)
    o2 = np.argsort(inv, kind="stable")
    inv_s = inv[o2]
    counts = np.bincount(inv, minlength=n_w)
    starts = np.zeros(n_w, dtype=np.int64)
    starts[1:] = np.cumsum(counts)[:-1]
    within = np.arange(inv_s.size) - starts[inv_s]
    half_id_sorted = (within % 2)             # 0 -> A, 1 -> B
    half_id = np.empty(n, dtype=np.int64)
    half_id[o2] = half_id_sorted

    is_a = half_id == 0
    is_b = half_id == 1

    # toxicity on half A (mean mo60), perm/temp loadings on half B (means)
    tox_a, cnt_tox_a = _group_mean(np.where(is_a, m60, np.nan), inv, n_w)
    perm_b, cnt_perm_b = _group_mean(np.where(is_b, p, np.nan), inv, n_w)
    temp_b, cnt_temp_b = _group_mean(np.where(is_b, t, np.nan), inv, n_w)

    elig = (cnt_tox_a >= K_half) & (cnt_perm_b >= K_half) & (cnt_temp_b >= K_half) \
        & np.isfinite(tox_a) & np.isfinite(perm_b) & np.isfinite(temp_b)
    pos = np.where(elig)[0]
    if pos.size < 3:
        return None
    return {
        "wallet_ids": uniq[pos].astype(np.int64),
        "toxicity_A": tox_a[pos],
        "perm_B": perm_b[pos],
        "temp_B": temp_b[pos],
        "n_wallets": int(pos.size),
    }


# ==================== permutation null on the permanent-minus-temporary gap ====================
def _perm_gap_pvalue(tox, perm, temp, observed_gap, rng, n_perm=N_PERM):
    """Two-sided permutation p for the (permanent - temporary) rank-corr gap.

    The link between the toxicity ranking and the loadings is broken by shuffling
    the toxicity vector across wallets; for each shuffle we recompute
        gap = spearman(tox_perm, perm) - spearman(tox_perm, temp)
    and count |null gap| >= |observed gap|. p = (count+1)/(n_perm+1), floored at
    1/(n_perm+1). Shuffling toxicity (not the loadings) keeps the perm/temp pair's
    own correlation structure intact under the null.

    THE COUNTING IS stats.permutation_p AND THE ARITHMETIC IS UNCHANGED: TWO-SIDED on
    the absolute gap, an ABSOLUTE slack of 1e-12 exactly as this function applied, and
    a denominator of n_perm.

    THE ONE POLICY THIS FILE DOES NOT SHARE WITH THE MODULE, stated here because the
    array handed over hides it. A draw whose gap is undefined is SUBSTITUTED BY ZERO on
    the line below, where the module would drop it and divide by what survived. Two of
    the twenty-four permutation sites in this tree substitute and this is one of them,
    so the substitution is left in place and the module is handed an array that is
    already finite everywhere -- which is why its block reports nothing dropped. That
    is an honest description of the array it was given and not of the null, so the
    count of substituted draws is returned beside it. The substitution is not neutral:
    a null centred near zero gains mass at its own centre, so for a positive observed
    gap the count of extreme draws falls and the p falls with it. Changing it would
    move a published p and is owed its own recompute.
    """
    if not np.isfinite(observed_gap):
        return float("nan"), float("nan"), float("nan"), None
    tox = np.asarray(tox, dtype=np.float64)
    perm = np.asarray(perm, dtype=np.float64)
    temp = np.asarray(temp, dtype=np.float64)
    n = tox.size
    null = np.empty(n_perm, dtype=np.float64)
    n_substituted = 0
    idx = np.arange(n)
    for i in range(n_perm):
        rng.shuffle(idx)
        ts = tox[idx]
        g = spearman(ts, perm) - spearman(ts, temp)
        if not np.isfinite(g):
            n_substituted += 1
        null[i] = g if np.isfinite(g) else 0.0
    procedure = stats.permutation_p(observed_gap, null, side="two_sided",
                                    abs_tol=1e-12, n_requested=n_perm,
                                    cell=("temp_perm_decomp", "perm_minus_temp_gap"))
    procedure["n_draws_substituted_zero"] = int(n_substituted)
    procedure["failed_draw_policy"] = (
        "a draw whose statistic is undefined is REPLACED BY 0.0 before counting, not "
        "dropped; the module's n_draws_dropped therefore describes the array it was "
        "handed and is zero by construction")
    p = procedure["p"]
    # POPULATION spread (ddof=0), which is what this file has always reported; the
    # block beside it carries the sample one under null_sd.
    return float(p), float(null.mean()), float(null.std(ddof=0)), procedure


# ==================== whale robustness ====================
def _whale_drop_gap(loads, n_drop=N_DROP_WHALES):
    """Recompute the perm/temp rank correlations after dropping the top wallets by
    fill count; confirm the (permanent - temporary) correlation gap keeps its sign.
    """
    fills = loads["fills"]
    if fills.size <= n_drop + 3:
        return {
            K_FULL_GAP: float("nan"), K_DROPPED_GAP: float("nan"),
            "sign_preserved": False, "n_whales_dropped": 0,
        }
    order = np.argsort(-fills, kind="stable")
    drop = order[:n_drop]
    keep = np.ones(fills.size, dtype=bool)
    keep[drop] = False

    def _gap(mask):
        c_perm = spearman(loads["toxicity"][mask], loads["perm_loading"][mask])
        c_temp = spearman(loads["toxicity"][mask], loads["temp_loading"][mask])
        if not (np.isfinite(c_perm) and np.isfinite(c_temp)):
            return float("nan")
        return c_perm - c_temp

    full_gap = _gap(np.ones(fills.size, dtype=bool))
    dropped_gap = _gap(keep)
    sign_ok = bool(
        np.isfinite(full_gap) and np.isfinite(dropped_gap)
        and np.sign(full_gap) == np.sign(dropped_gap) and full_gap != 0.0)
    return {
        K_FULL_GAP: full_gap,
        K_DROPPED_GAP: dropped_gap,
        "sign_preserved": sign_ok,
        "n_whales_dropped": int(n_drop),
        "n_wallets_after_drop": int(keep.sum()),
        "criterion": H.whale_drop("fill_count", n_drop)["criterion"],
    }


# ==================== decomposition-validity diagnostics ====================
def _decomposition_diagnostics(permanent, temporary):
    """Fill-level validity check for the permanent/temporary split (per slice).

    The Huang-Stoll / Hasbrouck permanent-vs-transient LABEL is only meaningful if
    the temporary leg is a genuine REVERTING component (mean temporary > 0: the
    early move overshoots the eventual move and snaps back) AND permanent/temporary
    are not mechanically the same quantity negated (corr > CORR_PERM_TEMP_MAX).

    Returns the fill-level Pearson corr(permanent, temporary), the mean of each leg
    (bps), whether mid impact GROWS monotonically with horizon (mean |mo60| >
    mean |mo1|, where mo1 = permanent + temporary by construction), and a single
    decomposition_valid flag. On this December book-mid sample corr ~ -0.96 and mid
    impact grows monotonically, so decomposition_valid is False.
    """
    p = np.asarray(permanent, dtype=np.float64)
    t = np.asarray(temporary, dtype=np.float64)
    fin = np.isfinite(p) & np.isfinite(t)
    n = int(fin.sum())
    if n < 3:
        return {
            "n_fills": n,
            K_FILL_CORR: float("nan"),
            K_MEAN_PERM_FILL: float("nan"),
            K_MEAN_TEMP_FILL: float("nan"),
            "impact_grows_monotonically": False,
            "decomposition_valid": False,
        }
    pf, tf = p[fin], t[fin]
    mo1 = pf + tf                       # permanent + temporary == mo1_mid
    sp, st = pf.std(), tf.std()
    corr = (float(np.corrcoef(pf, tf)[0, 1]) if sp > 0.0 and st > 0.0
            else float("nan"))
    mean_t = float(tf.mean())
    grows = bool(np.abs(pf).mean() > np.abs(mo1).mean())
    valid = bool(np.isfinite(corr) and corr > CORR_PERM_TEMP_MAX and mean_t > 0.0)
    return {
        "n_fills": n,
        K_FILL_CORR: corr,
        K_MEAN_PERM_FILL: float(pf.mean()),
        K_MEAN_TEMP_FILL: mean_t,
        "impact_grows_monotonically": grows,
        "decomposition_valid": valid,
    }


# ==================== per-slice driver ====================
def analyse_slice(taker_id, permanent, temporary, temporary10, mo60_mid, rng):
    """Full temp/perm result block for one slice (coin or pooled), all K in K_LIST.

    For each K:
      * naive (same-sample) loadings + rank corr of toxicity vs perm / temp
        (perm leg flagged as a near-identity);
      * split-sample (odd/even) rank corr of toxicity_A vs perm_B / temp_B (the
        honest headline) + permutation null on the perm-minus-temp gap;
      * whale-drop robustness on the naive same-sample gap.

    The permanent-vs-temporary verdict flags are GATED on the fill-level
    decomposition_valid diagnostic: on this sample permanent and temporary are
    ~ -0.96 correlated (no genuine reversion), so the split does not support an
    independent permanent-impact result and the flags read False.
    """
    diag = _decomposition_diagnostics(permanent, temporary)
    decomp_valid = diag["decomposition_valid"]
    block = {"decomposition_diagnostics": diag}
    for K in K_LIST:
        loads = per_wallet_loadings(
            taker_id, permanent, temporary, temporary10, mo60_mid, K)
        if loads is None:
            block[f"K{K}"] = {"n_wallets": 0,
                              "note": "too few eligible wallets at this K"}
            continue

        # ---- naive same-sample correlations (perm leg ~ tautology) ----
        corr_perm = spearman(loads["toxicity"], loads["perm_loading"])
        corr_temp = spearman(loads["toxicity"], loads["temp_loading"])
        corr_temp10 = spearman(loads["toxicity"], loads["temp10_loading"])
        naive_gap = (corr_perm - corr_temp
                     if (np.isfinite(corr_perm) and np.isfinite(corr_temp))
                     else float("nan"))

        # mean loadings (bps) across eligible wallets, with simple dispersion
        def _ms(a):
            a = np.asarray(a, dtype=np.float64)
            a = a[np.isfinite(a)]
            return (float(a.mean()) if a.size else float("nan"),
                    float(a.std(ddof=0)) if a.size else float("nan"))
        perm_mean, perm_sd = _ms(loads["perm_loading"])
        temp_mean, temp_sd = _ms(loads["temp_loading"])
        temp10_mean, temp10_sd = _ms(loads["temp10_loading"])

        whales = _whale_drop_gap(loads)

        # ---- split-sample (identity-breaking) headline ----
        split = per_wallet_split_loadings(
            taker_id, permanent, temporary, mo60_mid, K_HALF_MIN,
            np.random.default_rng(SEED + K))
        if split is None:
            split_block = {"n_wallets": 0,
                           "note": "too few wallets with both halves >= K_half",
                           "decomposition_valid": decomp_valid}
        else:
            sc_perm = spearman(split["toxicity_A"], split["perm_B"])
            sc_temp = spearman(split["toxicity_A"], split["temp_B"])
            split_gap = (sc_perm - sc_temp
                         if (np.isfinite(sc_perm) and np.isfinite(sc_temp))
                         else float("nan"))
            # Seeding is left exactly as published (SEED*3 + K). settings.rng offers
            # a per-cell stream that would be better, but switching to it would move
            # every p-value in this artifact, and a seeding change is owed its own
            # recompute rather than being made in passing during a renaming.
            p_gap, null_mean, null_sd, gap_procedure = _perm_gap_pvalue(
                split["toxicity_A"], split["perm_B"], split["temp_B"],
                split_gap, np.random.default_rng(SEED * 3 + K))
            # honest verdict: the permanent/temporary split must FIRST be a valid
            # decomposition (temporary genuinely reverts and is not just -permanent;
            # decomp_valid), THEN permanent must beat temporary out-of-half AND that
            # margin must clear the permutation null. On this sample decomp_valid is
            # False (corr ~ -0.96, monotonic growth), so perm_wins/loads read False:
            # "perm beats temp" is mechanical here, not an independent result.
            perm_wins = bool(
                decomp_valid
                and np.isfinite(sc_perm) and np.isfinite(sc_temp)
                and sc_perm > sc_temp and sc_perm > 0)
            gap_significant = bool(np.isfinite(p_gap) and p_gap <= 0.05)
            corr_pt = diag[K_FILL_CORR]
            verdict = (
                "PASSED - temporary leg reverts and is separable from permanent"
                if decomp_valid else
                ("FAILED - permanent (mo60) and temporary (mo1 - mo60) are "
                 f"{corr_pt:.2f}-correlated at fill level and mid impact grows "
                 "monotonically with horizon, so 'temporary' is continued price "
                 "discovery (drift), not reverting own-impact. Not an independent "
                 "permanent-vs-transient split; the only surviving signal is the "
                 "odd/even split-half persistence of the 60s markout, which "
                 "corroborates ks2_persistence_10day and is NOT an independent "
                 "permanent-impact result."))
            split_block = {
                "n_wallets": int(split["n_wallets"]),
                "k_half_min": K_HALF_MIN,
                K_RC_PERM_SPLIT: sc_perm,
                K_RC_TEMP_SPLIT: sc_temp,
                K_GAP: split_gap,
                "perm_permutation_p_two_sided": p_gap,
                "p_floor": P_FLOOR,
                "perm_null_mean_gap": null_mean,
                "perm_null_std_gap": null_sd,
                "perm_gap_procedure": gap_procedure,
                "decomposition_valid": decomp_valid,
                "permanent_beats_temporary": perm_wins,
                "gap_outside_null_p_le_0p05": gap_significant,
                "loads_on_permanent_not_temporary": bool(
                    perm_wins and gap_significant),
                "decomposition_verdict": verdict,
            }

        block[f"K{K}"] = {
            "n_wallets": loads["n_wallets"],
            "min_fills_K": K,
            K_MEAN_PERM: perm_mean,
            K_STD_PERM: perm_sd,
            K_MEAN_TEMP: temp_mean,
            K_STD_TEMP: temp_sd,
            K_MEAN_TEMP10: temp10_mean,
            K_STD_TEMP10: temp10_sd,
            "naive_same_sample": {
                K_RC_PERM: corr_perm,
                K_RC_TEMP: corr_temp,
                K_RC_TEMP10: corr_temp10,
                K_GAP: naive_gap,
                "caveat": (f"toxicity == per-wallet mean "
                           f"{H.headline_mid_col(PERM_H)} == permanent loading "
                           "on the SAME fills, so the perm correlation is "
                           "near-tautological (~1); read the split-sample block, "
                           "not this, as the headline"),
            },
            f"whale_robustness_naive_gap_{WHALE_KEY}": whales,
            "split_sample_headline": split_block,
        }
    return block


# ==================== I/O + main ====================
def _load_mid_npz(data_root):
    # The root stays whatever --data-root / CAP_DATA_ROOT resolved to; only the name of
    # the file and the "it is missing, run this" message move into panel_io, which names
    # i4_midmarkout.py as the producer exactly as this function used to.
    path = os.path.join(P.data_root(data_root), "quickwin_markouts_mid.npz")
    # panel_io names i4_midmarkout.py as the producer when the file is absent, exactly as
    # this function used to; the load stays here because build.py derives this script's
    # input edge from the argument of np.load.
    P.require_present("mid", path)
    z = np.load(path, allow_pickle=False)
    return z, path


def main():
    t0 = artifact.start_clock()
    ap = argparse.ArgumentParser(
        description="Huang-Stoll / Hasbrouck temporary-vs-permanent mid-impact "
                    "decomposition + per-counterparty permanent/temporary loadings.")
    ap.add_argument(
        "--data-root", default=os.environ.get("CAP_DATA_ROOT", HERE),
        help="directory holding %s / %s / output (default: this script's dir "
             "or $CAP_DATA_ROOT)." % (MID_NPZ_NAME, OUT_NAME))
    args = ap.parse_args()
    data_root = os.path.abspath(args.data_root)

    z, npz_path = _load_mid_npz(data_root)
    taker_id = z["taker_id"].astype(np.int64)
    coin = z["coin"].astype(np.int8)
    # Read only to state the window in the artifact's scope; it enters no computation.
    day = z["day"].astype(np.int64)
    # The three rungs through panel_io, which builds each column name from the ladder
    # settings.py declares and takes the lens from the FILE. They used to be three
    # string literals, which is a window fixed in a place no search for the word
    # horizon reaches. P.score returns a float64 COPY, as .astype did, so the join-
    # quality blanking a few lines down still writes into this file's own arrays.
    mo1_mid = P.score(z, "mid", EARLY_H)
    mo10_mid = P.score(z, "mid", MID_H)
    mo60_mid = P.score(z, "mid", PERM_H)

    # JOIN-QUALITY GATE: keep a fill's markouts only where the entry snapshot and
    # the relevant horizon snapshot both joined within tolerance. i4_midmarkout
    # already nan's badly-joined horizons, but the gap fields let us be explicit
    # and consistent: blank a horizon whose entry OR horizon gap exceeds tolerance.
    gap_entry = z["gap_entry_ms"].astype(np.float64)
    gap_h1 = z["gap_h1_ms"].astype(np.float64)
    gap_h10 = z["gap_h10_ms"].astype(np.float64)
    gap_h60 = z["gap_h60_ms"].astype(np.float64)
    bad_entry = ~np.isfinite(gap_entry) | (gap_entry > GAP_MAX_MS)
    mo1_mid[bad_entry | ~np.isfinite(gap_h1) | (gap_h1 > GAP_MAX_MS)] = np.nan
    mo10_mid[bad_entry | ~np.isfinite(gap_h10) | (gap_h10 > GAP_MAX_MS)] = np.nan
    mo60_mid[bad_entry | ~np.isfinite(gap_h60) | (gap_h60 > GAP_MAX_MS)] = np.nan

    permanent, temporary, temporary10 = decompose_fills(mo1_mid, mo10_mid, mo60_mid)

    taker_map_path = os.path.join(data_root, TAKER_MAP_NAME)
    n_takers_mapped = 0
    if os.path.exists(taker_map_path):
        try:
            # The map file is a wrapper, {"_direction": ..., "map": {hex: int}}; a bare
            # len() of the top level counts the two wrapper keys, and that is exactly
            # what the committed temp_perm_results.json reports (n_takers_mapped = 2).
            with open(taker_map_path) as fh:
                _tm = json.load(fh)
            n_takers_mapped = (len(_tm.get("map", _tm))
                               if isinstance(_tm, dict) else 0)
        except (ValueError, OSError):
            n_takers_mapped = 0

    rng = np.random.default_rng(SEED)

    # What every number in this file was computed under. It used to sit inside the
    # payload's _meta; artifact.write is the single place that stamps it, so keeping
    # it here as well would give one record two homes.
    settings_used = dict(
        h=PERM_H, lens=LENS,
        permanent_leg_horizon_s=PERM_H,
        temporary_leg_horizons_s=[EARLY_H, PERM_H],
        temporary10_leg_horizons_s=[MID_H, PERM_H],
        mid_columns=[H.headline_mid_col(h)
                     for h in (EARLY_H, MID_H, PERM_H)],
        k_half_min=K_HALF_MIN,
        gap_max_ms=GAP_MAX_MS,
        corr_perm_temp_max=CORR_PERM_TEMP_MAX,
        whale_drop=H.whale_drop("fill_count", N_DROP_WHALES),
        # H.fingerprint asserts a migrating declaration only when the caller
        # states what its run used; this one uses the declared seed and the
        # declared 2000 draws, bootstraps nothing and ranks on no fill floor.
        master_seed=SEED, n_perm=N_PERM, p_floor=P_FLOOR,
        settings_not_used=["n_boot", "rank_floor_fills"])

    results = {
        "_meta": {
            "object": ("Huang-Stoll/Hasbrouck temporary-vs-permanent mid-impact "
                       "decomposition + per-counterparty loadings"),
            "seed": SEED,
            "decomposition": {
                K_MEAN_PERM_FILL: f"{H.headline_mid_col(PERM_H)} (long-horizon "
                                  f">={PERM_H}s signed mid move; non-reverting "
                                  f"information component)",
                K_MEAN_TEMP_FILL: f"{H.headline_mid_col(EARLY_H)} - "
                                  f"{H.headline_mid_col(PERM_H)} (Huang-Stoll "
                                  f"realized-spread: early effective impact minus "
                                  f"permanent; the reverting transient own-impact)",
                _f("temporary10_bps", LEG_TEMP10):
                    f"{H.headline_mid_col(MID_H)} - {H.headline_mid_col(PERM_H)} "
                    f"(reversion remaining at {MID_H}s)",
                "identity": (f"permanent + temporary == "
                             f"{H.headline_mid_col(EARLY_H)} by construction"),
                "sign": "positive = taker profited = maker adversely selected",
            },
            "toxicity_score": (f"established per-counterparty score = per-wallet "
                               f"mean {H.headline_mid_col(PERM_H)} (the i3/ks2 "
                               f"ranking statistic at the {PERM_H}s window)"),
            "toxicity_score_window_note": (
                f"This object ranks wallets on the {PERM_H}s book mid because that "
                f"is where its permanent leg is defined. The study's HEADLINE window "
                f"is {H.HEADLINE_HORIZON_S}s, so these rank correlations are not the "
                f"headline persistence figures and must not be quoted as them. Every "
                f"field name states the window it belongs to."),
            "field_suffix_style": H.FIELD_SUFFIX_STYLE,
            "field_suffix_note": (
                f"A leg built from ONE window carries that window ('_{LEG_PERM}'); a "
                f"leg built from a DIFFERENCE of two carries both "
                f"('_{LEG_TEMP}'); every one of them ends in the lens '_{LENS}', "
                f"because these are book-mid numbers and the trade-print markout of "
                f"the same fill is a different quantity."),
            "identity_guard": ("naive same-sample perm correlation is ~tautological "
                               "(toxicity IS the wallet mean mo60 = permanent "
                               "loading); the SPLIT-SAMPLE odd/even block "
                               "(toxicity on half A, loadings on half B) is the "
                               "honest headline"),
            "K_list": list(K_LIST),
            "k_half_min": K_HALF_MIN,
            "n_perm": N_PERM,
            "p_floor": P_FLOOR,
            "n_drop_whales": N_DROP_WHALES,
            "gap_max_ms": GAP_MAX_MS,
            "n_takers_mapped": n_takers_mapped,
            "n_rows_total": int(taker_id.size),
            "prediction": ("rank_corr(toxicity, permanent) > rank_corr(toxicity, "
                           "temporary) out-of-half, gap outside the permutation "
                           "null -> per-counterparty toxicity loads on the "
                           "PERMANENT (information) leg, not transient own-impact"),
            "decomposition_verdict": (
                "FAILED - the permanent (mo60) and temporary (mo1 - mo60) legs are "
                "strongly NEGATIVELY correlated at fill level (~ -0.96 on this "
                "sample; see each slice's "
                f"decomposition_diagnostics.{K_FILL_CORR}) and mid "
                "impact grows monotonically with horizon, so 'temporary' captures "
                "continued price discovery (drift), not reverting own-impact. The "
                "Huang-Stoll / Hasbrouck permanent-vs-transient LABEL does not "
                "apply on this sample. The only surviving, usable signal is the "
                "odd/even split-half persistence of the 60s markout, which merely "
                "corroborates ks2_persistence_10day and is NOT an independent "
                "permanent-impact result. Accordingly the per-slice "
                "'permanent_beats_temporary' and 'loads_on_permanent_not_temporary' "
                "flags are gated on decomposition_valid and read False."),
        }
    }

    # per coin
    for code, name in COIN_CODES.items():
        sel = coin == code
        if not np.any(sel):
            results[name] = {"note": "no rows for this coin"}
            continue
        results[name] = analyse_slice(
            taker_id[sel], permanent[sel], temporary[sel], temporary10[sel],
            mo60_mid[sel], rng)

    # pooled (headline)
    results["pooled"] = analyse_slice(
        taker_id, permanent, temporary, temporary10, mo60_mid, rng)

    # What the numbers cover. The unit of analysis is the WALLET, split odd/even
    # within wallet, so the population names the per-half floor that admits one.
    days = np.unique(day)
    scope = {
        "population": (f"{taker_id.size:,} rows of the book-mid panel reduced to "
                       f"per-wallet loadings; a wallet enters the split-half block "
                       f"only with at least {K_HALF_MIN} fills in EACH half, and the "
                       f"rank cells run over {list(K_LIST)} fills"),
        "window": (f"{days.size} days present in the input, day-of-month "
                   f"{days.min()}-{days.max()}; the split is odd/even WITHIN wallet "
                   "rather than early against late, so every day enters both halves"),
        "coins": [COIN_CODES[c] for c in sorted(COIN_CODES)],
    }

    # The output name and directory still come from OUT_NAME and the resolved data
    # root, so a caller that redirects either redirects the whole write, as before.
    out_path = artifact.write(os.path.basename(OUT_NAME), results,
                              script=__file__, inputs=[npz_path], scope=scope,
                              settings=settings_used, started=t0,
                              out_dir=data_root)

    _print_summary(results, out_path)


# -------------------- printed summary --------------------
def _fmt(x, nd=4):
    return f"{x:.{nd}f}" if isinstance(x, float) and np.isfinite(x) else "n/a"


def _print_summary(results, out_path):
    print("=" * 88)
    print("TEMP/PERM - Huang-Stoll/Hasbrouck decomposition + per-counterparty loadings")
    print("=" * 88)
    print("  permanent = mo60_mid (info, non-reverting);  temporary = mo1_mid - mo60_mid")
    print("  toxicity  = per-wallet mean mo60_mid (the i3/ks2 score).  +ve = maker adverse.")
    print(f"  rows={results['_meta']['n_rows_total']:,}  seed={results['_meta']['seed']}  "
          f"perm={results['_meta']['n_perm']} (p-floor={results['_meta']['p_floor']:.4f})")
    print("-" * 88)
    for K in K_LIST:
        kk = f"K{K}"
        print(f"\n  [min fills K = {K}]  per-wallet loadings (bps) and rank corr "
              f"vs toxicity")
        h = (f"  {'slice':<7} {'n_wal':>6} {'permLoad':>9} {'tempLoad':>9} | "
             f"{'naive rc_perm':>13} {'naive rc_temp':>13}")
        print(h)
        print("-" * len(h))
        for key in ("BTC", "ETH", "pooled"):
            blk = results.get(key, {})
            cell = blk.get(kk) if isinstance(blk, dict) else None
            if not cell or cell.get("n_wallets", 0) == 0:
                print(f"  {key:<7} {'--':>6}  (no eligible wallets)")
                continue
            ns = cell["naive_same_sample"]
            print(f"  {key:<7} {cell['n_wallets']:>6} "
                  f"{_fmt(cell[K_MEAN_PERM], 3):>9} "
                  f"{_fmt(cell[K_MEAN_TEMP], 3):>9} | "
                  f"{_fmt(ns[K_RC_PERM], 3):>13} "
                  f"{_fmt(ns[K_RC_TEMP], 3):>13}")

        print(f"\n  [min fills K = {K}]  SPLIT-SAMPLE headline (toxicity on half A, "
              f"loadings on half B - the identity-breaking test)")
        h2 = (f"  {'slice':<7} {'n_wal':>6} {'rc_permB':>9} {'rc_tempB':>9} "
              f"{'gap':>8} {'perm_p':>8} {'verdict':>22}")
        print(h2)
        print("-" * len(h2))
        for key in ("BTC", "ETH", "pooled"):
            blk = results.get(key, {})
            cell = blk.get(kk) if isinstance(blk, dict) else None
            sp = cell.get("split_sample_headline") if cell else None
            if not sp or sp.get("n_wallets", 0) == 0:
                print(f"  {key:<7} {'--':>6}  (no split-eligible wallets)")
                continue
            verdict = ("perm>temp (p ok)" if sp.get("loads_on_permanent_not_temporary")
                       else ("perm>temp (p n.s.)" if sp.get("permanent_beats_temporary")
                             else "temp not beaten"))
            print(f"  {key:<7} {sp['n_wallets']:>6} "
                  f"{_fmt(sp[K_RC_PERM_SPLIT], 3):>9} "
                  f"{_fmt(sp[K_RC_TEMP_SPLIT], 3):>9} "
                  f"{_fmt(sp[K_GAP], 3):>8} "
                  f"{_fmt(sp['perm_permutation_p_two_sided'], 4):>8} "
                  f"{verdict:>22}")
    print("-" * 88)
    print("  READING: a positive rc with PERMANENT that beats rc with TEMPORARY")
    print("  out-of-half (split-sample) and clears the permutation null means the")
    print("  established per-counterparty toxicity loads on the PERMANENT (information)")
    print("  leg, not the transient own-impact (temporary) leg - the substantive claim.")
    print("=" * 88)
    print(f"  results -> {os.path.basename(out_path)}")


if __name__ == "__main__":
    main()
