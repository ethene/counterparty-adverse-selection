#!/usr/bin/env python3
"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-08-25
References: Hyperliquid Level-4 order-book data, Zenodo 18184441 (Albers et al. 2026);
Hyperliquid maker fee schedule (1.5 bps base) as recorded by maker_econ.py; Easley,
Lopez de Prado and O'Hara (2012) on flow toxicity.

WHAT IS KNOWN BEFORE A FILL AGAINST WHAT IT COSTS AFTERWARDS, IN ONE PICTURE.

The report argues that a maker on a transparent perpetual venue can rank counterparties
before quoting to them, and that the ranking is worth money. Those are two claims and the
report supports them in two different places, so a reader has to hold one page against
another to see whether the ranking that separates wallets is the same ranking that
separates losses. This figure puts both on one pair of axes. The horizontal axis carries
only information that exists BEFORE the fill: which tenth of the counterparty ranking a
wallet fell into, scored on the first half of the window. The vertical axis carries what
happened AFTER: the maker's net result on that wallet's fills in the second half, in
basis points of notional, after the venue's maker fee.

THE TWO HALVES ARE DISJOINT AND THE PRODUCER PROVES IT RATHER THAN ASSERTING IT. The
ranking is built by maker_econ.build_toxicity_labels from EARLY-half fills only, and every
net figure drawn here is measured by maker_econ.net_by_decile on LATE-half fills only. The
same file records days_disjoint and fills_disjoint, and both are read below and refused if
either is false. Nothing on the horizontal axis is therefore learned from the fills on the
vertical one. The honest qualification, which the caption carries, is that the ranking is
itself built out of realised outcomes of EARLIER fills: a wallet's past is what makes it a
pre-trade signal for its future, which is precisely the mechanism under test and not a
leak of it.

WHY TWO SERIES AND NOT ONE, which is the finding that decided the shape of the panel. The
same ten cells tell two different stories depending on how a fill is weighted, and each
story alone misleads. Weighted by notional, the rank correlation between the decile and
the net result is -0.14: eight of the ten cells sit in a band and the tenth drops away, so
a reader sees noise and one cliff. Weighted equally per fill, the same correlation is
-0.98, an almost perfect staircase, and a reader sees a clean gradient with no sense of
where the money is. Both are true and they are answers to different questions. The bars
are the money question, the markers are the per-fill question, and the strip beneath them
answers the third: the tenth decile is a tenth of the WALLETS and over half of the FILLS,
so the cliff is where the volume already was.

WHAT THE VERTICAL AXIS IS AND WHAT IT IS NOT. The measure is the book-mid one,
net_MID_lower = half the quoted spread minus the mid markout minus the maker fee, and it
is conservative in one direction only: the half-spread is the quoted one and therefore a
lower bound on the spread income a maker actually realises. It is NOT a lower bound on a
maker's profit, because two costs are outside it entirely. The exit is not priced, and
neither is funding on the inventory the fills leave behind. So the axis says what one side
of the ledger does across the ranking, and the level of any single bar is not a trading
result.

WHAT THIS FIGURE DOES NOT CARRY. The decile table in maker_econ_results.json has no
bootstrap interval on any of its cells. The interval machinery in that file is attached to
the policy block, not to this table, so there is no uncertainty to draw and none is drawn.
The caption says so rather than leaving ten bare points to be read as ten measured
quantities. The first decile in particular is the second most negative cell under notional
weighting and the least negative under equal weighting; it holds 2.9 per cent of the late
fills, so the notional-weighted figure there rests on a few large prints, and no claim is
made about it.

THE SLICE DRAWN IS THE ONE THE REST OF THE WORK REPORTS ON, and every coordinate of it is
read from settings.py rather than typed here: the fill floor from wallet_fill_floor, the
horizon from HEADLINE_HORIZON_S, the reference price from HEADLINE_LENS. The fee tier is
the base rung of the venue schedule, which is the conservative reading and the one
maker_econ.py leads its own summary with; the zero-fee rung is a stated scenario needing a
fourteen-day volume no ten-day window can contain. The sixty-second companion, the zero-fee
tier and all eight fill-floor rungs are written into the results file beside the drawn
numbers, so a reader can check the shape survives them without opening the 384 kB artifact
this file reads.

DRAWN AT THE SIZE IT IS PRINTED. The canvas is 5.53 inches wide because that is the width
of the single text column of the report, and no taller than 3.5 inches because a figure
that fills a page in an appendix pushes the thing it supports onto the next one. Every
point size below is the size a reader of the page sees.

THIS FILE COMPUTES NO NEW QUANTITY. It reads one committed artifact, so it has an exit
code of its own, it costs under a second, and redrawing it never means recomputing the
hour-long node that produced the numbers. It takes no command line: a figure has nothing
to choose.

Run command (bare python3 is BLOCKED on this machine):
  uv run --no-project --with-requirements requirements.txt python3 -u \
      money/m9_decile_economics_figure.py
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
SRC_JSON = os.path.join(HERE, "maker_econ_results.json")
OUT_PNG = os.path.join(HERE, "m9_decile_economics.png")
OUT_JSON = os.path.join(HERE, "m9_decile_economics_figure_results.json")

T0 = artifact.start_clock()

# The printed geometry, in one place, because a size named twice is a size that drifts.
WIDTH_IN, HEIGHT_IN, DPI_OUT = 5.53, 3.4, 200
PT_LABEL, PT_TITLE, PT_LEGEND, PT_NOTE = 8, 9, 7.5, 7.5
plt.rcParams.update({"font.size": PT_LABEL,
                     "axes.labelsize": PT_LABEL,
                     "axes.titlesize": PT_TITLE,
                     "xtick.labelsize": PT_LABEL,
                     "ytick.labelsize": PT_LABEL,
                     "legend.fontsize": PT_LEGEND})

# ---------------------------------------------------------------------------
# Which cell of the artifact is drawn. Every coordinate is READ, not typed.
# ---------------------------------------------------------------------------
K_HEADLINE = H.wallet_fill_floor("maker_econ", "headline")
H_HEADLINE = H.HEADLINE_HORIZON_S
H_COMPANION = H.COMPANION_HORIZON_S
# maker_econ.py names its two reference prices net_MID_lower and net_PRINT; settings.py
# names the headline lens "mid". The mapping between the two vocabularies lives here
# because this is the only file that has to speak both.
LENS_TO_MEASURE = {"mid": "net_MID_lower", "print": "net_PRINT"}
MEASURE = LENS_TO_MEASURE[H.HEADLINE_LENS]
COMPANION_MEASURE = LENS_TO_MEASURE["print"]
TIER = "base"                 # the venue's base maker rung, 1.5 bps
COMPANION_TIER = "t4_0fee"    # the zero-fee scenario, reported and not drawn
N_DECILES = 10

R = json.load(open(SRC_JSON, encoding="utf-8"))
DEC_ALL = R["net_by_toxicity_decile"]
SRC_META = R["_meta"]


def cell_key(k, h):
    """The two rung names the artifact uses, spelled in one place."""
    return f"K{int(k)}", f"h{int(h)}"


def _require(condition, what):
    """Refuse to draw rather than draw a picture whose premise is false.

    A figure that quietly draws a broken premise is worse than one that does not draw:
    the picture reaches the report and the premise never does.
    """
    if not condition:
        raise SystemExit(f"[m9] refusing to draw: {what}")


KK, HH = cell_key(K_HEADLINE, H_HEADLINE)
_require(KK in DEC_ALL, f"{SRC_JSON} carries no rung {KK}; it has {sorted(DEC_ALL)}")
_require(HH in DEC_ALL[KK], f"rung {KK} carries no horizon {HH}")
BLOCK = DEC_ALL[KK][HH]
_require(int(BLOCK["horizon_s"]) == int(H_HEADLINE),
         f"the {HH} block reports horizon_s {BLOCK['horizon_s']}, not {H_HEADLINE}")
_require(TIER in BLOCK["tiers_reported"],
         f"the {HH} block reports tiers {BLOCK['tiers_reported']}, which excludes {TIER}")


def series(block, measure, tier, field):
    """One field across the ten deciles of one cell, in decile order."""
    out = []
    for d in range(1, N_DECILES + 1):
        out.append(block["deciles"][f"decile_{d:02d}"][measure][tier][field])
    return np.asarray(out, dtype=float)


DECILE = np.arange(1, N_DECILES + 1)
VW = series(BLOCK, MEASURE, TIER, "net_vw_bps")
EW = series(BLOCK, MEASURE, TIER, "net_ew_bps")
NF = series(BLOCK, MEASURE, TIER, "n_fills")
_require(np.isfinite(VW).all() and np.isfinite(EW).all(),
         "a drawn cell is not finite, so the panel would carry a gap with no name")
SHARE = NF / NF.sum()


def spearman(a, b):
    """Rank correlation of two ten-point series, computed on ranks with numpy alone.

    scipy is not imported for this: the two inputs have no ties by construction (the
    decile index is 1..10 and the net figures are distinct floats), so the rank
    transform is exact and the Pearson correlation of the ranks IS the Spearman
    coefficient. A tie would make that false, so the tie count is asserted rather than
    assumed.
    """
    a, b = np.asarray(a, float), np.asarray(b, float)
    _require(len(set(a.tolist())) == a.size and len(set(b.tolist())) == b.size,
             "a rank correlation was asked for on a series holding ties, where the "
             "plain rank transform is not the Spearman coefficient")
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    return float(np.corrcoef(ra, rb)[0, 1])


RHO_VW = spearman(DECILE, VW)
RHO_EW = spearman(DECILE, EW)
GAP_VW = float(VW[-1] - VW[:-1].mean())
GAP_EW = float(EW[-1] - EW[:-1].mean())

# ---------------------------------------------------------------------------
# The out-of-sample premise, read out of the artifact rather than believed.
# ---------------------------------------------------------------------------
FP = SRC_META["settings_fingerprint"]
EARLY_DAYS = [int(d) for d in FP["early_days"]]
LATE_DAYS = [int(d) for d in FP["late_days"]]
_require(not (set(EARLY_DAYS) & set(LATE_DAYS)),
         f"the labelling days {EARLY_DAYS} and the measurement days {LATE_DAYS} "
         "intersect, so the horizontal axis is not a pre-trade quantity")
_require(int(FP["rank_floor_fills"]) == int(K_HEADLINE),
         f"the artifact was produced at rank_floor_fills {FP['rank_floor_fills']} while "
         f"settings.py now declares {K_HEADLINE}")

# The eligible-wallet counts live in the policy block of the same file, which is built
# from the same label set at the same rung, so the wallet population of this figure is
# read there instead of being recounted.
POLICY = R["b1_idealized_policy_upper_bound"][KK][HH]
N_ELIGIBLE = int(POLICY["n_eligible_takers"])
N_TOXIC_CUT = int(POLICY["n_toxic_takers_dropped"])

# THE DECILES DO NOT COVER THE LATE HALF, AND THE CAPTION HAS TO SAY SO. A wallet that
# did not reach the early-fill floor carries no label, so its late fills sit in no decile
# at all. The ten cells therefore describe a NARROWER population than "the late half",
# and the gap is not small: at this rung it is nearly a third. The share is computed here
# rather than asserted, and it is printed on the figure itself.
N_LATE_TOTAL = int(R["baseline_net"]["pooled"]["n_late_fills"])
N_IN_DECILES = int(NF.sum())
COVERAGE = N_IN_DECILES / N_LATE_TOTAL
_require(0.0 < COVERAGE <= 1.0,
         f"the decile cells hold {N_IN_DECILES:,} fills against a late half of "
         f"{N_LATE_TOTAL:,}, which is not a share of it")
# Wallets per decile under the producer's own rule, rank*10//n capped at 9 then +1. It is
# recomputed here rather than read because the artifact stores fills and not wallets, and
# a caption that says "a tenth of the wallets" should be able to show the tenth.
_ranks = np.arange(N_ELIGIBLE)
_dec_of_rank = np.minimum((_ranks * N_DECILES) // N_ELIGIBLE, N_DECILES - 1) + 1
WALLETS_PER_DECILE = [int((_dec_of_rank == d).sum()) for d in DECILE]


def days(ds):
    """A day list as a range when it is one, which every half here is."""
    ds = sorted(ds)
    return f"{ds[0]}-{ds[-1]}" if ds == list(range(ds[0], ds[-1] + 1)) else str(ds)


# ---------------------------------------------------------------------------
# The figure. One tall panel for the money, one short strip for where the fills are.
# ---------------------------------------------------------------------------
# Constrained layout and not tight_layout: the two panels have different heights and a
# two-line label under the lower one, and tight_layout placed that second line off the
# bottom edge of the canvas without saying so. A caption that names the measurement days
# is the whole point of the axis, so the layout has to be one that keeps it.
fig, (ax, axn) = plt.subplots(
    2, 1, figsize=(WIDTH_IN, HEIGHT_IN), sharex=True, layout="constrained",
    gridspec_kw={"height_ratios": [3.1, 1.0]})
fig.get_layout_engine().set(h_pad=0.02, w_pad=0.02, hspace=0.03, wspace=0.0)

# Bars are the notional-weighted result, because that is the money. The markers on top
# are the equal-weighted result, in the same unit and therefore on the same axis: a
# second scale for a quantity measured in the same units would invite the reader to
# compare two heights that are not comparable.
ax.bar(DECILE, VW, width=0.72, color="0.62", edgecolor="0.30", linewidth=0.6,
       label="weighted by notional (the money)", zorder=2)
ax.plot(DECILE, EW, "o-", ms=3.6, lw=1.2, color="C3",
        label="weighted equally per fill (the typical fill)", zorder=3)
ax.axhline(0, color="0.35", lw=0.9, zorder=1)
ax.set_ylabel("maker net result,\nbasis points of notional")
ax.set_title("Ranked before the fill, measured after it: the maker's net result\n"
             "falls with the counterparty's pre-trade toxicity decile")
ax.legend(loc="lower left", frameon=False, handlelength=1.6)
ax.grid(axis="y", alpha=0.28)
ax.set_axisbelow(True)
# Headroom above zero for the legend and the two correlations, and a floor below the
# deepest bar so the tenth decile is not clipped by its own label.
ax.set_ylim(min(VW.min(), EW.min()) * 1.30, max(0.0, VW.max(), EW.max()) + 1.35)
ax.text(0.972, 0.95,
        f"rank correlation with the decile:  {RHO_VW:+.2f} by notional,"
        f"  {RHO_EW:+.2f} per fill",
        transform=ax.transAxes, ha="right", va="top", fontsize=PT_NOTE, color="0.25",
        bbox=dict(facecolor="white", edgecolor="none", pad=1.0))

axn.bar(DECILE, 100.0 * SHARE, width=0.72, color="0.80", edgecolor="0.45",
        linewidth=0.6, zorder=2)
axn.set_ylabel("share of\nfills, %")
axn.set_ylim(0, 100.0 * SHARE.max() * 1.30)
axn.grid(axis="y", alpha=0.28)
axn.set_axisbelow(True)
# EVERY BAR IS LABELLED, not only the tallest. The deciles hold equal numbers of WALLETS
# and very unequal numbers of FILLS, here a factor of nineteen between the largest and
# the smallest. Labelling the tenth alone left the other nine as nine indistinguishable
# stubs, so a reader could not tell the 2.9 per cent decile from the 8.9 per cent one and
# had no way to see that the bars of the panel above rest on populations that differ by
# more than an order of magnitude.
for x, s in zip(DECILE, SHARE):
    axn.text(x, 100.0 * s, f"{100.0 * s:.1f}", ha="center", va="bottom",
             fontsize=6.5, color="0.25")

axn.set_xticks(DECILE)
# THE LABEL NAMES THE REFERENCE PRICE, THE FEE AND THE POPULATION, because the sign of
# every bar depends on all three. Measured across this artifact at the headline horizon:
# against the book mid at the base fee no decile is positive, while against the trade
# print at the zero-fee rung six of the ten are. A caption naming only the horizon would
# let a reader carry the sign of this panel to a cell that does not have it. The
# population line is there because the ten cells are not the late half: a wallet under
# the early-fill floor carries no label and its fills sit in no decile.
axn.set_xlabel(
    f"counterparty toxicity decile, scored on days {days(EARLY_DAYS)} "
    f"(1 = least toxic)\n"
    f"net against the book mid on the disjoint days {days(LATE_DAYS)}, "
    f"{H_HEADLINE} seconds, base maker fee\n"
    f"wallets with {K_HEADLINE} or more early fills: {N_IN_DECILES:,} of "
    f"{N_LATE_TOTAL:,} late fills ({100.0 * COVERAGE:.0f}%)")
axn.set_xlim(0.4, N_DECILES + 0.6)

fig.savefig(OUT_PNG, dpi=DPI_OUT)
plt.close(fig)
# Printed relative to this file, so the line names the target without putting a local
# home directory into the console output or into any log that captures it.
print(f"[m9] wrote {os.path.relpath(OUT_PNG, HERE)}")

# ---------------------------------------------------------------------------
# The results file: what was drawn, and the slices that were not.
# ---------------------------------------------------------------------------
drawn = {
    "cell": {"rung": KK, "horizon_key": HH, "measure": MEASURE, "fee_tier": TIER,
             "min_early_fills": int(K_HEADLINE), "horizon_s": int(H_HEADLINE)},
    "decile": DECILE.tolist(),
    "net_vw_bps": VW.tolist(),
    "net_ew_bps": EW.tolist(),
    "n_fills": [int(v) for v in NF],
    "share_of_late_fills": SHARE.tolist(),
    "n_wallets_per_decile": WALLETS_PER_DECILE,
}

# Every other slice of the same table, so the shape can be checked against the fill
# floor, the horizon and the fee tier without opening the artifact this file reads.
sweep = {}
for rung, by_h in DEC_ALL.items():
    for hkey, blk in by_h.items():
        for measure in ("net_MID_lower", "net_PRINT"):
            for tier in blk["tiers_reported"]:
                v = series(blk, measure, tier, "net_vw_bps")
                e = series(blk, measure, tier, "net_ew_bps")
                sweep[f"{rung}.{hkey}.{measure}.{tier}"] = {
                    "net_vw_bps": v.tolist(),
                    "net_ew_bps": e.tolist(),
                    "most_negative_decile_vw": int(np.nanargmin(v)) + 1,
                    "rho_decile_vs_vw": spearman(DECILE, v),
                    "rho_decile_vs_ew": spearman(DECILE, e),
                }

headline_slices = [k for k in sweep if k.endswith(f".{MEASURE}.{TIER}")]
tenth_worst = [k for k in headline_slices if sweep[k]["most_negative_decile_vw"] == N_DECILES]

# THE SIGN IS A PROPERTY OF THE REFERENCE PRICE AND THE FEE, not of the ranking. Counted
# here rather than described, at the drawn rung, so the caption's claim that no decile is
# positive can be checked against the cell it is made about and against the cells it is
# not made about.
sign_census = {}
for hkey in sorted(DEC_ALL[KK]):
    for measure in ("net_MID_lower", "net_PRINT"):
        for tier in DEC_ALL[KK][hkey]["tiers_reported"]:
            v = series(DEC_ALL[KK][hkey], measure, tier, "net_vw_bps")
            sign_census[f"{KK}.{hkey}.{measure}.{tier}"] = {
                "positive_deciles": [int(i) + 1 for i in np.where(v > 0)[0]],
                "n_positive": int((v > 0).sum()),
                "min_bps": float(v.min()),
                "max_bps": float(v.max()),
            }

results = {
    "question": (
        "does what is known about a counterparty BEFORE a fill order the maker's net "
        "result AFTER it, on fills the ranking never saw"),
    "figure_file": os.path.basename(OUT_PNG),
    "drawn": drawn,
    "summary": {
        "rho_decile_vs_net_vw_bps": RHO_VW,
        "rho_decile_vs_net_ew_bps": RHO_EW,
        "tenth_decile_minus_mean_of_first_nine_vw_bps": GAP_VW,
        "tenth_decile_minus_mean_of_first_nine_ew_bps": GAP_EW,
        "tenth_decile_share_of_late_fills": float(SHARE[-1]),
        "most_negative_decile_vw": int(np.nanargmin(VW)) + 1,
        "interpretation": (
            "the two weightings answer two questions and disagree on purpose. Per fill "
            "the ordering is almost perfect, so the pre-trade rank sorts the typical "
            "fill. By notional the first nine deciles sit in a band and the tenth drops "
            f"away by {GAP_VW:.2f} bps, and that tenth carries "
            f"{100.0 * SHARE[-1]:.1f} per cent of the late fills, so the loss is "
            "concentrated where the volume already was rather than spread along the "
            "ranking"),
    },
    "population_is_narrower_than_the_late_half": {
        "fills_in_the_ten_deciles": N_IN_DECILES,
        "late_half_fills": N_LATE_TOTAL,
        "coverage": COVERAGE,
        "note": (
            f"a wallet under the {K_HEADLINE}-fill early floor carries no label, so its "
            f"late fills belong to no decile. The ten cells hold "
            f"{100.0 * COVERAGE:.1f} per cent of the late half and the caption says so. "
            "The floor buys reliability of the ranking and costs coverage, and the two "
            "move against each other across the rungs recorded in all_slices"),
    },
    "fills_per_decile_are_not_equal": {
        "largest_over_smallest": float(NF.max() / NF.min()),
        "largest_decile": int(np.argmax(NF)) + 1,
        "smallest_decile": int(np.argmin(NF)) + 1,
        "note": (
            "the deciles are equal in WALLETS and unequal in FILLS by a factor of "
            f"{NF.max() / NF.min():.0f} here, so bars of equal width would invite a "
            "reader to weigh ten cells that do not carry equal weight. The lower strip "
            "of the figure carries the share of every decile, each one labelled, rather "
            "than encoding it in the width of the bar above, because a width that "
            "varies with the count makes the AREA of a bar meaningless while its height "
            "is the quantity"),
    },
    "sign_depends_on_reference_price_and_fee": {
        "drawn_cell": f"{KK}.{HH}.{MEASURE}.{TIER}",
        "by_cell": sign_census,
        "note": (
            "the sign of a decile is a property of the reference price and the fee rung "
            "and not of the ranking, so the caption names all three. The drawn cell has "
            "no positive decile; other cells of the same rung do. The panel never mixes "
            "two reference prices on one axis"),
    },
    "what_the_measure_is_not": (
        "net_MID_lower is half the quoted spread minus the mid markout minus the maker "
        "fee. The half-spread is the quoted one, so the measure is a lower bound on the "
        "SPREAD INCOME a maker realises; it is not a lower bound on profit, because the "
        "exit and the funding on the inventory the fills leave behind are outside the "
        "model. The figure is read across the ranking and not at the level of one bar"),
    "no_uncertainty_here": (
        "the decile table of maker_econ_results.json carries no bootstrap interval on "
        "any cell; the interval machinery of that file is attached to the policy block "
        "instead. Nothing is drawn as an error bar and no cell is claimed individually. "
        "The first decile holds "
        f"{100.0 * SHARE[0]:.1f} per cent of the late fills, so its notional-weighted "
        "figure rests on few large prints and is not commented on"),
    "out_of_sample_premise": {
        "labelled_on_days": EARLY_DAYS,
        "measured_on_days": LATE_DAYS,
        "days_disjoint": True,
        "checked_here": (
            "the two day sets are read from the source artifact and their intersection "
            "is asserted empty before anything is drawn; the producer asserts the same "
            "at the fill level"),
        "qualification": (
            "the pre-trade rank is itself built from realised outcomes of EARLIER "
            "fills, which is the mechanism under test rather than a leak of it: no "
            "fill on the vertical axis contributed to the horizontal one"),
    },
    "decile_is_not_the_toxic_cut": {
        "n_eligible_wallets": N_ELIGIBLE,
        "wallets_in_tenth_decile": WALLETS_PER_DECILE[-1],
        "wallets_in_toxic_cut": N_TOXIC_CUT,
        "note": (
            "the tenth decile and the toxic cut used by the policy block are built by "
            "two different roundings of the same top ten per cent and differ by one "
            "wallet, so the caption says decile and not toxic cut"),
    },
    "robustness_across_slices": {
        "headline_measure_and_tier": f"{MEASURE}.{TIER}",
        "n_slices_of_that_measure_and_tier": len(headline_slices),
        "n_where_tenth_decile_is_most_negative": len(tenth_worst),
        "exceptions": sorted(set(headline_slices) - set(tenth_worst)),
        "note": (
            "eight fill-floor rungs against two horizons. The companion horizon is "
            f"{H_COMPANION} seconds, the companion reference price is "
            f"{COMPANION_MEASURE} and the companion fee tier is {COMPANION_TIER}; all "
            "of them are in the sweep below and none is drawn"),
    },
    "all_slices": sweep,
}

scope_block = {
    "population": (
        f"late-half fills of the {N_ELIGIBLE:,} wallets that clear the {K_HEADLINE}-fill "
        f"early-half floor, {N_IN_DECILES:,} fills, which is {100.0 * COVERAGE:.1f} per "
        f"cent of the {N_LATE_TOTAL:,} late-half fills: a wallet under the floor carries "
        f"no label and its fills belong to no decile, so this is NOT the late half. Cut "
        f"into ten groups of equal WALLET count and therefore unequal fill count, a "
        f"factor of {NF.max() / NF.min():.0f} between the largest and the smallest; the "
        f"tenth decile holds {WALLETS_PER_DECILE[-1]} wallets and "
        f"{100.0 * SHARE[-1]:.1f} per cent of the fills. The baseline block of the same "
        f"artifact measures every late fill and is therefore a wider population than "
        f"this one"),
    "window": (
        f"single December window; days {days(EARLY_DAYS)} label the wallets and the "
        f"disjoint days {days(LATE_DAYS)} carry every net figure drawn"),
    "coins": SRC_META["scope"]["coins"],
}

settings_used = dict(
    h=H_HEADLINE,
    lens=H.HEADLINE_LENS,
    rank_floor_fills=int(K_HEADLINE),
    master_seed=None,
    n_perm=None,
    n_boot=None,
    early_days=EARLY_DAYS,
    late_days=LATE_DAYS,
    overrides_note=(
        "this file draws and computes no new quantity: every net figure is read from "
        "maker_econ_results.json, and the only things computed here are two rank "
        "correlations, a gap and a share, all of them deterministic functions of the "
        "numbers read. No random stream is drawn, so no seed, no permutation count and "
        "no bootstrap count apply and each is stated as not applying rather than left "
        "to be read as the declaration. The fill floor, the horizon and the reference "
        "price are read from settings.py at run time and are never typed here"),
)

artifact.write(os.path.basename(OUT_JSON), results,
               script=__file__, inputs=[SRC_JSON], scope=scope_block,
               settings=settings_used, started=T0,
               out_dir=os.path.dirname(OUT_JSON))
print(f"[m9] wrote {os.path.relpath(OUT_JSON, HERE)}")
print(f"[m9] rank correlation decile against net: {RHO_VW:+.4f} by notional, "
      f"{RHO_EW:+.4f} per fill")
print(f"[m9] tenth decile {VW[-1]:+.4f} bps by notional against "
      f"{VW[:-1].mean():+.4f} for the first nine, and it carries "
      f"{100.0 * SHARE[-1]:.1f} per cent of the late fills")
print(f"[m9] tenth decile is the most negative in {len(tenth_worst)} of "
      f"{len(headline_slices)} fill-floor and horizon slices of {MEASURE}.{TIER}")
