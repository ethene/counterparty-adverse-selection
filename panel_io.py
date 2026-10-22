"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-07-31
References: internal settings.py (the declared scoring window and lens); internal
build.py (the producer of each panel named below); no external source.

READING THE MARKOUT PANEL: ONE PLACE FOR THE FILE, THE WINDOW AND THE LENS.

WHAT THIS MODULE IS FOR. Every number in this study is a markout -- how far the price
had moved a fixed number of seconds after a fill -- and every markout is read out of one
of four .npz panels on disk. Fifty-seven of the eighty-three tracked scripts call
np.load for themselves, and each of them repeats three decisions that are not really
theirs to take:

  1. WHERE THE FILE IS. Five different environment-variable names for one idea are in
     force today (CAP_DATA_ROOT, CAP_DATA_DIR, CAP_CHECK_ROOT, PANEL_DATA_ROOT,
     PANEL_V2_DATA_ROOT), so relocating the data means knowing which script speaks which
     name.
  2. WHICH COLUMN IS THE SCORE. This is the expensive one, and it does not look like a
     decision at all. A line reading z["mo60"] fixes the scoring horizon at sixty
     seconds exactly as firmly as a constant would, while grepping for the word horizon
     will never find it. The repository declares ten seconds in settings.py;
     checks/chk_headline_horizon.py counts how many places still spell a window instead
     of asking for it.
  3. WHAT TO SAY WHEN THE COLUMN IS NOT THERE. Each file writes its own message, and a
     KeyError on a mid-lens column read from a print-lens panel is a common enough
     mistake to deserve one worded answer.

So this module holds those three decisions once. It computes nothing: no number in the
study changes because a script reads its panel through here rather than by hand, and
that is the property that makes the migration safe to do file by file.

WHAT IT DELIBERATELY DOES NOT DO. It does not invent a way of naming columns. The window
and the lens are declared in settings.py and spelled by settings.headline_print_col(),
settings.headline_mid_col() and their companions; this module calls those and adds no
fourth spelling. It also does not type a markout column name anywhere in its own source,
which is what lets it satisfy the gate rather than be exempted from it.

THE FOUR PANELS, and why there are four rather than one. Two of them are the same fills
scored against two different reference prices, which answer two different questions: the
trade print is what the counterparty actually paid, so the maker's earned spread sits
inside it, while the book mid at the same instant takes the spread out and leaves the
price move alone. The other two are the wider cross-month panel and its rebuild. All
four are gitignored intermediates, not repository content, so a fresh clone has to run
the producer named beside each one before anything here will open.

WHY THE CALLER STILL WRITES np.load ITSELF, which looks like the one thing a loader
module ought to have taken over. build.py derives the dependency graph of this project
from the syntax trees of the scripts: the argument of np.load is an input edge, the
first argument of artifact.write is an output edge. That derivation is deliberately
syntactic, because a mention is not an edge -- matching on names once attributed
fourteen producers to one file -- and its price is that a path build.py cannot fold to a
constant makes NO edge at all. A call of the form np.load(P.open_panel("mid")) folds to
nothing, because the fold does not follow a call into another module. Swallowing the
load here therefore costs the project a real property: measured on 2026-07-31, moving
the load of twenty-eight scripts inside this module deleted 30 edges from the graph and
took build.py's own residue of unaccounted I/O calls from zero to ten, against a
declared ceiling of zero.

So the division of labour is the one that keeps both properties. This module owns WHERE
the file is, WHICH column is the score, and WHAT IS SAID when either is missing. The
caller keeps one line, np.load(NPZ_PATH), where NPZ_PATH is a module-level constant
build.py can fold, so the edge stays derived rather than declared by hand -- and a
derived edge cannot go stale, while a hand-written one silently can.

USAGE

    import panel_io as P

    NPZ_PATH = os.path.join(P.data_root(), "quickwin_markouts_mid.npz")
    ...
    P.require_present("mid", NPZ_PATH)    # or says which producer writes it
    z = np.load(NPZ_PATH)
    y = P.score(z, "mid")                 # the declared window, mid lens: mo10_mid today
    y60 = P.score(z, "mid", H.COMPANION_HORIZON_S)      # the companion window
    notional = P.column(z, "notional")    # any other column, same refusal wording

Self-check, which needs no data on disk:

    uv run --no-project python3 panel_io.py
"""
import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import settings as H                                              # noqa: E402

# The panels this module knows, each with the lens its markout columns are measured
# against and the producer that writes it. The lens belongs to the FILE and not to the
# caller: quickwin_markouts.npz carries trade-print columns and nothing else, so asking
# it for a mid column is a mistake the caller should not be able to make by accident.
# The producer is carried so that a missing file names the command that creates it --
# these are gitignored intermediates, and on a fresh clone every one of them is absent.
PANELS = {
    "print": {
        "file": "quickwin_markouts.npz",
        "lens": "print",
        "producer": "build_quickwin_markouts.py",
        "what": "one row per fill of the headline window, scored against the trade print",
    },
    "mid": {
        "file": "quickwin_markouts_mid.npz",
        "lens": "mid",
        "producer": "i4_midmarkout.py",
        "what": "the same fills in the same row order, scored against the book mid, "
                "plus the book state at entry",
    },
    "panel": {
        "file": "panel_markouts.npz",
        "lens": "print",
        "producer": "panel_persistence.py --build",
        "what": "the cross-month panel: the same fields as the print panel plus period",
    },
    "panel_v2": {
        "file": "panel_markouts_v2.npz",
        "lens": "panel_v2_lens",   # replaced below; see the loop under this dict
        "producer": "panel_rebuild_v2.py",
        "what": "the rebuild of the cross-month panel, carrying block time and the "
                "liquidation flag as well",
    },
}
PANELS["panel_v2"]["lens"] = PANELS["panel"]["lens"]   # same columns, same reference price

# The environment variables already in force in the tree for "the directory the .npz
# files live in". This module honours all of them rather than adding a sixth name,
# because a script that speaks one of these today has to keep speaking it after it is
# migrated, or the migration moves behaviour instead of only moving code. They are read
# in this order and the first one SET and non-empty wins.
DATA_ROOT_ENV = ("CAP_DATA_ROOT", "CAP_DATA_DIR", "CAP_CHECK_ROOT",
                 "PANEL_DATA_ROOT", "PANEL_V2_DATA_ROOT")


class PanelError(Exception):
    """Something was asked of a panel that the panel cannot answer.

    One class rather than three, because the three failures a caller can hit -- an
    unknown panel, a horizon off the declared ladder, a column the file does not hold --
    are all the same mistake seen from different sides: the request names something the
    repository has not declared. Every message names WHAT WAS ASKED and WHAT EXISTS,
    in that order, because a refusal that does not say what is available sends the
    reader back to the file with a hex editor.
    """


# =====================================================================
# 1. WHERE THE FILE IS
# =====================================================================

def data_root(explicit=None, env_names=DATA_ROOT_ENV):
    """The directory the panels are read from.

    Resolution order, first hit wins: an explicit argument (a --data-root flag), then
    each environment variable in env_names, then the directory this module lives in.
    The last step is why no absolute path appears anywhere: the location is derived at
    run time from the module's own file, so a clone into any directory finds its data
    without editing anything.
    """
    if explicit:
        return os.path.abspath(explicit)
    for name in env_names:
        raw = (os.environ.get(name) or "").strip()
        if raw:
            return os.path.abspath(raw)
    return HERE


def known_panels():
    """The panel kinds this module can open, for an error message or a --help line."""
    return tuple(sorted(PANELS))


def spec(kind):
    """The declaration for one panel kind, refusing an unknown kind by name."""
    if kind not in PANELS:
        raise PanelError(
            f"unknown panel kind {kind!r}; the declared kinds are "
            f"{', '.join(known_panels())}")
    return PANELS[kind]


def panel_file(kind):
    """The basename of the panel, with no directory attached."""
    return spec(kind)["file"]


def lens_of(kind):
    """Which reference price this panel's markout columns are measured against."""
    return spec(kind)["lens"]


def producer_of(kind):
    """The command that writes this panel, named in the message when it is absent."""
    return spec(kind)["producer"]


def panel_path(kind, root=None, env_names=DATA_ROOT_ENV):
    """Full path to a panel. Existence is not checked here; open_panel checks it."""
    return os.path.join(data_root(root, env_names), panel_file(kind))


# =====================================================================
# 2. WHICH COLUMN IS THE SCORE
# =====================================================================

def score_col(kind, h=None):
    """The markout column of this panel at horizon h seconds.

    The name is never typed here. It comes from the accessors in settings.py that own
    the spelling, so this function cannot disagree with the declaration even by a
    typo, and a horizon outside the declared ladder is refused by settings.py before
    this function returns anything. h defaults to the declared headline window.

    The LENS is not a parameter: it is a property of the panel, taken from the table
    above. That closes the one mistake that is easy to make and hard to see -- asking
    the trade-print panel for a book-mid column, which raises a bare KeyError deep in
    numpy and looks like a corrupt file.
    """
    lens = lens_of(kind)
    seconds = H.HEADLINE_HORIZON_S if h is None else int(h)
    try:
        return (H.headline_mid_col(seconds) if lens == "mid"
                else H.headline_print_col(seconds))
    except ValueError as exc:
        raise PanelError(
            f"asked panel {kind!r} for a {seconds}s markout column; the declared "
            f"ladder is {H.LADDER_S} seconds, so no such column was ever written "
            f"({exc})") from exc


def ladder_cols(kind):
    """Every markout column this panel carries, headline first, then the rest.

    A file that legitimately walks the whole term structure asks for the ladder here
    instead of naming three columns, so the walk moves by itself when the declaration
    moves.
    """
    rungs = [H.HEADLINE_HORIZON_S] + [s for s in H.LADDER_S
                                      if s != H.HEADLINE_HORIZON_S]
    return tuple(score_col(kind, s) for s in rungs)


# =====================================================================
# 3. OPENING, AND REFUSING TO HAND OVER WHAT IS NOT THERE
# =====================================================================

def require_present(kind, path=None, root=None, env_names=DATA_ROOT_ENV):
    """Refuse to go on when the panel is not on disk, and return its path.

    The caller loads it: see the note in the module docstring on why the np.load stays
    at the call site. What this function removes from the caller is the message, which
    was written out once per script and said something slightly different each time.
    The message names the producer, because the panels are gitignored intermediates and
    a fresh clone carries none of them, so "it is missing" without "run this" is only
    half an answer.

    path is accepted so that a caller which already holds the constant it is about to
    load passes that very constant, and this function cannot check one file while the
    caller loads another.
    """
    resolved = path or panel_path(kind, root, env_names)
    if not os.path.exists(resolved):
        raise FileNotFoundError(
            f"{os.path.basename(resolved)} not found in "
            f"{os.path.basename(os.path.dirname(resolved))}{os.sep}. It is a gitignored "
            f"intermediate, so a fresh clone does not carry it: run "
            f"{producer_of(kind)} to write it, or point one of "
            f"{', '.join(env_names)} at the directory that holds it.")
    return resolved


def require_columns(z, kind, *names):
    """Refuse at the top when a column the analysis needs is not in the file.

    Given a handle the caller has just opened, this turns a failure deep inside the
    work into one refusal before any of it, worded the same way everywhere.
    """
    for name in names:
        _require_column(z, name, kind)
    return z


def _require_column(z, name, kind=None):
    """Refuse a column the file does not hold, naming what was asked and what exists."""
    if name in z.files:
        return
    where = f"panel {kind!r} ({panel_file(kind)})" if kind else "this npz"
    raise PanelError(
        f"asked {where} for the column {name!r}; it holds "
        f"{len(z.files)} columns and that is not one of them. Present: "
        f"{', '.join(sorted(z.files))}")


def column(z, name, dtype=None, kind=None):
    """One named column, with the refusal above instead of a bare KeyError."""
    _require_column(z, name, kind)
    arr = z[name]
    return arr if dtype is None else arr.astype(dtype)


def score(z, kind, h=None, dtype="float64"):
    """The markout column of this panel at the declared window, as float64.

    This is the one call the analysis scripts want: it settles the horizon, the lens
    and the missing-column message in a single line, and it settles them the same way
    everywhere. The dtype is spelled as a string rather than as numpy.float64 so that
    this module needs no numpy import at all: everything it does is names, paths and
    messages, and a module with no array dependency is one the gate scanning for stray
    reads of the panel never has to make an exception for.
    """
    return column(z, score_col(kind, h), dtype=dtype, kind=kind)


def columns_of(kind, root=None, env_names=DATA_ROOT_ENV):
    """The column names a panel on disk actually holds, read without loading any array.

    An .npz is a zip of one member per column, so the member list answers "what is in
    this file" from the directory alone, at no cost and without numpy. It is what the
    self-check below compares this module's claims against.
    """
    path = require_present(kind, root=root, env_names=env_names)
    with zipfile.ZipFile(path) as zf:
        return sorted(n[:-4] if n.endswith(".npy") else n for n in zf.namelist())


# =====================================================================
# 4. SELF-CHECK
#
# It runs without any panel on disk, because the panels are gitignored intermediates
# and the point of the check is that the module's own logic is sound, not that this
# machine happens to hold the data. Where a panel IS present it is opened as well, and
# its column list is compared against what the module claims the panel carries.
# =====================================================================

def self_check(verbose=True):
    """Exercise every promise this module makes. Returns a dict, raises on failure."""
    out = {"checks": [], "panels_on_disk": [], "panels_absent": []}

    def ok(what, got, want):
        passed = got == want
        out["checks"].append({"check": what, "got": got, "want": want,
                              "passed": passed})
        if verbose:
            print(f"  [{'ok ' if passed else 'FAIL'}] {what}: {got!r}")
        if not passed:
            raise AssertionError(f"{what}: expected {want!r}, got {got!r}")

    # -- the column names agree with settings.py, which is the only source ----
    ok("score_col('print') is the headline print column",
       score_col("print"), H.headline_print_col())
    ok("score_col('mid') is the headline mid column",
       score_col("mid"), H.headline_mid_col())
    ok("score_col('panel') follows the print lens",
       score_col("panel"), H.headline_print_col())
    ok("score_col('print', companion) is the companion print column",
       score_col("print", H.COMPANION_HORIZON_S), H.companion_print_col())
    ok("score_col('mid', companion) is the companion mid column",
       score_col("mid", H.COMPANION_HORIZON_S), H.companion_mid_col())
    ok("the ladder for the mid panel has one column per declared rung",
       len(ladder_cols("mid")), len(H.LADDER_S))
    ok("the ladder for the mid panel leads with the headline column",
       ladder_cols("mid")[0], H.headline_mid_col())

    # -- the refusals fire, and say what was asked and what exists ------------
    off_ladder = max(H.LADDER_S) + 1
    try:
        score_col("mid", off_ladder)
    except PanelError as exc:
        ok(f"a {off_ladder}s window is refused and the message names the ladder",
           str(H.LADDER_S) in str(exc) and str(off_ladder) in str(exc), True)
    else:
        raise AssertionError(f"a {off_ladder}s window was NOT refused")

    try:
        spec("no_such_panel")
    except PanelError as exc:
        ok("an unknown panel kind is refused and the message lists the kinds",
           all(k in str(exc) for k in known_panels()), True)
    else:
        raise AssertionError("an unknown panel kind was NOT refused")

    class _Fake:
        files = ["coin", "notional"]

        def __getitem__(self, k):
            raise KeyError(k)

    try:
        column(_Fake(), "not_a_column", kind="mid")
    except PanelError as exc:
        ok("a missing column is refused and the message names asked and present",
           "not_a_column" in str(exc) and "notional" in str(exc), True)
    else:
        raise AssertionError("a missing column was NOT refused")

    # -- the location is derived, never typed --------------------------------
    # Compared as booleans and not printed as paths: the answer here IS an absolute
    # path on whatever machine runs it, and printing it would put the account name of
    # the person running the check into any log they paste.
    ok("with nothing set, the root is this module's own directory",
       data_root(env_names=()) == HERE, True)
    ok("an explicit root wins over the module's directory",
       data_root(explicit=os.path.join(HERE, "somewhere"), env_names=())
       == os.path.join(HERE, "somewhere"), True)
    os.environ["PANEL_IO_SELFCHECK_ROOT"] = os.path.join(HERE, "elsewhere")
    try:
        ok("a named environment variable wins over the module's directory",
           data_root(env_names=("PANEL_IO_SELFCHECK_ROOT",))
           == os.path.join(HERE, "elsewhere"), True)
    finally:
        del os.environ["PANEL_IO_SELFCHECK_ROOT"]

    # -- and where the data is present, the claims are checked against it -----
    for kind in known_panels():
        path = panel_path(kind)
        if not os.path.exists(path):
            out["panels_absent"].append(kind)
            continue
        cols = set(columns_of(kind))
        missing = [c for c in ladder_cols(kind) if c not in cols]
        out["panels_on_disk"].append({"kind": kind, "file": panel_file(kind),
                                      "n_columns": len(cols),
                                      "ladder_missing": missing})
        if verbose:
            print(f"  [{'ok ' if not missing else 'FAIL'}] {panel_file(kind)} carries "
                  f"every rung of the declared ladder ({len(cols)} columns present)")
        if missing:
            raise AssertionError(
                f"{panel_file(kind)} is missing {missing}, so the lens or the ladder "
                f"this module declares for {kind!r} does not match the file")

    return out


if __name__ == "__main__":
    print("panel_io self-check")
    print(f"  declared window {H.HEADLINE_HORIZON_S}s, companion "
          f"{H.COMPANION_HORIZON_S}s, ladder {H.LADDER_S}")
    res = self_check()
    n = len(res["checks"])
    print(f"  {n} checks passed; panels present: "
          f"{[p['kind'] for p in res['panels_on_disk']] or 'none'}; absent: "
          f"{res['panels_absent'] or 'none'}")
