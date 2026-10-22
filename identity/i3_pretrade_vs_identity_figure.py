#!/usr/bin/env python3
"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-08-25
References: Hyperliquid Level-4 order-book data, Zenodo 18184441 (Albers et al. 2026);
Easley, Lopez de Prado and O'Hara (2012) on flow toxicity and VPIN; Glosten and Milgrom
(1985) on adverse selection against an uninformed quoter; Cont, Kukanov and Stoikov (2014)
on order-flow imbalance, which is one of the ten book features the right panel controls
for.

WHAT AN OBSERVER CAN SEE WHILE THE QUOTE IS STILL STANDING, AND HOW FAR IT CARRIES.

This is the pre-trade half of the appendix pair; money/m9_decile_economics_figure.py is
the post-trade half. Everything on both panels here is knowable at the instant the maker
is deciding whether to quote and at what width. Nothing on either panel is an outcome of
the fill being decided about.

The report rests on one claim and this figure is the direct test of it: THE VISIBLE STATE
OF THE ORDER BOOK BARELY DISTINGUISHES THE COUNTERPARTIES WHO WILL COST THE MAKER MONEY,
AND THE COUNTERPARTY'S OWN IDENTITY DOES. If that were false the project would have no
subject, because a maker who can read the book already has everything identity could give
and has no reason to resolve wallets at all. The two panels attack the claim from the two
opposite directions, and they are drawn side by side because either one alone is open to
an obvious objection that the other closes.

THE LEFT PANEL ASKS WHETHER IDENTITY IS THE BOOK IN DISGUISE. Markouts scatter, and some
of that scatter sits BETWEEN counterparties: wallets differ from each other, not merely
within themselves. The bar called `raw` is that between-counterparty share of the total
scatter. The objection to it is immediate and fair. Wallets trade at different moments; if
one habitually arrives when the spread is wide and another when the book is lopsided, then
what looks like a difference between counterparties is really a difference between market
states, and identity is a proxy carrying no information of its own. The test is to subtract
the book state from every fill and recompute the same share on the residual. Had identity
been the book in disguise, the wallet averages would have collapsed together and the share
would have fallen to its noise floor. IT DOES NOT COLLAPSE, and that non-collapse is what
the panel is for. The fall it does show is the honest measure of how much of the difference
between counterparties the visible book can take credit for.

WHY TWO RESIDUAL BARS AND NOT ONE, which is a caveat the source artifact raises against
itself and which this file refuses to lose. The LINEAR book fit explains under one per cent
of markout variance, so subtracting it can barely move anything, and a high retain on the
linear residual is close to a tautology of that near-zero fit rather than evidence. The
artifact says exactly this in `caveats.linear_retain_is_tautological` and retracts an
earlier, stronger framing of its own. The NON-LINEAR control -- deciles of each control
plus their pairwise products, thirty design columns, a fit one and a half to three and a
half times the linear one -- is a real control, and the retain on THAT residual is the
non-tautological statement. Both are drawn, and the non-linear bar is given the accent
colour because it is the one that carries weight.

THE NOISE FLOOR IS DRAWN AND NOT FOOTNOTED, for the same reason. The between-share is
computed IN SAMPLE: the same rows form the per-wallet averages and the total they are
divided by. With K fills per wallet, sampling noise alone inflates the share by roughly
1/K even when every wallet is identical, which is two per cent at the fifty-fill floor and
one per cent at the hundred-fill floor. On the pooled fifty-fill cell the raw share is
2.98 per cent against a 2.0 per cent floor, so most of that particular bar could be floor.
A reader who cannot see that line would read the pooled cell as evidence of the same
strength as the BTC hundred-fill cell, which stands at 11.9 per cent against a 1.0 per cent
floor. The line is therefore part of the picture.

THE RIGHT PANEL ASKS THE COMPLEMENTARY QUESTION AND ASKS IT OUT OF SAMPLE. Give a
predictor the whole public information set -- four summaries of the trade tape and ten
features of the full level-2 book, fourteen in all -- and let it predict how toxic each
counterparty will be in the FUTURE half of the window. Then add one single column: what
that counterparty's markouts looked like in the PAST half. The bar is what that one column
adds to the out-of-sample fit. One column against fourteen, one declared axis, and the
public arm is not handicapped: it holds every book feature the venue publishes.

WHAT THE RIGHT PANEL IS NOT, and this is the qualification the caption carries because the
value registry demands it at entries M50 and M51. The anonymous arm is NOT blind to
identity. All fourteen of its features are per-wallet averages, so the flow has already
been partitioned by counterparty before that arm ever sees it. The only thing withheld is
the wallet's own past markout. So the number measures the worth of KNOWING HOW THIS
COUNTERPARTY HAS BEHAVED, and not the worth of being able to tell counterparties apart at
all. The second is worth more and is not what is drawn.

NOTHING ON THE RIGHT PANEL SEES THE FUTURE, and the file refuses to draw rather than
assert it. The label is built from the early days of the window and the target is measured
on the late days, and `_require` below reads both lists out of the artifact and stops if
they intersect. The fit is scored five-fold across WALLETS, so the coefficient the label
gets is estimated on other counterparties and applied to held-out ones. A wallet's past is
what makes it a pre-trade signal for its own future; that is the mechanism under test, not
a leak of it.

WHY THE BAR IS A MEDIAN AND THE WHISKER IS NOT A CONFIDENCE INTERVAL. Every incremental
figure in the source artifact comes from ONE five-fold split of the wallets, and that
single draw moves with the split: on the ETH fifty-fill cell the stored draw sits at the
95th percentile of its own distribution over forty splits. The artifact's own
`seed_robustness.reporting_rule` says to quote the median with its range and not the
stored draw, so the bar is the median over forty fold seeds, the whisker is the smallest
and largest of the forty, and the hollow marker is the stored draw so a reader holding the
paper against the file can find it. THE WHISKER IS SENSITIVITY TO THE SPLIT AND NOTHING
ELSE: the wallets, the features and the targets are identical in all forty draws, so it is
not sampling uncertainty, it is not a confidence interval, and a count like forty out of
forty is not a p-value. Significance on these cells comes from the label-permutation
placebo, which is a separate procedure, and its p sits on the resolution floor of two
thousand draws rather than being a measured smallness.

WHY THE TWO PANELS DO NOT SHARE AN AXIS, and why they must not. Three differences, any one
of which is sufficient. The unit differs: a row of the left panel is one FILL, a row of the
right panel is one WALLET. The holdout differs: the left share is in sample by
construction, the right one holds out whole wallets and measures them on days its
predictors never saw. And the quantity differs: the left is a share of variance
attributable to a grouping, the right is a difference between two out-of-sample fits. Two
axes, two labels, and the caption says so.

WHAT IS RECORDED BESIDE THE DRAWING AND NOT DRAWN. The sixty-second companion horizon and
the pooled population both live in the results file this writes. The pooled cells of the
right-hand source are excluded from the picture on the source's own instruction: it marks
them `pooled_is_diagnostic_only` because the two coins have OPPOSITE book-recoverability --
the public book leaves ETH toxicity almost unrecovered and largely recovers BTC toxicity --
so an average of the two describes neither. Drawing it would put on the page the one
reading the artifact forbids.

BOTH PANELS SHOW PERCENTAGES AND THE SOURCES HOLD FRACTIONS. Every number is multiplied by
one hundred exactly once, at PCT below, and the axis labels and the caption both say per
cent. Confusing a fraction with a percentage has happened in this project before, so the
conversion has one home in this file and the results file records both forms.

DRAWN AT THE SIZE IT IS PRINTED. The canvas is 5.53 inches wide because that is the width
of the single text column of the report, and no taller than 3.5 inches so that an appendix
figure does not push what it supports onto the next page. Every point size below is the
size a reader of the page sees.

THIS FILE COMPUTES NO NEW QUANTITY. It reads two committed artifacts, costs under a
second, and redrawing it never means recomputing the two nodes that produced the numbers.
It takes no command line: a figure has nothing to choose.

Run command (bare python3 is BLOCKED on this machine):
  uv run --no-project --with-requirements requirements.txt python3 -u \
      identity/i3_pretrade_vs_identity_figure.py
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

import artifact
import settings as H

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DEPTH = os.path.join(HERE, "i3_depth_control_results.json")
SRC_BOOK = os.path.join(HERE, "i3_book_nonrecoverability_results.json")
OUT_PNG = os.path.join(HERE, "i3_pretrade_vs_identity.png")
OUT_JSON = os.path.join(HERE, "i3_pretrade_vs_identity_figure_results.json")

T0 = artifact.start_clock()

# The printed geometry, in one place, because a size named twice is a size that drifts.
WIDTH_IN, HEIGHT_IN, DPI_OUT = 5.53, 3.45, 200
PT_LABEL, PT_TITLE, PT_LEGEND, PT_NOTE = 7.5, 8, 6.8, 6.5
plt.rcParams.update({"font.size": PT_LABEL,
                     "axes.labelsize": PT_LABEL,
                     "axes.titlesize": PT_TITLE,
                     "xtick.labelsize": PT_LABEL,
                     "ytick.labelsize": PT_LABEL,
                     "legend.fontsize": PT_LEGEND})

# The one place a fraction becomes a percentage. Both forms reach the results file.
PCT = 100.0

# Which slice is drawn. Read from settings.py, never typed here.
H_HEADLINE = H.HEADLINE_HORIZON_S
H_COMPANION = H.COMPANION_HORIZON_S
LENS = H.HEADLINE_LENS

DEPTH = json.load(open(SRC_DEPTH, encoding="utf-8"))
BOOK = json.load(open(SRC_BOOK, encoding="utf-8"))


def _require(condition, what):
    """Refuse to draw rather than draw a picture whose premise is false.

    A figure that quietly draws a broken premise is worse than one that does not draw:
    the picture reaches the report and the premise never does. Each condition below is a
    thing the caption asserts, so each is read out of the artifact instead of believed.
    """
    if not condition:
        raise SystemExit(f"[i3-fig] refusing to draw: {what}")


# ---------------------------------------------------------------------------
# LEFT PANEL: the between-counterparty share of markout scatter, before and after
# the visible book is subtracted.
# ---------------------------------------------------------------------------
D_SCOPE = DEPTH["scope"]
D_CAVEATS = DEPTH["caveats"]

_require(int(D_SCOPE["horizon_s"]) == int(H_HEADLINE),
         f"the depth artifact reports horizon {D_SCOPE['horizon_s']} s while settings.py "
         f"declares the headline horizon {H_HEADLINE} s")
_require(D_SCOPE["markout_source"] == LENS,
         f"the depth artifact was measured against {D_SCOPE['markout_source']} while "
         f"settings.py declares the headline lens {LENS}")
# The three caveats the caption carries. A caveat that leaves the artifact must not go on
# leaving the caption silently, so its absence stops the drawing.
for key in ("between_share_is_in_sample", "linear_retain_is_tautological",
            "nonlinear_control_added"):
    _require(key in D_CAVEATS,
             f"the depth artifact no longer carries caveats.{key}, which the caption "
             "states; the caption would outlive the fact")

CONTROL_COLS = list(D_SCOPE["control_cols"])
_require(len(CONTROL_COLS) == 3,
         f"the panel names three visible quantities and the artifact controls for "
         f"{len(CONTROL_COLS)}: {CONTROL_COLS}")

# Plain-language names for the three controls, so the caption does not have to send a
# reader to the code to learn what was held constant.
CONTROL_WORDS = {
    "imb_entry": "queue imbalance at the best prices",
    "spread_entry_bps": "quoted spread in basis points",
    "micro_dev_bps": "deviation of the size-weighted price from the mid",
}
_require(all(c in CONTROL_WORDS for c in CONTROL_COLS),
         f"a control has no plain-language name here: {CONTROL_COLS}")


def depth_groups():
    """The three populations of the depth artifact, in drawing order.

    POOLED is legitimate here and is drawn. That is not a contradiction of the right
    panel dropping its own pooled cells: the two artifacts answer different questions,
    and only the second one records a prohibition against pooling, for a reason that
    belongs to it -- the coins differ in how far the public book recovers toxicity, which
    is a statement about the RIGHT panel's quantity and not about this one.
    """
    groups = list(DEPTH["by_coin"]) + [DEPTH["pooled"]]
    return groups


LEFT = []
for g in depth_groups():
    r2_lin = float(g["ols_book_state"]["r2_book_state"])
    r2_nl = float(g["ols_book_state_nonlinear"]["r2_book_state_nonlinear"])
    # The non-linear design contains the linear one, so its fit cannot be the smaller of
    # the two. If it ever were, the accent bar would be the weaker control and the
    # caption's reason for giving it weight would be gone.
    _require(r2_nl >= r2_lin,
             f"{g['coin']}: the non-linear book fit {r2_nl:.6f} is below the linear "
             f"{r2_lin:.6f}, so the richer control is not the stronger one")
    for cell in g["cells"]:
        LEFT.append({
            "coin": g["coin"],
            "K": int(cell["K"]),
            "n_wallets": int(cell["n_wallets"]),
            "n_obs_eligible": int(cell["n_obs_eligible"]),
            "raw": float(cell["between_share_raw"]),
            "after_linear": float(cell["between_share_residual"]),
            "after_nonlinear": float(cell["between_share_nonlinear_residual"]),
            "noise_floor": float(cell["between_share_in_sample_noise_floor"]),
            "retained_linear": float(cell["share_retained_fraction"]),
            "retained_nonlinear": float(cell["share_retained_nonlinear"]),
            "loo_taker_r2_raw": float(cell["loo_taker_r2_raw"]),
            "loo_taker_r2_residual": float(cell["loo_taker_r2_residual"]),
            "placebo_p": float(cell["placebo_residual_p"]),
            "placebo_p_is_floor": bool(cell["placebo_residual_p_is_floor"]),
            "r2_book_linear": r2_lin,
            "r2_book_nonlinear": r2_nl,
        })

_require(len(LEFT) == 6,
         f"the left panel's source holds three populations at two fill floors and offered "
         f"{len(LEFT)} cells")
# The floor is 1/K by construction. Checked rather than trusted, because the caption
# explains the line by that formula and a line drawn from a different rule would make the
# explanation false.
for c in LEFT:
    _require(abs(c["noise_floor"] - 1.0 / c["K"]) < 1e-12,
             f"{c['coin']} K={c['K']}: the recorded noise floor {c['noise_floor']} is not "
             f"1/K, which is what the caption says it is")

# THE COINS ARE DRAWN APART AND THE POOLED CELL IS NOT DRAWN, and the reason is measured
# here rather than carried over by analogy from the other artifact.
#
# The right-hand source forbids pooling in so many words, because its two coins answer
# oppositely. This source says nothing of the kind, so the question had to be put to its
# own numbers, and they answer it: the pooled between-counterparty share is SMALLER THAN
# EITHER COIN'S, 2.98 per cent against 6.98 for BTC and 3.87 for ETH at the fifty-fill
# floor. A number below both of the things it supposedly averages is not a summary of
# them.
#
# The mechanism, measured on the panel rather than guessed at: pooling changes both parts
# of the ratio and in opposite directions. Total markout variance blends to 43.11 from
# 19.02 on BTC and 62.86 on ETH, and the variance between wallet means FALLS to 1.283 from
# 1.328 and 2.434, because a wallet trading both coins contributes one mean averaged
# across two instruments of quite different scale instead of two separate ones. So the
# pooled cell understates identity on both coins at once. It is kept in the results file
# with this note beside it and kept off the page.
LEFT_ALL = LEFT
LEFT = [c for c in LEFT_ALL if c["coin"] != "POOLED"]
LEFT_POOLED = [c for c in LEFT_ALL if c["coin"] == "POOLED"]
_require(len(LEFT) == 4 and len(LEFT_POOLED) == 2,
         f"the left panel expects two coins at two floors and a pooled pair set aside, "
         f"and got {len(LEFT)} drawn against {len(LEFT_POOLED)} set aside")
for p in LEFT_POOLED:
    per_coin = [c["raw"] for c in LEFT if c["K"] == p["K"]]
    _require(p["raw"] < min(per_coin),
             f"the pooled cell at K={p['K']} no longer sits below both coins "
             f"({p['raw']:.4f} against {min(per_coin):.4f}), so the measured reason this "
             "file gives for leaving it off the page no longer holds and must be re-read")

# ---------------------------------------------------------------------------
# RIGHT PANEL: what one column of counterparty history adds out of sample over the
# whole public information set.
# ---------------------------------------------------------------------------
B_DESIGN = BOOK["test_design"]
EARLY_DAYS = [int(d) for d in B_DESIGN["early_days"]]
LATE_DAYS = [int(d) for d in B_DESIGN["late_days"]]
_require(not (set(EARLY_DAYS) & set(LATE_DAYS)),
         f"the labelling days {EARLY_DAYS} and the measured days {LATE_DAYS} intersect, "
         "so the counterparty label would carry information from the half it predicts")
_require(int(B_DESIGN["primary_horizon_s"]) == int(H_HEADLINE),
         f"the book artifact calls {B_DESIGN['primary_horizon_s']} s primary while "
         f"settings.py declares {H_HEADLINE} s")
# The prohibition on pooling is read out of the artifact and obeyed, not remembered.
_require(BOOK["headline"].get("pooled_is_diagnostic_only") is True,
         "the book artifact no longer marks its pooled cells diagnostic-only, so the "
         "reason this panel drops them may no longer hold and should be re-read")

B_FAMILY = BOOK["family"]
# HOW MANY CELLS HAVE A p SITTING ON THE RESOLUTION FLOOR, recounted here from the cells
# themselves rather than reprinted from the summary that sits beside them. The caption
# says this number out loud, and a summary and its own detail have disagreed elsewhere in
# this work; a recount costs one pass over twelve records.
N_AT_FLOOR_RECOUNT = sum(1 for c in list(BOOK["by_coin"]) + list(BOOK["pooled"])
                         if c["placebo_p_is_floor"])
_require(N_AT_FLOOR_RECOUNT == int(B_FAMILY["n_cells_with_p_at_floor"]),
         f"the family summary says {B_FAMILY['n_cells_with_p_at_floor']} cells carry a p "
         f"on the floor and counting the cells gives {N_AT_FLOOR_RECOUNT}")
_require(len(list(BOOK["by_coin"]) + list(BOOK["pooled"]))
         == int(B_FAMILY["n_cells_tested"]),
         "the family size and the number of cells present disagree")

SWEEP = BOOK["seed_robustness"]
_require("scope_of_variation" in SWEEP,
         "the fold-seed sweep no longer states what it varies, and the caption's "
         "statement that the whisker is not a confidence interval rests on it")
N_SEEDS = int(SWEEP["n_seeds"])

BOOK_FEATURES = list(B_DESIGN["book_feature_names"])


def sweep_cell(coin, h, k):
    """The fold-seed summary of one cell, found by its three coordinates."""
    for c in SWEEP["cells"]:
        if c["coin"] == coin and int(c["horizon_s"]) == int(h) and int(c["K"]) == int(k):
            return c
    return None


RIGHT = []
for row in BOOK["by_coin"]:
    if int(row["horizon_s"]) != int(H_HEADLINE):
        continue
    s = sweep_cell(row["coin"], row["horizon_s"], row["K"])
    _require(s is not None,
             f"{row['coin']} h={row['horizon_s']} K={row['K']} has no fold-seed sweep, "
             "so the bar would have to be the single stored draw the artifact says not "
             "to quote")
    stored = float(row["incremental_oos_r2"])
    lo, hi = float(row["oos_r2_public"]), float(row["oos_r2_public_plus_fe"])
    # The two fits and their difference come from ONE split, so they are consistent with
    # each other and the difference is theirs. Checked, because the caption reads the
    # increment as the gap between exactly these two fits.
    _require(abs((hi - lo) - stored) < 1e-9,
             f"{row['coin']} K={row['K']}: the stored increment {stored} is not the gap "
             f"between the two stored fits {lo} and {hi}")
    _require(abs(float(s["stored_single_seed"]) - stored) < 1e-12,
             f"{row['coin']} K={row['K']}: the sweep and the cell disagree about the "
             "stored draw, so one of them is describing another cell")
    RIGHT.append({
        "coin": row["coin"],
        "K": int(row["K"]),
        "horizon_s": int(row["horizon_s"]),
        "n_wallets": int(row["n_wallets"]),
        "n_public_features": int(row["n_public_features"]),
        "oos_r2_public": lo,
        "oos_r2_public_plus_fe": hi,
        "incremental_stored_single_split": stored,
        "stored_percentile_of_own_sweep": float(s["stored_percentile"]),
        "incremental_median_over_seeds": float(s["median"]),
        "incremental_min_over_seeds": float(s["min"]),
        "incremental_max_over_seeds": float(s["max"]),
        "n_seeds_positive": int(s["n_seeds_positive"]),
        "placebo_p": float(row["placebo_p"]),
        "placebo_p_is_floor": bool(row["placebo_p_is_floor"]),
        "bh_qvalue": float(row["bh_qvalue"]),
        "survives_fdr": bool(row["survives_fdr"]),
    })

RIGHT.sort(key=lambda c: (c["coin"], c["K"]))
_require(len(RIGHT) == 4,
         f"the right panel expects two coins at two fill floors on the headline horizon "
         f"and found {len(RIGHT)} cells")

# ---------------------------------------------------------------------------
# The drawing.
# ---------------------------------------------------------------------------
fig, (axL, axR) = plt.subplots(
    1, 2, figsize=(WIDTH_IN, HEIGHT_IN), layout="constrained",
    gridspec_kw={"width_ratios": [1.30, 1.0]})
fig.get_layout_engine().set(h_pad=0.02, w_pad=0.04, hspace=0.0, wspace=0.02)

C_RAW, C_LIN, C_NL = "0.78", "0.55", "C0"
C_BAR, C_MARK = "0.62", "C3"

# --- left ---
x = np.arange(len(LEFT), dtype=float)
w = 0.26
raw = np.array([c["raw"] for c in LEFT]) * PCT
lin = np.array([c["after_linear"] for c in LEFT]) * PCT
nl = np.array([c["after_nonlinear"] for c in LEFT]) * PCT
floor = np.array([c["noise_floor"] for c in LEFT]) * PCT
loo = np.array([c["loo_taker_r2_residual"] for c in LEFT]) * PCT

b_raw = axL.bar(x - w, raw, width=w, color=C_RAW, edgecolor="0.30", linewidth=0.5,
                zorder=2)
b_lin = axL.bar(x, lin, width=w, color=C_LIN, edgecolor="0.30", linewidth=0.5,
                zorder=2)
b_nl = axL.bar(x + w, nl, width=w, color=C_NL, edgecolor="0.20", linewidth=0.5,
               zorder=2)
# The in-sample noise floor of each cell, as a segment spanning its group. Drawn on top
# of the bars because a bar standing near it is the case a reader must not miss.
for xi, f in zip(x, floor):
    h_floor, = axL.plot([xi - 1.5 * w, xi + 1.5 * w], [f, f], color="k", lw=1.0,
                        ls=(0, (3, 2)), zorder=4)

# THE OUT-OF-SAMPLE QUANTITY, WHICH IS THE ONE THE SOURCE CALLS LOAD-BEARING. The three
# bars are descriptive: they are computed in sample, and the artifact's own caveats say
# the weight sits not on them but on the label-permutation null and on this leave-one-out
# fit. Predict each fill's markout by the MEAN OF THAT COUNTERPARTY'S OTHER FILLS, on the
# residual after the book control, and score it against the grand mean: the counterparty's
# own fill never enters its own prediction, so nothing here is fitted to what it explains.
# It belongs on this axis and not on the right-hand one because it is a share of the
# variance of the same fills over the same population as the bars beside it.
h_loo, = axL.plot(x, loo, "D", ms=4.0, mfc="white", mec="C3", mew=1.2, zorder=5)

axL.set_xticks(x)
axL.set_xticklabels([f"{c['coin'].replace('POOLED', 'both')}\n{c['K']}" for c in LEFT])
axL.set_xlabel("coin and minimum fills per counterparty")
axL.set_ylabel("share of markout scatter sitting\nbetween counterparties, per cent")
axL.set_title("Subtracting the visible book leaves the\ndifferences between "
              "counterparties standing")
# Handles are passed in the order the eye meets the bars, left to right, with the floor
# last. Left to itself the legend puts the line before the patches, which reads as though
# the floor were the subject and the bars the annotation.
axL.legend([b_raw, b_lin, b_nl, h_floor, h_loo],
           ["raw", "less the linear book", "less the non-linear book",
            "noise floor, 1/K", "out of sample, leave-one-out"],
           loc="upper left", frameon=False, handlelength=1.4, borderpad=0.2,
           labelspacing=0.22)
axL.grid(axis="y", alpha=0.28)
axL.set_axisbelow(True)
axL.set_ylim(0, max(raw.max(), floor.max(), loo.max()) * 1.52)

# --- right ---
xr = np.arange(len(RIGHT), dtype=float)
med = np.array([c["incremental_median_over_seeds"] for c in RIGHT]) * PCT
lo_s = np.array([c["incremental_min_over_seeds"] for c in RIGHT]) * PCT
hi_s = np.array([c["incremental_max_over_seeds"] for c in RIGHT]) * PCT
one = np.array([c["incremental_stored_single_split"] for c in RIGHT]) * PCT

axR.bar(xr, med, width=0.56, color=C_BAR, edgecolor="0.30", linewidth=0.6,
        label=f"median of {N_SEEDS} splits", zorder=2)
axR.errorbar(xr, med, yerr=np.vstack([med - lo_s, hi_s - med]), fmt="none",
             ecolor="k", elinewidth=0.9, capsize=2.4, capthick=0.9, zorder=3,
             label="range of those splits")
axR.plot(xr, one, "o", ms=3.8, mfc="none", mec=C_MARK, mew=1.1, zorder=4,
         label="the stored split")

axR.set_xticks(xr)
axR.set_xticklabels([f"{c['coin']}\n{c['K']}" for c in RIGHT])
axR.set_xlabel("coin and minimum fills per half\nover each bar: the book alone")
axR.set_ylabel("added by the counterparty label,\npercentage points of out-of-sample fit")
axR.set_title(f"Counterparty history adds\nout of sample, at {H_HEADLINE} seconds")
axR.legend(loc="upper left", frameon=False, handlelength=1.5, borderpad=0.2,
           labelspacing=0.25)
axR.grid(axis="y", alpha=0.28)
axR.set_axisbelow(True)
axR.set_ylim(0, hi_s.max() * 1.62)
# Set rather than left to autoscale. Autoscaling fits the BARS, and the note written over
# each outermost bar is a text rather than an artist with data limits, so it is not
# counted and the default five per cent margin leaves it hanging over the frame. The pad
# is the half-width of the widest note plus a little.
axR.set_xlim(xr[0] - 0.75, xr[-1] + 0.75)
# What the public set reaches WITHOUT the label, written over each cell. THE NOTE IS THE
# BARE FIGURE AND ITS MEANING IS STATED ONCE, under the axis. Two earlier drafts carried
# the words "book alone" over every bar, first inside the tick label and then above the
# whisker, and the measurement below refused both: four of them do not fit across four
# bars in two inches, and the second draft failed by five and a half pixels, which is
# under a hundredth of an inch on the printed page and is not something an eye settles.
notes = []
for xi, top, c in zip(xr, hi_s, RIGHT):
    notes.append(axR.text(xi, top + hi_s.max() * 0.045,
                          f"{c['oos_r2_public'] * PCT:.0f}%",
                          ha="center", va="bottom", fontsize=PT_NOTE,
                          color="0.25"))

fig.savefig(OUT_PNG, dpi=DPI_OUT)

# THE LABELS ARE MEASURED AFTER DRAWING RATHER THAN JUDGED BY EYE. These four sit above
# bars whose heights come out of the data, so a rerun on moved numbers can push one into
# its neighbour or off the panel, and both failures are silent in a saved file that
# nobody opens. The boxes are taken from the renderer that just wrote the file, so what
# is measured is what was drawn.
_rend = fig.canvas.get_renderer()


def _side_by_side(texts, panel, what):
    """Refuse if any two of these run into each other, or if one leaves the panel.

    THE POPULATION MATTERS MORE THAN THE RULE, and getting it wrong is how this check
    first passed a broken figure. Its earlier version measured only the four notes over
    the right-hand bars -- the labels that had already been fixed -- and reported a clean
    layout while the tick labels underneath them overlapped into an unreadable run. A
    predicate applied to the part already known to be sound is not a check on the whole.
    So every row of text placed side by side on either panel is passed through here.
    """
    boxes = [t.get_window_extent(renderer=_rend) for t in texts]
    order = sorted(range(len(boxes)), key=lambda i: boxes[i].x0)
    for a, b in zip(order, order[1:]):
        _require(boxes[a].x1 <= boxes[b].x0,
                 f"{what}: {texts[a].get_text()!r} and {texts[b].get_text()!r} overlap by "
                 f"{boxes[a].x1 - boxes[b].x0:.1f} pixels")
    for box, t in zip(boxes, texts):
        for over, side in ((panel.x0 - box.x0, "left edge"),
                           (box.x1 - panel.x1, "right edge"),
                           (box.y1 - panel.y1, "top edge")):
            # Named side by side, because "it leaves the panel" sends a reader hunting
            # through the labels and the edges for the one that moved.
            _require(over <= 1.0,
                     f"{what}: {t.get_text()!r} crosses the panel's {side} by "
                     f"{over:.1f} pixels")


_panelL = axL.get_window_extent(renderer=_rend)
_panelR = axR.get_window_extent(renderer=_rend)
_side_by_side(notes, _panelR, "the figures over the right-hand bars")
_side_by_side(axR.get_xticklabels(), _panelR, "the right-hand cell labels")
_side_by_side(axL.get_xticklabels(), _panelL, "the left-hand cell labels")
# A legend is one block rather than a row, so only its containment is asked. It sits
# inside the axes by choice, and a legend wider than the panel it sits in is the failure
# that put two clipped words on the page.
for ax, panel, what in ((axL, _panelL, "the left-hand legend"),
                        (axR, _panelR, "the right-hand legend")):
    lbox = ax.get_legend().get_window_extent(renderer=_rend)
    for over, side in ((panel.x0 - lbox.x0, "left edge"),
                       (lbox.x1 - panel.x1, "right edge"),
                       (lbox.y1 - panel.y1, "top edge")):
        _require(over <= 1.0,
                 f"{what} crosses the panel's {side} by {over:.1f} pixels")

# TITLES AND AXIS LABELS ARE MEASURED AGAINST THE CANVAS, NOT THE PANEL, because a
# centred title is meant to overhang the axes it belongs to and is only wrong when it
# leaves the page. This is the third population this check had to grow to cover: the
# first version watched four notes, then the cell labels and legends were added after a
# clipped legend reached the file, and both passed a figure whose right-hand title and
# axis label were cut off mid-word at the canvas edge. Every text this file places is now
# measured against something.
#
# THE Y LABEL IS NOT ASKED, and the reason is not that it is safe by assumption. Measured
# on a probe figure: a rotated y label reports an extent from before the layout engine
# placed it -- x0 at 554.9 on a canvas 553 wide, while the label plainly draws inside its
# panel. An instrument that reports a position the drawing does not have would fail every
# honest run, and a check that fires on everything gets switched off. The y label is also
# the one text constrained layout sizes the axes AROUND, so it cannot be the one that
# overflows. The title and the x label report truthfully -- the same probe put the title
# 6.6 pixels past the edge, which is the clipping that prompted this -- and they are asked.
_canvas = fig.get_window_extent(renderer=_rend)
for ax, name in ((axL, "left"), (axR, "right")):
    for text, what in ((ax.title, "title"), (ax.xaxis.label, "x label")):
        box = text.get_window_extent(renderer=_rend)
        for over, side in ((_canvas.x0 - box.x0, "left"), (box.x1 - _canvas.x1, "right"),
                           (_canvas.y0 - box.y0, "bottom"), (box.y1 - _canvas.y1, "top")):
            _require(over <= 1.0,
                     f"the {name} panel's {what} runs off the {side} of the canvas by "
                     f"{over:.1f} pixels, so it reaches the page cut off mid-word")
plt.close(fig)

# ---------------------------------------------------------------------------
# The caption, written here so that the picture and the words it needs travel
# together and cannot drift apart in a document.
# ---------------------------------------------------------------------------
POOLED_50 = next(c for c in LEFT_POOLED if c["K"] == 50)
LEFT_ETH_50 = next(c for c in LEFT if c["coin"] == "ETH" and c["K"] == 50)
LEFT_BTC_50 = next(c for c in LEFT if c["coin"] == "BTC" and c["K"] == 50)
LOO_MIN = min(c["loo_taker_r2_residual"] for c in LEFT)
LOO_MAX = max(c["loo_taker_r2_residual"] for c in LEFT)
ETH_50 = next(c for c in RIGHT if c["coin"] == "ETH" and c["K"] == 50)
NL_MIN = min(c["r2_book_nonlinear"] for c in LEFT)
NL_MAX = max(c["r2_book_nonlinear"] for c in LEFT)
LIN_MAX = max(c["r2_book_linear"] for c in LEFT)

CAPTION = (
    "What is visible before the fill, and what identity adds to it. "
    "LEFT: the share of markout scatter that sits between counterparties rather than "
    "within them, at two floors on the minimum fills a wallet must have, REPORTED PER COIN "
    "because the two coins do not average -- pooling them returns "
    f"{POOLED_50['raw'] * PCT:.2f} per cent at the fifty-fill floor, below both "
    f"{LEFT_BTC_50['raw'] * PCT:.2f} for BTC and {LEFT_ETH_50['raw'] * PCT:.2f} for ETH, "
    "since a wallet trading both contributes one mean across two instruments of different "
    "scale; the pooled cells are in the results file and not on the page. The first bar is "
    "that share as measured; the second and third "
    "recompute it after subtracting the entry state of the visible book -- "
    + "; ".join(CONTROL_WORDS[c] for c in CONTROL_COLS) + " -- "
    f"linearly and then through deciles with their pairwise products. The linear fit "
    f"explains {LIN_MAX * PCT:.1f} per cent of markout variance at most, so the small "
    f"fall onto the second bar is close to a tautology of that near-zero fit and is not "
    f"evidence; the third bar rests on a control worth {NL_MIN * PCT:.1f} to "
    f"{NL_MAX * PCT:.1f} per cent of variance and is the meaningful one. These shares "
    f"are computed IN SAMPLE, with the "
    f"same rows forming the per-wallet averages and the total, which lifts them by "
    f"roughly one over the fill floor even when counterparties are identical; that floor "
    f"is the dashed line, and the pooled fifty-fill cell stands at "
    f"{POOLED_50['raw'] * PCT:.2f} per cent against a floor of "
    f"{LEFT_ETH_50['noise_floor'] * PCT:.1f} per cent. THE THREE BARS ARE THEREFORE "
    f"DESCRIPTIVE AND ARE NOT WHAT THE FINDING RESTS ON: the source puts the weight on a "
    f"label-permutation null and on the open diamond, which is out of sample. That "
    f"diamond predicts each fill's markout by the mean of that counterparty's OTHER "
    f"fills, on the residual after the book control, so no fill enters its own "
    f"prediction; it runs from {LOO_MIN * PCT:.1f} to {LOO_MAX * PCT:.1f} per cent. It is "
    f"a fit rather than a variance share, so it is not the bars' arithmetic complement "
    f"and is placed on this axis only because it is a fraction of the variance of the "
    f"same fills over the same population. RIGHT: out-of-sample test at the "
    f"{H_HEADLINE}-second horizon. A predictor holding the entire public information set "
    f"-- four trade-tape summaries and {len(BOOK_FEATURES)} order-book features, "
    f"{RIGHT[0]['n_public_features']} in all, each averaged over the counterparty's fills "
    f"in days {EARLY_DAYS[0]} to {EARLY_DAYS[-1]} -- predicts that counterparty's mean "
    f"markout over the disjoint days {LATE_DAYS[0]} to {LATE_DAYS[-1]}. The bar is what "
    f"adding one further column, the counterparty's own markout in the early days, adds "
    f"to that fit, scored five-fold across wallets so the coefficient is learned on other "
    f"counterparties. Bars are medians over {N_SEEDS} fold splits and whiskers their "
    f"smallest and largest, as the source instructs; THE WHISKER VARIES ONLY WHICH "
    f"WALLETS FALL IN WHICH FOLD, so it is neither a confidence interval nor sampling "
    f"uncertainty, and the open circle is the single split the file stores, which on the "
    f"ETH fifty-fill cell happens to sit at the "
    f"{ETH_50['stored_percentile_of_own_sweep']:.0f}th percentile of its own spread. The "
    f"percentage written over each bar is what that same public set reaches WITHOUT the "
    f"label, and it is read from the stored single split rather than from the median, "
    f"because the fold sweep records only the increment. Significance here rests on a "
    f"label-permutation placebo corrected for the {B_FAMILY['n_cells_tested']}-cell "
    f"family, not on the height of a bar, and on {N_AT_FLOOR_RECOUNT} of those "
    f"{B_FAMILY['n_cells_tested']} cells no permutation beat the observed lift, so the "
    f"reported p is the resolution floor of {B_DESIGN['n_perm']} draws and is a bound "
    f"rather than a measured smallness. The anonymous arm is not blind to identity: its "
    f"features are per-wallet averages, so it is given the flow already separated by "
    f"counterparty and is denied only that counterparty's past markout. The two panels "
    f"use different units -- a fill on the left, a wallet on the right -- different "
    f"holdouts and different quantities, and their heights are not comparable. THEY ALSO "
    f"HOLD DIFFERENT THINGS CONSTANT, which is the difference most likely to be read past: "
    f"the left panel removes {len(CONTROL_COLS)} quantities of the book at the instant of "
    f"entry, measured on each fill, while the right gives its predictor "
    f"{RIGHT[0]['n_public_features']} quantities of the book AND the trade tape, averaged "
    f"over a counterparty's fills. A wider control on the right is why its bar is the "
    f"stronger statement and not the larger version of the left one. The "
    f"per-coin figures are reported separately because the coins differ: the public book "
    f"leaves ETH toxicity largely unrecovered and recovers much of BTC's, so the pooled "
    f"cells of the right-hand source are marked diagnostic-only there and are not drawn "
    f"here. Sources: i3_depth_control_results.json and "
    f"i3_book_nonrecoverability_results.json."
)

# ---------------------------------------------------------------------------
# The results file: every drawn coordinate in both forms, and what was not drawn.
# ---------------------------------------------------------------------------
results = {
    "object": "I3-PRETRADE-FIGURE - the pre-trade appendix panel: visible book state "
              "against counterparty identity, drawn from two committed artifacts and "
              "computing no new quantity.",
    "figure_file": os.path.basename(OUT_PNG),
    "caption": CAPTION,
    "units": {
        "sources_hold": "fractions",
        "figure_and_caption_show": "per cent and percentage points",
        "conversion": "every drawn value is the source value times 100, applied once",
    },
    "left_panel": {
        "question": "Does the visible state of the book account for the differences "
                    "between counterparties, or do those differences survive it?",
        "source_file": os.path.basename(SRC_DEPTH),
        "unit_of_observation": "one taker fill",
        "in_sample": True,
        "controls": [{"column": c, "meaning": CONTROL_WORDS[c]} for c in CONTROL_COLS],
        "nonlinear_control": D_SCOPE["nonlinear_control"],
        "cells_drawn": [
            {**c,
             "raw_pct": c["raw"] * PCT,
             "after_linear_pct": c["after_linear"] * PCT,
             "after_nonlinear_pct": c["after_nonlinear"] * PCT,
             "noise_floor_pct": c["noise_floor"] * PCT}
            for c in LEFT],
        "producer_caveats_carried_into_the_caption": D_CAVEATS,
    },
    "right_panel": {
        "question": "Over the whole public information set, does one column of "
                    "counterparty history still add out-of-sample lift?",
        "source_file": os.path.basename(SRC_BOOK),
        "unit_of_observation": "one counterparty wallet",
        "out_of_sample": {
            "label_built_on_days": EARLY_DAYS,
            "target_measured_on_days": LATE_DAYS,
            "days_disjoint": True,
            "scoring": f"{B_DESIGN['n_folds']}-fold across wallets",
        },
        "public_information_set": B_DESIGN["public_info_set"],
        "book_feature_names": BOOK_FEATURES,
        "reporting_rule_obeyed": SWEEP["reporting_rule"],
        "whisker_is_not": SWEEP["scope_of_variation"],
        "cells_drawn": [
            {**c,
             "oos_r2_public_pct": c["oos_r2_public"] * PCT,
             "oos_r2_public_plus_fe_pct": c["oos_r2_public_plus_fe"] * PCT,
             "incremental_median_over_seeds_pp": c["incremental_median_over_seeds"] * PCT,
             "incremental_min_over_seeds_pp": c["incremental_min_over_seeds"] * PCT,
             "incremental_max_over_seeds_pp": c["incremental_max_over_seeds"] * PCT}
            for c in RIGHT],
    },
    "recorded_and_not_drawn": {
        "companion_horizon_s": H_COMPANION,
        "why_the_companion_is_not_drawn":
            f"the source calls {H_HEADLINE} s its primary horizon and the {H_COMPANION} s "
            "cells answer a different question; its own registry entry forbids reading "
            "the two horizons as one quantity",
        "companion_cells": [
            {"coin": r["coin"], "K": int(r["K"]), "horizon_s": int(r["horizon_s"]),
             "incremental_oos_r2_stored": r["incremental_oos_r2"],
             "incremental_median_over_seeds":
                 (sweep_cell(r["coin"], r["horizon_s"], r["K"]) or {}).get("median"),
             "placebo_p": r["placebo_p"], "survives_fdr": r["survives_fdr"],
             "interpretation": r["interpretation"]}
            for r in BOOK["by_coin"] if int(r["horizon_s"]) != int(H_HEADLINE)],
        "pooled_cells_of_the_right_hand_source": [
            {"coin": r["coin"], "K": int(r["K"]), "horizon_s": int(r["horizon_s"]),
             "incremental_oos_r2_stored": r["incremental_oos_r2"]}
            for r in BOOK["pooled"]],
        "why_pooled_is_not_drawn": BOOK["headline"]["diagnostic_note"],
        "pooled_cells_of_the_left_hand_source": [
            {**c,
             "raw_pct": c["raw"] * PCT,
             "after_linear_pct": c["after_linear"] * PCT,
             "after_nonlinear_pct": c["after_nonlinear"] * PCT,
             "noise_floor_pct": c["noise_floor"] * PCT}
            for c in LEFT_POOLED],
        "why_the_left_pooled_cells_are_not_drawn": (
            "this source records no prohibition on pooling, unlike the other one, so the "
            "question was put to its own numbers instead of carried over by analogy. They "
            "answer it: the pooled between-counterparty share is SMALLER THAN EITHER "
            "COIN'S at both floors -- "
            + "; ".join(
                f"at the {p['K']}-fill floor {p['raw'] * PCT:.2f} per cent against "
                + " and ".join(f"{c['raw'] * PCT:.2f} for {c['coin']}"
                               for c in LEFT if c["K"] == p["K"])
                for p in LEFT_POOLED)
            + ". A value below both of the things it averages is not a summary of them. "
              "Measured on the panel rather than reasoned about: pooling blends total "
              "markout variance to 43.11 from 19.02 on BTC and 62.86 on ETH, while the "
              "variance between wallet means FALLS to 1.283 from 1.328 and 2.434, because "
              "a wallet trading both coins contributes one mean across two instruments of "
              "different scale instead of two separate ones. The producer of this figure "
              "refuses to run if the pooled cell ever stops sitting below both coins, so "
              "this reason cannot go stale unnoticed"),
    },
    "significance_does_not_come_from_the_drawn_bars": {
        "left": "a label-permutation null on the residual between-counterparty share, "
                "and a leave-one-out per-counterparty fit; both in the source",
        "right": "a label-permutation placebo with Benjamini-Hochberg correction over "
                 "the twelve-cell family; the p of nine cells sits on the resolution "
                 "floor of 2000 draws and is a bound rather than a measured smallness",
        "p_floor": B_DESIGN["p_floor"],
    },
    "registry_entries_covering_the_right_hand_source": [
        "M50", "M51", "M52", "M53", "M54", "M55", "M56", "M57", "M58", "M59", "M60",
        "M61", "M62", "M63", "M64", "M72", "M73",
    ],
    "registry_entries_covering_the_left_hand_source": [],
    "registry_note":
        "the left-hand source has no entry in the value registry, so the caption's "
        "qualifications on it are taken from the artifact's own caveats block instead of "
        "from a registered forbidden claim",
}

scope_block = {
    "population": (
        f"left panel: {LEFT[0]['n_obs_eligible']:,} to "
        f"{max(c['n_obs_eligible'] for c in LEFT):,} taker fills per cell, belonging to "
        f"{min(c['n_wallets'] for c in LEFT):,} to "
        f"{max(c['n_wallets'] for c in LEFT):,} counterparties depending on the fill "
        f"floor, over three populations (each coin and both together) at two floors. "
        f"Right panel: {min(c['n_wallets'] for c in RIGHT)} to "
        f"{max(c['n_wallets'] for c in RIGHT)} counterparties per cell, each clearing "
        f"the floor in BOTH halves of the window, two coins at two floors; the pooled "
        f"cells of that source exist and are excluded on its own instruction"),
    "window": (
        "left panel, quoted from its source rather than restated: "
        + DEPTH["_meta"]["scope"]["window"]
        + f". Right panel: days {EARLY_DAYS[0]}-{EARLY_DAYS[-1]} carry the counterparty "
          f"label and the disjoint days {LATE_DAYS[0]}-{LATE_DAYS[-1]} carry the target"),
    "coins": DEPTH["_meta"]["scope"]["coins"],
}

settings_used = dict(
    h=H_HEADLINE,
    lens=LENS,
    rank_floor_fills=[c["K"] for c in LEFT[:2]],
    master_seed=None,
    n_perm=None,
    n_boot=None,
    early_days=EARLY_DAYS,
    late_days=LATE_DAYS,
    overrides_note=(
        "this file draws and computes no new quantity: every coordinate is read from "
        "i3_depth_control_results.json or i3_book_nonrecoverability_results.json, and "
        "the only arithmetic performed here is multiplying a fraction by one hundred. No "
        "random stream is drawn, so no seed, no permutation count and no bootstrap count "
        "applies, and each is stated as not applying rather than left to be read as the "
        "declaration. The horizon and the reference price are read from settings.py at "
        "run time and are never typed here; the fill floors are read from the artifacts, "
        "because they are a property of the runs being drawn"),
)

artifact.write(os.path.basename(OUT_JSON), results,
               script=__file__, inputs=[SRC_DEPTH, SRC_BOOK], scope=scope_block,
               settings=settings_used, started=T0,
               out_dir=os.path.dirname(OUT_JSON))

print(f"[i3-fig] wrote {os.path.basename(OUT_PNG)} and {os.path.basename(OUT_JSON)}")
print(f"[i3-fig] left: between-counterparty share, raw against the non-linear residual")
for c in LEFT:
    print(f"[i3-fig]   {c['coin']:>6} K={c['K']:<4} raw {c['raw'] * PCT:6.2f}%  "
          f"linear {c['after_linear'] * PCT:6.2f}%  "
          f"non-linear {c['after_nonlinear'] * PCT:6.2f}%  "
          f"floor {c['noise_floor'] * PCT:4.1f}%  "
          f"retain(non-linear) {c['retained_nonlinear']:.3f}")
print(f"[i3-fig] the visible book explains "
      f"{min(c['r2_book_linear'] for c in LEFT) * PCT:.2f} to "
      f"{max(c['r2_book_linear'] for c in LEFT) * PCT:.2f} per cent of markout variance "
      f"linearly, {min(c['r2_book_nonlinear'] for c in LEFT) * PCT:.2f} to "
      f"{max(c['r2_book_nonlinear'] for c in LEFT) * PCT:.2f} per cent non-linearly")
print(f"[i3-fig] right: added by the counterparty label at {H_HEADLINE} s, "
      f"median over {N_SEEDS} fold splits")
for c in RIGHT:
    print(f"[i3-fig]   {c['coin']:>4} K={c['K']:<4} public alone "
          f"{c['oos_r2_public'] * PCT:5.1f}%  adds "
          f"{c['incremental_median_over_seeds'] * PCT:5.1f} pp "
          f"({c['incremental_min_over_seeds'] * PCT:.1f} to "
          f"{c['incremental_max_over_seeds'] * PCT:.1f} across splits), "
          f"stored draw {c['incremental_stored_single_split'] * PCT:.1f} pp at the "
          f"{c['stored_percentile_of_own_sweep']:.0f}th percentile")
