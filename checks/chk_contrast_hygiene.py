#!/usr/bin/env python3
"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-08-03
References: none (repository gate; it declares no quantity of its own and compares
leaves of one results file against each other).

ARE THE TWO THINGS WHOSE DIFFERENCE IS PUBLISHED ACTUALLY COMPARABLE.

Why this gate exists, and it is a measurement rather than a principle. The tree has
several layers of checking and they all put the same question about one number.
Provenance asks whether the code that produced it is the code on disk; input freshness
asks whether the file it was computed from still is; the register sweep asks whether the
same number appears at every place that quotes it. None asks the third question, which
is whether the two things a published difference is a difference OF differ along the one
axis the text names.

The gap has a price and it was paid on 2026-08-03. The quoter bake-off published that
bbgl beat as_toxicity by 0.636 bps of pooled net cost at the base fee tier, and the
prose attributed the gap to the form in which counterparty identity is used. The arms
differed by a factor of four in realised quote width -- 1.4423 bps of mean surcharge on
64.42% of fills against 6.3646 on 100% -- and the recapture that books the cost is an
approximation with no queue and no fill probability, so a printed fill is booked to the
arm whatever the arm quoted and standing wider is free. That difference passed all five
instruments the tree had, each of which is silent by construction: each asks whether it
is the same number, none asks whether the comparison is a comparison.

THREE STATES PER PAIR, AND THE MIDDLE ONE IS THE WHOLE DESIGN.

The first version of this gate had two states, declared and not declared, and demanded
a declaration for every pair inside a container on the grounds that a container which
publishes an ordering over its own keys has thereby published every pair. The artifact
says otherwise about itself, in its own words at declared_axis_comparisons.why, and it
is right: a ranking orders arms on one metric and does not thereby make any two of them
comparable. Against a nine-arm bake-off the two-state rule produced 36 findings of which
none was a defect, and a gate that is red for a reason nobody can act on is a gate
people stop reading. So:

  DECLARED AS A COMPARISON      a manifest names the pair, gives its axis and the list
                                held equal with a tolerance on each, and the delta
                                block marks the difference published. Every held-equal
                                address that is addressable under an arm is RE-MEASURED
                                on the leaves, and the verdict compared against the
                                producer's own
  DECLARED AS NOT A COMPARISON  both arms are named in the declaration's ranking-only
                                list and no manifest publishes the pair. Reported with
                                its leaf-difference count and nothing is asked of it:
                                the work makes no claim here
  NOT DECLARED AT ALL           an arm in neither. This is the finding, and it fails

WHAT IS READ RATHER THAN RESTATED. The axis, the held-equal list, the tolerance on each
quantity and the grounds for the middle state all live in the artifact and are read from
it at the addresses the declaration names. A check that retypes the rule it checks goes
on asserting the old rule after the rule is fixed, and its disagreement then looks like
a finding without being one. What the declaration file adds is only what no address can
say: that a person considered a pair and chose to publish no difference for it.

AND WHAT IS NOT BELIEVED. The producer writes `holds` beside each held-equal quantity
and `all_held_equal_quantities_hold` beside the manifest. This gate ignores both and
re-measures from the leaves, then compares its own verdict against them and reports a
disagreement as a finding in its own right. Reading the summary field would make this a
check that the producer can write a True, which is not a check.

THE TOLERANCE IS DECLARED PER QUANTITY AND IS HONOURED, AND THAT IS MEASURED RATHER
THAN polite. The producer solves a pass-through so that two arms land on one width, and
one published difference lands at 2.9e-16 relative against a declared rtol of 1e-09. A
comparator demanding exact equality calls that a breach and cries wolf about the
seventeenth decimal; one that ignores the declared tolerance passes a real breach. So
the rtol beside each quantity is used, and the measured gap is printed next to it so a
reader sees the margin rather than a verdict.

THE DIRECTION OF FAILURE, WHICH DECIDES the small things. A false alarm stops somebody
and costs a look; a run that reads clean over a confounded difference goes into a
published paper. Wherever the choice arose this gate took the noisy side: a declared
arm missing from the artifact fails rather than being skipped, an arm that is present
but is not a mapping fails rather than being walked to one nameless leaf, a held-equal
address that is not under both arms is a breach rather than a pass, a leaf under one arm
and not the other counts as TWO differences so a rename cannot read as a move, NaN
equals NaN and True is not 1.

CALIBRATION, RUN ON EVERY INVOCATION RATHER THAN BEHIND A FLAG. There are two decisions
here and they fail differently, so there are four cases and not two.

  coverage, silent    as_toxicity_ew against naive_const, live: the middle state
  coverage, fires     an arm in no state at all, INJECTED
  held equal, silent  as_toxicity_ew against bbgl, live: a published difference
  held equal, fires   a fixture manifest whose held-equal address moved, INJECTED

The firing halves are injected on purpose. A firing case taken from the live tree
empties the day somebody repairs what it was watching, and the gate is then calibrated
on a population with no failures left in it -- which is how two instruments of this
project came to be red or silent while checking nothing.

    uv run --no-project --with-requirements requirements.txt python3 \\
        checks/chk_contrast_hygiene.py
    uv run --no-project --with-requirements requirements.txt python3 \\
        checks/chk_contrast_hygiene.py --pair "quoter_bakeoff quoters.K50 as_toxicity_ew vs bbgl"
"""
import argparse
import itertools
import json
import math
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import artifact                                                        # noqa: E402
import contrast_declarations as decl                                   # noqa: E402
from evidence import make_expect, mismatch_text, report_gate           # noqa: E402

OUT_NAME = "chk_contrast_hygiene_results.json"

# The three states. Named as constants because the tally, the gate, the screen and the
# calibration all speak about the same three, and a state spelled twice is a state that
# can drift apart from itself.
COMPARISON = "declared_a_comparison"
NOT_A_COMPARISON = "declared_not_a_comparison"
UNDECLARED = "not_declared"
STATES = (COMPARISON, NOT_A_COMPARISON, UNDECLARED)

# Differing leaves outside the manifest carried into the results file, per pair in the
# first state. Breaches are always carried whole, however many: they are the findings.
# Pairs in the middle state carry counts only. The 72 pairs of this artifact hold tens
# of thousands of differing leaves between them, and writing them out would make this
# file larger than the artifact it is about while saying nothing the block tally does
# not.
OUTSIDE_KEPT_PER_PAIR = 40


# =====================================================================
# PATHS, PATTERNS AND WHAT COUNTS AS THE SAME VALUE
# =====================================================================

def leaves(node, prefix=""):
    """Every scalar under `node`, as (dotted path, value).

    A list index is its own path segment written [i], so a pattern segment can match it
    like any other. _meta is skipped wherever it appears: it describes the file rather
    than the arm.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            if key == artifact.META_KEY:
                continue
            yield from leaves(value, f"{prefix}.{key}" if prefix else str(key))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from leaves(value, f"{prefix}.[{index}]" if prefix else f"[{index}]")
    else:
        yield prefix, node


def matches_pattern(path, pattern):
    """Does a dotted leaf path match a declared pattern.

    "*" matches exactly one segment, "**" matches any number including none. Anything
    else must match a segment literally. Written out rather than translated into a
    regular expression because a pattern that silently means something other than it
    reads is the failure this whole gate is about.
    """
    return _match(path.split("."), pattern.split("."))


def _match(path, pattern):
    if not pattern:
        return not path
    head, rest = pattern[0], pattern[1:]
    if head == "**":
        if not rest:
            return True
        return any(_match(path[i:], rest) for i in range(len(path) + 1))
    if not path:
        return False
    if head == "*" or head == path[0]:
        return _match(path[1:], rest)
    return False


def same_value(left, right):
    """Whether two leaves carry the same value, with the two traps closed by hand.

    NaN EQUALS NaN HERE. Two arms that both report an undefined interval end agree
    about it; `!=` says they differ, and on a pair this gate must stay silent on that
    alone manufactured 72 differences out of 219.

    TRUE IS NOT 1. Python compares them equal, so a flag that became a count, or a
    count of one that became a flag, reads as unchanged. Both have happened in this
    project's own hand-rolled counts, which is why neither is left to the default.
    """
    if isinstance(left, bool) != isinstance(right, bool):
        return False
    if (isinstance(left, float) and isinstance(right, float)
            and math.isnan(left) and math.isnan(right)):
        return True
    if (isinstance(left, (int, float)) and isinstance(right, (int, float))
            and not isinstance(left, bool) and not isinstance(right, bool)):
        if math.isnan(left) or math.isnan(right):
            return False
        return left == right
    return left == right


def relative_gap(left, right):
    """|a-b| / max(|a|,|b|) for two finite numbers, else None.

    Reported beside both values because a bare pair of numbers does not say whether a
    difference is a rounding artefact or a factor of four, and the finding this gate was
    written for is a factor of four sitting under a difference of 0.636.
    """
    if not (isinstance(left, (int, float)) and isinstance(right, (int, float))):
        return None
    if isinstance(left, bool) or isinstance(right, bool):
        return None
    if math.isnan(left) or math.isnan(right) or math.isinf(left) or math.isinf(right):
        return None
    scale = max(abs(left), abs(right))
    if scale == 0.0:
        return 0.0
    return abs(left - right) / scale


def dig(node, dotted):
    """The value at a dotted path, as (found, value).

    The flag is separate from the value because None is a value a leaf can hold, and a
    gate that could not tell an absent address from an address holding null would report
    an unreachable held-equal quantity as one that agreed.
    """
    for segment in dotted.split("."):
        if not isinstance(node, dict) or segment not in node:
            return False, None
        node = node[segment]
    return True, node


# =====================================================================
# READING THE PRODUCER'S OWN DECLARATION OUT OF THE ARTIFACT
# =====================================================================

def published_manifests(document, declaration):
    """The pairs the artifact itself says it publishes, keyed by frozenset of arms.

    READ AND NOT RESTATED. The axis, the held-equal list and the tolerance on each are
    the producer's, at the address the declaration names. A check carrying its own copy
    would go on asserting the old rule after the rule is fixed, and its disagreement
    would then look like a finding without being one.

    A manifest counts as publishing a difference only when the delta block marks it
    published AND the manifest records no refusal. A refused manifest is a difference
    the producer computed and withheld, which is the producer doing its job, so that
    pair goes to the middle state carrying the refusal as its grounds.

    Returns (published, withheld, the manifest block was found at all).
    """
    found, manifests = dig(document, declaration["manifests_at"])
    if not found or not isinstance(manifests, dict):
        return {}, {}, False
    found, deltas = dig(document, declaration["deltas_at"])
    deltas = deltas if found and isinstance(deltas, dict) else {}

    published, withheld = {}, {}
    for name, manifest in manifests.items():
        if not isinstance(manifest, dict):
            continue
        arm_a, arm_b = manifest.get("arm_a"), manifest.get("arm_b")
        if not (isinstance(arm_a, str) and isinstance(arm_b, str)):
            continue
        delta = deltas.get(name)
        is_published = bool(isinstance(delta, dict) and delta.get("published"))
        refusal = manifest.get("refusal")
        row = {"manifest": name, "arm_a": arm_a, "arm_b": arm_b,
               "axis": manifest.get("axis"),
               "consequence_of_the_axis": manifest.get("consequence_of_the_axis"),
               "not_held_equal": manifest.get("not_held_equal"),
               "producer_says_all_hold":
                   manifest.get("all_held_equal_quantities_hold"),
               "refusal": refusal,
               "held_equal_measured": manifest.get("held_equal_measured") or []}
        if is_published and refusal is None:
            published[frozenset((arm_a, arm_b))] = row
        else:
            row["why_not_published"] = (
                "the manifest records a refusal, so the producer computed this "
                f"difference and withheld it: {str(refusal)[:80]}"
                if refusal is not None else
                "the delta block does not mark this difference published")
            withheld[frozenset((arm_a, arm_b))] = row
    return published, withheld, True


def held_equal_specs(manifest, prefix):
    """The manifest's held-equal quantities, split into re-measurable and not.

    A quantity is re-measurable here when its measured_by address is relative to an arm,
    which the producer marks with a template prefix. The rest are settings and solve
    fields shared by both arms by construction -- the recapture fraction, the headline
    horizon, the eligible-wallet count -- and no walk of the two arms' leaves reaches
    them.

    THE UNREACHABLE ONES ARE NAMED AND NOT COUNTED AS RE-MEASURED. Folding them into
    the re-measured count would report six quantities verified where three were, which
    is the direction of error that reaches a report: a number saying more was measured
    than was.

    BUT UNREACHABLE IS NOT THE SAME AS UNCHECKED, AND TREATING IT SO WAS A HOLE IN THIS
    GATE UNTIL 2026-08-05. The producer records both values beside every held-equal
    quantity, reachable or not. For an unreachable one this gate cannot fetch the
    numbers and so cannot catch a wrong fetch -- but it can re-do the arithmetic on what
    was recorded, and that catches the failure that matters: two recorded values that
    differ beyond the declared tolerance under a `holds` of true.

    The hole was an inconsistency in this gate's own design rather than an oversight
    about the producer. It already refuses to believe `holds` on every arm-relative row
    and re-measures instead; on the rest it was believing `holds` in silence. Refusing a
    summary field on 21 rows of 24 and accepting it on the other 3 is the accepting part
    that would carry a bad figure.

    The distinction the classifier manifests made visible: in the equal-width manifests
    this row reads ONE address for both arms, so it is true by construction and nothing
    could ever differ. In the classifier manifests the two sides are genuinely different
    addresses -- what the model scored and charged, against what the comparison arm's
    solve runs over -- so it CAN differ, and a classifier coming back short of a
    counterparty the quoter charges is exactly what would show up there. Both printed as
    "not re-measured", which flattened a tautology and a live measurement into one word.

    THIS GATE STILL CANNOT TELL THOSE TWO APART, AND NO LONGER PRETENDS TO. The first
    version of the fix marked a row whose two recorded values are equal as the one-
    address kind, which is structure inferred from a coincidence of values, and it got
    the classifier row wrong on the live tree straight away: two different addresses
    agreeing at 2069 today were reported as a row that could never differ. Separating
    them would take parsing the prose of measured_by, a predicate keyed on wording that
    breaks when the wording changes. So the address is printed and the reader decides.
    """
    reachable, unreachable = [], []
    for quantity in manifest["held_equal_measured"]:
        if not isinstance(quantity, dict):
            continue
        address = quantity.get("measured_by") or ""
        row = {"quantity": quantity.get("quantity"),
               "measured_by": address,
               "rtol": quantity.get("rtol"),
               "producer_says_holds": quantity.get("holds")}
        if address.startswith(prefix):
            row["arm_relative_path"] = address[len(prefix):]
            reachable.append(row)
        else:
            row["why_unreachable"] = (
                "the address is not relative to an arm, so it names a setting or a "
                "solve field shared by both arms rather than a leaf under either. The "
                "values the producer recorded are re-checked arithmetically below; "
                "what cannot be checked from here is whether it fetched the right ones")
            row["recorded_left"] = quantity.get("arm_a")
            row["recorded_right"] = quantity.get("arm_b")
            unreachable.append(row)
    return reachable, unreachable


def recheck_recorded(specs):
    """Re-do the arithmetic on the values the producer recorded for an unreachable row.

    Weaker than measure_held_equal by exactly one thing, and the difference is stated on
    every row rather than left for a reader to remember: this compares numbers the
    PRODUCER fetched, so a wrong fetch is invisible here and only a wrong comparison is
    caught. It is strictly more than believing `holds`, which is what this gate did with
    these rows before 2026-08-05.

    A row whose two recorded values differ beyond the declared rtol is a breach: the
    manifest says the quantity is held equal and its own numbers say it is not, and the
    difference should have been withheld. A row where this verdict and the producer's
    `holds` disagree is a disagreement, and the existing rule for that fires.
    """
    rows = []
    for spec in specs:
        left, right = spec.get("recorded_left"), spec.get("recorded_right")
        row = dict(spec)
        rtol = spec["rtol"] if isinstance(spec["rtol"], (int, float)) else 0.0
        gap = relative_gap(left, right)
        if gap is None:
            # Either value non-finite, or not a pair of numbers at all. Identity is the
            # only claim left, and a NaN recorded for a quantity declared held equal is
            # a quantity that was never established, not one that agreed.
            finite_pair = all(isinstance(v, (int, float)) and not isinstance(v, bool)
                              and math.isfinite(v) for v in (left, right))
            row["holds"] = bool(finite_pair) and same_value(left, right)
            row["measured_gap"] = None
            row["why"] = (
                "the recorded values are not a pair of finite numbers, so nothing was "
                "established: recorded "
                f"{_plain(left)!r} against {_plain(right)!r}")
        else:
            row["holds"] = gap <= rtol
            row["measured_gap"] = gap
            row["why"] = (f"recorded {_plain(left)!r} against {_plain(right)!r}, "
                          f"relative gap {gap:.3e} against the declared rtol "
                          f"{rtol:.3e} -- the producer's own numbers, re-compared")
        # NO CLAIM IS MADE ABOUT HOW MANY ADDRESSES WERE READ, AND THE FIRST VERSION OF
        # THIS FUNCTION MADE ONE. It marked a row whose two recorded values are equal as
        # "one address read for both arms, so it cannot differ". That is a statement
        # about STRUCTURE inferred from a coincidence of VALUES, and it was wrong on the
        # live tree within minutes of being written: the classifier manifests read
        # ml_gate.n_wallets_charged_<arm> against equal_width_solve.n_wallets_floor_
        # eligible -- two genuinely different addresses, which happen to agree at 2069
        # on this run -- and the mark told a reader the row could never differ. That row
        # is the one that would catch a classifier coming back short of a counterparty
        # the quoter charges, so the error pointed at the safe reading of the one row
        # here with something to say.
        #
        # Telling the two apart would mean parsing the prose of measured_by, which is a
        # predicate keyed on wording and would break the first time the wording changed.
        # So the row says what is known and stops: the values agree, and this gate did
        # not fetch them.
        row["addresses_not_established"] = (
            "this gate did not fetch these values, so it cannot tell one address read "
            "for both arms from two addresses that happen to agree. Read measured_by "
            "for which it is")
        rows.append(row)
    return rows


def measure_held_equal(container, arm_a, arm_b, specs):
    """Re-measure each reachable held-equal quantity on the leaves. One row each.

    The rtol the producer declared beside the quantity is used, and the measured gap
    reported next to it. Not politeness: one published difference of this tree lands at
    2.9e-16 relative against a declared 1e-09, so exact equality would cry wolf about
    the seventeenth decimal while ignoring the declaration would pass a real breach.

    The producer's own `holds` is carried through and compared, never trusted. A gate
    reading that field would be checking that the producer can write a True.
    """
    rows = []
    for spec in specs:
        path = spec["arm_relative_path"]
        found_a, value_a = dig(container[arm_a], path)
        found_b, value_b = dig(container[arm_b], path)
        row = dict(spec)
        row.update({"left": _plain(value_a), "right": _plain(value_b),
                    "found_under_left": found_a, "found_under_right": found_b})
        if not (found_a and found_b):
            missing = ("both arms" if not (found_a or found_b)
                       else (arm_b if found_a else arm_a))
            row["holds"] = False
            row["measured_gap"] = None
            row["why"] = (f"the declared address {path} is not under {missing}, so a "
                          f"quantity the manifest says is held equal cannot be "
                          f"measured at all, which leaves it unverified rather than "
                          f"verified")
            rows.append(row)
            continue
        gap = relative_gap(value_a, value_b)
        rtol = spec["rtol"] if isinstance(spec["rtol"], (int, float)) else 0.0
        if gap is None:
            row["holds"] = same_value(value_a, value_b)
            row["measured_gap"] = None
            row["why"] = ("not a pair of finite numbers, so compared for identity "
                          "rather than against a tolerance")
        else:
            row["holds"] = gap <= rtol
            row["measured_gap"] = gap
            row["why"] = (f"relative gap {gap:.3e} against the declared rtol "
                          f"{rtol:.3e}")
        rows.append(row)
    return rows


# =====================================================================
# COMPARING TWO ARMS LEAF BY LEAF
# =====================================================================

def compare_arms(container, left_name, right_name, held_paths=()):
    """Every leaf under both arms, and which of them the manifest does not mention.

    A leaf under one arm only is recorded as a difference on BOTH sides -- vanished and
    appeared -- so a renamed key counts twice and cannot read as a single move.

    `held_paths` are the arm-relative addresses the manifest declared. They are used
    only to keep the outside report honest: a leaf the manifest already measures is not
    repeated in the list of differences the manifest did not mention.
    """
    left = dict(leaves(container[left_name]))
    right = dict(leaves(container[right_name]))
    shared = sorted(set(left) & set(right))
    only_left = sorted(set(left) - set(right))
    only_right = sorted(set(right) - set(left))

    rows = []
    for path in shared:
        if same_value(left[path], right[path]):
            continue
        rows.append({
            "path": path, "kind": "differs",
            "left": _plain(left[path]), "right": _plain(right[path]),
            "relative_gap": relative_gap(left[path], right[path]),
        })
    for path in only_left:
        rows.append({"path": path, "kind": "only_under_" + left_name,
                     "left": _plain(left[path]), "right": None,
                     "relative_gap": None})
    for path in only_right:
        rows.append({"path": path, "kind": "only_under_" + right_name,
                     "left": None, "right": _plain(right[path]),
                     "relative_gap": None})

    declared = set(held_paths)
    outside = [row for row in rows if row["path"] not in declared]
    return {
        "n_leaves_under_both": len(shared),
        "n_leaves_under_one_arm_only": len(only_left) + len(only_right),
        "n_differing_leaves": len(rows),
        "n_outside_the_manifest": len(outside),
        "outside_by_block": _by_block(outside),
        "outside": outside[:OUTSIDE_KEPT_PER_PAIR],
        "n_outside_kept": min(len(outside), OUTSIDE_KEPT_PER_PAIR),
    }


def _plain(value):
    """A leaf as JSON can hold it. NaN and infinity become their spelling."""
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return "NaN" if math.isnan(value) else ("Infinity" if value > 0
                                                else "-Infinity")
    return value


def _by_block(rows):
    """Differences outside the manifest, counted by their top path segment.

    A pair here can hold four hundred differing leaves and a list of them is not a
    report anybody reads. The block tally says the useful thing: how many are the cost
    surface, which is the outcome, and how many sit somewhere the axis does not explain.
    """
    tally = {}
    for row in rows:
        block = row["path"].split(".")[0]
        tally[block] = tally.get(block, 0) + 1
    return dict(sorted(tally.items(), key=lambda kv: (-kv[1], kv[0])))


# =====================================================================
# THE SWEEP: EVERY PAIR OF EVERY DECLARED CONTAINER, INTO ONE OF THREE STATES
# =====================================================================

def resolve_containers(document, dotted):
    """Every mapping the dotted path reaches, as {path: mapping}.

    A "*" segment expands to every key at that level, which is what lets one declaration
    cover the two horizon containers of the bake-off. An unresolvable path returns
    nothing and the caller fails the run over it: a container nobody found is not a
    container whose arms agreed.
    """
    found = {"": document}
    for segment in dotted.split("."):
        step = {}
        for path, node in found.items():
            if not isinstance(node, dict):
                continue
            keys = list(node) if segment == "*" else (
                [segment] if segment in node else [])
            for key in keys:
                step[f"{path}.{key}" if path else key] = node[key]
        found = step
        if not found:
            return {}
    return {path: node for path, node in found.items() if isinstance(node, dict)}


def pair_id(declaration, container_path, left, right):
    """The stable name of one contrast, as --pair takes it and the debt list holds it."""
    left, right = sorted((left, right))
    return f"{declaration['id']} {container_path} {left} vs {right}"


def _classify(key, left, right, published, withheld, ranking_only, grounds):
    """Which of the three states one pair is in, and on what grounds. No measuring."""
    if key in published:
        return COMPARISON, published[key]["axis"]
    if key in withheld:
        return NOT_A_COMPARISON, withheld[key]["why_not_published"]
    if left in ranking_only and right in ranking_only:
        return NOT_A_COMPARISON, grounds
    return UNDECLARED, None


def sweep(root, declarations):
    """Judge every pair of every declared container. Returns (pairs, unresolved).

    `unresolved` is kept apart from a pair that came out clean, and that separation is
    this gate's direction of failure written into its data structure: a declaration
    naming an artifact, a container or an arm that is not there produced no comparison
    at all, and a comparison that did not happen must never be counted with the ones
    that agreed.
    """
    pairs, unresolved = [], []
    for declaration in declarations:
        rel = declaration["artifact"]
        path = os.path.join(root, rel)
        try:
            with open(path, encoding="utf-8") as handle:
                document = json.load(handle)
        except (OSError, ValueError) as exc:
            unresolved.append({
                "declaration": declaration["id"], "what": "the artifact",
                "expected": rel, "found": str(exc)[:160], "place": rel})
            continue

        published, withheld, manifests_found = published_manifests(
            document, declaration)
        if not manifests_found:
            unresolved.append({
                "declaration": declaration["id"],
                "what": "the producer's own manifest block",
                "expected": f"{declaration['manifests_at']} to hold the axis and the "
                            f"held-equal list of every published difference",
                "found": "the address reaches nothing, so this gate has no declaration "
                         "to check against and cannot tell a claim from a non-claim",
                "place": f"{rel} -> {declaration['manifests_at']}"})

        grounds_found, grounds = dig(document, declaration["grounds_at"])
        if not (grounds_found and isinstance(grounds, str) and grounds.strip()):
            unresolved.append({
                "declaration": declaration["id"],
                "what": "the grounds for the middle state",
                "expected": f"{declaration['grounds_at']} to carry the producer's own "
                            f"sentence on why a ranking does not make two arms "
                            f"comparable",
                "found": "the address reaches nothing or an empty value",
                "place": f"{rel} -> {declaration['grounds_at']}"})
            grounds = None

        containers = resolve_containers(document, declaration["arms_under"])
        if not containers:
            unresolved.append({
                "declaration": declaration["id"], "what": "the arm container",
                "expected": f"{declaration['arms_under']} to reach at least one "
                            f"mapping inside {rel}",
                "found": "the path reaches nothing",
                "place": f"{rel} -> {declaration['arms_under']}"})
            continue

        ranking_only = set(declaration["ranking_only_arms"])
        in_a_manifest = {arm for key in list(published) + list(withheld)
                         for arm in key}
        declared_arms = ranking_only | in_a_manifest

        for container_path, container in sorted(containers.items()):
            arms = [key for key in sorted(container)
                    if isinstance(container[key], dict)]
            # An arm that is there but is not a mapping. Left alone it walks to one
            # nameless leaf and compares clean against another one, handing back the
            # result of a comparison that never happened.
            for key in sorted(container):
                if not isinstance(container[key], dict) and key in declared_arms:
                    unresolved.append({
                        "declaration": declaration["id"],
                        "what": "a declared arm that is not a mapping",
                        "expected": f"{container_path}.{key} to be an object whose "
                                    f"leaves can be walked",
                        "found": f"a {type(container[key]).__name__}: "
                                 f"{str(container[key])[:60]}",
                        "place": f"{rel} -> {container_path} -> {key}"})
            # AN ABSENT ARM HAS TWO CAUSES AND THEY ARE NOT THE SAME FAULT. Both fail,
            # and neither is softened; what differs is what a reader should go and do,
            # and one message for both sends them to the wrong place. Measured on
            # 2026-08-05: the hand-written list was extended to eleven arms while the
            # artifact still held the nine of a producer run that had not landed, and
            # the single message read as a broken artifact when nothing was broken.
            #
            #   a MANIFEST names it     the artifact publishes a difference about an
            #                           arm the container it points at does not hold.
            #                           One producer run wrote both, so this cannot be
            #                           a timing artifact: the artifact contradicts
            #                           itself and the figure rests on nothing
            #   only the LIST names it  the hand-written declaration and the artifact
            #                           are out of step. They live in different files
            #                           and are written by different hands -- a person
            #                           and a run -- so either the arm was dropped from
            #                           the producer, or this list is ahead of a run
            #                           that has not finished
            for arm in sorted(declared_arms):
                if arm in container:
                    continue
                named_by_manifest = arm in in_a_manifest
                unresolved.append({
                    "declaration": declaration["id"],
                    "what": ("an arm a manifest names" if named_by_manifest
                             else "an arm only the hand-written list names"),
                    "expected": f"{arm} among the keys of {container_path}",
                    "found": "present: " + ", ".join(arms),
                    "place": f"{rel} -> {container_path}",
                    "means": (
                        "a manifest publishes a difference about this arm and the "
                        "container does not hold it. The same producer run wrote the "
                        "manifest and the container, so the artifact contradicts "
                        "itself and the published difference rests on nothing"
                        if named_by_manifest else
                        "the ranking-only list and the artifact are out of step. "
                        "Either the arm was dropped from the producer and the line "
                        "should come out of the list, or the list is ahead of a "
                        "producer run that has not landed yet, in which case this "
                        "clears itself when the run writes the artifact")})

            for left, right in itertools.combinations(arms, 2):
                key = frozenset((left, right))
                state, grounds_text = _classify(
                    key, left, right, published, withheld, ranking_only, grounds)
                row = {
                    "id": pair_id(declaration, container_path, left, right),
                    "declaration": declaration["id"], "artifact": rel,
                    "container": container_path, "left": left, "right": right,
                    "state": state, "grounds": grounds_text,
                    # WHICH ARM BLOCKS THE MIDDLE STATE, WHICH IS NOT THE SAME AS
                    # WHICH ARM IS UNKNOWN. An arm can be arm_a of one published
                    # manifest and still leave every OTHER pair it forms undeclared,
                    # because the middle state needs BOTH arms in the ranking-only
                    # list. Naming arms absent from `declared_arms` printed an empty
                    # list in exactly that case -- a failure that named no place, which
                    # is the one thing a red run may not do.
                    "arms_not_in_the_ranking_only_list": sorted(
                        arm for arm in (left, right) if arm not in ranking_only),
                }
                if state is COMPARISON:
                    manifest = published[key]
                    reachable, unreachable = held_equal_specs(
                        manifest, declaration["arm_relative_prefix"])
                    measured = measure_held_equal(container, left, right, reachable)
                    # The unreachable rows are re-checked on the numbers the producer
                    # recorded. Weaker than a leaf walk by one thing and it says so on
                    # every row -- a wrong fetch is invisible, a wrong comparison is
                    # not -- and it is strictly more than believing `holds`, which is
                    # what happened to these rows before 2026-08-05.
                    rechecked = recheck_recorded(unreachable)
                    judged = measured + rechecked
                    # The count is of RECORDED VALUES THAT AGREE, and it claims only
                    # that. An earlier spelling called such a row a tautology on the
                    # ground that one address had been read for both arms; that infers
                    # structure from a coincidence of values, and it was wrong on this
                    # tree within minutes, which recheck_recorded records at length. So
                    # the test is the one the field name makes: are the two numbers the
                    # producer wrote down the same number.
                    tautologies = [
                        item for item in rechecked
                        if same_value(item.get("recorded_left"),
                                      item.get("recorded_right"))]
                    breaches = [item for item in judged if not item["holds"]]
                    disagreements = [
                        item for item in judged
                        if isinstance(item["producer_says_holds"], bool)
                        and item["producer_says_holds"] != item["holds"]]
                    row.update({
                        "manifest": manifest["manifest"],
                        "arm_a_of_the_manifest": manifest["arm_a"],
                        "arm_b_of_the_manifest": manifest["arm_b"],
                        "axis": manifest["axis"],
                        "consequence_of_the_axis":
                            manifest["consequence_of_the_axis"],
                        "manifest_not_held_equal": manifest["not_held_equal"],
                        "producer_says_all_hold": manifest["producer_says_all_hold"],
                        "held_equal_remeasured": measured,
                        "held_equal_rechecked_from_recorded_values": rechecked,
                        "n_held_equal_declared": len(reachable) + len(unreachable),
                        "n_held_equal_remeasured": len(measured),
                        "n_held_equal_rechecked": len(rechecked),
                        "how_each_was_judged": {
                            "re-measured from the leaves of both arms":
                                len(measured),
                            "re-compared from the values the producer recorded, "
                            "because the address is not relative to an arm":
                                len(rechecked),
                            "taken on the producer's word": 0,
                        },
                        "n_breaches": len(breaches),
                        "breaches": breaches,
                        "n_disagreements_with_the_producer": len(disagreements),
                        "disagreements_with_the_producer": disagreements,
                    })
                    row.update(compare_arms(
                        container, left, right,
                        [item["arm_relative_path"] for item in reachable]))
                else:
                    # The other two states are not measured against a list, because
                    # there is none. The leaf count is still taken: it costs nothing
                    # and it is what lets a reader see that a pair the work makes no
                    # claim about does differ, without that being a finding.
                    row["n_breaches"] = 0
                    counts = compare_arms(container, left, right)
                    row.update({name: counts[name] for name in (
                        "n_leaves_under_both", "n_leaves_under_one_arm_only",
                        "n_differing_leaves", "outside_by_block")})
                pairs.append(row)
    return pairs, unresolved


def against_the_debt(breached, declared):
    """The frozen debt as a set difference, both ways.

    Returns (outside, repaid). `outside` is the regression this gate fails on; `repaid`
    is a frozen pair that no longer breaches, printed so whoever equalised the arms can
    shorten the list.

    A FUNCTION RATHER THAN TWO COMPREHENSIONS INSIDE main(), because this is where the
    number that decides the exit code is made and it reads 0 on this tree. A count that
    goes into a decision has to be shown capable of finding something, and a predicate
    buried in main() cannot be asserted on the case where it must fire.
    """
    outside = sorted(name for name in breached if name not in declared)
    repaid = sorted(name for name in declared if name not in breached)
    return outside, repaid


# =====================================================================
# CALIBRATION: FOUR CASES, TWO COMPARATORS, EACH WITH ONE OF EITHER KIND
# =====================================================================

def _fixture_arm(width, n, extra=None, note=None):
    arm = {"width": {"pooled": {"mean_bps": width, "frac": 1.0 if width else 0.0}},
           "population": {"n": n},
           "outcome": {"cost_bps": -3.0 - width}}
    if extra is not None:
        arm["outcome"]["ci"] = extra
    if note is not None:
        arm["note"] = note
    return arm


def _fixture_document(arms, manifests, deltas, grounds="a fixture's grounds"):
    return {"quoters": {"T": arms},
            "declared_axis_comparisons": {
                "why": grounds, "manifests": manifests, "deltas": deltas}}


def _fixture_manifest(arm_a, arm_b, quantities):
    return {"arm_a": arm_a, "arm_b": arm_b, "axis": "a fixture's axis",
            "consequence_of_the_axis": "a fixture's consequence",
            "not_held_equal": [], "all_held_equal_quantities_hold": True,
            "refusal": None, "held_equal_measured": quantities}


def _fixture_declaration(**overrides):
    row = {"id": "fixture", "artifact": "fixture_results.json",
           "arms_under": "quoters.*",
           "manifests_at": "declared_axis_comparisons.manifests",
           "deltas_at": "declared_axis_comparisons.deltas",
           "grounds_at": "declared_axis_comparisons.why",
           "arm_relative_prefix": "quoters.<K>.<arm>.",
           "ranking_only_arms": ("a", "b"),
           "ranking_only_reason": "a fixture's decision",
           "ranking_only_decided": "2026-08-03"}
    row.update(overrides)
    return row


def _write(work, document):
    with open(os.path.join(work, "fixture_results.json"), "w",
              encoding="utf-8") as handle:
        json.dump(document, handle)


def _self_test_leaf_comparator(expect):
    """The leaf walk, one fixture per decision it makes. None of these can decay."""
    nan = float("nan")

    container = {"a": _fixture_arm(0.0, 100), "b": _fixture_arm(0.0, 100)}
    container["b"]["outcome"]["cost_bps"] = -2.5
    row = compare_arms(container, "a", "b")
    expect("two arms differing in one leaf report one difference",
           row["n_differing_leaves"] == 1, f"{row['n_differing_leaves']}")

    container = {"a": _fixture_arm(0.0, 100, note="only here"),
                 "b": _fixture_arm(0.0, 100)}
    container["b"]["remark"] = "only here"
    row = compare_arms(container, "a", "b")
    expect("a renamed key counts as two differences, not one",
           row["n_leaves_under_one_arm_only"] == 2
           and row["n_differing_leaves"] == 2,
           f"{row['n_leaves_under_one_arm_only']} one-sided, "
           f"{row['n_differing_leaves']} differing")

    container = {"a": _fixture_arm(0.0, 100, extra=nan),
                 "b": _fixture_arm(0.0, 100, extra=nan)}
    row = compare_arms(container, "a", "b")
    expect("NaN equals NaN, or a silent pair manufactures 72 differences",
           row["n_differing_leaves"] == 0, f"{row['n_differing_leaves']}")
    container["b"]["outcome"]["ci"] = 1.0
    row = compare_arms(container, "a", "b")
    expect("NaN against a number is still a difference",
           row["n_differing_leaves"] == 1, f"{row['n_differing_leaves']}")

    expect("True is not 1, which Python's own comparison gets wrong",
           not same_value(1, True) and not same_value(True, 1),
           "bare == would call them equal")

    for path, pattern, want in (
            ("width.pooled.mean_bps", "width.**", True),
            ("width", "width.**", True),
            ("net.BTC.n_fills", "net.*.n_fills", True),
            ("net.BTC.deep.n_fills", "net.*.n_fills", False),
            ("outcome.cost_bps", "width.**", False),
            ("width.pooled.[0]", "width.*.*", True)):
        expect(f"pattern {pattern!r} against {path!r} is {want}",
               matches_pattern(path, pattern) is want,
               f"got {matches_pattern(path, pattern)}")

    expect("an absent address is told apart from an address holding null",
           dig({"a": None}, "a") == (True, None) and dig({}, "a") == (False, None),
           "otherwise an unreachable held-equal quantity reads as one that agreed")


def _self_test_coverage(expect):
    """THE THREE STATES. One case that must fire, one that must stay silent.

    Both injected. Every arm of the live tree is in a state today, so a firing case
    taken from it would empty the moment somebody declared the arm -- which is how a
    calibration case of this project emptied on 2026-08-03, leaving an instrument that
    was red while checking nothing.
    """
    with tempfile.TemporaryDirectory() as work:
        quantity = {"quantity": "width", "rtol": 0.0,
                    "measured_by": "quoters.<K>.<arm>.width.pooled.mean_bps",
                    "holds": True}
        arms = {"a": _fixture_arm(1.0, 100), "b": _fixture_arm(1.0, 100),
                "c": _fixture_arm(2.0, 100)}
        manifests = {"a_minus_b": _fixture_manifest("a", "b", [quantity])}
        deltas = {"a_minus_b": {"published": True}}

        # MUST FIRE. `c` is in no manifest and in no ranking-only list.
        _write(work, _fixture_document(arms, manifests, deltas))
        pairs, unresolved = sweep(work, [_fixture_declaration()])
        by_state = {state: [p for p in pairs if p["state"] == state]
                    for state in STATES}
        expect("an arm in no manifest and no ranking-only list is NOT DECLARED",
               len(by_state[UNDECLARED]) == 2
               and all("c" in p["arms_not_in_the_ranking_only_list"] for p in by_state[UNDECLARED]),
               f"{len(by_state[UNDECLARED])} undeclared pair(s), each naming the arm")
        expect("and the pair the manifest publishes is a COMPARISON",
               len(by_state[COMPARISON]) == 1, f"{len(by_state[COMPARISON])}")
        expect("and the three states partition the pairs, losing none",
               len(pairs) == 3 and sum(len(v) for v in by_state.values()) == 3,
               f"{len(pairs)} pairs over {len(by_state[COMPARISON])}/"
               f"{len(by_state[NOT_A_COMPARISON])}/{len(by_state[UNDECLARED])}")

        # MUST STAY SILENT. The same tree with `c` named in the ranking-only list.
        pairs, unresolved = sweep(
            work, [_fixture_declaration(ranking_only_arms=("a", "b", "c"))])
        by_state = {state: [p for p in pairs if p["state"] == state]
                    for state in STATES}
        expect("declaring that arm ranking-only moves its pairs to the middle state, "
               "not to silence",
               not by_state[UNDECLARED] and len(by_state[NOT_A_COMPARISON]) == 2
               and not unresolved,
               f"{len(by_state[UNDECLARED])} undeclared, "
               f"{len(by_state[NOT_A_COMPARISON])} not-a-comparison")
        expect("a middle-state pair carries the producer's grounds, read from the "
               "artifact and not restated here",
               all(p["grounds"] == "a fixture's grounds"
                   for p in by_state[NOT_A_COMPARISON]),
               "changing the artifact's sentence changes what this gate prints")
        expect("a middle-state pair is still counted, so a reader sees it differs "
               "without that being a finding",
               all(p["n_differing_leaves"] > 0 and p["n_breaches"] == 0
                   for p in by_state[NOT_A_COMPARISON]),
               f"{[p['n_differing_leaves'] for p in by_state[NOT_A_COMPARISON]]} "
               f"differing leaves, 0 breaches")

        # AN ARM IN A MANIFEST IS NOT THEREBY COVERED FOR ITS OTHER PAIRS, AND THE
        # FAILURE MUST NAME IT. Found by running the firing case end to end on
        # 2026-08-03: the gate went red over 14 pairs and printed an empty list where
        # the arm should have been, because it named arms absent from every state while
        # the arm was arm_a of a published manifest. A red run that names no place is
        # the one thing a red run may not be.
        _write(work, _fixture_document(arms, manifests, deltas))
        pairs, _u = sweep(work, [_fixture_declaration(ranking_only_arms=("b", "c"))])
        by_state = {state: [p for p in pairs if p["state"] == state]
                    for state in STATES}
        undeclared = by_state[UNDECLARED]
        expect("an arm published in one manifest still leaves its OTHER pairs "
               "undeclared",
               len(undeclared) == 1 and {undeclared[0]["left"],
                                         undeclared[0]["right"]} == {"a", "c"},
               f"{len(undeclared)} undeclared, "
               f"{len(by_state[COMPARISON])} comparison, "
               f"{len(by_state[NOT_A_COMPARISON])} not-a-comparison")
        expect("and the failure names the arm that blocks the middle state",
               undeclared[0]["arms_not_in_the_ranking_only_list"] == ["a"],
               f"named {undeclared[0]['arms_not_in_the_ranking_only_list']}; the "
               f"earlier predicate named arms in NO state and printed nothing here")

        # A manifest the producer REFUSED is a non-claim, not a claim to be checked.
        refused = {"a_minus_b": dict(_fixture_manifest("a", "b", [quantity]),
                                     refusal="the solve did not land")}
        _write(work, _fixture_document(arms, refused, deltas))
        pairs, _u = sweep(
            work, [_fixture_declaration(ranking_only_arms=("a", "b", "c"))])
        row = next(p for p in pairs if {p["left"], p["right"]} == {"a", "b"})
        expect("a manifest the producer refused is a non-claim, not a comparison",
               row["state"] == NOT_A_COMPARISON
               and "refusal" in (row["grounds"] or ""),
               f"state {row['state']}")

        # The grounds address going missing is a finding: the middle state would rest
        # on nothing, and this gate must not supply the reason itself.
        document = _fixture_document(arms, manifests, deltas)
        del document["declared_axis_comparisons"]["why"]
        _write(work, document)
        _p, unresolved = sweep(
            work, [_fixture_declaration(ranking_only_arms=("a", "b", "c"))])
        expect("the grounds address going missing is reported, not filled in",
               any(row["what"] == "the grounds for the middle state"
                   for row in unresolved),
               f"unresolved: {[row['what'] for row in unresolved]}")

        # AN ABSENT ARM, BOTH CAUSES, TOLD APART. Both fail; they send a reader to
        # different places, and one message for both sent a reader looking for a broken
        # artifact on 2026-08-05 when the truth was a producer run still running.
        _write(work, _fixture_document(arms, manifests, deltas))
        _p, unresolved = sweep(work, [_fixture_declaration(
            ranking_only_arms=("a", "b", "c", "an_arm_that_is_not_there"))])
        listed = [row for row in unresolved
                  if row["what"] == "an arm only the hand-written list names"]
        expect("an arm only the hand-written list names, absent, fails and says the "
               "list may be ahead of a run",
               len(listed) == 1 and "has not landed" in listed[0]["means"],
               f"unresolved: {[row['what'] for row in unresolved]}")

        # The same absence, but the arm is named by a MANIFEST. Same failure, different
        # cause: one producer run wrote both the manifest and the container.
        ahead = {"a_minus_ghost": _fixture_manifest("a", "a_ghost_arm", [quantity])}
        _write(work, _fixture_document(
            arms, ahead, {"a_minus_ghost": {"published": True}}))
        _p, unresolved = sweep(work, [_fixture_declaration(
            ranking_only_arms=("a", "b", "c"))])
        by_manifest = [row for row in unresolved
                       if row["what"] == "an arm a manifest names"]
        expect("an arm a manifest names, absent, fails as an artifact that "
               "contradicts itself",
               len(by_manifest) == 1
               and "contradicts itself" in by_manifest[0]["means"]
               and not any(row["what"] == "an arm only the hand-written list names"
                           for row in unresolved),
               f"unresolved: {[row['what'] for row in unresolved]}")
        broken = dict(arms, c="not an arm at all")
        _write(work, _fixture_document(broken, manifests, deltas))
        pairs, unresolved = sweep(
            work, [_fixture_declaration(ranking_only_arms=("a", "b", "c"))])
        expect("a declared arm that is not a mapping fails instead of comparing",
               any(row["what"] == "a declared arm that is not a mapping"
                   for row in unresolved)
               and not any("c" in (p["left"], p["right"]) for p in pairs),
               f"{len(pairs)} pair(s) judged, unresolved: "
               f"{[row['what'] for row in unresolved]}")


def _self_test_held_equal(expect):
    """THE HELD-EQUAL LIST. One case that must fire, one that must stay silent.

    Injected, and the pair also calibrates the TOLERANCE, which one case cannot: the
    same gap must breach at rtol 0 and hold at rtol 1e-9.
    """
    with tempfile.TemporaryDirectory() as work:
        address = "quoters.<K>.<arm>.width.pooled.mean_bps"
        deltas = {"a_minus_b": {"published": True}}
        at_rtol_zero = {"a_minus_b": _fixture_manifest("a", "b", [
            {"quantity": "width", "rtol": 0.0, "measured_by": address,
             "holds": True}])}

        # MUST FIRE. The declared address carries 1.0 against 4.0 at rtol 0.
        arms = {"a": _fixture_arm(1.0, 100), "b": _fixture_arm(4.0, 100)}
        _write(work, _fixture_document(arms, at_rtol_zero, deltas))
        pairs, _u = sweep(work, [_fixture_declaration()])
        row = pairs[0]
        expect("a moved held-equal address is a breach",
               row["n_breaches"] == 1
               and row["breaches"][0]["measured_gap"] == 0.75,
               f"{row['n_breaches']} breach(es), gap "
               f"{row['breaches'][0]['measured_gap'] if row['breaches'] else None}")
        expect("the breach carries both values, the gap and the declared tolerance",
               row["breaches"][0]["left"] == 1.0
               and row["breaches"][0]["right"] == 4.0
               and row["breaches"][0]["rtol"] == 0.0,
               f"{row['breaches'][0]['left']} against "
               f"{row['breaches'][0]['right']}, rtol {row['breaches'][0]['rtol']}")
        expect("and the producer's own `holds: true` is contradicted, not believed",
               row["n_disagreements_with_the_producer"] == 1,
               "a gate reading that field would check that the producer can write a "
               "True")

        # MUST STAY SILENT. The same address agreeing, while the outcome differs.
        arms = {"a": _fixture_arm(1.0, 100), "b": _fixture_arm(1.0, 100)}
        arms["b"]["outcome"]["cost_bps"] = -2.0
        _write(work, _fixture_document(arms, at_rtol_zero, deltas))
        pairs, _u = sweep(work, [_fixture_declaration()])
        row = pairs[0]
        expect("an unmoved held-equal address is silent while the outcome differs",
               row["n_breaches"] == 0 and row["n_outside_the_manifest"] > 0,
               f"{row['n_breaches']} breach(es), "
               f"{row['n_outside_the_manifest']} differences outside the manifest")
        expect("and the leaf the manifest measures is not repeated outside it",
               all(item["path"] != "width.pooled.mean_bps"
                   for item in row["outside"]),
               f"outside: {[item['path'] for item in row['outside']][:3]}")

        # THE TOLERANCE, BOTH WAYS, ON ONE GAP. Live evidence that it is needed: a
        # published difference of this tree lands at 2.9e-16 against a declared 1e-09.
        arms = {"a": _fixture_arm(1.0, 100), "b": _fixture_arm(1.0 + 1e-15, 100)}
        for rtol, want_breach in ((0.0, True), (1e-9, False)):
            manifests = {"a_minus_b": _fixture_manifest("a", "b", [
                {"quantity": "width", "rtol": rtol, "measured_by": address,
                 "holds": True}])}
            _write(work, _fixture_document(arms, manifests, deltas))
            pairs, _u = sweep(work, [_fixture_declaration()])
            expect(f"a gap of 1e-15 {'breaches' if want_breach else 'holds'} at "
                   f"rtol {rtol:.0e}",
                   bool(pairs[0]["n_breaches"]) is want_breach,
                   f"{pairs[0]['n_breaches']} breach(es)")

        # A declared address not under both arms leaves the quantity UNVERIFIED, which
        # must not read as verified.
        manifests = {"a_minus_b": _fixture_manifest("a", "b", [
            {"quantity": "width", "rtol": 0.0, "holds": True,
             "measured_by": "quoters.<K>.<arm>.width.pooled.a_missing_leaf"}])}
        _write(work, _fixture_document(arms, manifests, deltas))
        pairs, _u = sweep(work, [_fixture_declaration()])
        expect("a held-equal address that is not under the arms is a breach, not a "
               "pass",
               pairs[0]["n_breaches"] == 1
               and not pairs[0]["breaches"][0]["found_under_left"],
               f"{pairs[0]['n_breaches']} breach(es)")

        # A held-equal quantity whose address is not arm-relative is NAMED, not counted
        # as checked: six declared and three measured must never read as six measured.
        manifests = {"a_minus_b": _fixture_manifest("a", "b", [
            {"quantity": "width", "rtol": 0.0, "measured_by": address,
             "holds": True},
            {"quantity": "a_setting", "rtol": 0.0, "holds": True,
             "measured_by": "RECOVER_FRAC, applied by the same line to both arms",
             "arm_a": 0.5, "arm_b": 0.5}])}
        _write(work, _fixture_document(arms, manifests, deltas))
        pairs, _u = sweep(work, [_fixture_declaration()])
        row = pairs[0]
        expect("a held-equal quantity this gate cannot reach is counted apart from "
               "one it re-measures",
               row["n_held_equal_declared"] == 2
               and row["n_held_equal_remeasured"] == 1
               and row["n_held_equal_rechecked"] == 1,
               f"{row['n_held_equal_declared']} declared, "
               f"{row['n_held_equal_remeasured']} re-measured, "
               f"{row['n_held_equal_rechecked']} re-compared")
        expect("and nothing is taken on the producer's word",
               row["how_each_was_judged"]["taken on the producer's word"] == 0
               and sum(row["how_each_was_judged"].values())
               == row["n_held_equal_declared"],
               f"{row['how_each_was_judged']}")

        # AN UNREACHABLE ROW IS NOT AN UNCHECKED ROW. Two opposite cases on the one
        # thing this gate CAN still do with it: re-compare the numbers the producer
        # recorded. Before 2026-08-05 these rows were believed, which is the same
        # summary field this gate refuses on every other row.
        recheck = {"quantity": "a_setting", "rtol": 0.0, "holds": True,
                   "measured_by": "RECOVER_FRAC, one line for both arms"}
        for a, b, want_breach, what in (
                (0.5, 0.5, False, "agreeing recorded values stay silent"),
                (0.5, 0.4, True, "recorded values that differ under a `holds` of true "
                                 "are a breach"),
                (0.5, float("nan"), True, "a not-a-number recorded for a quantity "
                                          "declared held equal establishes nothing")):
            manifests = {"a_minus_b": _fixture_manifest("a", "b", [
                dict(recheck, arm_a=a, arm_b=b)])}
            _write(work, _fixture_document(arms, manifests, deltas))
            pairs, _u = sweep(work, [_fixture_declaration()])
            expect(what, bool(pairs[0]["n_breaches"]) is want_breach,
                   f"recorded {a} against {b}: {pairs[0]['n_breaches']} breach(es)")
        expect("and contradicting the producer on such a row is reported as a "
               "disagreement too",
               pairs[0]["n_disagreements_with_the_producer"] == 1,
               "the row said holds: true and its own two numbers do not agree")

        # THE MARK THAT WAS REMOVED, AND WHY THERE IS NO CASE FOR IT. An earlier
        # version marked a row whose two recorded values agree as "one address read for
        # both arms, so it cannot differ" -- structure inferred from a coincidence of
        # values. It was wrong on the live tree at once: the classifier manifests read
        # two genuinely different addresses that agree at 2069 today, and the mark said
        # that row could never differ when it is the one row here with something to
        # say. What replaces it is an assertion that the gate makes NO such claim.
        manifests = {"a_minus_b": _fixture_manifest("a", "b", [
            dict(recheck, arm_a=2069.0, arm_b=2069.0)])}
        _write(work, _fixture_document(arms, manifests, deltas))
        pairs, _u = sweep(work, [_fixture_declaration()])
        got = pairs[0]["held_equal_rechecked_from_recorded_values"][0]
        expect("two agreeing recorded values carry no claim about how many addresses "
               "were read",
               "one address" not in json.dumps(got).replace(
                   got["addresses_not_established"], ""),
               "the row says the values agree and that it did not fetch them, and "
               "stops there")

        # The manifest block going missing leaves the gate with nothing to check
        # against, which is a finding and not an empty clean sweep.
        document = _fixture_document(arms, manifests, deltas)
        del document["declared_axis_comparisons"]["manifests"]
        _write(work, document)
        _p, unresolved = sweep(work, [_fixture_declaration()])
        expect("the manifest block going missing is reported, not read as no claims",
               any(row["what"] == "the producer's own manifest block"
                   for row in unresolved),
               f"unresolved: {[row['what'] for row in unresolved]}")

    # A declaration naming a missing artifact produces no comparison, and the sweep
    # must say so rather than return an empty clean list.
    pairs, unresolved = sweep(ROOT, [_fixture_declaration()])
    expect("a declaration naming a missing artifact is unresolved, not clean",
           not pairs and any(row["what"] == "the artifact" for row in unresolved),
           f"{len(pairs)} pairs, {len(unresolved)} unresolved")

    # The two legs whose zero decides the exit code, shown able to find something.
    outside, repaid = against_the_debt(
        ["fixture pair one", "fixture pair two"], ("fixture pair one",))
    expect("a breach outside the frozen debt is found by the set difference",
           outside == ["fixture pair two"] and repaid == [],
           f"outside={outside}, repaid={repaid}")
    outside, repaid = against_the_debt([], ("fixture pair one",))
    expect("a frozen pair that stopped breaching is reported as repaid",
           outside == [] and repaid == ["fixture pair one"],
           f"outside={outside}, repaid={repaid}")


def _self_test_live(pairs, expect, unanswered):
    """The two live cases, one per comparator, both of them the SILENT half.

    A live silent case decays in the safe direction: it going noisy is the gate catching
    something. The firing halves are injected above, because a live firing case empties
    the day the defect is repaired.
    """
    coverage = decl.CALIBRATION_COVERAGE_MUST_STAY_SILENT
    wanted = f"{coverage['declaration']} {coverage['container']} " \
             f"{' vs '.join(sorted((coverage['left'], coverage['right'])))}"
    row = next((p for p in pairs if p["id"] == wanted), None)
    if row is None:
        unanswered.append({
            "case": wanted, "expected": coverage["why"],
            "found": "the pair is not in the sweep at all",
            "place": f"{coverage['declaration']} -> {coverage['container']}",
            "means": "the case was taken from the tree on 2026-08-03 and the sweep no "
                     "longer reaches it; pick another and name it in "
                     "contrast_declarations.py"})
    elif row["state"] != coverage["expect_state"]:
        unanswered.append({
            "case": wanted,
            "expected": f"state {coverage['expect_state']}. {coverage['why']}",
            "found": f"state {row['state']}",
            "place": f"{row['artifact']} -> {row['container']}",
            "means": "a pair the work made no claim about has changed state. If a "
                     "difference is now published for it that is the work moving on "
                     "and a new case must be named; if it went undeclared, an arm left "
                     "the ranking-only list"})
    else:
        expect(f"{wanted} -> {row['state']}, as calibrated", True,
               f"{row['n_differing_leaves']} of its {row['n_leaves_under_both']} "
               f"shared leaves differ, and none of that is a finding")
        expect(f"{wanted} -> its grounds are the producer's own",
               bool(row["grounds"]),
               f"read this run from {decl.QUOTER_BAKEOFF['grounds_at']}")

    held = decl.CALIBRATION_HELD_EQUAL_MUST_STAY_SILENT
    wanted = f"{held['declaration']} {held['container']} " \
             f"{' vs '.join(sorted((held['left'], held['right'])))}"
    row = next((p for p in pairs if p["id"] == wanted), None)
    if row is None or row["state"] != COMPARISON:
        unanswered.append({
            "case": wanted,
            "expected": f"a published difference with {held['expect_breaches']} "
                        f"breach(es). {held['why']}",
            "found": "not in the sweep" if row is None else f"state {row['state']}",
            "place": f"{held['declaration']} -> {held['container']}",
            "means": "the difference this gate was calibrated on is no longer "
                     "published; name another published difference here"})
    elif row["n_breaches"] != held["expect_breaches"]:
        unanswered.append({
            "case": wanted,
            "expected": f"{held['expect_breaches']} breach(es), measured 2026-08-03. "
                        f"{held['why']}",
            "found": f"{row['n_breaches']} breach(es): "
                     + ", ".join(str(item["quantity"]) for item in row["breaches"]),
            "place": f"{row['artifact']} -> {row['container']}",
            "means": "a published difference has stopped holding what it declares, "
                     "which is this gate finding something rather than this gate being "
                     "wrong"})
    else:
        expect(f"{wanted} -> {row['n_breaches']} breach(es), as calibrated", True,
               f"{row['n_held_equal_remeasured']} of {row['n_held_equal_declared']} "
               f"declared quantities re-measured on the leaves, "
               f"{row['n_held_equal_rechecked']} re-compared from the recorded values")
        expect(f"{wanted} -> re-measured rather than read, and it agrees",
               row["n_disagreements_with_the_producer"] == 0
               and row["n_held_equal_remeasured"]
               == held["expect_held_equal_addresses"],
               f"{row['n_held_equal_remeasured']} address(es) walked against the "
               f"{held['expect_held_equal_addresses']} calibrated")
        expect(f"{wanted} -> silence here is not an empty comparison",
               row["n_outside_the_manifest"] > 0,
               f"{row['n_outside_the_manifest']} leaves differ outside what the "
               f"manifest measures {row['outside_by_block']}")


def calibrate(pairs):
    """All four cases plus the leaf comparator. Returns (failures, asserted, open)."""
    failures, unanswered, asserted = [], [], []
    # The printing assertion comes from evidence.py, where chk_input_freshness.py reads
    # the same one. It is a factory rather than a plain function because it writes into
    # this scope's two lists and is then handed on to the four calibration routines
    # below, which is the shape those routines already expected.
    expect = make_expect(asserted, failures)

    print("-" * 78)
    print("  CALIBRATION 1: the leaf comparator, one fixture per decision")
    _self_test_leaf_comparator(expect)
    print()
    print("  CALIBRATION 2: the three states, one case that fires and one that does not")
    _self_test_coverage(expect)
    print()
    print("  CALIBRATION 3: the held-equal list and its tolerance, both directions")
    _self_test_held_equal(expect)
    print()
    print("  CALIBRATION 4: the two live silent cases, one per comparator")
    _self_test_live(pairs, expect, unanswered)
    for row in unanswered:
        print(f"    [NOT ANSWERED] {row['case']}")
        print(f"                   expected  : {row['expected'][:130]}")
        print(f"                   found     : {row['found'][:130]}")
        print(f"                   means     : {row['means'][:130]}")
    print(f"    {len(asserted) - len(failures)} of {len(asserted)} calibration "
          f"assertions hold, {len(unanswered)} case(s) not answered")
    return failures, asserted, unanswered


# =====================================================================
# THE RUN
# =====================================================================

def print_comparison(row):
    """One published difference: its axis, what was re-measured, and what differs."""
    print(f"  {row['left']} against {row['right']}   in {row['artifact']} -> "
          f"{row['container']}")
    print(f"      manifest      : {row['manifest']} "
          f"(arm_a {row['arm_a_of_the_manifest']}, "
          f"arm_b {row['arm_b_of_the_manifest']})")
    print(f"      axis declared : {row['axis']}")
    print(f"      held equal    : {row['n_held_equal_declared']} declared, "
          f"{row['n_held_equal_remeasured']} re-measured on the leaves, "
          f"{row['n_held_equal_rechecked']} re-compared from the recorded values, "
          f"0 taken on trust")
    for item in row["held_equal_remeasured"]:
        print(f"        [{'ok  ' if item['holds'] else 'BREACH'}] "
              f"{str(item['quantity']):46} {item['why']}")
        if not item["holds"]:
            print(f"                 {row['left']} {item['left']!r}   "
                  f"{row['right']} {item['right']!r}")
            print(f"                 address {item['measured_by']}")
    for item in row["held_equal_rechecked_from_recorded_values"]:
        # A DIFFERENT MARK FROM THE LEAF WALK, BECAUSE IT IS A WEAKER CHECK AND SAYING
        # so is the whole point. What is NOT said is how many addresses were read: two
        # values that agree may be one address read twice or two addresses that happen
        # to agree, and this gate cannot tell them apart without parsing the prose of
        # measured_by. The address is printed instead, so a reader can see which.
        mark = "ok~ " if item["holds"] else "BREACH"
        print(f"        [{mark}] {str(item['quantity']):46} {item['why']}")
        print(f"                 by {item['measured_by'][:88]}")
        print(f"                 not fetched by this gate, so a wrong FETCH is "
              f"invisible here; a wrong COMPARISON is not")
    if row["n_disagreements_with_the_producer"]:
        print(f"      DISAGREES WITH THE PRODUCER on "
              f"{row['n_disagreements_with_the_producer']} quantity(ies): the "
              f"artifact's own `holds` says one thing and the leaves another")
    print(f"      leaves        : {row['n_leaves_under_both']} under both arms, "
          f"{row['n_leaves_under_one_arm_only']} under one only")
    print(f"      differing outside what the manifest measures: "
          f"{row['n_outside_the_manifest']} {row['outside_by_block']}")
    print("      Those are candidates for a person to sort into the axis, a "
          "consequence of it, and")
    print("      a confound. This gate does not sort them and does not say the "
          "contrast is sound.")


def main():
    started = artifact.start_clock()
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[6])
    parser.add_argument("--pair", metavar="ID",
                        help="judge one pair by its id and exit non-zero if it "
                             "breaches its held-equal list or is undeclared, ignoring "
                             "the frozen debt. This is the calibration handle")
    parser.add_argument("--list", action="store_true",
                        help="print the state of every pair and stop")
    args = parser.parse_args()

    pairs, unresolved = sweep(ROOT, decl.DECLARATIONS)
    by_id = {row["id"]: row for row in pairs}
    by_state = {state: [row for row in pairs if row["state"] == state]
                for state in STATES}

    if args.list:
        for name in sorted(by_id):
            row = by_id[name]
            print(f"{row['state']:26} {row['n_breaches']:2} breach(es)   {name}")
        return 0

    if args.pair:
        row = by_id.get(args.pair)
        if row is None:
            print(mismatch_text(
                "--pair names no pair of any declared container",
                f"one of the {len(by_id)} ids that --list prints",
                f"--pair {args.pair!r}, which matches none of them",
                "checks/contrast_declarations.py, the DECLARATIONS table",
                "nothing was compared. This exit is about the command line and not "
                "about the artifact"))
            return 2
        print("=" * 78)
        print("  IS THE COMPARISON A COMPARISON - one pair")
        print("=" * 78)
        if row["state"] is COMPARISON:
            print_comparison(row)
            verdict = "BREACH" if row["n_breaches"] else "HELD"
        else:
            print(f"  {row['left']} against {row['right']}   in {row['artifact']} -> "
                  f"{row['container']}")
            print(f"      state         : {row['state']}")
            print(f"      grounds       : {(row['grounds'] or 'NONE')[:150]}")
            print(f"      leaves        : {row['n_leaves_under_both']} under both "
                  f"arms, {row['n_differing_leaves']} of them differ "
                  f"{row['outside_by_block']}")
            if row["state"] is NOT_A_COMPARISON:
                print("      The work publishes no difference for this pair, so "
                      "nothing is asked of it.")
                print("      Those differing leaves are not findings; they are what "
                      "two arms nobody")
                print("      subtracted look like beside each other.")
                verdict = "NOT A CLAIM"
            else:
                print(f"      NOT IN THE RANKING-ONLY LIST: "
                      f"{', '.join(row['arms_not_in_the_ranking_only_list']) or 'none'}")
                print("      No manifest publishes this pair and the arm is in no "
                      "ranking-only list, so")
                print("      nobody has said whether this is a claim. That is the "
                      "finding.")
                verdict = "NOT DECLARED"
        print("-" * 78)
        print(f"  VERDICT: {verdict}   (--pair ignores the frozen debt on purpose)")
        return 1 if (row["n_breaches"] or row["state"] is UNDECLARED) else 0

    breached = sorted(row["id"] for row in pairs if row["n_breaches"])
    undeclared_debt, repaid = against_the_debt(breached, decl.DECLARED_BREACHES)
    undeclared_pairs = sorted(row["id"] for row in by_state[UNDECLARED])
    disagreeing = [row for row in by_state[COMPARISON]
                   if row["n_disagreements_with_the_producer"]]
    grounds = next((row["grounds"] for row in by_state[NOT_A_COMPARISON]
                    if row["grounds"]), None)

    print("=" * 78)
    print("  IS THE COMPARISON A COMPARISON - contrast-hygiene gate")
    print("=" * 78)
    print(f"  declarations            : {len(decl.DECLARATIONS)} in "
          f"checks/contrast_declarations.py")
    print(f"  pairs judged            : {len(pairs)} over "
          f"{len({row['container'] for row in pairs})} arm container(s)")
    print("  predicate               : a pair is a COMPARISON when a manifest names "
          "both arms and the")
    print("                            delta block marks it published; NOT A "
          "COMPARISON when both arms")
    print("                            are named in the hand-written ranking-only "
          "list or the producer")
    print("                            refused the manifest; NOT DECLARED otherwise")
    print()
    for state in STATES:
        print(f"      {state:28} {len(by_state[state]):4}")
    print(f"      {'total':28} {len(pairs):4}")
    print()
    print("  the middle state rests on the producer's own grounds, read this run from")
    print(f"  {decl.QUOTER_BAKEOFF['artifact']} -> "
          f"{decl.QUOTER_BAKEOFF['grounds_at']}:")
    print(f"      \"{(grounds or 'NOT FOUND')[:140]}\"")
    print(f"  and on a hand-written decision naming its arms, taken "
          f"{decl.QUOTER_BAKEOFF['ranking_only_decided']}.")
    print("  Neither is restated in this gate: a check carrying its own copy of a rule "
          "asserts the")
    print("  old rule after the rule is fixed.")

    print()
    print(f"  PAIRS NOT DECLARED IN EITHER SENSE: {len(undeclared_pairs)} "
          f"(permitted 0)")
    for name in undeclared_pairs:
        print(f"      {name}   not in the ranking-only list: "
              f"{', '.join(by_id[name]['arms_not_in_the_ranking_only_list'])}")
    print(f"  PUBLISHED DIFFERENCES BREACHING THEIR HELD-EQUAL LIST: {len(breached)}")
    print(f"      outside the frozen debt : {len(undeclared_debt)} (permitted 0)")
    for name in undeclared_debt:
        print(f"          {name}")
    print(f"      declared and now repaid : {len(repaid)}"
          + ("; shorten DECLARED_BREACHES in contrast_declarations.py"
             if repaid else ""))
    print(f"  RE-MEASUREMENTS DISAGREEING WITH THE PRODUCER'S OWN VERDICT: "
          f"{len(disagreeing)} (permitted 0)")

    print()
    print(f"  PUBLISHED DIFFERENCES, EACH RE-MEASURED AGAINST ITS OWN MANIFEST: "
          f"{len(by_state[COMPARISON])}")
    for row in sorted(by_state[COMPARISON], key=lambda r: r["id"]):
        print()
        print_comparison(row)

    print()
    print(f"  PAIRS THE WORK MAKES NO CLAIM ABOUT: {len(by_state[NOT_A_COMPARISON])}, "
          f"counted and not questioned")
    print("      Listed so a reader sees the population rather than trusting it was "
          "swept. Leaf")
    print("      differences among them are not findings: nobody subtracted these two "
          "arms.")
    for row in sorted(by_state[NOT_A_COMPARISON],
                      key=lambda r: -r["n_differing_leaves"])[:6]:
        print(f"      - {row['left']} against {row['right']} in {row['container']}: "
              f"{row['n_differing_leaves']} differing leaves")
    if len(by_state[NOT_A_COMPARISON]) > 6:
        print(f"      ... and {len(by_state[NOT_A_COMPARISON]) - 6} more, all in "
              f"{OUT_NAME}")

    if unresolved:
        print()
        print(f"  DECLARATIONS THAT PRODUCED NO COMPARISON AT ALL: {len(unresolved)}")
        for row in unresolved:
            print(f"      - {row['what']}: expected {row['expected'][:80]}")
            print(f"        found {row['found'][:80]}  at {row['place']}")

    print()
    failures, asserted, unanswered = calibrate(pairs)

    rules = [
        {"name": "every pair is in a declared state: a comparison, or a written "
                 "non-claim",
         "permitted": 0, "found": len(undeclared_pairs),
         "assumption": "a pair is a claim when a manifest publishes it and a non-claim "
                       "when a person wrote down that it is one. An arm in neither has "
                       "entered a published ranking with no axis and no held-equal "
                       "list and nobody has said so. The middle state exists because "
                       "the two-state version of this rule reported 36 findings on a "
                       "nine-arm bake-off of which none was a defect, and a gate that "
                       "is red for a reason nobody can act on stops being read",
         "method": "the manifests at the declared address for the first state, the "
                   "hand-written ranking-only arm list for the second, every other "
                   "pair of the container for the third",
         "note": "put the arm in a state: either a manifest publishing its difference "
                 "with an axis and a held-equal list, or the ranking-only list with "
                 "the reason. Do not widen the ranking-only list silently to make a "
                 "run green -- the middle state is a decision and is written in words",
         "sites": [{"file": by_id[name]["artifact"], "line": "-",
                    "detail": f"{name}: not in the ranking-only list -- "
                              f"{', '.join(by_id[name]['arms_not_in_the_ranking_only_list'])}",
                    "source": by_id[name]["container"]}
                   for name in undeclared_pairs]},
        {"name": "no published difference breaches the held-equal list it declares",
         "permitted": 0, "found": len(undeclared_debt),
         "assumption": "the frozen debt is empty. It held 28 pairs when this gate was "
                       "written, over a six-arm bake-off in which 14 of 15 pairs "
                       "differed in realised quote width; the bake-off was recomputed "
                       "with three arms solved onto one target width and those "
                       "differences are what it publishes now. The list may only ever "
                       "be shortened, so from here it can only stay empty",
         "method": "every held-equal address the manifest gives that is relative to an "
                   "arm, re-measured on the leaves against the rtol the manifest "
                   "declares beside it; the producer's own `holds` is compared, never "
                   "read",
         "note": "equalise the arms on the quantity named beside the breach, or move "
                 "it out of the manifest's held-equal list and say there why it is a "
                 "consequence of the axis rather than a confound",
         "sites": [{"file": by_id[name]["artifact"], "line": "-",
                    "detail": f"{name}: {by_id[name]['n_breaches']} declared "
                              f"quantity(ies) differ, first at "
                              f"{by_id[name]['breaches'][0]['quantity']}",
                    "source": by_id[name]["container"]}
                   for name in undeclared_debt]},
        {"name": "this gate's re-measurement agrees with the producer's own verdict",
         "permitted": 0, "found": len(disagreeing),
         "assumption": "the artifact writes `holds` beside each held-equal quantity. "
                       "This gate ignores it, re-measures from the leaves and then "
                       "compares. A disagreement means one of the two is wrong about a "
                       "published difference, and until the mechanism is named neither "
                       "figure should be used",
         "method": "the boolean this gate measured against the boolean the manifest "
                   "recorded, per quantity",
         "note": "re-run the producer into a scratch directory and diff leaf by leaf; "
                 "do not adopt either verdict until the mechanism is named",
         "sites": [{"file": row["artifact"], "line": "-",
                    "detail": f"{row['id']}: "
                              f"{row['n_disagreements_with_the_producer']} "
                              f"quantity(ies) where `holds` and the leaves disagree",
                    "source": row["container"]}
                   for row in disagreeing]},
        {"name": "every declaration resolves: the artifact, the manifest block, the "
                 "grounds and every declared arm",
         "permitted": 0, "found": len(unresolved),
         "assumption": "a pair nobody compared is not a pair that agreed. The grounds "
                       "for the middle state live in the artifact and are quoted from "
                       "there every run; if that address goes empty the middle state "
                       "rests on nothing, and this gate must report that rather than "
                       "supply the reason itself",
         "method": "the dotted addresses of the declaration resolved against the "
                   "artifact, and the declared arm names against the container's keys, "
                   "with an absent arm split by whether a MANIFEST names it or only "
                   "the hand-written list does",
         "note": "what to do differs by which row fired, and every row carries its own "
                 "sentence. An arm a manifest names is an artifact contradicting "
                 "itself and the published figure rests on nothing. An arm only the "
                 "hand-written list names is that list and the artifact being out of "
                 "step, which also happens while a producer run is still running and "
                 "clears itself when it lands. A missing address is neither: correct "
                 "it, or restore what the producer used to write there",
         "sites": [{"file": row["place"], "line": "-",
                    "detail": f"{row['what']}: expected {row['expected']}; found "
                              f"{row['found']}"
                              + (f". {row['means']}" if row.get("means") else "")}
                   for row in unresolved]},
        {"name": "the gate is calibrated on opposite cases, two per comparator",
         "permitted": 0, "found": len(failures),
         "assumption": "there are two decisions here and they fail differently, so one "
                       "pair of cases is not enough. The firing halves are injected "
                       "because a firing case taken from the live tree empties the day "
                       "the defect is repaired, which is how two instruments of this "
                       "project came to be red or silent while checking nothing",
         "method": f"{len(asserted)} assertions, run on every invocation rather than "
                   f"behind a flag",
         "note": "until this passes no count above means anything: a comparator nobody "
                 "has seen fire is not evidence that there is nothing to find",
         "sites": [{"file": "checks/" + OUT_NAME, "line": "-",
                    "detail": f"{row['assertion']}: {row['detail']}"}
                   for row in failures]},
    ]

    over = [rule for rule in rules
            if rule["permitted"] is not None and rule["found"] > rule["permitted"]]
    clean = all(rule["found"] == 0 for rule in rules) and not breached
    verdict = "FAIL" if over else ("PASS" if clean else "PASS_AT_BASELINE")

    payload = {
        "verdict": verdict,
        "asks": "whether the two arms of each published difference differ along the "
                "one axis their manifest names, and before that, whether anybody has "
                "said which pairs are claims at all. Neither is asked by the "
                "freshness, provenance or register gates: each of those asks whether "
                "it is the same NUMBER, and none asks whether the comparison is a "
                "comparison",
        "does_not_ask": "whether any contrast is sound. This gate sorts nothing into "
                        "axis, consequence and confound, and prints no word that could "
                        "be read as approval: an instrument certifying a contrast "
                        "would report success where there may be none, which is the "
                        "direction of error that passes a review",
        "states": {
            "predicate": {
                COMPARISON: "a manifest at the declared address names both arms and "
                            "the delta block marks the difference published",
                NOT_A_COMPARISON: "both arms are named in the hand-written "
                                  "ranking-only list and no manifest publishes the "
                                  "pair, or the producer refused the manifest",
                UNDECLARED: "everything else, which is the finding",
            },
            "counts": {state: len(by_state[state]) for state in STATES},
            "population": f"{len(pairs)} pairs over "
                          f"{len({row['container'] for row in pairs})} containers, "
                          f"being every pair of arms each container holds",
        },
        "read_from_the_artifact_not_restated": {
            "axis_and_held_equal": decl.QUOTER_BAKEOFF["manifests_at"],
            "what_is_published": decl.QUOTER_BAKEOFF["deltas_at"],
            "grounds_for_the_middle_state": decl.QUOTER_BAKEOFF["grounds_at"],
            "grounds_text_this_run": grounds,
            "why": "a check that retypes the rule it checks goes on asserting the old "
                   "rule after the rule is fixed, and its disagreement then looks like "
                   "a finding without being one. The producer's own `holds` fields are "
                   "the exception: those are compared, never read",
        },
        "decided_by_hand": {
            "ranking_only_arms": list(decl.QUOTER_BAKEOFF["ranking_only_arms"]),
            "reason": decl.QUOTER_BAKEOFF["ranking_only_reason"],
            "decided": decl.QUOTER_BAKEOFF["ranking_only_decided"],
            "why_named_one_by_one": "written as 'everything else' the third state "
                                    "could never fire, and a rule that cannot fire is "
                                    "not a rule",
        },
        "n_pairs_judged": len(pairs),
        "undeclared_pairs": undeclared_pairs,
        "breaching_pairs": breached,
        "disagreements_with_the_producer": [row["id"] for row in disagreeing],
        "frozen_debt": {
            "pairs": list(decl.DECLARED_BREACHES),
            "n": len(decl.DECLARED_BREACHES),
            "was": 28,
            "why_empty": "the 28 were pairs of a six-arm bake-off differing in "
                         "realised quote width under published cost differences. The "
                         "bake-off was recomputed with three arms solved onto one "
                         "target width, and the 0.636 bps figure this gate was written "
                         "for is no longer a published difference",
            "outside_the_debt": undeclared_debt,
            "declared_and_now_repaid": repaid,
        },
        "calibration": {
            "coverage_must_stay_silent": decl.CALIBRATION_COVERAGE_MUST_STAY_SILENT,
            "coverage_must_fire": decl.CALIBRATION_COVERAGE_MUST_FIRE,
            "held_equal_must_stay_silent":
                decl.CALIBRATION_HELD_EQUAL_MUST_STAY_SILENT,
            "held_equal_must_fire": decl.CALIBRATION_HELD_EQUAL_MUST_FIRE,
            "n_assertions": len(asserted),
            "n_failed": len(failures),
            "failures": failures,
            "not_answered": unanswered,
        },
        "unresolved": unresolved,
        "pairs": pairs,
    }

    artifact.write(
        OUT_NAME, payload,
        script=__file__,
        inputs=[os.path.join(ROOT, d["artifact"]) for d in decl.DECLARATIONS]
               + [os.path.join(HERE, "contrast_declarations.py")],
        scope={
            "population": f"{len(pairs)} pairs of arms over "
                          f"{len({row['container'] for row in pairs})} containers "
                          f"declared in checks/contrast_declarations.py, judged on "
                          f"{sum(row['n_leaves_under_both'] for row in pairs)} leaf "
                          f"comparisons",
            "window": "n/a: this gate compares leaves of a results file against each "
                      "other and reads no market data; the window is whatever the "
                      "artifact under test declares",
            "coins": "n/a: whatever the artifact under test declares",
        },
        started=started,
        extra_meta={
            "not_caught": [
                "a confound the manifest does not name. This gate re-measures the "
                "held-equal list it is given and nothing else, so an axis declared "
                "carelessly is checked carelessly",
                "a held-equal quantity whose address is not relative to an arm. The "
                "recapture fraction, the headline horizon and the eligible-wallet "
                "count are shared by both arms by construction and no walk of the two "
                "arms reaches them; they are named unreachable and not counted as "
                "checked",
                "a middle-state pair that should have been a claim. Moving a pair "
                "there is a decision written by hand, and this gate checks that "
                "somebody wrote it, never that they were right to",
                "a measurement the artifact does not print. Two arms differing in "
                "something neither records have no leaf to differ at",
                "a confound entering through a shared input rather than through the "
                "arms: two arms reading one stale column agree perfectly, and that is "
                "chk_input_freshness's question",
            ],
        },
    )

    print("-" * 78)
    print(f"  VERDICT: {verdict}")
    print(f"  results -> {OUT_NAME}")

    code = report_gate(rules, OUT_NAME, inputs={
        "population": f"{len(pairs)} pairs of arms over "
                      f"{len({row['container'] for row in pairs})} containers",
        "predicate": "three states: the producer's manifests, the hand-written "
                     "ranking-only list, and everything else",
    })
    return 1 if (over or failures) else code


if __name__ == "__main__":
    sys.exit(main())
