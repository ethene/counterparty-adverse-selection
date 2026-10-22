#!/usr/bin/env python3
"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-08-03
References: none (repository infrastructure; it declares no quantity of its own. It
draws the graph build.py derives from the syntax trees of this tree's scripts, over the
group table typed in run/_groups.py).

THE PICTURE OF THE PIPELINE, DRAWN FROM THE GRAPH RATHER THAN BY HAND.

WHAT THIS IS FOR. A reader who opens this repository, and a reviewer who reads the
report, both ask the same first question: what feeds what. The answer already exists in
machine-readable form -- build.py reads every tracked script and returns the producers,
the artifacts and the edges between them -- but at its own resolution it is 80 producer
nodes and about a hundred edges, which no one can read. This module lifts those edges to
the level of the NINE GROUPS the pipeline is already divided into, and prints the result
as a Mermaid flowchart: nine boxes, one per group, and one arrow per ordered pair of
groups that pass a file between them.

WHY IT IS GENERATED AND NOT DRAWN. A diagram drawn by hand is a claim about the code
that stops being true the first time a script starts reading a different file, and
nothing in the repository would notice. Every label, every box and every arrow below is
read out of two places that the code itself maintains: build.graph() for the edges and
run/_groups.GROUPS for the membership and the captions. The caption under each box is the
group's `question` field verbatim -- the same sentence run/<group>.py prints and README.md
tabulates -- so the picture cannot describe a group differently from the entry point that
runs it.

WHY MERMAID AND NOT GRAPHVIZ. Three reasons, in the order they matter here. Mermaid needs
no external binary, so a stranger who clones this repository renders it with nothing
installed, while Graphviz needs `dot` on the machine. Its output is ordinary text, so it
goes into git and diffs line by line, and a changed arrow shows up in a review as a
changed line rather than as a changed image. And it renders three ways with no extra step:
GitHub draws it inside the fenced block below, an editor preview draws it, and a report
takes it as a pasted picture.

THE PICTURE FILE, AND WHY IT IS COMMITTED RATHER THAN BUILT ON DEMAND. A report wants an
image and not a fenced block, so this module also writes pipeline_diagram.png -- but only
when asked with --png, and only where mermaid-cli is installed. requirements.txt declares
Python packages and mermaid-cli is a Node program, so a stranger who clones this
repository and installs the requirements does not have it; a producer that needed it in
order to run would be a producer that does not reproduce. The picture is therefore a
committed file, exactly like the five figures the plotting scripts write, --png is how it
is refreshed, and a --png run on a machine without mermaid-cli says so and exits non-zero
rather than leaving a truncated file behind a zero exit code.

WHICH OF TWO RUNS THE RECORDED COST IS, because this node now has two and they differ by
half again. The render sits inside the timed window, so a --png run records about six
seconds and a plain run about four. What every plan of this repository needs is the plain
one, since the build never passes --png, so the artifact in the repository is left by a
plain run and the picture is refreshed separately. A results file recording six seconds
would price a rebuild of this node at a step the rebuild does not take.

WHAT MAKES THE PICTURE READABLE ON A PAGE, AND HOW THAT WAS MEASURED. The report is A4
portrait with one text column 7966 twips wide, which is 5.532 inches or 140.5 mm or 398.3
points, and its body type is 11 pt. The same template sets margins of 20 mm at the head
and 30 mm at the foot, so the text block is 247 mm tall and a figure placed across the
column has to leave room under itself for its caption inside that. A drawing placed at the
column width carries its own type onto the page at

    type on the page = declared font size * 398.3 / width of the drawing in its own units

so the readable size is decided by the width of the layout and not by anything typed here.

THE FIRST SWEEP, taken 2026-08-03 on a drawing then 1046 units wide. Each row was rendered
and its geometry read back off the rendered drawing:

    flowchart LR, the group question wrapped at 42   1876 x 1206 units   3.40 pt
    flowchart LR, shorter captions                   1827 x  608 units   3.49 pt
    flowchart TB, the same questions                 1116 x 2150 units   4.02 pt
    flowchart TB, two lines a box, 16 px             1112 x  782 units   5.73 pt
    flowchart TB, two lines a box, 24 px             1046 x 1349 units   9.14 pt

WHY THAT SWEEP IS REPEATED BELOW RATHER THAN QUOTED. It chose 24 px and recorded 9.14 pt,
and that figure stopped being true without a word from anything here. The group table
grew, the graph grew an arrow, the layout widened from 1046 units to 1320, and the same
24 px now puts 7.24 pt on the page -- under the eight points this file treats as the floor
and treats as the reason the questions were moved out of the boxes. The type size is a
property of the rendered layout, so a number for it is a cache: it is re-measured when the
layout moves, and `--measure` re-derives it from a render rather than reading it here.

THE SWEEP AS RE-MEASURED 2026-08-08, on the flowchart this tree draws today, rendered by
mermaid-cli 11.12.0 and read off the viewBox of each drawing. The last column is what the
247 mm text block has left under the figure for its caption:

    20 px   1313 x 1123 units    6.07 pt   120 mm tall   127 mm left
    24 px   1320 x 1457 units    7.24 pt   155 mm tall    92 mm left
    28 px   1327 x 1850 units    8.40 pt   196 mm tall    51 mm left
    30 px   1331 x 2047 units    8.98 pt   216 mm tall    31 mm left
    32 px   1335 x 2256 units    9.55 pt   238 mm tall    10 mm left
    36 px   1342 x 2548 units   10.68 pt   267 mm tall      none
    40 px   1485 x 2972 units   10.73 pt   281 mm tall      none

Five findings came out of the two sweeps and each one is a constant or a refusal below.

THE WIDTH IS SET BY THE LAYOUT AND NOT BY THE TEXT. Cutting the captions under flowchart
LR moved the width from 1876 to 1827 units and the type from 3.40 to 3.49 pt, which is
nothing: nine boxes stand side by side either way. Turning the flow to TB is what moves
it, because the widest rank then holds three or four boxes instead of nine.

A LARGER DECLARED FONT MAKES THE TYPE LARGER ON THE PAGE, which is the opposite of the
first guess. Box padding, node spacing and Mermaid's own wrapping width are fixed pixel
counts that do not scale with the font, so raising the font raises the share of the
drawing that is type rather than air: the width moves 1313 to 1342 units across a font
that doubles, and the type moves 6.07 pt to 10.68 pt with it.

WHAT STOPS IT IS THE PAGE AND NOT THE TYPE, and the first sweep put that boundary in the
wrong place. It read the ceiling at about 25 px; on today's wider drawing the type keeps
growing to 36 px, and what runs out first is the page. At 32 px the figure is 238 mm tall
against a 247 mm text block, so its caption does not fit under it, and past 36 px the
title becomes the widest thing on the drawing, the width jumps from 1342 to 1485 units,
and the type stops moving at all. 28 px is taken rather than 30 or 31 because the 51 mm it
leaves is a rank of this flowchart: a tenth group added to the table lengthens the drawing
by about one rank, which is 32 mm at this size, and the figure still holds its page.

A WIDER TEXT WRAP IS THE LEVER THAT LOOKS RIGHT AND LOSES. Boxes cap at 260 units, so
letting their text wrap later makes them shorter and the drawing wider, and the width is
what the type is divided by: at 24 px, moving Mermaid's wrapping width from its default
200 to 400 took the drawing from 1320 x 1457 to 1889 x 1061 units and the type from
7.24 pt down to 5.06 pt. It is measured here so that it is not tried again.

A BOX CARRIES THE STEP AND NOT THE QUESTION, and the question is not lost. Each question
is three wrapped lines; nine boxes of three lines make a drawing 7.5 inches tall whose type
is back under 8 pt. Both the step and the question are typed in run/_groups.py and neither
is written here, so the picture still cannot describe a group differently from the entry
point that runs it. The full question is printed in the table under the picture, where a
long sentence costs no legibility at all.

WHAT THE NUMBER ON AN ARROW COUNTS, because two different counts are defensible and only
one is stated. It is the number of READ EDGES crossing that group boundary: one for each
(artifact, consuming node) pair, so an artifact read by three nodes of another group
counts three. The alternative -- distinct artifacts crossing -- is printed beside it in
the reconciliation table, because the two answer different questions and quoting one for
the other is how a count comes out right and about the wrong thing.

THE RECONCILIATION, AND WHY IT IS PRINTED RATHER THAN ASSUMED. Every read edge of the
graph falls into exactly one of three buckets: inside one group, across two groups, or
touching a node that no group claims. The three must sum to the total, and --check exits
non-zero when they do not, when a declared group has no arrow at all, when a group names a
node the graph does not hold, or when two groups claim one node. Nodes no group claims are
NOT silently dropped from the count: they are named, and the edges touching them are
reported as their own bucket, because an edge that vanishes from a picture of the pipeline
is exactly the failure this file exists to prevent.

WHAT IT WRITES, AND WHY THERE ARE TWO FILES. The picture goes into build_diagram.md,
which is for a person: it renders on GitHub, it diffs line by line, and a report takes it
as a pasted image. The counts behind the picture go into build_diagram_results.json,
which is for the repository's own instruments, and it carries the service block
artifact.py stamps on every results file -- the producer and its hash, the two
declarations this run stands on and theirs, the population, the elapsed seconds.

Until 2026-08-03 only the first of the two existed, and the cost was not that a number
was missing. A producer that writes no results file is invisible to both freshness guards
of this tree, because each of them compares an artifact against the hash of its producer
and there was no artifact here to open; the node had no recorded run time, so any plan
that summed what a rebuild costs was summing over a hole; and a caption assembled from
the registry of quantities could bind no record at all to this diagram and had to say so
in the caption itself. The document is a picture of the counts and the results file is
the counts, which is the same division of labour every other node of this tree keeps.

    uv run --no-project --with-requirements requirements.txt python3 build_diagram.py
    uv run --no-project --with-requirements requirements.txt python3 build_diagram.py --png
    uv run --no-project --with-requirements requirements.txt python3 build_diagram.py --check
    uv run --no-project --with-requirements requirements.txt python3 build_diagram.py --group money
    uv run --no-project --with-requirements requirements.txt python3 build_diagram.py --measure
    uv run --no-project --with-requirements requirements.txt python3 build_diagram.py --selftest
"""
import argparse
import datetime
import hashlib
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import artifact                                                         # noqa: E402
import build                                                            # noqa: E402
from run._groups import GROUPS                                          # noqa: E402

OUT_NAME = "build_diagram.md"
# The results file, named after the producer rather than after the picture, because what
# it records is what this node computed and the picture is one of its two outputs.
OUT_JSON_NAME = "build_diagram_results.json"
# The rendered picture, named after what it shows rather than after the producer, because
# it sits beside the five figures of the report and a reader picks it out of that row.
OUT_PNG_NAME = "pipeline_diagram.png"

# THE FOUR NUMBERS THE READABLE SIZE STANDS ON, each one measured rather than chosen. The
# derivation and both sweeps are in the module docstring; what they buy is 8.40 pt of type
# on the 5.532-inch column of the report, against 7.24 pt at the 24 px this drawing
# carried until 2026-08-08 and 3.40 pt under the left-to-right layout before that, on body
# text of 11 pt. Change any of them and re-measure, and re-measure when nothing here
# changes either: the type size on the page is not a property of this file, it is a
# property of the rendered layout, and the layout widens whenever the graph does. That is
# what `--measure` is for, and it is how the 9.14 pt this comment used to claim was found
# to have become 7.24 without a line of this file moving.
DIRECTION = "TB"            # the flow. LR puts nine boxes in one rank and costs 5.7 pt
# Declared type, re-measured 2026-08-08 on the flowchart this tree draws today. 24 px was
# chosen when the drawing was 1046 units wide and gave 9.14 pt on the column; the drawing
# is 1320 units wide now and the same 24 px gives 7.24 pt, under the floor. 28 px gives
# 8.40 pt and leaves 51 mm of the 247 mm text block under the figure, which is enough for
# the caption and a rank of growth. The ceiling here is the page, not the type: see the
# sweep in the module docstring, and `--measure` to take it again.
BASE_FONT_PX = 28
NODE_SPACING = 20           # air between boxes of one rank, in fixed pixels
RANK_SPACING = 25           # air between ranks, in fixed pixels
# The page the picture is placed on, both numbers read off the report template rather than
# assumed: the 1col template declares a text column of 7966 twips, which is 398.3 points
# and 140.5 mm, and margins of 20 mm and 30 mm, which leave a text block 247 mm tall.
# They are constants of the template and not of this drawing, and they are here because
# the only thing that turns a declared font into a readable one is the width it lands on.
COLUMN_PT = 398.3
COLUMN_MM = 140.5
PAGE_TEXT_MM = 247.0
# The scale mermaid-cli renders the picture at. 3 puts about 425 pixels on each inch of
# the report column, which is denser than the 130 to 150 the five plotted figures carry.
PNG_SCALE = 3
MMDC = "mmdc"

# The title drawn above the flowchart, in the form the five plotted figures of this report
# already use: one sentence that says what the picture shows, with no figure number in it,
# because the numbering belongs to the document the figure is placed in and not to the
# figure. Kept under about eighty-five characters: past that the title itself becomes the
# widest thing on the drawing and starts setting the width, which costs type size.
# WHAT THE NUMBER IS, not what the arrow is. Until 2026-08-04 this read "every arrow is
# a file one group writes and another reads", which names the arrow and leaves the only
# number on the drawing unnamed -- and misnames it, because the number is a count of
# reads and not a file: a file written by the group at the tail and read by three scripts
# of the group at the head counts three. A figure owes its reader the scale as well as the
# axes, and a flowchart's one scale is the integer on its arrows.
TITLE = ("Nine groups of scripts. A number on an arrow counts file reads, and a "
         "thick outline marks a group that reads the raw archive")

# The two files this producer genuinely stands on, hashed as its declared inputs. Neither
# is an artifact, so neither becomes an edge of the graph; they are named because a change
# in either moves every count below, and a reader asking why a number moved should not
# have to guess which of the two moved it. build.py derives the graph from the syntax
# trees, run/_groups.py types the membership and the captions.
IN_BUILD = os.path.join(HERE, "build.py")
IN_GROUPS = os.path.join(HERE, "run", "_groups.py")

# How wide a caption line is allowed to be before it wraps. Chosen so the widest of the
# nine questions makes six lines rather than one line no screen holds.
WRAP = 42


# =====================================================================
# 1. LIFTING THE EDGES
#
# One function, so that the picture, the reconciliation and the check all read the same
# numbers. A second traversal kept beside this one would drift from it, which is the
# failure run/_groups.py already documents for hand-kept node lists.
# =====================================================================

UNCLAIMED = None            # the group of a node no entry in GROUPS names


def lift(graph, groups):
    """Group-level edges of `graph` under the membership typed in `groups`.

    Returns a dict with everything any caller of this module needs, so that no caller
    walks the graph a second time:

      owner        node key -> group id, for every node some group claims
      unclaimed    node keys no group claims, sorted
      stale        (group id, node key) a group names and the graph does not hold
      duplicate    (node key, first group, second group) claimed twice
      edges        (src group, dst group) -> read-edge count, groups only
      artifacts    (src group, dst group) -> set of artifact names crossing
      within       read edges whose two ends are in one group
      touching     [(producer key, artifact, consumer key, src group, dst group)]
                   for every read edge with an unclaimed node on either end
      nodes        group id -> node keys, sorted
      tape         group id -> how many of its nodes walk the raw archive
    """
    owner, duplicate, stale = {}, [], []
    for entry in groups:
        for key in entry["nodes"]:
            if key in owner:
                duplicate.append((key, owner[key], entry["id"]))
            owner[key] = entry["id"]
            if key not in graph.nodes:
                stale.append((entry["id"], key))

    made_by = {}
    for key, node in graph.nodes.items():
        for name in node.outputs:
            made_by.setdefault(name, set()).add(key)

    edges, artifacts, touching = {}, {}, []
    within = 0
    for key, node in graph.nodes.items():
        dst = owner.get(key, UNCLAIMED)
        for name in node.inputs:
            for producer in made_by.get(name, ()):
                src = owner.get(producer, UNCLAIMED)
                if src is UNCLAIMED or dst is UNCLAIMED:
                    touching.append((producer, name, key, src, dst))
                elif src == dst:
                    within += 1
                else:
                    edges[(src, dst)] = edges.get((src, dst), 0) + 1
                    artifacts.setdefault((src, dst), set()).add(name)

    nodes, tape = {}, {}
    for entry in groups:
        nodes[entry["id"]] = sorted(k for k in entry["nodes"] if k in graph.nodes)
        tape[entry["id"]] = sum(1 for k in nodes[entry["id"]]
                                if graph.nodes[k].stage == "tape")
    return {
        "owner": owner,
        "unclaimed": sorted(k for k in graph.nodes if k not in owner),
        "stale": stale,
        "duplicate": duplicate,
        "edges": edges,
        "artifacts": artifacts,
        "within": within,
        "touching": touching,
        "nodes": nodes,
        "tape": tape,
    }


def totals(lifted):
    """The three buckets and their sum, which is every read edge of the graph."""
    across = sum(lifted["edges"].values())
    return {
        "within_one_group": lifted["within"],
        "across_two_groups": across,
        "touching_an_unclaimed_node": len(lifted["touching"]),
        "read_edges_total": lifted["within"] + across + len(lifted["touching"]),
        "arrows_between_groups": len(lifted["edges"]),
        "artifacts_crossing_a_boundary": len(
            {name for names in lifted["artifacts"].values() for name in names}),
    }


# =====================================================================
# 2. WRITING MERMAID
#
# Mermaid reads four characters specially inside a quoted label -- the quote itself, the
# hash that opens an entity code, and the angle brackets -- so they are replaced rather
# than passed through. Nothing else about the caption is altered: it is the group's
# question as typed, wrapped, because a caption that paraphrases the entry point is a
# second description that can go stale against the first.
# =====================================================================

def _escape(text):
    return (text.replace("&", "&amp;").replace('"', "&quot;")
                .replace("#", "&#35;").replace("<", "&lt;").replace(">", "&gt;"))


def _label(title, caption):
    # break_on_hyphens is off because the captions carry hyphenated terms the report
    # uses -- counterparty-resolved, cross-sectional -- and a wrap that splits one of
    # them across a line break renames the term in the picture.
    wrapped = textwrap.wrap(" ".join(caption.split()), WRAP, break_on_hyphens=False)
    lines = [_escape(title)] + [_escape(line) for line in wrapped]
    return "<br/>".join(lines)


def _box(entry, lifted):
    """The two lines one group's box carries, both read out of run/_groups.py.

    Line one names the group and how many nodes of the graph it claims. Line two is the
    step, split on the comma that the step field already carries, so the number and the
    name of the step are two halves of one declared string rather than two things typed
    twice and able to disagree.

    ONE RULE FOR ALL NINE, WHICH IS THE POINT. A picture whose boxes were shortened one
    at a time would be a hand-drawn picture wearing a generated one's clothes: the next
    group added to the table would come out long and nobody would notice. Everything here
    is a field lookup and a partition, so a tenth group is drawn the same way as the nine.
    """
    number, _sep, name = entry["step"].partition(",")
    return [f"{entry['id']} -- {len(lifted['nodes'][entry['id']])} scripts",
            f"step {number.strip()}: {name.strip()}"]


def _yaml_quote(text):
    """The title as a double-quoted YAML scalar.

    Mermaid reads a diagram title out of a YAML front matter block, so a bare colon
    followed by a space ends the key and the whole render fails. Measured on this file's
    own title, which carries such a colon: unquoted it takes the renderer down with a
    parser error and no picture at all, which is a failure that at least announces
    itself, and quoted it draws.
    """
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _front_matter():
    """The title block and the settings directive, as the two lines above the flowchart.

    The directive travels inside the source rather than as a command-line option to the
    renderer, because the source is what goes into git, what GitHub draws and what the
    picture is rendered from. A layout setting kept outside it would mean the drawing in
    the repository and the drawing in the report were shaped by different numbers.
    """
    return [
        "---",
        f"title: {_yaml_quote(TITLE)}",
        "---",
        "%%{init: {'flowchart': {'nodeSpacing': " + str(NODE_SPACING)
        + ", 'rankSpacing': " + str(RANK_SPACING) + "}, 'themeVariables': {'fontSize': '"
        + str(BASE_FONT_PX) + "px'}, 'themeCSS': '.flowchartTitleText { font-size: "
        + str(BASE_FONT_PX) + "px; }'}}%%",
    ]


# The characters a Mermaid label may not carry unquoted, and that this module escapes
# or must never emit. Checked on the produced text rather than trusted, because a
# diagram that does not parse fails silently: the renderer shows nothing and the file
# still looks well formed in a diff.
HAZARDS = ('"', "#", "<", ">")


def _lint(text):
    """Refutations against the emitted Mermaid, as a list of strings. Empty is clean."""
    bad = []
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        # THE FRONT MATTER IS YAML AND NOT MERMAID, so it is refuted by its own rule
        # rather than by the label rules below, which would read the title as a label and
        # ask the wrong questions of it. The rule that matters is the one that has already
        # broken a render: an unquoted colon inside the title ends the key.
        if stripped.startswith("title:"):
            value = stripped[len("title:"):].strip()
            if not (value.startswith('"') and value.endswith('"') and len(value) > 1):
                bad.append(f"line {number}: the front matter title is not a quoted YAML "
                           "scalar, so a colon inside it ends the key and nothing draws")
            elif re.search(r'(?<!\\)"', value[1:-1]):
                bad.append(f"line {number}: an unescaped quote inside the front matter "
                           "title closes the scalar early")
            continue
        if not stripped or stripped.startswith(("flowchart", "subgraph", "end", "---",
                                                "%%{", "direction", "classDef",
                                                "class ")):
            continue
        # EXACTLY TWO QUOTES, OR NONE. Every line this module emits carries at most one
        # label, so any other count means a quote reached the text unescaped. Counting
        # parity alone is not enough and the difference is the whole point: a raw quote
        # inside a label leaves an EVEN count, splits the label in two at the wrong
        # place, and passes a parity test while breaking the render.
        if stripped.count('"') not in (0, 2):
            bad.append(f"line {number}: {stripped.count(chr(34))} quotes, so a label "
                       f"holds one that was never escaped")
        for start, close in (("[", "]"), ("(", ")"), ("{", "}")):
            if stripped.count(start) != stripped.count(close):
                bad.append(f"line {number}: {start} and {close} do not balance")
        for label in _labels_of(stripped):
            # The one tag a label is allowed to hold is the line break this module puts
            # there itself, so it is removed before the hazard test rather than made an
            # exception inside it.
            label = label.replace("<br/>", " ")
            for hazard in HAZARDS:
                if hazard in label:
                    bad.append(f"line {number}: an unescaped {hazard!r} inside a label")
            if "-->" in label:
                bad.append(f"line {number}: an arrow inside a label ends it early")
    return bad


def _labels_of(line):
    """Every quoted label on one line."""
    parts = line.split('"')
    return parts[1::2]


def _ident(text):
    """A Mermaid node id: letters, digits and underscores, and never empty."""
    out = "".join(ch if ch.isalnum() else "_" for ch in text)
    return "g_" + out


def mermaid_top(graph, groups, lifted):
    """The nine-box flowchart: one box per declared group, one arrow per ordered pair."""
    order = [entry["id"] for entry in groups]
    rank = {gid: i for i, gid in enumerate(order)}
    out = _front_matter() + [f"flowchart {DIRECTION}"]
    for entry in groups:
        gid = entry["id"]
        label = "<br/>".join(_escape(line) for line in _box(entry, lifted))
        out.append(f'  {_ident(gid)}["{label}"]')
    out.append("")
    for (src, dst) in sorted(lifted["edges"],
                             key=lambda k: (-lifted["edges"][k], rank.get(k[0], 99),
                                            rank.get(k[1], 99))):
        count = lifted["edges"][(src, dst)]
        out.append(f'  {_ident(src)} -->|{count}| {_ident(dst)}')
    out.append("")
    # The groups that walk the raw archive are marked, because "which of these costs
    # hours" is the second question anyone asks of a pipeline picture and the stage is
    # already recorded per node.
    #
    # The mark is explained in the TITLE, not here. Until 2026-08-30 the thick outline
    # sat on five of the nine boxes with no key anywhere -- not in the box, not in the
    # caption, not in the note the report puts under the figure -- so a reader saw a
    # distinction drawn and never learned what it distinguished. A difference shown
    # without a key is worse than one not shown: the reader knows something is being
    # said and cannot read it.
    #
    # The first attempt put the key in a box of its own. It rendered in the same fill,
    # the same border and the same rank as the nine real groups, so it read as a tenth
    # group with the arrows of its neighbours passing through it, and the first reader
    # shown the picture did not find the key at all. The height measurement did not see
    # that and could not: it counts millimetres, not whether a box reads as a legend.
    # The title already carries the other convention of this drawing -- what the number
    # on an arrow means -- so the key belongs beside it, in the one place on the canvas
    # that cannot be mistaken for a node.
    tape = [entry["id"] for entry in groups if lifted["tape"][entry["id"]]]
    if tape:
        out.append("  classDef tape stroke-width:3px")
        out.append("  class " + ",".join(_ident(g) for g in tape) + " tape")
    return "\n".join(out)


def mermaid_group(graph, groups, lifted, gid):
    """The second level: the nodes of one group, and the groups it trades files with."""
    entry = next((e for e in groups if e["id"] == gid), None)
    if entry is None:
        raise SystemExit(f"no group named {gid!r}; the nine are "
                         + ", ".join(e["id"] for e in groups))
    keys = lifted["nodes"][gid]
    ids = {key: f"n_{i}" for i, key in enumerate(keys)}
    out = ["flowchart LR",
           f'  subgraph {_ident(gid)}["{_label(gid, entry["question"])}"]',
           "    direction LR"]
    for key in keys:
        node = graph.nodes[key]
        title = key + ("  [tape]" if node.stage == "tape" else "")
        made = ", ".join(node.outputs) or "writes nothing this graph can see"
        out.append(f'    {ids[key]}["{_label(title, made)}"]')
    out.append("  end")

    made_by = {}
    for key, node in graph.nodes.items():
        for name in node.outputs:
            made_by.setdefault(name, set()).add(key)

    # The stub arrows carry READ EDGES, the same quantity the top-level arrows carry,
    # so that a reader who compares the two levels compares one number with itself. An
    # earlier draft counted distinct artifacts here and read edges there, which made the
    # data-to-money arrow say 3 on one picture and 10 on the other with no word between
    # them saying they were different questions.
    inside, incoming, outgoing = [], {}, {}
    unnamed = "(no group claims it)"
    for key in keys:
        for name in graph.nodes[key].inputs:
            for producer in made_by.get(name, ()):
                if producer in ids:
                    inside.append((producer, name, key))
                else:
                    src = lifted["owner"].get(producer, UNCLAIMED) or unnamed
                    incoming[src] = incoming.get(src, 0) + 1
    made_here = {name for key in keys for name in graph.nodes[key].outputs}
    for key, node in graph.nodes.items():
        if key in ids:
            continue
        dst = lifted["owner"].get(key, UNCLAIMED) or unnamed
        for name in node.inputs:
            if name in made_here:
                outgoing[dst] = outgoing.get(dst, 0) + 1

    for producer, name, key in sorted(set(inside)):
        out.append(f'  {ids[producer]} -->|{_escape(name)}| {ids[key]}')
    for src, count in sorted(incoming.items()):
        out.append(f'  {_ident(src)}_in["{_escape(src)}"] -->|{count}| {_ident(gid)}')
    for dst, count in sorted(outgoing.items()):
        out.append(f'  {_ident(gid)} -->|{count}| {_ident(dst)}_out["{_escape(dst)}"]')
    return "\n".join(out)


# =====================================================================
# 2b. THE PICTURE
#
# Two functions and they answer two different questions. render_png() makes the file;
# picture_state() says what the file on disk is. They are kept apart because only the
# second may go into the results file: the first needs mermaid-cli, and a results file
# whose contents depended on whether a machine had mermaid-cli installed would differ
# between two correct runs and make every provenance comparison of this artifact fail.
# =====================================================================

def _png_pixels(path):
    """Width and height out of a PNG header, or None if the file is not one.

    Read from the IHDR chunk rather than with an imaging library, because the tree's
    requirements declare none for this and a picture's own geometry is thirteen bytes.
    """
    try:
        with open(path, "rb") as handle:
            head = handle.read(24)
    except OSError:
        return None
    if len(head) < 24 or head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", head[16:24])
    return width, height


def _viewbox(path):
    """Width and height of a rendered drawing in its own units, or None if it has none.

    The PNG says how many pixels it is and that is not the question: the type size on a
    report page is set by how many of the drawing's own units its width is, and only the
    SVG carries those. Read with a pattern for the same reason _png_pixels is read off
    thirteen bytes -- a drawing's geometry is one attribute, and an XML parser for it
    would be a dependency requirements.txt does not declare.
    """
    try:
        with open(path, "r", encoding="utf-8") as handle:
            head = handle.read(8192)
    except (OSError, UnicodeDecodeError):
        return None
    found = re.search(r'viewBox="\s*[-\d.]+\s+[-\d.]+\s+([\d.]+)\s+([\d.]+)\s*"', head)
    if not found:
        return None
    return float(found.group(1)), float(found.group(2))


def picture_state(path):
    """What the committed picture is, as facts about the bytes on disk and nothing else.

    Population: the one file OUT_PNG_NAME beside this script. Predicate: does it exist,
    what do its bytes hash to, and what does its own header say its size is. No verdict
    about whether it is current lives here, because that question needs mermaid-cli and
    the answer would then depend on the machine rather than on the repository.
    """
    if not os.path.exists(path):
        return {
            "file": OUT_PNG_NAME,
            "present": False,
            "sha256": None,
            "pixels": None,
            "what_this_is": (
                "the rendered flowchart, absent from this working tree. Run this "
                "producer with --png on a machine that has mermaid-cli to write it"),
        }
    size = _png_pixels(path)
    return {
        "file": OUT_PNG_NAME,
        "present": True,
        "sha256": artifact.sha256_file(path),
        "pixels": None if size is None else f"{size[0]}x{size[1]}",
        "what_this_is": (
            "the flowchart above, rendered by mermaid-cli at scale "
            f"{PNG_SCALE} on a white ground and committed to this repository. It is "
            "committed rather than built on demand because mermaid-cli is a Node "
            "program and requirements.txt declares Python packages, so a stranger who "
            "installs the requirements can read the picture without being able to "
            "render it. Refresh it with --png"),
    }


def render_png(text, out_path):
    """Render the drawn flowchart to out_path with mermaid-cli. Returns (ok, message).

    A missing renderer is reported and is not a crash and is not a pass: the caller
    exits non-zero with the message below, because a --png run that printed nothing and
    returned zero would be the one failure direction that travels -- a measurement that
    reads as success where there was none.
    """
    if shutil.which(MMDC) is None:
        return False, (
            f"mermaid-cli ({MMDC}) is not on PATH, so nothing was rendered and "
            f"{OUT_PNG_NAME} on disk is exactly as it was. Nothing in this repository "
            f"needs it in order to be read: the flowchart source is in {OUT_NAME} and "
            "the rendered picture is committed beside it. To refresh the picture, "
            "install the renderer with `npm install -g @mermaid-js/mermaid-cli` and "
            "run this file again with --png.")
    with tempfile.TemporaryDirectory() as scratch:
        source = os.path.join(scratch, "flowchart.mmd")
        with open(source, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
        # The exit code is taken off the call itself, before anything is done with the
        # output, because a code read after a pipe is the code of the pipe.
        proc = subprocess.run(
            [MMDC, "-i", source, "-o", out_path, "-b", "white",
             "-s", str(PNG_SCALE), "-q"],
            capture_output=True, text=True)
        code = proc.returncode
        noise = (proc.stderr or proc.stdout or "").strip()
    if code != 0:
        return False, (f"{MMDC} exited {code} and the picture was not replaced. What it "
                       f"said:\n{noise[:800]}")
    size = _png_pixels(out_path)
    where = f"{size[0]}x{size[1]} pixels" if size else "a file that is not a PNG"
    return True, f"{OUT_PNG_NAME}: {where}"


def measure_layout(text):
    """What this drawing puts on the report page. Returns (ok, a table or a message).

    THE NUMBER THIS ANSWERS is the one the module docstring reasons about and the one a
    figure is accepted or refused on: the size of the type in the boxes once the picture
    is placed across the 140.5 mm column, and the height the figure then takes out of the
    247 mm text block. Both come off the rendered drawing rather than off the constants,
    because the width is decided by the layout: the same declared font gave 9.14 pt on a
    drawing of 1046 units and 7.24 pt on the same flowchart once it had grown to 1320.

    IT RENDERS TO SVG AND NOT TO PNG on purpose. mermaid-cli fits a PNG into a fixed
    viewport, so every picture it writes here is 2352 pixels wide whatever the drawing is
    and its pixel count answers a different question. The SVG carries the drawing's own
    units, which is what the type size divides by.

    A missing renderer is reported and is not a zero, on the same rule render_png keeps:
    a measurement that could not be taken must not read as a measurement that came out.
    """
    if shutil.which(MMDC) is None:
        return False, (
            f"mermaid-cli ({MMDC}) is not on PATH, so the drawing could not be rendered "
            "and its width on the page could not be measured. Nothing was read and "
            "nothing is claimed. Install it with `npm install -g "
            "@mermaid-js/mermaid-cli` and run this file again with --measure.")
    with tempfile.TemporaryDirectory() as scratch:
        source = os.path.join(scratch, "flowchart.mmd")
        with open(source, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
        drawn = os.path.join(scratch, "flowchart.svg")
        proc = subprocess.run([MMDC, "-i", source, "-o", drawn, "-b", "white", "-q"],
                              capture_output=True, text=True)
        code = proc.returncode
        noise = (proc.stderr or proc.stdout or "").strip()
        size = _viewbox(drawn) if code == 0 else None
    if code != 0:
        return False, (f"{MMDC} exited {code} and nothing was measured. What it "
                       f"said:\n{noise[:800]}")
    if size is None:
        return False, ("the renderer wrote a drawing with no viewBox, so its width in "
                       "its own units could not be read and no type size follows from it")
    width, height = size
    tall = COLUMN_MM * height / width
    return True, {
        "declared_font_px": BASE_FONT_PX,
        "width_units": width,
        "height_units": height,
        "type_pt_on_the_column": BASE_FONT_PX * COLUMN_PT / width,
        "figure_mm_at_column_width": tall,
        "page_mm_left_under_it": PAGE_TEXT_MM - tall,
    }


def picture_verdict(text, out_path):
    """Is the committed picture the picture today's flowchart draws? Three answers.

    MATCHES, DIFFERS, and NOT CHECKED, and the third is neither of the first two on
    purpose. A machine without mermaid-cli cannot answer the question, and reporting it
    as current would be a check that passes by being unable to run -- which is exactly
    the shape of a silent guard this repository has already paid for once.

    A DIFFERS carries two possible causes and names both, because they are not the same
    repair: the picture is stale against a changed flowchart, or the renderer here is a
    different build from the one that made the committed file.
    """
    if not os.path.exists(out_path):
        return "DIFFERS", f"{OUT_PNG_NAME} is not in this working tree at all"
    if shutil.which(MMDC) is None:
        return "NOT CHECKED", (
            f"mermaid-cli is not on PATH, so whether {OUT_PNG_NAME} still draws today's "
            "flowchart could not be established either way")
    with tempfile.TemporaryDirectory() as scratch:
        fresh = os.path.join(scratch, OUT_PNG_NAME)
        ok, message = render_png(text, fresh)
        if not ok:
            return "NOT CHECKED", message
        here, there = artifact.sha256_file(out_path), artifact.sha256_file(fresh)
    if here == there:
        return "MATCHES", f"{OUT_PNG_NAME} is byte for byte what this flowchart renders"
    return "DIFFERS", (
        f"{OUT_PNG_NAME} hashes {here[:12]} and a fresh render of today's flowchart "
        f"hashes {there[:12]}. Either the flowchart moved and the picture was not "
        "refreshed with --png, or this machine's mermaid-cli is a different build from "
        "the one that rendered the committed file")


# =====================================================================
# 3. THE DOCUMENT
# =====================================================================

def document(graph, groups, lifted):
    counts = graph.counts()
    t = totals(lifted)
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        "# The pipeline, group by group",
        "",
        f"GENERATED FILE. Producer `{os.path.basename(__file__)}`, written {now}. "
        "Every box, arrow and caption below is read from `build.graph()` and from the "
        "`GROUPS` table in `run/_groups.py`; nothing here is typed by hand, and an edit "
        "to this file is overwritten by the next run of the producer.",
        "",
        "Each box is one group of the pipeline and carries the step it is the code of, "
        "in the words run/_groups.py declares. The number on an arrow is how many times "
        "a file written by the group at the tail is read by a script of the group at "
        "the head. A thick border marks a group that walks the raw archive, which is "
        "what makes a recompute cost hours rather than seconds. The question each group "
        "answers is one sentence long and is printed in the table below rather than "
        "inside a box: nine boxes of three lines each shrink the type on a report page "
        "to under eight points, and the whole point of a picture is that it can be "
        "read.",
        "",
        f"The same flowchart is committed as a picture, `{OUT_PNG_NAME}`, for the "
        "report to place. It is rendered from the block below by mermaid-cli, which is "
        "a Node program and therefore not something `requirements.txt` can install, so "
        "the picture is a file in this repository rather than a build step. "
        "`build_diagram.py --png` refreshes it where mermaid-cli is installed and says "
        "so where it is not, and `--check` reports whether the committed picture is "
        "still what this flowchart draws.",
        "",
        "The picture is drawn to be placed across the whole text column of the report, "
        f"which the template sets at {COLUMN_MM:.0f} mm. At that width the type in the "
        "boxes measured 8.40 pt on 2026-08-08 against body text of 11 pt, and the "
        "figure stands 196 mm tall, which leaves 51 mm of the page under it for the "
        "caption. Placing it narrower shrinks the type in proportion and is what the "
        "layout was chosen against: `build_diagram.py --measure` renders the flowchart "
        "and reads those three numbers back off it rather than restating them.",
        "",
        "```mermaid",
        mermaid_top(graph, groups, lifted),
        "```",
        "",
        "## The groups",
        "",
        "| group | step | entry point | scripts | of them walk the archive | "
        "the question it answers |",
        "|---|---|---|---|---|---|",
    ]
    for entry in groups:
        gid = entry["id"]
        # The pipe is escaped rather than trusted absent: one of these sentences growing
        # a pipe would silently split a table cell in two and move every later column.
        question = entry["question"].replace("|", "\\|")
        lines.append(f"| `{gid}` | {entry['step']} | `{entry['entry']}` | "
                     f"{len(lifted['nodes'][gid])} | {lifted['tape'][gid]} | "
                     f"{question} |")
    lines += [
        "",
        "## Every arrow, and what crosses it",
        "",
        "`read edges` counts one for each pair of an artifact and a script that reads "
        "it. `distinct artifacts` counts the files themselves, so a file read by three "
        "scripts of one group is three read edges and one artifact. The two are "
        "different questions and are printed apart on purpose.",
        "",
        "| from | to | read edges | distinct artifacts |",
        "|---|---|---|---|",
    ]
    for key in sorted(lifted["edges"], key=lambda k: (-lifted["edges"][k], k)):
        lines.append(f"| `{key[0]}` | `{key[1]}` | {lifted['edges'][key]} | "
                     f"{len(lifted['artifacts'][key])} |")
    lines += [
        "",
        "## The count, and the predicate that took it",
        "",
        "Population: every read edge of the dependency graph, that is every pair of a "
        "script and an artifact it reads whose producer this tree holds. Predicate: the "
        "producer's group against the consumer's group, under the membership typed in "
        "`run/_groups.py`. The three buckets are exhaustive and disjoint, so they sum to "
        "the total, and `--check` fails when they do not.",
        "",
        "| quantity | value |",
        "|---|---|",
        f"| scripts scanned | {counts['scripts_scanned']} |",
        f"| producer nodes | {counts['producer_nodes']} |",
        f"| artifacts produced | {counts['artifacts_produced']} |",
        f"| groups declared | {len(groups)} |",
        f"| read edges, total | {t['read_edges_total']} |",
        f"| of them inside one group | {t['within_one_group']} |",
        f"| of them across two groups | {t['across_two_groups']} |",
        f"| of them touching a node no group claims | "
        f"{t['touching_an_unclaimed_node']} |",
        f"| arrows drawn between groups | {t['arrows_between_groups']} |",
        f"| distinct artifacts crossing a boundary | "
        f"{t['artifacts_crossing_a_boundary']} |",
        f"| cycles build.py reports | {counts['cycles']} |",
    ]
    if lifted["unclaimed"]:
        lines += [
            "",
            "## What is not on the picture, and why",
            "",
            f"{len(lifted['unclaimed'])} producer nodes belong to no group, so no box "
            "holds them and the edges touching them are counted in their own bucket "
            "above rather than drawn. They are named here rather than dropped, because a "
            "picture that quietly omits part of the pipeline is worse than one that says "
            "what it omits. `run/<group>.py --census` reports the same list.",
            "",
        ]
        for key in lifted["unclaimed"]:
            lines.append(f"- `{key}`")
        if lifted["touching"]:
            lines += ["", "The edges that reach them:", ""]
            for producer, name, key, src, dst in sorted(lifted["touching"]):
                lines.append(
                    f"- `{producer}` [{src or 'no group'}] writes `{name}`, "
                    f"read by `{key}` [{dst or 'no group'}]")
    lines.append("")
    return "\n".join(lines)


# =====================================================================
# 3b. THE SAME COUNTS AS A RESULTS FILE
#
# Every number here comes out of the one `lifted` the document above was written from,
# so the picture and the file cannot disagree: a second traversal to fill this block
# would be a second answer to one question, which is the failure lift() exists to end.
#
# NOTHING HERE MOVES BETWEEN TWO RUNS OVER AN UNCHANGED TREE, and that is a property
# worth stating rather than hoping for. artifact.py's comparison recomputes a producer
# into a scratch directory and diffs everything outside _meta["run"]; a field that
# carried the time of the run, or the hash of a document that carries it, would report a
# difference on every single comparison and stop being read. That is exactly why the
# drawn Mermaid is hashed here and the written document is not: the document opens with
# the timestamp of its own run and the flowchart does not.
# =====================================================================

def _scanned_digest(graph):
    """One hash over every script the graph was derived from, with the count beside it.

    WHY A DIGEST AND NOT A LIST OF INPUTS. This producer's real input is the whole
    tracked tree: build.py reads every script and returns the edges between them, so an
    edit to any one of them can move a count in this file. Declaring a hundred inputs
    would state that faithfully and cost a hundred hash records for a question nobody
    asks file by file; declaring none would leave the freshness guards comparing this
    artifact against its producer alone, which is the very blindness that left this node
    unwatched. One digest over the sorted (name, hash) pairs answers the question that is
    actually asked -- has anything the graph is derived from moved -- with one field.

    Unreadable files are COUNTED rather than skipped. A scanned script that cannot be
    opened would otherwise leave the digest looking clean while it was taken over a
    smaller population than the one it claims.
    """
    lines, unreadable = [], []
    for rel in sorted(graph.scanned):
        try:
            digest = artifact.sha256_file(os.path.join(HERE, rel))
        except OSError:
            unreadable.append(rel)
            continue
        lines.append(f"{rel} {digest}")
    return {
        "n_scripts": len(lines),
        "n_unreadable": len(unreadable),
        "unreadable": sorted(unreadable),
        "sha256": hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest(),
        "what_this_is": (
            "sha256 over the sorted lines '<script path relative to the repository "
            "root> <sha256 of its bytes>', one line per script build.py scanned. It "
            "moves when any scanned script changes, is added or is removed, and it "
            "moves for no other reason."),
    }


def results(graph, groups, lifted):
    """What this producer computed, as the payload of its results file."""
    counts = graph.counts()
    t = totals(lifted)
    rank = {entry["id"]: i for i, entry in enumerate(groups)}
    boxes = [{
        "group": entry["id"],
        "step": entry["step"],
        "entry_point": entry["entry"],
        "question": entry["question"],
        "n_scripts": len(lifted["nodes"][entry["id"]]),
        "n_scripts_walking_the_archive": lifted["tape"][entry["id"]],
        "scripts": lifted["nodes"][entry["id"]],
    } for entry in groups]
    # The drawing order of the arrows, which is the order mermaid_top emits them in, so
    # a reader comparing the file with the picture reads the two down the same column.
    arrows = [{
        "from": src,
        "to": dst,
        "read_edges": lifted["edges"][(src, dst)],
        "distinct_artifacts": len(lifted["artifacts"][(src, dst)]),
        "artifacts": sorted(lifted["artifacts"][(src, dst)]),
    } for (src, dst) in sorted(lifted["edges"],
                               key=lambda k: (-lifted["edges"][k], rank.get(k[0], 99),
                                              rank.get(k[1], 99)))]
    return {
        "boxes": {
            "n_groups_declared": len(groups),
            "n_scripts_claimed_by_a_group": sum(b["n_scripts"] for b in boxes),
            "n_groups_walking_the_archive": sum(1 for b in boxes
                                                if b["n_scripts_walking_the_archive"]),
            "by_group": boxes,
        },
        "arrows": {
            "n_arrows_drawn": t["arrows_between_groups"],
            "n_distinct_artifacts_crossing_a_boundary":
                t["artifacts_crossing_a_boundary"],
            "each": arrows,
        },
        # The three buckets every read edge of the graph falls into, exhaustive and
        # disjoint by construction, printed with their sum so the file carries the
        # reconciliation --check performs rather than only its verdict.
        "read_edges": {
            "total": t["read_edges_total"],
            "inside_one_group": t["within_one_group"],
            "across_two_groups": t["across_two_groups"],
            "touching_an_unclaimed_node": t["touching_an_unclaimed_node"],
            "buckets_sum_to_total": (
                t["read_edges_total"] == t["within_one_group"]
                + t["across_two_groups"] + t["touching_an_unclaimed_node"]),
        },
        "graph": {
            "scripts_scanned": counts["scripts_scanned"],
            "producer_nodes": counts["producer_nodes"],
            "artifacts_produced": counts["artifacts_produced"],
            "tape_nodes": counts["tape_nodes"],
            "cycles": counts["cycles"],
        },
        # Named rather than dropped, for the reason the document states: a picture that
        # quietly omits part of the pipeline is worse than one that says what it omits.
        "unclaimed_producer_nodes": lifted["unclaimed"],
        "group_entries_the_graph_does_not_hold": [
            {"group": gid, "node": key} for gid, key in lifted["stale"]],
        "nodes_claimed_by_two_groups": [
            {"node": key, "groups": [first, second]}
            for key, first, second in lifted["duplicate"]],
        "drawn_flowchart_sha256": hashlib.sha256(
            mermaid_top(graph, groups, lifted).encode("utf-8")).hexdigest(),
        # What the picture on disk IS, never whether it is current: see picture_state.
        "picture": picture_state(os.path.join(HERE, OUT_PNG_NAME)),
        # The layout settings the drawing stands on, recorded because they decide the
        # size of the type on a report page and a reader asking why the picture changed
        # shape should find the answer in the file rather than in a diff of the producer.
        "drawing_settings": {
            "direction": DIRECTION,
            "declared_font_px": BASE_FONT_PX,
            "node_spacing_px": NODE_SPACING,
            "rank_spacing_px": RANK_SPACING,
            "png_scale": PNG_SCALE,
            "what_this_buys": (
                "type of 8.40 pt on the 5.532-inch text column of the report template, "
                "against 7.24 pt at the 24 px this drawing carried until 2026-08-08 and "
                "3.40 pt under the left-to-right layout before that, on body text of "
                "11 pt. The figure is then 196 mm tall and leaves 51 mm of the 247 mm "
                "text block for its caption. The size on the page is the declared font "
                "times 398.3 divided by the width of the rendered drawing in its own "
                "units, so it is a property of the layout and not of these settings: "
                "the same 24 px read 9.14 pt while the drawing was 1046 units wide and "
                "7.24 pt once the graph had widened it to 1320 without either setting "
                "moving. The figures here were measured on 2026-08-08 and are taken "
                "again by `build_diagram.py --measure`, which renders the flowchart and "
                "reads the width back off it rather than trusting this sentence"),
        },
        "scanned_scripts": _scanned_digest(graph),
        "what_the_number_on_an_arrow_counts": (
            "READ EDGES crossing that group boundary: one for each pair of an artifact "
            "and a script of another group that reads it, so an artifact read by three "
            "scripts of one group counts three. The count of distinct artifacts is "
            "carried beside it because the two answer different questions."),
    }


# =====================================================================
# 4. THE CHECK, AND ITS CALIBRATION
#
# A predicate whose zero goes into a decision is calibrated on two opposite cases: one
# where it must fire and one where it must stay silent. One reference case cannot tell a
# predicate that is too wide from one that is too narrow, so both are built below out of
# a graph small enough to hold in the head, and --selftest runs them.
# =====================================================================

class _FakeNode:
    def __init__(self, inputs, outputs, stage="analysis"):
        self.inputs, self.outputs, self.stage = inputs, outputs, stage


class _FakeGraph:
    def __init__(self, nodes):
        self.nodes = nodes
        # Empty on purpose: the fixture holds no file on disk, so the digest over the
        # scanned scripts is taken over nothing and must SAY so rather than look clean.
        # That is the case the n_scripts field beside the hash exists to make visible.
        self.scanned = {}

    def counts(self):
        return {"scripts_scanned": len(self.scanned),
                "producer_nodes": len(self.nodes),
                "artifacts_produced": len({a for n in self.nodes.values()
                                           for a in n.outputs}),
                "tape_nodes": sum(1 for n in self.nodes.values()
                                  if n.stage == "tape"),
                "cycles": 0}


def _selftest():
    ok = True

    def case(name, condition, detail=""):
        nonlocal ok
        ok = ok and condition
        print(f"  {'PASS' if condition else 'FAIL'}  {name}"
              + (f"   {detail}" if detail else ""))

    # MUST FIRE: b.py reads what a.py writes and the two are in different groups, so
    # exactly one arrow alpha -> beta exists and it carries one read edge.
    g = _FakeGraph({"a.py": _FakeNode([], ["x.json"], stage="tape"),
                    "b.py": _FakeNode(["x.json"], ["y.json"])})
    groups = ({"id": "alpha", "step": "1, one", "question": "q1", "entry": "e1",
               "nodes": ("a.py",)},
              {"id": "beta", "step": "2, two", "question": "q2", "entry": "e2",
               "nodes": ("b.py",)})
    lifted = lift(g, groups)
    t = totals(lifted)
    case("an edge across two groups is drawn",
         lifted["edges"] == {("alpha", "beta"): 1},
         f"edges={lifted['edges']}")
    case("the archive walker is marked", lifted["tape"] == {"alpha": 1, "beta": 0})
    case("the buckets sum to the total", t["read_edges_total"] == 1
         and t["within_one_group"] == 0
         and t["touching_an_unclaimed_node"] == 0)

    # MUST STAY SILENT: the same two scripts inside ONE group. The read edge still
    # exists, so a predicate that counts edges rather than crossings would report an
    # arrow here; there must be none, and the edge must land in `within` instead.
    groups_one = ({"id": "alpha", "step": "1, one", "question": "q1", "entry": "e1",
                   "nodes": ("a.py", "b.py")},)
    lifted_one = lift(g, groups_one)
    t_one = totals(lifted_one)
    case("no arrow when both ends are in one group",
         lifted_one["edges"] == {}, f"edges={lifted_one['edges']}")
    case("and the edge is not lost, it is counted as internal",
         t_one["within_one_group"] == 1 and t_one["read_edges_total"] == 1)

    # THE THIRD BUCKET, both directions: a node no group claims, on each end in turn.
    groups_half = ({"id": "alpha", "step": "1, one", "question": "q1", "entry": "e1",
                    "nodes": ("a.py",)},)
    t_half = totals(lift(g, groups_half))
    case("an unclaimed consumer is counted, not dropped",
         t_half["touching_an_unclaimed_node"] == 1 and t_half["read_edges_total"] == 1)

    # A STALE ENTRY AND A DOUBLE CLAIM are what the census exists to catch.
    groups_bad = ({"id": "alpha", "step": "1, one", "question": "q1", "entry": "e1",
                   "nodes": ("a.py", "gone.py")},
                  {"id": "beta", "step": "2, two", "question": "q2", "entry": "e2",
                   "nodes": ("a.py", "b.py")})
    lifted_bad = lift(g, groups_bad)
    case("a group entry the graph does not hold is reported",
         lifted_bad["stale"] == [("alpha", "gone.py")])
    case("a node two groups claim is reported",
         lifted_bad["duplicate"] == [("a.py", "alpha", "beta")])

    # The escaping, on the two characters Mermaid reads specially inside a label.
    case("a quote and a hash are escaped in a caption",
         _escape('a "b" #c') == "a &quot;b&quot; &#35;c", _escape('a "b" #c'))

    # THE BOX RULE, on the two shapes the step field comes in. It must split on the
    # comma the field carries, and it must not lose either half.
    case("a box carries the group, its node count and its step, split on the comma",
         _box(groups[0], lifted) == ["alpha -- 1 scripts", "step 1: one"],
         str(_box(groups[0], lifted)))
    odd = {"id": "alpha", "step": "4 with 4A, what the name adds", "question": "q",
           "entry": "e", "nodes": ("a.py",)}
    case("and a step whose number is not one word survives the split",
         _box(odd, lifted) == ["alpha -- 1 scripts",
                               "step 4 with 4A: what the name adds"],
         str(_box(odd, lifted)))

    # THE FRONT MATTER, on the failure that has actually happened: a colon in the title.
    # Must stay silent on the quoted form, must fire on the bare one.
    case("a title with a colon is quoted, so the front matter parses",
         _yaml_quote("a: b") == '"a: b"', _yaml_quote("a: b"))
    case("a quote inside a title is escaped rather than left to end the scalar",
         _yaml_quote('say "no"') == '"say \\"no\\""', _yaml_quote('say "no"'))
    case("the lint passes the front matter this module emits",
         _lint("\n".join(_front_matter())) == [],
         str(_lint("\n".join(_front_matter()))))
    case("the lint catches a title that was never quoted",
         len(_lint("title: a: b")) > 0, str(_lint("title: a: b")))

    # THE PICTURE, on a file that is one and a file that is not. A reader of the header
    # that accepted anything would report a size for a text file.
    with tempfile.TemporaryDirectory() as scratch:
        real = os.path.join(scratch, "one.png")
        with open(real, "wb") as handle:
            handle.write(b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR"
                         + struct.pack(">II", 640, 480))
        fake = os.path.join(scratch, "two.png")
        with open(fake, "w", encoding="utf-8") as handle:
            handle.write("this is not a picture")
        case("a PNG header is read for its size", _png_pixels(real) == (640, 480),
             str(_png_pixels(real)))
        case("and a file that is not a PNG reports no size at all",
             _png_pixels(fake) is None, str(_png_pixels(fake)))
        gone = picture_state(os.path.join(scratch, "absent.png"))
        case("a picture that is not there is reported absent, not hashed",
             gone["present"] is False and gone["sha256"] is None, str(gone))
        there = picture_state(real)
        case("and a picture that is there is hashed and measured",
             there["present"] is True and there["pixels"] == "640x480"
             and len(there["sha256"]) == 64, str(there))

        # THE DRAWING'S OWN UNITS, on a drawing that carries them and one that does not.
        # The width read here is the one the type size on the page is divided by, so a
        # reader that returned something for anything would put a type size on the page
        # that no drawing has. The two cases are the shape mermaid-cli writes, taken
        # from a real render of this flowchart, and the text file above.
        drawn = os.path.join(scratch, "one.svg")
        with open(drawn, "w", encoding="utf-8") as handle:
            handle.write('<svg aria-roledescription="flowchart-v2" '
                         'viewBox="0 -56 1327.359375 1850" style="max-width: 1327px;" '
                         'width="100%" xmlns="http://www.w3.org/2000/svg">')
        case("a drawing's own width and height are read off its viewBox",
             _viewbox(drawn) == (1327.359375, 1850.0), str(_viewbox(drawn)))
        case("and a file carrying no viewBox reports no geometry at all",
             _viewbox(fake) is None, str(_viewbox(fake)))

    # THE LINT, on two opposite cases of its own. A lint that passes everything is the
    # same as no lint, and one that fails everything would have stopped the run above.
    case("the lint passes a well-formed declaration",
         _lint('  a["one<br/>two"]') == [], str(_lint('  a["one<br/>two"]')))
    case("the lint passes a well-formed edge",
         _lint('  a -->|3| b_in["data"]') == [],
         str(_lint('  a -->|3| b_in["data"]')))
    case("the lint catches a raw quote inside a label",
         len(_lint('  a["he said "no" to it"]')) > 0)
    case("the lint catches an unbalanced bracket",
         len(_lint('  a["one"] -->|3| b["two"')) > 0)

    # THE RESULTS FILE CARRIES THE SAME COUNTS AS THE PICTURE, on the same two opposite
    # cases. A payload assembled from a second traversal would pass the first of these
    # and fail the second without anything saying so, which is precisely why it is
    # assembled from the one `lifted` the drawing is assembled from.
    payload = results(g, groups, lift(g, groups))
    case("the results file draws the one arrow the picture draws",
         payload["arrows"]["n_arrows_drawn"] == 1
         and payload["arrows"]["each"][0]["from"] == "alpha"
         and payload["arrows"]["each"][0]["to"] == "beta"
         and payload["arrows"]["each"][0]["read_edges"] == 1,
         f"arrows={payload['arrows']['each']}")
    case("and it reports no arrow when both ends are in one group",
         results(g, groups_one, lift(g, groups_one))["arrows"]["n_arrows_drawn"] == 0)
    case("the three buckets sum in the file as well as in the reconciliation",
         payload["read_edges"]["buckets_sum_to_total"] is True
         and payload["read_edges"]["total"] == 1)
    case("the box count is the count of declared groups",
         payload["boxes"]["n_groups_declared"] == 2
         and payload["boxes"]["n_scripts_claimed_by_a_group"] == 2)
    # A digest taken over nothing says so instead of reading as a clean tree, which is
    # the opposite case to the live run below where it covers every scanned script.
    case("a digest over no scripts reports its own population as zero",
         payload["scanned_scripts"]["n_scripts"] == 0
         and payload["scanned_scripts"]["n_unreadable"] == 0)
    return ok


def check(graph, groups, lifted):
    """Print the reconciliation and return an exit code. Non-zero means look."""
    t = totals(lifted)
    problems = ["the drawn diagram does not parse: " + line
                for line in _lint(mermaid_top(graph, groups, lifted))]
    if t["read_edges_total"] != (t["within_one_group"] + t["across_two_groups"]
                                 + t["touching_an_unclaimed_node"]):
        problems.append("the three buckets do not sum to the total")
    silent = [e["id"] for e in groups
              if not any(e["id"] in pair for pair in lifted["edges"])]
    if silent:
        problems.append("groups with no arrow at all: " + ", ".join(silent))
    if lifted["stale"]:
        problems.append("group entries the graph does not hold: "
                        + ", ".join(f"{g}/{k}" for g, k in lifted["stale"]))
    if lifted["duplicate"]:
        problems.append("nodes claimed twice: "
                        + ", ".join(f"{k} ({a}, {b})"
                                    for k, a, b in lifted["duplicate"]))
    print("  RECONCILIATION")
    print(f"    read edges total                  {t['read_edges_total']}")
    print(f"      inside one group                {t['within_one_group']}")
    print(f"      across two groups               {t['across_two_groups']}")
    print(f"      touching an unclaimed node      "
          f"{t['touching_an_unclaimed_node']}")
    print(f"    arrows between groups             {t['arrows_between_groups']}")
    print(f"    distinct artifacts crossing       "
          f"{t['artifacts_crossing_a_boundary']}")
    print(f"    producer nodes no group claims    {len(lifted['unclaimed'])}")
    for key in lifted["unclaimed"]:
        print(f"      {key}")
    # The picture is reported and does not decide the exit code. Its three verdicts
    # include one that means the question could not be asked, and a mode that failed
    # because a Node program is absent would say nothing about whether this pipeline's
    # graph reconciles, which is what --check is for.
    verdict, detail = picture_verdict(mermaid_top(graph, groups, lifted),
                                      os.path.join(HERE, OUT_PNG_NAME))
    print(f"    the committed picture             {verdict}")
    print(f"      {detail}")
    if problems:
        for line in problems:
            print(f"    REFUTED: {line}")
        return 1
    # THE CLOSING LINE NAMES THE DEBT THE BUCKET ABOVE COUNTED. Until 2026-08-30 it
    # said only that the table reconciles, which is true and is the smaller half of
    # what the run found: a reader who takes the last line and does not read the list
    # above it carries away a picture in which every producer node is drawn. Both
    # numbers below are the ones just counted and neither is typed here, because a
    # sentence that carries the size of a gap as a constant goes false on the day the
    # gap moves and goes false silently. The VERDICT on that size is not taken here --
    # run/gates.py --census holds it against a declared ceiling and returns a code on
    # it -- since two instruments judging one gap by two rules is how the two come to
    # disagree, and this one exits zero because the reconciliation it performs held.
    unclaimed = len(lifted["unclaimed"])
    touching = t["touching_an_unclaimed_node"]
    if unclaimed:
        # Both halves carry their own verb, because a debt of one reads as a typo
        # under a sentence written for many, and a reader who stops to reread the
        # grammar has stopped reading the number.
        nodes = ("1 producer node" if unclaimed == 1
                 else f"{unclaimed} producer nodes")
        edges = (f"{touching} read edge reaching an unclaimed node is"
                 if touching == 1
                 else f"{touching} read edges reaching an unclaimed node are")
        closing = (
            f"the buckets sum, every group has an arrow, and the table matches the "
            f"graph, WITH A DEBT: no entry point claims {nodes}, named above, and "
            f"the {edges} counted above rather than drawn. run/gates.py --census "
            f"holds that count against a declared ceiling and is the instrument "
            f"that returns a code on it; the zero here is about the reconciliation "
            f"alone.")
    else:
        closing = ("the buckets sum, every group has an arrow, the table matches "
                   "the graph, and every producer node of it is claimed by an "
                   "entry point.")
    # Wrapped rather than typed onto fixed lines, because the width of the numbers
    # in it is not known until they are counted, and a sentence hand-broken around
    # a two-digit debt breaks in the wrong place at three digits. break_on_hyphens
    # is off for the reason the captions above have it off: it would split --census.
    print(textwrap.fill(closing, 78, initial_indent="    ",
                        subsequent_indent="      ", break_on_hyphens=False))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Draw this pipeline's dependency graph at the level of its groups.")
    parser.add_argument("--group", metavar="ID",
                        help="print the second level: the nodes of one named group")
    parser.add_argument("--check", action="store_true",
                        help="print the reconciliation and exit non-zero if it fails")
    parser.add_argument("--png", action="store_true",
                        help=f"also render the flowchart to {OUT_PNG_NAME}. Needs "
                             "mermaid-cli, which is a Node program and not one of the "
                             "requirements; without it this exits non-zero and says so")
    parser.add_argument("--measure", action="store_true",
                        help="render the flowchart and report the type size it puts on "
                             "the report column and the height it takes off the page. "
                             "Needs mermaid-cli, and says so rather than reporting a "
                             "zero without it")
    parser.add_argument("--selftest", action="store_true",
                        help="run the calibration cases and exit")
    parser.add_argument("--stdout", action="store_true",
                        help="print the document instead of writing it")
    args = parser.parse_args(argv)

    if args.selftest:
        print("  CALIBRATION, two opposite cases per predicate")
        return 0 if _selftest() else 1

    # Taken before the graph is derived, so the recorded cost is the whole node. Deriving
    # the graph is what this producer spends its time on: it parses every tracked script.
    started = artifact.start_clock()
    graph = build.graph()
    lifted = lift(graph, GROUPS)

    if args.group:
        drawn = mermaid_group(graph, GROUPS, lifted, args.group)
        bad = _lint(drawn)
        if bad:
            for line in bad:
                print(f"REFUSED: {line}", file=sys.stderr)
            return 1
        print(drawn)
        return 0
    if args.check:
        return check(graph, GROUPS, lifted)
    if args.measure:
        ok, found = measure_layout(mermaid_top(graph, GROUPS, lifted))
        if not ok:
            print(f"NOT MEASURED: {found}", file=sys.stderr)
            return 2
        print("  THE DRAWING ON THE REPORT PAGE")
        print(f"    declared font                     {found['declared_font_px']} px")
        print(f"    the drawing, in its own units     "
              f"{found['width_units']:.0f} x {found['height_units']:.0f}")
        print(f"    type on the {COLUMN_MM:.1f} mm column      "
              f"{found['type_pt_on_the_column']:.2f} pt, against 11 pt body text")
        print(f"    the figure, placed at that width  "
              f"{found['figure_mm_at_column_width']:.0f} mm tall")
        print(f"    left of the {PAGE_TEXT_MM:.0f} mm text block  "
              f"{found['page_mm_left_under_it']:.0f} mm, for the caption under it")
        return 0

    text = document(graph, GROUPS, lifted)
    # A diagram that does not parse renders as nothing at all, so it is never written:
    # a file on disk that looks well formed in a diff and draws an empty box is the one
    # failure this producer cannot let through.
    bad = _lint(mermaid_top(graph, GROUPS, lifted))
    if bad:
        for line in bad:
            print(f"REFUSED: {line}", file=sys.stderr)
        return 1
    # --stdout prints and writes nothing at all, the results file included: it is the
    # mode for looking, and a mode that looks must not leave an artifact behind that a
    # later reader takes for the product of a run that wrote the document.
    if args.stdout:
        if args.png:
            print("--stdout writes nothing and --png writes a file, so the two cannot "
                  "be asked for together", file=sys.stderr)
            return 2
        print(text)
        return 0
    out_path = os.path.join(HERE, OUT_NAME)
    with open(out_path, "w", encoding="utf-8") as handle:
        handle.write(text)
    t = totals(lifted)
    print(f"[build_diagram] {len(GROUPS)} groups, {t['arrows_between_groups']} arrows, "
          f"{t['across_two_groups']} of {t['read_edges_total']} read edges cross a "
          f"group boundary -> {OUT_NAME}")

    # The picture comes between the document and the results file, so that the hash the
    # results file records for it is the hash of the picture this run left on disk and
    # not of the one the run before left there.
    drawn_png = True
    if args.png:
        drawn_png, message = render_png(mermaid_top(graph, GROUPS, lifted),
                                        os.path.join(HERE, OUT_PNG_NAME))
        print(f"[build_diagram] {'wrote ' if drawn_png else 'DID NOT WRITE THE PICTURE. '}"
              f"{message}", file=sys.stdout if drawn_png else sys.stderr)

    # The results file goes last, so that a run which failed to write the picture leaves
    # no counts claiming to describe one. What the two hashed inputs are and what they
    # are not is stated in the scope rather than left to be inferred from their presence.
    claimed = sum(len(lifted["nodes"][entry["id"]]) for entry in GROUPS)
    artifact.write(
        OUT_JSON_NAME, results(graph, GROUPS, lifted),
        script=__file__,
        inputs=[IN_BUILD, IN_GROUPS],
        scope={
            "population": (
                f"{len(graph.scanned)} tracked scripts of this repository, of which "
                f"{len(graph.nodes)} produce an artifact and are nodes of the dependency "
                f"graph; the {len(GROUPS)} declared groups claim {claimed} of those "
                f"nodes and {len(lifted['unclaimed'])} are claimed by none. The two "
                "hashed inputs are the DECLARATIONS this run stands on -- the graph "
                "deriver and the group table -- and not the population: an edit to any "
                "other scanned script moves these counts without moving either hash, "
                "which is what the digest under scanned_scripts is for"),
            "window": ("n/a: this artifact describes the repository at the moment of "
                       "the run and covers no period of market data"),
            "coins": ("n/a: the unit here is a script and an edge between scripts, not "
                      "a trade"),
        },
        settings=dict(
            scoring_settings_apply=False,
            overrides_note=(
                "This producer measures the repository and not the market. No markout "
                "is computed here, so horizon_s, lens and every fill floor in this "
                "block state what settings.py declares and say nothing about this "
                "artifact; they are left at the declaration rather than overridden to "
                "some value, because inventing a horizon for a count of edges would be "
                "a correct number about the wrong thing. What this run genuinely stands "
                "on is the pair of declarations recorded as inputs."),
        ),
        started=started)
    print(f"[build_diagram] wrote {OUT_JSON_NAME}")
    # Non-zero when the picture was asked for and did not appear. The document and the
    # counts are on disk either way and are correct either way; what failed is one named
    # step, and a zero here would report the run as whole when it was not.
    return 0 if drawn_png else 2


if __name__ == "__main__":
    sys.exit(main())
