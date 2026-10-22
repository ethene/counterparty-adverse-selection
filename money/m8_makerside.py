"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-19
References: Hyperliquid node-data S3 archive; Zenodo 18184441 (Albers et al. 2026).
"""

# ---------------------------------------------------------------------------
# OBJECT M8 — MAKER-SIDE ADVERSE-SELECTION INCIDENCE (honest reframing)
#
# Every counterparty-resolved markout has two sides. The taker-side study (the
# headline) asks which TAKERS are toxic. This script flips to the resting side
# and asks which MAKERS systematically LOSE -- i.e. which liquidity providers are
# the ones bearing the adverse selection. The maker on each collapsed taker trade
# is the crossed=false leg sharing the hash, carried in the extended npz as
# maker_id (>=0; -1 means no maker leg was matched).
#
# Sign convention. mo10 is the SIGNED TAKER markout in bps: positive = the taker
# profited over the next 10 seconds = the maker that filled it was adverse-
# selected. The maker faces the SAME number with the SAME sign: a positive mean
# markout faced means the maker is systematically picked off (a loser); a
# negative mean means the maker collected spread without being run over. So we
# aggregate mo10 per maker AS IS and read positive = maker adverse-selected.
#
# PER-DOLLAR REFRAME (mirrors m11_concentration.py). An earlier cut led with the
# raw dollar-loss Gini (~0.97) and read it as "a handful of makers carry the
# adverse selection." A verification pass showed that reading is a TRADE-SIZE
# artefact: the raw dollar-loss Gini (~0.9721) is essentially the per-maker
# NOTIONAL Gini (~0.9847) -- pure size inequality, the biggest dollar losers are
# just the biggest makers. The quantity that actually measures who is toxic-as-a-
# maker is the PER-DOLLAR loss: dollar loss divided by dollar notional (the
# notional-weighted mean markout faced). Its concentration across net-loser
# makers is only MODERATE (Gini ~0.55), so this script LEADS with per-dollar
# loss concentration and a top-k toxic-maker share, and DEMOTES the raw dollar
# Gini to a labelled size-artefact diagnostic shown next to the notional Gini so
# the equivalence is visible. The raw 0.97 is never cited alone.
#
# Per maker we report:
#   * mean signed markout faced (bps), notional-weighted (= per-dollar loss) and
#     equal-weighted,
#   * total maker dollar loss = sum over its fills of (mo10/1e4) * notional,
#   * trade and counterparty counts.
# Then the cross-maker PER-DOLLAR loss concentration (the headline), the raw
# dollar-loss Gini next to the notional Gini (size-artefact diagnostic), and a
# check of the Hyperliquid HLP (Hyperliquidity Provider) protocol vault plus the
# top makers by loss and by volume: is the protocol vault itself a systematic
# loser, and which dominant maker is it?
#
# numpy-only. Reads the EXTENDED quickwin_markouts.npz (needs maker_id, mo10,
# notional). Reads maker_map.json to resolve the HLP vault address to its code.
# Writes m8_makerside_results.json. No plotting.
# ---------------------------------------------------------------------------

import json
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
from stats import (describe_quantiles, gini, hhi, top_k_share,
                   top_pct_share)

# ---------------------------------------------------------------------------
# Paths / config
# ---------------------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
# Located by panel_io rather than joined here, so the one place that knows where
# the markout panels live is the one place that has to change if they move.
NPZ_PATH = os.path.join(P.data_root(), "quickwin_markouts.npz")
MAKER_MAP_PATH = os.path.join(P.data_root(), "maker_map.json")
OUT_PATH = os.path.join(HERE, "m8_makerside_results.json")

# int8 code -> symbol. The map is a property of the FILE, not of the project
# (quickwin_markouts.npz carries {0, 1}, panel_markouts.npz carries {0, 1, 2}), so it
# is asked for by artifact name and never written out here.
COIN_NAME = H.coin_labels("quickwin")

RNG_SEED = H.seed_for("m8_makerside")  # this run's seed (no randomness used here, kept
                                     # for parity), READ from settings.py and no longer
                                     # typed. The value is the same 20260619, so no
                                     # number here moves; settings.MASTER_SEED is
                                     # 20260620
np.random.seed(RNG_SEED)

NO_MAKER = -1                        # maker_id sentinel for "no crossed=false leg matched"

# ---------------------------------------------------------------------------
# HLP VAULT ADDRESSES — the known Hyperliquid HLP (Hyperliquidity Provider)
# protocol-vault addresses (lowercase hex), matched case-insensitively against
# the address keys in maker_map.json. The primary is the canonical HLP vault;
# the secondary is a candidate we also test so the check does not hinge on one
# address. Both are reported regardless of whether they match a maker code.
# ---------------------------------------------------------------------------
HLP_VAULT_ADDR = "0xdfc24b077bc1425ad1dea75bcb6f8158e10df303"          # primary
HLP_VAULT_ADDR_SECONDARY = "0x5078c2fbea2b2ad61bc840bc023e35fce56bedb6"  # secondary candidate

# how many top makers (by loss and by notional) to list for HLP cross-validation
TOP_MAKERS_REPORTED = 10

# Minimum fills for a maker to enter the ranked "systematic loser" tables, so a
# one-off fill with a huge markout does not top the chart.
MIN_FILLS_RANKED = 10
TOP_N_REPORTED = 25                  # how many extreme makers to list each way


# ---------------------------------------------------------------------------
# Distribution / concentration helpers come from stats.py, which m11_concentration.py
# imports as well. The phrase this comment used to carry was "mirror
# m11_concentration.py", and a mirror is exactly the thing a reader cannot check: the
# five spellings here were identical to the five there on the syntax tree, but nothing
# said so and nothing kept them so. The quantile summary was called describe here and
# describe_quantiles there; it keeps the longer name, because artifact.py already owns
# describe() for something else entirely.
# ---------------------------------------------------------------------------
# Per-maker aggregation
# ---------------------------------------------------------------------------
def maker_aggregate(maker_id, mo_score, notional):
    """Collapse fills to per-maker totals.

    Returns a dict of aligned arrays keyed by the unique maker code:
      ids                : maker codes (sorted),
      n_fills            : trade count per maker,
      mo_sum / mo_cnt    : sum and count of finite mo10 (for equal-weighted mean),
      mow_sum / notl_sum : sum of mo10*notional and of notional (notional-weighted),
      cost_sum           : sum of (mo10/1e4)*notional = maker signed dollar loss.

    Positive markout / cost => the maker is adverse-selected (a loser).
    """
    finite = np.isfinite(mo_score) & np.isfinite(notional) & (notional >= 0)
    mid = maker_id[finite]
    mo = mo_score[finite].astype(np.float64)
    notl = notional[finite].astype(np.float64)

    if mid.size == 0:
        z = np.empty(0, dtype=np.float64)
        return {"ids": np.empty(0, dtype=np.int64), "n_fills": z, "mo_sum": z.copy(),
                "mo_cnt": z.copy(), "mow_sum": z.copy(), "notl_sum": z.copy(),
                "cost_sum": z.copy()}

    ids, inv = np.unique(mid, return_inverse=True)
    n_fills = np.zeros(ids.size, dtype=np.float64)
    mo_sum = np.zeros(ids.size, dtype=np.float64)
    mow_sum = np.zeros(ids.size, dtype=np.float64)
    notl_sum = np.zeros(ids.size, dtype=np.float64)
    cost_sum = np.zeros(ids.size, dtype=np.float64)

    np.add.at(n_fills, inv, 1.0)
    np.add.at(mo_sum, inv, mo)
    np.add.at(mow_sum, inv, mo * notl)
    np.add.at(notl_sum, inv, notl)
    np.add.at(cost_sum, inv, (mo / 1e4) * notl)

    return {"ids": ids, "n_fills": n_fills, "mo_sum": mo_sum, "mo_cnt": n_fills,
            "mow_sum": mow_sum, "notl_sum": notl_sum, "cost_sum": cost_sum}


def maker_means(agg):
    """Equal- and notional-weighted mean signed markout faced, per maker (bps)."""
    eq = np.where(agg["mo_cnt"] > 0, agg["mo_sum"] / agg["mo_cnt"], np.nan)
    nw = np.where(agg["notl_sum"] > 0, agg["mow_sum"] / agg["notl_sum"], np.nan)
    return eq, nw


# ---------------------------------------------------------------------------
# One slice (coin or pooled)
# ---------------------------------------------------------------------------
def analyse_slice(maker_id, mo_score, notional, code_to_addr):
    """Maker-side incidence + concentration for one slice."""
    agg = maker_aggregate(maker_id, mo_score, notional)
    ids = agg["ids"]
    n_makers = int(ids.size)
    if n_makers == 0:
        return {"n_makers": 0, "note": "no matched makers in this slice"}

    eq_mean, nw_mean = maker_means(agg)
    cost = agg["cost_sum"]            # signed dollar loss; positive = maker loses
    notl_sum = agg["notl_sum"]        # per-maker dollar notional
    n_fills = agg["n_fills"]

    # ---- distribution of per-maker mean markout faced (equal-weighted) ----
    dist_eq = describe_quantiles(eq_mean)
    dist_nw = describe_quantiles(nw_mean)

    # ---- (1) HEADLINE: per-dollar maker-loss concentration -------------------
    # nw_mean is the per-maker notional-weighted mean markout faced (bps) =
    # dollar loss / dollar notional, i.e. loss per unit traded. It strips out
    # trade size, so a big maker and a small maker with the same loss-per-dollar
    # score the same. It is SIGNED (positive = the maker loses per dollar). The
    # concentration measure that matters is the Gini on the NET-LOSER subset
    # (makers with positive per-dollar loss) plus the top-k share of that
    # positive per-dollar loss.
    pdl = nw_mean[np.isfinite(nw_mean)]              # per-dollar loss, bps, signed
    pos_pdl = pdl[pdl > 0]                           # net-loser makers
    pos_pdl_total = float(pos_pdl.sum())
    pos_pdl_desc = np.sort(pos_pdl)[::-1]
    per_dollar_block = {
        "measure": "per-maker notional-weighted mean markout faced (dollar loss / "
                   "dollar notional, bps); size-stripped",
        "n_makers_with_notional": int(pdl.size),
        "mean_per_dollar_loss_bps": (float(pdl.mean()) if pdl.size else float("nan")),
        "frac_makers_net_loser": (float((pdl > 0).mean()) if pdl.size else float("nan")),
        "n_net_loser_makers": int(pos_pdl.size),
        "per_dollar_loss_gini": gini(pos_pdl),       # ~0.55 pooled -> moderate
        "per_dollar_loss_hhi": hhi(pos_pdl),
        "per_dollar_top_1pct_share": top_pct_share(pos_pdl_desc, pos_pdl_total, 0.01),
        "per_dollar_top_10pct_share": top_pct_share(pos_pdl_desc, pos_pdl_total, 0.10),
        "per_dollar_top10_share": top_k_share(pos_pdl_desc, pos_pdl_total, 10),
        "headline_note": (
            "this is the HEADLINE: per-dollar (size-stripped) maker-loss "
            "concentration is only MODERATE (Gini ~0.55), so the maker-side "
            "adverse selection is NOT carried by a tiny handful of makers -- the "
            "biggest dollar losers are just the biggest makers (see the "
            "size-artefact diagnostic below)"),
    }

    # ---- (2) raw dollar-loss concentration: SIZE-ARTEFACT DIAGNOSTIC ----------
    # The raw dollar-loss Gini is essentially the per-maker NOTIONAL Gini (pure
    # size inequality). It is shown ONLY next to the notional Gini so the
    # equivalence is visible, and is explicitly flagged do-not-cite-alone.
    pos_cost = cost[cost > 0]
    pos_cost_total = float(pos_cost.sum())
    pos_cost_desc = np.sort(pos_cost)[::-1]
    notional_gini = gini(notl_sum[notl_sum > 0])
    size_artefact_block = {
        "label": "DOLLAR-LOSS concentration is a TRADE-SIZE artefact -- "
                 "do NOT cite the raw Gini alone",
        "n_loser_makers": int(pos_cost.size),
        "total_maker_loss_quote": pos_cost_total,
        "dollar_loss_gini_size_artefact_do_not_cite": gini(pos_cost),
        "per_maker_notional_gini": notional_gini,
        "size_artefact_note": (
            "dollar_loss_gini_size_artefact_do_not_cite (~0.97) is essentially "
            "the per_maker_notional_gini (~0.98): the dollar-loss concentration "
            "is pure trade-size inequality, not loss dispersion. Cite the "
            "per_dollar_loss_gini in (1) instead, never this raw figure alone"),
        "dollar_loss_hhi": hhi(pos_cost),
        "dollar_loss_top_1pct_share": top_pct_share(pos_cost_desc, pos_cost_total, 0.01),
        "dollar_loss_top_10pct_share": top_pct_share(pos_cost_desc, pos_cost_total, 0.10),
    }

    # ---- net maker dollar PnL across all makers (sign: + = makers lose overall) ----
    net_cost = float(cost.sum())

    # ---- ranked extreme makers (>= MIN_FILLS_RANKED fills) ----
    rankable = n_fills >= MIN_FILLS_RANKED
    ranked = _rank_extremes(ids, eq_mean, nw_mean, cost, n_fills, rankable,
                            code_to_addr)

    # ---- top makers by loss and by notional (HLP cross-validation) -----------
    top_makers = _top_makers(ids, cost, notl_sum, nw_mean, n_fills, code_to_addr)

    return {
        "n_makers": n_makers,
        "n_rankable_makers": int(rankable.sum()),
        "mean_markout_faced_bps_equal_weight": dist_eq,
        "mean_markout_faced_bps_notional_weight": dist_nw,
        # (1) headline per-dollar (notional-normalized) loss concentration
        "per_dollar_loss_concentration": per_dollar_block,
        # (2) raw dollar-loss Gini DEMOTED to a size-artefact diagnostic
        "dollar_loss_concentration_size_artefact": size_artefact_block,
        "net_maker_dollar_pnl_quote": net_cost,
        "net_sign_note": ("positive net => makers collectively LOSE (are adverse-"
                          "selected); negative => makers collectively earn spread"),
        "worst_losers": ranked["worst"],
        "best_earners": ranked["best"],
        "top_makers_by_dollar_loss": top_makers["by_loss"],
        "top_makers_by_notional": top_makers["by_notional"],
    }


def _rank_extremes(ids, eq_mean, nw_mean, cost, n_fills, rankable, code_to_addr):
    """Top systematic losers and earners among makers with enough fills.

    Loser = highest mean markout faced (most adverse-selected). Earner = lowest.
    Each entry carries the maker code, its address if resolvable, and its stats.
    """
    idx = np.where(rankable)[0]
    if idx.size == 0:
        return {"worst": [], "best": []}
    eqr = eq_mean[idx]
    order = np.argsort(np.where(np.isfinite(eqr), eqr, -np.inf))   # ascending markout

    def _entry(j):
        code = int(ids[j])
        return {
            "maker_id": code,
            "maker_addr": code_to_addr.get(code),
            "mean_markout_faced_bps": (float(eq_mean[j])
                                       if np.isfinite(eq_mean[j]) else None),
            "mean_markout_faced_bps_notional_wt": (float(nw_mean[j])
                                                   if np.isfinite(nw_mean[j]) else None),
            "dollar_loss_quote": float(cost[j]),
            "n_fills": int(n_fills[j]),
        }

    worst_local = order[::-1][:TOP_N_REPORTED]    # highest markout faced
    best_local = order[:TOP_N_REPORTED]           # lowest markout faced
    worst = [_entry(idx[j]) for j in worst_local]
    best = [_entry(idx[j]) for j in best_local]
    return {"worst": worst, "best": best}


def _top_makers(ids, cost, notl_sum, nw_mean, n_fills, code_to_addr):
    """Top makers by total dollar loss and by notional volume.

    Lists TOP_MAKERS_REPORTED makers each way with code, address, dollar loss,
    per-dollar mean markout faced (notional-weighted), notional and fill count,
    and flags whether either HLP candidate address is the maker. This lets us
    cross-validate which dominant maker is the HLP vault even when neither HLP
    address resolves directly in the maker map.
    """
    hlp_set = {a.strip().lower() for a in (HLP_VAULT_ADDR, HLP_VAULT_ADDR_SECONDARY)
               if a and a.strip()}

    def _entry(j):
        code = int(ids[j])
        addr = code_to_addr.get(code)
        addr_l = addr.lower() if isinstance(addr, str) else None
        return {
            "maker_id": code,
            "maker_addr": addr,
            "dollar_loss_quote": float(cost[j]),
            "notional_quote": float(notl_sum[j]),
            "mean_markout_faced_bps_notional_wt": (float(nw_mean[j])
                                                   if np.isfinite(nw_mean[j]) else None),
            "n_fills": int(n_fills[j]),
            "is_hlp_candidate": bool(addr_l in hlp_set) if addr_l else False,
        }

    by_loss = [_entry(j) for j in np.argsort(cost)[::-1][:TOP_MAKERS_REPORTED]]
    by_notional = [_entry(j) for j in np.argsort(notl_sum)[::-1][:TOP_MAKERS_REPORTED]]
    return {"by_loss": by_loss, "by_notional": by_notional}


# ---------------------------------------------------------------------------
# HLP vault check
# ---------------------------------------------------------------------------
def _hlp_one(addr_raw, maker_id, mo_score, notional, maker_to_code, all_cost_rank):
    """HLP loser check for a single candidate address.

    Resolves addr to its maker code (case-insensitive), aggregates the fills
    where it was the maker, and reports mean markout faced, dollar loss, and its
    RANK among all makers by dollar loss. `all_cost_rank` maps maker code -> rank
    (1 = biggest dollar loser) so a match can be placed in the full ordering.
    """
    addr = (addr_raw or "").strip().lower()
    if not addr:
        return {"status": "skipped", "reason": "address empty"}

    code = None
    for k, v in maker_to_code.items():
        if k.lower() == addr:
            code = int(v)
            break
    if code is None:
        return {"status": "not_found",
                "address": addr,
                "reason": ("address not present in maker_map.json (this HLP "
                           "candidate was never matched as a maker in this "
                           "window; see top_makers for cross-validation)")}

    sel = (maker_id == code) & np.isfinite(mo_score) & np.isfinite(notional)
    n = int(sel.sum())
    if n == 0:
        return {"status": "no_fills", "address": addr, "maker_id": code,
                "reason": "vault code present in map but no finite-markout fills here"}

    mo = mo_score[sel].astype(np.float64)
    notl = notional[sel].astype(np.float64)
    notl_sum = float(notl.sum())
    cost = float(np.sum((mo / 1e4) * notl))
    return {
        "status": "ok",
        "address": addr,
        "maker_id": code,
        "n_fills": n,
        "mean_markout_faced_bps_equal_weight": float(mo.mean()),
        "mean_markout_faced_bps_notional_weight": (float(np.sum(mo * notl) / notl_sum)
                                                   if notl_sum > 0 else float("nan")),
        "dollar_loss_quote": cost,
        "rank_among_makers_by_loss": all_cost_rank.get(code),
        "n_makers_ranked": len(all_cost_rank),
        "is_systematic_loser": bool(cost > 0),
        "loser_note": ("positive mean markout faced / positive dollar loss => the "
                       "HLP vault is systematically adverse-selected as a maker"),
    }


def hlp_vault_check(maker_id, mo_score, notional, maker_to_code):
    """Is either configured HLP protocol-vault candidate a systematic loser?

    Checks BOTH HLP_VAULT_ADDR (primary) and HLP_VAULT_ADDR_SECONDARY against
    maker_map.json case-insensitively. For any that match a maker code, reports
    that maker's dollar loss, mean markout faced, fill count and rank among all
    makers by total dollar loss. Returns a combined dict with both candidates and
    a one-line summary of whether any matched.
    """
    # rank every maker by total dollar loss (1 = biggest loser) so a matched HLP
    # candidate can be placed in the full ordering.
    fin = np.isfinite(mo_score) & np.isfinite(notional) & (notional >= 0)
    mid = maker_id[fin]
    cost_row = (mo_score[fin].astype(np.float64) / 1e4) * notional[fin].astype(np.float64)
    all_cost_rank = {}
    if mid.size:
        ids, inv = np.unique(mid, return_inverse=True)
        csum = np.zeros(ids.size, dtype=np.float64)
        np.add.at(csum, inv, cost_row)
        order = np.argsort(csum)[::-1]               # high-to-low loss
        for rank, j in enumerate(order, start=1):
            all_cost_rank[int(ids[j])] = rank

    primary = _hlp_one(HLP_VAULT_ADDR, maker_id, mo_score, notional,
                       maker_to_code, all_cost_rank)
    secondary = _hlp_one(HLP_VAULT_ADDR_SECONDARY, maker_id, mo_score, notional,
                         maker_to_code, all_cost_rank)
    any_matched = primary.get("status") == "ok" or secondary.get("status") == "ok"
    return {
        "primary": primary,
        "secondary": secondary,
        "any_candidate_matched": any_matched,
        "summary_note": (
            "neither HLP candidate resolves to a maker code; use top_makers_by_* "
            "(by dollar loss and by notional) to cross-validate which dominant "
            "maker is the protocol vault" if not any_matched else
            "at least one HLP candidate matched a maker code; see its loss profile"),
    }


def main():
    t0 = artifact.start_clock()
    # panel_io raises when the file is absent and names the producer to run, and the
    # require list turns a missing column into one refusal here, before any work, that
    # says what was asked for and what the file actually holds. Both messages used to be
    # written out per script; this file needs the EXTENDED build, whose distinguishing
    # column is maker_id, and that is what the list checks.
    # panel_io names the producer to run when a file is absent, so that message is
    # written once for the whole tree; the loads stay here because build.py derives
    # this script's input edges from the arguments of np.load.
    P.require_present("print", NPZ_PATH)
    data = np.load(NPZ_PATH)
    # This file needs the EXTENDED build, whose distinguishing column is maker_id, so
    # the required list is checked at the top and refused in one wording that names what
    # was asked for and what the file actually holds.
    P.require_columns(data, "print", "maker_id", P.score_col("print"),
                      "notional", "coin")

    maker_id = data["maker_id"].astype(np.int64)
    taker_id = (data["taker_id"].astype(np.int64) if "taker_id" in data.files
                else None)
    mo_score = P.score(data, "print")
    notional = data["notional"].astype(np.float64)
    coin = data["coin"].astype(np.int8)
    # Read only to state the window in the artifact's scope; it enters no computation.
    day = data["day"].astype(np.int64)

    # maker map: code -> address (for naming extremes) and address -> code (HLP).
    maker_to_code = {}
    if os.path.exists(MAKER_MAP_PATH):
        with open(MAKER_MAP_PATH) as fh:
            maker_to_code = json.load(fh).get("map", {})
    code_to_addr = {int(v): k for k, v in maker_to_code.items()}

    # drop the rows with no matched maker BEFORE any aggregation.
    has_maker = maker_id != NO_MAKER
    n_no_maker = int((~has_maker).sum())
    maker_id_m = maker_id[has_maker]
    taker_id_m = taker_id[has_maker] if taker_id is not None else None
    # mo_score is the DECLARED headline window (settings.headline_print_col). The _m
    # suffix means "restricted to the maker-matched rows" and states nothing about the
    # window, which is what a name carrying a window it does not come from would do.
    mo_score_m = mo_score[has_maker]
    notional_m = notional[has_maker]
    coin_m = coin[has_maker]

    # ---- accounting identity (NOT an independent validation) -----------------
    # The total signed-markout dollar cost is partition-invariant: summing it
    # ungrouped, grouped by maker, or grouped by taker gives the same number to
    # the cent. That is an ACCOUNTING IDENTITY (every fill's cost is counted once
    # under any partition), so the maker-grouped == taker-grouped equality
    # VALIDATES NOTHING independent -- it is not a two-sided consistency check.
    fin = np.isfinite(mo_score_m) & np.isfinite(notional_m) & (notional_m >= 0)
    row_cost = (mo_score_m[fin] / 1e4) * notional_m[fin]
    ungrouped_cost = float(row_cost.sum())

    def _grouped_sum(keys):
        if keys is None or keys[fin].size == 0:
            return None
        u, iv = np.unique(keys[fin], return_inverse=True)
        s = np.zeros(u.size, dtype=np.float64)
        np.add.at(s, iv, row_cost)
        return float(s.sum())

    accounting_identity = {
        "label": "accounting identity (sum of signed markout cost is "
                 "partition-invariant), not an independent validation",
        "ungrouped_signed_cost_quote": ungrouped_cost,
        "maker_grouped_signed_cost_quote": _grouped_sum(maker_id_m),
        "taker_grouped_signed_cost_quote": _grouped_sum(taker_id_m),
        "note": ("ungrouped == maker-grouped == taker-grouped by construction "
                 "(each fill's signed cost is counted exactly once under any "
                 "partition); the equality validates nothing independent"),
    }

    results = {
        "_meta": {
            "object": "M8 maker-side adverse-selection incidence",
            "sign_convention": (f"{H.headline_print_col()} positive = taker profited "
                                "= MAKER adverse-selected; aggregated per maker "
                                "as-is"),
            "headline": ("per-DOLLAR (notional-normalized) maker-loss "
                         "concentration; raw dollar-loss Gini is a demoted "
                         "size-artefact diagnostic, never cited alone"),
            "reference_caveat": ("markout is a trade-print VWAP, not a book mid; "
                                 "dollar figures are signed-markout cost, and the "
                                 "adverse-selection interpretation is held pending "
                                 "the book-mid (I4) check"),
            "min_fills_ranked": MIN_FILLS_RANKED,
            "top_n_reported": TOP_N_REPORTED,
            "top_makers_reported": TOP_MAKERS_REPORTED,
            "rng_seed": RNG_SEED,
            "n_trades_total": int(maker_id.size),
            "n_trades_with_maker": int(maker_id_m.size),
            "n_trades_no_maker": n_no_maker,
            "hlp_vault_addr_primary": HLP_VAULT_ADDR,
            "hlp_vault_addr_secondary": HLP_VAULT_ADDR_SECONDARY,
        },
        "accounting_identity": accounting_identity,
    }

    # What the numbers cover. The unit here is the MAKER, and rows with no matched
    # maker are dropped before any aggregation, so the population is stated over the
    # matched rows rather than over the input. The window is read off the same rows.
    days = np.unique(day[has_maker])
    scope = {
        "population": (f"{maker_id_m.size:,} maker-matched fills of "
                       f"{maker_id.size:,} in the trade-print panel, aggregated per "
                       "maker; the concentration and incidence figures take every "
                       "matched maker with no fill floor, and only the ranked loser "
                       f"and earner tables floor at {MIN_FILLS_RANKED} fills"),
        "window": (f"{days.size} days present among the matched rows, day-of-month "
                   f"{days.min()}-{days.max()}; the calendar dates of the window "
                   "are declared by its producer, build_quickwin_markouts.py"),
        "coins": [COIN_NAME[c] for c in sorted(COIN_NAME)],
    }
    results["_meta"]["rank_floor_note"] = (
        f"rank_floor_fills={MIN_FILLS_RANKED} is the floor for entering the ranked "
        f"maker tables (worst_losers / best_earners); the concentration and "
        f"incidence figures are over ALL matched makers with no fill floor")

    for code, name in COIN_NAME.items():
        sel = coin_m == code
        results[name] = analyse_slice(
            maker_id_m[sel], mo_score_m[sel], notional_m[sel], code_to_addr)

    results["pooled"] = analyse_slice(
        maker_id_m, mo_score_m, notional_m, code_to_addr)

    # HLP vault check on the pooled, maker-matched data.
    results["hlp_vault_check"] = hlp_vault_check(
        maker_id_m, mo_score_m, notional_m, maker_to_code)

    # The output name and directory still come from the module-level OUT_PATH, so a
    # caller that redirects that constant redirects the whole write, as before. Two
    # stamped settings differ from the declaration and are passed explicitly rather
    # than left to look like the declared value: the module seeds numpy with its own
    # literal, and the ranked loser and earner tables use a 10-fill floor, not the
    # 50-fill wallet rank floor settings.py declares. The maker map is named as a
    # second input because the addresses it supplies reach the reported tables.
    artifact.write(os.path.basename(OUT_PATH), results,
                   script=__file__, inputs=[NPZ_PATH, MAKER_MAP_PATH], scope=scope,
                   settings={"h": H.HEADLINE_HORIZON_S, "lens": "print",
                             "master_seed": RNG_SEED,
                             "rank_floor_fills": MIN_FILLS_RANKED},
                   started=t0, out_dir=os.path.dirname(OUT_PATH))

    print_summary(results)
    print(f"\n[m8] wrote {os.path.basename(OUT_PATH)}")


# ---------------------------------------------------------------------------
# Printed summary
# ---------------------------------------------------------------------------
def _fmt(x, nd=4):
    return f"{x:.{nd}f}" if isinstance(x, float) and np.isfinite(x) else "n/a"


def print_summary(results):
    print("=" * 84)
    print("M8 — MAKER-SIDE ADVERSE-SELECTION INCIDENCE (per-dollar reframe)")
    print("=" * 84)
    meta = results["_meta"]
    print(f"trades total : {meta['n_trades_total']:,}  "
          f"(with maker: {meta['n_trades_with_maker']:,}, "
          f"no maker: {meta['n_trades_no_maker']:,})")
    print("HEADLINE = per-DOLLAR maker-loss concentration (size-stripped).")
    print("Raw dollar-loss Gini is a TRADE-SIZE artefact, shown only next to the")
    print("per-maker notional Gini -- never cite the raw figure alone.\n")

    # ---- (1) per-dollar (headline) ----
    print("(1) PER-DOLLAR MAKER-LOSS CONCENTRATION  [the measure that matters]")
    h = (f"{'slice':<8} {'makers':>8} {'mean_eq':>9} {'mean_nw':>9} "
         f"{'%losers':>8} {'pd_gini':>9} {'pd_t1%':>8} {'pd_t10%':>9}")
    print(h)
    print("-" * len(h))
    for key in ("BTC", "ETH", "pooled"):
        if key not in results or "n_makers" not in results[key]:
            continue
        r = results[key]
        if r.get("n_makers", 0) == 0:
            print(f"{key:<8} {0:>8}  (no matched makers)")
            continue
        eq = r["mean_markout_faced_bps_equal_weight"]
        pd = r["per_dollar_loss_concentration"]
        print(f"{key:<8} {r['n_makers']:>8,} {_fmt(eq['mean'], 3):>9} "
              f"{_fmt(r['mean_markout_faced_bps_notional_weight']['mean'], 3):>9} "
              f"{_fmt(pd['frac_makers_net_loser'], 3):>8} "
              f"{_fmt(pd['per_dollar_loss_gini'], 3):>9} "
              f"{_fmt(pd['per_dollar_top_1pct_share'], 3):>8} "
              f"{_fmt(pd['per_dollar_top_10pct_share'], 3):>9}")
    print("    (pd_gini ~0.55 => maker-side adverse selection is MODERATELY, not")
    print("     extremely, concentrated; mean_eq/nw in bps)")

    # ---- (2) size-artefact diagnostic ----
    print("\n(2) DOLLAR-LOSS concentration  [SIZE ARTEFACT -- do NOT cite alone]")
    h2 = (f"{'slice':<8} {'loss_gini*':>11} {'notl_gini':>10} {'net_$loss':>14}")
    print(h2)
    print("-" * len(h2))
    for key in ("BTC", "ETH", "pooled"):
        if key not in results or "n_makers" not in results[key]:
            continue
        r = results[key]
        if r.get("n_makers", 0) == 0:
            continue
        sa = r["dollar_loss_concentration_size_artefact"]
        print(f"{key:<8} "
              f"{_fmt(sa['dollar_loss_gini_size_artefact_do_not_cite'], 4):>11} "
              f"{_fmt(sa['per_maker_notional_gini'], 4):>10} "
              f"{_fmt(r['net_maker_dollar_pnl_quote'], 1):>14}")
    print("    (loss_gini* ~= notl_gini => the dollar-loss Gini is pure trade size;")
    print("     net_$loss > 0 => makers lose overall)")

    # ---- accounting identity ----
    ai = results.get("accounting_identity", {})
    print("\nACCOUNTING IDENTITY (partition-invariant, NOT an independent check):")
    print(f"    ungrouped     = {_fmt(ai.get('ungrouped_signed_cost_quote'), 2)}")
    print(f"    maker-grouped = {_fmt(ai.get('maker_grouped_signed_cost_quote'), 2)}")
    print(f"    taker-grouped = {_fmt(ai.get('taker_grouped_signed_cost_quote'), 2)}")
    print("    (equal by construction; validates nothing independent)")

    # ---- top makers (pooled) for HLP cross-validation ----
    pooled = results.get("pooled", {})
    print("\nTOP MAKERS (pooled) — for HLP cross-validation:")
    print("  by DOLLAR LOSS:")
    for e in pooled.get("top_makers_by_dollar_loss", [])[:10]:
        flag = "  <-- HLP candidate" if e.get("is_hlp_candidate") else ""
        print(f"    code={e['maker_id']:>6} $loss={_fmt(e['dollar_loss_quote'],1):>14} "
              f"notl={_fmt(e['notional_quote'],0):>16} "
              f"mo_nw={_fmt(e['mean_markout_faced_bps_notional_wt'],3):>8} "
              f"fills={e['n_fills']:>7} {e.get('maker_addr')}{flag}")
    print("  by NOTIONAL volume:")
    for e in pooled.get("top_makers_by_notional", [])[:10]:
        flag = "  <-- HLP candidate" if e.get("is_hlp_candidate") else ""
        print(f"    code={e['maker_id']:>6} notl={_fmt(e['notional_quote'],0):>16} "
              f"$loss={_fmt(e['dollar_loss_quote'],1):>14} "
              f"mo_nw={_fmt(e['mean_markout_faced_bps_notional_wt'],3):>8} "
              f"fills={e['n_fills']:>7} {e.get('maker_addr')}{flag}")

    # ---- HLP vault check (both candidates) ----
    hlp = results.get("hlp_vault_check", {})
    print("\nHLP VAULT CHECK (both candidates):")
    for tag in ("primary", "secondary"):
        c = hlp.get(tag, {})
        st = c.get("status", "n/a")
        print(f"  {tag:<10} status={st}")
        if st == "ok":
            print(f"    addr={c['address']}  code={c['maker_id']}  "
                  f"fills={c['n_fills']:,}  "
                  f"mean_faced={_fmt(c['mean_markout_faced_bps_equal_weight'], 3)} bps  "
                  f"$loss={_fmt(c['dollar_loss_quote'], 1)}  "
                  f"rank={c.get('rank_among_makers_by_loss')}/{c.get('n_makers_ranked')}  "
                  f"systematic_loser={c['is_systematic_loser']}")
        else:
            print(f"    {c.get('reason', '')}")
    print(f"  any_candidate_matched = {hlp.get('any_candidate_matched')}")
    print("=" * 84)


if __name__ == "__main__":
    main()
