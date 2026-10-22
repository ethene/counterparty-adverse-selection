# Counterparty-Resolved Adverse Selection and Quote Design on a Transparent Perpetual Exchange

This repository holds the code, the committed results and the reproduction notebook for
the paper

> Dmitry Stakhin and Saad Zaman (2026). *Counterparty-Resolved Adverse Selection and Quote
> Design on a Transparent Perpetual Exchange*. Preprint, SSRN.

Every number in the paper is read from a results file in this tree, and every results file
names the script that wrote it, the inputs it read with their hashes, and the settings it
ran under. `CITATION.cff` gives the citation for the paper and for this software.

## What the paper asks, in brief

On Hyperliquid, a perpetual futures exchange that settles on its own chain, every fill
records the wallet on each side. The adverse selection a resting market maker suffers can
therefore be attributed to the recurring counterparty that caused it, rather than to an
anonymous aggregate as on a centralised exchange. The paper asks three questions of that
attribution: whether it is stable enough to act on, whether a maker who sees only the full
public order book could have reached the same ranking without it, and what acting on it is
worth to a maker who quotes. It extends the inventory-only market-making model of
Avellaneda and Stoikov (2008) with a counterparty-resolved adverse-selection term.

## Reproducing the results

There are three routes, from the cheapest to the most complete.

**1. The notebook, which needs no account and no payment.**

```
notebooks/counterparty_adverse_selection.ipynb
```

Open it locally, or upload the single file to Google Colab, and run all cells. It
downloads about 190 MB from the public dataset deposited with this paper, three files and
no more (`notebook_fills.npz`, `notebook_book_BTC.npz`, `notebook_book_ETH.npz`), rebuilds
most of the reported figures from the per-fill data and the order-book series, and asserts
each one against the published value, printing a pass or fail line per comparison. The
last cell fails the run if any comparison fails. A few figures need inputs the published
slice does not carry, such as a second venue or the full late tape; the notebook displays
those from the committed results files, says so on the line that prints them, and lists
them in a table near its end. The notebook ships with the saved output of one complete
run, and `notebooks/README.md` describes what it downloads and what it checks.

Dataset: https://doi.org/10.5281/zenodo.23540388. Its three files are byte-identical
(same MD5) to those of the earlier record 10.5281/zenodo.21820077.

**2. The integrity checks, offline, one command.**

```
uv run --no-project --with-requirements requirements.txt python3 checks/run_all_checks.py
```

These check the tree against its own rules: that every results file still matches the code
and the inputs that produced it, that no setting is declared in two places, that no join
reads a price stamped after the moment it prices, and that the raw parse is right. The
runner prints how many checks it runs, the verdict of each and what each enforces. Checks
that need the derived intermediates, the network or a walk over the raw archive are
opt-in, through `--data`, `--network` and `--tape`. `--network` only fetches from free
public hosts; every check that can call the requester-pays S3 archive, which bills the
caller, is under `--tape`, and reads from `CAP_RAW_CACHE` instead when the hours are
cached there.

**3. The pipeline from the raw archive.** The scripts are split into nine groups, one
directory each, and each group has one entry point in `run/`. With no flags an entry point
prints what it would recompute and what that would cost, and computes nothing; `--run`
recomputes the group; `--only NAME` brings one script, one results file or one
`file:key.path` quantity up to date together with what it reads.

```
uv run --no-project --with-requirements requirements.txt python3 run/persistence.py
uv run --no-project --with-requirements requirements.txt python3 run/persistence.py --run
uv run --no-project --with-requirements requirements.txt python3 build.py --plan
```

`build.py` owns the dependency graph, which it derives from the syntax of every script,
and the skip rule: a script is re-run only when its own bytes, the bytes of an input, or a
setting it depends on has changed. Rebuilding from the raw archive reads requester-pays
buckets and needs AWS credentials; `CONFIG.md` describes the setup.

## The data

**Source of the trades.** Every reported figure is computed from the Hyperliquid node
data, `s3://hl-mainnet-node-data/node_fills_by_block`, parsed by
`data/build_quickwin_markouts.py`. The order-book snapshots come from a second archive,
`s3://hyperliquid-archive/market_data`. Both buckets are requester-pays.

The open archive of Albers, Cucuringu, Howison and Shestopaloff, "An Open Book" (Zenodo,
DOI 10.5281/zenodo.18184441, 2026), carries the same trades for December 2025. We compared
the two trade by trade on BTC and ETH on 21 October 2026, matching on coin, block hash,
price, size and both wallets. Eight of the ten days agree exactly. On 9 December the
archive repeats about 700 records between 12:39 and 12:41 UTC, and on 12 December it has no
records from about 17:41 to 18:14 UTC; the node data is complete in both places. The fields
`crossed` (which side is the maker), `dir` and `closedPnl`, which the parser reads, are
present only in the node data. The archive can still be used without an account to re-check
the repeat-counterparty structure: download `trades_2025_12.tar` and point
`data/killswitch1_repeat_density.py` at it.

**What is covered.** The reported results use the December 2025 window, 4 to 13 December,
on BTC and ETH: 2,480,267 taker trades by 45,849 taker wallets against 9,367 makers. The
unit is one collapsed taker trade: a sweep that crosses several resting makers prints one
fill per maker, and the parser merges the legs that share a block hash and a taker wallet
into one row at a size-weighted entry price. A wider panel of eight ten-day windows from
August 2025 to May 2026 on BTC, ETH and SOL, 26,035,902 collapsed trades, is used only to
ask whether the persistence result holds outside December. Its committed readers pin three
windows (August, October and December 2025), which is 10,455,129 rows. Book coverage is
above 99.7 per cent in four windows and between 96.29 and 97.31 per cent in three; November
2025 covers about 61 per cent because the published archive itself is thin there, so no
book-based measure is computed on it.

**Counterparty codes.** The `taker_code` and `maker_code` columns of the published
per-fill file are integer pseudonyms. The map from codes to on-chain addresses is not
published, although a reader holding the open source data can rebuild it by matching on
coin, time, price and size.

**Licences.** The code in this repository is released under the MIT licence (`LICENSE`).
The derived dataset on Zenodo is released under CC-BY-4.0, the licence of that record.

## The results in one page

The quantity measured throughout is the signed taker markout: the move of the reference
price after a fill, signed so that a positive number means the taker was right and the
maker lost. The reference is the mid of the order book, taken from the last snapshot
strictly before the trade, and the horizon is ten seconds, declared once in `settings.py`.
Wallets are ranked on the first five days of the window and measured on the last five.

1. *The flow costs the maker.* Weighted by notional, the book mid moves 2.2388 basis points
   against the maker in the ten seconds after a fill, against 1.8779 at one second and
   2.3150 at sixty. By ten seconds 98.1 per cent of the eventual move has arrived, against
   a declared threshold of 95 per cent. Equal-weighted the level is 1.3147, so the cost
   sits in the large trades.
2. *Toxicity is a trait of the wallet.* A wallet ranked on the early half keeps its rank in
   the late half at a noise-corrected Spearman correlation of 0.78 to 0.90 on the trade
   print and 0.81 to 0.92 on the book mid, over two coins and two minimum-trade floors. The
   uncorrected correlation on the trade print is 0.50 to 0.79.
3. *The public book does not reach the same ranking, and the two coins differ.* Against
   fourteen public features, four from the trade tape and ten from the order book, wallet identity adds an out-of-sample R-squared of
   0.0594 on BTC and 0.4000 on ETH, medians over forty fold seeds.
4. *A screen on the counterparty avoids most of the cost.* Ranking wallets on the early
   half and dropping the worst tenth avoids 91.0 per cent of the gross positive cost booked
   in the late half, against 9.9 per cent for a random tenth. This result is measured on
   the trade print, and it rests on a small number of wallets: dropping the ten costliest
   wallets leaves 70.7 per cent.
5. *Resolving the counterparty improves the quote, as a smaller cost rather than a profit.*
   The counterparty-resolved quoter beats symmetric Avellaneda-Stoikov by 0.5231 basis
   points of net result, of which 0.3200 survives a label-shuffle placebo at a permutation
   p of 0.0005. Every quoter compared is net negative at every fee tier, and the comparison
   books no fill probability, so the gain is an upper bound.

All five rest on one venue, two instruments and one ten-day window.

The table below gives the file and key each figure is read from. The first column names
the figure, the second the results file, the third the key inside it.

| Figure | File | Key |
|---|---|---|
| trades, taker wallets, makers | `data/quickwin_pass_summary.json` | `total_rows`, `n_unique_takers`, `n_unique_makers` |
| markout term structure | `markout/ws1_horizon_results.json` | `level_termstructure.pooled.{1,10,60}.vw` and `.ew`; the arrived share is `final_decision.info_frac.{h}` against `final_decision.info_complete_frac_threshold` |
| persistence, trade print | `persistence/ks2_persistence_10day_results.json` | `persistence_pooled[*].spearman_disattenuated` and `.spearman_obs` |
| persistence, book mid | `persistence/ks2_persistence_mid_results.json` | `persistence_pooled[*].spearman_disattenuated` |
| identity lift over the public book | `identity/i3_book_nonrecoverability_results.json` | `seed_robustness.cells[coin, horizon_s=10, K=50].median`, `.min`, `.max` |
| cost and the avoidable share | `money/t3_results.json` | `pooled.total_cost_usd_10s`; `pooled.avoidable_10s.avoidable_share_oos_top10pct_10s`, `.random_floor_top10pct_10s.mean`, `.oracle_ceiling_top10pct_10s`, `.whale_drop_ladder_top10pct_10s` |
| maker net by fee tier | `money/maker_econ_results.json` | `baseline_net.pooled.by_horizon.h10.net_MID_lower.by_fee_tier.{base,rebate3}.net_vw_bps` |
| counterparty-resolved gain and its placebo | `quoters/mm_bakeoff_results.json` | `adverse_selection_term_value.K50.pooled.base.as_toxicity_minus_as_symmetric_delta_net_vw_bps`; `placebo_label_shuffle.count_matched.pooled.reduction_vs_null_net_vw_bps` and `.permutation_p` |
| scoring horizon | `settings.py` | `HEADLINE_HORIZON_S`, echoed in every results file at `_meta.settings_fingerprint.headline_horizon_s` |

`HYPOTHESIS_FAMILY.md` names which cells carry the argument, so that the several thousand
sensitivity p-values in the tree are not read as several thousand findings.

## How the tree is laid out

A script's directory is its pipeline group, so the path of a file says which entry point
recomputes it. The groups, in the order they depend on each other:

| Directory | Entry point | What the group answers |
|---|---|---|
| `data/` | `run/data.py` | what was parsed out of the archive, over which windows and coins, and whether the parse reproduces |
| `markout/` | `run/markout.py` | how large the cost of a fill to the maker is, and how it varies with horizon, size, inventory and side |
| `persistence/` | `run/persistence.py` | whether that cost is a stable trait of the wallet rather than of one window |
| `identity/` | `run/identity.py` | whether a maker who sees only the public tape and book could recover what the counterparty's identity gives |
| `quoters/` | `run/quoters.py` | what the standard quoting models do on this fill set, and what the counterparty-resolved term changes |
| `money/` | `run/money.py` | what the cost is worth in currency, where it is concentrated, and what a policy acting on the counterparty recovers |
| `probes/` | `run/controls.py` | whether each result is explained by something other than what it is claimed to be explained by |
| `checks/` | `run/gates.py` | whether the raw parse is right and whether the tree still holds against its own rules |
| `notebook_build/` | `run/notebook.py` | what the reproduction notebook downloads and what it asserts against |

Two further directories are not groups: `run/` holds the entry points, the module they
share and five shell drivers for the long acquisition passes, and `notebooks/` holds the
notebook and the files that ship with it. The root holds what no single group owns: the
shared modules, the build and its diagram, the register of inputs and the documents.
`pipeline_diagram.png` draws the nine groups and the files that pass between them, and
`build_diagram.md` is the same drawing as Mermaid text; both are generated by
`build_diagram.py` from the dependency graph.

`run/gates.py --census` puts the group table against the dependency graph and reports any
script no group claims, any group entry the graph does not hold, and any script claimed
twice.

Where to start reading: `settings.py` declares every setting that moves a reported number,
with the argument that fixed each value; `CONFIG.md` explains those settings and says which
script reads which; every analysis script opens with a header that states what it
computes, what it does not claim and what would refute it.

## Environment

- Python 3.11 or later, with the versions pinned in `requirements.txt`.
- The command that honours the pins is
  `uv run --no-project --with-requirements requirements.txt python3 <script>.py`.
  The shorter form `--with numpy` resolves numpy freshly on the day of the run and does not
  install matplotlib, so it does not reproduce the pinned environment.
- Alternatively, `pip install -r requirements.txt` into a Python 3.11 environment and run
  the scripts with plain `python3`.
- `requirements.txt` lists, beside each pin, which files import that package. The list is
  generated by `build_requirements_census.py`, which exits non-zero when it has moved.
- The scripts that fetch from the archives need the AWS command-line client on `PATH`, and
  the `lz4` binary as a decompression fallback.

## Every tracked file

Every tracked file is named in one of the tables below, with what it is and why it exists.
Scripts and the results file each writes share a row, so a number can be walked back to the
code that produced it. **Writes** names the tracked file a script produces; `none` means it
writes only large intermediates that are regenerated rather than stored, or no artifact at
all. `[core]` marks a script that produces a number cited in the paper, `[robustness]` one
that defends a core result, `[check]` one that checks the tree against itself.

Within a group the name prefix encodes the role. `build_` and `i4_` are data builds and
`panel_` is the eight-window panel; `d1_` and `d2_` describe the raw material; `m2_` to
`m11_` are measurement objects; `i2_`, `i3_` and `i5_` are identification objects; `t1_`
and `t3_` are tradeability tests; `ws1_` to `ws3_` are horizon selection and screening;
`chk_` are the checks. A name ending in `_figure` writes an image together with a results
file recording what the image draws. `as_`, `gm_` and `kss_` are the initials of Avellaneda
and Stoikov, Glosten and Milgrom, and Kline, Saggio and Solvsten, whose procedures those
files implement; `eb_` is empirical Bayes; `mm_` is the market maker. In `probes/` a letter
marks one named objection (A1 the calibration of scope, B1 the mobility gate, C the
decomposition, D to G four later objections); the B2 of `money/maker_econ_b2.py` is a
different series and numbers the maker's policies. `killswitch` and `ks2_` are the two
feasibility tests written before the study, and `ks2_persistence_10day.py` is the second of
them done at the power it needed.

### Documents and environment

| File | What it is and why |
|---|---|
| `README.md` | this file |
| `LICENSE` | the MIT licence for the code |
| `CITATION.cff` | how to cite the paper and this software |
| `CONFIG.md` | what every setting means and which script reads it. It holds no values, because a second copy of a number drifts from the first |
| `CONTRIBUTORS.md` | who wrote the code |
| `HYPOTHESIS_FAMILY.md` | the declared hypothesis family: which claims carry the argument and which cell heads each, so the multiplicity correction applies to that family and nothing else |
| `DEFERRED_EDITS.md` | edits to an expensive producer that are written down instead of made. A results file records the hash of the script that wrote it, so a comment added to a producer makes a correct results file stale and only a rerun restores the match. `checks/chk_expensive_edits.py` reads it |
| `requirements.txt` | the pinned dependencies, with a generated list of which files import each package |
| `.gitignore` | what is regenerated rather than stored: the large `.npz` intermediates, raw archive caches, per-wallet address maps, run logs, and credentials |

### Shared infrastructure

These belong to no single group and compute no quantity of their own.

| File | What it is and why |
|---|---|
| `settings.py` | the single home of every setting that moves a reported number, each with the argument that fixed its value. `SETTING_STATE` says which declarations every consumer already follows |
| `stats.py` | the permutation test with its floor, the bootstrap interval and the Benjamini-Hochberg correction. Every function returns the procedure beside the number, so a p-value never travels without its draw count |
| `artifact.py` | the one writer of results files. Each records its producer and that producer's hash, its inputs and their hashes, the population and window covered, the settings fingerprint and the run |
| `panel_io.py` | where a markout panel is, which column is the score, and what to say when the column is missing |
| `build.py` | the recompute as a dependency graph with a skip rule, derived from the syntax of every script. With no arguments it runs its own self-test, which exits 1: of its 77 assertions one fails by design, the census of file operations, whose residue of unresolved calls stands above a declared ceiling of zero. `checks/chk_build_selftest.py` holds that failure against the declared debt and passes while nothing else fails |
| `build_declarations.py` | the file operations `build.py` cannot resolve to a constant, declared by hand with the reason |
| `skip_rule.py` | the rule by which the build decides whether a node has to run: skip, run and name what moved, or neither when the question cannot be put |
| `build_results.json` | the journal of one build: which nodes were planned, why, and what each cost |
| `build_diagram.py` | draws the dependency graph as nine group boxes. `--png` also renders the picture, which needs mermaid-cli |
| `build_diagram.md` | the drawing as Mermaid text, with the counts it shows and the predicate behind each. Generated |
| `build_diagram_results.json` | the record of how that drawing was taken, including the hash of the picture |
| `pipeline_diagram.png` | the same drawing rendered |
| `data_register.py` | the register of every file the pipeline reads, resolved by hash rather than by path, with the computations that stand on each |
| `data_register.md` | that register for a reader. Generated |
| `data_register_results.json` | the same register for a program |
| `build_requirements_census.py` | derives the list inside `requirements.txt` of which files import which package; `--write` regenerates it |
| `prose_assemble.py` | fills figures into a document from the results files at the addresses the register of quantities states, so a figure in the text cannot go stale. `--check` reports any figure the text disagrees with |

### 1. `data/`: the expensive passes and the checks on them

| Script | Writes | What it is and why |
|---|---|---|
| `build_quickwin_markouts.py` **[core]** | `quickwin_pass_summary.json` | the single expensive pass over the fills archive. Collapses each taker sweep to one row per block hash and taker at a size-weighted entry price, computes the signed taker markout, and writes the shared per-fill intermediate and per coin-day diagnostics |
| `i4_l2_mid.py` **[core]** | none | streams the L2 book snapshots and builds the per-coin series of mid, spread, top-of-book imbalance and micro-price |
| `i4_midmarkout.py` **[core]** | `i4_midmarkout_results.json` | the same markout against the book mid, on rows identical to and in the same order as the trade-print file |
| `panel_persistence.py --build` **[core]** | none | the only writer of `panel_markouts.npz`, the eight-window three-coin panel. Checkpoints per coin-month and discards raw files as it goes to stay inside the disk limit |
| | `panel_persistence_results.json` | written by the same script under `--analyze`, described in section 3 |
| `panel_build.py` | none | the earlier three-window builder, which writes to its own file name so that the two builders cannot overwrite each other |
| `panel_rebuild_v2.py` | `panel_v2_manifest.json` | the panel plus the native nanosecond block time and the forced-liquidation flag. The manifest records the hash and size of the panel and of the 24 shards it read, since the panel itself is not stored |
| `build_toxicity_frame.py` | `toxicity_frame_results.json`, `notebooks/wallet_toxicity_frame.csv` | a counterparty-level frame: one row per counterparty and coin, behaviour features from the early half of the window and the mean late-half markout as the label. The halves are disjoint, so no fill feeds both a feature and the label |
| `step1_inventory.py` **[check]** | none | per coin and window, the trade count, the snapshot count, the median snapshot spacing and the wall-clock coverage, against the values recorded when the cell was built |
| `check_first.py` **[check]** | `check_first_results.json` | a quick check of the two intermediates: schema, day coverage, row alignment by content, the per-day divisor |
| `killswitch1_repeat_density.py` **[validation]** | none | the first feasibility test: whether the tape has enough recurring counterparties for a per-wallet effect to be identifiable |
| `killswitch2_markout_join.py` **[validation]** | none | a superseded first attempt at a reference mid from the book-change stream, which carries no per-event timestamp. Kept for the sign convention it documents |
| `d1_book_shape_figure.py` | `d1_book_shape.png`, `d1_book_shape_figure_results.json` | the shape of the order book: median resting notional against distance from the mid, and the hourly median spread across the ten days with the early-late boundary marked |
| `d2_fill_tape_figure.py` | `d2_fill_tape.png`, `d2_fill_tape_figure_results.json` | the trade tape: daily trade counts with the early-late cut, and the distribution of trade notional on a log axis |

### 2. `markout/`: how large the cost is and how it is shaped

| Script | Writes | What it answers |
|---|---|---|
| `ws1_horizon_persistence.py` **[core]** | `ws1_horizon_results.json` | which horizon should define the score: out-of-sample rank persistence and the share of the eventual move already arrived, over a grid of horizons. It is the evidence behind the declaration in `settings.py` |
| `ws1_plot.py` | `ws1_horizon_choice.png` | the figure of that decision, read from the results file |
| `ws1_markout_curve_figure.py` | `ws1_markout_curve.png`, `ws1_markout_curve_figure_results.json` | the cost curve: how far the mid moves against the maker after a fill, value- and equal-weighted, pooled and by coin |
| `m5_termstructure.py` **[core]** | `m5_termstructure_results.json` | the toxicity curve over horizon and the per-wallet monotonicity, against the chance ordering |
| `m6_inventory.py` **[robustness]** | `m6_inventory_results.json` | whether a taker already holding a position, or adding to one, hits the maker harder |
| `confound_asymmetry.py` **[robustness]** | `confound_asymmetry_results.json` | whether the buy-sell gap in markout is adverse selection or directional drift |
| `temp_perm_decomp.py` **[robustness, null]** | `temp_perm_results.json` | a temporary-versus-permanent split of impact. The label is not supported on this sample and `probes/probe_G_horizon.py` replaces it; the split-half persistence block remains valid |
| `m2_figure.py` | `m2_fig1_counterparty_toxicity.png`, `m2_figure_results.json` | the figure motivating the premise: an out-of-sample-identified set of counterparties against the rest, on two price references. Its population differs from the headline one (550 wallets in the drawn decile against 4,943), and its results file records the labelling rule |

### 3. `persistence/`: is it a stable trait of the wallet

| Script | Writes | What it answers |
|---|---|---|
| `ks2_persistence_10day.py` **[core]** | `ks2_persistence_10day_results.json`, and `ks2_persistence_mid_results.json` under `--source mid` | the main within-window persistence test: split-half reliability of the per-wallet score, and early-versus-late rank persistence corrected for it, on the trade print and on the book mid |
| `ks2_markout_multiday.py` **[core]** | `ks2_multiday_results.json` | the three-day predecessor, where the sweep collapse was introduced |
| `i2_walletfe.py` **[core]** | `i2_walletfe_results.json` | the share of cross-sectional markout variance that is a stable per-wallet component, naive and corrected by a split-half covariance |
| `panel_persistence.py --analyze` **[core]** | `data/panel_persistence_results.json` | whether a wallet's toxicity in one month predicts it in another |
| `panel_common_idio.py` **[core]** | `panel_common_idio_results.json` | a wallet's toxicity split into a market-wide component per window and an idiosyncratic component stable across windows |
| `panel_analyze.py` **[core]** | `panel_analyze_results.json` | whether the December identification and cost chain reproduces month by month, with the December estimators run unchanged |
| `panel_extended.py` **[robustness]** | the seven `panel_extended_results_*.json` | the same estimators over all eight windows, written to separate files; the control run must reproduce the committed file cell for cell |
| | `panel_extended_results_h1_canonical.json`, `panel_extended_results_h10_canonical.json`, `panel_extended_results_h60_canonical.json` | the control runs on the three committed windows, one per horizon |
| | `panel_extended_results_h1_all.json`, `panel_extended_results_h10_all.json`, `panel_extended_results_h60_all.json` | the same over all eight windows |
| | `panel_extended_results_h60_canonical_REPEAT.json` | a repeat of one control, kept so the two runs can be compared |
| `forward_toxicity.py` **[robustness]** | `forward_toxicity_results.json` | the same claim on a strictly later window that did not exist when the method was fixed |
| `three_coin_persistence.py` **[robustness]** | `three_coin_persistence_results.json` | persistence on a third contract, SOL, and on the book mid, with a fifty-seed split-half reliability. Its estimator differs from `ks2_persistence_10day.py`, so the two sets of numbers are close but not equal |
| `m9_crossasset.py` **[robustness]** | `m9_crossasset_results.json` | whether a wallet toxic in one coin is toxic in another, as a curve over the fill floor |
| `ws2_hard_classifier.py` **[core]** | `ws2_hard_classifier_results.json`, `ws2_hard_classifier.png` | a toxic-or-not rule with credibility shrinkage, a per-wallet significance filter, and a threshold set by out-of-sample validity and checked against economic break-even |
| `ws3_taker_pnl.py` **[core]** | `ws3_taker_pnl_results.json` | whether the wallets flagged toxic from the maker's loss are the wallets that profit on their own realised result |
| `ws3_plot.py` | `ws3_taker_pnl.png` | the rank agreement between toxicity and realised profit, pooled and by coin, with bootstrap intervals |

### 4. `identity/`: could an anonymous maker have known

| Script | Writes | What it answers |
|---|---|---|
| `i3_nonrecoverability_oos.py` **[core]** | `i3_results.json`, and `i3_nonrecoverability_mid_results.json` under `--source mid` | a maker who knows only anonymous trade-flow metrics predicts a wallet's future toxicity; the wallet's own history is added and the out-of-sample lift is measured against a label-permutation placebo. It bounds recovery from the trade tape, not from the book |
| `i3_book_comparator.py` **[core]** | `i3_book_nonrecoverability_results.json` | the headline identification test: the full public book feature set joined to each fill with no lookahead, and whether identity still adds lift on top of it |
| `i5_exclusion.py` **[core]** | `i5_exclusion_results.json` | the pre-registered exclusion test: flow extending a position should carry permanent impact, flow reducing one should revert |
| `i3_depth_control.py` **[robustness]** | `i3_depth_control_results.json` | whether identity is a proxy for the book state each wallet trades into, with a linear and a non-linear control |
| `own_size_control.py` **[robustness]** | `own_size_control_results.json` | the same question for trade size and style, with a placebo that permutes within size deciles |
| `follow_the_informed_oos.py` **[robustness]** | `follow_the_informed_oos_results.json` | whether a maker could follow the toxic wallets rather than decline them, out of sample and net of fees and latency |
| `i3_pretrade_vs_identity_figure.py` | `i3_pretrade_vs_identity.png`, `i3_pretrade_vs_identity_figure_results.json` | what is knowable while the quote stands: the between-counterparty share of markout variance before and after subtracting the book state, read from the identification results |

### 5. `quoters/`: the quoting models

| Script | Writes | What it answers |
|---|---|---|
| `as_quoter.py` **[core]** | `as_quoter_results.json` | the Avellaneda-Stoikov closed form, calibrated on the fills: the inventory-only, counterparty-blind baseline |
| `gm_quoter.py` **[core]** | `gm_quoter_results.json` | the Glosten-Milgrom quoter, whose signal is market-level flow toxicity with no counterparty identity |
| `mm_bakeoff.py` **[core]** | `mm_bakeoff_results.json` | all quoters on one fill set under one maker net-result measure: naive at book, naive constant, symmetric Avellaneda-Stoikov, Glosten-Milgrom, Barzykin-Bergault-Gueant-Lemmel, and Avellaneda-Stoikov with the counterparty-resolved term, plus width-matched controls and a label-shuffle placebo |
| `t1_toxicity_skew_backtest.py` **[core]** | `t1_backtest_results.json` | the counterparty-aware maker against the symmetric baseline, ranked on an early window and evaluated on a later one, with a walk-forward version |
| `mm_bakeoff_reference_figure.py` | `mm_bakeoff_reference.png`, `mm_bakeoff_reference_figure_results.json` | the same quoters under the book-mid and the trade-print measures, showing that "no rule is profitable" depends on the reference price |

### 6. `money/`: what it is worth

| Script | Writes | What it answers |
|---|---|---|
| `t3_capacity.py` **[core]** | `t3_results.json` | the maker's gross loss to adverse selection in dollars over the window, and the share a held-out screen would have avoided |
| `maker_econ.py` **[core]** | `maker_econ_results.json` | the maker's net result on the real fee schedule, computed two independent ways that must agree, with the screen applied out of sample |
| `maker_econ_b2.py` **[core]** | `maker_econ_b2_results.json` | the deployable policy: widen against flagged wallets, recapture part of the flow, decline the rest, with the forgone benign income reported |
| `m11_concentration.py` **[core]** | `m11_results.json` | how concentrated the cost is across counterparties, per dollar and in dollars |
| `m8_makerside.py` **[core]** | `m8_makerside_results.json` | which makers bear the adverse selection, including whether the protocol vault is among them |
| `m4_realizedpnl.py` **[robustness]** | `m4_realizedpnl_results.json` | a second toxicity measure with no reference-price model: the taker's realised profit as booked by the exchange |
| `m7_size.py` **[robustness]** | `m7_size_results.json` | whether adverse selection sits in large or small fills, by notional decile per coin |
| `sensitivity_rollup.py` | `sensitivity_rollup_results.json` | what each number would be at the other candidate setting, extracted from the sweeps already in the results files |
| `m9_decile_economics_figure.py` | `m9_decile_economics.png`, `m9_decile_economics_figure_results.json` | the early-half ranking decile against the late-half net result, notional- and equal-weighted |

### 7. `checks/`: the checks

Two kinds. The first checks the raw parse against the archive itself; the second checks the
tree against its own rules. Every check writes a results file beside itself, exits non-zero
on a regression, and prints the expectation, the fact and the place.

| Check | Writes | What it enforces |
|---|---|---|
| `chk_side_signconv.py` | `chk_side_signconv_results.json` | the aggressor-side and markout-sign convention, re-derived from raw bytes |
| `chk_book_orientation.py` | `chk_book_orientation_results.json` | that the book is the right way up, from raw ladder monotonicity |
| `chk_dir_vs_startpos.py` | `chk_dir_vs_startpos_results.json` | that the parsed direction agrees with the signed pre-trade position |
| `chk_closedpnl.py` | `chk_closedpnl_results.json` | the semantics and sign of the realised-profit field |
| `chk_join_nolookahead.py` | `join_nolookahead_results.json` | that no join reaches forward in time, as a unit test on hand-built arrays |
| `chk_rowcounts_determinism.py` | `chk_rowcounts_determinism_results.json` | the row counts, and that re-parsing a day reproduces the stored slice |
| `chk_field_hygiene.py` | `chk_field_hygiene_results.json` | that no fill is dropped by the parse and that the duplicated parser has not drifted |
| `chk_maker_attribution.py` | `chk_maker_attribution_results.json` | whether resting orders carry the owner's identity in the raw data |
| `chk_liquidation_field.py` | `chk_liquidation_field_results.json` | the liquidation marker, re-derived without the project parser |
| `chk_academic_header.py` | `chk_academic_header_results.json` | that every tracked script and the notebook open with the study name, its author and its date |
| `chk_no_abs_paths.py` | `chk_no_abs_paths_results.json` | that no tracked file names a home directory |
| `chk_settings_home.py` | `chk_settings_home_results.json` | one home per setting, no key collision, no stale settings fingerprint, and the notebook's declared values agreeing with `settings.py` |
| `chk_headline_horizon.py` | `chk_headline_horizon_results.json` | that the scoring horizon is declared and never spelled in a column name |
| `chk_artifact_provenance.py` | `chk_artifact_provenance_results.json` | that every results file names its producer, inputs, runtime, population and settings, and still matches the code that wrote it |
| `chk_input_freshness.py` | `chk_input_freshness_results.json` | that every input hash a results file recorded still equals the file on disk |
| `chk_producer_committed.py` | `chk_producer_committed_results.json` | that the recorded producer bytes of every results file exist somewhere in the history. This repository's history starts at its own first commit, so a results file computed before it is listed on a separate line, neither passed nor failed, when `checks/NEUTRAL_EDITS.json` certifies that its recorded producer leads to the one on disk by an edit that changes no figure; without such a certificate it fails |
| `chk_run_happened.py` | `chk_run_happened_results.json` | that a recompute took place after a given moment before its numbers are compared |
| `chk_pinned_versions.py` | `chk_pinned_versions_results.json` | that the library versions a results file recorded are the versions `requirements.txt` pins |
| `chk_requirements_census.py` | `chk_requirements_census_results.json` | that the census inside `requirements.txt` (how many files, which third-party and standard modules they import) still matches the tree, reporting apart a finding where only the render date moved |
| `chk_notebook_expectations.py` | `chk_notebook_expectations_results.json` | that the figures embedded in the notebook equal `notebooks/notebook_expected.json` and that no cell fetches them from elsewhere |
| `chk_notebook_pointer_table.py` | `chk_notebook_pointer_table_results.json` | that what the notebook's table calls out of reach is not something the notebook recomputes |
| `chk_decision_lookahead.py` | `chk_decision_lookahead_results.json` | that no screening decision uses data from after it: population, threshold, constants and inputs |
| `chk_contrast_hygiene.py` | `chk_contrast_hygiene_results.json` | that the two arms of a published difference differ only along the declared axis |
| `contrast_declarations.py` | none, it is a declaration | which pairs of arms the work ranks without claiming a difference |
| `chk_expensive_edits.py` | `chk_expensive_edits_results.json` | that no cosmetic edit is made to an expensive producer unless it is listed in `DEFERRED_EDITS.md` |
| `chk_prose_numbers.py` | `chk_prose_numbers_results.json` | that every figure in a register of quantities equals the results-file leaf at its address, with the check's own false-acceptance rate measured on each run. The register is not shipped and is passed with `--registry PATH` or `PROSE_REGISTRY`; without one the check records that it compared nothing and exits 0 |
| `chk_build_selftest.py` | `chk_build_selftest_results.json` | the build's own self-test, held against a declared ceiling of known failures |
| `run_record.py` | none, it is a module | the one implementation of "does this results file match the script that wrote it" |
| `NEUTRAL_EDITS.json` | none, it is a register | certificates that a specific edit to a producer cannot have moved any figure |
| `evidence.py` | none | the shared reporting helper the checks call |
| `run_all_checks.py` | `run_all_checks_results.json` | runs all checks, grouped by what each needs |
| `run_verify_s3.sh` | none | runs the checks that re-walk the raw archive, fastest first |

### 8. `probes/`: robustness against named objections

Each probe answers one objection, and none produces a headline number.

| Probe | Writes | The objection it answers |
|---|---|---|
| `connected_set_b1.py` | `connected_set_b1_results.json` | whether the two-sided decomposition is identified off genuine mobility or leans on one dominant maker |
| `kss_decomp_c.py` | `kss_decomp_c_results.json` | the taker-by-maker variance decomposition, naive and de-biased side by side, validated by a planted-signal simulation and a label placebo. It runs a sample-split analogue of the leave-out correction rather than the full procedure |
| `kss_decomp_c_bookmid.py` | `kss_decomp_c_bookmid_results.json` | the same decomposition on the book mid |
| `c2_bookstate_control.py` | `c2_bookstate_control_results.json` | whether the maker-side effect survives controlling for the book state at entry |
| `c_matched_precision.py` | `c_matched_precision_results.json` | the decomposition with matched fill counts on both sides, so the gap is not an estimability artefact |
| `eb_scoring.py` | `eb_scoring_results.json` | empirical-Bayes scoring of wallets with unreliable estimates, validated out of sample |
| `persistence_crosswindow.py` | `persistence_crosswindow_results.json` | out-of-time persistence with training months before the test window |
| `decay_curve.py` | `decay_curve_results.json` | how persistence decays as the gap between windows widens |
| `calib_print_vs_mid.py` | `calib_print_vs_mid_results.json` | whether the trade-print measure ranks wallets closely enough to the book-mid measure for the wider panel to be in scope |
| `probe_D_pull.py` | none | fetches the funding inputs for the probe below from public endpoints, as parquet |
| `probe_D_funding.py` | `probe_D_funding_results.json` | whether aggregate on-chain flow toxicity predicts the next period's funding and basis moves |
| `probe_E_leadlag.py` | `probe_E_leadlag_results.json` | cross-venue price discovery against the dominant centralised venue |
| `probe_E_lag_resolution.py` | `probe_E_lag_resolution_results.json` | whether the lead found above is a property of the market or of the grid step |
| `probe_F_hlp_liq.py` | `probe_F_hlp_liq_results.json` | how adversely selected the protocol vault is, and whether forced liquidations read as non-toxic |
| `probe_G_horizon.py` | `probe_G_horizon_results.json` | a fuller horizon grid with a long tail, classifying each counterparty's curve by shape |
| `flat_surcharge_control.py` **[robustness]** | `flat_surcharge_control_results.json` | what knowing the counterparty buys once quote width is held constant: a flat premium at the same average width, booked on the same fills |
| `survivorship_census.py` **[robustness]** | `survivorship_census_results.json` | what the rule admitting a wallet only if it trades in both halves costs, with two published quantities recomputed under counterfactual rules |
| `decile_overlap.py` **[robustness]** | `decile_overlap_results.json` | how far apart the decile ranked by mean markout and the decile ranked by dollar cost are |

### 9. `notebook_build/`: what the notebook downloads

| Script | Writes | What it is and why |
|---|---|---|
| `make_notebook_fills.py` | none | builds the per-fill file the notebook recomputes from, with wallets as pseudonymous codes |
| `make_notebook_book.py` | `notebooks/notebook_book_meta.json` | packs the order-book series and feature block the notebook downloads, one file per coin |
| `make_notebook_data.py` | none | extracts the reported figures from the committed results files into `notebooks/notebook_expected.json` |
| `embed_notebook_expectations.py` | none | writes `notebooks/notebook_expected.json` into one generated cell of the notebook; `--check` exits non-zero if the cell is behind its file |

### 10. `notebooks/`: the reproduction notebook and what ships with it

| File | What it is and why |
|---|---|
| `counterparty_adverse_selection.ipynb` | the self-contained notebook described under "Reproducing the results" |
| `README.md` | how to run it, what each downloaded file is, and what it recomputes and what it displays |
| `notebook_expected.json` | the figures the notebook asserts against, generated from the committed results files |
| `notebook_fills_meta.json` | what the published per-fill file contains: columns, row count, window, pseudonym counts, hash and deposit |
| `notebook_book_meta.json` | the same record for the two order-book files |
| `notebook_data_meta.json` | the same record for an earlier, superseded slice |
| `wallet_toxicity_frame.csv` | the counterparty-level frame written by `data/build_toxicity_frame.py`, tracked because rebuilding it needs the raw tape. Keyed by integer index, not by address |

### 11. `run/`: entry points and shell drivers

| File | What it is and why |
|---|---|
| `_groups.py` | the group table and what the nine entry points share: the plan, the cost, the membership census and the command line |
| `data.py`, `markout.py`, `persistence.py`, `identity.py`, `quoters.py`, `money.py`, `controls.py`, `gates.py`, `notebook.py` | one entry point per group, as in the table under "How the tree is laid out". `gates.py --run` hands over to `checks/run_all_checks.py` |
| `run_step1_data.sh` | the data stage: an inventory by default, acquisition with `build`, in dependency order and resumable |
| `run_i4.sh` | the book pass: archive sync, mid series, mid markouts, then their consumers |
| `run_panel_l2.sh` | the book for every panel window and coin, one window at a time to fit on disk |
| `run_panel.sh` | the panel build followed by its analyses |
| `run_completeness.sh` | the completeness sweep, light scripts first |

## Conventions

- **One home per setting.** A setting that moves a reported number is declared in
  `settings.py` and read from there. `checks/chk_settings_home.py` and
  `checks/chk_headline_horizon.py` enforce this.
- **One writer per results file.** `artifact.py` writes every results file, so each records
  its producer, its inputs, its population and its settings.
- **No absolute paths.** A script records its inputs by file name and builds the paths it
  reads from its own location. `checks/chk_no_abs_paths.py` enforces this.
- **Baselines are declared debt.** A check printing `PASS_AT_BASELINE` found known debt
  recorded in its own file with the reason, and no regression on top of it. A baseline may
  only be lowered.
- **Results file names.** Most scripts write `<name>_results.json`. The exceptions are
  `t3_capacity.py` to `t3_results.json`, `m11_concentration.py` to `m11_results.json`,
  `ks2_markout_multiday.py` to `ks2_multiday_results.json`,
  `t1_toxicity_skew_backtest.py` to `t1_backtest_results.json`,
  `ws1_horizon_persistence.py` to `ws1_horizon_results.json`, `temp_perm_decomp.py` to
  `temp_perm_results.json`, `i3_nonrecoverability_oos.py` to `i3_results.json`,
  `build_quickwin_markouts.py` to `quickwin_pass_summary.json`, and
  `chk_join_nolookahead.py` to `join_nolookahead_results.json`.

## Licence and citation

Code: MIT, see `LICENSE`. Data: CC-BY-4.0, the licence of the Zenodo record. To cite, use
`CITATION.cff`.
