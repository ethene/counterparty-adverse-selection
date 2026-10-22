#!/usr/bin/env python3
"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-07-31
References: none (repository infrastructure; it declares no quantity of its own and
reads the run record artifact.py writes into every results file).

DID THE RUN HAPPEN. A CLEAN DIFF IS FREE WHEN NOTHING RAN.

Why this module exists, measured rather than supposed. On 31 July a producer was
edited, a recompute was launched, and the artifact was then compared leaf by leaf
against a snapshot taken before the edit. The comparison returned 454 leaves, zero
moved, and that was very nearly carried into the work as proof that the edit changed
no number. The run had not happened: the launcher was the tail of a command chain, it
did not survive the wrapper, the log file was zero bytes and no process was alive. The
comparison had compared a file with a copy of itself, and a clean answer was
guaranteed whatever the edit did.

The shape of that failure is what makes it worth a module. A check that dies returns
an error and stops the work; this one returned exactly the answer it was asked for. So
the question "are the numbers the same" may not be put until the question "did
anything run" has been answered, and answering the second one needs facts the first
one never looks at.

TWO LEGS, AND ONE OF THEM IS NOT ELSEWHERE IN THIS TREE. A run happened when both of
these hold of the artifact's own _meta block:

    _meta.run.finished_utc is LATER than the moment the recompute was launched,
    _meta.producer.sha256 equals the bytes of the producer script on disk.

The second leg is already asked by checks/chk_artifact_provenance.py, whose
freshness() answers "does this file still match the code that wrote it", and this
module calls that same population and the same script index rather than growing a
second home for either. The first leg is asked nowhere: build.py's skip rule reads the
producer hash, the input hashes and the settings, and states plainly that it consults
no date. That is right for the skip rule, whose question is "what was this computed
with". It is not enough for the question "did the thing I launched an hour ago
actually run", because an artifact that was never rewritten answers the hash leg
perfectly.

THE REFERENCE MOMENT IS AN ARGUMENT AND HAS NO DEFAULT. There is no way to read off a
file when somebody meant to start a recompute, so the caller says it: an ISO instant,
or a file whose modification time marks the launch. With no reference given the first
leg is NOT ASKED, and every printed line and the results file say so in those words.
A guard that silently answered the easy half would be the same defect one level up.

WHAT A PASS DOES NOT MEAN, and it is worth saying in the module rather than in a
report nobody opens. Both legs together prove that a process wrote this file after the
reference moment using today's producer bytes. They do not prove the numbers were
recomputed: a producer that reads a cache and rewrites its own artifact passes both.
And the producer hash covers the producer's own bytes only, so an edit to a module it
imports moves the numbers and moves neither leg; chk_run_happened.py measures how far
that reaches and prints the count.

    from run_record import judge, sweep, contract
"""
import ast
import datetime
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
_TREE = os.path.dirname(HERE)
if _TREE not in sys.path:
    sys.path.insert(0, _TREE)
import artifact                                                       # noqa: E402
import chk_artifact_provenance as _prov                               # noqa: E402

# The five answers, kept apart. RAN and DID_NOT_RUN are opposite verdicts on a
# question that was put; UNANSWERABLE means it could not be put, and folding it into
# either of the others is how a tree of unrecorded runs reads as a tree of good ones.
RAN = "ran"
DID_NOT_RUN = "did_not_run"
UNANSWERABLE = "unanswerable"

# THE FOURTH AND FIFTH, ADDED 2026-08-04, AND THE REASON IS A DISAGREEMENT BETWEEN TWO
# INSTRUMENTS RATHER THAN A PREFERENCE. This module and chk_artifact_provenance.py put
# the same producer-hash question and read it off two different exemption lists: on
# 2026-08-04 the provenance census reported zero artifacts older than their code while
# this module reported four as runs that never happened, and the four were the same
# four -- every one of them carrying a certificate in checks/NEUTRAL_EDITS.json stating
# that the edit which moved the hash cannot have moved a figure. One tree, one
# question, two answers, and neither instrument wrong about what it was actually
# asking. The cure is that this module CALLS the provenance gate's certificate lookup
# and its vocabulary of record kinds rather than keeping copies: a guard that reprints
# a rule goes blind to that rule changing, which is the defect repaired in the
# no-lookahead guard on 2026-08-02.
#
# Neither is folded into RAN, and that matters more than the exit code. A certified
# artifact was NOT written by the bytes on disk; what is proven is that the difference
# cannot reach a number. A reader must be able to see how much of a green tree rests on
# a proof rather than on a run, so the two are tallied and printed under their own
# names.
NEUTRAL_BY_CERTIFICATE = "neutral_by_certificate"
KIND_NOT_ANSWERABLE = "kind_not_answerable"

# THE CERTIFICATE EXCUSES ONE LEG AND NEVER THE OTHER, and the asymmetry is the whole
# of its meaning. It is a statement about an EDIT: these two spellings of the producer
# compute the same figures. It says nothing whatever about whether a process ran since
# the moment a recompute was asked for, so leg one keeps its verdict untouched and an
# artifact that failed leg one still reads did_not_run however well certified it is.
CERTIFICATE_EXCUSES = "producer_hash_matches_disk"

# THE DECLARED KIND EXCUSES THAT SAME LEG AND NO OTHER, for a different reason and with
# the same limit. The certificate is a proof about one EDIT: these two spellings of the
# producer compute the same figures. The kind is a statement about the FILE: it records
# that a run happened rather than what a quantity is, so its producer hash is right for
# the run it describes and goes stale on the next edit to that producer by
# construction, and asking freshness of it has no answer rather than a bad one. Both
# stop at the same place. Neither says a process ran since a recompute was asked for,
# so leg one keeps its verdict untouched and a journal that failed leg one still reads
# did_not_run however plainly it declares its kind.
KIND_EXCUSES = "producer_hash_matches_disk"

# The shape artifact.py writes: "%Y-%m-%dT%H:%M:%SZ". One second is therefore the
# finest reference moment this module can resolve, and a run that finished inside the
# same second as the reference is not distinguishable from one that finished before it.
FINISH_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
FINISH_RESOLUTION_S = 1

# Extensions that can carry a run record at all. An .npz is a zip of arrays and an
# .png is an image; neither has anywhere to put a _meta block, so neither can be asked
# this question and both are counted as out of range rather than reported as clean.
RECORDED_EXT = (".json",)


def parse_moment(text):
    """An ISO instant as epoch seconds, or a ValueError naming what was expected.

    Accepts the spelling artifact.py writes and the spellings a person types. A
    timestamp with no zone is read as UTC, because every stamp in this tree is UTC and
    reading a bare local time as local would move the reference by the machine's
    offset without telling anybody.
    """
    raw = str(text).strip()
    normalised = raw.replace("Z", "+00:00").replace(" ", "T")
    try:
        moment = datetime.datetime.fromisoformat(normalised)
    except ValueError:
        raise ValueError(
            f"{raw!r} is not an instant this module can read. Expected an ISO "
            f"instant such as 2026-07-31T14:53:00Z, which is the spelling "
            f"artifact.py writes into _meta.run.finished_utc")
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=datetime.timezone.utc)
    return moment.timestamp()


def moment_of_file(path):
    """The modification time of a launch marker, as epoch seconds.

    The use is narrow and it is the one the 31 July failure needed: the launcher
    writes a log the moment it starts, so that file's date is when the recompute was
    asked for. It is a reference moment, never a verdict -- nothing here compares one
    file's date against another's.
    """
    return os.path.getmtime(path)


def as_utc(epoch):
    """Epoch seconds in the spelling the artifacts use, so both sides read alike."""
    return datetime.datetime.fromtimestamp(
        float(epoch), datetime.timezone.utc).strftime(FINISH_FORMAT)


def finish_of(meta):
    """(epoch, recorded text, why it is missing) for one artifact's run record."""
    block = meta.get(artifact.VOLATILE_KEY) if isinstance(meta, dict) else None
    if not isinstance(block, dict):
        return None, None, (f"carries no _meta.{artifact.VOLATILE_KEY} block, so it "
                            f"records no moment at which a computation finished")
    recorded = block.get("finished_utc")
    if not recorded:
        return None, None, (f"_meta.{artifact.VOLATILE_KEY} records no finished_utc, "
                            f"so the moment its computation ended is not on file")
    try:
        return parse_moment(recorded), recorded, None
    except ValueError as exc:
        return None, recorded, str(exc)


def producer_of(meta):
    """(script basename, recorded sha256, why it is missing) for one artifact."""
    record = meta.get("producer") if isinstance(meta, dict) else None
    if not isinstance(record, dict):
        return None, None, ("names no producer in the canonical _meta.producer "
                            "record, so it cannot be told from the code that wrote it")
    name, digest = record.get("script"), record.get("sha256")
    if not name or not digest:
        return name, digest, ("_meta.producer records "
                              f"{'no script name' if not name else 'no sha256'}, so "
                              "the artifact cannot be compared with a file on disk")
    return name, digest, None


def script_index(root):
    """Producer basename -> repo-relative path, from the provenance gate's own map.

    Imported rather than rewritten. It is the same question that gate asks and it
    already answers a duplicate basename with None instead of guessing; two
    implementations of one predicate is how two honest censuses of these artifacts
    returned 24 and 32 for a single property.
    """
    return _prov.scripts_on_disk(root)


def judge(rel, root, scripts=None, reference=None):
    """Whether a run wrote this artifact after the reference moment, with today's code.

    `rel` is repo-relative; `reference` is epoch seconds or None. The record returned
    always carries the expectation, the fact and the place, whatever the verdict, so a
    caller printing a failure never has to go and look them up.
    """
    scripts = script_index(root) if scripts is None else scripts
    path = os.path.join(root, rel)
    record = {
        "artifact": rel,
        "reference_utc": as_utc(reference) if reference is not None else None,
        "verdict": UNANSWERABLE,
        "legs": {},
        "why": [],
        "place": f"{os.path.basename(rel)} -> _meta.{artifact.VOLATILE_KEY}."
                 f"finished_utc and _meta.producer.sha256",
    }
    if not rel.endswith(RECORDED_EXT):
        record["why"].append(
            f"{os.path.splitext(rel)[1] or 'this file type'} carries no _meta block, "
            f"so neither leg can be read out of it")
        return record
    try:
        meta = artifact.read_meta(path)
    except (ValueError, OSError) as exc:
        record["why"].append(f"unreadable as an artifact: {exc}")
        return record

    finished, finished_text, finish_gap = finish_of(meta)
    name, recorded_hash, producer_gap = producer_of(meta)
    record["producer"] = name

    # LEG ONE: the run ended after the moment the recompute was asked for.
    if reference is None:
        record["legs"]["finished_after_reference"] = {
            "asked": False,
            "recorded_finish_utc": finished_text,
            "why_not_asked": "no reference moment was given, so the question 'did "
                             "anything run' was NOT PUT; pass one to ask it",
        }
    elif finished is None:
        record["legs"]["finished_after_reference"] = {
            "asked": True, "answered": False, "recorded_finish_utc": finished_text,
            "why": finish_gap}
        record["why"].append(finish_gap)
    else:
        after = finished > reference
        record["legs"]["finished_after_reference"] = {
            "asked": True, "answered": True, "holds": after,
            "recorded_finish_utc": finished_text,
            "reference_utc": as_utc(reference),
            "seconds_after_reference": round(finished - reference, 3),
        }
        if not after:
            record["why"].append(
                f"the last computation this file records finished at "
                f"{finished_text}, which is {round(reference - finished)} s BEFORE "
                f"the reference moment {as_utc(reference)}: no run of it has happened "
                f"since")

    # LEG TWO: the bytes that wrote it are the bytes on disk.
    if recorded_hash is None:
        record["legs"]["producer_hash_matches_disk"] = {
            "asked": True, "answered": False, "why": producer_gap}
        record["why"].append(producer_gap)
    else:
        producer_rel = scripts.get(name)
        if not producer_rel:
            gap = (f"names {name} as its producer, and the tree holds "
                   f"{'no file' if name not in scripts else 'more than one file'} "
                   f"by that name, so the recorded hash has nothing to be compared "
                   f"against")
            record["legs"]["producer_hash_matches_disk"] = {
                "asked": True, "answered": False, "why": gap}
            record["why"].append(gap)
        else:
            on_disk = artifact.sha256_file(os.path.join(root, producer_rel))
            same = on_disk == recorded_hash
            leg = {
                "asked": True, "answered": True, "holds": same,
                "producer": producer_rel,
                "recorded_sha256": recorded_hash[:12],
                "on_disk_sha256": on_disk[:12],
            }
            record["legs"]["producer_hash_matches_disk"] = leg
            if not same:
                # Asked of the provenance gate, which owns this question, rather than
                # by reading the certificate file here. The lookup is bound to the PAIR
                # of hashes, so a producer edited again voids it without anyone acting.
                certificate = _prov.neutral_certificate(
                    root, rel, recorded_hash, on_disk)
                if certificate:
                    leg["excused_by_certificate"] = certificate
                    record["why"].append(
                        f"the run recorded here used {producer_rel} at "
                        f"{recorded_hash[:12]} and the file on disk is "
                        f"{on_disk[:12]}, so this file was NOT written by the bytes "
                        f"that are there now; checks/NEUTRAL_EDITS.json certifies "
                        f"that this exact pair of hashes cannot have moved a figure "
                        f"in it, which is a proof about the edit and not a record of "
                        f"a run")
                else:
                    record["why"].append(
                        f"the run recorded here used {producer_rel} at "
                        f"{recorded_hash[:12]}, and the file on disk is "
                        f"{on_disk[:12]}: whatever wrote this file is not the code "
                        f"that is there now")

    # THE DECLARED KIND IS READ HERE, BEFORE ANY VERDICT IS SETTLED, AND IT EXCUSES
    # THE SAME ONE LEG THE CERTIFICATE DOES. Until 2026-08-29 the kind was consulted
    # in the LAST branch of the chain below, after `if failed`, and a declared kind
    # can only matter when a leg has fallen -- so on every file the question was
    # actually about, the branch was unreachable and the file read did_not_run. The
    # two guards of this tree then answered one question two ways: the provenance gate
    # sets a run journal aside, this module called it a run that never happened.
    # Measured the same day on a fabricated journal whose producer hash was moved by
    # one digit: judge() returned did_not_run while _prov.UNANSWERABLE_BY_KIND held
    # the word. The pair of cases in _selftest() below is that measurement, kept.
    #
    # WHY THE FIX IS PER-LEG AND NOT A REORDERING OF THE CHAIN. Moving the kind branch
    # bodily above `if failed` would excuse leg one as well, and leg one is the leg
    # that asks whether anything ran at all. A journal whose finish time is older than
    # the reference moment did not run, whatever kind it declares. That is the same
    # asymmetry CERTIFICATE_EXCUSES states two screens up, and it is stated once more
    # here because an error that excuses a leg points at success, which is the
    # direction that travels.
    kind = meta.get(_prov.KIND_FIELD) if isinstance(meta, dict) else None
    excusing_kind = kind if kind in _prov.UNANSWERABLE_BY_KIND else None
    hash_leg = record["legs"].get(KIND_EXCUSES) or {}
    if (excusing_kind and hash_leg.get("answered")
            and hash_leg.get("holds") is False):
        hash_leg["excused_by_kind"] = excusing_kind
        record["record_kind"] = excusing_kind
        record["why"].append(
            f"declares record_kind={excusing_kind!r}: "
            f"{_prov.UNANSWERABLE_BY_KIND[excusing_kind]}. The producer-hash leg is "
            f"therefore SET ASIDE for this file rather than counted as a run that "
            f"did not happen; whether anything ran is a separate question and keeps "
            f"its own answer")

    asked = [leg for leg in record["legs"].values() if leg.get("asked")]
    answered = [leg for leg in asked if leg.get("answered")]
    fell = [leg for leg in answered if leg.get("holds") is False]
    # Three buckets out of one, and the order of the tests is the precedence. A kind
    # says the question has no answer for this file at all; a certificate says this
    # particular pair of hashes cannot have moved a figure. The first is the wider
    # statement, so it is read first where a file carries both. No file in this tree
    # carries both today -- checks/NEUTRAL_EDITS.json REFUSES to certify the one run
    # journal and gives the kind as its reason -- and the precedence is written down
    # anyway, because a rule left to the day it is needed is a rule nobody decided.
    excused_by_kind = [leg for leg in fell if leg.get("excused_by_kind")]
    excused = [leg for leg in fell
               if leg.get("excused_by_certificate") and not leg.get("excused_by_kind")]
    failed = [leg for leg in fell
              if not leg.get("excused_by_certificate")
              and not leg.get("excused_by_kind")]
    if failed:
        record["verdict"] = DID_NOT_RUN
    elif excused_by_kind:
        record["verdict"] = KIND_NOT_ANSWERABLE
    elif excused:
        record["verdict"] = NEUTRAL_BY_CERTIFICATE
    elif len(answered) == len(asked) and answered:
        record["verdict"] = RAN
    elif excusing_kind:
        # The kind reached in the other way: not a leg that fell, but a leg that could
        # never be put. checks/NEUTRAL_EDITS.json is written by a person and names no
        # producer at all, so nothing here fails and nothing here answers. The file
        # states what kind of record it is, and this gate reads the meaning of that
        # word out of the provenance gate's vocabulary rather than deciding it here. A
        # kind the vocabulary does not hold is judged exactly as before.
        record["verdict"] = KIND_NOT_ANSWERABLE
        record["record_kind"] = excusing_kind
        record["why"].append(
            f"declares record_kind={excusing_kind!r}: "
            f"{_prov.UNANSWERABLE_BY_KIND[excusing_kind]}")
    else:
        record["verdict"] = UNANSWERABLE
    return record


# =====================================================================
# THE CALIBRATION: TWO OPPOSITE CASES FOR THE DECLARED KIND
# =====================================================================

_FIXTURE_PRODUCER = "# a stand-in producer for the calibration of run_record\n"

# The vocabulary this module reads is the provenance gate's, so the firing half has to
# use a word that gate does NOT hold. Written here as a constant rather than inline, so
# that the day the vocabulary grows this word can be checked against it by program.
_A_WORD_THE_VOCABULARY_DOES_NOT_HOLD = "a_computed_quantity"


def _self_test_fixture(work, name, kind, recorded_hash, finished_utc):
    """One results file on disk, differing from its neighbours in one field.

    Written to a scratch directory and never to the tree. The producer named is a real
    file with real bytes, so the hash leg is answered by the same code path a live
    artifact takes rather than by a stub: what is fabricated here is the artifact, not
    the comparison.
    """
    # The self-description says the same thing in every fixture, deliberately. The
    # file name on disk has to differ so four of them can sit in one directory, and if
    # that name were copied in here the arms of the pair would differ in two fields
    # instead of one. The axis check at the end of _selftest() caught exactly that when
    # this function was first written, which is the pair earning its keep before it
    # had judged anything.
    meta = {"artifact_meta_version": artifact.SHAPE_VERSION,
            "results_file": "a_calibration_fixture.json",
            "producer": {"script": "fixture_producer.py",
                         "sha256": recorded_hash},
            artifact.VOLATILE_KEY: {"finished_utc": finished_utc}}
    if kind is not None:
        meta[_prov.KIND_FIELD] = kind
        meta[_prov.KIND_WHY_FIELD] = ("written by this calibration, so the printed "
                                      "reason is exercised as well")
    path = os.path.join(work, name)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({artifact.META_KEY: meta, "value": 1}, handle)
    return path


def _selftest():
    """Whether the declared-kind exemption fires where it must and stays silent where
    it must not. Returns (assertions, failures).

    WHY THIS PAIR AND NOT ONE CASE. Until 2026-08-29 the kind was consulted only after
    the chain had already returned did_not_run, so it could not reach any file whose
    hash leg had actually fallen -- which is every file the exemption exists for. That
    defect was invisible to the tree for as long as it stood, because nothing here ever
    asked the module to demonstrate that the exemption could fire. A single case would
    not have caught it either way round: a case that only fires cannot tell an
    exemption that works from one that excuses everything, and a case that only stays
    silent cannot tell a working exemption from a dead one.

    So four arms, and each names what it must do. Two of them differ in the declared
    word and in nothing else, measured field by field, because a pair whose halves
    differ in two things measures neither.

    Nothing here touches the tree. Both fixtures live in a scratch directory that is
    removed on the way out, and the producer they name is written there too.
    """
    asserted, failures = 0, []

    def expect(label, holds, saw):
        nonlocal asserted
        asserted += 1
        if not holds:
            failures.append(f"{label} -- {saw}")

    work = tempfile.mkdtemp(prefix="run_record_calibration_")
    try:
        producer = os.path.join(work, "fixture_producer.py")
        with open(producer, "w", encoding="utf-8") as handle:
            handle.write(_FIXTURE_PRODUCER)
        on_disk = artifact.sha256_file(producer)
        moved = ("0" if on_disk[0] != "0" else "1") + on_disk[1:]
        scripts = {"fixture_producer.py": "fixture_producer.py"}
        finished = "2026-08-29T12:00:00Z"
        later = parse_moment("2026-08-29T18:00:00Z")

        _self_test_fixture(work, "journal.json", "run_journal", moved, finished)
        _self_test_fixture(work, "plain.json", None, moved, finished)
        _self_test_fixture(work, "invented.json", _A_WORD_THE_VOCABULARY_DOES_NOT_HOLD,
                 moved, finished)
        _self_test_fixture(work, "healthy.json", "run_journal", on_disk, finished)

        journal = judge("journal.json", work, scripts)
        plain = judge("plain.json", work, scripts)
        invented = judge("invented.json", work, scripts)
        healthy = judge("healthy.json", work, scripts)
        journal_late = judge("journal.json", work, scripts, reference=later)

        expect("MUST SET THE FILE ASIDE: a run journal whose producer hash has moved "
               "is not a run that did not happen",
               journal["verdict"] == KIND_NOT_ANSWERABLE,
               f"gave {journal['verdict']}; this is the arm that was unreachable "
               f"before 2026-08-29, and an exemption nobody has seen fire is not "
               f"evidence that it fires")
        expect("MUST FIRE: the same file without the declared word still reads "
               "did_not_run",
               plain["verdict"] == DID_NOT_RUN,
               f"gave {plain['verdict']}; if this arm goes quiet the exemption is "
               f"excusing every file rather than the declared one")
        expect("MUST FIRE: a file cannot excuse itself by inventing a word the "
               "vocabulary does not hold",
               invented["verdict"] == DID_NOT_RUN,
               f"gave {invented['verdict']} on record_kind="
               f"{_A_WORD_THE_VOCABULARY_DOES_NOT_HOLD!r}")
        expect("MUST FIRE ANYWAY: a declared kind excuses the producer-hash leg and "
               "never the question whether anything ran",
               journal_late["verdict"] == DID_NOT_RUN,
               f"gave {journal_late['verdict']} for a journal that finished "
               f"{finished}, hours BEFORE the reference moment; the kind is a "
               f"statement about a hash and says nothing about a run")
        expect("MUST STAY SILENT: the declared kind does not downgrade a file whose "
               "hash matches the bytes on disk",
               healthy["verdict"] == RAN,
               f"gave {healthy['verdict']} for a journal written by the producer that "
               f"is there now")

        # The axis, measured rather than assumed. The two halves of the pair above are
        # a contrast, and a contrast whose arms differ in more than one thing measures
        # none of them. Read out of the files as they were written, so an edit to
        # _self_test_fixture that moves a second field is caught here and not by a reader.
        left = artifact.read_meta(os.path.join(work, "journal.json"))
        right = artifact.read_meta(os.path.join(work, "plain.json"))
        axis = {_prov.KIND_FIELD, _prov.KIND_WHY_FIELD}
        moved_fields = {key for key in set(left) | set(right)
                        if left.get(key) != right.get(key)}
        expect("the two halves of the pair differ in the declared kind and in nothing "
               "else",
               moved_fields == axis,
               f"they differ in {sorted(moved_fields)}, expected {sorted(axis)}")
        expect("both halves really did fail the producer-hash leg, so the pair is "
               "about the exemption and not about a hash that happened to match",
               all(r["legs"][KIND_EXCUSES].get("holds") is False
                   for r in (journal, plain, invented)),
               "one of the three fixtures matched the producer on disk")
    finally:
        _prov._NEUTRAL_CACHE.pop(
            os.path.join(work, "checks", "NEUTRAL_EDITS.json"), None)
        shutil.rmtree(work, ignore_errors=True)
    return asserted, failures


def sweep(root, names=None, reference=None):
    """Judge every tracked results file, or the named ones. Returns (records, dropped).

    The population is the provenance gate's, which is the .gitignore predicate asked
    of every .json in the tree. `dropped` is what that predicate left out and why, so
    a count here can never be read as a count of the whole tree.
    """
    # THE CALIBRATION RUNS HERE, ON EVERY SWEEP, RATHER THAN BEHIND A FLAG. A
    # comparator nobody has seen fire is not evidence that there is nothing to find,
    # and this module carried an exemption that could not fire for two weeks without
    # anything noticing. checks/chk_run_happened.py keeps a calibration of its own
    # behind --self-test, which the battery does not pass, so a flag here would have
    # been the same silence again.
    #
    # WHAT THIS DOES NOT COVER, said plainly rather than left to be assumed. skip_rule
    # and build.py call judge() directly and never reach this line, so the pair below
    # runs once per sweep of the tree and not once per node of a build.
    asserted, failures = _selftest()
    if failures:
        raise SystemExit(
            "[run-record] the declared-kind exemption is not calibrated: "
            + f"{len(failures)} of {asserted} assertions do not hold. Until this "
            + "passes no count below means anything.\n    "
            + "\n    ".join(failures))
    print(f"  {asserted} of {asserted} calibration assertions hold: the declared-kind "
          f"exemption fires on a moved hash and stays silent on a matching one")

    kept, dropped = _prov.population(root)
    if names:
        wanted = {os.path.basename(n) for n in names}
        missing = wanted - {os.path.basename(k) for k in kept}
        if missing:
            raise SystemExit(
                f"[run-record] not a tracked results file in this tree: "
                f"{', '.join(sorted(missing))}")
        kept = [k for k in kept if os.path.basename(k) in wanted]
    scripts = script_index(root)
    return [judge(rel, root, scripts, reference) for rel in kept], dropped


# =====================================================================
# WHAT THE TWO LEGS CANNOT SEE, COUNTED
# =====================================================================

_STDLIB_OR_VENDOR = frozenset((
    "argparse", "ast", "collections", "contextlib", "csv", "datetime", "fnmatch",
    "functools", "glob", "gzip", "hashlib", "importlib", "io", "itertools", "json",
    "math", "os", "pathlib", "platform", "random", "re", "shutil", "subprocess",
    "sys", "tempfile", "time", "types", "typing", "urllib", "warnings", "zipfile",
    "numpy", "np", "pandas", "scipy", "sklearn", "statsmodels", "matplotlib",
    "boto3", "botocore",
))


def _imports_of(path):
    """Head module names a file imports, from its syntax tree."""
    try:
        with open(path, encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
    except (OSError, SyntaxError):
        return set()
    heads = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            heads.update((alias.name or "").split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            heads.add((node.module or "").split(".")[0])
    return {h for h in heads if h and h not in _STDLIB_OR_VENDOR}


def import_closure(rel, root, tracked):
    """Every tracked .py this producer reaches through import, transitively.

    The point of the number. The producer hash proves one file's bytes. The code that
    made the numbers is this whole set, and no hash in the artifact covers any member
    of it but the first, so an edit to a shared module moves the figures and moves
    neither leg of this guard.
    """
    seen, queue = set(), [rel]
    while queue:
        current = queue.pop()
        for head in _imports_of(os.path.join(root, current)):
            target = tracked.get(f"{head}.py")
            if target and target not in seen and target != rel:
                seen.add(target)
                queue.append(target)
    return sorted(seen)


def blindness(root, records):
    """What this guard does not see, as numbers rather than as a caveat.

    Four things, and the third is the one that decides how much a green run is worth.
    """
    tracked = script_index(root)
    answerable = [r for r in records if r["verdict"] != UNANSWERABLE]
    no_finish = [r["artifact"] for r in records
                 if not (r["legs"].get("finished_after_reference") or {})
                 .get("recorded_finish_utc")]
    no_hash = [r["artifact"] for r in records
               if not (r["legs"].get("producer_hash_matches_disk") or {})
               .get("recorded_sha256")]

    # Files in the tree that no run record can reach, because their format has no
    # place to put one. Counted with the same .gitignore predicate as the artifacts.
    rules = _prov.ignore_patterns(root)
    unrecordable = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ("__pycache__", ".git")]
        for name in filenames:
            if not name.endswith((".npz", ".png", ".csv", ".parquet")):
                continue
            rel = os.path.relpath(os.path.join(dirpath, name),
                                  root).replace(os.sep, "/")
            if not _prov.is_ignored(rel, rules):
                unrecordable.append(rel)

    reach, worst = {}, (None, 0)
    for record in records:
        producer = (record["legs"].get("producer_hash_matches_disk") or {}).get(
            "producer")
        if not producer:
            continue
        closure = import_closure(producer, root, tracked)
        reach[record["artifact"]] = len(closure)
        if len(closure) > worst[1]:
            worst = (record["artifact"], len(closure))

    # How many artifacts one shared module reaches. settings.py is the module every
    # producer in this tree reads its declared numbers from, so it is the honest worst
    # case rather than an invented one.
    shared = {}
    for record in records:
        producer = (record["legs"].get("producer_hash_matches_disk") or {}).get(
            "producer")
        if not producer:
            continue
        for member in import_closure(producer, root, tracked):
            shared.setdefault(member, []).append(record["artifact"])

    return {
        "population_examined": len(records),
        "verdict_could_be_reached_for": len(answerable),
        "no_finish_time_recorded": {"count": len(no_finish),
                                    "files": sorted(no_finish)[:12]},
        "no_producer_hash_recorded": {"count": len(no_hash),
                                      "files": sorted(no_hash)[:12]},
        "outside_the_range_entirely": {
            "count": len(unrecordable),
            "why": "an .npz, .png, .csv or .parquet has nowhere to carry a _meta "
                   "block, so neither leg exists for it and this guard reports "
                   "nothing about it at all",
            "files": sorted(unrecordable)[:12],
        },
        "reference_resolution_s": FINISH_RESOLUTION_S,
        "reference_resolution_note":
            f"finished_utc is written to whole seconds, so a run that ended inside "
            f"the same second as the reference moment cannot be told from one that "
            f"ended before it; the guard's time discrimination is "
            f"{FINISH_RESOLUTION_S} s and no finer",
        "hash_covers_one_file_of": {
            "median_modules_behind_an_artifact":
                sorted(reach.values())[len(reach) // 2] if reach else 0,
            "widest": {"artifact": worst[0], "modules": worst[1]},
            "top_shared_modules": sorted(
                ({"module": m, "artifacts_it_reaches": len(v)}
                 for m, v in shared.items()),
                key=lambda d: -d["artifacts_it_reaches"])[:6],
            "why": "the producer hash covers the producer's own bytes. Every other "
                   "module in that closure can be edited, move every number, and "
                   "leave both legs of this guard holding",
        },
        "what_a_pass_still_permits":
            "a producer that reads a cache and rewrites its own artifact satisfies "
            "both legs; this guard proves a run occurred, never that a quantity was "
            "recomputed",
    }


# =====================================================================
# THE CONTRACT, IN THE SHAPE checks/evidence.py PRINTS
# =====================================================================

def contract(records, reference):
    """One sub-check per artifact, so a failure names the file it is about.

    `refuted` is a run that demonstrably did not happen. `uncertain` is an artifact
    that records too little to be asked, which is a fact about the file and not about
    the run, and evidence.py prints it under a heading that says the question was not
    answered.
    """
    reference_text = as_utc(reference) if reference is not None else None
    subs = []
    for record in records:
        legs = record["legs"]
        finish = legs.get("finished_after_reference") or {}
        hashes = legs.get("producer_hash_matches_disk") or {}
        if reference_text:
            expectation = (
                f"a recompute launched at {reference_text} leaves this file with a "
                f"finish time later than that moment, and with the producer hash of "
                f"{record.get('producer') or 'the script that wrote it'} as it "
                f"stands on disk")
        else:
            expectation = (
                f"this file still carries the producer hash of "
                f"{record.get('producer') or 'the script that wrote it'} as it "
                f"stands on disk. NO reference moment was given, so whether any run "
                f"happened was NOT ASKED")
        # Five verdicts into the contract's three words, and each mapping is a decision
        # rather than a convenience. A certified artifact goes to `confirmed` because
        # nothing about it is unresolved -- the difference is proven unable to reach a
        # figure -- and its note says in full that the file was not written by today's
        # bytes, so the word never stands alone. A declared kind goes to `uncertain`
        # and is then named to report_contract as informational, which is that
        # function's own device for an uncertain that is by design: the exemption
        # appears on the screen by name instead of becoming an invisible default.
        verdict = {RAN: "confirmed", DID_NOT_RUN: "refuted",
                   UNANSWERABLE: "uncertain",
                   NEUTRAL_BY_CERTIFICATE: "confirmed",
                   KIND_NOT_ANSWERABLE: "uncertain"}[record["verdict"]]
        subs.append({
            "name": os.path.basename(record["artifact"]),
            "assumption": expectation,
            "method": (f"_meta.{artifact.VOLATILE_KEY}.finished_utc against the "
                       f"reference moment; _meta.producer.sha256 against sha256 of "
                       f"the producer found in the tree by basename"),
            "observed": {
                "recorded_finish_utc": finish.get("recorded_finish_utc"),
                "reference_utc": reference_text,
                "seconds_after_reference": finish.get("seconds_after_reference"),
                "producer": hashes.get("producer") or record.get("producer"),
                "recorded_sha256": hashes.get("recorded_sha256"),
                "on_disk_sha256": hashes.get("on_disk_sha256"),
            },
            "verdict": verdict,
            "note": " ".join(record["why"]) or (
                "both legs hold: a process wrote this file after the reference "
                "moment using the producer bytes that are on disk now"),
        })
    informational = [os.path.basename(r["artifact"]) for r in records
                     if r["verdict"] == KIND_NOT_ANSWERABLE]
    worst = ("refuted" if any(s["verdict"] == "refuted" for s in subs)
             else "uncertain" if any(s["verdict"] == "uncertain"
                                     and s["name"] not in informational
                                     for s in subs)
             or reference is None else "confirmed")
    return {"check": "run_happened", "checks": subs, "overall_verdict": worst,
            "informational": informational}


if __name__ == "__main__":
    # The module is a library and has no results file of its own. It is runnable all
    # the same, because the pair above is the one thing in it a reader may want to see
    # fire without running the whole gate that imports it.
    _asserted, _failures = _selftest()
    print(f"  {_asserted - len(_failures)} of {_asserted} calibration assertions hold")
    for _label in _failures:
        print(f"    FAILED: {_label}")
    sys.exit(1 if _failures else 0)
