#!/usr/bin/env python3
"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-08-04
References: none (repository hygiene gate).

EVERY FILE OF CODE OPENS WITH THE STUDY HEADER.

Why this gate exists. Each notebook and each script opens by naming the study it
belongs to, its author and its date. On 2026-08-04 all 108 tracked Python files and the
reproduction notebook carried a header, and nothing in this repository asked whether
they did. A rule that holds today and is enforced by nothing is a rule that will stop
holding on the day a file is added, and it will stop holding silently: the header is
the first thing a reader sees and the last thing anybody thinks to re-count.

What the header must carry. Three parts, and each is load-bearing on its own. The
study name says which piece of work the file belongs to, so a file copied out of this
repository still says where it came from. The author line is who is answerable for it.
The date places the file against the history of the work. This gate reads the first
part of the file only: a mention of the study buried three hundred lines down is a
comment, not a header. A `References:` line usually follows and is not required.

The population is every file of code the source release ships. A Git checkout reads
that population from its index; an extracted source ZIP gets the same population from
the shared recursive census. Notebooks are read as JSON and judged on their opening
cells, because that is where a notebook header lives.

Read-only. Exits non-zero on a finding and names file and reason.

    uv run --no-project python3 checks/chk_academic_header.py
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
import artifact                                                         # noqa: E402
from evidence import report_gate, shipped_tree_files                    # noqa: E402

OUT_JSON = os.path.join(HERE, "chk_academic_header_results.json")

# The three parts, each with the reason it is required. Named one at a time rather
# than as a single pattern over the whole block: one pattern would report "header
# malformed" and leave the reader to work out which part is missing, and the repair
# differs by part.
#
# Each part is matched on SUBSTANCE, not on the punctuation of the template. The
# first version of this gate asked for literal strings with the template's colon and
# capital letter and reported fourteen findings, seven of which were punctuation in
# files that carried every part. A gate that fails a file for a colon measures the
# template, and the requirement is about what the header says.
STUDY_NAME = "Counterparty adverse selection on Hyperliquid"
PARTS = (
    (re.compile(r"\s+".join(STUDY_NAME.split()), re.I),
     "names the study this file belongs to"),
    (re.compile(r"\bAuthors?\s*[:\-]\s*\S", re.I),
     "names who is answerable for the file"),
    (re.compile(r"\bDate\s*[:\-]?\s*\d{4}-\d{2}-\d{2}", re.I),
     "dates the file, so a reader can place it against the history of the work"),
)

# How far into the file the header may begin. A header is what opens a file; twelve
# lines allows a shebang, an encoding line and a blank line before the docstring, and
# refuses to accept a mention of the study from the middle of the body.
HEAD_LINES = 12

# How much of a notebook counts as its opening. A notebook does not open with a
# docstring: it opens with a title cell, and its code header sits in the first code
# cell below. Both are the opening, so the region runs to the first code cell
# inclusive, and no further.
NOTEBOOK_OPENING_CELLS = 6


def header_region(text, ext):
    """The part of a file where a header may legitimately stand.

    A notebook keeps its header inside a cell rather than at the top of the file, and
    the file itself opens with JSON scaffolding, so reading its first twelve physical
    lines would judge the wrong thing. The first cell is read instead.
    """
    if ext == ".ipynb":
        try:
            doc = json.loads(text)
        except json.JSONDecodeError:
            return None
        parts = []
        for i, cell in enumerate(doc.get("cells") or []):
            src = cell.get("source")
            parts.append("".join(src) if isinstance(src, list) else str(src or ""))
            # The opening ends at the first code cell: past it the notebook is doing
            # work, and a declaration found there is a comment in the body.
            if cell.get("cell_type") == "code" or i + 1 >= NOTEBOOK_OPENING_CELLS:
                break
        return "\n".join(parts)
    return "\n".join(text.split("\n")[:HEAD_LINES])


def missing_parts(region):
    """Which required parts are absent from the header region.

    Returns the list of missing parts. An empty list is the passing answer; a region
    of None means the file could not be parsed at all, which is a finding of its own
    and is reported by the caller rather than silently read as "nothing missing".
    """
    return [(pat.pattern, why) for pat, why in PARTS if not pat.search(region)]


def tracked_code_files():
    """Every shipped Python file and notebook, repo-relative, stable order."""
    return [p for p in shipped_tree_files(ROOT) if p.endswith((".py", ".ipynb"))]


def calibrate():
    """Two opposite cases per predicate, both built here rather than named on disk.

    A calibration anchored on a live file goes vacuous the day that file is repaired,
    and in this project that has already happened twice in one day. Every fixture is
    written out in full below, so this calibration cannot quietly stop testing
    anything.

    The fixtures are shaped like the files this tree actually holds, which is the
    other half of the lesson. A fixture written to the template rather than to the
    real case certifies nothing: the first version of this gate passed its own
    calibration and then reported seven files for punctuation the requirement never
    asked for.
    """
    template = ('#!/usr/bin/env python3\n"""\n'
                f"{STUDY_NAME} | Author: A Name | Date: 2026-01-01\n"
                "References: none.\n"
                '"""\nimport os\n')
    # The same three parts, spelled the way a hand-written header spells them: lower
    # case, a comment rather than a docstring, two authors, a dash for a colon. This
    # must pass: the requirement is the content, not the punctuation.
    live_variant = ("# counterparty adverse selection on hyperliquid -- "
                    "Authors - A Name, B Name | date 2026-06-22\n"
                    "import os\n")
    # Study and date named, author absent. This is the defect the gate is for.
    no_author = ('"""\n'
                 f"{STUDY_NAME} | Date: 2026-06-22\n"
                 "What this probe measures, in one line.\n"
                 '"""\nimport os\n')
    bare = "import os\n\n\ndef main():\n    return 0\n"
    # The header written far below the opening region: every part is present in the
    # file and absent from the header, and only a gate that bounds its region can tell
    # those two apart.
    late = ("import os\n" * 40
            + f"# {STUDY_NAME} | Author: A Name | Date: 2026-01-01\n")
    # A notebook that opens with a title cell and carries author and date in its first
    # code cell, which is how the reproduction notebook in this tree is built.
    nb_ok = json.dumps({"cells": [
        {"cell_type": "markdown", "source": [f"# {STUDY_NAME}\n"]},
        {"cell_type": "markdown", "source": ["## The data\n"]},
        {"cell_type": "code",
         "source": ["# Author: A Name | Date: 2026-01-01\n"]},
    ]})
    # The same notebook with author and date moved past the first code cell, where
    # they are a comment in the body rather than a header.
    nb_late = json.dumps({"cells": [
        {"cell_type": "markdown", "source": [f"# {STUDY_NAME}\n"]},
        {"cell_type": "code", "source": ["import os\n"]},
        {"cell_type": "code",
         "source": ["# Author: A Name | Date: 2026-01-01\n"]},
    ]})

    def names(region):
        return sorted(n for n, _ in missing_parts(region))

    all_parts = sorted(p.pattern for p, _ in PARTS)
    author = PARTS[1][0].pattern
    author_and_date = sorted([PARTS[1][0].pattern, PARTS[2][0].pattern])
    rows = [
        ("header present", "must stay silent: template punctuation",
         names(header_region(template, ".py")), []),
        ("header present", "must stay silent: the punctuation live files use",
         names(header_region(live_variant, ".py")), []),
        ("author missing", "must fire: study and date named, no author",
         names(header_region(no_author, ".py")), [author]),
        ("header absent", "must fire: no header at all",
         names(header_region(bare, ".py")), all_parts),
        ("region is bounded", "must fire: header written past the opening lines",
         names(header_region(late, ".py")), all_parts),
        ("notebook opening", "must stay silent: title cell plus first code cell",
         names(header_region(nb_ok, ".ipynb")), []),
        ("notebook opening", "must fire: author and date past the first code cell",
         names(header_region(nb_late, ".ipynb")), author_and_date),
    ]
    return [(name, what, got, want, got == want) for name, what, got, want in rows]


def scan():
    findings, scanned = [], 0
    for rel in tracked_code_files():
        path = os.path.join(ROOT, rel)
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError as exc:
            findings.append({"file": rel, "line": 0, "rule": "UNREADABLE",
                             "detail": str(exc), "source": ""})
            continue
        scanned += 1
        region = header_region(text, os.path.splitext(rel)[1])
        if region is None:
            findings.append({
                "file": rel, "line": 1, "rule": "UNPARSEABLE-NOTEBOOK",
                "detail": "the notebook is not readable as JSON, so whether it "
                          "carries a header cannot be answered either way",
                "source": ""})
            continue
        for needle, why in missing_parts(region):
            findings.append({
                "file": rel,
                "line": 1,
                "rule": "NO-STUDY-HEADER",
                "detail": f"the opening of this file does not carry {needle!r}, which "
                          f"{why}",
                "source": region.strip().split("\n")[0][:120],
            })
    return findings, scanned


def main():
    started = artifact.start_clock()
    cal = calibrate()
    cal_failed = [c for c in cal if not c[4]]
    findings, scanned = scan()
    verdict = "PASS" if not findings and not cal_failed else "FAIL"

    print("=" * 76)
    print("  STUDY HEADER - every file of code opens with study, author and date")
    print("=" * 76)
    print(f"  calibration cases  : {len(cal)}, failed {len(cal_failed)}")
    for name, what, got, want, ok in cal:
        print(f"  {'ok  ' if ok else 'FAIL'} {name}: {what}")
        if not ok:
            print(f"       expected {want!r}, got {got!r}")
    print(f"  files scanned      : {scanned}")
    print(f"  findings           : {len(findings)}")
    for f in findings:
        print(f"  {f['rule']:22} {f['file']}")
        print(f"      | {f['detail']}")
    print("-" * 76)
    print(f"  VERDICT: {verdict}")

    artifact.write(
        os.path.basename(OUT_JSON),
        {"verdict": verdict, "n_findings": len(findings), "findings": findings,
         "calibration": [{"predicate": n, "case": w, "got": repr(g),
                          "want": repr(x), "ok": ok} for n, w, g, x, ok in cal]},
        script=__file__,
        # The population is a list of files rather than one file, so it is stated in
        # scope instead of being hashed: hashing every tracked script here would put
        # the repository into its own artifact.
        inputs=[],
        scope={
            "population": f"{scanned} shipped .py and .ipynb files",
            "window": "n/a: this gate reads the repository as it stands now, not a "
                      "period of market data",
            "coins": "n/a: this gate reads file text and touches no market data",
        },
        started=started,
        extra_meta={"n_files_scanned": scanned,
                    "head_lines": HEAD_LINES,
                    "required_parts": [p.pattern for p, _ in PARTS],
                    "n_calibration_cases": len(cal),
                    "n_calibration_failed": len(cal_failed)},
    )

    if cal_failed:
        print("  CALIBRATION FAILED: no zero in this report can be believed.")
        return 2
    return report_gate(
        [{"name": "NO-STUDY-HEADER",
          "permitted": 0,
          "found": len(findings),
          "assumption": ("every notebook and script this repository tracks opens by "
                         "naming the study it belongs to, its author and its date. A "
                         "file that does not say what work it belongs to and who "
                         "answers for it is a file nobody can answer for once it is "
                         "copied out of this tree"),
          "method": (f"the patterns {', '.join(repr(p.pattern) for p, _ in PARTS)} "
                     f"inside the first {HEAD_LINES} lines of a script, or inside a "
                     "notebook's opening cells up to and including its first code "
                     "cell; calibrated on seven cases in memory, two of which are "
                     "shaped like the live files rather than like the template"),
          "note": ("add the header line at the top of the file, in the form "
                   f"'{STUDY_NAME} | Author: <name> | Date: <YYYY-MM-DD>'; the same "
                   "words further down are a comment, not a header"),
          "sites": findings}],
        OUT_JSON, inputs={"tree": "shared checkout/archive shipped-tree census"})


if __name__ == "__main__":
    sys.exit(main())
