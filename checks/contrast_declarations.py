#!/usr/bin/env python3
"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-08-03
References: none (a declaration read by checks/chk_contrast_hygiene.py; it computes
nothing and publishes no figure of its own).

WHICH PAIRS OF ARMS ARE CLAIMS, WHICH ARE DELIBERATELY NOT CLAIMS, AND THE DIFFERENCE
BETWEEN EITHER OF THOSE AND A PAIR NOBODY THOUGHT ABOUT.

A difference between two arms means what the text says it means only if the arms differ
along the one axis the text names. But a harder question comes first, and getting it
wrong in either direction breaks the gate that follows.

  Treat every pair inside a container as a published claim and the gate demands an
  entry for all 36 pairs of a nine-arm bake-off. Nothing is wrong with 33 of them, so
  the gate is permanently red, and a permanently red gate is a switched-off gate. That
  is not a guess: this project emptied a calibration case for exactly that reason on
  2026-08-03, and the first version of this file made the same error one level up.

  Treat an undeclared pair as nothing to answer for and a tenth arm can walk into a
  published ranking with no axis, no held-equal list and nobody noticing.

So there are three states and not two, and the middle one is a written decision rather
than an absence.

WHERE EACH OF THE THREE COMES FROM, AND WHY THEY COME FROM DIFFERENT PLACES.

  DECLARED AS A COMPARISON. Read out of the artifact, never restated here. The
      producer writes its own manifest per published difference -- the axis, the list
      held equal, the tolerance on each, and what it classifies as a consequence or a
      confound -- at declared_axis_comparisons.manifests, and marks the difference
      published at declared_axis_comparisons.deltas. A check that retyped that list
      would be blind to exactly the change it exists to notice, so the check reads the
      addresses and RE-MEASURES them on the leaves rather than believing the summary
      field beside them.

  DECLARED AS NOT A COMPARISON. Written here, by hand, with the reason, because it is
      a decision and not a measurement: no address in the artifact can say that
      somebody thought about a pair and chose not to publish a difference for it. What
      is NOT retyped here is the grounds, which the artifact already carries at
      declared_axis_comparisons.why; the check quotes it from that address every run.

  NOT DECLARED AT ALL. Everything left. This is the finding, and the whole point of
      naming the arms below one by one instead of writing "everything else": a tenth
      arm belongs to no state until a person puts it in one.

THE FORM OF THIS FILE. Python rather than JSON, and the cost is measured on both sides.
A .json here joins the population chk_artifact_provenance.py walks, where a hand-written
file carries no producer, no inputs, no run record and no scope: checks/NEUTRAL_EDITS.json
sits in that position today and appears in four of that gate's missing-record lists. A
.py stays out of that population, carries the header every file of this tree carries, and
lets the reason for a decision sit on the line under it.
"""

# =====================================================================
# THE QUOTER BAKE-OFF
# =====================================================================
#
# Nine re-quoting rules are run over one fixed set of maker fills. The artifact orders
# all nine on one metric and publishes THREE differences, each with its own axis, its
# own held-equal list and its own solved equal-width construction.
#
# NOTHING ABOUT THE AXES IS WRITTEN HERE. They are at declared_axis_comparisons in the
# artifact, put there by the producer that computed them, which is the only place they
# can be kept honest: an axis restated in a checking file drifts towards whatever the
# check happens to find, and a check carrying its own copy of a rule goes on asserting
# the old rule after the rule is fixed. The addresses below are how the check reaches
# them.

QUOTER_BAKEOFF = {
    "id": "quoter_bakeoff",
    "artifact": "quoters/mm_bakeoff_results.json",
    "arms_under": "quoters.*",

    # The producer's own statement of what it publishes and on what axis.
    "manifests_at": "declared_axis_comparisons.manifests",
    "deltas_at": "declared_axis_comparisons.deltas",

    # The producer's own grounds for the middle state. Quoted from this address on
    # every run and never copied into this file. As of 2026-08-03 it says that a
    # ranking orders arms on one metric and does not make any two of them comparable,
    # but the check prints whatever is there today rather than that sentence.
    "grounds_at": "declared_axis_comparisons.why",

    # An arm-relative held-equal address in a manifest starts with this. The rest are
    # settings and solve fields shared by both arms by construction, which no walk of
    # the two arms' leaves can reach; the check names those unreachable rather than
    # counting them checked.
    "arm_relative_prefix": "quoters.<K>.<arm>.",

    # THE MIDDLE STATE, ARM BY ARM. Every arm the container may hold. A pair of these
    # that no manifest publishes is a considered non-claim; an arm outside this list is
    # a finding. Listing them rather than writing "all the rest" is what keeps the
    # third state able to fire: with "all the rest" nothing can ever be undeclared, and
    # a rule that cannot fire is not a rule.
    "ranking_only_arms": (
        "naive_at_book", "naive_const", "as_symmetric", "gm_vpin", "bbgl",
        "as_toxicity", "as_toxicity_ew", "bbgl_flat", "as_toxicity_plus_global",
    ),
    # NO COUNTS IN THIS SENTENCE, AND THAT IS DELIBERATE. It read "a difference for
    # three pairs and an ordering over all nine" until 2026-08-05, and by the time it
    # was read both numbers were wrong: the producer had grown more arms and more
    # published differences. A count written by hand beside a fact that lives elsewhere
    # is a copy, and this project has already paid for copies -- one headline figure
    # lived in 78 files at its old value and 25 at its new one. The live counts are the
    # artifact's and the gate prints them from the sweep on every run.
    "ranking_only_reason":
        "the work publishes a difference for the pairs its manifests name, and an "
        "ordering over every arm. Those are different claims. A difference is made "
        "only where the arms were built to be equal on everything but one axis, which "
        "for this bake-off means a solved equal-width construction, and the producer "
        "solves it for the pairs it publishes and no others. Any other pair differs in "
        "realised quote width as well as in rule, and since the recapture books a "
        "printed fill to the arm whatever the arm quoted, standing wider is free and "
        "such a difference would be confounded. The work does not make it, so this "
        "gate does not ask what its axis was. The grounds are the producer's own and "
        "are read at grounds_at.",
    "ranking_only_decided": "2026-08-03",
}

DECLARATIONS = (QUOTER_BAKEOFF,)


# =====================================================================
# THE DEBT, AND WHY IT IS EMPTY
# =====================================================================
#
# This list held 28 pairs when the gate was written on 2026-08-03, over a six-arm
# bake-off in which 14 of the 15 pairs differed in realised quote width while the prose
# published their cost differences as though they did not. It is empty now, and that is
# a repair rather than a relaxation: the bake-off was recomputed with the arms it
# compares solved to land on one target width, and the differences it publishes are
# those solved pairs. The 0.636 bps figure this gate was written for is no longer a
# published difference. How many such pairs there are today is the artifact's fact and
# the gate counts it on every run; a number written here would be a second copy, which
# is what the paragraph above the arm list is about.
#
# It may only ever be shortened, so from here it can only stay empty. A pair that
# breaches its declared held-equal list fails the run and is named. Adding a pair here
# to turn a red run green removes the gate, which is the only thing it is for.
DECLARED_BREACHES = ()


# =====================================================================
# FOUR OPPOSITE CASES: TWO COMPARATORS, EACH WITH ONE OF EITHER KIND
# =====================================================================
#
# There are two decisions in this gate and they fail in different ways, so one pair of
# cases is not enough. Which state a pair is in is one comparator; whether a declared
# comparison's held-equal list actually holds is another.
#
# WHERE EACH CASE COMES FROM, AND WHY THE FIRING ONES ARE INJECTED. A case taken from
# the live tree empties the day somebody fixes what it was watching, and the gate then
# certifies itself on a population with no failures left in it. That happened to two
# instruments of this project on 2026-08-03. So the cases that must FIRE are built in a
# temporary directory by the check and cannot decay, while the cases that must stay
# SILENT are live: those decay in the safe direction, because a live silent case going
# noisy is the gate catching something.

# Coverage: a pair both of whose arms are in ranking_only_arms and which no manifest
# publishes. It must land in the middle state and must not be reported.
CALIBRATION_COVERAGE_MUST_STAY_SILENT = {
    "declaration": "quoter_bakeoff",
    "container": "quoters.K50",
    "left": "as_toxicity_ew",
    "right": "naive_const",
    "expect_state": "declared_not_a_comparison",
    "why": "both arms stand in the ordering the bake-off publishes and no manifest "
           "names the pair, so the work makes no claim about their difference. Before "
           "the three states existed this pair was reported as a missing declaration, "
           "and 36 such reports on one run is how a gate teaches people to stop "
           "reading it",
}

# Coverage: the firing half is injected by the check, because every arm of this tree is
# in a state today. This entry records what the injection is, so both halves are
# described in one place.
CALIBRATION_COVERAGE_MUST_FIRE = {
    "injected": True,
    "what": "an arm placed in a fixture container that appears in no manifest and in "
            "no ranking_only_arms list",
    "expect_state": "not_declared",
    "why": "taken from the live tree this case would empty the day the arm is "
           "declared, leaving a gate that reports nothing and cannot be shown able to "
           "report anything. Two instruments of this project failed that way on "
           "2026-08-03, which is why it is injected",
}

# Held equal: a published difference whose declared list holds on every arm-relative
# address, in both containers.
#
# MOVED OFF THE EXACTLY-EQUAL PAIR ON 2026-08-05, AND THAT IS THE WHOLE VALUE OF THE
# CASE. It used to stand on as_toxicity_ew against bbgl, whose solved widths land on the
# same float, 6.364595937112405 twice over. A case that holds by exact equality cannot
# tell a comparator honouring the declared rtol apart from one demanding equality to the
# last bit, and this gate exists to catch the second. The pair below lands at
# 6.364595937112404 against 6.364595937112405 -- a relative gap of 1.4e-16, non-zero and
# far inside the declared 1e-09 -- so a comparator that stopped reading the tolerance
# would now fail here instead of passing. The classifier arms solve into the same
# neighbourhood, so this is also the case that keeps a correct landing from being read
# as a breach when they land.
CALIBRATION_HELD_EQUAL_MUST_STAY_SILENT = {
    "declaration": "quoter_bakeoff",
    "container": "quoters.K50",
    "left": "as_toxicity_plus_global",
    "right": "bbgl",
    "expect_breaches": 0,
    "expect_held_equal_addresses": 3,
    "why": "the equal-width solve lands as_toxicity_plus_global's pooled mean extra "
           "half spread at 6.364595937112404 against bbgl's 6.364595937112405, a "
           "relative gap of 1.4e-16 against the 1e-09 the producer declares, and the "
           "late-fill count and the finite-extra count agree exactly at 1234777. Three "
           "of its seven declared held-equal quantities are addressable under an arm "
           "and are the three re-measured here; the other four -- the shared global "
           "leg, the wallet count carrying a wallet-specific premium, the recapture "
           "fraction and the headline horizon -- are settings and solve fields shared "
           "by both arms by construction, which no walk of the arms can reach and "
           "which this gate reports as unreachable rather than counting as checked. "
           "400 leaves under both arms do differ, so the silence is a measured "
           "agreement on the declared list and not an empty comparison",
}

# Held equal: injected, for the same reason as the coverage firing case. As of
# 2026-08-03 no published difference of this tree breaches its list, and a firing case
# that depends on one doing so would be a gate waiting for a defect to certify itself.
CALIBRATION_HELD_EQUAL_MUST_FIRE = {
    "injected": True,
    "what": "a fixture manifest whose declared held-equal address carries a different "
            "value in the two arms, once inside the declared tolerance and once "
            "outside it",
    "expect_breaches": 1,
    "why": "all three published differences hold today, so there is no live case. The "
           "pair of injections also calibrates the TOLERANCE, which a single case "
           "cannot: the producer declares rtol 1e-09 on the solved width and 0.0 on "
           "the counts, and one published difference lands at 2.9e-16 relative. A "
           "comparator demanding exact equality would call that a breach, and one "
           "ignoring the declared tolerance would pass a real one",
}
