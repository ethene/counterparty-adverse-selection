#!/usr/bin/env python3
"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-08-26
References: Hyperliquid Level-4 node fill archive, node_fills_by_block hourly store,
December 2025 window, as parsed by data/build_quickwin_markouts.py and published on
Zenodo 18184441 (Albers et al. 2026); Easley, Lopez de Prado and O'Hara (2012) on the
size distribution of trades as a description of order flow.

THE DATA THE REPORT STANDS ON, SHOWN AS DATA RATHER THAN ASSERTED IN A SENTENCE.

Every result in this report is measured on one trade tape: ten days of executed trades
on two coins, collapsed so that one taker order sweeping several resting quotes counts
once. The report states the size of that tape in words and then never shows it. A
reader is asked to accept, on the strength of one sentence, both that there is enough
of it and that its two halves are alike enough for one to label counterparties and the
other to measure what those labels were worth. This figure puts the tape itself on the
page so that both can be seen instead of believed.

WHY THE LEFT PANEL CARRIES A VERTICAL LINE AND WHAT WOULD FALSIFY THE DESIGN. The
out-of-sample premise of the whole report is a cut through this window: the earlier
half scores each counterparty, the later half measures the maker's result against it,
and no fill appears on both sides. That premise is worth nothing if the two halves are
not comparable, because then a difference between them could be a difference in the
market rather than in what was learned. The line marks the cut and the two halves are
drawn to the same scale, so a reader can see the comparison rather than take it. The
cut is NOT typed here: it is settings.split_early_late over the days actually present,
which is the same function every consumer of this tape calls, and the producer refuses
to draw if the halves it is about to label disagree with what that function returns.

WHY THE RIGHT PANEL IS A DISTRIBUTION AND NOT A SUMMARY. A mean trade size on this
tape is close to meaningless: the mean is twenty thousand dollars and the median is
five hundred, because the two are answers about different trades. The panel therefore
draws the whole distribution on a logarithmic axis, where the shape is legible, and the
numbers beside it are quantiles rather than a mean. What a reader takes away is the
spread: the central ninety-eight per cent of trades covers more than four decades of
notional, so any statement about "a trade" on this venue is a statement about a
population whose members differ by four orders of magnitude.

WHAT THE RIGHT PANEL DOES NOT EXPLAIN, STATED HERE BECAUSE THE OPPOSITE IS EASY TO
ASSUME. The report elsewhere reports that the top decile of ranked wallets holds 56.2
per cent of the late-half fills. That is a property of how many fills each WALLET does,
and this panel measures how large each FILL is. The two are different quantities on the
same tape and neither is drawn as a cause of the other. The results file below repeats
this in the same words, so the figure cannot be cited for a mechanism it does not show.

WHAT IS DELIBERATELY ABSENT. No curve of cumulative share against ranked counterparties
and no single-number inequality index is drawn. That question was asked and settled
against drawing it, and a picture is a way of reopening a settled question without
saying so. The panel is about the size of a trade and says nothing about who did it.

THE HORIZONTAL AXIS OF THE LEFT PANEL IS THE ONLY TIME AXIS THIS FILE CAN DRAW. The
tape it reads carries a day column and no intraday clock, so a day is the finest grain
available here. An hour-of-day panel exists in principle from a much larger companion
file, but that file carries a different population from the one the report publishes on,
and drawing two populations under one caption is the error this file exists to avoid.

DRAWN AT THE SIZE IT IS PRINTED. The canvas is 5.53 inches wide because that is the
width of the single text column of the report, and 3.4 inches tall to match the four
figures already in the tree. Every point size below is the size a reader of the page
sees.

WHAT THIS FILE ADDS TO THE RECORD AND WHAT IT COSTS. It reads one packed array and one
build summary, computes counts and quantiles over 2.48 million rows, and costs under
five seconds. Every number drawn is printed to the screen and written to the results
file beside it, so the picture can be checked without measuring pixels. It takes no
command line: a figure has nothing to choose.

Run command (bare python3 is BLOCKED on this machine):
  uv run --no-project --with-requirements requirements.txt python3 -u \
      data/d2_fill_tape_figure.py
"""
import json
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# artifact.py and settings.py sit in the repository root, one directory up from this
# group, so the path is built from this file's own location and never from the working
# directory the run happens to start in.
_CODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CODE_DIR not in sys.path:
    sys.path.insert(0, _CODE_DIR)

import artifact                                                         # noqa: E402
import settings as H                                                    # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_NPZ = os.path.join(_CODE_DIR, "quickwin_markouts.npz")
SRC_SUMMARY = os.path.join(HERE, "quickwin_pass_summary.json")
OUT_PNG = os.path.join(HERE, "d2_fill_tape.png")
OUT_JSON = os.path.join(HERE, "d2_fill_tape_figure_results.json")

T0 = artifact.start_clock()

# The printed geometry, in one place, because a size named twice is a size that drifts.
WIDTH_IN, HEIGHT_IN, DPI_OUT = 5.53, 3.4, 200
PT_LABEL, PT_TITLE, PT_LEGEND, PT_NOTE = 7.5, 8, 6.6, 6.5
plt.rcParams.update({"font.size": PT_LABEL,
                     "axes.labelsize": PT_LABEL,
                     "axes.titlesize": PT_TITLE,
                     "xtick.labelsize": PT_LABEL,
                     "ytick.labelsize": PT_LABEL,
                     "legend.fontsize": PT_LEGEND})

# One colour per coin on BOTH panels, so a reader learns the pairing once. The quantity
# is carried by the artist and not by the colour: a bar is a count, a marker is money, a
# step outline is a distribution.
COIN_COLOUR = {"BTC": "C0", "ETH": "C1"}
COIN_MARKER = {"BTC": "o", "ETH": "s"}

# The coin code map belongs to the FILE being read and is fetched from its one home.
COIN_LABEL = H.coin_labels("quickwin")          # {0: 'BTC', 1: 'ETH'}
COINS = [COIN_LABEL[c] for c in sorted(COIN_LABEL)]

USD_M, USD_BN = 1e6, 1e9
PCT = 100.0

# The right panel's bin grid. Five bins to the decade over the range the data occupies,
# which is wide enough to hold every observation and fine enough that the mode is not a
# plateau. Both ends are derived from the data below and asserted to contain it.
BINS_PER_DECADE = 5
# The central band whose width in decades is the number the caption carries. Stated as a
# pair of percentiles rather than as "the range", because the range of a heavy-tailed
# sample is a property of its largest single observation.
SPREAD_LO_PCT, SPREAD_HI_PCT = 1.0, 99.0
QUANTILES = (0.0, 1.0, 5.0, 10.0, 25.0, 50.0, 75.0, 90.0, 95.0, 99.0, 99.9, 100.0)


def _require(condition, what):
    """Refuse to draw rather than draw a picture whose premise is false.

    A figure that quietly draws a broken premise is worse than one that does not draw:
    the picture reaches the report and the premise never does. Each condition below is
    something the caption or an axis asserts, so each is read out of the data or out of
    settings.py instead of being believed.
    """
    if not condition:
        raise SystemExit(f"[d2-fig] refusing to draw: {what}")


def _require_input(path, produced_by, argv=""):
    """Refuse with an address and a next command rather than an interpreter traceback.

    Both inputs below are intermediates that git does not carry -- one is tens of
    megabytes -- so their ABSENCE is the normal state of a fresh clone, not a fault.
    Dying inside np.load tells a reader who just cloned the repository neither which
    file is missing nor how to make it, and this figure goes into the report, so the
    reader who hits it is the one the Source Code column is about.

    Calibrated on two opposite cases, both run against this tree: with the file on disk
    the guard stays silent and the figure draws; with the same file renamed away it
    fires, names the file, and prints the command that writes it.
    """
    if not os.path.exists(path):
        run = f"{produced_by} {argv}".strip()
        raise SystemExit(
            f"[d2-fig] refusing to draw: {os.path.basename(path)} is not on disk. "
            f"It is an intermediate the repository does not carry, and it is written "
            f"by {produced_by}. Build it with: python3 {run}")


# ---------------------------------------------------------------------------
# THE TAPE, AND THE PROOF THAT ALL OF IT ARRIVED.
#
# A truncated read of a packed array is silent: the columns are still the right shape
# and every number computed from them is still arithmetically correct, only measured on
# a population smaller than the one named. The guard against that is not a feeling about
# the file size but the count the BUILDER recorded when it wrote the file, which sits in
# its own summary beside it. Expectation, fact and place are printed on a mismatch.
# ---------------------------------------------------------------------------
_require_input(SRC_NPZ, "data/build_quickwin_markouts.py")
_require_input(SRC_SUMMARY, "data/build_quickwin_markouts.py")

Z = np.load(SRC_NPZ)
SUMMARY = json.load(open(SRC_SUMMARY, encoding="utf-8"))

day = Z["day"].astype(np.int16)
coin = Z["coin"].astype(np.int8)
notional = Z["notional"].astype(np.float64)
taker_id = Z["taker_id"]
maker_id = Z["maker_id"]

N_ROWS = int(day.size)
N_ROWS_DECLARED = int(SUMMARY["total_rows"])
_require(N_ROWS == N_ROWS_DECLARED,
         f"short read of {os.path.basename(SRC_NPZ)}: the builder recorded "
         f"{N_ROWS_DECLARED:,} rows in {os.path.basename(SRC_SUMMARY)} and this run "
         f"loaded {N_ROWS:,}, a shortfall of {N_ROWS_DECLARED - N_ROWS:,}")

for name, arr in (("day", day), ("coin", coin), ("notional", notional),
                  ("taker_id", taker_id), ("maker_id", maker_id)):
    _require(arr.size == N_ROWS,
             f"column {name} holds {arr.size:,} values against {N_ROWS:,} in day")

_require(np.all(np.isfinite(notional)) and float(notional.min()) > 0.0,
         "the notional column carries a non-positive or non-finite value, and a "
         "logarithmic axis cannot hold one")

CODES_PRESENT = sorted(int(c) for c in np.unique(coin))
_require(CODES_PRESENT == sorted(COIN_LABEL),
         f"the file carries coin codes {CODES_PRESENT} while settings.py declares "
         f"{sorted(COIN_LABEL)} for this artifact")

DAYS = tuple(int(d) for d in np.unique(day))
DAYS_DECLARED = tuple(int(s[-2:]) for s in SUMMARY["config"]["days_resolved"])
_require(DAYS == DAYS_DECLARED,
         f"the file carries days {DAYS} while the builder resolved {DAYS_DECLARED}")

# Every hourly file of every day accounted for, read from the builder's own record. This
# is the second, independent answer to "did all of it arrive": the first counted rows in
# the packed array, this one counts the source files that produced them.
HOURS_BY_DAY = SUMMARY["hours_by_day"]
HOURS_EXPECTED = 24
hour_shortfalls = {d: len(h) for d, h in sorted(HOURS_BY_DAY.items())
                   if len(h) != HOURS_EXPECTED}
_require(not hour_shortfalls,
         f"the builder recorded fewer than {HOURS_EXPECTED} hourly files on "
         f"{hour_shortfalls}, so at least one day of this tape is a partial pull")

# ---------------------------------------------------------------------------
# THE CUT, TAKEN FROM THE RULE AND NOT TYPED.
# ---------------------------------------------------------------------------
EARLY_DAYS, LATE_DAYS = H.split_early_late(DAYS)
_require(H.day_split_agrees(EARLY_DAYS, LATE_DAYS),
         "the halves this panel is about to label are not the halves the rule in "
         "settings.py returns for the days present")
_require(not (set(EARLY_DAYS) & set(LATE_DAYS)),
         "the two halves share a day, so the line drawn between them would be false")

is_early = np.isin(day, EARLY_DAYS)
is_late = np.isin(day, LATE_DAYS)
_require(int(is_early.sum()) + int(is_late.sum()) == N_ROWS,
         "a row sits in neither half, so the panel would draw fewer trades than it "
         "names in its scope")

# ---------------------------------------------------------------------------
# THE DAY PREDICATE, CALIBRATED ON TWO OPPOSITE CASES BEFORE ANY COUNT IS BELIEVED.
#
# Every per-day number below is `day == d`, and a selector that silently matches nothing
# would draw ten empty bars as confidently as ten full ones. So the selector is shown a
# day it MUST find and two days it MUST NOT: the first day of the window, and the days
# on either side of the window's edges. A zero from this predicate is only evidence
# after both sides have answered.
# ---------------------------------------------------------------------------
CALIB_PRESENT = int(DAYS[0])
CALIB_ABSENT = (int(DAYS[0]) - 1, int(DAYS[-1]) + 1)
calib_hit = int((day == CALIB_PRESENT).sum())
calib_miss = {d: int((day == d).sum()) for d in CALIB_ABSENT}
_require(calib_hit > 0,
         f"the day selector found no row on day {CALIB_PRESENT}, which is in the window")
_require(all(v == 0 for v in calib_miss.values()),
         f"the day selector found rows outside the window on {calib_miss}")

# ---------------------------------------------------------------------------
# WHAT IS DRAWN ON THE LEFT: counts and turnover, per day, per coin.
# ---------------------------------------------------------------------------
by_day = {}
for code in sorted(COIN_LABEL):
    sym = COIN_LABEL[code]
    m_coin = coin == code
    by_day[sym] = {
        "fills": np.array([int((m_coin & (day == d)).sum()) for d in DAYS]),
        "notional_usd": np.array([float(notional[m_coin & (day == d)].sum())
                                  for d in DAYS]),
    }

FILLS_TOTAL_BY_DAY = sum(by_day[s]["fills"] for s in COINS)
_require(int(FILLS_TOTAL_BY_DAY.sum()) == N_ROWS,
         f"the per-day counts sum to {int(FILLS_TOTAL_BY_DAY.sum()):,} against "
         f"{N_ROWS:,} rows loaded, so a row belongs to no drawn day")

HALVES = {
    "early": {"days": list(EARLY_DAYS), "mask": is_early},
    "late": {"days": list(LATE_DAYS), "mask": is_late},
}
half_stats = {}
for name, blk in HALVES.items():
    m = blk["mask"]
    half_stats[name] = {
        "days": blk["days"],
        "fills": int(m.sum()),
        "notional_usd": float(notional[m].sum()),
        "takers": int(np.unique(taker_id[m]).size),
        "makers": int(np.unique(maker_id[m]).size),
    }
RATIO_FILLS = half_stats["late"]["fills"] / half_stats["early"]["fills"]
RATIO_NOTIONAL = (half_stats["late"]["notional_usd"]
                  / half_stats["early"]["notional_usd"])

# ---------------------------------------------------------------------------
# WHAT IS DRAWN ON THE RIGHT: the distribution of one trade's notional.
# ---------------------------------------------------------------------------
size_stats, hist = {}, {}
lo_edge = np.floor(np.log10(notional.min()) * BINS_PER_DECADE) / BINS_PER_DECADE
hi_edge = np.ceil(np.log10(notional.max()) * BINS_PER_DECADE) / BINS_PER_DECADE
N_BINS = int(round((hi_edge - lo_edge) * BINS_PER_DECADE))
EDGES = np.logspace(lo_edge, hi_edge, N_BINS + 1)
_require(EDGES[0] <= notional.min() and EDGES[-1] >= notional.max(),
         "the bin grid does not contain every observation, so the drawn shares would "
         "not sum to the population")

for code in sorted(COIN_LABEL):
    sym = COIN_LABEL[code]
    v = notional[coin == code]
    q = {f"p{p:g}": float(np.percentile(v, p)) for p in QUANTILES}
    counts, _ = np.histogram(v, bins=EDGES)
    _require(int(counts.sum()) == v.size,
             f"{sym}: {v.size - int(counts.sum()):,} trades fell outside the bin grid")
    hist[sym] = counts / v.size * PCT
    size_stats[sym] = {
        "n_fills": int(v.size),
        "quantiles_usd": q,
        "mean_usd": float(v.mean()),
        "mean_over_median": float(v.mean() / q["p50"]),
        "spread_decades_central_98pct": float(
            np.log10(q[f"p{SPREAD_HI_PCT:g}"] / q[f"p{SPREAD_LO_PCT:g}"])),
        "share_of_fills_under_100_usd": float((v < 100.0).mean() * PCT),
        "share_of_fills_over_10000_usd": float((v > 1e4).mean() * PCT),
        # The floor at ten dollars is the sharpest feature of the panel: on both coins
        # the share falls by an order of magnitude the moment the axis crosses it, so
        # both sides of that step are recorded. WHICH bin is the tallest is a separate
        # question and is read off the counts rather than asserted -- it is the bin above
        # ten dollars on one coin and a bin two decades further out on the other, and a
        # sentence naming one of them for both was wrong about the second.
        "share_in_the_bin_above_10_usd": float(
            ((v >= 10.0) & (v < 10.0 ** (1.0 + 1.0 / BINS_PER_DECADE))).mean() * PCT),
        "share_under_10_usd": float((v < 10.0).mean() * PCT),
        "tallest_bin": {
            "from_usd": float(EDGES[int(np.argmax(counts))]),
            "to_usd": float(EDGES[int(np.argmax(counts)) + 1]),
            "share_pct": float(hist[sym][int(np.argmax(counts))]),
        },
    }

SPREAD_DECADES_MIN = min(size_stats[s]["spread_decades_central_98pct"] for s in COINS)
SPREAD_DECADES_FLOOR = int(np.floor(SPREAD_DECADES_MIN))

# The three figures the report publishes about this tape, recomputed here from the file
# rather than copied from the prose, so a drift between the two is a refusal to draw and
# not a sentence nobody re-reads.
PUBLISHED = {
    "fills": {"published_text": "about 2.5 million", "recomputed": N_ROWS,
              "agrees": abs(N_ROWS - 2.5e6) / 2.5e6 < 0.02},
    "takers": {"published": 45849, "recomputed": int(np.unique(taker_id).size)},
    "makers": {"published": 9367, "recomputed": int(np.unique(maker_id).size)},
}
PUBLISHED["takers"]["agrees"] = (PUBLISHED["takers"]["published"]
                                 == PUBLISHED["takers"]["recomputed"])
PUBLISHED["makers"]["agrees"] = (PUBLISHED["makers"]["published"]
                                 == PUBLISHED["makers"]["recomputed"])
for what, blk in PUBLISHED.items():
    _require(blk["agrees"],
             f"the report publishes {blk.get('published', blk.get('published_text'))} "
             f"{what} and this file counts {blk['recomputed']:,} on the same tape")

# THE CAPTION CARRIES TWO NUMBERS AND BOTH ARE ASSERTED AGAINST WHAT WAS MEASURED.
# A caption is prose and drifts silently: the number in it is read by everyone and
# recomputed by nobody. An earlier draft of this one said the halves carry "comparable
# volume", which is not a measured statement at all -- by trade count they differ by
# under one per cent and by money by seventeen, so the one word covered two answers.
# Both figures below are therefore the rounded form of a quantity computed above, and
# the producer refuses to draw if either rounding stops being true.
CAPTION_HALF_GAP_PCT = abs(1.0 - RATIO_FILLS) * PCT
CAPTION = ("The window's two halves differ by one per cent in trade count, and trade "
           "size spans four decades.")
_require(12 <= len(CAPTION.split()) <= 19,
         f"the caption runs to {len(CAPTION.split())} words, outside the twelve to "
         f"nineteen the report's other captions hold")
_require(round(CAPTION_HALF_GAP_PCT) == 1,
         f"the caption says the halves differ by one per cent in trade count and the "
         f"measured gap is {CAPTION_HALF_GAP_PCT:.2f} per cent")
_require(SPREAD_DECADES_FLOOR == 4,
         f"the caption says four decades and the narrower coin spans "
         f"{SPREAD_DECADES_MIN:.2f}")

# ---------------------------------------------------------------------------
# The drawing.
# ---------------------------------------------------------------------------
fig, (axL, axR) = plt.subplots(
    1, 2, figsize=(WIDTH_IN, HEIGHT_IN), layout="constrained",
    gridspec_kw={"width_ratios": [1.30, 1.0]})
fig.get_layout_engine().set(h_pad=0.02, w_pad=0.04, hspace=0.0, wspace=0.03)

# --- left: the tape by day ---
x = np.arange(len(DAYS), dtype=float)
bar_w = 0.38
axLm = axL.twinx()          # money on the right spine, count on the left

bar_handles, line_handles = [], []
for i, sym in enumerate(COINS):
    offset = (i - 0.5) * bar_w
    b = axL.bar(x + offset, by_day[sym]["fills"] / 1e3, width=bar_w,
                color=COIN_COLOUR[sym], edgecolor="0.25", linewidth=0.4,
                alpha=0.72, zorder=2)
    bar_handles.append(b)
    h, = axLm.plot(x, by_day[sym]["notional_usd"] / USD_BN, COIN_MARKER[sym],
                   ms=3.4, mfc="white", mec=COIN_COLOUR[sym], mew=1.15,
                   ls=(0, (2, 1.6)), lw=0.9, color=COIN_COLOUR[sym], zorder=5)
    line_handles.append(h)

# The cut. Drawn between the last early day and the first late day, at a position
# derived from the split rather than from a typed index.
CUT_AT = len(EARLY_DAYS) - 0.5
axL.axvline(CUT_AT, color="k", lw=1.0, ls=(0, (4, 2)), zorder=6)

axL.set_xticks(x)
axL.set_xticklabels([str(d) for d in DAYS])
axL.set_xlabel("day of the December window")
axL.set_ylabel("trades, thousands")
axLm.set_ylabel("turnover, $ bn")
axL.set_title("The tape by day, and the cut\nthe out-of-sample design rests on")
axL.grid(axis="y", alpha=0.26)
axL.set_axisbelow(True)
axL.set_xlim(-0.72, len(DAYS) - 0.28)
axL.set_ylim(0, float(max(by_day[s]["fills"].max() for s in COINS)) / 1e3 * 1.88)
# The money ceiling is set well above the tallest marker on purpose. Both series share
# one frame, and the legend sits across the top of it; a ceiling fitted to the data puts
# the three tallest turnover markers behind the legend text.
axLm.set_ylim(0, float(max(by_day[s]["notional_usd"].max() for s in COINS))
              / USD_BN * 1.46)

# The two halves named on the axis rather than in the caption alone, because a reader
# who meets the line first should not have to leave the panel to learn what it separates.
axL.text(CUT_AT / 2 / (len(DAYS) - 1), 0.965, "labels the wallets",
         transform=axL.transAxes, ha="center", va="top", fontsize=PT_NOTE,
         color="0.25")
axL.text((CUT_AT + len(DAYS) - 1) / 2 / (len(DAYS) - 1), 0.965, "measures the result",
         transform=axL.transAxes, ha="center", va="top", fontsize=PT_NOTE,
         color="0.25")

axL.legend(bar_handles + line_handles,
           [f"{s} trades" for s in COINS] + [f"{s} turnover" for s in COINS],
           loc="upper left", bbox_to_anchor=(-0.015, 0.905), ncol=2, frameon=False,
           handlelength=1.3, borderpad=0.15, labelspacing=0.2, columnspacing=0.9,
           handletextpad=0.5)

# --- right: the size of one trade ---
for sym in COINS:
    # The FIRST edge is the one repeated, not the last. Under where="post" the value
    # y[i] is held from x[i] to x[i+1], so the leading zero that closes the outline on
    # the left must sit on a zero-width segment at EDGES[0]; repeating the last edge
    # instead gives that zero the whole first bin and slides every bar one bin to the
    # right, which is one fifth of a decade, a factor of 1.585 in dollars.
    axR.step(np.insert(EDGES, 0, EDGES[0]), np.concatenate([[0.0], hist[sym], [0.0]]),
             where="post", color=COIN_COLOUR[sym], lw=1.15, zorder=3,
             label=f"{sym}, median ${size_stats[sym]['quantiles_usd']['p50']:,.0f}")
    axR.axvline(size_stats[sym]["quantiles_usd"]["p50"], color=COIN_COLOUR[sym],
                lw=0.8, ls=(0, (1, 1.6)), zorder=2)

axR.set_xscale("log")
axR.set_xlim(EDGES[0], EDGES[-1])
axR.set_xlabel("notional of one trade, dollars")
# The denominator is named on the axis. Each outline is normalised by its OWN coin's
# trade count, so the two of them sum to two hundred per cent and not one hundred; an
# axis reading "share of trades" invites the reader to add them. The results file has
# carried the longer wording all along and the axis had the short one.
axR.set_ylabel("share of that coin's trades, per cent")
axR.set_title(f"Trade size: the middle {100 - 2 * SPREAD_LO_PCT:.0f} per\ncent "
              f"covers {SPREAD_DECADES_FLOOR} decades of notional")
axR.grid(alpha=0.26)
axR.set_axisbelow(True)
axR.set_ylim(0, float(max(hist[s].max() for s in COINS)) * 1.34)
axR.legend(loc="upper left", frameon=False, handlelength=1.5, borderpad=0.2,
           labelspacing=0.25)
# The dotted verticals are the medians, said once under the legend rather than twice
# beside each line.
axR.text(0.03, 0.795, "dotted: the median of each", transform=axR.transAxes,
         fontsize=PT_NOTE, color="0.3", va="top")

fig.savefig(OUT_PNG, dpi=DPI_OUT)
plt.close(fig)

# ---------------------------------------------------------------------------
# The record. Every number on the picture is here in words, so the figure can be
# checked without measuring pixels.
# ---------------------------------------------------------------------------
results = {
    "caption": CAPTION,
    "caption_numbers_are_asserted": {
        "half_gap_in_trade_count_pct": float(CAPTION_HALF_GAP_PCT),
        "narrower_coin_spread_decades": float(SPREAD_DECADES_MIN),
        "note": "the caption states one per cent and four decades; both are the "
                "rounded form of a quantity computed in this run, and the producer "
                "exits rather than drawing if either rounding stops holding. The gap "
                "quoted is by TRADE COUNT; by money the late half is heavier, and the "
                "caption says count for that reason rather than using one word for "
                "two different answers",
    },
    "figure": {
        "file": os.path.basename(OUT_PNG),
        "panels": {
            "left": {
                "x": "day of month, the ten days of the December window",
                "y_left": "trades per day per coin, thousands, drawn as bars",
                "y_right": "turnover per day per coin, dollars billion, drawn as "
                           "markers on a dashed line",
                "annotation": "a dashed vertical between the last labelling day and "
                              "the first measuring day",
            },
            "right": {
                "x": "notional of a single collapsed taker trade, dollars, "
                     "logarithmic",
                "y": "share of that coin's trades falling in the bin, per cent",
                "annotation": "a dotted vertical at each coin's median",
            },
        },
        "size_in": {"width": WIDTH_IN, "height": HEIGHT_IN, "dpi": DPI_OUT},
        "size_px": {"width": int(round(WIDTH_IN * DPI_OUT)),
                    "height": int(round(HEIGHT_IN * DPI_OUT))},
    },
    "tape": {
        "n_fills": N_ROWS,
        "n_takers": int(np.unique(taker_id).size),
        "n_makers": int(np.unique(maker_id).size),
        "days": list(DAYS),
        "coins": COINS,
        "notional_usd_total": float(notional.sum()),
        "unit": "one row is one taker order after the sweep across resting quotes has "
                "been collapsed, not one printed fill",
    },
    "agreement_with_published_figures": {
        "checked": PUBLISHED,
        "note": "the three counts the report states about this tape, recomputed here "
                "from the packed array. A disagreement refuses to draw rather than "
                "annotating the picture, because a figure that draws one population "
                "under the name of another is the error hardest to see afterwards",
    },
    "left_panel_numbers": {
        "per_day": [
            {"day": int(d),
             **{s: {"fills": int(by_day[s]["fills"][i]),
                    "notional_usd": float(by_day[s]["notional_usd"][i])}
                for s in COINS},
             "half": "labelling" if d in EARLY_DAYS else "measuring"}
            for i, d in enumerate(DAYS)
        ],
        "halves": half_stats,
        "late_over_early": {
            "fills": float(RATIO_FILLS),
            "notional": float(RATIO_NOTIONAL),
            "note": "the comparability the out-of-sample design needs, as a ratio. "
                    "Neither is a test and neither is claimed as one: the halves are "
                    "two fixed calendar stretches and not a sample, so what these say "
                    "is how alike the two stretches were and nothing about why",
        },
        "two_days_are_short_and_the_input_is_not": {
            "short_days": [int(d) for i, d in enumerate(DAYS)
                           if FILLS_TOTAL_BY_DAY[i] < 0.6 * float(
                               np.median(FILLS_TOTAL_BY_DAY))],
            "hourly_files_expected_per_day": HOURS_EXPECTED,
            "days_with_fewer": hour_shortfalls,
            "note": "two days carry roughly a third of a typical day's trades. That is "
                    "the market and not a partial read: the builder recorded all "
                    f"{HOURS_EXPECTED} hourly source files on every one of the "
                    f"{len(DAYS)} days, and the row count of this array equals the "
                    "count the builder wrote down. Both are asserted above and the "
                    "producer exits rather than drawing if either fails",
        },
    },
    "right_panel_numbers": {
        "per_coin": size_stats,
        "bin_grid": {"bins_per_decade": BINS_PER_DECADE, "n_bins": N_BINS,
                     "lo_usd": float(EDGES[0]), "hi_usd": float(EDGES[-1])},
        "why_a_distribution_and_not_a_mean": (
            "the mean of a trade's notional exceeds its median by a factor of "
            + ", ".join(f"{size_stats[s]['mean_over_median']:.0f} on {s}"
                        for s in COINS)
            + ", so a single central figure describes no trade on this tape"),
        "what_this_panel_does_not_explain": (
            "the report states elsewhere that the top decile of ranked wallets holds "
            "56.2 per cent of the late-half fills. That is a property of how many "
            "fills each WALLET does; this panel measures how large each FILL is. They "
            "are different quantities on the same tape, and nothing here is drawn as a "
            "cause of the other"),
        "the_step_at_ten_dollars_is_observed_and_not_explained": (
            "the bin immediately above ten dollars holds "
            + " and ".join(
                f"{size_stats[s]['share_in_the_bin_above_10_usd']:.1f} per cent of {s}"
                for s in COINS)
            + " trades, and below ten dollars the shares fall to "
            + " and ".join(f"{size_stats[s]['share_under_10_usd']:.2f} per cent on {s}"
                           for s in COINS)
            + ". A step that sharp is the signature of a rule rather than of behaviour, "
              "but no minimum order value is documented anywhere in this repository, so "
              "the step is recorded as measured and no cause is asserted for it. The "
              "step is not the same thing as the mode: the tallest bin is "
            + " and ".join(
                f"${size_stats[s]['tallest_bin']['from_usd']:,.0f} to "
                f"${size_stats[s]['tallest_bin']['to_usd']:,.0f} on {s} at "
                f"{size_stats[s]['tallest_bin']['share_pct']:.1f} per cent"
                for s in COINS)
            + ", so the two coins put their mode in different places and only one of "
              "them puts it at the floor"),
        "deliberately_absent": (
            "no cumulative-share curve against ranked counterparties and no "
            "single-number inequality index. That question was settled against "
            "drawing it, and a picture would reopen it without saying so. This panel "
            "is about the size of a trade and says nothing about who did it"),
    },
    "predicate_calibration": {
        "selector": "day == d over the day column of the packed array",
        "must_find": {"day": CALIB_PRESENT, "rows": calib_hit},
        "must_stay_silent": {str(k): v for k, v in calib_miss.items()},
        "note": "a per-day count is only evidence once the selector has been shown one "
                "day it has to find and two it has to miss. Both sides are asserted "
                "before any bar is drawn, so ten empty bars cannot be published as ten "
                "measured ones",
    },
    "what_is_not_drawn": {
        "time_of_day": "the tape read here carries a day column and no intraday clock, "
                       "so a day is the finest grain this file can draw. The companion "
                       "array that does carry one holds a different population from "
                       "the one the report publishes on, and a panel mixing two "
                       "populations under one caption would be worse than no panel",
        "the_resting_book": "this figure is the executed tape only. What was quoted "
                            "and not hit is a separate question with its own figure",
        "uncertainty": "nothing here is an estimate, so nothing carries an interval: "
                       "every number is a count or a quantile of the whole population "
                       "named in scope, and there is no sampling step to put a band on",
    },
}

scope_block = {
    "population": (
        f"every collapsed taker trade on the tape, {N_ROWS:,} of them across "
        f"{int(np.unique(taker_id).size):,} taker wallets and "
        f"{int(np.unique(maker_id).size):,} maker wallets. No fill floor, no wallet "
        f"floor and no horizon applies: this is the tape itself and not a slice of it, "
        f"which makes it a WIDER population than any results block measured on ranked "
        f"wallets. One row is one taker order after its sweep across resting quotes has "
        f"been collapsed, so this count is trades and not printed fills"),
    "window": (
        f"single December window, days {DAYS[0]} to {DAYS[-1]} of the month; days "
        f"{EARLY_DAYS[0]}-{EARLY_DAYS[-1]} label the wallets elsewhere in the report "
        f"and the disjoint days {LATE_DAYS[0]}-{LATE_DAYS[-1]} carry the measurement, "
        f"and the panel draws the line between them"),
    "coins": COINS,
}

settings_used = dict(
    lens=None,
    master_seed=None,
    n_perm=None,
    n_boot=None,
    rank_floor_fills=None,
    min_common_wallets=None,
    early_days=list(EARLY_DAYS),
    late_days=list(LATE_DAYS),
    override_reasons={
        "lens": "no markout is drawn, so no reference price applies; the panels carry "
                "counts, turnover and trade size, none of which is measured against a "
                "price at a later moment",
        "master_seed": "no random stream is drawn: every number is a count or a "
                       "quantile of the whole population",
        "n_perm": "no permutation null is computed here",
        "n_boot": "no interval is computed here",
        "rank_floor_fills": "no wallet floor applies: the figure draws every trade on "
                            "the tape, which is the point of it",
        "min_common_wallets": "no two-half wallet overlap is required: this file draws "
                              "the halves side by side and joins nothing across them",
    },
    overrides_note=(
        "the horizon is stated by the fingerprint as the headline one and is not used: "
        "nothing on either panel is measured at a horizon. The day split is NOT typed "
        "in this file, it is settings.split_early_late over the days present, and the "
        "producer refuses to draw unless settings.day_split_agrees confirms the two "
        "tuples it is about to label"),
)

artifact.write(os.path.basename(OUT_JSON), results,
               script=__file__, inputs=[SRC_NPZ, SRC_SUMMARY], scope=scope_block,
               settings=settings_used, started=T0,
               out_dir=os.path.dirname(OUT_JSON))

print(f"[d2] wrote {os.path.basename(OUT_PNG)} at "
      f"{int(round(WIDTH_IN * DPI_OUT))}x{int(round(HEIGHT_IN * DPI_OUT))} px "
      f"and {os.path.basename(OUT_JSON)}")
print(f"[d2] tape: {N_ROWS:,} collapsed trades, "
      f"{int(np.unique(taker_id).size):,} takers, "
      f"{int(np.unique(maker_id).size):,} makers, days {DAYS[0]}-{DAYS[-1]}, "
      f"{', '.join(COINS)}")
print(f"[d2] published figures agree: "
      + ", ".join(f"{k} {v['recomputed']:,}" for k, v in PUBLISHED.items()))
print(f"[d2] labelling half {half_stats['early']['fills']:,} trades and "
      f"${half_stats['early']['notional_usd'] / USD_BN:.2f} bn against measuring half "
      f"{half_stats['late']['fills']:,} and "
      f"${half_stats['late']['notional_usd'] / USD_BN:.2f} bn; "
      f"late over early {RATIO_FILLS:.4f} by trades and {RATIO_NOTIONAL:.4f} by money")
for i, d in enumerate(DAYS):
    print(f"[d2]   day {d:2d} {'label ' if d in EARLY_DAYS else 'measure'}  "
          + "  ".join(f"{s} {by_day[s]['fills'][i]:7,} trades "
                      f"${by_day[s]['notional_usd'][i] / USD_M:8,.1f}m"
                      for s in COINS))
for s in COINS:
    q = size_stats[s]["quantiles_usd"]
    print(f"[d2] {s} trade size: median ${q['p50']:,.0f}, "
          f"p1 ${q['p1']:,.0f}, p99 ${q['p99']:,.0f}, max ${q['p100']:,.0f}; "
          f"mean over median {size_stats[s]['mean_over_median']:.0f}x; "
          f"central 98 per cent spans "
          f"{size_stats[s]['spread_decades_central_98pct']:.2f} decades")
print(f"[d2] day selector calibrated: day {CALIB_PRESENT} found {calib_hit:,} rows, "
      f"days {CALIB_ABSENT[0]} and {CALIB_ABSENT[1]} found "
      f"{calib_miss[CALIB_ABSENT[0]]} and {calib_miss[CALIB_ABSENT[1]]}")
print(f"[d2] caption ({len(CAPTION.split())} words): {CAPTION}")
