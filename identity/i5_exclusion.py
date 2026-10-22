"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-19
References: Hyperliquid node-data S3 archive; Zenodo 18184441 (Albers et al. 2026).
"""

# ---------------------------------------------------------------------------
# OBJECT I5 - PRE-REGISTERED KYLE EXCLUSION CHECK (position-extending vs reducing).
#
# This is the load-bearing identification test. The full-identification
# story rests on a Kyle (1985) reading of taker flow: a taker whose fill EXTENDS
# a position (opens or grows an exposure) is, on average, trading on information,
# so the price impact they impose on the maker is PERMANENT -- the taker markout
# should GROW or hold as the horizon lengthens. A taker whose fill REDUCES a
# position (closes / cuts an exposure) is, on average, trading for inventory /
# liquidity reasons, so any impact is TRANSIENT -- the markout should mean-revert,
# decaying from the 1-second to the 60-second horizon.
#
# The is_open flag from the build script encodes this partition as EXTEND/REDUCE:
#     is_open == 1  -> the fill OPENS or EXTENDS a position  (EXTEND)
#     is_open == 0  -> the fill CLOSES or REDUCES a position (REDUCE)
# NB: "EXTEND" is NOT the same as "accumulate on information". is_open == 1 also
# contains every OPEN-FROM-FLAT fill (start_pos == 0). On this dataset those
# open-from-flat fills are ~24% of the is_open == 1 rows and are, on average,
# UNINFORMED (BTC mean mo60 about -0.150 bps), so lumping them into "extend"
# drags the BTC extend-minus-reduce mo60 gap NEGATIVE (about -0.213 bps) and
# trips the REJECT verdict. The informative split for the Kyle reading is
# extend-FROM-A-POSITION versus reduce, i.e. EXCLUDE open-from-flat. We therefore
# report BOTH partitions side by side (see the two splits below).
#
# Sign convention (from the build script): mo1/mo10/mo60 are SIGNED taker markouts
# in basis points, positive = taker profited = maker bore adverse selection.
#
# Pre-registered prediction (the exclusion restriction we are testing):
#   EXTEND  -> permanent  -> permanence ratio mo60/mo1 >= 1
#   REDUCE  -> transient   -> permanence ratio mo60/mo1 <  1 (mean-reverts)
# and the extend-minus-reduce mo60 gap is positive and outside a label-permuted
# null. If that pattern holds we read the Kyle exclusion as IDENTIFIED; if it is
# rejected, the design falls back to a reduced-form (descriptive) reading.
#
# TWO SPLITS reported per slice:
#   (A) is_open split            : EXTEND = is_open == 1 (includes open-from-flat),
#                                  REDUCE = is_open == 0. The naive partition.
#   (B) exclude-open-from-flat   : EXTEND = is_open == 1 AND start_pos != 0
#                                  (genuine grow-from-a-position), REDUCE unchanged;
#                                  open-from-flat rows are dropped from both groups.
# On BTC the gap is -0.213 bps under (A) but flips POSITIVE (about +0.0115 bps)
# under (B), which RECONCILES I5 with M6 (M6's directional / sign result reads the
# extend leg as the grow-from-position flow, not the open-from-flat flow). The
# explicit M6/I5 reconciliation note is emitted in the output for each slice.
#
# Three robustness layers, all pre-registered (run on BOTH splits):
#   (1) per coin and pooled, with n, so a single coin cannot carry the result;
#   (2) a LABEL-PERMUTATION placebo: shuffle the EXTEND/REDUCE labels (fixed seed
#       20260619, 2000 shuffles) and confirm the observed extend-minus-reduce
#       mo60 gap lies outside the permuted null (two-sided permutation p, floored
#       at 1/2001);
#   (3) a WHALE-ROBUSTNESS recompute: drop the top-10 wallets by trade count and
#       confirm the extend-vs-reduce gap keeps its sign (the result is not the
#       artefact of a few hyperactive accounts).
#
# numpy-only, fixed seed 20260619 for the permutation. Reads ONLY the shared
# intermediate (quickwin_markouts.npz); it does NOT parse raw data.
#
# Run command (bare python3 is BLOCKED on this machine):
#   uv run --no-project --with-requirements requirements.txt python3 identity/i5_exclusion.py
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

# -------------------- configuration --------------------
HERE = os.path.dirname(os.path.abspath(__file__))
# Located through panel_io, so one module knows where the panels are. The environment
# list is EMPTY on purpose: this file has never honoured a data-root override, and
# adopting panel_io's five names would let a machine that happens to export one of them
# feed this script a different panel. With no name honoured the answer is the directory
# the code sits in, which is what it was. The file name stays a literal inside the join,
# because build.py derives the input edge by folding the argument of np.load to its last
# literal component and a call there would fold to nothing.
DATA_ROOT_ENV = ()
NPZ_PATH = os.path.join(P.data_root(env_names=DATA_ROOT_ENV),
                        "quickwin_markouts.npz")
RESULTS_PATH = os.path.join(HERE, "i5_exclusion_results.json")

COIN_CODES = H.coin_labels("quickwin")   # the map belongs to the FILE, not the project

# The three rungs this object needs, asked for by ROLE and never typed. The permanence
# ratio is a statement ABOUT the ladder, so all three appear; the test statistic is the
# gap at the LONG companion window, which is not the window the study scores on. That
# difference is declared in the fingerprint rather than left to be inferred from a key
# name, because a reader comparing this file to a headline-window result is comparing
# two different quantities.
#
# Asked of panel_io rather than of settings.py directly, which moves no name and adds
# one thing: the LENS stops being a choice made here. P.score_col("print", h) reads the
# reference price off the panel this file opens, so asking the trade-print panel for a
# book-mid column is refused by name instead of raising a bare KeyError inside numpy.
COL_SHORT = P.score_col("print", H.LADDER_S[0])   # shortest rung of the ladder
COL_HEAD = P.score_col("print")                   # the window the study scores on
COL_LONG = P.score_col("print", H.COMPANION_HORIZON_S)  # window this test's gap uses

KEY_PERMANENCE = f"permanence_ratio_{COL_LONG}_over_{COL_SHORT}"

SEED = H.seed_for("i5_exclusion")   # 20260619, declared per purpose rather than typed
                            # here. It differs from MASTER_SEED deliberately: two scripts
                            # sharing one seed would draw the same permutation stream and
                            # their placebos would stop being independent. The value is
                            # unchanged by this line, which is why the artifact it feeds
                            # reproduces leaf for leaf.
N_PERM = H.N_PERM           # label-permutation shuffles; the declared budget, so the
                            # floor is 1/2001 = 0.000500 and a corrected threshold at
                            # 0.05/48 = 0.00104 is clearable here
N_DROP_WHALES = H.WHALE_DROP_K  # top wallets by FILL COUNT dropped in robustness; the
                            # count is declared, the criterion is this file's, and it
                            # answers "is this a few hyperactive accounts"


# -------------------- group statistics --------------------
def _group_means(mo1, mo10, mo60, is_open):
    """Mean mo1/mo10/mo60 (bps) and counts for the extend / reduce partition.

    EXTENDING = is_open == 1, REDUCING = is_open == 0. Each horizon mean uses
    only the rows finite at that horizon, so a missing 60s markout does not drop
    the row from the 1s mean. Returns a dict with both groups' means, counts, and
    the permanence ratio mo60/mo1 per group (Kyle: extend >= 1, reduce < 1).
    """
    mo1 = np.asarray(mo1, dtype=np.float64)
    mo10 = np.asarray(mo10, dtype=np.float64)
    mo60 = np.asarray(mo60, dtype=np.float64)
    op = np.asarray(is_open, dtype=np.int64)

    ext = op == 1
    red = op == 0

    def _block(mask):
        def _m(col):
            v = col[mask]
            v = v[np.isfinite(v)]
            return (float(v.mean()) if v.size else float("nan")), int(v.size)
        m1, n1 = _m(mo1)
        m10, n10 = _m(mo10)
        m60, n60 = _m(mo60)
        # permanence ratio mo60/mo1. Guarded against a ~0 / sign-flipped mo1
        # denominator: only defined when mo1 is finite and clearly nonzero.
        if np.isfinite(m60) and np.isfinite(m1) and abs(m1) > 1e-12:
            perm = float(m60 / m1)
        else:
            perm = float("nan")
        # Every window-bearing key is BUILT from the column it reports, so a key can
        # never name one window while carrying another.
        return {
            "n": int(mask.sum()),
            f"mean_{COL_SHORT}_bps": m1, f"n_{COL_SHORT}": n1,
            f"mean_{COL_HEAD}_bps": m10, f"n_{COL_HEAD}": n10,
            f"mean_{COL_LONG}_bps": m60, f"n_{COL_LONG}": n60,
            KEY_PERMANENCE: perm,
        }

    return {"extending": _block(ext), "reducing": _block(red)}


def _gap_mo60(mo60, is_open):
    """Observed extend-minus-reduce mean mo60 gap for a label vector.

    Uses only rows finite in mo60. Returns NaN if either group is empty after
    the finite filter. This is the test statistic the permutation null mirrors.
    """
    mo60 = np.asarray(mo60, dtype=np.float64)
    op = np.asarray(is_open, dtype=np.int64)
    fin = np.isfinite(mo60)
    mo60 = mo60[fin]
    op = op[fin]
    ext = op == 1
    red = op == 0
    if not ext.any() or not red.any():
        return float("nan")
    return float(mo60[ext].mean() - mo60[red].mean())


# -------------------- (2) label-permutation placebo --------------------
def _permutation_test(mo60, is_open, n_perm=N_PERM, seed=SEED):
    """Two-sided label-permutation placebo for the extend-minus-reduce mo60 gap.

    The is_open labels are reshuffled n_perm times under a fixed-seed generator;
    each shuffle recomputes the extend-minus-reduce mo60 gap on the (fixed) mo60
    values. The permutation p-value is the share of |null gap| >= |observed gap|,
    with the conventional +1/(n_perm+1) inclusion of the observed labelling, so p
    is floored at 1/(n_perm+1) and never zero.

    Only rows finite in mo60 are permuted (the label set is held to that subset),
    so the null preserves the real group sizes among scorable rows.
    """
    mo60 = np.asarray(mo60, dtype=np.float64)
    op = np.asarray(is_open, dtype=np.int64)
    fin = np.isfinite(mo60)
    mo60 = mo60[fin]
    op = op[fin]

    n = mo60.size
    n_ext = int(np.sum(op == 1))
    n_red = int(np.sum(op == 0))
    floor = H.p_floor(n_perm)
    if n == 0 or n_ext == 0 or n_red == 0:
        return {
            f"observed_gap_{COL_LONG}_bps": float("nan"),
            "perm_p_two_sided": float("nan"),
            "perm_p_two_sided_is_floor": False,
            "p_floor": floor,
            "n_perm": int(n_perm),
            "null_mean": float("nan"),
            "null_std": float("nan"),
            "n_scored": int(n),
            "n_extending": n_ext,
            "n_reducing": n_red,
        }

    obs = float(mo60[op == 1].mean() - mo60[op == 0].mean())

    # A permuted gap is determined entirely by which rows get the "extend" label,
    # so it is enough to draw n_ext indices and difference the two group means.
    rng = np.random.default_rng(seed)
    total = float(mo60.sum())
    idx = np.arange(n)
    null = np.empty(n_perm, dtype=np.float64)
    for i in range(n_perm):
        rng.shuffle(idx)
        ext_sum = float(mo60[idx[:n_ext]].sum())
        ext_mean = ext_sum / n_ext
        red_mean = (total - ext_sum) / n_red
        null[i] = ext_mean - red_mean

    # THE COUNTING IS stats.permutation_p, AND IT IS THE SAME COUNT. The +1 that
    # includes the observed labelling is the module's floor rule, and the three things
    # that could have moved the number are each unchanged:
    #
    #   the side stays TWO-SIDED at `|null| >= |observed|`. The question here is
    #     whether extending and reducing flow differ, not which of them is worse, and a
    #     one-sided p on it would be half the honest number;
    #   the slack is ZERO -- this test has never subtracted a tolerance before
    #     comparing, so it is passed as an explicit abs_tol of 0.0 rather than taking
    #     the module's default, which scales with the comparison;
    #   the denominator is the requested budget here and the count of finite draws in
    #     the module, and the two are the same count BY CONSTRUCTION: every row entering
    #     the loop is finite in the scored column, both groups are non-empty by the
    #     guard above, so each draw is a difference of two means of finite numbers and
    #     no draw can come back as no number.
    #
    # null_std stays local because it is a DIFFERENT quantity from the module's: this
    # file reports the population spread of the null (ddof=0) and the module reports the
    # sample one (ddof=1).
    block = stats.permutation_p(
        obs, null, side="two_sided", abs_tol=0.0, n_requested=int(n_perm),
        cell=("i5_exclusion_extend_minus_reduce_gap", COL_LONG))
    p = block["p"]
    return {
        f"observed_gap_{COL_LONG}_bps": obs,
        "perm_p_two_sided": float(p),
        # True means no shuffle produced a gap as large as the observed one, so the p is
        # the budget's smallest expressible value rather than a measurement of how small
        # the p is. Five of the six cells in the committed artifact sit here.
        "perm_p_two_sided_is_floor": bool(block["p_is_floored"]),
        "p_floor": floor,
        "n_perm": int(n_perm),
        "null_mean": float(block["null_mean"]),
        "null_std": float(null.std(ddof=0)),
        "n_scored": int(n),
        "n_extending": n_ext,
        "n_reducing": n_red,
        # The procedure beside the number: side, slack, both draw counts and the floor.
        "permutation_procedure": block,
    }


# -------------------- (3) whale-robustness --------------------
def _most_active_drop_robustness(taker_id, mo60, is_open, n_drop=N_DROP_WHALES):
    """Recompute the extend-minus-reduce mo60 gap after dropping the most active.

    WHAT IS ORDERED HERE IS ACTIVITY, NOT ADVERSE SELECTION, and the name says so
    because the tree also ranks counterparties by markout and cuts a top fraction of
    that ranking. The wallets removed below are the ones with the most ROWS in the
    slice; their markout plays no part in choosing them, and the set they form is not
    the study's selected set and is not built from it. Nothing here is a toxicity
    decision: the question asked is only whether a handful of hyperactive accounts
    produce the sign of the gap.

    The top n_drop wallets by TRADE COUNT (most rows in the slice) are removed,
    and the gap is recomputed on the remainder. Confirms the sign of the gap is
    not produced by a handful of hyperactive accounts. Reports the full-sample
    gap, the dropped-whale gap, whether the sign is preserved, and which wallets
    were dropped (with their trade counts).
    """
    tid = np.asarray(taker_id, dtype=np.int64)
    mo60 = np.asarray(mo60, dtype=np.float64)
    op = np.asarray(is_open, dtype=np.int64)

    full_gap = _gap_mo60(mo60, op)

    uniq, counts = np.unique(tid, return_counts=True)
    if uniq.size == 0:
        return {
            f"full_gap_{COL_LONG}_bps": full_gap,
            f"dropped_gap_{COL_LONG}_bps": float("nan"),
            "sign_preserved": False,
            "n_whales_dropped": 0,
            "dropped_wallets": [],
        }

    k = int(min(n_drop, uniq.size))
    # most-traded first; stable tie-break keeps the result deterministic
    order = np.argsort(-counts, kind="stable")
    dropped_ids = uniq[order[:k]]
    dropped_counts = counts[order[:k]]

    keep = ~np.isin(tid, dropped_ids)
    dropped_gap = _gap_mo60(mo60[keep], op[keep])

    sign_ok = (
        np.isfinite(full_gap) and np.isfinite(dropped_gap)
        and np.sign(full_gap) == np.sign(dropped_gap)
        and full_gap != 0.0
    )
    return {
        f"full_gap_{COL_LONG}_bps": full_gap,
        f"dropped_gap_{COL_LONG}_bps": dropped_gap,
        "whale_drop_criterion": H.whale_drop("fill_count", n_drop)["criterion"],
        "sign_preserved": bool(sign_ok),
        "n_whales_dropped": k,
        "n_rows_after_drop": int(np.sum(keep)),
        "dropped_wallets": [
            {"taker_id": int(w), "trade_count": int(c)}
            for w, c in zip(dropped_ids, dropped_counts)
        ],
    }


# -------------------- verdict --------------------
def _verdict(group_means, perm):
    """Pre-registered one-line verdict from the pooled evidence.

    The Kyle exclusion is read as IDENTIFIED when ALL hold:
      * extending permanence ratio mo60/mo1 >= 1 (impact permanent / growing),
      * reducing permanence ratio mo60/mo1 <  1 (impact mean-reverts),
      * the extend-minus-reduce mo60 gap is positive, and
      * that gap is outside the permuted null (perm p <= 0.05).
    Otherwise the pattern is REJECTED and the design is reduced-form.
    """
    ext = group_means["extending"][KEY_PERMANENCE]
    red = group_means["reducing"][KEY_PERMANENCE]
    gap = perm[f"observed_gap_{COL_LONG}_bps"]
    p = perm["perm_p_two_sided"]

    ext_permanent = np.isfinite(ext) and ext >= 1.0
    red_transient = np.isfinite(red) and red < 1.0
    gap_positive = np.isfinite(gap) and gap > 0.0
    gap_significant = np.isfinite(p) and p <= 0.05

    identified = bool(ext_permanent and red_transient and gap_positive and gap_significant)
    return {
        "kyle_exclusion_identified": identified,
        "verdict": ("IDENTIFIED: extending impact permanent, reducing impact "
                    "transient, gap positive and outside the permuted null"
                    if identified else
                    "REJECTED: Kyle exclusion pattern does not hold -> "
                    "reduced-form (descriptive) reading"),
        "checks": {
            "extending_permanent_ratio_ge_1": bool(ext_permanent),
            "reducing_transient_ratio_lt_1": bool(red_transient),
            "extend_minus_reduce_gap_positive": bool(gap_positive),
            "gap_outside_null_p_le_0p05": bool(gap_significant),
        },
    }


def _split_block(taker_id, mo1, mo10, mo60, label, run_perm_and_most_active_drop):
    """Full I5 battery for ONE extend/reduce labelling of a slice.

    `label` is the EXTEND(1)/REDUCE(0) vector to test on these rows. The same
    machinery serves both the is_open split (label == is_open) and the
    exclude-open-from-flat split (rows pre-filtered, label still is_open).
    """
    gm = _group_means(mo1, mo10, mo60, label)
    block = {
        "n_rows": int(np.asarray(label).size),
        "n_extending": int(np.sum(np.asarray(label) == 1)),
        "n_reducing": int(np.sum(np.asarray(label) == 0)),
        "group_means": gm,
    }
    if run_perm_and_most_active_drop:
        perm = _permutation_test(mo60, label)
        most_active_drop = _most_active_drop_robustness(taker_id, mo60, label)
        block["permutation_placebo"] = perm
        block["whale_robustness"] = most_active_drop
        block["verdict"] = _verdict(gm, perm)
    return block


def _slice_result(taker_id, mo1, mo10, mo60, is_open, start_pos,
                  run_perm_and_most_active_drop):
    """Full I5 block for one slice, reporting BOTH extend/reduce splits.

    Split (A) is_open: EXTEND = is_open == 1 (includes open-from-flat),
                       REDUCE = is_open == 0.
    Split (B) exclude-open-from-flat: drop rows where is_open == 1 AND
                       start_pos == 0, then EXTEND = is_open == 1 (grow-from-a-
                       position only), REDUCE = is_open == 0 unchanged.

    An explicit M6/I5 reconciliation note records the BTC-style sign flip: the
    open-from-flat fills are uninformed, so split (A) can show a negative
    extend-minus-reduce gap while split (B) -- the grow-from-position flow that
    M6 reads as the extend leg -- is positive, reconciling the two objects.
    """
    is_open = np.asarray(is_open, dtype=np.int64)
    start_pos = np.asarray(start_pos, dtype=np.float64)

    # ---- split (A): is_open as-is (open-from-flat lumped into EXTEND) ----
    split_a = _split_block(taker_id, mo1, mo10, mo60, is_open,
                           run_perm_and_most_active_drop)

    # ---- split (B): exclude open-from-flat (is_open==1 & start_pos==0) ----
    open_from_flat = (is_open == 1) & (start_pos == 0.0)
    keep = ~open_from_flat
    split_b = _split_block(
        taker_id[keep], mo1[keep], mo10[keep], mo60[keep], is_open[keep],
        run_perm_and_most_active_drop)

    # open-from-flat diagnostics (the rows that drive the difference between A/B)
    fin_off = np.isfinite(mo60[open_from_flat])
    off_mo60 = mo60[open_from_flat][fin_off]
    n_off = int(open_from_flat.sum())
    frac_off_of_extend = (n_off / int(np.sum(is_open == 1))
                          if np.sum(is_open == 1) else float("nan"))

    gap_a = split_a["group_means"]
    gap_b = split_b["group_means"]
    gap_a_val = _gap_mo60(mo60, is_open)
    gap_b_val = _gap_mo60(mo60[keep], is_open[keep])
    flipped = bool(
        np.isfinite(gap_a_val) and np.isfinite(gap_b_val)
        and np.sign(gap_a_val) != np.sign(gap_b_val))

    reconciliation = {
        "n_open_from_flat": n_off,
        "frac_of_extend_group": float(frac_off_of_extend),
        f"open_from_flat_mean_{COL_LONG}_bps": (
            float(off_mo60.mean()) if off_mo60.size else float("nan")),
        f"gap_{COL_LONG}_split_is_open_bps": float(gap_a_val),
        f"gap_{COL_LONG}_split_exclude_open_from_flat_bps": float(gap_b_val),
        "sign_flips_between_splits": flipped,
        "note": (
            "is_open==1 mixes uninformed open-from-flat fills into EXTEND; "
            "excluding them (start_pos==0 opens) isolates grow-from-a-position "
            "flow. Where the gap flips from negative under the is_open split to "
            "positive under the exclude split, I5 RECONCILES with M6, which "
            "reads the extend leg as grow-from-position rather than open-from-flat."),
    }

    return {
        "n_rows": int(is_open.size),
        "n_open_from_flat": n_off,
        "split_is_open": split_a,
        "split_exclude_open_from_flat": split_b,
        "m6_i5_reconciliation": reconciliation,
    }


# -------------------- main --------------------
def main():
    t0 = artifact.start_clock()
    # panel_io owns both refusals: the missing-FILE message names the producer that
    # writes this gitignored intermediate and names no directory, so no account name can
    # reach a pasted log, and the missing-COLUMN message names what was asked and what
    # the file holds.
    P.require_present("print", NPZ_PATH, env_names=DATA_ROOT_ENV)

    data = np.load(NPZ_PATH)
    P.require_columns(data, "print", "taker_id", "coin", "is_open", "start_pos",
                      "day", COL_SHORT, COL_HEAD, COL_LONG)
    taker_id = data["taker_id"].astype(np.int64)
    coin = data["coin"].astype(np.int64)
    is_open = data["is_open"].astype(np.int64)
    start_pos = data["start_pos"].astype(np.float64)
    # The three rungs as float64, each asked for by role through the panel's own lens.
    mo1 = P.score(data, "print", H.LADDER_S[0])
    mo10 = P.score(data, "print")
    mo60 = P.score(data, "print", H.COMPANION_HORIZON_S)
    # Read only to state the window in the artifact's scope; it enters no computation.
    day = data["day"].astype(np.int64)

    # What every number in this file was computed under. The window recorded is the
    # LONG COMPANION, because that is the window the test statistic and the verdict
    # live at -- not the window the study scores wallets on. A fingerprint that said
    # the headline here would describe a different quantity. It is built before the
    # results dict because artifact.write is the single place that stamps it.
    settings_used = dict(
        h=H.COMPANION_HORIZON_S, lens="print",
        master_seed=SEED,
        n_perm=N_PERM,
        n_boot=None,
        rank_floor_fills=None,
        persistence_floor_fills=None,
        fdr_alpha=None,
        horizons_used_s=list(H.LADDER_S),
        statistic_horizon_s=H.COMPANION_HORIZON_S,
        whale_drop_criterion="fill_count",
        p_floor=H.p_floor(N_PERM),
        overrides_note=(
            "the test statistic is the extend-minus-reduce gap at the LONG "
            "COMPANION window, and the permanence ratio is a statement about the "
            "whole ladder, so is_headline_horizon is False on purpose and this "
            "file is NOT comparable cell-for-cell with a headline-window result; "
            "master_seed 20260619 not settings.MASTER_SEED 20260620; n_perm 2000 "
            "matches the declaration, so the floor 0.000500 clears a "
            "48-cell corrected threshold of 0.00104; no bootstrap is drawn and no "
            "wallet floor or FDR family applies here; whales are dropped by FILL "
            "COUNT"),
            )

    results = {
        "_meta": {
            "object": "I5 - pre-registered Kyle exclusion check (extend vs reduce)",
            "is_open_encoding": "1 = opens/EXTENDS a position, 0 = closes/REDUCES",
            "extend_reduce_note": (
                "EXTEND (is_open==1) is NOT 'accumulate on information': it also "
                "contains open-from-flat (start_pos==0) fills, which on this "
                "dataset are ~24% of EXTEND and uninformed. Two splits are "
                "reported: (A) is_open as-is, (B) exclude open-from-flat."),
            "markout_sign": ("signed taker markout bps; positive = taker "
                             "profited = maker adverse-selected"),
            "pre_registered_prediction": (
                f"EXTEND permanent ({COL_LONG}/{COL_SHORT} >= 1); REDUCE transient "
                f"({COL_LONG}/{COL_SHORT} < 1); extend-minus-reduce {COL_LONG} gap > 0 "
                "and outside the label-permuted null"),
            "splits": {
                "A_is_open": "EXTEND = is_open==1 (incl open-from-flat), "
                             "REDUCE = is_open==0",
                "B_exclude_open_from_flat": "drop is_open==1 & start_pos==0; "
                             "EXTEND = grow-from-position only, REDUCE = is_open==0",
            },
            "m6_i5_reconciliation": (
                "BTC gap is negative under split A but positive under split B "
                "(open-from-flat fills are uninformed); split B reconciles I5 "
                "with M6's extend-leg reading"),
            "permutation": {
                "n_perm": N_PERM, "seed": SEED,
                "p_floor": H.p_floor(N_PERM),
                "p_floor_note": (
                    f"{N_PERM} draws cannot express a p below {H.p_floor(N_PERM):.6f}; "
                    "each slice carries perm_p_two_sided_is_floor saying whether its p is "
                    "a measurement or that floor"),
            },
            "whale_robustness": {
                "n_drop_top_by_trade_count": N_DROP_WHALES,
                "criterion": H.whale_drop("fill_count", N_DROP_WHALES)["criterion"],
            },
        }
    }

    # What the numbers cover. The unit of analysis is the FILL and no wallet floor
    # gates this file, so the population is the rows read; the split into extend and
    # reduce is a partition of them, not a filter on them.
    days = np.unique(day)
    scope = {
        "population": (f"{taker_id.size:,} rows of the trade-print panel, partitioned "
                       "into extend and reduce fills; the unit of analysis is the "
                       "fill, so no wallet fill floor gates this file"),
        "window": (f"{days.size} days present in the input, day-of-month "
                   f"{days.min()}-{days.max()}; the calendar dates of the window "
                   "are declared by its producer, build_quickwin_markouts.py"),
        "coins": [COIN_CODES[c] for c in sorted(COIN_CODES)],
    }

    # per coin (full battery: means + permutation + whale-robustness + verdict)
    for code, name in COIN_CODES.items():
        sel = coin == code
        results[name] = _slice_result(
            taker_id[sel], mo1[sel], mo10[sel], mo60[sel], is_open[sel],
            start_pos[sel], run_perm_and_most_active_drop=True,
        )

    # pooled (all rows) -- this carries the headline verdict
    results["pooled"] = _slice_result(
        taker_id, mo1, mo10, mo60, is_open, start_pos, run_perm_and_most_active_drop=True,
    )

    # The output name and directory still come from the module-level RESULTS_PATH, so
    # a caller that redirects that constant redirects the whole write, as before.
    artifact.write(os.path.basename(RESULTS_PATH), results,
                   script=__file__, inputs=[NPZ_PATH], scope=scope,
                   settings=settings_used, started=t0,
                   out_dir=os.path.dirname(RESULTS_PATH))

    _print_summary(results)
    print(f"\n[i5] wrote {os.path.basename(RESULTS_PATH)}")


# -------------------- printed summary --------------------
def _fmt(x, nd=4):
    return f"{x:.{nd}f}" if isinstance(x, float) and np.isfinite(x) else "n/a"


def _split_table(results, split_key, split_title):
    """Print the markout ladder + gap/perm/whale/verdict table for one split."""
    slices = tuple(COIN_CODES.values()) + ("pooled",)
    print(f"\n  ----- SPLIT {split_title} -----")
    print(f"  Mean markout ladder (bps) and permanence ratio {COL_LONG}/{COL_SHORT}:")
    h = (f"  {'slice':>7} {'grp':>10} | {COL_SHORT:>8} {COL_HEAD:>8} {COL_LONG:>8} | "
         f"{'perm':>7} | {'n':>11}")
    print(h)
    print("-" * len(h))
    for key in slices:
        sp = results[key][split_key]
        for grp in ("extending", "reducing"):
            g = sp["group_means"][grp]
            print(f"  {key:>7} {grp:>10} | {_fmt(g[f'mean_{COL_SHORT}_bps'], 3):>8} "
                  f"{_fmt(g[f'mean_{COL_HEAD}_bps'], 3):>8} "
                  f"{_fmt(g[f'mean_{COL_LONG}_bps'], 3):>8} | "
                  f"{_fmt(g[KEY_PERMANENCE], 3):>7} | "
                  f"{g['n']:>11,}")

    print(f"\n  Extend-minus-reduce {COL_LONG} gap ({H.COMPANION_HORIZON_S}s, the "
          f"companion window and NOT the {H.HEADLINE_HORIZON_S}s scoring window), "
          "permutation placebo, whale check:")
    h2 = (f"  {'slice':>7} | {'gap bps':>9} | {'perm p':>8} | {'floor':>5} | "
          f"{'whale gap':>9} | {'sign?':>5} | verdict")
    print(h2)
    print("-" * (len(h2) + 6))
    for key in slices:
        sp = results[key][split_key]
        perm = sp.get("permutation_placebo", {})
        wh = sp.get("whale_robustness", {})
        vd = sp.get("verdict", {})
        gap = perm.get(f"observed_gap_{COL_LONG}_bps", float("nan"))
        p = perm.get("perm_p_two_sided", float("nan"))
        at_floor = "yes" if perm.get("perm_p_two_sided_is_floor") else ""
        wgap = wh.get(f"dropped_gap_{COL_LONG}_bps", float("nan"))
        sign_ok = "yes" if wh.get("sign_preserved") else "no"
        tag = "IDENT" if vd.get("kyle_exclusion_identified") else "REJECT"
        print(f"  {key:>7} | {_fmt(gap, 4):>9} | {_fmt(p, 4):>8} | {at_floor:>5} | "
              f"{_fmt(wgap, 4):>9} | {sign_ok:>5} | {tag}")


def _print_summary(results):
    print("=" * 86)
    print("OBJECT I5 - PRE-REGISTERED KYLE EXCLUSION CHECK (extend vs reduce)")
    print("=" * 86)
    print(f"  Kyle: EXTEND impact permanent ({COL_LONG}/{COL_SHORT} >= 1); "
          "REDUCE impact transient (< 1).")
    print("  Sign: positive markout = taker profited = maker adverse-selected.")
    print("  EXTEND (is_open==1) includes uninformed open-from-flat fills; two")
    print("  splits reported - (A) is_open as-is, (B) exclude open-from-flat.")
    print("-" * 86)

    _split_table(results, "split_is_open", "(A) is_open as-is")
    _split_table(results, "split_exclude_open_from_flat",
                 "(B) exclude open-from-flat (start_pos==0 opens dropped)")

    # M6/I5 reconciliation per slice
    print("\n  M6/I5 RECONCILIATION (open-from-flat drives the A vs B difference):")
    h3 = (f"  {'slice':>7} | {'n_off':>9} | {'off_' + COL_LONG:>9} | "
          f"{'gapA bps':>9} | {'gapB bps':>9} | {'flips?':>6}")
    print(h3)
    print("-" * (len(h3) + 4))
    for key in tuple(COIN_CODES.values()) + ("pooled",):
        rec = results[key]["m6_i5_reconciliation"]
        flips = "yes" if rec["sign_flips_between_splits"] else "no"
        print(f"  {key:>7} | {rec['n_open_from_flat']:>9,} | "
              f"{_fmt(rec[f'open_from_flat_mean_{COL_LONG}_bps'], 3):>9} | "
              f"{_fmt(rec[f'gap_{COL_LONG}_split_is_open_bps'], 4):>9} | "
              f"{_fmt(rec[f'gap_{COL_LONG}_split_exclude_open_from_flat_bps'], 4):>9} | "
              f"{flips:>6}")

    pv_a = results["pooled"]["split_is_open"].get("verdict", {})
    pv_b = results["pooled"]["split_exclude_open_from_flat"].get("verdict", {})
    print("-" * 86)
    print(f"  POOLED VERDICT (A, is_open)            : {pv_a.get('verdict', 'n/a')}")
    print(f"  POOLED VERDICT (B, exclude open-flat)  : {pv_b.get('verdict', 'n/a')}")
    first_coin = COIN_CODES[min(COIN_CODES)]
    btc_rec = results[first_coin]["m6_i5_reconciliation"]
    print(f"  {first_coin} gap: "
          f"{_fmt(btc_rec[f'gap_{COL_LONG}_split_is_open_bps'], 4)} (A) -> "
          f"{_fmt(btc_rec[f'gap_{COL_LONG}_split_exclude_open_from_flat_bps'], 4)} (B) "
          f"= reconciles with M6" if btc_rec["sign_flips_between_splits"]
          else f"  {first_coin} gap sign unchanged between splits")
    print("=" * 86)


if __name__ == "__main__":
    main()
