"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-19
References: Hyperliquid node-data S3 archive; Zenodo 18184441 (Albers et al. 2026).
"""

# ---------------------------------------------------------------------------
# OBJECT T3 - ECONOMIC MAGNITUDE / CAPACITY OF AVOIDABLE ADVERSE-SELECTION COST.
#
# This is the single non-technical number of the study: how large,
# in plain dollars, is the maker's gross loss to taker adverse selection over
# the resolved window, and what share of it is concentrated in a small set of
# persistently toxic wallets (the "in principle avoidable" portion).
#
# The $/day figure divides by the number of distinct resolved days actually
# present in the npz (derived at runtime, NOT hardcoded), so a partial window
# (e.g. 7 of 10 days resolved) is not understated, and a future full re-run
# self-labels with the day count it actually resolved.
#
# Two markout horizons are computed throughout. The 10s horizon is the HEADLINE
# (the horizon study ws1_horizon_persistence.py selects 10s as the scoring
# horizon); the 60s horizon is the robustness COMPANION. Each horizon is computed
# end to end on itself, so neither cell mixes horizons.
#
# HOW THE KEYS ARE NAMED, and what this file used to do instead. Every key whose
# value depends on the scoring window states that window: cost_bps_10s is the
# headline, cost_bps_60s is the companion, and NO key is left unsuffixed. The
# convention is declared once, in settings.FIELD_SUFFIX_STYLE, and every key is
# BUILT by settings.field_name rather than typed here.
#
# Until 2026-07-30 this file did the opposite: it suffixed the headline _10s and
# left the 60s companion unsuffixed "for backward compatibility", while
# panel_analyze.py left the HEADLINE unsuffixed and suffixed the companion _60s.
# Both files emitted a key spelled exactly cost_bps, so that one name carried a
# 10s number in one artifact and a 60s number in the other, and a reader comparing
# the two read one name as two different quantities without anything raising. An
# unsuffixed key cannot say which of the two conventions it belongs to, which is
# why there is now no unsuffixed key. The old spellings and their replacements are
# listed in the migration note beside RESULTS_PATH below.
#
# Per coin and pooled, over the resolved days:
#   - Total taker-side adverse-selection COST = sum over rows of
#       (markout_bps / 1e4) * notional
#     i.e. the maker's gross loss to taker adverse selection, computed at the 10s
#     horizon (headline, keys *_10s) and at the 60s horizon (companion, keys
#     *_60s). mo* are SIGNED taker markouts in bps; positive = taker profited =
#     maker bore adverse selection, so a positive total cost is a maker loss.
#   - Expressed three ways: total $ over the window, $/day, and in bps of total
#     notional (the bps figure equals the volume-weighted mean markout).
#   - "Avoidable" portion (OUT-OF-SAMPLE). Over wallets eligible by the rank floor
#     in the EARLY half of the window, rank wallets by their EARLY gross cost, then
#     MEASURE the share of LATE gross POSITIVE cost captured by (a) the
#     early-ranked top decile and (b) the early-ranked top-50. Which days are early
#     and which are late is DERIVED from the days the npz actually carries, by
#     settings.split_early_late, and is never a hardcoded day-of-month tuple.
#     Ranking and measurement use the SAME horizon within a cell: the headline
#     ranks on 10s and measures on 10s, the companion ranks on 60s and measures on
#     60s. The ranking window (early) and the measurement window (late) are
#     DISJOINT, so the share is honest: it is the late cost a maker who screened
#     wallets on their early behaviour would have avoided. Reported beside a
#     RANDOM-selection floor (random wallet sets of the same size) and a
#     rank-on-late ORACLE ceiling so the lift over chance is visible.
#   - The old IN-SAMPLE concentration (rank and measure on the same all-days cost)
#     is retained ONLY as a relabelled "in_sample_concentration" diagnostic; it is
#     NOT the avoidable number, because ranking on the cost you then concentrate is
#     bounded toward 100% by construction.
#
# HONEST FRAMING (hard requirement). This is a GROSS, UPPER-BOUND number, NOT a
# net trading edge or alpha. The raw volume-weighted mean markout is sub-1 bps,
# while perp TAKER FEES (~2.5-4.5 bps) plus FUNDING swamp it. A maker does not
# "earn" this by trading; it is a recurring, partly-avoidable COST that better
# counterparty screening can reduce. The raw mean markout in bps is printed
# directly next to the ~2.5-4.5 bps fee band so the comparison is unavoidable.
#
# numpy-only. Reads ONE shared intermediate (quickwin_markouts.npz) produced by
# the expensive orchestrator pass. Does NOT parse raw data here.
#
# Run command (bare python3 is BLOCKED on this machine):
#   uv run --no-project --with-requirements requirements.txt python3 money/t3_capacity.py
# ---------------------------------------------------------------------------

import os
import sys

import numpy as np

# artifact.py, settings.py and the other shared modules sit in the
# repository root, one directory up from this group, so the path is built
# from this file's own location and never from the working directory the
# run happens to start in.
_CODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CODE_DIR not in sys.path:
    sys.path.insert(0, _CODE_DIR)

import artifact
import panel_io as P
import settings as H

# Scored at the headline window with the long companion column kept beside it for
# robustness. Both names come from settings.py; no window is declared here.

# -------------------- configuration --------------------
HERE = os.path.dirname(os.path.abspath(__file__))
# Located by panel_io rather than joined here, so the one place that knows where
# the markout panels live is the one place that has to change if they move.
NPZ_PATH = os.path.join(P.data_root(), "quickwin_markouts.npz")
RESULTS_PATH = os.path.join(HERE, "t3_results.json")

# KEY MIGRATION, 2026-07-30. Every key in t3_results.json now states its window.
# A citation to an earlier spelling is traced through this table:
#   cost_bps                          -> cost_bps_60s
#   total_cost_usd                    -> total_cost_usd_60s
#   cost_per_day_usd                  -> cost_per_day_usd_60s
#   raw_mean_markout_bps              -> raw_mean_markout_bps_60s
#   avoidable_share_oos_top10pct      -> avoidable_share_oos_top10pct_60s
#   avoidable_share_oos_top50         -> avoidable_share_oos_top50_60s
#   avoidable                         -> avoidable_60s
#   _diag.total_notional_usd          -> _diag.total_notional_usd_60s
# and inside each avoidable block every key gains its window plus, for the
# whale-drop ladder, its criterion:
#   drop_top_k_top10pct.{10,50,100}   -> whale_drop_ladder_top10pct_<h>s
#                                        .drop_top{10,50,100}_by_gross_cost
#   drop_top_k_top50.{10,50,100}      -> whale_drop_ladder_top50_<h>s
#                                        .drop_top{10,50,100}_by_gross_cost
# The keys already carrying _10s keep their spelling. No VALUE moves: the same
# number is written under a name that says which window produced it.

COIN_CODES = H.coin_labels("quickwin")   # the map belongs to the FILE, not the project

# THE EARLY-AND-LATE SPLIT IS DERIVED, NOT DECLARED. These two names are OVERRIDE
# HOOKS and default to None, which means "split the days the input actually
# carries" through settings.split_early_late. They used to be the literal tuples
# (4,5,6,7,8) and (9,10,11,12,13), which are days of the MONTH and are right only
# for a window that opens on the 4th and closes on the 13th. The December window
# this file reads does open on the 4th, so the derived split reproduces those
# tuples exactly and no number here moves; a twelve-day window would have been
# split three-against-seven, or had two of its days silently discarded.
#
# The hooks stay because panel_analyze.py runs these estimators on a MULTI-MONTH
# panel and sets EARLY_DAYS_OVERRIDE to each period's own early half for the duration
# of one call. Setting EARLY_DAYS_OVERRIDE alone is enough: the late half is then every
# present day that is not early, so an injected early half can no longer leave the late
# half on another month's day numbers.
#
# WHY THEY CARRY _OVERRIDE IN THE NAME, renamed here 2026-07-31, following gm_quoter.py,
# which took the same suffix earlier that day in commit ff3b8fe.
# They used to be spelled EARLY_DAYS and LATE_DAYS, which are
# the names settings.py owns for the day split, and the settings gate read them as this
# file declaring that setting a second time -- two of the sites it reports. The reading
# was right about the name and wrong about the value: there is no value here to migrate,
# because the split already comes from settings.py and what these two hold is the
# ABSENCE of an override. A name that states a setting its value does not come from is
# the defect settings.py calls out in its own second rule, so the repair is to make the
# name say what the object is. Two places read these names -- _per_wallet_cost and
# main() below -- and one place writes one of them, panel_analyze.py, which was renamed
# in the same pass. None before, None after, so the rename moves no number.
EARLY_DAYS_OVERRIDE = None
LATE_DAYS_OVERRIDE = None

MIN_EARLY_TRADES = H.RANK_FLOOR_FILLS   # trade floor for a wallet to enter the ranking

# THIS FILE SELECTS BY SUMMED DOLLAR COST, AND THAT IS A DIFFERENT OBJECT FROM THE
# STUDY'S DECLARED SELECTION, so the names say which one they mean. The declared
# selection orders counterparties by their MEAN book-mid markout in basis points and
# takes ceil(10% x N). What is ordered here is each counterparty's SUMMED early dollar
# adverse-selection cost, and the cut takes max(1, floor(10% x N)). Ranking by a rate
# and ranking by a total answer different questions -- who is dearest per fill against
# who is dearest in aggregate -- and they do not return the same tail, so calling both
# of them "the toxic decile" made one word carry two sets. The fraction below is
# therefore named for what it cuts and not for the word decile.
DOLLAR_COST_TOP_FRAC = 0.10    # top-10% of wallets ranked by summed dollar cost
TOP_N = 50                     # top-50 wallets by persistent toxicity
PER_TAKER_FEE_BPS = (2.5, 4.5)  # perp taker fee band for the honest comparison

# robustness configuration (DEFECT FIX 2026-06-19)
# DROP_TOP_K is the ladder; WHALE_DROP_CRITERION says what "largest" is measured in,
# because dropping the ten largest by NOTIONAL answers "is this a volume artifact"
# while dropping the ten largest by COST answers "is this ten wallets", and the two
# questions have different answers. This file has always dropped by cost -- the
# largest per-wallet signed adverse-selection cost in the MEASUREMENT (late) half,
# at the cell's own horizon -- and used to write the result under a key naming only
# the count. settings.whale_drop builds a key that states both.
DROP_TOP_K = H.WHALE_DROP_LADDER
WHALE_DROP_CRITERION = "gross_cost"
BOOTSTRAP_N = H.boot_draws("t3_capacity")    # resamples over wallets for the headline
                               # 95% CI, READ from settings.py, which since 2026-07-31
                               # is the declared N_BOOT. This file's published interval
                               # was drawn at 1000, half of it, so the two endpoints
                               # move and the point estimate they bracket does not
BOOTSTRAP_SEED = H.seed_for("t3_capacity")   # fixed seed for reproducible CI, READ from
                               # settings.py; the value is the same 20260619 this file
                               # has always drawn, so the interval does not move
# Both of the two lines above are READ from settings.py and neither is typed here, and
# the two are now in DIFFERENT positions against the headline declaration. The bootstrap
# budget agreed with it on 2026-07-31: the per-purpose map holds N_BOOT for every
# consumer, so this file draws the declared 2000 against the 1000 its published interval
# was drawn at, and that adoption is what the recompute of this node pays for. The seed
# has not moved -- settings.MASTER_SEED is 20260620 against the 20260619 the per-purpose
# seed map records -- so adopting it is still owed its own recompute rather than a silent
# switch inside a renaming pass. Both stay recorded in the settings fingerprint, the
# budget now as a confirmation and the seed still as an override, because the fingerprint
# compares a run against the HEADLINE declaration and not against the map that records
# what the tree currently holds.
#
# WHY THE SPELLING MATTERED. checks/chk_settings_home.py never counted this budget: its
# alias list carries N_BOOT and N_BOOTSTRAP, and this file writes BOOTSTRAP_N, so the
# site was invisible to the gate rather than absent from the tree. The gate's own note
# says its figure is a floor for exactly this reason. Reading the value from the
# declaration closes the site whether or not the alias list is ever widened.

# out-of-sample avoidable-share configuration (METHODOLOGY FIX 2026-06-20)
# The headline avoidable share is OUT-OF-SAMPLE: wallets are ranked on their EARLY
# gross cost and the captured share is measured on the disjoint LATE gross POSITIVE
# cost. A random-selection floor (same cut sizes, many draws) and a rank-on-late
# ORACLE ceiling bracket the lift.
RANDOM_DRAWS = 1000            # random wallet-set draws for the selection floor
RANDOM_SEED = H.MASTER_SEED    # the one seed; its literal value here was already 20260620

# WHY THIS FILE DOES NOT IMPORT stats.py, examined 2026-07-31 rather than left silent.
# stats.py owns the three statistical procedures this work reports -- the permutation
# p-value, the percentile bootstrap interval and the multiplicity correction -- and five
# files in the tree have moved onto it. This one has moved onto none, and each of the
# three has a different reason.
#
# The PERMUTATION does not apply. Nothing here permutes a label. The random-selection
# floor below draws random wallet SETS of the fixed cut sizes and reports their mean and
# 95th percentile as a floor to compare the ranked share against; no p-value is computed
# from it and none is written out, which is the same thing _meta says under n_perm.
#
# The CORRECTION does not apply either: this file reports no family of p-values.
#
# The BOOTSTRAP does apply, and it stays here for exactly one reason, the same one
# maker_econ.py records: the generator. stats.bootstrap_ci resamples with the identical
# generator.integers(0, n, size=n) call at the identical alpha and takes the same
# percentiles, but it builds its stream from the master seed and the named cell and
# accepts no generator argument. This file's interval was published from
# default_rng(BOOTSTRAP_SEED) with BOOTSTRAP_SEED at 20260619, and MASTER_SEED is
# 20260620, so the move would re-draw every resample and shift both endpoints. That is a
# measured change owed its own recompute, not something to slip inside a rename.

WHALE_RULE = (
    "RULE: never present a point avoidable-% without its whale-dropped companion. "
    "The companions are the drop-top-10/50/100 ladder, dropped by GROSS COST (the "
    "largest per-wallet signed cost in the measurement half, not the largest by "
    "notional), and the leave-one-out of the single largest such wallet. Both are "
    "reported beside every headline share."
)

FEE_NOTE = (
    "GROSS, UPPER-BOUND avoidable cost - NOT a net trading edge or alpha. "
    "The raw volume-weighted mean markout is sub-1 bps, while perp taker fees "
    "(~2.5-4.5 bps) plus funding swamp it. This is a recurring, partly-avoidable "
    "COST that counterparty screening can reduce, not money a maker earns by trading."
)


# -------------------- helpers --------------------
def _safe_div(num, den):
    """num / den with a 0.0 result when the denominator is non-finite or zero."""
    if den is None or not np.isfinite(den) or den == 0.0:
        return 0.0
    return float(num / den)


def _cost_block(mo_bps, notional, n_days):
    """Cost summary for one signed-markout column over a set of rows.

    Cost per row = (markout_bps / 1e4) * notional. Positive total = maker loss.
    Only rows with a finite markout AND a finite notional contribute.
    Returns total $, $/day, cost in bps of total notional (= volume-weighted
    mean markout), the summed notional used, and the number of contributing rows.
    """
    mo = np.asarray(mo_bps, dtype=np.float64)
    nt = np.asarray(notional, dtype=np.float64)
    valid = np.isfinite(mo) & np.isfinite(nt)
    mo, nt = mo[valid], nt[valid]
    cost_rows = (mo / 1e4) * nt
    total_cost = float(np.sum(cost_rows))
    total_notional = float(np.sum(nt))
    return {
        "total_cost_usd": total_cost,
        "cost_per_day_usd": _safe_div(total_cost, n_days),
        "cost_bps": _safe_div(total_cost, total_notional) * 1e4,
        "_total_notional": total_notional,
        "_n_rows": int(valid.sum()),
        "_cost_rows": cost_rows,
        "_valid_mask": valid,
    }


def _resolve_split(days_present, early_days=None, late_days=None):
    """The (early, late) day tuples for one call, derived unless overridden.

    Three cases, and the middle one is why this is a function. With neither
    override the days present are split by settings.split_early_late, which is a
    function OF THE DAYS and therefore right on a window of any length. With only
    early_days given -- the way panel_analyze.py drives these estimators, one
    period at a time -- the late half is every present day that is not early, so an
    injected early half cannot leave the late half on another month's day numbers.
    With both given they are used as passed, intersected with the days present.
    """
    present = sorted(int(d) for d in set(days_present))
    if early_days is None and late_days is None:
        return H.split_early_late(present)
    early = tuple(d for d in present if early_days is not None and d in set(
        int(x) for x in early_days))
    if late_days is None:
        late = tuple(d for d in present if d not in set(early))
    else:
        late = tuple(d for d in present if d in set(int(x) for x in late_days))
    return early, late


def _per_wallet_cost(taker_id, coin_mask, day, mo_bps, notional,
                     early_days=None, late_days=None):
    """Per-wallet EARLY / LATE / ALL-days adverse-selection cost for one slice.

    Horizon-generic: whichever markout column is passed as mo_bps is used for the
    ranking, the measurement and the eligibility count alike, so a cell built from
    this helper never mixes horizons. Called once with the 10s column (headline)
    and once with the 60s column (companion).

    The early and late halves are DERIVED from the days this slice actually carries
    (see _resolve_split), so the helper is right on a window of any length, and the
    halves it used are returned in diag so the artifact states them rather than
    promising them.

    Over the eligible population (>= MIN_EARLY_TRADES trades in the EARLY half),
    this returns three per-wallet signed-cost vectors aligned to the SAME wallet id
    order:
      - early_cost: signed cost over the wallet's EARLY rows only. This is the
                    held-out RANKING signal.
      - late_cost : signed cost over the wallet's LATE rows only. This is the
                    MEASUREMENT base for the out-of-sample share.
      - all_cost  : signed cost over ALL the wallet's in-scope rows (every
                    resolved day). Retained ONLY for the in-sample concentration
                    diagnostic, not the avoidable number.

    Wallets are NOT pre-sorted here; the ranking is applied per-window downstream
    so the same eligible set drives the OOS, in-sample, random and oracle blocks.

    Returns (ids, early_cost, late_cost, all_cost, diag). Each *_cost is the SIGNED
    per-wallet dollar cost; positive = the maker lost money to that wallet.
    """
    tid = np.asarray(taker_id, dtype=np.int64)
    day = np.asarray(day, dtype=np.int64)
    mo = np.asarray(mo_bps, dtype=np.float64)
    nt = np.asarray(notional, dtype=np.float64)

    in_scope = coin_mask & np.isfinite(mo) & np.isfinite(nt)
    cost_rows = (mo / 1e4) * nt

    diag = {"n_ranked_wallets": 0, "early_days": [], "late_days": []}

    s_tid = tid[in_scope]
    s_cost = cost_rows[in_scope]
    s_day = day[in_scope]
    empty = (np.empty(0, np.int64),) + (np.empty(0, np.float64),) * 3 + (diag,)
    if s_tid.size == 0:
        return empty

    uniq, inv = np.unique(s_tid, return_inverse=True)

    # The split is a function of the days in front of us, taken through
    # settings.split_early_late unless a caller injected a half explicitly.
    early_res, late_res = _resolve_split(np.unique(s_day), EARLY_DAYS_OVERRIDE,
                                         LATE_DAYS_OVERRIDE)
    diag["early_days"] = [int(d) for d in early_res]
    diag["late_days"] = [int(d) for d in late_res]

    early = np.isin(s_day, np.asarray(early_res, dtype=np.int64))
    late = np.isin(s_day, np.asarray(late_res, dtype=np.int64))

    # per-wallet cost in each window (and over all in-scope rows)
    all_cost = np.bincount(inv, weights=s_cost, minlength=uniq.size)
    early_cost = np.bincount(inv[early], weights=s_cost[early], minlength=uniq.size)
    late_cost = np.bincount(inv[late], weights=s_cost[late], minlength=uniq.size)

    # eligibility: >= MIN_EARLY_TRADES trades in the EARLY window (same gate as before).
    # NOTE on a horizon asymmetry: in_scope above already drops rows whose markout is
    # non-finite at THIS horizon, so e_counts counts only rows the current horizon can
    # score. The eligible population therefore moves slightly with the horizon. On the
    # pooled slice it is 2070 wallets at 10s against 2069 at 60s; the single wallet in
    # the difference has 50 finite early 10s rows but only 48 finite early 60s rows, so
    # it clears the 50-trade floor at 10s and misses it at 60s. This is expected, not a
    # defect, and it is why the wallet counts are reported per horizon rather than once.
    e_counts = np.bincount(inv[early], minlength=uniq.size)
    keep = e_counts >= MIN_EARLY_TRADES

    ids = uniq[keep].astype(np.int64)
    diag["n_ranked_wallets"] = int(ids.size)
    return (
        ids,
        early_cost[keep].astype(np.float64),
        late_cost[keep].astype(np.float64),
        all_cost[keep].astype(np.float64),
        diag,
    )


def _gross_share(costs_sorted, k):
    """Avoidable share of the top-k wallets on a GROSS positive-cost base.

    Base = sum of POSITIVE per-wallet cost (the gross adverse-selection bill a
    maker who screened nobody would pay). Numerator = sum of POSITIVE per-wallet
    cost among the top-k wallets by cost. Using the positive part on both sides
    makes the share monotone non-decreasing in k and bounded in [0, 1], unlike a
    signed-net denominator which can be a small fraction of gross and non-monotone.

    Expects costs_sorted already ordered most-costly-first (in-sample helper).
    """
    pos = np.maximum(costs_sorted, 0.0)
    gross = float(np.sum(pos))
    if gross == 0.0:
        return 0.0
    kk = min(int(k), pos.size)
    return _safe_div(float(np.sum(pos[:kk])), gross)


def _selected_share(measure_cost, sel_mask):
    """Share of GROSS positive MEASURE cost captured by a selected wallet set.

    Base = sum of positive measure cost over ALL wallets. Numerator = sum of
    positive measure cost over the selected wallets only. Selection is a boolean
    mask aligned to measure_cost; this lets the same routine serve the OOS
    (rank-on-early), oracle (rank-on-late) and random selections.
    """
    pos = np.maximum(np.asarray(measure_cost, dtype=np.float64), 0.0)
    gross = float(np.sum(pos))
    if gross == 0.0:
        return 0.0
    return _safe_div(float(np.sum(pos[np.asarray(sel_mask, dtype=bool)])), gross)


def _top_by_dollar_cost_mask(rank_cost, k):
    """Boolean mask selecting the top-k wallets by descending SUMMED DOLLAR cost.

    The quantity ordered is a total in dollars, not a rate in basis points, and that
    is what separates this selection from the study's declared one. Two counterparties
    with the same mean markout are ordered here by how much they traded, so this cut
    answers who is dearest in aggregate while the declared cut answers who is dearest
    per fill. The two tails overlap and are not the same set.
    """
    rc = np.asarray(rank_cost, dtype=np.float64)
    n = rc.size
    kk = min(int(k), n)
    mask = np.zeros(n, dtype=bool)
    if kk <= 0:
        return mask
    order = np.argsort(-rc, kind="stable")
    mask[order[:kk]] = True
    return mask


def _whale_key(k):
    """The whale-drop ladder key for one rung: the count AND what it is largest by.

    Built by settings.whale_drop so the criterion cannot be dropped from the name.
    """
    return H.whale_drop(WHALE_DROP_CRITERION, k)["key"]


def _empty_avoidable_block():
    """Zeroed avoidable block for an empty / degenerate slice."""
    return {
        "_gross_positive_late_cost_usd": 0.0,
        "_net_signed_late_cost_usd": 0.0,
        "net_over_gross_ratio_late": 0.0,
        "n_ranked_wallets": 0,
        "n_top_decile_wallets": 0,
        "n_top_n_wallets": 0,
        "avoidable_share_oos_top10pct": 0.0,
        "avoidable_share_oos_top50": 0.0,
        "random_floor_top10pct": {"mean": 0.0, "p95": 0.0, "n_draws": 0, "seed": RANDOM_SEED},
        "random_floor_top50": {"mean": 0.0, "p95": 0.0, "n_draws": 0, "seed": RANDOM_SEED},
        "oracle_ceiling_top10pct": 0.0,
        "oracle_ceiling_top50": 0.0,
        "whale_drop_ladder_top10pct": {_whale_key(k): 0.0 for k in DROP_TOP_K},
        "whale_drop_ladder_top50": {_whale_key(k): 0.0 for k in DROP_TOP_K},
        "leave_one_out_largest": {
            "wallet_id": 0,
            "wallet_late_cost_usd": 0.0,
            "wallet_late_cost_share_of_gross": 0.0,
            "top10pct_before": 0.0, "top10pct_after": 0.0,
            "top50_before": 0.0, "top50_after": 0.0,
        },
        "bootstrap_ci_oos_top10pct": {
            "lo": 0.0, "hi": 0.0, "n_resamples": 0, "seed": BOOTSTRAP_SEED,
        },
        "in_sample_concentration": {
            "note": "DIAGNOSTIC ONLY - rank and measure on the SAME all-days cost; "
                    "bounded toward 100% by construction, NOT the avoidable number.",
            "share_top10pct": 0.0,
            "share_top50": 0.0,
            "_gross_positive_all_cost_usd": 0.0,
        },
        "whale_rule": WHALE_RULE,
    }


def _avoidable_block(ids, early_cost, late_cost, all_cost, diag):
    """OUT-OF-SAMPLE avoidable share + robustness, with floor / oracle / in-sample.

    Rank wallets on their EARLY (days 4-8) gross cost, measure the captured share
    of LATE (days 9-13) gross POSITIVE cost for the top-decile and top-50 cuts.
    Both cost vectors come from the same markout horizon (see _per_wallet_cost),
    so the block is horizon-generic and is built once for 10s and once for 60s.
    The ranking and measurement windows are disjoint, so the share is honest.
    Reported beside:
      - a RANDOM-selection floor (random wallet sets of the same cut size),
      - a rank-on-late ORACLE ceiling,
      - the old IN-SAMPLE concentration (relabelled diagnostic, NOT avoidable),
      - drop-top-K / leave-one-out / bootstrap robustness on the LATE-cost base.
    """
    n_ranked = int(ids.size)
    late_pos = np.maximum(late_cost, 0.0)
    gross_late = float(np.sum(late_pos))
    net_late = float(np.sum(late_cost))

    if n_ranked == 0 or gross_late == 0.0:
        out = _empty_avoidable_block()
        out["n_ranked_wallets"] = n_ranked
        return out

    n_decile = max(1, int(np.floor(n_ranked * DOLLAR_COST_TOP_FRAC)))
    n_top_n = min(TOP_N, n_ranked)

    out = {
        "_gross_positive_late_cost_usd": round(gross_late, 2),
        "_net_signed_late_cost_usd": round(net_late, 2),
        "net_over_gross_ratio_late": round(_safe_div(net_late, gross_late), 4),
        "n_ranked_wallets": n_ranked,
        "n_top_decile_wallets": n_decile,
        "n_top_n_wallets": n_top_n,
    }

    # ---- HEADLINE: out-of-sample share (rank on EARLY, measure on LATE) ----
    sel_decile = _top_by_dollar_cost_mask(early_cost, n_decile)
    sel_topn = _top_by_dollar_cost_mask(early_cost, n_top_n)
    share_oos_decile = _selected_share(late_cost, sel_decile)
    share_oos_topn = _selected_share(late_cost, sel_topn)
    out["avoidable_share_oos_top10pct"] = round(share_oos_decile, 4)
    out["avoidable_share_oos_top50"] = round(share_oos_topn, 4)

    # ---- random-selection floor (same cut sizes, many draws) ----
    rng_r = np.random.default_rng(RANDOM_SEED)
    rand_decile = np.empty(RANDOM_DRAWS, dtype=np.float64)
    rand_topn = np.empty(RANDOM_DRAWS, dtype=np.float64)
    for r in range(RANDOM_DRAWS):
        perm = rng_r.permutation(n_ranked)
        md = np.zeros(n_ranked, dtype=bool)
        md[perm[:n_decile]] = True
        mt = np.zeros(n_ranked, dtype=bool)
        mt[perm[:n_top_n]] = True
        rand_decile[r] = _selected_share(late_cost, md)
        rand_topn[r] = _selected_share(late_cost, mt)
    out["random_floor_top10pct"] = {
        "mean": round(float(np.mean(rand_decile)), 4),
        "p95": round(float(np.percentile(rand_decile, 95)), 4),
        "n_draws": RANDOM_DRAWS,
        "seed": RANDOM_SEED,
    }
    out["random_floor_top50"] = {
        "mean": round(float(np.mean(rand_topn)), 4),
        "p95": round(float(np.percentile(rand_topn, 95)), 4),
        "n_draws": RANDOM_DRAWS,
        "seed": RANDOM_SEED,
    }

    # ---- oracle ceiling (rank on LATE itself = best achievable selection) ----
    out["oracle_ceiling_top10pct"] = round(
        _selected_share(late_cost, _top_by_dollar_cost_mask(late_cost, n_decile)), 4)
    out["oracle_ceiling_top50"] = round(
        _selected_share(late_cost, _top_by_dollar_cost_mask(late_cost, n_top_n)), 4)

    # ---- robustness on the OOS LATE-cost base: drop the K largest LATE-cost
    # wallets, then recompute the OOS share over the remaining population (rank on
    # early, measure on late), with cut sizes re-derived on the shrunken set ----
    # The ordering is by per-wallet signed LATE cost, descending, so "largest" here
    # means largest ADVERSE-SELECTION COST and not largest notional. The key states
    # the criterion (see _whale_key) because the two answer different questions.
    late_order = np.argsort(-late_cost, kind="stable")  # largest LATE cost first
    drop_decile = {}
    drop_top50 = {}
    for k in DROP_TOP_K:
        kk = _whale_key(k)
        if k >= n_ranked:
            drop_decile[kk] = 0.0
            drop_top50[kk] = 0.0
            continue
        keep_idx = late_order[k:]
        e_rem = early_cost[keep_idx]
        l_rem = late_cost[keep_idx]
        m = keep_idx.size
        dk = max(1, int(np.floor(m * DOLLAR_COST_TOP_FRAC)))
        tk = min(TOP_N, m)
        drop_decile[kk] = round(
            _selected_share(l_rem, _top_by_dollar_cost_mask(e_rem, dk)), 4)
        drop_top50[kk] = round(
            _selected_share(l_rem, _top_by_dollar_cost_mask(e_rem, tk)), 4)
    out["whale_drop_ladder_top10pct"] = drop_decile
    out["whale_drop_ladder_top50"] = drop_top50

    # ---- single-wallet leave-one-out of the largest LATE-cost wallet ----
    big = int(late_order[0])
    largest_late = float(late_cost[big])
    keep1 = late_order[1:]
    e1 = early_cost[keep1]
    l1 = late_cost[keep1]
    m1 = keep1.size
    dk1 = max(1, int(np.floor(m1 * DOLLAR_COST_TOP_FRAC))) if m1 else 0
    tk1 = min(TOP_N, m1)
    out["leave_one_out_largest"] = {
        "wallet_id": int(ids[big]),
        "wallet_late_cost_usd": round(largest_late, 2),
        "wallet_late_cost_share_of_gross": round(_safe_div(largest_late, gross_late), 4),
        "top10pct_before": round(share_oos_decile, 4),
        "top10pct_after": round(_selected_share(l1, _top_by_dollar_cost_mask(e1, dk1)), 4) if m1 else 0.0,
        "top50_before": round(share_oos_topn, 4),
        "top50_after": round(_selected_share(l1, _top_by_dollar_cost_mask(e1, tk1)), 4) if m1 else 0.0,
    }

    # ---- bootstrap 95% CI on the OOS top-decile share, resampling wallets with
    # replacement (fixed seed). Each resample re-ranks on early and re-measures on
    # late, so the CI captures whale-driven instability of the OOS selection ----
    rng_b = np.random.default_rng(BOOTSTRAP_SEED)
    boot = np.empty(BOOTSTRAP_N, dtype=np.float64)
    for b in range(BOOTSTRAP_N):
        idx = rng_b.integers(0, n_ranked, size=n_ranked)
        e_b = early_cost[idx]
        l_b = late_cost[idx]
        dk = max(1, int(np.floor(e_b.size * DOLLAR_COST_TOP_FRAC)))
        boot[b] = _selected_share(l_b, _top_by_dollar_cost_mask(e_b, dk))
    lo, hi = np.percentile(boot, [2.5, 97.5])
    out["bootstrap_ci_oos_top10pct"] = {
        "lo": round(float(lo), 4),
        "hi": round(float(hi), 4),
        "n_resamples": BOOTSTRAP_N,
        "seed": BOOTSTRAP_SEED,
    }

    # ---- in-sample concentration (DIAGNOSTIC ONLY, relabelled, NOT avoidable):
    # rank and measure on the SAME all-days cost, the original construction ----
    all_sorted = np.sort(all_cost)[::-1]
    out["in_sample_concentration"] = {
        "note": "DIAGNOSTIC ONLY - rank and measure on the SAME all-days cost; "
                "bounded toward 100% by construction, NOT the avoidable number.",
        "share_top10pct": round(_gross_share(all_sorted, n_decile), 4),
        "share_top50": round(_gross_share(all_sorted, n_top_n), 4),
        "_gross_positive_all_cost_usd": round(float(np.sum(np.maximum(all_cost, 0.0))), 2),
    }

    out["whale_rule"] = WHALE_RULE
    return out


# Keys inside an avoidable block whose value does NOT move with the scoring window,
# and which therefore must not claim one: the standing rule is prose, identical in
# every block. Everything else in the block is a measurement at one window and gets
# that window's suffix when the block is written out.
_BLOCK_WINDOW_FREE_KEYS = ("whale_rule",)


def _name_block_for_window(block, h):
    """Rewrite one avoidable block's keys so each states the window it came from.

    Why the naming happens HERE and not where the block is built. _avoidable_block
    is horizon-generic: it is handed a pair of cost vectors and never learns which
    markout column produced them, so a window typed into a key inside it would be a
    name asserting something the code cannot know -- the exact defect settings.py
    rule 2 describes. The caller does know the window, so the caller names it, and
    it names it through settings.field_name rather than by string concatenation.
    """
    return {
        (k if k in _BLOCK_WINDOW_FREE_KEYS else H.field_name(k, h)): v
        for k, v in block.items()
    }


def _slice_result(taker_id, coin_mask, day, mo10, mo60, notional, n_days):
    """Full T3 result block for one slice (a coin, or pooled = all rows).

    n_days is the count of distinct resolved days in the npz, derived at runtime
    (NOT hardcoded), and is the divisor for the $/day figure.
    """
    mo60_s = np.asarray(mo60)[coin_mask]
    mo10_s = np.asarray(mo10)[coin_mask]
    nt_s = np.asarray(notional)[coin_mask]

    c60 = _cost_block(mo60_s, nt_s, n_days)
    c10 = _cost_block(mo10_s, nt_s, n_days)

    ids, early_cost, late_cost, all_cost, diag = _per_wallet_cost(
        taker_id, coin_mask, day, mo60, notional
    )
    avoid = _avoidable_block(ids, early_cost, late_cost, all_cost, diag)

    # Same rank-early / measure-late procedure run on the 10s markout. The
    # horizon study (ws1_horizon_persistence.py) selects 10s as the scoring
    # horizon, so this is the cell the report leads on; the 60s block above is
    # kept as the robustness companion and as the anchor for the committed
    # check values.
    ids10, early10, late10, all10, diag10 = _per_wallet_cost(
        taker_id, coin_mask, day, mo10, notional
    )
    avoid10 = _avoidable_block(ids10, early10, late10, all10, diag10)

    hh, hc = H.HEADLINE_HORIZON_S, H.COMPANION_HORIZON_S

    # Volume-weighted mean markout at the companion horizon, kept as the anchor for
    # the fee comparison below. Same value as cost_bps at that window; kept under its
    # own name because the fee paragraph cites it.
    out = {
        # HEADLINE window cost, three ways
        H.field_name("total_cost_usd", hh): round(c10["total_cost_usd"], 2),
        H.field_name("cost_per_day_usd", hh): round(c10["cost_per_day_usd"], 2),
        H.field_name("cost_bps", hh): round(c10["cost_bps"], 4),
        # COMPANION window cost, three ways
        H.field_name("total_cost_usd", hc): round(c60["total_cost_usd"], 2),
        H.field_name("cost_per_day_usd", hc): round(c60["cost_per_day_usd"], 2),
        H.field_name("cost_bps", hc): round(c60["cost_bps"], 4),
        # OUT-OF-SAMPLE avoidable share at the HEADLINE window, lifted out of the
        # block below so the number the report leads on sits at the top of the slice.
        H.field_name("avoidable_share_oos_top10pct", hh):
            avoid10["avoidable_share_oos_top10pct"],
        H.field_name("avoidable_share_oos_top50", hh):
            avoid10["avoidable_share_oos_top50"],
        # The same two at the COMPANION window.
        H.field_name("avoidable_share_oos_top10pct", hc):
            avoid["avoidable_share_oos_top10pct"],
        H.field_name("avoidable_share_oos_top50", hc):
            avoid["avoidable_share_oos_top50"],
        # honest comparison anchors
        H.field_name("raw_mean_markout_bps", hc): round(c60["cost_bps"], 4),
        "taker_fee_band_bps": list(PER_TAKER_FEE_BPS),
        "fee_note": FEE_NOTE,
    }

    # The two full avoidable blocks: the random floor, the oracle ceiling, the
    # whale-drop ladder, the leave-one-out and the bootstrap interval, one block per
    # window, every key inside it naming its window.
    out[H.field_name("avoidable", hh)] = _name_block_for_window(avoid10, hh)
    out[H.field_name("avoidable", hc)] = _name_block_for_window(avoid, hc)

    # Diagnostics. Wallet counts and the notional denominator are reported PER
    # WINDOW: eligibility and the finite-markout mask are both counted over rows the
    # given window can score, so the eligible population and the notional behind
    # cost_bps both move slightly with the window. Never pair a headline share with a
    # companion wallet count. The early and late day sets are the DERIVED split the
    # run actually used, printed so the split is checkable and not a promise.
    out["_diag"] = {
        H.field_name("n_rows", hh): c10["_n_rows"],
        H.field_name("n_rows", hc): c60["_n_rows"],
        H.field_name("total_notional_usd", hh): round(c10["_total_notional"], 2),
        H.field_name("total_notional_usd", hc): round(c60["_total_notional"], 2),
        H.field_name("n_ranked_wallets", hh): diag10["n_ranked_wallets"],
        H.field_name("n_ranked_wallets", hc): diag["n_ranked_wallets"],
        H.field_name("n_top_decile_wallets", hh): avoid10["n_top_decile_wallets"],
        H.field_name("n_top_decile_wallets", hc): avoid["n_top_decile_wallets"],
        H.field_name("n_top_n_wallets", hh): avoid10["n_top_n_wallets"],
        H.field_name("n_top_n_wallets", hc): avoid["n_top_n_wallets"],
        "early_days_used": diag10["early_days"],
        "late_days_used": diag10["late_days"],
    }
    return out


# -------------------- main --------------------
def main():
    t0 = artifact.start_clock()
    # panel_io raises when the file is absent and names the producer to run, so the
    # "is it there" test and the "what do I do about it" message live in one place
    # instead of once per script.
    # panel_io names the producer to run when the file is absent, so that message
    # is written once for the whole tree; the load itself stays here because
    # build.py derives this script's input edge from the argument of np.load.
    P.require_present("print", NPZ_PATH)
    data = np.load(NPZ_PATH)
    taker_id = data["taker_id"].astype(np.int64)
    coin = data["coin"].astype(np.int64)
    day = data["day"].astype(np.int64)
    mo10 = data[H.headline_print_col()].astype(np.float64)
    mo60 = data[H.companion_print_col()].astype(np.float64)
    notional = data["notional"].astype(np.float64)

    # Number of distinct resolved days, derived from the npz at runtime (NOT
    # hardcoded). This is the divisor for the $/day figure, so a future 10-day
    # re-run self-labels with the day count it actually resolved.
    n_days = int(np.unique(day).size)

    # The early and late halves for the whole run, derived from the days the npz
    # carries. Reported in _meta so the artifact states its own split; the per-slice
    # split is derived the same way inside _per_wallet_cost and reported per slice.
    early_run, late_run = _resolve_split(np.unique(day), EARLY_DAYS_OVERRIDE,
                                         LATE_DAYS_OVERRIDE)
    hh, hc = H.HEADLINE_HORIZON_S, H.COMPANION_HORIZON_S
    hl_share = H.field_name("avoidable_share_oos_top10pct", hh)
    cp_share = H.field_name("avoidable_share_oos_top10pct", hc)

    # Which setting each number was computed under, so a figure lifted out of this
    # file still knows what produced it. The overrides are the places this run
    # genuinely differs from the declaration; all four migrating settings are stated,
    # so nothing lands in declared_not_confirmed. It is built before the results dict
    # because artifact.write is the single place that stamps it.
    settings_used = dict(
        h=hh,
        lens="print",
        master_seed=RANDOM_SEED,
        n_perm=None,
        n_boot=BOOTSTRAP_N,
        rank_floor_fills=MIN_EARLY_TRADES,
        bootstrap_seed=BOOTSTRAP_SEED,
        random_floor_draws=RANDOM_DRAWS,
        whale_drop_criterion=WHALE_DROP_CRITERION,
        whale_drop_ladder=list(DROP_TOP_K),
        early_days=list(early_run),
        late_days=list(late_run),
        override_reasons={
            "n_boot": f"the run drew {BOOTSTRAP_N} resamples, which IS the "
                      f"declared {H.N_BOOT}: stated as a CONFIRMATION and not as "
                      f"a deviation. It was 1000 until 2026-07-31, half the "
                      f"declaration, so the two endpoints of the interval moved "
                      f"with the adoption and the share they bracket did not",
            "n_perm": "no permutation test runs in this file; the random floor "
                      "is a selection draw, not a label permutation, so the "
                      "declared permutation budget does not apply",
            "bootstrap_seed": f"the file draws TWO streams. The random floor is "
                              f"seeded {RANDOM_SEED}, which is the declared "
                              f"master seed. The bootstrap is seeded "
                              f"{BOOTSTRAP_SEED} and is reported here rather "
                              f"than folded in, because folding it in moves the "
                              f"published interval.",
        },
            )

    results = {
        "_meta": {
            "object": "T3 - economic magnitude of avoidable adverse-selection cost",
            "window_days": n_days,
            "horizon_note": (
                f"The {hh}s window is the HEADLINE (the horizon study "
                f"ws1_horizon_persistence.py selects it as the scoring window); the "
                f"{hc}s window is the robustness COMPANION. EVERY key whose value "
                f"depends on the window states that window: the headline carries the "
                f"_{hh}s suffix and the companion carries _{hc}s, and NO key is left "
                f"unsuffixed. Until 2026-07-30 the companion keys here were unsuffixed "
                f"while panel_analyze.py left the HEADLINE unsuffixed, so a key spelled "
                f"cost_bps meant {hh}s in one artifact and {hc}s in the other. The "
                f"convention is now declared once in settings.FIELD_SUFFIX_STYLE and "
                f"every key is built by settings.field_name. Old spelling -> new: "
                f"cost_bps -> cost_bps_{hc}s, total_cost_usd -> total_cost_usd_{hc}s, "
                f"cost_per_day_usd -> cost_per_day_usd_{hc}s, raw_mean_markout_bps -> "
                f"raw_mean_markout_bps_{hc}s, avoidable -> avoidable_{hc}s, "
                f"avoidable_share_oos_top10pct -> {cp_share}, "
                f"avoidable_share_oos_top50 -> "
                f"{H.field_name('avoidable_share_oos_top50', hc)}, and inside each "
                f"avoidable block every key gains its window. No VALUE moved."
            ),
            "markout_sign": "signed taker markout bps; positive = taker profited = maker adverse-selected; positive total cost = maker loss",
            "early_days": list(early_run),
            "late_days": list(late_run),
            "split_rule": (
                "The early and late halves are DERIVED from the days present, by "
                "settings.split_early_late: first ceil(n/2) days early, the rest late. "
                "They used to be the hardcoded day-of-month tuples (4,5,6,7,8) and "
                "(9,10,11,12,13), which are correct only for a window that opens on the "
                "4th and closes on the 13th. This input does open on the 4th, so the "
                "derived split reproduces those tuples exactly and no number moved; a "
                "twelve-day window would have been split three-against-seven, or had "
                "two of its days discarded outright."
            ),
            "avoidable_definition": (
                f"OUT-OF-SAMPLE share, computed at BOTH windows. Over wallets with "
                f">= {MIN_EARLY_TRADES} trades in the EARLY half (days "
                f"{early_run[0]}-{early_run[-1]}), rank wallets by their EARLY gross "
                f"cost, then MEASURE the share of LATE (days {late_run[0]}-"
                f"{late_run[-1]}) gross POSITIVE cost captured by the early-ranked top "
                f"decile / top-{TOP_N}. HEADLINE cell = rank on {hh}s, measure on {hh}s "
                f"(key {hl_share}). COMPANION cell = rank on {hc}s, measure on {hc}s "
                f"(key {cp_share}). Each cell uses ONE window for both the ranking and "
                f"the measurement, so NEITHER cell is a mixed-window hybrid. The ranking "
                f"half (early) and the measurement half (late) are DISJOINT, so the "
                f"share is honest and is NOT bounded toward 100% by construction. "
                f"Reported beside a random-selection floor (same cut sizes) and a "
                f"rank-on-late oracle ceiling."
            ),
            "avoidable_base": (
                f"gross positive per-wallet LATE (days {late_run[0]}-{late_run[-1]}) "
                f"cost, taken at the same window as the ranking: the {hh}s late cost for "
                f"the headline cell and the {hc}s late cost for the companion cell; "
                f"net/gross ratio reported per slice and per window"
            ),
            "in_sample_note": (
                f"avoidable_{hh}s.in_sample_concentration_{hh}s retains the OLD "
                f"rank-and-measure-on-the-same-all-days-cost number as a DIAGNOSTIC "
                f"only; it is bounded toward 100% by construction and is NOT the "
                f"avoidable share."
            ),
            "random_floor_and_oracle": (
                f"random-selection floor = {RANDOM_DRAWS} random wallet sets of the "
                f"same cut size (seed {RANDOM_SEED}, mean + p95); oracle ceiling = "
                f"rank-on-late selection (best achievable)"
            ),
            "robustness": (
                f"all on the OOS LATE-cost base: drop-top-"
                f"{'/'.join(str(k) for k in DROP_TOP_K)} wallets by "
                f"{WHALE_DROP_CRITERION} (the largest per-wallet signed cost in the "
                f"measurement half, NOT the largest by notional -- dropping by notional "
                f"answers 'is this a volume artifact', dropping by cost answers 'is this "
                f"ten wallets'), single-wallet leave-one-out of the largest such wallet, "
                f"and a {BOOTSTRAP_N}-resample bootstrap 95% CI (seed {BOOTSTRAP_SEED}). "
                f"The ladder keys name the count and the criterion together: "
                f"{', '.join(_whale_key(k) for k in DROP_TOP_K)}."
            ),
            "whale_rule": WHALE_RULE,
            "npz_path": os.path.basename(NPZ_PATH),
            "fee_note": FEE_NOTE,
        }
    }

    # per coin
    for code, name in COIN_CODES.items():
        mask = coin == code
        results[name] = _slice_result(
            taker_id, mask, day, mo10, mo60, notional, n_days
        )

    # pooled (all rows)
    pooled_mask = np.ones(coin.shape, dtype=bool)
    results["pooled"] = _slice_result(
        taker_id, pooled_mask, day, mo10, mo60, notional, n_days
    )

    # What the numbers cover. The avoidable share is an OUT-OF-SAMPLE statistic, so
    # the population names the floor a wallet must clear in the EARLY half to be
    # ranked, and the window names the two disjoint halves by their resolved days.
    scope = {
        "population": (f"{taker_id.size:,} rows of the trade-print panel aggregated "
                       f"to per-wallet gross cost; a wallet is ranked only if it has "
                       f"at least {MIN_EARLY_TRADES} trades in the early half, and "
                       "the late half it is measured on is disjoint from it"),
        "window": (f"{n_days} resolved days in the input, early {list(early_run)} "
                   f"against late {list(late_run)}, derived from the days present by "
                   "settings.split_early_late"),
        "coins": [COIN_CODES[c] for c in sorted(COIN_CODES)],
    }

    # The output name and directory still come from the module-level RESULTS_PATH, so
    # a caller that redirects that constant redirects the whole write, as before.
    artifact.write(os.path.basename(RESULTS_PATH), results,
                   script=__file__, inputs=[NPZ_PATH], scope=scope,
                   settings=settings_used, started=t0,
                   out_dir=os.path.dirname(RESULTS_PATH))

    # -------------------- printed summary --------------------
    lo, hi = PER_TAKER_FEE_BPS
    print("=" * 78)
    print("OBJECT T3 - AVOIDABLE ADVERSE-SELECTION COST (capacity / magnitude)")
    print("=" * 78)
    print(f"  Window: {n_days} resolved days. "
          f"HEADLINE horizon: {hh}s. COMPANION horizon: {hc}s.")
    print("  Sign: positive cost = maker's gross loss to taker adverse selection.")
    print("  Each horizon is ranked AND measured on itself; no cell mixes horizons.")
    print(f"  Avoidable shares are OUT-OF-SAMPLE: rank on early days "
          f"{early_run[0]}-{early_run[-1]}, measure on late days "
          f"{late_run[0]}-{late_run[-1]}")
    print("  gross positive cost (disjoint halves, derived from the days present).")
    print("-" * 78)
    header = (f"  {'slice':>7} | {'total $':>15} | {'$ / day':>13} | "
              f"{'cost bps':>9} | {'OOS 10%':>9} | {'OOS 50':>8}")

    # Headline first: the shorter window is the one the report leads on. Every key
    # read below is built for the window in hand, so no printed line can pair a
    # figure with the wrong window's label.
    horizons = (
        (f"HEADLINE - {hh}s horizon", hh),
        (f"COMPANION - {hc}s horizon", hc),
    )
    for title, h in horizons:
        print(f"  {title}:")
        print(header)
        for key in ("BTC", "ETH", "pooled"):
            r = results[key]
            print(f"  {key:>7} | {r[H.field_name('total_cost_usd', h)]:>15,.2f} | "
                  f"{r[H.field_name('cost_per_day_usd', h)]:>13,.2f} | "
                  f"{r[H.field_name('cost_bps', h)]:>9.4f} | "
                  f"{r[H.field_name('avoidable_share_oos_top10pct', h)] * 100:>8.2f}% | "
                  f"{r[H.field_name('avoidable_share_oos_top50', h)] * 100:>7.2f}%")
        print("-" * 78)

    # Eligibility is counted over rows the given horizon can score, so the ranked
    # population moves slightly with the horizon. Printed per horizon so no reader
    # pairs a headline share with a companion wallet count.
    print("  RANKED-WALLET COUNTS (eligibility is horizon-specific):")
    for key in ("BTC", "ETH", "pooled"):
        dg = results[key]["_diag"]
        print(f"    {key:>7}: {dg[H.field_name('n_ranked_wallets', hh)]:>5} wallets "
              f"at {hh}s (top decile "
              f"{dg[H.field_name('n_top_decile_wallets', hh)]:>4})  | "
              f"{dg[H.field_name('n_ranked_wallets', hc)]:>5} at {hc}s "
              f"(top decile {dg[H.field_name('n_top_decile_wallets', hc)]:>4})")
    print("-" * 78)

    print("  OOS SHARE vs RANDOM FLOOR vs ORACLE CEILING (top-decile):")
    for title, h in horizons:
        print(f"    {title}:")
        for key in ("BTC", "ETH", "pooled"):
            a = results[key][H.field_name("avoidable", h)]
            rf = a[H.field_name("random_floor_top10pct", h)]
            orc = a[H.field_name("oracle_ceiling_top10pct", h)]
            print(f"      {key:>7}: OOS "
                  f"{a[H.field_name('avoidable_share_oos_top10pct', h)] * 100:6.2f}%  | "
                  f"random floor {rf['mean'] * 100:5.2f}% "
                  f"(p95 {rf['p95'] * 100:5.2f}%)  | "
                  f"oracle {orc * 100:6.2f}%")
    print("-" * 78)

    # WHALE_RULE applies to every headline share, so the whale-dropped companions
    # are printed for both cells.
    print(f"  ROBUSTNESS (whale-dropped companions on the OOS late-cost base; "
          f"dropped by {WHALE_DROP_CRITERION}):")
    for title, h in horizons:
        print(f"    {title}:")
        for key in ("BTC", "ETH", "pooled"):
            a = results[key][H.field_name("avoidable", h)]
            loo = a[H.field_name("leave_one_out_largest", h)]
            ci = a[H.field_name("bootstrap_ci_oos_top10pct", h)]
            d = a[H.field_name("whale_drop_ladder_top10pct", h)]
            ins = a[H.field_name("in_sample_concentration", h)]
            print(f"      {key}:")
            print(f"        OOS top-10% share = "
                  f"{a[H.field_name('avoidable_share_oos_top10pct', h)] * 100:.2f}%  "
                  f"[boot 95% CI {ci['lo'] * 100:.2f}-{ci['hi'] * 100:.2f}%]  "
                  f"net/gross(late) = "
                  f"{a[H.field_name('net_over_gross_ratio_late', h)] * 100:.2f}%")
            print("        drop-top-"
                  + "/".join(str(k) for k in DROP_TOP_K)
                  + f" by {WHALE_DROP_CRITERION} -> "
                  + " / ".join(f"{d[_whale_key(k)] * 100:.2f}%" for k in DROP_TOP_K))
            print(f"        largest late wallet = "
                  f"{loo['wallet_late_cost_share_of_gross'] * 100:.2f}% "
                  f"of gross; leave-it-out: top-10% "
                  f"{loo['top10pct_before'] * 100:.2f}% -> "
                  f"{loo['top10pct_after'] * 100:.2f}%")
            print(f"        [diagnostic] in-sample concentration (NOT avoidable) = "
                  f"{ins['share_top10pct'] * 100:.2f}%")
    print("-" * 78)
    print("  HONEST FRAMING - this is a GROSS, UPPER-BOUND cost, NOT a net edge:")
    pooled = results["pooled"]
    print(f"    raw volume-weighted mean {hh}s markout = "
          f"{pooled[H.field_name('cost_bps', hh)]:+.4f} bps  (headline)")
    print(f"    raw volume-weighted mean {hc}s markout = "
          f"{pooled[H.field_name('raw_mean_markout_bps', hc)]:+.4f} bps  (companion)")
    print(f"    perp taker fee band                  = ~{lo}-{hi} bps "
          f"(plus funding) -> SWAMPS the markout")
    print("    => a recurring, partly-avoidable COST, not alpha a maker earns.")
    print("-" * 78)
    print(f"  results -> {RESULTS_PATH}")
    print("=" * 78)


if __name__ == "__main__":
    main()
