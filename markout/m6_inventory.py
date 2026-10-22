"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-19
References: Hyperliquid node-data S3 archive; Zenodo 18184441 (Albers et al. 2026).
"""

# ---------------------------------------------------------------------------
# OBJECT M6 - TOXICITY vs SIGNED PRE-TRADE INVENTORY.
#
# Does a taker who is already carrying a large position, or who is adding to an
# existing position rather than unwinding it, hit the maker with more adverse
# selection? Two readings of "inventory drives toxicity" are tested:
#
#   (a) MAGNITUDE. Spearman rank correlation of the per-fill taker markout against
#       the ABSOLUTE pre-trade inventory |start_pos|. Both windows are reported: the
#       declared headline window and the long companion beside it, each under a key
#       that names its own window in seconds, so neither reading can be quoted as
#       the other. A positive rank correlation says fills placed on top of a
#       bigger book carry more taker markout, i.e. more maker adverse selection.
#       Spearman (rank) rather than Pearson because markout and |inventory| are
#       both heavy-tailed and the relationship need not be linear.
#
#   (b) DIRECTION. Split fills by whether the taker trades in the SAME direction
#       as their existing inventory (ACCUMULATING: a long buys more, a short
#       sells more) or the OPPOSITE direction (REDUCING: a long sells, a short
#       buys). inv_dir = sign(start_pos); aligned_dir = +1 for a buy-aggressor
#       (taker_side==1), -1 for a sell-aggressor (taker_side==0). The product
#       inv_dir * aligned_dir is +1 when the trade extends the position and -1
#       when it cuts it. Report n and the mean markout for each group; if
#       accumulating fills carry a higher mean markout, the taker building
#       inventory is the more toxic flow.
#
# Sign convention (from the build script): mo* are SIGNED taker markouts in bps,
# positive = taker profited = maker bore adverse selection.
#
# start_pos is present on 100% of rows; ~87.8% are nonzero. Fills with
# start_pos == 0 have no defined inventory direction (sign 0) and are EXCLUDED
# from the directional split (but the |start_pos| Spearman keeps them, since
# |0| = 0 is a valid smallest-inventory value).
#
# numpy-only. Reads the shared intermediate (quickwin_markouts.npz) only; it does
# NOT parse raw data. Writes m6_inventory_results.json and prints a small table.
#
# Run command (bare python3 is BLOCKED on this machine):
#   uv run --no-project --with-requirements requirements.txt python3 markout/m6_inventory.py
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
from stats import rankdata

# -------------------- configuration --------------------
HERE = os.path.dirname(os.path.abspath(__file__))
# Located by panel_io rather than joined here, so the one place that knows where
# the markout panels live is the one place that has to change if they move.
NPZ_PATH = os.path.join(P.data_root(), "quickwin_markouts.npz")
RESULTS_PATH = os.path.join(HERE, "m6_inventory_results.json")

# int8 code -> symbol. The map is a property of the FILE, not of the project
# (quickwin_markouts.npz carries {0, 1}, panel_markouts.npz carries {0, 1, 2}), so it
# is asked for by artifact name and never written out here.
COIN_CODES = H.coin_labels("quickwin")

# Result keys are BUILT from the declared windows, never typed, so a key cannot keep
# a stale window over a new number. The npz column spellings (mo10, mo60) stay inside
# the code where they name the input column; the OUTPUT names its window in seconds.
HEAD_S = H.HEADLINE_HORIZON_S
COMP_S = H.COMPANION_HORIZON_S
K_RHO_HEAD = H.field_name("spearman_markout_vs_abs_start_pos", HEAD_S)
K_RHO_COMP = H.field_name("spearman_markout_vs_abs_start_pos", COMP_S)
K_N_HEAD = H.field_name("n_markout", HEAD_S)
K_N_COMP = H.field_name("n_markout", COMP_S)
K_MEAN_HEAD = H.field_name("mean_markout_bps", HEAD_S)
K_MEAN_COMP = H.field_name("mean_markout_bps", COMP_S)
K_GAP_HEAD = H.field_name("accumulate_minus_reduce_markout_bps", HEAD_S)
K_GAP_COMP = H.field_name("accumulate_minus_reduce_markout_bps", COMP_S)


# -------------------- distribution math --------------------
# The ranking comes from stats.py, where m4_realizedpnl.py and checks/chk_closedpnl.py
# read it too. Average-tie ranks are what Spearman's rho needs to stay correct under the
# repeated values this file is full of -- heavy ties at zero inventory and at rounded
# markouts -- so the tie rule is the part worth having in one place. The correlation
# below stays here because it also reports the paired count, which the shared one does
# not.
def _spearman(a, b):
    """Spearman rank correlation between two aligned vectors (numpy-only).

    Equals the Pearson correlation of the average-tie ranks. Returns NaN when
    fewer than 2 finite paired points or when either ranked vector has zero
    variance (e.g. a constant column). Only rows finite in BOTH a and b enter.
    """
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    m = np.isfinite(a) & np.isfinite(b)
    a, b = a[m], b[m]
    n = a.size
    if n < 2:
        return float("nan"), int(n)
    ra = rankdata(a)
    rb = rankdata(b)
    ra = ra - ra.mean()
    rb = rb - rb.mean()
    denom = np.sqrt(np.sum(ra * ra) * np.sum(rb * rb))
    if denom == 0.0:
        return float("nan"), int(n)
    rho = float(np.sum(ra * rb) / denom)
    return rho, int(n)


def _mean_or_nan(v):
    v = np.asarray(v, dtype=np.float64)
    v = v[np.isfinite(v)]
    return (float(v.mean()) if v.size else float("nan")), int(v.size)


# -------------------- (a) magnitude: Spearman vs |start_pos| --------------------
def _magnitude_block(start_pos, mo60, mo10):
    """Spearman rho of mo60 and mo10 against |start_pos| for one slice.

    All rows with a finite markout and finite start_pos enter (start_pos == 0
    is the legitimate smallest |inventory| value, so it is kept here). A positive
    rho means larger pre-trade inventory associates with more taker markout, i.e.
    more maker adverse selection.
    """
    abspos = np.abs(np.asarray(start_pos, dtype=np.float64))
    rho60, n60 = _spearman(mo60, abspos)
    rho10, n10 = _spearman(mo10, abspos)
    return {
        K_RHO_COMP: rho60,
        K_N_COMP: n60,
        K_RHO_HEAD: rho10,
        K_N_HEAD: n10,
        "note": ("positive rho => bigger pre-trade inventory associates with "
                 "more taker markout (more maker adverse selection)"),
    }


# -------------------- (b) direction: accumulating vs reducing --------------------
def _direction_block(start_pos, taker_side, mo60, mo10):
    """Mean markout for fills that extend vs reduce the taker's position.

    inv_dir     = sign(start_pos)             (+1 long, -1 short, 0 flat)
    aligned_dir = +1 if taker_side == 1 (buy-aggressor) else -1 (sell-aggressor)
    extend = inv_dir * aligned_dir == +1  (accumulating: long buys / short sells)
    reduce = inv_dir * aligned_dir == -1  (reducing:     long sells / short buys)

    Fills with start_pos == 0 have inv_dir == 0 (no defined direction) and are
    EXCLUDED from this split. Reports n and mean mo60 / mo10 per group plus the
    accumulate-minus-reduce gap (positive => building inventory is more toxic).
    """
    sp = np.asarray(start_pos, dtype=np.float64)
    side = np.asarray(taker_side, dtype=np.int64)
    mo60 = np.asarray(mo60, dtype=np.float64)
    mo10 = np.asarray(mo10, dtype=np.float64)

    inv_dir = np.sign(sp)                              # -1, 0, +1
    aligned_dir = np.where(side == 1, 1.0, -1.0)       # buy-aggressor = +1
    prod = inv_dir * aligned_dir

    extend = prod > 0                                  # excludes inv_dir == 0
    reduce = prod < 0

    acc_mo60, n_acc = _mean_or_nan(mo60[extend])
    red_mo60, n_red = _mean_or_nan(mo60[reduce])
    acc_mo10, n_acc10 = _mean_or_nan(mo10[extend])
    red_mo10, n_red10 = _mean_or_nan(mo10[reduce])

    gap60 = (acc_mo60 - red_mo60
             if (np.isfinite(acc_mo60) and np.isfinite(red_mo60))
             else float("nan"))
    gap10 = (acc_mo10 - red_mo10
             if (np.isfinite(acc_mo10) and np.isfinite(red_mo10))
             else float("nan"))

    n_flat = int(np.sum(inv_dir == 0))
    return {
        "accumulating": {
            "n": n_acc, K_MEAN_COMP: acc_mo60, K_MEAN_HEAD: acc_mo10,
            "definition": "taker trades SAME direction as existing inventory",
        },
        "reducing": {
            "n": n_red, K_MEAN_COMP: red_mo60, K_MEAN_HEAD: red_mo10,
            "definition": "taker trades OPPOSITE direction to existing inventory",
        },
        K_GAP_COMP: gap60,
        K_GAP_HEAD: gap10,
        "n_flat_excluded": n_flat,
        "note": ("positive gap => fills that BUILD inventory carry higher taker "
                 "markout than fills that CUT it; start_pos==0 rows excluded"),
    }


def _slice_result(start_pos, taker_side, mo60, mo10):
    """Full M6 block for one slice (a coin, or pooled = all rows)."""
    abspos = np.abs(np.asarray(start_pos, dtype=np.float64))
    n_rows = int(start_pos.size)
    n_nonzero = int(np.sum(abspos > 0))
    return {
        "n_rows": n_rows,
        "n_start_pos_nonzero": n_nonzero,
        "frac_start_pos_nonzero": (float(n_nonzero / n_rows) if n_rows else float("nan")),
        "magnitude": _magnitude_block(start_pos, mo60, mo10),
        "direction": _direction_block(start_pos, taker_side, mo60, mo10),
    }


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
    # Read only to state the window in the artifact's scope. The day column enters no
    # computation here; it is loaded so the file can say which days its numbers cover
    # instead of leaving a reader to infer the window from the input's name.
    day = data["day"].astype(np.int64)
    start_pos = data["start_pos"].astype(np.float64)
    taker_side = data["taker_side"].astype(np.int64)
    mo10 = data[H.headline_print_col()].astype(np.float64)
    mo60 = data[H.companion_print_col()].astype(np.float64)

    results = {
        "_meta": {
            "object": "M6 - toxicity vs signed pre-trade inventory",
            "markout_sign": ("signed taker markout bps; positive = taker "
                             "profited = maker adverse-selected"),
            "magnitude_test": (f"Spearman rho of the {COMP_S}s and {HEAD_S}s taker "
                               f"markout vs |start_pos|, each under its own key"),
            "direction_test": ("mean markout, accumulating (extend) vs reducing "
                               "(cut), where extend = sign(start_pos) * "
                               "[+1 buy-aggr / -1 sell-aggr] > 0"),
            "start_pos_coverage": ("100% present; ~87.8% nonzero; start_pos==0 "
                                   "kept in the |start_pos| Spearman, excluded "
                                   "from the directional split"),
        }
    }

    # What the numbers cover, stated rather than inferred, and built from the data
    # this run actually loaded. The npz path, the fingerprint and the population note
    # used to be written here by hand; artifact.write records all three in one shape,
    # so keeping them here as well would give one record two homes.
    days = np.unique(day)
    scope = {
        "population": (f"{coin.size:,} rows of the trade-print panel; every fill "
                       "with a finite markout and a finite start_pos enters, with "
                       "no per-wallet fill floor, no resampling and no randomness"),
        "window": (f"{days.size} days present in the input, day-of-month "
                   f"{days.min()}-{days.max()}; the calendar dates of the window "
                   "are declared by its producer, build_quickwin_markouts.py"),
        "coins": [COIN_CODES[c] for c in sorted(COIN_CODES)],
    }

    # per coin
    for code, name in COIN_CODES.items():
        sel = coin == code
        results[name] = _slice_result(
            start_pos[sel], taker_side[sel], mo60[sel], mo10[sel]
        )

    # pooled (all rows)
    results["pooled"] = _slice_result(start_pos, taker_side, mo60, mo10)

    # The output name and directory still come from the module-level RESULTS_PATH, so
    # a caller that redirects that constant redirects the whole write, as before.
    # Nothing here differs from the declaration, so no setting is overridden: the unit
    # of analysis is the FILL, so the per-wallet rank floor the fingerprint carries
    # does not gate this file at all, and no seed or resampling budget enters it.
    artifact.write(os.path.basename(RESULTS_PATH), results,
                   script=__file__, inputs=[NPZ_PATH], scope=scope,
                   settings={"h": HEAD_S, "lens": "print"}, started=t0,
                   out_dir=os.path.dirname(RESULTS_PATH))

    _print_summary(results)
    print(f"\n[m6] wrote {os.path.basename(RESULTS_PATH)}")


# -------------------- printed summary --------------------
def _fmt(x, nd=4):
    return f"{x:.{nd}f}" if isinstance(x, float) and np.isfinite(x) else "n/a"


def _print_summary(results):
    print("=" * 80)
    print("OBJECT M6 - TOXICITY vs SIGNED PRE-TRADE INVENTORY")
    print("=" * 80)
    print("  Sign: positive markout = taker profited = maker adverse-selected.")
    print("-" * 80)

    # (a) magnitude
    print("(a) MAGNITUDE - Spearman rho of markout vs |start_pos|")
    h1 = (f"  {'slice':>7} | {('rho ' + str(COMP_S) + 's'):>10} | "
          f"{('rho ' + str(HEAD_S) + 's'):>10} | {'n':>12}")
    print(h1)
    print("-" * len(h1))
    for key in ("BTC", "ETH", "pooled"):
        m = results[key]["magnitude"]
        print(f"  {key:>7} | {_fmt(m[K_RHO_COMP]):>10} | "
              f"{_fmt(m[K_RHO_HEAD]):>10} | "
              f"{m[K_N_COMP]:>12,}")
    print("    (positive rho => bigger inventory => more maker adverse selection)")

    # (b) direction
    print(f"\n(b) DIRECTION - mean {COMP_S}s markout (bps): accumulating vs reducing")
    h2 = (f"  {'slice':>7} | {'acc mean':>9} {'acc n':>11} | "
          f"{'red mean':>9} {'red n':>11} | {'acc-red':>8}")
    print(h2)
    print("-" * len(h2))
    for key in ("BTC", "ETH", "pooled"):
        d = results[key]["direction"]
        acc, red = d["accumulating"], d["reducing"]
        print(f"  {key:>7} | {_fmt(acc[K_MEAN_COMP], 3):>9} {acc['n']:>11,} | "
              f"{_fmt(red[K_MEAN_COMP], 3):>9} {red['n']:>11,} | "
              f"{_fmt(d[K_GAP_COMP], 3):>8}")
    print("    (positive acc-red => building inventory is the more toxic flow)")
    print("=" * 80)


if __name__ == "__main__":
    main()
