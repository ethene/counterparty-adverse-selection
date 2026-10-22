"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-22
References:
  Avellaneda, M. and S. Stoikov (2008). High-Frequency Trading in a Limit Order Book.
  Cartea, A., G. Duran-Martin and L. Sanchez-Betancourt (2023). Detecting Toxic Flow.
  Easley, D., M. Lopez de Prado and M. O'Hara (2012). Flow Toxicity and Liquidity.
  Albers, J., M. Cucuringu, S. Howison and A. Shestopaloff (2026). An Open Book
    (Hyperliquid L4), Zenodo 10.5281/zenodo.18184441.

follow_the_informed_oos.py

Adversarial robustness test for the cost-not-alpha framing.

QUESTION
  We frame counterparty toxicity defensively: a maker should DECLINE persistently
  toxic counterparties, not trade with them. The obvious objection is that toxic
  wallets are informed, so a maker who instead FOLLOWS their trade direction might
  harvest directional alpha. This script tests that objection out-of-sample and
  net of realistic costs and a detection-latency lag.

DESIGN (no-lookahead at two levels)
  1. Classify toxicity on an EARLY window (days < SPLIT_DAY): a wallet's toxicity
     is its mean taker markout at the headline horizon (mo10) over its early fills. Toxic = top decile among
     wallets with >= MIN_FILLS_EARLY early fills.
  2. Evaluate on a disjoint LATE window (days >= SPLIT_DAY). Day sets are disjoint,
     so no late outcome enters the classifier (wallet-level no-lookahead).
  3. The follow-signal copies the toxic wallet's signed direction. Because the
     stored markout mo[H] is taker-profit-signed (positive = the taker made money
     in its own direction), the forward price return captured by copying that
     direction IS mo[H]. Detection latency: a follower can only act LAG seconds
     after the trade is observable, so the captured return is mo[H] - mo[LAG]
     (markouts are cumulative-from-entry; this strips the pre-signal move). This is
     trade-level no-lookahead.
  4. Net P&L subtracts a round-trip taker fee + half-spread entry slippage.
  5. Placebos: random activity-matched wallets, and a direction-shuffle.

The expected (and paper-confirming) outcome is FAILURE of the acceptance bar:
the signal is cost-avoidance, not alpha.

Run:
  uv run --no-project --with-requirements ../requirements.txt python3 follow_the_informed_oos.py
"""

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
import stats

# ----------------------------------------------------------------------------
# Configuration (all knobs explicit; nothing hidden)
# ----------------------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
# Located by panel_io rather than joined here, so the one place that knows where the
# markout panels live is the one place that has to change if they move.
NPZ_PRIMARY = os.path.join(P.data_root(), "quickwin_markouts.npz")
NPZ_MID = os.path.join(P.data_root(), "quickwin_markouts_mid.npz")               # optional 300s/robustness
OUT_JSON = os.path.join(HERE, "follow_the_informed_oos_results.json")

SPLIT_DAY = 9            # early = day < 9 (Dec 4-8), late = day >= 9 (Dec 9-13). A day
                         # of the month, right only for a window beginning on the 4th;
                         # settings.split_early_late is the declared rule and a TARGET.
TOXIC_QUANTILE = 0.90    # top decile by early mean headline markout
MIN_FILLS_EARLY = 10     # wallet must be active early to be rank-able. The loosest rung
                         # of settings.RANK_FLOOR_SENSITIVITY, not the declared
                         # RANK_FLOOR_FILLS of 50; recorded as an override below.
MIN_FILLS_LATE = 5       # below this a late wallet is flagged low-power
CLASSIFY_HORIZON = H.headline_print_col()  # toxicity defined on the HEADLINE markout.
# The HORIZON_LAG ladder below is a DIFFERENT quantity and deliberately keeps its own
# windows: it is the copycat's HOLDING horizon (enter one lag after the trade becomes
# observable, exit at H), not a measure of who is more harmful. Leave it alone. What the
# fingerprint therefore has to say, and does, is that the window it records is the
# CLASSIFICATION window while the acceptance bar is decided at a HOLDING horizon of
# 60 s entered after a 10 s detection lag -- two different quantities that happen to be
# spelled with the same column names.

# Realistic costs (bps). Hyperliquid taker fee ~2.25 bps/leg; round trip = in+out.
TAKER_FEE_BPS = 4.5      # 2 x ~2.25 bps round-trip taker
HALF_SPREAD_BPS = 1.0    # entry slippage to the touch
TOTAL_COST_BPS = TAKER_FEE_BPS + HALF_SPREAD_BPS

# Forward horizons and the detection-latency lag applied to each.
# Captured gross return = mo[H] - mo[LAG]. LAG=None means act at entry (idealised,
# look-ahead-violating; reported only as an upper bound, never the headline).
# Real, actionable cells use a strictly positive lag.
# Column names come from settings so the LADDER is one list project-wide; what this file
# owns is the PAIRING of an exit column with an entry lag, which is the holding-horizon
# quantity and nothing settings.py decides.
_LADDER = [H.headline_print_col(h) for h in H.LADDER_S]   # short-to-long
HORIZON_LAG = {
    _LADDER[0]: None,          # shortest rung with no lag: an idealised ceiling, not
                               # actionable, reported as an upper bound only
    _LADDER[1]: _LADDER[0],    # act one rung after the trade becomes observable
    _LADDER[2]: _LADDER[1],    # act ten seconds after it is observable: the realistic cell
}
# A 300 s exit would need a column no producer writes, which is why 300 is deliberately
# absent from settings.LADDER_S; the loader below picks it up only if a future build adds
# it, and resolve_horizons then logs the skip rather than failing.
OPTIONAL_LONG_COL = "mo300"

# Random-wallet placebo draws, READ from settings.py and no longer typed here. The budget
# is not a matter of taste: settings.min_perm_draws computes it from the level, the family
# size and the floor margin, so changing any of those moves it.
#
# Why the old literal of 1000 had to go, and it is not that it failed. Its floor was
# 1/1001 = 0.000999 against a corrected rank-one threshold of 0.05/48 = 0.001042, so it
# cleared the bar by four percent. That is precisely the position settings.PERM_FLOOR_MARGIN
# exists to forbid: a budget that only just clears puts every floored p on the boundary,
# where the last digit of the correction decides the verdict rather than the evidence.
# The declared budget puts the floor at half the threshold instead of just under it.
NPERM = H.N_PERM
RNG_SEED = H.seed_for("follow_the_informed_oos")
                        # READ from settings.py and no longer typed. The value is the
                        # same 20260622 this file has always drawn from, so no number
                        # here moves; settings.MASTER_SEED is 20260620, so the
                        # fingerprint still records this as an override
N_ACTIVITY_BINS = 20    # quantile bins for activity-matched placebo

# Acceptance bar (see module docstring / paper).
BAR_MIN_NET_TSTAT = 3.0
BAR_MIN_HITRATE = 0.51
BAR_MAX_PLACEBO_P = 0.01
# (exit column, entry-lag column) that MUST clear for the objection to count: a 60 s
# HOLDING horizon entered after a 10 s detection lag. Both names are built, not typed.
BAR_REQUIRED_CELL = (H.companion_print_col(), H.headline_print_col())

COIN_NAMES = H.coin_labels("quickwin")   # the map belongs to the FILE, not the project


# ----------------------------------------------------------------------------
# Load
# ----------------------------------------------------------------------------
def load_quickwin(path):
    d = np.load(path, allow_pickle=True)
    cols = {
        "taker_id": d["taker_id"].astype(np.int64),
        "coin": d["coin"].astype(np.int64),
        "day": d["day"].astype(np.int64),
        "taker_side": d["taker_side"].astype(np.int64),
        "notional": d["notional"].astype(np.float64),
    }
    for h in _LADDER:
        # Through panel_io, so a rung the panel does not carry is refused by name
        # instead of surfacing as a bare KeyError from inside numpy.
        cols[h] = P.column(d, h, dtype="float64", kind="print")
    # optional 300s if a future build adds it
    if OPTIONAL_LONG_COL in d.files:
        cols[OPTIONAL_LONG_COL] = d[OPTIONAL_LONG_COL].astype(np.float64)
    return cols


def resolve_horizons(cols):
    """Keep only horizons whose column AND lag column exist; log skips."""
    usable = {}
    skipped = {}
    for h, lag in HORIZON_LAG.items():
        if h not in cols:
            skipped[h] = "horizon column %s not present in npz" % h
            continue
        if lag is not None and lag not in cols:
            skipped[h] = "lag column %s not present in npz" % lag
            continue
        usable[h] = lag
    return usable, skipped


# ----------------------------------------------------------------------------
# Core test
# ----------------------------------------------------------------------------
def taker_dir(taker_side):
    """+1 buy ('B', taker_side==1), -1 sell ('A', taker_side==0)."""
    return np.where(taker_side == 1, 1.0, -1.0)


def early_toxicity_ranks(cols, coin):
    """Per-wallet early mean markout (toxicity) on one coin. Returns dict
    wallet_id -> (early_mean_tox, early_fill_count) over wallets with
    >= MIN_FILLS_EARLY early fills."""
    sel = (cols["coin"] == coin) & (cols["day"] < SPLIT_DAY)
    tid = cols["taker_id"][sel]
    tox = cols[CLASSIFY_HORIZON][sel]
    good = ~np.isnan(tox)
    tid, tox = tid[good], tox[good]
    if tid.size == 0:
        return {}, {}
    order = np.argsort(tid, kind="mergesort")
    tid, tox = tid[order], tox[order]
    uniq, start = np.unique(tid, return_index=True)
    sums = np.add.reduceat(tox, start)
    counts = np.diff(np.append(start, tid.size))
    means = sums / counts
    keep = counts >= MIN_FILLS_EARLY
    tox_map = {int(w): float(m) for w, m, c in zip(uniq[keep], means[keep], counts[keep])}
    cnt_map = {int(w): int(c) for w, c in zip(uniq[keep], counts[keep])}
    return tox_map, cnt_map


def toxic_wallet_set(tox_map):
    if not tox_map:
        return set()
    vals = np.array(list(tox_map.values()))
    thr = np.quantile(vals, TOXIC_QUANTILE)
    return {w for w, v in tox_map.items() if v >= thr}


def build_late(cols, coin):
    """Pre-slice the late out-of-sample window for one coin ONCE so the placebo
    loops do not re-mask 2.48M rows on every draw. Returns aligned column arrays."""
    sel = (cols["coin"] == coin) & (cols["day"] >= SPLIT_DAY)
    late = {"tid": cols["taker_id"][sel], "notional": cols["notional"][sel]}
    for h in _LADDER + [OPTIONAL_LONG_COL]:
        if h in cols:
            late[h] = cols[h][sel]
    return late


def follow_returns(late, wallet_arr, horizon, lag):
    """Late-window follow-trades by wallets in wallet_arr on one coin.
    Vectorised membership (np.isin) so it is cheap inside the placebo loop.
    Returns gross per-trade bps array (post detection-latency) and notional."""
    tid = late["tid"]
    if wallet_arr.size == 0:
        return np.empty(0), np.empty(0)
    in_set = np.isin(tid, wallet_arr)
    if not in_set.any():
        return np.empty(0), np.empty(0)
    moH = late[horizon][in_set]
    moL = late[lag][in_set] if lag is not None else np.zeros(int(in_set.sum()))
    notl = late["notional"][in_set]
    # mo is already taker-profit-signed (the captured return in the trade's own
    # direction), so following the direction yields mo[H]-mo[L] directly.
    gross = moH - moL
    ok = ~np.isnan(gross)
    return gross[ok], notl[ok]


def summarise(gross, label):
    n = gross.size
    if n == 0:
        return {"label": label, "n": 0}
    net = gross - TOTAL_COST_BPS
    sd = net.std(ddof=1) if n > 1 else float("nan")
    tstat = (net.mean() / (sd / np.sqrt(n))) if (n > 1 and sd > 0) else float("nan")
    return {
        "label": label,
        "n": int(n),
        "gross_mean_bps": float(gross.mean()),
        "gross_median_bps": float(np.median(gross)),
        "net_mean_bps": float(net.mean()),
        "net_median_bps": float(np.median(net)),
        "net_hit_rate": float((net > 0).mean()),
        "net_tstat": float(tstat),
        # Renamed 2026-07-31 from "cost_bps", which was the same key name two other
        # producers use for a different quantity. Here it is the round-trip trading
        # cost this backtest ASSUMES -- a constant, 5.5 in every cell, taker fee plus
        # half a spread -- while t3_capacity.py and panel_analyze.py write cost_bps
        # as an adverse-selection cost MEASURED per notional, which varies cell by
        # cell. An assumption and a measurement under one name is worse than a
        # missing window suffix: a reader who joins on the name combines the two
        # without anything going wrong visibly. The value is unchanged, so the
        # artifact needs recomputing but no number in it moves.
        "assumed_round_trip_cost_bps": TOTAL_COST_BPS,
    }


def activity_matched_placebo(cols, coin, tox_set, tox_cnt_map, all_tox_map,
                             all_cnt_map, horizon, lag, rng):
    """NPERM random wallet sets, same size, activity (early-fill) distribution
    quantile-matched to the toxic set. Returns empirical p-value that a random
    set's mean net >= the toxic set's mean net, plus the null distribution.

    Returns (p, null_draws, toxic_net, procedure), the last being the counting block
    stats.permutation_p records: the side, both draw counts, the slack and the rule
    that produced it, so the artifact carries the procedure and not only its result."""
    late = build_late(cols, coin)
    # toxic-set realised mean net
    tox_arr0 = np.fromiter(tox_set, dtype=np.int64, count=len(tox_set))
    g_tox, _ = follow_returns(late, tox_arr0, horizon, lag)
    tox_net = (g_tox - TOTAL_COST_BPS).mean() if g_tox.size else float("nan")

    pool = np.array(sorted(all_tox_map.keys()))
    if pool.size == 0 or len(tox_set) == 0:
        return float("nan"), [], tox_net, None
    pool_cnt = np.array([all_cnt_map[int(w)] for w in pool], dtype=float)
    # activity bins
    edges = np.quantile(pool_cnt, np.linspace(0, 1, N_ACTIVITY_BINS + 1))
    edges[-1] = np.inf
    pool_bin = np.clip(np.digitize(pool_cnt, edges[1:-1]), 0, N_ACTIVITY_BINS - 1)
    # how many toxic wallets fall in each activity bin
    tox_arr = np.array(sorted(tox_set))
    tox_cnt = np.array([all_cnt_map[int(w)] for w in tox_arr], dtype=float)
    tox_bin = np.clip(np.digitize(tox_cnt, edges[1:-1]), 0, N_ACTIVITY_BINS - 1)
    need = np.bincount(tox_bin, minlength=N_ACTIVITY_BINS)
    bin_members = [pool[(pool_bin == b) & ~np.isin(pool, tox_arr)]
                   for b in range(N_ACTIVITY_BINS)]

    null = []
    for _ in range(NPERM):
        picks = []
        for b in range(N_ACTIVITY_BINS):
            k = int(need[b])
            members = bin_members[b]
            if k == 0 or members.size == 0:
                continue
            repl = members.size < k
            picks.append(rng.choice(members, size=k, replace=repl))
        if not picks:
            null.append(float("nan"))
            continue
        rset_arr = np.concatenate(picks).astype(np.int64)
        g_r, _ = follow_returns(late, rset_arr, horizon, lag)
        null.append((g_r - TOTAL_COST_BPS).mean() if g_r.size else float("nan"))
    null = np.array(null, dtype=float)
    # THE COUNTING IS stats.permutation_p AND THE ARITHMETIC IS UNCHANGED. This site is
    # already one of the six in the tree that divide by the draws that came BACK rather
    # than by the budget asked for, which is what the module does, so the denominator
    # needs no argument: a draw is recorded as NaN whenever an activity bin has no
    # member left to draw from, and counting those in the denominator would claim a
    # resolution the run did not have. The comparison is ONE-SIDED -- the question is
    # whether a size-and-activity-matched random set earns at least what the toxic set
    # earns -- and carries an ABSOLUTE slack of zero, which is what this line applied.
    # The module's finite filter and this line's ~isnan agree here because every draw
    # is either NaN or the mean of a finite return vector.
    procedure = stats.permutation_p(tox_net, null, side="greater", abs_tol=0.0,
                                    n_requested=NPERM,
                                    cell=("follow_the_informed", "activity_matched",
                                          coin, horizon, str(lag)))
    if procedure["p"] is None:
        # No usable draw, or a toxic set with no follow-trade to score: this file
        # reported NaN there and still does. It is not a large p; it is no test.
        return float("nan"), null.tolist(), tox_net, procedure
    return float(procedure["p"]), null.tolist(), float(tox_net), procedure


def direction_shuffle_placebo(cols, coin, tox_set, horizon, lag, rng):
    """Flip each follow-trade's sign at random; a real directional edge must beat
    its own shuffled-sign version. Returns toxic net mean and shuffled net mean."""
    late = build_late(cols, coin)
    tox_arr0 = np.fromiter(tox_set, dtype=np.int64, count=len(tox_set))
    g, _ = follow_returns(late, tox_arr0, horizon, lag)
    if g.size == 0:
        return float("nan"), float("nan")
    signs = rng.choice(np.array([-1.0, 1.0]), size=g.size)
    g_shuf = g * signs
    return float((g - TOTAL_COST_BPS).mean()), float((g_shuf - TOTAL_COST_BPS).mean())


# ----------------------------------------------------------------------------
# Driver
# ----------------------------------------------------------------------------
def main():
    t0 = artifact.start_clock()
    rng = np.random.default_rng(RNG_SEED)
    # Refuse at the top, in panel_io's wording, instead of letting a missing panel surface
    # as a bare numpy error eighty seconds into the run. This file had no existence check
    # at all; the message names the producer that writes the panel, which a fresh clone
    # does not carry.
    P.require_present("print", NPZ_PRIMARY)
    cols = load_quickwin(NPZ_PRIMARY)
    usable, skipped = resolve_horizons(cols)

    # What every number in this file was computed under. The window recorded is the
    # CLASSIFICATION window; the acceptance bar is decided at a holding horizon, which
    # is a different quantity and is named beside it. It is built before the results
    # dict because artifact.write is the single place that stamps it.
    settings_used = dict(
        h=H.HEADLINE_HORIZON_S, lens="print",
        master_seed=RNG_SEED,
        n_perm=NPERM,
        n_boot=None,
        rank_floor_fills=MIN_FILLS_EARLY,
        persistence_floor_fills=None,
        whale_drop_k=None,
        fdr_alpha=None,
        early_late_split=f"day < {SPLIT_DAY} vs day >= {SPLIT_DAY}",
        classification_horizon_s=H.HEADLINE_HORIZON_S,
        holding_horizon_s=H.COMPANION_HORIZON_S,
        detection_lag_s=H.HEADLINE_HORIZON_S,
        p_floor=H.p_floor(NPERM),
        overrides_note=(
            "horizon_s is the window the TOXICITY CLASSIFICATION uses. The "
            "acceptance bar is a different quantity: a HOLDING horizon of "
            f"{H.COMPANION_HORIZON_S}s entered after a {H.HEADLINE_HORIZON_S}s "
            "detection lag, which is how long a copycat must wait before the "
            "trade is observable. That is not adverse-selection harm and is not "
            "comparable with a scoring window, so it is declared separately "
            "rather than folded into horizon_s. master_seed 20260622 not "
            "settings.MASTER_SEED 20260620; n_perm is the declared budget, read "
            "from settings.py and no longer typed here; no "
            "bootstrap is drawn; rank_floor_fills 10, the loosest rung of "
            "settings.RANK_FLOOR_SENSITIVITY, not the declared 50; no whale-drop "
            "arm and no FDR family run here; the split is a DAY-OF-MONTH cut "
            "rather than settings.split_early_late, which is a TARGET"),
            )

    results = {
        "config": {
            "split_day": SPLIT_DAY, "toxic_quantile": TOXIC_QUANTILE,
            "min_fills_early": MIN_FILLS_EARLY, "min_fills_late": MIN_FILLS_LATE,
            "classify_horizon": CLASSIFY_HORIZON,
            "classify_horizon_s": H.HEADLINE_HORIZON_S,
            "taker_fee_bps": TAKER_FEE_BPS, "half_spread_bps": HALF_SPREAD_BPS,
            "total_cost_bps": TOTAL_COST_BPS, "horizon_lag": HORIZON_LAG,
            "horizon_lag_meaning": (
                "exit column -> entry-lag column. These are HOLDING horizons, not "
                "adverse-selection scoring windows: the captured return is "
                "mo[exit] - mo[lag], the move a copycat could still take after waiting "
                "for the trade to become observable. The same column names appear here "
                "and in the toxicity score, and they mean two different quantities."),
            "nperm": NPERM, "rng_seed": RNG_SEED,
            "p_floor": H.p_floor(NPERM),
            "p_floor_note": (
                f"{NPERM} random-wallet draws cannot express a p below "
                f"{H.p_floor(NPERM):.6f}; each cell carries "
                "placebo_random_wallet_p_is_floor saying whether its p is a measurement "
                "or that floor"),
            "acceptance_bar": {
                "min_net_tstat": BAR_MIN_NET_TSTAT, "min_hit_rate": BAR_MIN_HITRATE,
                "max_placebo_p": BAR_MAX_PLACEBO_P,
                "required_cell": list(BAR_REQUIRED_CELL),
            },
        },
        "skipped_horizons": skipped,
        "cells": {},
        "verdict": {},
    }

    bar_cleared_any = False
    for coin in (0, 1):
        cname = COIN_NAMES[coin]
        tox_map, cnt_map = early_toxicity_ranks(cols, coin)
        tox_set = toxic_wallet_set(tox_map)
        late = build_late(cols, coin)
        tox_arr = np.fromiter(tox_set, dtype=np.int64, count=len(tox_set))
        for horizon, lag in usable.items():
            g_tox, _ = follow_returns(late, tox_arr, horizon, lag)
            n_late_wallets = len({w for w in tox_set})  # eligibility, not power
            cell = summarise(g_tox, "%s_%s_lag_%s" % (cname, horizon, lag))
            cell["n_toxic_wallets_early"] = len(tox_set)
            cell["lag"] = lag
            cell["actionable"] = lag is not None
            cell["low_power"] = bool(g_tox.size < MIN_FILLS_LATE * 50)

            p_act, null_dist, tox_net, act_procedure = activity_matched_placebo(
                cols, coin, tox_set, cnt_map, tox_map, cnt_map, horizon, lag, rng)
            cell["placebo_random_wallet_p"] = p_act
            # The counting block, so the cell records the side, the requested and the
            # usable draw count, the slack and the rule that set it, beside the p.
            cell["placebo_random_wallet_procedure"] = act_procedure
            # True means no activity-matched random wallet set reached the toxic set's
            # mean net return, so the p is the budget's smallest expressible value.
            # Measured against the REQUESTED budget, which is what this key has always
            # meant; the block above carries the floor of the draws that came back,
            # which is the honest one when a draw failed.
            cell["placebo_random_wallet_p_is_floor"] = (
                bool(H.p_is_floored(p_act, NPERM)) if p_act == p_act else False)
            cell["placebo_null_mean_net_bps"] = (
                float(np.nanmean(null_dist)) if null_dist else float("nan"))

            net_tox, net_shuf = direction_shuffle_placebo(
                cols, coin, tox_set, horizon, lag, rng)
            cell["placebo_shuffle_toxic_net_bps"] = net_tox
            cell["placebo_shuffle_random_net_bps"] = net_shuf
            cell["beats_shuffle"] = (
                bool(net_tox > net_shuf) if not np.isnan(net_tox) else False)

            # per-cell bar check
            clears = (
                cell.get("n", 0) > 0
                and cell.get("net_mean_bps", -1) > 0
                and cell.get("net_tstat", -1) > BAR_MIN_NET_TSTAT
                and cell.get("net_hit_rate", 0) > BAR_MIN_HITRATE
                and (not np.isnan(p_act) and p_act < BAR_MAX_PLACEBO_P)
                and cell.get("beats_shuffle", False)
                and cell.get("actionable", False)
            )
            cell["clears_bar"] = bool(clears)
            if clears and (horizon, lag) == BAR_REQUIRED_CELL:
                bar_cleared_any = True

            results["cells"]["%s|%s|lag=%s" % (cname, horizon, lag)] = cell

    # Verdict: the required actionable cell (60s, 10s lag) must clear on a coin.
    req_cells = {k: v for k, v in results["cells"].items()
                 if v.get("lag") == BAR_REQUIRED_CELL[1]
                 and BAR_REQUIRED_CELL[0] in k}
    results["verdict"] = {
        "alpha_worth_reporting": bool(bar_cleared_any),
        "required_cell": "%s lag=%s" % BAR_REQUIRED_CELL,
        "interpretation": (
            "ALPHA: the defensive framing left directional money on the table; "
            "reframe required." if bar_cleared_any else
            "NO ALPHA (expected): following toxic wallets does not pay net of the "
            "taker fee, half-spread, and detection-latency lag. The counterparty "
            "toxicity signal is a COST-AVOIDANCE (defensive) signal, not directional "
            "alpha. This CONFIRMS the cost-not-alpha framing."),
        "required_cells_detail": {
            k: {"net_mean_bps": v.get("net_mean_bps"),
                "net_tstat": v.get("net_tstat"),
                "net_hit_rate": v.get("net_hit_rate"),
                "placebo_random_wallet_p": v.get("placebo_random_wallet_p"),
                "placebo_random_wallet_p_is_floor": bool(
                    v.get("placebo_random_wallet_p_is_floor")),
                "beats_shuffle": v.get("beats_shuffle"),
                "clears_bar": v.get("clears_bar")}
            for k, v in req_cells.items()},
    }

    # What the numbers cover. The test ranks wallets on the early half and measures
    # copycat trades on the late half, so the population names both floors and the
    # window names the two disjoint halves by the days actually present.
    days = np.unique(cols["day"])
    early_days = [int(d) for d in days if d < SPLIT_DAY]
    late_days = [int(d) for d in days if d >= SPLIT_DAY]
    scope = {
        "population": (f"{cols['taker_id'].size:,} rows of the trade-print panel; a "
                       f"wallet is classified toxic on at least {MIN_FILLS_EARLY} "
                       f"early fills and followed on at least {MIN_FILLS_LATE} late "
                       "fills, and the follow-trades are the copycat population the "
                       "cells are measured over"),
        "window": (f"{days.size} days present in the input, early {early_days} "
                   f"against late {late_days}, cut at day {SPLIT_DAY}"),
        "coins": [COIN_NAMES[c] for c in sorted(COIN_NAMES)],
    }

    # The output name and directory still come from the module-level OUT_JSON, so a
    # caller that redirects that constant redirects the whole write, as before.
    artifact.write(os.path.basename(OUT_JSON), results,
                   script=__file__, inputs=[NPZ_PRIMARY], scope=scope,
                   settings=settings_used, started=t0,
                   out_dir=os.path.dirname(OUT_JSON))

    print("=== follow-the-informed OOS test ===")
    print("skipped horizons:", skipped)
    for k, v in results["cells"].items():
        if v.get("n", 0) == 0:
            print("%-22s n=0 (no follow-trades)" % k)
            continue
        print("%-22s n=%7d gross=%+.3f net=%+.3f t=%+.2f hit=%.3f "
              "p_rand=%s%s shuffle_beat=%s clears=%s" % (
                  k, v["n"], v["gross_mean_bps"], v["net_mean_bps"],
                  v["net_tstat"], v["net_hit_rate"],
                  ("%.5f" % v["placebo_random_wallet_p"]
                   if not np.isnan(v["placebo_random_wallet_p"]) else "nan"),
                  " FLOOR" if v.get("placebo_random_wallet_p_is_floor") else "      ",
                  v["beats_shuffle"], v["clears_bar"]))
    print("VERDICT:", results["verdict"]["interpretation"])
    print("cells are named exit|lag: the lag is a DETECTION delay and the exit a HOLDING")
    print("horizon, not the adverse-selection scoring window the toxicity score uses.")
    print("wrote", os.path.basename(OUT_JSON))


if __name__ == "__main__":
    main()
