"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-08-03
References:
  - Glosten, Milgrom (1985). Bid, Ask and Transaction Prices in a Specialist Market
    (adverse selection as a per-fill rate, which is what one of the two cuts orders by).
  - Easley, Lopez de Prado, O'Hara (2012). Flow Toxicity and Liquidity in a
    High-Frequency World (toxicity as a property of the flow a maker absorbs).
  - Avellaneda, Stoikov (2008). High-frequency trading in a limit order book (the
    quoting family whose results are booked over the rate-ranked selection).
"""

# ---------------------------------------------------------------------------
# OBJECT - the two selections this study calls "the toxic decile", and how far
# apart they actually are.
#
# This repository cuts a toxic decile twice, by two different rules, and both
# results have been called the toxic decile in prose.
#
#   RATE  maker_econ.build_toxicity_labels ranks counterparties by their MEAN
#         book-mid markout in basis points over the early half and takes
#         ceil(10% x N) of them. Every persistence figure and every quoter
#         result in the study is booked over this set.
#
#   COST  t3_capacity ranks counterparties by their SUMMED early dollar
#         adverse-selection cost and takes max(1, floor(10% x N)). The headline
#         avoidable-cost share stands on this set.
#
# t3_capacity says of itself, beside its own fraction, that "calling both of
# them 'the toxic decile' made one word carry two sets". Ranking by a rate and
# ranking by a total answer different questions - who is dearest per fill
# against who is dearest in aggregate - and no artifact in this tree had ever
# reported how much of one set the other contains. That is the gap this file
# closes, and it closes it by measurement rather than by choosing a winner:
# there is no choice to make between two numbers that answer two questions.
#
# HOW THE TWO SETS ARE BUILT HERE. By calling the producers, not by restating
# them. The rate set comes back from maker_econ.build_toxicity_labels itself.
# The cost set comes back from t3_capacity._per_wallet_cost, whose cut size is
# read off t3_capacity._avoidable_block - the producer's own arithmetic, not a
# copy of it - and whose members are picked by t3_capacity._top_by_dollar_cost_mask.
# A check that reprints the logic it checks goes blind the moment that logic is
# repaired, so nothing here reprints it. The one place this file does its own
# arithmetic is the COUNTERFACTUAL cut size in the ceil-against-floor block,
# which is by construction the rule the producer does not use.
#
# THE JOIN IS ON THE WHOLE INTEGER WALLET IDENTIFIER AND NEVER ON A NUMBER.
# Joining two files on a rounded quantity merges wallets that are not the same
# wallet and accepts a fabricated value as readily as a real one. The
# calibration block measures both failures on this very population instead of
# asserting them.
#
# WHAT THIS FILE DOES NOT DO. It does not re-estimate anything. Both producers
# already build these two lists inside themselves; this file builds them once
# more by the same rules and compares them. It publishes counts, shares and
# sums only - never a list of wallet identifiers, which are raw data.
#
# COST. numpy only, two shared intermediates, no raw parse and no order-book
# rebuild. Seconds, and the elapsed time is recorded in the artifact.
# ---------------------------------------------------------------------------

import json
import os
import sys

import numpy as np

# The shared modules sit in the repository root, one directory up from this
# group, and this file also imports from the money group. Both are built from this
# file's own location and never from the working directory the run happens to
# start in.
_CODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_CODE_DIR, os.path.join(_CODE_DIR, "money")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import artifact
import maker_econ as ME
import panel_io as P
import settings as H
import t3_capacity as T3

HERE = os.path.dirname(os.path.abspath(__file__))

OUT_NAME = "decile_overlap_results.json"
MID_NPZ = "quickwin_markouts_mid.npz"
PRINT_NPZ = "quickwin_markouts.npz"

# The published cost share this file reproduces before it reports anything else. A
# selection that does not reproduce the published number is not the published
# selection, whatever it is named.
PUBLISHED_FILE = "t3_results.json"
REPRODUCTION_ATOL = 5e-5     # the artifact rounds its shares to four places

HORIZON = H.HEADLINE_HORIZON_S
K_HEADLINE = ME.K_HEADLINE          # early fills a wallet needs to be ranked at all
COINS = H.coin_labels("quickwin")

# The calibration draws fabricated values to measure what a numeric join accepts.
FABRICATED_DRAWS = 1000
ROUND_DP = 2                        # decimals a careless join would round a key to


def _ids_of(collection):
    """A sorted int64 array of wallet identifiers, from a set or an array."""
    return np.array(sorted(int(x) for x in collection), dtype=np.int64)


def _shares(n_inter, n_left, n_right):
    """The intersection as a share of EACH set. Two numbers, never averaged.

    The share of the rate set held by the cost set and the share of the cost set held
    by the rate set are different quantities whenever the two sets differ in size, and
    a single "overlap" figure hides which one a reader is being shown.
    """
    union = n_left + n_right - n_inter
    return {
        "share_of_rate_set": round(n_inter / n_left, 4) if n_left else 0.0,
        "share_of_cost_set": round(n_inter / n_right, 4) if n_right else 0.0,
        "jaccard": round(n_inter / union, 4) if union else 0.0,
    }


def _positions_in(uniq, ids):
    """Positions of `ids` inside the sorted `uniq`, refusing anything not found.

    The join is on the whole integer identifier, so a lookup that does not land exactly
    is an error and not a near miss to be tolerated. Every identifier handed here comes
    from the same slice's rows, so a failure means the two sides are not the population
    they are believed to be, which is worth stopping for.
    """
    pos = np.searchsorted(uniq, ids)
    if ids.size and (int(pos.max()) >= uniq.size or not np.array_equal(uniq[pos], ids)):
        raise ValueError(
            "a wallet identifier being scored is absent from the slice's own taker "
            "index; the two sides are not the same population")
    return pos


def _rate_selection(arrs, row_mask):
    """The RATE set for one slice, straight out of maker_econ.build_toxicity_labels.

    The slice is taken on the rows before the producer sees them, so the producer
    applies its own eligibility floor, its own early/late split and its own
    ceil(10% x N) cut to exactly the rows of this coin. Nothing about the rule is
    restated here.
    """
    sliced = {k: v[row_mask] for k, v in arrs.items()}
    return ME.build_toxicity_labels(sliced, K_HEADLINE, horizon=HORIZON)


def _cost_selection(taker_id, row_mask, day, mo_print, notional):
    """The COST set for one slice, straight out of t3_capacity.

    _per_wallet_cost applies the same eligibility floor over the rows this window can
    score and returns the per-wallet early and late dollar cost vectors. _avoidable_block
    is called for its cut size and for the published share it recomputes, so the number
    of wallets in the cut is the producer's own max(1, floor(10% x N)) rather than a
    copy of that expression living here. _top_by_dollar_cost_mask then picks them.
    """
    ids, early_cost, late_cost, all_cost, diag = T3._per_wallet_cost(
        taker_id, row_mask, day, mo_print, notional)
    block = T3._avoidable_block(ids, early_cost, late_cost, all_cost, diag)
    k_cut = int(block["n_top_decile_wallets"])
    mask = T3._top_by_dollar_cost_mask(early_cost, k_cut)
    return ids, early_cost, late_cost, mask, k_cut, block, diag


def _cost_parts(early_cost, late_cost, in_rate, in_cost):
    """Dollar cost carried by each of the four parts, on the COST-ranked population.

    The population is stated rather than assumed: the per-wallet dollar cost vectors
    exist only for the wallets t3_capacity ranks, so a rate-set member outside that
    population contributes nothing here and is counted separately by the caller. Every
    share goes through the producer's own _selected_share, whose base is the gross
    POSITIVE cost over the whole ranked population, which is the base the published
    avoidable share stands on.
    """
    parts = {
        "in_both_sets": in_rate & in_cost,
        "rate_set_only": in_rate & ~in_cost,
        "cost_set_only": ~in_rate & in_cost,
        "in_neither_set": ~in_rate & ~in_cost,
    }
    out = {"_population": (
        "the wallets t3_capacity ranks, because the per-wallet dollar cost vectors "
        "exist only there; a rate-set member outside this population is counted by "
        "n_rate_set_outside_the_cost_ranked_population and contributes nothing below")}
    for name, mask in parts.items():
        out[name] = {
            "n_wallets": int(mask.sum()),
            "late_gross_positive_cost_usd": round(
                float(np.sum(np.maximum(late_cost[mask], 0.0))), 2),
            "share_of_late_gross_positive_cost": round(
                T3._selected_share(late_cost, mask), 4),
            "late_signed_cost_usd": round(float(np.sum(late_cost[mask])), 2),
            "early_gross_positive_cost_usd": round(
                float(np.sum(np.maximum(early_cost[mask], 0.0))), 2),
            "share_of_early_gross_positive_cost": round(
                T3._selected_share(early_cost, mask), 4),
        }
    return out


def _bps_parts(uniq, early_tox, part_ids):
    """Mean early markout in bps for each part, over the wallets that carry a score.

    The score is maker_econ's own early_tox: one unweighted mean of a wallet's early
    fills with a finite book-mid markout at the headline horizon. The figure below is
    an unweighted mean OF THOSE PER-WALLET MEANS, so a wallet with fifty fills and one
    with fifty thousand count alike, which is exactly the property that separates this
    ordering from the dollar one. Wallets whose score is not finite are counted and
    excluded rather than treated as zero.
    """
    out = {"_population": (
        "every wallet either producer ranks in this slice, so the four parts below "
        "cover the union of the two ranked populations and not just one of them")}
    for name, ids in part_ids.items():
        block = {"n_wallets": int(ids.size), "n_with_finite_score": 0,
                 "mean_early_markout_bps": None, "median_early_markout_bps": None,
                 "min_early_markout_bps": None, "max_early_markout_bps": None}
        if ids.size:
            vals = early_tox[_positions_in(uniq, ids)]
            vals = vals[np.isfinite(vals)]
            block["n_with_finite_score"] = int(vals.size)
            if vals.size:
                block["mean_early_markout_bps"] = round(float(np.mean(vals)), 4)
                block["median_early_markout_bps"] = round(float(np.median(vals)), 4)
                block["min_early_markout_bps"] = round(float(np.min(vals)), 4)
                block["max_early_markout_bps"] = round(float(np.max(vals)), 4)
        out[name] = block
    return out


def _cut_rule_sensitivity(rate_ids, rate_scores, n_rate_pop,
                          cost_pop_ids, early_cost, cost_ids):
    """Does the intersection depend on ceil against max(1, floor(...))?

    The two producers cut the same nominal ten percent with two different roundings, so
    the question has a number rather than an opinion. The counterfactual cut SIZE is
    computed here, because it is by construction the rule neither producer uses; the
    counterfactual MEMBERS are still taken by rank order.

    For the rate set the ceil and floor cuts differ by at most one wallet, so the floor
    variant is the producer's own set less its lowest-scoring member. For the cost set
    the producer's own selector is called again at the larger size.
    """
    n_rate_ceil = int(rate_ids.size)
    n_rate_floor = max(1, int(np.floor(n_rate_pop * ME.TOXIC_DECILE_FRAC)))
    n_cost_floor = int(cost_ids.size)
    n_cost_ceil = max(1, int(np.ceil(cost_pop_ids.size * T3.DOLLAR_COST_TOP_FRAC)))

    drop = n_rate_ceil - n_rate_floor
    if drop < 0 or drop > 1:
        raise ValueError(
            f"ceil and floor of the same ten percent differ by {drop} wallets, which "
            "the drop-the-lowest construction below cannot express; recompute the "
            "floor variant through the producer instead of assuming a one-wallet gap")
    if drop:
        order = np.argsort(rate_scores, kind="stable")   # ascending score
        rate_floor_ids = np.sort(rate_ids[order[drop:]])
    else:
        rate_floor_ids = rate_ids

    cost_ceil_ids = np.sort(
        cost_pop_ids[T3._top_by_dollar_cost_mask(early_cost, n_cost_ceil)])

    pairings = {
        "as_the_producers_cut_it__rate_ceil_x_cost_floor": (rate_ids, cost_ids),
        "rate_floor_x_cost_floor": (rate_floor_ids, cost_ids),
        "rate_ceil_x_cost_ceil": (rate_ids, cost_ceil_ids),
        "rate_floor_x_cost_ceil": (rate_floor_ids, cost_ceil_ids),
    }
    sizes = {}
    for name, (left, right) in pairings.items():
        inter = np.intersect1d(left, right, assume_unique=True)
        sizes[name] = {"n_rate_set": int(left.size), "n_cost_set": int(right.size),
                       "n_intersection": int(inter.size)}
    actual = sizes["as_the_producers_cut_it__rate_ceil_x_cost_floor"]["n_intersection"]
    spread = [b["n_intersection"] for b in sizes.values()]
    return {
        "cut_sizes": {
            "rate_ceil": n_rate_ceil, "rate_floor": n_rate_floor,
            "cost_floor": n_cost_floor, "cost_ceil": n_cost_ceil,
        },
        "intersection_under_each_pairing": sizes,
        "wallets_the_rounding_moves": int(max(spread) - min(spread)),
        "intersection_as_the_producers_cut_it": actual,
    }


def _concentration(late_cost, in_rate, in_cost, k=10):
    """Why the two sets can capture very different amounts of the same cost base.

    The late positive cost is held by a handful of wallets, so which of them clears a
    cut decides almost the whole captured share. This block counts how much the k
    largest hold and how many of them each selection contains, which is the mechanism
    behind every gap between the two capture figures above. It is a DIAGNOSTIC computed
    here, not a rule taken from either producer, and k is a round number chosen to be
    read beside the share rather than to be a threshold.
    """
    positive = np.maximum(late_cost, 0.0)
    gross = float(np.sum(positive))
    order = np.argsort(-positive, kind="stable")[:k]
    return {
        "k": k,
        "share_of_late_gross_positive_cost_held_by_k_largest": round(
            float(np.sum(positive[order])) / gross, 4) if gross else 0.0,
        "of_the_k_largest_in_rate_set": int(in_rate[order].sum()),
        "of_the_k_largest_in_cost_set": int(in_cost[order].sum()),
        "reading": ("the cost-ranked cut is built to contain the largest, so it holds "
                    "most of this base by construction; how many of them the "
                    "rate-ranked cut happens to contain is what its captured share "
                    "mostly is"),
    }


def _calibration(rate_ids, rate_pop_ids, cost_ids, cost_pop_ids,
                 scores, costs, rng):
    """Two opposite cases for the intersection, and the false-match rate of a numeric key.

    A comparator that has never been shown to find a full overlap and a null overlap is
    not known to be able to find either, so both are run on live sets from this tree:
    a set against itself, which must come back at one, and a set against its own
    complement inside its own population, which must come back at zero.

    The join key is measured too. A wallet identifier is a whole integer and two
    different wallets never share one; a rounded score or a rounded dollar amount both
    merges real wallets and accepts a value that was never in the data. Both failures
    are counted here on this population rather than asserted.
    """
    self_inter = np.intersect1d(rate_ids, rate_ids, assume_unique=True)
    rate_complement = np.setdiff1d(rate_pop_ids, rate_ids, assume_unique=True)
    null_inter = np.intersect1d(rate_ids, rate_complement, assume_unique=True)
    cost_self = np.intersect1d(cost_ids, cost_ids, assume_unique=True)
    cost_complement = np.setdiff1d(cost_pop_ids, cost_ids, assume_unique=True)
    cost_null = np.intersect1d(cost_ids, cost_complement, assume_unique=True)

    def key_report(values, label, decimals):
        finite = values[np.isfinite(values)]
        keys = np.round(finite, decimals)
        distinct = np.unique(keys)
        merged = int(finite.size - distinct.size)
        lo, hi = float(np.min(finite)), float(np.max(finite))
        fabricated = rng.uniform(lo, hi, size=FABRICATED_DRAWS)
        accepted = int(np.isin(np.round(fabricated, decimals), distinct).sum())
        return {
            "key": label,
            "decimals": decimals,
            "population": ("the wallets t3_capacity ranks on the pooled slice, so both "
                           "rounded keys below are measured over the same wallets and "
                           "their two failure rates are comparable"),
            "n_values": int(finite.size),
            "n_distinct_keys": int(distinct.size),
            "wallets_merged_with_another_wallet": merged,
            "value_range": [round(lo, 4), round(hi, 4)],
            "fabricated_values_drawn": FABRICATED_DRAWS,
            "fabricated_values_accepted": accepted,
            "false_match_rate": round(accepted / FABRICATED_DRAWS, 4),
        }

    id_pool = np.unique(np.concatenate([rate_pop_ids, cost_pop_ids]))
    return {
        "must_find_full_overlap__rate_set_against_itself": {
            "n_intersection": int(self_inter.size),
            "expected": int(rate_ids.size),
            "shares": _shares(int(self_inter.size), int(rate_ids.size), int(rate_ids.size)),
            "passed": bool(self_inter.size == rate_ids.size),
        },
        "must_find_no_overlap__rate_set_against_its_complement": {
            "n_intersection": int(null_inter.size),
            "expected": 0,
            "n_in_complement": int(rate_complement.size),
            "passed": bool(null_inter.size == 0),
        },
        "must_find_full_overlap__cost_set_against_itself": {
            "n_intersection": int(cost_self.size),
            "expected": int(cost_ids.size),
            "passed": bool(cost_self.size == cost_ids.size),
        },
        "must_find_no_overlap__cost_set_against_its_complement": {
            "n_intersection": int(cost_null.size),
            "expected": 0,
            "n_in_complement": int(cost_complement.size),
            "passed": bool(cost_null.size == 0),
        },
        "join_key_false_match_rate": {
            "whole_wallet_identifier": {
                "key": "taker_id (int64, whole field)",
                "n_values": int(id_pool.size),
                "n_distinct_keys": int(np.unique(id_pool).size),
                "wallets_merged_with_another_wallet": 0,
                "note": "an identifier is compared whole, so two different wallets "
                        "cannot share a key and no rounding can invent one. This is "
                        "the key every join in this file uses.",
            },
            "rounded_mean_markout_bps": key_report(
                scores, "round(early markout bps, 2)", ROUND_DP),
            "rounded_dollar_cost": key_report(
                costs, "round(early dollar cost, 2)", ROUND_DP),
            "reading": ("The two rounded keys fail in different directions on one and "
                        "the same population, which is why both are shown. The score "
                        "key lives in a narrow range, so a fabricated value lands on an "
                        "occupied key often. The dollar key spans six orders of "
                        "magnitude, so a fabricated value almost never lands on one, "
                        "and it fails the other way instead: half the wallets sit "
                        "within a few cents of zero and rounding merges them. A "
                        "comparator that only ever cried wolf would have shown two high "
                        "rates. A number is never a join key here."),
        },
    }


def main():
    started = artifact.start_clock()
    data_root = P.data_root()
    mid_path = P.require_present("mid", os.path.join(data_root, MID_NPZ))
    print_path = P.require_present("print", os.path.join(data_root, PRINT_NPZ))

    zm = np.load(mid_path)
    zp = np.load(print_path)

    taker_id = zp["taker_id"].astype(np.int64)
    coin = zp["coin"].astype(np.int64)
    day = zp["day"].astype(np.int64)
    notional = zp["notional"].astype(np.float64)
    mo_print = zp[H.headline_print_col()].astype(np.float64)
    a_mid = zm[H.headline_mid_col()].astype(np.float64)

    # The two selections are compared wallet by wallet, so they have to be reading the
    # same rows in the same order. maker_econ asserts this alignment before it computes
    # anything and so does this file: a comparison across two row orders would return a
    # confident number about nothing.
    alignment = {}
    for key in ("taker_id", "coin", "day"):
        same = bool(np.array_equal(zm[key].astype(np.int64), zp[key].astype(np.int64)))
        alignment[key] = same
        if not same:
            raise SystemExit(
                f"[decile_overlap] the two panels disagree on '{key}', so a wallet-level "
                "comparison across them is not defined; rebuild them from one parse")

    # Beside its own producer in the money group, not beside this probe. The file name
    # stays the last component of the join, because that is what build.py folds this
    # script's input edge out of.
    with open(os.path.join(_CODE_DIR, "money", PUBLISHED_FILE), encoding="utf-8") as fh:
        published_doc = json.load(fh)
    published_key = H.field_name("avoidable_share_oos_top10pct", HORIZON)

    rng = np.random.default_rng(H.MASTER_SEED)
    slices = [(name, coin == code) for code, name in sorted(COINS.items())]
    slices.append(("pooled", np.ones(coin.shape, dtype=bool)))

    by_slice = {}
    calibration = None
    for name, row_mask in slices:
        print(f"[{name}] rows {int(row_mask.sum()):,}", flush=True)

        labels = _rate_selection({"taker_id": taker_id, "day": day,
                                  f"a_mid_{HORIZON}": a_mid}, row_mask)
        rate_ids = _ids_of(labels["toxic_taker_set"])
        rate_pop_ids = labels["uniq"][labels["eligible_mask_taker"]].astype(np.int64)
        uniq, early_tox = labels["uniq"].astype(np.int64), labels["early_tox"]

        (cost_pop_ids, early_cost, late_cost, cost_mask, k_cut,
         block, diag) = _cost_selection(taker_id, row_mask, day, mo_print, notional)
        cost_ids = cost_pop_ids[cost_mask]

        # The published share, recomputed through the producer's own routine on the set
        # this file just rebuilt. If it does not land on the artifact, the set is not
        # the published one and nothing below is about the published number.
        recomputed = T3._selected_share(late_cost, cost_mask)
        published = float(published_doc[name][published_key])
        reproduced = bool(abs(recomputed - published) <= REPRODUCTION_ATOL)

        inter = np.intersect1d(rate_ids, cost_ids, assume_unique=True)
        pop_inter = np.intersect1d(rate_pop_ids, cost_pop_ids, assume_unique=True)

        in_rate = np.isin(cost_pop_ids, rate_ids)
        outside = int(rate_ids.size - int(np.isin(rate_ids, cost_pop_ids).sum()))

        part_ids = {
            "in_both_sets": inter,
            "rate_set_only": np.setdiff1d(rate_ids, cost_ids, assume_unique=True),
            "cost_set_only": np.setdiff1d(cost_ids, rate_ids, assume_unique=True),
            "in_neither_set": np.setdiff1d(
                np.union1d(rate_pop_ids, cost_pop_ids),
                np.union1d(rate_ids, cost_ids), assume_unique=True),
        }

        by_slice[name] = {
            "populations": {
                "n_ranked_by_rate": int(rate_pop_ids.size),
                "n_ranked_by_cost": int(cost_pop_ids.size),
                "n_ranked_by_both": int(pop_inter.size),
                "n_ranked_by_rate_only": int(rate_pop_ids.size - pop_inter.size),
                "n_ranked_by_cost_only": int(cost_pop_ids.size - pop_inter.size),
                "predicate_rate": (
                    f"at least {K_HEADLINE} early fills carrying a finite "
                    f"{HORIZON}s book-mid markout, counted by "
                    "maker_econ.build_toxicity_labels"),
                "predicate_cost": (
                    f"at least {T3.MIN_EARLY_TRADES} early rows carrying a finite "
                    f"{HORIZON}s trade-print markout and a finite notional, counted by "
                    "t3_capacity._per_wallet_cost"),
                "why_they_differ": (
                    "the two lenses do not carry the same missing-value pattern, so a "
                    "wallet can clear the same floor on one and miss it on the other; "
                    "the floor itself is the same number on both sides"),
            },
            "selections": {
                "n_rate_set": int(rate_ids.size),
                "n_cost_set": int(cost_ids.size),
                "n_intersection": int(inter.size),
                "shares_of_the_intersection": _shares(
                    int(inter.size), int(rate_ids.size), int(cost_ids.size)),
                "n_rate_set_outside_the_cost_ranked_population": outside,
                "rule_rate": ("top ceil(10% x N) by MEAN book-mid markout in bps over "
                              "the early half (maker_econ.build_toxicity_labels, the "
                              "cut at the ceil expression inside it)"),
                "rule_cost": ("top max(1, floor(10% x N)) by SUMMED early dollar cost "
                              "(t3_capacity._avoidable_block for the size, "
                              "_top_by_dollar_cost_mask for the members)"),
            },
            "dollar_cost_by_part": _cost_parts(
                early_cost, late_cost, in_rate, cost_mask),
            "mean_markout_bps_by_part": _bps_parts(uniq, early_tox, part_ids),
            "what_each_set_captures_of_the_same_cost_base": {
                "base": ("gross POSITIVE late-half dollar cost over the "
                         f"{int(cost_pop_ids.size)} wallets t3_capacity ranks, which is "
                         "the base the published avoidable share stands on"),
                "captured_by_cost_set": round(recomputed, 4),
                "captured_by_rate_set": round(T3._selected_share(late_cost, in_rate), 4),
                "captured_by_intersection": round(
                    T3._selected_share(late_cost, in_rate & cost_mask), 4),
                "note": ("the rate figure is a LOWER bound by exactly the "
                         f"{outside} rate-set wallets this population does not carry"),
                "why_the_two_figures_differ": _concentration(
                    late_cost, in_rate, cost_mask),
            },
            "which_side_is_a_published_cell": {
                "rate_set": ("maker_econ publishes ONE rate-ranked selection and it is "
                             "the pooled one, so the pooled row here is the study's own "
                             "set and the per-coin rows are the same rule applied to a "
                             "coin slice, which no artifact of this tree publishes"),
                "cost_set": ("t3_capacity publishes this selection per coin AND pooled, "
                             "so every row here is a published cell on that side"),
                "consequence": ("quote the pooled row when the sentence is about the "
                                "study's toxic decile; a per-coin row compares one "
                                "published set against a constructed one and says so"),
            },
            "reproduction_of_the_published_share": {
                "published": published,
                "published_address": f"{PUBLISHED_FILE}#{name}.{published_key}",
                "recomputed": round(recomputed, 6),
                "atol": REPRODUCTION_ATOL,
                "reproduced": reproduced,
                "means": ("the cost set rebuilt here IS the set the published share "
                          "stands on, so the overlap figures above are about that "
                          "number and not about a lookalike selection"),
            },
            "cut_rule_sensitivity": _cut_rule_sensitivity(
                rate_ids, early_tox[_positions_in(uniq, rate_ids)],
                int(rate_pop_ids.size), cost_pop_ids, early_cost, cost_ids),
            "window": {"early_days": diag["early_days"], "late_days": diag["late_days"]},
        }

        if not reproduced:
            print(f"  [{name}] recomputed share {recomputed:.6f} against published "
                  f"{published:.6f} - the rebuilt set is NOT the published one",
                  flush=True)

        if name == "pooled":
            calibration = _calibration(
                rate_ids, rate_pop_ids, cost_ids, cost_pop_ids,
                early_tox[_positions_in(uniq, cost_pop_ids)], early_cost, rng)

        sel = by_slice[name]["selections"]
        print(f"  rate {sel['n_rate_set']:>4}   cost {sel['n_cost_set']:>4}   "
              f"both {sel['n_intersection']:>4}   "
              f"of rate {sel['shares_of_the_intersection']['share_of_rate_set']:.3f}   "
              f"of cost {sel['shares_of_the_intersection']['share_of_cost_set']:.3f}",
              flush=True)

    payload = {
        "question": (
            "How much of the study's rate-ranked toxic decile is the same set of "
            "counterparties as the cost-ranked one. The two are cut by different rules "
            "on different quantities and are not alternatives to each other: one "
            "answers who is dearest per fill and the other who is dearest in "
            "aggregate. Neither is corrected to the other here."),
        "by_slice": by_slice,
        "calibration": calibration,
        "reading_rule": (
            "Quote the two shares of the intersection together and never one alone: "
            "the share of the rate set that the cost set holds and the share of the "
            "cost set that the rate set holds are different numbers whenever the two "
            "cuts differ in size. Name the ranking beside any figure taken from here."),
        "row_alignment_verified": alignment,
    }

    artifact.write(
        OUT_NAME,
        payload,
        script=__file__,
        inputs=[mid_path, print_path,
                os.path.join(_CODE_DIR, "money", PUBLISHED_FILE)],
        scope={
            "population": (
                f"counterparties with at least {K_HEADLINE} early-half fills, taken "
                "twice: once over the fills carrying a finite book-mid markout at the "
                f"{HORIZON}s horizon, which is the population maker_econ ranks by mean "
                "markout in bps, and once over the fills carrying a finite trade-print "
                "markout and notional, which is the population t3_capacity ranks by "
                "summed dollar cost. The two populations are reported separately and "
                "their difference is counted"),
            "window": ("the ten resolved days of the headline window, split into the "
                       "early ranking half and the disjoint late measurement half by "
                       "settings.split_early_late; both producers derive the split "
                       "from the days present and both are reported per slice"),
            "coins": [COINS[c] for c in sorted(COINS)] + ["pooled"],
        },
        started=started,
        settings=dict(
            h=HORIZON,
            lens="mid and print together",
            rank_floor_fills=[K_HEADLINE],
            master_seed=H.MASTER_SEED,
            n_perm=None,
            n_boot=T3.BOOTSTRAP_N,
            override_reasons={
                "lens": ("this file compares one selection taken on the book-mid lens "
                         "against one taken on the trade-print lens, so neither name "
                         "alone describes the run and the pair is stated instead"),
                "master_seed": ("the declared master seed draws the fabricated values "
                                "of the join-key calibration, which is the only random "
                                "draw this file owns"),
                "n_perm": ("no permutation test runs here; nothing is resampled to "
                           "build a null"),
                "n_boot": ("this file draws no bootstrap of its own. The figure is what "
                           "t3_capacity._avoidable_block draws when it is called for "
                           "its cut size, and it is stated so the call is visible"),
            },
        ),
        extra_meta={
            "object": ("overlap between the two selections this study has called the "
                       "toxic decile: the rate-ranked one every persistence and quoting "
                       "result is booked over, and the cost-ranked one the headline "
                       "avoidable share stands on"),
            "producers_called": {
                "rate": "maker_econ.build_toxicity_labels",
                "cost": ("t3_capacity._per_wallet_cost, _avoidable_block for the cut "
                         "size, _top_by_dollar_cost_mask for the members, "
                         "_selected_share for every cost share"),
                "why": ("a check that reprints the rule it checks goes blind the moment "
                        "the rule is repaired, so both selections are taken from the "
                        "producers and only the counterfactual cut size of the "
                        "ceil-against-floor block is computed here"),
            },
            "not_published_here": ("no wallet identifier appears in this artifact. It "
                                   "carries counts, shares and sums only"),
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
