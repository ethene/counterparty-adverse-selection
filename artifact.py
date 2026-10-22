#!/usr/bin/env python3
"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-07-30
References: none (repository infrastructure; the settings it stamps are declared in
settings.py, whose own references are listed there).

ONE PLACE WRITES A RESULTS FILE, SO EVERY RESULTS FILE SAYS THE SAME THINGS ABOUT
ITSELF.

Why this module exists. Sixty-eight files in this tree call json.dump themselves, and
each one decided on its own what to record about how the file was made. The result was
measured over the 74 tracked .json artifacts: 13 name the script that wrote them, 5
name their own inputs, 5 name how long the computation took, and 24 name the
population, window and coins the numbers cover. Two costs follow, and the second is
the one that has already been paid twice.

The first cost is that a reader cannot answer two ordinary questions without reading
code: is this file older than the script that writes it, and how long does recomputing
it take.

The second cost is that a census of the artifacts disagrees with itself, and the
disagreement is not small. Counted three ways on the same day, the number of artifacts
carrying a settings fingerprint came out as 24, as 32 and as 38, and all three counts
are correct about different things.

  24 is the count of files holding a key literally named settings_fingerprint.
  32 is the count of files holding the block, wherever it sits. Eight files hold it
     without that key name: seven of the m-group write its fields flat into _meta, and
     chk_settings_home_results.json puts it under _meta.settings.
  38 is the count of BLOCKS rather than files. Six artifacts carry two -- the four
     i3 files, own_size_control and panel_analyze -- because a sub-result inside them
     stamps its own.

The same confusion of blocks with files gave an earlier wrong number: the key "script"
occurs 20 times across 13 files, and 20 was reported as a count of files. None of this
is a lapse of attention. While sixty-eight independent places write the record, any two
censuses of it will differ, and the way to end that is one writer and one predicate.

So the record is written in one place: here.

THE SHAPE OF _meta, WHICH IS THE AGREEMENT WITH checks/chk_artifact_provenance.py.
That check counts these properties across the tree; this module is what makes them
countable by exactly one predicate, and describe() below IS that predicate, so the
check does not re-implement it.

    "_meta": {
      "artifact_meta_version": 1,
      "results_file": "<basename of this very file>",
      "producer": {"script": "<basename>", "sha256": "<hex>", "bytes": <int>,
                   "bytes_in_object_db": "present|absent|unasked",
                   "object_format": "<sha1|sha256|null>",
                   "object_id": "<hex|null>", "unasked_because": "<text|null>"},
      "inputs": [{"name": "<basename or URI>", "bytes": <int|null>,
                  "sha256": "<hex|null>", "present": <bool>}, ...],
      "scope": {"population": ..., "window": ..., "coins": ..., ...},
      "settings_fingerprint": {...},          # settings.fingerprint(), verbatim
      "run": {"runtime_s": <float>, "finished_utc": "...", "python": "...",
              "platform": "...", "packages": {...}}
    }
    <every key the producer computed follows, untouched>

Four notes on why each field is what it is.

  PRODUCER carries a hash of the script's own bytes, not a git commit. The question it
  answers is "is this artifact older than the code that writes it", and git cannot
  answer that: a script edited but not yet committed has the same commit as before,
  and an artifact written from a dirty tree records a commit that never produced it.
  The file's own hash has neither failure.

  It also carries, beside that hash, WHETHER THOSE EXACT BYTES ARE IN THE REPOSITORY'S
  OBJECT DATABASE at the moment of writing. The hash is a claim about the code that
  produced a number, and it is a claim anyone can check only while the bytes it names
  still exist somewhere. Four artifacts of this tree record a hash that resolves to no
  object at all: the runs happened on edited code that was overwritten before it was
  ever saved, so the distance between the recorded producer and the one on disk is not
  a distance anyone can measure, and no rerun can now reconstruct what was measured.
  Nothing said so at the time; it was noticed six weeks later. The field states the
  fact at the only moment when it is still cheap to establish. It does not refuse the
  write -- running a node on uncommitted code while the code is being worked on is
  ordinary and goes on working -- and what it stops is the record claiming a provenance
  it does not have. Three answers, never two; see OBJECT_DB_STATES below.

  INPUTS carry size and hash so a future build step can skip a script whose inputs did
  not move. Hashing is chunked and costs about a second per 1.3 GB here, so the
  largest input in the tree, panel_markouts_v2.npz at 572 MB, costs under half a
  second. An input that no longer exists at write time is recorded with present=false
  rather than raising, because the raw-tape parsers delete each day's hourly directory
  immediately after parsing it -- the system disk has about seven gigabytes free and
  cannot hold them.

  SCOPE is required and is never inferred. A check stamped ALL_PASS that had been run
  over a single hour of data once entered this project as a statement about the whole
  array. A field the caller must fill in is the only thing that stops that, because
  every inferred scope is inferred from something that was true of the run rather than
  of the question.

  RUN holds everything that may differ between two runs that produced identical
  numbers: elapsed seconds, the finishing timestamp, the interpreter and the versions
  of the libraries the producer had loaded. It is one nested container ON PURPOSE.
  Recomputing an artifact into a scratch directory and comparing it leaf by leaf
  against the one on disk is how this project tells "the code changed" from "the file
  is older than the code", and that comparison has to skip exactly one container. With
  volatile fields spread through the block, the comparer either hunts for them by name
  -- and a name added later is missed -- or reports a difference on every single run
  and stops being read. The invariant is therefore stated as a rule and tested below:
  everything outside _meta["run"] is byte-identical for two runs on the same inputs,
  settings and code.

WHAT THIS MODULE DOES NOT DO. It does not check a number. It makes a number traceable
to the script, the inputs and the settings that produced it, so that checking it costs
one run instead of a search. The numbers themselves are checked by the steps that own
them.

Usage from a producer:

    import artifact
    t0 = artifact.start_clock()
    ...
    artifact.write(
        "m7_size_results.json", results,
        script=__file__,
        inputs=["quickwin_markouts.npz", "quickwin_taker_map.json"],
        scope={"population": "2,480,267 taker fills, 966 wallets at the 50-fill floor",
               "window": "2025-12-04..2025-12-13, 10 days",
               "coins": ["BTC", "ETH"]},
        settings={"h": 10, "lens": "mid", "master_seed": 20260620},
        started=t0)

Self-test, since this repository has no separate test directory:

    uv run --no-project python3 artifact.py
"""
import datetime
import hashlib
import json
import os
import platform
import subprocess
import sys
import time

# The module's own directory. Every path this module builds starts here, so nothing it
# writes or reads depends on the working directory a producer happened to run from,
# and no absolute path is ever recorded. checks/chk_no_abs_paths.py enforces the rule
# across the tree; this is the module's share of it.
HERE = os.path.dirname(os.path.abspath(__file__))

META_KEY = "_meta"
VOLATILE_KEY = "run"          # the one container a leaf-by-leaf comparison skips
SHAPE_VERSION = 1

# The scope fields a caller must state. Named, not inferred; see the module docstring.
REQUIRED_SCOPE_KEYS = ("population", "window", "coins")

# The five records this module writes, in the canonical position of each. The
# provenance check iterates over this rather than retyping the names, which is what
# stops a census by key name from disagreeing with a census by content.
CANONICAL_FIELDS = ("producer", "inputs", "scope", "settings_fingerprint",
                    VOLATILE_KEY)

# Every spelling the tree used for these records before this module existed. They are
# listed for two reasons: describe() recognises them, so a census can report "recorded,
# but not in the canonical form" instead of "absent"; and write() refuses a payload
# that still carries one, because a record living in two places is the defect this
# module was written to end.
LEGACY_SPELLINGS = {
    "producer": ("script", "source_script"),
    "inputs": ("inputs", "source_files"),
    "scope": ("scope", "coverage"),
    VOLATILE_KEY: ("runtime_s", "seconds"),
    "settings_fingerprint": ("settings_fingerprint", "settings_module"),
}

# A runtime this long means the caller mixed two clocks rather than computed for a
# month. time.perf_counter() counts from an arbitrary origin, so subtracting it from
# time.time() yields about 1.7e9 seconds; the guard turns that into a message instead
# of a nonsense field nobody reads.
MAX_PLAUSIBLE_RUNTIME_S = 30 * 24 * 3600

# The three answers to "are the producer's exact bytes in the object database". They are
# named here so that a gate reading the field imports these rather than retyping the
# strings, the way checks/chk_artifact_provenance.py already takes its spellings from
# LEGACY_SPELLINGS instead of restating them.
#
# THREE, AND THE THIRD IS NOT THE SECOND. `absent` is the database answering no, which
# says a run happened on code nobody saved. `unasked` is there being no database to put
# the question to, which is the ordinary condition of anyone running this tree from an
# extracted archive or from a hosted notebook, where no repository was ever unpacked.
# Folding the two together would stamp every such reader's artifacts with the finding
# this field exists to raise, and a finding that fires on every honest run is one that
# gets read past.
OBJECT_DB_PRESENT = "present"
OBJECT_DB_ABSENT = "absent"
OBJECT_DB_UNASKED = "unasked"
OBJECT_DB_STATES = (OBJECT_DB_PRESENT, OBJECT_DB_ABSENT, OBJECT_DB_UNASKED)

# How long git is given to answer before the question is abandoned as unasked. The two
# commands run here are local and take about ten milliseconds each, measured on this
# repository; the ceiling is for the conditions where they do not return at all -- a
# repository on a volume that has gone away, a database another process is holding --
# because a record-keeping field must never be why a computation that finished loses
# its result.
GIT_PROBE_TIMEOUT_S = 10.0

# Whether a repository holds a directory, and how it names objects, cannot change while
# a producer runs, so it is asked once per directory. The saving is a whole git call --
# about ten milliseconds, which is twice the entire run of the cheapest producer here.
_OBJECT_FORMAT_CACHE = {}


def results_dir(name, default=None):
    """The directory of the results file called `name`, found by looking for it.

    WHY THIS EXISTS. Producers write their results beside themselves, so a producer
    that reads a SIBLING's results used to name the file beside itself too. Once the
    scripts were grouped into directories that stopped being true: sensitivity_rollup
    reads eight artifacts that now sit in five different groups. A table of names
    against groups would answer the question and would go stale the next time a script
    changes group, silently, because nothing checks a table. This looks instead, and it
    looks one level down because that is where a group sits.

    The caller keeps the file NAME as the last component of its own join, which is what
    the build graph folds an input edge out of. Handing back a directory rather than a
    full path is what preserves that.
    """
    if os.path.isfile(os.path.join(HERE, name)):
        return HERE
    for entry in sorted(os.listdir(HERE)):
        if entry.startswith(".") or entry.startswith("__"):
            continue
        candidate = os.path.join(HERE, entry)
        if os.path.isdir(candidate) and os.path.isfile(
                os.path.join(candidate, name)):
            return candidate
    # Absent is the caller's business: several callers treat a missing artifact as a
    # section they cannot fill rather than as a failure, and a raise here would turn
    # that into one. The directory handed back is where the caller would have looked.
    return HERE if default is None else default


def start_clock():
    """The value to hand back as `started`. Wall clock, deliberately.

    A monotonic clock would be the textbook choice for an interval, but producers here
    already hold a time.time() from their own opening lines, and a block that silently
    accepts either clock would record a runtime wrong by the machine's uptime. One
    clock, named in one place, plus the guard on the resulting value.
    """
    return time.time()


# How often a long loop says where it is. A tenth of the draws is the coarsest report
# that still distinguishes a slow run from a stopped one, and it caps the noise at ten
# lines per loop no matter how many draws the loop makes.
PROGRESS_FRACTION = 0.10


def progress(label, done, total, started, every=None, stream=None):
    """Report where a long loop has got to, on a schedule, and return whether it spoke.

    WHY THIS EXISTS AT ALL. maker_econ.py runs for 83 minutes and own_size_control.py
    for 115, both measured from their own artifacts, and neither prints a character
    between its opening banner and its results. A long computation that says nothing
    is indistinguishable from a stopped one from the outside, so the only way to tell
    a live run from a dead one was to wait for it to end -- which is the same
    information, arriving too late to act on.

    WHY IT REPORTS TIME AS WELL AS COUNT. A fraction alone says how far a loop has
    come and not how long the rest will take, and those differ whenever the draws are
    not equally expensive. The remaining estimate is the elapsed time scaled by the
    draws left, which assumes they are; the assumption is stated in the line itself by
    printing both numbers, so a reader who watches the estimate move knows it was
    wrong rather than having to guess.

    It prints and nothing else. No generator is touched, no array is read, so a run
    with progress reporting and a run without draw the same numbers in the same order.

    label   what is running, printed as the line's prefix.
    done    draws finished, counted from 1.
    total   draws the loop will make.
    started the value artifact.start_clock() returned, for the elapsed time.
    every   print every this many draws. Default is a tenth of the total, at least one.
    """
    if total <= 0:
        return False
    if every is None:
        every = max(1, int(total * PROGRESS_FRACTION))
    if done % every and done != total:
        return False
    elapsed = time.time() - float(started)
    frac = done / total
    remaining = elapsed * (total - done) / done if done else float("nan")
    print(f"[{label}] {done:,}/{total:,} draws ({frac:6.1%}) "
          f"elapsed {elapsed / 60:.1f} min, {total - done:,} left "
          f"(~{remaining / 60:.1f} min at this rate)",
          file=stream, flush=True)
    return True


def sha256_file(path, chunk=1 << 20):
    """Hash a file's bytes in chunks, so a 572 MB input does not enter memory whole."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def _object_format(directory):
    """How the repository holding `directory` names its objects, or None if none does.

    MEASURED RATHER THAN ASSUMED, and the assumption would not be harmless. A repository
    initialised for sha256 gives identical bytes a different name than one on sha1, so a
    probe that took sha1 for granted would report every artifact of such a tree as
    missing from a database that in fact holds it -- a whole tree of false alarms, and
    ones indistinguishable in the record from a whole tree of unsaved runs.

    One command answers both halves of the question. It fails outside a repository and
    prints the format inside one, so asking it is also how "there is no database here"
    is established, and the two facts cannot come from two commands that disagree.
    """
    if directory in _OBJECT_FORMAT_CACHE:
        return _OBJECT_FORMAT_CACHE[directory]
    proc = subprocess.run(["git", "rev-parse", "--show-object-format"],
                          cwd=directory, capture_output=True, text=True,
                          timeout=GIT_PROBE_TIMEOUT_S)
    fmt = proc.stdout.strip() if proc.returncode == 0 else ""
    _OBJECT_FORMAT_CACHE[directory] = fmt or None
    return _OBJECT_FORMAT_CACHE[directory]


def _object_name(path, object_format):
    """The name git would give these bytes: type, length, a NUL, then the content.

    COMPUTED HERE RATHER THAN ASKED OF `git hash-object`, and the reason is not the
    saved call. git applies the repository's clean filters before naming a blob, so in a
    tree that converts line endings it names the bytes that WOULD be stored rather than
    the bytes lying on disk. The `sha256` recorded beside this is a hash of the bytes on
    disk, and a gate resolving that hash against the blobs of the database is asking
    about those same bytes. Asking git here would let the two readings disagree, and the
    disagreement runs in the dangerous direction: the field would read `present` for
    bytes no gate can find. Computed this way the two questions are the same question.

    The formula is the one thing that can drift out of step with git, so the self-test
    holds it against `git hash-object` on a real repository rather than trusting it.

    The file is read whole, unlike sha256_file() beside it, because the length has to be
    hashed before the content and a second pass to measure it would let the two disagree
    if the file moved between them. A producer is tens of kilobytes; the chunked reader
    exists for the 572 MB inputs, which never reach here.
    """
    with open(path, "rb") as fh:
        content = fh.read()
    h = hashlib.new(object_format)
    h.update(b"blob %d\0" % len(content))
    h.update(content)
    return h.hexdigest()


def _unasked(reason, object_format=None, object_id=None):
    """The producer record for a question that could not be put, with why beside it."""
    return {"bytes_in_object_db": OBJECT_DB_UNASKED, "object_format": object_format,
            "object_id": object_id, "unasked_because": reason}


def _object_db_record(script_path):
    """Whether the producer's exact bytes are a blob of the object database, and its name.

    WHAT IT SAYS, EXACTLY. That a blob of these bytes exists, which is weaker than their
    being reachable from a commit: a blob added and never committed, or left behind by a
    branch since deleted, counts here. The weaker statement is the one measured because
    it is the one the recorded hash needs -- a hash that resolves to no object at all is
    the failure, and reachability would cost a walk of the whole history at every write.
    The field is named for what it measures, so nothing has to remember the difference.

    IT RECORDS AND DOES NOT REFUSE. A node run on code still being edited is ordinary
    and goes on working. What stops is the record claiming a provenance it does not have.

    EVERY FAILURE ENDS IN `unasked` WITH A REASON, AND NONE ENDS IN A RAISE. No git on
    the machine, no repository above the producer, a database that will not answer: a
    field about record-keeping must not be why a computation that succeeded loses its
    result. The reason names the EXCEPTION TYPE and never its message, because a message
    carries the path it failed on, and an absolute path is the one thing that may not
    enter an artifact of this tree -- checks/chk_no_abs_paths.py holds that with an empty
    list of exceptions. Swallowing a failure silently is the habit that makes a zero
    unreadable; swallowing it into a field the artifact carries is the opposite.
    """
    directory = os.path.dirname(script_path)
    object_format = object_id = None
    try:
        object_format = _object_format(directory)
        if object_format is None:
            return _unasked("no repository holds the producer, so there is no object "
                            "database to ask; this is what a run from an extracted "
                            "archive or a hosted notebook records")
        object_id = _object_name(script_path, object_format)
        proc = subprocess.run(["git", "cat-file", "-e", object_id], cwd=directory,
                              capture_output=True, text=True,
                              timeout=GIT_PROBE_TIMEOUT_S)
    except Exception as exc:
        return _unasked("the object database could not be asked: "
                        + type(exc).__name__, object_format, object_id)
    if proc.returncode in (0, 1):
        # Nought is the object being there and one is it not. Anything else is git
        # declining to answer -- a name it will not parse, a database it cannot read --
        # and declining is a third thing rather than a no. Measured on this repository:
        # a well-formed name that is absent returns 1 and says nothing, and a name that
        # is not a name at all returns 128.
        state = OBJECT_DB_PRESENT if proc.returncode == 0 else OBJECT_DB_ABSENT
        return {"bytes_in_object_db": state, "object_format": object_format,
                "object_id": object_id, "unasked_because": None}
    return _unasked(f"git declined to answer, exit {proc.returncode}",
                    object_format, object_id)


def _record_name(spec):
    """What an input is called in the record.

    A local path collapses to its basename: the directory names the machine, which
    neither reproduces nor belongs in a published artifact. A URI is kept whole, because
    for the two Amazon buckets the bucket and key ARE the identity of the input and
    contain nothing local.
    """
    text = str(spec)
    return text if "://" in text else os.path.basename(text.rstrip(os.sep))


def input_record(spec, base_dir=None):
    """One entry of the inputs list: name, size and hash of what was read.

    A relative path is resolved against base_dir -- the producer's own directory --
    before the working directory is tried. The producers name their inputs relatively
    ("quickwin_markouts.npz"), so resolving against the working directory would make
    the record depend on where the run was launched from: the same producer would
    record a hash from the repository root and present=false from anywhere else. Two
    artifacts disagreeing because they were written from different directories is the
    defect checks/chk_no_abs_paths.py exists for, and it applies to what a file records
    as much as to what it reads.

    An input that is not a readable local file is recorded with present=false and no
    hash. That is the honest record for the two cases that occur here: a bucket URI,
    and a parsed day whose hourly directory the producer deleted to stay inside the
    disk budget.

    A DIRECTORY THAT EXISTS IS NOT ABSENT, and until 2026-08-04 this recorder said it
    was. Presence was decided by isfile, so an input naming a directory -- an hourly
    cache kept on disk, a shard folder -- was written present=false with no hash, which
    reads as "the input is gone". Measured that day on two inputs, l2_cache and binance:
    the lead-lag probe computed a result from data it recorded as missing. The direction
    was safe, an instrument overstating a shortage rather than hiding one, but the two
    facts are different and a record that conflates them cannot be read.

    Presence is therefore decided by exists, and kind says which case a reader is
    looking at, so that "no hash" carries its reason with it: a directory has no single
    hash to record, a URI is not local at all, and an absent path is the one that owes
    a rebuild.
    """
    name = _record_name(spec)
    path = str(spec)
    if "://" in path:
        return {"name": name, "bytes": None, "sha256": None,
                "present": False, "kind": "uri"}
    candidates = [path] if os.path.isabs(path) else \
        ([os.path.join(base_dir, path)] if base_dir else []) + [path]
    for candidate in candidates:
        if os.path.isfile(candidate):
            return {"name": name, "bytes": os.path.getsize(candidate),
                    "sha256": sha256_file(candidate), "present": True, "kind": "file"}
        if os.path.isdir(candidate):
            return {"name": name, "bytes": None, "sha256": None,
                    "present": True, "kind": "directory"}
    return {"name": name, "bytes": None, "sha256": None,
            "present": False, "kind": "absent"}


def _validate_scope(scope):
    """Refuse to write rather than accept a scope that says nothing.

    The refusal is the point of the field. An artifact whose scope is absent, empty or
    None reads exactly like an artifact computed over everything, and this project has
    already published a verdict taken from a check that had run over one hour of data.
    A caller for whom a field genuinely does not apply says so and says why, in the
    form "n/a: <reason>", which is a statement a reader can weigh.
    """
    if not isinstance(scope, dict):
        raise ValueError(
            "scope must be a mapping stating what the numbers cover, with the keys "
            f"{REQUIRED_SCOPE_KEYS}; it is never inferred, because an inferred scope "
            "describes the run rather than the question, and a check run over one "
            "hour of data has already been read here as a verdict over the whole "
            f"array (got {type(scope).__name__})")
    missing = [k for k in REQUIRED_SCOPE_KEYS if k not in scope]
    if missing:
        raise ValueError(
            f"scope is missing {missing}; state each of {REQUIRED_SCOPE_KEYS} "
            "explicitly, or give the string 'n/a: <reason>' for one that genuinely "
            "does not apply to this artifact")
    for key in REQUIRED_SCOPE_KEYS:
        value = scope[key]
        if value is None or (hasattr(value, "__len__") and len(value) == 0):
            raise ValueError(
                f"scope[{key!r}] is empty; an empty scope field reads exactly like a "
                "scope covering everything. Write what the numbers actually cover, or "
                "'n/a: <reason>'")
        if not isinstance(value, (str, list, tuple, dict, int)):
            raise ValueError(
                f"scope[{key!r}] is a {type(value).__name__}; a scope field is text, a "
                "list, a mapping or a count")
        if isinstance(value, str):
            text = value.strip()
            low = text.lower()
            if low.startswith("n/a") or low.startswith("not applicable"):
                reason = text.partition(":")[2].strip()
                if len(reason) < 4:
                    raise ValueError(
                        f"scope[{key!r}] declines the field without a reason; write "
                        "'n/a: <why this artifact has no such dimension>' so a reader "
                        "can weigh the omission instead of guessing at it")
            elif len(text) < 3:
                raise ValueError(
                    f"scope[{key!r}] is {text!r}, which states nothing "
                    "a reader can use")


def _json_default(obj):
    """Convert the few non-JSON types the producers actually hold.

    numpy is not imported here -- this module has no numeric dependency and the check
    that reads artifacts must run without one -- so numpy scalars and arrays are
    recognised by behaviour. .item() and .tolist() are exact for every dtype in this
    tree, so nothing is rounded on the way out. A set becomes a SORTED list, because an
    unsorted one would make the file differ between runs outside the volatile block and
    break the invariant this module promises.
    """
    if isinstance(obj, (set, frozenset)):
        return sorted(obj)
    if hasattr(obj, "item") and getattr(obj, "shape", None) == ():
        return obj.item()
    if hasattr(obj, "tolist"):
        return obj.tolist()
    if isinstance(obj, (datetime.date, datetime.datetime)):
        return obj.isoformat()
    raise TypeError(
        f"{type(obj).__name__} has no JSON form; convert it in the producer, where "
        "what it means is known, rather than here")


def _settings_fingerprint(settings_kwargs):
    """settings.fingerprint(**kwargs), imported without assuming the caller's sys.path.

    The keyword arguments are the caller's statement of what its run actually used.
    They are passed through untouched, so fingerprint() keeps its refusal to assert a
    migrating declaration the run did not confirm: an unstated one lands in
    declared_not_confirmed instead of being asserted. Filling those in here from the
    module's defaults would put a false statement into the very block a reader consults
    to check the artifact.
    """
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    import settings as S
    return S.fingerprint(**(settings_kwargs or {}))


def _volatile_block(started):
    """Everything two runs may legitimately differ in while every number matches."""
    runtime = time.time() - float(started)
    if runtime < 0 or runtime > MAX_PLAUSIBLE_RUNTIME_S:
        raise ValueError(
            f"runtime came out as {runtime:.1f} s, which is not an elapsed time; "
            "`started` must be the value of artifact.start_clock() taken when the "
            "computation began. A perf_counter() value passed here differs from the "
            "wall clock by the machine's uptime")
    # Versions of libraries the PRODUCER loaded, read from sys.modules rather than
    # imported. Nothing is pulled in that the run did not already use, and a number
    # that moves with a library version can be traced to the version that produced it.
    packages = {}
    for name in ("numpy", "scipy", "pandas", "sklearn", "statsmodels"):
        mod = sys.modules.get(name)
        version = getattr(mod, "__version__", None)
        if version:
            packages[name] = str(version)
    return {
        "runtime_s": round(float(runtime), 3),
        "finished_utc": datetime.datetime.now(datetime.timezone.utc)
                                .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "packages": packages,
    }


def _reserved_names():
    """Canonical keys plus every legacy spelling of the same records."""
    names = {"artifact_meta_version", "results_file"} | set(CANONICAL_FIELDS)
    for spellings in LEGACY_SPELLINGS.values():
        names |= set(spellings)
    return names


def write(out_name, payload, *, script, inputs, scope, started, settings=None,
          extra_meta=None, out_dir=None, indent=2, answered=True):
    """Write one results file with the _meta block above, and return its path.

    out_name    bare file name. A path with a directory in it is refused: an artifact
                lives beside the script that writes it, which is the convention the
                tree already follows, and refusing the path here is also what keeps an
                absolute path out of a published artifact.
    payload     what the producer computed. Kept verbatim; if it carries its own _meta,
                the descriptive keys survive and the records this module owns must be
                passed as parameters instead.
    script      the producer's __file__. Its basename, its hash, and whether those exact
                bytes are in the repository's object database are recorded; the
                directory it sits in is not.
    inputs      the files the producer read, as paths or URIs. An empty list is a
                statement that the producer reads no file, not a way to skip the
                field; a producer that reads a whole tree says so in scope instead of
                hashing every file of it.
    scope       population, window, coins. Required, never inferred.
    started     artifact.start_clock(), taken when the computation began.
    settings    keyword arguments for settings.fingerprint(): what this run USED.
    extra_meta  descriptive fields belonging in _meta that are not one of the records.
    out_dir     where to write. Defaults to the producer's own directory; a scratch
                run overrides it, and the value is never recorded in the file.
    answered    whether this run reached its verdict. False says the run could not ask
                its question at all -- the file it reads is not on this machine, the
                archive it needs was never fetched -- and then an artifact already on
                disk is LEFT ALONE and its path returned unchanged. See below.

    WHY A RUN THAT REACHED NO VERDICT MUST NOT WRITE. Measured on a clean clone of this
    repository: three results files lost most of their content to a run that had nothing
    to read. The largest fell from 529,834 bytes to 2,394 -- and those bytes were the
    evidence the file exists to carry, 965 published figures compared against their
    registered addresses with a false-acceptance rate measured beside them. Anyone
    checking this work by cloning it and running the gates therefore destroyed the very
    record they came to read, and nothing on the screen said so.

    The stub is not wrong about this machine. It is simply a smaller true statement than
    the one it replaces, and the screen already carries it: the gate prints UNCERTAIN
    and names the leg that could not run. So the file keeps the larger statement and the
    run keeps the smaller one, which is the only arrangement where a reader loses
    nothing. Where no artifact exists yet, the stub IS the best available record and is
    written normally.
    """
    if os.path.isabs(out_name) or os.sep in out_name or "/" in out_name:
        raise ValueError(
            f"out_name must be a bare file name, got {out_name!r}; the destination "
            "directory is the producer's own, or out_dir for a scratch run")
    if not isinstance(payload, dict):
        raise TypeError(
            f"payload must be a mapping, got {type(payload).__name__}; a results file "
            "whose top level is a list cannot carry a _meta block")

    _validate_scope(scope)

    script_path = os.path.abspath(script)
    producer = {
        "script": os.path.basename(script_path),
        "sha256": sha256_file(script_path),
        "bytes": os.path.getsize(script_path),
    }
    # Asked at the moment of writing, because it is the only moment when it can still be
    # answered: the bytes named by the hash above are on disk now and may not be an hour
    # from now. Measured on this repository: 25 ms for the first artifact a process
    # writes and 11 ms for every one after, the difference being the cached format. It
    # cannot raise.
    producer.update(_object_db_record(script_path))

    payload = dict(payload)
    carried = dict(payload.pop(META_KEY, {}) or {})
    for source, block in (("payload _meta", carried), ("extra_meta", extra_meta or {})):
        clash = sorted(set(block) & _reserved_names())
        if clash:
            raise ValueError(
                f"{source} still carries {clash}, which artifact.write records itself. "
                "Pass them as parameters and delete them from the block: a record kept "
                "in two places is what made one census of these files return 24 and "
                "another 32 for the same property")
    carried.update(extra_meta or {})

    meta = {
        "artifact_meta_version": SHAPE_VERSION,
        "results_file": out_name,
        "producer": producer,
        "inputs": [input_record(spec, os.path.dirname(script_path))
                   for spec in inputs],
        "scope": dict(scope),
        "settings_fingerprint": _settings_fingerprint(settings),
    }
    meta.update(carried)
    # The volatile container goes last, so a reader scrolling _meta meets the records
    # that identify the artifact before the ones that merely date it.
    meta[VOLATILE_KEY] = _volatile_block(started)

    document = {META_KEY: meta}
    document.update(payload)

    directory = out_dir if out_dir is not None else os.path.dirname(script_path)
    os.makedirs(directory, exist_ok=True)
    out_path = os.path.join(directory, out_name)
    if not answered and os.path.exists(out_path):
        # The run reached no verdict and an answer from a run that did is already here.
        # Say so on the screen, by name and by size, so that the file left in place is
        # never mistaken for this run's own output.
        print(f"[artifact] {out_name} LEFT AS IT WAS "
              f"({os.path.getsize(out_path)} bytes): this run reached no verdict, so it "
              f"does not overwrite the record of a run that did")
        return out_path
    # Written to a neighbouring temporary file and moved into place, so an interrupted
    # run leaves the previous artifact intact instead of a truncated file that the next
    # check reads as corrupt.
    tmp_path = out_path + ".partial"
    with open(tmp_path, "w", encoding="utf-8") as fh:
        json.dump(document, fh, indent=indent, default=_json_default)
        fh.write("\n")
    os.replace(tmp_path, out_path)
    return out_path


def read_meta(path):
    """The _meta block of an artifact on disk, or an empty mapping if it has none."""
    with open(path, encoding="utf-8") as fh:
        document = json.load(fh)
    if not isinstance(document, dict):
        return {}
    block = document.get(META_KEY)
    return block if isinstance(block, dict) else {}


def _fingerprint_form(meta, document):
    """Where the settings fingerprint sits: the canonical sub-block, flat, or nowhere.

    Both shapes are recognised on purpose. A census that looked only where the
    convention puts the block reported the eight m-group artifacts as unstamped, and
    that undercount reached this project's own documents twice.
    """
    block = meta.get("settings_fingerprint")
    if isinstance(block, dict) and block.get("settings_module"):
        return "nested"
    if meta.get("settings_module"):
        return "flat"

    def anywhere(node):
        if isinstance(node, dict):
            if node.get("settings_module"):
                return True
            return any(anywhere(v) for v in node.values())
        if isinstance(node, list):
            return any(anywhere(v) for v in node)
        return False

    return "elsewhere" if anywhere(document) else None


def describe(source):
    """What one artifact records about its own making. THE census predicate.

    Takes a path or an already-loaded document. Returns, for each of the five records,
    whether it is present at all -- under the canonical name or any legacy spelling --
    and whether it is present in the canonical form. checks/chk_artifact_provenance.py
    counts these fields across the tree and does not define them again, which is the
    whole point: while the record had sixty-eight authors, three honest censuses of it
    returned 24, 32 and 38 for one property.

    One verdict per FILE, deliberately. Two of those three numbers differ because a
    count of key occurrences was read as a count of files, and a census summing this
    function cannot make that mistake: six artifacts here carry two fingerprint blocks
    and each still returns one verdict.
    """
    if isinstance(source, (str, bytes, os.PathLike)):
        with open(source, encoding="utf-8") as fh:
            document = json.load(fh)
    else:
        document = source
    if not isinstance(document, dict):
        return {"has_meta": False, "complete": False,
                "missing": list(CANONICAL_FIELDS), "records": {},
                "note": "top level is not a mapping, so it cannot carry _meta"}

    meta = document.get(META_KEY)
    meta = meta if isinstance(meta, dict) else {}
    records, missing = {}, []
    for field in CANONICAL_FIELDS:
        if field == "settings_fingerprint":
            form = _fingerprint_form(meta, document)
            entry = {"present": form is not None, "canonical": form == "nested",
                     "form": form}
        elif field == VOLATILE_KEY:
            block = meta.get(VOLATILE_KEY)
            canonical = isinstance(block, dict) and "runtime_s" in block
            legacy = any(name in meta for name in LEGACY_SPELLINGS[VOLATILE_KEY])
            entry = {"present": bool(canonical or legacy), "canonical": bool(canonical)}
        elif field == "inputs":
            value = meta.get(field)
            # An EMPTY list counts as canonical, because write() makes the parameter
            # mandatory: passing [] is the producer stating that it reads no file, and
            # a few genuinely do. A census that treated it as absent would leave a
            # floor under the bar that no migration could ever lift. The count is
            # reported so a reader can put its own bar on zero-input artifacts.
            canonical = isinstance(value, list)
            legacy = any(name in meta for name in LEGACY_SPELLINGS[field])
            entry = {"present": bool(canonical or legacy), "canonical": bool(canonical),
                     "n": len(value) if isinstance(value, list) else None}
        else:
            value = meta.get(field)
            canonical = isinstance(value, (dict, list)) and len(value) > 0
            if field == "producer":
                canonical = isinstance(value, dict) and bool(value.get("script")) \
                    and bool(value.get("sha256"))
            legacy = any(name in meta for name in LEGACY_SPELLINGS[field])
            entry = {"present": bool(canonical or legacy), "canonical": bool(canonical)}
        records[field] = entry
        if not entry["canonical"]:
            missing.append(field)
    return {
        "has_meta": bool(meta),
        "meta_version": meta.get("artifact_meta_version"),
        "records": records,
        "complete": not missing,
        "missing": missing,
    }


def strip_volatile(document):
    """The document without the one container two runs may differ in.

    This is the comparison side of the invariant: recompute an artifact into a scratch
    directory, pass both through this, and any remaining difference is a difference in
    the numbers or in the code that made them.
    """
    if not isinstance(document, dict):
        return document
    out = dict(document)
    meta = out.get(META_KEY)
    if isinstance(meta, dict):
        meta = dict(meta)
        meta.pop(VOLATILE_KEY, None)
        out[META_KEY] = meta
    return out


# =====================================================================
# SELF-TEST
#
# In this module rather than in a test directory, because the repository has none and
# a reader cloning it runs what is in front of them. It writes into a temporary
# directory the operating system hands out, never into the repository.
# =====================================================================

def _self_test():
    import shutil
    import tempfile

    work = tempfile.mkdtemp(prefix="artifact_selftest_")
    failures = []
    not_run = []

    def check(name, ok, detail=""):
        print(f"  {'PASS' if ok else 'FAIL'}  {name}"
              + (f" -- {detail}" if detail else ""))
        if not ok:
            failures.append(name)

    def skip(name, why):
        """A case this machine cannot build. Counted apart from a pass, deliberately.

        Reported rather than dropped and never counted as a pass: two of the cases
        below need a repository to exist, and a machine without git cannot have one.
        Printing the gap is the difference between a case that did not run and a case
        that was loosened until it did.
        """
        print(f"  SKIP  {name} -- {why}")
        not_run.append(name)

    try:
        # An input with known bytes, so the recorded size and hash can be checked
        # against a hash computed the other way round.
        source = os.path.join(work, "an_input.json")
        with open(source, "w", encoding="utf-8") as fh:
            fh.write('{"rows": 3}')
        expected_hash = hashlib.sha256(open(source, "rb").read()).hexdigest()

        payload = {"headline_bps": 1.2345, "cells": [{"coin": "BTC", "n": 7}]}
        scope = {"population": "3 rows of a fixture, not market data",
                 "window": "no window: fixture written by the self-test",
                 "coins": "n/a: fixture carries no coin"}

        t0 = start_clock()
        first = write("selftest_results.json", payload, script=__file__,
                      inputs=[source], scope=scope, settings={"h": 10, "lens": "mid"},
                      started=t0, out_dir=work)

        with open(first, encoding="utf-8") as fh:
            doc = json.load(fh)
        meta = doc[META_KEY]

        # 1. The shape is the one the docstring declares, field by field.
        check("_meta is the first key",
              list(doc)[0] == META_KEY)
        check("shape has exactly the declared records",
              all(f in meta for f in CANONICAL_FIELDS),
              f"present: {[f for f in CANONICAL_FIELDS if f in meta]}")
        check("producer names the script by basename and hashes its bytes",
              meta["producer"]["script"] == os.path.basename(__file__)
              and meta["producer"]["sha256"] == sha256_file(os.path.abspath(__file__)))
        # End to end, through write() rather than through the helper alone: the state
        # is one of the three declared ones, and the two names that make the claim
        # checkable travel with it or are null together.
        check("producer says whether its own bytes are in the object database",
              meta["producer"]["bytes_in_object_db"] in OBJECT_DB_STATES
              and (meta["producer"]["object_id"] is None)
              == (meta["producer"]["object_format"] is None),
              f"{meta['producer']['bytes_in_object_db']}, "
              f"format {meta['producer']['object_format']}")
        # `kind` joined the record after this case was written, and the whole-dict
        # equality below then failed on every run -- correctly, since the shape had
        # moved -- while nothing in the battery ran this file, so the failure sat
        # unread. It is listed here rather than dropped from the comparison: a case
        # loosened until it passes stops being a case.
        check("input carries name, size, hash and kind",
              meta["inputs"][0] == {"name": "an_input.json", "bytes": 11,
                                    "sha256": expected_hash, "present": True,
                                    "kind": "file"},
              f"hash {meta['inputs'][0]['sha256'][:12]}...")
        check("scope is stored as given",
              meta["scope"] == scope)
        check("fingerprint sits in the canonical sub-block",
              meta["settings_fingerprint"].get("settings_module") == "settings.py")
        check("fingerprint still refuses what the run did not confirm",
              "declared_not_confirmed" in meta["settings_fingerprint"],
              "n_perm and the seed were not stated by this caller")
        check("runtime and every timestamp sit inside the one volatile container",
              meta[VOLATILE_KEY]["runtime_s"] >= 0
              and "finished_utc" in meta[VOLATILE_KEY],
              f"container is _meta[{VOLATILE_KEY!r}]")
        check("the payload is unchanged",
              {k: v for k, v in doc.items() if k != META_KEY} == payload)
        check("describe() calls the file complete",
              describe(first)["complete"] is True)

        # 2. An input named relatively is found beside its producer, not beside the
        #    working directory. The self-test runs from the repository root while the
        #    fixture producer and its input sit in the temporary directory, so a
        #    record resolved against the working directory would read present=false.
        fake_producer = os.path.join(work, "fixture_producer.py")
        with open(fake_producer, "w", encoding="utf-8") as fh:
            fh.write("# a stand-in producer for the self-test\n")
        relative = write("relative_input_results.json", payload, script=fake_producer,
                         inputs=["an_input.json"], scope=scope,
                         started=start_clock(), out_dir=work)
        record = read_meta(relative)["inputs"][0]
        check("a relative input is resolved against the producer's directory",
              record["present"] and record["sha256"] == expected_hash,
              f"cwd is {os.path.basename(os.getcwd())}, the input is not there")

        # 3. Nothing outside the volatile container moves between two runs. The second
        #    run is deliberately given a different `started`, so the volatile block is
        #    guaranteed to differ and the comparison is not passing by accident.
        time.sleep(0.01)
        second = write("selftest_results_again.json", payload, script=__file__,
                       inputs=[source], scope=scope, settings={"h": 10, "lens": "mid"},
                       started=start_clock() - 3.0, out_dir=work)
        with open(second, encoding="utf-8") as fh:
            doc2 = json.load(fh)
        a, b = strip_volatile(doc), strip_volatile(doc2)
        a[META_KEY] = {k: v for k, v in a[META_KEY].items() if k != "results_file"}
        b[META_KEY] = {k: v for k, v in b[META_KEY].items() if k != "results_file"}
        check("two runs agree everywhere outside the volatile container",
              json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True))
        check("the volatile container did differ, so the test above was not vacuous",
              doc[META_KEY][VOLATILE_KEY]["runtime_s"]
              != doc2[META_KEY][VOLATILE_KEY]["runtime_s"],
              f"{doc[META_KEY][VOLATILE_KEY]['runtime_s']} against "
              f"{doc2[META_KEY][VOLATILE_KEY]['runtime_s']}")

        # A producer that reads no file states so with an empty list, and the artifact
        # still counts as complete. Anything else would leave a floor under the
        # provenance bar that no migration could lift.
        none_in = write("no_inputs_results.json", payload, script=__file__, inputs=[],
                        scope=scope, started=start_clock(), out_dir=work)
        d_none = describe(none_in)
        check("an artifact stating zero inputs is still complete",
              d_none["complete"] and d_none["records"]["inputs"]["n"] == 0)

        # 4. A missing or empty scope field refuses the write. Silence here is the
        #    failure mode the field exists to prevent, so the test asserts that nothing
        #    was written as well as that the call raised.
        for bad, why in (
            ({"population": "x", "window": "y"}, "a missing key"),
            ({"population": "", "window": "y", "coins": ["BTC"]}, "an empty value"),
            ({"population": "x", "window": None, "coins": ["BTC"]}, "None"),
            ({"population": "n/a", "window": "y", "coins": ["BTC"]},
             "n/a without a reason"),
            (None, "no scope at all"),
        ):
            name = "refused_%s.json" % why.replace(" ", "_")
            try:
                write(name, payload, script=__file__, inputs=[source], scope=bad,
                      started=start_clock(), out_dir=work)
                check(f"scope with {why} is refused", False, "it was written")
            except ValueError:
                check(f"scope with {why} is refused",
                      not os.path.exists(os.path.join(work, name)),
                      "raised, and no file left behind")

        # 5. A payload still carrying a record this module owns is refused, because
        #    that is precisely how one property came to exist in two shapes.
        try:
            write("collide_results.json", {META_KEY: {"script": "old_way.py"}},
                  script=__file__, inputs=[], scope=scope, started=start_clock(),
                  out_dir=work)
            check("a payload keeping its own producer record is refused", False)
        except ValueError:
            check("a payload keeping its own producer record is refused", True)

        # 6. describe() sees a legacy artifact as recorded-but-not-canonical rather
        #    than as absent. This is the undercount that reached our own documents.
        legacy = {META_KEY: {"script": "m8_makerside.py", "settings_module":
                             "settings.py", "coverage": "10 days"}, "x": 1}
        d = describe(legacy)
        check("legacy spellings are seen as present but not canonical",
              d["records"]["producer"]["present"]
              and not d["records"]["producer"]["canonical"]
              and d["records"]["settings_fingerprint"]["form"] == "flat"
              and not d["complete"])

        # 7. A clock mix-up is caught rather than recorded.
        try:
            write("clockmix_results.json", payload, script=__file__, inputs=[],
                  scope=scope, started=time.perf_counter(), out_dir=work)
            check("a perf_counter value passed as `started` is refused", False)
        except ValueError:
            check("a perf_counter value passed as `started` is refused", True)

        # 8. `answered` in its three states. A rule with one case proves nothing: the
        #    case that must fire and the case that must stay silent are both needed,
        #    and here there is a third, because a stub with no artifact beside it is
        #    the best record available and must be written like any other.
        rich = write("answered_results.json", {"rows": list(range(400))},
                     script=__file__, inputs=[], scope=scope,
                     started=start_clock(), out_dir=work)
        big = os.path.getsize(rich)

        # 8a. MUST NOT WRITE: a run that reached no verdict, over an artifact that did.
        write("answered_results.json", {"rows": []}, script=__file__, inputs=[],
              scope=scope, started=start_clock(), out_dir=work, answered=False)
        check("a run that reached no verdict leaves the answering artifact alone",
              os.path.getsize(rich) == big,
              f"{os.path.getsize(rich)} bytes against {big}")

        # 8b. MUST WRITE: the same small payload, once `answered` says a verdict was
        #     reached. Without this case 8a would also pass on a write that never
        #     works at all.
        write("answered_results.json", {"rows": []}, script=__file__, inputs=[],
              scope=scope, started=start_clock(), out_dir=work, answered=True)
        check("an answering run does overwrite, so 8a is not a broken write",
              os.path.getsize(rich) < big,
              f"{os.path.getsize(rich)} bytes against {big}")

        # 8c. MUST WRITE: nothing on disk to protect, so the stub is the record.
        fresh = os.path.join(work, "unanswered_first_results.json")
        write("unanswered_first_results.json", {"rows": []}, script=__file__,
              inputs=[], scope=scope, started=start_clock(), out_dir=work,
              answered=False)
        check("with no artifact on disk, a run that reached no verdict still writes",
              os.path.exists(fresh))

        # 9. THE OBJECT DATABASE QUESTION IN ALL THREE OF ITS ANSWERS. Two of them need
        #    a repository, so one is built here: a temporary directory the operating
        #    system handed out, initialised, with one file committed into it. A fixture
        #    that is a real repository is the only fixture that proves anything, because
        #    what is under test is what git answers -- a stand-in carrying the expected
        #    string would measure the stand-in.
        def git_in(directory, *argv):
            return subprocess.run(["git"] + list(argv), cwd=directory,
                                  capture_output=True, text=True,
                                  timeout=GIT_PROBE_TIMEOUT_S)

        try:
            have_git = git_in(work, "--version").returncode == 0
        except Exception:
            have_git = False

        if have_git:
            repo = os.path.join(work, "fixture_repo")
            os.makedirs(repo)
            git_in(repo, "init", "-q")
            saved_producer = os.path.join(repo, "a_saved_producer.py")
            with open(saved_producer, "w", encoding="utf-8") as fh:
                fh.write("# a producer whose bytes were saved before it ran\n")
            git_in(repo, "add", "a_saved_producer.py")
            git_in(repo, "-c", "user.name=fixture", "-c",
                   "user.email=fixture@example.invalid", "commit", "-q", "-m",
                   "the fixture commit")

            # 9a. PRESENT.
            saved = _object_db_record(saved_producer)
            check("a producer whose bytes were saved is found in the object database",
                  saved["bytes_in_object_db"] == OBJECT_DB_PRESENT,
                  f"answer {saved['bytes_in_object_db']}, "
                  f"format {saved['object_format']}")

            # The one thing here that can drift away from git without anyone noticing
            # is the formula for an object name, since it is computed rather than asked
            # for. Held against git's own answer on the fixture, so drift fails a case
            # instead of quietly turning every reading into `absent`.
            check("the object name computed here is the name git gives the same bytes",
                  saved["object_id"]
                  == git_in(repo, "hash-object", "--", "a_saved_producer.py")
                  .stdout.strip(),
                  f"{(saved['object_id'] or '')[:16]}...")

            # 9b. ABSENT, in the exact shape of the defect: a producer edited after the
            #     commit that saved it. The old bytes are still in the database and the
            #     ones that would run are not, which is why the question has to be put
            #     about the content and not about the file's name or its history.
            with open(saved_producer, "a", encoding="utf-8") as fh:
                fh.write("# one line added after the commit, and not saved\n")
            edited = _object_db_record(saved_producer)
            check("a producer edited after its commit is absent from the database",
                  edited["bytes_in_object_db"] == OBJECT_DB_ABSENT,
                  f"answer {edited['bytes_in_object_db']}, "
                  f"and its name is recorded either way: "
                  f"{(edited['object_id'] or '')[:16]}...")
        else:
            skip("a saved producer reads present, an edited one reads absent",
                 "no git on this machine, so no fixture repository could be built")

        # 9c. UNASKED, and the case that must not read as 9b. Runs on every machine:
        #     without git the reason differs and the answer does not.
        bare = os.path.join(work, "no_repository_here")
        os.makedirs(bare)
        stranger = os.path.join(bare, "a_stranger_producer.py")
        with open(stranger, "w", encoding="utf-8") as fh:
            fh.write("# the same producer, on a machine holding no repository\n")
        unasked = _object_db_record(stranger)
        check("with no repository the question is unasked, NOT answered absent",
              unasked["bytes_in_object_db"] == OBJECT_DB_UNASKED
              and unasked["bytes_in_object_db"] != OBJECT_DB_ABSENT
              and bool(unasked["unasked_because"]),
              unasked["unasked_because"] or "no reason was recorded")
        check("an unasked question records no object name it did not compute",
              unasked["object_id"] is None and unasked["object_format"] is None)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    print("-" * 76)
    if not_run:
        print(f"  {len(not_run)} case(s) NOT RUN on this machine: "
              + "; ".join(not_run))
    print(f"  VERDICT: {'PASS' if not failures else 'FAIL ' + ', '.join(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    print("=" * 76)
    print("  artifact.py self-test -- the shape of _meta and the refusals that hold it")
    print("=" * 76)
    sys.exit(_self_test())
