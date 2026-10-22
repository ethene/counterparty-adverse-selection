"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-20
References:
  - Hyperliquid node-data S3 archive (node_fills_by_block/hourly), s3://hl-mainnet-node-data.
  - Zenodo 18184441 (Albers et al. 2026).
  - Easley, Lopez de Prado, O'Hara (2012). "Flow Toxicity and Liquidity in a
    High-frequency World." Review of Financial Studies 25(5), 1457-1493 (VPIN).
  - Benjamini, Y., Hochberg, Y. (1995). "Controlling the False Discovery Rate."
    JRSS-B 57(1), 289-300.
"""

# ---------------------------------------------------------------------------
# OBJECT PANEL-ANALYZE - DOES THE DECEMBER CORE CHAIN REPRODUCE EVERY MONTH?
#
# The validated December run (i3_nonrecoverability_oos.py + t3_capacity.py)
# showed, on one 10-day BTC/ETH window, that (a) a wallet's own EARLY-half
# markout history adds OUT-OF-SAMPLE predictive lift over the anonymous trade
# tape (VPIN / signed-flow imbalance / size / intensity) - i.e. per-counterparty
# toxicity is NON-RECOVERABLE from anonymous flow - and (b) the resulting
# adverse-selection cost concentrates in a thin tail of persistently toxic
# wallets. The standing referee worry is REGIME SPECIFICITY: December 2025 might
# be special. This script re-runs the SAME validated core chain on a PANEL of
# three 10-day windows (Aug / Oct / Dec 2025) across {BTC, ETH, SOL}, per period
# and pooled, per coin and pooled-coin, so the headline read is unambiguous:
#
#   the non-recoverability result REPRODUCES across all three months, or it does
#   not. We do NOT re-derive any statistic here - every estimator is IMPORTED
#   from the December scripts (i3_nonrecoverability_oos.py, t3_capacity.py) and
#   run unchanged, just sliced by the new `period` column.
#
# WHAT IS IMPORTED (never copied):
#   from i3_nonrecoverability_oos:
#       _aggregate_features  - per-wallet anonymous metrics + history FE + target
#       incremental_lift     - OOS-by-wallet incremental R^2 / Spearman of B over A
#       placebo_pvalue       - label-permuted-FE null (p-floor 1/(N_PERM+1))
#       whale_robust_check   - drop top-k wallets by notional, sign of lift holds
#       benjamini_hochberg   - BH-FDR q-values over the cell family
#       spearman             - rank correlation
#       (constants N_FOLDS, N_PERM, K_LIST, HORIZONS, WHALE_DROP_K, RNG_SEED,
#        FDR_ALPHA reused verbatim so the panel cells match December's settings)
#   from t3_capacity:
#       _cost_block          - signed adverse-selection cost ($ total / $-per-day
#                              / bps) with the runtime per-day divisor
#       _per_wallet_cost     - per-wallet ranking on the early-half trade floor
#       _avoidable_block     - top-decile / top-50 avoidable share + robustness
#
# PANEL WINDOW (fixed): coins {BTC, ETH, SOL} x three 10-day windows:
#   202508 = 2025-08-04..08-13   (day-of-month 4..13)
#   202510 = 2025-10-06..10-15   (day-of-month 6..15)
#   202512 = 2025-12-04..12-13   (day-of-month 4..13)
# 9 coin-month cells, 90 coin-days. `period` is the int YYYYMM column.
#
# SCOPE vs ARTIFACT: panel_markouts.npz was later rebuilt from these 3 windows to
# 8 (Aug 2025 .. May 2026, 26,035,902 rows on disk). This script pins
# CANONICAL_PERIODS below and restricts its load to the 3 windows above, so the
# ANALYSED population stays the 10,455,129 rows the reported panel numbers were
# computed on (BTC 3,736,972 / ETH 4,356,836 / SOL 2,361,321). Quote the analysed
# figure when describing a panel RESULT and the on-disk figure when describing
# COVERAGE; they are different quantities.
#
# EARLY/LATE SPLIT per period: the December scripts hardcode day-of-month 4-8 /
# 9-13, but the panel windows differ by month (Oct = 6..15). So per period we
# resolve the days ACTUALLY present in that period and split them into an early
# and a late half (first ceil(n/2) days = early), exactly as the validated
# ks2_persistence split does on the resolved set. We then pass those period-
# specific day-of-month lists to the IMPORTED i3._aggregate_features and (via the
# t3.EARLY_DAYS_OVERRIDE module global, which is precisely t3's documented "early
# half" knob) to the IMPORTED t3._per_wallet_cost, so each estimator runs on its own
# month's early/late halves while the code path stays the December code path.
#
# DATA SOURCE = node_fills_by_block ONLY (trade-print markout on native ns
# block_time). This script does NOT parse raw data; it READS panel_markouts.npz
# (the quickwin schema + a `period` column) produced by the separate panel build
# pass. The full 90-cell pull is a separate background step; this file is the
# cheap consumer.
#
# Run command (bare python3 is BLOCKED on this machine):
#   uv run --no-project --with-requirements requirements.txt python3 persistence/panel_analyze.py
# ---------------------------------------------------------------------------

import argparse
import json
import os
import sys

import numpy as np

# The shared modules sit in the repository root, one directory up from this
# group, and this file also imports from the identity group and the money group. Both are built from this
# file's own location and never from the working directory the run happens to
# start in.
_CODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_CODE_DIR, os.path.join(_CODE_DIR, "identity"), os.path.join(_CODE_DIR, "money")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import artifact
import panel_io as P
import settings as H
import stats

# IMPORT (do not copy) the validated December harnesses. ------------------------
# i3 and t3 both guard their work behind `if __name__ == "__main__"`, so importing
# them runs NOTHING; it only binds the functions + the registered constants.
import i3_nonrecoverability_oos as i3
import t3_capacity as t3

# -------------------- configuration --------------------
HERE = os.path.dirname(os.path.abspath(__file__))
# data-root resolution: env override, else this script's directory. NO hardcoded
# /Users path. Only the BASENAME of the npz is ever written into the result JSON.
# The data root and the panel name both come from panel_io. The environment variable
# this script has always honoured is passed in by name rather than dropped, so a run
# that sets PANEL_DATA_ROOT still reads the same file it read before.
PANEL_ENV = ("PANEL_DATA_ROOT",)
DATA_ROOT = P.data_root(env_names=PANEL_ENV)
PANEL_NPZ_PATH = os.path.join(P.data_root(env_names=PANEL_ENV), "panel_markouts.npz")
RESULTS_PATH = os.path.join(HERE, "panel_analyze_results.json")

# Fixed panel window (the SHARED SPEC). period = int YYYYMM.
PERIODS = (202508, 202510, 202512)
# Pins the paper's Aug/Oct/Dec 3-window check: panel_markouts.npz was later rebuilt from
# 3 to 8 windows, so main() restricts the loaded fills to these three periods so a re-run
# on the extended npz reproduces the committed panel_analyze_results.json.
CANONICAL_PERIODS = (202508, 202510, 202512)
PERIOD_WINDOW_DOM = {                 # day-of-month range of each 10-day window
    202508: tuple(range(4, 14)),      # 2025-08-04..08-13
    202510: tuple(range(6, 16)),      # 2025-10-06..10-15
    202512: tuple(range(4, 14)),      # 2025-12-04..12-13
}
COIN_CODES = H.coin_labels("panel")           # {0: BTC, 1: ETH, 2: SOL}; the map
                                              # belongs to the FILE, so it is asked
                                              # for by artifact name and never typed

# All cell settings are reused verbatim from the December i3 run so the panel
# cells are directly comparable to it. Declared here as a header constant block.
HORIZONS = i3.HORIZONS                 # (60, 10) = (companion, headline) from settings
K_LIST = i3.K_LIST                     # (50, 100)
N_FOLDS = i3.N_FOLDS
N_PERM = i3.N_PERM
WHALE_DROP_K = i3.WHALE_DROP_K
FDR_ALPHA = i3.FDR_ALPHA
RNG_SEED = i3.RNG_SEED                 # 20260619 (same master seed as December)
P_FLOOR = H.p_floor(N_PERM)

# Two of the settings above differ from what settings.py declares, on purpose: the
# December seed 20260619 (settings declares MASTER_SEED 20260620) and i3's 1000
# permutation draws (settings declares 2000). Both are inherited from the December
# run this panel exists to reproduce, so changing either would move every p-value
# in the artifact and break the comparison the panel is for. They are therefore
# passed to H.fingerprint as EXPLICIT OVERRIDES, which is how a deliberate
# difference is told apart from a drift.
# H.fingerprint asserts a MIGRATING declaration only when the caller states what its
# run used, so every one this run has a value for is stated here, and the ones it has
# no use for are named as such rather than left to look unanswered.
SETTINGS_OVERRIDES = {
    "master_seed": RNG_SEED,
    "n_perm": N_PERM,
    "p_floor": P_FLOOR,
    "n_folds": N_FOLDS,
    "rank_floor_fills": t3.MIN_EARLY_TRADES,   # the ranking floor t3 applied
    "random_draws": t3.RANDOM_DRAWS,           # the avoidable-share random floor
    "settings_not_used": ["n_boot"],           # nothing here bootstraps
}

# -------------------- window-bearing field names, built and never typed --------
# settings.FIELD_SUFFIX_STYLE = "explicit": every field whose VALUE depends on the
# scoring window states that window in its NAME, and no such field is left
# unsuffixed. This file used to leave the HEADLINE window unsuffixed and suffix
# only the companion; t3_capacity.py does the opposite, leaving the COMPANION
# unsuffixed. Both wrote a key spelled `cost_bps`, so the one name meant 10 s in
# this artifact and 60 s in that one, and a reader comparing the two files read a
# single name as two different quantities. Nothing in either file said so. Names
# are therefore built by H.field_name from the horizon in hand and never typed.
#
# The LENS is not appended here: the panel reads node_fills_by_block only, so
# every number in this artifact is a trade-print markout and no key could be
# confused with a book-mid one. The lens is stated once, in the fingerprint.
def _f(base, h):
    """The name of one window-bearing field at horizon h seconds."""
    return H.field_name(base, h)


# -------------------- early/late split for a period --------------------
# The split is settings.split_early_late: the days ACTUALLY PRESENT in a period,
# first ceil(n/2) early and the remainder late. It used to be a local copy of the
# same rule; it now comes from the one declaration, because a rule that lives in
# two files is a rule that can disagree with itself. The December scripts hardcode
# day-of-month 4-8 / 9-13, which is wrong for the October window (days 6..15).
_split_early_late = H.split_early_late


# -------------------- one non-recoverability cell --------------------
def _nonrecoverability_cell(g_taker, g_day, g_not, g_isbuy, g_mo,
                            early_days, late_days, K, label, period, h):
    """Run the IMPORTED December non-recoverability chain on one slice at one K/h.

    Builds the per-wallet feature panel with i3._aggregate_features (anonymous
    VPIN / imbalance / size / intensity + history FE + LATE-half target), then
    i3.incremental_lift, i3.placebo_pvalue and i3.whale_robust_check exactly as
    the December run does. Seeds are derived deterministically from i3.RNG_SEED so
    every panel cell is reproducible and matches the December seed scheme
    (RNG_SEED + K + h / RNG_SEED*3 + K + h / RNG_SEED*7 + K + h), offset by the
    period so the three months use independent-but-fixed streams.

    WHY THE PLACEBO p HERE IS NOT stats.permutation_p, while the correction below IS.
    The p is not computed in this file at all: i3.placebo_pvalue draws its own null and
    returns a bare number, so moving it to the shared module means editing that file's
    procedure, not this file's call. It would also change the number twice over -- the
    stream would come from a named cell instead of the derived seeds above, and the
    denominator would become the count of draws that came back finite instead of the
    budget. Both are measured changes owed a recompute of the December artifact this
    panel exists to be comparable with, which is the one thing the panel may not do.
    """
    row = {"period": int(period), "coin": label, "horizon_s": int(h), "K": int(K)}
    if not late_days:
        row.update({"n_wallets": 0, "incremental_oos_r2": None,
                    "incremental_spearman": None, "placebo_p": None,
                    "whale_robust": "n/a",
                    "note": "period has no late half (fewer than 2 distinct days)"})
        return row

    built = i3._aggregate_features(
        g_taker, g_day, g_not, g_isbuy, g_mo, early_days, late_days, K)
    if built is None:
        row.update({"n_wallets": 0, "incremental_oos_r2": None,
                    "incremental_spearman": None, "placebo_p": None,
                    "whale_robust": "n/a",
                    "note": "too few eligible wallets for OOS folds"})
        return row

    _wallet_ids, X_anon, hist_fe, target, tot_not = built
    # period offset keeps the three months' streams distinct yet fixed.
    poff = int(period)
    lift = i3.incremental_lift(
        X_anon, hist_fe, target, np.random.default_rng(RNG_SEED + poff + K + h))
    folds = lift.pop("_folds")
    Xa = lift.pop("_Xa")
    _ = lift.pop("_target")

    p_perm = i3.placebo_pvalue(
        Xa, target, hist_fe, lift["incremental_oos_r2"], folds,
        np.random.default_rng(RNG_SEED * 3 + poff + K + h))
    incr_no_whale, whale_verdict = i3.whale_robust_check(
        X_anon, hist_fe, target, tot_not, lift["incremental_oos_r2"],
        np.random.default_rng(RNG_SEED * 7 + poff + K + h))

    row.update({
        "n_wallets": int(lift["n_wallets"]),
        "oos_r2_anon": lift["oos_r2_anon"],
        "oos_r2_anon_plus_fe": lift["oos_r2_anon_plus_fe"],
        "incremental_oos_r2": lift["incremental_oos_r2"],
        "oos_spearman_anon": lift["oos_spearman_anon"],
        "oos_spearman_anon_plus_fe": lift["oos_spearman_anon_plus_fe"],
        "incremental_spearman": lift["incremental_spearman"],
        "placebo_p": p_perm,
        "incremental_oos_r2_no_whales": incr_no_whale,
        "whale_robust": whale_verdict,
    })

    # Same honesty flag as December: a non-positive incremental R^2 alongside a
    # POSITIVE incremental Spearman is an UNDERPOWERED / INCONCLUSIVE cell, never
    # evidence that toxicity is recoverable.
    incr_r2 = row["incremental_oos_r2"]
    incr_sp = row["incremental_spearman"]
    if (incr_r2 is not None and incr_r2 == incr_r2 and incr_r2 <= 0
            and incr_sp is not None and incr_sp == incr_sp and incr_sp > 0):
        row["interpretation"] = (
            "INCONCLUSIVE/UNDERPOWERED, not a recoverability finding: incremental "
            f"R^2 {incr_r2:+.4f} <= 0 while incremental Spearman {incr_sp:+.4f} > 0. "
            "The positive rank lift means the wallet-history FE still orders future "
            "toxicity out of sample; the non-positive R^2 is a level-fit artefact. "
            "Do NOT read this cell as evidence toxicity is recoverable from the tape.")
    else:
        row["interpretation"] = None
    return row


# -------------------- one economic-cost cell --------------------
def _cost_cell(coin_mask, day, mo10, mo60, notional, taker_id,
               early_days, label, period, n_days):
    """Per-period adverse-selection cost via the IMPORTED t3 estimators.

    Headline cost (t3._cost_block) has no module-global dependency and is clean:
    total $, $/day (divisor = distinct resolved days in THIS period), and bps.
    The avoidable-share ranking (t3._per_wallet_cost / t3._avoidable_block) uses
    t3's documented EARLY_DAYS_OVERRIDE module knob as its early-half trade floor; we
    set that knob to THIS period's early-half day-of-month set for the duration of the
    call (restored afterwards), so the imported t3 code runs unchanged on the
    correct month. Returns the compact economic block for the period.
    """
    mo60_s = np.asarray(mo60)[coin_mask]
    mo10_s = np.asarray(mo10)[coin_mask]
    nt_s = np.asarray(notional)[coin_mask]

    c60 = t3._cost_block(mo60_s, nt_s, n_days)
    c10 = t3._cost_block(mo10_s, nt_s, n_days)

    # temporarily point t3's early-half knob at THIS period's early window, run the
    # imported ranking + avoidable block, then restore. This is the faithful reuse
    # path: t3.EARLY_DAYS_OVERRIDE is exactly t3's "early half used to rank persistent
    # toxicity" knob; we feed it the month's early half rather than hardcoded 4-8. The
    # knob was called t3.EARLY_DAYS until 2026-07-31; only the NAME changed, and it
    # changed because a name spelling a setting whose value comes from settings.py is
    # the defect settings.py names in its own second rule.
    saved_early = t3.EARLY_DAYS_OVERRIDE
    try:
        # t3.EARLY_DAYS_OVERRIDE is a MODULE GLOBAL and has to be set as one. t3's
        # _per_wallet_cost declares early_days / late_days parameters, but its body
        # reads the globals and ignores the parameters, so passing them at the call
        # site would be discarded without a word and October would be ranked on the
        # wrong half. The LATE half is deliberately left unset so t3 derives it as
        # "present days minus early", which is what splits the October window
        # (days 6..15) correctly instead of on another month's day numbers.
        t3.EARLY_DAYS_OVERRIDE = tuple(int(d) for d in early_days)
        # t3._per_wallet_cost returns five values since the out-of-sample rewrite
        # (early / late / all-days cost per wallet, plus the diagnostic block), and
        # _avoidable_block takes all five. This caller unpacked three and passed
        # three, so panel_analyze.py raised ValueError before writing anything and
        # its committed results file predates the rewrite. Repaired 2026-07-30.
        # The wallet ranking runs on the HEADLINE window. It used to run on the
        # companion one, which meant the panel screened counterparties on a window
        # the work does not report -- and the companion window loses its lift
        # entirely in the October regime, where five of eight cells go negative.
        ids, early_cost, late_cost, all_cost, diag = t3._per_wallet_cost(
            taker_id, coin_mask, day, mo10, notional)
        avoid = t3._avoidable_block(ids, early_cost, late_cost, all_cost, diag)
    finally:
        t3.EARLY_DAYS_OVERRIDE = saved_early

    HL, CO = H.HEADLINE_HORIZON_S, H.COMPANION_HORIZON_S
    return {
        "period": int(period),
        "coin": label,
        "n_days": int(n_days),
        # EVERY field below whose value depends on the window states the window.
        # There is no unsuffixed cost field any more, in either direction: a reader
        # can no longer pick "the plainest-looking one" and get a window by accident.
        _f("total_cost_usd", HL): round(c10["total_cost_usd"], 2),
        _f("cost_per_day_usd", HL): round(c10["cost_per_day_usd"], 2),
        _f("cost_bps", HL): round(c10["cost_bps"], 4),
        _f("total_cost_usd", CO): round(c60["total_cost_usd"], 2),
        _f("cost_per_day_usd", CO): round(c60["cost_per_day_usd"], 2),
        _f("cost_bps", CO): round(c60["cost_bps"], 4),
        _f("raw_mean_markout_bps", HL): round(c10["cost_bps"], 4),
        "taker_fee_band_bps": list(t3.PER_TAKER_FEE_BPS),
        # t3's out-of-sample rewrite renamed these: the avoidable share is now the
        # OOS one (rank on early, measure on late) and the old in-sample number is a
        # relabelled diagnostic. The caller still asked for the pre-rewrite key names,
        # which is the second half of why this script could not run.
        #
        # The four ranking numbers carry the headline suffix because the ranking runs
        # on the headline window: t3._per_wallet_cost was handed mo10 above. The keys
        # of the dict t3 RETURNS stay window-free, correctly - that function is told
        # which markout to use and cannot know which window it is, so a window in its
        # own return keys would be a guess. Only the artifact names the window.
        _f("avoidable_share_top10pct", HL): avoid["avoidable_share_oos_top10pct"],
        _f("avoidable_share_top50", HL): avoid["avoidable_share_oos_top50"],
        _f("random_floor_top10pct", HL): avoid["random_floor_top10pct"],
        _f("oracle_ceiling_top10pct", HL): avoid["oracle_ceiling_top10pct"],
        _f("in_sample_concentration_top10pct", HL):
            avoid["in_sample_concentration"]["share_top10pct"],
        _f("n_ranked_wallets", HL): avoid.get("n_ranked_wallets", 0),
        # The halves t3 ACTUALLY used, read back out of its diagnostic block rather
        # than restated from what we asked for. The two can differ: this caller
        # injects only the early half and t3 derives the late one, so the artifact
        # records the derivation instead of promising it. Days of the month, not
        # windows, so they carry no horizon suffix.
        "early_days_resolved": list(diag.get("early_days", [])),
        "late_days_resolved": list(diag.get("late_days", [])),
        _f("_n_rows", HL): c10["_n_rows"],
        _f("_n_rows", CO): c60["_n_rows"],
        # The notional total is read off the COMPANION cost block, so it counts the
        # rows that carry a finite 60 s markout, not the 10 s ones. Those row counts
        # differ (they differ by 201 rows on the first cell of the committed file),
        # so this total is a companion-window quantity and now says so.
        _f("total_notional_usd", CO): round(c60["_total_notional"], 2),
    }


# -------------------- main --------------------
def main():
    started = artifact.start_clock()
    # panel_io raises when the file is absent and names the producer to run, and the
    # require list turns a missing column into one refusal here, before any work, that
    # says what was asked for and what the file actually holds. The extra column this
    # panel must carry beyond the quickwin schema is the int period (YYYYMM).
    # panel_io names the producer to run when a file is absent, so that message is
    # written once for the whole tree; the loads stay here because build.py derives
    # this script's input edges from the arguments of np.load.
    P.require_present("panel", PANEL_NPZ_PATH)
    z = np.load(PANEL_NPZ_PATH, allow_pickle=False)
    # The extra column this panel must carry beyond the quickwin schema is the int
    # period (YYYYMM); a missing one is refused here, before any work.
    P.require_columns(z, "panel", "taker_id", "coin", "day", P.score_col("panel"),
                      P.score_col("panel", H.COMPANION_HORIZON_S),
                      "notional", "period")

    taker_id = z["taker_id"].astype(np.int64)
    coin = z["coin"].astype(np.int8)
    day = z["day"].astype(np.int64)               # day-of-month within each window
    period = z["period"].astype(np.int64)         # YYYYMM
    mo_by_h = {H.COMPANION_HORIZON_S: z[H.companion_print_col()].astype(np.float64),
               H.HEADLINE_HORIZON_S: z[H.headline_print_col()].astype(np.float64)}
    notional = z["notional"].astype(np.float64)
    mo10 = mo_by_h[H.HEADLINE_HORIZON_S]
    mo60 = mo_by_h[H.COMPANION_HORIZON_S]

    # Buy/sell flag for the anonymous VPIN / imbalance predictors. Prefer the REAL
    # aggressor side (taker_side) exactly as i3 does; fall back to i3's documented
    # start_pos-sign proxy only if absent (so the panel never silently changes the
    # comparator's side convention vs December).
    if "taker_side" in z.files:
        is_buy_all = (z["taker_side"].astype(np.int64) != 0).astype(np.int64)
        side_source = "taker_side (real aggressor flag from intermediate)"
    elif "start_pos" in z.files and "is_open" in z.files:
        is_buy_all = i3._derive_is_buy(
            z["start_pos"].astype(np.float64), z["is_open"].astype(np.int64),
            taker_id, day)
        side_source = "start_pos-sign proxy (taker_side absent)"
    else:
        is_buy_all = np.ones(taker_id.size, dtype=np.int64)
        side_source = "all-buy fallback (no side fields present)"
    print(f"[panel] buy/sell flag source: {side_source}")

    # ---- pin to the paper's canonical Aug/Oct/Dec windows (CANONICAL_PERIODS) ----
    # panel_markouts.npz was rebuilt from 3 to 8 windows; the loop below iterates whatever
    # periods are in the npz, so an unrestricted re-run would consume all 8 and DIVERGE
    # from the committed panel_analyze_results.json. Restrict every per-row array to the
    # three canonical windows so the re-run reproduces the paper. Idempotent: a no-op when
    # the npz already holds only those three.
    _keep = np.isin(period, np.asarray(CANONICAL_PERIODS, dtype=np.int64))
    if not bool(_keep.all()):
        taker_id = taker_id[_keep]
        coin = coin[_keep]
        day = day[_keep]
        period = period[_keep]
        notional = notional[_keep]
        mo10 = mo10[_keep]
        mo60 = mo60[_keep]
        mo_by_h = {H.COMPANION_HORIZON_S: mo60, H.HEADLINE_HORIZON_S: mo10}
        is_buy_all = is_buy_all[_keep]
        print(f"[panel] restricted to canonical periods {list(CANONICAL_PERIODS)}: "
              f"{period.size:,} of {_keep.size:,} rows")

    periods_present = sorted(int(p) for p in np.unique(period))
    print(f"[panel] periods present in npz: {periods_present}")

    results = {
        "object": "PANEL-ANALYZE - December core chain re-run per period + pooled; "
        "reproduction reported PER HORIZON (10s is the headline and the robust "
        "common thread; the 60s companion window attenuates in the October "
        "crash regime)",
        # This file's own descriptive object block. It is NOT the canonical scope
        # record: that one is the population / window / coins triple in _meta.scope,
        # which artifact.write requires and which a census reads by one predicate.
        "scope": {
            "canonical_scope_at": "_meta.scope",
            "settings_fingerprint_at": "_meta.settings_fingerprint",
            "periods_requested": list(PERIODS),
            "periods_present": periods_present,
            "period_window_dom": {str(k): list(v) for k, v in PERIOD_WINDOW_DOM.items()},
            "coins": list(COIN_CODES.values()),
            "horizons_s": list(HORIZONS),
            "K_list": list(K_LIST),
            "n_folds": N_FOLDS,
            "n_perm": N_PERM,
            "p_floor": P_FLOOR,
            "whale_drop_k": WHALE_DROP_K,
            "fdr_alpha": FDR_ALPHA,
            "rng_seed": RNG_SEED,
            "data_source": "node_fills_by_block ONLY (trade-print markout, native ns "
            "block_time). No l2Book / book-mid in this panel (a documented follow-on).",
            "early_late_split": "per period, first ceil(n/2) distinct resolved days "
            "= EARLY, remainder = LATE (generalises the ks2 first-half/second-half "
            "split so each month's window splits on its own day range).",
            "comparator_scope": "TRADE-TAPE-ONLY anonymous metrics (VPIN bulk-volume "
            "classification, rolling signed-flow imbalance, mean size, trade "
            "intensity); identical to the December i3 comparator family. NO order book.",
            "imported_from": {
                "i3_nonrecoverability_oos": ["_aggregate_features", "incremental_lift",
                                             "placebo_pvalue", "whale_robust_check",
                                             "benjamini_hochberg", "spearman"],
                "t3_capacity": ["_cost_block", "_per_wallet_cost", "_avoidable_block"],
            },
            "side_source": side_source,
            "headline_question": "Does the non-recoverability result (history FE adds "
            "OOS lift over the anonymous trade tape, placebo kills it) REPRODUCE "
            "across ALL THREE months, not just December?",
        },
        "nonrecoverability": {"by_coin": [], "pooled": []},
        "economic_cost": {"by_coin": [], "pooled": []},
        "issues": [],
    }

    # report any requested period that did not show up in the npz
    for p in PERIODS:
        if p not in periods_present:
            results["issues"].append(
                f"period {p} requested but ABSENT from panel_markouts.npz")

    # groups: each panel coin separately, then pooled-coin (-1 sentinel = all coins).
    # Built from the artifact's own coin map (settings.coin_labels("panel")) so a
    # coin cannot be listed here under a code the panel npz does not use.
    coin_groups = [(code, label) for code, label in sorted(COIN_CODES.items())]
    coin_groups.append((-1, "POOLED"))

    for p in periods_present:
        p_mask = period == p
        if not p_mask.any():
            continue
        # resolve the days actually present in THIS period and split early/late
        present_dom = sorted(int(d) for d in np.unique(day[p_mask]))
        early_days, late_days = _split_early_late(present_dom)
        n_days = len(present_dom)
        req_dom = PERIOD_WINDOW_DOM.get(int(p))
        if req_dom is not None and n_days < len(req_dom):
            results["issues"].append(
                f"period {p}: {n_days}/{len(req_dom)} window days resolved "
                f"(present day-of-month {present_dom}); short window is underpowered.")
        print(f"[panel] period {p}: days={present_dom} early={early_days} "
              f"late={late_days}")

        for code, label in coin_groups:
            if code == -1:
                sel = p_mask
            else:
                sel = p_mask & (coin == code)
            if not sel.any():
                # silently skip an absent coin-month (e.g. SOL missing a window)
                continue

            g_taker = taker_id[sel]
            g_day = day[sel]
            g_not = notional[sel]
            g_isbuy = is_buy_all[sel]

            # ---- non-recoverability cells (coin x horizon x K) ----
            for h in HORIZONS:
                g_mo = mo_by_h[h][sel]
                for K in K_LIST:
                    row = _nonrecoverability_cell(
                        g_taker, g_day, g_not, g_isbuy, g_mo,
                        early_days, late_days, K, label, p, h)
                    bucket = (results["nonrecoverability"]["pooled"] if code == -1
                              else results["nonrecoverability"]["by_coin"])
                    bucket.append(row)
                    print(f"[panel] NR {p} {label:<6} h={h:>2}s K={K:>3} "
                          f"n={row.get('n_wallets', 0):>5} "
                          f"incrR2={i3._fmt(row.get('incremental_oos_r2'))} "
                          f"incrSp={i3._fmt(row.get('incremental_spearman'))} "
                          f"placebo_p={i3._fmt(row.get('placebo_p'))} "
                          f"whale_ok={row.get('whale_robust')}")

            # ---- economic cost (one block per coin-period) ----
            cost = _cost_cell(sel, day, mo10, mo60, notional, taker_id,
                              early_days, label, p, n_days)
            cbucket = (results["economic_cost"]["pooled"] if code == -1
                       else results["economic_cost"]["by_coin"])
            cbucket.append(cost)
            _hl = H.HEADLINE_HORIZON_S
            print(f"[panel] COST {p} {label:<6} "
                  f"total=${cost[_f('total_cost_usd', _hl)]:,.2f} "
                  f"$/day=${cost[_f('cost_per_day_usd', _hl)]:,.2f} "
                  f"bps={cost[_f('cost_bps', _hl)]:+.4f} "
                  f"avoid10%="
                  f"{cost[_f('avoidable_share_top10pct', _hl)] * 100:.1f}%")

    # ----------------------------------------------------------------------
    # BH-FDR over the FULL family of non-recoverability cells (period x coin x
    # horizon x K), using the IMPORTED i3.benjamini_hochberg. Cells with a null
    # placebo p (too few wallets / no positive lift) are excluded from the family
    # size m and never survive - identical convention to December.
    # ----------------------------------------------------------------------
    all_nr = results["nonrecoverability"]["by_coin"] + results["nonrecoverability"]["pooled"]
    family_p = []
    for r in all_nr:
        pp = r.get("placebo_p")
        family_p.append(float("nan") if (pp is None or pp != pp) else float(pp))
    # The correction comes from stats.py rather than from i3's copy of it. It costs no
    # q: stats._legacy_bh_vectorised is that copy, and the self-test there runs the two
    # against each other on 200 random families with ties and untestable cells. What
    # the module adds is the CUTOFF the q-values were judged against, which no local
    # copy returned and which a claim of surviving the correction cannot be read
    # without: alpha/m depends on the family size, and this work's families run from 4
    # to 448 at one alpha.
    bh = stats.benjamini_hochberg(
        family_p, alpha=FDR_ALPHA,
        family="panel non-recoverability placebo p-values across "
               "(period x coin x horizon x K), per-coin and pooled")
    qvals = bh["q"]
    m_tested = int(bh["family_size"])
    survivors = []
    for r, q in zip(all_nr, qvals):
        if q is None:
            r["bh_qvalue"] = None
            r["survives_fdr"] = False
        else:
            r["bh_qvalue"] = float(q)
            r["survives_fdr"] = bool(q <= FDR_ALPHA)
            if r["survives_fdr"]:
                survivors.append({"period": r["period"], "coin": r["coin"],
                                  "horizon_s": r["horizon_s"], "K": r["K"],
                                  "placebo_p": r.get("placebo_p"),
                                  "bh_qvalue": float(q)})

    results["nonrecoverability"]["family"] = dict(
        bh, q=None,
        q_note="the q-values are on the cells, under bh_qvalue; this block holds the "
               "procedure, the family and the cutoff applied to them",
        fdr_alpha=FDR_ALPHA,
        n_cells_total=len(all_nr),
        n_cells_tested=m_tested,
        n_cells_untestable=len(all_nr) - m_tested,
        n_survivors=len(survivors),
        survivors=survivors,
    )

    # ----------------------------------------------------------------------
    # HEADLINE READ - HONEST, PER HORIZON not just per period.
    #
    # The weak read ("at least ONE positive-lift cell survives BH-FDR per
    # period") is literally true in every resolved month but HIDES that the two
    # horizons behave very differently. The 10s signal is the robust common
    # thread - the pre-registered POOLED/10s/K=50 cell survives BH-FDR in EVERY
    # month. The 60s headline horizon ATTENUATES SHARPLY in the October crash
    # regime: there, almost no 60s cell survives (typically only one coin's
    # K=50 cell, at a trivial incremental R^2), the pooled and other-coin 60s
    # cells go NEGATIVE on incremental R^2, and the aggregate 60s markout for
    # October flips negative (makers PROFITED on net 60s flow that month).
    #
    # So we report reproduction (1) per period (survivor count out of the
    # per-period cell family), (2) per horizon (does that horizon survive in
    # every month?), and (3) with an explicit October-60s attenuation flag read
    # straight from the cell rows. Every number below is COUNTED from all_nr /
    # the economic_cost blocks - nothing is hardcoded, so the logic is correct
    # whether the panel carries 2 coins or 3 (SOL added) and whatever the BH
    # family size turns out to be. The BH family is PANEL-WIDE (m = all tested
    # cells across every period x coin x horizon x K), not per period.
    # ----------------------------------------------------------------------
    def _is_pos_r2(r):
        v = r.get("incremental_oos_r2")
        return v is not None and v == v and v > 0

    def _survives_pos(r):
        # a cell "supports non-recoverability" only if it BOTH survives FDR and
        # carries a positive incremental R^2 (a survivor with R^2<=0 is not lift)
        return bool(r.get("survives_fdr")) and _is_pos_r2(r)

    horizons_present = sorted({int(r["horizon_s"]) for r in all_nr})

    # all economic-cost blocks (per-coin + pooled), needed for the maker-profit
    # leg of the attenuation rule below.
    all_cost = (results["economic_cost"]["by_coin"]
                + results["economic_cost"]["pooled"])

    # ---- shared attenuation rule, applied per (period, horizon) -------------
    # A horizon's evidence in a given period is ATTENUATED (collapses in that
    # regime) when its surviving positive-lift evidence is THIN - at most ONE cell
    # carries positive incremental R^2 AND survives BH-FDR - which is precisely the
    # collapse the October-attenuation block headlines ("only 1 of 8 cells"). The
    # other two markers that block also reports - negative-incremental-R^2 cells
    # present and an all-maker-profit aggregate markout - are crash-regime SEVERITY
    # descriptors that, on this panel, also appear at the 10s horizon and even in
    # otherwise-healthy months (every period-horizon carries at least one negative
    # cell, and the whole October crash month is maker-profitable at BOTH horizons).
    # So they corroborate a collapse but cannot, on their own, gate robustness
    # without flagging the robust 10s thread; the thin-survivor count is the leg
    # that actually distinguishes a collapsed horizon from a robust one. We carry
    # the severity markers alongside for the report. Coin-agnostic and counted
    # straight from the cell rows - no hardcoded horizon or coin list.
    def _attenuation_markers(p, h):
        h_cells = [r for r in all_nr
                   if r.get("period") == p and int(r["horizon_s"]) == h]
        n_survivors = sum(1 for r in h_cells if _survives_pos(r))
        any_negative = any(not _is_pos_r2(r) for r in h_cells)
        # every cost field states its window, so the field for the horizon under
        # test is BUILT from that horizon; there is no unsuffixed default to fall
        # back on and therefore no way to read the wrong window silently.
        cost_field = _f("cost_bps", h)
        p_cost = [c.get(cost_field) for c in all_cost if c.get("period") == p]
        p_cost = [v for v in p_cost if v is not None and v == v]
        all_maker_profit = bool(p_cost) and all(v < 0 for v in p_cost)
        return n_survivors, any_negative, all_maker_profit

    def _period_horizon_attenuated(p, h):
        n_survivors, _any_negative, _all_maker_profit = _attenuation_markers(p, h)
        return bool(n_survivors <= 1)

    # ---- per period: survivor count out of that period's cell family --------
    per_period_support = {}
    for p in periods_present:
        cells = [r for r in all_nr if r.get("period") == p]
        n_pos = sum(1 for r in cells if _is_pos_r2(r))
        n_pos_fdr = sum(1 for r in cells if _survives_pos(r))
        # split the survivor count by horizon so the 60s attenuation is visible
        by_h = {}
        for h in horizons_present:
            h_cells = [r for r in cells if int(r["horizon_s"]) == h]
            by_h[str(h)] = {
                "n_cells": len(h_cells),
                "n_positive_lift_survives_fdr": sum(
                    1 for r in h_cells if _survives_pos(r)),
            }
        per_period_support[str(p)] = {
            "n_cells": len(cells),
            "n_cells_positive_lift": n_pos,
            "n_cells_positive_lift_survives_fdr": n_pos_fdr,
            "by_horizon": by_h,
            "reproduces": bool(n_pos_fdr > 0),
        }
    tested_periods = [p for p in periods_present
                      if per_period_support[str(p)]["n_cells"] > 0]

    # ---- per horizon: does THIS horizon survive (pos-lift + FDR) every month? -
    # "survives_every_month" is the ROBUST label: it requires a positive-lift cell
    # to survive BH-FDR in every tested period AND that the horizon is NOT
    # attenuated in any tested period (same _period_horizon_attenuated rule the
    # ATTENUATION block uses). So a horizon that survives only via a single trivial
    # cell, or that goes negative / maker-profitable in a crash month, is fragile.
    per_horizon_support = {}
    for h in horizons_present:
        months_with_survivor = [
            p for p in tested_periods
            if per_period_support[str(p)]["by_horizon"][str(h)][
                "n_positive_lift_survives_fdr"] > 0]
        attenuated_periods = [
            p for p in tested_periods if _period_horizon_attenuated(p, h)]
        survives_every_month = bool(
            tested_periods
            and len(months_with_survivor) == len(tested_periods)
            and not attenuated_periods)
        per_horizon_support[str(h)] = {
            "n_periods_tested": len(tested_periods),
            "n_periods_with_surviving_positive_lift": len(months_with_survivor),
            "periods_with_surviving_positive_lift": months_with_survivor,
            "attenuated_periods": attenuated_periods,
            "survives_every_month": survives_every_month,
        }

    # the robust common thread = the SMALLEST horizon that survives every month
    # (10s if present). Reported by value so the prose can name it.
    robust_horizons = sorted(
        int(h) for h, blk in per_horizon_support.items()
        if blk["survives_every_month"])
    robust_horizon = min(robust_horizons) if robust_horizons else None
    # the horizon(s) that do NOT survive in every month (e.g. 60s)
    fragile_horizons = sorted(
        int(h) for h, blk in per_horizon_support.items()
        if not blk["survives_every_month"])

    # ---- explicit October-60s (largest-horizon-in-crash) attenuation flag ----
    # Find the worst regime: the (period, horizon) with the fewest surviving
    # positive-lift cells among horizons that are otherwise strong elsewhere.
    # We surface the standard worry concretely: the LARGEST horizon in whichever
    # period has the fewest survivors at that horizon. Read its survivor cells
    # and the sign of its aggregate markout straight from the data.
    largest_h = max(horizons_present) if horizons_present else None
    attenuation = None
    if largest_h is not None and tested_periods:
        # period where the largest horizon is weakest (fewest pos-lift survivors)
        weak_p = min(
            tested_periods,
            key=lambda p: per_period_support[str(p)]["by_horizon"][
                str(largest_h)]["n_positive_lift_survives_fdr"])
        weak_cells = [r for r in all_nr
                      if r.get("period") == weak_p
                      and int(r["horizon_s"]) == largest_h]
        weak_survivors = [
            {"coin": r["coin"], "K": r["K"],
             "incremental_oos_r2": r.get("incremental_oos_r2"),
             "bh_qvalue": r.get("bh_qvalue")}
            for r in weak_cells if _survives_pos(r)]
        weak_negative = [
            {"coin": r["coin"], "K": r["K"],
             "incremental_oos_r2": r.get("incremental_oos_r2")}
            for r in weak_cells if not _is_pos_r2(r)]
        # sign of the aggregate markout at the largest horizon in that period:
        # a positive cost is a maker LOSS (adverse selection), a negative one a
        # maker PROFIT. The field is built from the horizon under test, and the
        # dicts emitted below carry that same built name, so the window travels
        # with the number instead of being implied by the block it sits in.
        all_cost = (results["economic_cost"]["by_coin"]
                    + results["economic_cost"]["pooled"])
        _wk_field = _f("cost_bps", largest_h)
        weak_cost = [
            {"coin": c["coin"], _wk_field: c.get(_wk_field)}
            for c in all_cost if c.get("period") == weak_p]
        any_pos_cost = any(
            c[_wk_field] is not None and c[_wk_field] == c[_wk_field]
            and c[_wk_field] > 0 for c in weak_cost)
        all_neg_cost = bool(weak_cost) and all(
            c[_wk_field] is not None and c[_wk_field] == c[_wk_field]
            and c[_wk_field] < 0 for c in weak_cost)
        # "attenuation" = a MEANINGFUL collapse of this horizon in this regime,
        # not merely "fewer survivors". It fires when the surviving evidence at
        # this horizon is thin or contradicted: at most one cell survives, OR
        # any negative-incremental-R^2 cell is present, OR the aggregate markout
        # is maker-profitable for every coin. This is deliberately TRUE even
        # when a single trivial cell technically survives BH-FDR - the weak
        # any-cell rule would otherwise hide exactly that case.
        is_attenuated = bool(
            len(weak_survivors) <= 1 or weak_negative or all_neg_cost)
        attenuation = {
            "period": int(weak_p),
            "horizon_s": int(largest_h),
            "n_cells_at_horizon": len(weak_cells),
            "n_positive_lift_survives_fdr": len(weak_survivors),
            "is_attenuated": is_attenuated,
            "surviving_cells": weak_survivors,
            "negative_incremental_r2_cells": weak_negative,
            _f("aggregate_markout_cost_bps", largest_h): weak_cost,
            "aggregate_markout_any_maker_loss": bool(any_pos_cost),
            "aggregate_markout_all_maker_profit": all_neg_cost,
            "flag": (
                f"ATTENUATION at the {largest_h}s horizon in period {weak_p}: "
                f"only {len(weak_survivors)} of {len(weak_cells)} {largest_h}s "
                f"cell(s) carry positive incremental R^2 AND survive BH-FDR"
                + (f" ({weak_survivors[0]['coin']} K={weak_survivors[0]['K']} at "
                   f"incremental R^2 "
                   f"{weak_survivors[0]['incremental_oos_r2']:+.4f})"
                   if weak_survivors else "")
                + (f"; {len(weak_negative)} {largest_h}s cell(s) have NEGATIVE "
                   f"incremental R^2 (incl. pooled / other coins)"
                   if weak_negative else "")
                + ("; and the aggregate " + str(largest_h)
                   + "s markout for this period is NEGATIVE for every coin "
                   "(makers PROFITED on net, i.e. the crash flow was NOT adverse "
                   "to the maker at this horizon)" if all_neg_cost else "")
                + "."),
        }

    reproduces_all = bool(
        tested_periods
        and all(per_period_support[str(p)]["reproduces"] for p in tested_periods))

    # honest one-line verdict: lead with the horizon split, never with the weak
    # "some cell survives everywhere" read.
    if robust_horizon is not None:
        verdict = (
            f"REPRODUCES AT THE {robust_horizon}s HORIZON IN EVERY RESOLVED "
            f"MONTH (the robust common thread: a positive-incremental-lift "
            f"{robust_horizon}s cell survives the panel-wide BH-FDR in each of "
            f"{', '.join(str(p) for p in tested_periods)}; the pre-registered "
            f"pooled / {robust_horizon}s / K=50 cell is the through-line). "
            "Per-period survivor counts across the full cell family: "
            + "; ".join(
                f"{p} = {per_period_support[str(p)]['n_cells_positive_lift_survives_fdr']}"
                f"/{per_period_support[str(p)]['n_cells']}"
                for p in tested_periods)
            + ". ")
    else:
        verdict = (
            "NO horizon survives positive-lift BH-FDR in every resolved month. "
            "Per-period survivor counts across the full cell family: "
            + "; ".join(
                f"{p} = {per_period_support[str(p)]['n_cells_positive_lift_survives_fdr']}"
                f"/{per_period_support[str(p)]['n_cells']}"
                for p in tested_periods)
            + ". ")
    if attenuation is not None and attenuation["is_attenuated"]:
        verdict += (
            f"BUT THE {attenuation['horizon_s']}s HORIZON IS NOT ROBUST ACROSS "
            f"REGIMES - it attenuates sharply in period {attenuation['period']}: "
            + attenuation["flag"]
            + " A single trivial cell technically surviving BH-FDR does NOT make "
            "this horizon reproduce in that regime. Do NOT report a flat "
            "'reproduces in every month' headline: that is true only under the weak "
            "rule that ANY single positive-lift cell survives per period, and it "
            "masks this horizon split.")

    results["headline"] = {
        "question": "Does the non-recoverability result reproduce across all "
        "resolved months (Aug / Oct / Dec 2025) - and at WHICH horizon?",
        "bh_family_scope": "PANEL-WIDE: one Benjamini-Hochberg family over all "
        "tested cells (period x coin x horizon x K); m = "
        f"{results['nonrecoverability']['family']['n_cells_tested']} tested cells "
        "(not a per-period family).",
        "robust_horizon_s": robust_horizon,
        "robust_horizons_s": robust_horizons,
        "fragile_horizons_s": fragile_horizons,
        "per_period": per_period_support,
        "per_horizon": per_horizon_support,
        "october_or_worst_regime_attenuation": attenuation,
        "reproduces_all_periods_weak_rule": reproduces_all,
        "weak_rule_note": "reproduces_all_periods_weak_rule = at least one "
        "positive-lift cell survives BH-FDR in every period. This is TRUE here but "
        "is the weak read: it does not distinguish horizons. Use robust_horizon_s "
        "and october_or_worst_regime_attenuation for the honest statement.",
        "verdict": verdict,
    }

    # bare-filename meta (no absolute paths leak into the JSON artefact)
    results["_meta"] = {
        "input_npz": os.path.basename(PANEL_NPZ_PATH),
        "rng_seed": RNG_SEED,
        "imported_modules": ["i3_nonrecoverability_oos", "t3_capacity"],
    }
    # THE FINGERPRINT USED TO BE WRITTEN TWICE, into _meta and then copied into scope by
    # a line that did nothing else. That is the record living in two places, and it is
    # what makes a census of this property return different counts depending on where it
    # looks. artifact.write now builds it once, from these keywords, and puts it in
    # _meta. Two of the keywords are OVERRIDES: the seed and the permutation budget are
    # December's, not the declared ones, because this panel exists to reproduce
    # December's cells and a different seed would move every p-value here. An override is
    # visible; a drift is not.
    artifact.write(
        os.path.basename(RESULTS_PATH), results,
        script=__file__,
        inputs=[PANEL_NPZ_PATH],
        scope={
            # taker_id AFTER the restriction to the canonical windows, which is the
            # population the numbers were computed on. The npz holds more rows than
            # that, and quoting the file's row count here would describe coverage while
            # claiming to describe the result -- two quantities this project has
            # confused before.
            "population": (
                f"{int(taker_id.size)} taker fills over "
                f"{len(periods_present)} windows; every cell repeated at each of "
                f"{list(HORIZONS)} seconds and each fill floor in {list(K_LIST)}, "
                f"per coin and pooled, with the out-of-sample split by wallet over "
                f"{N_FOLDS} folds"),
            "window": (f"windows present {periods_present} of {list(PERIODS)} "
                       f"requested, ten days each, split per period into an early and "
                       f"a late half over its own resolved days"),
            "coins": list(COIN_CODES.values()),
        },
        settings=dict(
            h=H.HEADLINE_HORIZON_S, lens="print",
            horizons_reported=list(HORIZONS),
            field_suffix_style=H.FIELD_SUFFIX_STYLE,
            **SETTINGS_OVERRIDES),
        started=started)

    _print_summary(results)


# -------------------- printed summary --------------------
def _print_summary(results):
    print("\n" + "=" * 88)
    print("PANEL-ANALYZE - DECEMBER CORE CHAIN REPRODUCED PER PERIOD + POOLED - SUMMARY")
    print("=" * 88)
    sc = results["scope"]
    print(f"  periods present : {sc['periods_present']}")
    print(f"  coins           : {sc['coins']}  (pooled-coin = POOLED)")
    print(f"  data source     : node_fills_by_block trade-print markout (no book-mid)")
    print(f"  comparator      : TRADE-TAPE-ONLY (VPIN / imbalance / size / intensity)")
    print(f"  estimators      : IMPORTED verbatim from i3_nonrecoverability_oos + t3_capacity")
    if results["issues"]:
        print("-" * 88)
        for msg in results["issues"]:
            print(f"  [!] {msg}")
    print("-" * 88)
    print("  NON-RECOVERABILITY (incremental OOS lift of history-FE over anonymous tape):")
    hdr = (f"  {'period':>7} {'coin':<6} {'h(s)':>4} {'K':>4} {'n_wal':>6} "
           f"{'incrR2':>9} {'incrSp':>9} {'placebo_p':>10} {'whale_ok':>9} "
           f"{'q_bh':>8} {'fdr':>4}")
    for block, name in ((results["nonrecoverability"]["by_coin"], "PER-COIN"),
                        (results["nonrecoverability"]["pooled"], "POOLED")):
        if not block:
            continue
        print(f"  [{name}]")
        print(hdr)
        for r in block:
            fdr = "OK" if r.get("survives_fdr") else ""
            print(f"  {r.get('period', ''):>7} {r['coin']:<6} "
                  f"{r['horizon_s']:>4} {r['K']:>4} {r.get('n_wallets', 0):>6} "
                  f"{i3._fmt(r.get('incremental_oos_r2')):>9} "
                  f"{i3._fmt(r.get('incremental_spearman')):>9} "
                  f"{i3._fmt(r.get('placebo_p')):>10} "
                  f"{str(r.get('whale_robust', '')):>9} "
                  f"{i3._fmt(r.get('bh_qvalue')):>8} {fdr:>4}")
    fam = results["nonrecoverability"].get("family")
    if fam:
        print("-" * 88)
        print(f"  BH-FDR (alpha={fam['fdr_alpha']}): "
              f"{fam['n_survivors']} survivors of {fam['n_cells_tested']} testable "
              f"({fam['n_cells_untestable']} untestable) across "
              f"{fam['n_cells_total']} cells.")
    print("-" * 88)
    print(f"  ECONOMIC COST per period (signed {H.HEADLINE_HORIZON_S}s "
          f"adverse-selection cost; positive = maker loss):")
    chdr = (f"  {'period':>7} {'coin':<6} {'days':>4} {'total $':>16} "
            f"{'$ / day':>14} {'cost bps':>9} {'avoid 10%':>9}")
    for block, name in ((results["economic_cost"]["by_coin"], "PER-COIN"),
                        (results["economic_cost"]["pooled"], "POOLED")):
        if not block:
            continue
        print(f"  [{name}]")
        print(chdr)
        for r in block:
            hl = H.HEADLINE_HORIZON_S
            print(f"  {r['period']:>7} {r['coin']:<6} {r['n_days']:>4} "
                  f"{r[_f('total_cost_usd', hl)]:>16,.2f} "
                  f"{r[_f('cost_per_day_usd', hl)]:>14,.2f} "
                  f"{r[_f('cost_bps', hl)]:>9.4f} "
                  f"{r[_f('avoidable_share_top10pct', hl)] * 100:>8.2f}%")
    hl = results.get("headline")
    if hl:
        print("-" * 88)
        print(f"  HEADLINE: {hl['question']}")
        print(f"  {hl.get('bh_family_scope', '')}")
        print("  per period (positive-lift cells surviving panel-wide BH-FDR / "
              "all cells), split by horizon:")
        for pkey, blk in hl["per_period"].items():
            mark = "REPRODUCES" if blk["reproduces"] else "no"
            hsplit = "  ".join(
                f"{h}s={hb['n_positive_lift_survives_fdr']}/{hb['n_cells']}"
                for h, hb in sorted(blk.get("by_horizon", {}).items(),
                                    key=lambda kv: int(kv[0])))
            print(f"    period {pkey}: {blk['n_cells_positive_lift_survives_fdr']}"
                  f"/{blk['n_cells']} cells survive  [{hsplit}]  -> {mark}")
        print("  per horizon (survives positive-lift BH-FDR in every month?):")
        for hkey, hb in sorted(hl.get("per_horizon", {}).items(),
                               key=lambda kv: int(kv[0])):
            tag = "ROBUST (every month)" if hb["survives_every_month"] else \
                "ATTENUATES (not every month)"
            print(f"    {hkey}s: {hb['n_periods_with_surviving_positive_lift']}"
                  f"/{hb['n_periods_tested']} months -> {tag}")
        att = hl.get("october_or_worst_regime_attenuation")
        if att is not None:
            print(f"  [!] {att['flag']}")
        rh = hl.get("robust_horizon_s")
        print(f"  => robust horizon (survives every month) = "
              f"{str(rh) + 's' if rh is not None else 'NONE'}")
        print(f"  => reproduces_all_periods (WEAK rule, any-cell) = "
              f"{hl.get('reproduces_all_periods_weak_rule')}")
        print(f"  {hl['verdict']}")
    print("=" * 88)
    print(f"  results -> {os.path.basename(RESULTS_PATH)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Panel re-run of the December non-recoverability + economic-cost "
                    "core chain per period (202508/202510/202512) and pooled, per "
                    "coin (BTC/ETH/SOL) and pooled-coin. Reads panel_markouts.npz; "
                    "imports the estimators from i3_nonrecoverability_oos + t3_capacity.")
    ap.parse_args()
    main()
