# Reproducibility notebook

`counterparty_adverse_selection.ipynb` rebuilds the book-based results this
work publishes, live from the raw fills and the L2 mid series, and checks each
recomputed number against the published value. The last
cell prints a PASS/FAIL table and fails the run if any check does not pass. It counts
its comparisons as it runs, so the number belongs to the run and is not written here:
this line used to carry one, and three sections added on 9 August 2026 made it wrong
overnight while the sentence around it still read as current.

## The file ships with the saved output of one complete pass

Open it and the verdict is already on the page. That is deliberate, and it is stated here
so that a saved number is not read as a number nobody re-derived: the reader runs the
file to confirm what is printed rather than to discover it, and the two must agree.

There are only two honest states, and it is the middle one that does the damage:
**the saved output of one complete fresh run, or no saved output anywhere.** While the
notebook was still being worked on it shipped with none, because any saved run goes stale
as soon as the next comparison is added. The outputs were restored from a single clean
pass once the last comparison was in, and from one pass rather than several, so that
every printed number on the page comes from the same execution.

That rule was written after the middle state cost something, and the account is dated
because the figures in it belong to that day and not to now. **On 12 August 2026** the
run saved into this file still printed `50/50 checks reproduce the reported numbers`
while the notebook standing around it had grown to make seven times that many, so a
reader who opened the file without running it read a count short by a factor of seven, in
the one document whose whole job is to be checked. Three sections added on 10 August
carried no saved output at all, so the same reader saw nothing under them and could not
tell an unrun cell from an empty one.

Two properties make the present state the first of the two rather than the middle one
again, and both are read off the file rather than asserted. The execution numbers of the
code cells run consecutively from one with no gaps, which is what one pass leaves behind
and what several passes do not. The few code cells that show nothing are the ones that
define functions and print nothing, rather than cells that went unrun. This prints both,
and no count of them is written here for the reason the section above gives:

```
uv run --no-project --with-requirements ../requirements.txt python3 - <<'EOF'
import json
code = [c for c in json.load(open("counterparty_adverse_selection.ipynb"))["cells"]
        if c["cell_type"] == "code"]
ex = [c.get("execution_count") for c in code]
print(len(code), "code cells;", sum(1 for c in code if c.get("outputs")), "carry output")
print("one pass:", ex == list(range(1, len(ex) + 1)))
print("cells showing nothing:", [i + 1 for i, c in enumerate(code) if not c.get("outputs")])
EOF
```

Nothing about this changes what the notebook does. Run all, and it prints its table.

It is **self-contained**: upload the single `.ipynb` to Google Colab (or open it
anywhere) and *Runtime, then Run all*. Nothing to add by hand. On first run it
downloads about 190 MB from a public Zenodo dataset (DOI 10.5281/zenodo.23540388,
byte-identical to the earlier record 10.5281/zenodo.21820077), three files and no more:

- `notebook_fills.npz`: the per-fill inputs (native block_time, trade
  price, aggressor side, signed pre-trade position, pseudonymous counterparty and
  maker codes), with **no markout precomputed** for the book branch;
- `notebook_book_BTC.npz` / `notebook_book_ETH.npz`: the L2 order-book series
  (timestamp, mid, spread, queue imbalance, microprice), and with them the eight
  order-book features the identity-against-book comparison is measured on (order-flow
  imbalance, a book-based VPIN, queue imbalance at one and at ten levels, bid and ask
  depth within 5 and within 10 basis points). They sit on the book clock and are not
  resampled, so the notebook does the as-of join itself.

The numbers it checks itself against are **not** among them. They are written into a
generated cell just below the imports, and the section after next says why.

The notebook loads the three files, then **recomputes** the book-mid markout term
structure and the order-book features from the raw fills with a no-lookahead as-of join
to the mid series (the `recompute_from_raw` helper in the analysis-functions cell). So
the derived numbers are rebuilt in front of you, not read from a precomputed slice. The
trade-print markout is carried as a committed column in `notebook_fills.npz`, because
recomputing it differs only by an economically-null within-block print-tie ordering.

## The files

`notebook_fills.npz` is built by `../notebook_build/make_notebook_fills.py` from the gitignored
intermediate `quickwin_markouts.npz` plus the native `block_time` clock.
`notebook_book_BTC.npz` / `notebook_book_ETH.npz` are packed by
`../notebook_build/make_notebook_book.py` out of two working files: the mid series `../data/i4_l2_mid.py`
writes from the L2 book archive, and the order-book feature block the comparison node
builds. The shipped copy carries a different name from the working `mid_series_*.npz`
on purpose, because the two hold different columns and one name over two files would
hand the search below the wrong one. All three are gitignored (too large for the
repository) and hosted on
the open Zenodo record so the notebook fetches them with no auth. `ZENODO` in the first
cell points at the record (DOI 10.5281/zenodo.23540388).

The counterparty and maker fields in `notebook_fills.npz` are pseudonyms: the wallet
identifiers are re-indexed to contiguous integers and the hex address map is not
shipped, so the linkage between a code and an address is not distributed here. It
stays derivable by anyone who wants it, because the public source data carry the same
fills with their on-chain addresses: the Hyperliquid node data the fills were built
from, and the open deposit of the same trades by Albers et al.
(DOI 10.5281/zenodo.18184441). The codes can be matched back on coin, timestamp, price
and size. That
is a property of the source being public, not something this file introduces.

To rebuild the per-fill file locally:

```
uv run --no-project --with-requirements ../requirements.txt python3 ../notebook_build/make_notebook_fills.py
```

## Why the reported numbers travel inside the notebook

They used to be fetched alongside the data. A fourth file, `notebook_expected.json`,
sat beside the three above on the public archive, and the first cell downloaded it
whenever it was not already on disk. That arrangement let the figures and the code
that verifies them be of different ages, because they were different files and one of
them lived on a host nothing here could see. On 6 August 2026 they were: the deposited
copy had been published four weeks earlier at 3,713 bytes against the 18,460 the
repository carried, every value in it belonged to a scoring window this study no longer
uses, and a reader following the instructions above got **4 checks of 25** and a failed
assertion in the last cell. Nothing was wrong with the notebook.

A figure and the code that verifies it cannot be of different ages when they travel in
one file. So the values now sit in a generated cell below the imports, written there
from `notebook_expected.json` by `../notebook_build/embed_notebook_expectations.py`, and
`../checks/chk_notebook_expectations.py` compares the embedded copy against that file
leaf by leaf and refuses to let any cell fetch the figures from anywhere else. The three
data files stay on the archive: they are far too large to inline, and all three still
match the deposit byte for byte.

**Changing a committed expectation is therefore a two-step edit inside this repository
and no longer a release.** Rebuild `notebook_expected.json` with
`../notebook_build/make_notebook_data.py`, then run the embedder:

```
uv run --no-project --with-requirements ../requirements.txt python3 \
    ../notebook_build/embed_notebook_expectations.py
uv run --no-project --with-requirements ../requirements.txt python3 \
    ../notebook_build/embed_notebook_expectations.py --check
```

With `--check` nothing is written and the program says whether the cell has fallen
behind its file. Skipping the second step used to leave a Colab run asserting against a
previous Zenodo release while the same notebook passed locally; there is no longer a
remote copy for the two to disagree about.

## What it reproduces

Everything below is recomputed live from the raw fills and the L2 mid series and
compared against the number this work publishes. **How many comparisons that comes to is
printed by the run and is written nowhere in this file**, and the reason is a measured
one rather than a preference: the count moved from 51 to 361 over a single day of work
on 12 August 2026, and every sentence that carried it went wrong at once while still
reading as current.

The notebook is laid out as numbered questions. The first nine are set out here because
they carry the caveats a reader needs, which window, which lens and which population.
The later ones rebuild the decline policy and its size-matched null, the disagreement
between the maker's cost and the counterparty's own profit, the whole-book comparison,
the refusal rule, the flat-surcharge control, the inventory-only quoter, the figure the
report opens with, the persistence read through the book's own mid, and the choice of
scoring window; each says in its own prose what it does and what it ties back to.

- **1. What the flow costs.** Book-mid markout term structure at 1, 10 and 60 s (1.88 /
  2.24 / 2.32 bps), plus the trade print at 10 s (0.52 bps). Those three
  mid figures are the assert targets themselves, `mid_markout_vw.mo1_mid` / `.mo10_mid`
  / `.mo60_mid`, and the same three sit at `level_termstructure.pooled.{1,10,60}.vw` in
  the pipeline's `ws1_horizon_results.json`, which is a second address on the same
  quantity and agrees to nine digits. They rose on 2026-08-02 when the
  entry leg of the join moved onto a snapshot stamped strictly before the fill, so the
  pre-trade mid no longer carries the fill's own impact.
- **2. Whether a counterparty stays toxic.** Persistence of per-counterparty toxicity,
  noise-corrected 0.78 to 0.90, on two coins at two fill floors. This band
  is the **trade-price** measure at the scoring window, from
  `persistence_pooled[*].spearman_disattenuated` in `ks2_persistence_10day_results.json`;
  it is not the book-mid measure used in the bullet above. The same test on the book mid
  runs a little higher, 0.81 to 0.92, at the same key in
  `ks2_persistence_mid_results.json`. The band published earlier, 0.43 to 0.54, is the
  same measure taken at the sixty-second companion window and is not what the notebook
  checks.
- **3. Whether the anonymous book could have told you.** Non-recoverability: surviving
  share 0.83 to 0.88, the extra out-of-sample identity R^2 on each coin at each floor,
  and the thin control's own linear book R^2 under 1 percent.
- **4. What a screen would avoid.** Avoidable cost of $2.38 M pooled, 91.0 percent of it
  avoidable pooled (89.8 percent on BTC, 88.7 percent on ETH) via a held-out top-decile
  screen. **This is the scoring-window cell**, the one the report leads on.
  The sixty-second companion cell sits beside it in the pipeline's `t3_results.json`
  under the unsuffixed keys ($2.55 M pooled, 87.4 percent avoidable) and is not what the
  notebook checks. `make_notebook_data.py` reads the headline-suffixed keys, so the
  assert targets follow the scoring window declared in `settings.py` rather than a typed
  number.
- **5. Whether the cost is concentrated.** Toxicity concentration: Gini 0.51 on BTC, 0.54
  on ETH, 0.54 pooled.
- **6. Whether a passive maker makes money.** Maker net by fee tier, negative at every
  real tier. It is a cost, not an edge. It is taken at the sixty-second
  companion window rather than the scoring window, because the committed value it ties
  back to is the h60 pooled cell of the maker-economics run; the cell says so beside the
  code.
- **7. Whether resolving the counterparty beats book-only quoting.** The bake-off term
  value and its label-shuffle placebo come from a dedicated run and are displayed. What
  the notebook can tie back live is the arithmetic of the placebo itself, that the
  published reduction of +0.32 bps is the observed arm minus the shuffled one.

A few numbers are shown from the committed values because re-running them needs the
whole late tape: the bake-off term value with its placebo in
section 7, and in section 9 the 60-second follow-the-informed test, which asks whether
copying the toxic flow pays and answers no. The full-book incremental fit used to sit in
this list and no longer does: section 12 rebuilds it.
Section 8 is displayed for the same reason: it shows what each of the nine quoters costs
at the base fee tier, and checks the table against itself. The width the equal-width arms
are solved to has to be the solved pass-through times the premium one unit of it buys,
and each quoter's cost at the base tier has to be its cost at the zero-fee tier less the
fee the venue publishes.

## Running it beside this repository instead of in Colab

The first cell looks for each input in the working directory, then in `notebooks/` as
seen from the repository root, then one level up, and downloads only what none of the
three holds. So a run started from this directory finds `notebook_fills.npz` here and
the two `notebook_book_*.npz` files beside it, and fetches nothing at all.
Every path in that search is relative, so the notebook carries no trace of the machine
it was written on. A full pass takes a few minutes.
