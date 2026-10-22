#!/usr/bin/env python3
"""
WHAT THE SYNTAX TREE CANNOT SAY ABOUT THIS PIPELINE, SAID BY HAND AND CHECKED.

Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-07-31
References: none (repository infrastructure; it declares no quantity of its own).

Why this file exists, and why it is not a list of edges. build.py derives the pipeline
graph from the syntax tree of every script: the argument of np.load is an input, the
first argument of artifact.write is an output. That route is chosen over name matching
because a mention is not an edge -- matching on names once attributed fourteen
producers to one file. The cost of the route is that a path build.py cannot fold to a
constant makes no edge at all, and on 31 July 51 file operations in 24 scripts folded
to nothing. Reading the graph as complete while a fiftieth of its I/O was invisible is
the failure this file exists to prevent.

The 51 were not one problem. Twenty-eight of them were the folder being too weak: a
path handed to a one-line helper, a family held in a dict, a loop variable over a glob.
Those were fixed in build.py where they belong, because an edge that CAN be derived
should never be typed by hand -- a typed edge goes stale silently and a derived one
cannot. What is left here is the residue that no folder can reach, and each entry says
which of these things it is:

    walker      the path comes from a walk of the tracked tree, so the reader's input
                is the repository, not one artifact. chk_no_abs_paths.py opens every
                tracked text file; naming those files as its inputs would put 200 edges
                in the graph and say nothing.
    own_output  the producer reads back a file it writes itself -- the _meta block it
                has just stamped, to recover its own runtime, or a picture of its own
                that it renders under a flag. Recording either as an input would make
                the producer a cycle with itself.
    raw_tape    a raw tape file. Deliberately not an artifact of this graph: the disk
                rule in build.py is that raw days are never cached, so no node may stand
                for one.
    fixture     a self-test writing into a temporary directory the operating system
                hands out. The file never exists in the tree and no other script reads
                it.
    command_line
                the operator names the file when running the script: the document to
                assemble, the copy to write it to, a patch to weigh. The path is not
                unfoldable by accident but by design, because the script is a tool over
                whatever document it is pointed at rather than a producer of one
                artifact. Declared apart from `walker`, which is a walk of the tree.
    internal    working state under a directory git does not keep, reached in a shape
                the folder cannot see through.
    reads       a genuine edge the fold cannot reach. The artifacts are named here.
    open        still unresolved, and the reason it is hard is stated. This class is
                the point of the file: a residue that is listed and counted can only
                shrink deliberately, while a residue that is invisible grows.

WHAT ADDED TEN ENTRIES ON 2026-08-03. build.py folded paths in ONE flat environment per
file, so where two functions bound the same name to two different files, every fold got
whichever value the walk settled on last. Eighteen I/O calls in twelve scripts were
folding to a name from another function: prose_assemble.py read and wrote display.json,
which this repository does not contain, and checks/chk_artifact_provenance.py's census
was recorded as reading NEUTRAL_EDITS.json instead of the tracked files it walks. Each
of those calls counted as accounted for, which is why the residue read 6. Folding per
scope corrected them, and a corrected call has to land somewhere: ten of them are the
entries below, each naming what the call really opens.

WHAT ADDED SEVEN ENTRIES ON 2026-08-04, AND WHO RAISED THE DEBT. Eight calls in five
scripts stood unresolved against a ceiling of 0, and the ceiling had not slipped: four
of the five files entered the tree on 3 and 4 August, so the residue was raised by new
work rather than by anything in the folder going wrong. That is the ordinary way this
number moves, and it is why it is measured on every self-test rather than at the end of
a pass. Seven entries cover the eight because two np.load calls in decile_overlap.py's
main share one key, which is the same shape as the three raw-tape reads below.

None of the eight was fixed by editing the script that holds it. Each of those five
files is already committed, and its producer hash is what its artifact was stamped
with, so a comment added to buy an edge would have made a correct artifact stale and
cost a recompute of a result that had not changed. A declaration costs nothing and says
the same thing.

THE RULE THAT KEEPS THIS FILE HONEST. Every entry is keyed by (script, enclosing
function, call) and build.py's self-test fails if an entry matches nothing in the tree.
A declaration whose call has been deleted or renamed is a statement about code that no
longer exists, and this repository has already been through one round of that: a fact
with several homes and no owner went stale in five files at once. Keying on the
function rather than on the line number is the same care -- line numbers in this tree
move whenever anything above them is edited.

The key is deliberately NOT unique. Three raw-tape reads sit in one function of
killswitch1_repeat_density.py and one entry covers all three, because they are one
statement about one function.
"""

# ---------------------------------------------------------------------------
# 1. SCRIPTS THAT HOLD MORE THAN ONE BUILD NODE
# ---------------------------------------------------------------------------
# A script selected by a command-line arm is not one node. i3_book_comparator.py reads
# book_feats_BTC.npz and also writes it, which the graph reported as a cycle -- and a
# cycle is the one finding a reader is meant to act on, so a false one is expensive.
# What the file actually holds is two stages behind one --stage flag: STAGE 1 streams
# the local level-2 cache and emits the book features, STAGE 2 and 3 read those features
# back and score them. Within one process the write strictly precedes the read. Split
# into the two arms the flag already defines, the write and the read land on different
# nodes and the cycle is gone, which is the honest shape rather than a suppression.
#
# Each arm states its own stage, because they differ: the first walks the raw cache and
# the second does not, and that difference is exactly what the tape/analysis split is
# for.
ARMS = {
    "identity/i3_book_comparator.py": (
        {
            "argv": ("--stage", "feats"),
            "stage": "tape",
            "writes": ("book_feats_*.npz",),
            "reads": (),
            "why": "STAGE 1 alone: stream the local level-2 cache and emit one book "
                   "feature series per coin. It reads no artifact of this graph; its "
                   "input is the raw cache, which is never a node.",
        },
        {
            "argv": ("--stage", "test"),
            "stage": "analysis",
            "writes": ("i3_book_nonrecoverability_results.json",),
            "reads": ("book_feats_*.npz", "notebook_fills.npz",
                      "quickwin_markouts_mid.npz"),
            "why": "STAGE 2 and 3 alone: join the book features to every fill and score "
                   "whether the public book recovers counterparty toxicity. The book "
                   "features must already exist, which is what makes this the reader "
                   "of the arm above rather than a second writer of it.",
        },
    ),
    # The same shape, found the same way: the graph reported panel_persistence.py as a
    # cycle with itself the moment its panel reads were declared. It is not a cycle. Its
    # --build arm parses the coin-month cells into the panel; its --analyze arm reads
    # that panel back and scores wallet persistence across months. Run with neither
    # flag it does both, in that order, which is why the write-then-read inside one
    # process was never a problem and only the graph needed telling.
    "data/panel_persistence.py": (
        {
            "argv": ("--build",),
            "stage": "tape",
            "writes": ("panel_markouts.npz", "panel_taker_map.json"),
            "reads": (),
            "why": "parse the coin-month cells into the cross-month panel. It walks "
                   "the raw tape through the parser it imports, which is why its stage "
                   "is tape even though it names no locator of its own.",
        },
        {
            "argv": ("--analyze",),
            "stage": "analysis",
            "writes": ("panel_persistence_results.json",),
            "reads": ("panel_markouts.npz",),
            "why": "read the panel and score, for each ordered pair of months, whether "
                   "a wallet's toxicity in the first predicts its toxicity in the "
                   "second. Reads only what the arm above wrote.",
        },
    ),
    # A THIRD SHAPE: arms that do not chain. The two above are stages of one
    # computation, the second reading what the first wrote. These two are the same
    # computation run against two different price references, and neither reads the
    # other -- so they are marked parallel, and the mark is not decoration: without it
    # the graph would be free to treat a pair of arms that share nothing as if the
    # second waited on the first.
    #
    # Why it needed declaring at all. --source picks the markout reference, and the
    # fold takes the branch the module constant names, so the syntax tree sees the
    # trade arm alone: one input, one output, and the book-mid half of the question
    # invisible. Measured on 31 July -- i3_nonrecoverability_mid_results.json had no
    # producer anywhere in the graph while sitting in the tree as a tracked artifact.
    # Both arms were run to confirm what each reads and writes rather than read off
    # the source: 15 s and 14 s, and each artifact's own inputs record names its half.
    "identity/i3_nonrecoverability_oos.py": (
        {
            "argv": ("--source", "trade"),
            "stage": "analysis",
            "writes": ("i3_results.json",),
            "reads": ("quickwin_markouts.npz", "quickwin_taker_map.json"),
            "parallel": True,
            "why": "score whether the public book recovers counterparty toxicity when "
                   "toxicity is measured against the TRADE PRINT. This is the arm the "
                   "module constants name, so it is the one the fold already saw.",
        },
        {
            "argv": ("--source", "mid"),
            "stage": "analysis",
            "writes": ("i3_nonrecoverability_mid_results.json",),
            "reads": ("quickwin_markouts_mid.npz", "quickwin_taker_map.json"),
            "parallel": True,
            "why": "the same scoring against the BOOK MID. It reads the other "
                   "intermediate and writes the other results file, and it reads "
                   "nothing the arm above writes, which is what makes the pair "
                   "parallel rather than a chain.",
        },
    ),
}

# ---------------------------------------------------------------------------
# 2. THE ARTIFACT WITH TWO PRODUCERS
# ---------------------------------------------------------------------------
# Left as a declared slot on purpose. The uniqueness rule -- one artifact, one producer
# -- is what the graph enforces, and panel_markouts.npz was written by both
# panel_build.py and panel_persistence.py, which do not write the same file. That
# collision is owned elsewhere and is not decided here; this slot exists so that a
# resolution has a place to be recorded rather than living in two docstrings, which is
# where the warning lived while the wrong file was being overwritten.
#
# The shape an entry takes: "panel_markouts.npz": "panel_persistence.py", meaning that
# script is the declared producer and any other writer of the name is a defect the
# graph should report. Empty means no name currently needs the slot.
CONFLICT_OWNERS = {}

# ---------------------------------------------------------------------------
# 3. THE I/O THE FOLD CANNOT REACH
# ---------------------------------------------------------------------------
# Keyed by (script, enclosing function, call). See the header for the five classes.
DECLARED_IO = {
    # -- the repository itself is the input ---------------------------------
    ("artifact.py", "sha256_file", "open"): {
        "class": "walker",
        "why": "hashes whatever file it is handed. It is the hashing primitive every "
               "provenance record in this repository is built on, so its input is any "
               "file at all and no single artifact.",
    },
    ("artifact.py", "_object_name", "open"): {
        "class": "walker",
        "why": "reads the bytes of whatever producer it is handed, to give them the "
               "name git would give them and ask whether the object database holds it. "
               "Same reason as sha256_file above: the input is any script of this tree "
               "at all, and naming one would be naming the wrong one for every other "
               "producer that calls artifact.write.",
    },
    ("artifact.py", "read_meta", "open"): {
        "class": "walker",
        "why": "reads the _meta block of whatever document it is handed. Same reason: "
               "it is the accessor, not a consumer of one artifact.",
    },
    ("artifact.py", "describe", "open"): {
        "class": "walker",
        "why": "the canonical predicate for provenance, and it takes either a path or "
               "an already-loaded document. checks/chk_artifact_provenance.py runs it "
               "over every tracked .json, so its input is that population and no one "
               "file. Until 2026-08-03 this call folded to an_input.json, which is a "
               "name from this module's own self-test and not a file of this tree.",
    },
    ("checks/chk_artifact_provenance.py", "census", "open"): {
        "class": "walker",
        "why": "the provenance census opens every tracked .json in turn. Its input is "
               "the population of tracked files, which changes when a file is added "
               "rather than when a file is rewritten.",
    },
    ("checks/chk_artifact_provenance.py", "census", "artifact.describe"): {
        "class": "walker",
        "why": "the same census, describing each document it just opened.",
    },
    ("checks/chk_artifact_provenance.py", "main", "artifact.describe"): {
        "class": "walker",
        "why": "describes its own output after writing it, over the same population.",
    },
    ("checks/chk_producer_committed.py", "artifacts", "open"): {
        "class": "walker",
        "why": "opens every tracked .json in turn to read the producer hash it records, "
               "the same population and the same shape as the provenance census above. "
               "Its input is the set of tracked files, which changes when a file is "
               "added and not when a file is rewritten.",
    },
    ("checks/chk_contrast_hygiene.py", "sweep", "open"): {
        "class": "walker",
        "why": "opens whichever artifact each contrast declaration names, one pass per "
               "declaration. The population is the DECLARATIONS table in "
               "checks/contrast_declarations.py, a neighbouring module, so the path is "
               "a value read out of a record and never a constant of this script -- the "
               "same statement as chk_prose_numbers.read_source below. Naming today's "
               "one artifact here would be a typed edge that stops being true the "
               "moment a second contrast is declared, and the whole point of that "
               "table is that contrasts are added to it.",
    },
    ("checks/chk_input_freshness.py", "sweep", "open"): {
        "class": "walker",
        "why": "the freshness sweep opens every artifact of its population in turn and "
               "reads the input records out of its _meta. Its input is that population, "
               "which is a census of tracked files rather than any one artifact, and a "
               "file it cannot read is a result of this gate rather than a failure of "
               "it.",
    },
    ("checks/chk_input_freshness.py", "_self_test_live", "artifact.read_meta"): {
        "class": "walker",
        "why": "the calibration reads the _meta of the anchor artifact it picked, and "
               "WHICH artifact that is, is decided at run time from the records the "
               "sweep just judged rather than by any line here. Declared as a walk for "
               "the same reason as prose_assemble._self_test below and NOT as a read: "
               "an edge taken from a calibration would schedule this gate whenever "
               "whichever file happened to anchor it moved.",
    },
    ("checks/chk_input_freshness.py", "_self_test_live_fifth_step",
     "artifact.read_meta"): {
        "class": "walker",
        "why": "the fifth step of the same live calibration, added 2026-08-05, and the "
               "same call for the same reason as the entry above: it reads the _meta "
               "of an anchor artifact chosen at run time from the records the sweep "
               "just judged. Declared apart rather than folded into that entry because "
               "the key is the enclosing FUNCTION, and two functions reading the same "
               "way are two statements: if this step is renamed or removed, this "
               "declaration matches nothing and stale_declarations() says so, which is "
               "the behaviour a shared entry would lose.",
    },
    ("checks/evidence.py", "notebook_cells", "open"): {
        "class": "walker",
        "why": "opens a tracked notebook to read its cells, for whichever check hands "
               "it a name. Two entries used to stand here, one per check, because the "
               "key is the enclosing FUNCTION and two functions reading the same way "
               "are two statements. They were one function copied twice, so the two "
               "statements were one statement typed twice, and the copies were "
               "consolidated into this module on 2026-08-11. Its callers -- "
               "chk_headline_horizon.py, on the tree carrying one horizon everywhere, "
               "and chk_settings_home.py, on the settings-home rule -- both walk the "
               "tracked notebooks, so the tree is the input either way.",
    },
    ("checks/chk_headline_horizon.py", "iter_sources", "open"): {
        "class": "walker",
        "why": "the other half of the same walk: every tracked .py under the tree, "
               "yielded with its source. The notebooks were declared here and the "
               "sources were not, because this call was folding to .gitignore, a name "
               "bound in the function that reads the ignore patterns.",
    },
    ("checks/chk_no_abs_paths.py", "scan", "open"): {
        "class": "walker",
        "why": "opens every tracked text file looking for an absolute path. Naming its "
               "inputs would name every tracked file in the repository.",
    },
    ("checks/chk_academic_header.py", "scan", "open"): {
        "class": "walker",
        "why": "opens every tracked .py and the notebook to read the opening of each "
               "and check it carries the standard header with author and date. "
               "Naming its inputs would name every script in the "
               "repository, which is the population and not a set of artifacts.",
    },
    ("checks/chk_decision_lookahead.py", "analyse", "open"): {
        "class": "walker",
        "why": "opens every tracked .py to ask whether the module lets the late half of "
               "the window reach a decision taken on the early half. Naming its inputs "
               "would name every script in the repository, which is the population and "
               "not a set of artifacts.",
    },
    ("checks/chk_decision_lookahead.py", "unresolved_split_callers", "open"): {
        "class": "walker",
        "why": "walks the same population a second time to count the modules that reach "
               "the declared cut through a wrapper this gate cannot follow, so that its "
               "own blind spot is printed beside its findings rather than left implied.",
    },
    ("checks/chk_decision_lookahead.py", "_read_text", "open"): {
        "class": "walker",
        "why": "the one reader behind three walks over the same population: the search "
               "for functions that behave like the window cut, the index of artifacts by "
               "the producer each names, and the line lookup behind a provenance finding. "
               "Naming its inputs would name every tracked file in the repository.",
    },
    # ADDED 2026-08-28 with the pinned-version gate, and declared as a CLASS rather than
    # covered by a bigger ceiling. The two are not the same act: naming the class takes
    # these calls out of the residue, so the count returns to what it was, while raising
    # a ceiling would leave them unresolved and merely permit them. The ceiling here may
    # only ever be lowered, and a new tree-walking gate is exactly the case this class
    # was written for.
    ("checks/chk_pinned_versions.py", "artifacts", "open"): {
        "class": "walker",
        "why": "opens every shipped .json that carries a _meta block, to read the "
               "library versions its run recorded and hold them against the pins in "
               "requirements.txt. Naming its inputs would name every results file in "
               "the repository, which is the population this gate measures and not a "
               "set of artifacts it depends on.",
    },
    ("checks/chk_pinned_versions.py", "producer_imports", "open"): {
        "class": "walker",
        "why": "opens the producer of each artifact that recorded no versions at all, "
               "to ask from its syntax whether it imports a pinned distribution. That "
               "is what separates a legitimate silence -- artifact.py builds its version "
               "block from sys.modules, so a producer that loads nothing pinned records "
               "nothing and is right to -- from a record that was lost. Its input is "
               "every script in the repository, reached by basename through the tree.",
    },
    ("checks/chk_settings_home.py", "code_units", "open"): {
        "class": "walker",
        "why": "walks the tracked sources for the same rule.",
    },
    ("checks/chk_settings_home.py", "rule3", "open"): {
        "class": "walker",
        "why": "walks the tracked sources again for the third rule of that check.",
    },
    ("checks/chk_expensive_edits.py", "_sha256", "open"): {
        "class": "walker",
        "why": "hashes whatever file it is handed, the same primitive artifact.py holds "
               "under another name. Its input is any file at all and no one artifact.",
    },
    ("checks/chk_expensive_edits.py", "main", "open"): {
        "class": "walker",
        "why": "two calls in one function, and both take their path from a census "
               "rather than from this file. The first opens every tracked .json in "
               "turn, the list coming from git itself; the second opens the producer "
               "SOURCE that each of those artifacts names in its own _meta, so the file "
               "being read is chosen by the artifact and not by any line here.",
    },
    ("checks/chk_prose_numbers.py", "read_source", "open"): {
        "class": "walker",
        "why": "opens whichever file a register record states as its source. The "
               "population is the register, which is why the path is a value read out "
               "of a record and never a constant of this script.",
    },
    ("checks/chk_prose_numbers.py", "module_constants", "open"): {
        "class": "walker",
        "why": "the register's second kind of address is a name in a producer script "
               "rather than a key in a JSON file, and this parses whichever script the "
               "record names, without importing it. Same population as read_source "
               "above: the register decides the file, so this script names none.",
    },
    ("checks/run_record.py", "judge", "artifact.read_meta"): {
        "class": "walker",
        "why": "the run-happened gate reads the _meta block of each artifact it is "
               "handed, one call for the whole population. Naming its inputs would name "
               "every recorded artifact in the repository and would say nothing about "
               "which one moved.",
    },
    ("checks/run_record.py", "_imports_of", "open"): {
        "class": "walker",
        "why": "parses whatever script it is handed to read that script's import heads, "
               "walking outward from one producer. Its subject is the import graph, so "
               "the population is the tracked sources.",
    },
    ("data/step1_inventory.py", "read_columns", "np.load"): {
        "class": "walker",
        "why": "the inventory runner opens each panel and each mid-price series it "
               "finds, reading only the columns it needs, and reports the ones that "
               "are absent. Its subject is which artifacts exist and how big they are, "
               "so the population is the input and a missing file is a result rather "
               "than a failure.",
    },

    # -- the producer reading back what it just wrote ------------------------
    ("build_diagram.py", "_png_pixels", "open"): {
        "class": "own_output",
        "why": "reads thirteen bytes of a PNG header to recover the picture's own "
               "geometry. The file is pipeline_diagram.png beside this script, which "
               "this script itself renders under --png, so both callers read what this "
               "producer writes: picture_state reports the committed picture's size, "
               "and render_png reads back what it has just rendered. An input edge "
               "would make this producer a cycle with itself. The picture is not a node "
               "of the graph either way, because it is written through mermaid-cli and "
               "no write in this file names it.",
    },
    ("checks/chk_input_freshness.py", "main", "artifact.read_meta"): {
        "class": "own_output",
        "why": "reads back the results file this gate has just written, so that the "
               "gate's own input records are held to the rule it applies to everything "
               "else -- its results file is outside the population it sweeps, so the "
               "rule has to be applied to it here or not at all. Straight read-back of "
               "its own output, and an input edge would schedule this gate forever.",
    },
    ("persistence/ks2_markout_multiday.py", "main", "artifact.read_meta"): {
        "class": "own_output",
        "why": "reads its own results file straight after writing it, to recover the "
               "runtime the writer stamped. An input edge here would make the script a "
               "cycle with itself and would schedule it forever.",
    },
    ("persistence/ks2_persistence_10day.py", "main", "artifact.read_meta"): {
        "class": "own_output",
        "why": "the same pattern: its own runtime, read back out of its own _meta.",
    },
    ("persistence/ks2_persistence_10day.py", "main_mid", "artifact.read_meta"): {
        "class": "own_output",
        "why": "the mid-price entry point of the same script, doing the same thing "
               "with its own results file.",
    },

    # -- raw tape, which is never a node ------------------------------------
    ("data/killswitch1_repeat_density.py", "_iter_trades_from_path", "open"): {
        "class": "raw_tape",
        "why": "opens a raw trade file, plain or compressed, and yields its records. "
               "Three calls in this one function, one per container format. A raw day "
               "is never a node of this graph, because the disk rule is that raw days "
               "are not cached.",
    },
    ("data/i4_l2_mid.py", "decompress", "open"): {
        "class": "raw_tape",
        "why": "the lz4 fallback of the level-2 decoder: when neither the lz4 nor the "
               "unlz4 command is on the machine, the raw hour is opened here and "
               "decoded in process. The path is the hour handed in by the walk, so no "
               "line here names a file, and a raw hour is never a node.",
    },
    ("identity/i3_book_comparator.py", "decompress", "open"): {
        "class": "raw_tape",
        "why": "the same fallback, copied into the book comparator. Until 2026-08-03 "
               "it folded to book_feats_*.npz, which is this script's own OUTPUT, "
               "bound to the same name in another function.",
    },
    ("checks/chk_book_orientation.py", "_decompress", "open"): {
        "class": "raw_tape",
        "why": "the same fallback again, in the check that reads the book the other "
               "way round. Its docstring says it mirrors i4_l2_mid.decompress, and it "
               "was folding to mid_series_*.npz for the same reason.",
    },

    # -- a self-test fixture -------------------------------------------------
    ("artifact.py", "_self_test", "open"): {
        "class": "fixture",
        "why": "the artifact module's own self-test, writing into a temporary "
               "directory the operating system hands out and deleting it again. The "
               "file never exists in the tree.",
    },
    ("checks/chk_artifact_provenance.py", "judge", "artifact.describe"): {
        "class": "fixture",
        "why": "the freshness calibration describes a document it has just built in "
               "memory, whose producer is a fixture script written into a temporary "
               "work directory. Nothing here is a file of the tree: the point of the "
               "fixture is that the recorded hash can be moved by one digit and the "
               "same real freshness() asked about both. Distinct from the census and "
               "main entries above, which describe tracked artifacts.",
    },
    ("checks/chk_run_happened.py", "_self_test", "open"): {
        "class": "fixture",
        "why": "the run-happened gate's own self-test, reading back a fixture artifact "
               "it wrote into a temporary directory and rewriting it without a finish "
               "time, to check that a silent artifact reads as unanswerable rather "
               "than as a pass. Two calls, one temporary file, never in the tree.",
    },
    ("checks/chk_run_happened.py", "_self_test_cut", "open"): {
        "class": "fixture",
        "why": "the same gate's calibration of its producer-hash leg, added 2026-08-04. "
               "It copies one real artifact of this tree into a temporary directory "
               "twice, once as it stands and once with a single hex digit of the "
               "recorded hash changed, and judges both. The pair is CUT FROM the tree "
               "rather than anchored on whatever divergence the tree happens to hold, "
               "because the version that was so anchored emptied itself the day those "
               "divergences turned out to carry certificates. Nothing it writes lives "
               "outside the temporary directory.",
    },
    ("checks/chk_artifact_provenance.py", "_self_test_judge_producerless",
     "artifact.describe"): {
        "class": "fixture",
        "why": "the provenance census calibrating the branch that reads a declared "
               "record_kind BEFORE it looks for a producer, added 2026-08-04 with the "
               "hand_register kind. The document it describes is built in memory and "
               "never opened from disk; it exists so that a file with no producer and a "
               "declared kind can be told from one with no producer and no kind.",
    },
    ("prose_assemble.py", "_self_test", "open"): {
        "class": "walker",
        "why": "the self-test reads its expected figure out of the artifact directly, "
               "so that the assertion stands against the artifact rather than against "
               "the machinery under test. WHICH artifact is decided by the register: "
               "the path is gate.locate() of the source_file that record D01 states. "
               "Declared as a walk of the register for the same reason as "
               "chk_prose_numbers.read_source, and NOT as a read, because an edge "
               "taken from a self-test would schedule this script whenever that "
               "artifact moved.",
    },

    # -- the operator names the file ----------------------------------------
    ("prose_assemble.py", "main", "open"): {
        "class": "command_line",
        "why": "four calls in one function, and all four take their path from the "
               "command line: the document to assemble, the marked-up copy under -o, "
               "the display patch under --declare, and the assembled document itself. "
               "This script is a tool over whatever document it is pointed at, so it "
               "produces no fixed artifact and consumes none. What it DOES write "
               "under a name of its own is the provenance sidecar beside its output, "
               "and that edge is derived rather than declared.",
    },
    ("prose_assemble.py", "load_overlay", "open"): {
        "class": "command_line",
        "why": "the display declarations named by --display, read while a patch is "
               "being weighed before it is moved into the register. Named on the "
               "command line, so no line of this file names it. Until 2026-08-03 this "
               "call folded to display.json, a fixture the self-test writes into a "
               "temporary directory and hands to this function -- which put a file "
               "the repository does not contain into the graph as a real input.",
    },
    ("notebook_build/embed_notebook_expectations.py", "read_notebook", "open"): {
        "class": "command_line",
        "why": "the notebook named by --notebook, whose default is the reproduction "
               "notebook and whose value may be any copy of it. Declared the same way "
               "as prose_assemble above and for the same reason: this is a tool over "
               "whatever document it is pointed at. Its own self-checks and the gate "
               "that guards it both run it over copies in a temporary directory, so a "
               "typed edge here would name one of several documents it legitimately "
               "opens.",
    },
    ("notebook_build/embed_notebook_expectations.py", "write_notebook", "open"): {
        "class": "command_line",
        "why": "the same document, written back after the generated cell is replaced. "
               "The notebook is not an artifact of this graph and has no _meta block "
               "to carry provenance, so declaring a write edge here would add a "
               "producer for a file the graph does not otherwise know. What keeps the "
               "cell honest is checks/chk_notebook_expectations.py, which compares it "
               "leaf by leaf against the file of figures rather than by a hash.",
    },
    ("notebook_build/embed_notebook_expectations.py", "sha256_file", "open"): {
        "class": "walker",
        "why": "hashes whatever file it is handed, so that a second run can state that "
               "it left the notebook byte-identical. Same statement as the hashing "
               "primitive in artifact.py: its input is any file at all and no one "
               "artifact.",
    },

    # -- and one of its calls IS an edge -------------------------------------
    ("notebook_build/embed_notebook_expectations.py", "main", "open"): {
        "class": "reads",
        "reads": ("notebook_expected.json",),
        "why": "the figures themselves, at the path --expected names and defaults to. "
               "This one is a real edge and is declared as one: when the file of "
               "figures is rewritten, the cell inside the notebook is behind it until "
               "this script runs again, which is exactly the staleness that put a copy "
               "deposited on 10 July in front of a reader on 6 August. The path cannot "
               "fold because it arrives through argparse, but WHICH file it is, is not "
               "in doubt.",
    },

    # -- a genuine edge the fold cannot reach --------------------------------
    ("prose_assemble.py", "load_register", "open"): {
        "class": "reads",
        "reads": ("registry.json",),
        "why": "the register of quantities, at the address a search of the enclosing "
               "directories returns. Same statement as the chk_prose_numbers entry "
               "below: WHICH file it is, this script states as a module constant; "
               "WHERE it is, is not knowable from the source, because the register "
               "lives beside this repository and a bare clone does not carry it.",
    },
    ("data/build_toxicity_frame.py", "build", "np.load"): {
        "class": "reads",
        "reads": ("quickwin_markouts_mid.npz",),
        "why": "the mid-lens panel, reached as P.panel_path('mid'). panel_io.py's "
               "header states the convention that keeps such an edge derived -- the "
               "caller holds the path in a module-level constant and writes "
               "np.load(NPZ_PATH) -- and this is the one caller in the tree that "
               "calls the locator inline instead, so the fold, which does not follow "
               "a call into another module, reaches nothing. The artifact this script "
               "writes records the same file as its input, by name and by hash.",
    },
    ("probes/decile_overlap.py", "main", "np.load"): {
        "class": "reads",
        "reads": ("quickwin_markouts_mid.npz", "quickwin_markouts.npz"),
        "why": "both panels, and two calls in this one function. Each name is a module "
               "constant of this script, but neither reaches its np.load: the path "
               "goes out through P.require_present, which returns it, and the fold "
               "does not follow a call into another module. So the file the call site "
               "holds is the RETURN of a locator and nothing here names it, while the "
               "names themselves are real inputs -- this script compares the two "
               "lenses wallet by wallet and cannot run on one.",
    },
    ("quoters/t1_toxicity_skew_backtest.py", "main", "np.load"): {
        "class": "reads",
        "reads": ("quickwin_markouts_mid.npz",),
        "why": "the mid-lens panel, held in the module constant MID_NPZ_PATH, which is "
               "assigned P.panel_path('mid'). The constant carries no file name at all: "
               "the locator maps the lens to the basename in panel_io.py, so there is "
               "nothing in this file for the fold to reach. The print-lens load beside "
               "it does fold, because that constant is built from a literal basename, "
               "and the difference between the two lines is the whole reason this entry "
               "exists. Same shape as build_toxicity_frame.build above, which calls the "
               "locator inline instead of binding it.",
    },
    ("data/check_first.py", "check_schema_and_days", "np.load"): {
        "class": "reads",
        "reads": ("quickwin_markouts.npz", "quickwin_markouts_mid.npz"),
        "why": "loops over the two markout intermediates by name and loads each. The "
               "loop variable holds a different constant on each pass, so the call "
               "site names no one file, and both are real inputs.",
    },
    ("checks/chk_prose_numbers.py", "main", "open"): {
        "class": "reads",
        "reads": ("registry.json",),
        "why": "the register of quantities, opened at the address a search of the "
               "enclosing directories returns. WHICH file it is, is stated in this "
               "script as a module constant; WHERE it is, is not knowable from the "
               "source, because the register lives beside this repository rather than "
               "in it and a bare clone does not carry it at all. So the name is a real "
               "edge and the path is not foldable, which is precisely this class.",
    },
    ("persistence/panel_extended.py", "_load", "np.load"): {
        "class": "reads",
        "reads": ("panel_markouts.npz",),
        "why": "the loader this script substitutes into panel_persistence, so that the "
               "window and the markout column can be chosen from the command line. It "
               "is never called here -- it is handed to the other module, which calls "
               "it with the panel path -- so no call site in this file can name the "
               "file it reads.",
    },
    ("data/panel_persistence.py", "_load_panel", "np.load"): {
        "class": "reads",
        "reads": ("panel_markouts.npz",),
        "why": "the panel loader. It takes the path as a parameter because "
               "panel_extended.py replaces this function wholesale, and a function "
               "that can be replaced cannot hold its own file name.",
    },
    ("data/panel_persistence.py", "identify_builder", "np.load"): {
        "class": "reads",
        "reads": ("panel_markouts.npz",),
        "why": "opens the panel already on disk and decides which builder wrote it, "
               "from the columns rather than from the file name. Reading the name "
               "would be the assumption that made the two-producer collision "
               "invisible in the first place.",
    },
    ("notebook_build/make_notebook_fills.py", "main", "np.load"): {
        "class": "internal",
        "why": "reads the per-cell shards under the checkpoint directory to recover "
               "the native block timestamps. Those shards are working state git does "
               "not keep, so they are internal to the node that wrote them; the pair "
               "is declared here because the loop unpacks them out of a dict and the "
               "fold reaches the values but not the pair.",
    },
}


def io_key(script, scope, call):
    """The key an unresolved I/O call is looked up by."""
    return (script, scope or "", call)


def classify(script, scope, call):
    """The declaration for one unresolved call, or None if none was made."""
    return DECLARED_IO.get(io_key(script, scope, call))


def declared_edges(script, scope, call):
    """The artifacts a declaration names, as (reads, writes)."""
    record = classify(script, scope, call) or {}
    return tuple(record.get("reads", ())), tuple(record.get("writes", ()))


def counts():
    """How many declarations of each class this file holds."""
    tally = {}
    for record in DECLARED_IO.values():
        tally[record["class"]] = tally.get(record["class"], 0) + 1
    tally["arms"] = sum(len(v) for v in ARMS.values())
    return tally
