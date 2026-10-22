#!/usr/bin/env python3
"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-07-31
References: none (repository gate; it declares no quantity of its own and reads the
run record artifact.py writes into every results file).

BEFORE ASKING WHETHER THE NUMBERS MOVED, ASK WHETHER ANYTHING RAN.

What this gate is for, and it is one incident rather than a principle. A producer was
edited, a recompute was launched, and the resulting artifact was compared leaf by leaf
against a snapshot taken before the edit: 454 leaves, none moved. That reads as proof
that the edit is number-neutral and it is not proof of anything, because the run never
started -- the launcher was the tail of a command chain, it did not survive the
wrapper, its log was zero bytes and no process was alive. The comparison had compared
a file with a copy of itself and could not have returned anything else.

A failing check is harmless: it stops the work. This one returned the expected answer,
which is why the defect needs a gate of its own rather than a rule of thumb.

HOW IT IS USED. The reference moment is the instant the recompute was asked for, and
it is an argument because nothing on disk records it:

    uv run --no-project python3 checks/chk_run_happened.py --since 2026-07-31T14:53:00Z
    uv run --no-project python3 checks/chk_run_happened.py --since-file panel_run.log
    uv run --no-project python3 checks/chk_run_happened.py --since now \\
        --only ws1_horizon_results.json
    uv run --no-project python3 checks/chk_run_happened.py            # hash leg only
    uv run --no-project python3 checks/chk_run_happened.py --self-test

With no --since the "did anything run" question is NOT PUT and the run says so in its
verdict line and in its own results file; only the producer-hash leg is judged, and
the overall verdict is uncertain however clean that leg comes out. A gate that
answered the easy half quietly would repeat the defect it exists to catch.

WHAT IT READS AND WHAT IT WRITES. It reads _meta blocks and hashes .py files. It runs
no producer, downloads nothing and touches no artifact but its own results file.

ONE SELF-REFERENCE, DECLARED RATHER THAN LEFT TO SURFACE. Inside the battery this gate
runs before run_all_checks.py writes its own results file, so it always reads that file
as the PREVIOUS run left it. Edit run_all_checks.py and the first battery run after the
edit reports its results file as written by code that is no longer on disk, which is
true and is exactly what the gate is for; the second run clears it. Observed on
2026-07-31, predicted and then confirmed by running the battery twice: two divergences
became one, and the remaining one is the tape node nobody has recomputed. It is left
visible rather than exempted, because an exemption here would be the gate declining to
report the one class of staleness it can see without being told a reference moment.
"""
import argparse
import json
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
_TREE = os.path.dirname(HERE)
if _TREE not in sys.path:
    sys.path.insert(0, _TREE)
import artifact                                                       # noqa: E402
import chk_artifact_provenance as _prov                               # noqa: E402
from evidence import report_contract                                  # noqa: E402
import run_record as R                                                # noqa: E402

OUT_JSON = os.path.join(HERE, "chk_run_happened_results.json")


def _reference(args):
    """The reference moment as epoch seconds, or None when it was not given."""
    if args.since_file:
        path = args.since_file if os.path.isabs(args.since_file) else os.path.join(
            args.root, args.since_file)
        if not os.path.exists(path):
            raise SystemExit(f"[run-happened] no such launch marker: "
                             f"{os.path.basename(args.since_file)}")
        return R.moment_of_file(path)
    if args.since:
        if args.since == "now":
            return time.time()
        return R.parse_moment(args.since)
    return None


def _print_summary(records, reference, blind):
    tally = {}
    for record in records:
        tally[record["verdict"]] = tally.get(record["verdict"], 0) + 1
    print("=" * 78)
    print("  DID THE RUN HAPPEN - run-record gate")
    print("=" * 78)
    if reference is None:
        print("  reference moment  : NOT GIVEN. The question 'did anything run' was "
              "NOT PUT;")
        print("                      only the producer-hash leg below was judged. "
              "Pass --since to ask it.")
    else:
        print(f"  reference moment  : {R.as_utc(reference)}")
    print(f"  artifacts examined: {len(records)}")
    for verdict in (R.RAN, R.DID_NOT_RUN, R.NEUTRAL_BY_CERTIFICATE,
                    R.KIND_NOT_ANSWERABLE, R.UNANSWERABLE):
        print(f"    {verdict:22}: {tally.get(verdict, 0)}")
    if tally.get(R.NEUTRAL_BY_CERTIFICATE):
        print(f"      {tally[R.NEUTRAL_BY_CERTIFICATE]} of the above were NOT written "
              f"by the producer bytes now on disk. checks/NEUTRAL_EDITS.json")
        print("      certifies that each exact pair of hashes cannot have moved a "
              "figure, which is a")
        print("      proof about an edit and never a record of a run. Named here so "
              "the share of this")
        print("      tree standing on a proof rather than on a run stays countable:")
        for record in records:
            if record["verdict"] == R.NEUTRAL_BY_CERTIFICATE:
                print(f"        - {record['artifact']}")
    print("-" * 78)
    print("  WHAT THIS GATE DOES NOT SEE, counted on this tree:")
    print(f"    artifacts with no finish time recorded : "
          f"{blind['no_finish_time_recorded']['count']}")
    print(f"    artifacts with no producer hash        : "
          f"{blind['no_producer_hash_recorded']['count']}")
    print(f"    files with nowhere to keep a record    : "
          f"{blind['outside_the_range_entirely']['count']} "
          f"(.npz / .png / .csv / .parquet)")
    print(f"    time discrimination                    : "
          f"{blind['reference_resolution_s']} s, no finer")
    reach = blind["hash_covers_one_file_of"]
    print(f"    modules behind a typical artifact      : "
          f"{reach['median_modules_behind_an_artifact']} imported, 1 hashed "
          f"(widest: {reach['widest']['modules']} behind "
          f"{reach['widest']['artifact']})")
    for row in reach["top_shared_modules"]:
        print(f"      an edit to {row['module']:<28} moves numbers in "
              f"{row['artifacts_it_reaches']} artifacts and trips 0 legs")


# =====================================================================
# CALIBRATION: ONE INPUT THAT MUST FIRE, ONE THAT MUST STAY SILENT
#
# Two opposite cases per leg, and both pairs are taken from the live tree wherever
# the tree can supply them, because a comparator checked against one reference cannot
# tell a comparator that is too loose from one that is too tight. This project has
# already shipped three versions of one guard that were wrong in opposite directions
# and passed the single reference each time.
#
# LEG ONE is calibrated on the real artifacts and cannot go stale: with the reference
# moment set to now, every artifact that records a finish time must read did_not_run,
# because no run in this tree finished in the future; with the reference set to the
# epoch, every one of them must read ran on that leg. Same files, opposite verdicts,
# and no literal for either.
#
# LEG TWO is calibrated on the divergence the tree actually holds: one artifact whose
# recorded producer hash differs from the script on disk, and the rest that match. If
# that divergence is ever repaired the opposite case disappears from the tree, and the
# self-test then says so and reports the leg as NOT ANSWERED rather than passing on a
# population with no failures in it.
#
# A fabricated pair runs beside both, in a temporary directory, so the two legs are
# also exercised against inputs built to fail one at a time.
# =====================================================================

_FIXTURE_PRODUCER = "# a stand-in producer for the calibration of chk_run_happened\n"


def _self_test_fixture(work, name, script_name, digest, finished_utc):
    """One artifact with a run record made to order, written into a temp directory.

    THE NAME OF THIS FUNCTION CARRIES MEANING AND IS NOT FREE TO CHANGE. The build
    tells a product apart from a calibration fixture by the name of the enclosing
    function, matching the prefixes in build.FIXTURE_SCOPES. Under the earlier name
    the graph read every file written here as an output of this check, went looking
    for fixture_1_results.json in the tree, did not find it, and left the node
    permanently in "must run" with the cause "absent from the tree" -- a node the
    plan would offer to recompute forever for a file that exists only inside a
    temporary directory that this function deletes.
    """
    document = {artifact.META_KEY: {
        "artifact_meta_version": 1,
        "results_file": name,
        "producer": {"script": script_name, "sha256": digest, "bytes": 1},
        "inputs": [],
        "scope": {"population": "fixture", "window": "fixture", "coins": "fixture"},
        artifact.VOLATILE_KEY: {"runtime_s": 0.0, "finished_utc": finished_utc},
    }, "value": 1}
    path = os.path.join(work, name)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(document, handle)
    return path


def _self_test(root):
    """Prove the guard fires on one input and stays silent on its opposite."""
    failures, asserted = [], 0

    def expect(label, condition, detail=""):
        nonlocal asserted
        asserted += 1
        mark = "ok  " if condition else "FAIL"
        print(f"    [{mark}] {label}" + (f"  {detail}" if detail else ""))
        if not condition:
            failures.append(label)

    print("-" * 78)
    print("  CALIBRATION 1: fabricated pair, one leg wrong at a time")
    with tempfile.TemporaryDirectory() as work:
        script = os.path.join(work, "fixture_producer.py")
        with open(script, "w", encoding="utf-8") as handle:
            handle.write(_FIXTURE_PRODUCER)
        real = artifact.sha256_file(script)
        wrong = "0" * 64
        reference = R.parse_moment("2026-07-31T12:00:00Z")
        scripts = {"fixture_producer.py": "fixture_producer.py"}

        cases = (
            ("late finish, matching hash", "13:00:00Z", real, R.RAN),
            ("early finish, matching hash", "11:00:00Z", real, R.DID_NOT_RUN),
            ("late finish, moved hash", "13:00:00Z", wrong, R.DID_NOT_RUN),
            ("early finish, moved hash", "11:00:00Z", wrong, R.DID_NOT_RUN),
        )
        for index, (label, clock, digest, want) in enumerate(cases):
            name = f"fixture_{index}_results.json"
            _self_test_fixture(work, name, "fixture_producer.py", digest,
                     f"2026-07-31T{clock}")
            got = R.judge(name, work, scripts, reference)
            expect(f"{label} -> {want}", got["verdict"] == want,
                   f"got {got['verdict']}")
            if want == R.DID_NOT_RUN:
                expect(f"{label} states expectation, fact and place",
                       bool(got["why"]) and bool(got["place"]),
                       f"why={got['why'][0][:48]}...")

        # An artifact recording no finish time is neither a pass nor a failure.
        name = "fixture_silent_results.json"
        path = _self_test_fixture(work, name, "fixture_producer.py", real, "2026-07-31T13:00:00Z")
        document = json.load(open(path, encoding="utf-8"))
        document[artifact.META_KEY][artifact.VOLATILE_KEY].pop("finished_utc")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(document, handle)
        got = R.judge(name, work, scripts, reference)
        expect("no finish time recorded -> unanswerable, not ran",
               got["verdict"] == R.UNANSWERABLE, f"got {got['verdict']}")

    print()
    print("  CALIBRATION 2: leg one against the live tree, opposite references")
    future, _ = R.sweep(root, reference=time.time())
    past, _ = R.sweep(root, reference=R.parse_moment("1970-01-02T00:00:00Z"))
    timed = [r for r in future
             if (r["legs"]["finished_after_reference"]).get("answered")]
    fired = [r for r in timed if r["verdict"] == R.DID_NOT_RUN]
    passed = [r for r in past
              if (r["legs"]["finished_after_reference"]).get("holds") is True]
    expect("reference = now: every recorded run reads did_not_run",
           len(timed) > 0 and len(fired) == len(timed),
           f"{len(fired)} of {len(timed)} artifacts carrying a finish time")
    expect("reference = 1970: every recorded run passes leg one",
           len(passed) == len(timed),
           f"{len(passed)} of {len(timed)}")

    print()
    print("  CALIBRATION 3: leg two, both cases DERIVED from a live artifact")
    # THE ANCHOR IS CHOSEN BY RULE AND THE OPPOSITE CASE IS MADE FROM IT. The earlier
    # version of this block anchored the must-fire case on whatever divergence the tree
    # happened to hold, and 2026-08-04 is exactly the day that emptied: the four
    # diverged artifacts all turned out to carry certificates, so the leg that proved
    # this guard could find anything would have reported nothing and passed. A
    # calibration anchored on a live defect erases itself the day the defect is
    # repaired. Both cases below are cut from a real artifact of this tree, and the
    # must-fire one differs from the must-stay-silent one by ONE HEX DIGIT of the
    # recorded hash and by nothing else, so the two arms are a comparison.
    records, _ = R.sweep(root, reference=None)
    silent_source = next((r for r in sorted(records, key=lambda x: x["artifact"])
                          if r["verdict"] == R.RAN), None)
    if silent_source is None:
        expect("a live artifact whose producer hash matches exists to cut the pair "
               "from", False, "no artifact of this tree reads 'ran'")
    else:
        rel = silent_source["artifact"]
        producer_rel = silent_source["legs"]["producer_hash_matches_disk"]["producer"]
        with tempfile.TemporaryDirectory() as work:
            os.makedirs(os.path.join(work, "checks"), exist_ok=True)
            producer_name = os.path.basename(producer_rel)
            with open(os.path.join(root, producer_rel), "rb") as src, \
                    open(os.path.join(work, producer_name), "wb") as dst:
                dst.write(src.read())
            with open(os.path.join(root, rel), encoding="utf-8") as handle:
                document = json.load(handle)
            true_hash = document[artifact.META_KEY]["producer"]["sha256"]
            moved = ("1" if true_hash[0] != "1" else "0") + true_hash[1:]
            scripts = {producer_name: producer_name}

            def _self_test_cut(digest, name):
                document[artifact.META_KEY]["producer"]["script"] = producer_name
                document[artifact.META_KEY]["producer"]["sha256"] = digest
                path = os.path.join(work, name)
                with open(path, "w", encoding="utf-8") as handle:
                    json.dump(document, handle)
                return R.judge(name, work, scripts, None)

            quiet = _self_test_cut(true_hash, os.path.basename(rel))
            loud = _self_test_cut(moved, os.path.basename(rel))
            expect("MUST STAY SILENT: the artifact as the tree holds it reads ran",
                   quiet["verdict"] == R.RAN,
                   f"{os.path.basename(rel)} gave {quiet['verdict']}")
            expect("MUST FIRE: the same record with one hex digit of the recorded "
                   "hash changed reads did_not_run",
                   loud["verdict"] == R.DID_NOT_RUN,
                   f"gave {loud['verdict']}")
            expect("the firing case states the expectation, the fact and the place",
                   bool(loud["why"]) and bool(loud["place"])
                   and loud["legs"]["producer_hash_matches_disk"].get(
                       "on_disk_sha256"),
                   f"{loud['why'][0][:56]}..." if loud["why"] else "no why recorded")

    print()
    print("  CALIBRATION 4: the certificate excuses leg two and nothing else")
    # Added 2026-08-04 with the certificate lookup itself. Three cases, and the third
    # is what keeps the excuse narrow: a certificate is a statement about an EDIT, so
    # it may never rescue an artifact that failed the question "did anything run".
    with tempfile.TemporaryDirectory() as work:
        os.makedirs(os.path.join(work, "checks"), exist_ok=True)
        script = os.path.join(work, "fixture_producer.py")
        with open(script, "w", encoding="utf-8") as handle:
            handle.write(_FIXTURE_PRODUCER)
        on_disk = artifact.sha256_file(script)
        recorded = ("1" if on_disk[0] != "1" else "0") + on_disk[1:]
        scripts = {"fixture_producer.py": "fixture_producer.py"}
        name = "fixture_certified_results.json"
        reference = R.parse_moment("2026-07-31T12:00:00Z")

        def _self_test_register(pair):
            with open(os.path.join(work, "checks", "NEUTRAL_EDITS.json"), "w",
                      encoding="utf-8") as handle:
                json.dump({"_declaration": {"issued_utc": "2026-08-04T00:00:00Z",
                                            "evidence": "calibration fixture"},
                           "certified": [{"artifact": name,
                                          "producer": "fixture_producer.py",
                                          "sha256_recorded": pair[0],
                                          "sha256_on_disk": pair[1]}]}, handle)
            _prov._NEUTRAL_CACHE.clear()

        _self_test_fixture(work, name, "fixture_producer.py", recorded,
                           "2026-07-31T13:00:00Z")
        _self_test_register((recorded, on_disk))
        excused = R.judge(name, work, scripts, None)
        expect("MUST STAY SILENT: a moved hash covered by a certificate for that "
               "exact pair is not a run that failed to happen",
               excused["verdict"] == R.NEUTRAL_BY_CERTIFICATE,
               f"gave {excused['verdict']}")
        expect("and it is NOT folded into ran: the record still says the file was "
               "not written by the bytes on disk",
               excused["verdict"] != R.RAN and bool(excused["why"]),
               f"{excused['why'][0][:60]}..." if excused["why"] else "silent")

        _self_test_register((("2" if recorded[0] != "2" else "3") + recorded[1:], on_disk))
        wrong_pair = R.judge(name, work, scripts, None)
        expect("MUST FIRE: a certificate naming a different pair of hashes does not "
               "cover this one",
               wrong_pair["verdict"] == R.DID_NOT_RUN,
               f"gave {wrong_pair['verdict']}")

        early = "fixture_certified_early_results.json"
        _self_test_fixture(work, early, "fixture_producer.py", recorded,
                           "2026-07-31T11:00:00Z")
        _self_test_register((recorded, on_disk))
        with open(os.path.join(work, "checks", "NEUTRAL_EDITS.json"),
                  encoding="utf-8") as handle:
            register = json.load(handle)
        register["certified"][0]["artifact"] = early
        with open(os.path.join(work, "checks", "NEUTRAL_EDITS.json"), "w",
                  encoding="utf-8") as handle:
            json.dump(register, handle)
        _prov._NEUTRAL_CACHE.clear()
        stale_run = R.judge(early, work, scripts, reference)
        expect("MUST FIRE ANYWAY: a certified artifact that finished BEFORE the "
               "reference moment still reads did_not_run",
               stale_run["verdict"] == R.DID_NOT_RUN,
               f"gave {stale_run['verdict']}; the certificate is a proof about an "
               f"edit and says nothing about whether anything ran")
        _prov._NEUTRAL_CACHE.clear()

    print()
    print(f"  {asserted - len(failures)} of {asserted} calibration assertions hold")
    if failures:
        for label in failures:
            print(f"    FAILED: {label}")
        return 1
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Whether a recompute actually happened, before any comparison of "
                    "numbers is allowed to mean anything.")
    parser.add_argument(
        "--root", default=os.path.dirname(HERE),
        help="the tree to read. Defaults to the repository this file lives in. It is "
             "an option because the same question is asked of a scratch copy of a "
             "run before its artifacts are moved into the tree, and a gate that can "
             "read only one directory has to be edited to answer that")
    parser.add_argument(
        "--since", default=None,
        help="the moment the recompute was launched, as an ISO instant such as "
             "2026-07-31T14:53:00Z, or the word now")
    parser.add_argument(
        "--since-file", default=None,
        help="a file whose modification time marks the launch, such as the log the "
             "launcher opens when it starts")
    parser.add_argument("--only", nargs="+", default=None,
                        help="judge these results files instead of the whole tree")
    parser.add_argument("--self-test", action="store_true",
                        help="run the calibration and exit")
    args = parser.parse_args(argv)
    args.root = os.path.abspath(args.root)

    if args.self_test:
        return _self_test(args.root)

    started = artifact.start_clock()
    reference = _reference(args)
    records, dropped = R.sweep(args.root, args.only, reference)
    blind = R.blindness(args.root, records)
    _print_summary(records, reference, blind)

    tally = {}
    for record in records:
        tally[record["verdict"]] = tally.get(record["verdict"], 0) + 1
    payload = {
        "verdict": ("FAIL" if tally.get(R.DID_NOT_RUN)
                    else "UNCERTAIN" if reference is None
                    else "PASS"),
        "reference_utc": R.as_utc(reference) if reference is not None else None,
        "reference_given": reference is not None,
        "question_put": ("both legs" if reference is not None
                         else "the producer-hash leg only; whether any run happened "
                              "was NOT ASKED because no reference moment was given"),
        "tally": tally,
        "records": records,
        "blindness": blind,
        "population_dropped": dropped,
    }
    artifact.write(
        os.path.basename(OUT_JSON), payload,
        script=__file__,
        # The tree is the input and it is a list of files rather than one file, so it
        # is stated in scope instead of being hashed member by member.
        inputs=[],
        scope={
            "population": f"{len(records)} git-tracked results files, "
                          f"{len(dropped)} dropped by the .gitignore predicate",
            "window": "n/a: this gate reads run records as they stand now, not a "
                      "period of market data",
            "coins": "n/a: this gate reads file metadata and touches no market data",
        },
        started=started,
        extra_meta={"reference_utc": payload["reference_utc"],
                    "question_put": payload["question_put"]},
    )
    print(f"  results -> {os.path.basename(OUT_JSON)}")
    agreement = R.contract(records, reference)
    return report_contract(
        agreement, OUT_JSON,
        inputs={"tree": os.path.basename(args.root),
                "reference": payload["reference_utc"] or "NOT GIVEN"},
        # Named rather than defaulted. These are the artifacts that declare, in their
        # own _meta, a record_kind whose producer hash answers nothing; listing them
        # here puts the exemption on the screen instead of leaving it as a silent rule.
        informational=agreement.get("informational") or (),
        extra={"what a green run still permits":
               blind["what_a_pass_still_permits"]})


if __name__ == "__main__":
    sys.exit(main())
