#!/usr/bin/env python3
"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-08-21
References: none (repository provenance gate).

THE CODE THAT WROTE A RESULTS FILE MUST STILL EXIST SOMEWHERE.

Why this gate exists, and why it is not the freshness gate. Every results file in this
tree records the sha256 of the script that wrote it. chk_artifact_provenance compares
that recorded hash with the script as it stands on disk and reports the two apart when
the producer has been edited since the run. That comparison is a DISTANCE, and a
distance is readable: both ends exist, the difference is a diff, and a reader can look
at it and decide whether the edit touched a number.

This gate asks a different question, and it is the question that has no diff. Does the
recorded hash correspond to any bytes that still exist at all? A producer edited and
then overwritten before it was ever saved leaves a results file pointing at a version
of the code that exists nowhere: not in the working tree, not in any commit, not in a
dangling object. One end of the distance is missing, so no comparison is possible in
principle, and the freshness gate reports the two apart without being able to say that
the far end is gone. The remedy is also different. A readable distance is settled by
reading the diff. An absent end can only be settled by running the producer again.

What was measured on 2026-08-21. Ninety-nine tracked results files record a producer
hash. Ninety-five of those hashes resolve to bytes this repository still holds. Four do
not, and all four finished within five minutes of each other on 2026-08-11, while the
directory layout was being rearranged: the nodes ran on edited code, and those exact
bytes were replaced before anything was saved. Nothing in the tree noticed for ten days.

HOW A HASH IS RESOLVED, AND WHY THE OBVIOUS QUESTION IS THE WRONG ONE. A recorded
producer hash is sha256 of the script's bytes -- artifact.write computes it with
sha256_file and nothing else. That is not how Git names an object under either object
format. Git names a blob by hashing a header and the content together, so a plain
content sha256 is not an object name even in a repository whose object format is
sha256, and this repository's object format is sha1 besides. Asking `git cat-file -e`
for a recorded producer hash therefore fails for every artifact in the tree, including
the ninety-five that are perfectly sound -- a predicate that answers "missing" for
everything, which is the shape of a false alarm that never stops.

So the method is not assumed, it is PROBED at run time and the probe is printed. The
gate takes a file it knows the object database holds, computes the same content sha256
artifact.write would compute for it, and asks `git cat-file -e` about it. If Git
answers yes, the recorded hashes are object names and can be resolved that way. If Git
answers no -- which is what happens here -- the gate resolves by CONTENT instead: it
reads every blob in the object database once and indexes it by the sha256 of its bytes.
That census covers reachable and dangling objects alike, which matters, because a
producer version committed once and then rewritten survives as a dangling object and is
recoverable; the four found here are not even that.

DEGRADING HONESTLY. A stranger may unpack this repository from a source archive with no
.git directory at all. There is then no object database to ask, and the honest answer is
that the question cannot be put -- not that everything passed. In that case the gate
prints what it could not do, records a verdict of NOT_ANSWERABLE and exits zero. The
population it walks comes from the shared shipped-tree census either way.

CALIBRATION, and why the live defect is not what calibrates it. Two of the three cases
are built from a producer that is committed in this repository right now, so they are
real files of real code rather than an invented example. One must stay silent: the
sha256 of that producer's committed bytes, which the object database holds by
construction. One must fire: the same producer's bytes with a single byte appended,
which is exactly the shape of the disease -- genuine code, edited, never saved -- and
which no object database can hold. The third must fire on a hash of nothing.

The four live findings are deliberately NOT a calibration case. They are being
recomputed, and a case anchored on a defect passes only until the defect is repaired,
after which it silently proves nothing. The appended-byte case keeps firing forever.

THE DECLARED DEBT NAMES BOTH THE COUNT AND THE FILES, AND TODAY IT IS EMPTY. BASELINE
below excuses an artifact by path AND by recorded hash together, never by a bare count.
Naming only a count would let a fifth artifact take a repaired one's place under an
unchanged ceiling; naming the pair means an excuse retires itself, because recomputing
an artifact changes the hash it records and the pair stops matching. The four found on
2026-08-21 were recomputed that same day and all 99 producer hashes then resolved, so
the debt is nil and the ceiling is zero. Any artifact not named there fails at once.

Read-only. Exits non-zero on a finding outside the baseline, and names file and reason.

    uv run --no-project --with-requirements requirements.txt python3 \
        checks/chk_producer_committed.py
"""
import hashlib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
import artifact                                                         # noqa: E402
import chk_artifact_provenance as _prov                                 # noqa: E402
from evidence import report_gate, shipped_tree_files                    # noqa: E402

OUT_JSON = os.path.join(HERE, "chk_producer_committed_results.json")
SELF_OUTPUT = "checks/" + os.path.basename(OUT_JSON)

# THE DEBT IS EMPTY, AND IT IS EMPTY BECAUSE IT WAS PAID, NOT BECAUSE IT WAS WAIVED.
#
# Four artifacts carried this defect on 2026-08-21 and are named in the docstring above.
# All four were recomputed the same day. Measured after the recompute: 99 of 99 shipped
# results files record a producer hash that resolves, so the count this gate is holding
# down is zero and its ceiling is zero.
#
# Leaving a ceiling of four standing after the four were repaired is the reason this
# constant is a mapping and not a number. A ceiling is a statement about SIZE, and a
# ceiling four above the truth admits four fresh breakages without a word -- exactly the
# silence this gate was written to end. Naming path and recorded hash together makes the
# excuse retire itself: recompute an artifact and the hash it records changes, the pair
# stops matching, and the entry is reported as spent and meant to be deleted. That is
# what happened here, within hours of the debt being written down.
#
# An entry belongs here only when repair has to wait, and it carries the date and the
# reason it waits. Anything not named here fails this gate at once.
BASELINE = {}

# THE HISTORY THIS REPOSITORY STARTS WITH IS NOT THE HISTORY ITS ARTIFACTS WERE WRITTEN
# IN, AND THAT IS DECLARED RATHER THAN PERMITTED BY A CEILING. The open repository begins
# at its own first commit; the commits the earlier artifacts were computed under are not
# shipped. Measured on that first commit: 61 results files record a producer hash this
# object database cannot resolve, because the version that wrote them lived only in the
# history that was left behind. A ceiling of 61 would admit a 62nd silently. Instead one
# declared category is asked of each such file: the recorded hash is the FROM side of a
# live certificate in checks/NEUTRAL_EDITS.json, and the TO side of that certificate is
# the producer on disk. Then the link between the bytes that ran and the bytes that ship
# is proved by the certificate's own comparator, and the file is printed on its own line,
# neither as a pass nor as a failure. Without such a certificate it fails as before. The
# certificate is looked up by CALLING chk_artifact_provenance.neutral_certificate, the
# one home of that rule, never by reading the register here a second time.
PRIOR_HISTORY_RULE = "PRODUCER-IN-UNSHIPPED-HISTORY-CERTIFIED"
PRIOR_HISTORY_WORDS = ("the prior history is not shipped; the link from the recorded "
                       "producer to the one on disk is certified")


def certified_link(root, rel, recorded, live):
    """The certificate tying a recorded producer hash to the bytes on disk, or None."""
    if not live:
        return None
    return _prov.neutral_certificate(root, rel, recorded, live)


# A recorded producer hash is 64 hex characters. Anything else is a different record and
# is reported as unreadable rather than silently skipped.
HASH_LENGTH = 64


def git_root():
    """This repository's own top level, or None when there is no repository here.

    Resolved the way evidence.shipped_tree_files resolves it: a checkout counts only
    when Git's top level IS this tree. An extracted archive dropped inside some other
    repository would otherwise borrow that repository's object database and be told its
    producers are fine on the strength of somebody else's history.
    """
    try:
        probe = subprocess.run(["git", "-C", ROOT, "rev-parse", "--show-toplevel"],
                               capture_output=True, text=True, check=False)
    except OSError:
        return None
    if probe.returncode != 0:
        return None
    top = os.path.realpath(probe.stdout.strip())
    return top if top == os.path.realpath(ROOT) else None


def object_format(root):
    """The name Git gives this repository's object format, or "unknown"."""
    probe = subprocess.run(["git", "-C", root, "rev-parse", "--show-object-format"],
                           capture_output=True, text=True, check=False)
    return probe.stdout.strip() if probe.returncode == 0 else "unknown"


def blob_names(root):
    """Every blob object name in the database, reachable and dangling alike."""
    listed = subprocess.run(
        ["git", "-C", root, "cat-file", "--batch-all-objects",
         "--batch-check=%(objectname) %(objecttype)"],
        capture_output=True, text=True, check=True).stdout
    return [line.split()[0] for line in listed.splitlines()
            if line.endswith(" blob")]


def content_index(root, names):
    """content sha256 -> one object name holding those bytes, for every blob given.

    The whole database is streamed through a single `cat-file --batch`, because asking
    Git once per object would start a process per blob and the count here is in the
    thousands.
    """
    if not names:
        return {}
    proc = subprocess.run(["git", "-C", root, "cat-file", "--batch"],
                          input="\n".join(names).encode(),
                          capture_output=True, check=True)
    buf, cursor, index = proc.stdout, 0, {}
    while cursor < len(buf):
        end = buf.find(b"\n", cursor)
        if end < 0:
            break
        header = buf[cursor:end].decode(errors="replace").split()
        if len(header) != 3:
            break
        name, size = header[0], int(header[2])
        body = buf[end + 1:end + 1 + size]
        index.setdefault(hashlib.sha256(body).hexdigest(), name)
        cursor = end + 1 + size + 1
    return index


def committed_bytes(root, rel):
    """The bytes of *rel* as the current commit holds them, or None."""
    proc = subprocess.run(["git", "-C", root, "show", f"HEAD:{rel}"],
                          capture_output=True, check=False)
    return proc.stdout if proc.returncode == 0 else None


def probe_method(root, index):
    """Whether `git cat-file -e` answers the question the recorded hashes ask.

    Measured, never assumed. A content sha256 known to be in the database is put to
    `git cat-file -e`. Answering yes would mean recorded hashes are object names;
    answering no means they are not, and resolution has to go by content.

    Returns (method, sentence). The sentence is printed, so a reader is told which of
    the two ways the count in front of them was taken.
    """
    if not index:
        return "content-census", ("no blob was readable, so the probe could not be "
                                  "run and resolution fell back to content")
    known = next(iter(index))
    answered = subprocess.run(["git", "-C", root, "cat-file", "-e", known],
                              capture_output=True, check=False).returncode == 0
    if answered:
        return "cat-file", (f"`git cat-file -e` resolved {known[:12]}..., a content "
                            f"sha256 this database holds, so recorded hashes are "
                            f"object names and are resolved that way")
    return "content-census", (
        f"`git cat-file -e` refused {known[:12]}..., a content sha256 this database "
        f"demonstrably holds, so a recorded hash is not an object name here; every "
        f"blob was read once and indexed by the sha256 of its bytes instead")


def resolves(digest, root, index, method):
    """Whether bytes hashing to *digest* still exist in the object database."""
    if method == "cat-file":
        return subprocess.run(["git", "-C", root, "cat-file", "-e", digest],
                              capture_output=True, check=False).returncode == 0
    return digest in index


def producer_record(document):
    """The producer block of a loaded results file, under any spelling it has used."""
    meta = document.get("_meta")
    if not isinstance(meta, dict):
        return None
    for key in ("producer",) + tuple(artifact.LEGACY_SPELLINGS.get("producer", ())):
        block = meta.get(key)
        if isinstance(block, dict):
            return block
    return None


def artifacts(root):
    """(repo-relative path, producer block) for every shipped results file that has one.

    The population is stated as what was walked and what carried a hash, so that a zero
    here can be told apart from a walk that found nothing to look at.
    """
    found, walked = [], 0
    for rel in shipped_tree_files(root):
        if not rel.endswith(".json") or rel == SELF_OUTPUT:
            continue
        walked += 1
        try:
            with open(os.path.join(root, rel), encoding="utf-8") as fh:
                document = json.load(fh)
        except (OSError, ValueError):
            continue
        if not isinstance(document, dict):
            continue
        block = producer_record(document)
        if block and isinstance(block.get("sha256"), str):
            found.append((rel, block))
    return found, walked


def on_disk_sha256(root, script_name):
    """sha256 of the producer of that basename in the working tree, or None.

    A basename occurring twice returns None rather than whichever copy the walk met
    first: attributing an artifact to the wrong copy would make the report confidently
    wrong about whether the bytes are recoverable, and the difference decides whether
    the repair is a save or a rerun.
    """
    hits = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ("__pycache__", ".git")]
        if script_name in filenames:
            hits.append(os.path.join(dirpath, script_name))
    if len(hits) != 1:
        return None
    try:
        return artifact.sha256_file(hits[0])
    except OSError:
        return None


def calibrate(root, index, method):
    """Three cases against the live object database: one silent, two firing.

    The first two are built from a producer this repository has committed, so the
    fixture is real code and not a resemblance to it. The firing one is that same code
    with one byte added, which is precisely what an edited-and-overwritten producer
    looks like and which no database can ever hold. Neither depends on the four
    findings the tree carries today, so neither erases itself when they are repaired.
    """
    rows = []
    committed = None
    for candidate in sorted(r for r in shipped_tree_files(root) if r.endswith(".py")):
        body = committed_bytes(root, candidate)
        if body:
            committed, source = body, candidate
            break

    if committed is None:
        return [("a committed producer resolves",
                 "must stay silent: no committed script could be read, so neither "
                 "case below could be built and no zero from this gate is believable",
                 "unavailable", "resolves", False)]

    good = hashlib.sha256(committed).hexdigest()
    rows.append(("a committed producer resolves",
                 f"must stay silent: the committed bytes of {source}",
                 "resolves" if resolves(good, root, index, method) else "absent",
                 "resolves", resolves(good, root, index, method)))

    edited = hashlib.sha256(committed + b"\n#\n").hexdigest()
    rows.append(("an unsaved edit does not resolve",
                 f"must fire: the same bytes of {source} with one edit appended, "
                 f"which is the disease's own shape",
                 "resolves" if resolves(edited, root, index, method) else "absent",
                 "absent", not resolves(edited, root, index, method)))

    nothing = "0" * HASH_LENGTH
    rows.append(("a hash of nothing does not resolve",
                 "must fire: sixty-four zeros, which name no bytes at all",
                 "resolves" if resolves(nothing, root, index, method) else "absent",
                 "absent", not resolves(nothing, root, index, method)))

    # THE DECLARED CATEGORY, ON TWO OPPOSITE CASES TAKEN FROM THE LIVE REGISTER. The
    # first live certificate whose TO side is the producer on disk must be accepted for
    # its own FROM hash; the same artifact with one hex digit of that FROM hash changed
    # must not be, or the category would excuse any unresolvable hash at all.
    pair = None
    try:
        with open(os.path.join(root, "checks", "NEUTRAL_EDITS.json"),
                  encoding="utf-8") as fh:
            register = json.load(fh)
    except (OSError, ValueError):
        register = {}
    for entry in register.get("certified") or ():
        live = on_disk_sha256(root, os.path.basename(str(entry.get("producer") or "")))
        if live and live == entry.get("sha256_on_disk"):
            pair = (entry["artifact"], entry["sha256_recorded"], live)
            break
    if pair is None:
        rows.append(("a certified link is accepted",
                     "must stay silent: no live certificate names a producer whose TO "
                     "side is on disk, so neither case could be built",
                     "unavailable", "certified", False))
        return rows
    rel, recorded, live = pair
    got = certified_link(root, rel, recorded, live) is not None
    rows.append(("a certified link is accepted",
                 f"must stay silent: {rel} with the FROM hash its certificate names",
                 "certified" if got else "not certified", "certified", got))
    flipped = recorded[:-1] + ("0" if recorded[-1] != "0" else "1")
    got = certified_link(root, rel, flipped, live) is not None
    rows.append(("an uncertified hash is not accepted",
                 f"must fire: {rel} with one hex digit of that FROM hash changed",
                 "certified" if got else "not certified", "not certified", not got))
    return rows


def scan(root, index, method):
    """Findings, excused entries, spent baseline entries, and the population walked."""
    found, walked = artifacts(root)
    findings, excused, matched, certified = [], [], set(), []
    for rel, block in found:
        digest = block["sha256"]
        script = os.path.basename(str(block.get("script") or "")) or "unnamed"
        if len(digest) != HASH_LENGTH:
            findings.append({
                "file": rel, "line": 0, "rule": "PRODUCER-HASH-UNREADABLE",
                "detail": f"the recorded producer hash is {len(digest)} characters "
                          f"long, and a sha256 is {HASH_LENGTH}, so this record "
                          f"cannot be resolved either way",
                "source": digest[:32]})
            continue
        if resolves(digest, root, index, method):
            continue

        # Whether the bytes survive unsaved in the working tree decides the repair, so
        # the two cases are told apart rather than reported as one.
        live = on_disk_sha256(root, script)
        link = certified_link(root, rel, digest, live)
        if link is not None:
            certified.append({
                "file": rel, "line": 0, "rule": PRIOR_HISTORY_RULE,
                "detail": f"{PRIOR_HISTORY_WORDS}: {script} moved from "
                          f"{digest[:12]} to the bytes on disk {live[:12]}, and "
                          f"checks/NEUTRAL_EDITS.json certifies that pair for this "
                          f"artifact",
                "source": digest[:32] + "...",
                "certificate": link})
            continue
        if live == digest:
            where = (f"those bytes are in the working tree as {script} and have "
                     f"simply never been saved, so saving them repairs this")
        else:
            where = (f"those bytes are in no commit, no dangling object and not in "
                     f"{script} as it stands, so nothing can be compared against "
                     f"them and only running {script} again repairs this")
        entry = {
            "file": rel, "line": 0, "rule": "PRODUCER-NEVER-COMMITTED",
            "detail": f"this file was computed by a version of {script} whose bytes "
                      f"this repository does not hold: {where}",
            "source": digest[:32] + "..."}
        if BASELINE.get(rel) == digest:
            matched.add(rel)
            excused.append(entry)
        else:
            findings.append(entry)
    spent = sorted(set(BASELINE) - matched)
    return findings, excused, spent, walked, len(found), certified


def main():
    started = artifact.start_clock()
    root = git_root()

    print("=" * 76)
    print("  PRODUCER COMMITTED - the code that wrote a results file still exists")
    print("=" * 76)

    if root is None:
        print("  object database    : none. This tree is not a repository of its own,")
        print("                       so there is nothing to resolve a recorded hash")
        print("                       against and the question cannot be put here.")
        print("  files walked       : not counted, the walk would answer nothing")
        print("-" * 76)
        print("  VERDICT: NOT_ANSWERABLE")
        artifact.write(
            os.path.basename(OUT_JSON),
            {"verdict": "NOT_ANSWERABLE", "n_findings": 0, "findings": [],
             "why_not_answered": ("no Git object database accompanies this tree, so "
                                  "whether a recorded producer hash names bytes that "
                                  "still exist cannot be asked at all"),
             "calibration": []},
            script=__file__, inputs=[],
            scope={"population": "no population: the question was not put",
                   "window": "n/a: this gate reads the repository as it stands now",
                   "coins": "n/a: this gate reads file text and no market data"},
            started=started, answered=False,
            extra_meta={"resolution_method": "none",
                        "object_format": "unknown"})
        return 0

    fmt = object_format(root)
    names = blob_names(root)
    index = content_index(root, names)
    method, sentence = probe_method(root, index)
    cal = calibrate(root, index, method)
    cal_failed = [c for c in cal if not c[4]]
    findings, excused, spent, walked, carried, certified = scan(root, index, method)
    verdict = "PASS" if not findings and not cal_failed else "FAIL"

    print(f"  object format      : {fmt}")
    print(f"  resolution method  : {method}")
    print(f"                       {sentence}")
    print(f"  object database    : {len(names)} blobs, "
          f"{len(index)} distinct contents")
    print(f"  calibration cases  : {len(cal)}, failed {len(cal_failed)}")
    for name, what, got, want, ok in cal:
        print(f"  {'ok  ' if ok else 'FAIL'} {name}: {what}")
        if not ok:
            print(f"       expected {want!r}, got {got!r}")
    print(f"  population         : {walked} shipped .json files walked, "
          f"{carried} record a producer hash")
    print(f"  predicate          : the recorded _meta.producer.sha256 names bytes "
          f"the object database holds")
    print(f"  findings           : {len(findings)}")
    for f in findings:
        print(f"  {f['rule']:26} {f['file']}")
        print(f"      | {f['detail']}")
    print(f"  certified, prior history not shipped: {len(certified)} -- not a pass "
          f"and not a failure: {PRIOR_HISTORY_WORDS}")
    for f in certified:
        print(f"      ~ {f['file']}")
    print(f"  excused by baseline: {len(excused)} of {len(BASELINE)} declared")
    for f in excused:
        print(f"      - {f['file']}")
    if spent:
        print(f"  baseline entries spent: {len(spent)}, delete them from BASELINE")
        for rel in spent:
            print(f"      - {rel} no longer records the hash the debt names")
    print("-" * 76)
    print(f"  VERDICT: {verdict}")

    artifact.write(
        os.path.basename(OUT_JSON),
        {"verdict": verdict, "n_findings": len(findings), "findings": findings,
         "excused_by_baseline": excused,
         "certified_prior_history_not_shipped": certified,
         "baseline_entries_spent": spent,
         "calibration": [{"predicate": n, "case": w, "got": g, "want": x, "ok": ok}
                         for n, w, g, x, ok in cal]},
        script=__file__,
        # The population is the whole shipped tree rather than a named file, so it is
        # stated in scope; hashing every results file here would put the repository
        # inside its own artifact.
        inputs=[],
        scope={
            "population": f"{carried} shipped results files recording a producer "
                          f"hash, out of {walked} .json files walked",
            "window": "n/a: this gate reads the repository as it stands now, not a "
                      "period of market data",
            "coins": "n/a: this gate reads file text and touches no market data",
        },
        started=started,
        extra_meta={"object_format": fmt,
                    "resolution_method": method,
                    "resolution_probe": sentence,
                    "n_blobs": len(names),
                    "n_distinct_contents": len(index),
                    "n_json_walked": walked,
                    "n_with_producer_hash": carried,
                    "n_excused": len(excused),
                    "n_certified_prior_history": len(certified),
                    "n_baseline_declared": len(BASELINE),
                    "n_baseline_spent": len(spent),
                    "n_calibration_cases": len(cal),
                    "n_calibration_failed": len(cal_failed)},
    )

    if cal_failed:
        print("  CALIBRATION FAILED: no zero in this report can be believed.")
        return 2
    return report_gate(
        [{"name": "PRODUCER-NEVER-COMMITTED",
          "permitted": 0,
          "found": len(findings),
          "assumption": ("every results file this repository ships was written by a "
                         "version of its producer that this repository still holds. "
                         "When the recorded hash names bytes that exist nowhere, the "
                         "freshness comparison has only one end and cannot be made at "
                         "all, so the figure in the file stands on code nobody can "
                         "read, and the only repair is to run the producer again"),
          "method": ("_meta.producer.sha256 of every shipped results file, resolved "
                     f"against this repository's object database by {method}, the "
                     "method chosen by a live probe rather than assumed; calibrated "
                     "on three cases, two of them built from a committed producer of "
                     "this tree"),
          "note": ("run the named producer again so its results file records a "
                   "version of the code that exists; a diff cannot settle this, "
                   "because there is nothing at the far end to diff against"),
          "sites": findings},
         {"name": "PRODUCER-NEVER-COMMITTED-DEBT",
          "permitted": len(BASELINE),
          "found": len(excused),
          "assumption": ("the four artifacts of 2026-08-11 named in BASELINE are a "
                         "declared debt, carried by path and by recorded hash so that "
                         "an excuse retires itself when its artifact is recomputed"),
          "method": "path and recorded hash both equal to a BASELINE entry",
          "note": "recompute these four and delete their entries",
          "sites": excused},
         {"name": PRIOR_HISTORY_RULE,
          "permitted": None,
          "found": len(certified),
          "assumption": ("reported, not gated: " + PRIOR_HISTORY_WORDS + ". The "
                         "recorded hash is the FROM side of a live certificate in "
                         "checks/NEUTRAL_EDITS.json and its TO side is the producer on "
                         "disk"),
          "method": "chk_artifact_provenance.neutral_certificate, called",
          "note": "a real run of the producer retires the entry",
          "sites": certified}],
        OUT_JSON,
        inputs={"object database": f"{len(names)} blobs, resolved by {method}"})


if __name__ == "__main__":
    sys.exit(main())
