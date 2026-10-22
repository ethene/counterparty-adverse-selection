"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-20
References: Hyperliquid node-data S3 archive (s3://hl-mainnet-node-data); Hyperliquid
  L2-book archive (s3://hyperliquid-archive/market_data); Zenodo 18184441 (Albers et al. 2026).
"""

# ---------------------------------------------------------------------------
# I4 - MID markout (maker adverse-selection on the L2-book mid).
#
# build_quickwin_markouts.py already books, per collapsed taker trade, the
# adverse-selection markout against the TRADE-PRINT reference price (one VWAP
# print per hash). This script recomputes the SAME markout against the L2-BOOK
# MID, so the two reference clocks can be cross-checked (a robustness leg of I4):
# a real maker adverse-selection signal should show up on the book mid, not only
# on trade prints that the taker itself moved.
#
# ROW ALIGNMENT (non-negotiable): the output rows must be identical to and in
# the same order as quickwin_markouts.npz. We GUARANTEE this by importing
# build_quickwin_markouts as a module and reusing its parse_day verbatim, then
# walking the EXACT same `for day in DAYS: for coin in COINS:` loop and the same
# per-slice append order (d["taker_addr"] order). The native trade-print markout
# columns and every original column are copied straight through; the mid-markout
# columns are computed alongside on the SAME fills.
#
# The mid join itself uses the L2-book mid series written by i4_l2_mid.py
# (mid_series_BTC.npz / mid_series_ETH.npz), loaded FULLY into memory (both coins,
# full window) so a fill near an hour boundary reaches across that boundary.
#
# OUTPUT npz schema (quickwin_markouts_mid.npz), one aligned row per collapsed
# trade, SAME order as quickwin_markouts.npz:
#   -- every original column, copied through --
#   taker_id int32 | coin int8 | day int16 | entry_px float64 |
#   notional float32 | is_open int8 | start_pos float32 | taker_side int8 |
#   closed_pnl float32 | dir_code int8 | maker_id int32
#   -- NEW mid-based columns --
#   mo1_mid, mo10_mid, mo60_mid  float32  maker adverse-selection markout on MID (bps)
#       = sign_taker * (mid(t+h) - mid(t)) / mid(t) * 1e4
#         sign_taker = +1 if taker BOUGHT (taker_side==1) else -1
#         POSITIVE = taker profited = maker adverse-selected (same convention).
#   imb_entry         float32  imb of the entry snapshot
#   spread_entry_bps  float32  spread(t)/mid(t)*1e4
#   micro_dev_bps     float32  (micro(t)-mid(t))/mid(t)*1e4
#   gap_entry_ms, gap_h1_ms, gap_h10_ms, gap_h60_ms  float32  |snapshot t - target t|
#
# Run command (bare python3 is BLOCKED on this machine):
#   uv run --no-project --with-requirements requirements.txt python3 data/i4_midmarkout.py
# ---------------------------------------------------------------------------

import os
import sys

import numpy as np

# One place writes a results file, so every results file says the same things about
# itself: the producer and its hash, the inputs, the scope, the settings fingerprint
# and the run. See artifact.py for why the record has one author rather than sixty-eight.
# artifact.py, settings.py and the other shared modules sit in the
# repository root, one directory up from this group, so the path is built
# from this file's own location and never from the working directory the
# run happens to start in.
_CODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CODE_DIR not in sys.path:
    sys.path.insert(0, _CODE_DIR)

import artifact
import build_quickwin_markouts as bqm
import panel_io as P
import settings as H

# The one seed, taken from the declaration rather than repeated here. Its value is
# unchanged (settings.MASTER_SEED is 20260620), so binding it moves nothing.
SEED = H.MASTER_SEED
np.random.seed(SEED)

HERE = os.path.dirname(os.path.abspath(__file__))
# The series and the array it writes live under the declared data root, which stayed at
# the top of the repository when the producers were grouped. The results file stays
# beside its producer.
MID_PATH = {c: os.path.join(P.data_root(), f"mid_series_{c}.npz")
            for c in H.coin_labels("quickwin").values()}
OUT_NPZ = os.path.join(P.data_root(), "quickwin_markouts_mid.npz")
OUT_SUMMARY = os.path.join(HERE, "i4_midmarkout_results.json")

# This script is a PRODUCER: it writes a column for every rung of the ladder, so it
# fixes no scoring window. The rungs come from settings.LADDER_S and the column names
# from settings.headline_mid_col(h), so the on-disk schema cannot drift from what the
# analysis files ask for. Adding a rung here is therefore a settings change, not an
# edit to this file.
HORIZONS_S = tuple(H.LADDER_S)
MS_PER_S = 1000
GAP_MAX_MS = 5000.0          # entry/horizon join tolerance


# -------------------- optional ENV smoke-test overrides --------------------
# Mirror the contract overrides onto the imported module so the SAME fills are
# parsed for both the trade-print and the mid pass.
def _apply_env_overrides():
    days = os.environ.get("CAP_DAYS")
    coins = os.environ.get("CAP_COINS")
    if days:
        bqm.DAYS = [d.strip() for d in days.split(",") if d.strip()]
    if coins:
        cs = tuple(c.strip().upper() for c in coins.split(",") if c.strip())
        bqm.COINS = cs
    # CAP_HOURS is honoured by the mid loader / i4_l2_mid; the fill parse reads
    # whole days, so hour subsetting only narrows the mid series (some fills then
    # fall outside the loaded mid window and nan-drop, which is the intended
    # smoke-test behaviour).


# -------------------- mid series loader (full window, in memory) --------------------
def load_mid_series():
    """Load mid_series_{COIN}.npz for every active coin into memory.

    Returns {coin: {"t_ms","mid","spread","imb","micro"}} with t_ms sorted asc.
    The producer (i4_l2_mid.py) already sorts and de-dups; we re-assert sort here
    so searchsorted is always valid even if the artifact is regenerated loosely.
    """
    series = {}
    for coin in bqm.COINS:
        path = MID_PATH.get(coin)
        if path is None or not os.path.exists(path):
            raise FileNotFoundError(
                f"missing mid series for {coin}: {path} - run i4_l2_mid.py first")
        z = np.load(path)
        t_ms = np.asarray(z["t_ms"], dtype=np.int64)
        mid = np.asarray(z["mid"], dtype=np.float64)
        spread = np.asarray(z["spread"], dtype=np.float64)
        imb = np.asarray(z["imb"], dtype=np.float64)
        micro = np.asarray(z["micro"], dtype=np.float64)
        # defensive: enforce ascending t_ms, collapse dup t_ms keeping last
        if t_ms.size:
            order = np.argsort(t_ms, kind="stable")
            t_ms, mid, spread, imb, micro = (
                t_ms[order], mid[order], spread[order], imb[order], micro[order])
            keep = np.ones(t_ms.size, dtype=bool)
            keep[:-1] = t_ms[1:] != t_ms[:-1]   # for runs of equal t_ms keep last
            t_ms, mid, spread, imb, micro = (
                t_ms[keep], mid[keep], spread[keep], imb[keep], micro[keep])
        series[coin] = {"t_ms": t_ms, "mid": mid, "spread": spread,
                        "imb": imb, "micro": micro}
        print(f"[i4mid] loaded mid_series_{coin}: {t_ms.size:,} snapshots")
    return series


# -------------------- as-of joins (the JOIN GUARDS, vectorized) --------------------
def join_entry(t_fill_ms, S):
    """LAST snapshot STRICTLY EARLIER than t_fill (no lookahead, and no same-instant).

    Returns (idx, gap_ms, valid). idx<0 / gap>GAP_MAX_MS => invalid.

    WHY STRICTLY EARLIER, AND WHAT IT COST TO FIND OUT. Until 2026-08-02 this used
    side="right", which takes the last snapshot with snapshot_t <= t_fill and therefore
    ACCEPTS a snapshot carrying the fill's own millisecond. That is not a lookahead in
    the usual sense -- nothing after the fill is read -- but a book stamped at the
    instant of the trade already carries the trade's own impact, so the entry mid it
    supplies is contaminated by the very quantity the markout is trying to measure, and
    the measured harm on those rows collapses.

    Measured on the artifact this file wrote under the old rule, over its own 2,480,267
    rows: 326,849 of them (13.18 per cent) had gap_entry_ms exactly 0, and the
    notional-weighted 10s book-mid markout on that stratum was +0.5238 bps against
    +2.2867 bps on the rest. The published pooled figure of +2.0616 bps was therefore a
    mixture of two populations and UNDERSTATED the harm by about ten per cent of its own
    size. A random join would put 0.18 per cent of rows on a same-instant snapshot, so
    the 13.18 per cent is a property of the join rule, not of the tape.

    side="left" - 1 returns the last index with snapshot_t < t_fill. The change can only
    move a row's entry snapshot one step earlier, so gap_entry_ms rises for exactly those
    rows and the GAP_MAX_MS guard below still decides validity.
    """
    t_arr = S["t_ms"]
    n = t_arr.size
    idx = np.searchsorted(t_arr, t_fill_ms, side="left") - 1
    valid = idx >= 0
    gap = np.full(t_fill_ms.shape, np.inf, dtype=np.float64)
    safe = np.where(valid, idx, 0)
    gap[valid] = np.abs(t_fill_ms[valid] - t_arr[safe[valid]].astype(np.float64))
    valid &= gap <= GAP_MAX_MS
    return idx, gap, valid


def join_horizon(t_fill_ms, h_s, S):
    """FIRST snapshot with snapshot_t >= t_fill + h*1000.

    Returns (idx, gap_ms, valid). out-of-range / gap>GAP_MAX_MS => invalid.
    """
    t_arr = S["t_ms"]
    n = t_arr.size
    target = t_fill_ms + h_s * MS_PER_S
    idx = np.searchsorted(t_arr, target, side="left")
    valid = idx < n
    gap = np.full(t_fill_ms.shape, np.inf, dtype=np.float64)
    safe = np.where(valid, idx, 0)
    gap[valid] = np.abs(t_arr[safe[valid]].astype(np.float64) - target[valid].astype(np.float64))
    valid &= gap <= GAP_MAX_MS
    return idx, gap, valid


def mo_col(h):
    """Book-mid markout column name for one rung, built from settings, never typed."""
    return H.headline_mid_col(h)


def gap_col(h):
    """Join-gap column name for one rung.

    The spelling gap_h{h}_ms is the SCHEMA of an npz that already exists on disk and
    that other scripts read by name, so it is built from h rather than renamed: a name
    change here would orphan every committed artifact. It is derived from the same rung
    list as the markout column beside it, so the two cannot fall out of step.
    """
    return f"gap_h{int(h)}_ms"


MO_COLS = tuple(mo_col(h) for h in HORIZONS_S)
GAP_COLS = ("gap_entry_ms",) + tuple(gap_col(h) for h in HORIZONS_S)


def compare_rows(pairs):
    """Row-by-row verdict on this pass's print columns against the shipped file's.

    pairs   iterable of (mine, theirs) 1-D arrays of equal length, one pair per rung.
    Returns (identical, max_abs_diff, nan_pattern_equal).

    WHY THIS IS NOT THE ROW COUNT, and why it is a separate function. The row count and
    the two volume-weighted means are both invariant to a permutation of the rows, so
    neither can see the one failure that would silently ruin every mid column: the same
    fills emitted in another order, each mid value then sitting beside the wrong trade.
    This comparison sees it.

    The missing-value pattern is compared on its own because nan != nan, so a
    subtraction alone would report every nan-against-nan row as a difference. The
    tolerance on the finite entries is exactly zero, not a guessed epsilon: both sides
    are the same float32 column from the same bqm.compute_markouts_all, so agreeing
    rows agree bit for bit.

    CALIBRATED ON TWO OPPOSITE CASES, both of which this function must get right and
    which its self-test exercises: an identical pair including nans, where it must
    return True, and a pair that is a PERMUTATION of the same values, where it must
    return False. A one-sided check would not tell a working comparison from one that
    compares an array with itself, which is the exact defect this file's summary
    carried before.

    Self-test (cheap, no tape, no npz):
        uv run --no-project --with-requirements requirements.txt python3 data/i4_midmarkout.py --selftest
    """
    patterns_equal = []
    diffs = []
    for mine, theirs in pairs:
        mine = np.asarray(mine, dtype=np.float64)
        theirs = np.asarray(theirs, dtype=np.float64)
        nan_mine, nan_theirs = np.isnan(mine), np.isnan(theirs)
        patterns_equal.append(bool(np.array_equal(nan_mine, nan_theirs)))
        both = ~nan_mine & ~nan_theirs
        diffs.append(float(np.max(np.abs(mine[both] - theirs[both])))
                     if both.any() else float("nan"))
    nan_pattern_equal = bool(all(patterns_equal))
    max_abs_diff = max(diffs) if diffs else float("nan")
    identical = bool(nan_pattern_equal and max_abs_diff == 0.0)
    return identical, max_abs_diff, nan_pattern_equal


def _selftest():
    """Two opposite cases for compare_rows, printed with expectation, fact and place."""
    rng = np.random.default_rng(SEED)
    a = rng.normal(size=2000).astype(np.float32)
    a[::97] = np.nan                      # a realistic scatter of join misses
    b = rng.normal(size=2000).astype(np.float32)
    b[::53] = np.nan

    checks = []
    # MUST BE SILENT: the same columns, nans and all.
    got = compare_rows(((a, a.copy()), (b, b.copy())))
    checks.append(("identical pair", True, got[0], got))
    # MUST FIRE: the same VALUES in another order. Row count, nan count and every
    # volume-weighted mean are unchanged by this, which is the point.
    perm = rng.permutation(a.size)
    got = compare_rows(((a, a.copy()[perm]), (b, b.copy()[perm])))
    checks.append(("permuted pair", False, got[0], got))

    bad = 0
    for name, expect, fact, detail in checks:
        ok = fact is expect
        bad += (not ok)
        print(f"[selftest] {name:<15} expect identical={expect}  fact={fact}  "
              f"(max_abs_diff={detail[1]!r}, nan_pattern_equal={detail[2]})  "
              f"place=i4_midmarkout.compare_rows  {'OK' if ok else 'FAIL'}")
    print(f"[selftest] {'PASS' if bad == 0 else 'FAIL'}: {len(checks) - bad}"
          f"/{len(checks)} cases")
    return bad


def compute_mid_block(t_fill_ms, taker_side, S):
    """Compute the mid-markout block for one coin-day slice of fills.

    t_fill_ms  int64[n]   fill block_time in epoch-ms
    taker_side int8[n]    1 if taker bought, 0 if sold
    S          dict       this coin's full-window mid series

    Returns dict of float32 arrays length n:
      mo1_mid, mo10_mid, mo60_mid, imb_entry, spread_entry_bps, micro_dev_bps,
      gap_entry_ms, gap_h1_ms, gap_h10_ms, gap_h60_ms
    """
    n = t_fill_ms.size
    nan = np.float32(np.nan)
    out = {k: np.full(n, nan, dtype=np.float32) for k in (
        MO_COLS + ("imb_entry", "spread_entry_bps", "micro_dev_bps") + GAP_COLS)}

    if n == 0:
        return out
    if S["t_ms"].size == 0:
        # no book for this coin: every join is nan, but rows are kept
        for k in GAP_COLS:
            out[k][:] = np.inf
        return out

    # entry snapshot (last at-or-before)
    e_idx, e_gap, e_valid = join_entry(t_fill_ms, S)
    out["gap_entry_ms"][:] = e_gap.astype(np.float32)

    e_safe = np.where(e_valid, e_idx, 0)
    mid_entry = S["mid"][e_safe]
    # entry features (only where the entry snapshot is valid)
    out["imb_entry"][e_valid] = S["imb"][e_safe][e_valid].astype(np.float32)
    spread_bps = S["spread"][e_safe] / mid_entry * 1e4
    out["spread_entry_bps"][e_valid] = spread_bps[e_valid].astype(np.float32)
    micro_dev = (S["micro"][e_safe] - mid_entry) / mid_entry * 1e4
    out["micro_dev_bps"][e_valid] = micro_dev[e_valid].astype(np.float32)

    # sign_taker: +1 if bought, -1 if sold
    sign_taker = np.where(taker_side == 1, 1.0, -1.0)

    gap_keys = {h: gap_col(h) for h in HORIZONS_S}
    mo_keys = {h: mo_col(h) for h in HORIZONS_S}
    for h in HORIZONS_S:
        h_idx, h_gap, h_valid = join_horizon(t_fill_ms, h, S)
        out[gap_keys[h]][:] = h_gap.astype(np.float32)
        h_safe = np.where(h_valid, h_idx, 0)
        mid_h = S["mid"][h_safe]
        # both legs must be valid AND entry mid finite
        ok = e_valid & h_valid & np.isfinite(mid_entry) & (mid_entry > 0)
        # maker adverse-selection markout on mid:
        #   = sign_taker * (mid(t+h) - mid(t)) / mid(t) * 1e4
        # sign_taker = +1 if taker BOUGHT else -1, so
        # POSITIVE = taker profited = maker adverse-selected.
        mo = sign_taker * (mid_h - mid_entry) / mid_entry * 1e4
        vals = np.where(ok, mo, np.nan)
        out[mo_keys[h]][:] = vals.astype(np.float32)
    return out


# -------------------- main --------------------
def main():
    t0 = artifact.start_clock()
    _apply_env_overrides()
    print(f"[i4mid] days={bqm.DAYS} coins={bqm.COINS} horizons={HORIZONS_S}s "
          f"seed={SEED}")

    mid_series = load_mid_series()

    # original-passthrough column accumulators (must match build_quickwin order)
    col_addr = []
    col_coin = []
    col_day = []
    col_entry_px = []
    col_mo1 = []
    col_mo10 = []
    col_mo60 = []
    col_notional = []
    col_is_open = []
    col_start_pos = []
    col_taker_side = []
    col_closed_pnl = []
    col_dir_code = []
    col_maker_addr = []

    # new mid-column accumulators (same key set compute_mid_block returns)
    col_new = {k: [] for k in (
        MO_COLS + ("imb_entry", "spread_entry_bps", "micro_dev_bps") + GAP_COLS)}

    resolved = []
    issues = []

    # EXACT same loop structure and append order as build_quickwin_markouts.main()
    for day in bqm.DAYS:
        day_num = int(day[6:8])
        per_coin, hours_ok = bqm.parse_day(day)
        if per_coin is None:
            issues.append(f"day {day} missing on S3 - skipped")
            print(f"[i4mid] day {day} MISSING on S3 - skipped")
            continue
        resolved.append(day)

        for coin in bqm.COINS:
            d = per_coin[coin]
            n_trades = int(d["taker_ts"].size)
            if n_trades == 0 or d["print_ts"].size == 0:
                # build_quickwin SKIPS the append for an empty/print-less slice;
                # we replicate that skip so the row order stays identical.
                issues.append(f"{coin} {day}: empty - skipped (matches print pass)")
                print(f"[i4mid] SLICE {coin} {day}: empty - skipped")
                continue

            # trade-print markout (REUSED verbatim) for the passthrough columns
            mo = bqm.compute_markouts_all(
                d["taker_ts"], d["taker_px"], d["taker_dir"],
                d["print_ts"], d["print_px"])
            mo1, mo10, mo60 = mo[1], mo[10], mo[60]
            notional = d["taker_size"] * d["taker_px"]

            # block_time is NANOSECONDS -> convert ONCE to epoch-ms for the mid join
            t_ms_fill = (d["taker_ts"] // 1_000_000).astype(np.int64)
            taker_side = np.asarray(d["taker_side"], dtype=np.int8)

            S = mid_series.get(coin)
            if S is None:
                # coin not in the loaded mid window (e.g. ENV coin subset): nan
                S = {"t_ms": np.empty(0, np.int64), "mid": np.empty(0),
                     "spread": np.empty(0), "imb": np.empty(0),
                     "micro": np.empty(0)}
            blk = compute_mid_block(t_ms_fill, taker_side, S)

            # append passthrough columns in the SAME order as the print pass
            n_rows = n_trades
            col_addr.extend(d["taker_addr"].tolist())
            col_coin.extend([bqm.COIN_CODE[coin]] * n_rows)
            col_day.extend([day_num] * n_rows)
            col_entry_px.extend(d["taker_px"].tolist())
            col_mo1.extend(mo1.tolist())
            col_mo10.extend(mo10.tolist())
            col_mo60.extend(mo60.tolist())
            col_notional.extend(notional.tolist())
            col_is_open.extend(d["taker_open"].tolist())
            col_start_pos.extend(d["taker_spos"].tolist())
            col_taker_side.extend(d["taker_side"].tolist())
            col_closed_pnl.extend(d["taker_cpnl"].tolist())
            col_dir_code.extend(d["taker_dcode"].tolist())
            col_maker_addr.extend(d["maker_addr"].tolist())

            for k in col_new:
                col_new[k].extend(blk[k].tolist())

            # per-slice nan diagnostic on the HEADLINE mid markout (the column the
            # analysis files score on), named from settings so the printed caption and
            # the column it reports can never be two different windows.
            head_col = H.headline_mid_col()
            v_head = np.asarray(blk[head_col], dtype=np.float64)
            nd_head = float(np.mean(np.isnan(v_head))) if v_head.size else float("nan")
            print(f"[i4mid] SLICE {coin} {day}: trades={n_trades:,} "
                  f"{head_col} nan-drop={nd_head*100:.1f}%")

    # ---- integer-code wallets / makers EXACTLY as the print pass does ----
    # First-seen order over the same row order reproduces the same code spaces;
    # taker_id/maker_id therefore equal those in quickwin_markouts.npz.
    wallet_to_code = {}
    taker_id = np.empty(len(col_addr), dtype=np.int32)
    for i, w in enumerate(col_addr):
        code = wallet_to_code.get(w)
        if code is None:
            code = len(wallet_to_code)
            wallet_to_code[w] = code
        taker_id[i] = code

    maker_to_code = {}
    maker_id = np.empty(len(col_maker_addr), dtype=np.int32)
    for i, w in enumerate(col_maker_addr):
        if w is None:
            maker_id[i] = -1
            continue
        code = maker_to_code.get(w)
        if code is None:
            code = len(maker_to_code)
            maker_to_code[w] = code
        maker_id[i] = code

    # ---- assemble aligned arrays with SPEC dtypes ----
    coin_arr = np.asarray(col_coin, dtype=np.int8)
    day_arr = np.asarray(col_day, dtype=np.int16)
    entry_px_arr = np.asarray(col_entry_px, dtype=np.float64)
    mo1_arr = np.asarray(col_mo1, dtype=np.float32)
    mo10_arr = np.asarray(col_mo10, dtype=np.float32)
    mo60_arr = np.asarray(col_mo60, dtype=np.float32)
    notional_arr = np.asarray(col_notional, dtype=np.float32)
    is_open_arr = np.asarray(col_is_open, dtype=np.int8)
    start_pos_arr = np.asarray(col_start_pos, dtype=np.float32)
    taker_side_arr = np.asarray(col_taker_side, dtype=np.int8)
    closed_pnl_arr = np.asarray(col_closed_pnl, dtype=np.float32)
    dir_code_arr = np.asarray(col_dir_code, dtype=np.int8)

    new_arr = {k: np.asarray(col_new[k], dtype=np.float32) for k in col_new}

    # The mid-side columns are written under the names settings.py builds, so the
    # ladder here and the ladder the analysis files read are the same list by
    # construction rather than by two matching spellings.
    np.savez_compressed(
        OUT_NPZ,
        taker_id=taker_id,
        coin=coin_arr,
        day=day_arr,
        entry_px=entry_px_arr,
        notional=notional_arr,
        is_open=is_open_arr,
        start_pos=start_pos_arr,
        taker_side=taker_side_arr,
        closed_pnl=closed_pnl_arr,
        dir_code=dir_code_arr,
        maker_id=maker_id,
        **{k: new_arr[k] for k in MO_COLS},
        imb_entry=new_arr["imb_entry"],
        spread_entry_bps=new_arr["spread_entry_bps"],
        micro_dev_bps=new_arr["micro_dev_bps"],
        **{k: new_arr[k] for k in GAP_COLS},
    )

    total_rows = int(taker_id.size)

    # ---- per-horizon nan-drop fractions ----
    def _nan_frac(a):
        a = np.asarray(a, dtype=np.float64)
        return float(np.mean(np.isnan(a))) if a.size else float("nan")

    nan_drop = {k: _nan_frac(new_arr[k]) for k in MO_COLS}

    # ---- sanity: vol-weighted mean of the HEADLINE mid markout vs its print twin ----
    # Both column names come from settings.py, so the two sides of the comparison are
    # the same window by construction. SHORT_H is the first rung of the ladder, kept as
    # the second sanity pair because the shortest window is where a bad join shows first.
    SHORT_H = HORIZONS_S[0]
    HEAD_H = H.HEADLINE_HORIZON_S

    def _vw_mean(vals, weights):
        vals = np.asarray(vals, dtype=np.float64)
        weights = np.asarray(weights, dtype=np.float64)
        m = np.isfinite(vals) & np.isfinite(weights) & (weights > 0)
        if not m.any():
            return float("nan")
        return float(np.sum(vals[m] * weights[m]) / np.sum(weights[m]))

    vw_mo1_mid = _vw_mean(new_arr[H.headline_mid_col(SHORT_H)], notional_arr)
    vw_mo10_mid = _vw_mean(new_arr[H.headline_mid_col(HEAD_H)], notional_arr)

    # THE PRINT SIDE OF THE PAIR IS TWO DIFFERENT COMPARISONS, AND EACH ONE NOW HAS ITS
    # OWN KEY. They answer different questions, so a single field carrying whichever of
    # them the filesystem happened to allow is not a weaker version of either -- it is a
    # field whose meaning a reader cannot recover from the file.
    #
    #   THIS PASS. The trade-print columns recomputed here, by the same
    #   bqm.compute_markouts_all, on the same fills as the mid columns beside them. It
    #   asks whether the two LENSES agree inside one run. No file enters it, so it is
    #   computed unconditionally and it can never say anything about the shipped
    #   artifact.
    #
    #   SHIPPED. The same two means taken from quickwin_markouts.npz, the artifact the
    #   study's print-lens numbers are actually drawn from. It asks whether this pass
    #   reproduces that file, so it covers the join and the file itself. It is
    #   computable only when the file is on disk, and where it is not, every key
    #   belonging to it is null. Null is the honest record: the comparison was not made.
    #   What the two MEANS do not cover is the row order, because a volume-weighted mean
    #   over the whole array is invariant to a permutation of the rows; the row-by-row
    #   comparison below covers that, and it is recorded under its own key rather than
    #   folded into the means.
    #
    # What this replaces. The print side used to be chosen by whether the npz happened
    # to be on disk, under one key name, and the summary recorded neither the choice nor
    # the question -- so vw_mean_..._print_bps meant the shipped file on one machine and
    # this run's own columns on another, with nothing in the artifact to tell them
    # apart. The row count was worse: the fallback arm compared mo10_arr against the row
    # count OF THAT SAME ARRAY, so row_aligned_to_print_npz came out true by
    # construction, having compared nothing. A tautology reported as a check is what
    # this file exists to catch elsewhere.
    print_npz = os.path.join(P.data_root(), "quickwin_markouts.npz")
    have_shipped = os.path.exists(print_npz)

    vw_mo1_print_this_pass = _vw_mean(mo1_arr, notional_arr)
    vw_mo10_print_this_pass = _vw_mean(mo10_arr, notional_arr)

    if have_shipped:
        zp = np.load(print_npz)
        mo1_print = np.asarray(zp[H.headline_print_col(SHORT_H)], dtype=np.float64)
        mo10_print = np.asarray(zp[H.headline_print_col(HEAD_H)], dtype=np.float64)
        notional_print = np.asarray(zp["notional"], dtype=np.float64)
        rows_shipped = int(mo10_print.size)
        aligned = bool(rows_shipped == total_rows)
        vw_mo1_print = _vw_mean(mo1_print, notional_print) if aligned else float("nan")
        vw_mo10_print = _vw_mean(mo10_print, notional_print) if aligned else float("nan")
        # ROW BY ROW, and it is a separate question from the row COUNT above. Equal
        # lengths and equal volume-weighted means are both invariant to a permutation of
        # the rows, so neither can see the failure this whole file is built to rule out:
        # the same fills emitted in another order would satisfy both, and every mid
        # column would then sit beside the wrong trade. Only an element-wise comparison
        # sees it, and it costs nothing here because this pass already holds its own
        # copy of the trade-print columns in memory.
        rows_identical = None
        max_abs_diff = None
        nan_pattern_equal = None
        if aligned:
            rows_identical, max_abs_diff, nan_pattern_equal = compare_rows(
                ((mo1_arr, mo1_print), (mo10_arr, mo10_print)))
        print_arm = "shipped_artifact"
        print_arm_answers = ("this pass reproduces the trade-print artifact the "
                             "study's print-lens numbers come from, row by row and "
                             "not only in aggregate")
    else:
        rows_shipped = None
        # NOT False. False would say the row counts were compared and disagreed; None
        # says no comparison was made, which is what happened.
        aligned = None
        vw_mo1_print = None
        vw_mo10_print = None
        rows_identical = None
        max_abs_diff = None
        nan_pattern_equal = None
        print_arm = "no_shipped_artifact"
        print_arm_answers = ("the shipped trade-print artifact was absent, so every "
                             "field belonging to that comparison is null and nothing "
                             "here checks against it; the *_this_pass fields beside "
                             "them are a lens agreement within this run and are not a "
                             "substitute for it")

    summary = {
        "config": {
            "days_requested": list(bqm.DAYS),
            "days_resolved": resolved,
            "coins": list(bqm.COINS),
            "horizons_s": list(HORIZONS_S),
            "seed": SEED,
            "gap_max_ms": GAP_MAX_MS,
            "mid_join": "entry=last snapshot t<=t_fill; horizon=first t>=t_fill+h*1000",
            "markout_sign": "mo*_mid bps; positive = taker profited = maker adverse-selected",
            "out_npz": os.path.basename(OUT_NPZ),
            "mid_columns_written": list(MO_COLS),
            "reuses": "build_quickwin_markouts.parse_day (row-aligned to quickwin_markouts.npz)",
        },
        "total_rows": total_rows,
        # True or false only where the comparison was made. Null where the shipped
        # trade-print artifact was not on disk, because no row count was compared.
        "row_aligned_to_print_npz": aligned,
        # WHICH comparison the *_print_bps fields below are, named in the artifact so a
        # reader never has to guess what this run did. The *_this_pass fields are always
        # this run's own print columns; the plain *_print_bps fields are always the
        # shipped artifact, and are null when it was absent.
        "print_twin_source": {
            "arm": print_arm,
            "file": os.path.basename(print_npz) if have_shipped else None,
            "answers": print_arm_answers,
            "comparison_made": bool(have_shipped),
            "rows_shipped_artifact": rows_shipped,
            "rows_this_pass": int(total_rows),
            "row_aligned": aligned,
            # The row COUNT and the row CONTENT are two verdicts, kept apart because
            # the first cannot see a reordering and the second can.
            "rows_identical": rows_identical,
            "rows_identical_predicate": (
                "element-wise over all rows, this pass's own trade-print columns "
                "against the shipped file's, at both rungs of the sanity pair; the "
                "missing-value patterns are compared separately because nan != nan, "
                "and the tolerance on the finite entries is exactly zero because both "
                "sides are the same float32 computation. Null means the shipped "
                "artifact was absent or the row counts already disagreed, so no "
                "element-wise comparison was attempted."),
            "max_abs_diff_vs_shipped": max_abs_diff,
            "nan_pattern_equal_vs_shipped": nan_pattern_equal,
        },
        "nan_drop_frac": nan_drop,
        f"vw_mean_{H.headline_mid_col(SHORT_H)}_bps": vw_mo1_mid,
        f"vw_mean_{H.headline_print_col(SHORT_H)}_print_bps": vw_mo1_print,
        f"vw_mean_{H.headline_mid_col(HEAD_H)}_bps": vw_mo10_mid,
        f"vw_mean_{H.headline_print_col(HEAD_H)}_print_bps": vw_mo10_print,
        f"vw_mean_{H.headline_print_col(SHORT_H)}_print_bps_this_pass":
            vw_mo1_print_this_pass,
        f"vw_mean_{H.headline_print_col(HEAD_H)}_print_bps_this_pass":
            vw_mo10_print_this_pass,
        "issues": issues,
    }
    # The raw hourly directories parse_day pulled are deleted the moment they are
    # parsed -- the system disk cannot hold them -- so the bucket key is what identifies
    # them, and artifact.input_record keeps a URI whole for exactly that reason.
    day_inputs = [f"s3://{bqm.S3_BUCKET}/node_fills_by_block/hourly/{d}/"
                  for d in resolved]
    artifact.write(
        os.path.basename(OUT_SUMMARY), summary,
        script=__file__,
        inputs=[MID_PATH[c] for c in bqm.COINS if c in MID_PATH]
               + [print_npz] + day_inputs,
        # What the numbers cover, stated rather than inferred, and it NAMES THE ARM the
        # print-twin comparison ran in: the same file with and without the shipped
        # artifact beside it holds two different populations for those fields, and a
        # reader has to be able to see which one this is without owning the machine.
        scope={
            "population": (f"{total_rows:,} collapsed taker trades, one row per "
                           f"(hash, taker) sweep, re-marked on the L2 book mid; no "
                           f"wallet floor and no eligibility filter is applied"),
            "window": (f"{len(resolved)} of {len(bqm.DAYS)} requested days resolved: "
                       f"{', '.join(resolved) if resolved else 'none'}"),
            # Never an empty list: an empty scope field reads exactly like a scope
            # covering every coin. CAP_COINS can be set to a list of separators only.
            "coins": list(bqm.COINS) or "n/a: the resolved coin list is empty",
            "print_twin_arm": print_arm,
            "print_twin_arm_note": print_arm_answers,
        },
        # A PRODUCER fixes no scoring window -- it writes a column for every rung -- so
        # horizon_s is the headline only in the sense that the sanity pair is measured
        # there, and horizons_written_s is the list that matters for the artifact.
        settings={
            "h": HEAD_H, "lens": "mid",
            "master_seed": SEED,
            "horizons_written_s": list(HORIZONS_S),
            "n_perm": None,
            "n_boot": None,
            "rank_floor_fills": None,
            "persistence_floor_fills": None,
            "whale_drop_k": None,
            "fdr_alpha": None,
            "overrides_note": (
                "this is a PRODUCER: it re-marks every fill at every rung of "
                "settings.LADDER_S and selects no window, applies no wallet floor, "
                "draws no permutation or bootstrap and tests nothing, so those "
                "declarations do not apply to it and are recorded as null rather "
                "than inherited. The seed is settings.MASTER_SEED unchanged. The "
                "sanity comparison at the bottom of this file is measured at the "
                "headline window and at the shortest rung."),
        },
        started=t0)

    # ---- console summary ----
    print("\n" + "=" * 76)
    print("I4 MID-MARKOUT - SUMMARY")
    print("=" * 76)
    def _fmt_bps(x):
        """A null print-twin mean prints as 'not compared', never as a number."""
        return "not compared" if x is None else f"{x:+.4f} bps"

    print(f"  days resolved : {len(resolved)}/{len(bqm.DAYS)} -> {resolved}")
    print(f"  total rows    : {total_rows:,}  "
          f"(row-aligned to print npz: "
          f"{'not compared' if aligned is None else aligned})")
    print(f"  print twin    : {print_arm} "
          f"({os.path.basename(print_npz) if have_shipped else 'no shipped artifact'}"
          f", {'n/a' if rows_shipped is None else format(rows_shipped, ',')} rows)")
    print(f"  rows identical: "
          f"{'not compared' if rows_identical is None else rows_identical}"
          f"  (element-wise; max abs diff "
          f"{'n/a' if max_abs_diff is None else format(max_abs_diff, '.6g')}, "
          f"nan pattern equal "
          f"{'n/a' if nan_pattern_equal is None else nan_pattern_equal})")
    print("  nan-drop      : " + "  ".join(
        f"{k}={nan_drop[k]*100:.1f}%" for k in MO_COLS))
    print(f"  SANITY vw-mean {H.headline_mid_col(HEAD_H)}  = {vw_mo10_mid:+.4f} bps")
    print(f"         vw-mean {H.headline_print_col(HEAD_H)} shipped  = "
          f"{_fmt_bps(vw_mo10_print)}  (expect same order of magnitude, sub-1 to ~1 bps)")
    print(f"         vw-mean {H.headline_print_col(HEAD_H)} this pass= "
          f"{_fmt_bps(vw_mo10_print_this_pass)}  (lens agreement within this run only)")
    if issues:
        print("  ISSUES        :", "; ".join(issues[:8]))
    print(f"  npz     -> {os.path.basename(OUT_NPZ)}")
    print(f"  summary -> {os.path.basename(OUT_SUMMARY)}")
    print("=" * 76)


if __name__ == "__main__":
    # The self-test walks no tape and opens no npz, so the row-by-row comparison can be
    # calibrated without paying for the pass it belongs to.
    if "--selftest" in sys.argv[1:]:
        raise SystemExit(_selftest())
    main()
