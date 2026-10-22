#!/usr/bin/env python3
"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-08-07
References: Hyperliquid Level-4 order-book data, Zenodo 18184441 (Albers et al. 2026).

WS3 figure: how a counterparty's markout toxicity ranks against that same counterparty's
OWN realised profit, pooled and then coin by coin. Reads ws3_taker_pnl_results.json and
computes nothing.

One panel, three rows. Each row is one rank correlation drawn as a dot with the
bootstrap interval the producer stored for it, against a rule at zero: the pooled
population, then each coin on its own.

WHY THIS IS A DIFFERENT FIGURE AND NOT THE OLD ONE MADE SMALLER. The sentence the figure
carries changed. It used to say that a pooled rank correlation of -0.0001 puts the
relation "in the tail and nowhere else". The results file says otherwise in its own
interpretation field, and has since it was written: the pooled zero is two relations of
OPPOSITE SIGN cancelling, one coin above zero and the other below, with neither
bootstrap interval covering zero. A figure that cannot show that is a figure arguing
against the text beside it.

Neither old panel could show it. The left panel drew one pooled line through ten
equal-count bins, and eight of those ten points sat within two basis points of each
other while the two end bins stretched the scale across twenty, so the middle was
unreadable; being pooled, it could not have shown a per-coin split under any scale. The
right panel joined TWO category medians with a dashed line, which draws a trend where
there are two groups and no line between them, and both of those medians are already
written out as numbers in the report prose.

THE WHISKERS ARE THE PRODUCER'S OWN BOOTSTRAP INTERVALS. The caption of the figure this
replaces promised error bars and the figure drew none anywhere. Every number here
resolves to a key of the results file and none is computed at drawing time:

  dot            rank_agreement.<arm>.rho
  whisker ends   rank_agreement.<arm>.boot_lo, rank_agreement.<arm>.boot_hi
  row count      rank_agreement.<arm>.n
  permutation p  rank_agreement.<arm>.placebo_p, floored per placebo_p_is_floor
  draws behind p rank_agreement.<arm>.placebo_procedure.n_draws_usable
  horizon in the label   score_horizon_s
  arm names      coin_map

DRAWN HERE AND NOT IN THE NODE THAT COMPUTES, which is the older reason this file exists
and still holds. Both panels used to be drawn inside ws3_taker_pnl.py, which cost the
figure two ways. Redrawing meant recomputing, at a recorded 37.9 seconds. And the
drawing sat behind a catch that printed one line and returned zero, so when the launch
form resolved no matplotlib the node wrote a fresh results file, said "plot skipped",
exited clean and left a two-day-old figure standing beside numbers that had moved. On
this figure that cost a SIGN. A figure that fails to be drawn must not be able to hide
inside the exit code of a computation that succeeded. Drawn here it has an exit code of
its own, it costs under a second, and it says what the file it reads says.

DRAWN AT THE SIZE IT IS PRINTED. The canvas is 5.5 inches wide because that is the width
the report gives a figure, and the type sizes below are the sizes a reader sees. The old
canvas was twelve inches wide and was scaled down to just over four on the page, which
took its 10-point labels to about three and a half against 11-point body text.

This file takes no command line at all, deliberately: build.py refuses a bare run to any
producer that reads one, and a figure has nothing to choose.

Input:  ws3_taker_pnl_results.json
Output: ws3_taker_pnl.png
"""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
IN_JSON = os.path.join(HERE, "ws3_taker_pnl_results.json")
OUT_PNG = os.path.join(HERE, "ws3_taker_pnl.png")

R = json.load(open(IN_JSON))

# The rows are named by the artifact rather than typed here. coin_map is what the
# producer used to turn its integer coin codes back into tickers, so a run over a
# different pair draws that pair instead of putting the wrong two labels on real values.
COINS = [R["coin_map"][k] for k in sorted(R["coin_map"], key=int)]
ARMS = ["pooled"] + COINS
RA = R.get("rank_agreement", {})

# A worded refusal and a non-zero code, never a picture drawn from whatever happens to be
# present. The failure this guards against is the one that reads as success: an older
# results file carries the pooled arm alone, and three rows drawn from it would be one
# row repeated three times, which is the very claim the panel exists to deny.
NEEDED = ("rho", "boot_lo", "boot_hi", "n", "placebo_p")
missing = [f"rank_agreement.{arm}.{field}"
           for arm in ARMS
           for field in NEEDED
           if field not in RA.get(arm, {})]
if missing:
    raise SystemExit(
        "[ws3] REFUSED: ws3_taker_pnl_results.json is missing "
        f"{len(missing)} key(s) this figure reads: {', '.join(missing)}. "
        "The panel draws one rank correlation and its bootstrap interval per arm, and "
        "the arms are the pooled population plus every coin named in coin_map. Run "
        "ws3_taker_pnl.py once; its recorded runtime is 37.9 seconds.")

# Print sizes, set once so every text element obeys them: what is written here is what
# the reader measures on the page, because the canvas is already the printed width.
plt.rcParams.update({
    "font.size": 8,
    "axes.titlesize": 9,
    "axes.labelsize": 8,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "legend.fontsize": 7.5,
})

H = R["score_horizon_s"]
# Grey for the pooled row and one colour per coin, so the eye separates the row that is
# an average of the other two from the two it averages.
COLOURS = {"pooled": "0.30"}
CYCLE = ["C0", "C3", "C2", "C4"]
for i, c in enumerate(COINS):
    COLOURS[c] = CYCLE[i % len(CYCLE)]
ROW_TITLE = {"pooled": "Pooled"}


def p_sentence(arm):
    """Say the permutation p without letting a floored p read as a measured one.

    Both coin arms come back with zero permutation draws at least as extreme as the
    observed one, so their p is not 0.0005 but the smallest number this many draws can
    return. Printing the floor bare invites a reader to compare it with a p that was
    actually attained, and the two are not the same statement.
    """
    a = RA[arm]
    if a.get("placebo_p_is_floor"):
        draws = a.get("placebo_procedure", {}).get("n_draws_usable")
        tail = f" (the floor of {draws:,} draws)" if draws else " (its floor)"
        return f"permutation p = {a['placebo_p']:.4f}{tail}"
    return f"permutation p = {a['placebo_p']:.3f}"


fig, ax = plt.subplots(figsize=(5.5, 3.4))

# Rows top to bottom in the order the sentence reads them: the pooled figure first, then
# the two coins it hides.
ys = list(range(len(ARMS) - 1, -1, -1))
for y, arm in zip(ys, ARMS):
    a = RA[arm]
    rho, lo, hi = a["rho"], a["boot_lo"], a["boot_hi"]
    ax.errorbar([rho], [y], xerr=[[rho - lo], [hi - rho]], fmt="o", ms=4.5,
                color=COLOURS[arm], ecolor=COLOURS[arm], elinewidth=1.4, capsize=3.5)
    # The two numbers that carry the argument sit on the first line; the test that
    # supports them sits under it in grey, so a reader takes the interval first.
    ax.text(0, y + 0.36, f"{rho:+.4f} on [{lo:+.4f}, {hi:+.4f}]",
            ha="center", va="bottom", fontsize=8, color=COLOURS[arm],
            bbox=dict(facecolor="white", edgecolor="none", pad=0.8))
    ax.text(0, y + 0.16, p_sentence(arm), ha="center", va="bottom",
            fontsize=8, color="0.35",
            bbox=dict(facecolor="white", edgecolor="none", pad=0.8))

ax.axvline(0, color="0.45", ls=":", lw=1.0, zorder=0)
ax.set_yticks(ys)
ax.set_yticklabels([f"{ROW_TITLE.get(a, a)}\n{RA[a]['n']:,} units" for a in ARMS])
ax.set_ylim(-0.55, len(ARMS) - 0.28)

# Symmetric about zero, so the rule sits in the middle of the panel and the two coins are
# read against each other by eye rather than by their numbers.
span = max(max(abs(RA[a]["boot_lo"]), abs(RA[a]["boot_hi"])) for a in ARMS)
ax.set_xlim(-1.45 * span, 1.45 * span)

# THE AXIS NAMES ITS QUANTITY AND ITS UNIT, AND STOPS THERE. A correlation has no
# physical unit, and a reader who is not told so reads +0.1013 as a tenth of something;
# the range it lives on is the unit here. What the axis does NOT carry is the fill floor
# behind the population and the level behind the whiskers, because neither is the name of
# the axis: both are properties of the method and both belong in the note under the
# figure, where the report can spell them out at the width of a paragraph. Four lines of
# label under a panel three inches tall took room from the thing being labelled.
ax.set_xlabel(f"Spearman rank correlation: per-wallet {H}-second markout toxicity\n"
              "against realised profit per dollar (dimensionless, -1 to +1)")
ax.set_title("Toxicity against the counterparty's own realised profit:\n"
             "the pooled near-zero is two opposite relations cancelling")
ax.grid(axis="x", alpha=0.3)
ax.set_axisbelow(True)

fig.tight_layout()
fig.savefig(OUT_PNG, dpi=200)
# Printed relative to this file, so the line names the target without putting a local
# home directory into the console output or into any log that captures it.
print(f"[ws3] wrote {os.path.relpath(OUT_PNG, HERE)}")
