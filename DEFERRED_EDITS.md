# Edits that are written down instead of made

An artifact records the hash of the bytes of the script that produced it, so editing a
producer makes a correct artifact stale, and only a run restores the match. For the
heaviest nodes here that run is measured in hours. An edit that changes no computed
figure — a comment, a docstring, a progress line, a rename — therefore costs those hours
and buys nothing.

This file is where such an edit waits. It lands with the next change that reruns that
node anyway, and until then the intent is recorded rather than lost.

`checks/chk_expensive_edits.py` reads this file. A node named here is a declared debt and
the check reports it without failing; a cosmetic edit made in the source and not named
here fails the check. Do not run a node to make that check green — running is the price
the check exists to prevent.

## Format

One line per deferred edit, at the left margin, opening with an open box and the
producer's file name:

    - [ ] `producer.py` — what the edit does, and why it changes no figure.

Tick it when the edit has landed and the node has been rerun for a reason of its own.

Two things about that shape are read by the check and not only by a person. The box must be
open, because ticking it says the debt is spent, and from that moment the name stops
excusing anything. And the line must begin at the left margin, because the sample above is
indented in order to be a sample. Until 2026-08-20 the check stripped each line before
testing it and could tell neither apart: `producer.py`, a file that has never existed in
this repository, was excused on every run, and so were the two entries below that had
already landed.

## Waiting

None.

## Landed

- [x] `build.py` — nine lines of its header docstring showed the run form
  `uv run --no-project --with numpy python3 ...`, which resolves numpy on the day of the
  run: measured on 2026-08-13 it installed 2.5.2 against the 2.4.6 this tree pins, announced
  nothing, and installed no matplotlib. The pinned form
  `uv run --no-project --with-requirements requirements.txt python3 ...` is what
  `README.md` already tells the reader, and it is what those lines now carry. The edit was
  made on 2026-08-13 across forty files and reverted here alone.

  Landed 2026-08-14, and the price that held it back was named wrongly rather than paid.
  The deferral put the cost at "at least 260 minutes over 60 nodes", which is the price of
  a whole build; the price of an edit is what the edit makes stale, and those are different
  questions with different populations. Measured by resolving the committed hash of
  `build.py` by content across the tree: it is recorded in exactly four places, and not one
  of them is worth four hours. `build_results.json` holds it as its producer, and that file
  declares `record_kind: run_journal` with a field of its own saying freshness against the
  producer is not answerable for a journal of a run. `build_diagram_results.json` is the
  only artifact declaring `build.py` among its inputs, it is written by `build_diagram.py`,
  and its recorded runtime is 10.068 seconds. `data_register_results.json` and
  `checks/chk_input_freshness_results.json` carry the hash in their bodies, and neither
  declares `build.py` as an input, so no freshness gate reads it there. The 39 certificates
  in `checks/NEUTRAL_EDITS.json` are spent by a build, not by this edit, and this edit does
  not schedule one.

  It landed with a substantive change to the same file, which is the condition this file
  states for landing: the tape-parser names were made to resolve against the tree instead
  of against a path. So `build_results.json` is owed a run for a reason of its own, and the
  docstring rides along at no added cost. `chk_expensive_edits.py` reads the pair as
  SUBSTANTIVE at 9 minutes and passes.

- [x] `mm_bakeoff.py` — take the selection-floor key off the `glft_q0_spread_vs_as` block,
  or state beside it that the block does not read the floor. Measured 2026-07-31 by pairing
  the artifact against its snapshot across the floor change: sixteen keys vanished and
  sixteen appeared, and they hold the same sixteen values to the last digit, `K10` renamed
  to `K50`. So the label claims the quote spread was computed over the 2069-wallet
  population when the floor never entered it, which is the same defect as a count whose
  predicate cannot fire. Changes no figure, since the values are already proven identical
  across both rungs.

  Landed 2026-08-01, on the run this node was already owed for aligning the two arms of its
  label-shuffle placebo. The floor key is gone rather than annotated: the coin tree now sits
  under `glft_total_spread_bps`, which names the quantity instead of a rung it never read.
  In its place the block carries `rank_floor_independence`, where the claim is MEASURED —
  the view is rebuilt from the context of every rung in `k_list` and compared leaf by leaf,
  and the leaf count, the moved count and the comparator's predicate are all printed. The
  comparator is calibrated under `--selftest` on a pair that must move and a pair that must
  not, plus the two traps that have produced wrong counts here before: a value that stayed
  not-a-number read as a difference, and a renamed key read as no difference at all.

- [ ] `data/panel_rebuild_v2.py` — two comment lines name the directory that builds the notebook's inputs, and it was renamed from `notebook` to `notebook_build` on 2026-08-30 because the tree also holds `notebooks`, which ships the notebook itself and is a different thing. The rename is an address and changes nothing this node computes; the node's recorded run is 3,455 s, so making it in the source would cost that and buy a comment.
