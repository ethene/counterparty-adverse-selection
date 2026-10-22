#!/usr/bin/env python3
"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-07-30
References: none (repository infrastructure; it declares no quantity of its own and
reads the records artifact.py writes and the declarations settings.py holds).

RECOMPUTING IS A BUILD, NOT A RITUAL.

Why this module exists. "Re-run everything" is the only recompute this repository has
ever had, and nobody can say what it costs: of the 74 tracked results files, 5 record
how long their own computation took. Some producers walk the raw tape and take hours;
most read a panel that is already parsed and take seconds. Running them as one
undifferentiated batch means the cheap work waits behind the expensive work, and a
setting that touches only the analysis re-walks the tape for no reason. This module
turns the recompute into a graph with a skip rule, so what runs is what has to.

WHAT THE GRAPH IS BUILT FROM, and why not from names. Every edge here comes from the
syntax tree of the script that makes it: the argument of np.load is an input, the
first argument of artifact.write is an output, open() with a writing mode is an
output. Deriving the same graph from name similarity was tried in this project and
attributed fourteen producers to one file, because eleven scripts mention an artifact
in a comment and three more read a file whose name shares a prefix. A mention is not
an edge.

The cost of the syntax-tree route is that a path this module cannot fold to a constant
is not an edge either, and on 31 July 2026 that cost was measured: 51 file operations
in 24 scripts folded to nothing, so a fiftieth of the repository's I/O was invisible
while the graph read as complete. Two thirds of the 51 were this module being too weak
rather than the code being unreadable -- a path handed to a one-line helper, a family
of files held in a dict, a loop variable over a glob -- and those are now folded here,
because an edge that CAN be derived must never be typed by hand: a typed edge goes
stale in silence, a derived one cannot. The rest is written down in
build_declarations.py with the reason each one is beyond folding, and the self-test
fails if a declaration ever names code that has moved. Between them the two cover every
I/O call in the tree, and UNRESOLVED_IO_CEILING holds that at zero as a declared debt
that may only be lowered.

ONE PRODUCER PER ARTIFACT is the rule the graph enforces. Where a script seems to break
it, the usual cause is that the script is not one node: i3_book_comparator.py writes
the book features under --stage feats and reads them back under --stage test, and read
as a single node that is a cycle with itself. panel_persistence.py has the same shape
under --build and --analyze. Both are declared as arms in build_declarations.py, one
node each, and the cycle resolves into the edge it always was. A conflict that is NOT
of that kind -- two different scripts writing one name -- the planner refuses to
schedule until the caller says which producer it means.

THE SKIP RULE, and what it is allowed to look at. A node is up to date when three
things all still hold, all three read out of the artifact's own _meta block:

    the producer hash recorded in the artifact equals the script on disk,
    every recorded input hash equals the file on disk,
    every setting the node's STAGE depends on is unchanged.

Nothing here consults a file date. That was measured rather than assumed: on 30 July
a results file was observed four minutes NEWER than its own script and computed under
the previous setting, because a long run that started before the edit finished after
it. A date answers "when was this written", never "what was it computed with".

AND THERE IS A THIRD ANSWER, WHICH IS NOT A SHADE OF EITHER. Each of the three
conditions above can fail to be ASKED at all, and the answer then is neither "skip"
nor "run": it is "cannot be told". An .npz carries no _meta block, so nothing about
its producer was ever recorded. A raw-tape node's input is deleted by the parser the
moment the day is parsed, so no input hash exists and none ever will while the tape
is not cached. Reading those as proof is how, on 31 July, two raw-tape nodes --
i3_book_comparator.py under --stage feats and i4_l2_mid.py -- printed "provably up to
date" with not one condition put; reading them as staleness would re-walk the tape on
every plan. So the fold lives in skip_rule.py, which keeps the three apart, and the
planner gives the third its own outcome: such a node is listed by name with the
reason its condition could not be put, and is NOT launched. Two explicit overrides
run it anyway -- --run-unprovable, or naming it with --only, since a person who names
a node has asked for it while the ancestors that target drags in behind it have not.

WHERE THE PRODUCER HASH IS COMPARED, AND WHY NOT HERE. Once. In
checks/run_record.py, which checks/chk_run_happened.py already calls as its second
leg and checks/chk_artifact_provenance.py already calls in freshness(). skip_rule.py
calls the same function with no reference moment, which is that module's way of
saying "ask the hash leg, do not ask whether a run happened". This module used to
hash the producer itself, which made three implementations of one predicate; two
implementations of one predicate is how two honest censuses of these artifacts once
returned 24 and 32 for a single property.

TWO STAGES, AND WHY THE SPLIT IS THE POINT OF THE THIRD CONDITION. Scripts that walk
the raw tape are a different kind of work from scripts that read a parsed panel: hours
against seconds, and a network fetch against a local read. If a tape node's skip rule
consulted the whole settings fingerprint, then changing the false-discovery rate --
which no marking has ever depended on -- would re-walk the tape. So a tape node's
third condition reads the MARKING settings only, and the marking settings are read off
the artifact's own columns rather than off a stamp: a marking is current when the file
carries a column for every horizon on the ladder, in every lens family it already
holds. An analysis node's third condition reads the settings fingerprint the artifact
stamped. The property this buys is checkable and the self-test checks it in both
directions: an analysis-only change plans no tape node, and a ladder change plans one.

TWO STAGES, AND THE IMPORT THAT CROSSED THEM. A script that walks the tape through a
module it imports is a tape walker, and three did: panel_build.py, panel_persistence.py
and panel_rebuild_v2.py call parse_day out of build_quickwin_markouts and name no
locator of their own. Read at their own call sites all three were analysis nodes, and
an analysis node is one an analysis-only setting is allowed to schedule -- so changing
the false-discovery rate would have planned three raw-tape walks. The stage predicate
is therefore transitive over local imports, and _spread_tape_stage does that.

AND TWO THINGS AN IMPORT STATEMENT AND A WRITE CALL DO NOT SAY. Transitivity read out
of ast.Import alone stops at a module loaded by path, and one script does that:
checks/chk_rowcounts_determinism.py builds a spec from the parser's file name and calls
its parse_day over 24 hours of a day. It was labelled analysis and scheduled on that
label. Likewise, a write read out of the first argument of a write call cannot see a
write with no call: panel_extended.py assigns the output name inside the module it
imports and lets that module do the writing, so it was not a node at all and seven
results files in the tree had no producer. DYNAMIC_IMPORTS and
_resolve_redirected_writes read both, by the same folder and with no name matching --
an assignment counts only when the attribute is one the target module's own writer
builds its path from.

THE STAGE STOPS AT A MODULE WHOSE ARMS DISAGREE. panel_persistence.py is a tape walker
under --build and an analysis node under --analyze. A script that imports it inherits
neither, because which arm an import means is not written in the import; the refusal is
recorded on the importer rather than left silent.

THE DISK LIMIT IS PART OF THE BUILD, and it is a policy this module declares rather
than a property of whatever machine the build runs on. A day of raw tape arrives as 24
compressed hourly files and a parser holds a day at a time, so the rule is one line:
PARSED PANELS ARE CACHED, AND A RAW DAY SURVIVES ONLY WHEN IT IS ASKED TO.

Four consequences follow, and they are set out with what enforces each rather than as
one claim, because they are not equally strong. A raw day is never a node of this
graph, so nothing can ask to keep one: a tape locator resolves to a CONDITION through
skip_rule.raw_tape_condition, never to a producer with an output. Tape nodes are
scheduled one at a time, and that is checked rather than intended -- the ceiling is
MAX_CONCURRENT_TAPE_NODES and a further tape node of the same plan is recorded
DEFERRED instead of launched, because two parsers each holding a day is how the volume
is actually filled. Free space is measured against a declared allowance before a tape
node launches, and both numbers travel into the build's own record so a reader judges
the margin instead of trusting it; the allowance is a policy figure and says so where
it is declared, never a measurement of any disk.

The fourth is the one that moved. Deletion is still the DEFAULT, but it is GATED, and
a day can now be kept: CAP_KEEP_RAW decides whether a parsed day survives and
CAP_RAW_CACHE says where it lives. Measured over the tree on 2026-08-20 rather than
assumed, every parser named in TAPE_PARSERS deletes under that key and not one deletes
unconditionally. Refetching is still never a reason to decline a recompute; it has
simply stopped being the only way to get a day back, which is what makes the raw input
of a tape node hashable at all.

What is NOT established here is how many days any particular volume can hold: that is a
fact about a machine, and this file states the allowance instead of guessing it. The
parsers are named in TAPE_PARSERS rather than counted, and parser_disposal() reads each
one's syntax tree and reports, per parser, every disposal call and the setting its
branch stands under, directly or through the parser it imports, so a parser that stops
deleting reads as one changed row rather than as a policy that quietly became false.

WHAT --what-if CAN AND CANNOT PRICE. It moves one field of the settings fingerprint and
counts what that would schedule, so it prices every setting an ARTIFACT records. Two
consequences follow from the stage split above and both are properties of the code
rather than of any tree. Every fingerprint field prices zero raw-tape walks, because a
tape node's third condition never reads the fingerprint. And the settings that DO move
the tape -- the three in MARKING_SETTINGS -- are not fingerprint fields, so they cannot
be named on this flag at all; the ladder move is exercised through marking_overrides,
which today only the self-test passes.

WHAT THIS MODULE DOES NOT DO. It does not check a number and it does not know what any
artifact means. It answers "what has to run, and why", and it runs it. Whether the
resulting number is right is the business of the checks in checks/ and of the steps
that own the quantity.

HOW TO RUN IT. The pinned form below is the one README.md gives, and the pin is the
point: --with-requirements installs the versions requirements.txt names, while the
shorter --with numpy resolves numpy on the day of the run. Measured 2026-08-13, the
short form installed numpy 2.5.2 against the 2.4.6 this tree pins, announced nothing
about the substitution, and installed no matplotlib at all.

Each line below is whole and can be pasted as it stands. Nothing is abbreviated into a
shell variable on purpose: a reader who pastes one line and not the line that defined
the variable would be running an unpinned interpreter without being told.

    uv run --no-project --with-requirements requirements.txt python3 build.py --plan
    uv run --no-project --with-requirements requirements.txt python3 build.py --graph
    uv run --no-project --with-requirements requirements.txt python3 build.py --only m7_size_results.json
    uv run --no-project --with-requirements requirements.txt python3 build.py --run --only ws2_hard_classifier.py
    uv run --no-project --with-requirements requirements.txt python3 build.py --run --run-unprovable
    uv run --no-project --with-requirements requirements.txt python3 build.py --what-if fdr_alpha=0.01
    uv run --no-project --with-requirements requirements.txt python3 build.py --what-if rank_floor_fills=100
    uv run --no-project --with-requirements requirements.txt python3 build.py
    uv run --no-project --with-requirements requirements.txt python3 build.py --self-test

--plan says what would run, what would be skipped and what cannot be told, each with its
recorded cost, and runs nothing. --graph prints the graph itself. The bare form and
--self-test both run the self-test.
"""
import argparse
import ast
import collections
import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import zipfile

# Every path this module builds starts from its own location, so a run from any
# working directory reads the same tree and records no absolute path.
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = HERE

# Any absolute home path, so a captured line can be recorded without carrying the
# account name of the machine into a tracked file. Same shape the no-absolute-paths
# gate looks for, kept here rather than imported so the build has no dependency on
# a check.
HOME_PATH_RE = re.compile(r"/(?:Users|home)/[^/\s\"']+/")


if HERE not in sys.path:
    sys.path.insert(0, HERE)
import artifact                                                    # noqa: E402
import build_declarations as D                                     # noqa: E402
import settings as S                                               # noqa: E402
# The skip rule itself lives next door, and the split is on purpose: this module owns
# the TREE -- the file index, the hash cache, the graph -- and skip_rule.py owns the
# RULE, which touches no file and can therefore be driven to all three of its answers
# against fabricated records in a second. It is also the one place the producer-hash
# comparison is made, by delegation to checks/run_record.py, so that this repository
# holds one implementation of that predicate rather than three.
import skip_rule as K                                              # noqa: E402

# The .gitignore predicate is imported rather than restated. It is the same question
# the provenance gate asks -- "would git track this file" -- and two implementations of
# one predicate is how two honest censuses of these artifacts returned 24 and 32 for a
# single property. If this import breaks, the fix is to follow the rename, never to
# copy the rules back in here.
_CHECKS_DIR = os.path.join(ROOT, "checks")
if _CHECKS_DIR not in sys.path:
    sys.path.insert(0, _CHECKS_DIR)
import chk_artifact_provenance as _prov                            # noqa: E402

# =====================================================================
# 1. WHAT COUNTS AS AN ARTIFACT, AND WHAT COUNTS AS A SCRIPT
# =====================================================================

# Extensions a build edge can carry. A file this module does not recognise is not an
# edge, and unresolved() says so; guessing at .txt or .log would put run logs into the
# dependency graph, and a log changes on every run by construction.
ARTIFACT_EXT = (".json", ".npz", ".csv", ".png", ".parquet", ".ipynb")

# Directories skipped whole. __pycache__ and .git hold no source.
SKIP_DIRS = ("__pycache__", ".git")

# The build's own script and output, excluded from its own graph. A build that
# schedules itself is a cycle by construction, and recording a build would otherwise
# mark the build as out of date. The exclusion also removes a false reading this
# module produces about itself: it holds the string "s3://" as the constant that
# recognises a tape locator, and it imports subprocess to launch producers, so its own
# stage predicate classifies it as a tape walker.
SELF_SCRIPT = "build.py"
SELF_OUTPUT = "build_results.json"

# WHAT build_results.json IS, SAID IN THE FILE ITSELF.
#
# Every other results file in this tree answers "what is this quantity, and would it
# come out the same today". The freshness gate next door asks that question by
# comparing the producer hash an artifact recorded against the script on disk, and a
# mismatch there means the number may be wrong and the producer should be run again.
#
# This file cannot answer that question, and the reason is not a gap. It records that
# a build HAPPENED: which nodes were planned, why each was planned, what each cost.
# The moment build.py is edited the record becomes older than the code, exactly as the
# gate says -- and it is still a correct account of a run that took place under the
# previous code. Re-running the build to make the hashes agree does not recompute a
# quantity, it holds a second run and writes a second journal, which the next edit
# makes stale again. Measured on 31 July: one edit to build.py turned the freshness
# column from zero stale to one, and nothing about any number had changed.
#
# So the file says what kind of record it is, in a field a program can read. The gate
# owns the decision of what to do with it; what the build owes is the statement, and
# the statement has to live where the file is written rather than in a list of
# exceptions kept somewhere else -- a list of exceptions is a second home for a fact,
# and this repository has already had one fact go stale in five homes at once.
RECORD_KIND = "run_journal"
RECORD_KIND_WHY = (
    "a journal of one build, not a computed quantity. Its producer hash is correct "
    "for the run it records and goes stale on the next edit to build.py by "
    "construction, because the thing it describes is a run and not a number. "
    "Freshness against the producer is therefore not answerable for this file, and a "
    "reader wanting a current plan runs the build again rather than treating this "
    "file as out of date")


def _ignore_rules():
    """The .gitignore rules, from the one place that parses them."""
    for name in ("ignore_patterns", "is_ignored"):
        if not hasattr(_prov, name):
            raise RuntimeError(
                f"checks/chk_artifact_provenance.py no longer exposes {name}(); this "
                "module reads the tracked-file predicate from there on purpose, so "
                "that one predicate has one home. Follow the rename rather than "
                "copying the .gitignore rules into this file")
    return _prov.ignore_patterns(ROOT)


def tracked_scripts():
    """Every .py in the tree that git would track, repo-relative and sorted."""
    rules = _ignore_rules()
    found = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if not name.endswith(".py"):
                continue
            rel = os.path.relpath(os.path.join(dirpath, name),
                                  ROOT).replace(os.sep, "/")
            if not _prov.is_ignored(rel, rules):
                found.append(rel)
    return sorted(found)


# =====================================================================
# 2. FOLDING A PATH EXPRESSION TO A NAME
#
# The tree writes its paths one way -- HERE = os.path.dirname(os.path.abspath(
# __file__)) and then os.path.join(HERE, "quickwin_markouts.npz") -- so folding
# os.path.join to its last literal component recovers the file name without ever
# recovering a directory. That is deliberate twice over: a directory is the machine
# and does not belong in a published artifact, and two scripts naming one file through
# different roots are the same node here, which is what makes the uniqueness rule bite.
# =====================================================================

# A name assembled at run time keeps a * where the run-time part was, so
# mid_series_{coin}_{period}.npz becomes mid_series_*.npz: one node standing for the
# family, which is what the producers treat it as.
_FORMAT_HOLE = re.compile(r"\{[^}]*\}|%[-#0-9.]*[sdfgi]")
# Adjacent holes collapse to one. f"mid_series_{coin}{suffix}.npz" would otherwise fold
# to a two-star pattern while the script that reads the same family writes one hole,
# and the two spellings would be two nodes. That is not hypothetical: it is why
# mid_series_*.npz was read by two scripts and produced by none.
_STAR_RUN = re.compile(r"\*{2,}")


def _pattern(text):
    return _STAR_RUN.sub("*", text)


# Calls that hand back the path they were given. They are not path constructors, so
# folding them to their argument adds no edge that the code does not already write.
PATH_PASSTHROUGH = ("path.normpath", "path.realpath", "path.expanduser",
                    "path.expandvars", "fspath",
                    # A list of paths is still the same path pattern. sorted(glob.glob(
                    # SHARD_GLOB)) is how three scripts name a family of shards, and
                    # the sort and the glob change nothing about which family it is.
                    "glob.glob", "glob.iglob", "sorted", "list")

# Keys under which the folder carries its own state inside the same environment as the
# file's names. A Python identifier cannot contain a parenthesis, so no binding of a
# variable can ever collide with either of these.
HELPERS_KEY = "()helpers"
DEPTH_KEY = "()depth"
# How far a helper may fold into another helper. Two is what this tree needs -- a path
# helper calling os.path.join -- and the cap is what stops a recursive helper folding
# forever.
HELPER_DEPTH = 3


def _dotted(func):
    """The dotted name of a call target: np.savez_compressed, os.path.join, open."""
    parts = []
    node = func
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _fold(node, env):
    """A path expression as a string, or None where it does not fold.

    None is a real answer and is counted. A folder that guessed would put an edge in
    the graph that no line of code makes.
    """
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else None
    if isinstance(node, ast.Name):
        return env.get(node.id)
    if isinstance(node, ast.JoinedStr):
        out = []
        for piece in node.values:
            if isinstance(piece, ast.Constant) and isinstance(piece.value, str):
                out.append(piece.value)
            else:
                out.append("*")
        return _pattern("".join(out))
    if isinstance(node, ast.BinOp):
        if isinstance(node.op, ast.Add):
            left, right = _fold(node.left, env), _fold(node.right, env)
            if left is None and right is None:
                return None
            return _pattern((left or "*") + (right or "*"))
        if isinstance(node.op, ast.Mod):
            left = _fold(node.left, env)
            return None if left is None else _pattern(_FORMAT_HOLE.sub("*", left))
        return None
    if isinstance(node, ast.Call):
        name = _dotted(node.func)
        # A one-return helper that hands back a path: _resolve(data_root, PRINT_NPZ).
        # Folded with this call's arguments bound to its parameters, because that is
        # where the file name is written.
        expression, inner = _helper_env(name, node, env)
        if expression is not None:
            folded = _fold(expression, inner)
            if folded is not None:
                return folded
        if name.endswith("path.join") or name == "join":
            parts = [_fold(a, env) for a in node.args]
            # The last component names the file; earlier components are the machine.
            return parts[-1] if parts else None
        if name.endswith("path.basename") or name.endswith("path.abspath"):
            value = _fold(node.args[0], env) if node.args else None
            return os.path.basename(value) if value else None
        if name.endswith(".format"):
            base = _fold(node.func.value, env) \
                if isinstance(node.func, ast.Attribute) else None
            return None if base is None else _pattern(_FORMAT_HOLE.sub("*", base))
        # Calls that return their own argument's path unchanged. Dropping these cost
        # real edges: m2_figure.py writes os.path.normpath(os.path.join(...)) and was
        # not a node of this graph at all, so the figure it produces had no producer.
        if any(name.endswith(tail) for tail in PATH_PASSTHROUGH):
            return _fold(node.args[0], env) if node.args else None
        if name.endswith(".get") and isinstance(node.func, ast.Attribute):
            # MID_PATH.get(coin) reads the family; os.environ.get(KEY, default) reads
            # the default, because the environment variable is not in the source.
            return (_fold(node.func.value, env)
                    or (_fold(node.args[1], env) if len(node.args) > 1 else None))
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
        # `args.out or os.path.join(HERE, "panel_extended_results.json")`. The left
        # arm is a command-line override that folds to nothing; the right arm is the
        # name the code states, and stating it is the whole point of the default.
        for value in node.values:
            folded = _fold(value, env)
            if folded is not None:
                return folded
        return None
    if isinstance(node, ast.IfExp):
        for value in (node.body, node.orelse):
            folded = _fold(value, env)
            if folded is not None:
                return folded
    if isinstance(node, ast.DictComp):
        # MID_PATH = {c: os.path.join(HERE, f"mid_series_{c}.npz") for c in COINS}.
        # One expression, one family, and the star the f-string leaves is exactly the
        # family the readers treat it as.
        return _fold(node.value, env)
    if isinstance(node, ast.Dict):
        folded = {_fold(v, env) for v in node.values}
        return folded.pop() if len(folded) == 1 else None
    if isinstance(node, ast.Subscript):
        # SHARD[c] and MID_PATH[coin]: the subscript picks a member of the family the
        # container names, and the family is what a build node stands for.
        return _fold(node.value, env)
    return None


def _constant_env(tree, env=None):
    """Names bound to a foldable path, across whatever tree it is handed.

    Walked twice, because a producer may bind a name below the function that uses it
    and one pass would miss the binding.

    ON ITS OWN THIS IS FLAT, and flat was wrong. The claim that stood here until
    2026-08-03 was that a single environment for the whole file "can only ever add
    edges that some line of the file genuinely writes". Measured against the tree, it
    adds edges no line writes, because two functions may bind the same name to two
    different files and one flat answer is one of them. prose_assemble.py binds `path`
    in four places; the value from its self-test reached three production functions and
    made the script read and write display.json, which is a file this repository does
    not have. checks/chk_artifact_provenance.py binds `path` in two places; the value
    from _neutral_certificate reached census and made the census read NEUTRAL_EDITS.json
    instead of the population of tracked files it actually walks. Eighteen I/O calls in
    twelve scripts folded to a name from another function.

    So _scoped_envs below asks this function once per function of the file, and the
    callers inside a scope use that answer. This one stays flat and is the base the
    scoped ones are built from.
    """
    env = dict(env or {})
    for _ in range(2):
        for node in ast.walk(tree):
            targets, source = (), None
            if isinstance(node, ast.Assign):
                targets, source = node.targets, node.value
            elif isinstance(node, (ast.For, ast.AsyncFor)):
                # `for f in sorted(glob.glob(SHARD_GLOB)): np.load(f)`. The loop
                # variable stands for one member of the family the iterable names, and
                # the family is the node. Without this the read is unresolved and a
                # panel family looks read by nobody.
                targets, source = (node.target,), node.iter
            if source is None:
                continue
            value = _fold(source, env)
            if value is None:
                continue
            for target in targets:
                if isinstance(target, ast.Name):
                    env[target.id] = value
    return env


def _module_level_names(tree):
    """Names bound at module level, which every function of the file can see."""
    names = set()
    for node in tree.body:
        targets = ()
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            targets = (node.target,)
        for target in targets:
            names |= _name_ids(target)
    return names


def _scope_locals(tree):
    """For each function of the file, the names that function binds itself.

    A parameter counts, and it is the half that matters most: `def load_overlay(path)`
    binds `path` to whatever the caller hands it, so a value the flat environment holds
    for `path` is some other function's and is not this one's to use. Assignments,
    loop variables and `with ... as name` count for the same reason.

    The scope is the innermost enclosing function, the same one _in_scope reports, so a
    nested helper's bindings stay its own rather than widening the function around it.
    """
    bound = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        spec = node.args
        names = {a.arg for a in spec.posonlyargs + spec.args + spec.kwonlyargs}
        for extra in (spec.vararg, spec.kwarg):
            if extra is not None:
                names.add(extra.arg)
        bound.setdefault(node.name, set()).update(names)
    for node, scope in _in_scope(tree):
        if scope is None:
            continue
        targets = ()
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, (ast.For, ast.AsyncFor, ast.AnnAssign, ast.AugAssign)):
            targets = (node.target,)
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            targets = tuple(item.optional_vars for item in node.items
                            if item.optional_vars is not None)
        for target in targets:
            bound.setdefault(scope, set()).update(_name_ids(target))
    return bound


def _scoped_envs(tree, env):
    """One folding environment per function, so a name means what THAT function bound.

    Built from the flat environment by removing the names this function binds itself
    and then folding the function's own body back on top. A module-level constant is
    kept whatever the function does with the name, because a module constant IS visible
    inside every function and that is the shape almost every path in this tree has:
    NPZ_PATH at module level, np.load(NPZ_PATH) inside a function.

    What this deliberately does NOT do is guess. Where a function binds a name to
    something that does not fold -- a parameter, a path joined onto a directory chosen
    at run time -- the name folds to nothing here, the call lands in the residue, and
    the residue is counted against a ceiling of zero. A missing edge is loud; an
    invented one is silent, which is why this is the direction to fail in.
    """
    module_bound = _module_level_names(tree)
    own = _scope_locals(tree)
    envs = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        mine = own.get(node.name, set())
        base = {name: value for name, value in env.items()
                if name == HELPERS_KEY or name in module_bound or name not in mine}
        envs[node.name] = _constant_env(node, base)
    return envs


def _path_helpers(tree):
    """Every one-return helper in the file, kept as parameters plus return expression.

    The shape this is for is everywhere in this tree, in two variants:

        def _cell_shard_path(coin, period):
            return os.path.join(CKPT_DIR, f"{coin}_{period}.npz")
        def _resolve(root, name):
            return os.path.join(root, name)

    and then np.savez_compressed(_cell_shard_path(coin, period), ...) or
    np.load(_resolve(data_root, PRINT_NPZ)) three hundred lines away. The second
    variant is why the return is kept UNFOLDED: its return expression says nothing at
    all on its own -- the file name lives in the argument at the call site -- so it can
    only be folded once the parameters are bound, which is what the call site does.

    Only a function with exactly ONE return is kept. A helper with two returns can hand
    back two different files, and binding it to whichever return came first would state
    an edge the code does not make.
    """
    helpers = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        returns = [n for n in ast.walk(node)
                   if isinstance(n, ast.Return) and n.value is not None]
        if len(returns) != 1:
            continue
        spec = node.args
        helpers[node.name] = ([a.arg for a in (spec.posonlyargs + spec.args)],
                              returns[0].value)
    return helpers


def _helper_env(name, node, env):
    """The environment inside a one-return helper, given the arguments at this call.

    Returns None when the helper is unknown or the call recursed too deep. The depth
    cap is not a performance guard: a helper that calls itself would otherwise fold
    forever, and a build that hangs on a syntax tree is worse than one that reports an
    unresolved call.
    """
    helpers = env.get(HELPERS_KEY) or {}
    if name not in helpers or env.get(DEPTH_KEY, 0) >= HELPER_DEPTH:
        return None, None
    params, expression = helpers[name]
    inner = dict(env)
    inner[DEPTH_KEY] = env.get(DEPTH_KEY, 0) + 1
    for param, arg in zip(params, node.args):
        folded = _fold(arg, env)
        if folded is not None:
            inner[param] = folded
    for kw in node.keywords:
        if kw.arg in params:
            folded = _fold(kw.value, env)
            if folded is not None:
                inner[kw.arg] = folded
    return expression, inner


def _call_site_envs(tree, env, scope_envs=None):
    """For each function in the file, the environments its own call sites give it.

    Why this pass exists. Half the reads in this tree are written as a two-liner --
    `def load_quickwin(path): ... np.load(path)` called once as
    `load_quickwin(NPZ_PRIMARY)` -- and a folder that looks only at the np.load line
    sees a parameter and reports "did not fold". The edge is on the page; it is just
    one call away. So every call of a function defined in the same file is folded, its
    arguments bound to the parameter names, and the I/O inside the function is folded
    again under that binding.

    A function called from two places with two different constants gets two
    environments and contributes BOTH reads, which is the honest answer: it does read
    both files. Nothing here crosses a file boundary, and nothing is guessed -- an
    argument that does not fold binds nothing, and the call stays unresolved.

    A CALL MADE INSIDE A SELF-TEST BINDS NOTHING, and that is the one exception. What a
    self-test hands a function is a fixture: prose_assemble._self_test writes
    display.json into a directory the operating system hands out and calls load_overlay
    with it. Binding that argument here carried the fixture into load_overlay's
    production read, so the graph had the script reading a file the repository does not
    contain -- and because the same flat name reached the write side too, the script
    came out as a cycle with itself. The fixture writes were already kept apart at the
    call loop; this is the same statement made one level earlier, where the fixture is
    handed over.
    """
    params, bodies = {}, {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            spec = node.args
            params[node.name] = [a.arg for a in (spec.posonlyargs + spec.args)]
            bodies[node.name] = node

    scope_envs = scope_envs or {}
    envs = {}
    for node, scope in _in_scope(tree):
        if not isinstance(node, ast.Call):
            continue
        target = _dotted(node.func)
        if target not in params:
            continue
        if _is_fixture(scope) and not _is_fixture(target):
            continue
        here = scope_envs.get(scope, env)
        bound = {}
        for name, arg in zip(params[target], node.args):
            folded = _fold(arg, here)
            if folded is not None:
                bound[name] = folded
        for kw in node.keywords:
            if kw.arg in params[target]:
                folded = _fold(kw.value, here)
                if folded is not None:
                    bound[kw.arg] = folded
        if bound:
            merged = dict(scope_envs.get(target, env))
            merged.update(bound)
            # The parameter is rarely the thing the I/O call names. `def load(fn): p =
            # os.path.join(HERE, fn); json.load(open(p))` reads p, and p only exists
            # once fn is bound, so the function's own assignments are folded again
            # under the binding this call site gives it.
            merged = _constant_env(bodies[target], merged)
            envs.setdefault(target, []).append(merged)
    return envs


# How much literal text a pattern must keep to stand for a family. A name assembled
# entirely out of run-time parts folds to something like *_*.npz, which fnmatch
# matches against nearly every panel in this tree, and a node holding it would claim
# every one of them as its output. Three literal characters outside the extension is
# the floor: mid_series_*.npz keeps eleven and stands for one family, *_*.npz keeps
# one and stands for nothing, so it is counted as an unresolved write instead.
MIN_PATTERN_LITERAL = 3


def _artifact_name(value):
    """The bare file name if this string names an artifact, else None."""
    if not value or "://" in value:
        return None
    base = os.path.basename(value)
    if not base.endswith(ARTIFACT_EXT):
        return None
    if "*" in base:
        stem = base[:base.rindex(".")]
        if max((len(part) for part in stem.split("*")), default=0) < MIN_PATTERN_LITERAL:
            return None
    return base


# =====================================================================
# 3. READING ONE SCRIPT
# =====================================================================

# Calls whose first argument is a file being READ.
READERS = ("np.load", "numpy.load", "np.loadtxt", "np.genfromtxt",
           "pd.read_csv", "pd.read_json", "pd.read_parquet",
           "artifact.read_meta", "artifact.describe")
# Calls whose first argument is a file being WRITTEN.
WRITERS = ("np.savez", "np.savez_compressed", "np.save", "np.savetxt",
           "artifact.write")
# Methods, matched on the attribute alone because the receiver is a figure or a frame
# whose own name carries no information.
WRITER_METHODS = ("savefig", "to_csv", "to_json", "to_parquet")

# Calls that load a module the import statements never name, with the position of the
# argument that names it.
#
# WHY AN IMPORT READ OFF ast.Import ALONE IS HALF A CENSUS. The stage predicate is
# transitive over local imports, because a script that walks the tape through a module
# it imports is a tape walker. Read out of the import statements only, that transitivity
# stops at the first module loaded by path -- and one script in this tree is loaded that
# way: checks/chk_rowcounts_determinism.py builds a spec from the file name of the raw
# tape parser, executes it, and calls its parse_day over all 24 hours of a December day.
# On its import statements it imports nothing of this tree at all, so the graph labelled
# it analysis, and an analysis label is a licence for any analysis-only setting to
# schedule it. It was scheduled on that label once, and the run is hours.
#
# The tree already held the right answer somewhere else, which is the part worth stating:
# checks/run_all_checks.py keeps that same file in its TAPE group by hand. Two homes for
# one fact with only one of them derived is exactly how the derived one goes quietly
# wrong, so the derived one is taught to read what the hand-kept one already knows.
#
# The position differs by call and is written down rather than guessed: the module is
# the second argument of spec_from_file_location and the first of the other three.
DYNAMIC_IMPORTS = {
    "importlib.util.spec_from_file_location": 1,
    "importlib.import_module": 0,
    "imp.load_source": 1,
    "__import__": 0,
}


def _dynamic_import_position(name):
    """Which argument of this call names a module, or None if the call names none.

    Matched on the dotted name and on its last component, because `from importlib
    import import_module` is the same call as `importlib.import_module`. A predicate
    that knows only the spelling in front of it today goes quiet the moment somebody
    writes the other one, and going quiet is the failure this table repairs.
    """
    for call, position in DYNAMIC_IMPORTS.items():
        tail = call.rsplit(".", 1)[-1]
        if name == call or name == tail or name.endswith("." + tail):
            return position
    return None


def _name_ids(node):
    """Every bare name inside one expression."""
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def _assignment_sources(tree):
    """For each module-level name, the names its value is assembled from.

    Module level only, and that is the point: a name bound inside a function cannot be
    reached from another file, so it can never be the name a redirect assigns to.
    """
    sources = {}
    for node in tree.body:
        value = getattr(node, "value", None)
        if value is None or not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if isinstance(target, ast.Name):
                sources.setdefault(target.id, set()).update(_name_ids(value))
    return sources


def _output_name_closure(seeds, sources, imported):
    """The module-level names this file's writer builds its output path from.

    Transitive, because the name at the write call is rarely the only one that carries
    the output: panel_persistence.py writes through RESULTS_NAME and binds RESULTS_NAME
    = os.path.basename(RESULTS_PATH), so either name redirects the write and both
    belong to the set.

    Imported names are dropped. `os` is a name inside every os.path.join and stands for
    the module rather than for the file, and an imported name in this set would let an
    assignment to any module attribute at all read as a redirect.
    """
    start = set(seeds) - imported
    out, frontier = set(start), list(start)
    while frontier:
        current = frontier.pop()
        for upstream in (sources.get(current) or set()) - imported:
            if upstream not in out:
                out.add(upstream)
                frontier.append(upstream)
    return out

# Functions whose file writes are FIXTURES rather than build products. A self-test
# writes into a temporary directory the operating system hands out and deletes it
# again, so the file it names never exists in the tree and no other script reads it.
# Counting those as artifacts is not a small error: artifact.py appeared as a producer
# of an_input.json and as a cycle with itself, and the cycle report is the part that
# matters, because a cycle is the one finding a reader is meant to act on. The rule is
# the enclosing FUNCTION, taken from the syntax tree, not the file name -- a producer
# and its self-test live in the same file by the convention of this repository.
FIXTURE_SCOPES = ("_self_test", "_selftest", "test_", "_test")

# The two things a raw-tape walk needs, and it needs BOTH. Requiring both is what
# separates a script that walks the tape from one that cites it in its references
# header: 35 tracked scripts mention the archive as measured on 2026-08-30, against 30
# when this line was written, and a mention is a string constant indistinguishable from
# a locator until you ask whether anything fetches it. The number is dated because it
# moves with the tree: the live one is scripts_mentioning_the_tape in --graph --json,
# and a count kept here without a date reads as a claim about today and goes wrong
# silently.
TAPE_LOCATORS = ("s3://", "node_fills_by_block")
TAPE_MECHANISMS = ("subprocess", "boto3", "botocore")
TAPE_TOOLS = ("aws", "lz4")


def _in_scope(tree):
    """Every node of the tree paired with the name of the function enclosing it.

    ast.walk loses the scope, and the scope is what separates a build product from a
    self-test fixture. The outermost scope is None, meaning module level.
    """
    def descend(node, scope):
        for child in ast.iter_child_nodes(node):
            inner = child.name if isinstance(
                child, (ast.FunctionDef, ast.AsyncFunctionDef)) else scope
            yield child, inner
            yield from descend(child, inner)
    yield from descend(tree, None)


def _is_fixture(scope):
    return bool(scope) and scope.startswith(FIXTURE_SCOPES)


# =====================================================================
# READING THE COMMAND LINE BY HAND
#
# The build refuses to launch a producer that reads its command line, because a run
# without arguments picks whatever arm the script falls back to and records that as
# the result. Recognising those producers by their add_argument calls was half a
# predicate: ten of them never call argparse at all and reach into sys.argv directly,
# so the build saw them as taking no arguments and would have launched every one of
# them bare. The two spellings are one question, and this is where it is asked.
#
# What is NOT an argument. sys.argv[0] is the program's own name; a script printing it
# in a usage line is not reading its command line. That is the one exclusion, and it is
# made on the literal index rather than on anything else, so a variable index counts.
# =====================================================================

def _parent_map(tree):
    """Child -> parent for the whole tree.

    ast has no upward links, and two questions here are about the node ABOVE the one
    that matched: `is this sys.argv[0]`, and `does a branch reading a declared setting
    stand over this deletion`. Building the map once per script is cheaper than
    re-walking for every match.
    """
    parents = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    return parents


def _argv_option(node, parents):
    """The option name a manual argv read is testing for, when it is testing for one.

    `"--smoke" in sys.argv[1:]` names its flag as plainly as add_argument does, and
    recovering it is what lets the build tell a reader which option to pass. The walk
    upward stops at the first enclosing comparison, so a string constant somewhere
    else in the statement cannot be mistaken for the flag.
    """
    seen, current = 0, parents.get(node)
    while current is not None and seen < 4:
        if isinstance(current, ast.Compare) and len(current.ops) == 1 and \
                isinstance(current.ops[0], ast.In) and \
                isinstance(current.left, ast.Constant) and \
                isinstance(current.left.value, str) and \
                current.left.value.startswith("-"):
            return current.left.value
        current = parents.get(current)
        seen += 1
    return None


def _manual_argv(tree):
    """Every read of sys.argv in one script, with its scope, line and option name.

    Both spellings are matched: `sys.argv` after `import sys`, and a bare `argv` after
    `from sys import argv`. The second is not in this tree today; it is matched anyway
    because a predicate that only sees the spelling currently in use is a predicate
    that goes quiet the moment somebody writes the other one, and going quiet is the
    exact failure this function was added to repair.
    """
    imported_bare = any(
        isinstance(node, ast.ImportFrom) and node.module == "sys"
        and any(alias.name == "argv" for alias in node.names)
        for node in ast.walk(tree))
    parents = _parent_map(tree)
    found = []
    for node, scope in _in_scope(tree):
        if isinstance(node, ast.Attribute) and node.attr == "argv" and \
                isinstance(node.value, ast.Name) and node.value.id == "sys":
            spelling = "sys.argv"
        elif imported_bare and isinstance(node, ast.Name) and node.id == "argv" and \
                isinstance(node.ctx, ast.Load):
            spelling = "argv"
        else:
            continue
        parent = parents.get(node)
        if isinstance(parent, ast.Subscript) and \
                isinstance(parent.slice, ast.Constant) and parent.slice.value == 0:
            continue                  # the program's own name, not an argument
        found.append({"scope": scope or "", "line": node.lineno,
                      "spelling": spelling, "option": _argv_option(node, parents)})
    return found


# The text predicate's own idea of a manual argv read: the name, not followed by the
# literal index zero. Kept beside the function so the one exclusion the two predicates
# share -- argv[0] is the program's name -- is visible in both places rather than
# implied in one.
_ARGV_TEXT_RE = re.compile(r"\bsys\.argv\b(?!\s*\[\s*0\s*\])")


def _argv_lines(source):
    """The same census read off the SOURCE TEXT, as a second opinion on the first.

    Deliberately not an ast walk: two implementations of one predicate agree for a
    reason only when they look differently. This one reads lines and knows nothing
    about expressions; the other reads expressions and knows nothing about lines. They
    cannot return the same COUNT -- one line here holds two reads -- so what is
    compared is the set of SCRIPTS, which both can answer, and the self-test compares
    them over the real tree.

    This is the coarser of the two and it is meant to be. It cannot see that a name
    sits inside a docstring, so a script that only DISCUSSES sys.argv would show up
    here and not in the ast census. No script in this tree does today. If one ever
    does, the disagreement is a prompt to look at that script, which is what a second
    opinion is for; it is not a reason to delete the second opinion.
    """
    return [number for number, line in enumerate(source.splitlines(), start=1)
            if _ARGV_TEXT_RE.search(line.split("#", 1)[0])]


class ScriptFacts:
    """What one script's syntax tree says about its own inputs, outputs and stage."""

    def __init__(self, rel):
        self.rel = rel
        self.reads = set()
        self.writes = set()
        self.declared_inputs = set()   # the inputs= list handed to artifact.write
        self.fixture_writes = set()    # files a self-test writes into a temp directory
        self.unresolved = []           # I/O calls whose path did not fold
        self.declared = []             # unresolved calls build_declarations covers
        self.not_an_artifact = []      # folded, but the name is not an artifact
        self.internal = []             # folded under a checkpoint dir git does not keep
        self.mentions_tape = False     # a locator appears anywhere, docstrings included
        self.fetches_tape = False      # a locator AND a mechanism that fetches it
        self.imports_local = set()     # modules of this tree the script imports
        self.dynamic_imports = set()   # of those, the ones loaded by path, not by import
        self.unnamed_imports = []      # dynamic loads whose module argument did not fold
        self.import_aliases = {}       # local name -> the module it stands for
        self.output_names = set()      # module names ITS OWN writer builds its path from
        self.attribute_writes = []     # `other.NAME = <artifact>`, resolved across files
        self.redirected_writes = []    # of those, the ones that resolved to a write
        self.tape_via = None           # the imported module its tape stage came from
        self.tape_not_inherited = []   # tape stages refused, with the module refused
        self.argv_flags = []           # argparse options, if the script takes any
        self.argv_manual = []          # reads of sys.argv that bypass argparse
        self.parse_error = None

    @property
    def inputs(self):
        """Everything the script reads: what the tree shows plus what it declares.

        The union is deliberate. The declared list is the producer's own statement and
        is what artifact.write hashes, so it is authoritative; the syntax tree catches
        a read the producer forgot to declare. Neither alone is complete.
        """
        return self.reads | self.declared_inputs

    @property
    def takes_argv(self):
        """Whether this script reads its command line at all, by either route.

        Two routes, and for ten months the build could see only one of them. A script
        that calls add_argument declares its options to argparse and the flag is a
        string constant at the call site. A script that writes `"--smoke" in sys.argv`
        declares nothing, and to the old predicate it looked like a script that takes
        no arguments -- so the build would launch it bare and record the result as
        THE result, when what it had actually measured was the arm the script picks
        when nobody says otherwise. Ten producer nodes read the command line this way.
        """
        return bool(self.argv_flags) or bool(self.argv_manual)

    def argv_options(self):
        """Every option name either route names, plus a marker for each positional.

        A flag recovered from `"--smoke" in sys.argv` is as good a name as one
        recovered from add_argument. A bare `sys.argv[1]` names nothing, so it is
        reported as `<positional>` rather than dropped: a reader who is told the
        script takes an argument can pass one, and a reader who is told nothing
        cannot.
        """
        names = set(self.argv_flags)
        for record in self.argv_manual:
            names.add(record["option"] or "<positional>")
        return sorted(names)

    @property
    def stage(self):
        return "tape" if self.fetches_tape else "analysis"


def _fold_dir(node, env, dir_env=None):
    """The directory an os.path.join names, when the join has one.

    _fold deliberately keeps only the last component of a path, because a directory is
    the machine and does not belong in a published artifact. One question still needs the
    directory and only that question: whether a file lives in a checkpoint directory
    that git does not keep. This returns the component just before the file name, and
    nothing else uses it.
    """
    if isinstance(node, ast.Call):
        name = _dotted(node.func)
        expression, inner = _helper_env(name, node, env)
        if expression is not None:
            directory = _fold_dir(expression, inner, dir_env)
            if directory is not None:
                return directory
        if (name.endswith("path.join") or name == "join") and len(node.args) > 1:
            return _fold(node.args[-2], env)
        if any(name.endswith(tail) for tail in PATH_PASSTHROUGH) and node.args:
            return _fold_dir(node.args[0], env, dir_env)
        if name.endswith(".get") and isinstance(node.func, ast.Attribute):
            return _fold_dir(node.func.value, env, dir_env)
    if isinstance(node, ast.DictComp):
        return _fold_dir(node.value, env, dir_env)
    if isinstance(node, ast.Dict):
        seen = {_fold_dir(v, env, dir_env) for v in node.values}
        return seen.pop() if len(seen) == 1 else None
    if isinstance(node, ast.Subscript):
        return _fold_dir(node.value, env, dir_env)
    if isinstance(node, ast.Name):
        # `marker = os.path.join(CELL_DIR, ...)` then `open(marker)` two functions
        # away. The name carries the directory even though the expression at the open()
        # does not, and that is the shape every checkpoint marker in this tree has.
        return (dir_env or {}).get(node.id)
    return None


def _dir_bindings(tree, env):
    """Names bound to a path, paired with the directory that path was joined under.

    A second flat environment beside _constant_env, holding the part _fold throws
    away. Kept apart rather than folded in, because every other caller wants the file
    name with no directory at all, and one environment answering two questions is how
    a machine path would leak back into a published artifact.
    """
    bound = {}
    for _ in range(2):
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                targets, source = node.targets, node.value
            elif isinstance(node, (ast.For, ast.AsyncFor)):
                targets, source = (node.target,), node.iter
            else:
                continue
            directory = _fold_dir(source, env, bound)
            if directory is None:
                continue
            for target in targets:
                if isinstance(target, ast.Name):
                    bound[target.id] = directory
                elif isinstance(target, (ast.Tuple, ast.List)):
                    for element in target.elts:
                        if isinstance(element, ast.Name):
                            bound[element.id] = directory
    return bound


def _is_internal_dir(directory, rules):
    """Whether a directory git does not keep, i.e. node-internal working state.

    The predicate is the same .gitignore one the rest of this module imports, asked of
    a directory instead of a file. That is the whole rule and it needs no hand-kept
    list: panel_cells/, panel_ckpt/ and panel_ckpt_v2/ hold per-cell shards and their
    done-markers, a producer writes them so that an interrupted run can resume, and git
    keeps none of them. A file no reader outside the producing script can ever open is
    not an edge of this graph -- it is that node's own scratch space.
    """
    if not directory or "/" in directory or "." in directory:
        return False
    return bool(_prov.is_ignored(f"{directory}/probe.json", rules))


def scan(rel, rules=None, source=None):
    """One script's facts, read from its syntax tree.

    `source` is handed in only by a written-in fixture: a pair of sources put through
    THIS function, so that a predicate asserted over the live tree goes on being shown
    able to tell its two cases apart on the day the tree stops holding a counter-example.
    A fixture read by a second, private copy of this reader would calibrate the copy. Left
    at None, which is every live read, the file is opened as before.
    """
    facts = ScriptFacts(rel)
    rules = _ignore_rules() if rules is None else rules
    if source is None:
        path = os.path.join(ROOT, rel)
        with open(path, encoding="utf-8") as fh:
            source = fh.read()
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        facts.parse_error = str(exc)
        return facts

    env = _constant_env(tree)
    env[HELPERS_KEY] = _path_helpers(tree)
    env = _constant_env(tree, env)          # again, now that helper calls fold
    # One environment per function, and every fold below a call site uses the one for
    # the scope the call is in. The flat `env` is kept for the questions that are about
    # the file rather than about a call: the directory bindings, which only ever REMOVE
    # an edge by placing a file in a checkpoint directory, and the module-level reads.
    scope_envs = _scoped_envs(tree, env)
    dir_env = _dir_bindings(tree, env)
    call_envs = _call_site_envs(tree, env, scope_envs)
    mechanisms = set()
    # The names this file's own writer builds its output path out of, collected at the
    # write calls below and closed over the module-level assignments afterwards. Another
    # script can only redirect a write by assigning to one of these, so the set is what
    # keeps a redirect readable without trusting an attribute name to mean what it looks
    # like.
    output_seeds = set()
    # The command line, read by hand. Done here rather than in the call loop below
    # because a manual argv read is not a call at all -- it is a subscript, or the
    # right-hand side of an `in` -- so the loop that walks calls could never have seen
    # one, and that is precisely why it did not.
    facts.argv_manual = _manual_argv(tree)

    def resolve(node, scope):
        """Artifact names this call's first argument stands for, and how it landed.

        Returns (names, folded, verdict). The verdict is the point of this function:
        a call that folded to '.gitignore' and a call that folded to nothing are both
        "no edge" to the graph and completely different to a reader, and the old
        two-way answer put them in one bucket of 51.
        """
        if not node.args:
            return [], None, "unresolved"
        here = scope_envs.get(scope, env)
        folded = _fold(node.args[0], here)
        directory = _fold_dir(node.args[0], here, dir_env)
        seen = [folded] if folded is not None else []
        # The path may be a parameter this function was handed a constant for.
        if _artifact_name(folded) is None or _is_internal_dir(directory, rules):
            for extra in call_envs.get(scope, ()):
                other = _fold(node.args[0], extra)
                if other is not None and other not in seen:
                    seen.append(other)
                if directory is None:
                    directory = _fold_dir(node.args[0], extra, dir_env)
        # A checkpoint directory answers first. A shard under panel_ckpt/ carries a
        # perfectly good artifact name and would otherwise become a node of the graph,
        # which is how one script came to read and write its own output.
        if _is_internal_dir(directory, rules):
            return [], folded, "internal"
        names = sorted({n for n in (_artifact_name(v) for v in seen) if n})
        if names:
            return names, folded, "edge"
        if seen:
            return [], seen[0], "not_an_artifact"
        return [], None, "unresolved"

    def note(bucket, call, kind, verdict, folded, node, fixture, scope=None):
        # The scope, not the line, is what a declaration keys on. Line numbers in this
        # tree move whenever anything above them is edited, and a declaration keyed on
        # a number that moved is a declaration that silently stops applying.
        record = {"call": call, "kind": kind, "fixture": fixture,
                  "line": node.lineno, "scope": scope or ""}
        if folded is not None:
            record["folded"] = folded
        bucket.append(record)

    for node, scope in _in_scope(tree):
        fixture = _is_fixture(scope)
        here = scope_envs.get(scope, env)
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            # A locator inside a FIXTURE is a string the file builds in order to test
            # itself against; it is not an address this node reaches for. Counting it
            # marks the node as tape, and the stage is not decoration: the scheduler
            # runs a tape node alone and behind a free-space check, so a false mark
            # queues gates that need neither. Measured on this tree the day the ask
            # was written: 41 of 105 producer nodes carried the stage and 27 of 27
            # gates did, while four gates actually walk the archive. The flag is
            # already computed four lines up for the I/O ledger and was simply not
            # asked here.
            if any(mark in node.value for mark in TAPE_LOCATORS) and not fixture:
                facts.mentions_tape = True
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = ([a.name for a in node.names]
                     if isinstance(node, ast.Import) else [node.module or ""])
            for name in names:
                head = (name or "").split(".")[0]
                if head in TAPE_MECHANISMS:
                    mechanisms.add(head)
                if head:
                    facts.imports_local.add(head)
            # The local name each import binds, paired with the module it stands for.
            # `import panel_persistence as pp` is the only thing that says which file
            # `pp.RESULTS_PATH = ...` is a statement about, and without the pairing that
            # assignment is an attribute on an unknown object.
            for alias in node.names:
                if isinstance(node, ast.ImportFrom):
                    local, module = alias.asname or alias.name, alias.name
                elif alias.asname:
                    local, module = alias.asname, alias.name.split(".")[-1]
                else:
                    local = module = alias.name.split(".")[0]
                if local:
                    facts.import_aliases[local] = module
            continue
        if isinstance(node, ast.Assign):
            # `pp.RESULTS_PATH = out_path`: a write this file performs through another
            # module. Only recorded here, with the alias as written; whether the alias
            # names a module of this tree and whether that module writes through that
            # attribute are questions about ANOTHER FILE, and they are settled once
            # every file has been read.
            for target in node.targets:
                if not (isinstance(target, ast.Attribute)
                        and isinstance(target.value, ast.Name)):
                    continue
                written = _artifact_name(_fold(node.value, here))
                if written:
                    facts.attribute_writes.append(
                        {"alias": target.value.id, "attr": target.attr,
                         "name": written, "scope": scope or "", "line": node.lineno,
                         "fixture": fixture})
            continue
        if not isinstance(node, ast.Call):
            continue

        name = _dotted(node.func)
        attr = name.rsplit(".", 1)[-1]

        if name.startswith("subprocess.") or name.endswith(".Popen"):
            # A tape fetch is an external command; which command is in the argv.
            argv = []
            for arg in node.args:
                if isinstance(arg, ast.List):
                    argv += [_fold(e, here) or "" for e in arg.elts]
                else:
                    argv.append(_fold(arg, here) or "")
            if any(any(tool == (part or "").split()[0] if part else False
                       for tool in TAPE_TOOLS) for part in argv):
                mechanisms.add("subprocess")

        position = _dynamic_import_position(name)
        if position is not None:
            # A module loaded by path is an import, and the stage predicate is
            # transitive over imports. The argument is folded by the same folder every
            # other path in this module goes through, so a locator held in a constant
            # reads here exactly as it reads at an np.load.
            argument = node.args[position] if len(node.args) > position else None
            folded = _fold(argument, here) if argument is not None else None
            module = os.path.splitext(os.path.basename(folded))[0] if folded else None
            if module:
                facts.imports_local.add(module)
                facts.dynamic_imports.add(module)
            else:
                # Counted apart from the unresolved FILE operations, and deliberately
                # so. An import is not a file operation, and the residue ceiling was
                # measured for file operations; folding a second kind of miss into that
                # number would move a debt that is about something else.
                facts.unnamed_imports.append(
                    {"call": name, "scope": scope or "", "line": node.lineno})

        if name in READERS or (attr == "load" and name.endswith("np.load")):
            named, folded, verdict = resolve(node, scope)
            if verdict == "edge" and not fixture:
                facts.reads.update(named)
            elif verdict == "internal":
                note(facts.internal, name, "read", verdict, folded, node, fixture, scope)
            elif verdict == "not_an_artifact":
                note(facts.not_an_artifact, name, "read", verdict, folded,
                     node, fixture, scope)
            elif verdict == "unresolved":
                note(facts.unresolved, name, "read", verdict, folded, node,
                     fixture, scope)
        elif name in WRITERS or attr in WRITER_METHODS:
            if node.args and not fixture:
                output_seeds.update(_name_ids(node.args[0]))
            named, folded, verdict = resolve(node, scope)
            if verdict == "edge":
                (facts.fixture_writes if fixture else facts.writes).update(named)
            elif verdict == "internal":
                note(facts.internal, name, "write", verdict, folded, node, fixture, scope)
            elif verdict == "not_an_artifact":
                note(facts.not_an_artifact, name, "write", verdict, folded, node,
                     fixture, scope)
            else:
                note(facts.unresolved, name, "write", verdict, folded, node,
                     fixture, scope)
            if name == "artifact.write" and not fixture:
                for kw in node.keywords:
                    if kw.arg == "inputs" and isinstance(kw.value, (ast.List, ast.Tuple)):
                        for element in kw.value.elts:
                            declared = _artifact_name(_fold(element, here))
                            if declared:
                                facts.declared_inputs.add(declared)
        elif name == "open":
            mode = _fold(node.args[1], here) if len(node.args) > 1 else None
            for kw in node.keywords:
                if kw.arg == "mode":
                    mode = _fold(kw.value, here)
            writing = bool(mode) and any(c in mode for c in "wax")
            kind = "write" if writing else "read"
            named, folded, verdict = resolve(node, scope)
            if verdict == "edge":
                if fixture:
                    if writing:
                        facts.fixture_writes.update(named)
                else:
                    (facts.writes if writing else facts.reads).update(named)
            elif verdict == "internal":
                note(facts.internal, "open", kind, verdict, folded, node, fixture, scope)
            elif verdict == "not_an_artifact":
                note(facts.not_an_artifact, "open", kind, verdict, folded,
                     node, fixture, scope)
            else:
                note(facts.unresolved, "open", kind, verdict, folded, node,
                     fixture, scope)
        elif attr == "add_argument":
            flag = _fold(node.args[0], here) if node.args else None
            if flag and flag.startswith("--"):
                facts.argv_flags.append(flag)

    facts.fetches_tape = bool(facts.mentions_tape and mechanisms)
    facts.output_names = _output_name_closure(output_seeds, _assignment_sources(tree),
                                              set(facts.import_aliases))
    return facts


# =====================================================================
# 4. THE GRAPH
# =====================================================================

class Node:
    """One producer and the artifacts it makes.

    A producer is a script, or a script under one command-line arm. The two are kept
    apart by `key`: a script whose arms are declared holds one node per arm, and `key`
    is what the graph, the plan and the cycle report are keyed on, while `script` stays
    the file to hash and to launch.
    """

    def __init__(self, facts, argv=(), stage=None, outputs=None, inputs=None):
        self.script = facts.rel
        self.facts = facts
        self.argv = tuple(argv)
        self.outputs = sorted(facts.writes if outputs is None else outputs)
        self.inputs = sorted(facts.inputs if inputs is None else inputs)
        self.stage = stage or facts.stage

    @property
    def key(self):
        return " ".join((self.script,) + self.argv)

    def __repr__(self):
        return f"<Node {self.key} -> {len(self.outputs)} artifacts>"


class Graph:
    """Scripts, artifacts and the edges between them, plus what did not resolve."""

    def __init__(self, nodes, conflicts, orphans, cycles, unresolved, scanned):
        self.nodes = nodes                # node key -> Node, producers only
        self.conflicts = conflicts        # artifact -> [nodes], more than one
        self.orphans = orphans            # artifact -> [scripts] that read it, no maker
        self.cycles = cycles              # [[node key, ...]]
        self.unresolved = unresolved      # script -> [{call, kind, scope, line}]
        self.scanned = scanned            # every script looked at, producer or not
        self.spellings = {}               # read name -> the produced family it means
        # Nodes the last plan over this graph DECLINED to decide about: not scheduled
        # and not counted as current. Kept here rather than in the plan's own list so
        # that "the plan" stays what will run, which is what every caller reads it as.
        self.stood_aside = []

    # -- lookups -------------------------------------------------------
    def producer_of(self, name):
        # Exact spelling first, then the families. A node whose output name is
        # assembled at run time is registered under the PATTERN it writes, such as
        # panel_extended_results_h*_*.json, because the concrete names do not appear
        # in any source file. Without the second pass this method answered None for
        # all seven extended-panel results while the graph plainly held their
        # producer: the build expanded the pattern internally and every caller asking
        # by file name got nothing. Measured 2026-07-31, after the pattern edge was
        # added; the seven files were the whole of the difference.
        for node in self.nodes.values():
            if name in node.outputs:
                return node
        # A PATTERN WITH NO LITERAL PREFIX IDENTIFIES NOTHING, and accepting one is
        # worse than answering None. Calibrated on two opposite cases the moment this
        # fallback was written: the seven extended-panel files must resolve, and a
        # name that belongs to nobody must not. The second case failed at once,
        # because checks/chk_join_nolookahead.py declares the output "*_results.json",
        # which matches every results file in the tree. So a pattern qualifies only if
        # it has at least one literal character before its first wildcard, and among
        # those that qualify the most specific wins, measured by how much of the
        # pattern is literal.
        best, best_literal = None, -1
        for node in self.nodes.values():
            for output in node.outputs:
                if "*" not in output or not output.split("*", 1)[0]:
                    continue
                if not fnmatch.fnmatch(name, output):
                    continue
                literal = len(output.replace("*", ""))
                if literal > best_literal:
                    best, best_literal = node, literal
        return best

    def consumers_of(self, name):
        return sorted(n.key for n in self.nodes.values() if name in n.inputs)

    def node_named(self, script):
        """The one node standing for this script, found by NAME rather than by place.

        Takes a repo-relative path or a bare file name and answers the same either way,
        because a caller that knows which script it means should not also have to know
        which directory the script currently sits in. The tree was laid out by pipeline
        group on 2026-08-11, and from that commit two self-test lines reported that a
        script read no artifacts at all: both asked self.nodes for a bare name, both got
        None, and None reads downstream exactly like a node that reads nothing. That is
        the direction of measuring error that passes for a finding rather than stopping
        the run, and it stood for three days.

        None when nothing matches AND when more than one does. A script declared in
        arms is several nodes, and picking one of them would answer a question about
        the whole script with a fact about one of its halves.
        """
        want = os.path.basename(script)
        hits = [n for n in self.nodes.values()
                if n.script == script or os.path.basename(n.script) == want]
        return hits[0] if len(hits) == 1 else None

    def counts(self):
        artifacts = {a for n in self.nodes.values() for a in n.outputs}
        return {
            "scripts_scanned": len(self.scanned),
            "producer_nodes": len(self.nodes),
            "artifacts_produced": len(artifacts),
            "tape_nodes": sum(1 for n in self.nodes.values() if n.stage == "tape"),
            "analysis_nodes": sum(1 for n in self.nodes.values()
                                  if n.stage == "analysis"),
            "artifacts_with_two_producers": len(self.conflicts),
            "artifacts_read_with_no_producer": len(self.orphans),
            "cycles": len(self.cycles),
            "scripts_with_unresolved_io": len(self.unresolved),
            "unresolved_io_calls": sum(len(v) for v in self.unresolved.values()),
            # The three ways an I/O call can be no edge and still be accounted for.
            # Printed beside the residue on purpose: "51 calls did not fold" was one
            # number covering three different situations, and only one of them was a
            # gap in the graph.
            "io_declared_by_hand": sum(len(f.declared) for f in self.scanned.values()),
            "io_folded_but_not_an_artifact": sum(
                len(f.not_an_artifact) for f in self.scanned.values()),
            "io_into_a_checkpoint_dir": sum(
                len(f.internal) for f in self.scanned.values()),
            "scripts_mentioning_the_tape": sum(
                1 for f in self.scanned.values() if f.mentions_tape),
            # The three facts the syntax tree gives up only when it is read past the
            # import statement and past the write call. Each is counted apart from the
            # I/O residue above: a module that did not fold is not a file operation, and
            # a ceiling measured for file operations must not move when one appears.
            "modules_loaded_by_path": sum(
                len(f.dynamic_imports) for f in self.scanned.values()),
            "dynamic_imports_not_named": sum(
                len(f.unnamed_imports) for f in self.scanned.values()),
            "writes_redirected_through_another_module": sum(
                len(f.redirected_writes) for f in self.scanned.values()),
            "tape_stages_refused_to_an_importer": sum(
                len(f.tape_not_inherited) for f in self.scanned.values()),
            # Both routes into the command line, counted apart. Folding them into one
            # number would hide the half that was invisible: every node here is one
            # this build declines to launch, and until the second route was read the
            # ten in the middle column were being launched bare.
            "nodes_reading_the_command_line": sum(
                1 for n in self.nodes.values() if n.facts.takes_argv),
            "nodes_reading_it_through_sys_argv": sum(
                1 for n in self.nodes.values() if n.facts.argv_manual),
            "nodes_reading_it_through_argparse": sum(
                1 for n in self.nodes.values() if n.facts.argv_flags),
        }

    def stale_declarations(self):
        """Declarations that match nothing in the tree, which is a declaration lying.

        A declaration is a statement about a line of code. When the line is renamed or
        deleted the statement survives, keeps being counted as covered, and hides the
        call that replaced it. This is the same failure as a plan whose ticks were
        written once and never revisited, so it is checked by program rather than by
        eye.
        """
        seen = set()
        for facts in self.scanned.values():
            for record in facts.declared + facts.unresolved:
                seen.add(D.io_key(facts.rel, record.get("scope"), record["call"]))
        missing = sorted(key for key in D.DECLARED_IO if key not in seen)
        for script in D.ARMS:
            if script not in self.scanned:
                missing.append((script, "", "declared arms of a script not in the tree"))
        return missing


def _cycles(nodes):
    """Script cycles: A writes what B reads and B writes what A reads.

    Reported rather than raised. A self-loop is real here -- a script that reads a
    panel and rewrites it in place is one -- and calling that a fatal error would stop
    the build from planning anything.
    """
    maker = {}
    for node in nodes.values():
        for name in node.outputs:
            maker.setdefault(name, node.key)
    edges = {k: {maker[i] for i in n.inputs if i in maker} for k, n in nodes.items()}
    found, state = [], {}

    def walk(script, path):
        state[script] = "open"
        for nxt in sorted(edges.get(script, ())):
            if state.get(nxt) == "open":
                found.append(path[path.index(nxt):] + [script] if nxt in path
                             else [nxt, script])
            elif nxt not in state:
                walk(nxt, path + [script])
        state[script] = "done"

    for script in sorted(edges):
        if script not in state:
            walk(script, [])
    return found


def _resolve_redirected_writes(scanned):
    """A write a script performs by repointing the output name of a module it imports.

    THE SHAPE, and why no call site can show it. panel_extended.py calls no writer at
    all. It assigns pp.RESULTS_PATH and pp.RESULTS_NAME -- a name it assembles at run
    time out of the horizon and the window set it was asked for -- and then calls the
    analysis in panel_persistence.py, which writes through those very names. The write
    rule reads the first argument of a write call; there is no write call; so the file
    was not a node of this graph at all, and the seven panel_extended_results_h*.json
    sitting in the tree had no producer: never planned, never noticed stale, and no
    reader could be told what made them.

    THE RULE, and both halves of it carry weight. An assignment `alias.NAME = value` is
    a write BY THE ASSIGNING SCRIPT when NAME is one of the module-level names the
    TARGET module's own writer builds its path from, and when the value folds to an
    artifact name. Either half alone is name matching: assigning some attribute is not
    a write, and folding to a file name says nothing about which module ever writes it.

    Settled here rather than inside scan() because "is this attribute an output name" is
    a question about another file, and one file's syntax tree cannot answer it.
    """
    by_module = {os.path.splitext(os.path.basename(rel))[0]: rel for rel in scanned}
    for rel, facts in scanned.items():
        for record in facts.attribute_writes:
            if record["fixture"]:
                continue
            module = facts.import_aliases.get(record["alias"])
            target = by_module.get(module) if module else None
            if not target or target == rel:
                continue
            if record["attr"] not in scanned[target].output_names:
                continue
            facts.writes.add(record["name"])
            facts.redirected_writes.append(dict(record, module=module, script=target))
    return scanned


def _mixed_stage_arms(rel):
    """The stages a script's declared arms disagree about, or None if they agree.

    A script whose arms are declared is not one node and need not be one stage:
    panel_persistence.py parses the raw tape under --build and reads the parsed panel
    under --analyze. Which of the two an importer inherits cannot be read off the import
    statement, so it is not read off it.
    """
    stages = {arm["stage"] for arm in (D.ARMS.get(rel) or ())}
    return sorted(stages) if len(stages) > 1 else None


def _spread_tape_stage(scanned):
    """A script that walks the tape THROUGH AN IMPORT is a tape walker too.

    Measured, not supposed. panel_build.py, panel_persistence.py and panel_rebuild_v2.py
    each import build_quickwin_markouts and call its parse_day, which is what downloads
    an hourly file and deletes it again. None of the three imports boto3 or subprocess
    itself, so the call-site predicate read all three as analysis nodes -- and an
    analysis node is one that an analysis-only setting is allowed to schedule. That is
    the stage split failing in the direction that costs hours: changing the
    false-discovery rate would have planned three raw-tape walks.

    The rule is transitive over LOCAL imports only. An import of numpy or json cannot
    make anything a tape walker, because a module outside this tree is not scanned and
    contributes no locator.

    AND IT STOPS AT A MODULE WHOSE ARMS DISAGREE. panel_persistence.py holds two
    declared arms, and they are different stages by declaration: --build parses the raw
    tape, --analyze reads the parsed panel. Its file therefore reads as a tape walker,
    but the module a caller imports is neither arm -- panel_extended.py imports it to
    reuse the analysis estimators and calls nothing that touches the tape. Inheriting
    tape from an arm the importer never calls would put an hours-long label on a run
    that reads one panel, and the planner spends that label: a tape node is scheduled
    alone, behind a free-space guard, and never in parallel. The refusal is recorded
    rather than silent, because a stage that was declined is exactly the kind of fact
    that has to be visible to be argued with.
    """
    by_module = {os.path.splitext(os.path.basename(rel))[0]: rel for rel in scanned}
    changed = True
    while changed:
        changed = False
        for rel, facts in scanned.items():
            if facts.fetches_tape:
                continue
            for module in sorted(facts.imports_local):
                upstream = by_module.get(module)
                if not upstream or upstream == rel or not scanned[upstream].fetches_tape:
                    continue
                stages = _mixed_stage_arms(upstream)
                if stages:
                    refusal = {"module": module, "script": upstream, "stages": stages,
                               "why": "its declared arms are not one stage, so the "
                                      "importer inherits neither"}
                    if refusal not in facts.tape_not_inherited:
                        facts.tape_not_inherited.append(refusal)
                    continue
                facts.fetches_tape = True
                facts.tape_via = module
                changed = True
                break
    return scanned


def _apply_declarations(facts):
    """Move every declared I/O call out of the residue, and add the edges it names.

    What is left in facts.unresolved afterwards is the residue proper: file operations
    nobody has yet either taught the folder to read or written down. That number is the
    one worth printing, because the old 51 mixed it with a dozen calls that were never
    edges at all.
    """
    residue, declared = [], []
    for record in facts.unresolved:
        entry = D.classify(facts.rel, record.get("scope"), record["call"])
        if entry is None:
            residue.append(record)
            continue
        record = dict(record, declared=entry["class"], why=entry["why"])
        declared.append(record)
        if entry["class"] == "reads":
            facts.reads.update(entry.get("reads", ()))
        elif entry["class"] == "writes":
            facts.writes.update(entry.get("writes", ()))
    facts.unresolved = residue
    facts.declared = declared
    return facts


def _arms_of(facts):
    """One node per declared arm of a script, or a single node when it has none."""
    arms = D.ARMS.get(facts.rel)
    if not arms:
        return [Node(facts)]
    return [Node(facts, argv=arm["argv"], stage=arm["stage"],
                 outputs=arm["writes"], inputs=arm["reads"]) for arm in arms]


_SPELLING_MARK = "\x01"


def _subsuming_producer(name, produced):
    """The produced FAMILY a read pattern is a narrower spelling of, if there is one.

    One family gets spelled two ways whenever two scripts assemble the name from
    different pieces: i4_l2_mid.py writes mid_series_{coin}{suffix}.npz, whose adjacent
    holes collapse to mid_series_*.npz, while step1_inventory.py reads
    mid_series_{coin}_{period}.npz, which keeps the underscore and folds to
    mid_series_*_*.npz. Both name the same sixteen files on disk. Read as two nodes,
    one of them has a producer and no readers and the other has readers and no
    producer, and the edge between the two halves of the pipeline disappears.

    A read pattern is matched against a produced pattern by neutralising its own stars
    first, so the question asked is "would every name this reader can mean also be a
    name that producer writes". Only an unambiguous single answer is used: two
    candidate producers means the spelling is genuinely ambiguous, and inventing an
    edge there would be the name-matching mistake this module exists to avoid.
    """
    if "*" not in name:
        return None
    probe = name.replace("*", _SPELLING_MARK)
    hits = [q for q in produced
            if q != name and "*" in q and fnmatch.fnmatch(probe, q)]
    return hits[0] if len(hits) == 1 else None


def graph():
    """The whole graph, read from the syntax trees of every tracked script."""
    scanned, nodes, unresolved = {}, {}, {}
    made_by, read_by = {}, {}
    rules = _ignore_rules()
    for rel in tracked_scripts():
        if os.path.basename(rel) == SELF_SCRIPT and rel == SELF_SCRIPT:
            continue
        scanned[rel] = _apply_declarations(scan(rel, rules))
    # Before the stage spread and before any node is made: a write performed through
    # another module is still this script's write, and a script with no write is not a
    # node at all, so a redirect settled later would be settled too late.
    _resolve_redirected_writes(scanned)
    _spread_tape_stage(scanned)

    # First pass: who writes what. The readers cannot be resolved until this is known,
    # because a reader's name may be a narrower spelling of a family somebody writes.
    for rel, facts in scanned.items():
        facts.writes.discard(SELF_OUTPUT)
        for node in _arms_of(facts):
            for name in node.outputs:
                made_by.setdefault(name, []).append(node.key)
    produced = set(made_by)
    spellings = {}

    for rel, facts in scanned.items():
        if facts.unresolved:
            unresolved[rel] = facts.unresolved
        for name in list(facts.reads | facts.declared_inputs):
            if name in produced:
                continue
            family = _subsuming_producer(name, produced)
            if family:
                spellings[name] = family
                facts.reads.discard(name)
                facts.declared_inputs.discard(name)
                facts.reads.add(family)
        # Every script counts as a reader, producer or not: an artifact read only by a
        # check still has readers, and a check is not a node of this graph.
        for name in facts.inputs:
            read_by.setdefault(name, []).append(rel)
        if not facts.writes and rel not in D.ARMS:
            continue
        for node in _arms_of(facts):
            nodes[node.key] = node

    conflicts = {a: sorted(v) for a, v in made_by.items() if len(v) > 1}
    orphans = {a: sorted(v) for a, v in read_by.items() if a not in made_by}
    built = Graph(nodes, conflicts, orphans, _cycles(nodes), unresolved, scanned)
    built.spellings = spellings
    return built


def argv_census(graph_=None):
    """Which producers read their command line, counted twice by different means.

    Why it is counted twice. This build declines to launch a producer that reads its
    command line, so the list of such producers decides which artifacts a run can
    refresh and which a person has to launch by hand. A list that quietly loses a
    member does not fail; it just runs that producer bare and files the fallback arm
    under the name of the result. One predicate cannot notice that about itself.

    So the same question is put two ways and the answers are compared as SETS OF
    SCRIPTS. The syntax tree answers it by expression: an add_argument call, or a read
    of sys.argv that is not argv[0]. The source text answers it by line, knowing
    nothing about either. The self-test fails when the two sets differ, and prints the
    difference in both directions rather than a count, because a count says only that
    something is wrong and the names say which script.

    Returns the two sets, their symmetric difference, and the per-node detail.
    """
    graph_ = graph_ or graph()
    by_tree, by_text, detail = set(), set(), {}
    for rel, facts in graph_.scanned.items():
        if facts.argv_manual:
            by_tree.add(rel)
        with open(os.path.join(ROOT, rel), encoding="utf-8") as handle:
            lines = _argv_lines(handle.read())
        if lines:
            by_text.add(rel)
        if facts.argv_manual or lines:
            detail[rel] = {"tree_lines": sorted({r["line"] for r in facts.argv_manual}),
                           "text_lines": lines,
                           "options": sorted({r["option"] for r in facts.argv_manual
                                              if r["option"]}),
                           "scopes": sorted({r["scope"] for r in facts.argv_manual}),
                           "is_a_producer": any(n.script == rel
                                                for n in graph_.nodes.values())}
    return {
        "manual_by_syntax_tree": sorted(by_tree),
        "manual_by_source_text": sorted(by_text),
        "disagreement": sorted(by_tree ^ by_text),
        "detail": detail,
        # The population the refusal actually acts on: producer nodes, not scripts. A
        # script that reads the command line but writes no artifact is never launched
        # by this build, so it cannot be run bare by it either.
        "nodes_reading_the_command_line": sorted(
            node.key for node in graph_.nodes.values() if node.facts.takes_argv),
        "nodes_by_argparse_only": sorted(
            node.key for node in graph_.nodes.values()
            if node.facts.argv_flags and not node.facts.argv_manual),
        "nodes_by_sys_argv_only": sorted(
            node.key for node in graph_.nodes.values()
            if node.facts.argv_manual and not node.facts.argv_flags),
        "nodes_by_both": sorted(
            node.key for node in graph_.nodes.values()
            if node.facts.argv_manual and node.facts.argv_flags),
    }


# =====================================================================
# 5. WHAT THE SKIP RULE IS ALLOWED TO READ
# =====================================================================

# Fields of settings.fingerprint() that describe the SETTINGS MODULE rather than the
# run. horizon_s and lens say which column the run chose; headline_horizon_s and the
# rest say what the module declares, and those are what moves under a script's feet.
# Comparing the run's own choices would call every artifact stale the moment a second
# artifact chose a different horizon on purpose.
SETTINGS_OWNED_FIELDS = (
    "headline_horizon_s", "companion_horizon_s", "headline_lens",
    "reliability_seed", "fdr_alpha", "persistence_floor_fills", "whale_drop_k",
    "master_seed", "n_perm", "n_boot", "rank_floor_fills", "min_common_wallets",
)

# The five above that settings.py is still MIGRATING onto, and which therefore have to
# be read out of a different place in the artifact.
#
# WHY A SEPARATE PLACE. An artifact records such a setting in one of two forms, and the
# two mean opposite things. Nested inside declared_not_confirmed it is the DECLARATION
# as it stood when the file was written, which is settings-owned and is what this rule
# exists to compare. At the top level it is the value the run ITSELF stated, passed as
# an override by a caller that knew what it drew, which is the run's own choice in the
# same sense as horizon_s and lens.
#
# Measured on 31 July 2026, across the 49 tracked results files that carry a
# fingerprint block: rank_floor_fills appears nested in 18 files, all reading 50, which
# is the declaration; and at the top level in 31 files reading 1, 10, 25, 30, 50,
# [20, 50], [20, 50, 100], [10, 25, 50], [30, 50, 100] and [50, 100], which are
# sensitivity arms. Comparing the top-level form against the declaration would call 25
# of those 31 stale on the spot and buy a full recompute out of files that are doing
# exactly what they were written to do. So the nested form is compared and the
# top-level form is left alone.
#
# THE COST OF THAT CHOICE, stated rather than left to be discovered: a run that
# CONFIRMED the declared value at the top level is not compared either, because its
# record is indistinguishable from an arm that happens to sit on the declaration. Seven
# files are in that position today -- six confirming rank_floor_fills 50 and one
# confirming n_boot 2000 -- and a move of those declarations will not schedule them.
MIGRATING_DECLARATION_FIELDS = frozenset(
    ("master_seed", "n_perm", "n_boot", "rank_floor_fills", "min_common_wallets"))

# The settings a MARKING depends on, and nothing else. A tape node is rebuilt when one
# of these moves; no other setting can reach it. LADDER_S decides which markout
# columns exist, LENSES which reference prices are marked, COIN_CODES_BY_ARTIFACT
# which coins are in the file. The false-discovery rate, the seeds, the wallet floors
# and the permutation budget decide nothing about the tape and appear nowhere here.
MARKING_SETTINGS = ("LADDER_S", "LENSES", "COIN_CODES_BY_ARTIFACT")

_HASH_CACHE = {}


def sha256_of(path):
    """Hash of a file, memoised on identity so one panel is not hashed 26 times."""
    stat = os.stat(path)
    key = (path, stat.st_mtime_ns, stat.st_size)
    if key not in _HASH_CACHE:
        _HASH_CACHE[key] = artifact.sha256_file(path)
    return _HASH_CACHE[key]


_INDEX_CACHE = {}


def _file_index():
    """Every file in the tree, indexed by bare name. Walked once per run.

    One panel is read by twenty-five scripts, so a lookup that walked the tree each
    time would walk it hundreds of times for one plan.
    """
    if ROOT not in _INDEX_CACHE:
        index = {}
        # Anything that writes into the tree must call forget_tree() afterwards, or a
        # file created during this process stays invisible to every later lookup and
        # the node that produced it reads back as "absent from the tree" -- planned
        # again on the very next pass, which is the opposite of what a build is for.
        for dirpath, dirnames, filenames in os.walk(ROOT):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for found in filenames:
                index.setdefault(found, []).append(os.path.join(dirpath, found))
        _INDEX_CACHE[ROOT] = index
    return _INDEX_CACHE[ROOT]


_SCRIPTS_CACHE = {}


def script_index():
    """Producer basename -> repo-relative path, from the provenance gate's own map.

    Cached per root because the map is built by walking the tree, and the skip rule
    asks for it once per node. Imported rather than rewritten for the reason the
    .gitignore predicate is: a basename that appears twice must resolve to None
    rather than to whichever copy the walk met first, and that decision has one home.
    """
    if ROOT not in _SCRIPTS_CACHE:
        _SCRIPTS_CACHE[ROOT] = _prov.scripts_on_disk(ROOT)
    return _SCRIPTS_CACHE[ROOT]


def forget_tree():
    """Drop the cached listing and the cached hashes, because the tree just changed.

    All three caches are keyed on state that a producer run invalidates: the index on
    which files exist, the hashes on what they contain, the script map on which .py
    files are there. Clearing one without the others leaves a plan that half-believes
    the old tree.
    """
    _INDEX_CACHE.pop(ROOT, None)
    _SCRIPTS_CACHE.pop(ROOT, None)
    _HASH_CACHE.clear()


def locate_all(name):
    """Every repository path an artifact name stands for.

    A name with a star is a FAMILY -- mid_series_*.npz is sixteen files written by one
    call in a loop -- and the members are matched by the same star. A plain name that
    matches twice returns both paths and the caller declines to compare: resolving to
    whichever copy the walk met first would make the hash comparison confidently wrong
    rather than silent.
    """
    index = _file_index()
    if "*" not in name:
        return sorted(index.get(name, ()))
    return sorted(path for found, paths in index.items()
                  if fnmatch.fnmatch(found, name) for path in paths)


def _locate(name):
    """The single path a name stands for, or None if it stands for none or many."""
    hits = locate_all(name)
    return hits[0] if len(hits) == 1 else None


def marking_view(overrides=None):
    """The marking settings as they stand now, with an optional injected change.

    The override argument exists so the self-test can ask "what would a ladder change
    plan" without editing settings.py, which is the only way to test the stage split
    in the direction where it must fire.
    """
    view = {name: getattr(S, name) for name in MARKING_SETTINGS}
    view.update(overrides or {})
    return view


def required_markout_columns(view=None):
    """Column names a current marking must carry, per lens family.

    BUILT from settings, never typed. settings.py states the rule as its second: a
    field name never states a setting its value does not come from, so the ladder
    column names are asked of the module that owns the ladder.
    """
    view = view or marking_view()
    ladder = tuple(view["LADDER_S"])
    # settings refuses to name a column for a window no artifact carries, and that
    # refusal is the guard, not a bug to route around. It is also exactly the answer
    # this function needs: a window whose column cannot be named is a window the
    # marking does not have, so it belongs in the gap list rather than the required
    # list. Hence the refusal is caught here and turned into a named gap, and the
    # accessor keeps its strictness for every other caller.
    out = {"print": set(), "mid": set(), "unnameable": set()}
    for h in ladder:
        for lens, accessor in (("print", S.headline_print_col),
                               ("mid", S.headline_mid_col)):
            try:
                out[lens].add(accessor(h))
            except ValueError:
                out["unnameable"].add(h)
    return out


def _npz_columns(path):
    """Column names inside an .npz without loading an array or importing numpy.

    An .npz is a zip of .npy members, so the member list is the column list and costs
    a directory read. A 572 MB panel answers in milliseconds.
    """
    try:
        with zipfile.ZipFile(path) as archive:
            return {os.path.splitext(n)[0] for n in archive.namelist()}
    except (zipfile.BadZipFile, OSError):
        return None


def marking_gaps(path, view=None):
    """Horizons the ladder asks for that this marking file does not carry.

    Empty means current. None means the question does not apply: the file carries no
    markout column at all, so it is not a marking, and asking a mid-price series for a
    markout column would call every such file permanently stale.
    """
    columns = _npz_columns(path)
    if columns is None:
        return None
    required = required_markout_columns(view)
    gaps = []
    # A window the ladder asks for whose column cannot even be named is a gap for every
    # marking file, because no file can carry a column that has no name.
    for h in sorted(required.pop("unnameable", ())):
        gaps.append(f"h={h}s: no column name exists for this window, so the marking "
                    f"has to be rebuilt before anything can score on it")
    for lens, wanted in required.items():
        present = {c for c in columns if c in wanted}
        # A lens family counts as present in the file if ANY of its columns is there.
        family_seen = present or {c for c in columns
                                  if c.startswith("mo")
                                  and c.endswith("_mid") == (lens == "mid")}
        if not family_seen:
            continue
        for column in sorted(wanted - present):
            gaps.append({"lens": lens, "column": column})
    return gaps


def _as_list(value):
    """A value in list form, for comparing a ladder against a single rung.

    None is the empty ladder and anything else is a ladder of one, so that a setting
    declared as a tuple and asked about as a scalar compare as the same shape. `or []`
    was used here once and quietly turned 0 and "" into the empty ladder as well.
    """
    if isinstance(value, (list, tuple)):
        return list(value)
    if value is None:
        return []
    return [value]


def setting_moved(was, now):
    """Whether two readings of one setting are different settings.

    THE CRASH THIS REPLACES. The comparison used to coerce BOTH sides with list() as
    soon as EITHER was a list, so asking what a ladder-valued setting would do at a
    single value -- `--what-if persistence_floor_fills=10`, where the recorded reading
    is [50, 100] and the asked-about one is 10 -- called list(10) and raised
    TypeError. The tool that exists to price a settings change could not be pointed at
    a scalar, which is the form most settings changes take.

    Mixed shapes are now answered rather than refused: a ladder and a rung are put in
    the same shape and compared. [50, 100] against 10 is a move; [10] against 10 is
    not, because a one-rung ladder and that rung are the same setting.
    """
    if isinstance(was, (list, tuple)) or isinstance(now, (list, tuple)):
        return _as_list(was) != _as_list(now)
    return was != now


def recorded_setting(block, field):
    """What an artifact recorded for one settings-owned field: (recorded?, value).

    For a migrating declaration the answer is read from declared_not_confirmed and
    nowhere else, for the reason written beside MIGRATING_DECLARATION_FIELDS: at the
    top level the same field name carries the run's own arm, not the declaration.

    A FIELD PRESENT WITH A NULL VALUE IS A DECLARATION THAT THE SETTING DOES NOT APPLY,
    AND THE PRESENCE OF THE KEY IS NOT EVIDENCE ABOUT ITS VALUE. settings.fingerprint()
    puts null into the block one way only: the producer passed it as an override, and
    the same call then names the field in `overridden` and says why in overrides_note --
    "no FDR family applies", "no bootstrap is drawn, so n_boot does not apply". Read as
    a value, that null compares unequal to every real setting, so asking `field in
    block` scheduled the node on the strength of a statement that there was nothing to
    compare. Measured across the tree on 11 August 2026: 96 fingerprint blocks hold 66
    null settings-owned fields and all 66 are named in `overridden`, none arriving by
    any other route, which is why the declaration is what is read here rather than the
    emptiness being read as meaning.

    The three outcomes stay apart. Declared not to apply -- no condition, here. Recorded
    as a number equal to today's -- the condition holds. Recorded as a number that
    differs -- the condition fails and the move is printed, which is the case of
    ws3_taker_pnl_results.json, whose whale_drop_k is a stated 5 against a declared 10
    and is named in `overridden` just the same. Membership alone would silence it too.
    """
    if field in MIGRATING_DECLARATION_FIELDS:
        declared = block.get("declared_not_confirmed")
        if isinstance(declared, dict) and field in declared:
            return True, declared[field]
        return False, None
    if field in block:
        if block[field] is None and field in set(block.get("overridden") or ()):
            return False, None
        return True, block[field]
    return False, None


def _rel(path):
    """A repository path in the spelling the checks use: relative, forward slashes."""
    return os.path.relpath(path, ROOT).replace(os.sep, "/")


def status(node, graph_, settings_view=None, marking_overrides=None):
    """Whether a node has to run, and the reason in the words of the thing that moved.

    Three verdicts, and the third is the one this function exists to get right. The
    fold from conditions to verdict is skip_rule.verdict(); what happens here is
    putting the conditions, which needs the tree.

      up_to_date  every condition was put and every one held
      must_run    a condition was put and failed; `reasons` names which
      unknown     a condition could not be put, so no answer exists. Counted apart,
                  printed apart, and NOT SCHEDULED by default -- see plan().

    WHAT CHANGED HERE, AND WHY IT IS NOT A PREFERENCE. The old rule reached
    up_to_date in two ways that were not evidence. A raw-tape node whose markout
    ladder was complete returned up_to_date having asked nothing else at all, and two
    nodes in this tree were in that position on 31 July. And an input recorded with no
    hash was met with a bare `continue`, so 24 of the 183 input records in this tree
    were neither compared nor mentioned. Both are now conditions that were ASKED and
    could not be ANSWERED, which is the third verdict and not the first.
    """
    conditions = []
    scripts = script_index()
    view = marking_view(marking_overrides)
    current = settings_view if settings_view is not None else S.declaration_view()

    for name in node.outputs:
        paths = locate_all(name)
        if not paths:
            conditions.append(K.failed("output_present", name, "absent from the tree"))
            continue

        if node.stage == "tape":
            # A tape node's SETTINGS condition is the marking, and only the marking.
            # No settings field is read in this branch, which is what makes the
            # property provable rather than promised: no analysis setting can reach
            # here, so no analysis setting can schedule a raw-tape walk.
            for path in paths:
                base = os.path.basename(path)
                gaps = marking_gaps(path, view)
                if gaps:
                    conditions.append(K.failed(
                        "marking_ladder", base,
                        "the ladder asks for a column this marking does not carry",
                        gaps))
                elif gaps is None:
                    conditions.append(K.unanswerable(
                        "marking_ladder", base,
                        "not a zip archive, so its columns cannot be read without "
                        "loading it", K.NO_RECORD_AT_ALL))
                else:
                    conditions.append(K.held(
                        "marking_ladder", base,
                        "the file carries a column for every rung of the ladder, in "
                        "every lens family it already holds"))
                # AND THE TWO CONDITIONS A TAPE NODE CANNOT PUT, said rather than
                # passed over. This is the repair: with only the line above, a
                # complete marking read as proof that the node was current, when its
                # producer had never been compared and its input no longer exists.
                conditions.append(_producer_condition(path, base, scripts))
                conditions.extend(_input_conditions(path, base, node))
            continue

        if len(paths) > 1:
            conditions.append(K.unanswerable(
                "output_present", name,
                f"the name stands for {len(paths)} files, so no one record can be "
                "compared against it", K.NOT_RESOLVABLE))
            continue
        path = paths[0]

        conditions.append(_producer_condition(path, name, scripts))
        conditions.extend(_input_conditions(path, name, node))
        conditions.extend(_settings_conditions(path, name, current))

    reasons, gaps = K.split(conditions)
    return {"script": node.script, "argv": list(node.argv),
            "node": node.key, "stage": node.stage,
            "verdict": K.verdict(conditions),
            "reasons": reasons, "unknown": gaps,
            "unknown_causes": K.causes(conditions),
            "conditions_put": len(conditions),
            "conditions_answered": sum(1 for c in conditions if c["answered"]),
            "known_runtime_s": recorded_runtime(node)}


def _producer_condition(path, output, scripts):
    """Do the bytes that wrote this file equal the script on disk. One home, not two.

    Handed straight to skip_rule, which hands it to checks/run_record.py. This
    function exists only to turn an absolute path into the repo-relative spelling
    those modules take.
    """
    return K.producer_condition(_rel(path), ROOT, output, scripts)


def _read_meta(path):
    """The _meta block of an artifact, or None where there is none to read."""
    try:
        return artifact.read_meta(path)
    except (ValueError, OSError):
        return None


def _input_conditions(path, output, node):
    """One condition per input the artifact recorded, plus the raw-tape statement.

    AN EMPTY INPUT LIST IS NOT THE SAME AS A MISSING ONE, and telling them apart is
    what this function is careful about. Five gates in this tree legitimately record
    inputs=[]: they walk the whole repository rather than reading one file, and they
    state the tree in their scope instead of hashing it member by member. Reading that
    declaration as a gap would put five nodes into "cannot be told" for doing exactly
    what they were written to do -- measured, it did, in the first draft of this rule.

    So the empty list is checked AGAINST THE GRAPH, which derives what a producer
    reads from its own syntax tree and knows nothing about what the artifact recorded.
    Agreeing at zero is a declaration and holds. Disagreeing -- the graph derives
    inputs and the artifact recorded none of them -- is a gap, because then the file
    is silent about something it demonstrably read.

    Calibrated in both directions on 31 July 2026: five nodes must stay silent
    (chk_expensive_edits, chk_headline_horizon, chk_no_abs_paths, chk_run_happened,
    chk_settings_home, all with zero derived inputs) and NO node in the tree is on the
    firing side today, so that half is exercised on a fabricated pair in the self-test
    rather than left untested.
    """
    meta = _read_meta(path)
    if meta is None:
        if node.stage == "tape":
            return [K.raw_tape_condition(output, node.key)]
        return [K.unanswerable(
            "input_bytes", output,
            "the file carries no _meta block, so it records nothing about what it "
            "read and whether that has since changed cannot be asked",
            K.NO_RECORD_AT_ALL)]
    records = meta.get("inputs")
    if records is None:
        return [K.unanswerable(
            "input_bytes", output,
            "the _meta block holds no inputs list at all, so what this file read was "
            "never recorded", K.NO_RECORD_AT_ALL)]
    if not records:
        if node.stage == "tape":
            return [K.raw_tape_condition(output, node.key)]
        if node.inputs:
            return [K.unanswerable(
                "input_bytes", output,
                f"the artifact recorded an empty input list while the graph derives "
                f"{len(node.inputs)} input(s) from this producer's own syntax tree, "
                f"so what it read is not on file and cannot be compared",
                K.NO_HASH_RECORDED, {"derived_inputs": node.inputs})]
        return [K.held(
            "input_bytes", output,
            "the producer declares no file input and the graph derives none from its "
            "syntax tree: what it walks is the repository itself, which its scope "
            "states rather than its input list hashing member by member")]
    return [K.input_condition(record, output, _locate, sha256_of)
            for record in records if isinstance(record, dict)]


def _settings_conditions(path, output, current):
    """One condition per settings-owned field the artifact stamped.

    A field the CURRENT view does not carry is not a field that moved: there is
    nothing to compare it against, and reading its absence as None would call every
    artifact that recorded it stale. A field the ARTIFACT did not record is a gap, and
    it is the reason the settings block is checked field by field rather than whole.
    """
    meta = _read_meta(path)
    block = (meta or {}).get("settings_fingerprint")
    if not isinstance(block, dict):
        return [K.unanswerable(
            "settings", output,
            "stamps no settings fingerprint, so no declared setting can be compared "
            "against what settings.py holds now",
            K.NO_RECORD_AT_ALL if meta is None else K.NO_HASH_RECORDED)]
    out = []
    for field in SETTINGS_OWNED_FIELDS:
        if field not in current:
            continue
        recorded, was = recorded_setting(block, field)
        if not recorded:
            continue
        now = current[field]
        if setting_moved(was, now):
            out.append(K.failed("settings", output, f"the setting {field} moved",
                                {"field": field, "recorded": was, "now": now}))
        else:
            out.append(K.held("settings", output,
                              f"the setting {field} is what this file was computed "
                              f"under", {"field": field, "value": now}))
    # A file that stamped a fingerprint naming NONE of the settings-owned fields puts
    # no settings condition at all, and that is deliberate rather than an oversight.
    # The condition is per FIELD: a field the current view does not carry is not a
    # field that moved, and symmetrically a field the artifact never recorded is not a
    # field that moved either. The cost is stated where it is paid, beside
    # MIGRATING_DECLARATION_FIELDS: a run that confirmed a declaration at the top
    # level rather than nesting it is not compared, and a move of that declaration
    # will not schedule it. Seven files are in that position today.
    return out


def recorded_runtime(node):
    """The longest runtime any of this node's outputs recorded, or None.

    None is the common answer today and is the point of the field: five of the tracked
    results files record how long they took, so a plan can price a fraction of itself
    and must say which fraction rather than present a made-up total.
    """
    best = None
    for name in node.outputs:
        if not name.endswith(".json"):
            continue
        path = _locate(name)
        if not path:
            continue
        try:
            block = artifact.read_meta(path).get(artifact.VOLATILE_KEY)
        except (ValueError, OSError):
            continue
        if isinstance(block, dict) and isinstance(block.get("runtime_s"), (int, float)):
            best = max(best or 0.0, float(block["runtime_s"]))
    return best


# =====================================================================
# 6. THE DISK LIMIT, WRITTEN INTO THE BUILD
# =====================================================================

# The two settings that decide what happens to a day of raw tape once it is parsed.
# They have ONE home, here, and the policy text below is assembled out of them rather
# than spelling them again, so a renamed key cannot leave a stale key name in the prose.
# That both names are the ones the parsers really read is checked against their syntax
# trees, not against this comment.
RAW_CACHE_KEEP_KEY = "CAP_KEEP_RAW"    # whether a parsed day survives the run
RAW_CACHE_DIR_KEY = "CAP_RAW_CACHE"    # where a fetched day lands and is looked for

# The rule, in one line, so that it is a property of the build and not of anyone's
# memory: PARSED PANELS ARE CACHED, AND A RAW DAY IS KEPT OR DELETED BY A DECLARED
# SETTING WHOSE DEFAULT IS TO DELETE.
CACHE_POLICY = {
    "cached": "parsed panels and the maps beside them -- the .npz markout files and "
              "the per-wallet taker maps. They are what every analysis node reads, "
              "they are deterministic given the tape, and they are what a rebuild is "
              "trying to avoid.",
    "raw_days": "the raw tape, deleted by default. Each day arrives as 24 hourly "
                "compressed files and is parsed; whether the day's directory then "
                f"survives is decided by {RAW_CACHE_KEEP_KEY}, and "
                f"{RAW_CACHE_DIR_KEY} says where it lives. A day already in that "
                "directory with a full complement of hourly files is reused instead of "
                "refetched. No build node stands for a raw day either way, kept or "
                "deleted, so nothing in this graph can ask for one directly.",
    "why": "the system volume cannot hold thirty days of the tape at once, so deleting "
           "is what a long unattended run wants and is the default. Writing the rule "
           "here is what makes it a build property instead of six independent habits.",
    # Why the default has an off switch at all. Written down because the opposite rule
    # stood here until 2026-08-03 and was two days out of date: it said there is no
    # local cache of raw days and that a rebuild refetches, which the tree stopped
    # doing on 2 August.
    "raw_day_disposal": "deletion is the DEFAULT, not the wired-in action, and the key "
                        "that turns it off is declared rather than implied. Three "
                        "reasons, and the first is about proof rather than disk. An "
                        "input deleted before the artifact is written cannot be "
                        "hashed, so a node that walks the tape can never be PROVEN "
                        "unchanged, only assumed -- and reproducibility with a missing "
                        "input is not checked at all. Three nodes here walk the same "
                        "ten days, so without a kept day one recompute batch pays "
                        "three fetches for identical bytes. And the volume is still "
                        "the scarce thing, which is why keeping is the setting and "
                        "deleting is what happens when nobody sets it.",
}

# The parsers, named rather than counted. Each one fetches a day of the raw tape and
# deletes that day's directory before it fetches the next, which is what makes the
# never_cached rule above true of the code and not only of this docstring. The
# self-test checks each name against the tree in two ways -- the script exists and it
# calls something that removes a directory -- because a list of file names in a comment
# is exactly the kind of statement that goes stale without anybody noticing.
#
# THIS LIST IS TYPED BY HAND, AND THAT IS ITS WEAKNESS. The census below walks THIS
# tuple, so a parser missing from it is invisible to the census by construction, and
# the census then answers a question about six files while reading as an answer about
# the tree. That is exactly what happened: ks2_markout_multiday.py was added on
# 2026-08-04 after it was found to build an s3:// key, fetch it with `aws s3 cp` and
# remove the hour in a `finally` with no condition on it, having never been named here.
# The disposal answer moved from three of six to three of seven without a single line
# of parser code changing.
#
# WHAT THE TREE ALREADY DERIVES, AND WHY IT DOES NOT REPLACE THIS TUPLE. facts
# .fetches_tape is derived from the syntax -- a tape locator anywhere in the file and a
# fetch mechanism beside it -- and on 2026-08-04 it read 16 of 105 scanned scripts, 8 of
# them directly rather than through an import. The two populations are close and they
# are NOT the same question, which is why one is not yet folded into the other. The
# derived predicate is wider at both ends: checks/chk_book_orientation.py earns it from
# a bucket named in its header plus any subprocess call at all, and i4_l2_mid.py and
# i3_book_comparator.py fetch a DIFFERENT archive -- the level-2 book -- whose disposal
# rule is not this one. It is also narrower: panel_build.py and panel_rebuild_v2.py
# belong here and reach the tape only through the parser they import, so the direct
# reading misses them. Deriving this tuple therefore needs a predicate for "fetches the
# fills tape and must dispose of what it fetched", which is a narrower statement than
# either reading gives today. Until that predicate exists and is calibrated on two
# opposite cases, the list stays typed and the gap stays written down here.
#
# NAMED BY BASENAME, AND RESOLVED AGAINST THE TREE INSTEAD OF AGAINST A PLACE. Five of
# these seven were written here as the paths they sat at, and on 2026-08-11 the tree was
# laid out by pipeline group: the five moved into subdirectories, and every one of them
# read back as "not in the tree" although not a line of any parser had changed. FOUR
# self-test lines failed on that alone -- that the parsers are in the tree, that the
# location key is read by something, that they delete by default, and that one of them
# inherits its gate through the parser it imports. Every one of the four is worded as a
# statement about what a parser DOES, and all four were false for a reason that was
# purely about where a file sat. Measured by running the self-test at each commit: 1
# failure before the move, 7 at it.
#
# A name joined to a place goes stale on the next move, and there will be a next move.
# A name resolved through the tree's own basename map does not, so the names here are
# basenames and tape_parser_paths() below is the only thing that turns one into a path.
TAPE_PARSERS = (
    "ks2_persistence_10day.py",
    "ks2_markout_multiday.py",
    "build_quickwin_markouts.py",
    "panel_build.py",
    "panel_rebuild_v2.py",
    "chk_field_hygiene.py",
    "chk_liquidation_field.py",
)

# Calls that dispose of a fetched day. Any one of them is enough; which one a parser
# uses depends on whether it fetched a directory of hourly files or a single hour.
DISPOSAL_CALLS = ("shutil.rmtree", "os.remove", "os.unlink", "unlink")

# How many I/O calls the graph is allowed to leave unaccounted for. This is a DECLARED
# DEBT, not a preference: it was measured at 0 on 31 July 2026, after 28 of the original
# 51 were recovered by teaching the folder to read a helper, a dict of paths and a loop
# over a glob, and the remaining 23 were written down in build_declarations.py. The
# number may only ever be lowered. Raising it to make a failing self-test pass would
# turn the one honest measurement of this graph's blind spot into a rubber stamp, which
# is precisely how a graph comes to look complete while a fiftieth of its I/O is
# invisible.
UNRESOLVED_IO_CEILING = 0

# Free space a tape node is required to find before it is launched. This is a STATED
# ALLOWANCE and not a measurement, and saying which it is matters: a day of raw tape
# survives on this machine only when RAW_CACHE_KEEP_KEY is set, so on a default run
# there is nothing to weigh and the number here was never derived from one. The guard
# prints the measured free space beside it so a reader judges the margin rather than
# trusting the constant.
RAW_DAY_ALLOWANCE_GB = 2.0

# Tape nodes are scheduled one at a time. Two parsers each holding a day's hourly
# directory is how the volume is actually filled; one at a time is the only
# concurrency rule that makes the allowance above mean anything.
MAX_CONCURRENT_TAPE_NODES = 1


def _module_file(module):
    """The syntax tree of a tracked module of this repository, by module name.

    None where the name is not a file of this tree, which is the answer that matters:
    an alias pointing outside the repository can carry no statement about our settings,
    and crediting one would be the mistake this function's caller already made once
    with artifact.py.
    """
    for rel in tracked_scripts():
        if os.path.splitext(os.path.basename(rel))[0] != module:
            continue
        try:
            with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
                return ast.parse(fh.read())
        except (OSError, SyntaxError):
            return None
    return None


def _reads_a_cache_key(tree):
    """Functions of this file that read one of the raw-cache settings, by key.

    A gate is written as `if keep_raw_days():`, never as a bare os.environ read at the
    deletion itself, so the key is one call away from the branch every time. This is
    the map that closes that step.
    """
    keys = (RAW_CACHE_KEEP_KEY, RAW_CACHE_DIR_KEY)
    out = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        found = sorted({child.value for child in ast.walk(node)
                        if isinstance(child, ast.Constant) and child.value in keys})
        if found:
            out[node.name] = found
    return out


def disposal_calls(source):
    """Every disposal call in one SOURCE TEXT: its name, its line and its gate.

    It takes the source rather than a path for one reason, and the reason is a repair
    made on 2026-08-04. The two opposite cases this predicate is calibrated on used to
    be two live nodes of the tree: a parser that deleted under the declared key and a
    parser that deleted outright. The second one stopped existing the day the tree was
    repaired -- every parser now stands under the key -- and an assertion naming a live
    node as the ungated case can then only fail, which is a calibration dying together
    with the defect it was anchored to. Reading a source string instead lets the ungated
    case be WRITTEN in the self-test and put through this very function, so the negative
    half survives the tree being correct. The positive half stays on the live tree,
    because a predicate that only ever saw its own fixtures is not calibrated on this
    repository at all.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    parents = _parent_map(tree)
    local_readers = _reads_a_cache_key(tree)
    aliases = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                if isinstance(node, ast.ImportFrom):
                    aliases[alias.asname or alias.name] = node.module or alias.name
                else:
                    aliases[alias.asname or alias.name.split(".")[0]] = \
                        alias.name.split(".")[-1]

    def gate_of(node):
        """The settings a branch above this call tests, walking outward."""
        walk, seen = parents.get(node), []
        while walk is not None:
            if isinstance(walk, ast.If):
                for called in ast.walk(walk.test):
                    if not isinstance(called, ast.Call):
                        continue
                    name = _dotted(called.func)
                    head, _, attr = name.rpartition(".")
                    if not head:
                        seen += local_readers.get(name, [])
                    else:
                        # `bqm.keep_raw_days()`: the reader is in the module the alias
                        # names, so the file that owns the key is read there rather than
                        # guessed from the attribute name.
                        module = aliases.get(head)
                        upstream = _module_file(module) if module else None
                        if upstream:
                            seen += _reads_a_cache_key(upstream).get(attr, [])
            walk = parents.get(walk)
        return sorted(set(seen))

    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _dotted(node.func) in DISPOSAL_CALLS:
            found.append({"call": _dotted(node.func), "line": node.lineno,
                          "gated_on": gate_of(node)})
    return sorted(found, key=lambda r: r["line"])


def disposal_shape(calls):
    """Which of the three shapes a set of disposal calls is.

    One rule, called by both the census over the tree and the calibration over the
    written fixtures, so the two cannot drift apart. A file counts as gated when AT
    LEAST ONE of its disposals stands under the declared key: the others clear a failed
    download and are not the day teardown the policy is about.
    """
    if not calls:
        return "none"
    return ("by_setting"
            if any(RAW_CACHE_KEEP_KEY in c["gated_on"] for c in calls)
            else "unconditional")


def tape_parser_paths():
    """Each named parser, resolved to where it sits, by CONTENT rather than by path.

    The one place a basename from TAPE_PARSERS becomes a path. Resolution goes through
    script_index(), which is the map the provenance gate already resolves a recorded
    producer through, so a parser and an artifact's producer are found by one rule and
    cannot disagree about where a file is.

    A name absent from the tree resolves to None, and so does a basename the tree holds
    twice. Both are answers rather than guesses: the census reads the second as "not
    present" instead of opening whichever copy the walk met first, which would attribute
    a disposal to the wrong file and read as a policy being honoured.
    """
    index = script_index()
    return {name: index.get(name) for name in TAPE_PARSERS}


def parser_disposal():
    """For each named parser: does it dispose of the day it fetched, and under what.

    Read out of the syntax tree, not out of a docstring. The answer is a row per parser
    so that a parser which stopped deleting reads as one changed row rather than as a
    policy that quietly became false.

    WHY THE GATE IS PART OF THE ANSWER. Until 2026-08-03 this returned the first
    disposal call found anywhere in the file and called that "deletes the day it
    fetched". Two things were wrong with it at once. It could not tell an unconditional
    deletion from one standing under a setting, and after 2 August 2026 the two heaviest
    parsers delete only by DEFAULT, with the deletion standing in the else-arm of a
    branch that reads the declared key -- so a true statement about the presence of a
    call was being read as a statement about behaviour. And the call it picked was
    arbitrary: build_quickwin_markouts.py holds four removal calls, three of them
    clearing a failed download and one being the day teardown, and the first in walk
    order is not the one the policy is about.

    So each row now carries EVERY disposal call the file makes, each with the setting
    its branch reads, if any. A parser counts as gated when at least one of its
    disposals stands under the declared key; ungated when none of them does. The
    per-call list is kept in the row so that the summary can be argued with rather than
    only agreed with.
    """
    def disposals(rel):
        """Every disposal call in one tracked file of this tree, by path."""
        path = os.path.join(ROOT, rel)
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as fh:
            return disposal_calls(fh.read())

    # A parser can dispose THROUGH THE PARSER IT IMPORTS, and one of them does:
    # panel_build.py holds no removal call of its own, because it fetches and parses by
    # calling parse_day out of build_quickwin_markouts, and that function deletes the
    # day. Reading only the direct calls reported it as a parser that keeps what it
    # fetches, which would have been a false alarm about the one rule the disk limit
    # rests on. The same transitive reading is what the stage predicate needs, and for
    # the same reason.
    def settings_read(rel):
        """Which of the two declared keys this file reads anywhere in its own body.

        Asked apart from the gate, because the two keys answer different questions:
        one decides whether the day survives, the other decides where it lives, and
        only the first can ever appear over a deletion. Without this the location key
        would be a name in the policy text that nothing has to honour.
        """
        tree = _module_file(os.path.splitext(os.path.basename(rel))[0])
        if tree is None:
            return []
        return sorted({key for keys in _reads_a_cache_key(tree).values()
                       for key in keys})

    by_module = {os.path.splitext(os.path.basename(rel))[0]: rel
                 for rel in tracked_scripts()}

    def summarise(row, calls):
        row.update(disposes=bool(calls), via=calls[0]["call"] if calls else None,
                   calls=calls, gated_on=sorted({k for c in calls
                                                 for k in c["gated_on"]}),
                   # WHICH shape this parser is, and the two are not the same statement.
                   # A parser is "by_setting" when a deletion of its stands under the
                   # declared key, and "unconditional" when it disposes and none does.
                   # Asked of disposal_shape rather than decided here, so that the
                   # calibration fixtures and this census go through one rule.
                   disposal=disposal_shape(calls))
        return row

    resolved = tape_parser_paths()
    rows = []
    for parser in TAPE_PARSERS:
        # The declared name and the place it resolved to are both kept, because they
        # answer different questions. A row is read back by its NAME, which is what the
        # policy above declares and what the assertions below name; the PATH is what a
        # reader opens, and it is a fact about today's tree rather than about the rule.
        rel = resolved.get(parser)
        path = os.path.join(ROOT, rel) if rel else None
        row = {"parser": parser, "script": rel or parser,
               "present": bool(path) and os.path.exists(path), "disposes": False,
               "via": None, "through": None, "calls": [], "gated_on": [],
               "disposal": "none", "reads_settings": []}
        if row["present"]:
            row["reads_settings"] = settings_read(rel)
            calls = disposals(rel)
            if calls:
                summarise(row, calls)
            else:
                # Only another NAMED PARSER counts as the route. The first version of
                # this credited any imported module that happened to hold a removal
                # call, and it passed by crediting artifact.py, whose only rmtree is in
                # its own self-test fixture. A check that passes for the wrong reason is
                # worse than one that fails.
                #
                # The gate travels with the route. panel_build.py fetches and parses by
                # calling parse_day out of build_quickwin_markouts, so whatever decides
                # the day's fate there decides it here, and reading this row as an
                # unconditional deletion would be the same mistake one level along.
                for module in sorted(scan(rel).imports_local):
                    upstream = by_module.get(module)
                    if (upstream and upstream != rel
                            and os.path.basename(upstream) in TAPE_PARSERS
                            and disposals(upstream)):
                        summarise(row, disposals(upstream))
                        row["through"] = module
                        break
        rows.append(row)
    return rows


def disk_free_gb(path=None):
    """Free space on the volume the repository sits on, in gigabytes."""
    stat = os.statvfs(path or ROOT)
    return stat.f_bavail * stat.f_frsize / (1024 ** 3)


def disk_guard(stage):
    """Whether a node of this stage may be launched, and the numbers behind the answer."""
    free = disk_free_gb()
    needed = RAW_DAY_ALLOWANCE_GB if stage == "tape" else 0.0
    return {"stage": stage, "free_gb": round(free, 2), "allowance_gb": needed,
            "ok": free >= needed,
            "note": CACHE_POLICY["raw_days"] if stage == "tape" else ""}


# =====================================================================
# 7. PLANNING
# =====================================================================

def _topological(nodes, graph_):
    """Producers ordered so that a node runs after everything it reads."""
    maker = {}
    for node in nodes:
        for name in node.outputs:
            maker.setdefault(name, node.key)
    by_script = {n.key: n for n in nodes}
    ordered, state = [], {}

    def visit(script):
        if state.get(script) == "done":
            return
        state[script] = "open"
        node = by_script[script]
        for name in node.inputs:
            upstream = maker.get(name)
            if upstream and upstream != script and state.get(upstream) != "open":
                visit(upstream)
        state[script] = "done"
        ordered.append(node)

    for script in sorted(by_script):
        visit(script)
    return ordered


def resolve_target(text, graph_):
    """A target named as a script, an artifact, or artifact:key.path.

    The third form is how a single QUANTITY is asked for: a number in the report is a
    key path inside one artifact, so naming it resolves to the one node that writes
    that file and to nothing else.
    """
    name = text.split(":", 1)[0]
    if name in graph_.nodes:
        return [graph_.nodes[name]]
    node = graph_.producer_of(name)
    if node:
        return [node]
    if name in graph_.conflicts:
        raise SystemExit(
            f"{name} is written by {graph_.conflicts[name]}. Name the producer script "
            "instead of the artifact: two scripts writing one file do not write the "
            "same file, and the build will not choose between them")
    matches = [n for n in graph_.nodes.values()
               if any(fnmatch.fnmatch(o, name) for o in n.outputs)
               or fnmatch.fnmatch(n.script, name)]
    if matches:
        return matches
    raise SystemExit(
        f"nothing in the graph writes {name!r}. `--graph` lists every artifact this "
        "build knows how to make")


def plan(targets=None, stage=None, settings_view=None, marking_overrides=None,
         graph_=None, run_unprovable=False):
    """What would run, in the order it would run, with the reason for each entry.

    THE THIRD VERDICT HAS ITS OWN SCHEDULING, and that is the whole of the policy
    here. A node that MUST RUN is scheduled. A node that is provably up to date is
    left out. A node that CANNOT BE TOLD is neither: it is returned in the plan with
    scheduled=False, printed under a heading of its own with the reason its condition
    could not be put, and not launched. Treating it as stale would walk the raw tape
    every time the build is asked what to do, which is the one thing a build exists to
    avoid; treating it as current would be the silent fold this repository already
    made twice.

    Two ways to override it, both explicit. `run_unprovable=True` schedules them all.
    And a node named DIRECTLY as a target is always scheduled, because a person who
    names a node has asked for it -- while the ancestors that target drags in behind
    it obey the default, which is the case that once started an unwanted tape download
    off a single --only.
    """
    graph_ = graph_ or graph()
    asked_for = set()
    if targets:
        wanted, seen = [], set()
        for text in targets:
            for node in resolve_target(text, graph_):
                asked_for.add(node.key)
                if node.key not in seen:
                    seen.add(node.key)
                    wanted.append(node)
        # Everything the targets read, transitively, so asking for one number brings
        # its upstream with it.
        maker = {a: n for n in graph_.nodes.values() for a in n.outputs}
        frontier = list(wanted)
        while frontier:
            node = frontier.pop()
            for name in node.inputs:
                upstream = maker.get(name)
                if upstream and upstream.key not in seen:
                    seen.add(upstream.key)
                    wanted.append(upstream)
                    frontier.append(upstream)
        candidates = wanted
    else:
        candidates = list(graph_.nodes.values())

    if stage:
        candidates = [n for n in candidates if n.stage == stage]

    ordered = _topological(candidates, graph_)
    entries, planned, stood_aside = [], set(), []
    # A node whose own conditions hold can still have to run, because a node ABOVE it
    # is going to run and rewrite what it reads. Its recorded input hash matches the
    # file on disk right now and will not a moment later, so the forward walk has to be
    # part of the plan rather than something a second pass discovers. Ordering is
    # topological, so an upstream entry is always seen before its readers.
    maker = {a: n.key for n in graph_.nodes.values() for a in n.outputs}
    for node in ordered:
        state = status(node, graph_, settings_view, marking_overrides)
        if state["verdict"] == "up_to_date":
            # Only a SCHEDULED upstream is inherited. A deferred one is not going to
            # rewrite anything, so a reader of its output is still up to date, and
            # inheriting from it would turn one unprovable node into a cascade.
            upstream = sorted({maker[name] for name in node.inputs
                               if maker.get(name) in planned})
            if not upstream:
                continue
            state = dict(state, verdict="must_run", reasons=[{
                "output": "(inherited)",
                "why": "an upstream producer is in this plan, so what this node reads "
                       "will change before it runs",
                "detail": upstream}])
        scheduled = (state["verdict"] == "must_run" or run_unprovable
                     or node.key in asked_for)
        state = dict(state, scheduled=scheduled)
        if not scheduled:
            # NOT IN `entries`, AND THAT IS THE CONTRACT RATHER THAN A HIDING PLACE.
            # Everything downstream of this function -- run/_groups.py's price(), its
            # exit code, this module's own runner -- reads `entries` as "what will
            # run". A node the build declines to decide about is not that, so it
            # travels on the graph instead, where the plan printer and the run journal
            # both read it and both name it.
            state["not_scheduled_why"] = (
                "no condition of this node could be answered, so whether it is "
                "current is unknown. It is not run, because running it would cost its "
                "full time to answer a question nothing on disk can answer; and it is "
                "not counted as current either. Name it with --only, or pass "
                "--run-unprovable, to run it anyway")
            stood_aside.append(state)
            continue
        entries.append(state)
        planned.add(node.key)
    graph_.stood_aside = stood_aside
    return entries, graph_


def what_if(field, value, graph_=None):
    """What moving ONE setting would schedule, split by stage. Nothing is written.

    This is the stage split made answerable rather than asserted. The setting is moved
    in the plan's own view of the fingerprint, never in settings.py, so the question can
    be asked of a field whose real value nobody wants to change, and asked again a
    minute later with a different field.

    The answer to print is the two counts: how many analysis nodes the move schedules,
    and how many raw-tape walks. The second number is the one the split exists to keep
    at zero for every field outside the marking.
    """
    graph_ = graph_ or graph()
    # declaration_view() and not fingerprint(), because the question is about the
    # DECLARATION and fingerprint() states no declaration the run did not confirm. The
    # three settings whose change is worth pricing at all -- rank_floor_fills, n_boot,
    # min_common_wallets -- are migrating ones, so against fingerprint() this function
    # answered "no such field" for exactly the fields it was built for.
    view = dict(S.declaration_view())
    if field not in view:
        raise SystemExit(
            f"settings.declaration_view() has no field {field!r}. It holds: "
            + ", ".join(sorted(view)))
    was = view[field]
    view[field] = value
    entries, _ = plan(settings_view=view, graph_=graph_)
    cited = [e for e in entries
             if any("setting " + field in r["why"] for r in e["reasons"])]
    return {
        "field": field, "was": was, "now": value,
        "in_the_marking": field.upper() in MARKING_SETTINGS,
        # Scheduled, not merely listed. The plan also carries the nodes it declines to
        # decide about, and counting those here would price a settings move with work
        # the move does not cause.
        "scheduled_total": sum(1 for e in entries if e.get("scheduled")),
        "scheduled_citing_this_field": len(cited),
        "tape_walks_citing_this_field": sum(1 for e in cited if e["stage"] == "tape"),
        "scripts": [e["script"] for e in cited],
        "tape_scripts": [e["script"] for e in cited if e["stage"] == "tape"],
    }


def survey(graph_=None, settings_view=None, marking_overrides=None):
    """Every node's verdict, so a plan can be read against what it left out."""
    graph_ = graph_ or graph()
    rows = [status(n, graph_, settings_view, marking_overrides)
            for n in graph_.nodes.values()]
    tally = {"up_to_date": 0, "must_run": 0, "unknown": 0}
    for row in rows:
        tally[row["verdict"]] += 1
    return rows, tally, graph_


# =====================================================================
# 8. RUNNING
# =====================================================================

def run_node(node, argv=(), timeout=None):
    """Run one producer and record what it cost. Returns the record."""
    guard = disk_guard(node.stage)
    if not guard["ok"]:
        return {"script": node.script, "argv": list(node.argv), "verdict": "REFUSED", "guard": guard,
                "why": f"{guard['free_gb']} GB free, {guard['allowance_gb']} GB "
                       "required before a raw-tape walk"}
    if node.facts.takes_argv and not argv:
        # BOTH ROUTES, NOT ONE. The test used to read argv_flags alone, which is the
        # argparse route, and ten producer nodes read sys.argv directly and were
        # launched bare -- as_quoter.py, gm_quoter.py, mm_bakeoff.py,
        # killswitch1_repeat_density.py and six of the checks. What they record when
        # run bare is the fallback arm, filed under the name of the result.
        return {"script": node.script, "argv": list(node.argv), "verdict": "NEEDS_ARGV",
                "flags": node.facts.argv_options(),
                "read_by": sorted({"argparse" if node.facts.argv_flags else None,
                                   "sys.argv" if node.facts.argv_manual else None}
                                  - {None}),
                "why": "this producer reads its command line, so running it "
                       "bare would silently pick its default arm. Pass --argv"}
    # STREAM THE NODE'S OUTPUT, DO NOT CAPTURE IT.
    #
    # This used to be subprocess.run(capture_output=True), and the first full run
    # showed what that costs. One node ran for sixty-seven minutes and the build
    # printed nothing at all, because the node's own progress lines were sitting in a
    # pipe waiting for it to exit. Which node was running had to be read off the child
    # process list, how many had finished from file modification times, and whether the
    # run was alive from two samples of accumulated CPU time taken seconds apart. Three
    # measurements standing in for the output the node was already producing.
    #
    # A long node that prints nothing is indistinguishable from a hung one, and telling
    # them apart needs operating-system tools that a reader of this repository will not
    # reach for. So the lines are echoed as they arrive, each tagged with the node, and
    # the tail is kept as well, because a failure still has to leave a record that
    # outlives the terminal.
    started = time.time()
    tail = collections.deque(maxlen=40)
    print(f"[build] START {node.key}", flush=True)
    proc = subprocess.Popen([sys.executable, os.path.join(ROOT, node.script),
                             *node.argv, *argv],
                            cwd=ROOT, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, bufsize=1)
    try:
        for line in proc.stdout:
            line = line.rstrip("\n")
            # REDACT BEFORE RECORDING, NEVER AFTER.
            #
            # The tail is written into this build's own results file, which is tracked,
            # and a failing node's tail is a traceback carrying absolute paths. Keeping
            # the line verbatim put the account name of the machine into a tracked file
            # and turned the no-absolute-paths gate red -- measured within minutes of
            # this streaming code first running. The gate is right and the recording was
            # wrong: what a reader needs from a tail is which file and which line, not
            # whose home directory it sat under.
            tail.append(HOME_PATH_RE.sub("<repo>/", line))
            print(f"  [{node.key}] {line}", flush=True)
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        raise
    elapsed = round(time.time() - started, 2)
    print(f"[build] {'OK' if proc.returncode == 0 else 'FAILED'} {node.key} "
          f"in {elapsed} s", flush=True)
    # The producer just wrote into the tree, so both caches now describe a tree that no
    # longer exists. Dropping them here rather than at the end of build() is what makes
    # a second node see the first node's output.
    forget_tree()
    return {"script": node.script, "argv": list(node.argv), "verdict": "OK" if proc.returncode == 0 else "FAILED",
            "exit": proc.returncode, "seconds": elapsed,
            # The tail is now of the merged stream, not of stderr alone. A node that
            # fails on the last line of a long print is far commoner here than one that
            # writes to stderr, and the old field showed nothing in that case.
            "output_tail": list(tail)[-6:]}


def _skip_summary(entries, rows):
    """What the skip rule left out, and what that was worth in recorded minutes.

    Stated as a LOWER BOUND whenever a skipped node records no runtime, because a node
    with no recorded cost contributes nothing to the sum and is not free. The counts
    are printed with the predicate that produced them: `up_to_date` and not in the
    plan.
    """
    # A node the plan stood aside is verdict `unknown`, so it can never satisfy the
    # predicate below and needs no exclusion of its own.
    in_plan = {e["node"] for e in entries}
    skipped = [r for r in rows
               if r["node"] not in in_plan and r["verdict"] == "up_to_date"]
    priced = [r["known_runtime_s"] for r in skipped if r["known_runtime_s"]]
    return {
        "predicate": "verdict is up_to_date and the node is not in the plan",
        "population": f"{len(rows)} producer nodes of this repository",
        "nodes_skipped": len(skipped),
        "nodes_skipped_with_a_recorded_runtime": len(priced),
        "recorded_seconds_not_spent": round(sum(priced), 1),
        "is_a_lower_bound": len(priced) < len(skipped),
        "nodes": sorted(r["node"] for r in skipped),
    }


def build(targets=None, stage=None, argv=(), out_dir=None, timeout=None,
          run_unprovable=False):
    """Plan, then run what the plan holds, one tape node at a time."""
    started = artifact.start_clock()
    entries, graph_ = plan(targets=targets, stage=stage,
                           run_unprovable=run_unprovable)
    ran, tape_running = [], 0
    for entry in entries:
        # LOOK THE NODE UP BY ITS KEY, NOT BY ITS SCRIPT.
        #
        # The nodes are keyed by script-plus-argv, because one script run under two arms
        # is two nodes. When the record's "script" field was narrowed to the bare script
        # name -- the right thing for a producer claim, which has to resolve to a file --
        # this lookup started missing every node that takes arguments, and the run died
        # with a KeyError on the first of them. The record carries both: "script" for
        # anyone resolving a producer, "node" for anyone addressing the node.
        node = graph_.nodes[entry["node"]]
        if node.stage == "tape":
            tape_running += 1
            if tape_running > MAX_CONCURRENT_TAPE_NODES:
                ran.append({"script": node.script, "argv": list(node.argv), "verdict": "DEFERRED",
                            "why": "one raw-tape walk at a time; the volume cannot "
                                   "hold two days of hourly files"})
                continue
        ran.append(run_node(node, argv=argv, timeout=timeout))
    rows, tally, _ = survey(graph_)
    payload = {
        "planned": [{"script": e["script"], "stage": e["stage"],
                     "verdict": e["verdict"], "scheduled": e.get("scheduled"),
                     "reasons": e["reasons"], "unknown": e["unknown"],
                     "unknown_causes": e.get("unknown_causes", {})}
                    for e in entries],
        # What the skip rule bought, as a number rather than as a claim: the recorded
        # cost of the nodes it left out, and how many of those record no cost at all.
        "skipped": _skip_summary(entries, rows),
        # And what it declined to decide about. A journal that recorded only what ran
        # cannot be told from the journal of a build that had nothing to do, and a
        # build that stood twelve raw-tape nodes aside has not had nothing to do.
        "stood_aside": [{"node": e["node"], "stage": e["stage"],
                         "why": e.get("not_scheduled_why", ""),
                         "causes": e.get("unknown_causes", {}),
                         "known_runtime_s": e["known_runtime_s"]}
                        for e in getattr(graph_, "stood_aside", [])],
        "ran": ran,
        "graph": graph_.counts(),
        "verdicts_after": tally,
        "cache_policy": CACHE_POLICY,
        "parsers": parser_disposal(),
        "declarations": D.counts(),
        "stale_declarations": graph_.stale_declarations(),
        "disk": disk_guard("tape"),
    }
    artifact.write(
        SELF_OUTPUT, payload, script=__file__,
        inputs=sorted({i for n in graph_.nodes.values() for i in n.inputs}),
        scope={"population": f"{len(graph_.nodes)} producer scripts of this repository",
               "window": "the tree as it stands at the moment of the run",
               "coins": "n/a: this file records a build, not a measurement"},
        settings={}, started=started, out_dir=out_dir,
        # See RECORD_KIND above. This is the whole of the build's side of the
        # freshness question: it says what kind of record this is, in the file, in a
        # field a program can read, and leaves the gate to decide what that means.
        extra_meta={"record_kind": RECORD_KIND, "record_kind_why": RECORD_KIND_WHY})
    return payload


# =====================================================================
# 9. PRINTING
# =====================================================================

def _print_graph(graph_):
    counts = graph_.counts()
    print("  THE GRAPH")
    for key, value in counts.items():
        print(f"    {key:38s} {value}")
    if graph_.conflicts:
        print("\n  ARTIFACTS WITH MORE THAN ONE PRODUCER -- the uniqueness rule bites")
        for name, scripts in sorted(graph_.conflicts.items()):
            print(f"    {name}")
            for script in scripts:
                print(f"        written by {script}")
    else:
        print("\n  every artifact has exactly one producer")
    if graph_.cycles:
        print("\n  CYCLES")
        for cycle in graph_.cycles:
            print("    " + " -> ".join(cycle))
    heavy = sorted(set((len(graph_.consumers_of(a)), a)
                        for n in graph_.nodes.values() for a in n.outputs),
                   reverse=True)
    print("\n  MOST-READ ARTIFACTS")
    for count, name in heavy[:5]:
        if count:
            print(f"    {count:3d} readers   {name}")
    if graph_.unresolved:
        total = sum(len(v) for v in graph_.unresolved.values())
        print(f"\n  WHAT DID NOT FOLD: {total} I/O calls in "
              f"{len(graph_.unresolved)} scripts build no edge")
        for script in sorted(graph_.unresolved):
            for record in graph_.unresolved[script]:
                print(f"    {script}:{record['line']} in {record['scope'] or 'module'}"
                      f"  {record['call']}  ({record['kind']})")
    else:
        print("\n  every I/O call in the tree is accounted for: an edge, a declaration "
              "in build_declarations.py, a checkpoint file, or not an artifact")
    stale = graph_.stale_declarations()
    if stale:
        print("\n  DECLARATIONS THAT MATCH NOTHING IN THE TREE -- each one is a "
              "statement about code that has moved")
        for key in stale:
            print(f"    {key}")
    if graph_.spellings:
        print("\n  ONE FAMILY SPELLED TWO WAYS -- the reader's name paired to the "
              "producer's")
        for read, family in sorted(graph_.spellings.items()):
            print(f"    {read}  read as  {family}")
    if graph_.orphans:
        print(f"\n  READ BUT MADE BY NOTHING IN THIS TREE: {len(graph_.orphans)} names."
              " Each is either fetched from outside the repository or left by a run "
              "that is no longer part of the pipeline")
        for name, readers in sorted(graph_.orphans.items()):
            print(f"    {name:34s} read by {', '.join(readers)}")
    if D.ARMS:
        print("\n  SCRIPTS HOLDING MORE THAN ONE NODE")
        for script, arms in sorted(D.ARMS.items()):
            for arm in arms:
                print(f"    {script} {' '.join(arm['argv'])}  [{arm['stage']}] "
                      f"-> {', '.join(arm['writes'])}")
    census = argv_census(graph_)
    print(f"\n  NODES THIS BUILD WILL NOT LAUNCH BARE: "
          f"{len(census['nodes_reading_the_command_line'])}. Each reads its command "
          "line, so a bare run would record the fallback arm under the name of the "
          "result")
    for label, key in (("argparse only    ", "nodes_by_argparse_only"),
                       ("sys.argv only    ", "nodes_by_sys_argv_only"),
                       ("both             ", "nodes_by_both")):
        for node_key in census[key]:
            options = graph_.nodes[node_key].facts.argv_options()
            print(f"    {label} {node_key:44s} {' '.join(options)}")
    if census["disagreement"]:
        print("\n  THE TWO ARGV PREDICATES DISAGREE about these scripts, so one of "
              "them is wrong and the census cannot be trusted until it is known which")
        for rel in census["disagreement"]:
            row = census["detail"][rel]
            print(f"    {rel}  syntax tree {row['tree_lines']}, "
                  f"source text {row['text_lines']}")


def _price(seconds):
    """A recorded runtime in the unit a reader can act on, or the honest absence."""
    if not seconds:
        return "not recorded"
    return f"{seconds / 60.0:.0f} min" if seconds >= 90 else f"{seconds:.0f} s"


def _cost_line(rows, label):
    """The summed cost of a set of nodes, and how much of the set carries no cost.

    Printed as a LOWER BOUND whenever anything is unpriced, because a node with no
    recorded runtime contributes zero to the sum and is not free. Substituting an
    invented number for an unrecorded one is the thing this line exists not to do.
    """
    known = [r["known_runtime_s"] for r in rows if r["known_runtime_s"]]
    missing = len(rows) - len(known)
    total = sum(known)
    bound = "at least " if missing else ""
    return (f"  {label}: {len(rows)} nodes, {bound}{total / 60.0:.0f} min "
            f"({len(known)} of them priced from their own artifact"
            + (f", {missing} record no runtime" if missing else "") + ")")


def _print_plan(entries, graph_, tally, rows=()):
    scheduled = list(entries)
    deferred = sorted(getattr(graph_, "stood_aside", []),
                      key=lambda r: -(r["known_runtime_s"] or 0))
    # The other half of a build's answer: the nodes the plan LEAVES OUT because every
    # condition of theirs was put and held. Taken from the survey the caller has
    # already computed rather than judged a second time, because judging a node twice
    # in one run is how two counts of one property come to disagree.
    in_plan = {e["node"] for e in entries} | {e["node"] for e in deferred}
    skipped = sorted((r for r in rows
                      if r["node"] not in in_plan and r["verdict"] == "up_to_date"),
                     key=lambda r: -(r["known_runtime_s"] or 0))

    print(f"  {tally['up_to_date']} nodes are provably up to date, "
          f"{tally['must_run']} must run, {tally['unknown']} cannot be told")
    print("  the three are kept apart on purpose: `up to date` means every condition "
          "was put and held,")
    print("  `cannot be told` means a condition could not be put at all, and neither "
          "is evidence of the other")
    print()
    print(_cost_line(scheduled, "WOULD RUN               "))
    print(_cost_line(skipped, "WOULD BE SKIPPED, proven"))
    print(_cost_line(deferred, "NOT DECIDED, not run    "))

    if scheduled:
        print("\n  WOULD RUN")
        for entry in scheduled:
            print(f"\n    {entry['script']}  [{entry['stage']}, "
                  f"{_price(entry['known_runtime_s'])} last time]")
            for reason in entry["reasons"][:3]:
                print(f"        RUN   {reason['output']}: {reason['why']}")
            for gap in entry["unknown"][:2]:
                print(f"        ?     {gap['output']}: {gap['why']}")
    else:
        print("\n  WOULD RUN: nothing. Every node whose conditions could be put has "
              "them all holding")

    if skipped:
        print(f"\n  WOULD BE SKIPPED -- every condition put, every one holding")
        for row in skipped:
            print(f"    {_price(row['known_runtime_s']):>10s} saved   "
                  f"{row['node']}  ({row['conditions_answered']} conditions answered)")

    if deferred:
        by_cause = {}
        for entry in deferred:
            for cause, count in (entry.get("unknown_causes") or {}).items():
                by_cause[cause] = by_cause.get(cause, 0) + count
        print(f"\n  NOT DECIDED, AND THEREFORE NOT RUN -- a condition could not be "
              f"put. Pass --run-unprovable,")
        print("  or name one with --only, to run it anyway")
        for cause, count in sorted(by_cause.items(), key=lambda kv: -kv[1]):
            print(f"      {count:4d} questions could not be put because: {cause}")
        for entry in deferred:
            gap = entry["unknown"][0] if entry.get("unknown") else {}
            print(f"\n    {entry['node']}  [{entry['stage']}, "
                  f"{_price(entry['known_runtime_s'])} last time]")
            print(f"        ?     {gap.get('output', '')}: "
                  f"{(gap.get('why') or '')[:96]}")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Recompute what has to be recomputed, and say why.")
    parser.add_argument("--graph", action="store_true",
                        help="print the dependency graph and stop")
    parser.add_argument("--plan", action="store_true",
                        help="print what would run, what would be skipped and what "
                             "cannot be told, with each node's recorded cost. Runs "
                             "nothing. This is what the build does with no other "
                             "flag; the option exists because a bare invocation is "
                             "taken by the self-test")
    parser.add_argument("--run-unprovable", action="store_true",
                        help="also run the nodes whose conditions could not be put. "
                             "Off by default: those nodes are neither proven current "
                             "nor proven stale, and running them costs their full "
                             "time to answer a question nothing on disk can answer")
    parser.add_argument("--only", action="append", default=[],
                        metavar="NAME",
                        help="a script, an artifact, or artifact:key.path -- the one "
                             "quantity to bring up to date, with its upstream")
    parser.add_argument("--stage", choices=("tape", "analysis"),
                        help="plan one stage only")
    parser.add_argument("--run", action="store_true",
                        help="run the plan instead of printing it")
    parser.add_argument("--argv", nargs=argparse.REMAINDER, default=[],
                        help="options passed to the producer being run")
    parser.add_argument("--out-dir", default=None,
                        help="where the build's own record goes; defaults to this "
                             "directory")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--what-if", metavar="FIELD=VALUE", default=None,
                        help="move one settings field in the plan only, and print what "
                             "that move would schedule and how much of it walks the "
                             "raw tape")
    parser.add_argument("--self-test", action="store_true",
                        help="prove the skip rule skips and the run rule runs")
    args = parser.parse_args(argv)

    if args.self_test:
        return _self_test()

    if args.what_if:
        if "=" not in args.what_if:
            raise SystemExit("--what-if takes FIELD=VALUE, for instance fdr_alpha=0.01")
        field, raw = args.what_if.split("=", 1)
        try:
            value = json.loads(raw)
        except ValueError:
            value = raw
        answer = what_if(field.strip(), value)
        if args.json:
            print(json.dumps(answer, indent=2))
            return 0
        print(f"  MOVING {answer['field']}: {answer['was']!r} -> {answer['now']!r}")
        print(f"  this field is {'IN' if answer['in_the_marking'] else 'NOT in'} the "
              "marking settings, so the tape "
              + ("may" if answer["in_the_marking"] else "must not") + " be walked")
        print(f"  nodes citing this field:  {answer['scheduled_citing_this_field']}")
        print(f"  of which raw-tape walks:  {answer['tape_walks_citing_this_field']}")
        for script in answer["scripts"]:
            print(f"      {script}")
        if answer["tape_scripts"]:
            print("  TAPE WALKS SCHEDULED BY THIS MOVE:")
            for script in answer["tape_scripts"]:
                print(f"      {script}")
        return 0

    if args.graph:
        graph_ = graph()
        if args.json:
            print(json.dumps({"counts": graph_.counts(),
                              "conflicts": graph_.conflicts,
                              "cycles": graph_.cycles}, indent=2))
        else:
            _print_graph(graph_)
        return 0

    if args.run:
        payload = build(targets=args.only or None, stage=args.stage,
                        argv=args.argv, out_dir=args.out_dir,
                        run_unprovable=args.run_unprovable)
        print(json.dumps(payload["ran"], indent=2) if args.json else "")
        if not args.json:
            for record in payload["ran"]:
                print(f"  {record['verdict']:11s} {record['script']}"
                      + (f"  {record['seconds']} s" if "seconds" in record else "")
                      + (f"  -- {record['why']}" if record.get("why") else ""))
        if not args.json and payload["stood_aside"]:
            print(f"\n  and {len(payload['stood_aside'])} nodes were STOOD ASIDE: no "
                  "condition of theirs could be answered, so they are neither run "
                  "nor counted as current.")
            print("  Pass --run-unprovable, or name one with --only, to run them")
            for record in payload["stood_aside"]:
                print(f"      {record['node']:52s} {record['causes']}")
        return 0 if all(r["verdict"] in ("OK", "DEFERRED")
                        for r in payload["ran"]) else 1

    entries, graph_ = plan(targets=args.only or None, stage=args.stage,
                           run_unprovable=args.run_unprovable)
    rows, tally, _ = survey(graph_)
    if args.json:
        print(json.dumps({"plan": entries, "verdicts": tally,
                          "skipped": _skip_summary(entries, rows),
                          "stood_aside": [e["node"] for e in graph_.stood_aside],
                          "graph": graph_.counts()}, indent=2))
    else:
        _print_plan(entries, graph_, tally, rows)
    return 0


# =====================================================================
# 10. SELF-TEST
#
# A fixture tree in a temporary directory, never the repository. The fixture is the
# only place a build can be PROVEN to skip: proving it on the real tree would need a
# full recompute, which is hours, and the real tree's artifacts mostly record nothing
# to compare against yet.
#
# Every assertion below has a non-vacuity partner. "The build skipped everything" is
# true of a build that cannot see anything, so each skip is paired with a change that
# must make the same node run, and each "no tape node was planned" is paired with a
# change that must plan one.
# =====================================================================

_FIXTURE_PRODUCER = '''\
import os, sys
sys.path.insert(0, {repo!r})
import artifact
HERE = os.path.dirname(os.path.abspath(__file__))
IN_JSON = os.path.join(HERE, "{inp}")
OUT_JSON = os.path.join(HERE, "{out}")
def main():
    t0 = artifact.start_clock()
    with open(IN_JSON) as fh:
        rows = len(fh.read())
    artifact.write(os.path.basename(OUT_JSON), {{"rows": rows}},
                   script=__file__, inputs=[IN_JSON],
                   scope={{"population": "a fixture, not market data",
                          "window": "no window", "coins": "n/a: fixture"}},
                   settings={{"h": 10, "lens": "mid"}}, started=t0,
                   out_dir=os.path.dirname(OUT_JSON))
if __name__ == "__main__":
    main()
'''

# The fixture tree, as a chain of three with a fourth off to the side:
#
#     fixture_input.json -> first -> second -> third
#     fixture_side_input.json -> side
#
# The side branch is the whole point of the shape. "Changing an input plans its
# consumers" is satisfied by a build that plans EVERYTHING, and a two-node fixture
# cannot tell the two apart. With a fourth node that reads something else, the
# assertion becomes an equality against a set that excludes it, and a build that
# over-plans fails.
_FIXTURE_TREE = (
    ("fixture_first.py", "fixture_input.json", "fixture_first_results.json"),
    ("fixture_second.py", "fixture_first_results.json", "fixture_second_results.json"),
    ("fixture_third.py", "fixture_second_results.json", "fixture_third_results.json"),
    ("fixture_side.py", "fixture_side_input.json", "fixture_side_results.json"),
)


def _self_test():
    import shutil
    import tempfile

    work = tempfile.mkdtemp(prefix="build_selftest_")
    failures = []

    def check(name, ok, detail=""):
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" -- {detail}" if detail else ""))
        if not ok:
            failures.append(name)

    global ROOT
    real_root = ROOT
    try:
        # ---- a fixture tree: a chain of three, plus one node off to the side ----
        for name in ("fixture_input.json", "fixture_side_input.json"):
            with open(os.path.join(work, name), "w") as fh:
                fh.write('{"n": 1}')
        for script, source, output in _FIXTURE_TREE:
            with open(os.path.join(work, script), "w") as fh:
                fh.write(_FIXTURE_PRODUCER.format(repo=real_root, inp=source,
                                                  out=output))
        first = os.path.join(work, "fixture_first.py")
        every = {script for script, _, _ in _FIXTURE_TREE}
        chain = {"fixture_first.py", "fixture_second.py", "fixture_third.py"}

        ROOT = work
        forget_tree()
        g = graph()
        check("the graph reads every fixture producer out of its syntax tree",
              set(g.nodes) == every, f"found {sorted(g.nodes)}")
        check("the chain is an edge: each node reads what the one above it writes",
              g.nodes["fixture_second.py"].inputs == ["fixture_first_results.json"]
              and g.nodes["fixture_third.py"].inputs == ["fixture_second_results.json"])
        check("the side node reads its own input and nothing from the chain",
              g.nodes["fixture_side.py"].inputs == ["fixture_side_input.json"])
        check("every fixture artifact has exactly one producer", not g.conflicts)

        entries, _ = plan(graph_=g)
        check("before any run, every node is planned",
              {e["script"] for e in entries} == every, f"{len(entries)} planned")

        # ---- the full run, through build() rather than by hand ---------------
        # Through build() on purpose: the claim being tested is about the build, and a
        # loop that ran the producers itself would test the producers instead.
        payload = build(out_dir=work)
        check("the full run ran every node and all of them succeeded",
              {r["script"] for r in payload["ran"]} == every
              and all(r["verdict"] == "OK" for r in payload["ran"]),
              f"{[(r['script'], r['verdict']) for r in payload['ran']]}")

        forget_tree()
        again = build(out_dir=work)
        # An empty `ran` is the whole claim: a node the build DECLINES to decide about
        # is recorded here too, as UNPROVABLE, so this line says both that nothing was
        # launched and that nothing had to be stood aside from.
        check("a SECOND FULL RUN immediately after the first runs NOTHING, and stands "
              "nothing aside as unprovable either",
              again["ran"] == [],
              f"{[(r['script'], r['verdict']) for r in again['ran']]}")
        check("and the build's own record prices what the skip bought",
              again["skipped"]["nodes_skipped"] == len(every)
              and again["skipped"]["predicate"],
              f"{again['skipped']['nodes_skipped']} nodes skipped by the predicate "
              f"{again['skipped']['predicate']!r}")

        # Non-vacuity for the line above: the same call must plan the node again as
        # soon as one input byte moves. A build that skips everything unconditionally
        # would pass the assertion above and fail this one.
        with open(os.path.join(work, "fixture_input.json"), "w") as fh:
            fh.write('{"n": 2}')
        forget_tree()
        entries, _ = plan()
        planned = {e["script"] for e in entries}
        check("changing one input plans EXACTLY its consumers and their consumers",
              planned == chain, f"planned {sorted(planned)}")
        check("and the node that reads something else is NOT planned",
              "fixture_side.py" not in planned)
        check("the head of the chain cites the input, not a date",
              any(r["why"] == "an input has changed"
                  for e in entries if e["script"] == "fixture_first.py"
                  for r in e["reasons"]))
        check("the nodes below it cite the upstream that is about to rewrite them",
              all(any("upstream producer is in this plan" in r["why"]
                      for r in e["reasons"])
                  for e in entries if e["script"] != "fixture_first.py"))

        # Non-vacuity for the script-hash condition: rerun to green, then edit the
        # producer only.
        build(out_dir=work)
        forget_tree()
        check("back to nothing to do after the rerun", plan()[0] == [])
        with open(first, "a") as fh:
            fh.write("\n# one comment, which changes the script's bytes\n")
        forget_tree()
        entries, _ = plan()
        check("editing a producer plans that producer",
              "fixture_first.py" in {e["script"] for e in entries},
              "the recorded producer hash no longer matches the file")

        # ---- asking for ONE quantity -----------------------------------------
        build(out_dir=work)
        with open(os.path.join(work, "fixture_input.json"), "w") as fh:
            fh.write('{"n": 3}')
        forget_tree()
        one, _ = plan(targets=["fixture_first_results.json:rows"])
        check("naming one quantity plans its producer and its upstream, not the tree",
              {e["script"] for e in one} == {"fixture_first.py"},
              f"planned {sorted(e['script'] for e in one)}")

        # ---- THE THIRD ANSWER, AND THAT IT IS NEITHER OF THE OTHER TWO --------
        #
        # Every assertion above is about a node the build can DECIDE. The case this
        # block is for is the one the real tree is full of and the fixture had none
        # of: a node whose condition cannot be put at all. Two folds are possible and
        # both are wrong, so both are asserted against: it must not read up_to_date,
        # which would be the tree reading as verified when nothing was checked, and it
        # must not be launched, which would pay a node's full runtime to answer a
        # question nothing on disk can answer. What it must do is say so and stand
        # aside, and then run on either of the two explicit overrides.
        build(out_dir=work)
        forget_tree()
        check("everything is provable and current again before the third answer is "
              "tested", plan()[0] == [])
        side_input = os.path.join(work, "fixture_side_input.json")
        with open(side_input, encoding="utf-8") as fh:
            side_bytes = fh.read()
        os.remove(side_input)
        forget_tree()
        entries, planned_graph = plan()
        aside = planned_graph.stood_aside
        side = [e for e in aside if e["script"] == "fixture_side.py"]
        check("a node whose recorded input is GONE reads unknown, not up_to_date",
              len(side) == 1 and side[0]["verdict"] == "unknown",
              f"stood aside {[(e['script'], e['verdict']) for e in aside]}")
        check("and the record names the input and why it could not be compared",
              bool(side) and side[0]["unknown"]
              and side[0]["unknown"][0]["cause"] == K.INPUT_ABSENT,
              f"{side[0]['unknown'][0]['why'][:60] if side and side[0]['unknown'] else ''}")
        check("and it is NOT in the plan, so the build does not pay a node's runtime "
              "to answer a question nothing on disk can answer",
              entries == [], f"{[e['script'] for e in entries]}")
        check("and nothing else is dragged in: an unprovable node is not a cascade",
              {e["script"] for e in aside} == {"fixture_side.py"},
              f"{sorted(e['script'] for e in aside)}")
        # The two opposite cases for the refusal. Without these, "it is not scheduled"
        # is satisfied by a planner that schedules nothing at all.
        forced, _ = plan(run_unprovable=True)
        check("--run-unprovable DOES schedule it, which is the opposite case",
              {e["script"] for e in forced} == {"fixture_side.py"},
              f"{[e['script'] for e in forced]}")
        named, _ = plan(targets=["fixture_side.py"])
        check("and naming it directly schedules it too, because a person who names a "
              "node has asked for it",
              {e["script"] for e in named} == {"fixture_side.py"},
              f"{[e['script'] for e in named]}")
        with open(side_input, "w", encoding="utf-8") as fh:
            fh.write(side_bytes)
        forget_tree()
        check("and putting the input back makes the node provable and current again, "
              "with no run in between", plan()[0] == [])

        # The other way a condition cannot be put, and the live tree holds no example
        # of it: an artifact recording an EMPTY input list for a node the graph
        # derives an input for. Five real gates record an empty list legitimately --
        # they walk the repository and state it in scope -- so the rule may not fire
        # on emptiness alone, and the only way to exercise the firing side is here.
        second_results = os.path.join(work, "fixture_second_results.json")
        with open(second_results, encoding="utf-8") as fh:
            document = json.load(fh)
        kept_inputs = document[artifact.META_KEY]["inputs"]
        check("the fixture's middle node really does record an input, so emptying it "
              "below is a change", bool(kept_inputs), f"{kept_inputs}")
        document[artifact.META_KEY]["inputs"] = []
        with open(second_results, "w", encoding="utf-8") as fh:
            json.dump(document, fh)
        forget_tree()
        entries, planned_graph = plan()
        middle = [e for e in planned_graph.stood_aside
                  if e["script"] == "fixture_second.py"]
        check("an artifact recording NO inputs for a node the graph says reads one is "
              "unknown", len(middle) == 1 and middle[0]["verdict"] == "unknown",
              f"stood aside {[e['script'] for e in planned_graph.stood_aside]}, "
              f"planned {[e['script'] for e in entries]}")
        document[artifact.META_KEY]["inputs"] = kept_inputs
        with open(second_results, "w", encoding="utf-8") as fh:
            json.dump(document, fh)
        forget_tree()
        check("and restoring the input list makes it provable again, so the rule "
              "reads the list and not the file",
              not [e for e in plan()[0] if e["script"] == "fixture_second.py"])

        # ---- the stage split, in both directions ------------------------------
        ROOT = real_root
        forget_tree()
        real = graph()
        tape_nodes = [n for n in real.nodes.values() if n.stage == "tape"]
        check("the real tree has tape nodes at all, so the next two tests are not empty",
              bool(tape_nodes), f"{len(tape_nodes)} of {len(real.nodes)} nodes")

        # An analysis-only setting is moved and the tape must not stir. The move is
        # injected rather than edited into settings.py, so nothing on disk changes.
        moved = dict(S.declaration_view())
        moved["fdr_alpha"] = float(moved.get("fdr_alpha") or 0.05) / 2.0
        entries, _ = plan(settings_view=moved, graph_=real)
        stirred = [e for e in entries if e["stage"] == "tape"
                   and any("setting" in r["why"] for r in e["reasons"])]
        check("moving an analysis-only setting walks no tape",
              not stirred, f"{len(stirred)} tape nodes cited a setting")
        # Non-vacuity: the same injected change must reach the analysis stage, or the
        # line above only says that nothing reads settings at all.
        touched = [e for e in entries if e["stage"] == "analysis"
                   and any("setting" in r["why"] for r in e["reasons"])]
        check("and the same change DOES reach the analysis stage",
              bool(touched), f"{len(touched)} analysis nodes cited the moved setting")

        # A marking change must reach the tape. A rung with no column anywhere is
        # added to the ladder; every marking file is then short of a column.
        ladder = tuple(sorted(set(S.LADDER_S) | {5}))
        short = [n for n in tape_nodes
                 if status(n, real, marking_overrides={"LADDER_S": ladder})["reasons"]]
        check("adding a rung to the ladder DOES plan a tape walk",
              bool(short), f"{len(short)} tape nodes short of a column")

        # ---- the graph is declared whole --------------------------------------
        counts = real.counts()
        check("every artifact has exactly one producer",
              not real.conflicts, f"{real.conflicts}")
        check("the graph has no cycles", not real.cycles, f"{real.cycles}")
        check("every I/O call is accounted for, and the residue is at or under its "
              "declared ceiling",
              counts["unresolved_io_calls"] <= UNRESOLVED_IO_CEILING,
              f"{counts['unresolved_io_calls']} unresolved against a ceiling of "
              f"{UNRESOLVED_IO_CEILING}; {counts['io_declared_by_hand']} declared, "
              f"{counts['io_folded_but_not_an_artifact']} folded to something that is "
              f"not an artifact, {counts['io_into_a_checkpoint_dir']} into a "
              "checkpoint directory")
        stale = real.stale_declarations()
        check("no declaration names code that is no longer there", not stale,
              f"{stale}")

        # ---- the lookup the three lines below stand on ------------------------
        # node_named answers None both when nothing matches and when several do, and a
        # None reads downstream exactly like a node that reads no artifacts -- which is
        # what the two lines below reported for a fortnight after the move. So the
        # lookup is calibrated before it is relied on, on two opposite cases taken from
        # the live tree: a script that sits in a subdirectory must be found by its bare
        # name, and a script declared in arms must NOT be, because answering with one of
        # its halves would settle a question about the whole script with half a fact.
        found_by_name = real.node_named("m11_concentration.py")
        split_script = sorted({n.script for n in real.nodes.values()
                               if sum(1 for m in real.nodes.values()
                                      if m.script == n.script) > 1})
        check("a script is found by its bare name from wherever it sits",
              found_by_name is not None and os.path.dirname(found_by_name.script),
              f"m11_concentration.py -> "
              f"{found_by_name.script if found_by_name else None}")
        check("and a script standing for several nodes is NOT resolved to one of them, "
              "so the lookup above is not answering whatever it met first",
              bool(split_script)
              and all(real.node_named(rel) is None for rel in split_script),
              f"{len(split_script)} scripts declare arms: {split_script}")

        # ---- a name means what the function around it bound -------------------
        # Both directions, on live files, because one reference point cannot tell a
        # rule that is too narrow from one that is too wide. The first pair asks
        # whether one name in two functions gives two answers; the second asks whether
        # the module constant every read in this tree is written as still reaches
        # inside a function, which is what a scope rule drawn too tight would break.
        # Asked of node_named rather than of the nodes dict, and that is not a tidying:
        # the dict is keyed on the script's PLACE, so every line below was an assertion
        # about the directory layout as much as about the reading rule it means to test.
        leadlag = real.node_named("probe_E_leadlag.py")
        two_ways = set(leadlag.inputs) if leadlag else set()
        check("one name bound in two functions folds to two files, not twice to one",
              {"mid_series_*.npz", "hl_print_series_*.npz"} <= two_ways,
              f"probe_E_leadlag binds p in load_hl_mid and in load_hl_print; "
              f"inputs {sorted(two_ways)}")
        constant_read = real.node_named("m11_concentration.py")
        check("and a module-level constant still folds inside a function, which is how "
              "nearly every read in this tree is written",
              "quickwin_markouts.npz" in set(constant_read.inputs if constant_read
                                             else ()),
              f"m11_concentration.py reads {sorted(constant_read.inputs) if constant_read else []}")

        # ---- a self-test's fixture is not the pipeline's input ----------------
        # prose_assemble writes display.json into a temporary directory and hands it to
        # load_overlay. Bound at that call site, the fixture became a real input, and
        # the same name reaching the write side made the script a cycle with itself.
        assembler = real.node_named("prose_assemble.py")
        touched = set(assembler.inputs) | set(assembler.outputs) if assembler else set()
        check("a file a self-test hands to a production function is not an edge",
              "display.json" not in touched, f"prose_assemble.py touches {sorted(touched)}")
        check("and it still writes the sidecar it really writes, so the line above is "
              "not the node having been emptied",
              "*.provenance.json" in (set(assembler.outputs) if assembler else ()),
              f"outputs {sorted(assembler.outputs) if assembler else []}")
        # The opposite case for the same machinery: a call site OUTSIDE a self-test
        # must still bind, or the rule above would have cost the graph 24 real reads.
        rollup = real.node_named("sensitivity_rollup.py")
        check("and a call site outside a self-test still binds its argument",
              "mm_bakeoff_results.json" in (set(rollup.inputs) if rollup else ()),
              f"sensitivity_rollup.py reads {len(rollup.inputs) if rollup else 0} "
              "artifacts, none of them named at its own read")

        # Non-vacuity for the pairing: it must pair the family it was written for, and
        # it must leave the genuinely external names alone. A pairing rule that paired
        # everything would empty the orphan list and hide the files this repository
        # really does fetch from outside itself.
        check("a family spelled two ways is read as one node",
              real.spellings.get("mid_series_*_*.npz") == "mid_series_*.npz",
              f"{real.spellings}")
        check("and a name nothing in the tree writes stays an orphan",
              any(a.endswith(".parquet") for a in real.orphans),
              f"{sorted(real.orphans)}")

        # A script with declared arms must land as several nodes, and the arms must
        # hold together in one of exactly two shapes. Without that second half the
        # split would be a way of hiding a cycle rather than resolving one.
        #
        #   a CHAIN     the later arm reads what the earlier one wrote. Two stages of
        #               one computation, and the write strictly precedes the read.
        #   PARALLEL    the arms share nothing: disjoint outputs and neither reading
        #               the other's. One computation run against two references.
        #
        # Parallel is declared per arm and then CHECKED, not taken on the word of the
        # declaration. A pair marked parallel whose arms did overlap would be a cycle
        # wearing a label, which is worse than the unsplit node it replaced.
        for script, arms in sorted(D.ARMS.items()):
            keys = [n.key for n in real.nodes.values() if n.script == script]
            check(f"{script} is {len(arms)} nodes, not one", len(keys) == len(arms),
                  f"{keys}")
            written = {a for arm in arms for a in arm["writes"]}
            read = {a for arm in arms for a in arm["reads"]}
            declared_parallel = all(arm.get("parallel") for arm in arms)
            if declared_parallel:
                overlap = written & read
                outputs = [set(arm["writes"]) for arm in arms]
                shared_output = any(outputs[i] & outputs[j]
                                    for i in range(len(outputs))
                                    for j in range(i + 1, len(outputs)))
                check(f"and its arms are parallel as declared: no arm reads what "
                      f"another writes, and no two write the same artifact",
                      not overlap and not shared_output,
                      f"written {sorted(written)}, read {sorted(read)}, "
                      f"overlap {sorted(overlap)}, shared output {shared_output}")
            else:
                check(f"and its arms chain: the later arm reads what the earlier one "
                      f"wrote",
                      bool(written & read) or len(arms) < 2,
                      f"written {sorted(written)}, read {sorted(read)}")
        # Non-vacuity for the branch above: both shapes must be present in the tree,
        # or one of the two legs has never been exercised and could be anything.
        shapes = {"parallel" if all(a.get("parallel") for a in arms) else "chain"
                  for arms in D.ARMS.values()}
        check("both arm shapes are exercised, so neither leg of the test above is "
              "dead code", shapes == {"chain", "parallel"}, f"{sorted(shapes)}")

        # ---- an import that is not an import statement -------------------------
        # The stage predicate is transitive over local imports, so a module loaded by
        # path has to count as one. Asserted over the tree rather than over one name:
        # what must hold is that every script loading a NAMED PARSER this way reads as a
        # tape walker. The membership half used to be asked of the live tree, and it was
        # answered by the one file that loaded a module by path, and that file is not
        # published in this repository, so the live census is empty and
        # the question is put to a written source instead, the same repair this block
        # made on 12 August for the parser case below. How many live files load a module
        # by path is printed, because it is a state of the tree and not a property the
        # build may demand of it.
        by_path = {rel: sorted(f.dynamic_imports) for rel, f in real.scanned.items()
                   if f.dynamic_imports}
        by_path_probe = scan("woven_by_path.py",
                             source="import importlib.util\n"
                                    "spec = importlib.util.spec_from_file_location(\n"
                                    "    'mod', 'some_module.py')\n")
        plain_probe = scan("woven_plain_import.py", source="import some_module\n")
        check("a module loaded by path is read as an import, and an ordinary import "
              "is not read as one",
              bool(by_path_probe.dynamic_imports) and not plain_probe.dynamic_imports,
              f"by path reads {sorted(by_path_probe.dynamic_imports)}, ordinary import "
              f"reads {sorted(plain_probe.dynamic_imports)}; "
              f"live tree: {len(by_path)} file(s) {by_path or ''}")
        parser_modules = {os.path.splitext(os.path.basename(p))[0]
                          for p in TAPE_PARSERS}
        loads_a_parser = sorted(rel for rel, f in real.scanned.items()
                                if f.dynamic_imports & parser_modules)
        not_tape = [rel for rel in loads_a_parser
                    if not real.scanned[rel].fetches_tape]
        # THE TWO OPPOSITE CASES, WRITTEN IN RATHER THAN NAMED. Until 12 August 2026 this
        # line also demanded `bool(loads_a_parser)` over the live tree, and one script
        # answered it: checks/chk_rowcounts_determinism.py built a spec from the parser's
        # file name and executed it. That day the file was given an ordinary import --
        # the repair this rule asks for -- and the assertion began to fail for the one
        # reason that must never fail a gate: the defect it was calibrated on had been
        # fixed. No dynamic import is left in the tree, so no live node can play
        # either case.
        #
        # The pair below differs along ONE axis, whether the file walks the tape itself,
        # and both halves of the live predicate are asked of it: the membership half,
        # which must see a parser loaded by path in both, and the violation half, which
        # must fire on the one that is not a tape walker and stay silent on the one that
        # is. Both go through scan(), the same reader the census above goes through; the
        # census then hands its facts to _apply_declarations, which touches neither of
        # the two fields read here. The parser is named out of TAPE_PARSERS rather than
        # spelled again, so a fixture cannot go on testing a name the tree has dropped.
        woven_parser = os.path.basename(TAPE_PARSERS[0])
        by_path_fixture = ("import importlib.util\n"
                           "def load():\n"
                           "    spec = importlib.util.spec_from_file_location(\n"
                           f"        'parser', {woven_parser!r})\n"
                           "    return spec\n")
        walks_tape = ("import subprocess\n" + by_path_fixture +
                      "def fetch(day):\n"
                      "    subprocess.run(['aws', 's3', 'cp',\n"
                      "                    's3://a-bucket/' + day, '.'])\n")
        reads_parsed = ("import json\n" + by_path_fixture +
                        "def read(day):\n"
                        "    with open(day + '.json') as fh:\n"
                        "        return json.load(fh)\n")
        woven = {name: scan(f"woven_{name}.py", source=src)
                 for name, src in (("tape", walks_tape),
                                   ("analysis", reads_parsed))}
        woven_loads = {name: sorted(f.dynamic_imports & parser_modules)
                       for name, f in woven.items()}
        woven_not_tape = sorted(name for name, f in woven.items()
                                if not f.fetches_tape)
        check("a written source that loads a raw-tape parser by path is read as loading "
              "it, whether or not it walks the tape itself",
              all(woven_loads.values()), f"{woven_loads}")
        check("and the same predicate tells that pair apart: the one that walks the tape "
              "reads as a tape walker and the one that only reads a parsed day does not, "
              "so an empty live census below is a fact about the tree and not a mute "
              "predicate", woven_not_tape == ["analysis"],
              f"read as NOT tape: {woven_not_tape}, expected ['analysis']")
        # And the live tree, read for the same two shapes. Asserted as the violation only:
        # that no script loads a parser this way without reading as a tape walker. How
        # many load one at all is printed, because that is a state of the tree today
        # rather than a property the build may demand of it.
        check("and no script of this tree loads a raw-tape parser that way without "
              "reading as a tape walker", not not_tape,
              f"{len(loads_a_parser)} such loader(s) {loads_a_parser}; "
              f"{not_tape or 'none'} did not read as tape")
        mislabelled = [rel for rel in loads_a_parser
                       if rel in real.nodes and real.nodes[rel].stage != "tape"]
        check("and the node it makes carries the tape stage, which is what the "
              "planner reads", not mislabelled, f"{mislabelled}")

        # ---- a write performed through another module --------------------------
        redirected = {rel: f.redirected_writes for rel, f in real.scanned.items()
                      if f.redirected_writes}
        check("a write redirected through another module's output name is an edge",
              bool(redirected),
              "; ".join(f"{rel} sets {row['module']}.{row['attr']} to {row['name']}"
                        for rel, rows in sorted(redirected.items()) for row in rows))
        named = sorted({row["name"] for rows in redirected.values() for row in rows})
        check("and every artifact those writes name has a producer",
              all(real.producer_of(n) for n in named),
              f"{[(n, bool(real.producer_of(n))) for n in named]}")
        # Non-vacuity for the pair above: the names must stand for files that are
        # actually in the tree. A redirect resolved to a pattern nothing matches would
        # satisfy both lines and still leave the artifacts without a producer, which is
        # the state this rule was written to end.
        on_disk = {n: len(locate_all(n)) for n in named}
        check("and the files they stand for are in the tree",
              all(on_disk.values()), f"{on_disk}")

        # ---- a stage refused to an importer ------------------------------------
        # A module whose declared arms are different stages hands neither one to a
        # script that imports it. Both halves are asserted: such a module exists, so the
        # refusal is reachable, and no importer took the stage from a module it refused.
        mixed = sorted(rel for rel in D.ARMS if _mixed_stage_arms(rel))
        refusals = {rel: f.tape_not_inherited for rel, f in real.scanned.items()
                    if f.tape_not_inherited}
        check("a script whose arms are unlike stages exists, so the refusal below is "
              "not dead code", bool(mixed), f"{mixed}")
        took_it_anyway = [rel for rel, rows in refusals.items()
                          if real.scanned[rel].tape_via in {r["module"] for r in rows}]
        check("and no importer took the tape stage from a module that refused it",
              bool(refusals) and not took_it_anyway,
              f"{len(refusals)} refusals {sorted(refusals)}; took it anyway "
              f"{took_it_anyway or 'none'}")
        stayed_analysis = sorted(rel for rel in refusals
                                 if not real.scanned[rel].fetches_tape)
        check("and at least one node is an analysis node because of that refusal",
              bool(stayed_analysis), f"{stayed_analysis}")

        # ---- the command line, counted twice ----------------------------------
        # The build declines to launch a producer that reads its command line. That
        # list therefore decides which artifacts a run can refresh and which a person
        # must launch by hand, and a list that quietly loses a member does not fail --
        # it runs the producer bare and files the fallback arm under the name of the
        # result. So the census is taken by two predicates that look differently, the
        # syntax tree by expression and the source text by line, and the sets of
        # scripts must match. The difference is printed in both directions, because a
        # count says only that something is wrong and the names say which script.
        census = argv_census(real)
        only_tree = sorted(set(census["manual_by_syntax_tree"])
                           - set(census["manual_by_source_text"]))
        only_text = sorted(set(census["manual_by_source_text"])
                           - set(census["manual_by_syntax_tree"]))
        check("the two argv predicates name the same scripts",
              not census["disagreement"],
              f"{len(census['manual_by_syntax_tree'])} scripts by syntax tree, "
              f"{len(census['manual_by_source_text'])} by source text; seen only by "
              f"the tree {only_tree}, only by the text {only_text}")
        # Non-vacuity. Two predicates that both return nothing agree perfectly and
        # prove nothing, and that is exactly the state the build was in before the
        # second route was read: argparse answered, sys.argv was silent, and the
        # agreement of one predicate with itself was mistaken for a complete census.
        check("and the census is not empty, so the agreement above says something",
              bool(census["nodes_by_sys_argv_only"]),
              f"{len(census['nodes_by_sys_argv_only'])} producer nodes read the "
              f"command line ONLY through sys.argv: "
              f"{census['nodes_by_sys_argv_only']}")
        # And the refusal must actually act on the second route. A census the runner
        # never consults would leave the producers being launched exactly as before.
        # An analysis node is chosen, because the free-space guard answers before this
        # test does on a tape node, and a REFUSED verdict would then read as a pass of
        # a rule that had not been reached.
        by_hand = sorted((n for n in real.nodes.values()
                          if n.facts.argv_manual and not n.facts.argv_flags
                          and n.stage == "analysis"), key=lambda n: n.key)
        refused = [run_node(n)["verdict"] for n in by_hand[:1]]
        check("a producer that reads sys.argv and never calls argparse is refused a "
              "bare run", refused == ["NEEDS_ARGV"],
              f"{by_hand[0].key if by_hand else 'none'} -> {refused}")

        # ---- the disk rule is in the build ------------------------------------
        guard = disk_guard("tape")
        check("a tape node is gated on measured free space",
              set(guard) >= {"free_gb", "allowance_gb", "ok"},
              f"{guard['free_gb']} GB free against a {guard['allowance_gb']} GB "
              "allowance")
        check("no raw day is a node of this graph",
              not any(".lz4" in a or "hourly" in a
                      for n in real.nodes.values() for a in n.outputs))
        # WHAT THESE ASK, AND WHY THEY NO LONGER ASK IT OF THEMSELVES. Two checks stood
        # here until 2026-08-03 and both tested a substring of the very string they were
        # checking -- "raw tape" in CACHE_POLICY["never_cached"], and "decision rather
        # than a gap" in CACHE_POLICY["no_local_raw_cache"]. Neither could fail except
        # by an edit to itself, so neither said anything about the code; and the second
        # was certifying a decision the user had reversed on 31 July, which a check that
        # reads the tree could not have done. What follows asks the same question of the
        # parsers' syntax trees instead.
        disposal = parser_disposal()
        absent = [r["parser"] for r in disposal if not r["present"]]
        keeps = [r["parser"] for r in disposal if r["present"] and not r["disposes"]]
        check("every parser named in the cache rule is in the tree", not absent,
              f"missing {absent}; the seven resolve to "
              f"{[r['script'] for r in disposal]}")
        check("and every one of them disposes of the day it fetched, by default or "
              "outright", not keeps,
              "; ".join(f"{r['script']} {r['disposal']} via {r['via']}"
                        + (f" through {r['through']}" if r["through"] else "")
                        for r in disposal if r["disposes"]) or f"kept by {keeps}")

        # The key the build declares must be the key the deletions actually stand under.
        # This is the join that keeps the policy text above honest: the text is built
        # from these two constants, and the constants are compared here against what the
        # parsers do, so a key renamed in one place cannot go unnoticed in the other.
        gate_keys = sorted({k for r in disposal for k in r["gated_on"]})
        check("the key the build declares is the key the deletions stand under",
              gate_keys == [RAW_CACHE_KEEP_KEY],
              f"gates read {gate_keys}, the build declares {RAW_CACHE_KEEP_KEY!r}; "
              f"one tape node at a time is a stated allowance and stands at "
              f"{MAX_CONCURRENT_TAPE_NODES}")
        dir_readers = sorted(r["script"] for r in disposal
                             if RAW_CACHE_DIR_KEY in r["reads_settings"])
        check("and the key that says WHERE a kept day lives is read by the tree too, "
              "so it is not a name only the policy knows",
              bool(dir_readers), f"{RAW_CACHE_DIR_KEY} read by {dir_readers}")

        # THE TWO OPPOSITE CASES, both from the live tree. The parsers that walk the ten
        # shared days delete by DEFAULT, under the declared key; three other named
        # parsers delete outright. A predicate that answered "by setting" for all six
        # would be too wide, and the one that stood here until 2026-08-03 -- any removal
        # call anywhere in the file -- answered "deletes" for all six and was too narrow
        # to see the difference at all. One reference point cannot tell those apart.
        # Collected by the DECLARED NAME, not by the path the row resolved to, and the
        # two literals below are basenames for the same reason. This line failed from
        # 2026-08-11 to 2026-08-14 over a tree in which both parsers were present and
        # both were gated: the move put them in subdirectories, the census could not
        # find them, and rows it could not find carry no disposal to be collected. Now
        # that the census resolves a name to a path, the row knows both, and this line
        # must go on reading the NAME -- comparing against the path would put the
        # directory layout back inside an assertion that is not about the layout.
        by_setting = sorted(r["parser"] for r in disposal
                            if r["disposal"] == "by_setting")
        outright = sorted(r["parser"] for r in disposal
                          if r["disposal"] == "unconditional")
        check("the parsers that walk the shared days delete by DEFAULT, under a key the "
              "run can turn off",
              {"build_quickwin_markouts.py", "ks2_persistence_10day.py"}
              <= set(by_setting), f"by setting: {by_setting}")
        # THE NEGATIVE HALF, INJECTED RATHER THAN NAMED. Until 2026-08-04 this line
        # required panel_rebuild_v2.py and checks/chk_liquidation_field.py to read as
        # ungated, and on that day both were put under the declared key -- which is the
        # repair the disposal policy asks for. The assertion then began to fail for the
        # one reason that must never fail a gate: the defect it was calibrated on had
        # been fixed, so `outright` over the live tree is now empty and no live node can
        # play the negative case. The pair below is written here and put through
        # disposal_calls and disposal_shape, the same two functions the census above
        # goes through, so the predicate keeps being shown to tell the shapes apart
        # after the tree stops offering it a counter-example.
        ungated_fixture = (
            "import shutil\n"
            "def teardown(day_dir):\n"
            "    shutil.rmtree(day_dir)\n")
        gated_fixture = (
            "import os\n"
            "import shutil\n"
            "def keep_raw_days():\n"
            f"    return bool(os.environ.get({RAW_CACHE_KEEP_KEY!r}))\n"
            "def teardown(day_dir):\n"
            "    if keep_raw_days():\n"
            "        print('kept')\n"
            "    else:\n"
            "        shutil.rmtree(day_dir)\n")
        shapes = {name: disposal_shape(disposal_calls(src))
                  for name, src in (("ungated", ungated_fixture),
                                    ("gated", gated_fixture))}
        check("and the same predicate, put through two written sources that differ in "
              "the gate alone, tells them apart -- so the shapes above are a reading "
              "and not a restatement of what the tree happens to hold",
              shapes == {"ungated": "unconditional", "gated": "by_setting"},
              f"fixtures {shapes}, expected "
              "{'ungated': 'unconditional', 'gated': 'by_setting'}")
        # And what the live tree holds today, printed rather than asserted: after the
        # repair above there is no ungated parser left, and that is a state of the tree
        # rather than a property the build may demand of it.
        check("and the live tree is read for the same two shapes, so the census is not "
              "vacuous", bool(by_setting) or bool(outright),
              f"by setting {len(by_setting)}, outright {len(outright)}: {outright}")
        # A file may hold several removal calls, and the gated one must not be outvoted
        # by the ungated ones beside it. build_quickwin_markouts.py holds four: three
        # clear a failed download, and the fourth is the day teardown. The predicate
        # that picked whichever the walk reached first was reading one of the three.
        crowded = [r for r in disposal if not r["through"] and len(r["calls"]) > 1]
        check("and a file holding several removal calls is judged by all of them, not "
              "by whichever the walk reached first",
              bool(crowded) and all(r["disposal"] == "by_setting" for r in crowded),
              "; ".join(f"{r['script']}: {len(r['calls'])} calls, "
                        f"{sum(1 for c in r['calls'] if c['gated_on'])} gated"
                        for r in crowded) or "no parser holds more than one")
        # And the gate travels along an import, which is the one route that produced a
        # false alarm before: panel_build.py holds no removal call of its own.
        relayed = [r for r in disposal if r["through"]]
        check("and a parser that disposes through the one it imports inherits its gate",
              bool(relayed) and all(r["disposal"] == "by_setting" for r in relayed),
              "; ".join(f"{r['script']} through {r['through']} -> {r['disposal']}"
                        for r in relayed) or "no parser disposes through another")

        # ---- the stage split, answered rather than asserted --------------------
        # what_if is the same instrument the command line prints, so the number in the
        # assertion and the number a reader sees are produced by one code path.
        answer = what_if("fdr_alpha",
                         float(S.declaration_view().get("fdr_alpha") or 0.05) / 2,
                         graph_=real)
        check("moving the false-discovery rate schedules NO raw-tape walk",
              answer["tape_walks_citing_this_field"] == 0,
              f"{answer['scheduled_citing_this_field']} nodes cited it, "
              f"{answer['tape_walks_citing_this_field']} of them tape")
        check("and that same move is not vacuous: it does schedule analysis work",
              answer["scheduled_citing_this_field"] > 0,
              f"{answer['scripts']}")
    finally:
        ROOT = real_root
        shutil.rmtree(work, ignore_errors=True)

    print("-" * 76)
    print(f"  VERDICT: {'PASS' if not failures else 'FAIL ' + ', '.join(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    if len(sys.argv) == 1:
        print("=" * 76)
        print("  build.py self-test -- the skip rule skips, and the run rule runs")
        print("=" * 76)
        sys.exit(_self_test())
    sys.exit(main())
