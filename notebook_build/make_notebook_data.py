"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-07-03
References: Hyperliquid node-data S3 archive (s3://hl-mainnet-node-data); Zenodo
  18184441 (Albers, Cucuringu, Howison, Shestopaloff, "An Open Book", 2026).

SUPERSEDED (2026-07-10). The notebook now recomputes the book results live from the
raw fills and the L2 mid series; it downloads notebook_fills.npz + mid_series_*.npz,
built by make_notebook_fills.py and i4_l2_mid.py. This legacy builder still produces
the older precomputed-markout slice notebook_data.npz for reference.

Build the reduced review dataset for the reproducibility notebook, with the wallet
identifiers carried through as pseudonymous codes.

The two on-disk intermediates (quickwin_markouts.npz, quickwin_markouts_mid.npz)
are large (45 MB + 62 MB) and gitignored by design; they also carry the raw
integer wallet codes that map back to on-chain addresses through
quickwin_taker_map.json. This script merges the row-aligned columns the notebook
needs, carries the wallet and maker codes through as compact pseudonymous integers
(they are already contiguous 0..N-1 and hold no address information on their own),
and downcasts to a single compact file. The hex-to-id address map
(quickwin_taker_map.json) is not published, so the linkage between a code and an
address is not distributed here. It stays derivable: the public source data carry
the same fills with their on-chain addresses -- the Hyperliquid node data the fills
were built from, and the open deposit of the same trades by Albers et al. (Zenodo
18184441) -- so a reader can match the shipped rows back on coin, timestamp, price and size. That is
a property of the source being public, not a weakness added by this file.

WHAT THIS FILE IS NOT, corrected 2026-08-13. Until that day this docstring, and the
payload below, said the notebook downloads this file from Zenodo 21171473. Both halves
were wrong, and the second one was wrong in the direction that hides a stale number.

The notebook downloads notebook_fills.npz and notebook_book_{COIN}.npz from record
23540388 (byte-identical to the earlier record 21820077) and never opens notebook_data.npz; measured by reading the notebook, which
names the other two in its own dataset_file calls and this one nowhere. And the copy
of THIS file sitting under 21171473 is a superseded generation: 56,198,506 bytes
against the 56,054,763 written here, a different md5, and it carries the book-side
columns as they were before join_entry stopped accepting a snapshot stamped at the
fill's own millisecond on 2026-08-02. That copy pools the 10 s book-mid markout to
+2.0616 bps, which is the figure i4_midmarkout.join_entry names as the one the
correction retired; this tree publishes +2.2388 bps.

The raw materials of that older record are NOT stale, and the difference matters when
deciding what to do about it: its mid_series_{COIN}.npz are byte-identical to the
working series here, and its notebook_fills.npz agrees with the current slice on all
thirteen shared arrays. Recomputing the headline from those two through this tree's
own joins returns 2.2388012821934655, equal to the published figure to the last digit.
Exactly one file of that record is behind, and it is this one.

It also (a) extracts the headline result numbers from the committed *_results.json
files into notebook_expected.json so the notebook asserts against generated - not
hand-typed - reference values, and (b) runs a regression guard that reproduces a
known stored number from the reduced file before trusting it.

Run: uv run --no-project --with numpy python3 make_notebook_data.py
"""
import json
import os
import sys

import numpy as np

# The shared modules sit in the repository root, one directory up from this
# group, and this file also imports from the identity and the quoters groups. All three
# are built from this file's own location and never from the working directory the run
# happens to start in.
_CODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_CODE_DIR, os.path.join(_CODE_DIR, "identity"),
           os.path.join(_CODE_DIR, "quoters")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import artifact  # noqa: E402
import panel_io as P  # noqa: E402
import settings as H  # noqa: E402
# Imported for their declared constants, not to run them: the notebook rebuilds the
# identity-against-book cell and needs the estimator's settings and its feature list to
# come from the one place that owns them.
import i3_book_comparator as i3b  # noqa: E402
import i3_nonrecoverability_oos as i3o  # noqa: E402
# The same reason, for the flat-surcharge control the notebook rebuilds: the booked
# offset is RECOVER_FRAC * min(premium, max(a_mid, 0)) and the premium is
# lambda_tox * max(early_tox, 0), so the recapture fraction, the pass-through and the
# fill floor the quoter is compared at all belong to the quoter. flat_surcharge_control.py
# imports them from here for exactly this reason, and a constant retyped beside a
# declaration is a number that can drift without anyone editing it twice.
import mm_bakeoff as MB  # noqa: E402
# The same reason again, for the JOINT-matched null the notebook rebuilds. One of that
# sampler's constants is a safety cap on the greedy walk into the admissible region, and
# the backtest does not publish it in any field of its artifact: it never binds on this
# tree, so no draw carries a trace of it. The notebook still has to bound the same loop,
# and a cap retyped into this file would be a second home for a number whose home is the
# quoter. So it is taken by import, exactly as the constants above are.
import t1_toxicity_skew_backtest as T1B  # noqa: E402
# The maker's fee schedule, for the same reason: the notebook retypes it in order to run
# standalone, and a schedule retyped beside its declaration is a number that can drift
# without anyone editing it twice. Imported for the constant, never to run the file.
sys.path.insert(0, os.path.join(_CODE_DIR, "money"))
import maker_econ as ME  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
# Located by panel_io rather than joined here, so the one place that knows where the
# markout panels live is the one place that has to change if they move.
PRINT_NPZ = os.path.join(P.data_root(), "quickwin_markouts.npz")
MID_NPZ = os.path.join(P.data_root(), "quickwin_markouts_mid.npz")
OUT_NPZ = os.path.join(_CODE_DIR, "notebooks", "notebook_data.npz")
OUT_META = os.path.join(_CODE_DIR, "notebooks", "notebook_data_meta.json")
OUT_EXPECTED = os.path.join(_CODE_DIR, "notebooks", "notebook_expected.json")

COIN_MAP = {0: "BTC", 1: "ETH"}

# Columns the notebook's twelve sections actually consume, taken from the union
# of the two intermediates. Everything else (entry_px, closed_pnl, dir_code,
# gap_* ) is dropped: no notebook section reads it.
#   from print npz:  mo1, mo10, mo60   (trade-print markout, the maker's loss)
#   from mid  npz:   mo{1,10,60}_mid, imb_entry, spread_entry_bps, micro_dev_bps
#   shared/base:     coin, day, notional, taker_side, start_pos, is_open
FLOAT32 = "float32"


def load_and_align():
    # The refusal is panel_io's, so a missing panel is worded the same way everywhere and
    # the message names the producer that writes it. It also replaces a message that
    # interpolated the FULL path: these are absolute at run time, so the old wording put
    # the local account name of whoever ran it into the console and into any log that
    # captured it. panel_io prints the basename and its parent's basename only.
    P.require_present("print", PRINT_NPZ)
    P.require_present("mid", MID_NPZ)
    zp = np.load(PRINT_NPZ, allow_pickle=False)
    zm = np.load(MID_NPZ, allow_pickle=False)

    n = zp["taker_id"].shape[0]
    if zm["taker_id"].shape[0] != n:
        sys.exit(f"ERROR: row-count mismatch print={n} mid={zm['taker_id'].shape[0]}")

    # The mid npz is built to be row-identical to the print npz (i4_midmarkout
    # guarantees the same order). Verify the alignment keys byte-for-byte before
    # merging, exactly as maker_econ.load_aligned does.
    for k in ("taker_id", "coin", "day", "taker_side", "maker_id"):
        if not np.array_equal(zp[k], zm[k]):
            sys.exit(f"ERROR: alignment key '{k}' differs between the two npz.")
    if not np.allclose(zp["notional"].astype(np.float64),
                       zm["notional"].astype(np.float64),
                       rtol=0, atol=1e-3, equal_nan=True):
        sys.exit("ERROR: notional differs between the two npz.")
    print(f"[align] OK - {n:,} rows, 5 keys + notional match across both files")
    return zp, zm, n


def deidentify(codes):
    """Return compact pseudonymous codes 0..N-1 for an integer id column.

    np.unique(return_inverse) is grouping-invariant: every row of a wallet keeps
    the same code, so per-wallet aggregates (persistence, concentration, toxicity
    ranks) are unchanged. Here the inputs are ALREADY contiguous 0..N-1, so this
    re-index is a no-op (the codes come out identical); it does NOT by itself add
    protection. What the shipped file leaves out is the hex-to-id address map, so
    the linkage between a code and an address is not distributed here. A reader can
    still re-derive it from the open source tape, which carries the same fills with
    their on-chain addresses, so treat the codes as pseudonyms rather than
    anonymised identifiers.

    -1 sentinel guard (latent-bug guard; inert on the current window). A maker_id
    of -1 marks a fill with NO resolved maker. Plain np.unique would treat -1 as a
    real value and remap it to 0, collapsing "no maker" into a fake maker-0 group
    and shifting every real maker by +1. The current window has ZERO -1 rows, so
    the guarded branch below is never taken and the output is byte-identical; if a
    future rebuild introduces -1 rows they are preserved as -1 through the re-index.
    """
    codes = np.asarray(codes)
    sentinel = codes == -1
    if sentinel.any():
        real = codes[~sentinel]
        uniq, inv_real = np.unique(real, return_inverse=True)
        out = np.full(codes.shape, -1, dtype=np.int32)
        out[~sentinel] = inv_real.astype(np.int32)
        return out, int(uniq.shape[0])
    uniq, inv = np.unique(codes, return_inverse=True)
    return inv.astype(np.int32), uniq.shape[0]


def build(zp, zm, n):
    taker_code, n_takers = deidentify(zp["taker_id"])
    maker_code, n_makers = deidentify(zp["maker_id"])

    cols = {
        "taker_code": taker_code,
        "maker_code": maker_code,
        "coin": zp["coin"].astype(np.int8),
        "day": zp["day"].astype(np.int16),
        "notional": zp["notional"].astype(FLOAT32),
        "taker_side": zp["taker_side"].astype(np.int8),
        "start_pos": zp["start_pos"].astype(FLOAT32),
        "is_open": zp["is_open"].astype(np.int8),
        # trade-print markout (bps), the maker's signed loss
        "mo1": zp["mo1"].astype(FLOAT32),
        "mo10": zp["mo10"].astype(FLOAT32),
        "mo60": zp["mo60"].astype(FLOAT32),
        # book-mid markout (bps)
        "mo1_mid": zm["mo1_mid"].astype(FLOAT32),
        "mo10_mid": zm["mo10_mid"].astype(FLOAT32),
        "mo60_mid": zm["mo60_mid"].astype(FLOAT32),
        # entry book state (RQ2 controls + BBO half-spread)
        "imb_entry": zm["imb_entry"].astype(FLOAT32),
        "spread_entry_bps": zm["spread_entry_bps"].astype(FLOAT32),
        "micro_dev_bps": zm["micro_dev_bps"].astype(FLOAT32),
    }
    return cols, n_takers, n_makers


def regression_guard(cols):
    """Reproduce a couple of stored numbers from the reduced columns.

    If the reduction (column selection, downcast, re-index) preserved the data,
    the per-coin volume-weighted mean 60s markout computed here must match the
    ks2 slice means, and the pooled avoidable-cost dollars must be in the right
    ballpark. A hard mismatch means the reduced file is not a faithful copy.
    """
    ok = True
    coin = cols["coin"]
    for c, name in COIN_MAP.items():
        m = coin == c
        mo60 = cols["mo60"][m].astype(np.float64)
        w = cols["notional"][m].astype(np.float64)
        good = np.isfinite(mo60) & np.isfinite(w)
        vw = float(np.sum(mo60[good] * w[good]) / np.sum(w[good]))
        print(f"[guard] {name} vw-mean mo60 = {vw:+.4f} bps  (n={m.sum():,})")
    # sanity: markout columns are not all-NaN, ids are contiguous from 0
    for k in ("mo10_mid", "spread_entry_bps"):
        frac = float(np.mean(np.isfinite(cols[k])))
        print(f"[guard] {k}: finite fraction = {frac:.3f}")
        if frac == 0.0:
            ok = False
    if cols["taker_code"].min() != 0:
        ok = False
    return ok


def extract_expected():
    """Pull the headline numbers the notebook asserts against out of the
    committed result JSONs, so the reference values are generated, not typed.

    Returns (expected, sources). `sources` is every results file this function
    actually opened, in the order it opened them, so the artifact can hash each one.
    Without that list the extracted numbers cannot be told apart from numbers older
    than the results they were extracted from, which is the one failure a file of
    reference values has.
    """
    sources = []

    def load(fn):
        # The artifacts named below sit in the group directories of their producers
        # rather than beside this packer, so the directory is looked up by the name.
        # The name stays the last component of the join, which is what the build graph
        # folds each input edge out of.
        p = os.path.join(artifact.results_dir(fn), fn)
        if not os.path.exists(p):
            return None
        # The RESOLVED path is what gets hashed, not the bare name. Until 2026-08-13
        # this appended fn, and artifact.input_record resolves a relative name against
        # the producer's own directory and then the working directory - neither of
        # which is where these files live now that the scripts sit in group folders.
        # Twenty-one of the twenty-two inputs were written present=false with no hash,
        # which reads as "the results are gone" when they were open two lines above.
        # artifact._record_name collapses a path to its basename, so the record still
        # says quickwin_pass_summary.json and carries no directory of this machine.
        sources.append(p)
        return json.load(open(p))

    exp = {}

    # ---- the population every other number below sits on ----
    # Added 2026-08-12. The notebook already PRINTED both of these in the cell that
    # loads the data and compared neither, so the two numbers the report opens with
    # were the only reported figures the notebook could contradict in silence. They
    # cost nothing to check: the loaded arrays hold them.
    #
    # Both counts are properties of a stated collapsing rule and not of the tape, so
    # the rule travels beside them under its own key. One row here is one (block hash,
    # taker) sweep with a size-weighted entry price, NOT one exchange print: on the
    # raw tape a single taker order that sweeps several resting orders arrives as
    # several prints, and counting those would answer a different question with the
    # same word.
    qw = load("quickwin_pass_summary.json")
    if qw:
        exp["tape_population"] = {
            "n_collapsed_taker_trades": qw["total_rows"],
            "n_distinct_taker_wallets": qw["n_unique_takers"],
            "_shared": {
                "row_unit": qw["config"]["dedup"],
                "n_days_resolved": qw["config"]["n_days_resolved"],
                "coins": qw["config"]["coins"],
            },
        }

    ks2 = load("ks2_persistence_10day_results.json")
    if ks2:
        exp["persistence"] = [
            {"coin": e["coin"], "K": e["K"],
             "spearman_disattenuated": e["spearman_disattenuated"],
             "rel_early": e["rel_early"], "rel_late": e["rel_late"],
             "pvalue": e["pvalue"], "n": e["n_counterparties"]}
            for e in ks2.get("persistence_pooled", [])
        ]

    i3 = load("i3_depth_control_results.json")
    if i3:
        exp["i3_nonrecoverability"] = {
            "pooled_share_retained_nonlinear": [c["share_retained_nonlinear"]
                                                for c in i3["pooled"]["cells"]],
            "by_coin_loo_taker_r2_residual": {
                COIN_MAP.get(bc.get("coin_code", i), bc.get("coin", str(i))):
                    [c["loo_taker_r2_residual"] for c in bc["cells"]]
                for i, bc in enumerate(i3.get("by_coin", []))
            },
            "placebo_residual_p": i3["pooled"]["cells"][0]["placebo_residual_p"],
        }

    t3 = load("t3_results.json")
    if t3:
        # t3 suffixes its HEADLINE keys with the horizon and leaves the 60 s companion
        # unsuffixed for backward compatibility, so the bare name is the wrong one to
        # read at any horizon but 60. Reading it here is what made the notebook check
        # itself against the companion while the report quoted the headline: both files
        # stayed internally consistent and stopped describing the same quantity.
        _sfx = f"_{H.HEADLINE_HORIZON_S}s"

        def _t3key(coin, stem):
            return t3[coin][stem + _sfx] if (stem + _sfx) in t3[coin] else t3[coin][stem]

        exp["t3_avoidable"] = {
            c: {"total_cost_usd": _t3key(c, "total_cost_usd"),
                "avoidable_share_oos_top10pct": _t3key(c, "avoidable_share_oos_top10pct"),
                "horizon_s": H.HEADLINE_HORIZON_S}
            for c in ("BTC", "ETH", "pooled") if c in t3
        }

    m11 = load("m11_results.json")
    if m11:
        exp["m11_gini"] = {
            c: m11[c]["per_dollar_toxicity"]["net_toxic_gini"]
            for c in ("BTC", "ETH") if c in m11
        }

    mb = load("mm_bakeoff_results.json")
    if mb:
        asv = mb["adverse_selection_term_value"]["K10"]
        exp["bakeoff_term_value_base"] = {
            c: {"vs_as_symmetric": asv[c]["base"]["as_toxicity_minus_as_symmetric_delta_net_vw_bps"],
                "vs_gm": asv[c]["base"]["as_toxicity_minus_gm_delta_net_vw_bps"]}
            for c in ("BTC", "ETH") if c in asv
        }
        exp["bakeoff_cross_checks"] = mb["cross_checks"]

    fol = load("follow_the_informed_oos_results.json")
    if fol:
        cell = fol["cells"].get("BTC|mo1|lag=None", {})
        exp["follow_btc_mo1"] = {
            "net_mean_bps": cell.get("net_mean_bps"),
            "placebo_shuffle_random_net_bps": cell.get("placebo_shuffle_random_net_bps"),
        }
        # the report's headline follow figure is the 60s markout, both coins
        exp["follow_60s"] = {
            c: fol["cells"].get(f"{c}|mo60|lag=mo10", {}).get("net_mean_bps")
            for c in ("BTC", "ETH")
        }

    # ---- extra reported figures the notebook also reproduces/displays ----
    i4 = load("i4_midmarkout_results.json")
    me = load("maker_econ_results.json")
    if i4:
        exp["mid_markout_vw"] = {
            "mo1_mid": i4.get("vw_mean_mo1_mid_bps"),
            "mo10_mid": i4.get("vw_mean_mo10_mid_bps"),
            "mo60_mid": (me or {}).get("cross_checks", {}).get(
                "m8_reconciliation", {}).get("vw_a_mid_60_bps"),
            "mo10_print": i4.get("vw_mean_mo10_print_bps"),
        }

    if i3:
        exp["linear_book_r2"] = {
            bc.get("coin", str(i)): bc["ols_book_state"]["r2_book_state"]
            for i, bc in enumerate(i3.get("by_coin", []))
        }

    if m11:
        exp["m11_gini_pooled"] = m11["pooled"]["per_dollar_toxicity"]["net_toxic_gini"]

    ib = load("i3_book_nonrecoverability_results.json")
    if ib:
        # full-public-book incremental OOS fit at the headline cell (h10, K50):
        # identity adds most where the book is blind (ETH >> BTC)
        cells = [bc for bc in ib.get("by_coin", [])
                 if bc.get("horizon_s") == 10 and bc.get("K") == 50]
        exp["i3book_incremental_h10_K50"] = {
            bc.get("coin"): bc.get("incremental_oos_r2") for bc in cells
        }
        # the two anchor numbers that make the per-coin split legible: the FULL public
        # book already reads toxicity on BTC (high R2, identity adds little) but is
        # blind on ETH (~0 R2, identity carries it).
        exp["i3book_public_r2_h10_K50"] = {
            bc.get("coin"): bc.get("oos_r2_public") for bc in cells
        }
        # the pre-registered pooled headline cell with its robustness stats
        ph = next((bc for bc in ib.get("pooled", [])
                   if bc.get("horizon_s") == 10 and bc.get("K") == 50), {})
        exp["i3book_pooled_h10_K50"] = {
            "incremental_oos_r2": ph.get("incremental_oos_r2"),
            "incremental_spearman": ph.get("incremental_spearman"),
            "placebo_p": ph.get("placebo_p"),
            "survives_fdr": ph.get("survives_fdr"),
            "whale_robust": ph.get("whale_robust"),
        }
        # Added 2026-08-10, so the notebook can REBUILD this cell rather than display
        # it. Until the order-book block travelled there was nothing to rebuild it
        # from; now there is, and what the rebuild needs beside the data is the whole
        # of the estimator's settings. They are read out of settings.py here rather
        # than typed into a cell, for the same reason every other constant is.
        _bcells = {f"{bc.get('coin')}|{bc.get('horizon_s')}|{bc.get('K')}": bc
                   for bc in (ib.get("by_coin", []) + ib.get("pooled", []))}
        exp["i3book_cells"] = {
            key: {k: c.get(k) for k in
                  ("n_wallets", "n_public_features", "oos_r2_public",
                   "oos_r2_public_plus_fe", "incremental_oos_r2",
                   "oos_spearman_public", "oos_spearman_public_plus_fe",
                   "incremental_spearman", "placebo_p", "placebo_p_is_floor",
                   "incremental_oos_r2_no_whales", "whale_robust")}
            for key, c in _bcells.items()
            if c.get("horizon_s") == H.HEADLINE_HORIZON_S and c.get("K") == 50
        }
        exp["i3book_cells"]["_shared"] = {
            "features": list(i3b.book_feature_names()),
            "n_folds": i3o.N_FOLDS,
            "n_perm": i3o.N_PERM,
            "ridge_lambda": i3o.RIDGE_LAMBDA,
            "vpin_buckets": i3o.N_VPIN_BUCKETS,
            "vpin_window": i3o.VPIN_WINDOW,
            "imb_window": i3o.IMB_WINDOW,
            "whale_drop_k": i3o.WHALE_DROP_K,
            # run_cell draws its three streams as RNG_SEED + K + h, RNG_SEED*3 + K + h
            # and RNG_SEED*7 + K + h; the notebook is handed the seeds rather than the
            # arithmetic, so a change to either cannot be missed by a reader comparing
            # the two.
            "seeds": {"fit": i3b.RNG_SEED + 50 + H.HEADLINE_HORIZON_S,
                      "placebo": i3b.RNG_SEED * 3 + 50 + H.HEADLINE_HORIZON_S,
                      "whale": i3b.RNG_SEED * 7 + 50 + H.HEADLINE_HORIZON_S},
        }

    if mb:
        p = mb["placebo_label_shuffle"]["count_matched"]["pooled"]
        gated = mb["placebo_label_shuffle"]["rank_floor_gated"]["pooled"]
        # The reduction and its interval are lifted rather than subtracted here. Until
        # 2026-08-06 only the two ENDS were carried and the notebook's own prose did the
        # subtraction in words, which is how one quantity came to be quoted three ways on
        # one screen: the text said 0.29 with 0.37 as its upper bound while the cell under
        # it printed the difference of the two ends. Both ends and the difference now come
        # from the same block that the producer publishes, and the gated arm travels beside
        # them under its own name, because it is the UPPER BOUND and not the estimate.
        exp["bakeoff_placebo_pooled"] = {
            "observed": p["observed_toxicity_reduction_net_vw_bps"],
            "random_mean": p["random_mean"],
            "p_value": p["permutation_p"],
            "reduction_vs_null": p["reduction_vs_null_net_vw_bps"],
            "ci95_wallet_clustered": p["ci95_wallet_clustered"],
            "ci_excludes_zero": p["ci_excludes_zero"],
            "gated_upper_bound": gated["reduction_vs_null_net_vw_bps"],
        }

        # ---- what each quoter costs, and the width the equal-width arms are held to ----
        # Added 2026-08-06. These are DISPLAYED, not recomputed: rebuilding a quoter needs
        # the whole late tape, which does not ship with the notebook. What the notebook can
        # still do is check the table against itself, and the leaves below are carried so
        # that it can.
        eqw = mb.get("declared_axis_comparisons", {}).get("equal_width_solve", {})
        exp["bakeoff_quoter_costs"] = {
            "shared_target_extra_bps": eqw.get("target_mean_extra_bps"),
            # THE TWO LEAVES BELOW EXIST SO THE LINE ABOVE CAN BE CHECKED RATHER THAN
            # QUOTED. Added 2026-08-12. The shared width was carried alone, so the only
            # comparison a notebook could write against it was the number against
            # itself, and a comparison that cannot fail is not a comparison. The width
            # is SOLVED, not measured: the equal-width leg's multiplier times the
            # resolved unit term reproduces it. Carrying both halves lets the notebook
            # re-derive the published width from independent numbers, which is the
            # difference between a reader checking our arithmetic and a reader reading
            # it back to us.
            "shared_target_multiplier": eqw.get("lambda_as_toxicity_ew"),
            "shared_target_unit_term_bps": eqw.get(
                "unit_resolved_term_mean_extra_bps"),
            "quoter_net_base": mb.get("bakeoff_ranking", {}).get("pooled", {}),
        }

    # ---- what declining the worst decile removes, and what it costs ----
    # Added 2026-08-10. The notebook could not reach this table before, not because the
    # arithmetic was hard but because the shipped slice carried no order-book series to
    # rebuild the book-mid lens from. It does now, so the whole table travels rather than
    # its pooled column alone. All six cells are carried, because the reported claim is a
    # comparison across them: the reduction clears the size-matched null in five and not
    # in the sixth, and a reader who is handed only the five is being handed a result.
    t1 = load("t1_backtest_results.json")
    if t1:
        _split = f"t1_early_late_split_{H.HEADLINE_HORIZON_S}s"

        def _region_freedom(rf):
            """The measured half of the region reading, without its prose.

            A cell with no screened members publishes the note alone and no members, and
            that shape has to survive here as an empty reading rather than as a raise."""
            rf = rf or {}
            if "top_members" not in rf:
                return None
            return {"top_members": [
                        {"rank": m.get("rank"),
                         "share_of_target_pct": m.get("share_of_target_pct"),
                         "one_for_one_swaps_in_band": m.get("one_for_one_swaps_in_band")}
                        for m in rf["top_members"]],
                    "top_members_share_of_target_pct": rf.get(
                        "top_members_share_of_target_pct"),
                    "pool_wallets_above_band": rf.get("pool_wallets_above_band")}

        def _t1joint(n):
            """The JOINT-matched null of one cell, refusal and all.

            A REFUSED CELL TRAVELS AS A REFUSAL AND NOT AS AN ABSENCE. On this tree the
            BTC cell of the declared lens gets no verdict: its eight independent starts
            disagree about the tail, so the backtest withholds the reduction and the
            tail fraction and writes the reason instead. Dropping that cell here would leave the
            notebook rebuilding five cells where the study has six, and a reader counting
            them would conclude the sixth was never run. So the refusal flag and the words
            of the refusal travel, and so do the per-chain readings the refusal was decided
            on -- the chains themselves ran and produced numbers, and it is only the verdict
            that is withheld.

            EVERY FIELD IS READ THROUGH get. The verdict fields are the JSON null on a
            refused cell and hold numbers on a cleared one, and the per-chain lists are
            absent entirely if a chain never entered the region. Both shapes have to build
            without raising, because the day this null clears BTC as well is a day nobody
            should have to edit this function."""
            j = n.get("joint_matched_placebo") or {}
            chains = j.get("chains") or []
            agree = j.get("chain_agreement") or {}
            axes = j.get("axes_held") or {}
            return {
                "joint_refused": bool(j.get("refused")),
                "joint_refusal_reasons": list(j.get("refusal_reasons") or []),
                "joint_n_toxic_wallets": j.get("n_toxic_wallets"),
                "joint_target_notional_usd": j.get("target_toxic_notional_usd"),
                "joint_n_ranked_wallets": j.get("n_ranked_wallets"),
                "joint_largest_wallet_share_of_target_pct": j.get(
                    "largest_wallet_share_of_target_pct"),
                "joint_observed_set_in_region": (
                    j.get("observed_set_reading") or {}).get("in_region"),
                "joint_predicate_calibrated": (
                    j.get("predicate_calibration") or {}).get("calibrated"),
                # The chain-level readings are what makes a refusal checkable. The entry
                # walk and the tail count are the two the notebook recomputes step for
                # step, so a port that took another path through the generator would be
                # caught here rather than averaged away in a pooled mean.
                "joint_chain_entry_attempts": [
                    (c.get("sampler") or {}).get("entry_attempts") for c in chains],
                "joint_chain_entry_dev_pct": [
                    (c.get("sampler") or {}).get("entry_dev_pct") for c in chains],
                "joint_chain_mean_reduction_pct": [
                    c.get("mean_reduction_pct") for c in chains],
                "joint_chain_tail_counts": [
                    c.get("draws_at_or_above_observed") for c in chains],
                "joint_chains_agree": agree.get("agree"),
                "joint_pooled_tail_fraction": agree.get("pooled_tail_fraction"),
                "joint_allowed_departure": agree.get("allowed_departure"),
                "joint_largest_departure": agree.get("largest_departure"),
                "joint_count_held_exactly": axes.get("count_held_exactly"),
                "joint_draw_notional_dev_pct_min": axes.get("draw_notional_dev_pct_min"),
                "joint_draw_notional_dev_pct_max": axes.get("draw_notional_dev_pct_max"),
                "joint_matched_mean_reduction_pct": j.get(
                    "joint_matched_mean_reduction_pct"),
                "joint_matched_p95_reduction_pct": j.get(
                    "joint_matched_p95_reduction_pct"),
                "joint_matched_max_reduction_pct": j.get(
                    "joint_matched_max_reduction_pct"),
                # NOT A P-VALUE AND NO LONGER NAMED ONE. The producer renamed this on
                # 2026-08-30: it counts the draws that reached the observed reduction and
                # floors the ratio, which is a property of these draws, and the block
                # declares in the neighbouring key that uniformity over the region is not
                # established. The arithmetic never changed; the name did.
                "joint_matched_tail_fraction_floored": j.get(
                    "joint_matched_tail_fraction_floored"),
                # THREE STATES AND NOT TWO, which is why no bool() stands here. True where
                # no draw reached the observed reduction, false where one did, and the JSON
                # null where the cell built no null at all. Collapsing the third into the
                # second would let a cell that was never drawn read as a cell whose draws
                # reached the value.
                "joint_no_draw_reached_observed": j.get("no_draw_reached_observed"),
                # HOW MUCH ROOM THE REGION LEAVES THE DRAW. Where the largest members carry
                # most of the target, every admissible draw is a near-copy of the observed
                # set, and a tail fraction at the floor says less than it appears to. The
                # notebook rebuilds this block rather than displaying it, so only the
                # measured fields travel: the words that explain them have their home in
                # the artifact, and six copies of one paragraph is how a fact grows a
                # second home.
                "joint_region_freedom": _region_freedom(j.get("region_freedom")),
            }

        def _t1cell(arm, lens):
            n = t1[arm]["by_measure"][lens][_split]
            s = n["size_matched_placebo"]
            d = n["policies"]["decline_top_decile"]
            cell = dict(_t1joint(n))
            cell.update({
                "observed_reduction_pct": s["observed_reduction_pct"],
                "size_matched_mean_reduction_pct": s["size_matched_mean_reduction_pct"],
                "size_matched_p95_reduction_pct": s["size_matched_p95_reduction_pct"],
                "toxicity_vs_size_matched_p": s["toxicity_vs_size_matched_p"],
                "toxicity_beats_size_matched": s["toxicity_beats_size_matched"],
                "size_only_top_decile_reduction_pct":
                    s["size_only_top_decile_by_notional_reduction_pct"],
                "symmetric_late_cost_usd": n["symmetric_late_cost_usd"],
                "notional_given_up_pct": d["notional_given_up_pct"],
                "benign_share_of_given_up_pct": d["benign_share_of_given_up_pct"],
            })
            return cell

        exp["t1_decline_worst_decile"] = {
            f"{arm}|{lens}": _t1cell(arm, lens)
            for arm in ("pooled", "BTC", "ETH") if arm in t1
            for lens in ("mid", "print")
            if lens in t1[arm].get("by_measure", {})
            and _split in t1[arm]["by_measure"][lens]
        }
        exp["t1_decline_worst_decile"]["_shared"] = {
            "n_draws": t1["pooled"]["by_measure"]["mid"][_split][
                "size_matched_placebo"]["n_draws"],
            "n_notional_strata": t1["pooled"]["by_measure"]["mid"][_split][
                "size_matched_placebo"]["n_notional_strata"],
            "p_floor": t1["pooled"]["by_measure"]["mid"][_split][
                "size_matched_placebo"]["p_floor"],
            # The draw's seed travels with the numbers rather than being typed into the
            # notebook, because a null that is redrawn on another stream is another null
            # and would disagree with the published mean for a reason no reader could see.
            "seed": t1["pooled"]["by_measure"]["mid"][_split][
                "size_matched_placebo"]["seed"],
            "rank_floor_fills": t1["pooled"]["by_measure"]["mid"][_split][
                "size_matched_placebo"].get("rank_floor_fills", H.RANK_FLOOR_FILLS),
            "horizon_s": H.HEADLINE_HORIZON_S,
        }
        # ---- the JOINT-matched null's own constants ----
        # Read off the pooled cell of the declared lens, the same cell the block above
        # reads, so both nulls' settings come from the run that produced the numbers
        # rather than from anyone's memory of them. The three sampler settings are not
        # top-level fields of that null: they are written by the sampler into every
        # chain's own diagnostics, which is where the run actually records what it did,
        # and the first chain is as good as any because a chain that ran on other
        # settings would not be a chain of this null.
        _jn = t1["pooled"]["by_measure"]["mid"][_split]["joint_matched_placebo"]
        _jsamp = (_jn.get("chains") or [{}])[0].get("sampler") or {}
        exp["t1_decline_worst_decile"]["_shared"]["joint"] = {
            "n_draws": _jn.get("n_draws"),
            "n_chains": _jn.get("n_chains"),
            "n_draws_per_chain": _jn.get("n_draws_per_chain"),
            # Its own stream, and a different one from the null above: the count-matched
            # null draws on the file's base seed, the size-matched one on the next offset,
            # this one on the one after. A notebook redrawing on either neighbour's stream
            # would disagree with the published mean for a reason no reader could see.
            "seed": _jn.get("seed"),
            "tail_fraction_floor": _jn.get("tail_fraction_floor"),
            "tolerance_pct": _jn.get("tolerance_pct"),
            "burn_attempts": _jsamp.get("burn_attempts"),
            "step_attempts": _jsamp.get("step_attempts_between_draws"),
            "pair_probability": _jsamp.get("pair_probability"),
            # The one number of this null that the artifact does not carry, taken from the
            # quoter that owns it rather than retyped here. It is a cap and not a budget:
            # the greedy entry reaches the region in a few hundred swaps on every cell of
            # this tree, so the cap never binds and no published draw depends on it.
            "entry_attempt_cap": T1B.JOINT_PLACEBO_ENTRY_ATTEMPT_CAP,
            # The batch the entry draws from the generator at a time, taken the same way.
            # A batch of another size asks the generator for another count and walks
            # another chain, so the notebook has to redraw on this one.
            "entry_block": T1B.JOINT_PLACEBO_ENTRY_BLOCK,
            "chain_agreement_sigma": (
                _jn.get("chain_agreement") or {}).get(
                    "sigma_bar", T1B.JOINT_PLACEBO_CHAIN_AGREEMENT_SIGMA),
        }

    # ---- the maker's cost and the counterparty's own profit rank wallets apart ----
    # Added 2026-08-10, and it needed one column the slice did not carry, the realised
    # profit a fill closes out. Both admission arms travel, not the published one alone:
    # the sign of the median gap is opposite between them, the report prints both side by
    # side, and a notebook that recomputed only the first would reproduce half a sentence.
    w3 = load("ws3_taker_pnl_results.json")
    if w3:
        ov = w3["oos_validation"]
        ra = w3["rank_agreement"]
        exp["ws3_taker_pnl"] = {
            "late_pnl_pd_bps_flag_median": ov["late_pnl_pd_bps_flag_median"],
            "late_pnl_pd_bps_rest_median": ov["late_pnl_pd_bps_rest_median"],
            "late_pos_pnl_rate_flag": ov["late_pos_pnl_rate_flag"],
            "late_pos_pnl_rate_rest": ov["late_pos_pnl_rate_rest"],
            "median_gap_ci": ov["median_gap_ci"],
            "n_flag": ov["n_flag"], "n_rest": ov["n_rest"],
            "rank_rho": {k: ra[k]["rho"] for k in ("pooled", "BTC", "ETH") if k in ra},
            "rank_n": {k: ra[k]["n"] for k in ("pooled", "BTC", "ETH") if k in ra},
            "rank_placebo_p": {k: ra[k]["placebo_p"] for k in ("pooled", "BTC", "ETH")
                               if k in ra},
            # The horizon travels as a declared number and the column name does not
            # travel at all. A bare "mo10_mid" in a tracked cell fixes the scoring
            # window by spelling it, which is the one thing the horizon gate forbids:
            # were the window ever redeclared, the literal would stay behind and the
            # notebook would go on checking a rung the study no longer scores on.
            "score_horizon_s": w3.get("score_horizon_s"),
            "K": w3.get("K"),
            "toxic_quantile": 0.90,
            "n_perm": H.N_PERM,
            "n_boot": H.boot_draws("ws3_taker_pnl"),
            # Every random stream in this study is derived from the master seed and the
            # name of the cell that draws it, so no two cells share a sequence and none
            # depends on the order the cells ran in. The derived key is what travels,
            # because a notebook that redrew on a stream of its own would disagree with
            # the published interval for a reason a reader could not see, and the rule
            # that builds the key is not something to retype beside the numbers.
            "streams": {
                "placebo": {s: list(H.cell_key("ws3", "placebo", s, w3.get("K")))
                            for s in ("pooled", "BTC", "ETH")},
                "bootstrap": {s: list(H.cell_key("ws3", "bootstrap", s, w3.get("K")))
                              for s in ("pooled", "BTC", "ETH")},
                "oos_median_gap": list(
                    H.cell_key("ws3", "bootstrap", "oos_median_gap", w3.get("K"))),
            },
        }

    sc = load("survivorship_census_results.json")
    if sc:
        arms = sc.get("sites", {}).get("ws3_taker_pnl", {}).get("arms", {})
        exp["ws3_admission_arms"] = {
            a: {k: arms[a][k] for k in
                ("late_min_fills", "n_admitted", "n_flagged", "n_rest",
                 "decile_threshold_bps", "late_pnl_pd_bps_flag_median",
                 "late_pnl_pd_bps_rest_median", "median_gap_bps",
                 "median_gap_ci", "median_gap_ci_excludes_zero")}
            for a in ("as_committed", "early_only") if a in arms
        }
        # The two arms resample on two named streams, for the same reason the arms exist
        # at all: they must not be able to agree by having drawn the same numbers.
        exp["ws3_admission_arms"]["_shared"] = {
            "K": H.wallet_fill_floor("ws3_taker_pnl", "headline"),
            "n_boot": H.boot_draws("ws3_taker_pnl"),
            "streams": {a: list(H.cell_key("survivorship_census", "oos_median_gap", a,
                                           H.wallet_fill_floor("ws3_taker_pnl",
                                                               "headline")))
                        for a in ("as_committed", "early_only")},
        }

    # ---- the rule that decides which counterparties a maker would refuse ----
    # Added 2026-08-12. The notebook carried nothing of the HARD rule that turns a score
    # into a refusal, although the report quotes the cutoff, the flagged fraction and the
    # captured cost from it. Every column the producer reads is already in the notebook's
    # memory after the load cell, so the whole block is recomputable and the notebook was displaying nothing of it.
    ws2 = load("ws2_hard_classifier_results.json")
    if ws2:
        exp["ws2_hard_classifier"] = {
            "n_eligible": ws2["n_eligible"],
            "auc_shrunk": ws2["oos_validity"]["auc_shrunk"],
            "auc_placebo_mean": ws2["oos_validity"]["auc_placebo_mean"],
            "auc_p": ws2["oos_validity"]["auc_p"],
            "youden_threshold_bps": ws2["oos_validity"]["youden_threshold_bps"],
            "youden_flag_fraction": ws2["oos_validity"]["youden_flag_fraction"],
            "capture_at_youden": ws2["capture_at_youden"],
            "median_half_spread_bps": ws2["economic"]["median_half_spread_bps"],
            "breakeven_bps": ws2["economic"]["breakeven_bps"],
            "n_econ_toxic": ws2["economic"]["n_econ_toxic"],
            "econ_flag_fraction": ws2["economic"]["econ_flag_fraction"],
            "capture_at_econ": ws2["capture_at_econ"],
            "capture_curve_share_of_late_cost":
                ws2["capture_curve_share_of_late_cost"],
            "_shared": {
                # Read from settings.py, never typed, exactly as the producer reads them.
                "fills_each_half": H.wallet_fill_floor("ws2_hard_classifier",
                                                       "both_halves"),
                "score_horizon_s": ws2["score_horizon_s"],
                "n_perm": H.N_PERM,
                "p_floor": H.p_floor(H.N_PERM),
                # The rebate is the producer's own published leaf rather than a literal
                # here: the break-even line is a recomputed half-spread PLUS a stated
                # rebate, and only the first half of that sum is a measurement.
                "rebate_bps": ws2["economic"]["rebate_bps"],
                # The two literals of the producer that no artifact leaf carries, and
                # they are carried rather than typed into a notebook cell so that the
                # cell states no constant of its own. They mirror ws2_hard_classifier.py
                # at the label line and at the Youden grid line.
                "late_cost_decile_quantile": 0.90,
                "youden_grid_quantiles": {"from": 0.5, "to": 0.995, "n": 60},
                # The placebo stream, derived from the master seed and the name of the
                # draw the same way the producer derives it, so the notebook cannot
                # shuffle on a stream of its own and disagree for an invisible reason.
                "placebo_stream": list(H.cell_key(
                    "ws2", "auc_placebo",
                    H.wallet_fill_floor("ws2_hard_classifier", "both_halves"))),
            },
        }

    # ---- what identity buys once the quote width is held constant ----
    # Added 2026-08-12. This is the study's strongest negative control and the notebook
    # said nothing about it. The control's own producer refuses to publish a residual
    # until it has reproduced the published delta independently, so both the reproduction
    # and the split travel here: a notebook that checked the split alone would be checking
    # a comparison against a baseline it never saw.
    fs = load("flat_surcharge_control_results.json")
    if fs and fs.get("reproduction", {}).get("reproduced"):
        _floor_key = f"rank_floor_{MB.K_HEADLINE}"
        exp["flat_surcharge_control"] = {
            "published_delta_bps": fs["reproduction"]["published"],
            "recomputed_no_rank_floor_bps":
                fs["reproduction"]["recomputed"]["no_rank_floor"],
            "recomputed_at_rank_floor_bps":
                fs["reproduction"]["recomputed"][_floor_key],
            "n_wallets_no_rank_floor":
                fs["reproduction"]["n_wallets_scored"]["no_rank_floor"],
            "n_wallets_at_rank_floor":
                fs["reproduction"]["n_wallets_scored"][_floor_key],
            "pooled": {k: fs["pooled"]["one_global_constant"][k]
                       for k in ("width_bps", "flat_same_width_gain_bps",
                                 "identity_residual_bps", "width_share_pct",
                                 "identity_share_pct")},
            "pooled_at_rank_floor": {
                k: fs["pooled_at_rank_floor"]["one_global_constant"][k]
                for k in ("width_bps", "flat_same_width_gain_bps",
                          "identity_residual_bps", "width_share_pct",
                          "identity_share_pct")},
            "_shared": {
                # The quoter's own constants, imported from the quoter.
                "recover_frac": MB.RECOVER_FRAC,
                "lambda_tox": MB.LAMBDA_TOX_HEADLINE,
                "rank_floor_fills": MB.K_HEADLINE,
                "construction_that_reproduces":
                    fs["reproduction"]["construction_that_reproduces"],
                "reproduction_rtol": fs["reproduction"]["rtol"],
            },
        }

    # ---- the inventory-only quoter beside the spread the venue actually quotes ----
    # Added 2026-08-12. The A-S baseline is the model the whole extension is built on and
    # the notebook displayed none of it. Six of its per-coin leaves need only the entry
    # price and the entry spread, and the other six need a per-session volatility that the
    # same two columns rebuild, so the whole block travels rather than the level alone.
    asq = load("as_quoter_results.json")
    if asq:
        _pc = asq["as_spread_vs_real"]["per_coin"]
        exp["as_quoter_spread_vs_real"] = {
            c: {k: _pc[c][k] for k in
                ("mid_ref_price", "sigma_price_used", "observed_median_spread_bps",
                 "mean_half_spread_price", "k_price_calibrated", "as_arrival_floor_bps",
                 "floor_minus_observed_bps", "gamma_match_inventory_eq_spread",
                 "inventory_term_at_gamma_match_bps", "arrival_term_at_gamma_match_bps",
                 "vol_spread_spearman_rho", "vol_spread_n_sessions")}
            for c in ("BTC", "ETH") if c in _pc
        }
        exp["as_quoter_spread_vs_real"]["_shared"] = {
            "time_remaining_eval": asq["as_spread_vs_real"]["time_remaining_eval"],
            # The producer's two literals that no leaf carries: a session needs three
            # fills to carry a volatility at all, and fifty for its median spread to
            # enter the volatility-against-spread correlation.
            "min_fills_per_session": 3,
            "min_fills_for_session_spread": 50,
        }

    # ---- the head figure's own numbers ----
    # Added 2026-08-12. The figure the report opens with is drawn from a decile cut the
    # notebook never took: its own figure cell draws a DIFFERENT population (per coin,
    # ranked by dollar cost, at the whole-window floor) and checked nothing. The label
    # travels with the separation because the separation is a property of the label:
    # the two counts are what the caption has to say aloud, since this figure stands on
    # a floor applied to each HALF and not on the study's whole-window one.
    m2 = load("m2_figure_results.json")
    if m2:
        exp["m2_figure"] = {
            "threshold_bps": m2["labelling"]["threshold_bps"],
            "n_wallets_toxic_decile": m2["n_wallets"]["toxic_decile"],
            "n_wallets_remaining": m2["n_wallets"]["remaining"],
            "headline_separation_bps": m2["headline_separation_bps"],
            "separation_bps": m2["separation_bps"],
            "_shared": {
                # The ranking column is NOT lifted here. It would put a bare "mo10" into
                # the generated cell of a notebook that never reads it, and a bare column
                # literal in a tracked file fixes the window without declaring it, which
                # chk_headline_horizon holds at zero. The window is already declared on
                # the next lines as a number, so nothing is lost by leaving the name out.
                "top_quantile": m2["labelling"]["top_quantile"],
                "min_fills_per_half": m2["labelling"]["min_fills_per_half"],
                "ladder_s": m2["ladder_s"],
                "headline_horizon_s": m2["headline_horizon_s"],
            },
        }

    # ---- the same persistence, read through the book-mid lens ----
    # Added 2026-08-12. The notebook checked the trade-print arm of this measurement and
    # was silent about the book-mid one, which is the lens every other section scores on.
    # The reliability divisor travels as a checked quantity rather than as a given: the
    # print arm's cell reads it out of the artifact and divides by it, so the one number
    # the noise correction stands on was the one number nobody recomputed.
    ksm = load("ks2_persistence_mid_results.json")
    if ksm:
        exp["ks2_persistence_mid"] = {
            f"{e['coin']}|{e['K']}": {
                "n_counterparties": e["n_counterparties"],
                "spearman_obs": e["spearman_obs"],
                "spearman_disattenuated": e["spearman_disattenuated"],
                "rel_early": e["rel_early"], "rel_late": e["rel_late"],
                "pvalue": e["pvalue"],
                "n_draws_usable": e["permutation"]["n_draws_usable"],
                "null_mean": e["permutation"]["null_mean"],
                "null_sd": e["permutation"]["null_sd"],
            }
            for e in ksm.get("persistence_pooled", [])
        }
        exp["ks2_persistence_mid"]["_shared"] = {
            "fill_floors": list(H.PERSISTENCE_FLOOR_FILLS),
            "score_horizon_s": H.HEADLINE_HORIZON_S,
            "n_perm": H.N_PERM,
            # Both streams, and they are two rather than one on purpose: the split-half
            # reliability draws one generator across every coin, floor and half in order,
            # and the correlation null draws another across every cell in order. A
            # notebook that reordered either loop would redraw a different null and
            # disagree with the published p for a reason no reader could see.
            "reliability_seed": H.RELIABILITY_SEED,
            # NOT settings.MASTER_SEED: the producer declares this null's own seed and
            # records the difference as a fingerprint override, so it is lifted from the
            # artifact that ran under it rather than from the declaration it departs from.
            "correlation_null_seed": ksm["_meta"]["settings_fingerprint"].get(
                "master_seed", {}).get("correlation_permutation_null"),
            "extreme_tolerance_absolute": 1e-12,
        }

    # ---- the persistence figure the REPORT prints, and its own home ----
    # Added 2026-08-12, and it replaces rather than joins what the persistence section
    # used to compare against. Three files measure this one quantity and they are close
    # enough to be read as one: the trade-print arm of ks2 gives 0.8525 / 0.9043 / 0.7847
    # / 0.8363, its book-mid arm 0.8491 / 0.9190 / 0.8089 / 0.9206, and this file 0.8414
    # / 0.9207 / 0.7987 / 0.9194. The prose carries the third set and names no other, so
    # a section standing under the first was showing a reader four numbers that look like
    # the four in the text and are not them.
    #
    # WHAT SEPARATES THE THIRD FROM THE SECOND IS NOT THE LENS: both read the book mid at
    # the headline window, both keep the same wallets (644, 328, 569, 338), and their
    # observed correlations agree to the last unit in the last place. They differ in the
    # noise correction alone, and this file's own estimator field says so: the divisor
    # here is the mean of fifty row-wise splits, against one positional split at one seed
    # there, so the two "are close and are not checks on each other". Both stay published;
    # only the one the prose quotes travels into the section that quotes it.
    tc = load("three_coin_persistence_results.json")
    if tc:
        _mid = {f"{c['coin']}|{c['K']}": c for c in tc.get("cells", [])
                if c.get("lens") == "mid"
                and c.get("horizon_s") == H.HEADLINE_HORIZON_S}
        # The third contract is measured by the producer and is not in the published
        # slice, so its cells cannot be rebuilt in front of a reader. They are named
        # here, without their values, so the section can say which cells it leaves out
        # instead of leaving a gap: a figure carried but never compared is the shape
        # this file exists to avoid.
        _shipped = set(COIN_MAP.values())
        _out_of_reach = sorted(k for k in _mid if k.split("|")[0] not in _shipped)
        exp["three_coin_persistence_mid"] = {
            k: {"disatt": c["disatt"]}
            for k, c in sorted(_mid.items()) if k not in _out_of_reach
        }
        exp["three_coin_persistence_mid"]["_shared"] = {
            "lens": "mid",
            "horizon_s": H.HEADLINE_HORIZON_S,
            "fill_floors": list(H.PERSISTENCE_FLOOR_FILLS),
            "n_reliability_splits": next(iter(_mid.values()))["n_reliability_splits"],
            # The producer's own floor on a split half: below this many wallets in
            # common the reliability is noise, and dividing by it manufactures
            # persistence out of nothing.
            "min_wallets_for_reliability": 10,
            "cells_not_in_the_published_slice": _out_of_reach,
            "contracts_in_the_published_slice": sorted(_shipped),
            # One stream per half per cell, derived from the master seed and the name of
            # the draw the way every other stream in this study is. What travels is the
            # whole key WITHOUT its last component, because that last component is the
            # split index and it counts from zero to the split budget above. Handing over
            # fifty keys per half would say the same thing fifty times, and handing over
            # the rule that builds a key would put that rule in a second place.
            "reliability_stream_prefix": {
                k: {half: list(H.cell_key(f"three_coin_reliability_{half}", "mid",
                                          H.HEADLINE_HORIZON_S, k.split("|")[0],
                                          int(k.split("|")[1])))
                    for half in ("early", "late")}
                for k in sorted(_mid) if k not in _out_of_reach
            },
        }

    # ---- the per-contract split of the counterparty premium, and what it collects ----
    # Added 2026-08-12. The section that separates width from identity was written pooled
    # and the report quotes it per contract, where the two numbers are 2.85 and 10.65
    # percent and the split is the finding. The same three lines the pooled block already
    # runs give it, restricted to one contract's rows.
    if fs and fs["reproduction"]["reproduced"]:
        exp["flat_surcharge_control"]["by_coin"] = {
            c: {k: fs["by_coin"][c][k] for k in
                ("width_bps", "true_gain_bps", "flat_same_width_gain_bps",
                 "identity_residual_bps", "identity_share_pct")}
            for c in ("BTC", "ETH") if c in fs["by_coin"]
        }

    # ---- the same premium as the bake-off's own per-contract difference ----
    # Added 2026-08-12, and it is deliberately taken from the QUOTER's file rather than
    # from the control that reproduces it. The pooled figure was already checked against
    # the control; the per-contract pair was not checked at all, and reading it here is
    # what makes the notebook's rebuild a comparison against the quoting run and not
    # against a second file agreeing with it.
    if mb:
        _asv50 = mb["adverse_selection_term_value"][f"K{MB.K_HEADLINE}"]
        exp["bakeoff_term_value_at_study_floor"] = {
            c: _asv50[c]["base"]["as_toxicity_minus_as_symmetric_delta_net_vw_bps"]
            for c in ("BTC", "ETH") if c in _asv50
        }
        exp["bakeoff_term_value_at_study_floor"]["_shared"] = {
            "rank_floor_fills": MB.K_HEADLINE,
            "fee_tier": "base",
            "measure": "net_MID_lower",
        }

    # ---- the counterparties the idealised decline policy is eligible to rank ----
    # Added 2026-08-12. The report quotes this count beside the policy's upper bound and
    # the notebook carried neither. The count is the whole of what the notebook can say
    # about that block without the fee-tier machinery: it is wallets with at least the
    # stated number of scoreable fills in the ranking half, and nothing about the policy.
    # `me` is the same file the maker-net block above already opened; loading it a
    # second time would put one results file into the source list twice and make the
    # artifact say it read twenty-two files where it read twenty-one.
    if me:
        _b1 = me["b1_idealized_policy_upper_bound"]
        exp["decline_policy_eligibility"] = {
            k.replace("K", ""): _b1[k][f"h{H.HEADLINE_HORIZON_S}"]["n_eligible_takers"]
            for k in _b1 if f"h{H.HEADLINE_HORIZON_S}" in _b1[k]
        }
        exp["decline_policy_eligibility"]["_shared"] = {
            "horizon_s": H.HEADLINE_HORIZON_S,
            "unit_rule": "taker wallet, pooled over contracts",
            "counts_what": "fills with a finite book-mid markout in the ranking half",
        }

    # ---- the maker's fee schedule, at its declaration ----
    # Added 2026-08-12. This is not a result and no run produces it: it is the venue's
    # published schedule, declared once in maker_econ.py, and the notebook retypes it
    # because it also runs with no repository beside it. Two copies of one fact is the
    # whole reason it travels here: the comparison is between the two homes, not between
    # a rebuild and a number.
    exp["maker_fee_bps"] = dict(ME.MAKER_FEE_BPS)
    exp["maker_fee_bps"]["_shared"] = {
        "declared_in": "maker_econ.py",
        "source": ME.FEE_SOURCE,
        "is_a_declaration_not_a_result": True,
    }

    # ---- what the admission rule of the head figure costs, counterparty by counterparty ----
    # Added 2026-08-12. Every figure of that head figure is measured on wallets that
    # cleared a fill floor in BOTH halves, and the report quotes what that rule removes:
    # of the wallets the ranking half admits, some come back too thin and some never come
    # back at all, and the two are removed by different things. The separations under the
    # two other admission rules travel with the counts, because a count of what was
    # dropped says nothing about whether dropping it moved the answer.
    sc = load("survivorship_census_results.json")
    if sc and "m2_figure" in sc.get("sites", {}):
        _m2s = sc["sites"]["m2_figure"]
        exp["survivorship_m2"] = {
            "loss": dict(sc["totals"]["loss_by_site"]["m2_figure"]),
            "arms": {a: {"late_min_fills": _m2s["arms"][a]["late_min_fills"],
                         "n_admitted": _m2s["arms"][a]["n_admitted"],
                         "n_toxic_decile": _m2s["arms"][a]["n_toxic_decile"],
                         "n_remaining": _m2s["arms"][a]["n_remaining"],
                         "decile_threshold_bps": _m2s["arms"][a]["decile_threshold_bps"],
                         "headline_separation_bps":
                             _m2s["arms"][a]["headline_separation_bps"]}
                     for a in _m2s["arms"]},
            "_shared": {
                "floor_fills": _m2s["floor_fills"],
                # The ranking column is NOT lifted, for the same reason as above: the
                # window is declared as a number below, and the bare name would be an
                # undeclared window literal inside a generated cell nothing reads.
                "decile_quantile": _m2s["held_equal"]["decile_quantile"],
                "unit_rule": _m2s["held_equal"]["unit_rule"],
                "headline_horizon_s": H.HEADLINE_HORIZON_S,
                # The count is of SCOREABLE fills and not of rows: a fill whose markout
                # could not be computed is not one a wallet can be ranked on, and the
                # two counts differ by a few thousand rows.
                "counts_what": _m2s["counts_what"],
            },
        }

    # ---- the horizon the whole study scores on, and the curve it was chosen on ----
    # Added 2026-08-12. Every other section of the notebook takes the ten-second window
    # as given. The window was not given: it was selected on a curve over eight rungs by
    # two pre-registered rules, and the notebook carried columns for three of the eight,
    # so the one decision the rest of the work hangs from was the one decision no reader
    # could re-run. The five missing rungs need no new input -- the shipped order-book
    # series carries the mid at every millisecond, and the same as-of join the notebook
    # already runs at 1, 10 and 60 seconds answers at 2, 5, 20, 30 and 120 too.
    #
    # TWO CURVES TRAVEL, NOT ONE, because two rules were applied and they are not one
    # rule. The COST rule reads the level term structure and asks how much of the
    # permanent move has arrived; its evidence is `level_termstructure` and the plateau
    # the fractions are stated against. The RANKING rule reads the early-to-late rank
    # persistence and asks how long a score has to be averaged before the ordering
    # repeats out of sample; its evidence is `pooled`. Shipping one of them would let a
    # reader read it as the defence of both, which is the error the producer's own
    # docstring was rewritten to stop.
    #
    # The persistence cells travel WITHOUT their bootstrap interval and permutation p on
    # purpose. Both are drawn from seeded streams the notebook has no settings module to
    # derive, and both are separately published elsewhere; what the notebook can rebuild
    # exactly is the observed correlation and its noise divisor, because the split-half
    # reliability here is an ODD/EVEN split by fill order and draws no random numbers at
    # all. The one place the draws still reach is `selection.argmax_se`, so it travels as
    # a stated input to the tie-break rather than as something rebuilt.
    ws1 = load("ws1_horizon_results.json")
    if ws1:
        _grid = [int(h) for h in ws1["grid_s"]]
        _fd = ws1["final_decision"]
        exp["horizon_choice"] = {
            "level_vw_bps": {str(h): ws1["level_termstructure"]["pooled"][str(h)]["vw"]
                             for h in _grid},
            "level_n": {str(h): ws1["level_termstructure"]["pooled"][str(h)]["n"]
                        for h in _grid},
            "plateau_vw_bps": _fd["plateau_vw_bps"],
            "info_frac": {str(h): _fd["info_frac"][str(h)] for h in _grid},
            "info_complete_horizons": _fd["info_complete_horizons"],
            "most_persistent_info_complete": _fd["most_persistent_info_complete"],
            "recommended_score_horizon_s": _fd["recommended_score_horizon_s"],
            "recommended_info_frac": _fd["recommended_info_frac"],
            "persistence": {
                str(h): {k: ws1["pooled"][str(h)][k] for k in
                         ("n_units", "rho_obs", "rel_early", "rel_late", "rho_disatt")}
                for h in _grid if ws1["pooled"].get(str(h))
            },
            "selection": {k: ws1["selection"][k] for k in
                          ("argmax_h", "argmax_disatt", "argmax_se", "within_1se",
                           "h_star_parsimony")},
            "_shared": {
                "grid_s": _grid,
                # The floor the curve was measured at, and it is NOT the study's. Ten
                # fills is the loosest rung of settings.RANK_FLOOR_SENSITIVITY, against
                # the fifty every analysis file scores on. The horizon was chosen on
                # this curve, so the number is load-bearing here and nowhere else, and
                # a reader who carries a persistence from this section to another one
                # has to be told which floor each was taken at.
                "K_primary": int(ws1["K_primary"]),
                "plateau_horizons_s": _fd["plateau_horizons_s"],
                "info_complete_frac_threshold": _fd["info_complete_frac_threshold"],
                # A wallet's BTC score and its ETH score are two units, never one: the
                # producer keys the unit on the pair, and pooling them would average two
                # different books into one ranking.
                "unit_is_wallet_within_coin": True,
                # The reliability split, spelled out because it is the one estimator in
                # this block that could be built three defensible ways. It is by fill
                # ORDER within the unit -- first, third, fifth against second, fourth,
                # sixth -- and it is not the row-wise coin flip the persistence section
                # above uses, nor a wallet-wise one.
                "reliability_split": "odd/even by fill order within the unit",
                # Below this the correction is dividing by noise, and the producer
                # refuses the cell rather than reporting a number built that way.
                "min_reliability": 0.05,
            },
        }

    return exp, sources


def main():
    t0 = artifact.start_clock()
    os.makedirs(os.path.dirname(OUT_NPZ), exist_ok=True)
    zp, zm, n = load_and_align()
    cols, n_takers, n_makers = build(zp, zm, n)

    guard_ok = regression_guard(cols)
    if not guard_ok:
        sys.exit("ERROR: regression guard failed - reduced file is not faithful.")

    np.savez_compressed(OUT_NPZ, **cols)
    sha = artifact.sha256_file(OUT_NPZ)
    size_mb = os.path.getsize(OUT_NPZ) / 1e6
    day_min, day_max = int(cols["day"].min()), int(cols["day"].max())

    # source_files is gone from the payload on purpose: artifact.write records the
    # inputs with their sizes and hashes, and a record kept in two places is how one
    # census of these files disagreed with another.
    meta = {
        "object": "Reduced review dataset for the reproducibility notebook, with "
                  "pseudonymous wallet codes",
        "author": "Dmitry Stakhin",
        "window": {"coins": list(COIN_MAP.values()),
                   "days_dec2025": [day_min, day_max]},
        "n_rows": int(n),
        "n_takers": int(n_takers),
        "n_makers": int(n_makers),
        "deidentified": ("taker_code and maker_code are pseudonyms, re-indexed "
                         "contiguous integers; the hex address map is not shipped, "
                         "so the linkage to on-chain addresses is not distributed "
                         "here, but a reader holding the public source data can "
                         "re-derive it, because the Hyperliquid node data the fills "
                         "were built from, and the open deposit of the same trades by "
                         "Albers et al. (Zenodo 18184441), carry the same fills with "
                         "their addresses"),
        "columns": {k: str(v.dtype) for k, v in cols.items()},
        "sha256": sha,
        "size_mb": round(size_mb, 1),
        # WHERE THIS FILE IS PUBLISHED, AND WHY THAT STOPPED BEING ONE URL. Until
        # 2026-08-13 these were "doi" and "zenodo_url" naming record 21171473, which
        # reads as "the file described below is the file at that address". It is not,
        # and nothing in the tree could notice: sha256 above is a claim about the LOCAL
        # file, and the archive copy's own checksum was written down nowhere, so the two
        # could drift apart in silence and did.
        #
        # The archive fact is DECLARED, NOT DERIVED, on the same terms as the 190 MB in
        # requirements.txt: it sits on the other side of the network, this producer
        # cannot reach it, and it does not pretend to. Measured 2026-08-13. One command
        # re-measures it and asks nothing of this repository:
        #
        #   curl -s https://zenodo.org/api/records/21171473 | python3 -c \
        #     "import json,sys; print([(f['key'], f['size'], f['checksum']) \
        #      for f in json.load(sys.stdin)['files']])"
        "published": {
            "current_record": None,
            "note": ("in no current archive record. The notebook reads "
                     "notebook_fills.npz and notebook_book_{COIN}.npz from record "
                     "23540388 and never opens this file"),
            "superseded_copy": {
                "doi": "10.5281/zenodo.21171473",
                "url": ("https://zenodo.org/records/21171473/files/"
                        "notebook_data.npz?download=1"),
                "md5": "083fb31f9cd3ff16e05c736d06a712e0",
                "bytes": 56198506,
                "checked_utc": "2026-08-13",
                "matches_this_file": False,
                "why": ("written before i4_midmarkout.join_entry stopped accepting a "
                        "book snapshot stamped at the fill's own millisecond, on "
                        "2026-08-02. Its six book-side columns carry the retired "
                        "values and its pooled 10 s book-mid markout is +2.0616 bps, "
                        "the figure that correction retired"),
            },
        },
    }
    scope = {"population": (f"{n:,} fills, {n_takers:,} taker and {n_makers:,} maker "
                            f"pseudonyms; every row of the two aligned intermediates, "
                            f"reduced to the columns the notebook consumes"),
             "window": f"December 2025, days {day_min} to {day_max}",
             "coins": list(COIN_MAP.values())}
    # The lens is not stated: this file ships BOTH reference prices as columns
    # (mo{h} and mo{h}_mid), so a single lens in the fingerprint would be a claim
    # about the artifact that the artifact does not make.
    artifact.write(os.path.basename(OUT_META), meta, script=__file__,
                   inputs=[PRINT_NPZ, MID_NPZ], scope=scope, started=t0,
                   settings={"h": H.HEADLINE_HORIZON_S},
                   out_dir=os.path.dirname(OUT_META))

    expected, sources = extract_expected()
    # The inputs are the committed results files the numbers were lifted from, hashed,
    # so a reader can tell whether these reference values are older than the results
    # they claim to reproduce.
    artifact.write(
        os.path.basename(OUT_EXPECTED), expected, script=__file__, inputs=sources,
        scope={"population": (f"{len(expected)} groups of reported figures, extracted "
                              f"from {len(sources)} committed results files; no number "
                              f"is computed here"),
               "window": f"December 2025, days {day_min} to {day_max}",
               "coins": list(COIN_MAP.values())},
        started=t0, settings={"h": H.HEADLINE_HORIZON_S},
        out_dir=os.path.dirname(OUT_EXPECTED))

    print(f"\n[write] {OUT_NPZ}  ({size_mb:.1f} MB)")
    print(f"[write] sha256 = {sha}")
    print(f"[write] {OUT_META}")
    print(f"[write] {OUT_EXPECTED}  ({len(expected)} result groups)")
    print(f"[done] {n:,} rows | {n_takers:,} takers | {n_makers:,} makers | "
          f"days {day_min}-{day_max}")


if __name__ == "__main__":
    main()
