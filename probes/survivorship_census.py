#!/usr/bin/env python3
"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-08-05
References: Hyperliquid Level-4 order-book data, Zenodo 18184441 (Albers et al. 2026).

WHAT THE TWO-SIDED ADMISSION RULE COSTS, MEASURED INSTEAD OF CONCEDED.

WHAT THIS FILE IS FOR. Five producers in this repository admit a counterparty into a
count only when it reached a minimum number of fills in BOTH halves of the window: the
half the wallet is ranked on and the disjoint half it is measured on. Written out, the
rule says that a wallet is scored on its early behaviour and then, before that score is
allowed to matter, the later window is consulted to see whether the wallet came back.
The wallets that never came back leave the sample, and so do the wallets that came back
too rarely. What survives is a population selected on an outcome that follows the
ranking in time, which is survivorship in its plainest form.

The report has to state this as a limitation, and a limitation stated without a number
is an opinion. This node supplies the numbers. It changes none of the five producers
and moves none of their masks: it re-implements each admission expression beside its
original, at the same unit, the same floor, the same lens and the same window, and then
recounts under two counterfactual rules. The five producers keep publishing what they
publish; what this file adds is the price of their rule.

THE THREE POPULATIONS, and each answers a different question.

  early_only          the wallets the ranking could have been formed on. It applies the
                      floor to the ranking half alone and asks nothing at all about the
                      later window, so it is the largest of the three and it is the only
                      one that carries no information from after the ranking.
  as_committed        what the five producers ship today: the floor in the ranking half
                      AND the same floor again in the measurement half.
  late_at_least_one   the floor in the ranking half, and a single fill in the later one.
                      It keeps every wallet whose later behaviour is observable at all
                      and drops only the ones with nothing to measure, which is the
                      loosest rule under which a later measurement still exists.

THE LOSS SPLITS IN TWO, and the two halves have different standing. A wallet that made
no fill at all in the later window cannot be measured there by any rule, so its loss is
not attributable to the threshold: it is the shape of the data. A wallet that came back
but fewer than K times is dropped by the threshold alone, and admitting it costs nothing
but a noisier measurement of a wallet that is really there. The first quantity is what
the report may call unavoidable; the second is what the report must call a choice. They
are counted separately here for that reason, and the fact that both are printed is what
stops a single loss figure from being read as either one.

WHAT ELSE THE NODE COMPUTES, and why these two quantities rather than a table of counts.
A count says how many wallets a rule removes. It does not say whether the study's
published findings depend on the removal, and that is the question the report is
answering. So two published quantities are recomputed under all three populations:

  1. the separation between the toxic decile and the rest at the headline horizon, on
     both reference prices, which is the head figure of the study;
  2. the later realized profit of the flagged wallets against the rest, which is the
     out-of-sample counterparty-side validation.

THE DECLARED AXIS. Exactly one thing differs between the three arms of every comparison
below: the number of fills demanded in the LATER window. Everything else is held equal
by construction rather than by intention -- the same two panels, the same rows, the same
scoring column, the same lens, the same day split, the same floor in the ranking half,
the same decile quantile, the same resampling budget and the same named random streams.
The list of held-equal measurements is not a promise in this docstring: it is computed
per site and compared across arms, and a difference in any of them stops the run.

THE CALIBRATION, WITHOUT WHICH NOTHING IS PRINTED. The as_committed arm is not a new
computation; it is a re-implementation of five expressions that already have published
answers. So it is required to reproduce those answers exactly before any counterfactual
is written. The anchors are READ from the five committed artifacts at run time rather
than typed here, so the gate cannot drift from what the tree publishes, and the five
artifacts are recorded as inputs with their hashes. A single disagreement stops the run,
names the measurement that diverged and prints both values. The pattern is the one
flat_surcharge_control.py already uses: a control that has not reproduced its baseline
has no baseline, and its residual is a number about nothing.

THE PREDICATE THAT SPLITS THE LOSS IS CALIBRATED ON TWO OPPOSITE CASES, both live. It
must find a non-empty "came back but below the floor" bucket at the four sites whose
floor exceeds one fill, and it must find that bucket EMPTY at build_toxicity_frame.py,
whose floor is a single fill and where the two counterfactuals therefore coincide with
the committed rule by construction. A predicate that reported a loss there would be
measuring itself.

Inputs (local, de-identified): quickwin_markouts.npz, quickwin_markouts_mid.npz, and
the five committed artifacts whose populations this node reproduces.
Output: survivorship_census_results.json.

    uv run --no-project --with-requirements requirements.txt \
        python3 probes/survivorship_census.py
"""
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

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_NAME = "survivorship_census_results.json"

# The two panels. Located by panel_io, which is the one place that knows where they
# live; the np.load calls stay at their own call sites because build.py derives this
# script's input edges by folding the argument of np.load to a constant, and a path it
# cannot fold makes no edge at all.
NPZ_PRINT = os.path.join(P.data_root(), "quickwin_markouts.npz")
NPZ_MID = os.path.join(P.data_root(), "quickwin_markouts_mid.npz")

# The five committed artifacts this node has to reproduce before it may print anything.
# They are read rather than transcribed: an anchor typed into this file would be a
# second home for a published number, and the two homes would part company on the first
# recompute of any of the five.
# Each sits beside its own producer, so the group directory is named here and the file
# name stays the last component of the join: that is what build.py folds the input edge
# out of, and a directory it cannot fold makes no edge at all.
IN_M2 = os.path.join(_CODE_DIR, "markout", "m2_figure_results.json")
IN_WS1 = os.path.join(_CODE_DIR, "markout", "ws1_horizon_results.json")
IN_WS2 = os.path.join(_CODE_DIR, "persistence", "ws2_hard_classifier_results.json")
IN_WS3 = os.path.join(_CODE_DIR, "persistence", "ws3_taker_pnl_results.json")
IN_FRAME = os.path.join(_CODE_DIR, "data", "toxicity_frame_results.json")

# The three admission rules, named by what they demand of the LATER window. The names
# are the keys of every per-arm block below, so a reader never has to remember an order.
ARMS = ("early_only", "as_committed", "late_at_least_one")

# The decile cut the two recomputed quantities use. It is the cut both m2_figure.py and
# ws3_taker_pnl.py already apply, held equal across the arms because it is not the axis:
# moving it would make the arms differ in two things at once.
TOXIC_Q = 0.90

# Relative slack for the calibration comparisons of continuous quantities. Counts are
# compared exactly -- a population is an integer and there is no such thing as
# reproducing it approximately. A volume-weighted mean is a sum of millions of floats
# whose order of accumulation is not guaranteed across numpy builds, so it is compared
# with a relative tolerance rather than bit for bit; 1e-9 is far tighter than any
# difference a changed population would produce and far looser than accumulation noise.
CALIBRATION_RTOL = 1e-9


# =====================================================================
# 1. THE SMALL PIECES
# =====================================================================

def _finite_counts(unit, mask, value, n_units):
    """Per-unit sum and count of the finite values of `value` inside `mask`.

    This is the shape all five admission expressions are built on, written once. The
    count is of FINITE scores and not of rows, because that is what every one of the
    five counts: a fill whose markout could not be computed is not a fill the wallet
    can be scored on.
    """
    keep = mask & np.isfinite(value)
    return (np.bincount(unit[keep], weights=value[keep], minlength=n_units),
            np.bincount(unit[keep], minlength=n_units).astype(np.float64))


def _row_counts(unit, mask, n_units):
    """Per-unit count of ROWS inside `mask`, finite or not.

    Kept apart from the function above because ws3_taker_pnl.py's admission expression
    genuinely uses this one on the later window -- `la["cnt"]`, a count of fills rather
    than of scores -- while using the finite count on the ranking window. The asymmetry
    is that producer's and is reproduced rather than tidied away.
    """
    return np.bincount(unit[mask], minlength=n_units).astype(np.float64)


def _admit(early_cnt, late_cnt, k, arm):
    """The admission mask of one arm, given the two per-unit counts and the floor.

    One function for all three arms, so the arms cannot drift apart in anything except
    the number this function reads off the arm's name, which is the declared axis.
    """
    base = early_cnt >= k
    if arm == "early_only":
        return base
    if arm == "as_committed":
        return base & (late_cnt >= k)
    if arm == "late_at_least_one":
        return base & (late_cnt >= 1)
    raise ValueError(f"unknown arm {arm!r}; the declared arms are {ARMS}")


def _late_floor_of(arm, k):
    """What the arm demands of the later window. This IS the axis, as a number."""
    return {"early_only": 0, "as_committed": int(k), "late_at_least_one": 1}[arm]


def _decompose(early_cnt, late_cnt, k):
    """Split the wallets the floor admits on the ranking half into the three buckets.

    kept                admitted by the committed rule.
    returned_below_k    came back, but fewer than k times: removed by the threshold and
                        by nothing else.
    never_returned      made no fill at all in the later window: removed by the data.

    The three are exhaustive and disjoint over the ranking-half population, and the
    artifact asserts that they sum to it rather than trusting the arithmetic here.
    """
    base = early_cnt >= k
    kept = base & (late_cnt >= k)
    returned_below = base & (late_cnt >= 1) & (late_cnt < k)
    never = base & (late_cnt < 1)
    return {
        "early_eligible": int(base.sum()),
        "kept_as_committed": int(kept.sum()),
        "returned_below_floor": int(returned_below.sum()),
        "never_returned": int(never.sum()),
    }


def _vw_mean(mask, values, weights):
    """Volume-weighted mean of `values` over the finite rows of `mask`.

    The same expression m2_figure.py's `vw` applies, extracted so that the three arms
    share one implementation and the calibration compares like with like.
    """
    keep = mask & np.isfinite(values)
    w = weights[keep]
    total = float(np.sum(w))
    if total == 0.0:
        return float("nan")
    return float(np.sum(values[keep] * w) / total)


def _relative_gap(got, want):
    """Relative difference, falling back to the absolute one when the anchor is zero."""
    if want == 0.0:
        return abs(got)
    return abs(got - want) / abs(want)


# =====================================================================
# 2. THE CALIBRATION LEDGER, WHICH DECIDES WHETHER ANYTHING IS WRITTEN
# =====================================================================

class Calibration:
    """Every claim that the committed arm reproduces a published number.

    Each entry names the measurement, the artifact and key path the anchor was read
    from, the anchor, what this run computed, and whether they agree. The verdict is a
    property of the whole ledger: one disagreement and nothing is written. The refusal
    is closed -- it names the measurement and prints both values -- because a control
    that says only "mismatch" sends the reader back to two files with no idea which
    number moved.
    """

    def __init__(self):
        self.entries = []

    def exact(self, what, source, got, want):
        self.entries.append({"measurement": what, "anchor_source": source,
                             "anchor": want, "recomputed": got,
                             "comparison": "exact", "tolerance": None,
                             "agrees": bool(got == want)})

    def close(self, what, source, got, want, rtol=CALIBRATION_RTOL):
        gap = _relative_gap(float(got), float(want))
        self.entries.append({"measurement": what, "anchor_source": source,
                             "anchor": float(want), "recomputed": float(got),
                             "comparison": "relative", "tolerance": rtol,
                             "relative_gap": gap, "agrees": bool(gap <= rtol)})

    @property
    def failures(self):
        return [e for e in self.entries if not e["agrees"]]

    def report(self):
        print(f"[calibration] {len(self.entries) - len(self.failures)}"
              f"/{len(self.entries)} committed-arm measurements reproduce their "
              f"published anchor", flush=True)
        for e in self.failures:
            print(f"[calibration] REFUSED on {e['measurement']}: "
                  f"published {e['anchor']!r} in {e['anchor_source']}, "
                  f"recomputed {e['recomputed']!r}", flush=True)
        return not self.failures

    def block(self):
        return {
            "why": "the as_committed arm re-implements five published admission "
                   "expressions; until it returns their published populations and "
                   "quantities it has reproduced nothing, and a counterfactual "
                   "measured against a baseline that was never reproduced is a "
                   "difference between two unknowns",
            "n_measurements": len(self.entries),
            "n_agreeing": len(self.entries) - len(self.failures),
            "all_agree": not self.failures,
            "measurements": self.entries,
        }


# =====================================================================
# 3. THE FIVE SITES
# =====================================================================

def site_m2(zp, zm, cal, anchors):
    """m2_figure.py line 112: q = (ce >= MIN_FILLS) & (cl >= MIN_FILLS).

    Unit: the wallet. Floor: settings.wallet_fill_floor('m2_figure', 'both_halves').
    Ranking column: the headline TRADE-PRINT markout, which is what that file ranks on;
    the book-mid panel supplies the second lens the separation is reported under, and
    contributes nothing to the admission.
    """
    k = int(H.wallet_fill_floor("m2_figure", "both_halves"))
    tid = zp["taker_id"].astype(np.int64)
    day = zp["day"]
    notl = zp["notional"].astype(np.float64)
    n_units = int(tid.max()) + 1
    early_days, late_days = H.split_early_late(np.unique(day))
    early = np.isin(day, list(early_days))
    late = np.isin(day, list(late_days))

    rank_col = H.headline_print_col()
    rank_score = zp[rank_col].astype(np.float64)
    sum_e, cnt_e = _finite_counts(tid, early, rank_score, n_units)
    _sum_l, cnt_l = _finite_counts(tid, late, rank_score, n_units)

    ladder_print = [H.headline_print_col(h) for h in H.LADDER_S]
    ladder_mid = [H.headline_mid_col(h) for h in H.LADDER_S]

    arms = {}
    for arm in ARMS:
        q = _admit(cnt_e, cnt_l, k, arm)
        early_mean = np.full(n_units, np.nan)
        early_mean[q] = sum_e[q] / cnt_e[q]
        thr = float(np.nanquantile(early_mean[q], TOXIC_Q))
        is_tox = np.zeros(n_units, bool)
        is_ben = np.zeros(n_units, bool)
        is_tox[q & (early_mean >= thr)] = True
        is_ben[q & (early_mean < thr)] = True
        tox_rows = late & is_tox[tid]
        ben_rows = late & is_ben[tid]
        # A wallet admitted by the early_only arm may have no later fill at all, so it
        # is labelled and then contributes nothing to the measurement. Both counts are
        # recorded, because reporting only the first would say a group was measured on
        # wallets that supplied no observation.
        tox_measured = int(np.unique(tid[tox_rows]).size)
        ben_measured = int(np.unique(tid[ben_rows]).size)
        block = {
            "late_min_fills": _late_floor_of(arm, k),
            "n_admitted": int(q.sum()),
            "n_toxic_decile": int(is_tox.sum()),
            "n_remaining": int(is_ben.sum()),
            "n_toxic_with_late_fills": tox_measured,
            "n_remaining_with_late_fills": ben_measured,
            "decile_threshold_bps": thr,
            "vw_markout_bps": {"trade_print": {}, "book_mid": {}},
            "separation_bps": {"trade_print": {}, "book_mid": {}},
        }
        for h, cp, cm in zip(H.LADDER_S, ladder_print, ladder_mid):
            pt = _vw_mean(tox_rows, zp[cp].astype(np.float64), notl)
            pb = _vw_mean(ben_rows, zp[cp].astype(np.float64), notl)
            mt = _vw_mean(tox_rows, zm[cm].astype(np.float64), notl)
            mb = _vw_mean(ben_rows, zm[cm].astype(np.float64), notl)
            block["vw_markout_bps"]["trade_print"][str(h)] = {"toxic_decile": pt,
                                                              "remaining": pb}
            block["vw_markout_bps"]["book_mid"][str(h)] = {"toxic_decile": mt,
                                                           "remaining": mb}
            block["separation_bps"]["trade_print"][str(h)] = pt - pb
            block["separation_bps"]["book_mid"][str(h)] = mt - mb
        head = str(H.HEADLINE_HORIZON_S)
        block["headline_separation_bps"] = {
            "trade_print": block["separation_bps"]["trade_print"][head],
            "book_mid": block["separation_bps"]["book_mid"][head],
        }
        arms[arm] = block
        print(f"[m2 {arm:18s}] admitted {block['n_admitted']:,} wallets, "
              f"toxic {block['n_toxic_decile']:,}, rest {block['n_remaining']:,}, "
              f"separation print {block['headline_separation_bps']['trade_print']:+.4f} "
              f"mid {block['headline_separation_bps']['book_mid']:+.4f} bps", flush=True)

    committed = arms["as_committed"]
    cal.exact("m2_figure toxic-decile wallet count", "m2_figure_results.json "
              "n_wallets.toxic_decile", committed["n_toxic_decile"],
              int(anchors["m2"]["n_wallets"]["toxic_decile"]))
    cal.exact("m2_figure remaining wallet count", "m2_figure_results.json "
              "n_wallets.remaining", committed["n_remaining"],
              int(anchors["m2"]["n_wallets"]["remaining"]))
    cal.close("m2_figure decile threshold (bps)", "m2_figure_results.json "
              "labelling.threshold_bps", committed["decile_threshold_bps"],
              anchors["m2"]["labelling"]["threshold_bps"])
    for lens in ("trade_print", "book_mid"):
        for h in H.LADDER_S:
            cal.close(f"m2_figure separation, {lens}, {h}s",
                      f"m2_figure_results.json separation_bps.{lens}.{h}",
                      committed["separation_bps"][lens][str(h)],
                      anchors["m2"]["separation_bps"][lens][str(h)])

    return {
        "producer": "m2_figure.py",
        "admission_expression": "q = (ce >= MIN_FILLS) & (cl >= MIN_FILLS)",
        "unit": "counterparty wallet, pooled over coins",
        "floor_source": "settings.wallet_fill_floor('m2_figure', 'both_halves')",
        "floor_fills": k,
        "panel": P.panel_file("print"),
        "ranking_column": rank_col,
        "counts_what": "fills with a finite headline trade-print markout",
        "held_equal": {
            "early_days": [int(d) for d in early_days],
            "late_days": [int(d) for d in late_days],
            "floor_fills": k,
            "ranking_column": rank_col,
            "unit_rule": "taker_id",
            "decile_quantile": TOXIC_Q,
            "n_rows": int(tid.size),
        },
        "loss_decomposition": _decompose(cnt_e, cnt_l, k),
        "arms": arms,
    }


def site_ws1(zm, cal, anchors):
    """ws1_horizon_persistence.py line 292: early[u][1] >= K and late[u][1] >= K.

    Unit: the wallet-coin pair. Floor: the file's K_PRIMARY, ten fills, which its own
    header calls the loosest rung of settings.RANK_FLOOR_SENSITIVITY and which is read
    from that declaration here rather than typed.

    A STAND-IN IS USED FOR THE SCORE AND IT IS DECLARED. That file scores its grid by
    re-marking the fills against the mid series at eight horizons; this node reads the
    committed headline mid column instead, which is the SAME quantity at the headline
    rung -- the file's own reproduction gate asserts that the two agree there. The
    stand-in is not assumed to be sound: the committed arm has to return the published
    unit count at the headline rung, and if it does not, nothing is written.
    """
    k = int(min(H.RANK_FLOOR_SENSITIVITY))
    taker = zm["taker_id"].astype(np.int64)
    coin = zm["coin"].astype(np.int8)
    day = zm["day"]
    unit = taker * 4 + coin.astype(np.int64)
    n_units = int(unit.max()) + 1
    early_days, late_days = H.split_early_late(np.unique(day))
    early = np.isin(day, list(early_days))
    late = np.isin(day, list(late_days))
    score = P.score(zm, "mid")
    _se, cnt_e = _finite_counts(unit, early, score, n_units)
    _sl, cnt_l = _finite_counts(unit, late, score, n_units)

    arms = {}
    for arm in ARMS:
        q = _admit(cnt_e, cnt_l, k, arm)
        arms[arm] = {"late_min_fills": _late_floor_of(arm, k),
                     "n_admitted": int(q.sum())}
        print(f"[ws1 {arm:18s}] admitted {int(q.sum()):,} wallet-coin units",
              flush=True)

    cal.exact("ws1_horizon_persistence pooled unit count at the headline rung",
              f"ws1_horizon_results.json pooled.{H.HEADLINE_HORIZON_S}.n_units",
              arms["as_committed"]["n_admitted"],
              int(anchors["ws1"]["pooled"][str(H.HEADLINE_HORIZON_S)]["n_units"]))

    return {
        "producer": "ws1_horizon_persistence.py",
        "admission_expression":
            "units = [u for u in early if u in late and early[u][1] >= K "
            "and late[u][1] >= K]",
        "unit": "wallet-coin pair",
        "floor_source": "min(settings.RANK_FLOOR_SENSITIVITY), the file's K_PRIMARY",
        "floor_fills": k,
        "panel": P.panel_file("mid"),
        "ranking_column": P.score_col("mid"),
        "counts_what": "fills with a finite headline book-mid markout",
        "stand_in_note":
            "the producer re-marks its own eight-horizon grid from the mid series; "
            "this census reads the committed headline mid column, which its "
            "reproduction gate asserts is the same quantity at that rung. The "
            "calibration below is what makes the stand-in a measured claim rather "
            "than an assumption, and it covers the headline rung only",
        "held_equal": {
            "early_days": [int(d) for d in early_days],
            "late_days": [int(d) for d in late_days],
            "floor_fills": k,
            "ranking_column": P.score_col("mid"),
            "unit_rule": "taker_id * 4 + coin",
            "n_rows": int(unit.size),
        },
        "loss_decomposition": _decompose(cnt_e, cnt_l, k),
        "arms": arms,
    }


def site_ws2(zm, cal, anchors):
    """ws2_hard_classifier.py line 131: (e_cnt >= K) & (l_cnt >= K) & finite means.

    Unit: the wallet-coin pair. Floor:
    settings.wallet_fill_floor('ws2_hard_classifier', 'both_halves').

    The two finiteness conjuncts add nothing to the mask -- a unit with at least one
    finite score has a finite mean -- and they are reproduced anyway, so that the
    expression censused is the expression written.
    """
    k = int(H.wallet_fill_floor("ws2_hard_classifier", "both_halves"))
    taker = zm["taker_id"].astype(np.int64)
    coin = zm["coin"].astype(np.int8)
    day = zm["day"]
    unit = taker * 4 + coin.astype(np.int64)
    n_units = int(unit.max()) + 1
    early_days, late_days = H.split_early_late(np.unique(day))
    early = np.isin(day, list(early_days))
    late = np.isin(day, list(late_days))
    score = P.score(zm, "mid")
    sum_e, cnt_e = _finite_counts(unit, early, score, n_units)
    sum_l, cnt_l = _finite_counts(unit, late, score, n_units)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean_e = np.where(cnt_e > 0, sum_e / np.maximum(cnt_e, 1), np.nan)
        mean_l = np.where(cnt_l > 0, sum_l / np.maximum(cnt_l, 1), np.nan)

    arms = {}
    for arm in ARMS:
        q = _admit(cnt_e, cnt_l, k, arm) & np.isfinite(mean_e)
        if arm != "early_only":
            q = q & np.isfinite(mean_l)
        arms[arm] = {"late_min_fills": _late_floor_of(arm, k),
                     "n_admitted": int(q.sum())}
        print(f"[ws2 {arm:18s}] admitted {int(q.sum()):,} wallet-coin units",
              flush=True)

    cal.exact("ws2_hard_classifier eligible unit count",
              "ws2_hard_classifier_results.json n_eligible",
              arms["as_committed"]["n_admitted"], int(anchors["ws2"]["n_eligible"]))

    return {
        "producer": "ws2_hard_classifier.py",
        "admission_expression":
            "elig = (e_cnt >= K) & (l_cnt >= K) & np.isfinite(e_mean) "
            "& np.isfinite(l_mean)",
        "unit": "wallet-coin pair",
        "floor_source":
            "settings.wallet_fill_floor('ws2_hard_classifier', 'both_halves')",
        "floor_fills": k,
        "panel": P.panel_file("mid"),
        "ranking_column": P.score_col("mid"),
        "counts_what": "fills with a finite headline book-mid markout",
        "held_equal": {
            "early_days": [int(d) for d in early_days],
            "late_days": [int(d) for d in late_days],
            "floor_fills": k,
            "ranking_column": P.score_col("mid"),
            "unit_rule": "taker_id * 4 + coin",
            "n_rows": int(unit.size),
        },
        "loss_decomposition": _decompose(cnt_e, cnt_l, k),
        "arms": arms,
    }


def site_ws3(zm, cal, anchors):
    """ws3_taker_pnl.py line 299: (ea["cnt_mo"] >= K) & (la["cnt"] >= K) & finite mean.

    Unit: the wallet-coin pair. Floor: settings.wallet_fill_floor('ws3_taker_pnl',
    'headline'), fifty fills, five times the floor the other four sites apply.

    The two windows are counted differently by this producer and that asymmetry is
    reproduced: the ranking half counts fills with a finite markout, the later half
    counts fills. Tidying it would change the population and make the census a
    measurement of a different rule than the one shipped.

    This is where the report's number is. The later realized profit of the flagged
    wallets against the rest is recomputed under all three admissions, with the median
    gap and its bootstrap interval drawn from a stream named for the arm, so no two
    arms share draws.
    """
    k = int(H.wallet_fill_floor("ws3_taker_pnl", "headline"))
    n_boot = int(H.boot_draws("ws3_taker_pnl"))
    taker = zm["taker_id"].astype(np.int64)
    coin = zm["coin"].astype(np.int8)
    day = zm["day"]
    unit = taker * 4 + coin.astype(np.int64)
    n_units = int(unit.max()) + 1
    early_days, late_days = H.split_early_late(np.unique(day))
    early = np.isin(day, list(early_days))
    late = np.isin(day, list(late_days))
    score = P.score(zm, "mid")
    cpnl = zm["closed_pnl"].astype(np.float64)
    notl = zm["notional"].astype(np.float64)

    sum_e, cnt_e = _finite_counts(unit, early, score, n_units)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean_e = np.where(cnt_e > 0, sum_e / np.maximum(cnt_e, 1), np.nan)
    # The LATER window's admission counts rows, not finite scores: that is `la["cnt"]`.
    cnt_l_rows = _row_counts(unit, late, n_units)
    late_cp = np.bincount(unit[late], weights=cpnl[late], minlength=n_units)
    late_nt = np.bincount(unit[late], weights=notl[late], minlength=n_units)
    with np.errstate(invalid="ignore", divide="ignore"):
        late_pnl_pd = np.where(late_nt > 0, late_cp / np.maximum(late_nt, 1) * 1e4,
                               np.nan)

    arms = {}
    for arm in ARMS:
        elig = _admit(cnt_e, cnt_l_rows, k, arm) & np.isfinite(mean_e)
        thr = float(np.quantile(mean_e[elig], TOXIC_Q))
        flag = elig & (mean_e >= thr)
        rest = elig & ~flag
        pnl_flag = late_pnl_pd[flag]
        pnl_rest = late_pnl_pd[rest]
        pnl_flag = pnl_flag[np.isfinite(pnl_flag)]
        pnl_rest = pnl_rest[np.isfinite(pnl_rest)]
        rng = H.rng("survivorship_census", "oos_median_gap", arm, k)
        gaps = np.empty(n_boot)
        for i in range(n_boot):
            gf = pnl_flag[rng.integers(0, pnl_flag.size, pnl_flag.size)]
            gr = pnl_rest[rng.integers(0, pnl_rest.size, pnl_rest.size)]
            gaps[i] = np.median(gf) - np.median(gr)
            artifact.progress(f"ws3 {arm} bootstrap", i + 1, n_boot, T0)
        lo, hi = (float(v) for v in np.percentile(gaps, [2.5, 97.5]))
        med_flag = float(np.median(pnl_flag))
        med_rest = float(np.median(pnl_rest))
        arms[arm] = {
            "late_min_fills": _late_floor_of(arm, k),
            "n_admitted": int(elig.sum()),
            "n_flagged": int(flag.sum()),
            "n_rest": int(rest.sum()),
            "n_flagged_with_late_pnl": int(pnl_flag.size),
            "n_rest_with_late_pnl": int(pnl_rest.size),
            "decile_threshold_bps": thr,
            "late_pnl_pd_bps_flag_median": med_flag,
            "late_pnl_pd_bps_rest_median": med_rest,
            "late_pnl_pd_bps_flag_mean": float(np.mean(pnl_flag)),
            "late_pnl_pd_bps_rest_mean": float(np.mean(pnl_rest)),
            "median_gap_bps": med_flag - med_rest,
            "median_gap_ci": [lo, hi],
            "median_gap_ci_excludes_zero": bool(lo > 0.0 or hi < 0.0),
            "flagged_median_above_rest": bool(med_flag > med_rest),
            "bootstrap": {"n_draws": n_boot, "budget_source":
                          "settings.boot_draws('ws3_taker_pnl')",
                          "cell": ["survivorship_census", "oos_median_gap", arm, k],
                          "percentiles": [2.5, 97.5]},
            "bootstrap_note":
                "the interval of the as_committed arm is close to but not identical "
                "with the one ws3_taker_pnl_results.json publishes, and the reason is "
                "the stream rather than the data. Every generator in this tree is "
                "derived from settings.MASTER_SEED and the NAME of the cell drawing "
                "it, so a cell named for this census draws a different resample of the "
                "same numbers than a cell named for that producer. The medians the "
                "interval is built around reproduce exactly and are calibrated against "
                "the published ones; the endpoints are a resampling estimate and are "
                "deliberately not calibrated, because requiring two differently named "
                "streams to agree bit for bit would be requiring them to be one stream",
        }
        print(f"[ws3 {arm:18s}] admitted {int(elig.sum()):,} units, flagged "
              f"{int(flag.sum()):,}; late PnL/$ median flag {med_flag:+.3f} vs rest "
              f"{med_rest:+.3f} bps, gap CI [{lo:+.3f},{hi:+.3f}]", flush=True)

    committed = arms["as_committed"]
    oos = anchors["ws3"]["oos_validation"]
    cal.exact("ws3_taker_pnl flagged unit count",
              "ws3_taker_pnl_results.json oos_validation.n_flag",
              committed["n_flagged"], int(oos["n_flag"]))
    cal.exact("ws3_taker_pnl remaining unit count",
              "ws3_taker_pnl_results.json oos_validation.n_rest",
              committed["n_rest"], int(oos["n_rest"]))
    cal.close("ws3_taker_pnl late PnL/$ median, flagged",
              "ws3_taker_pnl_results.json "
              "oos_validation.late_pnl_pd_bps_flag_median",
              committed["late_pnl_pd_bps_flag_median"],
              oos["late_pnl_pd_bps_flag_median"])
    cal.close("ws3_taker_pnl late PnL/$ median, remaining",
              "ws3_taker_pnl_results.json "
              "oos_validation.late_pnl_pd_bps_rest_median",
              committed["late_pnl_pd_bps_rest_median"],
              oos["late_pnl_pd_bps_rest_median"])

    return {
        "producer": "ws3_taker_pnl.py",
        "admission_expression":
            'elig = (ea["cnt_mo"] >= K) & (la["cnt"] >= K) '
            '& np.isfinite(ea["mean_mo"])',
        "unit": "wallet-coin pair",
        "floor_source": "settings.wallet_fill_floor('ws3_taker_pnl', 'headline')",
        "floor_fills": k,
        "panel": P.panel_file("mid"),
        "ranking_column": P.score_col("mid"),
        "counts_what":
            "the ranking half counts fills with a finite headline book-mid markout; "
            "the later half counts FILLS, finite or not, which is this producer's own "
            "asymmetry and is reproduced rather than tidied",
        "held_equal": {
            "early_days": [int(d) for d in early_days],
            "late_days": [int(d) for d in late_days],
            "floor_fills": k,
            "ranking_column": P.score_col("mid"),
            "unit_rule": "taker_id * 4 + coin",
            "decile_quantile": TOXIC_Q,
            "bootstrap_draws": n_boot,
            "n_rows": int(unit.size),
        },
        "loss_decomposition": _decompose(cnt_e, cnt_l_rows, k),
        "arms": arms,
    }


def site_frame(zm, cal, anchors):
    """build_toxicity_frame.py line 141: `if w not in late_by_taker: continue`.

    Unit: the wallet-coin pair. Floor: one fill, and it is STRUCTURAL rather than
    declared -- a wallet is in that dictionary exactly when it has at least one finite
    later score, so there is no constant to read from settings.py and none is invented
    here.

    THIS SITE IS THE CALIBRATION CASE THAT MUST STAY SILENT. With a floor of one fill,
    the committed rule and the late_at_least_one counterfactual are the same rule, so
    the "came back but below the floor" bucket must be empty and the two arms must
    return the same population. A predicate reporting a loss here would be measuring
    itself rather than the data.
    """
    k = 1
    taker = zm["taker_id"].astype(np.int64)
    coin = zm["coin"].astype(np.int8)
    day = zm["day"]
    unit = taker * 4 + coin.astype(np.int64)
    n_units = int(unit.max()) + 1
    days = np.unique(day)
    early_days, late_days = H.split_early_late(days)
    # The producer cuts its halves as days[:half], days[half:] rather than through the
    # declaration. The two forms agree on this input, and the agreement is asserted here
    # instead of assumed, because a window with an odd number of days would part them.
    half = days.size // 2
    assert list(days[:half]) == list(early_days) and list(days[half:]) == list(late_days), (
        f"build_toxicity_frame.py cuts its halves as days[:{half}] / days[{half}:], "
        f"which on this input gives {list(days[:half])} / {list(days[half:])}, while "
        f"settings.split_early_late gives {list(early_days)} / {list(late_days)}; the "
        "census cannot stand in for a rule it does not reproduce")
    early = np.isin(day, list(early_days))
    late = np.isin(day, list(late_days))
    score = P.score(zm, "mid")
    _se, cnt_e = _finite_counts(unit, early, score, n_units)
    _sl, cnt_l = _finite_counts(unit, late, score, n_units)

    arms = {}
    for arm in ARMS:
        q = _admit(cnt_e, cnt_l, k, arm)
        arms[arm] = {"late_min_fills": _late_floor_of(arm, k),
                     "n_admitted": int(q.sum())}
        print(f"[frame {arm:16s}] admitted {int(q.sum()):,} wallet-coin rows",
              flush=True)

    cal.exact("build_toxicity_frame row count",
              "toxicity_frame_results.json n_rows",
              arms["as_committed"]["n_admitted"], int(anchors["frame"]["n_rows"]))

    return {
        "producer": "build_toxicity_frame.py",
        "admission_expression": "if w not in late_by_taker: continue",
        "unit": "wallet-coin pair, written as one row of the training frame",
        "floor_source":
            "structural: membership of the later-window group means, which is one "
            "finite score. No constant is declared for it and none is invented here",
        "floor_fills": k,
        "panel": P.panel_file("mid"),
        "ranking_column": P.score_col("mid"),
        "counts_what": "fills with a finite headline book-mid markout",
        "held_equal": {
            "early_days": [int(d) for d in early_days],
            "late_days": [int(d) for d in late_days],
            "floor_fills": k,
            "ranking_column": P.score_col("mid"),
            "unit_rule": "taker_id * 4 + coin",
            "n_rows": int(unit.size),
        },
        "loss_decomposition": _decompose(cnt_e, cnt_l, k),
        "arms": arms,
    }


# =====================================================================
# 4. THE GATES OVER THE ASSEMBLED SITES
# =====================================================================

def check_axis(sites):
    """One declared axis, and everything else held equal. Returns findings, never None.

    The held-equal list is per site and is compared across that site's three arms; the
    axis is compared too, and it must DIFFER, because an axis that does not move makes
    the three arms one arm under three names. Both directions are checked for the same
    reason a predicate needs two opposite cases.
    """
    findings = []
    for key, site in sites.items():
        # The message names the FILE and not the address key. The key lost its
        # extension so that an address could be split on the dot; a refusal still has
        # to send the reader to a file, so it reads the name out of the block.
        name = site["producer"]
        floors = {arm: site["arms"][arm]["late_min_fills"] for arm in ARMS}
        # The frame site is the declared exception and it is named, not exempted: with a
        # floor of one, as_committed and late_at_least_one ARE the same rule, so their
        # axis values coincide by construction and their populations must too.
        expected_coincidence = site["floor_fills"] == 1
        coincide = floors["as_committed"] == floors["late_at_least_one"]
        if coincide != expected_coincidence:
            findings.append(
                f"{name}: the committed and late_at_least_one arms "
                f"{'share' if coincide else 'do not share'} a later-window floor "
                f"({floors['as_committed']} against {floors['late_at_least_one']}), "
                f"which is not what a floor of {site['floor_fills']} implies")
        if coincide:
            a = site["arms"]["as_committed"]["n_admitted"]
            b = site["arms"]["late_at_least_one"]["n_admitted"]
            if a != b:
                findings.append(
                    f"{name}: the two arms share a later-window floor of "
                    f"{floors['as_committed']} and must therefore admit the same "
                    f"population, but they admit {a:,} and {b:,}")
        if floors["early_only"] != 0:
            findings.append(f"{name}: the early_only arm demands "
                            f"{floors['early_only']} later fills, so it is not the "
                            f"arm it is named for")
    return findings


def _dotted_keys(node, path=()):
    """Every key in the payload whose own name holds a dot, with where it sits."""
    out = []
    if isinstance(node, dict):
        for key, value in node.items():
            here = path + (str(key),)
            if "." in str(key):
                out.append(".".join(here))
            out += _dotted_keys(value, here)
    elif isinstance(node, list):
        for i, value in enumerate(node):
            out += _dotted_keys(value, path + (str(i),))
    return out


def check_addressable(payload):
    """No key of this artifact may hold a dot, so every leaf can be named.

    WHY THIS IS ENFORCED HERE RATHER THAN REMEMBERED. An address into a results file is
    split on the dot by the register's resolver, so a key that contains one cannot be
    descended into: the leaf exists in the file and no address reaches it. This artifact
    shipped in exactly that state on 2026-08-05, with its site blocks keyed by file name
    -- 261 of its 325 numeric leaves unreachable by their own path, including the head
    figure's separation and this node's own headline gap. Nothing detected it, because
    the file was well formed and every number in it was right. A rule that is only
    written down goes on being true until the next key is added, so it is a gate.

    Calibrated on two opposite cases, both cheap and both here: a fixture carrying a
    dotted key must be caught, and this run's real payload must pass. One case alone
    would not tell a gate that never fires from a gate that always does.
    """
    fixture = {"sites": {"m2_figure.py": {"n": 1}}}
    caught = _dotted_keys(fixture)
    live = _dotted_keys(payload)
    return {
        "rule": "no key of this artifact holds a dot, because an address is split on "
                "the dot and a key holding one cannot be descended into",
        "calibration": {
            "must_fire": {"fixture": "sites -> 'm2_figure.py'",
                          "found": caught, "fired": bool(caught)},
            "must_stay_silent": {"population": "every key of this run's payload",
                                 "found": live, "silent": not live},
            "passed": bool(caught) and not live,
        },
        "n_keys_holding_a_dot": len(live),
        "keys_holding_a_dot": live,
        "passed": bool(caught) and not live,
    }


def calibrate_decomposition(sites):
    """Two opposite live cases for the predicate that splits the loss.

    Must fire: the four sites whose floor exceeds one fill have a non-empty "came back
    below the floor" bucket, because that bucket is exactly what their threshold
    removes on top of what the data removes.
    Must stay silent: build_toxicity_frame.py, whose floor is one fill, where that
    bucket is empty by construction.

    One reference case cannot tell a predicate that is too wide from one that is too
    narrow apart, which is why both are here and why both are taken off the live tree
    rather than written as fixtures.
    """
    fires, silent, findings = [], [], []
    for key, site in sites.items():
        name = site["producer"]
        d = site["loss_decomposition"]
        total = d["kept_as_committed"] + d["returned_below_floor"] + d["never_returned"]
        if total != d["early_eligible"]:
            findings.append(
                f"{name}: the three buckets sum to {total:,} against "
                f"{d['early_eligible']:,} admitted on the ranking half, so they are "
                f"not a partition of it")
        if site["floor_fills"] > 1:
            fires.append({"site": key, "producer": name,
                          "returned_below_floor": d["returned_below_floor"]})
            if d["returned_below_floor"] <= 0:
                findings.append(
                    f"{name}: floor {site['floor_fills']} and no wallet at all came "
                    f"back below it, which is the reading a predicate returns when it "
                    f"is not looking")
        else:
            silent.append({"site": key, "producer": name,
                           "returned_below_floor": d["returned_below_floor"]})
            if d["returned_below_floor"] != 0:
                findings.append(
                    f"{name}: floor is one fill, so no wallet can come back below it, "
                    f"yet {d['returned_below_floor']:,} are reported")
    return {
        "must_fire": fires,
        "must_stay_silent": silent,
        "findings": findings,
        "passed": not findings,
    }


def _headline_finding(sites):
    """Whether the admission rule changes the DIRECTION of the published comparison.

    Read off the three arms rather than written down: a sentence typed here would be a
    second home for a result and would go on saying what it said on the day it was
    typed. What the function decides is only which arms put the flagged wallets above
    the rest and which intervals clear zero; the prose around those two facts is fixed
    and true whichever way they come out.
    """
    arms = sites["ws3_taker_pnl"]["arms"]
    above = sorted(a for a in ARMS if arms[a]["flagged_median_above_rest"])
    below = sorted(a for a in ARMS if not arms[a]["flagged_median_above_rest"])
    clears_zero = sorted(a for a in ARMS if arms[a]["median_gap_ci_excludes_zero"])
    return {
        "quantity": "the later realized profit per dollar of the flagged "
                    "counterparties against the rest, at ws3_taker_pnl.py",
        "arms_where_flagged_earn_more": above,
        "arms_where_flagged_earn_less": below,
        "order_depends_on_admission": bool(above and below),
        "arms_whose_interval_excludes_zero": clears_zero,
        "median_gap_bps_by_arm": {a: arms[a]["median_gap_bps"] for a in ARMS},
        "what_it_means":
            "the direction of this comparison is a property of the admission rule and "
            "not only of the counterparties. Both lists above are non-empty, so the "
            "sign of the gap turns over between the arms; and the arm whose interval "
            "clears zero is the one that asks nothing about the later window, which is "
            "also the only arm free of the selection. A report may state the committed "
            "figure, but it may not state it without this one beside it"
            if (above and below) else
            "the direction of this comparison survives every admission rule tested, so "
            "the selection changes the size of the gap and not its sign",
    }


# =====================================================================
# 5. THE RUN
# =====================================================================

T0 = artifact.start_clock()


def main():
    print("[census] the admission rule of five producers, priced under three rules",
          flush=True)
    print(f"[census] headline window {H.HEADLINE_HORIZON_S}s, headline lens "
          f"{H.HEADLINE_LENS}, arms {ARMS}", flush=True)

    P.require_present("print", NPZ_PRINT)
    P.require_present("mid", NPZ_MID)
    zp = np.load(NPZ_PRINT)
    zm = np.load(NPZ_MID)
    # The two panels are the SAME fills in the same order under two reference prices,
    # which is the property the m2 site relies on when it labels wallets off one panel
    # and measures them on the other. Asserted rather than assumed: a silent misalign
    # would attribute one wallet's later behaviour to another and raise nothing.
    for col in ("taker_id", "coin", "day"):
        assert np.array_equal(zp[col], zm[col]), (
            f"the trade-print and book-mid panels disagree on {col!r}, so they are not "
            "the same rows in the same order and no quantity below can be measured "
            "across the two")
    print(f"[census] {zp['taker_id'].size:,} fills, panels aligned", flush=True)

    anchors = {
        "m2": json.load(open(IN_M2)),
        "ws1": json.load(open(IN_WS1)),
        "ws2": json.load(open(IN_WS2)),
        "ws3": json.load(open(IN_WS3)),
        "frame": json.load(open(IN_FRAME)),
    }

    cal = Calibration()
    # THE KEY CARRIES NO FILE EXTENSION, and that is a repair rather than a style.
    # These keys used to be spelled with their ".py", which reads well and is
    # unaddressable: an address is split on the dot, so `sites.m2_figure.py.arms...`
    # descends into a key `m2_figure` that does not exist and resolves to nothing.
    # Measured on 2026-08-05 with the register's own resolver, checks/chk_prose_numbers
    # .resolve: 261 of this artifact's 325 numeric leaves could not be reached by their
    # own path, and every one of the 261 sat under a key holding a dot, while all 64
    # that were reachable sat under keys without one. The figures were in the file and
    # no consumer could name them, which is the same as not publishing them. The
    # producer's full file name is not lost by this: it stands in the `producer` field
    # of each site block, which is where a name belongs rather than in an address.
    sites = {
        "m2_figure": site_m2(zp, zm, cal, anchors),
        "ws1_horizon_persistence": site_ws1(zm, cal, anchors),
        "ws2_hard_classifier": site_ws2(zm, cal, anchors),
        "ws3_taker_pnl": site_ws3(zm, cal, anchors),
        "build_toxicity_frame": site_frame(zm, cal, anchors),
    }

    if not cal.report():
        print("[census] REFUSED: nothing is written. The committed arm has to return "
              "the published population before a counterfactual measured against it "
              "means anything", flush=True)
        return 1

    axis_findings = check_axis(sites)
    if axis_findings:
        for f in axis_findings:
            print(f"[census] REFUSED on the axis: {f}", flush=True)
        return 2

    decomp = calibrate_decomposition(sites)
    if not decomp["passed"]:
        for f in decomp["findings"]:
            print(f"[census] REFUSED on the loss predicate: {f}", flush=True)
        return 3

    early_days, late_days = H.split_early_late(np.unique(zm["day"]))
    payload = {
        "axis": {
            "what_differs":
                "the number of fills the LATER window is required to hold. Nothing "
                "else differs between the three arms of any comparison in this file",
            "arms": {arm: _late_floor_of(arm, 0) if arm != "as_committed"
                     else "the site's own floor" for arm in ARMS},
            "held_equal":
                "per site: the two panels and their row order, the ranking column, the "
                "lens, the day split, the floor applied to the ranking half, the decile "
                "quantile and the resampling budget. Each is recorded under the site's "
                "held_equal key and compared across its arms; a difference stops the run",
            "differs_by_consequence":
                "the admitted population, the decile threshold taken on it, which "
                "wallets fall either side of that threshold, and every quantity "
                "measured on them. These follow FROM the axis and are the answer, not "
                "a confound",
        },
        "arms": {
            "early_only":
                "the floor in the ranking half and no requirement at all on the later "
                "one. The only arm that consults nothing after the moment of ranking",
            "as_committed":
                "the floor in the ranking half and the same floor again in the later "
                "one. What the five producers ship",
            "late_at_least_one":
                "the floor in the ranking half and one fill in the later one. The "
                "loosest rule under which a later measurement exists at all",
        },
        "sites": sites,
        "totals": {
            "n_sites": len(sites),
            "n_sites_with_floor_above_one": sum(
                1 for s in sites.values() if s["floor_fills"] > 1),
            "loss_by_site": {name: s["loss_decomposition"]
                             for name, s in sites.items()},
        },
        "predicate_calibration": decomp,
        "addressability": None,   # filled below, once the payload it judges is built
        "calibration": cal.block(),
        "headline_finding": _headline_finding(sites),
        "deliberate_lookahead": {
            "what": "this producer CONTAINS the defect it measures, on purpose, and "
                    "says so here rather than leaving a reader to find it. In the "
                    "as_committed arm of every site, the admitted set is built from a "
                    "reduction over later-half rows and then a threshold is taken over "
                    "that set: at the ws3 site the expression is "
                    "np.quantile(mean_e[elig], TOXIC_Q) with elig carrying the later "
                    "count. That is the same shape checks/chk_decision_lookahead.py "
                    "names in the five producers, and it is here because reproducing "
                    "the rule is the only way to price it",
            "why_it_is_not_the_same_fault": "the five producers take a DECISION under "
                    "that population -- a decile cut whose members are then reported "
                    "as a finding about counterparties. This node takes no decision "
                    "under it: the population is the object of measurement, and the "
                    "two arms beside it exist precisely to say what the rule costs. A "
                    "static reading cannot tell an auditor of a rule from a user of "
                    "it, so the distinction is declared here in words and the gate is "
                    "left to fire",
            "how_to_read_a_finding_against_this_file": "a lookahead finding naming "
                    "survivorship_census.py is expected and is not a regression. What "
                    "would be a regression is the early_only arm acquiring a "
                    "later-half term, because that arm's whole claim is that it "
                    "consults nothing after the ranking; the axis gate above compares "
                    "the three arms' later-window floors on every run and stops the "
                    "run if that arm ever demands more than zero",
        },
        "what_this_licenses":
            "a statement that the five producers rank counterparties whose return to "
            "the later window is already known, together with the size of that "
            "selection and the share of it the threshold rather than the data imposes. "
            "It does NOT license a claim that any published number is wrong: the "
            "committed arm reproduces every published anchor it was calibrated on, and "
            "the counterfactuals are what those numbers become under a different "
            "admission rule, not corrections to them",
    }

    # Judged on the finished payload, then recorded inside it: the gate has to see
    # every key this run will publish, including the ones added last.
    addressable = check_addressable(payload)
    payload["addressability"] = addressable
    if not addressable["passed"]:
        print(f"[census] REFUSED: {addressable['n_keys_holding_a_dot']} key(s) of this "
              f"artifact hold a dot, so no address can reach the leaves beneath them: "
              f"{addressable['keys_holding_a_dot']}", flush=True)
        return 4
    print(f"[census] every key is addressable; the resolver splits on the dot and no "
          f"key holds one", flush=True)

    scope_block = {
        "population":
            f"the {int(zp['taker_id'].size):,} taker fills of the December window, "
            f"grouped into the unit each of the five admission sites uses, and counted "
            f"under three admission rules per site",
        "window":
            f"days {min(early_days)}-{max(late_days)}, split by "
            f"settings.split_early_late into early {list(early_days)} and late "
            f"{list(late_days)}",
        "coins": list(H.coin_labels("quickwin").values()),
        "early_days": [int(d) for d in early_days],
        "late_days": [int(d) for d in late_days],
        "lens": "both: the admission of four sites is on the book-mid column and of "
                "one on the trade-print column, and the recomputed separation is "
                "reported under both",
        "horizon_s": H.HEADLINE_HORIZON_S,
    }

    out = artifact.write(
        OUT_NAME, payload,
        script=__file__,
        inputs=[NPZ_PRINT, NPZ_MID, IN_M2, IN_WS1, IN_WS2, IN_WS3, IN_FRAME],
        scope=scope_block,
        started=T0,
        settings=dict(
            h=H.HEADLINE_HORIZON_S,
            lens="both",
            master_seed=H.MASTER_SEED,
            n_boot=H.boot_draws("ws3_taker_pnl"),
            rank_floor_fills=sorted({s["floor_fills"] for s in sites.values()}),
            persistence_floor_fills=None,
            whale_drop_k=None,
            fdr_alpha=None,
            early_late_split=(
                f"settings.split_early_late over the days present: early "
                f"{list(early_days)}, late {list(late_days)}"),
            overrides_note=(
                "rank_floor_fills is a LIST here and not a scalar, because this node "
                "censuses five sites that apply four different floors and reproducing "
                "each site's own floor is the point of it; the floors are read from "
                "settings.wallet_fill_floor and from RANK_FLOOR_SENSITIVITY, never "
                "typed. n_boot is settings.boot_draws('ws3_taker_pnl'), stated as a "
                "CONFIRMATION rather than a deviation: the interval recomputed here is "
                "that producer's interval under a different admission, so it draws that "
                "producer's budget. whale_drop_k and fdr_alpha are null because nothing "
                "here drops a whale or corrects a family"),
        ),
        extra_meta={
            "what_this_is":
                "the price of the two-sided admission rule that five producers apply, "
                "counted three ways per site and split into the part the data imposes "
                "and the part the threshold imposes",
        },
    )
    print(f"[census] wrote {os.path.basename(out)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
