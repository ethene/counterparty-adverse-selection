#!/usr/bin/env python3
"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-08-03
References: Hyperliquid Level-4 order-book data, Zenodo 18184441 (Albers et al. 2026).

The horizon-choice figure (reads ws1_horizon_results.json, no recompute).

ws1_horizon_choice.png, two panels one above the other:
  Panel A: persistence of toxicity from the early to the late window, against horizon
           (why the sixty-second rung is dropped).
  Panel B: value-weighted markout LEVEL against horizon (why one second is too short).
Together they justify the ten-second scoring window and dropping sixty.

DRAWN AT THE SIZE IT IS PRINTED, since 2026-08-08. The canvas is the width of the text
column of the report, 5.5 inches, and every point size named below is the size a reader
of the page sees. It used to be drawn on an 8.5-inch canvas and placed at 4.1 inches,
a reduction to 48 per cent that takes the type down with everything else: the tick
labels were left at the ten-point default and reached the page under five points beside
eleven-point body text. Nothing chosen at placement time can undo that, because by then
the type is part of the picture. A figure has one legible size, so it is drawn at it.
Two panels go one above the other and never side by side, because half of a 5.5-inch
column is not wide enough to carry an axis.

EVERY LABEL IS WRITTEN OUT. The axis labels and panel titles used to carry an ASCII
arrow, an internal work-stream tag and three abbreviations, all of which ask a reader
of the report to know something that is not on the page. A figure owes its reader axes,
labels and scales, and every graph carries a title and readable axis labels.

WHAT THIS FILE STOPPED DRAWING ON 2026-08-08. It also wrote a standalone persistence
curve. That figure read the same artifact and drew the same six series as Panel A,
adding only a vertical line at one second, so the report showed one panel twice and the
second copy earned nothing. The report keeps Panel A and drops the standalone curve, so
nothing here draws it any more and the file it wrote has been removed from the tree.

WHY THE DRAWING SITS APART FROM THE COMPUTATION. Until 2026-08-03 a WS1 figure was
drawn inside ws1_horizon_persistence.py, the node that computes the results file, and
that cost it two ways. Redrawing meant recomputing, at a recorded 302.3 seconds. And
the drawing sat behind a catch that printed one line and returned zero, so when the
launch form resolved no matplotlib the node wrote a fresh results file, said "plot
skipped", exited clean and left a two-day-old figure standing beside numbers that had
moved. A figure that fails to be drawn must not be able to hide inside the exit code of
a computation that succeeded. Drawn here, from the artifact rather than from memory, it
has an exit code of its own, it costs half a second, and it says the same thing the
file it reads says.

The figure reads ONE artifact and computes nothing, so it needs no panel, no tape and
no arguments. This file takes no command line at all, deliberately: build.py refuses a
bare run to any producer that reads one, and a figure has nothing to choose.
"""
import os, json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

HERE = os.path.dirname(os.path.abspath(__file__))
R = json.load(open(os.path.join(HERE, "ws1_horizon_results.json")))
GRID = R["grid_s"]
H_CHOSEN = R["final_decision"]["recommended_score_horizon_s"]

# The printed geometry, in one place, because a size named twice is a size that drifts.
# WIDTH_IN is the text column of the report and DPI_OUT the density it is saved at; the
# point sizes are read off the page, not off the screen. Tick labels are set here rather
# than at each call because set_xticklabels below takes its size from the defaults, so a
# size passed only to the axis labels would leave the numbers under the axis at ten.
WIDTH_IN, HEIGHT_IN, DPI_OUT = 5.5, 7.0, 200
PT_LABEL, PT_TITLE, PT_LEGEND, PT_NOTE = 8, 9, 7.5, 8
plt.rcParams.update({"font.size": PT_LABEL,
                     "axes.labelsize": PT_LABEL,
                     "axes.titlesize": PT_TITLE,
                     "xtick.labelsize": PT_LABEL,
                     "ytick.labelsize": PT_LABEL,
                     "legend.fontsize": PT_LEGEND,
                     "figure.titlesize": PT_TITLE})


def secs(h):
    """Spell a horizon with its unit, singular at one.

    The horizons come out of the results file, so no label can type its own number, and
    a label built by f-string alone produced "persistence-rule best 1 seconds" the day
    the rule's argmax landed on the shortest rung of the grid.
    """
    return f"{h} second" if h == 1 else f"{h} seconds"


def disatt(d):
    return [d[str(h)]["rho_disatt"] if d[str(h)] and d[str(h)]["rho_disatt"] is not None else np.nan for h in GRID]


def obs(d):
    return [d[str(h)]["rho_obs"] if d[str(h)] else np.nan for h in GRID]


fig, (axA, axB) = plt.subplots(2, 1, figsize=(WIDTH_IN, HEIGHT_IN), sharex=True)

# Panel A: persistence
lo = [R["pooled"][str(h)]["boot_lo"] if R["pooled"][str(h)] else np.nan for h in GRID]
hi = [R["pooled"][str(h)]["boot_hi"] if R["pooled"][str(h)] else np.nan for h in GRID]
plc = [R["pooled"][str(h)]["placebo_mean"] if R["pooled"][str(h)] else np.nan for h in GRID]
axA.axvspan(5, 10, color="green", alpha=0.08, label="5 to 10 seconds")
axA.plot(GRID, disatt(R["pooled"]), "o-", color="C0", label="pooled, disattenuated")
axA.plot(GRID, obs(R["pooled"]), "s--", color="C1", label="pooled, observed")
axA.fill_between(GRID, lo, hi, color="C1", alpha=0.15, label="observed, 95% confidence band")
axA.plot(GRID, disatt(R["per_coin"]["BTC"]), "^-", color="C2", alpha=0.6,
         label="Bitcoin, disattenuated")
axA.plot(GRID, disatt(R["per_coin"]["ETH"]), "v-", color="C3", alpha=0.6,
         label="Ether, disattenuated")
axA.plot(GRID, plc, ":", color="grey", label="placebo (shuffled)")
axA.axvline(H_CHOSEN, color="k", ls="-", alpha=0.7)
# Both callouts are placed in AXES fractions with the arrow head in data coordinates,
# never at a typed data offset from the point. A typed offset is a second, silent
# dependence on the level of the curve: the July figure put "1s = N% of impact" at
# vw[0] - 0.45 bps, and when the entry-mid fix raised every rung by about 0.177 bps the
# panel's own range tightened and that text landed outside the axes with an arrow
# crossing the whole page. In axes fractions the callout keeps its place whatever the
# numbers do, which is the property a figure regenerated from fresh results needs.
#
# The callout TEXT is built from the same number that places the arrow. It used to read
# "chosen 10s" typed by hand beside an arrow placed at H_CHOSEN, so a horizon that moved
# in the results file would move the arrow and leave the words behind. The dropped rung
# is named once here for the same reason.
H_DROPPED = 60
# The first callout is placed BELOW the curves, not above them. At (0.52, 0.80) in axes
# fractions this text sat underneath the legend and could not be read at all: the legend
# fills the top band of this panel, and spelling the callout out in words rather than as
# "chosen 10s" made it wide enough to reach into that band.
axA.annotate(f"chosen: {secs(H_CHOSEN)}", xy=(H_CHOSEN, 0.53), xycoords="data",
             xytext=(0.26, 0.33), textcoords="axes fraction", fontsize=PT_NOTE,
             arrowprops=dict(arrowstyle="->", color="k"))
# One line, and in the margin under the axis rather than among the curves. Inside the
# data there is one gap this note could sit in, between the lower edge of the confidence
# band and the placebo, and over the horizons it points at that gap measures 0.0422 of a
# correlation unit. Two lines of eight-point text stand 0.28 inches tall, which on a
# panel this size is 0.097 of a correlation unit, so the note is more than twice the hole
# it has to go in. One line halves the height and doubles the width, which is the right
# trade here because width is what this panel has. Below the lowest series there is no
# data to cover at all, so that is where it goes, and the room for it is reserved a few
# lines down rather than taken from the curves.
axA.annotate(f"{secs(H_DROPPED)}: persistence halved, rung dropped",
             xy=(H_DROPPED, R["pooled"][str(H_DROPPED)]["rho_disatt"]),
             xycoords="data", xytext=(0.36, 0.03), textcoords="axes fraction",
             fontsize=PT_NOTE, color="firebrick",
             arrowprops=dict(arrowstyle="->", color="firebrick"))
# WRITTEN OUT, not abbreviated, and with no arrow. This label used to read
# "early->late persistence (Spearman)" and the panel title carried an internal
# work-stream tag, "WS1(A)". Both ask a reader of the report to know something that is
# not on the page: what the arrow stands for, and what a work stream is. A figure owes
# its reader axes, labels and scales, and every graph carries a title and readable axis
# labels.
#
# BROKEN OVER THREE LINES, and the break is what makes it fit rather than a preference.
# A y label is centred on its own axes and grows in both directions from the middle, so
# its LENGTH is bounded by the height of the panel it belongs to and by nothing else. On
# two lines this sentence measured 3.18 inches against a panel 2.60 inches tall, and the
# overflow went where overflow always goes on a centred label: half up and half down, so
# the top of it stood over the panel and into the figure title. Three lines bring it
# inside, and the check is mechanical rather than visual -- the rendered extent of this
# label must stay inside the extent of its own axes, which is asserted after the draw
# below and which is where those two numbers were read off.
axA.set_ylabel("persistence of toxicity from the\n"
               "early to the late window\n"
               "(Spearman rank correlation)")
axA.set_title("Persistence falls as the markout horizon lengthens")
# ROOM IS MADE FOR THE FURNITURE, NOT FOUND FOR IT. The legend holds the same seven
# entries it always did and comes out 3.54 inches wide; what changed on 2026-08-08 is the
# panel under it, from 7.48 inches wide to 4.51. The legend went from covering about half
# the width of the panel to covering four fifths of it, which is what takes the choice
# away from matplotlib: on the old canvas it could be left to find a corner clear of the
# curves and it did, and at four fifths of the width there is no such corner, because
# every series starts in the top left and the only hole inside the data is the sliver
# between the confidence band and the placebo. So the y axis is widened at both ends
# until the drawn data sits in the middle of the panel with a band kept clear above it
# for the legend and a band below it for the margin note. Nothing is rescaled and no
# series is clipped: the same numbers sit at the same places against the same ticks,
# with blank paper added over and under them.
LEGEND_BAND, NOTE_BAND = 0.30, 0.10
_lo, _hi = axA.get_ylim()
# The ticks are taken BEFORE the widening and then frozen, so the axis is ruled over the
# range the data earns and the two blank bands carry no ticks at all. A rank correlation
# cannot pass one, so an automatic tick reading 1.2 would offer the eye a value the
# quantity does not have and leave the reader to work out that the space is for the
# legend. Freezing them takes a locator rather than set_yticks, which widens the view
# again to fit whatever it is handed and would undo the line below it.
_ruled = [t for t in axA.get_yticks() if _lo <= t <= _hi]
_span = (_hi - _lo) / (1.0 - LEGEND_BAND - NOTE_BAND)
_floor = _lo - NOTE_BAND * _span
axA.set_ylim(_floor, _floor + _span)
axA.yaxis.set_major_locator(mticker.FixedLocator(_ruled))
axA.legend(loc="upper center", ncol=2, framealpha=0.9); axA.grid(alpha=0.3)

# Panel B: level term structure
vw = [R["level_termstructure"]["pooled"][str(h)]["vw"] for h in GRID]
plateau = R["final_decision"]["plateau_vw_bps"]
axB.axvspan(5, 10, color="green", alpha=0.08)
axB.plot(GRID, vw, "o-", color="C4", label="pooled value-weighted markout")
axB.axhline(plateau, color="grey", ls="--", alpha=0.7,
            label=f"plateau, about {plateau:.2f} basis points")
axB.axvline(H_CHOSEN, color="k", ls="-", alpha=0.7)
frac1 = R["final_decision"]["info_frac"]["1"]
# Both notes go UNDER the curve, and the legend over it. This panel holds one rising line,
# which cuts the paper into a wedge above, already spoken for by the legend and the
# plateau rule, and a wedge below, empty from the second rung rightward. Both notes used
# to sit at the level of the curve itself rather than clear of it, which reads as a
# placement until the panel narrows: the note naming the chosen horizon ran along the
# curve from the eight-second point to the seventy-second one. Under the line neither
# note has anything to cross.
axB.annotate(f"1 second carries {frac1*100:.0f}% of the impact\n(under-measures the cost)",
             xy=(1, vw[0]),
             xycoords="data", xytext=(0.13, 0.16), textcoords="axes fraction",
             fontsize=PT_NOTE, color="firebrick",
             arrowprops=dict(arrowstyle="->", color="firebrick"))
axB.annotate(f"impounded by about {secs(H_CHOSEN)}",
             xy=(H_CHOSEN, R["level_termstructure"]["pooled"][str(H_CHOSEN)]["vw"]),
             xycoords="data", xytext=(0.50, 0.48), textcoords="axes fraction",
             fontsize=PT_NOTE, color="k")
axB.set_xscale("log"); axB.set_xticks(GRID); axB.set_xticklabels(GRID)
axB.set_xlabel("markout horizon after the fill (seconds, logarithmic scale)")
# Two lines for the same reason Panel A's label takes three: the panel is 2.60 inches
# tall and the label is centred on it, so a single line of this sentence would be longer
# than the axis it names.
axB.set_ylabel("value-weighted markout level\n(basis points)")
axB.set_title(f"Permanent price impact is impounded by about {secs(H_CHOSEN)}")
axB.legend(loc="upper left", framealpha=0.9); axB.grid(alpha=0.3)

# Three lines, one clause each. As two lines the middle one measured 6.95 inches at this
# point size against a canvas 5.5 inches wide, and a title that overruns is not shortened
# by the page: matplotlib centres it and lets both ends fall off the paper. Breaking at
# the clause is also where a reader would pause.
sup = fig.suptitle(f"Choosing the toxicity horizon\n"
                   f"the markout level is complete and persistence is still high\n"
                   f"at {secs(H_CHOSEN)}, so the {H_DROPPED}-second rung is dropped",
                   fontsize=PT_TITLE, y=0.997, va="top")
# NO reserved strip is passed here, and passing one is the mistake this line replaces.
# tight_layout of the pinned matplotlib measures the figure title itself and leaves room
# for it, so the rect that used to keep the top of the canvas clear was a second helping
# of the same reservation: the two together opened a band of blank paper between the
# title and Panel A about as tall as the title.
fig.tight_layout()

# THE FIT IS MEASURED, NOT EYEBALLED, because the thing that goes wrong here goes wrong
# silently. A y label longer than its own panel is not clipped and raises nothing: it is
# drawn past the top of the panel, over the figure title, and the file on disk looks like
# a figure until somebody reads it. That is what the two-line version of Panel A's label
# did. Every number this file draws comes out of the results file, so any of these labels
# can grow the day a horizon is renamed, and a guard that runs at drawing time is the
# only one that sees it. Failing prints the expectation, the fact and the place; it does
# not shrink the type to make itself pass, because the point sizes are what the report
# asked for and a label that cannot fit at eight points is a label to rewrite.
fig.canvas.draw()
rend = fig.canvas.get_renderer()
title_floor = sup.get_window_extent(renderer=rend).y0
for panel, where in ((axA, "Panel A"), (axB, "Panel B")):
    label = panel.yaxis.label.get_window_extent(renderer=rend)
    frame = panel.get_window_extent(renderer=rend)
    if label.y1 > frame.y1 or label.y0 < frame.y0:
        raise SystemExit(
            f"{where}: the y axis label is taller than the panel it names. "
            f"expected the label inside {frame.y0:.0f} to {frame.y1:.0f} pixels, "
            f"found {label.y0:.0f} to {label.y1:.0f}. Break the label onto one more "
            f"line: ws1_plot.py, {where} set_ylabel")
    if label.y1 > title_floor:
        raise SystemExit(
            f"{where}: the y axis label reaches into the figure title. expected the "
            f"label below {title_floor:.0f} pixels, found its top at {label.y1:.0f}. "
            f"Break the label onto one more line: ws1_plot.py, {where} set_ylabel")

out = os.path.join(HERE, "ws1_horizon_choice.png")
fig.savefig(out, dpi=DPI_OUT)
# Printed relative to this file. The console line used to carry the absolute path, which
# puts a local home directory into any log that captures the run, and a log that lands in
# the tree is a tracked text file the absolute-path guard then has to catch.
print(f"wrote {os.path.relpath(out, HERE)}")
