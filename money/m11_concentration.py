"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-19
References: Hyperliquid node-data S3 archive; Zenodo 18184441 (Albers et al. 2026).
"""

# ---------------------------------------------------------------------------
# OBJECT M11 — TOXICITY vs COST CONCENTRATION (honest reframing)
#
# An earlier cut of this script led with a dollar-cost concentration figure
# ("top 1% of wallets hold ~87% of adverse-selection cost", Gini ~0.98) and
# read it as evidence that "a handful of wallets drive adverse selection." A
# verification pass showed that reading is WRONG. The dollar-cost Gini is an
# artefact of trade-SIZE inequality, not of toxicity dispersion:
#
#   * If every fill's markout is replaced by the GLOBAL MEAN markout (so per-fill
#     toxicity is held constant), the dollar-cost Gini is still ~0.977. Almost
#     all of the dollar Gini is therefore just notional inequality -- the top-cost
#     wallets are simply the biggest traders, carrying near-average markouts.
#   * The quantity that actually measures "who is toxic" is the PER-DOLLAR
#     markout (cost per unit notional, in bps). It is SIGNED -- roughly half of
#     wallets are net-toxic and the mean is negative, so the average
#     counterparty is mildly UN-toxic. A Gini on the full signed vector is not
#     meaningful (a shift-by-min Gini collapses toward 0, ~0.025, and is kept
#     only as a labelled diagnostic). The sign-appropriate measure is the Gini
#     of the NET-TOXIC subset -- the wallets with positive per-dollar markout.
#
# A later adversarial audit showed the FIRST cut of that net-toxic Gini was
# itself inflated by un-filtered tiny single-fill wallets: with no minimum-fills
# filter, a wallet that trades once carries a single noisy 10s markout that
# self-selects into the net-toxic subset on its own sign. About 64% of net-toxic
# wallets have < 10 fills and several thousand are single-fill, so the unfiltered
# subset is dominated by noise and the Gini reads HIGH (~0.58 pooled). The script
# now reports the net-toxic concentration at min-fills cuts of >= 1 / >= 10 / >= 25
# side by side and takes the HEADLINE at >= 10 fills (~0.53 pooled Gini, top-1%
# ~7.8%, top-10% ~37%; >= 25 is ~0.51). The unfiltered >= 1 cut (~0.58) is kept
# only as an explicitly-labelled INFLATED LOWER BOUND. Two further honesty notes:
# the pdm>0 net-toxic subset is selected in-sample by the same markout that then
# measures its dispersion (an upward bias on the Gini), and the BTC-vs-ETH gap
# (~0.55 vs ~0.58 raw) collapses to ~0.02 under filtering and has no standard
# error, so it is NOT reported as a finding. The headline cut carries a
# wallet-level bootstrap CI.
#
# So the honest takeaway is TWO-SIDED: DOLLAR COST is concentrated because TRADE
# SIZE is concentrated (the dollar Gini ~0.98 is a size artefact, not toxicity
# concentration); and AMONG NET-TOXIC WALLETS with a non-trivial fill count
# per-dollar toxicity is only MODERATELY concentrated (headline Gini ~0.53), while
# the AVERAGE wallet is near-neutral/negative and about half are not toxic at all.
# This does NOT support "a handful of wallets drive all adverse selection". A
# counterparty-resolved quoting rule that keys off "biggest dollar losers" would
# mostly be re-discovering "biggest traders".
#
# This script therefore LEADS with per-dollar toxicity, reports the raw
# dollar-cost concentration ONLY alongside its held-constant-toxicity
# counterfactual (so the size artefact is visible), and replaces the old
# drop-one-whale check with drop-top-10/50/100 plus a notional-controlled view
# (each wallet's share of cost against its share of notional).
#
# Per-wallet dollar cost = sum over the wallet's fills of (mo10 / 1e4) * notional
# where mo10 is the SIGNED taker markout in basis points at the 10-second
# horizon (positive = taker profited = maker lost). This sum is retained but is
# NO LONGER the headline.
#
# numpy-only. No plotting here: Lorenz x/y points are stored in the JSON so a
# later figure step can draw them without re-running the heavy join.
# ---------------------------------------------------------------------------

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
from stats import (describe_quantiles, gini, hhi, top_k_share,
                   top_pct_share)

# ---------------------------------------------------------------------------
# Paths / config
# ---------------------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
# Located by panel_io rather than joined here, so the one place that knows where
# the markout panels live is the one place that has to change if they move.
NPZ_PATH = os.path.join(P.data_root(), "quickwin_markouts.npz")
OUT_PATH = os.path.join(HERE, "m11_results.json")

# int8 code -> symbol. The map is a property of the FILE, not of the project
# (quickwin_markouts.npz carries {0, 1}, panel_markouts.npz carries {0, 1, 2}), so it
# is asked for by artifact name and never written out here.
COIN_NAME = H.coin_labels("quickwin")

# Number of Lorenz sample points stored for the figure. The curve is monotone
# and smooth, so a fixed grid keeps the JSON small without losing shape.
LORENZ_POINTS = 200

# Top-k wallet counts to report shares for. 1% is handled separately (it is a
# fraction of the wallet count, not a fixed k).
TOPK_COUNTS = (10, 50, 100)

# Minimum-fills cuts for the net-toxic concentration sensitivity. The headline
# concentration is reported at HEADLINE_MIN_FILLS; the >= 1 cut is kept only as
# an (inflated) lower bound because it lets one noisy single-fill 10s markout
# enter the net-toxic subset and self-select on its own sign.
MIN_FILLS_CUTS = (1, 10, 25)
HEADLINE_MIN_FILLS = 10

# Bootstrap settings for the headline net-toxic concentration CI. Resamples
# wallets (the net-toxic subset at the headline cut) with replacement. Seconds-
# scale on this npz.
#
# READ from settings.py since 2026-07-31, where it used to be the literal 800.
# This file was the sixth bootstrap consumer and the one no census in this
# repository had ever resolved: the spelling BOOTSTRAP_DRAWS is in no alias list
# of checks/chk_settings_home.py, so the gate never reported the site, and the
# per-purpose map never carried it. The declared budget is 2000, which puts fifty
# draws in each tail of a 95 percent interval against the twenty this file drew,
# so the three percentile blocks below move and the point estimates beside them
# do not.
BOOTSTRAP_DRAWS = H.boot_draws("m11_concentration")
BOOTSTRAP_SEED = H.MASTER_SEED   # the declared seed; this file already ran on it, so
                                 # reading it from settings.py moves no number

# The drop-top-k arms rank wallets by their GROSS DOLLAR COST, and the keys say so.
# A key reading only "drop_top10" does not say top ten by what, and dropping the ten
# largest by cost asks "is this ten wallets" while dropping the ten largest by
# notional asks "is this a volume artifact" -- different questions with different
# answers, which is why settings.whale_drop puts the criterion inside the key.
DROP_KEYS = {k: H.whale_drop("gross_cost", k)["key"] for k in TOPK_COUNTS}
CONTROLLED_KEYS = {
    k: f"top{k}_by_" + H.whale_drop("gross_cost", k)["criterion"]
    for k in TOPK_COUNTS
}


# ---------------------------------------------------------------------------
# Per-wallet aggregation
# ---------------------------------------------------------------------------
def wallet_aggregate(taker_id, cost_per_trade, notional, mo_weighted):
    """Aggregate per-trade quantities into per-wallet totals.

    taker_id        : int array, the wallet code on each trade.
    cost_per_trade  : float array, maker signed loss per trade (quote units).
    notional        : float array, trade notional in quote units (>= 0).
    mo_weighted     : float array, mo10 * notional per trade (for a notional-
                      weighted mean markout; summed then divided by notional).

    Returns (wallet_ids, wallet_cost, wallet_notional, wallet_mo_weighted,
    wallet_fills), all aligned and sorted by wallet id. wallet_fills is the
    number of trades the wallet appears in (used by the min-fills sensitivity).
    The per-dollar markout for a wallet is wallet_mo_weighted / wallet_notional
    and is computed by the caller so the zero-notional guard lives in one place.
    """
    if taker_id.size == 0:
        z = np.empty(0, dtype=np.float64)
        return (np.empty(0, dtype=np.int64), z, z.copy(), z.copy(),
                np.empty(0, dtype=np.int64))
    uniq, inv = np.unique(taker_id, return_inverse=True)
    cost = np.zeros(uniq.size, dtype=np.float64)
    notl = np.zeros(uniq.size, dtype=np.float64)
    mow = np.zeros(uniq.size, dtype=np.float64)
    fills = np.zeros(uniq.size, dtype=np.int64)
    np.add.at(cost, inv, cost_per_trade.astype(np.float64))
    np.add.at(notl, inv, notional.astype(np.float64))
    np.add.at(mow, inv, mo_weighted.astype(np.float64))
    np.add.at(fills, inv, 1)
    return uniq, cost, notl, mow, fills


def per_dollar_markout(wallet_mo_weighted, wallet_notional):
    """Notional-weighted mean markout per wallet, in bps (cost per unit notional).

    This is the toxicity measure that matters: it strips out trade size, so a
    big wallet and a small wallet with the same average markout score the same.
    Wallets with zero notional are returned as NaN and excluded by callers.
    """
    out = np.full(wallet_notional.shape, np.nan, dtype=np.float64)
    nz = wallet_notional > 0
    out[nz] = wallet_mo_weighted[nz] / wallet_notional[nz]
    return out


# ---------------------------------------------------------------------------
# Distribution math
#
# gini, hhi, top_k_share, top_pct_share and describe_quantiles come from stats.py,
# which m8_makerside.py imports as well. They used to be defined in both files; the
# two spellings were identical on the syntax tree, so a reader had no way to tell
# which was the one this work reports and no reason to hope they agreed forever.
# What stays here is what only this file does: the signed diagnostic below and the
# Lorenz sampling, neither of which m8 has any use for.
# ---------------------------------------------------------------------------
def gini_signed(values):
    """DIAGNOSTIC ONLY -- DO NOT CITE. Shift-by-min Gini of a signed vector.

    Per-dollar markout is signed (many counterparties are un-toxic, i.e.
    negative cost per unit notional). This function shifts the values by their
    own minimum so the plain Lorenz construction can run. On this data the shift
    is large relative to the spread, so the statistic collapses toward 0
    (~0.025 pooled) and SAYS NOTHING about toxicity concentration -- a
    shift-by-min Gini is not a meaningful inequality measure for signed data.
    It is retained only as a labelled diagnostic; the headline concentration
    uses gini() on the net-toxic (positive per-dollar) subset instead.
    Returns NaN if the shifted total is non-positive (e.g. all values identical).
    """
    v = np.asarray(values, dtype=np.float64)
    v = v[np.isfinite(v)]
    if v.size == 0:
        return float("nan")
    shifted = v - v.min()
    total = shifted.sum()
    if total <= 0:
        return float("nan")
    return gini(shifted)


def lorenz_curve(values, n_points=LORENZ_POINTS):
    """Lorenz x/y points for a non-negative vector.

    x = cumulative fraction of units (poorest-to-richest),
    y = cumulative fraction of the total.
    Both start at (0, 0) and end at (1, 1). The full cumulative curve is
    sub-sampled onto a fixed grid of n_points so the stored JSON is compact.
    Returns (x_list, y_list) as plain Python floats, or empty lists if the
    total is non-positive.
    """
    v = np.sort(np.asarray(values, dtype=np.float64))
    n = v.size
    total = v.sum()
    if n == 0 or total <= 0:
        return [], []
    cum = np.cumsum(v) / total
    cum = np.concatenate(([0.0], cum))            # prepend the (0,0) origin
    x_full = np.arange(0, n + 1, dtype=np.float64) / n
    if n + 1 <= n_points:
        x_s, y_s = x_full, cum
    else:
        # sample evenly across the unit-fraction axis (always keep endpoints)
        grid = np.linspace(0.0, 1.0, n_points)
        idx = np.clip(np.round(grid * n).astype(int), 0, n)
        x_s, y_s = x_full[idx], cum[idx]
    return [float(a) for a in x_s], [float(b) for b in y_s]


# ---------------------------------------------------------------------------
# (1) HEADLINE — per-dollar (notional-normalized) toxicity concentration
# ---------------------------------------------------------------------------
def _adverse_net_concentration(pos):
    """(gini, top-1% share, top-10% share, total, n) for a positive vector.

    WHAT IS SELECTED HERE IS A POPULATION AND NOT A TAIL, and that is why the name
    no longer says decile or top. The rule is absolute: a counterparty is in when its
    per-dollar markout is above zero, measured over the whole window rather than the
    ranking half, at a floor of ten fills rather than fifty. It therefore admits
    roughly half of all counterparties, whereas the study's declared selection admits
    a tenth by construction. A Gini computed over this population and a cost share
    computed over that tail are statistics of two different objects, and reading one
    as the other is the error this rename is meant to make impossible.

    The keys this file writes still spell the old word -- net_toxic_gini,
    n_net_toxic_wallets, toxic_top_1pct_share, frac_wallets_toxic. Changing a key
    changes what the artifact says and is owed a run, so the code names are corrected
    here and the key names are left as declared debt.

    pos = that population's per-dollar markouts, all positive. All four shares share
    one sort so the helper is cheap enough to call inside the bootstrap loop.
    """
    pos = np.asarray(pos, dtype=np.float64)
    if pos.size == 0:
        return (float("nan"), float("nan"), float("nan"), 0.0, 0)
    total = float(pos.sum())
    sorted_desc = np.sort(pos)[::-1]
    return (
        gini(pos),
        top_pct_share(sorted_desc, total, 0.01),
        top_pct_share(sorted_desc, total, 0.10),
        total,
        int(pos.size),
    )


def _bootstrap_adverse_net_ci(pos, draws, seed):
    """Wallet-level bootstrap CI for the net-toxic Gini / top-shares.

    NOT ROUTED THROUGH stats.bootstrap_ci, and three separate differences say why. The
    module draws one resample index per call, so three calls would score the Gini and
    the two top-shares on three DIFFERENT resamples where this loop scores all three on
    the same one, and the three intervals here are meant to describe one act of
    resampling. Its stream comes from settings.rng and a named cell where this file
    draws from its own declared bootstrap seed, so adopting it would redraw every
    endpoint. And it returns two endpoints where this block reports three, the median
    included. Each of those is a change with a number attached, so none of them belongs
    in a consolidation; the interval method is the same percentile rule either way.

    Resamples the net-toxic wallets (pos) with replacement `draws` times and
    recomputes the Gini and the top-1% / top-10% shares each draw, returning
    2.5 / 50 / 97.5 percentiles. This is a descriptive CI: it captures sampling
    noise in WHICH wallets land in the net-toxic subset but NOT the in-sample
    selection bias from defining membership by pdm > 0 on the same markout (that
    bias is noted separately and pushes the point estimate up, not the width).
    Returns None if there are too few wallets or draws <= 0.
    """
    pos = np.asarray(pos, dtype=np.float64)
    if draws <= 0 or pos.size < 2:
        return None
    rng = np.random.default_rng(seed)
    n = pos.size
    gv = np.empty(draws, dtype=np.float64)
    t1 = np.empty(draws, dtype=np.float64)
    t10 = np.empty(draws, dtype=np.float64)
    for b in range(draws):
        samp = pos[rng.integers(0, n, size=n)]
        g, s1, s10, _, _ = _adverse_net_concentration(samp)
        gv[b], t1[b], t10[b] = g, s1, s10

    def pctls(a):
        a = a[np.isfinite(a)]
        if a.size == 0:
            return {"lo": float("nan"), "med": float("nan"), "hi": float("nan")}
        return {
            "lo": float(np.percentile(a, 2.5)),
            "med": float(np.percentile(a, 50.0)),
            "hi": float(np.percentile(a, 97.5)),
        }

    return {
        "method": "wallet resample with replacement",
        "draws": int(draws),
        "seed": int(seed),
        "net_toxic_gini": pctls(gv),
        "toxic_top_1pct_share": pctls(t1),
        "toxic_top_10pct_share": pctls(t10),
        "note": (
            "descriptive CI over wallet sampling only; does NOT correct the "
            "in-sample pdm>0 selection bias, which inflates the point estimate"),
    }


def per_dollar_block(per_dollar_mo, wallet_fills,
                     min_fills_cuts=MIN_FILLS_CUTS,
                     headline_min_fills=HEADLINE_MIN_FILLS,
                     bootstrap_draws=BOOTSTRAP_DRAWS,
                     bootstrap_seed=BOOTSTRAP_SEED):
    """Concentration / dispersion of per-dollar markout across wallets.

    THIS IS THE HEADLINE measure. per_dollar_mo[i] is wallet i's cost per unit
    notional in bps (signed; positive = the wallet's flow was toxic to the
    maker on average). wallet_fills[i] is the number of trades wallet i appears
    in (used to filter out tiny single-fill wallets whose 10s markout is one
    noisy draw that self-selects on its own sign).

    Because per-dollar markout is signed and roughly half the wallets are
    net-toxic while the average wallet is near-neutral/negative, a Gini on the
    full signed vector is not meaningful (see gini_signed, kept only as a
    labelled diagnostic). The HEADLINE concentration is therefore a
    sign-appropriate statistic on the NET-TOXIC subset (wallets with positive
    per-dollar markout):

      * net_toxic_gini      -- standard Gini on the positive subset, i.e. how
                               unevenly per-dollar toxicity is spread AMONG the
                               wallets that are actually toxic.
      * toxic_top_1pct_share / toxic_top_10pct_share -- share of total positive
                               per-dollar toxicity held by the top 1% / 10% of
                               toxic wallets.

    TWO selection problems are handled explicitly here:

      1. MIN-FILLS. With no fills filter, single-fill wallets carry one noisy
         10s markout each, so the net-toxic subset is dominated by tiny wallets
         and the concentration reads HIGH. min_fills_sensitivity recomputes the
         net-toxic concentration at >= 1 / >= 10 / >= 25 fills; the >= 1 cut is
         relabelled as an INFLATED LOWER BOUND and the headline is taken at
         headline_min_fills (default 10).
      2. IN-SAMPLE pdm>0 SELECTION. The net-toxic subset is selected by the same
         per-dollar markout that then measures its dispersion, so a wallet with a
         marginally positive (noisy) markout enters the subset and inflates the
         tail. This is an upward bias on net_toxic_gini and the top-shares; it is
         flagged in selection_bias_note and the bootstrap CI does NOT remove it.

    The honest reading: among net-toxic wallets with a non-trivial fill count,
    per-dollar toxicity is MODERATELY concentrated; the AVERAGE wallet is
    near-neutral/negative (mean_bps below) and roughly half are not toxic at all,
    so toxicity is not driven by a tiny handful of wallets.
    """
    pdm = np.asarray(per_dollar_mo, dtype=np.float64)
    fills = np.asarray(wallet_fills, dtype=np.int64)
    finite = np.isfinite(pdm)
    pdm = pdm[finite]
    fills = fills[finite]
    q = describe_quantiles(pdm)

    # ---- min-fills sensitivity on the net-toxic concentration ----
    sensitivity = {}
    for cut in min_fills_cuts:
        keep = fills >= cut
        pdm_c = pdm[keep]
        pos_c = pdm_c[pdm_c > 0]
        g, t1, t10, tot, npos = _adverse_net_concentration(pos_c)
        entry = {
            "min_fills": int(cut),
            "n_wallets_at_cut": int(pdm_c.size),
            "n_net_toxic_wallets": npos,
            "net_toxic_gini": g,
            "toxic_top_1pct_share": t1,
            "toxic_top_10pct_share": t10,
            "net_toxic_total_bps": tot,
        }
        if cut <= 1:
            entry["label"] = ("INFLATED LOWER BOUND -- includes single-fill "
                              "wallets whose one 10s markout self-selects on "
                              "its own sign")
        sensitivity[f"min_fills_{cut}"] = entry

    # ---- headline: net-toxic concentration at headline_min_fills ----
    keep_h = fills >= headline_min_fills
    pdm_h = pdm[keep_h]
    pos_h = pdm_h[pdm_h > 0]
    g_h, t1_h, t10_h, tot_h, npos_h = _adverse_net_concentration(pos_h)
    boot = _bootstrap_adverse_net_ci(pos_h, bootstrap_draws, bootstrap_seed)

    out = {
        "measure": "per-wallet mean markout (cost per unit notional, bps)",
        "n_wallets": int(pdm.size),
        "mean_bps": q["mean"],
        "mean_sign": ("negative" if (np.isfinite(q["mean"]) and q["mean"] < 0)
                      else "positive" if np.isfinite(q["mean"]) else "n/a"),
        "frac_wallets_toxic": q["frac_positive"],   # share with positive markout
        # ---- HEADLINE concentration: net-toxic subset at >= headline fills ----
        "headline_min_fills": int(headline_min_fills),
        "n_net_toxic_wallets": npos_h,
        "net_toxic_gini": g_h,
        "toxic_top_1pct_share": t1_h,
        "toxic_top_10pct_share": t10_h,
        "net_toxic_total_bps": tot_h,
        # ---- min-fills sensitivity (>= 1 is the inflated lower bound) ----
        "min_fills_sensitivity": sensitivity,
        # ---- light wallet-level bootstrap CI at the headline cut ----
        "bootstrap_ci": (boot if boot is not None
                         else {"inference": "descriptive, no CI"}),
        "inference": ("bootstrap CI over wallets at the headline cut"
                      if boot is not None else "descriptive, no CI"),
        "concentration_note": (
            "net_toxic_gini and toxic_top_*_share describe concentration AMONG "
            "net-toxic wallets only, at >= {0} fills; mean_bps (signed, over ALL "
            "wallets) is near-neutral/negative, so the average counterparty is "
            "not toxic".format(headline_min_fills)),
        "min_fills_note": (
            "without a fills filter the net-toxic subset is dominated by tiny "
            "single-fill wallets carrying one noisy 10s markout; the >= 1 cut in "
            "min_fills_sensitivity is therefore an INFLATED LOWER BOUND and the "
            "headline uses >= {0} fills".format(headline_min_fills)),
        "selection_bias_note": (
            "the net-toxic subset is selected by pdm > 0 using the SAME "
            "per-dollar markout that then measures its dispersion, so membership "
            "and dispersion share an in-sample selection that biases "
            "net_toxic_gini and the top-shares UPWARD; the bootstrap CI captures "
            "wallet-sampling noise only and does not remove this bias"),
        # ---- diagnostic, NOT a headline; collapses toward 0 on signed data ----
        "diagnostic_signed_gini_do_not_cite": gini_signed(pdm),
        "distribution_bps": q,
    }
    return out


# ---------------------------------------------------------------------------
# (2) DOLLAR-COST concentration + held-constant-toxicity counterfactual
# ---------------------------------------------------------------------------
def dollar_cost_block(wallet_cost, wallet_notional, mean_markout_bps):
    """Raw dollar-cost concentration shown NEXT TO its size-only counterfactual.

    wallet_cost      : per-wallet summed maker loss (signed, quote units).
    wallet_notional  : per-wallet summed notional (quote units, >= 0).
    mean_markout_bps : the GLOBAL notional-weighted mean markout (bps). Holding
                       every fill's toxicity at this constant turns each wallet's
                       cost into (mean_markout/1e4) * wallet_notional, so the
                       counterfactual cost Gini equals the notional Gini. The
                       gap between dollar_cost_gini and constant_toxicity_gini is
                       the part of the dollar Gini that is REAL toxicity
                       dispersion rather than trade-size inequality.

    Top-k / top-1% shares are reported on POSITIVE dollar cost (loss-makers), so
    they read as 'fraction of maker dollar loss', and are flagged in labels as a
    COST measure, not a toxicity measure.
    """
    wc = np.asarray(wallet_cost, dtype=np.float64)
    wn = np.asarray(wallet_notional, dtype=np.float64)

    # --- raw dollar cost (positive = loss-makers) ---
    pos = wc[wc > 0]
    pos_total = float(pos.sum())
    sorted_desc = np.sort(pos)[::-1]
    lx, ly = lorenz_curve(pos)
    dollar_cost_gini = gini(pos)

    # --- held-constant-toxicity counterfactual ---
    # Replace every fill's markout with the global mean: each wallet's cost
    # becomes (mean_markout/1e4) * wallet_notional, i.e. proportional to its
    # notional. Scaling every value by the same constant leaves the Gini
    # unchanged, so the counterfactual dollar-cost Gini is identically the
    # notional Gini -- computing it that way is sign-robust (it does not break
    # when the global mean markout is negative, which it is on this data). We
    # still report constant_toxicity_gini as a named field so the reader sees
    # "cost Gini under constant toxicity" sitting next to the raw cost Gini.
    notional_gini = gini(wn[wn > 0])
    constant_toxicity_gini = notional_gini

    return {
        "label": "DOLLAR COST concentration (NOT toxicity) -- driven by trade size",
        "n_wallets": int(wc.size),
        "n_positive_cost_wallets": int(pos.size),
        "total_cost_quote": float(wc.sum()),
        "positive_cost_total_quote": pos_total,
        "dollar_cost_gini": dollar_cost_gini,
        "constant_toxicity_gini": constant_toxicity_gini,
        "constant_toxicity_markout_bps": float(mean_markout_bps),
        "notional_gini": notional_gini,
        "size_artifact_note": (
            "constant_toxicity_gini is the dollar-cost Gini with per-fill "
            "toxicity held at the global mean; its closeness to dollar_cost_gini "
            "shows how much of the dollar Gini is pure trade-size inequality"
        ),
        "hhi_cost": hhi(pos),
        "cost_top_1pct_share": top_pct_share(sorted_desc, pos_total, 0.01),
        "cost_top10_share": top_k_share(sorted_desc, pos_total, 10),
        "cost_top50_share": top_k_share(sorted_desc, pos_total, 50),
        "cost_top100_share": top_k_share(sorted_desc, pos_total, 100),
        "lorenz_cost_x": lx,
        "lorenz_cost_y": ly,
    }


# ---------------------------------------------------------------------------
# (3) drop-top-k robustness + notional-controlled view
# ---------------------------------------------------------------------------
def drop_topk_block(wallet_cost, wallet_notional):
    """Robustness of dollar-cost concentration to removing the top earners, and
    a notional-controlled view of where cost sits relative to volume.

    Replaces the old single-whale check. We report the positive-cost top-10
    share after dropping the top 10 / 50 / 100 highest-cost wallets, plus the
    share of TOTAL notional carried by the same top-cost wallets -- if the
    top-cost wallets also carry a comparable share of notional, the cost
    concentration is just size, not toxicity.
    """
    wc = np.asarray(wallet_cost, dtype=np.float64)
    wn = np.asarray(wallet_notional, dtype=np.float64)

    pos_mask = wc > 0
    pos_cost = wc[pos_mask]
    pos_notl = wn[pos_mask]
    if pos_cost.size == 0:
        empty = {"note": "no positive-cost wallets; drop-top-k check not applicable",
                 "notional_controlled": {}}
        empty.update({DROP_KEYS[k]: {} for k in TOPK_COUNTS})
        return empty

    order = np.argsort(pos_cost)[::-1]   # high-to-low by cost
    cost_desc = pos_cost[order]
    notl_desc = pos_notl[order]
    full_cost_total = float(cost_desc.sum())
    full_notl_total = float(notl_desc.sum())

    def drop_block(k):
        kk = int(min(k, cost_desc.size))
        kept = cost_desc[kk:]
        kept_total = float(kept.sum())
        return {
            "k_dropped": kk,
            "cost_share_of_dropped": (
                float(cost_desc[:kk].sum() / full_cost_total)
                if full_cost_total > 0 else float("nan")),
            "gini_after_drop": gini(kept),
            "hhi_after_drop": hhi(kept),
            "cost_total_after_drop": kept_total,
        }

    def notional_controlled(k):
        # top-k by cost: what share of cost vs what share of notional do they
        # carry? Near-equal shares => cost concentration is just size.
        kk = int(min(k, cost_desc.size))
        cost_share = (float(cost_desc[:kk].sum() / full_cost_total)
                      if full_cost_total > 0 else float("nan"))
        notl_share = (float(notl_desc[:kk].sum() / full_notl_total)
                      if full_notl_total > 0 else float("nan"))
        ratio = (cost_share / notl_share
                 if (np.isfinite(cost_share) and np.isfinite(notl_share)
                     and notl_share > 0) else float("nan"))
        return {
            "k": kk,
            "cost_share": cost_share,
            "notional_share": notl_share,
            "cost_to_notional_ratio": ratio,   # ~1 => cost tracks size, not toxicity
        }

    out = {
        "note": (
            "drop-top-k replaces the old single-whale check; "
            "notional_controlled compares each top-cost group's cost share to "
            "its notional share (ratio ~1 means cost concentration is trade "
            "size, not toxicity). Every top-k key names the criterion the k "
            "wallets are largest BY, which is gross dollar cost here"),
    }
    out.update({DROP_KEYS[k]: drop_block(k) for k in TOPK_COUNTS})
    out["notional_controlled"] = {
        CONTROLLED_KEYS[k]: notional_controlled(k) for k in TOPK_COUNTS
    }
    return out


# ---------------------------------------------------------------------------
# Per-coin / pooled driver
# ---------------------------------------------------------------------------
def analyse_slice(taker_id, cost_per_trade, notional, mo_weighted, mo_score):
    """Build per-wallet measures for one slice and return the full result dict.

    The slice's global notional-weighted mean markout (bps) is computed here and
    fed to the held-constant-toxicity counterfactual so each coin uses its own
    mean rather than the pooled one.
    """
    wallet_ids, wallet_cost, wallet_notl, wallet_mow, wallet_fills = (
        wallet_aggregate(taker_id, cost_per_trade, notional, mo_weighted))
    pdm = per_dollar_markout(wallet_mow, wallet_notl)

    notl_sum = float(notional.sum())
    mean_markout_bps = (float(mo_weighted.sum() / notl_sum)
                        if notl_sum > 0 else float("nan"))

    block = {
        "n_trades": int(taker_id.size),
        "n_wallets": int(wallet_ids.size),
        "global_mean_markout_bps_notional_weighted": mean_markout_bps,
        # (1) headline: per-dollar toxicity
        "per_dollar_toxicity": per_dollar_block(pdm, wallet_fills),
        # (2) dollar cost + size-only counterfactual
        "dollar_cost": dollar_cost_block(wallet_cost, wallet_notl, mean_markout_bps),
        # (3) drop-top-k + notional-controlled
        "robustness": drop_topk_block(wallet_cost, wallet_notl),
    }
    return block


def main():
    t0 = artifact.start_clock()
    # panel_io raises when the file is absent and names the producer to run, so the
    # "is it there" test and the "what do I do about it" message live in one place
    # instead of once per script.
    # panel_io names the producer to run when the file is absent, so that message
    # is written once for the whole tree; the load itself stays here because
    # build.py derives this script's input edge from the argument of np.load.
    P.require_present("print", NPZ_PATH)
    data = np.load(NPZ_PATH)
    taker_id = data["taker_id"].astype(np.int64)
    coin = data["coin"].astype(np.int8)
    # Through panel_io, which takes the window from settings.py and the lens from the
    # FILE, so this read cannot pick a column of the other reference price by accident.
    mo_score = P.score(data, "print")            # signed taker markout, bps
    notional = data["notional"].astype(np.float64)
    # Read only to state the window in the artifact's scope; it enters no computation.
    # It is filtered with everything else so the window describes the rows that
    # actually reached the sums rather than the rows the input happened to hold.
    day = data["day"].astype(np.int64)

    # Maker's signed loss per trade in quote units. mo10 is the taker's markout
    # in basis points (positive = taker profited), so dividing by 1e4 and
    # scaling by notional gives the maker's realised loss to that counterparty.
    cost_per_trade = (mo_score / 1e4) * notional

    # notional-weighted markout helper: summed per wallet then divided by summed
    # notional gives the wallet's per-dollar markout (bps).
    mo_weighted = mo_score * notional

    # Drop trades with no usable 10s markout (or bad notional) so they do not
    # enter any sum.
    valid = (np.isfinite(cost_per_trade) & np.isfinite(mo_score)
             & np.isfinite(notional) & (notional >= 0))
    day = day[valid]
    taker_id = taker_id[valid]
    coin = coin[valid]
    mo_score = mo_score[valid]
    notional = notional[valid]
    cost_per_trade = cost_per_trade[valid]
    mo_weighted = mo_weighted[valid]

    results = {
        "_meta": {
            "object": "M11 toxicity vs cost concentration (reframed)",
            "headline": "per_dollar_toxicity (notional-normalized markout)",
            "horizon_s": H.HEADLINE_HORIZON_S,
            "markout_column": H.headline_print_col(),
            "cost_definition": (f"sum({H.headline_print_col()}/1e4 * notional) per wallet "
                                "= maker loss (reported as DOLLAR COST, not toxicity)"),
            "framing_note": (
                "dollar cost is concentrated because trade size is concentrated; "
                "per-unit toxicity is only mildly concentrated and on average "
                "does not favour the taker -- see per_dollar_toxicity and the "
                "constant_toxicity_gini counterfactual"),
            "headline_min_fills": HEADLINE_MIN_FILLS,
            "min_fills_cuts": list(MIN_FILLS_CUTS),
            "net_toxic_concentration_note": (
                "net-toxic concentration is reported at a HEADLINE min-fills cut "
                "(>= {0} fills); the unfiltered >= 1 cut is an inflated lower "
                "bound dominated by single-fill wallets. See per_dollar_toxicity."
                "min_fills_sensitivity in each slice.".format(HEADLINE_MIN_FILLS)),
            "btc_vs_eth_split_caveat": (
                "the BTC-vs-ETH net-toxic-Gini gap is NOT a reliable finding: it "
                "is ~0.03 unfiltered and collapses to ~0.02 once tiny wallets are "
                "removed, and it has no standard error. Do not read a BTC/ETH "
                "toxicity-concentration difference from these numbers."),
            "inference_note": (
                "headline net-toxic concentration carries a wallet-level "
                "bootstrap CI (per_dollar_toxicity.bootstrap_ci); all other "
                "figures are descriptive. The pdm>0 net-toxic selection is "
                "in-sample and biases the concentration upward (per_dollar_"
                "toxicity.selection_bias_note)."),
            "n_trades_valid": int(taker_id.size),
            "lorenz_points": LORENZ_POINTS,
        }
    }

    # What the numbers cover. The unit of analysis is the WALLET, and the floors
    # differ between blocks, so the population names both: the per-dollar
    # distribution carries no floor and the headline net-toxic cut carries one.
    days = np.unique(day)
    scope = {
        "population": (f"{taker_id.size:,} rows of the trade-print panel with a "
                       "finite markout and a finite non-negative notional, summed "
                       "per wallet; the per-dollar distribution takes every wallet "
                       "with no fill floor, and the headline net-toxic cut floors "
                       f"at {HEADLINE_MIN_FILLS} fills"),
        "window": (f"{days.size} days present in the input, day-of-month "
                   f"{days.min()}-{days.max()}; the calendar dates of the window "
                   "are declared by its producer, build_quickwin_markouts.py"),
        "coins": [COIN_NAME[c] for c in sorted(COIN_NAME)],
    }
    results["_meta"]["rank_floor_note"] = (
        f"the headline net-toxic concentration floors wallets at "
        f"{HEADLINE_MIN_FILLS} fills, and the >= 1 and >= "
        f"{max(MIN_FILLS_CUTS)} cuts sit beside it in min_fills_sensitivity; the "
        f"per-dollar distribution over ALL wallets carries no floor at all")

    # ---- per coin ----
    for code, name in COIN_NAME.items():
        sel = coin == code
        results[name] = analyse_slice(
            taker_id[sel], cost_per_trade[sel], notional[sel],
            mo_weighted[sel], mo_score[sel])

    # ---- pooled (all coins) ----
    results["pooled"] = analyse_slice(
        taker_id, cost_per_trade, notional, mo_weighted, mo_score)

    # The output name and directory still come from the module-level OUT_PATH, so a
    # caller that redirects that constant redirects the whole write, as before. Two
    # stamped settings genuinely differ from the declaration and are passed
    # explicitly: the bootstrap runs its own number of draws rather than the declared
    # one, which is twenty draws in each tail of a 95% interval instead of fifty, and
    # the headline net-toxic cut floors wallets lower than the declared rank floor.
    # The bootstrap seed agrees with the declared master seed and is passed too,
    # because a migrating declaration is only asserted when the caller states what
    # its run used. No permutation test runs here, so that budget stays in
    # declared_not_confirmed where it belongs.
    artifact.write(os.path.basename(OUT_PATH), results,
                   script=__file__, inputs=[NPZ_PATH], scope=scope,
                   settings={"h": H.HEADLINE_HORIZON_S, "lens": "print",
                             "master_seed": BOOTSTRAP_SEED,
                             "n_boot": BOOTSTRAP_DRAWS,
                             "rank_floor_fills": HEADLINE_MIN_FILLS},
                   started=t0, out_dir=os.path.dirname(OUT_PATH))

    print_summary(results)
    print(f"\n[m11] wrote {os.path.basename(OUT_PATH)}")


# ---------------------------------------------------------------------------
# Printed summary
# ---------------------------------------------------------------------------
def _fmt(x, nd=4):
    return f"{x:.{nd}f}" if isinstance(x, float) and np.isfinite(x) else "n/a"


def print_summary(results):
    print("=" * 74)
    print("M11 — TOXICITY vs COST CONCENTRATION (reframed)")
    print("=" * 74)
    print(f"valid trades : {results['_meta']['n_trades_valid']:,}")
    print("HEADLINE = per-dollar toxicity (cost per unit notional, bps).")
    print("Dollar-cost concentration is a TRADE-SIZE artefact, shown only with")
    print("its held-constant-toxicity counterfactual.\n")

    # ---- (1) headline: per-dollar toxicity ----
    hmf = results["_meta"].get("headline_min_fills", HEADLINE_MIN_FILLS)
    print("(1) PER-DOLLAR TOXICITY  [the measure that actually matters]")
    print(f"    HEADLINE net-toxic concentration is at >= {hmf} fills. Gini is on")
    print("    the NET-TOXIC subset only (positive per-dollar markout). mean_bps")
    print("    is over ALL wallets and is near-neutral/negative.")
    h1 = (f"{'slice':<8} {'wallets':>9} {'mean_bps':>10} {'sign':>9} "
          f"{'%toxic':>8} {'tox_gini':>9} {'tox_t1%':>8} {'tox_t10%':>9}")
    print(h1)
    print("-" * len(h1))
    for key in ("BTC", "ETH", "pooled"):
        if key not in results:
            continue
        pd = results[key]["per_dollar_toxicity"]
        print(f"{key:<8} {pd['n_wallets']:>9,} {_fmt(pd['mean_bps'], 3):>10} "
              f"{pd['mean_sign']:>9} {_fmt(pd['frac_wallets_toxic'], 3):>8} "
              f"{_fmt(pd['net_toxic_gini']):>9} "
              f"{_fmt(pd['toxic_top_1pct_share'], 3):>8} "
              f"{_fmt(pd['toxic_top_10pct_share'], 3):>9}")
    print("    (among net-toxic wallets toxicity is MODERATELY concentrated;")
    print("     the average wallet is not toxic -- both statements hold)")

    # ---- (1b) min-fills sensitivity on the net-toxic concentration ----
    print("\n(1b) MIN-FILLS SENSITIVITY  [net-toxic Gini / top-shares by fills cut]")
    print("     >= 1 is the INFLATED LOWER BOUND (single-fill wallets); headline")
    print(f"     is >= {hmf}.")
    hs = (f"{'slice':<8} {'minfill':>8} {'n_net_tox':>10} {'tox_gini':>9} "
          f"{'tox_t1%':>8} {'tox_t10%':>9}")
    print(hs)
    print("-" * len(hs))
    for key in ("BTC", "ETH", "pooled"):
        if key not in results:
            continue
        sens = results[key]["per_dollar_toxicity"].get("min_fills_sensitivity", {})
        for cut in MIN_FILLS_CUTS:
            e = sens.get(f"min_fills_{cut}")
            if not e:
                continue
            print(f"{key:<8} {('>=' + str(cut)):>8} {e['n_net_toxic_wallets']:>10,} "
                  f"{_fmt(e['net_toxic_gini']):>9} "
                  f"{_fmt(e['toxic_top_1pct_share'], 3):>8} "
                  f"{_fmt(e['toxic_top_10pct_share'], 3):>9}")
    # bootstrap CI at the headline cut (pooled)
    pooled_pd = results.get("pooled", {}).get("per_dollar_toxicity", {})
    boot = pooled_pd.get("bootstrap_ci", {})
    if isinstance(boot, dict) and "net_toxic_gini" in boot:
        g = boot["net_toxic_gini"]
        print(f"     pooled bootstrap 95% CI (>= {hmf}, {boot.get('draws')} draws): "
              f"gini [{_fmt(g['lo'])}, {_fmt(g['hi'])}]")
    else:
        print("     bootstrap: " + str(boot.get("inference", "n/a")))
    print("     BTC-vs-ETH split: NOT reliable (gap ~0.02 under filtering, no SE)")

    # ---- (2) dollar cost + counterfactual ----
    print("\n(2) DOLLAR-COST concentration  [size artefact -- NOT toxicity]")
    h2 = (f"{'slice':<8} {'cost_gini':>10} {'const_tox':>10} {'notional':>10} "
          f"{'cost_t1%':>9} {'cost_t10':>9}")
    print(h2)
    print("-" * len(h2))
    for key in ("BTC", "ETH", "pooled"):
        if key not in results:
            continue
        dc = results[key]["dollar_cost"]
        print(f"{key:<8} {_fmt(dc['dollar_cost_gini']):>10} "
              f"{_fmt(dc['constant_toxicity_gini']):>10} "
              f"{_fmt(dc['notional_gini']):>10} "
              f"{_fmt(dc['cost_top_1pct_share']):>9} "
              f"{_fmt(dc['cost_top10_share']):>9}")
    print("    (const_tox ~= notional => the dollar Gini is mostly trade size)")

    # ---- (3) notional-controlled robustness ----
    print("\n(3) NOTIONAL-CONTROLLED  [cost share vs notional share of top-cost wallets]")
    h3 = (f"{'slice':<8} {'grp':>6} {'cost_sh':>9} {'notl_sh':>9} {'ratio':>8}")
    print(h3)
    print("-" * len(h3))
    for key in ("BTC", "ETH", "pooled"):
        if key not in results:
            continue
        nc = results[key]["robustness"].get("notional_controlled", {})
        for k in TOPK_COUNTS:
            grp = CONTROLLED_KEYS[k]
            if grp not in nc:
                continue
            r = nc[grp]
            print(f"{key:<8} {('top' + str(k)):>6} {_fmt(r['cost_share'], 3):>9} "
                  f"{_fmt(r['notional_share'], 3):>9} "
                  f"{_fmt(r['cost_to_notional_ratio'], 2):>8}")
    print("    (ratio ~1 => top-cost wallets are just the biggest traders)")
    print("=" * 74)


if __name__ == "__main__":
    main()
