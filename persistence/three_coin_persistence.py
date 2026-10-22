#!/usr/bin/env python3
"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-08-05
References:
  - Spearman, C. (1904). "The proof and measurement of association between two things."
    American Journal of Psychology 15(1), 72-101. (Split-half reliability, and the
    correction for attenuation this file divides by.)
  - Brown, W. (1910). "Some experimental results in the correlation of mental
    abilities." British Journal of Psychology 3(3), 296-322. (The prophecy formula
    used to lift a half-length reliability to full length.)
  - Hyperliquid node-data L4 archive (s3://hl-mainnet-node-data), parsed into
    panel_markouts_v2.npz by panel_rebuild_v2.py.

DOES THE WALLET RANKING HOLD ON A THIRD CONTRACT, AND ON THE BOOK-MID LENS?

WHAT THIS ANSWERS AND WHY IT IS SEPARATE FROM ks2_persistence_10day.py. That file scores
the two contracts the ten-day quickwin window carries, BTC and ETH, and it is the
project's headline persistence. The question here is narrower and is the one a reader
asks immediately afterwards: two contracts is a thin basis for a claim about wallets,
so does the same ranking survive on a third, and does it survive when the harm is
measured against the book mid rather than the trade print. The December panel is the
only file in this tree that carries SOL, so it is the only place the question can be put
at all.

WHY THE ESTIMATOR IS NOT ks2's, AND WHY THE DIFFERENCE IS DECLARED RATHER THAN QUIETLY
CARRIED. Both files divide an observed early-versus-late rank correlation by the square
root of the two half-window reliabilities. They differ in how the reliability itself is
taken, in two ways at once, and either way alone moves the third decimal:

  ks2 splits a wallet's fills ODD and EVEN by position and uses ONE seed.
  This file splits ROW BY ROW with a fair coin and averages FIFTY split seeds.

Averaging over seeds is the reason this file exists in the shape it does: a reliability
read off one split carries the noise of that split into the divisor, and settings.py
records the measured size of that noise as RELIABILITY_SEED_SPREAD_SD, 0.0086 on the
headline cell. Fifty splits put the divisor's own standard error an order below the
quantity it corrects. The cost is that the two files' numbers are close but not equal,
and neither is a check on the other. Whichever is quoted has to be quoted with its
estimator named, which is what the register entry does.

WHAT MOVED WHEN THIS COMPUTATION CAME INTO THE REPOSITORY, because the numbers it
publishes are not the numbers a scratch script produced on 2026-07-29. Three causes were
possible and the print lens separates them, because a print-lens figure passes through
neither the mid rebuild nor -- in its observed correlation -- any random split at all.

  THE ENTRY JOIN, and it is the one that moves the published numbers. The scratch script
  built the book-mid markout with its own copy of the i4_midmarkout formula, taken when
  that formula used side="right" -- the last snapshot AT OR BEFORE the fill. On
  2026-08-02 i4_midmarkout changed that to strictly before, because a snapshot stamped
  with the fill's own millisecond already carries that fill's impact: 13.18 per cent of
  fills were taking their entry mid from one, and the harm measured on them collapsed to
  a quarter of the harm on the rest. Every mid-lens observed correlation in this file
  rises against the scratch run, by between 0.002 and 0.034, and no print-lens one moves.
  This file does not carry a copy of the formula at all. It CALLS
  i4_midmarkout.compute_mid_block, so the lens it scores is the lens the shipped mid
  artifact holds, and a future repair to the join reaches this file without anyone
  remembering to bring it.

  THE SEED, which moves the correction and not the correlation. The scratch script opened
  each reliability split on abs(hash((lens, h, coin, K, s))) % 2**32. Python salts string
  hashing per process, so that seed differed on every run and the artifact could not be
  reproduced even by its own author -- measured three times in three processes on
  2026-08-05, it returned 3204786889, 2192008809 and 128567485. Here every stream comes
  from settings.rng(), which derives it from MASTER_SEED and the cell identity, so two
  runs of this file draw the same splits and no two cells share one. The size of what
  that changes is readable off the print lens, where the correlation itself stands still
  and only the divisor is redrawn: the disattenuated figures there move by at most 0.009,
  which is settings.RELIABILITY_SEED_SPREAD_SD, 0.0086, arrived at from the other
  direction.

  THE INPUT, which moved nothing and was the suspect. panel_markouts_v2.npz was rebuilt
  on 2026-08-04, after the scratch run, and a figure standing on bytes that no longer
  exist is a figure nobody can check. Measured rather than argued: replaying the scratch
  script's accumulator on TODAY's panel returns 0.597665 for the ten-second print lens on
  bitcoin at the fifty-fill floor, against the 0.5977 that run published. The December
  print columns are what they were.

  A FOURTH THING TURNED UP IN THAT MEASUREMENT AND IT IS NOT ONE OF THE THREE. The print
  lens does move, by up to 0.0003, and the cause is the width of an accumulator: the
  scratch script summed the panel's float32 markout column with numpy.cumsum, which keeps
  the input dtype, so a per-wallet mean over as many as 1.2 million rows accumulated in
  single precision. This file casts to float64 before summing. Same rows, same rule, a
  wider register: 0.597665 in float32 against 0.597497 in float64 on the cell above.

THE CONTROL, AND WHY IT IS A REFUSAL RATHER THAN A PRINTED WARNING. The book-mid
markout this file rebuilds for three coins must reproduce, on the two coins where a
shipped artifact exists, what quickwin_markouts_mid.npz already holds. If it does not,
the lens is not the project's lens and no persistence computed on it may be read. So the
comparison runs first, cell by cell over coin and day on both the mean and the count of
usable rows, and a failure raises before a single persistence figure is computed. The
pattern is the one flat_surcharge_control.py already uses: a producer that cannot
reproduce the published quantity does not get to print the new one.

THE CONTROL IS CALIBRATED ON TWO OPPOSITE CASES AND BOTH ARE TAKEN OFF THIS TREE, because
a control that has only ever passed is indistinguishable from one that cannot fail. Both
were run on 2026-08-05 by substituting the entry join and leaving everything else alone.

  It MUST pass with i4_midmarkout.join_entry as it stands, and does: the worst of the
  twenty coin-day cells differs by 9.06e-08 bps in the mean and by zero usable rows.

  It MUST refuse with the pre-2026-08-02 entry rule, the one that took the last snapshot
  at or before the fill, and does: twenty cells of twenty disagree, the worst of them ETH
  on day 10.

    uv run --no-project --with-requirements requirements.txt python3 -u \
        three_coin_persistence.py
    uv run --no-project --with-requirements requirements.txt python3 -u \
        three_coin_persistence.py --smoke        # one lens, one horizon
"""
import argparse
import os
import sys
import time

import numpy as np
from scipy.stats import spearmanr

HERE = os.path.dirname(os.path.abspath(__file__))
# The shared modules sit in the repository root, one directory up from this
# group, and this file also imports from the data group. Both are built from this
# file's own location and never from the working directory the run happens to
# start in.
_CODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_CODE_DIR, os.path.join(_CODE_DIR, "data")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import artifact                                                        # noqa: E402
import panel_io as P                                                   # noqa: E402
import settings as H                                                   # noqa: E402
# The book-mid lens is CALLED, not copied: compute_mid_block carries the entry and
# horizon joins, the gap tolerance and the sign convention, and it is the same function
# that wrote quickwin_markouts_mid.npz.
import i4_midmarkout as I4                                             # noqa: E402

OUT_NAME = "three_coin_persistence_results.json"

# All three sit under the declared data root, which stayed at the top of the repository
# when the producers were grouped into directories.
PANEL = os.path.join(P.data_root(), "panel_markouts_v2.npz")
QUICKWIN = os.path.join(P.data_root(), "quickwin_markouts.npz")
QUICKWIN_MID = os.path.join(P.data_root(), "quickwin_markouts_mid.npz")

# The December period code inside the panel. The panel carries several periods in one
# array and the third contract exists only in this one.
PERIOD = 202512
# The mid series are named by period here rather than bare, because the bare spelling
# exists for two of the three coins only. For those two the two spellings are the same
# bytes -- verified by hash on 2026-08-05, c0c1890b for BTC and eb617dff for ETH -- so
# naming the period costs nothing and states which window the snapshots come from.
MID_SERIES = os.path.join(P.data_root(), "mid_series_{coin}_%d.npz" % PERIOD)

# Every setting below is bound from the declaration rather than typed. The three that
# have a value at all in this file are the coin map of the PANEL (three coins, where
# quickwin has two), the number of reliability splits, and the floor on how many wallets
# a cell needs before its correlation is reported.
COINS = H.coin_labels("panel")                    # {0: BTC, 1: ETH, 2: SOL}
QUICKWIN_COINS = H.coin_labels("quickwin")        # {0: BTC, 1: ETH}
HORIZONS_S = tuple(H.LADDER_S)
LENSES = tuple(H.LENSES)
FLOORS = tuple(H.PERSISTENCE_FLOOR_FILLS)
MIN_WALLETS = H.MIN_COMMON_WALLETS
N_PERM = H.N_PERM

# How many independent row-wise splits the reliability is averaged over. It is a COUNT
# of seeds and not a seed, so it is not one of the values settings.py declares; it is
# the number the published figure was computed at and the reason it is fifty rather than
# five is in the module docstring. i3_book_comparator.py holds the same kind of constant
# under SEED_SWEEP_N.
RELIABILITY_SPLITS = 50
# A split half needs this many wallets in common before a rank correlation is taken off
# it at all. Below that the reliability itself is noise and dividing by it manufactures
# persistence out of nothing.
MIN_WALLETS_FOR_RELIABILITY = 10


def _day_split():
    """The early and late halves of the window, from the one declaration."""
    early, late = H.split_early_late(sorted(set(range(4, 14))))
    return ([int(d) for d in early], [int(d) for d in late])


def load_panel():
    """The December slice of the panel: wallet, coin, day, side, time, print markouts."""
    z = np.load(PANEL)
    sel = z["period"] == PERIOD
    out = {
        "taker_id": z["taker_id"][sel],
        "coin": z["coin"][sel],
        "day": z["day"][sel],
        "taker_side": z["taker_side"][sel],
        "t_ms": (z["block_time_ns"][sel] // 1_000_000).astype(np.int64),
    }
    for h in HORIZONS_S:
        out[("print", h)] = z[f"mo{h}"][sel]
    return out


def load_mid_series(coin):
    """One coin's book-mid series, in the shape i4_midmarkout's joins expect.

    The sort and the duplicate-timestamp collapse are i4_midmarkout.load_mid_series's,
    repeated here only because that function reads a fixed path list built from the
    quickwin coin map and cannot be pointed at the third contract. The arithmetic that
    follows -- the joins, the tolerance, the markout -- is that module's own.
    """
    path = MID_SERIES.format(coin=coin)
    z = np.load(path)
    t_ms = np.asarray(z["t_ms"], dtype=np.int64)
    cols = {k: np.asarray(z[k], dtype=np.float64)
            for k in ("mid", "spread", "imb", "micro")}
    if t_ms.size:
        order = np.argsort(t_ms, kind="stable")
        t_ms = t_ms[order]
        cols = {k: v[order] for k, v in cols.items()}
        keep = np.ones(t_ms.size, dtype=bool)
        keep[:-1] = t_ms[1:] != t_ms[:-1]
        t_ms = t_ms[keep]
        cols = {k: v[keep] for k, v in cols.items()}
    return dict(t_ms=t_ms, **cols)


def build_mid_lens(panel):
    """The book-mid markout for every row of the December panel, one coin at a time."""
    n = panel["coin"].size
    out = {("mid", h): np.full(n, np.nan, dtype=np.float64) for h in HORIZONS_S}
    for code, name in sorted(COINS.items()):
        sel = panel["coin"] == code
        if not sel.any():
            continue
        S = load_mid_series(name)
        block = I4.compute_mid_block(panel["t_ms"][sel], panel["taker_side"][sel], S)
        for h in HORIZONS_S:
            out[("mid", h)][sel] = block[I4.mo_col(h)].astype(np.float64)
        print(f"  [mid] {name}: {int(sel.sum()):,} rows, "
              f"{int(np.isfinite(out[('mid', H.HEADLINE_HORIZON_S)][sel]).sum()):,} "
              f"usable at {H.HEADLINE_HORIZON_S} s", flush=True)
    return out


def control_against_shipped(panel, mid):
    """Reproduce the shipped book-mid artifact on the two coins that have one.

    Returns the per-cell table. Raises if any cell disagrees, because a lens that does
    not reproduce the published one is a different lens and nothing computed on it may
    be read as this project's persistence.
    """
    zq = np.load(QUICKWIN)
    zm = np.load(QUICKWIN_MID)
    col = I4.mo_col(H.HEADLINE_HORIZON_S)
    days_early, days_late = _day_split()
    days = list(days_early) + list(days_late)
    rows, bad = [], []
    for code, name in sorted(QUICKWIN_COINS.items()):
        for d in days:
            theirs = zm[col][(zq["coin"] == code) & (zq["day"] == d)]
            mine = mid[("mid", H.HEADLINE_HORIZON_S)][
                (panel["coin"] == code) & (panel["day"] == d)]
            tm, mm = float(np.nanmean(theirs)), float(np.nanmean(mine))
            tn, mn = int(np.isfinite(theirs).sum()), int(np.isfinite(mine).sum())
            row = {"coin": name, "day": int(d),
                   "shipped_mean_bps": tm, "rebuilt_mean_bps": mm,
                   "shipped_usable_rows": tn, "rebuilt_usable_rows": mn,
                   "abs_mean_difference_bps": abs(tm - mm),
                   "usable_row_difference": abs(tn - mn)}
            rows.append(row)
            # The tolerance on the mean is the last bit of a float32 column carried
            # through a mean of six figures of rows, not a guessed epsilon; the row
            # count has no tolerance at all, because a count is an integer and two
            # populations either match or do not.
            if row["usable_row_difference"] != 0 or row["abs_mean_difference_bps"] > 1e-4:
                bad.append(row)
    if bad:
        worst = max(bad, key=lambda r: r["abs_mean_difference_bps"])
        raise SystemExit(
            "the rebuilt book-mid lens does not reproduce quickwin_markouts_mid.npz, so "
            "no persistence is computed. Expected the shipped column "
            f"{col!r}; {len(bad)} of {len(rows)} coin-day cells disagree. Worst cell: "
            f"{worst['coin']} day {worst['day']}, shipped mean "
            f"{worst['shipped_mean_bps']:.6f} bps against rebuilt "
            f"{worst['rebuilt_mean_bps']:.6f} bps, shipped rows "
            f"{worst['shipped_usable_rows']:,} against rebuilt "
            f"{worst['rebuilt_usable_rows']:,}. The usual cause is that this file and "
            "the shipped artifact were built under different entry-join rules; "
            "i4_midmarkout.join_entry moved from at-or-before to strictly-before on "
            "2026-08-02 and everything downstream of it had to be rebuilt")
    return rows


def group_means(keys, values):
    """Mean of `values` within each distinct key. Returns (keys, means, counts)."""
    order = np.argsort(keys, kind="stable")
    keys, values = keys[order], values[order]
    uniq, start = np.unique(keys, return_index=True)
    end = np.append(start[1:], keys.size)
    csum = np.concatenate(([0.0], np.cumsum(values)))
    return uniq, (csum[end] - csum[start]) / (end - start), (end - start)


def split_half_reliability(wallet, value, generator):
    """Reliability of one half-window's per-wallet mean, from one random row split.

    Each ROW goes to one side of the split on a fair coin, the two per-wallet means are
    rank-correlated over the wallets present on both sides, and the result is lifted to
    full length by the Spearman-Brown formula 2r / (1 + r). Row-wise rather than by
    position within the wallet, so a wallet whose behaviour drifts through the window
    does not have the drift counted as unreliability.
    """
    left = generator.random(wallet.size) < 0.5
    k1, m1, _ = group_means(wallet[left], value[left])
    k2, m2, _ = group_means(wallet[~left], value[~left])
    common, i1, i2 = np.intersect1d(k1, k2, return_indices=True)
    if common.size < MIN_WALLETS_FOR_RELIABILITY:
        return np.nan
    r = spearmanr(m1[i1], m2[i2]).statistic
    if not np.isfinite(r) or r <= -1:
        return np.nan
    return 2.0 * r / (1.0 + r)


def one_cell(lens, horizon_s, coin, floor, wallet, day, value, days_early, days_late):
    """One (lens, horizon, coin, floor) cell of the persistence table, or None."""
    early = np.isin(day, days_early)
    late = np.isin(day, days_late)
    ke, me, ne = group_means(wallet[early], value[early])
    kl, ml, nl = group_means(wallet[late], value[late])
    kept = np.intersect1d(ke[ne >= floor], kl[nl >= floor])
    if kept.size < MIN_WALLETS:
        return None
    xe = me[np.searchsorted(ke, kept)]
    xl = ml[np.searchsorted(kl, kept)]
    observed = float(spearmanr(xe, xl).statistic)

    in_early = early & np.isin(wallet, kept)
    in_late = late & np.isin(wallet, kept)
    rel_early, rel_late = [], []
    for s in range(RELIABILITY_SPLITS):
        rel_early.append(split_half_reliability(
            wallet[in_early], value[in_early],
            H.rng("three_coin_reliability_early", lens, horizon_s, coin, floor, s)))
        rel_late.append(split_half_reliability(
            wallet[in_late], value[in_late],
            H.rng("three_coin_reliability_late", lens, horizon_s, coin, floor, s)))
    rel_early = np.asarray(rel_early, dtype=np.float64)
    rel_late = np.asarray(rel_late, dtype=np.float64)
    per_split = observed / np.sqrt(rel_early * rel_late)

    null = H.rng("three_coin_permutation", lens, horizon_s, coin, floor)
    hits = sum(1 for _ in range(N_PERM)
               if abs(spearmanr(xe, null.permutation(xl)).statistic) >= abs(observed))
    return {
        "lens": lens, "horizon_s": int(horizon_s), "coin": coin, "K": int(floor),
        "n_wallets": int(kept.size),
        "spearman_obs": observed,
        "disatt": float(observed / np.sqrt(np.nanmean(rel_early)
                                           * np.nanmean(rel_late))),
        "disatt_p05": float(np.nanpercentile(per_split, 5)),
        "disatt_p95": float(np.nanpercentile(per_split, 95)),
        "reliability_early_mean": float(np.nanmean(rel_early)),
        "reliability_late_mean": float(np.nanmean(rel_late)),
        "n_reliability_splits": RELIABILITY_SPLITS,
        "pvalue": float((hits + 1) / (N_PERM + 1)),
        "p_floor": H.p_floor(N_PERM),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--smoke", action="store_true",
                    help="the headline lens and horizon only, to prove the wiring")
    args = ap.parse_args()

    t_start = artifact.start_clock()
    lenses = (H.HEADLINE_LENS,) if args.smoke else LENSES
    horizons = ((H.HEADLINE_HORIZON_S,) if args.smoke else HORIZONS_S)
    days_early, days_late = _day_split()
    print(f"[3coin] coins={sorted(COINS.values())} lenses={list(lenses)} "
          f"horizons={list(horizons)}s floors={list(FLOORS)} "
          f"| early days {days_early} against late {days_late}", flush=True)

    t_load = time.time()
    panel = load_panel()
    print(f"[3coin] panel period {PERIOD}: {panel['coin'].size:,} rows loaded in "
          f"{time.time() - t_load:.0f} s", flush=True)
    mid = build_mid_lens(panel)

    control = control_against_shipped(panel, mid)
    print(f"[3coin] control against quickwin_markouts_mid.npz: {len(control)} coin-day "
          f"cells, worst mean difference "
          f"{max(r['abs_mean_difference_bps'] for r in control):.2e} bps, worst row "
          f"difference {max(r['usable_row_difference'] for r in control)}", flush=True)

    source = dict(mid)
    for h in HORIZONS_S:
        source[("print", h)] = panel[("print", h)].astype(np.float64)

    cells, skipped = [], []
    for lens in lenses:
        for h in horizons:
            for code, coin in sorted(COINS.items()):
                base = (panel["coin"] == code) & np.isfinite(source[(lens, h)])
                wallet = panel["taker_id"][base]
                day = panel["day"][base]
                value = source[(lens, h)][base]
                for floor in FLOORS:
                    cell = one_cell(lens, h, coin, floor, wallet, day, value,
                                    days_early, days_late)
                    if cell is None:
                        skipped.append({"lens": lens, "horizon_s": int(h),
                                        "coin": coin, "K": int(floor),
                                        "why": f"fewer than {MIN_WALLETS} wallets clear "
                                               f"the floor in both halves"})
                        continue
                    cells.append(cell)
                    print(f"  {lens:5s} h={h:2d} {coin:4s} K={floor:3d} "
                          f"n={cell['n_wallets']:4d} obs={cell['spearman_obs']:+.4f} "
                          f"disatt={cell['disatt']:+.4f} p={cell['pvalue']:.5f}",
                          flush=True)

    scope = {
        "population": (
            f"{panel['coin'].size:,} taker fills of the December panel, period "
            f"{PERIOD}, on three contracts. A wallet enters a cell when it clears the "
            f"cell's fill floor in BOTH halves of the window, and a cell is reported "
            f"only when at least {MIN_WALLETS} wallets do; "
            f"{len(cells)} cells reported and {len(skipped)} skipped for that reason. "
            f"Each reliability is the mean of {RELIABILITY_SPLITS} independent row-wise "
            f"splits"),
        "window": (f"December 2025, days {days_early[0]} to {days_late[-1]}; "
                   f"early half {days_early} against late half {days_late}"),
        "coins": sorted(COINS.values()),
    }
    payload = {
        "question": ("whether the wallet ranking by adverse-selection harm survives "
                     "from the early half of the window to the late half on a third "
                     "contract, and on the book-mid lens as well as the trade print"),
        "estimator": (
            "rho_disattenuated = rho_observed / sqrt(mean reliability early * mean "
            "reliability late), where each reliability is the Spearman-Brown lift of a "
            "rank correlation between two random halves of a wallet's ROWS, averaged "
            f"over {RELIABILITY_SPLITS} splits. It differs from "
            "ks2_persistence_10day.py in the unit of the split and in the number of "
            "splits, so the two files' figures are close and are not checks on each "
            "other"),
        "mid_lens_built_by": ("i4_midmarkout.compute_mid_block, called rather than "
                             "copied, so the entry and horizon joins and the gap "
                             "tolerance are the ones the shipped artifact used"),
        "control_vs_shipped_mid": control,
        "cells": cells,
        "cells_skipped": skipped,
    }
    out = artifact.write(
        OUT_NAME, payload, script=__file__,
        inputs=[PANEL, QUICKWIN, QUICKWIN_MID]
               + [MID_SERIES.format(coin=c) for c in sorted(COINS.values())],
        scope=scope,
        settings={"h": H.HEADLINE_HORIZON_S, "n_perm": N_PERM,
                  "master_seed": H.MASTER_SEED},
        started=t_start)
    print(f"\n[3coin] wrote {os.path.basename(out)}: {len(cells)} cells", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
