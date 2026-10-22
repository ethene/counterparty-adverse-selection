#!/usr/bin/env python3
"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-07-31
References: none (repository infrastructure; it reads only the register of quantities
and the artifacts this tree produces).

THE PROSE STOPS HOLDING NUMBERS. IT HOLDS THE NAME OF A NUMBER, AND THE VALUE IS PUT
IN WHEN THE DOCUMENT IS ASSEMBLED.

WHY, BEFORE HOW. The report a reader reads carries figures, and today the same
figure is typed out in five places: the artifact a script wrote, the register of
quantities that addresses it, the narrative, the draft, and the reports of the audit
passes. Five places is not five witnesses. It has already produced one WRONG statement
that stood in five files at once, each of them looking like confirmation of the other
four, because every copy was made from a copy. A number that is typed cannot be stale
in one place only; it goes stale silently and stays plausible.

So the value gets one home -- the artifact -- and the prose gets a reference to it. The
sentence names the quantity; this script goes to the artifact and puts the value in.
After that a stale number in the text is not unlikely, it is impossible: the text has
no number in it to go stale.

THE ROAD TO THE VALUE IS THE ONE THE GATE ALREADY WALKS, AND THIS IS THE WHOLE POINT.
checks/chk_prose_numbers.py goes from a register record to the artifact leaf its own
address names -- source_file plus a key path in source_key -- and it joins the
register's sub-names to artifact leaves BY WHOLE NAME, never by value. That module is
imported here and its functions are called. Nothing about addressing, resolving or
joining is written a second time in this file. A second implementation would be a
second home for the address, which is the defect this script exists to end, one level
up.

THE MARKUP, AND WHY IT IS AN HTML COMMENT.

    <!--#D01-->2 480 267<!--/#D01-->

The opener names the quantity, the closer repeats the name, and between them stands
the value as it is to be read. Two candidates were weighed.

  A pandoc bracketed span, `[2 480 267]{#D01}`, is shorter and is native markdown. It
  was refused for two measured reasons. It depends on the `bracketed_spans` extension:
  where that extension is off, or where the file is read by any other markdown tool,
  the span degrades to the literal characters `[2 480 267]{#D01}` INSIDE A PUBLISHED
  DOCUMENT. And where it is on, pandoc emits a bookmark into the .docx, so the markup
  changes the deliverable even when it works.

  An HTML comment cannot do either. Markdown has no other use for `<!-- -->`, so the
  marker can never collide with the prose's own brackets and parentheses -- measured on
  the narrative as it stands: it contains zero occurrences of `<!--`, so every marker
  in the file is one this script put there. Pandoc parses the comment as raw HTML and
  every writer that is not an HTML writer drops it, so a source that was never
  assembled still exports to .docx as clean prose carrying the value that was last read
  into it. The failure mode of the markup is therefore "the figure is a little old",
  never "the reader sees machinery".

The value stays visible in the source ON PURPOSE, rather than the marker standing
alone in its place. Three things follow from that and each of them is worth the extra
characters. The source stays readable to a human, who is the main reader of a draft.
The assembly becomes checkable rather than merely obedient: it compares what stands in
the text with what the artifact holds, so `--check` reports a stale figure by name
instead of silently overwriting it. And the move onto references is reversible and can
be proved so, because assembling a marked-up copy of a document that is already correct
must return that document character for character.

WHAT THE REGISTER DECLARES AND WHAT THE TEXT DECLARES. The text declares nothing but
which quantity it is naming. Rounding, scale and units are properties of the quantity,
so they are declared beside it in the register, in an optional `display` field, whose
shape is stated at DISPLAY_FIELD below. No record carries that field yet -- measured
2026-07-31, 0 of 108 -- so a fallback is declared here and it is deliberately a poor
one: the number of significant digits the register itself printed. It is poor because
the register was filled in by hand and prints some figures at full double precision and
others at the precision of the prose, so for many quantities it will render more digits
than the sentence wants. That is reported rather than papered over: `--propose` writes
out exactly the display declarations the current text implies, as a patch for the
register, and prints how many quantities need one.

The declarations may be supplied from a separate file with `--display` while that patch
is being weighed. That file may carry display specs and nothing else; a `value` in it
is refused, because a second home for a VALUE is the very thing this script is against.

WHERE THIS SITS IN THE EXPORT, AND THE ORDER OF THE STEPS AT PUBLICATION TIME. The
report is written in markdown and converted by pandoc against the report template
(`pandoc --reference-doc=<template>.docx --shift-heading-level-by=-1`). This script
runs BEFORE pandoc and hands it a document with no machinery in it, so the conversion
is untouched and no pandoc option changes.

    1. run the integrity gates, so the artifacts the figures come from are the ones
       the tree currently computes;
    2. `--check` the marked source. A figure the text disagrees with fails here, with
       its line and both numbers, and the export does not start;
    3. `--build` the marked source into the document to be converted. The provenance
       sidecar written beside it names, for every figure, the artifact file, the key
       path, and the script that produced it;
    4. pandoc the built document into .docx against the template;
    5. the .docx goes to the detector and to the portal.

Step 2 is the one that earns the mechanism: it is the difference between a stale
figure being unlikely and a stale figure stopping the export.

Run:

    uv run --no-project python3 prose_assemble.py --build  DOC.md -o OUT.md
    uv run --no-project python3 prose_assemble.py --check  DOC.md
    uv run --no-project python3 prose_assemble.py --propose DOC.md -o MARKED.md \\
        --declare display_patch.json
    uv run --no-project python3 prose_assemble.py --self-test
"""
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.join(HERE, "checks")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import artifact                                                      # noqa: E402
import chk_prose_numbers as gate                                     # noqa: E402
from evidence import Tally                                           # noqa: E402

# ----------------------------------------------------------------------------------
# THE MARKUP
# ----------------------------------------------------------------------------------

# A reference is a record id, optionally followed by a colon and the register's own
# sub-name for one leaf of that record: `D01`, `M28:BTC.10`, `M11:10pct`. The sub-name
# is spelled exactly as chk_prose_numbers reports it, because that is the vocabulary
# the join already speaks and a second spelling would be a second address.
_REF = r"[A-Za-z][A-Za-z0-9_]*(?::[A-Za-z0-9_.]+)?"
OPEN = re.compile(r"<!--#(" + _REF + r")-->")
CLOSE = re.compile(r"<!--/#(" + _REF + r")-->")
ANY_MARKER = re.compile(r"<!--/?#" + _REF + r"-->")

# The optional register field that declares how a quantity is written down. Either one
# spec for a record with a single figure, or a mapping from the register's sub-name to
# a spec. A spec may carry:
#   digits    significant digits to round to (an integer figure keeps all of them)
#   scale     multiply before printing, for a share written as a percentage
#   sign      "always" to print a leading + on a positive figure
#   minus     "unicode" to print U+2212 instead of the hyphen
#   thousands the separator between groups of three, "" by default
#   units     text appended after the figure
DISPLAY_FIELD = "display"
SPEC_KEYS = ("digits", "scale", "sign", "minus", "thousands", "units")

# The fallback when no display is declared: print as many significant digits as the
# register itself printed. Declared debt, 2026-07-31: it is wrong for every record that
# copied its value at full double precision, and the repair is a display field on the
# record rather than a cleverer rule here. `--propose --declare` writes the patch.
FALLBACK = "the significant digits the register itself printed"

# The proposer refuses to anchor a figure to a token written to fewer than this many
# significant digits. One digit buys a rounding gap of up to fifty per cent, which
# matched the literal "1" to a figure of 0.96 and the literal "2" to a figure of 15.6
# on the first pass over the narrative. Two digits cap the gap at five per cent.
MIN_ANCHOR_DIGITS = 2

# Scales the proposer will try, in order. 1 is the figure itself; 100 is a share
# written as a percentage, which the prose does in several places.
ANCHOR_SCALES = (1.0, 100.0)

# How near a written figure has to be to an addressed one before the proposer calls it
# a SUSPECT: a figure the sentence appears to be quoting but which is not a rounding of
# what the artifact holds. Two per cent is wide enough to cover a figure that moved when
# its artifact was recomputed and narrow enough that an unrelated number in the same
# paragraph does not land inside it. A suspect is never anchored and never substituted;
# it is printed for a person to judge, because "this literal IS that quantity" is a
# claim about meaning that no arithmetic here can settle.
SUSPECT_BAND = 0.02


class BuildError(Exception):
    """Raised with every fault found, so one run reports all of them, not the first."""


# ----------------------------------------------------------------------------------
# THE REGISTER, READ THROUGH THE GATE'S OWN ROAD
# ----------------------------------------------------------------------------------

def load_register(argv=None):
    """[record] of the register of quantities. Absent register is a build failure.

    The register is not published with this repository, so it is read from where the
    caller names it and from nowhere else: --registry PATH, or PROSE_REGISTRY when no
    flag is given. The rule is the gate's own, reached by calling
    gate.registry_argument rather than spelled a second time here, so the two cannot
    come to disagree about where the register is. There is no default path. The gate
    treats an unnamed register as the ordinary state of a clone and passes; a document
    cannot be assembled without it at all, so here it stops the run.
    """
    found, _how = gate.registry_argument(argv)
    if not found or not os.path.isfile(found):
        raise BuildError(
            f"the register of quantities ({gate.REGISTRY_NAME}) was "
            + (f"named as {found!r} and is not a file" if found else
               f"not named: pass {gate.REGISTRY_FLAG} PATH or set {gate.REGISTRY_ENV}")
            + ". No document can be assembled without it: the register is what says "
            "where each figure lives")
    with open(found, encoding="utf-8") as fh:
        return json.load(fh)


def addressed_leaves(record):
    """{register sub-name: (artifact key path, artifact value)} for one record.

    Every step here is chk_prose_numbers': read_source finds and opens the stated file,
    join_record walks the stated key path and pairs the register's sub-names to artifact
    leaves by whole-name equality. Nothing is searched for and nothing is matched by
    value. A record whose address does not resolve returns an empty mapping and the
    reason, which is what the caller turns into a named build failure.
    """
    kind, document, note = gate.read_source(record)
    if kind is None:
        return {}, note
    pairs, _missed, _addresses, n_leaves = gate.join_record(record, kind, document)
    if not pairs:
        if not n_leaves:
            return {}, ("no address written in source_key resolves to a number inside "
                        "the stated file")
        return {}, ("the address resolves, but no sub-name of the record equals a name "
                    "on the artifact's own key path")
    out = {}
    for path, declared, artifact_path, artifact_value, rule in pairs:
        name = ".".join(path)
        out.setdefault(name, {
            "declared": declared,
            "artifact_key_path": ".".join(artifact_path),
            "artifact_value": artifact_value,
            "join_rule": rule,
        })
    return out, None


# ----------------------------------------------------------------------------------
# HOW A FIGURE IS WRITTEN DOWN
# ----------------------------------------------------------------------------------

def significant_digits_of_text(text):
    """Significant digits of a figure AS WRITTEN, which repr() cannot tell you.

    The token "0.90" is written to two digits and float("0.90") remembers one, so the
    count is taken from the characters. A trailing zero after a decimal point is
    significant; a trailing zero in an integer is not, since nothing distinguishes 20
    rounded from 20 exact.
    """
    body = text.strip().lstrip("+-−").replace(" ", "").replace(" ", "")
    body = body.replace(" ", "").replace(",", ".")
    if "." in body:
        whole, _, frac = body.partition(".")
        if whole.strip("0") == "":
            return max(1, len(frac.lstrip("0")))
        return max(1, len(whole.lstrip("0")) + len(frac))
    return max(1, len(body.strip("0") or "0"))


def parse_number(text):
    """The value of a written figure, or None. Spaces group digits; U+2212 is a minus."""
    body = (text.strip().replace(" ", "").replace(" ", "").replace(" ", "")
            .replace("−", "-").replace(",", "."))
    try:
        return float(body)
    except ValueError:
        return None


def round_significant(value, digits):
    if value == 0 or not math.isfinite(value):
        return float(value)
    return float("%.*e" % (max(1, int(digits)) - 1, value))


def _group_thousands(digits_text, separator):
    if not separator:
        return digits_text
    out = []
    while len(digits_text) > 3:
        out.insert(0, digits_text[-3:])
        digits_text = digits_text[:-3]
    out.insert(0, digits_text)
    return separator.join(out)


def render(value, spec):
    """One figure written down the way its register record declares.

    Rounding, scale, sign, separator and units all come from `spec`, which comes from
    the register. Nothing here is taken from the document being assembled.
    """
    scale = float(spec.get("scale", 1.0) or 1.0)
    scaled = float(value) * scale
    digits = spec.get("digits")
    is_integer = (isinstance(value, int) and not isinstance(value, bool)
                  and scale == 1.0 and digits is None)

    if is_integer:
        body = str(abs(int(value)))
        text = _group_thousands(body, spec.get("thousands", ""))
        negative = int(value) < 0
    else:
        if digits is None:
            digits = gate.significant_digits(value)
        rounded = round_significant(scaled, digits)
        magnitude = abs(rounded)
        if magnitude == 0 or not math.isfinite(magnitude):
            decimals = max(0, int(digits) - 1)
        else:
            decimals = max(0, int(digits) - 1 - math.floor(math.log10(magnitude)))
        text = "%.*f" % (decimals, abs(rounded))
        whole, _, frac = text.partition(".")
        whole = _group_thousands(whole, spec.get("thousands", ""))
        text = whole + ("." + frac if frac else "")
        negative = rounded < 0

    minus = "−" if spec.get("minus") == "unicode" else "-"
    if negative:
        text = minus + text
    elif spec.get("sign") == "always":
        text = "+" + text
    units = spec.get("units")
    return text + (units if units else "")


def spec_for(record, leaf, overlay=None):
    """The display declaration for one leaf: the register's, or the declared fallback.

    `overlay` is the patch-under-consideration keyed by "ID" or "ID:leaf". It may only
    carry display keys; a value in it is refused where it is loaded, not here.
    """
    ident = str(record.get("id"))
    if overlay:
        for key in (f"{ident}:{leaf}" if leaf else ident, ident):
            if key in overlay:
                return dict(overlay[key])
    declared = record.get(DISPLAY_FIELD)
    if isinstance(declared, dict):
        if leaf and leaf in declared:
            return dict(declared[leaf])
        if any(k in declared for k in SPEC_KEYS):
            return dict(declared)
    return {}


def load_overlay(path):
    """Display declarations held outside the register while the patch is weighed."""
    if not path:
        return {}
    with open(path, encoding="utf-8") as fh:
        loaded = json.load(fh)
    if not isinstance(loaded, dict):
        raise BuildError(f"{os.path.basename(path)} must be a mapping from "
                         "\"ID\" or \"ID:leaf\" to a display spec")
    for key, spec in loaded.items():
        if not isinstance(spec, dict):
            raise BuildError(f"{os.path.basename(path)}: {key} is not a mapping")
        stray = sorted(set(spec) - set(SPEC_KEYS))
        if stray:
            raise BuildError(
                f"{os.path.basename(path)}: {key} carries {stray}, which is not a "
                f"display key. This file declares only how a figure is WRITTEN "
                f"({', '.join(SPEC_KEYS)}); a value here would be a second home for "
                "the value, which is what this whole mechanism exists to prevent")
    return loaded


# ----------------------------------------------------------------------------------
# READING THE MARKERS OUT OF A DOCUMENT
# ----------------------------------------------------------------------------------

def _where(text, position):
    """(line, column) of an offset, one-based, for a message a person can act on."""
    line = text.count("\n", 0, position) + 1
    column = position - (text.rfind("\n", 0, position) + 1) + 1
    return line, column


def fences(text):
    """[(reference, value start, value end, opener start, closer end)] in order.

    An opener with no closer, a closer with no opener and a closer naming a different
    reference are all faults rather than something to skip: each of them means the
    document says something about a figure that cannot be acted on.
    """
    found, faults, cursor = [], [], 0
    while True:
        opener = OPEN.search(text, cursor)
        stray = CLOSE.search(text, cursor)
        if stray and (opener is None or stray.start() < opener.start()):
            line, column = _where(text, stray.start())
            faults.append(f"line {line} column {column}: a closing marker for "
                          f"#{stray.group(1)} with no opening marker before it")
            cursor = stray.end()
            continue
        if opener is None:
            break
        closer = CLOSE.search(text, opener.end())
        nxt = OPEN.search(text, opener.end())
        if closer is None or (nxt and nxt.start() < closer.start()):
            line, column = _where(text, opener.start())
            faults.append(f"line {line} column {column}: the marker for "
                          f"#{opener.group(1)} is never closed. Write "
                          f"<!--/#{opener.group(1)}--> after the figure")
            cursor = opener.end()
            continue
        if closer.group(1) != opener.group(1):
            line, column = _where(text, opener.start())
            faults.append(f"line {line} column {column}: the marker for "
                          f"#{opener.group(1)} is closed by #{closer.group(1)}; the "
                          "closing marker repeats the reference so that a crossed pair "
                          "is a fault rather than a silent substitution")
            cursor = closer.end()
            continue
        found.append((opener.group(1), opener.end(), closer.start(),
                      opener.start(), closer.end()))
        cursor = closer.end()
    return found, faults


# ----------------------------------------------------------------------------------
# THE ASSEMBLY
# ----------------------------------------------------------------------------------

def assemble(text, records, overlay=None, keep_markers=False):
    """(assembled text, [substitution]) or raise BuildError naming every fault.

    A substitution records what stood in the document, what the artifact holds, and
    whether the two agreed. `keep_markers` writes the markers back out, which is what
    makes assembly idempotent on a source file; the shipped document drops them.
    """
    by_id = {str(r.get("id")): r for r in records}
    marks, faults = fences(text)
    resolved, out, cursor = [], [], 0
    cache = {}

    for reference, value_start, value_end, mark_start, mark_end in marks:
        ident, _, leaf = reference.partition(":")
        line, column = _where(text, mark_start)
        place = f"line {line} column {column}"
        standing = text[value_start:value_end]

        record = by_id.get(ident)
        if record is None:
            faults.append(f"{place}: #{reference} names {ident}, which is not a record "
                          f"of the register of quantities")
            continue
        if ident not in cache:
            cache[ident] = addressed_leaves(record)
        leaves, why = cache[ident]
        if not leaves:
            faults.append(
                f"{place}: #{reference} cannot be given a value, because {why}. The "
                f"register states source_file={record.get('source_file')!r} and "
                f"source_key={str(record.get('source_key'))[:90]!r}")
            continue
        if not leaf:
            if len(leaves) != 1:
                faults.append(
                    f"{place}: #{reference} names a record holding {len(leaves)} "
                    f"figures, so the reference must name one of them: "
                    f"{', '.join('#%s:%s' % (ident, k) for k in sorted(leaves))}")
                continue
            leaf = next(iter(leaves))
        if leaf not in leaves:
            faults.append(
                f"{place}: #{reference} names the sub-figure {leaf!r}, which the "
                f"record does not address. It addresses: "
                f"{', '.join(sorted(leaves)) or '(none)'}")
            continue

        entry = leaves[leaf]
        agree, relative, tolerance = gate.agrees(entry["declared"],
                                                 entry["artifact_value"])
        if not agree:
            faults.append(
                f"{place}: #{reference} is not safe to substitute. The register states "
                f"{entry['declared']!r} and the artifact holds "
                f"{entry['artifact_value']!r} at {entry['artifact_key_path']}, a "
                f"relative difference of {relative:.3g} against a tolerance of "
                f"{tolerance:.3g}. Repair the register against the artifact first")
            continue

        spec = spec_for(record, leaf, overlay)
        written = render(entry["artifact_value"], spec)
        out.append(text[cursor:mark_start])
        if keep_markers:
            out.append(f"<!--#{reference}-->{written}<!--/#{reference}-->")
        else:
            out.append(written)
        cursor = mark_end
        resolved.append({
            "reference": reference,
            "id": ident,
            "leaf": leaf,
            "line": line,
            "stood_in_the_text": standing,
            "written": written,
            "changed": standing != written,
            "artifact_value": entry["artifact_value"],
            "source_file": record.get("source_file"),
            "artifact_key_path": entry["artifact_key_path"],
            "join_rule": entry["join_rule"],
            "producer_script": record.get("producer_script"),
            "display_declared": bool(spec),
        })

    if faults:
        raise BuildError("\n".join(faults))
    out.append(text[cursor:])
    return "".join(out), resolved


# ----------------------------------------------------------------------------------
# THE PROPOSER: MOVING A DOCUMENT THAT ALREADY HOLDS ITS NUMBERS ONTO REFERENCES
# ----------------------------------------------------------------------------------

# A written figure. Groups of three digits may be separated by a space, and the minus
# may be either the hyphen or U+2212, both of which the narrative uses.
TOKEN = re.compile(r"[+\-−]?\d+(?:[   ]\d{3})+(?:[.,]\d+)?"
                   r"|[+\-−]?\d+(?:[.,]\d+)?")

# A citation of a register record as the narrative already writes it: [#D01].
CITATION = re.compile(r"\[#([A-Za-z][A-Za-z0-9_]*)\]")


def blank_machinery(chunk):
    """The block with its machinery blanked out, so only PROSE figures are read.

    Two things in this document are machinery rather than prose, and the digits of
    both would otherwise enter the population of written figures. A marker already
    placed carries a value that belongs to another reference. And a citation carries
    the digits of a record identifier: measured on the narrative of 2026-07-31, the
    `11` of the citation `[#M11]` is a faithful two-digit rendering of M12's flagged
    share of 0.1141 taken as a percentage, so it anchored, and building that document
    would have rewritten the citation itself. Blanking keeps every offset intact, so
    a span found in the blanked block is the same span in the real one.
    """
    return CITATION.sub(lambda m: " " * len(m.group(0)),
                        ANY_MARKER.sub(lambda m: " " * len(m.group(0)), chunk))


def scopes(text):
    """[(start, end)] of the blocks a citation may anchor inside.

    A block is a paragraph. It is extended over the table that immediately follows it,
    because the tables of this document carry the figures and the citation sits in the
    sentence introducing them; without the extension the densest part of the text is
    unreachable. The extension is a declared rule and the census below reports how many
    anchors depend on it.
    """
    blocks, start = [], 0
    for gap in re.finditer(r"\n[ \t]*\n", text):
        blocks.append((start, gap.start()))
        start = gap.end()
    blocks.append((start, len(text)))
    merged = []
    for index, (a, b) in enumerate(blocks):
        end = b
        following = blocks[index + 1] if index + 1 < len(blocks) else None
        if following and text[following[0]:following[1]].lstrip().startswith("|"):
            end = following[1]
        merged.append((a, end))
    return merged


def spec_from_token(value, token_text, scale):
    """The display declaration that makes `value` come out as `token_text`.

    This is the one place where the prose tells us anything about rounding, and it does
    so ONCE, during the move onto references. What it says is written into the patch for
    the register; after that the text is free of it.
    """
    spec = {"digits": significant_digits_of_text(token_text)}
    if scale != 1.0:
        spec["scale"] = scale
    if any(sep in token_text for sep in (" ", " ", " ")):
        spec["thousands"] = " "
    if token_text.startswith("+"):
        spec["sign"] = "always"
    if token_text.startswith("−"):
        spec["minus"] = "unicode"
    if isinstance(value, int) and not isinstance(value, bool) and scale == 1.0:
        spec.pop("digits", None)
    return spec


def anchor(text, records):
    """Anchor addressed figures to the literals that already stand in a document.

    THE PREDICATE, stated beside its population because a count taken by an unstated
    predicate says nothing. Population: every written figure inside the block of a
    citation [#ID], against every leaf of that record whose address resolves. A token
    anchors a leaf when all four hold.

      1. The token is a faithful rendering of the artifact value at the token's own
         precision: rounding the value to as many significant digits as the token is
         written to returns the token's value exactly.
      2. The token is written to at least MIN_ANCHOR_DIGITS significant digits. One
         digit admits a rounding gap of up to fifty per cent, and on the first pass over
         the narrative it matched the literal "1" to a figure of 0.96 and "2" to 15.6.
      3. The pairing is mutual: that token is faithful to exactly one leaf, and that
         leaf has exactly one faithful token in the block. Anything else is refused, so
         a block naming four figures of one family cannot have them silently permuted.
      4. The token is prose rather than machinery: it is not inside a marker already
         placed and it is not inside a citation. See blank_machinery.

    Returns (marked text, [anchor], census, [suspect]). Everything refused is counted by
    reason. A suspect is a leaf with no faithful token whose block nonetheless holds a
    figure within SUSPECT_BAND of it: the sentence looks like it is quoting the quantity
    and getting it wrong. Suspects are reported, never marked.
    """
    by_id = {str(r.get("id")): r for r in records}
    census = {"citations": 0, "citations with no addressed leaf": 0,
              "leaves offered": 0, "anchored": 0,
              "refused: no faithful token in the block": 0,
              "of those, a near figure stands in the block (suspect)": 0,
              "refused: the token is faithful to more than one leaf": 0,
              "refused: the leaf has more than one faithful token": 0}
    blocks = scopes(text)
    taken, anchors, suspects = [], [], []

    # FIRST PASS. Which figures of the block are a faithful rendering of SOMETHING the
    # block cites, whichever record it belongs to. The union is what the suspect rule
    # consults below, and it has to be built before any citation is judged: on the
    # narrative as it stands, the first version of the rule consulted only the record
    # being judged and reported the mid-book cell 0.82 as a suspect against the print
    # cell 0.8363 of the same coin, which is two quantities of similar size and not a
    # stale figure at all.
    seen = []
    for citation in CITATION.finditer(text):
        record = by_id.get(citation.group(1))
        if record is None:
            seen.append((citation, None, None, None))
            continue
        leaves, _why = addressed_leaves(record)
        block = next((b for b in blocks if b[0] <= citation.start() <= b[1]),
                     (0, len(text)))
        seen.append((citation, leaves or None, block,
                     blank_machinery(text[block[0]:block[1]])))
    faithful_in_block = {}
    for _citation, leaves, block, blanked in seen:
        if not leaves:
            continue
        for span, _hits in _faithful_tokens(blanked, block[0], leaves).items():
            faithful_in_block.setdefault(block, set()).add(span)

    for citation, leaves, block, blanked in seen:
        ident = citation.group(1)
        census["citations"] += 1
        if not leaves:
            census["citations with no addressed leaf"] += 1
            continue
        candidates = {span: hits for span, hits
                      in _faithful_tokens(blanked, block[0], leaves).items()
                      if not any(not (span[1] <= a or span[0] >= b) for a, b in taken)}

        census["leaves offered"] += len(leaves)
        by_leaf = {}
        for span, hits in candidates.items():
            if len(hits) > 1:
                census["refused: the token is faithful to more than one leaf"] += 1
                continue
            name, written, scale = hits[0]
            by_leaf.setdefault(name, []).append((span, written, scale))
        for name in sorted(leaves):
            picks = by_leaf.get(name, [])
            if not picks:
                census["refused: no faithful token in the block"] += 1
                near = _near_figures(blanked, block[0], leaves[name]["artifact_value"],
                                     faithful_in_block.get(block, set()))
                for written, observed, scale in near:
                    census["of those, a near figure stands in the block (suspect)"] += 1
                    suspects.append({
                        "id": ident, "leaf": name, "token": written,
                        "artifact_value": leaves[name]["artifact_value"],
                        "scale": scale,
                        "relative_difference": abs(observed / scale
                                                   - leaves[name]["artifact_value"])
                        / max(abs(leaves[name]["artifact_value"]),
                              abs(observed / scale)),
                        "line": _where(text, block[0] + blanked.find(written))[0],
                    })
                continue
            if len(picks) > 1:
                census["refused: the leaf has more than one faithful token"] += 1
                continue
            span, written, scale = picks[0]
            taken.append(span)
            anchors.append({
                "id": ident, "leaf": name, "span": span, "token": written,
                "spec": spec_from_token(leaves[name]["artifact_value"], written, scale),
                "artifact_value": leaves[name]["artifact_value"],
                "line": _where(text, span[0])[0],
            })
            census["anchored"] += 1

    anchors.sort(key=lambda a: a["span"][0])
    out, cursor = [], 0
    for item in anchors:
        a, b = item["span"]
        reference = f"{item['id']}:{item['leaf']}" if item["leaf"] else item["id"]
        out.append(text[cursor:a])
        out.append(f"<!--#{reference}-->{text[a:b]}<!--/#{reference}-->")
        cursor = b
    out.append(text[cursor:])
    return "".join(out), anchors, census, suspects


def _faithful_tokens(blanked, offset, leaves):
    """{span: [(leaf, written, scale)]} for every figure of a block that renders a leaf.

    THE ONE PLACE the rendering question is asked, so the anchoring rule and the suspect
    rule cannot drift apart. Faithful means: rounding the artifact value to as many
    significant digits as the figure is written to returns the figure exactly.
    """
    found = {}
    for token in TOKEN.finditer(blanked):
        written = token.group(0)
        observed = parse_number(written)
        if observed is None:
            continue
        digits = significant_digits_of_text(written)
        if digits < MIN_ANCHOR_DIGITS:
            continue
        span = (offset + token.start(), offset + token.end())
        for name, entry in leaves.items():
            value = entry["artifact_value"]
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                continue
            for scale in ANCHOR_SCALES:
                rounded = round_significant(float(value) * scale, digits)
                if abs(rounded - observed) <= 1e-12 * max(1.0, abs(observed)):
                    found.setdefault(span, []).append((name, written, scale))
                    break
    return found


def _near_figures(blanked, offset, value, spoken):
    """Figures in a block within SUSPECT_BAND of `value` but not a rendering of it.

    A figure that faithfully renders ANY quantity the block cites is left out, whichever
    record it belongs to: it is that quantity's figure, and standing near this one as
    well is a coincidence of two quantities of similar size rather than evidence that
    the sentence quotes this one wrongly.
    """
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value == 0:
        return []
    out = []
    for token in TOKEN.finditer(blanked):
        span = (offset + token.start(), offset + token.end())
        if span in spoken:
            continue
        written = token.group(0)
        observed = parse_number(written)
        if observed is None:
            continue
        digits = significant_digits_of_text(written)
        if digits < MIN_ANCHOR_DIGITS:
            continue
        for scale in ANCHOR_SCALES:
            if round_significant(float(value) * scale, digits) == observed:
                break
            gap = abs(observed / scale - float(value)) / max(abs(float(value)),
                                                             abs(observed / scale))
            if gap <= SUSPECT_BAND:
                out.append((written, observed, scale))
                break
    return out


# ----------------------------------------------------------------------------------
# THE RUN
# ----------------------------------------------------------------------------------

def _report(resolved):
    changed = [s for s in resolved if s["changed"]]
    undeclared = [s for s in resolved if not s["display_declared"]]
    print(f"  figures substituted      : {len(resolved)}")
    print(f"  predicate for 'changed'  : the characters standing between the markers "
          f"differ from")
    print(f"                             what the artifact holds, written as the "
          f"register declares")
    print(f"  unchanged                : {len(resolved) - len(changed)}")
    print(f"  changed                  : {len(changed)}")
    for entry in changed:
        print(f"      line {entry['line']:4d}  #{entry['reference']}  "
              f"{entry['stood_in_the_text']!r} -> {entry['written']!r}  "
              f"[{entry['source_file']} :: {entry['artifact_key_path']}]")
    if undeclared:
        print(f"  written by the fallback  : {len(undeclared)} "
              f"({FALLBACK})")
    return changed


def _write_provenance(out_path, document_name, resolved, started):
    """A sidecar naming, for every figure in the assembled document, where it came from.

    The assembled document is prose and carries no machinery, so its provenance goes
    beside it. artifact.write is the one writer of a results file in this tree and it
    is used here too, so this file records the same things about itself as every other.
    """
    directory = os.path.dirname(os.path.abspath(out_path)) or "."
    name = os.path.basename(out_path) + ".provenance.json"
    return artifact.write(
        name,
        {"document": os.path.basename(document_name),
         "figures_substituted": len(resolved),
         "figures_whose_text_was_stale": sum(1 for s in resolved if s["changed"]),
         "substitutions": resolved},
        script=__file__,
        inputs=[document_name, gate.REGISTRY_NAME],
        scope={
            "population": (f"{len(resolved)} marked figures in "
                           f"{os.path.basename(document_name)}, each addressed by one "
                           "record of the register of quantities"),
            "window": ("n/a: this file records where figures came from and reads no "
                       "market data"),
            "coins": "n/a: this file records where figures came from",
        },
        started=started, out_dir=directory)


def main(argv):
    started = artifact.start_clock()
    mode = None
    for candidate in ("--build", "--check", "--propose"):
        if candidate in argv:
            mode = candidate
    if mode is None:
        print(__doc__.strip().splitlines()[-6:][0])
        print("usage: prose_assemble.py --build|--check|--propose DOC [-o OUT] "
              "[--display FILE] [--declare FILE] [--registry PATH]")
        return 2

    def option(flag, default=None):
        return argv[argv.index(flag) + 1] if flag in argv else default

    document = option(mode)
    if not document or document.startswith("-"):
        print(f"{mode} needs the document to read")
        return 2
    out_path = option("-o")
    overlay = load_overlay(option("--display"))
    records = load_register(argv)
    with open(document, encoding="utf-8") as fh:
        text = fh.read()

    print("=" * 76)
    print("  A DOCUMENT ASSEMBLED FROM ITS ARTIFACTS - prose_assemble")
    print("=" * 76)
    print(f"  document                 : {os.path.basename(document)}")
    print(f"  register of quantities   : {gate.REGISTRY_NAME}, {len(records)} records")

    if mode == "--propose":
        marked, anchors, census, suspects = anchor(text, records)
        print(f"  population               : every written figure inside the block of a "
              f"[#ID] citation")
        print(f"  predicate for 'anchored' : the figure is what the artifact value "
              f"rounds to at the")
        print(f"                             figure's own precision, at least "
              f"{MIN_ANCHOR_DIGITS} digits, and the")
        print(f"                             pairing of figure and quantity is mutual")
        for key, value in census.items():
            print(f"      {value:5d}  {key}")
        if suspects:
            print(f"  figures standing near a quantity they are not a rounding of. "
                  f"Each is a place")
            print(f"  to read: either the text has gone stale or the register's address "
                  f"is wrong:")
            for item in suspects:
                print(f"      line {item['line']:4d}  #{item['id']}:{item['leaf']}  "
                      f"text {item['token']!r} against artifact "
                      f"{item['artifact_value']!r}"
                      + (f" (scaled by {item['scale']:g})" if item["scale"] != 1 else "")
                      + f", {item['relative_difference']:.2%} apart")
        if out_path:
            with open(out_path, "w", encoding="utf-8") as fh:
                fh.write(marked)
            print(f"  marked-up copy           -> {os.path.basename(out_path)}")
        patch = {}
        for item in anchors:
            if item["spec"]:
                patch[f"{item['id']}:{item['leaf']}"] = item["spec"]
        declare = option("--declare")
        if declare:
            with open(declare, "w", encoding="utf-8") as fh:
                json.dump(patch, fh, indent=2, ensure_ascii=False, sort_keys=True)
                fh.write("\n")
            print(f"  display declarations     -> {os.path.basename(declare)}, "
                  f"{len(patch)} quantities. They belong in the register, one "
                  f"{DISPLAY_FIELD!r} field per record")
        return 0

    try:
        assembled, resolved = assemble(text, records, overlay)
    except BuildError as exc:
        print("-" * 76)
        print("  THE DOCUMENT CANNOT BE ASSEMBLED. Every fault, with its place:")
        for line in str(exc).splitlines():
            print(f"      {line}")
        return 1
    changed = _report(resolved)

    if mode == "--check":
        print("-" * 76)
        verdict = "REFUTED" if changed else "CONFIRMED"
        print(f"  VERDICT: {verdict} -- the figures written in the document "
              f"{'do not all' if changed else 'all'} equal their artifacts")
        return 1 if changed else 0

    if not out_path:
        print("  --build needs -o OUT to write the assembled document")
        return 2
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(assembled)
    provenance = _write_provenance(out_path, document, resolved, started)
    print(f"  assembled document       -> {os.path.basename(out_path)}")
    print(f"  provenance               -> {os.path.basename(provenance)}")
    return 0


# ----------------------------------------------------------------------------------
# SELF-TEST
#
# In the module rather than in a test directory, because this repository has none. Every
# case that can be taken from the live tree is taken from it: a fixture proves what the
# fixture was built to prove, while the live register and the live artifacts are what
# the script will actually be run against.
#
#     uv run --no-project python3 prose_assemble.py --self-test
# ----------------------------------------------------------------------------------

def _self_test():
    # The tally counts as each assertion is made rather than being typed beside them,
    # and it lives in evidence.py, where the gate this file imports reads the same one.
    # Binding the method to a plain name keeps every call site below unchanged.
    tally = Tally()
    expect = tally.expect

    records = load_register()
    by_id = {str(r.get("id")): r for r in records}

    # THE FIGURE IS READ INDEPENDENTLY OF THE ROAD UNDER TEST. D01 states the row count
    # of the main tape; the file is opened here directly, so the assertion below is
    # against the artifact rather than against the machinery that fetched it.
    tape = gate.locate(by_id["D01"]["source_file"])
    with open(tape, encoding="utf-8") as fh:
        rows = json.load(fh)["total_rows"]

    # CASE ONE, THE SUBSTITUTION THAT MUST HAPPEN. The marked text carries a figure and
    # the assembled text must carry exactly what the artifact holds.
    marked = f"The tape holds <!--#D01-->{rows}<!--/#D01--> fills.\n"
    built, resolved = assemble(marked, records)
    expect((
        (built == f"The tape holds {rows} fills.\n",
         f"a marked figure must be replaced by the artifact's own: got {built!r}"),
        (len(resolved) == 1 and not resolved[0]["changed"],
         "a document already holding the right figure must report nothing changed"),
        (resolved[0]["artifact_value"] == rows,
         "the substituted value must be the one the artifact holds"),
        ("<!--" not in built, "no marker may survive into the assembled document"),
    ))

    # CASE TWO, THE OPPOSITE. A reference to an identifier that does not exist must stop
    # the build and name the identifier and the place.
    broken = "Line one.\nThe tape holds <!--#ZZ99-->1<!--/#ZZ99--> fills.\n"
    try:
        assemble(broken, records)
        expect(((False, "a reference to an unknown identifier must fail the build"),))
    except BuildError as exc:
        message = str(exc)
        expect((
            ("ZZ99" in message, "the failure must name the identifier"),
            ("line 2" in message, "the failure must name the line"),
            ("register" in message,
             "the failure must say what kind of thing was not found"),
        ))

    # THE STALENESS PREDICATE, ON TWO OPPOSITE CASES. Same document, one digit moved.
    stale = f"<!--#D01-->{rows - 1}<!--/#D01-->\n"
    _text, moved = assemble(stale, records)
    _text, still = assemble(f"<!--#D01-->{rows}<!--/#D01-->\n", records)
    expect((
        (moved[0]["changed"] and moved[0]["written"] == str(rows),
         "a figure in the text that differs from its artifact must be reported changed"),
        (not still[0]["changed"],
         "a figure in the text that equals its artifact must not be reported changed"),
    ))

    # A RECORD HOLDING SEVERAL FIGURES REFUSES AN UNQUALIFIED REFERENCE, and names the
    # references that would work. M28 addresses the per-coin persistence cells.
    leaves, _why = addressed_leaves(by_id["M28"])
    try:
        assemble("<!--#M28-->0.8<!--/#M28-->\n", records)
        expect(((False, "an ambiguous reference must fail the build"),))
    except BuildError as exc:
        expect((
            ("#M28:BTC.10" in str(exc),
             "the failure must list the references that would resolve"),
        ))
    try:
        assemble("<!--#M28:NOSUCH-->0.8<!--/#M28:NOSUCH-->\n", records)
        expect(((False, "a sub-figure the record does not address must fail"),))
    except BuildError as exc:
        expect((("NOSUCH" in str(exc), "the failure must name the sub-figure"),))

    # MALFORMED MARKUP IS A FAULT, NOT SOMETHING TO STEP OVER.
    for bad, why in (
        ("<!--#D01-->2480267\n", "an unclosed marker"),
        ("<!--#D01-->2480267<!--/#D02-->\n", "a crossed pair"),
        ("2480267<!--/#D01-->\n", "a closing marker with no opener"),
    ):
        try:
            assemble(bad, records)
            expect(((False, f"{why} must fail the build"),))
        except BuildError:
            expect(((True, f"{why} must fail the build"),))

    # HOW A FIGURE IS WRITTEN DOWN. Rounding is significant digits measured where the
    # figure sits, and the separator and sign are the register's to declare.
    expect((
        (render(0.8047783992567011, {"digits": 4}) == "0.8048",
         "four significant digits of 0.80477... must be 0.8048"),
        (render(0.9043320410395064, {"digits": 2}) == "0.90",
         "a trailing zero must survive: two digits of 0.9043 is 0.90"),
        (render(2480267, {"thousands": " "}) == "2 480 267",
         "a count must group in threes when the register declares a separator"),
        (render(2480267, {}) == "2480267",
         "with nothing declared a count is written plainly"),
        (render(0.11410001805380032, {"digits": 3, "scale": 100.0}) == "11.4",
         "a share written as a percentage is declared by scale, never by the text"),
        (render(0.5626, {"digits": 4, "sign": "always"}) == "+0.5626",
         "a leading plus is declared"),
        (render(-0.035, {"digits": 2, "minus": "unicode"}) == "−0.035",
         "the minus sign is declared"),
    ))

    # SIGNIFICANT DIGITS ARE COUNTED IN THE CHARACTERS, because float() forgets the
    # trailing zero that tells you how precisely the figure was written.
    expect((
        (significant_digits_of_text("0.90") == 2, "0.90 is written to two digits"),
        (significant_digits_of_text("0.8048") == 4, "0.8048 is written to four"),
        (significant_digits_of_text("2 480 267") == 7, "a grouped count keeps its digits"),
        (significant_digits_of_text("1") == 1, "1 is written to one digit"),
        (significant_digits_of_text("15.6") == 3, "15.6 is written to three"),
    ))

    # THE ANCHORING PREDICATE, ON TWO OPPOSITE CASES DRAWN FROM THE LIVE REGISTER.
    # It must reach the figure the narrative actually prints, and it must refuse the
    # coarse literals that the first version of it accepted.
    btc10 = leaves["BTC.10"]["artifact_value"]
    marked, anchors, census, _s = anchor(
        f"Persistence at ten seconds is 0.8048 on bitcoin. [#M28]\n", records)
    expect((
        (any(a["leaf"] == "BTC.10" for a in anchors),
         "the literal the narrative prints must anchor to the leaf it names"),
        ("<!--#M28:BTC.10-->0.8048<!--/#M28:BTC.10-->" in marked,
         f"the anchored literal must be wrapped: got {marked!r}"),
        (abs(round_significant(btc10, 4) - 0.8048) < 1e-12,
         "the test's own expectation must be the artifact's figure rounded, not a "
         "number typed here"),
    ))
    # The digit floor, on the pair that isolates it. M12's flagged share is 0.1141 and
    # it is the only leaf of that record a one-digit literal could reach, so mutual
    # uniqueness cannot carry this case and only the floor can. Written to one digit the
    # literal must be refused; written to three it must anchor. Verified by mutation:
    # dropping the floor to one digit makes the first of these two anchor.
    _m, coarse, _c, _s = anchor("The flagged share is 0.1 of them. [#M12]\n", records)
    _m, fine, _c, _s = anchor("The flagged share is 0.114 of them. [#M12]\n", records)
    expect((
        (not coarse,
         "a one-digit literal must not anchor a figure of 0.1141: that rounding gap "
         "runs to fifty per cent, and it is how '1' matched 0.96 and '2' matched 15.6"),
        (any(a["leaf"] == "youden_flag_fraction" for a in fine),
         "three digits of the same figure must anchor, so the refusal above is the "
         "floor talking and not the figure being unreachable"),
    ))

    # Faithfulness, on the pair that isolates it: one unit off in the last digit the
    # literal is written to. Nothing about the size of the gap is consulted -- 0.8047
    # is a tenth of a per cent away from the figure and is still not a rendering of it.
    _m, wrong, _c, _s = anchor("Persistence is 0.8047 on bitcoin. [#M28]\n", records)
    _m, right, _c, _s = anchor("Persistence is 0.8048 on bitcoin. [#M28]\n", records)
    expect((
        (not any(a["leaf"] == "BTC.10" for a in wrong),
         "a literal one unit off in its own last digit must not anchor"),
        (any(a["leaf"] == "BTC.10" for a in right),
         "the correctly rounded literal must anchor, so the refusal above is "
         "faithfulness talking and not the block being unreachable"),
    ))

    # Mutual uniqueness, on both of its halves and each against its opposite. The two
    # ether cells of M28 are 0.77362 and 0.77344, so two written digits cannot tell them
    # apart and four can; and one leaf offered the same literal twice has no way to
    # choose between the two places.
    _m, blurred, _c, _s = anchor("Ether sits at 0.77 on both. [#M28]\n", records)
    _m, sharp, _c, _s = anchor("Ether at five seconds is 0.7736. [#M28]\n", records)
    _m, twice, _c, _s = anchor("Bitcoin is 0.8048, and again 0.8048. [#M28]\n", records)
    expect((
        (not blurred,
         "a literal faithful to two leaves of the same family must not be assigned to "
         "either: that is how a block of four cells gets silently permuted"),
        (any(a["leaf"] == "ETH.5" for a in sharp),
         "the same family at four digits must anchor, so the refusal above is the "
         "ambiguity talking"),
        (not twice,
         "a leaf offered the same literal in two places must not pick one of them"),
    ))

    # MACHINERY IS NOT PROSE, ON THE PAIR THAT ISOLATES IT. The same two digits, once
    # standing inside the citation [#M11] and once standing in the sentence, with M12
    # cited both times so its flagged share of 0.1141 is offered as a percentage both
    # times. Taken from the live tree rather than invented: on the narrative of
    # 2026-07-31 the first of these two anchored, and --build would then have rewritten
    # the citation into [#M11.4].
    _m, in_citation, _c, _s = anchor(
        "The worst decile is the other road to the same line. [#M11] [#M12]\n", records)
    _m, in_prose, _c, _s = anchor(
        "The line falls at 11 per cent of the counterparties. [#M12]\n", records)
    expect((
        (not any(a["leaf"] == "youden_flag_fraction" for a in in_citation),
         "the digits of a citation identifier must not be read as a written figure"),
        (any(a["leaf"] == "youden_flag_fraction" for a in in_prose),
         "the same two digits written in the sentence must anchor, so the refusal "
         "above is the blanking talking and not the figure being unreachable"),
    ))

    # A DISPLAY FILE MAY NOT CARRY A VALUE. That would be a second home for the number,
    # which is the defect the whole mechanism exists to end.
    import tempfile
    with tempfile.TemporaryDirectory() as work:
        path = os.path.join(work, "display.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"D01": {"digits": 3, "value": 1.0}}, fh)
        try:
            load_overlay(path)
            expect(((False, "a display file carrying a value must be refused"),))
        except BuildError as exc:
            expect((("value" in str(exc),
                     "the refusal must name what it refused"),))

    # THE ASSEMBLY IS IDEMPOTENT ON A MARKED SOURCE: assembling with the markers kept
    # returns a document that assembles to the same thing again.
    kept, _r = assemble(marked, records, keep_markers=True)
    again, _r2 = assemble(kept, records, keep_markers=True)
    expect(((kept == again, "assembling a marked source twice must not drift"),))

    print("=" * 76)
    print("  prose_assemble self-test -- the value comes from the artifact, the text "
          "holds only its name")
    print("=" * 76)
    for why in tally.failures:
        print(f"  FAIL  {why}")
    print(f"  {'PASS' if not tally.failures else 'FAIL'}: "
          f"{tally.asserted - len(tally.failures)} of {tally.asserted} assertions hold")
    return 1 if tally.failures else 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(_self_test())
    try:
        sys.exit(main(sys.argv[1:]))
    except BuildError as exc:
        print(f"  {exc}")
        sys.exit(1)
