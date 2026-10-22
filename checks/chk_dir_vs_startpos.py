"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-20
References: Hyperliquid node-data S3 archive (s3://hl-mainnet-node-data); Zenodo 18184441 (Albers et al. 2026).

RE-VERIFICATION CHECK - dir parsing vs inventory sign (chk_dir_vs_startpos).

WHAT THIS GROUND-TRUTHS
-----------------------
The npz carries two fields that the writer (build_quickwin_markouts.py) reads from
the SAME earliest-block_time leg of each collapsed taker trade, as two independent
JSON keys read from the SAME upstream fill object:
  - dir_code : the fill `dir` STRING mapped via
        DIR_CODE = {"Open Long": 0, "Open Short": 1, "Close Long": 2, "Close Short": 3}
        (-1 = unknown). is_open == 1 iff dir_code in {0, 1} (OPEN_DIRS).
  - start_pos: the signed `startPosition` NUMBER (pre-trade inventory).

CAVEAT - this test cannot catch a COMMON-MODE upstream semantic error: if
Hyperliquid emits both `dir` and `startPosition` consistently-but-wrong, the 100%
agreement is just an exchange-accounting tautology and the check is blind to it
(the closedPnl check is a third-key corroboration against exactly that).

Because these two come from different raw keys, they are an INTERNAL CROSS-CHECK:
if the `dir` string is parsed/mapped correctly AND the `startPosition` sign
convention is what we assume (+ = long, - = short), then a CLOSE fill must reduce
an existing position, so:
  - Close Long  (dir_code 2) => pre-trade position is LONG  => start_pos > 0
  - Close Short (dir_code 3) => pre-trade position is SHORT => start_pos < 0
  - Open from flat (dir_code 0/1) => start_pos ~ 0 (but an OPEN that EXTENDS an
    existing position is also tagged "Open Long/Short", so opens legitimately mix
    in nonzero same-sign inventory; we therefore report opens diagnostically, not
    as a pass/fail gate).

We do NOT assume the convention is correct; we TEST it and emit a verdict. A
sign-flip in start_pos OR a wrong dir map would show up as Close Long being
predominantly negative (or Close Short predominantly positive).

CONTRACT (written to chk_dir_vs_startpos_results.json):
  { "check": "...", "checks": [ {name, assumption, method, observed, verdict, note} ],
    "overall_verdict": "confirmed|refuted|uncertain" }

Run (bare python3 is BLOCKED on this machine):
  uv run --no-project --with-requirements requirements.txt python3 checks/chk_dir_vs_startpos.py
  uv run --no-project --with-requirements requirements.txt python3 checks/chk_dir_vs_startpos.py --smoke
"""

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from evidence import report_contract                            # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CODE_DIR = os.path.dirname(HERE)
if CODE_DIR not in sys.path:
    sys.path.insert(0, CODE_DIR)
import artifact                                                 # noqa: E402
import panel_io as P                                            # noqa: E402

# LOCATED by panel_io rather than joined against this file's own directory, so the one
# place that knows where the markout panels live is the one place that has to change if
# they move. With none of the environment variables panel_io honours set, data_root()
# returns the directory the module itself lives in, which is CODE_DIR -- the path this
# line resolved to before, so the file this check reads does not change.
#
# The np.load below stays where it is: build.py derives an input edge by folding the
# argument of np.load to a constant, and a path it cannot fold makes no edge at all.
# The missing-file branch further down is also left alone on purpose -- it WRITES a
# not-applicable artifact rather than raising, which panel_io.require_present would not
# do, and replacing it would change what this check publishes when the panel is absent.
NPZ_PATH = os.path.join(P.data_root(), "quickwin_markouts.npz")
RESULTS_PATH = os.path.join(HERE, "chk_dir_vs_startpos_results.json")

CHECK_NAME = "chk_dir_vs_startpos"

# Mirror of build_quickwin_markouts.py (READ from source, not invented). The
# writer maps the raw `dir` string to these integer codes; we re-state them here
# only to LABEL the cross-tab, never to overwrite what is on disk.
DIR_CODE = {"Open Long": 0, "Open Short": 1, "Close Long": 2, "Close Short": 3}
CODE_TO_DIR = {v: k for k, v in DIR_CODE.items()}
CODE_TO_DIR[-1] = "unknown"
OPEN_CODES = {0, 1}   # is_open == 1 iff dir_code in OPEN_DIRS

SMOKE_ROWS = 200_000          # --smoke processes the first 200k rows only
DOMINANT_THRESHOLD = 0.70     # an expected cell must hold > this fraction to pass

# start_pos is float32; treat |start_pos| < tol as "flat". A relative tolerance is
# meaningless here (inventory is in coin units, scale varies BTC vs ETH vs SOL),
# so use a small absolute floor plus a data-driven check that it is well below the
# typical |start_pos| of close fills.
ZERO_TOL = 1e-9


def _sign_bucket(start_pos, tol):
    """Return (n_pos, n_zero, n_neg, n_nan) for a start_pos slice."""
    nan = np.isnan(start_pos)
    finite = ~nan
    sp = start_pos[finite]
    near_zero = np.abs(sp) < tol
    pos = sp > tol
    neg = sp < -tol
    return int(pos.sum()), int(near_zero.sum()), int(neg.sum()), int(nan.sum())


def _frac(num, den):
    return float(num) / float(den) if den else float("nan")


def main():
    started = artifact.start_clock()
    smoke = "--smoke" in sys.argv

    if not os.path.exists(NPZ_PATH):
        # Emit a contract-shaped uncertain result rather than crashing.
        out = {
            "check": CHECK_NAME,
            "checks": [{
                "name": "npz_present",
                "assumption": "quickwin_markouts.npz exists next to the writer",
                "method": "os.path.exists",
                # THE NAME, NEVER THE PATH. NPZ_PATH is absolute, and on the machine
                # this was written on it begins with an account name; written here it
                # would put that name into a published artifact, which
                # checks/chk_no_abs_paths.py forbids outright. The branch only fires when
                # the file is absent, so on a tree that has it the record stayed clean
                # by luck rather than by construction. Measured in a clean clone: the
                # field held the full path of the clone's own directory.
                "observed": {"file": os.path.basename(NPZ_PATH), "exists": False},
                "verdict": "uncertain",
                "note": "input npz not found; cannot cross-validate dir vs start_pos",
            }],
            "overall_verdict": "uncertain",
        }
        # The input is named in `inputs` even though it is absent: input_record
        # writes present=false for it, which is the record that says the check ran
        # and found nothing, as against the check never having run.
        artifact.write(
            os.path.basename(RESULTS_PATH), out,
            script=__file__,
            inputs=[NPZ_PATH],
            scope={
                "population": "0 rows: the markout slice this check reads is not on "
                              "disk in this clone, so nothing was examined",
                "window": "n/a: no data was read",
                "coins": "n/a: no data was read",
            },
            started=started,
            # answered=False: this stub is 2,307 bytes against the 6,785 the answering
            # run leaves, and the difference is the agreement it demonstrates. A reader
            # who clones and runs the gates keeps that demonstration.
            answered=False,
        )
        print(f"[{CHECK_NAME}] UNCERTAIN: npz missing at "
              f"{os.path.basename(NPZ_PATH)}")
        return report_contract(out, RESULTS_PATH,
                               inputs={"npz": NPZ_PATH})

    data = np.load(NPZ_PATH, allow_pickle=False)
    dir_code = data["dir_code"].astype(np.int64)
    start_pos = data["start_pos"].astype(np.float64)
    is_open = data["is_open"].astype(np.int64)
    n_total = dir_code.shape[0]

    if smoke:
        n = min(SMOKE_ROWS, n_total)
        dir_code = dir_code[:n]
        start_pos = start_pos[:n]
        is_open = is_open[:n]
    n_used = dir_code.shape[0]

    checks = []

    # ---- CHECK 1: dir_code <-> is_open consistency (cheap sanity on the codes) ----
    # is_open must equal (dir_code in {0,1}); if it does not, the two fields were not
    # derived from the same leg and the rest of the cross-tab is meaningless.
    expected_open = np.isin(dir_code, list(OPEN_CODES)).astype(np.int64)
    # unknown dir_code (-1) is is_open=0 in the writer (not in OPEN_DIRS); align that.
    mism = int(np.sum(expected_open != is_open))
    checks.append({
        "name": "dir_code_implies_is_open",
        "assumption": "is_open == 1 iff dir_code in {0=Open Long,1=Open Short}",
        "method": "compare is_open to (dir_code in {0,1}) row-by-row",
        "observed": {
            "rows": n_used,
            "mismatches": mism,
            "mismatch_frac": _frac(mism, n_used),
        },
        "verdict": "confirmed" if mism == 0 else "refuted",
        "note": ("is_open is a deterministic function of dir_code; any mismatch "
                 "means the two were not read from the same leg"),
    })

    # ---- CHECK 2: full cross-tab dir_code x sign(start_pos) ----
    crosstab = {}
    for code in [0, 1, 2, 3, -1]:
        sel = dir_code == code
        n_code = int(sel.sum())
        n_pos, n_zero, n_neg, n_nan = _sign_bucket(start_pos[sel], ZERO_TOL)
        n_finite = n_pos + n_zero + n_neg
        crosstab[CODE_TO_DIR[code]] = {
            "code": code,
            "n_rows": n_code,
            "n_start_pos_positive": n_pos,
            "n_start_pos_near_zero": n_zero,
            "n_start_pos_negative": n_neg,
            "n_start_pos_nan": n_nan,
            "frac_positive": _frac(n_pos, n_finite),
            "frac_near_zero": _frac(n_zero, n_finite),
            "frac_negative": _frac(n_neg, n_finite),
        }

    checks.append({
        "name": "dir_x_startpos_crosstab",
        "assumption": ("start_pos sign convention: + = long, - = short "
                       "(pre-trade inventory)"),
        "method": ("cross-tabulate dir_code against sign(start_pos) with a "
                   f"near-zero bucket |start_pos| < {ZERO_TOL}; report fractions "
                   "over finite rows"),
        "observed": crosstab,
        "verdict": "confirmed",  # diagnostic table; the gating verdict is in CHECK 3
        "note": ("descriptive cross-tab; the directional expectation is evaluated "
                 "in the close_fills_reduce_inventory check"),
    })

    # ---- CHECK 3: the GATING directional test on CLOSE fills ----
    # This is the field-semantics ground-truth. Opens can legitimately extend an
    # existing position (nonzero same-sign inventory), so opens are NOT gated.
    # Closes are unambiguous: closing/reducing requires a pre-trade position of the
    # matching sign, independent of any same-leg coupling.
    cl_long = crosstab["Close Long"]
    cl_short = crosstab["Close Short"]
    frac_cl_long_pos = cl_long["frac_positive"]
    frac_cl_short_neg = cl_short["frac_negative"]

    # also surface the dominant cell for each expected close direction so a reviewer
    # sees WHICH sign dominates, not just whether the expected one passed.
    def _dominant(cell):
        cand = {
            "positive": cell["frac_positive"],
            "near_zero": cell["frac_near_zero"],
            "negative": cell["frac_negative"],
        }
        # NaN-safe argmax
        best = max(cand.items(), key=lambda kv: (kv[1] if kv[1] == kv[1] else -1.0))
        return best[0], best[1]

    cl_long_dom_sign, cl_long_dom_frac = _dominant(cl_long)
    cl_short_dom_sign, cl_short_dom_frac = _dominant(cl_short)

    # verdict logic:
    #  confirmed  -> Close Long mostly positive AND Close Short mostly negative
    #  refuted    -> a sign flip: Close Long mostly negative OR Close Short mostly positive
    #  uncertain  -> neither cleanly dominates (e.g. both near-zero / sparse)
    long_ok = (frac_cl_long_pos == frac_cl_long_pos) and frac_cl_long_pos > DOMINANT_THRESHOLD
    short_ok = (frac_cl_short_neg == frac_cl_short_neg) and frac_cl_short_neg > DOMINANT_THRESHOLD

    long_flip = cl_long_dom_sign == "negative" and cl_long_dom_frac > DOMINANT_THRESHOLD
    short_flip = cl_short_dom_sign == "positive" and cl_short_dom_frac > DOMINANT_THRESHOLD

    if long_flip or short_flip:
        close_verdict = "refuted"
    elif long_ok and short_ok:
        close_verdict = "confirmed"
    else:
        close_verdict = "uncertain"

    checks.append({
        "name": "close_fills_reduce_inventory",
        "assumption": ("Close Long => start_pos > 0 (was long); "
                       "Close Short => start_pos < 0 (was short). A pass means BOTH "
                       "the dir map and the start_pos sign are read consistently."),
        "method": ("among dir_code==Close Long rows, fraction with start_pos>0; "
                   "among dir_code==Close Short rows, fraction with start_pos<0; "
                   f"each expected cell must exceed {DOMINANT_THRESHOLD}"),
        "observed": {
            "close_long_n": cl_long["n_rows"],
            "close_long_frac_positive_expected": frac_cl_long_pos,
            "close_long_dominant_sign": cl_long_dom_sign,
            "close_long_dominant_frac": cl_long_dom_frac,
            "close_short_n": cl_short["n_rows"],
            "close_short_frac_negative_expected": frac_cl_short_neg,
            "close_short_dominant_sign": cl_short_dom_sign,
            "close_short_dominant_frac": cl_short_dom_frac,
            "threshold": DOMINANT_THRESHOLD,
        },
        "verdict": close_verdict,
        "note": ("the decisive field-semantics ground-truth: two independent JSON "
                 "keys read from the same upstream fill object (dir string, "
                 "startPosition number) must agree on the close direction; blind to "
                 "a common-mode upstream error (closedPnl is a third-key corroborant)"),
    })

    # ---- CHECK 4: opens-from-flat diagnostic (informational, not gated) ----
    # If most OPENS came from flat, opens would cluster near zero. Extensions of an
    # existing position legitimately move opens off zero, so we report but do not
    # gate. A surprisingly LOW near-zero fraction here is expected on a busy venue.
    op_long = crosstab["Open Long"]
    op_short = crosstab["Open Short"]
    checks.append({
        "name": "opens_diagnostic",
        "assumption": ("Open-from-flat => start_pos ~ 0; extensions of an existing "
                       "position legitimately make opens nonzero same-sign"),
        "method": "report near-zero / same-sign / opposite-sign fractions for opens",
        "observed": {
            "open_long": {
                "n_rows": op_long["n_rows"],
                "frac_near_zero": op_long["frac_near_zero"],
                "frac_positive_same_sign": op_long["frac_positive"],
                "frac_negative_opposite": op_long["frac_negative"],
            },
            "open_short": {
                "n_rows": op_short["n_rows"],
                "frac_near_zero": op_short["frac_near_zero"],
                "frac_negative_same_sign": op_short["frac_negative"],
                "frac_positive_opposite": op_short["frac_positive"],
            },
        },
        "verdict": "uncertain",
        "note": ("informational only; opens mix flat-opens and extensions so no "
                 "clean directional expectation, NOT used in overall_verdict"),
    })

    # ---- overall verdict: driven by the two GATING checks (1 and 3) ----
    gating = [checks[0]["verdict"], checks[2]["verdict"]]
    if "refuted" in gating:
        overall = "refuted"
    elif all(v == "confirmed" for v in gating):
        overall = "confirmed"
    else:
        overall = "uncertain"

    out = {
        "check": CHECK_NAME,
        "smoke": smoke,
        "rows_total": int(n_total),
        "rows_used": int(n_used),
        "checks": checks,
        "overall_verdict": overall,
    }
    artifact.write(
        os.path.basename(RESULTS_PATH), out,
        script=__file__,
        inputs=[NPZ_PATH],
        scope={
            "population": f"{int(n_used):,} taker fills of the {int(n_total):,} in "
                          f"{os.path.basename(NPZ_PATH)}"
                          + (" (--smoke prefix, NOT representative)" if smoke else ""),
            "window": "the span of quickwin_markouts.npz; the check reads the slice "
                      "whole and does not cut it by date",
            "coins": "every coin present in quickwin_markouts.npz; the agreement of "
                     "direction with the pre-trade position is not cut by coin",
        },
        started=started,
    )

    # ---- one-line human summary ----
    print(
        f"[{CHECK_NAME}] overall={overall} | "
        f"rows={n_used:,}{' (SMOKE)' if smoke else ''} | "
        f"is_open<->dir mism={mism} | "
        f"Close Long +{frac_cl_long_pos:.3f} (dom {cl_long_dom_sign}) | "
        f"Close Short -{frac_cl_short_neg:.3f} (dom {cl_short_dom_sign}) | "
        f"-> {os.path.basename(RESULTS_PATH)}"
    )
    # A refutation here is a sign flip in start_pos or a wrong dir map, which would
    # invert the OPEN/CLOSE split every downstream population is cut on. Until
    # 2026-07-30 it was written into the results file and the run exited 0 regardless.
    return report_contract(
        out, RESULTS_PATH, inputs={"npz": NPZ_PATH},
        # These two carry `uncertain` because they are reported and not judged, not
        # because a leg failed to run: the cross-tab is descriptive and opens mix
        # flat-opens with extensions, so neither has a directional expectation to
        # miss. The gating pair is dir_code_implies_is_open and
        # close_fills_reduce_inventory, and those are not on this list.
        informational=("dir_x_startpos_crosstab", "opens_diagnostic"))


if __name__ == "__main__":
    sys.exit(main())
