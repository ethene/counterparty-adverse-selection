"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-20
"""

# ---------------------------------------------------------------------------
# CHECK_FIRST - a READ-ONLY repro / integrity GATE for the markout intermediates.
#
# This is a LIGHT gate: it loads the two markout .npz intermediates, the small
# t3 result JSON, and the data acquisition log, and asserts the cheap invariants a
# reviewer should be able to confirm in seconds WITHOUT re-running the 10-day
# compute. It writes nothing except its own result JSON and never touches the
# raw archive.
#
# Four checks (mirroring the task spec):
#   1. SCHEMA + DAY COVERAGE. Row counts, column lists, and the set of distinct
#      calendar days each .npz covers. The day is read from the persisted `day`
#      int16 column (day-of-month 4..13 = Dec 4..13 2025); the build script does
#      NOT persist a raw ns block_time column in the .npz (it is consumed during
#      the markout join), so the canonical day key is `day`, mapped here to the
#      Dec-2025 calendar. OPEN QUESTION answered: does the trade-print npz cover
#      7 days (Dec 4-10) or the full 10 (Dec 4-13)?
#   2. ROW ALIGNMENT BY CONTENT. The mid .npz must be row-aligned to the print
#      .npz element-wise on stable key columns (not merely equal length). We
#      compare integer keys exactly and float keys with a tight tolerance, and
#      FAIL the gate if the matching fraction is not ~1.0.
#   3. T3 PER-DAY DIVISOR. Recompute the avoidable-cost $/day with divisor =
#      len(unique(day)) read from the print npz, and compare against the
#      old "/10" assumption and against what t3_results.json actually recorded.
#   4. LOG CONSISTENCY. Does data_acquisition_log.md record an l2Book pull AND a
#      book-mid execution, now that the book-mid execution artifact (i4 mid results)
#      shows the run happened? Flags a log that under-records, or still describes as
#      future work, a run the artifacts show has happened.
#
# REPRODUCIBILITY: no hardcoded user paths. HERE = this file's dir; a
# --data-root / CAP_CHECK_ROOT override relocates the .npz + JSON inputs, and a
# --repo-root / CAP_REPO_ROOT override relocates the acquisition log. Only
# os.path.basename is written into the result JSON. numpy + stdlib only.
#
# Run:
#   uv run --no-project --with-requirements requirements.txt python3 data/check_first.py
# ---------------------------------------------------------------------------

import argparse
import json
import os
import re
import sys

import numpy as np

# One place writes a results file. This gate's own verdict is an artifact like any
# other, so it carries the same _meta block: producer and hash, inputs with their
# hashes, scope, settings fingerprint, run. See artifact.py.
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

SEED = H.MASTER_SEED  # the declared seed; this file already ran on it, so reading it
                      # from settings.py moves no number
np.random.seed(SEED)  # deterministic; no RNG is used but the seed is fixed per contract.

HERE = os.path.dirname(os.path.abspath(__file__))

# --- inputs (basenames; resolved against the roots below) -----------------
# NOT taken from panel_io, and the reason is worth stating because every other reader
# in this tree does take it from there. build.py derives this script's input edges
# from the folded argument of np.load, and it folds a module-level constant but not
# a call into another module. Naming these two through panel_io left three np.load
# calls here that the graph could not account for, against a declared ceiling of
# zero. So the names stay literal until either build.py can fold across a module or
# build_declarations.py carries the two calls that are not already declared there.
PRINT_NPZ = "quickwin_markouts.npz"          # trade-print markout intermediate
MID_NPZ = "quickwin_markouts_mid.npz"        # book-mid markout intermediate
T3_CAPACITY_PY = "t3_capacity.py"            # divisor convention lives here
T3_RESULTS_JSON = "t3_results.json"          # recorded t3 magnitude
I4_MID_RESULTS_JSON = "i4_midmarkout_results.json"  # book-mid execution artifact

# the acquisition log (lives beside the repository, not inside it)
LOG_REL = os.path.join("02_data", "data_acquisition_log.md")

OUT_JSON = "check_first_results.json"

# Dec 2025: day-of-month -> ISO date. The window is Dec 4..13 2025.
DAY_TO_DATE = {d: "2025-12-%02d" % d for d in range(4, 14)}

# Stable key columns shared by both npz, used for the by-content alignment test.
INT_KEYS = ("taker_id", "coin", "day", "taker_side", "dir_code", "is_open", "maker_id")
FLOAT_KEYS = ("entry_px", "notional", "start_pos")

ALIGN_MIN_FRAC = 0.999999  # gate floor: ~1.0 element-wise match required

# A DISCREPANCY THIS GATE COULD NOT ASK ABOUT IS NOT A DISCREPANCY IT FOUND, and the two
# must not share an exit code. Everything this gate reads that is not shipped with the
# code -- the two markout intermediates and the acquisition log --
# is absent in a bare clone, and every one of those absences used to land in the same
# list as a real inconsistency between the writing and the artifacts. A reader who
# clones this repository and runs this gate first, as the README tells them to, would
# then see a count of "discrepancies" made entirely of files they were never given.
#
# Entries carrying this prefix say "not asked". The rest say "asked, and the answer
# disagrees", and only those decide the exit code.
UNASKABLE = "UNASKABLE: "


# Directories that hold copies rather than the file itself, so a walk that looked into
# them would report an ambiguity that does not exist.
_SKIP_DIRS = {".git", "__pycache__", ".ipynb_checkpoints", "node_modules"}


def _directory_holding(root, name):
    """The directory under `root` that holds a file called `name`.

    Hands back a DIRECTORY and never a full path, so that the caller keeps the file name
    as the last component of its own join. That division is not a matter of taste: the
    build derives its dependency graph by folding path expressions, and `_path_helpers`
    in build.py keeps a helper only when it has exactly ONE return, on the stated ground
    that a helper with two returns can hand back two different files and binding it to
    whichever return came first would state an edge the code does not make. All the
    deciding lives here, where several returns are honest and where no I/O call reads
    the result directly; `_resolve` below stays foldable.

    Measured, because this was learned the expensive way: written as one four-return
    function this raised the build's count of unaccounted file operations from 8 to 13
    against a ceiling of 0, and no gate said so -- the battery holds failures against a
    baseline rather than holding the residue, and the sentence naming the debt is typed
    by hand and dated.

    The direct join is tried first, since it is right whenever the file has not moved
    and costs one stat. Two files answering to one name is refused out loud rather than
    resolved by taking the first: choosing silently would be the same defect one layer
    down. A name that is nowhere hands back the conventional directory, so the caller
    reports an absent input in its own words instead of this function deciding what the
    absence means.
    """
    if os.path.exists(os.path.join(root, name)):
        return root
    hits = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        if name in filenames:
            hits.append(dirpath)
    if len(hits) > 1:
        raise SystemExit(
            f"[check_first] {name} answers to {len(hits)} files under this tree: "
            + ", ".join(sorted(os.path.relpath(h, root) for h in hits))
            + ". Refusing to choose: this gate reads one of them and would report a "
              "verdict about a file it did not name")
    return hits[0] if hits else root


def _resolve(root, name):
    """The file called `name` under `root`, found BY NAME rather than at a guessed path.

    THIS USED TO BE `os.path.join(root, name)` AND THAT MADE THIS GATE ACCUSE THIS
    PROJECT'S OWN WRITING OF A CLAIM IT HAD EVIDENCE FOR. Two of the four files named
    here sit one directory below the root today -- money/t3_results.json and
    data/i4_midmarkout_results.json -- because the scripts were sorted into groups. The
    join kept looking where they used to be, found nothing, and check4 concluded that
    the report states a result no execution artifact backs. Measured: the artifact is on
    disk, readable, and says the run happened. So the finding was about this function.

    One return, and the file name is the last component of it. That is what lets the
    build fold `_resolve(data_root, PRINT_NPZ)` at the call site into the name of an
    artifact; the search itself is one call further in, where it may branch freely.
    """
    return os.path.join(_directory_holding(root, name), name)


def _days_from_npz(z):
    """Distinct calendar days from the persisted int16 `day` column."""
    day = np.asarray(z["day"]).astype(np.int64)
    nums = sorted(int(x) for x in np.unique(day))
    dates = [DAY_TO_DATE.get(n, "day-%d" % n) for n in nums]
    return nums, dates


def check_schema_and_days(data_root, disc):
    """Check 1: row counts, columns, and day coverage of each npz."""
    out = {}
    npz_days = {}
    for label, name in (("print", PRINT_NPZ), ("mid", MID_NPZ)):
        path = _resolve(data_root, name)
        if not os.path.exists(path):
            out[label] = {"file": name, "present": False}
            disc.append(UNASKABLE + "missing intermediate: %s" % name)
            continue
        z = np.load(path, allow_pickle=True)
        try:
            cols = list(z.files)
            nrows = int(np.asarray(z[cols[0]]).shape[0]) if cols else 0
            day_nums, day_dates = _days_from_npz(z)
            npz_days[label] = day_nums
            out[label] = {
                "file": name,
                "present": True,
                "rows": nrows,
                "n_columns": len(cols),
                "columns": cols,
                "day_nums": day_nums,
                "day_dates": day_dates,
                "n_days": len(day_nums),
            }
        finally:
            z.close()

    # OPEN QUESTION: 7 days (Dec 4-10) vs full 10 (Dec 4-13)?
    pr = out.get("print", {})
    if pr.get("present"):
        n = pr.get("n_days")
        out["print_day_coverage_verdict"] = (
            "FULL_10_DAYS (Dec 4-13)" if n == 10
            else "SEVEN_DAYS (Dec 4-10)" if n == 7
            else "PARTIAL_%d_DAYS" % (n if n is not None else -1)
        )
        if n != 10:
            disc.append(
                "print npz covers %d distinct days (%s), not the full 10 (Dec 4-13)"
                % (n, ",".join(pr.get("day_dates", [])))
            )

    # row-count parity is a necessary (not sufficient) precondition for alignment
    if out.get("print", {}).get("present") and out.get("mid", {}).get("present"):
        if out["print"]["rows"] != out["mid"]["rows"]:
            disc.append(
                "row-count mismatch: print=%d vs mid=%d"
                % (out["print"]["rows"], out["mid"]["rows"])
            )
        # both npz should cover the same day set
        if npz_days.get("print") != npz_days.get("mid"):
            disc.append(
                "day-set mismatch: print=%s mid=%s"
                % (npz_days.get("print"), npz_days.get("mid"))
            )
    return out


def check_row_alignment(data_root, disc):
    """Check 2: mid npz row-aligned to print npz BY CONTENT on stable keys."""
    pp = _resolve(data_root, PRINT_NPZ)
    mp = _resolve(data_root, MID_NPZ)
    if not (os.path.exists(pp) and os.path.exists(mp)):
        disc.append(UNASKABLE + "alignment skipped: one or both npz absent")
        return {"checked": False, "reason": "npz absent"}

    a = np.load(pp, allow_pickle=True)
    b = np.load(mp, allow_pickle=True)
    try:
        if a[a.files[0]].shape[0] != b[b.files[0]].shape[0]:
            disc.append("alignment FAIL: differing row counts (length test)")
            return {"checked": True, "passed": False, "reason": "length mismatch"}

        per_key = {}
        worst = 1.0
        for k in INT_KEYS:
            if k in a.files and k in b.files:
                frac = float((np.asarray(a[k]) == np.asarray(b[k])).mean())
                per_key[k] = round(frac, 8)
                worst = min(worst, frac)
        for k in FLOAT_KEYS:
            if k in a.files and k in b.files:
                fa = np.asarray(a[k]).astype(np.float64)
                fb = np.asarray(b[k]).astype(np.float64)
                close = np.isclose(fa, fb, rtol=1e-6, atol=1e-9, equal_nan=True)
                frac = float(close.mean())
                per_key[k] = round(frac, 8)
                worst = min(worst, frac)

        passed = worst >= ALIGN_MIN_FRAC and len(per_key) > 0
        if not passed:
            disc.append(
                "alignment FAIL: worst key-match fraction %.8f < %.6f"
                % (worst, ALIGN_MIN_FRAC)
            )
        return {
            "checked": True,
            "passed": bool(passed),
            "keys_compared": sorted(per_key.keys()),
            "match_fraction_by_key": per_key,
            "worst_match_fraction": round(worst, 8),
            "floor": ALIGN_MIN_FRAC,
        }
    finally:
        a.close()
        b.close()


def _signed_total_cost_usd(data_root):
    """Recompute the pooled signed adverse-selection cost over the npz, on the
    headline scoring column (see settings.py).

    Cost convention matches t3_capacity: per row cost_usd = (headline markout in bps / 1e4) *
    notional; positive = maker adverse-selected. We only need the pooled total
    and the day count to expose the per-day divisor; this is a few vector ops,
    not the full avoidable-decomposition pass.
    """
    z = np.load(_resolve(data_root, PRINT_NPZ), allow_pickle=True)
    try:
        mo_score = np.asarray(z[H.headline_print_col()]).astype(np.float64)
        notional = np.asarray(z["notional"]).astype(np.float64)
        day = np.asarray(z["day"]).astype(np.int64)
        finite = np.isfinite(mo_score) & np.isfinite(notional)
        total_cost = float(np.sum((mo_score[finite] / 1e4) * notional[finite]))
        n_days = int(np.unique(day).size)
        return total_cost, n_days
    finally:
        z.close()


def check_t3_divisor(data_root, disc):
    """Check 3: recompute $/day with divisor = len(unique(day))."""
    if not os.path.exists(_resolve(data_root, PRINT_NPZ)):
        return {"checked": False, "reason": "print npz absent"}

    total_cost, n_days = _signed_total_cost_usd(data_root)
    per_day_corrected = total_cost / n_days if n_days else float("nan")
    per_day_div10 = total_cost / 10.0

    out = {
        "checked": True,
        "metric": (f"pooled signed {H.HEADLINE_HORIZON_S}s adverse-selection "
                   f"cost (USD), column {H.headline_print_col()}"),
        "pooled_total_cost_usd_recomputed": round(total_cost, 2),
        "n_days_from_npz": n_days,
        "per_day_corrected_usd": round(per_day_corrected, 2),
        "per_day_if_divided_by_10_usd": round(per_day_div10, 2),
    }

    # cross-check against what t3_results.json actually recorded
    t3_path = _resolve(data_root, T3_RESULTS_JSON)
    if os.path.exists(t3_path):
        try:
            t3 = json.load(open(t3_path))
            rec_window = t3.get("_meta", {}).get("window_days")
            pooled = t3.get("pooled", {})
            out["t3_recorded_window_days"] = rec_window
            # t3 suffixes its HEADLINE keys with the horizon and leaves the 60 s
            # companion unsuffixed for backward compatibility, so the bare name
            # is the wrong one to read at any horizon but 60.
            _sfx = f"_{H.HEADLINE_HORIZON_S}s"
            _tk = ("total_cost_usd" + _sfx if "total_cost_usd" + _sfx in pooled
                   else "total_cost_usd")
            _dk = ("cost_per_day_usd" + _sfx if "cost_per_day_usd" + _sfx in pooled
                   else "cost_per_day_usd")
            out["t3_recorded_key"] = _tk
            out["t3_recorded_total_cost_usd"] = pooled.get(_tk)
            out["t3_recorded_cost_per_day_usd"] = pooled.get(_dk)
            _rec = pooled.get(_tk)
            if _rec is not None:
                _gap = abs(_rec - total_cost)
                out["recomputed_vs_t3_abs_usd"] = round(_gap, 2)
                out["recomputed_matches_t3"] = bool(
                    _gap <= max(1.0, 0.001 * abs(_rec)))
                if not out["recomputed_matches_t3"]:
                    disc.append(
                        "recomputed %s cost %.2f but t3 %s records %.2f"
                        % (H.headline_print_col(), total_cost, _tk, _rec))
            # Is the recorded divisor the real day count, or a stale 7/10?
            if rec_window is not None and rec_window != n_days:
                disc.append(
                    "t3_results window_days=%s but npz has %d distinct days -> "
                    "recorded $/day uses the wrong divisor" % (rec_window, n_days)
                )
                out["divisor_matches_npz"] = False
            else:
                out["divisor_matches_npz"] = True
            # sanity: does the recorded per-day equal recorded_total / recorded_window?
            rt = pooled.get("total_cost_usd")
            cpd = pooled.get("cost_per_day_usd")
            if rt is not None and cpd is not None and rec_window:
                implied = rt / rec_window
                if abs(implied - cpd) > max(1.0, 0.001 * abs(cpd)):
                    disc.append(
                        "t3_results internal $/day inconsistency: %.2f vs total/window %.2f"
                        % (cpd, implied)
                    )
        except (ValueError, KeyError) as exc:
            disc.append("could not parse t3_results.json: %s" % exc)
            out["t3_parse_error"] = str(exc)
    else:
        out["t3_results_present"] = False
    return out


# --- text / log consistency (Check 4) -------------------------------------
# Matchers tuned to the actual prose. We look for evidence of (a) an l2Book /
# Level-2 book pull and (b) a completed book-mid markout execution in the LOG.
_L2_PULL_RE = re.compile(
    r"l2[_\s-]?book|level[\s-]?2 (?:order[\s-]?book|book)|l2_cache|book[\s-]?diff (?:pull|download)",
    re.IGNORECASE,
)
_BOOK_MID_RAN_RE = re.compile(
    r"book[\s-]?mid (?:check|markout|join|execution)[^.\n]*"
    r"(?:has (?:since )?run|= ?ran|ran|completed|executed)"
    r"|(?:ran|built\+?ran|executed|completed).{0,40}book[\s-]?mid",
    re.IGNORECASE,
)
# the log's stale framing: book-mid still described as a FUTURE/next experiment
_BOOK_MID_FUTURE_RE = re.compile(
    r"book[\s-]?mid[^.\n]*(?:next experiment|decisive next|pending|if .*needed|to be run|future work)"
    r"|(?:next experiment|decisive next|pending)[^.\n]*book[\s-]?mid",
    re.IGNORECASE,
)


def _read_text(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return None


def check_text_consistency(repo_root, data_root, disc):
    """Check 4: log records vs execution artifacts."""
    # The volume-weighted book-mid markout key i4_midmarkout.py writes, built from
    # settings.py rather than typed, so this lookup cannot drift from the producer.
    _I4_MID_VW_KEY = f"vw_mean_{H.headline_mid_col()}_bps"
    log_path = os.path.join(repo_root, LOG_REL)
    log_txt = _read_text(log_path)

    out = {
        "log_file": os.path.basename(LOG_REL),
    }

    # log evidence
    log_l2_pull = bool(log_txt and _L2_PULL_RE.search(log_txt))
    log_bookmid_ran = bool(log_txt and _BOOK_MID_RAN_RE.search(log_txt))
    log_bookmid_future = bool(log_txt and _BOOK_MID_FUTURE_RE.search(log_txt))
    out["log_records_l2book_pull"] = log_l2_pull
    out["log_records_bookmid_execution"] = log_bookmid_ran
    out["log_still_frames_bookmid_as_future"] = log_bookmid_future

    # execution artifact: i4 book-mid results that confirm the run
    i4_path = _resolve(data_root, I4_MID_RESULTS_JSON)
    i4_ran = False
    i4_detail = {}
    if os.path.exists(i4_path):
        try:
            i4 = json.load(open(i4_path))
            days_resolved = i4.get("config", {}).get("days_resolved", [])
            # row_aligned_to_print_npz is THREE-VALUED in the producer: true or false
            # where the shipped trade-print artifact was compared, null where it was
            # absent and no comparison was made. Only true counts as evidence that the
            # book-mid pass ran against the artifact; null is carried through to the
            # detail block untouched, beside the arm that produced it, so a reader sees
            # "not compared" rather than a bare false.
            i4_detail = {
                "file": os.path.basename(I4_MID_RESULTS_JSON),
                "total_rows": i4.get("total_rows"),
                "row_aligned_to_print_npz": i4.get("row_aligned_to_print_npz"),
                "print_twin_arm": i4.get("print_twin_source", {}).get("arm"),
                "n_days_resolved": len(days_resolved),
                # The key is BUILT from settings, never typed: a typed mo10_mid here
                # and a settings-built mo10_mid in the producer are two homes for one
                # name, and the day they disagree this lookup returns None in silence.
                # The string is the same one the producer writes, so no key moves.
                _I4_MID_VW_KEY: i4.get(_I4_MID_VW_KEY),
            }
            i4_ran = (
                i4.get("row_aligned_to_print_npz") is True
                and int(i4.get("total_rows", 0)) > 0
                and len(days_resolved) > 0
            )
        except (ValueError, KeyError) as exc:
            disc.append("could not parse %s: %s" % (I4_MID_RESULTS_JSON, exc))
    out["bookmid_execution_artifact_present"] = i4_ran
    out["bookmid_execution_artifact_detail"] = i4_detail

    # ---- consistency verdicts ----
    if log_txt is None:
        disc.append(UNASKABLE + "data_acquisition_log.md not readable for the "
                    "l2Book / book-mid check")

    # A FILE THAT COULD NOT BE READ IS NOT A FILE THAT LACKS SOMETHING, and the three
    # verdicts below say what the log DOES NOT record. Each flag under them defaults to
    # False, so on a machine where the log is absent every one of them fired, and this
    # gate reported in the same breath that the log was unreadable and that the log
    # omits three things. Measured in a clean clone: two such lines, both stated as
    # findings, both about a document the run never opened.
    #
    # The absence is already reported above, once, in its own words. Below runs only
    # where there is a document to be right or wrong about.
    log_read = log_txt is not None

    # The acquisition log under-records the i4 work.
    if log_read and i4_ran and not log_l2_pull:
        disc.append(
            "data_acquisition_log.md does NOT record an l2Book / Level-2 book pull, "
            "yet the book-mid execution artifact (%s) shows it ran on %d days -> "
            "log is stale / under-records the i4 acquisition"
            % (os.path.basename(I4_MID_RESULTS_JSON), i4_detail.get("n_days_resolved", 0))
        )
    if log_read and i4_ran and not log_bookmid_ran:
        disc.append(
            "data_acquisition_log.md does NOT record a completed book-mid execution, "
            "yet the artifact confirms it ran -> log under-records the book-mid run"
        )
    if log_read and i4_ran and log_bookmid_future:
        disc.append(
            "data_acquisition_log.md still frames the book-mid check as a FUTURE / "
            "decisive-next experiment, but it has already run (artifact present) -> "
            "stale log framing"
        )
    return out


def main():
    t0 = artifact.start_clock()
    ap = argparse.ArgumentParser(description="read-only repro/integrity gate")
    # RESOLVED by panel_io rather than by reading the environment here, so the rule for
    # turning a flag, a variable and a fallback into one directory is written once for
    # the tree. env_names is narrowed to the single name this gate speaks TODAY: panel_io
    # honours five, and widening this gate to all five would change which directory it
    # reads whenever one of the other four is set, which is a behaviour change and not a
    # move of code. The name and the fallback are therefore exactly what stood here.
    ap.add_argument(
        "--data-root",
        default=P.data_root(env_names=("CAP_CHECK_ROOT",)),
        help="dir holding the .npz + result JSON inputs (default: this script's dir)",
    )
    ap.add_argument(
        "--repo-root",
        # Two levels up, not one: this script sits in a group directory inside the
        # repository, so the workspace root is the parent of the REPOSITORY. One level
        # would name the repository itself, which does not hold 02_data,
        # and the check would report it missing instead of reading it.
        default=os.environ.get("CAP_REPO_ROOT",
                               os.path.abspath(os.path.join(_CODE_DIR, ".."))),
        help="workspace root holding 02_data/ (default: the directory "
             "holding this repository)",
    )
    args = ap.parse_args()
    data_root = os.path.abspath(args.data_root)
    repo_root = os.path.abspath(args.repo_root)

    discrepancies = []
    result = {}

    result["check1_schema_and_days"] = check_schema_and_days(data_root, discrepancies)
    result["check2_row_alignment"] = check_row_alignment(data_root, discrepancies)
    result["check3_t3_divisor"] = check_t3_divisor(data_root, discrepancies)
    result["check4_text_consistency"] = check_text_consistency(
        repo_root, data_root, discrepancies
    )

    # gate verdict: ok iff no discrepancies AND the hard alignment check passed.
    align = result["check2_row_alignment"]
    align_ok = align.get("passed", False) if align.get("checked") else False
    result["ok"] = bool(len(discrepancies) == 0 and align_ok)
    result["discrepancies"] = discrepancies

    # The same list, split by whether the gate could ask. `ok` above keeps its old
    # meaning -- everything asked and everything agreed -- because other readers use
    # it; these two are what the exit code is taken from.
    unaskable = [d for d in discrepancies if d.startswith(UNASKABLE)]
    found = [d for d in discrepancies if not d.startswith(UNASKABLE)]
    result["unaskable"] = unaskable
    result["discrepancies_found"] = found
    result["verdict"] = ("FAIL" if (found or (align.get("checked") and not align_ok))
                         else "UNCERTAIN" if unaskable else "PASS")

    # The scope is READ OFF what check 1 actually found, never assumed. A gate that ran
    # with one intermediate missing covered a different population from one that ran
    # with both, and this project has already published a verdict stamped ALL_PASS that
    # had been computed over a single hour. Both cases are stated here in words.
    pr = result["check1_schema_and_days"].get("print", {})
    md = result["check1_schema_and_days"].get("mid", {})
    if pr.get("present") and md.get("present"):
        population = (f"{pr['rows']:,} rows of {PRINT_NPZ} against {md['rows']:,} rows "
                      f"of {MID_NPZ}, compared element-wise on "
                      f"{len(INT_KEYS) + len(FLOAT_KEYS)} stable key columns")
    else:
        present = [name for name, blk in (("print", pr), ("mid", md))
                   if blk.get("present")]
        population = ("no row comparison: present intermediates are "
                      + (", ".join(present) if present else "none"))
    day_dates = pr.get("day_dates") or md.get("day_dates") or []
    window = (f"{len(day_dates)} distinct days read from the persisted day column: "
              f"{day_dates[0]}..{day_dates[-1]}" if day_dates
              else "no day column read: neither intermediate was present")

    artifact.write(
        OUT_JSON, result,
        script=__file__,
        # Everything this gate opened. The acquisition log lives beside the repository
        # rather than inside it, so it is handed over as a resolved path; only the
        # basename is ever recorded.
        inputs=[_resolve(data_root, PRINT_NPZ), _resolve(data_root, MID_NPZ),
                _resolve(data_root, T3_RESULTS_JSON),
                _resolve(data_root, I4_MID_RESULTS_JSON),
                os.path.join(repo_root, LOG_REL)],
        scope={
            "population": population,
            "window": window,
            # Stated as not applicable rather than filled in from the coin map: this
            # gate reads the schema, the day column and the cost columns, and never
            # splits any check by coin, so a coin list here would describe the input
            # file instead of the checks.
            "coins": ("n/a: every check is over the whole file; nothing here is cut "
                      "by coin"),
        },
        settings={
            "h": H.HEADLINE_HORIZON_S, "lens": "print",
            "master_seed": SEED,
            "n_perm": None,
            "n_boot": None,
            "rank_floor_fills": None,
            "override_reasons": {
                "lens": (f"check 3 recomputes the pooled adverse-selection cost on the "
                         f"trade-print column {H.headline_print_col()}; the book-mid "
                         f"intermediate is opened for its schema and its row keys "
                         f"only, never for a markout value"),
                "master_seed": ("bound from settings.MASTER_SEED and unchanged; no "
                                "generator is drawn in this file at all"),
                "n_perm": "no permutation test and no bootstrap run in this gate",
                "n_boot": "see n_perm",
                "rank_floor_fills": ("no wallet floor applies: every check is over all "
                                     "rows, and no per-wallet population is gated"),
            },
        },
        extra_meta={
            "object": "read-only repro/integrity gate for the markout intermediates",
            "data_root": os.path.basename(data_root.rstrip(os.sep)) or data_root,
            # Relative to the repository, so the record names "..", the directory a
            # clone sits in, and never the name that directory has on one machine.
            "repo_root": os.path.relpath(repo_root, _CODE_DIR),
            "note": "light gate; no heavy compute, no raw-archive access",
        },
        started=t0,
        # The same rule as the other gates, in the same words: a run that reached no
        # verdict leaves the record of a run that did. PASS and FAIL are both verdicts.
        answered=(result["verdict"] != "UNCERTAIN"))
    # NOT "wrote": artifact.write declines to write when this run reached no verdict,
    # and it says so on its own line. One sentence claiming a write that did not happen
    # is the same defect as an exit code claiming a pass that did not happen, only
    # smaller, and this file is not the place to say it twice or to say it wrong.
    print("[check_first] %s | ok=%s | %d discrepancies"
          % (OUT_JSON, result["ok"], len(discrepancies)))
    for line in found:
        print("  FOUND    : %s" % line)
    for line in unaskable:
        print("  NOT ASKED: %s" % line[len(UNASKABLE):])
    print("  VERDICT: %s" % result["verdict"])

    # THE EXIT CODE AND THE PRINTED WORD ARE NOW THE SAME EVENT. This gate had no
    # sys.exit at all: it printed ok=False and handed back a zero, so a reviewer
    # following the README, which names this gate as the first thing to run, was told
    # by the shell that everything held. An error that points at success is the one
    # that travels; an error that points at alarm stops the work and costs nothing.
    #
    # UNCERTAIN keeps a zero on purpose, and that is not the same leniency. It says the
    # gate was handed a machine without the files, which is a fact about the machine,
    # and the word on the screen carries it. FAIL means a question was asked and the
    # answer disagreed, and that is the only state the shell needs to shout about.
    return 0 if result["verdict"] in ("PASS", "UNCERTAIN") else 1


if __name__ == "__main__":
    # main() returns the code; raising it here is what makes the shell see it. The
    # bare call above threw the return value away, which is how a gate that printed
    # ok=False still told every caller it was fine.
    sys.exit(main())
