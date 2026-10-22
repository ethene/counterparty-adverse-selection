"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-20
References: Hyperliquid market-data L2 book S3 archive (s3://hyperliquid-archive/market_data);
           Zenodo 18184441 (Albers et al. 2026); local parser i4_l2_mid.py.

chk_book_orientation.py - GROUND-TRUTH the L2 book orientation our pipeline assumes.

ASSUMPTION UNDER TEST (NEVER trusted, only tested here):
    In each raw l2Book snapshot, data["levels"][0] are BIDS and data["levels"][1]
    are ASKS (positional, never validated upstream). Our derived series therefore
    set spread = ask_px - bid_px, which should be STRICTLY POSITIVE if the
    orientation is correct. If [0]/[1] were swapped (or the book were ever crossed),
    spread would go <= 0.

This script does NOT bake the convention in as ground truth. It TESTS it two ways
and emits a verdict per the shared check contract.

Leg (a) - DERIVED SERIES (CIRCULAR, by construction):
    Load mid_series_BTC.npz / mid_series_ETH.npz. These store spread = ask - bid as
    computed by the pipeline, where ask = levels[1][0].px and bid = levels[0][0].px.
    Because spread is DEFINED as levels[1].px - levels[0].px, "spread > 0" only
    restates levels[1][0] > levels[0][0]; it CANNOT detect a levels[0]/[1] swap. It
    confirms ask > bid only GIVEN the assumed orientation, so this leg is circular
    and never on its own grounds the verdict. A scale sanity check also runs: mid must
    sit inside the [min,max] envelope of its own series and be in a plausible order of
    magnitude (no decimal/scale error), and spread must be a small fraction of mid.

Leg (b) - RAW LADDER MONOTONICITY (the NON-CIRCULAR test; skipped under --smoke):
    Re-parse the raw L2 snapshots the same way i4_l2_mid.py does - obj["raw"]["data"],
    bids = levels[0], asks = levels[1], px via float() - but DO NOT compare bid to ask
    via a derived spread. Instead test the ladder SHAPE itself, which is what actually
    distinguishes the two sides:
        levels[0] (bids) prices STRICTLY DESCENDING away from top of book,
        levels[1] (asks) prices STRICTLY ASCENDING away from top of book,
        best-bid (levels[0][0]) < best-ask (levels[1][0]), none crossed/equal.
    A levels[0]/[1] swap would flip the monotonicity (the "bid" ladder would ascend),
    which a spread sign cannot see. Sampled across ALL cached December days, both
    coins, multiple hours per day. Reports counts: inverted (best-bid>best-ask),
    crossed-or-equal (best-bid>=best-ask), bids-not-descending, asks-not-ascending -
    all expected 0. This leg, and only this leg, can ground the verdict.

Verdict:
    confirmed  -> the non-circular monotonicity raw leg RAN and passed (0 inverted,
                  0 crossed/equal, 0 bids-not-descending, 0 asks-not-ascending), and
                  the derived legs agree.
    refuted    -> any SYSTEMATIC raw monotonicity violation (swapped/crossed ladders).
    uncertain  -> the raw leg did not run (e.g. --smoke leaves only the circular
                  derived leg), a leg unavailable, or a tiny inconsistent stray.

Run:
    uv run --no-project --with-requirements ../requirements.txt python3 chk_book_orientation.py            # full (raw leg by default)
    uv run --no-project --with-requirements ../requirements.txt python3 chk_book_orientation.py --smoke    # derived (circular) legs only
Writes chk_book_orientation_results.json next to this script.
"""

import json
import os
import subprocess
import sys

import numpy as np

# --- paths ----------------------------------------------------------------
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if THIS_DIR not in sys.path:
    sys.path.insert(0, THIS_DIR)
from evidence import report_contract                                     # noqa: E402

CODE_DIR = os.path.abspath(os.path.join(THIS_DIR, os.pardir))            # the repository root
if CODE_DIR not in sys.path:
    sys.path.insert(0, CODE_DIR)
import artifact                                                          # noqa: E402
import settings as H                                                     # noqa: E402

DATA_DIR = os.path.abspath(os.path.join(CODE_DIR, os.pardir, "02_data"))  # .../02_data
L2_CACHE = os.path.join(DATA_DIR, "l2_cache")
OUT_JSON = os.path.join(THIS_DIR, "chk_book_orientation_results.json")

# The coins this check reads, asked for by STORE rather than typed. Both legs walk the
# same store: leg (a) opens mid_series_{COIN}.npz, which is what i4_l2_mid.py derives
# from the L2 cache, and leg (b) opens the cache itself. That store carries no integer
# codes -- its leaves are named BTC.lz4 and ETH.lz4 -- so the question this file asks is
# "which symbols does the l2 cache carry", and settings.coin_symbols is the accessor for
# exactly that question. Proved equal before the move: the literal here was
# ["BTC", "ETH"] and coin_symbols("l2_cache") returns ("BTC", "ETH").
COINS = list(H.coin_symbols("l2_cache"))
# A swept-for-anomaly fraction this small (< 1e-4) is treated as numerically
# negligible, not a systematic inversion.
TINY_FRAC = 1e-4
# Plausible order-of-magnitude envelopes for a sanity ceiling on the mid series.
# These are wide guards against a decimal/scale mis-read, NOT a precise price check.
PRICE_BAND = {"BTC": (1.0e3, 1.0e7), "ETH": (1.0e2, 1.0e6)}
# Spread should be a small fraction of mid for a liquid top-of-book; a huge ratio
# would signal swapped/garbage levels rather than a real one-tick spread.
MAX_SPREAD_FRAC_OF_MID = 0.05  # 5% ceiling on median spread/mid; generous.

# Raw monotonicity sampling: span ALL cached days, both coins, several hours/day.
# These hours mirror the adversarial audit (early / mid / late of the daily file).
RAW_SAMPLE_HOURS = [0, 11, 23]
# Snapshots read per (day, coin, hour) cell; the audit drew ~1800 across 20 cells.
RAW_SNAPS_PER_CELL = 90


# --------------------------------------------------------------------------
# Leg (a): derived mid_series_{COIN}.npz
# --------------------------------------------------------------------------
def check_derived_spread():
    """spread = ask - bid in the pipeline output; spread>0 confirms bid<ask."""
    per_coin = {}
    total_rows = 0
    total_nonpos = 0
    all_min_spread = []
    missing = []

    for coin in COINS:
        path = os.path.join(CODE_DIR, f"mid_series_{coin}.npz")
        if not os.path.exists(path):
            missing.append(coin)
            continue
        with np.load(path, allow_pickle=False) as z:
            spread = np.asarray(z["spread"], dtype=np.float64)
            mid = np.asarray(z["mid"], dtype=np.float64)
        n = int(spread.shape[0])
        nonpos = int(np.count_nonzero(spread <= 0.0))
        min_spread = float(np.min(spread)) if n else float("nan")
        per_coin[coin] = {
            "rows": n,
            "spread_le0_count": nonpos,
            "spread_le0_frac": (nonpos / n) if n else None,
            "min_spread": min_spread,
            "median_spread": float(np.median(spread)) if n else None,
            "mid_min": float(np.min(mid)) if n else None,
            "mid_max": float(np.max(mid)) if n else None,
            "median_mid": float(np.median(mid)) if n else None,
        }
        total_rows += n
        total_nonpos += nonpos
        if n:
            all_min_spread.append(min_spread)

    overall_frac = (total_nonpos / total_rows) if total_rows else None
    observed = {
        "per_coin": per_coin,
        "total_rows": total_rows,
        "total_spread_le0": total_nonpos,
        "total_spread_le0_frac": overall_frac,
        "global_min_spread": (min(all_min_spread) if all_min_spread else None),
        "missing_coins": missing,
    }

    # NOTE: this leg is CIRCULAR. spread is DEFINED in the pipeline as
    # levels[1][0].px - levels[0][0].px, so "spread > 0" only restates
    # levels[1][0] > levels[0][0]; it cannot detect a levels[0]/[1] swap. It
    # confirms ask > bid GIVEN the assumed orientation, nothing more. It therefore
    # never reads "confirmed": at best it is "uncertain" (orientation not provable
    # from a derived spread), and only goes "refuted" on a systematic sign anomaly.
    circular_tag = (" [CIRCULAR: spread := levels[1].px - levels[0].px, so this "
                    "only restates levels[1]>levels[0] GIVEN the assumed "
                    "orientation - it cannot catch a [0]/[1] swap.]")
    if total_rows == 0:
        verdict = "uncertain"
        note = "no mid_series_*.npz rows loaded; cannot test derived spread."
    elif overall_frac == 0.0:
        verdict = "uncertain"
        note = ("spread = ask - bid is strictly positive for ALL derived rows "
                "across {0} coins ({1} rows) -> ask > bid GIVEN the assumed "
                "orientation.").format(len(per_coin), total_rows) + circular_tag
    elif overall_frac is not None and overall_frac < TINY_FRAC:
        verdict = "uncertain"
        note = ("spread <= 0 on a numerically negligible {0:.2e} of rows; "
                "consistent with ask > bid given the assumed orientation.").format(
                    overall_frac) + circular_tag
    elif overall_frac is not None and overall_frac < 0.05:
        verdict = "uncertain"
        note = ("spread <= 0 on {0:.3%} of rows - small but above the negligible "
                "floor; inspect those snapshots.").format(overall_frac) + circular_tag
    else:
        verdict = "refuted"
        note = ("spread <= 0 on {0:.3%} of rows - SYSTEMATIC; levels[0]/[1] may be "
                "swapped or the book is routinely crossed.").format(overall_frac)

    return {
        "name": "derived_spread_positive",
        "assumption": "mid_series spread = ask_px - bid_px > 0 (i.e. levels[0]=bids, "
                      "levels[1]=asks gives bid < ask).",
        "method": "Loaded mid_series_{BTC,ETH}.npz; counted rows with spread<=0 and "
                  "the minimum/median spread per coin and overall. CIRCULAR by "
                  "construction (spread := levels[1].px - levels[0].px): proves only "
                  "ask>bid GIVEN the assumed orientation, never grounds the verdict.",
        "circular": True,
        "observed": observed,
        "verdict": verdict,
        "note": note,
    }, missing


def check_scale_sanity():
    """Guard against a decimal / scale mis-read in the mid series."""
    per_coin = {}
    bad = []
    any_loaded = False

    for coin in COINS:
        path = os.path.join(CODE_DIR, f"mid_series_{coin}.npz")
        if not os.path.exists(path):
            continue
        with np.load(path, allow_pickle=False) as z:
            mid = np.asarray(z["mid"], dtype=np.float64)
            spread = np.asarray(z["spread"], dtype=np.float64)
        if mid.shape[0] == 0:
            continue
        any_loaded = True
        lo, hi = PRICE_BAND.get(coin, (0.0, np.inf))
        med_mid = float(np.median(mid))
        mn, mx = float(np.min(mid)), float(np.max(mid))
        in_band = bool(lo <= med_mid <= hi)
        # mid must lie within its own [min,max] envelope (trivially true, but flags
        # NaN/inf contamination).
        finite = bool(np.all(np.isfinite(mid)))
        med_spread = float(np.median(spread))
        spread_ratio = (med_spread / med_mid) if med_mid > 0 else float("inf")
        ratio_ok = bool(0.0 <= spread_ratio <= MAX_SPREAD_FRAC_OF_MID)
        per_coin[coin] = {
            "median_mid": med_mid,
            "mid_min": mn,
            "mid_max": mx,
            "price_band": [lo, hi],
            "median_in_band": in_band,
            "all_finite": finite,
            "median_spread": med_spread,
            "median_spread_frac_of_mid": spread_ratio,
            "spread_ratio_ok": ratio_ok,
        }
        if not (in_band and finite and ratio_ok):
            bad.append(coin)

    if not any_loaded:
        verdict = "uncertain"
        note = "no mid series available for the scale sanity check."
    elif not bad:
        verdict = "confirmed"
        note = ("mid sits in a plausible order of magnitude per coin, is all-finite, "
                "and median spread is a small fraction of mid (no decimal/scale error).")
    else:
        verdict = "refuted"
        note = "scale/finiteness/spread-ratio anomaly for coins: {0}.".format(bad)

    return {
        "name": "mid_scale_sanity",
        "assumption": "mid is a plausible price (no decimal/scale mis-read) and spread "
                      "is a small fraction of mid.",
        "method": "Per coin: median mid in a wide price band, all values finite, and "
                  "median spread/mid <= {0}.".format(MAX_SPREAD_FRAC_OF_MID),
        "observed": {"per_coin": per_coin, "anomalous_coins": bad},
        "verdict": verdict,
        "note": note,
    }


# --------------------------------------------------------------------------
# Leg (b): raw re-parse, mirroring i4_l2_mid.py
# --------------------------------------------------------------------------
def _decompress(path):
    """Mirror i4_l2_mid.decompress: lz4 CLI -> unlz4 -> python lz4 module."""
    for cmd in (["lz4", "-dc", path], ["unlz4", "-c", path]):
        try:
            proc = subprocess.run(cmd, check=True, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE)
            return proc.stdout
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
    try:
        import lz4.frame as lz4f  # type: ignore

        with open(path, "rb") as fh:
            return lz4f.decompress(fh.read())
    except Exception as exc:  # noqa: BLE001
        print("  [warn] lz4 decode failed for {0}: {1}".format(path, exc), file=sys.stderr)
        return None


def _iter_l2_cells():
    """Yield (day, coin, hour, path) over ALL cached December days, both coins,
    and the sampled hours - the cells the monotonicity leg walks. Local cache only;
    no S3. Missing/empty files are skipped."""
    if not os.path.isdir(L2_CACHE):
        return
    days = sorted(d for d in os.listdir(L2_CACHE)
                  if os.path.isdir(os.path.join(L2_CACHE, d)))
    for day in days:
        for coin in COINS:
            for hour in RAW_SAMPLE_HOURS:
                path = os.path.join(L2_CACHE, day, str(hour), "l2Book",
                                    "{0}.lz4".format(coin))
                if os.path.exists(path) and os.path.getsize(path) > 0:
                    yield day, coin, hour, path


def _ladder_descending(levels):
    """True if the price ladder is STRICTLY descending top->down (bid side shape)."""
    prev = None
    for lvl in levels:
        px = float(lvl["px"])
        if prev is not None and not (px < prev):
            return False
        prev = px
    return True


def _ladder_ascending(levels):
    """True if the price ladder is STRICTLY ascending top->down (ask side shape)."""
    prev = None
    for lvl in levels:
        px = float(lvl["px"])
        if prev is not None and not (px > prev):
            return False
        prev = px
    return True


def check_raw_monotonicity():
    """NON-CIRCULAR orientation test: re-parse raw L2 snapshots and verify the LADDER
    SHAPE, not a derived spread sign.

    Parsing mirrors i4_l2_mid.parse_file exactly: obj['raw']['data'], bids=levels[0],
    asks=levels[1], px via float(). But instead of comparing bid to ask through the
    pipeline's spread (which is DEFINED as levels[1]-levels[0] and so circular), it
    tests that the levels[0] ladder is strictly DESCENDING (a real bid book) and the
    levels[1] ladder strictly ASCENDING (a real ask book), with best-bid < best-ask
    and none crossed/equal. A levels[0]/[1] swap flips the monotonicity, which the
    spread sign cannot see - this is the only leg that grounds the verdict.

    Walks ALL cached December days, both coins, several hours per day. Local l2_cache
    only; no S3.
    """
    checked = 0
    inverted = 0              # best-bid > best-ask  (clear orientation flip)
    crossed_eq = 0            # best-bid >= best-ask (inverted OR locked book)
    bids_not_desc = 0         # levels[0] ladder not strictly descending
    asks_not_asc = 0          # levels[1] ladder not strictly ascending
    parse_skips = 0
    cells_used = 0
    per_coin = {c: {"checked": 0, "inverted": 0, "crossed_eq": 0,
                    "bids_not_desc": 0, "asks_not_asc": 0} for c in COINS}
    cells_seen = set()
    days_seen = set()
    examples = []            # a few concrete top-of-book pairs for the record

    for day, coin, hour, path in _iter_l2_cells():
        raw = _decompress(path)
        if raw is None:
            continue
        cells_used += 1
        cells_seen.add((day, coin, hour))
        days_seen.add(day)
        from_this_cell = 0
        for line in raw.split(b"\n"):
            if from_this_cell >= RAW_SNAPS_PER_CELL:
                break
            if not line:
                continue
            try:
                obj = json.loads(line)
                data = obj["raw"]["data"]
                levels = data["levels"]
                bids = levels[0]          # ASSUMED bids - shape tested right here
                asks = levels[1]          # ASSUMED asks
                if not bids or not asks:
                    continue
                bb_px = float(bids[0]["px"])
                ba_px = float(asks[0]["px"])
                bid_desc = _ladder_descending(bids)
                ask_asc = _ladder_ascending(asks)
            except (ValueError, KeyError, IndexError, TypeError):
                parse_skips += 1
                continue

            checked += 1
            from_this_cell += 1
            per_coin[coin]["checked"] += 1
            if bb_px > ba_px:
                inverted += 1
                per_coin[coin]["inverted"] += 1
            if bb_px >= ba_px:
                crossed_eq += 1
                per_coin[coin]["crossed_eq"] += 1
            if not bid_desc:
                bids_not_desc += 1
                per_coin[coin]["bids_not_desc"] += 1
            if not ask_asc:
                asks_not_asc += 1
                per_coin[coin]["asks_not_asc"] += 1
            if len(examples) < 6:
                examples.append({"day": day, "coin": coin, "hour": hour,
                                 "best_bid_px": bb_px, "best_ask_px": ba_px,
                                 "bids_descending": bool(bid_desc),
                                 "asks_ascending": bool(ask_asc),
                                 "bid_lt_ask": bool(bb_px < ba_px)})
        del raw

    violations = inverted + crossed_eq + bids_not_desc + asks_not_asc
    inv_frac = (inverted / checked) if checked else None
    observed = {
        "snapshots_checked": checked,
        "inverted_bid_gt_ask": inverted,
        "inverted_frac": inv_frac,
        "crossed_or_equal_bid_ge_ask": crossed_eq,
        "bids_not_descending": bids_not_desc,
        "asks_not_ascending": asks_not_asc,
        "cells_used": cells_used,
        "distinct_cells": len(cells_seen),
        "distinct_days": len(days_seen),
        "sample_hours": list(RAW_SAMPLE_HOURS),
        "parse_skips": parse_skips,
        "per_coin": per_coin,
        "examples": examples,
    }

    if checked == 0:
        verdict = "uncertain"
        note = ("no raw snapshots parsed from the local l2_cache (empty or "
                "undecodable); the non-circular leg could not run.")
    elif violations == 0:
        verdict = "confirmed"
        note = ("ladder monotonicity holds on ALL {0} raw snapshots across {1} "
                "(day,coin,hour) cells / {2} days: levels[0] strictly descending "
                "(bids), levels[1] strictly ascending (asks), best-bid < best-ask, "
                "none crossed/equal (0 inverted, 0 crossed/equal, 0 bids-not-desc, "
                "0 asks-not-asc) -> levels[0]=bids, levels[1]=asks is GROUND-TRUTHED "
                "non-circularly.").format(checked, len(cells_seen), len(days_seen))
    elif inv_frac is not None and violations / checked < TINY_FRAC:
        verdict = "uncertain"
        note = ("a stray {0} monotonicity violation(s) out of {1} (inverted {2}, "
                "crossed/equal {3}, bids-not-desc {4}, asks-not-asc {5}); not "
                "systematic - likely a momentary crossed/locked book, but flag "
                "it.").format(violations, checked, inverted, crossed_eq,
                              bids_not_desc, asks_not_asc)
    else:
        verdict = "refuted"
        note = ("SYSTEMATIC ladder-shape violation on {0:.3%} of raw snapshots "
                "(inverted {1}, crossed/equal {2}, bids-not-desc {3}, asks-not-asc "
                "{4}) - levels[0]/[1] are NOT bids/asks as assumed.").format(
                    violations / checked, inverted, crossed_eq, bids_not_desc,
                    asks_not_asc)

    return {
        "name": "raw_ladder_monotonicity",
        "assumption": "data['levels'][0]=bids (strictly descending ladder) and "
                      "[1]=asks (strictly ascending ladder), with best-bid<best-ask "
                      "and no crossed/equal book.",
        "method": ("Mirrored i4_l2_mid parsing (levels[0]=bids, levels[1]=asks, px via "
                   "float) on raw l2_cache snapshots across ALL cached days, both "
                   "coins, hours {0}, up to {1}/cell; tested ladder MONOTONICITY "
                   "(non-circular), not a derived spread sign.").format(
                       list(RAW_SAMPLE_HOURS), RAW_SNAPS_PER_CELL),
        "circular": False,
        "observed": observed,
        "verdict": verdict,
        "note": note,
    }


# --------------------------------------------------------------------------
def combine(verdicts):
    """min-tier combine: any refuted -> refuted; else any uncertain -> uncertain."""
    if any(v == "refuted" for v in verdicts):
        return "refuted"
    if any(v == "uncertain" for v in verdicts):
        return "uncertain"
    return "confirmed"


def main():
    started = artifact.start_clock()
    smoke = "--smoke" in sys.argv[1:]

    checks = []
    derived_chk, missing = check_derived_spread()
    checks.append(derived_chk)
    checks.append(check_scale_sanity())

    # The non-circular monotonicity raw leg runs BY DEFAULT (local cache, fast);
    # only --smoke skips it, leaving just the circular derived legs.
    raw_ran_and_passed = False
    if smoke:
        checks.append({
            "name": "raw_ladder_monotonicity",
            "assumption": "data['levels'][0]=bids (descending ladder) and [1]=asks "
                          "(ascending ladder), best-bid<best-ask, none crossed/equal.",
            "method": "SKIPPED under --smoke (raw lz4 ladder-monotonicity re-parse not run).",
            "circular": False,
            "observed": {"skipped": True},
            "verdict": "uncertain",
            "note": ("smoke mode: only the CIRCULAR derived-spread leg ran, which "
                     "cannot prove orientation; run full mode to ground-truth via the "
                     "non-circular raw ladder monotonicity."),
        })
    else:
        raw_chk = check_raw_monotonicity()
        checks.append(raw_chk)
        raw_ran_and_passed = (raw_chk["verdict"] == "confirmed")

    # A CIRCULAR leg can never LIFT the verdict to "confirmed" (its own "uncertain"
    # is structural, not evidence of a problem), but it CAN refute on a systematic
    # sign anomaly. So: any leg "refuted" -> refuted; otherwise combine only the
    # NON-circular legs to decide confirmed/uncertain.
    if any(c["verdict"] == "refuted" for c in checks):
        combined = "refuted"
    else:
        noncirc = [c["verdict"] for c in checks if not c.get("circular", False)]
        combined = combine(noncirc) if noncirc else "uncertain"

    # GATE: "confirmed" requires the non-circular monotonicity raw leg to have RUN
    # and PASSED. Under --smoke the raw leg is skipped, leaving only the circular
    # derived leg, so the orientation reads "uncertain".
    if combined == "refuted":
        overall = "refuted"
    elif raw_ran_and_passed and combined == "confirmed":
        overall = "confirmed"
    else:
        overall = "uncertain"

    result = {
        "check": "chk_book_orientation",
        "mode": "smoke" if smoke else "full",
        "non_circular_raw_leg_ran_and_passed": raw_ran_and_passed,
        "checks": checks,
        "overall_verdict": overall,
    }
    # The scope is stated from what THIS run actually touched, not from the constants
    # above: the derived leg reads whichever mid series are on disk, and the raw leg
    # samples the local l2 cache, so a run on a partial clone covers less than COINS
    # and the artifact has to say so.
    by_name = {c["name"]: c.get("observed", {}) for c in checks}
    derived_seen = by_name.get("derived_spread_positive", {})
    raw_seen = by_name.get("raw_ladder_monotonicity", {})
    artifact.write(
        os.path.basename(OUT_JSON), result,
        script=__file__,
        inputs=[os.path.join(CODE_DIR, f"mid_series_{coin}.npz") for coin in COINS]
               + [L2_CACHE],
        scope={
            "population": f"{derived_seen.get('total_rows', 0):,} mid-series rows on "
                          f"the derived leg and "
                          f"{raw_seen.get('snapshots_checked', 0):,} raw book "
                          f"snapshots on the monotonicity leg",
            "window": f"{raw_seen.get('distinct_days', 0)} days of the local l2 cache "
                      f"sampled at {raw_seen.get('sample_hours', 0)} hours per cell; "
                      f"the mid series carry their own span",
            "coins": [c for c in COINS
                      if c not in derived_seen.get("missing_coins", [])] or COINS,
        },
        settings={"lens": "book"},
        started=started,
        # A run that reached no verdict does not overwrite one that did. `uncertain`
        # here means the non-circular leg could not run at all -- the local book cache
        # is not on this machine, or --smoke skipped it -- and the record it would
        # leave is smaller than the one already on disk: measured on a clean clone,
        # 9,134 bytes became 5,233. `refuted` is a verdict and is written like any
        # other, because a refutation is exactly the news this file must carry.
        answered=(overall != "uncertain"),
        extra_meta={
            # `mode` is deliberately NOT repeated here: the payload already carries it,
            # and a record kept in two places is the defect artifact.py exists to end.
            "not_caught": [
                "the derived leg is circular: it restates levels[1] > levels[0] under "
                "the orientation it assumes, so it can refute but never confirm",
            ],
        },
    )

    # one-line human summary
    parts = []
    for c in checks:
        parts.append("{0}={1}".format(c["name"], c["verdict"]))
    print("[chk_book_orientation] overall={0} ({1}) | {2} | wrote {3}".format(
        overall, "smoke" if smoke else "full", "; ".join(parts),
        os.path.basename(OUT_JSON)))
    # An upside-down book turns every mid-price and every spread in the study into
    # its own mirror image, so a refutation stops the run. The circular derived leg
    # is left off the informational list on purpose: it cannot LIFT the verdict, but
    # it can refute, and a systematic negative spread is worth a red run.
    return report_contract(result, OUT_JSON,
                           inputs={"l2_cache": L2_CACHE,
                                   "mode": "smoke" if smoke else "full"})


if __name__ == "__main__":
    sys.exit(main())
