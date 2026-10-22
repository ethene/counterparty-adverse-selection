#!/usr/bin/env python3
"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-08-12
References: notebooks/counterparty_adverse_selection.ipynb (the notebook whose
pointer table this gate reads and whose comparisons it reads it against); the committed
*_results.json files of this tree, each of which names its own producer.

WHAT THE POINTER TABLE CLAIMS IS OUT OF REACH, THE NOTEBOOK MUST NOT BE COMPARING.

Why this gate exists, and it was measured rather than imagined. The reproduction
notebook carries, near its end, a table of the reported figures it does NOT recompute:
what each one shows, the script that produces it, and what it needs that the published
slice does not carry. The table is a promise to the reader that these figures are out of
reach here, and the reader has no way to test it.

It was written on 6 August. On 10 August three commits inside twenty-seven minutes
taught the notebook to rebuild three of the things the table lists -- the screening
table, the disagreement between the maker's cost and the counterparty's own profit, and
the identity-against-book comparison. Nobody opened the table. It has held the same
twenty-five rows across every commit since, and it now tells a reader that figures the
notebook recomputes in front of them cannot be recomputed here.

Nothing in this tree could have noticed. The table is prose in a markdown cell, and no
gate reads prose against behaviour. This one does.

WHAT IT BINDS TO. Not a name. Two gates of this tree have already gone silent because
they matched a name that later moved, so the question here is asked of what the notebook
DOES: the comparison function is found by its behaviour rather than by being called
`check`, the call sites of that function are read out of the syntax tree, and the value
each comparison is made against is resolved through the notebook's own namespace to an
address in its file of figures.

HOW A ROW IS TIED TO A COMPARISON, and this is the part that needed measuring. A row
names a script; the notebook compares values. Tying the two by the script is too wide,
and that is a fact about this table rather than a worry: three of its rows name
`mm_bakeoff.py` and all three are truthful, because the notebook compares two OTHER
values of that same run. Three more name `t1_toxicity_skew_backtest.py`, two of them
stale and the third truthful, because the figure it points at never travelled into the
notebook's expectations at all. One script, rows of opposite standing; no predicate keyed
on the script can separate them.

What separates them is the VALUE. The packer that builds the notebook's file of figures
lifts numbers out of the committed results files and computes none of its own -- its own
scope line says so, and the claim is measured here rather than taken: 224 of the 225
leaves under the compared groups stand in their source results file at the identical
value, the one exception being a quantile the packer types in beside them.
So a number is a name both sides can say, and it survives every rename this tree has
suffered: rename the key in the results file, rename the key in the file of figures,
rename the variable in the packer, and the number is still the number.

Therefore a row must carry the ADDRESS of its figure inside the results file its script
writes, spelled in backticks the way it already spells the script. That is asked only of
rows whose results file holds at least one compared value: 12 of the 25 rows today. The
other thirteen name scripts that reach the notebook's expectations not at all, and are
already verifiable as they stand.

A row with no address, whose file does hold compared values, is a finding in its own
right, and not a soft one. It is exactly the state the table is in now, and it is why
nobody could see that two of its rows had gone false. A judgement without an address
reads as settled work and closes the question without answering it, which is the same
reason a compliance verdict in this project is forbidden without one.

THREE QUESTIONS, each printing an expectation, a fact and a place when it goes over.

  RULE 1  The pointer table is there, and there is exactly one of it, with rows. Zero
          tables fails rather than passing quietly: a gate that says nothing when the
          thing it guards is absent has measured its own reach and not the tree.

  RULE 2  Every row points somewhere. The script it names is the producer of a results
          file present in this tree -- resolved by reading what each results file says
          about its OWN producer, not by matching the name against a directory listing
          -- and every address a row carries resolves inside that file.

  RULE 3  No row stands for a figure the notebook compares. Two ways to go over, kept
          apart because they are repaired differently:
            (a) the row's address resolves to a value the notebook compares;
            (b) the row carries no address while its results file holds compared values,
                so the row cannot be told apart from them.

THE THIRD OUTCOME. A matched value that carries few significant digits is reported as a
match and marked as weakly distinguished, rather than silently dropped. Dropping it would
be an error in the direction that passes: a stale row would go quiet because its figure
happened to be a round number. A boolean is the one thing left out of the join, and that
was measured rather than assumed -- the first repaired table tried against this gate came
back with findings on `False` standing beside `False`, because these results files hold
hundreds of flags and a boolean matches nearly everything. How many compared figures that
leaves out is printed. The rate at which an unrelated address of these same files happens
to hold a compared value is measured on the live tree and printed beside the verdict too,
so the reader knows what the join is worth.

WHAT THIS GATE IS BLIND TO, said out loud. It reads the script column and the backticked
addresses, and nothing else in the row: it cannot tell whether the sentence in the first
column describes the figure the address points at. It joins by value, so two distinct
quantities of one file holding the same number are indistinguishable to it, and a boolean
figure cannot be joined at all. An address naming a whole block rather than a leaf is
judged over every leaf under it, so such a row fires if any part of the block is compared.
And it is silent about figures the table does not mention at all -- a reported figure that
is neither recomputed nor listed here is a gap this gate does not measure.

Read-only over the repository. Every fixture the calibration builds goes to a scratch
directory of its own and the notebook is never opened for writing.

    uv run --no-project --with-requirements requirements.txt python3 \
        checks/chk_notebook_pointer_table.py
    uv run --no-project --with-requirements requirements.txt python3 \
        checks/chk_notebook_pointer_table.py --selftest
"""
import argparse
import ast
import glob
import json
import os
import re
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

OUT_JSON = os.path.join(HERE, "chk_notebook_pointer_table_results.json")

NOTEBOOK = os.path.join(ROOT, "notebooks",
                        "counterparty_adverse_selection.ipynb")
EXPECTED_JSON = os.path.join(ROOT, "notebooks", "notebook_expected.json")

# The names the file of figures is bound to inside the notebook. EXPECTED is what the
# generated cell assigns; every other name is discovered by following assignments, so a
# cell that renames it does not take this gate's sight away.
FIGURES_ROOT = "EXPECTED"

# The comparison function, as a LAST RESORT. The live one is found by what it does, and
# which of the two was used is printed and recorded: a gate matching a name the notebook
# no longer writes is a gate that has stopped asking anything.
COMPARATOR_CONTRACT = "check"

# What identifies the comparison function by behaviour: it takes a recomputed number and
# a reported one, decides agreement with a magnitude, and keeps the outcome in a list.
COMPARATOR_MIN_ARGS = 3

# A backticked token is a script when it ends this way. The table already spells its
# scripts in backticks, so no new convention is introduced by reading them.
SCRIPT_SUFFIX = ".py"

# How an address is written in a row: a backticked dotted path into the results file,
# with [i] for a position in a list. Anything backticked that is neither this nor a
# script is left alone, because a row is prose and may quote a word.
ADDRESS_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_|.\-]*(\[\d+\])?"
                        r"([.][A-Za-z0-9_|.\-]+(\[\d+\])?)*$")

# Below this many significant digits a numeric match is reported as weakly
# distinguished. It is NOT a floor that hides the match: an error that hides a finding
# passes through, and this gate would rather name a coincidence than miss a stale row.
WEAK_DIGITS = 6

# How far the resolver follows a name before giving up. A bound against a cycle, not a
# judgement about the notebook.
RESOLVE_DEPTH = 8

# Leaves of the file of figures that the packer types in rather than lifts: they belong
# to the recompute's settings, not to the reported figures, and no results file holds
# them. Named as a path fragment so the walk can say why it skipped them.
DECLARED_FRAGMENTS = ("._shared.", ".streams.")


# ----------------------------------------------------------------- reading the tree

def read_notebook(path):
    """The cells of a notebook as (index, cell_type, source), or an error string.

    A notebook that cannot be parsed is a finding rather than an empty list, because an
    empty list makes every rule below report zero and a zero over nothing reads on
    screen as agreement.
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


def read_json(path):
    """A JSON document, or None. Used where absence is answered by the caller."""
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def leaves(node, path=""):
    """Every scalar under a value, as (address, value).

    The address is spelled the way a row spells it, so the two can be compared without
    either side translating: dots between keys, [i] for a position in a list.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            step = f"{path}.{key}" if path else str(key)
            yield from leaves(value, step)
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from leaves(value, f"{path}[{i}]")
    else:
        yield path, node


def at_address(doc, address):
    """The subtree a row's address names, or None when it does not resolve.

    None means the address is wrong, and that is a finding: a pointer table whose
    pointers do not resolve sends the reader somewhere there is nothing to read.
    """
    node = doc
    for part in re.findall(r"[^.\[\]]+|\[\d+\]", address):
        if part.startswith("["):
            i = int(part[1:-1])
            if not isinstance(node, list) or i >= len(node):
                return None
            node = node[i]
        else:
            if not isinstance(node, dict) or part not in node:
                return None
            node = node[part]
    return node


def significant_digits(value):
    """How many digits a number carries, which is how distinguishable it is.

    A count of 50 and a share of 0.9 are held by dozens of unrelated addresses of these
    files; a markout of -1.4423007 is held by one. The gate reports both kinds of match
    and says which is which.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    text = repr(abs(value)).replace(".", "").replace("e", " ").split()[0].lstrip("0")
    return len(text.rstrip("0"))


# ------------------------------------------------- the producers, read off artifacts

def packer_inputs():
    """The results files the file of figures was built from, as it records them itself.

    WHY THIS IS ASKED AND NOT INFERRED FROM THE VALUES, and it was measured on the way
    to the answer. The first version of this gate decided that a results file reaches
    the notebook when one of its values equals a value the notebook compares. Every
    single file of this tree passed that test, including the three-contract run and the
    lead-lag probe, which the packer has never opened: 8 percent of the numeric leaves
    of these files happen to hold a compared value, because a fill floor of 50 and a
    quantile of 0.9 sit in dozens of unrelated places. The predicate was measuring
    coincidence and calling it reach.

    The exact answer is written in the artifact. The packer records every results file
    it opened, with its size and hash, and that record is what freshness is judged by
    everywhere else in this tree. So the question "can this file reach the notebook at
    all" is answered by reading it rather than by guessing from numbers, and the join by
    value is then only ever asked INSIDE a file that can.
    """
    doc = read_json(EXPECTED_JSON) or {}
    inputs = (doc.get("_meta") or {}).get("inputs") or []
    return {os.path.basename(i.get("name") or "") for i in inputs if i.get("name")}


def producers_in_tree():
    """{script basename: [results files it wrote]}, read from the files themselves.

    Every results file of this tree records the script that wrote it, so the map is a
    property of the artifacts rather than a guess from a directory listing. That matters
    here: the table names `t1_toxicity_skew_backtest.py` and the file it writes is called
    `t1_backtest_results.json`, and no rule about names connects those two.
    """
    out = {}
    for path in sorted(glob.glob(os.path.join(ROOT, "**", "*_results.json"),
                                 recursive=True)):
        doc = read_json(path)
        if not isinstance(doc, dict):
            continue
        script = (doc.get("_meta") or {}).get("producer", {}).get("script")
        if script:
            out.setdefault(os.path.basename(script), []).append(path)
    return out


# --------------------------------------------------------- RULE 1: finding the table

def pipe_rows(text):
    """The data rows of a pipe table in a markdown cell, header and rule dropped."""
    lines = [ln.strip() for ln in text.split("\n") if ln.strip().startswith("|")]
    rows = [ln for ln in lines if set(ln) - set("|-: ")]
    return rows[1:] if len(rows) > 1 else []


def looks_like_pointer_table(text):
    """True when a markdown cell holds a table whose rows point at scripts.

    Recognised by what the table DOES -- most of its rows name a script in backticks --
    rather than by the wording of its header, which is prose somebody may rewrite. The
    table is being rewritten as this gate is written, so keying on its heading would
    have made the gate silent on the day it shipped.
    """
    rows = pipe_rows(text)
    if not rows:
        return False
    with_script = sum(1 for r in rows if re.search(r"`[^`]+\.py`", r))
    return with_script * 2 >= len(rows)


def find_tables(cells):
    """(index, source) for every markdown cell holding a pointer table."""
    return [(i, src) for i, kind, src in cells
            if kind == "markdown" and looks_like_pointer_table(src)]


def rule1(cells, nb_error):
    """Findings for the presence and uniqueness of the pointer table."""
    rel = os.path.relpath(NOTEBOOK, ROOT)
    if nb_error:
        return [{"file": rel, "line": 0, "detail": nb_error, "source": "RULE 1"}], []
    tables = find_tables(cells)
    if len(tables) == 1 and pipe_rows(tables[0][1]):
        return [], tables
    if not tables:
        return [{
            "file": rel, "line": 0,
            "detail": (f"expected 1 markdown cell holding the pointer table and found "
                       f"0 among {sum(1 for c in cells if c[1] == 'markdown')} markdown "
                       f"cells. A table is recognised here by most of its rows naming a "
                       f"script in backticks. This fails rather than passing quietly: "
                       f"with no table there is nothing to compare against the "
                       f"notebook, and silence would read as agreement"),
            "source": "RULE 1"}], []
    if len(tables) > 1:
        return [{"file": f"{rel}#cell{i}", "line": 0,
                 "detail": (f"expected 1 pointer table, found {len(tables)}. Two tables "
                            f"of what the notebook does not recompute can disagree, and "
                            f"nothing says which one a reader is meant to believe"),
                 "source": "RULE 1"} for i, _src in tables], tables
    return [{"file": f"{rel}#cell{tables[0][0]}", "line": 0,
             "detail": "the pointer table holds no rows at all",
             "source": "RULE 1"}], tables


# ------------------------------------- what the notebook actually compares, by behaviour

def parsable(src):
    """A cell's source with its magic and shell lines commented out.

    A line opening with % or ! is not Python and ends the parse at the first one, hiding
    every call below it in the same cell.
    """
    return "\n".join("#" + ln if ln.lstrip()[:1] in ("%", "!") else ln
                     for ln in src.split("\n"))


def code_trees(cells):
    """[(cell index, syntax tree)] for every code cell that parses."""
    out = []
    for idx, kind, src in cells:
        if kind != "code":
            continue
        try:
            out.append((idx, ast.parse(parsable(src))))
        except SyntaxError:
            continue
    return out


def comparator_in_force(trees):
    """(name of the comparison function, where the name came from).

    Found by BEHAVIOUR: a function of the notebook that takes at least three arguments,
    decides agreement with a magnitude, and keeps what it decided in a list. Two gates of
    this tree went silent by matching a name that later moved, so the name is read off
    the notebook and the contract below is used only when the notebook holds no such
    function or holds several. Which of the two was used is printed, because a gate
    calling a function nobody defines has stopped asking anything.
    """
    found = []
    for _idx, tree in trees:
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if len(node.args.args) < COMPARATOR_MIN_ARGS:
                continue
            body = ast.dump(node)
            if "'abs'" in body and "'append'" in body:
                found.append(node.name)
    if len(set(found)) == 1:
        return found[0], "the notebook (found by what the function does)"
    if not found:
        return COMPARATOR_CONTRACT, ("contract (the notebook defines no function that "
                                     "compares two numbers and keeps the outcome)")
    return COMPARATOR_CONTRACT, (f"contract (the notebook defines {len(set(found))} "
                                 f"functions that look like the comparison: "
                                 f"{', '.join(sorted(set(found)))})")


def namespace(trees):
    """{name: [value nodes]} over the WHOLE notebook, which is how a notebook runs.

    Cells share one namespace: the alias is assigned in one cell and read in another,
    and the helper that compares is defined in one and called from a third. A resolver
    stopping at the cell boundary would resolve almost nothing here.

    Three bindings beyond plain assignment, each of which the notebook actually uses:
    a loop over a literal sequence binds its target to the members, a loop over anything
    else binds its target to the sequence itself (which is enough to reach the group the
    members come from), and a parameter binds to what the call sites pass.
    """
    env = {}
    funcs = {}
    for _idx, tree in trees:
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        env.setdefault(target.id, []).append(node.value)
                    elif isinstance(target, (ast.Tuple, ast.List)):
                        for el in target.elts:
                            if isinstance(el, ast.Name):
                                env.setdefault(el.id, []).append(node.value)
            elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
                if isinstance(node.target, ast.Name) and node.value is not None:
                    env.setdefault(node.target.id, []).append(node.value)
            elif isinstance(node, (ast.For, ast.comprehension)):
                iter_node = node.iter
                members = (list(iter_node.elts)
                           if isinstance(iter_node, (ast.List, ast.Tuple, ast.Set))
                           else [iter_node])
                targets = ([node.target] if isinstance(node.target, ast.Name)
                           else [e for e in getattr(node.target, "elts", [])
                                 if isinstance(e, ast.Name)])
                for i, tgt in enumerate(targets):
                    for member in members:
                        if isinstance(member, (ast.Tuple, ast.List)) and \
                                len(targets) == len(member.elts):
                            env.setdefault(tgt.id, []).append(member.elts[i])
                        else:
                            env.setdefault(tgt.id, []).append(member)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                funcs[node.name] = node
    # Parameters take what the call sites pass. Without this the eighteen comparisons of
    # the classifier's table resolve to nothing at all, because they are made inside a
    # helper and the group they read is handed in.
    for _idx, tree in trees:
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
                continue
            target = funcs.get(node.func.id)
            if target is None:
                continue
            params = [a.arg for a in target.args.args]
            for name, value in zip(params, node.args):
                env.setdefault(name, []).append(value)
            for kw in node.keywords:
                if kw.arg in params:
                    env.setdefault(kw.arg, []).append(kw.value)
    return env, funcs


def figure_roots(env):
    """Every name bound to the file of figures, the agreed one and its aliases."""
    roots = {FIGURES_ROOT}
    for _round in range(RESOLVE_DEPTH):
        grew = False
        for name, values in env.items():
            if name in roots:
                continue
            for value in values:
                if isinstance(value, ast.Name) and value.id in roots:
                    roots.add(name)
                    grew = True
                    break
        if not grew:
            break
    return roots


def resolve_paths(node, env, roots, depth=0, seen=frozenset()):
    """The addresses in the file of figures an expression can descend from.

    An address is a tuple of segments, and a segment is either a key this gate could
    read or None. None is a WILDCARD and is honest about what it means: the expression
    reaches some member of that group and the gate cannot say which, so everything under
    it is taken as reached. Widening at the wildcard is the safe direction here -- the
    dangerous error is the one that lets a stale row through, not the one that names a
    row for a reader to look at.
    """
    if depth > RESOLVE_DEPTH:
        return set()
    if isinstance(node, ast.Subscript):
        base = node.value
        if isinstance(base, ast.Name) and base.id in roots:
            key = node.slice
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                return {(key.value,)}
            return {(None,)}
        prefixes = resolve_paths(base, env, roots, depth + 1, seen)
        if not prefixes:
            return set()
        key = node.slice
        if isinstance(key, ast.Constant) and not isinstance(key.value, bool):
            step = (key.value,)
        else:
            step = tuple(_literal_keys(key, env, roots, depth, seen)) or (None,)
        return {p + (s,) for p in prefixes for s in step}
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "get":
            base = func.value
            args = node.args
            key = args[0] if args else None
            if isinstance(base, ast.Name) and base.id in roots:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    return {(key.value,)}
                return {(None,)}
            prefixes = resolve_paths(base, env, roots, depth + 1, seen)
            if isinstance(key, ast.Constant):
                return {p + (key.value,) for p in prefixes}
            return {p + (None,) for p in prefixes}
        out = set()
        for arg in list(node.args) + [k.value for k in node.keywords]:
            out |= resolve_paths(arg, env, roots, depth + 1, seen)
        return out
    if isinstance(node, ast.Name):
        if node.id in seen:
            return set()
        out = set()
        for value in env.get(node.id, ()):
            out |= resolve_paths(value, env, roots, depth + 1, seen | {node.id})
        return out
    if isinstance(node, (ast.BinOp, ast.UnaryOp, ast.IfExp, ast.Tuple, ast.List)):
        out = set()
        for child in ast.iter_child_nodes(node):
            out |= resolve_paths(child, env, roots, depth + 1, seen)
        return out
    if isinstance(node, ast.Attribute):
        return resolve_paths(node.value, env, roots, depth + 1, seen)
    return set()


def _literal_keys(node, env, roots, depth, seen):
    """The strings or numbers a subscript key can take, when that can be decided."""
    if isinstance(node, ast.Constant):
        return {node.value}
    if isinstance(node, ast.Name):
        if node.id in seen or depth > RESOLVE_DEPTH:
            return set()
        out = set()
        for value in env.get(node.id, ()):
            got = _literal_keys(value, env, roots, depth + 1, seen | {node.id})
            if not got:
                return set()
            out |= got
        return out
    if isinstance(node, ast.JoinedStr):
        out = {""}
        for part in node.values:
            got = _literal_keys(part, env, roots, depth + 1, seen)
            if not got:
                return set()
            out = {a + str(b) for a in out for b in got}
        return out
    if isinstance(node, ast.FormattedValue):
        return _literal_keys(node.value, env, roots, depth + 1, seen)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _literal_keys(node.left, env, roots, depth + 1, seen)
        right = _literal_keys(node.right, env, roots, depth + 1, seen)
        if not left or not right:
            return set()
        return {str(a) + str(b) for a in left for b in right}
    return set()


def expand(paths, figures):
    """Concrete leaf addresses of the file of figures the resolved paths cover.

    A wildcard segment expands to every key at that level, which is what makes the
    widening explicit rather than hidden: the gate says it reached the group and not
    which member, and takes the group.
    """
    out = {}
    for path in paths:
        nodes = [("", figures)]
        for segment in path:
            step = []
            for prefix, node in nodes:
                if isinstance(node, dict):
                    keys = list(node) if segment is None else (
                        [segment] if segment in node else [])
                    for key in keys:
                        step.append((f"{prefix}.{key}" if prefix else str(key),
                                     node[key]))
                elif isinstance(node, list):
                    idx = range(len(node)) if segment is None else (
                        [segment] if isinstance(segment, int) and
                        -len(node) <= segment < len(node) else [])
                    for i in idx:
                        step.append((f"{prefix}[{i}]", node[i]))
            nodes = step
        for prefix, node in nodes:
            for address, value in leaves(node, prefix):
                out[address] = value
    return out


def compared_figures(cells):
    """(address -> value) for every figure the notebook compares, plus what it read.

    Returns the map, the comparator's name, where that name came from, and how many call
    sites were read. The count of call sites is what says a silence was taken over
    something: no findings and no call sites means nothing was measured.
    """
    trees = code_trees(cells)
    name, name_from = comparator_in_force(trees)
    env, _funcs = namespace(trees)
    roots = figure_roots(env)
    figures = read_json(EXPECTED_JSON) or {}

    # A list rather than a set, so the figures keep the order their comparisons appear
    # in. The calibration then builds its firing case out of the FIRST computing cell,
    # which is where a reader meets the notebook.
    paths, n_calls, n_unresolved = [], 0, 0
    for _idx, tree in trees:
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == name):
                continue
            n_calls += 1
            reported = node.args[2] if len(node.args) > 2 else None
            for kw in node.keywords:
                if kw.arg == "reported":
                    reported = kw.value
            if reported is None:
                n_unresolved += 1
                continue
            got = resolve_paths(reported, env, roots)
            if got:
                paths.extend(p for p in sorted(got, key=repr) if p not in paths)
            else:
                # A comparison against something that is not a figure of the file at
                # all -- the notebook compares one of its rebuilds against a constant,
                # and against a file of its own. Counted, not folded into either answer.
                n_unresolved += 1
    values = expand(paths, figures)
    values = {a: v for a, v in values.items()
              if not any(f in f".{a}." for f in DECLARED_FRAGMENTS)}
    return values, name, name_from, n_calls, n_unresolved, len(roots)


# ---------------------------------------------------------- RULE 2 and 3: the rows

def row_scripts(row):
    """Scripts a row names, in backticks."""
    return [t for t in re.findall(r"`([^`]+)`", row) if t.endswith(SCRIPT_SUFFIX)]


def row_addresses(row):
    """Addresses a row names, in backticks: anything backticked that is not a script.

    A row is prose and may quote a word, so a backticked token has to look like an
    address before it is treated as one. What it must NOT do is quietly drop a token it
    does not understand, because that would let a wrong address pass as no address.
    """
    good, bad = [], []
    for token in re.findall(r"`([^`]+)`", row):
        if token.endswith(SCRIPT_SUFFIX):
            continue
        (good if ADDRESS_RE.match(token) else bad).append(token)
    return good, bad


def rows_of(tables):
    """[(cell index, row number within the table, row text)] over the found tables."""
    out = []
    for idx, src in tables:
        for n, row in enumerate(pipe_rows(src), start=1):
            out.append((idx, n, row))
    return out


def judge_rows(rows, producers, compared, reachable):
    """Findings for RULE 2 and RULE 3, and the counts each was taken over.

    Every result of a row is one of five, and they are kept apart because they are
    repaired differently: the script does not resolve; the address does not resolve; the
    address names a compared figure; the row has no address while its file is one the
    packer reads; or the row is answered.

    `reachable` is the set of results files the file of figures was built from. A row
    whose file is not among them is answered as it stands: nothing of that run can be a
    figure the notebook compares, so no address is asked of it and no value of it is
    joined. That is what keeps the join from reporting a coincidence in a file the
    notebook has never seen.
    """
    rel = os.path.relpath(NOTEBOOK, ROOT)
    # A boolean is left out of the join, and this was measured rather than assumed. The
    # first repaired table tried against this gate came back with findings on `False`
    # standing at one address and `False` standing at another: the study's results files
    # hold hundreds of flags, so a boolean matches nearly everything and the join stops
    # being a join. Numbers stay in whatever their precision, because dropping a
    # low-precision match would be an error in the direction that passes.
    compared_values = {}
    n_boolean = 0
    for address, value in compared.items():
        if isinstance(value, bool):
            n_boolean += 1
            continue
        compared_values.setdefault(repr(value), []).append(address)

    r2, r3, weak = [], [], []
    n_rows = n_answered = n_needs_address = 0
    for cell_idx, n, row in rows:
        n_rows += 1
        scripts = row_scripts(row)
        where = f"{rel}#cell{cell_idx}"
        if not scripts:
            r2.append({"file": where, "line": n,
                       "detail": ("this row names no script in backticks, so there is "
                                  "no results file to resolve its figure in and no way "
                                  "to test what it claims"),
                       "source": "RULE 2"})
            continue
        addresses, malformed = row_addresses(row)
        for token in malformed:
            r2.append({"file": where, "line": n,
                       "detail": (f"the backticked token {token!r} is neither a script "
                                  f"nor an address this gate can resolve. It is "
                                  f"reported rather than ignored: a token silently "
                                  f"dropped would let a wrong address pass as none"),
                       "source": "RULE 2"})
        for script in scripts:
            base = os.path.basename(script)
            files = producers.get(base) or []
            if not files:
                r2.append({"file": where, "line": n,
                           "detail": (f"no results file in this tree names {base} as "
                                      f"its producer, so the row points a reader at a "
                                      f"script whose output they cannot open. The map "
                                      f"is read from what each results file says about "
                                      f"its own producer, not from a directory listing"),
                           "source": "RULE 2"})
                continue
            doc = read_json(files[0]) or {}
            fname = os.path.basename(files[0])
            # RULE 2 is asked of every row, reachable or not: an address that resolves
            # nowhere is a broken instruction whatever the file turns out to be.
            resolved = []
            for address in addresses:
                node = at_address(doc, address)
                if node is None:
                    r2.append({"file": where, "line": n,
                               "detail": (f"the address {address!r} does not resolve "
                                          f"inside {fname}, the file {base} writes. A "
                                          f"pointer that does not resolve sends a "
                                          f"reader to a place with nothing in it"),
                               "source": "RULE 2"})
                    continue
                resolved.append((address, node))
            if fname not in reachable:
                # The file of figures was never built from this run, so no value of it
                # can be a figure the notebook compares. The row is answered as it
                # stands: no address is asked of it, and none of its values is joined,
                # which is what keeps a coincidence in an unread file from being
                # reported as reach.
                n_answered += 1
                continue
            if not addresses:
                n_needs_address += 1
                r3.append({
                    "file": where, "line": n,
                    "detail": (f"this row carries no address, and {fname} is one of the "
                               f"{len(reachable)} results files "
                               f"{os.path.relpath(EXPECTED_JSON, ROOT)} was built from, "
                               f"so some of its figures are among the "
                               f"{len(compared)} the notebook compares. The row cannot "
                               f"be told apart from those, which is exactly the state "
                               f"that let three commits in twenty-seven minutes falsify "
                               f"two rows of this table with nothing noticing. Name the "
                               f"address of this row's figure inside {fname}, in "
                               f"backticks, the way the row already names the script"),
                    "source": "RULE 3(b)"})
                continue
            n_answered += 1
            for address, node in resolved:
                for leaf_address, value in leaves(node, address):
                    if isinstance(value, bool):
                        continue
                    at = compared_values.get(repr(value))
                    if not at:
                        continue
                    digits = significant_digits(value)
                    named = leaf_address.rsplit(".", 1)[-1]
                    agrees = any(a.rsplit(".", 1)[-1] == named for a in at)
                    r3.append({
                        "file": where, "line": n,
                        "detail": (f"{leaf_address} of "
                                   f"{os.path.basename(files[0])} holds {value!r}, and "
                                   f"the notebook compares that same value at "
                                   f"{at[0]} of "
                                   f"{os.path.relpath(EXPECTED_JSON, ROOT)}. The row "
                                   f"tells a reader this figure cannot be rebuilt here "
                                   f"while the notebook rebuilds it in front of them"
                                   + ("; the two leaves carry the same name, which the "
                                      "packer lifts them by"
                                      if agrees else
                                      "; the two leaves are named differently, which "
                                      "the packer does where it renames on the way")
                                   + ("" if digits >= WEAK_DIGITS else
                                      f"; the value carries {digits} significant "
                                      f"digits, so this match is weakly distinguished "
                                      f"and is reported rather than dropped, because a "
                                      f"dropped match is a stale row going quiet")),
                        "source": "RULE 3(a)"})
                    if digits < WEAK_DIGITS:
                        weak.append(leaf_address)
    return r2, r3, {"n_rows": n_rows, "n_answered": n_answered,
                    "n_needs_address": n_needs_address, "n_weak_matches": len(weak),
                    "n_boolean_not_joinable": n_boolean}


def coincidence_rate(rows, producers, compared, reachable):
    """How often an unrelated address of these files happens to hold a compared value.

    The join here is by value, so this is what the join is worth, and it is measured on
    the live tree rather than assumed. Printed beside the verdict: a membership test
    whose false-match rate nobody measured is a test whose zero means nothing.
    """
    compared_values = {repr(v) for v in compared.values()
                       if not isinstance(v, bool)}
    files = set()
    for _idx, _n, row in rows:
        for script in row_scripts(row):
            for path in producers.get(os.path.basename(script)) or []:
                if os.path.basename(path) in reachable:
                    files.add(path)
    total = hits = 0
    for path in sorted(files):
        doc = read_json(path)
        if doc is None:
            continue
        for _address, value in leaves(doc):
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                continue
            total += 1
            hits += repr(value) in compared_values
    return total, hits, len(files)


# ------------------------------------------------------------------- calibration

def live_notebook_doc():
    """The real notebook, from disk and then from git. Never written to.

    The working copy may be part way through a write, so an unreadable notebook on disk
    is not a reason for the calibration to fail: the last committed version is the same
    real notebook and is what the fixtures are then built from.
    """
    doc = read_json(NOTEBOOK)
    if doc is not None:
        return doc, "the working tree"
    rel = os.path.relpath(NOTEBOOK, ROOT)
    out = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=ROOT,
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError("the calibration has no real notebook to build a fixture "
                           "from: the working tree copy will not parse and git has no "
                           "committed copy either")
    return json.loads(out.stdout), "git HEAD"


def as_markdown_cell(text, cell_id):
    """A markdown cell holding this text, with the line endings a notebook keeps.

    The line endings are the point. A notebook stores source as a list of lines each
    ending in a newline, and a list written without them joins back into one physical
    line, which no table survives.
    """
    lines = text.split("\n")
    source = [ln + "\n" for ln in lines[:-1]] + [lines[-1]]
    return {"cell_type": "markdown", "id": cell_id, "metadata": {}, "source": source}


TABLE_HEAD = ("| What it shows | Checked by | What it needs that the published slice "
              "does not carry |\n|---|---|---|")


def fixture_doc(doc, rows, tables=1):
    """The real notebook with its pointer table replaced by the given rows.

    Built from the live notebook rather than from an invented one, because a fixture
    that does not look like the real case certifies nothing: a gate of this tree once
    passed its own calibration on an invented fixture and then read zero through a live
    file. Everything else in the notebook survives, including every comparison, which is
    the half of the question the fixture must not disturb.
    """
    doc = json.loads(json.dumps(doc))
    kept, first = [], None
    for cell in doc.get("cells") or []:
        src = cell.get("source")
        text = "".join(src) if isinstance(src, list) else str(src or "")
        if cell.get("cell_type") == "markdown" and looks_like_pointer_table(text):
            if first is None:
                first = len(kept)
            continue
        kept.append(cell)
    if first is None:
        raise RuntimeError("the calibration found no pointer table in the real "
                           "notebook, so it has no place to build the fixture at")
    made = []
    if rows is not None:
        body = "\n".join(TABLE_HEAD.split("\n") + list(rows))
        for i in range(tables):
            made.append(as_markdown_cell(body, f"ptrtable{i}"))
    doc["cells"] = kept[:first] + made + kept[first:]
    return doc


def make_row(what, script, needs, address=None):
    """One row in the shape the table writes them."""
    subject = f"{what}" + (f", at `{address}`" if address else "")
    return f"| {subject} | `{script}` | {needs} |"


BUILT = []


def write_fixture(tmp, name, doc):
    path = os.path.join(tmp, name)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)
    BUILT.append(name)
    return path


def ask(path, producers, reachable):
    """The three questions over one notebook, as their findings."""
    cells, nb_error = read_notebook(path)
    s1, tables = rule1(cells or [], nb_error)
    compared, _name, _from, _calls, _unres, _roots = compared_figures(cells or [])
    s2, s3, counts = judge_rows(rows_of(tables), producers, compared, reachable)
    return s1, s2, s3, counts


def doc_cells(doc):
    """A doc's cells in the shape the predicates read."""
    return [(i, c.get("cell_type"),
             "".join(c.get("source") or []) if isinstance(c.get("source"), list)
             else str(c.get("source") or ""))
            for i, c in enumerate(doc.get("cells") or [])]


def pick_cases(doc, producers, reachable):
    """The live cases the calibration needs, all derived from the tree.

    A calibration case anchored on a particular row erases itself the day that row is
    rewritten, and this table is being rewritten as this gate is written. So nothing
    here quotes a row: the silent scripts are every script the table names whose results
    file the packer has never read, and the firing one carries a figure the notebook
    compares, found back in the file that holds it.
    """
    cells = doc_cells(doc)
    compared, _name, _from, _calls, _unres, _roots = compared_figures(cells)
    if not compared:
        raise RuntimeError("the notebook compares no figure this gate can resolve, so "
                           "there is no firing case to build")
    compared_values = {repr(v) for v in compared.values()}

    silent = []
    for _idx, _n, row in rows_of(find_tables(cells)):
        for script in row_scripts(row):
            base = os.path.basename(script)
            files = producers.get(base) or []
            if files and os.path.basename(files[0]) not in reachable:
                silent.append((base, os.path.basename(files[0])))
    # The firing case: a figure the notebook compares, found back in the results file
    # that holds it, with an uncompared address of the same file beside it. Only files
    # the packer actually read are eligible, so the pair differs by the address alone.
    firing = None
    for address, value in compared.items():
        if significant_digits(value) < WEAK_DIGITS:
            continue
        for base, files in sorted(producers.items()):
            if os.path.basename(files[0]) not in reachable:
                continue
            doc_here = read_json(files[0])
            if not isinstance(doc_here, dict):
                continue
            named = [a for a, v in leaves(doc_here) if repr(v) == repr(value)]
            if not named:
                continue
            # Not out of _meta: the fixture has to look like a row about a figure of
            # the run, and the artifact's own bookkeeping is not one.
            spare = next((a for a, v in leaves(doc_here)
                          if repr(v) not in compared_values
                          and not a.startswith("_meta")
                          and isinstance(v, float) and not isinstance(v, bool)), None)
            if spare is None:
                continue
            firing = (base, named[0], spare, address)
            break
        if firing:
            break
    if not silent:
        raise RuntimeError("every script the table names writes a file the packer "
                           "reads, so the silent case cannot be built from this tree")
    if firing is None:
        raise RuntimeError("no compared figure of the notebook could be found back in "
                           "the results file that holds it, so the firing case cannot "
                           "be built")
    return silent, firing


def calibrate(producers, reachable):
    """Two opposite cases for every question, on the live tree.

    One reference case cannot tell a predicate that is too wide from one that is too
    narrow apart, so each question gets a case where it must stay silent and one where
    it must fire. The pair that matters most is the last: one row, one script, one file,
    the address moved from a figure the notebook compares to one it does not. Those two
    differ by nothing else, and a predicate that cannot separate them is either useless
    or unusable.
    """
    doc, doc_from = live_notebook_doc()
    silent, (fire_script, fire_address, spare_address, figure_address) = pick_cases(
        doc, producers, reachable)
    lines = []
    tmp = tempfile.mkdtemp(prefix="chk_nb_ptr_")
    try:
        # MUST STAY SILENT, and over the whole live population rather than one pick. A
        # row naming a script whose results file the packer has never opened cannot be
        # about a compared figure, so it needs no address and no value of it is joined.
        quiet_rows = [make_row(f"what the {base} run reports", base,
                               "A contract or a venue outside the published slice")
                      for base, _f in silent]
        quiet = write_fixture(tmp, "quiet.ipynb", fixture_doc(doc, quiet_rows))
        s1, s2, s3, counts = ask(quiet, producers, reachable)
        assert not s1, f"RULE 1 fires on one pointer table and one only: {s1}"
        assert not s2, f"RULE 2 fires on rows whose scripts this tree has: {s2}"
        assert not s3, (f"RULE 3 fires on {len(silent)} row(s) whose results files the "
                        f"packer never read: {s3}")
        assert counts["n_answered"] == len(silent), (
            f"the silent rows are not all counted as answered: {counts}")
        lines.append(f"the silent case is {len(silent)} row(s) naming "
                     f"{', '.join(sorted({b for b, _f in silent}))}, whose results "
                     f"files are not among the {len(reachable)} the packer reads")

        # Every case below carries one of these silent rows as ballast, so each case
        # row is judged beside a neighbour rather than alone in a table of one.
        ballast = quiet_rows[:1]

        # ...and the silence is not vacuous. The notebook must still be comparing
        # something, or a silent RULE 3 says nothing at all about a notebook that does.
        cells, _err = read_notebook(quiet)
        compared, cname, cfrom, ncalls, _unres, nroots = compared_figures(cells)
        assert ncalls >= 1 and compared, (
            "the fixture notebook compares nothing this gate can resolve, so RULE 3 "
            "staying silent proves nothing")
        assert "notebook" in cfrom, (
            f"the comparison function was taken from the written contract rather than "
            f"found in the notebook ({cfrom}), so the calibration measured the fallback")
        lines.append(f"the silent case still makes {ncalls} comparisons over "
                     f"{len(compared)} figures, through {cname}() found by what it does, "
                     f"and {nroots} name(s) bound to the file of figures")

        # MUST FIRE, RULE 3(b). The same row for a script whose file DOES hold compared
        # figures, with no address: it cannot be told apart from them.
        blind_row = make_row("what this run reports", fire_script, "the full tape")
        # Named for the case rather than for the word, because the other notebook gate
        # writes a fixture of its own for a different kind of blindness -- a fetch whose
        # arguments come from the environment -- and both were called blind.ipynb. The
        # build reads a written name out of the syntax tree without caring which
        # directory it lands in, so one name written by two scripts is one artifact with
        # two producers, which is a thing this tree forbids. The other fourteen fixture
        # names across the two gates are already distinct; this one was the exception.
        blind = write_fixture(tmp, "blind_row.ipynb",
                              fixture_doc(doc, [blind_row] + ballast))
        s1, s2, s3, counts = ask(blind, producers, reachable)
        assert not s1 and not s2, f"the addressless row disturbed RULE 1 or RULE 2: {s2}"
        assert len(s3) == 1 and s3[0]["source"] == "RULE 3(b)", (
            f"an addressless row for {fire_script} is not reported: {s3}")

        # MUST FIRE, RULE 3(a). The same row carrying the address of the figure the
        # notebook compares in its first computing cell.
        named_row = make_row("what this run reports", fire_script, "the full tape",
                             address=fire_address)
        named = write_fixture(tmp, "named.ipynb",
                              fixture_doc(doc, [named_row] + ballast))
        s1, s2, s3, _counts = ask(named, producers, reachable)
        assert not s1 and not s2, f"the named row disturbed RULE 1 or RULE 2: {s2}"
        assert len(s3) == 1 and s3[0]["source"] == "RULE 3(a)", (
            f"a row addressing the compared figure {fire_address} is not reported: {s3}")
        assert figure_address in s3[0]["detail"], (
            f"the finding does not name where the notebook compares it: {s3[0]}")

        # MUST STAY SILENT, and this is the pair that separates too wide from too
        # narrow. The same row, the same script, the same file: only the address moves,
        # to a figure of that file the notebook does not compare.
        spare_row = make_row("what this run reports", fire_script, "the full tape",
                             address=spare_address)
        spare = write_fixture(tmp, "spare.ipynb",
                              fixture_doc(doc, [spare_row] + ballast))
        s1, s2, s3, _counts = ask(spare, producers, reachable)
        assert not s1 and not s2 and not s3, (
            f"a row addressing {spare_address}, which the notebook does not compare, is "
            f"reported: {s3 or s2}")
        lines.append(f"the firing pair is one row for {fire_script}: at {fire_address} "
                     f"it fires, because the notebook compares that value at "
                     f"{figure_address}; at {spare_address} of the same file it is "
                     f"silent; and with no address at all it fires for being "
                     f"indistinguishable")

        # MUST FIRE, RULE 2, in both of its directions: a script no results file claims,
        # and an address that does not resolve in the file its script writes.
        ghost = write_fixture(tmp, "ghost.ipynb", fixture_doc(
            doc, [make_row("what this run reports", "no_such_producer.py",
                           "the tape")] + ballast))
        _s1, s2, _s3, _c = ask(ghost, producers, reachable)
        assert len(s2) == 1 and "names" in s2[0]["detail"], (
            f"a script no results file claims is not reported: {s2}")
        nowhere = write_fixture(tmp, "nowhere.ipynb", fixture_doc(
            doc, [make_row("what this run reports", fire_script, "the tape",
                           address="no.such.address")] + ballast))
        _s1, s2, _s3, _c = ask(nowhere, producers, reachable)
        assert len(s2) == 1 and "does not resolve" in s2[0]["detail"], (
            f"an address that resolves nowhere is not reported: {s2}")

        # MUST FIRE, RULE 1, in both of its two directions.
        gone = write_fixture(tmp, "gone.ipynb", fixture_doc(doc, None))
        s1, _s2, s3, counts = ask(gone, producers, reachable)
        assert len(s1) == 1 and "found 0" in s1[0]["detail"], (
            f"an absent pointer table is not reported: {s1}")
        assert counts["n_rows"] == 0 and not s3, (
            "RULE 3 reports findings over a table that is not there")
        twice = write_fixture(tmp, "twice.ipynb",
                              fixture_doc(doc, quiet_rows, tables=2))
        s1, _s2, _s3, _c = ask(twice, producers, reachable)
        assert len(s1) == 2, f"two pointer tables are not reported: {s1}"
        lines.append(f"RULE 1 fires on zero tables and on two, RULE 2 on a script no "
                     f"results file claims and on an address resolving nowhere")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    lines.insert(0, f"calibration: {len(BUILT)} fixtures built from the real notebook "
                    f"read out of {doc_from}, each one the whole notebook with its "
                    f"pointer table replaced")
    return " | ".join(lines)


# ------------------------------------------------------------------------- the run

def main():
    parser = argparse.ArgumentParser(
        description="what the pointer table calls out of reach, the notebook must not "
                    "be comparing")
    parser.add_argument("--selftest", action="store_true",
                        help="run the calibration only and exit non-zero if any case "
                             "of it fails")
    args = parser.parse_args()

    started = artifact.start_clock()
    producers = producers_in_tree()
    reachable = packer_inputs()
    try:
        calibration = calibrate(producers, reachable)
    except AssertionError as exc:
        print("CALIBRATION FAILED. This gate has not been shown to work today, so "
              "nothing it says about the pointer table can be relied on.")
        print(f"  {exc}")
        return 2
    except RuntimeError as exc:
        print(f"CALIBRATION COULD NOT RUN: {exc}")
        return 2
    print(calibration)
    if args.selftest:
        return 0

    cells, nb_error = read_notebook(NOTEBOOK)
    s1, tables = rule1(cells or [], nb_error)
    compared, cname, cfrom, n_calls, n_unresolved, n_roots = compared_figures(cells or [])
    rows = rows_of(tables)
    s2, s3, counts = judge_rows(rows, producers, compared, reachable)
    n_leaves, n_hits, n_files = coincidence_rate(rows, producers, compared, reachable)

    rel = os.path.relpath(NOTEBOOK, ROOT)
    print("=" * 78)
    print("  WHAT THE POINTER TABLE CALLS OUT OF REACH, THE NOTEBOOK MUST NOT COMPARE")
    print("=" * 78)
    print(f"  notebook                 : {rel}"
          + (f", {len(cells)} cells" if cells else " (unreadable)"))
    print(f"  pointer table            : {len(tables)} found, "
          f"{counts['n_rows']} row(s)")
    print(f"  comparison function      : {cname}(), from {cfrom}")
    print(f"  figures it compares      : {len(compared)} leaf address(es) of "
          f"{os.path.relpath(EXPECTED_JSON, ROOT)}, over {n_calls} call site(s)")
    print(f"  results files in the tree: {len(producers)} producer(s) named by their "
          f"own artifacts")
    print(f"  RULE 1 the table is there: {len(s1)} finding(s)")
    print(f"  RULE 2 the rows point    : {len(s2)} finding(s) over {counts['n_rows']} "
          f"row(s)")
    print(f"  RULE 3 none is compared  : {len(s3)} finding(s); "
          f"{counts['n_answered']} row(s) answered, {counts['n_needs_address']} "
          f"carrying no address while their file holds compared figures")
    # The three states of the instrument, printed whether or not they are empty. An
    # empty answer from a measuring instrument is a third state and not a synonym for a
    # healthy one.
    print(f"  ...comparisons not resolved to a figure: {n_unresolved} of {n_calls}")
    print(f"  ...matches on a value under {WEAK_DIGITS} significant digits: "
          f"{counts['n_weak_matches']}")
    print(f"  ...compared figures left out of the join for being boolean: "
          f"{counts['n_boolean_not_joinable']} of {len(compared)}")
    print(f"  ...the join by value, measured: {n_hits} of {n_leaves} numeric leaves in "
          f"the {n_files} results file(s) these rows name hold a compared value "
          f"({n_hits / max(n_leaves, 1):.2%})")

    verdict = "PASS" if not (s1 or s2 or s3) else "FAIL"
    artifact.write(
        os.path.basename(OUT_JSON),
        {"verdict": verdict,
         "comparator": cname,
         "comparator_read_from": cfrom,
         "n_figure_root_names": n_roots,
         "n_rule1_table_present": len(s1),
         "n_rule2_rows_point_somewhere": len(s2),
         "n_rule3_row_is_compared": len(s3),
         "n_rows": counts["n_rows"],
         "n_rows_answered": counts["n_answered"],
         "n_rows_without_address": counts["n_needs_address"],
         "n_weak_matches": counts["n_weak_matches"],
         "n_boolean_not_joinable": counts["n_boolean_not_joinable"],
         "n_comparison_call_sites": n_calls,
         "n_comparisons_not_resolved": n_unresolved,
         "n_compared_figures": len(compared),
         "compared_figures": sorted(compared),
         "coincidence_numeric_leaves": n_leaves,
         "coincidence_hits": n_hits,
         "coincidence_files": n_files,
         "notebook_error": nb_error,
         "findings": s1 + s2 + s3,
         "calibration": calibration},
        script=__file__,
        inputs=[NOTEBOOK, EXPECTED_JSON],
        scope={
            "population": (f"{counts['n_rows']} rows of the pointer table of {rel}, "
                           f"against {len(compared)} figures the notebook compares"),
            "window": ("n/a: this gate compares a claim against behaviour as both "
                       "stand now, and reads no market data"),
            "coins": "n/a: this gate reads figures already computed, not market data",
        },
        started=started,
        extra_meta={"comparator_contract": COMPARATOR_CONTRACT,
                    "figures_root": FIGURES_ROOT,
                    "weak_match_digits": WEAK_DIGITS,
                    "declared_fragments": list(DECLARED_FRAGMENTS)},
    )
    print(f"  results -> {os.path.basename(OUT_JSON)}")

    return report_gate(
        [{"name": "the pointer table is present exactly once, with rows",
          "permitted": 0,
          "found": len(s1),
          "assumption": ("the notebook carries one table of the reported figures it "
                         "does not recompute. Zero tables fails as loudly as two, "
                         "because with no table there is nothing to compare against "
                         "the notebook's behaviour and silence would read as health"),
          "method": ("every markdown cell is read for a pipe table most of whose rows "
                     "name a script in backticks, which is what such a table DOES "
                     "rather than what its heading says"),
          "note": ("going over means the promise this gate exists to test is either "
                   "absent or duplicated"),
          "sites": s1},
         {"name": "every row points somewhere a reader can open",
          "permitted": 0,
          "found": len(s2),
          "assumption": ("a row sends the reader to a script and, where it names one, "
                         "to an address inside that script's results file. Both have "
                         "to be there, or the row is an instruction that cannot be "
                         "followed"),
          "method": (f"the script of each row is looked up in a map built by reading "
                     f"what every results file of this tree says about its OWN "
                     f"producer, {len(producers)} of them; the address is then resolved "
                     f"inside that file leaf by leaf"),
          "note": ("going over means a row names a script or an address this tree does "
                   "not have, which is what a rename leaves behind"),
          "sites": s2},
         {"name": "no row stands for a figure the notebook compares",
          "permitted": 0,
          "found": len(s3),
          "assumption": ("the table is a promise that these figures are out of reach "
                         "here. A figure the notebook rebuilds and compares in front of "
                         "the reader is not out of reach, and a row that cannot be told "
                         "apart from such a figure is not a promise anyone can test"),
          "method": (f"the notebook's comparison function is found by what it does, its "
                     f"{n_calls} call sites are read, and the value each comparison is "
                     f"made against is resolved through the whole notebook namespace to "
                     f"{len(compared)} leaf addresses of "
                     f"{os.path.relpath(EXPECTED_JSON, ROOT)}. A row's address is "
                     f"resolved in its own results file and joined to those by VALUE, "
                     f"which is the one name both sides can say: the packer lifts "
                     f"numbers and computes none, so a rename on either side leaves the "
                     f"join standing. {n_hits} of {n_leaves} numeric leaves of the files "
                     f"these rows name hold a compared value, which is what the join is "
                     f"worth"),
          "note": ("going over means the notebook and its own table disagree about what "
                   "the notebook does, which is the state that let three commits in "
                   "twenty-seven minutes falsify two rows with nothing noticing"),
          "sites": s3}],
        OUT_JSON,
        inputs={"notebook": rel,
                "figures": os.path.relpath(EXPECTED_JSON, ROOT)})


if __name__ == "__main__":
    sys.exit(main())
