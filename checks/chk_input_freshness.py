#!/usr/bin/env python3
"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-08-03
References: none (repository gate; it declares no quantity of its own and reads the
input record artifact.py writes into every results file).

DID THE INPUT MOVE. THE OTHER TWO GATES ONLY EVER ASK WHETHER THE CODE MOVED.

Why this gate exists, and it is a measurement rather than a principle. On 2 August
twelve artifacts of this tree were found standing on a column that no longer existed on
disk, and not one gate had said a word about any of them. The mechanism is in the
question the existing gates put. chk_artifact_provenance.py compares an artifact
against the hash of its PRODUCER, and chk_run_happened.py compares the same hash plus a
finish time. Both therefore ask "has the code changed". Nobody asks "has the input
changed". Of the 81 nodes in the build graph 65 are pure readers of another node's
output, so the whole lower layer of the graph is invisible to both gates by
construction, and no amount of care with either would have caught it.

The worst form of it had already happened the same day: eight records of the register
of figures read as agreement between two numbers, because BOTH sides were stale. Two
copies of one out-of-date number agree perfectly, and agreement measured that way
certifies nothing at all. That is the direction of measuring error that passes straight
through a review, which is why the question needs a gate rather than a habit.

WHAT IS COMPARED. artifact.write() already records, for every input a producer
declared, its name, its size, its sha256 and whether it was present at write time. That
record is the producer's own statement of what the numbers were computed from. This
gate re-resolves each name, hashes the file that is there now, and compares. Nothing is
recomputed and no producer is launched: the comparison is between what an artifact SAYS
it read and what is on disk today.

SEVEN OUTCOMES PER INPUT, AND THEY ARE KEPT APART BECAUSE FOUR OF THEM ARE NOT DEBT.

  matches            a hash was recorded, the file is on disk, and they are equal
  rewritten          the recorded hash and the file on disk differ as BYTES, both sides
                     carry a _meta block, the recorded byte-state was found in this
                     repository's history, and the two documents are identical once
                     _meta is taken off: the file was rewritten and the numbers were
                     not. See the section below, which is the whole reason it is a
                     state of its own rather than a footnote on a divergence
  diverged           the bytes differ and the numbers differ with them. An input that
                     carries no _meta at all lands here too, and correctly: for a
                     producer script or a raw array the whole file IS its content, so
                     "did the bytes move" and "did the content move" are one question
  diverged_unknown   the bytes differ, the input carries _meta, and the recorded
                     byte-state is in no object of this repository's history, so
                     whether the numbers moved CANNOT BE ANSWERED here. It is counted
                     with diverged and never with matches: an unanswerable question is
                     not a question that came back clean
  absent_from_disk   a hash was recorded, so the file existed when the artifact was
                     written, and it is not there now. The comparison cannot be made
                     at all, which is worse than a divergence rather than better
  no_hash_recorded   a local name carrying no hash. The input was already gone when
                     the artifact was written, because the raw-tape parsers delete
                     each day's hourly directory as soon as they have parsed it
  remote_address     the name is an address rather than a file: an archive bucket key
                     or a URL. Nothing local was ever expected here, so this is the
                     design of the tape parsers and not staleness of anything

Folding these into one another is the whole trap. Counting remote addresses as missing
inputs would report the tape parsers as broken every single run, and a gate that is red
for a reason nobody can act on stops being read. Counting them as clean would report an
unverifiable input as verified, which is the direction that does damage.

A REWRITE IS NOT A DIVERGENCE, AND UNTIL 2026-08-11 THIS GATE COULD NOT TELL THEM APART.
The hash it compared was of the WHOLE FILE, _meta and all, and _meta carries the clock
of the run and the hash of the producer. So recomputing a node moved the hash of its
output whether or not a single published figure moved with it, and every consumer of
that node was reported as standing on an input that no longer exists. Measured that day
on the recompute of six nodes: 16 diverged edges over 6 artifacts, of which 11 stood on
results files whose numbers had not moved by a single digit -- ws1_horizon_results.json
1498 leaves, t3_results.json 327, as_quoter_results.json 184, m2_figure_results.json 40,
ws2_hard_classifier_results.json 29, toxicity_frame_results.json 4, and zero moved in
every one of them. A gate that goes red on work that changed nothing is a gate somebody
learns to run and ignore, and that is the same ending as a gate that is silent.

WHAT IS COMPARED INSTEAD, AND BOTH SIGNS ARE KEPT. The recorded whole-file hash stays
exactly where it was and means exactly what it meant: it is the only thing the producers
write and the only thing older artifacts carry. Beside it this gate now derives a second
sign, the hash of the same document with the _meta block taken off, for the recorded
byte-state and for the file on disk. Replacing the first with the second would have left
every record written before today meaning something different under an unchanged name,
which is the defect this project calls "the name stayed and the quantity under it
changed".

HOW THE RECORDED BODY IS RECOVERED, AND WHY BY CONTENT RATHER THAN BY PATH. The input
record keeps a hash and not the bytes, so the document that hash stands for has to be
found again. Every artifact of this tree is committed, so the byte-state is an object of
this repository's history, and it is looked up there by CONTENT: every blob whose
historical basename matches the input's is hashed, and the one equal to the record is
the document the producer read. Looking it up by PATH was tried first and measured at 0
of 16, because the restructuring of 2026-08-10 moved these files and `git log` of the
name they carry today returns nothing at all. The same lookup by content found 11 of 11.
That is the rule this project already applies to a missing input and to a duplicate
basename, and it holds a third time: a hash identifies a document, a path is a guess
about where it sits.

WHAT A REWRITE IS ALLOWED TO MOVE, AND IT IS AN ALLOW-LIST ON PURPOSE. Identical numbers
under a changed SETTING are not the same answer, they are a different question with the
same digits, so a rewrite is silent only when the fields of _meta that moved all sit in
REWRITE_MAY_MOVE below. Anything else -- the settings fingerprint, the scope, a field
nobody has thought of yet -- makes the edge diverged and names the field. An allow-list
fails towards the alarm; a deny-list would let a record shape added next year through
because nobody remembered to add it. Measured on all 11 rewrites of 2026-08-11: the
fields that moved were the producer, the run clock and the input list, and neither the
settings fingerprint nor the scope moved in a single one of them.

WHAT THIS DOES NOT DO. It does not make a rewritten input match. The state is its own,
it is printed on its own line, and the artifact standing on one is named, because a
consumer that was never re-run against the file now on disk has still not been re-run.
What it does is stop that fact from being reported in the same words as a figure
standing on numbers that no longer exist.

THE POPULATION, AND THE TWO AMENDMENTS THIS GATE MAKES TO THE SHARED ONE. The
population is chk_artifact_provenance.population(), which is the .gitignore predicate
asked of every .json in the tree. It is called rather than copied: two implementations
of one predicate is how four honest censuses of these artifacts returned 20, 24, 32 and
38 for a single property. Two amendments are made to what it returns, and both are
printed on every run so that neither is a silent difference between two counts.

  ONE. That function removes chk_artifact_provenance's OWN results file, for a reason
  that belongs to that gate alone: it would otherwise score itself. For this gate that
  file is an ordinary artifact with eighty-two recorded inputs, so it is put back. It
  is not a small correction. Leaving the exclusion in place reports six artifacts on a
  diverged input where the number is seven, and the missing one is a gate.

  TWO. This gate's own results file is removed instead, for the reason the neighbour
  removes its own: reading this run's own previous output would make the answer depend
  on the previous run rather than on the tree. It is held to the rule by re-resolving
  the inputs of the file this run has just written, which is the SELF-CONFORMANCE leg
  at the end of main(), so nothing here is exempt from what it enforces.

HOW A NAME IS RESOLVED, IN FIVE STEPS, AND WHY IT TAKES FIVE.
artifact.input_record() resolves a relative name against the producer's own directory
and then against the WORKING DIRECTORY, and records the input under its BASENAME alone,
because a directory names the machine and neither reproduces nor belongs in a published
artifact. The record is therefore narrower than the thing the producer resolved, and
re-resolving it needs to make up the difference in five steps.

  the producer's own directory      what input_record() tries first
  the tree root                     the working directory every producer here is
                                    launched from, which is what input_record() reaches
                                    through its second candidate. Not decoration:
                                    re-resolving without it reports thirty-two inputs
                                    as absent while they sit on disk, and hides a real
                                    divergence in chk_side_signconv_results.json behind
                                    a false "the file is gone"
  the only file of that name        a producer that declared probes/decay_curve.json
                                    had the directory taken off it by the record, so
                                    neither place above finds it. It places 20 of the
                                    312 records, and 19 of those are comparisons the
                                    two-step resolver could not make at all: the count
                                    of absent inputs falls from 52 to 33, and every one
                                    of the 19 comes out matching

The third step refuses to guess. A basename the tree holds more than once resolves to
NOTHING rather than to whichever copy the walk met first -- the 24 shard_*.npz live in
both panel checkpoint directories -- which is the rule chk_artifact_provenance already
applies to producer names, for the same reason: guessing there would compare an
artifact against a file it never read. That refusal is what makes the third step safe,
and every name it leaves unresolved is reported with the candidates that made it
ambiguous.

  the one candidate whose        THE FOURTH STEP, and it is what lets the refusal above
  contents equal the hash        be narrow. The record drops the directory but it keeps
                                 a sha256, and a hash identifies a file where a
                                 basename cannot. Hashing each candidate and keeping
                                 the one that equals the recorded digest chooses by
                                 CONTENT, so it can never select a file the artifact
                                 never read; when none matches, nothing is chosen and
                                 the ambiguity stands. It took the absent count from 61
                                 to 11 in one run

  the declared roots outside     THE FIFTH STEP, added 2026-08-05, and it exists
  the tree                       because the four above all look INSIDE the tree while
                                 some inputs have never lived there

THE FIFTH STEP, AND THE COUNT THAT MADE IT NECESSARY. Eleven inputs read absent from
disk on 2026-08-05, and every one of the eleven was on disk: resolving them by CONTENT
rather than by the paths this gate had searched found all eleven, hash-exact, 11 of 11,
over a walk of 9 425 files. They sit beside the tree rather than in it, in the data
directory and among the written documents, and no amount of searching within the
tree could ever have found them. The count was measuring this gate's own lookup and not
the repository, which is the same defect measured a day earlier when a sibling
instrument reported 33 absent inputs of which 33 were present. Before naming a thing
missing, resolve it by content: a hash identifies a file, a path is a guess about where
it is.

AND TEN OF THE ELEVEN WERE THE HARMLESS DIRECTION. The eleventh was not, and it is the
reason this repair mattered rather than tidied. chk_prose_numbers_results.json recorded
reading registry.json at 8b065cee2256; the register on disk is a different file now.
That edge had been reading absent_from_disk, which says the comparison CANNOT BE MADE,
and behind it sat a divergence that says the comparison was made and failed. A gate
cannot see past a false absence, so for as long as the eleven read absent this one was
invisible: an artifact publishing figures off a version of the register that no longer
exists, with nothing red anywhere. That is the direction of measuring error that goes
straight through a review, and it is what an unexamined "the file is simply gone" costs.

Two conditions make the step safe, and both are load-bearing.

  A ROOT IS RELATIVE AND OPTIONAL. The roots are written as paths relative to the tree
  root, never absolute, because an absolute path names this machine and this repository
  has to run on somebody else's. A root that is not on disk is not searched, and the
  inputs that would have lived under it read absent_from_disk with the missing root
  NAMED in the reason. That is the case of a person who cloned this tree alone, which
  is how it is meant to be cloned, and they are owed the honest answer rather than a
  count that quietly went to zero. The armed rule stands down in that state and says so,
  because the measurement cannot be made there rather than having been made and passed.

  A CANDIDATE IS CHOSEN BY CONTENT, exactly as in the fourth step. Two files of one name
  under a declared root resolve to the one whose digest equals the record, and to
  nothing at all when neither does. A walk-order rule would compare an artifact against
  a file it never read, and the calibration below builds precisely that trap: two copies
  where the matching one sorts second.

Every one of these directories is named here explicitly rather than inherited from
wherever this gate happens to be launched from, which is the same lesson one level
down: an answer that moves with the working directory is not an answer about it. The
hashing itself is artifact.sha256_file, and the agreement between this resolution and
artifact.input_record is asserted on live files in the calibration below, so the shared
function is called rather than reimplemented in the part that decides.

WHY THE NARROW RESOLVER HAD TO GO, rather than be left as a caveat. An input that reads
"absent" cannot be compared, so a divergence underneath it is invisible. That is not
the harmless direction: it is a measurement that reports success -- nothing to see --
where there may be a stale figure, and it is the same shape as the defect this whole
gate was written for. The first run of this gate found 17 such names in its OWN results
file through the self-conformance leg below, which is where the third step came from.

THE DEBT IS A NAMED LIST AND NOT A COUNT, AND THAT WAS MEASURED RATHER THAN CHOSEN.
Four runs of this gate over one tree on which nothing had been recomputed, on
2026-08-03, gave 30, 33, 36 and 28 diverged edges, over 7 artifacts and then 6. Both
counts move on a green run, because a results file is two things at once: an artifact
with declared inputs, and a file the battery rewrites.

  Running the battery REFRESHED run_all_checks_results.json, whose declared inputs are
  the check scripts, and its five edges vanished; editing any check script brings them
  straight back. chk_artifact_provenance_results.json declares all 83 tracked files,
  because reading them is what it does, so everything that runs afterwards adds an edge
  to it: 1 when this gate runs alone, 4 inside the battery, 11 once a few checks had
  been run by hand.

A ceiling on either count would have to sit at the worst case, and a ceiling of 7
artifacts passes a genuine seventh on any run where run_all_checks_results.json happens
to be fresh -- slack in the one direction that does damage. So the frozen debt is a set
of names. An artifact outside it fails the run and is named; one inside it that has
been recomputed drops out and is reported so the list can be shortened. The edge count
is printed as a lower bound and never gated, which is the treatment, and the stated
reason, that chk_artifact_provenance already gives its file-date proxy.

AND A LIST OF NAMES HAS A FAILURE A COUNT DOES NOT: A NAME CAN STOP POINTING AT
ANYTHING, AND IT THEN READS AS FINISHED WORK. An entry drops out of the set of artifacts
found standing on a moved input for two reasons that look identical from here -- the
artifact was recomputed, or the artifact is not in the population any more -- and until
2026-08-12 both came out in one list under the word "repaid", printed with the words
"shorten the list in this file" beside it. Measured that day: two of the six entries
named addresses the restructuring had emptied -- commit 9d52367 of 2026-08-11, which
moved 112 files -- i3_nonrecoverability_mid having gone into identity/ and
sensitivity_rollup into money/, and both had been
printed as repaid on every run for a day with nothing red anywhere. That is the
direction of measuring error this whole file was written about, arriving through the
gate's own bookkeeping rather than through the tree.

So the entries are resolved against the population as a rule of their own, armed at
zero, and resolved BY CONTENT before by path: an entry whose basename an artifact
carries at another address is reported MOVED with that address, because the repair there
is to re-point the line and striking it would drop a live divergence out of the declared
list; only an entry no artifact answers to at all is reported gone. Zero here is a floor
and not a frozen debt, because there is no state of this tree in which a line pointing
at nothing is correct. The three cases that calibrate it are built from the POPULATION
and never from the declared list, for the reason the retired pair below records: the
declared list is meant to be shortened until it is empty, and a case standing on it
would go vacuous on the day the work is finished.

HOW THIS GATE IS CALIBRATED, AND WHY BOTH CASES ARE BUILT RATHER THAN NAMED. A
comparator needs two opposite cases, one it must fire on and one it must stay silent
on, because a single reference point cannot tell a predicate that is too wide from one
that is too narrow. Both are constructed here on every run. The silent case is a real
input record lifted out of this run's own sweep -- live data, chosen by a rule and
never written out as a name. The firing case is that same record with one hex digit of
its recorded sha256 changed and nothing else touched, so both halves resolve the same
name by the same step, hash the same file on disk, and differ in exactly the one
quantity this gate judges. That last sentence is measured field by field rather than
believed.

The construction is a repair and not a preference. The calibration first written on
2026-08-03 NAMED two artifacts: notebooks/notebook_expected.json, which then stood on
maker_econ_results.json at a hash the file no longer carried, and
mm_bakeoff_results.json, whose three inputs all matched. The firing case went vacuous
inside a day. The notebook was recomputed, the divergence was repaid -- somebody
doing the work this gate exists to prompt -- and the leg that was supposed to prove
this gate can find anything reported NOT ANSWERED with 0 diverged inputs of 9. What
remained was a green gate with no demonstration left that it fires at all, which is
the direction of measuring error that passes straight through a review. This project
has already lost two instruments to that mechanism in a single day. The pair below
cannot empty the same way: it stands on the sweep rather than on a defect, and the one
condition that would stop it running -- a tree holding no verifiable input record
whatever -- fails the run rather than falling silent.

    uv run --no-project --with-requirements requirements.txt python3 \\
        checks/chk_input_freshness.py
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import artifact                                                        # noqa: E402
import chk_artifact_provenance as _prov                                # noqa: E402
import panel_io                                                        # noqa: E402
from evidence import make_expect, report_gate                          # noqa: E402

OUT_NAME = "chk_input_freshness_results.json"
OUT_JSON = os.path.join(HERE, OUT_NAME)
SELF_OUTPUT = os.path.relpath(OUT_JSON, ROOT).replace(os.sep, "/")

# The seven outcomes. Named as constants because the tally, the gate and the calibration
# all speak about the same seven, and a state spelled twice is a state that can drift.
MATCHES = "matches"
REWRITTEN = "rewritten_same_numbers"
DIVERGED = "diverged"
UNKNOWN = "diverged_body_unknown"
ABSENT = "absent_from_disk"
NO_HASH = "no_hash_recorded"
REMOTE = "remote_address"
# A script read as an input whose bytes moved by comments and docstrings alone, with a
# live certificate saying so in checks/NEUTRAL_EDITS.json. Kept apart from MATCHES: a
# reader must see how much of a clean tree rests on a proof rather than on a run.
NEUTRAL_INPUT = "moved_neutrally_certified"
STATES = (MATCHES, REWRITTEN, NEUTRAL_INPUT, DIVERGED, UNKNOWN, ABSENT, NO_HASH,
          REMOTE)

# The states that leave an artifact standing on an input it was not computed from. Named
# once, here, because three places ask the question -- the artifact-level rule, the tally
# and the self-conformance leg -- and a set spelled three times is a set that can drift.
# UNKNOWN belongs here and that is the whole of requirement three: a byte-state this
# repository cannot produce leaves the comparison unmade, and an unmade comparison is
# never a pass.
NOT_STANDING_ON_WHAT_IT_READ = (DIVERGED, UNKNOWN)

# WHAT A REWRITE IS ALLOWED TO HAVE MOVED IN _meta, AS AN ALLOW-LIST.
#
# The body being identical says the numbers did not move. It does not say the numbers
# still answer the same question: a figure recomputed on a different SETTING or over a
# different SCOPE can come out to the same digits and mean something else, which is the
# defect this project has already met twice under the name "the name stayed and the
# quantity under it changed". So the two records that say what a number MEANS are not on
# this list, and an edge whose settings fingerprint or scope moved reads diverged with
# the field named.
#
# It is an allow-list rather than a deny-list because the two fail in opposite
# directions. A deny-list passes every _meta field added after it was written, silently;
# an allow-list stops on one and makes somebody say which kind it is. Measured over the
# 11 rewrites of 2026-08-11: the fields that moved were producer, run and inputs -- all
# three on this list -- and settings_fingerprint and scope moved in none of them.
# The largest file this gate will read whole to take a content hash of it. Every results
# file of this tree is orders below it; the inputs that are not results files are the
# derived arrays, the largest of which is 572 MB, and none of those carries a _meta block
# to separate anyway. Above the cap the edge stays counted as a divergence, which is the
# direction a refusal to look is allowed to have.
MAX_BODY_BYTES = 64 << 20

REWRITE_MAY_MOVE = (
    "producer",                # the node was re-run, which is the case being judged
    "inputs",                  # its own inputs were re-hashed, or moved house
    artifact.VOLATILE_KEY,     # the run clock, which two runs may always differ in
    "results_file",            # the file was renamed, which moves no figure
    "artifact_meta_version",   # the record shape, which carries no quantity
    # The calendar date of the run, which is the run clock at a coarser grain: one
    # producer of this tree, quoters/mm_bakeoff.py, writes the day beside the clock
    # instead of inside it, so the same rewrite that moves run moves this too. Named
    # here on 2026-08-13, which is what the list above asks for: it stopped on a field
    # nobody had classified and printed it rather than passing it, and the answer is
    # that its kind is a clock. Measured: run_date holds "2026-08-13" where
    # run.finished_utc of the same record holds "2026-08-13T10:03:52Z". Population, and
    # it is named because three of them are in play here and two of them happen to have
    # the same size: of the 99 tracked .json files that carry a _meta block, exactly two
    # hold run_date, and one of those two is this check's own results file recording the
    # finding -- so one producer publishes it. The other two counts a reader may reach
    # for are 88 files matching *_results.json and *_meta.json, and 88 distinct producers
    # named across the 99; neither is the population of this sentence.
    "run_date",
)

# THE FIFTH RESOLUTION STEP: SEARCH ROOTS OUTSIDE THE TREE, DECLARED HERE BY NAME.
#
# Each is a path RELATIVE to the tree root and each is optional. Relative because an
# absolute path names this machine, leaks an account name into a published artifact and
# cannot be followed by anybody who clones this repository -- checks/chk_no_abs_paths.py
# fails the run on one, and its exemption list is empty and stays empty. Optional
# because this tree is meant to be cloned on its own: a person who has only the tree has
# none of these directories, and the honest answer for them is absent_from_disk naming
# the root that is not there, never a count that quietly reached zero.
#
# Each carries the reason it is outside, because a root nobody can justify is a root
# somebody will widen until the gate resolves everything to something.
EXTERNAL_ROOTS = (
    {"path": "../02_data",
     "holds": "the market data itself: the December 2025 trade archive, the funding "
              "and spot pulls, the four days of the forward recording, and the "
              "acquisition log that records where each of them came from",
     "why_it_is_outside": "thirteen gigabytes of third-party market data cannot sit "
                          "inside a repository whose whole purpose is to be cloned and "
                          "re-run, and the licence and provenance of that data belong "
                          "beside the data rather than beside the code"},
)

# A CENSUS OF THE TREE IS NOT A COMPUTATION OVER DATA, AND ONLY ONE OF THE TWO CARRIES
# A FIXED DEBT. An artifact declaring more than this share of the population as its
# inputs has read the tree rather than a dataset, so anything at all that runs
# afterwards makes it stale. That is true and worth reporting, but it is a function of
# what has been recomputed since, not a backlog anybody works off, and a single ceiling
# over both kinds moves for reasons nobody can act on.
#
# The boundary is not a tuned number. The largest computation in this tree declares 27
# inputs of a population of 82; the census declares 83. Nothing whatever sits between a
# third and the whole, so any cut in that gap gives the same two groups.
CENSUS_INPUT_SHARE = 0.5

# Debt frozen on 2026-08-03, the day this gate was introduced, over a population of 82
# tracked .json files carrying 312 input records of which 258 hold a hash. A baseline
# here is a DECLARED DEBT and never a result: it may only ever be lowered, and the
# commit that lowers it names the artifacts that were recomputed. Raising one to turn a
# red run green removes the gate, which is the only thing it is for.
#
# THE DEBT IS A LIST AND NOT A NUMBER, AND THAT IS A MEASUREMENT RATHER THAN A
# PREFERENCE. Both counts of this debt move on a tree where nothing was recomputed.
# Four runs on 2026-08-03 gave 30, 33, 36 and 28 diverged edges, over 7 artifacts and
# then 6. The reason is that a results file is two things at once: an artifact with
# declared inputs, and a file the battery rewrites.
#
#   run_all_checks_results.json declares the check scripts, so a battery run refreshes
#   it and its five edges vanish; editing any check script brings them back.
#   chk_artifact_provenance_results.json declares all 83 tracked files, because reading
#   them is what it does, so everything that runs afterwards adds an edge: 1 when this
#   gate runs alone, 4 inside the battery, 11 once a few checks had been run by hand.
#
# A ceiling on either count would have to sit at the worst case, and a ceiling of 7
# artifacts passes a genuine seventh whenever run_all_checks_results.json happens to be
# fresh -- slack in the one direction that does damage. So the frozen debt is the SET
# below. An artifact outside it standing on a moved input fails the run and is named;
# one inside it that has been recomputed simply drops out and is reported so the list
# can be shortened. The list may only ever be shortened, and shortening it is the
# commit that says what was recomputed.
#
# Frozen 2026-08-03 at the seven the tree held at rest, with what each stood on:
#
#   build_results.json                            14 inputs moved under it
#   sensitivity_rollup_results.json                7
#   checks/run_all_checks_results.json            5, and 0 straight after a battery
#   checks/chk_artifact_provenance_results.json   1 on its own, 4 in a battery, and it
#                                                 grows with everything that runs after
#   checks/chk_side_signconv_results.json         1
#   i3_nonrecoverability_mid_results.json         1
#   notebooks/notebook_expected.json               1
#
# SHORTENED BY ONE ON 2026-08-05, AND THE OTHER CANDIDATE WAS KEPT ON A MEASUREMENT.
# The run of 2026-08-05 reported two of the seven as repaid and asked for both to be
# struck. Only one of the two was.
#
#   notebooks/notebook_expected.json  STRUCK. All nine of its declared inputs were
#   re-hashed by hand off disk and all nine match, maker_econ_results.json among them
#   at 68425aa7b25a, which is the value that had moved under it. Its inputs are results
#   of computations, so it re-diverges only when one of those nine nodes is recomputed,
#   which is what debt on this list is supposed to mean.
#
#   checks/run_all_checks_results.json  KEPT, and its cleanliness is not a repair. It
#   declares the fifteen check SCRIPTS as its inputs, chk_input_freshness.py among them
#   at 92bf8bfc3a44, so it reads clean only for as long as nobody edits a check -- and
#   editing this very file, to add the fifth resolution step, put it back on a moved
#   input the same day. Its state answers "has the battery been run since the last edit
#   to a check", which is a fact about what has run and not a backlog anybody works off.
#   Striking it would fail the next run for a regression that had not happened.
#
# SHORTENED BY THREE ON 2026-08-12, AND TWO OF THE THREE WERE NOT REPAIRS AT ALL: THEY
# WERE ENTRIES POINTING AT AN ADDRESS THAT NO LONGER EXISTED, PRINTED EVERY RUN AS
# "declared and now repaid". That is the reason DECLARED_DEBT_STATES below exists, and
# the reason it is armed rather than reported: an entry whose subject is gone cannot
# ever fire and cannot ever be repaid, so it reads exactly like finished work.
#
#   i3_nonrecoverability_mid_results.json  and  sensitivity_rollup_results.json
#   STRUCK. The restructuring -- commit 9d52367 of 2026-08-11, 112 files -- moved the
#   first into identity/ and the second into money/, and neither entry moved with it. Struck only after the files
#   were found again BY CONTENT at their new addresses and re-hashed by hand off disk:
#   identity/i3_nonrecoverability_mid_results.json declares 2 inputs and both match,
#   money/sensitivity_rollup_results.json declares 8 of which 4 carry a hash and all 4
#   match. So the divergence really was worked off, by the recompute the move required,
#   and the entry was dead as well as repaid. Had either come back dirty at its new
#   address the entry would have been RE-POINTED rather than struck, which is why the
#   rule below separates "the subject moved" from "the subject is gone" and names the
#   new address in the first case.
#
#   build_results.json  STRUCK, on the second sign rather than on a recompute. Ten of
#   its forty input records have moved as BYTES, and for all ten the recorded byte-state
#   was recovered from this repository's history by content and its body, with _meta
#   taken off, is identical to the body on disk -- as_quoter, i4_midmarkout,
#   ks2_persistence_10day, m2_figure, survivorship_census, t3, toxicity_frame,
#   ws1_horizon, ws2_hard_classifier and ws3_taker_pnl, ten of ten. The _meta fields
#   that moved are the producer, the run clock and the input list; the settings
#   fingerprint and the scope moved in none of the ten. So no figure this artifact
#   publishes stands on a number that no longer exists, which is the whole of what this
#   list is for. Those ten edges are still reported, under
#   rewritten_same_numbers, where they say the consumer has not been re-run rather than
#   that it is stale.
#
#   checks/chk_side_signconv_results.json  KEPT, and deliberately not decided on
#   2026-08-12. All three of its input records read clean that day, two matching and one
#   carrying no hash, which is the shape of a repaid entry. It is left standing because
#   that artifact was being rewritten while the reading was taken, so a verdict on it
#   would have been a verdict on a file mid-edit. It is the next candidate for striking,
#   and striking it needs one re-hash by hand once that file is at rest.
DECLARED_DIVERGED_ARTIFACTS = (
    "checks/chk_artifact_provenance_results.json",
    "checks/chk_side_signconv_results.json",
    "checks/run_all_checks_results.json",
)

# DOES EACH DECLARED ENTRY STILL HAVE A SUBJECT. A DEBT THAT MATCHES NOTHING READS AS
# FINISHED WORK, WHICH IS THE ONE DIRECTION OF ERROR THAT PASSES THROUGH A REVIEW.
#
# The list above is a set of names and the run compares it against the artifacts found
# standing on a moved input. That comparison answers a name it can no longer find in
# exactly the same words as a name it found and cleared: both come out in
# `declared_and_now_repaid`, which is printed with the words "shorten the list in this
# file" beside it. Measured on 2026-08-12: two of the six entries named an address the
# restructuring had emptied -- commit 9d52367 of 2026-08-11, 112 files moved -- and both
# had been printed as repaid on every run since, for a day, with nothing red anywhere.
#
# So the entries are resolved against the population as their own rule, and it is armed
# at zero rather than reported. Zero is a floor and not a frozen debt: an entry with no
# subject is a broken line in this file, never a backlog, and there is no state of the
# tree in which one is correct.
#
# THE THREE STATES ARE KEPT APART BECAUSE THE REPAIR DIFFERS, AND BECAUSE STRIKING A
# MOVED ENTRY WOULD LOSE A LIVE DIVERGENCE. An entry is resolved BY CONTENT first --
# does any artifact of the population carry this basename -- exactly as an input name is,
# and for the reason this file has already written down three times: a hash or a name
# identifies a document, a path is a guess about where it sits. An entry whose file
# merely moved house is re-pointed and keeps its debt; only an entry whose subject is
# nowhere in the population at all is struck.
DEBT_MATCHED = "matched"
DEBT_MOVED = "subject_moved"
DEBT_GONE = "subject_matches_nothing"
DECLARED_DEBT_STATES = (DEBT_MATCHED, DEBT_MOVED, DEBT_GONE)

# Inputs that carried a hash when the artifact was written and are not on disk now.
# These are the large derived arrays and the parquet pulls, which the tree does not
# keep: the disk budget is stated in artifact.py. It is debt rather than design because
# a hash WAS recorded, which means the file was there once and could be there again.
#
# This one was frozen twice on the same day and the first figure was wrong, which is
# worth keeping written down. It was set at 52 against a resolver that looked in two
# places, and 19 of those 52 were files sitting in the tree under a name whose directory
# the record had dropped. A ceiling 19 above the real debt is slack a future regression
# can hide inside, and the direction matters: an input that reads absent cannot be
# compared, so a divergence underneath it is invisible. The figure below is what the
# three-step resolver measures, and it may only ever be lowered from here.
BASELINE_ABSENT_WITH_A_RECORDED_HASH = 0
# LOWERED FROM 11 TO 0 ON 2026-08-05, and by a repair rather than by a rewording. The
# eleven were the whole of the debt, and all eleven were on disk the entire time. They
# were resolved by CONTENT rather than by path -- a walk of 9 425 files of the
# workspace, hashing every file carrying one of the eleven basenames -- and each of the
# eleven matched its recorded digest exactly, 11 of 11, with exactly one candidate
# apiece. Four days of the forward recording and the acquisition log sit under
# ../02_data, the three funding and spot pulls under ../02_data/raw/funding, the trade
# archive under ../02_data/raw, and two written documents in a directory of prose
# beside it that this repository does not declare. Not one of them had ever been
# inside this tree.
#
# So the eleven were never data this repository had lost. They were the four resolution
# steps of that day all looking INSIDE the tree while the file sat beside it, which is
# a count measuring its own instrument rather than the world. The fifth step reads the
# declared roots above and takes the figure to nought.
#
# It may only ever go down, and there is one floor below which it cannot: on a checkout
# that carries the tree alone these eleven cannot be found by anything, and the rule
# below stands DOWN rather than passing or failing, saying which declared root was
# absent. A measurement that cannot be made is not a measurement that passed.
#
# LOWERED FROM 33 ON 2026-08-04, and by a repair rather than by a rewording. Adding the
# fourth resolution step -- choosing among same-named candidates by the recorded hash,
# never by position -- took the count from 61 to 11 in one run. The 61 was itself the
# 33 plus 28 inputs declared that day by two new artifacts, so the honest before-and-
# after on the same population is 33 against 11: twenty-two of the original debt was
# never missing data at all, it was the same panel shard kept under two directories and
# a lookup that refused to tell them apart. What is left is eleven inputs that really
# are gone from disk, and lowering the figure is what the rule above requires of a
# repair. It may only ever go down.

# THE TWO OPPOSITE CASES, BUILT ON EVERY RUN AND NAMED NOWHERE.
#
# One reference point cannot calibrate a comparator: it cannot tell one that is too
# wide from one that is too narrow. This project has already shipped three versions of
# a single guard that were wrong in opposite directions and passed their one reference
# every time. So the calibration is a pair. What follows is about where the pair comes
# from, which turned out to matter more than what is in it.
#
# THE PAIR IS INJECTED RATHER THAN ASSERTED, AND THAT IS A REPAIR MADE 2026-08-04.
# Written a day earlier, this calibration NAMED two artifacts of the live tree: one
# that then stood on a moved input and therefore had to fire, one whose inputs all
# matched and therefore had to stay silent. Inside a day the first had been
# recomputed. The debt was worked off, which is the gate doing its job, and the leg
# that proved this gate can fire went vacuous with it, reporting NOT ANSWERED with 0
# diverged inputs of 9. A case anchored on a live defect erases itself the moment the
# defect is repaired, and what is left behind is a green gate that has never been seen
# to find anything -- the direction of measuring error that passes through a review
# rather than stopping it. The retired pair is written down here so that the history
# does not leave with the names:
#
#   fired  until 2026-08-04  notebooks/notebook_expected.json, 1 of its 9 hashed
#                            inputs moved: the notebook took its expected figures
#                            from maker_econ_results.json at b95333fa592f and the
#                            file on disk had become 68425aa7b25a. Repaired by
#                            recomputing the notebook, after which the case read
#                            0 diverged of 9 and answered nothing
#   silent until 2026-08-04  mm_bakeoff_results.json, 3 hashed inputs and 3 matches
#
# WHAT REPLACES THEM, AND WHY IT CANNOT EMPTY. The silent half is a real input record
# lifted at run time out of this run's own sweep -- CALIBRATION_ANCHOR_RULE below says
# which one and the run prints it -- so it is live data exercising the live resolution,
# and no name in this file can go stale with the tree. The firing half is that same
# record with one hex digit of its recorded sha256 changed. Nothing else differs, and
# that is measured leaf by leaf rather than assumed: the two verdicts are compared
# field by field and the only fields permitted to move are the recorded hash, the
# verdict, and the sentence that explains the verdict.
#
# The pair also carries the discrimination the retired silent case was picked for.
# Both halves resolve to the SAME file and read the SAME digest off disk, and one
# comes out matches while the other comes out diverged. A gate keyed on the file rather
# than on the edge cannot produce those two answers in one run. Unlike the retired
# case, this holds whatever the tree has just recomputed.
#
# The single condition that would stop the pair running is a tree holding no matched
# input record at all. That is reported as a FAILURE and not as a silence: a gate that
# cannot be exercised has not passed.
CALIBRATION_ANCHOR_RULE = (
    "the first, in sorted order by artifact then by input name, of the input records "
    "this run judged as matches while carrying a recorded hash and resolving to a file "
    "on disk")
CALIBRATION_MUST_STAY_SILENT = {
    "case": "a real input record of a live artifact, unaltered",
    "chosen_by": CALIBRATION_ANCHOR_RULE,
    "expect": MATCHES,
    "why": "the file the artifact recorded reading is the file that is there now, so "
           "there is nothing for this gate to report",
}
CALIBRATION_MUST_FIRE = {
    "case": "that same record with one hex digit of its recorded sha256 changed",
    "chosen_by": "derived from the silent case, so the two differ by one hex digit "
                 "and by nothing else",
    "expect": UNKNOWN,
    "why": "the recorded hash no longer equals the file on disk, which is the whole "
           "of what this gate judges. One digit rather than a whole hash keeps the "
           "fault the smallest one the gate is meant to notice, and keeps the length "
           "and the alphabet, so nothing can reject it for a reason other than the "
           "comparison itself. It reads diverged_body_unknown rather than diverged "
           "since 2026-08-11, and that is the point of it now: a byte-state nobody "
           "can produce is counted as debt and never as a pass, which is the live "
           "case for the rule that a repair may not turn an unanswerable question "
           "green",
}
# THE SECOND LIVE PAIR, ADDED 2026-08-11 WITH THE SECOND SIGN. The pair above moves the
# recorded hash to a value that never existed, so it settles what happens to an
# unanswerable edge and cannot settle what happens to an answerable one. This pair moves
# it to a byte-state that DID exist, taken out of this repository's own history, and it
# is the only pair that exercises the comparison the repair was written for.
CALIBRATION_BODY_ANCHOR_RULE = (
    "the first input record, in sorted order by artifact then by input name, that "
    "resolves to a document on disk carrying a _meta block and for which this "
    "repository's history holds an earlier byte-state of the same name")
CALIBRATION_BODY_MUST_STAY_SILENT = {
    "case": "a real input record pointed at a real earlier byte-state of the same file "
            "whose content is identical to what is on disk",
    "chosen_by": CALIBRATION_BODY_ANCHOR_RULE,
    "expect": REWRITTEN,
    "why": "the file was rewritten and its numbers were not, which is what recomputing "
           "a node does to every consumer of it and what this gate reported as a stale "
           "figure until 2026-08-11",
}
CALIBRATION_BODY_MUST_FIRE = {
    "case": "the same record pointed at a real earlier byte-state of the same file "
            "whose content DIFFERS from what is on disk",
    "chosen_by": CALIBRATION_BODY_ANCHOR_RULE,
    "expect": DIVERGED,
    "why": "the numbers moved, which is the finding this gate exists for. Both halves "
           "stand on states that really existed in this repository, so neither can be "
           "dismissed as a value the tree could never produce, and both are chosen by "
           "rule rather than named, so a recompute moves which record is used and "
           "never whether there is one",
}
CALIBRATION_RETIRED = {
    "retired_on": "2026-08-04",
    "why": "both cases named a live artifact, and the firing one went vacuous when "
           "the divergence it stood on was repaired: 0 diverged of 9 where 1 was "
           "expected. A calibration case anchored on a live defect erases itself the "
           "day somebody fixes the defect",
    "fired": {"artifact": "notebooks/notebook_expected.json", "hashed_inputs": 9,
              "expect_diverged": 1, "diverged_input": "maker_econ_results.json",
              "recorded": "b95333fa592f", "on_disk": "68425aa7b25a"},
    "stayed_silent": {"artifact": "mm_bakeoff_results.json", "hashed_inputs": 3,
                      "expect_diverged": 0},
}


# =====================================================================
# THE POPULATION AND THE TWO AMENDMENTS
# =====================================================================

def population(root):
    """Every tracked .json this gate judges, and what it added and removed, and why.

    Returns (kept, dropped, amendments). The amendments are returned rather than
    applied silently because each is a difference between this gate's count and the
    neighbouring gate's count of what looks like the same thing, and an unexplained
    difference between two counts of one property is the defect both gates exist to
    prevent.
    """
    kept, dropped = _prov.population(root)
    kept, dropped = list(kept), [dict(row) for row in dropped]
    amendments = []

    # AMENDMENT ONE. The shared predicate removes the provenance gate's own results
    # file so that gate cannot score itself. Here it is an ordinary artifact, and it
    # carries a recorded input hash for every file of the population, so leaving it out
    # would hide a gate's own staleness behind a rule written for a different question.
    readmit = _prov.SELF_OUTPUT
    if readmit not in kept and os.path.isfile(os.path.join(root, readmit)):
        kept.append(readmit)
        dropped = [row for row in dropped if row["file"] != readmit]
        amendments.append({
            "file": readmit, "action": "readmitted",
            "why": "chk_artifact_provenance.population() removes it so that gate "
                   "cannot score itself; that reason does not apply to a gate asking "
                   "about its inputs, and leaving it out reports 6 artifacts on a "
                   "diverged input where the measured number is 7"})

    # AMENDMENT TWO. This gate's own output, for the reason the neighbour removes its
    # own: reading the previous run's output would make this run's answer depend on the
    # previous run. The SELF-CONFORMANCE leg in main() holds it to the rule instead.
    if SELF_OUTPUT in kept:
        kept.remove(SELF_OUTPUT)
        dropped.append({"file": SELF_OUTPUT, "rule": "this gate's own output"})
        amendments.append({
            "file": SELF_OUTPUT, "action": "removed",
            "why": "this gate writes it, so reading it would make this run's answer "
                   "depend on the previous run's; it is held to the same rule by the "
                   "self-conformance leg, which re-resolves the file just written"})

    return sorted(kept), sorted(dropped, key=lambda row: row["file"]), amendments


# =====================================================================
# RESOLVING AN INPUT NAME AND JUDGING ONE EDGE
# =====================================================================

def resolution_bases(meta, root, scripts):
    """The directories an input name is resolved against, in order, and the producer.

    First the producer's own directory, which is what artifact.input_record() tries
    first. Then the tree root, which is the working directory every producer in this
    tree is launched from and therefore the second candidate input_record() reaches
    through the ordinary relative path. Naming it here rather than relying on the
    process's working directory is the point: a gate whose answer moves with the
    directory it was started from is not answering a question about the repository.

    The third step is not a directory and is not returned here; it is the basename
    index below, consulted only when both of these fail.
    """
    record = meta.get("producer") if isinstance(meta, dict) else None
    name = record.get("script") if isinstance(record, dict) else None
    producer_rel = scripts.get(name) if name else None
    bases = []
    if producer_rel:
        bases.append((os.path.join(root, os.path.dirname(producer_rel)),
                      "the producer's own directory"))
    bases.append((root, "the tree root"))
    return bases, name, producer_rel


def basename_index(root):
    """Basename -> every repo-relative path on disk carrying it, sorted.

    THE THIRD RESOLUTION STEP, AND ITS REFUSAL IS THE WHOLE OF ITS SAFETY. An input
    record keeps the basename and drops the directory, so a producer that declared
    probes/decay_curve_results.json leaves a record that neither the producer's
    directory nor the tree root can resolve. Measured on this gate's first run, 42 of
    52 apparent absences were files that had been in the tree all along.

    A basename the tree holds twice keeps BOTH paths and resolves to neither, exactly
    as chk_artifact_provenance.scripts_on_disk refuses a duplicate producer name.
    Guessing would compare an artifact against a file it never read, and a false MATCH
    is the one outcome this gate exists to prevent -- it certifies a stale figure, where
    a false alarm merely costs somebody a look. The candidates are kept so that an
    unresolved name is reported with the reason it could not be resolved.

    The walk covers the disk rather than the tracked files, because the question is
    whether the producer's input is there, and an input excluded from version control
    for its size is still the file the numbers were computed from.
    """
    found = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ("__pycache__", ".git")]
        for name in filenames:
            rel = os.path.relpath(os.path.join(dirpath, name),
                                  root).replace(os.sep, "/")
            found.setdefault(name, []).append(rel)
    return {name: sorted(paths) for name, paths in found.items()}


def external_roots(root, specs=EXTERNAL_ROOTS):
    """The declared roots outside the tree, split into present and missing, and indexed.

    THE FIFTH RESOLUTION STEP. Returns (present, missing, index), where index maps a
    basename to every path beneath a PRESENT root carrying it, written relative to the
    tree root and therefore as `../02_data/...`. Nothing absolute is built, kept or
    reported: the paths this function hands out are the paths that go into the results
    file, and chk_no_abs_paths.py reads that file like any other.

    A root that is not a directory on this disk goes into `missing` and is not searched.
    That is not a degraded mode to be hidden. It is the ordinary state of anybody who
    cloned this tree by itself, which is how the tree is meant to be cloned, and the
    caller turns it into a named reason on every input it then cannot resolve.
    """
    present, missing, index = [], [], {}
    for spec in specs:
        base = os.path.normpath(os.path.join(root, spec["path"]))
        if not os.path.isdir(base):
            missing.append(dict(spec, on_disk=False, n_files=0))
            continue
        count = 0
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in ("__pycache__", ".git")]
            for name in filenames:
                rel = os.path.relpath(os.path.join(dirpath, name),
                                      root).replace(os.sep, "/")
                index.setdefault(name, []).append(rel)
                count += 1
        present.append(dict(spec, on_disk=True, n_files=count))
    return (present, missing,
            {name: sorted(paths) for name, paths in index.items()})


def roots_note(present, missing):
    """One sentence naming which declared roots were searched and which were not.

    Written once per run and carried into the reason of every input that could not be
    resolved, because "the file is not on disk" and "the place it lives was not on this
    disk to search" are different facts and the second one names its own repair.
    """
    searched = ", ".join(f"{row['path']} ({row['n_files']} files)" for row in present)
    gone = ", ".join(row["path"] for row in missing)
    if not missing:
        return f"the declared roots outside the tree were searched: {searched}"
    if not present:
        return (f"NONE of the declared roots outside the tree is on this disk "
                f"({gone}), so an input that lives under one of them cannot be found "
                f"here at all; this is what a checkout of the tree by itself looks "
                f"like, and it is a limit of the checkout rather than a missing file")
    return (f"the declared roots on this disk were searched ({searched}), and "
            f"{gone} is NOT on this disk, so an input living there cannot be found")


def pack_roots(present, missing, index):
    """What judge_edge() is handed for the fifth step, note and all, built in one place.

    The note is computed once per run rather than once per input record: it says the
    same thing for all 373 of them, and a sentence assembled 373 times is a sentence
    that can come out differently on the 374th.
    """
    return {"index": index, "present": present, "missing": missing,
            "note": roots_note(present, missing)}


def withheld_roots(specs=EXTERNAL_ROOTS):
    """The same declaration with nothing on disk: what a clone of the tree alone sees.

    Not a test double. This is the state of a reader's clone, and the live
    calibration judges one real input record with it to show that the answer there is
    an honest absent_from_disk naming the root, and not a count that reached zero.
    """
    return pack_roots([], [dict(spec, on_disk=False, n_files=0) for spec in specs], {})


# THE DATA DIRECTORY IS A DECLARED ROOT TOO, AND IT IS ASKED OF ITS OWN HOME. The
# derived intermediates the pipeline reads -- markout panels, mid series, taker maps --
# are excluded from version control for their size and live wherever the repository's
# data setting points: panel_io.data_root(), which honours CAP_DATA_DIR and its sibling
# names. Measured 2026-10-21 on the open checkout: 167 input records read absent from
# disk, and resolved by content every one of the 167 lay in that directory with its
# recorded hash. The count measured where this gate looked. So the directory is a root,
# taken by CALLING panel_io rather than by re-reading its environment names here, and it
# is declared only when the setting moves it off the default -- the default is the tree
# itself, which the first four steps already search.
DATA_ROOT_SPEC = {
    "holds": "the derived intermediates the pipeline reads and does not ship: markout "
             "panels, mid series and taker maps, wherever the repository's data "
             "setting points",
    "why_it_is_outside": "they are excluded from version control for their size; "
                         "panel_io.data_root() is their one declared home, and it is "
                         "read by calling it, never by repeating its rule",
    "from": "panel_io.data_root()",
}


def declared_roots(root=None):
    """EXTERNAL_ROOTS plus the data directory, when the data setting moves it elsewhere.

    The data root is written relative to the tree root, like every other root, so the
    results file carries no absolute path. Returns a tuple shaped like EXTERNAL_ROOTS.
    """
    root = ROOT if root is None else root
    chosen = os.path.realpath(panel_io.data_root())
    default = os.path.realpath(panel_io.data_root(env_names=()))
    tree = os.path.realpath(root)
    if chosen == default or chosen == tree:
        return EXTERNAL_ROOTS
    rel = os.path.relpath(chosen, tree).replace(os.sep, "/")
    if any(os.path.normpath(spec["path"]) == os.path.normpath(rel)
           for spec in EXTERNAL_ROOTS):
        return EXTERNAL_ROOTS
    return EXTERNAL_ROOTS + (dict(DATA_ROOT_SPEC, path=rel),)


def _declared_root_of(rel_path, present):
    """Which declared root a resolved path came from, so the answer names its source."""
    for spec in present:
        if rel_path.startswith(spec["path"].rstrip("/") + "/"):
            return spec["path"]
    return None


def _choose_by_content(candidates, root, recorded, cache):
    """One path among same-named candidates, by uniqueness or by CONTENT, never by order.

    Returns (path or None, how, survivors). Shared by the third-and-fourth steps inside
    the tree and by the fifth step outside it, called rather than copied, because two
    implementations of one rule is how a repair reaches one of them and not the other.

    The refusal is the safety. A basename identifies no file when the tree holds it
    twice, and choosing whichever copy the walk met first would compare an artifact
    against a file it may never have read. A hash does identify one, so hashing every
    candidate and keeping the one that equals the record chooses by what the producer
    actually read; when none matches, nothing is chosen and the ambiguity stands
    exactly as it was.
    """
    if len(candidates) == 1:
        return candidates[0], "unique", None
    if not recorded:
        return None, None, None
    matched = [c for c in candidates
               if _digest(os.path.join(root, c), cache) == recorded]
    if len(matched) == 1:
        return matched[0], "content", 1
    return None, None, len(matched)


def _digest(path, cache):
    """sha256 of one file, hashed once per run however many artifacts name it.

    The cache is not an optimisation for its own sake. Eighty-eight distinct files
    stand behind the population's input records and two of them are large arrays; the
    same quickwin_markouts.npz is named by fourteen artifacts, and hashing it fourteen
    times would turn a two-second gate into one nobody puts in the battery.
    """
    if path not in cache:
        cache[path] = artifact.sha256_file(path)
    return cache[path]


# =====================================================================
# THE SECOND SIGN: THE DOCUMENT WITHOUT ITS _meta BLOCK
# =====================================================================

def body_digest(raw):
    """(digest, meta, why_not) for one document: its hash with the _meta block removed.

    The first return value is the SECOND SIGN this gate compares, and it exists because
    the first one answers a question nobody asked. A results file carries the clock of
    its run and the hash of its producer inside _meta, so re-running a node moves the
    hash of the whole file whether or not one published figure moved with it. Taking
    _meta off leaves exactly what the file publishes, and comparing that answers the
    question a reader of this gate actually has.

    `why_not` is filled and the digest is None for anything that has no body to speak
    of: a producer script, a raw array, a document that is not a mapping, a results file
    written before this record existed. Those are not failures of this function and they
    are not silences either -- the caller turns each into a named state, because "this
    input has no separable content" and "this input's content moved" are different facts
    and only the second one is a stale figure.

    The digest is taken over a canonical dump rather than over the raw bytes, so that
    reindenting a file or writing its keys in another order is not read as a moved
    number. That is deliberate and it is also the limit: two documents whose keys differ
    only in ORDER hash the same here, which for a file of results carries no quantity.

    THE RULE IS WRITTEN TWICE IN THIS PROJECT AND THAT IS DECLARED RATHER THAN HIDDEN.
    The snapshot tool the restructuring of 2026-08-10 was measured with drops _meta for
    the same reason and says so in its own docstring. It lives outside this tree, and
    this tree may not reach outside itself -- that is the rule that keeps it cloneable
    on its own. So the two cannot be one function, and the
    honest treatment is to name the other one here rather than let a reader believe
    there is only one.
    """
    try:
        document = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None, None, "it is not a JSON document, so the whole file is its content"
    if not isinstance(document, dict):
        return None, None, "its top level is not a mapping, so it carries no _meta"
    if not isinstance(document.get(artifact.META_KEY), dict):
        return None, None, ("it carries no _meta block, so there is nothing to take off "
                            "and the whole file is its content")
    body = {key: value for key, value in document.items()
            if key != artifact.META_KEY}
    text = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return (hashlib.sha256(text.encode("utf-8")).hexdigest(),
            document[artifact.META_KEY], None)


def content_hash_on_disk(path):
    """The second sign of a file on disk, with the size cap applied in one place.

    Three callers ask this -- the judgement, the live calibration's anchor search and the
    live pair -- and a cap written three times is a cap that drifts in two of them.

    A REFUSAL TO LOOK IS IN THE SAFE DIRECTION AND IS SAID OUT LOUD. Taking the second
    sign means holding a whole document in memory, and the inputs of this tree include
    derived arrays of several hundred megabytes. None of those is a JSON results file, so
    nothing this repair exists for is above the cap; and refusing to look can only leave
    an edge counted as debt, never clear one.
    """
    size = os.path.getsize(path)
    if size > MAX_BODY_BYTES:
        return None, None, (f"it is {size / 1e6:.0f} MB, above the "
                            f"{MAX_BODY_BYTES / 1e6:.0f} MB this gate will read into "
                            f"memory to take a content hash")
    return body_digest(_raw_on_disk(path))


def _raw_on_disk(path):
    """The bytes of one input file. The one read of an input's whole content, shared by
    the second sign and by the handmade calibration pair, so the build's I/O census sees
    one call and not two."""
    with open(path, "rb") as handle:
        return handle.read()


class History:
    """The byte-states this repository holds, addressed by CONTENT and not by path.

    An input record keeps a hash and not the bytes, so the document that hash stands for
    has to be found again before the second sign can be taken of it. Every artifact of
    this tree is committed, which makes the recorded byte-state an object of this
    repository's history, and this is the lookup.

    BY CONTENT, AND THAT IS A MEASUREMENT RATHER THAN A PREFERENCE. The obvious lookup
    is by path: walk `git log` of the file and hash each version, which is what
    chk_expensive_edits._committed_source does for a producer script. It was tried here
    first and it answered 0 of 16, because the restructuring of 2026-08-10 moved these
    files and the paths they carry today have no history at all. The same recorded
    hashes were then looked for among every object of the repository and 11 of 11 were
    there. A hash identifies a document; a path is a guess about where it sits, and this
    is the third place in this file where that guess has been wrong.

    The neighbour's function is therefore NOT called here, and the reason is that it
    answers a different question -- the bytes at a known path -- rather than that its
    answer was inconvenient. That it now returns nothing for a moved producer is a
    finding about that gate and is reported as one.

    Nothing is retained but a map from digest to object id, so a repository with a large
    history costs one pass and not one copy of itself in memory. Two lookups are tried
    in order and the run says which one placed the state: the objects whose historical
    basename is the input's, which is one hundredth of the repository and settles every
    case measured so far, and then every object there is, which finds a file that was
    renamed rather than moved.
    """

    def __init__(self, root):
        self.root = root
        self._by_name = None        # basename -> [object id], the whole history
        self._digests = {}          # basename -> {sha256: object id}
        self._anywhere = None       # {sha256: object id} over every object
        self.n_objects = 0
        self.n_blobs_hashed = 0
        self.note = None

    def _run(self, args, binary=False):
        try:
            return subprocess.run(["git", "-C", self.root] + args,
                                  capture_output=True,
                                  text=not binary)
        except (OSError, ValueError):
            return None

    def _index(self):
        """basename -> object ids, over every object of every ref. Built once."""
        if self._by_name is not None:
            return self._by_name
        self._by_name = {}
        out = self._run(["rev-list", "--objects", "--all"])
        if out is None or out.returncode:
            self.note = ("git could not be asked for this repository's history here, so "
                         "no recorded byte-state can be recovered and every input whose "
                         "bytes moved reads " + UNKNOWN)
            return self._by_name
        lines = out.stdout.splitlines()
        for line in lines:
            oid, _, path = line.partition(" ")
            if path:
                self._by_name.setdefault(os.path.basename(path), []).append(oid)
        self.n_objects = len(lines)
        self.note = (f"{self.n_objects} objects of this repository's history are "
                     f"reachable, carrying {len(self._by_name)} distinct basenames")
        return self._by_name

    def usable(self):
        """Whether a recorded byte-state can be looked for at all on this checkout."""
        return bool(self._index())

    def _hash(self, oids):
        """{sha256: object id} over the given objects, hashed once and not retained."""
        found = {}
        oids = sorted(set(oids))
        if not oids:
            return found
        try:
            proc = subprocess.Popen(["git", "-C", self.root, "cat-file", "--batch"],
                                    stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        except (OSError, ValueError):
            return found
        try:
            for oid in oids:
                proc.stdin.write((oid + "\n").encode())
                proc.stdin.flush()
                header = proc.stdout.readline().decode().split()
                if len(header) != 3:
                    # "<oid> missing": nothing follows it, so nothing is consumed. Any
                    # other reading here would put the stream out of step and every
                    # object after it would be hashed as somebody else's bytes.
                    continue
                data = proc.stdout.read(int(header[2]))
                proc.stdout.read(1)
                if header[1] == "blob":
                    found[hashlib.sha256(data).hexdigest()] = oid
        finally:
            proc.stdin.close()
            proc.wait()
        self.n_blobs_hashed += len(found)
        return found

    def _hash_all(self):
        """{sha256: object id} over every object there is, taken as one stream.

        THE SHAPE OF THIS CALL IS THE WHOLE OF ITS COST. Asking for objects one at a
        time down a pipe costs a round trip apiece, and over the 2707 objects of this
        repository that measured at 16 seconds, which would have tripled the price of a
        gate the battery runs every time. `--batch-all-objects` hands every object over
        unasked and the same work takes under a second. The saving is not the point on
        its own; a gate that becomes expensive is a gate somebody takes out of the
        battery, and this one exists because nobody was asking its question at all.
        """
        found = {}
        try:
            proc = subprocess.Popen(
                ["git", "-C", self.root, "cat-file", "--batch-all-objects", "--batch",
                 "--buffer"],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE)
        except (OSError, ValueError):
            return found
        try:
            while True:
                line = proc.stdout.readline()
                if not line:
                    break
                header = line.decode("utf-8", "replace").split()
                if len(header) != 3:
                    continue
                # Exactly size bytes and then the one newline git writes after them, so
                # the stream stays in step even for a blob full of newlines.
                data = proc.stdout.read(int(header[2]))
                proc.stdout.read(1)
                if header[1] == "blob":
                    found[hashlib.sha256(data).hexdigest()] = header[0]
        finally:
            proc.stdout.close()
            proc.wait()
        self.n_blobs_hashed += len(found)
        return found

    def _show(self, oid):
        out = self._run(["cat-file", "blob", oid], binary=True)
        return None if out is None or out.returncode else out.stdout

    def digests(self, basename):
        """Every byte-state of this basename the history holds, as sha256 -> object id.

        Used by find() and by the live calibration, which needs to see the states rather
        than ask about one: its two halves are built by looking for a real earlier state
        of a real input whose content agrees with today's, and another whose content
        does not. Naming a state in this file instead would be a case anchored on the
        tree, and this file has already lost one calibration that way.
        """
        if basename not in self._digests:
            self._digests[basename] = self._hash(self._index().get(basename, ()))
        return self._digests[basename]

    def blob(self, oid):
        """The bytes of one object, for a caller that already knows which one."""
        return self._show(oid)

    def find(self, basename, digest):
        """(bytes, how) for one recorded byte-state, or (None, None) if it is gone."""
        if not digest or not self.usable():
            return None, None
        oid = self.digests(basename).get(digest)
        if oid:
            return self._show(oid), "among the objects carrying this input's basename"
        if self._anywhere is None:
            self._anywhere = self._hash_all()
        oid = self._anywhere.get(digest)
        if oid:
            return self._show(oid), ("among every object of the history, which places a "
                                     "file that was renamed rather than moved")
        return None, None


def judge_body(row, path, history):
    """Did the BYTES move on their own, or did the numbers move with them.

    Called for one edge whose recorded hash and file on disk already differ, and it is
    the only place that distinction is made, so the calibration exercising this function
    is exercising what the run decides with.

    Three answers and they are three states rather than one with a footnote. The input
    has no separable content, so the bytes are the content and this is a divergence. The
    body is recovered and differs, which is a divergence and the one this gate was
    written for. The body is recovered and agrees, which is a rewrite -- provided every
    _meta field that moved is on the allow-list, because identical digits under a
    changed setting are a different question rather than the same answer.

    A recorded byte-state this repository cannot produce is the fourth answer and it is
    not any of the three: it reads diverged_body_unknown, which is counted as debt. An
    artifact may never go green because the evidence that would have cleared it is
    missing.
    """
    recorded = row["recorded_sha256"]
    now_body, now_meta, why_not = content_hash_on_disk(path)
    row["on_disk_body_sha256"] = now_body

    if now_body is None:
        # A SCRIPT WHOSE EDIT IS CERTIFIED DOCUMENTATION-ONLY. The certificate is read by
        # calling chk_artifact_provenance, the one home of that register, so the gate
        # that asks about producers and this one, which asks about inputs, cannot answer
        # one pair of hashes two ways.
        certified = _prov.documentation_only_pair(ROOT, row["input"], recorded,
                                                  row["on_disk_sha256"])
        if certified:
            row["state"] = NEUTRAL_INPUT
            row["neutral_certificate"] = certified
            row["why"] = (
                f"input changed neutrally, certified: {row['input']} moved from "
                f"{recorded[:12]} to {row['on_disk_sha256'][:12]} by comments and "
                f"docstrings alone, as checks/NEUTRAL_EDITS.json certifies for that pair "
                f"of hashes; no statement of it changed, so no reader of it can have "
                f"moved a figure. Not a run: a run of this artifact retires the entry")
            return row
        row["state"] = DIVERGED
        row["why"] = (
            f"this artifact was computed from {row['input']} at {recorded[:12]} and the "
            f"file on disk is {row['on_disk_sha256'][:12]}. There is no separable "
            f"content to compare here, because {why_not}, so the bytes ARE the content "
            f"and this is a change in what the artifact stands on")
        return row

    if history is None:
        row["state"] = UNKNOWN
        row["why"] = (
            f"this artifact was computed from {row['input']} at {recorded[:12]} and the "
            f"file on disk is {row['on_disk_sha256'][:12]}. The file carries a _meta "
            f"block, so a rewrite and a moved number are two different things here, and "
            f"no history was offered on this run to tell them apart. The comparison is "
            f"unmade rather than passed, and this edge is counted with the divergences")
        return row

    then_raw, how = history.find(os.path.basename(row["where"]), recorded)
    if then_raw is None:
        row["state"] = UNKNOWN
        row["why"] = (
            f"this artifact was computed from {row['input']} at {recorded[:12]} and the "
            f"file on disk is {row['on_disk_sha256'][:12]}. Whether the numbers moved "
            f"cannot be told apart from whether the file was merely rewritten, because "
            f"no object of this repository's history carries the recorded byte-state, "
            f"so the document it stands for cannot be read. "
            + (history.note or "") +
            ". The comparison is unmade rather than passed, and this edge is counted "
            "with the divergences")
        return row

    then_body, then_meta, then_why_not = body_digest(then_raw)
    row["recorded_body_sha256"] = then_body
    row["recorded_state_found_in"] = how
    if then_body is None:
        row["state"] = UNKNOWN
        row["why"] = (
            f"the recorded byte-state of {row['input']} was recovered from this "
            f"repository's history, and it cannot be read as a document: "
            f"{then_why_not}. The file on disk can be, so the two are not comparable "
            f"and the comparison is unmade rather than passed")
        return row

    moved = sorted(key for key in set(then_meta) | set(now_meta)
                   if then_meta.get(key) != now_meta.get(key))
    row["meta_fields_that_moved"] = moved
    if then_body != now_body:
        row["state"] = DIVERGED
        row["why"] = (
            f"this artifact was computed from {row['input']} whose content hashed "
            f"{then_body[:12]}, and the content of the file on disk is {now_body[:12]}: "
            f"every figure here stands on numbers that no longer exist")
        return row

    outside = [key for key in moved if key not in REWRITE_MAY_MOVE]
    if outside:
        row["state"] = DIVERGED
        row["why"] = (
            f"{row['input']} publishes the same numbers as it did when this artifact "
            f"read it, and it publishes them under a changed {', '.join(outside)}. "
            f"Identical digits on a different setting are a different question rather "
            f"than the same answer, so this counts as a change in what the artifact "
            f"stands on")
        return row

    row["state"] = REWRITTEN
    row["why"] = (
        f"{row['input']} was rewritten and its numbers were not: the recorded state and "
        f"the file on disk differ as bytes ({recorded[:12]} against "
        f"{row['on_disk_sha256'][:12]}) and agree exactly once _meta is taken off, at "
        f"{now_body[:12]}. What moved inside _meta is {', '.join(moved) or 'nothing'}, "
        f"and every one of those is on the allow-list. The recorded state was found "
        f"{how}")
    return row


def judge_edge(rel, record, bases, root, cache, index=None, external=None,
               history=None):
    """One input record of one artifact, as one of the seven outcomes.

    `record` is an entry of _meta.inputs as artifact.write() left it. `external` is what
    external_roots() returned, packed by the caller, or None when the fifth step is to
    be withheld -- which is not a switch for convenience but the state of a checkout
    carrying the tree alone, and the live calibration below judges one real record both
    ways to prove the two answers differ in the way they are supposed to.

    `history` is what a byte-difference is put to before it is called a divergence, and
    None withholds that question exactly as None withholds the fifth step: an edge whose
    bytes moved then reads diverged_body_unknown and is counted as debt. Withholding it
    can make this gate stricter and never looser, which is the direction a switch is
    allowed to have.

    The returned row always carries the expectation, the fact and the place whatever the
    verdict, so a caller printing a failure never has to go back to the file to find
    them.
    """
    name = str(record.get("name") or "")
    recorded = record.get("sha256") or None
    row = {"artifact": rel, "input": name, "recorded_sha256": recorded,
           "recorded_bytes": record.get("bytes"),
           "present_when_written": bool(record.get("present")),
           "on_disk_sha256": None, "on_disk_bytes": None, "where": None,
           "resolved_by": None, "resolved_root": None, "ambiguous_in": None,
           "ambiguity_survives_hashing": None,
           # THE SECOND SIGN, BESIDE THE FIRST AND NOT INSTEAD OF IT. The two recorded_*
           # and two on_disk_* fields are the whole-file hash and the hash of the same
           # document without _meta. Both are written on every edge, so a reader can see
           # which of the two moved, and so that a record written before this gate could
           # take the second sign stays comparable under the first.
           "recorded_body_sha256": None, "on_disk_body_sha256": None,
           "recorded_state_found_in": None, "meta_fields_that_moved": None}

    if "://" in name:
        row["state"] = REMOTE
        row["why"] = ("an address rather than a local file, so nothing on disk was "
                      "ever expected here; the raw-tape parsers read the archive "
                      "directly and this is their design, not staleness")
        return row

    found = None
    for base, label in bases:
        candidate = os.path.join(base, name)
        if os.path.isfile(candidate):
            found, row["resolved_by"] = candidate, label
            break
    if found is None and index is not None and name in index:
        # THE THIRD AND FOURTH STEPS, INSIDE THE TREE. The third takes a basename the
        # tree holds exactly once. The fourth takes one it holds twice and picks the
        # copy whose CONTENTS equal the recorded hash, which is what the panel shards
        # need: the tree keeps every one of them in both panel_ckpt and panel_ckpt_v2,
        # so 24 declared inputs of probe_F_hlp_liq and 24 of panel_v2_manifest read as
        # absent while every one sat on disk unchanged. Neither step ever chooses by
        # walk order; when nothing resolves, the ambiguity is recorded and stands.
        picked, how, survivors = _choose_by_content(index[name], root, recorded, cache)
        if picked:
            found = os.path.join(root, picked)
            row["resolved_by"] = ("the only file of that name in the tree"
                                  if how == "unique" else
                                  "the one candidate whose contents equal the "
                                  "recorded hash")
        else:
            row["ambiguous_in"] = list(index[name])
            row["ambiguity_survives_hashing"] = survivors

    if found is None and external and name in external["index"]:
        # THE FIFTH STEP, ADDED 2026-08-05. Everything above searches INSIDE the tree,
        # and eleven inputs of this repository have never been inside it: four days of
        # the forward recording, the funding and spot pulls, the December trade archive,
        # the acquisition log and two written documents beside the tree. They
        # read absent from disk while all eleven lay on disk, hash-exact, which is a
        # count measuring the search this gate performed rather than the repository.
        #
        # The roots are declared in EXTERNAL_ROOTS, relative and optional, and only a
        # root that is a directory on this disk is in the index at all. The choice among
        # same-named candidates is the same content rule as the step above, called and
        # not copied: a file the artifact never read cannot be selected, here or there.
        picked, how, survivors = _choose_by_content(external["index"][name], root,
                                                    recorded, cache)
        if picked:
            found = os.path.join(root, picked)
            row["resolved_root"] = _declared_root_of(picked, external["present"])
            row["resolved_by"] = (
                "a declared root outside the tree"
                if how == "unique" else
                "a declared root outside the tree, chosen by contents")
            row["ambiguous_in"] = None
            row["ambiguity_survives_hashing"] = None
        else:
            row["ambiguous_in"] = sorted(set(row["ambiguous_in"] or [])
                                         | set(external["index"][name]))
            row["ambiguity_survives_hashing"] = survivors

    if not recorded:
        row["state"] = NO_HASH
        # Whether it is on disk NOW is worth recording even though it changes no
        # verdict: an input that was gone at write time and is present again can be
        # brought under this gate by rerunning its consumer, and one that is still gone
        # cannot. That is the difference between debt somebody can work off and a
        # limit of the tree.
        row["where"] = os.path.relpath(found, root).replace(os.sep, "/") if found \
            else None
        row["why"] = ("no hash was recorded, so the input was already absent when the "
                      "artifact was written" + (
                          "; it is on disk now, so rerunning the producer would put "
                          "this edge under the gate" if found else
                          "; it is still absent, so this edge cannot be checked at "
                          "all"))
        return row

    if found is None:
        row["state"] = ABSENT
        # WHICH DECLARED ROOT WAS MISSING IS PART OF THE ANSWER, NOT A FOOTNOTE. On a
        # checkout carrying the tree by itself, none of these roots exists, and eleven
        # inputs that are perfectly well on the author's disk cannot be found by
        # anything. That reader is owed the reason and the name of the place, because
        # the repair is theirs to make and it is a fetch rather than a recompute.
        note = external["note"] if external else (
            "the declared roots outside the tree were not searched on this run")
        row["declared_roots_missing"] = [row_["path"] for row_ in
                                         (external["missing"] if external
                                          else declared_roots())]
        if row["ambiguous_in"]:
            row["why"] = (
                f"a hash was recorded, so {name} was on disk when this artifact was "
                f"written, and {len(row['ambiguous_in'])} files of that name are now "
                f"reachable: {', '.join(row['ambiguous_in'][:4])}. The record keeps "
                f"only the basename, so it identifies none of them, and none of them "
                f"carries the recorded digest either, so choosing one would compare "
                f"this artifact against a file it may never have read. {note}")
        else:
            row["why"] = (
                f"a hash was recorded, so {name} was on disk when this artifact was "
                f"written, and none of the five places its name resolves to holds it "
                f"now: the producer's directory, the tree root, the tree by basename, "
                f"the tree by content, and the declared roots outside the tree. {note}. "
                f"The comparison cannot be made, which leaves the artifact "
                f"unverifiable rather than verified")
        return row

    current = _digest(found, cache)
    row["where"] = os.path.relpath(found, root).replace(os.sep, "/")
    row["on_disk_sha256"] = current
    row["on_disk_bytes"] = os.path.getsize(found)
    if current == recorded:
        row["state"] = MATCHES
        row["why"] = "the file this artifact was computed from is unchanged"
        return row

    # THE BYTES MOVED, WHICH IS NOT YET AN ANSWER. Until 2026-08-11 this was the end of
    # the road and every byte-difference was called a divergence, which reported eleven
    # consumers of six recomputed nodes as standing on figures that no longer existed
    # while not one figure had moved. What separates the two is judge_body, and
    # withholding the history there yields diverged_body_unknown rather than a pass.
    return judge_body(row, found, history)


def sweep(root, files, scripts, cache, index, external=None, history=None):
    """Judge every input record of every artifact in the population.

    Returns (edges, unreadable, no_inputs). `no_inputs` is kept apart from an artifact
    whose inputs all match: a file recording no input list at all is not clean, it is
    unasked, and eleven of the eighty-two are in that position today.
    """
    edges, unreadable, no_inputs = [], [], []
    for rel in files:
        path = os.path.join(root, rel)
        try:
            with open(path, encoding="utf-8", errors="replace") as handle:
                document = json.load(handle)
        except (OSError, ValueError) as exc:
            unreadable.append({"file": rel, "detail": str(exc)[:200]})
            continue
        meta = document.get(artifact.META_KEY) if isinstance(document, dict) else None
        meta = meta if isinstance(meta, dict) else {}
        records = meta.get("inputs")
        if not isinstance(records, list) or not records:
            no_inputs.append(rel)
            continue
        bases, producer, producer_rel = resolution_bases(meta, root, scripts)
        for record in records:
            if not isinstance(record, dict):
                continue
            row = judge_edge(rel, record, bases, root, cache, index, external,
                             history)
            row["producer"] = producer_rel or producer
            edges.append(row)
    return edges, unreadable, no_inputs


def ambiguous_names(edges):
    """The blind spot that is left, as a number and by name.

    Everything the three resolution steps cannot place, and the only reason left is a
    basename the tree holds more than once. It is reported and never gated: the fix is
    not in this gate but in the record, which would have to keep the directory it was
    given. Refusing to guess is what keeps this a false ALARM rather than a false
    match, and a false alarm costs somebody a look where a false match costs a
    published figure.
    """
    rows = {}
    for row in edges:
        if row["state"] == ABSENT and row["ambiguous_in"]:
            entry = rows.setdefault(row["input"],
                                    {"input": row["input"],
                                     "candidates": row["ambiguous_in"],
                                     "declared_by": []})
            entry["declared_by"].append(row["artifact"])
    for entry in rows.values():
        entry["declared_by"] = sorted(set(entry["declared_by"]))
    return [rows[name] for name in sorted(rows)]


def declared_debt_subjects(files, declared=DECLARED_DIVERGED_ARTIFACTS):
    """One row per declared debt entry: has it still got a subject, and where is it.

    THE QUESTION IS NOT WHETHER THE DEBT WAS REPAID. It is whether the line in this file
    still points at anything, which is a different question and the one nothing was
    asking. A repaid entry and a dead entry both drop out of the set of artifacts found
    standing on a moved input, so both are printed as repaid, and only one of the two is
    work somebody did.

    RESOLVED BY CONTENT AND NOT BY THE PATH THE ENTRY CARRIES. An entry whose declared
    path is not in the population is looked up again by BASENAME, and an artifact of the
    population carrying that name is the same document under a new address: the entry is
    reported moved, WITH the address, and it keeps whatever debt it had. Striking it
    instead would drop a live divergence out of the declared list and turn the next run
    red for a regression nobody caused. Only an entry no artifact of the population
    answers to at all is reported gone.

    The population is passed in rather than re-derived, so this rule and the sweep are
    counted over one set of files. Two derivations of one population is how four honest
    censuses of these artifacts returned four different numbers.
    """
    by_basename = {}
    for rel in files:
        by_basename.setdefault(os.path.basename(rel), []).append(rel)

    rows = []
    for rel in declared:
        if rel in files:
            rows.append({"declared": rel, "state": DEBT_MATCHED, "found_at": [rel],
                         "why": "this entry names an artifact of the population, so it "
                                "is a line that can still fire and can still be repaid"})
            continue
        elsewhere = sorted(by_basename.get(os.path.basename(rel), ()))
        if elsewhere:
            rows.append({
                "declared": rel, "state": DEBT_MOVED, "found_at": elsewhere,
                "why": f"no artifact of the population sits at this address, and "
                       f"{len(elsewhere)} carries the same basename: the file moved "
                       f"house and the entry did not move with it. Re-point the entry "
                       f"at {', '.join(elsewhere)}; do not strike it, because the debt "
                       f"it declares is judged at the new address and striking it "
                       f"would fail the next run for a regression nobody caused"})
            continue
        rows.append({
            "declared": rel, "state": DEBT_GONE, "found_at": [],
            "why": "no artifact of the population sits at this address and none carries "
                   "this basename anywhere, so this entry has no subject: it can never "
                   "fire and can never be repaid, and it is printed as repaid on every "
                   "run. Strike it, or say in this file what it is waiting for"})
    return rows


# =====================================================================
# CALIBRATION: ONE CASE THAT MUST FIRE, ONE THAT MUST STAY SILENT
#
# Run on every invocation rather than behind a flag, because a calibration nobody
# executes is a comment. Two halves, and they answer different questions on purpose.
#
# The fabricated half builds seven input records in a temporary directory, covering all
# five outcomes, each wrong in exactly one way. It settles whether the five outcomes are
# told apart, and it touches nothing in the tree.
#
# The live half settles whether the comparison itself works on real data: it takes one
# input record out of this run's own sweep, judges it as it stands, then judges it again
# with one hex digit of its recorded hash changed. Neither half can be emptied by
# anything the tree does, which is the property the previous version of this block did
# not have -- it named two artifacts, and the firing one was repaired out from under it.
# Both halves fail the run rather than reporting NOT ANSWERED: with nothing anchored on
# a live defect there is no longer a case that can decay honestly.
# =====================================================================

_FIXTURE_PRODUCER = "# a stand-in producer for the calibration of chk_input_freshness\n"


def _self_test_fixture(work, name, inputs):
    """One artifact with an input record made to order, in a temporary directory.

    THE NAME OF THIS FUNCTION CARRIES MEANING AND IS NOT FREE TO CHANGE. The build
    graph tells a build product from a calibration fixture by the name of the enclosing
    function, matching the prefixes in build.FIXTURE_SCOPES. Under any other name the
    graph reads the files written here as outputs of this check, goes looking for them
    in the tree, does not find them, and leaves a node permanently in "must run" for a
    file that exists only inside a directory this function's caller deletes.
    """
    document = {artifact.META_KEY: {
        "artifact_meta_version": artifact.SHAPE_VERSION,
        "results_file": name,
        "producer": {"script": "fixture_producer.py", "sha256": "0" * 64, "bytes": 1},
        "inputs": inputs,
        "scope": {"population": "fixture", "window": "fixture", "coins": "fixture"},
        artifact.VOLATILE_KEY: {"runtime_s": 0.0},
    }, "value": 1}
    with open(os.path.join(work, name), "w", encoding="utf-8") as handle:
        json.dump(document, handle)
    return name


def _self_test_fabricated(expect):
    """Five artifacts, one per outcome, each wrong in exactly one way."""
    with tempfile.TemporaryDirectory() as work:
        with open(os.path.join(work, "fixture_producer.py"), "w",
                  encoding="utf-8") as handle:
            handle.write(_FIXTURE_PRODUCER)
        source = os.path.join(work, "an_input.json")
        with open(source, "w", encoding="utf-8") as handle:
            handle.write('{"rows": 3}')
        true_hash = artifact.sha256_file(source)
        scripts = {"fixture_producer.py": "fixture_producer.py"}
        cache = {}

        # A file the third step must find, one directory down from both bases, and a
        # PAIR sharing one basename that it must refuse to resolve. The two together
        # are what separate a third step that closes the gap from one that guesses.
        os.mkdir(os.path.join(work, "one_level_down"))
        buried = os.path.join(work, "one_level_down", "a_buried_input.json")
        with open(buried, "w", encoding="utf-8") as handle:
            handle.write('{"rows": 5}')
        buried_hash = artifact.sha256_file(buried)
        for copy in ("first_copy", "second_copy"):
            os.mkdir(os.path.join(work, copy))
            with open(os.path.join(work, copy, "a_shared_name.npz"), "w",
                      encoding="utf-8") as handle:
                handle.write(copy)
        index = basename_index(work)

        cases = (
            ("an unchanged input reads matches", MATCHES,
             {"name": "an_input.json", "bytes": 11, "sha256": true_hash,
              "present": True}),
            ("a moved input reads diverged", DIVERGED,
             {"name": "an_input.json", "bytes": 11, "sha256": "1" * 64,
              "present": True}),
            ("a hashed input that is gone reads absent, not diverged", ABSENT,
             {"name": "a_deleted_input.npz", "bytes": 99, "sha256": "2" * 64,
              "present": True}),
            ("a local name with no hash reads no_hash_recorded, not absent", NO_HASH,
             {"name": "a_deleted_input.npz", "bytes": None, "sha256": None,
              "present": False}),
            ("a bucket key reads remote_address, not absent", REMOTE,
             {"name": "s3://an-archive/hourly/20251204/23.lz4", "bytes": None,
              "sha256": None, "present": False}),
            ("a name whose directory the record dropped is still found", MATCHES,
             {"name": "a_buried_input.json", "bytes": 11, "sha256": buried_hash,
              "present": True}),
            ("a basename the tree holds twice is refused, not guessed", ABSENT,
             {"name": "a_shared_name.npz", "bytes": 10, "sha256": "3" * 64,
              "present": True}),
        )
        for number, (label, want, record) in enumerate(cases):
            name = f"fixture_{number}_results.json"
            _self_test_fixture(work, name, [record])
            with open(os.path.join(work, name), encoding="utf-8") as handle:
                meta = json.load(handle)[artifact.META_KEY]
            bases, _p, _r = resolution_bases(meta, work, scripts)
            row = judge_edge(name, record, bases, work, cache, index)
            expect(label, row["state"] == want,
                   f"expected {want}, found {row['state']}")
            expect(f"{label} -- and it names the place",
                   bool(row["why"]) and (row["where"] or row["state"] in
                                         (ABSENT, NO_HASH, REMOTE)) is not None,
                   f"why={row['why'][:56]}...")

        # The refusal must say WHY it refused, or the reader cannot tell a name the
        # tree does not hold from one it holds twice, and those need opposite fixes.
        ambiguous = judge_edge("fixture_6_results.json", cases[6][2],
                               [(work, "the tree root")], work, cache, index)
        expect("the refused name reports both candidates",
               len(ambiguous["ambiguous_in"] or ()) == 2,
               f"candidates {ambiguous['ambiguous_in']}")

        # The resolution used above must be the one artifact.py records with, or this
        # gate is comparing against a rule the producers never followed. Asserted
        # rather than assumed, on a file both can see.
        mine = _digest(source, cache)
        theirs = artifact.input_record("an_input.json", work)
        expect("this gate's resolution agrees with artifact.input_record",
               theirs["present"] and theirs["sha256"] == mine,
               f"{str(theirs['sha256'])[:12]} against {mine[:12]}")

    _self_test_fifth_step(expect)
    _self_test_body(expect)


class _FixtureHistory:
    """A stand-in for History holding byte-states it was handed, rather than git's.

    CALIBRATION 1 has to be able to produce every answer judge_body can give, including
    the one where the recorded state is nowhere to be found, and it has to run on a
    checkout that may have no git in it at all. So the lookup is stood in for here and
    only here. The live half puts the real History to the real history of this
    repository, which is the half that would notice if the git side broke, and the two
    together cover what neither covers alone.
    """

    def __init__(self, states):
        self._states = dict(states)
        self.note = "a fixture history built for this calibration"
        self.n_blobs_hashed = len(self._states)

    def usable(self):
        return True

    def find(self, basename, digest):
        data = self._states.get(digest)
        return (data, "in the fixture history") if data else (None, None)


def _self_test_body(expect):
    """The second sign, over every answer it can give, on documents built to order.

    SIX CASES AND THEY ARE THREE OPPOSING PAIRS, because this is the widest thing this
    gate does -- it is the one place where a difference the old comparison called a
    divergence is allowed not to be one -- and a repair that made everything silent
    would look exactly like a repair that worked.

    MUST STAY SILENT: an input rewritten with the same numbers under a moved run clock
    and a moved producer hash, which is the case measured 11 times on 2026-08-11.

    MUST FIRE, and each for a different reason, because a single firing case cannot tell
    a comparison that works from one that fires on everything: a moved number; the same
    numbers under a moved settings fingerprint, which is a different question with the
    same digits; a recorded state no history holds; a history withheld altogether; and
    an input with no _meta at all, where the bytes are the content and the repair must
    not reach.
    """
    with tempfile.TemporaryDirectory() as work:
        with open(os.path.join(work, "fixture_producer.py"), "w",
                  encoding="utf-8") as handle:
            handle.write(_FIXTURE_PRODUCER)
        scripts = {"fixture_producer.py": "fixture_producer.py"}

        def document(numbers, meta_extra):
            meta = {"artifact_meta_version": artifact.SHAPE_VERSION,
                    "results_file": "an_input_results.json",
                    "producer": {"script": "p.py", "sha256": "a" * 64, "bytes": 1},
                    "inputs": [], "scope": {"population": "f", "window": "f",
                                            "coins": "f"},
                    artifact.VOLATILE_KEY: {"runtime_s": 1.0}}
            meta.update(meta_extra)
            return json.dumps({artifact.META_KEY: meta, "by_coin": numbers},
                              indent=1).encode("utf-8")

        # What is on disk now, and three earlier byte-states of it. Every one of the
        # three differs from what is on disk as BYTES; they differ from each other in
        # exactly one thing apiece, which is what makes the answers below attributable.
        now = document([0.1965, 2], {})
        same_numbers = document([0.1965, 2], {
            artifact.VOLATILE_KEY: {"runtime_s": 99.0},
            "producer": {"script": "p.py", "sha256": "b" * 64, "bytes": 2}})
        moved_numbers = document([0.1628, 2], {
            artifact.VOLATILE_KEY: {"runtime_s": 99.0}})
        moved_setting = document([0.1965, 2], {
            artifact.VOLATILE_KEY: {"runtime_s": 99.0},
            "settings_fingerprint": {"settings_module": "settings.py",
                                     "sha256": "c" * 64}})

        target = os.path.join(work, "an_input_results.json")
        with open(target, "wb") as handle:
            handle.write(now)
        script_input = os.path.join(work, "a_producer_input.py")
        with open(script_input, "w", encoding="utf-8") as handle:
            handle.write("# the version on disk now\n")

        def sha(raw):
            return hashlib.sha256(raw).hexdigest()

        older_script = b"# an older version\n"
        history = _FixtureHistory({sha(same_numbers): same_numbers,
                                   sha(moved_numbers): moved_numbers,
                                   sha(moved_setting): moved_setting,
                                   sha(older_script): older_script})
        index = basename_index(work)

        cases = (
            ("MUST STAY SILENT: a rewrite that moved the run clock and the producer "
             "hash and no number", REWRITTEN,
             {"name": "an_input_results.json", "bytes": len(same_numbers),
              "sha256": sha(same_numbers), "present": True}, history),
            ("MUST FIRE: one moved number reads diverged", DIVERGED,
             {"name": "an_input_results.json", "bytes": len(moved_numbers),
              "sha256": sha(moved_numbers), "present": True}, history),
            ("MUST FIRE: the same numbers under a moved settings fingerprint read "
             "diverged", DIVERGED,
             {"name": "an_input_results.json", "bytes": len(moved_setting),
              "sha256": sha(moved_setting), "present": True}, history),
            ("MUST FIRE: a recorded state no history holds reads "
             "diverged_body_unknown, never matches", UNKNOWN,
             {"name": "an_input_results.json", "bytes": 11, "sha256": "7" * 64,
              "present": True}, history),
            ("MUST FIRE: withholding the history reads diverged_body_unknown rather "
             "than passing", UNKNOWN,
             {"name": "an_input_results.json", "bytes": len(same_numbers),
              "sha256": sha(same_numbers), "present": True}, None),
            ("MUST FIRE: an input with no _meta is untouched by the repair and stays "
             "diverged", DIVERGED,
             {"name": "a_producer_input.py", "bytes": 20,
              "sha256": sha(b"# an older version\n"), "present": True}, history),
        )
        for number, (label, want, record, hist) in enumerate(cases):
            cache = {}
            name = f"fixture_body_{number}_results.json"
            _self_test_fixture(work, name, [record])
            with open(os.path.join(work, name), encoding="utf-8") as handle:
                meta = json.load(handle)[artifact.META_KEY]
            bases, _p, _r = resolution_bases(meta, work, scripts)
            row = judge_edge(name, record, bases, work, cache, index, None, hist)
            expect(label, row["state"] == want,
                   f"expected {want}, found {row['state']}: {row['why'][:96]}")

        # BOTH SIGNS, AND THE FIRST ONE UNTOUCHED. The repair is only safe if it added a
        # second comparison rather than replaced the first: a reader of any edge must be
        # able to see the whole-file hashes that moved AND the content hashes that did
        # not. Checked on the silent case, where all four are filled.
        cache = {}
        record = cases[0][2]
        _self_test_fixture(work, "fixture_body_signs_results.json", [record])
        with open(os.path.join(work, "fixture_body_signs_results.json"),
                  encoding="utf-8") as handle:
            meta = json.load(handle)[artifact.META_KEY]
        bases, _p, _r = resolution_bases(meta, work, scripts)
        silent = judge_edge("fixture_body_signs_results.json", record, bases, work,
                            cache, index, None, history)
        expect("the silent case keeps BOTH signs: two whole-file hashes that differ "
               "and two content hashes that agree",
               (silent["recorded_sha256"] != silent["on_disk_sha256"]
                and silent["recorded_body_sha256"] == silent["on_disk_body_sha256"]
                and bool(silent["recorded_body_sha256"])),
               f"file {str(silent['recorded_sha256'])[:8]}/"
               f"{str(silent['on_disk_sha256'])[:8]}, content "
               f"{str(silent['recorded_body_sha256'])[:8]}/"
               f"{str(silent['on_disk_body_sha256'])[:8]}")
        expect("and it names which _meta fields moved, so a reader can check the "
               "allow-list rather than trust it",
               sorted(silent["meta_fields_that_moved"] or []) ==
               ["producer", artifact.VOLATILE_KEY],
               f"moved {silent['meta_fields_that_moved']}")

        # The allow-list must be read as a list of what MAY move, not of what does. A
        # settings fingerprint that moved is named in the sentence, or the reader of a
        # red run cannot tell which of the two divergences they are looking at.
        cache = {}
        record = cases[2][2]
        setting = judge_edge("fixture_body_signs_results.json", record, bases, work,
                             cache, index, None, history)
        expect("the settings case says WHICH field put it outside the allow-list",
               "settings_fingerprint" in setting["why"],
               f"why={setting['why'][:96]}")


def _self_test_fifth_step(expect):
    """The fifth step, on a fixture tree with a sibling root beside it and one missing.

    FOUR CASES AND THEY ARE TWO OPPOSING PAIRS, because one reference point cannot tell
    a resolver that is too wide from one that is too narrow, and this step is the widest
    thing in the file: it is allowed to look outside the repository. It must find what
    is genuinely there, refuse what is not, prefer content to walk order, and say WHICH
    declared root was missing when it comes back empty.

    Built rather than named, and built here rather than on the live tree, so that it
    also runs for the reader who cloned this repository by itself and has neither
    ../02_data on their disk. The live half of the same question is in
    CALIBRATION 2, where the roots are withheld from a real input record.
    """
    with tempfile.TemporaryDirectory() as parent:
        tree = os.path.join(parent, "tree")
        beside = os.path.join(parent, "beside_the_tree")
        os.mkdir(tree)
        os.mkdir(beside)
        with open(os.path.join(tree, "fixture_producer.py"), "w",
                  encoding="utf-8") as handle:
            handle.write(_FIXTURE_PRODUCER)

        neighbour = os.path.join(beside, "a_neighbour_input.parquet")
        with open(neighbour, "w", encoding="utf-8") as handle:
            handle.write("data that never lived inside the tree")
        neighbour_hash = artifact.sha256_file(neighbour)

        # TWO COPIES OF ONE NAME, AND THE MATCHING ONE SORTS SECOND. A resolver that
        # took the first candidate the walk offered would read this pair as diverged
        # while the file the producer actually read sits right there. The trap is set
        # deliberately: "aa_first" sorts before "bb_second", and the record's hash is
        # the second one's.
        for folder, body in (("aa_first", "the copy the artifact did NOT read"),
                             ("bb_second", "the copy the artifact DID read")):
            os.mkdir(os.path.join(beside, folder))
            with open(os.path.join(beside, folder, "a_twice_held_name.npz"), "w",
                      encoding="utf-8") as handle:
                handle.write(body)
        twin_hash = artifact.sha256_file(
            os.path.join(beside, "bb_second", "a_twice_held_name.npz"))

        specs = (
            {"path": "../beside_the_tree", "holds": "a fixture neighbour directory",
             "why_it_is_outside": "it stands in for the data directory"},
            {"path": "../not_on_this_disk", "holds": "a root that does not exist",
             "why_it_is_outside": "it stands in for a checkout that carries the tree "
                                  "alone"},
        )
        present, missing, index = external_roots(tree, specs)
        roots = pack_roots(present, missing, index)
        scripts = {"fixture_producer.py": "fixture_producer.py"}
        tree_index = basename_index(tree)
        cache = {}

        expect("a declared root that is not on disk is reported missing, not skipped",
               [row["path"] for row in missing] == ["../not_on_this_disk"]
               and [row["path"] for row in present] == ["../beside_the_tree"],
               f"present {[r['path'] for r in present]}, missing "
               f"{[r['path'] for r in missing]}")

        def judge(record, with_roots):
            name = "fixture_fifth_results.json"
            _self_test_fixture(tree, name, [record])
            with open(os.path.join(tree, name), encoding="utf-8") as handle:
                meta = json.load(handle)[artifact.META_KEY]
            bases, _p, _r = resolution_bases(meta, tree, scripts)
            return judge_edge(name, record, bases, tree, cache, tree_index, with_roots)

        # MUST STAY SILENT. It is outside the tree, so the four steps before this one
        # cannot see it; it is under a declared root that exists, so this one can.
        outside = judge({"name": "a_neighbour_input.parquet", "bytes": 38,
                         "sha256": neighbour_hash, "present": True}, roots)
        expect("MUST STAY SILENT: an input under a declared root that exists reads "
               "matches",
               outside["state"] == MATCHES, f"found {outside['state']}")
        expect("and it names the root it came from rather than only the path",
               outside["resolved_root"] == "../beside_the_tree"
               and outside["resolved_by"] == "a declared root outside the tree",
               f"root {outside['resolved_root']}, by {outside['resolved_by']}")

        # MUST FIRE, ONE. Nowhere in the tree and nowhere under any declared root.
        nowhere = judge({"name": "a_name_that_is_nowhere.npz", "bytes": 7,
                         "sha256": "4" * 64, "present": True}, roots)
        expect("MUST FIRE: an input under no root at all reads absent_from_disk",
               nowhere["state"] == ABSENT, f"found {nowhere['state']}")
        expect("and the reason names the declared root that is not on this disk",
               "../not_on_this_disk" in nowhere["why"]
               and nowhere["declared_roots_missing"] == ["../not_on_this_disk"],
               f"missing {nowhere.get('declared_roots_missing')}")

        # MUST FIRE, TWO, AND THIS IS THE ONE THE COUNT DEPENDS ON. Withhold the roots
        # and the very record that read matches must read absent and say which roots
        # were not searched. A step that made a real absence disappear from the count
        # would pass the first three cases and fail this one.
        withheld = judge({"name": "a_neighbour_input.parquet", "bytes": 38,
                          "sha256": neighbour_hash, "present": True},
                         withheld_roots(specs))
        expect("MUST FIRE: the same input reads absent_from_disk when no declared root "
               "is on disk",
               withheld["state"] == ABSENT, f"found {withheld['state']}")
        expect("and that answer names both declared roots rather than going quiet",
               sorted(withheld["declared_roots_missing"] or []) ==
               ["../beside_the_tree", "../not_on_this_disk"],
               f"missing {withheld.get('declared_roots_missing')}")
        expect("the pair differs in the roots on disk and in nothing about the record",
               (withheld["input"] == outside["input"]
                and withheld["recorded_sha256"] == outside["recorded_sha256"]
                and withheld["recorded_bytes"] == outside["recorded_bytes"]),
               f"{withheld['input']} at {str(withheld['recorded_sha256'])[:12]}")

        # CONTENT, NOT WALK ORDER. Both copies are under the same present root and the
        # matching one sorts second, so a resolver choosing by position reads diverged.
        twin = judge({"name": "a_twice_held_name.npz", "bytes": 31,
                      "sha256": twin_hash, "present": True}, roots)
        expect("two copies under one root resolve by CONTENT, not by walk order",
               twin["state"] == MATCHES
               and (twin["where"] or "").endswith("bb_second/a_twice_held_name.npz"),
               f"{twin['state']} at {twin['where']}")
        expect("and the run says so, rather than reporting it as a plain resolution",
               twin["resolved_by"] == "a declared root outside the tree, chosen by "
                                      "contents",
               f"by {twin['resolved_by']}")

        # And the refusal survives outside the tree too: no candidate carrying the
        # recorded digest means nothing is chosen, exactly as inside it.
        neither = judge({"name": "a_twice_held_name.npz", "bytes": 31,
                         "sha256": "5" * 64, "present": True}, roots)
        expect("two copies and neither matching the record resolve to nothing, not to "
               "the first",
               neither["state"] == ABSENT
               and len(neither["ambiguous_in"] or ()) == 2
               and neither["ambiguity_survives_hashing"] == 0,
               f"{neither['state']}, candidates {neither['ambiguous_in']}")


def _live_anchor(edges):
    """The live input record this run's pair is built on, and the set it came from.

    Chosen out of the run's own sweep by CALIBRATION_ANCHOR_RULE rather than written
    into this file as a name. A name here is a hostage to the tree: the case it stands
    on gets repaired and the leg goes vacuous with it, which is what happened to the
    version of this calibration that named two artifacts. This choice empties only if
    the tree holds no verifiable input record whatever, and that condition fails the
    run rather than passing quietly.

    Sorted rather than taken as it comes, so two runs over one tree pick the same
    record and a reader can repeat the case by hand.
    """
    matched = sorted((row for row in edges
                      if row["state"] == MATCHES and row["recorded_sha256"]
                      and row["where"]),
                     key=lambda row: (row["artifact"], row["input"]))
    return (matched[0] if matched else None), len(matched)


def _one_hex_digit_changed(digest):
    """The same hash with its leading hex digit changed, and nothing else.

    The fault has to be the SMALLEST one this gate is meant to notice, or the case
    proves only that it can tell a hash from a sentence. Keeping the length and the
    alphabet matters for the same reason: nothing downstream may reject this string for
    any property other than the comparison under test.
    """
    return ("1" if digest[0] != "1" else "0") + digest[1:]


def _live_body_anchors(edges, root, history, limit=25):
    """Two real earlier byte-states of live inputs: one body-equal, one body-different.

    Returns (silent, firing, scanned), where each is None or a dict naming the edge, the
    earlier state and what it should read. Both are drawn from the repository's own
    history by the rule in CALIBRATION_BODY_ANCHOR_RULE rather than written down as
    names, for the reason this file has already paid for once: a case that names an
    artifact empties the day somebody repairs that artifact, and what is left is a green
    gate nobody has seen find anything.

    The scan stops as soon as both halves are in hand, and it stops at `limit` candidate
    inputs whatever it has, so the calibration cannot turn into a walk of the history of
    every input. Measured on 2026-08-11: the first candidate examined supplied both
    halves, over populations of 72 and 98 records that could have supplied them.
    """
    silent = firing = None
    scanned = 0
    for row in sorted((edge for edge in edges
                       if edge["where"] and edge["recorded_sha256"]),
                      key=lambda edge: (edge["artifact"], edge["input"])):
        if silent and firing:
            break
        if scanned >= limit:
            break
        path = os.path.join(root, row["where"])
        try:
            now_body, _meta_now, _why = content_hash_on_disk(path)
        except OSError:
            continue
        if now_body is None:
            continue
        basename = os.path.basename(row["where"])
        states = history.digests(basename)
        if not states:
            continue
        scanned += 1
        cand_silent = cand_firing = None
        on_disk = _digest(path, {})
        for digest in sorted(states):
            if digest == on_disk:
                continue
            raw = history.blob(states[digest])
            if raw is None:
                continue
            then_body, then_meta, _why = body_digest(raw)
            if then_body is None:
                continue
            if then_body != now_body and not cand_firing:
                cand_firing = {"row": row, "sha256": digest, "expect": DIVERGED,
                               "content": f"{then_body[:12]} against {now_body[:12]}"}
            elif then_body == now_body and not cand_silent:
                # It only stays silent if what moved inside _meta is on the allow-list;
                # picking a state that moved a setting would build a case that must
                # FIRE and assert that it does not, which is a calibration proving the
                # opposite of what it says.
                moved = [key for key in set(then_meta) | set(_meta_now)
                         if then_meta.get(key) != _meta_now.get(key)]
                if all(key in REWRITE_MAY_MOVE for key in moved):
                    cand_silent = {"row": row, "sha256": digest, "expect": REWRITTEN,
                                   "content": f"{now_body[:12]} on both sides",
                                   "meta_moved": sorted(moved)}
        # BOTH HALVES COME FROM ONE CANDIDATE OR NEITHER IS TAKEN. The assertion this
        # pair feeds requires the two halves to stand on one artifact, one input name
        # and one file on disk, because that is the only shape in which their two
        # answers say something about the comparison rather than about two files.
        # Filling the halves independently -- silent from the first candidate that
        # offers one, firing from a later candidate -- builds a pair that cannot pass
        # its own axis check, and on 2026-08-29 it did exactly that: the silent half
        # landed on quoters/as_quoter_results.json and the firing half on
        # checks/NEUTRAL_EDITS.json, and the gate failed one assertion of 59 for two
        # days while every count it reported was correct. Requiring one candidate to
        # supply both is STRICTER, not looser: where no single input has both an
        # earlier body-equal and an earlier body-different state, the pair reports
        # itself unexercised, and that branch asserts the repair cleared nothing.
        if cand_silent and cand_firing:
            silent, firing = cand_silent, cand_firing
    return silent, firing, scanned


def _first_number_moved(node):
    """A deep copy of `node` with its first numeric leaf moved by one, or None."""
    if isinstance(node, bool):
        return None
    if isinstance(node, (int, float)):
        return node + 1
    if isinstance(node, dict):
        for key in sorted(node):
            moved = _first_number_moved(node[key])
            if moved is not None:
                return {**node, key: moved}
        return None
    if isinstance(node, list):
        for i, value in enumerate(node):
            moved = _first_number_moved(value)
            if moved is not None:
                return node[:i] + [moved] + node[i + 1:]
        return None
    return None


def _self_test_handmade_body_anchors(edges, root, workdir):
    """The two earlier byte-states, made by hand from a live input and committed to a
    temporary git, when this repository's own history holds none.

    WHY THIS EXISTS. The open repository's history starts at its own first commit, so
    no input has an earlier state in it, and the live pair above could only report
    itself unexercised -- while edges that resolved through objects git still holds
    loose read rewritten_same_numbers, which the unexercised branch rightly refuses.
    Waiting for history to supply a case is waiting on the past. So the earlier states
    are made from the real file on disk: one with only its run clock moved, which must
    read as a rewrite, and one with its first number moved by one, which must read as
    a divergence. Both are committed under the input's own basename in a git created
    in `workdir`, and that git is the history the two judgements consult. The file on
    disk, the artifact and the input record are the live ones; only the recorded
    byte-state is made.

    Returns (silent, firing, history) or (None, None, None).
    """
    for row in sorted((edge for edge in edges
                       if edge["where"] and edge["recorded_sha256"]
                       and edge["state"] == MATCHES),
                      key=lambda edge: (edge["artifact"], edge["input"])):
        path = os.path.join(root, row["where"])
        try:
            if os.path.getsize(path) > MAX_BODY_BYTES:
                continue
            raw = _raw_on_disk(path)
            document = json.loads(raw.decode("utf-8"))
        except (OSError, ValueError, UnicodeDecodeError):
            continue
        if not isinstance(document, dict):
            continue
        meta = document.get(artifact.META_KEY)
        if not isinstance(meta, dict) or not isinstance(meta.get(artifact.VOLATILE_KEY),
                                                         dict):
            continue
        body = {k: v for k, v in document.items() if k != artifact.META_KEY}
        moved_body = _first_number_moved(body)
        if moved_body is None:
            continue
        clock = dict(meta[artifact.VOLATILE_KEY], finished_utc="2000-01-01T00:00:00Z")
        silent_doc = {**document, artifact.META_KEY: {**meta,
                                                      artifact.VOLATILE_KEY: clock}}
        firing_doc = {**moved_body, artifact.META_KEY: meta}
        silent_raw = (json.dumps(silent_doc, indent=2) + "\n").encode("utf-8")
        firing_raw = (json.dumps(firing_doc, indent=2) + "\n").encode("utf-8")
        name = os.path.basename(row["where"])

        def git(*args):
            return subprocess.run(["git", "-C", workdir, *args], capture_output=True,
                                  check=False)

        if git("init", "-q").returncode:
            return None, None, None
        # Written into git's object store through git itself, so no file is created in
        # the temporary directory and the build's I/O census has nothing to resolve.
        for i, data in enumerate((silent_raw, firing_raw)):
            made = subprocess.run(["git", "-C", workdir, "hash-object", "-w", "--stdin"],
                                  input=data, capture_output=True, check=False)
            oid = made.stdout.decode().strip()
            if made.returncode or not oid:
                return None, None, None
            if git("update-index", "--add", "--cacheinfo",
                   f"100644,{oid},{name}").returncode:
                return None, None, None
            if git("-c", "user.name=calibration", "-c", "user.email=calibration@local",
                   "commit", "-q", "-m", f"state {i}").returncode:
                return None, None, None
        now_body = body_digest(raw)[0]
        silent = {"row": row, "sha256": hashlib.sha256(silent_raw).hexdigest(),
                  "expect": REWRITTEN, "content": f"{now_body[:12]} on both sides",
                  "meta_moved": [artifact.VOLATILE_KEY]}
        firing = {"row": row, "sha256": hashlib.sha256(firing_raw).hexdigest(),
                  "expect": DIVERGED,
                  "content": f"{body_digest(firing_raw)[0][:12]} against "
                             f"{now_body[:12]}"}
        return silent, firing, History(workdir)
    return None, None, None


def _self_test_live_body(edges, root, scripts, index, external, history, expect):
    """The second sign, on two byte-states this repository really held.

    THE AXIS IS THE RECORDED BYTE-STATE AND NOTHING ELSE MOVES. Same artifact, same
    input name, same file on disk, same resolution step; the two halves differ in which
    earlier version of that file the record points at, and they must come out
    rewritten_same_numbers and diverged respectively. A comparison keyed on the file
    rather than on the content cannot produce those two answers in one run.

    It reports itself as not exercised, without failing the run, in exactly one state:
    a checkout where the history holds no earlier state of any input -- no git, a
    shallow clone, or a tree whose artifacts have never been committed. That is not a
    silent pass, and it is asserted as such: in that same state the repair itself
    resolves nothing, every input whose bytes moved reads diverged_body_unknown, and the
    gate is stricter than it was before the repair rather than looser. The two facts are
    checked together below, because "the case did not run" is only acceptable while "the
    feature cannot fire either" holds with it.
    """
    silent_case, firing_case, scanned = _live_body_anchors(edges, root, history)
    chosen_by = CALIBRATION_BODY_ANCHOR_RULE
    workdir = None
    if not (silent_case and firing_case):
        workdir = tempfile.mkdtemp(prefix="freshness_handmade_history_")
        silent_case, firing_case, made = _self_test_handmade_body_anchors(
            edges, root, workdir)
        if made is not None:
            history = made
            chosen_by = ("HANDMADE: the first matched JSON input with a run clock and a "
                         "number, in sorted order; its two earlier states were made "
                         "from the file on disk and committed to a temporary git, "
                         "because this repository's history holds no earlier state")
            print("    [ hand ] this repository's history holds no earlier state of a "
                  "live input; the pair is made by hand in a temporary git")
    try:
        return _self_test_live_body_pair(edges, root, scripts, index, external,
                                         history, expect, silent_case, firing_case,
                                         scanned, chosen_by)
    finally:
        if workdir:
            shutil.rmtree(workdir, ignore_errors=True)


def _self_test_live_body_pair(edges, root, scripts, index, external, history, expect,
                              silent_case, firing_case, scanned, chosen_by):
    """The body of _self_test_live_body, once its two cases are in hand or not."""
    if not (silent_case and firing_case):
        moved = [row for row in edges if row["state"] in NOT_STANDING_ON_WHAT_IT_READ]
        rewritten = [row for row in edges if row["state"] == REWRITTEN]
        print(f"    [ -- ] the second sign is not exercised on live data: "
              f"{scanned} input(s) examined, "
              f"{'a body-equal' if silent_case else 'no body-equal'} and "
              f"{'a body-different' if firing_case else 'no body-different'} earlier "
              f"state found")
        expect("where the second sign cannot be exercised it has also cleared nothing",
               not rewritten,
               f"{len(rewritten)} edge(s) read {REWRITTEN} on a run where the "
               f"calibration for that state could not be built, which would be a "
               f"repair certifying what it cannot demonstrate; {len(moved)} edge(s) "
               f"counted as debt")
        return {"exercised": False,
                "n_inputs_examined": scanned,
                "why": "this repository's history holds no earlier byte-state of any "
                       "input this run resolved, which is a checkout without git, a "
                       "shallow clone, or a tree whose artifacts were never committed. "
                       "In that state the repair resolves nothing either, so the gate "
                       "is stricter than before it and not looser",
                "and_it_cleared": len(rewritten)}

    out = {}
    for half, case in (("silent", silent_case), ("firing", firing_case)):
        row = case["row"]
        record = {"name": row["input"], "bytes": row["recorded_bytes"],
                  "sha256": case["sha256"], "present": True}
        meta = artifact.read_meta(os.path.join(root, row["artifact"]))
        bases, _p, _r = resolution_bases(meta, root, scripts)
        judged = judge_edge(row["artifact"], record, bases, root, {}, index, external,
                            history)
        where = f"{row['artifact']} -> _meta.inputs -> {row['input']}"
        print(f"    anchor  : {where}")
        print(f"              at the earlier state {case['sha256'][:12]}, content "
              f"{case['content']}")
        made = "a handmade" if chosen_by.startswith("HANDMADE") else "a real"
        expect(f"{'MUST STAY SILENT' if half == 'silent' else 'MUST FIRE'}: {made} "
               f"earlier state of a live input whose content "
               f"{'agrees with' if half == 'silent' else 'differs from'} the file on "
               f"disk reads {case['expect']}",
               judged["state"] == case["expect"],
               f"expected {case['expect']}, found {judged['state']} at {where}: "
               f"{judged['why'][:96]}")
        out[half] = {"artifact": row["artifact"], "input": row["input"],
                     "resolved_to": row["where"],
                     "earlier_state": case["sha256"],
                     "read": judged["state"],
                     "content": case["content"]}
        out[half + "_row"] = judged

    a, b = out["silent_row"], out["firing_row"]
    # HELD EQUAL, MEASURED RATHER THAN ASSUMED, exactly as for the pair above. If the
    # two halves stood on different files or different artifacts the two answers would
    # say nothing about the comparison, only about the two files.
    expect("the two halves stand on one artifact, one input name and one file on disk",
           (a["artifact"] == b["artifact"] and a["input"] == b["input"]
            and a["where"] == b["where"] and a["resolved_by"] == b["resolved_by"]
            and a["on_disk_sha256"] == b["on_disk_sha256"]
            and a["on_disk_body_sha256"] == b["on_disk_body_sha256"]),
           f"{a['where']} against {b['where']}")
    expect("one file on disk reads a rewrite under one earlier state and a divergence "
           "under another, in one run",
           a["state"] == REWRITTEN and b["state"] == DIVERGED,
           f"{a['state']} against {b['state']} at {a['where']}")
    expect("the silent half keeps both signs and the firing half shows the content "
           "hashes that differ",
           (a["recorded_body_sha256"] == a["on_disk_body_sha256"]
            and b["recorded_body_sha256"] != b["on_disk_body_sha256"]
            and a["recorded_sha256"] != a["on_disk_sha256"]),
           f"silent content {str(a['recorded_body_sha256'])[:8]}/"
           f"{str(a['on_disk_body_sha256'])[:8]}, firing content "
           f"{str(b['recorded_body_sha256'])[:8]}/"
           f"{str(b['on_disk_body_sha256'])[:8]}")

    return {"exercised": True,
            "chosen_by": chosen_by,
            "n_inputs_examined": scanned,
            "silent": out["silent"],
            "firing": out["firing"],
            "meta_fields_the_silent_half_moved": silent_case.get("meta_moved"),
            "held_equal": ["artifact", "input", "where", "resolved_by",
                           "on_disk_sha256", "on_disk_body_sha256"]}


def _self_test_live(edges, root, scripts, cache, index, external, history, expect):
    """One live input record, judged as it stands and again with its hash corrupted.

    Returns what the pair was built on, so the results file records which record this
    run's calibration stood on and what each half answered. Returns None when the tree
    offers nothing to build it from, which is a failure and is asserted as one.
    """
    anchor, population = _live_anchor(edges)
    print(f"    anchor  : {CALIBRATION_ANCHOR_RULE},")
    print(f"              over a population of {population} such records of "
          f"{len(edges)} judged this run")
    if anchor is None:
        expect("the tree offers a matched input record to build the pair on",
               False,
               f"expected at least 1, found 0 of {len(edges)} input records reading "
               f"{MATCHES} with a recorded hash and a file resolved on disk; neither "
               f"half can be built, so this gate has not been exercised at all")
        return None

    where = f"{anchor['artifact']} -> _meta.inputs -> {anchor['input']}"
    print(f"              {where}")
    meta = artifact.read_meta(os.path.join(root, anchor["artifact"]))
    bases, _p, _r = resolution_bases(meta, root, scripts)

    # The record as the producer wrote it, rebuilt from what the sweep read out of the
    # artifact, and the same record with one digit moved. Both go back through
    # judge_edge, which is the function that decides on live data: a calibration that
    # reimplemented the comparison would be blind to every change made to it.
    silent_record = {"name": anchor["input"], "bytes": anchor["recorded_bytes"],
                     "sha256": anchor["recorded_sha256"], "present": True}
    firing_record = dict(silent_record,
                         sha256=_one_hex_digit_changed(anchor["recorded_sha256"]))
    silent = judge_edge(anchor["artifact"], silent_record, bases, root, cache, index,
                        external, history)
    fires = judge_edge(anchor["artifact"], firing_record, bases, root, cache, index,
                       external, history)

    expect("MUST STAY SILENT: a live input record, unaltered, reads matches",
           silent["state"] == MATCHES,
           f"expected {MATCHES}, found {silent['state']} at {where}")
    # WHICH OF THE TWO DEBT STATES IT MUST READ DEPENDS ON THE ANCHOR, AND IT IS
    # COMPUTED FROM THE FILE RATHER THAN READ OFF THE VERDICT. One hex digit moved gives
    # a byte-state that never existed anywhere. If the anchor is a results file the
    # document behind that state cannot be recovered, so whether the numbers moved is
    # unanswerable and the edge must read diverged_body_unknown -- which is the live
    # case for the rule that an unanswerable edge is counted as debt and never as a
    # pass. If the anchor is a producer script or an array there is no separable content
    # at all, the bytes ARE the content, and the honest answer is a plain divergence
    # with no history consulted. Both are the gate firing; asserting only one of them
    # would make this leg fail whenever the sweep happened to sort a script first, which
    # is what it did on 2026-08-11 with build.py.
    anchor_content = content_hash_on_disk(os.path.join(root, anchor["where"]))[0]
    expect_fire = UNKNOWN if anchor_content else DIVERGED
    kind = ("carries a _meta block, so a byte-state that never existed leaves the "
            "question unanswerable" if anchor_content else
            "carries no _meta block, so its bytes are its content")
    print(f"              the anchor {kind}:")
    print(f"              this half must read {expect_fire}")
    expect(f"MUST FIRE: the same record with one hex digit of its hash changed reads "
           f"{expect_fire}, which is counted as debt and never as a pass",
           fires["state"] == expect_fire,
           f"expected {expect_fire}, found {fires['state']} at {where}")
    expect("and both debt states are inside the count the artifact rule is armed on",
           UNKNOWN in NOT_STANDING_ON_WHAT_IT_READ
           and DIVERGED in NOT_STANDING_ON_WHAT_IT_READ,
           f"armed on {NOT_STANDING_ON_WHAT_IT_READ}")
    expect("the firing half names both hashes and the file it compared",
           bool(fires["recorded_sha256"] and fires["on_disk_sha256"]
                and fires["where"]),
           f"recorded {str(fires['recorded_sha256'])[:12]}, on disk "
           f"{str(fires['on_disk_sha256'])[:12]}, at {fires['where']}")

    # HELD EQUAL, MEASURED RATHER THAN ASSUMED. Two arms are a comparison only if
    # exactly one declared thing separates them. Here the axis is the recorded hash;
    # the verdict and the sentence explaining it are its consequences; everything else
    # -- the file resolved, the step that resolved it, the digest read off disk, the
    # size and the presence flag -- has to be identical, and it is checked leaf by leaf
    # rather than trusted, because a difference nobody measured is the one that ruins
    # the inference.
    # on_disk_body_sha256 joined this set on 2026-08-11 and it is a consequence rather
    # than a second axis: the second sign of the file on disk is only read when the
    # first sign moved, so the silent half never takes it and the firing half does.
    # Reading it on every edge would mean loading every input into memory, and the
    # inputs of this tree include arrays of several hundred megabytes.
    axis = {"recorded_sha256", "state", "why"}
    if anchor_content:
        axis.add("on_disk_body_sha256")
    moved = {key for key in set(silent) | set(fires)
             if silent.get(key) != fires.get(key)}
    expect("the two halves differ in the recorded hash and its consequences, and in "
           "nothing else",
           moved == axis,
           f"expected {sorted(axis)}, found {sorted(moved)}")
    expect("both halves read one file, found by one resolution step, at one digest",
           (silent["where"] == fires["where"]
            and silent["resolved_by"] == fires["resolved_by"]
            and silent["on_disk_sha256"] == fires["on_disk_sha256"]),
           f"{fires['where']} by {fires['resolved_by']}, digest "
           f"{str(fires['on_disk_sha256'])[:12]}")

    # ONE FILE, TWO ANSWERS, IN ONE RUN. This is the discrimination the retired silent
    # case was picked for: the comparison is per EDGE and not per file, so a gate that
    # condemned every artifact naming a file somebody else had moved would fail here.
    # Unlike the retired case it holds whatever the tree has just recomputed.
    expect("one file on disk reads matches under one record and diverged under "
           "another",
           silent["state"] == MATCHES and fires["state"] == DIVERGED
           and silent["where"] == fires["where"],
           f"{fires['where']}, {silent['state']} against {fires['state']}")

    # The resolution above must be the one artifact.py records with, asserted on a LIVE
    # file this time and not only inside a temporary directory: a shared function that
    # agreed on a fixture and disagreed on the tree would be invisible to the other leg.
    theirs = artifact.input_record(anchor["where"], root)
    expect("on a live file too, this gate's resolution agrees with "
           "artifact.input_record",
           bool(theirs["present"]) and theirs["sha256"] == anchor["recorded_sha256"],
           f"{str(theirs['sha256'])[:12]} against {anchor['recorded_sha256'][:12]} "
           f"at {anchor['where']}")

    return {
        "chosen_by": CALIBRATION_ANCHOR_RULE,
        "population": population,
        "artifact": anchor["artifact"],
        "input": anchor["input"],
        "resolved_to": anchor["where"],
        "resolved_by": anchor["resolved_by"],
        "recorded_sha256": anchor["recorded_sha256"],
        "corrupted_to": firing_record["sha256"],
        "silent_half_read": silent["state"],
        "firing_half_read": fires["state"],
        "held_equal": sorted(set(silent) - axis),
        "fifth_step": _self_test_live_fifth_step(edges, root, scripts, cache, index,
                                                 external, expect),
        "second_sign": _self_test_live_body(edges, root, scripts, index, external,
                                            history, expect),
    }


def _self_test_live_fifth_step(edges, root, scripts, cache, index, external, expect):
    """One real input that lives OUTSIDE the tree, judged with the roots and without.

    THE AXIS IS WHETHER THE DECLARED ROOTS ARE ON THIS DISK, AND NOTHING ELSE MOVES.
    Same artifact, same input name, same recorded hash, same producer. With the roots
    the record must read matches and name the root it came from; with the roots
    withheld it must read absent_from_disk and name the roots that were not searched.
    Those are the two answers this step is allowed to give, and the second of them is
    the answer a reader's clone gets, so it is measured here rather than
    assumed.

    Anchored by RULE and not by name, like the pair above, so that a file moving house
    inside ../02_data cannot empty the case. It is reported as not exercised, without
    failing the run, in the one state where the tree offers nothing to build it from: a
    checkout carrying no declared root, where there is no such record to find. That
    state is not a silent pass, because the fabricated pair in CALIBRATION 1 builds its
    own roots and runs there in full.
    """
    outside = sorted((row for row in edges
                      if row["state"] == MATCHES and row["resolved_root"]
                      and row["recorded_sha256"]),
                     key=lambda row: (row["artifact"], row["input"]))
    if not outside:
        print(f"    [ -- ] the fifth step is not exercised on live data: "
              f"{len(external['present'])} declared root(s) on this disk and 0 of "
              f"{len(edges)} input records resolved through one")
        return {"exercised": False,
                "why": "no input record of this tree resolved through a declared root "
                       "outside it, which is the state of a checkout that carries the "
                       "tree alone; the fabricated pair in calibration 1 builds its "
                       "own roots and covers the step there"}

    anchor = outside[0]
    record = {"name": anchor["input"], "bytes": anchor["recorded_bytes"],
              "sha256": anchor["recorded_sha256"], "present": True}
    meta = artifact.read_meta(os.path.join(root, anchor["artifact"]))
    bases, _p, _r = resolution_bases(meta, root, scripts)
    where = f"{anchor['artifact']} -> _meta.inputs -> {anchor['input']}"
    print(f"    anchor  : the first, in sorted order, of the {len(outside)} input "
          f"records this run")
    print(f"              resolved through a declared root outside the tree,")
    print(f"              {where}")

    with_roots = judge_edge(anchor["artifact"], record, bases, root, cache, index,
                            external)
    without = judge_edge(anchor["artifact"], record, bases, root, cache, index,
                         withheld_roots(declared_roots(root)))

    expect("MUST STAY SILENT: a real input under a declared root reads matches and "
           "names the root",
           with_roots["state"] == MATCHES and bool(with_roots["resolved_root"]),
           f"{with_roots['state']} from {with_roots['resolved_root']} at {where}")
    expect("MUST FIRE: the same record with no declared root on disk reads "
           "absent_from_disk",
           without["state"] == ABSENT,
           f"expected {ABSENT}, found {without['state']} at {where}")
    expect("and the withheld half names every declared root rather than reporting "
           "nothing to see",
           sorted(without["declared_roots_missing"] or [])
           == sorted(spec["path"] for spec in declared_roots(root)),
           f"named {without.get('declared_roots_missing')}")
    expect("the two halves hold the record itself equal, so the only thing that moved "
           "is the roots",
           (with_roots["input"] == without["input"]
            and with_roots["recorded_sha256"] == without["recorded_sha256"]
            and with_roots["recorded_bytes"] == without["recorded_bytes"]
            and with_roots["artifact"] == without["artifact"]),
           f"{without['input']} at {str(without['recorded_sha256'])[:12]}")

    return {
        "exercised": True,
        "chosen_by": "the first, in sorted order by artifact then by input name, of "
                     "the input records this run resolved through a declared root "
                     "outside the tree and judged as matches",
        "population": len(outside),
        "artifact": anchor["artifact"],
        "input": anchor["input"],
        "resolved_to": anchor["where"],
        "declared_root": anchor["resolved_root"],
        "with_the_roots_on_disk": with_roots["state"],
        "with_the_roots_withheld": without["state"],
        "withheld_half_named": without["declared_roots_missing"],
        "held_equal": ["artifact", "input", "recorded_sha256", "recorded_bytes"],
    }


DEBT_CALIBRATION_ANCHOR_RULE = (
    "the first artifact of this run's population, in sorted order, whose basename no "
    "other artifact of the population carries")


def _self_test_declared_debt(files, expect):
    """Three cases for the declared-debt rule, all three built from the live population.

    ANCHORED ON THE POPULATION AND NEVER ON THE DECLARED LIST, and that is the whole
    design of it. The list this rule judges is the one thing in this file that is meant
    to be shortened until it is empty, so a calibration standing on it would go vacuous
    on the day the last debt is repaid -- which is the exact way this file has already
    lost one calibration, and the reason the retired pair is written down above. The
    population cannot empty while there is a tree to judge.

    The silent case is a declared entry naming a real artifact. The two firing cases are
    that same entry with ONE thing changed and nothing else: its directory, which must
    read as a move and must name the real address, and its basename, which must read as
    a subject that is nowhere. Both faults are built rather than named, so no repair to
    the tree can empty them.
    """
    anchor = None
    seen = {}
    for rel in sorted(files):
        seen.setdefault(os.path.basename(rel), []).append(rel)
    for rel in sorted(files):
        if len(seen[os.path.basename(rel)]) == 1:
            anchor = rel
            break

    print(f"    anchor  : {DEBT_CALIBRATION_ANCHOR_RULE},")
    print(f"              over a population of {len(files)} artifacts")
    if anchor is None:
        expect("the population offers an artifact with an unshared basename to build "
               "the three cases on", False,
               f"expected at least 1, found 0 of {len(files)}; no case can be built, so "
               f"this rule has not been exercised at all")
        return None
    print(f"              {anchor}")

    base = os.path.basename(anchor)
    moved_from = "__not_a_directory_of_this_tree__/" + base
    gone_name = os.path.join(os.path.dirname(anchor), "__no_such_artifact__" + base)
    gone_name = gone_name.replace(os.sep, "/")

    # The two fabricated addresses have to be addresses the tree really does not hold,
    # or the case measures the fixture rather than the rule. Asserted rather than
    # assumed, because a name that collided would make a firing case read silent and
    # this file counts a silence it cannot account for as a failure.
    expect("the fabricated moved address is not an artifact of the population",
           moved_from not in files, moved_from)
    expect("the fabricated gone basename is carried by no artifact of the population",
           os.path.basename(gone_name) not in seen, gone_name)

    silent = declared_debt_subjects(files, (anchor,))
    moved = declared_debt_subjects(files, (moved_from,))
    gone = declared_debt_subjects(files, (gone_name,))

    expect("MUST STAY SILENT: a declared entry naming a real artifact reads matched",
           [row["state"] for row in silent] == [DEBT_MATCHED],
           f"expected [{DEBT_MATCHED}], found {[row['state'] for row in silent]} "
           f"for {anchor}")
    expect(f"MUST FIRE: the same entry under a directory the tree does not hold reads "
           f"{DEBT_MOVED}",
           [row["state"] for row in moved] == [DEBT_MOVED],
           f"expected [{DEBT_MOVED}], found {[row['state'] for row in moved]} "
           f"for {moved_from}")
    # The address is asserted and not only the state, because the state alone would pass
    # on a rule that found the basename somewhere and reported the wrong place. Naming
    # the new address is the whole difference between re-pointing an entry and striking
    # a live divergence out of the list.
    expect("MUST FIRE: the moved entry names the address the artifact really sits at",
           moved and moved[0]["found_at"] == [anchor],
           f"expected [{anchor}], found "
           f"{moved[0]['found_at'] if moved else 'no row at all'}")
    expect(f"MUST FIRE: an entry whose basename no artifact carries reads {DEBT_GONE}",
           [row["state"] for row in gone] == [DEBT_GONE],
           f"expected [{DEBT_GONE}], found {[row['state'] for row in gone]} "
           f"for {gone_name}")
    return {"anchor": anchor, "chosen_by": DEBT_CALIBRATION_ANCHOR_RULE,
            "population": len(files),
            "must_stay_silent": {"entry": anchor, "expect": DEBT_MATCHED,
                                 "found": silent[0]["state"]},
            "must_fire_moved": {"entry": moved_from, "expect": DEBT_MOVED,
                                "found": moved[0]["state"],
                                "expect_found_at": [anchor],
                                "found_at": moved[0]["found_at"]},
            "must_fire_gone": {"entry": gone_name, "expect": DEBT_GONE,
                               "found": gone[0]["state"]}}


def _self_test_data_root(expect):
    """The data-root step on three cases, in a temporary tree with its own data beside it.

    MUST STAY SILENT: an input lying in the directory the data setting names, with the
    hash its artifact recorded, reads matches and names that root. MUST FIRE: the same
    input with one byte changed in a temporary copy reads as moved. MUST FIRE: with the
    setting unset and the file nowhere in the tree, it reads absent_from_disk. The
    setting is changed for the duration of the case and put back after it.
    """
    names = panel_io.DATA_ROOT_ENV
    saved = {name: os.environ.get(name) for name in names}
    result = {}
    try:
        with tempfile.TemporaryDirectory() as parent:
            tree = os.path.join(parent, "tree")
            data = os.path.join(parent, "data_beside")
            os.makedirs(tree)
            os.makedirs(data)
            payload = b"derived intermediate, fixture bytes\n" * 64
            name = "fixture_intermediate.npz"
            path = os.path.join(data, name)
            with open(path, "wb") as fh:
                fh.write(payload)
            record = {"name": name, "bytes": len(payload),
                      "sha256": hashlib.sha256(payload).hexdigest(), "present": True}

            def judge():
                specs = declared_roots(tree)
                present, missing, idx = external_roots(tree, specs)
                ext = pack_roots(present, missing, idx)
                return judge_edge("fixture_results.json", record, [], tree, {}, {},
                                  ext), specs

            for n in names:
                os.environ.pop(n, None)
            os.environ["CAP_DATA_DIR"] = data
            fresh, specs = judge()
            with open(path, "r+b") as fh:
                fh.seek(7)
                byte = fh.read(1)
                fh.seek(7)
                fh.write(bytes([byte[0] ^ 0x01]))
            moved, _ = judge()
            os.remove(path)
            for n in names:
                os.environ.pop(n, None)
            gone, gone_specs = judge()
    finally:
        for n, value in saved.items():
            if value is None:
                os.environ.pop(n, None)
            else:
                os.environ[n] = value

    expect("MUST STAY SILENT: an input in the data directory with its recorded hash "
           "reads matches and names that root",
           fresh["state"] == MATCHES and fresh["resolved_root"] == "../data_beside",
           f"{fresh['state']} from {fresh['resolved_root']}")
    expect("MUST FIRE: the same input with one byte changed reads as moved",
           moved["state"] in (DIVERGED, UNKNOWN),
           f"expected {DIVERGED} or {UNKNOWN}, found {moved['state']}")
    expect("MUST FIRE: with the data setting unset and no file, it reads "
           "absent_from_disk",
           gone["state"] == ABSENT
           and all(spec["path"] != "../data_beside" for spec in gone_specs),
           f"{gone['state']}, roots {[spec['path'] for spec in gone_specs]}")
    result.update({"with_setting": fresh["state"], "one_byte_changed": moved["state"],
                   "setting_unset_and_no_file": gone["state"]})
    return result


def _self_test_neutral_input(root, index, external, history, expect):
    """The certified-script state on two opposite cases from the live register.

    MUST READ the new state: the first documentation-only certificate whose TO side is
    the script on disk, judged as an input record carrying its FROM hash. MUST READ
    moved: the same record with one hex digit of that FROM hash changed.
    """
    register = _prov._neutral_register(root)
    pick = None
    for entry in register.get("certified") or ():
        name = os.path.basename(str(entry.get("producer") or ""))
        path = os.path.join(root, str(entry.get("producer") or ""))
        if (str(entry.get("carried_by") or "").startswith(
                "one leg, " + _prov.DOCUMENTATION_ONLY_ROUTE)
                and os.path.isfile(path)
                and artifact.sha256_file(path) == entry.get("sha256_on_disk")):
            pick = (name, os.path.dirname(path), entry["sha256_recorded"])
            break
    if pick is None:
        expect("a live documentation-only certificate is on disk to build the pair on",
               False, "no certificate's TO side equals its script on disk")
        return None
    name, where, recorded = pick
    bases = [(where, "the certified script's directory")]

    def judge(digest):
        return judge_edge("fixture_consumer_results.json",
                          {"name": name, "bytes": None, "sha256": digest,
                           "present": True}, bases, root, {}, index, external, history)

    certified = judge(recorded)
    moved = judge(_one_hex_digit_changed(recorded))
    expect("MUST READ the certified state: a script input whose pair of hashes is "
           "certified documentation-only",
           certified["state"] == NEUTRAL_INPUT,
           f"expected {NEUTRAL_INPUT}, found {certified['state']} for {name}")
    expect("MUST FIRE: the same record with one hex digit changed reads moved",
           moved["state"] in NOT_STANDING_ON_WHAT_IT_READ,
           f"expected {DIVERGED}, found {moved['state']} for {name}")
    return {"script": name, "certified": certified["state"],
            "one_hex_digit_changed": moved["state"]}


def _self_test_calibration(edges, root, scripts, index, external, history, files):
    """Both halves. Returns (failures, asserted, anchor).

    `cache` is deliberately NOT shared with the sweep. The live half hashes the file it
    compares a second time, which costs one read and settles a question a shared cache
    would hide: that the digest is read off the disk at judgement time rather than
    carried in from an earlier one.
    """
    failures, asserted, cache = [], [], {}
    # The printing assertion comes from evidence.py, where chk_contrast_hygiene.py reads
    # the same one. It is a factory rather than a plain function because it writes into
    # this scope's two lists and is then handed on to the calibration routines below,
    # which is the shape those routines already expected.
    expect = make_expect(asserted, failures)

    print("-" * 78)
    print("  CALIBRATION 1: fabricated input records over all five outcomes and over "
          "the fifth")
    print("  resolution step, one fault each, on a fixture tree with its own roots "
          "beside it")
    _self_test_fabricated(expect)
    print()
    print("  CALIBRATION 2: live input records -- one with one hex digit of its hash "
          "moved, one")
    print("  that lives outside the tree judged with the declared roots and without "
          "them, and a")
    print("  pair pointed at two byte-states this repository really held, one whose "
          "content")
    print("  agrees with the file on disk and one whose content does not")
    anchor = _self_test_live(edges, root, scripts, cache, index, external, history,
                             expect)
    print()
    print("  CALIBRATION 3: the declared debt against the population -- one entry "
          "naming a real")
    print("  artifact, the same entry under a directory the tree does not hold, and the "
          "same entry")
    print("  under a basename no artifact carries")
    debt = _self_test_declared_debt(files, expect)
    print()
    print("  CALIBRATION 4: the data directory as a declared root -- an input there with "
          "its")
    print("  recorded hash, the same input with one byte changed, and the setting unset "
          "with no file")
    _self_test_data_root(expect)
    print()
    print("  CALIBRATION 5: a script input whose edit is certified documentation-only, "
          "and the")
    print("  same record with one hex digit of its hash changed")
    _self_test_neutral_input(root, index, external, history, expect)
    print(f"    {len(asserted) - len(failures)} of {len(asserted)} calibration "
          f"assertions hold. Neither case names an artifact, so neither can be "
          f"emptied by a repair")
    return failures, asserted, anchor, debt


# =====================================================================
# THE RUN
# =====================================================================

def _sites(rows, limit=None):
    """Findings as places: the artifact, the input, and both hashes."""
    out = []
    for row in rows if limit is None else rows[:limit]:
        detail = f"input {row['input']}"
        if row["recorded_sha256"]:
            detail += f", recorded {row['recorded_sha256'][:12]}"
        if row["on_disk_sha256"]:
            detail += f", on disk {row['on_disk_sha256'][:12]}"
        elif row["state"] == ABSENT:
            detail += ", and the file is not on disk"
        out.append({"file": row["artifact"], "line": "-", "detail": detail,
                    "source": row.get("where") or ""})
    return out


def main():
    started = artifact.start_clock()
    files, dropped, amendments = population(ROOT)
    scripts = _prov.scripts_on_disk(ROOT)
    index = basename_index(ROOT)
    roots_present, roots_missing, roots_index = external_roots(ROOT,
                                                               declared_roots(ROOT))
    external = pack_roots(roots_present, roots_missing, roots_index)
    history = History(ROOT)
    cache = {}
    edges, unreadable, no_inputs = sweep(ROOT, files, scripts, cache, index, external,
                                         history)

    tally = {state: [row for row in edges if row["state"] == state]
             for state in STATES}
    # The two states that say the artifact does not stand on what it read, taken
    # together everywhere. diverged_body_unknown is in here and that is requirement
    # three: a recorded byte-state this repository cannot produce leaves the question
    # unanswered, and an unanswered question may not clear an artifact.
    diverged = [row for row in edges
                if row["state"] in NOT_STANDING_ON_WHAT_IT_READ]
    on_diverged = sorted({row["artifact"] for row in diverged})
    rewritten = tally[REWRITTEN]
    on_rewritten = sorted({row["artifact"] for row in rewritten})
    absent = tally[ABSENT]

    # Which artifacts read the TREE rather than a dataset. Counted from the declared
    # input lists rather than from a list of names, so a second census added later is
    # classified without anyone remembering to edit this file.
    declared = {}
    for row in edges:
        declared[row["artifact"]] = declared.get(row["artifact"], 0) + 1
    census = {rel for rel, count in declared.items()
              if count > CENSUS_INPUT_SHARE * len(files)}
    data_diverged = [row for row in diverged if row["artifact"] not in census]
    census_diverged = [row for row in diverged if row["artifact"] in census]
    on_data_diverged = sorted({row["artifact"] for row in data_diverged})

    # DOES EACH DECLARED ENTRY STILL POINT AT ANYTHING. Asked BEFORE the set difference
    # below, because the answer changes what that difference is allowed to mean: an
    # entry with no subject drops out of `on_diverged` for the same reason a repaid one
    # does, and until 2026-08-12 the two came out in one list under the word "repaid".
    debt_subjects = declared_debt_subjects(files)
    debt_alive = {row["declared"] for row in debt_subjects
                  if row["state"] == DEBT_MATCHED}
    debt_without_a_subject = [row for row in debt_subjects
                              if row["state"] != DEBT_MATCHED]

    # The debt as a set difference, both ways. `undeclared` is the regression this gate
    # fails on; `repaid` is a declared artifact that no longer stands on a moved input,
    # printed so that the list in this file can be shortened by whoever did the work.
    # `repaid` is counted over the entries that HAVE a subject, so that a line pointing
    # at an empty address is never reported as work somebody did.
    undeclared = [rel for rel in on_diverged
                  if rel not in DECLARED_DIVERGED_ARTIFACTS]
    repaid = [rel for rel in DECLARED_DIVERGED_ARTIFACTS
              if rel in debt_alive and rel not in on_diverged]

    print("=" * 78)
    print("  DID THE INPUT MOVE - input-freshness gate")
    print("=" * 78)
    print(f"  population              : {len(files)} tracked .json on disk, "
          f"{len(dropped)} left out")
    print(f"  predicate               : chk_artifact_provenance.population(), "
          f"amended in {len(amendments)} place(s):")
    for row in amendments:
        print(f"      {row['action']:11} {row['file']}")
        print(f"                  {row['why'][:96]}")
    print(f"  input records read      : {len(edges)} across "
          f"{len(files) - len(no_inputs)} artifacts; {len(no_inputs)} artifacts "
          f"record no input list at all")
    print(f"  distinct files hashed   : {len(cache)}, "
          f"{sum(os.path.getsize(p) for p in cache) / 1e6:.0f} MB")
    print(f"  resolution              : five steps, in order, hashed by "
          f"artifact.sha256_file. Every")
    print(f"                            step that placed a name is printed, so the "
          f"counts below sum")
    print(f"                            to the records this run could resolve at all")
    by_step = {}
    for row in edges:
        if row["resolved_by"]:
            by_step[row["resolved_by"]] = by_step.get(row["resolved_by"], 0) + 1
    for step in sorted(by_step, key=lambda k: (-by_step[k], k)):
        print(f"      resolved by {step:52} {by_step[step]:4}")
    print(f"      {'resolved by nothing, or not a local file':64} "
          f"{len(edges) - sum(by_step.values()):4}")

    print()
    print(f"  THE FIFTH STEP: declared search roots OUTSIDE the tree, "
          f"{len(roots_present)} on this disk, "
          f"{len(roots_missing)} not")
    print(f"      Each is written relative to the tree root, never absolute, and each "
          f"is optional:")
    print(f"      a checkout carrying this tree alone has none of them, and the inputs "
          f"that live")
    print(f"      under one then read absent_from_disk with the root NAMED, rather "
          f"than vanishing")
    print(f"      from the count. On such a checkout the rule below stands down and "
          f"says so.")
    for row in roots_present + roots_missing:
        state = f"on disk, {row['n_files']} files" if row["on_disk"] \
            else "NOT ON THIS DISK, not searched"
        print(f"      - {row['path']:16} {state}")
        print(f"          holds  : {row['holds'][:88]}")
        print(f"          outside: {row['why_it_is_outside'][:88]}")
    print()
    print("  seven outcomes per input record, and only the first four are comparisons:")
    for state in STATES:
        print(f"      {state:26} {len(tally[state]):4}")
    print(f"      {'total':26} {len(edges):4}")
    if tally[NEUTRAL_INPUT]:
        print(f"  input changed neutrally, certified -- not a pass and not a failure, "
              f"{len(tally[NEUTRAL_INPUT])} edge(s):")
        for row in tally[NEUTRAL_INPUT]:
            print(f"      ~ {row['artifact']} <- {row['input']} "
                  f"{row['recorded_sha256'][:12]} -> {row['on_disk_sha256'][:12]}")

    print()
    print(f"  ARTIFACTS STANDING ON AN INPUT THAT MOVED: {len(on_diverged)} over "
          f"{len(diverged)} edges. Of the "
          f"{len(DECLARED_DIVERGED_ARTIFACTS)} declared,")
    print(f"      {len(DECLARED_DIVERGED_ARTIFACTS) - len(repaid)} are still standing "
          f"(the edge count itself is reported, NOT gated)")
    print(f"      outside the declared debt : {len(undeclared)} (permitted 0)"
          + (f" -- {', '.join(undeclared)}" if undeclared else ""))
    print(f"      declared and now repaid   : {len(repaid)}"
          + (f" -- {', '.join(repaid)}; shorten the list in this file"
             if repaid else "")
          + f"  (counted over the {len(debt_alive)} entries that still have a subject)")
    print(f"      declared and matching nothing: {len(debt_without_a_subject)} "
          f"(permitted 0). An entry whose subject is not in")
    print(f"      the population can never fire and can never be repaid, so it reads "
          f"exactly like")
    print(f"      finished work. Two of six read that way for a day, on 2026-08-12, "
          f"after a move.")
    for row in debt_without_a_subject:
        print(f"        - {row['declared']} [{row['state']}]"
              + (f" -> {', '.join(row['found_at'])}" if row["found_at"] else ""))
        print(f"            {row['why'][:104]}")
    print(f"      of the edges, {len(data_diverged)} stand on data and are a backlog "
          f"somebody works off;")
    print(f"      {len(census_diverged)} belong to {len(census)} census artifact(s) "
          f"declaring more than {CENSUS_INPUT_SHARE:.0%} of the population,")
    print(f"      which anything that runs afterwards makes stale, so that part "
          f"counts what has run")
    print(f"      since rather than debt. Three runs over one unchanged tree gave 30, "
          f"33 and 36 edges")
    print(f"      and 7 artifacts every time, which is why the artifact count is the "
          f"one with a ceiling.")
    for rel in on_diverged:
        rows = [row for row in diverged if row["artifact"] == rel]
        print(f"      - {rel}: {len(rows)} of "
              f"{len([e for e in edges if e['artifact'] == rel])} recorded inputs"
              + ("   [census of the tree]" if rel in census else ""))
        for row in rows:
            print(f"          [{row['state']}] {row['input']} recorded "
                  f"{row['recorded_sha256'][:12]}, on disk "
                  f"{row['on_disk_sha256'][:12]}  ({row['where']})")
            if row["recorded_body_sha256"]:
                print(f"            content {row['recorded_body_sha256'][:12]} -> "
                      f"{str(row['on_disk_body_sha256'])[:12]}, so the numbers moved "
                      f"and not only the file")
            elif row["state"] == UNKNOWN:
                print("            the recorded byte-state is not in this "
                      "repository's history, so whether")
                print("            the numbers moved cannot be answered; counted as "
                      "debt, never as a pass")
            else:
                print("            no _meta on this input, so the whole file is its "
                      "content")

    print()
    print(f"  INPUTS REWRITTEN WITHOUT THEIR NUMBERS MOVING: {len(rewritten)} edges "
          f"over {len(on_rewritten)} artifact(s).")
    print("  These are NOT debt and they are not matches either. The bytes moved, so "
          "the consumer")
    print("  has not been re-run against the file now on disk; the content did not, so "
          "no figure it")
    print("  publishes stands on a number that no longer exists. Before 2026-08-11 "
          "these were")
    print("  reported in the same words as a real divergence, which is what recomputing "
          "six nodes")
    print("  and moving nothing did to this gate.")
    print(f"      history                 : {history.note or 'not consulted this run'}")
    print(f"      blobs hashed to recover the recorded states: "
          f"{history.n_blobs_hashed}")
    for rel in on_rewritten:
        rows = [row for row in rewritten if row["artifact"] == rel]
        print(f"      - {rel}: {len(rows)} of "
              f"{len([e for e in edges if e['artifact'] == rel])} recorded inputs")
        for row in rows:
            print(f"          {row['input']}: bytes "
                  f"{row['recorded_sha256'][:12]} -> {row['on_disk_sha256'][:12]}, "
                  f"content {row['on_disk_body_sha256'][:12]} on both sides")
            print(f"            _meta moved in "
                  f"{', '.join(row['meta_fields_that_moved']) or 'nothing'}; the "
                  f"recorded state was found")
            print(f"            {row['recorded_state_found_in']}")

    print()
    print(f"  inputs hashed at write time and not on disk now: {len(absent)} "
          f"(baseline {BASELINE_ABSENT_WITH_A_RECORDED_HASH})")
    print("  These leave their artifact UNVERIFIABLE rather than verified: the")
    print("  comparison cannot be made at all. Counted apart from the "
          f"{len(tally[NO_HASH])} local names")
    print(f"  carrying no hash and the {len(tally[REMOTE])} archive addresses, "
          f"neither of which was")
    print("  ever expected to be a file on this disk.")
    if roots_missing:
        print(f"  {len(roots_missing)} declared root(s) are not on this disk "
              f"({', '.join(row['path'] for row in roots_missing)}), so this count")
        print("  cannot be read as debt of the repository: an input that lives under "
              "one of")
        print("  them is unreachable here whatever its state. The rule below stands "
              "DOWN.")
    for row in absent:
        print(f"      - {row['artifact']}: {row['input']} recorded "
              f"{row['recorded_sha256'][:12]}")

    elsewhere = ambiguous_names(edges)
    print()
    print("  THIS GATE'S OWN BLIND SPOT, reported and NOT gated:")
    print(f"      names the tree holds more than once, so they resolve to nothing: "
          f"{len(elsewhere)}")
    for row in elsewhere:
        print(f"        - {row['input']} is at {', '.join(row['candidates'][:3])}")
        print(f"            declared by {', '.join(row['declared_by'][:3])}")
    print("      An input record keeps the basename and drops the directory, so a name")
    print("      the tree holds twice identifies neither copy. This gate refuses to")
    print("      choose rather than guess: comparing an artifact against a file it may")
    print("      never have read would certify a stale figure instead of catching one.")
    print("      The fix belongs in the record, which would have to keep its directory.")

    print()
    failures, asserted, anchor, debt_calibration = _self_test_calibration(
        edges, ROOT, scripts, index, external, history, files)

    rules = [
        {"name": "every declared debt entry still has a subject in the population",
         # ARMED AT ZERO, AND ZERO IS A FLOOR RATHER THAN A FROZEN DEBT. There is no
         # state of this tree in which a line pointing at nothing is correct: it can
         # never fire and can never be repaid, so it is printed as repaid on every run
         # while doing nothing at all. Measured on 2026-08-12: two of the six entries
         # then declared named addresses the restructuring had emptied -- commit 9d52367
         # of 2026-08-11 -- and both had read "declared and now repaid" for a day with
         # nothing red.
         "permitted": 0, "found": len(debt_without_a_subject),
         "assumption": "an entry of DECLARED_DIVERGED_ARTIFACTS names an artifact this "
                       "run judges. A name resolving to no artifact is a broken line in "
                       "the gate rather than debt of the tree, which is why this is the "
                       "one count here with a floor instead of a baseline",
         "method": "each declared name against the population, by path first and then "
                   "BY BASENAME: a name carried by an artifact at another address is "
                   "reported moved WITH that address, because the repair there is to "
                   "re-point the entry and striking it would drop a live divergence out "
                   "of the list; a name no artifact answers to at all is reported gone",
         "note": "re-point the entry at the address named, or strike it and say in the "
                 "commit what was recomputed. Do not leave it standing: it is counted "
                 "as repaid work every run",
         "sites": [{"file": row["declared"], "line": "-",
                    "detail": f"[{row['state']}] {row['why']}",
                    "source": ", ".join(row["found_at"])}
                   for row in debt_without_a_subject]},
        {"name": "no artifact outside the declared debt stands on an input that moved",
         "permitted": 0, "found": len(undeclared),
         "assumption": f"the {len(DECLARED_DIVERGED_ARTIFACTS)} artifacts left of the "
                       f"seven frozen on 2026-08-03 are the whole of this debt. The "
                       f"list may only ever be shortened, and it was shortened by one "
                       f"on 2026-08-05. The debt is a LIST "
                       f"rather than a count because both counts move on a tree where "
                       f"nothing was recomputed -- four runs that day gave 30, 33, 36 "
                       f"and 28 edges over 7 artifacts and then 6 -- and a ceiling of "
                       f"7 would pass a genuine seventh whenever "
                       f"run_all_checks_results.json happens to be fresh",
         "method": "the sha256 in _meta.inputs against sha256 of the file found by the "
                   "five resolution steps: the producer's directory, the tree root, "
                   "the tree by basename, the tree by content, then the declared roots "
                   "outside the tree. Where those two differ, the recorded byte-state "
                   "is recovered from this repository's history by CONTENT and the two "
                   "documents are compared with _meta taken off, so a file rewritten "
                   "with the same numbers is not counted here; a recorded state the "
                   "history does not hold is counted here, because the question is "
                   "then unanswered rather than answered clean. One verdict per "
                   "artifact, then the set difference against the declared list",
         "note": "recompute the artifact; every figure it publishes stands on a "
                 "version of its input that no longer exists. Do not add it to the "
                 "declared list, which may only ever be shortened",
         "sites": [{"file": rel, "line": "-",
                    "detail": f"{len([r for r in diverged if r['artifact'] == rel])} "
                              f"of its recorded inputs moved, and it is not in the "
                              f"debt declared on 2026-08-03"}
                   for rel in undeclared]},
        {"name": "input records rewritten with the same numbers",
         # REPORTED AND NEVER GATED, and it is the count this repair created. It is not
         # debt: no figure stands on a number that no longer exists. It is not nothing
         # either: the consumer has still not been re-run against the bytes now on disk,
         # and somebody deciding what to recompute wants to see it. A ceiling here would
         # be a ceiling on how much honest recomputation the tree is allowed to do.
         "permitted": None, "found": len(rewritten),
         "assumption": "the recorded byte-state and the file on disk are two documents "
                       "with identical content and differ only in _meta, every field "
                       "of which that moved is on the allow-list; identical digits "
                       "under a moved settings fingerprint or scope are counted as a "
                       "divergence instead, and none of the 11 measured on 2026-08-11 "
                       "was of that kind",
         "method": "the recorded byte-state recovered from this repository's history by "
                   "content, then both documents hashed with _meta removed",
         "note": f"over {len(on_rewritten)} artifact(s); before 2026-08-11 every one of "
                 f"these was reported in the same words as a real divergence",
         "sites": _sites(rewritten, limit=40)},
        {"name": "input records whose recorded byte-state the history does not hold",
         # REPORTED, and armed through the rule above rather than here. Every one of
         # these is already inside the artifact-level count, because an unanswered
         # question is counted as debt. A second ceiling on the same edges would report
         # one fault twice and would have to be re-frozen for reasons nobody can act on,
         # such as a run whose output was overwritten before it was ever committed.
         "permitted": None, "found": len(tally[UNKNOWN]),
         "assumption": "a byte-state no object of this repository carries cannot be "
                       "read, so whether the numbers moved is unknown rather than "
                       "clean. Measured 0 of 16 on 2026-08-11, when all 11 recoverable "
                       "states were found and the other 5 inputs carry no _meta at all",
         "method": "every object of every ref hashed and compared with the recorded "
                   "sha256, first among the objects carrying this input's basename and "
                   "then among all of them",
         "note": "commit the artifact, or accept that this edge stays counted as debt; "
                 "it can never be cleared by anything short of the bytes themselves",
         "sites": _sites(tally[UNKNOWN], limit=40)},
        {"name": "input records that no longer match the file on disk",
         # UNARMED ON PURPOSE, and the reason is measured. This count moves in both
         # directions on an unchanged tree: a results file is an artifact with declared
         # inputs and also a thing the battery rewrites, so a green battery run took
         # five edges off it while the provenance census gained edges for everything
         # that ran after it. A ceiling here would have to sit at the worst case and be
         # re-frozen after every battery, which is slack rather than a gate. It is a
         # lower bound on the debt, and the artifact count above is what is armed.
         "permitted": None, "found": len(diverged),
         "assumption": "reported as a lower bound until somebody can freeze a figure "
                       "a green run does not move. Three runs over one unchanged tree "
                       "on 2026-08-03 gave 30, 33 and 36",
         "method": "the same comparison, counted per edge instead of per artifact",
         "note": f"of these, {len(data_diverged)} stand on data and are a backlog; "
                 f"{len(census_diverged)} belong to a census that declares more than "
                 f"half the population and so counts what has run since, not debt",
         "sites": _sites(diverged)},
        {"name": "inputs hashed at write time and absent from disk now",
         # ARMED ONLY WHERE THE MEASUREMENT CAN BE MADE. A declared root that is not on
         # this disk puts every input living under it out of reach, and a count taken
         # in that state measures the checkout rather than the repository -- which is
         # exactly the defect that produced the eleven this step repaired. So the rule
         # stands DOWN there and says which root was missing, instead of passing (which
         # would certify what it could not see) or failing (which would be red for a
         # reason the reader cannot act on, and a red nobody can act on stops being
         # read). The count itself is printed in full either way.
         "permitted": 0 if not roots_missing else None, "found": len(absent),
         "assumption": "an input that carried a hash was on disk once and can be "
                       "there again, so its absence is debt rather than design. "
                       "Lowered from 11 to 0 on 2026-08-05 by adding the fifth "
                       "resolution step: all eleven were on disk the whole time, "
                       "hash-exact, beside the tree, and the count "
                       "was measuring which places this gate had searched"
                       + ("" if not roots_missing else
                          ". NOT ARMED on this run: "
                          + ", ".join(row["path"] for row in roots_missing)
                          + " is not on this disk, so an input living there cannot be "
                            "resolved here at all and its absence is a property of "
                            "this checkout"),
         "method": "a recorded sha256 whose name resolves to no file in the "
                   "producer's directory, at the tree root, in the tree by basename, "
                   "in the tree by content, or under a declared root outside the tree",
         "note": "the artifact is unverifiable rather than verified; rebuild the "
                 "input, fetch the root it lives under, or state in the artifact why "
                 "it cannot exist",
         "sites": _sites(absent, limit=40)},
        {"name": "every file in the population parses",
         "permitted": 0, "found": len(unreadable),
         "assumption": "a results file that cannot be read cannot be judged, so it "
                       "is counted as a failure rather than skipped. Zero is the "
                       "floor and always was: this is a broken file, not debt",
         "method": "json.load over the population",
         "sites": [{"file": row["file"], "line": "-", "detail": row["detail"]}
                   for row in unreadable]},
        {"name": "the gate is calibrated on two opposite cases",
         "permitted": 0, "found": len(failures),
         "assumption": "the predicate fires on a case built to fail and stays silent "
                       "on its opposite: fabricated records covering every outcome, "
                       "including a rewrite that moved no number and a rewrite that "
                       "moved a setting; one live input record judged as it stands and "
                       "again with one hex digit of its hash moved; and a live pair "
                       "pointed at two byte-states this repository really held, one "
                       "whose content agrees with the file on disk and one whose "
                       "content does not; and a declared debt entry naming a real "
                       "artifact against the same entry under a directory the tree does "
                       "not hold and under a basename no artifact carries. One reference "
                       "point cannot tell a predicate that is too wide from one that "
                       "is too narrow, and a case NAMING a live artifact empties the "
                       "day that artifact is repaired, which is how the pair written "
                       "here on 2026-08-03 went vacuous",
         "method": f"{len(asserted)} assertions, run on every invocation rather than "
                   f"behind a flag; the live pair is drawn from this run's own sweep "
                   f"by rule rather than by name",
         "note": "until this passes, no count above means anything: a comparator "
                 "nobody has seen fire is not evidence that there is nothing to find",
         "sites": [{"file": OUT_NAME, "line": "-",
                    "detail": f"{row['assertion']}: {row['detail']}"}
                   for row in failures]},
    ]

    over = [rule for rule in rules
            if rule["permitted"] is not None and rule["found"] > rule["permitted"]]
    clean = all(rule["found"] == 0 for rule in rules)
    verdict = "FAIL" if over else ("PASS" if clean else "PASS_AT_BASELINE")

    payload = {
        "verdict": verdict,
        "asks": "whether every artifact still stands on the version of each input it "
                "recorded reading, which is the question neither existing freshness "
                "gate puts: both compare an artifact against its PRODUCER's hash and "
                "so ask only whether the code moved",
        "population": {
            "n_artifacts": len(files),
            "n_left_out": len(dropped),
            "n_without_an_input_list": len(no_inputs),
            "predicate": "chk_artifact_provenance.population(), the .gitignore rules "
                         "applied to every .json on disk",
            "amendments": amendments,
            "files": files,
            "left_out": dropped,
            "artifacts_without_an_input_list": no_inputs,
        },
        "resolution": {
            "steps_in_order": ["the producer's own directory",
                               "the tree root, which is the working directory every "
                               "producer here is launched from",
                               "the only file of that name in the tree, refused when "
                               "the tree holds more than one",
                               "among same-named files in the tree, the one whose "
                               "contents equal the recorded hash",
                               "the declared roots outside the tree, by the same "
                               "content rule, and only those on this disk"],
            "n_resolved_by_step": by_step,
            "hashed_by": "artifact.sha256_file",
            "n_distinct_files_hashed": len(cache),
            "why_ambiguity_is_refused": "a basename the tree holds twice identifies "
                                        "neither copy, and choosing one would give a "
                                        "false MATCH, which is the one outcome this "
                                        "gate exists to prevent",
            "declared_roots_outside_the_tree": {
                "asks": "where an input lives that has never been inside this tree",
                "written_as": "a path relative to the tree root, never absolute: an "
                              "absolute path names this machine, leaks an account name "
                              "into a published artifact and cannot be followed by anyone "
                              "who clones this repository",
                "optional_because": "this tree is meant to be cloned on its own. A "
                                    "root that is not on disk is not searched, and "
                                    "every input that would have lived under it reads "
                                    "absent_from_disk naming the root, which is the "
                                    "honest answer rather than a count that reached "
                                    "zero",
                "note_this_run": external["note"],
                "on_disk": roots_present,
                "not_on_disk": roots_missing,
                "added": "2026-08-05, after eleven inputs read absent from disk and "
                         "all eleven were found on disk by content, 11 of 11, over a "
                         "walk of 9425 files: the count was measuring which places "
                         "this gate searched rather than the repository",
            },
        },
        "tally": {state: len(tally[state]) for state in STATES},
        "n_edges": len(edges),
        "rewritten_same_numbers": {
            "asks": "whether a byte-difference between the recorded input and the file "
                    "on disk is a difference in the numbers, or only in the _meta block "
                    "that carries the run clock and the producer hash",
            "n_edges": len(rewritten),
            "n_artifacts": len(on_rewritten),
            "artifacts": on_rewritten,
            "edges": rewritten,
            "both_signs_are_kept": "the whole-file sha256 the producers write is "
                                   "untouched and still means what it meant; the hash "
                                   "of the same document without _meta is derived "
                                   "beside it. Replacing the first with the second "
                                   "would leave every record written earlier meaning "
                                   "something else under an unchanged name",
            "what_a_rewrite_may_move_in_meta": list(REWRITE_MAY_MOVE),
            "why_an_allow_list": "identical numbers under a changed settings "
                                 "fingerprint or scope are a different question with "
                                 "the same digits, so those two are not on the list; "
                                 "and a deny-list would pass a record shape added "
                                 "after it was written, silently",
            "recorded_state_recovered_from": history.note,
            "n_blobs_hashed": history.n_blobs_hashed,
            "added": "2026-08-11, after recomputing six nodes reported 16 diverged "
                     "edges over 6 artifacts of which 11 stood on results files whose "
                     "numbers had not moved by one digit: ws1_horizon_results.json 1498 "
                     "leaves, t3_results.json 327, as_quoter_results.json 184, "
                     "m2_figure_results.json 40, ws2_hard_classifier_results.json 29, "
                     "toxicity_frame_results.json 4, zero moved in each",
            "not_a_match": "the consumer has still not been re-run against the bytes "
                           "now on disk, and the artifact standing on a rewrite is "
                           "named above; what changed is that this is no longer "
                           "reported in the same words as a stale figure",
        },
        "diverged": {
            "n_edges": len(diverged),
            "n_artifacts": len(on_diverged),
            "artifacts": on_diverged,
            "edges": diverged,
            "counts_two_states": {
                DIVERGED: len(tally[DIVERGED]),
                UNKNOWN: len(tally[UNKNOWN]),
                "why_together": "an artifact whose recorded byte-state this repository "
                                "cannot produce has not been shown to stand on its "
                                "input; the comparison is unmade, and an unmade "
                                "comparison is counted as debt rather than as a pass",
            },
            "declared_debt": list(DECLARED_DIVERGED_ARTIFACTS),
            "outside_the_declared_debt": undeclared,
            "declared_and_now_repaid": repaid,
            "declared_and_now_repaid_predicate": "declared, still naming an artifact of "
                                                 "the population, and not among the "
                                                 "artifacts standing on a moved input. "
                                                 "The middle clause was added 2026-08-12 "
                                                 "and it is not decoration: without it "
                                                 "an entry whose address the "
                                                 "restructuring emptied -- commit "
                                                 "9d52367 of 2026-08-11 -- "
                                                 "comes out in this list, which is a "
                                                 "broken line reported as finished work",
            "declared_debt_matching_nothing": debt_without_a_subject,
            "declared_debt_subjects": debt_subjects,
            "declared_debt_states": list(DECLARED_DEBT_STATES),
            "why_a_list_and_not_a_count": "both counts move on a tree where nothing "
                                          "was recomputed: four runs on 2026-08-03 "
                                          "gave 30, 33, 36 and 28 edges over 7 "
                                          "artifacts and then 6, because a results "
                                          "file is an artifact with declared inputs "
                                          "and also a file the battery rewrites. A "
                                          "ceiling of 7 would pass a genuine seventh "
                                          "whenever run_all_checks_results.json "
                                          "happens to be fresh",
            "standing_on_data": {
                "n_edges": len(data_diverged),
                "n_artifacts": len(on_data_diverged),
                "artifacts": on_data_diverged,
                "means": "a backlog somebody works off by recomputing the artifact",
            },
            "standing_on_the_tree": {
                "n_edges": len(census_diverged),
                "artifacts": sorted(census),
                "predicate": f"declares more than {CENSUS_INPUT_SHARE:.0%} of the "
                             f"{len(files)} tracked .json as its inputs; the largest "
                             f"computation here declares 27 and the census 83, so "
                             f"nothing sits near the boundary",
                "measured_both_ways": "run on its own this reads 1; run inside the "
                                      "battery it reads 4, being the four checks that "
                                      "rewrite their results file between the "
                                      "provenance census and this gate",
            },
        },
        "absent_from_disk": {
            "n_edges": len(absent),
            "baseline": BASELINE_ABSENT_WITH_A_RECORDED_HASH,
            "armed": not roots_missing,
            "why_not_armed": None if not roots_missing else (
                "one or more declared roots outside the tree are not on this disk ("
                + ", ".join(row["path"] for row in roots_missing)
                + "), so an input living under one of them cannot be resolved here "
                  "whatever its state, and this count would measure the checkout "
                  "rather than the repository"),
            "means": "the artifact cannot be verified at all, which is worse than a "
                     "divergence rather than better",
            "lowered_on": "2026-08-05, from 11 to 0, by the fifth resolution step",
            "edges": absent,
        },
        "not_a_comparison": {
            "no_hash_recorded": len(tally[NO_HASH]),
            "remote_address": len(tally[REMOTE]),
            "why_kept_apart": "counting archive addresses as missing inputs would "
                              "report the tape parsers as broken on every run, and "
                              "counting them as clean would report an unverifiable "
                              "input as verified",
        },
        "blind_spot": {
            "gated": False,
            "asks": "input names the tree holds more than once, which the record's "
                    "basename cannot tell apart and this gate refuses to guess at",
            "n": len(elsewhere),
            "rows": elsewhere,
            "where_the_fix_belongs": "the input record, which drops the directory it "
                                     "was given; nothing this gate can do closes it "
                                     "without introducing a false match",
        },
        "calibration": {
            "must_fire": CALIBRATION_MUST_FIRE,
            "must_stay_silent": CALIBRATION_MUST_STAY_SILENT,
            "second_sign_must_fire": CALIBRATION_BODY_MUST_FIRE,
            "second_sign_must_stay_silent": CALIBRATION_BODY_MUST_STAY_SILENT,
            "anchor": anchor,
            "declared_debt_rule": debt_calibration,
            "why_the_debt_pair_is_anchored_on_the_population": (
                "the declared list is the one thing in this file meant to be shortened "
                "until it is empty, so a case standing on it goes vacuous the day the "
                "last debt is repaid -- which is exactly how the pair written here on "
                "2026-08-03 erased itself. The population cannot empty while there is a "
                "tree to judge, so all three cases are built from it: one entry naming a "
                "real artifact, the same entry under a directory the tree does not hold, "
                "and the same entry under a basename no artifact carries"),
            "retired": CALIBRATION_RETIRED,
            "n_assertions": len(asserted),
            "n_failed": len(failures),
            "failures": failures,
            "why_it_cannot_go_vacuous": "neither case names an artifact of the tree. "
                                        "The silent half is drawn from this run's own "
                                        "sweep by rule and the firing half is that "
                                        "same record with one hex digit changed, so a "
                                        "repair anywhere in the tree moves which "
                                        "record is used and never whether there is "
                                        "one. The single condition that would stop "
                                        "the pair running -- no matched input record "
                                        "in the whole tree -- is asserted as a failure "
                                        "rather than reported as a silence",
        },
        "edges": edges,
        "unreadable": unreadable,
    }

    out_path = artifact.write(
        OUT_NAME, payload,
        script=__file__,
        # The population is what this gate reads. The files whose hashes it COMPARED
        # are named in the payload with both hashes rather than listed here, so that
        # the eighty-eight of them are not hashed a second time to say what the
        # payload already says.
        inputs=[os.path.join(ROOT, rel) for rel in files]
               + [os.path.join(ROOT, ".gitignore")],
        scope={
            "population": f"{len(edges)} input records declared by {len(files)} "
                          f"tracked .json files on disk under this repository",
            "window": "n/a: this gate reads the repository as it stands now, not a "
                      "period of market data",
            "coins": "n/a: this gate compares file hashes and touches no market data",
        },
        started=started,
        extra_meta={
            "amendments_to_the_shared_population": amendments,
            "not_caught": [
                "an input whose basename the tree holds more than once resolves to "
                "nothing and reads as absent; the count of those is in blind_spot",
                "a matching hash proves the input file is unchanged, never that the "
                "artifact was recomputed from it; that is chk_run_happened's question",
                "an input the producer never declared is invisible here, because this "
                "gate reads what an artifact SAYS it read",
            ],
        },
    )

    # SELF-CONFORMANCE. This gate's own results file is out of the population it
    # measures, so the rule is applied to it here instead, by re-resolving every input
    # record of the file just written. They were hashed seconds ago, so anything other
    # than a clean answer means the writer and this comparison disagree about what an
    # input record is. A gate exempt from its own rule is not a rule.
    #
    # THE CACHE IS DELIBERATELY NOT SHARED WITH THE SWEEP, AND THAT IS A REPAIR MADE
    # 2026-08-12 ON A DIVERGED RUN OF THIS VERY LEG. Two runs of this gate eleven
    # minutes apart, over one tree and one version of this file, answered differently:
    # the first reported an input of its own record that did not re-resolve, the second
    # 99 of 99 clean. The mechanism is the two moments a hash can be taken at, and it
    # was not the tree moving under a published figure. artifact.input_record hashes
    # each input at WRITE time, at the end of the run; the sweep hashed the same files
    # at its start and put them in `cache`. Handing that cache to this leg made it
    # compare a write-time hash against a start-of-run hash, so anything rewritten by
    # another process in between read as a divergence of this gate against itself. On
    # the diverged run a neighbouring instrument rewrote checks/
    # chk_artifact_provenance_results.json at 15:30:54, inside the window; the clean run
    # had no writer inside its own.
    #
    # A fresh cache makes the leg ask what it says it asks -- does the record the writer
    # has just made re-resolve against the disk NOW -- and it costs one re-hash of the
    # population, which is 99 small documents rather than the arrays. The calibration
    # above already refuses the shared cache for exactly this reason and says so; this
    # leg not doing the same was an inconsistency inside one file.
    written_meta = artifact.read_meta(out_path)
    bases, _p, _r = resolution_bases(written_meta, ROOT, scripts)
    own = [judge_edge(SELF_OUTPUT, record, bases, ROOT, {}, index, external,
                      history)
           for record in written_meta.get("inputs") or []]
    own_bad = [row for row in own if row["state"] not in (MATCHES,)]
    print()
    print(f"  this gate's own results file, held to the same rule: "
          f"{len(own) - len(own_bad)} of {len(own)} of its recorded inputs re-resolve "
          f"and match")
    for row in own_bad:
        print(f"      - {row['input']}: {row['state']}")
    rules.append({
        "name": "this gate's own results file re-resolves clean",
        "permitted": 0, "found": len(own_bad),
        "assumption": "the file this gate has just written records inputs that were "
                      "hashed seconds ago, so every one of them must re-resolve and "
                      "match. It is left out of the population it measures, so this "
                      "rule is the only thing holding it to its own rule. The one thing "
                      "that can move it without any figure moving is another process "
                      "writing into this tree mid-run, which is why the hash is taken "
                      "off disk here and never carried in from the sweep",
        "method": "judge_edge() re-run over _meta.inputs of the file just written, with "
                  "a FRESH cache, so the comparison is write-time hash against disk now "
                  "rather than write-time hash against start-of-run hash",
        "note": "artifact.write and this gate disagree about what an input record is; "
                "fix the reader or the writer, not the ceiling",
        "sites": _sites(own_bad)})
    if own_bad:
        over.append(rules[-1])
        verdict = "FAIL"
        payload["verdict"] = verdict

    print("-" * 78)
    print(f"  VERDICT: {verdict}")
    print(f"  results -> {OUT_NAME}")

    code = report_gate(rules, OUT_NAME, inputs={
        "population": f"{len(files)} tracked .json under this repository",
        "predicate": "chk_artifact_provenance.population, amended twice",
    })
    return 1 if (over or failures) else code


if __name__ == "__main__":
    sys.exit(main())
