#!/usr/bin/env python3
"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-07-31
References: internal artifacts only -- ws1_horizon_results.json,
i3_book_nonrecoverability_results.json, t3_results.json, m11_results.json,
maker_econ_results.json, maker_econ_b2_results.json, mm_bakeoff_results.json,
as_quoter_results.json. No external source is used or needed: this file reads what
those producers already wrote and reports no number of its own.

ONE TABLE ANSWERING "WHAT DOES THIS SETTING COST", FOR EVERY SETTING AND EVERY CANDIDATE.

Why this file exists. settings.py says what each setting IS and what justifies it. It
does not say what a reported number would become if the setting were different, and that
is the question a reviewer asks and the question the results discussion has to answer.
Today the only way to answer it is to re-run the tree at the other candidate, and one
pass over the tree takes hours. So the answer is expensive enough that it does not get
asked, which is the failure mode this file removes: after this, the question is a file
read.

WHY IT EXTRACTS AND DOES NOT RECOMPUTE. The sweeps have already been run. ws1 re-marks
the tape on an eight-rung horizon grid and reports the persistence at every rung; i3
re-scores every cell over forty independent fold seeds and reports the spread; t3 and m11
carry the whale-drop ladder; maker_econ, maker_econ_b2 and mm_bakeoff carry the wallet
floor, the lens, the horizon and the fee tier as nested axes of one surface. Recomputing
any of that here would produce a SECOND number for a quantity that already has one, and
this project has already learned what that costs: when the same quantity lives in two
files it eventually disagrees with itself, and then the work has to stop and find out
which copy is right. A roll-up that lifts values leaves exactly one producer per number.
Every row therefore carries the file and the key path it was lifted from, and `origin`
says extracted so that a row which is ever NOT extracted cannot hide among the rest.

WHAT A ROW IS, AND WHAT IT IS NOT. A row is one (setting, candidate, quantity) triple:
the value that quantity takes when that setting sits at that candidate, with every OTHER
axis of the same artifact pinned, and `held_fixed` says at what. Two rows may be compared
only inside one group -- one setting, one quantity, one source file -- and the roll-up
never subtracts across files, because the eight sources do not share a population, a
window or a coin set. Their own scope blocks are copied into `source_scopes` verbatim so
that the differences are visible rather than asserted away.

THREE TRAPS THIS FILE IS BUILT AGAINST, each one having already fired in this project.

  1. A predicate that cannot match. The coin symbol in i3 is not a key in the path, it is
     the VALUE of a field inside a list of records, so a sweep that looks for it among
     key names returns nothing while the data sits there. So the axis discovery has two
     forms -- sibling keys and a field inside a list -- and _dig refuses a filter that
     matches no record or more than one, rather than returning nothing quietly.

  2. A float in the join key. The same quantity is stored at different precisions in
     different files, so a rounded float used to line two records up will silently line
     up the wrong pair. Every filter this file joins on is a whole field -- a coin
     symbol, an integer fill floor, an integer horizon -- and _match refuses a float in a
     filter with an error naming the field.

  3. nan is not equal to nan. A missing value compared naively reads as a change, and a
     min or max taken over a column holding one returns nonsense. Non-finite values are
     dropped from every spread with a count kept, and no value is ever compared to
     another to decide identity: identity is decided on the CANDIDATE, which is a whole
     field by construction.

NO SETTING VALUE IS TYPED HERE. The candidates come from the artifacts, discovered by
reading their axes; the value in force comes from settings.py through getattr; the pinned
values in held_fixed come from settings.py too. What is typed is the SPELLING each file
uses for a candidate -- "K50", "h10", "net_MID_lower", "drop_top50_by_gross_cost" -- and
those are properties of the file, not of the project, which is why they are typed beside
the file they belong to and nowhere else.

WHAT THE OUTPUT SAYS THAT NO SOURCE ARTIFACT SAYS. Three things. `spread` per group:
how far the quantity travels across the candidates, which is what the setting costs.
`coverage`: every setting declared in settings.py with its sweep or with the plain
statement that it has none -- and the settings with no sweep are the more useful half of
this file, because an unswept setting is an unmeasured assumption. `axes_not_declared`:
axes the artifacts sweep whose parameter has no home in settings.py at all, which is the
same gap seen from the other side.

Run: uv run --no-project --with-requirements ../requirements.txt python3 sensitivity_rollup.py
Reads eight artifacts and writes sensitivity_rollup_results.json beside itself. Seconds.
"""

import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# artifact.py, settings.py and the other shared modules sit in the
# repository root, one directory up from this group, so the path is built
# from this file's own location and never from the working directory the
# run happens to start in.
_CODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CODE_DIR not in sys.path:
    sys.path.insert(0, _CODE_DIR)

# Imported under its own name and NOT under an alias, which is load-bearing rather than
# stylistic. build.py derives the graph from this tree's syntax and recognises a write by
# the dotted name of the call, matching the literal "artifact.write". Written as an alias,
# the call reads A.write, which matches no writer and no reader: the write is not reported
# as unresolved, it is not seen at all. The file then appears with eight reads and no
# writes, which is not a node, so the artifact it produces has no producer in the graph
# and the self-test passes at a residue of zero while the edge is missing. Verified both
# ways on 31 July: under the alias the suite returned PASS with the node absent.
import artifact                 # noqa: E402  (path set above, as every producer does)
import settings as S            # noqa: E402

OUT_NAME = "sensitivity_rollup_results.json"

# The eight artifacts this roll-up reads. Bare names: the directory is built from this
# file's own location at read time and never recorded.
WS1 = "ws1_horizon_results.json"
I3 = "i3_book_nonrecoverability_results.json"
T3 = "t3_results.json"
M11 = "m11_results.json"
MAKER = "maker_econ_results.json"
MAKER_B2 = "maker_econ_b2_results.json"
BAKEOFF = "mm_bakeoff_results.json"
AS_QUOTER = "as_quoter_results.json"
SOURCES = (WS1, I3, T3, M11, MAKER, MAKER_B2, BAKEOFF, AS_QUOTER)


# =====================================================================
# 1. SPELLINGS. What each file calls a candidate, kept beside the file that uses it.
#
# These are the only typed strings in this module that stand for a setting, and they are
# typed because they are properties of an artifact rather than of the project: the value
# they point at is read from settings.py, and the label is built around it, never the
# other way round. f"K{S.RANK_FLOOR_FILLS}" moves with the declaration; "K50" would not.
# =====================================================================

def k_label(fills):
    """maker_econ and mm_bakeoff spell a wallet floor K<fills>."""
    return f"K{int(fills)}"


def h_label(seconds):
    """maker_econ and mm_bakeoff spell a horizon h<seconds>."""
    return f"h{int(seconds)}"


# The two lenses as maker_econ, maker_econ_b2 and mm_bakeoff spell them. The mapping is
# BUILT rather than typed: the file's spelling is split on the underscore and matched
# against settings.LENSES, so a spelling that stops meaning what it says raises here.
LENS_FILE_SPELLING = {"net_MID_lower": "mid", "net_PRINT": "print"}
for _spelling, _lens in LENS_FILE_SPELLING.items():
    if _lens not in S.LENSES:
        raise RuntimeError(
            f"{_spelling!r} is read as the {_lens!r} lens, which settings.LENSES "
            f"{S.LENSES} does not declare")


def lens_spelling(lens):
    """The file spelling of a lens named the way settings.py names it."""
    for spelling, name in LENS_FILE_SPELLING.items():
        if name == lens:
            return spelling
    raise ValueError(f"no file spelling recorded for lens {lens!r}")


MID = lens_spelling(S.HEADLINE_LENS)
HEAD_H = h_label(S.HEADLINE_HORIZON_S)
HEAD_K = k_label(S.RANK_FLOOR_FILLS)
# The persistence floor is a pair: settings.py states 50 is the reported cell and 100 is
# the check that the cell is not a small-sample artifact, so the cell is the lower rung.
PERSIST_CELL = min(S.PERSISTENCE_FLOOR_FILLS)
BTC = S.coin_labels("quickwin")[0]      # the coin code map is a property of the file

# The fee tier the maker-economics surface reports first. It is NOT a setting: settings.py
# declares no fee, which is the finding recorded under axes_not_declared below. The name
# is pinned here so every row that holds the tier fixed holds it at the same one.
BASE_TIER = "base"


# =====================================================================
# 2. WALKING AN ARTIFACT. One walker, and it refuses rather than returns nothing.
# =====================================================================

class Missing(Exception):
    """A path that does not resolve. Raised, never swallowed into a None."""


def _match(record, filt):
    """True when a record satisfies every field of a filter. Whole fields only.

    The refusal is the point. A float in a filter is the join defect this project has
    already paid for: the same quantity is stored at different precisions in different
    files, so 10.0 from one file and 10.000000001 from another are one value and two
    keys. An integer horizon, an integer fill floor and a coin symbol are exact.
    """
    for field, wanted in filt.items():
        if isinstance(wanted, float):
            raise TypeError(
                f"the filter on {field!r} is a float ({wanted!r}); a join key must be a "
                f"whole field, because the same quantity is stored at different "
                f"precisions in different files and two spellings of one value would "
                f"then be two keys")
        if field not in record:
            return False
        got = record[field]
        if isinstance(got, float):
            raise TypeError(
                f"the record's {field!r} is a float ({got!r}) and cannot be a join key "
                f"for the same reason a float filter cannot")
        if got != wanted:
            return False
    return True


def _dig(document, path, where=None):
    """Follow a path into a loaded artifact. Every component is a whole key or a filter.

    A component is a string (a dict key), an integer (a list index) or a mapping (a
    filter over a list of records, which must select exactly one). The mapping form
    exists because a coin symbol, a horizon and a fill floor live as FIELD VALUES inside
    i3's by_coin list rather than as keys, and a sweep that looked for them among key
    names found nothing while the records sat in front of it.
    """
    node = document
    walked = []
    for step in path:
        walked.append(step)
        trail = " -> ".join(repr(w) for w in walked)
        if isinstance(step, dict):
            if not isinstance(node, list):
                raise Missing(f"{trail}: a filter needs a list, found "
                              f"{type(node).__name__}")
            hits = [r for r in node if isinstance(r, dict) and _match(r, step)]
            if len(hits) != 1:
                raise Missing(f"{trail}: the filter selects {len(hits)} records of "
                              f"{len(node)}, and a value is only unambiguous at one")
            node = hits[0]
        elif isinstance(step, int) and isinstance(node, list):
            if step >= len(node):
                raise Missing(f"{trail}: index past the end of a list of {len(node)}")
            node = node[step]
        else:
            if not isinstance(node, dict) or step not in node:
                have = sorted(node)[:8] if isinstance(node, dict) else \
                    type(node).__name__
                raise Missing(f"{trail}: no such key; found {have}")
            node = node[step]
    if where is not None:
        node = _dig(node, [where])
    return node


def _path_text(path):
    """The key path as one readable string, so a row states where it came from.

    READABLE AND NOT AUTHORITATIVE, which is why every row carries key_path_parts beside
    this. A dotted string cannot be split back into the path it came from once a key
    contains a dot, and this repository has such keys: the deployable-policy grid spells
    a cell f0.25_w0_c0, so splitting its path on the dot invents two components that do
    not exist. The defect is the same one as rounding a float into a join key -- a whole
    thing flattened into a spelling that no longer identifies it -- and it was found by a
    reader written to re-read every value from the sources, which is what such a reader
    is for.
    """
    parts = []
    for step in path:
        if isinstance(step, dict):
            parts.append("[" + ",".join(f"{k}={v}" for k, v in sorted(step.items())) + "]")
        else:
            parts.append(str(step))
    return ".".join(parts)


def _path_parts(path):
    """The key path as whole components: what a reader should follow. Never split a path.

    A filter component keeps its mapping form, so the record it selects is identified by
    its fields rather than by a position that would move if the list were reordered.
    """
    return [dict(step) if isinstance(step, dict) else step for step in path]


# =====================================================================
# 3. READING A CANDIDATE OUT OF A LABEL.
#
# Each spec says how its file spells a candidate. The rule is named in every row it
# produces, so a reader can see how "drop_top50_by_gross_cost" became the integer 50
# without opening this file.
# =====================================================================

def _as_int(text):
    return int(text)


def _as_lens(text):
    """"net_MID_lower" and "net_PRINT" carry the lens in their middle component."""
    name = LENS_FILE_SPELLING.get(f"net_{text}")
    if name is None:
        raise ValueError(f"no lens recorded for the spelling net_{text}")
    return name


def _as_text(text):
    return text


PARSERS = {"int": _as_int, "lens": _as_lens, "text": _as_text}


# =====================================================================
# 4. THE SPECS. One per (setting, quantity, file); the candidates are DISCOVERED.
#
# A spec never lists its candidates. It says where the axis is and how the file spells a
# candidate, and the candidates are whatever the artifact turns out to carry. That is the
# difference between reporting a sweep and asserting one: a rung this file names but the
# artifact does not hold shows up as absent, and a rung the artifact holds that no
# declaration mentions shows up as undeclared. Both have already happened.
#
#   kind "keys"   the candidates are sibling dict keys at `at`, matched by `label_re`
#   kind "field"  the candidates are the distinct values of `field` among the records of
#                 the list at `at` that satisfy `where`
#   kind "point"  one named candidate at one path, for a rung stored in a shape of its
#                 own -- the undropped baseline of a drop ladder, or the primary cell of
#                 a file whose robustness rungs live under a different key
# =====================================================================

SPECS = [
    # ---- the scoring window -------------------------------------------------
    # THE THREE ROWS BELOW ARE EVIDENCE FOR TWO DECISIONS, NOT FOR ONE. The persistence
    # row is the evidence for the RANKING window and for nothing else; the level and
    # completeness rows are the evidence for the COST window and for nothing else. One
    # number carries both only because both criteria clear at the same rung, and
    # settings.py is where that is declared. The `means` text of the first row says the
    # window was chosen on persistence, which is the older single-decision reading; the
    # wording is owed a correction and cannot have one here, because `means` is written
    # into this file's own artifact and editing it is a change to what the artifact
    # says rather than a renaming. Declared debt, 2026-08-01.
    dict(setting="HEADLINE_HORIZON_S", file=WS1, kind="keys",
         quantity="rank_persistence_disattenuated",
         means="early-to-late Spearman of the per-wallet toxicity score, corrected for "
               "split-half unreliability. This is the number the window was chosen on.",
         at=["pooled"], label_re=r"^(\d+)$", parse="int", leaf=["rho_disatt"],
         held_fixed={"wallet floor (fills in EACH half)": "the file's K_primary",
                     "population": "pooled over coins", "lens": S.HEADLINE_LENS}),
    dict(setting="HEADLINE_HORIZON_S", file=WS1, kind="keys",
         quantity="markout_level_vw_bps",
         means="volume-weighted mean adverse markout in basis points at the horizon; the "
               "level whose plateau says when the permanent price move has arrived.",
         at=["level_termstructure", "pooled"], label_re=r"^(\d+)$", parse="int",
         leaf=["vw"],
         held_fixed={"population": "pooled over coins", "lens": S.HEADLINE_LENS}),
    dict(setting="HEADLINE_HORIZON_S", file=WS1, kind="keys",
         quantity="information_complete_fraction",
         means="share of the plateau markout already impounded at the horizon, against "
               "the file's stated completeness threshold.",
         at=["final_decision", "info_frac"], label_re=r"^(\d+)$", parse="int", leaf=[],
         held_fixed={"population": "pooled over coins", "lens": S.HEADLINE_LENS}),
    dict(setting="HEADLINE_HORIZON_S", file=T3, kind="keys",
         quantity="gross_cost_bps",
         means="gross taker-side adverse-selection cost over the window in basis points "
               "of notional. An upper-bound cost, not an edge.",
         at=["pooled"], label_re=r"^cost_bps_(\d+)s$", parse="int", leaf=[],
         held_fixed={"population": "pooled over coins"}),
    dict(setting="HEADLINE_HORIZON_S", file=T3, kind="keys",
         quantity="avoidable_share_top_decile",
         means="share of the out-of-sample gross cost carried by the worst decile of "
               "counterparties ranked on the disjoint early half.",
         at=["pooled"], label_re=r"^avoidable_share_oos_top10pct_(\d+)s$", parse="int",
         leaf=[], held_fixed={"population": "pooled over coins",
                              "wallets dropped": "none"}),
    dict(setting="HEADLINE_HORIZON_S", file=MAKER, kind="keys",
         quantity="maker_net_vw_bps",
         means="volume-weighted net maker result in basis points after the fee of the "
               "pinned tier. Negative is a cost.",
         at=["baseline_net", "pooled", "by_horizon"], label_re=r"^h(\d+)$", parse="int",
         leaf=[MID, "by_fee_tier", BASE_TIER, "net_vw_bps"],
         held_fixed={"lens": S.HEADLINE_LENS, "fee tier": BASE_TIER,
                     "population": "pooled over coins"}),
    dict(setting="HEADLINE_HORIZON_S", file=BAKEOFF, kind="keys",
         quantity="quoter_net_vw_bps_as_toxicity",
         means="net result in basis points of the counterparty-resolved quoter, the one "
               "quoter whose spread reads a per-wallet toxicity label.",
         at=["quoters", HEAD_K, "as_toxicity", "net_by_coin", "pooled", "by_horizon"],
         label_re=r"^h(\d+)$", parse="int",
         leaf=[MID, "by_fee_tier", BASE_TIER, "net_vw_bps"],
         held_fixed={"wallet floor (early fills)": S.RANK_FLOOR_FILLS,
                     "lens": S.HEADLINE_LENS, "fee tier": BASE_TIER,
                     "quoter": "as_toxicity", "population": "pooled over coins"}),
    dict(setting="HEADLINE_HORIZON_S", file=I3, kind="field",
         quantity="incremental_oos_r2_of_identity",
         means="out-of-sample R-squared the counterparty fixed effect adds ON TOP of the "
               "full public order book. The claim that identity is not recoverable.",
         at=["by_coin"], where={"coin": BTC, "K": PERSIST_CELL}, field="horizon_s",
         leaf=["incremental_oos_r2"],
         held_fixed={"coin": BTC, "wallet floor (fills in EACH half)": PERSIST_CELL}),

    # ---- the lens -----------------------------------------------------------
    dict(setting="HEADLINE_LENS", file=MAKER, kind="keys",
         quantity="toxicity_screen_value_delta_net_vw_bps",
         means="basis points the idealised counterparty screen adds to the maker's net "
               "result. The upper bound on what naming the counterparty is worth.",
         at=["b1_idealized_policy_upper_bound", HEAD_K, HEAD_H, "delta_net_vw_bps"],
         label_re=r"^net_(.+)$", parse="lens", leaf=[BASE_TIER],
         held_fixed={"wallet floor (early fills)": S.RANK_FLOOR_FILLS,
                     "horizon_s": S.HEADLINE_HORIZON_S, "fee tier": BASE_TIER}),
    dict(setting="HEADLINE_LENS", file=MAKER, kind="keys",
         quantity="maker_net_vw_bps",
         means="volume-weighted net maker result in basis points before any screen.",
         at=["baseline_net", "pooled", "by_horizon", HEAD_H], label_re=r"^net_(.+)$",
         parse="lens", leaf=["by_fee_tier", BASE_TIER, "net_vw_bps"],
         held_fixed={"horizon_s": S.HEADLINE_HORIZON_S, "fee tier": BASE_TIER,
                     "population": "pooled over coins"}),
    dict(setting="HEADLINE_LENS", file=MAKER_B2, kind="keys",
         quantity="deployable_baseline_net_bps",
         means="net result in basis points of the fill-aware baseline the deployable "
               "widening policy is measured against.",
         at=["by_measure"], label_re=r"^net_(.+)$", parse="lens",
         leaf=["surface", "baseline_by_tier", BASE_TIER, "baseline_net_bps"],
         held_fixed={"fee tier": BASE_TIER}),
    dict(setting="HEADLINE_LENS", file=BAKEOFF, kind="keys",
         quantity="quoter_net_vw_bps_as_toxicity",
         means="net result in basis points of the counterparty-resolved quoter.",
         at=["quoters", HEAD_K, "as_toxicity", "net_by_coin", "pooled", "by_horizon",
             HEAD_H],
         label_re=r"^net_(.+)$", parse="lens",
         leaf=["by_fee_tier", BASE_TIER, "net_vw_bps"],
         held_fixed={"wallet floor (early fills)": S.RANK_FLOOR_FILLS,
                     "horizon_s": S.HEADLINE_HORIZON_S, "fee tier": BASE_TIER,
                     "quoter": "as_toxicity", "population": "pooled over coins"}),

    # ---- the rank floor: minimum fills in the RANKING window -----------------
    # Every spec in this block gates on fills in the early half only. The other floor,
    # which gates on fills in BOTH halves, is a different quantity and sits below.
    dict(setting="RANK_FLOOR_FILLS", file=MAKER, kind="keys",
         quantity="toxicity_screen_value_delta_net_vw_bps",
         means="basis points the idealised counterparty screen adds to the maker's net "
               "result.",
         at=["b1_idealized_policy_upper_bound"], label_re=r"^K(\d+)$", parse="int",
         leaf=[HEAD_H, "delta_net_vw_bps", MID, BASE_TIER],
         held_fixed={"horizon_s": S.HEADLINE_HORIZON_S, "lens": S.HEADLINE_LENS,
                     "fee tier": BASE_TIER}),
    dict(setting="RANK_FLOOR_FILLS", file=MAKER, kind="keys",
         quantity="n_toxic_takers_dropped",
         means="how many counterparties the screen declines. The floor's bite in wallets "
               "rather than in basis points.",
         at=["b1_idealized_policy_upper_bound"], label_re=r"^K(\d+)$", parse="int",
         leaf=[HEAD_H, "n_toxic_takers_dropped"],
         held_fixed={"horizon_s": S.HEADLINE_HORIZON_S}),
    dict(setting="RANK_FLOOR_FILLS", file=BAKEOFF, kind="keys",
         quantity="quoter_net_vw_bps_as_toxicity",
         means="net result in basis points of the counterparty-resolved quoter.",
         at=["quoters"], label_re=r"^K(\d+)$", parse="int",
         leaf=["as_toxicity", "net_by_coin", "pooled", "by_horizon", HEAD_H, MID,
               "by_fee_tier", BASE_TIER, "net_vw_bps"],
         held_fixed={"horizon_s": S.HEADLINE_HORIZON_S, "lens": S.HEADLINE_LENS,
                     "fee tier": BASE_TIER, "quoter": "as_toxicity",
                     "population": "pooled over coins"}),
    dict(setting="RANK_FLOOR_FILLS", file=BAKEOFF, kind="keys",
         quantity="adverse_selection_term_value_bps",
         means="basis points separating the counterparty-resolved quoter from the "
               "identical quoter that is blind to identity. What the name is worth "
               "inside one model rather than across models.",
         at=["adverse_selection_term_value"], label_re=r"^K(\d+)$", parse="int",
         leaf=[BTC, BASE_TIER, "as_toxicity_minus_as_symmetric_delta_net_vw_bps"],
         held_fixed={"coin": BTC, "fee tier": BASE_TIER}),
    dict(setting="RANK_FLOOR_FILLS", file=M11, kind="keys",
         quantity="net_toxic_gini",
         means="Gini of the per-dollar toxicity across wallets at the cut. How "
               "concentrated the harm is once the floor decides who is measurable.",
         at=["pooled", "per_dollar_toxicity", "min_fills_sensitivity"],
         label_re=r"^min_fills_(\d+)$", parse="int", leaf=["net_toxic_gini"],
         held_fixed={"population": "pooled over coins",
                     "horizon_s": S.HEADLINE_HORIZON_S}),
    dict(setting="RANK_FLOOR_FILLS", file=M11, kind="keys",
         quantity="n_wallets_at_cut",
         means="how many wallets survive the floor. The floor's bite in wallets.",
         at=["pooled", "per_dollar_toxicity", "min_fills_sensitivity"],
         label_re=r"^min_fills_(\d+)$", parse="int", leaf=["n_wallets_at_cut"],
         held_fixed={"population": "pooled over coins"}),

    # ---- the persistence floor: minimum fills in EACH half -------------------
    # ws1 and i3 gate on both halves. settings.py declares this a DIFFERENT quantity from
    # the rank floor above, and both producers nonetheless stamp it into their fingerprint
    # under the rank floor's name. The rows are filed by what the code does.
    dict(setting="PERSISTENCE_FLOOR_FILLS", file=WS1, kind="point",
         quantity="rank_persistence_disattenuated",
         means="early-to-late Spearman of the per-wallet score, corrected for split-half "
               "unreliability.",
         candidate_at=["K_primary"],
         path=["pooled", str(S.HEADLINE_HORIZON_S), "rho_disatt"],
         held_fixed={"horizon_s": S.HEADLINE_HORIZON_S,
                     "population": "pooled over coins", "lens": S.HEADLINE_LENS}),
    dict(setting="PERSISTENCE_FLOOR_FILLS", file=WS1, kind="keys",
         quantity="rank_persistence_disattenuated",
         means="the same quantity at the robustness rungs, which the file stores under a "
               "key of its own rather than beside the primary cell.",
         at=["robustness_K"], label_re=r"^(\d+)$", parse="int",
         leaf=[str(S.HEADLINE_HORIZON_S), "rho_disatt"],
         held_fixed={"horizon_s": S.HEADLINE_HORIZON_S,
                     "population": "pooled over coins", "lens": S.HEADLINE_LENS}),
    dict(setting="PERSISTENCE_FLOOR_FILLS", file=WS1, kind="point",
         quantity="split_half_reliability_early",
         means="measured split-half reliability of the early-window score. The number the "
               "floor was chosen on: below it, most of a corrected persistence is the "
               "correction.",
         candidate_at=["K_primary"],
         path=["pooled", str(S.HEADLINE_HORIZON_S), "rel_early"],
         held_fixed={"horizon_s": S.HEADLINE_HORIZON_S,
                     "population": "pooled over coins"}),
    dict(setting="PERSISTENCE_FLOOR_FILLS", file=WS1, kind="keys",
         quantity="split_half_reliability_early",
         means="the same reliability at the robustness rungs.",
         at=["robustness_K"], label_re=r"^(\d+)$", parse="int",
         leaf=[str(S.HEADLINE_HORIZON_S), "rel_early"],
         held_fixed={"horizon_s": S.HEADLINE_HORIZON_S,
                     "population": "pooled over coins"}),
    dict(setting="PERSISTENCE_FLOOR_FILLS", file=I3, kind="field",
         quantity="incremental_oos_r2_of_identity",
         means="out-of-sample R-squared the counterparty fixed effect adds on top of the "
               "full public order book.",
         at=["by_coin"], where={"coin": BTC, "horizon_s": S.HEADLINE_HORIZON_S},
         field="K", leaf=["incremental_oos_r2"],
         held_fixed={"coin": BTC, "horizon_s": S.HEADLINE_HORIZON_S}),
    dict(setting="PERSISTENCE_FLOOR_FILLS", file=I3, kind="field",
         quantity="n_wallets",
         means="how many wallets clear the floor in both halves. The floor's bite.",
         at=["by_coin"], where={"coin": BTC, "horizon_s": S.HEADLINE_HORIZON_S},
         field="K", leaf=["n_wallets"],
         held_fixed={"coin": BTC, "horizon_s": S.HEADLINE_HORIZON_S}),

    # ---- the whale drop -----------------------------------------------------
    # The undropped rung is stored in a shape of its own in every one of these files, so
    # it is lifted as a point. Without it the ladder has no origin and the spread would
    # measure the distance between two robustness arms rather than the distance from the
    # headline.
    dict(setting="WHALE_DROP_K", file=T3, kind="point",
         quantity="avoidable_share_top_decile",
         means="share of the out-of-sample gross cost carried by the worst decile.",
         candidate=0, candidate_note="the undropped headline; zero is the absence of the "
                                     "drop and not a declared rung",
         path=["pooled", f"avoidable_{S.HEADLINE_HORIZON_S}s",
               f"avoidable_share_oos_top10pct_{S.HEADLINE_HORIZON_S}s"],
         held_fixed={"horizon_s": S.HEADLINE_HORIZON_S, "criterion": "gross_cost",
                     "population": "pooled over coins"}),
    dict(setting="WHALE_DROP_K", file=T3, kind="keys",
         quantity="avoidable_share_top_decile",
         means="the same share after dropping the k costliest counterparties.",
         at=["pooled", f"avoidable_{S.HEADLINE_HORIZON_S}s",
             f"whale_drop_ladder_top10pct_{S.HEADLINE_HORIZON_S}s"],
         label_re=r"^drop_top(\d+)_by_gross_cost$", parse="int", leaf=[],
         held_fixed={"horizon_s": S.HEADLINE_HORIZON_S, "criterion": "gross_cost",
                     "population": "pooled over coins"}),
    dict(setting="WHALE_DROP_K", file=M11, kind="point",
         quantity="cost_concentration_gini",
         means="Gini of the positive per-wallet dollar cost. Verified in the producer to "
               "be the same population the ladder drops from: both take the wallets with "
               "cost above zero, so this is the ladder's own zero rung.",
         candidate=0, candidate_note="the undropped headline",
         path=["pooled", "dollar_cost", "dollar_cost_gini"],
         held_fixed={"population": "pooled over coins", "criterion": "gross_cost"}),
    dict(setting="WHALE_DROP_K", file=M11, kind="keys",
         quantity="cost_concentration_gini",
         means="the same Gini after dropping the k costliest wallets.",
         at=["pooled", "robustness"], label_re=r"^drop_top(\d+)_by_gross_cost$",
         parse="int", leaf=["gini_after_drop"],
         held_fixed={"population": "pooled over coins", "criterion": "gross_cost"}),
    dict(setting="WHALE_DROP_K", file=M11, kind="point",
         quantity="positive_cost_total_quote",
         means="total positive per-wallet dollar cost. Same verified population as the "
               "ladder, so this is its zero rung.",
         candidate=0, candidate_note="the undropped headline",
         path=["pooled", "dollar_cost", "positive_cost_total_quote"],
         held_fixed={"population": "pooled over coins", "criterion": "gross_cost"}),
    dict(setting="WHALE_DROP_K", file=M11, kind="keys",
         quantity="positive_cost_total_quote",
         means="what is left of that total after dropping the k costliest wallets.",
         at=["pooled", "robustness"], label_re=r"^drop_top(\d+)_by_gross_cost$",
         parse="int", leaf=["cost_total_after_drop"],
         held_fixed={"population": "pooled over coins", "criterion": "gross_cost"}),
    dict(setting="WHALE_DROP_K", file=I3, kind="point",
         quantity="incremental_oos_r2_of_identity",
         means="out-of-sample R-squared the counterparty fixed effect adds on top of the "
               "public book, with every counterparty kept.",
         candidate=0, candidate_note="the undropped headline",
         path=["by_coin", {"coin": BTC, "horizon_s": S.HEADLINE_HORIZON_S,
                           "K": PERSIST_CELL}, "incremental_oos_r2"],
         held_fixed={"coin": BTC, "horizon_s": S.HEADLINE_HORIZON_S,
                     "wallet floor (fills in EACH half)": PERSIST_CELL}),
    dict(setting="WHALE_DROP_K", file=I3, kind="point",
         quantity="incremental_oos_r2_of_identity",
         means="the same, with the costliest counterparties removed. The candidate is "
               "read from the file's own test_design rather than typed.",
         candidate_at=["test_design", "whale_drop_k"],
         path=["by_coin", {"coin": BTC, "horizon_s": S.HEADLINE_HORIZON_S,
                           "K": PERSIST_CELL}, "incremental_oos_r2_no_whales"],
         held_fixed={"coin": BTC, "horizon_s": S.HEADLINE_HORIZON_S,
                     "wallet floor (fills in EACH half)": PERSIST_CELL}),

    # ---- which criterion the largest counterparties are largest BY -----------
    dict(setting="WHALE_DROP_CRITERIA", file=M11, kind="keys",
         quantity="cost_concentration_gini",
         means="Gini after dropping the declared number of counterparties, by each "
               "criterion the artifact carries. settings.py declares four criteria; how "
               "many appear here is the point of the row count.",
         at=["pooled", "robustness"],
         label_re=rf"^drop_top{S.WHALE_DROP_K}_by_(\w+)$", parse="text",
         leaf=["gini_after_drop"],
         held_fixed={"k": S.WHALE_DROP_K, "population": "pooled over coins"}),

    # ---- the seed -----------------------------------------------------------
    # The forty draws are summarised rather than stored, so the candidates below are the
    # summary points of the sweep and not seed values. A row here answers "how far does
    # the result move when only the fold split moves", which is the question the seed
    # raises; it cannot answer "what does seed 17 give", and says so.
    dict(setting="MASTER_SEED", file=I3, kind="point",
         quantity="incremental_oos_r2_of_identity",
         means="lowest of forty independent fold splits.",
         candidate="sweep_min", candidate_kind="sweep_summary",
         candidate_note="the forty draws are summarised in the artifact, not stored, so "
                        "no individual seed can be looked up",
         path=["seed_robustness", "cells",
               {"coin": BTC, "horizon_s": S.HEADLINE_HORIZON_S, "K": PERSIST_CELL},
               "min"],
         held_fixed={"coin": BTC, "horizon_s": S.HEADLINE_HORIZON_S,
                     "wallet floor (fills in EACH half)": PERSIST_CELL}),
    dict(setting="MASTER_SEED", file=I3, kind="point",
         quantity="incremental_oos_r2_of_identity",
         means="median of forty independent fold splits, which is what the file's own "
               "reporting rule says to quote.",
         candidate="sweep_median", candidate_kind="sweep_summary",
         path=["seed_robustness", "cells",
               {"coin": BTC, "horizon_s": S.HEADLINE_HORIZON_S, "K": PERSIST_CELL},
               "median"],
         held_fixed={"coin": BTC, "horizon_s": S.HEADLINE_HORIZON_S,
                     "wallet floor (fills in EACH half)": PERSIST_CELL}),
    dict(setting="MASTER_SEED", file=I3, kind="point",
         quantity="incremental_oos_r2_of_identity",
         means="highest of forty independent fold splits.",
         candidate="sweep_max", candidate_kind="sweep_summary",
         path=["seed_robustness", "cells",
               {"coin": BTC, "horizon_s": S.HEADLINE_HORIZON_S, "K": PERSIST_CELL},
               "max"],
         held_fixed={"coin": BTC, "horizon_s": S.HEADLINE_HORIZON_S,
                     "wallet floor (fills in EACH half)": PERSIST_CELL}),
    dict(setting="MASTER_SEED", file=I3, kind="point",
         quantity="incremental_oos_r2_of_identity",
         means="the single draw the artifact ships in by_coin, which is the number the "
               "prose quotes. Its percentile inside the sweep is beside it in the file.",
         candidate="stored_draw", candidate_kind="sweep_summary",
         path=["seed_robustness", "cells",
               {"coin": BTC, "horizon_s": S.HEADLINE_HORIZON_S, "K": PERSIST_CELL},
               "stored_single_seed"],
         held_fixed={"coin": BTC, "horizon_s": S.HEADLINE_HORIZON_S,
                     "wallet floor (fills in EACH half)": PERSIST_CELL}),
]


# Axes the artifacts sweep whose parameter has NO declaration in settings.py. Reported
# separately and never mixed with the settings above, because a value with no home cannot
# have a value in force and cannot be said to have moved away from one. This is the same
# gap as an unswept setting, seen from the other side: there, a declaration with no
# measurement; here, a measurement with no declaration.
UNDECLARED_SPECS = [
    dict(axis="maker_fee_bps", file=MAKER, kind="keys",
         quantity="maker_net_vw_bps",
         means="volume-weighted net maker result in basis points. The fee tier moves it "
               "further than any declared setting does, and no file declares the tier.",
         at=["baseline_net", "pooled", "by_horizon", HEAD_H, MID, "by_fee_tier"],
         label_re=r"^(.+)$", parse="text", leaf=["net_vw_bps"],
         candidate_value_at=["maker_fee_bps"],
         held_fixed={"horizon_s": S.HEADLINE_HORIZON_S, "lens": S.HEADLINE_LENS,
                     "population": "pooled over coins"}),
    dict(axis="quoter_model", file=BAKEOFF, kind="keys",
         quantity="quoter_net_vw_bps",
         means="net result in basis points of each quoting model in the bake-off. This "
               "axis is the OBJECT of the study rather than a nuisance setting, and it "
               "is listed here because it too has no declaration.",
         at=["quoters", HEAD_K], label_re=r"^(.+)$", parse="text",
         leaf=["net_by_coin", "pooled", "by_horizon", HEAD_H, MID, "by_fee_tier",
               BASE_TIER, "net_vw_bps"],
         held_fixed={"wallet floor (early fills)": S.RANK_FLOOR_FILLS,
                     "horizon_s": S.HEADLINE_HORIZON_S, "lens": S.HEADLINE_LENS,
                     "fee tier": BASE_TIER, "population": "pooled over coins"}),
    dict(axis="deploy_grid_fill_widen_cost", file=MAKER_B2, kind="keys",
         quantity="deployable_net_bps",
         means="net result in basis points of the deployable widening policy across its "
               "grid. One label carries three parameters at once -- retained benign "
               "fills, widening in basis points, and the cost multiplier -- which is why "
               "no single number here can be traced back to one parameter.",
         at=["by_measure", MID, "surface", "b2_surface"],
         label_re=r"^(f[\d.]+_w[\d.]+_c[\d.]+)$", parse="text",
         leaf=["by_fee_tier", BASE_TIER, "b2_net_bps"],
         held_fixed={"lens": S.HEADLINE_LENS, "fee tier": BASE_TIER}),
]


# Which declaration supplies the candidates of which setting. A name here is an
# identifier in settings.py, checked below, never a value.
CANDIDATE_SET_OF = {
    "HEADLINE_HORIZON_S": "LADDER_S",
    "COMPANION_HORIZON_S": "LADDER_S",
    "HEADLINE_LENS": "LENSES",
    "RANK_FLOOR_FILLS": "RANK_FLOOR_SENSITIVITY",
    "WHALE_DROP_K": "WHALE_DROP_LADDER",
    # These two ARE their own candidate sets: the declaration is the tuple of rungs.
    "PERSISTENCE_FLOOR_FILLS": "PERSISTENCE_FLOOR_FILLS",
    "WHALE_DROP_CRITERIA": "WHALE_DROP_CRITERIA",
}

# Why a setting has no candidate sweep, stated once per setting rather than left to be
# inferred from an absence. An absence with no reason beside it reads exactly like an
# oversight, and two of these are oversights while the rest are not.
NO_SWEEP_REASON = {
    "LADDER_S": "not a setting in its own right: it is the candidate set of "
                "HEADLINE_HORIZON_S and COMPANION_HORIZON_S, and it is an enumeration of "
                "the columns the marked tape carries rather than a choice.",
    "LENSES": "not a setting in its own right: it is the candidate set of HEADLINE_LENS, "
              "and it enumerates the two reference prices the tape carries.",
    "RANK_FLOOR_SENSITIVITY": "not a setting in its own right: it is the candidate set of "
                              "RANK_FLOOR_FILLS.",
    "WHALE_DROP_LADDER": "not a setting in its own right: it is the candidate set of "
                         "WHALE_DROP_K.",
    "COMPANION_HORIZON_S": "swept by the same grid as HEADLINE_HORIZON_S and reported "
                           "there: the companion is a second READING of the horizon "
                           "sweep, not a second sweep.",
    "COIN_CODES_BY_ARTIFACT": "a property of each data file rather than a choice; there "
                              "is no alternative candidate to sweep, and a wrong map is "
                              "an error rather than a different setting.",
    "FIELD_SUFFIX_STYLE": "a naming convention. It moves no number, so a sweep of it has "
                          "nothing to report.",
    "PERM_FAMILY_SIZE": "counted by its producer from the cells actually tested, so its "
                        "value is an observation rather than a choice. No candidate set "
                        "exists.",
    "FDR_ALPHA": "NO CANDIDATE SET IS DECLARED and no artifact reports a second level. "
                 "What every verdict would become at a different level is therefore "
                 "unmeasured, and the level enters every FDR verdict in the work.",
    "PERM_FLOOR_MARGIN": "NO CANDIDATE SET IS DECLARED. It is a stated judgement that "
                         "doubles the permutation budget, and no artifact reports what "
                         "the budget would be without it.",
    "N_PERM": "no candidate set. Its effect is not a value shift but a FLOOR on what a "
              "p-value can express, so a sweep would answer a different question than "
              "the one the budget was chosen on.",
    "N_BOOT": "no candidate set. Its effect is on the width of an interval rather than "
              "on a point estimate; no artifact reports the interval at a second budget.",
    "MASTER_SEED": "swept indirectly and only in one file: the forty fold splits in "
                   "i3_book_nonrecoverability_results.json, summarised there rather than "
                   "stored per seed. No other producer reports a second seed.",
    "RELIABILITY_SEED": "NO SWEEP EXISTS. Its consumers are the split-half reliability "
                        "estimators, and no artifact in the repository reports a "
                        "reliability at a second seed.",
    "RELIABILITY_SEED_SPREAD_SD": "NOT A SETTING BUT A MEASUREMENT OF ONE, and settings.py "
                                  "records that nothing in this repository produces it. "
                                  "It is the result the RELIABILITY_SEED sweep would have "
                                  "written if that sweep were a script.",
    "DAY_FLOOR_FILLS": "NO CANDIDATE SET IS DECLARED and settings.py records no basis for "
                       "the value either. Both gaps are open at once.",
    "MIN_COMMON_WALLETS": "no candidate set, and no consumer: settings.py records that "
                          "nothing reads this declaration yet, so there is nothing for a "
                          "sweep to move.",
}


def _check_declarations():
    """Every name this module points at must exist in settings.py. Fail on import.

    A spec naming a setting that no longer exists would produce rows filed under nothing,
    and a reason written for a deleted declaration outlives it and misleads the next
    reader. Both are caught here rather than in the output.
    """
    known = set(S.SETTING_BASIS)
    for spec in SPECS:
        name = spec["setting"]
        if name not in known:
            raise RuntimeError(f"a spec files rows under {name!r}, which settings.py "
                               f"does not declare")
        if not hasattr(S, name):
            raise RuntimeError(f"settings.py has no attribute {name!r}")
    for name, source in CANDIDATE_SET_OF.items():
        for who in (name, source):
            if not hasattr(S, who):
                raise RuntimeError(f"CANDIDATE_SET_OF names {who!r}, which settings.py "
                                   f"does not declare")
    for name in NO_SWEEP_REASON:
        if name not in known:
            raise RuntimeError(f"NO_SWEEP_REASON explains {name!r}, which settings.py no "
                               f"longer declares; a reason must not outlive its setting")


# =====================================================================
# 5. BUILDING THE ROWS.
# =====================================================================

# Where each source was actually opened, filled by _load as it opens it and read by
# main when the run records what it read.
#
# WHY THE PATH IS RECORDED RATHER THAN REBUILT LATER. Handing artifact.write the eight
# bare names left four of them written into the provenance block as present=false with
# no hash, while the run had just read all eight. The two sides resolve a bare name
# differently and neither is wrong about its own question: reading goes through
# artifact.results_dir, which LOOKS one directory down and so finds a source in another
# group, and recording goes through artifact.input_record, which resolves a relative
# name against this producer's own directory and then the working directory and does
# not look down at all. Four of the eight sit in markout, identity and quoters, so
# exactly those four came out absent. A rerun on the bare names writes the same four
# absences again, which is why the fix is here and not in either of those two functions:
# what a producer records must be what it opened, and only the producer knows that.
_OPENED = {}


def _load(name):
    """One source artifact, read from the group directory that holds it.

    The eight sources sit in five different groups, so the directory is looked up by
    the name rather than assumed to be this file's own. Nothing absolute is recorded:
    artifact.results_dir builds the directory from its own module location, and the
    path kept for the provenance record is made relative to this file's own directory
    before it is kept. The file name stays the last component of the join, because that
    is what the build graph folds each input edge out of, and _load_sources below
    explains why every caller passes a constant.
    """
    path = os.path.join(artifact.results_dir(name), name)
    _OPENED[name] = os.path.relpath(path, HERE)
    return json.load(open(path, encoding="utf-8"))


def _load_sources():
    """The eight source artifacts, read by name, one call per name. Not a loop.

    WHY THIS IS WRITTEN OUT INSTEAD OF LOOPED OVER SOURCES. build.py derives the
    dependency graph by reading this tree's syntax, taking the argument of a read as an
    input edge and folding it to a constant string. A path built from a loop variable
    folds to nothing, and a call that folds to nothing produces NO EDGE AT ALL -- the
    graph loses the dependency in silence rather than reporting it. That is not a
    hypothetical: fifty-one operations across twenty-four scripts were once invisible to
    the graph while the picture was believed complete, and the unresolved ceiling stands
    at zero so the gap cannot come back. The loop that stood here cost eight edges.

    The alternative allowed for a genuinely unfoldable path is a hand-written entry in
    build_declarations.py. It is not used here because it does not have to be: an edge
    that CAN be derived from the code should be, since a derived edge cannot go stale
    and a declared one goes stale silently. Written out, each read folds to the constant
    beside it, and the graph gets all eight.

    The price of writing them out is that this list could drift from SOURCES, so it is
    checked against it rather than trusted.
    """
    documents = {
        WS1: _load(WS1),
        I3: _load(I3),
        T3: _load(T3),
        M11: _load(M11),
        MAKER: _load(MAKER),
        MAKER_B2: _load(MAKER_B2),
        BAKEOFF: _load(BAKEOFF),
        AS_QUOTER: _load(AS_QUOTER),
    }
    if set(documents) != set(SOURCES):
        raise RuntimeError(
            f"the reads written out above and SOURCES disagree: "
            f"{sorted(set(SOURCES) - set(documents))} are declared as inputs and never "
            f"read, {sorted(set(documents) - set(SOURCES))} are read and never declared. "
            f"A source added to SOURCES needs its own read here, because a read written "
            f"as a loop over SOURCES folds to no path and disappears from the build "
            f"graph without failing")
    return documents


def _fingerprint_of(document):
    """The settings fingerprint, found in either of the two placements that exist here.

    Seven of the eight sources carry it inside _meta, where artifact.py puts it. One
    carries it flat at the top level, because it predates that module. Reading only the
    canonical placement would report the eighth as having no fingerprint at all, which is
    a different and worse statement than the truth.
    """
    meta = document.get("_meta", {})
    if isinstance(meta, dict) and "settings_fingerprint" in meta:
        return meta["settings_fingerprint"], "_meta.settings_fingerprint"
    if "settings_fingerprint" in document:
        return (document["settings_fingerprint"],
                "settings_fingerprint at the top level, flat: this artifact pre-dates "
                "artifact.py and was not written through it")
    return None, "absent"


def _in_force(setting):
    value = getattr(S, setting)
    return list(value) if isinstance(value, tuple) else value


def _in_force_candidate(setting):
    """The candidate the work currently runs at, and the rule that picks it.

    A scalar declaration is its own answer. A tuple declaration is not: settings.py
    states that the persistence floor's lower rung is the reported cell and the higher
    one is the check, so the cell is the minimum; and it states no primary for the four
    whale-drop criteria, so that one has no answer and says so instead of inventing one.
    """
    value = getattr(S, setting)
    if not isinstance(value, tuple):
        return value, "the declaration itself"
    if setting == "PERSISTENCE_FLOOR_FILLS":
        return min(value), ("the lower rung: settings.py states the lower is the "
                            "reported cell and the higher is the small-sample check")
    return None, ("the declaration is a set of candidates and names no primary among "
                  "them, so no candidate is in force")


def _rows_from_spec(spec, document, setting_key="setting"):
    """Every row one spec produces. Candidates are discovered, never listed."""
    name = spec[setting_key]
    rows = []
    common = dict(
        **{setting_key: name},
        quantity=spec["quantity"],
        quantity_means=spec["means"],
        source_file=spec["file"],
        held_fixed=dict(spec.get("held_fixed", {})),
        origin="extracted",
        origin_means="lifted verbatim from the artifact named; no value in this file is "
                     "recomputed from data",
    )

    if spec["kind"] == "point":
        path = list(spec["path"])
        if "candidate_at" in spec:
            candidate = _dig(document, list(spec["candidate_at"]))
            candidate_source = ("read from the artifact at " +
                                _path_text(spec["candidate_at"]))
        else:
            candidate = spec["candidate"]
            candidate_source = "stated by the spec"
        rows.append(dict(common, candidate=candidate, candidate_label_in_file=None,
                         candidate_from=candidate_source,
                         candidate_kind=spec.get("candidate_kind", "value"),
                         candidate_note=spec.get("candidate_note"),
                         label_rule="n/a: this rung is stored in a shape of its own",
                         value=_dig(document, path), key_path=_path_text(path),
                         key_path_parts=_path_parts(path)))
        return rows

    if spec["kind"] == "keys":
        # Read here rather than above: a "field" spec carries no label spelling at all,
        # because its candidates are field VALUES and not key names, and reading a label
        # rule it does not have would fail it with a KeyError that says nothing.
        parse = PARSERS[spec["parse"]]
        pattern = re.compile(spec["label_re"])
        node = _dig(document, list(spec["at"]))
        if not isinstance(node, dict):
            raise Missing(f"{_path_text(spec['at'])}: an axis of sibling keys needs a "
                          f"mapping, found {type(node).__name__}")
        labels = [k for k in node if pattern.match(str(k))]
        if not labels:
            raise Missing(
                f"{_path_text(spec['at'])}: no key matches {spec['label_re']!r}; the "
                f"keys present are {sorted(node)[:10]}. A predicate that matches nothing "
                f"is reported as a failure, never as an empty sweep")
        for label in labels:
            candidate = parse(pattern.match(str(label)).group(1))
            path = list(spec["at"]) + [label] + list(spec["leaf"])
            row = dict(common, candidate=candidate, candidate_label_in_file=label,
                       candidate_from="discovered among the sibling keys at " +
                                      _path_text(spec["at"]),
                       candidate_kind="value", candidate_note=None,
                       label_rule=f"{spec['label_re']} parsed as {spec['parse']}",
                       value=_dig(document, path), key_path=_path_text(path),
                       key_path_parts=_path_parts(path))
            if "candidate_value_at" in spec:
                row["candidate_parameter"] = _dig(
                    document, list(spec["at"]) + [label] + list(spec["candidate_value_at"]))
                row["candidate_parameter_key"] = _path_text(spec["candidate_value_at"])
            rows.append(row)
        return rows

    if spec["kind"] == "field":
        node = _dig(document, list(spec["at"]))
        if not isinstance(node, list):
            raise Missing(f"{_path_text(spec['at'])}: an axis of field values needs a "
                          f"list of records, found {type(node).__name__}")
        where = dict(spec["where"])
        field = spec["field"]
        found = []
        for record in node:
            if isinstance(record, dict) and _match(record, where) and field in record:
                if record[field] not in found:
                    found.append(record[field])
        if not found:
            raise Missing(
                f"{_path_text(spec['at'])}: no record satisfies {where} and carries "
                f"{field!r}. The fields a record does carry are "
                f"{sorted(node[0]) if node and isinstance(node[0], dict) else 'none'}")
        for candidate in found:
            filt = dict(where, **{field: candidate})
            path = list(spec["at"]) + [filt] + list(spec["leaf"])
            rows.append(dict(common, candidate=candidate, candidate_label_in_file=None,
                             candidate_from=f"discovered as a distinct value of the "
                                            f"{field!r} field inside the list at " +
                                            _path_text(spec["at"]),
                             candidate_kind="value", candidate_note=None,
                             label_rule=f"the whole field {field!r} of a record, joined "
                                        f"on {sorted(where)}",
                             value=_dig(document, path), key_path=_path_text(path),
                             key_path_parts=_path_parts(path)))
        return rows

    raise ValueError(f"unknown spec kind {spec['kind']!r} for {name}")


def _numeric(value):
    """A value a spread may be taken over, or None. bool is not a number here.

    A bool passes isinstance(x, int) in Python and would enter a spread as 0 or 1, which
    is a number about a flag rather than about a quantity.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(float(value)) else None


def _spread(group, in_force_candidate):
    """How far the quantity travels across the candidates of one setting.

    Two different questions are answered separately rather than merged, because the
    obvious phrase "the spread between the extreme candidates" means both and they are
    not the same number when the quantity is not monotone in the candidate:

      value_range        the distance between the largest and the smallest VALUE, which
                         is what the setting can cost at worst.
      across_candidates  the value at the highest candidate minus the value at the
                         lowest, which is the direction and size of the trend, and which
                         only exists when the candidates can be ordered.

    Non-finite values are dropped with a count kept. Two runs that both hold a nan would
    otherwise compare unequal, since nan is not equal to itself, and a min over a column
    holding one is not a minimum.
    """
    usable, dropped = [], 0
    for row in group:
        v = _numeric(row["value"])
        if v is None:
            dropped += 1
        else:
            usable.append((row["candidate"], v, row))
    out = {
        "n_candidates": len(group),
        "n_usable": len(usable),
        "n_non_numeric_or_non_finite": dropped,
        "candidates": [r["candidate"] for r in group],
    }
    if len(usable) < 2:
        out["spread"] = None
        out["spread_absent_because"] = (
            "fewer than two candidates carry a finite number, so there is no distance to "
            "report. A single-candidate group is the finding rather than a defect: it "
            "says the axis exists in the declaration and not in the artifact")
        if usable:
            out["only_value"] = usable[0][1]
        return out

    lo = min(usable, key=lambda t: t[1])
    hi = max(usable, key=lambda t: t[1])
    out["value_min"] = {"candidate": lo[0], "value": lo[1],
                        "key_path": lo[2]["key_path"]}
    out["value_max"] = {"candidate": hi[0], "value": hi[1],
                        "key_path": hi[2]["key_path"]}
    out["value_range"] = hi[1] - lo[1]
    out["value_range_means"] = ("the largest minus the smallest value over the "
                                "candidates. This is what the setting costs at worst.")

    # An exact zero is the one reading of this table that must not be taken at face
    # value, and it is flagged here rather than left to whoever reads the row. Every
    # quantity in this file is a volume-weighted mean, a rank correlation or a Gini over
    # hundreds of thousands of rows. Two such numbers agreeing to the last bit is not a
    # small effect measured accurately; it is the same array reaching the estimator
    # twice, which means the candidate never entered the computation. The distinction is
    # not cosmetic: read as insensitivity it says the setting is safe to ignore, and read
    # correctly it says the sweep has not happened yet.
    if out["value_range"] == 0.0:
        out["value_range_is_exactly_zero"] = True
        out["exact_zero_means"] = (
            "the candidates are bit-identical, so this row measures a code path and not "
            "a market. Before reading it as insensitivity, open the producer and check "
            "that its arm reaches this quantity: the usual cause is a per-candidate mask "
            "computed and then not read, so every arm sees one input.")

    orderable = all(isinstance(c, (int, float)) and not isinstance(c, bool)
                    for c, _, _ in usable)
    if orderable:
        first = min(usable, key=lambda t: t[0])
        last = max(usable, key=lambda t: t[0])
        out["at_lowest_candidate"] = {"candidate": first[0], "value": first[1]}
        out["at_highest_candidate"] = {"candidate": last[0], "value": last[1]}
        out["across_candidate_range"] = last[1] - first[1]
        out["across_candidate_range_means"] = (
            "the value at the highest candidate minus the value at the lowest. Differs "
            "from value_range whenever the quantity is not monotone in the candidate.")
    else:
        out["across_candidate_range"] = None
        out["across_candidate_range_absent_because"] = (
            "the candidates are not orderable, so there is no highest and no lowest")

    at_in_force = [(c, v) for c, v, _ in usable if c == in_force_candidate]
    if at_in_force:
        base = at_in_force[0][1]
        out["value_at_in_force_candidate"] = base
        out["relative_to_in_force"] = (
            abs(out["value_range"]) / abs(base) if base != 0 else None)
        out["relative_to_in_force_means"] = (
            "the value range as a multiple of the value the work currently reports. "
            "Absent where that value is zero, which is a division and not a finding.")
    else:
        out["value_at_in_force_candidate"] = None
        out["in_force_candidate_absent_because"] = (
            f"the candidate in force ({in_force_candidate!r}) is not among the "
            f"candidates this artifact carries, so the sweep does not pass through the "
            f"cell the work reports")
    return out


# =====================================================================
# 6. THE CENSUS OF SETTINGS WITH NO SWEEP -- the more useful half of the output.
# =====================================================================

def _coverage(rows_by_setting):
    """Every setting settings.py declares, with its sweep or with the reason it has none.

    Ordered so that the settings with no sweep at all come first. An unswept setting is
    an assumption nobody has priced, and burying it under the ones that are measured is
    how it stays unpriced.
    """
    entries = []
    for name, basis in S.SETTING_BASIS.items():
        if basis["kind"] == "not_a_setting":
            continue
        rows = rows_by_setting.get(name, [])
        in_force_value = _in_force(name)
        in_force_cand, in_force_rule = _in_force_candidate(name)
        candidate_set_name = CANDIDATE_SET_OF.get(name)
        declared = None
        if candidate_set_name is not None:
            value = getattr(S, candidate_set_name)
            declared = list(value) if isinstance(value, tuple) else [value]
        found = []
        for row in rows:
            if row["candidate"] not in found:
                found.append(row["candidate"])
        entry = {
            "setting": name,
            "basis_kind": basis["kind"],
            "state": S.SETTING_STATE.get(name, "not recorded in SETTING_STATE"),
            "value_in_force": in_force_value,
            "candidate_in_force": in_force_cand,
            "candidate_in_force_rule": in_force_rule,
            "candidate_set_declared_by": candidate_set_name,
            "candidates_declared": declared,
            "candidates_found_in_artifacts": found,
            "n_rows": len(rows),
            "has_sweep": bool(rows),
        }
        if declared is not None:
            entry["declared_but_no_value_found"] = [
                c for c in declared if c not in found]
            entry["found_but_not_declared"] = [
                c for c in found if c not in declared]
        if not rows:
            entry["no_sweep_because"] = NO_SWEEP_REASON.get(
                name, "NOT EXPLAINED. No reason is on record, which is itself the "
                      "finding: an absence with no reason beside it cannot be told "
                      "apart from an oversight.")
        entries.append(entry)
    entries.sort(key=lambda e: (e["has_sweep"], e["setting"]))
    return entries


# =====================================================================
# 7. RUN.
# =====================================================================

def build():
    _check_declarations()
    documents = _load_sources()

    rows, failures = [], []
    for spec in SPECS:
        try:
            rows.extend(_rows_from_spec(spec, documents[spec["file"]]))
        except (Missing, KeyError, TypeError, ValueError) as exc:
            failures.append({"setting": spec["setting"], "file": spec["file"],
                             "quantity": spec["quantity"], "error": str(exc)})

    undeclared_rows, undeclared_failures = [], []
    for spec in UNDECLARED_SPECS:
        try:
            for row in _rows_from_spec(spec, documents[spec["file"]], setting_key="axis"):
                row["axis"] = spec["axis"]
                row["setting"] = None
                row["setting_absent_because"] = (
                    "this axis is swept by the artifact and declared by no setting, so "
                    "it has no value in force to move away from")
                undeclared_rows.append(row)
        except (Missing, KeyError, TypeError, ValueError) as exc:
            undeclared_failures.append({"axis": spec["axis"], "file": spec["file"],
                                        "error": str(exc)})

    # Each row's relation to the declaration. Decided on the CANDIDATE, which is a whole
    # field by construction -- an integer floor, an integer horizon, a lens name. Never
    # on the value: every numeric row holds a float, and two files store one quantity at
    # two precisions, so a value can never decide whether two rows are the same cell.
    rows_by_setting = {}
    for row in rows:
        name = row["setting"]
        in_force_cand, in_force_rule = _in_force_candidate(name)
        row["value_in_force"] = _in_force(name)
        row["candidate_in_force"] = in_force_cand
        row["candidate_in_force_rule"] = in_force_rule
        row["is_the_candidate_in_force"] = (
            None if in_force_cand is None else row["candidate"] == in_force_cand)
        row["setting_state"] = S.SETTING_STATE.get(name, "not recorded in SETTING_STATE")
        row["setting_basis_kind"] = S.SETTING_BASIS[name]["kind"]
        rows_by_setting.setdefault(name, []).append(row)

    groups = {}
    for row in rows:
        groups.setdefault((row["setting"], row["quantity"], row["source_file"]),
                          []).append(row)
    undeclared_groups = {}
    for row in undeclared_rows:
        undeclared_groups.setdefault((row["axis"], row["quantity"], row["source_file"]),
                                     []).append(row)

    spreads = []
    for (setting, quantity, source), group in groups.items():
        in_force_cand, _ = _in_force_candidate(setting)
        block = {"setting": setting, "quantity": quantity, "source_file": source,
                 "quantity_means": group[0]["quantity_means"],
                 "held_fixed": group[0]["held_fixed"],
                 "candidate_in_force": in_force_cand,
                 "computed_here": True,
                 "computed_here_means": "the distance is arithmetic over values this file "
                                        "extracted; no value in the row set is computed"}
        block.update(_spread(group, in_force_cand))
        spreads.append(block)
    spreads.sort(key=lambda b: (b["setting"], b["quantity"], b["source_file"]))

    undeclared_spreads = []
    for (axis, quantity, source), group in undeclared_groups.items():
        block = {"axis": axis, "quantity": quantity, "source_file": source,
                 "quantity_means": group[0]["quantity_means"],
                 "held_fixed": group[0]["held_fixed"], "computed_here": True}
        block.update(_spread(group, None))
        undeclared_spreads.append(block)
    undeclared_spreads.sort(key=lambda b: (b["axis"], b["quantity"]))

    source_scopes = {}
    for name, document in documents.items():
        fingerprint, placement = _fingerprint_of(document)
        meta = document.get("_meta", {})
        source_scopes[name] = {
            "scope_as_the_producer_wrote_it": meta.get("scope") if isinstance(meta, dict)
                                              else None,
            "scope_absent_because": None if (isinstance(meta, dict) and "scope" in meta)
                                    else "this artifact pre-dates artifact.py and carries "
                                         "no scope block",
            "settings_fingerprint_placement": placement,
            "settings_fingerprint": fingerprint,
        }

    coverage = _coverage(rows_by_setting)
    unswept = [e["setting"] for e in coverage if not e["has_sweep"]]

    payload = {
        "object": ("SENSITIVITY ROLL-UP: one row per (setting, candidate, quantity), "
                   "saying what a reported number becomes when a setting moves to another "
                   "candidate. Every value is lifted from an existing artifact; nothing "
                   "here is recomputed from market data."),
        "how_to_read": {
            "a_row": "one candidate of one setting, with every other axis of that "
                     "artifact pinned at held_fixed, and the file and key path the value "
                     "came from.",
            "a_group": "rows sharing a setting, a quantity and a source file. Only "
                       "inside a group may two rows be compared: the eight sources do "
                       "not share a population, a window or a coin set, and their own "
                       "scope blocks are reproduced under source_scopes.",
            "the_spread": "value_range is what the setting costs at worst; "
                          "across_candidate_range is the trend from the lowest candidate "
                          "to the highest, and differs whenever the quantity is not "
                          "monotone in the candidate.",
            "the_useful_half": "coverage lists every declared setting, unswept ones "
                               "first. A setting with no sweep is an assumption whose "
                               "price nobody has measured.",
        },
        "counts": {
            "settings_declared": len([n for n, b in S.SETTING_BASIS.items()
                                      if b["kind"] != "not_a_setting"]),
            "settings_with_a_sweep": len([e for e in coverage if e["has_sweep"]]),
            "settings_without_a_sweep": len(unswept),
            "settings_without_a_sweep_named": unswept,
            "rows": len(rows),
            "groups": len(spreads),
            "source_artifacts": len(SOURCES),
            "undeclared_axes": len(undeclared_spreads),
            "undeclared_rows": len(undeclared_rows),
            "groups_with_an_exactly_zero_range": len(
                [b for b in spreads if b.get("value_range_is_exactly_zero")]),
            "groups_with_an_exactly_zero_range_named": [
                f"{b['setting']} / {b['quantity']} / {b['source_file']}"
                for b in spreads if b.get("value_range_is_exactly_zero")],
        },
        "coverage": coverage,
        "spread": spreads,
        "rows": sorted(rows, key=lambda r: (r["setting"], r["quantity"],
                                            r["source_file"], str(r["candidate"]))),
        "axes_not_declared": {
            "what_this_is": ("axes the artifacts sweep whose parameter has no "
                             "declaration in settings.py. The mirror image of an unswept "
                             "setting: there, a declaration with no measurement; here, a "
                             "measurement with no declaration. Neither can be compared "
                             "to a value in force, because there is none."),
            "spread": undeclared_spreads,
            "rows": undeclared_rows,
            "failures": undeclared_failures,
        },
        "source_scopes": source_scopes,
        "failures": failures,
        "failures_means": ("a spec whose path did not resolve. Reported rather than "
                           "skipped: a sweep that silently returns nothing is "
                           "indistinguishable from a setting that does not move a "
                           "number, and this project has read one as the other."),
    }
    return payload, documents


def main():
    started = artifact.start_clock()
    payload, _ = build()
    counts = payload["counts"]

    scope = {
        "population": (
            f"no market data: {counts['rows']} values lifted from "
            f"{counts['source_artifacts']} existing artifacts, forming "
            f"{counts['groups']} comparable groups over "
            f"{counts['settings_with_a_sweep']} of the {counts['settings_declared']} "
            f"settings declared in settings.py. The populations the values were computed "
            f"over are NOT one population and are not merged anywhere in this file; each "
            f"source's own scope block is reproduced verbatim under source_scopes."),
        "window": (
            "the union of the source windows, which is not one window. Seven sources "
            "state their own window in their scope block and one pre-dates that block; "
            "all are reproduced under source_scopes. No row in this file is compared to "
            "a row from another file."),
        "coins": (
            "the union of the source coin sets, which is not one set: the trade-print "
            "and book sources carry two coins and the panel sources carry three. Each "
            "row names the coin it was pinned at under held_fixed where the source "
            "resolves by coin, and 'pooled over coins' where it does not."),
    }

    # The paths this run actually opened, in the order the sources are declared. Passed
    # instead of the bare names because a bare name is resolved by the recorder against
    # this file's own directory only, and four of the eight sources sit in other groups.
    # The check is here rather than trusted: an input whose path was never recorded
    # would be handed over as a bare name again and would be written down as absent,
    # which reads as a missing file rather than as a producer that forgot to say where
    # it looked.
    unopened = sorted(set(SOURCES) - set(_OPENED))
    if unopened:
        raise RuntimeError(
            f"{unopened} are declared in SOURCES and no path was recorded for them, so "
            f"this run cannot say where it read them; recording a bare name instead "
            f"writes present=false with no hash, which is a statement about a missing "
            f"file and not about a producer that did not look")
    opened = [_OPENED[name] for name in SOURCES]

    path = artifact.write(
        OUT_NAME, payload, script=__file__, inputs=opened, scope=scope,
        started=started,
        settings={"rollup_selects_no_setting":
                  "this file reads other artifacts and computes no number of its own. "
                  "The horizon and lens stated in this block are the DECLARATION; this "
                  "run spans every candidate of every axis it found, so neither is a "
                  "property of the artifact."},
        extra_meta={"reads_only": "every input is a results file; no data file is opened",
                    "recompute_cost": "seconds, because nothing is recomputed"})

    print(f"[sensitivity_rollup] {counts['rows']} rows over {counts['groups']} groups "
          f"from {counts['source_artifacts']} artifacts")
    print(f"[sensitivity_rollup] settings declared {counts['settings_declared']}, "
          f"with a sweep {counts['settings_with_a_sweep']}, "
          f"without {counts['settings_without_a_sweep']}")
    print(f"[sensitivity_rollup] no sweep: "
          f"{', '.join(counts['settings_without_a_sweep_named'])}")
    for block in payload["spread"]:
        rng = block.get("value_range")
        shown = "n/a" if rng is None else f"{rng:+.6g}"
        print(f"  {block['setting']:<26} {block['quantity']:<38} "
              f"{block['source_file']:<40} n={block['n_candidates']:<3} range={shown}")
    for block in payload["axes_not_declared"]["spread"]:
        rng = block.get("value_range")
        shown = "n/a" if rng is None else f"{rng:+.6g}"
        print(f"  [undeclared] {block['axis']:<30} {block['quantity']:<30} "
              f"n={block['n_candidates']:<3} range={shown}")
    if payload["failures"] or payload["axes_not_declared"]["failures"]:
        print(f"[sensitivity_rollup] FAILURES: {len(payload['failures'])} settings, "
              f"{len(payload['axes_not_declared']['failures'])} undeclared axes")
        for f in payload["failures"] + payload["axes_not_declared"]["failures"]:
            print("   ", json.dumps(f))
    print(f"[sensitivity_rollup] wrote {os.path.basename(path)}")


if __name__ == "__main__":
    main()
