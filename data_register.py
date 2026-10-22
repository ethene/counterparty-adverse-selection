#!/usr/bin/env python3
"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-08-11

References: the data acquisition log beside the repository for every source named in the
recovery table below; Albers, Cucuringu, Howison and Shestopaloff, "An Open Book"
(Zenodo 18184441, CC-BY-4.0) for the public archive this pipeline parses.

THE REGISTER OF EVERY FILE THIS PIPELINE READS, LOOKED UP BY WHAT IT IS RATHER THAN BY
WHERE IT WAS LAST SEEN.

WHAT THIS IS FOR, IN THE READER'S TERMS FIRST. The report says the code reproduces. A
reader who wants to test that asks four questions about every file the code reads, and
until this module none of the four had a written answer: what is this file, where is it
now, which computations stand on it, and what does it cost to get it back if it is gone.
The four answers exist -- every results file in this tree already records the name, the
size and the sha256 of everything its producer read -- but they exist scattered across
scores of files, one artifact at a time, and nothing collected them. How many artifacts
that is on the tree of the day is counted in the output rather than written here, because
a number typed into a header is a cache of a count and this repository has already paid
for one of those.

WHY LOOKING UP BY PATH IS THE DEFECT AND NOT AN INCONVENIENCE. Between the morning and
the evening of 2026-08-08 five files were called missing and all five were whole,
somewhere else on the same disk. The mechanism was one mechanism each time: an instrument
asked "is there a file at this path", the answer was no, and no was reported as "the file
is gone". A file is not its path. A file is its bytes, the sha256 names those bytes, and
the record that says a producer read 46 870 849 bytes hashing to 57ccfc6f... is a
statement about the bytes and not about any directory. So this register resolves every
declared input BY HASH over a declared search area, and reports the path it found as an
observation rather than as the question. A file that moved is found and its new address
is printed. A file that is genuinely nowhere is the only thing this can call absent, and
when it says that it also says on what evidence.

THAT DEFECT HAS A TWIN AND IT COSTS MORE. Looking up by path can also say YES about the
wrong thing: a stale copy at the expected address answers "present" while the input the
artifact was computed from is a different file. The identity test catches that too, and
it is reported separately: `present_at_the_recorded_path` means the bytes at the address
hash to the recorded value, and a row that resolves off the recorded path while something
else sits at that address is printed with both.

THE FOUR ANSWERS, AND WHERE EACH COMES FROM.

  what it is        the input's name and the sha256 the producer recorded when it read
                    it. One name may carry two identities, and that is not an error: it
                    means the file was rebuilt between two runs, and both are kept,
                    because an artifact computed on the first stands on the first.
  where it is       the paths in the search area whose bytes hash to that identity.
                    Nothing here is inferred from a name.
  who reads it      every artifact whose _meta.inputs names it, the producer that wrote
                    that artifact, and the pipeline group run/_groups.py puts that
                    producer in, so the answer is in the same words as the entry points.
  what without it   a class from the table RECOVERY below, every entry of which cites the
                    acquisition log. Four outcomes are possible and they are not the same
                    outcome: a clone brings it back, this pipeline rebuilds it, a
                    download brings it back free, a download brings it back for money, or
                    nothing brings it back at all.

THE REVERSE SIDE, WHICH IS WHERE THE FINDING WAS. A register of what is declared answers
nothing about what is lying in the data directories WITHOUT being declared, and that is
the half that found something: four days of forward-recorded tape, believed lost with a
scratch directory, whole on disk and named by nobody. So the second half of this module
walks the six data directories and sorts every file into one of five buckets, four of
which are ways of being accounted for and the fifth of which is the finding.

WHY THE FILE IS SORTED INTO BUCKETS AND NOT INTO "DECLARED" AND "NOT". Because the
cheap two-way split produces a false finding, and this repository has already paid for
one: an hourly file under raw_fills_cache is named by no artifact, but the day directory
it sits in IS named, as the s3:// prefix the day was pulled from. Calling those 240 files
undeclared would be an instrument reporting its own coarseness as a shortage of records.
The buckets are therefore named after the evidence that accounts for the file, each
bucket is counted, and the fifth is the only one that says nobody claims this.

THE SEARCH AREA IS DECLARED, BECAUSE A SEARCH THAT FINDS NOTHING HAS TO SAY WHERE IT
LOOKED. Three areas, each printed with its file count and its size, each marked present
or absent:

  tree        this repository. Always present, because this file is inside it.
  data        ../02_data, whose six directories the acquisition log names as the
              home of data on this machine, and the log itself, which three artifacts
              declare as an input. Outside this repository by design -- raw days are
              gigabytes and a clone does not carry them -- so the path is built
              from this file's own location and never typed, and an absent data root is
              reported as an absent area rather than as a disk full of missing files.
              Walking only the six named directories was the first version and it called
              the acquisition log missing, which is this module's own defect made in the
              module written to remove it: a search that does not cover a file cannot
              say anything about that file.
  documents   the documents of the parent workspace that artifacts of this repository
              declare as inputs. They are DECLARED ONE BY ONE in WORKSPACE_DOCUMENTS
              below rather than found by walking the directory they sit in. In this
              repository the list is empty: the write-up drafts once named there are
              not published, and no path to them is kept in the code. The acquisition
              log is covered by the data area.

WHY THAT THIRD AREA IS A LIST AND NOT A WALK, WHICH IS THE ONE THING THIS MODULE HAS TWO
MODES FOR. The first version walked the whole workspace, and a walk answers a question
nobody asked of a register that ships with the code. It reports every file of the working
copy this repository happens to sit in, and what it reported was overwhelmingly copies
taken before a computation was repeated: files this pipeline does not read, sitting at
addresses that describe one disk rather than this work. A register whose readable half is
mostly such addresses has stopped being a register of what the pipeline reads. So the
shipped mode declares the documents it needs, resolves them by content like everything
else, and leaves the walk to a second mode for whoever wants the full local census:

  default             the shipped register. Three areas: this repository, the data root,
                      and the declared documents. What it does not cover it says in
                      words, in the output itself, so that its silence about the rest of
                      a local disk is read as a declared boundary and not as an empty
                      directory.
  --full-local-census the same register with the third area replaced by a walk of the
                      whole workspace. Nothing this repository ships is built from it.

WHAT IT COSTS TO RUN, AND WHY IT IS NOT A SWEEP OF EVERY BYTE. Hashing all three areas
would be about 17 GB. It is not needed: a file can only carry a declared identity if its
size equals the size recorded beside that identity, so size is a free necessary condition
and only size-matching files are hashed. The filter cannot hide a declared input -- a
file of the wrong size cannot hash to the right value -- and it cannot invent an
undeclared one for the same reason. Files whose name matches a declared name are hashed
as well, at any size, so that a file which CHANGED at its recorded address is reported as
changed rather than as absent.

CALIBRATION, WITHOUT WHICH NONE OF THE COUNTS ABOVE MEANS ANYTHING. A resolver that finds
everything and a resolver that finds nothing both print a tidy table. Two fixtures are
therefore built out of a real file of this tree on every run, one for each direction, and
both are resolved by the same function the register itself uses:

  must fire     the true identity of a real file, declared against a directory the file
                is not in. The resolver has to find it anyway and name the true address.
                A resolver that answers by path fails this one.
  must be silent
                the same file's size with one byte of its content changed, so the search
                really runs over every file of that size and really has to come back
                empty. A resolver that is too wide fails this one.

The fixtures are BUILT rather than named, and that is deliberate. A calibration case
pointed at a live defect of the tree erases itself the day the defect is fixed, and then
the calibration passes on nothing. These two are derived from whatever this file's
neighbour happens to be at run time, so they cannot go stale, and they do not appear in
the register: they are resolved separately and reported under `calibration`.

The live tree is measured too, and reported beside them, because the fixtures prove the
instrument works and only the tree can say what the instrument found: the count of
declared inputs resolving OFF their recorded path is printed as a finding, with the rows
named.

WHAT THIS MODULE DOES NOT ANSWER, so that its silence is not read as a verdict. It does
not say whether an input is FRESH -- whether the artifact standing on it was computed
from the bytes on disk today; that is checks/chk_input_freshness.py, which asks a
different question and owns it. It does not price a rebuild; build.py does that from the
runtime each artifact records. And it does not judge a missing file: it reports the class
of recovery and leaves the decision to a reader who knows what the run is for.

    uv run --no-project --with-requirements requirements.txt python3 data_register.py
    uv run --no-project --with-requirements requirements.txt python3 data_register.py --selftest
    uv run --no-project --with-requirements requirements.txt python3 data_register.py --full-local-census --stdout
"""
import argparse
import fnmatch
import hashlib
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import artifact                                                          # noqa: E402

OUT_NAME = "data_register.md"
OUT_JSON_NAME = "data_register_results.json"

# The parent workspace this repository sits in. Built from this file's own location so
# that no machine of anyone's appears in a published file, and treated as optional
# throughout: a reader who clones only this repository has neither of the outer two
# areas, and gets a register over the tree with the other two marked absent.
WORKSPACE = os.path.dirname(HERE)
DATA_ROOT = os.path.join(WORKSPACE, "02_data")

# WHICH OF THE TWO MODES IS RUNNING, and it decides the third search area and nothing
# else. True is the shipped register, whose third area is the declared list below; False
# is the full local census, whose third area is a walk of the whole workspace. Both
# resolve by content through the same predicate, so the modes differ in WHERE they look
# and never in HOW they decide.
SHIPPING = True

# The documents of the parent workspace that artifacts of this repository declare as
# inputs, named one at a time so that a reader sees the area instead of inferring it from
# a directory. The acquisition log is not here because the data area already covers it.
# A document that is not on the machine is reported as an absent member of a present
# area, which is a different fact from a missing input and is kept apart from it.
#
# EMPTY IN THIS REPOSITORY, and the emptiness is declared rather than the mechanism
# removed. The two documents once named here were drafts of the write-up kept beside
# the code where it was first developed; neither is published with this repository, and
# no script here needs one to compute a figure. An artifact that still declares one of
# them as an input is reported below as declared and absent, which is the true state of
# a clone.
WORKSPACE_DOCUMENTS = ()

# The six directories the acquisition log names as the homes of data on this machine.
# Listed rather than discovered, because a directory that ought to hold data and holds
# nothing is a finding, and a walk of whatever happens to be there cannot report it.
DATA_DIRS = ("raw", "processed", "l2_cache", "l2_cache_panel",
             "forward_cache", "raw_fills_cache")

# Directories skipped in every area. `.git` is 38 MB of packed objects that are not files
# of this project, and `__pycache__` holds compiled copies of files already walked.
SKIP_DIRS = {".git", "__pycache__", ".ipynb_checkpoints", ".DS_Store"}

# =====================================================================
# THE RECOVERY TABLE
# =====================================================================
# What happens if a file is gone. Every entry cites the section of
# data acquisition log it is taken from, because the cost and the
# openness of a source are external facts about the world and this table is a cache of
# them: re-read the log when one is disputed, do not argue from here.
#
# The rules are tried in order and the FIRST match wins, and the order is the order of
# what a reader would actually do. A file this repository ships is restored by a clone
# before anything is downloaded; a file this pipeline computes is rebuilt before its
# source is fetched again; only what neither of those reaches is a download.
#
# `matches` is a list of shell patterns over the input's name, or the sentinel None for
# the two rules decided by something other than the name. A rule that matches nothing on
# a given tree is reported under recovery_rules_that_matched_nothing, because a rule
# nobody meets is either dead or wrong and both are worth seeing.
RECOVERY = (
    {"id": "in_this_repository",
     "matches": None,
     "decided_by": "git ls-files: the file is tracked, so a clone carries it",
     "cost": "free, and already done by the clone",
     "source": "this repository"},
    {"id": "rebuilt_by_this_pipeline",
     "matches": None,
     "decided_by": "build.py's graph holds a node whose output carries this name, "
                   "either literally or through a family the output names with a glob",
     "cost": "one node's runtime, which build.py reads from that node's own artifact",
     "source": "a producer of this repository"},
    {"id": "internal_working_state",
     "matches": None,
     "decided_by": "the file resolved into a directory this repository's own .gitignore "
                   "keeps out of git, so it is working state of the node that wrote it",
     "cost": "one node's runtime. Git does not carry it and no archive holds it, "
             "because it is a checkpoint of a computation and not data",
     "source": "the producer that wrote it, rerun"},
    {"id": "self_test_fixture",
     "matches": ["fixture_*"],
     "decided_by": "the name is a fixture a self-test writes into a temporary directory",
     "cost": "none: it is created and thrown away inside one run of a check",
     "source": "the check's own self-test"},
    {"id": "free_public_archive",
     "matches": ["trades_2025_12.tar", "book_diffs_*.tar", "https://zenodo.org/*",
                 "*aggTrades*", "*bookDepth*", "binance",
                 "*_funding.parquet", "*_klines.parquet", "funding"],
     "decided_by": "the name is one of the openly published objects",
     "cost": "free, no account: Zenodo 18184441 is CC-BY-4.0 and ungated, "
             "data.binance.vision is anonymous, and the Hyperliquid funding endpoint "
             "needs no key",
     "source": "Zenodo 18184441 (Albers et al.) for the trades tar and the book diffs; "
               "data.binance.vision for the cross-venue files; the Hyperliquid info "
               "endpoint for funding"},
    {"id": "metered_requester_pays",
     "matches": ["s3://*", "*.lz4", "l2_cache", "l2_cache_panel", "raw_fills_cache"],
     "decided_by": "the object lives in a requester-pays bucket",
     "cost": "the requester pays AWS egress, about 0.09 USD a gigabyte with the first "
             "100 GB of a month free; a day of fills is about half a gigabyte",
     "source": "s3://hl-mainnet-node-data for the account-resolved fills and "
               "s3://hyperliquid-archive for the L2 book snapshots"},
    {"id": "recorded_forward_no_backfill",
     "matches": ["????-??-??.ndjson.gz", "forward_cache"],
     "decided_by": "the name is a day of the forward recorder's own output",
     "cost": "NOT RECOVERABLE for a day already past. A recorder collects forward from "
             "the moment it runs and no route backfills the public websocket stream, so "
             "a lost day of this tape is a lost window, not a re-download",
     "source": "the forward recorder's own host, which holds the second copy"},
    {"id": "outside_this_repository",
     "matches": None,
     "decided_by": "the file resolved outside this repository and no source above claims "
                   "it. It is tried LAST of the located classes on purpose: the raw tape "
                   "also lives outside, and the useful answer about the tape is the "
                   "archive it comes from, not the directory it happens to sit in",
     "cost": "free, but not by a download: these are documents of the parent "
             "workspace this repository sits inside",
     "source": "the parent workspace"},
    {"id": "declared_but_never_produced",
     "matches": None,
     "decided_by": "the name is absent from the area, no producer of this tree writes "
                   "it and no rule above claims it",
     "cost": "it has to be BUILT, and no script of this repository builds it. This is a "
             "debt of provenance and not a lost file: nothing was deleted, the input was "
             "named by a producer that never had it",
     "source": "none: it would have to be written first"},
)

RECOVERY_UNKNOWN = {
    "id": "not_classified",
    "cost": "unknown",
    "source": "no rule of this table matched, and a guess here would read as a fact",
}


# =====================================================================
# 1. WHAT THE ARTIFACTS DECLARE THEY READ
# =====================================================================

def _walk_files(root, skip=SKIP_DIRS):
    """Every file under root, as absolute paths, with the skipped directories pruned."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in skip)
        for name in sorted(filenames):
            if name in skip:
                continue
            yield os.path.join(dirpath, name)


def declarations(tree=HERE):
    """Every (artifact, input) pair this repository records, read out of the artifacts.

    The base directory against which a record's name would resolve is the ARTIFACT's own
    directory and not a guess: artifact.write refuses an out_name with a directory in it
    and defaults the destination to the producer's own directory, so the artifact sits
    beside the producer that wrote it and the producer resolved its inputs against that
    same directory. Taking the base from the artifact's location therefore reproduces
    what the producer did, without having to find the producer's file first.
    """
    out, with_a_list = [], 0
    for path in _walk_files(tree):
        if not path.endswith(".json"):
            continue
        try:
            with open(path, encoding="utf-8") as handle:
                document = json.load(handle)
        except (ValueError, UnicodeDecodeError, OSError):
            continue
        if not isinstance(document, dict):
            continue
        meta = document.get("_meta")
        if not isinstance(meta, dict) or not isinstance(meta.get("inputs"), list):
            continue
        with_a_list += 1
        producer = (meta.get("producer") or {}).get("script")
        base = os.path.dirname(path)
        for record in meta["inputs"]:
            if not isinstance(record, dict):
                continue
            out.append({
                "artifact": os.path.relpath(path, tree),
                "producer": producer,
                "base_dir": base,
                "name": record.get("name"),
                "bytes": record.get("bytes"),
                "sha256": record.get("sha256"),
                # `kind` was added to the recorder on 2026-08-04; artifacts written
                # before that carry none, and the absence is kept as None rather than
                # filled in, because inventing the kind of a record written by an older
                # recorder is a statement about a run nobody watched.
                "kind": record.get("kind"),
                "present_when_recorded": record.get("present"),
            })
    return out, with_a_list


def is_pattern(name):
    """True for a declared name that is a glob rather than a file.

    A handful of records name a family -- `mid_series_*.npz` -- because the producer read
    whatever the glob matched. Such a record has no size and no hash, so it cannot be
    resolved by content at all, and saying so is more useful than resolving it by name
    and calling the answer an identity.
    """
    return bool(name) and any(ch in name for ch in "*?[")


def name_rows(decls):
    """Fold the declarations into one row per declared name."""
    rows = {}
    for d in decls:
        row = rows.setdefault(d["name"], {
            "name": d["name"],
            "read_by": [],
            "identities": {},
            "kinds_recorded": set(),
            "recorded_paths": set(),
        })
        row["read_by"].append({"artifact": d["artifact"], "producer": d["producer"]})
        row["kinds_recorded"].add(d["kind"])
        if d["sha256"]:
            ident = row["identities"].setdefault(
                d["sha256"], {"sha256": d["sha256"], "bytes": d["bytes"],
                              "declared_times": 0})
            ident["declared_times"] += 1
        if d["name"] and "://" not in d["name"] and not is_pattern(d["name"]):
            row["recorded_paths"].add(os.path.join(d["base_dir"], d["name"]))
    return rows


# =====================================================================
# 2. THE SEARCH AREA AND THE CONTENT INDEX
# =====================================================================

def workspace_documents():
    """The declared documents of the workspace, each with its address and whether it is
    here. The address is built from this file's own location, so no machine of anyone's
    is typed anywhere, and it is used to READ the file and not to answer for it: what the
    register says about such a document is decided by its bytes like every other row."""
    out = []
    for doc in WORKSPACE_DOCUMENTS:
        path = os.path.join(WORKSPACE, *doc["parts"])
        out.append({"id": doc["id"], "path": path, "present": os.path.isfile(path)})
    return out


def search_areas():
    """The three areas, each with the reason it is in the search and whether it is here."""
    data_present = os.path.isdir(DATA_ROOT)
    areas = [
        {"id": "tree", "root": HERE, "present": True,
         "why": "this repository: every artifact, every script and every derived "
                "intermediate a run leaves beside its producer"},
        {"id": "data", "root": DATA_ROOT, "present": data_present,
         "why": "../02_data, whose six data directories the acquisition log names "
                "as the home of data on this machine, and the acquisition log itself. "
                "It sits outside this repository because a raw day is gigabytes; a clone "
                "without it gets a register over the tree and this area marked absent"},
    ]
    if SHIPPING:
        docs = workspace_documents()
        areas.append({
            "id": "workspace_documents", "root": WORKSPACE,
            "present": os.path.isdir(WORKSPACE),
            "paths": [d["path"] for d in docs if d["present"]],
            "members": [{"id": d["id"], "name": os.path.basename(d["path"]),
                         "present": d["present"]} for d in docs],
            "why": "the documents of the parent workspace that artifacts of this "
                   "repository declare as inputs, named one at a time rather than found "
                   "by walking the workspace: a walk reports every file of one working "
                   "copy, and the files it adds are not files this pipeline reads"})
    else:
        areas.append({
            "id": "workspace", "root": WORKSPACE, "present": os.path.isdir(WORKSPACE),
            "why": "the whole parent workspace this repository sits in. This area is "
                   "the full local census and is not what the shipped register is built "
                   "from: it describes one machine and covers files no producer reads",
            "exclude": (HERE, DATA_ROOT)})
    return areas


def area_files(areas):
    """Every file of every present area, as {absolute path: (area id, size)}.

    A path is attributed to the first area that holds it, so the workspace area does not
    re-report the tree it contains.

    An area may name its files instead of naming a root to walk, and the declared
    documents do. The two are handled apart on purpose: a listed file that is not on the
    machine is simply not in the area, which is what an absent document is, while a root
    that is not on the machine is an absent AREA and has to be reported as one.
    """
    seen = {}
    for area in areas:
        if not area["present"]:
            continue
        if area.get("paths") is not None:
            for path in sorted(area["paths"]):
                if path in seen:
                    continue
                try:
                    seen[path] = (area["id"], os.path.getsize(path))
                except OSError:
                    continue
            continue
        roots = ([os.path.join(area["root"], d) for d in area["subdirs"]]
                 if area.get("subdirs") else [area["root"]])
        excluded = tuple(os.path.join(p, "") for p in area.get("exclude", ()))
        for root in roots:
            if not os.path.isdir(root):
                continue
            for path in _walk_files(root):
                if path in seen or path.startswith(excluded):
                    continue
                try:
                    seen[path] = (area["id"], os.path.getsize(path))
                except OSError:
                    continue
    return seen


def content_index(files, wanted_sizes, wanted_names):
    """sha256 -> the paths whose bytes carry it, over the files worth hashing.

    Two cheap tests decide what is worth hashing, and their union is what makes the
    filter safe rather than merely fast. SIZE is a necessary condition for carrying a
    declared identity, so a file of an unrecorded size provably carries none and skipping
    it cannot hide an input. NAME is added on top so that a file sitting at a recorded
    address with CHANGED content is hashed too, and comes out as changed instead of as
    absent -- which is the second half of the defect this register exists for.
    """
    index, hashed_bytes, hashed = {}, 0, 0
    for path, (_area, size) in sorted(files.items()):
        if size not in wanted_sizes and os.path.basename(path) not in wanted_names:
            continue
        try:
            digest = artifact.sha256_file(path)
        except OSError:
            continue
        index.setdefault(digest, []).append(path)
        hashed += 1
        hashed_bytes += size
    return index, {"n_files_hashed": hashed, "bytes_hashed": hashed_bytes,
                   "n_files_in_the_area": len(files),
                   "bytes_in_the_area": sum(s for _a, s in files.values())}


# =====================================================================
# 3. RESOLUTION -- THE ONE PREDICATE, USED BY THE REGISTER AND BY THE CALIBRATION
# =====================================================================

def resolve_identity(sha256, recorded_paths, index, tree=HERE):
    """Where the bytes carrying this identity are, and whether that is where it was read.

    This is the predicate the whole module stands on, and it is deliberately one
    function: the calibration below resolves its two fixtures through this same call, so
    a claim that the instrument fires and stays silent is a claim about the code that ran
    the register and not about a copy of it.
    """
    found = sorted(index.get(sha256, []))
    at_recorded = [p for p in found if p in recorded_paths]
    elsewhere = [p for p in found if p not in recorded_paths]
    if at_recorded:
        status = "present_at_the_recorded_path"
    elif elsewhere:
        status = "present_off_the_recorded_path"
    else:
        status = "absent_from_the_search_area"
    return {
        "sha256": sha256,
        "status": status,
        "found_at": [_show(p, tree) for p in found],
        "at_the_recorded_path": [_show(p, tree) for p in at_recorded],
        "off_the_recorded_path": [_show(p, tree) for p in elsewhere],
    }


def _show(path, tree=HERE):
    """A path as a reader of this repository would write it, and never as this machine has
    it. Inside the tree it is relative to the tree; outside it is relative to the
    workspace with a leading marker, so that a file two directories up reads as what it
    is without a home directory appearing in a published file."""
    try:
        inside = os.path.relpath(path, tree)
    except ValueError:
        inside = None
    if inside and not inside.startswith(".."):
        return inside
    try:
        outside = os.path.relpath(path, WORKSPACE)
    except ValueError:
        return os.path.basename(path)
    if outside.startswith(".."):
        return os.path.basename(path)
    if outside == ".":
        return ".."
    # A DECLARED DOCUMENT IS SHOWN BY ITS NAME AND ITS AREA, NOT BY THE DIRECTORIES IT
    # SITS IN. Where such a document sits inside a working copy is a fact about that copy
    # and not about this pipeline, and the four questions this register answers -- what it
    # is, where it is, who reads it, what it costs -- are all answered by the area and the
    # name. The full local census keeps the chain, because there the chain is the point.
    if SHIPPING and not _under(path, DATA_ROOT):
        return "the parent workspace: " + os.path.basename(path)
    return "../" + outside


def _under(path, root):
    """True when path is root or sits below it."""
    return path == root or path.startswith(root + os.sep)


# =====================================================================
# 4. WHAT IT COSTS TO GET A FILE BACK
# =====================================================================

def tracked_names(tree=HERE):
    """The basenames git tracks in this repository, or None when git cannot answer.

    None and the empty set are different answers and are kept apart: a clone without git
    installed cannot say what a clone carries, and reporting that as "nothing is tracked"
    would move every shipped file into a download class it does not belong to.
    """
    try:
        done = subprocess.run(["git", "-C", tree, "ls-files", "-z"],
                              capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    return {os.path.basename(p) for p in done.stdout.decode().split("\0") if p}


def pipeline_outputs():
    """Every basename some node of the build graph writes, or None when it cannot run.

    build.graph() derives the outputs from the syntax trees of the tracked scripts, so
    this is the pipeline's own answer to "do we make this file" rather than a second list
    that would go stale beside it.
    """
    try:
        import build
        return {name for node in build.graph().nodes.values()
                for name in getattr(node, "outputs", ())}
    except Exception:                                        # noqa: BLE001
        return None


def ignored_directories(tree=HERE):
    """The directories this repository's own .gitignore keeps out of git.

    Read rather than listed, because the tree already states this and a second list here
    would go stale beside it. Only the entries written as a directory are taken: a
    pattern like `*.log` says nothing about where a file lives.
    """
    path = os.path.join(tree, ".gitignore")
    out = set()
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line.endswith("/") and not line.startswith("#") and "*" not in line:
                    out.add(line.rstrip("/").lstrip("/"))
    except OSError:
        return out
    return out


def recovery_of(name, tracked, outputs, status=None, found_in=(), found_at=(),
                ignored=frozenset()):
    """The first rule of RECOVERY this name meets, with what decided it.

    Three of the seven rules are decided by something other than the name, and they are
    the three that matter most: what a clone already carries, what this pipeline rebuilds,
    and what nothing at all produces. A name-only table would put the first two in a
    download class they do not belong to and would have no way of saying the third.
    """
    for rule in RECOVERY:
        if rule["id"] == "in_this_repository":
            if tracked is not None and name in tracked:
                return dict(rule, matched_on="git ls-files")
            continue
        if rule["id"] == "rebuilt_by_this_pipeline":
            # Exactly, or through a family: build.py folds an output written in a loop
            # to the glob the loop wrote, so `mid_series_BTC.npz` is produced by a node
            # whose declared output is `mid_series_*.npz`. Matching on the literal alone
            # sent 27 rebuildable files into the unclassified column.
            if outputs is not None and (
                    name in outputs
                    or any(is_pattern(o) and fnmatch.fnmatch(name, o) for o in outputs)):
                return dict(rule, matched_on="an output of the build graph")
            continue
        if rule["id"] == "internal_working_state":
            hit = sorted({p.split("/")[0] for p in found_at
                          if "/" in p and p.split("/")[0] in ignored})
            if hit:
                return dict(rule, matched_on=", ".join(hit))
            continue
        if rule["id"] == "outside_this_repository":
            if set(found_in) - {"tree"}:
                return dict(rule,
                            matched_on=", ".join(sorted(set(found_in) - {"tree"})))
            continue
        if rule["id"] == "declared_but_never_produced":
            if status and status.startswith(("absent", "no_recorded_identity",
                                             "pattern_matches_nothing")):
                return dict(rule, matched_on=status)
            continue
        for pattern in rule["matches"]:
            if fnmatch.fnmatch(name, pattern):
                return dict(rule, matched_on=pattern)
    return dict(RECOVERY_UNKNOWN, matched_on=None)


# =====================================================================
# 5. THE REGISTER
# =====================================================================

def register(rows, index, tracked, outputs, files, tree=HERE):
    """One entry per declared name, with the four answers filled in."""
    out = []
    ignored = ignored_directories(tree)
    by_name = {}
    for path in index_paths(index):
        by_name.setdefault(os.path.basename(path), []).append(path)
    for name in sorted(rows, key=lambda n: (n or "")):
        row = rows[name]
        kinds = sorted(str(k) for k in row["kinds_recorded"])
        entry = {
            "name": name,
            "n_declarations": len(row["read_by"]),
            "kinds_recorded": kinds,
            "read_by": sorted({(d["artifact"], d["producer"]) for d in row["read_by"]}),
            "identities": [],
            "shape": "file",
            "status": None,
        }
        entry["read_by"] = [{"artifact": a, "producer": p} for a, p in entry["read_by"]]

        if name and "://" in name:
            entry["shape"] = "remote_object"
            entry["status"] = "not_a_local_file"
            entry["note"] = ("a URI, so no local copy is expected and no hash was ever "
                             "recorded; what a rebuild costs is the class below")
        elif is_pattern(name):
            entry["shape"] = "pattern"
            matches = sorted(_show(p, tree) for p in index_paths(index)
                             if fnmatch.fnmatch(os.path.basename(p), name))
            entry["status"] = ("pattern_matches_files" if matches
                               else "pattern_matches_nothing")
            entry["found_at"] = matches
            entry["note"] = ("the record names a family and not a file, so it carries no "
                             "size and no hash and cannot be resolved by content at all. "
                             "What is shown is a NAME match over the search area, which "
                             "is weaker evidence and is labelled as such")
        elif "directory" in kinds and not row["identities"]:
            entry["shape"] = "directory"
            here = [_show(p, tree) for p in _dirs_named(name)]
            entry["status"] = "directory_present" if here else "directory_absent"
            entry["found_at"] = here
            entry["note"] = ("a directory has no single hash, so this row is resolved by "
                             "name and its presence is weaker evidence than every file "
                             "row above")
        elif not row["identities"]:
            entry["shape"] = "file"
            same_name = sorted(_show(p, tree) for p in by_name.get(name, []))
            entry["status"] = ("no_recorded_identity_but_a_name_match" if same_name
                               else "no_recorded_identity_and_no_name_match")
            entry["found_at"] = same_name
            entry["note"] = ("every artifact that names this input recorded it as absent, "
                             "so no sha256 was ever written for it and there is nothing "
                             "to search for. The row rests on the NAME, which is the "
                             "weakest evidence in this file")
        else:
            for ident in sorted(row["identities"].values(),
                                key=lambda i: -i["declared_times"]):
                found = resolve_identity(ident["sha256"], row["recorded_paths"], index,
                                         tree)
                found.update(bytes=ident["bytes"],
                             declared_times=ident["declared_times"])
                entry["identities"].append(found)
            states = {i["status"] for i in entry["identities"]}
            if states == {"absent_from_the_search_area"}:
                # THE ONE DISTINCTION THAT MUST NOT BE BLURRED. "No file carries the
                # bytes this artifact read" and "no file of this name exists" are
                # different facts, and the first is the ordinary consequence of a
                # rebuild: the input was recomputed after the artifact was written, so
                # the recorded version is gone and a current one sits in its place.
                # Reporting the first in the words of the second is how a healthy tree
                # gets called a tree with missing data.
                same_name = sorted(_show(p, tree) for p in by_name.get(name, []))
                entry["status"] = ("the_recorded_bytes_are_gone_a_file_of_that_name_"
                                   "is_present" if same_name
                                   else "absent_from_the_search_area")
                entry["a_file_of_that_name_at"] = same_name
            elif "absent_from_the_search_area" in states:
                entry["status"] = "some_identities_absent"
            elif states == {"present_at_the_recorded_path"}:
                entry["status"] = "present_at_the_recorded_path"
            else:
                entry["status"] = "present_off_the_recorded_path"
            entry["recorded_paths"] = sorted(_show(p, tree)
                                             for p in row["recorded_paths"])

        found_abs = [p for i in entry["identities"] for p in index.get(i["sha256"], [])]
        if not found_abs:
            found_abs = by_name.get(name, [])
        entry["found_in_areas"] = sorted({files[p][0] for p in found_abs if p in files})
        entry["recovery"] = recovery_of(
            name or "", tracked, outputs, entry["status"], entry["found_in_areas"],
            sorted({_show(p, tree) for p in found_abs}), ignored)
        out.append(entry)
    return out


def index_paths(index):
    """Every path the content index holds, flattened."""
    return [p for paths in index.values() for p in paths]


def _dirs_named(name):
    """Directories in the search area whose basename is this one.

    The roots are the roots of the mode's own area. Searching the whole workspace while
    the shipped area is this repository and the data root would answer a row out of a
    place the register says it did not look.
    """
    found = []
    for root in ((HERE, DATA_ROOT) if SHIPPING else (HERE, DATA_ROOT, WORKSPACE)):
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, _files in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for d in dirnames:
                if d == name:
                    found.append(os.path.join(dirpath, d))
    return sorted(set(found))


# =====================================================================
# 6. THE REVERSE SIDE -- WHAT LIES IN THE DATA DIRECTORIES UNCLAIMED
# =====================================================================

def _declared_days(rows):
    """The eight-digit days named by a declared remote prefix, mapped to the prefix.

    The hourly files of a cached day are named by nobody -- an artifact declares the
    s3:// prefix the day came from, not the twenty-four files pulled out of it -- and a
    census that called them undeclared would be reporting its own coarseness. The day in
    the prefix is the link, and it is spelled out here so a reader can check the
    attribution rather than take it.
    """
    days = {}
    for name in rows:
        if not name or "://" not in name:
            continue
        for part in name.rstrip("/").split("/"):
            if len(part) == 8 and part.isdigit():
                days.setdefault(part, set()).add(name)
    return days


BUCKETS = ("declared_by_name", "declared_by_content", "inside_a_declared_directory",
           "a_day_of_a_declared_remote_prefix", "undeclared")


def bucket_of(path, digest, claims):
    """Which of the five buckets accounts for one file of a data directory.

    Split out of the census so that the census can be calibrated: a count of zero
    undeclared files is exactly the kind of answer that has to be shown capable of being
    something else, and the only way to show it is to put a file nobody declares through
    this same function and watch it come out undeclared.
    """
    base = os.path.basename(path)
    parts = os.path.relpath(path, DATA_ROOT).split(os.sep)
    if base in claims["names"]:
        return "declared_by_name", None
    if digest and digest in claims["hashes"]:
        return "declared_by_content", None
    inside = claims["directories"].intersection(parts)
    if inside:
        return "inside_a_declared_directory", sorted(inside)
    hit = sorted({uri for part in parts for day, uris in claims["days"].items()
                  if day in part for uri in uris})
    if hit:
        return "a_day_of_a_declared_remote_prefix", hit
    return "undeclared", None


def claims_of(rows):
    """Everything this repository says about files, in the four shapes bucket_of needs."""
    return {
        "names": {n for n in rows if n},
        "hashes": {ident for row in rows.values() for ident in row["identities"]},
        "directories": {n for n, row in rows.items()
                        if n and "directory" in {str(k)
                                                 for k in row["kinds_recorded"]}},
        "days": _declared_days(rows),
    }


def undeclared_census(files, rows, index, tree=HERE):
    """Every file of the data area, sorted into how it is accounted for.

    Five buckets. Four of them are ways of being accounted for and are printed with their
    counts so that the fifth can be read as what it is: a file in a data directory that
    nothing in this repository claims.
    """
    claims = claims_of(rows)
    buckets = {k: [] for k in BUCKETS}
    total_bytes = {k: 0 for k in buckets}
    attribution = {}
    # The index the other way round, built once. Asked path by path it would be a scan of
    # every identity for every file of a data area, which on this tree is fourteen
    # thousand files against a few hundred identities.
    digest_of = {p: sha for sha, paths in index.items() for p in paths}

    for path, (area, size) in sorted(files.items()):
        if area != "data":
            continue
        key, why = bucket_of(path, digest_of.get(path), claims)
        if why:
            attribution[path] = why
        buckets[key].append(path)
        total_bytes[key] += size

    return {
        "population": ("every file under ../02_data, whose six directories the "
                       "acquisition log calls the home of data on this machine"),
        "per_directory": {
            d: sum(1 for p in files
                   if files[p][0] == "data"
                   and os.path.relpath(p, DATA_ROOT).split(os.sep)[0] == d)
            for d in DATA_DIRS},
        "buckets": {
            key: {"n_files": len(paths), "bytes": total_bytes[key],
                  "files": [_show(p, tree) for p in paths[:200]],
                  "truncated_after": 200 if len(paths) > 200 else None}
            for key, paths in buckets.items()},
        "what_each_bucket_means": {
            "declared_by_name": "an artifact names this file as an input",
            "declared_by_content": "no artifact names it, but its bytes carry an "
                                   "identity some artifact recorded, so it is the same "
                                   "file under another name",
            "inside_a_declared_directory": "an artifact declares the directory it sits "
                                           "in as its input, which is what a producer "
                                           "that read a whole cache records",
            "a_day_of_a_declared_remote_prefix": "an artifact declares the remote prefix "
                                                 "this day was pulled from, so the file "
                                                 "is the local copy of a declared object",
            "undeclared": "nothing in this repository claims this file. This is the "
                          "bucket the register exists to print",
        },
        "attribution": {_show(p, tree): v for p, v in sorted(attribution.items())[:50]},
    }


# =====================================================================
# 7. CALIBRATION
# =====================================================================

def calibration(index, rows, tree=HERE):
    """Two fixtures built from a real file of this tree, one per direction.

    Both go through resolve_identity, the same call the register uses. The fixture file
    is this module's own neighbour artifact.py: it cannot be absent, because this module
    imported it to get here, and it is hashed in every run anyway.
    """
    fixture = os.path.join(tree, "artifact.py")
    size = os.path.getsize(fixture)
    true_hash = artifact.sha256_file(fixture)

    # BOTH FIXTURES SEARCH THE SAME INDEX, and the index has the fixture file in it. The
    # first version of this calibration put the fixture in for the firing case only, and
    # the silent case then passed over an index holding NO file of that size at all: it
    # proved that a search of an empty shelf finds nothing, which is not the question.
    # With the file present, the silent case has a same-size neighbour it has to look at
    # and reject on content, which is the property being claimed.
    grown = _with(index, fixture, true_hash)

    # MUST FIRE. The true identity, declared against a directory the file is not in. A
    # resolver that answers "is there a file at this path" reports absent here.
    wrong_dir = os.path.join(tree, "checks")
    fires = resolve_identity(true_hash, {os.path.join(wrong_dir, "artifact.py")},
                             grown, tree)

    # MUST BE SILENT. The same file with one byte changed: the size is unchanged, so the
    # search really runs over every file of that size in the index and really has to come
    # back empty. A resolver too wide to tell two files of one size apart reports found.
    with open(fixture, "rb") as handle:
        blob = bytearray(handle.read())
    blob[0] ^= 0x01
    absent_hash = hashlib.sha256(bytes(blob)).hexdigest()
    silent = resolve_identity(absent_hash, set(), grown, tree)

    same_size = sum(1 for paths in grown.values() for _p in paths)
    rejected = sum(1 for paths in grown.values() for p in paths
                   if os.path.isfile(p) and os.path.getsize(p) == size)

    # THE CENSUS HAS ITS OWN PAIR, because it printed a zero. A count of zero undeclared
    # files is indistinguishable from a sorter that files everything under one of the
    # four accounted-for headings, and the difference is the whole finding. Two paths go
    # through bucket_of: one nothing in this repository names, in a directory nothing
    # names, which has to come out undeclared; and one carrying a declared name, which
    # has to come out declared. Neither path needs to exist on disk -- the sorter reads
    # names and an identity, not bytes -- so the fixtures cost nothing and cannot
    # disturb the tree.
    claims = claims_of(rows)
    plain = [n for n in sorted(claims["names"])
             if n and "://" not in n and not is_pattern(n)]
    # A data-shaped name is preferred for the fixture only so that the document reads
    # about the thing being sorted; any declared name would do the same work.
    a_declared_name = next((n for n in plain if n.endswith((".npz", ".tar", ".parquet"))),
                           plain[0] if plain else "settings.py")
    census_fires, _why = bucket_of(
        os.path.join(DATA_ROOT, "processed", "a_file_nothing_declares.bin"), None, claims)
    census_silent, _why = bucket_of(
        os.path.join(DATA_ROOT, "processed", a_declared_name), None, claims)
    return {
        "how_the_fixtures_are_made": (
            "both are derived at run time from artifact.py, the module this file "
            "imports, so neither can go stale and neither names a live defect of the "
            "tree. The first carries that file's true sha256 and a recorded address the "
            "file is not at; the second carries the same size with one byte of the "
            "content flipped, an identity nothing on disk can hold"),
        "must_fire": {
            "expected": "found, off the recorded path, and the true address named",
            "status": fires["status"],
            "found_at": fires["found_at"],
            "passed": (fires["status"] == "present_off_the_recorded_path"
                       and "artifact.py" in fires["found_at"]),
        },
        "must_be_silent": {
            "expected": "absent from the search area",
            "status": silent["status"],
            "found_at": silent["found_at"],
            "n_files_of_that_size_the_search_had_to_reject": rejected,
            # A silent case answered by size is a silent case answered by nothing, so
            # the neighbour has to be there for the verdict to mean anything.
            "passed": (silent["status"] == "absent_from_the_search_area"
                       and rejected >= 1),
        },
        "n_identities_in_the_index": len(index),
        "n_paths_in_the_index": same_size,
        "the_census_of_undeclared_files": {
            "how_the_fixtures_are_made": (
                "two paths under a data directory are put through bucket_of, the same "
                "sorter the census runs on every real file. One is named by nothing and "
                "sits in a directory named by nothing; the other carries a name some "
                "artifact declares"),
            "must_fire": {
                "fixture": "02_data/processed/a_file_nothing_declares.bin",
                "expected": "undeclared", "measured": census_fires,
                "passed": census_fires == "undeclared"},
            "must_be_silent": {
                "fixture": f"02_data/processed/{a_declared_name}",
                "expected": "declared_by_name", "measured": census_silent,
                "passed": census_silent == "declared_by_name"},
        },
    }


def _with(index, path, digest):
    """The content index plus one path, without touching the caller's copy."""
    grown = {k: list(v) for k, v in index.items()}
    if path not in grown.setdefault(digest, []):
        grown[digest].append(path)
    return grown


# =====================================================================
# 8. THE TWO OUTPUTS
# =====================================================================

def totals(entries):
    """The counts that go in front of the table, each with the predicate that took it."""
    by_status = {}
    for e in entries:
        by_status[e["status"]] = by_status.get(e["status"], 0) + 1
    files = [e for e in entries if e["shape"] == "file" and e["identities"]]
    off = [e for e in files if e["status"] == "present_off_the_recorded_path"]
    outside = [e for e in entries
               if set(e.get("found_in_areas", [])) - {"tree"}]
    # THE ONLY ROWS THAT MEAN A FILE IS GONE. A row whose recorded bytes are gone while a
    # file of that name sits there is a rebuilt input, which is what a working pipeline
    # does, and counting it as an absence would put nine healthy rows into an alarm.
    absent = [e for e in entries if e["status"] in
              ("absent_from_the_search_area",
               "no_recorded_identity_and_no_name_match")]
    rebuilt = [e for e in entries if e["status"] in
               ("the_recorded_bytes_are_gone_a_file_of_that_name_is_present",
                "some_identities_absent")]
    return {
        "n_names_declared": len(entries),
        "n_resolvable_by_content": len(files),
        "n_found_by_content": sum(
            1 for e in files if e["status"] != "absent_from_the_search_area"),
        "n_found_off_the_recorded_path": len(off),
        "names_found_off_the_recorded_path": [e["name"] for e in off],
        "n_found_outside_this_repository": len(outside),
        "names_found_outside_this_repository": [e["name"] for e in outside],
        "n_absent": len(absent),
        "names_absent": [e["name"] for e in absent],
        "n_recorded_version_superseded": len(rebuilt),
        "names_recorded_version_superseded": [e["name"] for e in rebuilt],
        "by_status": dict(sorted(by_status.items())),
        "by_recovery_class": _count(e["recovery"]["id"] for e in entries),
    }


def _count(values):
    out = {}
    for v in values:
        out[v] = out.get(v, 0) + 1
    return dict(sorted(out.items()))


def mode_block(areas):
    """What this file covers and what it does not, written into the file itself.

    A boundary that lives only in the code is a boundary the reader of the output cannot
    see, and the two silences look identical from here: a directory that was searched and
    held nothing reads exactly like a directory that was never searched. So the mode says
    which of the two it is, in words, beside the counts it took.
    """
    docs = [a for a in areas if a["id"] == "workspace_documents"]
    if SHIPPING:
        covers = ("this repository, the data directories the acquisition log names as "
                  "the home of data on this machine, and the documents of the parent "
                  "workspace that artifacts of this repository declare as inputs, each "
                  "named one at a time under search_areas below")
        omits = ("everything else on the machine this ran on. The workspace around this "
                 "repository is NOT walked in this mode, so no count in this file is a "
                 "census of a local disk, and a file's absence from this register is not "
                 "evidence that the file is absent from that disk. What is claimed here "
                 "is what the declared areas hold, and nothing about what they do not "
                 "cover")
        other = ("the second mode, run as data_register.py --full-local-census, replaces "
                 "the third area with a walk of the whole workspace. It answers a "
                 "question about one machine, and nothing this repository ships is built "
                 "from it")
    else:
        covers = ("this repository, the data directories the acquisition log names, and "
                  "a walk of the whole parent workspace this repository sits in, which "
                  "is a census of one machine and not a property of this pipeline")
        omits = ("nothing of the workspace, which is what makes this the wrong mode to "
                 "ship: the addresses it prints describe the directories of one working "
                 "copy rather than the files this pipeline reads")
        other = ("the shipped mode, run as data_register.py with no argument, has a "
                 "declared list of documents for its third area instead of a walk")
    return {
        "id": "shipping" if SHIPPING else "full_local_census",
        "what_this_file_describes": covers,
        "what_this_file_does_not_describe": omits,
        "the_other_mode": other,
        "declared_documents_of_the_workspace": docs[0]["members"] if docs else None,
    }


def results(entries, areas, index_stats, census, calib, decls, rules_unmatched,
            n_with_list):
    """The machine-readable half."""
    return {
        "mode": mode_block(areas),
        "search_areas": [
            {"id": a["id"], "path": _show(a["root"]), "present": a["present"],
             "why": a["why"]} for a in areas],
        "declarations": {
            "n_artifacts_declaring_inputs": len({d["artifact"] for d in decls}),
            "n_declaration_edges": len(decls),
            "n_distinct_names": len({d["name"] for d in decls}),
            "n_distinct_identities": len({d["sha256"] for d in decls if d["sha256"]}),
            "n_artifacts_carrying_an_inputs_list": n_with_list,
            "predicate": ("a .json file of this repository whose top level carries a "
                          "_meta block with an inputs list, and one edge per record of "
                          "that list. The two artifact counts differ on purpose: an "
                          "empty inputs list is a producer stating it reads no file, "
                          "which is a declaration and not a gap, so it is counted in "
                          "the second number and not in the first"),
        },
        "index": index_stats,
        "totals": totals(entries),
        "register": entries,
        "undeclared_census": census,
        "calibration": calib,
        "recovery_rules_that_matched_nothing": rules_unmatched,
        "what_each_count_counts": {
            "n_found_off_the_recorded_path": (
                "the input resolved by hash, and no copy carrying that identity sits at "
                "the address its reader would have resolved. This is the count a "
                "path-based instrument would report as missing files"),
            "n_absent": (
                "no file in the declared search area carries any identity recorded for "
                "this name, or no identity was ever recorded and no file bears the name"),
            "bytes_hashed": (
                "the bytes this run actually read, against bytes_in_the_area which is "
                "what a sweep of everything would have read"),
        },
    }


def _sentence(text):
    """A field of the payload set as a sentence of the document.

    The two halves have to be the same string -- a document that re-words what the JSON
    says is a second home for the same fact -- so the only thing done to it here is what
    turns a field into prose: a capital and a full stop.
    """
    text = text.strip()
    return text[:1].upper() + text[1:] + ("" if text.endswith(".") else ".")


def document(entries, areas, index_stats, census, calib, decls, tot):
    """The readable half. Every number below is printed from the same payload the JSON
    carries, so the two cannot disagree."""
    L = []
    w = L.append
    w("# The data register")
    w("")
    w("What every file this pipeline reads is, where it is now, which computations "
      "stand on it, and what it costs to get it back. Generated by `data_register.py`; "
      "do not edit, the next run overwrites it.")
    w("")
    w("## How a file is looked up here")
    w("")
    w("By its bytes. Each artifact of this repository records the name, the size and the "
      "sha256 of everything its producer read, and this register resolves those hashes "
      "over a declared search area. A file that has been moved is found and its new "
      "address is printed; only a file no bytes in the area carry is called absent. "
      "Looking up by path answers **no** for a file that moved and **yes** for a stale "
      "copy at the expected address, and both of those have happened here.")
    w("")
    w("## The search area")
    w("")
    mode = mode_block(areas)
    w("**What this describes.** " + _sentence(mode["what_this_file_describes"]))
    w("")
    w("**What this does not describe.** "
      + _sentence(mode["what_this_file_does_not_describe"]))
    w("")
    w(_sentence(mode["the_other_mode"]))
    w("")
    if mode["declared_documents_of_the_workspace"]:
        w("The documents named one at a time: "
          + ", ".join(f"`{d['name']}` ({d['id']}, "
                      f"{'on this machine' if d['present'] else 'not on this machine'})"
                      for d in mode["declared_documents_of_the_workspace"]) + ".")
        w("")
    w("| area | where | present | why it is searched |")
    w("|---|---|---|---|")
    for a in areas:
        w(f"| `{a['id']}` | `{_show(a['root'])}` | {'yes' if a['present'] else 'no'} "
          f"| {a['why']} |")
    w("")
    w(f"The area holds {index_stats['n_files_in_the_area']:,} files and "
      f"{index_stats['bytes_in_the_area'] / 2**30:.2f} GB. This run hashed "
      f"{index_stats['n_files_hashed']:,} of them, "
      f"{index_stats['bytes_hashed'] / 2**30:.2f} GB: a file can only carry a declared "
      "identity if its size equals the size recorded beside that identity, so size is a "
      "free necessary condition and only size-matching files are hashed. Files whose "
      "name matches a declared name are hashed at any size, so that a changed file at a "
      "recorded address comes out as changed rather than as absent.")
    w("")
    w("## The count, and the predicate that took it")
    w("")
    w("| count | value | predicate |")
    w("|---|---:|---|")
    w(f"| artifacts declaring what they read | "
      f"{len({d['artifact'] for d in decls})} | a `.json` of this tree whose `_meta` "
      "carries an `inputs` list |")
    w(f"| declaration edges | {len(decls)} | one per record of those lists |")
    w(f"| distinct input names | {tot['n_names_declared']} | the `name` field of a "
      "record, which is a basename by design |")
    w(f"| names resolvable by content | {tot['n_resolvable_by_content']} | at least one "
      "sha256 was recorded for the name |")
    w(f"| of those, found | {tot['n_found_by_content']} | some file of the area carries "
      "a recorded identity |")
    w(f"| of those, found OFF the recorded address | "
      f"{tot['n_found_off_the_recorded_path']} | found, and nothing carrying that "
      "identity sits where its reader would have looked |")
    w(f"| of those, found outside this repository | "
      f"{tot['n_found_outside_this_repository']} | the bytes are in the data directories "
      "or the workspace, not in the clone |")
    w(f"| recorded version superseded | {tot['n_recorded_version_superseded']} | the "
      "exact bytes an artifact read are gone and a file of that name is there, which is "
      "what a rebuild leaves behind and is NOT a missing file |")
    w(f"| declared and nowhere in the area | {tot['n_absent']} | no file carries any "
      "recorded identity AND no file bears the name |")
    w("")
    w("The middle row is the one a path-based instrument gets wrong, and it is most of "
      "the register. A record keeps only the basename of what its producer read, so the "
      "only address a later reader can reconstruct is 'beside the producer'; for "
      f"{tot['n_found_off_the_recorded_path']} of {tot['n_resolvable_by_content']} names "
      "that address holds nothing carrying the recorded identity, and every one of them "
      "is found by content.")
    w("")
    if tot["names_found_outside_this_repository"]:
        w("Resolved outside this repository: "
          + ", ".join(f"`{n}`" for n in tot["names_found_outside_this_repository"]) + ".")
        w("")
    if tot["names_absent"]:
        w("Declared and carried by nothing in the area, by content or by name: "
          + ", ".join(f"`{n}`" for n in tot["names_absent"]) + ".")
        w("")
    w("## Calibration")
    w("")
    w("Two instruments print counts here and each one gets a pair, because a resolver "
      "that finds everything and a resolver that finds nothing both print a tidy table, "
      "and a sorter that files everything under an accounted-for heading prints a zero "
      "in the column that matters.")
    w("")
    w(_sentence(calib["how_the_fixtures_are_made"]))
    w("")
    w("| instrument | fixture | expected | measured | verdict |")
    w("|---|---|---|---|---|")
    for key, label in (("must_fire", "must fire"),
                       ("must_be_silent", "must stay silent")):
        c = calib[key]
        w(f"| resolving an input by content | {label} | {c['expected']} "
          f"| `{c['status']}` | {'PASS' if c['passed'] else 'FAIL'} |")
    cen = calib["the_census_of_undeclared_files"]
    for key, label in (("must_fire", "must fire"),
                       ("must_be_silent", "must stay silent")):
        c = cen[key]
        w(f"| sorting a data file | {label} | `{c['expected']}` | `{c['measured']}` "
          f"| {'PASS' if c['passed'] else 'FAIL'} |")
    w("")
    w(_sentence(cen["how_the_fixtures_are_made"]))
    w("")
    w(f"The silent fixture was not answered by its size: "
      f"{calib['must_be_silent']['n_files_of_that_size_the_search_had_to_reject']} "
      "file(s) of exactly that size sit in the index and every one of them had to be "
      "hashed and rejected on content.")
    w("")
    w("## What it costs to get a file back")
    w("")
    w("| class | names | cost | source |")
    w("|---|---:|---|---|")
    seen = {}
    for e in entries:
        seen.setdefault(e["recovery"]["id"], e["recovery"])
    for cid, n in tot["by_recovery_class"].items():
        r = seen[cid]
        w(f"| `{cid}` | {n} | {r['cost']} | {r['source']} |")
    w("")
    w("## What lies in the data directories")
    w("")
    w(_sentence(census["population"]))
    w("")
    w("Files per directory: "
      + ", ".join(f"`{d}` {n}" for d, n in census["per_directory"].items()) + ".")
    w("")
    w("| bucket | files | GB | what it means |")
    w("|---|---:|---:|---|")
    for key, b in census["buckets"].items():
        w(f"| `{key}` | {b['n_files']} | {b['bytes'] / 2**30:.2f} "
          f"| {census['what_each_bucket_means'][key]} |")
    w("")
    w("## The register")
    w("")
    w("| input | read by | identity | where it is | if it is lost |")
    w("|---|---:|---|---|---|")
    for e in entries:
        ident = "-"
        if e["identities"]:
            first = e["identities"][0]
            ident = f"`{first['sha256'][:12]}` ({first['bytes']:,} B)"
            if len(e["identities"]) > 1:
                ident += f" and {len(e['identities']) - 1} more"
        # Every address of every identity, not the first one's: a name carried by two
        # identities is usually one file written by two producers into two directories,
        # and printing one of the two is how a reader is left believing there is one.
        seen_at = []
        for got in ([i["found_at"] for i in e["identities"]]
                    or [e.get("found_at", []), e.get("a_file_of_that_name_at", [])]):
            for p in got:
                if p not in seen_at:
                    seen_at.append(p)
        where = ", ".join(f"`{p}`" for p in seen_at[:3]) or f"_{e['status']}_"
        if len(seen_at) > 3:
            where += f" and {len(seen_at) - 3} more"
        w(f"| `{e['name']}` | {e['n_declarations']} | {ident} | {where} "
          f"| `{e['recovery']['id']}` |")
    w("")
    return "\n".join(L)


# =====================================================================
# 9. SELF-TEST
# =====================================================================

def selftest():
    """Two opposite cases for each thing this module decides, run on the live tree."""
    global DATA_ROOT, SHIPPING                                           # noqa: PLW0603
    failures = []

    def check(what, ok):
        print(f"  {'ok  ' if ok else 'FAIL'}  {what}")
        if not ok:
            failures.append(what)

    check("a glob name is called a pattern", is_pattern("mid_series_*.npz"))
    check("a plain name is not called a pattern", not is_pattern("mid_series_BTC.npz"))

    idx = {"aa" * 32: ["/x/y/z.npz"]}
    hit = resolve_identity("aa" * 32, {"/x/y/z.npz"}, idx)
    check("an identity at its recorded address reads as present there",
          hit["status"] == "present_at_the_recorded_path")
    moved = resolve_identity("aa" * 32, {"/somewhere/else/z.npz"}, idx)
    check("the same identity elsewhere reads as off the recorded address",
          moved["status"] == "present_off_the_recorded_path")
    gone = resolve_identity("bb" * 32, {"/x/y/z.npz"}, idx)
    check("an identity nothing carries reads as absent",
          gone["status"] == "absent_from_the_search_area")

    r = recovery_of("2026-06-20.ndjson.gz", set(), set())
    check("a forward-recorder day is classed as not recoverable",
          r["id"] == "recorded_forward_no_backfill")
    r = recovery_of("trades_2025_12.tar", set(), set())
    check("the public archive tar is classed as a free download",
          r["id"] == "free_public_archive")
    r = recovery_of("quickwin_markouts.npz", set(), {"quickwin_markouts.npz"})
    check("a file this pipeline writes is classed as rebuildable before any download",
          r["id"] == "rebuilt_by_this_pipeline")
    r = recovery_of("settings.py", {"settings.py"}, {"settings.py"})
    check("a tracked file is classed as carried by the clone, ahead of a rebuild",
          r["id"] == "in_this_repository")
    r = recovery_of("nothing_named_like_this.bin", set(), set())
    check("an unmatched name is not classified rather than guessed",
          r["id"] == "not_classified")

    check("a path inside the tree is shown relative to it",
          _show(os.path.join(HERE, "settings.py")) == "settings.py")
    check("a path outside the tree is shown relative to the workspace",
          _show(os.path.join(DATA_ROOT, "raw", "x.tar")).startswith("../02_data/"))
    check("no absolute path of this machine survives the display",
          not _show(os.path.join(DATA_ROOT, "raw", "x.tar")).startswith(os.sep))

    days = _declared_days({"s3://b/node_fills_by_block/hourly/20251204/": None,
                           "quickwin_markouts.npz": None})
    check("a day is read out of a declared remote prefix", "20251204" in days)
    check("a local name contributes no day", len(days) == 1)

    # THE CLONE A STRANGER GETS. The data directories are outside this repository and a
    # clone does not carry them, so the two states of that root are the pair that
    # decides whether this module is usable by a reader who clones the repository. An
    # absent root has to come back as one area marked absent and a register over the
    # tree, and never as a disk full of files that are gone.
    real = DATA_ROOT
    try:
        DATA_ROOT = os.path.join(HERE, "a_directory_that_is_not_here")
        areas = search_areas()
        gone = [a for a in areas if a["id"] == "data"][0]
        check("a missing data root is reported as an absent area", not gone["present"])
        check("an absent area contributes no files",
              not any(files_[0] == "data" for files_ in area_files(areas).values()))
    finally:
        DATA_ROOT = real
    here = [a for a in search_areas() if a["id"] == "data"][0]
    check("the data root of this machine is reported as present", here["present"])

    # THE MODE'S OWN PAIR. The shipped area is a RESTRICTION, and a restriction that is
    # not measured cannot be told apart from a workspace that happens to be empty: both
    # print the same short table. So the two modes are run against each other on the live
    # tree, and the claim is the difference between them rather than either one alone.
    def declared_address(shown):
        """True for an address inside a root the shipped mode says it searched."""
        return (not shown.startswith("..")
                or shown.startswith("../02_data" + os.sep)
                or shown.startswith("the parent workspace: "))

    real_mode = SHIPPING
    try:
        SHIPPING = True
        shipped = {_show(p) for p in area_files(search_areas())}
        SHIPPING = False
        walked = {_show(p) for p in area_files(search_areas())}
    finally:
        SHIPPING = real_mode
    check("every address of the shipped area sits in a root the file declares",
          all(declared_address(s) for s in shipped))
    check("the walk reaches addresses the shipped area leaves out, so the shipped "
          "silence is a boundary and not an empty workspace",
          any(not declared_address(s) for s in walked))
    check("the walk is the larger of the two areas", len(walked) > len(shipped))

    print(f"\n  {len(failures)} failure(s)")
    return 1 if failures else 0


# =====================================================================
# 10. ENTRY POINT
# =====================================================================

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[5])
    parser.add_argument("--selftest", action="store_true",
                        help="run the two-opposite-cases battery and write nothing")
    parser.add_argument("--stdout", action="store_true",
                        help="print the document and write nothing at all")
    parser.add_argument("--full-local-census", action="store_true",
                        help="replace the declared documents area with a walk of the "
                             "whole workspace. It describes one machine, so it prints "
                             "and never writes the two files this repository ships")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()

    global SHIPPING                                                      # noqa: PLW0603
    SHIPPING = not args.full_local_census
    # THE SHIPPED FILES ARE BUILT BY THE SHIPPED MODE, AND THAT IS A GATE RATHER THAN A
    # HABIT. The two modes differ in what their addresses are about, so a local census
    # written over the shipped names would put the directories of one working copy into a
    # file a stranger reads, which is the defect the modes exist to separate.
    if not SHIPPING and not args.stdout:
        print("REFUSED: --full-local-census describes one machine and does not write the "
              "files this repository ships. Add --stdout to read it.", file=sys.stderr)
        return 2

    started = artifact.start_clock()
    clock = time.time()

    decls, n_with_list = declarations()
    rows = name_rows(decls)
    areas = search_areas()
    files = area_files(areas)
    wanted_sizes = {i["bytes"] for row in rows.values()
                    for i in row["identities"].values() if i["bytes"]}
    wanted_names = {n for n in rows if n and "://" not in n and not is_pattern(n)}
    print(f"[data_register] {len(decls)} declarations over {len(rows)} names; "
          f"{len(files)} files in the area, hashing those of "
          f"{len(wanted_sizes)} declared sizes")
    index, index_stats = content_index(files, wanted_sizes, wanted_names)
    print(f"[data_register] hashed {index_stats['n_files_hashed']} files, "
          f"{index_stats['bytes_hashed'] / 2**30:.2f} GB, in "
          f"{time.time() - clock:.1f} s")

    tracked = tracked_names()
    outputs = pipeline_outputs()
    entries = register(rows, index, tracked, outputs, files)
    census = undeclared_census(files, rows, index)
    calib = calibration(index, rows)
    matched = {e["recovery"]["id"] for e in entries}
    unmatched = [r["id"] for r in RECOVERY if r["id"] not in matched]

    tot = totals(entries)
    text = document(entries, areas, index_stats, census, calib, decls, tot)

    # A calibration that failed is not a footnote under a table: it says the table's
    # numbers were taken with an instrument that does not work, so nothing is written.
    # Both pairs are gates, the census pair included, because the census is the half
    # that prints a zero and a zero is what an uncalibrated sorter prints best.
    cen = calib["the_census_of_undeclared_files"]
    failed = [f"{half}.{end}"
              for half, block in (("resolver", calib), ("census", cen))
              for end in ("must_fire", "must_be_silent")
              if not block[end]["passed"]]
    if failed:
        print(f"REFUSED: {', '.join(failed)} did not hold, so every count above was "
              "taken with an instrument that has not shown it works", file=sys.stderr)
        return 1

    if args.stdout:
        print(text)
        return 0

    with open(os.path.join(HERE, OUT_NAME), "w", encoding="utf-8") as handle:
        handle.write(text + "\n")
    print(f"[data_register] {tot['n_names_declared']} names, "
          f"{tot['n_found_off_the_recorded_path']} found off the recorded address, "
          f"{tot['n_absent']} absent, "
          f"{census['buckets']['undeclared']['n_files']} undeclared files in the data "
          f"directories -> {OUT_NAME}")

    artifact.write(
        OUT_JSON_NAME,
        results(entries, areas, index_stats, census, calib, decls, unmatched,
                n_with_list),
        script=__file__,
        inputs=[],
        scope={
            "population": (
                f"{len({d['artifact'] for d in decls})} artifacts of this repository "
                f"that declare what they read, {len(decls)} declaration edges and "
                f"{tot['n_names_declared']} distinct input names, resolved against "
                f"{index_stats['n_files_in_the_area']} files of the declared search "
                "area. The area is this repository, the six data directories of "
                "../02_data, and the documents of the parent workspace that "
                "artifacts of this repository declare as inputs, each named one at a "
                "time. The workspace itself is not walked, so no count here is a census "
                "of a local disk; an area that is not on the machine is reported absent "
                "rather than as missing files"),
            "window": ("n/a: this artifact describes the files this pipeline reads at "
                       "the moment of the run and covers no period of market data"),
            "coins": ("n/a: the unit here is a file and a declaration about a file, not "
                      "a trade"),
        },
        settings=dict(
            scoring_settings_apply=False,
            overrides_note=(
                "This producer measures the files of the pipeline and not the market. "
                "No markout is computed here, so every scoring field of this block "
                "states what settings.py declares and says nothing about this artifact. "
                "The inputs list is empty on purpose and the reason is the one "
                "build_declarations.py calls a walker: this producer reads every "
                "artifact and every file of three directory trees, so naming them as "
                "inputs would put thousands of edges in the graph and say less than the "
                "population field above already says"),
        ),
        started=started)
    print(f"[data_register] wrote {OUT_JSON_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
