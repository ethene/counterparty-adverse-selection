"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-07-29
References: Hyperliquid node-data S3 archive (s3://hl-mainnet-node-data); Hyperliquid
market-data L2 book S3 archive (s3://hyperliquid-archive/market_data); Zenodo 18184441
(Albers et al. 2026). Reads only artifacts already on disk: quickwin_markouts.npz,
quickwin_markouts_mid.npz, panel_markouts.npz, panel_markouts_v2.npz, the panel_ckpt
and panel_ckpt_v2 shards, quickwin_pass_summary.json, and mid_series_*.npz.
"""

# ---------------------------------------------------------------------------
# STEP 1 DATA INVENTORY - the read-only half of run_step1_data.sh.
#
# Nothing here downloads anything and nothing here recomputes a result. It opens
# the acquisition artifacts that are already on disk, measures four things per
# coin-window cell, and compares each against the value this project recorded
# when the cell was built:
#
#   fills      collapsed taker trades in that cell (one row per (hash, taker) sweep)
#   snapshots  L2 book snapshots in that cell
#   med_gap    median spacing between consecutive book snapshots, in seconds
#   coverage   fraction of the window's wall clock with a live snapshot series
#
# WHY COVERAGE AND NOT A FILE COUNT. The 202511 window pulled 720 of 720 expected
# archive files and still covers only about 61 percent of its ten days: the gaps
# are inside the files, not missing files. A book-mid measure computed on that
# window therefore marks two fifths of its trades against a stale reference price.
# A file-count gate cannot see this, so the inventory measures the series itself.
#
# COVERAGE DEFINITION. A window is ten calendar days = 864,000 seconds of wall
# clock. Dead time is the summed duration of every gap between consecutive
# snapshots longer than BOOK_GAP_TOL_S, plus the lead-in from the window start to
# the first snapshot and the tail from the last snapshot to the window end when
# either exceeds the same tolerance. Coverage is one minus dead time over wall
# clock. The tolerance sits far above the 0.54 second median cadence, so ordinary
# spacing never counts as dead time; only a genuine outage does.
#
# Usage:
#   uv run --no-project --with-requirements ../requirements.txt python3 step1_inventory.py
#   uv run --no-project --with-requirements ../requirements.txt python3 step1_inventory.py --hours-gate december
#   uv run --no-project --with-requirements ../requirements.txt python3 step1_inventory.py --hours-gate panel
#
# Exit status: 0 when every present cell agrees with the recorded values, 1 when
# any cell diverges or any gated build is short of a full 24 hours on a day.
# ---------------------------------------------------------------------------

import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))

# The settings module sits in the repository root, one directory up from this group, so
# the path is built from this file's own location and never from the working directory
# the run happens to start in. It declares data, holds no state and starts no fetch,
# which is what the note below rules out.
_CODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CODE_DIR not in sys.path:
    sys.path.insert(0, _CODE_DIR)

import settings as H  # noqa: E402
import panel_io as P  # noqa: E402

# -------------------- the acquisition grid --------------------
# Eight ten-day windows, three coins. Identical to PERIOD_DAYS in
# panel_persistence.py and to the window list in run_panel_l2.sh; repeated here as
# plain data so the inventory never imports a builder and never triggers a fetch.
PERIODS = (202508, 202509, 202510, 202511, 202512, 202601, 202603, 202605)
# The coins and their codes belong to the FILE being inventoried. This inventory walks
# the PANEL artifacts, which carry {0, 1, 2}; the December quickwin artifact carries
# {0, 1} and agrees with the panel on the two codes it does hold.
COINS = tuple(sym for _, sym in sorted(H.coin_labels("panel").items()))
COIN_CODE = H.coin_codes("panel")
WINDOW_FIRST_DAY = {
    202508: "20250804", 202509: "20250904", 202510: "20251006", 202511: "20251104",
    202512: "20251204", 202601: "20260104", 202603: "20260304", 202605: "20260504",
}
WINDOW_DAYS = 10
WALL_CLOCK_S = WINDOW_DAYS * 86400.0          # 864,000 s per window
DECEMBER_PERIOD = 202512                      # the headline window

# -------------------- recorded expectations --------------------
# Every number below was measured from the build on the machine that produced the
# committed results. A reviewer's own pull is compared against them cell by cell.

# Collapsed taker trades per coin-window, as held by panel_markouts.npz.
EXPECTED_FILLS = {
    "BTC": (814777, 727516, 1721332, 2022864, 1200863, 1118856, 1947220, 1651847),
    "ETH": (1462641, 1010559, 1614791, 1630961, 1279404, 858925, 843482, 651023),
    "SOL": (733734, 635744, 1120170, 862100, 507417, 565922, 559914, 493840),
}
EXPECTED_PANEL_ROWS = 26035902                # sum of EXPECTED_FILLS
EXPECTED_DECEMBER_ROWS = 2480267              # quickwin_markouts.npz, BTC+ETH

# The v2 rebuild (panel_rebuild_v2.py, which additionally carries block_time_ns and
# is_liq) covers the same grid but its three 202511 cells came out 14,020 rows
# short: its shards record "202511 20251110: 23/24 hours", while the v1 build of
# that same day holds all 24. The missing hour is 21:00 to 22:00 UTC on 2025-11-10
# and the shortfall splits BTC 6,472, ETH 5,032, SOL 2,516. The hour was lost on
# the pull, not absent from the archive: the v2 builder accepts a day once 20 of
# its 24 hourly objects land, so 23 of 24 passed without a retry.
#
# Two further facts about the gap. No row exists in v2 that is absent from v1, so
# nothing was gained in the rebuild. And 349 trades in the minute before the gap
# carry a 60 second markout measured against the first print after it, because the
# join takes the first print at or after the horizon; the shift on those rows
# averages 7 to 9 bps and reaches 23. Thirty-two rows are affected at 10 seconds
# and none at 1 second. Read the 202511 row counts and markouts from the v1 build.
#
# This is the exact failure this runner exists to catch, so both sets of numbers
# are recorded rather than one being quietly preferred.
EXPECTED_FILLS_V2 = {
    "BTC": (814777, 727516, 1721332, 2016392, 1200863, 1118856, 1947220, 1651847),
    "ETH": (1462641, 1010559, 1614791, 1625929, 1279404, 858925, 843482, 651023),
    "SOL": (733734, 635744, 1120170, 859584, 507417, 565922, 559914, 493840),
}
EXPECTED_PANEL_V2_ROWS = 26021882

# L2 book snapshots per coin-window.
EXPECTED_SNAPSHOTS = {
    "BTC": (1579970, 1579063, 1578358, 962736, 1572177, 1510054, 1521329, 1556724),
    "ETH": (1579971, 1579055, 1578371, 964259, 1572228, 1510147, 1521371, 1556765),
    "SOL": (1579953, 1579029, 1578347, 965475, 1572259, 1510163, 1521373, 1556723),
}

# Book coverage per coin and window, in percent, measured at BOOK_GAP_TOL_S below.
# Keyed per coin rather than per window because 202511 spreads 0.17 points across
# the three instruments while every other window agrees to a hundredth, and a
# single stand-in value there would be checked against a number no coin produces.
#
# The 202511 figure is a property of the exchange archive and not of the download.
# Three observations establish that. No hour file failed to arrive, since
# i4_l2_mid.py abandons a whole hour on a fetch failure and all 240 hours carry
# snapshots on all three coins. The objects that arrived are not truncated: dead
# time is spread evenly through the hour, 14.8 percent of it in the first ten
# minutes against 16.6 in the last, and the final snapshot of an hour sits at a
# median 0.9999 of the way through it. And all 720 of the window's hourly objects
# were re-fetched from the archive and read line by line: it holds 963,631 records
# for BTC, 965,151 for ETH and 966,404 for SOL, and every one of them parses, with
# no line unreadable and no snapshot rejected for an empty side. Whatever the
# archive published, we hold. Fourth, the recording rate is unstable in a way a
# sound window's is not: per hour and against the window's own median, October
# spans 0.96 to 1.00 and December 0.95 to 1.01, while November spans 0.44 to 1.75.
#
# Cross-coin synchrony is true and proves nothing, in either direction. Healthy
# October matches 52 of its 52 gap-start minutes across all three coins, and the
# per-hour densities of the three coins correlate at 0.9999 in October, December
# and November alike, because one recorder writes all three.
EXPECTED_COVERAGE_PCT = {
    "BTC": (99.76, 99.95, 99.94, 60.73, 99.91, 96.29, 96.97, 97.30),
    "ETH": (99.77, 99.95, 99.94, 60.83, 99.91, 96.30, 96.97, 97.31),
    "SOL": (99.76, 99.94, 99.94, 60.90, 99.91, 96.30, 96.97, 97.30),
}
EXPECTED_MEDIAN_GAP_S = 0.54                  # every window, every coin

# -------------------- agreement tolerances --------------------
BOOK_GAP_TOL_S = 2.0          # a gap longer than this counts as dead time
FILLS_TOL = 0                 # a complete pull is deterministic to the row
SNAPSHOT_REL_TOL = 0.005      # 0.5 percent of the recorded count
COVERAGE_TOL_PCT = 0.05       # percentage points; per-coin expectations are exact
                              # to a hundredth, so the slack that once hid a
                              # cross-coin spread is no longer needed
MEDIAN_GAP_TOL_S = 0.05       # seconds
THIN_BOOK_PCT = 95.0          # below this a cell is flagged unfit for a book measure

# -------------------- artifact paths --------------------
# The four markout panels are LOCATED by panel_io, so the one place that knows where they
# live is the one place that has to change if they move. With none of the environment
# variables panel_io honours set, data_root() returns the directory the module lives in,
# which is this file's own directory -- the value HERE had on these four lines before --
# so every row of the inventory below reads the same file it read then.
#
# The np.load calls further down stay where they are: build.py derives an input edge by
# folding the argument of np.load to a constant, and a path it cannot fold makes no edge
# at all. What moves here is the DIRECTORY, not the load.
#
# The two checkpoint directories and the book series keep joining against HERE, because
# they are not panels and panel_io is about panels.
PANEL_NPZ = os.path.join(P.data_root(), "panel_markouts.npz")
PANEL_V2_NPZ = os.path.join(P.data_root(), "panel_markouts_v2.npz")
QUICKWIN_NPZ = os.path.join(P.data_root(), "quickwin_markouts.npz")
QUICKWIN_MID_NPZ = os.path.join(P.data_root(), "quickwin_markouts_mid.npz")
QUICKWIN_SUMMARY = os.path.join(HERE, "quickwin_pass_summary.json")
PANEL_CKPT = os.path.join(P.data_root(), "panel_ckpt")
PANEL_CKPT_V2 = os.path.join(P.data_root(), "panel_ckpt_v2")


def mid_series_path(coin, period):
    """Panel book artifact for one coin-window (run_panel_l2.sh writes these)."""
    return os.path.join(P.data_root(), f"mid_series_{coin}_{period}.npz")


def december_mid_path(coin):
    """December book artifact written without a suffix by run_i4.sh."""
    return os.path.join(P.data_root(), f"mid_series_{coin}.npz")


# ===========================================================================
# measurement
# ===========================================================================
def window_bounds_ms(period):
    """Epoch-millisecond start and end of a window's ten-day wall clock."""
    d = WINDOW_FIRST_DAY[period]
    start = int(np.datetime64(f"{d[:4]}-{d[4:6]}-{d[6:8]}T00:00:00", "ms").astype("int64"))
    return start, start + int(WINDOW_DAYS * 86400 * 1000)


def read_columns(path, columns):
    """Named columns of an npz, or None when the file is absent or unreadable.

    A file that exists but fails to load is named in a warning rather than raised.
    A truncated npz left by an interrupted write is a real state this runner will
    meet, and a traceback is a poor way to describe it.
    """
    if not os.path.exists(path):
        return None
    try:
        with np.load(path, allow_pickle=False) as z:
            return {c: z[c] for c in columns}
    except Exception as exc:                      # noqa: BLE001 - report, do not crash
        print(f"  [warn] {os.path.basename(path)} exists but could not be read: {exc}")
        return None


def measure_book(path, period):
    """Snapshot count, median interval and wall-clock coverage for one book file.

    Returns None when the file is absent or unreadable. Reads only the t_ms
    column, so the four price columns are never decompressed.
    """
    cols = read_columns(path, ["t_ms"])
    if cols is None:
        return None
    t_ms = cols["t_ms"]
    n = int(t_ms.size)
    if n < 2:
        return {"n": n, "median_gap_s": float("nan"), "coverage_pct": 0.0}

    t0, t1 = window_bounds_ms(period)
    gaps_s = np.diff(t_ms) / 1000.0
    lead_s = (int(t_ms[0]) - t0) / 1000.0
    tail_s = (t1 - int(t_ms[-1])) / 1000.0

    dead_s = float(gaps_s[gaps_s > BOOK_GAP_TOL_S].sum())
    if lead_s > BOOK_GAP_TOL_S:
        dead_s += lead_s
    if tail_s > BOOK_GAP_TOL_S:
        dead_s += tail_s

    return {"n": n,
            "median_gap_s": float(np.median(gaps_s)),
            "coverage_pct": 100.0 * (1.0 - dead_s / WALL_CLOCK_S)}


def measure_panel_fills(path):
    """Rows per (coin, window) plus the row total, from a panel npz.

    Returns (cells, total), or (None, None) when the file is absent or unreadable.
    Only the coin and period columns are read.
    """
    cols = read_columns(path, ["coin", "period"])
    if cols is None:
        return None, None
    coin = cols["coin"]
    period = cols["period"]
    cells = {}
    for c in COINS:
        code = COIN_CODE[c]
        for p in PERIODS:
            cells[(c, p)] = int(np.count_nonzero((coin == code) & (period == p)))
    return cells, int(coin.size)


def npz_rows(path, column):
    """Row count of one column, or None when the file is absent or unreadable."""
    cols = read_columns(path, [column])
    return None if cols is None else int(cols[column].size)


# ===========================================================================
# the inventory table
# ===========================================================================
def cell_status(fills, fills_exp, book, snap_exp, cov_exp):
    """One cell's verdict: agreement, divergence, or an absent input.

    Returns (status text, ok flag). A cell is ok when every present measure sits
    inside its tolerance. Thin book coverage is appended as a warning even when the
    cell agrees with the record, because agreement and fitness for use are two
    different questions.
    """
    notes = []
    ok = True

    if fills is None:
        notes.append("no fills")
        ok = False
    elif abs(fills - fills_exp) > FILLS_TOL:
        notes.append(f"fills {fills - fills_exp:+,}")
        ok = False

    if book is None:
        notes.append("no book")
        ok = False
    else:
        if abs(book["n"] - snap_exp) > SNAPSHOT_REL_TOL * snap_exp:
            notes.append(f"snapshots {book['n'] - snap_exp:+,}")
            ok = False
        if abs(book["median_gap_s"] - EXPECTED_MEDIAN_GAP_S) > MEDIAN_GAP_TOL_S:
            notes.append(f"cadence {book['median_gap_s']:.3f}s")
            ok = False
        if abs(book["coverage_pct"] - cov_exp) > COVERAGE_TOL_PCT:
            notes.append(f"coverage {book['coverage_pct']:.2f} vs {cov_exp:.2f}")
            ok = False

    text = "ok" if not notes else ", ".join(notes)
    if book is not None and book["coverage_pct"] < THIN_BOOK_PCT:
        text += "  [book thin]"
    return text, ok


def print_inventory():
    """Print the per-cell table plus the artifact cross-checks and the census.

    Returns True when everything present agrees with the recorded values.
    """
    print("=" * 104)
    print("STEP 1 DATA INVENTORY - reads what is on disk, downloads nothing")
    print("=" * 104)
    print(f"Book coverage is the fraction of a window's {WALL_CLOCK_S:,.0f} s wall clock with a live")
    print(f"snapshot series; a gap longer than {BOOK_GAP_TOL_S:.1f} s counts as dead time. Cadence is the")
    print("median spacing between consecutive snapshots. Expected values were measured on the")
    print("build that produced the committed results.")
    print("")

    panel_cells, panel_total = measure_panel_fills(PANEL_NPZ)
    if panel_cells is None:
        print(f"  {os.path.basename(PANEL_NPZ)} absent or unreadable - the fills columns "
              f"below stay empty.")
        print("")

    header = (f"{'coin':<4}  {'window':<6}  {'fills':>11}  {'expected':>11}  "
              f"{'snapshots':>11}  {'expected':>11}  {'cadence':>7}  "
              f"{'cover%':>7}  {'expect':>7}  status")
    print(header)
    print("-" * 104)

    all_ok = True
    census_both, census_fills_only, census_thin = [], [], []

    for c in COINS:
        for i, p in enumerate(PERIODS):
            fills = None if panel_cells is None else panel_cells[(c, p)]
            fills_exp = EXPECTED_FILLS[c][i]
            snap_exp = EXPECTED_SNAPSHOTS[c][i]
            cov_exp = EXPECTED_COVERAGE_PCT[c][i]
            book = measure_book(mid_series_path(c, p), p)

            status, ok = cell_status(fills, fills_exp, book, snap_exp, cov_exp)
            all_ok = all_ok and ok

            if fills is not None and book is not None:
                census_both.append((c, p))
            elif fills is not None:
                census_fills_only.append((c, p))
            if book is not None and book["coverage_pct"] < THIN_BOOK_PCT:
                census_thin.append((c, p, book["coverage_pct"]))

            f_txt = "-" if fills is None else f"{fills:,}"
            n_txt = "-" if book is None else f"{book['n']:,}"
            g_txt = "-" if book is None else f"{book['median_gap_s']:.3f}"
            v_txt = "-" if book is None else f"{book['coverage_pct']:.2f}"
            print(f"{c:<4}  {p:<6}  {f_txt:>11}  {fills_exp:>11,}  "
                  f"{n_txt:>11}  {snap_exp:>11,}  {g_txt:>7}  "
                  f"{v_txt:>7}  {cov_exp:>7.2f}  {status}")
        print("")

    all_ok = _print_fills_crosschecks(panel_cells, panel_total) and all_ok
    all_ok = _print_book_crosschecks() and all_ok
    _print_census(census_both, census_fills_only, census_thin)
    return all_ok


def _mark(ok):
    return "ok" if ok else "DIVERGES"


def _print_fills_crosschecks(panel_cells, panel_total):
    """Artifact-level fills checks that no single cell can express."""
    print("fills artifacts")
    print("-" * 104)
    ok = True

    if panel_total is None:
        print(f"  {'panel_markouts.npz':<28} absent or unreadable")
        ok = False
    else:
        hit = panel_total == EXPECTED_PANEL_ROWS
        print(f"  {'panel_markouts.npz':<28} {panel_total:>12,} rows  "
              f"expected {EXPECTED_PANEL_ROWS:>12,}  {_mark(hit)}")
        ok = ok and hit

    v2_cells, v2_total = measure_panel_fills(PANEL_V2_NPZ)
    if v2_total is None:
        print(f"  {'panel_markouts_v2.npz':<28} absent or unreadable")
    else:
        hit = v2_total == EXPECTED_PANEL_V2_ROWS
        print(f"  {'panel_markouts_v2.npz':<28} {v2_total:>12,} rows  "
              f"expected {EXPECTED_PANEL_V2_ROWS:>12,}  {_mark(hit)}")
        ok = ok and hit
        short = [(c, p) for c in COINS for i, p in enumerate(PERIODS)
                 if v2_cells[(c, p)] != EXPECTED_FILLS[c][i]]
        if short:
            gap = EXPECTED_PANEL_ROWS - v2_total
            wins = ", ".join(str(p) for p in sorted({p for _, p in short}))
            print(f"      the v2 rebuild is {gap:,} rows short of the v1 build in "
                  f"{len(short)} cells, all in {wins}.")
            print("      Its shards record 23 of 24 hours on one day of that window,")
            print("      while the v1 build of the same day holds all 24, so the hour")
            print("      was lost on the pull. Carry block_time_ns and is_liq from v2,")
            print("      but read that window's row counts from v1.")

    dec = npz_rows(QUICKWIN_NPZ, "taker_id")
    if dec is None:
        print(f"  {'quickwin_markouts.npz':<28} absent or unreadable")
        ok = False
    else:
        hit = dec == EXPECTED_DECEMBER_ROWS
        print(f"  {'quickwin_markouts.npz':<28} {dec:>12,} rows  "
              f"expected {EXPECTED_DECEMBER_ROWS:>12,}  {_mark(hit)}")
        ok = ok and hit
        if panel_cells is not None:
            pan_dec = panel_cells[("BTC", DECEMBER_PERIOD)] + panel_cells[("ETH", DECEMBER_PERIOD)]
            hit = pan_dec == dec
            print(f"  {'  vs panel 202512 BTC+ETH':<28} {pan_dec:>12,} rows  "
                  f"{'same tape, same parse':>21}  {_mark(hit)}")
            ok = ok and hit

    mid = npz_rows(QUICKWIN_MID_NPZ, "taker_id")
    if mid is None:
        print(f"  {'quickwin_markouts_mid.npz':<28} absent or unreadable")
        ok = False
    elif dec is not None:
        hit = mid == dec
        print(f"  {'quickwin_markouts_mid.npz':<28} {mid:>12,} rows  "
              f"{'row-aligned to fills':>21}  {_mark(hit)}")
        ok = ok and hit
    print("")
    return ok


def _print_book_crosschecks():
    """The December book is pulled by two different runners; they must agree."""
    print("book artifacts")
    print("-" * 104)
    ok = True
    for c in ("BTC", "ETH"):
        standalone = december_mid_path(c)
        panelled = mid_series_path(c, DECEMBER_PERIOD)
        if not os.path.exists(standalone) or not os.path.exists(panelled):
            print(f"  mid_series_{c}.npz or its 202512 companion absent")
            ok = False
            continue
        try:
            with np.load(standalone, allow_pickle=False) as a, \
                 np.load(panelled, allow_pickle=False) as b:
                same = (sorted(a.files) == sorted(b.files)
                        and all(np.array_equal(a[k], b[k]) for k in a.files))
                n = int(a["t_ms"].size)
        except Exception as exc:                  # noqa: BLE001 - report, do not crash
            print(f"  mid_series_{c}.npz or its 202512 companion could not be read: {exc}")
            ok = False
            continue
        print(f"  mid_series_{c}.npz{'':<10} {n:>12,} snapshots  "
              f"{'identical to _202512':>21}  {_mark(same)}")
        ok = ok and same
    print("")
    return ok


def _print_census(both, fills_only, thin):
    """The one thing to know before trusting a number built on a cell."""
    total = len(COINS) * len(PERIODS)
    print("cell census")
    print("-" * 104)
    print(f"  {len(both)} of {total} coin-window cells carry both fills and book.")
    if fills_only:
        print(f"  {len(fills_only)} cells carry fills only, so no book-mid measure can be "
              f"built on them:")
        for c, p in fills_only:
            print(f"      {c} {p}")
    else:
        print("  0 cells carry fills only.")
    if thin:
        print(f"  {len(thin)} cells have book coverage below {THIN_BOOK_PCT:.0f} percent. Fills and "
              f"trade-print markouts on these are")
        print("  sound, but a book-mid measure marks part of the window against a stale "
              "reference price:")
        for c, p, v in thin:
            print(f"      {c} {p} at {v:.2f} percent")
    else:
        print(f"  0 cells have book coverage below {THIN_BOOK_PCT:.0f} percent.")
    print("")


# ===========================================================================
# hours gate - run after a stage builds, never on a stage that was skipped
# ===========================================================================
def gate_december():
    """Fail when any December day was parsed with fewer than 24 hourly files."""
    if not os.path.exists(QUICKWIN_SUMMARY):
        print(f"[gate] {os.path.basename(QUICKWIN_SUMMARY)} absent - cannot confirm "
              f"the December fills pull was complete.")
        return False
    with open(QUICKWIN_SUMMARY) as fh:
        summary = json.load(fh)
    hours = summary.get("hours_by_day", {})
    short = {d: len(h) for d, h in hours.items() if len(h) < 24}
    missing = [d for d in summary.get("config", {}).get("days_requested", [])
               if d not in hours]
    if short or missing:
        for d, n in sorted(short.items()):
            print(f"[gate] December fills: {d} parsed {n} of 24 hours.")
        for d in missing:
            print(f"[gate] December fills: {d} absent entirely.")
        print("[gate] A short day yields a short series that looks complete. "
              "Re-run the stage rather than building anything derived from it.")
        return False
    print(f"[gate] December fills: {len(hours)} days, 24 of 24 hours on each.")
    return True


def _gate_shards(ckpt_dir, label):
    """Fail when any panel shard records a day short of 24 hours."""
    if not os.path.isdir(ckpt_dir):
        print(f"[gate] {label}: checkpoint dir {os.path.basename(ckpt_dir)} absent.")
        return False
    shards = sorted(f for f in os.listdir(ckpt_dir)
                    if f.startswith("shard_") and f.endswith(".npz"))
    if not shards:
        print(f"[gate] {label}: no shards in {os.path.basename(ckpt_dir)}.")
        return False
    bad = []
    for sf in shards:
        try:
            with np.load(os.path.join(ckpt_dir, sf), allow_pickle=True) as z:
                issues = [str(x) for x in z["_issues"].tolist()]
                resolved = [str(x) for x in z["_resolved_days"].tolist()]
        except Exception as exc:                  # noqa: BLE001 - report, do not crash
            bad.append(f"{sf}: unreadable ({exc})")
            continue
        for msg in issues:
            if "hours" in msg:
                bad.append(f"{sf}: {msg}")
        if len(resolved) < WINDOW_DAYS:
            bad.append(f"{sf}: {len(resolved)} of {WINDOW_DAYS} days resolved")
    if bad:
        for line in bad:
            print(f"[gate] {label}: {line}")
        print(f"[gate] {label}: a window short of a full day is not built, it is "
              f"re-pulled.")
        return False
    print(f"[gate] {label}: {len(shards)} shards, 10 days and 24 hours each.")
    return True


def gate_panel():
    """Both panel builds must hold complete windows before anything reads them."""
    v1 = _gate_shards(PANEL_CKPT, "panel fills v1")
    v2 = _gate_shards(PANEL_CKPT_V2, "panel fills v2")
    return v1 and v2


def main():
    args = sys.argv[1:]
    if args and args[0] == "--hours-gate":
        what = args[1] if len(args) > 1 else ""
        if what == "december":
            sys.exit(0 if gate_december() else 1)
        if what == "panel":
            sys.exit(0 if gate_panel() else 1)
        print("usage: step1_inventory.py --hours-gate {december|panel}")
        sys.exit(2)

    ok = print_inventory()
    if ok:
        print("VERDICT: every cell and artifact on disk matches the recorded values.")
    else:
        print("VERDICT: at least one cell or artifact diverges from the recorded "
              "values, or is absent. Read the status column above.")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
