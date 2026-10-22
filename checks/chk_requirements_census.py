#!/usr/bin/env python3
"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-08-30
References: none (repository infrastructure gate; it runs the requirements census and
reads what that run printed).

THE COUNTS INSIDE requirements.txt ARE DERIVED BY A PROGRAM, AND NOTHING RAN THAT
PROGRAM.

Why this gate exists, and it was measured rather than argued. requirements.txt does not
only pin versions: between two fence lines it carries a census of this repository --
how many .py files the source release ships, which of them import each pinned
distribution, how many pipeline entry points there are, what the tree takes from the
standard library. Those numbers are written by build_requirements_census.py from the
syntax tree of every shipped file, and that program run with no arguments reports what
moved and exits non-zero when the block disagrees with the tree.

On 2026-08-30 the block had fallen behind the tree in five places and was regenerated.
The five were not counting errors: re-running the census against the commit that typed
them reproduces them exactly. A hand-typed count does not go wrong, it goes stale, and
it does so without saying anything.

The defect this gate closes is one level up from that. The census program belonged to no
group of run_all_checks.py, so nothing ran it, and the block could fall behind again
while the battery beside it printed zero failures. Both statements would be true and
together misleading: while a program that exits non-zero sits outside the run that
reports the health of the tree, "no failures" means "none among the ones we look at" and
reads as "none at all". That is the direction of error that travels, and this repository
has closed exactly this hole once before, for the build's own self-test, in
chk_build_selftest.py. This file follows that one.

WHAT THIS GATE ASKS. Four questions, and the first two are about the instrument rather
than about the tree, because a reading nobody can trust is worse than no reading.

    the census finished, and printed the shape this gate reads;
    three readings of one quantity agree -- the findings this gate counted, the number
        the census names in its own opening line, and the process exit code;
    a fourth reading, taken WITHOUT the census, agrees with it: the counts are read
        straight out of the block's prose and compared against the census asked for the
        tree in JSON. This is what catches a census that prints PASS over a stale block;
    the block disagrees with the tree in nothing but its date stamp.

WHY THE DATE STAMP IS COUNTED APART, and it was measured rather than assumed. The census
renders the block with the date of the run that renders it and then compares the whole
line, so the day after a regeneration it reports one finding whose expectation and fact
differ in nothing else:

    EXPECTATION # WHICH FILES NEED WHAT, counted on 2026-08-30 by walking ... all 129
    FACT        # WHICH FILES NEED WHAT, counted on 2026-08-29 by walking ... all 129

Measured on a copy of this tree on 2026-08-30 by moving the stored date back one day and
changing nothing else: the census exits 1 and names that line. A gate that failed on it
would be reporting the calendar and not the tree, and would go red every day that nobody
regenerated a block that was already right. So a finding whose two sides are equal once
every date in them is blanked is reported as a DATE-STAMP finding, printed, and NOT
counted against the ceiling. Nothing can hide behind that: the population count sits on
the same physical line as the date, so a stale count cannot be read as a stale date, and
the classifier is calibrated on both directions below.

Arming that second rule is not this gate's decision to make. The repair lives in
build_requirements_census.py -- render the stamp outside the compared region, or compare
the line with its date blanked -- and that file has an owner. Until then the count is
reported and never fails, which is what a permitted of None means in evidence.py.

HOW THE READING IS CALIBRATED, and the fixtures are this tree rather than an invented
example. A gate that reports nothing and a tree with nothing wrong look identical from
the outside, so six cases are put through the whole instrument on every invocation. All
of them work on a copy of every shipped file of this tree, built and removed inside the
run:

    the mirror is complete       -- every shipped file reached the copy;
    the mirror reads what the tree reads -- the copy, untouched, repeats the live run
                                    exactly, or the cases under it are about some other
                                    tree;
    the copy with its block rendered from the copy's own tree -- must stay silent;
    that same freshened copy with ONE count raised by one -- must fire, and the finding
                                    must NOT be read as a date stamp;
    that same freshened copy with ONLY its date moved -- must fire, the finding MUST be
                                    read as a date stamp, and no finding of any other
                                    kind may appear;
    lines of this run's own output that are not findings -- must not be counted.

The last three differ along exactly one declared axis: the bytes of one line of the
copy's requirements.txt. THE BLOCK IS RENDERED BEFORE EITHER CASE IS BUILT, and that was
measured rather than argued: on a copy of a tree whose block had fallen behind in two
places, raising a count on a line that was already reported changed the finding and not
the number of them, so the firing case read the same count as the silent one and went red
on the very tree this gate exists to report on. A calibration case anchored on a defect
erases itself.

Nothing is written in the real requirements.txt, which is never opened for writing here,
--write is never invoked, and the copy is removed whether the run succeeds or not.

Reading the result. PASS means the block agrees with the tree. FAIL means it does not, or
that this gate could not trust its own reading. The repair for a real disagreement is one
command, and the run prints it.

    uv run --no-project --with-requirements requirements.txt python3 \
        checks/chk_requirements_census.py
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
import artifact                                                          # noqa: E402
from evidence import report_gate, shipped_tree_files                     # noqa: E402
# CALLED, not copied. The rule about home paths in a published artifact has one home, and
# this gate copies text out of another program's output into a tracked .json, which is
# exactly the route by which such a path would arrive.
from chk_no_abs_paths import redact                                      # noqa: E402
# CALLED, not copied, for the same reason the census itself gives for asking
# checks/evidence.py what the tree ships. The fence lines and the list of pinned
# distributions are the census's own constants; spelling them again here would give this
# gate a second answer that drifts from the first, and the drift would be invisible
# because both would keep answering.
from build_requirements_census import (BEGIN, END, DISTRIBUTIONS,        # noqa: E402
                                       render)

OUT_JSON = os.path.join(HERE, "chk_requirements_census_results.json")

# Named as repository-relative paths and joined at run time, so nothing about this
# machine reaches the artifact.
CENSUS_SCRIPT = "build_requirements_census.py"
REQUIREMENTS = "requirements.txt"

# Measured at 1.0 seconds on 2026-08-30 over 129 shipped .py files, on the live tree and
# on a copy of it. The limit is two orders above that: this gate exists to report what
# the census says, and a limit tight enough to trip on a slow machine would report the
# machine instead.
TIMEOUT_S = 600

# HOW THE CENSUS SPEAKS. Every pattern here is written against the census's own printing
# in its main(): one opening line, then three aligned lines per finding, then the repair
# command.
PASS_RE = re.compile(r"^PASS  requirements\.txt agrees with the tree: (\d+) shipped")
FAIL_RE = re.compile(r"^FAIL  requirements\.txt disagrees with the tree in (\d+) place")
PLACE_RE = re.compile(r"^  PLACE       (.*)$")
EXPECTATION_RE = re.compile(r"^  EXPECTATION (.*)$")
FACT_RE = re.compile(r"^  FACT        (.*)$")

# The census names a line INSIDE the derived block; a reader opens a line of a file.
BLOCK_LINE_RE = re.compile(r"\bline[s]? (\d+)")

DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")

# A whole number that is not part of a date. The lookarounds are what keep the three
# fields of 2026-08-30 out: each of them touches a hyphen on one side.
STANDALONE_INT_RE = re.compile(r"(?<![\d-])(\d+)(?![\d-])")


def root_file(name):
    """A file of the repository root, built from this module's location at run time."""
    return os.path.join(ROOT, name)


# =====================================================================
# 1. RUNNING THE CENSUS AND READING WHAT IT PRINTED
# =====================================================================

def run_census(cwd, extra=()):
    """Run the census in *cwd* and return what it printed, its code and its cost.

    The exit code is taken from the completed process on the same statement that
    launched it, with no pipe between: a code read from anywhere else is a code about
    something else, and this project has already had one wrapper record exit 0 over
    seven failed runs.

    Standard error is captured rather than silenced. The census refuses some inputs by
    raising SystemExit with a sentence -- a requirements.txt with no fence lines, or one
    that closes the block before it opens it -- and that sentence appears there and
    nowhere else. A gate that discarded it would report the same "nothing found" for a
    refusal as for a clean tree.

    The interpreter is this one, sys.executable, so the census runs under the environment
    the battery already resolved. Its path is never recorded: it names a directory on
    this machine. Neither is *cwd*, for the same reason.
    """
    started = time.time()
    script = os.path.join(cwd, CENSUS_SCRIPT)
    if not os.path.isfile(script):
        return {"ran": False, "why": "the script is not in this tree at all",
                "code": None, "text": "", "seconds": 0.0}
    try:
        proc = subprocess.run([sys.executable, CENSUS_SCRIPT, *extra],
                              cwd=cwd, capture_output=True, text=True,
                              timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired as exc:
        return {"ran": False, "why": f"it did not finish inside {TIMEOUT_S}s",
                "code": None, "text": str(exc)[:2000],
                "seconds": time.time() - started}
    return {"ran": True, "why": "", "code": proc.returncode,
            "text": (proc.stdout or "") + (proc.stderr or ""),
            "seconds": time.time() - started}


def read_findings(text):
    """Every finding the census printed, as {place, expectation, fact}.

    A finding opens with its PLACE line and the two lines under it fill it in, which is
    the order the census writes them in. A PLACE with nothing under it is kept with
    empty sides rather than dropped, because a finding this gate cannot read is a fact
    about the instrument and the rule below is what reports it.
    """
    rows = []
    for line in text.split("\n"):
        place = PLACE_RE.match(line)
        if place:
            rows.append({"place": place.group(1).strip(),
                         "expectation": "", "fact": ""})
            continue
        if not rows:
            continue
        expectation = EXPECTATION_RE.match(line)
        if expectation:
            rows[-1]["expectation"] = expectation.group(1).strip()
            continue
        fact = FACT_RE.match(line)
        if fact:
            rows[-1]["fact"] = fact.group(1).strip()
    return rows


def read_headline(text):
    """The census's own opening line as (word, number), or (None, None).

    This is the SECOND reading of the same quantity, and it exists because a count taken
    by one predicate says nothing until a second, independent one agrees with it. On a
    failing run the census states how many places it found before it lists them, so the
    comparison below is an exact reconstruction and not a resemblance. On a passing run
    the number in that line is the population it walked, which is why the word is
    returned beside it and the two are never mixed.
    """
    for line in text.split("\n"):
        failed = FAIL_RE.match(line)
        if failed:
            return "FAIL", int(failed.group(1))
        passed = PASS_RE.match(line)
        if passed:
            return "PASS", int(passed.group(1))
    return None, None


def date_only(finding):
    """Whether the two sides of a finding differ in nothing but a date.

    Blanking every date in both sides and asking whether what is left is the same string
    is the whole test, and it is deliberately narrow: one character of difference
    anywhere else and the answer is no. See the header for why this class is separated
    and why nothing can hide inside it.
    """
    expectation, fact = finding.get("expectation", ""), finding.get("fact", "")
    if not expectation or not fact or expectation == fact:
        return False
    return DATE_RE.sub("<date>", expectation) == DATE_RE.sub("<date>", fact)


# =====================================================================
# 2. THE FOURTH READING: THE BLOCK, READ WITHOUT THE CENSUS
# =====================================================================

def block_span(text):
    """(lines, first, last) around the derived block, or (lines, None, None)."""
    lines = text.split("\n")
    first = next((i for i, line in enumerate(lines) if line.startswith(BEGIN)), None)
    last = next((i for i, line in enumerate(lines) if line.startswith(END)), None)
    if first is None or last is None or last < first:
        return lines, None, None
    return lines, first, last


def scrape_block(text):
    """The counts the derived block STATES, read out of its own prose.

    THIS IS AN INDEPENDENT READING AND NOT A COPY OF THE CENSUS'S RENDERER. The census
    decides whether the block agrees with the tree by rendering the block again and
    diffing it; this reads the numbers a human reads and compares them with the tree the
    census reports in JSON. Two readings of one quantity, taken by two different methods,
    which is the only arrangement in which either one agreeing means anything.

    The cost of independence is that the phrases below are the census's rendering prose
    written a second time, so a change to its wording blinds this reader. That is why a
    count this reader CANNOT find is a finding rather than a skip: a scraper that reads
    nothing reports nothing, and reports it in the shape of good news.
    """
    lines, first, last = block_span(text)
    if first is None:
        return {}
    block = lines[first:last + 1]
    flowed = re.sub(r"\s+", " ", " ".join(line.lstrip("#").strip() for line in block))
    found = {}
    for name, pattern in (
            ("shipped .py files", r"all (\d+) shipped \.py files"),
            ("entry points", r"pipeline has (\d+) groups"),
            ("standard library modules", r"The (\d+) other modules")):
        hit = re.search(pattern, flowed)
        found[name] = int(hit.group(1)) if hit else None
    for distribution, _tops in DISTRIBUTIONS:
        # The column the census renders: the comment mark, the name padded out, the
        # count, then the word "files" and the sentence. Matched per line rather than on
        # the flowed text so that a name appearing inside a sentence cannot be read as a
        # count.
        per_line = re.compile(r"^#\s+" + re.escape(distribution) + r"\s+(\d+)\s+files?,")
        hit = next((per_line.match(line) for line in block if per_line.match(line)), None)
        found[distribution + " files"] = int(hit.group(1)) if hit else None
    return found


def tree_counts(census):
    """The same counts as the census reads them out of the tree."""
    counts = {"shipped .py files": census["population"],
              "entry points": len(census["entry_points"]),
              "standard library modules": len(census["standard_library"])}
    for distribution, _tops in DISTRIBUTIONS:
        counts[distribution + " files"] = census["packages"][distribution]["count"]
    return counts


def compare_counts(stated, derived):
    """(unreadable, disagreeing) between what the block says and what the tree holds."""
    unreadable = [name for name in derived if stated.get(name) is None]
    disagreeing = [(name, stated[name], derived[name]) for name in derived
                   if stated.get(name) is not None and stated[name] != derived[name]]
    return sorted(unreadable), sorted(disagreeing)


# =====================================================================
# 3. THE CALIBRATION MIRROR
# =====================================================================

def mirror_tree():
    """A copy of every shipped file of this tree, in a directory of its own.

    Asked of checks/evidence.shipped_tree_files, which is the same question the census
    itself asks, so the copy holds the census's population by construction rather than by
    resemblance. The copy carries no .git, so the census walks it recursively there and
    reads the git index here; that the two agree is the first calibration case below and
    not an assumption.

    Returns (directory, shipped, copied). The path is used and never recorded.
    """
    copy = tempfile.mkdtemp(prefix="requirements_census_calibration_")
    shipped = shipped_tree_files(ROOT)
    copied = 0
    for relative in shipped:
        source = os.path.join(ROOT, relative)
        if not os.path.isfile(source):
            continue
        target = os.path.join(copy, relative)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copyfile(source, target)
        copied += 1
    return copy, len(shipped), copied


def freshen_block(copy):
    """Rewrite the copy's derived block from the copy's own tree. Returns the new text.

    WHY THE FIXTURE HAS TO BE FRESHENED FIRST, AND IT WAS MEASURED RATHER THAN ARGUED. The
    pair below is built by breaking one line of the block on purpose and requiring the
    census to notice. A line that is ALREADY wrong cannot be broken again: on a copy of a
    tree whose block had fallen behind in two places, raising a count on a line that was
    already reported changed the finding and not the number of them, so the firing case
    read the same count as the silent one and went red -- on the very tree this gate
    exists to report on. A calibration case anchored on a defect erases itself.

    So the block is rendered from the tree before either case is built, and the pair then
    means the same thing in every state of the live tree.

    THE CENSUS'S OWN RENDERER IS CALLED, NOT COPIED. render() is the function --write
    uses; the counts handed to it are the counts the census itself reports for the copy,
    asked for in JSON. Nothing here knows how a line of that block is spelled, so this
    fixture cannot drift from the thing it is a fixture for. --write itself is never
    invoked, here or anywhere else in this gate.
    """
    asked = run_census(copy, ("--json",))
    path = os.path.join(copy, REQUIREMENTS)
    try:
        fresh = render(json.loads(asked["text"]))
    except (ValueError, KeyError, TypeError, SystemExit):
        return None
    with open(path, encoding="utf-8") as handle:
        lines, first, last = block_span(handle.read())
    if first is None:
        return None
    text = "\n".join(lines[:first] + list(fresh) + lines[last + 1:])
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return text


def bump_one_count(path):
    """Raise the first whole number of the derived block by one. Returns (before, after).

    The first standalone integer of the block is the population the census walked, and
    it shares its physical line with the date stamp, which is what makes the pair of
    cases below differ along one axis and no more: the same line is touched twice, once
    in its count and once in its date.
    """
    with open(path, encoding="utf-8") as handle:
        lines, first, last = block_span(handle.read())
    if first is None:
        return None
    for index in range(first, last + 1):
        hit = STANDALONE_INT_RE.search(lines[index])
        if not hit:
            continue
        before, after = hit.group(1), str(int(hit.group(1)) + 1)
        lines[index] = lines[index][:hit.start(1)] + after + lines[index][hit.end(1):]
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines))
        return before, after
    return None


def move_the_date(path):
    """Move the first date of the derived block and nothing else. Returns (before, after).

    The replacement keeps the length of what it replaces, so the census's own wrapping
    cannot move and the finding it reports is about the date and about nothing else.
    """
    with open(path, encoding="utf-8") as handle:
        lines, first, last = block_span(handle.read())
    if first is None:
        return None
    for index in range(first, last + 1):
        hit = DATE_RE.search(lines[index])
        if not hit:
            continue
        before = hit.group(0)
        after = ("1999" if before.startswith("2000") else "2000") + before[4:]
        lines[index] = lines[index][:hit.start()] + after + lines[index][hit.end():]
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines))
        return before, after
    return None


def block_findings(findings):
    """The findings that name a line of the derived block, and only those.

    The census answers two questions in one run: whether the derived block matches the
    tree, and whether the prose ABOVE the block names the same entry points the run/
    directory holds. The second is a real finding and it is not what the calibration
    fixtures below break, so counting it among them would make a case pass or fail for a
    reason outside its own axis. Recognised by the census's own way of naming a place: a
    block finding carries the line it sits on, an entry-point finding carries a script.
    """
    return [f for f in findings if BLOCK_LINE_RE.search(f.get("place") or "")]


def noise_case(live_run):
    """The case a reader drawn too wide would fail, on the live run's own bytes.

    The census prints its verdict, its repair command and its blank lines, and none of
    those is a finding. Built from what this run printed rather than from an invented
    line, so it cannot go stale against a change in the way the census prints.
    """
    other = [line for line in (live_run["text"] if live_run["ran"] else "").split("\n")
             if line.strip() and not PLACE_RE.match(line)
             and not EXPECTATION_RE.match(line) and not FACT_RE.match(line)]
    if not other:
        return ("only a finding is counted",
                "must never happen: the census printed no line at all that is not part "
                "of a finding, so this case has nothing to be built from",
                0, "at least one line", False)
    noise = read_findings("\n".join(other))
    return ("only a finding is counted",
            f"must stay silent: the {len(other)} lines of this run that are not part of "
            f"a finding, the verdict and the repair command among them",
            len(noise), 0, len(noise) == 0)


def calibrate(live_run, live_findings):
    """Five cases through the whole instrument, four of them on a copy of this tree.

    ONE REFERENCE POINT CANNOT CALIBRATE A GATE: it cannot tell one that is too wide from
    one that is too narrow, and both failures look identical from the outside -- a gate
    reporting nothing. So the cases come in opposite pairs. A copy with nothing changed
    must read exactly what the live tree read, which on a tree whose block agrees is
    silence; the same copy with one count raised by one must fire. A finding whose sides
    differ in a count must not be read as a date stamp; one whose sides differ in nothing
    but a date must be, and must add no other kind.

    EVERY CASE IS STATED AS A DIFFERENCE FROM THE PRISTINE COPY RATHER THAN AS AN
    ABSOLUTE, and that is what keeps the pair honest on a day when the block HAS fallen
    behind. Written as "the copy must find nothing", the silent case would go red on
    exactly the tree this gate exists to report on, and the gate would then print that its
    own reading could not be trusted while the reading was correct and damning. Written as
    a difference, the axis stays one digit of one line in every state of the tree.

    Nothing is invented. A fixture written to the shape a format is supposed to have
    certifies the shape and not the format, and this repository has already paid for that
    once. Every case here is this tree's own bytes, put through the same reader the live
    run goes through, which also means the calibration cannot go stale against a change
    in the way the census prints.
    """
    cases = []
    copy = None
    base = []
    try:
        copy, shipped, copied = mirror_tree()
        cases.append((
            "the mirror is complete",
            f"must copy every shipped file, or the cases under it compare two "
            f"different trees: {shipped} shipped",
            copied, shipped, copied == shipped))

        requirements = os.path.join(copy, REQUIREMENTS)
        quiet = run_census(copy)
        base = read_findings(quiet["text"])
        cases.append((
            "the mirror reads what the tree reads",
            f"must repeat the live run exactly, or the cases under it are about some "
            f"other tree: the live run exited {live_run['code']} with "
            f"{len(live_findings)} finding(s)",
            (quiet["code"], len(base)),
            (live_run["code"], len(live_findings)),
            quiet["code"] == live_run["code"] and len(base) == len(live_findings)))

        fresh = freshen_block(copy)
        if fresh is None:
            cases.append(("the fixture could not be built",
                          "must never happen: the census's own renderer would not "
                          "rewrite the derived block of the copy", None, "a block",
                          False))
            return cases + [noise_case(live_run)]
        silent = block_findings(read_findings(run_census(copy)["text"]))
        cases.append((
            "the block against the tree",
            "must stay silent: the copy with its derived block rendered from the copy's "
            "own tree by the census's own renderer",
            len(silent), 0, len(silent) == 0))

        moved = bump_one_count(requirements)
        if moved is None:
            cases.append(("the firing case could not be built",
                          "must never happen: the derived block of the copy carries no "
                          "whole number to raise", None, "a number", False))
        else:
            loud = run_census(copy)
            loud_real = [f for f in block_findings(read_findings(loud["text"]))
                         if not date_only(f)]
            cases.append((
                "the block against the tree",
                f"must fire: that same freshened copy with one count of the block raised "
                f"from {moved[0]} to {moved[1]} and nothing else touched",
                (loud["code"] != 0, len(loud_real)), (True, ">=1"),
                loud["code"] != 0 and len(loud_real) >= 1))

        with open(requirements, "w", encoding="utf-8") as handle:
            handle.write(fresh)
        stamped = move_the_date(requirements)
        if stamped is None:
            cases.append(("the date case could not be built",
                          "must never happen: the derived block of the copy carries no "
                          "date", None, "a date", False))
        else:
            dated = block_findings(read_findings(run_census(copy)["text"]))
            dated_real = [f for f in dated if not date_only(f)]
            dated_stamps = [f for f in dated if date_only(f)]
            # THIS CASE ASKS FOR SILENCE, AND UNTIL 2026-08-30 IT ASKED FOR A FINDING.
            # The census used to compare the line that carries the day it was taken, so a
            # copy whose stored date had moved and nothing else reported one finding whose
            # two sides differed in the date alone. That was measured, and the census was
            # then made blind to that date: the stamp is still written, because a reader
            # wants to know when the counts were taken, and it is no longer one of the
            # things the two blocks are asked to agree about. So the honest expectation
            # here is now zero findings of either kind. The classification of a date-only
            # finding is kept rather than deleted, because it is the thing that would tell
            # a later reader WHY this gate went red if the blindness were ever undone.
            cases.append((
                "a date stamp is not read as tree drift",
                f"must stay silent: that same freshened copy with its stored date moved "
                f"from {stamped[0]} to {stamped[1]} and nothing else touched reports no "
                f"finding at all, because the census does not compare the day it stamps",
                (len(dated_stamps), len(dated_real)), (0, 0),
                len(dated_stamps) == 0 and len(dated_real) == 0))
    finally:
        if copy and os.path.isdir(copy):
            shutil.rmtree(copy, ignore_errors=True)

    return cases + [noise_case(live_run)]


# =====================================================================
# 4. THE GATE
# =====================================================================

def block_first_line(text):
    """Where the derived block opens in requirements.txt, 1-based, or 0."""
    _lines, first, _last = block_span(text)
    return 0 if first is None else first + 1


def file_line(place, opens_at):
    """The line of requirements.txt a finding sits on, or 0.

    The census counts lines from the start of the derived block, because that is the
    region it owns. A reader opens a file. Adding the offset is what turns one into the
    other; a place that names no line at all -- the entry-point findings name a script --
    returns 0 rather than a guess.
    """
    hit = BLOCK_LINE_RE.search(place or "")
    if not hit or not opens_at:
        return 0
    return opens_at + int(hit.group(1)) - 1


def last_words(text):
    """The last line of the output carrying anything to read, for a failed run.

    A run that died leaves its reason in the last line that says something, and the
    literal last line is often blank. Quoting a blank line is quoting nothing, which is
    the shape of evidence without the evidence.
    """
    for line in reversed(text.strip().split("\n")):
        if any(character.isalnum() for character in line):
            return redact(line.strip())[:200]
    return ""


def main():
    started = artifact.start_clock()
    run = run_census(ROOT)
    findings = read_findings(run["text"])
    word, number = read_headline(run["text"])
    stamps = [f for f in findings if date_only(f)]
    real = [f for f in findings if not date_only(f)]

    try:
        with open(root_file(REQUIREMENTS), encoding="utf-8") as handle:
            requirements_text = handle.read()
    except OSError:
        requirements_text = ""
    opens_at = block_first_line(requirements_text)

    def site(finding, rule):
        return {"file": REQUIREMENTS,
                "line": file_line(finding["place"], opens_at),
                "rule": rule,
                "detail": redact(finding["place"])[:160],
                "source": redact(f"expected {finding['expectation']!r}; the file holds "
                                 f"{finding['fact']!r}")[:400]}

    sites_real = [site(f, "BLOCK-DISAGREES-WITH-TREE") for f in real]
    sites_stamp = [site(f, "BLOCK-DATE-STAMP-ONLY") for f in stamps]

    # THE FOURTH READING, TAKEN WITHOUT THE CENSUS'S DIFF. The counts read out of the
    # block's prose against the same counts asked of the tree, so that a census printing
    # PASS over a stale block is caught by something that does not share its logic.
    asked = run_census(ROOT, ("--json",))
    try:
        tree = tree_counts(json.loads(asked["text"]))
    except (ValueError, KeyError, TypeError):
        tree = {}
    stated = scrape_block(requirements_text)
    unreadable_counts, disagreeing_counts = compare_counts(stated, tree)

    # THE INSTRUMENT, ASKED BEFORE THE TREE. Each entry below is a way for the counts
    # above to be wrong rather than for the block to be stale, and they are kept apart
    # because the two send a reader to different places.
    unreadable, disagreements = [], []
    if not run["ran"]:
        unreadable.append({
            "file": CENSUS_SCRIPT, "line": 0, "rule": "CENSUS-DID-NOT-RUN",
            "detail": f"CENSUS-DID-NOT-RUN: the census did not finish: {run['why']}",
            "source": last_words(run["text"])})
    elif word is None:
        unreadable.append({
            "file": CENSUS_SCRIPT, "line": 0, "rule": "CENSUS-PRINTED-NOTHING-READABLE",
            "detail": f"CENSUS-PRINTED-NOTHING-READABLE: the run exited {run['code']} "
                      f"and printed no opening line this gate can read as a verdict, so "
                      f"its answer is unknown rather than clean",
            "source": last_words(run["text"])})
    if not tree:
        unreadable.append({
            "file": CENSUS_SCRIPT, "line": 0, "rule": "CENSUS-JSON-UNREADABLE",
            "detail": "CENSUS-JSON-UNREADABLE: the census asked for the tree in JSON did "
                      "not return a census, so the counts of the block were compared "
                      "against nothing",
            "source": last_words(asked["text"])})
    for name in unreadable_counts:
        unreadable.append({
            "file": REQUIREMENTS, "line": opens_at, "rule": "BLOCK-COUNT-UNREADABLE",
            "detail": f"BLOCK-COUNT-UNREADABLE: the derived block states no count of "
                      f"{name} this gate can read, so its agreement with the tree was "
                      f"not measured. Either the block lost the sentence or the census "
                      f"changed the words it renders",
            "source": f"the tree holds {tree.get(name)}"})

    if word is not None:
        # Three readings of one quantity, compared. The exit code is a fact of the
        # process, the opening line is the census's own summary, and the findings are
        # what this gate counted; two of them agreeing while the third does not is a
        # broken instrument, whichever two they are.
        if word == "FAIL" and number != len(findings):
            disagreements.append({
                "file": CENSUS_SCRIPT, "line": 0, "rule": "TWO-READINGS-DISAGREE",
                "detail": f"TWO-READINGS-DISAGREE: the census says it found {number} "
                          f"places and this gate read {len(findings)} of them out of "
                          f"the same output",
                "source": f"stated {number}, read {len(findings)}"})
        if word == "PASS" and findings:
            disagreements.append({
                "file": CENSUS_SCRIPT, "line": 0, "rule": "TWO-READINGS-DISAGREE",
                "detail": f"TWO-READINGS-DISAGREE: the opening line says the block "
                          f"agrees with the tree and {len(findings)} finding(s) are "
                          f"printed under it",
                "source": "; ".join(f["place"] for f in findings)[:200]})
        if (run["code"] == 0) != (word == "PASS"):
            disagreements.append({
                "file": CENSUS_SCRIPT, "line": 0, "rule": "EXIT-CODE-DISAGREES",
                "detail": f"EXIT-CODE-DISAGREES: the process exited {run['code']} and "
                          f"its own opening line says {word}; the census returns 1 when "
                          f"and only when the block disagrees with the tree",
                "source": f"exit {run['code']}, opening line {word}"})
    if run["code"] == 0 and disagreeing_counts:
        # The reading that does not share the census's logic, contradicting it. This is
        # the one that catches a census whose diff has stopped seeing.
        disagreements.append({
            "file": REQUIREMENTS, "line": opens_at, "rule": "FOURTH-READING-DISAGREES",
            "detail": f"FOURTH-READING-DISAGREES: the census exited 0, and "
                      f"{len(disagreeing_counts)} of the counts read straight out of the "
                      f"derived block are not the counts the same census reports for "
                      f"the tree",
            "source": "; ".join(f"{name}: the block says {said}, the tree holds {held}"
                                for name, said, held in disagreeing_counts)[:400]})

    cal = calibrate(run, findings)
    cal_failed = [c for c in cal if not c[4]]
    broken = bool(unreadable or disagreements or cal_failed or not cal)
    verdict = "FAIL" if (real or broken) else "PASS"

    print("=" * 76)
    print("  THE REQUIREMENTS CENSUS, RUN AS A GATE")
    print("=" * 76)
    print(f"  ran                : {CENSUS_SCRIPT} with no arguments, "
          f"{run['seconds']:.1f}s, exit {run['code']}")
    print(f"  calibration cases  : {len(cal)}, failed {len(cal_failed)}")
    for name, what, got, want, ok in cal:
        print(f"  {'ok  ' if ok else 'FAIL'} {name}: {what}")
        if not ok:
            print(f"       expected {want!r}, got {got!r}")
    print(f"  findings read      : {len(findings)}, of which {len(stamps)} differ in "
          f"nothing but a date")
    print(f"  block against tree : {len(tree)} counts asked of the tree, "
          f"{len(unreadable_counts)} unreadable in the block, "
          f"{len(disagreeing_counts)} disagreeing")
    for finding in sites_real:
        print(f"  STALE        {finding['file']}:{finding['line']}  "
              f"{finding['detail'][:70]}")
        print(f"      | {finding['source'][:150]}")
    for finding in sites_stamp:
        print(f"  date stamp   {finding['file']}:{finding['line']}  "
              f"{finding['detail'][:70]}")
        print(f"      | {finding['source'][:150]}")
    if stamps:
        # Printed and deliberately NOT counted against the exit code, with the repair
        # named. A count nobody is reminded of stops being a debt and becomes a habit.
        print(f"  {len(stamps)} finding(s) differ in nothing but the date the census "
              f"stamps into the block as it renders it, so they report the calendar "
              f"rather than the tree. The repair is in {CENSUS_SCRIPT}: render the stamp "
              f"outside the compared region, or compare each line with its date blanked.")
    if real:
        print(f"  Repair: uv run --no-project python3 {CENSUS_SCRIPT} --write")
    if broken:
        print("  the block is not judged on this run: the reading above could not be "
              "trusted, and a count taken from it would be a count of nothing.")
    print("-" * 76)
    print(f"  VERDICT: {verdict}")
    print(f"  results -> {os.path.basename(OUT_JSON)}")

    artifact.write(
        os.path.basename(OUT_JSON),
        {"verdict": verdict,
         "n_findings": len(findings),
         "n_stale": len(real),
         "n_date_stamp_only": len(stamps),
         "stale": sites_real,
         "date_stamp_only": sites_stamp,
         # The fourth reading, written down beside the census's own so that the two can
         # be compared with each other next week rather than each with itself.
         "counts_stated_in_block": stated,
         "counts_held_by_tree": tree,
         "counts_disagreeing": [{"name": n, "block": b, "tree": t}
                                for n, b, t in disagreeing_counts],
         "instrument": {"exit_code": run["code"],
                        "seconds": round(run["seconds"], 1),
                        "opening_word": word,
                        "opening_number": number,
                        "unreadable": unreadable,
                        "disagreements": disagreements},
         "calibration": [{"predicate": n, "case": w, "got": repr(g), "want": repr(x),
                          "ok": ok} for n, w, g, x, ok in cal]},
        script=__file__,
        # The census and the file it writes into, both hashed. That is what makes this
        # gate's record move when the thing it reports on moves: the freshness gates of
        # this directory ask whether an artifact still stands on the version of each
        # input it recorded, and this artifact is a statement about those two files on
        # one particular day.
        inputs=[root_file(CENSUS_SCRIPT), root_file(REQUIREMENTS)],
        scope={
            "population": (f"the derived block of {REQUIREMENTS} against the syntax "
                           f"tree of every shipped .py file of this repository, which "
                           f"the census walked on this run"),
            "window": "n/a: this gate reads a program's output, not a period of market "
                      "data",
            "coins": "n/a: this gate reads no market data",
        },
        started=started,
        extra_meta={
            "runtime_seconds_of_census": round(run["seconds"], 1),
            "date_stamp_note": (
                "findings whose two sides are equal once every date in them is blanked "
                "are counted apart and never fail this gate. The census renders the "
                "block with the date of the run that renders it and then compares the "
                "whole line, so the day after a regeneration it reports one such finding "
                "with the tree unmoved. Measured on a copy of this tree on 2026-08-30 by "
                "moving the stored date back one day: the census exits 1 and names that "
                "line. Arming this rule is a decision for the owner of the census, not "
                "for this gate; the repair is to render the stamp outside the compared "
                "region or to compare each line with its date blanked"),
            "n_calibration_cases": len(cal),
            "n_calibration_failed": len(cal_failed),
        },
    )

    if cal_failed:
        print("  CALIBRATION FAILED: no zero in this report can be believed.")

    return report_gate(
        [{"name": "BLOCK-DISAGREES-WITH-TREE",
          "permitted": 0,
          "found": len(real),
          "assumption": ("the census inside requirements.txt is derived from the syntax "
                         "tree of every shipped .py file, and until 2026-08-30 the "
                         "program that derives it was in no group of this battery, so "
                         "the block could fall behind while the battery beside it "
                         "printed zero failures"),
          "method": (f"{CENSUS_SCRIPT} run with no arguments, its findings read from "
                     f"its own PLACE, EXPECTATION and FACT lines, and the count "
                     f"cross-read against the number it states for itself and against "
                     f"the process exit code"),
          "note": ("a reader of requirements.txt is being told how many files this "
                   "repository ships and which of them need each pinned package, and "
                   "the numbers are not the tree's. The repair is one command: "
                   f"{CENSUS_SCRIPT} --write"),
          "sites": sites_real},
         {"name": "BLOCK-DATE-STAMP-ONLY",
          # UNARMED ON PURPOSE, and the reason is in the header and in the artifact. The
          # finding is real and it is not about the tree; arming it belongs to whoever
          # owns the census, because the repair is a change to how the census renders.
          "permitted": None,
          "found": len(stamps),
          "assumption": ("a finding whose two sides are equal once every date in them is "
                         "blanked reports the calendar and not the tree: the census "
                         "stamps the block with the date of the run that renders it and "
                         "then compares the whole line"),
          "method": "both sides of each finding with every date blanked, compared as "
                    "strings",
          "note": "counted and printed, never failing. The repair lives in the census",
          "sites": sites_stamp},
         {"name": "CENSUS-UNREADABLE",
          "permitted": 0,
          "found": len(unreadable),
          "assumption": ("the census finishes, prints the shape this gate reads, answers "
                         "in JSON when asked for the tree, and the block states every "
                         "count this gate compares. A run that died and a block with "
                         "nothing wrong both produce no findings, and only this rule "
                         "tells them apart"),
          "method": "the process is required to return, to open with its own verdict "
                    "line, to return a census in JSON, and the block is required to "
                    "state each of the counts in words this gate can read",
          "note": "nothing was measured about the block on this run",
          "sites": unreadable},
         {"name": "READINGS-DISAGREE",
          "permitted": 0,
          "found": len(disagreements),
          "assumption": ("four readings of one quantity agree: the findings counted "
                         "here, the number the census states for itself, the exit code "
                         "of the process, and the counts read straight out of the block "
                         "and compared with the tree without the census's diff"),
          "method": "the findings are counted against the number the census names, the "
                    "exit code is required to follow the verdict word, and the block's "
                    "own counts are compared with the census asked for the tree in "
                    "JSON",
          "note": "the count of findings cannot be trusted, in either direction, until "
                  "the disagreement is explained",
          "sites": disagreements},
         {"name": "CALIBRATION",
          "permitted": 0,
          "found": len(cal_failed) if cal else 1,
          "assumption": ("the gate is shown to fire on a block that has fallen behind "
                         "and to stay silent on one that has not, on a copy of this "
                         "tree rather than on an invented example. Without that, a clean "
                         "report is indistinguishable from a gate that reports nothing"),
          "method": "a copy of every shipped file of this tree, censused with nothing "
                    "changed, then with one count of the block raised by one, then with "
                    "only its date moved; and the lines of the live run that are not "
                    "findings",
          "note": "no count in this report can be believed",
          "sites": [{"file": os.path.basename(__file__), "line": 0,
                     "detail": f"{name}: {what}", "source": f"want {want!r}, got {got!r}"}
                    for name, what, got, want, ok in cal if not ok]}],
        OUT_JSON,
        inputs={"census": f"{CENSUS_SCRIPT}, {len(findings)} finding(s), "
                          f"{run['seconds']:.1f}s",
                "block": f"{REQUIREMENTS}, derived block opening at line {opens_at}"})


if __name__ == "__main__":
    sys.exit(main())
