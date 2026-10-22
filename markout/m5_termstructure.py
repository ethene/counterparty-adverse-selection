"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-19
References: Hyperliquid node-data S3 archive; Zenodo 18184441 (Albers et al. 2026).
"""

# ---------------------------------------------------------------------------
# OBJECT M5 — MARKOUT TERM-STRUCTURE (the toxicity curve)
#
# Each fill carries a signed TAKER markout at three horizons after the trade:
# 1s (mo1), 10s (mo10) and 60s (mo60), in basis points. Positive markout means
# the taker was right (the mid moved their way), so the MAKER was adversely
# selected by that horizon. Reading those three numbers as a curve over horizon
# tells us how toxicity accrues with time:
#
#   * a RISING curve (mo1 < mo10 < mo60) means the maker keeps bleeding as the
#     price continues to drift the taker's way -- classic permanent-impact /
#     informed-flow adverse selection that gets worse the longer you hold;
#   * a FALLING curve means early markout reverts (transient / liquidity-driven
#     pressure that mean-reverts, e.g. the taker paid for immediacy);
#   * a FLAT curve means the information is essentially impounded by 1s.
#
# This script reports the curve three ways:
#   (1) PER-COIN and POOLED simple mean and notional-weighted mean markout at
#       1s/10s/60s, the curve SHAPE label, and the 60s-minus-1s slope (bps).
#   (2) A PER-WALLET monotonicity statistic: among wallets with >= 50 trades,
#       the fraction whose own mean markout RISES monotonically with horizon
#       (mean_mo1 < mean_mo10 < mean_mo60), reported NEXT TO the fraction that
#       strictly FALLS (mean_mo1 > mean_mo10 > mean_mo60) and the 1/6 monotonic
#       null (a 3-point ordering is one of 6, so 1/6 = 16.7% of wallets rise by
#       chance). On this data strict-falling is MORE common than strict-rising
#       and rising is only ~1.4x the null, so the per-wallet ordering does NOT
#       establish that "rising markout is a property of individual
#       counterparties" -- that corroboration is dropped. The pooled simple-mean
#       rising curve is genuine and stands on its own; the per-wallet fractions
#       are reported descriptively, not as evidence for a per-counterparty law.
#
# On the weighting: the notional-weighted mean is NOT billed as the
# economically honest curve. Its steep slope is largely a low-1s-anchor
# artefact -- a handful of top-0.1%-notional fills (BTC top-0.1% = ~24% of
# dollars at a sharply negative mean 1s markout) drag the weighted 1s down and
# manufacture slope. We therefore also report a TRIMMED weighted curve (drop the
# top-0.1% of fills by notional) and a 99%-WINSORIZED weighted curve (clip
# markout to its 0.5/99.5 percentiles) so the reader can see how much of the raw
# weighted slope survives once the extreme anchors are tamed.
#
# numpy-only. Writes m5_termstructure_results.json and prints a small curve
# table. No plotting here.
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
from stats import safe_mean, weighted_mean

# ---------------------------------------------------------------------------
# Paths / config
# ---------------------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
# Located by panel_io rather than joined here, so the one place that knows where
# the markout panels live is the one place that has to change if they move.
NPZ_PATH = os.path.join(P.data_root(), "quickwin_markouts.npz")
OUT_PATH = os.path.join(HERE, "m5_termstructure_results.json")

# int8 code -> symbol. The map is a property of the FILE, not of the project
# (quickwin_markouts.npz carries {0, 1}, panel_markouts.npz carries {0, 1, 2}), so it
# is asked for by artifact name and never written out here.
COIN_NAME = H.coin_labels("quickwin")

# Horizon labels in ascending order, paired with their npz field names. Both halves
# are BUILT from the declared ladder rather than typed: the whole ladder IS the object
# of this file, so a column added to or removed from the ladder has to appear here,
# and a label can never state a window its column does not come from. The ascending
# order is load-bearing -- shape, slope and monotonicity all read first-to-last.
HORIZONS = tuple((H.headline_print_col(h), f"{h}s") for h in H.LADDER_S)
FIRST_LABEL = HORIZONS[0][1]     # the short end of the curve
LAST_LABEL = HORIZONS[-1][1]     # the long end; the slope is last minus first

# The slope keys name BOTH endpoints, so they are built from the ladder's own ends
# rather than typed. settings.field_name carries one window and cannot express a
# difference between two, which is why these are composed from the labels above.
_SLOPE_STEM = f"slope_{LAST_LABEL}_minus_{FIRST_LABEL}"
K_SLOPE_MEAN = f"{_SLOPE_STEM}_mean_bps"
K_SLOPE_WEIGHTED = f"{_SLOPE_STEM}_weighted_bps"
K_SLOPE_TRIMMED = f"{_SLOPE_STEM}_trimmed_weighted_bps"
K_SLOPE_WINSOR = f"{_SLOPE_STEM}_winsorized_weighted_bps"

# Minimum trades for a wallet to enter the per-wallet monotonicity statistic. This is
# the same 50 fills settings.RANK_FLOOR_FILLS declares, so the fingerprint this file
# stamps needs no override for the wallet floor; it is still a local literal and is
# owed the same migration as the other consumers of that setting.
MIN_TRADES_PER_WALLET = 50

# A curve is called "flat" when the 60s-minus-1s slope is within this many bps
# of zero; outside the band it is rising (positive) or falling (negative).
FLAT_SLOPE_BPS = 0.05

# A 3-point markout curve has 3! = 6 strict orderings, so under a null of random
# ordering 1/6 of wallets rise (and 1/6 fall) by chance. We print the per-wallet
# rising/falling fractions next to this null so neither is over-read.
MONOTONIC_NULL = 1.0 / 6.0

# Top fraction of fills by notional dropped to build the TRIMMED weighted curve;
# these few largest fills carry an outsized share of the dollar weight and set
# the raw weighted slope. 0.001 = top 0.1%.
TRIM_TOP_NOTIONAL_FRAC = 0.001

# Winsorize markout to this two-sided tail before the winsorized weighted curve
# (clip each horizon's markout to its 0.5 / 99.5 percentiles). 0.005 = 99% kept.
WINSOR_TAIL = 0.005


# ---------------------------------------------------------------------------
# Curve shape helpers
# ---------------------------------------------------------------------------
def shape_label(curve):
    """Classify a 3-point markout curve [m1, m10, m60] as rising/falling/flat.

    'rising' / 'falling' require the END (60s) to sit clearly above / below the
    START (1s) by more than FLAT_SLOPE_BPS; otherwise 'flat'. The label is
    driven by the 1s->60s span rather than strict step monotonicity, because the
    headline question is whether toxicity grows or reverts over the minute. Strict
    step monotonicity is reported separately as a boolean.
    """
    if any(not np.isfinite(x) for x in curve):
        return "n/a"
    m1, _m10, m60 = curve
    slope = m60 - m1
    if slope > FLAT_SLOPE_BPS:
        return "rising"
    if slope < -FLAT_SLOPE_BPS:
        return "falling"
    return "flat"


def is_strictly_rising(curve):
    """True iff m1 < m10 < m60 with all three finite (strict step monotonicity)."""
    if any(not np.isfinite(x) for x in curve):
        return False
    m1, m10, m60 = curve
    return bool(m1 < m10 < m60)


# safe_mean and weighted_mean come from stats.py, which m7_size.py imports as well.
# Both files carried a byte-identical copy of each. The two trimmed variants below
# stay here, because they are this file's argument about how much of the raw slope is
# a handful of the largest fills, and nothing else in the tree asks that.
def trimmed_weighted_mean(values, weights, drop_top_frac):
    """Notional-weighted mean after dropping the top `drop_top_frac` of rows by
    weight (notional). Built to show how much of the raw weighted slope is a
    handful of the largest fills. The trim mask is computed on the full notional
    vector for this slice so the same fills are removed at every horizon.
    """
    v = np.asarray(values, dtype=np.float64)
    w = np.asarray(weights, dtype=np.float64)
    n = w.size
    if n == 0:
        return float("nan")
    k = int(np.floor(n * drop_top_frac))
    if k <= 0:
        return weighted_mean(v, w)
    # threshold = smallest notional inside the dropped top-k set; keep rows
    # strictly below it (ties at the threshold are dropped with the top set).
    order = np.argsort(w)
    thresh = w[order[-k]]
    keep = w < thresh
    if not np.any(keep):
        return float("nan")
    return weighted_mean(v[keep], w[keep])


def winsorized_weighted_mean(values, weights, tail):
    """Notional-weighted mean after winsorizing the MARKOUT (not the weight) to
    its [tail, 1-tail] percentiles. Clipping the extreme markout values tames the
    low-1s anchor without discarding the dollars: every fill keeps its notional
    weight but a few outlier markouts cannot set the curve on their own.
    """
    v = np.asarray(values, dtype=np.float64)
    w = np.asarray(weights, dtype=np.float64)
    finite = np.isfinite(v)
    if not np.any(finite):
        return float("nan")
    lo = np.quantile(v[finite], tail)
    hi = np.quantile(v[finite], 1.0 - tail)
    vc = np.clip(v, lo, hi)
    return weighted_mean(vc, w)


# ---------------------------------------------------------------------------
# (1) per-slice curve (simple + notional-weighted)
# ---------------------------------------------------------------------------
def curve_block(mo, notional):
    """Mean and notional-weighted-mean markout curve for one slice.

    mo       : dict horizon-field -> 1-D markout array (bps), e.g. mo['mo60'].
    notional : 1-D notional array aligned with the markout arrays.

    Returns the two curves (as horizon-keyed dicts and as ordered lists), each
    curve's shape label, strict-monotonicity flag, and 60s-minus-1s slope.
    """
    n_trades = int(notional.size)

    mean_curve = {lbl: safe_mean(mo[fld]) for fld, lbl in HORIZONS}
    wmean_curve = {lbl: weighted_mean(mo[fld], notional) for fld, lbl in HORIZONS}
    # Same notional-weighted curve, but with the extreme anchors tamed two ways:
    # (a) drop the top-0.1% fills by notional, (b) 99%-winsorize the markout.
    trim_curve = {
        lbl: trimmed_weighted_mean(mo[fld], notional, TRIM_TOP_NOTIONAL_FRAC)
        for fld, lbl in HORIZONS
    }
    winsor_curve = {
        lbl: winsorized_weighted_mean(mo[fld], notional, WINSOR_TAIL)
        for fld, lbl in HORIZONS
    }

    mean_list = [mean_curve[lbl] for _fld, lbl in HORIZONS]
    wmean_list = [wmean_curve[lbl] for _fld, lbl in HORIZONS]
    trim_list = [trim_curve[lbl] for _fld, lbl in HORIZONS]
    winsor_list = [winsor_curve[lbl] for _fld, lbl in HORIZONS]

    def slope(curve_list):
        a, c = curve_list[0], curve_list[-1]   # 1s and 60s
        return float(c - a) if (np.isfinite(a) and np.isfinite(c)) else float("nan")

    return {
        "n_trades": n_trades,
        "mean_markout_bps": mean_curve,
        "weighted_mean_markout_bps": wmean_curve,
        "trimmed_weighted_mean_markout_bps": trim_curve,
        "winsorized_weighted_mean_markout_bps": winsor_curve,
        "trim_top_notional_frac": TRIM_TOP_NOTIONAL_FRAC,
        "winsor_tail": WINSOR_TAIL,
        "mean_curve_shape": shape_label(mean_list),
        "weighted_curve_shape": shape_label(wmean_list),
        "trimmed_weighted_curve_shape": shape_label(trim_list),
        "winsorized_weighted_curve_shape": shape_label(winsor_list),
        "mean_strictly_rising": is_strictly_rising(mean_list),
        "weighted_strictly_rising": is_strictly_rising(wmean_list),
        K_SLOPE_MEAN: slope(mean_list),
        K_SLOPE_WEIGHTED: slope(wmean_list),
        K_SLOPE_TRIMMED: slope(trim_list),
        K_SLOPE_WINSOR: slope(winsor_list),
    }


# ---------------------------------------------------------------------------
# (2) per-wallet monotonicity
# ---------------------------------------------------------------------------
def per_wallet_monotonic_fraction(taker_id, mo1, mo10, mo60):
    """Among wallets with >= MIN_TRADES_PER_WALLET fills, the fraction whose mean
    markout strictly RISES with horizon (mean_mo1 < mean_mo10 < mean_mo60) AND
    the fraction that strictly FALLS (mean_mo1 > mean_mo10 > mean_mo60), reported
    next to the 1/6 monotonic null.

    Both fractions are returned because the rising one alone was being read as
    "rising markout is a property of individual counterparties" -- but on this
    data strict-falling is MORE common and rising sits only modestly above the
    1/6 chance level, so neither ordering carries that claim. The two fractions
    are descriptive.

    Per-wallet means are built with grouped sums divided by per-wallet finite
    counts at EACH horizon independently, so a row with a missing 60s markout
    still contributes to that wallet's 1s and 10s means. A wallet qualifies for
    the denominator on its TOTAL fill count (rows in this slice), matching the
    spec's ">= 50 trades" wording; wallets that end up with a NaN mean at any
    horizon are counted as neither rising nor falling (they cannot satisfy a
    strict inequality).
    """
    n = taker_id.size
    if n == 0:
        return {
            "n_wallets_ge_min": 0,
            "min_trades": MIN_TRADES_PER_WALLET,
            "monotonic_null": MONOTONIC_NULL,
            "frac_monotonic_rising": float("nan"),
            "n_monotonic_rising": 0,
            "frac_monotonic_falling": float("nan"),
            "n_monotonic_falling": 0,
        }

    uniq, inv = np.unique(taker_id, return_inverse=True)
    nuniq = uniq.size

    # total fills per wallet (the ">= 50 trades" gate uses the row count)
    fills = np.zeros(nuniq, dtype=np.int64)
    np.add.at(fills, inv, 1)

    def wallet_mean(mo):
        v = np.asarray(mo, dtype=np.float64)
        finite = np.isfinite(v)
        ssum = np.zeros(nuniq, dtype=np.float64)
        cnt = np.zeros(nuniq, dtype=np.float64)
        np.add.at(ssum, inv[finite], v[finite])
        np.add.at(cnt, inv[finite], 1.0)
        out = np.full(nuniq, np.nan, dtype=np.float64)
        nz = cnt > 0
        out[nz] = ssum[nz] / cnt[nz]
        return out

    m1 = wallet_mean(mo1)
    m10 = wallet_mean(mo10)
    m60 = wallet_mean(mo60)

    qualifies = fills >= MIN_TRADES_PER_WALLET
    n_q = int(qualifies.sum())
    if n_q == 0:
        return {
            "n_wallets_ge_min": 0,
            "min_trades": MIN_TRADES_PER_WALLET,
            "monotonic_null": MONOTONIC_NULL,
            "frac_monotonic_rising": float("nan"),
            "n_monotonic_rising": 0,
            "frac_monotonic_falling": float("nan"),
            "n_monotonic_falling": 0,
        }

    # strictly rising / strictly falling AND all three means finite, restricted
    # to qualifying wallets
    all_finite = np.isfinite(m1) & np.isfinite(m10) & np.isfinite(m60)
    rising = all_finite & (m1 < m10) & (m10 < m60)
    falling = all_finite & (m1 > m10) & (m10 > m60)
    n_rise = int(np.sum(rising & qualifies))
    n_fall = int(np.sum(falling & qualifies))

    return {
        "n_wallets_ge_min": n_q,
        "min_trades": MIN_TRADES_PER_WALLET,
        "monotonic_null": MONOTONIC_NULL,
        "frac_monotonic_rising": float(n_rise / n_q),
        "n_monotonic_rising": n_rise,
        "frac_monotonic_falling": float(n_fall / n_q),
        "n_monotonic_falling": n_fall,
    }


# ---------------------------------------------------------------------------
# Per-coin / pooled driver
# ---------------------------------------------------------------------------
def analyse_slice(taker_id, mo1, mo10, mo60, notional):
    """Full term-structure result dict for one slice (coin or pooled)."""
    mo = dict(zip((fld for fld, _lbl in HORIZONS), (mo1, mo10, mo60)))
    return {
        "curve": curve_block(mo, notional),
        "per_wallet_monotonicity": per_wallet_monotonic_fraction(
            taker_id, mo1, mo10, mo60),
    }


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
    # The three rungs, read in the ladder's own order and never by a typed column.
    mo1, mo10, mo60 = (data[fld].astype(np.float64) for fld, _lbl in HORIZONS)
    notional = data["notional"].astype(np.float64)
    # Read only to state the window in the artifact's scope; it enters no computation.
    # It is filtered with everything else so the window describes the rows that
    # actually reached the curve rather than the rows the input happened to hold.
    day = data["day"].astype(np.int64)

    # Keep rows usable for the curve: at least one finite horizon and a finite,
    # non-negative notional. A row missing a single horizon still informs the
    # other horizons (per-horizon means drop NaNs independently), so we do NOT
    # require all three markouts to be present.
    any_horizon = np.isfinite(mo1) | np.isfinite(mo10) | np.isfinite(mo60)
    valid = any_horizon & np.isfinite(notional) & (notional >= 0)
    day = day[valid]
    taker_id = taker_id[valid]
    coin = coin[valid]
    mo1 = mo1[valid]
    mo10 = mo10[valid]
    mo60 = mo60[valid]
    notional = notional[valid]

    results = {
        "_meta": {
            "object": "M5 markout term-structure (toxicity curve over horizon)",
            "horizons": [lbl for _fld, lbl in HORIZONS],
            "markout_sign": ("signed taker markout in bps; positive = taker "
                             "profited = maker adversely selected"),
            "shape_rule": (f"rising/falling if |{LAST_LABEL}-{FIRST_LABEL} slope| > "
                           f"{FLAT_SLOPE_BPS} bps, else flat"),
            "min_trades_per_wallet": MIN_TRADES_PER_WALLET,
            "monotonic_null": MONOTONIC_NULL,
            "weighted_curve_caveat": (
                "raw notional-weighted slope is largely a low-1s-anchor "
                "artefact of the top-0.1%-notional fills; trimmed (drop top "
                f"{TRIM_TOP_NOTIONAL_FRAC:.1%} by notional) and "
                f"{1 - 2 * WINSOR_TAIL:.0%}-winsorized weighted curves are "
                "reported alongside it and are NOT billed as the single honest "
                "curve"),
            "per_wallet_caveat": (
                "rising and falling per-wallet fractions are descriptive only; "
                "strict-falling exceeds strict-rising on this data, so the "
                "ordering does not establish a per-counterparty rising property"),
            "n_trades_valid": int(taker_id.size),
        }
    }

    results["_meta"]["horizons_reported_s"] = list(H.LADDER_S)
    results["_meta"]["slope_endpoints_s"] = [H.LADDER_S[0], H.LADDER_S[-1]]

    # What the numbers cover, built from the rows this run kept rather than from a
    # description of them. The input name, the fingerprint and the population note
    # were written into _meta by hand here; artifact.write records all three in one
    # shape, and keeping them here as well would give one record two homes.
    days = np.unique(day)
    scope = {
        "population": (f"{taker_id.size:,} rows of the trade-print panel with at "
                       "least one finite rung and a finite non-negative notional; "
                       f"the per-wallet monotonicity statistic gates at "
                       f"{MIN_TRADES_PER_WALLET} fills, and no randomness or "
                       "resampling enters this file"),
        "window": (f"{days.size} days present in the input, day-of-month "
                   f"{days.min()}-{days.max()}; the calendar dates of the window "
                   "are declared by its producer, build_quickwin_markouts.py"),
        "coins": [COIN_NAME[c] for c in sorted(COIN_NAME)],
    }

    # ---- per coin ----
    for code, name in COIN_NAME.items():
        sel = coin == code
        results[name] = analyse_slice(
            taker_id[sel], mo1[sel], mo10[sel], mo60[sel], notional[sel])

    # ---- pooled (all coins) ----
    results["pooled"] = analyse_slice(taker_id, mo1, mo10, mo60, notional)

    # The output name and directory still come from the module-level OUT_PATH, so a
    # caller that redirects that constant redirects the whole write, as before. This
    # file reports the WHOLE ladder, so the stamped window is the declared headline
    # and the ladder is named beside it; the shape and slope statistics read the two
    # ends of that ladder, which the endpoint field states. The per-wallet
    # monotonicity gate is the stated wallet floor, and no seed or resampling budget
    # enters this file.
    artifact.write(os.path.basename(OUT_PATH), results,
                   script=__file__, inputs=[NPZ_PATH], scope=scope,
                   settings={"h": H.HEADLINE_HORIZON_S, "lens": "print",
                             "rank_floor_fills": MIN_TRADES_PER_WALLET},
                   started=t0, out_dir=os.path.dirname(OUT_PATH))

    print_summary(results)
    print(f"\n[m5] wrote {os.path.basename(OUT_PATH)}")


# ---------------------------------------------------------------------------
# Printed summary
# ---------------------------------------------------------------------------
def _fmt(x, nd=3):
    return f"{x:.{nd}f}" if isinstance(x, float) and np.isfinite(x) else "n/a"


def print_summary(results):
    print("=" * 78)
    print("M5 — MARKOUT TERM-STRUCTURE (signed taker markout, bps; +ve = maker adverse)")
    print("=" * 78)
    print(f"valid trades : {results['_meta']['n_trades_valid']:,}")
    print("Rising curve  => toxicity accrues over the minute (informed flow).")
    print("Falling curve => early markout reverts (transient / liquidity).\n")

    # ---- (1) simple mean curve -- the headline curve ----
    _labels = [lbl for _fld, lbl in HORIZONS]
    _slope_head = f"slope{LAST_LABEL[:-1]}-{FIRST_LABEL[:-1]}"
    print("(1) MARKOUT CURVE  [simple mean, bps -- the headline curve]")
    h1 = (f"{'slice':<8} " + " ".join(f"{lbl:>9}" for lbl in _labels)
          + f" {_slope_head:>10} {'shape':>9}")
    print(h1)
    print("-" * len(h1))
    for key in ("BTC", "ETH", "pooled"):
        if key not in results:
            continue
        c = results[key]["curve"]
        m = c["mean_markout_bps"]
        print(f"{key:<8} " + " ".join(f"{_fmt(m[lbl]):>9}" for lbl in _labels)
              + f" {_fmt(c[K_SLOPE_MEAN]):>10} "
              f"{c['mean_curve_shape']:>9}")

    # ---- (1b) notional-weighted: raw vs trimmed vs winsorized ----
    print("\n(1b) NOTIONAL-WEIGHTED CURVE  [bps] -- raw slope is a low-1s anchor "
          "artefact;")
    print("     trimmed (drop top-0.1% notional) and 99%-winsorized shown next "
          "to it.")
    h1b = (f"{'slice':<8} {'variant':>10} "
           + " ".join(f"{lbl:>9}" for lbl in _labels)
           + f" {_slope_head:>10} {'shape':>9}")
    print(h1b)
    print("-" * len(h1b))
    for key in ("BTC", "ETH", "pooled"):
        if key not in results:
            continue
        c = results[key]["curve"]
        for variant, ck, sk, shk in (
            ("raw", "weighted_mean_markout_bps",
             K_SLOPE_WEIGHTED, "weighted_curve_shape"),
            ("trim0.1%", "trimmed_weighted_mean_markout_bps",
             K_SLOPE_TRIMMED, "trimmed_weighted_curve_shape"),
            ("winsor99", "winsorized_weighted_mean_markout_bps",
             K_SLOPE_WINSOR, "winsorized_weighted_curve_shape"),
        ):
            w = c[ck]
            print(f"{key:<8} {variant:>10} "
                  + " ".join(f"{_fmt(w[lbl]):>9}" for lbl in _labels)
                  + f" {_fmt(c[sk]):>10} {c[shk]:>9}")

    # ---- (2) per-wallet monotonicity: rising vs falling vs null ----
    _rise = "<".join(_labels)
    _fall = ">".join(_labels)
    print("\n(2) PER-WALLET MONOTONICITY  [wallets with >= "
          f"{MIN_TRADES_PER_WALLET} trades; strict {_rise} rising vs "
          f"{_fall} falling]")
    print(f"    null = 1/6 = {MONOTONIC_NULL:.3f} (one of six orderings). "
          "Falling > rising here, so this does NOT show a per-counterparty "
          "rising property.")
    h2 = (f"{'slice':<8} {'wallets>=min':>13} {'frac_rising':>12} "
          f"{'frac_falling':>13} {'null(1/6)':>10}")
    print(h2)
    print("-" * len(h2))
    for key in ("BTC", "ETH", "pooled"):
        if key not in results:
            continue
        pw = results[key]["per_wallet_monotonicity"]
        print(f"{key:<8} {pw['n_wallets_ge_min']:>13,} "
              f"{_fmt(pw['frac_monotonic_rising']):>12} "
              f"{_fmt(pw['frac_monotonic_falling']):>13} "
              f"{_fmt(pw['monotonic_null']):>10}")
    print("=" * 78)


if __name__ == "__main__":
    main()
