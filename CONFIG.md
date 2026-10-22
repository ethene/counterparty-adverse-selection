# Configuration

**`settings.py` is the single home for every setting that moves a reported number.**
A quantity declared there is not declared anywhere else, and a script reads it
through that module instead of typing a value. Read `settings.py` first: each
declaration carries what the quantity means and by what argument the value was
chosen, and `SETTING_STATE` at the end of that file says which declarations every
consumer already follows and which are still being migrated.

This document explains the settings and says where each one is consumed. **It holds
no values.** A value printed here would be a second copy of the number, and a second
copy is the defect `settings.py` exists to remove: the two copies drift, and nothing
raises when they do. Where a number appears below it is a measured property of the
data rather than a setting, and the artifact it was measured from is named beside it.

## How a setting reaches a script

Three routes, and a reproducer needs to tell them apart.

1. **Declared in `settings.py`** and read from there. This is the intended route and
   the one most scripts now take.
2. **A module-level literal still sitting in the script.** This is migration debt,
   because a literal is what makes two files disagree about one quantity. The tables
   below name where the debt sits, but they name it as of the day they were written.
   **The live count is `checks/chk_settings_home_results.json`**, which the guard
   rewrites on every run with the file and line of every remaining site. Read that
   file before trusting a list here, and prefer it when the two disagree.
3. **Read at run time from the environment or the command line.** A run of the same
   file can then differ from another run of it. Left at their defaults these knobs
   reproduce the reported results; the next section lists all of them.

Two guards keep the routes from blurring. `checks/chk_settings_home.py` carries five
rules, one per way a second home appears: a setting declared outside its home, a built
key that collides with a typed one, an artifact whose stamped fingerprint is stale, an
input chosen by the state of the filesystem rather than by a declaration, and a
notebook mirror that no longer agrees with what it mirrors. Its results file counts
each rule separately, under the keys `n_rule1_second_home` through
`n_rule5_notebook_mirror`. `checks/chk_headline_horizon.py`
looks for a scoring window fixed by a column spelling rather than by a declaration.
Both carry a baseline that may only move downward, and both write a results file
beside themselves that names their scope and their exclusions.

## Run-time knobs, in full

The census below was taken by walking the syntax tree of every tracked `.py` file
in this repository, not by searching for text. Retaken on 4 August 2026 over 109 tracked
`.py` files, it returns **twenty-three environment variables and forty-five
command-line flags**, eleven of the flags declared by `build.py`, the build entry point,
on its own. The two counts that stood here before that day, twenty-two and thirty-one,
were taken on a smaller tree; the flag figure had drifted furthest, because a flag is
added whenever an entry point grows a question it can answer without computing.

**A command-line flag** is a string literal beginning with two dashes standing as a
positional argument of `add_argument`. That predicate is unambiguous and the count under
it is exact.

**An environment variable** needs two predicates rather than one, and the difference
between them is a finding rather than a technicality. The narrow one, which is what this
document used to state, is a string literal standing as the first argument of
`os.environ.get` or `os.getenv` or as the subscript of `os.environ[...]`. It misses a
live route: `panel_io.py` holds a tuple of names, `DATA_ROOT_ENV`, and reads each of them
in turn, and `check_first.py` passes its own tuple in as `env_names=("CAP_CHECK_ROOT",)`.
A name travelling inside a tuple never stands as anybody's first argument, so under the
narrow predicate `CAP_CHECK_ROOT` reads as absent from a repository that reads it in two
files. The wider predicate used here is a string constant of the exact shape `CAP_<UPPER>`
or `PANEL_<UPPER>` appearing anywhere in a syntax tree, anchored at both ends so that a
name mentioned inside a printed sentence is part of a longer string and does not match.
It is calibrated on two opposite cases: it must find `CAP_CHECK_ROOT`, which only the
tuple route reaches, and must not find an invented name of the same shape.

One name the wider predicate returns is excluded by hand and the reason is stated here
rather than left as a discrepancy: `PANEL_COINS` occurs as a string only in the alias
list of `checks/chk_settings_home.py`, where it names a Python constant the guard looks
for, not a variable anything reads from the environment. Twenty-four names match, that
one is not a knob, so twenty-three are.

### Environment variables

| Variable | Read by | What it moves |
|---|---|---|
| `CAP_KEEP_RAW` | declared in `build_quickwin_markouts.py` and named in `build.py`, which carries the key so the skip rule can fingerprint it. Five further files act on it and none of them spells it: `ks2_persistence_10day.py`, `ks2_markout_multiday.py`, `panel_rebuild_v2.py`, `checks/chk_field_hygiene.py` and `checks/chk_liquidation_field.py` all call `build_quickwin_markouts.keep_raw_days()` rather than re-reading the environment, which is why a search for the name finds two files and the behaviour is in seven | Whether a day of raw tape survives the run that parsed it. Unset, the day is deleted the moment it is parsed, which is the default a long unattended run wants. Set to `1`, it stays. It matters for more than disk: a node whose input is deleted before the artifact is written has nothing left to fingerprint, so it can never be *proved* unchanged, only assumed; and three nodes here walk the same ten days, so without it one wave pays three downloads of identical bytes. |
| `CAP_RAW_CACHE` | the same, through `build_quickwin_markouts.raw_cache_dir()` | Which directory a downloaded day lands in and is looked for. Defaults to the system temp directory. A day already there with a full complement of hourly files is reused instead of re-fetched, and a partial one is not: it falls through to the same count test that accepts a fresh pull. The two files agree on the directory NAME as well, which they did not until 2 August 2026 — one wrote `quickwin_<day>`, the other `ks2day_<day>`, and that alone made one wave fetch the same bytes twice. |
| `CAP_DAYS` | `as_quoter.py`, `gm_quoter.py`, `i3_book_comparator.py`, `i4_l2_mid.py`, `i4_midmarkout.py`, `maker_econ.py`, `mm_bakeoff.py`, `panel_rebuild_v2.py`, `probes/probe_G_horizon.py` | Narrows the run to the listed trading days. |
| `CAP_COINS` | the same nine files | Narrows the run to the listed coins. |
| `CAP_HOURS` | `i3_book_comparator.py`, `i4_l2_mid.py` | Narrows the book pull to the listed hours. |
| `CAP_DAYS_E` | `probes/probe_E_leadlag.py` | The lead-lag probe's own day list, kept separate from `CAP_DAYS`. |
| `CAP_DATA_ROOT` | `i3_book_comparator.py`, `own_size_control.py`, `panel_common_idio.py`, `temp_perm_decomp.py`, and `panel_io.py`, which holds it in the shared tuple `DATA_ROOT_ENV` | Where the intermediates are read from. Also settable with `--data-root`. |
| `CAP_DATA_DIR` | `mm_bakeoff.py`, and `panel_io.py` in the same tuple | The same idea under the name that file uses. |
| `CAP_L2_CACHE` | `i4_l2_mid.py` | The local order-book cache directory, so a multi-window pull cannot disturb the December cache. |
| `CAP_MID_SUFFIX` | `i4_l2_mid.py` | Suffix on the mid-series output name, so a rebuild writes beside the December artifact instead of over it. |
| `CAP_FORWARD_DIR` | `forward_toxicity.py` | Where the forward-recorded feed is read from. |
| `CAP_BOOT_CAP` | `mm_bakeoff.py` | Ceiling on rows entering one bootstrap draw. This is the size of a draw and not the number of draws; the two multiply rather than compete, so the cap cannot hold the budget below what `settings.py` declares. `CAP_N_BOOT` stood beside it until 2026-07-31 and was removed with the adoption of the declared budget: an environment variable that overrules a declaration puts the effective setting on the machine rather than in the repository, which is what this file exists to prevent. |
| `CAP_CHECK_ROOT` | `check_first.py`, which passes it as `env_names=("CAP_CHECK_ROOT",)`, and `panel_io.py`, which holds it in `DATA_ROOT_ENV` | Directory the first-pass check walks. It reaches the environment only inside a tuple, which is the route the narrow predicate above cannot see. |
| `CAP_ALLOW_OPEN_TAIL` | `forward_toxicity.py` | Whether a daily file that ends in a broken gzip stream may be read anyway. Unset, a short read stops the run and prints the file, the rows it did read and the rows it expected. Set to `1`, the run proceeds and the count of rows kept is written into the artifact, so what the run saw is recorded rather than guessed. It exists because tolerance for a truncated input had been unconditional and silent, and an incomplete transfer of a closed day is indistinguishable from the live recorder's still-open file for today unless somebody says which one it is. |
| `CAP_REPO_ROOT` | `check_first.py` | Repository root the same check resolves paths against. |
| `CAP_LIQ_DAY`, `CAP_LIQ_HOUR` | `checks/chk_liquidation_field.py` | The raw hour that check re-walks for the liquidation-object verification. |
| `CAP_TRADES_TAR` | `checks/chk_maker_attribution.py` | Path to the raw trades archive that check reads. |
| `PANEL_DATA_ROOT` | `panel_analyze.py`, `panel_build.py`, `panel_persistence.py`, and `panel_io.py` in `DATA_ROOT_ENV` | Where the panel intermediates live. |
| `PANEL_V2_DATA_ROOT` | `panel_rebuild_v2.py`, and `panel_io.py` in the same tuple | The same for the second panel build, kept separate so the two cannot overwrite each other. |
| `PANEL_IO_SELFCHECK_ROOT` | `panel_io.py`, and nowhere else | Not a knob of the pipeline. `panel_io.py` sets and deletes it inside its own self-test, to prove that a named environment variable beats the module's directory when both could answer where the data is. It is listed here because the census returns it and an unexplained name in a census reads as a knob nobody documented. |
| `PANEL_SMOKE_COIN`, `PANEL_SMOKE_DAY` | `panel_build.py` | One coin and one day for a smoke build. Also settable with `--smoke-coin` and `--smoke-day`. |

### Command-line flags

| Flag | Script | What it moves |
|---|---|---|
| `--source {trade,mid}` | `ks2_persistence_10day.py`, `i3_nonrecoverability_oos.py` | Which reference price the harm is measured against. See the lens section. |
| `--horizon` | `panel_extended.py` | The window the extended panel is read on; defaults to the declared headline. |
| `--periods {all,canonical}` | `panel_extended.py` | Whether every window or only the canonical ones enter the run. |
| `--out` | `panel_extended.py` | Output file name. |
| `--build`, `--analyze` | `panel_persistence.py` | Which half of that script runs. |
| `--coin`, `--period`, `--days` | `panel_persistence.py` | The cells built or analysed. |
| `--stage` | `i3_book_comparator.py`, `build.py` | In the first, which stage of the book comparison runs; in the second, which stage of the build. The two files spell their own stage names and the flag is not shared between them. |
| `--data-root` | `check_first.py`, `i3_book_comparator.py`, `own_size_control.py`, `panel_common_idio.py`, `temp_perm_decomp.py` | Same as `CAP_DATA_ROOT`; the flag wins when both are given. |
| `--repo-root` | `check_first.py` | Same as `CAP_REPO_ROOT`. |
| `--smoke-coin`, `--smoke-day`, `--no-merge` | `panel_build.py` | Smoke build and whether the shards are merged. |
| `--smoke` | `checks/chk_join_nolookahead.py` | Runs that check on a slice. |
| `--data`, `--network`, `--tape`, `--timeout` | `checks/run_all_checks.py` | Which opt-in dependency groups run and how long each check may take. `--data` adds the check over the ignored `quickwin_markouts.npz` intermediate; the other two add live fetches and raw-tape walks. |
| `--only` | `checks/run_all_checks.py`, `build.py`, `checks/chk_run_happened.py`, `run/_groups.py` | Restricts the run to the named checks in the first, to the named nodes in the second and fourth, and to the named artifacts in the third. |
| `--root`, `--since`, `--since-file` | `checks/chk_run_happened.py` | Which tree that gate walks, and the reference moment a recompute has to be later than. The reference has no default on purpose: without one the first of that gate's two legs is not answered but silently skipped, so it is either given as a timestamp or taken from the modification time of a named file. |
| `--list`, `--pair` | `checks/chk_contrast_hygiene.py` | Print every pair of arms the gate knows about and stop, or judge one named pair instead of all of them. |
| `--members`, `--census` | `run/_groups.py`, and so every entry point in `run/` | What the group holds and why each script is in it, and the whole group table put against the dependency graph. Neither computes anything. |
| `--group`, `--png`, `--check`, `--stdout`, `--selftest` | `build_diagram.py` | Draw the nodes of one named group instead of the nine boxes, render the picture as well as the Mermaid text, print the reconciliation of the drawing against the graph and exit non-zero when it fails, print the document instead of writing it, and run the file's calibration cases and exit. Only `--png` writes an image, and rendering is opt-in because it needs mermaid-cli, a Node program that is deliberately not one of the requirements; without it that run exits non-zero and says so rather than leaving a truncated file behind a zero exit code. |
| `--start`, `--end` | `probes/probe_D_pull.py` | The probe's pull window. |
| `--part`, `--zenodo-interim` | `probes/probe_F_hlp_liq.py` | Which part of that probe runs and which input it reads. |
| `--run`, `--plan`, `--graph`, `--json`, `--out-dir`, `--what-if`, `--self-test`, `--run-unprovable` | `build.py` | The build entry point's own knobs: run the plan instead of printing it, print the plan, print the dependency graph and stop, machine-readable output, where the build's own record goes, what moving one settings field would schedule, the file's proof that its skip rule skips, and whether a node the skip rule can put no question to is launched anyway. Only the last of the eight changes what is computed, and it changes which nodes run rather than what any of them computes. Counting `--stage`, `--only` and `--argv` from the rows above, `build.py` declares eleven flags, which is why the flag count of this repository moves with it. |
| `--argv` | `build.py` | The one build flag that does reach a computation: everything after it is forwarded verbatim to the producer being run, so a run-time knob of that producer can be set through it. |

## The scoring window

| Setting | Where declared | Where consumed | Meaning |
|---|---|---|---|
| `HEADLINE_HORIZON_S` | `settings.py` | every script that scores or ranks reads it as `settings.HEADLINE_HORIZON_S`, and `checks/chk_headline_horizon.py` counts what is left and writes the number into its results file; the reproduction notebook declares it once for itself, because it also runs detached from this repository | **Two decisions stand on this one declaration and they are not one decision.** The cost window asks how long after a fill the permanent price move has arrived, and is defended by the completeness curve alone. The ranking window asks over how long a counterparty's markout must be averaged before the ordering of counterparties reproduces on days it was not fitted on, and is defended by the early-to-late rank persistence alone. The two criteria pull opposite ways, so a single number is available only where both clear at the same rung, which is what `ws1_horizon_persistence.py` records in `ws1_horizon_results.json`: at the chosen window the permanent move is nearly fully impounded while the noise-corrected persistence is still well above what the long window gives. That file is the evidence behind the declaration, not a second opinion on it, and the choice between rungs is a stated human judgement on top of the grid rather than a grid maximum. `settings.py` says which of the two criteria each figure belongs to. |
| `LADDER_S` | `settings.py` | every producer writes one markout column per rung; consumers build the column names with `settings.headline_print_col()` and `settings.headline_mid_col()` | Every window an artifact carries a column for. A window outside the ladder has no column anywhere and cannot be scored without re-marking the tape, which only `ws1_horizon_persistence.py` does. |
| `COMPANION_HORIZON_S` | `settings.py` | every producer that writes a robustness column beside the headline one reads it off the module. The readers are not listed here because the list moves with every migration; what is held live is the complement, the sites still fixing a window of their own, which `checks/chk_settings_home_results.json` names with file and line under the group `horizon` | The long window kept beside the headline. It is never the headline. `gm_quoter.py` carries a constant named `J_HORIZON`, which is named for its own quantity and is not a scoring window. |
| `POLICY_HORIZONS`, `LABEL_ANCHOR_HORIZON` | `maker_econ.py`, built from the two declarations above | that file's decile and policy blocks | Which windows the policy blocks are reported on, and which label set stands in for the blocks that have no window of their own. |
| `HORIZON` | `maker_econ_b2.py`, bound to `settings.HEADLINE_HORIZON_S` | that file | The single window the B2 block ranks and measures on. Compare B2 only against the `maker_econ` B1 block at the matching window key. |
| `NS_PER_S` | typed as a literal in `build_quickwin_markouts.py`, `killswitch2_markout_join.py`, `ks2_markout_multiday.py` and `ks2_persistence_10day.py`; `panel_build.py` imports the first of those rather than retyping it | the four files that convert a window in seconds to the native nanosecond block clock | Nanoseconds per second. This is arithmetic, not a choice, so the four copies cannot disagree in a way that changes a number. Earlier revisions of this document called it six files and named `panel_rebuild_v2.py`, which mentions the name only in a comment about what it reuses. |

**The entry leg takes the last snapshot STRICTLY EARLIER than the fill, and this changed
on 2 August 2026.** Until then it took the last snapshot at-or-before, which accepts one
stamped with the fill's own millisecond. Such a snapshot already carries that fill's
impact, so the entry mid it supplies is contaminated by the very quantity a markout
measures. It was not a rare edge: 326,849 of the 2,480,267 collapsed taker trades,
13.18 per cent, took their entry mid from a same-instant snapshot, where a random join
would put 0.18 per cent. The notional-weighted ten-second harm read +0.52 basis points
on that stratum against +2.29 on the rest, so the published pooled figure was a mixture
of two populations and understated the harm; correcting it moved the figure from 2.0616
to 2.2388 basis points.

The horizon leg is unchanged: the first snapshot at-or-after the fill plus the window. So
the two legs are deliberately asymmetric — strictly before against at-or-after — and
`checks/chk_join_nolookahead.py` pins exactly that, on a fixture that discriminates the
two at equality.

The rule had four separate spellings in this tree and now has one behaviour: the copies in
`ws1_horizon_persistence.py`, `i3_book_comparator.py` and `probes/probe_G_horizon.py` were
changed with it, and the two checks that used to re-type it now call the producer instead.
That is the deeper repair. A guard that re-types the logic it guards is blind to the logic
changing; `ws1_horizon_persistence.py` proved it by failing its own reproduction gate the
moment one copy moved, which is the gate working, not breaking.

**The join tolerance is not a window, and the two have been confused.** `GAP_MAX_MS`
is the furthest a book snapshot may sit from the instant it is being used to price:
a fill whose entry snapshot or whose horizon snapshot is further away than that has
its mid markout blanked rather than measured against a stale price. It is a
*data-quality gate on the join* and it decides which rows survive; a scoring window is
a *measurement interval* and it decides what is measured on the rows that do. They are
different quantities with different units and different consequences, and neither is a
looser version of the other: widening the tolerance admits rows priced against a
staler book, widening the window measures a later price on the same rows. The two
values are close enough in seconds to invite the question, so it is answered here
rather than left to a reader.

The tolerance has **no home in `settings.py` yet**, and that is stated rather than
hidden. Counted by syntax tree rather than by text search — predicate: a module-level
assignment binding the name `GAP_MAX_MS` to a constant — it is typed in **seven**
files: `i4_midmarkout.py`, `i3_book_comparator.py`, `own_size_control.py`,
`temp_perm_decomp.py`, `ws1_horizon_persistence.py`, `probes/probe_G_horizon.py` and
`checks/chk_side_signconv.py`. All seven hold the same value today. Five of the six
followers name `i4_midmarkout.py` in a comment as the source they match, and
`temp_perm_decomp.py` carries a comment about what the gate buys without saying where
the number came from.

What a run used is recoverable from the artifact in six of the seven: five write the
value under the key `gap_max_ms` and `probes/probe_G_horizon.py` writes it inside a
sentence. **The seventh, `ws1_horizon_persistence.py`, records nothing about it at
all**, and that file is the one that chooses the scoring window, so the gate that
decides which rows enter its curve is not stated anywhere in the artifact the choice
rests on. The spelling is in no alias list of `checks/chk_settings_home.py`, which is
why no census this repository has produced has ever counted these seven sites.

**One window per block.** Wherever a result is labelled with a window, the
counterparties were *ranked* on the early-window markout at that window *and* the
late-window profit was *measured* at that window. No block ranks on one window and
measures on another. A mixed block credits itself with the gain of the shorter
measurement while charging only the notional the longer screen declines, which
overstates how efficient the screen is. Eligibility, meaning at least the required
number of early fills with a finite markout, is counted at the block's own window
too, so the eligible and toxic sets differ slightly between windows.
`build_toxicity_labels` in `maker_econ.py` takes the window as a keyword-only
argument so it cannot be confused with the fill floor.

## The lens: which price the harm is measured against

| Setting | Where declared | Where consumed | Meaning |
|---|---|---|---|
| `LENSES` | `settings.py` | reached through `settings.field_name()` rather than by reading the tuple, so nearly every producer consumes it without naming it: that accessor takes the lens as an argument and refuses one outside the tuple, which is what makes the indirection safe. `settings.headline_print_col()` and `settings.headline_mid_col()` carry the lens in the function name instead and take no lens argument at all, so they check the window against `LADDER_S` and not the lens. One file reads the tuple directly, `sensitivity_rollup.py`, which tests each column spelling it lifts against it so that a spelling which stops meaning what it says raises there | The two reference prices the project reports. The trade print is what the counterparty actually paid, so the maker's earned spread and the bid-ask bounce sit inside it. The book mid at the same instant removes both, so it isolates the price move. Neither is a correction of the other. |
| `HEADLINE_LENS` | `settings.py` | stamped into every fingerprint block, and read by one script, `sensitivity_rollup.py`, which turns it into the column spelling it lifts values under and repeats it in the `held_fixed` block of every group that pins a lens. No producer branches on it: a producer that writes both lenses writes both regardless | Which of the two leads in the text. The reasoning is in `settings.py`: on the headline window the two lenses give nearly the same answer, so the choice is not doing the work, and the mid leads because it answers the adverse-selection question without the maker's own spread inside the number. |
| the lens of one run | `--source {trade,mid}` | `ks2_persistence_10day.py`, `i3_nonrecoverability_oos.py` | The two files that compute both lenses take the choice on the command line and write it into the results file name and into the fingerprint. |

The lens is not recoverable from a column name in every file, which is why it
belongs in the stamped fingerprint rather than in a reader's inference from an
input filename.

## Data window and instruments

| Setting | Where declared | Meaning |
|---|---|---|
| `DAYS` | `build_quickwin_markouts.py` and `ks2_persistence_10day.py` hold the ten December trading days; `i3_book_comparator.py` and `i4_l2_mid.py` hold the same ten as `DEFAULT_DAYS`; `probes/probe_E_leadlag.py` holds them as calendar dates | The December pass. `ks2_markout_multiday.py` declares a three-day list under the same name, and that is a legitimate difference rather than a stale copy: the file measures day-pair persistence over consecutive days and needs three, not ten. The same file holds a second three-day list beside it, `FALLBACK_DAYS`, used when a requested day does not resolve, so its run can end on a day set that neither list states on its own; the file writes the resolved days into its own scope block, which is where the days a run actually used are to be read. `forward_toxicity.py` splits by calendar date because its window is a forward-recorded one and not this one. |
| the panel windows | `PERIOD_DAYS` in `panel_persistence.py`; `panel_rebuild_v2.py` binds the same object from there rather than restating it | Eight ten-day windows from 2025-08 to 2026-05, of which the December pass is one. `step1_inventory.py` repeats the first day of each window as plain data so the inventory never imports a builder and never triggers a fetch. |
| `COINS` | `build_quickwin_markouts.py`, `ks2_markout_multiday.py` and `ks2_persistence_10day.py` name the two December coins, all three by asking `settings.coin_labels("quickwin")` rather than by typing symbols, and `probes/probe_E_leadlag.py` does the same; `PANEL_COINS` in `panel_build.py` and `panel_persistence.py` names the wider panel set through `settings.coin_labels("panel")`, `panel_rebuild_v2.py` binds that object from `panel_persistence.py`, and `step1_inventory.py` and `probes/probe_D_pull.py` also use the name `COINS` for the wider set, likewise through the accessor. Three files still type a coin set of their own, and the guard counts them live under the group `coins`: `checks/chk_book_orientation.py` and `i4_l2_mid.py` as `DEFAULT_COINS` each type the list of symbols, and `checks/chk_rowcounts_determinism.py` types the code map itself, which is the more consequential of the two because a wrong map relabels a coin rather than dropping it. `forward_toxicity.py` types the wider triple too, and the guard excludes that file whole because it is on the allow list for a different reason, its calendar-date day split | Which perpetuals are in a pass. The name alone does not tell you how many coins are meant, which is the reason the code map below is asked for by artifact. |
| `COIN_FILTER` | `killswitch1_repeat_density.py` | Coins counted in the repeat-density scan. Set it to `None` to count all perpetuals; the file says why the deep markets are the default. |
| the early-and-late split | `settings.split_early_late(days_present)` | Which days rank a wallet and which days measure it. **This cannot be a constant.** A day-of-month tuple is right only for a window that begins on the fourth, and one panel window begins on the sixth, so a fixed tuple gives that window a three-day early half against a seven-day late half or discards two of its ten days outright. The function takes the first half of the days actually present, so on a ten-day window beginning on the fourth it returns exactly the old split and moves no December number. Migrated files keep `EARLY_DAYS` and `LATE_DAYS` as `None` overrides that fall through to the function. Day-of-month literals remain in two places: `i3_nonrecoverability_oos.py` as the two tuples, and through it `i3_book_comparator.py`, which reads that file's tuples; and `follow_the_informed_oos.py` as a single split day. An earlier revision of this row named `m2_figure.py` as a third site, and that is no longer so: the figure calls the function over the days its input carries and says at the declaration that day-of-month bounds are never typed there. The live count is the group `split` in `checks/chk_settings_home_results.json`, which pairs `EARLY_DAYS` with `LATE_DAYS` and so counts a file with both twice. `forward_toxicity.py` splits on calendar dates and is a legitimate difference, not debt, because its window is a different one; the guard carries it on its exclusion list with that reason. `panel_analyze.py` is the opposite case and worth reading before you touch it: it computes the split with the function and then assigns it into the module global of `t3_capacity.py`, because that file's own helper declares day parameters and then ignores them in favour of its globals, so passing them at the call site would be discarded without a word. |

### The four trade files, and the one trap in using them

Four `.npz` files hold trades. **A row of any of them is one collapsed taker trade and
not one fill**, the legs of a sweep merged at a size-weighted entry price by
`build_quickwin_markouts.py`; the README section "The data" gives the
merge and the producer that states it. Two of them carry information the others do not;
two are earlier stages that were kept. Knowing which is which prevents both a redundant
re-run and a wrong join. Three of the four row counts below are enforced rather than
merely recorded: `checks/chk_rowcounts_determinism.py` asserts the two December counts
on load, records the panel total and asserts the analysed subset of it, and writes
`checks/chk_rowcounts_determinism_results.json`. The second panel build is not in that
check's scope; its count is an expectation declared in `step1_inventory.py`, which a
reader's own pull is compared against cell by cell.

| File | Rows, one per collapsed taker trade | Scope | Carries |
|------|------|-------|---------|
| `panel_markouts.npz` | 26,035,902 | 3 coins x 8 windows | every trade, trade-print markout at every rung of the ladder |
| `panel_markouts_v2.npz` | 26,021,882 | same | the same plus `block_time_ns` and `is_liq` |
| `quickwin_markouts.npz` | 2,480,267 | Dec 2025, BTC+ETH | a subset of the panel, same columns |
| `quickwin_markouts_mid.npz` | 2,480,267 | Dec 2025, BTC+ETH | the book-mid markout and the order-book features |

`quickwin_markouts.npz` is contained in `panel_markouts.npz`: the December two-coin
slice of the panel is the same rows with the same columns plus `period`. It is kept
because `quickwin_markouts_mid.npz` is row-aligned to it, which that same check
verifies element by element, and because every consumer script reads it by name.

`panel_markouts_v2.npz` is 14,020 rows short of `panel_markouts.npz`, and those rows
are one hour of trading, 21:00 to 22:00 UTC on 2025-11-10, that the v2 pull did not
retrieve. The v2 build accepts a day once enough of its hourly objects land, so that
day passed without a retry. Every other row agrees with the v1 build field for field,
and no row exists in v2 that is absent from v1. The gap has one second-order effect
worth knowing: the markout join takes the first print at or after the window, so a
few hundred trades in the last minute before the gap carry a long-window markout
measured against the first price after it, a mean absolute shift of single-digit
basis points on those rows. Take the two extra columns from this file, and take the
2025-11 row counts and markouts from `panel_markouts.npz`. These figures were
measured by loading the two files and differencing them; no committed artifact
carries them, which is a gap this document states rather than hides.

**The trap: wallet numbering is not shared, and the disagreement is near total.**
Each file was coded with its own first-seen integer map, `quickwin_taker_map.json`,
`panel_taker_map.json` and `panel_taker_map_v2.json`. Every address in the quickwin
map also appears in the panel map, and **not one of them holds the same integer in
both**. The two panel maps, built from the same data days apart, agree on barely a
third of the addresses they share. So joining any two of these files on `taker_id`
pairs unrelated counterparties for most rows and fails silently, because the integers
are valid in both files and nothing raises. The maps are regenerated rather than
committed, so these counts too were measured by loading them.

No script in this repository performs such a join, and the figures above are the
price of a detour that was not taken. Scripts that read two files at once align them
by row position and then verify the alignment by byte equality on stable columns.
Where counterparty identity has to be carried across files, the route already exists
and does not go through these integers: the `panel_ckpt` and `panel_ckpt_v2` shards
keep the raw taker and maker address strings, and identity is resolved by address
there.

Were such a join ever needed, the key would have to be wider than it first looks.
Coin, day, side, notional and entry price leaves about a third of the quickwin rows
in groups of two or more. Adding the signed pre-trade position brings that near one
percent, and adding realized profit near eight parts in a thousand. Not all of that
residue is harmful, because many of the surviving groups belong entirely to one
taker, where a join cannot pick the wrong wallet. December is also the mildest of the
eight windows; over the whole panel the same key leaves several times that share of
rows ambiguous.

Joining on `block_time_ns` does not remove the ambiguity, and an earlier version of
this file said that it did. A block carries several fills, on average nearly two and
in one case a few thousand, so most rows sit in a block that holds more than one
fill. The field also lives only in `panel_markouts_v2.npz` and the `panel_ckpt_v2`
shards, which is to say it is absent from exactly the pair of files whose code maps
disagree.

## Wallet eligibility

Three different quantities, not one setting with three names. They gate three
different populations, and the tree still spells them `K_LIST`, `K_VALUES`, `KMIN`,
`K_HEADLINE`, `K_POOL`, `K_HALF_MIN`, `K`, `KS`, `K_MIN` and `MIN_FILLS`.

The last four of those ten spellings were watched by nothing until 2026-07-31. The gate
`checks/chk_settings_home.py` counts by an alias list, and `K`, `KS`, `K_MIN` and
`MIN_FILLS` were in no list, so five fill floors in four files —
`probes/persistence_crosswindow.py`, `ws2_hard_classifier.py`, `ws3_taker_pnl.py` and
`m2_figure.py` — had never appeared in any census this repository produced. They read
`settings.py` now and the alias list carries their spellings, which is why the gate's
count did not rise when it learnt to see them.

**What these floors cost is measured and not estimated, since 2026-08-05.** A floor here
is applied twice — once to the window a wallet is ranked on and once to the disjoint
window it is measured on — so the population that survives is selected on an outcome
that follows the ranking in time. `survivorship_census.py` re-implements the five
admission expressions that do this, at the same unit, floor, lens and window as their
owners, and recounts each under two counterfactual rules: the floor on the ranking half
alone, and the floor on the ranking half with a single fill demanded of the later one.
It declares no setting of its own and types no floor: each site's floor is read from the
same declaration its owner reads, which is what lets the census follow a floor when the
floor moves. What it adds is the price. At the four sites whose floor exceeds one fill,
between 53.97 and 56.87 percent of the wallets eligible on the ranking half survive to
be counted, and between 53.3 and 68.2 percent of what is removed is removed by the
threshold rather than by the data — those wallets did come back, just fewer times than
the floor. The published separation of the head figure barely moves under this: across
all three rules it spans 0.021 basis points on the trade-print reference and 0.017 on
the book mid. The out-of-sample realized-profit comparison of `ws3_taker_pnl.py` does
move, and changes sign. Every one of those figures is a leaf of
`survivorship_census_results.json` and not a number kept here.

The pair `(10, 50)` beside the pair `(50, 100)` is **two quantities and not one setting
at two values**, and a census that sorts by value rather than by role reports it as a
disagreement that does not exist. `(50, 100)` is `PERSISTENCE_FLOOR_FILLS`, a floor on
each half of a split window. `(10, 50)` is the `sweep` role of the ranking-window floor,
which three files report a curve over. Different populations, different questions.

| Setting | Where declared | Where consumed | Meaning |
|---|---|---|---|
| `RANK_FLOOR_FILLS` | `settings.py` | three files gate on it directly: `t1_toxicity_skew_backtest.py`, `t3_capacity.py` and `probes/decay_curve.py` read it as their minimum trade count per wallet. **Four more adopted it on 2026-07-31** through the `headline` role of `WALLET_FILL_FLOOR_BY_PURPOSE` — `maker_econ.py`, `maker_econ_b2.py`, `mm_bakeoff.py` and `ws3_taker_pnl.py` — and until that day all four pointed their prose at a 10-fill rung instead. The count of four is by ROLE and not by value, which is what an earlier count of three missed: the first three also declare a sweep and `ws3_taker_pnl.py` does not, so a census that walked the sweep files found one fewer. Two files still run on a different rung and read the declared value only to state the difference: `forward_toxicity.py` and `i2_walletfe.py`; `own_size_control.py` reads it in the same way. `ws1_horizon_persistence.py` holds a fifth site under the spelling `K_PRIMARY`, watched by no alias list, and it stays at 10 on purpose — the reliability curve measured there is the EVIDENCE for the declaration, so raising it would remove the measurement that justifies the value. `sensitivity_rollup.py` is a third kind and runs on no rung at all: it reads the declaration to build the label under which the headline rung is looked up in the artifacts it lifts from, so that the label moves when the declaration moves. The sites still typing a floor of their own are counted live under the group `wallet_floor` in `checks/chk_settings_home_results.json` | Minimum fills in the ranking window for a wallet's score to be a measurement of that wallet rather than of noise. Decided by the measured split-half reliability rather than by taste, and the multipliers are read off the artifacts: at the loosest rung `ws1_horizon_results.json` gives reliabilities 0.333 and 0.386, a disattenuation multiplier of 2.7891, so 64 percent of the corrected number is the correction; at the declared floor and above, the four cells of `ks2_persistence_10day_results.json` give 1.1514, 1.2285, 1.4267 and 1.5626. The floor sets the POPULATION and not a caption: on the December window ten early fills leave 9,654 eligible takers and a 966-wallet toxic decile, fifty leave 2,069 and 207. |
| `RANK_FLOOR_SENSITIVITY` | `settings.py` | **no file reads the tuple.** Five name it: `follow_the_informed_oos.py`, `ws1_horizon_persistence.py`, `ws2_hard_classifier.py`, `ws3_taker_pnl.py` and `sensitivity_rollup.py`, each in a comment and in the sentence it writes into its own results file. Of the four that run at the loosest rung, two typed that rung as their own literal until 2026-07-31 and now read it from `WALLET_FILL_FLOOR_BY_PURPOSE`; the tuple itself still hands nothing out | The rungs reported as a sensitivity. The loosest rung is reported and never a headline. The four files that run at it each say so in their own results file. That the ladder is stated and not handed out is the state to fix here: the tuple is a declaration nothing yet depends on, so a change to it would move no number. What did change is the other half of that defect — `ws2_hard_classifier.py` and `ws3_taker_pnl.py` no longer hold their rung as a second home, so the rung and the ladder now disagree in one place instead of three. |
| `PERSISTENCE_FLOOR_FILLS` | `settings.py` | read from the module, most of them under the name `K_LIST` or `K_POOL`, by `i3_depth_control.py`, `i3_nonrecoverability_oos.py`, `ks2_persistence_10day.py`, `own_size_control.py`, `panel_common_idio.py`, `panel_persistence.py` and `temp_perm_decomp.py`, and by `sensitivity_rollup.py`, which reads it to name the rung a lifted value belongs to; `panel_analyze.py` and `i3_book_comparator.py` both take it second-hand as `i3.K_LIST` from `i3_nonrecoverability_oos.py` | Minimum fills in **each** half. A wallet needs the count twice, so the same total buys half the precision per half; this is a different quantity from the rank floor, not a stricter setting of it. The lower rung is the reported cell and the higher one is the check that the cell is not a small-sample artifact. Every one of those files is on the same value, so adopting the declaration moved no number. |
| `DAY_FLOOR_FILLS` | `settings.py` | exactly two files, `ks2_markout_multiday.py` as `FILL_THRESHOLD_K` and `ks2_persistence_10day.py` as `K_DAY` | Minimum fills within one day, for the day-over-day reads. **The direction is argued and the value is not**, and `settings.py` records that. A day is a fifth of a half, which puts this floor below the persistence floor and says nothing about where below: a fifth of the persistence floor would not give this number. No artifact and no source stands behind it. What a different value would move is visible in the two artifacts. In `ks2_persistence_10day_results.json` the floor decides which counterparties enter the per-day heterogeneity ratio and the adjacent-day block: at the declared value the twenty coin-day slices pass between 155 and 630 counterparties out of totals between 4,026 and 12,746, a passing share between 2.7 and 8.4 percent, and the eighteen adjacent-day pairs carry between 83 and 343. In `ks2_multiday_results.json` it decides eligibility for the three-day run, whose six pair correlations carry p-values. Lowering it widens the population with wallets whose daily mean is measured on fewer fills; raising it narrows the population. The adjacent-day block states that it is descriptive and carries no p-value; the three-day pairs do carry p-values, so those are what a change would move. **No sweep exists.** `sensitivity_rollup_results.json` records this setting with `has_sweep` false and no candidate set declared, and states that the missing basis and the missing candidate set are two open gaps rather than one. |
| `MIN_COMMON_WALLETS` | `settings.py` | `panel_persistence.py` reads it as `MIN_N_COUNTERPARTIES`, its minimum counterparty count, and no other file | Below this a rank correlation is reported with a flag. The cell is still computed and is marked, never dropped without saying so. **No basis is on record**: thirty is the familiar small-sample rule of thumb, but no source is cited for it here and no measurement in this work chose it. What a different value would move can be read off the shipped artifact without recomputing anything, and the answer is nothing over a wide range: of the forty-eight records in `panel_persistence_results.json` that carry a counterparty count, the smallest carries thirty-six, so at the declared value not one cell is flagged, and any value up to thirty-six leaves every reported number and every flag exactly as they are. The setting only begins to act above thirty-six: two of the forty-eight cells sit below fifty and six below one hundred. **No sweep exists**, and `sensitivity_rollup_results.json` says so, though its stated reason is stale in the same way the migration map is: it repeats that nothing reads the declaration. The migration map in `settings.py` still calls this one undeclared elsewhere; that comment is stale, and the consumer named here is real. |
| `K_LIST` | one name over two different eligibility rules | most of its sites read `settings.PERSISTENCE_FLOOR_FILLS`; in `maker_econ.py`, `maker_econ_b2.py` and `mm_bakeoff.py` the name holds the `sweep` role of the ranking-window floor, a pair whose lower rung is the loosest one | The sweep is deliberately unchanged by the adoption of 2026-07-31, because the curve over both rungs is what those files report. What moved is the `headline` role beside it: the three no longer lead on the loosest rung. `RANK_FLOOR_FILLS` still carries the state "target" rather than "in force", and the reason CHANGED on 2026-08-01 when the recompute landed: it is no longer that the artifacts are owed a run. A census over the 81 tracked results files, predicate "the key stands in `_meta.settings_fingerprint`", puts ten artifacts at the declared fifty and leaves four recording ten (`follow_the_informed_oos`, `m11`, `m8_makerside`, `ws2_hard_classifier`), two at twenty-five, two at thirty, one at one, and six carrying a grid. Those are other consumers reading the floor for their own question, not stragglers, so the word stays "target" until each has been read and either adopted or declared an exception. |
| `REPEAT_FILL_FLOOR`, `RICH_VOLUME_SHARE`, `MIN_RECURRING_WALLETS` | `killswitch1_repeat_density.py` | that file only | The three thresholds of the repeat-density scan: how many fills make a wallet recurring, what share of notional the recurring wallets must hold, and how many of them there must be for the verdict to stand. They gate a screening scan, not a reported estimate, and they have no consumer elsewhere. |

## Statistics, resampling and randomness

| Setting | Where declared | Where consumed | Meaning |
|---|---|---|---|
| `N_PERM` | `settings.py`, where it is **computed and not typed** | every file that draws a label permutation reads the budget from the module, most binding it as `N_PERM` and some under a name of their own such as `N_PERM_CORR` or `N_PLACEBO`; the shared `stats.py` reads it as well, to check a budget against the declaration. A file that draws fewer reads the declared value too, so that its fingerprint can state the shortfall against it. What is still typed as a literal is the row below, counted live under the group `permutations` in `checks/chk_settings_home_results.json` | Label-permutation draws. The budget sets the p-value floor at one over one more than the budget, so it decides what a claim is able to assert rather than how precisely it is asserted. This one is arithmetically obliged rather than chosen: the floor has to clear the Benjamini-Hochberg threshold at the smallest rank of the largest family, so the budget follows from the level and the family size, and `settings.py` derives it from those two instead of stating a number. |
| | migration debt, and what is left of it | The six scripts this row used to name as running an order of magnitude below the budget no longer do: `i2_walletfe.py`, `own_size_control.py`, `panel_common_idio.py`, `ws1_horizon_persistence.py`, `ws2_hard_classifier.py` and `ws3_taker_pnl.py` each now bind `N_PERM` from the module, and their artifacts were recomputed at the declared budget without a single verdict moving. The literal this row used to name in `probes/probe_F_hlp_liq.py` is gone too, and so are the ones in `follow_the_informed_oos.py`, `i3_depth_control.py` and `i3_nonrecoverability_oos.py`; all four now bind the declared budget and only name it in a comment. What remains is two artifacts whose scripts already read the declaration but whose stored numbers predate it, `panel_analyze_results.json` and `i3_book_nonrecoverability_results.json`, and six typed budgets. Five of them are for a null that is not the file's main permutation: `ks2_markout_multiday.py` and `ks2_persistence_10day.py` for the per-day variance ratio, `forward_toxicity.py` under the name `NPERM` for its forward window, `probes/probe_E_leadlag.py` as `N_PLACEBO` for the randomized-lag draw, and `t1_toxicity_skew_backtest.py` as `N_SIZE_PLACEBO` for the size-matched one. The sixth is of a different kind and was missing from an earlier revision of this row: `probes/probe_G_horizon.py` types a budget equal to the declared one, so it is a second copy of the number rather than a shortfall against it, which is the failure a second home produces even when the two agree today. Do not count this list by hand a second time: the guard writes it live under the group `permutations`, and its own count is lower than the six here because **two** files on its allow list are excluded whole, `forward_toxicity.py` and `probes/probe_G_horizon.py` | Raising a budget changes the p-values a file can express, so it is a measured change and not a rename, and that is why the declaration carries the state "target". A second budget in the same file is not automatically debt: in both `ks2` files the second null produces a variance ratio rather than a p-value, and a ratio has no threshold to clear, so its budget buys precision in a denominator rather than resolution in a floor. |
| `N_BOOT` | `settings.py` | **every consumer draws it since 2026-07-31.** `confound_asymmetry.py` binds the declared budget as its own and the shared `stats.py` takes it as the default of its resampler; the other six read it through `BOOT_DRAWS_BY_PURPOSE`, whose entries are now the declaration itself rather than a shortfall against it — `maker_econ.py`, `mm_bakeoff.py`, `t3_capacity.py`, `ws1_horizon_persistence.py`, `ws3_taker_pnl.py` and `m11_concentration.py`. `maker_econ_b2.py` is not on either list and says so in its own fingerprint: it draws no bootstrap, its nulls are label permutations. Two earlier revisions of this row were wrong in opposite directions: the first named `confound_asymmetry.py` as the only reader, which was true before the consolidation, and the second added `ws1_horizon_persistence.py` and `ws3_taker_pnl.py`, which at the time did not read it at all and named it in a comment beside a budget of their own | Bootstrap resamples. The budget decides how many draws land in each tail of a ninety-five percent percentile interval, one fortieth of the budget, and therefore how far an endpoint moves between seeds. |
| | migration debt, and what closing it costs | Six files ran below the declared budget until 2026-07-31: `ws1_horizon_persistence.py` and `ws3_taker_pnl.py` at a quarter, `maker_econ.py` and `t3_capacity.py` at a half, `m11_concentration.py` at two fifths and `mm_bakeoff.py` at less than a sixth. All six are entries of `BOOT_DRAWS_BY_PURPOSE` and every entry now holds `N_BOOT`, so the debt is closed in the declaration and the six artifacts are owed their run. Two of the six had no home a census could reach. `mm_bakeoff.py` kept its 300 as the default argument of `os.environ.get("CAP_N_BOOT", "300")` — a budget whose only home was a string inside a call — and that environment read is now removed, so nothing outside the repository can overrule the declaration. `m11_concentration.py` kept the literal 800 under the spelling `BOOTSTRAP_DRAWS`, which is in no alias list of `checks/chk_settings_home.py` even now, which is why the sentence "outside `settings.py` the tree holds no bootstrap-budget literal at all" stood in this row and was a census taken with a predicate that could not see the site. `t3_capacity.py` was the same class of miss under `BOOTSTRAP_N`, found one day earlier, and that spelling did enter the alias list | The gap was against `draws_per_tail` and not against the budget: fifty draws per tail declared against 25, 25, 20, 12.5, 12.5 and 7.5 run. Closing it moves interval endpoints and no point estimate, and it moves them by the noise of a larger draw rather than in a direction. **One consumer is an exception worth naming**: `ws1_horizon_persistence.py` takes the standard deviation of the same draws as `boot_se`, and `boot_se` is the width of the parsimony tie-break in its horizon selection, so there the budget reaches a discrete list and not only a band. On the grid as it stands the selected horizon cannot move — the maximum sits at the shortest rung and the rule takes the minimum of the list — but the mechanism belongs in the record. |
| `PERM_FLOOR_MARGIN` | `settings.py` | no script reads it. It is one of the three inputs `settings.min_perm_draws()` uses to derive `N_PERM`, and a file that reports a floor reads the derived budget rather than the margin. Six files name it without reading it: `follow_the_informed_oos.py`, `i3_depth_control.py`, `i3_nonrecoverability_oos.py`, `m4_realizedpnl.py` and `probes/probe_F_hlp_liq.py` in a comment saying why their budget is derived and not typed, and `sensitivity_rollup.py` in the coverage row it writes for the setting. A comment is not a read, and it is worth stating because a text search for the name returns all six | How much room the permutation floor must keep above the correction threshold. The inequality that fixes the budget is arithmetic and cannot be argued with; this factor is the one part of it that is a judgement, and it is separated out precisely so that the arguable part is visible and the unarguable part is not mistaken for a choice. Without it a budget that clears the threshold by four percent would count as passing, and every p-value resting on the floor would have its verdict decided by the last digit of the correction. |
| `COIN_CODES_BY_ARTIFACT` | `settings.py`, consumed through `settings.coin_labels()` and `settings.coin_codes()`, and through nothing else: no file reads the map itself | most producers in the tree; the accessor requires the artifact name, so the call site says which map it means | The integer code each perpetual carries inside an intermediate. **The map is a property of the file, not of the project**, which is why the accessor refuses to answer without being told which artifact is meant: the quickwin intermediates code two coins and the panel intermediates code three, and the same integer therefore names different perpetuals in different files. A single project-wide map would silently relabel every panel number that passed through it. |
| `FIELD_SUFFIX_STYLE` | `settings.py` | `panel_analyze.py`, `panel_common_idio.py`, `panel_persistence.py` and `temp_perm_decomp.py` read it and stamp it into their own fingerprint block, so an artifact states which convention its keys were built under. `t3_capacity.py` names the declaration in the message it writes beside its renamed keys and does not read the value | One naming rule for the window a field belongs to. Two opposite conventions were in force at once, and under them a single key `cost_bps` meant one window in one file and a different window in another, so two artifacts could be compared field by field and silently disagree about what was being compared. The declaration carries the state "target" because the sites are not all converted yet. One case turned out not to be a missing suffix at all and is worth stating, because it is the harder version of the same defect: `follow_the_informed_oos.py` wrote six keys named `cost_bps`, but its quantity is the round-trip trading cost the backtest **assumes**, a constant 5.5 in every cell, while `t3_capacity.py` and `panel_analyze.py` write `cost_bps` as an adverse-selection cost **measured** per notional that varies cell by cell. Adding a window suffix would have made an assumption and a measurement look like the same quantity at two horizons. It is now `assumed_round_trip_cost_bps`, and the value did not move. |
| `FDR_ALPHA` | `settings.py` | read from the module by `i2_walletfe.py`, `i3_nonrecoverability_oos.py`, `ks2_persistence_10day.py`, `own_size_control.py`, `panel_build.py`, `panel_common_idio.py` and `panel_persistence.py`, and by the shared `stats.py`; `panel_analyze.py` and `i3_book_comparator.py` both take it second-hand from `i3_nonrecoverability_oos.py` | Benjamini-Hochberg level for every family of cells. No second value exists in the tree, so this one was never a measured change. The level is also one of the two inputs the permutation budget is derived from, which is why raising the level would silently raise the budget too. |
| `N_FOLDS` | `i3_nonrecoverability_oos.py`; `panel_analyze.py` and `i3_book_comparator.py` both import it from there | those three | The k-fold wallet split for out-of-sample scoring. It has no second value anywhere. It is declared in a producer rather than in `settings.py`, which is why its consumers reach it by importing that producer, and which is the reason the two second-hand readers are named here: a reader looking only at `settings.py` would not find the quantity at all. |
| `MASTER_SEED` | `settings.py` | Predicate for a file that draws: its syntax tree holds a call to `default_rng`, to `RandomState`, to the legacy `numpy.random.seed`, or to `rng()` in its bare or attribute form; calibrated on live files, `gm_quoter.py` must fire and `checks/chk_no_abs_paths.py` must stay silent. Three further routes return zero with their zero calibrated: the stdlib `random` module, a pandas `.sample` call, and any `np.random.<f>` other than `seed`, `default_rng` and `RandomState`. That last zero matters: nothing here draws from the numpy **global** state, so the `np.random.seed(...)` calls in the tree seed a stream no line reads. Four files that match the predicate draw no number that can reach a results file, `build_quickwin_markouts.py`, `check_first.py`, `i4_l2_mid.py` and `m8_makerside.py`, and `i4_midmarkout.py` draws only inside `_selftest`. The rest are filed by the weakest rule each uses: the declared rule (this module, `stats.py` through it, and the three `ws` consumers, which reach it as `H.rng(...)`); the joined-and-hashed form in `panel_persistence.py`, whose two base seeds are read from `settings.py` and whose rule alone is local; the base seed alone; the base seed plus arithmetic over the loop coordinates; child seeds drawn from a parent generator, in `i2_walletfe.py` and `panel_common_idio.py`; and an integer built from the data label, for the per-day variance ratio of the two `ks2` files. The seeds still typed as literals are counted live under the group `seed` in `checks/chk_settings_home_results.json`. That guard does not see all of them, because its alias list holds neither `SEED_CORR_NULL` nor `CAP_BOOK_SEED` and `probes/probe_G_horizon.py` is exempted whole by file | The one seed. Its value is arbitrary; what matters is that there is one, because then a p-value that differs between two scripts differs for a reason a reader can inspect. `settings.rng(*cell)` derives a generator from the seed together with the identity of the cell, so that a result does not depend on the order cells are computed in and two cells do not silently draw the same stream. That accessor now has callers: `ws1_horizon_persistence.py`, `ws2_hard_classifier.py` and `ws3_taker_pnl.py` draw through it, so in those three the order property holds and two cells cannot silently share a stream. `stats.py` calls it too, and differently: its own `rng` is a pass-through that hands the cell identity over unchanged, so a file routed through the shared module inherits the same property without naming the seed itself. The files that bind the seed build their own generators from it, so the property is in force in part of the tree and not yet in the rest. The accessor refuses a cell identity made entirely of integers, because a string cell name decomposes into character codes that would collide with the tuple of those same numbers; refusing the ambiguous form leaves every existing stream byte-identical, whereas changing how the seed is derived would have moved every permutation and bootstrap value in the tree to close a collision that never once occurred. |
| | migration debt | Predicate: module-level assignments whose name contains `SEED` and whose value is an integer literal, over all tracked `.py` outside `settings.py`. One such site is a seed a consumer draws, `SEED` 20260622 in `probes/probe_G_horizon.py`. Two more are `SEED_CORR_NULL` 424242 in the two `ks2` files and one is `CAP_BOOK_SEED` in `i3_book_comparator.py`; the others, `N_SPLIT_SEEDS` in two files, `SEED_SWEEP_N` and `SEED_SWEEP_STREAMS`, count seeds or streams rather than being one. The predicate finds no other site; a seed typed inside a function is outside its reach, and the live guard named in the row above is the count to trust | This is why the declaration is a target rather than settled. `SEED_BY_PURPOSE` holds one seed per purpose, several purposes share a value, and `MASTER_SEED` is not one of them. Each consumer records its own seed as a fingerprint override, so the difference is visible in the results file instead of being indistinguishable from a drift. |
| `RELIABILITY_SEED` | `settings.py` | three files read it, `ks2_persistence_10day.py`, `panel_common_idio.py` and `panel_persistence.py`, all three under the name `RNG_RELIABILITY`. An earlier revision named `ws1_horizon_persistence.py` as a fourth reader; that file names the declaration inside the sentence it writes into its own results file, to say which estimator its own seed does not belong to, and does not read the value | The split-half reliability seed, separate on purpose: it seeds a different estimator, the within-wallet odd-and-even split, and those three files already agree on it, so their reliability tables are comparable cell for cell. |
| `RELIABILITY_SEED_SPREAD_SD` | `settings.py`, and flagged there as having no basis | stated in the paper beside the persistence, and read by no file at all | **Nothing in this repository produces this number, and the declaration says so.** Where it came from is on record in words: fifty seeds were swept through the reliability estimator, and the figure is the standard deviation of what the headline book-mid persistence did across them on the December window at the declared persistence floor. What is not on record is the sweep. No script here performs it and no artifact records it, so a reader who clones this repository cannot reach the number. The cell the spread is taken around is reachable and checkable, in `ks2_persistence_mid_results.json` under `persistence_pooled`; the spread is not. An earlier revision of this row presented it as measured, which is the one claim a configuration document must never make about a number it cannot point at. What a different value would move is nothing computed: no file reads the declaration, so the figure carries a sentence of the paper and no cell of any table. There is no sweep to point at either, and `sensitivity_rollup_results.json` states the reason exactly: this is not a setting but a measurement of one, and it is the result the `RELIABILITY_SEED` sweep would have written if that sweep were a script. Until it is one, treat the value as an assertion recorded in words, not as a result of this code. |

Do not change a seed when reproducing published numbers. A seed derived from `hash()`
of a string is not reproducible at all, because Python salts string hashing per
process unless `PYTHONHASHSEED` is set.

**One derivation rule, decided 2026-08-02.** What a reader has to be able to check is not
the seed but the stream, because two generators opened on the same integer emit the same
uniforms in the same order, and then a difference between two results is not a difference
between their statistics. So this project declares ONE rule for turning a declared seed
into a stream, and the rule takes two parameters rather than none: which declared seed the
stream belongs to, and which cell is being computed.

    stream = SHA-256("<base seed>|<component>|<component>|...") folded to 64 bits

The rule is already written in the tree, at `panel_persistence.cell_rng`, and
`settings.rng(*cell)` is the same rule with the base fixed to `MASTER_SEED` and the
components flattened to character codes rather than joined. The joined form is the
declared one for two reasons that were measured rather than preferred. It separates
`("ws1", "placebo")` from `("ws1", "plac", "ebo")`, which the flattening cannot and which
`settings._refuse_ambiguous_cell` records as an open defect whose repair is exactly this
boundary marking. And it takes the base as an argument, so one rule covers `MASTER_SEED`,
`RELIABILITY_SEED` and every entry of `SEED_BY_PURPOSE`, where the flattened form fixes
the base at `MASTER_SEED` and so cannot express the other two at all.

Three shapes present in the tree are **not** roles of the rule and are being retired: a
base seed plus arithmetic on the loop coordinates, which collides -- under
`RNG_SEED + K + h` the cell at 50 fills and 60 seconds takes the same integer as the cell
at 100 fills and 10 seconds; child seeds drawn from a parent generator, which depends on
loop order and which hands `i2_walletfe.py` and `panel_common_idio.py` the identical five
split seeds; and a stream seeded from the data label alone, which no sweep over the
declared seed can reach. The one shape that does look like a second rule and is not is a
**sweep over seeds**, where the spread across seeds is the finding: that is the base
parameter taking many values, and `RELIABILITY_SEED_SPREAD_SD` and the forty fold seeds of
`SEED_SWEEP_SEEDS` in `i3_book_comparator.py` are the two cases of it.

Adoption is a measured change and not a rename: it redraws every permutation and bootstrap
value in the file that moves, so each moved node owes a recompute and a leaf-by-leaf
comparison against the artifact it had before.

## Whale-drop robustness

| Setting | Where declared | Where consumed | Meaning |
|---|---|---|---|
| `WHALE_DROP_K` | `settings.py` | every file that runs the whale-drop robustness reads it from the module, several of them binding it under the name `N_DROP_WHALES`; `panel_analyze.py` takes it from `i3_nonrecoverability_oos.py`, and `i3_book_comparator.py` takes it from there too. A site still typing a count of its own would be counted under the group `whale_drop` in `checks/chk_settings_home_results.json`, where today there are none | How many of the largest counterparties are dropped to answer the question "is this a handful of wallets?". One probe deliberately drops fewer and says so at the declaration. |
| `WHALE_DROP_LADDER` | `settings.py` | `t3_capacity.py` | The answer is not binary and the ladder is the finding: `t3_results.json` reports the avoidable share falling as the drop deepens. |
| `WHALE_DROP_CRITERIA` and `settings.whale_drop()` | `settings.py` | `i2_walletfe.py`, `i5_exclusion.py`, `m11_concentration.py`, `m4_realizedpnl.py`, `m9_crossasset.py`, `panel_common_idio.py`, `t1_toxicity_skew_backtest.py`, `t3_capacity.py` and `temp_perm_decomp.py` build their key through the accessor | **The criterion is the setting, not the count.** Dropping the largest by notional answers "is this a volume artifact"; dropping by cost answers "is this a handful of wallets". Different questions, different answers, and one key name used to cover both. The accessor makes the criterion required and builds the key from it, so no artifact can say "top ten" without saying top ten by what. |

## What the word "toxic" is allowed to mean, and what the other cuts are called instead

A census on 2026-08-01 read every place in this repository that turns a per-counterparty
quantity into two classes. Fourteen such places existed and they ran eleven different
rules; only one of the fourteen matched the study's declared selection on all of lens,
horizon, statistic, cut rule and fill floor. The rest were not drift: they answer
different questions and select different objects, and each of them was called toxicity.
A word that names five objects names none of them, so four of the five were given names
of their own. Nothing about any computation changed with the names; the proof is filed in
`checks/NEUTRAL_EDITS.json`, entry by entry, and every affected artifact is reported by
`checks/chk_artifact_provenance.py` under `neutral_by_certificate` rather than as fresh.

| What the object is | What it is called now | Where | How it differs from the declared selection |
|---|---|---|---|
| The declared selection | toxicity, and this alone | `maker_econ.py`, `build_toxicity_labels` | it is the declaration |
| Counterparties ordered by trade-print markout | `_rank_print_markout`, `_print_markout_top_mask` | `t1_toxicity_skew_backtest.py` | two axes: the column read is the trade print where the declaration is the book mid, and the cut is sized `max(1, floor(0.10 N))` where the declaration is `ceil(0.10 N)`. On 2 069 ranked counterparties that is 206 against 207 |
| Counterparties ordered by summed dollar cost | `DOLLAR_COST_TOP_FRAC`, `_top_by_dollar_cost_mask` | `t3_capacity.py` | the quantity ordered is a total in dollars, not a rate in basis points, so it answers who is dearest in aggregate rather than who is dearest per fill; the two tails overlap and are not the same set |
| Counterparties whose net per-dollar markout is adverse | `_adverse_net_concentration`, `_bootstrap_adverse_net_ci` | `m11_concentration.py` | an absolute rule at zero over the whole window at a floor of ten fills, so it names a population of about half of all counterparties and not a tail of a tenth |
| Fills bucketed by trade size | `N_NOTIONAL_DECILES`, `notional_decile_index` | `m7_size.py` | the unit is a fill and not a counterparty, and the quantity cut on is notional; it makes no statement about adverse selection at all |
| The most active counterparties, removed as a robustness check | `_most_active_drop_robustness` | `i5_exclusion.py` | ordered by row count, so markout plays no part in choosing the set; it is not a selection and is not built from one |

Two spellings are left as declared debt because correcting them is not free. The keys
these files write still carry the old word — `n_toxic_wallets` and
`target_toxic_notional_usd` in `t1_backtest_results.json`, and `net_toxic_gini`,
`n_net_toxic_wallets`, `toxic_top_1pct_share` and `frac_wallets_toxic` in
`m11_results.json`. A key is what an artifact says rather than what a script is called,
so changing one is a change to the artifact and is owed a run rather than a certificate.
The dollar-cost block of `m11_concentration.py` needed no rename: its own artifact
already labels it "DOLLAR COST concentration (NOT toxicity) -- driven by trade size".

## Coin code maps

The code map is a property of the **file**, not of the project: the December file
carries two codes and the panel file carries three. One project-wide map would be
wrong for one of them, and the failure is silent, because a code valid in both files
relabels one coin as another without raising. So `COIN_CODES_BY_ARTIFACT` in
`settings.py` is keyed by artifact and `settings.coin_labels(artifact)` and
`settings.coin_codes(artifact)` demand the artifact's name and raise on one they do
not know. Every script that decodes a coin column asks through the accessor, several
of them for both maps at once, where they report per-coin results over a superset of
what one input file carries.

## Field naming

`FIELD_SUFFIX_STYLE` in `settings.py` declares the convention, and
`settings.field_name(base, h, lens)` builds every window-bearing key so that none is
typed. The convention is that **every window-bearing field names its window
explicitly and no key is left unsuffixed**, because an unsuffixed key cannot say
which convention it belongs to. That ambiguity was real: two files once wrote a key
of the same literal name meaning two different windows, under two opposite suffix
rules. The lens is appended as well when a file writes both lenses, because a
mid-lens value under a print-lens key is the same defect as a long-window value under
a short-window key. The files that write window-bearing keys build them there:
`ks2_markout_multiday.py`, `ks2_persistence_10day.py`, `m6_inventory.py`,
`m7_size.py`, `panel_analyze.py`, `panel_build.py`, `panel_common_idio.py`,
`panel_persistence.py`, `t1_toxicity_skew_backtest.py` and `t3_capacity.py`.

## Migration state, and what a fingerprint may assert

`SETTING_STATE` at the end of `settings.py` labels each declaration. **In force**
means every consumer already agrees, so adopting the declaration moves no number.
**Target** means consumers disagree, so the switch will move a published number and
is owed its own recompute with a leaf-by-leaf comparison. `checks/chk_settings_home.py`
reads that map, so a target cannot be quietly relabelled as settled.

`settings.fingerprint()` returns the block a results file stamps into its `_meta`
under the key `settings_fingerprint`. It asserts only the settings whose declaration
is in force. A setting still being migrated appears under `declared_not_confirmed`,
which says what the module declares while stating plainly that this run did not
confirm it, unless the caller passes what its run actually used. Without that rule a
script still drawing the smaller permutation budget would stamp the declared budget
into its own results file, and the artifact would assert something false about itself
in the very block a reader consults to check it.

## Getting the data (free routes first)

You do not need AWS to reproduce the results. The reproduction notebook
`notebooks/counterparty_adverse_selection.ipynb` downloads about 190 MB from the public
dataset named in `README.md` and recomputes the reported numbers, with no account and no
payment. Three files come down from that record and no more: the per-fill file and the two
order-book series. The figures the notebook checks itself against are not among them; they
travel inside the notebook in a generated cell, so that they cannot be of a different age
than the code checking them. `notebooks/README.md` gives the details.

The counterparty and maker fields of the per-fill file are pseudonymous codes. The address
map is not published, so the linkage to on-chain addresses is not distributed here, though
a reader holding the open source data can re-derive it by matching on coin, time, price and
size.

The trades behind every reported figure were parsed from the Hyperliquid node data,
`s3://hl-mainnet-node-data/node_fills_by_block`. The same December 2025 trades are also
openly published by Albers et al. (2026), Zenodo DOI 10.5281/zenodo.18184441, with two
local differences described in `README.md`, and without the fields `crossed`, `dir` and
`closedPnl` the parser reads. To re-check the repeat-counterparty structure with no
account, download `trades_2025_12.tar` from that record and point
`data/killswitch1_repeat_density.py` at it. The requester-pays S3 route below is needed
only to rebuild the `.npz` intermediates from raw.

The notebook declares its own scoring window rather than importing `settings.py`,
because it is meant to run detached from a clone of this repository. That is the one
place a declaration is deliberately repeated, and the notebook says so at the point
of declaration.

## AWS access (optional, only for a full raw rebuild)

Skip this section unless you are regenerating the intermediates from the raw archive;
the notebook route above needs none of it.

The fills-fetching scripts read `s3://hl-mainnet-node-data`
(`node_fills_by_block/hourly/<YYYYMMDD>/<H>.lz4`), a **requester-pays** bucket: the
caller's AWS account is billed for the GET and egress, so valid credentials are
required even though the data is public. Every call already passes
`--request-payer requester`.

The mid-price intermediate is built from a **second, separate** archive,
`s3://hyperliquid-archive/market_data/<YYYYMMDD>/<H>/l2Book/<COIN>.lz4`. This bucket
holds the L2 order-book snapshots consumed by `i4_l2_mid.py` and by
`i3_book_comparator.py`, and synced by the first step of `run/run_i4.sh`. It is also
**requester-pays** and uses the same AWS credentials and the same flag, but it is a
different archive from `hl-mainnet-node-data`: the fills live in one bucket, the L2
book in the other.

Setup:

1. Use an IAM principal with **read-only** S3 access (`s3:GetObject`,
   `s3:ListBucket`). No write or delete permission is needed or wanted.
2. Provide credentials through the standard AWS chain, environment variables
   (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, optional `AWS_SESSION_TOKEN`), an
   `~/.aws/credentials` profile, or an instance role.
3. **Never commit credentials.** No key, secret, token, `.env`, or
   `~/.aws/credentials` file belongs in this repository. The root `.gitignore`
   already excludes `.env*`; keep AWS keys out of every committed file and out of
   script source.
4. The `aws` CLI and the `lz4` decompressor must be installed and on `PATH`.
