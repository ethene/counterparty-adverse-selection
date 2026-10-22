#!/usr/bin/env python3
"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-08-05
References: internal settings.py (split_early_late, the one home of the window cut);
ws2_hard_classifier.py and flat_surcharge_control.py (the two opposite calibration cases).

CHK - A DECISION MAY NOT BE TAKEN WITH DATA FROM AFTER IT.

WHY, BEFORE HOW. This work claims that refusing to serve wallets flagged toxic on the
early half of a ten-day window removes part of the adverse-selection cost on the late
half. The claim is a claim about a RULE, and a rule is only a rule if everything it
consumes was on the table when it fired. Put one late-half quantity into the flagging
decision and the result stops being a rule and becomes a description of a window already
observed. Nothing else in this repository asks that question of the decision layer.

WHAT WAS ALREADY GUARDED, MEASURED RATHER THAN ASSUMED. checks/chk_join_nolookahead.py
runs SEVEN sub-checks, all of them over arrays built inside that file -- its own artifact
records `population: 7 hand-built join fixtures, not market data` and an EMPTY input list.
It guards the as-of JOIN: that a markout never reads a price stamped after the moment it
is priced at. That is a different question from this one and it does not reach a single
decision site: the names ws2_hard_classifier and build_toxicity_frame appear in it zero
times, and the only tree module it touches at all is i4_midmarkout,
whose join_entry it calls. A causal join and a causal decision are two questions, and
until this file the second had no instrument.

WHAT THIS ASKS, IN WORDS, BEFORE THE MACHINERY. Four questions, each about a different
way the future gets into a decision. The first three read one module's syntax tree. The
fourth cannot: it reads where the module's inputs came from.

RULE 1 (the population). Is the set of units the decision is taken over chosen using
something only the late half knows? Requiring a wallet to have traded K times in the late
half before it may be scored at all is a requirement no live rule can impose: on the day
the flag fires, those fills have not happened. The survivors are then not a sample of the
wallets a maker faces, they are a sample of the wallets that came back.

RULE 2 (the cutoff). Is the threshold that turns a score into a decision chosen by
maximising something against the late half, and then reported as though it had been
available? A cutoff tuned on the outcome it is later scored against is the outcome
wearing a decision's clothes.

RULE 3 (the constant). Is a constant that the decision is compared with computed over the
whole window, where the decision itself is taken on the early half? A median spread over
all ten days is not knowable on day four, and a break-even line built from it is a line
drawn after the fact.

RULE 4 (the provenance). Was the value the decision reads FITTED against the days the
decision is booked on? An arm whose surcharge is a monotone function of a classifier's
probability satisfies the three rules above in silence -- measured, on a module that
resolves the cut, loads a probability and books lam * max(p_hat * mo_early, 0) on late
rows: RULE 1 zero, RULE 2 zero, RULE 3 zero, indistinguishable from an early-only
control. Every line of it is honest arithmetic on a number that is not honest here, and
what is wrong with the number is where it came from. Provenance is a property of the
artifact that produced it, so no rule reading one file can see it however carefully it
is written.

HOW THE QUESTION IS ASKED WITHOUT NAMING ANYBODY. No rule below matches a file name, a
function name or a variable name. The analysis starts from ONE thing and follows the data:
settings.split_early_late, the tree's only home for the window cut. The check CALLS that
function on a probe day range to learn which of the two tuples it returns carries the
future -- the slot is measured, never typed here -- and then propagates that label through
the syntax tree of every module, so a site is found by what it computes and not by what it
is called. Renaming every variable in a producer changes nothing this file reports.

THE CUT ALSO ARRIVES THROUGH A WRAPPER, AND UNTIL 2026-08-05 THAT MADE THE HEADLINE
PRODUCER INVISIBLE. mm_bakeoff.py never spells the settings function: it imports
maker_econ.early_late_days and unpacks that. The seed keyed on the settings call and the
blind-spot count keyed on the same call, so the file behind every published quoting
number appeared in neither list, and the gate's own measure of what it could not see did
not show it either. Wrappers are now found by BEHAVIOUR -- a static shape and purity
filter, then a CALL on a probe range whose result is measured -- so no spelling is
matched anywhere. The count moved from eleven modules with a resolved cut to eighteen,
and from eight modules reaching the cut unresolvably to three.

THE GRADE IS THE WHOLE TRICK, AND IT IS WHAT SEPARATES A DEFECT FROM THE CORRECT DESIGN.
Late data reaches an honest producer too: the late half is where the outcome is MEASURED,
so a late row mask has to touch the arithmetic somewhere or nothing would ever be scored.
So late taint is carried at two grades. ROW grade is bare membership -- these rows fall in
the late half -- and it is legitimate at the measurement step. UNIT grade is what a
REDUCTION over late rows produces: a per-wallet count, mean or cost. That is knowledge
about the future of a named counterparty, and using it to pick who gets scored, where the
cutoff sits, or what the score is compared against is the defect. flat_surcharge_control.py
is the live proof the distinction is needed: it books its offset on late rows, its early
premium is subscripted by a late mask, and it is CORRECT -- the mask it uses is row grade.
Score the two the same and either the guard fails a healthy producer or it passes a sick
one.

THE DEBT IS DECLARED BY SITE, NOT BY COUNT. Findings already known sit in DECLARED_DEBT
with a reason and a date; anything else is a regression and this gate goes red on it.
Keying the exemption to a count would let one site be fixed and another appear in silence,
so each entry names the file, the rule and the binding it excuses. An entry that matches
no site is itself a finding: either the defect was repaired, in which case the line comes
out, or the predicate stopped seeing it, which is the direction of error that travels.

CALIBRATION, RUN ON EVERY INVOCATION AND NOT ONCE WHEN THIS WAS WRITTEN. Every rule is
shown flipping its verdict on ONE edited line of a live producer, and all the cases are
files of this tree rather than fixtures. A fixture that does not look like the real node
certifies nothing: this tree has already had a predicate whose calibration passed on a
hand-built string while it read zero through the live producer it was written for. The
healthy case is flat_surcharge_control.py exactly as committed, which reaches all three
predicates and must survive them. The paired case is ws2_hard_classifier.py with ONE line
edited per rule, which proves the predicate keys on the defect and not on the file. The
one-line edits are asserted to have applied, so a producer that changes shape breaks the
calibration loudly instead of quietly certifying nothing.

THE PAIRED EDIT RUNS IN EITHER DIRECTION, AND THAT IS WHAT KEEPS THE GATE HONEST ABOUT
REPAIRS. Two rules still have a defect standing in that producer, so their edit REMOVES it
and the rule must go quiet. RULE 3's defect was repaired on 2026-08-05 -- the break-even
line is now built from an early-half median where it used to use the whole window -- so no
producer of this tree carries it, and its edit INJECTS it back instead, with the rule
required to fire on the injected defect and to read zero on the file as committed. Written
only the first way, this file would have made every repair break its own calibration, which
puts the pressure on leaving defects standing. Both directions test the same claim: that
the verdict follows the one line carrying the defect and not the name of the file.

Read-only. Stdlib plus numpy, because the battery runs without pandas or scikit-learn and
a gate that cannot run in the battery is a gate nobody runs.

    uv run --no-project --with-requirements requirements.txt python3 checks/chk_decision_lookahead.py
"""
import ast
import importlib
import json
import os
import re
import sys

import numpy                                                       # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import artifact                                                   # noqa: E402
import settings as S                                              # noqa: E402
from evidence import report_gate, shipped_tree_files              # noqa: E402
# What counts as a self-test scope is declared once in build.py and read by the I/O
# census already. Calling it rather than repeating it is the
# difference between one convention and two that drift.
import build                                                      # noqa: E402
from build import FIXTURE_SCOPES                                  # noqa: E402

OUT_NAME = "chk_decision_lookahead_results.json"
OUT_JSON = os.path.join(HERE, OUT_NAME)

# ---------------------------------------------------------------------------
# THE GRADES. Names, not magic strings scattered through the file.
# ---------------------------------------------------------------------------
LATE_ROW = "late_row"        # rows that fall in the late half; legitimate for measuring
LATE_UNIT = "late_unit"      # a REDUCTION over late rows: per-wallet future knowledge
EARLY_ROW = "early_row"
EARLY_UNIT = "early_unit"
RAW_COL = "raw_column"       # a column read straight off the panel, neither half
WHOLE_WINDOW = "whole_window"  # a reduction of a raw column with NEITHER half's mask on it

# Calls that collapse rows into per-unit or scalar statistics. A late row mask that
# passes through one of these stops being "which rows" and becomes "what this wallet did".
REDUCERS = frozenset({
    "sum", "mean", "median", "average", "quantile", "percentile", "std", "var",
    "min", "max", "prod", "bincount", "count_nonzero", "histogram", "corrcoef", "cov",
    "nanmean", "nanmedian", "nansum", "nanstd", "nanvar", "nanmin", "nanmax",
    "add", "value_counts", "groupby", "agg",
})
# np.add on its own is elementwise; only the .reduce/.at forms aggregate, and those
# arrive as an Attribute on the ufunc, which _reducer_name below resolves.
REDUCER_ATTR_ONLY = frozenset({"add"})

# Calls whose result is a boolean mask or an index array: the shape a POPULATION is
# selected with. Rule 1 asks about a selector, not about any subscript at all.
SELECTOR_CALLS = frozenset({
    "isin", "isfinite", "isnan", "isinf", "where", "nonzero", "flatnonzero", "argwhere",
    "logical_and", "logical_or", "logical_not", "logical_xor", "in1d", "greater",
    "greater_equal", "less", "less_equal", "equal", "not_equal",
})
LOADERS = frozenset({"load", "loadtxt", "genfromtxt", "read_csv", "read_parquet"})


# ---------------------------------------------------------------------------
# THE DECLARED DEBT. Each entry names a file, a rule and the binding it excuses,
# together with why it is tolerated and the date it was written down. A finding that
# matches no entry is a regression; an entry that matches no finding is reported too.
# These may only ever be REMOVED. Adding one is an edit somebody signs, on this line.
#
# REMOVED 2026-08-05: the RULE 3 entry for ws2_hard_classifier.py's `breakeven_bps`. The
# defect it excused was repaired rather than tolerated -- the median spread the break-even
# line is built from is now taken over the early half, where it used to run over the whole
# window -- so the entry stopped matching a finding and became a declaration standing over
# nothing, which this gate reports as a finding of its own. What the repair moved is
# recorded in the producer beside the line: the break-even cutoff from 0.4507 to 0.4575
# basis points, and the flagged count from 3,708 of 5,539 eligible units to 3,696.
# ---------------------------------------------------------------------------
# ADDED 2026-08-29, and signed here as this block requires: the RULE 4 entry for
# data/d1_book_shape_figure.py's `book_feats_*.npz`. It is the first entry written for a
# producer that takes NO decision, so the ground is worth separating from the twelve
# above. Those excuse a value that really does enter a choice and is tolerated anyway.
# This one excuses a day overlap in a file whose loaded values never leave two
# verification records: an equality check against the committed depth columns, which can
# only stop the run, and a degeneracy count that decides a parsing route. Everything the
# figure draws is re-parsed from the raw snapshots by the file itself. The reason below
# names both sites, so the claim can be checked by opening the artifact instead of taken
# on the word of this line.
DECLARED_DEBT = [
    {"file": "persistence/ws2_hard_classifier.py", "rule": "RULE 1", "binding": "idx",
     "date": "2026-08-05",
     "reason": (
         "the eligibility mask requires at least K fills in BOTH halves, so the three "
         "early per-wallet arrays it subsets are restricted to wallets that traded again "
         "after the flag would have fired. The file's own header says the late half is "
         "the prediction target only; the mask contradicts it. Left standing rather than "
         "repaired in place because the repair moves the eligible count and every figure "
         "downstream of it, which is a recompute and a re-reading of the register, not an "
         "edit")},
    {"file": "persistence/ws2_hard_classifier.py", "rule": "RULE 2", "binding": "thr_youden",
     "date": "2026-08-05",
     "reason": (
         "the cutoff is the argmax of true-positive minus false-positive rate over sixty "
         "candidates, scored against the late-window cost decile, and the flagged "
         "fraction reported beside it is measured at that same cutoff on that same half. "
         "The number is a fitted value, not an out-of-sample one, whatever it is called")},
    {"file": "markout/m2_figure.py", "rule": "RULE 1", "binding": "q",
     "date": "2026-08-05",
     "reason": (
         "the wallets the headline figure draws are those clearing the fill floor in BOTH "
         "halves, and the top-decile cut is taken over that survivor set. Same defect as "
         "the classifier's eligibility mask, on the figure the report leads with")},
    {"file": "markout/ws1_horizon_persistence.py", "rule": "RULE 1", "binding": "u",
     "date": "2026-08-05",
     "reason": (
         "the unit list keeps a wallet only when it clears the floor in both halves, "
         "which is unavoidable for a persistence correlation -- the quantity being "
         "measured is defined on pairs -- but it makes the population a survivor set all "
         "the same, and the artifact does not say so. Declared so that the limitation is "
         "written down rather than assumed harmless")},
    {"file": "persistence/ws3_taker_pnl.py", "rule": "RULE 1", "binding": "elig",
     "date": "2026-08-05",
     "reason": (
         "the out-of-sample leg flags on the early top decile and measures late realized "
         "profit, but the wallets it ranks are those with K fills in both halves, so the "
         "flag is taken over a set the flagging moment cannot know")},
    {"file": "data/build_toxicity_frame.py", "rule": "RULE 1",
     "binding": "w not in late_by_taker", "date": "2026-08-05",
     "reason": (
         "a counterparty with no late-half fills gets no row at all, so the feature "
         "frame this file writes is a table of wallets that came back. "
         "The frame's own leakage note covers label leakage and says nothing about this")},
    # RULE 4, ADDED 2026-08-05 WITH THE RULE ITSELF. Six sites, one of them a control
    # and five of them a census, and none of them an arm priced off the loaded value.
    # They are declared and not suppressed because the rule is the only instrument
    # standing between this study and an arm whose surcharge is a function of a fitted
    # quantity: if the debt were keyed to a count rather than to a named input, such an
    # arm would land inside the allowance and nothing would say so.
    {"file": "probes/flat_surcharge_control.py", "rule": "RULE 4",
     "binding": "mm_bakeoff_results.json", "date": "2026-08-05",
     "reason": (
         "the control reads the published delta, which mm_bakeoff.py measures on days "
         "9 to 13, and books its own offset on those same days. What it does with the "
         "loaded value is choose which of two constructions of the early premium the "
         "published number stands on, and refuse to print a residual unless one of them "
         "reproduces it. That choice is made with a quantity from the window the file "
         "reports over, and it is the point of the file rather than a defect in it: a "
         "control that has not reproduced the published number has no baseline. "
         "Declared so that the dependence is written down instead of assumed harmless")},
    {"file": "probes/survivorship_census.py", "rule": "RULE 4",
     "binding": "m2_figure_results.json", "date": "2026-08-05",
     "reason": (
         "the census prices the two-sided admission rule by reading what the producers "
         "that carry it published, so their late-half quantities are its SUBJECT and "
         "not an input to a decision it takes. Same ground as its RULE 1 entry below, "
         "and the file says so to its own artifact under deliberate_lookahead")},
    {"file": "probes/survivorship_census.py", "rule": "RULE 4",
     "binding": "toxicity_frame_results.json", "date": "2026-08-05",
     "reason": "as the m2_figure entry above: a population read to be priced, not used",
     },
    {"file": "probes/survivorship_census.py", "rule": "RULE 4",
     "binding": "ws1_horizon_results.json", "date": "2026-08-05",
     "reason": "as the m2_figure entry above: a population read to be priced, not used",
     },
    {"file": "probes/survivorship_census.py", "rule": "RULE 4",
     "binding": "ws2_hard_classifier_results.json", "date": "2026-08-05",
     "reason": "as the m2_figure entry above: a population read to be priced, not used",
     },
    {"file": "probes/survivorship_census.py", "rule": "RULE 4",
     "binding": "ws3_taker_pnl_results.json", "date": "2026-08-05",
     "reason": "as the m2_figure entry above: a population read to be priced, not used",
     },
    {"file": "data/d1_book_shape_figure.py", "rule": "RULE 4",
     "binding": "book_feats_*.npz", "date": "2026-08-29",
     "reason": (
         "this producer draws the appendix figure of the raw material and takes no "
         "decision at all, so RULE 4's premise -- that an arm is priced off a quantity "
         "fitted on the days it quotes over -- has no arm to attach to here. The days "
         "do meet: i3_book_comparator.py measures on days 9 to 13 and this module binds "
         "the same late half. What it binds it FOR is the right-hand panel, which draws "
         "the boundary between the two halves and prints each half's median quoted "
         "spread, so the reader can see that the split this study rests on does not sit "
         "on a regime break. That is a description of the window, not a booking across "
         "it, and RULE 4 cannot tell the two apart because both bind the same name. "
         "What makes this checkable rather than asserted is where the loaded values go: "
         "book_feats_{COIN}.npz is opened at exactly two sites and NEITHER of them "
         "reaches the picture. check_against_book_feats() recomputes the four depth "
         "columns from the raw levels and requires them to equal the committed artifact "
         "row by row, which can only stop the run and can never move a number; its "
         "result is recorded under against_a_committed_artifact and is not plotted. "
         "degeneracy_of_two_rungs() counts how often the two rungs of that file are "
         "equal, which is the measurement behind spending two and a half minutes on the "
         "raw snapshots instead, and it decides a parsing route rather than a "
         "counterparty, a cutoff or a price. Every series on both panels is re-parsed "
         "from the raw snapshots by this file. So no value fitted on the late half "
         "reaches any published quantity, and a reader can confirm it by opening the "
         "artifact and finding those two records and no third. The entry is keyed to "
         "this ONE input on purpose: a second fitted input read by the same file is a "
         "new finding and this line will not excuse it")},
    {"file": "probes/survivorship_census.py", "rule": "RULE 1", "binding": "elig",
     "date": "2026-08-05",
     "reason": (
         "this producer carries the admission rule as the OBJECT of a measurement rather "
         "than as the ground of a decision. Its as_committed arm rebuilds the two-sided "
         "mask on purpose, so that the price of the rule can be printed beside the two "
         "arms that relax it, and the file declares this to its own artifact under the "
         "key deliberate_lookahead. Removing the pattern would hide the very expression "
         "being priced, which is why the entry stands here instead")},
]


# ---------------------------------------------------------------------------
# LEARNING THE CUT FROM ITS OWN HOME, INSTEAD OF RETYPING IT
# ---------------------------------------------------------------------------
def probe_split():
    """Call settings.split_early_late and measure which returned slot carries the future.

    A guard that re-types the rule it guards is blind to the rule changing, and this tree
    has paid for that once already in checks/chk_join_nolookahead.py. So nothing about the
    cut is written here: the function is called on a probe range, the two tuples are
    compared, and the slot holding the larger day numbers is the late one. If the rule
    ever returns something that is not two disjoint ordered halves, this raises rather
    than guessing, because every finding below hangs off which slot means the future.
    """
    probe = tuple(range(4, 14))
    halves = S.split_early_late(probe)
    if not (isinstance(halves, tuple) and len(halves) == 2):
        raise SystemExit(
            f"settings.{S.split_early_late.__name__} returned {halves!r}; this gate "
            f"needs exactly two halves to know which one is the future")
    first, second = halves
    if not first or not second:
        raise SystemExit(
            f"settings.{S.split_early_late.__name__}({probe}) returned an empty half "
            f"{halves!r}; the probe range was chosen to give two non-empty halves")
    if set(first) & set(second):
        raise SystemExit(
            f"settings.{S.split_early_late.__name__}({probe}) returned overlapping "
            f"halves {halves!r}; a cut whose halves share a day cannot separate a "
            f"decision from its outcome")
    late_slot = 1 if max(second) > max(first) else 0
    return {"function": f"settings.{S.split_early_late.__name__}",
            "probe_days": list(probe),
            "returned": [list(first), list(second)],
            "late_slot": late_slot,
            "measured": ("the slot holding the larger day numbers is the future half; "
                         "this is read off the call, never typed in this file")}


# ---------------------------------------------------------------------------
# THE SECOND WAY THE CUT ARRIVES: A WRAPPER, FOUND BY WHAT IT DOES
# ---------------------------------------------------------------------------
# WHY THIS EXISTS, MEASURED BEFORE IT WAS WRITTEN. The artifact of 2026-08-05 listed
# eleven modules with a resolved cut and eight that reach the cut in a shape the gate
# could not follow, and mm_bakeoff.py -- the producer of every published quoting number
# in this study -- was in NEITHER list. It never spells settings.split_early_late: it
# imports maker_econ.early_late_days and unpacks that. The seed above keys on the
# settings call, and the coverage count keys on the same call, so a module reaching the
# cut one step removed was invisible to the findings AND to the count of blind spots,
# which is the worse of the two.
#
# ATTACHED TO BEHAVIOUR, NOT TO A NAME, BECAUSE THIS TREE HAS BEEN BITTEN TWICE BY
# NAME-MATCHED GUARDS. An earlier guard outside this tree compared a tool name that
# later changed, and the freshness gate compared a producer hash where the input had moved;
# both went quiet without failing. So nothing here matches "early_late_days" or any
# other spelling. A function earns the label in three stages, and the last one is a
# call rather than a reading:
#
#   SHAPE.  It reaches the declared cut -- directly or through another function that
#           already earned the label -- every one of its returns is a two-element tuple
#           or a call to something that already earned it, and it takes exactly one
#           required argument. A function returning a bool or a dict is out here, which
#           is where settings.day_split_agrees leaves: it calls the cut and returns
#           whether two tuples agree with it.
#   PURITY. Its body opens nothing, imports nothing and calls nothing outside numpy,
#           the safe builtins and the labels already earned. This is a SAFETY screen and
#           not a detection rule: the next stage calls the function, and a gate may not
#           call a function that might write. checks/chk_settings_home.py's rule5 leaves
#           here, on its call to notebook_cells.
#   CALL.   The survivors are called on a probe day range and the result is MEASURED:
#           two non-empty disjoint sequences whose union is the probe. Which slot holds
#           the future is read off the larger day numbers, exactly as probe_split does
#           for the settings function, and never typed. t1_toxicity_skew_backtest.py's
#           _early_late_masks passes both static stages and is rejected here, because
#           what it returns is two boolean masks over rows and not two day sets -- a
#           file that reaches the machinery and is stopped by what it actually does.
def _read_text(rel):
    """Read one tracked file of this tree, by repo-relative path.

    ONE READER FOR THE THREE WALKS ADDED ON 2026-08-05, and that is a decision about
    build.py rather than about style. The build's I/O census asks every disk call to
    resolve to a named artifact or to be declared, and a walk over a whole population
    can do neither. Three call sites would need three declarations for one and the same
    population; routed through here they need one.
    """
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


SAFE_BUILTINS = frozenset({
    "sorted", "set", "tuple", "list", "int", "len", "max", "min", "range", "dict",
    "abs", "sum", "enumerate", "zip", "frozenset", "bool", "float", "reversed",
    "any", "all", "str",
})
PROBE_DAYS = tuple(range(4, 14))


def _is_pure_of_days(fn, earned):
    """A cut resolver is a pure function of the days. Safety screen, not a rule."""
    for node in ast.walk(fn):
        if isinstance(node, (ast.With, ast.AsyncWith, ast.Import, ast.ImportFrom,
                             ast.Global, ast.Nonlocal)):
            return False, f"contains {type(node).__name__}"
        if isinstance(node, ast.Call):
            name = _call_name(node)
            if name in earned or name in SAFE_BUILTINS:
                continue
            if (isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id in ("np", "numpy")):
                continue
            return False, f"calls {ast.unparse(node.func)[:40]}"
    return True, ""


def _returns_two(fn, earned):
    rets = [n for n in ast.walk(fn) if isinstance(n, ast.Return)]
    if not rets:
        return False
    for ret in rets:
        value = ret.value
        if value is None:
            return False
        if isinstance(value, ast.Tuple) and len(value.elts) == 2:
            continue
        if isinstance(value, ast.Call) and _call_name(value) in earned:
            continue
        return False
    return True


def _one_required_argument(fn):
    positional = fn.args.posonlyargs + fn.args.args
    required = len(positional) - len(fn.args.defaults)
    keyword_required = sum(1 for arg, default in zip(fn.args.kwonlyargs,
                                                     fn.args.kw_defaults)
                           if default is None)
    return required == 1 and keyword_required == 0


def _shape_candidates(rel, source):
    """Functions of one module that pass SHAPE and PURITY, with the screen-outs."""
    split_fn = S.split_early_late.__name__
    if split_fn not in source:
        return [], []
    try:
        tree = ast.parse(source, filename=rel)
    except SyntaxError:
        return [], []
    local = {n.name: n for n in ast.walk(tree)
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    earned, screened = {split_fn}, []
    for _round in range(6):
        grew = False
        for name, node in sorted(local.items()):
            if name in earned:
                continue
            if not any(isinstance(c, ast.Call) and _call_name(c) in earned
                       for c in ast.walk(node)):
                continue
            if not (_returns_two(node, earned) and _one_required_argument(node)):
                continue
            pure, why = _is_pure_of_days(node, earned)
            if not pure:
                screened.append({"file": rel, "function": name, "stage": "purity",
                                 "why": why})
                continue
            earned.add(name)
            grew = True
        if not grew:
            break
    return sorted(earned - {split_fn}), screened


def cut_resolvers(rel_paths):
    """Every function of this tree that BEHAVES like the declared cut.

    Returns (confirmed, rejected). `confirmed` maps a repo-relative module path and a
    function name to the slot its result holds the future in, measured by calling it.
    """
    confirmed, rejected = {}, []
    for rel in rel_paths:
        names, screened = _shape_candidates(rel, _read_text(rel))
        rejected.extend(screened)
        if not names:
            continue
        module_name = rel[:-3].replace(os.sep, ".").replace("/", ".")
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:                                   # noqa: BLE001
            rejected.append({"file": rel, "function": "<module>", "stage": "import",
                             "why": f"{type(exc).__name__}: {exc}"[:120]})
            continue
        for name in names:
            probe = list(PROBE_DAYS)
            try:
                got = getattr(module, name)(numpy.array(probe, dtype=numpy.int64))
            except Exception as exc:                               # noqa: BLE001
                rejected.append({"file": rel, "function": name, "stage": "call",
                                 "why": f"{type(exc).__name__}: {exc}"[:120]})
                continue
            halves = _measure_halves(got, probe)
            if halves is None:
                rejected.append({"file": rel, "function": name, "stage": "call",
                                 "why": (f"returned {type(got).__name__} "
                                         f"{repr(got)[:60]}, which is not two day sets "
                                         f"partitioning the probe")})
                continue
            first, second = halves
            confirmed[(rel, name)] = {
                "late_slot": 1 if max(second) > max(first) else 0,
                "returned": [first, second],
                "probe_days": probe,
                "measured": ("called on the probe range; the slot holding the larger "
                             "day numbers is the future half, read off the call")}
    return confirmed, rejected


def _measure_halves(got, probe):
    """Two disjoint non-empty day sets covering the probe, or None."""
    if not isinstance(got, (tuple, list)) or len(got) != 2:
        return None
    try:
        first = [int(x) for x in got[0]]
        second = [int(x) for x in got[1]]
    except (TypeError, ValueError):
        return None
    if not first or not second:
        return None
    if set(first) & set(second) or set(first) | set(second) != set(probe):
        return None
    return first, second


_MODULE_PATHS = None


def module_path(dotted):
    """The repository-relative file an import names, found by looking for it.

    An import statement carries no directory: `import maker_econ as ME` says the module
    name and nothing about where it sits. While every producer sat at the top of the
    tree, spelling the dotted name with a `.py` on the end happened to BE the path, and
    the two could not be told apart. Once the producers were grouped, that spelling
    stopped resolving and every cross-module resolver went unfound -- silently, which is
    a rule going quiet rather than a rule reporting. So the name is resolved against the
    files this tree actually holds, and a name matching two of them is left alone rather
    than picked between.
    """
    global _MODULE_PATHS
    if _MODULE_PATHS is None:
        found = {}
        for rel in shipped_tree_files(ROOT):
            if rel.endswith(".py"):
                found.setdefault(os.path.basename(rel), []).append(rel)
        _MODULE_PATHS = found
    spelled = dotted.replace(".", "/") + ".py"
    hits = _MODULE_PATHS.get(os.path.basename(spelled), [])
    return hits[0] if len(hits) == 1 else spelled


def wrapper_calls_of(rel, tree, confirmed):
    """Local call names in one module that reach a confirmed resolver, with its slot.

    Three spellings, all of them resolved by following the IMPORT to the file that
    defines the function rather than by matching what the name is spelled as here:
    a local def, `from other import f as g`, and `import other` followed by
    `other.f(...)`, which _call_name flattens to `f`.
    """
    out = {}
    for (owner, name), record in confirmed.items():
        if owner == rel:
            out[name] = record["late_slot"]
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and not node.level:
            owner = module_path(node.module)
            for alias in node.names:
                record = confirmed.get((owner, alias.name))
                if record:
                    out[alias.asname or alias.name] = record["late_slot"]
        elif isinstance(node, ast.Import):
            for alias in node.names:
                owner = module_path(alias.name)
                for (holder, name), record in confirmed.items():
                    if holder == owner:
                        out.setdefault(name, record["late_slot"])
    return out


# ---------------------------------------------------------------------------
# THE ANALYSIS
# ---------------------------------------------------------------------------
def _call_name(node):
    """The last name of a called thing: np.median -> 'median', bincount -> 'bincount'."""
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _reducer_name(node):
    """True when this Call collapses rows. Handles the ufunc .reduce spelling."""
    name = _call_name(node)
    if name is None:
        return False
    if name in ("reduce", "reduceat", "at"):
        return True
    if name in REDUCER_ATTR_ONLY:
        return isinstance(node.func, ast.Attribute) and isinstance(
            node.func.value, ast.Attribute)
    return name in REDUCERS


def _fold_sites(sites, key):
    """One finding per thing that has to be REPAIRED, with every use listed under it.

    ws2_hard_classifier.py subsets three arrays with one eligibility mask on one line,
    ws1_horizon_persistence.py subsets one dictionary with one unit list in four places,
    and ws2's break-even line is compared with the score twice. Reported flat that is
    thirteen findings over five defects, and a reader cannot tell how many repairs the
    list is asking for. The uses are kept in the record rather than dropped, so nothing
    is lost by folding them; only the count changes, and it changes to the count of
    repairs.
    """
    folded = {}
    for site in sites:
        k = (site["file"], site.get("source"), key(site))
        head = folded.get(k)
        use = {"line": site["line"], "consumer": site.get("binding")}
        if head is None:
            folded[k] = dict(site, binding=key(site), uses=[use])
        else:
            head["uses"].append(use)
            head["line"] = min(head["line"], site["line"])
    for site in folded.values():
        site["n_uses"] = len(site["uses"])
    return sorted(folded.values(), key=lambda s: (s["file"], s["line"]))


def _targets(node):
    """The names a target expression binds, flattened through tuples and stars."""
    out = []
    if isinstance(node, ast.Name):
        out.append(node.id)
    elif isinstance(node, (ast.Tuple, ast.List)):
        for elt in node.elts:
            out.extend(_targets(elt))
    elif isinstance(node, ast.Starred):
        out.extend(_targets(node.value))
    return out


_COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)


def _scope_paths(tree):
    """Map every node to the tuple of scope names enclosing it.

    A tuple rather than one name, because a helper defined inside a producer reads the
    producer's locals, and a lookup that stopped at the innermost function would lose the
    grade of every name it closes over. Module level is the empty tuple.

    A COMPREHENSION IS A SCOPE, AND LEAVING IT OUT COST ONE FALSE FINDING, MEASURED
    2026-08-05. Python gives every comprehension its own namespace, so the `d` of
    `[int(d) in early_set for d in day]` and the `d` of
    `set(int(d) for d in np.unique(day[is_late]))` are two different names. Folded into
    one function-level namespace they became one, the second handed the first its late
    grade, and from there maker_econ.py's early-only eligibility mask read as
    late-derived and RULE 1 fired on a construction that is correct. This is the same
    disease the tuple-unpacking repair fixed at the statement level, one scope down.
    The synthetic name is numbered in walk order rather than by identity, so two runs
    over the same source produce the same scopes and the artifact stays byte-stable.
    """
    scope_of = {tree: ()}
    counter = [0]

    def walk(node, path):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                inner = path + (child.name,)
            elif isinstance(child, _COMPREHENSIONS):
                counter[0] += 1
                inner = path + (f"<comprehension {counter[0]}>",)
            else:
                inner = path
            scope_of[child] = inner
            walk(child, inner)

    walk(tree, ())
    return scope_of


class ModuleTaint:
    """Which names in one module carry early-half, late-half or whole-window knowledge.

    A fixpoint over every binding in the file: a name takes the union of the grades of
    the names its defining expression mentions, plus a promotion from ROW grade to UNIT
    grade whenever the expression puts that name through a reduction. Names are keyed by
    the function they live in, so that two producers' local `order` are two names; one
    flat namespace was tried first and it smeared every grade onto every name, which
    destroys the one distinction the whole gate rests on.
    """

    def __init__(self, source, filename, late_slot, wrappers=None):
        self.filename = filename
        self.tree = ast.parse(source, filename=filename)
        self.scope_of = _scope_paths(self.tree)
        self.late_slot = late_slot
        # Local call names that reach a function MEASURED to resolve the cut, each
        # with the slot that call was measured to return the future in. Empty when the
        # caller has not run the discovery, which keeps every existing call site of
        # this class working unchanged.
        self.wrappers = dict(wrappers or {})
        self.taint = {}              # (scope path, name) -> set of grades
        self.selectors = set()       # (scope path, name) for masks and index arrays
        self.stores = set()          # (scope path, name) for a loaded panel
        self.functions = {}          # local def name -> node
        self.reducing = set()        # local defs that aggregate rows
        self.split_sites = []        # how the cut was resolved, for the record
        self._collect_functions()
        self._seed()
        if self.split_sites:
            self._bind_cache = self._bindings()
            self._fixpoint()
        else:
            self._bind_cache = []

    # -- lookups ----------------------------------------------------------
    def read(self, scope, name):
        """Grades of `name` as seen from `scope`: the name itself and every enclosing one."""
        out = set()
        for depth in range(len(scope), -1, -1):
            out |= self.taint.get((scope[:depth], name), set())
        return out

    def is_selector(self, scope, name):
        return any((scope[:d], name) in self.selectors
                   for d in range(len(scope), -1, -1))

    def is_store(self, scope, name):
        return any((scope[:d], name) in self.stores
                   for d in range(len(scope), -1, -1))

    # -- setup ------------------------------------------------------------
    def _collect_functions(self):
        for node in ast.walk(self.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.functions.setdefault(node.name, node)
        changed = True
        while changed:
            changed = False
            for name, node in self.functions.items():
                if name in self.reducing:
                    continue
                for call in ast.walk(node):
                    if isinstance(call, ast.Call) and (
                            _reducer_name(call) or _call_name(call) in self.reducing):
                        self.reducing.add(name)
                        changed = True
                        break

    def _seed(self):
        """Find where the future enters the module, in the two forms this tree uses.

        FORM A is the declared one: a call to the settings function, unpacked into two
        names. FORM B is a module that cuts the sorted day list itself, tail slice late;
        build_toxicity_frame.py does exactly that, so a guard anchored only on form A
        would be blind to the feature frame and everything that reads it. FORM C is the cut arriving
        through a WRAPPER, which is how mm_bakeoff.py gets it and why that file was in
        neither the covered list nor the blind-spot list until 2026-08-05. The wrapper
        is identified by cut_resolvers above, which calls it, and the slot carrying the
        future comes from that call rather than from this module's local slot.
        """
        split_fn = S.split_early_late.__name__
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.Assign) or not node.targets:
                continue
            targets = _targets(node.targets[0])
            scope = self.scope_of.get(node, ())
            if len(targets) == 2:
                if isinstance(node.value, ast.Call) and _call_name(node.value) == split_fn:
                    self._mark_halves(targets, node, scope, "settings call")
                    continue
                if isinstance(node.value, ast.Call) and _call_name(
                        node.value) in self.wrappers:
                    called = _call_name(node.value)
                    self._mark_halves(
                        targets, node, scope,
                        f"wrapper measured to resolve the cut: {called}",
                        late_slot=self.wrappers[called])
                    continue
                if isinstance(node.value, ast.Tuple) and len(node.value.elts) == 2:
                    sliced = [self._slice_of(e) for e in node.value.elts]
                    if all(sliced) and sliced[0][0] == sliced[1][0]:
                        heads = [s[1] for s in sliced]
                        if heads.count("head") == 1 and heads.count("tail") == 1:
                            first_is_head = heads[0] == "head"
                            ordered = (targets if first_is_head
                                       else [targets[1], targets[0]])
                            self._mark_halves(ordered, node, scope,
                                              "own tail slice of the sorted days",
                                              late_slot=1)
                            continue
            if isinstance(node.value, ast.Call) and _call_name(node.value) in LOADERS:
                for name in targets:
                    self.stores.add((scope, name))

    @staticmethod
    def _slice_of(node):
        """(base name, 'head'|'tail') for x[:k] and x[k:], else None."""
        if not (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name)):
            return None
        sl = node.slice
        if not isinstance(sl, ast.Slice) or sl.step is not None:
            return None
        if sl.lower is None and sl.upper is not None:
            return (node.value.id, "head")
        if sl.lower is not None and sl.upper is None:
            return (node.value.id, "tail")
        return None

    def _mark_halves(self, targets, node, scope, how, late_slot=None):
        slot = self.late_slot if late_slot is None else late_slot
        early_name, late_name = targets[1 - slot], targets[slot]
        self.taint.setdefault((scope, early_name), set()).add(EARLY_ROW)
        self.taint.setdefault((scope, late_name), set()).add(LATE_ROW)
        self.split_sites.append({"line": node.lineno, "how": how,
                                 "scope": ".".join(scope) or "<module>",
                                 "early_binding": early_name,
                                 "late_binding": late_name})

    # -- taint of an expression -------------------------------------------
    def _bare_taint(self, node, scope):
        """Grades of the names mentioned under `node`, with no promotion applied."""
        grades = set()
        for name in ast.walk(node):
            if isinstance(name, ast.Name):
                grades |= self.read(scope, name.id)
                if self.is_store(scope, name.id):
                    grades.add(RAW_COL)
        return grades

    def expr_taint(self, node, scope):
        grades = self._bare_taint(node, scope)
        for call in ast.walk(node):
            if not isinstance(call, ast.Call):
                continue
            local = _call_name(call)
            args = list(call.args) + [k.value for k in call.keywords]
            arg_grades = set()
            for arg in args:
                arg_grades |= self._bare_taint(arg, scope)
            if local in self.functions:
                # A local call also carries what its defaults close over, which is how
                # flat_surcharge_control.py hands its late row mask to its inner helper.
                fn = self.functions[local]
                for default in list(fn.args.defaults) + [
                        d for d in fn.args.kw_defaults if d is not None]:
                    arg_grades |= self._bare_taint(default, self.scope_of.get(fn, ()))
                grades |= arg_grades
            if _reducer_name(call) or local in self.reducing:
                if LATE_ROW in arg_grades:
                    grades.add(LATE_UNIT)
                if EARLY_ROW in arg_grades:
                    grades.add(EARLY_UNIT)
                # A reduction over a raw panel column with NEITHER half's mask on it is
                # a whole-window constant: knowable only once the window has run out.
                if RAW_COL in arg_grades and not (
                        {EARLY_ROW, LATE_ROW, EARLY_UNIT, LATE_UNIT} & arg_grades):
                    grades.add(WHOLE_WINDOW)
                grades |= arg_grades
        return grades

    def is_selector_expr(self, node, scope):
        """True when this expression evaluates to a mask or an index array."""
        if isinstance(node, (ast.Compare, ast.BoolOp)):
            return True
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.Not, ast.Invert)):
            return True
        if isinstance(node, ast.BinOp) and isinstance(
                node.op, (ast.BitAnd, ast.BitOr, ast.BitXor)):
            return True
        if isinstance(node, ast.Call) and _call_name(node) in SELECTOR_CALLS:
            return True
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp)):
            return any(gen.ifs for gen in node.generators)
        if isinstance(node, ast.Subscript):
            return self.is_selector_expr(node.value, scope)
        if isinstance(node, ast.Name):
            return self.is_selector(scope, node.id)
        return False

    # -- the fixpoint -----------------------------------------------------
    def _bindings(self):
        """(binding scope, names, value, value scope) for everything the module binds."""
        out = []
        for node in ast.walk(self.tree):
            scope = self.scope_of.get(node, ())
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    # ELEMENT-WISE WHEN BOTH SIDES ARE TUPLES, AND THAT IS A REPAIR
                    # MEASURED ON 2026-08-05. Binding the whole right-hand side to every
                    # target name is right for `a, b = f(x)`, where the grades of the
                    # returned pair cannot be told apart, and wrong for
                    # `me, ml = early & c, late & c`, where they can: the union handed
                    # the early mask the late grade and the late mask the early one, and
                    # from there both halves were the same colour through the rest of the
                    # module. Five findings in build_toxicity_frame.py came from that one
                    # line and none of them was real.
                    if (isinstance(target, (ast.Tuple, ast.List))
                            and isinstance(node.value, (ast.Tuple, ast.List))
                            and len(target.elts) == len(node.value.elts)):
                        for elt, val in zip(target.elts, node.value.elts):
                            out.append((scope, _targets(elt), val, scope))
                    else:
                        out.append((scope, _targets(target), node.value, scope))
            elif isinstance(node, (ast.AnnAssign, ast.AugAssign)) and node.value:
                out.append((scope, _targets(node.target), node.value, scope))
            elif isinstance(node, (ast.For, ast.AsyncFor)):
                out.append((scope, _targets(node.target), node.iter, scope))
            elif isinstance(node, _COMPREHENSIONS):
                # The target is bound INSIDE the comprehension's own scope and the
                # iterable is read outside it, which is what Python does and what keeps
                # two comprehensions' loop variables apart.
                inner = self.scope_of.get(node.generators[0], scope)
                for gen in node.generators:
                    out.append((inner, _targets(gen.target), gen.iter, scope))
            elif isinstance(node, ast.withitem) and node.optional_vars is not None:
                out.append((scope, _targets(node.optional_vars), node.context_expr, scope))
        # Parameters take what the defaults and the call sites hand them. The argument is
        # read in the CALLER's scope and written in the callee's, which is the only place
        # in this analysis where the two differ.
        for name, fn in self.functions.items():
            inner = self.scope_of.get(fn, ()) + (name,)
            outer = self.scope_of.get(fn, ())
            params = [a.arg for a in fn.args.args] + [a.arg for a in fn.args.kwonlyargs]
            defaults = list(fn.args.defaults)
            if defaults:
                for param, default in zip(params[len(params) - len(defaults):], defaults):
                    out.append((inner, [param], default, outer))
            for call in ast.walk(self.tree):
                if isinstance(call, ast.Call) and _call_name(call) == name:
                    call_scope = self.scope_of.get(call, ())
                    for param, arg in zip(params, call.args):
                        out.append((inner, [param], arg, call_scope))
                    for kw in call.keywords:
                        if kw.arg in params:
                            out.append((inner, [kw.arg], kw.value, call_scope))
        return out

    def _fixpoint(self):
        for _round in range(12):
            changed = False
            for scope, names, value, value_scope in self._bind_cache:
                grades = self.expr_taint(value, value_scope)
                selector = self.is_selector_expr(value, value_scope)
                for name in names:
                    have = self.taint.setdefault((scope, name), set())
                    if not grades <= have:
                        have |= grades
                        changed = True
                    if selector and (scope, name) not in self.selectors:
                        self.selectors.add((scope, name))
                        changed = True
            if not changed:
                break

    # -- the three questions ----------------------------------------------
    def _fixture(self, node):
        return any(part.startswith(FIXTURE_SCOPES)
                   for part in self.scope_of.get(node, ()))

    def _assign_targets_of(self):
        """node -> the names the assignment statement containing it binds."""
        owner = {}
        for stmt in ast.walk(self.tree):
            if isinstance(stmt, ast.Assign) and stmt.targets:
                names = []
                for target in stmt.targets:
                    names.extend(_targets(target))
                for child in ast.walk(stmt.value):
                    owner.setdefault(child, names)
        return owner

    def _rule1_dropped_units(self):
        """The SECOND shape of a population chosen by the future: dropping the unit.

        A loop over counterparties that skips the ones absent from a late-half table is
        the same defect as an eligibility mask, written as control flow instead of as
        arithmetic, and build_toxicity_frame.py writes it that way. The test has to name
        the loop's OWN target, because that is what makes it a unit dropped for its own
        future rather than an empty cell skipped: flat_surcharge_control.py skips a coin
        with no booked rows on a late-derived test that never mentions the coin, and that
        is correct.
        """
        found, near = [], []
        loops = [n for n in self._loops() if hasattr(n, "target")]
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.If) or self._fixture(node):
                continue
            if not node.body or not all(
                    isinstance(s, (ast.Continue, ast.Break)) for s in node.body):
                continue
            # THE INNERMOST enclosing loop, not every loop above it. Attributing the
            # guard to an outer loop as well reports one site twice, once as a finding
            # and once as its own near miss, which is a gate arguing with itself.
            inner = None
            for loop in loops:
                if any(n is node for n in ast.walk(loop)):
                    if inner is None or any(n is loop for n in ast.walk(inner)):
                        inner = loop
            if inner is None:
                continue
            targets = set(_targets(inner.target))
            if not targets:
                continue
            scope = self.scope_of.get(node, ())
            grades = self.expr_taint(node.test, scope)
            test_names = {n.id for n in ast.walk(node.test) if isinstance(n, ast.Name)}
            named = sorted(test_names & targets)
            record = {"file": self.filename, "line": node.lineno,
                      "binding": named[0] if named else sorted(targets)[0],
                      "index": ast.unparse(node.test)[:60]}
            if LATE_UNIT in grades and named:
                record["detail"] = (
                    f"the loop drops {record['binding']} when {record['index']} holds, a "
                    f"test built from a reduction over late-half rows: the units that "
                    f"survive are the ones that came back")
                record["source"] = "RULE 1"
                found.append(record)
            elif LATE_ROW in grades or LATE_UNIT in grades:
                record["detail"] = (
                    "a late-derived test skips an iteration without naming the unit "
                    "being iterated, which is an empty cell rather than a counterparty "
                    "dropped for its own future")
                near.append(record)
        return found, near

    def rule1_sites(self):
        """A per-unit early quantity subset by a selector built on late per-unit data.

        The near-miss list is kept beside the findings on purpose: it is what the
        calibration reads to prove the machinery REACHED a healthy producer and was
        silenced by the grade, rather than never getting there at all.
        """
        found, near = [], []
        owner = self._assign_targets_of()
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.Subscript) or self._fixture(node):
                continue
            scope = self.scope_of.get(node, ())
            if EARLY_UNIT not in self.expr_taint(node.value, scope):
                continue
            index = node.slice
            if isinstance(index, ast.Slice) or not self.is_selector_expr(index, scope):
                continue
            # THE SELECTOR HAS TO BRING THE FUTURE FROM SOMEWHERE ELSE. An array already
            # carrying a late grade masked by a test on ITSELF -- ev[np.isfinite(ev)] --
            # is the same defect one line downstream, not a second one, and counting it
            # buries the site that has to be repaired under its own consequences.
            own = {n.id for n in ast.walk(node.value) if isinstance(n, ast.Name)}
            index_grades = set()
            for name in ast.walk(index):
                if isinstance(name, ast.Name) and name.id not in own:
                    index_grades |= self.read(scope, name.id)
            record = {"file": self.filename, "line": node.lineno,
                      "binding": ast.unparse(node.value)[:60],
                      "index": ast.unparse(index)[:60]}
            if LATE_UNIT in index_grades:
                record["detail"] = (
                    f"the population of {record['binding']} is chosen by "
                    f"{record['index']}, which is built from a reduction over late-half "
                    f"rows: on the day the decision fires those rows do not exist")
                record["source"] = "RULE 1"
                record["_index_names"] = sorted(
                    n.id for n in ast.walk(index)
                    if isinstance(n, ast.Name) and LATE_UNIT in self.read(scope, n.id))
                record["_binds"] = list(owner.get(node, []))
                found.append(record)
            elif LATE_ROW in index_grades:
                record["detail"] = ("late knowledge reaches this subscript at ROW grade "
                                    "only, which is the measurement step and is correct")
                near.append(record)

        # A SITE WHOSE FUTURE ARRIVES ONLY THROUGH AN ALREADY-NAMED SITE IS THE SAME
        # DEFECT ONE LINE ON. ws2_hard_classifier.py subsets three early arrays by the
        # eligibility mask and then masks two of the results for finiteness; reporting
        # the second as a finding of its own buries the line that has to be repaired
        # under its own consequences. Only ever REMOVES, so nothing new can hide here.
        for _round in range(3):
            produced = {name for site in found for name in site["_binds"]}
            keep = [s for s in found
                    if not (s["_index_names"] and set(s["_index_names"]) <= produced)]
            if len(keep) == len(found):
                break
            found = keep

        dropped, dropped_near = self._rule1_dropped_units()
        for site in found:
            site.pop("_index_names", None)
            site.pop("_binds", None)
        return (_fold_sites(found + dropped, lambda s: s["index"]),
                near + dropped_near)

    def _loops(self):
        return [n for n in ast.walk(self.tree)
                if isinstance(n, (ast.For, ast.AsyncFor, ast.While))]

    def _selected_on_late(self):
        """Names taken from a search whose objective reads late per-unit data.

        Each is kept with the loop it was picked in, because the comparison INSIDE that
        loop is the search's own objective test and not a decision. Counting it would
        make every accumulator look like a threshold.
        """
        picked = {}
        loops = self._loops()

        def enclosing_loop(node):
            for loop in loops:
                if any(n is node for n in ast.walk(loop)):
                    return loop
            return None

        for node in ast.walk(self.tree):
            if self._fixture(node):
                continue
            scope = self.scope_of.get(node, ())
            if isinstance(node, ast.If):
                loop = enclosing_loop(node)
                if loop is None or LATE_UNIT not in self.expr_taint(node.test, scope):
                    continue
                for stmt in ast.walk(node):
                    if isinstance(stmt, ast.Assign) and stmt.targets:
                        for name in _targets(stmt.targets[0]):
                            picked.setdefault(name, (node.lineno, loop, scope))
            elif isinstance(node, ast.Assign) and node.targets:
                if isinstance(node.value, ast.Call) and _call_name(node.value) in (
                        "argmax", "argmin") and LATE_UNIT in self.expr_taint(
                            node.value, scope):
                    for name in _targets(node.targets[0]):
                        picked.setdefault(name, (node.lineno, enclosing_loop(node), scope))
                # A COMPREHENSION THAT FILTERS ON LATE DATA IS A SEARCH TOO, written as
                # one expression instead of as a loop. flat_surcharge_control.py picks
                # between two constructions exactly that way, and a predicate blind to
                # the spelling would report its silence there as evidence.
                elif isinstance(node.value, _COMPREHENSIONS):
                    # The filter is read in the COMPREHENSION's scope, not the
                    # statement's: since 2026-08-05 the loop variable lives inside the
                    # comprehension, and reading the test outside it resolves nothing.
                    if any(LATE_UNIT in self.expr_taint(
                               test, self.scope_of.get(gen, scope))
                           for gen in node.value.generators for test in gen.ifs):
                        for name in _targets(node.targets[0]):
                            picked.setdefault(name, (node.lineno, node.value, scope))
        # An ALIAS of a picked name is picked too: `thr = best` and `thr = float(best)`
        # are the same threshold. Nothing else propagates, because a value COMPUTED from
        # a threshold is no longer the threshold and reporting it would bury the site.
        for _round in range(4):
            grew = False
            for scope, names, value, value_scope in self._bind_cache:
                mentioned = {n.id for n in ast.walk(value) if isinstance(n, ast.Name)}
                if not mentioned or not (mentioned & set(picked)):
                    continue
                if not mentioned <= set(picked):
                    continue          # mixed in with something else: not an alias
                if any(isinstance(n, (ast.Subscript, ast.Compare, ast.Attribute))
                       for n in ast.walk(value)):
                    continue
                line, loop, _s = picked[sorted(mentioned & set(picked))[0]]
                for name in names:
                    if name not in picked:
                        picked[name] = (line, loop, scope)
                        grew = True
            if not grew:
                break
        return picked

    def _cutoff_uses(self, cutoffs, exclude_grade=None):
        """Comparisons applying one of `cutoffs` to a score carrying early UNIT grade.

        `cutoffs` maps a name to the loop it was chosen in, or to None. A comparison
        inside that loop is the search's own objective and is skipped: the finding is a
        threshold escaping its search and being applied as a rule.
        """
        out = []
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.Compare) or self._fixture(node):
                continue
            scope = self.scope_of.get(node, ())
            sides = [node.left] + list(node.comparators)
            names_per_side = [{n.id for n in ast.walk(s) if isinstance(n, ast.Name)}
                              for s in sides]
            for i, side in enumerate(sides):
                hit = names_per_side[i] & set(cutoffs)
                if not hit:
                    continue
                loop = cutoffs[sorted(hit)[0]]
                if loop is not None and any(n is node for n in ast.walk(loop)):
                    continue
                for j, other in enumerate(sides):
                    if i == j or (names_per_side[j] & set(cutoffs)):
                        continue
                    other_grades = self.expr_taint(other, scope)
                    if EARLY_UNIT not in other_grades:
                        continue
                    if exclude_grade and exclude_grade in other_grades:
                        continue
                    out.append({"line": node.lineno, "cutoff": sorted(hit)[0],
                                "score": ast.unparse(other)[:60]})
        return out

    def rule2_sites(self):
        picked = self._selected_on_late()
        uses = self._cutoff_uses({n: v[1] for n, v in picked.items()})
        found = [dict(site, file=self.filename, binding=site["cutoff"],
                      detail=(f"{site['cutoff']} is chosen by a search that maximises "
                              f"against late-half data and is then applied as a cutoff "
                              f"to {site['score']}, an early-half score: the threshold "
                              f"carries the answer it is later scored against"),
                      source="RULE 2")
                 for site in uses]
        return _fold_sites(found, lambda s: s["cutoff"]), sorted(picked)

    def rule3_sites(self):
        """A constant reduced over the WHOLE window and then compared with an early score."""
        whole = {}
        for scope, names, value, value_scope in self._bind_cache:
            if WHOLE_WINDOW in self.expr_taint(value, value_scope):
                for name in names:
                    whole.setdefault(name, ast.unparse(value)[:70])
        uses = self._cutoff_uses({n: None for n in whole},
                                 exclude_grade=WHOLE_WINDOW)
        found = [dict(site, file=self.filename, binding=site["cutoff"],
                      detail=(f"{site['cutoff']} comes from {whole[site['cutoff']]}, a "
                              f"reduction over the whole window with neither half's mask "
                              f"on it, and it is compared with {site['score']}, a score "
                              f"the decision takes on the early half alone"),
                      source="RULE 3")
                 for site in uses]
        return _fold_sites(found, lambda s: s["cutoff"]), sorted(whole)


# ---------------------------------------------------------------------------
# THE SWEEP
# ---------------------------------------------------------------------------
def tracked_python():
    """Every shipped .py file, repo-relative and in stable order."""
    return [p for p in shipped_tree_files(ROOT) if p.endswith(".py")]


def analyse(rel_path, late_slot, confirmed=None):
    """Analyse one module. Returns None when it holds no early/late cut at all."""
    path = os.path.join(ROOT, rel_path)
    with open(path, encoding="utf-8") as fh:
        source = fh.read()
    try:
        tree = ast.parse(source, filename=rel_path)
    except SyntaxError:
        return None
    wrappers = wrapper_calls_of(rel_path, tree, confirmed or {})
    mod = ModuleTaint(source, rel_path, late_slot, wrappers=wrappers)
    if not mod.split_sites:
        return None
    r1, near1 = mod.rule1_sites()
    r2, picked = mod.rule2_sites()
    r3, whole = mod.rule3_sites()
    return {"file": rel_path, "split_sites": mod.split_sites,
            "rule1": r1, "rule1_near_miss": near1,
            "rule2": r2, "selected_on_late": picked,
            "rule3": r3, "whole_window_statistics": whole}


def unresolved_split_callers(rel_paths, confirmed=None):
    """Modules that reach the cut, directly or through a wrapper, and still cannot be
    labelled here.

    This is the gate measuring its own blindness, and it is a rule rather than a note.
    A gate that reported zero findings without saying how many modules it could not ask
    the question of would be reporting the silence of its own predicate as a property of
    the tree. WIDENED ON 2026-08-05 to count wrapper callers as well: before that, a
    module reaching the cut one step removed was missing from this count too, so the
    blind spot did not even show up as a blind spot.
    """
    fn = S.split_early_late.__name__
    confirmed = confirmed or {}
    out = []
    for rel in rel_paths:
        with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
            source = fh.read()
        try:
            tree = ast.parse(source, filename=rel)
        except SyntaxError:
            continue
        wrappers = wrapper_calls_of(rel, tree, confirmed)
        reach = [n for n in ast.walk(tree)
                 if isinstance(n, ast.Call)
                 and (_call_name(n) == fn or _call_name(n) in wrappers)]
        if not reach:
            continue
        mod = ModuleTaint(source, rel, 0, wrappers=wrappers)
        if not mod.split_sites:
            how = ("calls the cut directly"
                   if any(_call_name(n) == fn for n in reach)
                   else "reaches the cut through a wrapper measured to resolve it")
            out.append({"file": rel, "line": reach[0].lineno,
                        "detail": (f"{how} but never unpacks two halves into two names "
                                   f"in this module, so no half can be labelled here"),
                        "source": "COVERAGE"})
    return out


# ---------------------------------------------------------------------------
# RULE 4: WHERE THE DECISION INPUT CAME FROM
# ---------------------------------------------------------------------------
# WHY A FOURTH RULE, MEASURED RATHER THAN IMAGINED. An arm whose surcharge is a
# monotone function of a classifier's predicted probability passes all three rules above
# in silence. Measured on a module that resolves the cut, reads a probability off disk
# and books lam * max(p_hat * mo_early, 0) on late rows: RULE 1 zero, RULE 2 zero,
# RULE 3 zero, and nothing separating it from an early-only control. None of the three
# shapes describes it. It selects no population with the future, tunes no threshold
# against the outcome and compares against no whole-window constant. Every line of it is
# arithmetic on a number that was honest where it was computed and is not honest here.
# What is wrong with the number is WHERE IT CAME FROM, and provenance is a property of
# the artifact that produced it, not of any expression in the consumer. Three rules
# reading one file's syntax tree cannot see it in principle, however carefully written.
#
# THE QUESTION, IN WORDS. A module books its decision on a set of days. A value it loads
# was produced by a script that split its own window and measured its outcome on the
# late half of it. If those two day sets meet, the consumer is holding a number that was
# fitted against the very days it is about to trade over, and no amount of care inside
# the consumer can undo that.
#
# HOW IT IS ASKED WITHOUT NAMING ANYBODY. Four resolutions, each from a home that
# already exists rather than from a table written here.
#   INPUTS      come from build.scan, which derives what a script reads from its syntax.
#   PRODUCERS   come from build.graph().producer_of, the tree's one map of file to maker.
#   ARTIFACTS   are found by _meta.producer.script, so the artifact is matched by what it
#               says produced it and never by the shape of its file name.
#   THE HALVES  come from settings.split_early_late applied to the days the artifact
#               declares, with the future slot read off probe_split. A producer that
#               resolves NO cut has no late half and therefore no label window, which is
#               how a raw panel builder stays silent: i4_midmarkout.py writes the file
#               ws2_hard_classifier.py reads, and it declares one window and no halves.
DAY_LIST_RE = re.compile(r"\[\s*\d+(?:\s*,\s*\d+)+\s*\]")
DAY_STAMP_RE = re.compile(r"(?<!\d)(20\d{6})(?!\d)")
DAY_ISO_RE = re.compile(r"(?<!\d)20\d\d-(\d\d)-(\d\d)(?!\d)")
DAY_RANGE_RE = re.compile(r"(?<![\d.])(\d{1,2})\s*(?:\.\.|-|to )\s*(\d{1,2})(?![\d.])")


def _day_of(number):
    """A declared day, whether it is written 4, 20251204 or 4 of a bracketed list."""
    return number % 100 if number > 31 else number


def declared_days(window):
    """The day-of-month numbers one artifact's scope window states, or an empty set.

    FOUR SPELLINGS, IN ORDER, AND THE LOOSEST ONE ONLY WHEN THE OTHERS FIND NOTHING.
    Bracketed integer lists, eight-digit stamps and ISO dates are unambiguous. A bare
    range like `days 4-8` is not -- inside `2025-12-04..2025-12-13` it would read 4 to
    20 -- so it is tried only on a window carrying none of the three precise forms. That
    is what lets markout/m2_figure_results.json resolve, whose window is written
    "December 2025, days 4-8 for labelling and the disjoint days 9-13 for measurement".
    An empty set is an honest answer and is counted as such; it is never a pass.
    """
    out = set()
    if isinstance(window, dict):
        for value in window.values():
            out |= declared_days(value)
        return out
    if isinstance(window, (list, tuple)):
        if window and all(isinstance(x, int) and not isinstance(x, bool)
                          for x in window):
            return {_day_of(x) for x in window if 1 <= _day_of(x) <= 31}
        for value in window:
            out |= declared_days(value)
        return out
    if not isinstance(window, str):
        return out
    for chunk in DAY_LIST_RE.findall(window):
        out |= {_day_of(int(n)) for n in re.findall(r"\d+", chunk)}
    out |= {int(stamp) % 100 for stamp in DAY_STAMP_RE.findall(window)}
    out |= {int(day) for _month, day in DAY_ISO_RE.findall(window)}
    if not out:
        for low, high in DAY_RANGE_RE.findall(window):
            low, high = int(low), int(high)
            if 1 <= low < high <= 31:
                out |= set(range(low, high + 1))
    return {d for d in out if 1 <= d <= 31}


def artifact_by_producer():
    """Every shipped results artifact, keyed by the script it says produced it.

    KEYED BY THE PATH, NOT BY THE NAME THE ARTIFACT RECORDS, and the difference is not
    cosmetic. An artifact records its producer by BASENAME on purpose: a directory names
    the machine and does not belong in a published file. Every caller of this index speaks
    the repository-relative path, because that is what a walk of the tree hands back.
    While every producer sat at the top of the tree the two spellings were the same
    string and the mismatch could not show. Once the producers were grouped into
    directories they parted, and an index keyed by the recorded name would answer None
    for all 56 of them -- which is not a finding but a rule going silent, the shape of
    failure that passes for a clean tree. So the recorded name is resolved to the file
    of that name in this tree, and a name that resolves to nothing is left out rather
    than keyed under a spelling nobody asks for.
    """
    by_base = {}
    for rel in shipped_tree_files(ROOT):
        if rel.endswith(".py"):
            by_base.setdefault(os.path.basename(rel), []).append(rel)
    index = {}
    for rel in shipped_tree_files(ROOT):
        if not rel.endswith("_results.json"):
            continue
        try:
            meta = json.loads(_read_text(rel)).get("_meta", {})
        except (OSError, ValueError):
            continue
        script = (meta.get("producer") or {}).get("script")
        if not script:
            continue
        hits = by_base.get(os.path.basename(script), [])
        key = hits[0] if len(hits) == 1 else script
        index.setdefault(key, (rel, meta))
    return index


def late_half(days, late_slot):
    """The future half of a declared day set, cut by the same function as everything."""
    if len(days) < 2:
        return set()
    halves = S.split_early_late(sorted(days))
    if not (isinstance(halves, tuple) and len(halves) == 2):
        return set()
    return {int(d) for d in halves[late_slot]}


def rule4_sites(rel, covered, index, graph_, late_slot):
    """One record per input this module loads: does its maker's label half meet ours?

    Returns (findings, reached). `reached` is every input that was resolved all the way
    to a producer and an artifact, whether or not it produced a finding, because a rule
    that reports only its findings cannot show that it looked.
    """
    findings, reached, blind = [], [], []
    ours = index.get(rel)
    if ours is None:
        return findings, reached, blind
    booking = late_half(declared_days(ours[1].get("scope", {}).get("window")), late_slot)
    if not booking:
        return findings, reached, blind
    try:
        names = sorted(build.scan(rel).inputs)
    except Exception:                                              # noqa: BLE001
        return findings, reached, blind
    lines = _read_text(rel).splitlines()
    for name in names:
        # AN INPUT THIS RULE CANNOT FOLLOW IS SAID OUT LOUD, NOT SKIPPED. Measured
        # 2026-08-05 on the very node this rule was written for: the headline quoting
        # node read a fitted result whose producer sat in a directory the build does not
        # scan, and build.graph answered None for it. A fitted quantity read from a
        # producer this gate cannot resolve is exactly the shape RULE 4 exists to catch,
        # so a silent skip here would report the gate's own blindness as a clean tree.
        node = graph_.producer_of(name)
        if node is None:
            blind.append({"file": rel, "input": name,
                          "why": "no producer for this name in build.graph()"})
            continue
        maker = node.script
        # A SCRIPT READING ITS OWN EARLIER STAGE IS NOT FOREIGN PROVENANCE, and this
        # screen was written after the rule reported one. i3_book_comparator.py writes
        # book_feats_*.npz under --stage feats and reads it back under no arm; the graph
        # keeps the two apart by argv, so producer_of answers with the same file. One
        # script in two passes over one window has one window, and calling that a
        # decision fitted on its own outcome would be the gate arguing with itself.
        if maker == rel:
            continue
        found = index.get(maker)
        if found is None:
            blind.append({"file": rel, "input": name, "producer": maker,
                          "why": "its producer names no artifact of this tree"})
            continue
        label = (late_half(declared_days(found[1].get("scope", {}).get("window")),
                           late_slot)
                 if maker in covered else set())
        overlap = sorted(label & booking)
        record = {"file": rel, "input": name, "producer": maker,
                  "producer_artifact": found[0],
                  "producer_resolves_a_cut": maker in covered,
                  "label_days": sorted(label), "booking_days": sorted(booking),
                  "days_in_common": overlap}
        reached.append(record)
        if not overlap:
            continue
        line = next((i + 1 for i, text in enumerate(lines) if name in text), 0)
        findings.append({
            "file": rel, "line": line, "binding": name, "source": "RULE 4",
            "index": f"{maker} -> {found[0]}",
            "detail": (f"{name} is made by {maker}, which splits its own window and "
                       f"measures on days {sorted(label)}; this module books its "
                       f"decision on days {sorted(booking)}, and the two meet on "
                       f"{overlap}. The value was fitted against the days it is used "
                       f"to trade over, which nothing inside this file can undo"),
            "producer": maker, "producer_artifact": found[0],
            "days_in_common": overlap})
    return findings, reached, blind


def match_debt(site, rule):
    for entry in DECLARED_DEBT:
        if (entry["file"] == site["file"] and entry["rule"] == rule
                and entry["binding"] == site.get("binding")):
            return entry
    return None


# ---------------------------------------------------------------------------
# CALIBRATION
# ---------------------------------------------------------------------------
# The three one-line edits. Each moves exactly ONE leg of one predicate in a live
# producer's own source, so a rule whose verdict does not flip afterwards is keying on the
# file rather than on the defect. They are not edits anybody would ship; they are the
# smallest edit that changes the truth of what the predicate claims.
#
# THE EDIT RUNS IN WHICHEVER DIRECTION THE PRODUCER LEAVES OPEN, and that is the whole
# reason `direction` exists rather than being assumed. A calibration that can only remove a
# defect needs the defect to still be there, which ties the gate's ability to certify
# itself to the tree's failure to repair anything: fix the producer and the calibration
# fails, so the pressure runs towards leaving defects standing. Both directions prove the
# same thing -- that the predicate keys on the defect and not on the file -- because both
# ask whether the verdict follows the ONE line that carries it.
#
#   REMOVE_DEFECT: the live producer carries the defect, so the rule must fire on the file
#                  as committed and go silent on the edited copy.
#   INJECT_DEFECT: the live producer was repaired, so the rule must be silent on the file
#                  as committed and fire on the edited copy. `before` is then the REPAIRED
#                  line and `after` puts the defect back.
#
# RULE 3 was turned round on 2026-08-05, when the break-even line in ws2_hard_classifier.py
# stopped being half a whole-window median and became half an early-half one. No producer
# of this tree carries that defect any more, so there is nothing left for the rule to fire
# on except an injected one, and a rule with no live case is a rule nobody has run.
REMOVE_DEFECT = "remove"
INJECT_DEFECT = "inject"
FIRE_CASE = "persistence/ws2_hard_classifier.py"
SILENT_CASE = "probes/flat_surcharge_control.py"
ONE_LINE_EDITS = {
    "RULE 1": {
        "direction": REMOVE_DEFECT,
        "before": "elig = (e_cnt >= K) & (l_cnt >= K) & np.isfinite(e_mean) & np.isfinite(l_mean)",
        "after": "elig = (e_cnt >= K) & np.isfinite(e_mean)"},
    "RULE 2": {
        "direction": REMOVE_DEFECT,
        "before": "frac_youden = float(np.mean(tau_star >= thr_youden))",
        "after": "frac_youden = float('nan')"},
    "RULE 3": {
        "direction": INJECT_DEFECT,
        "before": "half_spread = float(np.median(spread[ie & np.isfinite(spread)]) / 2.0)",
        "after": "half_spread = float(np.median(spread[np.isfinite(spread)]) / 2.0)"},
}
# What each rule must do on FIRE_CASE exactly as committed, derived from the direction
# rather than written twice: a rule whose edit REMOVES a defect has one to remove, and a
# rule whose edit INJECTS one has none standing.
LIVE_EXPECTATION = {rule: (edit["direction"] == REMOVE_DEFECT)
                    for rule, edit in ONE_LINE_EDITS.items()}


# The two opposite live cases for the WRAPPER predicate, and for the day reader and the
# provenance rule that stand on it. Named here rather than inside the assertions so that
# a case going missing from the tree fails loudly instead of being quietly skipped.
WRAPPER_MUST_CONFIRM = ("money/maker_econ.py", "early_late_days")
WRAPPER_MUST_REJECT = ("quoters/t1_toxicity_skew_backtest.py",
                       "_early_late_masks")
WINDOW_MUST_READ = "quoters/mm_bakeoff_results.json"
WINDOW_MUST_STAY_EMPTY = "build_diagram_results.json"
PROVENANCE_MUST_FIRE = ("probes/flat_surcharge_control.py",
                        "mm_bakeoff_results.json")
PROVENANCE_MUST_BE_SILENT = ("persistence/ws2_hard_classifier.py",
                             "quickwin_markouts_mid.npz")


def _self_test_wrappers(confirmed, rejected):
    """The wrapper predicate on two opposite live functions of this tree.

    One reference cannot tell a predicate that is too wide from one that is too narrow,
    and here the two are one line apart in the same producer. maker_econ.early_late_days
    must be confirmed, because mm_bakeoff.py reaches the cut through it and was invisible
    to this gate until it was. t1_toxicity_skew_backtest._early_late_masks must be
    rejected: it passes SHAPE and PURITY, it is called, and what comes back is two
    boolean masks over rows rather than two day sets, which is the case that proves the
    verdict is read off the call and not off the static filter that got there.
    """
    hit = confirmed.get(WRAPPER_MUST_CONFIRM)
    assert hit is not None, (
        f"{WRAPPER_MUST_CONFIRM[0]}:{WRAPPER_MUST_CONFIRM[1]} was not confirmed as a "
        f"cut resolver. It is how mm_bakeoff.py reaches the cut, so a gate that cannot "
        f"see it cannot ask any of its questions of the file that produces every "
        f"published quoting number: {sorted(confirmed)}")
    assert hit["returned"][hit["late_slot"]] == [9, 10, 11, 12, 13], (
        f"the confirmed slot of {WRAPPER_MUST_CONFIRM[1]} returned "
        f"{hit['returned']}, and the future half read off it is not the second half of "
        f"the probe range; the measurement this gate hangs on has moved")
    assert WRAPPER_MUST_REJECT not in confirmed, (
        f"{WRAPPER_MUST_REJECT[0]}:{WRAPPER_MUST_REJECT[1]} was confirmed as a cut "
        f"resolver; it returns two row masks and not two day sets, so a predicate "
        f"accepting it is keying on the static shape and never reading the call")
    stopped = [r for r in rejected
               if (r["file"], r["function"]) == WRAPPER_MUST_REJECT]
    assert stopped and stopped[0]["stage"] == "call", (
        f"{WRAPPER_MUST_REJECT[1]} was not rejected AT THE CALL, so its absence proves "
        f"nothing about the behavioural stage: {stopped}")
    return {
        "must_confirm": {"file": WRAPPER_MUST_CONFIRM[0],
                         "function": WRAPPER_MUST_CONFIRM[1],
                         "returned": hit["returned"], "late_slot": hit["late_slot"]},
        "must_reject": {"file": WRAPPER_MUST_REJECT[0],
                        "function": WRAPPER_MUST_REJECT[1],
                        "stage": stopped[0]["stage"], "why": stopped[0]["why"]},
        "n_confirmed": len(confirmed), "n_rejected": len(rejected),
        "why": ("both functions pass the static filter; the call separates them, which "
                "is what keeps this attached to behaviour rather than to a spelling"),
    }


def _self_test_provenance(covered, index, graph_, late_slot):
    """The day reader and RULE 4, each on two opposite live cases of this tree."""
    ours = index.get("quoters/mm_bakeoff.py")
    assert ours and ours[0] == WINDOW_MUST_READ, (
        f"{WINDOW_MUST_READ} is not the artifact that names quoters/mm_bakeoff.py as "
        f"its producer, so the case this reader is calibrated on is gone")
    read_days = declared_days(ours[1]["scope"]["window"])
    assert len(read_days) == 10, (
        f"the day reader took {sorted(read_days)} out of the window of "
        f"{WINDOW_MUST_READ}, which declares ten days; a reader that cannot read the "
        f"headline artifact's window cannot be trusted on any other")
    blank = index.get("build_diagram.py")
    assert blank and blank[0] == WINDOW_MUST_STAY_EMPTY, (
        f"{WINDOW_MUST_STAY_EMPTY} is not where build_diagram.py's artifact lives")
    assert declared_days(blank[1]["scope"]["window"]) == set(), (
        f"the day reader found days in {WINDOW_MUST_STAY_EMPTY}, whose window says it "
        f"covers no period of market data. A reader that finds a window everywhere "
        f"reports its own looseness as a property of the tree")

    fires, seen, _blind = rule4_sites(PROVENANCE_MUST_FIRE[0], covered, index,
                                      graph_, late_slot)
    hit = [f for f in fires if f["binding"] == PROVENANCE_MUST_FIRE[1]]
    assert hit, (
        f"RULE 4 is silent on {PROVENANCE_MUST_FIRE[0]} reading "
        f"{PROVENANCE_MUST_FIRE[1]}, which is made by a producer that splits its own "
        f"window and publishes a quantity measured on the late half of it: {fires}")
    _q, quiet_seen, _qb = rule4_sites(PROVENANCE_MUST_BE_SILENT[0], covered, index,
                                      graph_, late_slot)
    resolved = [s for s in quiet_seen if s["input"] == PROVENANCE_MUST_BE_SILENT[1]]
    assert resolved, (
        f"{PROVENANCE_MUST_BE_SILENT[1]} was not resolved to a maker and an artifact at "
        f"all in {PROVENANCE_MUST_BE_SILENT[0]}, so its silence proves nothing: the "
        f"predicate never reached it")
    assert not resolved[0]["days_in_common"], (
        f"RULE 4 fires on {PROVENANCE_MUST_BE_SILENT[0]} reading "
        f"{PROVENANCE_MUST_BE_SILENT[1]}, whose maker declares one window and no "
        f"halves, so it has no label half to meet anything: {resolved[0]}")
    assert not resolved[0]["producer_resolves_a_cut"], (
        f"{resolved[0]['producer']} now resolves a cut, so this case no longer tests "
        f"what it was written to test and a new silent case is needed")
    return {
        "day_reader": {
            "must_read": {"artifact": WINDOW_MUST_READ, "days": sorted(read_days)},
            "must_stay_empty": {"artifact": WINDOW_MUST_STAY_EMPTY, "days": []}},
        "rule4_must_fire": {
            "file": hit[0]["file"], "input": hit[0]["binding"],
            "producer": hit[0]["producer"], "days_in_common": hit[0]["days_in_common"]},
        "rule4_must_be_silent": {
            "file": PROVENANCE_MUST_BE_SILENT[0], "input": resolved[0]["input"],
            "producer": resolved[0]["producer"],
            "producer_artifact": resolved[0]["producer_artifact"],
            "producer_resolves_a_cut": False,
            "label_days": resolved[0]["label_days"],
            "booking_days": resolved[0]["booking_days"],
            "days_in_common": []},
        "why": ("both inputs resolve all the way to a maker and its artifact; the one "
                "that stays silent is silenced by its maker declaring no late half, not "
                "by the predicate failing to reach it"),
    }


def _self_test(late_slot):
    """Two opposite cases per rule, all of them live producers of this tree.

    One reference case cannot tell a predicate that is too wide from one that is too
    narrow. So each rule is shown holding the verdict its producer's committed text calls
    for, staying silent on a healthy producer that REACHES the same machinery, and flipping
    that verdict the moment the one line carrying its defect is edited. Which way the flip
    runs is read off ONE_LINE_EDITS rather than assumed: a repaired producer inverts the
    pair without weakening it.
    """
    fire_path = os.path.join(ROOT, FIRE_CASE)
    silent_path = os.path.join(ROOT, SILENT_CASE)
    for path in (fire_path, silent_path):
        if not os.path.isfile(path):
            raise SystemExit(
                f"calibration case {os.path.relpath(path, ROOT)} is not in this tree; "
                f"this gate cannot certify a predicate against a file that is gone")
    with open(fire_path, encoding="utf-8") as fh:
        fire_src = fh.read()
    with open(silent_path, encoding="utf-8") as fh:
        silent_src = fh.read()

    fire = ModuleTaint(fire_src, FIRE_CASE, late_slot)
    assert fire.split_sites, f"the cut was not resolved in {FIRE_CASE} at all"
    fire_sites = {"RULE 1": fire.rule1_sites()[0],
                  "RULE 2": fire.rule2_sites()[0],
                  "RULE 3": fire.rule3_sites()[0]}
    counts = {rule: len(sites) for rule, sites in fire_sites.items()}
    # BOTH DIRECTIONS ARE ASSERTED, not just the firing one. A rule declared repaired that
    # keeps firing on the committed file means the repair did not take, and that failure is
    # as much a calibration failure as a rule gone quiet on a defect still standing.
    for rule, n in counts.items():
        if LIVE_EXPECTATION[rule]:
            assert n >= 1, (
                f"{rule} is silent on {FIRE_CASE}, the case it was written for, while its "
                f"calibration edit is declared to REMOVE a defect that is therefore "
                f"supposed to be standing there. Either the producer was repaired, in "
                f"which case turn the edit round to {INJECT_DEFECT}, or the predicate "
                f"stopped seeing the defect, which is the direction of error that travels")
        else:
            assert n == 0, (
                f"{rule} fires on {FIRE_CASE} although its calibration edit is declared "
                f"to INJECT a defect there, which says the file is repaired. A rule "
                f"firing on the repaired file is either a second site the repair missed "
                f"or a predicate keying on something else: {fire_sites[rule]}")

    silent = ModuleTaint(silent_src, SILENT_CASE, late_slot)
    assert silent.split_sites, (
        f"the cut was not resolved in {SILENT_CASE}, so its silence proves nothing: "
        f"the predicate never reached it")
    s1, near = silent.rule1_sites()
    assert not s1, f"RULE 1 fires on {SILENT_CASE}, which books its offset correctly: {s1}"
    assert near, (
        f"no near miss in {SILENT_CASE}: late data does not reach a subscript of an "
        f"early quantity there, so this file cannot certify that the ROW/UNIT grade is "
        f"what silences the rule")
    assert not silent.rule2_sites()[0], f"RULE 2 fires on {SILENT_CASE}"
    assert silent.rule2_sites()[1], (
        f"nothing in {SILENT_CASE} is selected against late data, so its RULE 2 silence "
        f"does not test the second leg of the predicate")
    assert not silent.rule3_sites()[0], f"RULE 3 fires on {SILENT_CASE}"

    edited = {}
    for rule, edit in ONE_LINE_EDITS.items():
        before, after = edit["before"], edit["after"]
        assert before in fire_src, (
            f"the calibration edit for {rule} no longer matches {FIRE_CASE}: the line\n"
            f"  {before}\nis not in the file. Re-derive the edit from the producer as it "
            f"stands; a calibration that silently stops applying certifies nothing")
        mutant = ModuleTaint(fire_src.replace(before, after), FIRE_CASE, late_slot)
        got = {"RULE 1": len(mutant.rule1_sites()[0]),
               "RULE 2": len(mutant.rule2_sites()[0]),
               "RULE 3": len(mutant.rule3_sites()[0])}
        if edit["direction"] == REMOVE_DEFECT:
            assert got[rule] == 0, (
                f"{rule} still fires on {FIRE_CASE} after the one line that carries the "
                f"defect was edited away, so it is keying on something other than the "
                f"defect: {got}")
        else:
            assert got[rule] >= 1, (
                f"{rule} stays silent on {FIRE_CASE} after the defect was put back into "
                f"the one line that carries it, so the rule reads neither the defect nor "
                f"the repair and its silence on the committed file proves nothing: {got}")
        # THE OTHER TWO KEEP THE VERDICT THEY HAVE ON THE COMMITTED FILE. Written as a
        # comparison against `counts` rather than as ">= 1", because one of the three is
        # now expected to be silent there and a bare floor would assert the opposite of
        # what this file declares two hundred lines up.
        for other, value in got.items():
            if other == rule:
                continue
            assert (value >= 1) == (counts[other] >= 1), (
                f"editing the {rule} line flipped {other} as well: it reads "
                f"{counts[other]} on {FIRE_CASE} as committed and {value} on the edited "
                f"copy ({got}), so the three predicates are not independent and one of "
                f"them is reading the wrong thing")
        edited[rule] = {"direction": edit["direction"], "findings_per_rule": got}

    # THE EXEMPTION MACHINERY GETS ITS OWN TWO CASES, because it is the part of this
    # gate that can turn a real finding green and nothing else here would notice. One
    # site that must be excused and one that must not: a binding one letter different
    # from a declared one is a different site, and if the match were loose enough to
    # swallow it, every future finding in that file would go quiet.
    if DECLARED_DEBT:
        real = DECLARED_DEBT[0]
        hit = {"file": real["file"], "binding": real["binding"], "source": real["rule"]}
        assert match_debt(hit, real["rule"]) is real, (
            "a declared site is not matched by its own entry, so the debt list is not "
            "excusing what it says it excuses")
        for altered in ({**hit, "binding": real["binding"] + "_"},
                        {**hit, "file": "no_such_producer.py"}):
            assert match_debt(altered, real["rule"]) is None, (
                f"the debt entry for {real['file']} also excuses {altered}, which is a "
                f"different site: an exemption this loose hides the next finding")
        assert match_debt(hit, "RULE 9") is None, (
            "a debt entry excuses a rule it was not written for")

    fires_live = sorted(r for r in counts if LIVE_EXPECTATION[r])
    repaired = sorted(r for r in counts if not LIVE_EXPECTATION[r])
    return {
        # RENAMED FROM "fires_on" ON 2026-08-05, because the old name asserted in the key
        # what the value no longer says of every rule: one of the three is now expected to
        # read zero here. A key whose name outlives its meaning is the failure this tree
        # keeps paying for, so the name moved with the quantity.
        "on_the_committed_producer": {
            "file": FIRE_CASE,
            "findings_per_rule": counts,
            "must_fire": fires_live,
            "must_be_silent_because_repaired": repaired,
            "why": ("a rule under a remove-the-defect edit has a defect standing here and "
                    "must fire; a rule under an inject-the-defect edit was repaired here "
                    "and must read zero, which is asserted rather than allowed")},
        "debt_matching": ("one declared site matches its own entry; the same site with "
                          "a changed binding, a changed file or a changed rule matches "
                          "none"),
        "silent_on_healthy": {
            "file": SILENT_CASE,
            "rule1_near_misses": len(near),
            "selected_on_late_bindings": len(silent.rule2_sites()[1]),
            "why": ("late data reaches this producer at ROW grade and is selected on, "
                    "and neither reaches a decision, so all three rules must be silent")},
        # RENAMED FROM "silent_after_one_line_edit" the same day and for the same reason:
        # the edit no longer only silences. Each entry now carries the direction it ran in
        # beside the counts it produced.
        "verdict_flips_on_one_line_edit": edited,
        "sentence": (
            f"calibration: on {FIRE_CASE} as committed, {', '.join(fires_live)} fire and "
            f"{', '.join(repaired)} read zero because the defect there was repaired; all "
            f"three stay silent on {SILENT_CASE}, which reaches the same machinery; and "
            f"each flips its own verdict, and only its own, when the single line carrying "
            f"it is edited -- removed where the defect stands, injected where it does not"),
    }


# ---------------------------------------------------------------------------
def main():
    started = artifact.start_clock()
    split = probe_split()
    calibration = _self_test(split["late_slot"])
    print(calibration["sentence"])

    scanned = tracked_python()
    confirmed, rejected = cut_resolvers(scanned)
    calibration["wrappers"] = _self_test_wrappers(confirmed, rejected)
    print(f"  wrapper calibration     : "
          f"{calibration['wrappers']['must_confirm']['function']} confirmed by call, "
          f"{calibration['wrappers']['must_reject']['function']} rejected at the call")
    reports = [r for r in (analyse(p, split["late_slot"], confirmed) for p in scanned)
               if r]
    covered = [r["file"] for r in reports]
    coverage_gaps = unresolved_split_callers(scanned, confirmed)

    # RULE 4 needs three things this file does not hold: what each module reads, who
    # writes each of those files, and what that writer declared about its own window.
    # All three are called rather than copied -- build.scan, build.graph and the
    # artifacts' own _meta -- so a change in any of them reaches this gate.
    index = artifact_by_producer()
    graph_ = build.graph()
    calibration["provenance"] = _self_test_provenance(set(covered), index, graph_,
                                                      split["late_slot"])
    provenance, provenance_reached, provenance_blind = [], [], []
    for report in reports:
        hits, seen, blind = rule4_sites(report["file"], set(covered), index, graph_,
                                        split["late_slot"])
        report["rule4"] = hits
        report["rule4_inputs_resolved"] = seen
        report["rule4_inputs_unresolved"] = blind
        provenance.extend(hits)
        provenance_reached.extend(seen)
        provenance_blind.extend(blind)

    findings = {"RULE 1": [], "RULE 2": [], "RULE 3": [], "RULE 4": []}
    excused = []
    for report in reports:
        for rule, key in (("RULE 1", "rule1"), ("RULE 2", "rule2"), ("RULE 3", "rule3"),
                          ("RULE 4", "rule4")):
            for site in report[key]:
                entry = match_debt(site, rule)
                if entry:
                    excused.append(dict(site, declared_reason=entry["reason"],
                                        declared_on=entry["date"]))
                else:
                    findings[rule].append(site)

    # Matched by all three parts, RULE included. Two entries for one file and one
    # binding under different rules are two exemptions, and letting either of them
    # answer for the other is how an exemption outlives the finding it was written for.
    matched = {id(e) for site in excused for e in DECLARED_DEBT
               if e["file"] == site["file"] and e["rule"] == site.get("source")
               and e["binding"] == site.get("binding")}
    stale_debt = [{"file": e["file"], "line": 0, "binding": e["binding"],
                   "detail": (f"declared debt for {e['rule']} on {e['binding']} matches "
                              f"no finding today: either it was repaired, in which case "
                              f"this line comes out, or the predicate stopped seeing it"),
                   "source": "DEBT"}
                  for e in DECLARED_DEBT if id(e) not in matched]

    print(f"  cut read from           : {split['function']}, late slot "
          f"{split['late_slot']} of {split['returned']}")
    print(f"  tracked .py scanned     : {len(scanned)}")
    print(f"  modules with a cut      : {len(covered)}")
    print(f"  rule 1 (population)     : {len(findings['RULE 1'])} undeclared")
    print(f"  rule 2 (cutoff)         : {len(findings['RULE 2'])} undeclared")
    print(f"  rule 3 (constant)       : {len(findings['RULE 3'])} undeclared")
    print(f"  rule 4 (provenance)     : {len(findings['RULE 4'])} undeclared, over "
          f"{len(provenance_reached)} inputs resolved to a maker and its artifact, "
          f"{len(provenance_blind)} it could not follow")
    print(f"  declared debt excused   : {len(excused)} of {len(DECLARED_DEBT)}")
    print(f"  cut reached, unresolved : {len(coverage_gaps)}")

    # THE DEBT ON THE SCREEN, EVERY RUN. An exemption that only lives inside a source
    # file and a results file is an exemption nobody reads, and the whole reason this
    # gate can be green while seven decision sites carry the future is that it says so
    # out loud each time it passes.
    if excused:
        print(f"  the {len(excused)} sites below are KNOWN and DECLARED, not clean:")
        for site in excused:
            print(f"    {site['file']}:{site['line']} [{site['source']}] "
                  f"{site['binding']}  (declared {site['declared_on']})")
            print(f"      {site['declared_reason']}")

    if any(findings.values()) or stale_debt:
        verdict = "FAIL"
    elif excused:
        verdict = "PASS_AT_BASELINE"
    else:
        verdict = "ALL_PASS"
    artifact.write(
        OUT_NAME,
        {"verdict": verdict,
         "split_declaration": split,
         "n_tracked_python_scanned": len(scanned),
         "modules_with_a_resolved_cut": covered,
         "per_module": reports,
         "undeclared_findings": findings,
         "declared_debt": DECLARED_DEBT,
         "declared_debt_excused": excused,
         "declared_debt_matching_nothing": stale_debt,
         "cut_reached_but_unresolved": coverage_gaps,
         "cut_resolvers_confirmed": [
             {"file": rel, "function": name, **record}
             for (rel, name), record in sorted(confirmed.items())],
         "cut_resolver_candidates_rejected": rejected,
         "rule4_inputs_resolved": provenance_reached,
         "rule4_inputs_unresolved": provenance_blind,
         "calibration": calibration},
        script=__file__,
        # The declaration and the modules that actually carry a cut. Hashing all 100-odd
        # tracked scripts would drown the record; the population that is scanned but
        # holds no cut is stated in scope instead, which is the convention artifact.write
        # asks for when a producer reads a tree.
        inputs=[os.path.join(ROOT, "settings.py")] + [os.path.join(ROOT, f)
                                                      for f in covered],
        scope={
            "population": (f"{len(scanned)} tracked .py files of this repository are "
                           f"parsed; {len(covered)} of them resolve a two-half day cut "
                           f"and are the population the three rules are counted over. "
                           f"A module with no cut is outside the question, not passing "
                           f"it"),
            "window": ("n/a: this gate reads source text as it stands and no market "
                       f"data. The cut it labels halves by is "
                       f"{split['function']}, probed on days "
                       f"{split['probe_days'][0]}-{split['probe_days'][-1]}"),
            "coins": "n/a: this gate reads source text and touches no market data",
        },
        started=started,
        extra_meta={"late_slot": split["late_slot"],
                    "n_modules_with_cut": len(covered),
                    "n_coverage_gaps": len(coverage_gaps),
                    "declared_debt_entries": len(DECLARED_DEBT)},
    )

    # The verdict word goes to the screen only when the gate is green, because the
    # battery runner reads the FIRST word it recognises out of a check's whole output
    # and PASS_AT_BASELINE outranks FAIL in that list. A red run must say only FAIL,
    # and report_gate below is what says it.
    if verdict != "FAIL":
        print(f"  VERDICT: {verdict}")

    return report_gate(
        [{"name": "population chosen with late-half knowledge",
          "permitted": 0,
          "found": len(findings["RULE 1"]),
          "assumption": ("the units a decision is taken over are chosen with what was "
                         "on the table when it fired; requiring a wallet to trade again "
                         "in the late half selects the wallets that came back, which no "
                         "live rule can do"),
          "method": ("late taint starts at the slot settings.split_early_late returns "
                     "for the future, is carried through the syntax tree, and is raised "
                     "from ROW to UNIT grade by any reduction. A finding is a purely "
                     "early per-unit array subscripted by a selector carrying UNIT grade"),
          "note": ("going over means a published effect is measured on survivors rather "
                   "than on the counterparties a maker would actually face"),
          "sites": findings["RULE 1"]},
         {"name": "cutoff tuned on the half it is scored against",
          "permitted": 0,
          "found": len(findings["RULE 2"]),
          "assumption": ("a threshold that turns a score into a decision is a decision "
                         "parameter and has to be picked from what the decision can see"),
          "method": ("a value assigned inside a loop whose test carries late UNIT grade, "
                     "or taken from an argmax over it, and then used as a cutoff in a "
                     "comparison against a score carrying early UNIT grade and no late "
                     "grade at all"),
          "note": ("going over means the reported flagged fraction and everything read "
                   "off it are in-sample, whatever the file says about out-of-sample"),
          "sites": findings["RULE 2"]},
         {"name": "constant reduced over the whole window feeding an early decision",
          "permitted": 0,
          "found": len(findings["RULE 3"]),
          "assumption": ("a line a decision is compared with must be computable at the "
                         "moment of the decision; an average over all ten days is not"),
          "method": ("a binding whose expression reduces a raw panel column with neither "
                     "half's mask on it, propagated forward, then compared against a "
                     "purely early score"),
          "note": ("going over means a break-even line drawn with hindsight is presented "
                   "as one a maker could have drawn on day four"),
          "sites": findings["RULE 3"]},
         {"name": "decision input fitted against the days it is booked on",
          "permitted": 0,
          "found": len(findings["RULE 4"]),
          "assumption": ("a value a decision reads was computable before the decision "
                         "fired; a number measured on the late half of the same window "
                         "the consumer books on was not"),
          "method": ("each input of a module with a resolved cut is resolved to its "
                     "maker through build.graph, the maker to its artifact through "
                     "_meta.producer.script, and the artifact's declared window to a "
                     "late half through settings.split_early_late. A finding is a "
                     "non-empty intersection of that half with the consumer's own"),
          "note": ("going over means an arm is priced off a quantity fitted on the days "
                   "it quotes over, which no rule reading one file's syntax can see"),
          "sites": findings["RULE 4"]},
         {"name": "declared debt matching no finding",
          "permitted": 0,
          "found": len(stale_debt),
          "assumption": ("every excused site is still there and still excused for the "
                         "reason written beside it; an exemption that matches nothing "
                         "either outlived its defect or lost sight of it"),
          "method": ("each DECLARED_DEBT entry is matched to today's findings by file, "
                     "rule and binding, and the unmatched ones are counted"),
          "note": ("going over means an exemption is standing over a site this gate can "
                   "no longer see, which is the direction of error that travels"),
          "sites": stale_debt},
         {"name": "modules reaching the cut in a shape this gate cannot follow",
          # UNARMED, and that is a decision rather than an oversight. The count is the
          # gate measuring its own blindness: these modules call the declared cut but
          # hand the halves on through a wrapper, so no name in them can be labelled
          # early or late and none of the three questions can be asked. Arming it would
          # be asking producers to change shape for the convenience of this file. The
          # number is printed on every run so that a zero above is read next to it.
          "permitted": None,
          "found": len(coverage_gaps),
          "assumption": ("a zero from the three rules above is a zero over the modules "
                         "this gate can label, and this count says how many it cannot"),
          "method": (f"a module calling {split['function']} whose call is not unpacked "
                     f"into two names in the same module"),
          "note": "these modules are outside the three questions, not passing them",
          "sites": coverage_gaps}],
        OUT_JSON,
        inputs={"cut_declared_in": "settings.py",
                "scanned": f"{len(scanned)} shipped .py files (shared census)",
                "population": f"{len(covered)} of them resolve a cut"})


if __name__ == "__main__":
    sys.exit(main())
