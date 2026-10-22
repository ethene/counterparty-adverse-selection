#!/usr/bin/env python3
"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-07-30
References: none (repository hygiene gate over settings.py).

ONE HOME PER SETTING, AND THE CODE CANNOT BYPASS IT.

Why this gate exists. A setting that moves a reported number used to enter the code
as a SPELLING rather than as a parameter: a module-level literal, or a string inside
the line that read a column. Two consequences followed, and the second is the one
that costs. Editing the declaration propagated nowhere, so every site had to be
edited by hand and the same quantity drifted apart between files. And a wrong
setting does not break: the analytical files carry every window side by side, so
reading the wrong one raises nothing and returns a plausible number. A wrong setting
is a DIFFERENT VALID NUMBER, and only a declaration can tell the two apart.

settings.py is that declaration. This check enforces six properties of it.

  RULE 1  No file re-declares a load-bearing setting as a module-level literal.
          A consumer reads it from settings.py. A file that genuinely needs a
          different value binds it from settings.py and says in one line why, or it
          appears in ALLOW with the reason.

  RULE 2  No dictionary mixes a literal key with a key built from a constant that
          can equal it. When they collide the second write wins and one reported
          quantity disappears from the output file with nothing raised. This class
          cost the project the companion-window descriptive value in two artifacts.

  RULE 3  Every artifact that carries a settings fingerprint agrees with the current
          declaration, or names in the same block the setting it overrode. An
          artifact whose fingerprint silently disagrees is stale, and a number
          lifted out of it cannot be traced to the code that is on disk.

  RULE 4  No input is chosen by the state of the filesystem. Writing "read file A if
          it is on disk, else file B" makes the POPULATION a property of the machine
          rather than of a declaration, and the result file does not record which one
          it read. This happened here: probe_F_hlp_liq.py picked between two panels
          that differ by 14,020 rows and of which only one carries the liquidation
          column the block is about, so the same script on the same machine answered
          differently before and after a file was deleted. A test that GATES -- that
          returns an empty or absent result when the file is missing -- is the
          legitimate form and is not flagged, because it substitutes no population.

  RULE 5  The notebook's mirrored settings still agree with settings.py. The notebook
          also runs standalone from the published dataset, with no repository beside
          it to import, so it cannot read settings.py and has to repeat the few
          values it scores on. A repeat is safe exactly while it still agrees; the
          day it drifts it is a second home holding a different number, which is the
          whole defect. Agreement is checked by program, not asserted by a comment.

  RULE 6  Every site settings.SETTING_SITES declares still agrees with the declaration
          it names. RULE 1 counts places that hold a literal; it cannot see whether the
          literal is the SAME number, and a site that agrees today and drifts tomorrow
          leaves that count exactly where it was. settings.site_agrees answers the
          second question, and this rule ASKS it rather than repeating its comparison,
          because a check that reprints the logic it checks is blind to exactly the
          repair it should catch. A site can be compared only while a literal is left
          there, so the count is printed with the population it was taken over, and a
          second armed count says how many site keys resolved to no file at all.

Scope: every shipped .py, and the code cells of every shipped .ipynb. A checkout uses
its Git index and an extracted source ZIP uses the same shared recursive census. The
notebook is what a reader re-runs, so a literal there costs what a literal in a
script costs. Notebook findings are counted SEPARATELY from script findings
throughout, because the two debts are paid off by different work and a single blended
number cannot be lowered on purpose.

What this check deliberately does NOT catch, so nobody mistakes a green run for a
clean tree. It cannot see a name that states a setting its value does not come from
(a field called _10s fed by a 60 s variable): the defect lives in the relation
between two places and no single-file rule reaches it, and it has occurred here.
Within RULE 4 it sees a two-branch choice only: a fallback spelled `open(A) or
open(B)`, a try/except that falls back on an exception, and a glob that silently
returns whichever shards happen to be present all pass.

Read-only. Writes its verdict beside itself and exits non-zero on a regression.

    uv run --no-project python3 checks/chk_settings_home.py
"""
import ast
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT_JSON = os.path.join(HERE, "chk_settings_home_results.json")

sys.path.insert(0, ROOT)
import artifact                                               # noqa: E402
import settings as S                                          # noqa: E402
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from evidence import (notebook_cells, report_gate,            # noqa: E402
                      shipped_tree_files)

# The settings whose value moves a reported number, each with every spelling the tree
# has used for it. A literal declaration of any of these names outside settings.py is
# a second home for one quantity. The alias lists are the measured ones: a census by
# syntax tree found the seed under seven names and the wallet threshold under seven.
#
# WIDENED 2026-07-31, and the direction matters. Adding a spelling can only RAISE what
# this file reports, never lower it, so a widening is the one edit here that cannot be a
# way of making a red run green. Five spellings were added: BOOTSTRAP_N under the
# bootstrap budget, which the docstring's own "this figure is a floor, not a census"
# paragraph already named as the site nobody had ever counted; and K, KS, K_MIN and
# MIN_FILLS under the wallet floor, which between them held five fill floors in four
# files that no census in this repository had ever seen. All of them were migrated onto
# settings.py in the same action, which is why the count below did not move. Widening the
# list and leaving the sites would have been the honest half of the same work; doing only
# that would have raised the number with nothing having got worse, and the paragraph on
# the baselines says why that must not be read as a regression.
#
# WHAT THIS LIST STILL CANNOT SEE, measured the same day and stated so the next census
# does not have to rediscover it. ALLOW below keys on the FILE, so a file exempted for one
# setting is exempted for every setting it holds. Two files stand in it, and between them
# they carry six declarations the exemption was never argued for: probes/probe_G_horizon.py
# holds the seed 20260622 and the floors K_MIN 50 and K_HALF_MIN 20 beside the horizon grid
# it is exempt for, and forward_toxicity.py holds COINS and NPERM beside the calendar day
# split it is exempt for. Narrowing ALLOW to a (file, group) pair is the repair; it is not
# made here because both files would then report, and their debt has to be migrated before
# a baseline that may only fall can absorb it. Neither artifact records a runtime, so the
# price of migrating them is not a number this repository holds.
LOAD_BEARING = {
    "seed": ("SEED", "RNG_SEED", "BOOTSTRAP_SEED", "SEED_PERM", "SEED_BOOT",
             "RNG_CORR_SEED", "RNG_RELIABILITY", "MASTER_SEED", "RELIABILITY_SEED"),
    "permutations": ("N_PERM", "NPERM", "N_PERM_CORR", "N_PLACEBO", "N_SIZE_PLACEBO"),
    "bootstrap": ("N_BOOT", "N_BOOTSTRAP", "BOOTSTRAP_N"),
    "wallet_floor": ("K_LIST", "K_VALUES", "KMIN", "K_HEADLINE", "K_POOL",
                     "K_HALF_MIN", "K_DAY", "FILL_THRESHOLD_K", "MIN_RANK_TRADES",
                     "RANK_FLOOR_FILLS", "PERSISTENCE_FLOOR_FILLS", "DAY_FLOOR_FILLS",
                     "MIN_EARLY_TRADES", "K", "KS", "K_MIN", "MIN_FILLS"),
    "whale_drop": ("N_DROP_WHALES", "WHALE_DROP_K"),
    "coins": ("COINS", "PANEL_COINS", "DEFAULT_COINS", "COIN_CODES", "COIN_NAMES",
              "COIN_CODE", "COIN_NAME", "COIN_LABEL"),
    "horizon": ("HEADLINE_HORIZON", "HEADLINE_HORIZON_S", "HORIZONS", "HORIZONS_S",
                "LADDER_S", "COMPANION_HORIZON_S", "CONTRAST_HORIZON_S",
                "SCORE_HORIZON_S"),
    "fdr": ("FDR_ALPHA",),
    "split": ("EARLY_DAYS", "LATE_DAYS", "EARLY", "LATE"),
}
ALIAS_OF = {name: group for group, names in LOAD_BEARING.items() for name in names}

# ---- override hooks: watched under the setting they name, exempt only while empty ----
# Declared here, with the reason and the date, because a gate that quietly stops counting
# something is a gate nobody can audit. Added 2026-07-31.
#
# WHAT A HOOK IS. Some files carry a module-level name that a caller writes to before
# invoking an estimator -- panel_analyze.py sets t3_capacity's early half once per period
# -- and that defaults to None. Empty, the name holds the ABSENCE of an override and the
# consumer beside it reads settings.py, so there is no value here and nothing to drift.
# Bound to a value it is exactly the defect RULE 1 exists for.
#
# WHY THE EXEMPTION IS A VALUE TEST AND NOT A NAME TEST. gm_quoter.py renamed its two
# hooks to EARLY_DAYS_OVERRIDE / LATE_DAYS_OVERRIDE on 2026-07-30, and both sites left
# this check's count, because the new names were in no alias list. From that day nothing
# in the tree would have reported EARLY_DAYS_OVERRIDE = (4, 5, 6, 7, 8). Measured
# 2026-07-31 by grepping the tree for the suffixed names and finding them in no watch
# list here. Watching the suffixed names and exempting only the empty ones closes it.
#
# THE ASYMMETRY IS DELIBERATE. An UNSUFFIXED name bound to None still counts, because the
# name claims to BE the setting while holding no value, and a name that states a setting
# its value does not come from is the one defect this file's own docstring says it cannot
# see. The suffix is what makes the name honest. Six such sites remain in maker_econ.py,
# t1_toxicity_skew_backtest.py and t3_capacity.py; the rename is held until each of those
# producers is recomputed for a reason of its own, because editing a producer makes its
# artifact stale and a rename on its own does not earn the recompute that costs.
OVERRIDE_HOOK_SUFFIX = "_OVERRIDE"
ALIAS_OF.update({name + OVERRIDE_HOOK_SUFFIX: group
                 for group, names in LOAD_BEARING.items() for name in names})

# Files allowed to declare a load-bearing setting locally, each with the reason. A
# reason is about WHAT THE FILE COMPUTES, never about the edit being inconvenient.
ALLOW = {
    "settings.py": "the single source of truth itself",
    "persistence/forward_toxicity.py": "its window is a different one, so its day split is "
                           "calendar dates rather than days of the month",
    "probes/probe_G_horizon.py": "the horizon grid IS the object of study and is "
                                 "deliberately finer than the ladder",
}

# What the notebook is ALLOWED to repeat from settings.py, and the declaration each
# repeat has to agree with. The notebook is the one consumer that cannot import
# settings.py: it is published to run from the dataset alone, uploaded to a hosted
# notebook service such as Google Colab with no repository beside it, so the values it
# scores on have to be typed into a cell.
# That makes it the one place where a second home is legitimate -- and the one place
# where drift is invisible, because nothing else in the tree moves when it happens.
# It already has: the notebook kept scoring on the retired 60 s window after the
# repository moved to 10 s, and its own saved checks passed on the old numbers.
#
# So the exemption is not "the notebook may declare settings". It is "the notebook may
# MIRROR these named settings, and the mirror is verified against the declaration on
# every run". Each entry maps the notebook's name to how it is checked.
NOTEBOOK_MIRROR = {
    "SCORE_HORIZON_S": ("value", "HEADLINE_HORIZON_S"),
    "LADDER_S": ("value", "LADDER_S"),
    "COMPANION_HORIZON_S": ("value", "COMPANION_HORIZON_S"),
    "K_LIST": ("value", "PERSISTENCE_FLOOR_FILLS"),
    "MIN_EARLY_TRADES": ("value", "RANK_FLOOR_FILLS"),
    # The day halves are checked by RULE, not by value. settings.split_early_late is a
    # function of the days present precisely because no tuple is right for every
    # window, so there is no tuple in settings.py to compare against. What is checked
    # instead is that the notebook's own two tuples are the split that function
    # returns for the union of them: the cut can then move only by moving the rule.
    "EARLY_DAYS": ("split", "early"),
    "LATE_DAYS": ("split", "late"),
}

# Debt standing against the gate on the day it was introduced, 2026-07-30. Every one
# is a consumer still declaring its own literal instead of reading settings.py. The
# only legitimate edit to this number is DOWNWARD, with the migration that earned the
# reduction named in the commit. Raising it to turn a red run green defeats the gate.
#
# The baselines below are per SCOPE, and deliberately not one blended number. Script
# debt is paid off by migrating a consumer to settings.py; notebook debt is paid off
# by mirroring or by deleting a cell literal. Blending them would make either debt
# reducible by work on the other, and neither could then be driven to zero on purpose.
BASELINE_RULE1 = 0       # lowered 2026-08-12 from 1, and the one site it was holding
                         # open is gone: it was a classifier seed in a module that is
                         # no longer part of this repository, and before it left it had
                         # been migrated to settings.seed_for and rerun, with no payload
                         # value moving. Below is what the line said when it stood at 1.
                         #
                         # Lowered 2026-07-31 from 7, and this is the floor rather than
                         # a resting point. The six sites that stood before it were
                         # override hooks bound to None in maker_econ.py,
                         # t1_toxicity_skew_backtest.py and t3_capacity.py, and they
                         # were repaired by NAME rather than forgiven by predicate:
                         # all three now spell them EARLY_DAYS_OVERRIDE and
                         # LATE_DAYS_OVERRIDE, the spelling gm_quoter.py adopted
                         # first, and every suffixed name is watched here and exempt
                         # only while it holds nothing. The rename was proved
                         # number-neutral before it landed, on seven window shapes and
                         # on the injected path panel_analyze.py takes, with the
                         # comparator calibrated to say "different" on a deliberately
                         # wrong split. The one site left was the classifier seed
                         # named above: settings.py already declared the same value
                         # for that purpose, so migrating it moved no number. Only
                         # ever lower this line.
                         # Old note, kept because it dates the previous step: lowered
                         # 2026-07-31 from 24, and what the last seven are is
                         # the part to read before the number. SIX of them are bound to
                         # None -- the early and late halves in maker_econ.py,
                         # t1_toxicity_skew_backtest.py and t3_capacity.py -- and None
                         # declares no value at all. Those are override hooks whose
                         # consumer reads settings.split_early_late when nothing is
                         # injected, so they are second homes to the predicate and to
                         # nothing else. They are counted anyway, because the predicate
                         # is `ast.literal_eval succeeds` and narrowing it to exclude
                         # None would be a judgement smuggled into a measurement; the
                         # artifact carries the value and the kind of every site instead,
                         # so a reader can tell a live second home from a paid-off one
                         # without opening six files.
                         #
                         # The SEVENTH holds a number: the classifier seed named at
                         # the top of this note.
                         #
                         # So the rest of the debt is discharged. The last live site,
                         # the seed in i5_exclusion.py, moved on 2026-07-31: the
                         # declared value already equalled the literal, 20260619 both
                         # sides, and the artifact reproduced with 454 leaves and none
                         # of them moved. Only ever lower this line.
# Superseded reasoning, kept because it explains how the debt was read down:
#                        # lowered 2026-07-31 from 55, earlier the same day from 76, and
                         # on 2026-07-30 from 118. Only ever lower it.
                         #
                         # THE 55 TO 24 DROP RESTED ON A FINDING ABOUT THE OTHER 31, and
                         # the finding is worth more than the number. Parsing all 55 sites
                         # and comparing each literal against what settings.py declared
                         # gave one match and 43 differences. So this was never a naming
                         # debt waiting to be typed away: a mechanical migration would
                         # have moved 43 figures at once, and only a recompute would have
                         # said so. The differences were the code being right and the
                         # declaration being the wrong shape. Seeds are 20260619, 21, 22
                         # and 23, deliberately distinct so two scripts never draw the
                         # same stream; the wallet floor is a grid of three or five values
                         # in the code against a single value declared. settings.py was
                         # taught to declare a seed per purpose and a sweep beside its
                         # headline point, after which the declared value equalled the
                         # local one at 47 of 55 sites, and only then was anything moved.
                         # Every moved site was proved equal first and diffed after:
                         # sixteen artifacts, no payload value moved.
                         #
                         # WHAT THE REMAINING 24 ARE, counted on 2026-07-31 from this
                         # check's own findings rather than estimated. Seven seed literals
                         # in seven files; eight early and late halves of the window in
                         # four; three coin sets in three; two per-wallet fill thresholds
                         # in one; two bootstrap budgets in two; one permutation budget;
                         # one scoring window.
                         #
                         # THIS FIGURE IS A FLOOR, NOT A CENSUS. The capacity node spells
                         # its bootstrap budget under a name this check's alias list does
                         # not carry, so at least one real site has never been counted
                         # here. Extending the alias list will RAISE the measured number
                         # without anything having got worse, and that rise must not be
                         # mistaken for a regression.
# ARMED at zero on 2026-07-30, when the six colliding sites in the two ks2 files were
# repaired and the descriptive quantity of the companion window came back into both
# artifacts. Zero is the only defensible baseline here, because a collision does not
# degrade a number, it DELETES one: the literal key and the key built from a constant
# resolve to the same string and the second write silently replaces the first.
BASELINE_RULE2 = 0         # key collisions: none may stand, they lose a quantity.

# ARMED at zero on 2026-07-30, the day the notebook and the filesystem rule came into
# scope. Zero here is not an aspiration: each of these three was MEASURED at zero on
# the tree the day it was armed, so the number holds what is already true rather than
# forgiving what is not. Like every baseline in this file it may only ever move DOWN,
# and it is already at the floor, so any change to these three lines is a regression
# being written into the gate instead of being fixed.
#
# What each one holds:
#   RULE 1 notebook  the notebook declares seven settings and every one is a checked
#                    mirror of settings.py; an eighth typed into a cell is a new home.
#   RULE 4           no input is chosen by the filesystem. The one site that was
#                    (i4_midmarkout.py, the print twin of the sanity pair) had its
#                    SOURCE fixed the same day, and the sentence that used to stand
#                    here said the arm was "written into the artifact". That was a
#                    claim about the code stated as a claim about the file, and it does
#                    not hold: i4_midmarkout_results.json on disk was last written at
#                    db750f9, which is an ancestor of b16d313 where the fix landed, and
#                    it carries neither print_twin_source nor a scope naming the arm --
#                    only the old row_aligned_to_print_npz: true, which is the field
#                    whose meaning depended on the branch. So what rule 4 measures is
#                    the tree's SOURCE, which is what it reads, and the shipped
#                    artifact is separately owed a run. That run is not cheap and the
#                    debt is declared rather than quietly carried: the node re-walks
#                    the raw tape through build_quickwin_markouts.parse_day, and the
#                    sibling build over the same ten days recorded 758.8 s in
#                    quickwin_pass_summary.json. Read first-hand 2026-07-31.
#   RULE 5           all seven notebook mirrors agree with the declaration. A single
#                    disagreement means the notebook scores on another window, which
#                    is what a reader would re-run.
BASELINE_RULE1_NOTEBOOK = 0
BASELINE_RULE4 = 0          # inputs chosen by the filesystem
BASELINE_RULE5 = 0          # notebook mirrors that no longer agree with settings.py

# ARMED at zero on 2026-08-12, the day RULE 6 was wired up, and both were MEASURED at
# zero on the tree that day rather than hoped for. Like every baseline here they may
# only ever move DOWN, and both are already at the floor.
#
# RULE 6 asks settings.site_agrees about every site SETTING_SITES declares. A
# disagreement is a site holding a different value from the home it names, which is the
# whole defect this file exists for, so zero is the only defensible ceiling.
#
# The address ceiling is separate because it fails in the opposite direction. A site key
# that resolves to no file, or to two files, is not a disagreement -- it is a comparison
# that never happened, and it leaves a green count that means nothing. That is the error
# direction that passes through, so it is armed rather than reported.
BASELINE_RULE6 = 0          # sites whose literal disagrees with the home they name
BASELINE_RULE6_ADDRESS = 0  # site keys that resolve to no file or to more than one


def tracked(suffix):
    return [p for p in shipped_tree_files(ROOT) if p.endswith(suffix)]


# notebook_cells comes from evidence.py, where chk_headline_horizon.py reads it too.
# Both files held a copy that differed only in local names and wording, and both
# computed the same repository root for it; the shared one computes that root from its
# own location.


def code_units(py_paths, nb_paths):
    """Every unit of source this gate reads, as (label, scope, source, rel).

    label is what a finding points at; rel is the file the ALLOW list keys on.
    """
    for rel in py_paths:
        with open(os.path.join(ROOT, rel), encoding="utf-8", errors="replace") as fh:
            yield rel, "py", fh.read(), rel
    for rel in nb_paths:
        for label, src in notebook_cells(rel):
            yield label, "notebook", src, rel


def _literal(node):
    try:
        ast.literal_eval(node)
        return True
    except (ValueError, TypeError, SyntaxError):
        return False


def _norm(value):
    """Compare a declared sequence to a mirrored one by CONTENT, not by type.

    A tuple in settings.py and a list in a cell are the same setting; a different
    order or a different member is not.
    """
    if isinstance(value, (list, tuple)):
        return ("seq",) + tuple(_norm(v) for v in value)
    return value


def rule1(units):
    """Module-level literal declarations of a load-bearing setting."""
    found = []
    for label, scope, src, rel in units:
        if rel in ALLOW:
            continue
        try:
            tree = ast.parse(src)
        except SyntaxError as exc:
            found.append({"rule": "SYNTAX", "file": label, "scope": scope,
                          "line": exc.lineno or 0, "detail": str(exc),
                          "name": None, "group": None})
            continue
        for node in tree.body:                        # module level only
            if not isinstance(node, ast.Assign):
                continue
            for t in node.targets:
                if not isinstance(t, ast.Name) or t.id not in ALIAS_OF:
                    continue
                if not _literal(node.value):
                    continue                          # bound from settings, fine
                if t.id.endswith(OVERRIDE_HOOK_SUFFIX) \
                        and ast.literal_eval(node.value) is None:
                    continue        # an EMPTY override hook declares no value; see the
                                    # declaration of OVERRIDE_HOOK_SUFFIX above
                if scope == "notebook" and t.id in NOTEBOOK_MIRROR:
                    continue        # a declared mirror; RULE 5 checks it still agrees
                fix = (f"mirror it from settings.py and add {t.id} to "
                       f"NOTEBOOK_MIRROR so the repeat is checked"
                       if scope == "notebook" else
                       f"read it from settings.py, or add {rel} to ALLOW with what "
                       f"it computes")
                # THE VALUE IS REPORTED, NOT ONLY THE PLACE, and the two kinds of
                # finding below are why. A name bound to a NUMBER is a second home: the
                # value lives here as well as in settings.py and the two can drift. A
                # name bound to None declares no value at all -- it is an override hook
                # whose consumer reads settings.py when nothing is injected -- and it is
                # counted here because `None` is a literal to ast.literal_eval, which is
                # the predicate and not a judgement about the site. Reading the count
                # alone therefore cannot tell a live second home from a paid-off one, and
                # a reader who has to open six files to find that out will not. So the
                # count stays exactly as the predicate computes it and the artifact says
                # what each site holds. Measured 2026-07-31: of 8 sites, 6 hold None
                # (the early/late halves in t1_toxicity_skew_backtest.py, t3_capacity.py
                # and maker_econ.py, all three routed through settings.split_early_late)
                # and 2 hold a seed integer.
                value = ast.literal_eval(node.value)
                kind = "override_hook_no_value" if value is None else "declared_value"
                found.append({
                    "rule": "RULE-1-second-home",
                    "file": label, "scope": scope, "line": node.lineno, "name": t.id,
                    "group": ALIAS_OF[t.id],
                    "value": value,
                    "declaration_kind": kind,
                    "detail": (f"{t.id} is bound to the literal {value!r}. "
                               + (f"None declares no value: the site is an override "
                                  f"hook and its consumer reads settings.py when "
                                  f"nothing is injected, so migrating it would move "
                                  f"nothing. It is counted because None is a literal "
                                  f"to the predicate this rule uses"
                                  if value is None else
                                  f"That is a second home for the "
                                  f"{ALIAS_OF[t.id]} setting; {fix}")),
                })
    return found


def rule2(units):
    """Dicts mixing a literal key with a key built from a constant that can equal it."""
    found = []
    # What the single hole in a built key can evaluate to. A window number covers
    # f"markout{H.HEADLINE_HORIZON_S}_mean_bps"; a column spelling covers
    # f"{H.headline_print_col()}_mean_bps", which is the form that actually cost this
    # project a quantity, and which a number-only substitution walks straight past.
    windows = [str(h) for h in S.LADDER_S]
    windows += [S.headline_print_col(h) for h in S.LADDER_S]
    windows += [S.headline_mid_col(h) for h in S.LADDER_S]
    windows += [f"{h}s" for h in S.LADDER_S]
    for label, scope, src, _rel in units:
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            literals, built = {}, []
            for k in node.keys:
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    literals.setdefault(k.value, getattr(k, "lineno", node.lineno))
                elif isinstance(k, ast.JoinedStr):
                    # rebuild the key with every window substituted for the hole
                    parts, holes = [], 0
                    for v in k.values:
                        if isinstance(v, ast.Constant):
                            parts.append(str(v.value))
                        else:
                            parts.append(None)
                            holes += 1
                    if holes == 1:
                        built.append((parts, getattr(k, "lineno", node.lineno)))
            for parts, line in built:
                for w in windows:
                    cand = "".join(p if p is not None else w for p in parts)
                    if cand in literals:
                        found.append({
                            "rule": "RULE-2-key-collision",
                            "file": label, "scope": scope, "line": line, "name": cand,
                            "group": "horizon",
                            "detail": f"the built key equals the literal key "
                                      f"{cand!r} declared on line {literals[cand]} "
                                      f"when the window is {w}s; the second write "
                                      f"wins and one quantity leaves the artifact",
                        })
    return found


def rule3(paths):
    """Artifacts whose fingerprint disagrees with the current declaration.

    Returns the findings and a census keyed so that no reader has to guess what was
    counted. Files and blocks are DIFFERENT numbers here: six artifacts stamp the same
    fingerprint twice, once under _meta and once under scope, so a block count runs
    ahead of a file count by six. The rule works block by block, because each block is
    a separate claim about what produced the numbers around it; the file count is what
    anybody asking "how many artifacts are stamped" means.
    """
    checked, found = 0, []
    files_stamped, multi = [], {}
    current = S.fingerprint()
    watched = ("headline_horizon_s", "companion_horizon_s", "master_seed",
               "reliability_seed", "n_perm", "n_boot", "fdr_alpha",
               "rank_floor_fills", "whale_drop_k", "headline_lens")
    for rel in paths:
        try:
            with open(os.path.join(ROOT, rel), encoding="utf-8",
                      errors="replace") as fh:
                doc = json.load(fh)
        except (OSError, ValueError):
            continue
        # The block is found WHEREVER it sits, not only where the convention puts it.
        # Two placements appeared on the day stamping began: the m-group wrote the
        # fields flat into _meta, ks2 nested them under _meta.settings_fingerprint.
        # The nested form is the convention, because a named sub-block cannot collide
        # with the file's own _meta keys, but a gate that only looked in the convention
        # would have skipped the other seven artifacts and reported them as unstamped.
        def blocks_of(node):
            if isinstance(node, dict):
                if node.get("settings_module") == "settings.py":
                    yield node
                for v in node.values():
                    yield from blocks_of(v)
            elif isinstance(node, list):
                for v in node:
                    yield from blocks_of(v)

        n_here = 0
        for b in blocks_of(doc):
            if b.get("settings_module") != "settings.py":
                continue                              # not fingerprinted yet
            checked += 1
            n_here += 1
            overridden = set(b.get("overridden") or ())
            for key in watched:
                if key not in b or key in overridden:
                    continue
                if b[key] != current[key]:
                    found.append({
                        "rule": "RULE-3-stale-fingerprint",
                        "file": rel, "scope": "json", "line": 0, "name": key,
                        "group": "fingerprint",
                        "detail": f"the artifact was computed with {key}={b[key]!r} "
                                  f"and settings.py now declares "
                                  f"{current[key]!r}; recompute it, or record the "
                                  f"difference in the block's overridden list",
                    })
        if n_here:
            files_stamped.append(rel)
            if n_here > 1:
                multi[rel] = n_here
    census = {
        "n_files_stamped": len(files_stamped),
        "n_fingerprint_blocks": checked,
        "files_with_more_than_one_block": multi,
        "own_results_files_counted": sorted(f for f in files_stamped
                                            if f.startswith("checks/")),
        "note": ("files and blocks are different numbers: an artifact that stamps the "
                 "fingerprint under both _meta and scope contributes one file and two "
                 "blocks. own_results_files_counted names the check outputs inside the "
                 "file count -- they carry a fingerprint because this gate writes one, "
                 "and they are not artifacts the study produced."),
    }
    return found, census


# Calls that ask the filesystem whether something is there. Spelled as the attribute
# name so os.path.exists(p), Path(p).exists() and os.access(p, R_OK) are all caught
# without the check having to know how the module was imported.
FS_PROBES = ("exists", "isfile", "isdir", "is_file", "is_dir", "getsize", "access")


def _fs_probe(test):
    """The filesystem call inside a test, or None."""
    for n in ast.walk(test):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        name = (f.attr if isinstance(f, ast.Attribute)
                else f.id if isinstance(f, ast.Name) else None)
        if name in FS_PROBES:
            return name
    return None


def _is_absence(node):
    """True when the value says NO DATA rather than OTHER DATA.

    None and the empty containers are how a gate reports that the input is not there.
    Returning one of them closes the move; the caller has nothing to compute on and
    cannot mistake it for a result. Substituting a second file instead is the defect,
    because the caller computes happily on a different population.
    """
    if node is None:
        return False
    try:
        v = ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError):
        return False
    return v is None or (isinstance(v, (str, bytes, list, tuple, dict, set))
                         and len(v) == 0)


def _branch_statements(body):
    """Statements of a branch, not descending into nested function or class bodies."""
    for stmt in body:
        for n in ast.walk(stmt):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            yield n


def _assigned(body):
    """{name: [value nodes]} assigned anywhere in a branch."""
    out = {}
    for n in _branch_statements(body):
        if isinstance(n, ast.Assign):
            targets, value = n.targets, n.value
        elif isinstance(n, (ast.AnnAssign, ast.AugAssign)):
            targets, value = [n.target], n.value
        else:
            continue
        for t in targets:
            names = ([e for e in t.elts if isinstance(e, ast.Name)]
                     if isinstance(t, (ast.Tuple, ast.List)) else
                     [t] if isinstance(t, ast.Name) else [])
            for nm in names:
                out.setdefault(nm.id, []).append(value)
    return out


def _terminates(body):
    """The branch ends the move: returns, raises, exits, or skips the iteration."""
    for n in _branch_statements(body):
        if isinstance(n, (ast.Return, ast.Raise, ast.Continue, ast.Break)):
            return True
        if isinstance(n, ast.Call):
            f = n.func
            name = (f.attr if isinstance(f, ast.Attribute)
                    else f.id if isinstance(f, ast.Name) else None)
            if name == "exit":
                return True
    return False


def rule4(units):
    """Inputs chosen by the state of the filesystem rather than by a declaration."""
    found = []
    for label, scope, src, _rel in units:
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        lines = src.split("\n")

        def _src(lineno):
            return lines[lineno - 1].strip()[:120] if 0 < lineno <= len(lines) else ""

        for node in ast.walk(tree):
            # A: value = A if <file is there> else B
            if isinstance(node, ast.IfExp):
                probe = _fs_probe(node.test)
                if not probe:
                    continue
                if _is_absence(node.body) or _is_absence(node.orelse):
                    continue                       # gates to "no data", legitimate
                found.append({
                    "rule": "RULE-4-input-chosen-by-disk",
                    "file": label, "scope": scope, "line": node.lineno,
                    "name": probe, "group": "input",
                    "detail": "a conditional expression picks between two values on "
                              f"os.path.{probe}(); the input then depends on which "
                              "files this machine happens to hold, and the result "
                              "file cannot say which one it read. Declare the input, "
                              "and gate to an empty result when it is missing",
                    "source": _src(node.lineno),
                })
                continue
            # B: if <file is there>: x = one input  else: x = a different input
            if not isinstance(node, ast.If) or not node.orelse:
                continue
            probe = _fs_probe(node.test)
            if not probe:
                continue
            a, b = _assigned(node.body), _assigned(node.orelse)
            shared = sorted(set(a) & set(b))
            if not shared:
                continue                           # the branches bind different things
            if _terminates(node.body) or _terminates(node.orelse):
                continue                           # one branch closes the move
            if (all(_is_absence(v) for n in shared for v in a[n])
                    or all(_is_absence(v) for n in shared for v in b[n])):
                continue                           # one branch substitutes nothing
            found.append({
                "rule": "RULE-4-input-chosen-by-disk",
                "file": label, "scope": scope, "line": node.lineno,
                "name": ", ".join(shared), "group": "input",
                "detail": f"os.path.{probe}() decides which values {', '.join(shared)} "
                          "take, so the population is a property of this machine "
                          "rather than of a declaration, and two runs can differ "
                          "without either saying so. Declare the input, and gate to "
                          "an empty result when it is missing",
                "source": _src(node.lineno),
            })
    return found


def rule5(nb_paths):
    """Notebook mirrors of settings.py that no longer agree with it."""
    found, checked = [], []
    for rel in nb_paths:
        seen = {}
        for label, src in notebook_cells(rel):
            try:
                tree = ast.parse(src)
            except SyntaxError:
                continue
            for node in tree.body:
                if not isinstance(node, ast.Assign):
                    continue
                for t in node.targets:
                    if not isinstance(t, ast.Name) or t.id not in NOTEBOOK_MIRROR:
                        continue
                    if not _literal(node.value):
                        continue
                    seen[t.id] = (label, node.lineno, ast.literal_eval(node.value))
        if not seen:
            continue        # no mirrors at all: nothing declared, nothing to compare

        for name, (label, line, value) in sorted(seen.items()):
            kind, target = NOTEBOOK_MIRROR[name]
            if kind == "value":
                declared = getattr(S, target)
                agrees = _norm(value) == _norm(declared)
                detail = (f"{name} mirrors settings.{target}; the notebook holds "
                          f"{value!r} and settings.py declares {declared!r}")
            else:
                early = seen.get("EARLY_DAYS", (None, None, ()))[2]
                late = seen.get("LATE_DAYS", (None, None, ()))[2]
                want = S.split_early_late(tuple(early) + tuple(late))
                declared = want[0] if target == "early" else want[1]
                agrees = _norm(value) == _norm(declared)
                detail = (f"{name} is the {target} half of the notebook's own days; "
                          f"settings.split_early_late over those days returns "
                          f"{declared!r} and the notebook holds {value!r}")
            checked.append({"name": name, "file": label, "line": line,
                            "mirrors": target, "value": list(value)
                            if isinstance(value, (list, tuple)) else value,
                            "agrees": bool(agrees)})
            if not agrees:
                found.append({
                    "rule": "RULE-5-notebook-mirror-drift",
                    "file": label, "scope": "notebook", "line": line, "name": name,
                    "group": ALIAS_OF.get(name, "mirror"),
                    "detail": detail + ". The notebook repeats this value because it "
                              "also runs standalone; a repeat that no longer agrees "
                              "is a second home holding a different number, and the "
                              "notebook is what a reader re-runs",
                })
        # A mirror that vanished is not an improvement: the window is then fixed some
        # other way, which is the spelling this whole gate exists to stop.
        for name in NOTEBOOK_MIRROR:
            if name in seen:
                continue
            found.append({
                "rule": "RULE-5-notebook-mirror-missing",
                "file": rel, "scope": "notebook", "line": 0, "name": name,
                "group": ALIAS_OF.get(name, "mirror"),
                "detail": f"{name} is listed as a checked mirror of settings."
                          f"{NOTEBOOK_MIRROR[name][1]} but no cell declares it, so "
                          f"nothing verifies the value the notebook actually scores "
                          f"on. Restore the declaration, or drop the entry from "
                          f"NOTEBOOK_MIRROR and say what replaced it",
            })
    return found, checked


def _module_bindings(src):
    """{name: (kind, value, line)} for every module-level binding of one source unit.

    kind is "literal" when the right-hand side reads as a constant and "expression"
    otherwise. The distinction is the whole point: a name bound to an expression is a
    site that has been MIGRATED and reads its value from settings.py, and there is no
    literal left to compare. A name bound to a constant still holds a value here.

    A tuple target is unpacked rather than skipped, and this is not tidiness. The two
    day halves of identity/i3_nonrecoverability_oos.py are bound as
    `EARLY_DAYS, LATE_DAYS = H.split_early_late(...)`, and a reader that only looked at
    ast.Name called both of them absent -- measured on this tree, two sites reported as
    missing that are on disk and healthy. The other direction matters more: written as
    `EARLY_DAYS, LATE_DAYS = (4, 5), (9, 10)` the same statement holds two literals, and
    treating every unpacking as an expression would hide two second homes. So an
    unpacking whose right-hand side is a sequence of the same length is read element by
    element, and any other unpacking is an expression.
    """
    out = {}
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return out
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for t in node.targets:
            if isinstance(t, ast.Name):
                pairs = [(t, node.value)]
            elif isinstance(t, (ast.Tuple, ast.List)):
                aligned = (isinstance(node.value, (ast.Tuple, ast.List))
                           and len(node.value.elts) == len(t.elts))
                pairs = [(e, node.value.elts[i] if aligned else None)
                         for i, e in enumerate(t.elts) if isinstance(e, ast.Name)]
            else:
                pairs = []
            for nm, value_node in pairs:
                if value_node is not None and _literal(value_node):
                    out[nm.id] = ("literal", ast.literal_eval(value_node), node.lineno)
                else:
                    out[nm.id] = ("expression", None, node.lineno)
    return out


def rule6(py_paths):
    """Every site settings.py declares, asked of settings.site_agrees.

    WHY THIS RULE IS NOT RULE 1 AGAIN. RULE 1 counts places that hold a literal, and it
    answers "how many second homes are there". It says nothing about whether the second
    home holds the SAME number as the first, and a site that agrees today and drifts
    tomorrow leaves that count exactly where it was. Two passes have already answered
    the agreement question by hand and answered it differently, which is why the
    resolver was written down in settings.SETTING_SITES: for each site it names the one
    declaration that site is supposed to read.

    THE COMPARISON IS ASKED, NOT REPEATED. settings.site_agrees is called; its rule is
    not copied here. A check that reprints the logic it checks goes on asserting the old
    logic after the logic is repaired, and its disagreement then looks like a finding
    without being one. Ask the producer.

    WHY THE SITE IS RESOLVED BY CONTENT AND NOT BY THE PATH IT SPELLS. The keys hold flat
    paths -- "maker_econ.py::SEED" -- and the tree has since been laid out in group
    directories, so that file is money/maker_econ.py today. Measured on 2026-08-12: an
    exact-path lookup resolved 15 of the 64 sites and reported 49 as missing files, none
    of which is missing. Resolving by base name finds all 64. A name is an identifier and
    a path is a guess, and a census whose zero rests on the guess is a false zero.

    WHAT THIS RULE CANNOT CLAIM, and it has to be printed beside the count rather than
    left for a reader to work out. Only a site still holding a literal can be compared at
    all. A migrated site has no literal, an override hook bound to None has no value, and
    settings.site_agrees returns None for both rather than guessing. So the count of
    disagreements is taken over the COMPARED population, which this rule reports beside
    it, and a tree that has migrated every site compares nothing and must say so instead
    of printing a green zero.
    """
    by_base = {}
    for rel in py_paths:
        by_base.setdefault(os.path.basename(rel), []).append(rel)
    shipped = set(py_paths)
    cache = {}

    def bindings(rel):
        if rel not in cache:
            with open(os.path.join(ROOT, rel), encoding="utf-8",
                      errors="replace") as fh:
                cache[rel] = _module_bindings(fh.read())
        return cache[rel]

    found, sites = [], []
    for site in sorted(S.SETTING_SITES):
        rel, _, name = site.partition("::")
        row = {"site": site, "declared_path": rel, "name": name}
        if rel in shipped:
            row["file"], row["resolved_by"] = rel, "declared_path"
        else:
            candidates = by_base.get(os.path.basename(rel), [])
            if len(candidates) == 1:
                row["file"], row["resolved_by"] = candidates[0], "base_name"
            else:
                row["state"] = ("address_ambiguous" if candidates
                                else "address_unresolved")
                row["candidates"] = candidates
                sites.append(row)
                found.append({
                    "rule": "RULE-6-site-address", "file": rel, "scope": "py",
                    "line": 0, "name": name, "group": "site_map",
                    "detail": (f"settings.SETTING_SITES declares {site!r} and this tree "
                               f"holds {len(candidates)} file(s) it can be: "
                               f"{candidates or 'none'}. The site is not compared "
                               f"against its home at all, so its silence is not "
                               f"agreement. Point the key at the file, or drop it"),
                })
                continue

        kind, value, line = bindings(row["file"]).get(name, (None, None, 0))
        row["line"] = line
        if kind is None:
            # No module-level binding. This is what a site reads like when its value is
            # handed straight to a call -- probes/decay_curve.py passes seed_for() into
            # the generator constructor -- and SETTING_SITES says so in its own comment.
            # Nothing holds a value here, so there is nothing to disagree.
            row["state"] = "no_module_level_binding"
            sites.append(row)
            continue
        if kind == "expression":
            row["state"] = "migrated"
            sites.append(row)
            continue

        row["local_value"] = value
        partner = None
        if S.SETTING_SITES[site][0] == "rule":
            # The day-split rule needs both halves: it is the SPLIT that either
            # reproduces what the file holds or does not, and one half alone decides
            # nothing. settings.site_agrees returns None without the partner, which is
            # honest and useless, so the partner is looked up and passed.
            other = ("LATE_DAYS" if "EARLY" in name
                     else "EARLY_DAYS" if "LATE" in name else None)
            if other:
                p_kind, p_value, _ = bindings(row["file"]).get(other,
                                                              (None, None, 0))
                partner = p_value if p_kind == "literal" else None
        verdict = S.site_agrees(site, value, partner)
        row["agrees"] = verdict
        if verdict is None:
            row["state"] = "no_comparison_defined"
            sites.append(row)
            continue
        declaration = S.site_declaration(site)
        row["declared_path_in_settings"] = declaration["path"]
        row["declared_value"] = declaration["value"]
        row["state"] = "agrees" if verdict else "disagrees"
        sites.append(row)
        if not verdict:
            found.append({
                "rule": "RULE-6-site-disagrees-with-home",
                "file": row["file"], "scope": "py", "line": line, "name": name,
                "group": "site_map",
                "detail": (f"{name} holds {value!r} and settings."
                           f"{declaration['path']} declares "
                           f"{declaration['value']!r}. The site names that declaration "
                           f"as its home, so the two are one quantity living in two "
                           f"places with different values; read it from settings.py"),
            })

    counts = {}
    for row in sites:
        counts[row["state"]] = counts.get(row["state"], 0) + 1
    compared = counts.get("agrees", 0) + counts.get("disagrees", 0)
    census = {
        "n_sites_declared": len(sites),
        "n_compared": compared,
        "by_state": counts,
        # HOW EACH SITE WAS FOUND, not only how many were. The two numbers answer
        # different questions and only the pair is readable: a gate built on the
        # declared path alone would resolve the first number and be blind to the
        # second, while printing a green verdict over it.
        "by_resolution": {
            "declared_path": sum(1 for r in sites
                                 if r.get("resolved_by") == "declared_path"),
            "base_name": sum(1 for r in sites
                             if r.get("resolved_by") == "base_name"),
            "unresolved": sum(1 for r in sites
                              if r.get("state") == "address_unresolved"),
            "ambiguous": sum(1 for r in sites
                             if r.get("state") == "address_ambiguous"),
        },
        "n_resolved_by_base_name": sum(1 for r in sites
                                       if r.get("resolved_by") == "base_name"),
        "comparator": "settings.site_agrees, called rather than reimplemented",
        # WHAT THIS RULE VERIFIED ON THE RUN THAT WROTE THIS FILE, in a sentence, because
        # a reader who sees only the zero will read it as a clean tree. Today it is not a
        # verdict about cleanliness at all: the tree has migrated every site onto
        # settings.py, so there is no literal left to compare and the rule is standing
        # guard over a future edit rather than judging the present one.
        "verified_today": (
            "NOTHING. Every one of the "
            f"{len(sites)} declared sites is migrated, holds no value, or binds no "
            "module-level name, so no comparison of values took place and this zero is "
            "the absence of a population rather than the absence of a disagreement. The "
            "rule is armed and idle: it compares the moment a literal is written back at "
            "a declared site. What the run DID verify is the address of every site, "
            f"{len(sites)} of {len(sites)} resolved."
            if compared == 0 else
            f"{compared} of {len(sites)} declared sites still hold a literal and were "
            f"compared against the declaration they name; "
            f"{counts.get('disagrees', 0)} disagree."),
        "population_note": (
            "n_compared is the population the disagreement count is taken over, and it "
            "is smaller than the number of declared sites by construction: a migrated "
            "site holds no literal and an override hook bound to None holds no value, "
            "so neither can agree or disagree. A zero over a zero population verifies "
            "nothing and this rule says so on screen rather than printing it green."),
        "address_note": (
            "n_resolved_by_base_name counts site keys whose declared path is not in the "
            "tree while a file of that base name is. The keys carry the flat layout the "
            "tree had before the scripts were grouped into directories; resolving by "
            "content rather than by the spelled path is what keeps 49 of them from "
            "reading as missing files."),
    }
    return found, census


def notebook_unjudged(nb_paths):
    """Notebook declarations that RULE 1 does not judge, listed rather than hidden.

    RULE 1 only knows the names in LOAD_BEARING, so a green notebook count means "no
    second home among the settings this gate tracks", not "no settings typed into a
    cell". The difference is the list below. Reporting it keeps a zero from reading as
    coverage it does not have, and it is where the next name comes from when the gate
    is widened.
    """
    out = []
    for rel in nb_paths:
        for label, src in notebook_cells(rel):
            try:
                tree = ast.parse(src)
            except SyntaxError:
                continue
            for node in tree.body:
                if not isinstance(node, ast.Assign):
                    continue
                for t in node.targets:
                    if (isinstance(t, ast.Name) and t.id not in ALIAS_OF
                            and _literal(node.value)):
                        out.append({"file": label, "line": node.lineno, "name": t.id})
    return out


def main():
    started = artifact.start_clock()
    py = tracked((".py",))
    js = tracked((".json",))
    nb = tracked((".ipynb",))
    units = list(code_units(py, nb))
    f1 = rule1(units)
    f2 = rule2(units)
    f3, fp = rule3(js)
    f4 = rule4(units)
    f5, mirrors = rule5(nb)
    f6, site_census = rule6(py)
    n6 = sum(1 for f in f6 if f["rule"] == "RULE-6-site-disagrees-with-home")
    n6_addr = sum(1 for f in f6 if f["rule"] == "RULE-6-site-address")

    # Counted by scope, because the two debts are paid off by different work: a script
    # finding is migrated to settings.py, a notebook finding is mirrored or deleted.
    def _n(findings, scope):
        return sum(1 for f in findings if f.get("scope") == scope)

    n1, n1_nb = _n(f1, "py"), _n(f1, "notebook")
    n2, n2_nb = _n(f2, "py"), _n(f2, "notebook")
    n4, n4_nb = _n(f4, "py"), _n(f4, "notebook")

    # Only the two ARMED baselines can fail the run. The rules added after them report
    # their counts and stay advisory until a baseline is set for each, so that freezing
    # a debt figure stays a decision somebody makes rather than a side effect.
    regressed = (BASELINE_RULE1 is not None and n1 > BASELINE_RULE1) or \
                n2 > BASELINE_RULE2 or bool(f3)
    for count, base in ((n1_nb, BASELINE_RULE1_NOTEBOOK),
                        (n4 + n4_nb, BASELINE_RULE4),
                        (len(f5), BASELINE_RULE5),
                        (n6, BASELINE_RULE6),
                        (n6_addr, BASELINE_RULE6_ADDRESS)):
        regressed = regressed or (base is not None and count > base)
    unarmed = [n for n, b in (("rule1_notebook", BASELINE_RULE1_NOTEBOOK),
                              ("rule4", BASELINE_RULE4),
                              ("rule5", BASELINE_RULE5),
                              ("rule6", BASELINE_RULE6),
                              ("rule6_address", BASELINE_RULE6_ADDRESS)) if b is None]
    if BASELINE_RULE1 is None:
        verdict = "BASELINE_UNSET"
    elif regressed:
        verdict = "FAIL"
    elif n1 or n2:
        verdict = "PASS_AT_BASELINE"
    else:
        verdict = "PASS"

    results = {
        "_meta": {
            "scope_note": "counts are kept per scope and never blended: py debt is "
                          "paid off by migrating a consumer to settings.py, notebook "
                          "debt by mirroring or deleting a cell literal, and one "
                          "blended number could be lowered by work on the other",
            "n_py_scanned": len(py),
            "n_json_scanned": len(js),
            "n_notebooks_scanned": len(nb),
            "n_notebook_code_cells": sum(1 for u in units if u[1] == "notebook"),
            # Was one number called n_artifacts_fingerprinted, which read as a file
            # count and was a block count. The two differ by six, and the difference
            # is real rather than a miscount, so both are reported under names that
            # say which is which.
            "fingerprint_census": fp,
            "baseline_rule1": BASELINE_RULE1,
            "baseline_rule2": BASELINE_RULE2,
            "baseline_rule1_notebook": BASELINE_RULE1_NOTEBOOK,
            "baseline_rule4": BASELINE_RULE4,
            "baseline_rule5": BASELINE_RULE5,
            "baseline_rule6": BASELINE_RULE6,
            "baseline_rule6_address": BASELINE_RULE6_ADDRESS,
            "setting_site_census": site_census,
            "unarmed_baselines": unarmed,
            "unarmed_note": "a rule whose baseline is null reports its count and "
                            "cannot fail the run; set the baseline to arm it",
            "allow_list": ALLOW,
            "notebook_mirror": {k: list(v) for k, v in NOTEBOOK_MIRROR.items()},
            "notebook_mirrors_checked": mirrors,
            "notebook_declarations_not_judged": notebook_unjudged(nb),
            "notebook_declarations_not_judged_note": (
                "top-level literals in notebook cells whose names are not in "
                "LOAD_BEARING, so RULE 1 says nothing about them. The coin map is the "
                "one that matters most: settings.py keys the code map BY ARTIFACT "
                "because a code valid in two files relabels BTC as ETH without "
                "raising, and the notebook types its own. Adding COIN to the coins "
                "family was measured on 2026-07-30 and costs 8 further findings in "
                "probes/ plus 1 in the notebook, which is a decision about the frozen "
                "debt figure and not a side effect of widening the scope."),
            # The fingerprint used to be written here by hand, first as "settings"
            # and then under the canonical name. It is no longer written here at
            # all: artifact.write stamps it, from the same S.fingerprint() call, so
            # the record has one producer instead of two that can drift apart.
            "setting_state": S.SETTING_STATE,
            "not_caught": ["a name stating a setting its value does not come from",
                           "an input chosen by an `or` fallback, by a try/except, or "
                           "by a glob that returns whichever shards are present",
                           "a filesystem test whose two branches bind DIFFERENT names "
                           "that a later line then merges: RULE 4 pairs the branches "
                           "by the names they assign, so an unshared name is invisible",
                           "a setting spelled inside a notebook cell that the parse "
                           "could not read (see unparsable_cells)"],
            "unparsable_cells": [f["file"] for f in f1 if f["rule"] == "SYNTAX"],
        },
        "verdict": verdict,
        "n_rule1_second_home": n1,
        # The same count split by what each site actually holds, so the headline number
        # is not read as a count of live second homes when part of it is not. A site
        # bound to None declares no value and its consumer already reads settings.py;
        # a site bound to a value is the debt this rule was written for. These two sum
        # to n_rule1_second_home over the .py scope and neither replaces it: the gate is
        # judged on the count its predicate computes, and this is what that count is
        # made of.
        "n_rule1_by_declaration_kind": {
            "declared_value": sum(
                1 for f in f1 if f.get("declaration_kind") == "declared_value"
                and f["scope"] == "py"),
            "override_hook_no_value": sum(
                1 for f in f1 if f.get("declaration_kind") == "override_hook_no_value"
                and f["scope"] == "py"),
        },
        "n_rule1_second_home_notebook": n1_nb,
        "n_rule2_key_collision": n2,
        "n_rule2_key_collision_notebook": n2_nb,
        "n_rule3_stale_fingerprint": len(f3),
        "n_rule4_input_chosen_by_disk": n4,
        "n_rule4_input_chosen_by_disk_notebook": n4_nb,
        "n_rule5_notebook_mirror": len(f5),
        # Both counts carry their population with them. n_rule6_compared is the number
        # of sites that could disagree at all, and reading the disagreement count
        # without it is reading a ratio with the denominator torn off.
        "n_rule6_site_disagrees": n6,
        "n_rule6_compared": site_census["n_compared"],
        "n_rule6_site_address_unresolved": n6_addr,
        "by_scope": {
            "py": {"rule1": n1, "rule2": n2, "rule4": n4, "rule6": n6,
                   "rule6_address": n6_addr},
            "notebook": {"rule1": n1_nb, "rule2": n2_nb, "rule4": n4_nb,
                         "rule5": len(f5)},
            "json": {"rule3": len(f3)},
        },
        "findings": f1 + f2 + f3 + f4 + f5 + f6,
    }
    # This gate used to write its own file with json.dump and its own _meta block, so
    # it recorded no time at all: a reader could not tell today's verdict from one
    # taken a month ago under a different tree. Four of the records it kept by hand --
    # results_file, script, scope and the fingerprint -- are the shared module's, and
    # are now passed as parameters. `scope` changes shape rather than meaning: it was
    # one sentence, and the module asks for population, window and coins separately.
    carried = results.pop("_meta")
    artifact.write(
        os.path.basename(OUT_JSON), results,
        script=__file__,
        # The tree is the input and it is hundreds of files, so it is stated in scope
        # rather than hashed one by one.
        inputs=[],
        scope={
            "population": f"{len(py)} shipped .py and every code cell of the "
                          f"{len(nb)} shipped .ipynb for rules 1, 2 and 4; "
                          f"{len(js)} shipped .json for rule 3; the shipped "
                          f"notebooks for rule 5. A notebook finding points at "
                          f"file.ipynb#cellN and a line inside that cell",
            "window": "n/a: this gate reads the repository as it stands now, not a "
                      "period of market data",
            "coins": "n/a: this gate reads declarations and touches no market data",
        },
        started=started,
        extra_meta=carried,
    )

    print("=" * 78)
    print("  ONE HOME PER SETTING - settings.py gate")
    print("=" * 78)
    n_cells = sum(1 for u in units if u[1] == "notebook")
    print(f"  python files scanned     : {len(py)}")
    print(f"  json files scanned       : {len(js)}")
    print(f"  notebooks scanned        : {len(nb)} ({n_cells} code cells)")
    print(f"  fingerprinted            : {fp['n_files_stamped']} files, "
          f"{fp['n_fingerprint_blocks']} blocks "
          f"({len(fp['files_with_more_than_one_block'])} files stamp twice)")
    print(f"  RULE 1 second home  .py  : {n1}"
          + (f" (baseline {BASELINE_RULE1})" if BASELINE_RULE1 is not None else ""))
    print(f"  RULE 1 second home  .ipynb: {n1_nb}"
          + (f" (baseline {BASELINE_RULE1_NOTEBOOK})"
             if BASELINE_RULE1_NOTEBOOK is not None else "  (baseline not set)"))
    print(f"  RULE 2 key collision     : {n2} .py / {n2_nb} .ipynb "
          f"(baseline {BASELINE_RULE2} on .py)")
    print(f"  RULE 3 stale fingerprint : {len(f3)}")
    print(f"  RULE 4 input by disk     : {n4} .py / {n4_nb} .ipynb"
          + (f" (baseline {BASELINE_RULE4})" if BASELINE_RULE4 is not None
             else "  (baseline not set)"))
    print(f"  RULE 5 notebook mirror   : {len(f5)} of {len(mirrors)} mirrors disagree"
          + (f" (baseline {BASELINE_RULE5})" if BASELINE_RULE5 is not None
             else "  (baseline not set)"))
    compared = site_census["n_compared"]
    print(f"  RULE 6 site vs its home  : {n6} of {compared} compared disagree, "
          f"{site_census['n_sites_declared']} sites declared "
          f"(baseline {BASELINE_RULE6})")
    res = site_census["by_resolution"]
    print(f"      addresses resolved    : {res['declared_path']} by the path the key "
          f"spells, {res['base_name']} by base name, {res['unresolved']} nowhere, "
          f"{res['ambiguous']} ambiguous (baseline {BASELINE_RULE6_ADDRESS})")
    for state, n in sorted(site_census["by_state"].items(), key=lambda kv: -kv[1]):
        print(f"      {state:24} {n}")
    # The count and its population, in one sentence, because a zero over an empty
    # population is the shape of every false zero this repository has caught.
    if compared == 0:
        print("      NOTHING WAS COMPARED: every declared site is migrated, holds no "
              "value, or has no literal left, so this rule verified nothing today. "
              "It fires the moment a literal comes back.")
    by_group = {}
    for f in f1:
        by_group[f["group"]] = by_group.get(f["group"], 0) + 1
    for g, n in sorted(by_group.items(), key=lambda kv: -kv[1]):
        print(f"      {g:14} {n}")
    for f in f2 + f3 + f4 + f5:
        print(f"  {f['rule']:30} {f['file']}:{f['line']}  {f['name']}")
    print("-" * 78)
    print(f"  VERDICT: {verdict}")
    if verdict == "BASELINE_UNSET":
        print(f"  Set BASELINE_RULE1 = {n1} to freeze today's debt, then only ever "
              f"lower it.")
    if unarmed:
        print(f"  UNARMED, reported only: {', '.join(unarmed)}. Set each baseline to "
              f"the count above to arm it.")
    print(f"  results -> {os.path.basename(OUT_JSON)}")

    # Six rules share one verdict word, so a red run printed FAIL and left the reader
    # to find which of six regressed by comparing six counts to six baselines in the
    # table above. This says it: the rule, its ceiling, its count, and the file and
    # line of each finding.
    evidence_code = report_gate(
        [{"name": "RULE 1 second home for a setting, .py",
          "permitted": BASELINE_RULE1, "found": n1,
          "assumption": ("a setting is declared once, in settings.py, and read from "
                         "there. A second site holding the same value is a number "
                         "that can drift without anyone editing it twice. The "
                         "ceiling is a frozen debt figure that may only ever be "
                         "lowered"),
          "method": "AST walk of every tracked .py for a literal settings.py holds",
          "note": "migrate the site to settings.py; do not raise the ceiling",
          "sites": [f for f in f1 if f.get("scope") == "py"]},
         {"name": "RULE 1 second home for a setting, notebook",
          "permitted": BASELINE_RULE1_NOTEBOOK, "found": n1_nb,
          "assumption": "the same, over notebook code cells",
          "method": "AST walk of every code cell of every tracked .ipynb",
          "sites": [f for f in f1 if f.get("scope") == "notebook"]},
         {"name": "RULE 2 key collision, .py",
          # The gated count is the .py one, matching this gate's own condition. The
          # notebook collisions are counted and printed in the table above and are
          # NOT gated today; widening this to n2 + n2_nb would make the printed
          # evidence stricter than the rule it is reporting on.
          "permitted": BASELINE_RULE2, "found": n2,
          "assumption": ("no two settings share a key. A collision does not drift, "
                         "it destroys: one quantity silently overwrites the other, "
                         "so none may stand and the ceiling is zero"),
          "method": "duplicate declared keys across the scanned units",
          "note": f"{n2_nb} further collision(s) stand in notebooks, ungated",
          "sites": [f for f in f2 if f.get("scope") == "py"]},
         {"name": "RULE 3 stale fingerprint",
          "permitted": 0, "found": len(f3),
          "assumption": ("a results file stamped with the settings it was written "
                         "under still matches what settings.py declares today. A "
                         "stale stamp means the file is older than the code and its "
                         "numbers answer a question nobody is asking any more"),
          "method": "compare each stamped fingerprint block against settings.py",
          "sites": f3},
         {"name": "RULE 4 input chosen by the filesystem",
          "permitted": BASELINE_RULE4, "found": n4 + n4_nb,
          "assumption": ("no script picks its input by globbing or by newest-file: "
                         "which file was read must be a declaration, not whatever "
                         "the disk happened to hold that morning"),
          "method": "AST walk for glob/listdir/sort-by-mtime feeding a read",
          "sites": f4},
         {"name": "RULE 5 notebook mirror disagrees with settings.py",
          "permitted": BASELINE_RULE5, "found": len(f5),
          "assumption": ("a notebook that repeats a declaration must still agree "
                         "with the one home; the mirror is allowed only while it is "
                         "identical"),
          "method": f"compare each of the {len(mirrors)} mirrors against settings.py",
          "sites": f5},
         {"name": "RULE 6 a site disagrees with the home it names",
          "permitted": BASELINE_RULE6, "found": n6,
          "assumption": ("settings.SETTING_SITES names, for every site still holding a "
                         "literal, the one declaration that site is supposed to read. A "
                         "site holding a different value is one quantity in two places, "
                         "and only a comparison can tell that apart from a site that is "
                         "merely spelled twice"),
          "method": (f"settings.site_agrees was ASKED about each of the "
                     f"{site_census['n_sites_declared']} declared sites, not "
                     f"reimplemented here; {site_census['n_compared']} of them still "
                     f"hold a literal and could be compared at all"),
          "note": "read the site from settings.py; do not edit the declaration to match",
          "sites": [f for f in f6
                    if f["rule"] == "RULE-6-site-disagrees-with-home"]},
         {"name": "RULE 6 a declared site resolves to no file, or to two",
          "permitted": BASELINE_RULE6_ADDRESS, "found": n6_addr,
          "assumption": ("a site key that cannot be resolved is not compared, and its "
                         "silence reads exactly like agreement. This is the error "
                         "direction that passes through, so it is armed rather than "
                         "reported"),
          "method": ("the declared path first, then the unique file of that base name; "
                     f"{site_census['n_resolved_by_base_name']} sites resolve only by "
                     f"base name, because the keys carry the flat layout the tree had "
                     f"before the scripts were grouped"),
          "sites": [f for f in f6 if f["rule"] == "RULE-6-site-address"]}],
        OUT_JSON, inputs={"declared_in": "settings.py"})

    exit_code = 1 if verdict == "FAIL" else 0
    # The two can differ in exactly one way and it is worth saying out loud rather
    # than resolving silently: with RULE 1 unfrozen the overall verdict is
    # BASELINE_UNSET, which does not fail the run even though a rule went over.
    if evidence_code != exit_code:
        print(f"  note: the rules above would exit {evidence_code}; this gate exits "
              f"{exit_code} because its overall verdict is {verdict}. RULE 1 has no "
              f"baseline yet, so nothing is armed to fail against.")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
