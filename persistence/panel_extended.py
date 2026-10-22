"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-07-29
References: Hyperliquid node-data S3 archive (s3://hl-mainnet-node-data); Zenodo
  18184441 (Albers, Cucuringu, Howison, Shestopaloff, "An Open Book", 2026);
  panel_persistence.py (the estimators reused here, unchanged).
"""

# ---------------------------------------------------------------------------
# PANEL, EXTENDED - same estimators, wider window set, headline horizon.
#
# WHAT THIS ANSWERS. panel_persistence.py reports cross-month persistence on the
# three windows the published work quotes (Aug / Oct / Dec 2025) and reads it at
# the 60-second markout. Two facts make that narrower than the evidence we hold:
#
#   * panel_markouts.npz was rebuilt to EIGHT windows (Aug 2025 .. May 2026,
#     26,035,902 rows). Five of them have never been analysed.
#   * the artifact carries mo1 / mo10 / mo60. The report's headline horizon is
#     10 s, so the panel currently corroborates the headline at a horizon the
#     headline does not use.
#
# This script re-runs the SAME analysis - every estimator is IMPORTED from
# panel_persistence and none is re-derived - over a configurable window set and
# markout column, and writes to its OWN results file. panel_persistence.py and
# its committed panel_persistence_results.json are untouched, so the published
# numbers stay reproducible and these are an ADDITION beside them, never a
# replacement. Reporting both is the point: a robustness result that only exists
# after the scope was widened is worth less than one shown at both scopes.
#
# HOW THE OVERRIDE WORKS. panel_persistence._load_panel is the single place that
# (a) pins CANONICAL_PERIODS and (b) hardcodes the markout column. We substitute a
# loader that differs in exactly those two respects and keeps the store's
# horizon-free "mo_score" key, so every downstream function - _means_and_notional,
# cross_month_cell, the
# split-half reliability, the permutation null, the BH-FDR - runs byte-identical
# code on the wider input. RESULTS_PATH is redirected the same way.
#
# A DECLARED DEBT, OPENED 2026-08-30 AND CARRYING A SIZE THAT MAY ONLY BE LOWERED.
# The seven panel_extended_results_*.json standing in the tree today were written before
# the two records below existed, so each of them names panel_persistence.py as its
# producer and carries no hash of THIS file anywhere. Their numbers are not in doubt and
# their scope is not hidden -- every one of them stamps its window set, window count,
# horizon, markout column and lens as plain fields -- but a reader cannot tell from them
# which version of this wrapper produced them, and no gate can. Regenerating the seven
# costs 1206 seconds by their own recorded run times and moves no published value, which
# is why it is filed as debt rather than done: the record is the only thing that changes.
# Any run made from 2026-08-30 onward closes its own share of this debt automatically.
# SIZE OF THE DEBT ON 2026-08-30: seven artifacts. It may only ever fall.
#
# CONTROL: with --periods canonical --horizon 60 this must reproduce the
# committed panel_persistence_results.json cell for cell. That equivalence is
# the test that the override changed the SCOPE and nothing else; run it before
# trusting any widened number.
#
# Run:
#   uv run --no-project --with-requirements ../requirements.txt python3 panel_extended.py                  # 8 windows, 10 s
#   uv run --no-project --with-requirements ../requirements.txt python3 panel_extended.py --horizon 60     # 8 windows, 60 s
#   uv run --no-project --with-requirements ../requirements.txt python3 panel_extended.py \
#       --periods canonical --horizon 60                                        # the control
# ---------------------------------------------------------------------------

import argparse
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
# The shared modules sit in the repository root, one directory up from this
# group, and this file also imports from the data group. Both are built from this
# file's own location and never from the working directory the run happens to
# start in.
_CODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_CODE_DIR, os.path.join(_CODE_DIR, "data")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import artifact  # noqa: E402
import panel_persistence as pp  # noqa: E402
import settings as H  # noqa: E402

# The column that carries each horizon, BUILT from settings rather than typed, so a
# horizon this script offers on the command line cannot be one the artifact has no
# column for. settings.headline_print_col raises on a horizon outside LADDER_S.
HORIZON_COLUMNS = {h: H.headline_print_col(h) for h in H.LADDER_S}

# This script reads node_fills only, so every column above is a trade print.
LENS = "print"


def make_loader(periods, column):
    """A _load_panel with the window set and markout column made explicit.

    Mirrors pp._load_panel exactly apart from those two choices. The chosen
    column is stored under the horizon-free key "mo_score" because every downstream
    consumer reads that key by name; the two sides must be renamed together or the
    estimators fork, which is the one thing this script must not do.
    """
    def _load(npz_path):
        if not os.path.exists(npz_path):
            raise SystemExit(
                f"[panel-ext] panel npz not found: {os.path.basename(npz_path)}"
                f"\n      build it with panel_persistence.py --build first.")
        z = np.load(npz_path, allow_pickle=False)
        taker_id = z["taker_id"].astype(np.int64)
        coin = z["coin"].astype(np.int8)
        period = z["period"].astype(np.int64)
        mo = z[column].astype(np.float64)
        notional = z["notional"].astype(np.float64)

        keep = np.isin(period, np.asarray(sorted(periods), dtype=np.int64))
        missing = sorted(set(periods) - {int(p) for p in np.unique(period)})
        if missing:
            raise SystemExit(f"[panel-ext] requested window(s) absent from the "
                             f"artifact: {missing}")
        if not bool(keep.all()):
            taker_id, coin, period = taker_id[keep], coin[keep], period[keep]
            mo, notional = mo[keep], notional[keep]

        store, present = {}, []
        for code in np.unique(coin):
            clabel = pp.PANEL_COIN_LABEL.get(int(code), f"coin{int(code)}")
            for per in np.unique(period[coin == code]):
                sel = (coin == code) & (period == per)
                store[(clabel, int(per))] = {
                    "addr": taker_id[sel],
                    "mo_score": mo[sel],
                    "notional": notional[sel],
                }
                present.append((clabel, int(per)))
        return store, present
    return _load


def main():
    ap = argparse.ArgumentParser(
        description="Cross-month persistence on the full panel and at the "
                    "headline horizon. Writes its own results file; never "
                    "overwrites panel_persistence_results.json.")
    ap.add_argument("--horizon", type=int, default=H.HEADLINE_HORIZON_S,
                    choices=sorted(HORIZON_COLUMNS),
                    help=f"markout horizon in seconds (default "
                         f"{H.HEADLINE_HORIZON_S}, the headline)")
    ap.add_argument("--periods", choices=("all", "canonical"), default="all",
                    help="'all' = the eight built windows; 'canonical' = the "
                         "three the published work reports (the control)")
    ap.add_argument("--out", default=None,
                    help="results path override (default panel_extended_"
                         "results_h{H}_{scope}.json)")
    args = ap.parse_args()

    column = HORIZON_COLUMNS[args.horizon]
    periods = (tuple(pp.CANONICAL_PERIODS) if args.periods == "canonical"
               else tuple(pp.PERIODS))
    # A BARE NAME GIVEN TO --out IS RESOLVED HERE, BESIDE THE OTHER RESULTS, AND UNTIL
    # 2026-08-21 IT WAS NOT. The default already joins HERE; `args.out` did not, and a
    # bare name has no directory, so artifact.write fell back to writing beside the
    # PRODUCER -- and the producer of these figures is panel_persistence.py, which sits
    # in another group directory since the August sorting. Measured: rerunning the one
    # artifact this flag exists for, panel_extended_results_h60_canonical_REPEAT.json,
    # created a second copy one directory away while the committed one kept its July
    # timestamp and its stale producer hash. The run reported success and named the file
    # it had written, so nothing on the screen distinguished it from the run that was
    # asked for.
    #
    # The failure is the sharper kind: not a crash, but the same name landing in two
    # directories depending on whether the flag was passed, with the artifact a reader
    # opens left untouched. A path with a directory in it is still honoured as given,
    # since an explicit destination is the whole point of the flag.
    out_path = (args.out if args.out and os.path.dirname(args.out)
                else os.path.join(HERE, args.out) if args.out
                else os.path.join(
                    HERE,
                    f"panel_extended_results_h{args.horizon}_{args.periods}.json"))

    print("=" * 78)
    print(f"[panel-ext] windows : {len(periods)} -> {sorted(periods)}")
    print(f"[panel-ext] horizon : {args.horizon}s (column {column})")
    print(f"[panel-ext] results : {os.path.basename(out_path)}")
    print(f"[panel-ext] estimators imported unchanged from panel_persistence.py")
    print("=" * 78)

    # Redirect the module-level choices, then run the untouched analysis. The two
    # ACTIVE_ variables matter as much as the loader: without them the scope block
    # of the results file would report this file's defaults, so a 10 s run would
    # label itself 60 s and anyone quoting scope would misdescribe it.
    pp._load_panel = make_loader(periods, column)
    pp.ACTIVE_HORIZON_S = args.horizon
    # The column the loader above actually read. The store key is horizon-free, so
    # this is the ONLY place the truth about the column reaches
    # the results file; without it the descriptive slice keys and the scope object
    # string fall back to a guess.
    pp.ACTIVE_MARKOUT_COLUMN = column
    # The reference price. Stated even though it does not change, because the
    # substituted loader is exactly the place a book-mid series would enter, and a
    # lens left unstated is a lens that gets guessed.
    pp.ACTIVE_LENS = LENS
    pp.RESULTS_PATH = out_path
    pp.RESULTS_NAME = os.path.basename(out_path)

    # THIS FILE IS HASHED BY NOTHING, AND UNTIL 2026-08-30 THAT WAS TRUE OF THE
    # ARTIFACTS IT WRITES TOO. The producer record of every panel_extended_results_*.json
    # names panel_persistence.py, because artifact.write is called from that module and
    # records the caller's own __file__. Both freshness gates ask whether the RECORDED
    # producer's bytes moved, so an edit to this file -- the file that decides the window
    # set, the horizon, the markout column and the lens -- stales nothing and no gate
    # says a word. Measured the same day: the name of this file appears in one artifact
    # of the tree, the dependency graph, and its hash appears in none.
    #
    # The repair has to leave panel_persistence.py alone. Eight artifacts record it as
    # their producer and currently match its bytes exactly, so editing it would stale all
    # eight and buy a provenance record with a recompute. So this file declares ITSELF to
    # the writer instead, by wrapping the writer rather than reimplementing it: the
    # wrapper's own bytes become a hashed input, and chk_input_freshness -- which asks
    # about inputs and not about producers -- starts watching the file that sets the
    # scope. One line of intent, no copy of the writer's shape.
    _write_through = pp.write_results

    def _write_declaring_this_wrapper(results, started, settings=None,
                                      extra_meta=None, inputs=None):
        declared = ([pp.PANEL_NPZ_PATH] if inputs is None else list(inputs))
        declared.append(os.path.abspath(__file__))
        return _write_through(results, started, settings=settings,
                              extra_meta=extra_meta, inputs=declared)

    pp.write_results = _write_declaring_this_wrapper

    # What THIS run widened, stamped onto the artifact so a number lifted out of it can
    # never be quoted without the window set and horizon that produced it.
    extended_scope = {
        "windows": sorted(periods),
        "n_windows": len(periods),
        "horizon_s": args.horizon,
        "markout_column": column,
        "measure": "trade-print markout (node_fills); NOT the book-mid measure "
                   "the December headline uses",
        "estimators_from": "panel_persistence.py (imported, unmodified)",
        "produced_by": "panel_extended.py, which substitutes the loader and the output "
                       "name; the producer record names panel_persistence.py because "
                       "the write is called from there, so this field and the hashed "
                       "input beside it are where the wrapper declares itself",
        "canonical_comparison": sorted(pp.CANONICAL_PERIODS),
    }
    # The settings for THIS run. The horizon comes from the command line, so the
    # fingerprint is built from args.horizon and never from the declared headline: a
    # --horizon 60 run must not stamp itself 10 s. is_headline_horizon inside the block
    # therefore reads False on any non-default run, which is the single field that tells
    # a reader whether the number in hand is the headline one or a robustness arm. The
    # window set is also an override, because this script exists to widen it past the
    # three the published analysis pins.
    settings_used = dict(
        h=args.horizon, lens=LENS,
        markout_column=column,
        windows=sorted(periods),
        n_windows=len(periods),
        window_scope=args.periods,
        canonical_windows=sorted(pp.CANONICAL_PERIODS),
        **pp.SETTINGS_OVERRIDES)

    # ONE WRITE, not two. This script used to let analyze_panel write the file and then
    # rewrite it with the two blocks above, so the artifact was produced twice and the
    # second pass had to reproduce what the first had put in _meta -- which is how the
    # producer record came to have more than one home. analyze_panel now takes the
    # writer's arguments and does the single write itself.
    started = artifact.start_clock()
    results = pp.analyze_panel(started=started, settings=settings_used,
                               extra_meta={"extended_scope": extended_scope})
    print(f"[panel-ext] scope stamped -> {os.path.basename(out_path)}")
    return results


if __name__ == "__main__":
    main()
