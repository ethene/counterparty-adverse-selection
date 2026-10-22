#!/usr/bin/env python3
"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-08-06
References: notebooks/notebook_expected.json (the home of the reported figures);
embed_notebook_expectations.py (the producer of the cell this gate reads);
notebooks/counterparty_adverse_selection.ipynb (the consumer).

THE FIGURES INSIDE THE NOTEBOOK ARE THE FIGURES IN THEIR HOME.

Why this gate exists, and it was measured rather than imagined. The reproduction
notebook re-derives a set of figures and compares each one against the figure the
report publishes. Until 2026-08-06 it read those published figures from a file it
DOWNLOADED at run time from the public archive, Zenodo record 21820077. The copy
published there was written on 10 July and is 3,713 bytes; the copy in this
repository is 8,927 bytes, and every figure in the older one belongs to a scoring
window that has since been retired. A reader who followed the README got 4 of 25
checks passing and a notebook that then stopped.

The mechanism is worth naming, because it is not carelessness. The figure and the
notebook that verifies it were of different ages because they lived in different
files, and one of those files lived on a remote host that no gate here could see.
Nothing in this tree was wrong; the tree simply had no reach over the copy the
notebook actually read.

The repair moves the figures INSIDE the notebook, as one generated cell written by
embed_notebook_expectations.py out of notebooks/notebook_expected.json. That closes
the distance, and it opens one hole: a generated cell is still a cell, and a hand can
edit it. Then the notebook disagrees with its own home again, and this time silently,
because the two copies now sit in the same clone and no download is left to blame.
This gate is the thing that notices.

THREE QUESTIONS, and each one prints an expectation, a fact and a place when it goes
over.

  RULE 1  The generated cell is there, and there is exactly one of it. Zero cells is
          a failure, not a quiet pass: a gate that says nothing when the thing it
          guards is absent measures its own reach and not the tree. Two cells is a
          failure for the same reason a fact with two homes is one, since the reader
          of the notebook cannot tell which one the run used.

  RULE 2  The literal in that cell agrees with notebooks/notebook_expected.json, leaf
          by leaf. The walk descends into nested mappings and lists and reports the
          key path, the value in the notebook and the value in the home. Floating
          point is compared for exact equality on purpose: the cell is a COPY of the
          home and not a re-derivation of it, so a tolerance here would forgive
          exactly the drift the gate is for. This rule also refuses to return zero
          when it had nothing to compare, because a zero taken over an empty
          population reads on screen like agreement.

  RULE 3  No cell fetches the file of figures any more. The question is whether the
          file's name is PASSED INTO a call that reaches the network, which is not the
          same question as whether the name stands near such a call in the text. The
          first version of this rule asked the second one and reported the notebook's
          own comment explaining that the fetch had been taken out: the cell still
          fetches three data files, legitimately, and the paragraph above them names
          the file of figures. So the cells are parsed, every call that fetches is
          found -- directly, or through a function whose body fetches -- and each
          argument is resolved to the strings it can hold. A comment is not a call and
          a syntax tree holds no comments, so the question asks itself correctly.

          It has THREE outcomes, not two. A call whose argument cannot be resolved is
          reported as itself, because an empty answer from an instrument is a third
          state rather than a synonym for a healthy one. It neither fails the rule nor
          counts as silence, and the fetch inside a helper whose call sites ARE
          readable is not counted blind, since the question is answered there.

WHAT THIS GATE CALLS RATHER THAN REPEATS. The one thing it could have copied from the
producer is the marker line that identifies the generated cell. It reads it out of
embed_notebook_expectations.py instead, by walking that file's syntax tree for the
string constant carrying it, and falls back to the contract written below only when
the producer is not on disk or spells the marker in pieces the tree cannot resolve.
Which of the two was used is printed and recorded, because a gate matching a name the
producer no longer writes is a gate that has stopped asking anything.

Read-only over the repository. Everything the calibration writes goes to a scratch
directory of its own and the real notebook is never opened for writing.

    uv run --no-project --with-requirements requirements.txt python3 \
        checks/chk_notebook_expectations.py
    uv run --no-project --with-requirements requirements.txt python3 \
        checks/chk_notebook_expectations.py --selftest
"""
import argparse
import ast
import json
import math
import os
import pprint
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import artifact                                                       # noqa: E402
from evidence import report_gate                                      # noqa: E402

OUT_JSON = os.path.join(HERE, "chk_notebook_expectations_results.json")

NOTEBOOK = os.path.join(ROOT, "notebooks",
                        "counterparty_adverse_selection.ipynb")
EXPECTED_JSON = os.path.join(ROOT, "notebooks", "notebook_expected.json")
PRODUCER = os.path.join(ROOT, "embed_notebook_expectations.py")

# The agreed first line of the generated cell. This is the FALLBACK: the live value is
# read out of the producer whenever the producer is on disk, so that a producer which
# changes its own marker moves this gate with it instead of leaving it looking for a
# line nobody writes.
MARKER_CONTRACT = ("# GENERATED CELL - written by embed_notebook_expectations.py "
                   "from notebook_expected.json - DO NOT EDIT BY HAND")

# What identifies the marker inside the producer's source, by what it SAYS rather than
# by the name of the constant holding it. A gate keyed on a variable name goes silent
# the day the variable is renamed, and that has already happened twice in this tree.
MARKER_SIGNS = ("GENERATED CELL", "DO NOT EDIT")

# The name of the file of figures, as a cell would spell it.
EXPECTED_BASENAME = "notebook_expected.json"

# What counts as fetching, recognised by the call and not by the word. The first
# version of RULE 3 searched cell text for this file's name standing near a fetching
# word, and it reported the notebook's own comment explaining that the fetch had been
# removed: the cell still fetches three data files, legitimately, and the name of the
# file of figures sits three lines above in a comment. Adjacency in text and passing
# into a call are different things, and only the second is the question.
#
# urlretrieve and urlopen are matched on the tail of the dotted name because nothing
# else in Python is called that. A bare `get` is deliberately NOT here: it would match
# every dict lookup in the notebook.
FETCH_TAILS = ("urlretrieve", "urlopen")
FETCH_DOTTED = ("requests.get", "requests.post", "httpx.get", "httpx.post")

# Shell lines are not Python and no syntax tree sees them, so they are read as text.
# The rule is stated rather than hidden: this one leg of RULE 3 is a word search.
SHELL_FETCH_WORDS = ("wget", "curl")

# How far the resolver will follow a name before giving up, and how many rounds the
# interprocedural pass takes. Both are bounds against a cycle rather than judgements.
RESOLVE_DEPTH = 8

# The separator used to build a key path. A key holding it would make the path it is
# printed in unreadable and, worse, ambiguous, so such a key is quoted instead. This
# tree has already lost the addressability of 261 leaves of one artifact to a key that
# carried its address separator.
PATH_SEP = "."


# ----------------------------------------------------------------- reading the tree

def read_notebook(path):
    """The cells of a notebook as (index, cell_type, source), or an error string.

    A notebook that cannot be parsed is a finding rather than an empty list: an empty
    list would make every rule here report zero, and zero over nothing is the shape of
    failure this whole file exists to refuse.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except OSError as exc:
        return None, f"the notebook could not be opened: {exc.strerror or exc}"
    except ValueError as exc:
        return None, f"the notebook is not readable as JSON: {exc}"
    cells = []
    for i, cell in enumerate(doc.get("cells") or []):
        src = cell.get("source")
        text = "".join(src) if isinstance(src, list) else str(src or "")
        cells.append((i, cell.get("cell_type"), text))
    return cells, None


def read_home(path):
    """The figures as their home holds them, or an error string."""
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh), None
    except OSError as exc:
        return None, f"the home of the figures could not be opened: {exc}"
    except ValueError as exc:
        return None, f"the home of the figures is not readable as JSON: {exc}"


def marker_in_force():
    """(marker, where it came from). The producer is the home of this string.

    Resolved by walking the producer's syntax tree for a string constant that carries
    the marker's own words and opens with a comment character. A producer that builds
    the line by adding fragments together leaves no single constant to read, and that
    case is reported by name rather than guessed at: the contract below is used and
    the artifact says the resolution failed, so nobody reads a green run as proof that
    the two agree.
    """
    if not os.path.isfile(PRODUCER):
        return MARKER_CONTRACT, "contract (the producer is not on disk yet)"
    try:
        with open(PRODUCER, encoding="utf-8") as fh:
            tree = ast.parse(fh.read(), filename=os.path.basename(PRODUCER))
    except (OSError, SyntaxError) as exc:
        return MARKER_CONTRACT, f"contract (the producer would not parse: {exc})"
    found = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        first = node.value.split("\n")[0].strip()
        if first.startswith("#") and all(s in first for s in MARKER_SIGNS):
            found.append(first)
    if len(set(found)) == 1:
        return found[0], f"{os.path.basename(PRODUCER)} (read from its syntax tree)"
    if not found:
        return MARKER_CONTRACT, ("contract (the producer holds no single string "
                                 "constant carrying the marker; it may be built from "
                                 "fragments)")
    return MARKER_CONTRACT, (f"contract (the producer holds {len(set(found))} "
                             f"different marker strings, so none of them is the one)")


# --------------------------------------------------------- RULE 1: the cell is there

def marked_cells(cells, marker):
    """(cells opening with the marker, cells carrying it somewhere further down).

    The second list is what turns a bare zero into an actionable failure. A cell that
    holds the marker on its third line is a generated cell somebody has edited above
    the marker, and reporting only "no marked cell" would send the reader looking for
    a cell that is right there.
    """
    opening, buried = [], []
    for idx, kind, src in cells:
        if kind != "code":
            continue
        lines = src.split("\n")
        if lines and lines[0].rstrip() == marker:
            opening.append((idx, src))
        elif marker in src:
            buried.append((idx, src))
    return opening, buried


def rule1(cells, marker, nb_error):
    """Findings for the presence and uniqueness of the generated cell."""
    rel = os.path.relpath(NOTEBOOK, ROOT)
    if nb_error:
        return [{"file": rel, "line": 0, "detail": nb_error, "source": "RULE 1"}], []
    opening, buried = marked_cells(cells, marker)
    if len(opening) == 1:
        return [], opening
    sites = []
    if not opening:
        sites.append({
            "file": rel, "line": 0,
            "detail": ("expected exactly 1 code cell whose first line is the marker; "
                       f"found 0 among {sum(1 for c in cells if c[1] == 'code')} code "
                       "cells. Run embed_notebook_expectations.py to write the cell. "
                       "This is a failure and not a quiet pass: with no cell there is "
                       "nothing holding the figures the notebook checks against"),
            "source": "RULE 1"})
        for idx, _src in buried:
            sites.append({
                "file": f"{rel}#cell{idx}", "line": 0,
                "detail": ("this cell carries the marker, but not as its first line, "
                           "so something has been written above it. That is a "
                           "generated cell somebody has edited"),
                "source": "RULE 1"})
    else:
        for idx, _src in opening:
            sites.append({
                "file": f"{rel}#cell{idx}", "line": 1,
                "detail": (f"expected exactly 1 marked cell, found {len(opening)}. "
                           "Two copies of one fact cannot both be read, and nothing "
                           "in the notebook says which one the run used"),
                "source": "RULE 1"})
    return sites, opening


# ------------------------------------------------- RULE 2: the copy equals the home

def cell_literal(source):
    """(value, how it was found, line of the assignment, error).

    Preferring the agreed name EXPECTED and then falling back to the only mapping the
    cell assigns is deliberate. The name is the contract and is tried first; the shape
    is the behaviour and keeps the gate reading a cell whose name has moved, which is
    a rename to report rather than a reason to go blind.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return None, None, exc.lineno or 0, f"the cell does not parse: {exc}"
    mappings = []
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, TypeError, SyntaxError, MemoryError,
                    RecursionError) as exc:
                if target.id == "EXPECTED":
                    return None, None, node.lineno, (
                        f"EXPECTED is assigned something that is not a literal this "
                        f"gate can read back: {exc}")
                continue
            if isinstance(value, dict):
                mappings.append((target.id, value, node.lineno))
    for name, value, line in mappings:
        if name == "EXPECTED":
            return value, "the assignment to EXPECTED", line, None
    if len(mappings) == 1:
        name, value, line = mappings[0]
        return value, f"the only mapping the cell assigns, named {name}", line, None
    if not mappings:
        return None, None, 0, ("the cell assigns no mapping at module level, so it "
                               "carries no figures at all")
    names = ", ".join(sorted(n for n, _v, _l in mappings))
    return None, None, 0, (f"the cell assigns {len(mappings)} mappings ({names}) and "
                           f"none of them is called EXPECTED, so which one holds the "
                           f"figures is not stated")


def _step(path, key):
    """One step down a key path, quoting a key that would make the path ambiguous."""
    text = str(key)
    if PATH_SEP in text or "[" in text or "]" in text:
        return f'{path}["{text}"]'
    return f"{path}{PATH_SEP}{text}" if path else text


def _same(a, b):
    """Exact equality, with the type counted as part of the value.

    True and 1 compare equal in Python and are different values in a JSON document, so
    the boolean is separated first. Two floats are compared bit for bit because the
    cell is a copy: a tolerance here would let the copy drift by the width of the
    tolerance and call it agreement. Two NaNs at one address are the same figure even
    though NaN equals nothing, and saying so here is cheaper than a false finding.
    """
    if isinstance(a, bool) != isinstance(b, bool):
        return False
    if isinstance(a, float) and isinstance(b, float):
        if math.isnan(a) and math.isnan(b):
            return True
        return a == b
    return type(a) is type(b) and a == b


def count_leaves(node):
    """Scalars under a value. The population every count in this gate is taken over."""
    if isinstance(node, dict):
        return sum(count_leaves(v) for v in node.values())
    if isinstance(node, (list, tuple)):
        return sum(count_leaves(v) for v in node)
    return 1


def leaf_diff(in_cell, in_home, path="EXPECTED"):
    """Every place the copy and the home disagree, as (key path, cell, home, why)."""
    out = []
    if isinstance(in_home, dict) and isinstance(in_cell, dict):
        for key in in_home:
            if key not in in_cell:
                out.append((_step(path, key), "<absent>", in_home[key],
                            "the home holds this key and the cell does not"))
        for key in in_cell:
            if key not in in_home:
                out.append((_step(path, key), in_cell[key], "<absent>",
                            "the cell holds this key and the home does not"))
        for key in in_home:
            if key in in_cell:
                out.extend(leaf_diff(in_cell[key], in_home[key], _step(path, key)))
        return out
    if isinstance(in_home, list) and isinstance(in_cell, list):
        if len(in_home) != len(in_cell):
            out.append((path, f"{len(in_cell)} items", f"{len(in_home)} items",
                        "the two lists are of different length"))
        for i in range(min(len(in_home), len(in_cell))):
            out.extend(leaf_diff(in_cell[i], in_home[i], f"{path}[{i}]"))
        return out
    if isinstance(in_home, (dict, list)) != isinstance(in_cell, (dict, list)):
        out.append((path, type(in_cell).__name__, type(in_home).__name__,
                    "the copy and the home are of different shape at this address"))
        return out
    if not _same(in_cell, in_home):
        why = ("the two values differ" if type(in_cell) is type(in_home)
               else f"the copy is a {type(in_cell).__name__} and the home a "
                    f"{type(in_home).__name__}")
        out.append((path, in_cell, in_home, why))
    return out


def _locate(source, value, fallback):
    """The line of a cell where a value is written, or the assignment line.

    Best effort by design and stated as such in the finding. The literal is written by
    a producer this gate does not control, so the value may sit on a line of its own
    or share one with thirty others; when it cannot be found the reader is sent to the
    assignment, which is always right and less precise.
    """
    needle = repr(value)
    for n, line in enumerate(source.split("\n"), start=1):
        if needle in line:
            return n, True
    return fallback, False


def rule2(cells, opening, home, home_error):
    """Findings for the agreement of the copy with its home, plus the population."""
    rel = os.path.relpath(NOTEBOOK, ROOT)
    if home_error:
        return [{"file": os.path.relpath(EXPECTED_JSON, ROOT), "line": 0,
                 "detail": home_error, "source": "RULE 2"}], 0, None
    if len(opening) != 1:
        # NOT zero findings. There was nothing to compare, and a count of zero taken
        # over an empty population prints exactly like agreement.
        return [{
            "file": rel, "line": 0,
            "detail": (f"expected 1 marked cell to compare against "
                       f"{os.path.relpath(EXPECTED_JSON, ROOT)}, and found "
                       f"{len(opening)}, so no leaf was compared. This is reported as "
                       f"a finding because a count of 0 disagreements taken over 0 "
                       f"comparisons reads on screen as agreement"),
            "source": "RULE 2"}], 0, None
    idx, src = opening[0]
    value, how, line, error = cell_literal(src)
    if error:
        return [{"file": f"{rel}#cell{idx}", "line": line,
                 "detail": error + ". The cell has to hold the figures as one literal "
                                   "this gate can read back and compare",
                 "source": "RULE 2"}], 0, None
    n_leaves = count_leaves(home)
    sites = []
    for path, in_cell, in_home, why in leaf_diff(value, home):
        at, exact = _locate(src, in_cell, line)
        sites.append({
            "file": f"{rel}#cell{idx}", "line": at,
            "detail": (f"{path}: the notebook holds {in_cell!r} and "
                       f"{os.path.relpath(EXPECTED_JSON, ROOT)} holds {in_home!r}. "
                       f"{why}"
                       + ("" if exact else "; the line given is the assignment, since "
                                           "the value is not written on a line of its "
                                           "own")),
            "source": "RULE 2"})
    return sites, n_leaves, how


# ---------------------------------------------- RULE 3: nothing is fetched any more

def _dotted(node):
    """The dotted name a call is made through, or None for anything else."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    parts.append(node.id)
    return ".".join(reversed(parts))


def _is_fetch_call(dotted):
    """True when this dotted name is a call that goes to the network."""
    if not dotted:
        return False
    if dotted.rsplit(".", 1)[-1] in FETCH_TAILS:
        return True
    return any(dotted == d or dotted.endswith("." + d) for d in FETCH_DOTTED)


def _parsable(src):
    """A cell's source with its magic and shell lines commented out.

    A line opening with % or ! is not Python and would end the parse at the first one,
    hiding every call below it in the same cell. Commenting it in place keeps the line
    numbers, and the shell lines are read separately as text.
    """
    return "\n".join("#" + ln if ln.lstrip()[:1] in ("%", "!") else ln
                     for ln in src.split("\n"))


def _string_env(trees):
    """{name: [value nodes]} for every assignment anywhere in the notebook.

    The namespace is the whole notebook rather than one cell, because that is how a
    notebook runs: cells share one namespace, and the helper that fetches is defined in
    one cell and called from another. A rule that stopped at the cell boundary would
    resolve neither.
    """
    env = {}
    for tree in trees:
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        env.setdefault(target.id, []).append(node.value)
            elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
                if isinstance(node.target, ast.Name) and node.value is not None:
                    env.setdefault(node.target.id, []).append(node.value)
            elif isinstance(node, ast.For):
                # for f in ['a', 'b']: the loop name takes each member in turn, and a
                # fetch inside such a loop is how a list of files is downloaded.
                if isinstance(node.target, ast.Name) and isinstance(
                        node.iter, (ast.List, ast.Tuple, ast.Set)):
                    for item in node.iter.elts:
                        env.setdefault(node.target.id, []).append(item)
    return env


def _resolve(node, env, depth=0, seen=None):
    """The strings a node can evaluate to, or None when that cannot be decided.

    None is the THIRD outcome and is never folded into either of the other two. A
    caller that read None as "no match" would go quiet exactly where it cannot see,
    and one that read it as a finding would report every call whose argument is a
    parameter.
    """
    if depth > RESOLVE_DEPTH:
        return None
    seen = seen or set()
    if isinstance(node, ast.Constant):
        return {node.value} if isinstance(node.value, str) else None
    if isinstance(node, ast.Name):
        if node.id in seen:
            return None
        out = set()
        for value in env.get(node.id, ()):
            got = _resolve(value, env, depth + 1, seen | {node.id})
            if got is None:
                return None
            out |= got
        return out or None
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _resolve(node.left, env, depth + 1, seen)
        right = _resolve(node.right, env, depth + 1, seen)
        if left is None or right is None:
            return None
        return {a + b for a in left for b in right}
    if isinstance(node, ast.JoinedStr):
        out = {""}
        for part in node.values:
            got = _resolve(part, env, depth + 1, seen)
            if got is None:
                return None
            out = {a + b for a in out for b in got}
        return out
    if isinstance(node, ast.FormattedValue):
        return _resolve(node.value, env, depth + 1, seen)
    if isinstance(node, ast.Call):
        name = _dotted(node.func)
        if name and name.endswith("path.join"):
            out = {""}
            for arg in node.args:
                got = _resolve(arg, env, depth + 1, seen)
                if got is None:
                    return None
                out = {(a + "/" + b if a else b) for a in out for b in got}
            return out
    return None


def _fetching_functions(trees):
    """Names of functions in the notebook that reach the network, directly or not.

    Taken to a fixed point, so a helper that calls a helper that fetches is a fetcher.
    This is what binds the rule to behaviour: dataset_file is not recognised by being
    called dataset_file, but by holding urlretrieve in its body, and the file names
    that flow into it are then read at its call sites where they are literals.
    """
    funcs = {}
    for tree in trees:
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                funcs[node.name] = node
    fetchers = set()
    for _round in range(len(funcs) + 1):
        grew = False
        for name, node in funcs.items():
            if name in fetchers:
                continue
            for call in ast.walk(node):
                if not isinstance(call, ast.Call):
                    continue
                called = _dotted(call.func)
                if _is_fetch_call(called) or (called in fetchers):
                    fetchers.add(name)
                    grew = True
                    break
        if not grew:
            break
    return funcs, fetchers


def _enclosing(tree):
    """{node: name of the function it sits in}, for the calls of one tree."""
    where = {}

    def walk(node, scope):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            scope = node.name
        if isinstance(node, ast.Call):
            where[id(node)] = scope
        for child in ast.iter_child_nodes(node):
            walk(child, scope)

    walk(tree, None)
    return where


def rule3(cells, nb_error):
    """Fetches of the file of figures, found by what a call is PASSED.

    Returns (findings, calls that could not be resolved, number of fetch call sites).
    The three are kept apart on purpose. A finding is a fetch this gate can show
    carries the file of figures. An unresolved call is one whose argument this gate
    cannot decide, which is neither health nor a defect and is reported as itself. The
    count of call sites is what says the silence was taken over something: a run
    reporting no findings and no call sites has measured nothing.

    The namespace is the whole notebook and the place is the cell, which is how a
    notebook runs. Comments are invisible here by construction, because a syntax tree
    holds no comments, and that is the point: the notebook's own paragraph explaining
    that the fetch was removed used to be read as the fetch.
    """
    if nb_error:
        return [], [], 0
    rel = os.path.relpath(NOTEBOOK, ROOT)
    code = [(idx, _parsable(src)) for idx, kind, src in cells if kind == "code"]
    trees, per_cell = [], []
    for idx, src in code:
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        trees.append(tree)
        per_cell.append((idx, src, tree))
    env = _string_env(trees)
    _funcs, fetchers = _fetching_functions(trees)

    sites, unresolved, n_calls = [], [], 0
    interior = []            # fetches inside a fetching function, judged at its callers
    resolved_callers = set()  # fetching functions with a call site this gate can read
    for idx, src, tree in per_cell:
        where = _enclosing(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            called = _dotted(node.func)
            direct = _is_fetch_call(called)
            through = called in fetchers
            if not (direct or through):
                continue
            n_calls += 1
            values, blind = set(), False
            for arg in list(node.args) + [k.value for k in node.keywords]:
                got = _resolve(arg, env, 0)
                if got is None:
                    blind = True
                else:
                    values |= got
            hit = sorted(v for v in values if EXPECTED_BASENAME in v)
            record = {"cell": idx, "line": node.lineno, "call": called,
                      "through_helper": bool(through and not direct)}
            if hit:
                sites.append({
                    "file": f"{rel}#cell{idx}", "line": node.lineno,
                    "detail": (f"{called}() is passed {hit[0]!r}"
                               + (f", by way of the fetching helper {called}"
                                  if through and not direct else "")
                               + f". The figures the notebook checks against would "
                                 f"then come from a copy held somewhere else, which "
                                 f"is free to run ahead of this one or fall behind "
                                 f"it. They come from the generated cell now"),
                    "source": "RULE 3"})
                if through:
                    resolved_callers.add(called)
                continue
            if through and not blind:
                resolved_callers.add(called)
            if blind:
                scope = where.get(id(node))
                if scope in fetchers:
                    interior.append((record, scope))
                else:
                    unresolved.append(record)

    # A fetch whose argument is a parameter of a fetching helper is not blind: the
    # question is answered at the helper's call sites, and those are literals. It stays
    # unresolved only when nothing in the notebook calls the helper readably.
    for record, scope in interior:
        if scope not in resolved_callers:
            record["inside"] = scope
            unresolved.append(record)

    # Shell lines carry no syntax tree, so this one leg is a word search, and it is
    # declared rather than folded into the rest.
    for idx, _kind, src in cells:
        for n, line in enumerate(src.split("\n"), start=1):
            bare = line.lstrip()
            if bare[:1] != "!" or EXPECTED_BASENAME not in line:
                continue
            if any(w in bare.lower() for w in SHELL_FETCH_WORDS):
                sites.append({
                    "file": f"{rel}#cell{idx}", "line": n,
                    "detail": (f"a shell line fetches {EXPECTED_BASENAME}. Shell lines "
                               f"are not Python and carry no syntax tree, so this leg "
                               f"of the rule reads them as text"),
                    "source": "RULE 3"})
    return sites, unresolved, n_calls


# ------------------------------------------------------------------- calibration

def _fixture_cell(figures, marker):
    """The generated cell as the contract spells it, written here by hand.

    Written by hand on purpose. This gate never renders a cell in its real run, so
    borrowing the producer's renderer for the fixture would make the calibration test
    the two of them agreeing with each other rather than the gate reading a cell.
    """
    body = pprint.pformat(figures, width=88, sort_dicts=False)
    return "\n".join([
        marker,
        "# The figures below are a copy. Their home is notebooks/"
        "notebook_expected.json,",
        "# which is written from the committed results files of the pipeline.",
        "# Edit the home and run the producer again; do not edit this cell.",
        "",
        f"EXPECTED = {body}",
        "",
        "EXP = EXPECTED",
        "print('reported figures loaded for:', ', '.join(EXPECTED))",
    ])


def _live_notebook_doc():
    """The real notebook, from disk and then from git. Never written to.

    The working copy may be part way through a write, so an unreadable notebook on disk
    is not a reason for the calibration to fail: the last committed version is the same
    real notebook and is what the fixture is then built from.
    """
    try:
        with open(NOTEBOOK, encoding="utf-8") as fh:
            return json.load(fh), "the working tree"
    except (OSError, ValueError):
        pass
    rel = os.path.relpath(NOTEBOOK, ROOT)
    out = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=ROOT,
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError("the calibration has no real notebook to build a fixture "
                           "from: the working tree copy will not parse and git has no "
                           "committed copy either")
    return json.loads(out.stdout), "git HEAD"


def _live_home():
    """The real figures, from disk and then from git. Never written to."""
    try:
        with open(EXPECTED_JSON, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        pass
    rel = os.path.relpath(EXPECTED_JSON, ROOT)
    out = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=ROOT,
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError("the calibration has no real file of figures to build a "
                           "fixture from, on disk or in git")
    return json.loads(out.stdout)


def _first_float_path(node, path="EXPECTED"):
    """The address of the first float under a value, walked in a fixed order."""
    if isinstance(node, dict):
        for key, value in node.items():
            hit = _first_float_path(value, _step(path, key))
            if hit:
                return hit
        return None
    if isinstance(node, list):
        for i, value in enumerate(node):
            hit = _first_float_path(value, f"{path}[{i}]")
            if hit:
                return hit
        return None
    return path if isinstance(node, float) and not isinstance(node, bool) else None


def _nudge(node, target, path="EXPECTED"):
    """A copy of the figures with the float at `target` moved by one unit in the last
    place. Returns (copy, old value, new value)."""
    if isinstance(node, dict):
        out, old, new = {}, None, None
        for key, value in node.items():
            sub, o, n = _nudge(value, target, _step(path, key))
            out[key] = sub
            if o is not None:
                old, new = o, n
        return out, old, new
    if isinstance(node, list):
        out, old, new = [], None, None
        for i, value in enumerate(node):
            sub, o, n = _nudge(value, target, f"{path}[{i}]")
            out.append(sub)
            if o is not None:
                old, new = o, n
        return out, old, new
    if path == target:
        moved = math.nextafter(node, math.inf)
        return moved, node, moved
    return node, None, None


def _cell_text(cell):
    """The source of a cell as one string, the way a notebook stores it."""
    src = cell.get("source")
    return "".join(src) if isinstance(src, list) else str(src or "")


def _as_cell(text, cell_id):
    """A code cell holding this text, with the line endings a notebook keeps.

    The line endings are the point. A notebook stores source as a list of lines each
    ending in a newline, and a list written without them joins back into one physical
    line. The first version of this calibration did exactly that, and the fixture it
    built could not be read by the gate at all.
    """
    lines = text.split("\n")
    source = [ln + "\n" for ln in lines[:-1]] + [lines[-1]]
    return {"cell_type": "code", "execution_count": None, "id": cell_id,
            "metadata": {}, "outputs": [], "source": source}


def _doc_cells(doc):
    """A doc's cells in the shape read_notebook returns, for the predicates to read."""
    return [(i, c.get("cell_type"), _cell_text(c))
            for i, c in enumerate(doc.get("cells") or [])]


def _fetching_cell_indices(doc):
    """Which cells of a doc RULE 3 reports, decided by the rule itself.

    The fixture builder asks the predicate rather than repeating a text test of its
    own. That matters here more than usual: a text test is exactly what was wrong, and
    a builder still carrying one would strip the notebook's legitimate fetch of the
    three data files out of every fixture and leave a silent case that proves nothing.
    """
    sites, _unresolved, _n = rule3(_doc_cells(doc), None)
    out = set()
    for site in sites:
        tail = site["file"].rsplit("#cell", 1)
        if len(tail) == 2 and tail[1].isdigit():
            out.add(int(tail[1]))
    return out


def _live_fetch_form(doc):
    """(the call the notebook fetches through, the name holding its base address).

    Read off the notebook rather than typed here, so an injected fetch wears the same
    form as the real one. If the notebook moves from urlretrieve to something else, or
    renames the address it builds on, the injected case follows it instead of going
    stale into a shape the notebook no longer has.
    """
    cells = _doc_cells(doc)
    trees = []
    for _idx, kind, src in cells:
        if kind != "code":
            continue
        try:
            trees.append(ast.parse(_parsable(src)))
        except SyntaxError:
            continue
    env = _string_env(trees)
    for tree in trees:
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            called = _dotted(node.func)
            if not _is_fetch_call(called) or not node.args:
                continue
            base = None
            for inner in ast.walk(node.args[0]):
                if not isinstance(inner, ast.Name):
                    continue
                got = _resolve(inner, env, 0)
                if got and all(v.startswith("http") for v in got):
                    base = inner.id
                    break
            return called, base
    raise RuntimeError("the notebook makes no fetch this gate recognises, so the "
                       "calibration cannot build an injected fetch in the same form "
                       "as the real one")


def _injected_fetches(doc):
    """The lines that put a fetch of the file of figures back into the notebook.

    WHY THESE ARE INJECTED AND NOT QUOTED OUT OF GIT, and this is the paragraph to
    read before improving on it. The case RULE 3 must fire on was first built by
    lifting the real download cell out of HEAD, on the reasoning that a state the
    repository was actually in beats an imitation of it. That held for one day. The
    repair was committed as 5b6042e, the download left HEAD, and the calibration
    stopped being able to build its own firing case: it halted with "the committed
    notebook holds no fetch of the figures". A CALIBRATION CASE ANCHORED ON A DEFECT
    ERASES ITSELF THE MOMENT THE DEFECT IS REPAIRED, and repairing it is the whole
    point. So the case is injected into a copy of the notebook as it stands, and the
    FORM of the injected call is read off the notebook's own fetch, which is what
    keeps it looking like the real thing without depending on any commit.

    Two forms, because the resolver reads both and both have to keep working: an
    argument that is a string literal, and an argument built by addition from a
    variable, which is how the live line spells it.
    """
    called, base = _live_fetch_form(doc)
    address = base if base else repr("https://zenodo.org/records/23540388/files/")
    return {
        "literal": (f"{called}({address} + "
                    f"{EXPECTED_BASENAME + '?download=1'!r}, "
                    f"{EXPECTED_BASENAME!r})"),
        "built": (f"_want = {EXPECTED_BASENAME!r}\n"
                  f"{called}({address} + _want + '?download=1', _want)"),
    }


def _inject_into_fetch_cell(doc, text):
    """Append a line to the cell that already fetches, and return the doc.

    Into that cell rather than into a new one, so the injected call sits beside the
    legitimate ones with the same imports and the same address in scope. A fixture
    that does not look like the real case certifies nothing.
    """
    doc = json.loads(json.dumps(doc))
    for cell in doc.get("cells") or []:
        if cell.get("cell_type") != "code":
            continue
        try:
            tree = ast.parse(_parsable(_cell_text(cell)))
        except SyntaxError:
            continue
        if any(isinstance(n, ast.Call) and _is_fetch_call(_dotted(n.func))
               for n in ast.walk(tree)):
            merged = _cell_text(cell).rstrip("\n") + "\n" + text
            cell["source"] = _as_cell(merged, "x")["source"]
            return doc
    raise RuntimeError("no cell of the fixture fetches anything, so there is nowhere "
                       "to inject a fetch that looks like the notebook's own")


def _fixture_doc(doc, marker, cell_text, duplicate=False,
                 bury=False, extra_cell=None, inject=None):
    """One fixture notebook, built from the real one with a stated single change.

    Every cell that carries figures -- a generated cell, or a cell the rule reports as
    fetching the file -- is taken out first, and exactly what the case is about is put
    back. Doing it that way rather than by replacing one cell in place is what makes
    the fixture the same whether the notebook on disk has been repaired yet or not,
    and the notebook is being written by another hand while this runs. Everything
    else survives, including the cell that legitimately fetches the three data files.
    """
    doc = json.loads(json.dumps(doc))
    fetching = _fetching_cell_indices(doc)
    kept, first = [], None
    for i, cell in enumerate(doc.get("cells") or []):
        text = _cell_text(cell)
        if i in fetching or marker in text:
            if first is None:
                first = len(kept)
            continue
        kept.append(cell)
    if first is None:
        raise RuntimeError("the calibration found nothing in the real notebook that "
                           "carries the figures, neither a generated cell nor a "
                           "fetch, so it has no place to build the fixture at")
    inserted = []
    if cell_text is not None:
        text = ("# a hand added this line\n" + cell_text) if bury else cell_text
        inserted.append(_as_cell(text, "genexp"))
        if duplicate:
            inserted.append(_as_cell(cell_text, "genexp2"))
    if extra_cell is not None:
        inserted.append(_as_cell(extra_cell, "extra"))
    doc["cells"] = kept[:first] + inserted + kept[first:]
    # The injection happens last, on the finished fixture. Doing it earlier would put
    # the fetch into a cell this builder then strips as fetching the figures, and the
    # case would build itself away.
    return doc if inject is None else _inject_into_fetch_cell(doc, inject)


BUILT = []          # fixture names, so the calibration counts what it built rather
                    # than carrying a hand-typed number beside it


def _write(tmp, name, doc):
    path = os.path.join(tmp, name)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)
    BUILT.append(name)
    return path


def _ask(path, marker, home):
    """The three questions over one notebook, as three counts and their sites."""
    cells, nb_error = read_notebook(path)
    s1, opening = rule1(cells or [], marker, nb_error)
    s2, _n_leaves, _how = rule2(cells or [], opening, home, None)
    s3, blind, n_calls = rule3(cells or [], nb_error)
    return s1, s2, s3, blind, n_calls


def calibrate():
    """Two opposite cases for every one of the three questions, on the live tree.

    One reference case cannot tell a predicate that is too wide from one that is too
    narrow, so each question gets a case where it must stay silent and a case where it
    must fire. Every fixture is the real notebook with one thing changed, because a
    fixture that does not look like the real case certifies nothing: the last gate
    written here passed its own calibration on an invented fixture and then read zero
    through a live file.

    The silent case is checked for being non-vacuous as well. The live notebook holds
    a cell that names the file of figures inside a printed message and fetches
    nothing, and RULE 3 has to keep passing over it; if that cell ever leaves, the
    silence of RULE 3 would stop meaning anything and this says so.
    """
    marker = MARKER_CONTRACT
    doc, doc_from = _live_notebook_doc()
    home = _live_home()
    lines = []
    tmp = tempfile.mkdtemp(prefix="chk_nb_exp_")
    try:
        good_cell = _fixture_cell(home, marker)
        good = _write(tmp, "good.ipynb", _fixture_doc(doc, marker, good_cell))

        # MUST STAY SILENT, and this is the case the first version of RULE 3 got
        # wrong. The notebook still fetches its three data files, legitimately, and
        # the paragraph beside that fetch names the file of figures while explaining
        # why it is no longer fetched. A rule reading text reports the comment.
        s1, s2, s3, blind, n_calls = _ask(good, marker, home)
        assert not s1, f"RULE 1 fires on one marked cell and one only: {s1}"
        assert not s2, f"RULE 2 fires on a copy that equals its home: {s2}"
        assert not s3, (f"RULE 3 fires on the notebook as it stands, whose fetch is "
                        f"of the data files only: {s3}")

        # ...and that silence is not vacuous, in the two ways it could have been. The
        # notebook has to still be fetching something, or the rule passed over nothing;
        # and it has to still name the file of figures outside the generated cell, or
        # the text the old rule tripped on is no longer there to trip on.
        assert n_calls >= 1, (
            "the good fixture makes no fetch at all, so RULE 3 staying silent says "
            "nothing about a notebook that does")
        cells, _err = read_notebook(good)
        mentions = [i for i, _k, src in cells
                    if EXPECTED_BASENAME in src and marker not in src]
        assert mentions, (
            "the good fixture no longer names the file of figures outside the "
            "generated cell, so RULE 3 staying silent proves nothing about it")
        lines.append(f"the silent case fetches {n_calls} time(s) and still names the "
                     f"file of figures in {len(mentions)} cell(s) outside the "
                     f"generated one")

        # MUST FIRE, RULE 2. One float moved by one unit in the last place.
        target = _first_float_path(home)
        assert target, "the home holds no float, so the drift case cannot be built"
        moved, old, new = _nudge(home, target)
        assert repr(old) != repr(new), (
            "one unit in the last place did not change how the value is written, so "
            "the fixture carries no drift at all")
        drift = _write(tmp, "drift.ipynb",
                       _fixture_doc(doc, marker, _fixture_cell(moved, marker)))
        s1, s2, s3, _blind, _n = _ask(drift, marker, home)
        assert not s1 and not s3, "moving one figure disturbed RULE 1 or RULE 3"
        assert len(s2) == 1, (
            f"RULE 2 reported {len(s2)} disagreements for one moved figure: {s2}")
        assert target in s2[0]["detail"], (
            f"RULE 2 fired but names the wrong address: {s2[0]['detail']}")
        lines.append(f"one unit in the last place at {target} ({old!r} to {new!r}) "
                     f"is reported as 1 disagreement out of {count_leaves(home)} "
                     f"leaves compared")

        # MUST FIRE, RULE 1, in both of its two directions.
        two = _write(tmp, "two.ipynb",
                     _fixture_doc(doc, marker, good_cell, duplicate=True))
        s1, _s2, _s3, _b, _n = _ask(two, marker, home)
        assert len(s1) == 2, f"RULE 1 does not report two marked cells: {s1}"
        none_yet = _write(tmp, "none.ipynb", _fixture_doc(doc, marker, None))
        s1, s2, s3, _b, _n = _ask(none_yet, marker, home)
        assert len(s1) == 1 and "found 0" in s1[0]["detail"], (
            f"RULE 1 does not report an absent cell: {s1}")
        assert len(s2) == 1 and "no leaf was compared" in s2[0]["detail"], (
            f"RULE 2 returns silence where it compared nothing: {s2}")

        # MUST FIRE, RULE 3, on a fetch of the file of figures put back into the cell
        # that already fetches. Injected rather than lifted out of git, for the reason
        # written at _injected_fetches: the case that was lifted stopped existing the
        # day the repair was committed. Both forms the resolver reads are injected,
        # one after the other, and the form of the call is taken off the notebook's own.
        forms = _injected_fetches(doc)
        for kind, text in sorted(forms.items()):
            back = _write(tmp, f"back_{kind}.ipynb",
                          _fixture_doc(doc, marker, good_cell, inject=text))
            s1, s2, s3, _b, _n = _ask(back, marker, home)
            assert not s1 and not s2, (
                f"injecting the {kind} fetch disturbed RULE 1 or RULE 2")
            assert len(s3) == 1, (
                f"RULE 3 does not report a fetch of the figures whose argument is "
                f"{kind}: {s3}")
        lines.append(f"the injected fetch is reported in both of its forms "
                     f"({', '.join(sorted(forms))}), built in the shape the notebook "
                     f"itself fetches in")

        # MUST FIRE, RULE 3, by way of the helper. This is how the defect would come
        # back now that the fetch goes through dataset_file: one more call beside the
        # three legitimate ones, with the file of figures as its argument. Nothing in
        # the line says urlretrieve, and the rule reaches it because it knows which
        # functions fetch rather than which are named as though they did.
        through = _write(tmp, "through.ipynb",
                         _fixture_doc(doc, marker, good_cell,
                                      extra_cell=f"EXPPATH = dataset_file("
                                                 f"{EXPECTED_BASENAME!r})"))
        s1, s2, s3, _b, _n = _ask(through, marker, home)
        assert not s1 and not s2, "the helper case disturbed RULE 1 or RULE 2"
        assert len(s3) == 1 and "helper" in s3[0]["detail"], (
            f"RULE 3 does not follow the file of figures into the fetching helper: "
            f"{s3}")

        # THE THIRD OUTCOME HAS TO BE SHOWN CAPABLE OF HAPPENING. The live run prints
        # "not resolvable: 0", and a zero whose predicate has never fired is
        # indistinguishable from a predicate that cannot fire at all. Here a fetch is
        # given arguments that come from the environment, which nothing in the notebook
        # can decide: it must be counted blind, and it must NOT be counted as a finding.
        blindcase = _write(tmp, "blind.ipynb",
                           _fixture_doc(doc, marker, good_cell,
                                        extra_cell="urllib.request.urlretrieve("
                                                   "os.environ['SRC'], "
                                                   "os.environ['DST'])"))
        s1, s2, s3, blind2, _n = _ask(blindcase, marker, home)
        assert not s1 and not s2, "the unresolvable case disturbed RULE 1 or RULE 2"
        assert not s3, ("a fetch this gate cannot read is reported as a finding, which "
                        "makes an unanswered question look like a defect")
        assert len(blind2) == 1, (
            f"a fetch this gate cannot read is not counted as unresolvable, so its "
            f"zero on the live tree would mean nothing: {blind2}")
        # ...and the opposite: the notebook's own fetch, whose argument is a parameter
        # of a helper the notebook calls with literals, is NOT blind, because the
        # question is answered at those call sites.
        assert not blind, ("the fetch inside the notebook's helper is counted blind "
                           "even though its call sites are literals")
        lines.append("the third outcome fires on a fetch built from the environment "
                     "and stays at zero on the notebook's own helper, whose call "
                     "sites are literals")

        # A cell that opens with something else and carries the marker below it is an
        # edited generated cell, and saying "no cell" would send the reader away.
        buried = _write(tmp, "buried.ipynb",
                        _fixture_doc(doc, marker, good_cell, bury=True))
        s1, _s2, _s3, _b, _n = _ask(buried, marker, home)
        assert len(s1) == 2 and any("not as its first line" in s["detail"]
                                    for s in s1), (
            f"RULE 1 does not say that an edited cell is right there: {s1}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    lines.insert(0, f"calibration: {len(BUILT)} fixtures built from the real notebook "
                    f"read out of {doc_from}, over {count_leaves(home)} leaves of the "
                    f"real file of figures")
    lines.append("silent: one marked cell agreeing with its home; the notebook's own "
                 "fetch of its three data files, with the file of figures named in "
                 "the comment beside it; and a cell naming the file inside a printed "
                 "message with no call at all")
    lines.append("fires: one unit in the last place, zero marked cells, two marked "
                 "cells, a marker buried under an edit, a fetch of the file of figures "
                 "injected in both of its forms, and the same file passed to the "
                 "fetching helper")
    return " | ".join(lines)


# ------------------------------------------------------------------------- the run

def main():
    parser = argparse.ArgumentParser(
        description="the figures inside the notebook are the figures in their home")
    parser.add_argument("--selftest", action="store_true",
                        help="run the calibration only and exit non-zero if any case "
                             "of it fails")
    args = parser.parse_args()

    started = artifact.start_clock()
    try:
        calibration = calibrate()
    except AssertionError as exc:
        print("CALIBRATION FAILED. This gate has not been shown to work today, so "
              "nothing it says about the notebook can be relied on.")
        print(f"  {exc}")
        return 2
    except RuntimeError as exc:
        print(f"CALIBRATION COULD NOT RUN: {exc}")
        return 2
    print(calibration)
    if args.selftest:
        return 0

    marker, marker_from = marker_in_force()
    cells, nb_error = read_notebook(NOTEBOOK)
    home, home_error = read_home(EXPECTED_JSON)

    s1, opening = rule1(cells or [], marker, nb_error)
    s2, n_leaves, literal_from = rule2(cells or [], opening, home, home_error)
    s3, blind, n_fetch_calls = rule3(cells or [], nb_error)

    n_code = sum(1 for c in (cells or []) if c[1] == "code")
    rel = os.path.relpath(NOTEBOOK, ROOT)
    print("=" * 78)
    print("  THE FIGURES INSIDE THE NOTEBOOK ARE THE FIGURES IN THEIR HOME")
    print("=" * 78)
    print(f"  notebook                 : {rel}"
          + (f", {len(cells)} cells ({n_code} code)" if cells else " (unreadable)"))
    print(f"  home of the figures      : {os.path.relpath(EXPECTED_JSON, ROOT)}"
          + (f", {n_leaves} leaves" if n_leaves else " (unreadable)"))
    print(f"  marker read from         : {marker_from}")
    if literal_from:
        print(f"  figures in the cell read : {literal_from}")
    print(f"  RULE 1 marked cell       : {len(s1)} finding(s)")
    print(f"  RULE 2 copy against home : {len(s2)} finding(s) over {n_leaves} leaves")
    print(f"  RULE 3 fetch of the file : {len(s3)} finding(s) over "
          f"{n_fetch_calls} fetch call(s) in {len(cells or [])} cells")
    # The third outcome, printed whether or not it is empty. An empty answer from a
    # measuring instrument is a third state and not a synonym for a healthy one, so
    # the line stands even at zero rather than appearing only when there is something
    # to say.
    print(f"  ...of which not resolvable: {len(blind)}"
          + ("" if not blind else
             "  " + "; ".join(f"cell{b['cell']}:{b['line']} {b['call']}()"
                              for b in blind[:4])))

    verdict = "PASS" if not (s1 or s2 or s3) else "FAIL"
    artifact.write(
        os.path.basename(OUT_JSON),
        {"verdict": verdict,
         "marker": marker,
         "marker_read_from": marker_from,
         "n_rule1_marked_cell": len(s1),
         "n_rule2_copy_disagrees": len(s2),
         "n_rule3_fetch_of_the_file": len(s3),
         # The three outcomes of RULE 3, kept apart. A fetch this gate cannot resolve
         # is neither a finding nor health, and folding it into either would make one
         # of the two numbers say something it has not measured.
         "n_rule3_fetch_call_sites": n_fetch_calls,
         "n_rule3_calls_not_resolvable": len(blind),
         "rule3_calls_not_resolvable": blind,
         "n_leaves_compared": n_leaves,
         "n_cells": len(cells or []),
         "n_code_cells": n_code,
         "figures_in_the_cell_read_from": literal_from,
         "notebook_error": nb_error,
         "home_error": home_error,
         "findings": s1 + s2 + s3,
         "calibration": calibration},
        script=__file__,
        # Two named files rather than a walk, so both are hashed: this gate reads the
        # notebook and the home of the figures, and a rewrite of either is the event it
        # exists to notice.
        inputs=[NOTEBOOK, EXPECTED_JSON],
        scope={
            "population": (f"{len(cells or [])} cells of {rel} and {n_leaves} leaves "
                           f"of {os.path.relpath(EXPECTED_JSON, ROOT)}"),
            "window": ("n/a: this gate compares a copy against its home as both stand "
                       "now, and reads no market data"),
            "coins": "n/a: this gate reads figures already computed, not market data",
        },
        started=started,
        extra_meta={"marker_signs": list(MARKER_SIGNS),
                    "fetch_tails": list(FETCH_TAILS),
                    "fetch_dotted": list(FETCH_DOTTED),
                    "shell_fetch_words": list(SHELL_FETCH_WORDS),
                    "producer_on_disk": os.path.isfile(PRODUCER),
                    "path_separator": PATH_SEP},
    )
    print(f"  results -> {os.path.basename(OUT_JSON)}")

    return report_gate(
        [{"name": "the generated cell of figures is present exactly once",
          "permitted": 0,
          "found": len(s1),
          "assumption": ("the notebook carries the reported figures in one generated "
                         "cell, so that the figures and the checks that read them "
                         "cannot be of different ages. Zero cells fails as loudly as "
                         "two, because with no cell there is nothing to compare and "
                         "silence would read as health"),
          "method": (f"the first line of every code cell is compared against the "
                     f"marker, which is read from {marker_from}; a cell carrying the "
                     f"marker further down is reported as an edited generated cell"),
          "note": ("going over means the notebook has no single home for the figures "
                   "it checks against, which is the state that left it passing 4 of "
                   "its 25 checks"),
          "sites": s1},
         {"name": "the copy in the notebook equals the home of the figures",
          "permitted": 0,
          "found": len(s2),
          "assumption": ("the generated cell is a copy of notebooks/"
                         "notebook_expected.json and equals it at every leaf. A hand "
                         "that edits the cell moves the figure the notebook checks "
                         "against without moving the figure the report publishes"),
          "method": (f"the literal is read back with ast.literal_eval and walked leaf "
                     f"by leaf against the home over {n_leaves} leaves; floats are "
                     f"compared for exact equality, because the cell is a copy and "
                     f"not a re-derivation, and a mismatch prints the key path, the "
                     f"value in the notebook and the value in the home"),
          "note": ("going over means the notebook and the report disagree about a "
                   "published figure while both look healthy"),
          "sites": s2},
         {"name": "no cell fetches the file of figures from somewhere else",
          "permitted": 0,
          "found": len(s3),
          "assumption": ("the figures come from this clone. A copy fetched at run "
                         "time is free to run ahead of this one or fall behind it, "
                         "and no gate in this tree can see a remote file"),
          "method": (f"the code cells are parsed and every call that reaches the "
                     f"network is found, directly or through a function whose body "
                     f"does; each argument is resolved to the strings it can hold, "
                     f"across the whole notebook namespace, and a resolved string "
                     f"carrying {EXPECTED_BASENAME} is the finding. A comment is not a "
                     f"call and a syntax tree holds no comments, so the notebook's own "
                     f"paragraph about the removed fetch is invisible here. "
                     f"{n_fetch_calls} call site(s) were read and {len(blind)} could "
                     f"not be resolved; those are reported as a third outcome and do "
                     f"not fail this rule"),
          "note": ("going over means the published archive can once more decide what "
                   "the notebook checks against, which is what put a copy written on "
                   "10 July in front of a reader following the README"),
          "sites": s3}],
        OUT_JSON,
        inputs={"notebook": rel,
                "home": os.path.relpath(EXPECTED_JSON, ROOT),
                "producer": os.path.relpath(PRODUCER, ROOT)})


if __name__ == "__main__":
    sys.exit(main())
