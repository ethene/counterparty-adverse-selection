"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-21
References: Hyperliquid Level-4 order-book data, Zenodo 18184441 (Albers et al. 2026).

Problem-statement figure. Motivates the counterparty-resolution premise: a small,
OUT-OF-SAMPLE-identified set of counterparties is far more toxic (higher adverse-selection
markout) than the rest, robustly across two independent price references.

Reproducible: reads the verified per-fill markout arrays (no S3 re-pull) and regenerates
the figure deterministically. Toxic label is set on the EARLY half of the window and the cost
is measured on the disjoint LATE half, so the separation is out-of-sample. The halves are cut
by settings.split_early_late over the days the input carries, which on this December window
resolves to days 4-8 and 9-13.
"""
import os
import sys
import textwrap

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
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Taken before the panels are opened, so the recorded cost is the whole node and not
# the drawing alone. Until 2026-08-03 this file wrote no results file at all, and the
# consequences ran further than a missing number. Nothing anywhere recorded the lens,
# the horizon, the column or the window split the head figure of the study is drawn
# under, so its own caption had to say so aloud; the freshness guards, which compare an
# artifact against its producer, had no artifact here to compare and were blind to the
# node by construction; and the node had no recorded price, so any plan that summed the
# cost of redrawing was summing over a hole.
T0 = artifact.start_clock()

# No seed is declared here because nothing in this file draws a random number: the
# decile cut, the two masks and the four volume-weighted means are deterministic
# functions of the input arrays. A SEED = 20260621 used to stand on this line "for
# provenance", read by no expression in the file and differing from the declared
# MASTER_SEED, which is a second home for a load-bearing setting that could never be
# checked against anything, because no result depended on it.
# Per half, both windows: a wallet is kept only with this many fills in the early half
# AND this many in the late one. READ from settings.py and never typed. The declaration
# returns the same 10 this figure has always drawn, so reading it redraws no bar. It is a
# floor on a HALF and therefore a different quantity from RANK_FLOOR_FILLS, which is why
# it is declared per purpose rather than bound to the scalar.
MIN_FILLS = H.wallet_fill_floor("m2_figure", "both_halves")
# The early and late halves are DERIVED from the days the figure's input actually
# carries, by settings.split_early_late, and are never day-of-month bounds typed here.
# The two forms agree on this input and only on it: quickwin_markouts.npz runs 4 to 13,
# so the rule returns 4-8 and 9-13, the bounds this file used to declare.

HERE = os.path.dirname(os.path.abspath(__file__))
# Written BESIDE this file, inside the repository, like every other figure this tree
# produces. It used to be built in a figures directory one level up, which is a directory that
# sits NEXT TO the clone and not in it: this repository's root is the directory this file
# lives in. A reader who cloned the tree and ran this file got FileNotFoundError from
# savefig, because that directory does not exist in a clone and nothing here created it.
# The head figure of the study was therefore the one artifact a stranger could not
# reproduce. The makedirs below is the belt to that braces: HERE always exists, so it is
# a no-op today, and it keeps the guarantee if OUT is ever re-pointed into a subdirectory.
OUT = os.path.join(HERE, "m2_fig1_counterparty_toxicity.png")
# Beside the figure, and named after the producer rather than after the picture: the
# file records what the node computed, and the picture is one of its two outputs.
OUT_JSON = os.path.join(HERE, "m2_figure_results.json")
os.makedirs(os.path.dirname(OUT), exist_ok=True)

# The three panel columns are BUILT from the declared ladder, never typed, so the
# bars and their axis labels cannot drift apart from each other or from the window
# the decile cut below is taken on.
LADDER_PRINT = [H.headline_print_col(h) for h in H.LADDER_S]   # mo1 / mo10 / mo60
LADDER_MID = [H.headline_mid_col(h) for h in H.LADDER_S]       # the book-mid lens
LADDER_LABELS = [str(h) for h in H.LADDER_S]

# The two panels are LOCATED by panel_io rather than joined here, so the one place that
# knows where the markout panels live is the one place that has to change if they move.
# The np.load stays at this call site on purpose: build.py derives an input edge from the
# argument of np.load by folding it to a constant, and a path it cannot fold makes no
# edge at all, so swallowing the load inside the module would cost the dependency graph
# these two edges. panel_io says the same thing in its own docstring.
NPZ_PRINT = os.path.join(P.data_root(), "quickwin_markouts.npz")
NPZ_MID = os.path.join(P.data_root(), "quickwin_markouts_mid.npz")
# One worded refusal for a missing panel instead of a bare numpy error: both files are
# gitignored intermediates, so a fresh clone carries neither, and the message names the
# producer to run.
P.require_present("print", NPZ_PRINT)
P.require_present("mid", NPZ_MID)

zp = np.load(NPZ_PRINT)       # trade-print reference
zm = np.load(NPZ_MID)         # book-mid reference (entry-spread inflated level)
tid = zp["taker_id"].astype(np.int64)
day = zp["day"]
notl = zp["notional"].astype(np.float64)
N = tid.max() + 1
EARLY_DAYS, LATE_DAYS = H.split_early_late(np.unique(day))
early = np.isin(day, list(EARLY_DAYS))
late = np.isin(day, list(LATE_DAYS))


def _sumcnt(mask, val):
    m = mask & np.isfinite(val)
    return (np.bincount(tid[m], weights=val[m], minlength=N),
            np.bincount(tid[m], minlength=N).astype(float))


# OOS toxic label: rank wallets by EARLY-window mean trade-print headline markout; top decile = toxic.
# The decile CUT is taken on the headline window; the panels below then show all three
# rungs of the ladder for the wallets that cut selects.
mo_head_print = zp[H.headline_print_col()].astype(np.float64)
se, ce = _sumcnt(early, mo_head_print)
sl, cl = _sumcnt(late, mo_head_print)
q = (ce >= MIN_FILLS) & (cl >= MIN_FILLS)
em = np.full(N, np.nan)
em[q] = se[q] / ce[q]
thr = np.nanquantile(em[q], 0.90)
is_tox = np.zeros(N, bool); is_tox[q & (em >= thr)] = True
is_ben = np.zeros(N, bool); is_ben[q & (em < thr)] = True
tox_f = late & is_tox[tid]
ben_f = late & is_ben[tid]


def vw(fmask, arrs):
    out = []
    for a in arrs:
        a = a.astype(np.float64)
        m = fmask & np.isfinite(a)
        out.append(np.sum(a[m] * notl[m]) / np.sum(notl[m]))
    return np.array(out)


print_tox = vw(tox_f, [zp[c] for c in LADDER_PRINT])
print_ben = vw(ben_f, [zp[c] for c in LADDER_PRINT])
mid_tox = vw(tox_f, [zm[c] for c in LADDER_MID])
mid_ben = vw(ben_f, [zm[c] for c in LADDER_MID])
n_tox, n_ben = int(is_tox.sum()), int(is_ben.sum())
# The headline separation is computed ONCE, here, and used by both the caption and the
# results file. Computing it twice would put the study's motivating number in two places
# inside one script, which is the shape that let the caption say "about +1.2 bps" while
# the bars above it drew twice that.
_HEAD = H.LADDER_S.index(H.HEADLINE_HORIZON_S)
_gap_print = float(print_tox[_HEAD] - print_ben[_HEAD])
_gap_mid = float(mid_tox[_HEAD] - mid_ben[_HEAD])
_rungs = "/".join(str(h) for h in H.LADDER_S)
print(f"trade-print toxic {_rungs}:", np.round(print_tox, 2), "benign:", np.round(print_ben, 2))
print(f"book-mid    toxic {_rungs}:", np.round(mid_tox, 2), "benign:", np.round(mid_ben, 2))
print("n_tox", n_tox, "n_ben", n_ben)

# =====================================================================
# THE DRAWING IS DONE AT THE SIZE IT IS READ AT, and every point size below is the size
# on paper. This figure used to be drawn on a canvas 10.4 inches wide and then placed in
# a report column 4.1 inches wide, so the page shrank it by two and a half: the numbers
# printed over its bars were set at 8.5 points and reached the reader at 3.4, against
# body text of 11. Nothing about those numbers was small in the file, which is why no
# check and no reading of the code could ever have caught it -- they were small in the
# only place the figure is looked at. The canvas is therefore declared near the width it
# is placed at, and the sizes below are stated once, in points, rather than spelled at
# each call site where they could drift apart.
# =====================================================================
WIDTH_IN, HEIGHT_IN, DPI_OUT = 5.5, 6.2, 200
PT_AXIS = 8         # axis labels and the tick labels under them
PT_PANEL = 9        # the title over one panel
PT_LEGEND = 7.5
PT_VALUE = 7.5      # the value printed at the end of each bar
PT_NOTE = 8         # the caption lines under the panels
PT_SUPTITLE = 9.5   # the sentence the figure is drawn to support
plt.rcParams.update({"axes.labelsize": PT_AXIS,
                     "xtick.labelsize": PT_AXIS,
                     "ytick.labelsize": PT_AXIS})

# STACKED, NOT SIDE BY SIDE. On a canvas this wide two panels in a row would leave each
# of them about two inches once the vertical axis label and its ticks are paid for, and
# three pairs of bars with a value printed at every end do not fit in two inches. One
# under the other, each panel keeps the full width. Nothing is lost by the stack: the
# two panels are deliberately on DIFFERENT vertical scales, since the book-mid lens sits
# higher by the taker's own entry spread, so they were never meant to be read across.
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(WIDTH_IN, HEIGHT_IN))
x = np.arange(len(H.LADDER_S)); w = 0.38
labels = LADDER_LABELS
TOX, BEN = "#c0392b", "#2471a3"

R = fig.canvas.get_renderer()


def _frac_w(px):
    """Display pixels across, as a fraction of the canvas. Free of the output density."""
    return px / (fig.get_figwidth() * fig.dpi)


def _frac_h(px):
    return px / (fig.get_figheight() * fig.dpi)


def _pt_h(pt):
    """A height stated in points, as a fraction of the canvas."""
    return _frac_h(pt * fig.dpi / 72.0)


def _fits(s, fontsize, frac):
    """True when s, set at this size, MEASURES narrower than frac of the canvas."""
    t = fig.text(0, 0, s, fontsize=fontsize)
    inside = _frac_w(t.get_window_extent(renderer=R).width) <= frac
    t.remove()
    return inside


def wrap_to(s, fontsize, frac):
    """Break s into the fewest lines whose widest one still measures inside frac.

    The break is found by measuring rather than by a typed column count, for the same
    reason the vertical ceiling inside panel() is taken from the tallest bar: every
    caption line and both legend labels on this figure are BUILT from the numbers this
    run drew, so a column count tuned by hand to today's strings holds only until a
    value gains a digit. The search keeps a candidate only when EVERY one of its lines
    measures inside the budget, so a step where a wider allowance happens not to widen
    the longest line costs one extra line and never an overflow.
    """
    if _fits(s, fontsize, frac):
        return s
    lo, hi, best = 1, len(s), "\n".join(textwrap.wrap(s, 1))
    while lo <= hi:
        mid = (lo + hi) // 2
        cand = "\n".join(textwrap.wrap(s, mid))
        if all(_fits(ln, fontsize, frac) for ln in cand.split("\n")):
            best, lo = cand, mid + 1
        else:
            hi = mid - 1
    return best


def value_label(ax, xpos, v, span):
    """The bar's value, set clear of the bar rather than over it.

    Both labels used to be offset UPWARD from the bar's end. For a bar drawn below zero
    that puts the text inside the bar's own dark fill, which is where all three negative
    trade-print values sat, printed dark on dark. The offset now follows the sign, and
    the room for it is reserved at whichever end of the panel it is needed.
    """
    off = 0.02 * span
    ax.text(xpos, v + off if v >= 0 else v - off, f"{v:.2f}", ha="center",
            va="bottom" if v >= 0 else "top", fontsize=PT_VALUE)


def panel(ax, tox, ben, title):
    """One reference lens. The vertical range is DERIVED from the bars it has to hold.

    The two panels used to be given a typed ceiling, 2.0 on the trade-print one and 3.7
    on the book-mid one, tuned by hand to the numbers of the day they were typed. When
    the entry-mid fix of 2026-08-02 raised the levels, the tallest bar of each panel grew
    past its ceiling and was drawn CUT OFF at the top with its value overlapping the panel
    title: 2.11 against a ceiling of 2.0, and 3.92 against 3.7. A figure that silently
    truncates the bar carrying its own headline is worse than one that is merely stale,
    so the ceiling now comes from the tallest bar and the room for its label.
    """
    top = float(max(tox.max(), ben.max()))
    bottom = float(min(0.0, tox.min(), ben.min()))
    span = max(top - bottom, 1e-9)
    ymax = top + 0.14 * span            # room for the value printed above the tallest bar
    # The floor buys the same room only when there is something hanging below zero to
    # need it: a panel whose bars are all positive would otherwise be given a strip of
    # empty space it never uses, and on a stacked layout that space comes off the bars.
    ymin = bottom - (0.14 if bottom < 0 else 0.05) * span
    ax.bar(x - w / 2, tox, w, color=TOX)
    ax.bar(x + w / 2, ben, w, color=BEN)
    for i, (t, b) in enumerate(zip(tox, ben)):
        value_label(ax, i - w / 2, t, span)
        value_label(ax, i + w / 2, b, span)
    ax.axhline(0, color="0.6", lw=0.7)
    ax.set_xticks(x); ax.set_xticklabels(labels)
    # The unit belongs on the axis label rather than repeated on every tick: a figure
    # owes its reader axes, labels and scales, and an axis whose
    # unit lives only in the tick text is one relabelling away from carrying none.
    ax.set_xlabel("Markout horizon after the fill (seconds)")
    ax.set_ylim(ymin, ymax)
    # Measured against the axes rather than the canvas, because a panel title is centred
    # on its own panel and the vertical axis label and ticks stand outside it.
    ax.set_title(wrap_to(title, PT_PANEL, 0.86), fontsize=PT_PANEL)


panel(ax1, print_tox, print_ben, "Trade-print reference (conservative)")
panel(ax2, mid_tox, mid_ben, "Book-mid reference (level inflated by entry spread)")
handles = [plt.Rectangle((0, 0), 1, 1, color=TOX),
           plt.Rectangle((0, 0), 1, 1, color=BEN)]

# =====================================================================
# THE BANDS ABOVE AND BELOW THE PANELS ARE MEASURED, NOT TYPED. What is left over is
# handed to tight_layout as the rectangle the panels may use. The band used to be the
# constant rect=[0, 0.098, 1, 0.885], fitted by hand to the strings of the day it was
# written; but the caption lines and the legend labels are built from the numbers this
# run drew, and the title now has to be broken over more than one line at this width, so
# a typed band is a second home for a length that only the renderer knows.
# =====================================================================
# THE HEADLINE SENTENCE IS SET AS FIGURE TEXT RATHER THAN AS A SUPTITLE, and the choice
# is not cosmetic. tight_layout keeps room for a suptitle of its own accord, so a suptitle
# whose height has ALREADY been taken out of the rectangle handed to it is paid for twice
# and the panels are pushed down by it for nothing. Measured on this very layout: the top
# panel's bounding box reached 0.778 of the canvas with the suptitle present and 0.857
# with it removed, against a rectangle whose top was 0.881. Plain figure text is what
# tight_layout ignores, which is what leaves the band under this file's own control -- the
# same reason the caption lines below are figure text, so one rule now places all of them.
title_text = fig.text(
    0.5, 1.0 - _pt_h(4),
    wrap_to("A small, out-of-sample-identified set of counterparties is far more toxic "
            "than the rest", PT_SUPTITLE, 0.94),
    ha="center", va="top", fontsize=PT_SUPTITLE)
y_top = 1.0 - _pt_h(4) - _frac_h(title_text.get_window_extent(renderer=R).height) - _pt_h(5)
legend = fig.legend(handles,
                    [f"Toxic decile (top 10%, n={n_tox:,})",
                     f"Remaining counterparties (n={n_ben:,})"],
                    loc="upper center", ncol=2, fontsize=PT_LEGEND,
                    bbox_to_anchor=(0.5, y_top))
# A legend knows its own size only once it has been placed, so the height it costs is
# read after a render rather than guessed from the number of rows.
fig.canvas.draw()
y_top -= _frac_h(legend.get_window_extent(R).height) + _pt_h(6)

# All three caption lines are BUILT from what the figure drew. They used to be typed, and
# both of the first two had gone wrong in the way a typed caption does. The day bounds
# were spelled 4-8 and 9-13 while the file's own rule derives them from the input, so the
# caption was a second home for the split. And "about +1.2 bps" named no rung and no lens:
# 1.2 is the trade-print gap at ONE second, while the study's headline rung is ten
# seconds, where the same figure draws a gap twice that. A number can be right and still
# be about something other than the sentence it stands in, and arithmetic never catches
# that.
_D = lambda days: f"{min(days)}-{max(days)}"
captions = [
    (f"Hyperliquid BTC+ETH, December 2025. Toxic decile labelled on days "
     f"{_D(EARLY_DAYS)}; adverse-selection cost measured on the disjoint days "
     f"{_D(LATE_DAYS)}."),
    # THE SECOND LINE SAYS WHOSE POPULATION THIS IS, and it is not the study's headline
    # one. A wallet enters here only with MIN_FILLS fills in EACH half, which is the
    # declared floor applied to HALF the window rather than the headline floor applied to
    # the whole of it, and that is why the two groups count 550 and 4,943 rather than the
    # numbers the rest of the report carries. A caption that omits this leaves a reader to
    # assume one population where there are two, and no arithmetic check would ever catch
    # it, because every number on the figure is correct for the population it was taken on.
    (f"A wallet enters only with at least {MIN_FILLS} fills in EACH half, so these two "
     f"groups stand on a per-half floor and not on the whole-window one."),
    (f"At the {H.HEADLINE_HORIZON_S}-second headline horizon the toxic-vs-rest "
     f"separation is {_gap_print:+.2f} basis points under the trade-print reference and "
     f"{_gap_mid:+.2f} basis points under the book-mid reference."),
]
# Laid out from the bottom up, so each line stands on the height the one below it took
# rather than on a position typed for it.
y_bottom = _pt_h(4)
for caption in reversed(captions):
    block = fig.text(0.5, y_bottom, wrap_to(caption, PT_NOTE, 0.96), ha="center",
                     va="bottom", fontsize=PT_NOTE, linespacing=1.30)
    y_bottom += _frac_h(block.get_window_extent(renderer=R).height) + _pt_h(3)
y_bottom += _pt_h(3)

# THE UNIT SITS IN PARENTHESES, which is the form the report template asks for and not a
# matter of taste: "If including units in the label, present them within parentheses."
# Written after a comma, as this label read until 2026-08-04, the unit reads as a second
# clause of the quantity's name rather than as the scale the numbers are counted in.
#
# THE LABEL IS ROTATED, SO WHAT HAS TO FIT IS ITS LENGTH AGAINST THE PANEL'S HEIGHT, and
# at this canvas size the unbroken sentence is longer than a panel is tall. A rotated
# label longer than its own panel does not merely look cramped: tight_layout counts the
# overflow as part of the panel and pulls the panel in to make room for it, so the first
# drawing at this size lost a band of canvas to empty space AND still had the upper label
# crossing the panel above it and the lower one crossing the caption below. The budget is
# half of the band the two panels share -- converted from a height into the width the
# measuring helper reads -- and taken at four fifths of that half, because the panel
# title, the tick labels and the horizontal label are all paid for out of the same half.
# It is set here rather than beside the panels because the band is only known by now, and
# it is set BEFORE tight_layout because the horizontal room a two-line rotated label needs
# is twice a one-line one's, and tight_layout is what reserves it.
YLABEL = wrap_to("Volume-weighted mean markout (basis points)", PT_AXIS,
                 0.8 * ((y_top - y_bottom) / 2) * HEIGHT_IN / WIDTH_IN)
ax1.set_ylabel(YLABEL)
# The lower panel carried no vertical-axis label at all while the two stood side by side.
# It cannot borrow the other one: the two panels are on DIFFERENT scales, precisely
# because the book-mid lens sits higher by the taker's own entry spread, so a reader who
# takes one label to cover both is being told the two heights are comparable when they
# are not. Stacking them puts the two scales one under the other, where that reading is
# easier to fall into and not harder, so the label is repeated rather than shared.
ax2.set_ylabel(YLABEL)

fig.tight_layout(rect=[0, y_bottom, 1, y_top])
fig.savefig(OUT, dpi=DPI_OUT)
# Printed relative to this file, so the line names the target without putting a local
# home directory into the console output or into any log that captures it.
print("saved", os.path.relpath(OUT, HERE))

# =====================================================================
# THE RESULTS FILE. Every number below is one this figure DRAWS, read out of the same
# variables the bars and the caption are built from, so the artifact and the picture
# cannot disagree by construction.
#
# The keys carry the lens and the rung, and that is not decoration. This study reads
# two reference prices whose levels differ by the taker's own entry spread, and a bare
# key holding "the toxic markout" would be a value whose meaning depends on a setting
# recorded somewhere else. The nesting is lens, then group, then horizon in seconds.
# =====================================================================
_rung_map = lambda arr: {str(h): float(v) for h, v in zip(H.LADDER_S, arr)}
results = {
    "headline_horizon_s": H.HEADLINE_HORIZON_S,
    "ladder_s": [int(h) for h in H.LADDER_S],
    "vw_markout_bps": {
        "trade_print": {"toxic_decile": _rung_map(print_tox),
                        "remaining": _rung_map(print_ben)},
        "book_mid": {"toxic_decile": _rung_map(mid_tox),
                     "remaining": _rung_map(mid_ben)},
    },
    "separation_bps": {
        "trade_print": {str(h): float(t - b) for h, t, b
                        in zip(H.LADDER_S, print_tox, print_ben)},
        "book_mid": {str(h): float(t - b) for h, t, b
                     in zip(H.LADDER_S, mid_tox, mid_ben)},
    },
    # Named apart from the ladder above because this is the pair the caption publishes
    # and the report quotes, and a reader should not have to know which rung is the
    # headline one to find them.
    "headline_separation_bps": {"trade_print": _gap_print, "book_mid": _gap_mid},
    "labelling": {
        "rank_column": H.headline_print_col(),
        "rank_window": "early half",
        "measurement_window": "late half",
        "top_quantile": 0.90,
        "threshold_bps": float(thr),
        "min_fills_per_half": int(MIN_FILLS),
        # THE FLOOR THIS FIGURE IS NOT DRAWN AT, carried as a number beside the one it
        # is drawn at. The two are different quantities -- a floor on a HALF against a
        # floor on the whole window -- and the population sentence in the scope says so;
        # saying so while naming only one of the two numbers leaves the reader to take
        # the difference on trust when the file can simply state it.
        "whole_window_rank_floor_fills": int(H.RANK_FLOOR_FILLS),
        "floor_predicate": (
            f"a wallet enters only with at least {MIN_FILLS} fills in the early half "
            f"AND at least {MIN_FILLS} in the late half, which is "
            f"settings.wallet_fill_floor('m2_figure', 'both_halves'). It is NOT "
            f"settings.RANK_FLOOR_FILLS, which is {H.RANK_FLOOR_FILLS} fills over the "
            f"whole window and is what the rest of the study scores at"),
        "early_days": [int(d) for d in EARLY_DAYS],
        "late_days": [int(d) for d in LATE_DAYS],
    },
    "n_wallets": {"toxic_decile": n_tox, "remaining": n_ben},
    "interpretation": (
        "A decile of counterparties ranked on the EARLY half of the window stays more "
        "costly on the disjoint LATE half, under two reference prices that differ by "
        "the taker's own entry spread. The separation, not the level, is what the two "
        "lenses agree on: the book-mid level sits higher by that spread throughout."),
}
# THE POPULATION IS STATED, NEVER INFERRED, and it is not the study's headline one.
# A wallet enters this figure only with MIN_FILLS fills in EACH half, which is the
# declared floor applied to a HALF of the window rather than the headline floor applied
# to the whole of it. The two counts below therefore belong to this figure alone, and a
# reader comparing them with the counts elsewhere in the report is comparing two
# populations that were never the same one.
scope_block = {
    "population": (
        f"taker fills of the two markout panels aggregated to wallets; {n_tox + n_ben} "
        f"wallets are eligible, needing at least {MIN_FILLS} fills in EACH half of the "
        f"window, and the top decile by early-half mean markout holds {n_tox} of them "
        f"against {n_ben} in the rest. This per-half floor is a DIFFERENT quantity from "
        f"settings.RANK_FLOOR_FILLS, which is a floor on the whole window"),
    "window": (f"December 2025, days {_D(EARLY_DAYS)} for labelling and the disjoint "
               f"days {_D(LATE_DAYS)} for measurement, cut by settings.split_early_late "
               f"over the days the input carries"),
    "coins": "BTC and ETH perpetuals",
}
# BOTH LENSES, which is why the field is not one of the two names the rest of the tree
# uses. The panels are the same fills scored against two reference prices, and a
# fingerprint asserting one of them would be false about half the figure.
settings_used = dict(
    h=H.HEADLINE_HORIZON_S,
    lens="print+mid",
    master_seed=None,
    n_perm=None,
    n_boot=None,
    rank_floor_fills=None,
    persistence_floor_fills=None,
    whale_drop_k=None,
    fdr_alpha=None,
    reliability_seed=None,
    early_late_split=(
        f"settings.split_early_late over the days present: "
        f"early {sorted(int(d) for d in EARLY_DAYS)}, "
        f"late {sorted(int(d) for d in LATE_DAYS)}"),
    overrides_note=(
        "lens is BOTH references, because the two panels are the same fills scored "
        "against the trade print and against the book mid, and asserting either alone "
        "would be false about half the figure. The three horizons drawn are "
        "settings.LADDER_S and the decile CUT is taken on the headline print column at "
        f"{H.HEADLINE_HORIZON_S} seconds; horizon_s records that cut and not the ladder. "
        "The fill floor is settings.wallet_fill_floor for this file on BOTH HALVES, "
        "which is a floor on a HALF and therefore not settings.RANK_FLOOR_FILLS; "
        "rank_floor_fills is stated as not applying rather than left to be read as the "
        "declaration. No seed, no permutation, no bootstrap and no whale arm run here: "
        "the decile cut, the two masks and the four volume-weighted means are "
        "deterministic functions of the input arrays, so no random stream is drawn and "
        "no FDR family applies."),
)
artifact.write(os.path.basename(OUT_JSON), results,
               script=__file__, inputs=[NPZ_PRINT, NPZ_MID], scope=scope_block,
               settings=settings_used, started=T0,
               out_dir=os.path.dirname(OUT_JSON))
print("saved", os.path.relpath(OUT_JSON, HERE))
