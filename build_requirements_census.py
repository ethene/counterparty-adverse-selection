#!/usr/bin/env python3
"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-08-11

References: none (repository infrastructure; it declares no quantity of its own. It
reads the syntax tree of every shipped .py file and the shipped-file population from
checks/evidence.py).

THE COUNTS INSIDE requirements.txt, DERIVED FROM THE TREE INSTEAD OF TYPED.

WHY THIS FILE EXISTS. requirements.txt does not only pin versions. It also tells a
reader which files need which package, and how many files were looked at to find out,
and those are counts about this repository. Every one of them was typed by hand, and on
2026-08-11 five of the ten numbers in that file disagreed with the tree: the census said
109 shipped .py files against 117, numpy 73 files against 78, scipy five files against
six, the notebook download about 170 MB against 189.8, and pyarrow resolving to 25.0.0
against 25.0.1.

NONE OF THE FIVE WAS A COUNTING ERROR, AND THAT IS THE POINT. Re-running this census
against the commit that wrote those numbers, 942cc62 of 2026-08-04, reproduces all eight
tree counts exactly: 109 files, numpy 73, matplotlib 5, scipy 5, lz4 3, pyarrow 2, pandas
1, scikit-learn 1. The numbers were right on the day they were typed. What happened
afterwards is that the tree moved: eight scripts were added and none removed, which is
the whole of 109 -> 117, and fifty-one files were moved into group directories, which is
why the file names listed beside each package named a directory that no longer holds
them. numpy went 73 -> 78 because six of the eight new files import it and one old file,
persistence/ws3_plot.py, stopped importing it once the drawing moved out of the
computing scripts. A hand-typed count does not go wrong. It goes stale, and it does so
without saying anything, which is the failure this module exists to prevent.

WHAT IS DERIVED HERE AND WHAT IS NOT. Eight counts can be read out of the tree, and
this module reads them:

    the population       every shipped .py file, from checks/evidence.shipped_tree_files
    five package counts  which of those files import each pinned distribution
    the entry points     the pipeline groups, one run/<group>.py each
    the standard library which modules the tree takes from Python itself

One number cannot. The size of the download the reproduction notebook performs is a
property of a public archive on the other side of the network, not of this tree, so it
stays declared by hand -- and requirements.txt says so in those words beside the number,
with the command that re-measures it, so that a reader can tell a derived number from a
typed one without leaving the file. The versions the pinned environment resolves to are
declared by hand for the same reason and carry the same mark: two of the five pins
are ranges rather than exact, so what they resolve to is a fact about an index on the
day of the resolve.

WHY THE SYNTAX TREE AND NOT A TEXT SEARCH. Because the two disagree here, today, and the
text search is the one that is wrong. Searching this tree for the word matplotlib
returns seven files; five of them import it. The other two, markout/ws1_horizon_
persistence.py and persistence/ws3_taker_pnl.py, carry the sentence "a run that could
not import matplotlib wrote fresh numbers" inside their opening docstring, describing a
bug that was fixed on 2026-08-03. A count that reads prose as code overstates a
dependency by forty percent, and it does it silently.

WHAT AN IMPORT MEANS HERE. A file counts against a distribution when its syntax tree
holds an import whose top-level module belongs to that distribution -- `import numpy`,
`from scipy.stats import ks_2samp`, `import matplotlib.pyplot as plt`. The mapping from
module to distribution is written down below because it is not derivable: matplotlib
brings `mpl_toolkits` with it. Imports nested inside
a function or a try block count, because the file still needs the package to do its
work; a relative import does not, because it names this repository rather than a
dependency.

ADDING A FILE MEANS STAGING IT AND THEN REGENERATING, IN THAT ORDER. The population is
what the source release ships, and in a Git checkout that is the index: a file written
but not yet added is on disk and is not shipped, so it is correctly invisible here. The
consequence is an order of moves rather than a defect. Write the file, `git add` it,
then run --write, then commit both. Doing it the other way round leaves a block that
was true when it was written and stops being true one command later -- which is, in
miniature, the whole disease this module treats.

    uv run --no-project python3 build_requirements_census.py            # check
    uv run --no-project python3 build_requirements_census.py --write    # regenerate
    uv run --no-project python3 build_requirements_census.py --json     # the census

The check prints the expectation, the fact and the place for every count that moved, and
exits non-zero. It writes nothing, so it is safe to run at any time, and it is what makes
the derived block a claim the repository can defend rather than a claim it merely holds.
"""
import argparse
import ast
import datetime
import difflib
import re
import json
import os
import sys
import textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
if os.path.join(HERE, "checks") not in sys.path:
    sys.path.insert(0, os.path.join(HERE, "checks"))
from evidence import shipped_tree_files                                 # noqa: E402

REQUIREMENTS = os.path.join(HERE, "requirements.txt")
RUN_DIR = os.path.join(HERE, "run")

# The two lines that fence the derived region. Everything between them is written by
# this module; everything outside is prose kept by hand. Fencing rather than rewriting
# the whole file is deliberate: requirements.txt is read by every run in this project
# through --with-requirements, and a generator that owns the pins as well as the counts
# could break every run in the tree to fix a comment.
BEGIN = "# BEGIN DERIVED BLOCK"
END = "# END DERIVED BLOCK"

# Which top-level module belongs to which pinned distribution. Written down because it
# cannot be derived: an installed distribution and the name it is imported under are two
# different strings, and for one of the five they differ.
DISTRIBUTIONS = (
    ("numpy", ("numpy",)),
    ("matplotlib", ("matplotlib", "mpl_toolkits")),
    ("scipy", ("scipy",)),
    ("lz4", ("lz4",)),
    ("pyarrow", ("pyarrow",)),
)

# What each distribution is here for, in words. The counts and the file names below are
# derived; this sentence is not, because why a dependency exists is an argument and not
# a fact about a syntax tree. Kept here rather than in requirements.txt so that the
# derived block has one author and cannot half-update.
PURPOSE = {
    "numpy": "the array type every computing script in the pipeline is written in",
    "matplotlib": "drawing the figures of the paper, and the notebook besides",
    "scipy": "the statistical tests and the connected-component walk",
    "lz4": "reading the compressed archive files in process",
    "pyarrow": "reading and writing parquet",
}

# The population is .py files, so the reproduction notebook is outside it, and two of the
# pins are needed by that notebook as well as by the files counted below. Saying so is not
# decoration: a reader who trims a dependency to the one script named beside it would
# break the one route through this repository that needs no credentials at all.
NOTEBOOK_NOTE = (
    "The count is over .py files, so the reproduction notebook is not in it. It imports "
    "numpy and matplotlib itself, so a reader who trims the pins to the scripts listed "
    "above would still have to keep those two.")

# Above this many files a list of names stops informing and starts filling the screen.
# The threshold is stated rather than chosen per package, so that a package crossing it
# loses its list for a reason a reader can see.
NAMES_SHOWN_UP_TO = 8

# How wide a comment line in requirements.txt may be, matching the prose around it.
WIDTH = 88


# =====================================================================
# 1. READING THE TREE
# =====================================================================

def population():
    """Every shipped .py file, repo-relative and sorted.

    The predicate has one home and this is not it: checks/evidence.shipped_tree_files
    answers what the source release ships, reading the Git index in a checkout and
    walking the directory in an extracted archive, and every gate in checks/ asks it the
    same question. Copying its rules here would give this file a second answer that
    drifts from the first, which is the failure the shared helper was written to end.
    """
    return [path for path in shipped_tree_files(HERE) if path.endswith(".py")]


def imported_modules(relative_path):
    """The dotted modules a file imports, from its syntax tree.

    Relative imports are skipped: `from .evidence import report_gate` names this
    repository, not a dependency, and counting it would put this tree's own module names
    among the distributions.
    """
    with open(os.path.join(HERE, relative_path), "r", encoding="utf-8") as handle:
        source = handle.read()
    tree = ast.parse(source, filename=relative_path)
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                modules.add(node.module)
    return modules


def entry_points():
    """The pipeline group entry points: every run/<name>.py that is not a helper.

    A leading underscore marks a module the entry points share rather than an entry
    point of its own, which is the convention run/_groups.py already carries.
    """
    if not os.path.isdir(RUN_DIR):
        return []
    return sorted(
        "run/" + name for name in os.listdir(RUN_DIR)
        if name.endswith(".py") and not name.startswith("_"))


def census():
    """Every count this module derives, with the files each one rests on."""
    files = population()
    per_module = {path: imported_modules(path) for path in files}
    packages = {}
    for distribution, tops in DISTRIBUTIONS:
        hits = {}
        for path in files:
            matched = sorted(m for m in per_module[path] if m.split(".")[0] in tops)
            if matched:
                hits[path] = matched
        packages[distribution] = {
            "files": sorted(hits),
            "count": len(hits),
            "modules": sorted({m for names in hits.values() for m in names}),
        }
    everything = {m.split(".")[0] for names in per_module.values() for m in names}
    third_party = {top for _d, tops in DISTRIBUTIONS for top in tops}
    return {
        "population": len(files),
        "packages": packages,
        "entry_points": entry_points(),
        # What the tree takes from Python itself. Asked of sys.stdlib_module_names
        # rather than of a list typed here: a list typed here is the same hand-kept
        # count this module exists to end, and this repository already carried one that
        # named twelve of the modules it uses as though it named all of them.
        "standard_library": sorted(
            (everything - third_party) & set(sys.stdlib_module_names)),
        "taken_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d"),
    }


# =====================================================================
# 2. RENDERING THE DERIVED BLOCK
# =====================================================================

def _lines(text, initial, subsequent):
    """One paragraph as comment lines no wider than WIDTH.

    The indents are handed to textwrap rather than folded into the text because the
    census is a column: the distribution name and its count line up down the block, and
    a wrapper that treats the padding as ordinary whitespace collapses that column on
    the first re-render.
    """
    return textwrap.wrap(
        text, width=WIDTH, initial_indent=initial, subsequent_indent=subsequent,
        break_long_words=False, break_on_hyphens=False) or [initial.rstrip()]


# The column the counts stand in: "# ", then the distribution name, then the count, then
# the sentence. HANG is where a wrapped line resumes, which is under the sentence. It
# opens with the comment mark and not with blanks, because every line of this file that
# is not a pin has to be a comment: pip reads the file, and a continuation line indented
# with spaces alone would be read as a requirement and stop every run in the project.
NAME_WIDTH = 14
COUNT_WIDTH = 2
HANG = "# " + " " * (NAME_WIDTH + COUNT_WIDTH + 1)


def render(counts):
    """The derived block, as the list of comment lines it occupies in the file."""
    out = [BEGIN]
    out += _lines(
        "Everything down to END DERIVED BLOCK is written by "
        "build_requirements_census.py from the syntax tree of every shipped .py file. A "
        "hand edit here is overwritten the next time it runs, and running it without "
        "--write reports what moved instead of writing.", "# ", "# ")
    out.append("#")
    out += _lines(
        f"WHICH FILES NEED WHAT, counted on {counts['taken_utc']} by walking the syntax "
        f"tree of all {counts['population']} shipped .py files rather than by searching "
        f"for text. The two disagree, and the search is the one that is wrong: a text "
        f"search for the word matplotlib returns seven files here and five of them "
        f"import it, the other two carrying the word inside a docstring.", "# ", "# ")
    out.append("#")
    for distribution, _tops in DISTRIBUTIONS:
        entry = counts["packages"][distribution]
        out += _lines(
            f"{'file' if entry['count'] == 1 else 'files'}, {PURPOSE[distribution]}. "
            f"Imported as {', '.join(entry['modules'])}.",
            f"# {distribution:<{NAME_WIDTH}}{entry['count']:>{COUNT_WIDTH}} ", HANG)
        if entry["count"] <= NAMES_SHOWN_UP_TO:
            out += _lines(", ".join(entry["files"]) + ".", HANG, HANG)
    out.append("#")
    out += _lines(NOTEBOOK_NOTE, "# ", "# ")
    out.append("#")
    out += _lines(
        f"The pipeline has {len(counts['entry_points'])} groups and one entry point "
        f"each, the ones listed under RUN above: "
        f"{', '.join(counts['entry_points'])}.", "# ", "# ")
    out.append("#")
    out += _lines(
        f"Nothing else is installed. The {len(counts['standard_library'])} other "
        f"modules these files import come with Python: "
        f"{', '.join(counts['standard_library'])}.", "# ", "# ")
    out.append(END)
    # The one way this module could do real damage, refused here rather than regretted
    # later. requirements.txt is read by every run in this project through
    # --with-requirements, and pip reads any line that is not a comment as a package to
    # install. A wrapped line that lost its comment mark would therefore not produce a
    # wrong count; it would stop the whole project, and it would do it at the next run
    # rather than at this one. This has already happened once, in the first draft of the
    # wrapper above, which indented its continuations with blanks.
    for line in out:
        if line and not line.startswith("#"):
            raise SystemExit(
                f"build_requirements_census.py refuses to write a line that pip would "
                f"read as a requirement: {line!r}. Every line of the derived block has "
                f"to open with the comment mark.")
    return out


# =====================================================================
# 3. THE FILE, READ AND WRITTEN
# =====================================================================

def _split(text):
    """The requirements file as (before, inside, after) around the derived block."""
    lines = text.split("\n")
    try:
        first = next(i for i, line in enumerate(lines) if line.startswith(BEGIN))
        last = next(i for i, line in enumerate(lines) if line.startswith(END))
    except StopIteration:
        raise SystemExit(
            f"requirements.txt carries no derived block. Expected a line beginning "
            f"{BEGIN!r} and a later line beginning {END!r}; found neither or only one. "
            f"Add the two fence lines where the census belongs and run --write again.")
    if last < first:
        raise SystemExit("requirements.txt closes the derived block before it opens it.")
    return lines[:first], lines[first:last + 1], lines[last + 1:]


def check_run_section(before_and_after, counts):
    """Findings where the RUN prose and the run/ directory disagree.

    The entry points are named twice in this file on purpose: once as commands a reader
    types, and once in the derived block as a count. The list a reader types cannot be
    generated without rewriting the prose around it, so it is checked instead -- which is
    the same bargain run/_groups.py strikes with its membership table.
    """
    text = "\n".join(before_and_after)
    findings = []
    for name in counts["entry_points"]:
        if name not in text:
            findings.append((name, "run/ holds this entry point and the RUN section "
                                   "does not name it"))
    for line in text.split("\n"):
        for word in line.replace(",", " ").split():
            if word.startswith("run/") and word.endswith(".py"):
                if word not in counts["entry_points"]:
                    findings.append((word, "the RUN section names this entry point and "
                                           "run/ does not hold it"))
    return sorted(set(findings))


def main():
    parser = argparse.ArgumentParser(description=__doc__.strip().split("\n")[6])
    parser.add_argument("--write", action="store_true",
                        help="rewrite the derived block in requirements.txt")
    parser.add_argument("--json", action="store_true",
                        help="print the census as JSON and write nothing")
    args = parser.parse_args()

    counts = census()
    if args.json:
        print(json.dumps(counts, indent=2, sort_keys=True))
        return 0

    with open(REQUIREMENTS, "r", encoding="utf-8") as handle:
        text = handle.read()
    before, inside, after = _split(text)
    fresh = render(counts)

    if args.write:
        with open(REQUIREMENTS, "w", encoding="utf-8") as handle:
            handle.write("\n".join(before + fresh + after))
        moved = "unchanged" if inside == fresh else "rewritten"
        print(f"requirements.txt derived block {moved}: {len(fresh)} lines, "
              f"{counts['population']} shipped .py files walked")
        return 0

    # Line against line, ALIGNED FIRST. Walking the two blocks in step and reporting
    # every position where they differ measures this comparison rather than the tree:
    # one file added to the tree lengthens one list by one line, and from that line on
    # every later line sits opposite its neighbour and reads as a finding. Measured on
    # the calibration fixture: four things had really moved and the paired walk printed
    # twenty-eight. difflib aligns the blocks before comparing, so an insertion is
    # reported as an insertion and the twenty-four disappear.
    # THE COMPARISON IS BLIND TO THE DATE THE BLOCK STAMPS ON ITSELF, AND WITHOUT THAT IT
    # MEASURED THE CALENDAR. The first rendered line carries the day the census was taken.
    # Rendering it fresh stamps today, so the day after any regeneration that line differs
    # from the stored one and nothing else does: measured on 2026-08-30 by moving the
    # stored date back one day in a copy and touching nothing else, this program returned
    # exit 1 with a single finding whose expectation and fact were identical apart from
    # the date. A gate standing on that would have gone red every day that nobody
    # regenerated, which is a reading about the calendar and not about the tree. The date
    # is still written, because a reader wants to know when the counts were taken; it is
    # simply not one of the things the two blocks are asked to agree about. The
    # substitution is one-to-one per line, so the positions the diff returns still index
    # the untouched lines that get printed.
    findings = []
    _stamped_day = re.compile(r"counted on \d{4}-\d{2}-\d{2}")

    def _blind_to_the_day(lines):
        return [_stamped_day.sub("counted on <the day it was taken>", line)
                for line in lines]

    opcodes = difflib.SequenceMatcher(a=_blind_to_the_day(inside),
                                      b=_blind_to_the_day(fresh),
                                      autojunk=False).get_opcodes()
    for tag, old_from, old_to, new_from, new_to in opcodes:
        if tag == "equal":
            continue
        span = (f"line {old_from + 1}" if old_to - old_from <= 1
                else f"lines {old_from + 1}-{old_to}")
        findings.append((
            f"requirements.txt derived block, {span}",
            " / ".join(line.strip() for line in fresh[new_from:new_to]) or "(no line)",
            " / ".join(line.strip() for line in inside[old_from:old_to]) or "(no line)"))
    for place, detail in check_run_section(before + after, counts):
        findings.append((place, detail, "not so in the file"))

    if not findings:
        print(f"PASS  requirements.txt agrees with the tree: {counts['population']} "
              f"shipped .py files, "
              + ", ".join(f"{d} {counts['packages'][d]['count']}"
                          for d, _ in DISTRIBUTIONS)
              + f", {len(counts['entry_points'])} entry points")
        return 0

    print(f"FAIL  requirements.txt disagrees with the tree in {len(findings)} places.")
    for place, expectation, fact in findings:
        print(f"  PLACE       {place}")
        print(f"  EXPECTATION {expectation}")
        print(f"  FACT        {fact}")
    print("\nRepair: uv run --no-project python3 build_requirements_census.py --write")
    return 1


if __name__ == "__main__":
    sys.exit(main())
