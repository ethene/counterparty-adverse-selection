#!/usr/bin/env python3
"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-08-05
References:
  - Hayashi, T., Yoshida, N. (2005). "On covariance estimation of non-synchronously
    observed diffusion processes." Bernoulli 11(2), 359-379.
  - Binance public market-data archive, USD-M futures aggTrades.
  - Hyperliquid node-data L4 archive (book snapshots), via mid_series_{COIN}.npz.

HOW FINELY IS THE CROSS-VENUE LEAD KNOWN, AND DO THE TWO CONTRACTS DIFFER?

WHY THIS NODE EXISTS. probes/probe_E_leadlag.py reports that Binance leads Hyperliquid
by 0.75 s, and it reports the same 0.75 on both contracts. Read at two decimal places
that is a coincidence worth suspecting, because 0.75 is not a measurement there: it is
the third node of a lag grid whose step is HY_STEP_S = 0.25 s. A quantity that can only
come out as 0, 0.25, 0.50, 0.75 ... has two contracts landing on one value about as
often as chance allows, and a report that prints "the same 0.75 seconds on both
contracts" is then stating the resolution of the instrument as if it were the agreement
of the market.

So this node asks the question the published scan cannot: where does the peak sit when
the grid is fine enough not to decide the answer, and how far apart are the two
contracts once it is.

WHAT IS HELD EQUAL AND WHAT IS VARIED, stated before the run rather than after it.
Three comparisons are made and each varies exactly one thing.

  GRID.   The published 0.25 s step against a 0.05 s step, everything else identical:
          same window, same venues, same lens, same min-gap thinning, same tick cap,
          same estimator. What moves is only how finely the peak may be located.

  TICK BUDGET.  The published cap of 1,000,000 ticks per series against no cap at all,
          on the fine grid. This is the second limit and, on this window, the binding
          one: probe_E's own _thin_min_gap docstring works it out -- 864,000 seconds
          over 1,000,000 ticks is 0.86 s per tick, three and a half times the step the
          peak is then read on. If the peak moves when the cap is lifted, the published
          number is a property of the budget rather than of the two venues.

  DAY.    The ten days of the window scored one at a time on the fine grid, with the
          tick cap divided by ten so that a day's series carries the same mean tick
          spacing the pooled series had. The spread of the ten peaks is the honest
          uncertainty around the window figure, and it is what any statement about the
          two contracts differing has to be read against.

WHAT THIS NODE DOES NOT DO. It computes no placebo and no vector error-correction
model, so it asserts no significance and replaces no field of probe_E_leadlag. Its
subject is the RESOLUTION of one number that probe already publishes. The estimator
itself is imported from that file rather than re-typed here, so a repair to the scan
cannot leave this measurement quietly describing the old one.

    uv run --no-project --with-requirements requirements.txt python3 -u \
        probes/probe_E_lag_resolution.py
    uv run --no-project --with-requirements requirements.txt python3 -u \
        probes/probe_E_lag_resolution.py --smoke      # one coin, two days
"""
import argparse
import os
import sys
import time

import numpy as np

PROBES = os.path.dirname(os.path.abspath(__file__))
CODE_DIR = os.path.dirname(PROBES)
for _p in (PROBES, CODE_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import artifact                                                        # noqa: E402
# The scan, the thinning and the two loaders are CALLED, never copied. A guard that
# re-types the logic it guards is blind to that logic changing, and this file's whole
# subject is a property of probe_E's scan.
import probe_E_leadlag as E                                            # noqa: E402

OUT_NAME = "probe_E_lag_resolution_results.json"

# The fine grid. 0.05 s is a fifth of the published step, which is enough for the
# published node to remain a node of this grid too -- so the fine scan CONTAINS the
# coarse one and the two cannot disagree by construction about the value at 0.75.
FINE_STEP_S = 0.05
# The scan range. Narrower than probe_E's +/- 5 s on purpose: the published curve is
# single-peaked and has fallen to a fifth of its maximum by +/- 2 s on both coins, so a
# wider range would buy nothing and cost proportionally.
FINE_LO_S, FINE_HI_S = -0.5, 2.5

# Sub-grid refinement. The three points around the discrete maximum are fitted by a
# parabola and its vertex reported beside the grid maximum. It is stated as a separate
# field and never as THE answer, because it assumes a locally quadratic peak, which the
# data do not promise; its job is to say how much of a grid step the discrete maximum
# is throwing away.
REFINE = True

# What "no cap" is spelled as. probe_E's _thin_min_gap compares the kept-tick count
# against this number, so the way to say "do not cap" is a number no thinned series can
# reach rather than None, which that comparison would raise on. The min-gap thinning
# alone bounds a ten-day series at 864,000,000 ms / 250 ms = 3,456,000 ticks, so this is
# two orders above anything the function can be handed.
NO_CAP = 1 << 40


def lag_grid(step_s=FINE_STEP_S, lo=FINE_LO_S, hi=FINE_HI_S):
    """The lags scanned, in seconds. Built once so every configuration shares it."""
    n = int(round((hi - lo) / step_s)) + 1
    return np.round(lo + step_s * np.arange(n), 10)


def scan_curve(t1, px1, t2, px2, lags, label, started):
    """Hayashi-Yoshida cross-correlation at each lag. series1 = HL, series2 = Binance.

    The sign convention is probe_E's: series2 is shifted FORWARD by +lag, so a peak at
    a positive lag means Binance has to be pushed forward to line up with Hyperliquid,
    which is Binance moving first. probe_E stores that positive number as best_lag_s
    and its negation as hl_leads_s; this file reports the positive one and says so in
    the field name.
    """
    lr1 = np.diff(np.log(px1))
    lr2 = np.diff(np.log(px2))
    if lr1.size < 10 or lr2.size < 10:
        return None
    out = []
    for i, lg in enumerate(lags, start=1):
        c = E.hy_corr_at_lag(t1, lr1, t2, lr2, float(lg) * E.MS)
        out.append(float(c) if np.isfinite(c) else np.nan)
        artifact.progress(label, i, len(lags), started)
    return np.asarray(out, dtype=np.float64)


def peak_of(lags, curve):
    """Where the scan puts the lead, on the grid and refined off it.

    The peak is taken on the ABSOLUTE correlation, exactly as probe_E's hy_leadlag
    does, so the two files answer with the same rule rather than with two rules that
    happen to agree on this window.
    """
    if curve is None or not np.isfinite(curve).any():
        return None
    idx = int(np.nanargmax(np.abs(curve)))
    block = {
        "binance_leads_s": float(lags[idx]),
        "peak_corr": float(round(curve[idx], 6)),
        "grid_step_s": float(round(lags[1] - lags[0], 10)),
        "at_grid_edge": bool(idx in (0, len(lags) - 1)),
    }
    if REFINE and 0 < idx < len(lags) - 1:
        y0, y1, y2 = (abs(curve[idx - 1]), abs(curve[idx]), abs(curve[idx + 1]))
        denom = y0 - 2.0 * y1 + y2
        offset = 0.5 * (y0 - y2) / denom if denom != 0 else 0.0
        # A vertex further than half a step from the sampled maximum is not a
        # refinement of it, it is a sign the peak is not locally quadratic. Recorded as
        # null rather than clipped, so a reader is not handed a number the shape does
        # not support.
        block["binance_leads_s_refined"] = (
            float(round(lags[idx] + offset * block["grid_step_s"], 4))
            if abs(offset) <= 0.5 else None)
    else:
        block["binance_leads_s_refined"] = None
    return block


def thinned(t, px, t0, t1, min_gap_ms, max_ticks):
    """The pair of series probe_E would scan, under one stated tick budget."""
    m = (t >= t0) & (t <= t1)
    return E._thin_min_gap(t[m], px[m], min_gap_ms, max_ticks)


def one_configuration(name, hl, bn, t0, t1, min_gap_ms, max_ticks, lags, coin, started):
    """One (thinning, cap) configuration scored on one lag grid."""
    th_hl, ph_hl = thinned(hl[0], hl[1], t0, t1, min_gap_ms, max_ticks)
    th_bn, ph_bn = thinned(bn[0], bn[1], t0, t1, min_gap_ms, max_ticks)
    window_s = (t1 - t0) / E.MS
    label = f"{coin}/{name}"
    print(f"  [{label}] HL {th_hl.size:,} ticks, Binance {th_bn.size:,} ticks, "
          f"window {window_s / 3600:.1f} h, {len(lags)} lags", flush=True)
    curve = scan_curve(th_hl, ph_hl, th_bn, ph_bn, lags, label, started)
    block = peak_of(lags, curve) or {}
    block.update({
        "hy_min_gap_ms": int(min_gap_ms),
        "hy_max_ticks": (None if max_ticks == NO_CAP else int(max_ticks)),
        "n_hl_ticks": int(th_hl.size),
        "n_bn_ticks": int(th_bn.size),
        # The number the resolution argument turns on: how far apart the ticks the peak
        # is read off actually are, against the step it is read at.
        "mean_hl_tick_spacing_s": round(window_s / max(1, th_hl.size), 4),
        "mean_bn_tick_spacing_s": round(window_s / max(1, th_bn.size), 4),
        "curve": [[float(l), (None if not np.isfinite(c) else float(round(c, 6)))]
                  for l, c in zip(lags, curve)] if curve is not None else None,
    })
    return block


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--smoke", action="store_true",
                    help="one coin and two days, to prove the wiring without the cost")
    args = ap.parse_args()

    t_start = artifact.start_clock()
    days = list(E.DEFAULT_DAYS)
    coins = list(E.COINS)
    if args.smoke:
        days, coins = days[:2], coins[:1]

    print(f"[lagres] coins={coins} days={days[0]}..{days[-1]} ({len(days)}d) "
          f"| fine step {FINE_STEP_S}s over [{FINE_LO_S}, {FINE_HI_S}] "
          f"| published step {E.HY_STEP_S}s", flush=True)

    lags_fine = lag_grid()
    lags_pub = lag_grid(E.HY_STEP_S, FINE_LO_S, FINE_HI_S)
    by_coin = {}

    for coin in coins:
        print(f"\n===== {coin} =====", flush=True)
        t_load = time.time()
        hl = E.load_hl_mid(coin)
        bn = E.load_binance_trades(coin, days)
        if hl is None or bn is None:
            by_coin[coin] = {"status": "MISSING_SERIES",
                             "hl_mid_present": hl is not None,
                             "binance_trades_present": bn is not None}
            print(f"  [warn] {coin}: series missing, skipped", flush=True)
            continue
        print(f"  loaded in {time.time() - t_load:.0f} s: "
              f"HL {hl[0].size:,} ticks, Binance {bn[0].size:,} ticks", flush=True)

        t0 = max(int(hl[0].min()), int(bn[0].min()))
        t1 = min(int(hl[0].max()), int(bn[0].max()))
        cfg = {}
        # 1. The published configuration on the published grid. This is the control: it
        #    has to return the 0.75 that is in probe_E_leadlag_results.json, or the two
        #    files are not measuring one quantity and nothing below may be read.
        cfg["published_grid_published_cap"] = one_configuration(
            "pub-grid/pub-cap", hl, bn, t0, t1, E.HY_MIN_GAP_MS, E.MAX_HY_TICKS,
            lags_pub, coin, t_start)
        # 2. The same thing at a fifth of the step. Only the grid moves.
        cfg["fine_grid_published_cap"] = one_configuration(
            "fine-grid/pub-cap", hl, bn, t0, t1, E.HY_MIN_GAP_MS, E.MAX_HY_TICKS,
            lags_fine, coin, t_start)
        # 3. The fine grid with the tick cap lifted. Only the budget moves.
        cfg["fine_grid_no_cap"] = one_configuration(
            "fine-grid/no-cap", hl, bn, t0, t1, E.HY_MIN_GAP_MS, NO_CAP,
            lags_fine, coin, t_start)

        # 4. One day at a time, on the fine grid, with the cap scaled down by the number
        #    of days so a day's ticks sit as far apart as the pooled window's did.
        per_day = {}
        cap_day = max(1, int(E.MAX_HY_TICKS / len(days)))
        for ds in days:
            b = E._day_filter_ms([ds])
            if not b:
                continue
            d0, d1 = b[0]
            d0, d1 = max(d0, t0), min(d1, t1)
            if d1 - d0 < 3600 * E.MS:
                continue
            per_day[ds] = one_configuration(
                f"day {ds}", hl, bn, d0, d1, E.HY_MIN_GAP_MS, cap_day,
                lags_fine, coin, t_start)
        peaks = [v["binance_leads_s"] for v in per_day.values()
                 if v.get("binance_leads_s") is not None]
        by_coin[coin] = {
            "status": "OK",
            "lens": "HLbookmid-vs-BNtrade",
            "overlap_hours": round((t1 - t0) / E.MS / 3600, 2),
            "configurations": cfg,
            "per_day": per_day,
            "per_day_summary": {
                "n_days": len(peaks),
                "median_s": (float(np.median(peaks)) if peaks else None),
                "min_s": (float(np.min(peaks)) if peaks else None),
                "max_s": (float(np.max(peaks)) if peaks else None),
                "sd_s": (float(np.std(peaks, ddof=1)) if len(peaks) > 1 else None),
                "peaks_s": peaks,
            },
        }
        print(f"  [{coin}] published grid {cfg['published_grid_published_cap'].get('binance_leads_s')} s"
              f" | fine grid {cfg['fine_grid_published_cap'].get('binance_leads_s')} s"
              f" | no cap {cfg['fine_grid_no_cap'].get('binance_leads_s')} s"
              f" | per-day median {by_coin[coin]['per_day_summary']['median_s']} s",
              flush=True)

    # The comparison the report's sentence rests on: how far apart the two contracts are
    # once the grid stops deciding, against how far apart the days of one contract are.
    scored = [c for c in coins if by_coin.get(c, {}).get("status") == "OK"]
    between = None
    if len(scored) == 2:
        a, b = scored
        fine = {c: by_coin[c]["configurations"]["fine_grid_published_cap"]
                for c in scored}
        nocap = {c: by_coin[c]["configurations"]["fine_grid_no_cap"] for c in scored}
        spread = [by_coin[c]["per_day_summary"]["sd_s"] for c in scored]
        between = {
            "coins": [a, b],
            "published_step_s": E.HY_STEP_S,
            "fine_step_s": FINE_STEP_S,
            "difference_on_published_grid_s": round(
                by_coin[a]["configurations"]["published_grid_published_cap"]["binance_leads_s"]
                - by_coin[b]["configurations"]["published_grid_published_cap"]["binance_leads_s"], 4),
            "difference_on_fine_grid_s": round(
                fine[a]["binance_leads_s"] - fine[b]["binance_leads_s"], 4),
            "difference_uncapped_s": round(
                nocap[a]["binance_leads_s"] - nocap[b]["binance_leads_s"], 4),
            "within_coin_day_sd_s": [None if s is None else round(s, 4) for s in spread],
        }

    scope = {
        "population": (
            f"Hyperliquid book-mid ticks against Binance USD-M aggTrades, both venues' "
            f"raw asynchronous ticks pre-thinned to a {E.HY_MIN_GAP_MS} ms minimum gap. "
            f"Three tick budgets are scored side by side: the published cap of "
            f"{E.MAX_HY_TICKS:,} ticks per series, no cap, and "
            f"{max(1, int(E.MAX_HY_TICKS / len(days))):,} per series for the one-day "
            f"cuts, which holds a day's mean tick spacing at the pooled window's. "
            f"No placebo and no error-correction model is computed here, so this file "
            f"asserts no significance"),
        "window": (f"{len(days)} UTC days, {days[0]} to {days[-1]}, scored pooled and "
                   f"one day at a time"),
        "coins": coins,
    }
    payload = {
        "question": ("at what resolution is the Binance-over-Hyperliquid lead known, "
                     "and do the two contracts differ once the lag grid is fine enough "
                     "not to decide the answer"),
        "sign_convention": ("binance_leads_s is positive when Binance moves first. It "
                            "is probe_E_leadlag's best_lag_s and the negation of that "
                            "file's hl_leads_s"),
        "published_grid_step_s": E.HY_STEP_S,
        "fine_grid_step_s": FINE_STEP_S,
        "lag_range_s": [FINE_LO_S, FINE_HI_S],
        "window_days": days,
        "by_coin": by_coin,
        "between_coins": between,
    }
    out = artifact.write(
        OUT_NAME, payload, script=__file__,
        inputs=[E.BINANCE_RAW] + [os.path.join(CODE_DIR, f"mid_series_{c}.npz")
                                  for c in coins],
        scope=scope,
        settings={"hy_step_s": FINE_STEP_S, "hy_min_gap_ms": E.HY_MIN_GAP_MS,
                  "hy_max_ticks": E.MAX_HY_TICKS},
        started=t_start)
    print(f"\n[lagres] wrote {os.path.basename(out)}", flush=True)
    if between:
        print(f"[lagres] between contracts: published grid "
              f"{between['difference_on_published_grid_s']} s, fine grid "
              f"{between['difference_on_fine_grid_s']} s, uncapped "
              f"{between['difference_uncapped_s']} s; within-contract day-to-day sd "
              f"{between['within_coin_day_sd_s']}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
