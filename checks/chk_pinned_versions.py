#!/usr/bin/env python3
"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-08-28
References: none (repository reproducibility gate; the pins it reads are declared in
requirements.txt, where the reason for each one is written beside it).

EVERY RESULTS FILE IS ASKED WHICH LIBRARY VERSIONS COMPUTED IT, AND THE ANSWER IS
HELD AGAINST requirements.txt.

Why this gate exists, and it is a measurement rather than a worry. artifact.py has
stamped the versions of the libraries a producer had loaded into _meta.run.packages
since 2026-07-30, and until today nothing in this tree ever read one back. A record
written and never read is worth what an unwritten one is worth: on the day this gate
was added, ten of the eighty-five artifacts carrying a version record had been
computed under numpy 2.5.1 while requirements.txt pins numpy==2.4.6, and they had sat
that way for weeks with every other gate in this battery green.

How that happens is written down in requirements.txt itself and is not carelessness.
`uv run --no-project --with numpy python3` resolves numpy freshly on the day it runs
and announces nothing; `uv run --no-project --with-requirements requirements.txt
python3` honours the pins. The two commands differ by six words, they leave no trace
in any number, and the only thing that tells them apart afterwards is the version the
run wrote down. This gate is the thing that reads it.

WHAT IS COMPARED, AND IN WHICH DIRECTION. The recorded version is the fact. The
specifier in requirements.txt is the expectation. An exact pin (`==`) must be met
exactly; a range (`>=`, `<`, and the rest) must be satisfied. The comparison is on the
numeric release, so 2.4.6 and 2.4.6.0 are the same version and a string equality test
would have called them different.

FOUR OUTCOMES, AND EVERY RECORDED PACKAGE LANDS IN EXACTLY ONE. Keeping them apart is
the point: three of the four would read as a pass under a gate that only counted
mismatches.

  satisfied      a specifier exists for this distribution and the recorded version
                 meets it
  violated       a specifier exists and the recorded version does not meet it. This is
                 the finding the gate is for
  unpinned       a version was recorded for a distribution requirements.txt does not
                 constrain at all. Not a pass: the run stood on a library whose version
                 nothing in this repository fixes, so the next reader resolves whatever
                 the index serves them that day
  uncomparable   a specifier or a version this gate cannot order -- a URL requirement,
                 a wildcard, a pre-release suffix. Never silently a pass, because a
                 comparison that could not be made is not a comparison that succeeded

AND A FIFTH HEAP THAT IS NOT ABOUT PACKAGES BUT ABOUT SILENCE. An artifact carrying no
_meta.run.packages at all has not passed this gate, it has not been asked. Its size is
printed. artifact.py builds that block by reading sys.modules rather than by importing
anything, so a producer that never imports numpy legitimately records nothing, and on
the day this gate was written all 22 silent artifacts were of that kind: the syntax of
every one of their producers was walked and not one of them imports a pinned
distribution. That is what makes the silence readable rather than merely quiet, and it
is why the armed rule below is not the raw heap but the sharp question inside it --
an artifact that recorded nothing whose producer does import a pinned distribution.
That count is zero today and the rule is armed at zero.

The heap grows by one when this gate's own results file is COMMITTED, and not before,
which is worth saying because the two events are days apart. In a checkout the
population is the index, so an uncommitted results file is invisible to the census
however many times the gate has run; in an extracted source archive there is no index
and it counts from the first run. Either way it belongs there and is not a defect: it
carries a _meta, and its producer -- this file -- imports no pinned distribution, so it
is a legitimately silent artifact like the other twenty-two.

WHAT artifact.py DOES AND DOES NOT STAMP, because the gate can only judge what was
recorded. Its list is five import names: numpy, scipy, pandas, sklearn, statsmodels.
Three pinned distributions are outside it -- matplotlib, pyarrow and lz4 -- so no
artifact in this tree carries a version for any of them and this gate is blind to all
three by construction. The blindness is reported by name on every run rather than left
for someone to discover, and it is a property of the recorder rather than of this gate:
widening it belongs in artifact.py.

THE CEILING, AND IT MOVES ONE WAY ONLY. Ten artifacts violate a pin today. Repairing
them is a recompute of ten nodes, which is a decision somebody makes rather than one
this gate makes for them, so the debt is declared here BY NAME with its date and its
reason. Two rules follow from one declaration, on the two axes a debt can grow along:
the count may not rise above the number declared, and a violation in a file the
declaration does not name is a regression whatever the count says. The second rule is
what a bare count misses -- ten repaired and ten fresh ones would leave the count
unmoved.

    uv run --no-project --with-requirements requirements.txt python3 \
        checks/chk_pinned_versions.py
    uv run --no-project --with-requirements requirements.txt python3 \
        checks/chk_pinned_versions.py --calibrate

Read-only apart from its own results file. Exits non-zero on a regression, and prints
the expectation, the fact and the place for each one.
"""
import argparse
import ast
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
import artifact                                                          # noqa: E402
from evidence import report_gate, shipped_tree_files                     # noqa: E402

OUT_JSON = os.path.join(HERE, "chk_pinned_versions_results.json")

# The file that declares what a version is allowed to be. Named relative to this
# module's own location at run time, never as a path into a machine.
REQUIREMENTS = "requirements.txt"

# The address inside an artifact where a producer writes what it had loaded. Written
# once here and used everywhere below, so the gate and its report cannot drift apart.
PACKAGES_PATH = ("_meta", "run", "packages")

# WHICH IMPORT NAME BELONGS TO WHICH DISTRIBUTION, and this map is explicit because the
# relation cannot be derived. `import sklearn` comes from the distribution
# `scikit-learn`, and no rule about hyphens and underscores produces that. artifact.py
# records the IMPORT name, requirements.txt pins the DISTRIBUTION name, and a gate that
# guessed the translation would report a pinned package as unpinned.
#
# An import name absent from this map is reported as unpinned rather than skipped. That
# is the safe direction: a package this gate has never heard of is exactly the case
# where silence would be wrong.
IMPORT_TO_DISTRIBUTION = {
    "numpy": "numpy",
    "scipy": "scipy",
    "pandas": "pandas",
    "sklearn": "scikit-learn",
    "statsmodels": "statsmodels",
    "matplotlib": "matplotlib",
    "pyarrow": "pyarrow",
    "lz4": "lz4",
}

# The import name a pinned distribution would be recorded under, which is the map above
# read the other way. Used only to say which pins no artifact witnesses.
DISTRIBUTION_TO_IMPORT = {dist: imp for imp, dist in IMPORT_TO_DISTRIBUTION.items()}

# One clause of a version specifier. `===` is arbitrary-string equality in the packaging
# standard rather than a comparison of releases, so it is deliberately NOT accepted here
# and falls through to uncomparable.
CLAUSE_RE = re.compile(r"^(==|!=|~=|>=|<=|>|<)\s*(.+)$")

# A requirement line: a distribution name, then everything the line says about its
# version. Anything more elaborate -- a URL requirement, an extra, an environment
# marker -- fails this match and is carried through as uncomparable rather than dropped.
REQUIREMENT_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)\s*(.*)$")

# THE DECLARED DEBT, BY NAME AND NOT ONLY BY COUNT. Ten artifacts were computed under a
# resolve that ignored the pins, and repairing them is a recompute of ten nodes rather
# than an edit here. Each entry is the artifact, what it recorded, what was pinned, and
# the date the debt was declared.
#
# RAISING THIS IS FORBIDDEN. A ceiling that rises to meet the tree measures nothing. It
# comes down one entry at a time as each node is recomputed under the pinned resolve,
# and every run that comes in under the ceiling prints the lower number it would accept.
DECLARED_DEBT = {}

# Why the six stand, in one sentence, so a reader of a PASS_AT_BASELINE run knows WHAT
# is standing and not only how much.
DEBT_REASON = (
    "empty as of 2026-08-29, lowered from six and before that from ten. Every artifact "
    "this tree ships now records a version its pin admits: 107 of 107 satisfied, 0 "
    "violated. The last six were recomputed under the pinned resolve on 2026-08-29 in "
    "runs of 14, 15, 54, 86, 722 and 1615 seconds against recorded costs of 11.1, 13.9, "
    "49.1, 84.2, 699.2 and 1617.0. Nothing moved: 3242 content leaves compared before "
    "and after at a relative tolerance of 1e-12, declared before the runs, and 0 moved; "
    "0 leaves vanished; the 33 that appeared are provenance fields artifact.py did not "
    "write when these files were last built. The four inputs were hashed before the runs "
    "and all four matched what the artifacts recorded, so any move would have been "
    "attributable to the library and not to the data. This ceiling may only be lowered, "
    "and it is now at its floor: a violation from here is a regression, not a debt."
)


def release(text):
    """The numeric release tuple of a version string, or None if it is not plain.

    None is the answer for anything carrying a suffix -- 1.2.3rc1, 2.4.6.post1, a
    local version. Those are orderable under the full packaging rules and are not
    ordered here, and returning None routes them to `uncomparable` where a reader can
    see them, rather than to a comparison this gate would get subtly wrong.
    """
    parts = str(text).strip().split(".")
    out = []
    for part in parts:
        if not part.isdigit():
            return None
        out.append(int(part))
    return tuple(out) if out else None


def _padded(left, right):
    """The two releases zero-extended to a common length.

    This is what makes 2.4.6 and 2.4.6.0 the same version. A string comparison calls
    them different, and an artifact recording the second against a pin naming the first
    would be reported as a violation it is not.
    """
    width = max(len(left), len(right))
    return left + (0,) * (width - len(left)), right + (0,) * (width - len(right))


def satisfies(version, specifier):
    """Whether *version* meets *specifier*.

    Returns (True, ""), (False, why) or (None, why). None means the pair could not be
    compared at all, which is neither a pass nor a violation and is counted as its own
    outcome. A gate that folded it into either one would be reporting an answer it
    never obtained.
    """
    found = release(version)
    if found is None:
        return None, (f"the recorded version {version!r} is not a plain dotted numeric "
                      f"release, so this gate does not order it")
    if not str(specifier).strip():
        return None, "no specifier was given"
    for clause in str(specifier).split(","):
        clause = clause.strip()
        if not clause:
            continue
        match = CLAUSE_RE.match(clause)
        if not match:
            return None, (f"the clause {clause!r} is not one this gate reads; it "
                          f"accepts ==, !=, ~=, >=, <=, > and <")
        operator, bound_text = match.group(1), match.group(2).strip()
        bound = release(bound_text)
        if bound is None:
            return None, (f"the bound {bound_text!r} in {clause!r} is not a plain "
                          f"dotted numeric release")
        left, right = _padded(found, bound)
        if operator == "==":
            ok = left == right
        elif operator == "!=":
            ok = left != right
        elif operator == ">=":
            ok = left >= right
        elif operator == "<=":
            ok = left <= right
        elif operator == ">":
            ok = left > right
        elif operator == "<":
            ok = left < right
        else:                                                            # ~=
            if len(bound) < 2:
                return None, (f"{clause!r} is compatible-release with a single "
                              f"component, which names no series to stay inside")
            prefix = bound[:-1]
            head = (found + (0,) * len(prefix))[:len(prefix)]
            ok = left >= right and head == prefix
        if not ok:
            return False, f"{version} does not satisfy {clause}"
    return True, ""


def read_pins(path):
    """Distribution -> the specifier requirements.txt gives it, plus what was skipped.

    Read from the file rather than restated here. The pins are that file's to declare,
    and a gate holding its own copy of them is the failure this project has already met
    twice: two instruments answering one question differently because the second kept a
    private copy of the first one's list.
    """
    pins, unreadable = {}, []
    with open(path, encoding="utf-8") as handle:
        for number, raw in enumerate(handle.read().split("\n"), start=1):
            line = raw.split("#", 1)[0].strip()
            if not line or line.startswith("-"):
                continue
            match = REQUIREMENT_RE.match(line)
            if not match:
                unreadable.append({"line": number, "text": line[:120],
                                   "why": "not a distribution name followed by a "
                                          "version specifier"})
                continue
            name, specifier = match.group(1), match.group(2).strip()
            key = re.sub(r"[-_.]+", "-", name).lower()
            if not specifier:
                # A bare name pins nothing. Recorded as a pin with an empty specifier
                # so that an artifact naming it is reported as uncomparable rather than
                # as satisfied, which is the direction that does not travel.
                unreadable.append({"line": number, "text": line[:120],
                                   "why": "names a distribution and constrains no "
                                          "version, so nothing can be held against it"})
            pins[key] = specifier
    return pins, unreadable


def artifacts():
    """Every shipped .json carrying a _meta block, as (repo-relative path, document).

    The population is the shared shipped-tree census, so a Git checkout reads its index
    and a reviewer handed an extracted ZIP walks the archive. Files that are not JSON
    objects, and objects without a _meta, are not results files and are counted apart.
    """
    found, skipped = [], []
    for rel in shipped_tree_files(ROOT):
        if not rel.endswith(".json"):
            continue
        path = os.path.join(ROOT, rel)
        try:
            with open(path, encoding="utf-8") as handle:
                document = json.load(handle)
        except (OSError, ValueError) as exc:
            skipped.append({"file": rel, "why": f"unreadable as JSON: {exc}"})
            continue
        if not isinstance(document, dict) or not isinstance(document.get("_meta"),
                                                            dict):
            skipped.append({"file": rel, "why": "no _meta block, so it is not a "
                                                "results file of this tree"})
            continue
        found.append((rel, document))
    return found, skipped


def recorded_packages(document):
    """The _meta.run.packages map of an artifact, or None when it records none.

    None and {} are deliberately the same answer here and both mean NOT ASKED. What
    they are not is a pass.
    """
    node = document
    for key in PACKAGES_PATH:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node if isinstance(node, dict) and node else None


def producer_imports(document, script_index):
    """The pinned distributions the artifact's own producer imports, by its syntax.

    This is what turns silence into a reading. An artifact recording no versions is
    only innocent if the script that wrote it never loaded a pinned library, and that
    is answerable from the source rather than guessable: artifact.py builds its block
    from sys.modules, so a producer that imports nothing pinned records nothing and is
    right to.

    Returns (distributions, resolved), where resolved is False when the producer could
    not be found in the tree at all -- which is not the same as finding it and seeing
    no imports, and is reported as its own thing.
    """
    producer = document.get("_meta", {}).get("producer")
    name = producer.get("script") if isinstance(producer, dict) else None
    path = script_index.get(os.path.basename(str(name))) if name else None
    if not path:
        return set(), False
    try:
        with open(path, encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
    except (OSError, SyntaxError, ValueError):
        return set(), False
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imported.add(node.module.split(".")[0])
    return {IMPORT_TO_DISTRIBUTION[n] for n in imported
            if n in IMPORT_TO_DISTRIBUTION}, True


def script_index():
    """Basename -> absolute path, for every shipped Python file."""
    index = {}
    for rel in shipped_tree_files(ROOT):
        if rel.endswith(".py"):
            index.setdefault(os.path.basename(rel), os.path.join(ROOT, rel))
    return index


def judge(pins, population, scripts):
    """Sort every recorded (artifact, package) pair into the four outcomes.

    Returns a dict of lists. Each entry carries the file, the address inside it, the
    expectation and the fact, because a finding a reader cannot act on is a rumour.
    """
    out = {"satisfied": [], "violated": [], "unpinned": [], "uncomparable": [],
           "no_record": [], "no_record_but_uses_pinned": [], "producer_unresolved": []}
    for rel, document in population:
        packages = recorded_packages(document)
        if packages is None:
            uses, resolved = producer_imports(document, scripts)
            row = {"file": rel, "line": ".".join(PACKAGES_PATH),
                   "detail": "no version record: this artifact was never asked which "
                             "libraries computed it",
                   "producer_imports_pinned": sorted(uses),
                   "producer_resolved": resolved}
            out["no_record"].append(row)
            if uses:
                out["no_record_but_uses_pinned"].append(dict(
                    row, detail=("the producer imports " + ", ".join(sorted(uses)) +
                                 ", which this repository pins, and the artifact "
                                 "records no version for any of them")))
            if not resolved:
                out["producer_unresolved"].append(row)
            continue
        for import_name, version in sorted(packages.items()):
            address = ".".join(PACKAGES_PATH) + "." + str(import_name)
            distribution = IMPORT_TO_DISTRIBUTION.get(str(import_name))
            key = (re.sub(r"[-_.]+", "-", distribution).lower() if distribution
                   else re.sub(r"[-_.]+", "-", str(import_name)).lower())
            specifier = pins.get(key)
            base = {"file": rel, "line": address, "recorded": str(version),
                    "package": str(import_name), "distribution": distribution or key,
                    "specifier": specifier}
            if specifier is None:
                out["unpinned"].append(dict(base, detail=(
                    f"{import_name} {version} was loaded by the run and "
                    f"{REQUIREMENTS} constrains no version for it, so the next reader "
                    f"resolves whatever the index serves them"),
                    source=f"recorded {import_name}=={version}, pinned: nothing"))
                continue
            verdict, why = satisfies(version, specifier)
            if verdict is True:
                out["satisfied"].append(base)
            elif verdict is False:
                out["violated"].append(dict(base, detail=(
                    f"{import_name} was pinned {specifier} and this artifact was "
                    f"computed under {version}"),
                    source=f"expected {key}{specifier}, recorded {version}. {why}"))
            else:
                out["uncomparable"].append(dict(base, detail=why,
                    source=f"pinned {key}{specifier}, recorded {version}"))
    return out


def debt_faults(violated, table=None):
    """Violations the declaration does not name, which is the second axis of the debt.

    A count alone cannot see this. Ten entries repaired and ten fresh ones arriving
    leaves the count at ten while nothing the declaration promised is still true, and
    that is the shape a ceiling on a bare number always misses.
    """
    table = DECLARED_DEBT if table is None else table
    faults = []
    for row in violated:
        declared = table.get(row["file"])
        if declared is None:
            faults.append(dict(row, detail=(
                "this artifact violates a pin and is not named in the declared debt: "
                + row["detail"])))
            continue
        package, version, _date = declared
        if row["package"] != package or row["recorded"] != version:
            faults.append(dict(row, detail=(
                f"the declaration admits {package} {version} for this file and the "
                f"tree reports {row['package']} {row['recorded']}")))
    return faults


def _fixture(packages, producer=None):
    """A results-file document shaped the way artifact.write builds one."""
    meta = {"run": {"packages": dict(packages)}} if packages is not None else {"run": {}}
    if producer:
        meta["producer"] = {"script": producer}
    return {"_meta": meta}


def calibrate(population):
    """Two opposite cases per predicate, and the must-fire half really fires.

    Rows are (predicate, case, got, want, ok).

    THE FIXTURES ARE WRITTEN OUT HERE RATHER THAN NAMED ON DISK, and that is the whole
    reason this calibration survives its own success. The ten artifacts this gate finds
    today are meant to be recomputed; a calibration anchored on one of them would go
    vacuous the day it was repaired, and would do it silently.

    THE LIVE PAIR IS RUN AS WELL, because a fixture proves the predicate and only the
    tree proves the wiring. Both live cases are selected by reading the recorded version
    string directly, never by asking the predicate which files it flags -- a case chosen
    by the instrument under test certifies the instrument against itself. When the tree
    no longer holds a violating artifact the live must-fire case is reported as absent
    and does NOT fail: that absence is this gate's purpose achieved, and failing on it
    would make the repair look like a regression.
    """
    rows = []

    def case(predicate, what, got, want):
        rows.append((predicate, what, got, want, got == want))

    # Exact pin. Equal, unequal, and equal only after zero-extension: the third is
    # there because a string comparison passes the first two and fails the third.
    case("exact pin", "must stay silent: recorded equals the pin",
         satisfies("2.4.6", "==2.4.6")[0], True)
    case("exact pin", "must fire: recorded is a later release than the pin",
         satisfies("2.5.1", "==2.4.6")[0], False)
    case("exact pin", "must stay silent: 2.4.6.0 and 2.4.6 are one release",
         satisfies("2.4.6.0", "==2.4.6")[0], True)
    case("exact pin", "must fire: recorded is an earlier release than the pin",
         satisfies("2.4.5", "==2.4.6")[0], False)

    # Range. Inside, over the upper bound, under the lower bound.
    case("range", "must stay silent: inside both bounds",
         satisfies("1.18.0", ">=1.14,<2")[0], True)
    case("range", "must fire: at or above the upper bound",
         satisfies("2.0.0", ">=1.14,<2")[0], False)
    case("range", "must fire: below the lower bound",
         satisfies("1.13.0", ">=1.14,<2")[0], False)
    case("compatible release", "must stay silent: inside the series",
         satisfies("1.14.9", "~=1.14.2")[0], True)
    case("compatible release", "must fire: outside the series",
         satisfies("1.15.0", "~=1.14.2")[0], False)

    # Uncomparable. Neither a pass nor a violation, and the point of the case is that
    # it is neither: an unreadable specifier answering True is the dangerous direction.
    case("uncomparable", "must refuse: a pre-release suffix this gate does not order",
         satisfies("1.2.3rc1", "==1.2.3")[0], None)
    case("uncomparable", "must refuse: a wildcard clause",
         satisfies("1.2.3", "==1.2.*")[0], None)
    case("uncomparable", "must refuse: arbitrary-string equality",
         satisfies("1.2.3", "===1.2.3")[0], None)

    # The map from import name to distribution. sklearn resolving to scikit-learn is
    # the case no rule about punctuation produces, and getting it wrong would report a
    # pinned package as unpinned.
    case("name map", "must translate: the import name sklearn is scikit-learn",
         IMPORT_TO_DISTRIBUTION.get("sklearn"), "scikit-learn")
    case("name map", "must not invent: an unknown import name has no distribution",
         IMPORT_TO_DISTRIBUTION.get("torch"), None)

    # The sorter, end to end, on documents shaped the way artifact.write builds them.
    pins = {"numpy": "==2.4.6", "scipy": ">=1.14,<2"}
    scripts = script_index()
    sorted_out = judge(pins, [
        ("fixture_good.json", _fixture({"numpy": "2.4.6"})),
        ("fixture_bad.json", _fixture({"numpy": "2.5.1"})),
        ("fixture_unpinned.json", _fixture({"statsmodels": "0.14.0"})),
        ("fixture_silent.json", _fixture(None)),
    ], scripts)
    case("sorter", "must fire once: one fixture records a version outside its pin",
         len(sorted_out["violated"]), 1)
    case("sorter", "must stay silent: the fixture inside its pin is not a finding",
         [r["file"] for r in sorted_out["violated"]], ["fixture_bad.json"])
    case("sorter", "must fire: a recorded package nothing pins is its own outcome",
         [r["file"] for r in sorted_out["unpinned"]], ["fixture_unpinned.json"])
    case("sorter", "must fire: an artifact with no record is not a pass",
         [r["file"] for r in sorted_out["no_record"]], ["fixture_silent.json"])

    # The debt, on the axis a count cannot see. The same violation named and unnamed.
    # The table here is a FIXTURE and not the live DECLARED_DEBT on purpose: a case
    # anchored on the live debt erases itself the day the debt is cleared, and then
    # these three stop testing anything -- `next(iter({}))` does not even run. The
    # predicate is what is under test, not how many entries the tree happens to carry.
    fixture_debt = {"fixture/declared.json": ("numpy", "2.5.1", "2026-08-29")}
    named = "fixture/declared.json"
    package, version, _date = fixture_debt[named]
    declared_row = {"file": named, "package": package, "recorded": version,
                    "detail": "d", "line": "l"}
    case("declared debt", "must stay silent: a violation the declaration names",
         len(debt_faults([declared_row], fixture_debt)), 0)
    case("declared debt", "must fire: the same violation in a file not named",
         len(debt_faults([dict(declared_row, file="not/declared.json")], fixture_debt)), 1)
    case("declared debt", "must fire: a named file violating on another version",
         len(debt_faults([dict(declared_row, recorded="9.9.9")], fixture_debt)), 1)

    # THE GATE'S OWN POPULATION. How many pins are actually asked is printed beside every
    # count and on the verdict line, so it earns the same two cases as any other
    # predicate: a pin nothing records must be named as unasked, and a pin something
    # records must not be.
    witnessed = {"satisfied": [{"distribution": "numpy"}], "violated": [],
                 "uncomparable": []}
    case("gate population", "must fire: a pin no artifact records is named unasked",
         [row["distribution"]
          for row in unwitnessed_pins({"numpy": "==2.4.6", "lz4": ">=4"},
                                      witnessed)[0]], ["lz4"])
    case("gate population", "must stay silent: a pin an artifact records is asked",
         [row["distribution"]
          for row in unwitnessed_pins({"numpy": "==2.4.6"}, witnessed)[0]], [])

    # THE LIVE PAIR. Selected by reading the version string out of the artifact, not by
    # asking this gate which files it flags.
    live_bad = live_good = None
    for rel, document in population:
        packages = recorded_packages(document) or {}
        if packages.get("numpy") == "2.5.1" and live_bad is None:
            live_bad = rel
        if packages.get("numpy") == "2.4.6" and live_good is None:
            live_good = rel
    if live_good is not None:
        verdict, _why = satisfies("2.4.6", "==2.4.6")
        case("live tree", f"must stay silent: {live_good} recorded numpy 2.4.6",
             verdict, True)
    else:
        rows.append(("live tree", "no artifact in this tree records numpy 2.4.6, so "
                     "the silent half has no live case today", None, None, True))
    if live_bad is not None:
        verdict, _why = satisfies("2.5.1", "==2.4.6")
        case("live tree", f"must fire: {live_bad} recorded numpy 2.5.1 against "
                          f"the pin 2.4.6", verdict, False)
    else:
        rows.append(("live tree", "no artifact in this tree violates a pin, so the "
                     "firing half has no live case left. That is this gate's purpose "
                     "reached, and the fixtures above still hold it armed",
                     None, None, True))
    return rows


def unwitnessed_pins(pins, outcomes):
    """Pins no artifact in this tree carries a version for, with the reason.

    Printed on every run rather than left to be discovered. A pin nothing witnesses is
    not guarded by this gate at all, and for three of them the cause is upstream and
    named: artifact.py stamps five import names and matplotlib, pyarrow and lz4 are not
    among them, so no artifact could carry those versions however it ran.
    """
    seen = {row["distribution"] for key in ("satisfied", "violated", "uncomparable")
            for row in outcomes[key]}
    stamped = set()
    try:
        with open(os.path.join(ROOT, "artifact.py"), encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
    except (OSError, SyntaxError, ValueError):
        tree = None
    if tree is not None:
        # The names artifact.py loops over when it builds the block, read from its
        # syntax rather than retyped: a list copied here would go stale against the
        # module the moment somebody widened it, which is the whole disease this gate
        # is about.
        for node in ast.walk(tree):
            if not isinstance(node, ast.For) or not isinstance(node.iter, ast.Tuple):
                continue
            values = [e.value for e in node.iter.elts
                      if isinstance(e, ast.Constant) and isinstance(e.value, str)]
            if "numpy" in values:
                stamped |= {IMPORT_TO_DISTRIBUTION.get(v, v) for v in values}
    missing = []
    for key in sorted(pins):
        if key in {re.sub(r"[-_.]+", "-", s).lower() for s in seen if s}:
            continue
        import_name = DISTRIBUTION_TO_IMPORT.get(key, key)
        if stamped and key not in stamped:
            why = ("artifact.py does not stamp it: the block it writes names "
                   + ", ".join(sorted(stamped)))
        else:
            why = "no artifact in this tree records a version for it"
        missing.append({"distribution": key, "import_name": import_name,
                        "specifier": pins[key], "why": why})
    return missing, sorted(stamped)


def main(argv=None):
    parser = argparse.ArgumentParser(description=(
        "hold every recorded library version against the pins in requirements.txt"))
    parser.add_argument("--calibrate", action="store_true", help=(
        "run only the calibration: the cases this gate must fire on and the cases it "
        "must stay silent on, and nothing else"))
    args = parser.parse_args(argv)

    started = artifact.start_clock()
    requirements = os.path.join(ROOT, REQUIREMENTS)
    pins, unreadable_pins = read_pins(requirements)
    population, skipped = artifacts()
    scripts = script_index()
    outcomes = judge(pins, population, scripts)
    calibration = calibrate(population)
    calibration_failed = [row for row in calibration if not row[4]]

    if args.calibrate:
        print("=" * 76)
        print("  PINNED VERSIONS - calibration only")
        print("=" * 76)
        for predicate, what, got, want, ok in calibration:
            print(f"  {'ok  ' if ok else 'FAIL'} {predicate}: {what}")
            if not ok:
                print(f"       expected {want!r}, got {got!r}")
        print("-" * 76)
        print(f"  cases {len(calibration)}, failed {len(calibration_failed)}")
        print(f"  VERDICT: {'PASS' if not calibration_failed else 'FAIL'}")
        return 1 if calibration_failed else 0

    violated = outcomes["violated"]
    faults = debt_faults(violated)
    missing_pins, stamped = unwitnessed_pins(pins, outcomes)
    judged = len(outcomes["satisfied"]) + len(violated) + len(outcomes["unpinned"]) \
        + len(outcomes["uncomparable"])
    with_record = len(population) - len(outcomes["no_record"])
    over = len(violated) > len(DECLARED_DEBT)
    verdict = ("FAIL" if over or faults or outcomes["unpinned"]
               or outcomes["uncomparable"] or outcomes["no_record_but_uses_pinned"]
               or calibration_failed
               else ("PASS" if not violated else "PASS_AT_BASELINE"))

    print("=" * 76)
    print("  PINNED VERSIONS - every recorded library version against requirements.txt")
    print("=" * 76)
    print(f"  calibration cases  : {len(calibration)}, failed "
          f"{len(calibration_failed)}")
    for predicate, what, got, want, ok in calibration:
        print(f"  {'ok  ' if ok else 'FAIL'} {predicate}: {what}")
        if not ok:
            print(f"       expected {want!r}, got {got!r}")
    # POPULATION AND PREDICATE BESIDE THE COUNT. A zero without them is not a zero
    # anybody can act on: it does not say what was looked at or what was looked for.
    print("-" * 76)
    print(f"  population         : {len(population)} shipped .json files carrying a "
          f"_meta block, of {len(shipped_tree_files(ROOT))} shipped files; "
          f"{len(skipped)} .json files carry no _meta and are not results files")
    print(f"  predicate          : the version at "
          f"{'.'.join(PACKAGES_PATH)}.<import name> of each artifact, held against the "
          f"specifier {REQUIREMENTS} gives that distribution, compared on the numeric "
          f"release")
    print(f"  pins read          : {len(pins)} from {REQUIREMENTS} "
          f"({', '.join(sorted(pins))})")
    # THE GATE'S OWN POPULATION, BESIDE ITS COUNT AND NOT IN A FOOTNOTE. Everything
    # below this line is a statement about the pins that are ASKED, and that is fewer
    # than the pins that exist. A green verdict which does not name the population it
    # covers is the disease this gate was built against, so the number is printed here,
    # at the head of the counts, and again on the verdict line itself.
    print(f"  pins asked         : {len(pins) - len(missing_pins)} of {len(pins)}. "
          f"{len(missing_pins)} are asked by nothing"
          + (": " + ", ".join(row["distribution"] for row in missing_pins)
             if missing_pins else ""))
    print(f"  artifacts asked    : {with_record} carry a version record, "
          f"{len(outcomes['no_record'])} carry none")
    print(f"  package records    : {judged} (artifact, package) pairs judged")
    print(f"  satisfied          : {len(outcomes['satisfied'])}")
    print(f"  violated           : {len(violated)}")
    print(f"  unpinned           : {len(outcomes['unpinned'])}")
    print(f"  uncomparable       : {len(outcomes['uncomparable'])}")
    print(f"  ceiling            : {len(DECLARED_DEBT)}, a declared debt naming each "
          f"file, which may only be lowered")

    for row in violated:
        declared = DECLARED_DEBT.get(row["file"])
        print(f"  {'declared' if declared else 'NOT DECLARED':12} {row['file']}")
        print(f"      | {row['source']}")
        if declared:
            print(f"      | allowed since {declared[2]}")
    for row in outcomes["unpinned"]:
        print(f"  UNPINNED     {row['file']}")
        print(f"      | {row['source']}")
    for row in outcomes["uncomparable"]:
        print(f"  UNCOMPARABLE {row['file']}")
        print(f"      | {row['source']}: {row['detail']}")
    for row in outcomes["no_record_but_uses_pinned"]:
        print(f"  SILENT       {row['file']}")
        print(f"      | {row['detail']}")
    for row in unreadable_pins:
        print(f"  PIN UNREAD   {REQUIREMENTS}:{row['line']}  {row['why']}")
        print(f"      | {row['text']}")

    # THE SILENT HEAP, SIZED. An artifact that was never asked has not passed, and the
    # sentence saying how much of the tree that is belongs beside the counts above.
    print(f"  no version record  : {len(outcomes['no_record'])} artifacts, of which "
          f"{len(outcomes['no_record_but_uses_pinned'])} have a producer that imports "
          f"a pinned distribution and {len(outcomes['producer_unresolved'])} have a "
          f"producer this tree could not resolve. The rest import nothing pinned, so "
          f"the block artifact.py builds from sys.modules is empty for a reason")
    # WHAT THIS GATE CANNOT SEE, NAMED. A pin nothing records is unguarded here, and
    # saying so is worth more than a count that quietly covers fewer packages than a
    # reader assumes.
    print(f"  stamped by artifact.py : {', '.join(stamped) or 'unreadable'}")
    for row in missing_pins:
        print(f"  UNWITNESSED  {row['distribution']}{row['specifier']}: {row['why']}")
    if not violated and DECLARED_DEBT:
        print("  no artifact violates a pin. The ceiling above is now pure headroom "
              "and should be lowered to 0 by emptying DECLARED_DEBT.")
    elif not violated:
        print("  no artifact violates a pin and the debt is empty. A violation from "
              "here is a regression against a floor, not a debt to be declared.")
    elif not over and len(violated) < len(DECLARED_DEBT):
        print(f"  the debt today is {len(violated)}, under the ceiling of "
              f"{len(DECLARED_DEBT)}. Remove the cleared entries from DECLARED_DEBT.")
    if calibration_failed:
        print("  CALIBRATION FAILED: no zero in this report can be believed.")
    print("-" * 76)
    # The verdict carries its population in the same sentence. Read on its own,
    # "PASS_AT_BASELINE" says every pin holds; it does not, and cannot, because three
    # of the seven are recorded by nobody. Saying so here costs one line and is the
    # difference between a verdict and a verdict a reader can act on.
    print(f"  VERDICT: {verdict}, over {len(pins) - len(missing_pins)} of the "
          f"{len(pins)} pins in {REQUIREMENTS}"
          + (f". It says nothing about "
             + ", ".join(row["distribution"] for row in missing_pins)
             + ": no artifact records a version for them"
             if missing_pins else ""))
    print(f"  results -> {os.path.basename(OUT_JSON)}")

    artifact.write(
        os.path.basename(OUT_JSON),
        {"verdict": verdict,
         "n_artifacts": len(population),
         "n_with_version_record": with_record,
         "n_package_records_judged": judged,
         "n_satisfied": len(outcomes["satisfied"]),
         "n_violated": len(violated),
         "n_unpinned": len(outcomes["unpinned"]),
         "n_uncomparable": len(outcomes["uncomparable"]),
         "n_no_record": len(outcomes["no_record"]),
         "n_no_record_but_producer_uses_pinned":
             len(outcomes["no_record_but_uses_pinned"]),
         # The gate's own population, written into the artifact and not only printed.
         # Every count above is a statement about the pins that are asked, and that is
         # the smaller of the two numbers.
         "n_pins": len(pins),
         "n_pins_asked": len(pins) - len(missing_pins),
         "n_pins_asked_by_nothing": len(missing_pins),
         "baseline": len(DECLARED_DEBT),
         "violated": violated,
         "undeclared_violations": faults,
         "unpinned": outcomes["unpinned"],
         "uncomparable": outcomes["uncomparable"],
         "no_record": outcomes["no_record"],
         "pins": pins,
         "pins_unreadable": unreadable_pins,
         "pins_unwitnessed": missing_pins,
         "packages_stamped_by_artifact_module": stamped,
         "non_artifact_json": skipped,
         "calibration": [{"predicate": p, "case": w, "got": repr(g), "want": repr(x),
                          "ok": ok} for p, w, g, x, ok in calibration]},
        script=__file__,
        # requirements.txt is the expectation this gate reads, so it is hashed as an
        # input: when the pins move, this artifact is stale and the freshness gates of
        # this directory say so. The artifacts themselves are the population and are
        # stated in scope rather than hashed, for the same reason the absolute-path
        # gate does not hash the tree it reads.
        inputs=[requirements],
        scope={
            "population": (f"{len(population)} shipped .json files carrying a _meta "
                           f"block; {judged} (artifact, package) version records "
                           f"judged against {len(pins) - len(missing_pins)} of the "
                           f"{len(pins)} pins in {REQUIREMENTS}. The other "
                           f"{len(missing_pins)} are recorded by no artifact at all, "
                           f"so no verdict here covers them"),
            "window": "n/a: this gate reads the repository as it stands now, not a "
                      "period of market data",
            "coins": "n/a: this gate reads recorded version strings and touches no "
                     "market data",
        },
        started=started,
        extra_meta={
            "baseline_note": (
                f"a declared debt of {len(DECLARED_DEBT)} artifacts, named one by one "
                f"in this gate's own DECLARED_DEBT rather than counted, so that a "
                f"repaired entry replaced by a fresh violation cannot pass under an "
                f"unmoved total. {DEBT_REASON}"),
            "declared_debt": [{"file": name, "package": package, "recorded": version,
                               "declared": date}
                              for name, (package, version, date) in
                              sorted(DECLARED_DEBT.items())],
            "n_calibration_cases": len(calibration),
            "n_calibration_failed": len(calibration_failed),
            "blind_to": ("pins for which no artifact records a version: "
                         + ", ".join(row["distribution"] for row in missing_pins)
                         if missing_pins else "no pin is unwitnessed"),
        },
    )

    return report_gate(
        [{"name": "PIN-VIOLATION",
          "permitted": len(DECLARED_DEBT),
          "found": len(violated),
          "assumption": (
              "every artifact was computed under a library version this repository "
              "pins. A reader clones this tree, follows the run command in "
              f"{REQUIREMENTS}, and must get the numbers the report carries; a node "
              "computed under a version nothing fixes is a number nobody can "
              "reproduce. The ceiling is a declared debt of "
              f"{len(DECLARED_DEBT)} artifacts, named individually, and may only be "
              "lowered"),
          "method": (f"the version at {'.'.join(PACKAGES_PATH)}.<import name> of every "
                     f"shipped .json carrying a _meta block, held against the "
                     f"specifier {REQUIREMENTS} gives that distribution, compared on "
                     f"the numeric release rather than as a string"),
          "note": ("recompute the node under `uv run --no-project --with-requirements "
                   f"{REQUIREMENTS} python3`, then remove its entry from "
                   "DECLARED_DEBT. The short resolve form does not honour the pins"),
          "sites": violated},
         {"name": "PIN-VIOLATION-UNDECLARED",
          "permitted": 0,
          "found": len(faults),
          "assumption": (
              "a violation the declared debt does not name by file and version is a "
              "regression whatever the total says. Ten entries repaired and ten fresh "
              "ones arriving leaves the count unmoved while nothing the declaration "
              "promised is still true, and a ceiling on a bare number cannot see it"),
          "method": ("each violating file looked up in DECLARED_DEBT by name, and its "
                     "recorded package and version compared with what the entry "
                     "admits"),
          "note": ("either the node was recomputed and its entry should go, or a new "
                   "artifact was written under an unpinned resolve"),
          "sites": faults},
         {"name": "VERSION-RECORDED-BUT-UNPINNED",
          "permitted": 0,
          "found": len(outcomes["unpinned"]),
          "assumption": (
              f"every library a run loads and records is constrained by "
              f"{REQUIREMENTS}. A version recorded against no pin reads like a pass "
              "and is not one: nothing fixes it, so the next reader resolves whatever "
              "the index serves them on the day"),
          "method": ("each recorded import name translated to its distribution through "
                     "this gate's explicit map, then looked up among the pins; an "
                     "import name the map does not hold counts here rather than being "
                     "skipped"),
          "note": f"pin the distribution in {REQUIREMENTS}, with its reason beside it",
          "sites": outcomes["unpinned"]},
         {"name": "VERSION-UNCOMPARABLE",
          "permitted": 0,
          "found": len(outcomes["uncomparable"]),
          "assumption": (
              "every recorded version and every specifier can actually be ordered. A "
              "comparison that could not be made is not a comparison that passed, and "
              "folding it into either answer would report a verdict this gate never "
              "reached"),
          "method": ("the recorded version and each clause of the specifier parsed as "
                     "dotted numeric releases; anything else -- a wildcard, a "
                     "pre-release suffix, arbitrary-string equality -- lands here"),
          "note": ("widen the comparison in satisfies(), or write the version and the "
                   "pin in a form that can be ordered"),
          "sites": outcomes["uncomparable"]},
         {"name": "SILENT-BUT-USES-PINNED",
          "permitted": 0,
          "found": len(outcomes["no_record_but_uses_pinned"]),
          "assumption": (
              "an artifact that records no version was written by a producer that "
              "loaded no pinned library. That is what makes the silence readable: "
              "artifact.py builds its block from sys.modules, so a producer importing "
              "nothing pinned records nothing and is right to, while one that imports "
              "numpy and records nothing has lost the record"),
          "method": ("the syntax tree of each silent artifact's own producer walked "
                     "for imports, and those imports translated to distributions "
                     "through this gate's map"),
          "note": ("the producer wrote its results without artifact.write, or wrote "
                   "them before the block existed; recompute it through artifact.write"),
          "sites": outcomes["no_record_but_uses_pinned"]},
         {"name": "CALIBRATION",
          "permitted": 0,
          "found": len(calibration_failed),
          "assumption": (
              "before any zero above is believed, this gate is shown to find what it "
              "is looking for. Every predicate carries a case it must fire on and a "
              "case it must stay silent on, and one anchor is not enough: it cannot "
              "tell a predicate that is too wide from one that is too narrow"),
          "method": (f"{len(calibration)} cases: version fixtures written out in this "
                     f"file, and the live pair selected by reading the recorded "
                     f"version string rather than by asking this gate what it flags"),
          "note": "nothing this gate reported on this run means anything",
          "sites": [{"file": os.path.basename(__file__), "line": "calibrate()",
                     "detail": f"{p}: {w}", "source": f"expected {x!r}, got {g!r}"}
                    for p, w, g, x, _ok in calibration_failed]}],
        OUT_JSON,
        inputs={"pins": REQUIREMENTS,
                "tree": "shared checkout/archive shipped-tree census"})


if __name__ == "__main__":
    sys.exit(main())
