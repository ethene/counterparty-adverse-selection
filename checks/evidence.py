#!/usr/bin/env python3
"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-07-30
References: none (shared reporting helper for the checks in this directory).

WHEN A CHECK DISAGREES WITH THE DATA IT PRINTS THE EXPECTATION, THE FACT AND THE
PLACE.

Why this module exists, and it is two defects rather than one.

The first was measured. Seven of the thirteen checks here never exited non-zero.
They computed a verdict, wrote "overall_verdict": "refuted" into their own results
file, printed one summary line, and returned None, which is exit 0. A runner that
reads exit codes -- run_all_checks.py, or a newcomer following the README -- saw
green. A check that cannot fail is not a check, it is a report nobody reads, and
the whole point of putting the thirteen behind one command was that the command
means something.

The second cost an evening. chk_maker_attribution came back non-zero inside the
runner with the single line "one or more verdicts FAILED (see JSON)". Which
verdict, what it expected, what it found and which record disagreed were all in
the JSON, and none of it was on the screen, so the only way to learn the cause was
to run the check again by hand. A gate that reports a failure without the evidence
turns a real regression into a rumour and trains people to re-run instead of read.

So this module owns the two shared boundaries every repository check needs. First, it
turns the verdict contract those checks already build into a printed failure and an
exit code. Second, `shipped_tree_files` defines the file population once: a Git
checkout reads its index, while an extracted source archive walks the same shipped
tree and excludes only generated interpreter/tool caches. Four gates used to invoke
`git ls-files` themselves and therefore died before asking their question when a
source ZIP had no `.git` directory.

The verdict contract is theirs, not this module's -- a list of sub-checks, each with

    name        what was tested
    assumption  the EXPECTATION, in words, written before the data was read
    method      how it was measured, so a reader can repeat it
    observed    the FACT, as numbers
    verdict     confirmed | refuted | uncertain
    note        what a mismatch would mean

-- and every one of those fields was already being written and thrown away. This
prints them, in that order, for exactly the sub-checks that did not confirm.

CONFIRMED, REFUTED AND UNCERTAIN ARE THREE STATES AND ONLY ONE OF THEM FAILS.
`refuted` means the data contradicts the assumption: the run exits non-zero.
`uncertain` means the leg did not run at all -- the raw tape was unreachable, the
npz was absent, --smoke skipped it. That is not a defect in the repository and
failing on it would make the offline runs red for a reason nobody can act on. It
is printed as loudly as a refutation, under a heading that says the question was
NOT ANSWERED, because the failure this project actually made was reading a check
that had skipped its evidence leg as a check that had passed.

    from evidence import report_contract
    return report_contract(contract, OUT_JSON, inputs={"npz": NPZ_PATH})

THREE SHAPES OF CHECK, SO THREE ENTRY POINTS, AND THE SHAPE IS THEIRS NOT OURS.
`report_contract` serves the checks that build the sub-check contract above.
`report_verdicts` serves the raw-tape checks that keep a flat name -> True/False map
instead. `report_gate` serves the repository gates that count findings against a
declared ceiling -- absolute paths, horizon literals, second homes for a setting --
where the expectation is not a sentence about market data but a number of findings the
gate tolerates, and the place is a file and a line. Rewriting them into one shape would
have been a bigger change than the defect warranted, so the module speaks all three and
the failure prints the same three parts either way.

How many callers of each there are is deliberately NOT written here. It was, as eight,
two and three, and by 2026-08-05 the true counts were nine, two and eight: a number
typed beside the thing it counts goes stale in silence, which is a defect this
repository has met in its plan counters and in this file's own assertion tally. The
count is taken by walking the directory when somebody needs it.

WHAT THE THIRD PART OF A FAILURE POINTS AT IS NOW CHECKED. Every reporter here ends by
naming the file holding the full records, and until 2026-08-05 none of them looked to
see whether that file was there. See _records for what that cost and why the check
belongs in this module rather than in its callers.
"""
import json
import os
import subprocess
import sys

# How many leaves of `observed` to print per failing sub-check. The whole of it is
# in the results file; the screen gets enough to say what disagreed. Twenty-five is
# the largest `observed` block any of the current checks builds plus a margin.
MAX_LEAVES = 25

# How deep to walk a nested `observed` block. The cross-tab in chk_dir_vs_startpos
# nests two levels, so three leaves the room to add one without silently truncating.
MAX_DEPTH = 3

# Generated caches are not part of a source release even when a tool creates them in
# the extracted directory before a later gate starts. Nothing else is excluded by the
# archive fallback: hidden files, documentation and result artifacts all belong to the
# same population Git would enumerate in a checkout.
GENERATED_CACHE_DIRS = frozenset({
    "__pycache__", ".ipynb_checkpoints", ".mypy_cache", ".pytest_cache",
    ".ruff_cache",
})
GENERATED_CACHE_SUFFIXES = (".pyc", ".pyo")


class EmptyPopulation(SystemExit):
    """Raised when the shipped-file population is empty: a closed refusal, never a PASS.

    A SystemExit so that every gate standing on shipped_tree_files exits non-zero with
    the reason printed, without each of them having to remember to ask.
    """


def _refuse_empty(root, how):
    message = (f"shipped_tree_files: the population is EMPTY ({how}) under "
               f"{os.path.basename(root) or root}. A gate over zero files would print "
               "PASS about a tree it never read, so this refuses instead. In a Git "
               "checkout with no commit yet, stage or commit the files first "
               "(`git add -A`); in a source archive, check that it was extracted.")
    print(message, file=sys.stderr)
    raise EmptyPopulation(2)


def shipped_tree_files(root):
    """Every shipped file below *root*, repo-relative and deterministically sorted.

    A real checkout is identified only when `git rev-parse --show-toplevel` resolves
    to *root* itself. This prevents an extracted archive placed inside some unrelated
    parent repository from silently borrowing the parent's index. When that exact Git
    root is unavailable, recursive enumeration is the source-archive equivalent.

    AN EMPTY POPULATION IS REFUSED, NOT RETURNED. In a checkout the population is the
    index, which is what a commit ships, and in a repository with nothing staged that
    is the empty list: measured 2026-10-21 on a fresh checkout of this tree, where every
    gate standing on this function scanned 0 files and printed PASS. So an empty answer,
    from either branch, raises EmptyPopulation and the gate exits 2 with the reason.
    """
    root = os.path.realpath(os.path.abspath(root))
    try:
        probe = subprocess.run(
            ["git", "-C", root, "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=False)
    except OSError:
        probe = None
    if (probe is not None and probe.returncode == 0
            and os.path.realpath(probe.stdout.strip()) == root):
        listed = subprocess.run(
            ["git", "-C", root, "ls-files", "-z"],
            capture_output=True, check=True).stdout
        found = sorted(os.fsdecode(path) for path in listed.split(b"\0") if path)
        if not found:
            _refuse_empty(root, "git index of this checkout lists no file")
        return found

    found = []
    for current, dirs, files in os.walk(root, topdown=True, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in GENERATED_CACHE_DIRS)
        for name in sorted(files):
            if name.endswith(GENERATED_CACHE_SUFFIXES):
                continue
            absolute = os.path.join(current, name)
            found.append(os.path.relpath(absolute, root).replace(os.sep, "/"))
    if not found:
        _refuse_empty(root, "no Git checkout here, and the directory walk found no file")
    return sorted(found)


def _leaves(node, prefix="", depth=0):
    """(dotted key, value) for every scalar in a nested observed block."""
    if depth > MAX_DEPTH:
        yield prefix or "value", "..."
        return
    if isinstance(node, dict):
        for key, value in node.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            yield from _leaves(value, path, depth + 1)
    elif isinstance(node, (list, tuple)):
        if all(not isinstance(v, (dict, list, tuple)) for v in node):
            yield prefix or "value", list(node)
        else:
            for i, value in enumerate(node):
                yield from _leaves(value, f"{prefix}[{i}]", depth + 1)
    else:
        yield prefix or "value", node


def _fmt(value):
    if isinstance(value, float):
        return f"{value:.6g}"
    return json.dumps(value) if isinstance(value, (list, dict)) else str(value)


def _place(value):
    """A read input, named as fully as it can be without naming the machine.

    Every input used to be shortened to its basename whenever it held a separator.
    That was wrong, and the proof run of this module's own wiring on 2026-07-31 is
    what showed it: an S3 key printed as "23.lz4" and a Zenodo URL as "content", so
    the one line whose whole job is to say WHERE became the line that hid it.

    Only a LOCAL ABSOLUTE path needs shortening, because that is the string that
    carries an account name into a published artifact. A URL, an S3 key and a
    repo-relative path each say more whole than in pieces, and none of them names
    the machine.
    """
    text = str(value)
    if "://" in text:
        return text
    return os.path.basename(text) if os.path.isabs(text) else text


def _wrap(text, width, indent):
    """Wrap prose so a long assumption stays readable in a terminal."""
    words, lines, line = str(text).split(), [], ""
    for word in words:
        if line and len(line) + 1 + len(word) > width:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        lines.append(line)
    return ("\n" + indent).join(lines) if lines else ""


def _block(index, sub, results_file, inputs, heading):
    """Print one sub-check as expectation, fact and place."""
    name = sub.get("name", f"check[{index}]")
    print()
    print(f"  {heading}: {name}")
    if sub.get("assumption"):
        print(f"      expected  : {_wrap(sub['assumption'], 66, ' ' * 18)}")
    if sub.get("method"):
        print(f"      measured  : {_wrap(sub['method'], 66, ' ' * 18)}")
    observed = sub.get("observed")
    if observed is not None:
        rows = list(_leaves(observed))
        print("      found     : " + ("" if rows else "(nothing recorded)"))
        for key, value in rows[:MAX_LEAVES]:
            print(f"                    {key} = {_fmt(value)}")
        if len(rows) > MAX_LEAVES:
            print(f"                    ... and {len(rows) - MAX_LEAVES} more, "
                  f"all of them in {os.path.basename(results_file)}")
    if sub.get("note"):
        print(f"      means     : {_wrap(sub['note'], 66, ' ' * 18)}")
    # The place is two things and both are needed: where to read the full record,
    # and what the check was reading when it disagreed. A failure whose inputs are
    # unnamed cannot be reproduced by anyone who did not run it.
    print(f"      place     : {os.path.basename(results_file)} -> "
          f'checks[{index}] ("{name}")')
    for label, value in (inputs or {}).items():
        shown = _place(value)
        print(f"                  read {label} = {shown}")


def _records_path(results_file):
    """`results_file` as a path on disk, resolved the way its caller meant it.

    The parameter arrives in two shapes and always has. Three of the gates pass the
    bare file name and the other callers pass the whole path their own os.path.join
    built; both name the same file, because artifact.write puts an artifact beside the
    script that writes it.

    A bare name is therefore resolved against the directory of the module that called
    in here, taken from the call stack rather than from this module's own location.
    Assuming this module's directory would be right today only because every caller
    happens to be its neighbour, and would go quietly wrong the day one moves.
    """
    if os.path.isabs(results_file):
        return results_file
    mine = os.path.abspath(__file__)
    frame = sys._getframe(1)
    while frame is not None:
        caller = frame.f_globals.get("__file__")
        if caller and os.path.abspath(caller) != mine:
            return os.path.join(os.path.dirname(os.path.abspath(caller)), results_file)
        frame = frame.f_back
    return os.path.join(os.path.dirname(mine), results_file)


def _records(results_file):
    """The line saying where the full records are, checked before it is printed.

    THE POINTER USED TO BE A SENTENCE NOBODY HAD LOOKED AT. All three reporters printed
    `full records -> x.json` from the name they were handed and none of them ever asked
    whether x.json was there. Measured over this tree on 2026-08-05: nineteen scripts
    call these three reporters, eighteen of them write that file through artifact.py
    before they report, and one, a column check on the feature frame that is no longer
    part of this repository, built the path, handed it over and wrote nothing. For that one the line was a sentence about a file that
    had never existed, so a red run sent its reader to nothing and a green run left
    nothing behind at all.

    Which direction of error that is, is the whole reason it is checked here rather
    than left to the caller. A gate that goes red when it should not stops the work and
    costs an hour. A line that reads as evidence where there is no evidence passes
    straight through and is read later as work that was done.

    Returns (text, ok). When the records are there the text is the pointer as before.
    When they are not it is a mismatch in the same three parts as every other failure
    in this directory, built by the same mismatch_text the hard stops use, so that
    absent records read like a finding rather than like a footnote.

    WHAT THIS DELIBERATELY DOES NOT ASK is whether the file is a canonical artifact
    carrying a producer block and its inputs. That question has an owner already,
    checks/chk_artifact_provenance.py, and a check that repeats another check's
    predicate begins asserting the old rule on the day the rule is fixed.
    """
    path = _records_path(results_file)
    name = os.path.basename(results_file)
    # The place, named without naming the machine, by the same rule _place keeps: the
    # directory the file belongs in, and the file, and nothing above that.
    where = os.path.join(os.path.basename(os.path.dirname(path)), name)
    if not os.path.exists(path):
        found = "no such file; this run left no records at all"
    elif os.path.getsize(path) == 0:
        found = "the file is there and holds no bytes"
    else:
        return f"  full records -> {name}", True
    return mismatch_text(
        "the full records this check points at",
        f"{name} on disk beside the script that reported, holding the whole finding "
        f"list this screen is an extract of",
        found,
        where,
        "a summary whose records are absent cannot be read back, re-checked, or "
        "compared with the next run. Write the file through artifact.py, which is "
        "what the other callers of this module do, rather than dropping the pointer"
    ), False


def report_contract(contract, results_file, inputs=None, extra=None,
                    informational=()):
    """Print the evidence for every sub-check that did not confirm; return an exit code.

    Returns 1 when any sub-check is `refuted`, 0 otherwise. `uncertain` is printed
    but does not fail: it says a leg did not run, which is a fact about the machine
    rather than about the repository, and a gate that goes red offline stops being
    run at all.

    `informational` names the sub-checks whose `uncertain` is BY DESIGN rather than a
    leg that failed to run -- a descriptive cross-tab, a diagnostic with no clean
    directional expectation. They carry `uncertain` because the contract has no
    fourth word for "reported, not judged", and printing them as unanswered on every
    green run would teach a reader to skim the block where the real one appears.
    They are listed by name so that the exemption is a decision on the screen rather
    than an invisible default.

    `inputs` names what the check read, so the printed failure can be reproduced
    without opening the script. `extra` is any further evidence the caller measured
    outside the contract and wants on the screen beside it.

    It also returns 1 when `results_file` is not on disk, whatever the sub-checks said.
    A contract that confirms every leg and leaves no record behind has not reported;
    the reasoning is in _records.
    """
    subs = contract.get("checks", []) or []
    overall = contract.get("overall_verdict", "uncertain")
    skip = set(informational)
    refuted = [(i, s) for i, s in enumerate(subs) if s.get("verdict") == "refuted"]
    unknown = [(i, s) for i, s in enumerate(subs)
               if s.get("verdict") == "uncertain" and s.get("name") not in skip]

    records, records_ok = _records(results_file)

    if refuted or unknown or not records_ok:
        print("-" * 78)
    for index, sub in refuted:
        _block(index, sub, results_file, inputs, "MISMATCH")
    for index, sub in unknown:
        _block(index, sub, results_file, inputs, "NOT ANSWERED")

    if extra:
        print()
        for key, value in extra.items():
            print(f"  {key}: {value}")

    if refuted:
        print()
        print(f"  VERDICT: REFUTED - {len(refuted)} of {len(subs)} sub-checks "
              f"contradict their assumption; the expectation, the fact and the "
              f"place of each are printed above")
        print(records)
        return 1
    if unknown:
        print()
        print(f"  VERDICT: {overall.upper()} - {len(unknown)} of {len(subs)} "
              f"sub-checks did NOT run, so their question is unanswered rather "
              f"than answered clean; exit stays 0 because a leg that could not run "
              f"is a fact about this machine, not about the repository")
        print(records)
        return 0 if records_ok else 1
    if not records_ok:
        print(records)
        print()
        print(f"  VERDICT: FAIL - all {len(subs)} sub-checks confirm and this check "
              f"still leaves no records on disk, so there is nothing to read back")
        return 1
    return 0


def report_verdicts(verdicts, expectations, results_file, inputs=None, counts=None):
    """The same service for the two checks that keep flat name -> bool verdicts.

    chk_liquidation_field and chk_maker_attribution do not build the sub-check
    contract; they hold a mapping of verdict name to True/False and a separate block
    of counts. Both used to fail with one line naming no verdict at all. This turns
    the mapping into the same three-part evidence: `expectations` supplies the words
    for what each verdict asserts, and `counts` the numbers behind it.

    Returns 1 when any verdict is False, and 1 when `results_file` is not on disk
    whatever the verdicts said; the reasoning for the second is in _records.
    """
    failed = [k for k, v in verdicts.items()
              if v is False or (isinstance(v, str) and v.startswith("FAIL"))]
    records, records_ok = _records(results_file)
    if not failed:
        if records_ok:
            return 0
        print("-" * 78)
        print(records)
        print()
        print(f"  VERDICT: FAIL - all {len(verdicts)} verdicts hold and this check "
              f"still leaves no records on disk, so there is nothing to read back")
        return 1
    print("-" * 78)
    unexplained = ("no expectation is recorded for this verdict; add one to the "
                   "EXPECTATIONS map beside it, because a failing verdict whose "
                   "assertion is unwritten cannot be acted on")
    for name in failed:
        print()
        print(f"  MISMATCH: {name}")
        print(f"      expected  : "
              f"{_wrap(expectations.get(name, unexplained), 66, ' ' * 18)}")
        print(f"      found     : {verdicts[name]}")
    if counts:
        print()
        print("  the numbers the verdicts were taken from:")
        for key, value in _leaves(counts):
            print(f"      {key} = {_fmt(value)}")
    for label, value in (inputs or {}).items():
        shown = _place(value)
        print(f"      read {label} = {shown}")
    print()
    print(f"  VERDICT: FAIL - {len(failed)} of {len(verdicts)} verdicts failed: "
          f"{', '.join(failed)}")
    print(records)
    return 1


def mismatch_text(name, expected, found, place, means=None):
    """The same three parts as text, for a failure that aborts before any contract.

    An assert or a raise fires before the results file is built, so neither reporter
    above can serve it and a traceback is all the reader gets. This builds the same
    headings in the same order, so a hard stop reads like every other failure in
    this directory rather than like a bare inequality between two numbers whose file
    is never named. Fourteen of these messages carried a number and no place.

    One caveat, learned rather than reasoned: a caller raising KeyError must PRINT
    this and then raise something short. KeyError is the one builtin whose str() is
    the repr of its argument, so a multi-line message inside it reaches the screen
    as a single line with the newlines spelled out.
    """
    lines = [f"\n  MISMATCH: {name}",
             f"      expected  : {_wrap(expected, 66, ' ' * 18)}",
             f"      found     : {_wrap(found, 66, ' ' * 18)}",
             f"      place     : {_wrap(place, 66, ' ' * 18)}"]
    if means:
        lines.append(f"      means     : {_wrap(means, 66, ' ' * 18)}")
    return "\n".join(lines)


def notebook_cells(rel):
    """Code cells of a notebook as (label, source), ready to tokenise.

    The cell is the unit. Cells share one namespace, so a top-level assignment in a
    cell is a module-level declaration, and "cell 4, line 12" is what a reader can
    navigate to. Notebook source is JSON-escaped on disk, which is why a textual count
    over the file could only ever be an estimate: unpacking the cells is what makes the
    same tokeniser the scripts get apply to the notebook as well.

    Magic and shell lines (%matplotlib, !pip) are not Python and would abort the
    tokenise, so they are commented out in place: the line and its number survive and
    nothing else in the cell is lost to one unparsable line.

    `rel` is relative to the repository root, which is this directory's parent -- the
    same root the two checks that used to hold a copy of this each computed for
    themselves.
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        with open(os.path.join(root, rel), encoding="utf-8", errors="replace") as fh:
            nb = json.load(fh)
    except (OSError, ValueError):
        return []
    out = []
    for i, cell in enumerate(nb.get("cells", [])):
        if cell.get("cell_type") != "code":
            continue
        src = "".join(cell.get("source", []))
        lines = [("#" + ln if ln.lstrip()[:1] in ("%", "!") else ln)
                 for ln in src.split("\n")]
        out.append((f"{rel}#cell{i}", "\n".join(lines)))
    return out


# ----------------------------------------------------------------------------------
# THE TWO SHAPES OF SELF-TEST BOOKKEEPING
#
# Eight scripts in this tree define a nested function called `expect`, and the obvious
# reading -- one helper copied eight times -- is wrong. Resolved by content rather than
# by name, they are three different functions:
#
#   expect(pairs)                  three copies, tallies a COUNT and collects reasons
#   expect(label, holds, detail)   two copies, PRINTS each assertion as it is made
#   three further spellings        one copy each, not consolidated here
#
# Counting call sites by name gives 152 across the tree and says nothing, because it
# pools three unrelated signatures. Resolved by address the five consolidated here own
# 111 of those calls, and not one of the 111 changes: `Tally.expect` is bound to the
# same local name with the same signature, and `make_expect` returns a closure with the
# same signature. Two of the five were already being passed as an argument into sibling
# functions, so those callers already treated the closure as a value.
# ----------------------------------------------------------------------------------

class Tally:
    """The running count of assertions made, and the reasons the failing ones gave.

    Counting as each assertion is made, rather than typing a total beside them, is the
    point. The count in this module used to be the hand-typed sum 8 + 1 + 1 + 4 against
    the literal 14. A number set by hand beside the thing it counts is the same defect
    this repository already met in its plan counters, and adding one assertion without
    editing two other places would have printed a lie about how much was proved.

    A caller binds the method to a plain local name and its own call sites do not know
    an object is involved:

        tally = Tally()
        expect = tally.expect
    """

    def __init__(self):
        self.asserted = 0
        self.failures = []

    def expect(self, pairs):
        """Record `pairs` of (holds, why); keep the reason of every one that does not."""
        self.asserted += len(pairs)
        for holds, why in pairs:
            if not holds:
                self.failures.append(why)


def make_expect(asserted, failures):
    """An `expect(label, holds, detail)` that prints each assertion as it is made.

    Takes the caller's two lists rather than owning them, because the callers of this
    shape hand the returned function on to sibling routines and then read their own
    lists afterwards. `asserted` collects the label of every assertion made; `failures`
    collects a record for each one that did not hold.
    """

    def expect(label, holds, detail=""):
        asserted.append(label)
        print(f"    [{'ok  ' if holds else 'FAIL'}] {label}"
              + (f"  {detail}" if detail else ""))
        if not holds:
            failures.append({"assertion": label, "detail": detail})

    return expect


def _site(site, indent):
    """One finding as a place: file and line first, then why it was flagged."""
    if not isinstance(site, dict):
        return str(site)
    where = f"{site.get('file', '?')}:{site.get('line', '-')}"
    detail = site.get("detail") or site.get("name") or site.get("rule") or ""
    detail = str(detail)
    if len(detail) > 88:
        detail = detail[:85] + "..."
    text = where if not detail else f"{where}  {detail}"
    source = site.get("source")
    if source:
        text += f"\n{indent}| {str(source)[:110]}"
    return text


def report_gate(rules, results_file, inputs=None, sites_shown=20):
    """Print expectation, fact and place for every counted rule that went over.

    The third shape. A gate does not test an assumption about the market, it counts
    findings in the repository and compares the count to a ceiling it declares --
    zero for a rule nobody is allowed to break, a frozen debt figure for a rule with
    a backlog. So the EXPECTATION is the ceiling together with the sentence saying
    what the rule is for, the FACT is the count and how far over it went, and the
    PLACE is the file and line of each finding, which the gates already collect and
    which is the whole reason a reader can act on the failure at all.

    Each rule is a dict:

        name        the rule as the gate names it on screen
        assumption  what the rule is for, in words
        method      how the finding was recognised, so a reader can repeat it
        permitted   findings tolerated; None means UNARMED and can never fail
        found       findings counted
        sites       the findings, each {"file", "line", "detail", "source"}
        note        what going over means

    Returns 1 when any armed rule found more than it permits, 0 otherwise. A rule
    whose `permitted` is None reports its count and never fails: arming it is a
    decision somebody makes, and this module does not make it for them.

    It also returns 1 when `results_file` is not on disk, whatever the rules found. A
    gate that counts every rule under its ceiling and leaves no record behind has not
    reported; the reasoning is in _records, and this parameter went three weeks being
    printed and never read.
    """
    over = [r for r in rules
            if r.get("permitted") is not None and r["found"] > r["permitted"]]
    records, records_ok = _records(results_file)
    if not over:
        if records_ok:
            return 0
        print("-" * 78)
        print(records)
        print()
        print(f"  VERDICT: FAIL - all {len(rules)} rules are at or under their "
              f"ceiling and this gate still leaves no records on disk, so there is "
              f"nothing to read back")
        return 1

    unwritten =("no expectation is recorded for this rule; write one beside it, "
                 "because a gate that goes red without saying what it protects "
                 "cannot be acted on")
    print("-" * 78)
    for rule in over:
        permitted, found = rule["permitted"], rule["found"]
        print()
        print(f"  REGRESSED: {rule['name']}")
        print(f"      expected  : at most {permitted} finding"
              f"{'' if permitted == 1 else 's'}. "
              f"{_wrap(rule.get('assumption') or unwritten, 66, ' ' * 18)}")
        if rule.get("method"):
            print(f"      measured  : {_wrap(rule['method'], 66, ' ' * 18)}")
        print(f"      found     : {found}, which is {found - permitted} more than "
              f"this gate permits")
        sites = list(rule.get("sites") or ())
        if sites:
            print("      place     :")
            for site in sites[:sites_shown]:
                print(f"                  {_site(site, ' ' * 18)}")
            if len(sites) > sites_shown:
                print(f"                  ... and {len(sites) - sites_shown} more, "
                      f"all of them in {os.path.basename(results_file)}")
        else:
            # A count with no sites is still actionable, but only from the file.
            print(f"      place     : {os.path.basename(results_file)}, the findings "
                  f"list for this rule")
        if rule.get("note"):
            print(f"      means     : {_wrap(rule['note'], 66, ' ' * 18)}")

    for label, value in (inputs or {}).items():
        shown = _place(value)
        print(f"      read {label} = {shown}")
    print()
    print(f"  VERDICT: FAIL - {len(over)} of {len(rules)} rules found more than "
          f"they permit: {', '.join(r['name'] for r in over)}")
    print(records)
    return 1


def _self_test():
    """Prove the reporter fires, and prove it prints all three parts.

    Written because this module's whole claim is about what happens on a mismatch,
    and a reporter nobody has ever seen fire is exactly the thing it was built to
    stop. It is run rather than asserted: the output is captured and searched for
    the expectation, the fact and the place, and a clean contract is run alongside
    to show the reporter stays silent and returns 0 when nothing is wrong.
    """
    import contextlib
    import io as _io
    import shutil
    import tempfile

    tally = Tally()
    _expect = tally.expect

    # A RESULTS FILE THAT IS REALLY THERE, AND ONE THAT IS REALLY NOT. Every reporter
    # below now checks the pointer it prints, so the fixture has to supply a file on
    # disk rather than a name: a self-test run against names that exist nowhere would
    # measure the new check instead of the reporting it is here to prove. The present
    # one is written into a temporary directory the operating system hands out, so it
    # never enters the tree and no other script reads it.
    tmp = tempfile.mkdtemp(prefix="evidence_selftest_")
    PRESENT = os.path.join(tmp, "some_results.json")
    with open(PRESENT, "w", encoding="utf-8") as fh:
        fh.write('{"verdict": "PASS"}\n')
    ABSENT = os.path.join(tmp, "never_written_results.json")
    EMPTY = os.path.join(tmp, "empty_results.json")
    with open(EMPTY, "w", encoding="utf-8") as fh:
        fh.write("")

    def _run(fn, *args, **kwargs):
        buf = _io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = fn(*args, **kwargs)
        return code, buf.getvalue()

    refuted = {"checks": [
        {"name": "clean_leg", "assumption": "A", "method": "m", "observed": {"x": 1},
         "verdict": "confirmed", "note": "n"},
        {"name": "close_fills_reduce_inventory",
         "assumption": "Close Long implies start_pos > 0",
         "method": "fraction of Close Long rows with start_pos > 0",
         "observed": {"close_long_frac_positive": 0.02, "threshold": 0.7,
                      "nested": {"deep": [1, 2, 3]}},
         "verdict": "refuted", "note": "a sign flip in start_pos"},
    ], "overall_verdict": "refuted"}
    code, out = _run(report_contract, refuted, PRESENT,
                     inputs={"npz": os.path.join(os.sep, "somewhere", "tmp",
                                                 "quickwin_markouts.npz")})
    _expect((
        (code == 1, "a refuted contract must exit non-zero"),
        ("MISMATCH" in out, "the mismatch must be announced"),
        ("Close Long implies start_pos > 0" in out, "the EXPECTATION must print"),
        ("close_long_frac_positive = 0.02" in out, "the FACT must print"),
        ("checks[1]" in out, "the PLACE must print"),
        ("quickwin_markouts.npz" in out, "the input read must print"),
        ("clean_leg" not in out, "a confirmed leg must not be printed"),
        ("nested.deep = [1, 2, 3]" in out, "a nested observed leaf must print")))

    clean = {"checks": [{"name": "a", "verdict": "confirmed"}],
             "overall_verdict": "confirmed"}
    code, out = _run(report_contract, clean, PRESENT)
    _expect(((code == 0 and not out.strip(),
              "a confirmed contract must exit 0 and print nothing here"),))

    unknown = {"checks": [{"name": "raw_leg", "assumption": "the tape re-walk runs",
                           "observed": {"rewalk": "unavailable"},
                           "verdict": "uncertain", "note": "S3 unreachable"}],
               "overall_verdict": "uncertain"}
    code, out = _run(report_contract, unknown, PRESENT)
    _expect(((code == 0 and "NOT ANSWERED" in out,
              "an unanswered leg must be printed loudly and still exit 0"),))

    code, out = _run(report_verdicts,
                     {"object_exists": True, "method_is_market": False},
                     {"method_is_market": "every liquidation is method=market"},
                     PRESENT, counts={"n_legs": 7})
    _expect((
        (code == 1, "a false verdict must exit non-zero"),
        ("every liquidation is method=market" in out,
         "the expectation of a flat verdict must print"),
        ("n_legs = 7" in out, "the counts behind a flat verdict must print"),
        ("object_exists" not in out.split("VERDICT")[0],
         "a passing verdict must not be printed as a mismatch")))

    # A verdict that went false with nothing written about what it asserts must say
    # so on the screen rather than print an empty expectation, because a blank line
    # there reads as "no expectation was violated".
    code, out = _run(report_verdicts, {"undocumented": False}, {}, PRESENT)
    _expect(((code == 1 and "no expectation is recorded" in out,
              "an undocumented failing verdict must name its own gap"),))

    # THE THIRD SHAPE. One rule over its ceiling, one at its ceiling, one unarmed.
    gate_rules = [
        {"name": "ABS-HOME-PATH", "permitted": 0, "found": 2,
         "assumption": "no tracked text file names a home directory",
         "method": "regex over every git-tracked text file",
         "note": "the path does not exist for anyone who clones this",
         # The fixture source line deliberately does NOT spell a real home path:
         # this file is itself scanned by chk_no_abs_paths, and a test fixture that
         # trips the gate it is modelling would make the suite red about itself.
         "sites": [{"file": "checks/a.py", "line": 12, "detail": "hard-coded input",
                    "source": "PATH = <a home directory, spelled out>"},
                   {"file": "notebooks/b.ipynb", "line": 4, "detail": "cell 3"}]},
        {"name": "AT-BASELINE", "permitted": 18, "found": 18,
         "assumption": "the frozen horizon-literal debt does not grow"},
        {"name": "UNARMED", "permitted": None, "found": 9,
         "assumption": "reported only until somebody freezes a figure"},
    ]
    code, out = _run(report_gate, gate_rules, PRESENT,
                     inputs={"tree": "git ls-files"})
    _expect((
        (code == 1, "a rule over its ceiling must exit non-zero"),
        ("at most 0 findings" in out, "the CEILING must print as the expectation"),
        ("no tracked text file names a home directory" in out,
         "the words of the rule must print beside the ceiling"),
        ("found     : 2, which is 2 more" in out,
         "the FACT must print as the count and the distance over"),
        ("checks/a.py:12" in out, "the PLACE must print as file and line"),
        ("PATH = <a home directory, spelled out>" in out,
         "the offending source line must print"),
        ("AT-BASELINE" not in out, "a rule sitting at its ceiling must not print"),
        ("UNARMED" not in out, "a rule with no ceiling can never fail the run")))

    code, out = _run(report_gate, gate_rules[1:], PRESENT)
    _expect(((code == 0 and not out.strip(),
              "a gate with nothing over its ceiling must exit 0 and stay silent"),))

    # THE POINTER IS A CLAIM ABOUT THE DISK, SO IT IS CALIBRATED ON TWO OPPOSITE CASES.
    # One reference point cannot tell a check that is too wide from one too narrow: a
    # predicate that always fires and one that never fires both look right against a
    # single case. These two differ in one thing, whether the named file is there.
    #
    # MUST STAY SILENT: the gate reports over a results file that exists. This is the
    # live shape of eighteen of the nineteen callers, which write it through
    # artifact.py before they report.
    code, out = _run(report_gate, gate_rules, PRESENT)
    _expect((
        (code == 1, "a real regression must still exit 1 when the records are there"),
        ("full records -> some_results.json" in out,
         "a results file that IS on disk must print as the plain pointer"),
        ("no such file" not in out,
         "a results file that is on disk must not be reported as missing")))

    # MUST FIRE: the same gate, the same rules, over a file nobody wrote. This is the
    # shape the frame-column check had before 2026-08-05, and the reason the parameter
    # was worth checking at all.
    code, out = _run(report_gate, gate_rules, ABSENT)
    _expect((
        (code == 1, "a missing results file must exit non-zero"),
        ("no such file" in out, "the FACT must say the file is not there"),
        ("never_written_results.json" in out, "the PLACE must name the file"),
        ("MISMATCH" in out,
         "absent records must read as a finding, in the same shape as every other")))

    # AND THE SAME WHEN THE GATE FOUND NOTHING. A green verdict over absent records is
    # the dangerous direction: it is the run that says the rules hold and leaves no
    # way to check that claim. It used to exit 0 in silence.
    code, out = _run(report_gate, gate_rules[1:], ABSENT)
    _expect((
        (code == 1, "a green gate with no records on disk must exit non-zero"),
        ("no such file" in out,
         "a green gate with no records must say so rather than stay silent")))

    # A FILE THAT EXISTS AND HOLDS NOTHING IS THE SAME BROKEN PROMISE. An interrupted
    # write leaves the name in place, and existence alone would read it as evidence.
    code, out = _run(report_gate, gate_rules[1:], EMPTY)
    _expect(((code == 1 and "holds no bytes" in out,
              "an empty results file must be reported, not counted as records"),))

    # THE OTHER TWO REPORTERS ANSWER THE SAME WAY, because a rule fixed in one place of
    # three is the shape of defect this repository has already met.
    code, out = _run(report_contract, clean, ABSENT)
    _expect(((code == 1 and "no such file" in out,
              "a confirmed contract with no records on disk must exit non-zero"),))
    code, out = _run(report_verdicts, {"object_exists": True}, {}, ABSENT)
    _expect(((code == 1 and "no such file" in out,
              "passing verdicts with no records on disk must exit non-zero"),))

    # A BARE NAME RESOLVES AGAINST THE CALLER, NOT THE WORKING DIRECTORY. Three of the
    # gates pass the bare name, so the resolution is what decides whether the check
    # above measures the disk or the shell it was launched from. Asserted against the
    # live tree: a committed results file of this directory, and a name that is not.
    live = "chk_no_abs_paths_results.json"
    _expect((
        (os.path.dirname(_records_path(live)) == os.path.dirname(os.path.abspath(__file__)),
         "a bare results name must resolve beside the caller"),
        (_records(live)[1] is os.path.isfile(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), live)),
         "a bare name must be judged by the file it resolves to"),
        (_records("no_such_gate_results.json")[1] is False,
         "a bare name that resolves to nothing must be reported missing")))

    # THE PLACE MUST SURVIVE BEING PRINTED. Shortening every input that held a
    # separator turned an S3 key into "23.lz4" and an archive URL into "content",
    # which is the line whose whole job is to say where, saying nothing.
    code, out = _run(report_verdicts, {"v": False}, {"v": "x"}, PRESENT,
                     inputs={"s3_key": "s3://a-bucket/hourly/20251204/23.lz4",
                             "url": "https://zenodo.org/records/18184441/files/x",
                             "day_hour": "20251204/23",
                             "rel": "checks/chk_thing.py",
                             "local": os.path.join(os.sep, "somewhere", "home",
                                                   "quickwin_markouts.npz")})
    _expect((
        ("s3://a-bucket/hourly/20251204/23.lz4" in out,
         "an S3 key must print whole, not as its last segment"),
        ("https://zenodo.org/records/18184441/files/x" in out,
         "a URL must print whole"),
        ("day_hour = 20251204/23" in out,
         "a value that merely contains a slash must not be cut to its tail"),
        ("rel = checks/chk_thing.py" in out,
         "a repo-relative path must print whole: it names no machine"),
        ("local = quickwin_markouts.npz" in out,
         "a LOCAL ABSOLUTE path must still be cut to its basename"),
        (os.sep + "somewhere" not in out,
         "no absolute local path may reach the screen")))

    # THE POPULATION REFUSAL, ON TWO OPPOSITE CASES. A fresh Git checkout with an
    # empty index must refuse with a non-zero code; the same checkout with one file
    # staged must answer with that file and stay silent.
    repo = os.path.join(tmp, "fresh_checkout")
    os.makedirs(repo)
    have_git = subprocess.run(["git", "-C", repo, "init", "-q"],
                              capture_output=True, check=False).returncode == 0
    if have_git:
        with open(os.path.join(repo, "a.py"), "w", encoding="utf-8") as fh:
            fh.write("x = 1\n")
        refused, err = None, _io.StringIO()
        with contextlib.redirect_stderr(err):
            try:
                shipped_tree_files(repo)
            except EmptyPopulation as exc:
                refused = exc.code
        subprocess.run(["git", "-C", repo, "add", "a.py"],
                       capture_output=True, check=False)
        staged = shipped_tree_files(repo)
        _expect((
            (refused == 2, "an empty index must refuse with exit code 2"),
            ("EMPTY" in err.getvalue(), "the refusal must print its reason"),
            (staged == ["a.py"], "a staged file must be the population, silently"),))
    else:
        _expect(((False, "git is not available, so the population refusal on a "
                         "checkout could not be exercised"),))

    shutil.rmtree(tmp, ignore_errors=True)

    print("=" * 78)
    print("  evidence.py self-test")
    print("=" * 78)
    for why in tally.failures:
        print(f"  FAIL  {why}")
    print(f"  {'PASS' if not tally.failures else 'FAIL'}: "
          f"{tally.asserted - len(tally.failures)} of {tally.asserted} assertions hold")
    return 1 if tally.failures else 0


if __name__ == "__main__":
    import sys
    sys.exit(_self_test())
