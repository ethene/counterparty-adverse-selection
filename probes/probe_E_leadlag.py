"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-22
References: [Hyperliquid L4 (Zenodo 18184441, Albers et al. 2026); node_fills_by_block]

PROBE E - cross-venue price discovery: Hyperliquid (perp DEX) vs Binance USD-M
futures (the dominant CEX), BTC and ETH, December 2025 core. Who moves first?

Three complementary estimators, each on a venue PAIR of price series:
  (1) Hasbrouck (1995) information share  - VECM/VMA on a common time grid;
      bounds from Cholesky ordering both ways (HL-first and Binance-first).
  (2) Gonzalo-Granger (1995) component share - permanent-component weights from
      the same VECM (orientation-free, complements Hasbrouck's bounds).
  (3) Hayashi-Yoshida (2005) cross-correlation on the RAW asynchronous ticks
      (no resampling) - lead-lag at the lag that maximises |HY corr|.
      + = HL leads Binance, - = Binance leads HL.

REFERENCE-PRICE PRE-COMMITMENT (HARD): we use TRADE prices and BOOK mids ONLY.
  - HL information lens   = book mid  (mid_series_{COIN}.npz, true best-bid/ask mid).
  - HL execution lens     = trade print (last fill px, built from node_fills if the
                            optional hl_print_series_{COIN}.npz is present).
  - Binance execution lens= aggTrades price (transact_time, price, is_buyer_maker).
  - Binance book lens     = bookDepth band-1 mid (COARSE: Binance futures public
                            bookDepth has NO L1 best-bid/ask; only %-band VWAP depth
                            at +/-1..5% of mid. The band-1 (+/-1%) bid/ask VWAP px
                            average is a ~30-60s, ~0.4% proxy -> SECONDARY only).
  We NEVER use the HL mark/oracle (it is a stake-weighted median of CEX spot mids
  => mechanically lags into CEX-leads => would manufacture the result). Same for
  any Binance "mark"/index. Trade + true-book only.

PRE-REGISTERED kill-criterion (Hasbrouck, trade-vs-trade, 1s grid, Dec, BTC):
  H0 = no venue leads (IS midpoint ~ 0.5 +/- 0.10 covers 0.5 AND the HY peak lag
       is at 0 +/- one grid step). If both estimators say ~symmetric and the
       randomized-lag placebo is NOT beaten, Probe E returns NO LEAD-LAG SIGNAL
       (still a clean reportable null; the main analysis does not hinge on it).
  A directional claim requires: IS bound interval excludes 0.5 in the SAME
  direction on BOTH coins AND HY peak lag is non-zero in that direction AND it
  beats the randomized-lag placebo (|HY peak| > 95th pct of shuffled-lag |corr|).

CONTROLS (mandatory): placebo = randomized lag (circular block shuffle of one
  series' tick times) -> HY/IS must collapse to no-signal. Per-asset AND
  per-regime reporting (calm vs volatile day buckets). Oct-10 cascade window is
  EXCLUDED by construction (Dec core); if Oct days are passed they are dropped.

Heavy numpy/IO (parses multi-GB Binance aggTrades). Run in BACKGROUND.
Read-only on data; writes probes/probe_E_leadlag_results.json + a summary print.
"""
import csv
import glob
import io
import os
import sys
import zipfile

import numpy as np

# Resolved from this file's own location, not from the working directory, so the
# import works wherever the probe is launched from.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import artifact  # noqa: E402
import settings as H  # noqa: E402
import stats  # noqa: E402

# ----------------------------------------------------------------------------- paths
# Every path is anchored on this file, so the probe reads and writes the same things
# whichever directory it is launched from. The three constants used to be strings
# relative to the repository root, which meant the run only found its inputs when it
# started there and silently reported "no data" from anywhere else.
PROBES = os.path.dirname(os.path.abspath(__file__))
CODE_DIR = os.path.dirname(PROBES)
BINANCE_RAW = os.path.normpath(
    os.path.join(os.path.dirname(CODE_DIR), "02_data", "raw", "binance"))
OUT_JSON = os.path.join(PROBES, "probe_E_leadlag_results.json")

# The coins are the ones the two-coin December panel carries, read from the declaration
# rather than typed, so this probe cannot end up comparing a coin set the panel does not
# hold. It used to read COINS = ["BTC", "ETH"]; that literal equals what the declaration
# returns for this artifact, so binding it moves no number.
COINS = [H.coin_labels("quickwin")[c] for c in sorted(H.coin_labels("quickwin"))]

# Binance's ticker for each coin. This stays local on purpose: it is a property of the
# other venue, not a setting of this study, and nothing else in the tree needs it.
SYMBOL = {"BTC": "BTCUSDT", "ETH": "ETHUSDT"}

# Dec core window, UTC days (Oct-10 cascade NOT in this set -> excluded by design).
DEFAULT_DAYS = [f"2025-12-{d:02d}" for d in range(4, 14)]  # 2025-12-04 .. 2025-12-13
OCT10_DAYS = {"2025-10-10", "2025-10-11"}  # belt-and-braces guard if Oct is passed

# The generator this file threads through every pair and every placebo draw is opened
# on this seed. It is read from the declaration, which holds the 690 the published run
# drew under, and reading it is not adopting settings.MASTER_SEED: that is a different
# declaration and this file still overrides it, stated in the fingerprint.
SEED = H.seed_for("probe_E_leadlag")
GRID_S = 1.0              # common-grid sampling for VECM (Hasbrouck/GG): 1 second
HY_MAX_LAG_S = 5.0        # Hayashi-Yoshida lead-lag scan range, +/- seconds
HY_STEP_S = 0.25          # HY lag step
# Randomized-lag placebo draws, read from the declaration under this placebo's own
# purpose name, which holds the 50 the published run used (it was 200 before; a
# Hayashi-Yoshida scan over raw ticks is what each draw costs). The declaration records
# beside it that the floor 1/51 is what this budget can express and that the stated
# criterion here is whether the placebo distribution is beaten, not a corrected p.
N_PLACEBO = H.perm_draws("leadlag_randomised_lag_placebo")
HY_MIN_GAP_MS = 250       # min-gap pre-thinning of raw ticks for HY (sub-HY_STEP_S, keeps async)
MAX_HY_TICKS = 1_000_000  # hard cap on HY ticks per series (uniform-stride if exceeded)
VECM_LAGS = 5             # VAR lags in the VECM (in grid steps)
MS = 1000


def _env_list(name, default):
    raw = os.environ.get(name)
    if not raw:
        return default
    return [tok.strip() for tok in raw.split(",") if tok.strip()]


# ----------------------------------------------------------------------------- loaders
def load_hl_mid(coin):
    """HL book mid series (true best-bid/ask mid). Returns (t_ms int64, px float64)."""
    p = os.path.join(CODE_DIR, f"mid_series_{coin}.npz")
    if not os.path.exists(p):
        return None
    d = np.load(p)
    t = d["t_ms"].astype(np.int64)
    px = d["mid"].astype(np.float64)
    order = np.argsort(t, kind="stable")
    return t[order], px[order]


def load_hl_print(coin):
    """OPTIONAL HL trade-print series, if a helper has built it from node_fills.
    Expected npz keys: t_ms (int64 epoch-ms), px (float64 last trade price).
    Returns (t_ms, px) or None. The main loop builds this separately (heavy S3)."""
    p = os.path.join(CODE_DIR, f"hl_print_series_{coin}.npz")
    if not os.path.exists(p):
        return None
    d = np.load(p)
    t = d["t_ms"].astype(np.int64)
    px = d["px"].astype(np.float64)
    order = np.argsort(t, kind="stable")
    return t[order], px[order]


def _iter_zip_csv(path):
    """Yield decoded CSV rows from a (possibly zipped) Binance file. Handles the
    monthly zip-of-csv and the daily csv-or-zip layouts."""
    if path.endswith(".zip"):
        with zipfile.ZipFile(path) as zf:
            name = [n for n in zf.namelist() if n.endswith(".csv")][0]
            with zf.open(name) as fh:
                for row in csv.reader(io.TextIOWrapper(fh, "utf-8")):
                    yield row
    else:
        with open(path, newline="") as fh:
            for row in csv.reader(fh):
                yield row


def _day_filter_ms(days):
    """UTC [start, end) epoch-ms bounds covering the requested day strings."""
    import datetime as dt

    bounds = []
    for ds in days:
        if ds in OCT10_DAYS:
            continue
        y, m, d = (int(x) for x in ds.split("-"))
        s = dt.datetime(y, m, d, tzinfo=dt.timezone.utc)
        e = s + dt.timedelta(days=1)
        bounds.append((int(s.timestamp() * MS), int(e.timestamp() * MS)))
    return bounds


def load_binance_trades(coin, days):
    """Binance USD-M aggTrades -> (t_ms int64, px float64), within the day window.
    Reads monthly zip(s) under raw/binance/aggTrades/, filtered to `days`."""
    sym = SYMBOL[coin]
    pat1 = f"{BINANCE_RAW}/aggTrades/{sym}-aggTrades-*.zip"
    pat2 = f"{BINANCE_RAW}/aggTrades/{sym}-aggTrades-*.csv"
    files = sorted(glob.glob(pat1)) + sorted(glob.glob(pat2))
    if not files:
        return None
    bounds = _day_filter_ms(days)
    if not bounds:
        return None
    lo = min(b[0] for b in bounds)
    hi = max(b[1] for b in bounds)
    keep = np.zeros(0, dtype=bool)  # placeholder
    t_all, p_all = [], []
    for f in files:
        ts, ps = [], []
        first = True
        for row in _iter_zip_csv(f):
            if first:
                first = False
                # header row present iff col 0 is non-numeric
                if not row or not row[0].lstrip("-").isdigit():
                    continue
            # cols: agg_trade_id, price, quantity, first_id, last_id, transact_time, is_buyer_maker
            try:
                tt = int(row[5])
                px = float(row[1])
            except (ValueError, IndexError):
                continue
            if tt < lo or tt >= hi:
                continue
            ts.append(tt)
            ps.append(px)
        if ts:
            t_all.append(np.asarray(ts, dtype=np.int64))
            p_all.append(np.asarray(ps, dtype=np.float64))
    if not t_all:
        return None
    t = np.concatenate(t_all)
    p = np.concatenate(p_all)
    order = np.argsort(t, kind="stable")
    t, p = t[order], p[order]
    # keep only rows inside ANY requested day (handles non-contiguous days)
    m = np.zeros(t.size, dtype=bool)
    for (s, e) in bounds:
        m |= (t >= s) & (t < e)
    return t[m], p[m]


def load_binance_bookdepth_mid(coin, days):
    """Binance futures bookDepth band-1 mid (COARSE proxy). For each snapshot,
    reconstruct the +/-1% bid and ask VWAP price as notional/depth, then mid =
    average of the band(-1) and band(+1) prices. ~30-60s cadence, ~0.4% off true
    mid -> SECONDARY robustness reference only. Returns (t_ms int64, px) or None.
    bookDepth cols: timestamp(str 'YYYY-MM-DD HH:MM:SS'), percentage, depth, notional."""
    import datetime as dt

    sym = SYMBOL[coin]
    files = []
    for ds in days:
        if ds in OCT10_DAYS:
            continue
        files += sorted(glob.glob(f"{BINANCE_RAW}/bookDepth/{sym}-bookDepth-{ds}.zip"))
        files += sorted(glob.glob(f"{BINANCE_RAW}/bookDepth/{sym}-bookDepth-{ds}.csv"))
    if not files:
        return None
    # per-timestamp accumulate band-1 bid/ask reconstructed px
    snap_bid = {}  # ts_ms -> notional/depth at pct -1
    snap_ask = {}  # ts_ms -> notional/depth at pct +1
    for f in files:
        first = True
        for row in _iter_zip_csv(f):
            if first:
                first = False
                if row and row[0].strip().lower() == "timestamp":
                    continue
            try:
                pct = int(float(row[1]))
                if pct not in (-1, 1):
                    continue
                depth = float(row[2])
                notional = float(row[3])
                if depth <= 0:
                    continue
                ts = dt.datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S").replace(
                    tzinfo=dt.timezone.utc
                )
                ts_ms = int(ts.timestamp() * MS)
            except (ValueError, IndexError):
                continue
            px = notional / depth
            if pct == -1:
                snap_bid[ts_ms] = px
            else:
                snap_ask[ts_ms] = px
    common = sorted(set(snap_bid) & set(snap_ask))
    if not common:
        return None
    t = np.asarray(common, dtype=np.int64)
    px = np.asarray([0.5 * (snap_bid[k] + snap_ask[k]) for k in common], dtype=np.float64)
    return t, px


# ----------------------------------------------------------------------------- grid + log px
def to_log_grid(t_ms, px, t0, t1, grid_s):
    """Sample log-price onto a uniform grid via LAST-observation-carried-forward
    (no lookahead: each grid point uses the last tick at-or-before it).
    Returns (grid_t_ms, log_px) with NaN where no prior tick exists yet."""
    step = int(grid_s * MS)
    grid = np.arange(t0, t1 + step, step, dtype=np.int64)
    # last-at-or-before: searchsorted right minus 1 (the unit-tested convention)
    idx = np.searchsorted(t_ms, grid, side="right") - 1
    out = np.full(grid.size, np.nan, dtype=np.float64)
    ok = idx >= 0
    out[ok] = np.log(px[idx[ok]])
    return grid, out


# ----------------------------------------------------------------------------- VECM core
def fit_vecm(p1, p2, lags):
    """Single-cointegration VECM for two log-price series sharing one stochastic
    trend. Returns dict with Hasbrouck IS bounds, Gonzalo-Granger shares, and the
    reduced-form residual covariance. p1, p2 = aligned log-price grids (finite)."""
    n = p1.size
    if n < 50 * lags:
        return None
    dy1 = np.diff(p1)
    dy2 = np.diff(p2)
    # error-correction term: the spread (cointegrating vector ~ [1,-1] for one
    # asset on two venues; estimate beta by regressing p1 on p2 to be safe).
    A = np.vstack([p2, np.ones_like(p2)]).T
    coef, *_ = np.linalg.lstsq(A, p1, rcond=None)
    beta, c = coef[0], coef[1]
    ect = (p1 - beta * p2 - c)  # stationary spread, level series
    # build regressor matrix: lagged dy1, dy2 + lagged ect
    L = lags
    T = n - 1 - L
    if T < 50:
        return None
    Y1 = dy1[L:]
    Y2 = dy2[L:]
    # ect_{t-1} aligned to dy_t: dy index t (0..n-2) maps to level index t+1, so
    # ect_{t-1} is the level ect at index t -> ect[L : n-1] over the trimmed range.
    ect_lag = ect[L:n - 1]
    cols = [ect_lag]
    for k in range(1, L + 1):
        cols.append(dy1[L - k:n - 1 - k])
        cols.append(dy2[L - k:n - 1 - k])
    cols.append(np.ones(T))
    X = np.vstack([c[:T] for c in cols]).T
    # equation 1: dy1 ~ X ; equation 2: dy2 ~ X
    b1, *_ = np.linalg.lstsq(X, Y1[:T], rcond=None)
    b2, *_ = np.linalg.lstsq(X, Y2[:T], rcond=None)
    e1 = Y1[:T] - X @ b1
    e2 = Y2[:T] - X @ b2
    Omega = np.cov(np.vstack([e1, e2]))
    # error-correction (adjustment) speeds = coefficient on ect_lag (col 0)
    a1, a2 = b1[0], b2[0]
    # ----- Gonzalo-Granger component share -----
    # orthogonal-to-alpha row gives the common-factor weights. alpha = [a1, a2]'.
    # GG weights gamma proportional to [a2, -a1] normalised (alpha_perp).
    gg_raw = np.array([a2, -a1], dtype=np.float64)
    denom = gg_raw.sum()
    if abs(denom) < 1e-12:
        gg1 = gg2 = np.nan
    else:
        gg = gg_raw / denom
        gg1, gg2 = float(gg[0]), float(gg[1])
    # ----- Hasbrouck information share (bounds via Cholesky both orders) -----
    # common-factor row psi proportional to alpha_perp = [a2, -a1] (same direction).
    psi = np.array([a2, -a1], dtype=np.float64)
    is_bounds = hasbrouck_is(psi, Omega)
    return {
        "n_obs": int(T),
        "beta": round(float(beta), 6),
        "alpha_ect": [round(float(a1), 6), round(float(a2), 6)],
        "omega": [[round(float(Omega[0, 0]), 12), round(float(Omega[0, 1]), 12)],
                  [round(float(Omega[1, 0]), 12), round(float(Omega[1, 1]), 12)]],
        "gg_share_v1": round(gg1, 4) if np.isfinite(gg1) else None,
        "gg_share_v2": round(gg2, 4) if np.isfinite(gg2) else None,
        "is_v1_lower": is_bounds[0], "is_v1_upper": is_bounds[1],
        "is_v1_mid": round(0.5 * (is_bounds[0] + is_bounds[1]), 4),
    }


def hasbrouck_is(psi, Omega):
    """Hasbrouck information share of VENUE 1, lower/upper bound from the two
    Cholesky orderings of Omega. psi = common-factor row (length 2)."""
    def is_for_order(O):
        F = np.linalg.cholesky(O)  # lower-triangular
        pf = psi @ F
        num = pf[0] ** 2
        den = float(psi @ O @ psi)
        if den <= 0:
            return np.nan
        return num / den
    try:
        is_a = is_for_order(Omega)                      # venue1 ordered first
        O_sw = Omega[::-1, ::-1]
        psi_sw = psi[::-1]
        F2 = np.linalg.cholesky(O_sw)
        pf2 = psi_sw @ F2
        den = float(psi @ Omega @ psi)
        is_b = (pf2[1] ** 2) / den if den > 0 else np.nan  # venue1 ordered last
    except np.linalg.LinAlgError:
        return [None, None]
    lo = float(min(is_a, is_b))
    hi = float(max(is_a, is_b))
    return [round(lo, 4), round(hi, 4)]


# ----------------------------------------------------------------------------- Hayashi-Yoshida
def hy_corr_at_lag(t1, r1, t2, r2, lag_ms):
    """Vectorised Hayashi-Yoshida overlap covariance — the EXACT same estimator as
    the O(n) merge reference below, via searchsorted + prefix sums. Time intervals
    partition the line, so the series-2 intervals overlapping series-1 interval i
    form a CONTIGUOUS range [jlo, jhi]; the cross term is then
    r1[i] * (cumsum_r2[jhi+1] - cumsum_r2[jlo]). O(n log n), all numpy. Validated
    equal to hy_corr_at_lag_ref (the pure-Python merge)."""
    t1 = np.asarray(t1); t2 = np.asarray(t2)
    rr1 = np.asarray(r1, dtype=np.float64); rr2 = np.asarray(r2, dtype=np.float64)
    if rr1.size == 0 or rr2.size == 0:
        return np.nan
    s1 = t1[:-1].astype(np.float64); e1 = t1[1:].astype(np.float64)
    s2 = t2[:-1].astype(np.float64) + lag_ms; e2 = t2[1:].astype(np.float64) + lag_ms
    R2 = np.concatenate(([0.0], np.cumsum(rr2)))      # prefix sums, len n2+1
    jlo = np.searchsorted(e2, s1, side="right")       # first j with e2 > s1[i]
    jhi = np.searchsorted(s2, e1, side="left") - 1    # last  j with s2 < e1[i]
    valid = jlo <= jhi
    n2 = rr2.size
    seg = R2[np.clip(jhi + 1, 0, n2)] - R2[np.clip(jlo, 0, n2)]
    cross = float(np.sum(rr1[valid] * seg[valid]))
    v1 = float(np.dot(rr1, rr1)); v2 = float(np.dot(rr2, rr2))
    if v1 <= 0 or v2 <= 0:
        return np.nan
    return cross / np.sqrt(v1 * v2)


def hy_corr_at_lag_ref(t1, r1, t2, r2, lag_ms):
    """Hayashi-Yoshida cross-correlation of two return processes given as
    (interval-end times, returns), shifting series 2 by lag_ms. Sums products of
    returns whose (shifted) intervals OVERLAP. Returns the normalised correlation.
    Inputs: t1,t2 = tick times (interval [t_{i-1}, t_i]); r1,r2 = log returns."""
    # represent intervals by (start, end). returns r_i over (t[i-1], t[i]].
    s1 = t1[:-1].astype(np.float64); e1 = t1[1:].astype(np.float64)
    s2 = (t2[:-1] + lag_ms).astype(np.float64); e2 = (t2[1:] + lag_ms).astype(np.float64)
    rr1 = r1; rr2 = r2
    # overlap-sum via a merge (both interval lists sorted by start). O(n1+n2).
    i = j = 0
    n1, n2 = rr1.size, rr2.size
    cross = 0.0
    while i < n1 and j < n2:
        if e1[i] <= s2[j]:
            i += 1
        elif e2[j] <= s1[i]:
            j += 1
        else:
            cross += rr1[i] * rr2[j]
            # advance the interval that ends first
            if e1[i] < e2[j]:
                i += 1
            else:
                j += 1
    v1 = float(np.dot(rr1, rr1))
    v2 = float(np.dot(rr2, rr2))
    if v1 <= 0 or v2 <= 0:
        return np.nan
    return cross / np.sqrt(v1 * v2)


def hy_leadlag(t1, px1, t2, px2, max_lag_s, step_s):
    """Scan HY corr over lags; return (best_lag_s, best_corr, hl_leads_s, curve).
    series1 = HL, series2 = Binance. hy_corr_at_lag SHIFTS venue2 (Binance) FORWARD
    in time by +lag_ms (s2 = t2 + lag_ms). If Binance is the DELAYED copy of the
    common efficient price (i.e. HL moves first), the overlap correlation peaks at a
    NEGATIVE lag (Binance must be pulled BACKWARD to align with HL). So:
        raw best_lag_s < 0  <=>  HL leads.
    We therefore report hl_leads_s = -best_lag_s  (+ = HL leads, - = Binance leads),
    matching the docstring/grade() convention. (Verified: a planted Binance-lag of
    +2s recovers best_lag_s=-2.0 -> hl_leads_s=+2.0.) r computed from log px."""
    lr1 = np.diff(np.log(px1))
    lr2 = np.diff(np.log(px2))
    if lr1.size < 10 or lr2.size < 10:
        return None
    lags = np.arange(-max_lag_s, max_lag_s + step_s / 2, step_s)
    curve = []
    for lg in lags:
        c = hy_corr_at_lag(t1, lr1, t2, lr2, lg * MS)
        curve.append((float(lg), float(c) if np.isfinite(c) else None))
    valid = [(lg, c) for lg, c in curve if c is not None]
    if not valid:
        return None
    best = max(valid, key=lambda x: abs(x[1]))
    return {"best_lag_s": round(best[0], 3), "best_corr": round(best[1], 4),
            "hl_leads_s": round(-best[0], 3),
            "curve": [[lg, (round(c, 4) if c is not None else None)] for lg, c in curve]}


def hy_placebo(t1, px1, t2, px2, max_lag_s, step_s, rng, n_draws, cell=None):
    """Randomized-alignment placebo: rotate venue2's RETURN series against its own
    unchanged tick times, so every return keeps its value and its neighbours and only
    its position relative to venue1 is destroyed. The true peak |HY corr| must beat the
    placebo distribution to count as a lead-lag signal.

    WHAT THE NULL ARM MOVES, AND WHAT IT HOLDS STILL. This is written out because a
    placebo is only worth its p if the arms differ in exactly one thing, and the reader
    cannot see which thing from a p alone. One draw applies numpy.roll to venue2's log
    returns by an offset drawn uniformly from 1 to n-2. Everything else is held at the
    value the real arm used: venue1's times and returns, venue2's TIMES, the lag grid,
    the min-gap thinning and the tick cap that produced both series, and the
    normalisation by the two realised variances. So the two arms differ only in whether
    venue2's returns sit at the instants they actually occurred.

    WHY A ROTATION AND NOT A RESHUFFLE. A rotation preserves venue2's marginal
    distribution AND its own serial correlation exactly, both of which a free reshuffle
    would destroy; a null that also flattened venue2's autocorrelation would be easier
    to beat for a reason that has nothing to do with the two venues lining up, and the
    peak it produced would understate what chance can do. The cost of the rotation is
    one seam per draw, where the last return meets the first.

    THE NAME IN THE RECORDED BLOCK IS NOT A DESCRIPTION OF THIS ARM. stats.py labels
    every one of its counts "label permutation", which is the name of the family the
    counting procedure belongs to and not an account of what was permuted here. This
    docstring and the null_arm field below are the account; the recorded procedure name
    should not be read as one.

    `cell` only NAMES the test in the recorded procedure block; the draws come from
    the generator threaded in by the caller, so it seeds nothing and moves nothing.
    """
    real = hy_leadlag(t1, px1, t2, px2, max_lag_s, step_s)
    if real is None:
        return None
    peak = abs(real["best_corr"])
    lr1 = np.diff(np.log(px1))
    lr2 = np.diff(np.log(px2))
    null_peaks = []
    for _ in range(n_draws):
        shift = int(rng.integers(1, lr2.size - 1)) if lr2.size > 2 else 1
        lr2s = np.roll(lr2, shift)  # break timing, keep marginal distribution
        # recompute peak |corr| over the lag grid with shuffled returns
        lags = np.arange(-max_lag_s, max_lag_s + step_s / 2, step_s)
        best = 0.0
        for lg in lags:
            c = hy_corr_at_lag(t1, lr1, t2[: lr2s.size + 1], lr2s, lg * MS)
            if np.isfinite(c) and abs(c) > best:
                best = abs(c)
        null_peaks.append(best)
    null_peaks = np.asarray(null_peaks)
    # Counted by stats.py. The question is one-sided by construction: the statistic is
    # already an ABSOLUTE peak correlation, so "at least as extreme" means at least as
    # large, and there is no other side for it to be on. abs_tol=0.0 keeps the bare
    # `>=` this line has always used rather than the module's relative slack, which
    # would be a different number and is owed its own recompute. Every draw is a finite
    # peak by construction, so n_draws_dropped in the block below reads 0 and the
    # module's usable-count denominator is the n_draws this line divided by.
    perm = stats.permutation_p(peak, null_peaks, side="greater", abs_tol=0.0,
                               n_requested=n_draws, cell=cell)
    p = perm["p"]
    return {"real_peak_abs_corr": round(peak, 4),
            # What separates the two arms, in the file rather than in the docstring, so
            # a reader who never opens the script can see that they differ in one thing.
            "null_arm": (
                f"venue2's log-return series is rotated by numpy.roll through an offset "
                f"drawn uniformly from 1 to n-2, once per draw, {n_draws} draws. Held "
                f"identical to the real arm: venue1's times and returns, venue2's TICK "
                f"TIMES, the lag grid, the thinning and the tick cap that built both "
                f"series, and the normalisation by the two realised variances. A "
                f"rotation and not a reshuffle, so venue2 keeps its own marginal "
                f"distribution and its own serial correlation and loses only its "
                f"alignment with venue1. The procedure name recorded under "
                f"permutation.procedure is the family the counting belongs to, not an "
                f"account of what was moved here"),
            "placebo_p": round(p, 4),
            "placebo_95pct": round(float(np.percentile(null_peaks, 95)), 4),
            "beats_placebo": bool(p < 0.05),
            # The reported p is rounded to four places for reading, and 1/51 rounds to
            # 0.0196, which is close enough to the floor to be mistaken for a
            # measurement below it. So whether the p IS the floor is decided on the
            # unrounded value, by the predicate settings.py declares, and written down.
            "p_floor": perm["p_floor"],
            "p_is_floored": perm["p_is_floored"],
            "permutation": perm}


def _thin_min_gap(t, px, min_gap_ms, max_n):
    """Light min-gap pre-thinning of raw async ticks so the O(n) pure-Python HY
    overlap merge stays tractable over a 10-day window. Keeps the FIRST tick in
    each min_gap_ms time-bucket (vectorised via np.unique on t//gap), then a
    uniform-stride cap to max_n. This is a tractability approximation with an Epps
    trade-off, not a resample to a fixed grid.

    WHICH OF THE TWO LIMITS ACTUALLY SETS THE RESOLUTION, because the answer is not
    min_gap_ms and a sentence here used to say it was. min_gap_ms is 250 ms and
    HY_STEP_S is 0.25 s, so the min-gap is not below the lag step, it EQUALS it. And
    when the second limit binds, it is the one that decides: a series capped at max_n
    over a window of W seconds is left with a mean spacing of W / max_n, whatever
    min_gap_ms was. On the ten-day window that is 864 000 / 1 000 000 = 0.86 s per
    tick, three and a half times the lag step the peak is then read on. Whether the cap
    binds is not a property of this function but of the run, so both counts are written
    into the results file beside every pair -- n_hl_ticks_raw against n_hl_ticks_hy,
    and the same for the second venue -- and a reader who finds the second equal to
    max_n knows the stride, and not the min-gap, is what the lag was resolved at."""
    t = np.asarray(t); px = np.asarray(px)
    if t.size <= 2:
        return t, px
    buckets = ((t - t[0]) // max(1, int(min_gap_ms))).astype(np.int64)
    _, first = np.unique(buckets, return_index=True)
    idx = np.sort(first)
    if idx.size > max_n:
        idx = idx[np.linspace(0, idx.size - 1, max_n).astype(np.int64)]
    return t[idx], px[idx]


# ----------------------------------------------------------------------------- regime split
def split_regimes(t_ms, px, days):
    """Bucket the requested days into calm vs volatile by per-day realized vol of
    the HL mid (median split). Returns {day_str: 'calm'|'volatile'}."""
    import datetime as dt

    lab = {}
    rv = {}
    for ds in days:
        if ds in OCT10_DAYS:
            continue
        y, m, d = (int(x) for x in ds.split("-"))
        s = int(dt.datetime(y, m, d, tzinfo=dt.timezone.utc).timestamp() * MS)
        e = s + 86400 * MS
        msk = (t_ms >= s) & (t_ms < e)
        if msk.sum() > 10:
            lr = np.diff(np.log(px[msk]))
            rv[ds] = float(np.sqrt(np.sum(lr ** 2)))
    if not rv:
        return lab
    med = np.median(list(rv.values()))
    for ds, v in rv.items():
        lab[ds] = "volatile" if v >= med else "calm"
    return lab


# ----------------------------------------------------------------------------- per-coin run
def run_pair(coin, t_hl, px_hl, t_bn, px_bn, lens, days, rng, do_placebo=True):
    """Run all three estimators on one (HL, Binance) price-series pair."""
    if t_hl is None or t_bn is None:
        return {"status": "MISSING_SERIES", "lens": lens}
    t0 = max(int(t_hl.min()), int(t_bn.min()))
    t1 = min(int(t_hl.max()), int(t_bn.max()))
    if t1 - t0 < 3600 * MS:
        return {"status": "OVERLAP_TOO_SHORT", "lens": lens,
                "overlap_s": (t1 - t0) / MS}
    # VECM on a common 1s grid (LOCF both venues, drop leading NaNs)
    g, lp_hl = to_log_grid(t_hl, px_hl, t0, t1, GRID_S)
    _, lp_bn = to_log_grid(t_bn, px_bn, t0, t1, GRID_S)
    ok = np.isfinite(lp_hl) & np.isfinite(lp_bn)
    vecm = fit_vecm(lp_hl[ok], lp_bn[ok], VECM_LAGS) if ok.sum() > 500 else None

    # Hayashi-Yoshida on RAW async ticks within the overlap (no resampling)
    mh = (t_hl >= t0) & (t_hl <= t1)
    mb = (t_bn >= t0) & (t_bn <= t1)
    # min-gap pre-thin the raw async ticks for HY tractability (sub-HY_STEP_S gap
    # keeps the async character; bounds the O(n) pure-Python overlap merge).
    th_hl, ph_hl = _thin_min_gap(t_hl[mh], px_hl[mh], HY_MIN_GAP_MS, MAX_HY_TICKS)
    th_bn, ph_bn = _thin_min_gap(t_bn[mb], px_bn[mb], HY_MIN_GAP_MS, MAX_HY_TICKS)
    hy = hy_leadlag(th_hl, ph_hl, th_bn, ph_bn, HY_MAX_LAG_S, HY_STEP_S)
    plac = (hy_placebo(th_hl, ph_hl, th_bn, ph_bn, HY_MAX_LAG_S, HY_STEP_S, rng,
                       N_PLACEBO, cell=("hy_randomised_lag_placebo", coin, lens))
            if do_placebo
            else {"status": "skipped", "note": "placebo run only on the primary pair (speed)"})

    return {"status": "OK", "lens": lens,
            "overlap_hours": round((t1 - t0) / MS / 3600, 2),
            "n_hl_ticks_raw": int(mh.sum()), "n_bn_ticks_raw": int(mb.sum()),
            "n_hl_ticks_hy": int(th_hl.size), "n_bn_ticks_hy": int(th_bn.size),
            "hy_min_gap_ms": HY_MIN_GAP_MS, "hy_max_ticks": MAX_HY_TICKS,
            "vecm": vecm, "hayashi_yoshida": hy, "placebo": plac}


# The two lenses the per-coin verdict may be read off, in preference order: the
# trade-vs-trade pair is the kill-criterion lens and is used whenever the HL print
# series is on disk, the HL-book-mid pair otherwise. Named once, in one place, because
# the verdict and the family the verdict is corrected in have to be about the same
# pair; they used to be selected by two separate copies of this rule.
PRIMARY_PAIR_ORDER = ("HLprint_vs_BNtrade", "HLmid_vs_BNtrade")


def _primary_pair(pairs):
    """(name, block) of the pair one coin's verdict is read off."""
    for name in PRIMARY_PAIR_ORDER:
        pr = pairs.get(name)
        if isinstance(pr, dict) and pr.get("status") == "OK":
            return name, pr
    return PRIMARY_PAIR_ORDER[-1], pairs.get(PRIMARY_PAIR_ORDER[-1])


def placebo_family(by_coin, n_draws):
    """The family of placebo significances this probe asserts, with the room its draw
    budget leaves under the multiplicity correction that family implies.

    WHY THIS BLOCK IS IN THE ARTIFACT AND NOT IN A COMMENT. This probe asserts more
    than one significance -- one per coin -- so no single p of it can be read on its
    own. Benjamini-Hochberg compares the smallest p in a family against alpha divided
    by the family size, and settings.py declares that a budget's floor has to sit at
    PERM_FLOOR_MARGIN times below that bar, so that a p reported AT the floor is not
    decided by the last digit of the correction. This probe does not clear that
    requirement, and the honest place to say so is beside the p-values, in the file a
    reader opens, rather than in a note somewhere else.

    Every number here is computed from what the run actually produced: the family is
    counted from the pairs that returned a p, the floor from the budget, the threshold
    from the family size, and the two are divided. Nothing is asserted that a reader
    cannot recompute from the block.

    WHAT IS NOT DONE ABOUT IT, said out loud. The budget is not raised. One draw here
    is a Hayashi-Yoshida scan over the raw asynchronous ticks of both venues across the
    whole window, repeated over the entire lag grid, so the cost of this placebo is
    linear in the number of draws and it is the dominant cost of the probe. The
    shortfall is therefore carried as a declared debt with its size written down --
    min_draws_for_declared_margin says exactly how far short the budget is -- and not
    as a silent property of a number in a table.
    """
    members, outside, not_drawn = [], [], []
    for coin in sorted(by_coin):
        cd = by_coin[coin]
        pairs = cd.get("pairs") if isinstance(cd, dict) else None
        if not pairs:
            continue
        prim_name, _ = _primary_pair(pairs)
        for name, pr in pairs.items():
            plac = pr.get("placebo") if isinstance(pr, dict) else None
            if not isinstance(plac, dict) or plac.get("placebo_p") is None:
                not_drawn.append({
                    "coin": coin, "pair": name,
                    "reason": ((plac or {}).get("note") or (plac or {}).get("status")
                               or (pr or {}).get("status") or "no placebo block")})
                continue
            entry = {"coin": coin, "pair": name, "lens": pr.get("lens"),
                     "placebo_p": plac["placebo_p"],
                     "p_is_floored": bool(plac.get("p_is_floored"))}
            (members if name == prim_name else outside).append(entry)

    m = len(members)
    floor = H.p_floor(n_draws)
    required = H.PERM_FLOOR_MARGIN
    block = {
        "what_the_family_is": (
            "the per-coin placebo significances this probe asserts: one test per coin, "
            "taken on the pair the coin's verdict is read off, which is "
            + " then ".join(PRIMARY_PAIR_ORDER)
            + ". A placebo drawn on any other pair is reported under "
              "placebo_p_values_outside_the_family and is not corrected here, because "
              "no verdict is read off it"),
        "members": members,
        "family_size": m,
        "placebo_p_values_outside_the_family": outside,
        "pairs_with_no_placebo_drawn": not_drawn,
        "n_draws": int(n_draws),
        "n_draws_source": "settings.PERM_DRAWS_BY_PURPOSE"
                          "['leadlag_randomised_lag_placebo']",
        "p_floor": floor,
        "n_members_at_the_floor": sum(1 for x in members if x["p_is_floored"]),
        "alpha": H.FDR_ALPHA,
        "margin_required": required,
        "margin_required_source": "settings.PERM_FLOOR_MARGIN",
    }
    if m == 0:
        block.update({
            "rank1_threshold": None, "margin_achieved": None, "margin_met": None,
            "min_draws_for_declared_margin": None,
            "statement": "no placebo was drawn in this run, so this probe asserts no "
                         "significance and there is no family to correct in",
            "statement_short": "no placebo drawn, no family"})
        return block

    threshold = H.FDR_ALPHA / m
    achieved = threshold / floor
    met = bool(achieved >= required)
    need = H.min_perm_draws(family_size=m, alpha=H.FDR_ALPHA, margin=required,
                            quantum=1)
    block.update({
        "rank1_threshold": threshold,
        "margin_achieved": achieved,
        "margin_met": met,
        "min_draws_for_declared_margin": int(need),
        "statement": (
            f"{m} significance(s) are asserted, of which "
            f"{block['n_members_at_the_floor']} sit AT the p-value floor. With "
            f"{int(n_draws)} draws that floor is 1/{int(n_draws) + 1} = {floor:.4f}. "
            f"The rank-one bar this family has to clear is alpha/m = {H.FDR_ALPHA}/{m} "
            f"= {threshold:.4f}, so the floor sits {achieved:.3f} times below the bar "
            f"against the {required} that settings.PERM_FLOOR_MARGIN declares: "
            + ("the declared margin IS met" if met else
               f"THE DECLARED MARGIN IS NOT MET. A p at this floor clears the "
               f"correction, but by a distance the last digit of the correction can "
               f"decide, which is the position that constant exists to forbid. "
               f"{need} draws would satisfy it at this family size; the budget stays "
               f"at {int(n_draws)} because one draw is a Hayashi-Yoshida scan over the "
               f"raw ticks of both venues across the whole window, so this is a "
               f"declared debt with its price named and not an oversight")),
        "statement_short": (
            f"{m} asserted significance(s), {block['n_members_at_the_floor']} at the "
            f"floor {floor:.4f}; rank-one bar {threshold:.4f}; margin "
            f"{achieved:.3f} against a declared {required}, "
            + ("met" if met else f"NOT met ({need} draws would meet it)")),
    })
    return block


def main():
    t0 = artifact.start_clock()
    days = _env_list("CAP_DAYS_E", DEFAULT_DAYS)
    days = [d for d in days if d not in OCT10_DAYS]
    # One generator threaded through every pair and every placebo draw below, opened on
    # a seed that is NOT settings.MASTER_SEED. Its value is left alone: the placebo
    # distributions in this file's results are successive states of this stream, so
    # rebinding it would move every placebo p. Stated as an override in the artifact's
    # fingerprint.
    rng = np.random.default_rng(SEED)
    print(f"[probe_E] cross-venue lead-lag | coins={COINS} | days={days[0]}..{days[-1]} "
          f"({len(days)}d) | grid={GRID_S}s | HY +/-{HY_MAX_LAG_S}s")
    print("[probe_E] reference pre-commitment: HL book-mid + HL trade-print + "
          "Binance aggTrades + Binance bookDepth-band1-mid; NEVER mark/oracle.")

    out = {"window_days": days, "grid_s": GRID_S, "hy_max_lag_s": HY_MAX_LAG_S,
           "n_placebo": N_PLACEBO, "kill_criterion": (
               "Hasbrouck trade-vs-trade 1s Dec BTC: IS-mid in 0.5+/-0.10 AND "
               "HY peak lag in 0+/-1 step AND placebo NOT beaten -> NO LEAD-LAG."),
           "by_coin": {}}

    for coin in COINS:
        print(f"\n===== {coin} =====")
        hl_mid = load_hl_mid(coin)
        hl_prn = load_hl_print(coin)
        bn_trd = load_binance_trades(coin, days)
        bn_bd = load_binance_bookdepth_mid(coin, days)
        if hl_mid is None:
            print(f"  [warn] no HL mid_series for {coin} -> skip");
            out["by_coin"][coin] = {"status": "NO_HL_MID"}; continue
        if bn_trd is None:
            print(f"  [warn] no Binance aggTrades for {coin} under {BINANCE_RAW}/aggTrades/ "
                  f"-> run the data pull first.");
            out["by_coin"][coin] = {"status": "NO_BINANCE_TRADES"}; continue
        print(f"  HL mid {hl_mid[0].size:,} | HL print "
              f"{(hl_prn[0].size if hl_prn else 0):,} | "
              f"Binance trades {bn_trd[0].size:,} | "
              f"Binance bookDepth {(bn_bd[0].size if bn_bd else 0):,}")

        regimes = split_regimes(hl_mid[0], hl_mid[1], days)
        cres = {"regimes": regimes, "pairs": {}}

        # PRIMARY lens = trade-vs-trade (the kill-criterion pair). Needs HL print.
        if hl_prn is not None:
            cres["pairs"]["HLprint_vs_BNtrade"] = run_pair(
                coin, hl_prn[0], hl_prn[1], bn_trd[0], bn_trd[1],
                "trade-vs-trade", days, rng)
        else:
            cres["pairs"]["HLprint_vs_BNtrade"] = {
                "status": "NO_HL_PRINT_SERIES",
                "note": "build hl_print_series_{coin}.npz from node_fills to run "
                        "the trade-vs-trade kill-criterion lens."}
        # book-vs-trade: HL true book mid vs Binance trade (information lens, HL side clean)
        cres["pairs"]["HLmid_vs_BNtrade"] = run_pair(
            coin, hl_mid[0], hl_mid[1], bn_trd[0], bn_trd[1],
            "HLbookmid-vs-BNtrade", days, rng)
        # book-vs-book SECONDARY: HL mid vs Binance coarse bookDepth band-1 mid
        if bn_bd is not None:
            cres["pairs"]["HLmid_vs_BNbookdepth"] = run_pair(
                coin, hl_mid[0], hl_mid[1], bn_bd[0], bn_bd[1],
                "HLbookmid-vs-BNbookdepth(coarse)", days, rng, do_placebo=False)
        else:
            cres["pairs"]["HLmid_vs_BNbookdepth"] = {"status": "NO_BINANCE_BOOKDEPTH"}

        # ---- per-regime trade-vs-trade (or mid-vs-trade fallback) ----
        prim = hl_prn if hl_prn is not None else hl_mid
        prim_lens = "trade-vs-trade" if hl_prn is not None else "HLmid-vs-BNtrade(noprint)"
        for reg in ("calm", "volatile"):
            rdays = [d for d in days if regimes.get(d) == reg]
            if not rdays:
                continue
            cres["pairs"][f"PRIMARY_{reg}"] = run_pair(
                coin, prim[0], prim[1], bn_trd[0], bn_trd[1],
                f"{prim_lens}|{reg}", rdays, rng, do_placebo=False)

        # ---- per-coin verdict on the primary lens ----
        prim_name, p = _primary_pair(cres["pairs"])
        cres["primary_pair"] = prim_name
        verdict = grade(p)
        cres["verdict"] = verdict
        cres["primary_lens_used"] = ("trade-vs-trade" if hl_prn is not None
                                     else "HLmid-vs-BNtrade (no HL print series on disk)")
        out["by_coin"][coin] = cres
        _print_pair(coin, p, verdict)

    # cross-coin headline
    out["headline"] = headline(out["by_coin"])
    # THE SIZE OF THE HYPOTHESIS FAMILY AND THE ROOM THE BUDGET LEAVES UNDER IT, stated
    # in the artifact rather than left to whoever quotes a p from it. Both of this
    # probe's significances sit on the p-value floor, so the floor's distance from the
    # corrected threshold IS the strength of the claim, and it is short of what
    # settings.py declares. See placebo_family for why the budget is not raised.
    out["placebo_family"] = placebo_family(out["by_coin"], N_PLACEBO)
    # The scope states which coins were actually SCORED, not which were asked for. A
    # coin whose Binance ticks are not on disk is recorded above with a status and no
    # numbers, and a scope naming the requested list would let a two-coin claim be read
    # off a one-coin run. It also says the placebo budget out loud, because 50 draws put
    # this probe's smallest expressible p at 1/51 and no reading below that exists.
    scored = [c for c, v in out["by_coin"].items()
              if isinstance(v, dict) and "pairs" in v]
    skipped = {c: v.get("status") for c, v in out["by_coin"].items()
               if isinstance(v, dict) and "pairs" not in v}
    artifact.write(
        os.path.basename(OUT_JSON), out,
        script=__file__, inputs=[BINANCE_RAW]
        + [os.path.join(CODE_DIR, f"mid_series_{c}.npz") for c in COINS]
        + [os.path.join(CODE_DIR, f"hl_print_series_{c}.npz") for c in COINS],
        scope={
            "population": (f"raw asynchronous ticks of both venues over the days below, "
                           f"pre-thinned to a {HY_MIN_GAP_MS} ms minimum gap and capped "
                           f"at {MAX_HY_TICKS:,} ticks per series for the "
                           f"Hayashi-Yoshida scan, and sampled onto a {GRID_S} s grid "
                           f"for the vector error-correction model. {len(scored)} of "
                           f"{len(COINS)} coins were scored; skipped: {skipped or 'none'}"
                           f". The placebo budget is {N_PLACEBO} draws, so the smallest "
                           f"p this probe can express is "
                           f"{H.p_floor(N_PLACEBO):.4f}. Placebo family: "
                           f"{out['placebo_family']['statement_short']}"),
            "window": (f"{len(days)} UTC days, {days[0]} to {days[-1]}; the October "
                       f"cascade days {sorted(OCT10_DAYS)} are excluded by construction "
                       f"and dropped again here if they are passed in"),
            "coins": scored or f"n/a: no coin was scored, skipped {skipped}",
            "markout_horizon": ("none: this probe reads price SERIES and no markout "
                                "column, so it has no scoring horizon. The horizon_s "
                                "field of the fingerprint block below carries the "
                                "declared default and is not a property of this run"),
        },
        settings={"master_seed": SEED, "n_perm": N_PLACEBO},
        started=t0, out_dir=os.path.dirname(OUT_JSON))
    print(f"\n[probe_E] headline: {out['headline']}")
    print(f"[probe_E] placebo family: {out['placebo_family']['statement']}")
    print(f"[probe_E] wrote probes/{os.path.basename(OUT_JSON)}")


def grade(pair):
    """Apply the pre-registered directional / null decision to one pair result."""
    if not pair or pair.get("status") != "OK":
        return {"call": "NO_RESULT", "reason": pair.get("status") if pair else "missing"}
    vecm = pair.get("vecm") or {}
    hy = pair.get("hayashi_yoshida") or {}
    plac = pair.get("placebo") or {}
    is_mid = vecm.get("is_v1_mid")
    is_lo = vecm.get("is_v1_lower"); is_hi = vecm.get("is_v1_upper")
    lead = hy.get("hl_leads_s")
    beats = plac.get("beats_placebo", False)
    # null: IS midpoint within 0.5 +/- 0.10 AND HY peak ~0 AND placebo not beaten
    is_symmetric = (is_mid is not None and abs(is_mid - 0.5) <= 0.10)
    hy_zero = (lead is not None and abs(lead) <= HY_STEP_S + 1e-9)
    if is_symmetric and hy_zero and not beats:
        return {"call": "NO_LEAD_LAG", "is_v1_mid": is_mid, "hl_leads_s": lead,
                "beats_placebo": beats}
    # directional: IS bound excludes 0.5 same side as HY sign, placebo beaten
    direction = None
    if is_lo is not None and is_lo > 0.5 and lead is not None and lead > 0:
        direction = "HL_LEADS"
    elif is_hi is not None and is_hi < 0.5 and lead is not None and lead < 0:
        direction = "BINANCE_LEADS"
    if direction and beats:
        return {"call": direction, "is_v1_bounds": [is_lo, is_hi],
                "hl_leads_s": lead, "beats_placebo": beats}
    return {"call": "MIXED", "is_v1_mid": is_mid, "is_v1_bounds": [is_lo, is_hi],
            "hl_leads_s": lead, "beats_placebo": beats}


def _print_pair(coin, pair, verdict):
    if not pair or pair.get("status") != "OK":
        print(f"  {coin} primary: {pair.get('status') if pair else 'none'}")
        return
    vecm = pair.get("vecm") or {}
    hy = pair.get("hayashi_yoshida") or {}
    plac = pair.get("placebo") or {}
    print(f"  {coin} [{pair['lens']}] overlap={pair['overlap_hours']}h "
          f"HLticks={pair.get('n_hl_ticks_hy', pair.get('n_hl_ticks_raw', 0)):,} "
          f"BNticks={pair.get('n_bn_ticks_hy', pair.get('n_bn_ticks_raw', 0)):,}")
    print(f"     Hasbrouck IS(HL) mid={vecm.get('is_v1_mid')} "
          f"bounds=[{vecm.get('is_v1_lower')},{vecm.get('is_v1_upper')}] "
          f"| GG(HL)={vecm.get('gg_share_v1')}")
    print(f"     Hayashi-Yoshida HL_leads={hy.get('hl_leads_s')}s "
          f"peakcorr={hy.get('best_corr')} | placebo p={plac.get('placebo_p')} "
          f"beats={plac.get('beats_placebo')}")
    print(f"     VERDICT: {verdict.get('call')}")


def headline(by_coin):
    calls = {}
    for c, cd in by_coin.items():
        v = cd.get("verdict", {}) if isinstance(cd, dict) else {}
        calls[c] = v.get("call", cd.get("status", "?"))
    same = set(v for v in calls.values() if v in ("HL_LEADS", "BINANCE_LEADS"))
    if len(same) == 1 and all(calls[c] in same for c in calls):
        return f"DIRECTIONAL ({same.pop()}) on all coins: {calls}"
    if all(v == "NO_LEAD_LAG" for v in calls.values()):
        return f"NO LEAD-LAG (clean null) on all coins: {calls}"
    return f"MIXED / inconclusive: {calls}"


if __name__ == "__main__":
    main()
