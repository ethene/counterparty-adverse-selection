"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-22
References: [Hyperliquid L4 (Zenodo 18184441, Albers et al. 2026); node_fills_by_block]

PROBE D — does on-chain FLOW TOXICITY predict next-period funding / basis moves?
(second analysis unit; complement to the per-counterparty toxicity unit.)

QUESTION. Hyperliquid is a transparent DEX: every taker fill carries the signed
adverse-selection markout (toxicity). On a CEX you cannot see that. So the test
is whether aggregate on-chain flow toxicity carries INCREMENTAL information about
the NEXT period's change in the HL funding rate and the HL-vs-CEX basis, OVER AND
ABOVE (a) funding's own autoregression and (b) the contemporaneous CEX
(Binance) funding/premium controls. If a transparent-venue toxicity feature beats
a Double-AutoRegressive (DAR) null AFTER the CEX controls, the on-chain
observability is doing real work; if not, we report a clean, well-identified
negative ("toxicity is priced one-for-one with the CEX signal a venue can already
see"). Inan SSRN 5576424 (DAR funding null) magnitudes are a USER manual read.

REFERENCE-MID RULE (hard constraint). The funding clock outcomes use ONLY:
  - funding_rate / premium reported by HL and Binance public APIs;
  - basis = (HL premium) vs (Binance premium), where premium is each venue's own
    published mark-vs-index premium, NOT a constructed mark.
We NEVER use the HL oracle/mark as a reference for anything (it is a stake-weighted
median of CEX spot mids = circular). Flow-toxicity features come from the per-fill
trade-print markout (mo1/mo10/mo60 in panel_markouts.npz, bps); the trade-print is
the EXECUTION-COST lens and is the right object for a "how toxic was the flow"
aggregate (it does not feed any reference price here).

GRANULARITY. HL funding pays HOURLY; Binance USDT-M pays every 8 HOURS. We resolve
the mismatch two ways and report both: (A) aggregate HL to the 8h Binance clock
(sum/avg funding over each 8h bin) so HL and Binance live on one clock; (B) keep
the HL hourly clock and carry the Binance 8h funding as a step-function control
(forward-filled, plus an "hours-since-CEX-settlement" cadence dummy). The panel
spans the 8 monthly windows of the markout panel (Aug/Sep/Oct/Nov 2025, Dec 2025,
Jan/Mar/May 2026), days 4-15 of each, BTC/ETH/SOL.

KILL-CRITERION (pre-registered). Toxicity must beat the DAR null AFTER the CEX
controls: in the full model
    d_funding_{t+1} = AR(funding) + AR(|funding|)  [DAR null]
                    + CEX controls (Binance funding/premium, same clock)
                    + TOXICITY features (on-chain),
the toxicity block must add adjusted-R^2 / cut OOS RMSE versus the
DAR+CEX restricted model, with the joint block significant after a
Newey-West (HAC) covariance and surviving the placebo + whale-drop. If the
incremental OOS R^2 <= 0 (no lift), we PASS the criterion as a clean NEGATIVE
(report it; well-identified null: transparent-venue toxicity is already in the CEX
funding signal). PRE-REGISTERED so a null is not retrofitted as a win.

GUARDS (per project standard): per-coin reporting (never pooled-only);
a SHUFFLE placebo (permute the toxicity series within coin -> incremental R^2
must collapse to ~0); a RANDOM-LAG placebo (use toxicity from a random other bin);
a WHALE-DROP (rebuild toxicity after dropping the top-5 takers by notional ->
result must survive); a no-lookahead clock (features at bin t predict the change
into bin t+1, strict searchsorted-style alignment by funding_time).

INPUTS (read-only):
  panel_markouts.npz (repository root)                         (on-disk, verified)
  ../02_data/raw/funding/hl_funding.parquet                    (Probe-D data pull)
  ../02_data/raw/funding/binance_funding.parquet               (Probe-D data pull)
  ../02_data/raw/funding/binance_spot_klines.parquet           (Probe-D data pull, basis)
Each funding parquet uses the same venue-neutral funding-history schema:
  venue, symbol, funding_time_ms, rate_native, interval_hours, premium_index, ...
The HL backfill writes premium_index (HL exposes it); the Binance backfill leaves
premium_index NULL but writes mark_price_usd, so the Binance "premium" control is
the Binance funding rate itself plus a mark-vs-spot premium reconstructed from
mark_price_usd and the spot close (NOT an HL mark). Spot klines columns:
  symbol, open_time_ms, close (float).

Heavy numpy/regression: run in BACKGROUND. Writes JSON + prints a summary.
"""
import os
import sys

import numpy as np

# artifact.py and settings.py live one directory up, so every path below is built from
# this file's own location and never from the working directory the run happens to start
# in. The funding parquets sit outside the code directory, under the data tree, so their
# path is built from the same anchor rather than typed as a repository-root-relative
# string.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import artifact  # noqa: E402
import panel_io as P  # noqa: E402
import settings as H  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CODE_DIR = os.path.dirname(HERE)
# Located by panel_io rather than joined here, so the one place that knows where the
# markout panels live is the one place that has to change if they move.
PANEL = os.path.join(P.data_root(), "panel_markouts.npz")
# The toxicity feature is built on the COMPANION window, and the name of its column is
# asked for once here rather than spelled at each of the four places that used it. It is
# also the key this file gives that column inside its own panel dict, so the dict key
# and the column it holds are the same string by construction.
SCORE_COL = P.score_col("panel", H.COMPANION_HORIZON_S)
FUNDING_DIR = os.path.normpath(
    os.path.join(os.path.dirname(CODE_DIR), "02_data", "raw", "funding"))
HL_FUNDING = os.path.join(FUNDING_DIR, "hl_funding.parquet")
BN_FUNDING = os.path.join(FUNDING_DIR, "binance_funding.parquet")
BN_SPOT = os.path.join(FUNDING_DIR, "binance_spot_klines.parquet")
OUT = os.path.join(HERE, "probe_D_funding_results.json")

COIN = {0: "BTC", 1: "ETH", 2: "SOL"}
COIN_TO_BN = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT"}
# The placebo and walk-forward seed. NOT settings.MASTER_SEED. READ from settings.py,
# which declares 690 for this purpose, so every stream this file opens is the one its
# published numbers were drawn from. The value stays at 690: each coin-and-clock arm
# opens its OWN generator at SEED + coin + a clock offset, so this is the origin of a
# family of streams rather than one stream, and rebinding it to MASTER_SEED would move
# every placebo and every incremental R-squared in the file at once. Recorded as an
# override in the artifact's fingerprint.
#
# Note for whoever carries this further: the `rng = np.random.default_rng(SEED)` opened
# at the top of main() is DEAD -- nothing reads it, because every arm builds its own. It
# is left in place rather than deleted here so that this pass moves no number at all, but
# it reads as if one stream were threaded through the file, and it is not.
SEED = H.seed_for("probe_D_funding")
HOUR_MS = 3_600_000
DAY_MS = 86_400_000
EIGHT_H_MS = 8 * HOUR_MS

# panel windows: month code -> (year, month). days 4-15 of each window only.
WINDOWS = {202508: (2025, 8), 202509: (2025, 9), 202510: (2025, 10),
           202511: (2025, 11), 202512: (2025, 12), 202601: (2026, 1),
           202603: (2026, 3), 202605: (2026, 5)}


# --------------------------------------------------------------------------- io
def _load_parquet(path):
    """Load a parquet into a dict of numpy arrays (pyarrow). Returns None if absent."""
    if not os.path.exists(path):
        return None
    import pyarrow.parquet as pq
    tbl = pq.read_table(path)
    return {name: tbl.column(name).to_numpy(zero_copy_only=False)
            for name in tbl.column_names}


# --------------------------------------------------------------- panel -> clock
def bin_index_8h(t_ms):
    """8h bin index aligned to the Binance settlement grid (00:00/08:00/16:00 UTC)."""
    return (t_ms // EIGHT_H_MS).astype(np.int64)


def bin_index_1h(t_ms):
    return (t_ms // HOUR_MS).astype(np.int64)


def block_time_ms_for_panel(period, day):
    """Approximate per-fill epoch-ms WITHOUT the native block_time column (dropped at
    npz-persist). The panel only retains (period=YYYYMM, day=1..15). We CANNOT place a
    fill at sub-day resolution from the npz alone, so the panel toxicity aggregate is
    built at DAILY resolution and then mapped onto the funding clock by day. This is a
    deliberate, documented coarsening: the funding outcome is the change from one
    funding bin to the next, and the predictor is that day's realised flow toxicity.
    A block_time re-pull (data_acquisition_log 2026-06-22) would lift this to true 1h/8h
    intraday toxicity; flagged in the result as the v2 upgrade."""
    out = np.empty(period.size, dtype=np.int64)
    # vectorise by unique (period, day)
    key = period.astype(np.int64) * 100 + day.astype(np.int64)
    uk, inv = np.unique(key, return_inverse=True)
    base = np.empty(uk.size, dtype=np.int64)
    import datetime as dt
    for i, k in enumerate(uk):
        p = int(k // 100); dd = int(k % 100)
        y, mo = WINDOWS[p]
        base[i] = int(dt.datetime(y, mo, dd, tzinfo=dt.timezone.utc).timestamp() * 1000)
    return base[inv]


# ----------------------------------------------------- toxicity feature builder
def daily_toxicity(period, day, coin, mo, notional, taker_id, c, drop_whales=0):
    """Per-(window,day) flow-toxicity features for coin c, from the trade-print markout.
    Returns sorted arrays: day_ms (UTC midnight of that calendar day), and features.
      tox_mean     = notional-weighted mean markout (bps) = aggregate adverse selection
      tox_pos_frac = share of notional with markout > 0 (taker-profited = toxic)
      flow_n       = number of fills (activity control)
    drop_whales>0: drop the top-k takers by total notional in coin c (robustness)."""
    sel = (coin == c) & np.isfinite(mo)
    p = period[sel]; d = day[sel]; m = mo[sel].astype(np.float64)
    w = notional[sel].astype(np.float64); tk = taker_id[sel]
    if drop_whales > 0 and p.size:
        utk, inv = np.unique(tk, return_inverse=True)
        tot = np.bincount(inv, weights=w, minlength=utk.size)
        whales = set(np.argsort(tot)[::-1][:drop_whales].tolist())
        keep = ~np.isin(inv, list(whales))
        p, d, m, w, tk = p[keep], d[keep], m[keep], w[keep], tk[keep]
    if p.size == 0:
        return None
    key = p.astype(np.int64) * 100 + d.astype(np.int64)
    uk, inv = np.unique(key, return_inverse=True)
    n = uk.size
    sw = np.bincount(inv, weights=w, minlength=n)
    swm = np.bincount(inv, weights=w * m, minlength=n)
    cnt = np.bincount(inv, minlength=n).astype(np.float64)
    posw = np.bincount(inv, weights=w * (m > 0), minlength=n)
    tox_mean = swm / np.maximum(sw, 1e-12)
    tox_pos = posw / np.maximum(sw, 1e-12)
    # map each (window,day) key to a UTC-midnight epoch-ms. NO-LOOKAHEAD: a full
    # calendar day's flow toxicity is only fully realised at the END of that day, so
    # we stamp it at the START OF THE NEXT DAY (midnight of D+1). The downstream as-of
    # join (last-at-or-before) then assigns day-D toxicity only to funding bins that
    # begin on D+1 onward — never to an intraday-D bin that would peek at later-in-D
    # fills. (Placing it at midnight-of-D would let an 08:00-on-D bin be "predicted"
    # by fills through 23:59 on D = lookahead.)
    import datetime as dt
    day_ms = np.empty(n, dtype=np.int64)
    for i, k in enumerate(uk):
        pp = int(k // 100); dd = int(k % 100)
        y, mo_ = WINDOWS[pp]
        midnight_d = int(dt.datetime(y, mo_, dd, tzinfo=dt.timezone.utc).timestamp() * 1000)
        day_ms[i] = midnight_d + DAY_MS  # available only from start of D+1
    order = np.argsort(day_ms)
    return {"day_ms": day_ms[order], "tox_mean": tox_mean[order],
            "tox_pos": tox_pos[order], "flow_n": cnt[order]}


# ------------------------------------------------------- funding clock builders
def funding_series(fund, symbol):
    """Return (time_ms sorted, rate, premium_or_nan) for one symbol from a backfill dict."""
    sel = (fund["symbol"] == symbol)
    t = fund["funding_time_ms"][sel].astype(np.int64)
    r = fund["rate_native"][sel].astype(np.float64)
    if "premium_index" in fund:
        prem = np.asarray(fund["premium_index"][sel], dtype=np.float64)
    else:
        prem = np.full(t.size, np.nan)
    o = np.argsort(t)
    return t[o], r[o], prem[o]


def asof_value(query_ms, src_ms, src_val):
    """Last-at-or-before join (no lookahead): for each query bin start, the most recent
    funding value already settled. searchsorted side='right' minus 1; before first -> nan."""
    idx = np.searchsorted(src_ms, query_ms, side="right") - 1
    out = np.full(query_ms.size, np.nan)
    ok = idx >= 0
    out[ok] = src_val[idx[ok]]
    return out


def binance_premium(bn_fund, spot, symbol):
    """Reconstruct a Binance mark-vs-spot premium WITHOUT touching any HL price.
    premium = (mark_price_usd - spot_close_at_or_before) / spot_close. Binance funding
    rows carry markPrice (mark_price_usd); spot close from /api/v3/klines. This is the
    CEX premium control used alongside the Binance funding rate."""
    t, r, _ = funding_series(bn_fund, symbol)
    # markPrice rides the same funding rows -> pull directly (sorted by time)
    sel = (bn_fund["symbol"] == symbol)
    tm = bn_fund["funding_time_ms"][sel].astype(np.int64)
    mk = np.asarray(bn_fund["mark_price_usd"][sel], dtype=np.float64)
    o = np.argsort(tm)
    tm, mk = tm[o], mk[o]
    ssel = (spot["symbol"] == symbol)
    st = spot["open_time_ms"][ssel].astype(np.int64)
    sc = np.asarray(spot["close"][ssel], dtype=np.float64)
    so = np.argsort(st)
    st, sc = st[so], sc[so]
    spot_at = asof_value(tm, st, sc)
    prem = (mk - spot_at) / np.where(np.isfinite(spot_at) & (spot_at != 0), spot_at, np.nan)
    return tm, r, prem


# ------------------------------------------------------------------- regression
def ols(X, y):
    """OLS via lstsq; returns (beta, resid, yhat). X must include intercept column."""
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    yhat = X @ beta
    return beta, y - yhat, yhat


def adj_r2(y, resid, k):
    n = y.size
    sse = float(resid @ resid)
    sst = float(((y - y.mean()) ** 2).sum())
    if sst <= 0 or n - k <= 0:
        return float("nan")
    r2 = 1 - sse / sst
    return 1 - (1 - r2) * (n - 1) / (n - k)


def newey_west_F(X_full, X_restr, y, lags=2):
    """Joint significance of the extra columns in X_full vs X_restr via a HAC (Newey-West)
    Wald test on the added block. Returns (wald_stat, df). Simple, robust to the funding
    clock's mild autocorrelation."""
    # added columns = those in full not in restricted (full = [restr | extra])
    p_r = X_restr.shape[1]
    beta, resid, _ = ols(X_full, y)
    n, p = X_full.shape
    # HAC meat
    u = resid[:, None] * X_full
    S = u.T @ u
    for L in range(1, lags + 1):
        w = 1 - L / (lags + 1)
        G = u[L:].T @ u[:-L]
        S += w * (G + G.T)
    XtX_inv = np.linalg.pinv(X_full.T @ X_full)
    V = XtX_inv @ S @ XtX_inv
    extra = np.arange(p_r, p)
    if extra.size == 0:
        return 0.0, 0
    b = beta[extra]
    Vb = V[np.ix_(extra, extra)]
    wald = float(b @ np.linalg.pinv(Vb) @ b)
    return wald, extra.size


def oos_rmse(X, y, n_splits=5):
    """Expanding-window walk-forward OOS RMSE (time-ordered; no shuffle = no lookahead)."""
    n = y.size
    if n < 30:
        return float("nan")
    fold = n // (n_splits + 1)
    errs = []
    for s in range(1, n_splits + 1):
        tr = slice(0, s * fold)
        te = slice(s * fold, (s + 1) * fold)
        if te.stop - te.start < 3 or tr.stop < X.shape[1] + 2:
            continue
        beta, *_ = np.linalg.lstsq(X[tr], y[tr], rcond=None)
        e = y[te] - X[te] @ beta
        errs.append(float(e @ e))
    if not errs:
        return float("nan")
    # pooled RMSE across folds
    tot_n = sum(min((s + 1) * fold, n) - s * fold for s in range(1, n_splits + 1)
                if min((s + 1) * fold, n) - s * fold >= 3 and s * fold >= X.shape[1] + 2)
    return float(np.sqrt(sum(errs) / max(tot_n, 1)))


def build_design(funding_now, funding_lag, absfund_lag, cex_rate, cex_prem, tox, flow):
    """Assemble [intercept] and three nested designs sharing rows where all finite.
      DAR null   : [1, funding_lag, |funding|_lag]
      DAR+CEX    : DAR + [cex_rate, cex_prem]
      DAR+CEX+TOX: DAR+CEX + [tox_mean, tox_pos? -> here single tox col, flow]
    Returns (y, X_dar, X_cex, X_full, mask)."""
    cols = [funding_lag, absfund_lag, cex_rate, cex_prem, tox, flow, funding_now]
    fin = np.all([np.isfinite(c) for c in cols], axis=0)
    one = np.ones(int(fin.sum()))
    fl, af, cr, cp, tx, fn_, y = (c[fin] for c in cols)
    X_dar = np.column_stack([one, fl, af])
    X_cex = np.column_stack([one, fl, af, cr, cp])
    X_full = np.column_stack([one, fl, af, cr, cp, tx, fn_])
    return y, X_dar, X_cex, X_full, fin


# ------------------------------------------------------------------- per-coin run
def run_coin(c, panel, hl_fund, bn_fund, spot, rng, clock="8h"):
    name = COIN[c]
    bn_sym = COIN_TO_BN[name]
    # HL funding native hourly; aggregate to chosen clock for the outcome
    hlt, hlr, hlp = funding_series(hl_fund, name)
    if hlt.size < 10:
        return {"coin": name, "status": "no_HL_funding"}
    if clock == "8h":
        bins = bin_index_8h(hlt)
        ub, inv = np.unique(bins, return_inverse=True)
        # 8h HL funding = SUM of the hourly rates in the bin (8 hourly payments ~ one 8h)
        f_now = np.bincount(inv, weights=hlr, minlength=ub.size)
        # HL premium: average over the FINITE hourly premiums in the 8h bin only
        # (do NOT zero-fill NaNs, which would bias the bin premium toward 0).
        pfin = np.isfinite(hlp)
        psum = np.bincount(inv, weights=np.where(pfin, hlp, 0.0), minlength=ub.size)
        pcnt = np.bincount(inv, weights=pfin.astype(np.float64), minlength=ub.size)
        f_prem = np.where(pcnt > 0, psum / np.maximum(pcnt, 1.0), np.nan)
        bin_ms = ub * EIGHT_H_MS
    else:  # 1h
        bin_ms = hlt
        f_now = hlr
        f_prem = hlp
    order = np.argsort(bin_ms)
    bin_ms, f_now, f_prem = bin_ms[order], f_now[order], f_prem[order]
    # outcome = change INTO next bin: d_funding_{t+1} = f_now[t+1] - f_now[t]
    d_next = np.full(bin_ms.size, np.nan)
    d_next[:-1] = f_now[1:] - f_now[:-1]
    # AR predictors known at t
    f_lag = f_now.copy()
    af_lag = np.abs(f_now)
    # CEX controls (Binance), as-of last settled before each HL bin start (no lookahead)
    bnt, bnr, bnp = binance_premium(bn_fund, spot, bn_sym)
    cex_rate = asof_value(bin_ms, bnt, bnr)
    cex_prem = asof_value(bin_ms, bnt, bnp)
    # toxicity from the panel, daily -> map to each funding bin via as-of (last day <= bin)
    tox = daily_toxicity(panel["period"], panel["day"], panel["coin"], panel[SCORE_COL],
                         panel["notional"], panel["taker_id"], c)
    if tox is None:
        return {"coin": name, "status": "no_panel_coin"}
    tox_mean = asof_value(bin_ms, tox["day_ms"], tox["tox_mean"])
    flow_n = asof_value(bin_ms, tox["day_ms"], tox["flow_n"])
    flow_n = np.log1p(np.where(np.isfinite(flow_n), flow_n, 0.0))

    # primary outcome d_funding; also basis-change if both premiums present
    out = {"coin": name, "clock": clock, "n_bins": int(bin_ms.size)}

    def eval_block(y_out, label, tox_series, flow_series):
        y, Xd, Xc, Xf, mask = build_design(
            f_now, f_lag, af_lag, cex_rate, cex_prem, tox_series, flow_series)
        # outcome alignment: y_out is per-bin; restrict to mask AND set y to the OUTCOME
        y = y_out[mask]
        ok = np.isfinite(y)
        if ok.sum() < 30:
            return {"label": label, "status": "insufficient_n", "n": int(ok.sum())}
        y = y[ok]; Xd = Xd[ok]; Xc = Xc[ok]; Xf = Xf[ok]
        _, rd, _ = ols(Xd, y)
        _, rc, _ = ols(Xc, y)
        _, rf, _ = ols(Xf, y)
        ar2_d = adj_r2(y, rd, Xd.shape[1])
        ar2_c = adj_r2(y, rc, Xc.shape[1])
        ar2_f = adj_r2(y, rf, Xf.shape[1])
        wald, df = newey_west_F(Xf, Xc, y, lags=2)
        # chi2 p-value for the joint toxicity block
        from scipy import stats as st
        pval = float(st.chi2.sf(wald, df)) if df > 0 else float("nan")
        rmse_c = oos_rmse(Xc, y)
        rmse_f = oos_rmse(Xf, y)
        incr_oos_r2 = (1 - (rmse_f ** 2) / (rmse_c ** 2)) if (np.isfinite(rmse_c)
                       and rmse_c > 0 and np.isfinite(rmse_f)) else float("nan")
        return {"label": label, "n": int(y.size),
                "adjR2_DAR": round(ar2_d, 5), "adjR2_DAR_CEX": round(ar2_c, 5),
                "adjR2_DAR_CEX_TOX": round(ar2_f, 5),
                "incr_adjR2_tox_over_cex": round(ar2_f - ar2_c, 5),
                "wald_tox_block": round(wald, 3), "df": int(df),
                "p_tox_block_HAC": round(pval, 5),
                "oos_rmse_DAR_CEX": round(rmse_c, 7) if np.isfinite(rmse_c) else None,
                "oos_rmse_full": round(rmse_f, 7) if np.isfinite(rmse_f) else None,
                "incr_oos_R2": round(incr_oos_r2, 5) if np.isfinite(incr_oos_r2) else None,
                "KILL": ("PASS_positive" if (np.isfinite(incr_oos_r2) and incr_oos_r2 > 0
                          and np.isfinite(pval) and pval < 0.05)
                         else "PASS_clean_negative")}

    out["funding_change"] = eval_block(d_next, "d_funding_next", tox_mean, flow_n)

    # basis change outcome = change in (HL premium - CEX premium) into next bin
    basis = f_prem - asof_value(bin_ms, bnt, bnp)
    d_basis = np.full(bin_ms.size, np.nan)
    d_basis[:-1] = basis[1:] - basis[:-1]
    out["basis_change"] = eval_block(d_basis, "d_basis_next", tox_mean, flow_n)

    # ---- placebo 1: SHUFFLE toxicity within coin (break time alignment)
    tox_shuf = tox_mean.copy()
    fin_t = np.isfinite(tox_shuf)
    idx_fin = np.where(fin_t)[0]
    tmp = tox_shuf[idx_fin]
    tox_shuf[idx_fin] = tmp[rng.permutation(tmp.size)]
    out["placebo_shuffle_funding"] = eval_block(d_next, "placebo_shuffle", tox_shuf, flow_n)

    # ---- placebo 2: RANDOM-LAG (roll toxicity by a random nonzero offset)
    roll = int(rng.integers(3, max(4, tox_mean.size // 3)))
    tox_roll = np.roll(tox_mean, roll)
    out["placebo_randomlag_funding"] = eval_block(d_next, "placebo_randomlag", tox_roll, flow_n)

    # ---- whale-drop: rebuild toxicity after dropping top-5 takers by notional
    tox_wd = daily_toxicity(panel["period"], panel["day"], panel["coin"], panel[SCORE_COL],
                            panel["notional"], panel["taker_id"], c, drop_whales=5)
    if tox_wd is not None:
        tox_mean_wd = asof_value(bin_ms, tox_wd["day_ms"], tox_wd["tox_mean"])
        out["whale_drop_funding"] = eval_block(d_next, "whale_drop", tox_mean_wd, flow_n)
    return out


# --------------------------------------------------------------------------- main
def main():
    t0 = artifact.start_clock()
    rng = np.random.default_rng(SEED)
    # panel_io names the producer to run when the file is absent, so that message
    # is written once for the whole tree; the load itself stays here because
    # build.py derives this script's input edge from the argument of np.load.
    P.require_present("panel", PANEL)
    d = np.load(PANEL, allow_pickle=True)
    panel = {"period": d["period"].astype(np.int64), "day": d["day"].astype(np.int64),
             "coin": d["coin"].astype(np.int64), SCORE_COL: P.score(d, "panel", H.COMPANION_HORIZON_S),
             "notional": d["notional"].astype(np.float64),
             "taker_id": d["taker_id"].astype(np.int64)}
    hl_fund = _load_parquet(HL_FUNDING)
    bn_fund = _load_parquet(BN_FUNDING)
    spot = _load_parquet(BN_SPOT)
    missing = [n for n, x in [("hl_funding", hl_fund), ("binance_funding", bn_fund),
                              ("binance_spot_klines", spot)] if x is None]
    if missing:
        print("MISSING DATA (run the Probe-D data pull first):", missing)
        print("Expected under", FUNDING_DIR)
        # The artifact is still written, and it still states its scope: a results file
        # that silently keeps yesterday's numbers under today's timestamp is worse than
        # one that says it computed nothing. The scope declines each field WITH the
        # reason, which is the form artifact.write accepts in place of a value.
        out = {"status": "missing_data", "missing": missing,
               "expected_dir": os.path.basename(FUNDING_DIR)}
        artifact.write(
            os.path.basename(OUT), out,
            script=__file__, inputs=[PANEL, HL_FUNDING, BN_FUNDING, BN_SPOT],
            scope={
                "population": f"n/a: nothing was computed; missing inputs {missing}",
                "window": "n/a: no window was covered, the run stopped before loading",
                "coins": "n/a: no coin was scored, the run stopped before loading",
            },
            settings={"h": H.COMPANION_HORIZON_S, "lens": "print",
                      "master_seed": SEED},
            started=t0, out_dir=os.path.dirname(OUT))
        return

    print(f"Probe D | panel {panel['coin'].size:,} fills | "
          f"HL funding rows {hl_fund['symbol'].size:,} | "
          f"BN funding rows {bn_fund['symbol'].size:,}")

    results = {"seed": SEED, "kill_criterion":
               "toxicity beats DAR null AFTER CEX controls (incr OOS R2>0 & HAC p<0.05); "
               "incr OOS R2<=0 = clean well-identified NEGATIVE",
               "reference_note": "funding/premium from HL+Binance public APIs only; "
               "HL oracle/mark NEVER used; basis = HL premium vs Binance premium; "
               "toxicity = trade-print markout aggregate (execution-cost lens).",
               "by_coin": {}}
    for clock in ("8h", "1h"):
        for c in (0, 1, 2):
            r = run_coin(c, panel, hl_fund, bn_fund, spot,
                         np.random.default_rng(SEED + c + (0 if clock == "8h" else 100)),
                         clock=clock)
            results["by_coin"].setdefault(clock, {})[COIN[c]] = r
            fc = r.get("funding_change", {})
            print(f"[{clock}] {COIN[c]:3s} n={r.get('n_bins','?'):>5} "
                  f"incr_adjR2={fc.get('incr_adjR2_tox_over_cex')} "
                  f"incr_oosR2={fc.get('incr_oos_R2')} "
                  f"p_HAC={fc.get('p_tox_block_HAC')} -> {fc.get('KILL')}")

    # The population is a count of BINS, not of fills, and the two differ by four orders
    # of magnitude here: the panel's fills are aggregated to a coin x funding-bin series
    # before anything is regressed, so the regressions have as many observations as
    # there are bins. Stating the fill count alone would let a reader read a
    # twenty-million-row standard error off a few-hundred-row regression.
    periods = sorted(int(p) for p in np.unique(panel["period"]))
    days = np.unique(panel["day"])
    n_bins = {clock: {c: r.get("n_bins") for c, r in by.items()}
              for clock, by in results["by_coin"].items()}
    artifact.write(
        os.path.basename(OUT), results,
        script=__file__, inputs=[PANEL, HL_FUNDING, BN_FUNDING, BN_SPOT],
        scope={
            "population": (f"{panel['coin'].size:,} panel fills aggregated to a "
                           f"per-coin funding-bin series; the regressions run on the "
                           f"bins, not the fills, and the bin counts per clock and coin "
                           f"are {n_bins}. Funding and premium come from the Hyperliquid "
                           f"and Binance public endpoints, and the Hyperliquid oracle "
                           f"and mark are never read"),
            "window": (f"{len(periods)} monthly windows, {periods[0]} to "
                       f"{periods[-1]}, each contributing day-of-month "
                       f"{days.min()}-{days.max()}; both funding clocks are reported, "
                       f"the 8-hour Binance cadence and the 1-hour Hyperliquid one"),
            "coins": [COIN[c] for c in sorted(COIN)],
        },
        settings={"h": H.COMPANION_HORIZON_S, "lens": "print",
                  "master_seed": SEED},
        started=t0, out_dir=os.path.dirname(OUT))
    print("\nwrote", os.path.basename(OUT))


if __name__ == "__main__":
    main()
