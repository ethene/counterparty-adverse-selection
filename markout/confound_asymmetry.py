"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-19
References: Hyperliquid node-data S3 archive; Zenodo 18184441 (Albers et al. 2026).
"""

# ---------------------------------------------------------------------------
# OBJECT CONFOUND - DIRECTIONAL-DRIFT vs ADVERSE-SELECTION ASYMMETRY.
#
# A signed taker markout (positive = taker profited = maker adverse-selected)
# folds two distinct things into one number on a trending day:
#   (1) genuine adverse selection - informed takers picking off stale quotes;
#   (2) plain directional drift - in a window where price rose, every BUY
#       aggressor looks good and every SELL aggressor looks bad afterwards
#       (or the reverse on a falling window), purely from the trend, with no
#       information content at all.
#
# An earlier read found, POOLED and at the LONG COMPANION window of 60 s, the mean
# markout on SELL-aggressor trades (taker_side=0) around +0.77 bps versus
# BUY-aggressor (taker_side=1) around +0.34 bps - roughly a 2.3x gap. Those two
# figures are the companion window, not the window the study scores wallets on, and
# the gap is far smaller at the headline window; naming the window is therefore part
# of the finding. December 2025 had a price drift, so the concern is concrete: that
# buy/sell gap could be the drift leaking into the signed-markout convention rather
# than a real difference in counterparty toxicity. This object quantifies, AT EVERY
# RUNG OF THE LADDER and selecting none of them, how much of the signed markout is a
# stable adverse-selection feature versus a buy/sell asymmetry that tracks the trend.
#
# Per coin (BTC, ETH) and pooled, this reports:
#   1. Mean / median markout at each rung, split by taker_side (buy vs sell), with n,
#      a notional-weighted mean, and a bootstrap 95% CI on each side's mean.
#   2. The buy-minus-sell gap at each horizon, with a bootstrap CI on the gap.
#   3. A WITHIN-DAY control: the buy/sell gap recomputed day by day (days 4..13),
#      with per-day buy mean, sell mean and gap. A drift confound would make the
#      gap track each day's direction (flipping sign with the day's return);
#      a genuine feature keeps a stable sign across days.
#   4. A drift-neutralized view: the gap after DE-MEANING each day's markout by
#      that day's overall mean. Subtracting a constant daily drift removes a
#      first-order trend effect, so the surviving gap is the asymmetry that is
#      NOT explained by a constant per-day drift.
#   5. A one-line honest verdict per slice and horizon: is the SELL>BUY
#      asymmetry a likely directional-drift artifact (gap tracks days, collapses
#      after de-meaning) or a stable feature (survives within-day + de-meaning)?
#
# HONEST FRAMING (hard requirement). The signed-markout convention CANNOT, on
# its own, separate adverse selection from drift; this object does not claim to
# fully decompose them. It measures whether the specific buy/sell asymmetry is
# fragile to two standard drift controls (per-day sign stability and per-day
# de-meaning). Surviving both is necessary, not sufficient, evidence that the
# asymmetry is a real feature. The verdict is a flag for the writeup, not a test
# statistic, and is reported as such.
#
# numpy-only. Reads ONE shared intermediate (quickwin_markouts.npz) produced by
# the expensive orchestrator pass. Does NOT parse raw data here. Fixed RNG seed
# so the bootstrap CIs are reproducible.
#
# Run command (bare python3 is BLOCKED on this machine):
#   uv run --no-project --with-requirements requirements.txt python3 markout/confound_asymmetry.py
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

# -------------------- configuration --------------------
HERE = os.path.dirname(os.path.abspath(__file__))
# Located by panel_io rather than joined here, so the one place that knows where
# the markout panels live is the one place that has to change if they move.
NPZ_PATH = os.path.join(P.data_root(), "quickwin_markouts.npz")
RESULTS_PATH = os.path.join(HERE, "confound_asymmetry_results.json")

COIN_CODES = H.coin_labels("quickwin")    # the map belongs to the FILE, not the project
# Every rung of the ladder, short-to-long, built from settings.LADDER_S. This object
# selects no window: the whole point is how the buy/sell asymmetry behaves as the
# window lengthens, so a "headline" here would be a claim the file does not make.
HORIZONS = tuple(H.headline_print_col(h) for h in H.LADDER_S)
SIDE_BUY = 1                              # taker_side=1 -> buy aggressor
SIDE_SELL = 0                             # taker_side=0 -> sell aggressor
SEED = H.seed_for("confound_asymmetry")   # fixed bootstrap seed, READ from settings.py
                                          # and no longer typed. The value is the same
                                          # 20260619 this file has always drawn from, so
                                          # no number here moves; settings.MASTER_SEED is
                                          # 20260620, so the fingerprint still records
                                          # this as an explicit override
N_BOOT = H.N_BOOT                         # bootstrap resamples (small-n fallback only);
                                          # the declared budget, so fifty draws land in
                                          # each tail of a 95% interval
CI_LO, CI_HI = 2.5, 97.5                  # 95% percentile CI bounds
BIG_N = 2000                              # n above which the CI is computed
                                          # analytically (CLT) instead of by
                                          # resampling - exact-enough here and
                                          # ~1000x faster than a per-trade boot
Z95 = 1.959963984540054                   # 97.5th std-normal quantile (95% CI)

# Verdict thresholds (flags for the writeup, NOT test statistics):
#   - the de-meaned gap must keep at least this fraction of the raw gap AND keep
#     its sign for the asymmetry to be called "stable" rather than drift;
#   - the per-day gap sign must agree with the pooled gap sign on at least this
#     fraction of days for the within-day control to call it stable.
DEMEAN_SURVIVE_FRAC = 0.5
DAY_SIGN_STABLE_FRAC = 0.7

VERDICT_NOTE = (
    "Verdict is a writeup flag, not a test statistic. The signed-markout "
    "convention cannot fully separate adverse selection from directional drift; "
    "this only checks whether the buy/sell asymmetry survives two standard drift "
    "controls (per-day sign stability and per-day de-meaning). Surviving both is "
    "necessary, not sufficient, for the asymmetry to be a real feature."
)


# -------------------- helpers --------------------
def _finite(x):
    """Return the finite subset of x as float64 (drops NaN/inf rows)."""
    x = np.asarray(x, dtype=np.float64)
    return x[np.isfinite(x)]


def _mean_or_nan(x):
    x = _finite(x)
    return float(x.mean()) if x.size else float("nan")


def _median_or_nan(x):
    x = _finite(x)
    return float(np.median(x)) if x.size else float("nan")


def _wmean_or_nan(values, weights):
    """Notional-weighted mean over rows where both value and weight are finite
    and the weight is non-negative. NaN if no usable weight remains."""
    v = np.asarray(values, dtype=np.float64)
    w = np.asarray(weights, dtype=np.float64)
    ok = np.isfinite(v) & np.isfinite(w) & (w >= 0)
    v, w = v[ok], w[ok]
    tot = w.sum()
    if v.size == 0 or tot <= 0:
        return float("nan")
    return float(np.sum(v * w) / tot)


def _mean_ci(values, rng, n_boot=N_BOOT):
    """95% CI on the mean of a 1-D vector.

    For a large vector (n > BIG_N) the bootstrap distribution of the sample mean
    is, by the CLT, Normal(mean, std/sqrt(n)), so the CI is computed ANALYTICALLY
    as mean +/- Z95 * std/sqrt(n). This is exact-enough for these sample sizes
    (hundreds of thousands of trades) and runs in microseconds instead of
    resampling a per-trade array a thousand times.

    For a small vector (n <= BIG_N) it falls back to a vectorized percentile
    bootstrap, capped at n_boot resamples, using the seeded rng for
    reproducibility. Returns (lo, hi), or (nan, nan) when the vector is empty.
    """
    v = _finite(values)
    if v.size == 0:
        return float("nan"), float("nan")
    if v.size == 1:
        return float(v[0]), float(v[0])
    if v.size > BIG_N:
        m = float(v.mean())
        se = float(v.std(ddof=1)) / np.sqrt(v.size)
        return m - Z95 * se, m + Z95 * se
    idx = rng.integers(0, v.size, size=(n_boot, v.size))
    means = v[idx].mean(axis=1)
    lo = float(np.percentile(means, CI_LO))
    hi = float(np.percentile(means, CI_HI))
    return lo, hi


def _gap_ci(buy_vals, sell_vals, rng, n_boot=N_BOOT):
    """95% CI on the buy-minus-sell mean gap.

    The two sides are disjoint trade sets, so the gap variance is the sum of the
    two per-side mean variances: Var(gap) = std_buy^2/n_buy + std_sell^2/n_sell.
    When both sides are large (n > BIG_N) the CI is computed ANALYTICALLY as
    gap +/- Z95 * sqrt(Var(gap)) - exact-enough here and effectively free. When
    either side is small it falls back to a vectorized percentile bootstrap,
    capped at n_boot resamples and resampling the two sides independently, using
    the seeded rng. Returns (gap_point, lo, hi); gap_point is the plain point
    estimate buy_mean - sell_mean.
    """
    b = _finite(buy_vals)
    s = _finite(sell_vals)
    gap_point = (float(b.mean()) - float(s.mean())) if (b.size and s.size) else float("nan")
    if b.size == 0 or s.size == 0:
        return gap_point, float("nan"), float("nan")
    if b.size > BIG_N and s.size > BIG_N:
        var_gap = (b.var(ddof=1) / b.size) + (s.var(ddof=1) / s.size)
        half = Z95 * float(np.sqrt(var_gap))
        return gap_point, gap_point - half, gap_point + half
    bi = rng.integers(0, b.size, size=(n_boot, b.size))
    si = rng.integers(0, s.size, size=(n_boot, s.size))
    gaps = b[bi].mean(axis=1) - s[si].mean(axis=1)
    lo = float(np.percentile(gaps, CI_LO))
    hi = float(np.percentile(gaps, CI_HI))
    return gap_point, lo, hi


def _sign(x):
    """+1 / -1 / 0 sign of a possibly-NaN float (NaN -> 0)."""
    if not np.isfinite(x) or x == 0.0:
        return 0
    return 1 if x > 0 else -1


# -------------------- per-side / per-horizon stats --------------------
def _side_block(mo, notional, side_mask, rng):
    """Mean / median / weighted-mean / bootstrap-CI for one side, one horizon.

    mo, notional, side_mask are already restricted to the current coin slice.
    side_mask selects buy or sell rows. Only rows with a finite markout enter
    the mean/median/CI; the weighted mean additionally needs a finite, non-neg
    notional.
    """
    vals = mo[side_mask]
    wts = notional[side_mask]
    finite_vals = _finite(vals)
    lo, hi = _mean_ci(vals, rng)
    return {
        "n": int(finite_vals.size),
        "mean": _mean_or_nan(vals),
        "median": _median_or_nan(vals),
        "notional_weighted_mean": _wmean_or_nan(vals, wts),
        "mean_ci95": [lo, hi],
    }


def _within_day_control(mo, day, buy_mask, sell_mask, pooled_gap_sign):
    """Per-day buy mean, sell mean and gap, plus drift-control diagnostics.

    For each distinct day present in the slice this reports the buy mean, the
    sell mean, the gap and the per-day n on each side. Two summaries are derived:

      * sign stability: the fraction of days (weighted by usable days) whose gap
        sign matches the pooled gap sign. A drift confound flips the gap sign
        with the day's direction, so a low fraction is a drift signal.

      * de-meaned gap: for each day, subtract that day's overall (both-sides,
        notional-unweighted) mean markout from every row, then recompute the
        buy/sell gap. Pooling those per-day de-meaned rows removes a constant
        per-day drift. The pooled de-meaned gap is returned so the caller can
        compare it to the raw gap.
    """
    mo = np.asarray(mo, dtype=np.float64)
    day = np.asarray(day, dtype=np.int64)

    per_day = []
    days_sorted = np.unique(day)

    # accumulators for the pooled de-meaned gap (concatenate de-meaned rows)
    dem_buy_parts = []
    dem_sell_parts = []

    n_days_usable = 0
    n_days_sign_match = 0

    for d in days_sorted:
        d_mask = day == d
        d_buy = d_mask & buy_mask
        d_sell = d_mask & sell_mask

        buy_v = _finite(mo[d_buy])
        sell_v = _finite(mo[d_sell])

        buy_mean = float(buy_v.mean()) if buy_v.size else float("nan")
        sell_mean = float(sell_v.mean()) if sell_v.size else float("nan")
        gap = (buy_mean - sell_mean) if (buy_v.size and sell_v.size) else float("nan")

        # day overall mean across BOTH sides (the constant daily drift proxy)
        day_all = _finite(mo[d_mask])
        day_mean = float(day_all.mean()) if day_all.size else float("nan")

        # de-meaned per-side rows for this day (subtract the day's overall mean)
        if np.isfinite(day_mean):
            if buy_v.size:
                dem_buy_parts.append(buy_v - day_mean)
            if sell_v.size:
                dem_sell_parts.append(sell_v - day_mean)

        if buy_v.size and sell_v.size:
            n_days_usable += 1
            if pooled_gap_sign != 0 and _sign(gap) == pooled_gap_sign:
                n_days_sign_match += 1

        per_day.append({
            "day": int(d),
            "n_buy": int(buy_v.size),
            "n_sell": int(sell_v.size),
            "buy_mean": buy_mean,
            "sell_mean": sell_mean,
            "gap_buy_minus_sell": gap,
            "day_overall_mean": day_mean,
        })

    # pooled de-meaned gap (constant per-day drift removed)
    if dem_buy_parts and dem_sell_parts:
        dem_buy = np.concatenate(dem_buy_parts)
        dem_sell = np.concatenate(dem_sell_parts)
        demeaned_gap = float(dem_buy.mean()) - float(dem_sell.mean())
    else:
        demeaned_gap = float("nan")

    sign_match_frac = (n_days_sign_match / n_days_usable
                       if n_days_usable > 0 else float("nan"))

    return {
        "per_day": per_day,
        "n_days_usable": int(n_days_usable),
        "n_days_gap_sign_matches_pooled": int(n_days_sign_match),
        "gap_sign_stable_frac": sign_match_frac,
        "demeaned_gap_buy_minus_sell": demeaned_gap,
    }


def _verdict(raw_gap, demeaned_gap, sign_stable_frac):
    """One-line writeup flag: drift-artifact vs stable feature, for one horizon.

    Calls the asymmetry STABLE only when all three hold:
      * the de-meaned gap keeps the raw gap's sign,
      * the de-meaned gap keeps at least DEMEAN_SURVIVE_FRAC of the raw magnitude,
      * the per-day gap sign matches the pooled sign on at least
        DAY_SIGN_STABLE_FRAC of usable days.
    Otherwise it is flagged as a likely directional-drift artifact (or
    indeterminate when inputs are missing). Returns (label, reason).
    """
    if not np.isfinite(raw_gap) or not np.isfinite(demeaned_gap):
        return "indeterminate", "missing raw or de-meaned gap"

    raw_sign = _sign(raw_gap)
    dem_sign = _sign(demeaned_gap)
    survive_frac = (abs(demeaned_gap) / abs(raw_gap)) if raw_gap != 0 else float("nan")

    sign_kept = (raw_sign != 0 and dem_sign == raw_sign)
    mag_kept = np.isfinite(survive_frac) and survive_frac >= DEMEAN_SURVIVE_FRAC
    days_stable = np.isfinite(sign_stable_frac) and sign_stable_frac >= DAY_SIGN_STABLE_FRAC

    if sign_kept and mag_kept and days_stable:
        label = "stable_feature"
        reason = (
            f"survives de-meaning (keeps {survive_frac:.2f} of raw gap, same sign) "
            f"and per-day sign stable on {sign_stable_frac:.2f} of days"
        )
    else:
        label = "likely_drift_artifact"
        bits = []
        if not sign_kept:
            bits.append("gap sign flips/zeroes after de-meaning")
        if not mag_kept:
            frac_txt = f"{survive_frac:.2f}" if np.isfinite(survive_frac) else "n/a"
            bits.append(f"de-meaned gap keeps only {frac_txt} of raw (< {DEMEAN_SURVIVE_FRAC})")
        if not days_stable:
            frac_txt = f"{sign_stable_frac:.2f}" if np.isfinite(sign_stable_frac) else "n/a"
            bits.append(f"per-day gap sign matches pooled on only {frac_txt} of days")
        reason = "; ".join(bits)
    return label, reason


# -------------------- per-slice driver --------------------
def _slice_result(mo_cols, notional, day, taker_side, coin_mask, rng):
    """Full confound result block for one slice (a coin, or pooled = all rows).

    mo_cols is a dict horizon-name -> full 1-D markout array; everything is
    restricted to coin_mask here so the per-day control and bootstrap see only
    this slice's rows.
    """
    nt = np.asarray(notional, dtype=np.float64)[coin_mask]
    dy = np.asarray(day, dtype=np.int64)[coin_mask]
    ts = np.asarray(taker_side, dtype=np.int64)[coin_mask]

    buy_mask = ts == SIDE_BUY
    sell_mask = ts == SIDE_SELL

    block = {
        "n_rows": int(coin_mask.sum()),
        "n_buy": int(buy_mask.sum()),
        "n_sell": int(sell_mask.sum()),
        "horizons": {},
    }

    for hname in HORIZONS:
        mo = np.asarray(mo_cols[hname], dtype=np.float64)[coin_mask]

        buy_stats = _side_block(mo, nt, buy_mask, rng)
        sell_stats = _side_block(mo, nt, sell_mask, rng)

        gap_point, gap_lo, gap_hi = _gap_ci(mo[buy_mask], mo[sell_mask], rng)
        pooled_gap_sign = _sign(gap_point)

        within = _within_day_control(mo, dy, buy_mask, sell_mask, pooled_gap_sign)
        demeaned_gap = within["demeaned_gap_buy_minus_sell"]

        label, reason = _verdict(
            gap_point, demeaned_gap, within["gap_sign_stable_frac"]
        )

        block["horizons"][hname] = {
            "buy": buy_stats,
            "sell": sell_stats,
            "gap_buy_minus_sell": {
                "point": gap_point,
                "ci95": [gap_lo, gap_hi],
            },
            "within_day_control": within,
            "drift_neutralized": {
                "demeaned_gap_buy_minus_sell": demeaned_gap,
                "raw_gap_buy_minus_sell": gap_point,
                "demeaned_over_raw": (abs(demeaned_gap) / abs(gap_point)
                                      if (np.isfinite(demeaned_gap)
                                          and np.isfinite(gap_point)
                                          and gap_point != 0) else float("nan")),
            },
            "verdict": label,
            "verdict_reason": reason,
        }

    return block


# -------------------- main --------------------
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
    coin = data["coin"].astype(np.int64)
    day = data["day"].astype(np.int64)
    notional = data["notional"].astype(np.float64)
    taker_side = data["taker_side"].astype(np.int64)
    # keyed by the column name settings.py builds, so the dict key and the column it
    # holds are the same string by construction
    mo_cols = {name: data[name].astype(np.float64) for name in HORIZONS}

    # distinct days present, derived at runtime (NOT hardcoded), reported for
    # context on the within-day control.
    n_days = int(np.unique(day).size)

    rng = np.random.default_rng(SEED)

    # What every number in this file was computed under. horizon_s records the
    # headline window because that is the one a reader will compare against, but this
    # object SELECTS no window: the whole ladder is scored and the buy/sell gap is
    # reported at each rung. artifact.write is the single place that stamps it.
    settings_used = dict(
        h=H.HEADLINE_HORIZON_S, lens="print",
        master_seed=SEED,
        n_perm=None,
        n_boot=N_BOOT,
        rank_floor_fills=None,
        persistence_floor_fills=None,
        whale_drop_k=None,
        fdr_alpha=None,
        horizons_scored_s=list(H.LADDER_S),
        overrides_note=(
            "master_seed 20260619 not settings.MASTER_SEED 20260620; n_boot 2000 "
            "matches the declaration and is used only as the small-n fallback, "
            "since a group above the CLT threshold gets an analytic interval; no "
            "permutation test, no wallet floor, no whale-drop arm and no FDR "
            "family run here, so those declarations do not apply and are recorded "
            "as null rather than inherited; no window is selected -- every rung "
            "of the ladder is reported side by side, which is the object"),)

    results = {
        "_meta": {
            "object": "CONFOUND - directional-drift vs adverse-selection asymmetry",
            "window_days": n_days,
            "horizons_s": {H.headline_print_col(h): h for h in H.LADDER_S},
            "markout_sign": (
                "signed taker markout bps; positive = taker profited = maker "
                "adverse-selected"
            ),
            "side_codes": {"buy_aggressor": SIDE_BUY, "sell_aggressor": SIDE_SELL},
            "gap_definition": "buy_aggressor_mean minus sell_aggressor_mean (bps)",
            "ci_method": {
                "seed": SEED,
                "ci": "95%",
                "large_n": (
                    "analytic CLT: mean +/- 1.96*std/sqrt(n) for a side mean; "
                    "gap +/- 1.96*sqrt(std_buy^2/n_buy + std_sell^2/n_sell)"
                ),
                "small_n_fallback": (
                    f"vectorized percentile bootstrap, n_resamples={N_BOOT}, "
                    f"used only when a group has n <= {BIG_N}"
                ),
                "big_n_threshold": BIG_N,
            },
            "drift_neutralized_definition": (
                "per-day: subtract that day's overall (both-sides) mean markout "
                "from every row, then recompute the pooled buy/sell gap; removes a "
                "constant per-day drift"
            ),
            "verdict_thresholds": {
                "demean_survive_frac": DEMEAN_SURVIVE_FRAC,
                "day_sign_stable_frac": DAY_SIGN_STABLE_FRAC,
            },
            "verdict_note": VERDICT_NOTE,
        }
    }

    # per coin
    for code, name in COIN_CODES.items():
        mask = coin == code
        results[name] = _slice_result(
            mo_cols, notional, day, taker_side, mask, rng
        )

    # pooled (all rows)
    pooled_mask = np.ones(coin.shape, dtype=bool)
    results["pooled"] = _slice_result(
        mo_cols, notional, day, taker_side, pooled_mask, rng
    )

    # What the numbers cover. The unit of analysis is the FILL and no wallet floor
    # gates this file; the buy/sell split is a partition of the rows, not a filter.
    days = np.unique(day)
    scope = {
        "population": (f"{coin.size:,} rows of the trade-print panel, partitioned by "
                       "aggressor side; the unit of analysis is the fill, so no "
                       "wallet fill floor gates this file"),
        "window": (f"{days.size} days present in the input, day-of-month "
                   f"{days.min()}-{days.max()}; the within-day control demeans by "
                   "day, so the day count is what that control has to work with"),
        "coins": [COIN_CODES[c] for c in sorted(COIN_CODES)],
    }

    # The output name and directory still come from the module-level RESULTS_PATH, so
    # a caller that redirects that constant redirects the whole write, as before.
    artifact.write(os.path.basename(RESULTS_PATH), results,
                   script=__file__, inputs=[NPZ_PATH], scope=scope,
                   settings=settings_used, started=t0,
                   out_dir=os.path.dirname(RESULTS_PATH))

    _print_summary(results)


# -------------------- printed summary --------------------
def _fmt(x, nd=4):
    return f"{x:+.{nd}f}" if isinstance(x, float) and np.isfinite(x) else "n/a"


def _print_summary(results):
    n_days = results["_meta"]["window_days"]
    print("=" * 90)
    print("OBJECT CONFOUND - DIRECTIONAL-DRIFT vs ADVERSE-SELECTION ASYMMETRY")
    print("=" * 90)
    print(f"  Window: {n_days} resolved days. Gap = buy-aggressor mean minus "
          f"sell-aggressor mean (bps).")
    print("  Sign: positive markout = taker profited = maker adverse-selected.")
    print(f"  95% CI: analytic CLT for n>{BIG_N}, else seeded bootstrap "
          f"({N_BOOT} resamples, seed {SEED}).")
    print("-" * 90)

    for key in tuple(COIN_CODES.values()) + ("pooled",):
        r = results[key]
        print(f"\n  [{key}]  rows={r['n_rows']:,}  "
              f"buy={r['n_buy']:,}  sell={r['n_sell']:,}")
        header = (f"    {'horizon':>7} | {'buy mean':>10} | {'sell mean':>10} | "
                  f"{'raw gap':>10} | {'demean gap':>11} | {'day-sign':>8} | verdict")
        print(header)
        print("    " + "-" * (len(header) - 4))
        for hname in HORIZONS:
            h = r["horizons"][hname]
            buy_mean = h["buy"]["mean"]
            sell_mean = h["sell"]["mean"]
            raw_gap = h["gap_buy_minus_sell"]["point"]
            dem_gap = h["drift_neutralized"]["demeaned_gap_buy_minus_sell"]
            day_frac = h["within_day_control"]["gap_sign_stable_frac"]
            day_txt = f"{day_frac:.2f}" if np.isfinite(day_frac) else "n/a"
            print(f"    {hname:>7} | {_fmt(buy_mean):>10} | {_fmt(sell_mean):>10} | "
                  f"{_fmt(raw_gap):>10} | {_fmt(dem_gap):>11} | {day_txt:>8} | "
                  f"{h['verdict']}")

    print("\n" + "-" * 90)
    print("  Reminder: the verdict is a WRITEUP FLAG, not a test statistic.")
    print("  Signed markout cannot fully separate adverse selection from drift;")
    print("  this only checks survival of two drift controls (per-day sign + de-meaning).")
    print(f"  Windows: every rung of the ladder {list(H.LADDER_S)}s is reported and none")
    print(f"  is selected; the study's scoring window is {H.HEADLINE_HORIZON_S}s and the")
    print(f"  companion is {H.COMPANION_HORIZON_S}s, which is where the gap is largest.")
    print("-" * 90)
    print(f"  results -> {os.path.basename(RESULTS_PATH)}")
    print("=" * 90)


if __name__ == "__main__":
    main()
