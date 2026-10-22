#!/usr/bin/env python3
"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-07-30
References: internal ws1_horizon_results.json (horizon evidence), t3_results.json
(whale-drop ladder), ks2_persistence_10day_results.json (measured reliabilities),
panel_persistence_results.json (the family size the permutation budget is sized for).

SINGLE SOURCE OF TRUTH FOR EVERY SETTING THAT MOVES A REPORTED NUMBER.

Why this module exists. A setting used to enter this code as a SPELLING rather than
as a parameter. The scoring window was part of a column name, so z["mo60"] fixed it
as firmly as a constant did while no grep for the word "horizon" could find it. A
threshold, a seed and a resampling budget were module-level literals, so editing one
file propagated nowhere and every other file had to be edited by hand. Two costs
followed. First, the same quantity disagreed between files: a census by syntax tree
over the 73 tracked scripts found 337 distinct setting names in 559 declarations, 73
names declared in more than one file, and 33 of those disagreeing on the value.
Second, and worse, a wrong setting does not break. The analytical files carry mo1,
mo10 and mo60 side by side, so reading the wrong one raises nothing, types nothing
wrong and returns a plausible number. A wrong setting is not an error; it is a
DIFFERENT VALID NUMBER, and only a declaration can tell the two apart.

Four rules this file exists to enforce.

  1. One quantity, one name, one home. A quantity declared here is not re-declared
     anywhere. Where the same quantity currently wears several names (the seed alone
     appears as SEED, RNG_SEED, BOOTSTRAP_SEED, SEED_PERM, SEED_BOOT, RNG_CORR_SEED
     and RNG_RELIABILITY) the names collapse to one here and the aliases go away.

  2. A field name never states a setting that its value does not come from. Names
     drift in BOTH directions: before the window was consolidated a field named
     _10s carried a 60 s value; after the consolidation a variable named m60 carries
     a 10 s value. Neither is findable by grepping for a value, because the defect
     lives in the relation between a name and its source. So a name is BUILT from
     this module (see field_name) and never typed.

  3. Every artifact stamps what it was computed under. fingerprint() returns that
     block. Without it, "a reader re-runs and gets the same numbers" is a
     promise; with it, it is a checkable statement, which is what reproducibility
     asks for.

  4. Every declaration says what KIND of thing justifies it, not only what its value
     is. A value read off an artifact, a value forced by arithmetic and a value taken
     by convention are defended in three different ways, and a reader who cannot tell
     them apart has to take all three on trust. SETTING_BASIS carries the kind, the
     artifact and key where there is one, and the word "none" where there is nothing
     -- an empty spot said out loud beats a plausible story. basis_gaps() is empty or
     the module refuses to import, so a new declaration cannot arrive unclassified.

MIGRATION STATE, and why this file distinguishes two kinds of value. Some values
below are already what the whole tree uses; adopting them changes nothing. Others
are the value the tree SHOULD use, while some scripts still run on a different one,
so switching them will move a published number. Confusing the two would let a
consolidation quietly restate a result. Every declaration therefore carries its
state in SETTING_STATE: "in_force" means every consumer already agrees, "target"
means consumers disagree and the switch is a measured change owed its own recompute
and its own leaf-by-leaf comparison. checks/chk_settings_home.py reads this map.
"""

# =====================================================================
# 1. THE SCORING WINDOW
#
# Carried over verbatim from horizons.py, which this module replaces. The value and
# the reasoning are unchanged; only the home moved, so no number moves with it.
# =====================================================================

# TWO DECISIONS STAND ON THIS ONE NUMBER, AND THEY ARE NOT ONE DECISION.
#
# The first is the COST window: how long after a fill the permanent price move has
# arrived, so that what is measured is adverse selection rather than the fill's own
# transient push. It is defended by the completeness curve, and by nothing else.
#
# The second is the RANKING window: over how long a counterparty's markout has to be
# averaged before the ordering of counterparties reproduces on days that ordering was
# not fitted on. It is defended by the early-to-late rank persistence, and by nothing
# else.
#
# They are separate because the two criteria pull in opposite directions -- a longer
# window buys completeness and loses persistence -- so a single number is only
# available where both clear at the same rung. What settles this declaration is that
# both do, not that one criterion decides for the other. A grid on which they did not
# would leave this module carrying two declarations rather than one.
#
# ONE WINDOW PER BLOCK is a third statement and not a restatement of either. Within a
# reported block the counterparties are ranked at the same window their later profit is
# measured at, because a block that ranks at one window and measures at another books
# the gain the shorter measurement shows while turning away only the notional the
# longer screen declines, and so overstates how efficient the screen is.
#
# HEADLINE_HORIZON_S is 10 because the evidence ws1_horizon_persistence.py writes
# clears two stated criteria at 10 s: by then the permanent price move is 97.9%
# impounded (final_decision.info_frac["10"] = 0.9792, against a stated completeness
# threshold of 0.95), while the disattenuated early-to-late rank persistence is still
# 0.52 against 0.32 at 60 s. That same file records old_choice_companion_dominated =
# true and drops 60 and 120 from the reported term structure. 10 s is also the shortest
# conventional horizon at the information plateau and matches a maker's reaction window.
#
# WHAT DOES NOT JUSTIFY IT, and the distinction matters. That file also carries a key
# named final_decision.recommended_score_horizon_s holding 10, and it would be the
# natural thing to cite. It is not evidence: its own neighbouring key
# recommended_source says it is READ BACK from this declaration, so citing it would
# argue that this value is right because this value is what it is. What the producer
# owns is the curve and the two checks; what it does not own is the choice.
#
# The choice is a stated human judgement on top of the grid, not a grid maximum, in two
# separate directions. The grid's argmax over all rungs is 1 s, where only about 80% of
# the move has arrived and most of what has arrived is the trade's own transient push.
# The argmax over the rungs that ARE information-complete is 5 s, which the same file
# records at final_decision.most_persistent_info_complete, and which is not adopted for
# the reason given at LADDER_S below.
HEADLINE_HORIZON_S = 10

# Every horizon the producers actually write a column for. A horizon outside this
# tuple has no column in any artifact and cannot be scored without a re-mark
# (ws1_horizon_persistence.py is the only script that re-marks). This is why the 5 s
# horizon that the selection rule preferred cannot simply be adopted.
LADDER_S = (1, 10, 60)

# The long window kept beside the headline in robustness tables.
COMPANION_HORIZON_S = 60


def headline_print_col(h=HEADLINE_HORIZON_S):
    """Trade-print markout column name (quickwin_markouts.npz, panel_markouts.npz)."""
    if h not in LADDER_S:
        raise ValueError(f"no trade-print markout column exists for h={h}s; "
                         f"columns exist only for {LADDER_S}")
    return f"mo{h}"


def headline_mid_col(h=HEADLINE_HORIZON_S):
    """Book-mid markout column name (quickwin_markouts_mid.npz)."""
    if h not in LADDER_S:
        raise ValueError(f"no book-mid markout column exists for h={h}s; "
                         f"columns exist only for {LADDER_S}")
    return f"mo{h}_mid"


def companion_print_col():
    """Trade-print column of the long companion window kept in robustness tables.

    A script that reports the headline beside the companion asks for both here, so
    neither name is typed anywhere and neither can drift from what this file says.
    """
    return headline_print_col(COMPANION_HORIZON_S)


def companion_mid_col():
    """Book-mid column of the long companion window."""
    return headline_mid_col(COMPANION_HORIZON_S)


# =====================================================================
# 2. THE LENS: WHICH PRICE THE HARM IS MEASURED AGAINST
# =====================================================================

# Two reference prices answer two different questions, and the project reports both.
# The trade print is what the counterparty actually paid, so it carries the maker's
# earned spread and the bid-ask bounce inside it. The book mid at the same instant
# removes both, so it isolates the price move. Neither is a correction of the other.
# The lens is NOT recoverable from a column name alone in every file, which is why it
# belongs in the fingerprint: of 75 artifacts holding computed numbers, 17 name their
# lens and 33 leave it to be inferred from an input filename.
LENSES = ("print", "mid")
HEADLINE_LENS = "mid"

# Why the book mid leads. On the headline window the two lenses give the same answer to
# within a hundredth, so the choice is not doing the work. Read 30 July from the two
# artifacts at the same cell (BTC, 50-fill floor, persistence_pooled[0]
# .spearman_disattenuated): 0.8525 print in ks2_persistence_10day_results.json against
# 0.8417 mid in ks2_persistence_mid_results.json. The pair 0.84/0.86 stood here before
# and reproduces at no cell of either file; the reading above is the same quantity taken
# from both lenses at one named cell. The ordering is not stable across the ladder --
# at the 100-fill floor the mid is the higher of the two, 0.9143 against 0.9043 -- which
# is the point: neither lens dominates, so the lens is not what the result rests on.
# The mid leads because it answers the adverse-selection question without the maker's
# own spread inside the number, and because it is the lens whose magnitude the text
# interprets. The print lens is reported beside it, never instead of it.


# =====================================================================
# 3. RANDOMNESS
# =====================================================================

# The one seed. Its VALUE is arbitrary -- no integer is more correct than another --
# so it was chosen on the single property that only one value has: with one seed, a
# p-value that differs between two scripts differs because the STATISTIC differs, and
# a reader may compare them. NINE distinct seed values are drawn in this tree today
# (42, 690, 424242, 20240601, 20260619, 20260620, 20260621, 20260622, 20260623), so no
# such comparison is possible yet, and the nine are the distance still to travel.
#
# WHERE THE NINE LIVE NOW, which is a different question from how many there are and is
# the one that changed on 2026-07-31. Eight of the nine are entries of SEED_BY_PURPOSE
# below and the ninth is this line, so the tree holds nine values in ONE file rather than
# nine literals in nine. Counted by syntax tree on 2026-08-02, SEVEN seed literals remain
# in six files: the two on this line and the next, SEED_CORR_NULL 424242 in each of the
# two ks2 files, CAP_BOOK_SEED 20260620 in i3_book_comparator.py, SEED 20260622 in
# probes/probe_G_horizon.py, and SEED 42 in a classifier script that is not published in
# this repository.
#
# The figure FOUR stood here before, and the difference is in the predicate rather than
# in the tree. The earlier count was taken over the alias list at LOAD_BEARING["seed"] in
# checks/chk_settings_home.py, which holds neither SEED_CORR_NULL nor CAP_BOOK_SEED, so
# those three sites are not findings the guard suppressed but sites it cannot see. That
# is the same failure section 5 below records for the wallet floor, in the same
# instrument. The count above is taken over a wider population -- every module-level
# assignment whose target name contains "seed", case-insensitive -- which returns ten
# sites, three of which hold a COUNT of seeds rather than a seed: N_SPLIT_SEEDS in two
# files and SEED_SWEEP_N in one. CONFIG.md already carried the wider figure, so the two
# documents disagreed and this line was the one that was wrong.
#
# CAP_BOOK_SEED is of a kind of its own and is named rather than folded in: no generator
# in its file opens on it, and it is stamped into two artifact fields, book_seed and
# book_feature_seed, as though one had. A seed a reader can check against nothing is a
# worse state than a seed typed where it should have been read.
#
# The nine is a count over a named population, because two censuses of it disagreed and
# the disagreement was in the counting, not in the tree. Population: every module-level
# integer literal bound to a name containing "seed", over all tracked .py files
# including this one, re-counted by syntax tree on 30 July. Two traps sit in that
# predicate and both were walked into. A census that keeps every "seed" name returns
# ELEVEN values, because N_SPLIT_SEEDS = 5 in i2_walletfe.py and panel_common_idio.py
# and SEED_SWEEP_N = 40 in i3_book_comparator.py hold a COUNT OF SEEDS and not a seed;
# dropping those two leaves nine. A census run over the tree EXCLUDING this file
# returns EIGHT, because 20240601 exists as a literal nowhere but the RELIABILITY_SEED
# line below -- its three consumers bind the name rather than retype the value. Eight
# and nine are therefore the same tree counted over two populations, and the sentence
# that carried both at once had its count on one and its list on the other. Bare
# literals passed straight into a generator constructor were swept separately and add
# nothing: the only one is 690, already in the nine.
#
# WHAT THIS DECLARATION IS ACCEPTED ON, and it is not the scalar. A scalar shared by
# several consumers is the defect and not the property: two generators opened on the
# same integer draw the same uniforms in the same order, so a difference between two
# such results is not a difference between their statistics. What has to be shown is
# therefore the STREAM -- that each consumer's stream is derived from a declared seed by
# a stated rule.
#
# ONE RULE, DECIDED 2026-08-02. The work declares ONE derivation rule, and it takes two
# parameters rather than none: WHICH declared seed the stream belongs to, and WHAT cell
# is being computed. Its form is
#
#     stream = SHA-256("<base seed>|<component>|<component>|...") folded to 64 bits
#
# and it is already written in this tree, at panel_persistence.cell_rng. rng() below is
# the same rule with the base fixed to MASTER_SEED and the components flattened to
# character codes instead of joined by a separator; the flattening is the part that has
# to go, for the two reasons measured below.
#
# WHY ONE RULE AND NOT SEVERAL WITH NAMED ROLES, which is the shape section 5 reaches for
# the wallet fill floor and is deliberately NOT the shape reached here. The three fill
# floors are three QUANTITIES gating three populations, and one of them, the sweep, is a
# finding the work publishes; collapsing them would delete a reported curve. A derivation
# rule is not a quantity and nothing is reported about it: a reader is owed the knowledge
# that two cells were not mixed alike, never the knowledge of how the bits were mixed. So
# collapsing six spellings of one mechanism deletes nothing, and the two things that do
# differ between consumers -- which seed, which cell -- become parameters of the one rule.
# The single role that resembles a second rule is a SWEEP over seeds, where the spread
# across seeds is itself the finding: RELIABILITY_SEED_SPREAD_SD above, and the forty fold
# seeds of SEED_SWEEP_SEEDS in i3_book_comparator.py. A sweep is the base parameter taking
# many values, not a rule of its own.
#
# WHY THE JOINED FORM AND NOT THE FLATTENED ONE, on two properties measured here. First,
# the flattening in cell_key below cannot separate ("ws1", "placebo") from ("ws1", "plac",
# "ebo") -- checked, the two keys are equal -- and _refuse_ambiguous_cell states that the
# repair is boundary marking. The joined form IS boundary marking: the same pair gives two
# different keys under it, while a genuinely identical pair still gives one, so the defect
# this module documents as open is closed by the rule the tree already runs. Second,
# cell_key starts its part list at MASTER_SEED, so no stream on any other base can be
# written with it, and RELIABILITY_SEED and every per-purpose entry would need a second
# mechanism for as long as the base stays fixed. A rule that spans the tree has to take
# the base; the joined form does and the flattened one does not.
#
# WHO ACTUALLY DRAWS, re-counted by syntax tree on 2026-08-02 over the 99 tracked .py
# files of this repository. The count differs from the one that stood here on 1 August,
# and the difference is in the procedure rather than in the tree.
#
# The predicate both counts use: the file's syntax tree holds a call to default_rng, to
# RandomState, to the legacy numpy.random.seed, or to rng(). Calibrated in both directions
# on live files rather than on one reference, because one case cannot tell a predicate
# that is too wide from one that is too narrow: gm_quoter.py must fire and
# checks/chk_no_abs_paths.py must stay silent, and both do. With rng() recognised in its
# ATTRIBUTE form the predicate returns 45 files; with rng() recognised only as a bare name
# it returns 42, and the three in the gap are ws1_horizon_persistence.py,
# ws2_hard_classifier.py and ws3_taker_pnl.py, which reach the rule as H.rng(...) and draw
# by no other route. So 45 is the count, and 42 was low by exactly the three files already
# doing the declared thing.
#
# The predicate is also INCOMPLETE, which neither count showed. sklearn takes its stream
# through a keyword, random_state=, and the classifier script, not published in this
# repository, draws that way at two sites on a typed 42. Swept separately over the same 99 files: one file. Three further routes were
# swept and returned zero, and each zero is calibrated rather than assumed -- the stdlib
# random module (0), a pandas .sample call (0), and any np.random.<f> other than seed,
# default_rng and RandomState (0). The last zero is the one that pays: nothing in this tree
# draws from the numpy GLOBAL state, so the twelve np.random.seed(...) calls in the tree
# seed a stream no line reads. Its predicate fires on a file that does draw globally and
# stays silent on own_size_control.py and t1_toxicity_skew_backtest.py, which permute
# through their own generators.
#
# So 46 files touch randomness, and FIVE of them draw no number that can reach an artifact:
# build_quickwin_markouts.py, check_first.py, i4_l2_mid.py and m8_makerside.py hold no
# generator at all, each saying so in its own comment, and i4_midmarkout.py holds one only
# inside _selftest, reached from a separate entry mode. That leaves 41 files whose draws
# reach a published number. The ten once named here as opening a generator on this scalar
# included two of the five.
#
# WHERE THE 46 GET THEIR STREAM, each file filed under the weakest rule it uses:
#
#     5   the declared rule: this module, stats.py through it, and the three consumers
#         ws1_horizon_persistence.py, ws2_hard_classifier.py, ws3_taker_pnl.py
#     1   the joined form: panel_persistence.py, whose two base seeds are BOTH read from
#         here (RELIABILITY_SEED and seed_for) and only whose rule is local. It was filed
#         before as reaching no declaration at all, and that was wrong: what is local is
#         the rule, not the seed
#    23   the base seed alone, of which four hold no generator and one draws only in a
#         self-test, so 18 draw live; one of the 23, the classifier script not
#         published in this repository, arrives through sklearn on a typed literal
#    13   the base seed plus arithmetic on the loop coordinates
#     2   child seeds drawn from a parent generator: i2_walletfe.py, panel_common_idio.py
#     2   an integer built from the DATA LABEL, with no declared seed reachable at all:
#         the per-day heterogeneity ratio of ks2_persistence_10day.py and
#         ks2_markout_multiday.py
#
# WHAT THE LAST THREE COST, measured rather than argued.
#
# The arithmetic form COLLIDES. In i3_nonrecoverability_oos.py the three streams are seeded
# RNG_SEED + K + h, RNG_SEED*3 + K + h and RNG_SEED*7 + K + h; over the declared grid
# PERSISTENCE_FLOOR_FILLS (50, 100) and horizons (60, 10) the cell at 50 fills and 60
# seconds takes the SAME integer as the cell at 100 fills and 10 seconds, in all three
# streams. The same arithmetic runs in i3_book_comparator.py, and in panel_analyze.py with
# a period offset, where it collides once per period over three periods. The instrument is
# calibrated on the opposite case over the same grid: colliding_cells on those four cells
# named as identities returns nothing, and returns a group when handed a pair that does
# collide.
#
# The child-seed form SHARES A DRAW BETWEEN TWO FILES. i2_walletfe.py and
# panel_common_idio.py each open a generator on this scalar and take the first five
# integers from it, and the five are the same five in both: 868994903, 2121061393,
# 1705320240, 1051228009, 269056115. Each file uses them to assign wallets to halves, so
# wherever the two wallet sets overlap the two files perform one split and not two. The
# same construction on MASTER_SEED + 1 returns a different five, so the comparison can tell
# them apart. The form is order-dependent as well: the permutation seed of each (slice, K)
# is drawn inside the loop, so adding a slice moves every later seed.
#
# The data-label form is UNREACHABLE FROM ANY SEED. int(day)*4 plus a coin offset contains
# no declaration of this module, so a sweep over the declared seed cannot move the per-day
# variance ratio those two files report, and that ratio sits outside every sensitivity read
# the work performs on its seed.
#
# WHAT ADOPTION COSTS, and the question this number answers is what ONE run of every node
# whose draws change costs, at the runtime its own artifact last recorded. It is NOT the
# cost of changing the VALUE declared here: that walks the complement of this population
# and is what build.py --what-if answers. Recorded: 333.3 minutes over 33 of the 37 nodes
# that move. The other four have no recorded runtime and are named rather than guessed --
# forward_toxicity.py, ks2_markout_multiday.py, panel_build.py, probes/probe_G_horizon.py
# -- so the total is a lower bound. panel_persistence.py does NOT move under this decision,
# and that is part of why the joined form was chosen: it walks the tape, has thirteen
# downstream nodes, carries no recorded runtime, and holds 96 published cross-month
# p-values that migrating it onto the flattened form would redraw.
#
# Moving any consumer onto the rule redraws its streams and moves the numbers in its own
# results file, so it is a measured change owed a recompute and a leaf-by-leaf comparison,
# not a rename.
MASTER_SEED = 20260620

# The split-half reliability seed, kept separate ON PURPOSE. It seeds a different
# estimator -- the within-wallet odd/even split -- and its three consumers
# (ks2_persistence_10day.py, panel_persistence.py, panel_common_idio.py) all bind this
# name rather than retype the value, so their reliability tables are comparable cell
# for cell. Folding it into MASTER_SEED would break that comparison for no gain.
RELIABILITY_SEED = 20240601

# Measured, so the seed choice is not a matter of faith: sweeping 50 seeds through the
# reliability estimator moves the headline book-mid persistence on BTC at the 50-fill
# floor from 0.8191 to 0.8524 around a shipped 0.8417, a standard deviation of 0.0086.
# The seed does not carry the result. This number belongs in the report beside the
# persistence, because a reader is entitled to ask.
RELIABILITY_SEED_SPREAD_SD = 0.0086

# WHICH SEED EACH CONSUMER DRAWS FROM, and why that has to be a map rather than one
# number.
#
# WHY A SEED BELONGS TO A PURPOSE AND NOT TO THE WORK. Two scripts that open their
# generator on the same integer draw the same uniforms in the same order. Whatever each
# one then computes, the two results carry a single draw between them, so a difference
# between them is not only a difference between their statistics -- which is the one
# property MASTER_SEED was chosen for. A stream is separated in one of two ways: give the
# purpose its own seed, or derive the stream from (MASTER_SEED, cell) as rng() does. The
# second needs no declaration at all and is where this module is going. The first is what
# the tree holds today, and this map is where it is written down.
#
# WHAT THE TREE HOLDS, counted by syntax tree on 2026-07-31 and recounted after the
# migration of that day rather than estimated. Twenty-six purposes draw a seed, and they
# carry SEVEN distinct values between them, not twenty-six. Nine consumers share 20260619,
# eight probes share 690 and three share 20260623. So the tree does not have one seed per
# purpose, and this map does not claim that it does: it records what each consumer draws,
# and the sharing is visible in it because the values repeat.
#
# WHY EACH VALUE IS WHAT IT IS, which is the operative reason and is a different one from
# the paragraph above. Each of these is the value some published artifact was drawn under.
# Binding a consumer to MASTER_SEED redraws its streams and moves the numbers in its own
# results file, so adopting the declaration is a measured change owed its own recompute
# and its own leaf-by-leaf comparison, not a rename. Every one of these sites already says
# so in its own comment and stamps the difference into its artifact's fingerprint as a
# stated override. MASTER_SEED stays the target; this map is the record of the distance
# still to travel, and it shrinks as consumers move onto rng().
SEED_BY_PURPOSE = {
    # 20260619, shared by nine consumers.
    "build_quickwin_markouts": 20260619,
    "confound_asymmetry": 20260619,
    "i3_nonrecoverability_oos": 20260619,
    "i5_exclusion": 20260619,
    "m4_realizedpnl": 20260619,
    "m8_makerside": 20260619,
    "m9_crossasset": 20260619,
    "t1_toxicity_skew_backtest": 20260619,
    "t3_capacity": 20260619,
    # the maker-economics and quoting group.
    "maker_econ": 20260621,
    "as_quoter": 20260622,
    "follow_the_informed_oos": 20260622,
    "maker_econ_b2": 20260622,
    "gm_quoter": 20260623,
    "mm_bakeoff": 20260623,
    "forward_toxicity": 20260623,
    # 690, shared by eight probes.
    "c2_bookstate_control": 690,
    "c_matched_precision": 690,
    "decay_curve": 690,
    "kss_decomp_c": 690,
    "kss_decomp_c_bookmid": 690,
    "probe_D_funding": 690,
    "probe_E_leadlag": 690,
    "probe_F_hlp_liq": 690,
    # two streams that belong to one estimator each rather than to a whole script.
    # The correlation null is named separately from panel_persistence.py because that
    # file also draws the reliability split, and the split binds RELIABILITY_SEED.
    "panel_persistence_correlation_null": 424242,
}


def seed_for(purpose):
    """The seed one named purpose draws from. Raises on a purpose not declared here.

    A consumer needing its own stream has two legitimate moves and this is the second of
    them: derive the stream from MASTER_SEED through rng(), which needs no declaration,
    or declare the purpose here beside what it draws. Typing a fresh literal is the third
    move and is the one checks/chk_settings_home.py counts.
    """
    if purpose not in SEED_BY_PURPOSE:
        raise ValueError(
            f"no seed is declared for the purpose {purpose!r}. Either derive the stream "
            f"from MASTER_SEED through rng(), which needs no declaration, or add the "
            f"purpose here with the value its published artifact was drawn under")
    return SEED_BY_PURPOSE[purpose]


def _refuse_ambiguous_cell(cell):
    """Refuse a cell identity that cannot mean exactly one thing. Changes nothing else.

    WHY THIS IS A REFUSAL AND NOT A BETTER ENCODING. The flattening below writes a
    string as its character codes and an integer as itself, with nothing marking where
    one component ends and the next begins, so rng("AB") and rng(65, 66) return one
    stream. The obvious repair is to mark the boundaries -- stats.py does exactly that
    at its own layer, prefixing each component with its length. Doing it HERE would be
    a different repair with a different price: every existing cell would flatten to a
    new sequence, so every permutation p-value and every bootstrap interval in the tree
    would move, all of them because of a defect that the census below shows has never
    fired. A guard that refuses costs no number; a re-encoding costs all of them.

    WHAT IS REFUSED, and why each case is ambiguous under ANY convention, so that none
    of these rules can be argued away by adopting a different encoding later:

      * no components at all -- every caller would then share the head seed, which is
        the single global generator the docstring below exists to avoid.
      * an empty string -- it contributes no character codes, so ("a", "", "b") and
        ("a", "b") are one sequence.
      * a bool -- True flattens through int() to 1 and collides with the integer 1.
      * a float -- 10.0 flattens to 10 and collides with the integer 10, and the same
        quantity is stored at different precisions in different files, so two runs
        would seed differently while naming one cell.
      * a cell that NAMES nothing: all components integers. This is the case that
        closes rng("AB") against rng(65, 66), and it is not a rule invented here --
        it is the contract stats.rng already states in its own docstring, "pass at
        least the name of the quantity being computed", enforced one level down where
        the generator is actually built rather than only in the module above it. A bare
        run of integers is a coordinate, not a name, and a coordinate is what a spelled
        out string looks like.

    WHAT REMAINS OPEN, said plainly because a guard that oversells itself is worse than
    none. Two named cells can still collide: ("ws1", "placebo") and ("ws1", "plac",
    "ebo") flatten alike, and no per-call rule can separate them, because the defect is
    in the relation between two designations and not in either one. Closing that needs
    the boundary marking stats.py does, at the price named above. What makes the gap
    tolerable is that it is MEASURED rather than assumed: cell_key below exists so the
    designations a run actually uses can be compared for collision, and over the 148
    the tree produces the only colliding pair is the one stats.py builds on purpose to
    demonstrate this defect.
    """
    if not cell:
        raise ValueError(
            "a generator needs a cell identity. Pass at least the name of the quantity "
            "being computed, so that two procedures do not share a stream in silence")
    named = False
    for c in cell:
        if isinstance(c, bool):
            raise TypeError(
                f"a bool ({c!r}) in a cell identity: it flattens to {int(c)} and shares "
                f"a stream with that integer. Name the arm with a string instead")
        if isinstance(c, str):
            if not c:
                raise ValueError(
                    "an empty string in a cell identity contributes no character codes, "
                    "so it makes the identity equal to the same cell without it. Name "
                    "the component or leave it out")
            named = True
        elif not hasattr(type(c), "__index__"):
            raise TypeError(
                f"a cell component is a {type(c).__name__}; a cell is built from "
                f"strings and integers only. A float cannot be a cell identity because "
                f"it flattens to its truncation and because the same quantity is stored "
                f"at different precisions in different files, so two runs would seed "
                f"differently while naming one cell")
    if not named:
        raise ValueError(
            f"the cell identity {cell!r} is all integers, so it names nothing and cannot "
            f"be told apart from a string spelled out as its character codes: rng('AB') "
            f"and rng(65, 66) are the same stream. Lead with the name of the quantity")
    return cell


def cell_key(*cell):
    """The exact sequence rng() seeds from. Two cells share a stream iff these are equal.

    Exposed so that "no two cells in this run collide" is something a check can compute
    rather than something a comment asserts. rng() flattens through this function, so
    there is one flattening in the repository and not a second one written to inspect
    the first.
    """
    parts = [MASTER_SEED]
    for c in _refuse_ambiguous_cell(cell):
        if isinstance(c, str):
            parts.extend(ord(ch) for ch in c)
        else:
            parts.append(int(c))
    return parts


def colliding_cells(designations):
    """Groups of designations that share one stream. Empty means the run is clean.

    `designations` is an iterable of cell tuples. Returns a list of lists, each holding
    the designations that flatten alike.
    """
    seen = {}
    for cell in designations:
        seen.setdefault(tuple(cell_key(*cell)), []).append(tuple(cell))
    return [group for group in seen.values() if len(group) > 1]


def rng(*cell):
    """A generator for one named cell, derived from MASTER_SEED and the cell identity.

    Why a function and not a constant. A single global generator makes a result depend
    on the ORDER cells are computed in, so inserting a coin or a period silently
    changes an earlier cell. A per-cell literal seed has the opposite defect: two
    cells drawing the same stream look independent and are not. Deriving the stream
    from (MASTER_SEED, cell) gives both properties -- order-independent and distinct.

    The cell identity must be built from values, never from hash() of a string:
    Python salts string hashing per process unless PYTHONHASHSEED is set, so a seed
    derived that way differs on every run. The note is here because that defect was
    made and measured rather than imagined: an earlier draft of the three-coin
    persistence scoring opened each reliability split on abs(hash(...)) % 2**32, and
    the same split asked in three processes on 2026-08-05 returned 3204786889,
    2192008809 and 128567485 -- an artifact its own author could not reproduce.

    What the identity may and may not be is stated at _refuse_ambiguous_cell, together
    with the reason the ambiguity is closed by refusing rather than by re-encoding.
    """
    import numpy as np
    return np.random.default_rng(cell_key(*cell))


# =====================================================================
# 4. RESAMPLING BUDGETS
# =====================================================================

# Benjamini-Hochberg level for every family of cells. Conventional rather than derived:
# 0.05 is the level the discipline reports at, and the procedure it belongs to is named
# in every artifact that applies it (the `method` field reads "Benjamini-Hochberg
# (numpy-only, step-up)"). Already 0.05 everywhere it is declared; recorded here so a
# fifth file cannot introduce a different one. It stands FIRST in this section because
# the permutation budget below is computed from it.
FDR_ALPHA = 0.05

# The family the permutation budget is sized for. Read off an artifact rather than
# typed: panel_persistence_results.json records cross_month_fdr.family_size, which
# panel_persistence.py counts from the cells it actually tested.
#
# THIS IS ONE FAMILY AND NOT THE WORK, which matters because the budget follows from
# the size. The same key reads 448 in the three panel_extended_results_*_all.json arms,
# 20 in own_size_control_results.json, 8 in panel_common_idio_results.json and 4 in
# both ks2 files. The cross-month family is the one sized for here because it is the
# family the cross-month persistence claim is corrected in, which is the claim with the
# smallest p to assert. A script whose family is larger does not inherit this number:
# it passes its own size to min_perm_draws and gets its own budget, which is why the
# size is an argument and not a constant inside the function.
#
# The same key records n_distinct_comparisons = 24 beside it. family_size counts
# ORDERED period pairs and so counts every comparison twice; 24 is the number of
# distinct comparisons and is what prose quotes. The larger of the two is used here,
# because a budget sized for the larger count clears the smaller one as well.
PERM_FAMILY_SIZE = 48

# How much room the p-value floor is required to have under the corrected threshold.
# A budget that only just clears the threshold puts every floored p on the boundary,
# where the last digit of the correction decides the verdict. Requiring the floor to
# sit at half the threshold is a stated judgement and not arithmetic, and it is written
# down because it is exactly the difference between the 1000 draws the requirement on
# its own asks for and the 2000 the work runs. A reviewer may contest this number; the
# inequality it feeds is not contestable.
PERM_FLOOR_MARGIN = 2


def min_perm_draws(family_size=PERM_FAMILY_SIZE, alpha=FDR_ALPHA,
                   margin=PERM_FLOOR_MARGIN, quantum=1000):
    """Smallest permutation budget whose p-value floor clears a corrected threshold.

    The requirement in one line: a single significant cell has to be able to clear the
    multiplicity correction ON ITS OWN, with no help from the rest of its family.
    Benjamini-Hochberg compares the smallest-ranked p against alpha/m, so the floor
    1/(N+1) has to satisfy

        1 / (N + 1)  <=  alpha / (margin * m)

    and the budget is therefore a function of the LEVEL and the FAMILY SIZE rather than
    a number anyone gets to type. Reading the inequality the other way is the reason it
    is worth enforcing: a budget too small for its family cannot produce a significant
    result at rank one however strong the effect is, and it fails silently, by reporting
    a p at the floor that the correction then rejects.

    At alpha 0.05 and m 48 the bare requirement is 959 draws. With the margin it is
    1919. Rounded up to a whole thousand -- because a budget is quoted in thousands of
    draws and two scripts are compared on that figure -- it is 2000, which is the value
    the work runs.

    quantum=1 returns the bare minimum unrounded, which is what a caller wants when it
    is checking a budget rather than choosing one.
    """
    if family_size < 1 or alpha <= 0 or margin <= 0 or quantum < 1:
        raise ValueError(f"min_perm_draws needs family_size >= 1, alpha > 0, "
                         f"margin > 0 and quantum >= 1; got {family_size}, {alpha}, "
                         f"{margin}, {quantum}")
    threshold = alpha / (margin * family_size)
    # Step UP from a deliberate under-estimate rather than taking a ceiling of the
    # closed form. alpha is not exactly representable, so a ceiling can land one draw
    # short and hand back a budget whose floor sits just above the threshold -- the one
    # failure this function exists to prevent.
    n = max(1, int(margin * family_size / alpha) - 2)
    while 1.0 / (n + 1) > threshold:
        n += 1
    return -(-n // quantum) * quantum


# Label-permutation draws. The budget sets the p-value FLOOR at 1/(N+1), and a p
# reported at the floor is not a measurement: it says no draw beat the observed value
# and the true p is unknown below that point. So the value is not chosen; it is what
# the level and the family size above leave room for.
#
# Six scripts still run at 200 (i2_walletfe, own_size_control, panel_common_idio,
# ws1_horizon_persistence, ws2_hard_classifier, ws3_taker_pnl). Their floor is 0.00498
# against a corrected threshold of 0.05/48 = 0.00104, so no p of theirs can clear rank
# one at any effect size. Raising them changes their reported p-values, which is why
# this value is a target and not in force.
N_PERM = min_perm_draws()

# Bootstrap resamples. Arithmetically obliged in the same shape as N_PERM but from a
# different requirement, and still a literal because the requirement has not been
# written as an expression yet. The budget sets how many draws land in each tail of a
# 95% percentile interval, N * 0.025, and therefore how far the endpoint moves between
# seeds. The stated requirement is fifty draws per tail, and 50 / 0.025 = 2000.
#
# EVERY CONSUMER NOW DRAWS THIS BUDGET, adopted 2026-07-31. Until that day the map below
# held 1000 twice, 500 twice and 300 once -- 25, 12.5 and 7.5 draws per tail against the
# fifty this line asks for -- and each shortfall was declared debt rather than a second
# opinion. The debt is paid by raising the map, not by lowering this number: the five
# consumers all compute the same object, the two endpoints of a 95 percent percentile
# interval, and none of them argued it needed fewer draws.
#
# A SIXTH CONSUMER WAS FOUND THE SAME DAY and it is the reason this paragraph does not
# say "five". m11_concentration.py spells its budget BOOTSTRAP_DRAWS and held the literal
# 800, so it was outside every alias list the settings gate counts by and outside the map
# below; the sentence that used to stand here, "outside this line the tree holds no
# bootstrap-budget literal at all", was a census taken with a predicate that could not see
# it. That is the same mechanism as t3_capacity.py's BOOTSTRAP_N, found one paragraph and
# one day earlier, and the repair is the same: give the site a home and widen the list.
N_BOOT = 2000


def p_floor(n_perm=N_PERM):
    """The smallest p a budget of n_perm draws can express."""
    return 1.0 / (n_perm + 1)


def p_is_floored(p, n_perm=N_PERM, tol=1e-12):
    """True when a reported p is the budget's floor rather than a measurement.

    Every artifact that reports a p reports this beside it. A p of exactly 0.0 is
    impossible from a permutation test and means the floor was not applied.
    """
    return abs(float(p) - p_floor(n_perm)) <= tol


# HOW MANY DRAWS EACH CONSUMER TAKES, and the distinction that makes some of these
# numbers a different quantity from N_PERM rather than a shortfall against it.
#
# N_PERM answers exactly one question: how many draws does a p-value need before its
# floor can survive the multiplicity correction. A set of draws that never becomes a p
# is not asking that question, so the inequality min_perm_draws enforces has nothing to
# bind on, and a budget sized by it would be sized by a requirement that does not apply.
#
# THE TWO ks2 NODES ARE THAT CASE, and it was read in the code rather than inferred.
# ks2_persistence_10day.heterogeneity_ratio and the matching block in
# ks2_markout_multiday.py average their draws into v_perm, and v_perm is the DENOMINATOR
# of the variance ratio V_real / V_perm. No threshold is applied to that ratio and no p
# is reported from it, so what 1000 draws buy there is the precision of a denominator and
# not the resolution of a p-value. Both files draw their correlation p-values from a
# SECOND budget, bound to N_PERM, in the same run. So 1000 beside 2000 in those two files
# is two quantities standing side by side, which is why collapsing them to one number
# would move one of them.
#
# THE OTHER TWO PERMUTATION ENTRIES ARE NOT THAT CASE and are recorded as what they are.
# The lead-lag placebo runs 50 draws because a Hayashi-Yoshida scan over raw ticks is
# what each draw costs; its floor is 1/51 = 0.0196, the probe prints that floor in its own
# artifact, and its stated criterion is whether the placebo distribution is beaten rather
# than a corrected p. The size-matched placebo runs 1000, whose floor is 1/1001 =
# 0.000999. Against the family this module sizes for, PERM_FAMILY_SIZE 48, the bare
# corrected threshold is 0.05/48 = 0.001042, so that floor clears the bare requirement by
# four percent and fails the margin PERM_FLOOR_MARGIN asks for -- which is exactly the
# boundary position that constant exists to forbid. The comparison is against the DECLARED
# reference family and not against that file's own, which it counts for itself; what the
# arithmetic settles is that 1000 leaves no room, not by how much. Recording a number here
# is not endorsing it.
PERM_DRAWS_BY_PURPOSE = {
    "ks2_persistence_per_day_variance_ratio": 1000,
    "ks2_markout_per_day_variance_ratio": 1000,
    "leadlag_randomised_lag_placebo": 50,
    "t1_size_matched_placebo": 1000,
}

# Bootstrap resamples each consumer draws. The quantity that matters is not the budget
# but N * 0.025, the number of draws landing in each tail of a 95% percentile interval,
# because that is what fixes how far an endpoint moves between seeds. N_BOOT declares
# fifty per tail, and since 2026-07-31 every entry below is that declaration.
#
# WHY THE MAP SURVIVES THE ADOPTION rather than being deleted. It is the place a consumer
# that genuinely needs a different budget states so, next to the reason, the way
# PERM_DRAWS_BY_PURPOSE holds two entries that are a different quantity from N_PERM and
# not a shortfall against it. No bootstrap consumer is in that position today: all six
# compute the two endpoints of a percentile interval and none of them asks a question the
# tail count does not bear on. So the map holds one value six times, by reference and not
# by copy, and an entry that ever departs from the declaration will have to say why in
# writing rather than by holding a smaller integer.
#
# WHAT THE ADOPTION MOVES, and it is narrower than it sounds. A point estimate here is
# computed from the data, never from the resamples, so no point estimate moves. What moves
# is the two endpoints, and they move by the noise of a larger draw and in no direction:
# the interval does not become systematically wider or narrower. What does shrink is the
# spread of the endpoint between seeds, by sqrt(N_new / N_old) -- 1.41 for the two former
# thousands, 2.00 for the two former five-hundreds, 2.58 for mm_bakeoff and 1.58 for
# m11_concentration.
#
# ONE CONSUMER'S DRAWS DO NOT ONLY SET AN ENDPOINT, and this is worth saying because the
# sentence above is otherwise read as covering the whole map. ws1_horizon_persistence.py
# takes np.nanstd of its draws as boot_se, and boot_se is the width of the parsimony
# tie-break in its horizon selection: a candidate horizon enters within_1se when its
# disattenuated persistence clears the maximum minus one boot_se. So there the budget
# feeds a discrete list and not only a band. On the grid as it stands the list cannot
# change hands -- the maximum sits at the shortest horizon of the grid and the rule takes
# the minimum of the list, and the runner-up is 0.0047 below a threshold that would need
# boot_se a third larger to reach -- but the mechanism is there and the recompute has to
# be read with it in mind.
#
# TWO SITES WERE INVISIBLE TO THE SETTINGS GATE AND FOR THE SAME REASON, which is why the
# map is a record of the tree and not a mirror of the gate. t3_capacity spells its budget
# BOOTSTRAP_N, a spelling no alias list carried until 2026-07-31; m11_concentration spells
# it BOOTSTRAP_DRAWS, which no alias list carries even now, and held the literal 800.
#
# mm_bakeoff.py WAS A THIRD DEFECT AND A DIFFERENT ONE. It read its budget as
# `int(os.environ.get("CAP_N_BOOT", "300"))`, so the declared default lived inside a
# string inside a call and the effective budget was a property of the machine the run
# happened on. The environment read was removed with this adoption: leaving it would have
# let a shell variable overrule the declaration silently, which is the defect this module
# exists to remove and not a convenience.
BOOT_DRAWS_BY_PURPOSE = {
    "maker_econ": N_BOOT,
    "t3_capacity": N_BOOT,
    "ws1_horizon_persistence": N_BOOT,
    "ws3_taker_pnl": N_BOOT,
    "mm_bakeoff": N_BOOT,
    "m11_concentration": N_BOOT,
}


def perm_draws(purpose):
    """The permutation budget one named purpose draws. Raises on an undeclared purpose."""
    if purpose not in PERM_DRAWS_BY_PURPOSE:
        raise ValueError(
            f"no permutation budget is declared for {purpose!r}. A budget whose draws "
            f"become a p-value takes min_perm_draws() and is not declared here at all; "
            f"this map is for draws that answer a different question, and an entry has "
            f"to say which question")
    return PERM_DRAWS_BY_PURPOSE[purpose]


def boot_draws(purpose):
    """The bootstrap budget one named purpose draws, with its per-tail count available
    from draws_per_tail(). Raises on an undeclared purpose."""
    if purpose not in BOOT_DRAWS_BY_PURPOSE:
        raise ValueError(
            f"no bootstrap budget is declared for {purpose!r}; add it here with the "
            f"number of draws it puts in each tail, or read N_BOOT")
    return BOOT_DRAWS_BY_PURPOSE[purpose]


def draws_per_tail(n_boot=N_BOOT, tail=0.025):
    """Draws landing in each tail of a percentile interval, which is what a budget buys.

    Stated as a function because the budget on its own says nothing: 500 draws is twelve
    and a half per tail at a 95 percent interval and two and a half at 99, and it is the
    per-tail count that fixes how far an endpoint moves between seeds.

    The argument is the TAIL MASS and not the coverage, which is not a matter of taste
    here. Deriving the tail from a coverage costs a subtraction that binary cannot do
    exactly: 1 - 0.95 is 0.05000000000000004, so the declared budget came back as
    50.00000000000004 draws per tail rather than fifty. The tail mass is the number
    N_BOOT's own reasoning is written in, and 2000 * 0.025 is exactly 50.
    """
    if not 0.0 < tail < 0.5:
        raise ValueError(f"the tail mass has to sit strictly between 0 and 0.5; got "
                         f"{tail}. Pass 0.025 for a 95 percent interval")
    return n_boot * tail


# =====================================================================
# 5. WALLET ELIGIBILITY: THREE DIFFERENT QUANTITIES, NOT ONE SETTING
# =====================================================================

# These three are separate numbers because they gate three different populations. The
# tree currently spells them K_LIST, K_VALUES, KMIN, K_HEADLINE, K_POOL, K_HALF_MIN
# and K, which is how one artifact came to hold 206, 207 and 966 wallets all called
# the toxic decile.

# (a) RANK FLOOR: minimum fills in the ranking window for a wallet's score to be a
# measurement of that wallet rather than of noise. Decided by the MEASURED split-half
# reliability: at a 10-fill floor (ws1_horizon_results.json runs at K_primary 10)
# pooled["10"] reports rel_early 0.333 and rel_late 0.386, so the disattenuation
# multiplier is 2.79 and two thirds of the corrected persistence is the correction. At
# 50 to 100 fills ks2_persistence_10day_results.json reliability[*] reports 0.610 to
# 0.870, a multiplier of 1.15 to 1.56. The range 0.33 to 0.61 stood here before and is
# not the range of those cells: 0.61 is their low end and 0.33 is the 10-fill figure
# from the sentence above, so the two floors were reported as one range. The multiplier
# was right either way, and it carries the argument: 50 is the lowest floor at which the
# score is mostly signal, and 10 stays as a reported sensitivity and never as a headline.
#
# ADOPTED BY EVERY HEADLINE ON 2026-07-31. Until that day four files pointed their prose
# at the 10-fill rung while this line declared 50, and the four multipliers behind the
# choice were read out of the two artifacts first-hand rather than quoted: at ten fills
# ws1_horizon_results.json pooled["10"] gives rel_early 0.3331 and rel_late 0.3859, so
# 1/sqrt(rel_early * rel_late) is 2.7891 and the same file's rho_disatt / rho_obs is
# 2.7891 to four figures; at fifty and a hundred fills the four cells of
# ks2_persistence_10day_results.json reliability[*] give 1.1514, 1.2285, 1.4267 and
# 1.5626. So the correction is 64 percent of the corrected number at ten fills and
# between 13 and 36 percent at the declared floor.
RANK_FLOOR_FILLS = 50
RANK_FLOOR_SENSITIVITY = (10, 25, 50, 100)

# (b) PERSISTENCE FLOOR: minimum fills in EACH half. A wallet needs the count twice,
# so the same total buys half the precision per half. This is a different number from
# (a), not a stricter setting of it. Nine files already agree on (50, 100): 50 is the
# cell, 100 is the check that the cell is not a small-sample artifact.
PERSISTENCE_FLOOR_FILLS = (50, 100)

# (c) PER-DAY FLOOR: minimum fills within one day, for the day-over-day reads. Lower
# than (b) because a day is a fifth of a half.
DAY_FLOOR_FILLS = 25

# Minimum common wallets for a rank correlation to be reported without a flag. Below
# this a rank correlation is noise; the cell is still computed, and marked.
MIN_COMMON_WALLETS = 30

# WHAT EACH CONSUMER ACTUALLY RUNS, and why the declarations above cannot hold it.
#
# RANK_FLOOR_FILLS is one number and the consumers hold a LADDER each. That is not the
# same object seen at different values: a file that reports every rung of a sweep is
# reporting the curve as its finding, so a scalar declaration cannot be what it reads
# without deleting the finding. Three files sweep (10, 50), one sweeps (20, 50), one
# sweeps (30, 50, 100) and one sweeps (10, 20, 50, 100, 200), and the differences are the
# questions rather than drift -- the widest ladder belongs to the cross-asset portability
# read, where the whole point is watching a coefficient settle as the floor rises. So the
# declaration has to admit a per-consumer ladder, and averaging the six into one would
# answer none of them.
#
# THE PAIR (10, 50) AGAINST (50, 100) IS NOT ONE SETTING AT TWO VALUES, and reading it as
# one is what a census by value rather than by role produces. (50, 100) is
# PERSISTENCE_FLOOR_FILLS, a floor on EACH HALF, read by seven files and mirrored by the
# notebook. (10, 50) is the `sweep` role below, the ranking-window floor three files
# report a curve over. The two ladders gate different populations and answer different
# questions, so there is nothing to reconcile between them; what there was to do was give
# each a home, and both have one.
#
# The roles inside each entry are separate quantities and are named rather than ordered.
# "sweep" is every rung the file reports. "headline" is the rung its prose points at, and
# FOUR files declare one, not three: maker_econ.py, maker_econ_b2.py and mm_bakeoff.py
# spell it K_HEADLINE and ws3_taker_pnl.py spells it K. The count of three stood in this
# comment, in SETTING_STATE below and in the plan, and it was wrong in all three the same
# way -- it was taken by reading the three files that also declare a sweep, so the one
# consumer with a headline and no sweep fell out. All four held 10 against the 50
# RANK_FLOOR_FILLS declares; all four read the declaration from 2026-07-31, so the role
# now carries the declared floor rather than the distance to it. "both_halves" and
# "each_split_half" are floors
# on a HALF and not on the ranking window at all, so they belong beside
# PERSISTENCE_FLOOR_FILLS rather than beside RANK_FLOOR_FILLS -- and the two halves in
# question are different halves, the early/late split in one case and the odd/even split
# of the reliability estimator in the other.
#
# THE FIVE ENTRIES ADDED ON 2026-07-31 WERE INVISIBLE TO THE GATE, and that is worth
# saying because it is why they went unrecorded rather than being refused. Three of them
# spell the floor `K`, one spells it `MIN_FILLS` and one spells it `KS`, and none of those
# three spellings was in the alias list checks/chk_settings_home.py counts by, so the
# gate's own docstring was right when it called its figure a floor and not a census. The
# alias list was widened the same day, which is why the count could rise without anything
# in the tree having got worse; the sites were migrated first so that it did not.
#
# Two of the five are the SAME quantity as the entries above at a different value, and
# three are a floor on a HALF. ws3_taker_pnl is the one entry whose single number does two
# jobs in its own file: it gates a single-window fill count for the rank correlation and
# each half of the out-of-sample split, so it is recorded under the role its prose points
# at and the second use is named here rather than given a role of its own.
#
# THE SWEEPS ARE NOT RAISED WITH THE HEADLINES and the difference is the whole reason the
# map has roles. A sweep is the curve the file reports as its finding, so (10, 50) stays
# (10, 50) and the loose rung goes on being computed and published; what changes is which
# rung the prose points at. In maker_econ.py and mm_bakeoff.py both rungs already sit in
# the artifact under the keys K10 and K50, so the headline moving is a change of which
# block is cited. In maker_econ_b2.py it is not: that file builds both label sets and
# writes only the headline one, so its published surface is computed at the headline and
# at nothing else. ws3_taker_pnl.py has no sweep at all.
WALLET_FILL_FLOOR_BY_PURPOSE = {
    "maker_econ": {"sweep": (10, 50), "headline": RANK_FLOOR_FILLS},
    "maker_econ_b2": {"sweep": (10, 50), "headline": RANK_FLOOR_FILLS},
    "mm_bakeoff": {"sweep": (10, 50), "headline": RANK_FLOOR_FILLS},
    "i2_walletfe": {"sweep": (30, 50, 100)},
    "m9_crossasset": {"sweep": (10, 20, 50, 100, 200)},
    "eb_scoring": {"both_halves": 30},
    "temp_perm_decomp": {"each_split_half": 20},
    "m2_figure": {"both_halves": 10},
    "persistence_crosswindow": {"sweep": (20, 50)},
    "ws2_hard_classifier": {"both_halves": 10},
    "ws3_taker_pnl": {"headline": RANK_FLOOR_FILLS},
}


def wallet_fill_floor(purpose, role="sweep"):
    """One consumer's fill floor for one named role. Raises rather than substituting.

    The role is required and has no useful default beyond the sweep, because the roles
    are different quantities: handing back a headline where a sweep was asked for would
    return a number that is valid, plausible and about something else, which is the exact
    failure this module exists to make impossible.
    """
    if purpose not in WALLET_FILL_FLOOR_BY_PURPOSE:
        raise ValueError(
            f"no wallet fill floor is declared for {purpose!r}; read RANK_FLOOR_FILLS if "
            f"the consumer wants the declared floor, or add the consumer here with the "
            f"ladder it reports")
    entry = WALLET_FILL_FLOOR_BY_PURPOSE[purpose]
    if role not in entry:
        raise ValueError(
            f"{purpose!r} declares no {role!r} floor; it declares {sorted(entry)}. These "
            f"are different quantities and not one setting at different values, so the "
            f"missing one is not substituted from the others")
    return entry[role]


# =====================================================================
# 6. WHALE-DROP ROBUSTNESS: THE CRITERION IS THE SETTING, NOT THE COUNT
# =====================================================================

# How many of the largest counterparties are dropped to answer "is this ten wallets?".
# The answer is not binary and the ladder is the finding: t3_results.json shows the
# avoidable share falling from 0.9104 to 0.7068 at a drop of ten and to 0.5243 at
# fifty.
WHALE_DROP_K = 10
WHALE_DROP_LADDER = (10, 50, 100)

# Dropping the ten largest by notional answers "is this a volume artifact"; by cost it
# answers "is this ten wallets". Different questions, different answers, and the tree
# writes both under one key name. The accessor makes the criterion required so no
# artifact can say "top 10" without saying top 10 by what.
WHALE_DROP_CRITERIA = ("notional", "fill_count", "abs_realized_pnl", "gross_cost")


def whale_drop(criterion, k=WHALE_DROP_K):
    """The (k, criterion) pair for one whale-drop arm and the key that names both."""
    if criterion not in WHALE_DROP_CRITERIA:
        raise ValueError(f"unknown whale-drop criterion {criterion!r}; declare it in "
                         f"WHALE_DROP_CRITERIA together with what it answers")
    return {"k": int(k), "criterion": criterion,
            "key": f"drop_top{int(k)}_by_{criterion}"}


# =====================================================================
# 7. COINS: THE CODE MAP IS A PROPERTY OF THE FILE, NOT OF THE PROJECT
# =====================================================================

# Verified by loading both files: quickwin_markouts.npz carries codes {0, 1};
# panel_markouts.npz carries {0, 1, 2}. One project-wide map would be wrong for one of
# them, and the failure is silent, because a code valid in both files relabels BTC as
# ETH without raising. So the map is keyed by artifact and the accessor demands the
# artifact's name.
COIN_CODES_BY_ARTIFACT = {
    "quickwin": {0: "BTC", 1: "ETH"},
    "panel": {0: "BTC", 1: "ETH", 2: "SOL"},
    "forward": {},          # the forward feed carries coin symbols, not codes
}


def coin_labels(artifact):
    """code -> symbol for one artifact. Raises on an artifact not declared here."""
    if artifact not in COIN_CODES_BY_ARTIFACT:
        raise ValueError(
            f"no coin code map declared for {artifact!r}; the map belongs to the FILE "
            f"(quickwin carries {{0,1}}, panel carries {{0,1,2}}), so add the file "
            f"with its own map rather than reusing another file's")
    return dict(COIN_CODES_BY_ARTIFACT[artifact])


def coin_codes(artifact):
    """symbol -> code, the inverse, built here so no file writes its own."""
    return {v: k for k, v in coin_labels(artifact).items()}


# THE SECOND FORM, and why there are two forms rather than one written twice.
#
# The map above answers "what does the integer 1 mean in this file", which is the question
# every consumer of a packed .npz asks. Three consumers ask a different question and never
# see an integer at all: they walk a directory tree whose leaves are named BTC.lz4 and
# ETH.lz4, so what they need is the SET OF SYMBOLS a store carries, in no code order,
# because that store has no codes. Handing them a code map would make them invert it, and
# an inverted map with no codes in it is an empty set.
#
# So the two forms are two questions and not one value spelled twice. Nothing is repeated
# between them: coin_symbols() DERIVES the symbol list from the code map wherever a code
# map exists, so quickwin and panel have exactly one home each, and this map holds only
# the stores that have no codes to derive from.
#
# Read first-hand on 2026-07-31 by listing the tree: every day and hour under
# 02_data/l2_cache holds BTC.lz4 and ETH.lz4 and nothing else. The panel cache directory
# beside it holds no .lz4 at all today, which is why it is not declared here -- an empty
# listing is not evidence of an empty coverage, and a set declared from one would be a
# guess wearing the shape of a measurement.
COIN_SYMBOLS_BY_ARTIFACT = {
    "l2_cache": ("BTC", "ETH"),
}


def coin_symbols(artifact):
    """The coin symbols one store carries, in code order wherever codes exist.

    Derived from COIN_CODES_BY_ARTIFACT where that map is non-empty, so a symbol list and
    a code map can never disagree about the same file. Falls through to
    COIN_SYMBOLS_BY_ARTIFACT only for a store that carries no codes.
    """
    labels = COIN_CODES_BY_ARTIFACT.get(artifact)
    if labels:
        return tuple(labels[c] for c in sorted(labels))
    if artifact in COIN_SYMBOLS_BY_ARTIFACT:
        return tuple(COIN_SYMBOLS_BY_ARTIFACT[artifact])
    raise ValueError(
        f"no coin coverage declared for {artifact!r}. A store with integer codes is "
        f"declared in COIN_CODES_BY_ARTIFACT and its symbols are derived from there; a "
        f"store whose leaves are named by symbol is declared in "
        f"COIN_SYMBOLS_BY_ARTIFACT. Declared today: "
        f"{sorted(set(COIN_CODES_BY_ARTIFACT) | set(COIN_SYMBOLS_BY_ARTIFACT))}")


# =====================================================================
# 8. THE EARLY-AND-LATE SPLIT: A FUNCTION, BECAUSE A TUPLE CANNOT EXPRESS IT
# =====================================================================

def split_early_late(days_present):
    """Split the days ACTUALLY PRESENT into an early and a late half.

    Why this cannot be a constant. Six files DECLARED EARLY_DAYS = (4,5,6,7,8) and
    LATE_DAYS = (9,10,11,12,13) on the day this function was written -- as_quoter.py,
    gm_quoter.py, i3_nonrecoverability_oos.py, maker_econ.py,
    t1_toxicity_skew_backtest.py and t3_capacity.py, read back out of the commit that
    introduced this module. Those are days of the month, and they are right only
    for a window that begins on the 4th. panel_markouts.npz was loaded to check: its
    day column runs 4 to 15, and 1,016,651 rows -- 3.905% of the panel -- sit on days
    14 and 15, every one of them in period 202510, whose window begins 2025-10-06. A
    day-of-month split at 8/9 gives that window a three-day early half against a
    seven-day late half, and a split that also stops at 13 discards two of its ten
    days outright. No tuple can express the rule; only a function of the days present.

    Where those six stand today, checked 2026-07-31. None holds the literal pair any
    more. Four reach this function through a hook that is None unless a caller injects a
    half, and the hook is spelled with the _OVERRIDE suffix in every one of them:
    gm_quoter.py, maker_econ.py, t1_toxicity_skew_backtest.py and t3_capacity.py.
    i3_nonrecoverability_oos.py calls this function at import and keeps the two names
    for the tuples it returns. as_quoter.py takes the split as a call parameter and has
    no module-level name for it at all.

    First ceil(n/2) days early, the remainder late. Returns (early, late) as integer
    tuples. late is empty when fewer than two days are present, which the caller has
    to treat as a degenerate cell and not as a result.
    """
    d = sorted(int(x) for x in set(days_present))
    if len(d) < 2:
        return tuple(d), ()
    cut = (len(d) + 1) // 2
    return tuple(d[:cut]), tuple(d[cut:])


def day_split_agrees(early, late):
    """True when a consumer's own two day tuples are the split the rule returns for them.

    Why a consumer holding tuples can be checked at all. The rule above is a function of
    the days present, so there is no tuple in this module to compare a literal against,
    and a check written the obvious way would have nothing to read. What there is instead
    is a fixed point: run the rule over the UNION of the two tuples a consumer declares
    and it either hands back those same two tuples or it does not. A consumer that passes
    is one whose cut can now move only by moving the rule, which is the property the rule
    exists to give; a consumer that fails is holding a split its own window does not
    support.

    checks/chk_settings_home.py RULE 5 already applies exactly this test to the notebook's
    two tuples, with the three lines written out inside the check. The test lives here so
    that the rule and the way of checking it sit in one place, and so the same predicate
    reaches the scripts that hold literal tuples as well as the notebook.
    """
    e = tuple(int(x) for x in early)
    lt = tuple(int(x) for x in late)
    return split_early_late(e + lt) == (e, lt)


# =====================================================================
# 9. THE FIELD-NAMING CONVENTION, DECLARED ONCE
# =====================================================================

# The repository holds two OPPOSITE conventions for the same thing. t3_capacity.py
# says the headline carries the suffix _10s and the unsuffixed key is the 60 s
# companion; panel_analyze.py says the unsuffixed key is the headline and the
# companion carries _60s. Both write a key literally named cost_bps, and it means a
# different window in each file, so a reader comparing the two artifacts reads one
# name as two quantities.
#
# The convention: EVERY window-bearing field names its window explicitly, and no key
# is left unsuffixed. An unsuffixed key cannot say which convention it belongs to,
# which is exactly the ambiguity above.
FIELD_SUFFIX_STYLE = "explicit"


def field_name(base, h=HEADLINE_HORIZON_S, lens=None):
    """Build a window-bearing field name. Never type one.

    field_name("cost_bps") -> "cost_bps_10s"
    field_name("cost_bps", COMPANION_HORIZON_S) -> "cost_bps_60s"
    field_name("markout_mean_bps", lens="mid") -> "markout_mean_bps_10s_mid"

    The lens is appended when a file writes both lenses, because a mid-lens value
    under a print-lens key is the same defect as a 60 s value under a 10 s key. It
    already happened: ks2_persistence_10day.py builds its book-mid descriptive key
    from headline_print_col(), so the mid artifact carries the print spelling.
    """
    if h not in LADDER_S:
        raise ValueError(f"h={h}s is not a window any artifact carries: {LADDER_S}")
    if lens is not None and lens not in LENSES:
        raise ValueError(f"unknown lens {lens!r}; declared lenses are {LENSES}")
    name = f"{base}_{int(h)}s"
    return f"{name}_{lens}" if lens else name


# =====================================================================
# 10. MIGRATION STATE
# =====================================================================

# "in_force": every consumer already uses this value, so adopting the declaration
# moves no number. "target": consumers disagree, so the switch WILL move a published
# number and is owed its own recompute with a leaf-by-leaf comparison. A guard reads
# this map, so a target cannot be quietly re-labelled as settled.
SETTING_STATE = {
    "HEADLINE_HORIZON_S": "in_force",
    "LADDER_S": "in_force",
    "COMPANION_HORIZON_S": "in_force",
    "HEADLINE_LENS": "in_force",
    "RELIABILITY_SEED": "in_force",
    "FDR_ALPHA": "in_force",
    "PERSISTENCE_FLOOR_FILLS": "in_force",
    "DAY_FLOOR_FILLS": "in_force",
    "WHALE_DROP_K": "in_force",
    "COIN_CODES_BY_ARTIFACT": "in_force",
    # The three below stayed "target" through the migration of 2026-07-31, and the reason
    # is the distinction the word exists for. Every consumer of the three now READS its
    # value from this file, so no second home is left to drift; what has not happened is
    # that any of them adopted the declared value. A declaration a consumer reads and
    # overrides is a home; a declaration a consumer obeys is in force. These are the first.
    #
    # TWO OF THE EIGHT ARE IN AN IN-BETWEEN STATE THIS MAP HAS NO WORD FOR, and the word
    # they keep is the conservative one. On 2026-07-31 every consumer of N_BOOT and of
    # RANK_FLOOR_FILLS was moved onto the declared value, so the CODE now obeys both. The
    # published artifacts do not: they were drawn at 300 to 1000 resamples and at a
    # 10-fill headline, and the six bootstrap nodes and four floor nodes are owed their
    # run. "in_force" would tell a reader that adopting the declaration moves no number,
    # which is exactly the false half. So both stay "target" until the recompute lands and
    # its leaf-by-leaf comparison is accepted, and the word is what flips then.
    # RECOUNTED 2026-08-01. The word before this one said "eight seeds declared per
    # purpose", and eight is the count of a different population: it is what the
    # predicate "module-level integer literal bound to a name containing SEED, outside
    # this file" returned, carried across when the sentence was rewritten to point at
    # the per-purpose map instead. Read off the map itself, SEED_BY_PURPOSE holds 26
    # purposes carrying 7 distinct values, and MASTER_SEED is not one of them. The
    # state stays "target" for the reason measured beside the declaration above: ten
    # consumers open a generator on this scalar and eight reach no declaration here.
    "MASTER_SEED": "target",        # 26 purposes, 7 distinct values, none of them this
    "N_PERM": "target",             # six scripts still run 200 draws
    # FLIPPED 2026-07-31 after the recompute landed and its leaf comparison was accepted.
    # Census over the 81 tracked results files, predicate "the key stands in
    # _meta.settings_fingerprint": 23 artifacts record a bootstrap budget, 7 hold 2000, 2
    # declare that they draw none, 14 hold null, and NOT ONE holds a value below the
    # declaration. So adopting it moves no number, which is what this word means.
    "N_BOOT": "in_force",
    # STAYS "target", and the reason is measured rather than assumed. The same census over
    # the selection floor: 10 artifacts stand at 50, four still record 10
    # (follow_the_informed_oos, m11, m8_makerside, ws2_hard_classifier), two record 25, two
    # record 30, one records 1, and six more carry a grid. The earlier note here said
    # "artifacts at 10" flatly, which was true before the recompute of 2026-07-31 and is
    # now wrong in both directions.
    "RANK_FLOOR_FILLS": "target",
    "MIN_COMMON_WALLETS": "target",  # not declared anywhere yet
    "WHALE_DROP_CRITERIA": "target",  # one key name currently covers two criteria
    "FIELD_SUFFIX_STYLE": "target",  # two opposite conventions in force today
    "split_early_late": "target",   # six files use day-of-month tuples instead
    # The per-consumer maps are in force BY CONSTRUCTION, and the word means something
    # narrower for them than it does above. Each one was written from what the consumers
    # already hold, so adopting it moves no number and there is nothing to recompute.
    # What it does not mean is that the value is the one the work should run. That
    # sentence used to be illustrated by the bootstrap budgets, all of which sat under
    # N_BOOT; since 2026-07-31 they do not, so the illustration is now the wallet floors,
    # whose sweeps hold a loose rung the reliability evidence rules out as a headline and
    # keep it deliberately, as the reported curve. A record agreeing with the tree is a
    # different statement from a choice agreeing with the evidence, and this map answers
    # only the first.
    "SEED_BY_PURPOSE": "in_force",
    "PERM_DRAWS_BY_PURPOSE": "in_force",
    "BOOT_DRAWS_BY_PURPOSE": "in_force",
    "WALLET_FILL_FLOOR_BY_PURPOSE": "in_force",
    "COIN_SYMBOLS_BY_ARTIFACT": "in_force",
}


# =====================================================================
# 11. WHAT JUSTIFIES EACH SETTING
#
# SETTING_STATE above answers "does the tree agree with this value". This map answers
# the different and older question a reader asks first: WHY THIS VALUE. "Why ten
# seconds and not sixty" gets asked at every discussion and will be asked by a
# reviewer, so it needs a written answer rather than a spoken one.
#
# The kinds are separate because they are defended in three different ways, and mixing
# them is how a preference comes to be quoted as a finding. A derived value is defended
# by re-running its producer. An arithmetic value is defended by the inequality, which
# is why the one such value in this file is an expression and not a literal. A
# conventional value is defended by naming its source, and by nothing else.
#
# Three kinds beyond those three earn their place by being true, and all three are worse
# news than the first three. "arbitrary" says any value serves and what is defended is
# that there is exactly ONE of them; a reviewer who contests the value has misunderstood
# it. "as_run" says the value is defended by neither an artifact, an inequality nor a
# source, but by the fact that a NAMED CONSUMER ran it and its published results file
# records the difference as a stated override -- so what an as_run declaration asserts is
# a fact about the tree, and a reader who wants to know whether the value is right has to
# look at the setting it deviates from and not at the record of the deviation.
# "none" says no basis is on record. Three declarations carry "none" --
# RELIABILITY_SEED_SPREAD_SD, DAY_FLOOR_FILLS and MIN_COMMON_WALLETS -- and they are the
# useful output of this map: an empty spot named out loud is worth more than a
# plausible story over it.
#
# READBACK is the field to read second, and it is where the map stops flattering the
# code. A producer that takes a setting as an INPUT and writes it back into its own
# results file has not derived anything, and the key it writes cannot be cited as a
# source without arguing that the value is right because it is what it is. Nine of the
# thirteen derived entries are like that, so their named key is the EVIDENCE the
# producer owns rather than the value it echoes, and the claim they support is "the
# choice clears a stated criterion" and not "the choice was computed". Four entries have
# readback False and they are the only settings a reader can check without consulting
# this module at all: LADDER_S, LENSES and COIN_CODES_BY_ARTIFACT are read off the data
# files themselves, and PERM_FAMILY_SIZE is counted by its producer from the cells it
# tested.
# =====================================================================

BASIS_KINDS = ("derived", "arithmetic", "conventional", "arbitrary", "as_run", "none",
               "not_a_setting")

SETTING_BASIS = {
    # ---- the scoring window -------------------------------------------------
    "HEADLINE_HORIZON_S": {
        "kind": "derived", "readback": True,
        "artifact": "ws1_horizon_results.json",
        "key": "final_decision.info_frac, .info_complete_frac_threshold, "
               ".most_persistent_info_complete, .old_choice_companion_dominated",
        "basis": "the evidence clears two stated criteria at 10 s: information "
                 "complete against a 0.95 threshold, and persistence still high where "
                 "the 60 s companion has half of it. The choice on top of that evidence "
                 "is a human judgement -- the grid's information-complete argmax is 5 s, "
                 "which no producer writes a column for. The key that holds the value, "
                 "final_decision.recommended_score_horizon_s, is read back from here and "
                 "is not evidence for it."},
    "LADDER_S": {
        "kind": "derived", "readback": False,
        "artifact": "quickwin_markouts.npz, panel_markouts.npz",
        "key": "column names",
        "basis": "the windows a column exists for. Loaded 30 July: both files carry "
                 "mo1, mo10 and mo60 and nothing else, so a horizon outside this tuple "
                 "cannot be scored without re-marking the tape. This is the reason the "
                 "5 s rung the selection evidence prefers cannot simply be adopted."},
    "COMPANION_HORIZON_S": {
        "kind": "derived", "readback": True,
        "artifact": "ws1_horizon_results.json",
        "key": "final_decision.old_choice_companion_dominated",
        "basis": "60 s is kept BECAUSE the same evidence dominates it for scoring: it "
                 "buys no information the headline lacks and costs half the persistence. "
                 "Reporting the dominated window beside the headline is what lets a "
                 "reader see that the headline was not chosen to flatter the result. The "
                 "key companion_window_still_reported_s is read back from here."},

    # ---- the lens -----------------------------------------------------------
    "LENSES": {
        "kind": "derived", "readback": False,
        "artifact": "quickwin_markouts.npz, quickwin_markouts_mid.npz",
        "key": "column names mo{h} against mo{h}_mid",
        "basis": "the two reference prices the tape actually carries. An enumeration of "
                 "what exists, not a choice between them."},
    "HEADLINE_LENS": {
        "kind": "derived", "readback": True,
        "artifact": "ks2_persistence_10day_results.json, ks2_persistence_mid_results.json",
        "key": "persistence_pooled[*].spearman_disattenuated",
        "basis": "the mid answers the adverse-selection question without the maker's own "
                 "earned spread inside the number. The evidence is that it does not "
                 "matter which is chosen: the two lenses agree to within a hundredth at "
                 "the headline cell and swap order at the 100-fill floor, so the result "
                 "does not rest on the lens. Which lens each file computed is read back "
                 "from here."},

    # ---- randomness ---------------------------------------------------------
    "MASTER_SEED": {
        "kind": "arbitrary", "readback": False, "artifact": None, "key": None,
        "basis": "no integer is more correct than another. What is defended is that "
                 "there is exactly one, so that a p-value differing between two scripts "
                 "differs because the statistic differs. Contesting the value would be a "
                 "misreading; contesting the count of them would not."},
    "RELIABILITY_SEED": {
        "kind": "arbitrary", "readback": False, "artifact": None, "key": None,
        "basis": "arbitrary in the same way, and separate on purpose because it seeds a "
                 "different estimator. Three files bind the name -- "
                 "ks2_persistence_10day.py, panel_persistence.py, panel_common_idio.py "
                 "-- so their reliability tables are comparable cell for cell."},
    "RELIABILITY_SEED_SPREAD_SD": {
        "kind": "none", "readback": False, "artifact": None, "key": None,
        "basis": "NOTHING IN THIS REPOSITORY PRODUCES THIS NUMBER. It was measured by "
                 "sweeping fifty seeds through the reliability estimator, but no script "
                 "in the tree performs that sweep and no artifact records it, so a "
                 "reader who clones the repository cannot reproduce or check it. The "
                 "cell it is a spread around is real and checkable "
                 "(ks2_persistence_mid_results.json persistence_pooled[0]"
                 ".spearman_disattenuated); the spread is not. Either the sweep becomes "
                 "a script with an artifact or the number leaves the report."},

    "SEED_BY_PURPOSE": {
        "kind": "as_run", "readback": False, "artifact": None,
        "key": "the seed literal at each named consumer, and the master_seed override "
               "each of their results files stamps",
        "basis": "what each consumer actually draws, read by syntax tree on 2026-07-31 "
                 "over the sites the settings gate flags. Twenty-four sites carry seven "
                 "distinct values, so the tree does not have one seed per purpose and "
                 "this map does not assert that it does. Each value is defended only by "
                 "being the one its published artifact was drawn under; MASTER_SEED "
                 "remains the target and this is the record of the distance to it."},

    # ---- resampling budgets -------------------------------------------------
    "FDR_ALPHA": {
        "kind": "conventional", "readback": False, "artifact": None, "key": None,
        "basis": "0.05 is the level the discipline reports at, and the procedure it "
                 "belongs to is Benjamini-Hochberg step-up, named in the `method` field "
                 "of every artifact that applies it. Defended by the source, not by any "
                 "computation of ours."},
    "PERM_FAMILY_SIZE": {
        "kind": "derived", "readback": False,
        "artifact": "panel_persistence_results.json",
        "key": "cross_month_fdr.family_size (48), beside n_distinct_comparisons (24)",
        "basis": "counted by panel_persistence.py from the cells it tested, not taken "
                 "from here. One family and not the work: the same key is 448 in the "
                 "panel_extended _all arms, 20, 8 and 4 elsewhere. A script with a "
                 "larger family passes its own size to min_perm_draws."},
    "PERM_FLOOR_MARGIN": {
        "kind": "conventional", "readback": False, "artifact": None, "key": None,
        "basis": "a stated judgement with no external source: the p-value floor is "
                 "required to sit at half the corrected threshold rather than just under "
                 "it, so that a floored p is not a boundary case. This is the whole "
                 "distance between the 1000 draws the requirement asks for and the 2000 "
                 "the work runs, which is why it is a named number and not a habit."},
    "N_PERM": {
        "kind": "arithmetic", "readback": False,
        "artifact": None, "key": "computed by min_perm_draws()",
        "basis": "the p-value floor is 1/(N+1) and has to clear alpha/(margin * m), so "
                 "N follows from FDR_ALPHA, PERM_FAMILY_SIZE and PERM_FLOOR_MARGIN and "
                 "is not a matter of taste. Not a literal: change the level or the "
                 "family and the budget moves with them."},
    "N_BOOT": {
        "kind": "arithmetic", "readback": False, "artifact": None, "key": None,
        "basis": "a 95 percent percentile interval puts N * 0.025 draws in each tail, "
                 "the stated requirement is fifty per tail, and 50 / 0.025 = 2000. Same "
                 "shape as N_PERM and still typed rather than computed; writing it as an "
                 "expression is the obvious next move and has not been made."},

    "PERM_DRAWS_BY_PURPOSE": {
        "kind": "as_run", "readback": False, "artifact": None,
        "key": "n_perm_varratio and n_placebo in the consumers' own results files",
        "basis": "the budgets four named draws actually take, and two of the four are a "
                 "DIFFERENT QUANTITY from N_PERM rather than a shortfall against it: the "
                 "two ks2 nodes average their draws into the denominator of a variance "
                 "ratio that no threshold is applied to, read in heterogeneity_ratio on "
                 "2026-07-31. The other two are budgets that do feed a p, and their "
                 "floors are stated beside them so the position is legible rather than "
                 "endorsed."},
    "BOOT_DRAWS_BY_PURPOSE": {
        "kind": "as_run", "readback": False, "artifact": None,
        "key": "the n_boot field of each consumer's fingerprint block",
        "basis": "the resamples six named consumers draw. Since 2026-07-31 every entry "
                 "is N_BOOT itself, so what this map records is that the tree holds no "
                 "bootstrap exception rather than which exceptions it holds. The entries "
                 "stood at 1000, 1000, 500, 500, 300 and 800 -- 25, 25, 12.5, 12.5, 7.5 "
                 "and 20 draws per tail against the fifty declared -- and each was "
                 "declared debt with a named size rather than a disagreement about what "
                 "a bootstrap needs, which is why the debt was paid by raising the map. "
                 "Two of the six had no home a census could find: mm_bakeoff's 300 was "
                 "the default argument of an environment read, and m11_concentration's "
                 "800 is spelled BOOTSTRAP_DRAWS, a name in no alias list of the "
                 "settings gate."},

    # ---- wallet eligibility -------------------------------------------------
    "RANK_FLOOR_FILLS": {
        "kind": "derived", "readback": True,
        "artifact": "ks2_persistence_10day_results.json, ws1_horizon_results.json",
        "key": "reliability[*].reliability at K 50 and 100; pooled[*].rel_early and "
               ".rel_late at K_primary 10",
        "basis": "chosen on measured split-half reliability. At a 10-fill floor the "
                 "disattenuation multiplier is 2.7891, so 64 percent of the corrected "
                 "number is the correction; at 50 to 100 fills the four cells give "
                 "1.1514, 1.2285, 1.4267 and 1.5626. 50 is the lowest floor at which the "
                 "score is mostly signal. Both producers read the floor from here, so "
                 "the artifacts show what the floor BUYS rather than where it came from. "
                 "Adopted by all four headline consumers on 2026-07-31, which moves the "
                 "POPULATION and not only a caption: at ten early fills the December "
                 "window carries 9,654 eligible takers and a 966-wallet toxic decile, at "
                 "fifty it carries 2,069 and 207."},
    "RANK_FLOOR_SENSITIVITY": {
        "kind": "derived", "readback": True,
        "artifact": "ws1_horizon_results.json, ks2_persistence_10day_results.json",
        "key": "K_primary and robustness_K keys (10, 25, 50); reliability[*].K (50, 100)",
        "basis": "the union of the floors the artifacts actually carry, which is exactly "
                 "these four. A sensitivity ladder that names a floor no artifact reports "
                 "would be a promise rather than a report."},
    "PERSISTENCE_FLOOR_FILLS": {
        "kind": "derived", "readback": True,
        "artifact": "ks2_persistence_10day_results.json",
        "key": "reliability[*].K and persistence_pooled[*].K",
        "basis": "a wallet needs the fill count in BOTH halves, so the same total buys "
                 "half the precision per half; this is a different quantity from the rank "
                 "floor and not a stricter setting of it. 50 is the reported cell and 100 "
                 "is the check that the cell is not a small-sample artifact, and the file "
                 "carries both."},
    "DAY_FLOOR_FILLS": {
        "kind": "none", "readback": False, "artifact": None, "key": None,
        "basis": "the DIRECTION is argued and the VALUE is not. A day is a fifth of a "
                 "half, which says the per-day floor belongs below the persistence floor "
                 "and says nothing about where; a fifth of 50 would be 10, not 25. No "
                 "artifact and no source stands behind 25."},
    "MIN_COMMON_WALLETS": {
        "kind": "none", "readback": False, "artifact": None, "key": None,
        "basis": "no basis on record. 30 is the familiar small-sample rule of thumb, but "
                 "no source is cited for it here and no measurement in this work chose "
                 "it. It is also the one declaration no consumer reads yet, so nothing "
                 "currently depends on it being right."},

    "WALLET_FILL_FLOOR_BY_PURPOSE": {
        "kind": "as_run", "readback": False, "artifact": None,
        "key": "the K rungs each consumer's results file reports",
        "basis": "the ladders six consumers sweep and the per-half and headline floors "
                 "five more apply, read by syntax tree on 2026-07-31 and recounted after "
                 "the migration of that day. The four headline entries stopped being "
                 "as_run later the same day and now hold RANK_FLOOR_FILLS itself; the "
                 "sweeps are still as_run, because the loose rung of a reported curve is "
                 "a finding and not a debt. The declaration is a map because "
                 "RANK_FLOOR_FILLS is one number and a file reporting a whole sweep has "
                 "the curve as its finding, so a scalar cannot be what it reads without "
                 "deleting the finding. The roles inside an entry are separate "
                 "quantities and are never substituted for one another. Four of the "
                 "eleven entries were added the day the settings gate learnt the "
                 "spellings K, KS, K_MIN and MIN_FILLS; before that no census here could "
                 "see them, so their absence from this map was not a judgement."},

    # ---- whale-drop robustness ----------------------------------------------
    "WHALE_DROP_K": {
        "kind": "derived", "readback": True,
        "artifact": "t3_results.json",
        "key": "pooled.avoidable_10s.whale_drop_ladder_top10pct_10s.drop_top10_by_gross_cost",
        "basis": "the headline rung of a ladder whose SHAPE is the finding, not a rung "
                 "chosen because it answers best. The question 'is this ten wallets' has "
                 "no yes or no, so the reported answer is the whole ladder and 10 is "
                 "where prose points. The producer reads the rungs from here."},
    "WHALE_DROP_LADDER": {
        "kind": "derived", "readback": True,
        "artifact": "t3_results.json",
        "key": "whale_drop_ladder_* key suffixes drop_top10, drop_top50, drop_top100",
        "basis": "the three rungs the artifact reports, spanning from a handful of "
                 "wallets to a hundred, which is what makes the fall in the avoidable "
                 "share readable as a curve rather than a single before-and-after."},
    "WHALE_DROP_CRITERIA": {
        "kind": "derived", "readback": True,
        "artifact": "t3_results.json, m11_results.json",
        "key": "drop_top{k}_by_{criterion} key names",
        "basis": "the four criteria the artifacts carry. Dropping the largest by "
                 "notional answers 'is this a volume artifact'; by cost it answers 'is "
                 "this ten wallets'. Different questions with different answers, which is "
                 "why the accessor makes the criterion required and no key may say 'top "
                 "10' without saying top 10 by what."},

    # ---- coins --------------------------------------------------------------
    "COIN_CODES_BY_ARTIFACT": {
        "kind": "derived", "readback": False,
        "artifact": "quickwin_markouts.npz, panel_markouts.npz",
        "key": "the distinct values of the coin column",
        "basis": "a property of each FILE and not of the project. Loaded 30 July: "
                 "quickwin carries codes {0, 1} and panel carries {0, 1, 2}, so one "
                 "project-wide map would be wrong for one of them, and wrong silently, "
                 "because a code valid in both relabels BTC as ETH without raising."},

    "COIN_SYMBOLS_BY_ARTIFACT": {
        "kind": "derived", "readback": False,
        "artifact": "02_data/l2_cache",
        "key": "the {symbol}.lz4 file names present under each day and hour",
        "basis": "listed on 2026-07-31: every day and hour of that store holds BTC.lz4 "
                 "and ETH.lz4 and nothing else. This map holds ONLY stores that carry no "
                 "integer codes, because coin_symbols() derives the symbol list from "
                 "COIN_CODES_BY_ARTIFACT wherever a code map exists, so no coverage is "
                 "written down twice. The panel cache directory is absent from the map "
                 "because it holds no .lz4 today, and an empty listing is not evidence "
                 "of an empty coverage."},

    # ---- naming -------------------------------------------------------------
    "FIELD_SUFFIX_STYLE": {
        "kind": "conventional", "readback": False, "artifact": None, "key": None,
        "basis": "a convention of this project with no external source, adopted against "
                 "a measured defect rather than a preference: two files both wrote a key "
                 "named cost_bps and it meant a different window in each. Naming the "
                 "window in every window-bearing field is the smallest rule that makes "
                 "that collision impossible."},

    # ---- bookkeeping, not settings -----------------------------------------
    "BASIS_KINDS": {"kind": "not_a_setting", "readback": False, "artifact": None,
                    "key": None, "basis": "the vocabulary of this map."},
    "SETTING_BASIS": {"kind": "not_a_setting", "readback": False, "artifact": None,
                      "key": None, "basis": "this map."},
    "SETTING_STATE": {"kind": "not_a_setting", "readback": False, "artifact": None,
                      "key": None,
                      "basis": "bookkeeping about settings, not a setting. It records "
                               "whether consumers agree with a declaration, which is a "
                               "fact about the tree and moves as the tree is migrated."},
    "SETTING_SITES": {"kind": "not_a_setting", "readback": False, "artifact": None,
                      "key": None,
                      "basis": "the resolver, not a setting. It holds no value and no "
                               "verdict: it says which declaration each flagged site is "
                               "supposed to read, so that whether the site agrees is "
                               "computed on demand and cannot go stale in place."},
}


def basis_gaps():
    """Public constants with no entry in SETTING_BASIS, and entries naming no constant.

    Returned rather than printed so a check can assert it is empty. The module refuses
    to import while the first list is non-empty, which is what stops a new declaration
    from arriving with its reasoning left in someone's head.
    """
    public = {n for n, v in globals().items()
              if not n.startswith("_") and n.isupper() and not callable(v)}
    return {"unclassified": sorted(public - set(SETTING_BASIS)),
            "orphaned": sorted(set(SETTING_BASIS) - public)}


def _check_basis():
    gaps = basis_gaps()
    if gaps["unclassified"]:
        raise RuntimeError(
            f"settings.py declares {gaps['unclassified']} with no entry in "
            f"SETTING_BASIS. Say what kind of thing justifies the value -- one of "
            f"{BASIS_KINDS} -- and name the artifact and key if it is derived. Use "
            f"'none' if there is no basis; an empty spot named out loud is the point "
            f"of the map.")
    if gaps["orphaned"]:
        raise RuntimeError(
            f"SETTING_BASIS names {gaps['orphaned']}, which this module does not "
            f"declare. A basis for a setting that no longer exists outlives the "
            f"setting and misleads the next reader.")
    for name, entry in SETTING_BASIS.items():
        if entry["kind"] not in BASIS_KINDS:
            raise RuntimeError(f"SETTING_BASIS[{name!r}] has kind {entry['kind']!r}, "
                               f"which is not one of {BASIS_KINDS}")
        if entry["kind"] == "derived" and not entry.get("key"):
            raise RuntimeError(f"SETTING_BASIS[{name!r}] claims to be derived but names "
                               f"no key. A derived value is defended by re-running its "
                               f"producer, which needs the artifact and the key.")


# =====================================================================
# 12. EVERY SITE THAT STILL HOLDS A LITERAL, AND WHAT THIS MODULE SAYS ABOUT IT
#
# Why this map is here rather than in the gate that counts the sites. Twice now the
# question "is the declared value the same as the local one" has been answered by hand,
# and twice the answer came out differently -- not because the tree differed but because
# the two passes RESOLVED a site to a declaration differently. One pass sent every
# horizon-family name to HEADLINE_HORIZON_S and read a disagreement; another sent
# HORIZONS_S to LADDER_S and read agreement. Both are defensible readings of a name, and
# that is the defect: a census whose resolver is a judgement produces a number nobody can
# reproduce, and the three counts it reports move without the tree moving.
#
# So the resolver is written down. For each site the settings gate flags, this map names
# the ONE declaration that site is supposed to read. It holds no values -- the values stay
# in the declarations above and each has exactly one home -- and it holds no verdicts:
# whether a site agrees is computed, not recorded, so it cannot go stale in place.
#
# The shape says what kind of home a site has, because four kinds exist and only two of
# them have a value to compare against:
#
#   ("constant", NAME)              read NAME directly.
#   ("map", NAME, key[, role])      read one entry of a per-consumer map.
#   ("call", FUNC, argument)        the declaration is derived, so ask for it.
#   ("rule", FUNC)                  there is no value to compare: the declaration is a
#                                   RULE, and agreement means the rule reproduces what
#                                   the site holds. day_split_agrees is that test.
#   ("local", reason)               the site is not a setting at all. Recording this is
#                                   the point of the entry: eight of the sites below are
#                                   names bound to None, which declare no value and
#                                   cannot disagree with anything, and counting them as
#                                   debt overstates the debt by eight.
#
# Adding a site here does not make it stop being counted by the gate; the gate keeps its
# own allow list and its own frozen figure, and lowering that figure stays a decision
# somebody makes. What this map removes is the step where somebody has to decide, again,
# what each site was supposed to read.
SETTING_SITES = {
    # ---- seeds --------------------------------------------------------------
    "as_quoter.py::SEED": ("map", "SEED_BY_PURPOSE", "as_quoter"),
    "build_quickwin_markouts.py::RNG_SEED":
        ("map", "SEED_BY_PURPOSE", "build_quickwin_markouts"),
    "confound_asymmetry.py::SEED": ("map", "SEED_BY_PURPOSE", "confound_asymmetry"),
    "follow_the_informed_oos.py::RNG_SEED":
        ("map", "SEED_BY_PURPOSE", "follow_the_informed_oos"),
    "gm_quoter.py::SEED": ("map", "SEED_BY_PURPOSE", "gm_quoter"),
    "i3_nonrecoverability_oos.py::RNG_SEED":
        ("map", "SEED_BY_PURPOSE", "i3_nonrecoverability_oos"),
    "i5_exclusion.py::SEED": ("map", "SEED_BY_PURPOSE", "i5_exclusion"),
    "m4_realizedpnl.py::RNG_SEED": ("map", "SEED_BY_PURPOSE", "m4_realizedpnl"),
    "m8_makerside.py::RNG_SEED": ("map", "SEED_BY_PURPOSE", "m8_makerside"),
    "m9_crossasset.py::SEED": ("map", "SEED_BY_PURPOSE", "m9_crossasset"),
    "maker_econ.py::SEED": ("map", "SEED_BY_PURPOSE", "maker_econ"),
    "maker_econ_b2.py::SEED": ("map", "SEED_BY_PURPOSE", "maker_econ_b2"),
    "mm_bakeoff.py::SEED": ("map", "SEED_BY_PURPOSE", "mm_bakeoff"),
    "panel_persistence.py::RNG_CORR_SEED":
        ("map", "SEED_BY_PURPOSE", "panel_persistence_correlation_null"),
    "probes/c2_bookstate_control.py::SEED":
        ("map", "SEED_BY_PURPOSE", "c2_bookstate_control"),
    "probes/c_matched_precision.py::SEED":
        ("map", "SEED_BY_PURPOSE", "c_matched_precision"),
    "probes/kss_decomp_c.py::SEED": ("map", "SEED_BY_PURPOSE", "kss_decomp_c"),
    "probes/kss_decomp_c_bookmid.py::SEED":
        ("map", "SEED_BY_PURPOSE", "kss_decomp_c_bookmid"),
    "probes/probe_D_funding.py::SEED": ("map", "SEED_BY_PURPOSE", "probe_D_funding"),
    "probes/probe_E_leadlag.py::SEED": ("map", "SEED_BY_PURPOSE", "probe_E_leadlag"),
    "probes/probe_F_hlp_liq.py::SEED": ("map", "SEED_BY_PURPOSE", "probe_F_hlp_liq"),
    "t1_toxicity_skew_backtest.py::RNG_SEED":
        ("map", "SEED_BY_PURPOSE", "t1_toxicity_skew_backtest"),
    "t3_capacity.py::BOOTSTRAP_SEED": ("map", "SEED_BY_PURPOSE", "t3_capacity"),
    "forward_toxicity.py::RNG_SEED": ("map", "SEED_BY_PURPOSE", "forward_toxicity"),
    # decay_curve.py hands its seed straight to the generator constructor, so there is no
    # module-level name to key on. The site is recorded under the name of the call it
    # sits in, because a site with no key here is a site the resolver cannot answer for.
    "probes/decay_curve.py::default_rng": ("map", "SEED_BY_PURPOSE", "decay_curve"),

    # ---- resampling budgets -------------------------------------------------
    "ks2_markout_multiday.py::N_PERM":
        ("map", "PERM_DRAWS_BY_PURPOSE", "ks2_markout_per_day_variance_ratio"),
    "ks2_persistence_10day.py::N_PERM":
        ("map", "PERM_DRAWS_BY_PURPOSE", "ks2_persistence_per_day_variance_ratio"),
    "probes/probe_E_leadlag.py::N_PLACEBO":
        ("map", "PERM_DRAWS_BY_PURPOSE", "leadlag_randomised_lag_placebo"),
    "t1_toxicity_skew_backtest.py::N_SIZE_PLACEBO":
        ("map", "PERM_DRAWS_BY_PURPOSE", "t1_size_matched_placebo"),
    "maker_econ.py::N_BOOT": ("map", "BOOT_DRAWS_BY_PURPOSE", "maker_econ"),
    "ws1_horizon_persistence.py::N_BOOT":
        ("map", "BOOT_DRAWS_BY_PURPOSE", "ws1_horizon_persistence"),
    "ws3_taker_pnl.py::N_BOOT": ("map", "BOOT_DRAWS_BY_PURPOSE", "ws3_taker_pnl"),
    "t3_capacity.py::BOOTSTRAP_N": ("map", "BOOT_DRAWS_BY_PURPOSE", "t3_capacity"),
    # This site used to be the DEFAULT of an environment read. The environment read was
    # removed on 2026-07-31 with the adoption of the declared budget, so the site is now
    # an ordinary one; what the run drew is still stamped in the artifact.
    "mm_bakeoff.py::N_BOOT": ("map", "BOOT_DRAWS_BY_PURPOSE", "mm_bakeoff"),
    # Added 2026-07-31. The sixth bootstrap consumer, and the one no census had ever
    # resolved: it spells the budget BOOTSTRAP_DRAWS, which is in no alias list of
    # checks/chk_settings_home.py, so the gate never reported it and the map never
    # carried it. Recording it here is what makes the site answerable.
    "m11_concentration.py::BOOTSTRAP_DRAWS":
        ("map", "BOOT_DRAWS_BY_PURPOSE", "m11_concentration"),

    # ---- wallet fill floors -------------------------------------------------
    "i2_walletfe.py::K_VALUES":
        ("map", "WALLET_FILL_FLOOR_BY_PURPOSE", "i2_walletfe", "sweep"),
    "m9_crossasset.py::K_VALUES":
        ("map", "WALLET_FILL_FLOOR_BY_PURPOSE", "m9_crossasset", "sweep"),
    "maker_econ.py::K_LIST":
        ("map", "WALLET_FILL_FLOOR_BY_PURPOSE", "maker_econ", "sweep"),
    "maker_econ.py::K_HEADLINE":
        ("map", "WALLET_FILL_FLOOR_BY_PURPOSE", "maker_econ", "headline"),
    "maker_econ_b2.py::K_LIST":
        ("map", "WALLET_FILL_FLOOR_BY_PURPOSE", "maker_econ_b2", "sweep"),
    "maker_econ_b2.py::K_HEADLINE":
        ("map", "WALLET_FILL_FLOOR_BY_PURPOSE", "maker_econ_b2", "headline"),
    "mm_bakeoff.py::K_LIST":
        ("map", "WALLET_FILL_FLOOR_BY_PURPOSE", "mm_bakeoff", "sweep"),
    "mm_bakeoff.py::K_HEADLINE":
        ("map", "WALLET_FILL_FLOOR_BY_PURPOSE", "mm_bakeoff", "headline"),
    "probes/eb_scoring.py::KMIN":
        ("map", "WALLET_FILL_FLOOR_BY_PURPOSE", "eb_scoring", "both_halves"),
    "temp_perm_decomp.py::K_HALF_MIN":
        ("map", "WALLET_FILL_FLOOR_BY_PURPOSE", "temp_perm_decomp", "each_split_half"),
    # The four spellings no alias list carried before 2026-07-31, so no census in this
    # repository had ever resolved them to anything.
    "m2_figure.py::MIN_FILLS":
        ("map", "WALLET_FILL_FLOOR_BY_PURPOSE", "m2_figure", "both_halves"),
    "probes/persistence_crosswindow.py::KS":
        ("map", "WALLET_FILL_FLOOR_BY_PURPOSE", "persistence_crosswindow", "sweep"),
    "ws2_hard_classifier.py::K":
        ("map", "WALLET_FILL_FLOOR_BY_PURPOSE", "ws2_hard_classifier", "both_halves"),
    "ws3_taker_pnl.py::K":
        ("map", "WALLET_FILL_FLOOR_BY_PURPOSE", "ws3_taker_pnl", "headline"),

    # ---- coins --------------------------------------------------------------
    # Two of these three read a directory whose leaves are named by symbol, so their
    # home is the symbol form; the third holds the panel's integer code map and its home
    # is the code form. One family, two questions, and the map says which is which.
    "checks/chk_book_orientation.py::COINS": ("call", "coin_symbols", "l2_cache"),
    "i4_l2_mid.py::DEFAULT_COINS": ("call", "coin_symbols", "l2_cache"),
    "checks/chk_rowcounts_determinism.py::COIN_LABEL":
        ("map", "COIN_CODES_BY_ARTIFACT", "panel"),

    # ---- the scoring window -------------------------------------------------
    "checks/chk_side_signconv.py::HORIZONS_S": ("constant", "LADDER_S"),

    # ---- the early and late halves ------------------------------------------
    # Two sites hold day-of-month tuples, and their home is the RULE: a window opening on
    # the 4th makes split_early_late return exactly those two tuples, so the site agrees
    # and adopting the rule moves no number in that file.
    "i3_nonrecoverability_oos.py::EARLY_DAYS": ("rule", "day_split_agrees"),
    "i3_nonrecoverability_oos.py::LATE_DAYS": ("rule", "day_split_agrees"),
    # The remaining eight are bound to None. A name bound to None declares no value, so
    # it is not a second home for anything: it is the hook panel_analyze.py writes into
    # to run these estimators month by month, and None means "split the days the input
    # actually carries". The gate counts them because None is a literal, which is a
    # property of the counting rule and not of the tree.
    #
    # ALL EIGHT NOW CARRY THE _OVERRIDE SUFFIX, and the keys here follow the names in
    # the files rather than the names the files used to have. gm_quoter.py was renamed
    # in commit ff3b8fe and the two keys below went on naming EARLY_DAYS and LATE_DAYS,
    # which that file has not held since; site_declaration would have resolved a site
    # that does not exist while the two that do exist resolved to nothing. The other six
    # were renamed on 2026-07-31 in maker_econ.py, t1_toxicity_skew_backtest.py and
    # t3_capacity.py. The suffix is what makes the name honest, and it is what
    # checks/chk_settings_home.py keys its hook exemption on: a suffixed name bound to
    # None is a stated absence of an override, an unsuffixed one claims to BE the
    # setting while holding no value.
    "gm_quoter.py::EARLY_DAYS_OVERRIDE":
        ("local", "override hook, None means derive by rule"),
    "gm_quoter.py::LATE_DAYS_OVERRIDE":
        ("local", "override hook, None means derive by rule"),
    "maker_econ.py::EARLY_DAYS_OVERRIDE":
        ("local", "override hook, None means derive by rule"),
    "maker_econ.py::LATE_DAYS_OVERRIDE":
        ("local", "override hook, None means derive by rule"),
    "t1_toxicity_skew_backtest.py::EARLY_DAYS_OVERRIDE":
        ("local", "override hook, None means derive by rule"),
    "t1_toxicity_skew_backtest.py::LATE_DAYS_OVERRIDE":
        ("local", "override hook, None means derive by rule"),
    "t3_capacity.py::EARLY_DAYS_OVERRIDE":
        ("local", "override hook written by panel_analyze.py per period"),
    "t3_capacity.py::LATE_DAYS_OVERRIDE":
        ("local", "override hook written by panel_analyze.py per period"),
}


def site_declaration(site):
    """What this module declares for one flagged site, resolved rather than looked up.

    Returns the kind of home, the path a reader can follow to it, and the value where
    there is one. A site whose home is a rule or which is not a setting returns a value
    of None together with the kind, so a caller cannot mistake "no value to compare"
    for "the declared value is None".
    """
    if site not in SETTING_SITES:
        raise ValueError(
            f"{site!r} is not a site this module resolves. The key is the tracked path, "
            f"two colons, and the name bound at module level, as in "
            f"'maker_econ.py::K_LIST'. Add the site with the declaration it should read, "
            f"or with ('local', reason) if it is a quantity of that script alone")
    entry = SETTING_SITES[site]
    how = entry[0]
    if how == "constant":
        return {"how": how, "path": entry[1], "value": globals()[entry[1]]}
    if how == "map":
        value = globals()[entry[1]]
        for key in entry[2:]:
            value = value[key]
        return {"how": how, "path": "".join([entry[1]] + [f"[{k!r}]"
                                                          for k in entry[2:]]),
                "value": value}
    if how == "call":
        return {"how": how, "path": f"{entry[1]}({entry[2]!r})",
                "value": globals()[entry[1]](entry[2])}
    return {"how": how, "path": entry[1], "value": None}


def site_agrees(site, local_value, partner_value=None):
    """Whether a site's literal is what this module declares. None when it cannot be.

    True or False where a value exists to compare. None where no comparison is defined,
    which is the honest answer for a hook bound to None and for a site whose home is a
    rule that needs both halves of a split -- pass the other half as partner_value and
    the rule is applied instead.

    The comparison is by CONTENT, so a tuple here and a list at the site are the same
    setting while a different order or a different member is not. That is the same
    convention checks/chk_settings_home.py uses for the notebook's mirrors.
    """
    entry = SETTING_SITES.get(site)
    if entry is None:
        raise ValueError(f"{site!r} is not a site this module resolves")
    if entry[0] == "rule":
        if partner_value is None:
            return None
        early, late = ((local_value, partner_value) if "EARLY" in site
                       else (partner_value, local_value))
        return day_split_agrees(early, late)
    if entry[0] == "local":
        return None

    def content(value):
        if isinstance(value, (list, tuple)):
            return ("seq",) + tuple(content(v) for v in value)
        if isinstance(value, dict):
            return ("map",) + tuple(sorted((content(k), content(v))
                                           for k, v in value.items()))
        return value

    return content(local_value) == content(site_declaration(site)["value"])


# Which fingerprint field each migrating declaration would fill, so the block can
# refuse to assert a value the run may not have used. See fingerprint().
#
# A declaration that is missing from this map is invisible twice over: an artifact
# written under it records nothing about it, and build.py cannot price a change to it,
# because the only thing the build compares is what the artifacts recorded. That is
# what MIN_COMMON_WALLETS was until this line was added -- SETTING_STATE has called it
# "target" since the map was written, and no artifact carried the word. It records the
# declaration from here on; the artifacts written before this line stay silent about
# it, and the build reports the silence rather than guessing.
_TARGET_FIELD = {
    "MASTER_SEED": "master_seed",
    "N_PERM": "n_perm",
    "N_BOOT": "n_boot",
    "RANK_FLOOR_FILLS": "rank_floor_fills",
    "MIN_COMMON_WALLETS": "min_common_wallets",
}


def fingerprint(h=HEADLINE_HORIZON_S, lens=None, **overrides):
    """The block every results file stamps, so a number lifted out of a file still
    knows what produced it.

    WHY THIS FUNCTION REFUSES TO STATE SOME VALUES. A fingerprint is only worth
    stamping if every number in it is what the run actually used. The first version of
    this function copied every declaration into the block, including the ones
    SETTING_STATE marks as "target" -- values the tree is still migrating onto. A
    script that still draws 200 permutations would then have stamped n_perm 2000 into
    its own results file, and the artifact would assert something false about itself in
    the very block a reader consults to check it. That is worse than carrying no
    fingerprint, because it is not detectable by reading the artifact.

    So a field belonging to a migrating declaration appears only when the CALLER passes
    it, meaning the caller knows what its run used. Otherwise it goes into
    declared_not_confirmed, which says what settings.py declares while stating plainly
    that this run did not confirm it. Fields whose declaration is already in force
    everywhere are asserted directly.

    Anything a caller genuinely computed under a different setting is passed as an
    override and appears in the block, so a deliberate difference is visible instead
    of being indistinguishable from a drift.

    WHERE THE BLOCK GOES. Under the key `settings_fingerprint` inside the artifact's
    `_meta`, as a named sub-block. Two placements appeared on the day stamping began,
    the other being the fields written flat into `_meta`; the named sub-block is the
    convention because it cannot collide with a key the file already uses, and because
    a reader can point at one thing. checks/chk_settings_home.py finds the block in
    either position, so the flat form is detected rather than silently read as absent.
    """
    block = {
        "settings_module": "settings.py",
        "horizon_s": int(h),
        "is_headline_horizon": bool(h == HEADLINE_HORIZON_S),
        "headline_horizon_s": HEADLINE_HORIZON_S,
        "companion_horizon_s": COMPANION_HORIZON_S,
        "lens": lens,
        "headline_lens": HEADLINE_LENS,
        "reliability_seed": RELIABILITY_SEED,
        "fdr_alpha": FDR_ALPHA,
        "persistence_floor_fills": list(PERSISTENCE_FLOOR_FILLS),
        "whale_drop_k": WHALE_DROP_K,
        "horizon_source": "settings.py (set by ws1_horizon_results.json "
                          "final_decision.recommended_score_horizon_s)",
    }
    # A migrating declaration is asserted only if the caller states what its run used.
    unconfirmed = {}
    for name, field in _TARGET_FIELD.items():
        if field in overrides:
            continue
        value = globals()[name]
        unconfirmed[field] = list(value) if isinstance(value, tuple) else value
    if unconfirmed:
        block["declared_not_confirmed"] = dict(
            sorted(unconfirmed.items()),
            **{"note": "settings.py declares these; this run did not state what it "
                       "used, so they are the declaration and not a property of "
                       "this artifact"})
    if overrides:
        block.update(overrides)
        block["overridden"] = sorted(overrides)
    return block


def declaration_view(h=HEADLINE_HORIZON_S, lens=None):
    """The same block, with every migrating declaration stated at the top level.

    NOT FOR STAMPING, AND THE DIFFERENCE IS THE POINT. fingerprint() answers "what did
    this run use", and refuses to answer for a setting the run did not confirm. This
    function answers a different question: "what does settings.py declare right now",
    which has an answer for every declaration, confirmed or not.

    The build's skip rule asks the second question. It compares the declaration an
    artifact recorded against the declaration in force, and a value that only ever
    appears nested inside declared_not_confirmed cannot be compared at all -- which is
    why moving RANK_FLOOR_FILLS, N_BOOT or MIN_COMMON_WALLETS could not be priced
    before this function existed, and those are exactly the three whose move costs
    hours.

    Nothing is invented here: the values come from declared_not_confirmed, which
    fingerprint() already builds. Only the placement differs, and the placement is what
    a top-level comparison needs. The note line is dropped, because it is prose about
    the block rather than a setting.
    """
    view = dict(fingerprint(h=h, lens=lens))
    for name, field in sorted(_TARGET_FIELD.items()):
        value = globals()[name]
        view[field] = list(value) if isinstance(value, tuple) else value
    return view


def scope(h=HEADLINE_HORIZON_S, lens="print"):
    """Kept under its old name because artifacts already carry a block called scope.

    horizons.scope() was written as the block every results file should carry and was
    never called by anything; of 61 tracked results files, none carries a
    horizon_source field. fingerprint() supersedes it and states more.
    """
    return fingerprint(h=h, lens=lens)


# LAST LINE OF THE MODULE ON PURPOSE. Run here rather than beside SETTING_BASIS so that
# a declaration added anywhere in the file is inside the guard's reach; a guard placed
# next to the map would silently miss everything written below it, which is the same
# scope defect this module was built to remove.
_check_basis()
