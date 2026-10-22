#!/usr/bin/env python3
"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-07-30
References: none (test harness over the checks in this directory).

ONE RUNNER THAT RUNS THE INTEGRITY CHECKS REQUESTED AND SAYS WHICH FAILED.

Why this exists. The repository had thirteen checks and no way to run them together.
`run_verify_s3.sh` runs three of them, the three that need a fresh walk of the raw
tape, and it is a night job. The other ten were run by hand, one at a time, which
means in practice they were run when someone remembered. Two entries of the project
checklist said "add this check to the common run" while no common run existed.

There is a second reason, and it is the one that matters to a reader of the paper.
A newcomer should be able to clone the repository, run it, and get the same
numbers. A newcomer cannot do that by reading thirteen file headers. They run this.

How it is organised. Checks are grouped by WHAT THEY NEED, because a gate nobody can
run is not a gate, and a gate that fails for a reason outside the repository teaches
people to ignore it.

  LOCAL    reads only files shipped in a clean clone or extracted source ZIP. Seconds.
           This is the group that runs before every commit, and it runs with the
           network unplugged.
  DATA     reads the ignored derived per-fill intermediate
           `quickwin_markouts.npz`. Seconds once that 47 MB file has been built, but
           a clean clone does not carry it. Opt-in with --data.
  NETWORK  fetches a small object from a free public archive at run time, so it can
           fail for reasons that say nothing about the clone. Opt-in with --network.
           This grouping was learned rather than designed: its member sat in the
           local group at first, and came back non-zero on a range request to Zenodo
           that returned an empty body, while passing on its own a minute earlier. A
           newcomer offline would have read that as a broken repo. Nothing here costs
           money: a check that can call the requester-pays S3 archive belongs in TAPE.
  TAPE     reads the raw node-fills tape, from a local cache when CAP_RAW_CACHE holds
           the hours it needs and otherwise from the requester-pays S3 archive, which
           bills the caller and needs S3 credentials. Opt-in with --tape. The three
           re-walks are the commands `run_verify_s3.sh` has always run; the one-hour
           liquidation check joined them on 2026-10-21 because, without a cached hour,
           it fetches that hour from the same archive.
  LAST     runs after every group that was selected, because it hashes the results
           files of the checks around it. One member today: chk_input_freshness.

THE ORDER OF THE PLAN IS ITSELF A RULE, and it was learned rather than designed.
chk_input_freshness reads the artifacts of this tree to ask whether each still stands on
the inputs it recorded, and it then records all 99 of them as its own inputs -- 22 being
results files of checks in this battery. Listed ninth, as it was until 2026-08-12, it
hashed eight later checks' results files and they were rewritten behind it in the same
run. The measurement: a battery straight after the notebook was edited returned two
findings, both on this gate's own results file; a second battery, with nothing edited in
between, returned 17 of 17 and exit zero. A verdict that is wrong on the first look and
right on the second is a verdict about the order and not about the tree.

It is the same class as a check repeating the logic it guards -- blind to the change it
exists to notice -- along the axis of time rather than of content. So the rule has an
address in code: order_faults reads each check's own results file for what it declared
hashing, and refuses to run a plan in which any check precedes a results file it has
already hashed. `--selftest` calibrates that rule on two opposite cases from the live
tables.

The rule cannot be satisfied everywhere, and that is stated rather than discovered.
chk_artifact_provenance declares this gate's results file and this gate declares that
one, so no linear order puts both first. That pair is excused by name inside
chk_input_freshness with its reason, and the excuse is read from there by import rather
than copied here.

Reading the result. A check that exits zero passed. PASS_AT_BASELINE means the check
found known debt, recorded in that check's own baseline, and no regression on top of
it; the baseline is a number that may only ever be lowered. A non-zero exit is a
regression and this runner exits non-zero with it.

    uv run --no-project --with-requirements requirements.txt python3 checks/run_all_checks.py
    uv run --no-project --with-requirements requirements.txt python3 checks/run_all_checks.py --data
    uv run --no-project --with-requirements requirements.txt python3 checks/run_all_checks.py --network
    uv run --no-project --with-requirements requirements.txt python3 checks/run_all_checks.py --tape
    uv run --no-project --with-requirements requirements.txt python3 checks/run_all_checks.py --only settings_home
    uv run --no-project --with-requirements requirements.txt python3 checks/run_all_checks.py --selftest
"""
import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
import artifact                                                              # noqa: E402
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from evidence import mismatch_text                                           # noqa: E402

OUT_JSON = os.path.join(HERE, "run_all_checks_results.json")

# name -> (script, what it enforces in one line). Fastest first, so a broken tree
# shows its first failure early rather than after everything else.
LOCAL = [
    ("abs_paths", "chk_no_abs_paths.py",
     "no absolute home path in any tracked text file"),
    ("academic_header", "chk_academic_header.py",
     "every tracked script and notebook opens by naming the study, its author and "
     "its date"),
    ("settings_home", "chk_settings_home.py",
     "one home per setting; no key collision; no stale fingerprint"),
    ("artifact_provenance", "chk_artifact_provenance.py",
     "every results file names its producer, inputs, runtime, scope and settings, "
     "and still matches the code that wrote it"),
    # ADDED 2026-08-21, AND IT IS THE OTHER HALF OF THE QUESTION ABOVE. The provenance
    # check compares a recorded producer hash with the script on disk and reports the
    # two apart. That comparison presumes both ends exist. When a node runs on code
    # that is edited and then replaced before it is ever saved, the recorded hash names
    # bytes that exist nowhere, one end of the distance is missing, and no diff can be
    # read. Four artifacts of 2026-08-11 stood that way for ten days and no gate here
    # could see it, because every gate that looks at a producer hash looks at the
    # DIFFERENCE and none asked whether the far end was there to differ from.
    ("producer_committed", "chk_producer_committed.py",
     "every results file records a producer hash that names bytes this repository "
     "still holds, so the freshness comparison has two ends and a disagreement can "
     "be read as a diff instead of being unanswerable"),
    # ADDED 2026-08-28, AND IT IS THE THIRD LEG OF THE SAME QUESTION. The two above ask
    # whether the CODE that produced an artifact is the code on disk. Neither asks
    # whether the ENVIRONMENT it ran in is the one this repository declares, and
    # artifact.py had been stamping the library versions of every run into
    # _meta.run.packages since 2026-07-30 with nothing in this tree ever reading one
    # back. Written and never read is worth what unwritten is worth: ten artifacts had
    # been computed under numpy 2.5.1 against the pin numpy==2.4.6 for weeks, and every
    # gate in this battery was green over them. It costs under a second and reads only
    # shipped files, so it belongs in LOCAL beside the other two.
    ("pinned_versions", "chk_pinned_versions.py",
     "every artifact was computed under a library version requirements.txt pins, so a "
     "reader who follows the run command gets the numbers the report carries. "
     "Violations are counted against a declared debt that names each file, and a "
     "violation in a file the declaration does not name fails whatever the total says"),
    ("headline_horizon", "chk_headline_horizon.py",
     "the scoring window is declared, never spelled"),
    ("expensive_edits", "chk_expensive_edits.py",
     "no expensive producer carries an edit that changes no computed figure, because "
     "such an edit costs its whole runtime and buys nothing"),
    # ADDED 2026-08-14, AND THE REASON IS ABOUT THIS RUNNER RATHER THAN ABOUT THE BUILD.
    # build.py invoked with no arguments runs its own self-test: 73 assertions about the
    # graph every recompute decision is taken from -- one producer per artifact, no
    # cycle, every file operation accounted for, the skip rule skipping and the run rule
    # running. It belonged to no group here, so nothing ran it, and it had been exiting 1
    # for days while this runner printed 17 of 17 and exit zero.
    #
    # Both statements were true and together they misled. While a program that exits
    # non-zero sits outside the run that reports the health of the tree, "no failures"
    # means "none among the ones we look at" and reads as "none at all", which is the
    # direction of error that travels. It reads only shipped files and starts its
    # children with sys.executable, so it belongs in LOCAL: no network, no ignored
    # intermediate. It costs about eight seconds, most of it the self-test itself.
    ("build_selftest", "chk_build_selftest.py",
     "the build's own self-test passes: the graph it derives from the syntax of every "
     "script still holds one producer per artifact, no cycle and every file operation "
     "accounted for. Failing assertions are counted against a ceiling that is a "
     "declared debt and may only be lowered"),
    # ADDED 2026-08-30, AND IT IS THE SAME HOLE AS THE ONE ABOVE, IN A SECOND PLACE. The
    # counts inside requirements.txt -- how many .py files ship, which of them import
    # each pinned distribution, how many entry points there are -- are written by
    # build_requirements_census.py from the syntax tree of every shipped file, and that
    # program run with no arguments reports what moved and exits non-zero. It belonged to
    # no group here either, so nothing ran it, and on 2026-08-30 the block had fallen
    # behind the tree in five places while this runner printed zero failures beside it. A
    # hand-typed count does not go wrong, it goes stale, and it does so silently. It
    # reads only shipped files and starts its children with sys.executable, so it belongs
    # in LOCAL. It costs about five seconds, most of it the four censuses it runs: one on
    # the tree and three on a copy of it, which are its calibration.
    ("requirements_census", "chk_requirements_census.py",
     "the census inside requirements.txt still agrees with the tree it describes, read "
     "twice: once through the census's own comparison and once by reading the counts "
     "straight out of the block and asking the tree for the same ones. A finding that "
     "differs in nothing but the date the census stamps as it renders reports the "
     "calendar rather than the tree, and is counted apart"),
    ("prose_numbers", "chk_prose_numbers.py",
     "every figure the register declares equals the artifact leaf at the address the "
     "register itself writes down, and the check measures its own blindness. The "
     "register belongs to the write-up and is not shipped here, so with none named "
     "(--registry PATH or PROSE_REGISTRY) the check records that it compared nothing "
     "and exits 0"),
    ("run_happened", "chk_run_happened.py",
     "before a comparison of numbers is allowed to mean anything, the run that "
     "produced them is shown to have happened: a finish time later than the launch "
     "and a producer hash equal to the file on disk. Run here with no reference "
     "moment, so only the hash leg is judged; pass --since after a recompute to ask "
     "the other one"),
    # The two above ask whether the CODE moved, and both do it by comparing an
    # artifact against its producer's hash. Neither asks whether the INPUT moved, and
    # 65 of the 81 nodes of the build graph are pure readers of another node's output,
    # so the whole lower layer is invisible to them by construction. That third leg of
    # the same question is chk_input_freshness, and it is NOT listed here: see LAST,
    # below, for why it has to run after everything else in the plan.
    # The three above and the register sweep all ask whether it is the same NUMBER.
    # None asks whether the two things a published difference is a difference OF are
    # comparable, and on 2026-08-03 a headline contrast passed all four while its arms
    # differed fourfold in quote width along an axis the prose never named. It sits
    # here because it is the next question about the same figures.
    # Added 2026-08-06. The reproduction notebook is the first thing a reader opens,
    # and until that day it fetched the figures it checks itself against from the
    # public archive at run time. The deposited copy was four weeks old, every value
    # in it belonged to a scoring window this study had left, and a reader following
    # the README got four checks of twenty-five and a failed assertion. The figures
    # now travel inside the notebook, which is what this gate watches.
    ("notebook_expectations", "chk_notebook_expectations.py",
     "the figures written into the reproduction notebook are the figures its file of "
     "figures holds, and no cell fetches them from anywhere else"),
    # The one above asks whether the notebook's figures are the reported ones. It says
    # nothing about the notebook's own account of what it does NOT recompute, and that
    # account is a table of prose no gate could read. It was written on 2026-08-06; four
    # days later three commits inside twenty-seven minutes taught the notebook to rebuild
    # three of the things it lists, and the table went on saying they were out of reach.
    # It sits here because it reads the same notebook and asks the next question of it.
    ("notebook_pointer_table", "chk_notebook_pointer_table.py",
     "the table of figures the reproduction notebook says it cannot rebuild names none "
     "that it does rebuild, and every row of it points at a script and an address a "
     "reader can open"),
    ("contrast_hygiene", "chk_contrast_hygiene.py",
     "the arms of every published difference differ only along the axis their "
     "declaration names, and every measurement declared to be held equal between them "
     "actually is"),
    ("join_nolookahead", "chk_join_nolookahead.py",
     "no join reaches forward in time"),
    # The one above asks whether a PRICE is read from after the moment it is read for,
    # and it asks it of seven hand-built fixtures with no input at all. The one below
    # asks the same question of the DECISION layer, over the source of every tracked
    # module that cuts the window into halves: which counterparties get scored, where
    # the cutoff sits, and what the score is compared with. A causal join does not make
    # a causal rule, and until 2026-08-05 nothing here asked the second question.
    ("decision_lookahead", "chk_decision_lookahead.py",
     "no decision is taken with data from after it: the population, the cutoff and the "
     "constant a score is compared with all come from the early half"),
    ("dir_vs_startpos", "chk_dir_vs_startpos.py",
     "trade direction agrees with the pre-trade position"),
    ("book_orientation", "chk_book_orientation.py",
     "the order book is the right way up"),
]

# Fast, but not self-contained. quickwin_markouts.npz is a 47 MB derived per-fill
# intermediate deliberately excluded by *.npz in .gitignore. Keeping this check in
# LOCAL made the advertised clean-clone command fail for absence of a file the clone
# cannot contain. --data states the dependency at the command boundary instead.
DATA = [
    ("closedpnl", "chk_closedpnl.py",
     "realized profit agrees with the exchange's own field "
     "(reads the ignored quickwin_markouts.npz intermediate)"),
]

# Small live fetches from free public hosts. Quick, but they depend on a remote host
# being reachable and willing, so a failure here is not evidence about the repository
# until it repeats.
NETWORK = [
    ("maker_attribution", "chk_maker_attribution.py",
     "a fill is attributed to the maker that filled it "
     "(fetches a byte range from Zenodo)"),
]

# These read the raw tape: from CAP_RAW_CACHE when it holds the hours, otherwise from
# the requester-pays S3 archive, which needs credentials and bills the caller.
TAPE = [
    ("liquidation_field", "chk_liquidation_field.py",
     "the liquidation marker is where the data log says it is "
     "(one hourly object, from CAP_RAW_CACHE or else from requester-pays S3)"),
    ("field_hygiene", "chk_field_hygiene.py",
     "no silent drop, no non-positive size, no missing maker in the raw walk"),
    ("rowcounts_determinism", "chk_rowcounts_determinism.py",
     "re-parsing a day reproduces the stored slice"),
    ("side_signconv", "chk_side_signconv.py",
     "the markout sign convention holds against a re-derivation"),
]
# RUNS AFTER EVERYTHING ELSE, and that is a property of what it reads rather than a
# preference about tidiness.
#
# WHY, measured on 2026-08-12. chk_input_freshness asks whether every artifact still
# stands on the version of each input it recorded reading, and to ask it, it reads
# artifacts -- including the results files of the other checks. It then records all 99
# of them as its OWN declared inputs, 22 of which are results files written by members
# of this battery. So every check that runs AFTER it rewrites a file it has just
# hashed, and its own record is stale before the battery finishes.
#
# The measurement that showed it: a run straight after the notebook was edited reported
# two findings, both of them on this gate's own results file, naming
# chk_notebook_expectations_results.json and chk_notebook_pointer_table_results.json --
# the two checks listed after it. A second run, with nothing edited in between, came
# back 17 of 17 and exit zero. A verdict that is wrong on the first look and right on
# the second is not a verdict about the tree; it is a verdict about the order.
#
# THE ORDER CANNOT BE MADE PERFECT, and that is worth writing down rather than
# discovering later. chk_artifact_provenance declares this gate's results file as an
# input, and this gate declares that one, so the two of them cannot both come first.
# That pair is already excused by name inside chk_input_freshness, with its reason, and
# order_faults below reads that excuse from the gate itself rather than repeating it.
LAST = [
    ("input_freshness", "chk_input_freshness.py",
     "every artifact still stands on the version of each input it recorded reading, "
     "which neither freshness gate above can see: both compare an artifact against "
     "its producer's hash and so ask only whether the code changed. Runs last, because "
     "it hashes the results files of the checks around it"),
]

ALL_GROUPS = LOCAL + DATA + NETWORK + TAPE + LAST


# A check that could not ask its question is neither a pass nor a failure, and the
# word for that has to survive the trip from the check to this screen. These are the
# words the checks in this directory use for it.
UNANSWERED_WORDS = ("UNCERTAIN", "uncertain", "INCONCLUSIVE", "inconclusive")

# A check that was told by design not to ask its question in this checkout, and says so
# in its own word. Counted apart from both the passes and the unanswered: a skip is a
# declared absence of an input the repository does not ship, not a leg that failed to
# run, and it must never be added to the number that passed.
SKIPPED_WORDS = ("SKIPPED_NO_REGISTRY",)


def verdict_file(script, name):
    """The results file a check writes, or None.

    Two spellings exist in this directory and both are deliberate, so both are tried
    rather than one being assumed: twenty-one checks write `<script stem>_results.json`
    and `chk_join_nolookahead.py` writes `join_nolookahead_results.json`, which its own
    header at line 55 explains and pins with an assertion.
    """
    for candidate in (script[:-3] + "_results.json", name + "_results.json"):
        path = os.path.join(HERE, candidate)
        if os.path.isfile(path):
            return path
    return None


def read_results_document(path):
    """(the JSON a results file holds, when it was last written), or (None, None).

    THE ONE PLACE THIS DIRECTORY IS OPENED FOR READING, and it is one place on purpose.
    Three functions here asked the same thing of the same files -- what inputs did this
    check hash, what verdict did it record this run, what verdict does it record at all
    -- and each opened the file itself. Three opens for one question is the shape this
    repository has paid for elsewhere, and here it also showed up as arithmetic: every
    one of them stands in the build's residue of unaccounted file operations, so that
    debt was counting how many times this file repeats itself rather than anything
    about the tree.

    The modification time comes back with the document because the two questions are
    asked together everywhere: what the file says, and whether it is about this run.
    Reading it here rather than at each call site is also the only way the two cannot
    drift apart between the stat and the open.
    """
    if path is None or not os.path.isfile(path):
        return None, None
    when = os.path.getmtime(path)
    try:
        with open(path, encoding="utf-8") as handle:
            doc = json.load(handle)
    except (OSError, ValueError):
        return None, when
    return (doc if isinstance(doc, dict) else None), when


def verdict_word(doc):
    """The verdict a results document records, under any of its three spellings.

    Kept beside the reader rather than in each caller, for the reason the three
    spellings exist at all: the tree wrote this field three ways before the convention
    settled, and a caller that knows only one of them silently reports no verdict for
    the files using the other two.
    """
    if not isinstance(doc, dict):
        return None
    for key in ("overall_verdict", "verdict", "overall"):
        value = doc.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def declared_inputs(script, name):
    """Basenames the check's own results file records as its inputs, or None.

    Read out of the artifact rather than out of the check's source: what a run actually
    hashed is a fact the run wrote down, and a list retyped here would go stale against
    the very thing it describes.
    """
    doc, _when = read_results_document(verdict_file(script, name))
    if doc is None:
        return None
    inputs = (doc.get("_meta") or {}).get("inputs")
    if not isinstance(inputs, list):
        return None
    return {os.path.basename(item.get("name") or "") for item in inputs
            if isinstance(item, dict)}


def excused_artifacts():
    """Artifacts allowed to stand on a moved input, read from the gate that says so.

    CALLED, not copied. chk_input_freshness owns this list with its reasons written
    beside it, and this project has already had two instruments answer one question
    differently because the second kept its own copy of the exceptions.
    """
    try:
        import chk_input_freshness                                     # noqa: PLC0415
    except Exception:                                        # pragma: no cover
        return set(), "the freshness gate could not be imported, so no excuse is read"
    names = getattr(chk_input_freshness, "DECLARED_DIVERGED_ARTIFACTS", ())
    return {os.path.basename(n) for n in names}, None


def order_faults(plan, excused):
    """Checks that run before a check whose results file they have already hashed.

    The rule, and it is about time rather than content: a check which records another
    check's results file among its own inputs is describing a file the battery is about
    to rewrite, so its record is stale before the run ends. That is the same class as a
    gate repeating the logic it guards -- blind to the very change it exists to notice --
    only along the other axis.

    Returns (faults, pairs excused). An excused pair is not silence: it is printed, so
    that the part of this rule the tree cannot satisfy stays visible. chk_artifact_
    provenance and chk_input_freshness each declare the other's results file, so no
    linear order satisfies both; that pair is excused by name inside the freshness gate,
    with its reason, and the excuse is read from there.
    """
    faults, allowed = [], []
    written = [(i, name, script[:-3] + "_results.json", name + "_results.json")
               for i, (name, script, _what) in enumerate(plan)]
    for i, (name, script, _what) in enumerate(plan):
        inputs = declared_inputs(script, name)
        if not inputs:
            continue
        own = os.path.basename(verdict_file(script, name) or "")
        for j, later, cand_a, cand_b in written:
            if j <= i:
                continue
            hit = cand_a if cand_a in inputs else (cand_b if cand_b in inputs else None)
            if hit is None:
                continue
            row = {"earlier": name, "later": later, "file": hit, "declarer_file": own}
            (allowed if own in excused else faults).append(row)
    return faults, allowed


def calibrate_order(excused):
    """Two opposite cases for the order rule, both built from the live tables.

    One reference case cannot tell a predicate that is too wide from one that is too
    narrow apart. The silent case is the plan as it stands; the firing case is that same
    plan with the freshness gate put back where it sat until 2026-08-12, which is a
    state this repository was actually in rather than an invented one.

    Nothing here is hand-typed: the position it used to hold is found by looking for the
    check it used to sit behind, so a later edit to the tables moves the fixture with
    them instead of leaving it testing a shape nobody has.
    """
    plan = list(LOCAL) + list(DATA) + list(NETWORK) + list(TAPE) + list(LAST)
    faults, allowed = order_faults(plan, excused)
    print("=" * 78)
    print("  THE ORDER OF THE PLAN, CALIBRATED")
    print("=" * 78)
    if faults:
        print(f"  MUST STAY SILENT and did not: the plan as it stands reports "
              f"{len(faults)} fault(s), the first being {faults[0]['earlier']} before "
              f"{faults[0]['later']}")
        return 2
    if not allowed:
        print("  the silent case is vacuous: no pair at all was examined, so silence "
              "says nothing about a plan that has one")
        return 2

    names = [name for name, _s, _w in plan]
    if "run_happened" not in names or "input_freshness" not in names:
        print("  the firing case cannot be built: the plan no longer holds the two "
              "checks the old order was written between")
        return 2
    wrong = [row for row in plan if row[0] != "input_freshness"]
    wrong.insert(names.index("run_happened") + 1,
                 next(row for row in plan if row[0] == "input_freshness"))
    hurt, _allowed = order_faults(wrong, excused)
    if not hurt:
        print("  MUST FIRE and did not: the freshness gate put back ahead of the checks "
              "whose results files it hashes is reported clean, so this rule cannot see "
              "the order it exists to guard")
        return 2

    print(f"  silent : the plan as it stands, {len(plan)} checks, 0 fault(s) over "
          f"{len(allowed)} pair(s) examined and excused by name")
    for row in allowed[:3]:
        print(f"           {row['earlier']} -> {row['later']} ({row['file']}), excused "
              f"because {row['declarer_file']} is declared as allowed to stand on a "
              f"moved input")
    print(f"  fires  : the same plan with input_freshness back where it sat until "
          f"2026-08-12 reports {len(hurt)} fault(s):")
    for row in hurt[:8]:
        print(f"           {row['earlier']} runs before {row['later']} and has already "
              f"hashed {row['file']}")
    print(f"  excuses read from       : chk_input_freshness."
          f"DECLARED_DIVERGED_ARTIFACTS, {len(excused)} name(s), by import rather than "
          f"by a copy kept here")
    print()
    print("  VERDICT: PASS - the order rule fires on the order this battery had and "
          "stays silent on the order it has")
    return 0


# The slack on the freshness comparison below. A check started and finished inside the
# same second as this runner's clock reading would otherwise be judged to have written
# nothing, so the comparison is loosened by one second in the direction that costs
# nothing: the worst it can do is accept a file written one second too early, and the
# only files in this directory are ones this battery writes.
FRESH_SLACK_S = 1


def wrote_its_results_file(path, started):
    """Whether the check rewrote its own results file during THIS run.

    THE PREDICATE THE ADVICE AT THE BOTTOM OF THIS FILE STANDS ON, named here so that
    it has one home and can be calibrated. Until 2026-08-29 the runner asked this
    question only to decide where to read a verdict from, and then printed advice that
    assumed the answer was always yes: a check that could not answer its question was
    described as having a results file that "says which leg could not run and why". A
    check that cannot answer usually does not write at all, and the file sitting at
    that name is then the record of some earlier run -- three of them in this directory
    carry `overall_verdict: confirmed` from runs of other days. A reader following that
    advice reads a confirmation about a question nobody put, which is an error pointing
    at success and therefore the kind that travels.

    Calibrated on two opposite cases by _selftest_advice_predicate(), which runs
    on every invocation of this runner rather than behind a flag.
    """
    if path is None or not os.path.isfile(path):
        return False
    return os.path.getmtime(path) >= started - FRESH_SLACK_S


def standing_verdict(path):
    """(the verdict word a results file holds, when it was last written), or (None, None).

    Read off the file as it stands, with no freshness test at all. That is the point:
    this is what a reader sent to that file would find there, and naming it beside the
    date is the only way to show that the word is about another run.
    """
    doc, when = read_results_document(path)
    if when is None:
        return None, None
    stamp = datetime.datetime.fromtimestamp(
        when, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return verdict_word(doc), stamp


def _selftest_advice_predicate():
    """Two opposite cases for wrote_its_results_file. Returns a list of failures.

    One reference point cannot tell a predicate that is too wide from one that is too
    narrow, so both arms are built: a file written after the reference moment, which
    the predicate MUST accept, and the same file backdated well before it, which it
    MUST refuse. The two differ in the modification time and in nothing else -- the
    same bytes, the same path -- so the arms measure the comparison and not the file.

    A third arm covers the shape that produced the wrong advice in the first place: a
    name at which no file exists at all must come back false rather than raise.
    """
    failures = []
    work = tempfile.mkdtemp(prefix="run_all_checks_calibration_")
    try:
        path = os.path.join(work, "a_calibration_fixture_results.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"overall_verdict": "confirmed"}, handle)
        started = time.time()

        os.utime(path, (started + 5, started + 5))
        if not wrote_its_results_file(path, started):
            failures.append(
                "MUST FIRE: a results file written after the run began is not seen as "
                "written by this run, so every check would be reported off a stale file")

        os.utime(path, (started - 3600, started - 3600))
        if wrote_its_results_file(path, started):
            failures.append(
                "MUST STAY SILENT: a results file an hour older than this run is "
                "accepted as written by it, which is the defect this predicate exists "
                "to catch")

        word, when = standing_verdict(path)
        if word != "confirmed" or not when:
            failures.append(
                f"the standing verdict of a file this run did not write reads "
                f"{word!r} at {when!r}, expected 'confirmed' with a date; the advice "
                f"cannot name what a reader would find there")

        if wrote_its_results_file(os.path.join(work, "no_such_calibration_results.json"), started):
            failures.append(
                "MUST STAY SILENT: a name at which no file exists is reported as "
                "written by this run")
        if wrote_its_results_file(None, started):
            failures.append(
                "MUST STAY SILENT: a check that writes no results file at all is "
                "reported as having written one")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return failures


def verdict_from_file(script, name, started):
    """What the check itself recorded this run, or None if it did not record.

    WHY THIS READS THE FILE AND NOT THE SCREEN, which is the whole point of it. The
    previous version scraped the check's console output for one of six upper-case
    words and, finding none, invented "ok" whenever the exit code was zero. Measured
    on 2026-08-10 in a clean clone: four checks recorded `uncertain` in their own
    results files, three of those four were printed on this screen as "ok", and the
    run closed with VERDICT: PASS. A check that could not ask its question was
    reported in the same word as a check that asked it and got the right answer, and
    the error pointed at success, which is the direction that travels.

    A verdict is only accepted from a file this run wrote. Without that test a check
    that died before writing would be reported with the verdict of the run before it,
    which is the same defect one level further along: a word about a tree nobody
    looked at.
    """
    path = verdict_file(script, name)
    if not wrote_its_results_file(path, started):
        return None
    doc, _when = read_results_document(path)
    return verdict_word(doc)


def scrape_verdict(tail):
    """The check's verdict as printed, for the one check that records none.

    Kept as the fallback rather than deleted, because not every check writes a file
    this runner can read, and a fallback that goes silent is worse than one that reads
    the screen. The worse word is tried first within each family, and the longer
    before the shorter, because PASS is a substring of PASS_AT_BASELINE. The
    unanswered words are tried BEFORE the passing ones: a check can print UNCERTAIN in
    its summary and PASS on an individual leg above it, and reading that as a pass is
    the defect this whole function once had.
    """
    for word in UNANSWERED_WORDS + SKIPPED_WORDS:
        if f"VERDICT: {word}" in tail or f"overall={word}" in tail:
            return word
    for word in ("PASS_AT_BASELINE", "BASELINE_UNSET", "ALL_PASS", "CONFIRMED",
                 "PASS", "FAIL"):
        if word in tail:
            return word
    for word in ("refuted", "uncertain", "confirmed"):
        if f"overall={word}" in tail or f'"overall_verdict": "{word}"' in tail:
            return word
    return ""


def run_one(script, name, timeout_s):
    """Run one check and return (exit code, verdict word, seconds, output tail).

    The output tail is kept and written into the results file. An earlier version of
    this runner discarded it, and the first time a check came back non-zero there was
    nothing to diagnose: the check passed on its own and passed again under the same
    invocation, so the failure left no evidence at all. A runner that reports a
    failure without keeping the reason turns a real regression into a rumour.

    THE CHILD RUNS UNDER THE PINNED ENVIRONMENT, THE SAME ONE THE PARENT RUNS UNDER.
    Until 2026-08-21 the line below read `--with numpy`, and that short form does not
    honour requirements.txt: it resolves numpy freshly on the day it runs and installs
    nothing else at all. The measurement is recorded in build.py -- it returned numpy
    2.5.2 against the 2.4.6 this repository pins, and no matplotlib whatsoever. So this
    runner honoured the pin for itself, since the docstring at the top tells a reader
    to invoke it with --with-requirements, and broke it for every child it started.

    Four check results files recorded numpy 2.5.2 because of this while five recorded
    2.4.6, and which number a file carried depended on nothing but whether it had last
    been run by hand or by this runner. That is the worst shape a difference can take:
    the same check under two libraries, with the environment recorded faithfully in
    both artifacts and no reason visible in either for why they disagree.

    The path is relative and cwd is set explicitly just below, which is the convention
    the script argument already follows and which keeps a machine's own directory
    layout out of anything this runner writes down.
    """
    started = time.time()
    try:
        proc = subprocess.run(
            ["uv", "run", "--no-project", "--with-requirements", "requirements.txt",
             "python3", os.path.join("checks", script)],
            cwd=ROOT, capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired as exc:
        return 124, "TIMEOUT", time.time() - started, str(exc)[:2000]
    tail = (proc.stdout or "") + (proc.stderr or "")
    verdict = verdict_from_file(script, name, started) or scrape_verdict(tail)
    verdict = verdict or ("ok" if proc.returncode == 0 else "nonzero")
    rewrote = wrote_its_results_file(verdict_file(script, name), started)
    # THE TAIL IS KEPT FOR A CHECK THAT ANSWERED NOTHING, and not only for one that
    # failed. Added 2026-08-29 with the advice at the bottom of this file. A check
    # that could not put its question exits zero and usually writes no results file,
    # and this runner captures the child's output rather than letting it reach the
    # screen -- so before today the reason such a check gave existed in no file, on no
    # screen, and in this record either. The advice sent the reader to a results file
    # from another run because there was nowhere honest left to send them.
    keep = proc.returncode != 0 or verdict in UNANSWERED_WORDS
    return (proc.returncode, verdict,
            time.time() - started,
            tail[-4000:] if keep else "",
            rewrote)


def main():
    started = artifact.start_clock()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[6])
    ap.add_argument("--data", action="store_true",
                    help="also run the check that reads ignored quickwin_markouts.npz")
    ap.add_argument("--network", action="store_true",
                    help="also run the checks that fetch a small object from a free "
                         "public host")
    ap.add_argument("--tape", action="store_true",
                    help="also run the checks that read the raw tape, from "
                         "CAP_RAW_CACHE or else from requester-pays S3")
    ap.add_argument("--only", metavar="NAME",
                    help="run one check by its name from the table above")
    ap.add_argument("--timeout", type=int, default=1800,
                    help="per-check timeout in seconds (default 1800)")
    ap.add_argument("--selftest", action="store_true",
                    help="calibrate the rule that orders the plan, and exit")
    args = ap.parse_args()

    plan = list(LOCAL)
    if args.data:
        plan += list(DATA)
    if args.network or args.tape:
        plan += list(NETWORK)
    if args.tape:
        plan += list(TAPE)
    # Appended after every group that was selected, not merely after LOCAL. Placing it
    # at the end of one list would have left it stale again the moment --data or --tape
    # put another artifact-writing check behind it, which is the same defect with a
    # longer fuse.
    plan += list(LAST)
    if args.only:
        plan = [row for row in plan if row[0] == args.only] or \
               [row for row in ALL_GROUPS if row[0] == args.only]
        if not plan:
            # This exits non-zero, so it owes the same three parts as any other
            # failure here. It used to print one line naming no expectation and no
            # place, which reads like a usage hint rather than like the run having
            # been abandoned without a single check executed.
            print(mismatch_text(
                "--only names no check in this directory",
                f"one of the {len(ALL_GROUPS)} names in the table at the top of "
                f"this file: " + ", ".join(n for n, _s, _d in ALL_GROUPS),
                f"--only {args.only!r}, which matches none of them",
                "run_all_checks.py, the LOCAL, NETWORK and TAPE tables",
                "nothing ran. This exit is about the command line, not about the "
                "repository, and no check was executed either way"))
            return 2

    # THE ADVICE PREDICATE IS CALIBRATED ON EVERY INVOCATION, not behind --selftest.
    # The rule it guards is printed at the very bottom of a long run, which is exactly
    # where a wrong sentence goes unread; and the whole reason it was wrong is that
    # nobody had ever asked the predicate underneath it to demonstrate both answers.
    # It costs two files in a scratch directory and no check is started before it.
    advice_faults = _selftest_advice_predicate()
    if advice_faults:
        print(mismatch_text(
            "the predicate behind the advice for a check that answered nothing is not "
            "calibrated",
            "wrote_its_results_file accepts a file written during this run and refuses "
            "one written before it",
            f"{len(advice_faults)} of its calibration arms do not hold:\n      "
            + "\n      ".join(advice_faults),
            "run_all_checks.py, _selftest_advice_predicate",
            "nothing ran. Until the predicate holds, any advice this runner prints "
            "about where to read a verdict is unfounded"))
        return 2

    excused, excuse_note = excused_artifacts()
    faults, allowed = order_faults(plan, excused)
    if args.selftest:
        return calibrate_order(excused)

    print("=" * 78)
    print("  ALL INTEGRITY CHECKS")
    print("=" * 78)
    print(f"  order of the plan        : {len(faults)} check(s) run before a results "
          f"file they have already hashed, {len(allowed)} pair(s) excused by name"
          + (f"  ({excuse_note})" if excuse_note else ""))
    # THE RESIDUAL, NAMED. This runner writes its own results file after the last check,
    # so any check that hashes run_all_checks_results.json necessarily read the copy the
    # PREVIOUS run left. No ordering fixes that: the runner cannot write its record
    # before the checks it records. The excuse exists inside chk_input_freshness for
    # exactly this file; the two gates below have no such excuse, so a run that follows
    # an edit to this file reports them and the run after it comes back clean. Printed
    # rather than left to be rediscovered, because a fault nobody names is a fault
    # somebody spends a morning on.
    own = os.path.basename(OUT_JSON)
    readers = [name for name, script, _what in plan
               if (declared_inputs(script, name) or set()) & {own}]
    if readers:
        print(f"  ...and one it cannot fix : {own} is written after the last check, so "
              f"{', '.join(readers)} read the copy the previous run left"
              + ("" if own in excused else
                 ". None of them excuses that file, so a battery run straight after "
                 "this runner is edited reports it and the next one does not"))
    if faults:
        # Refused BEFORE anything runs. A battery executed in an order that is known to
        # stale its own record spends its whole runtime to produce a verdict about the
        # order rather than about the tree, and the first look would disagree with the
        # second for a reason no reader could see.
        print(mismatch_text(
            "every check runs before the checks whose results files it hashes",
            "0 checks running ahead of a results file they declare as an input",
            f"{len(faults)}: "
            + "; ".join(f"{f['earlier']} runs before {f['later']} and has hashed "
                        f"{f['file']}" for f in faults[:6])
            + ("" if len(faults) <= 6 else f" and {len(faults) - 6} more"),
            "run_all_checks.py, the LOCAL/DATA/NETWORK/TAPE tables and LAST",
            "nothing ran. Move the check named first in each pair after the ones it "
            "hashes, or declare the pair inside the gate that excuses such an artifact"))
        return 2
    if not args.only:
        omitted = []
        if not args.data:
            omitted.append("--data for the one ignored-intermediate check")
        if not (args.network or args.tape):
            omitted.append(f"--network for the {len(NETWORK)} free live fetch(es)")
        if not args.tape:
            omitted.append(f"--tape for the {len(TAPE)} raw-tape check(s), which can "
                           f"call requester-pays S3")
        print(f"  running {len(plan)} of {len(ALL_GROUPS)} checks"
              + ("; add " + ", ".join(omitted) if omitted else ""))
    rows, failed, unanswered, skipped = [], [], [], []
    for name, script, what in plan:
        if not os.path.exists(os.path.join(HERE, script)):
            rows.append({"name": name, "script": script, "verdict": "MISSING",
                         "exit": 127, "seconds": 0.0, "enforces": what,
                         "results_file_rewritten_by_this_run": False})
            failed.append(name)
            print(f"  {name:22} MISSING     {script}")
            continue
        code, verdict, secs, tail, rewrote = run_one(script, name, args.timeout)
        row = {"name": name, "script": script, "verdict": verdict,
               "exit": code, "seconds": round(secs, 1), "enforces": what,
               # Recorded per check rather than derived later, because the question is
               # about a moment that has passed by the time this file is written.
               "results_file_rewritten_by_this_run": rewrote}
        if tail:
            row["output_tail"] = tail
        rows.append(row)
        if code != 0:
            failed.append(name)
        elif verdict in UNANSWERED_WORDS:
            unanswered.append(name)
        elif verdict in SKIPPED_WORDS:
            skipped.append(name)
        print(f"  {name:22} {verdict:17} exit={code}  {secs:6.1f}s   {what}")

    # Three states, not two. A check that could not ask its question has not passed,
    # and calling the run PASS while one did not answer is a claim about a tree nobody
    # looked at. It is not a failure either: in a clean clone the reason is usually
    # that this repository deliberately does not ship a 47 MB derived intermediate, so
    # the fact is about the checkout rather than about the code, and a red run would
    # teach a newcomer to ignore the gates. The exit code therefore still tracks
    # failure alone, and the word on the screen tells the difference.
    if failed:
        headline = "FAIL"
    elif unanswered:
        headline = "PASS_WITH_UNANSWERED"
    elif skipped:
        headline = "PASS_WITH_SKIPPED"
    else:
        headline = "PASS"
    results = {
        "verdict": headline,
        "failed": failed,
        "unanswered": unanswered,
        "skipped": skipped,
        "n_passed": len(rows) - len(failed) - len(unanswered) - len(skipped),
        "checks": rows,
    }
    # The checks this run actually executed are its inputs, hashed one by one: a
    # runner that says PASS is saying it about particular files, and the hash is what
    # ties the word to them. The plan, not the table, because --only and the two
    # opt-in groups mean the run covers less than the table lists.
    plan_names = {name for name, _script, _what in plan}
    data_names = {name for name, _script, _what in DATA}
    network_names = {name for name, _script, _what in NETWORK}
    tape_names = {name for name, _script, _what in TAPE}
    included_groups = ["local"]
    if plan_names & data_names:
        included_groups.append("derived data")
    if plan_names & network_names:
        included_groups.append("live fetches")
    if plan_names & tape_names:
        included_groups.append("raw-tape walks")
    artifact.write(
        os.path.basename(OUT_JSON), results,
        script=__file__,
        inputs=[os.path.join(HERE, script) for _n, script, _w in plan],
        scope={
            "population": f"{len(rows)} of the {len(ALL_GROUPS)} checks in this "
                          f"directory: " + ", ".join(r["name"] for r in rows),
            "window": "n/a: this runner starts other programs and reads no market "
                      "data of its own; each check states its own window",
            "coins": "n/a: this runner reads no market data of its own",
        },
        started=started,
        extra_meta={
            "data_included": bool(plan_names & data_names),
            "network_included": bool(plan_names & network_names),
            "tape_included": bool(plan_names & tape_names),
            "n_checks_run": len(rows),
            "groups_run": " plus ".join(included_groups),
        },
    )

    # THE EVIDENCE, ON THE SCREEN, NOT ONLY IN THE FILE. run_one has always kept the
    # failing check's output; until now it went into the JSON and nowhere else, so a
    # red run printed a name and an exit code and the reader had to run the check
    # again by hand to learn the cause. That is the same defect the checks themselves
    # had, one level up: the runner knew the reason and did not say it. Each failing
    # check has already printed its own expectation, fact and place, so replaying its
    # tail here is enough -- this runner does not need to know what any check tests.
    for row in rows:
        if row["exit"] == 0:
            continue
        print()
        print("-" * 78)
        if row["verdict"] == "MISSING":
            why = "  (the script is not in this directory at all)"
        elif not row.get("output_tail"):
            why = "  (no output captured; the check died before printing)"
        else:
            why = ""
        # The same three headings the checks themselves print, taken from the same
        # module rather than retyped here, so a red run reads one way whether the
        # failure was found by a check or by this runner one level up.
        print(mismatch_text(
            f"{row['name']} exited non-zero, verdict {row['verdict']}",
            f"exit 0 from checks/{row['script']}, which enforces that "
            f"{row['enforces']}",
            f"exit {row['exit']} after {row['seconds']}s{why}",
            f"checks/{row['script']}, and the run record under checks[] in "
            f"{os.path.basename(OUT_JSON)}"))
        tail = row.get("output_tail", "")
        if tail:
            print(f"      the check said, last {len(tail.splitlines())} lines of its "
                  f"own output:")
            for line in tail.splitlines():
                print(f"      | {line}")

    print("-" * 78)
    print(f"  ran {len(rows)}, passed {results['n_passed']}, failed {len(failed)}"
          + (f": {', '.join(failed)}" if failed else ""))
    if skipped:
        print(f"  skipped {len(skipped)}, not counted as passed: {', '.join(skipped)}")
        for name in skipped:
            row = next(r for r in rows if r["name"] == name)
            print(f"       {name}: verdict {row['verdict']}; the reason is in its own "
                  f"results file and output")
    if unanswered:
        # Named on the screen rather than left to the file, because the whole defect
        # this replaced was a fact that existed in the files and not where it was read.
        #
        # AND THE ADVICE IS NOW PER CHECK, BECAUSE THE ONE SENTENCE THAT USED TO STAND
        # HERE WAS FALSE FOR EXACTLY THE CHECKS IT ADDRESSED. It read "its own results
        # file says which leg could not run and why". A check that could not put its
        # question generally does not rewrite its results file -- measured by hashing
        # three of them before and after such a run, all three unmoved -- and the file
        # left at that name then holds a verdict from some earlier run, `confirmed` in
        # all three cases. So the reader was sent to a confirmation about a question
        # nobody had put. The distinction is asked of wrote_its_results_file(), which
        # is one predicate with one home and a calibrated pair, and where the answer is
        # no the standing verdict and its date are printed so the word can be seen to
        # belong to another run.
        print(f"  did NOT answer {len(unanswered)}: {', '.join(unanswered)}")
        print("     each of these ran and reached no verdict, usually because a clean "
              "clone does not carry")
        print("     what it reads. Where to look, per check:")
        for name in unanswered:
            row = next(r for r in rows if r["name"] == name)
            path = verdict_file(row["script"], name)
            shown = os.path.basename(path) if path else None
            if row.get("results_file_rewritten_by_this_run"):
                print(f"       {name}: this run rewrote {shown}, so that file says "
                      f"which leg could not run and why")
                continue
            standing, when = standing_verdict(path)
            if shown is None:
                print(f"       {name}: this check writes no results file, so the only "
                      f"record of this run is the output kept under checks[] in "
                      f"{os.path.basename(OUT_JSON)}")
            else:
                print(f"       {name}: this run did NOT rewrite {shown}. That file is "
                      f"from a run of {when}")
                if standing:
                    print(f"         and it reads overall_verdict={standing!r}, which "
                          f"is a word about THAT run and is not evidence about this "
                          f"one")
            print(f"         what this run actually saw is the check's own output, "
                  f"kept under checks[] in {os.path.basename(OUT_JSON)}; to get an "
                  f"answer, run checks/{row['script']} where its inputs are present")
    print(f"  VERDICT: {results['verdict']}")
    print(f"  results -> {os.path.basename(OUT_JSON)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
