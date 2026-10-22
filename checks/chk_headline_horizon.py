#!/usr/bin/env python3
"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-07-29
References: internal settings.py; ws1_horizon_results.json (horizon selection).

CHK - THE HORIZON IS DECLARED, NOT TYPED.

What went wrong that this check exists to stop. An audit of the tree found the
scoring horizon fixed in two different ways. The first is visible: a constant
named HEADLINE_HORIZON or POLICY_HORIZONS or CLASSIFY_HORIZON, greppable, and
those had already drifted apart -- two scripts in one project each declared
themselves headline and meant different windows. The second is not visible at
all: a line reading z["mo60"] fixes the horizon exactly as firmly, and grepping
for the word "horizon" will never find it. There were more of the second kind
than the first, and every number the study leans on came out of one of them.

So this check scans the SOURCE, not the results. Two rules.

RULE 1 (no silent picks). A markout column name may not appear as a bare string
literal in analysis code. It must come from the accessor in settings.py that spells
that window: headline_print_col() and headline_mid_col() for the headline, and
companion_print_col() and companion_mid_col() for the long window kept beside it.
Naming only the headline pair here, as this rule did until 2026-07-31, made the
instruction wrong for the sixteen findings that deliberately read the companion
window: following it would have swapped their 60 s read for a 10 s one and moved
their numbers. The gate now derives the accessor from the literal, so the fix it
prints always returns the same string the code already holds. A file that
legitimately handles the whole ladder,
or that deliberately works on another window, declares itself in ALLOW below with
a one-line reason -- the reason is the point of the exemption, so an empty reason
fails too.

RULE 2 (one headline). No file may define its own HEADLINE_HORIZON* constant to a
literal. It binds to settings.HEADLINE_HORIZON_S, or it is named for the quantity
it actually serves (gm_quoter's J_HORIZON is the size of the informed jump, not a
scoring window, and says so).

SCOPE: every .py in this repository, and the code cells of the notebooks. The
notebook is what a reader re-runs to reproduce the study, so a window fixed by
spelling there costs exactly what one in a script costs, and it has already cost it:
the notebook went on scoring at the retired 60 s window after the repository moved to
10 s, and its own saved checks passed on the old numbers. The notebook is the one
consumer that cannot import settings.py -- it is published to run from the dataset
alone, with no repository beside it -- so it declares the window once, in a cell, and
that single declaration is legitimate. It is exempt from RULE 2 only while it AGREES
with settings.py; the day it drifts it is flagged, because a repeat that disagrees is
a second headline. Notebook findings are counted SEPARATELY from script findings:
the two debts are worked off differently, and one blended number cannot be lowered
deliberately.

Read-only. Exits non-zero when a TRACKED count rises above its baseline, and names
file, line and rule. Findings in .gitignored files are counted and printed under
their own heading; they set neither the verdict nor the exit code, because a
clone of the repository never contains those files.

    uv run --no-project python3 checks/chk_headline_horizon.py
"""
import ast
import fnmatch
import io
import json
import os
import re
import sys
import tokenize

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT_JSON = os.path.join(HERE, "chk_headline_horizon_results.json")

sys.path.insert(0, ROOT)
import artifact                                               # noqa: E402
import settings as S                                          # noqa: E402
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from evidence import notebook_cells, report_gate              # noqa: E402

# Every markout column any producer writes.
COLUMN_RE = re.compile(r"^mo(1|10|60|300)(_mid)?$")

# The rungs a LADDER READ has to name in full to count as one. 300 is deliberately not
# in here: only three producers write mo300 and no analysis walks a four-rung ladder, so
# requiring it would turn every honest three-rung walk back into a violation.
RUNG_NAMES = ("mo1", "mo10", "mo60")

# Findings standing against the gate. Every one is a single rung read directly instead
# of through settings.py, in a file that predates the gate; none was introduced by the
# horizon consolidation. This number is a DEBT, and the only legitimate edit to it is
# downward, with the migration that earned it named in the commit. Raising it to make a
# red run go green defeats the gate entirely.
#
# 64 when the gate was introduced, 2026-07-30 morning.
# 29 the same afternoon: fifteen root scripts were migrated to settings.py, which also
#    retired the sixteen file-level exemptions that the ladder rule already covered.
#    What remains is entirely inside probes/: eighteen reads in tracked probe files that
#    genuinely work on the companion window, and eleven in the three battery files that
#    are gitignored and never reach the published repository. Each of the eighteen needs a
#    decision, not a rename: whether the probe's claim belongs at the headline window
#    (migrate and re-run, numbers move) or at the companion one (declare and stay).
# 18 the same evening, once the gate learned to separate the two populations it had been
#    adding together. Eleven of the twenty-nine sit in three gitignored battery files that
#    never reach the published repository, so they were never our debt; counting them made
#    the gate demand a fix it could not accept. The eighteen tracked reads stand, and each
#    still needs the decision above rather than a rename.
# 18 on 2026-07-31, UNCHANGED, and the reason is written here rather than left implied,
#    because a debt figure that stands still for a day looks the same whether it was
#    examined or forgotten. All eighteen were examined one by one on that date and the
#    decision the note above demands was taken for each. None of them turned out to be
#    the second case -- a quantity that merely coincides with a window, the way
#    gm_quoter's J_HORIZON is a jump size and not a scoring window. Every one is a
#    markout column name, which is to say a window: sixteen spell the COMPANION window
#    (mo60, mo60_mid) and two spell the HEADLINE one (mo10). So there is nothing here
#    for the rule to stop counting, and no part of this figure comes down by narrowing
#    the gate.
#
#    What they all are is the FIRST case, and cheaper than that case was thought to be.
#    The note above says migrating means "numbers move". For these eighteen it does not:
#    settings.py declares companion_print_col() and companion_mid_col(), which return
#    exactly "mo60" and "mo60_mid", so each site is a one-line substitution that reads
#    the same column it reads today. Eighteen substitutions across seven files under
#    probes/, plus an import of settings in the two that do not have one yet
#    (eb_scoring.py, persistence_crosswindow.py), take this figure to zero in one move
#    with no recompute. It was not lowered today because those eighteen substitutions
#    have not been made, and a ceiling may only ever come down BEHIND work that was
#    actually done.
#
#    One of the eighteen is more than a substitution and is recorded so the migration
#    does not bury it. kss_decomp_c.py calls mo60 its "primary outcome" and mo10 its
#    "robustness horizon", while this repository declares the headline to be 10 s. That
#    is two files calling themselves headline and meaning different windows, which is
#    the defect this whole gate exists to surface. Migrating its four literals makes the
#    disagreement legible; it does not settle it, and settling it moves that probe's
#    published variance shares.
#
# 9 on 2026-07-31, once loading a markout panel and choosing the column the harm is
#    scored on stopped being the same act done in place. That used to happen inside every
#    producer that needed it, so a window could be fixed by spelling a column name and
#    nothing would notice. Both moved into panel_io.py, which takes the horizon and the
#    lens from settings.py and refuses a column outside the declared ladder, and nine
#    spellings stopped being spellings in one move.
BASELINE_VIOLATIONS = 0
# LOWERED to 0 on 2026-07-31, from 9, BEHIND the work rather than to make a red run go
# green, and the work is named so the drop can be checked line by line.
#
# The nine that stood were the ones panel_io.py had not reached: four in
# probes/kss_decomp_c.py and five in probes/probe_F_hlp_liq.py, neither of which loads a
# markout panel through that module -- the first reads panel_markouts.npz directly and
# the second reads the per-coin checkpoint shards. All nine were substitutions and
# nothing more, exactly as the note above predicted. Seven spelled the COMPANION window
# and were replaced by settings.companion_print_col(); two spelled the HEADLINE window
# and were replaced by settings.headline_print_col(). The gate itself derives which
# accessor belongs to which literal and printed the pairing for all nine, and both
# accessors return today the strings that were typed there -- "mo60" and "mo10" -- so the
# nine substitutions read the same columns, write the same keys and move no number.
#
# WHAT DID NOT COME DOWN WITH IT, so the zero is not read as more than it is. The
# disagreement recorded four paragraphs above still stands: kss_decomp_c.py calls the
# 60 s window its primary outcome while this repository declares the headline to be 10 s.
# Migrating its four literals made that legible in the code instead of hiding it inside
# two strings, and it did not settle it. Settling it moves that probe's published
# variance shares and is owed its own recompute.
#
# Eleven findings remain in the three gitignored battery files, reported and NOT gated:
# a clone never contains those files, so they were never the project's debt, and
# folding them in is what made an earlier figure impossible to drive to zero.
#
# Only ever lower this line. At zero the only edit left to it is a regression.

# ARMED at zero on 2026-07-30, the day the notebook came into scope. Measured, not
# hoped for: the notebook's fifteen markout column literals all sit inside full
# mo1/mo10/mo60 ladder reads and none of them fixes a window, and its one window
# declaration is a mirror checked against settings.py. Zero is therefore what the file
# already is, and it is the floor, so this line can only ever be edited to write a
# regression into the gate. It is deliberately a second number and not added to the
# one above: a blended figure could be lowered by migrating a script, which does
# nothing for the file a reader actually runs.
BASELINE_VIOLATIONS_NOTEBOOK = 0

# The notebook may repeat these window declarations, and only these, because it also
# runs standalone from the published dataset with no repository to import. Each entry
# maps the notebook's name to the declaration in settings.py it has to equal. The
# exemption is the AGREEMENT, not the name: a repeat that no longer matches is a
# second headline and is flagged.
NOTEBOOK_HORIZON_MIRROR = {
    "SCORE_HORIZON_S": "HEADLINE_HORIZON_S",
    "COMPANION_HORIZON_S": "COMPANION_HORIZON_S",
}

# Files exempt from RULE 1, each with the reason it is exempt. A file is exempt
# because of WHAT IT COMPUTES, never because changing it is inconvenient.
#
# A file-level exemption is a blanket permission: it silences every literal in the
# file, including one added tomorrow for no reason at all. So it is only justified
# when the finer ladder-read rule below CANNOT clear the file on its own. Sixteen
# entries that stood here on 2026-07-30 cleared it on their own -- every literal in
# them was part of a full mo1/mo10/mo60 walk -- and were removed with the violation
# count unchanged at 64. The list below is the residue that actually does work; the
# `exemptions_in_use` block of the results file is what proves it, and an entry that
# stops appearing there has stopped earning its place.
ALLOW = {
    # --- producers: they write the whole ladder, so they must name every column
    "data/i4_midmarkout.py": "producer: writes mo{1,10,60}_mid, must name all three",
    "data/panel_build.py": "producer: builds panel_markouts.npz across the ladder",
    "notebook_build/make_notebook_data.py": "producer: packs the ladder into the notebook artifact",
    # --- the ladder IS the object of study
    "probes/calib_print_vs_mid.py": "print-vs-mid calibration compares lens at each h",
    # --- a different window, on purpose, stated
    "identity/follow_the_informed_oos.py": "HORIZON_LAG is the copycat's HOLDING horizon (enter "
                                  "one lag after the trade is observable, exit at H), a "
                                  "different quantity from adverse-selection harm; the "
                                  "toxicity CLASSIFICATION does use the headline column",
    # --- checks that must reproduce the producer bit-for-bit
    "checks/chk_side_signconv.py": "re-derives a markout to verify the sign convention",
}

# Files that may still carry their own HEADLINE-ish constant, and why.
ALLOW_CONST = {
    "quoters/gm_quoter.py": "J_HORIZON is named for its quantity, not for a headline",
    "settings.py": "the single source of truth itself",
}


def _rel(path):
    return os.path.relpath(path, ROOT).replace(os.sep, "/")


def declared_home(column):
    """The call in settings.py that spells this column today, or None.

    Why the gate has to work this out per column instead of naming one accessor in
    the message. RULE 1 used to end every finding with "read it through
    settings.headline_print_col()/headline_mid_col()", which is the right
    instruction only for a literal that spells the HEADLINE window. Sixteen of the
    eighteen findings that stood when this function was written on 2026-07-31 spelled
    mo60, the COMPANION window, and
    settings.py has declared companion_print_col() and companion_mid_col() for
    exactly that since the module was written. Following the old message on one of
    those sixteen would have swapped a 60 s read for a 10 s one and moved the
    probe's numbers -- a gate about not typing the window, telling a reader to
    change it. The instruction is only safe when the call it names returns the same
    string the literal already holds, so it is derived from the literal.
    """
    lens = "mid" if column.endswith("_mid") else "print"
    seconds = int(column[2:-4] if column.endswith("_mid") else column[2:])
    if seconds == S.HEADLINE_HORIZON_S:
        return f"settings.headline_{lens}_col()", seconds
    if seconds == S.COMPANION_HORIZON_S:
        return f"settings.companion_{lens}_col()", seconds
    if seconds in S.LADDER_S:
        return f"settings.headline_{lens}_col({seconds})", seconds
    return None, seconds


def split_ladder_reads(hits, window=4):
    """Split literal hits into (choices, ladder_reads).

    A LADDER READ names every rung of one family together -- mo1, mo10, mo60 for the
    trade print, or their _mid counterparts -- inside `window` lines. That is code
    handling the whole ladder: a column-name tuple, a builder writing all three, a
    term-structure loop. It fixes no horizon and there is nothing to declare.

    Naming ONE rung is a choice, and the silent kind this gate exists to catch.

    This is deliberately finer than the file-level ALLOW. A blanket exemption covers
    the file forever, so a lone rung added to an exempt builder tomorrow passes: the
    exemption was granted for code that no longer describes the file. Grouping by
    pattern instead means the builder needs no exemption at all, and the lone rung is
    still caught the day it appears.
    """
    families = {}
    for h in hits:
        fam = "mid" if h["column_name"].endswith("_mid") else "print"
        families.setdefault(fam, []).append(h)

    choices, ladder = [], []
    for fam, fam_hits in families.items():
        rungs = {c for c in RUNG_NAMES if (c + "_mid" if fam == "mid" else c) in
                 {x["column_name"] for x in fam_hits}}
        fam_hits.sort(key=lambda x: x["line"])
        i = 0
        while i < len(fam_hits):
            group = [fam_hits[i]]
            j = i + 1
            while j < len(fam_hits) and fam_hits[j]["line"] - group[-1]["line"] <= window:
                group.append(fam_hits[j])
                j += 1
            names = {g["column_name"] for g in group}
            complete = all(
                (r + "_mid" if fam == "mid" else r) in names for r in RUNG_NAMES)
            (ladder if complete else choices).extend(group)
            i = j
        del rungs
    return choices, ladder


def gitignore_patterns():
    """The .gitignore rules, read as a file rather than asked of git.

    Why the distinction matters to this gate. A file that .gitignore excludes never
    reaches the published repository, so a horizon typed into one is not a defect the
    project owes anything for -- it is scratch. Folding the two together made the debt
    figure unusable: it could not be driven to zero however much of the repository
    was fixed, because eleven of the findings live in local exploration harnesses that
    nobody will ever clone.

    Read rather than queried on purpose. This check walks the filesystem and runs
    without git; asking `git ls-files` would make the gate fail in a plain unzipped
    copy of the repository, which is one of the ways the work gets handed over.
    """
    path = os.path.join(ROOT, ".gitignore")
    pats = []
    if not os.path.exists(path):
        return pats
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#"):
                pats.append(line)
    return pats


def is_ignored(rel, pats):
    """True when .gitignore excludes this repo-relative path.

    Covers the forms this .gitignore actually uses: a bare name or glob matched
    against any path segment, a trailing slash for a directory, a leading slash to
    anchor at the repository root, and a pattern containing a slash matched against
    the whole path. Negation (!) is honoured last, as git does. Anything more exotic
    than that is not implemented, and would be a reason to widen this function rather
    than to trust its answer.
    """
    parts = rel.split("/")
    ignored = False
    for pat in pats:
        neg = pat.startswith("!")
        p = pat[1:] if neg else pat
        anchored = p.startswith("/")
        p = p.lstrip("/")
        is_dir = p.endswith("/")
        p = p.rstrip("/")
        if "/" in p:
            hit = fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(rel, p + "/*")
        elif anchored:
            hit = fnmatch.fnmatch(parts[0], p) and (not is_dir or len(parts) > 1)
        else:
            hit = any(fnmatch.fnmatch(seg, p) for seg in parts[:-1]) if is_dir \
                else any(fnmatch.fnmatch(seg, p) for seg in parts)
        if hit:
            ignored = not neg
    return ignored


# notebook_cells comes from evidence.py, where chk_settings_home.py reads it too. Both
# files held a copy that differed only in local names and wording, and both computed the
# same repository root for it; the shared one computes that root from its own location.


def iter_sources():
    """Every unit this gate reads, as (label, scope, source, file).

    label is what a finding points at (a path, or a path plus a cell number); file is
    what the ALLOW list keys on, so a notebook exemption would cover the notebook and
    not one of its cells.
    """
    pats = gitignore_patterns()
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs
                   if d not in ("__pycache__", ".git", "panel_ckpt_v2",
                                ".ipynb_checkpoints")]
        for f in sorted(files):
            path = os.path.join(base, f)
            rel = _rel(path)
            scope = "py" if f.endswith(".py") else "notebook"
            if is_ignored(rel, pats):
                scope = "untracked_" + scope
            if f.endswith(".py"):
                yield rel, scope, open(path, encoding="utf-8",
                                       errors="replace").read(), rel
            elif f.endswith(".ipynb") and ".ipynb_checkpoints" not in rel:
                for label, src in notebook_cells(rel):
                    yield label, scope, src, rel


def scan_literals(src):
    """Bare markout column names appearing as STRING literals."""
    hits = []
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return hits, "unparsable"
    for tok in toks:
        if tok.type != tokenize.STRING:
            continue
        raw = tok.string
        # only single-token plain strings, not docstrings or f-strings with code
        if raw[:1] in "fFrRbB" or raw[:3] in ('"""', "'''"):
            continue
        val = raw.strip("\"'")
        if COLUMN_RE.match(val):
            # The column offset is carried because the line number alone is not a
            # place. probe_D_funding.py:456 reads `"mo60": d["mo60"]` -- a field name
            # and a column read on one line -- and the gate reported it as two
            # findings that printed identically, which reads like a defect in the
            # gate rather than like two sites needing two edits.
            hits.append({"line": tok.start[0], "col": tok.start[1] + 1,
                         "column_name": val,
                         "source": src.splitlines()[tok.start[0] - 1].strip()[:120]})
    return hits, None


def scan_constants(src):
    """Assignments of a HEADLINE-ish horizon constant to a bare literal."""
    out = []
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return out
    lines = src.splitlines()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for tgt in node.targets:
            if not isinstance(tgt, ast.Name):
                continue
            # The name must be about a HORIZON. Matching on "HEADLINE" alone fired
            # on K_HEADLINE, HEADLINE_MIN_FILLS, HEADLINE_POLICY and K_PRIMARY,
            # none of which is a window -- a check that cries wolf gets ignored.
            if "HORIZON" not in tgt.id:
                continue
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, (int, str)):
                out.append({"line": node.lineno, "name": tgt.id,
                            "value": node.value.value,
                            "source": lines[node.lineno - 1].strip()[:120]})
    return out


def main():
    started = artifact.start_clock()
    violations, exempt_used, unparsable = [], [], []
    mirrors_checked = []
    n_ladder = 0
    present, notebooks, untracked = set(), set(), set()
    for rel, scope, src, base in iter_sources():
        if scope.startswith("untracked_"):
            untracked.add(base)
        (notebooks if scope.endswith("notebook") else present).add(base)

        lits, err = scan_literals(src)
        if err:
            unparsable.append(rel)
            continue
        # A LADDER READ is not a horizon choice. Naming mo1, mo10 and mo60 together --
        # inside one statement, or on consecutive lines of one block -- is code that
        # handles the whole ladder, which is the thing this rule is not about. Naming
        # ONE rung is a choice, and a silent one. Splitting them here is what lets the
        # file-level ALLOW shrink: a builder that writes all three rungs no longer needs
        # a blanket exemption, and a lone rung added to that same builder tomorrow is
        # still caught. A file-wide pass would have swallowed it.
        lits, ladder = split_ladder_reads(lits)
        n_ladder += len(ladder)
        if lits:
            if base in ALLOW:
                reason = ALLOW[base].strip()
                if not reason:
                    violations.append({"rule": "ALLOW-entry-without-reason",
                                       "file": rel, "scope": scope})
                else:
                    exempt_used.append({"file": base, "unit": rel,
                                        "n_literals": len(lits), "reason": reason})
            else:
                for h in lits:
                    home, seconds = declared_home(h["column_name"])
                    which = ("the headline window" if seconds == S.HEADLINE_HORIZON_S
                             else "the companion window"
                             if seconds == S.COMPANION_HORIZON_S
                             else "a ladder rung that is neither the headline nor the "
                                  "companion window")
                    fix = (f"read it through {home}, which returns "
                           f'"{h["column_name"]}" today, so the edit moves no number'
                           if home else
                           f"no accessor in settings.py spells this column: {seconds}s "
                           f"is outside LADDER_S={S.LADDER_S}, so the read has no "
                           f"declared home and the column may not exist at all")
                    violations.append({
                        "rule": "RULE-1-silent-horizon",
                        "file": rel, "scope": scope, "line": h["line"],
                        "col": h["col"], "column_name": h["column_name"],
                        "horizon_s": seconds, "declared_home": home,
                        "detail": (f'col {h["col"]}: bare column literal '
                                   f'"{h["column_name"]}" fixes {which} ({seconds}s) '
                                   f"without declaring it; {fix}; or add {base} to "
                                   f"ALLOW with the reason it is exempt"),
                        "source": h["source"]})

        for c in scan_constants(src):
            if base in ALLOW_CONST:
                continue
            # The notebook's one declaration of the window. It is exempt while it
            # equals what settings.py declares, and only then: the notebook cannot
            # import the module, so agreement is the only thing that keeps the repeat
            # from becoming a second headline. Checked here rather than trusted,
            # because this is the file a reader re-runs.
            if scope.endswith("notebook") and c["name"] in NOTEBOOK_HORIZON_MIRROR:
                target = NOTEBOOK_HORIZON_MIRROR[c["name"]]
                declared = getattr(S, target)
                agrees = c["value"] == declared
                mirrors_checked.append({"file": rel, "line": c["line"],
                                        "name": c["name"], "mirrors": target,
                                        "value": c["value"], "agrees": bool(agrees)})
                if agrees:
                    continue
                violations.append({
                    "rule": "RULE-2-notebook-window-drift",
                    "file": rel, "scope": scope, "line": c["line"],
                    "detail": (f'{c["name"]} = {c["value"]!r} is the notebook\'s repeat '
                               f"of settings.{target}, which declares {declared!r}. The "
                               f"notebook scores on its own copy, so a copy that "
                               f"disagrees silently reports another window's numbers "
                               f"under the headline name"),
                    "source": c["source"]})
                continue
            violations.append({
                "rule": "RULE-2-local-headline-constant",
                "file": rel, "scope": scope, "line": c["line"],
                "detail": (f'{c["name"]} = {c["value"]!r} declares a headline horizon '
                           f"locally; bind it to settings.HEADLINE_HORIZON_S, or rename "
                           f"it for the quantity it actually serves"),
                "source": c["source"]})

    # ALLOW entries that no longer match a file: stale exemptions hide new drift.
    present |= notebooks
    stale = sorted(k for k in ALLOW if k not in present)
    for k in stale:
        violations.append({"rule": "stale-ALLOW-entry", "file": k,
                           "detail": "exemption names a file that no longer exists"})

    # An exemption for a file that no longer NEEDS one is the same hazard in slower
    # motion. Once ladder reads stopped counting as violations, 15 of the 22 entries
    # went idle: the files they name are clean today, but the blanket stays, so the
    # first lone rung written into any of them tomorrow passes unseen. Reported, not
    # failed -- an unused exemption is dead weight, not a defect in the code it names.
    used = {e["file"] for e in exempt_used}
    idle = sorted(k for k in ALLOW if k in present and k not in used)

    # The 64 findings standing on the day this gate was written are pre-existing debt:
    # single-rung reads that need migrating to settings.py, not defects introduced with
    # it. Failing on all of them makes the gate unrunnable and therefore unrun. The gate
    # fails on anything ABOVE the recorded baseline, so a regression is caught the day
    # it lands, and the baseline is a debt figure that must only ever go down.
    baseline = BASELINE_VIOLATIONS
    def _n(scope):
        return sum(1 for v in violations if v.get("scope") == scope)
    # Four counts, because two distinctions matter and they are independent: script
    # against notebook, and shipped against scratch. A finding in a .gitignored
    # file is not debt the project owes -- a clone never contains that file.
    n_py, n_py_untracked = _n("py"), _n("untracked_py")
    n_nb, n_nb_untracked = _n("notebook"), _n("untracked_notebook")
    n_py += sum(1 for v in violations if "scope" not in v)      # stale-ALLOW entries
    #
    # What the baseline is compared against, and why it is the TRACKED count. The
    # figure frozen on 2026-07-30 covered both populations at once and so read loose by
    # exactly the untracked count below; since it came down to zero on 2026-07-31 it is
    # the tracked debt itself, and the run goes red on the first tracked regression. The
    # untracked count is reported and NOT gated: those files are excluded from the
    # repository a reader clones, so a horizon typed into one costs the project
    # nothing, and gating it would make the repository's debt impossible to drive to
    # zero.
    regressed = n_py > baseline or (BASELINE_VIOLATIONS_NOTEBOOK is not None
                                    and n_nb > BASELINE_VIOLATIONS_NOTEBOOK)
    # The verdict word is taken over the population this gate GATES, which is the
    # tracked tree. It used to be taken over every finding, .gitignored ones included,
    # and that made the word contradict the counts printed directly under it: with both
    # baselines at zero and no tracked finding left anywhere, the gate still wrote
    # PASS_AT_BASELINE, which README and run_all_checks.py both define as "known debt
    # recorded in its own baseline". A reader -- and the runner, which copies this word
    # out of the output -- would read standing horizon debt in the published repository
    # where the tracked count is 0 and the only findings sit in three exploration
    # harnesses nobody clones. Corrected 2026-07-31, the day the tracked count reached
    # zero and the defect became visible.
    #
    # This hides nothing. The untracked findings keep their own counts in _meta, they
    # are printed below under a heading that says what they are, and verdict_population
    # states in words what the word covers.
    gated_violations = [v for v in violations
                        if not str(v.get("scope", "py")).startswith("untracked_")]
    untracked_violations = [v for v in violations
                            if str(v.get("scope", "py")).startswith("untracked_")]
    verdict = ("FAIL" if regressed else
               ("PASS" if not gated_violations else "PASS_AT_BASELINE"))
    results = {
        "_meta": {
            "object": "source-level gate: the scoring horizon is declared, not typed",
            "scope_excluded": ["__pycache__/", "panel_ckpt_v2/"],
            "scope_uncovered_note": (
                "The notebooks "
                "are INSIDE this gate as of 2026-07-30: the reproduction notebook is "
                "what "
                "a reader re-runs, so a window fixed by spelling there costs "
                "what one in a script costs. Notebook findings are counted separately "
                "in n_violations_notebook and are not folded into the script baseline, "
                "because the two debts are worked off by different edits."),
            "n_violations_py": n_py,
            "n_violations_notebook": n_nb,
            "n_violations_untracked_py": n_py_untracked,
            "n_violations_untracked_notebook": n_nb_untracked,
            "untracked_files": sorted(untracked),
            "untracked_note": (
                "these files match a .gitignore rule, so they are not in the "
                "repository a reader clones and their findings are reported "
                "outside the gated count. The baseline above is compared against the "
                "TRACKED count only. It stood above the debt it gates while it was "
                "frozen over both populations at once; since 2026-07-31 it is 0, which "
                "is the tracked debt exactly, so the gate now goes red on the first "
                "horizon typed into a tracked file rather than on the tenth."),
            "gated_count": "tracked .py only",
            "verdict_population": (
                "tracked .py plus tracked notebook cells. PASS means no horizon is "
                "typed anywhere in the repository a reader clones; it does "
                "NOT speak for the gitignored files counted in "
                "n_violations_untracked_py, nor for the directories in "
                "scope_excluded, which are not read at all"),
            "baseline_violations_notebook": BASELINE_VIOLATIONS_NOTEBOOK,
            "baseline_notebook_note": (
                "null means the notebook count is measured and reported and cannot "
                "fail the run; set it to the count above to arm it, after which it "
                "may only go down."),
            "notebook_window_mirror": NOTEBOOK_HORIZON_MIRROR,
            "notebook_mirrors_checked": mirrors_checked,
            "rule_1": "a markout column name may not appear as a bare string literal "
                      "outside an ALLOW-listed file; it comes from the settings.py "
                      "accessor that spells that window -- headline_print_col/"
                      "headline_mid_col, or companion_print_col/companion_mid_col for "
                      "the long window -- and each finding names the one that returns "
                      "the string already written there, so acting on it moves no "
                      "number. UNLESS it sits in a ladder read: "
                      "mo1, mo10 and mo60 of one family named together within four "
                      "lines, which fixes no horizon. A lone rung is a choice and is "
                      "flagged even inside a file whose other lines are ladder reads. "
                      "Known holes: matches plain literals only, so an f-string, a "
                      "concatenation or a %-format spelling of the same name passes; "
                      "and the ALLOW exemption is still per FILE, not per line",
            "n_ladder_reads_exempted": n_ladder,
            "rule_2": "no file defines its own horizon constant as an integer literal. "
                      "Requires HORIZON in the name and a plain int assignment: an "
                      "annotated assignment, a tuple target, a float, an arithmetic "
                      "expression, or a name spelled WINDOW instead of HORIZON passes. "
                      "The notebook may repeat the declarations in "
                      "notebook_window_mirror, and only while each still equals what "
                      "settings.py declares",
            "n_files_scanned": len(present),
            "n_notebooks_scanned": len(notebooks),
            "n_exempt_files": len(exempt_used),
            "baseline_violations": baseline,
            "regressed_above_baseline": bool(regressed),
            "idle_exemptions": idle,
            "idle_exemptions_note": (
                "these files carry a blanket ALLOW entry they no longer need: every "
                "literal in them is now recognised as a ladder read. The entry is dead "
                "weight and a standing blind spot, because a lone rung added to any of "
                "them would be exempted rather than flagged. Delete them as they are "
                "confirmed unnecessary."),
            "unparsable": unparsable,
        },
        "verdict": verdict,
        "n_violations": len(violations),
        "violations": violations,
        "exemptions_in_use": exempt_used,
    }
    # This gate used to write its own file with json.dump, so it carried a _meta block
    # it had invented: a `scope` sentence, and no record of when the verdict was taken
    # or which build of this script took it. A verdict with no time on it cannot be
    # told from last year's. The descriptive fields above are unchanged and travel as
    # extra_meta; `scope` changes shape rather than meaning, because the module asks
    # for population, window and coins separately.
    carried = results.pop("_meta")
    artifact.write(
        os.path.basename(OUT_JSON), results,
        script=__file__,
        # The tree is the input and it is a list of files, so it is stated in scope
        # rather than hashed one by one: this gate reads every tracked source file and
        # hashing all of them would put the whole repository into its own artifact.
        inputs=[],
        scope={
            "population": f"{len(present)} .py and {len(notebooks)} .ipynb under this "
                          f"repository, walked in full, EXCEPT the directories in "
                          f"scope_excluded, which are not scanned at all and whose "
                          f"contents are therefore NOT covered by the verdict. A "
                          f"notebook finding points at file.ipynb#cellN and a line "
                          f"inside that cell",
            "window": "n/a: this gate reads source text as it stands now, not a "
                      "period of market data. The windows it counts are the ones "
                      "SPELLED in that text",
            "coins": "n/a: this gate reads source text and touches no market data",
        },
        started=started,
        # No overrides. This gate reads the declaration in force to decide which
        # column name spells which window, so the plain fingerprint is what its run
        # used; passing the two horizons as overrides would stamp `overridden` and
        # say a deliberate difference had been made where there is none.
        extra_meta=carried,
    )

    print(f"[chk_headline_horizon] {verdict}  files={len(present)}  "
          f"exempt={len(exempt_used)}  violations={len(violations)}")
    print(f"    tracked .py       : {n_py} (baseline {baseline}, gated)")
    print(f"    tracked notebook  : {n_nb} (baseline "
          f"{BASELINE_VIOLATIONS_NOTEBOOK if BASELINE_VIOLATIONS_NOTEBOOK is not None else 'not set'}"
          f", gated)")
    print(f"    untracked .py     : {n_py_untracked} in {len(untracked)} gitignored "
          f"files, reported only")
    # Printed as two blocks, not one list. They used to run together, so eleven
    # findings in files nobody has to fix filled the screen under the same heading as
    # the findings that fail the run, and the reader had to carry the tracked/untracked
    # split in his head to know which lines were his.
    def _print_findings(items, limit=40):
        for v in items[:limit]:
            loc = f'{v["file"]}:{v.get("line", "-")}'
            print(f"  {v['rule']:32s} {loc}")
            print(f"      {v['detail']}")
            if "source" in v:
                print(f"      | {v['source']}")
        if len(items) > limit:
            print(f"  ... and {len(items) - limit} more (see "
                  f"{os.path.basename(OUT_JSON)})")

    _print_findings(gated_violations)
    if untracked_violations:
        print(f"  -- below: {len(untracked_violations)} findings in "
              f"{len(untracked)} gitignored files. Reported, NOT gated, and not part "
              f"of the verdict: these files are excluded from the repository the "
              f"reader clones --")
        _print_findings(untracked_violations)
    # PASS_AT_BASELINE exits clean: the debt is reported, not treated as a failure, so
    # the gate can sit in a check suite and still mean something when it goes red.
    #
    # What the block below adds is the sentence the list above never carried. A
    # regression printed forty violations and a count, and the reader had to know
    # already that the count is judged against a frozen debt figure, which of the two
    # populations is gated, and which of the forty lines are the NEW ones. The two
    # rules are reported separately because they are paid off by different work and
    # only the tracked count of each is gated.
    return report_gate(
        [{"name": "tracked .py above the frozen horizon-literal debt",
          "permitted": baseline,
          "found": n_py,
          "assumption": ("the scoring horizon is declared once in settings.py and "
                         "never typed as a literal, so the study cannot quote two "
                         "windows at each other. The ceiling is a debt figure, not a "
                         "target: it started at the count standing on the day this "
                         "gate was written, it may only ever be lowered, and it comes "
                         "down only behind a migration that was actually done. The run "
                         "goes red the moment tracked debt rises above it"),
          "method": ("RULE 1 flags a bare markout-column literal outside an "
                     "ALLOW-listed file unless it sits in a ladder read of mo1, "
                     "mo10 and mo60 within four lines; RULE 2 flags a file that "
                     "declares its own HORIZON as a plain int"),
          "note": (f"the {n_py_untracked} findings in {len(untracked)} gitignored "
                   f"files are counted separately and deliberately NOT gated -- the "
                   f"clone never contains those files -- and they are kept OUT "
                   f"of the place list above, which used to hold them. A reader "
                   f"acting on a red run was being sent to probe_battery.py, a file "
                   f"this count does not include and nobody has to fix: the fact and "
                   f"the place disagreed about which population was failing. The "
                   f"untracked findings are in the results file under scope "
                   f"untracked_py"),
          # Only the population the count is taken over. A site list wider than the
          # count is not evidence, it is a second question.
          "sites": [v for v in violations
                    if v.get("scope") == "py" or "scope" not in v]},
         {"name": "tracked notebook cells above their frozen debt",
          "permitted": BASELINE_VIOLATIONS_NOTEBOOK,
          "found": n_nb,
          "assumption": ("a notebook may repeat the declarations in "
                         "notebook_window_mirror, and only while each still equals "
                         "what settings.py declares"),
          "method": "the same two rules, walked over every code cell",
          "sites": [v for v in violations if v.get("scope") == "notebook"]}],
        OUT_JSON,
        inputs={"declared_in": "settings.py",
                "tree": "every tracked .py and .ipynb under this repository"})


if __name__ == "__main__":
    sys.exit(main())
