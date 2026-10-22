#!/usr/bin/env python3
"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-08-26
References: Hyperliquid Level-4 order-book archive, Zenodo 18184441 (Albers et al.
2026); the local snapshot reader i4_l2_mid.py, whose decompression and path rules this
file calls rather than restates; identity/i3_book_comparator.py, which produced the
depth columns this file reproduces independently; Glosten and Milgrom (1985) on the
quoted spread as the price of adverse selection.

THE DATA ITSELF, WHICH NO OTHER FIGURE OF THE REPORT SHOWS.

Five figures carry the argument and every one of them is a result: a markout curve, a
counterparty ranking, a decile ledger, a book-against-identity contrast, a quoter
bake-off. Not one shows the raw material those results are computed from. A reader who
wants to know what a Hyperliquid order book looks like, how deep it is, how wide it
quotes and whether the ten-day window is one market or several has nowhere to look. This
figure is that place, and it is deliberately not a result: nothing here is an outcome of
any decision the report makes.

THE LEFT PANEL IS THE BOOK. Horizontally, distance from the mid price in basis points,
bids to the left and asks to the right, so the two sides face each other the way they do
on a screen. Vertically, the median resting notional standing within that distance, in
millions of dollars. Both coins on one pair of axes, because the comparison is half the
point: BTC's twenty visible levels are exhausted inside 2.1 basis points of the mid while
ETH's reach out to 6.1, so the same twenty rungs describe a book five times tighter in
relative terms on one coin than on the other.

THE RIGHT PANEL IS THE WINDOW. Hourly median quoted spread in basis points across all ten
days, both coins, with the boundary between the two halves of the window drawn and named.
That boundary carries the weight of the whole study: counterparties are ranked on the
first half and every economic figure is measured on the second, and the split is only
sound if the two halves are the same market. A reader can now see that rather than take
it. What the panel shows is a window with no regime break at the cut: the medians of the
two halves sit within a few hundredths of a basis point of each other on both coins, and
what movement there is sits inside days rather than between halves.

WHY THE RAW SNAPSHOTS WERE PARSED INSTEAD OF THE DERIVED FEATURE FILE, and this was a
measurement rather than a preference. book_feats_{COIN}.npz carries resting depth at two
distances, 5 and 10 basis points, which would give a ladder of two rungs. Measured across
all 1,572,177 BTC rows, those two columns are EQUAL on 99.93 per cent of them -- because
the entire visible BTC book ends around 2.1 basis points from the mid, so both rungs
enclose the whole of it and the second says nothing the first did not. On ETH the same
pair differs by a factor of 1.31. A two-rung ladder is therefore a ONE-rung ladder on one
of the two coins, and it would draw a book shape that is an artifact of where the rungs
were placed. The raw snapshots carry twenty levels a side, which is the shape itself. The
cost of reading every one of them, all ten days and all twenty-four hours of each, is
about two and a half minutes, measured before the decision was taken and printed again by
every run.

HOW THIS FILE PROVES IT READ THE BOOK CORRECTLY, rather than asserting that it did. The
same pass that builds the ladder also recomputes, from the raw levels, the four depth
columns that identity/i3_book_comparator.py wrote into book_feats_{COIN}.npz weeks ago,
and compares them snapshot by snapshot against the committed artifact. Two producers that
never shared a line of code have to agree on 6.3 million numbers per coin, and the run
refuses to draw if they do not. That is a stronger statement than any internal assertion
could be: a misread ladder cannot reproduce a column it did not compute.

WHAT THE MEDIAN IS OVER, because the answer is not "time". The venue emits a snapshot when
the book changes, so a busy minute contributes more snapshots than a quiet one, and the
median here is the median SNAPSHOT rather than the median second. Both are defensible and
they are different quantities; this one is named so that nobody has to guess which was
drawn. The per-day counts are written to the results file so the weighting is visible.

DRAWN AT THE SIZE IT IS PRINTED. The canvas matches the four figures already assembled --
5.53 inches wide, the width of the report's single text column, at 200 dots per inch --
so every point size below is the size a reader of the page sees.

Run command (bare python3 is BLOCKED on this machine):
  uv run --no-project --with-requirements requirements.txt python3 -u \
      data/d1_book_shape_figure.py
"""
import datetime
import json
import os
import re
import sys
import time

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# artifact.py, settings.py and the snapshot reader sit in the repository root, one
# directory up from this group, so every path below is built from this file's own
# location and never from the working directory the run happens to start in.
_CODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CODE_DIR not in sys.path:
    sys.path.insert(0, _CODE_DIR)

import artifact                                                         # noqa: E402
import settings as H                                                    # noqa: E402
# The lz4 decoder and the cache path rule are CALLED, not restated. i4_l2_mid.py is the
# file that established how a snapshot hour is located and decompressed in this tree; a
# second copy of either would be free to drift away from it silently, and a figure drawn
# from a drifted copy would look exactly like a figure drawn from the real one.
import i4_l2_mid as L2                                                  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_PNG = os.path.join(HERE, "d1_book_shape.png")
OUT_JSON = os.path.join(HERE, "d1_book_shape_figure_results.json")

T0 = artifact.start_clock()

# The printed geometry, in one place, matching the four figures already assembled.
WIDTH_IN, HEIGHT_IN, DPI_OUT = 5.53, 3.4, 200
PT_LABEL, PT_TITLE, PT_LEGEND, PT_NOTE = 8, 9, 7.5, 6.8
plt.rcParams.update({"font.size": PT_LABEL,
                     "axes.labelsize": PT_LABEL,
                     "axes.titlesize": PT_TITLE,
                     "xtick.labelsize": PT_LABEL,
                     "ytick.labelsize": PT_LABEL,
                     "legend.fontsize": PT_LEGEND})

# --------------------------------------------------------------------------
# What is read. Every one of these is asked for by STORE rather than typed: the
# coins come from the declaration of what the snapshot cache carries, and the days
# and hours come from the reader that built the cache in the first place.
# --------------------------------------------------------------------------
COINS = list(H.coin_symbols("l2_cache"))
DAYS = list(L2.DEFAULT_DAYS)
HOURS = list(L2.DEFAULT_HOURS)
N_CELLS_EXPECTED = len(DAYS) * len(HOURS) * len(COINS)

# The distance grid of the left panel. A quarter of a basis point is finer than one
# tick on either coin (BTC's tick is 0.107 bps at these prices, ETH's 0.313), so the
# grid never merges two rungs of the ladder into one point. It runs to 8 because the
# deepest visible ETH level measured over the window sits at 8.6 and the median at 6.1.
EDGES_BPS = np.round(np.arange(0.25, 8.0001, 0.25), 4)

# Depth agreement with the committed artifact. The two producers are independent and
# both go through float, so exact equality is not the right bar; a relative gap of 1e-9
# is fifteen orders of magnitude tighter than any depth difference that could change the
# picture, and loose enough that the last bit of a float sum does not stop a run.
DEPTH_RTOL = 1e-9
# How many snapshots may disagree beyond that before the run refuses to draw. Zero: two
# producers reading the same bytes under the same rule have no licence to differ at all,
# and a floor above zero would let a real disagreement hide under a tolerance.
DEPTH_MAX_BAD = 0

# How much of a side counts as "the book has ended" for the marker on the left panel and
# for the distance reported beside it. Ninety-nine per cent, declared here rather than
# chosen per coin: the last per cent of a side sits in single levels that appear and
# vanish between snapshots, so the maximum of the curve is a distance nobody quoting into
# this book would call its edge.
BOOK_END_SHARE = 0.99

# The caption is measured, not eyeballed. Our figure captions run twelve to nineteen
# words and this one is held to that range by an assertion rather than by counting once.
CAPTION_MIN_WORDS, CAPTION_MAX_WORDS = 12, 19
CAPTION = ("Resting notional by distance from the mid on both coins, and hourly "
           "quoted spread either side of the split.")


def _require(condition, what):
    """Refuse to draw rather than draw a picture whose premise is false.

    A figure that quietly draws a broken premise is worse than one that does not draw:
    the picture reaches the report and the premise never does.
    """
    if not condition:
        raise SystemExit(f"[d1] refusing to draw: {what}")


def say(text):
    """One progress line, unbuffered, so a run of minutes is watchable from outside."""
    print(f"[d1] {text}", flush=True)


# ==========================================================================
# 1. THE CACHE: WHAT IS THERE, AND A PREDICATE THAT HAS BEEN SHOWN TO WORK
# ==========================================================================

def have_cell(day, hour, coin):
    """Whether one hour of one coin is on disk, by the path rule the reader uses.

    The path is built by i4_l2_mid.local_path rather than joined here, so this
    predicate cannot answer a question about a directory layout the reader does not
    use. `present` means a file that exists AND carries bytes: a zero-length file is
    the shape a failed download leaves behind, and counting it as present is how a
    short read becomes an unremarked gap in a picture.
    """
    path = L2.local_path(day, str(hour), coin)
    return os.path.exists(path) and os.path.getsize(path) > 0, path


def calibrate_presence():
    """Two opposite cases for the presence predicate, both drawn from the live cache.

    A predicate that answers "no" to everything reports an empty cache as cleanly as a
    correct one does, and this file would then draw a book from whatever it happened to
    find without ever saying what it missed. So before any count is believed, the
    predicate is shown a case it MUST find and three it MUST NOT, and the three are the
    three ways a cell can fail to exist: a day outside the window on either side, and a
    coin the cache does not carry.
    """
    must_find = [(DAYS[0], HOURS[0], COINS[0]), (DAYS[-1], HOURS[-1], COINS[-1])]
    # The day before the window opens and the day after it closes, derived from the
    # declared window rather than typed, so the case follows the window if it moves.
    before = (datetime.datetime.strptime(DAYS[0], "%Y%m%d")
              - datetime.timedelta(days=1)).strftime("%Y%m%d")
    after = (datetime.datetime.strptime(DAYS[-1], "%Y%m%d")
             + datetime.timedelta(days=1)).strftime("%Y%m%d")
    must_miss = [(before, HOURS[0], COINS[0]), (after, HOURS[0], COINS[0]),
                 (DAYS[0], HOURS[0], "SOL")]

    cases = []
    for day, hour, coin in must_find:
        found, path = have_cell(day, hour, coin)
        cases.append({"case": f"{day}/{hour}/{coin}", "expected": "present",
                      "found": bool(found), "why": "inside the declared window"})
        _require(found, f"the presence predicate cannot find {day}/{hour}/{coin}, "
                        f"which the declared window says must be there; the cache is "
                        f"not where {os.path.basename(path)} is looked for")
    for day, hour, coin in must_miss:
        found, _ = have_cell(day, hour, coin)
        why = ("a day outside the declared window" if coin == COINS[0] and day != DAYS[0]
               else "a coin the snapshot cache does not carry")
        cases.append({"case": f"{day}/{hour}/{coin}", "expected": "absent",
                      "found": bool(found), "why": why})
        _require(not found, f"the presence predicate reports {day}/{hour}/{coin} as "
                            f"present, and it cannot be: it is outside what the cache "
                            f"declares it holds, so the predicate answers yes to "
                            f"everything and no count taken with it means anything")
    return cases


def census_cache():
    """Every cell the window declares, and whether it is on disk. A gap is a finding."""
    present, missing = [], []
    for day in DAYS:
        for hour in HOURS:
            for coin in COINS:
                found, path = have_cell(day, hour, coin)
                (present if found else missing).append(
                    {"day": day, "hour": hour, "coin": coin,
                     "file": os.path.relpath(path, _CODE_DIR)})
    return present, missing


# ==========================================================================
# 2. THE LADDER, READ FROM THE RAW SNAPSHOTS
# ==========================================================================

def ladder_of_file(path, edges, depth_k):
    """One hour of one coin: per snapshot, the cumulative book on each side.

    Returns t_ms, cumulative NOTIONAL within each edge for bids and asks, and
    cumulative SIZE within each of `depth_k` basis points for bids and asks. The second
    pair exists only to be held against book_feats_{COIN}.npz afterwards.

    The parse mirrors what both existing readers do -- obj["raw"]["data"], levels[0] are
    bids and levels[1] are asks, prices and sizes through float -- and that orientation
    is not assumed here on faith: checks/chk_book_orientation.py grounds it
    non-circularly by testing that the two ladders run in opposite directions.

    The cumulative sums are taken with searchsorted over the levels AS THEY ARRIVE,
    which is sound because a bid ladder descends in price and an ask ladder ascends, so
    both are already sorted ascending in DISTANCE from the mid. That ordering is
    asserted per snapshot rather than trusted, because everything below it would be
    silently wrong if a snapshot ever arrived out of order.
    """
    raw = L2.decompress(path)
    if raw is None:
        return None
    lines = raw.split(b"\n")
    n_lines = sum(1 for ln in lines if ln)

    t_out = np.empty(n_lines, dtype=np.int64)
    nb_out = np.empty((n_lines, edges.size), dtype=np.float32)
    na_out = np.empty((n_lines, edges.size), dtype=np.float32)
    db_out = np.empty((n_lines, len(depth_k)), dtype=np.float64)
    da_out = np.empty((n_lines, len(depth_k)), dtype=np.float64)
    kbps = np.asarray(depth_k, dtype=np.float64)

    n = 0
    skipped = 0
    unsorted = 0
    for line in lines:
        if not line:
            continue
        try:
            data = json.loads(line)["raw"]["data"]
            t_ms = int(data["time"])
            bids, asks = data["levels"][0], data["levels"][1]
            if not bids or not asks:
                skipped += 1
                continue
            bpx = np.fromiter((float(lv["px"]) for lv in bids), np.float64, len(bids))
            bsz = np.fromiter((float(lv["sz"]) for lv in bids), np.float64, len(bids))
            apx = np.fromiter((float(lv["px"]) for lv in asks), np.float64, len(asks))
            asz = np.fromiter((float(lv["sz"]) for lv in asks), np.float64, len(asks))
        except (ValueError, KeyError, IndexError, TypeError):
            skipped += 1
            continue

        mid = 0.5 * (bpx[0] + apx[0])
        if not (mid > 0):
            skipped += 1
            continue

        dist_b = (mid - bpx) * (1e4 / mid)
        dist_a = (apx - mid) * (1e4 / mid)
        if not (np.all(np.diff(dist_b) >= 0) and np.all(np.diff(dist_a) >= 0)):
            # A ladder that does not run monotonically away from the mid breaks the
            # premise of every cumulative sum below. Counted and skipped rather than
            # silently summed, and reported by the caller.
            unsorted += 1
            continue

        cum_nb = np.cumsum(bpx * bsz)
        cum_na = np.cumsum(apx * asz)
        cum_sb = np.cumsum(bsz)
        cum_sa = np.cumsum(asz)

        ib = np.searchsorted(dist_b, edges, side="right")
        ia = np.searchsorted(dist_a, edges, side="right")
        nb_out[n] = np.where(ib > 0, cum_nb[np.maximum(ib - 1, 0)], 0.0)
        na_out[n] = np.where(ia > 0, cum_na[np.maximum(ia - 1, 0)], 0.0)

        jb = np.searchsorted(dist_b, kbps, side="right")
        ja = np.searchsorted(dist_a, kbps, side="right")
        db_out[n] = np.where(jb > 0, cum_sb[np.maximum(jb - 1, 0)], 0.0)
        da_out[n] = np.where(ja > 0, cum_sa[np.maximum(ja - 1, 0)], 0.0)

        t_out[n] = t_ms
        n += 1

    return {"t_ms": t_out[:n], "cum_bid": nb_out[:n], "cum_ask": na_out[:n],
            "depth_bid": db_out[:n], "depth_ask": da_out[:n],
            "lines": n_lines, "parsed": n, "skipped": skipped, "unsorted": unsorted}


def read_coin(coin, edges, depth_k):
    """Every cached hour of one coin, in day order, with the ladder of each snapshot.

    Duplicate timestamps are collapsed keeping the LAST occurrence after a stable
    ascending sort, which is the rule i4_l2_mid.py and i3_book_comparator.py both
    applied when they built the series this run is checked against. Applying a
    different rule here would make the row counts differ for a reason that has nothing
    to do with the book.
    """
    blocks, per_day = [], {}
    lines = parsed = skipped = unsorted = 0
    t_start = time.time()
    for day in DAYS:
        d_parsed = 0
        for hour in HOURS:
            found, path = have_cell(day, hour, coin)
            if not found:
                continue
            got = ladder_of_file(path, edges, depth_k)
            _require(got is not None,
                     f"{os.path.relpath(path, _CODE_DIR)} would not decompress, so the "
                     f"hour is unread and the population would be short by one cell "
                     f"without saying so")
            # A SHORT READ IS A FINDING. An hour file of this venue carries thousands of
            # snapshots; an hour that yields none is a truncated or empty transfer, and
            # accepting it would put a hole in the window that nothing downstream could
            # see.
            _require(got["parsed"] > 0,
                     f"expected thousands of snapshots from "
                     f"{os.path.relpath(path, _CODE_DIR)}, read {got['parsed']} from "
                     f"{got['lines']} lines")
            blocks.append(got)
            lines += got["lines"]
            parsed += got["parsed"]
            skipped += got["skipped"]
            unsorted += got["unsorted"]
            d_parsed += got["parsed"]
        per_day[day] = d_parsed
        say(f"{coin} {day}: {d_parsed:,} snapshots "
            f"({parsed:,} so far, {time.time() - t_start:.0f} s elapsed)")

    t_ms = np.concatenate([b["t_ms"] for b in blocks])
    order = np.argsort(t_ms, kind="stable")
    keep = np.ones(order.size, dtype=bool)
    t_sorted = t_ms[order]
    keep[:-1] = t_sorted[1:] != t_sorted[:-1]
    take = order[keep]

    out = {"t_ms": t_sorted[keep], "per_day": per_day, "lines": lines,
           "parsed": parsed, "skipped": skipped, "unsorted": unsorted,
           "duplicates_dropped": int(order.size - int(keep.sum()))}
    # Concatenated one array at a time and the source blocks released as they are
    # consumed, so the peak is one copy of the largest array rather than two of all four.
    for key in ("cum_bid", "cum_ask", "depth_bid", "depth_ask"):
        stacked = np.concatenate([b[key] for b in blocks])
        for b in blocks:
            b[key] = None
        out[key] = stacked[take]
        del stacked
    return out


def median_by_column(matrix):
    """The median of each column, taken one column at a time.

    np.median over an axis of a 1.6-million-row matrix copies the whole matrix to sort
    it, which doubles the peak of the largest array in this run for no reason. Column by
    column the copy is one column.
    """
    return np.array([float(np.median(matrix[:, j])) for j in range(matrix.shape[1])])


# ==========================================================================
# 3. THE INDEPENDENT CHECK: DOES THE RE-PARSE REPRODUCE THE COMMITTED DEPTH
# ==========================================================================

def depth_columns_of(path):
    """The depth rungs a book_feats file carries, read from its own key names.

    Resolved from the file rather than typed, because a rung named in two places is a
    rung that can be renamed in one of them.
    """
    with np.load(path, allow_pickle=False) as z:
        names = list(z.files)
    rungs = sorted({int(m.group(1)) for m in
                    (re.fullmatch(r"depth_bid_(\d+)bps", n) for n in names) if m})
    return rungs


def check_against_book_feats(coin, got, depth_k, path):
    """Hold this run's re-parse against the depth columns already in the tree.

    THIS IS THE ONE STATEMENT THAT MAKES THE PICTURE CHECKABLE. Everything on the left
    panel comes from a ladder read here for the first time, and an assertion by this
    file about its own reading proves nothing. i3_book_comparator.py read the same raw
    bytes weeks ago under a rule written independently -- a plain Python loop over the
    levels, no searchsorted, no cumulative sums -- and wrote four depth columns per coin.
    If this run's ladder is right, those columns fall out of it exactly.
    """
    with np.load(path, allow_pickle=False) as z:
        ref_t = np.asarray(z["t_ms"], dtype=np.int64)
        ref = {}
        for k in depth_k:
            ref[("bid", k)] = np.asarray(z[f"depth_bid_{k}bps"], dtype=np.float64)
            ref[("ask", k)] = np.asarray(z[f"depth_ask_{k}bps"], dtype=np.float64)

    rows_here, rows_ref = int(got["t_ms"].size), int(ref_t.size)
    _require(rows_here == rows_ref,
             f"{coin}: this run read {rows_here:,} distinct snapshots and "
             f"{os.path.basename(path)} holds {rows_ref:,}. The two are the same "
             f"population by construction, so a difference is a short read on one side "
             f"and neither number may be published until it is named")
    aligned = int(np.count_nonzero(got["t_ms"] == ref_t))
    _require(aligned == rows_here,
             f"{coin}: {rows_here - aligned:,} of {rows_here:,} timestamps differ "
             f"between this run and {os.path.basename(path)}, so the two are not "
             f"row-aligned and a column comparison would compare different snapshots")

    worst = {}
    bad_total = 0
    for side in ("bid", "ask"):
        mine_all = got[f"depth_{side}"]
        for j, k in enumerate(depth_k):
            mine = mine_all[:, j]
            theirs = ref[(side, k)]
            gap = np.abs(mine - theirs)
            scale = np.maximum(np.abs(theirs), 1e-12)
            bad = int(np.count_nonzero(gap > DEPTH_RTOL * scale))
            bad_total += bad
            worst[f"depth_{side}_{k}bps"] = {
                "rows": int(mine.size),
                "rows_beyond_tolerance": bad,
                "max_absolute_gap": float(gap.max()),
                "max_relative_gap": float((gap / scale).max()),
                "median_here": float(np.median(mine)),
                "median_in_artifact": float(np.median(theirs)),
            }
    _require(bad_total <= DEPTH_MAX_BAD,
             f"{coin}: this run's re-parse disagrees with {os.path.basename(path)} on "
             f"{bad_total:,} depth readings beyond a relative {DEPTH_RTOL:g}. The "
             f"ladder drawn on the left panel is read the same way, so it cannot be "
             f"published until the disagreement is explained")
    return {"rows": rows_here, "timestamps_aligned": aligned,
            "rows_beyond_tolerance_total": bad_total, "relative_tolerance": DEPTH_RTOL,
            "columns": worst,
            "note": ("the depth columns of book_feats were written by "
                     "i3_book_comparator.py with a per-level Python loop; they are "
                     "recomputed here by a cumulative sum and a binary search over the "
                     "same raw bytes. Agreement on every row is what licenses the "
                     "ladder beside it")}


def degeneracy_of_two_rungs(coin, path, depth_k):
    """Why the two-rung ladder was not enough, stated as a measurement.

    The decision to spend two and a half minutes on the raw snapshots rests on this
    number and nothing else, so the number is computed by the run that acts on it
    rather than quoted from the day it was first taken.
    """
    lo, hi = min(depth_k), max(depth_k)
    out = {}
    with np.load(path, allow_pickle=False) as z:
        for side in ("bid", "ask"):
            a = np.asarray(z[f"depth_{side}_{lo}bps"], dtype=np.float64)
            b = np.asarray(z[f"depth_{side}_{hi}bps"], dtype=np.float64)
            same = int(np.count_nonzero(a == b))
            out[side] = {
                "rows": int(a.size),
                "rows_where_the_two_rungs_are_identical": same,
                "share_identical": float(same / a.size),
                f"median_{lo}bps": float(np.median(a)),
                f"median_{hi}bps": float(np.median(b)),
                "ratio_of_medians": float(np.median(b) / max(np.median(a), 1e-12)),
            }
    return out


# ==========================================================================
# 4. THE WINDOW: QUOTED SPREAD ACROSS THE TEN DAYS
# ==========================================================================

def spread_series(coin):
    """Hourly and daily median quoted spread in basis points, from the mid series.

    The mid series is the committed derivation of the same snapshots the left panel
    reads, and it is used here rather than re-derived because the quantity it holds --
    best ask minus best bid at every snapshot -- is exactly what this panel needs.
    """
    path = os.path.join(_CODE_DIR, f"mid_series_{coin}.npz")
    _require(os.path.exists(path),
             f"mid_series_{coin}.npz is not on this machine, so the window panel has "
             f"no series to draw for {coin}")
    with np.load(path, allow_pickle=False) as z:
        t_ms = np.asarray(z["t_ms"], dtype=np.int64)
        mid = np.asarray(z["mid"], dtype=np.float64)
        spread = np.asarray(z["spread"], dtype=np.float64)
    _require(np.all(np.isfinite(mid)) and np.all(mid > 0),
             f"mid_series_{coin}.npz carries a non-positive or non-finite mid, so a "
             f"spread in basis points of it is not defined")
    bps = spread / mid * 1e4

    # Epoch milliseconds to a day of the month and an hour, in UTC, which is the clock
    # the venue stamps with and the one the day directories of the cache are named for.
    seconds = t_ms // 1000
    days_from_epoch = seconds // 86400
    hour_of_day = (seconds % 86400) // 3600
    hour_index = days_from_epoch * 24 + hour_of_day
    hour_index = hour_index - hour_index.min()
    day_of_month = np.array(
        [datetime.datetime.fromtimestamp(int(s), datetime.timezone.utc).day
         for s in np.unique(seconds // 86400 * 86400)])
    day_key = days_from_epoch - days_from_epoch.min()

    n_hours = int(hour_index.max()) + 1
    hourly = np.full(n_hours, np.nan)
    hourly_n = np.zeros(n_hours, dtype=np.int64)
    order = np.argsort(hour_index, kind="stable")
    bounds = np.searchsorted(hour_index[order], np.arange(n_hours + 1))
    for h in range(n_hours):
        chunk = bps[order[bounds[h]:bounds[h + 1]]]
        hourly_n[h] = chunk.size
        if chunk.size:
            hourly[h] = float(np.median(chunk))
    # AN HOUR WITH NO ROWS IS A FINDING, not a gap to interpolate over. The cache holds
    # every hour of every day, so an empty hour means the series is short of the window
    # it claims and the panel would draw a continuous line across a hole.
    empty = [int(h) for h in np.where(hourly_n == 0)[0]]
    _require(not empty,
             f"{coin}: hours {empty[:8]} of the window carry no rows in "
             f"mid_series_{coin}.npz, so the series is shorter than the ten days it is "
             f"drawn across")

    daily = {}
    for d in np.unique(day_key):
        chunk = bps[day_key == d]
        daily[int(day_of_month[int(d)])] = {
            "median_bps": float(np.median(chunk)),
            "rows": int(chunk.size),
        }
    return {"hourly_median_bps": hourly, "hourly_rows": hourly_n,
            "daily": daily, "bps": bps, "day_of_month_of_row": day_key,
            "day_of_month_list": [int(x) for x in day_of_month],
            "rows": int(bps.size),
            "median_bps": float(np.median(bps))}


# ==========================================================================
# 5. RUN
# ==========================================================================

say(f"window {DAYS[0]}..{DAYS[-1]}, {len(HOURS)} hours a day, coins {COINS}")
CALIBRATION = calibrate_presence()
say(f"presence predicate calibrated on {len(CALIBRATION)} cases, "
    f"{sum(1 for c in CALIBRATION if c['expected'] == 'present')} that must be found "
    f"and {sum(1 for c in CALIBRATION if c['expected'] == 'absent')} that must not")

PRESENT, MISSING = census_cache()
say(f"cache holds {len(PRESENT)} of {N_CELLS_EXPECTED} declared cells")
_require(not MISSING,
         f"{len(MISSING)} of {N_CELLS_EXPECTED} declared cells are not on disk, the "
         f"first being {MISSING[0] if MISSING else ''}; the window would be drawn short "
         f"of what its axis says")

BOOK = {}
CHECK = {}
DEGEN = {}
DEPTH_K = None
for coin in COINS:
    feats = os.path.join(_CODE_DIR, f"book_feats_{coin}.npz")
    _require(os.path.exists(feats),
             f"book_feats_{coin}.npz is not on this machine, so the re-parse has "
             f"nothing independent to be held against and the ladder would rest on "
             f"this file's own word")
    rungs = depth_columns_of(feats)
    _require(rungs, f"book_feats_{coin}.npz carries no depth_bid_*bps column")
    if DEPTH_K is None:
        DEPTH_K = rungs
    _require(rungs == DEPTH_K,
             f"book_feats_{coin}.npz carries rungs {rungs} while the first coin "
             f"carried {DEPTH_K}, so one comparison would be against another quantity")
    DEGEN[coin] = degeneracy_of_two_rungs(coin, feats, DEPTH_K)

    say(f"reading {coin}: 240 hourly files, about 70 seconds")
    got = read_coin(coin, EDGES_BPS, DEPTH_K)
    say(f"{coin}: {got['parsed']:,} snapshots parsed from {got['lines']:,} lines, "
        f"{got['skipped']:,} unparseable, {got['unsorted']:,} with a ladder out of "
        f"order, {got['duplicates_dropped']:,} duplicate stamps dropped, "
        f"{got['t_ms'].size:,} distinct")
    CHECK[coin] = check_against_book_feats(coin, got, DEPTH_K, feats)
    say(f"{coin}: re-parse agrees with book_feats on all "
        f"{CHECK[coin]['rows']:,} rows of {2 * len(DEPTH_K)} depth columns")

    BOOK[coin] = {
        "median_cum_notional_bid": median_by_column(got["cum_bid"]),
        "median_cum_notional_ask": median_by_column(got["cum_ask"]),
        "snapshots": int(got["t_ms"].size),
        "per_day": got["per_day"],
        "lines": got["lines"], "parsed": got["parsed"], "skipped": got["skipped"],
        "unsorted": got["unsorted"],
        "duplicates_dropped": got["duplicates_dropped"],
    }
    del got

SPREAD = {}
for coin in COINS:
    SPREAD[coin] = spread_series(coin)
    say(f"{coin}: quoted spread median {SPREAD[coin]['median_bps']:.4f} bps over "
        f"{SPREAD[coin]['rows']:,} snapshots")

# The two halves of the window, taken from the rule rather than from a typed pair. The
# rule is a function of the days present because a literal pair is right only for a
# window that begins on the fourth of a month.
DAYS_PRESENT = sorted(SPREAD[COINS[0]]["day_of_month_list"])
EARLY_DAYS, LATE_DAYS = H.split_early_late(DAYS_PRESENT)
_require(len(EARLY_DAYS) > 0 and len(LATE_DAYS) > 0,
         f"the split rule returned {EARLY_DAYS} and {LATE_DAYS} for the days "
         f"{DAYS_PRESENT}, so there is no boundary to draw")
_require(H.day_split_agrees(EARLY_DAYS, LATE_DAYS),
         "the two halves drawn are not the split the rule returns for their own union")
BOUNDARY_HOUR = len(EARLY_DAYS) * len(HOURS)

HALVES = {}
for coin in COINS:
    s = SPREAD[coin]
    day_of = np.array([s["day_of_month_list"][d] for d in s["day_of_month_of_row"]])
    early = s["bps"][np.isin(day_of, EARLY_DAYS)]
    late = s["bps"][np.isin(day_of, LATE_DAYS)]
    _require(early.size > 0 and late.size > 0,
             f"{coin}: one half of the window carries no rows, so the boundary the "
             f"panel draws separates nothing")
    HALVES[coin] = {
        "labelling_half_days": list(EARLY_DAYS),
        "measurement_half_days": list(LATE_DAYS),
        "labelling_median_bps": float(np.median(early)),
        "measurement_median_bps": float(np.median(late)),
        "labelling_rows": int(early.size),
        "measurement_rows": int(late.size),
        "difference_bps": float(np.median(late) - np.median(early)),
        "ratio": float(np.median(late) / max(np.median(early), 1e-12)),
    }
    say(f"{coin}: labelling half {HALVES[coin]['labelling_median_bps']:.4f} bps "
        f"against measurement half {HALVES[coin]['measurement_median_bps']:.4f} bps, "
        f"a ratio of {HALVES[coin]['ratio']:.4f}")

# ==========================================================================
# 6. THE FIGURE
# ==========================================================================
SCALE_M = 1e6                      # dollars to millions, one place
COLOUR = {COINS[0]: "0.30", COINS[1]: "C0"} if len(COINS) == 2 else {}
for i, c in enumerate(COINS):
    COLOUR.setdefault(c, f"C{i}")

fig, (axL, axR) = plt.subplots(
    1, 2, figsize=(WIDTH_IN, HEIGHT_IN), layout="constrained",
    gridspec_kw={"width_ratios": [1.0, 1.15]})
fig.get_layout_engine().set(h_pad=0.02, w_pad=0.03, hspace=0.02, wspace=0.03)

# --- left: the book -------------------------------------------------------
# Bids are drawn at NEGATIVE distance and asks at positive, so the mid sits at the
# origin and the two sides face each other the way a book is read. The curve is
# cumulative, which is what makes it the familiar depth profile rather than a histogram
# whose bars depend on the width of the bin.
for coin in COINS:
    med_b = BOOK[coin]["median_cum_notional_bid"] / SCALE_M
    med_a = BOOK[coin]["median_cum_notional_ask"] / SCALE_M
    x_b = np.concatenate(([0.0], -EDGES_BPS))
    y_b = np.concatenate(([0.0], med_b))
    x_a = np.concatenate(([0.0], EDGES_BPS))
    y_a = np.concatenate(([0.0], med_a))
    axL.plot(x_b, y_b, lw=1.3, color=COLOUR[coin], label=coin)
    axL.plot(x_a, y_a, lw=1.3, color=COLOUR[coin])
    axL.fill_between(x_b, 0, y_b, color=COLOUR[coin], alpha=0.16, linewidth=0)
    axL.fill_between(x_a, 0, y_a, color=COLOUR[coin], alpha=0.16, linewidth=0)
    # WHERE THE BOOK EFFECTIVELY ENDS, MARKED, because a cumulative curve that has gone
    # flat is easy to read as depth continuing outward. The distance is the first edge
    # holding BOOK_END_SHARE of the side, which is a declared threshold and not the
    # deepest level: the first draft put the marker at the maximum instead, and on BTC
    # that landed at the right-hand edge of the panel, because the curve keeps rising by
    # thousandths of a million long after the book has, for a reader, ended.
    for med, sign in ((med_b, -1.0), (med_a, 1.0)):
        j = int(np.searchsorted(med, BOOK_END_SHARE * med.max(), side="left"))
        axL.plot([sign * EDGES_BPS[j]], [med[j]], "o", ms=3.0,
                 color=COLOUR[coin], zorder=4)
axL.axvline(0.0, color="0.35", lw=0.9, zorder=1)
axL.set_xlabel("distance from the mid, basis points\n"
               f"bids left, asks right; the dot holds "
               f"{BOOK_END_SHARE:.0%} of the grid")
axL.set_ylabel("median resting notional within\nthat distance, $ million")
axL.set_title("The visible book")
axL.legend(loc="upper center", frameon=False, handlelength=1.4, ncol=2,
           columnspacing=1.0)
axL.grid(axis="y", alpha=0.28)
axL.set_axisbelow(True)
axL.set_xlim(-EDGES_BPS.max(), EDGES_BPS.max())
axL.set_ylim(0, max(BOOK[c]["median_cum_notional_bid"].max()
                    for c in COINS) / SCALE_M * 1.20)

# --- right: the window ----------------------------------------------------
for coin in COINS:
    h = SPREAD[coin]["hourly_median_bps"]
    axR.plot(np.arange(h.size) / len(HOURS), h, lw=0.8, color=COLOUR[coin], label=coin)
axR.axvline(BOUNDARY_HOUR / len(HOURS), color="C3", lw=1.1, ls="--", zorder=3)
axR.set_ylim(0, max(np.nanmax(SPREAD[c]["hourly_median_bps"]) for c in COINS) * 1.42)
# The two labels sit in the empty band BETWEEN the coins rather than at the top of the
# panel, where the legend already is. Placed at the top they overprinted it, and the
# right-hand one ran off the edge of the canvas.
_LABEL_Y = axR.get_ylim()[1] * 0.45
axR.text(BOUNDARY_HOUR / len(HOURS) - 0.18, _LABEL_Y,
         f"wallets ranked\non days {EARLY_DAYS[0]}-{EARLY_DAYS[-1]}",
         ha="right", va="center", fontsize=PT_NOTE, color="C3")
axR.text(BOUNDARY_HOUR / len(HOURS) + 0.18, _LABEL_Y,
         f"outcomes measured\non days {LATE_DAYS[0]}-{LATE_DAYS[-1]}",
         ha="left", va="center", fontsize=PT_NOTE, color="C3")
axR.set_xticks(np.arange(len(DAYS)) + 0.5)
axR.set_xticklabels([str(d) for d in DAYS_PRESENT])
axR.set_xlim(0, len(DAYS))
axR.set_xlabel("day of December 2025, hourly medians\n"
               "the two halves never share a day")
axR.set_ylabel("quoted spread, basis points")
axR.set_title("The window either side of the split")
axR.legend(loc="upper right", frameon=False, handlelength=1.4)
axR.grid(axis="y", alpha=0.28)
axR.set_axisbelow(True)

# THE POPULATION IS PRINTED ON THE FIGURE, not left to the caption of whatever document
# the image is pasted into. An image travels; a sentence about it does not. Two short
# lines rather than one long one: measured on this canvas, a single line of this content
# runs about six inches against a page column of five and a half, and the ends of it -
# which are the population and the file count - were the parts that fell off.
fig.supxlabel(
    f"{sum(BOOK[c]['snapshots'] for c in COINS):,} book snapshots from all "
    f"{len(PRESENT)} hourly files, {int(DAYS[0][6:])}-{int(DAYS[-1][6:])} December "
    f"{DAYS[0][:4]}: "
    + ", ".join(f"{c} {BOOK[c]['snapshots']:,}" for c in COINS) + "\n"
    "twenty levels a side, read at every hour of the ten days",
    fontsize=PT_NOTE, color="0.25")

fig.savefig(OUT_PNG, dpi=DPI_OUT)
plt.close(fig)
say(f"wrote {os.path.relpath(OUT_PNG, HERE)} "
    f"({int(WIDTH_IN * DPI_OUT)} by {int(HEIGHT_IN * DPI_OUT)} points)")

# ==========================================================================
# 7. THE SAME NUMBERS AS TEXT
# ==========================================================================
say("left panel, median cumulative resting notional in $ million:")
say("   distance   " + "".join(f"{c + ' bid':>12}{c + ' ask':>12}" for c in COINS))
for j, e in enumerate(EDGES_BPS):
    if j % 4 == 3 or j == 0:
        row = f"   <={e:5.2f} bps"
        for c in COINS:
            row += (f"{BOOK[c]['median_cum_notional_bid'][j] / SCALE_M:12.3f}"
                    f"{BOOK[c]['median_cum_notional_ask'][j] / SCALE_M:12.3f}")
        say(row)
say("right panel, median quoted spread in basis points by day:")
for d in DAYS_PRESENT:
    say(f"   Dec {d:02d}  " + "  ".join(
        f"{c} {SPREAD[c]['daily'][d]['median_bps']:.4f}" for c in COINS))

CAPTION_WORDS = len(CAPTION.split())
_require(CAPTION_MIN_WORDS <= CAPTION_WORDS <= CAPTION_MAX_WORDS,
         f"the caption runs to {CAPTION_WORDS} words, outside the "
         f"{CAPTION_MIN_WORDS}-{CAPTION_MAX_WORDS} our captions hold to")

results = {
    "question": (
        "what does the order book this study is built on actually look like, and is "
        "the ten-day window one market either side of the cut that separates the "
        "wallets being ranked from the fills being measured"),
    "figure_file": os.path.basename(OUT_PNG),
    "caption": CAPTION,
    "caption_words": CAPTION_WORDS,
    "left_panel": {
        "axes": ("horizontal: signed distance from the mid in basis points, bids "
                 "negative and asks positive; vertical: median resting notional in "
                 "dollars standing within that distance, cumulative from the mid"),
        "distance_edges_bps": EDGES_BPS.tolist(),
        "median_cumulative_notional_usd": {
            coin: {"bid": BOOK[coin]["median_cum_notional_bid"].tolist(),
                   "ask": BOOK[coin]["median_cum_notional_ask"].tolist()}
            for coin in COINS},
        "the_median_is_over_snapshots_not_seconds": (
            "the venue emits a snapshot when the book changes, so a busy minute "
            "contributes more snapshots than a quiet one and this is the median "
            "snapshot rather than the median second. The per-day snapshot counts are "
            "below, so the weighting is visible rather than implied"),
        "how_far_the_visible_book_reaches": {
            coin: {
                "share_of_the_side_the_marker_holds": BOOK_END_SHARE,
                "bid_bps": float(EDGES_BPS[np.searchsorted(
                    BOOK[coin]["median_cum_notional_bid"],
                    BOOK_END_SHARE * BOOK[coin]["median_cum_notional_bid"].max(),
                    side="left")]),
                "ask_bps": float(EDGES_BPS[np.searchsorted(
                    BOOK[coin]["median_cum_notional_ask"],
                    BOOK_END_SHARE * BOOK[coin]["median_cum_notional_ask"].max(),
                    side="left")]),
                "total_median_notional_bid_usd": float(
                    BOOK[coin]["median_cum_notional_bid"].max()),
                "total_median_notional_ask_usd": float(
                    BOOK[coin]["median_cum_notional_ask"].max()),
                "note": ("the distance is the first edge of the grid holding that "
                         "share of the side, not the deepest level carrying anything: "
                         "the curve goes on rising by thousandths of a million past the "
                         "point where a reader would call the book finished, so its "
                         "maximum sits at the end of the grid on BTC and says nothing"),
            } for coin in COINS},
    },
    "right_panel": {
        "axes": ("horizontal: the ten days of the window, one point per hour; "
                 "vertical: median quoted spread of that hour in basis points of the "
                 "mid. The dashed line is the boundary between the half the wallets "
                 "are ranked on and the half every economic figure is measured on"),
        "hourly_median_spread_bps": {
            coin: [None if not np.isfinite(v) else float(v)
                   for v in SPREAD[coin]["hourly_median_bps"]] for coin in COINS},
        "hourly_rows": {coin: SPREAD[coin]["hourly_rows"].tolist() for coin in COINS},
        "daily_median_spread_bps": {
            coin: {str(d): SPREAD[coin]["daily"][d] for d in DAYS_PRESENT}
            for coin in COINS},
        "window_median_spread_bps": {
            coin: SPREAD[coin]["median_bps"] for coin in COINS},
        "the_two_halves": HALVES,
        "boundary_hour_index": BOUNDARY_HOUR,
        "split_rule": (
            "the halves come from settings.split_early_late over the days present, not "
            "from a typed pair, and settings.day_split_agrees confirms the two tuples "
            "drawn are the fixed point of that rule for their own union"),
        "what_this_panel_supports_and_what_it_does_not": (
            "it supports the premise that the window is one market across the cut: the "
            "two halves differ in median quoted spread by "
            + "; ".join(f"{c} {HALVES[c]['difference_bps']:+.4f} bps "
                        f"(ratio {HALVES[c]['ratio']:.3f})" for c in COINS)
            + ". It does NOT test the halves for equality of anything else, and it is "
              "not evidence that the counterparty population is stable across the cut, "
              "which is a separate question the persistence work answers"),
    },
    "why_the_raw_snapshots_were_parsed": {
        "the_alternative": (
            f"book_feats_{{COIN}}.npz carries resting depth at {DEPTH_K} basis points "
            f"and nothing between, which is a ladder of {len(DEPTH_K)} rungs"),
        "the_measurement_that_decided_it": DEGEN,
        "the_finding": (
            "on BTC the two rungs are the same number on almost every row, because the "
            "whole visible book ends inside the inner one; on ETH they differ by about "
            "a third. A ladder of two rungs is therefore a ladder of one rung on one of "
            "the two coins, and its shape would be a property of where the rungs were "
            "put rather than of the book"),
        "what_was_read_instead": (
            "every snapshot of every cached hour, twenty levels a side, giving the "
            "shape at a quarter of a basis point, which is finer than one tick on "
            "either coin"),
        "measured_cost": "about two and a half minutes, printed by every run",
    },
    "verification": {
        "against_a_committed_artifact": CHECK,
        "why_this_is_the_check_that_counts": (
            "the ladder drawn here is read by this file for the first time, so any "
            "assertion it makes about its own reading is circular. The same pass "
            "recomputes the four depth columns i3_book_comparator.py wrote into "
            "book_feats months earlier by an unrelated route -- a per-level Python loop "
            "against a cumulative sum and a binary search -- and the run refuses to "
            "draw unless the two agree on every row of every column"),
        "presence_predicate_calibration": {
            "cases": CALIBRATION,
            "why": ("a predicate that answers no to everything reports an empty cache "
                    "as cleanly as a correct one, so it is shown a cell that must be "
                    "found and three that must not: the day before the window, the day "
                    "after it, and a coin the cache does not carry"),
        },
        "short_read_guards": (
            "a declared cell missing from disk, an hour file that will not decompress, "
            "an hour that yields no snapshot, an hour of the mid series with no row, a "
            "row count that differs from the committed artifact, and a timestamp that "
            "does not align with it each stop the run and print expectation, fact and "
            "place. None of them fired on this run"),
    },
    "population": {
        "hourly_files_declared": N_CELLS_EXPECTED,
        "hourly_files_read": len(PRESENT),
        "hourly_files_missing": MISSING,
        "by_coin": {
            coin: {
                "lines_in_the_cache": BOOK[coin]["lines"],
                "snapshots_parsed": BOOK[coin]["parsed"],
                "lines_unparseable": BOOK[coin]["skipped"],
                "ladders_out_of_order": BOOK[coin]["unsorted"],
                "duplicate_timestamps_dropped": BOOK[coin]["duplicates_dropped"],
                "distinct_snapshots_drawn": BOOK[coin]["snapshots"],
                "snapshots_per_day": BOOK[coin]["per_day"],
                "mid_series_rows_for_the_spread_panel": SPREAD[coin]["rows"],
            } for coin in COINS},
    },
    "what_i_did_not_check": [
        "that the twenty levels the venue publishes are the whole book. They are the "
        "whole VISIBLE book, which is what a maker quoting into it can see, and the "
        "figure says visible in its own title. Whether resting interest exists beyond "
        "the twentieth level is not answerable from this feed at all",
        "the shape of the book at the moment of a fill. The medians here are over all "
        "snapshots, and a fill arrives at a moment selected by the taker rather than "
        "at random, so the book a taker meets is not the median book. That selection "
        "is the subject of the markout work and is not measured here",
        "any test of distributional equality between the two halves. What is drawn is "
        "the median quoted spread and what is claimed is that the two medians are "
        "close; higher moments, depth and the arrival rate are not compared",
        "the coins the study does not use. SOL series exist in this tree and the "
        "snapshot cache holds no SOL at all, so nothing here speaks for it",
    ],
}

scope_block = {
    "population": (
        f"{sum(BOOK[c]['snapshots'] for c in COINS):,} distinct order-book snapshots "
        f"read from all {len(PRESENT)} hourly files of the cache ("
        + ", ".join(f"{c} {BOOK[c]['snapshots']:,}" for c in COINS)
        + f"), twenty levels a side; and the "
        + ", ".join(f"{SPREAD[c]['rows']:,} {c}" for c in COINS)
        + " rows of the mid series for the quoted-spread panel. The medians are over "
          "snapshots and not over seconds"),
    "window": (
        f"{DAYS[0]} to {DAYS[-1]}, ten days, all {len(HOURS)} hours of each; the "
        f"labelling half is days {list(EARLY_DAYS)} and the measurement half days "
        f"{list(LATE_DAYS)}, and the boundary between them is drawn"),
    "coins": list(COINS),
}

settings_used = dict(
    lens="book",
    master_seed=None,
    n_perm=None,
    n_boot=None,
    early_days=list(EARLY_DAYS),
    late_days=list(LATE_DAYS),
    overrides_note=(
        "this file draws the raw material and computes no quantity that depends on a "
        "horizon, a fill floor or a reference price, so none of those is stated. No "
        "random stream is drawn, so the seed, the permutation count and the bootstrap "
        "count are stated as not applying rather than left to be read as the "
        "declaration. The two halves are not typed here: they come from "
        "settings.split_early_late over the days actually present"),
)

artifact.write(os.path.basename(OUT_JSON), results,
               script=__file__,
               inputs=[L2.L2_CACHE]
                      + [os.path.join(_CODE_DIR, f"mid_series_{c}.npz") for c in COINS]
                      + [os.path.join(_CODE_DIR, f"book_feats_{c}.npz") for c in COINS],
               scope=scope_block, settings=settings_used, started=T0,
               out_dir=os.path.dirname(OUT_JSON))
say(f"wrote {os.path.relpath(OUT_JSON, HERE)}")
say(f"caption ({CAPTION_WORDS} words): {CAPTION}")
say(f"total {time.time() - T0:.0f} s")
