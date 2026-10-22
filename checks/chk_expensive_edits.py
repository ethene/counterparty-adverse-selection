"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-07-31
References: none (repository gate; it declares no quantity of its own and reads only the
producer record artifact.py writes into every results file, and DEFERRED_EDITS.md).

A cosmetic edit to an expensive producer must not be made. This refuses it.

WHY THIS FILE EXISTS, in one paragraph. Every results file records the sha256 of the
bytes of the script that wrote it, and freshness is that hash against the script on
disk. So editing a producer -- even adding a comment -- makes a correct artifact stale,
and only a run restores the match. For the two heaviest nodes in this repository that
run costs 115 and 83 minutes by their own recorded runtime. On 2026-07-31 an edit that
added nothing but progress printing was made to the 115-minute node, and the repository
then spent 107 minutes recomputing it to buy back a log line. The rule against that was
written down the same day and did not hold, because it was a rule a person had to
remember. This check is the same rule with the remembering taken out.

WHAT IT DOES. For every producer whose recorded runtime is above a threshold, it
compares the script on disk against the version its artifact was written from, and
classifies the difference:

    substantive   the computation changed. The recompute is owed and this check says so
                  without objecting: that is the price of a real change.
    cosmetic      the computation did NOT change. Only printing, comments, docstrings or
                  formatting moved. The recompute buys nothing, and the check FAILS.

HOW A PRODUCER IS FOUND, and why by name rather than by path. An artifact records its
producer as a bare file name, all 99 of them here, while the scripts themselves sit in
group directories. Joining that name onto the repository root therefore names a file that
mostly does not exist, and skipping the node when it does not exist reports a population
of one where the tree holds twenty-seven. The name is an identifier and a path is a
guess, so the name is resolved against every tracked script in the tree, and the recorded
bytes are found by hashing every version ever committed under that name rather than by
reading one path. A name matching two files would make the lookup a guess again, and a
name matching nothing cannot be judged at all: both are reported and both fail this
check, because passing over them in silence is what made the earlier count false.

HOW COSMETIC IS DECIDED, and why this predicate and not a diff. A textual diff cannot
tell a renamed local from a new branch. This parses both versions into syntax trees,
removes what cannot affect a number -- docstrings, and statements whose whole effect is
to emit output -- and compares what is left. If the remaining trees are identical the
edit cannot have moved a figure, whatever the diff looks like. If they differ at all,
the edit is called substantive: the check errs towards permitting a run, because a
false "cosmetic" would block a real fix, while a false "substantive" costs only that
this check stays quiet.

WHAT TO DO WHEN IT FAILS. Do not run the node to make the check green: that is paying
the very price the check exists to prevent. Put the edit in DEFERRED_EDITS.md, revert
it in the source, and let it land with the next change that reruns that node anyway.
The file is read by this check, so a deferred edit is a declared debt with a place to
live rather than a note in somebody's head.

Run:
    uv run --no-project python3 checks/chk_expensive_edits.py
"""

import ast
import collections
import hashlib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import artifact  # noqa: E402
# The register of neutrality certificates is READ THROUGH ITS OWNER, never reimplemented
# here. Two gates that ask one question must consult one list, and consult it by calling:
# when chk_run_happened.py kept its own idea of what was excused, one gate called four runs
# missing while the other called the same four proven harmless, and neither was wrong about
# the question it had actually asked.
import chk_artifact_provenance as _prov  # noqa: E402
# evidence is imported by the battery wrapper; this check prints its own three
# lines -- expectation, fact and place -- for every finding, which is what the
# evidence rule asks for.

# A node is "expensive" when its own artifact says it took longer than this. The number is
# in seconds and it is a policy, not a measurement: below it, a wasted rerun is an
# annoyance; above it, it is an evening. Where the policy is set, though, was measured, on
# 2026-08-20 over the 99 tracked artifacts that record a runtime. The bar separates two
# populations that do not overlap and do not even come close. Below it are the checks in
# this directory: 24 of the 25 artifacts written from here run under ninety seconds, with a
# median of 1.71 s, so re-running one to settle a question costs nothing worth arguing
# about. Above it are the 26 producers the bar then selects, from 105.7 s to 6670.7 s and
# 334 minutes in total. No artifact in the repository records a runtime anywhere between
# 84.29 s and 105.70 s, so ninety sits inside an empty gap and no node is near the edge.
# The single check above the bar, chk_rowcounts_determinism.py at 311 s, is there because
# it re-parses the raw tape, which is the expense this bar is meant to catch.
EXPENSIVE_SECONDS = 90

# Functions whose entire purpose is to emit output. A statement that is one call to one
# of these, with its value discarded, cannot change a computed number. Anything else --
# including a call whose result is assigned, or one of these appearing inside a larger
# expression -- is kept and therefore counts as computation.
OUTPUT_CALLS = {"print", "progress", "write_line", "log", "info", "warning", "debug"}

DEFERRED = os.path.join(ROOT, "DEFERRED_EDITS.md")


def _tracked_json():
    out = subprocess.run(["git", "-C", ROOT, "ls-files", "*.json"],
                         capture_output=True, text=True)
    return out.stdout.split()


def _producer_index():
    """File name -> every tracked script carrying it, so a name can be resolved.

    A list and not a single path on purpose. One entry is a resolution; two entries are a
    collision and the caller must say so rather than take the first, which would answer a
    question it had not asked.
    """
    out = subprocess.run(["git", "-C", ROOT, "ls-files", "*.py"],
                         capture_output=True, text=True)
    index = collections.defaultdict(list)
    for rel in out.stdout.split():
        index[os.path.basename(rel)].append(rel)
    return index


_BLOBS = None


def _blobs_named(name):
    """Every version ever committed under this file name, as (blob id, the path it sat at).

    Listed from the object graph rather than from one path's history, so a file that was
    moved between directories still yields the versions written before the move. The whole
    listing is 3196 entries here and is taken once.
    """
    global _BLOBS
    if _BLOBS is None:
        out = subprocess.run(["git", "-C", ROOT, "rev-list", "--all", "--objects"],
                             capture_output=True, text=True)
        _BLOBS = collections.defaultdict(list)
        for row in out.stdout.splitlines():
            blob, _, path = row.partition(" ")
            if path:
                _BLOBS[os.path.basename(path)].append((blob, path))
    seen, out_rows = set(), []
    for blob, path in _BLOBS.get(name, []):
        if blob not in seen:
            seen.add(blob)
            out_rows.append((blob, path))
    return out_rows


def _newest_commit_holding(blob, path):
    """The last commit at which this path held these exact bytes, for the report line only.

    One call, reading the post-image blob of every commit that touched the path. The
    classification does not depend on this: it is the address a reader needs to go and look.
    """
    out = subprocess.run(["git", "-C", ROOT, "log", "--all", "--format=%H", "--raw",
                          "--abbrev=40", "--", path], capture_output=True, text=True)
    commit = None
    for row in out.stdout.splitlines():
        row = row.strip()
        if len(row) == 40 and not row.startswith(":"):
            commit = row
        elif row.startswith(":") and commit:
            fields = row.split()
            if len(fields) >= 4 and fields[3] == blob:
                return commit
    return None


def _sha256(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


class _Strip(ast.NodeTransformer):
    """Remove everything that cannot move a number: docstrings and pure output."""

    def _drop_docstring(self, node):
        body = list(node.body)
        if body and isinstance(body[0], ast.Expr) and isinstance(
                body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
            body = body[1:]
        node.body = body or [ast.Pass()]
        return node

    def visit_Module(self, node):
        self.generic_visit(node)
        return self._drop_docstring(node)

    def visit_FunctionDef(self, node):
        self.generic_visit(node)
        return self._drop_docstring(node)

    def visit_AsyncFunctionDef(self, node):
        self.generic_visit(node)
        return self._drop_docstring(node)

    def visit_ClassDef(self, node):
        self.generic_visit(node)
        return self._drop_docstring(node)

    def visit_Expr(self, node):
        """A bare call to an output function, value discarded, is not computation."""
        call = node.value
        if isinstance(call, ast.Call):
            fn = call.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
            if name in OUTPUT_CALLS:
                return None
        self.generic_visit(node)
        return node


def _drop_dead_locals(fn):
    """Remove simple assignments whose target nothing reads once printing is gone.

    Instrumenting a loop brings a clock with it: `t_cell = artifact.start_clock()`
    exists so the progress line can say how long the cell has taken. Strip the print
    and the assignment is left behind, read by nobody, and the trees differ over a
    variable that cannot reach a result. Only single-target assignments to a plain
    name are touched, and only when the name appears nowhere else in the function, so
    nothing with a second reader or a side effect through subscripting is removed.
    """
    for _ in range(3):
        reads = collections.Counter()
        for node in ast.walk(fn):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                reads[node.id] += 1
        removed = False
        for block in ast.walk(fn):
            body = getattr(block, "body", None)
            if not isinstance(body, list):
                continue
            keep = []
            for stmt in body:
                if (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1
                        and isinstance(stmt.targets[0], ast.Name)
                        and reads[stmt.targets[0].id] == 0):
                    removed = True
                    continue
                keep.append(stmt)
            if keep != body:
                block.body = keep or [ast.Pass()]
        if not removed:
            break


class _DropDeadParams(ast.NodeTransformer):
    """Remove parameters that exist only to carry text into a print, and their arguments.

    WHY THIS SECOND PASS IS NEEDED, and it is not a refinement but the whole point.
    The first version of this check was calibrated on the very edit it was written to
    prevent -- the progress printing added to the 115-minute node -- and it called that
    edit substantive. Instrumenting a loop is rarely one added print. It is a print
    plus a parameter threaded down to tell the print which cell is running, plus a
    keyword argument at every call site. Stripping the print alone leaves the parameter
    and the arguments, the trees differ, and the check waves through exactly what it
    exists to stop.

    A parameter that appears nowhere in the body once the output statements are gone
    cannot affect a number: nothing reads it. So it is dropped from the signature, and
    keyword arguments of that name are dropped from calls to that function. Positional
    arguments are left alone, because dropping one would shift the meaning of the rest.
    """

    def __init__(self):
        self.dead = {}          # function name -> parameters proved unread

    def visit_FunctionDef(self, node):
        self.generic_visit(node)
        _drop_dead_locals(node)
        used = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
        used |= {n.arg for n in ast.walk(node) if isinstance(n, ast.keyword) and n.arg}
        args = node.args
        positional = list(args.posonlyargs) + list(args.args)
        dropped = {a.arg for a in positional + list(args.kwonlyargs)
                   if a.arg not in used}
        if dropped:
            self.dead[node.name] = dropped
            # Defaults align with the TAIL of the positional list, so a default has to
            # be dropped by the index of its own parameter. Rebuilding by slicing what
            # is left keeps the count right and silently reassigns values to the wrong
            # parameters, which is how the first version let an instrumented loop pass.
            pad = [None] * (len(positional) - len(args.defaults)) + list(args.defaults)
            kept = [(a, d) for a, d in zip(positional, pad) if a.arg not in dropped]
            args.posonlyargs = [a for a in args.posonlyargs if a.arg not in dropped]
            args.args = [a for a in args.args if a.arg not in dropped]
            args.defaults = [d for _, d in kept if d is not None]
            kw_kept = [(a, d) for a, d in zip(args.kwonlyargs, args.kw_defaults)
                       if a.arg not in dropped]
            args.kwonlyargs = [a for a, _ in kw_kept]
            args.kw_defaults = [d for _, d in kw_kept]
        return node

    def visit_Call(self, node):
        self.generic_visit(node)
        fn = node.func
        name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
        dead = self.dead.get(name)
        if dead:
            node.keywords = [k for k in node.keywords if k.arg not in dead]
        return node


def _skeleton(src):
    """The part of a source file that can affect a number, as a comparable string.

    Two passes, and the order matters: output statements go first, then the parameters
    they were the only reader of. One pass alone lets an instrumented loop through.

    Returns None when the source does not parse, and the caller then declines to
    judge rather than guessing: an unparsable file is a finding of its own.
    """
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return None
    tree = _Strip().visit(tree)
    # Two sweeps: dropping a parameter can leave the next one unread in a chain of
    # helpers, and one sweep would stop at the first link.
    for _ in range(2):
        killer = _DropDeadParams()
        tree = killer.visit(tree)
        if not killer.dead:
            break
    ast.fix_missing_locations(tree)
    return ast.dump(tree, annotate_fields=True, include_attributes=False)


def _committed_source(name, sha):
    """The bytes the artifact was written from, found by content among versions of this name.

    Hashing every committed version is the only way to get the exact bytes: the recorded
    hash is of a version that may be several commits back, and reconstructing it from the
    current file is exactly the thing being tested. The search is over the file NAME and
    over raw bytes, so a producer that changed directory is still found, and so is one
    whose bytes would not survive a round trip through text decoding.
    """
    for blob, path in _blobs_named(name):
        raw = subprocess.run(["git", "-C", ROOT, "cat-file", "blob", blob],
                             capture_output=True)
        if raw.returncode:
            continue
        if hashlib.sha256(raw.stdout).hexdigest() == sha:
            return raw.stdout.decode("utf-8", "replace"), _newest_commit_holding(blob, path)
    return None, None


def _deferred_entries():
    """Node names OPEN in DEFERRED_EDITS.md, so a declared debt is not re-reported.

    Three things this reader must get right, and it got two of them wrong before.

    Only an open box excuses. A ticked entry means the edit has landed and the node has
    been rerun for a reason of its own, so the debt is spent; carrying on excusing that
    name lets the next cosmetic edit to the same producer through unremarked. Both entries
    in the file today are ticked, and both were being read as live.

    Only a line at the left margin is an entry. The Format section of that file shows the
    shape of an entry as an indented sample, and stripping the line before testing it made
    the sample indistinguishable from a record: `producer.py` was excused every run, and no
    such file exists in the tree. Fenced blocks are skipped for the same reason.
    """
    if not os.path.exists(DEFERRED):
        return set()
    names, fenced = set(), False
    with open(DEFERRED, encoding="utf-8") as fh:
        for line in fh:
            if line.lstrip().startswith("```"):
                fenced = not fenced
                continue
            if fenced or not line.startswith("- [ ] "):
                continue
            head = line[6:].split("—")[0].split(":")[0].strip().strip("`")
            if head.endswith(".py"):
                names.add(head)
    return names


def main():
    started = artifact.start_clock()
    deferred = _deferred_entries()
    index = _producer_index()
    tracked = _tracked_json()
    seen_json = with_record = 0
    rows, unparsable = [], []
    certified_by = {}
    for rel in tracked:
        path = os.path.join(ROOT, rel)
        try:
            with open(path, encoding="utf-8") as fh:
                doc = json.load(fh)
        except Exception:
            continue
        if not isinstance(doc, dict):
            continue
        seen_json += 1
        meta = doc.get("_meta") or {}
        producer = meta.get("producer")
        run = meta.get("run") or {}
        if not isinstance(producer, dict):
            continue
        seconds = run.get("runtime_s")
        script = producer.get("script")
        recorded = producer.get("sha256")
        if not (script and recorded and isinstance(seconds, (int, float))):
            continue
        with_record += 1
        if seconds < EXPENSIVE_SECONDS:
            continue
        # The recorded name is the identifier. Where the file sits is not recorded and must
        # not be guessed: joining the name onto the root is what emptied this population.
        candidates = index.get(os.path.basename(script), [])
        if not candidates:
            rows.append((script, rel, seconds, "unresolved", None, candidates))
            continue
        if len(candidates) > 1:
            rows.append((script, rel, seconds, "ambiguous", None, candidates))
            continue
        src_path = os.path.join(ROOT, candidates[0])
        on_disk = _sha256(src_path)
        if on_disk == recorded:
            rows.append((script, rel, seconds, "matches", None, candidates))
            continue
        was, commit = _committed_source(os.path.basename(script), recorded)
        if was is None:
            rows.append((script, rel, seconds, "undeterminable", None, candidates))
            continue
        with open(src_path, encoding="utf-8") as fh:
            now = fh.read()
        a, b = _skeleton(was), _skeleton(now)
        if a is None or b is None:
            unparsable.append(script)
            rows.append((script, rel, seconds, "undeterminable", None, candidates))
            continue
        kind = "substantive" if a != b else "cosmetic"
        if kind == "cosmetic":
            # A cosmetic edit is refused because it costs a whole runtime and buys nothing.
            # That premise fails when the edit already carries a neutrality certificate: the
            # register proves the figures cannot have moved, so no runtime is owed and there
            # is no cost to refuse. Reported under its own heading rather than folded into
            # the clean bucket, because a proof and an untouched file are different states.
            cert = _prov.neutral_certificate(ROOT, rel, recorded, on_disk)
            if cert:
                # The lookup answers narrowly by design -- it returns the register's own
                # issue date and evidence line, not the entry. The pair of hashes is
                # printed from THIS loop, where it was measured, rather than read back
                # out of the register: a field echoed from the document it is meant to
                # corroborate cannot corroborate it.
                certified_by[rel] = dict(cert, sha256_recorded=recorded,
                                         sha256_on_disk=on_disk)
                kind = "certified"
        rows.append((script, rel, seconds, kind, commit, candidates))

    certified = [r for r in rows if r[3] == "certified"]
    cosmetic = [r for r in rows if r[3] == "cosmetic" and r[0] not in deferred]
    excused = [r for r in rows if r[3] == "cosmetic" and r[0] in deferred]
    substantive = [r for r in rows if r[3] == "substantive"]
    matches = [r for r in rows if r[3] == "matches"]
    unknown = [r for r in rows if r[3] == "undeterminable"]
    unresolved = [r for r in rows if r[3] == "unresolved"]
    ambiguous = [r for r in rows if r[3] == "ambiguous"]

    line = "-" * 76
    print("=" * 78)
    print("  A COSMETIC EDIT TO AN EXPENSIVE PRODUCER - chk_expensive_edits")
    print("=" * 78)
    print(f"  population        : tracked results files whose _meta.run.runtime_s is at "
          f"least {EXPENSIVE_SECONDS} s")
    print(f"  predicate         : the artifact's recorded producer hash against the "
          f"script on disk; when they differ, the two versions are parsed, docstrings "
          f"and pure-output statements removed, and what remains compared")
    print(f"  producer found by : the recorded file NAME against every tracked script in "
          f"the tree, and the recorded bytes against every version ever committed under "
          f"that name; never by joining the name onto a directory")
    print()
    print(f"  tracked results files            : {seen_json}")
    print(f"      declaring producer and runtime: {with_record}")
    print(f"      of those, at least {EXPENSIVE_SECONDS} s      : {len(rows)}")
    print(f"  scripts tracked in the tree      : {sum(len(v) for v in index.values())} "
          f"under {len(index)} distinct names")
    print(f"      producers resolved           : {len(rows) - len(unresolved) - len(ambiguous)}")
    print(f"      names matching nothing       : {len(unresolved)}")
    print(f"      names matching two or more   : {len(ambiguous)}")
    print()
    print(f"  expensive nodes   : {len(rows)}")
    print(f"      up to date    : {len(matches)}")
    print(f"      substantive   : {len(substantive)}  (a real change; the rerun is owed)")
    print(f"      cosmetic      : {len(cosmetic)}  (the rerun buys nothing)")
    print(f"      certified     : {len(certified)}  (cosmetic, and "
          f"NEUTRAL_EDITS.json proves no figure can have moved, so no rerun is owed)")
    print(f"      deferred      : {len(excused)}  (cosmetic, and declared open in "
          f"{os.path.basename(DEFERRED)})")
    print(f"      undeterminable: {len(unknown)}")
    print(f"      unresolved    : {len(unresolved)}")
    print(f"      ambiguous     : {len(ambiguous)}")
    if substantive:
        print()
        for script, rel, sec, _, commit, cands in substantive:
            print(f"    SUBSTANTIVE {cands[0]}  ({sec / 60:.0f} min)")
            print(f"        the computation changed since {(commit or '?')[:12]}; "
                  f"{rel} is owed a run")
    if unknown:
        print()
        for script, rel, sec, _, _c, cands in unknown:
            print(f"    UNDETERMINABLE {cands[0] if cands else script}  ({sec / 60:.0f} min)")
            print(f"        the recorded bytes are in no committed version of this name, "
                  f"so there is nothing to compare against; {rel} was written from a "
                  f"version that never reached a commit")
    for script, rel, sec, _, commit, cands in unresolved:
        print()
        print(f"    UNRESOLVED {script}")
        print(f"        expected : the recorded producer name to match one tracked script")
        print(f"        found    : it matches none, so this node was not judged at all")
        print(f"        place    : {rel} records producer.script = {script}")
        print(f"        remedy   : correct the recorded name, or track the producer. A "
              f"node this check cannot see is a node it cannot protect, and reporting it "
              f"green would be the defect this check was repaired for.")
    for script, rel, sec, _, commit, cands in ambiguous:
        print()
        print(f"    AMBIGUOUS {script}")
        print(f"        expected : the recorded producer name to match one tracked script")
        print(f"        found    : it matches {len(cands)} -- {', '.join(cands)}")
        print(f"        place    : {rel} records producer.script = {script}")
        print(f"        remedy   : give the two files different names, or record the "
              f"producer with its directory. Taking the first would answer a question "
              f"this check was not asked.")
    for script, rel, sec, _, commit, cands in cosmetic:
        print()
        print(f"    COSMETIC {cands[0]}")
        print(f"        expected : the computation to have changed, or the file to be "
              f"untouched")
        print(f"        found    : only docstrings, comments or output statements moved "
              f"since {(commit or '?')[:12]}")
        print(f"        place    : {cands[0]} -> {rel}")
        print(f"        cost     : {sec / 60:.0f} minutes of recompute, buying no figure")
        print(f"        remedy   : revert it in the source and write it into "
              f"{os.path.basename(DEFERRED)}; it lands with the next run that node owes "
              f"anyway. Do NOT run the node to make this green.")
    for script, rel, sec, _, commit, cands in certified:
        cert = certified_by.get(rel) or {}
        print()
        print(f"    CERTIFIED {cands[0]}  ({sec / 60:.0f} min not owed)")
        print(f"        the edit is cosmetic, and NEUTRAL_EDITS.json carries this exact "
              f"pair of hashes for {rel}")
        print(f"        pair      : {str(cert.get('sha256_recorded'))[:12]} -> "
              f"{str(cert.get('sha256_on_disk'))[:12]}")
        print(f"        register  : issued {cert.get('issued_utc')}")
        print(f"        what it does NOT say: that the figure was right, only that this "
              f"distance cannot have moved it. A certificate dies the moment either hash "
              f"moves again, so this line is a statement about today.")
    if unparsable:
        print(f"\n    could not parse: {unparsable}")
    verdict = "FAIL" if (cosmetic or unresolved or ambiguous) else "PASS"
    print(line)
    print(f"  VERDICT: {verdict}")
    out = {
        "check": "expensive_edits",
        "verdict": verdict,
        "expensive_seconds": EXPENSIVE_SECONDS,
        "population": "tracked results files with a recorded producer and runtime",
        "predicate": ("recorded producer hash vs the script on disk, the script found by "
                      "resolving its recorded NAME against every tracked script in the "
                      "tree; on a difference, syntax trees compared with docstrings and "
                      "pure-output statements removed"),
        "counts": {"tracked_results_files": seen_json,
                   "declaring_producer_and_runtime": with_record,
                   "expensive_nodes": len(rows), "up_to_date": len(matches),
                   "substantive": len(substantive), "cosmetic": len(cosmetic),
                   "certified": len(certified),
                   "deferred": len(excused), "undeterminable": len(unknown),
                   "unresolved": len(unresolved), "ambiguous": len(ambiguous),
                   "tracked_scripts": sum(len(v) for v in index.values()),
                   "distinct_script_names": len(index)},
        "cosmetic": [{"script": c[0], "artifact": r, "runtime_s": sec}
                     for s, r, sec, _, _cm, c in cosmetic],
        "certified": [{"script": c[0], "artifact": r, "runtime_s": sec,
                       "sha256_recorded": (certified_by.get(r) or {}).get("sha256_recorded"),
                       "sha256_on_disk": (certified_by.get(r) or {}).get("sha256_on_disk"),
                       "register_issued_utc": (certified_by.get(r) or {}).get("issued_utc")}
                      for s, r, sec, _, _cm, c in certified],
        "substantive": [{"script": c[0], "artifact": r, "runtime_s": sec}
                        for s, r, sec, _, _cm, c in substantive],
        "undeterminable": [{"script": (c[0] if c else s), "artifact": r, "runtime_s": sec}
                           for s, r, sec, _, _cm, c in unknown],
        "unresolved": [{"recorded_name": s, "artifact": r, "runtime_s": sec}
                       for s, r, sec, _, _cm, c in unresolved],
        "ambiguous": [{"recorded_name": s, "artifact": r, "runtime_s": sec, "candidates": c}
                      for s, r, sec, _, _cm, c in ambiguous],
        "deferred_declared": sorted(deferred),
    }
    artifact.write("chk_expensive_edits_results.json", out, script=__file__,
                   inputs=[], started=started,
                   scope={"population": out["population"],
                          "predicate": out["predicate"],
                          "window": "n/a: this check reads source text and recorded "
                                    "metadata, never a market window",
                          "coins": "n/a: nothing here is measured per coin; the "
                                   "population is producers, not fills"},
                   out_dir=HERE)
    print(f"  results -> chk_expensive_edits_results.json")
    return 1 if verdict == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
