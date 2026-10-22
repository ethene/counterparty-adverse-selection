#!/usr/bin/env python3
"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-08-03
References: Hyperliquid Level-4 order-book data, Zenodo 18184441 (Albers et al. 2026).

A hard, principled toxic/not classifier (replaces the flat top-decile cut).

Three ingredients, all at the score horizon settings.py names as the headline one and
read here as headline_mid_col(); the window is never typed in this file:
  1. SHRINKAGE score (Buhlmann credibility): tau* = w_i*mean_i + (1-w_i)*mu,
     w_i = n_i/(n_i+n0), n0 = within-wallet var / between-wallet var (estimated, not tuned).
     Thin wallets are pulled to the population mean so a few lucky fills can't look extreme.
  2. SIGNIFICANCE: per-wallet z = mean_i / SE_i (SE from the wallet's own fill variance). A wallet
     is a toxic CANDIDATE only if its early score is significantly > 0 given its fill count.
  3. THRESHOLD by OUT-OF-SAMPLE VALIDITY: the early shrunk score predicts which wallets are in the
     costliest late-window decile (ROC/AUC, Youden's J cutoff), cross-checked against an ECONOMIC
     break-even cutoff (markout > maker half-spread income + rebate => unprofitable to serve).
     The captured-cost-vs-flagged-fraction curve is reported so the conclusion is not knife-edge.

NO LOOKAHEAD: the score and every threshold are chosen on the EARLY half; the LATE half is the
prediction target only. The halves are cut by settings.split_early_late over the days the input
carries, which on this December window resolves to days 4-8 and 9-13. Placebo (shuffle late
labels) must give AUC ~0.5. The break-even line obeys the same rule since 2026-08-05: the median
spread it is built from is taken over the EARLY half, where it used to be taken over the whole
window, so both sides of that comparison now know the same days. What the Youden cutoff still
carries is a different matter and is declared rather than repaired here: it is the argmax of a
search scored against the late half, and checks/chk_decision_lookahead.py holds the entry.

Liquidation negative-control anchor: forced liquidations are a known non-toxic class, but the
liquidation flag was dropped at npz-persist and is ~0% on BTC/ETH (they concentrate in alts), so that
specificity check is deferred to a targeted re-pull (documented limitation, per the pre-registration).

Inputs (local, de-id): quickwin_markouts_mid.npz.
Outputs: ws2_hard_classifier_results.json, ws2_hard_classifier.png.
"""
import os
import sys

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

HERE = os.path.dirname(os.path.abspath(__file__))
# The two artifacts this file writes, named once. A verification pass re-points these
# and nothing else, which is what lets the module be re-run without copying it.
# Located by panel_io rather than joined here, so the one place that knows where the
# markout panels live is the one place that has to change if they move.
IN_NPZ = os.path.join(P.data_root(), "quickwin_markouts_mid.npz")
OUT_JSON = os.path.join(HERE, "ws2_hard_classifier_results.json")
OUT_PNG = os.path.join(HERE, "ws2_hard_classifier.png")
# The early and late halves are DERIVED from the days the input actually carries, by
# settings.split_early_late, and are never day-of-month sets typed here. The two forms
# agree on this file's input and only on it: quickwin_markouts_mid.npz runs 4 to 13, so
# the rule returns 4-8 and 9-13, the sets this file used to declare. On a window that
# begins on the 6th the typed sets would cut a three-day half against a seven-day one.
# Minimum fills per wallet in EACH half. This is the LOOSEST rung of
# settings.RANK_FLOOR_SENSITIVITY, well below the declared RANK_FLOOR_FILLS of 50, and
# settings.py says plainly what that costs: at a 10-fill floor the measured split-half
# reliability is about 0.33 to 0.39, so most of a disattenuated score is the correction
# rather than the signal. Shrinkage is the answer this file gives to that -- a thin
# wallet is pulled to the population mean instead of being trusted -- but the floor is a
# deviation from the declaration and is recorded as an override, not inherited quietly.
# READ from settings.py and never typed. The declaration returns the same 10 this file
# has always run, so reading it moves no p and no AUC; what it removes is the second home
# the number used to have. The spelling `K` was in no alias list of the settings gate
# until 2026-07-31, so this site had never been counted anywhere.
K = H.wallet_fill_floor("ws2_hard_classifier", "both_halves")
# No seed literal lives here any more. The one random stream this file draws comes from
# settings.MASTER_SEED and the name of what it is drawing for, through settings.rng. This
# file used to declare 20260619, which is not the declared seed, so its p-value could not
# be compared with any other script's: a difference between two p-values would have been
# a difference of seeds as much as of statistics.
# Label-permutation draws, READ from settings.py and never typed. The budget fixes the
# p-value floor at 1/(N+1), and a p reported at the floor says only that no draw beat the
# observed value: the true p is unknown below that point. At the 200 draws this file used
# to declare, the floor was 0.00498 and the single AUC p below sat exactly on it, so the
# artifact reported a bound and not a measurement. settings.N_PERM is computed from the
# level, the family size and the margin rather than chosen, so the floor follows them.
N_PERM = H.N_PERM


def auc_mannwhitney(score, label):
    """AUC = P(score of a positive > score of a negative). Rank-based."""
    order = np.argsort(score, kind="stable")
    ranks = np.empty(score.size); ranks[order] = np.arange(1, score.size + 1)
    # average ties
    s = score[order]; i = 0
    while i < s.size:
        j = i
        while j + 1 < s.size and s[j + 1] == s[i]:
            j += 1
        if j > i:
            ranks[order[i:j + 1]] = (i + 1 + j + 1) / 2.0
        i = j + 1
    n1 = label.sum(); n0 = label.size - n1
    if n1 == 0 or n0 == 0:
        return np.nan
    return float((ranks[label == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def main():
    t0 = artifact.start_clock()
    # panel_io names the producer to run when the file is absent, so that message
    # is written once for the whole tree; the load itself stays here because
    # build.py derives this script's input edge from the argument of np.load.
    P.require_present("mid", IN_NPZ)
    z = np.load(IN_NPZ)
    taker = np.asarray(z["taker_id"], np.int64); coin = np.asarray(z["coin"], np.int8)
    day = np.asarray(z["day"], np.int16)
    mo = P.score(z, "mid")                 # headline window and mid lens, settings.py
    notl = np.asarray(z["notional"], np.float64); spread = np.asarray(z["spread_entry_bps"], np.float64)
    n = taker.size
    unit = taker * 4 + coin.astype(np.int64); nu = int(unit.max()) + 1
    early_days, late_days = H.split_early_late(np.unique(day))
    ie = np.isin(day, list(early_days)); il = np.isin(day, list(late_days))

    def wallet_stats(mask):
        fin = mask & np.isfinite(mo)
        cnt = np.bincount(unit[fin], minlength=nu).astype(float)
        s1 = np.bincount(unit[fin], weights=mo[fin], minlength=nu)
        s2 = np.bincount(unit[fin], weights=mo[fin] ** 2, minlength=nu)
        with np.errstate(invalid="ignore", divide="ignore"):
            mean = np.where(cnt > 0, s1 / np.maximum(cnt, 1), np.nan)
            var = np.where(cnt > 1, (s2 - cnt * mean ** 2) / np.maximum(cnt - 1, 1), np.nan)
        # late-window per-dollar cost for the label
        snt = np.bincount(unit[mask], weights=notl[mask], minlength=nu)
        cost = np.where(snt > 0, np.where(np.isfinite(mean), mean, 0) * snt, np.nan)  # $ adverse-selection
        return cnt, mean, var, cost

    e_cnt, e_mean, e_var, _ = wallet_stats(ie)
    l_cnt, l_mean, l_var, l_cost = wallet_stats(il)

    elig = (e_cnt >= K) & (l_cnt >= K) & np.isfinite(e_mean) & np.isfinite(l_mean)
    idx = np.where(elig)[0]
    em = e_mean[idx]; ev = e_var[idx]; ec = e_cnt[idx]
    lm = l_mean[idx]; lc = l_cost[idx]

    # ---- 1. Buhlmann shrinkage on the EARLY score ----
    mu = float(np.average(em, weights=ec))                     # population mean (fill-weighted)
    var_within = float(np.average(ev[np.isfinite(ev)], weights=ec[np.isfinite(ev)]))  # mean sampling var per fill
    var_between = float(np.var(em) - var_within / np.mean(ec))  # between-wallet var (noise-corrected)
    var_between = max(var_between, 1e-9)
    n0 = var_within / var_between                              # credibility constant (estimated)
    w = ec / (ec + n0)
    tau_star = w * em + (1 - w) * mu

    # ---- 2. per-wallet significance (one-sided z that mean>0) ----
    se = np.sqrt(np.where(ec > 0, ev / ec, np.inf))
    zscore = np.where(se > 0, em / se, 0.0)
    n_sig_toxic = int(np.sum(zscore > 1.645))                  # p<0.05 one-sided, raw score>0

    # ---- 3a. threshold by OOS validity: predict costliest late decile ----
    late_cost_pos = np.where(np.isfinite(lc), lc, 0.0)
    lab = (late_cost_pos >= np.quantile(late_cost_pos, 0.90)).astype(int)  # costliest late decile
    auc_shrunk = auc_mannwhitney(tau_star, lab)
    auc_raw = auc_mannwhitney(em, lab)
    # placebo: shuffle labels
    rng = H.rng("ws2", "auc_placebo", K)
    auc_perm = np.array([auc_mannwhitney(tau_star, rng.permutation(lab)) for _ in range(N_PERM)])
    auc_p = float((np.sum(auc_perm >= auc_shrunk) + 1) / (N_PERM + 1))

    # Youden's J cutoff on tau_star
    thr_grid = np.quantile(tau_star, np.linspace(0.5, 0.995, 60))
    best_j, thr_youden = -1, None
    for t in thr_grid:
        pred = tau_star >= t
        tp = np.sum(pred & (lab == 1)); fn = np.sum(~pred & (lab == 1))
        fp = np.sum(pred & (lab == 0)); tn = np.sum(~pred & (lab == 0))
        tpr = tp / max(tp + fn, 1); fpr = fp / max(fp + tn, 1)
        if tpr - fpr > best_j:
            best_j, thr_youden = tpr - fpr, float(t)

    # ---- 3b. economic break-even cutoff: markout > half-spread income + rebate ----
    # THE MEDIAN IS TAKEN ON THE EARLY HALF, THE HALF THE DECISION IS TAKEN ON. It used to
    # be taken over every finite row of the window while the score it is compared with is
    # the early-half shrunk score, so one side of the comparison knew days nine to thirteen
    # and the other did not. A maker standing on day four does not hold a median over ten
    # days, and a line built from one is drawn after the fact.
    #
    # What the repair costs, measured on 2026-08-05 rather than assumed small: the finite
    # spread column has 2,478,215 rows over the window and 1,244,769 in the early half, and
    # their medians are 0.301482 and 0.315075 basis points, so the break-even line moves
    # from 0.4507 to 0.4575, which is 1.51 percent of itself. The DIRECTION is the part that
    # matters. The whole-window line sat BELOW the causal one, so it declared unprofitable a
    # band of wallets whose score falls between the two, and every one of them is a wallet a
    # maker could not have refused on the day the flag fires: 3,708 of the 5,539 eligible
    # units were flagged on the old line against 3,696 on this one.
    half_spread = float(np.median(spread[ie & np.isfinite(spread)]) / 2.0)
    rebate = 0.3
    breakeven_bps = half_spread + rebate
    # flagged as "unprofitable to serve" if the (shrunk) early score exceeds break-even
    n_econ_toxic = int(np.sum(tau_star >= breakeven_bps))

    # ---- capture curve: flagged fraction -> share of late $ cost captured (smoothness) ----
    order = np.argsort(-tau_star)
    lc_pos = np.where(np.isfinite(lc) & (lc > 0), lc, 0.0)[order]
    total_cost = lc_pos.sum()
    cum = np.cumsum(lc_pos) / total_cost if total_cost > 0 else np.zeros_like(lc_pos)
    fracs = np.arange(1, order.size + 1) / order.size
    def capture_at(frac):
        k = max(int(frac * order.size), 1)
        return float(cum[k - 1])
    curve = {f"{int(fr*100)}pct": capture_at(fr) for fr in (0.05, 0.10, 0.20, 0.30, 0.50)}
    frac_youden = float(np.mean(tau_star >= thr_youden))
    frac_econ = float(np.mean(tau_star >= breakeven_bps))

    # What every number in this file was computed under. It used to sit in the payload
    # as a top-level key, which is a third placement of one record; artifact.write is
    # the single place that stamps it.
    settings_used = dict(
        h=H.HEADLINE_HORIZON_S, lens="mid",
        master_seed=H.MASTER_SEED,
        n_perm=N_PERM,
        n_boot=None,
        rank_floor_fills=K,
        persistence_floor_fills=None,
        whale_drop_k=None,
        fdr_alpha=None,
        early_late_split=(
            f"settings.split_early_late over the days present: "
            f"early {list(early_days)}, late {list(late_days)}"),
        p_floor=H.p_floor(N_PERM),
        overrides_note=(
            "rank_floor_fills 10, the loosest rung of settings.RANK_FLOOR_SENSITIVITY "
            "and NOT the declared 50: at ten fills a per-wallet mean is mostly noise, "
            "which is why this file shrinks thin wallets to the population mean rather "
            "than ranking them raw; master_seed is settings.MASTER_SEED and is stated "
            "as a CONFIRMATION rather than a deviation, the placebo stream being "
            "derived from it and the name of the draw through settings.rng, where "
            "this file used to declare 20260619; n_perm is settings.N_PERM and is "
            "likewise stated as a CONFIRMATION "
            "rather than a deviation, so the floor is 1/(N_PERM+1) and not the "
            "0.00498 the earlier 200-draw artifact reported; no bootstrap is drawn, "
            "so n_boot does not apply; there is one "
            "test here, not a family, so no FDR level applies, and no whale-drop arm "
            "runs. The halves are cut by settings.split_early_late over the days "
            "present, which on this input returns the same 4-8 / 9-13 the file "
            "used to type"),
        )

    # What the numbers cover. The unit is the wallet-coin pair, eligible only when it
    # clears the fill floor in BOTH halves, so the population states that and not the
    # row count alone.
    days_present = np.unique(day)
    scope_block = {
        "population": (f"{n:,} fills of the book-mid panel aggregated to wallet-coin "
                       f"units; {idx.size:,} units are eligible, needing at least "
                       f"{K} fills in EACH half with a finite mean in both"),
        "window": (f"{days_present.size} days present in the input, day-of-month "
                   f"{days_present.min()}-{days_present.max()}, split early "
                   f"{list(early_days)} against late {list(late_days)}"),
        "coins": [H.coin_labels("quickwin")[c]
                  for c in sorted(H.coin_labels("quickwin"))],
    }

    results = {
        "score_horizon_s": H.HEADLINE_HORIZON_S,
        "score_column": H.headline_mid_col(),
        "K": K, "n_eligible": int(elig.sum()),
        "shrinkage": {"mu_bps": mu, "var_within": var_within, "var_between": var_between,
                      "n0_credibility": n0, "mean_weight": float(np.mean(w))},
        "significance": {"n_sig_toxic": n_sig_toxic, "frac_sig_toxic": float(n_sig_toxic / idx.size)},
        "oos_validity": {"auc_shrunk": auc_shrunk, "auc_raw_meanscore": auc_raw,
                         "auc_placebo_mean": float(np.mean(auc_perm)), "auc_p": auc_p,
                         "auc_p_floor": H.p_floor(N_PERM),
                         # True means no shuffled-label draw reached the observed AUC, so
                         # the p is the budget's smallest expressible value.
                         "auc_p_is_floor": bool(H.p_is_floored(auc_p, N_PERM)),
                         "youden_threshold_bps": thr_youden, "youden_flag_fraction": frac_youden},
        "economic": {"median_half_spread_bps": half_spread, "rebate_bps": rebate,
                     "breakeven_bps": breakeven_bps, "n_econ_toxic": n_econ_toxic,
                     "econ_flag_fraction": frac_econ},
        "capture_curve_share_of_late_cost": curve,
        "capture_at_youden": capture_at(frac_youden), "capture_at_econ": capture_at(frac_econ),
        "liquidation_anchor": "DEFERRED - flag dropped at npz-persist and ~0% on BTC/ETH; needs targeted re-pull",
        "interpretation": (
            "Toxic/not is now a principled rule, not a flat decile: a Buhlmann-shrunk "
            f"{H.HEADLINE_HORIZON_S}s score "
            "(thin wallets pulled to the mean), a per-wallet significance filter, and a cutoff set by "
            "out-of-sample validity (AUC predicting the costliest late decile) and by economic "
            "break-even (markout above half-spread+rebate = unprofitable to serve). The captured-cost "
            "curve is smooth, so the conclusion does not hinge on an exact percentile.")
    }
    print(f"[ws2] eligible wallets={idx.size}, n0(credibility)={n0:.2f}, mu={mu:.3f}bps, mean w={np.mean(w):.3f}")
    print(f"[ws2] significantly toxic (z>1.645, mean>0): {n_sig_toxic} ({100*n_sig_toxic/idx.size:.1f}%)")
    print(f"[ws2] OOS AUC (shrunk)={auc_shrunk:.3f} raw={auc_raw:.3f} "
          f"placebo={np.mean(auc_perm):.3f} p={auc_p:.5f}"
          + (f"  [FLOOR: no draw of {N_PERM} reached the observed AUC, so this p is the "
             f"budget's smallest value, not a measurement]"
             if H.p_is_floored(auc_p, N_PERM) else ""))
    print(f"[ws2] Youden cutoff={thr_youden:.3f}bps -> flags {100*frac_youden:.1f}% wallets, captures {100*capture_at(frac_youden):.1f}% of late cost")
    print(f"[ws2] economic break-even={breakeven_bps:.2f}bps (half-spread {half_spread:.2f}+rebate {rebate}) -> flags {100*frac_econ:.1f}%, captures {100*capture_at(frac_econ):.1f}%")
    print(f"[ws2] capture curve: " + ", ".join(f"{k}:{100*v:.0f}%" for k, v in curve.items()))

    # The output name and directory still come from the module-level OUT_JSON, so a
    # caller that redirects that constant redirects the whole write, as before.
    artifact.write(os.path.basename(OUT_JSON), results,
                   script=__file__, inputs=[IN_NPZ], scope=scope_block,
                   settings=settings_used, started=t0,
                   out_dir=os.path.dirname(OUT_JSON))
    print(f"[ws2] wrote {os.path.basename(OUT_JSON)}")

    draw(results, OUT_PNG, series={"flagged_fraction": fracs, "captured_share": cum,
                                   "raw_early_mean_bps": em, "shrunk_score_bps": tau_star,
                                   "early_fill_count": ec})


def _pyplot():
    """Return pyplot, or refuse in words and exit non-zero. Never a silent success.

    The refusal is the point. A catch that printed "plot skipped" and returned zero is
    an error that reads as success, which is the direction that travels: on 2026-08-02
    this node wrote a correct results file, could not import matplotlib under the short
    launch form, said so in one line and exited zero, and the figure beside it stayed two
    days old with the pre-fix AUC and threshold drawn on it.
    """
    try:
        import matplotlib
    except ImportError as e:
        raise SystemExit(
            f"[ws2] REFUSED to draw the figure: {e}. This tree is launched with\n"
            "  uv run --no-project --with-requirements requirements.txt python3 <script>\n"
            "and the short --with numpy form resolves no matplotlib at all. Exiting "
            "non-zero on purpose: a figure that was not drawn must not read as a run "
            "that finished.")
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


# The five per-wallet series the figure draws and the results file does NOT carry, named
# here once so the refusal below can name them rather than say "some data is missing".
PLOT_SERIES = ("flagged_fraction", "captured_share",
               "raw_early_mean_bps", "shrunk_score_bps", "early_fill_count")


def draw(results, out_png, series):
    """Draw the two-panel classifier figure. Scalars from `results`, curves from `series`.

    Every scalar the figure prints -- the AUC, both cutoffs, the captured shares, the
    credibility constant, the score window -- is read out of the results payload, so those
    cannot drift from the artifact. The two panels also need five per-wallet series that
    the payload does not carry, and `series` is where a full run hands them over.

    Why they are not written to the artifact, measured rather than assumed: the five run
    to one value per eligible wallet-coin unit, 5539 of them on the December window, and
    JSON-encoding them adds 481,650 bytes to a results file that is 5,123 bytes today.
    The node's own recorded runtime is 2.798 seconds. Paying a ninety-fold growth of a
    results file to save under three seconds of recompute is the wrong trade, so this is
    the one figure of the four with no pure-reader path: its two sisters, ws1_plot.py and
    ws3_plot.py, redraw from their artifacts alone, and this one is drawn where the
    arrays are. What the results file does NOT carry is named in PLOT_SERIES rather than
    left to be discovered, because a figure drawn from a reduced set of series would be a
    different figure wearing this one's file name.
    """
    plt = _pyplot()
    fracs = series["flagged_fraction"]; cum = series["captured_share"]
    em = series["raw_early_mean_bps"]; tau_star = series["shrunk_score_bps"]
    ec = series["early_fill_count"]
    h = results["score_horizon_s"]
    auc_shrunk = results["oos_validity"]["auc_shrunk"]
    frac_youden = results["oos_validity"]["youden_flag_fraction"]
    frac_econ = results["economic"]["econ_flag_fraction"]
    breakeven_bps = results["economic"]["breakeven_bps"]
    n0 = results["shrinkage"]["n0_credibility"]
    cuts = [(frac_youden, "Youden", "C1", results["capture_at_youden"]),
            (frac_econ, "break-even", "C2", results["capture_at_econ"]),
            (0.10, "top-decile", "C3",
             results["capture_curve_share_of_late_cost"]["10pct"])]

    # THE CANVAS IS THE PRINTED SIZE, NOT A SCREEN SIZE SHRUNK ON THE WAY IN. This figure
    # was drawn twelve inches wide and the report placed it at the 105 mm the template
    # calls a sensible width for our column, so everything on it was reduced to 0.34 of
    # itself on the way to the page. Measured off the old image rather than reasoned
    # about: axis labels left at the default ten points arrived at 3.4 and the legend at
    # 2.8, beside body text of eleven, and the drawn box of the left panel, 12.8 by 10.6
    # cm of canvas, arrived at 4.4 by 3.7. Nothing in the drawing was wrong and every
    # scale on it was unreadable, which is a figure failing on legible scales
    # without one wrong number anywhere. So the type sizes below are stated in the points
    # they are meant to be READ at, and the canvas is 5.5 inches wide, which is the width
    # of the template's text block: placed at natural size one drawn point is one printed
    # point, and squeezed to the 105 mm column the axis labels still come out at 6 points
    # and the legend at 5.6.
    FIG_W_IN, FIG_H_IN, FIG_DPI = 5.5, 7.0, 200
    FS_AXIS, FS_TITLE, FS_LEGEND, FS_CBAR = 8, 9, 7.5, 8
    # STACKED RATHER THAN SIDE BY SIDE, and that follows from the width instead of from
    # taste. Two panels sharing 5.5 inches get a column of 6.98 cm each, and the side
    # label with its tick numbers takes 2.03 cm of that on this layout, so under 5 cm of
    # drawn box is left, against the 6 cm the template sets as the smallest side a figure
    # may have. A side-by-side pair at print size fails that rule. One above the other
    # each panel keeps the whole width, and the boxes this file actually draws measure
    # 9.02 by 6.67 cm -- counted off the saved image at its 200 dots per inch, not
    # predicted -- so both sides clear the rule when the report places the figure at its
    # own 5.5 inches. Placed instead at the 105 mm the template calls a sensible column
    # width the panels come back to 6.8 by 5.0 cm and the short side fails again, so the
    # placement that goes with this canvas is natural size and it is not a free choice.
    # THE COLOUR BAR GETS A COLUMN OF THE GRID, NOT A SLICE OF THE PANEL IT BELONGS TO.
    # Asked for the ordinary way it is cut out of the lower panel and out of that panel
    # only, which leaves the two stacked plot boxes ending at different places on the
    # right. Side by side nobody sees that; one above the other it reads as two figures
    # that happened to be filed together. A narrow second column, empty on the upper row,
    # holds both panels to the same width by construction rather than by adjustment.
    # CONSTRAINED LAYOUT AND NOT tight_layout, and the reason is the line above rather
    # than a preference. tight_layout cannot place an axes that holds a colour bar: run
    # with it on 2026-08-08 this figure printed "Axes that are not compatible with
    # tight_layout" and then drew what that means -- the vertical label of the upper
    # panel cut off at the left edge of the sheet, its horizontal label sitting on top
    # of the lower panel's title, and the colour bar's own label cut off at the right.
    # The warning is the useful kind, since it names the defect before the reader sees
    # it; what is not safe is to keep the call and read the warning as noise.
    fig = plt.figure(figsize=(FIG_W_IN, FIG_H_IN), constrained_layout=True)
    gs = fig.add_gridspec(2, 2, width_ratios=[28, 1], wspace=0.06)
    ax1 = fig.add_subplot(gs[0, 0])
    ax2 = fig.add_subplot(gs[1, 0])
    cax = fig.add_subplot(gs[1, 1])
    ax1.plot(fracs * 100, cum * 100, "-", color="C0", label="captured late $ cost")
    ax1.plot([0, 100], [0, 100], ":", color="grey", label="random")
    for frac, name, col, captured in cuts:
        ax1.axvline(frac * 100, ls="--", color=col, alpha=0.8,
                    label=f"{name} ({frac*100:.0f}% flagged, {100*captured:.0f}% cost)")
    # THE UNIT SITS IN PARENTHESES AND NOTHING ELSE DOES. Both labels used to carry
    # "percent" after a comma, and the horizontal one then spent its parentheses on the
    # score the ranking is taken by. The report template asks the opposite: "If including
    # units in the label, present them within parentheses." So the qualifier moves out
    # into the sentence and the unit moves in, which also stops a reader from reading
    # "(by the shrunk 10-second score)" as the scale the axis is counted in.
    # THE LINE BREAKS ARE PART OF THE PRINT SIZE AND CARRY NO WORDS OF THEIR OWN. Every
    # label here says exactly what it said on the twelve-inch canvas. What changed is the
    # box it has to fit inside: 12.8 by 10.6 cm of canvas then, 9.02 by 6.67 now. Set on
    # one line at eight points and measured with the renderer rather than guessed, the
    # side label of this panel runs 9.74 cm along a side 6.67 cm long and the label under
    # it runs 11.04 cm across a box 9.02 cm wide, so both are cut at the edge of the
    # sheet. They are broken where the phrase breaks. The label of the panel below, at
    # 8.06 cm, fits its width and stays on one line, which is why the breaks are not put
    # in everywhere for symmetry. The alternative -- shortening the words -- would pay
    # for the layout with the thing a reader needs most, which is an axis named in
    # words rather than in symbols.
    ax1.set_xlabel(f"share of counterparty wallets flagged by the\n"
                   f"shrunk {h}-second score (percent)", fontsize=FS_AXIS)
    ax1.set_ylabel("share of late-window dollar\nadverse-selection cost\ncaptured (percent)",
                   fontsize=FS_AXIS)
    ax1.tick_params(labelsize=FS_AXIS)
    # WRITTEN OUT. This title carried "AUC" bare, which is an initialism a reader of the
    # report is not given anywhere on the page, and every graph owes its reader a title
    # and legible labels.
    # TWO LINES AND SMALLER TYPE, measured rather than guessed. Spelling the initialism
    # out took this title past the six inches of its panel: drawn on one line at the
    # default size it was clipped at the left edge and its right half sat on top of the
    # title beside it, back when there was a title beside it. A figure whose two titles
    # overlap is worse than one that abbreviates, so the wording that fixes the
    # initialism has to pay for its own width. Stacking the panels removes the collision
    # -- there is no neighbour to the right of this title any more -- and the break stays
    # because the two lines are two statements, the second of which is the reading the
    # panel is drawn to support and not a continuation of the first.
    ax1.set_title(f"Capture curve is smooth (area under the curve {auc_shrunk:.3f})\n"
                  f"cutoff is a choice, not a cliff", fontsize=FS_TITLE)
    ax1.legend(fontsize=FS_LEGEND, loc="lower right"); ax1.grid(alpha=0.3)
    # shrinkage effect: raw vs shrunk score
    sc = ax2.scatter(em, tau_star, s=3, alpha=0.2, c=ec, cmap="viridis")
    ax2.plot([em.min(), em.max()], [em.min(), em.max()], ":", color="grey")
    ax2.axhline(breakeven_bps, color="C2", ls="--",
                label=f"break-even {breakeven_bps:.2f} basis points")
    ax2.set_xlabel(f"raw early-window {h}-second mean markout (basis points)",
                   fontsize=FS_AXIS)
    # Broken for the same reason as the vertical label of the panel above, and with the
    # same words: on one line it measures 6.71 cm along a side that is 6.67 cm long, so
    # it fails by four millimetres rather than by a lot, which is the way a label gets
    # left alone until someone reads the printed page.
    ax2.set_ylabel("Buhlmann credibility-shrunk\nscore (basis points)", fontsize=FS_AXIS)
    ax2.tick_params(labelsize=FS_AXIS)
    # The credibility constant is named in words and given its unit. Drawn as "n0=17.1"
    # it was a symbol standing for a quantity the picture never names, and the number is
    # a count of fills rather than a pure number, which is the part a reader cannot guess.
    ax2.set_title(f"Shrinkage pulls thin wallets to the mean\n"
                  f"(credibility constant {n0:.1f} fills)", fontsize=FS_TITLE)
    # THE THIRD SCALE OF THIS PANEL HAD NO KEY. Fill count is encoded as colour and was
    # named only in the panel title, which tells a reader what the colour means but never
    # what any particular shade is worth: a scale drawn without its own axis. A figure
    # owes its reader axes, labels and scales, and colour is the scale
    # that is easiest to leave unlabelled because it does not look like an axis.
    cb = fig.colorbar(sc, cax=cax)
    # Named with its unit in parentheses like the two drawn axes, because this is the
    # third axis of the panel, and a colour scale is owed the same as a drawn one. What is counted here is fills and not wallets or dollars, and
    # the scale runs to tens of thousands, so the reader who is not told cannot tell.
    # Broken over two lines on the print-size canvas: written along the bar it measures
    # 7.54 cm against the 6.67 the bar is tall, and a key cut off at the edge of the
    # sheet labels nothing.
    cb.set_label("fills by the wallet in the early\nwindow (number of fills)",
                 fontsize=FS_CBAR)
    cb.ax.tick_params(labelsize=FS_AXIS)
    # The points are drawn at one fifth opacity so a dense cloud stays readable. The key
    # must not inherit that: a washed-out colour bar cannot be matched to the points it
    # explains, which would leave the scale labelled and still unusable.
    cb.solids.set_alpha(1.0)
    ax2.legend(fontsize=FS_LEGEND, loc="upper left"); ax2.grid(alpha=0.3)
    # 200 dots per inch, and on a canvas drawn at the printed width that number means on
    # the page what it says here. It did not before: 130 dots on twelve inches is 1560
    # across, and 1560 squeezed into 105 mm is 377 to the printed inch, so the density
    # that reached the reader was a by-product of the reduction rather than a setting.
    # Take the reduction away and the setting has to stand on its own, which is why it
    # is stated beside the canvas it belongs to instead of being left where it was.
    fig.savefig(out_png, dpi=FIG_DPI)
    print(f"[ws2] wrote {os.path.basename(out_png)}")


if __name__ == "__main__":
    # The drawing is NOT wrapped in a catch that returns success. It used to be, and the
    # cost is measured: the short launch form has no matplotlib, so on 2026-08-02 this run
    # printed "plot skipped", exited zero, wrote a fresh results file and left a two-day-old
    # figure standing beside it. A missing figure now leaves a non-zero code.
    #
    # AND THIS FILE TAKES NO COMMAND LINE, which is a decision and not an omission. Its
    # two sister figures were split out into pure readers of their own results files, and
    # this one cannot be: PLOT_SERIES names the five per-wallet series it draws and the
    # results file carries none of them, for the measured reason in draw()'s docstring.
    # A flag that could only ever refuse is worse than no flag, because build.py denies a
    # bare run to every producer that reads its command line, and this node has to keep
    # running bare inside a recompute.
    main()
