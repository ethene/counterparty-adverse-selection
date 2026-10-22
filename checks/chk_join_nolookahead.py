"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-20
References: Hyperliquid node-data S3 archive (s3://hl-mainnet-node-data); Zenodo 18184441 (Albers et al. 2026).

PURE SYNTHETIC unit test of the no-lookahead as-of join used in the markout
pipeline. NO data load — this exercises the join arithmetic on hand-built arrays
so a reviewer can validate end-to-end cheaply and instantly.

What this GROUND-TRUTHS (vs trusting the convention):
  build_quickwin_markouts.price_at:
    idx = searchsorted(print_ts, q, side="right") - 1   (last print AT-OR-BEFORE q)
    idx < 0                         -> nan
    q > last_print (separate mask)  -> nan
  i4_midmarkout.join_entry / join_horizon (the entry-vs-horizon ASYMMETRY):
    entry   : searchsorted(t, t_fill,        side="left")  - 1   last STRICTLY BEFORE
    horizon : searchsorted(t, t_fill+h*1000, side="left")        first AT-OR-AFTER

The entry rule changed 2026-08-02 from at-or-before to STRICTLY before: a snapshot
stamped with the fill's own millisecond carries that fill's impact, and 13.18 per cent
of real fills were taking their entry mid from one. The entry leg is now CALLED from
i4_midmarkout rather than mirrored here, because a guard that re-types the logic it
guards is blind to the logic changing.

The convention is the thing being TESTED. Each assertion compares the mirrored
join output to a hand-derived no-lookahead expectation. Any single failure ->
the join would be capable of lookahead -> verdict "refuted". --smoke runs the
identical (already tiny) suite.
"""

import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# The producer this gate CALLS rather than mirrors, i4_midmarkout, sits in the data
# group rather than at the top of the repository, so its directory is named here. It is
# built from this file's own location, so nothing absolute is recorded.
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))
import artifact                                                 # noqa: E402
from evidence import report_contract                            # noqa: E402

CHECK_NAME = "join_nolookahead"

# THE OUTPUT NAME IS A LITERAL, AND THAT IS A REPAIR MEASURED ON 2026-08-04.
#
# It used to read f"{CHECK_NAME}_results.json". To Python that is one string. To the
# build graph it is a WILDCARD: build._fold turns every substituted piece of an
# f-string into a star, so this node declared its output as *_results.json and the
# graph read this check as the producer of 74 of the 102 artifact names it knows.
#
# The cost is not cosmetic, and it runs in both directions at once. A name standing
# for 74 files cannot have one producer condition put against it, so build.status()
# answers "cannot be told" for this node on every run and it is never provably
# current -- while the file this check does write, join_nolookahead_results.json, is
# absent from the graph entirely and therefore has no producer at all. Between those
# two, the staleness of somebody else's results file reached this node and put it in
# a recompute plan, and the build classifies it as a raw-tape walker because it calls
# into i4_midmarkout. Hours of counting, ordered by a declaration.
#
# So the name is written once, as a constant with no substitution in it, and the
# spelling assembled from CHECK_NAME is kept only as the guard below, which fails
# loudly rather than letting the two drift apart in silence.
OUT_NAME = "join_nolookahead_results.json"
if OUT_NAME != f"{CHECK_NAME}_results.json":
    raise SystemExit(
        f"the two spellings of this check's output disagree: OUT_NAME is {OUT_NAME!r} "
        f"and CHECK_NAME gives {CHECK_NAME}_results.json. OUT_NAME is the one the "
        f"build graph reads, because a name assembled at run time folds to a wildcard "
        f"there; fix OUT_NAME in checks/chk_join_nolookahead.py")
OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), OUT_NAME)


# ---------------------------------------------------------------------------
# Mirrored logic (copied arithmetic, NOT imported, so the test is self-contained
# and pins the exact convention the writers assume).
# ---------------------------------------------------------------------------
def price_at(print_ts, print_px, query):
    """Mirror of build_quickwin_markouts.price_at (lines 414-419)."""
    idx = np.searchsorted(print_ts, query, side="right") - 1
    out = np.full(np.asarray(query).shape, np.nan, dtype=np.float64)
    valid = idx >= 0
    out[valid] = print_px[idx[valid]]
    return out


def markout_ref(print_ts, print_px, query):
    """Mirror of the reference-price step inside compute_markouts_all:
    price_at(...) then the separate `tq > last_print -> nan` guard (line 434)."""
    ref = price_at(print_ts, print_px, query)
    if print_ts.size:
        last_print = print_ts[-1]
        ref[np.asarray(query) > last_print] = np.nan
    else:
        ref[:] = np.nan
    return ref


def entry_idx(t_arr, t_fill):
    """The producer's own entry index: last snapshot STRICTLY EARLIER than t_fill.

    CALLED, NOT MIRRORED, since 2026-08-02. This used to be a hand-copy described as a
    mirror of i4_midmarkout.join_entry "line 131" -- a line number that had already moved
    -- and when the producer changed its rule the copy silently kept the old one. A guard
    that re-types the logic it guards is blind to exactly the change it exists to catch.
    The gap and GAP_MAX_MS validity live in the producer too; this wrapper keeps the
    (idx, valid) shape the rest of this file expects."""
    import i4_midmarkout as I4
    idx, _gap, valid = I4.join_entry(np.asarray(t_fill), {"t_ms": np.asarray(t_arr)})
    return idx, valid


def horizon_idx(t_arr, t_fill, h_s):
    """Mirror of i4_midmarkout.join_horizon index (line 148): first AT-OR-AFTER
    t_fill + h*1000. Returns (idx, valid) where idx>=n is invalid."""
    target = t_fill + h_s * 1000
    idx = np.searchsorted(t_arr, target, side="left")
    valid = idx < t_arr.size
    return idx, valid


# ---------------------------------------------------------------------------
# Test suite. Each entry appends one record to `checks`. A failure flips its
# verdict to "refuted" and records the discrepancy in `note`.
# ---------------------------------------------------------------------------
def run_checks():
    checks = []

    # Shared synthetic print ladder.
    print_ts = np.array([10, 20, 30], dtype=np.int64)
    print_px = np.array([1.0, 2.0, 3.0], dtype=np.float64)

    # --- 1. interior query 25 -> 2.0 (last at-or-before, NEVER the future 3.0)
    q = np.array([25], dtype=np.int64)
    got = price_at(print_ts, print_px, q)
    exp = 2.0
    ok = np.isfinite(got[0]) and got[0] == exp
    checks.append({
        "name": "price_at_interior_no_lookahead",
        "assumption": "price_at returns the last print at-or-before q (side='right'-1); "
                      "it must never reach forward to a later print",
        "method": "price_at([10,20,30],[1,2,3], q=25)",
        "observed": {"got": _num(got[0]), "expected": exp,
                     "future_value_that_must_not_appear": 3.0},
        "verdict": "confirmed" if ok else "refuted",
        "note": "25 sits between print@20 and print@30; correct ref is 2.0. "
                "Getting 3.0 would be lookahead." if ok
                else f"LOOKAHEAD/MISJOIN: got {_num(got[0])}, expected {exp}.",
    })

    # --- 2. boundary query 30 -> 3.0 (at-or-before INCLUDES equal, via side='right'-1)
    q = np.array([30], dtype=np.int64)
    got = price_at(print_ts, print_px, q)
    exp = 3.0
    ok = np.isfinite(got[0]) and got[0] == exp
    checks.append({
        "name": "price_at_boundary_inclusive",
        "assumption": "an exact-timestamp match is included as at-or-before "
                      "(side='right' places q after the equal element, -1 lands on it)",
        "method": "price_at([10,20,30],[1,2,3], q=30)",
        "observed": {"got": _num(got[0]), "expected": exp},
        "verdict": "confirmed" if ok else "refuted",
        "note": "q==last print picks that print, not nan." if ok
                else f"BOUNDARY WRONG: got {_num(got[0])}, expected {exp}.",
    })

    # --- 3. before-first query 9 -> nan (idx == -1)
    q = np.array([9], dtype=np.int64)
    got = price_at(print_ts, print_px, q)
    ok = np.isnan(got[0])
    raw_idx = int(np.searchsorted(print_ts, 9, side="right") - 1)
    checks.append({
        "name": "price_at_before_first_nan",
        "assumption": "a query before every print yields idx -1 -> nan (no price to carry back)",
        "method": "price_at([10,20,30],[1,2,3], q=9); inspect searchsorted idx",
        "observed": {"got": _num(got[0]), "searchsorted_idx": raw_idx,
                     "expected": "nan"},
        "verdict": "confirmed" if ok else "refuted",
        "note": "idx=-1 -> nan, as required." if ok
                else f"EXPECTED nan for pre-first query, got {_num(got[0])}.",
    })

    # --- 4. after-last query 35 with last_print mask at 30 -> nan
    # price_at alone would carry 3.0 forward forever; the separate
    # `tq > last_print -> nan` guard must blank it.
    q = np.array([35], dtype=np.int64)
    pa = price_at(print_ts, print_px, q)            # carries 3.0 forward
    ref = markout_ref(print_ts, print_px, q)        # guard blanks it
    ok = (pa[0] == 3.0) and np.isnan(ref[0])
    checks.append({
        "name": "after_last_print_masked_nan",
        "assumption": "price_at carries the last price forward, but the explicit "
                      "tq>last_print mask blanks horizons past the last observed print",
        "method": "price_at(q=35)==3.0 carried; then tq>last_print(30) guard -> nan",
        "observed": {"price_at_carried": _num(pa[0]),
                     "after_mask": _num(ref[0]), "last_print": 30},
        "verdict": "confirmed" if ok else "refuted",
        "note": "carry-forward is real but the mask removes it -> no fabricated "
                "future price." if ok
                else (f"MASK FAILED: carried={_num(pa[0])}, masked={_num(ref[0])} "
                      "(expected carried==3.0 then nan)."),
    })

    # --- 5. entry-vs-horizon ASYMMETRY (i4_midmarkout join_entry / join_horizon)
    # snapshot grid every 1000 ms: t = [1000,2000,3000,4000,5000]
    # a fill lands EXACTLY on a snapshot -> entry and horizon resolve the two
    # different sides of the same boundary.
    t_arr = np.array([1000, 2000, 3000, 4000, 5000], dtype=np.int64)
    t_fill = np.array([3000], dtype=np.int64)  # fill exactly on snapshot idx 2

    e_idx, e_valid = entry_idx(t_arr, t_fill)
    # entry: last AT-OR-BEFORE t_fill -> idx 2 (t=3000), inclusive of equal.
    entry_ok = e_valid[0] and int(e_idx[0]) == 1

    h_idx, h_valid = horizon_idx(t_arr, t_fill, 1)  # target = 3000+1000 = 4000
    # horizon: first AT-OR-AFTER target -> idx 3 (t=4000), inclusive of equal,
    # NEVER reaching backward.
    horizon_ok = h_valid[0] and int(h_idx[0]) == 3

    # The asymmetry itself. CHANGED 2026-08-02, and the reason is a real defect, not a
    # convenience: for a fill landing exactly on a snapshot the entry leg must resolve to
    # the snapshot BEFORE it, index 1, not to the equal one at index 2. A snapshot
    # stamped with the fill's own millisecond already carries that fill's impact, so
    # using it as the entry mid measures the trade against its own footprint. Measured on
    # the real tape before the change: 326,849 of 2,480,267 fills (13.18 per cent) took
    # their entry mid from a same-instant snapshot, against 0.18 per cent under a random
    # join, and the notional-weighted 10s harm on that stratum read +0.52 bps against
    # +2.29 bps on the rest -- the published pooled figure was a mixture and understated
    # the harm, which the fix raised from 2.0616 to 2.2388 bps.
    #
    # The horizon leg is unchanged: first AT-OR-AFTER t_fill + h*1000. So the asymmetry
    # this sub-check exists to pin is now STRICTLY-BEFORE against at-or-after, and the
    # h=0 probe is what discriminates: at equality the entry leg must step back and the
    # horizon leg must stay.
    h0_idx, h0_valid = horizon_idx(t_arr, t_fill, 0)  # target == t_fill == 3000
    # first AT-OR-AFTER 3000 -> idx 2 (the equal one), via side='left'
    h0_ok = h0_valid[0] and int(h0_idx[0]) == 2
    asym_ok = entry_ok and horizon_ok and h0_ok
    checks.append({
        "name": "entry_horizon_asymmetry",
        "assumption": "entry uses searchsorted side='left'-1 (last STRICTLY BEFORE); "
                      "horizon uses side='left' (first at-or-after t_fill+h*1000). "
                      "These opposite sides are what make the join causal at both legs.",
        "method": "fill exactly on snapshot t=3000 in grid [1000..5000]; "
                  "entry_idx, horizon_idx(h=1), horizon_idx(h=0) checked vs hand value",
        "observed": {
            "entry_idx": int(e_idx[0]), "entry_expected": 1,
            "horizon_h1_idx": int(h_idx[0]), "horizon_h1_expected": 3,
            "horizon_h0_idx": int(h0_idx[0]), "horizon_h0_expected": 2,
            "entry_side": "left-1 (strictly before)",
            "horizon_side": "left (at-or-after)",
        },
        "verdict": "confirmed" if asym_ok else "refuted",
        "note": "entry lands strictly before the boundary; horizon lands on the "
                "at-or-after boundary; the two legs use opposite searchsorted "
                "sides as the code assumes." if asym_ok
                else (f"ASYMMETRY BROKEN: entry_idx={int(e_idx[0])}(exp 1) "
                      f"h1_idx={int(h_idx[0])}(exp 3) h0_idx={int(h0_idx[0])}(exp 2)."),
    })

    # --- 6. horizon out-of-range -> invalid (target past the last snapshot)
    far_fill = np.array([4500], dtype=np.int64)  # +1000 -> 5500 > last snap 5000
    hf_idx, hf_valid = horizon_idx(t_arr, far_fill, 1)
    ok = (not bool(hf_valid[0])) and int(hf_idx[0]) == t_arr.size
    checks.append({
        "name": "horizon_out_of_range_invalid",
        "assumption": "a horizon target past the last snapshot gives idx==n -> invalid "
                      "(no future snapshot is invented)",
        "method": "horizon_idx(t_fill=4500, h=1) -> target 5500 > last snapshot 5000",
        "observed": {"idx": int(hf_idx[0]), "n_snapshots": int(t_arr.size),
                     "valid": bool(hf_valid[0])},
        "verdict": "confirmed" if ok else "refuted",
        "note": "out-of-range horizon correctly flagged invalid." if ok
                else f"OOR NOT FLAGGED: idx={int(hf_idx[0])}, valid={bool(hf_valid[0])}.",
    })

    # --- 7. vectorized regression: a batch of queries reproduces all the
    # single-point expectations at once (guards against shape/broadcast bugs).
    batch_q = np.array([9, 10, 15, 20, 25, 30, 31], dtype=np.int64)
    batch_ref = markout_ref(print_ts, print_px, batch_q)
    expected = np.array([np.nan, 1.0, 1.0, 2.0, 2.0, 3.0, np.nan])
    vok = np.all(
        (np.isnan(batch_ref) & np.isnan(expected)) |
        (np.isclose(batch_ref, expected))
    )
    checks.append({
        "name": "vectorized_markout_ref_batch",
        "assumption": "the masked reference is monotone-step and never anticipates: "
                      "[<10]->nan, [10,20)->1, [20,30)->2, ==30->3, [>30]->nan",
        "method": "markout_ref over q=[9,10,15,20,25,30,31]",
        "observed": {"q": batch_q.tolist(),
                     "got": [_num(x) for x in batch_ref.tolist()],
                     "expected": [_num(x) for x in expected.tolist()]},
        "verdict": "confirmed" if bool(vok) else "refuted",
        "note": "step-function join with no lookahead reproduced vectorized." if vok
                else "VECTORIZED MISMATCH vs hand-derived step function.",
    })

    return checks


def _num(x):
    """JSON-safe float: NaN/inf -> string tokens so the contract stays valid JSON."""
    f = float(x)
    if np.isnan(f):
        return "nan"
    if np.isinf(f):
        return "inf" if f > 0 else "-inf"
    return f


def main():
    started = artifact.start_clock()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--smoke", action="store_true",
                    help="tiny slice (this suite is already tiny; behaves identically)")
    ap.parse_args()

    checks = run_checks()
    verdicts = {c["verdict"] for c in checks}
    if "refuted" in verdicts:
        overall = "refuted"
    elif "uncertain" in verdicts:
        overall = "uncertain"
    else:
        overall = "confirmed"

    payload = {"check": CHECK_NAME, "checks": checks, "overall_verdict": overall}
    # The literal name, not os.path.basename(OUT_PATH). The build graph reads the
    # first argument of this call to learn what this script produces, and it can only
    # read a name that is written down: folding a path expression recovers the last
    # literal component, so anything assembled at run time arrives there as a star.
    artifact.write(
        OUT_NAME, payload,
        script=__file__,
        # An EMPTY input list, and it is a statement rather than an omission: every
        # array this suite joins is built in the file itself, so there is no input
        # whose hash could change the answer.
        inputs=[],
        scope={
            "population": f"{len(checks)} hand-built join fixtures, not market data",
            "window": "n/a: the fixtures carry synthetic timestamps chosen to put a "
                      "forward reach within reach of the join",
            "coins": "n/a: the fixtures carry no coin",
        },
        started=started,
    )

    n_ref = sum(c["verdict"] == "refuted" for c in checks)
    print(f"[{CHECK_NAME}] {len(checks)} sub-checks | refuted={n_ref} | "
          f"OVERALL={overall.upper()} | wrote {OUT_NAME}")
    # A refuted sub-check here means the as-of join is capable of reaching forward in
    # time, which would put a future price into a markout. That has to stop the run,
    # and it has to say which query, which expectation and which index disagreed:
    # until 2026-07-30 this file wrote "refuted" into its own results and exited 0.
    return report_contract(payload, OUT_PATH,
                           inputs={"data": "none: hand-built arrays, no file read"})


if __name__ == "__main__":
    sys.exit(main())
