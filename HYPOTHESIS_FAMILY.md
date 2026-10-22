# Declared hypothesis family

## Why this file exists

The project reports several thousand permutation p-values. Almost all of them are
sensitivity coordinates: the same estimator re-run across coins, horizons, order-book
lenses, minimum-fill thresholds, fee tiers, window pairs and random seeds. A reader who
treats every one of them as a separate finding is entitled to ask for a multiplicity
correction over the whole count, and under any such correction nothing in the project
would survive, because the permutation designs cannot produce p-values small enough. That
is an artefact of how the sensitivity grids are reported, not a statement about the
evidence.

This file removes the ambiguity by naming, in advance of any correction, the small set of
cells that carry the argument. Six claims are made. Each claim is assigned one head cell,
identified by artifact and key. The multiplicity correction is applied to that family and
to nothing else. Every other cell in the project is a setting on a panel around a head
cell, and the rule for reading those cells is stated in the section on the settings panel
below.

Where a claim has no head cell, the row is left empty rather than omitted. An empty row in
a declared family is more informative than a missing row.

## The family

Notation. "N" is the number of permutations or random draws behind the p-value. "Floor" is
the smallest value that design can return, equal to 1/(N+1). "On floor" records whether the
reported p-value equals that smallest attainable value.

| | Claim | Head cell | Artifact and key | N | Floor | p | On floor | After correction |
|---|---|---|---|---|---|---|---|---|
| C1 | Adverse-selection cost is a property of the counterparty rather than of the moment | Rank correlation of per-wallet toxicity between the first and second halves of every panel cell, corrected for split-half reliability, read against the book mid at ten seconds | `full_panel_results.json`, `within_window[lens=mid, horizon_s=10]`: 24 of 24 cells positive and significant, median 0.813, range 0.362 to 0.929 over three coins and eight windows; the same file's `cross_window` carries 84 across-window comparisons on that lens, all positive and 83 significant. **That file is held with the authors' working record and is not shipped in this repository.** It was written on 29 July 2026 by a script that is not shipped either. It predates the metadata block every artifact here now carries, so it records no producer hash, no input hash and no scope, which is why it was never brought in: an artifact with no provenance cannot be shipped beside artifacts that all have one, and a provenance block written after the fact would be a record of nothing. All six figures quoted above were recomputed from that file on 30 August 2026 and every one of them reproduced: 24 cells of 24 positive and 24 of 24 significant, median 0.8127, range 0.3624 to 0.9289 over three coins and eight windows, and 84 cross-window comparisons all positive with 83 significant. What this row does NOT claim is that a reader holding only this repository can open the file | 2000 | 5.00e-04 | 5.00e-04 | yes | survives |
| C2 | That cost is not recoverable from the publicly visible order book | Out-of-sample incremental R-squared of a counterparty fixed effect added to a model already carrying the full public book and tape | `i3_book_nonrecoverability_results.json`, `headline_by_coin.by_coin[ETH].incremental_oos_r2` = 0.4829, with the BTC companion at 0.0593. Each is one fold split, and the same file's `seed_robustness.cells[coin, horizon_s=10, K=50]` carries the forty-seed median with its range beside it, 0.4000 over 0.2448 to 0.5152 for ETH and 0.0594 over 0.0434 to 0.0814 for BTC | 2000 | 5.00e-04 | 5.00e-04 | yes | survives |
| C3 | Knowledge of the counterparty cannot be converted into money through quote width | Gain of a flat constant premium set to the same notional-weighted average width, against the gain of the identity-resolved premium, so that the share of the effect that is width rather than identity can be read off | `flat_surcharge_control_results.json`, `pooled`: the identity-resolved premium books 0.5231 bps; a flat premium at the same notional-weighted width books 0.4838, so **92.5 per cent of the gain is width and 7.5 per cent is identity**. Setting one constant per coin instead of one globally moves that to 0.4856 and 7.2 per cent. Per coin the residual is +0.0111 bps on BTC against +0.0766 on ETH, which is 2.8 per cent of the BTC gain against 10.7 per cent of the ETH gain. **Identity is worth almost nothing on BTC and something real on ETH**, which is the same coin split this study reports from two unrelated directions, and a third place where it has to be explained rather than averaged away. The control recomputes the published premium itself before it reports anything and refuses to report a residual unless that recomputation lands on the published value; it does, to a relative 4.2e-16. The same run settles which population the premium is booked over: unfloored reproduces, the headline rank floor of fifty does not (0.3134), so the term is charged over all 32,578 scored wallets and not over the 2,069 that clear the floor. The debt opened here on 2026-08-03 is paid: the producer now sits in this repository | not applicable | none | none | not applicable | not corrected: the comparison is deterministic and carries no test statistic |
| C4 | The value of the counterparty's identity comes from declining part of the flow | Cost reduction of the policy that declines the top toxicity decile, against a null of random wallet sets matched on total declined notional | `t1_backtest_results.json`, `pooled.by_measure.mid.t1_early_late_split_10s.policies.decline_top_decile.cost_reduction_pct` = 42.937 with `notional_given_up_pct` = 28.162; p at `pooled.by_measure.mid.t1_early_late_split_10s.size_matched_placebo.toxicity_vs_size_matched_p`. The book mid is the head lens, declared at `_meta.settings_fingerprint.headline_lens`; the trade-print companion under `by_measure.print` reads 92.041 on the same policy and is never the quoted figure | 1000 | 9.99e-04 | 9.99e-04 | yes | survives |
| C5 | The result is a reduction of cost, not a source of revenue | Sign of the net volume-weighted result of all six quoters at the base fee tier | `mm_bakeoff_results.json`, `bakeoff_ranking.pooled.by_tier.base.all_net_negative` = true. The six are the first six entries of `QUOTER_NAMES` in `quoters/mm_bakeoff.py`, which that file declares as the bake-off and appends to without reordering: `naive_at_book`, `naive_const`, `as_symmetric`, `gm_vpin`, `bbgl`, `as_toxicity`. Among those six the least costly is `bbgl` at -2.4757 bps, read from `.ordered_ascending_cost`. **The sibling key `.best_cost_least_negative` is not the address for this claim**: three further arms were added after the bake-off, all of them controls, so that key reports over nine and names `bbgl_flat` at -2.4358 bps, which is a width-matched control rather than a seventh quoter. The sign statement holds over both populations | not applicable | none | none | not applicable | not corrected: the statement is about the sign of six deterministic point estimates |
| C6 | Expensive counterparties are informed rather than merely faster. **Carried as an untested hypothesis and not as a tested claim of this family**: it has no head cell and no artifact, so nothing about it enters the multiplicity correction and nothing here should be read as having measured it | None | None | | | | | not a tested claim; no cell to correct |

### The correction, computed

The family has six claims, of which three carry a test statistic. Both corrections are
reported so that the reader can see they agree.

Bonferroni at level 0.05 over all six claims gives a threshold of 0.05/6 = 8.33e-03. All
three tested cells clear it: C1 and C2 by a factor of 16.7, C4 by a factor of 8.3. Taking
the family as the three tested cells instead gives a threshold of 1.67e-02 and the same
verdict with more room.

Benjamini and Hochberg at level 0.05 over the three tested p-values gives adjusted values
of 7.50e-04 for C1, 7.50e-04 for C2 and 9.99e-04 for C4. All three are below 0.05, so the
rejection set is identical to the Bonferroni one. The two procedures agree here because
the family is small and the p-values sit far below the level.

Two numbers in this section were corrected on 2026-07-31 and the corrections are recorded
rather than quietly applied. The budget for C2 was written here as 1000 draws with a floor
of 9.99e-04, while the artifact it cites carries `n_perm` of 2000 and a stored value of
1/2001; the caption had not been updated after the budget was raised. Separately, the
adjusted values printed above were wrong even at the earlier p-values: the step-up
procedure takes a running minimum from the largest p-value down, and applying it to the
earlier triple returns 9.99e-04 for all three rather than the two values of 1.50e-03 that
stood here. Neither correction changes any verdict, and both were found by reading the
artifact against the caption rather than by recomputing the number.

Four head cells of the table above were re-read from their artifacts on 2026-08-03 and
three of them moved, so the moves are recorded here rather than quietly applied. The
cause of all three is one change: the entry leg of the markout join now takes the book
mid from a snapshot stamped strictly before the fill, where it used to accept a snapshot
carrying the fill's own impact. C2 moved from 0.4662 to 0.4829 on ETH and from 0.0561 to
0.0593 on BTC. C5 moved from -2.1462 to -2.4757 bps, and part of that gap was never the
join at all: the earlier figure was the least costly quoter at the ten-fill rank floor
rather than at the declared fifty, so it answered a question the caption did not ask. C4
moved for a different reason again: its address had gone dead. The path the caption gave
no longer exists in the file, because the policy block is now cut by measure before
anything else, and the 82.704 that stood beside it is today the trade-print figure of the
sixty-second window rather than anything on the declared cell. On the declared lens and
window the reduction is 42.937 per cent. None of the three moves changes a verdict in the
correction above, because every p in the family is unchanged. The fourth cell, C3, could
not be re-read on that day and was declared debt. **That debt was paid afterwards, so this
paragraph is the account of 2026-08-03 and not the current state**: the control now sits in
this repository as `probes/flat_surcharge_control.py`, and the C3 row above carries the figures
it produced.

C3 and C5 are not part of the correction because neither has a test statistic. C3 is a
comparison of two deterministic quantities computed on the same fills, and C5 is a
statement about the sign of six deterministic point estimates. Neither can be made
significant or insignificant by a multiplicity correction, and neither should be presented
as if it had been tested. C6 has no cell at all.

### Why a correction over the whole count is not attempted

A census of the project's stored results files, after removing byte-identical copies,
returns 4,837 raw p-values across 37 artifacts, of which about 83 per cent sit exactly on
their own floor. Bonferroni at level 0.05 over that count sets a threshold of 1.03e-05.
The finest floor anywhere in the project is 5.00e-04, from the designs that use 2,000
permutations. That floor is 48 times coarser than the threshold, so no cell in the project
could clear a project-wide Bonferroni correction regardless of the underlying effect. Even
at 20,000 permutations the floor would be 5.00e-05, still about five times too coarse;
clearing the threshold would take on the order of 97,000 permutations per cell.

This is the reason the family is declared rather than inferred from the count. The
declaration is made once, before the correction, and it is the reader's protection against
a family chosen after the fact to contain whatever happened to survive.

## How every other cell is read

Every p-value in the project outside the six rows above is a setting on a panel around a
head cell, not a separate finding. The panels vary the order-book lens (trade print
against book mid), the markout horizon (1, 10 and 60 seconds), the minimum-fill threshold
K, the fee tier, the coin, the calendar window and the fold or shuffle seed. They exist to
show that a head cell is not a lucky corner of its own grid, and they are reported in full
for that reason.

Three consequences follow, and they are binding on the prose of the paper.

First, a panel cell is never quoted on its own as evidence for a claim. When a panel cell
is quoted, it is quoted as the range or the count of the panel, for example the number of
window pairs that keep the sign, never as a p-value standing by itself.

Second, a panel cell that disagrees with its head cell is a limit on the head cell's scope,
and is reported as such in the same sentence. Two are known and are stated in the paper.
The book-recoverability result of C2 has the opposite reading on the two coins, 0.4829 for
ETH against 0.0593 for BTC, and the claim holds as stated only for ETH. The cross-window
persistence behind C1 is positive in all 168 window-pair comparisons of the ten-second
panel across both lenses, of which 84 use the book mid, but at the sixty-second horizon the
August to October pair for BTC is negative at -0.1432 with a permutation p of 2.00e-03. The
claim of C1 is therefore a claim about the ten-second horizon, and the horizon is named
wherever the claim appears.

Third, the multiplicity correction of the declared family is not re-run over panels. The
nine per-object corrections that already exist inside the analysis scripts remain where
they are and keep their own meaning, which is stated in the section below.

## What a p-value on the floor means

All three tested head cells, and about 83 per cent of the permutation p-values stored
anywhere in the project, are reported at exactly 1/(N+1). That is the smallest number the
permutation design can
return, and it is reached whenever no permuted draw matches or exceeds the observed
statistic. It is a bound, not a point estimate. The correct reading is that the tail
probability lies at or below the floor, with no further resolution available at that number
of permutations. A cell at the floor with 200 permutations and a cell at the floor with
2,000 permutations are not equally strong, and the number of permutations is reported next
to every such value for that reason.

Nothing in this project quotes a floored p-value as though it were a measured tail
probability, and no floored value is compared with another floored value to argue that one
effect is stronger than another.

## How the tail is counted, and what happens to a draw that returns no number

Two details of a permutation test change the number it returns, and neither is visible in
the number itself, so both are stated here for every value quoted in this document.

The first is whether a draw that ties the observed statistic is counted. A design that
counts a draw only when it strictly exceeds the observation returns a smaller p-value than
one that also counts equality within a numerical tolerance, and the difference is exactly
one unit of the floor per tied draw. On a budget of 2,000 that unit is 5.00e-04. C1 counts
ties with no tolerance at all. C2 and C4, and the persistence values quoted in the
supporting reports, count them with an absolute tolerance of 1e-12. The tolerance is
absolute rather than relative, which means it is a real allowance for statistics of order
one, such as a rank correlation or a share of variance, and no allowance at all for a
statistic measured in dollars, where 1e-12 falls below the last representable digit.

The second is what happens to a draw that produces no number, which occurs when a shuffle
leaves a cell with too few observations to compute the statistic. Three treatments exist in
the code: the draw is discarded and the denominator shrinks to the number of usable draws;
the draw is replaced by a value that can never be extreme and stays in the denominator; or
the draw is left as a non-number, which compares false and likewise stays in the
denominator. Discarding raises the p-value relative to the other two, by the ratio of the
requested budget to the usable count.

Neither detail affects any value quoted here, and that is a measurement rather than an
assumption. Every stored p-value in the repository is of the form (k+1)/(u+1), so the
denominator u can be recovered from the stored number and the declared budget. Recovering
it for every stored permutation p-value returns the full declared budget in each case, and
the artifacts that print the count directly agree: the fields recording usable and dropped
draws read equal to the requested budget and zero respectively. No draw has ever failed, so
the three treatments coincide on this tree. Ties are equally absent: no draw reaches the
observed statistic in any of the three tested head cells, whose observations sit between
3.3 and 16.7 null standard deviations above the null mean, so a tolerance of 1e-12 has
nothing to admit.

## The nine per-object corrections

Nine analysis scripts apply a Benjamini and Hochberg correction at level 0.05 inside
themselves, each over the family of cells that script produces. Those families are the
cell grid of one design, differing only in nuisance settings, and the correction answers a
well-posed question within each: which cells of this one design survive control of the
false discovery rate. The recorded sizes are 4, 8, 10, 12, 12, 12, 20, 48, 48 and 448;
the remaining family is assembled at run time from the coin-month cells of the panel
build and is 9 on the three-coin, three-window panel.

The size 448 was missing from this list until 2026-07-31 and the omission is recorded
rather than quietly repaired. Three artifacts of the extended panel, the arms that carry
all eight calendar windows rather than the canonical three, record a family of 448
alongside 224 distinct comparisons, and they recorded it on the day this paragraph was
first written. The list was therefore never a census of what the files hold: it was
assembled from the designs the writer had open. The consequence is not cosmetic, because
448 is the one family in the project whose rank-one threshold sits below the permutation
floor, and the section below states what that costs.

Those corrections are kept as they are, and no attempt is made to merge them into one. The
reason is that they are corrections over different designs measuring different quantities,
so a merged family would have no interpretable meaning; and the merged correction would in
any case be dominated by the panel, which contributes about nine tenths of the project's
p-values through cells that are near-duplicates of one another, so the adjustment would be
driven by the redundancy of a single design rather than by the number of distinct
questions asked.

Two counting points are recorded here because they affect how the per-object families
should be read. The cross-window persistence family stores every comparison twice, once in
each direction, because the rank statistic is symmetric and the code enumerates ordered
pairs; the stored family size of 48 is 24 distinct comparisons, and the family size of 168
in the wider panel is 168 across both lenses, 84 of which use the book mid. The rejection
set is the same either way, but the family size quoted in prose is the distinct count.

## The permutation budget of every producer, against its own family

A permutation test cannot return a p below its own floor, 1/(N+1) on N draws. Benjamini
and Hochberg compares the smallest p of a family against alpha/m, so a budget whose floor
sits near that bar puts every floored p on a boundary where the last digit of the
correction, and not the evidence, decides the verdict. The module states the requirement
as an inequality and separates the one arguable part of it:

    1 / (N + 1)  <=  alpha / (margin * m)

with `FDR_ALPHA` = 0.05 and `PERM_FLOOR_MARGIN` = 2. The margin is a judgement and is
declared as one; the inequality it feeds is arithmetic. The ratio reported below is
(alpha / m) divided by 1/(N+1), so a producer clears the requirement when its ratio is at
least 2.

The comparison that matters is against the producer's OWN family and not against the
reference family the module sizes the default budget for. That reference is 48, read off
the cross-month correction of the canonical panel, and it is the family the DEFAULT is
chosen for, not a family every producer inherits. A script whose family is larger passes
its own size to the same function and gets its own budget.

### How this census was taken

The population is every tracked Python file in this repository. Anchoring on the draw
alone is not enough, because a helper can draw while its caller computes the p, and the
draw itself has more spellings than one pattern holds: a shuffle, a permuted index, an
argsort of random keys, and a size-matched selection are all draws. Anchoring on the
verdict alone is not enough either, because four producers deliberately count their own
tail rather than call the shared helper, each for a stated reason. The census is therefore
the union of the two anchors, adjudicated file by file, and each producer's family was
then read from the correction block or the verdict rule in its own artifact rather than
inferred from the number of p-values it stores.

The predicate was calibrated on two opposite cases before it was trusted, and inside one
file so the calibration cannot drift between files: in the out-of-sample non-recoverability
script, the shuffle that permutes the wallet labels of the history fixed effect must be
found, and the shuffle four hundred lines earlier that assigns cross-validation folds must
not be, because the second produces no null distribution and no p. Three earlier drafts of
the predicate failed one side or the other, and each failure is the same kind: a count that
is easy to take standing in for the count that was asked for.

### The table

"N" is the draws the producer makes and the column beside it says where that number comes
from. "m" is the size of the producer's own family, with the grid it is counted over.
"Ratio" is (alpha/m) / (1/(N+1)), and the class follows from it.

| Producer | N | N comes from | m | m counts | Ratio | Class |
|---|---|---|---|---|---|---|
| `probes/probe_F_hlp_liq.py` | 2000 | `settings.N_PERM` | 3 | 3 coins, liquidation column | 33.35 | a |
| `probes/probe_G_horizon.py` | 2000 | literal 2000, equal to the declared value | 3 | 2 coins and pooled | 33.35 | a |
| `t1_toxicity_skew_backtest.py`, count-matched placebo | 2000 | `settings.N_PERM` | 3 | 2 coins and pooled | 33.35 | a |
| `ks2_persistence_10day.py` | 2000 | `settings.N_PERM` | 4 | 2 coins by 2 fill floors | 25.01 | a |
| `t1_toxicity_skew_backtest.py`, size-matched placebo | 1000 | `settings.perm_draws("t1_size_matched_placebo")` | 3 | 2 coins and pooled | 16.68 | a |
| `i3_depth_control.py` | 2000 | `settings.N_PERM` | 6 | 2 coins and pooled, by 2 fill floors | 16.68 | a |
| `i5_exclusion.py` | 2000 | `settings.N_PERM` | 6 | 2 coins and pooled, by 2 split rules | 16.68 | a |
| `temp_perm_decomp.py` | 2000 | `settings.N_PERM` | 6 | 2 coins and pooled, by 2 fill floors | 16.68 | a |
| `panel_common_idio.py` | 2000 | `settings.N_PERM` | 8 | 3 coins and pooled, by 2 fill floors | 12.51 | a |
| `panel_build.py` | 2000 | `settings.N_PERM` through `CELL_PERM_DRAWS` | 9 | 3 coins by 3 windows, counted at run time | 11.12 | a |
| `m9_crossasset.py` | 2000 | literal 2000, equal to the declared value | 10 | 2 horizons by 5 fill floors | 10.01 | a |
| `i3_nonrecoverability_oos.py` | 2000 | `settings.N_PERM` | 12 | 2 coins and pooled, by 2 horizons, by 2 fill floors | 8.34 | a |
| `i3_book_comparator.py` | 2000 | the same constant through the script above | 12 | 2 coins and pooled, by 2 horizons, by 2 fill floors | 8.34 | a |
| `own_size_control.py` | 2000 | `settings.N_PERM` | 20 | 2 coins, their two whale-dropped arms and pooled, by 2 horizons, by 2 fill floors | 5.00 | a |
| `panel_analyze.py` | 2000 | the same constant through the non-recoverability script | 48 | 3 periods by 3 coins and pooled, by 2 horizons, by 2 fill floors | 2.08 | a |
| `panel_persistence.py`, canonical arms | 2000 | `settings.N_PERM` | 48 | 3 periods giving 6 ordered pairs, by 2 fill floors, by 3 coins and pooled | 2.08 | a |
| `panel_persistence.py`, all-window arms | 2000 | `settings.N_PERM` | 448 | 8 periods giving 56 ordered pairs, by 2 fill floors, by 3 coins and pooled | 0.22 | b |
| `probes/probe_E_leadlag.py` | 50 | `settings.perm_draws("leadlag_randomised_lag_placebo")` | 2 | one test per coin, on the pair the coin's verdict is read off | 1.28 | b |

Class a means the floor sits at least the declared margin below the rank-one bar and
nothing is owed. Class b means it does not. Class c, below, is the exclusion by the kind
of quantity.

### The two producers in class b, and what raising them costs

The all-window arms of the extended panel are the only place in the project where the
floor sits ABOVE the rank-one bar rather than merely close to it. At 448 cells the bar is
0.05/448 = 1.116e-04 and the floor at 2000 draws is 4.998e-04, so a cell alone at the floor
could not be rejected at rank one however strong the effect. Satisfying the declared margin
at that family size takes 17,919 draws, which the budget convention rounds to 18,000.

What actually happened on the stored run is stated beside that, because the two are
different questions and the difference is the point of keeping a rank-one requirement. The
correction rejected 445 of the 448 cells, so the step-up cutoff it applied was 0.0497 and
not the rank-one bar, and every floored p cleared it by a factor of about ninety-nine. The
requirement is not about this run. It is about the run in which one cell is significant and
the rest are not, where the applied cutoff collapses onto the rank-one bar and a floored p
is rejected for the width of its floor rather than the size of its effect.

The price is measured and not guessed. Each of the three arms records a runtime of 257.1,
257.1 and 258.7 seconds at the present budget. Nine times the draws multiplies the
permutation work by nine and leaves the rest of the arm unchanged, so 9 times 258.7 seconds
is an upper bound of 38.8 minutes for the slowest arm and under two hours for all three.

The lead-lag placebo is the cheaper of the two and the one whose position is worse. It
draws 50, its floor is 1/51 = 0.0196, its family is the two per-coin significances the probe
asserts, and both of them sit exactly on that floor. The bar is 0.05/2 = 0.025, so the ratio
is 1.28 against the 2 required. The declared margin is satisfied at 79 draws, which is 1.58
times the present budget; the arm records a runtime of 457.6 seconds, so the upper bound is
12.1 minutes. The reason the budget was set low is stated in the probe itself and is real:
one draw is a Hayashi and Yoshida scan over the raw ticks of both venues across the whole
window. At 79 draws the floor becomes 1/80 = 0.0125 and the ratio becomes exactly 2.

### Class c: producers excluded by the kind of quantity

A permutation whose draws never become a verdict is not asking the question the inequality
answers, so sizing its budget by that inequality would size it by a requirement that does
not apply. Each producer below is excluded on that ground, and each row says what the draws
are for instead. The test applied was mechanical rather than editorial: a producer is in
this list when no p of its own is compared against a significance threshold anywhere in its
source, and when its own artifact records no boolean that reads a p.

| Producer | N | Cells | What the draws are for instead |
|---|---|---|---|
| `ks2_persistence_10day.py`, per-day arm | 1000 | 20 | the denominator of a variance ratio, which has no threshold to pass; the file's correlation p-values come from a second budget of 2000 in the same run |
| `ks2_markout_multiday.py`, per-day arm | 1000 | 20 | the same variance ratio on the multi-day window, likewise with its correlation p-values on a second budget of 2000 |
| `ws1_horizon_persistence.py` | 2000 | 56 | the horizon panel: the scoring horizon is chosen on the persistence curve and the information-complete fraction, and the placebo confirms the sign of each cell. The spread it certifies, read from `ws1_horizon_results.json` at `pooled.{1,10,120}.rho_disatt`, is 0.7502 at one second down to 0.2313 at a hundred and twenty, with the chosen ten seconds at 0.5267 |
| `i2_walletfe.py` | 2000 | 18 | the panel of wallet fixed-effect cells around the counterparty claim; the cells are read as a count and a range |
| `follow_the_informed_oos.py` | 2000 | 8 | the verdict is whether the toxicity-selected net beats the shuffled net, a comparison of two point estimates, and the economic bar beside it is a level in basis points |
| `maker_econ.py` | 2000 | 12 | the verdict is whether the observed reduction exceeds the null MEAN, not whether a p clears a threshold |
| `maker_econ_b2.py` | 2000 | 4 | the same rule on the second maker arm |
| `mm_bakeoff.py` | 2000 | 3 | the same rule across the quoter comparison |
| `m4_realizedpnl.py` | 2000 | 3 | the p accompanies a rank correlation that is reported with its bootstrap interval, and no verdict is read off it |
| `ws2_hard_classifier.py` | 2000 | 1 | one area-under-curve cell reported with its floor; the 0.05 elsewhere in that file is a z-score cut on wallets and not this p |
| `ws3_taker_pnl.py` | 2000 | 3 | three rank-agreement cells reported with their intervals |
| `forward_toxicity.py` | 1000 | 3 | the forward window, whose three p-values are measured rather than floored, at 0.1588, 0.2348 and 0.6354; the budget and its floor are declared in the artifact with the reason |

The exclusion is a claim about the present state of these files and it is checkable. Any
edit that makes one of them compare a p against a threshold moves it out of this list and
into the table above, where it acquires a family and a ratio.

## Standing conditions

This declaration is made against the artifacts as they stand. Three conditions attach to
it, and each is stated in the paper where the corresponding claim appears.

The head cell of C1 reports a reliability-corrected correlation of 0.5267, read from
`ws1_horizon_results.json` at `pooled.10.rho_disatt`, while the permutation and the
bootstrap interval attached to it both refer to the uncorrected 0.1935 at
`pooled.10.rho_obs` in the same block. The correction multiplies by 2.72, which is one over
the square root of the product of the two split-half reliabilities recorded beside them,
and it carries no interval of its own, so the tested quantity and the quoted quantity are
not the same quantity.

The head cell of C4 is tested against random wallet sets matched on total declined
notional, and beats that null by a wide margin. The same artifact records what a rule that
ranks wallets by notional alone reaches, and on the declared lens that rule is the stronger
of the two: 54.659 per cent at
`pooled.by_measure.mid.t1_early_late_split_10s.size_matched_placebo.size_only_top_decile_by_notional_reduction_pct`
against the 42.937 per cent of the toxicity rule. Under the trade-print companion the
ordering is the other way, 79.263 against 92.041. The artifact states beside that field
that ranking a fixed number of wallets by notional turns away more notional than the toxic
set does, so it is an upper bound on what size alone can reach rather than a like-for-like
baseline; the like-for-like baseline is the size-matched random mean, 28.550 per cent on
the declared lens. The declared claim is therefore about the marginal value of toxicity
over a size-matched random set, and not about toxicity being the best available ranking.
That distinction is load-bearing on the declared lens and the paper states it wherever the
claim appears.

The head cell of C5 is one cell of a surface, and how large that surface is and how much of
it is positive are two counts with no home in any artifact. `mm_bakeoff_results.json`
records the verdict at `cross_checks.all_quoters_net_negative_at_base` and at
`bakeoff_ranking.pooled.by_tier.base.all_net_negative`, both true, but it stores no census
of its own grid; the only stored count of positive cells,
`fill_aware_b2.n_positive_grid_cells`, belongs to a different and deliberately uncapped
grid and is excluded from that verdict by design. A count of the quoter surface therefore
has to be taken by sweeping the file, and a swept count is not a reported quantity. The
figures 430 of 2,592 stood here until 2026-08-03 with no address behind either of them and
are withdrawn rather than replaced. **Declared debt, opened 2026-08-03**: the bake-off
should store the census of its own net-result grid, as a total and as a count of positive
cells cut by measure and by fee tier, so the scope sentence in the paper has an address.
What is not in doubt and is stored is the head cell itself: the claim holds at the base fee
tier under the conservative book-mid measure, which is the cell named in the table above,
and the paper states that scope wherever the claim appears.
