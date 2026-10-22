#!/usr/bin/env python3
"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-08-14
References: none (repository infrastructure gate; it runs the build's own self-test and
reads what that run printed).

THE BUILD'S SELF-DIAGNOSIS IS A CHECK LIKE ANY OTHER, AND UNTIL TODAY NOTHING RAN IT.

Why this gate exists, and it was measured rather than argued. `build.py` invoked with no
arguments runs its own self-test: 77 assertions about the graph it derives from the
syntax tree of every script in this repository -- one producer per artifact, no cycles,
every file operation accounted for, the skip rule skipping and the run rule running. On
2026-08-14 that self-test returned exit 1, and it had been returning it for days. The
battery beside it printed 17 of 17 and exit zero.

Both statements were true and together they were misleading, which is the defect this
gate closes. The self-test belonged to no group of `run_all_checks.py`, so nothing ran
it; and while a program that exits non-zero sits outside the run that reports the health
of the tree, "no failures" means "none among the ones we look at" and reads as "none at
all". The direction of that error is the dangerous one: it points at success.

WHAT THIS GATE ASKS. Three questions, and the first two are about the instrument rather
than about the tree, because a reading nobody can trust is worse than no reading.

    the self-test finished, and printed the shape this gate reads;
    three readings of one quantity agree -- the assertion lines, the VERDICT line that
        names the failures by their own labels, and the process exit code;
    the number of failing assertions is at or under the ceiling declared below.

WHY THE FAILURES ARE COUNTED RATHER THAN NAMED. The ceiling is the gate. A gate that
also demanded each failure be one of the named ones would go red the day the build's
repair leaves a different three, which is a verdict about this file rather than about the
tree. So the count decides the exit code, and the names are printed beside it: every
failure is reported as declared or as not declared, and a failure nobody has declared is
named on the screen even while it sits under the ceiling. That is what a reader needs in
order to lower the ceiling, which is the only direction it moves.

WHAT THE CEILING COVERS TODAY is written out at DECLARED_DEBT below, one line each.

HOW THE READING IS CALIBRATED, and the fixtures are the run's own bytes. The predicate
here is a parser of the self-test's output, and a parser that reports nothing is
indistinguishable from a tree with nothing wrong. So three cases are put through it on
every invocation, all three built from the text the run just printed rather than invented:

    a line the run itself marked PASS               -- must be read as no failure;
    that same sentence with its one marker changed  -- must be read as exactly that
                                                       failure, by its own label;
    a line of the run's output that is not an assertion at all -- must not be counted.

The pair differs along one axis, the marker word, and neither case can go vacuous the day
the tree is repaired: a self-test that passes still prints passing lines, and this gate
says so rather than falling silent if it ever prints none.

Reading the result. PASS means the self-test failed nothing. PASS_AT_BASELINE means it
failed at or under the ceiling, and the failures are printed with their addresses in
build.py. FAIL means a regression over the ceiling, or an instrument this gate could not
trust.

    uv run --no-project --with-requirements requirements.txt python3 \
        checks/chk_build_selftest.py
"""
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
import artifact                                                          # noqa: E402
from evidence import report_gate                                         # noqa: E402
# CALLED, not copied. The rule about home paths in a published artifact has one home, and
# this gate copies text out of another program's output into a tracked .json, which is
# exactly the route by which such a path would arrive.
from chk_no_abs_paths import redact                                      # noqa: E402

OUT_JSON = os.path.join(HERE, "chk_build_selftest_results.json")

# The self-test is what `build.py` runs when it is given nothing to do, which is its own
# decision and is stated in its closing lines. Named here as a repository-relative path
# and joined at run time, so nothing about this machine reaches the artifact.
BUILD_SCRIPT = "build.py"

# Measured at 7.1 seconds on 2026-08-14 over 77 assertions, twice, on a copy of the live
# tree and on a clean clone. The timeout is two orders above that: this gate exists to
# report what the self-test says, and a limit tight enough to trip on a slow machine
# would report the machine instead.
TIMEOUT_S = 900

# HOW THE SELF-TEST SPEAKS. Both patterns are written against `build.py`'s own printing:
# `check()` prints two spaces, the marker, two spaces, the label, and " -- " with a
# detail when it has one; the closing line prints the word and, when something failed,
# the labels of the failures joined with ", ".
ASSERTION_RE = re.compile(r"^  (PASS|FAIL)  (\S.*)$")
VERDICT_RE = re.compile(r"^  VERDICT: (PASS|FAIL)(?: (.*))?$")

# THE CEILING, AND IT MOVES ONE WAY ONLY. One is a declared debt, not a preference, and
# it is the third number to stand here in one day. The history is short and worth keeping,
# because each step down was a repair rather than a re-reading:
#
#   9  the committed tree on 2026-08-14, measured in a clean clone;
#   3  after TAPE_PARSERS was taught to resolve a basename through the tree's own script
#      index -- SIX of the nine, not the seven this comment first claimed. Six was
#      measured twice and the two agreed: by substituting paths for bare names in the
#      committed tree, and by walking the history, where the commit that moved the files
#      into data/ and persistence/ took the count from 1 to 7;
#   2  after the notebook pointer gate stopped naming its blind-case fixture the same
#      thing the notebook expectations gate names its own;
#   1  after the tape-loader assertion stopped demanding a live counter-example the tree
#      no longer holds and was given a written-in pair instead.
#
# RAISING THIS NUMBER IS FORBIDDEN. A ceiling that rises to meet the tree measures
# nothing: it turns every regression into a one-line edit here and the gate stops being a
# gate. Lowering it is the ordinary act, and this gate prints the lower number it would
# accept at the end of every run that comes in under the ceiling.
BASELINE_FAILING_ASSERTIONS = 1

# WHAT THE CEILING IS ALLOWED TO COVER, one line each, so a reader of a PASS_AT_BASELINE
# run knows WHAT is standing and not only how much. The first element is a fragment of
# the assertion's own label, matched as a substring; None marks a slot that is declared
# and not yet claimed by a particular assertion.
DECLARED_DEBT = (
    ("every I/O call is accounted for",
     "8 file operations fold to no constant, against build.py's own "
     "UNRESOLVED_IO_CEILING of 0. All eight are the same shape -- an open() whose path is "
     "a parameter of a general-purpose reader, so the folder has no constant to fold and "
     "none of the eight names an artifact. Two repairs are open and both are edits in "
     "build.py and build_declarations.py rather than here: teach the folder to bind the "
     "argument at the call site, or write the eight down with a reason each. Raising "
     "UNRESOLVED_IO_CEILING is not one of them",
     "2026-08-14"),
)


def build_path():
    """The self-test's own file, built from this module's location at run time."""
    return os.path.join(ROOT, BUILD_SCRIPT)


def run_selftest():
    """Run the build's self-test and return what it printed, its code and its cost.

    The exit code is taken from the completed process on the same statement that
    launched it, with no pipe between: a code read from anywhere else is a code about
    something else, and this project has already had one wrapper record exit 0 over
    seven failed runs.

    Standard error is captured rather than silenced. A self-test that dies on an
    exception says so there and nowhere else, and a gate that discards it would report
    the same "nothing found" for a crash as for a clean tree.

    The interpreter is this one, `sys.executable`, so the self-test runs under the
    environment the battery already resolved. Its path is never recorded: it names a
    directory on this machine.
    """
    started = time.time()
    if not os.path.isfile(build_path()):
        return {"ran": False, "why": "the script is not in this tree at all",
                "code": None, "text": "", "seconds": 0.0}
    try:
        proc = subprocess.run([sys.executable, BUILD_SCRIPT],
                              cwd=ROOT, capture_output=True, text=True,
                              timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired as exc:
        return {"ran": False,
                "why": f"it did not finish inside {TIMEOUT_S}s",
                "code": None, "text": str(exc)[:2000],
                "seconds": time.time() - started}
    return {"ran": True, "why": "", "code": proc.returncode,
            "text": (proc.stdout or "") + (proc.stderr or ""),
            "seconds": time.time() - started}


def read_assertions(text):
    """Every assertion the self-test printed, as {marker, label, detail}.

    The label is what `check()` was given as its name, which is also what the closing
    VERDICT line repeats for each failure. Keeping them apart from the detail is what
    lets the two readings below be compared as sets rather than as strings.
    """
    rows = []
    for line in text.split("\n"):
        m = ASSERTION_RE.match(line)
        if not m:
            continue
        marker, rest = m.group(1), m.group(2)
        label, _, detail = rest.partition(" -- ")
        rows.append({"marker": marker, "label": label.strip(),
                     "detail": detail.strip()})
    return rows


def read_verdict(text):
    """The closing line as (word, the failures it names), or (None, None).

    This is the SECOND reading of the same quantity, and it exists because a count taken
    by one predicate says nothing until a second, independent one agrees with it. The
    self-test builds this line by joining the labels of everything that failed, so the
    comparison below is an exact reconstruction and not a resemblance.
    """
    for line in text.split("\n"):
        m = VERDICT_RE.match(line)
        if m:
            return m.group(1), (m.group(2) or "").strip()
    return None, None


def locate(label, source_lines):
    """Where in build.py the assertion with this label is written, as a line number.

    Found by content rather than by an index kept here: the labels are written in the
    source as adjacent string literals, so the opening words of one sit verbatim on the
    same physical line as the call that makes the assertion. The longest prefix that
    matches wins, and a label that matches nothing returns 0 rather than a guess.

    THE CALL IS LOOKED FOR BEFORE THE WORDS, and that was learned on the first run of
    this gate rather than designed: "every artifact has exactly one producer" is both an
    assertion and a heading the build prints when it reports the graph, and the words
    alone sent the reader to the heading, 540 lines above the assertion. A prefix that
    stands right after `check("` cannot be a heading.
    """
    words = label.split()
    for opener in ('check("', ""):
        for n in range(len(words), 2, -1):
            needle = opener + " ".join(words[:n])
            for i, line in enumerate(source_lines, start=1):
                if needle in line:
                    return i
    return 0


def last_words(text):
    """The last line of the output carrying anything to read, for a failed run.

    A run that died leaves its reason in the last line that says something, and the
    literal last line is usually a rule of dashes. Quoting the dashes is quoting
    nothing, which is the shape of evidence without the evidence.
    """
    for line in reversed(text.strip().split("\n")):
        if any(ch.isalnum() for ch in line):
            return redact(line.strip())[:200]
    return ""


def declared_for(label):
    """The declared-debt entry covering this label, or None."""
    for fragment, why, since in DECLARED_DEBT:
        if fragment and fragment in label:
            return {"fragment": fragment, "why": why, "declared": since}
    return None


def _leading_count(text):
    """The first whole number in a sentence, or None when it carries none.

    Both halves of the comparison below are prose written for a reader -- the assertion
    prints "N unresolved against a ceiling of 0" and the debt entry opens "N file
    operations fold to no constant" -- and the first number in each is the magnitude
    each is talking about. A sentence with no number at all yields None and is skipped
    rather than read as a zero, because a debt whose size nobody wrote down is not a
    debt of size nothing.
    """
    found = re.search(r"\d+", text or "")
    return int(found.group()) if found else None


def debt_grew(findings):
    """Declared debts whose MAGNITUDE is larger today than the entry admits.

    THE COUNT OF FAILING ASSERTIONS DOES NOT SEE A DEBT GETTING WORSE, AND THAT BLIND
    SPOT COST A WHOLE DAY. One assertion here fails, and the ceiling holds the number of
    failing assertions at one, so a repair elsewhere in the tree that took the residue
    inside that single assertion from 8 unaccounted file operations to 14 changed
    nothing this gate reports: same assertion, still failing, count still one, verdict
    still PASS_AT_BASELINE. The sentence naming the debt is typed by hand and dated, so
    it went on saying 8 while the tree said 14, and the reader who trusted the battery
    read the wrong number all day.

    A ceiling is a promise that a debt may only be lowered. That promise is about the
    SIZE of the debt and not only about how many lines report it, so the size is what is
    held here. Growth is a finding with the same standing as an undeclared failure; the
    repair is to shrink the debt back, and rewriting the number upward is not one of the
    ways to satisfy this.
    """
    grew = []
    for finding in findings:
        covered = finding.get("declared")
        if not covered:
            continue
        admitted = _leading_count(covered.get("why"))
        # `source`, never `detail`: detail is the assertion's LABEL and carries no
        # number at all, while source is the evidence the assertion printed beside it --
        # "8 unresolved against a ceiling of 0". Written first against detail, this
        # comparison read None on every run and could not have fired once, which is a
        # gate that reports nothing and looks exactly like a gate finding nothing.
        today = _leading_count(finding.get("source") or finding.get("detail"))
        if admitted is not None and today is not None and today > admitted:
            grew.append({"fragment": covered["fragment"], "admitted": admitted,
                         "today": today, "declared": covered["declared"]})
    return grew


def calibrate(text):
    """Three cases through the reader, all of them the run's own bytes.

    ONE REFERENCE POINT CANNOT CALIBRATE A READER: it cannot tell one that is too wide
    from one that is too narrow, and both failures here look identical from the outside --
    a gate reporting nothing. So the pair is a real sentence the run marked PASS and the
    same sentence with its marker changed to FAIL, which differ along exactly one axis.
    The third case is a line of the same output that is not an assertion at all, and it
    is the case a pattern drawn too wide would fail.

    Nothing is invented. A fixture written to the shape a format is supposed to have
    certifies the shape and not the format, and this repository has already paid for that
    once. Every case here is a line this run printed, which also means the calibration
    cannot go stale against a change to the way the self-test prints.
    """
    lines = [ln for ln in text.split("\n") if ASSERTION_RE.match(ln)]
    passing = [ln for ln in lines if ASSERTION_RE.match(ln).group(1) == "PASS"]
    other = [ln for ln in text.split("\n")
             if ln.strip() and not ASSERTION_RE.match(ln) and not VERDICT_RE.match(ln)]
    if not passing or not other:
        # Stated rather than skipped. A calibration that quietly finds no material is
        # the silence it exists to prevent, one level up.
        return [("the cases could not be built",
                 "must never happen: the self-test printed "
                 f"{len(passing)} passing assertion(s) and {len(other)} other line(s), "
                 "so the pair below has no live sentence to be built from",
                 "", "", False)]

    silent_case = passing[0]
    firing_case = "  FAIL" + silent_case[len("  PASS"):]
    label = ASSERTION_RE.match(silent_case).group(2).partition(" -- ")[0].strip()
    quiet = [r["label"] for r in read_assertions(silent_case) if r["marker"] == "FAIL"]
    loud = [r["label"] for r in read_assertions(firing_case) if r["marker"] == "FAIL"]
    noise = read_assertions("\n".join(other))
    return [
        ("the marker is read, not the sentence",
         "must stay silent: a line this run itself marked PASS",
         quiet, [], quiet == []),
        ("the marker is read, not the sentence",
         "must fire: that same sentence with its one marker changed to FAIL",
         loud, [label], loud == [label]),
        ("only an assertion is counted",
         f"must stay silent: the {len(other)} lines of this run that are not "
         "assertions, banners and progress among them",
         len(noise), 0, len(noise) == 0),
    ]


def main():
    started = artifact.start_clock()
    run = run_selftest()
    rows = read_assertions(run["text"])
    word, named = read_verdict(run["text"])
    failing = [r for r in rows if r["marker"] == "FAIL"]
    labels = [r["label"] for r in failing]

    try:
        with open(build_path(), encoding="utf-8", errors="replace") as fh:
            source_lines = fh.read().split("\n")
    except OSError:
        source_lines = []

    findings = []
    for row in failing:
        covered = declared_for(row["label"])
        findings.append({
            "file": BUILD_SCRIPT,
            "line": locate(row["label"], source_lines),
            "rule": "SELFTEST-ASSERTION-FAILED",
            "detail": row["label"],
            "source": redact(row["detail"])[:200],
            "declared": covered,
        })
    undeclared = [f for f in findings if not f["declared"]]

    # THE INSTRUMENT, ASKED BEFORE THE TREE. Each entry below is a way for the count
    # above to be wrong rather than for the tree to be broken, and they are separated
    # because the two send a reader to different places.
    unreadable, disagreements = [], []
    if not run["ran"]:
        unreadable.append({
            "file": BUILD_SCRIPT, "line": 0, "rule": "SELFTEST-DID-NOT-RUN",
            "detail": f"SELFTEST-DID-NOT-RUN: the self-test did not finish: "
                      f"{run['why']}",
            "source": last_words(run["text"])})
    elif not rows:
        unreadable.append({
            "file": BUILD_SCRIPT, "line": 0, "rule": "SELFTEST-PRINTED-NOTHING-READABLE",
            "detail": f"SELFTEST-PRINTED-NOTHING-READABLE: the run exited "
                      f"{run['code']} and printed no line this gate can read as an "
                      f"assertion, so its verdict is unknown rather than clean",
            "source": last_words(run["text"])})
    elif word is None:
        unreadable.append({
            "file": BUILD_SCRIPT, "line": 0, "rule": "SELFTEST-DID-NOT-CLOSE",
            "detail": f"SELFTEST-DID-NOT-CLOSE: {len(rows)} assertions were printed and "
                      f"no closing VERDICT line followed them, so the run stopped "
                      f"part-way and the count below is of a partial run",
            "source": last_words(run["text"])})
    else:
        # Three readings of one quantity, compared. The exit code is a fact of the
        # process, the VERDICT line is the self-test's own summary, and the assertion
        # lines are what this gate counted; two of them agreeing while the third does
        # not is a broken instrument, whichever two they are.
        rebuilt = ", ".join(labels)
        if word == "FAIL" and rebuilt != named:
            disagreements.append({
                "file": BUILD_SCRIPT, "line": 0, "rule": "TWO-READINGS-DISAGREE",
                "detail": "TWO-READINGS-DISAGREE: the labels this gate read as failing "
                          "do not rebuild the closing line the self-test wrote for "
                          "itself",
                "source": f"read {rebuilt[:80]!r}; the run wrote {named[:80]!r}"})
        if word == "PASS" and labels:
            disagreements.append({
                "file": BUILD_SCRIPT, "line": 0, "rule": "TWO-READINGS-DISAGREE",
                "detail": f"TWO-READINGS-DISAGREE: {len(labels)} assertion(s) printed "
                          f"FAIL and the closing line says PASS",
                "source": "; ".join(labels)[:200]})
        if (run["code"] == 0) != (not labels):
            disagreements.append({
                "file": BUILD_SCRIPT, "line": 0, "rule": "EXIT-CODE-DISAGREES",
                "detail": f"EXIT-CODE-DISAGREES: the process exited {run['code']} and "
                          f"{len(labels)} assertion(s) were read as failing; the "
                          f"self-test returns 1 when and only when something failed",
                "source": f"exit {run['code']}, failures {len(labels)}"})

    cal = calibrate(run["text"]) if run["ran"] else []

    # TWO OPPOSITE CASES FOR THE DEBT-SIZE RULE, BUILT OUT OF THIS RUN'S OWN FINDINGS so
    # that they cannot go stale the way a made-up example would. The first written form
    # of this rule read the wrong field and answered None on every run: it could not
    # have fired once, and a rule that cannot fire is indistinguishable on the screen
    # from a rule that found nothing. So the firing case is required to fire.
    if findings:
        _real = findings[0]
        _bigger = dict(_real, source="999999 " + str(_real.get("source") or ""))
        cal = list(cal) + [
            ("debt size, unchanged", "a debt reported at the size its entry admits is "
             "not a finding", len(debt_grew([_real])), 0, len(debt_grew([_real])) == 0),
            ("debt size, grown", "the same finding with its residue multiplied is "
             "reported", len(debt_grew([_bigger])), 1, len(debt_grew([_bigger])) == 1),
        ]
    cal_failed = [c for c in cal if not c[4]]

    over = len(failing) > BASELINE_FAILING_ASSERTIONS
    grew = debt_grew(findings)
    broken = bool(unreadable or disagreements or cal_failed or not cal)
    # A debt that got bigger fails the gate exactly as an extra failing assertion does.
    # The two are the same promise read on two different axes -- how many lines report
    # the debt, and how large the debt is -- and holding only the first is what let a
    # residue go from 8 to 14 under an unchanged verdict.
    verdict = ("FAIL" if over or grew or broken
               else ("PASS" if not failing else "PASS_AT_BASELINE"))

    print("=" * 76)
    print("  THE BUILD'S SELF-TEST, RUN AS A GATE")
    print("=" * 76)
    print(f"  ran                : {BUILD_SCRIPT} with no arguments, "
          f"{run['seconds']:.1f}s, exit {run['code']}")
    print(f"  calibration cases  : {len(cal)}, failed {len(cal_failed)}")
    for name, what, got, want, ok in cal:
        print(f"  {'ok  ' if ok else 'FAIL'} {name}: {what}")
        if not ok:
            print(f"       expected {want!r}, got {got!r}")
    print(f"  assertions read    : {len(rows)}, of which {len(failing)} failed")
    print(f"  ceiling            : {BASELINE_FAILING_ASSERTIONS}, a declared debt that "
          f"may only be lowered")
    for f in findings:
        covered = f["declared"]
        print(f"  {'declared' if covered else 'NOT DECLARED':12} "
              f"{BUILD_SCRIPT}:{f['line']}  {f['detail'][:70]}")
        print(f"      | {f['source'][:100]}")
        if covered:
            print(f"      | allowed since {covered['declared']}: {covered['why'][:88]}")
    for g in grew:
        print(f"  DEBT GREW    {g['fragment']}: the entry declared on {g['declared']} "
              f"admits {g['admitted']}, the tree reports {g['today']}. A ceiling may "
              f"only be lowered, and that holds for the SIZE of the debt and not only "
              f"for how many assertions report it. Shrink it back; rewriting the number "
              f"upward is not one of the repairs.")
    if undeclared and not over:
        # Printed, and deliberately NOT counted against the exit code. The gate is the
        # ceiling; this is the line that tells a reader the ceiling is covering
        # something nobody has written down yet.
        print(f"  {len(undeclared)} failure(s) under the ceiling are not named in "
              f"DECLARED_DEBT. Name them there, or lower the ceiling.")
    # THE RATCHET, SAID OUT LOUD, AND ONLY WHEN THE READING CAN BE BELIEVED. A ceiling
    # that nobody is reminded to lower stops being a debt and becomes a habit. It is
    # withheld when the instrument failed, because "lower the ceiling to 0" printed
    # under a run that died is advice built on a count of nothing.
    if broken:
        print("  the ceiling is not judged on this run: the reading above could not be "
              "trusted, and a count taken from it would be a count of nothing.")
    elif not failing:
        print("  nothing failed. The ceiling above is now pure headroom and should be "
              "lowered to 0.")
    elif not over and len(failing) < BASELINE_FAILING_ASSERTIONS:
        print(f"  the debt today is {len(failing)}, under the ceiling of "
              f"{BASELINE_FAILING_ASSERTIONS}. Lower the ceiling to {len(failing)}.")
    print("-" * 76)
    print(f"  VERDICT: {verdict}")
    print(f"  results -> {os.path.basename(OUT_JSON)}")

    artifact.write(
        os.path.basename(OUT_JSON),
        {"verdict": verdict,
         "n_assertions": len(rows),
         "n_failing": len(failing),
         "baseline": BASELINE_FAILING_ASSERTIONS,
         "failing": findings,
         # The size of each declared debt as the tree reports it today, beside the size
         # the entry admits. Written down because a number nobody records cannot be
         # compared with itself next week, which is how this one drifted unseen.
         "declared_debt_sizes": [
             {"fragment": f["declared"]["fragment"],
              "admitted": _leading_count(f["declared"]["why"]),
              "today": _leading_count(f.get("source") or f.get("detail"))}
             for f in findings if f.get("declared")],
         "declared_debt_grew": grew,
         "n_undeclared_under_ceiling": len(undeclared),
         "instrument": {"exit_code": run["code"],
                        "seconds": round(run["seconds"], 1),
                        "closing_word": word,
                        "unreadable": unreadable,
                        "disagreements": disagreements},
         "calibration": [{"predicate": n, "case": w, "got": repr(g), "want": repr(x),
                          "ok": ok} for n, w, g, x, ok in cal]},
        script=__file__,
        # The self-test's own file, hashed. That is what makes this gate's record move
        # when the thing it reports on moves: the two freshness gates of this directory
        # ask whether an artifact still stands on the version of each input it recorded,
        # and this artifact is a statement about build.py on one particular day.
        inputs=[build_path()],
        scope={
            "population": f"the {len(rows)} assertions build.py's self-test printed on "
                          f"this run; it asserts about every tracked script of this "
                          f"tree through the graph it derives from their syntax",
            "window": "n/a: this gate reads a program's output, not a period of market "
                      "data",
            "coins": "n/a: this gate reads no market data",
        },
        started=started,
        extra_meta={
            "runtime_seconds_of_selftest": round(run["seconds"], 1),
            "baseline_note": (
                f"a declared debt of {BASELINE_FAILING_ASSERTIONS}, read from this "
                "gate's own constant rather than spelled again here, because a number "
                "written twice is a number that comes apart. It stood at 9 in the "
                "committed tree of 2026-08-14 and came down in three measured steps -- "
                "six to a basename constant taught to resolve through the script index, "
                "one to a fixture name shared by two notebook gates, one to an assertion "
                "that demanded a live counter-example the tree no longer holds. It may "
                "only ever be lowered; the run prints the lower number it would accept "
                "whenever the debt comes in under it"),
            "declared_debt": [{"fragment": f, "why": w, "declared": d}
                              for f, w, d in DECLARED_DEBT],
            "n_calibration_cases": len(cal),
            "n_calibration_failed": len(cal_failed),
        },
    )

    if cal_failed:
        print("  CALIBRATION FAILED: no zero in this report can be believed.")

    return report_gate(
        [{"name": "SELFTEST-ASSERTION-FAILED",
          "permitted": BASELINE_FAILING_ASSERTIONS,
          "found": len(failing),
          "assumption": ("build.py's self-test is the only instrument in this tree that "
                         "asserts about the recompute graph itself, and until "
                         "2026-08-14 it was in no group of the battery, so it exited 1 "
                         "for days beside a battery reporting 17 of 17. The ceiling is "
                         f"a declared debt of {BASELINE_FAILING_ASSERTIONS} and may "
                         "only be lowered"),
          "method": (f"{BUILD_SCRIPT} run with no arguments, its assertion lines "
                     f"counted, and the count cross-read against the closing VERDICT "
                     f"line and the process exit code"),
          "note": ("a failing assertion of the build is a statement about the graph "
                   "every recompute decision is taken from: which script produces which "
                   "artifact, what has to run, and what may be skipped"),
          "sites": findings},
         {"name": "SELFTEST-UNREADABLE",
          "permitted": 0,
          "found": len(unreadable),
          "assumption": ("the self-test finishes and prints the shape this gate reads. "
                         "A run that died and a tree with nothing wrong both produce no "
                         "findings, and only this rule tells them apart"),
          "method": "the process is required to return, to print assertion lines, and "
                    "to close with its own VERDICT line",
          "note": "nothing was measured about the tree on this run",
          "sites": unreadable},
         {"name": "READINGS-DISAGREE",
          "permitted": 0,
          "found": len(disagreements),
          "assumption": ("the three readings of one quantity agree: the assertion lines "
                         "counted here, the labels the self-test names in its own "
                         "closing line, and the exit code of the process"),
          "method": "the failing labels are joined back into the closing line the "
                    "self-test wrote, and compared to it exactly",
          "note": "the count of failures cannot be trusted, in either direction, until "
                  "the disagreement is explained",
          "sites": disagreements},
         {"name": "CALIBRATION",
          "permitted": 0,
          "found": len(cal_failed) if cal else 1,
          "assumption": ("the reader is shown to find a failure it is given and to stay "
                         "silent on a line that passed, on this run's own bytes. "
                         "Without that, a clean report is indistinguishable from a "
                         "reader that reports nothing"),
          "method": "a passing line of this run, the same sentence with its marker "
                    "changed, and a line of the same output that is not an assertion",
          "note": "no count in this report can be believed",
          "sites": [{"file": os.path.basename(__file__), "line": 0,
                     "detail": f"{name}: {what}", "source": f"want {want!r}, got {got!r}"}
                    for name, what, got, want, ok in cal if not ok]}],
        OUT_JSON,
        inputs={"self-test": f"{BUILD_SCRIPT}, {len(rows)} assertions, "
                             f"{run['seconds']:.1f}s"})


if __name__ == "__main__":
    sys.exit(main())
