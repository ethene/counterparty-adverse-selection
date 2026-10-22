"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-22
References:
  - Avellaneda, Stoikov (2008) High-frequency trading in a limit order book (the
    symmetric inventory-only baseline the skew is measured against).
  - Hyperliquid maker fee schedule (maker 1.5 -> 0 bps; rebate -0.1/-0.2/-0.3 bps),
    fetched 2026-06-21 from the official docs; same source as maker_econ.py.
  - Hyperliquid node-data S3 + Zenodo 18184441 (Albers et al. 2026) -> the on-disk
    markout npz this consumes (no S3 re-pull).
  - Cartea, Sanchez-Betancourt (2025) "A Simple Strategy to Deal with Toxic Flow"
    (the decline/widen-against-informed-flow policy this object operationalises).
"""

# ---------------------------------------------------------------------------
# OBJECT B2 - FILL-AWARE NET ECONOMICS OF THE COUNTERPARTY-TOXICITY SKEW.
#
# WHY THIS EXISTS. maker_econ.py computes the maker's net P&L on the real maker
# fee schedule but its policy block is B1, the IDEALIZED UPPER BOUND: decline the
# persistently-toxic decile ENTIRELY. Both maker_econ.py and t1_toxicity_skew_
# backtest.py explicitly name the deployable, fill-aware policy ("quote wider,
# lose some benign fills, recapture a share at a worse price, pay a requote
# penalty") as FUTURE WORK and never run it. This object runs it, so the
# tradeability claim is computed on a realistic policy, not an upper bound.
#
# THE B2 POLICY (fill-aware, three knobs).
#   On the LATE half, against wallets pre-identified as toxic on the EARLY half
#   (the exact i3 / maker_econ OOS split), the maker WIDENS instead of accepting
#   at the normal quote. Per toxic-wallet late fill, with notional n and pre-fee
#   maker bps measure m (m = net_PRINT or net_MID_lower at the headline horizon):
#     - a recapture fraction f in [0,1] of that flow STILL trades, now at a quote
#       widened by w bps (extra spread the taker pays / the maker earns), minus a
#       per-fill requote/operational penalty c bps;
#     - the remaining (1-f) is DECLINED entirely (no P&L, no notional).
#   Benign (non-toxic-wallet) flow is accepted unchanged, at the normal quote.
#
#   Per-fill maker dollar P&L (sign: positive = maker earns):
#     accept-as-is : ((m - fee)            / 1e4) * n
#     B2 on toxic  : f * ((m + w - fee - c)/ 1e4) * n          [recaptured share]
#                    + (1-f) * 0                                [declined share]
#   B1 is the special case f = 0 (decline entirely; w, c irrelevant). "Widen-only,
#   never decline" is f = 1. The deployable region is 0 < f < 1.
#
# WHAT THE KNOBS MODEL (assumptions stated, not hidden).
#   f (recapture) : fill probability at the widened quote. Lower f = wider / more
#                   declined. NOT estimated from a live book (we have no queue model);
#                   swept over a grid so the reader sees the whole surface.
#   w (widen bps) : extra half-spread charged to the toxic taker who still trades.
#                   The taker's adverse-selection m is UNCHANGED by widening (their
#                   information does not go away), so widening adds +w, it does not
#                   remove m. This is the conservative, honest modelling choice.
#   c (penalty)   : per-recaptured-fill operational/requote cost in bps.
#
# THE HONEST CLAIM (NON-NEGOTIABLE, mirrors maker_econ / t1).
#   COST, NOT ALPHA. The headline is whether B2 IMPROVES net vs the symmetric
#   baseline (a cost reduction) and whether B2 net ever turns POSITIVE (it does
#   not, on this flow, except in fragile rebate-tier corners that are flagged).
#   Two prior results bound this object: (1) B2 <= B1 by construction wherever the
#   declined toxic flow was pure cost; (2) a symmetric passive maker is net-negative
#   at every maker fee tier (maker_econ), so B2 starts from a negative base.
#   Declining flow also FORGOES the rebate/spread the maker would have earned on the
#   BENIGN part of toxic-wallet flow; that forgone income is reported beside every
#   improvement so the tradeoff is explicit. Nothing here is an alpha, a Sharpe, or
#   a standalone trading edge.
#
# SCOPE. Single December window, BTC+ETH, trade-print + book-mid references, on-disk
# (quickwin_markouts.npz + quickwin_markouts_mid.npz), NO S3 re-pull. Counterfactual
# on realized markout, not a live LOB/fill simulation. VALIDATION / ILLUSTRATION of
# the deployable policy's economics, not a powered live-performance claim.
#
# THE BENIGN/ADVERSE SPLIT OF DECLINED FLOW HAD ITS SIGN INVERTED until 2026-08-03.
# `benign_share_of_declined` was computed from the predicate m <= 0, which selects the
# fills the maker LOST on, so a field named for benign flow published the adverse share:
# 0.7031 on the book-mid measure where the benign share is 0.2969, and 0.6720 against
# 0.3280 on the trade-print measure. The reading of the whole accounting block inverts
# with it -- the screen turns away flow that was mostly costing the maker, not flow that
# was mostly harmless. Both halves are published now, each under its own name, and the
# block carries a note saying that any figure quoted from the old field is the
# complement of what its name said. See _b2_usd.
#
# Run command (bare python3 is BLOCKED on this machine). The pinned form is the one
# requirements.txt governs; the short `--with numpy` form does NOT honour the pins,
# measured 2026-08-03:
#   uv run --no-project --with-requirements requirements.txt python3 -u maker_econ_b2.py
# `-u` is not decoration: this run prints for over an hour, and a buffered stream holds
# every progress line until the end, which is when they stop being useful.
# ---------------------------------------------------------------------------

import os
import sys
import time

import numpy as np

# artifact.py, settings.py and the other shared modules sit in the
# repository root, one directory up from this group, so the path is built
# from this file's own location and never from the working directory the
# run happens to start in.
_CODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CODE_DIR not in sys.path:
    sys.path.insert(0, _CODE_DIR)

import artifact
import settings as H
import stats

# reuse the verified loaders + fee schedule from maker_econ (same directory).
from maker_econ import (
    FEE_TIERS,
    MAKER_FEE_BPS,
    build_toxicity_labels,
    early_late_days,
    load_aligned,
)

# The seed of every placebo stream in this file, read from the declaration, which holds
# the 20260622 the published run drew under. Reading it is not adopting
# settings.MASTER_SEED: that is a different declaration and this file still overrides
# it, which the fingerprint states in words.
SEED = H.seed_for("maker_econ_b2")
np.random.seed(SEED)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_JSON = os.path.join(HERE, "maker_econ_b2_results.json")

# The horizon this module reports on. It is passed straight through to
# build_toxicity_labels, so the labels and the measurement can never drift apart:
# change this one constant and the ranking follows the measurement. B2 is compared
# against the B1 upper bound that maker_econ reports at the SAME horizon, so the
# two must stay on one clock for that bound to mean anything.
HORIZON = H.HEADLINE_HORIZON_S
# Min early fills per taker, sweep and headline, from the declaration. They match
# maker_econ.py by construction rather than by two files happening to hold the same pair,
# which is what the B1 bound this surface is read against requires.
#
# THE HEADLINE ROSE FROM 10 TO THE DECLARED 50 ON 2026-07-31, and until this file was
# keyed by the floor that rise cost the repository a whole arm. maker_econ.py and
# mm_bakeoff.py each carry a K10 block and a K50 block side by side, so moving the
# headline there moves which block the prose cites and leaves both computed. Here every
# published block used to be built from labels_by_K[K_HEADLINE] alone, and nothing in the
# output was keyed by the floor at all: the second label set was built, printed to the log
# and thrown away. A run at fifty would therefore have OVERWRITTEN the ten-fill surface,
# the B1 bound check, the deploy point and both placebos rather than gaining a sibling.
#
# So the ladder is now computed and published rung by rung, in the form the two siblings
# already use: a dict keyed K<fills>, one entry per rung, each holding the same five
# blocks. The headline rung is additionally reproduced at the top of each measure, which
# is what maker_econ.py does with its placebo block for the same reason -- a reader
# already standing on the old path keeps finding a number there, and _meta says which
# rung that number is.
K_LIST = H.wallet_fill_floor("maker_econ_b2", "sweep")
K_HEADLINE = H.wallet_fill_floor("maker_econ_b2", "headline")
# The rungs actually computed: the declared sweep, plus the declared headline in case a
# later declaration puts the headline outside its own sweep. Derived rather than typed,
# so the two declarations cannot disagree about what the file publishes.
K_RUNGS = tuple(sorted(set(K_LIST) | {K_HEADLINE}))
MEASURES = ("net_MID_lower", "net_PRINT")   # conservative, optimistic
N_PERM = H.N_PERM                 # placebo permutations (p-floor 1/(N_PERM+1))
# Raised from 200 on 2026-07-29. At 200 three of the four placebo blocks returned
# exactly 1/201, the floor, which reports "no draw reached the observed" and says
# nothing about how small the value is. At 2000 the same three resolved to 0.0035,
# 0.0015 and 0.0085, none of them on the new floor. Every effect size in the file is
# bit-identical between the two settings: only the placebo blocks move. Cost is 2413
# seconds against 281.
#
# THOSE THREE FIGURES ARE HISTORY AND NOT WHAT THE ARTIFACT HOLDS, and the reason is that
# one commit moved two things. The budget went from 200 to 2000 in the same change that
# replaced a literal HORIZON = 60 with the declared one, so the resolutions above were
# measured at a sixty-second scoring horizon while every later run measures at ten. On the
# artifact of 2026-07-31 all FOUR placebo blocks sit on the floor 1/2001, which is not the
# budget failing but the effect at ten seconds standing further out in its own null than
# two thousand draws can place. The floor is a bound and is reported as one.

# B2 knob grid. f=0 is B1 (decline entirely); f=1 is widen-only (never decline).
F_RECAPTURE = (0.0, 0.25, 0.5, 0.75, 1.0)
W_WIDEN_BPS = (0.0, 1.0, 2.0, 5.0)
C_PENALTY_BPS = (0.0, 0.5)
# the single "deployable" point reported in the headline (a realistic middle).
DEPLOY_POINT = {"f": 0.5, "w": 2.0, "c": 0.5}
# How many cells the grid walk visits, derived from the three knob tuples rather than
# typed, so a knob added to any of them moves the progress denominator with it.
N_GRID_CELLS = len(F_RECAPTURE) * len(W_WIDEN_BPS) * len(C_PENALTY_BPS)


def _toxic_mask(taker, toxic_set):
    """Row mask for "this fill's counterparty is in the toxic set".

    THE MASK IS THE SAME OBJECT THE COMPREHENSION BUILT, and the reason it is worth
    saying is that this function is called 16,004 times in one run. The old form,
    np.array([int(t) in toxic_set for t in taker]), converted each of the 2.48 million
    rows to a Python int and asked a Python set about it, once per placebo draw.
    Integer membership carries no rounding and neither form reorders anything, so no
    number in this file can move; what moves is the wall clock. This is the identical
    repair maker_econ._net_means_on_subset took for the identical reason, and it is
    written here rather than imported because the two take their inputs differently.
    """
    taker = np.asarray(taker, dtype=np.int64)
    if not toxic_set:
        return np.zeros(taker.size, dtype=bool)
    codes = np.fromiter(toxic_set, dtype=np.int64, count=len(toxic_set))
    return np.isin(taker, codes)


def _usd(measure_bps, fee_bps, notional):
    """Per-fill maker dollar P&L = ((measure - fee)/1e4) * notional, finite rows."""
    pnl = ((measure_bps - fee_bps) / 1e4) * notional
    return pnl


def _accept_all_usd(m, fee, notl, sel):
    """Symmetric baseline dollar P&L over selected rows (accept everything)."""
    fin = sel & np.isfinite(m) & np.isfinite(notl)
    if not fin.any():
        return 0.0, 0.0
    pnl = _usd(m[fin], fee, notl[fin])
    return float(np.nansum(pnl)), float(np.nansum(notl[fin]))


def _b2_usd(m, fee, notl, sel, is_toxic, f, w, c):
    """B2 dollar P&L + accounting over selected rows.

    Benign (non-toxic) fills accepted as-is. Toxic fills: recapture fraction f at
    (m + w - fee - c); decline (1-f). Returns dict of dollar aggregates.
    """
    fin = sel & np.isfinite(m) & np.isfinite(notl)
    benign = fin & ~is_toxic
    toxic = fin & is_toxic

    pnl_benign = float(np.nansum(_usd(m[benign], fee, notl[benign]))) if benign.any() else 0.0
    notl_benign = float(np.nansum(notl[benign])) if benign.any() else 0.0

    # toxic, recaptured at widened quote
    if toxic.any():
        pnl_toxic_recap = float(np.nansum(
            f * (((m[toxic] + w - c) - fee) / 1e4) * notl[toxic]))
        notl_toxic_recap = float(np.nansum(f * notl[toxic]))
        notl_toxic_declined = float(np.nansum((1.0 - f) * notl[toxic]))
        # SPLIT THE DECLINED FLOW BY WHETHER THE MAKER WAS ACTUALLY HURT BY IT. `m` is
        # the maker's PRE-FEE NET result in bps -- net_PRINT = -a_print or
        # net_MID_lower = s_bbo - a_mid, both built in maker_econ.load_aligned, and
        # maker_econ's own sign convention says maker_net positive = the maker earns.
        # So m > 0 is a fill the maker made money on, which is the flow it is a pity to
        # turn away, and m <= 0 is a fill it lost money on, which is the flow the screen
        # exists to turn away.
        #
        # THE SIGN WAS THE WRONG WAY ROUND UNTIL 2026-08-03. The line read
        # `benign_in_toxic = toxic & (m <= 0.0)` under the comment "m <= 0 = not
        # adverse", so a field named for the benign flow held the ADVERSE flow, and the
        # published share read 0.7031 on the book-mid measure when the benign share is
        # 0.2969. The error inverts the reading of the whole block: it said the screen
        # turns away seventy per cent benign flow, when the screen turns away seventy
        # per cent flow the maker was losing on. Both halves are published now, and
        # under names that say which is which, so the old number keeps a home and cannot
        # be mistaken for the new one.
        adverse_in_toxic = toxic & (m <= 0.0)
        benign_in_toxic = toxic & (m > 0.0)
        notl_adverse_declined = (float(np.nansum((1.0 - f) * notl[adverse_in_toxic]))
                                 if adverse_in_toxic.any() else 0.0)
        notl_benign_declined = (float(np.nansum((1.0 - f) * notl[benign_in_toxic]))
                                if benign_in_toxic.any() else 0.0)
    else:
        pnl_toxic_recap = notl_toxic_recap = notl_toxic_declined = 0.0
        notl_benign_declined = notl_adverse_declined = 0.0

    b2_pnl = pnl_benign + pnl_toxic_recap
    accepted_notl = notl_benign + notl_toxic_recap
    return {
        "b2_pnl_usd": b2_pnl,
        "accepted_notional_usd": accepted_notl,
        "toxic_notional_declined_usd": notl_toxic_declined,
        "benign_notional_declined_usd": notl_benign_declined,
        "adverse_notional_declined_usd": notl_adverse_declined,
    }


def _net_bps_on_accepted(pnl_usd, accepted_notl):
    """Net P&L expressed in bps on the notional the maker actually traded."""
    if accepted_notl <= 0:
        return float("nan")
    return (pnl_usd / accepted_notl) * 1e4


def b2_surface(arrs, late_mask, labels, measure):
    """Full (f, w, c) x fee-tier B2 net surface vs the symmetric baseline.

    All dollar P&L on the LATE half. Reports, per (f,w,c,tier): B2 net $, B2 net
    bps on accepted notional, baseline net $, delta vs baseline, and whether B2 net
    is positive. coin = pooled (all late fills)."""
    taker = arrs["taker_id"]
    notl = arrs["notional"]
    m = arrs[f"{measure}_{HORIZON}"]
    toxic_set = labels["toxic_taker_set"]
    is_toxic = _toxic_mask(taker, toxic_set)

    t_surf = artifact.start_clock()
    surface = {}
    base_cache = {}
    for tier in FEE_TIERS:
        fee = MAKER_FEE_BPS[tier]
        base_pnl, base_notl = _accept_all_usd(m, fee, notl, late_mask)
        base_cache[tier] = {
            "baseline_net_usd": base_pnl,
            "baseline_net_bps": _net_bps_on_accepted(base_pnl, base_notl),
            "baseline_accepted_notional_usd": base_notl,
        }

    for f in F_RECAPTURE:
        for w in W_WIDEN_BPS:
            for c in C_PENALTY_BPS:
                key = f"f{f:g}_w{w:g}_c{c:g}"
                surface[key] = {"f": f, "w": w, "c": c, "by_fee_tier": {}}
                acc = _b2_usd(m, fee=0.0, notl=notl, sel=late_mask,
                              is_toxic=is_toxic, f=f, w=w, c=c)
                # acc computed at fee=0; subtract the tier fee on accepted notional.
                for tier in FEE_TIERS:
                    fee = MAKER_FEE_BPS[tier]
                    # B2 pnl at this tier = (fee=0 pnl) - fee/1e4 * accepted_notional
                    b2_pnl = acc["b2_pnl_usd"] - (fee / 1e4) * acc["accepted_notional_usd"]
                    b2_bps = _net_bps_on_accepted(b2_pnl, acc["accepted_notional_usd"])
                    base = base_cache[tier]
                    surface[key]["by_fee_tier"][tier] = {
                        "b2_net_usd": b2_pnl,
                        "b2_net_bps": b2_bps,
                        "baseline_net_usd": base["baseline_net_usd"],
                        "delta_vs_baseline_usd": b2_pnl - base["baseline_net_usd"],
                        "b2_net_positive": bool(b2_pnl > 0),
                        "delta_positive": bool(b2_pnl > base["baseline_net_usd"]),
                    }
                artifact.progress(f"maker_econ_b2 surface {measure}",
                                  len(surface), N_GRID_CELLS, t_surf)
                declined = acc["toxic_notional_declined_usd"]
                surface[key]["accounting"] = {
                    "accepted_notional_usd": acc["accepted_notional_usd"],
                    "toxic_notional_declined_usd": declined,
                    # The two halves of the declined flow, each under the name of what
                    # it is. They sum to the line above, which the field below asserts
                    # rather than promises.
                    "benign_notional_declined_usd": acc["benign_notional_declined_usd"],
                    "adverse_notional_declined_usd": acc["adverse_notional_declined_usd"],
                    "benign_share_of_declined": (
                        acc["benign_notional_declined_usd"] / declined
                        if declined > 0 else 0.0),
                    "adverse_share_of_declined": (
                        acc["adverse_notional_declined_usd"] / declined
                        if declined > 0 else 0.0),
                    "halves_sum_to_declined": bool(
                        abs(acc["benign_notional_declined_usd"]
                            + acc["adverse_notional_declined_usd"] - declined)
                        <= max(1.0, abs(declined) * 1e-9)),
                    "reading": (
                        "benign = the maker's pre-fee net on that fill was POSITIVE, so "
                        "the fill was income the screen gives up; adverse = it was zero "
                        "or negative, so the fill was the cost the screen exists to "
                        "avoid. Before 2026-08-03 benign_share_of_declined carried the "
                        "ADVERSE share under the benign name, because the predicate "
                        "tested m <= 0; any figure quoted from that field before that "
                        "date is the complement of what its name says."),
                }
    return {"baseline_by_tier": base_cache, "b2_surface": surface}


def b1_bound_check(surface_block, measure):
    """Confirm B2 <= B1 (f=0) wherever the declined toxic flow was pure cost.

    B1 = the f=0 corner (decline entirely). For every (w, c) the f=0 cell is the
    bound; B2 at f>0 with w=0 (no extra spread) must not beat it on delta. Reports
    the max delta over the surface and the best deployable cell."""
    surf = surface_block["b2_surface"]
    # B1 deltas (f=0) per tier
    b1 = {k: v for k, v in surf.items() if v["f"] == 0.0}
    best = {"delta_usd": float("-inf"), "key": None, "tier": None, "b2_net_usd": None}
    any_b2_positive = False
    for key, cell in surf.items():
        for tier, t in cell["by_fee_tier"].items():
            if t["b2_net_positive"]:
                any_b2_positive = True
            if t["delta_vs_baseline_usd"] > best["delta_usd"]:
                best = {"delta_usd": t["delta_vs_baseline_usd"], "key": key,
                        "tier": tier, "b2_net_usd": t["b2_net_usd"],
                        "b2_net_bps": t["b2_net_bps"]}
    # the largest delta should come from a low-f (decline-heavy) cell -> B1-like
    return {
        "measure": measure,
        "best_delta_cell": best,
        "best_delta_is_decline_heavy": bool(best["key"] is not None
                                            and surf[best["key"]]["f"] <= 0.25),
        "any_b2_net_positive": any_b2_positive,
        "n_b1_cells": len(b1),
    }


def deploy_point_report(surface_block, measure):
    """The single realistic deployable point (f=0.5, w=2, c=0.5), all tiers."""
    f, w, c = DEPLOY_POINT["f"], DEPLOY_POINT["w"], DEPLOY_POINT["c"]
    key = f"f{f:g}_w{w:g}_c{c:g}"
    cell = surface_block["b2_surface"].get(key)
    if cell is None:
        return {"measure": measure, "deploy_point": DEPLOY_POINT, "note": "cell absent"}
    out = {"measure": measure, "deploy_point": DEPLOY_POINT, "by_fee_tier": {}}
    for tier, t in cell["by_fee_tier"].items():
        out["by_fee_tier"][tier] = {
            "b2_net_bps": t["b2_net_bps"],
            "b2_net_usd": t["b2_net_usd"],
            "delta_vs_baseline_usd": t["delta_vs_baseline_usd"],
            "b2_net_positive": t["b2_net_positive"],
        }
    out["accounting"] = cell["accounting"]
    return out


def placebo_random(arrs, late_mask, labels, measure, tier="t4_0fee", rng=None,
                   cell=""):
    """At the deploy point, does the TOXICITY-targeted B2 delta beat a random
    same-count B2 delta? Permutation over N_PERM random toxic sets (p-floor).

    `cell` names which (rung, measure, tier) block is speaking in the progress line.
    Four of these run one after another per rung, and a fraction that did not say
    whose it was would report progress through something the reader cannot identify.
    It carries no meaning for any number here.
    """
    t_cell = artifact.start_clock()
    if rng is None:
        rng = np.random.default_rng(SEED)
    taker = arrs["taker_id"]
    notl = arrs["notional"]
    m = arrs[f"{measure}_{HORIZON}"]
    fee = MAKER_FEE_BPS[tier]
    f, w, c = DEPLOY_POINT["f"], DEPLOY_POINT["w"], DEPLOY_POINT["c"]

    base_pnl, _ = _accept_all_usd(m, fee, notl, late_mask)

    def delta_for(toxic_set):
        is_tox = _toxic_mask(taker, toxic_set)
        acc = _b2_usd(m, 0.0, notl, late_mask, is_tox, f, w, c)
        b2 = acc["b2_pnl_usd"] - (fee / 1e4) * acc["accepted_notional_usd"]
        return b2 - base_pnl

    obs = delta_for(labels["toxic_taker_set"])
    # THE DRAWS ARE THIS FILE'S, THE COUNTING IS stats.permutation_p, and the p that
    # comes back is the number the hand-written count always produced. Each of the three
    # ways the two could have differed is closed here rather than left to be discovered.
    #
    # The stream. permutation_p does not draw anything -- it counts a null the caller
    # already built -- so the toxic sets below still come from this file's own SEED
    # stream and not from a named cell. The cell is recorded for the artifact only.
    #
    # The slack. Passed as an ABSOLUTE 1e-9, the value this file has always applied,
    # rather than the module's default, which scales with the comparison. That is a
    # declared departure and the returned block records tolerance_rule as "absolute,
    # stated by the caller". It is also the one place in the tree where 1e-9 is the
    # right number and not a typo: the statistic is a dollar delta of about 1.65
    # million, where one unit in the last place is 2.3e-10, so 1e-9 is a little over
    # four of them and an absolute 1e-12 could not change a single comparison.
    #
    # The denominator. The module divides by the count of draws that came back finite,
    # and the hand-written count divided by the requested budget. The two are the same
    # count here BY CONSTRUCTION, not by luck: delta_for returns
    # float(np.nansum(...)) - float(np.nansum(...)) over rows already masked to finite
    # markout and finite notional, so every draw is a finite dollar figure and none can
    # come back as no number.

    # pool of eligible takers to draw a random same-count toxic set from
    eligible = labels["eligible_mask_taker"]
    uniq = labels["uniq"]
    elig_ids = [int(uniq[i]) for i in np.where(eligible)[0]]
    n_toxic = len(labels["toxic_taker_set"])
    perm_deltas = []
    if elig_ids and n_toxic > 0:
        for draw_i in range(N_PERM):
            draw = set(int(x) for x in rng.choice(elig_ids, size=min(n_toxic, len(elig_ids)), replace=False))
            perm_deltas.append(delta_for(draw))
            artifact.progress(f"maker_econ_b2 placebo {cell}", draw_i + 1, N_PERM,
                              t_cell)
    pa = np.array(perm_deltas, dtype=np.float64) if perm_deltas else np.array([np.nan])
    perm = (stats.permutation_p(obs, pa, side="greater", abs_tol=1e-9,
                                n_requested=N_PERM,
                                cell=("maker_econ_b2_random_toxic_set", measure, tier))
            if perm_deltas else None)
    return {
        "measure": measure,
        "tier": tier,
        "deploy_point": DEPLOY_POINT,
        "observed_delta_usd": float(obs),
        "random_mean_delta_usd": float(np.nanmean(pa)),
        "random_p95_delta_usd": float(np.nanpercentile(pa, 95)) if pa.size else float("nan"),
        "permutation_p": (perm["p"] if perm_deltas else None),
        "toxicity_beats_random": bool(perm_deltas and obs > float(np.nanmean(pa))),
        "n_perm": N_PERM,
        "p_floor": stats.p_floor(N_PERM),
        # The procedure beside the number: side, slack, the two draw counts and the
        # floor. A p with no draw count next to it cannot be read.
        "permutation_procedure": perm,
    }


def rung_blocks(arrs, late_mask, labels, measure, rng, K=None):
    """The five published blocks of ONE measure at ONE wallet-fill floor.

    Every rung gets the identical treatment, in the identical order, so two rungs
    differ only by the label set handed in. The order also fixes how many draws the
    stream `rng` has spent by the time the function returns, which is what lets the
    headline rung keep the draw plan it has always had.

    `K` is passed for the progress lines only and touches nothing computed.
    """
    tag = f"K{K}" if K is not None else "K?"
    t_rung = artifact.start_clock()
    print(f"[maker_econ_b2] {tag} {measure}: surface starting "
          f"({N_GRID_CELLS} grid cells)", flush=True)
    block = b2_surface(arrs, late_mask, labels, measure)
    print(f"[maker_econ_b2] {tag} {measure}: surface done in "
          f"{(time.time() - t_rung) / 60:.1f} min; two placebos of {N_PERM} draws next",
          flush=True)
    out = {
        "surface": block,
        "b1_bound_check": b1_bound_check(block, measure),
        "deploy_point": deploy_point_report(block, measure),
        "placebo_t4_0fee": placebo_random(arrs, late_mask, labels, measure,
                                          "t4_0fee", rng, cell=f"{tag} {measure} t4_0fee"),
        "placebo_rebate3": placebo_random(arrs, late_mask, labels, measure,
                                          "rebate3", rng, cell=f"{tag} {measure} rebate3"),
    }
    print(f"[maker_econ_b2] {tag} {measure}: rung done in "
          f"{(time.time() - t_rung) / 60:.1f} min", flush=True)
    return out


def build_by_measure(arrs, late_mask, labels_by_K, rng):
    """Every measure at every rung of the declared ladder.

    THE SHAPE, which is maker_econ.py's and mm_bakeoff.py's and not a third one. Each
    measure holds the five blocks of the HEADLINE rung at its top level, and a by_K dict
    whose keys are the K<fills> spelling both siblings use, one entry per computed rung,
    each holding the same five blocks. Reading a figure therefore takes a rung key, and
    _meta.k_headline says which key the prose points at. Nothing is keyed by a literal.

    THE DRAW PLAN, and why it is not one rule for every rung. The headline rung draws
    from the stream `rng` the caller opened, in the order this file has always drawn in,
    so adding a rung cannot move a headline placebo. Every other rung draws from a stream
    derived from the seed and its own floor, so adding, dropping or reordering rungs
    cannot move any of them either. Both halves of that answer the same question -- what
    a cell's null depends on -- and the answer is: its own floor and nothing else about
    the ladder it happens to sit in.
    """
    headline_key = f"K{K_HEADLINE}"
    by_rung = {}
    # Headline first and on the shared stream: its four placebo blocks must consume
    # exactly the draws they consumed when this file published one rung.
    by_rung[headline_key] = {
        measure: rung_blocks(arrs, late_mask, labels_by_K[K_HEADLINE], measure, rng,
                             K=K_HEADLINE)
        for measure in MEASURES
    }
    for K in K_RUNGS:
        if K == K_HEADLINE:
            continue
        rung_rng = np.random.default_rng([SEED, K])
        by_rung[f"K{K}"] = {
            measure: rung_blocks(arrs, late_mask, labels_by_K[K], measure, rung_rng,
                                 K=K)
            for measure in MEASURES
        }

    by_measure = {}
    for measure in MEASURES:
        blocks = dict(by_rung[headline_key][measure])
        blocks["by_K"] = {f"K{K}": by_rung[f"K{K}"][measure] for K in K_RUNGS}
        by_measure[measure] = blocks
    return by_measure


def main():
    t0 = artifact.start_clock()
    print(f"[maker_econ_b2] seed={SEED}")
    arrs, align_ok, slice_meta = load_aligned()
    n_rows = int(arrs["taker_id"].size)
    print(f"[maker_econ_b2] loaded {n_rows:,} aligned fills; align={align_ok}")

    # Rank on the horizon this module measures on. Passing HORIZON explicitly is
    # what keeps the label set and the P&L on one clock.
    labels_by_K = {K: build_toxicity_labels(arrs, K, horizon=HORIZON) for K in K_RUNGS}
    # late_mask is decided by the DAY a fill sits on, so it is the same array at every
    # rung; reading it from the headline rung names a source rather than picking one.
    late_mask = labels_by_K[K_HEADLINE]["late_mask"]
    for K in K_RUNGS:
        lb = labels_by_K[K]
        print(f"[maker_econ_b2] K={K} h={HORIZON}s: eligible={lb['n_eligible']:,} "
              f"toxic={lb['n_toxic_takers']:,} disjoint(days={lb['days_disjoint']},"
              f"fills={lb['fills_disjoint']})")

    rng = np.random.default_rng(SEED)

    # The split the run actually used, derived from the days the input carries.
    early_run, late_run = early_late_days(arrs["day"])

    # Which settings produced these numbers, so a figure lifted out of this file still
    # knows what it was computed under. All four migrating settings are stated, so
    # nothing lands in declared_not_confirmed. The EARLY/LATE halves come from
    # maker_econ.early_late_days, a function of the days the input carries, because this
    # module takes its labels from build_toxicity_labels and must report the split that
    # function actually used. Handed to artifact.write as keyword arguments rather than
    # built here, so the block is stamped by the one function that writes artifacts.
    settings_used = {
        "h": HORIZON,
        "lens": "mid",
        "master_seed": SEED,
        "n_perm": N_PERM,
        "n_boot": None,
        "rank_floor_fills": K_HEADLINE,
        "rank_floor_sensitivity": list(K_LIST),
        "early_days": list(early_run),
        "late_days": list(late_run),
        "override_reasons": {
            "master_seed": f"the placebo streams here are seeded {SEED}, not the "
                           f"declared {H.MASTER_SEED}; adopting it re-draws them "
                           f"and moves the published placebo p-values",
            "n_boot": "no bootstrap runs in this file; the nulls here are "
                      "label permutations, so the declared bootstrap budget "
                      "does not apply",
            "rank_floor_fills": f"the headline cell gates takers at {K_HEADLINE} "
                                f"early fills, which IS the declared "
                                f"{H.RANK_FLOOR_FILLS}: a CONFIRMATION and not a "
                                f"deviation. It was 10 until 2026-07-31. Every "
                                f"rung of {list(K_RUNGS)} is COMPUTED AND "
                                f"PUBLISHED, under by_measure.<measure>.by_K."
                                f"K<fills>, so this file reports the curve and "
                                f"not one point, and raising the headline moves "
                                f"which rung the prose cites instead of erasing "
                                f"the other. The top level of each measure "
                                f"repeats the K{K_HEADLINE} rung. The ladder "
                                f"matches maker_econ.py so the B1 upper bound "
                                f"this surface is read against is the block at "
                                f"the same floor and the same window",
        },
    }
    headline_labels = labels_by_K[K_HEADLINE]
    scope = {
        "population": (f"{n_rows:,} aligned fills; the surface is evaluated on the "
                       f"{int(late_mask.sum()):,} LATE-half fills, against the toxic "
                       f"decile of the {headline_labels['n_eligible']:,} takers with at "
                       f"least {K_HEADLINE} early fills, which is "
                       f"{headline_labels['n_toxic_takers']:,} wallets. That is the "
                       f"HEADLINE rung; the file publishes the whole ladder and the "
                       f"population differs at every rung, which wallet_fill_floors "
                       f"states rung by rung"),
        "wallet_fill_floors": {
            "headline": f"K{K_HEADLINE}",
            "ladder_computed": [f"K{K}" for K in K_RUNGS],
            "by_rung": {
                f"K{K}": {
                    "min_early_fills": int(K),
                    "n_eligible_takers": int(labels_by_K[K]["n_eligible"]),
                    "n_toxic_takers": int(labels_by_K[K]["n_toxic_takers"]),
                }
                for K in K_RUNGS
            },
            "note": ("every rung listed here carries its own surface, B1 bound check, "
                     "deploy point and two placebos under by_measure.<measure>.by_K; "
                     "the blocks at the top of each measure are the headline rung "
                     "repeated, so a figure read there is a figure at "
                     f"K{K_HEADLINE}. The LATE mask is decided by the day a fill sits "
                     "on and is therefore identical at every rung; what moves with the "
                     "rung is which wallets are measurable and which of them carry the "
                     "toxic cut"),
        },
        "window": (f"single December window; early days {list(early_run)}, late days "
                   f"{list(late_run)}"),
        "coins": sorted(H.coin_labels("quickwin").values()),
        "note": ("on-disk, no S3 re-pull; a counterfactual on realized markout, not a "
                 "live fill model"),
    }

    results = {
        "_meta": {
            "object": "B2 fill-aware net economics of the counterparty-toxicity skew",
            "author": "Dmitry Stakhin",
            "date": "2026-06-22",
            "track": "11 (Cryptocurrency Markets - Microstructure)",
            "seed": SEED,
            "early_days": list(early_run),
            "late_days": list(late_run),
            "split_rule": (
                "The label and evaluation halves are DERIVED from the days present, by "
                "settings.split_early_late through maker_econ.early_late_days: first "
                "ceil(n/2) days early, the rest late. maker_econ.py used to declare them "
                "as the day-of-month tuples (4,5,6,7,8) and (9,10,11,12,13), correct only "
                "for a window opening on the 4th and closing on the 13th. This input does "
                "open on the 4th, so the derived split reproduces those tuples exactly "
                "and no number moved."
            ),
            "framing": "COST REDUCTION, NEVER NET ALPHA; B2 <= B1 upper bound; "
                       "symmetric maker net-negative at every tier (maker_econ).",
            "policy": "benign accepted as-is; toxic recaptured fraction f at +w bps "
                      "minus penalty c, declined (1-f). f=0 is B1 decline-entirely.",
            "declined_flow_split": (
                "SIGN REPAIRED 2026-08-03. Every accounting block splits the declined "
                "toxic-wallet notional into the part the maker was EARNING on "
                "(benign_notional_declined_usd, pre-fee net m > 0) and the part it was "
                "LOSING on (adverse_notional_declined_usd, m <= 0). Until this date the "
                "field benign_notional_declined_usd was built from the predicate "
                "m <= 0 and therefore held the adverse half under the benign name, so "
                "benign_share_of_declined published 0.7031 on net_MID_lower and 0.6720 "
                "on net_PRINT where the benign shares are 0.2969 and 0.3280. The "
                "consequence is a reversed reading and not a shifted number: the screen "
                "declines flow that was predominantly costing the maker, where the old "
                "field said it was predominantly harmless. Any figure taken from "
                "benign_share_of_declined in an artifact written before 2026-08-03 is "
                "the complement of what its name says."
            ),
            "knobs": {"f_recapture": list(F_RECAPTURE), "w_widen_bps": list(W_WIDEN_BPS),
                      "c_penalty_bps": list(C_PENALTY_BPS), "deploy_point": DEPLOY_POINT},
            "horizon_s": HORIZON,
            "label_horizon_policy": (
                "LABELS AND MEASUREMENT SHARE ONE HORIZON. Takers were RANKED on "
                "the early-window mean a_mid at horizon_s seconds AND the late-window "
                "P&L was MEASURED at horizon_s seconds. Nothing here mixes a ranking "
                "horizon with a different measurement horizon, and eligibility (at "
                "least K early fills with a finite a_mid) is counted at that same "
                "horizon. The B1 upper bound this surface is read against is the "
                "maker_econ block at the MATCHING horizon key, so compare "
                "b2 horizon_s against maker_econ b1_idealized_policy_upper_bound "
                "h<horizon_s> and never against a different one."
            ),
            "k_headline": K_HEADLINE,
            "k_list": list(K_LIST),
            "k_rungs_computed": list(K_RUNGS),
            "floor_key_policy": (
                "EVERY RUNG OF THE LADDER IS PUBLISHED, keyed K<fills> under "
                "by_measure.<measure>.by_K, which is the spelling maker_econ.py and "
                "mm_bakeoff.py already use for the same floor. The five blocks at the "
                "top of by_measure.<measure> are the k_headline rung repeated, so a "
                "reader on the old path still lands on a number and _meta says which "
                "rung it is. Before 2026-07-31 this file wrote the headline rung and "
                "nothing else, so raising the headline would have deleted the ten-fill "
                "arm instead of adding a fifty-fill one. Placebo streams: the headline "
                "rung draws from this file's seed stream in its historical order, every "
                "other rung from default_rng([SEED, K]), so no rung's null depends on "
                "what else the ladder holds."
            ),
            "measures": list(MEASURES),
            "fee_tiers": list(FEE_TIERS),
            "maker_fee_bps": MAKER_FEE_BPS,
            "n_rows": n_rows,
            "row_alignment_ok": align_ok,
        },
    }

    # Every rung of the ladder, with the headline rung repeated at the top of each
    # measure. One call, so the two rungs cannot be assembled by two different routes.
    results["by_measure"] = build_by_measure(arrs, late_mask, labels_by_K, rng)

    # artifact.write records the producer with its own hash, the two intermediates it
    # read with theirs, the scope, the settings block and the runtime, in the one shape
    # every results file in this tree carries. The inputs are named relatively and
    # resolved against this script's directory, so nothing local reaches the file.
    artifact.write(
        os.path.basename(OUT_JSON), results, script=__file__,
        inputs=["quickwin_markouts.npz", "quickwin_markouts_mid.npz"],
        scope=scope, started=t0, settings=settings_used,
        out_dir=os.path.dirname(OUT_JSON))

    _print_console(results)
    print(f"\n[maker_econ_b2] wrote {os.path.basename(OUT_JSON)}")


def _f(x, nd=3):
    if x is None:
        return "n/a"
    if isinstance(x, float) and x != x:
        return "nan"
    if isinstance(x, (int, float)):
        return f"{x:+,.{nd}f}"
    return str(x)


def _print_console(results):
    print("\n" + "=" * 86)
    print("B2 FILL-AWARE NET ECONOMICS - SUMMARY  (cost reduction, not alpha)")
    print("=" * 86)
    print(f"  wallet-fill floors computed: {[f'K{K}' for K in K_RUNGS]}; "
          f"headline K{K_HEADLINE}. The blocks printed below are the headline rung.")
    for measure in MEASURES:
        mb = results["by_measure"][measure]
        dp = mb["deploy_point"]
        bc = mb["b1_bound_check"]
        print("-" * 86)
        print(f"[{measure}]  deploy point f={DEPLOY_POINT['f']} w={DEPLOY_POINT['w']} "
              f"c={DEPLOY_POINT['c']} bps:")
        if "by_fee_tier" in dp:
            print(f"   {'tier':<10} {'b2_net_bps':>12} {'b2_net_$':>16} "
                  f"{'delta_vs_base_$':>18} {'net>0':>6}")
            for tier in FEE_TIERS:
                t = dp["by_fee_tier"][tier]
                print(f"   {tier:<10} {_f(t['b2_net_bps'],3):>12} {_f(t['b2_net_usd'],0):>16} "
                      f"{_f(t['delta_vs_baseline_usd'],0):>18} {str(t['b2_net_positive']):>6}")
        best = bc["best_delta_cell"]
        print(f"   best delta cell: {best['key']} @ {best['tier']} "
              f"delta=${best['delta_usd']:,.0f} b2_net=${best['b2_net_usd']:,.0f} "
              f"(net_bps={_f(best.get('b2_net_bps'),3)})")
        print(f"   any B2 net positive anywhere on the surface: {bc['any_b2_net_positive']} "
              f"| best-delta-is-decline-heavy(f<=0.25): {bc['best_delta_is_decline_heavy']}")
        for tag in ("placebo_t4_0fee", "placebo_rebate3"):
            pb = mb[tag]
            print(f"   {tag}: obs delta ${pb['observed_delta_usd']:,.0f} vs random "
                  f"${pb['random_mean_delta_usd']:,.0f} (p={_f(pb['permutation_p'],4)}, "
                  f"beats_random={pb['toxicity_beats_random']})")
        print(f"   ladder (deploy point, t4_0fee, b2_net_bps then delta vs baseline $):")
        for K in K_RUNGS:
            cell = mb["by_K"][f"K{K}"]["deploy_point"].get("by_fee_tier", {})
            t = cell.get("t4_0fee")
            mark = " <- headline" if K == K_HEADLINE else ""
            if t is None:
                print(f"     K{K:<5}: cell absent{mark}")
            else:
                print(f"     K{K:<5}: {_f(t['b2_net_bps'],3):>12} "
                      f"{_f(t['delta_vs_baseline_usd'],0):>18}{mark}")
    print("=" * 86)
    print("  READING: B2 is a fill-aware COST overlay. It is bounded above by B1 "
          "(decline-entirely),")
    print("  and the symmetric maker is net-negative at every fee tier, so B2 net "
          "positive only")
    print("  appears (if at all) in fragile rebate-tier corners - a cost reduction, "
          "not alpha.")
    print("=" * 86)


if __name__ == "__main__":
    main()
