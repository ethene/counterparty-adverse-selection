#!/usr/bin/env python3
"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-07-31
References: none (repository gate; it reads only artifacts produced by this tree).

EVERY NUMBER THE WRITE-UP QUOTES MUST STILL BE THE NUMBER ITS ARTIFACT HOLDS.

WHY THIS CHECK EXISTS, AND WHY THE FIRST ATTEMPT AT IT DID NOT COUNT.

The paper this repository accompanies carries figures. Each figure came out of one script,
into one results file, under one setting. Nothing stops the file from being recomputed
after the sentence was written, and nothing stops the sentence from carrying a digit
that was never in the file. So the numbers need a gate.

A gate for exactly that was written on 2026-07-31 and it asked the wrong question. It
asked whether a number APPEARS SOMEWHERE in this tree. Run over two hundred INVENTED
values, it confirmed 136 of them. A test that accepts two thirds of made-up numbers is
not measuring the numbers; it is measuring how many numbers a large tree contains. The
defect is structural rather than a matter of tuning the search: a value has thousands
of chances to coincide with something when the population it is compared against is
the whole tree, so widening the tree makes the test weaker, and no threshold repairs
that.

WHAT CHANGED, AND IT IS THE WHOLE REASON THIS IS NOW POSSIBLE. The register of
quantities -- a registry.json kept beside the write-up -- now states, for each figure,
the artifact FILE it came out of and the KEY PATH inside that file. One address, not a
haystack. So this check never searches. It goes to the file the record names, walks the
key path the record names, reads what is there, and compares.

THE REGISTER DOES NOT SHIP WITH THIS REPOSITORY, AND THE CHECK SAYS SO RATHER THAN
GUESSING. It is a document of the write-up, not of the code, so a clone of the
repository does not contain it. The register is therefore an explicit input: it is
read from the path given by --registry PATH, or by the environment variable
PROSE_REGISTRY when no flag is given, and from nowhere else. With neither, the check
compares nothing, writes a results file whose single sub-check is `uncertain` with the
reason in words, prints NOT ANSWERED, and exits 0. It does not walk up out of the
repository to look for one: an earlier version did, and on a machine holding a second
copy of the tree above it, that walk resolved the register's file names against the
OTHER copy's artifacts, so the check reported on numbers this repository did not hold.
For the same reason every artifact a record names is resolved inside this repository
only.

THE THREE QUESTIONS THIS CHECK ANSWERS, AND THEY ARE SEPARATE.

  1. Where a registry figure could be joined to the artifact leaf its own address
     names, do the two numbers agree? A disagreement fails the run.
  2. Does every record name an address that can be reached at all? A record whose
     stated key path does not exist in its stated file cannot be traced by a reader,
     which is a defect of the same family even though no number is wrong. The count is
     held against a DECLARED DEBT rather than against zero, because the debt is real,
     measured, and not this check's to repair.
  3. Would this check notice if the figures were wrong? It corrupts every registry
     value and re-runs itself over the corrupted copy. The number of corrupted values
     it still accepts is printed on every run. That number is what separates this from
     the check it replaces, and it is measured rather than argued.

HOW A REGISTRY FIGURE IS JOINED TO AN ARTIFACT LEAF, AND WHY THE JOIN IS BY NAME.

A registry record holds `value`, which is either one number or a mapping of the
registry's own sub-names to numbers, and `source_key`, which names one or more key
paths inside `source_file`. The two vocabularies are not the same: the registry says
`btc` where the artifact says `BTC`, and it says `pooled` where the artifact path
happens to run through a segment called `pooled`. So the join has to be explicit, and
it obeys one rule above all others -- NOTHING IS EVER JOINED BY VALUE. A float is
never rounded into a key, and no figure is ever matched to "whichever leaf is closest",
because that is the degeneracy this check was written to end. Three rules, each of them
an equality between WHOLE NAMES, tried in this order:

  SINGLETON            the record declares one number and its address resolves to
                       exactly one number. There is nothing to pair up.
  PATH-INFIX           the registry's sub-name, read as a run of segments, appears as
                       a contiguous run inside the artifact's own key path, and every
                       artifact leaf it appears in holds the same number. Case is
                       folded, because `btc` and `BTC` are one name; nothing else about
                       the segment is allowed to differ.
  FAMILY-SUBSTITUTION  the address names one member of a family -- the `pooled` cell of
                       a per-coin block, say -- and the registry's sub-name is another
                       member. The sub-name replaces exactly one segment of the address
                       and must yield exactly one numeric leaf. If two positions would
                       both yield one, the substitution is ambiguous and is refused.

A registry sub-name that none of the three rules reaches is NOT guessed at. It is
counted as unaddressed and named in the results file, so the gap is visible instead of
being papered over by a looser rule.

WHAT COUNTS AS AGREEMENT, AND WHY THE TOLERANCE IS SET BY THE REGISTRY ITSELF.

The registry stores figures at the precision the prose uses. `0.1087` in the registry
sits against `0.10865165286860588` in the artifact, and those are the same number
written twice. A fixed tolerance would either call that a disagreement or would have to
be loosened until it accepted real errors, so the tolerance is derived from the
registry's own printing: half a unit in the last significant digit it chose to write,
measured where the figure sits and then expressed relatively. `0.1087` therefore buys
4.6e-4 and `0.70142521` buys 7.1e-9. A figure the registry stores as an integer -- a
row count, a wallet count -- must agree EXACTLY, because there is no rounding in a
count, and so must a declared zero, which has no last digit to round in.

That resolution is the right one rather than a comfortable one, and the run of
2026-07-31 shows it: the closest pair uses 96.7 per cent of its own tolerance. Any
tighter and correctly rounded copies would be reported as disagreements.

Two limits sit on the tolerance, both of them declared constants with a reason and a
date, and both movable only downwards.

Run:

    uv run --no-project python3 checks/chk_prose_numbers.py --registry PATH
    uv run --no-project python3 checks/chk_prose_numbers.py --registry PATH --verbose
    uv run --no-project python3 checks/chk_prose_numbers.py --self-test
    uv run --no-project python3 checks/chk_prose_numbers.py      # no register: says so
"""
import ast
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CODE_DIR = os.path.dirname(HERE)
for _p in (HERE, CODE_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import artifact                                                     # noqa: E402
from evidence import Tally, report_contract                         # noqa: E402

CHECK_NAME = "chk_prose_numbers"
OUT_JSON = os.path.join(HERE, "chk_prose_numbers_results.json")

# The register of quantities is an explicit input and has no default location. It is
# a document of the write-up rather than of this repository, so a clone does not have
# it, and this check says so and exits 0 rather than going red about a file that was
# never meant to be shipped. Only the basename is ever recorded.
REGISTRY_FLAG = "--registry"
REGISTRY_ENV = "PROSE_REGISTRY"
REGISTRY_NAME = "registry.json"
# The verdict of a run that had no register to read. Its own word, so that no reader --
# and not the battery -- can count a run that compared nothing among the passes.
SKIPPED_VERDICT = "SKIPPED_NO_REGISTRY"

# ----------------------------------------------------------------------------------
# THE TWO LIMITS ON THE TOLERANCE. Both are declared debt: reason, date, and the rule
# that they may be tightened and never loosened.
# ----------------------------------------------------------------------------------

# Floor. A figure the register copied at full double precision would otherwise buy a
# tolerance of about 5e-17, which is finer than the difference two decimal-to-binary
# round-trips of the same number can leave behind, so a true copy could read as a
# disagreement. Measured 2026-07-31: every one of those pairs is exactly equal today,
# so the floor is a guard rather than an accommodation, and it may be lowered if a
# round-trip is ever proved unnecessary. It is never raised.
MIN_REL_TOL = 1e-9

# Ceiling. Eight of the joined figures are printed to one or two significant digits --
# a fee ladder of 1.5, 0.4, 0.0 and three rebates, and two shares of exactly 1.0 --
# where half a unit in the last digit would buy a tolerance of five or fifty per cent.
# A gate that accepts a fifty per cent error accepts anything. All eight are exactly
# equal to their artifact, measured 2026-07-31, so the cap costs nothing today and
# closes the hole. Declared debt: lower it when the register stops printing any figure
# to fewer than three digits; never raise it.
MAX_REL_TOL = 1e-2

# Records this gate compares nothing from. Not zero, and the distance from zero is the
# register's to close rather than this check's: some point at a draft, an npz or a
# script rather than at a JSON artifact, some state their key path as a sentence, and
# some resolve to a block whose keys the register renamed into its own vocabulary.
# Frozen at what the run of 2026-07-31 measured and recorded stage by stage in
# chk_prose_numbers_results.json. Declared debt: lower it as records are given
# machine-readable addresses; never raise it.
UNCOMPARED_RECORD_DEBT = 70
UNCOMPARED_RECORD_DEBT_SET = "2026-07-31"

# What the degeneracy probe multiplies each registry figure by. Ten times the figure's
# own tolerance, floored at five per cent, so the corruption is noticeable BY THE
# STANDARD OF THE INSTRUMENT rather than by a number picked to look good.
DEGENERACY_TOLERANCE_MULTIPLE = 10.0
DEGENERACY_MIN_FRACTION = 0.05

# The instrument's range, reported rather than gated. A perturbation smaller than half
# the last digit the registry printed CANNOT be detected, and saying so with numbers is
# more use than a single pass mark. Each entry is a relative corruption.
# The rungs run past the tightest tolerance on purpose. A ladder that reads zero all
# the way down says only that it did not go far enough, and the useful statement is the
# rung where the check STOPS seeing the corruption.
RANGE_LADDER = (0.50, 0.05, 0.01, 1e-3, 1e-5, 1e-7, 1e-9, 1e-11)


# ----------------------------------------------------------------------------------
# FINDING THE FILES A REGISTRY RECORD NAMES
# ----------------------------------------------------------------------------------

# The register may name a file from above this repository, with leading directories
# of the tree it was written in. Only THIS repository is searched: the name is tried as
# stated against the repository root, then with its leading components dropped one at
# a time. Nothing above the root is ever tried, because a second copy of the tree
# sitting above a clone would otherwise answer for it. Nothing absolute is ever
# recorded: what the results file writes down is the name exactly as the register
# states it.
def locate(stated):
    """The stated file inside this repository, or None. The path is used, never recorded.

    A lookup, not a guess: the file either exists at the tried place or it does not.
    """
    if not isinstance(stated, str) or not stated.strip():
        return None
    parts = [p for p in stated.replace("\\", "/").split("/") if p and p != "."]
    if not parts:
        return None
    for cut in range(0, len(parts)):
        candidate = os.path.join(CODE_DIR, *parts[cut:])
        if os.path.isfile(candidate):
            return candidate
    return None


def registry_argument(argv=None, environ=None):
    """The register path the caller named, and how it was named; (None, None) if none.

    The flag wins over the environment, so a run can always say exactly which file it
    read. A path that is named but is not a file is returned as named, and main()
    refuses it as a finding rather than reading it as a bare clone: a typo in the path
    must not look like the ordinary state of a clone.
    """
    argv = sys.argv[1:] if argv is None else argv
    environ = os.environ if environ is None else environ
    for i, arg in enumerate(argv):
        if arg == REGISTRY_FLAG and i + 1 < len(argv):
            return argv[i + 1], "flag"
        if arg.startswith(REGISTRY_FLAG + "="):
            return arg.split("=", 1)[1], "flag"
    value = environ.get(REGISTRY_ENV)
    if value:
        return value, "env"
    return None, None


# ----------------------------------------------------------------------------------
# THE ADDRESS: READING A source_key AS KEY PATHS
# ----------------------------------------------------------------------------------

# A key path is a run of dotted segments. A segment is a name, a number, a `*` standing
# for every child, a brace set `{BTC,ETH}` standing for the listed children, or a brace
# placeholder `{h}` -- one token, no comma -- standing for every child. A segment may
# carry one bracket: `[3]` for a list position, `[*]` for every element, or
# `[period=202510, coin=BTC]` for the elements whose fields say so.
_NAME = r"[A-Za-z_][A-Za-z0-9_]*"
_SEGMENT = (r"(?:\*|" + _NAME + r"|[0-9]+)?(?:\{[^{}]*\})?(?:" + _NAME + r"|[0-9]+)?"
            r"(?:\[(?:\*|[0-9]+|[^\[\]]*=[^\[\]]*)\])?")
_ADDRESS = re.compile(r"\.?(?:" + _SEGMENT + r")(?:\.(?:" + _SEGMENT + r"))*")

# A module-level constant in a producer script, which is the other kind of address the
# registry uses: `mm_bakeoff.py :: QUOTER_NAMES (line 218)`.
_CONSTANT = re.compile(r"\b[A-Z][A-Z0-9_]{2,}\b")


def split_segments(text):
    """Split a dotted address, leaving the contents of brackets and braces alone."""
    segments, buf, depth = [], "", 0
    for ch in text:
        if ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        if ch == "." and depth == 0:
            segments.append(buf)
            buf = ""
        else:
            buf += ch
    segments.append(buf)
    return segments


def extract_addresses(source_key):
    """Every key path written in a source_key, in the order it writes them.

    A source_key is not always one address. It may name several, and it may carry a
    sentence around them. Two conventions the registry actually uses are honoured. A
    token beginning with a dot -- `oos_validity.auc_shrunk / .auc_raw_meanscore` --
    means a sibling of the address before it, so the previous parent is put back in
    front of it. Anything that resolves to nothing is simply dropped later, so prose
    around the addresses costs nothing but is never read AS an address.
    """
    if not isinstance(source_key, str):
        return []
    found, previous = [], None
    for match in _ADDRESS.finditer(source_key):
        token = match.group(0).strip()
        if not token or token == "." or not re.search(r"[A-Za-z]", token):
            continue
        if token.startswith("."):
            if previous is None:
                continue
            parent = split_segments(previous)[:-1]
            token = ".".join(parent + split_segments(token[1:]))
        found.append(token)
        previous = token
    ordered, seen = [], set()
    for token in found:
        if token not in seen:
            seen.add(token)
            ordered.append(token)
    return ordered


def _expand_braces(segment):
    """`K{10,50}` becomes K10 and K50; `{h}` becomes the wildcard `*`."""
    match = re.match(r"^(.*?)\{([^{}]*)\}(.*)$", segment)
    if not match:
        return [segment]
    before, inner, after = match.groups()
    if "," in inner:
        return [before + alt.strip() + after for alt in inner.split(",")]
    # One token inside braces is a placeholder for the name of the child, not a child
    # called that: `pooled.{h}.rho_disatt` means every horizon.
    return ["*"] if not (before or after) else [before + "*" + after]


def _child(node, name):
    """(key as the artifact spells it, value) for a WHOLE-name lookup, case folded.

    Case is the only thing forgiven, and only because `btc` and `BTC` are one name
    written twice. No prefix, no suffix and no partial match is ever accepted: that is
    what keeps this a lookup rather than a search.
    """
    if isinstance(node, dict):
        if name in node:
            return name, node[name]
        folded = {str(k).lower(): k for k in node}
        if name.lower() in folded:
            key = folded[name.lower()]
            return key, node[key]
    if isinstance(node, list) and name.isdigit() and int(name) < len(node):
        return name, node[int(name)]
    return None


def _passes_filter(node, spec):
    """`period=202510, coin=BTC` against one element of a list of records."""
    if not isinstance(node, dict):
        return False
    for part in spec.split(","):
        if "=" not in part:
            return False
        key, _, wanted = part.partition("=")
        if str(node.get(key.strip())) != wanted.strip():
            return False
    return True


def resolve(document, address):
    """[(key path as the artifact spells it, node)] for one address; [] if absent."""
    frontier = [((), document)]
    for raw in split_segments(address):
        segment = raw.strip()
        base, bracket = segment, None
        match = re.match(r"^(.*?)\[(.*)\]$", segment)
        if match:
            base, bracket = match.group(1).strip(), match.group(2).strip()
        alternatives = _expand_braces(base)
        following = []
        for path, node in frontier:
            reached = []
            for alt in alternatives:
                if alt == "*":
                    if isinstance(node, dict):
                        reached += [(path + (str(k),), v) for k, v in node.items()]
                    elif isinstance(node, list):
                        reached += [(path + (str(i),), v)
                                    for i, v in enumerate(node)]
                elif alt == "":
                    reached.append((path, node))
                else:
                    got = _child(node, alt)
                    if got is not None:
                        reached.append((path + (str(got[0]),), got[1]))
            for path2, node2 in reached:
                if bracket is None:
                    following.append((path2, node2))
                elif bracket == "*":
                    if isinstance(node2, list):
                        following += [(path2 + (str(i),), v)
                                      for i, v in enumerate(node2)]
                    elif isinstance(node2, dict):
                        following += [(path2 + (str(k),), v)
                                      for k, v in node2.items()]
                elif bracket.isdigit():
                    if isinstance(node2, list) and int(bracket) < len(node2):
                        following.append((path2 + (bracket,), node2[int(bracket)]))
                elif "=" in bracket:
                    items = (enumerate(node2) if isinstance(node2, list)
                             else node2.items() if isinstance(node2, dict) else ())
                    for key, value in items:
                        if _passes_filter(value, bracket):
                            following.append((path2 + (str(key),), value))
        frontier = following
        if not frontier:
            return []
    return frontier


def module_constants(path):
    """Module-level constants of a producer script, read WITHOUT running it.

    The registry's other kind of address is a name in a script rather than a key in a
    JSON file: the horizon a run was pinned to, the fee ladder, the deploy fraction.
    Those are exactly the figures that go stale silently, so they are worth reaching.
    The file is parsed, never imported: a constant whose value is not a literal is left
    out rather than evaluated.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
    except (OSError, SyntaxError, ValueError):
        return {}
    constants = {}
    for node in tree.body:
        targets = (node.targets if isinstance(node, ast.Assign)
                   else [node.target] if isinstance(node, ast.AnnAssign) else [])
        for target in targets:
            if isinstance(target, ast.Name):
                try:
                    constants[target.id] = ast.literal_eval(node.value)
                except (ValueError, TypeError, SyntaxError, MemoryError,
                        RecursionError):
                    pass
    return constants


# ----------------------------------------------------------------------------------
# LEAVES, TOLERANCE AND AGREEMENT
# ----------------------------------------------------------------------------------

def leaves(node, prefix=()):
    """(key path, scalar) for every scalar under a node."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield from leaves(value, prefix + (str(key),))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from leaves(value, prefix + (str(index),))
    else:
        yield prefix, node


def is_number(value):
    """True is an int in Python and is never a measurement. Booleans are excluded."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def numeric_leaves(node):
    return [(path, value) for path, value in leaves(node) if is_number(value)]


def significant_digits(value):
    """How many significant digits the registry chose to write."""
    text = repr(float(value))
    mantissa = text.split("e")[0] if "e" in text else text
    digits = mantissa.lstrip("-").replace(".", "").lstrip("0")
    if "." in mantissa:
        digits = digits.rstrip("0")
    return max(1, len(digits))


def tolerance(declared):
    """The relative tolerance the register's own precision buys for one figure.

    An integer buys none: a count either matches or it does not, and neither does a
    declared zero, which has no last significant digit to round in. A float buys half a
    unit in the last significant digit it was written to, held between the two declared
    limits above.

    The half-unit is measured where the figure actually sits, not where a mantissa of
    one would sit. Writing the tolerance as 0.5 * 10 ** (1 - digits) reads it off a
    leading digit of 1 and is therefore too loose by the mantissa, up to a factor of
    ten: it gave 0.70142521 a tolerance of 5e-8 when half a unit in its eighth digit is
    7.1e-9, and the self-test below caught it by accepting the next value up.
    """
    if isinstance(declared, int) and not isinstance(declared, bool):
        return 0.0
    value = abs(float(declared))
    if value == 0.0 or not math.isfinite(value):
        return 0.0
    exponent = math.floor(math.log10(value))
    half_unit = 0.5 * 10.0 ** (exponent - significant_digits(declared) + 1)
    return max(MIN_REL_TOL, min(MAX_REL_TOL, half_unit / value))


def agrees(declared, found):
    """(agree?, relative difference, tolerance used) for one figure against one leaf."""
    tol = tolerance(declared)
    a, b = float(declared), float(found)
    if math.isnan(a) or math.isnan(b):
        return (math.isnan(a) and math.isnan(b)), float("nan"), tol
    if a == b:
        return True, 0.0, tol
    scale = max(abs(a), abs(b))
    if scale == 0.0:
        return True, 0.0, tol
    rel = abs(a - b) / scale
    return rel <= tol, rel, tol


# ----------------------------------------------------------------------------------
# THE JOIN
# ----------------------------------------------------------------------------------

def _infix_hits(declared_path, artifact_paths):
    """Artifact paths holding the register sub-name as a contiguous run of segments."""
    wanted = tuple(part.lower() for part in declared_path)
    width = len(wanted)
    if not width:
        return []
    hits = []
    for path in artifact_paths:
        folded = tuple(part.lower() for part in path)
        for start in range(len(folded) - width + 1):
            if folded[start:start + width] == wanted:
                hits.append(path)
                break
    return hits


def _family_substitution(document, addresses, name):
    """Replace one segment of an address by `name`; accept only an unambiguous hit."""
    landed = []
    for address in addresses:
        segments = split_segments(address)
        for position, segment in enumerate(segments):
            if re.search(r"[\[\{\*]", segment):
                continue
            trial = ".".join(segments[:position] + [name]
                             + segments[position + 1:])
            hits = [(path, value) for path, value in resolve(document, trial)
                    if is_number(value)]
            if len(hits) == 1:
                landed.append(hits[0])
    if len(landed) == 1:
        return landed[0]
    if len(landed) > 1 and len({value for _, value in landed}) == 1:
        # Several positions land on the same number, so the substitution is unambiguous
        # about the FIGURE even though it is not about the route. The figure is what is
        # being checked, so this is accepted and the first route is recorded.
        return landed[0]
    return None


def read_source(record):
    """(kind, document, note) for the file a record names. Its path is never kept."""
    stated = record.get("source_file")
    if not isinstance(stated, str) or not stated.strip():
        return None, None, "the record states no source file"
    if ";" in stated or "," in stated:
        return None, None, ("the record states several files, so no single address "
                            "can be walked")
    path = locate(stated)
    if path is None:
        return None, None, "the stated file is not in this checkout"
    if stated.endswith(".json"):
        try:
            with open(path, encoding="utf-8") as fh:
                return "json", json.load(fh), None
        except (OSError, ValueError) as exc:
            return None, None, f"the stated file could not be read as JSON: {exc}"
    if stated.endswith(".py"):
        constants = module_constants(path)
        if not constants:
            return None, None, ("the stated script holds no module-level literal "
                                "constant to read")
        return "python", constants, None
    return None, None, ("the stated file is neither a JSON artifact nor a Python "
                        "producer, so it holds no addressable key")


def join_record(record, kind, document):
    """What one record yields: pairs, the sub-names no rule reached, and the addresses.

    Returns (pairs, unaddressed, addresses, leaves_resolved), where a pair is
    (declared path, declared value, artifact path, artifact value, rule).
    `leaves_resolved` is counted separately from the pairs ON PURPOSE. A record whose
    address resolves to nothing and a record whose address resolves but whose sub-names
    are the register's own vocabulary are two different defects with two different
    repairs, and reporting both as "the address does not exist" would send a reader to
    fix the wrong thing.
    """
    declared = numeric_leaves(record.get("value"))
    if kind == "python":
        addresses = [name for name
                     in _CONSTANT.findall(str(record.get("source_key") or ""))
                     if name in document]
        resolved = []
        for name in addresses:
            for sub, value in leaves(document[name]):
                if is_number(value):
                    resolved.append(((name,) + sub, value))
    else:
        addresses = extract_addresses(record.get("source_key"))
        resolved = []
        for address in addresses:
            for path, node in resolve(document, address):
                for sub, value in leaves(node):
                    if is_number(value):
                        resolved.append((path + sub, value))

    found = {}
    for path, value in resolved:
        found.setdefault(path, value)
    if not found:
        return [], [tuple(p) for p, _ in declared], addresses, 0

    pairs, unaddressed = [], []
    for path, value in declared:
        if len(declared) == 1 and len(found) == 1:
            only_path, only_value = next(iter(found.items()))
            pairs.append((path, value, only_path, only_value, "singleton"))
            continue
        hits = _infix_hits(path, list(found))
        if hits and len({found[h] for h in hits}) == 1:
            pairs.append((path, value, hits[0], found[hits[0]], "path-infix"))
            continue
        if len(path) == 1 and kind == "json":
            landed = _family_substitution(document, addresses, path[0])
            if landed is not None:
                pairs.append((path, value, landed[0], landed[1],
                              "family-substitution"))
                continue
        unaddressed.append(tuple(path))
    return pairs, unaddressed, addresses, len(found)


# ----------------------------------------------------------------------------------
# THE RUN
# ----------------------------------------------------------------------------------

def corrupt(value, factor_for):
    """The registry value with every number moved, for the degeneracy probe."""
    if isinstance(value, dict):
        return {k: corrupt(v, factor_for) for k, v in value.items()}
    if isinstance(value, list):
        return [corrupt(v, factor_for) for v in value]
    if is_number(value):
        moved = float(value) * (1.0 + factor_for(value))
        # A zero cannot be moved by multiplication, so it is replaced by a figure no
        # artifact in this tree holds at that address; leaving it alone would count a
        # value that was never corrupted as one the check failed to catch.
        return moved if value != 0 else 0.1370137
    return value


def sweep(records, value_of):
    """Walk every record once. `value_of` supplies the registry value to compare with.

    One walk serves both the real run and the degeneracy probe, which is deliberate:
    a probe that took a different route through the code would prove nothing about the
    route the run takes.
    """
    pairs, unaddressed, uncompared = [], [], []
    for record in records:
        ident = str(record.get("id", "?"))
        entry = {"id": ident, "source_file": record.get("source_file")}
        kind, document, note = read_source(record)
        if kind is None:
            uncompared.append(dict(entry, reason=note, stage="file not readable"))
            continue
        probe = dict(record)
        probe["value"] = value_of(record)
        found, missed, addresses, n_leaves = join_record(probe, kind, document)
        if not found and not missed:
            uncompared.append(dict(entry, stage="nothing declared",
                                   reason="the record declares no numeric value"))
            continue
        if not found and not n_leaves:
            uncompared.append(dict(
                entry, stage="address unreachable",
                addresses_read=addresses[:4],
                reason=("no address written in source_key resolves to a number inside "
                        "the stated file")))
        elif not found:
            uncompared.append(dict(
                entry, stage="no whole-name join",
                addresses_read=addresses[:4],
                artifact_leaves_reached=n_leaves,
                reason=("the address resolves, but none of the register's sub-names "
                        "equals a name on the artifact's own key path")))
        for path, declared, artifact_path, artifact_value, rule in found:
            ok, rel, tol = agrees(declared, artifact_value)
            pairs.append({
                "id": ident,
                "registry_leaf": ".".join(path) or "(the value itself)",
                "registry_value": declared,
                "source_file": record.get("source_file"),
                "artifact_key_path": ".".join(artifact_path),
                "artifact_value": artifact_value,
                "relative_difference": None if math.isnan(rel) else rel,
                "tolerance": tol,
                "join_rule": rule,
                "agrees": ok,
            })
        for path in missed:
            unaddressed.append({
                "id": ident,
                "register_sub_name": ".".join(path) or "(the value itself)",
                # Whether the record yielded any comparison at all, because an
                # unreached sub-name inside a record that was otherwise compared is a
                # gap in the register's vocabulary, while one inside a record that
                # yielded nothing is already counted as that record stopping.
                "record_also_compared": bool(found),
            })
    return pairs, uncompared, unaddressed


def degeneracy(records, fraction=None):
    """How many corrupted register figures this check accepts. Expectation zero."""
    if fraction is None:
        def factor_for(value):
            return max(DEGENERACY_MIN_FRACTION,
                       DEGENERACY_TOLERANCE_MULTIPLE * tolerance(value))
    else:
        def factor_for(_value):
            return fraction

    def value_of(record):
        return corrupt(record.get("value"), factor_for)

    pairs, _, _ = sweep(records, value_of)
    accepted = [p for p in pairs if p["agrees"]]
    return len(pairs), accepted


def main():
    started = artifact.start_clock()
    verbose = "--verbose" in sys.argv

    print("=" * 76)
    print("  REGISTRY FIGURES AGAINST THEIR OWN ARTIFACTS - chk_prose_numbers")
    print("=" * 76)

    registry_path, named_by = registry_argument()
    if registry_path is not None and not os.path.isfile(registry_path):
        # Named and not there. This is a finding, not a clone: the caller asked for a
        # comparison and the file they pointed at does not exist.
        print(f"  the register named by {named_by} is not a file: "
              f"{os.path.basename(registry_path) or registry_path}")
        print(f"  VERDICT: FAIL - pass {REGISTRY_FLAG} a path to an existing "
              f"{REGISTRY_NAME}, or name none to record that no register was given")
        return 2
    if registry_path is None:
        # No register was named. That is the ordinary state of a clone of this
        # repository, which does not ship the register, and it is a fact about the
        # checkout rather than about the numbers. Declared, not silent: the results
        # file says the comparison did not run and why.
        contract = {"check": CHECK_NAME, "checks": [{
            "name": "registry_present",
            "assumption": (f"a register of quantities ({REGISTRY_NAME}) was named, "
                           "because every figure this gate compares is addressed "
                           "by it"),
            "method": (f"read the path given by {REGISTRY_FLAG} PATH, or by the "
                       f"{REGISTRY_ENV} environment variable; no other location is "
                       "searched"),
            "observed": {"registry_found": False, "registry_named": False,
                         "looked_for": REGISTRY_NAME},
            "verdict": SKIPPED_VERDICT,
            "note": ("the register of quantities belongs to the write-up and is not "
                     "shipped with this repository, so no figure was compared either "
                     f"way. Name one with {REGISTRY_FLAG} PATH to run the comparison"),
        }], "overall_verdict": SKIPPED_VERDICT,
            "skip_reason": "no register of quantities was named"}
        # WRITTEN, NOT LEFT ALONE. The shared writer keeps an earlier answered file in
        # place when a run reaches no verdict, which protects a record the reader can
        # re-derive. A comparison against a register this repository does not ship
        # cannot be re-derived from a clone, so a file left from such a run would stand
        # here as a CONFIRMED nobody can check. The skip is therefore the record.
        artifact.write(
            os.path.basename(OUT_JSON), contract, script=__file__,
            inputs=[],
            scope={"population": "0 registry records: no register was named",
                   "window": "n/a: this gate reads recorded results, not market data",
                   "coins": "n/a: this gate reads recorded results, not market data"},
            started=started)
        # NOT A PASS AND NOT A FAILURE, AND SAID IN ITS OWN WORD. Run through the shared
        # reporter this read as a clean exit over zero comparisons, which is the false
        # zero shape; the battery reads SKIPPED_NO_REGISTRY and counts it apart from the
        # checks that passed.
        print(f"  no register of quantities was named ({REGISTRY_FLAG} PATH or "
              f"{REGISTRY_ENV}); this repository does not ship one, so nothing was "
              f"compared")
        print(f"  VERDICT: {SKIPPED_VERDICT} - 0 figures compared; this is not a pass")
        print(f"  results -> {os.path.basename(OUT_JSON)}")
        return 0

    with open(registry_path, encoding="utf-8") as fh:
        records = json.load(fh)

    pairs, uncompared, unaddressed = sweep(
        records, lambda record: record.get("value"))
    agreeing = [p for p in pairs if p["agrees"]]
    differing = [p for p in pairs if not p["agrees"]]

    n_probe, falsely_accepted = degeneracy(records)
    ladder = {}
    for fraction in RANGE_LADDER:
        total, accepted = degeneracy(records, fraction)
        # Labelled with the relative figure itself rather than as a percentage. Three
        # decimal places of a percentage print 1e-7, 1e-9 and 1e-11 all as "0.000%",
        # and three rungs collapsing into one entry hid the boundary this ladder is
        # for: the run of 2026-07-31 showed six rows for eight rungs.
        ladder[f"{fraction:g}"] = {"corrupted_figures_compared": total,
                                   "still_accepted": len(accepted)}

    from collections import Counter
    by_stage = Counter(entry["stage"] for entry in uncompared)
    by_reason = Counter(entry["reason"] for entry in uncompared)
    join_rules = Counter(p["join_rule"] for p in pairs)
    n_records = len(records)
    n_uncompared = len(uncompared)
    n_compared_records = n_records - n_uncompared
    n_unaddressed_in_compared = sum(1 for u in unaddressed
                                    if u["record_also_compared"])

    # ------------------------------------------------------------------ the screen
    # Population first, then the predicate that took each count, then the count. The
    # four stages below are mutually exclusive and sum to the register, so a reader can
    # add them up and see that nothing was quietly dropped.
    print(f"  register of quantities   : {REGISTRY_NAME}, {n_records} records")
    print()
    print("  predicate for 'compared' : at least one figure of the record joined to "
          "one")
    print("                             artifact leaf by a whole-name rule, never by "
          "value")
    print(f"  records compared         : {n_compared_records} of {n_records}")
    print(f"  records not compared     : {n_uncompared} of {n_records}, by stage")
    for stage, count in by_stage.most_common():
        print(f"      {count:3d}  {stage}")
    for reason, count in by_reason.most_common():
        print(f"           {count:3d}  {reason}")
    if verbose:
        for entry in uncompared:
            print(f"                {entry['id']:5s} {entry['stage']:22s} "
                  f"{entry['source_file']}")
    print()
    print(f"  figures compared         : {len(pairs)}, joined by")
    for rule, count in join_rules.most_common():
        print(f"      {count:3d}  {rule}")
    print(f"  agree                    : {len(agreeing)}")
    print(f"  differ                   : {len(differing)}")
    print(f"  register sub-names no rule reached : {len(unaddressed)}, of which "
          f"{n_unaddressed_in_compared} sit inside a record that was compared")
    print()
    print("  DEGENERACY OF THIS CHECK, measured rather than argued:")
    print(f"      every registry figure moved by "
          f"{DEGENERACY_TOLERANCE_MULTIPLE:.0f} times its own tolerance "
          f"(at least {DEGENERACY_MIN_FRACTION:.0%})")
    print(f"      corrupted figures compared : {n_probe}")
    print(f"      still accepted as agreeing : {len(falsely_accepted)}   "
          f"(expectation 0)")
    for entry in falsely_accepted:
        print(f"          {entry['id']}  {entry['registry_leaf']}  "
              f"{entry['registry_value']} vs {entry['artifact_value']}")
    print()
    print("  RANGE OF THIS CHECK. A corruption below half the last digit the registry")
    print("  printed cannot be seen, and the boundary is a number rather than a claim:")
    for label, row in ladder.items():
        print(f"      moved by {label:>9s} relative : {row['still_accepted']:3d} of "
              f"{row['corrupted_figures_compared']} still accepted")

    # ------------------------------------------------------------- the contract
    def sites(entries, limit=20):
        return entries[:limit]

    contract = {
        "check": CHECK_NAME,
        "checks": [
            {
                "name": "registry_figures_match_their_artifact",
                "assumption": (
                    "every figure the register of quantities states is still the "
                    "figure "
                    "held at the key path the register names, inside the file the "
                    "register names, to the precision the register itself printed"),
                "method": (
                    "for each record, walk the key path written in source_key inside "
                    "source_file and read the leaf; join the register's sub-names to "
                    "artifact leaves by whole-name equality only (singleton, "
                    "path-infix, family-substitution); compare with a relative "
                    "tolerance of half a unit in the last significant digit the "
                    f"register printed, held between {MIN_REL_TOL:g} and "
                    f"{MAX_REL_TOL:g}, and exactly for a count"),
                "observed": {
                    "registry_records": n_records,
                    "figures_compared": len(pairs),
                    "agree": len(agreeing),
                    "differ": len(differing),
                    "join_rules_used": dict(join_rules),
                    "register_sub_names_no_rule_reached": len(unaddressed),
                    "of_those_inside_a_compared_record": n_unaddressed_in_compared,
                    "differences": sites(differing),
                },
                "verdict": "refuted" if differing else "confirmed",
                "note": ("a difference means the artifact was recomputed after the "
                         "figure was recorded, or the figure was mistyped; either way "
                         "the number in the write-up cannot be traced to the file "
                         "beside it"),
            },
            {
                "name": "every_record_reaches_at_least_one_of_its_figures",
                "assumption": (
                    f"at most {UNCOMPARED_RECORD_DEBT} of the {n_records} records "
                    "yield "
                    "no comparison at all. The limit is declared debt, frozen "
                    f"{UNCOMPARED_RECORD_DEBT_SET}: a record pointing at a draft, an "
                    "npz or a sentence cannot be traced by a reader either, and "
                    "closing "
                    "that is the register's work rather than this gate's"),
                "method": ("count the records that produced no pair, at the stage each "
                           "of them stopped: the stated file could not be read, the "
                           "stated key path resolves to nothing inside it, or it "
                           "resolves but no sub-name of the record equals a name on "
                           "the "
                           "artifact's own key path"),
                "observed": {
                    "registry_records": n_records,
                    "records_compared": n_compared_records,
                    "records_uncompared": n_uncompared,
                    "permitted": UNCOMPARED_RECORD_DEBT,
                    "by_stage": dict(by_stage),
                    "by_reason": dict(by_reason),
                    "records": sites(uncompared),
                },
                "verdict": ("refuted" if n_uncompared > UNCOMPARED_RECORD_DEBT
                            else "confirmed"),
                "note": ("a figure whose stated address cannot be walked is quoted on "
                         "trust, because no reader can check it either; the debt only "
                         "ever moves down"),
            },
            {
                "name": "this_check_is_not_degenerate",
                "assumption": (
                    "with every registry figure moved by "
                    f"{DEGENERACY_TOLERANCE_MULTIPLE:.0f} times its own tolerance, at "
                    f"least {DEGENERACY_MIN_FRACTION:.0%}, this check accepts none of "
                    "them. The gate it replaces confirmed 136 of 200 invented values, "
                    "so a stated expectation is not enough and the figure is measured "
                    "on every run"),
                "method": ("corrupt every value in the register, run the same sweep "
                           "over the corrupted copy, and count the corrupted figures "
                           "still called agreeing"),
                "observed": {
                    "corrupted_figures_compared": n_probe,
                    "still_accepted": len(falsely_accepted),
                    "false_acceptance_rate": (len(falsely_accepted) / n_probe
                                              if n_probe else None),
                    "range_ladder": ladder,
                    "accepted": sites(falsely_accepted),
                },
                "verdict": "refuted" if falsely_accepted else "confirmed",
                "note": ("any corrupted figure this check accepts is a figure it could "
                         "not have caught in the register either, so the join rule or "
                         "the tolerance is wrong"),
            },
        ],
    }
    refuted = [c for c in contract["checks"] if c["verdict"] == "refuted"]
    contract["overall_verdict"] = "refuted" if refuted else "confirmed"

    # The full records go into the results file rather than onto the screen: the pairs
    # that agree are the evidence that the gate ran over something, and a reader
    # chasing one figure needs its key path, not a summary.
    contract["all_comparisons"] = pairs
    contract["register_sub_names_no_rule_reached"] = unaddressed
    contract["records_no_figure_compared_from"] = uncompared

    artifact.write(
        os.path.basename(OUT_JSON), contract, script=__file__,
        # The register is named, not pathed: artifact.write records a basename, which
        # is what keeps this file free of the account name it was read under.
        inputs=[registry_path],
        scope={
            "population": (f"{n_records} records of the register of quantities, of "
                           f"which {n_compared_records} yielded at least one "
                           f"comparison; {len(pairs)} figures joined to an artifact "
                           f"leaf by a whole-name rule"),
            "window": ("n/a: this gate reads figures already recorded, so it inherits "
                       "the window of each artifact it opens rather than having one"),
            "coins": ("n/a: this gate compares recorded figures and reads no market "
                      "data"),
        },
        started=started,
        extra_meta={
            "min_relative_tolerance": MIN_REL_TOL,
            "max_relative_tolerance": MAX_REL_TOL,
            "uncompared_record_debt": UNCOMPARED_RECORD_DEBT,
            "uncompared_record_debt_set": UNCOMPARED_RECORD_DEBT_SET,
        })

    print("-" * 76)
    print(f"  VERDICT: {contract['overall_verdict'].upper()}")
    print(f"  results -> {os.path.basename(OUT_JSON)}")
    return report_contract(contract, OUT_JSON,
                           inputs={"registry": REGISTRY_NAME})


# ----------------------------------------------------------------------------------
# SELF-TEST
#
# In the module rather than in a test directory, because this repository has none. The
# corrupted-register probe inside main() measures degeneracy against the register we
# happen to hold; these fixtures pin the PROPERTIES that make the probe come out at
# zero, so a later loosening of a join rule fails here instead of quietly widening what
# the gate accepts.
#
#     uv run --no-project python3 checks/chk_prose_numbers.py --self-test
# ----------------------------------------------------------------------------------

def _self_test():
    # The tally counts as each assertion is made rather than being typed beside them,
    # and it lives in evidence.py, where prose_assemble.py's self-test reads the same
    # one. Binding the method to a plain name keeps every call site below unchanged.
    tally = Tally()
    expect = tally.expect

    def join(value, source_key, document, kind="json"):
        record = {"id": "FIX", "value": value, "source_key": source_key}
        found, missed, _addresses, n_leaves = join_record(record, kind, document)
        return found, missed, n_leaves

    # THE PROPERTY THIS WHOLE FILE EXISTS FOR. The artifact block holds the register's
    # exact figure, but under a name the register does not use, beside another leaf.
    # Nothing may be joined: a rule that reached across to that figure would be finding
    # numbers rather than checking them, which is what the gate of 2026-07-31 did when
    # it confirmed 136 of 200 invented values.
    document = {"block": {"something_else_entirely": 0.4242, "neighbour": 0.9876}}
    found, missed, leaves_seen = join({"nkakoy": 0.4242}, "block", document)
    expect((
        (found == [], "a figure must never be joined to a leaf by its value"),
        (missed == [("nkakoy",)], "the unreached sub-name must be reported"),
        (leaves_seen == 2, "the leaves must still be counted as reached, so the record "
                           "is reported as unjoined rather than as unaddressed")))

    # The same document, with the register using the artifact's own name. Now it joins.
    found, _missed, _n = join({"something_else_entirely": 0.4242}, "block", document)
    expect((
        (len(found) == 1 and found[0][4] == "path-infix",
         "a sub-name equal to a name on the artifact key path must join"),
        (found and found[0][3] == 0.4242, "the joined leaf must be the artifact's"),))

    # WHERE THE REGISTER COMES FROM: two opposite cases and the order between them. A
    # register named by flag or environment must be found; with neither named, nothing
    # may be found, because no location is searched by default.
    expect((
        (registry_argument(["--registry", "r.json"], {}) == ("r.json", "flag"),
         "a register named by --registry PATH must be read from that path"),
        (registry_argument(["--registry=r.json"], {}) == ("r.json", "flag"),
         "the --registry=PATH spelling must be read as well"),
        (registry_argument([], {REGISTRY_ENV: "e.json"}) == ("e.json", "env"),
         f"a register named by {REGISTRY_ENV} must be read when no flag is given"),
        (registry_argument(["--registry", "r.json"], {REGISTRY_ENV: "e.json"})
         == ("r.json", "flag"), "the flag must win over the environment"),
        (registry_argument(["--verbose"], {}) == (None, None),
         "with neither named, no register may be found"),))

    # AN ARTIFACT IS RESOLVED INSIDE THIS REPOSITORY ONLY. A name carrying the leading
    # directories of the tree it was written in resolves by its tail; a name that exists
    # nowhere in this repository resolves to nothing, whatever sits above it.
    expect((
        (locate("some/outer/tree/checks/" + os.path.basename(__file__))
         == os.path.join(HERE, os.path.basename(__file__)),
         "a stated name with foreign leading directories must resolve by its tail"),
        (locate("no_such_dir/no_such_file_anywhere.json") is None,
         "a name absent from this repository must not resolve"),))

    # THE SINGLETON RULE AND ITS LIMIT, stated as a test rather than left implicit. One
    # declared figure against one resolved leaf is paired without consulting the name,
    # because there is nothing else it could mean. The cost is that a record whose
    # sub-name is wrong still passes on the strength of its figure, so the rule is
    # confined to the case where no other reading exists.
    found, _m, _n = join({"whatever_the_register_calls_it": 2480267.0}, "block",
                         {"block": {"total_rows": 2480267.0}})
    expect(((len(found) == 1 and found[0][4] == "singleton",
             "one declared figure against one resolved leaf must pair"),))

    # Case is the only difference forgiven, and only between whole names.
    document = {"per_coin": {"BTC": {"rho": 0.5123456}, "ETH": {"rho": 0.4123456}}}
    found, _m, _n = join({"btc": 0.5123456, "eth": 0.4123456}, "per_coin.{BTC,ETH}.rho",
                         document)
    expect(((len(found) == 2, "btc and BTC are one name written twice"),))

    # A partial name is NOT a name. `rho` must not reach `rho_disatt`. A second leaf is
    # present so the singleton rule cannot pair them regardless of their names.
    found, missed, _n = join(
        {"rho": 0.5123456, "sigma": 0.25}, "per_coin.BTC",
        {"per_coin": {"BTC": {"rho_disatt": 0.5123456, "sigma_other": 0.25}}})
    expect(((not found and set(missed) == {("rho",), ("sigma",)},
             "a sub-name that is a prefix of an artifact name must not join"),))

    # FAMILY SUBSTITUTION MUST REFUSE AN AMBIGUOUS ROUTE. `x` could replace either
    # segment here, and the two routes land on different numbers, so neither is used.
    document = {"a": {"b": 1.0, "x": 7.0}, "x": {"b": 9.0}}
    found, missed, _n = join({"a": 1.0, "x": 3.0}, "a.b", document)
    expect(((("x",) in missed,
             "a substitution that two positions satisfy differently must be refused"),))

    # TOLERANCE. A correctly rounded copy agrees; the same figure one unit off in the
    # last digit the register printed does not.
    expect((
        (agrees(0.1087, 0.10865165286860588)[0],
         "four printed digits must accept the figure they round from"),
        (not agrees(0.1088, 0.10865165286860588)[0],
         "one unit off in the last printed digit must not be accepted"),
        (agrees(0.70142521, 0.7014252142709717)[0],
         "eight printed digits must accept the figure they round from"),
        (not agrees(0.70142523, 0.7014252142709717)[0],
         "eight printed digits must reject a figure two units off in the eighth"),
        (not agrees(2480267, 2480268)[0], "a count must agree exactly"),
        (agrees(2480267, 2480267)[0], "a count that matches must be accepted"),
        (not agrees(0.0, 1e-12)[0],
         "a declared zero has no last digit to round in, so it must match exactly"),
        (tolerance(0.4) == MAX_REL_TOL,
         "a figure printed to one digit must be held at the declared ceiling"),
        (abs(tolerance(0.70142521) - 5e-9 / 0.70142521) < 1e-18,
         "the half-unit must be measured where the figure sits, not at a mantissa "
         "of one")))

    # A module-level constant is read without the script being imported.
    import tempfile
    with tempfile.TemporaryDirectory() as work:
        script = os.path.join(work, "fixture_producer.py")
        with open(script, "w", encoding="utf-8") as fh:
            fh.write("FEES = {'base': 1.5, 't3': 0.4}\n"
                     "SIDE_EFFECT = open('never_written.txt', 'w')\n")
        constants = module_constants(script)
        expect((
            (constants.get("FEES") == {"base": 1.5, "t3": 0.4},
             "a literal constant must be read out of the source"),
            ("SIDE_EFFECT" not in constants,
             "a non-literal must be left out rather than evaluated"),
            (not os.path.exists(os.path.join(work, "never_written.txt")),
             "reading a producer must never run it")))

    print("=" * 76)
    print("  chk_prose_numbers self-test -- the join is by name, never by value")
    print("=" * 76)
    for why in tally.failures:
        print(f"  FAIL  {why}")
    print(f"  {'PASS' if not tally.failures else 'FAIL'}: "
          f"{tally.asserted - len(tally.failures)} of {tally.asserted} assertions hold")
    return 1 if tally.failures else 0


if __name__ == "__main__":
    sys.exit(_self_test() if "--self-test" in sys.argv else main())
