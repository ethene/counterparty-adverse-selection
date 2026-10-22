"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-19
References: Hyperliquid node-data S3 archive; Zenodo 18184441 (Albers et al. 2026).
"""

# ---------------------------------------------------------------------------
# OBJECT M7 — SIZE STRUCTURE OF TOXICITY
#
# Question: is maker adverse selection concentrated in BIG fills or SMALL fills?
# If toxicity rises with trade size, the informed counterparties are trading in
# size (a quoting rule should widen / skew most against large incoming orders);
# if it is flat or falls with size, the toxic flow is in the small fills and a
# size-based defence buys little.
#
# Each fill carries a signed TAKER markout in basis points at 10s (mo10) and 60s
# (mo60); positive markout means the taker was right, i.e. the MAKER was
# adversely selected. We bucket fills into NOTIONAL DECILES (computed PER COIN,
# so BTC and ETH each get their own size cut and the cross-asset notional gap
# does not smear the deciles) and report, per decile:
#     the mean markout at each window, trade count, and total notional.
# The leading read of THIS file is the gradient of the mean 60 s markout from decile
# 1 (smallest) to decile 10 (largest), plus a strict-monotonicity check of that
# gradient. The 60 s window is the COMPANION, not the window settings.py declares as
# the study headline; every key that carries it says 60s, and the results file stamps
# the difference as an explicit override so the two cannot be confused.
#
# We also split off the TOP 1% of fills by notional (per coin) and compare their
# mean mo60 to the rest, because the biggest fills can behave very differently
# from the bulk of the top decile. Two cautions go with that split:
#   * mo60 RISES through the deciles (D10 mean mo60 clearly exceeds D1), so
#     toxicity grows with size across the bulk of the distribution; the only dip
#     is confined to the EXTREME top 1%, and only on an EQUAL-weight basis.
#   * Dollar-weighted, that top-1% dip largely collapses: a handful of the very
#     largest fills inside the top 1% carry most of its notional and are not the
#     low-markout ones, so we report BOTH the equal-weight and the
#     notional-weighted top-1% markout and do NOT let "big fills are safe"
#     generalize from the equal-weight number.
#
# Bucketing detail: deciles are cut on notional quantile EDGES via
# np.quantile(...)/np.searchsorted, then each fill is assigned to the decile
# whose edges bracket it. Ties at an edge (common when many fills share a round
# size) are all sent to the same bucket, so adjacent decile counts can be uneven;
# that is reported honestly via the per-decile n rather than forced to be equal.
#
# numpy-only. Writes m7_size_results.json and prints the decile table. No
# plotting here.
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
OUT_PATH = os.path.join(HERE, "m7_size_results.json")

# int8 code -> symbol. The map is a property of the FILE, not of the project
# (quickwin_markouts.npz carries {0, 1}, panel_markouts.npz carries {0, 1, 2}), so it
# is asked for by artifact name and never written out here.
COIN_NAME = H.coin_labels("quickwin")

# THE DECILES OF THIS FILE ARE CUT ON NOTIONAL AND ON NOTHING ELSE, and the names say
# so because the tree also carries a decile cut on counterparty markout, which is a
# different object with a different population: this one buckets FILLS by trade size,
# that one selects COUNTERPARTIES by adverse-selection score. Bare "decile" was doing
# duty for both, so the size buckets are spelled out here and the word is left to mean
# one thing.
N_NOTIONAL_DECILES = 10          # ten notional buckets
TOP_PCT = 0.01          # top 1% of fills by notional, reported separately

# Result keys are BUILT from the declared windows so a key cannot keep a stale window
# over a new number. The gradient and the top-1% split are read on the COMPANION
# window, which is why every one of their keys says 60s out loud: this file's leading
# statistic is deliberately not on the declared headline window, and the fingerprint
# records that as an explicit difference rather than leaving it to be inferred.
HEAD_S = H.HEADLINE_HORIZON_S
COMP_S = H.COMPANION_HORIZON_S
K_MEAN_HEAD = H.field_name("mean_markout_bps", HEAD_S)
K_MEAN_COMP = H.field_name("mean_markout_bps", COMP_S)
K_GRADIENT = H.field_name("markout_gradient", COMP_S)
K_TOP_MEAN = H.field_name("top_mean_markout_bps", COMP_S)
K_REST_MEAN = H.field_name("rest_mean_markout_bps", COMP_S)
K_TOP_MEAN_HEAD = H.field_name("top_mean_markout_bps", HEAD_S)
K_REST_MEAN_HEAD = H.field_name("rest_mean_markout_bps", HEAD_S)
K_TOP_WMEAN = H.field_name("top_wmean_markout_bps", COMP_S)
K_REST_WMEAN = H.field_name("rest_wmean_markout_bps", COMP_S)
K_TOP_MINUS_REST = H.field_name("top_minus_rest_markout_bps", COMP_S)
K_TOP_MINUS_REST_W = H.field_name("top_minus_rest_wmean_markout_bps", COMP_S)


# ---------------------------------------------------------------------------
# Bucketing
# ---------------------------------------------------------------------------
def notional_decile_index(notional):
    """Assign each FILL to a notional decile 0..N_NOTIONAL_DECILES-1 (0 = smallest).

    The unit bucketed here is one fill and the quantity cut on is its notional. That
    is worth saying, because the word decile is also used elsewhere in this repository
    for a cut over COUNTERPARTIES ordered by adverse-selection score, and the two share
    no unit, no population and no ordering quantity.

    Edges are the N_NOTIONAL_DECILES-1 interior quantiles of the notional vector. A
    fill is placed by searchsorted on those edges, so equal-notional ties land in the
    same bucket and the boundary fills go to the upper bucket. The result is clipped
    into [0, N_NOTIONAL_DECILES-1]. Returns an int array aligned with notional.
    """
    n = notional.size
    if n == 0:
        return np.empty(0, dtype=np.int64)
    qs = np.linspace(0.0, 1.0, N_NOTIONAL_DECILES + 1)[1:-1]   # interior cut points
    edges = np.quantile(notional, qs)
    idx = np.searchsorted(edges, notional, side="right")
    return np.clip(idx, 0, N_NOTIONAL_DECILES - 1).astype(np.int64)


# safe_mean and weighted_mean come from stats.py, which m5_termstructure.py imports as
# well. Both files carried a byte-identical copy of each. The weighted one is what makes
# the dollar-weighted top-1% markout differ from the equal-weight one, so it is worth
# knowing that the two files were reading the same definition rather than hoping.
def gradient_is_monotone(values):
    """Describe the decile-to-mean-markout gradient on the companion window.

    Returns a dict with strict-increasing / strict-decreasing flags (computed on
    the finite leading-to-trailing sequence) and the last-minus-first span. A
    strictly increasing sequence means toxicity grows with size; strictly
    decreasing means it concentrates in the small fills.
    """
    v = np.asarray(values, dtype=np.float64)
    finite = np.isfinite(v)
    vf = v[finite]
    if vf.size < 2:
        return {
            "strictly_increasing": False,
            "strictly_decreasing": False,
            "monotone": False,
            "direction": "n/a",
            "last_minus_first_bps": float("nan"),
        }
    diffs = np.diff(vf)
    inc = bool(np.all(diffs > 0))
    dec = bool(np.all(diffs < 0))
    direction = ("increasing" if inc else "decreasing" if dec else "non-monotone")
    return {
        "strictly_increasing": inc,
        "strictly_decreasing": dec,
        "monotone": inc or dec,
        "direction": direction,
        "last_minus_first_bps": float(vf[-1] - vf[0]),
    }


# ---------------------------------------------------------------------------
# Per-coin / pooled driver
# ---------------------------------------------------------------------------
def analyse_slice(notional, mo10, mo60):
    """Decile table + top-1%-vs-rest split for one slice.

    notional / mo10 / mo60 are aligned 1-D arrays already restricted to the
    slice (one coin, or all coins pooled). Deciles are cut on THIS slice's
    notional, so a per-coin call gets per-coin deciles.
    """
    n_trades = int(notional.size)
    if n_trades == 0:
        return {
            "n_trades": 0,
            "deciles": [],
            K_GRADIENT: gradient_is_monotone([]),
            "top1pct_vs_rest": {},
        }

    dec = notional_decile_index(notional)

    deciles = []
    mean_mo60_by_decile = []
    for d in range(N_NOTIONAL_DECILES):
        m = dec == d
        n_d = int(m.sum())
        mm60 = safe_mean(mo60[m])
        mm10 = safe_mean(mo10[m])
        deciles.append({
            "decile": d + 1,                         # 1 = smallest, 10 = largest
            "n": n_d,
            "total_notional": float(notional[m].sum()),
            "min_notional": (float(notional[m].min()) if n_d else float("nan")),
            "max_notional": (float(notional[m].max()) if n_d else float("nan")),
            K_MEAN_HEAD: mm10,
            K_MEAN_COMP: mm60,
        })
        mean_mo60_by_decile.append(mm60)

    grad = gradient_is_monotone(mean_mo60_by_decile)

    # --- top 1% by notional vs the rest ---
    k = max(1, int(np.ceil(n_trades * TOP_PCT)))
    order = np.argsort(notional)            # ascending
    top_idx = order[-k:]                    # k largest fills
    rest_idx = order[:-k] if k < n_trades else np.empty(0, dtype=order.dtype)
    top_thresh = float(notional[order[-k]]) if k <= n_trades else float("nan")

    top_block = {
        "pct": TOP_PCT,
        "n_top": int(top_idx.size),
        "n_rest": int(rest_idx.size),
        "notional_threshold": top_thresh,     # smallest notional inside the top set
        # equal-weight (each fill counts once)
        K_TOP_MEAN: safe_mean(mo60[top_idx]),
        K_REST_MEAN: safe_mean(mo60[rest_idx]),
        K_TOP_MEAN_HEAD: safe_mean(mo10[top_idx]),
        K_REST_MEAN_HEAD: safe_mean(mo10[rest_idx]),
        # notional-weighted (each fill counts by its dollars) -- inside the top
        # 1% the largest fills dominate the dollars and are not the low-markout
        # ones, so this can be far above the equal-weight number
        K_TOP_WMEAN: weighted_mean(mo60[top_idx], notional[top_idx]),
        K_REST_WMEAN: weighted_mean(mo60[rest_idx], notional[rest_idx]),
        "top_total_notional": float(notional[top_idx].sum()),
        "rest_total_notional": (float(notional[rest_idx].sum())
                                if rest_idx.size else 0.0),
    }
    tt = top_block[K_TOP_MEAN]
    rr = top_block[K_REST_MEAN]
    top_block[K_TOP_MINUS_REST] = (
        float(tt - rr) if (np.isfinite(tt) and np.isfinite(rr)) else float("nan"))
    # The same top-minus-rest gap, dollar-weighted. Compared to the equal-weight
    # gap this shows how much of the "big fills look safe" dip survives once the
    # largest fills inside the top 1% carry their proper weight.
    twt = top_block[K_TOP_WMEAN]
    rwt = top_block[K_REST_WMEAN]
    top_block[K_TOP_MINUS_REST_W] = (
        float(twt - rwt) if (np.isfinite(twt) and np.isfinite(rwt))
        else float("nan"))

    return {
        "n_trades": n_trades,
        "deciles": deciles,
        K_GRADIENT: grad,
        "top1pct_vs_rest": top_block,
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
    coin = data["coin"].astype(np.int8)
    mo10 = data[H.headline_print_col()].astype(np.float64)
    mo60 = data[H.companion_print_col()].astype(np.float64)
    notional = data["notional"].astype(np.float64)
    # Read only to state the window in the artifact's scope; it enters no computation.
    # It is filtered with everything else so the window describes the rows that
    # actually reached the deciles rather than the rows the input happened to hold.
    day = data["day"].astype(np.int64)

    # Keep rows with a usable companion-window markout and a positive notional: the
    # deciles are a notional cut (a zero / negative notional cannot be bucketed) and
    # the leading read is that window's mean per bucket, so a row missing it carries
    # no signal.
    valid = (np.isfinite(mo60) & np.isfinite(notional) & (notional > 0))
    day = day[valid]
    coin = coin[valid]
    mo10 = mo10[valid]
    mo60 = mo60[valid]
    notional = notional[valid]

    results = {
        "_meta": {
            "object": "M7 size structure of toxicity (notional deciles)",
            "markout_sign": ("signed taker markout in bps; positive = taker "
                             "profited = maker adversely selected"),
            "n_deciles": N_NOTIONAL_DECILES,
            "decile_basis": "per-coin notional quantiles (pooled uses pooled "
                            "notional)",
            "top_pct": TOP_PCT,
            "top1pct_caveat": (
                f"the {COMP_S}s markout rises across deciles (D10 > D1), so "
                "toxicity grows with size; the low-markout dip is confined to the "
                "extreme top 1% on an EQUAL-weight basis only -- dollar-weighted "
                "the top-1% gap collapses, so report both and do not generalize "
                "'big fills are safe'"),
            "row_filter": f"finite {COMP_S}s markout and notional > 0",
            "n_trades_valid": int(notional.size),
        }
    }

    # What the numbers cover, built from the rows this run kept rather than from a
    # description of them. The input name and the fingerprint were written into _meta
    # by hand here; artifact.write records both in one shape, and keeping them here as
    # well would give one record two homes.
    days = np.unique(day)
    scope = {
        "population": (f"{notional.size:,} rows of the trade-print panel with a "
                       f"finite {COMP_S}s markout and a notional above zero; the "
                       "unit of analysis is the fill, so no wallet floor, no seed "
                       "and no resampling enter this file"),
        "window": (f"{days.size} days present in the input, day-of-month "
                   f"{days.min()}-{days.max()}; the calendar dates of the window "
                   "are declared by its producer, build_quickwin_markouts.py"),
        "coins": [COIN_NAME[c] for c in sorted(COIN_NAME)],
    }
    results["_meta"]["horizon_note"] = (
        f"the decile table reports both windows ({HEAD_S}s and {COMP_S}s); the "
        f"gradient, its monotonicity flag and the top-1%-vs-rest cells are on the "
        f"{COMP_S}s companion window, which is why every one of their keys names it")

    # ---- per coin (deciles cut per coin) ----
    for code, name in COIN_NAME.items():
        sel = coin == code
        results[name] = analyse_slice(notional[sel], mo10[sel], mo60[sel])

    # ---- pooled (deciles cut on pooled notional) ----
    results["pooled"] = analyse_slice(notional, mo10, mo60)

    # The output name and directory still come from the module-level OUT_PATH, so a
    # caller that redirects that constant redirects the whole write, as before. The
    # gradient, the monotonicity check and the top-1% split are all read on the
    # COMPANION window, so the stamped window is that one and is_headline_horizon
    # comes back false; the declared headline stays in the block beside it.
    artifact.write(os.path.basename(OUT_PATH), results,
                   script=__file__, inputs=[NPZ_PATH], scope=scope,
                   settings={"h": COMP_S, "lens": "print"}, started=t0,
                   out_dir=os.path.dirname(OUT_PATH))

    print_summary(results)
    print(f"\n[m7] wrote {os.path.basename(OUT_PATH)}")


# ---------------------------------------------------------------------------
# Printed summary
# ---------------------------------------------------------------------------
def _fmt(x, nd=3):
    return f"{x:.{nd}f}" if isinstance(x, float) and np.isfinite(x) else "n/a"


def _fmt_notional(x):
    """Compact notional formatting (k / M) for the printed table."""
    if not (isinstance(x, float) and np.isfinite(x)):
        return "n/a"
    ax = abs(x)
    if ax >= 1e9:
        return f"{x / 1e9:.2f}B"
    if ax >= 1e6:
        return f"{x / 1e6:.2f}M"
    if ax >= 1e3:
        return f"{x / 1e3:.2f}k"
    return f"{x:.0f}"


def print_summary(results):
    print("=" * 84)
    print("M7 — SIZE STRUCTURE OF TOXICITY (signed taker markout, bps; +ve = maker adverse)")
    print("=" * 84)
    print(f"valid trades : {results['_meta']['n_trades_valid']:,}")
    print("Deciles are cut on NOTIONAL (1 = smallest fills, 10 = largest), per coin.")
    print(f"Rising {COMP_S}s markout across deciles => toxicity concentrated in "
          "BIG fills.\n")

    for key in ("BTC", "ETH", "pooled"):
        if key not in results:
            continue
        blk = results[key]
        if blk["n_trades"] == 0:
            print(f"[{key}] no valid trades\n")
            continue

        print(f"[{key}]  n_trades = {blk['n_trades']:,}")
        h = (f"{'dec':>3} {'n':>10} {'tot_notl':>10} {'max_notl':>10} "
             f"{('mean_' + str(HEAD_S) + 's'):>10} "
             f"{('mean_' + str(COMP_S) + 's'):>10}")
        print(h)
        print("-" * len(h))
        for d in blk["deciles"]:
            print(f"{d['decile']:>3} {d['n']:>10,} "
                  f"{_fmt_notional(d['total_notional']):>10} "
                  f"{_fmt_notional(d['max_notional']):>10} "
                  f"{_fmt(d[K_MEAN_HEAD]):>10} {_fmt(d[K_MEAN_COMP]):>10}")

        g = blk[K_GRADIENT]
        print(f"  {COMP_S}s-markout gradient (D1->D10): direction={g['direction']}, "
              f"monotone={g['monotone']}, "
              f"D10-D1 span={_fmt(g['last_minus_first_bps'])} bps  "
              "(rising => toxicity grows with size)")

        t = blk["top1pct_vs_rest"]
        print(f"  top {int(TOP_PCT * 100)}% by notional (n={t['n_top']:,}, "
              f"thresh={_fmt_notional(t['notional_threshold'])}):")
        print(f"     EQUAL-weight  {COMP_S}s  top={_fmt(t[K_TOP_MEAN])}  vs "
              f"rest={_fmt(t[K_REST_MEAN])}  "
              f"(top-rest={_fmt(t[K_TOP_MINUS_REST])} bps)")
        print(f"     NOTIONAL-wtd  {COMP_S}s  top={_fmt(t[K_TOP_WMEAN])}  vs "
              f"rest={_fmt(t[K_REST_WMEAN])}  "
              f"(top-rest={_fmt(t[K_TOP_MINUS_REST_W])} bps)")
        print("     => the equal-weight dip is the only sign of 'safe big "
              "fills'; dollar-weighted it largely collapses.")
        print()

    print("=" * 84)


if __name__ == "__main__":
    main()
