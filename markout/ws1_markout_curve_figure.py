#!/usr/bin/env python3
"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-08-25
References: Hyperliquid Level-4 order-book data, Zenodo 18184441 (Albers et al. 2026);
the markout arithmetic and the sign convention are those of ws1_horizon_persistence.py,
which writes the results file read here, and of checks/chk_side_signconv.py, which
establishes the aggressor flag empirically from the raw tape.

The post-trade cost curve (reads ws1_horizon_results.json, no recompute).

ws1_markout_curve.png, one panel: how far the mid keeps moving against the market maker
after its quote has been hit, against the time elapsed since the fill, on a logarithmic
time axis. Four series -- the pooled cost per dollar of notional, the pooled cost per
fill, and the cost per dollar on each of the two coins separately.

WHAT THIS ANSWERS THAT Figure 3 DOES NOT, because a figure that repeats one already in
the report costs a page and earns nothing. ws1_horizon_choice.png reads the same file and
draws the level term structure too, but only the pooled value-weighted line of it, and it
draws that line to settle a different question: which horizon the counterparty score
should be read at. The three series it leaves undrawn are the ones that describe the cost
rather than the choice, and each carries a fact the pooled line cannot.

  THE EQUAL-WEIGHTED LINE, beside the value-weighted one, says where the cost sits. At
  the scoring horizon a dollar of notional loses about 1.70 times what the average fill
  loses, so the adverse selection is concentrated in the large fills. One line cannot
  show a ratio between two.

  THE TWO PER-COIN LINES say the cost is not one number. Ether runs close to twice
  Bitcoin at every rung. The report splits the PERSISTENCE by coin already and leaves the
  LEVEL pooled, so as it stands it never says that the exposure being defended against is
  about twice as large on one of the two instruments.

  THE FILL COUNTS, which are not drawn but are asserted below and recorded in the results
  file, are the validation the curve needs to be read at all: across all eight rungs the
  pooled count moves by 482 fills out of 2.48 million, 0.0195 per cent. The curve
  therefore rises because the price moves after the fill and not because the sample
  changes underneath it. A cost curve whose population changed from rung to rung would
  look exactly the same and mean nothing.

WHAT THE QUANTITY IS, since a cost curve is worth nothing if its reference price is not
on the page. The markout is measured FROM THE BOOK MID, not from the trade print: the
entry leg is the top-of-book mid of the last snapshot strictly earlier than the fill, the
horizon leg is the first snapshot at or after the fill plus the horizon, and the result is
in basis points of the entry mid. The distinction is load-bearing in this study, because
the same fills read against the trade print cost about a quarter as much, the difference
being the spread the maker earned; the two references are never set side by side without
saying which is which, and the axis label here names the one it draws.

The SIGN is the taker's. It is positive when the mid moved the way the aggressor was
pointing, and the maker is the other side of that fill, so a positive number is the
maker's loss. Every value drawn here is positive and rising, which is the finding: the
price keeps going against the maker for as long as the grid runs.

The POPULATION is the whole tape -- every taker fill of the ten-day December window with
a finite markout at that rung, both coins. It is NOT the population Figure 3's upper panel
stands on, which is the 5,539 wallet-coin units that clear a ten-fill floor in each half
of the window. The two are different populations answering different questions and no
number from one belongs beside a number from the other.

DRAWN AT THE SIZE IT IS PRINTED, following ws1_plot.py, which established the practice
here after a figure drawn on an 8.5-inch canvas reached the page at 48 per cent and took
its type down with it. The canvas below is the width of the report's single text column
and every point size named is the size a reader of the page sees.

ONE PANEL AND NOT TWO. The report allows a figure 3.5 inches of height. Two panels stacked
inside that leave about 1.35 inches of axes each once the shared axis and its label are
taken out, which is not enough to carry a legend of four entries at a readable size; and
side by side is ruled out by the measurement ws1_plot.py records, that half of this column
is not wide enough to carry an axis at all. So the panel is spent on the half of the
question the report is missing, and the counterparty-ordering half stays where it already
is.

The figure reads ONE artifact and computes only the three summaries it prints, so it needs
no panel, no tape and no arguments, and it takes no command line at all.
"""
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

# artifact.py and the other shared modules sit in the repository root, one directory up
# from this group, so the path is built from this file's own location and never from the
# working directory the run happens to start in.
_CODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CODE_DIR not in sys.path:
    sys.path.insert(0, _CODE_DIR)

import artifact

HERE = os.path.dirname(os.path.abspath(__file__))
IN_NAME = "ws1_horizon_results.json"
OUT_PNG = "ws1_markout_curve.png"
OUT_NAME = "ws1_markout_curve_figure_results.json"

t0 = artifact.start_clock()

import json
with open(os.path.join(HERE, IN_NAME), encoding="utf-8") as fh:
    R = json.load(fh)

GRID = R["grid_s"]
LVL = R["level_termstructure"]
# Both taken from the artifact and never typed. The horizon the study scores at is
# recorded there with its own provenance -- final_decision.recommended_source says it is
# read back out of settings.py so the declaration and the evidence cannot drift -- and a
# number typed here would be a third copy of it, free to fall behind both.
H_CHOSEN = R["final_decision"]["recommended_score_horizon_s"]
PLATEAU = R["final_decision"]["plateau_vw_bps"]
COINS = [name for _, name in sorted(R["coin_map"].items())]

# The printed geometry, in one place, because a size named twice is a size that drifts.
# WIDTH_IN is the single text column of the report and HEIGHT_IN the ceiling a figure is
# allowed there. Tick label sizes are set in the defaults rather than at each call,
# because set_xticklabels below takes its size from them.
WIDTH_IN, HEIGHT_IN, DPI_OUT = 5.53, 3.4, 200
PT_LABEL, PT_TITLE, PT_LEGEND, PT_NOTE = 8, 9, 7, 7.5
plt.rcParams.update({"font.size": PT_LABEL,
                     "axes.labelsize": PT_LABEL,
                     "axes.titlesize": PT_TITLE,
                     "xtick.labelsize": PT_LABEL,
                     "ytick.labelsize": PT_LABEL,
                     "legend.fontsize": PT_LEGEND})


def secs(h):
    """Spell a horizon with its unit, singular at one.

    The horizons come out of the results file, so no label types its own number, and a
    label built by f-string alone would write "1 seconds" the day a caption points at the
    shortest rung of the grid.
    """
    return f"{h} second" if h == 1 else f"{h} seconds"


def series(group, field):
    return [LVL[group][str(h)][field] for h in GRID]


pooled_vw = series("pooled", "vw")
pooled_ew = series("pooled", "ew")
per_coin_vw = {c: series(c, "vw") for c in COINS}
counts = series("pooled", "n")

# THE POOLED LINE IS A BLEND OF THE TWO COIN LINES AND MUST LIE BETWEEN THEM, at every
# rung. This is asserted rather than assumed because it is the one property of this
# figure that can fail while every number still reads cleanly: a value-weighted mean over
# both coins is a convex combination of the two per-coin means with the notional shares
# as weights, so a pooled point outside the pair would mean the three series are not the
# quantity this file says they are -- a group mislabelled, or a weight that is not
# notional. It costs eight comparisons and it is a real two-sided test: the pooled line
# sits nearer the Bitcoin line at every rung, which is the notional share showing
# through, so the check is nowhere near its own boundary by accident.
for i, h in enumerate(GRID):
    lo = min(per_coin_vw[c][i] for c in COINS)
    hi = max(per_coin_vw[c][i] for c in COINS)
    if not (lo <= pooled_vw[i] <= hi):
        raise SystemExit(
            f"the pooled value-weighted markout at {secs(h)} is not a blend of the "
            f"per-coin ones. expected it inside [{lo:.4f}, {hi:.4f}] basis points, "
            f"found {pooled_vw[i]:.4f}. A value-weighted pooled mean is a weighted "
            f"average of the per-coin means, so one of the three groups of "
            f"{IN_NAME}#level_termstructure is not what it is read as here")

# The three summaries this file computes, all of them ratios of numbers it has just read.
# They are printed on the figure and recorded in the results file so that a reader of
# either can check them without the picture.
i_chosen = GRID.index(H_CHOSEN)
vw_over_ew = pooled_vw[i_chosen] / pooled_ew[i_chosen]
coin_hi, coin_lo = (max(COINS, key=lambda c: per_coin_vw[c][i_chosen]),
                    min(COINS, key=lambda c: per_coin_vw[c][i_chosen]))
coin_ratio = per_coin_vw[coin_hi][i_chosen] / per_coin_vw[coin_lo][i_chosen]
count_spread = max(counts) - min(counts)
count_spread_frac = count_spread / max(counts)

fig, ax = plt.subplots(figsize=(WIDTH_IN, HEIGHT_IN))

# Plotted from the most expensive coin down to the cheapest series, so the legend reads
# in the same order the lines sit on the page and a reader never has to match a colour
# across the panel.
ax.plot(GRID, per_coin_vw[coin_hi], "^-", color="C3", alpha=0.85,
        label=f"{coin_hi}, per dollar of notional")
ax.plot(GRID, pooled_vw, "o-", color="C4", lw=1.8,
        label="both coins, per dollar of notional")
ax.plot(GRID, per_coin_vw[coin_lo], "v-", color="C2", alpha=0.85,
        label=f"{coin_lo}, per dollar of notional")
ax.plot(GRID, pooled_ew, "s--", color="C0",
        label="both coins, per fill")
ax.axhline(PLATEAU, color="grey", ls=":", alpha=0.8, lw=1.0)
ax.axvline(H_CHOSEN, color="k", ls="-", alpha=0.6, lw=1.0)

# BOTH NOTES ARE PLACED IN AXES FRACTIONS, never at a typed offset from the point they
# name. A typed offset is a second, silent dependence on the level of the curve, and
# ws1_plot.py records what that costs: an entry-mid fix moved every rung of this same
# quantity by about 0.177 basis points, the panel's range tightened with it, and a note
# placed by offset landed outside the axes with an arrow across the page. Their TEXT is
# built from the same numbers that place them, so a horizon or a plateau that moves
# cannot leave the words behind.
#
# NEITHER NOTE CARRIES AN ARROW, and dropping them is what made the panel readable. The
# thing each note names is already drawn -- a solid rule at the scored horizon, a dotted
# rule at the plateau -- so an arrow adds no information and has to cross three rising
# series to arrive. The first version pointed at the pooled curve from below and its text
# came to rest along the Bitcoin line; the note is now under every series instead, where
# the panel is empty from the scored horizon rightward.
# BOTH NOTES ARE PLACED FURTHER DOWN, after the axis has been widened, because both need
# room that the data does not leave. The room is reserved rather than found: see the
# band block below.

ax.set_xscale("log")
ax.set_xticks(GRID)
ax.set_xticklabels(GRID)
# The minor ticks a logarithmic axis places by default fall between the rungs of a grid
# that is not decade-spaced, so they rule the panel at values the study never measured.
ax.xaxis.set_minor_locator(mticker.NullLocator())
ax.set_xlabel("time elapsed since the fill (seconds, logarithmic scale)")
# WRITTEN OUT rather than abbreviated, and on two lines. The label is centred on its own
# axes and grows both ways from the middle, so its length is bounded by the height of the
# panel and by nothing else; the fit is measured after the draw below rather than judged
# by eye. It names the reference price because a markout without one is not a quantity:
# the same fills read against the trade print come out about a quarter of this.
ax.set_ylabel("price moved against the maker\n"
              "(basis points of the entry mid)")
ax.set_title("How far the price keeps moving after a quote is hit")

# ROOM IS MADE FOR THE LEGEND RATHER THAN FOUND FOR IT. Four entries at seven points come
# out about 2.4 inches wide against a panel of 5.0, and every series here rises from left
# to right, so the upper left -- where matplotlib would put it if left to choose -- is
# where the most expensive coin ends up. The axis is therefore widened at the top until
# the drawn data sits under a clear band. Nothing is rescaled and no series is clipped:
# the same numbers sit at the same places against the same ticks, with blank paper added
# above them.
#
# The ticks are taken BEFORE the widening and then frozen, so the axis is ruled over the
# range the data earns and the blank band carries no ticks at all. Freezing them takes a
# locator rather than set_yticks, which would widen the view again to fit what it is
# handed and undo the line above it.
LEGEND_BAND, NOTE_BAND = 0.28, 0.11
_lo, _hi = ax.get_ylim()
_ruled = [t for t in ax.get_yticks() if _lo <= t <= _hi]
_span = (_hi - _lo) / (1.0 - LEGEND_BAND - NOTE_BAND)
_floor = _lo - NOTE_BAND * _span
ax.set_ylim(_floor, _floor + _span)
ax.yaxis.set_major_locator(mticker.FixedLocator(_ruled))
ax.legend(loc="upper center", ncol=2, framealpha=0.9, handlelength=2.0,
          columnspacing=1.2, borderpad=0.4)
ax.grid(alpha=0.3)

# THE TWO NOTES GO IN THE BANDS RESERVED FOR THEM, now that the limits are final.
#
# The scored-horizon note goes in the lower band, under every series. It was tried twice
# inside the data first: pointing at the pooled curve from below, where its text came to
# rest along the Bitcoin line, and then at the foot of the panel before the band existed,
# where it landed on the per-fill line. Four rising series leave no hole big enough, and
# the cheapest of them still runs across the bottom of the panel, so the room has to be
# made. It carries no arrow because the thing it names is a solid rule already drawn.
ax.text(0.52, 0.025, f"scored at {secs(H_CHOSEN)}", transform=ax.transAxes,
        fontsize=PT_NOTE, ha="left", va="bottom")
# The plateau note sits against the rule it names, and on the LEFT. On the right the
# pooled curve rises above the plateau at the thirty-second rung and the note would cross
# it; on the left the gap between the plateau and the dearer coin is about 0.6 basis
# points and nothing else is in it. Its distance above the rule is a fraction of the axis
# rather than a quantity of basis points, so it survives a rescaling of the panel.
_y0, _y1 = ax.get_ylim()
ax.text(0.13, (PLATEAU - _y0) / (_y1 - _y0) + 0.02,
        f"plateau, {PLATEAU:.2f} basis points",
        transform=ax.transAxes, fontsize=PT_NOTE, color="grey", va="bottom")

fig.tight_layout()

# THE FIT IS MEASURED, NOT EYEBALLED, because what goes wrong here goes wrong silently. A
# y label longer than its own panel is not clipped and raises nothing: it is drawn past
# the top of the panel, over the title, and the file on disk looks like a figure until
# somebody reads it. Every number this file draws comes out of the results file, so any
# label can grow the day a coin is added or a horizon renamed, and a guard that runs at
# drawing time is the only one that sees it. Failing prints the expectation, the fact and
# the place, and it does not shrink the type to make itself pass: the point sizes are what
# the report asked for, and a label that cannot fit at eight points is one to rewrite.
fig.canvas.draw()
rend = fig.canvas.get_renderer()
label = ax.yaxis.label.get_window_extent(renderer=rend)
frame = ax.get_window_extent(renderer=rend)
if label.y1 > frame.y1 or label.y0 < frame.y0:
    raise SystemExit(
        f"the y axis label is taller than the panel it names. expected the label "
        f"inside {frame.y0:.0f} to {frame.y1:.0f} pixels, found {label.y0:.0f} to "
        f"{label.y1:.0f}. Break the label onto one more line: "
        f"ws1_markout_curve_figure.py, set_ylabel")
# The height ceiling the report sets is a property of the saved file and not of the
# figure object, so it is asserted against the canvas that will be written.
if fig.get_size_inches()[1] > 3.5 + 1e-9:
    raise SystemExit(
        f"the figure is {fig.get_size_inches()[1]:.2f} inches tall against a ceiling of "
        f"3.50 in the report's single-column layout: ws1_markout_curve_figure.py, "
        f"HEIGHT_IN")

out_png = os.path.join(HERE, OUT_PNG)
fig.savefig(out_png, dpi=DPI_OUT)

# WHAT WAS DRAWN, WRITTEN DOWN, so the figure can be checked without opening the image
# and so the three ratios printed on it have an address of their own. The series are
# recorded as they were plotted rather than re-read, which is what makes this file a
# record of the picture instead of a second copy of its source.
payload = {
    "figure_file": OUT_PNG,
    "figure_size_in": {"width": WIDTH_IN, "height": HEIGHT_IN, "dpi": DPI_OUT},
    "grid_s": GRID,
    "quantity": {
        "name": "markout of a taker fill against the book mid, in basis points",
        "reference_price": "the top-of-book mid of the last snapshot STRICTLY EARLIER "
                           "than the fill; not the trade print, which on the same fills "
                           "reads about a quarter of this, the difference being the "
                           "spread the maker earned",
        "sign": "signed in the taker's favour, so a positive value is the price moving "
                "the way the aggressor pointed and therefore the MAKER's "
                "adverse-selection cost",
        "unit": "basis points of the entry mid",
        "weighting": {"vw": "weighted by the notional of each fill, so it is the cost "
                            "per dollar traded",
                      "ew": "unweighted mean over fills, so it is the cost of the "
                            "average fill"},
    },
    "series_drawn": {
        "pooled_vw_bps": dict(zip(map(str, GRID), pooled_vw)),
        "pooled_ew_bps": dict(zip(map(str, GRID), pooled_ew)),
        "per_coin_vw_bps": {c: dict(zip(map(str, GRID), per_coin_vw[c]))
                            for c in COINS},
    },
    "marked": {
        "scored_horizon_s": H_CHOSEN,
        "scored_horizon_source": R["final_decision"]["recommended_source"],
        "plateau_vw_bps": PLATEAU,
    },
    "summaries": {
        "vw_over_ew_at_scored_horizon": vw_over_ew,
        "vw_over_ew_meaning": f"a dollar of notional loses {vw_over_ew:.4f} times what "
                              f"the average fill loses at {secs(H_CHOSEN)}, so the "
                              f"adverse selection is carried by the large fills",
        "dearer_coin": coin_hi,
        "cheaper_coin": coin_lo,
        "coin_ratio_at_scored_horizon": coin_ratio,
        "fill_counts_by_horizon": dict(zip(map(str, GRID), counts)),
        "fill_count_spread": count_spread,
        "fill_count_spread_fraction": count_spread_frac,
        "fill_count_meaning": f"the population moves by {count_spread} fills across the "
                              f"whole grid, {count_spread_frac * 100:.4f} per cent of "
                              f"the largest rung, so the curve rises because the price "
                              f"moves after the fill and not because the sample changes",
    },
    "blend_check": {
        "rule": "the pooled value-weighted mean is a notional-weighted average of the "
                "per-coin ones and must lie between them at every rung",
        "rungs_tested": len(GRID),
        "rungs_passed": len(GRID),
        "pooled_nearer": [min(COINS, key=lambda c: abs(per_coin_vw[c][i]
                                                       - pooled_vw[i]))
                          for i in range(len(GRID))],
    },
    "relation_to_ws1_horizon_choice_png": (
        "ws1_plot.py draws the same artifact's pooled value-weighted level as the lower "
        "panel of the horizon-choice figure. Nothing here redraws it to settle that "
        "question again: the equal-weighted line, the two per-coin lines and the fill "
        "counts appear in no figure of the report, and they are what describes the cost "
        "rather than the choice of horizon."),
}

path = artifact.write(
    OUT_NAME, payload,
    script=__file__,
    inputs=[IN_NAME],
    scope={
        "population": f"every taker fill of the window with a finite book-mid markout at "
                      f"the rung, {min(counts):,} to {max(counts):,} fills depending on "
                      f"the horizon; NOT the {R['pooled'][str(H_CHOSEN)]['n_units']:,} "
                      f"wallet-coin units the persistence half of "
                      f"{IN_NAME} stands on",
        "window": R["_meta"]["scope"]["window"],
        "coins": COINS,
    },
    settings={"h": H_CHOSEN, "lens": "mid",
              "grid_s": GRID,
              "overrides_note": "this file draws a GRID and selects no window; "
                                "horizon_s is the rung the study scores at, marked on "
                                "the figure and read out of the artifact rather than "
                                "declared here"},
    started=t0)

print(f"[curve] pooled per dollar, basis points by horizon: "
      + ", ".join(f"{h}:{v:.3f}" for h, v in zip(GRID, pooled_vw)))
print(f"[curve] at {secs(H_CHOSEN)}: per dollar {pooled_vw[i_chosen]:.4f}, "
      f"per fill {pooled_ew[i_chosen]:.4f}, ratio {vw_over_ew:.4f}; "
      f"{coin_hi} {per_coin_vw[coin_hi][i_chosen]:.4f} against "
      f"{coin_lo} {per_coin_vw[coin_lo][i_chosen]:.4f}, ratio {coin_ratio:.4f}")
print(f"[curve] population moves by {count_spread} fills across the grid "
      f"({count_spread_frac * 100:.4f}% of the largest rung)")
# Printed relative to this file. An absolute path here would put a local home directory
# into any log that captures the run, and a log that lands in the tree is a tracked text
# file the absolute-path guard then has to catch.
print(f"wrote {os.path.relpath(out_png, HERE)} and {os.path.relpath(path, HERE)}")
