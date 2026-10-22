"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-22
References: [Hyperliquid L4 (Zenodo 18184441, Albers et al. 2026); node_fills_by_block]
"""

# ===========================================================================
# Probe G - TRANSIENT vs PERMANENT markout + horizon grid (BOOK MID).
# ---------------------------------------------------------------------------
# WHAT THIS DOES (and why it goes beyond temp_perm_decomp.py)
#   temp_perm_decomp.py read only the THREE pre-computed mid markouts already in
#   quickwin_markouts_mid.npz (1s/10s/60s) and labelled mo60 "permanent",
#   mo1-mo60 "temporary". An adversarial verify (recorded in that file's header)
#   showed that on this December BTC/ETH book sample mid-impact GROWS monotonically
#   out to 60s (~88% of fills have |mo60|>|mo1|), so a 1s..60s window cannot see
#   reversion at all and the permanent/temporary LABEL there is an over-label.
#
#   Probe G fixes the measurement window. It RE-MARKS every Dec 4-13 BTC+ETH fill
#   against the L2 book mid at a FULLER horizon grid
#       {0.1, 1, 5, 30, 300} seconds
#   so the curve can be seen to keep drifting (permanent / private information) OR
#   to rise and then mean-revert toward 0 (transient stale-quote sniping / latency
#   arb = a SPEED edge, not toxicity). The 300s tail is the load-bearing addition:
#   reversion that has not happened by 60s can still happen by 300s. We then build
#   a per-counterparty DECAY curve and classify the SHAPE.
#
# REFERENCE PRICE = BOOK MID (mid_series_{BTC,ETH}.npz), the INFORMATION lens.
#   The task's reference-mid rule: the trade-print reference is the execution-cost
#   lens (includes spread); the book mid is the information lens but its LEVEL is
#   inflated ~4x by own-spread-crossing, so we trust the cross-sectional RANKING /
#   the curve SHAPE, never the absolute level. Every classification statistic here
#   is shape-based (reversion fraction, ranks), never a level threshold. The HL
#   oracle/mark price is a stake-weighted median of CEX mids and is NEVER used
#   (it would be circular). This probe never touches it.
#
# MARKOUT SIGN (build convention, kept):
#   mo(h) = sign_taker * (mid(t+h) - mid(t)) / mid(t) * 1e4   [bps]
#   sign_taker = +1 if taker BOUGHT (taker_side==1) else -1.
#   POSITIVE = taker profited = maker adverse-selected.
#   We mark from the crossed=true taker leg; the crossed=false maker leg only
#   gives counterparty identity/size (handled upstream in parse_day).
#
# NO-LOOKAHEAD JOIN (the 7/7 unit-tested convention, reused verbatim from
# i4_midmarkout.py):
#   entry   = last snapshot at-or-before t_fill  = searchsorted(side='right') - 1
#   horizon = first snapshot at-or-after t_fill+h = searchsorted(side='left')
#   a query past the last snapshot -> nan. A per-leg join-gap tolerance
#   (GAP_MAX_MS) blanks a horizon whose entry OR horizon snapshot is too far from
#   target, so a loosely-joined snapshot cannot fake impact.
#
# SHAPE CLASSIFICATION (per counterparty, and pooled, per coin):
#   For a wallet's mean curve m(h) over the grid, let h* = argmax_h |m(h)| (the
#   peak-impact horizon) and m_end = m(300s). Define the signed
#       reversion_fraction = (m(h*) - m_end) / m(h*)        when m(h*) != 0
#   read on the curve oriented by its own peak sign:
#       ~0   -> PERMANENT  (drift does not revert; private information = toxicity)
#       ->1  -> TRANSIENT  (rises to a peak then snaps back toward 0; speed edge)
#       >1   -> OVER-REVERTS (snaps past 0 / reverses sign; strongly transient)
#   A wallet is labelled PERMANENT if reversion_fraction <= REV_PERM (0.25),
#   TRANSIENT if >= REV_TRANS (0.75), else MIXED. The HEADLINE is the population
#   SPLIT (what share of toxic counterparties are permanent vs transient) and the
#   pooled curve shape, NOT any single wallet.
#
# GUARDS / FALSIFIERS (pre-registered):
#   * PLACEBO = random wallets. Shuffle the counterparty label across fills and
#     rebuild the per-wallet curves; the real BETWEEN-WALLET dispersion of the
#     reversion_fraction (the curve-shape heterogeneity) must beat the shuffled
#     null. If the real shape dispersion does not exceed the random-wallet null,
#     "different counterparties have different decay shapes" is not earned.
#   * SIGN-PERSISTENCE of the decay. Split each wallet's fills odd/even; the
#     per-wallet reversion_fraction on half A must rank-correlate (Spearman) with
#     half B out-of-sample, beating a permutation null. A decay SHAPE that is a
#     stable counterparty trait persists out-of-half; pure noise does not.
#   * WHALE-DROP. Drop the top-5 counterparties by fill count; the pooled curve
#     shape and the permanent/transient split must keep their sign/ordering.
#   * PER-COIN always (BTC, ETH) plus pooled; never pooled-only.
#
# PRE-REGISTERED KILL-CRITERION
#   The probe is KILLED (its "private-information / permanent toxicity" reading
#   fails) if EITHER
#     (a) the pooled book-mid curve REVERTS - i.e. |m(300s)| < 0.5 * |m(h*)| in
#         BOTH BTC and ETH (the long-horizon drift snaps back, so the signal is a
#         transient speed edge, not information); OR
#     (b) the split-half rank-persistence of the per-wallet reversion_fraction
#         does NOT beat its permutation null (p > 0.05) AND the real between-wallet
#         shape dispersion does NOT beat the random-wallet placebo (p > 0.05) -
#         i.e. decay SHAPE is not a counterparty trait at all.
#   If (a): the toxicity is a SPEED edge. If (b): there is no per-counterparty
#   shape structure to exploit. Either way the "permanent private-information"
#   framing does not hold and must not be claimed.
#
# DATA (heavy; the main loop runs this, not the author):
#   re-parses Dec 4-13 BTC+ETH fills via build_quickwin_markouts.parse_day to
#   recover the fill block_time (ns) + taker_side + counterparty addr (the npz
#   stores only the 1/10/60s markouts, NOT the fill timestamp, so a finer grid
#   MUST be re-marked from the raw fills), then joins each fill to the full-window
#   mid_series_{BTC,ETH}.npz. Row order matches quickwin_markouts.npz by reusing
#   the same parse loop; the integer taker_id is rebuilt the same first-seen way.
#
# Run command (bare python3 is BLOCKED on this machine):
#   uv run --no-project --with-requirements requirements.txt python3 probes/probe_G_horizon.py
# Smoke slice: CAP_DAYS=20251204 CAP_COINS=BTC ... (honoured via _apply_env_overrides,
#   which MUTATES bqm.DAYS / bqm.COINS - build_quickwin reads no env vars itself).
# ---------------------------------------------------------------------------

import os
import sys

import numpy as np

# artifact and stats live one directory up (the repository root); build_quickwin_markouts
# moved into the `data` group on 2026-08-11, so that directory goes on the path too. The
# group is named rather than globbed, so a module that moves again fails loudly here
# instead of being resolved by whichever directory happens to hold a matching name.
_HERE = os.path.dirname(os.path.abspath(__file__))
_CODE_DIR = os.path.dirname(_HERE)
if _CODE_DIR not in sys.path:
    sys.path.insert(0, _CODE_DIR)
_DATA_DIR = os.path.join(_CODE_DIR, "data")
if _DATA_DIR not in sys.path:
    sys.path.insert(0, _DATA_DIR)
import artifact  # noqa: E402
import build_quickwin_markouts as bqm  # noqa: E402
import stats  # noqa: E402

# -------------------- configuration --------------------
# The placebo and permutation seed. NOT settings.MASTER_SEED, which is 20260620, and
# two days off it rather than unrelated -- the literal was typed on the day the probe
# was written. Left alone: the dispersion placebo opens at SEED + 11 and the split-half
# permutation at SEED + 23, so every p in this file counts against a stream this literal
# fixes, and rebinding it would move both. Recorded as an override in the fingerprint.
SEED = 20260622

MID_PATH = {c: os.path.join(_CODE_DIR, f"mid_series_{c}.npz") for c in ("BTC", "ETH")}
OUT_NAME = os.path.join(_HERE, "probe_G_horizon_results.json")

COIN_CODE = {"BTC": 0, "ETH": 1}
COIN_LABEL = {0: "BTC", 1: "ETH"}

# the fuller horizon grid (seconds). 0.1s catches sub-second latency arb; 300s is
# the load-bearing tail that lets reversion appear after 60s.
HORIZONS_S = (0.1, 1.0, 5.0, 30.0, 300.0)
MS_PER_S = 1000.0
GAP_MAX_MS = 5000.0          # per-leg join-gap tolerance (matches i4_midmarkout)

# per-counterparty eligibility: a wallet needs >= K fills with a FULL curve
# (every horizon finite) to get a stable curve shape.
K_MIN = 50
K_HALF_MIN = 20              # >= this many full-curve fills in EACH odd/even half

# shape thresholds on the signed reversion fraction (read on the peak-oriented
# curve): <=PERM -> permanent (information), >=TRANS -> transient (speed edge).
REV_PERM = 0.25
REV_TRANS = 0.75

N_PERM = 2000               # placebo / permutation draws
P_FLOOR = 1.0 / (N_PERM + 1)
N_DROP_WHALES = 5           # drop top-5 counterparties by fill count (task rule)


# -------------------- smoke-test ENV overrides --------------------
# Mirror i4_midmarkout._apply_env_overrides: build_quickwin_markouts hardcodes
# DAYS/COINS as module constants and reads NO env vars itself, so a smoke slice
# must MUTATE bqm.DAYS / bqm.COINS here (the prior version only documented this in
# a comment and never applied it, so CAP_DAYS/CAP_COINS were silently ignored and
# the "smoke slice" still parsed all 10 days). Probe G is BTC+ETH only (the
# l2_cache has no SOL book), so coins are filtered to those with a mid series.
def _apply_env_overrides():
    days = os.environ.get("CAP_DAYS")
    coins = os.environ.get("CAP_COINS")
    if days:
        bqm.DAYS = [d.strip() for d in days.split(",") if d.strip()]
    if coins:
        cs = tuple(c.strip().upper() for c in coins.split(",") if c.strip())
        cs = tuple(c for c in cs if c in MID_PATH)   # BTC/ETH only (have a book)
        if cs:
            bqm.COINS = cs
        else:
            print("[probeG] CAP_COINS had no BTC/ETH entry - keeping bqm.COINS")


# ==================== rank / correlation helpers (numpy-only) ====================
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
    if n < 3 or y.size != n:
        return float("nan")
    finite = np.isfinite(x) & np.isfinite(y)
    if finite.sum() < 3:
        return float("nan")
    rx, ry = _rankdata(x[finite]), _rankdata(y[finite])
    rx -= rx.mean()
    ry -= ry.mean()
    denom = np.sqrt((rx * rx).sum() * (ry * ry).sum())
    return float("nan") if denom == 0 else float((rx * ry).sum() / denom)


# ==================== mid series loader (full window, in memory) ====================
def load_mid_series(coins):
    """Load mid_series_{COIN}.npz for each active coin, t_ms ascending + de-duped.

    Returns {coin: {"t_ms","mid"}}. Only t_ms + mid are needed for the markout.
    """
    series = {}
    for coin in coins:
        path = MID_PATH.get(coin)
        if path is None or not os.path.exists(path):
            raise FileNotFoundError(
                f"missing mid series for {coin}: {path} - run i4_l2_mid.py first")
        z = np.load(path)
        t_ms = np.asarray(z["t_ms"], dtype=np.int64)
        mid = np.asarray(z["mid"], dtype=np.float64)
        if t_ms.size:
            order = np.argsort(t_ms, kind="stable")
            t_ms, mid = t_ms[order], mid[order]
            keep = np.ones(t_ms.size, dtype=bool)
            keep[:-1] = t_ms[1:] != t_ms[:-1]     # runs of equal t_ms -> keep last
            t_ms, mid = t_ms[keep], mid[keep]
        series[coin] = {"t_ms": t_ms, "mid": mid}
        print(f"[probeG] loaded mid_series_{coin}: {t_ms.size:,} snapshots")
    return series


# ==================== as-of joins (the JOIN GUARDS, vectorized) ====================
def _join_entry(t_fill_ms, S):
    """LAST snapshot STRICTLY EARLIER than t_fill: searchsorted left - 1.

    Was `right - 1` until 2026-08-02, which accepted a snapshot stamped with the fill's
    own millisecond. Such a snapshot already carries the fill's own impact, so the entry
    mid it supplies is contaminated by the quantity being measured. Changed together with
    the three other copies of this rule in the tree; the rule having four copies rather
    than one home is the defect underneath."""
    t_arr = S["t_ms"]
    idx = np.searchsorted(t_arr, t_fill_ms, side="left") - 1
    valid = idx >= 0
    gap = np.full(t_fill_ms.shape, np.inf, dtype=np.float64)
    safe = np.where(valid, idx, 0)
    gap[valid] = np.abs(t_fill_ms[valid] - t_arr[safe[valid]].astype(np.float64))
    valid &= gap <= GAP_MAX_MS
    return idx, valid


def _join_horizon(t_fill_ms, h_s, S):
    """FIRST snapshot t>=t_fill+h*1000 (first at-or-after): searchsorted left."""
    t_arr = S["t_ms"]
    n = t_arr.size
    target = t_fill_ms.astype(np.float64) + h_s * MS_PER_S
    idx = np.searchsorted(t_arr, target, side="left")
    valid = idx < n
    gap = np.full(t_fill_ms.shape, np.inf, dtype=np.float64)
    safe = np.where(valid, idx, 0)
    gap[valid] = np.abs(t_arr[safe[valid]].astype(np.float64) - target[valid])
    valid &= gap <= GAP_MAX_MS
    return idx, valid


def mark_grid(t_fill_ms, taker_side, S):
    """Signed book-mid markout (bps) at every horizon for one coin-day slice.

    Returns an (n, len(HORIZONS_S)) float64 array; nan where either leg is an
    invalid / out-of-tolerance join or the entry mid is non-positive.
    POSITIVE = taker profited = maker adverse-selected.
    """
    n = t_fill_ms.size
    out = np.full((n, len(HORIZONS_S)), np.nan, dtype=np.float64)
    if n == 0 or S["t_ms"].size == 0:
        return out
    e_idx, e_valid = _join_entry(t_fill_ms, S)
    e_safe = np.where(e_valid, e_idx, 0)
    mid_entry = S["mid"][e_safe]
    entry_ok = e_valid & np.isfinite(mid_entry) & (mid_entry > 0)
    sign_taker = np.where(taker_side == 1, 1.0, -1.0)
    for j, h in enumerate(HORIZONS_S):
        h_idx, h_valid = _join_horizon(t_fill_ms, h, S)
        h_safe = np.where(h_valid, h_idx, 0)
        mid_h = S["mid"][h_safe]
        ok = entry_ok & h_valid & np.isfinite(mid_h)
        mo = sign_taker * (mid_h - mid_entry) / mid_entry * 1e4
        out[ok, j] = mo[ok]
    return out


# ==================== curve shape statistics ====================
def _signed_reversion_fraction(curve):
    """Signed reversion fraction of one mean curve m(h) over the grid.

    h* = argmax|m|; oriented by sign(m(h*)); fraction = (m(h*)-m_end)/m(h*).
    ~0 permanent, ->1 transient, >1 over-reverts. NaN if the peak is ~0 or the
    curve has a nan at the peak / end horizon.
    """
    c = np.asarray(curve, dtype=np.float64)
    if c.size != len(HORIZONS_S) or not np.all(np.isfinite(c)):
        return float("nan")
    k = int(np.argmax(np.abs(c)))
    peak = c[k]
    if abs(peak) < 1e-9:
        return float("nan")
    end = c[-1]                                   # m(300s)
    return float((peak - end) / peak)


def _per_wallet_curves(taker_id, grid, k_min):
    """Per-wallet mean curve (full-curve fills only) for wallets with >= k_min.

    grid is (n, H). A fill enters a wallet's curve only if its WHOLE row is finite
    (so the same fills define every horizon of that wallet's curve - the curve is
    internally comparable across horizons). Returns dict with wallet_ids, curves
    (n_w, H), fills (per-wallet full-curve count), rev_frac (per wallet).
    """
    taker_id = np.asarray(taker_id, dtype=np.int64)
    full = np.all(np.isfinite(grid), axis=1)
    if full.sum() == 0:
        return None
    tid = taker_id[full]
    g = grid[full]
    uniq, inv = np.unique(tid, return_inverse=True)
    n_w = uniq.size
    H = g.shape[1]
    ssum = np.zeros((n_w, H), dtype=np.float64)
    for j in range(H):
        np.add.at(ssum[:, j], inv, g[:, j])
    cnt = np.bincount(inv, minlength=n_w).astype(np.float64)
    curves = ssum / cnt[:, None]
    elig = cnt >= k_min
    pos = np.where(elig)[0]
    if pos.size < 3:
        return None
    rev = np.array([_signed_reversion_fraction(curves[i]) for i in pos],
                   dtype=np.float64)
    return {
        "wallet_ids": uniq[pos].astype(np.int64),
        "curves": curves[pos],
        "fills": cnt[pos].astype(np.int64),
        "rev_frac": rev,
        "n_wallets": int(pos.size),
    }


def _classify_split(rev):
    """Permanent / transient / mixed counts + shares over finite reversion fracs."""
    r = np.asarray(rev, dtype=np.float64)
    r = r[np.isfinite(r)]
    n = r.size
    if n == 0:
        return {"n": 0}
    perm = int(np.sum(r <= REV_PERM))
    trans = int(np.sum(r >= REV_TRANS))
    mixed = n - perm - trans
    return {
        "n": n,
        "permanent_n": perm, "transient_n": trans, "mixed_n": mixed,
        "permanent_share": perm / n, "transient_share": trans / n,
        "mixed_share": mixed / n,
        "median_reversion_fraction": float(np.median(r)),
    }


def _vw_pooled_curve(grid, notional):
    """Notional-weighted pooled mean curve over full-curve fills (for the SHAPE)."""
    full = np.all(np.isfinite(grid), axis=1)
    if full.sum() == 0:
        return [float("nan")] * len(HORIZONS_S)
    g = grid[full]
    w = np.asarray(notional, dtype=np.float64)[full]
    w = np.where(np.isfinite(w) & (w > 0), w, 0.0)
    if w.sum() <= 0:
        w = np.ones(g.shape[0], dtype=np.float64)
    return [float(np.sum(g[:, j] * w) / np.sum(w)) for j in range(g.shape[1])]


# ==================== falsifiers ====================
def _placebo_shape_dispersion(taker_id, grid, k_min, rng, n_perm, real_disp):
    """Random-wallet placebo on the BETWEEN-wallet dispersion of reversion_frac.

    Shuffle the counterparty label across fills, rebuild per-wallet curves + their
    reversion-fraction dispersion (std). Real shape heterogeneity must exceed this
    random-label null.

    Returns the reported block: the one-sided p, the null's two moments, how many
    draws produced no curve set at all, and the counting procedure stats.py applied.

    WHAT THIS FUNCTION KEEPS AND WHAT IT HANDS OVER. The draw is the substance of the
    test and stays here. The counting -- the +1 convention, the floor, the record of
    what was counted -- goes to stats.py, and it is handed the array this function has
    always built, so the arithmetic is the arithmetic that produced the published
    numbers rather than the module's house style:

      * abs_tol=1e-12 is the absolute slack this line has always used. The module's
        default slack is RELATIVE to the scale of the comparison, which is the better
        rule for a tree whose statistics run from a correlation to a sum of dollars,
        and it is a DIFFERENT number here -- a change owed its own recompute, not a
        migration.
      * A draw that produces no curve set is substituted with 0.0 and KEPT in the
        denominator, which is this file's own convention and one stats.py deliberately
        does not share: it drops a failed draw and shrinks the denominator. Passing the
        substituted array preserves this file's denominator exactly. The substitution
        is the reason n_failed_draws is now reported: it is the number the module would
        have dropped, and the two spellings can only disagree while it is above zero
        AND the real dispersion sits at or below the tolerance, in which case the
        substituted zero counts as extreme for the module and did not count here.
        Both conditions are now visible in the artifact instead of being assumed away.
    """
    if not np.isfinite(real_disp):
        return {"p_one_sided": float("nan"),
                "null_mean_dispersion": float("nan"),
                "null_std_dispersion": float("nan"),
                "n_failed_draws": 0, "permutation": None,
                "note": "the real dispersion is not finite, so no placebo was drawn"}
    taker_id = np.asarray(taker_id, dtype=np.int64)
    n = taker_id.size
    null = np.empty(n_perm, dtype=np.float64)
    idx = np.arange(n)
    n_failed = 0
    for i in range(n_perm):
        rng.shuffle(idx)
        loads = _per_wallet_curves(taker_id[idx], grid, k_min)
        if loads is None:
            null[i] = 0.0
            n_failed += 1
            continue
        rv = loads["rev_frac"]
        rv = rv[np.isfinite(rv)]
        null[i] = float(np.std(rv, ddof=0)) if rv.size else 0.0
    perm = stats.permutation_p(real_disp, null, side="greater", abs_tol=1e-12,
                               n_requested=n_perm,
                               cell=("shape_dispersion_random_wallet_placebo", k_min))
    return {"p_one_sided": perm["p"],
            "null_mean_dispersion": float(null.mean()),
            "null_std_dispersion": float(null.std(ddof=0)),
            "n_failed_draws": int(n_failed),
            "permutation": perm}


def _split_half_persistence(taker_id, grid, k_half, rng, n_perm):
    """Odd/even split persistence of the per-wallet reversion_fraction.

    Each wallet's full-curve fills are shuffled then alternately assigned to half
    A / half B; reversion_fraction is computed on each half (needs >= k_half full
    fills per half). Observed Spearman(rev_A, rev_B) vs a permutation null that
    shuffles the B labels. Returns observed corr, p, n_wallets.
    """
    taker_id = np.asarray(taker_id, dtype=np.int64)
    full = np.all(np.isfinite(grid), axis=1)
    if full.sum() == 0:
        return None
    tid = taker_id[full]
    g = grid[full]
    n = tid.size
    order = rng.permutation(n)
    tid = tid[order]
    g = g[order]
    uniq, inv = np.unique(tid, return_inverse=True)
    n_w = uniq.size
    # within-wallet running index (stable group order) -> odd/even half id
    o2 = np.argsort(inv, kind="stable")
    inv_s = inv[o2]
    counts = np.bincount(inv, minlength=n_w)
    starts = np.zeros(n_w, dtype=np.int64)
    starts[1:] = np.cumsum(counts)[:-1]
    within = np.arange(inv_s.size) - starts[inv_s]
    half_sorted = within % 2
    half = np.empty(n, dtype=np.int64)
    half[o2] = half_sorted

    H = g.shape[1]

    def _half_curves(mask):
        gm = g[mask]
        im = inv[mask]
        ssum = np.zeros((n_w, H), dtype=np.float64)
        for j in range(H):
            np.add.at(ssum[:, j], im, gm[:, j])
        cnt = np.bincount(im, minlength=n_w).astype(np.float64)
        cur = np.full((n_w, H), np.nan, dtype=np.float64)
        nz = cnt > 0
        cur[nz] = ssum[nz] / cnt[nz, None]
        return cur, cnt

    cur_a, cnt_a = _half_curves(half == 0)
    cur_b, cnt_b = _half_curves(half == 1)
    elig = (cnt_a >= k_half) & (cnt_b >= k_half)
    pos = np.where(elig)[0]
    if pos.size < 3:
        return None
    rev_a = np.array([_signed_reversion_fraction(cur_a[i]) for i in pos])
    rev_b = np.array([_signed_reversion_fraction(cur_b[i]) for i in pos])
    fin = np.isfinite(rev_a) & np.isfinite(rev_b)
    if fin.sum() < 3:
        return None
    ra, rb = rev_a[fin], rev_b[fin]
    obs = spearman(ra, rb)
    # Permutation null: shuffle B. The draw stays here; stats.py counts it, and is
    # handed this file's own two conventions rather than its defaults, for the reasons
    # written out at _placebo_shape_dispersion above. side="two_sided" is the |c| >=
    # |obs| comparison this line has always made -- a decay shape that persists
    # NEGATIVELY out of half is as much a counterparty trait as one that persists
    # positively, so the question is genuinely two-sided and a one-sided p here would
    # be half the honest number. abs_tol=1e-12 is the slack that was written here. A
    # draw whose Spearman is not finite is substituted with 0.0 and kept in the
    # denominator, so n_failed_draws is reported beside the p.
    null = np.empty(n_perm, dtype=np.float64)
    idx = np.arange(rb.size)
    n_failed = 0
    for i in range(n_perm):
        rng.shuffle(idx)
        c = spearman(ra, rb[idx])
        if np.isfinite(c):
            null[i] = c
        else:
            null[i] = 0.0
            n_failed += 1
    perm = stats.permutation_p(obs, null, side="two_sided", abs_tol=1e-12,
                               n_requested=n_perm,
                               cell=("reversion_fraction_split_half", k_half))
    return {
        "n_wallets": int(fin.sum()),
        "k_half_min": k_half,
        "rank_corr_revA_vs_revB": obs,
        "permutation_p_two_sided": perm["p"],
        "p_floor": P_FLOOR,
        "null_mean": float(null.mean()),
        "n_failed_draws": int(n_failed),
        "permutation": perm,
    }


def _whale_drop_pooled(taker_id, grid, notional, n_drop):
    """Recompute the pooled curve + permanent/transient split after dropping the
    top-n_drop counterparties by fill count; report curve + split both ways.
    """
    taker_id = np.asarray(taker_id, dtype=np.int64)
    uniq, inv = np.unique(taker_id, return_inverse=True)
    fills = np.bincount(inv, minlength=uniq.size)
    if uniq.size <= n_drop + 3:
        return {"note": "too few wallets to whale-drop", "n_dropped": 0}
    order = np.argsort(-fills, kind="stable")
    drop_codes = set(order[:n_drop].tolist())
    keep_row = np.array([c not in drop_codes for c in inv], dtype=bool)

    full_curve = _vw_pooled_curve(grid, notional)
    drop_curve = _vw_pooled_curve(grid[keep_row], notional[keep_row])
    loads_full = _per_wallet_curves(taker_id, grid, K_MIN)
    loads_drop = _per_wallet_curves(taker_id[keep_row], grid[keep_row], K_MIN)
    split_full = _classify_split(loads_full["rev_frac"]) if loads_full else {"n": 0}
    split_drop = _classify_split(loads_drop["rev_frac"]) if loads_drop else {"n": 0}

    rf_full = _signed_reversion_fraction(np.asarray(full_curve))
    rf_drop = _signed_reversion_fraction(np.asarray(drop_curve))
    sign_ok = bool(
        np.isfinite(rf_full) and np.isfinite(rf_drop)
        and np.sign(rf_full) == np.sign(rf_drop))
    return {
        "n_dropped": int(n_drop),
        "pooled_curve_full_bps": full_curve,
        "pooled_curve_drop_bps": drop_curve,
        "pooled_reversion_fraction_full": rf_full,
        "pooled_reversion_fraction_drop": rf_drop,
        "permanent_share_full": split_full.get("permanent_share"),
        "permanent_share_drop": split_drop.get("permanent_share"),
        "reversion_sign_preserved": sign_ok,
    }


# ==================== per-slice driver ====================
def analyse_slice(taker_id, grid, notional, rng):
    """Full Probe-G result block for one slice (a coin or pooled)."""
    loads = _per_wallet_curves(taker_id, grid, K_MIN)
    pooled_curve = _vw_pooled_curve(grid, notional)
    pooled_rev = _signed_reversion_fraction(np.asarray(pooled_curve))
    n_full = int(np.sum(np.all(np.isfinite(grid), axis=1)))

    block = {
        "horizons_s": list(HORIZONS_S),
        "n_fills": int(taker_id.size),
        "n_full_curve_fills": n_full,
        "pooled_curve_vw_bps": pooled_curve,
        "pooled_reversion_fraction": pooled_rev,
        "pooled_shape": (
            "permanent" if (np.isfinite(pooled_rev) and pooled_rev <= REV_PERM)
            else "transient" if (np.isfinite(pooled_rev) and pooled_rev >= REV_TRANS)
            else "mixed"),
    }
    if loads is None:
        block["per_counterparty"] = {"n_wallets": 0,
                                     "note": "too few eligible wallets at K_MIN"}
        return block

    split = _classify_split(loads["rev_frac"])
    real_disp = float(np.std(loads["rev_frac"][np.isfinite(loads["rev_frac"])],
                             ddof=0)) if loads["rev_frac"].size else float("nan")

    # placebo: random-wallet null on the between-wallet shape dispersion
    placebo = _placebo_shape_dispersion(
        taker_id, grid, K_MIN, np.random.default_rng(SEED + 11), N_PERM, real_disp)
    p_disp = placebo["p_one_sided"]

    # split-half persistence of the per-wallet reversion fraction
    persist = _split_half_persistence(
        taker_id, grid, K_HALF_MIN, np.random.default_rng(SEED + 23), N_PERM)

    # whale-drop on the pooled shape + split
    whales = _whale_drop_pooled(taker_id, grid, notional, N_DROP_WHALES)

    # `is not None` in both lines is a guard, not a change of rule. stats.py returns no
    # p at all for a cell with no usable draw or a non-finite observed statistic, which
    # is the honest answer for a cell that was never tested and reads as "not beaten"
    # here, exactly as a large p did. Neither line could reach that case before.
    placebo_beats = bool(p_disp is not None and np.isfinite(p_disp) and p_disp <= 0.05)
    persist_beats = bool(persist is not None
                         and persist["permutation_p_two_sided"] is not None
                         and persist["permutation_p_two_sided"] <= 0.05
                         and np.isfinite(persist["rank_corr_revA_vs_revB"])
                         and persist["rank_corr_revA_vs_revB"] > 0)

    block["per_counterparty"] = {
        "k_min": K_MIN,
        "n_wallets": loads["n_wallets"],
        "split": split,
        "between_wallet_reversion_dispersion": real_disp,
        # The block the placebo returns, with the verdict and the budget's floor added
        # beside it. The keys it already carried keep their names and their values.
        "placebo_random_wallet": dict(
            placebo, p_floor=P_FLOOR, real_dispersion_beats_placebo=placebo_beats),
        "split_half_persistence": persist if persist is not None else {
            "note": "too few wallets with both halves >= K_half"},
        "persistence_beats_null": persist_beats,
        "whale_drop_top5": whales,
        "shape_is_a_counterparty_trait": bool(placebo_beats or persist_beats),
    }
    return block


# ==================== heavy data build (re-parse + re-mark) ====================
def build_grids():
    """Re-parse Dec 4-13 BTC+ETH, re-mark at the full grid, row-aligned to npz.

    Returns: taker_id (int32), coin (int8), notional (float64), grid (n,H float64).
    The integer taker_id is rebuilt with the SAME first-seen scheme as
    quickwin_markouts.npz so the codes line up with maker/taker maps.
    """
    _apply_env_overrides()
    print(f"[probeG] days={bqm.DAYS} coins={bqm.COINS} grid={HORIZONS_S}s seed={SEED}")
    mid_series = load_mid_series(bqm.COINS)

    col_addr, col_coin, col_notional = [], [], []
    grid_rows = []
    resolved, issues = [], []

    for day in bqm.DAYS:
        per_coin, _ = bqm.parse_day(day)
        if per_coin is None:
            issues.append(f"day {day} missing on S3")
            print(f"[probeG] day {day} MISSING on S3 - skipped")
            continue
        resolved.append(day)
        for coin in bqm.COINS:
            d = per_coin[coin]
            n_trades = int(d["taker_ts"].size)
            if n_trades == 0 or d["print_ts"].size == 0:
                issues.append(f"{coin} {day}: empty - skipped")
                continue
            t_ms_fill = (d["taker_ts"] // 1_000_000).astype(np.int64)  # ns -> ms
            taker_side = np.asarray(d["taker_side"], dtype=np.int8)
            S = mid_series.get(coin, {"t_ms": np.empty(0, np.int64),
                                      "mid": np.empty(0)})
            g = mark_grid(t_ms_fill, taker_side, S)
            notional = d["taker_size"] * d["taker_px"]

            col_addr.extend(d["taker_addr"].tolist())
            col_coin.extend([COIN_CODE[coin]] * n_trades)
            col_notional.extend(notional.tolist())
            grid_rows.append(g)
            full_frac = float(np.mean(np.all(np.isfinite(g), axis=1)))
            print(f"[probeG] SLICE {coin} {day}: trades={n_trades:,} "
                  f"full-curve={full_frac*100:.1f}%")

    if not grid_rows:
        raise SystemExit("[probeG] no slices parsed - nothing to analyse")

    grid = np.vstack(grid_rows)
    coin_arr = np.asarray(col_coin, dtype=np.int8)
    notional_arr = np.asarray(col_notional, dtype=np.float64)

    # first-seen integer taker_id (matches quickwin_markouts.npz code space)
    wallet_to_code = {}
    taker_id = np.empty(len(col_addr), dtype=np.int32)
    for i, w in enumerate(col_addr):
        code = wallet_to_code.get(w)
        if code is None:
            code = len(wallet_to_code)
            wallet_to_code[w] = code
        taker_id[i] = code

    return taker_id, coin_arr, notional_arr, grid, resolved, issues


# ==================== main ====================
def main():
    t0 = artifact.start_clock()
    rng = np.random.default_rng(SEED)
    taker_id, coin, notional, grid, resolved, issues = build_grids()

    results = {
        "_meta": {
            "object": ("Probe G - transient vs permanent book-mid markout over a "
                       "fuller horizon grid + per-counterparty decay-curve shape"),
            "reference_price": ("BOOK MID (mid_series_{BTC,ETH}.npz); information "
                                "lens. Level inflated ~4x by own-spread-crossing -> "
                                "shape/ranks only, never the level. HL oracle/mark "
                                "never used (circular)."),
            "horizons_s": list(HORIZONS_S),
            "markout_sign": "positive = taker profited = maker adverse-selected",
            "no_lookahead_join": ("entry=searchsorted right-1 (last at-or-before); "
                                  "horizon=searchsorted left (first at-or-after); "
                                  f"per-leg gap tolerance {GAP_MAX_MS} ms"),
            "shape_rule": {
                "signed_reversion_fraction": "(m(h*)-m(300s))/m(h*), h*=argmax|m|",
                "permanent_if_<=": REV_PERM, "transient_if_>=": REV_TRANS,
                "reading": "~0 permanent/information; ->1 transient/speed edge; "
                           ">1 over-reverts (sign reversal)",
            },
            "k_min": K_MIN, "k_half_min": K_HALF_MIN, "seed": SEED,
            "n_perm": N_PERM, "p_floor": P_FLOOR, "n_drop_whales": N_DROP_WHALES,
            "kill_criterion": (
                "KILL if (a) the per-counterparty shape split is MAJORITY "
                "TRANSIENT (transient_share > permanent_share) in BOTH BTC and "
                "ETH (speed edge, not information) OR (b) split-half persistence "
                "p>0.05 AND placebo p>0.05 (no per-counterparty shape structure). "
                "cond_a reads the sign-correct per-wallet split, NOT the signed "
                "pooled mean (which can revert toward 0 by cancellation of "
                "heterogeneous-direction permanent wallets; kept as a diagnostic "
                "only)."),
            "days_resolved": resolved, "issues": issues,
            "n_rows_total": int(taker_id.size),
        }
    }

    # per coin
    for code, name in COIN_LABEL.items():
        sel = coin == code
        if not np.any(sel):
            results[name] = {"note": "no rows for this coin"}
            continue
        results[name] = analyse_slice(
            taker_id[sel], grid[sel], notional[sel], rng)

    # pooled headline
    results["pooled"] = analyse_slice(taker_id, grid, notional, rng)

    # evaluate the kill criterion on the pooled per-coin curves
    results["_meta"]["kill_verdict"] = _kill_verdict(results)

    # The window is the days that RESOLVED, not the days that were asked for. This probe
    # parses the raw tape day by day and skips a day that is not on the bucket, recording
    # it in `issues`; the two lists differ whenever a day is missing, and a smoke slice
    # run under CAP_DAYS narrows the request to one day without changing anything else
    # in the file. A scope naming the requested days would let a ten-day claim be read
    # off a one-day run, which is the failure this project has already paid for once.
    coins_scored = [name for code, name in COIN_LABEL.items()
                    if isinstance(results.get(name), dict)
                    and "note" not in results[name]]
    artifact.write(
        os.path.basename(OUT_NAME), results,
        script=__file__,
        # The raw hourly tape is named as an input alongside the local mid series, in
        # the same s3:// form build_quickwin_markouts.py records it in. It is not a
        # local file and is recorded with present=false: the parser deletes each day's
        # hourly directory as soon as it has parsed it, because the system disk cannot
        # hold them. Only the days that RESOLVED are listed, so the input record and the
        # window in the scope name the same set of days.
        inputs=[MID_PATH[c] for c in sorted(MID_PATH)]
        + [f"s3://{bqm.S3_BUCKET}/node_fills_by_block/hourly/{d}/" for d in resolved],
        scope={
            "population": (f"{int(taker_id.size):,} book-mid fills carrying a full "
                           f"curve join at every horizon of the grid; a wallet enters "
                           f"the shape split at {K_MIN} full-curve fills and the "
                           f"split-half persistence at {K_HALF_MIN} in EACH half. The "
                           f"placebo budget is {N_PERM} draws, so the smallest p this "
                           f"probe can express is {P_FLOOR:.6f}"),
            "window": (f"{len(resolved)} days resolved on the raw tape: {resolved}"
                       + (f"; {len(issues)} day(s) did not resolve and are recorded "
                          f"under _meta.issues: {issues}" if issues else
                          "; every requested day resolved")),
            "coins": coins_scored or f"n/a: no coin produced a slice, issues {issues}",
        },
        # The fingerprint block holds ONE horizon field and this probe runs a grid of
        # five, so the field is given the tail rung the reversion fraction is measured
        # against, {HORIZONS_S[-1]} s. That is a real rung of this run and it is not the
        # headline, so is_headline_horizon reads false, which is the truth about this
        # probe. The grid itself is recorded in the payload under _meta.horizons_s.
        settings={"h": int(HORIZONS_S[-1]), "lens": "mid", "master_seed": SEED,
                  "n_perm": N_PERM, "rank_floor_fills": K_MIN},
        started=t0, out_dir=os.path.dirname(OUT_NAME))
    _print_summary(results)


def _kill_verdict(results):
    """Evaluate the pre-registered kill criterion from the assembled results.

    cond_a (the transience kill) is read on the SIGN-CORRECT per-counterparty
    split (each wallet's reversion fraction is computed on its OWN peak-oriented
    curve), NOT on the signed notional-weighted pooled mean. The signed pooled
    mean can revert toward 0 at 300s purely by cancellation of heterogeneous-
    direction PERMANENT wallets (half drift price up, half down, each permanent
    in its own direction) -- that is not transience. The signed-pooled reversion
    is therefore kept only as a reported diagnostic, never as a kill trigger.
    This re-operationalizes the pre-registered intent ("per-counterparty impact
    is transient/speed-edge -> kill") on the correct sign-safe object.
    """
    def _agg_signed_reverts(blk):
        c = np.asarray(blk.get("pooled_curve_vw_bps", []), dtype=np.float64)
        if c.size != len(HORIZONS_S) or not np.all(np.isfinite(c)):
            return None
        peak = c[int(np.argmax(np.abs(c)))]
        if abs(peak) < 1e-9:
            return None
        return bool(abs(c[-1]) < 0.5 * abs(peak))

    def _wallets_majority_transient(blk):
        sp = blk.get("per_counterparty", {}).get("split", {})
        if not sp or sp.get("n", 0) < 1:
            return None
        return bool(sp.get("transient_share", 0.0) > sp.get("permanent_share", 0.0))

    # cond_a: sign-correct transience (the kill object)
    btc_tr = _wallets_majority_transient(results.get("BTC", {}))
    eth_tr = _wallets_majority_transient(results.get("ETH", {}))
    cond_a = bool(btc_tr) and bool(eth_tr)

    # diagnostic only: signed aggregate impact reversion (sign-cancellation-prone)
    btc_agg_rev = _agg_signed_reverts(results.get("BTC", {}))
    eth_agg_rev = _agg_signed_reverts(results.get("ETH", {}))

    pc = results.get("pooled", {}).get("per_counterparty", {})
    persist_ok = bool(pc.get("persistence_beats_null"))
    placebo_ok = bool(pc.get("placebo_random_wallet", {})
                      .get("real_dispersion_beats_placebo"))
    cond_b = (not persist_ok) and (not placebo_ok)

    killed = cond_a or cond_b
    return {
        "condition_a_wallets_majority_transient_both_coins": cond_a,
        "btc_wallets_majority_transient": btc_tr,
        "eth_wallets_majority_transient": eth_tr,
        "condition_b_no_shape_structure": cond_b,
        "persistence_beats_null": persist_ok,
        "placebo_beats": placebo_ok,
        "KILLED": killed,
        "reading": ("transient speed edge not information (per-counterparty split)"
                    if cond_a else
                    "no per-counterparty shape structure" if cond_b else
                    "survives - permanent/private-information reading holds"),
        "diagnostic_signed_aggregate_impact_reverts": {
            "btc": btc_agg_rev, "eth": eth_agg_rev,
            "note": ("signed notional-weighted pooled mean reverting toward 0 at "
                     "300s can be cancellation of heterogeneous-direction "
                     "permanent wallets; NOT a kill trigger -- cond_a uses the "
                     "sign-correct per-counterparty split."),
        },
    }


# -------------------- printed summary --------------------
def _fmt(x, nd=4):
    return f"{x:.{nd}f}" if isinstance(x, float) and np.isfinite(x) else "n/a"


def _print_summary(results):
    m = results["_meta"]
    print("=" * 92)
    print("PROBE G - transient vs permanent book-mid markout + decay-curve shape")
    print("=" * 92)
    print(f"  reference = BOOK MID (shape/ranks only; level inflated ~4x)")
    print(f"  grid (s)  = {list(HORIZONS_S)}")
    print(f"  rows={m['n_rows_total']:,}  seed={m['seed']}  perm={m['n_perm']} "
          f"(p-floor={m['p_floor']:.4f})  K_MIN={m['k_min']}")
    print("-" * 92)
    curve_col = f"pooled curve (vw bps, {HORIZONS_S[0]}..{HORIZONS_S[-1]}s)"
    hdr = (f"  {'slice':<7} {'n_wal':>6} {curve_col:<46} "
           f"{'revFrac':>8} {'shape':>10}")
    print(hdr)
    print("-" * len(hdr))
    for key in ("BTC", "ETH", "pooled"):
        blk = results.get(key, {})
        if not isinstance(blk, dict) or "pooled_curve_vw_bps" not in blk:
            print(f"  {key:<7}  (no data)")
            continue
        cur = "[" + ", ".join(_fmt(v, 2) for v in blk["pooled_curve_vw_bps"]) + "]"
        pc = blk.get("per_counterparty", {})
        nw = pc.get("n_wallets", 0)
        print(f"  {key:<7} {nw:>6} {cur:<46} "
              f"{_fmt(blk.get('pooled_reversion_fraction'), 3):>8} "
              f"{blk.get('pooled_shape', 'n/a'):>10}")
    print("-" * 92)
    print("  per-counterparty SHAPE split (permanent / transient / mixed share) + falsifiers")
    for key in ("BTC", "ETH", "pooled"):
        pc = results.get(key, {}).get("per_counterparty", {})
        sp = pc.get("split", {})
        if not sp or sp.get("n", 0) == 0:
            print(f"  {key:<7}  (no eligible wallets)")
            continue
        pers = pc.get("split_half_persistence", {})
        plac = pc.get("placebo_random_wallet", {})
        print(f"  {key:<7} perm={_fmt(sp.get('permanent_share'),2)} "
              f"trans={_fmt(sp.get('transient_share'),2)} "
              f"mixed={_fmt(sp.get('mixed_share'),2)} | "
              f"persist rho={_fmt(pers.get('rank_corr_revA_vs_revB'),3)} "
              f"p={_fmt(pers.get('permutation_p_two_sided'),4)} | "
              f"placebo p={_fmt(plac.get('p_one_sided'),4)} | "
              f"trait={pc.get('shape_is_a_counterparty_trait')}")
    print("-" * 92)
    kv = m.get("kill_verdict", {})
    print(f"  KILL VERDICT: KILLED={kv.get('KILLED')}  -> {kv.get('reading')}")
    # These three keys are the ones _kill_verdict actually writes. The line used to ask
    # for condition_a_pooled_curve_reverts_both_coins, btc_reverts and eth_reverts,
    # which are the names the kill criterion carried BEFORE it was re-operationalised
    # onto the sign-correct per-counterparty split, so the summary printed None three
    # times and read as "the criterion was not evaluated" on a run that evaluated it.
    print(f"    cond_a (wallets majority transient both coins)="
          f"{kv.get('condition_a_wallets_majority_transient_both_coins')} "
          f"(BTC {kv.get('btc_wallets_majority_transient')}, "
          f"ETH {kv.get('eth_wallets_majority_transient')})")
    print(f"    cond_b (no shape structure)={kv.get('condition_b_no_shape_structure')} "
          f"(persist={kv.get('persistence_beats_null')}, placebo={kv.get('placebo_beats')})")
    print("=" * 92)
    print(f"  results -> {os.path.basename(OUT_NAME)}")


if __name__ == "__main__":
    main()
