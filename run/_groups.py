#!/usr/bin/env python3
"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-07-31
References: none (repository infrastructure; it declares no quantity of its own and
reads the graph build.py derives from the syntax trees of this tree's scripts).

ONE ENTRY POINT PER PIPELINE GROUP, AND THE TABLE THAT SAYS WHICH NODE BELONGS WHERE.

WHY THIS MODULE EXISTS. Until now every producer in this tree was its own entry point:
seventy-two scripts, each launched by hand, and the only way to learn which of them
answer one question was to open them one at a time. That is the shape a newcomer cannot
read, and reading it is what a repository owes a newcomer. The pipeline is not
seventy-two things. It is eight groups, each answering one question, and this module is
where the membership is written down so that a group can be named, planned, priced and
recomputed as one.

WHAT AN ENTRY POINT OWES, AND IT IS THREE THINGS. Every file in this directory can
recompute its whole group; can recompute one named node or one named quantity inside
one artifact; and can print the plan and its price while computing nothing at all. The
last is the default, because the first question anyone has about a recompute is what it
is going to cost, and a tool that answers that only by starting is not answering it.

WHERE THE WORK IS AND WHERE IT IS NOT. Nothing here decides what has to run. build.py
owns the dependency graph, the skip rule and the disk limit, and every plan printed
below is the plan build.py produced, filtered to one group's nodes and their upstream.
A second list of nodes kept beside build.py's would drift from it within a week, so
there is not one: the only thing this module adds to the graph is the GROUP each node
belongs to, which is a fact about the argument and cannot be read out of any syntax
tree.

HOW MEMBERSHIP IS DECIDED, AND WHY IT IS TYPED RATHER THAN DERIVED. A group is a
question, and which question a script answers is not visible in what it imports or what
it writes. So the table below is written by hand -- and because it is written by hand it
is checked by program: census() puts the table against the graph build.py derives and
reports three failures, each of which has already happened to a hand-kept list in this
repository. A node in the graph that no group claims is unassigned and is printed. A
group entry naming a node the graph does not hold is stale and is printed. A node
claimed by two groups is a duplicate and is printed, because two entry points that both
recompute one node will each report it as theirs.

WHAT A NODE IS HERE. The same thing it is in build.py: a script, or a script under one
declared command-line arm. panel_persistence.py is two nodes and they sit in two
different groups -- `--build` walks the raw archive and writes the panel every later
group reads, so it is data; `--analyze` asks whether a wallet's score survives from one
month to another, so it is persistence. Naming the script alone would have put the
archive walk into the persistence group and made that group's recompute cost hours it
does not owe.

THE PLAN'S PRICE, AND WHAT IT IS MISSING. Each artifact records how long its producer
took, under _meta.run.runtime_s, and that is what is printed beside each planned node.
Where a node has never recorded a runtime the line says so rather than guessing, and the
total states how many of the planned nodes it covers. A total that silently stood for
the whole plan would be the more useful-looking number and the less true one.

    uv run --no-project --with-requirements requirements.txt python3 run/persistence.py
    uv run --no-project --with-requirements requirements.txt python3 run/persistence.py --members
    uv run --no-project --with-requirements requirements.txt python3 run/persistence.py --census
    uv run --no-project --with-requirements requirements.txt python3 run/persistence.py --run
    uv run --no-project --with-requirements requirements.txt python3 run/persistence.py --only i2_walletfe_results.json --run
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
import build                                                            # noqa: E402


# =====================================================================
# 1. THE GROUPS
#
# Fields, and what each is for.
#
#   id          what the entry point is called, and the name --census prints
#   step        the step of the project plan this group is the code of
#   question    the one question the group answers, in the words the report uses
#   predicate   how a node was decided to belong here. Written down because a
#               classification without a stated rule cannot be argued with, only
#               agreed with, and the next person adding a script needs the rule
#   entry       the file to run
#   nodes       node keys, exactly as build.py keys them: script, plus the declared
#               arm where a script holds more than one node
#   unschedulable  scripts that belong to this group by the same predicate and that
#               build.py holds no node for, because it can see no artifact they write.
#               Named rather than dropped: an entry point that silently omits a member
#               of its own group is worse than one that says it cannot run it
# =====================================================================

GROUPS = (
    {
        "id": "data",
        "step": "1, the data",
        "question": "what was parsed out of the public archive, over which windows and "
                    "coins, and does the parse still reproduce",
        "predicate": "the node walks the raw archive, or it builds one of the shared "
                     "per-fill intermediates every other group reads, or it gates the "
                     "coverage and the schema of that build. Its output is an input to "
                     "another group rather than an answer to a question about the "
                     "market",
        "entry": "run/data.py",
        "nodes": (
            "data/build_quickwin_markouts.py",
            "data/i4_l2_mid.py",
            "data/i4_midmarkout.py",
            "data/panel_persistence.py --build",
            "data/panel_build.py",
            "data/panel_rebuild_v2.py",
            "data/check_first.py",
            "data/killswitch1_repeat_density.py",
            # Claimed on 2026-08-30. Until then no entry point reached them,
            # so no command a reader is told to run recomputed them. Placed by
            # SUBJECT, not by directory: all three read what this group parses out of the public archive.
            "data/d1_book_shape_figure.py",
            "data/d2_fill_tape_figure.py",
            "data/build_toxicity_frame.py",
        ),
        "unschedulable": (
            ("data/step1_inventory.py",
             "the read-only half of the acquisition stage. It prints an inventory table "
             "per coin and window and writes no tracked file, so build.py holds no node "
             "for it and no skip rule covers it"),
            ("data/killswitch2_markout_join.py",
             "the superseded first attempt at a reference mid, kept for provenance. It "
             "writes no tracked file"),
        ),
    },
    {
        "id": "markout",
        "step": "2, the harm of one trade",
        "question": "how large the harm to the maker who filled a trade is, and how it "
                    "is shaped -- over the horizon, over the trade size, over the "
                    "taker's inventory and over the side",
        "predicate": "the node reports the size or the shape of the per-fill markout "
                     "itself. It makes no claim about whether the wallet behind the "
                     "trade behaves the same way later, and none about what the "
                     "wallet's identity adds",
        "entry": "run/markout.py",
        "nodes": (
            "markout/ws1_horizon_persistence.py",
            "markout/ws1_plot.py",
            "markout/m5_termstructure.py",
            "markout/m6_inventory.py",
            "markout/confound_asymmetry.py",
            "markout/m2_figure.py",
            "markout/temp_perm_decomp.py",
            # Claimed on 2026-08-30. Until then no entry point reached it,
            # so no command a reader is told to run recomputed it. Placed by
            # SUBJECT, not by directory: it draws the markout curve this group measures.
            "markout/ws1_markout_curve_figure.py",
        ),
        "unschedulable": (),
    },
    {
        "id": "persistence",
        "step": "3, the wallet's score and whether it holds",
        "question": "whether the harm is a stable trait of the wallet rather than a "
                    "property of one window: does a wallet scored in one window keep "
                    "its rank in a disjoint later one, and how much of the "
                    "cross-sectional variance is a per-wallet component at all",
        "predicate": "the node scores a wallet in one window and asks what survives "
                     "into another, or it splits the variance into a per-wallet part "
                     "and the rest. Two windows, or two halves of one window, are what "
                     "every member has in common",
        "entry": "run/persistence.py",
        "nodes": (
            "persistence/ks2_persistence_10day.py",
            "persistence/ks2_markout_multiday.py",
            "persistence/three_coin_persistence.py",
            "data/panel_persistence.py --analyze",
            "persistence/panel_analyze.py",
            "persistence/panel_common_idio.py",
            "persistence/i2_walletfe.py",
            "persistence/forward_toxicity.py",
            "persistence/ws2_hard_classifier.py",
            "persistence/ws3_taker_pnl.py",
            "persistence/m9_crossasset.py",
            # Claimed on 2026-08-30. Until then no entry point reached them,
            # so no command a reader is told to run recomputed them. Placed by
            # SUBJECT, not by directory: one draws the taker-PnL figure; the other writes the seven
            # panel_extended_results_*.json over the wider window set.
            "persistence/ws3_plot.py",
            "persistence/panel_extended.py",
        ),
        "unschedulable": (),
    },
    {
        "id": "identity",
        "step": "4 with 4A, what the name adds over the public book",
        "question": "whether a maker who sees only public information -- the trade tape, "
                    "and then the full order book -- could have recovered what the "
                    "counterparty's identity gives, and whether the identity term "
                    "survives the controls that would explain it away",
        "predicate": "the node holds the public information set fixed and asks what "
                     "adding the counterparty's own history changes, or it removes one "
                     "candidate explanation of the identity term -- the book state the "
                     "wallet trades into, its trade size, the direction of its position "
                     "-- and reports what is left",
        "entry": "run/identity.py",
        "nodes": (
            "identity/i3_nonrecoverability_oos.py --source trade",
            "identity/i3_nonrecoverability_oos.py --source mid",
            "identity/i3_book_comparator.py --stage feats",
            "identity/i3_book_comparator.py --stage test",
            "identity/i3_depth_control.py",
            "identity/own_size_control.py",
            "identity/i5_exclusion.py",
            "identity/follow_the_informed_oos.py",
            # Claimed on 2026-08-30. Until then no entry point reached it,
            # so no command a reader is told to run recomputed it. Placed by
            # SUBJECT, not by directory: it draws the pre-trade-versus-identity comparison.
            "identity/i3_pretrade_vs_identity_figure.py",
        ),
        "unschedulable": (),
    },
    {
        "id": "quoters",
        "step": "5, the quoting models",
        "question": "what the standard quoting models do on this fill set, and what the "
                    "counterparty-resolved term changes about the quote they set",
        "predicate": "the node instantiates a quoting model, or it puts several of them "
                     "on one common fill set under one common metric. Its output is a "
                     "spread and an inventory rule, never a dollar result for a maker",
        "entry": "run/quoters.py",
        "nodes": (
            "quoters/as_quoter.py",
            "quoters/gm_quoter.py",
            "quoters/mm_bakeoff.py",
            "quoters/t1_toxicity_skew_backtest.py",
            # Claimed on 2026-08-30. Until then no entry point reached it,
            # so no command a reader is told to run recomputed it. Placed by
            # SUBJECT, not by directory: it draws the reference bake-off of the quoting models.
            "quoters/mm_bakeoff_reference_figure.py",
        ),
        "unschedulable": (),
    },
    {
        "id": "money",
        "step": "6, the money",
        "question": "what the harm is worth in currency: how large the maker's loss to "
                    "adverse selection is over the window, where it is concentrated, "
                    "and what a policy that acts on the counterparty changes about it",
        "predicate": "the node states a result in currency or as a share of one, or it "
                     "says how that currency amount is distributed across "
                     "counterparties, sizes and sides",
        "entry": "run/money.py",
        "nodes": (
            "money/t3_capacity.py",
            "money/maker_econ.py",
            "money/maker_econ_b2.py",
            "money/m11_concentration.py",
            "money/m8_makerside.py",
            "money/m4_realizedpnl.py",
            "money/m7_size.py",
            "money/sensitivity_rollup.py",
            # Claimed on 2026-08-30. Until then no entry point reached it,
            # so no command a reader is told to run recomputed it. Placed by
            # SUBJECT, not by directory: it draws the decile economics this group computes.
            "money/m9_decile_economics_figure.py",
        ),
        "unschedulable": (),
    },
    {
        "id": "controls",
        "step": "7, the controls and probes",
        "question": "whether each result is explained by something other than what it "
                    "is claimed to be explained by",
        "predicate": "the node puts the measurement where the right answer is known "
                     "before the run -- a planted signal, a permuted label, a class of "
                     "trades that should carry no information -- or it answers one "
                     "named objection to another group's result. None of them produces "
                     "a headline number of the study's own. Until 2026-08-05 the "
                     "membership was exactly probes/, and that sentence stood here as "
                     "part of the predicate; it was a description of who happened to be "
                     "in the group and not a property of the argument, so a control "
                     "that lives beside the producers it audits rather than under "
                     "probes/ was refuted by its own filing. Fourteen of the fifteen "
                     "still live under probes/; survivorship_census.py sits at the top "
                     "level because it re-implements five admission expressions "
                     "belonging to five different groups and is a probe of no single "
                     "one of them",
        "entry": "run/controls.py",
        "nodes": (
            "probes/survivorship_census.py",
            "probes/c2_bookstate_control.py",
            "probes/c_matched_precision.py",
            "probes/calib_print_vs_mid.py",
            "probes/connected_set_b1.py",
            "probes/decay_curve.py",
            "probes/eb_scoring.py",
            "probes/kss_decomp_c.py",
            "probes/kss_decomp_c_bookmid.py",
            "probes/persistence_crosswindow.py",
            "probes/probe_D_funding.py",
            "probes/probe_E_leadlag.py",
            "probes/probe_E_lag_resolution.py",
            "probes/probe_F_hlp_liq.py",
            "probes/probe_G_horizon.py",
            # Claimed on 2026-08-30. Until then no entry point reached them,
            # so no command a reader is told to run recomputed them. Placed by
            # SUBJECT, not by directory: both are controls on the published result.
            "probes/decile_overlap.py",
            "probes/flat_surcharge_control.py",
        ),
        "unschedulable": (
            ("probes/probe_D_pull.py",
             "it fetches the funding-clock inputs the funding probe needs and writes "
             "them as parquet under the data directory, which .gitignore does not keep, "
             "so build.py holds no node for it"),
        ),
    },
    {
        "id": "notebook",
        "step": "8, the build and the repository",
        "question": "what the reproducibility notebook downloads and what it asserts "
                    "against, so that a reader with no archive access and no repository "
                    "beside them recomputes the reported numbers and is told, per "
                    "number, whether it came out the same",
        # WHY THESE TWO ARE NOT IN THE DATA GROUP, WHICH IS WHERE THEY LOOK LIKE THEY
        # BELONG. They build files, and the data group is the group that builds files, so
        # they sat there first. Then the plan gave the answer: asking for the data group
        # scheduled seventeen nodes across five groups, because make_notebook_data.py
        # reads the committed results of nearly every other group in order to write the
        # notebook's assert targets. It is not the front of the pipeline, it is the end
        # of it, and putting it at the front made the cheapest group in the tree look
        # like the most expensive.
        "predicate": "the node writes something the reproducibility notebook consumes: "
                     "the per-fill file it downloads, or the expectations it asserts "
                     "against. Everything here runs after the group whose numbers it "
                     "copies, not before it",
        "entry": "run/notebook.py",
        "nodes": (
            "notebook_build/make_notebook_fills.py",
            "notebook_build/make_notebook_book.py",
            "notebook_build/make_notebook_data.py",
        ),
        "unschedulable": (),
    },
    {
        "id": "gates",
        "step": "7, the other half: the gates",
        "question": "whether the raw parse is right byte for byte, and whether the "
                    "repository still holds against its own rules",
        "predicate": "the node re-derives a field of the raw archive independently of "
                     "the project parser, or it enforces a rule of this repository "
                     "against the repository itself. In the tree they are exactly "
                     "checks/",
        # THE ONE GROUP THAT DOES NOT RECOMPUTE THROUGH THE BUILD, and the reason is
        # what a gate is. Every other group's result is a quantity, and a quantity whose
        # producer and inputs are unchanged is still the same quantity, so skipping it
        # is right. A gate's result is a verdict about the tree AS IT STANDS NOW, and a
        # verdict carried forward because nothing the build can hash has moved is a
        # verdict about a tree nobody looked at. So this group runs its checks every
        # time, through the runner that already registers them in three groups by what
        # each one needs -- network, raw archive, or nothing at all -- which is a
        # distinction the build graph does not hold and should not.
        #
        # That runner is therefore this group's entry point, and run/gates.py is a view
        # onto it rather than a second one. The list of checks lives there and only
        # there; gates_registry_agrees() below puts the membership written above against
        # it on every census, because two lists of one thing is how a census of this
        # tree once returned two different counts for a single property.
        "entry": "run/gates.py",
        "runner": "checks/run_all_checks.py",
        "nodes": (
            "checks/chk_academic_header.py",
            "checks/chk_artifact_provenance.py",
            "checks/chk_book_orientation.py",
            # Added 2026-08-29, and it is the third time the census has caught this
            # table one entry behind the runner. The gate wraps build.py's own
            # self-diagnosis, which the battery had no way of reaching before it
            # existed: the command README.md hands a newcomer exits non-zero, and
            # nothing in the battery said so.
            "checks/chk_build_selftest.py",
            "checks/chk_closedpnl.py",
            "checks/chk_contrast_hygiene.py",
            # Added 2026-08-05. Asks whether the late half of the window reaches a
            # decision the study takes on the early half. The neighbouring
            # chk_join_nolookahead answers a narrower question -- the price join inside
            # one fill -- on seven hand-built fixtures and no tree file, so nothing
            # watched the eligibility masks, the tuned cutoffs or the whole-window
            # constants until now.
            "checks/chk_decision_lookahead.py",
            "checks/chk_dir_vs_startpos.py",
            "checks/chk_expensive_edits.py",
            "checks/chk_field_hygiene.py",
            "checks/chk_headline_horizon.py",
            "checks/chk_input_freshness.py",
            "checks/chk_join_nolookahead.py",
            "checks/chk_liquidation_field.py",
            "checks/chk_maker_attribution.py",
            # Scheduled from 2026-08-05. It sat in "unschedulable" below on the ground
            # that it wrote no results file of its own, which was true and was itself
            # the defect: the shared reporter printed "full records -> ..." naming a
            # file it never wrote, so the promise read as kept while nothing held the
            # records. The reporter now writes that file through artifact.py, so the
            # gate has an artifact carrying its producer, inputs, scope and run, and
            # build.py can hold a node for it like any other.
            "checks/chk_no_abs_paths.py",
            # Added 2026-08-06, in the same move that registered it with the battery.
            # Registering a gate in one of the two lists and not the other is what the
            # census below exists to catch, and on the day this entry was missing the
            # census caught it: the runner knew the gate and this table did not, so
            # neither count of gates could be used.
            "checks/chk_notebook_expectations.py",
            # Added 2026-08-12, and the census caught this one the same way it caught
            # the entry above: the runner registered the gate, this table did not, and
            # the census said so while still exiting zero. It asks the next question of
            # the notebook after the one above -- whether the table of figures the
            # notebook says it cannot rebuild names any that it does rebuild.
            "checks/chk_notebook_pointer_table.py",
            # Both added 2026-08-29, in the same move as chk_build_selftest further up,
            # and both are legs of the question chk_artifact_provenance asks first. That
            # gate compares a recorded producer hash against the script on disk;
            # chk_producer_committed asks whether the recorded end exists at all, and
            # chk_pinned_versions asks whether the environment a run happened in is the
            # one requirements.txt declares. Both were registered with the runner -- on
            # 2026-08-21 and 2026-08-28 -- and neither was written here, so the census
            # could report no count of gates that both sides would stand behind.
            "checks/chk_pinned_versions.py",
            "checks/chk_producer_committed.py",
            "checks/chk_prose_numbers.py",
            "checks/chk_requirements_census.py",
            "checks/chk_rowcounts_determinism.py",
            "checks/chk_run_happened.py",
            "checks/chk_settings_home.py",
            "checks/chk_side_signconv.py",
            "checks/run_all_checks.py",
        ),
        "unschedulable": (),
    },
)

# Scripts that belong to no group because they answer no question: they are imported by
# the scripts that do. Listed rather than left implicit, so that census() can say
# "unassigned" about a producer and mean it, instead of printing six modules every run
# that a reader then has to learn to ignore.
INFRASTRUCTURE = (
    "settings.py",
    "stats.py",
    "artifact.py",
    "panel_io.py",
    "build.py",
    "build_declarations.py",
    "checks/evidence.py",
)


def group(group_id):
    """The one group with this id, or a SystemExit naming the ids that exist."""
    for entry in GROUPS:
        if entry["id"] == group_id:
            return entry
    raise SystemExit(
        f"no pipeline group is called {group_id!r}. The groups are: "
        + ", ".join(g["id"] for g in GROUPS))


def owner_of(node_key):
    """The group that claims this node key, or None."""
    for entry in GROUPS:
        if node_key in entry["nodes"]:
            return entry
    return None


# =====================================================================
# 2. THE TABLE AGAINST THE GRAPH
# =====================================================================

def gates_registry_agrees():
    """The gates group's membership, against the runner's own registry of checks.

    The gates are the one group whose members are already enumerated somewhere else:
    checks/run_all_checks.py registers each check under a name and a group, and that
    registry is what decides what runs. The table above repeats those file names so that
    the census can speak about the gates in the same terms as about every other group --
    and a repeat is a second home for a fact, which is the failure this repository has
    already paid for once. So the two are compared here on every census, as sets of
    script paths, and the difference is printed in both directions.

    Returns None when the runner cannot be imported at all, which is itself the answer:
    the cross-check is not available and the census says so rather than passing quietly.
    """
    checks_dir = os.path.join(ROOT, "checks")
    if checks_dir not in sys.path:
        sys.path.insert(0, checks_dir)
    try:
        import run_all_checks
    except ImportError as exc:
        return {"available": False, "why": str(exc)}
    registered = {f"checks/{script}" for _n, script, _w in run_all_checks.ALL_GROUPS}
    # The runner itself is a node of the graph and a member of the group, and it does
    # not register itself, so it is added on the registry side rather than removed on
    # the table side: a reader asking what the gates group holds has to be told about
    # the file that runs it.
    registered.add("checks/run_all_checks.py")
    # Both halves of the table's membership, not only the schedulable half. A gate that
    # writes no tracked results file of its own is still a member of this group by the
    # same predicate: the runner registers it and it runs. Comparing against `nodes`
    # alone made such a gate look like a disagreement between the table and the runner,
    # which it is not -- the disagreement it reported was with build.py's graph, and
    # that question is asked and answered separately, by the unschedulable list itself.
    g = group("gates")
    listed = set(g["nodes"]) | {name for name, _why in g["unschedulable"]}
    return {
        "available": True,
        "registered_by_the_runner": len(registered),
        "listed_in_this_table": len(listed),
        "registered_but_not_listed": sorted(registered - listed),
        "listed_but_not_registered": sorted(listed - registered),
    }


# =====================================================================
# WHAT THE CENSUS REFUSES, AND WHAT IT ONLY OWES
#
# Until 2026-08-29 the census printed every one of its findings and returned zero
# whatever it found. A disagreement between this table and the runner's own registry
# was on the screen for fourteen days under a line that reads like an all-clear, and
# nobody read it. That is the one direction of measuring error this repository treats
# as dangerous: a false alarm stops the work and costs nothing, an instrument that
# reports success where there is none travels.
#
# So the findings are sorted into two kinds, and the difference is not their severity
# but whether a number can be held against them.
#
# A REFUSAL is a self-contradiction. The table and the runner disagree about which
# gates exist; the table names a node the graph does not hold; two groups claim one
# node; the cross-check could not be made at all. In each case one of two documents is
# wrong and neither count can be used until it is known which, so no count is worth
# printing and the command says so with its exit code.
#
# A DEBT is a coverage gap with a size. A producer node no group claims is still a real
# node computing a real number; nothing about the table is wrong, it is merely
# incomplete, and turning the census red for it would make the command useless on the
# day it is most needed. What such a gap needs instead is a ceiling, and the ceiling
# needs a date and a rule. Both are below.
#
# THE CEILINGS BELOW MAY ONLY EVER BE LOWERED, and the case that earned them happened
# on the day they were written: an edit to a shared module in checks/ made the build
# read that module as the producer of four files that exist only inside a temporary
# directory, and the count of unclaimed nodes went from 14 to 15. The census printed
# the new name and exited zero. A ceiling turns that into a stop.
#
# LOWERED ON 2026-08-30, from 14 to 3, after eleven of the fourteen were claimed. Seven
# of the eleven draw a figure the report carries, so until that day no command a reader
# is told to run redrew a picture that reaches the reader. The three that remain are of
# one kind: they describe the repository rather than compute a number from the data.
# The move is one way by the rule stated above.
UNASSIGNED_CEILING = 3
UNACCOUNTED_CEILING = 6
CEILINGS_SET_ON = "2026-08-30"


def census_refusals(report):
    """The findings that make a census exit non-zero, one sentence each.

    Read out of the report the census itself returns rather than recomputed here, so
    that this function cannot drift away from the thing it judges: a guard that
    reprints a rule goes blind to the rule changing, and this repository has lost two
    instruments to exactly that.
    """
    refusals = []
    agree = report["gates_against_their_own_runner"]
    if not agree.get("available"):
        refusals.append(
            "the gates could not be compared against their own runner: "
            + agree.get("why", "no reason given"))
    elif agree["registered_but_not_listed"] or agree["listed_but_not_registered"]:
        refusals.append(
            f"the gates table and the gates runner disagree about "
            f"{len(agree['registered_but_not_listed']) + len(agree['listed_but_not_registered'])} "
            f"file(s), so one of them is wrong and neither count can be used until it "
            f"is known which")
    if report["stale"]:
        refusals.append(
            f"{len(report['stale'])} group entr(y/ies) name a node the graph does not "
            f"hold, so that entry point plans fewer nodes than its table says")
    if report["duplicate"]:
        refusals.append(
            f"{len(report['duplicate'])} node(s) are claimed by two groups, so two "
            f"entry points would each recompute them and each report them as theirs")
    return refusals


def census_debts(report):
    """The coverage gaps and their ceilings, as (label, today, ceiling) triples."""
    return [
        ("producer nodes no group claims", len(report["unassigned"]),
         UNASSIGNED_CEILING),
        ("scripts with no node and no group",
         len(report["scripts_with_no_node_and_no_group"]), UNACCOUNTED_CEILING),
    ]


def census_verdict(report):
    """(exit code, the sentences that explain it) for one census report."""
    reasons = list(census_refusals(report))
    reasons += [f"{label}: {today}, which is {today - ceiling} more than the ceiling "
                f"of {ceiling} declared on {CEILINGS_SET_ON}"
                for label, today, ceiling in census_debts(report) if today > ceiling]
    return (1 if reasons else 0), reasons


def _selftest_census_verdict():
    """Two opposite cases for the rule above, on reports built to order.

    The pair is not decoration. The rule it guards decides an exit code, and an exit
    code nobody has watched change is indistinguishable from the one this command
    returned unconditionally until today. One reference point could not tell a rule
    that refuses everything from one that refuses nothing, so both arms are here, and
    the arms differ in one field at a time.

    Built in memory. A calibration anchored on a live finding empties itself the day
    that finding is repaired, and this repository has already lost two instruments that
    way.
    """
    clean = {
        "unassigned": ["a"] * UNASSIGNED_CEILING,
        "stale": [],
        "duplicate": [],
        "scripts_with_no_node_and_no_group": ["b"] * UNACCOUNTED_CEILING,
        "gates_against_their_own_runner": {
            "available": True, "registered_but_not_listed": [],
            "listed_but_not_registered": []},
    }
    failures = []

    def expect(label, holds, saw):
        if not holds:
            failures.append(f"{label} -- {saw}")

    code, why = census_verdict(clean)
    expect("MUST STAY SILENT: a table that agrees with its runner and sits at its "
           "declared ceilings exits zero", code == 0, f"exited {code}: {why}")

    disagreeing = dict(clean, gates_against_their_own_runner=dict(
        clean["gates_against_their_own_runner"],
        registered_but_not_listed=["checks/chk_invented.py"]))
    code, why = census_verdict(disagreeing)
    expect("MUST FIRE: one gate registered by the runner and absent from the table "
           "exits non-zero", code == 1, f"exited {code}: {why}")

    unavailable = dict(clean, gates_against_their_own_runner={
        "available": False, "why": "the runner could not be imported"})
    code, why = census_verdict(unavailable)
    expect("MUST FIRE: a cross-check that could not be made at all is not a "
           "cross-check that passed", code == 1, f"exited {code}: {why}")

    for field in ("stale", "duplicate"):
        code, why = census_verdict(dict(clean, **{field: ["one"]}))
        expect(f"MUST FIRE: a single {field} entry exits non-zero",
               code == 1, f"exited {code}: {why}")

    grown = dict(clean, unassigned=["a"] * (UNASSIGNED_CEILING + 1))
    code, why = census_verdict(grown)
    expect("MUST FIRE: one unclaimed node above the ceiling exits non-zero, which is "
           "the case measured on 2026-08-29 and printed under an all-clear",
           code == 1, f"exited {code}: {why}")

    shrunk = dict(clean, unassigned=["a"] * (UNASSIGNED_CEILING - 1))
    code, why = census_verdict(shrunk)
    expect("MUST STAY SILENT: a debt BELOW its ceiling is progress and not a fault",
           code == 0, f"exited {code}: {why}")

    grown2 = dict(clean, scripts_with_no_node_and_no_group=["b"] * (UNACCOUNTED_CEILING + 1))
    code, why = census_verdict(grown2)
    expect("MUST FIRE: the second ceiling is held too, and not only the first",
           code == 1, f"exited {code}: {why}")
    return failures


def census(graph_=None):
    """Put the table above against the graph build.py derives, and report the gaps.

    Three failures are possible and each has happened to a hand-kept list in this
    repository, which is why none of them is left to the eye:

      unassigned  the graph holds a producer node no group claims. Nobody's entry point
                  recomputes it, so it is invisible to every command a reader is told
                  to run.
      stale       a group names a node key the graph does not hold. Usually a rename or
                  a declared arm that moved; the entry point then quietly plans one
                  node fewer than it says it does.
      duplicate   two groups claim one node. Both entry points would recompute it and
                  both would report it as theirs.

    The counts are returned rather than printed, so that the same function answers the
    question for a reader and for a program.
    """
    graph_ = graph_ or build.graph()
    in_graph = set(graph_.nodes)

    claimed, duplicate = {}, []
    for entry in GROUPS:
        for key in entry["nodes"]:
            if key in claimed:
                duplicate.append({"node": key,
                                  "claimed_by": [claimed[key], entry["id"]]})
            else:
                claimed[key] = entry["id"]

    unassigned = sorted(in_graph - set(claimed))
    stale = sorted(key for key in claimed if key not in in_graph)

    # Scripts the graph scanned and holds no node for, minus the ones a group has
    # already named as unschedulable and minus the shared modules. What is left is a
    # script nobody has accounted for at all.
    named_unschedulable = {rel for entry in GROUPS
                           for rel, _why in entry["unschedulable"]}
    producing = {node.script for node in graph_.nodes.values()}
    # The entry points themselves are not members of any group: they are how a group is
    # named. The exclusion is DERIVED from where this module sits rather than typed as a
    # list, so an entry point added later is covered without anyone remembering to add
    # it, and an entry point that starts writing an artifact becomes a node and shows up
    # as unassigned instead of being hidden here.
    here = os.path.basename(HERE)
    entry_points = {rel for rel in graph_.scanned
                    if os.path.dirname(rel) == here}
    unaccounted = sorted(set(graph_.scanned) - producing - named_unschedulable
                         - set(INFRASTRUCTURE) - entry_points)

    return {
        "groups": len(GROUPS),
        "nodes_in_the_graph": len(in_graph),
        "nodes_claimed": len(claimed),
        "unassigned": unassigned,
        "stale": stale,
        "duplicate": duplicate,
        "scripts_with_no_node_and_no_group": unaccounted,
        "gates_against_their_own_runner": gates_registry_agrees(),
        "by_group": {entry["id"]: sorted(entry["nodes"]) for entry in GROUPS},
    }


def print_census(report):
    print("=" * 78)
    print("  THE PIPELINE GROUPS, AGAINST THE GRAPH build.py DERIVES")
    print("=" * 78)
    print(f"  {report['groups']} groups claim {report['nodes_claimed']} of the "
          f"{report['nodes_in_the_graph']} producer nodes in the graph")
    print()
    for entry in GROUPS:
        print(f"  {entry['id']:12s} {len(entry['nodes']):3d} nodes   "
              f"step {entry['step']}")
        print(f"  {'':12s}     run: {entry['entry']}")
        for rel, why in entry["unschedulable"]:
            print(f"  {'':12s}     no node: {rel} -- {why[:88]}")
    for found, none_found, key, meaning in (
            ("NODES NO GROUP CLAIMS", "every node in the graph is claimed by a group",
             "unassigned",
             "no entry point recomputes them, so no command a reader is told to run "
             "reaches them"),
            ("GROUP ENTRIES THE GRAPH DOES NOT HOLD",
             "every node this table names is a node of the graph", "stale",
             "each entry point plans one node fewer than its table says"),
            ("SCRIPTS WITH NO NODE AND NO GROUP",
             "every script the graph scanned is a producer, a named member, or shared "
             "infrastructure", "scripts_with_no_node_and_no_group",
             "build.py can see no artifact they write and no group has named them")):
        rows = report[key]
        print()
        if rows:
            print(f"  {found}: {len(rows)}. {meaning.capitalize()}")
            for row in rows:
                print(f"      {row}")
        else:
            print(f"  {none_found}")
    print()
    agree = report["gates_against_their_own_runner"]
    if not agree.get("available"):
        print("  THE GATES COULD NOT BE COMPARED against their own runner: "
              + agree.get("why", ""))
    elif agree["registered_but_not_listed"] or agree["listed_but_not_registered"]:
        print("  THE GATES TABLE AND THE GATES RUNNER DISAGREE, so one of them is "
              "wrong and neither count can be used until it is known which")
        for row in agree["registered_but_not_listed"]:
            print(f"      registered by checks/run_all_checks.py, absent here: {row}")
        for row in agree["listed_but_not_registered"]:
            print(f"      listed here, not registered by the runner: {row}")
    else:
        print(f"  the {agree['listed_in_this_table']} gates listed here are exactly the "
              "ones checks/run_all_checks.py registers")

    print()
    if report["duplicate"]:
        print(f"  ONE NODE CLAIMED TWICE: {len(report['duplicate'])}. Two entry points "
              "would each recompute it and each report it as theirs")
        for row in report["duplicate"]:
            print(f"      {row['node']}  claimed by {', '.join(row['claimed_by'])}")
    else:
        print("  every claimed node is claimed by exactly one group")


# =====================================================================
# 3. WHAT A GROUP HOLDS
# =====================================================================

def print_members(entry, graph_):
    print("=" * 78)
    print(f"  GROUP {entry['id'].upper()} -- step {entry['step']}")
    print("=" * 78)
    print(f"  The question: {entry['question']}.")
    print()
    print(f"  Who belongs here: {entry['predicate']}.")
    print()
    print(f"  {len(entry['nodes'])} nodes. The runtime is the longest any of the node's "
          "own outputs recorded")
    for key in entry["nodes"]:
        node = graph_.nodes.get(key)
        if node is None:
            print(f"    {key:46s} NOT IN THE GRAPH -- this table entry is stale")
            continue
        seconds = build.recorded_runtime(node)
        cost = f"{seconds:9.1f} s" if seconds else "unrecorded"
        bare = "  reads its command line" if node.facts.takes_argv else ""
        print(f"    {key:46s} [{node.stage:8s}] {cost:>11s}{bare}")
        print(f"    {'':46s}  writes {', '.join(node.outputs)}")
    if entry["unschedulable"]:
        print()
        print("  IN THIS GROUP AND NOT RUNNABLE FROM HERE. build.py holds no node for "
              "these, so nothing below can plan them or tell whether they are current")
        for rel, why in entry["unschedulable"]:
            print(f"    {rel}")
            print(f"        {why}")


# =====================================================================
# 4. THE PLAN AND ITS PRICE
# =====================================================================

def plan_for(entry, targets, graph_):
    """build.py's plan for this group, or for the named targets inside it.

    The targets are the group's own node keys, so the plan build.py returns also holds
    everything those nodes read, transitively, however far outside this group it sits.
    That is the honest answer and not an accident of the call: recomputing the money
    group after the archive parse moved does have to re-walk the archive, and a plan
    that hid the walk would price the group at seconds and then take hours.
    """
    wanted = list(targets) if targets else list(entry["nodes"])
    return build.plan(targets=wanted, graph_=graph_)


def _plural(count, one, many):
    """The word that agrees with a count. A plan of one node is a common case here."""
    return one if count == 1 else many


def price(entries, graph_):
    """The plan's cost, and how much of the plan the cost covers."""
    known = [e["known_runtime_s"] for e in entries if e["known_runtime_s"]]
    tape = [e for e in entries if e["stage"] == "tape"]
    refused = [e for e in entries
               if graph_.nodes[e["node"]].facts.takes_argv]
    return {
        "nodes_planned": len(entries),
        "nodes_with_a_recorded_runtime": len(known),
        "recorded_seconds": round(sum(known), 1),
        "tape_nodes": len(tape),
        "nodes_the_build_will_not_launch_bare": len(refused),
        "refused": [e["node"] for e in refused],
    }


def print_plan(entry, entries, graph_, targets):
    what = ("the whole group" if not targets
            else "the named targets and everything they read: "
                 + ", ".join(targets))
    print("=" * 78)
    print(f"  GROUP {entry['id'].upper()} -- step {entry['step']}")
    print("=" * 78)
    print(f"  Asked for: {what}.")
    print(f"  {entry['question'].capitalize()}.")
    print()

    if not entries:
        print("  NOTHING HAS TO RUN. Every node of this group is provably up to date: "
              "its producer hash, every input hash and every setting its stage depends "
              "on still hold.")
        return price(entries, graph_)

    cost = price(entries, graph_)
    silent = cost["nodes_planned"] - cost["nodes_with_a_recorded_runtime"]
    print(f"  THE PRICE, BEFORE ANYTHING RUNS. {cost['nodes_planned']} "
          f"{_plural(cost['nodes_planned'], 'node is', 'nodes are')} planned. "
          f"{cost['nodes_with_a_recorded_runtime']} of them recorded what they cost")
    print(f"  last time, and those come to {cost['recorded_seconds']:.0f} s. The "
          f"remaining {silent} {_plural(silent, 'has', 'have')} never recorded a "
          "runtime, so the")
    print("  total above is a floor and not an estimate of the whole plan.")
    if cost["tape_nodes"]:
        guard = build.disk_guard("tape")
        print()
        print(f"  {cost['tape_nodes']} of them {_plural(cost['tape_nodes'], 'walks', 'walk')} "
              "the raw archive. Those are hours each, they are scheduled")
        print(f"  one at a time, and the volume has {guard['free_gb']} GB free against "
              f"the {guard['allowance_gb']} GB one walk is required to find.")
    if cost["refused"]:
        count = len(cost["refused"])
        print()
        print(f"  {count} of the planned nodes "
              f"{_plural(count, 'reads its own', 'read their own')} command line, and "
              "build.py declines to")
        print("  launch such a node bare, because a bare run records whichever arm the "
              "script falls back")
        print("  to under the name of the result. Each has to be named with --only and "
              "given its options")
        print("  with --argv.")
    print()
    print("  WHAT WOULD RUN, in the order it would run. The group in brackets is the "
          "group that owns")
    print("  the node; anything other than this one is upstream this group depends on.")
    for state in entries:
        node = graph_.nodes[state["node"]]
        seconds = state["known_runtime_s"]
        cost_text = f"{seconds:.0f} s last time" if seconds else "cost unrecorded"
        home = owner_of(state["node"])
        home_text = home["id"] if home else "unassigned"
        print(f"\n    {state['node']}")
        print(f"        [{home_text}, {state['stage']}, {state['verdict']}, "
              f"{cost_text}]"
              + ("  reads its command line" if node.facts.takes_argv else ""))
        for reason in state["reasons"][:3]:
            print(f"        RUN   {reason['output']}: {reason['why']}")
        for gap in state["unknown"][:2]:
            print(f"        ?     {gap['output']}: {gap['why']}")
    return cost


# =====================================================================
# 5. THE COMMAND LINE
# =====================================================================

def _resolve_inside(entry, targets, graph_):
    """The targets, checked to be nodes of THIS group, with the owner named if not.

    A per-group entry point that quietly recomputed another group's node would make the
    grouping decorative. So a target that resolves outside the group is refused here and
    the group that owns it is named, which is the answer the caller actually needs.
    """
    keys = []
    for text in targets:
        for node in build.resolve_target(text, graph_):
            if node.key in entry["nodes"]:
                keys.append(node.key)
                continue
            home = owner_of(node.key)
            raise SystemExit(
                f"{text!r} resolves to the node {node.key}, which group "
                f"{entry['id']} does not hold. "
                + (f"It belongs to group {home['id']}: run {home['entry']} --only "
                   f"{text}" if home else
                   "No group holds it either, which --census reports as unassigned."))
    return keys


def main(group_id, argv=None):
    entry = group(group_id)
    parser = argparse.ArgumentParser(
        prog=entry["entry"],
        description=f"Pipeline group {entry['id']} (step {entry['step']}): "
                    f"{entry['question']}.")
    parser.add_argument("--run", action="store_true",
                        help="run the plan. Without this flag the plan and its price "
                             "are printed and nothing is computed")
    parser.add_argument("--only", action="append", default=[], metavar="NAME",
                        help="one node of this group, one artifact it writes, or "
                             "artifact:key.path for a single quantity. Repeatable. "
                             "Everything the target reads comes with it")
    parser.add_argument("--members", action="store_true",
                        help="what this group holds, why each node is in it, and what "
                             "it cannot schedule")
    parser.add_argument("--census", action="store_true",
                        help="every group against the graph: what is unassigned, what "
                             "is stale, what is claimed twice")
    parser.add_argument("--argv", nargs=argparse.REMAINDER, default=[],
                        help="options passed to the producer being run. Needs --only, "
                             "because one option list cannot be right for a whole group")
    parser.add_argument("--json", action="store_true",
                        help="machine-readable output")
    args = parser.parse_args(argv)

    if args.argv and not args.only and not entry.get("runner"):
        raise SystemExit(
            "--argv passes one option list to every node it launches, which can only be "
            "right when exactly one node is launched. Name that node with --only.")
    if args.only and args.run and entry.get("runner"):
        raise SystemExit(
            f"group {entry['id']} recomputes through {entry['runner']}, which selects "
            f"what it runs with its own option. Use --argv --only NAME, where NAME is "
            f"the name that runner registers, and see {entry['runner']} for the table. "
            f"--only on its own still works here for the plan, which is a different "
            f"question: it says whether the build thinks that node is stale.")

    graph_ = build.graph()

    if args.census:
        report = census(graph_)
        # The rule that turns the report into an exit code is calibrated before it is
        # used, on every invocation rather than behind a flag. It costs nothing, and
        # the thing it guards is precisely a code nobody had watched change.
        broken = _selftest_census_verdict()
        if broken:
            print("  THE CENSUS VERDICT RULE IS NOT CALIBRATED, so no exit code it "
                  "gives means anything:")
            for line in broken:
                print(f"      {line}")
            return 2
        print(json.dumps(report, indent=2) if args.json else "", end="")
        code, reasons = census_verdict(report)
        if not args.json:
            print_census(report)
            print()
            for label, today, ceiling in census_debts(report):
                room = "at" if today == ceiling else ("under" if today < ceiling
                                                      else "OVER")
                print(f"  {label}: {today}, {room} the ceiling of {ceiling} declared "
                      f"on {CEILINGS_SET_ON}. The ceiling may only ever be lowered")
            print()
            if reasons:
                print(f"  VERDICT: FAIL - {len(reasons)} reason(s), and until they are "
                      f"settled no count above can be used")
                for line in reasons:
                    print(f"      {line}")
            else:
                print("  VERDICT: PASS - the table agrees with the graph and with the "
                      "gates runner, and both declared debts are at or under their "
                      "ceilings")
        return code

    if args.members:
        if args.json:
            print(json.dumps(
                {"id": entry["id"], "step": entry["step"],
                 "question": entry["question"], "predicate": entry["predicate"],
                 "entry": entry["entry"], "nodes": list(entry["nodes"]),
                 "unschedulable": [{"script": r, "why": w}
                                   for r, w in entry["unschedulable"]]}, indent=2))
        else:
            print_members(entry, graph_)
        return 0

    targets = _resolve_inside(entry, args.only, graph_) if args.only else []
    entries, graph_ = plan_for(entry, targets, graph_)

    if args.json and not args.run:
        print(json.dumps({"group": entry["id"], "plan": entries,
                          "price": price(entries, graph_)}, indent=2))
        return 0

    cost = print_plan(entry, entries, graph_, targets)

    if not args.run:
        print()
        print("  Nothing was computed. Add --run to run the plan above.")
        return 0

    if entry.get("runner"):
        # This group recomputes through its own runner rather than through the build,
        # for the reason written beside the group: a gate's result is a verdict about
        # the tree as it stands now, and a verdict is not a thing to skip. The plan
        # above still says which gates the build considers stale, which is a different
        # and useful question, and it is why this file prints the plan before handing
        # over.
        print()
        print("-" * 78)
        print(f"  HANDING OVER TO {entry['runner']}, which runs every gate rather than "
              "only the stale ones")
        print("-" * 78)
        proc = subprocess.run(
            ["uv", "run", "--no-project", "--with", "numpy", "python3",
             entry["runner"], *args.argv], cwd=ROOT)
        return proc.returncode

    if not entries:
        return 0

    print()
    print("-" * 78)
    print("  RUNNING THE PLAN ABOVE")
    print("-" * 78)
    payload = build.build(targets=targets or list(entry["nodes"]), argv=args.argv)
    if args.json:
        print(json.dumps({"group": entry["id"], "price": cost,
                          "ran": payload["ran"]}, indent=2))
        return 0 if all(r["verdict"] in ("OK", "DEFERRED")
                        for r in payload["ran"]) else 1
    print()
    for record in payload["ran"]:
        print(f"  {record['verdict']:12s} {record['script']}"
              + (f"  {record['seconds']} s" if "seconds" in record else "")
              + (f"  -- {record['why']}" if record.get("why") else ""))
    return 0 if all(r["verdict"] in ("OK", "DEFERRED") for r in payload["ran"]) else 1
