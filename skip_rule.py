#!/usr/bin/env python3
"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-07-31
References: none (repository infrastructure; it declares no quantity of its own and
reads only the records artifact.py writes into every results file).

WHETHER A NODE HAS TO RUN IS A THREE-ANSWER QUESTION, AND THE THIRD ANSWER IS WHY
THIS MODULE EXISTS SEPARATELY FROM THE BUILD.

The build next door owns the graph: which script makes which artifact, and in what
order. This module owns the one decision the graph exists to serve -- would this
node's result come out the same, so that running it again buys nothing. There are
three honest answers to that and not two:

    up_to_date   every condition was PUT, and every one HELD
    must_run     a condition was put and FAILED, and the record names what moved
    unknown      a condition could not be put at all, so the question has no answer

The third is not a shade of either of the others, and folding it either way is a
mistake with a measured cost here. Folded into the first, a tree reads as verified
when nothing about it was ever checked. Folded into the second, hours of raw-tape
work are re-run to answer a question nobody put.

BOTH FOLDS WERE IN THE TREE ON 31 JULY 2026, and this is the measurement rather than
the argument.

The first fold: of fifteen raw-tape nodes, two -- i3_book_comparator.py under
--stage feats, and i4_l2_mid.py -- came back up_to_date with ZERO conditions asked
of them. Their outputs are .npz files, which carry no _meta block, so no producer
hash and no input hash was ever recorded for either; the only thing the old rule
looked at was whether the markout ladder had a column, and a file that carries no
markout column at all answers that vacuously. "Provably up to date" was being
printed about two nodes nothing had been asked about.

The second fold: across the eighty tracked results files, 183 input records are
recorded and 24 of them carry no hash. The old rule met each of those 24 with a bare
`continue` -- neither compared, nor counted, nor mentioned. Ten of the 24 are the
whole input list of ks2_persistence_10day_results.json, whose inputs are ten day
locators into the public archive; that node's skip decision therefore rested on
nothing at all, and said so nowhere.

WHAT THE CONDITIONS ARE, AND WHAT THEY ARE NOT. A condition here is one comparison
between something an artifact RECORDED about its own computation and the same thing
as it stands now:

    producer_bytes   the sha256 the artifact recorded for its producer, against the
                     bytes of that script on disk
    input_bytes      the sha256 the artifact recorded for one input, against the
                     bytes of that file on disk
    settings         one settings-owned field the artifact stamped, against what
                     settings.py declares now
    marking_ladder   for a raw-tape node, whether the markout file carries a column
                     for every rung the ladder asks for
    output_present   whether the artifact is in the tree at all

No condition consults a file DATE, and that is measured rather than assumed: on 30
July a results file was observed four minutes NEWER than its own producer and
computed under the previous setting, because a long run that began before the edit
ended after it. A date answers "when was this written" and never "what was it
computed with".

WHAT THIS MODULE REUSES, AND WHY IT IS AN IMPORT AND NOT A COPY. The producer-bytes
condition is the same question checks/chk_artifact_provenance.py asks in freshness()
and checks/chk_run_happened.py asks as its second leg, and both of those already go
through checks/run_record.py. So this module calls run_record.judge() with no
reference moment -- which is exactly "ask leg two and do not ask leg one" -- instead
of hashing a producer for a third time. Two implementations of one predicate is how
two honest censuses of these very artifacts once returned 24 and 32 for a single
property, and the three-state vocabulary below is deliberately the same shape as
run_record's ran / did_not_run / unanswerable so that a reader moving between them
is reading one idea.

WHAT THIS MODULE DOES NOT DO, and the boundary is the point of it. It opens no file,
hashes nothing and walks no directory. Every fact it judges is handed to it: the
caller passes the artifact's own _meta records, and two callables that resolve a name
to a path and a path to a digest. That keeps the tree in the build, where the index
and the hash cache live, and keeps the rule here where it can be exercised against
fabricated records in a temporary directory -- which is the only place a skip rule
can be PROVEN to skip, because proving it on the real tree costs a full recompute.

ONE THING IT DELIBERATELY DOES NOT KNOW ABOUT. checks/NEUTRAL_EDITS.json certifies
that a particular pair of producer hashes cannot have moved a figure, and
chk_artifact_provenance.py reports that as a fifth outcome beside stale. This module
does not read it: a certificate says the NUMBERS did not move, which is a different
claim from "the computation would come out the same", and a build that skipped on a
certificate would leave the artifact permanently disagreeing with its producer. The
cost of that choice is stated so it can be argued with: a certified-neutral edit
still schedules its node here.

    from skip_rule import producer_condition, input_condition, verdict, split

Self-test, since this repository has no separate test directory:

    uv run --no-project python3 skip_rule.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
_CHECKS_DIR = os.path.join(HERE, "checks")
if _CHECKS_DIR not in sys.path:
    sys.path.insert(0, _CHECKS_DIR)
import run_record as R                                              # noqa: E402

# The three answers. The spellings are the ones build.py has always printed and
# written into its own record, so that adding the third answer properly does not
# rename the two that were already right.
UP_TO_DATE = "up_to_date"
MUST_RUN = "must_run"
UNKNOWN = "unknown"
STATES = (UP_TO_DATE, MUST_RUN, UNKNOWN)

# WHY a question could not be put. Kept as named causes rather than as free text,
# because the plan groups by them: "twelve nodes cannot be told because their input
# is the raw tape" is a fact a reader can act on, and twelve differently-worded
# sentences are not.
NO_RECORD_AT_ALL = "no_record_at_all"      # the file format carries no _meta block
NO_HASH_RECORDED = "no_hash_recorded"      # a record exists and holds no sha256
INPUT_ABSENT = "input_absent"              # a hash was recorded, the file is gone
NOT_RESOLVABLE = "not_resolvable"          # the name stands for none or many files
RAW_TAPE_GONE = "raw_tape_gone"            # deleted by the parser, by design
CAUSES = (NO_RECORD_AT_ALL, NO_HASH_RECORDED, INPUT_ABSENT, NOT_RESOLVABLE,
          RAW_TAPE_GONE)


# =====================================================================
# 1. ONE CONDITION, IN THREE SHAPES
#
# Every condition carries the same fields whatever its answer, so that a caller
# printing a failure never has to go and look up what was expected or where. That is
# the shape checks/evidence.py prints and checks/run_record.py records, and it is the
# one this project adopted after a gate exited non-zero with the single line "one or
# more verdicts FAILED".
# =====================================================================

def _condition(name, output, asked, answered, holds, why, cause=None, detail=None):
    record = {"condition": name, "output": output, "asked": asked,
              "answered": answered, "holds": holds, "why": why}
    if cause:
        record["cause"] = cause
    if detail is not None:
        record["detail"] = detail
    return record


def held(name, output, why, detail=None):
    """The condition was put and it holds."""
    return _condition(name, output, True, True, True, why, detail=detail)


def failed(name, output, why, detail=None):
    """The condition was put and it does not hold: this is what moved."""
    return _condition(name, output, True, True, False, why, detail=detail)


def unanswerable(name, output, why, cause, detail=None):
    """The condition could not be put. Never a pass and never a failure."""
    if cause not in CAUSES:
        raise ValueError(
            f"{cause!r} is not one of the causes this module names ({CAUSES}). A "
            "cause is what the plan groups by, so an unnamed one would print as a "
            "row of its own and read as a new kind of gap")
    return _condition(name, output, True, False, None, why, cause=cause,
                      detail=detail)


# =====================================================================
# 2. THE THREE CONDITIONS THAT READ AN ARTIFACT'S OWN RECORD
# =====================================================================

def producer_condition(rel, root, output, scripts=None):
    """Whether the bytes that wrote this artifact are the bytes on disk now.

    Delegated to checks/run_record.py with no reference moment, which is that
    module's way of saying "ask the producer-hash leg and do not ask whether a run
    happened". Everything this function does beyond the call is translating one
    vocabulary into the other, so there is exactly one place in the repository that
    knows how a producer hash is compared.
    """
    record = R.judge(rel, root, scripts, reference=None)
    leg = record["legs"].get("producer_hash_matches_disk") or {}
    if not leg:
        # judge() could not get as far as the leg: the extension carries no _meta
        # block, or the document would not read as an artifact.
        return unanswerable(
            "producer_bytes", output,
            " ".join(record["why"]) or "no producer record could be read",
            NO_RECORD_AT_ALL, {"place": record["place"]})
    if not leg.get("answered"):
        # run_record says "the tree holds no file / more than one file BY THAT NAME"
        # when the producer basename does not resolve, and says something else when
        # no hash was recorded at all. The two are different gaps and the plan groups
        # by them, so they are told apart on the phrase run_record itself writes.
        cause = (NOT_RESOLVABLE if "by that name" in (leg.get("why") or "")
                 else NO_HASH_RECORDED)
        return unanswerable("producer_bytes", output, leg.get("why") or "",
                            cause, {"place": record["place"]})
    detail = {"producer": leg.get("producer"),
              "recorded": leg.get("recorded_sha256"),
              "on_disk": leg.get("on_disk_sha256")}
    if leg.get("holds"):
        return held("producer_bytes", output,
                    f"the artifact records {leg.get('producer')} at "
                    f"{leg.get('recorded_sha256')} and that is the file on disk",
                    detail)
    return failed("producer_bytes", output,
                  "the script has changed since this file was written", detail)


def input_condition(record, output, locate, digest):
    """One recorded input, compared against the file on disk. Three answers.

    `record` is one entry of the artifact's own _meta.inputs list. `locate` maps a
    recorded name to a single path or None; `digest` maps a path to its sha256. Both
    are handed in so that this module touches no file.

    THE `continue` THIS REPLACES. The old rule read `if not record.get("sha256"):
    continue`, which passed silently over every input that had no hash -- 24 of the
    183 input records in this tree, ten of them the entire input list of one raw-tape
    artifact. Passing over a condition is not the same as putting it and finding it
    holds, and the difference is the whole of the third answer.
    """
    name = record.get("name") if isinstance(record, dict) else None
    if not name:
        return unanswerable(
            "input_bytes", output,
            "an input record carries no name, so there is nothing to look up",
            NO_RECORD_AT_ALL, {"record": record})
    recorded = record.get("sha256")
    if not recorded:
        external = "://" in name
        return unanswerable(
            "input_bytes", output,
            f"the artifact records the input {name} with no hash -- "
            + ("it is a locator into the public archive rather than a file of this "
               "tree" if external else
               "it was recorded present=false, meaning the file was already gone "
               "when the artifact was written")
            + " -- so whether that input has since changed cannot be asked",
            RAW_TAPE_GONE if external else NO_HASH_RECORDED, {"input": name})
    path = locate(name)
    if path is None:
        return unanswerable(
            "input_bytes", output,
            f"the artifact records a hash for the input {name}, and the tree holds "
            "no single file by that name to compare it against",
            INPUT_ABSENT, {"input": name})
    on_disk = digest(path)
    detail = {"input": name, "recorded": recorded[:12], "on_disk": on_disk[:12]}
    if on_disk == recorded:
        return held("input_bytes", output,
                    f"the input {name} is byte-for-byte what this artifact read",
                    detail)
    return failed("input_bytes", output, "an input has changed", detail)


def raw_tape_condition(output, node_key):
    """The input condition a raw-tape node cannot put, stated instead of skipped.

    Every parser in this tree deletes a day's hourly directory the moment it has
    parsed it, because the volume cannot hold the tape. So by the time the artifact
    is written its input no longer exists, nothing can be hashed, and no later run
    can compare anything. That is a property of the disk budget and not a defect,
    and the only wrong thing to do with it is to leave it unsaid -- which is what
    produced two raw-tape nodes reading "provably up to date" with nothing asked.
    """
    return unanswerable(
        "input_bytes", output,
        "this node walks the raw tape, and the parser deletes each day's hourly "
        "directory as soon as it has parsed it, so the input did not exist by the "
        "time the artifact was written and no hash of it was ever recorded. Whether "
        "this node is current cannot be established from the tree: that is neither "
        "proof it is current nor a reason to walk the tape again",
        RAW_TAPE_GONE, {"node": node_key})


# =====================================================================
# 3. THE FOLD, AND THE RULE THE OLD ONE DID NOT HAVE
# =====================================================================

def verdict(conditions):
    """One of the three states, from the conditions a caller managed to put.

    Three rules, and the third is the repair:

      a condition that was answered and FAILED makes the node run, whatever else
      holds. Something demonstrably moved, and nothing that could not be asked
      changes that.

      a condition that was ASKED and could not be ANSWERED makes the node unknown.
      It is not evidence of staleness and it is not evidence of currency.

      A NODE WITH NOTHING ANSWERED IS NEVER up_to_date. This is the rule the old
      code lacked, and it is not the same as the rule above it: a raw-tape node
      whose marking ladder is complete has one answered condition and would pass the
      second rule while nothing about its producer or its inputs had been looked at.
      Stated as a floor -- at least one condition must have been answered -- it
      catches that case and every future one shaped like it.
    """
    answered = [c for c in conditions if c.get("answered")]
    if any(c.get("holds") is False for c in answered):
        return MUST_RUN
    if not answered:
        return UNKNOWN
    if any(c.get("asked") and not c.get("answered") for c in conditions):
        return UNKNOWN
    return UP_TO_DATE


def split(conditions):
    """The conditions in the two lists build.py has always printed and recorded.

    `reasons` are the answered failures, which is what a plan prints as RUN lines.
    `unknown` are the questions that could not be put. Kept in the older shape --
    output plus why plus detail -- so that adding the third answer changes no field
    of build_results.json that anything already reads.
    """
    reasons, gaps = [], []
    for condition in conditions:
        if not condition.get("asked"):
            continue
        entry = {"output": condition["output"], "why": condition["why"]}
        if condition.get("detail") is not None:
            entry["detail"] = condition["detail"]
        if condition.get("answered"):
            if condition.get("holds") is False:
                reasons.append(entry)
        else:
            entry["cause"] = condition.get("cause")
            gaps.append(entry)
    return reasons, gaps


def causes(conditions):
    """How many questions could not be put, by the reason they could not.

    Printed beside a count of unknown nodes, because "twenty-three nodes cannot be
    told" is not actionable and "twelve of them because their input is the raw tape"
    is.
    """
    tally = {}
    for condition in conditions:
        if condition.get("asked") and not condition.get("answered"):
            cause = condition.get("cause") or NO_RECORD_AT_ALL
            tally[cause] = tally.get(cause, 0) + 1
    return tally


# =====================================================================
# 4. SELF-TEST
#
# Every leg is exercised on TWO OPPOSITE CASES: one input on which it must fire and
# one on which it must stay silent. One reference case cannot tell a predicate that
# is too loose from one that is too tight, and this repository has already shipped
# three editions of a single comparator that were wrong in opposite directions.
#
# The artifacts are fabricated in a temporary directory rather than taken from the
# tree. That is the point of the module boundary: the rule can be driven to all three
# answers in a second, where driving the real tree to them costs a full recompute.
# =====================================================================

_FIXTURE_PRODUCER = "# a stand-in producer for the calibration of skip_rule\n"


def _self_test_artifact(work, name, script_name, digest, inputs):
    """One results file with a producer record and an input list made to order.

    THE NAME OF THIS FUNCTION IS LOAD-BEARING and not a matter of taste. build.py
    reads its graph out of syntax trees, and it tells a build product from a test
    fixture by the name of the ENCLOSING FUNCTION: a write inside a scope beginning
    _self_test is a fixture and builds no edge. Called anything else, this function
    would make skip_rule.py a producer of the fabricated results files below, and
    they exist for a second inside a temporary directory.
    """
    import json
    import artifact
    document = {artifact.META_KEY: {
        "artifact_meta_version": 1,
        "results_file": name,
        "producer": {"script": script_name, "sha256": digest, "bytes": 1},
        "inputs": inputs,
        "scope": {"population": "fixture", "window": "fixture", "coins": "fixture"},
        artifact.VOLATILE_KEY: {"runtime_s": 0.0,
                                "finished_utc": "2026-07-31T12:00:00Z"},
    }, "value": 1}
    path = os.path.join(work, name)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(document, handle)
    return path


def _self_test():
    import shutil
    import tempfile
    import artifact

    failures, asserted = [], 0

    def expect(label, condition, detail=""):
        nonlocal asserted, failures
        asserted += 1
        print(f"  {'ok  ' if condition else 'FAIL'}  {label}"
              + (f"  --  {detail}" if detail else ""))
        if not condition:
            failures.append(label)

    print("=" * 78)
    print("  skip_rule.py self-test -- three answers, and each leg on two opposite "
          "cases")
    print("=" * 78)

    work = tempfile.mkdtemp(prefix="skip_rule_selftest_")
    try:
        script = os.path.join(work, "fixture_producer.py")
        with open(script, "w", encoding="utf-8") as handle:
            handle.write(_FIXTURE_PRODUCER)
        real = artifact.sha256_file(script)
        moved = "0" * 64

        payload = os.path.join(work, "fixture_input.json")
        with open(payload, "w", encoding="utf-8") as handle:
            handle.write('{"n": 1}')
        payload_hash = artifact.sha256_file(payload)

        def locate(name):
            path = os.path.join(work, name)
            return path if os.path.isfile(path) else None

        print("\n  LEG: the producer bytes, delegated to checks/run_record.py")
        _self_test_artifact(work, "fx_same_results.json", "fixture_producer.py", real, [])
        _self_test_artifact(work, "fx_moved_results.json", "fixture_producer.py", moved, [])
        scripts = R.script_index(work)
        same = producer_condition("fx_same_results.json", work, "fx_same_results.json",
                                  scripts)
        gone = producer_condition("fx_moved_results.json", work,
                                  "fx_moved_results.json", scripts)
        expect("a matching producer hash HOLDS",
               same["answered"] and same["holds"] is True, f"{same['why'][:52]}")
        expect("and a moved producer hash FAILS -- the opposite case",
               gone["answered"] and gone["holds"] is False,
               f"recorded {gone['detail']['recorded']}, on disk "
               f"{gone['detail']['on_disk']}")
        with open(os.path.join(work, "fx_nometa.npz"), "wb") as handle:
            handle.write(b"not really an npz")
        blind = producer_condition("fx_nometa.npz", work, "fx_nometa.npz", scripts)
        expect("and a format that carries no record is UNANSWERABLE, neither of the "
               "two", not blind["answered"] and blind["holds"] is None,
               f"cause {blind['cause']}")

        print("\n  LEG: one recorded input against the file on disk")
        good = input_condition({"name": "fixture_input.json", "sha256": payload_hash},
                               "fx", locate, artifact.sha256_file)
        bad = input_condition({"name": "fixture_input.json", "sha256": "1" * 64},
                              "fx", locate, artifact.sha256_file)
        expect("an unchanged input HOLDS",
               good["answered"] and good["holds"] is True, good["detail"]["input"])
        expect("and a moved input FAILS -- the opposite case",
               bad["answered"] and bad["holds"] is False,
               f"recorded {bad['detail']['recorded']}, on disk "
               f"{bad['detail']['on_disk']}")
        absent = input_condition({"name": "never_written.npz", "sha256": "2" * 64},
                                 "fx", locate, artifact.sha256_file)
        expect("an input whose file is gone is UNANSWERABLE, not a pass and not a "
               "failure", not absent["answered"] and absent["cause"] == INPUT_ABSENT)
        unhashed = input_condition(
            {"name": "s3://bucket/node_fills_by_block/hourly/20251204/",
             "sha256": None, "present": False}, "fx", locate, artifact.sha256_file)
        expect("and an input recorded WITHOUT a hash is unanswerable too, where the "
               "old rule passed over it in silence",
               not unhashed["answered"] and unhashed["cause"] == RAW_TAPE_GONE)

        print("\n  THE FOLD: what a mixture of conditions comes to")
        one = held("settings", "fx", "nothing moved")
        two = failed("settings", "fx", "the setting moved")
        three = unanswerable("input_bytes", "fx", "no hash", NO_HASH_RECORDED)
        expect("all conditions answered and holding -> up_to_date",
               verdict([one, one]) == UP_TO_DATE)
        expect("one answered failure -> must_run",
               verdict([one, two, three]) == MUST_RUN)
        expect("one unanswerable beside a holding condition -> unknown, NOT "
               "up_to_date", verdict([one, three]) == UNKNOWN)
        expect("nothing answered at all -> unknown, NOT up_to_date. This is the case "
               "two raw-tape nodes were reading as proof",
               verdict([three, three]) == UNKNOWN)
        expect("and no conditions at all -> unknown", verdict([]) == UNKNOWN)

        print("\n  THE SPLIT AND THE CAUSES, as the plan prints them")
        reasons, gaps = split([one, two, three])
        expect("the answered failure lands in reasons and nothing else does",
               len(reasons) == 1 and reasons[0]["why"] == "the setting moved")
        expect("the unanswerable lands in the gaps, carrying its cause",
               len(gaps) == 1 and gaps[0]["cause"] == NO_HASH_RECORDED)
        expect("and the causes are tallied by name",
               causes([three, three, one]) == {NO_HASH_RECORDED: 2})

        print("\n  THE REFUSAL: an unnamed cause is not accepted")
        try:
            unanswerable("input_bytes", "fx", "because", "a reason nobody named")
            expect("an unnamed cause raises", False, "it was accepted")
        except ValueError as exc:
            expect("an unnamed cause raises rather than printing as a new kind of "
                   "gap", "is not one of the causes" in str(exc))
    finally:
        shutil.rmtree(work, ignore_errors=True)

    print("-" * 78)
    print(f"  {asserted - len(failures)} of {asserted} assertions hold")
    print(f"  VERDICT: {'PASS' if not failures else 'FAIL ' + ', '.join(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(_self_test())
