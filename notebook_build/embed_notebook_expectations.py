#!/usr/bin/env python3
"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-08-06
References: none (repository tooling; the numbers it moves are produced by
  make_notebook_data.py out of the committed results files).

PUT THE REPORTED NUMBERS INSIDE THE NOTEBOOK, IN ONE GENERATED CELL.

Why this exists. The reproduction notebook recomputes its own figures and then
compares them against the numbers the report publishes. Those numbers live in
notebooks/notebook_expected.json. Until now the notebook fetched that file from the
public Zenodo record at run time, and that is where the trouble was: a small file
sitting on a remote archive can be of a different age than the notebook reading it.
The copy published on Zenodo was last refreshed on 10 July, 3 713 bytes against the
8 927 the tree carried later, and every number in it belonged to a retired
measurement window. Run the way README.md tells a reader to run it, one upload into
Colab and Run all, the notebook passed 4 of its 25 comparisons and stopped on the
assertion in its last cell. Nothing was wrong with the notebook.

Two files cannot be the same age unless they are one file. So the numbers move
inside the notebook, written into a cell this program owns, and the file the reader
uploads carries both the code and the figures it checks itself against. The three
large data files stay on Zenodo and are still downloaded at run time: they are
byte-identical to what is published, they are far too large to inline, and their
provenance is recorded in notebook_data_meta.json beside them.

What it writes. One code cell whose first line is a marker this program recognises,
carrying the whole parsed contents of notebook_expected.json, _meta included, as a
Python literal, then the two lines the rest of the notebook expects:

    EXP = EXPECTED
    print('loaded reported numbers for:', ...)

The literal is printed the Python way rather than with json.dumps, because JSON
writes true, false and null, and none of the three is Python. How exactly it was
printed is recorded in a comment line inside the cell itself, and this program reads
that line back before it prints anything: the cell has a second author, the notebook
editor who may insert it by hand, and two authors of one cell agree only if the
second one reads what the first one declared.

What it refuses to do. It refuses to write when the printed literal does not parse
back into the same values, when the cell already in the notebook declares a printing
method this program cannot reproduce, and when the place the cell belongs cannot be
found. A refusal names what was expected, what was found and where.

Usage, from the repository root:

    uv run --no-project --with-requirements requirements.txt python3 \\
        embed_notebook_expectations.py
    uv run --no-project --with-requirements requirements.txt python3 \\
        embed_notebook_expectations.py --check

With --check nothing is written: the program says whether the cell has fallen behind
notebook_expected.json and exits 1 if it has.
"""
import argparse
import ast
import hashlib
import json
import os
import pprint
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# The notebook directory stayed in the repository root when the builders were grouped,
# so it is reached from the root rather than from beside this file. Built from this
# file's own location, so nothing absolute is recorded.
_CODE_DIR = os.path.dirname(HERE)
NOTEBOOK_DIR = os.path.join(_CODE_DIR, "notebooks")
DEFAULT_NOTEBOOK = os.path.join(
    NOTEBOOK_DIR, "counterparty_adverse_selection.ipynb")
DEFAULT_EXPECTED = os.path.join(NOTEBOOK_DIR, "notebook_expected.json")

# The first line of the generated cell, and the only way the cell is found again.
# Matched whole, not by prefix: a comment that merely mentions this program is not
# the cell.
MARKER = ("# GENERATED CELL - written by embed_notebook_expectations.py from "
          "notebook_expected.json - DO NOT EDIT BY HAND")

# The cell is inserted after the cell that opens the notebook's downloads, and before
# the heading that starts the analysis. Both are matched on their text rather than on
# a cell number, because a cell number moves whenever anything above it is edited.
ANCHOR_ABOVE = "import os, json, urllib.request"
ANCHOR_BELOW = "## Analysis functions"

# The identifier the generated cell carries in the notebook. nbformat 4.5 wants every
# cell to have one, and a stable one is what makes a second run of this program leave
# the file alone.
CELL_ID = "expected-embed"

# How the literal is printed, written into the cell and read back from it. The line
# is machine-readable on purpose: this program and the notebook editor both write
# this cell, and a declared method is the only thing that keeps the two from drifting
# apart in a way that reads as a real difference.
#
# The wording below is the one the cell already in the notebook carries, and it is
# canonical for that reason rather than by preference. The two of us wrote the same
# line differently on the first attempt, "# rendered with" against "# Literal printed
# with:", and the two cells then disagreed by 8 characters while every number in them
# agreed. Reading is deliberately wider than writing: an older wording is understood
# and then rewritten to the canonical one, so the two versions converge instead of
# taking turns.
METHOD_PREFIX = "# rendered with "
METHOD_LINE_RE = re.compile(
    r"^#\s*(?:rendered with|Literal printed with:)\s*(?P<call>.+?)\s*$")
PFORMAT_RE = re.compile(
    r"^pprint\.pformat\(\s*payload\s*,\s*indent=(?P<indent>\d+)\s*,"
    r"\s*width=(?P<width>\d+)\s*,\s*sort_dicts=(?P<sort_dicts>True|False)\s*\)$")
DEFAULT_METHOD = {"indent": 1, "width": 100, "sort_dicts": False}


def method_line(method):
    """The one comment line that says how the literal below it was printed."""
    return (f"{METHOD_PREFIX}pprint.pformat(payload, indent={method['indent']}, "
            f"width={method['width']}, sort_dicts={method['sort_dicts']})")


def read_method(source):
    """The printing method declared inside a cell that already exists.

    Returns the method, or None when the cell carries no declaration, which is how a
    cell written before this convention reads. Raises when a declaration is there but
    names something this program cannot reproduce: printing it a different way would
    look like a real difference to anybody diffing the cell, and a silent second
    format is exactly the drift the declaration is meant to prevent.
    """
    for line in source.split("\n"):
        declared = METHOD_LINE_RE.match(line)
        if not declared:
            continue
        call = PFORMAT_RE.match(declared.group("call"))
        if not call:
            raise ValueError(
                "the cell declares a printing method this program cannot repeat: "
                f"{declared.group('call')!r}. Expected a call of the form "
                "pprint.pformat(payload, indent=N, width=N, sort_dicts=True|False)")
        return {"indent": int(call.group("indent")),
                "width": int(call.group("width")),
                "sort_dicts": call.group("sort_dicts") == "True"}
    return None


def render_literal(payload, method):
    """The parsed JSON as Python source, checked to parse back into the same values.

    Two things can go wrong and both are caught here rather than in the reader's
    Colab session. A float that is not finite prints as nan or inf, which no Python
    literal understands. And a printer set up differently from what it declares would
    give text that reads plausibly and evaluates to something else.
    """
    text = pprint.pformat(payload, indent=method["indent"], width=method["width"],
                          sort_dicts=method["sort_dicts"])
    try:
        back = ast.literal_eval(text)
    except (ValueError, SyntaxError) as exc:
        raise ValueError(f"the printed literal does not parse as Python: {exc}. "
                         "The usual cause is a non-finite float, which prints as nan "
                         "or inf and is not a literal") from exc
    diff = first_leaf_difference(payload, back)
    if diff is not None:
        where, want, got = diff
        raise ValueError(f"the literal does not read back as the file it came from, "
                         f"at {where}: expected {want!r} of type "
                         f"{type(want).__name__}, read back {got!r} of type "
                         f"{type(got).__name__}")
    return text


def first_leaf_difference(want, got, where="$"):
    """Where two parsed structures stop agreeing, or None when they agree.

    Compared leaf by leaf and by type as well as by value, because the point of this
    walk is the three JSON words Python does not share. True is not 1 here, and a
    comparison that says it is would pass the very case this is written for.
    """
    if type(want) is not type(got):
        return where, want, got
    if isinstance(want, dict):
        if list(want) != list(got):
            return where, list(want), list(got)
        for key in want:
            found = first_leaf_difference(want[key], got[key], f"{where}.{key}")
            if found is not None:
                return found
        return None
    if isinstance(want, list):
        if len(want) != len(got):
            return where, len(want), len(got)
        for i, (a, b) in enumerate(zip(want, got)):
            found = first_leaf_difference(a, b, f"{where}[{i}]")
            if found is not None:
                return found
        return None
    if want != got:
        return where, want, got
    return None


def first_line_difference(want, got):
    """The first line at which two versions of the cell part company.

    A report that says only "the cell disagrees" leaves the reader to diff by eye,
    and the two versions here are four hundred lines long and differ by one number.
    Lines are counted from one, the way an editor counts them.
    """
    want_lines, got_lines = want.split("\n"), got.split("\n")
    for i in range(max(len(want_lines), len(got_lines))):
        a = want_lines[i] if i < len(want_lines) else "<no such line>"
        b = got_lines[i] if i < len(got_lines) else "<no such line>"
        if a != b:
            return i + 1, a[:110], b[:110]
    return 0, "", ""


def build_source(payload, method):
    """The full text of the generated cell, ending without a trailing newline.

    The layout is fixed line by line, and the marker is the first line, because the
    notebook editor writes this same cell by hand and a guard compares the two. Any
    freedom in the layout here is a difference that guard would have to report.
    """
    lines = [
        MARKER,
        "# Home of these values: notebooks/notebook_expected.json, itself written by",
        "# make_notebook_data.py out of the committed results files. Regenerate with:",
        "#   uv run --no-project --with-requirements requirements.txt python3 "
        "embed_notebook_expectations.py",
        method_line(method),
        "",
        "EXPECTED = " + render_literal(payload, method),
        "",
        "EXP = EXPECTED",
        "print('loaded reported numbers for:', "
        "', '.join(k for k in EXP if k != '_meta'))",
    ]
    text = "\n".join(lines)
    # Proof that what goes into the notebook is a cell a reader can run, not only a
    # literal that parses. compile() raises here rather than in somebody's Colab.
    compile(text, "<generated cell>", "exec")
    return text


def to_source_list(text):
    """Cell text as nbformat stores it: one string per line, last one unterminated.

    That is the convention this notebook already follows in 30 of its 33 cells, and
    following it keeps the generated cell from standing out in a diff for a reason
    that has nothing to do with the numbers.
    """
    lines = text.split("\n")
    return [line + "\n" for line in lines[:-1]] + [lines[-1]]


def cell_text(cell):
    """The text of a cell, whether its source is stored as a list or as one string."""
    src = cell.get("source")
    return "".join(src) if isinstance(src, list) else str(src or "")


def read_notebook(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def write_notebook(path, doc):
    """Write the notebook the way Jupyter writes it, so a no-op run changes no byte.

    Measured against the notebook as it stands: indent 1, sorted keys, unescaped
    non-ASCII and one closing newline reproduce the file on disk exactly.
    """
    text = json.dumps(doc, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def find_generated(doc):
    """Index of the generated cell, or None. More than one is a refusal.

    Two cells carrying the marker would mean the notebook loads its numbers twice and
    the second load wins, so this is reported instead of being repaired by guesswork.
    """
    hits = [i for i, cell in enumerate(doc.get("cells") or [])
            if cell.get("cell_type") == "code"
            and cell_text(cell).split("\n")[0] == MARKER]
    if len(hits) > 1:
        raise ValueError(f"the notebook carries {len(hits)} cells with the marker, at "
                         f"positions {hits}. One of them is the cell and the rest are "
                         "copies; remove the copies by hand and run this again")
    return hits[0] if hits else None


def find_slot(doc):
    """Where a cell that does not exist yet has to go.

    Between the cell that sets up the downloads and the heading that opens the
    analysis. Both ends are checked, and their order too: if the heading came first,
    the notebook would read the numbers after using them.
    """
    cells = doc.get("cells") or []
    above = [i for i, c in enumerate(cells)
             if c.get("cell_type") == "code" and ANCHOR_ABOVE in cell_text(c)]
    below = [i for i, c in enumerate(cells)
             if c.get("cell_type") == "markdown"
             and cell_text(c).lstrip().startswith(ANCHOR_BELOW)]
    if not above:
        raise ValueError(
            f"expected a code cell containing {ANCHOR_ABOVE!r}, found none, in the "
            f"{len(cells)} cells of this notebook. That cell is where the generated "
            "cell goes after, and this program will not guess a position")
    if not below:
        raise ValueError(
            f"expected a markdown cell opening with {ANCHOR_BELOW!r}, found none, in "
            f"the {len(cells)} cells of this notebook. That heading is where the "
            "generated cell goes before, and this program will not guess a position")
    if above[0] >= below[0]:
        raise ValueError(
            f"expected {ANCHOR_ABOVE!r} above {ANCHOR_BELOW!r}, found them at cell "
            f"{above[0]} and cell {below[0]}. In that order the notebook would use "
            "the reported numbers before reading them")
    return above[0] + 1


def new_cell(text):
    return {"cell_type": "code", "execution_count": None, "id": CELL_ID,
            "metadata": {}, "outputs": [], "source": to_source_list(text)}


def sha256_file(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def cell_digests(doc):
    """One digest per cell, over its text, so a run can say what it left alone."""
    return [hashlib.sha256(cell_text(c).encode("utf-8")).hexdigest()
            for c in (doc.get("cells") or [])]


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Write the reported numbers from notebook_expected.json into a "
                    "generated cell of the reproduction notebook.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="write nothing; say whether the cell has fallen behind "
                         "notebook_expected.json and exit 1 if it has")
    ap.add_argument("--notebook", default=DEFAULT_NOTEBOOK,
                    help="the notebook to read and write (default: the reproduction "
                         "notebook beside this script)")
    ap.add_argument("--expected", default=DEFAULT_EXPECTED,
                    help="the file of reported numbers to embed (default: "
                         "notebooks/notebook_expected.json)")
    args = ap.parse_args(argv)

    nb_name = os.path.basename(args.notebook)
    exp_name = os.path.basename(args.expected)

    print("=" * 76)
    print("  EMBED THE REPORTED NUMBERS INTO THE REPRODUCTION NOTEBOOK")
    print("=" * 76)

    with open(args.expected, encoding="utf-8") as fh:
        payload = json.load(fh)
    doc = read_notebook(args.notebook)
    cells = doc.get("cells") or []
    print(f"  numbers file       : {exp_name}, {len(payload) - 1} groups beside _meta")
    print(f"  notebook           : {nb_name}, {len(cells)} cells")

    try:
        found = find_generated(doc)
        method = read_method(cell_text(cells[found])) if found is not None else None
        if method is None:
            method = dict(DEFAULT_METHOD)
            declared = "none in the notebook, so this program declares the default"
        else:
            declared = "read back from the cell already in the notebook"
        print(f"  printing method    : {declared}")
        print(f"                       {method_line(method)}")
        wanted = build_source(payload, method)
        # Where the cell belongs is resolved here as well, inside the same guard: a
        # notebook whose anchors have moved is a finding to be reported in words, not
        # a traceback, and --check has to answer it too.
        if found is None:
            slot = find_slot(doc)
            place = f"a new cell at position {slot} of {nb_name}"
            current = None
        else:
            slot = found
            place = f"cell {found} of {nb_name}"
            current = cell_text(cells[found])
    except ValueError as exc:
        print("-" * 76)
        print(f"  REFUSED: {exc}")
        print(f"  PLACE  : {nb_name}")
        return 2

    before = cell_digests(doc)
    stale = current != wanted

    if args.check:
        print(f"  cell               : {place}")
        print("-" * 76)
        if not stale:
            print("  the embedded cell carries exactly what the numbers file says.")
            return 0
        print("  the embedded cell has fallen behind the numbers file.")
        print(f"  EXPECTATION: {len(wanted)} characters, sha256 "
              f"{hashlib.sha256(wanted.encode()).hexdigest()[:16]}, built from "
              f"{exp_name}")
        if current is None:
            print("  FACT       : the cell is absent")
            print(f"  PLACE      : {place}")
        else:
            print(f"  FACT       : {len(current)} characters, sha256 "
                  f"{hashlib.sha256(current.encode()).hexdigest()[:16]}")
            line_no, want_line, got_line = first_line_difference(wanted, current)
            print(f"  PLACE      : {place}, line {line_no}")
            print(f"               expected {want_line!r}")
            print(f"               found    {got_line!r}")
        print(f"  REPAIR     : uv run --no-project --with-requirements "
              f"requirements.txt python3 {os.path.basename(__file__)}")
        return 1

    if not stale:
        print(f"  cell               : {place}, already current")
        print(f"  cells rewritten    : 0 of {len(cells)}")
        print(f"  cells left alone   : {len(cells)} of {len(cells)}")
        print(f"  sha256             : {sha256_file(args.notebook)}")
        print("-" * 76)
        print("  nothing to do.")
        return 0

    if found is None:
        cells.insert(slot, new_cell(wanted))
        what = "inserted"
    else:
        cell = cells[found]
        cell["source"] = to_source_list(wanted)
        # The output of the previous text is not the output of this text. Clearing it
        # is the honest state for a cell that has just changed; a reader's Run all
        # fills it in again.
        cell["outputs"] = []
        cell["execution_count"] = None
        what = "rewritten"
    doc["cells"] = cells

    write_notebook(args.notebook, doc)

    after = cell_digests(doc)
    untouched = sum(1 for d in before if d in after)
    print(f"  cell               : {place}, {what}")
    print(f"  cells rewritten    : 1 of {len(cells)}")
    print(f"  cells left alone   : {untouched} of {len(before)} that were there before")
    print(f"  sha256             : {sha256_file(args.notebook)}")
    print("-" * 76)
    print(f"  {what} the generated cell; run with --check to confirm it stays current.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
