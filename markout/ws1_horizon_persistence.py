#!/usr/bin/env python3
"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-08-03
References: Hyperliquid Level-4 order-book data, Zenodo 18184441 (Albers et al. 2026).

Horizon selection for the per-wallet adverse-selection (toxicity) score.

Question: which markout horizon best defines the score, and why that one and not another?

TWO QUESTIONS ARE BEING ASKED HERE AND THEY ARE NOT ONE QUESTION, which is why this file
produces two curves rather than one curve and a cross-check. The COST question asks how
long after a fill the permanent price impact has arrived, so that what is measured is
adverse selection and not the fill's own transient push; its evidence is the markout
LEVEL term structure and nothing else. The RANKING question asks over how long a
counterparty's score has to be averaged before the ordering of counterparties reproduces
on days that ordering was not fitted on; its evidence is the out-of-sample disattenuated
early-to-late rank persistence and nothing else.

The two pull opposite ways, because a longer window buys completeness and loses
persistence, so one horizon can serve both only where both clear at the same rung. An
earlier wording of this docstring made persistence the method and the level term
structure its cross-check, which reads as one decision with a subordinate criterion and
would let the persistence curve be cited as the defence of the cost window too.

Method: report both curves over the whole grid, then take the shortest rung the COST
decision admits, on its completeness criterion alone, among the rungs the RANKING
decision still scores highly, on its persistence criterion alone. Decision rules are
pre-registered before results are inspected. The whole curve is reported.

NO LOOKAHEAD INTO THE SCORE: a wallet's EARLY score uses only the early half of the
window, and the LATE score is the out-of-sample PREDICTION TARGET used to evaluate
persistence and to select the horizon (legitimate supervised model selection) -- it never
feeds the EARLY score that would actually be deployed. The halves are cut by
settings.split_early_late over the days the input carries, which on this December window
resolves to days 4-8 and 9-13.

Re-marks every fill against the book mid at a grid of horizons using the SAME as-of
join guards as i4_midmarkout.py (entry = last snapshot <= t_fill; horizon = first
snapshot >= t_fill + h; +/-5s tolerance). A reproduction gate asserts that the re-mark at
the headline window reproduces the committed column for that window before any new
horizon is trusted; the window and the column name both come from settings.py.

THIS FILE IS THE EVIDENCE BEHIND settings.HEADLINE_HORIZON_S, not a second opinion on it.
The decision itself is recorded in settings.py with its reasoning, and the value is read
back here so the two can never disagree; what this file contributes is the curve the
decision was made on. Read the fingerprint in the output before comparing any number
here with a number from an analysis file: the persistence curve is computed at a 10-fill
floor, the loosest rung of settings.RANK_FLOOR_SENSITIVITY, which is looser than anything
the analysis files score on.

Inputs (all on disk; the wallet codes in them are pseudonyms, see make_notebook_fills.py):
  notebooks/notebook_fills.npz   - block_time_ms, taker_code, coin, day, taker_side, entry_px, notional
  quickwin_markouts_mid.npz      - committed mo{1,10,60}_mid (reproduction cross-check), taker_id
  mid_series_{BTC,ETH}.npz       - t_ms, mid (top-of-book)
Outputs:
  ws1_horizon_results.json
Both WS1 figures are drawn by ws1_plot.py, which reads that results file and computes
nothing. This file drew ws1_persistence_vs_horizon.png until 2026-08-03, and the drawing
sat behind a catch that returned zero, so a run that could not import matplotlib wrote
fresh numbers, printed one line and left a two-day-old figure beside them.
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

HERE = os.path.dirname(os.path.abspath(__file__))
# Inputs and outputs named once, so a verification pass can re-point the outputs and
# nothing else and the module never has to be copied to be re-run.
IN_FILLS = os.path.join(_CODE_DIR, "notebooks", "notebook_fills.npz")
# The book-mid panel is located by panel_io, the one place that knows where the panels
# live. The other two inputs of this file -- the notebook fill dump and the per-coin
# mid series it re-marks against -- are not panels and panel_io declares nothing about
# them, so they stay joined here.
IN_MID_NPZ = os.path.join(P.data_root(), "quickwin_markouts_mid.npz")
# The results file is written by artifact.write, which takes a BARE name and puts the
# file beside this script. Only the name is needed, and only the name is ever recorded.
OUT_NAME = "ws1_horizon_results.json"

GRID = [1, 2, 5, 10, 20, 30, 60, 120]          # locked in pre-reg
# The grid is this file's OBJECT: it re-marks every fill at every rung, so it fixes no
# window. Two things it must contain, or the file cannot do its job -- the window
# settings.py names as the headline, and every rung a producer writes a column for,
# because those are what the reproduction gate below checks against.
assert H.HEADLINE_HORIZON_S in GRID, (
    f"the grid must contain settings.HEADLINE_HORIZON_S ({H.HEADLINE_HORIZON_S}s) or the "
    "reproduction gate cannot run")
assert set(H.LADDER_S) <= set(GRID), (
    f"the grid must contain every rung of settings.LADDER_S {H.LADDER_S}")
# Where the level term structure is read as flat. A judgement about the DATA, not a
# scoring window, so it lives here and not in settings.py.
PLATEAU_HORIZONS = (10, 20, 30, 60)
INFO_COMPLETE_FRAC = 0.95

# The early and late halves are DERIVED from the days the input actually carries, by
# settings.split_early_late, and are never day-of-month sets typed here. The two forms
# agree on this file's input and only on it: notebook_fills.npz runs 4 to 13, so the rule
# returns 4-8 and 9-13, the sets this file used to declare. On a window beginning on the
# 6th the typed sets would cut a three-day half against a seven-day one.
K_PRIMARY = 10                                   # locked; robustness at 25, 50.
K_ROBUST = [25, 50]
# K_PRIMARY is the LOOSEST rung of settings.RANK_FLOOR_SENSITIVITY and far below the
# declared RANK_FLOOR_FILLS of 50. It is load-bearing here in a way it is nowhere else:
# the horizon was chosen on this curve, and at ten fills the measured reliabilities below
# run about 0.29 to 0.44, so most of a disattenuated persistence is the correction. The
# curve is reported at 25 and 50 too (robustness_K) and the ordering holds, which is the
# reason the choice survives the floor. Recorded as an override, never inherited quietly.
GAP_MAX_MS = 5000.0                              # i4 tolerance
MS_PER_S = 1000
# No seed literal lives here any more. Both random streams below are derived from
# settings.MASTER_SEED and the identity of the cell being computed, through settings.rng.
# This file used to declare 424242 for the permutation and 20260619 for the bootstrap,
# neither of them the declared seed, which is how one quantity came to wear several names
# across the tree and how two scripts' p-values stopped being comparable.
# Label-permutation draws, READ from settings.py and never typed. Why this one cannot be
# a literal: the budget fixes the p-value floor at 1/(N+1), and a floor that does not
# clear the multiplicity threshold makes a floored p unable to survive the correction at
# ANY effect size -- and it fails silently, by reporting a number the correction then
# throws away. At the 200 draws this file used to declare, the floor was 0.00498 and 55
# of the 56 placebo p-values below sat exactly on it, against a threshold of 0.05/56 =
# 0.00089 for this file's own family. settings.N_PERM is computed from the level, the
# family size and the margin, so the floor follows them instead of being remembered.
N_PERM = H.N_PERM
# Bootstrap resamples, READ from settings.py under the name of this consumer, which since
# 2026-07-31 is the declared N_BOOT. The published intervals in this file were drawn at
# 500.
#
# What the number buys is not the budget but N * 0.025, the draws landing in each tail of
# a 95 percent interval, because that is what fixes how far an endpoint moves between
# seeds. 500 put twelve and a half draws in each tail against the fifty declared.
#
# THIS FILE IS THE ONE WHERE THE BUDGET DOES NOT ONLY BUY A BAND, which is why the
# recompute has to be read with the selection block open. np.nanstd of the same draws is
# boot_se, and boot_se is the width of the parsimony tie-break below: a horizon enters
# within_1se when its disattenuated persistence clears the maximum minus one boot_se. So
# a discrete list, and not only two endpoints, is drawn from this budget. What the list
# cannot do on the grid as it stands is change the chosen horizon: the maximum sits at the
# shortest rung of the grid and the rule takes the minimum of the list, and the runner-up
# is 0.0047 short of a threshold that would need boot_se a third larger to reach.
N_BOOT = H.boot_draws("ws1_horizon_persistence")

# code -> symbol, resolved empirically by median price and then CROSS-CHECKED against the
# declared map. The empirical resolution is kept because it is independent evidence; the
# check is what stops a silent relabel, which is the failure mode settings section 7
# exists for.
COIN_NAME = {c: None for c in H.coin_labels("quickwin")}


def load_mid(coin_name):
    z = np.load(os.path.join(P.data_root(), f"mid_series_{coin_name}.npz"))
    t = np.asarray(z["t_ms"], dtype=np.int64)
    mid = np.asarray(z["mid"], dtype=np.float64)
    order = np.argsort(t, kind="stable")
    t, mid = t[order], mid[order]
    keep = np.ones(t.size, dtype=bool)
    keep[:-1] = t[1:] != t[:-1]     # dup t_ms -> keep last (matches i4)
    return t[keep], mid[keep]


def join_entry(t_fill, S_t):
    # STRICTLY EARLIER, matching i4_midmarkout.join_entry. This function is a COPY of
    # that rule, and on 2026-08-02 the copy is what caught the two drifting apart: the
    # original moved to side="left" so that a snapshot stamped with the fill's own
    # millisecond -- which already carries the fill's impact -- can no longer supply the
    # entry mid, and this file's reproduction gate below promptly failed because it was
    # still comparing an old-rule re-mark against the new committed column. The gate was
    # right; the copy was stale. Four files in this tree spell this join out separately,
    # which is the actual defect underneath: the rule has no single home.
    idx = np.searchsorted(S_t, t_fill, side="left") - 1
    valid = idx >= 0
    safe = np.where(valid, idx, 0)
    gap = np.full(t_fill.shape, np.inf)
    gap[valid] = np.abs(t_fill[valid] - S_t[safe[valid]].astype(np.float64))
    valid &= gap <= GAP_MAX_MS
    return idx, valid


def join_horizon(t_fill, h_s, S_t):
    target = t_fill + h_s * MS_PER_S
    idx = np.searchsorted(S_t, target, side="left")
    valid = idx < S_t.size
    safe = np.where(valid, idx, 0)
    gap = np.full(t_fill.shape, np.inf)
    gap[valid] = np.abs(S_t[safe[valid]].astype(np.float64) - target[valid].astype(np.float64))
    valid &= gap <= GAP_MAX_MS
    return idx, valid


def markout_at(t_fill, taker_side, S_t, S_mid, h_s):
    """Signed book-mid markout in bps at horizon h. NaN where a leg is invalid."""
    e_idx, e_ok = join_entry(t_fill, S_t)
    h_idx, h_ok = join_horizon(t_fill, h_s, S_t)
    e_safe = np.where(e_ok, e_idx, 0)
    h_safe = np.where(h_ok, h_idx, 0)
    mid_e = S_mid[e_safe]
    mid_h = S_mid[h_safe]
    sign = np.where(taker_side == 1, 1.0, -1.0)
    ok = e_ok & h_ok & np.isfinite(mid_e) & (mid_e > 0)
    mo = sign * (mid_h - mid_e) / mid_e * 1e4
    return np.where(ok, mo, np.nan)


def spearman(x, y):
    """Spearman rho via Pearson on ranks (average ranks for ties)."""
    n = x.size
    if n < 3:
        return np.nan
    rx = _rankdata(x)
    ry = _rankdata(y)
    rx = rx - rx.mean()
    ry = ry - ry.mean()
    denom = np.sqrt((rx * rx).sum() * (ry * ry).sum())
    return float((rx * ry).sum() / denom) if denom > 0 else np.nan


def _rankdata(a):
    order = np.argsort(a, kind="stable")
    ranks = np.empty(a.size, dtype=np.float64)
    ranks[order] = np.arange(1, a.size + 1)
    # average ties
    s = a[order]
    i = 0
    while i < s.size:
        j = i
        while j + 1 < s.size and s[j + 1] == s[i]:
            j += 1
        if j > i:
            ranks[order[i:j + 1]] = (i + 1 + j + 1) / 2.0
        i = j + 1
    return ranks


def split_half_reliability(vals_by_unit_half):
    """Spearman-Brown reliability from odd/even within-unit half means.

    vals_by_unit_half: list of (mean_odd, mean_even) for units with >=2 fills split.
    """
    if len(vals_by_unit_half) < 3:
        return np.nan
    a = np.array([u[0] for u in vals_by_unit_half])
    b = np.array([u[1] for u in vals_by_unit_half])
    r = spearman(a, b)
    if not np.isfinite(r) or r <= -1:
        return np.nan
    return 2 * r / (1 + r)   # Spearman-Brown


def per_unit_means(unit_id, mo, day_arr, window_days):
    """Mean markout per unit within a day window; also odd/even half means.

    Returns dict unit -> (mean, n, mean_odd, mean_even) for units with n>=1.
    Odd/even split is by fill order (stable), used for reliability only.
    """
    in_win = np.array([d in window_days for d in day_arr]) if isinstance(window_days, set) else None
    mask = in_win & np.isfinite(mo)
    u = unit_id[mask]; m = mo[mask]
    order = np.argsort(u, kind="stable")
    u = u[order]; m = m[order]
    out = {}
    if u.size == 0:
        return out
    # group by contiguous runs of equal unit id
    boundaries = np.where(np.diff(u) != 0)[0] + 1
    starts = np.concatenate(([0], boundaries))
    ends = np.concatenate((boundaries, [u.size]))
    for s, e in zip(starts, ends):
        seg = m[s:e]
        n = seg.size
        mean = seg.mean()
        odd = seg[0::2].mean() if seg[0::2].size else np.nan
        even = seg[1::2].mean() if seg[1::2].size else np.nan
        out[int(u[s])] = (mean, n, odd, even)
    return out


def persistence_for_horizon(unit_id, mo, day_arr, K, cell):
    """Observed + disattenuated early->late Spearman at min-fills K, plus placebo/boot.

    `cell` names which cell of the grid this is -- the scope and the horizon -- and is
    what the two random streams below are derived from. It is required rather than
    defaulted, because a cell that forgets to name itself would silently share a stream
    with its neighbour, which is the defect the argument exists to remove.
    """
    early_days, late_days = H.split_early_late(np.unique(day_arr))
    early = per_unit_means(unit_id, mo, day_arr, set(early_days))
    late = per_unit_means(unit_id, mo, day_arr, set(late_days))
    units = [u for u in early if u in late and early[u][1] >= K and late[u][1] >= K]
    if len(units) < 10:
        return None
    xe = np.array([early[u][0] for u in units])
    xl = np.array([late[u][0] for u in units])
    rho_obs = spearman(xe, xl)
    # reliability within each window (odd/even), same unit set
    rel_e = split_half_reliability([(early[u][2], early[u][3]) for u in units
                                    if np.isfinite(early[u][2]) and np.isfinite(early[u][3])])
    rel_l = split_half_reliability([(late[u][2], late[u][3]) for u in units
                                    if np.isfinite(late[u][2]) and np.isfinite(late[u][3])])
    disatt = np.nan
    if np.isfinite(rel_e) and np.isfinite(rel_l) and rel_e > 0.05 and rel_l > 0.05:
        disatt = rho_obs / np.sqrt(rel_e * rel_l)
    # placebo: shuffle late labels. The stream comes from settings.MASTER_SEED and this
    # cell's identity, never from a literal. A literal seed shared by every cell makes all
    # 56 cells draw the SAME permutation sequence, so cells that read as independent are
    # not; a single module-level generator has the opposite defect, making a cell depend
    # on the ORDER cells are computed in, so inserting a horizon would move an earlier
    # one. Deriving from (MASTER_SEED, cell) is both order-independent and distinct.
    rng = H.rng("ws1", "placebo", K, *cell)
    perm = np.array([spearman(xe, rng.permutation(xl)) for _ in range(N_PERM)])
    placebo_mean = float(np.nanmean(perm))
    # THE COUNTING IS NOW stats.permutation_p, AND THE ARITHMETIC IS UNCHANGED. The note
    # that stood here named two differences and both turn out to be arguments, not
    # obstacles. The first is the slack: the module counts `|draw| >= |observed| - tol`
    # with tol scaled to the comparison BY DEFAULT, and this cell never applied one, so
    # it is stated as abs_tol=0.0 and the block records the rule as "absolute, stated by
    # the caller". The second is the denominator, and it needs the argument rather than
    # the assertion. A spearman of a degenerate cell returns NaN, and this line kept such
    # a draw in the denominator while the module divides by the draws that came back --
    # but the two counts cannot differ here. Permuting xl reorders the same values, so
    # the rank spread of every draw equals the rank spread of the observed pairing:
    # either every draw is finite, or none is and rho_obs is not finite either. The
    # second case is where the two spellings genuinely part -- this line reported the
    # budget's floor for a cell with no statistic at all, the module reports no test --
    # and it is carried over below rather than changed in passing. The generator was
    # never the obstacle: H.rng is what stats.rng passes through to.
    procedure = stats.permutation_p(rho_obs, perm, side="two_sided", abs_tol=0.0,
                                    n_requested=N_PERM,
                                    cell=("ws1", "placebo", K) + tuple(cell))
    placebo_p = float(procedure["p"] if procedure["p"] is not None
                      else H.p_floor(N_PERM))
    # bootstrap CI on rho_obs (resample units)
    # A separate stream from the placebo one, for the same reason: the two answer
    # different questions on the same cell and must not share draws.
    rngb = H.rng("ws1", "bootstrap", K, *cell)
    n = len(units)
    boot = np.empty(N_BOOT)
    for b in range(N_BOOT):
        ix = rngb.integers(0, n, n)
        boot[b] = spearman(xe[ix], xl[ix])
    # The interval itself is exactly stats.bootstrap_ci's -- percentile method, the same
    # 2.5/97.5 endpoints, the same integers(0, n, n) resample off the same stream -- but
    # this block is not routed through it, because boot_se below is a POPULATION standard
    # deviation (np.nanstd, ddof=0) where the module reports a sample one (ddof=1), and
    # boot_se is load-bearing: the parsimony tie-break picks the shortest horizon within
    # one boot_se of the maximum, so a factor of sqrt(500/499) can move h_star. The
    # module also does not return its draws, so the two cannot be mixed.
    lo, hi = np.nanpercentile(boot, [2.5, 97.5])
    return {
        "n_units": n, "rho_obs": rho_obs, "rel_early": rel_e, "rel_late": rel_l,
        "rho_disatt": None if not np.isfinite(disatt) else float(disatt),
        "boot_lo": float(lo), "boot_hi": float(hi), "boot_se": float(np.nanstd(boot)),
        "placebo_mean": placebo_mean, "placebo_p": placebo_p,
        "placebo_p_floor": H.p_floor(N_PERM),
        # True means no shuffle of the late labels reached |rho_obs|, so the p is the
        # budget's smallest expressible value and not a measurement.
        "placebo_p_is_floor": bool(H.p_is_floored(placebo_p, N_PERM)),
        # The counting block: the side, both draw counts, the slack and the rule that
        # set it, so the cell records the procedure and not only its result.
        "placebo_procedure": procedure,
    }


def main():
    started = artifact.start_clock()
    print("[ws1] loading fills ...")
    # panel_io names the producer to run when the book-mid panel is absent; the two
    # np.load calls stay here because build.py derives this script's input edges from
    # the argument of np.load.
    P.require_present("mid", IN_MID_NPZ)
    f = np.load(IN_FILLS)
    mid_npz = np.load(IN_MID_NPZ)

    t_ms = np.asarray(f["block_time_ms"], dtype=np.int64)
    side = np.asarray(f["taker_side"], dtype=np.int8)
    coin = np.asarray(f["coin"], dtype=np.int8)
    day = np.asarray(f["day"], dtype=np.int16)
    tk = np.asarray(f["taker_code"], dtype=np.int64)
    entry_px = np.asarray(f["entry_px"], dtype=np.float64)
    notional = np.asarray(f["notional"], dtype=np.float64)

    # --- alignment re-checks (both files must describe the SAME rows in order) ---
    assert np.array_equal(coin, np.asarray(mid_npz["coin"], dtype=np.int8)), "coin misaligned"
    assert np.array_equal(day, np.asarray(mid_npz["day"], dtype=np.int16)), "day misaligned"
    assert np.array_equal(tk, np.asarray(mid_npz["taker_id"], dtype=np.int64)), "taker id misaligned"
    assert np.allclose(entry_px, np.asarray(mid_npz["entry_px"], dtype=np.float64)), "entry_px misaligned"
    print(f"[ws1] {t_ms.size:,} fills, alignment OK")

    # --- coin code -> name by median price (BTC ~ 90k, ETH ~ 3k), then cross-checked ---
    for c in COIN_NAME:
        med = np.median(entry_px[coin == c])
        COIN_NAME[c] = "BTC" if med > 20000 else "ETH"
    declared = H.coin_labels("quickwin")
    assert COIN_NAME == declared, (
        f"median-price coin map {COIN_NAME} disagrees with the declared "
        f"settings.COIN_CODES_BY_ARTIFACT['quickwin'] {declared}; one of them relabels a "
        "coin, and that failure is silent")
    print(f"[ws1] coin map: {COIN_NAME} (matches the declared map)")

    # --- re-mark at the full grid, per coin ---
    mo_grid = {h: np.full(t_ms.size, np.nan, dtype=np.float64) for h in GRID}
    for c in COIN_NAME:
        name = COIN_NAME[c]
        S_t, S_mid = load_mid(name)
        m = coin == c
        for h in GRID:
            mo_grid[h][m] = markout_at(t_ms[m], side[m], S_t, S_mid, h)
        print(f"[ws1] re-marked {name}: {m.sum():,} fills across {len(GRID)} horizons")

    # --- REPRODUCTION GATE: the re-mark at the headline window must reproduce the
    # committed column for that window. Both the rungs and their column names come from
    # settings.py, so the gate cannot end up checking one window against another.
    gate = {}
    for h in H.LADDER_S:
        # Through panel_io, which builds the name from the same declaration and refuses
        # a rung the panel does not carry by naming what it does carry.
        stored = P.score(mid_npz, "mid", h)
        mine = mo_grid[h]
        both = np.isfinite(stored) & np.isfinite(mine)
        corr = spearman(stored[both], mine[both])
        w = notional[both]
        vw_stored = float(np.sum(w * stored[both]) / np.sum(w))
        vw_mine = float(np.sum(w * mine[both]) / np.sum(w))
        maxdiff = float(np.nanmax(np.abs(stored[both] - mine[both])))
        gate[f"h{h}"] = {"rank_corr": corr, "vw_stored": vw_stored, "vw_mine": vw_mine,
                         "max_abs_diff": maxdiff, "n_both": int(both.sum())}
        print(f"[gate] h={h}: corr={corr:.6f} vw_stored={vw_stored:.4f} vw_mine={vw_mine:.4f} maxdiff={maxdiff:.4g}")
    head_gate = f"h{H.HEADLINE_HORIZON_S}"
    assert gate[head_gate]["rank_corr"] > 0.999, \
        f"REPRO GATE FAILED at h={H.HEADLINE_HORIZON_S} (rank)"
    assert abs(gate[head_gate]["vw_mine"] - gate[head_gate]["vw_stored"]) < 0.02, \
        f"REPRO GATE FAILED at h={H.HEADLINE_HORIZON_S} (vw level)"
    print(f"[gate] PASSED - horizon machinery reproduces committed "
          f"{H.headline_mid_col()}; new horizons trusted.")

    # --- LEVEL term structure (information impounding): vw & ew mean per horizon ---
    # A wallet is held longer than 1s, so the maker's realised loss is the markout at
    # the horizon where information has IMPOUNDED. If the level is still climbing at 1s
    # but flat by 10s, 1s under-measures the cost even if its ranking is more persistent.
    lvl = {"pooled": {}}
    for name in COIN_NAME.values():
        lvl[name] = {}
    for h in GRID:
        mo = mo_grid[h]
        fin = np.isfinite(mo)
        lvl["pooled"][str(h)] = {"vw": float(np.sum(notional[fin] * mo[fin]) / np.sum(notional[fin])),
                                 "ew": float(np.mean(mo[fin])), "n": int(fin.sum())}
        for c in COIN_NAME:
            name = COIN_NAME[c]; mc = fin & (coin == c)
            lvl[name][str(h)] = {"vw": float(np.sum(notional[mc] * mo[mc]) / np.sum(notional[mc])),
                                 "ew": float(np.mean(mo[mc])), "n": int(mc.sum())}
    # THE NAME AND THE ARITHMETIC DISAGREE, KNOWINGLY. `frac_of_max` divides by the vw
    # markout at the LAST rung of the grid, 120 s, not by the maximum over the grid. The
    # level term structure is not monotone, so the two differ and the field runs above
    # one: it reads 1.0919 for the pooled 30 s rung in the committed artifact. The name
    # is the wrong one and the field is left alone anyway, because the criterion that
    # picked the scoring window reads info_frac -- a separate quantity, computed against
    # the MEDIAN over PLATEAU_HORIZONS a few lines below -- while frac_of_max is only
    # printed. Renaming it is free; changing the divisor would move a published number
    # and belongs to a recompute, not to a rename.
    for grp in lvl:
        base = lvl[grp][str(GRID[-1])]["vw"]
        for h in GRID:
            lvl[grp][str(h)]["frac_of_max"] = float(lvl[grp][str(h)]["vw"] / base) if base else None
    print("[level] pooled vw markout by h(s): " +
          ", ".join(f"{h}:{lvl['pooled'][str(h)]['vw']:.3f}({lvl['pooled'][str(h)]['frac_of_max']*100:.0f}%)" for h in GRID))

    # unit id = wallet within coin (avoid mixing a wallet's BTC and ETH scores)
    unit = tk.astype(np.int64) * 4 + coin.astype(np.int64)

    coin_names = list(COIN_NAME.values())
    # The same rule the persistence pass applies, evaluated once here so the fingerprint
    # states the halves this run genuinely used rather than a remembered pair.
    early_days, late_days = H.split_early_late(np.unique(day))
    # What every number in this file was computed under. The window recorded is the
    # headline one, but this file SELECTS no window: it re-marks the whole grid, and
    # grid_s is the list that matters.
    #
    # These are the KEYWORDS for settings.fingerprint, not the block itself. The block
    # is built once, by artifact.write, and lands in _meta.settings_fingerprint. It used
    # to be built here and stored as a top-level key of the payload, which put the record
    # in a second home: a census of the tree then had to decide whether a fingerprint
    # outside _meta counted, and three honest censuses of that property returned three
    # different numbers.
    settings_used = dict(
                   h=H.HEADLINE_HORIZON_S, lens="mid",
                   master_seed=H.MASTER_SEED,
                   reliability_seed=None,
                   n_perm=N_PERM,
                   n_boot=N_BOOT,
                   rank_floor_fills=[K_PRIMARY] + list(K_ROBUST),
                   persistence_floor_fills=None,
                   whale_drop_k=None,
                   fdr_alpha=None,
                   grid_s=list(GRID),
                   early_late_split=(
                       f"settings.split_early_late over the days present: "
                       f"early {list(early_days)}, late {list(late_days)}"),
                   plateau_horizons_s=list(PLATEAU_HORIZONS),
                   p_floor=H.p_floor(N_PERM),
                   overrides_note=(
                       "this file re-marks a GRID and selects no window; horizon_s is "
                       "recorded only because the reproduction gate is asserted there. "
                       "rank_floor_fills 10 primary with 25 and 50 as robustness: ten is "
                       "the LOOSEST rung of settings.RANK_FLOOR_SENSITIVITY and not the "
                       "declared 50, and it is load-bearing here because the horizon was "
                       "chosen on this curve. master_seed is settings.MASTER_SEED and is "
                       "stated as a CONFIRMATION rather than a deviation: this file used "
                       "to declare 424242 for the permutation and 20260619 for the "
                       "bootstrap, and now derives both streams from the declared seed "
                       "and the cell identity through settings.rng, so each of the 56 "
                       "cells draws its own stream instead of all of them re-drawing one. "
                       "reliability_seed does not apply: the split-half "
                       "reliability here is an ODD/EVEN split by fill order, which is "
                       "deterministic and draws no random numbers, unlike the seeded "
                       "estimator settings.RELIABILITY_SEED belongs to -- so the two "
                       "reliabilities are NOT the same estimator and must not be compared "
                       "cell for cell. n_perm is settings.N_PERM and is stated here as a "
                       "CONFIRMATION rather than a deviation: the run used the declared "
                       "budget, so the floor is 1/(N_PERM+1) and not the 0.00498 the "
                       "earlier 200-draw artifact reported. n_boot is settings.N_BOOT "
                       "and is a CONFIRMATION as well, adopted 2026-07-31 against the "
                       "500 the earlier artifact drew, so fifty draws decide each "
                       "endpoint instead of twelve and a half; in this file the same "
                       "draws also set boot_se, which is the width of the parsimony "
                       "tie-break in the selection block, so the budget reaches a "
                       "discrete list here and not only a band. The halves are cut by "
                       "settings.split_early_late over the "
                       "days present, which on this input returns the same 4-8 / 9-13 "
                       "the file used to type"),
    )
    results = {"grid_s": GRID, "K_primary": K_PRIMARY, "repro_gate": gate,
               "coin_map": COIN_NAME, "level_termstructure": lvl,
               "pooled": {},
               "per_coin": {n: {} for n in coin_names},
               "per_coin_K50": {n: {} for n in coin_names},
               "robustness_K": {}}

    # --- primary: pooled (wallet x coin units), per horizon ---
    for h in GRID:
        r = persistence_for_horizon(unit, mo_grid[h], day, K_PRIMARY, ("pooled", h))
        results["pooled"][str(h)] = r
        if r:
            print(f"[pooled K{K_PRIMARY}] h={h:3d}: rho_obs={r['rho_obs']:.4f} "
                  f"disatt={r['rho_disatt']} CI=[{r['boot_lo']:.3f},{r['boot_hi']:.3f}] "
                  f"placebo={r['placebo_mean']:.4f} (p={r['placebo_p']:.5f}"
                  f"{', FLOOR' if r['placebo_p_is_floor'] else ''}) n={r['n_units']}")

    # --- per coin (primary floor, plus 50 to cross-check the committed ks2 persistence) ---
    for c in COIN_NAME:
        name = COIN_NAME[c]
        m = coin == c
        for h in GRID:
            results["per_coin"][name][str(h)] = persistence_for_horizon(
                unit[m], mo_grid[h][m], day[m], K_PRIMARY, ("per_coin", name, h))
            results["per_coin_K50"][name][str(h)] = persistence_for_horizon(
                unit[m], mo_grid[h][m], day[m], 50, ("per_coin_K50", name, h))
    # Cross-check against the committed ks2 persistence, which is measured on the same
    # coin at the COMPANION window and a 50-fill floor. The cell is addressed by those
    # settings rather than by two typed numbers, so it cannot end up reading a different
    # cell than the one it claims to compare with.
    xcheck_coin = COIN_NAME[min(COIN_NAME)]
    b60 = results["per_coin_K50"][xcheck_coin][str(H.COMPANION_HORIZON_S)]
    if b60:
        print(f"[xcheck] {xcheck_coin} K50 h{H.COMPANION_HORIZON_S}: "
              f"rho_obs={b60['rho_obs']:.4f} disatt={b60['rho_disatt']} "
              f"(committed ks2 mid ~0.51 obs / ~0.73 disatt at the same window and floor)")

    # --- robustness at K=25,50 (pooled) ---
    for K in K_ROBUST:
        results["robustness_K"][str(K)] = {}
        for h in GRID:
            r = persistence_for_horizon(unit, mo_grid[h], day, K, ("robustness_K", h))
            results["robustness_K"][str(K)][str(h)] = r

    # --- apply pre-registered selection rule on pooled disattenuated persistence ---
    cand = [(h, results["pooled"][str(h)]) for h in GRID
            if results["pooled"][str(h)] and results["pooled"][str(h)]["rho_disatt"] is not None]
    best_h, best = max(cand, key=lambda kv: kv[1]["rho_disatt"])
    best_se = best["boot_se"]
    # parsimony tie-break: shortest h within 1 SE of the max disattenuated value
    within = [h for h, r in cand if r["rho_disatt"] >= best["rho_disatt"] - best_se]
    h_star = min(within) if within else best_h
    results["selection"] = {"argmax_h": best_h, "argmax_disatt": best["rho_disatt"],
                            "argmax_se": best_se, "within_1se": sorted(within),
                            "h_star_parsimony": h_star}
    print(f"[select] argmax h={best_h} (disatt={best['rho_disatt']:.4f}, SE={best_se:.4f}); "
          f"within 1 SE={sorted(within)} -> h*={h_star}")

    # --- FINAL horizon: the rung at which BOTH decisions clear, not one decision on two
    # criteria. The ranking decision, taken on persistence alone, selects h=1 (see
    # 'selection'). The cost decision, taken on the level term structure alone, refuses
    # h=1, because at one second the permanent adverse-selection impact has not arrived
    # and the maker holds longer than that. Neither overrules the other: what is taken
    # below is the SHORTEST rung the cost decision admits (info_frac >= 0.95 of the
    # plateau) among those the ranking decision still scores highly. Had no rung
    # satisfied both, this file would owe settings.py two declarations and not one.
    # See the deviation logged in the pre-registration file.
    plat = float(np.median([lvl["pooled"][str(h)]["vw"] for h in PLATEAU_HORIZONS]))
    info_frac = {h: lvl["pooled"][str(h)]["vw"] / plat for h in GRID}
    info_complete = [h for h in GRID if info_frac[h] >= INFO_COMPLETE_FRAC]
    ic_pers = [(h, results["pooled"][str(h)]["rho_disatt"]) for h in info_complete
               if results["pooled"][str(h)] and results["pooled"][str(h)]["rho_disatt"] is not None]
    best_ic = max(ic_pers, key=lambda kv: kv[1]) if ic_pers else (None, None)
    comp = str(H.COMPANION_HORIZON_S)
    dominated_companion = any(
        h < H.COMPANION_HORIZON_S and results["pooled"][str(h)] and results["pooled"][comp]
        and results["pooled"][str(h)]["rho_disatt"] is not None
        and results["pooled"][comp]["rho_disatt"] is not None
        and results["pooled"][str(h)]["rho_disatt"] > results["pooled"][comp]["rho_disatt"]
        for h in info_complete)
    # The recommendation is READ BACK from settings.py, which is where the decision and
    # its reasoning now live. Repeating the integer here would let the two drift, and a
    # drift between the file that chose the window and the file that declares it is
    # exactly the defect settings.py exists to prevent. What this file still owns is the
    # EVIDENCE: the grid, the curve, and the checks below that the recommendation clears
    # its own two criteria.
    recommended = H.HEADLINE_HORIZON_S
    results["final_decision"] = {
        "plateau_vw_bps": plat,
        "plateau_horizons_s": list(PLATEAU_HORIZONS),
        "info_complete_frac_threshold": INFO_COMPLETE_FRAC,
        "info_frac": {str(h): info_frac[h] for h in GRID},
        "info_complete_horizons": info_complete,
        "most_persistent_info_complete": best_ic[0],
        "recommended_score_horizon_s": recommended,
        "recommended_source": "settings.HEADLINE_HORIZON_S, read back so this file and "
                              "the declaration cannot drift; the evidence for it is the "
                              "curve and the two checks below",
        "recommended_is_info_complete": bool(recommended in info_complete),
        "recommended_info_frac": float(info_frac[recommended]),
        "reported_term_structure_s": [GRID[0], recommended, 30],
        # This list is what the horizon-selection FIGURE stops reporting, which is not the
        # same as what the study stops using: the companion window is still reported beside
        # the headline in every robustness table (settings.COMPANION_HORIZON_S). The old key
        # name "dropped" said the stronger thing.
        "dropped_from_reported_term_structure": [H.COMPANION_HORIZON_S, GRID[-1]],
        "companion_window_still_reported_s": H.COMPANION_HORIZON_S,
        "old_choice_companion_dominated": bool(dominated_companion),
        "rationale": ("persistence falls monotonically with h; the permanent impact is ~fully "
                      "impounded by 5-10s (1s captures only ~80% of the plateau); "
                      f"{recommended}s is the shortest conventional horizon at the plateau, "
                      "keeps high persistence (0.52 disatt vs 0.32 at 60s), and equals the "
                      "maker reaction window; 60s is dominated for SCORING (half the "
                      "persistence, no extra info) and is kept only as the reported "
                      "companion; 1s rejected (info incomplete + transient/own-impact "
                      "contamination). The most persistent info-complete rung is 5s, which "
                      "no producer writes a column for, which is why it is not adopted.")}
    print(f"[final] info-complete={info_complete}, most-persistent-IC={best_ic[0]}s, "
          f"recommended={recommended}s (from settings.py, info_frac="
          f"{info_frac[recommended]:.4f}), companion {H.COMPANION_HORIZON_S}s dropped from "
          f"the reported term structure but kept as the companion "
          f"(dominated={dominated_companion})")

    # The scope is stated from what this run actually read, never inferred and never
    # remembered: the fill count, the days the input carries, and the coin symbols the
    # median-price resolution produced and the declared map confirmed. The population
    # sentence names the FILL FLOOR too, because the curve is computed at ten fills and
    # every analysis file in this tree scores at fifty; a reader who takes a number from
    # here to compare with one from there has to be told that in the artifact.
    days_present = sorted(int(d) for d in np.unique(day))
    artifact.write(
        OUT_NAME, results,
        script=__file__,
        inputs=[IN_FILLS, IN_MID_NPZ]
               + [os.path.join(P.data_root(), f"mid_series_{n}.npz")
                  for n in COIN_NAME.values()],
        scope={
            "population": (
                f"{t_ms.size} taker fills re-marked at every rung of the "
                f"{len(GRID)}-point horizon grid; persistence over wallet-coin units "
                f"with at least {K_PRIMARY} fills in each half (the loosest rung of "
                f"settings.RANK_FLOOR_SENSITIVITY), with {K_ROBUST} as robustness and "
                f"a separate per-coin table at a 50-fill floor"),
            "window": (
                f"days {days_present[0]}-{days_present[-1]} of the December window, "
                f"split by settings.split_early_late into early {list(early_days)} and "
                f"late {list(late_days)}"),
            "coins": sorted(COIN_NAME.values()),
        },
        settings=settings_used,
        started=started)
    print(f"[ws1] wrote {OUT_NAME}")
    # The figure is NOT drawn here. It is drawn by ws1_plot.py, which reads this very
    # results file and computes nothing. Splitting it out is the fix rather than a
    # tidying: while one node both computed and drew, a figure that failed to be drawn
    # was invisible inside the exit code of a computation that had succeeded, and that
    # is exactly how the figure on disk came to be two days older than these numbers.
    print("[ws1] the figure is NOT drawn here. Draw it with:\n"
          "    uv run --no-project --with-requirements requirements.txt python3 "
          "ws1_plot.py")


if __name__ == "__main__":
    main()
