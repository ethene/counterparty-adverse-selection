#!/usr/bin/env python3
"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-08-03
References: Hyperliquid Level-4 order-book data, Zenodo 18184441 (Albers et al. 2026).

Counterparty-side validation of the toxicity score using the taker's OWN realized PnL.

Toxicity is measured from the MAKER's side (markout = the maker's loss after a fill). The
on-chain data also carries each taker's realized `closed_pnl`, so we can ask the CEX-impossible
question: are the wallets we flag toxic (maker loses) the same wallets that actually PROFIT
(taker wins)? Two independent measurements of the same informed-trading edge.

Tests:
  (1) Rank agreement: Spearman( per-wallet markout toxicity at the headline window ,
      per-wallet realized PnL/$ ), per coin + pooled, placebo + bootstrap + whale-robust.
  (2) OOS validation: flag toxic by EARLY-half markout top-decile, then compare LATE-half
      realized PnL of the flagged vs the rest. Clean out-of-sample, both sides. The halves
      are cut by settings.split_early_late over the days the input carries, which on this
      December window resolves to days 4-8 and 9-13.

The score horizon is whichever one settings.py names the headline (the horizon-selection
step is what set it there), read as headline_mid_col() and never typed here. closed_pnl is profit-positive and
~0 on opens (byte-verified in the data log). Taker-side throughout (toxicity is a taker property):
we sum closed_pnl over a wallet's AGGRESSOR fills, matching the fills the markout is measured on.

Inputs (local, de-id): quickwin_markouts_mid.npz.
Outputs: ws3_taker_pnl_results.json.
The figure is drawn by ws3_plot.py, which reads that results file and computes nothing.
This file drew it until 2026-08-03, and the drawing sat behind a catch that returned
zero, so a run that could not import matplotlib wrote fresh numbers, printed one line
and left a two-day-old figure beside them with the median late realized profit of the
flagged wallets drawn at the WRONG SIGN.
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
import stats

HERE = os.path.dirname(os.path.abspath(__file__))
# How many equal-count bins the left panel of the figure cuts the toxicity axis into.
# Named because it was a bare 10 and an 11 typed two lines apart inside the plotting
# branch, where the two had to agree and nothing said so.
N_TOXICITY_BINS = 10
# The artifacts this file writes, named once so a verification pass can re-point them
# and nothing else, which is what lets the module be re-run without being copied. The
# INPUT is located by panel_io instead, the one place that knows where the panels live.
IN_NPZ = os.path.join(P.data_root(), "quickwin_markouts_mid.npz")
OUT_JSON = os.path.join(HERE, "ws3_taker_pnl_results.json")
# The early and late halves are DERIVED from the days the input actually carries, by
# settings.split_early_late, and are never day-of-month sets typed here. The two forms
# agree on this file's input and only on it: quickwin_markouts_mid.npz runs 4 to 13, so
# the rule returns 4-8 and 9-13, the sets this file used to declare. On a window that
# begins on the 6th the typed sets would cut a three-day half against a seven-day one.
# Minimum fills per wallet, READ from settings.py and never typed. It is recorded under
# the headline role because that is what the prose points at; the same number also gates
# each half of the out-of-sample split below, and the declaration says so rather than
# inventing a second role for one value. The spelling `K` was in no alias list of the
# settings gate until 2026-07-31, so this site had never been counted anywhere.
#
# THE FLOOR ROSE FROM 10 TO THE DECLARED 50 ON 2026-07-31, and the argument lands on this
# file more directly than on any other consumer. What this file reports IS a rank
# agreement between two per-wallet scores, and the disattenuation multiplier at ten fills
# is 2.79 -- the quantity a noise floor stretches is the quantity here. The old floor
# bought wallet COUNT for a correlation whose answer is about zero, which is the direction
# that works against the finding rather than for it, and this run says whether the answer
# survives on wallets whose scores are mostly signal. The population moves with it: the
# pooled rank cell holds 18,161 wallet-coin units at ten fills and 4,335 at fifty, and the
# out-of-sample split holds 5,545 eligible units against 1,213.
K = H.wallet_fill_floor("ws3_taker_pnl", "headline")
# No seed literal lives here any more. Every random stream below is derived from
# settings.MASTER_SEED and the name of the cell it belongs to, through settings.rng. This
# file used to declare 424242 for the permutation and 20260619 for the bootstrap, neither
# of them the declared seed, so a p-value here could not be compared with one from any
# other script: the difference would have been a difference of seeds as much as of
# statistics.
# Label-permutation draws, READ from settings.py and never typed. The budget fixes the
# p-value floor at 1/(N+1); at the 200 draws this file used to declare the floor was
# 0.00498, which one of the three rank-agreement p-values below sat exactly on.
# settings.N_PERM is computed from the level, the family size and the margin, so the
# floor follows them instead of being remembered here.
N_PERM = H.N_PERM
# Bootstrap resamples, READ from settings.py under the name of this consumer, which since
# 2026-07-31 is the declared N_BOOT. The published intervals in this file were drawn at
# 500.
#
# What the number buys is not the budget but N * 0.025, the draws landing in each tail of
# a 95 percent interval, because that is what fixes how far an endpoint moves between
# seeds. 500 put twelve and a half draws in each tail against the fifty the declaration
# asks for. Both places the budget is spent here are percentile endpoints -- the band on
# the rank correlation and the band on the out-of-sample median gap -- so what the
# adoption moves is four endpoints per cell and no point estimate.
N_BOOT = H.boot_draws("ws3_taker_pnl")
TOXIC_Q = 0.90   # top decile


def _rankdata(a):
    order = np.argsort(a, kind="stable")
    ranks = np.empty(a.size); ranks[order] = np.arange(1, a.size + 1)
    s = a[order]; i = 0
    while i < s.size:
        j = i
        while j + 1 < s.size and s[j + 1] == s[i]:
            j += 1
        if j > i:
            ranks[order[i:j + 1]] = (i + 1 + j + 1) / 2.0
        i = j + 1
    return ranks


def spearman(x, y):
    if x.size < 3:
        return np.nan
    rx = _rankdata(x) - _rankdata(x).mean()
    ry = _rankdata(y) - _rankdata(y).mean()
    d = np.sqrt((rx * rx).sum() * (ry * ry).sum())
    return float((rx * ry).sum() / d) if d > 0 else np.nan


def agg(unit, n_units, mask, mo, cpnl, notl):
    """Per-unit aggregates over `mask`. Returns dict of arrays length n_units."""
    fin_mo = mask & np.isfinite(mo)
    cnt_mo = np.bincount(unit[fin_mo], minlength=n_units)
    sum_mo = np.bincount(unit[fin_mo], weights=mo[fin_mo], minlength=n_units)
    cnt = np.bincount(unit[mask], minlength=n_units)
    sum_cp = np.bincount(unit[mask], weights=cpnl[mask], minlength=n_units)
    sum_nt = np.bincount(unit[mask], weights=notl[mask], minlength=n_units)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean_mo = np.where(cnt_mo > 0, sum_mo / np.maximum(cnt_mo, 1), np.nan)
        pnl_per_dollar_bps = np.where(sum_nt > 0, sum_cp / np.maximum(sum_nt, 1) * 1e4, np.nan)
    return {"cnt_mo": cnt_mo, "mean_mo": mean_mo, "cnt": cnt,
            "sum_cp": sum_cp, "sum_nt": sum_nt, "pnl_pd_bps": pnl_per_dollar_bps}


def rank_agreement(mean_mo, pnl_pd, cnt_mo, K, scope):
    """Rank agreement for one scope, with its placebo and bootstrap.

    `scope` is required rather than defaulted because it is what the two random streams
    are derived from: the three scopes must not re-draw one shared permutation sequence,
    which is what a literal seed inside this function produced.
    """
    keep = (cnt_mo >= K) & np.isfinite(mean_mo) & np.isfinite(pnl_pd)
    x = mean_mo[keep]; y = pnl_pd[keep]
    if x.size < 10:
        return None
    rho = spearman(x, y)
    rng = H.rng("ws3", "placebo", scope, K)
    perm = np.array([spearman(x, rng.permutation(y)) for _ in range(N_PERM)])
    # THE COUNTING IS stats.permutation_p AND THE ARITHMETIC IS UNCHANGED: TWO-SIDED on
    # |rho|, because the question is whether the two rankings agree OR disagree more
    # than chance; an ABSOLUTE slack of zero, which is what this line applied, rather
    # than the module's default slack scaled to the comparison; and a denominator equal
    # to the budget. The last one is an equality, not a coincidence: permuting y
    # reorders the same values, so the rank spread of every draw equals that of the
    # observed pairing, and either every draw is finite or rho is not finite either.
    # That second case -- a cell with no statistic at all, where this line reported the
    # budget's floor and the module reports no test -- is carried over unchanged.
    procedure = stats.permutation_p(rho, perm, side="two_sided", abs_tol=0.0,
                                    n_requested=N_PERM,
                                    cell=("ws3", "placebo", scope, K))
    p = float(procedure["p"] if procedure["p"] is not None else H.p_floor(N_PERM))
    # A p AT the floor means no shuffle reached |rho|: that is the budget's smallest
    # expressible value, not a measurement of how small the p is.
    p_at_floor = bool(H.p_is_floored(p, N_PERM))
    rngb = H.rng("ws3", "bootstrap", scope, K)
    n = x.size
    boot = np.array([spearman(x[ix], y[ix]) for ix in (rngb.integers(0, n, n) for _ in range(N_BOOT))])
    lo, hi = np.nanpercentile(boot, [2.5, 97.5])
    # whale-robust: drop top-5 units by |notional-ish| proxy = |pnl|
    drop = np.argsort(-np.abs(y))[:5]
    m2 = np.ones(x.size, bool); m2[drop] = False
    rho_nowhale = spearman(x[m2], y[m2])
    return {"n": int(n), "rho": rho, "placebo_p": p,
            "placebo_p_floor": H.p_floor(N_PERM), "placebo_p_is_floor": p_at_floor,
            # The counting block: side, both draw counts, slack and the rule that set
            # it, so the cell records the procedure and not only its result.
            "placebo_procedure": procedure,
            "boot_lo": float(lo), "boot_hi": float(hi),
            "rho_drop_top5_pnl": rho_nowhale}


def _covers_zero(lo, hi):
    """True when an interval straddles zero, so this run does not settle the sign."""
    return lo <= 0.0 <= hi


def interpretation(results):
    """The reading of this run, ASSEMBLED FROM ITS OWN NUMBERS instead of typed beside them.

    WHY THIS IS A FUNCTION AND NOT A STRING, measured rather than argued. It was a string
    until 2026-08-05, and by then it had contradicted the numbers printed one key above it
    for four days with nothing noticing. It claimed that early-toxic-flagged wallets realize
    LOWER per-dollar PnL and a lower positive-PnL rate than the rest, and that the group's
    large aggregate profit was a single whale at about 82 percent of it. Every one of those
    claims was TRUE of the run this file used to do at a ten-fill floor: the flagged median
    was -3.637 against -0.129 basis points, the positive rate 0.4252 against 0.4810, the
    aggregate +6,121,000 dollars and the top-1 share 0.8221. The floor rose to the declared
    fifty on 2026-08-01 in commit ddc8786, the out-of-sample split went from 555 flagged
    against 4,990 to 122 against 1,091, and all four flipped. The numbers moved because they
    were computed. The sentence did not, because it was remembered, and a sentence that has
    to be remembered goes stale again.

    NO SIGNIFICANCE LEVEL IS DECLARED HERE, and that is deliberate rather than an omission.
    Every direction below is read off an interval this run already drew, and an interval
    covering zero settles no sign, so this text cannot disagree with the bands printed
    beside it and does not open a second home for a level that belongs in settings.py.

    THE TWO CONCENTRATION SHARES ARE NOT USED, on purpose. `flag_agg_top1_share` divides one
    unit's dollars by the group total, which reads as concentration only while the total is
    positive; the total is negative on this run, so the share comes out negative and a
    reader who takes 0.82 and -0.03 as the same kind of number is reading two different
    quantities under one name. The aggregate is stated in dollars instead, with and without
    its five largest contributions, which means the same thing under either sign.
    """
    o = results["oos_validation"]
    ra = results["rank_agreement"]
    h = results["score_horizon_s"]
    parts = []

    # ---- the full-window rank agreement, pooled ----
    pooled = ra.get("pooled")
    if pooled is None:
        parts.append("The pooled rank cell held too few units to carry a correlation, so "
                     "this run reports no full-window rank agreement at all.")
    else:
        flat = _covers_zero(pooled["boot_lo"], pooled["boot_hi"])
        parts.append(
            f"Over the full window the per-wallet {h}s markout, which is the maker's cost, "
            f"ranks {pooled['n']:,} wallet-coin units against their own realized PnL per "
            f"dollar at rho {pooled['rho']:+.4f}, on a bootstrap interval of "
            f"[{pooled['boot_lo']:+.4f}, {pooled['boot_hi']:+.4f}] that "
            + ("covers zero: pooled, the two rankings agree no better than chance."
               if flat else "excludes zero."))

    # ---- and per coin, which is where a pooled near-zero can hide two effects ----
    cells = {c: cell for c, cell in ra.items() if c != "pooled" and cell}
    decided = {c: cell for c, cell in cells.items()
               if not _covers_zero(cell["boot_lo"], cell["boot_hi"])}
    listed = ", ".join(
        f"{c} at rho {cell['rho']:+.4f} on [{cell['boot_lo']:+.4f}, {cell['boot_hi']:+.4f}]"
        for c, cell in sorted(cells.items()))
    positives = [c for c, cell in decided.items() if cell["rho"] > 0]
    negatives = [c for c, cell in decided.items() if cell["rho"] < 0]
    if cells and len(decided) == len(cells) and positives and negatives:
        parts.append(
            f"That pooled figure is not the per-coin picture repeated: {listed}. Both "
            f"intervals exclude zero and the two disagree in sign, so the pooled near-zero "
            f"is two opposite effects cancelling rather than the absence of one.")
    elif cells:
        parts.append(f"Per coin the same cell reads {listed}.")

    # ---- the out-of-sample leg ----
    fm = o["late_pnl_pd_bps_flag_median"]; rm = o["late_pnl_pd_bps_rest_median"]
    gap = fm - rm
    glo, ghi = o["median_gap_ci"]
    where = "HIGHER" if gap > 0 else ("LOWER" if gap < 0 else "the same")
    pf = o["late_pos_pnl_rate_flag"]; pr = o["late_pos_pnl_rate_rest"]
    prate = "higher" if pf > pr else ("lower" if pf < pr else "the same")
    parts.append(
        f"Out of sample, flagging on the early-half top decile and measuring on the late "
        f"half, the {o['n_flag']:,} flagged units realize a {where} median PnL per dollar "
        f"than the {o['n_rest']:,} others, {fm:+.3f} against {rm:+.3f} basis points. The "
        f"gap of {gap:+.3f} sits on a bootstrap interval of [{glo:+.3f}, {ghi:+.3f}], which "
        + ("covers zero, so the direction is not settled by this population."
           if _covers_zero(glo, ghi) else "excludes zero.")
        + f" Their positive-PnL rate is {prate}, {pf:.4f} against {pr:.4f}, and no interval "
        f"was drawn on that one.")

    # ---- the aggregate, in dollars, with and without its largest contributions ----
    agg = o["late_agg_realized_usd_flag"]; excl = o["flag_agg_excl_top5_usd"]
    word = "a net loss" if agg < 0 else "a net gain"
    kept = "the same sign" if (agg < 0) == (excl < 0) else "the opposite sign"
    parts.append(
        f"In aggregate dollars the flagged group books {agg:+,.0f} over the late half, "
        f"{word}, and dropping its five largest single-unit contributions leaves "
        f"{excl:+,.0f}, {kept}, so the sign is a property of the group and not of a few "
        f"wallets. "
        f"{o['n_positive_flag']:,} of the {o['n_flag_total']:,} flagged units end the late "
        f"half positive.")

    # ---- what follows for the DEFINITION, which is a claim about quantities and not a
    # reading of one, so it is written rather than computed. It has to hold whichever way
    # the gap above points, and it does. ----
    parts.append(
        "Whichever way that gap points, the two measurements are not one quantity: the "
        "maker's markout is a cost booked in the seconds after a fill, and the taker's "
        "realized PnL is settled whenever the position is eventually closed. Toxicity is "
        "therefore the MAKER's short-term realized adverse-selection cost, booked whether "
        "or not the counterparty ultimately profits, and it must NOT be defined by "
        "counterparty PnL.")
    parts.append(
        "CAVEAT: realized PnL is observed only from AGGRESSIVE (taker) closes; passive "
        "closes are invisible, so this is a partial view of counterparty profitability.")
    return " ".join(parts)


def main():
    t0 = artifact.start_clock()
    # panel_io names the producer to run when the panel is absent; the load itself stays
    # here because build.py derives this script's input edge from np.load's argument.
    P.require_present("mid", IN_NPZ)
    z = np.load(IN_NPZ)
    taker = np.asarray(z["taker_id"], dtype=np.int64)
    coin = np.asarray(z["coin"], dtype=np.int8)
    day = np.asarray(z["day"], dtype=np.int16)
    # The score column through panel_io: the window comes from settings.py and the lens
    # from the FILE, so this read cannot pick the trade-print column by accident.
    mo = P.score(z, "mid")                                       # headline, settings.py
    cpnl = np.asarray(z["closed_pnl"], dtype=np.float64)
    notl = np.asarray(z["notional"], dtype=np.float64)
    n = taker.size
    print(f"[ws3] {n:,} taker fills; closed_pnl range [{cpnl.min():.0f},{cpnl.max():.0f}]")

    unit = taker * 4 + coin.astype(np.int64)
    n_units = int(unit.max()) + 1
    early_days, late_days = H.split_early_late(np.unique(day))
    in_early = np.isin(day, list(early_days))
    in_late = np.isin(day, list(late_days))
    full = np.ones(n, bool)

    # The coin map is a property of the FILE, so it is asked for by artifact name rather
    # than re-derived here. The median-price resolution this file used to do is kept as a
    # CROSS-CHECK: if the declared map and the price test ever disagree, one of them is
    # relabelling a coin, and that failure is silent -- a code valid in both files turns
    # BTC into ETH without raising. So the two must agree or the run stops.
    coin_name = H.coin_labels("quickwin")
    price_check = {c: ("BTC" if np.median(z["entry_px"][coin == c]) > 20000 else "ETH")
                   for c in coin_name}
    assert price_check == coin_name, (
        f"declared coin map {coin_name} disagrees with the median-price test "
        f"{price_check}; one of them mislabels a coin")

    settings_used = dict(
        h=H.HEADLINE_HORIZON_S, lens="mid",
        master_seed=H.MASTER_SEED,
        n_perm=N_PERM,
        n_boot=N_BOOT,
        rank_floor_fills=K,
        persistence_floor_fills=None,
        whale_drop_k=5,
        whale_drop_criterion="abs_realized_pnl",
        fdr_alpha=None,
        early_late_split=(
            f"settings.split_early_late over the days present: "
            f"early {list(early_days)}, late {list(late_days)}"),
        p_floor=H.p_floor(N_PERM),
        overrides_note=(
            "master_seed is settings.MASTER_SEED, stated as a CONFIRMATION "
            "rather than a deviation: this file used to declare 424242 for "
            "the permutation and 20260619 for the bootstrap, and now derives "
            "every stream from the declared seed and the cell name through "
            "settings.rng, so the three scopes no longer re-draw one shared "
            "sequence; n_perm "
            "is settings.N_PERM and is stated as a CONFIRMATION rather than a "
            "deviation, so the floor is 1/(N_PERM+1) and not the 0.00498 the "
            "earlier 200-draw artifact reported; n_boot is settings.N_BOOT and "
            "is a CONFIRMATION as well, adopted 2026-07-31, so fifty draws "
            "decide each endpoint instead of the twelve and a half the earlier "
            "500-draw artifact reported; rank_floor_fills is "
            "settings.RANK_FLOOR_FILLS and is a CONFIRMATION too, adopted the "
            "same day against the 10 this file used to run, and that one moves "
            "the POPULATION rather than a band; the whale check drops the top "
            "FIVE units by absolute "
            "realized PnL, which is neither settings.WHALE_DROP_K nor a "
            "notional criterion; no FDR family applies. The halves are cut "
            "by settings.split_early_late over the days present, which on "
            "this input returns the same 4-8 / 9-13 the file used to type"),
    )


    # What the numbers cover, built from the rows and days this run loaded rather than
    # from a description of them. The fingerprint used to sit in the payload as a
    # top-level key, which is a third placement of one record; artifact.write puts it
    # in the one place, so it is passed above and no longer written here.
    days_present = np.unique(day)
    scope_block = {
        "population": (f"{n:,} taker fills of the book-mid panel aggregated to "
                       f"wallet-coin units; a unit enters a rank cell at the "
                       f"{K}-fill floor, and the out-of-sample split flags on the "
                       "early half and measures on the late half"),
        "window": (f"{days_present.size} days present in the input, day-of-month "
                   f"{days_present.min()}-{days_present.max()}, split early "
                   f"{list(early_days)} against late {list(late_days)}"),
        "coins": [coin_name[c] for c in sorted(coin_name)],
    }

    results = {"score_horizon_s": H.HEADLINE_HORIZON_S,
               "score_column": H.headline_mid_col(),
               "K": K, "coin_map": coin_name,
               "coin_map_source": "settings.COIN_CODES_BY_ARTIFACT['quickwin'], "
                                  "cross-checked against the median entry price",
               "rank_agreement": {}, "oos_validation": {}}

    # ---- (1) rank agreement: toxicity vs realized PnL/$ (full window) ----
    for scope, cmask in [("pooled", full), ("BTC", coin == (0 if coin_name[0] == "BTC" else 1)),
                         ("ETH", coin == (0 if coin_name[0] == "ETH" else 1))]:
        a = agg(unit, n_units, cmask, mo, cpnl, notl)
        r = rank_agreement(a["mean_mo"], a["pnl_pd_bps"], a["cnt_mo"], K, scope)
        results["rank_agreement"][scope] = r
        if r:
            print(f"[agree {scope:6s}] rho(toxicity,PnL/$)={r['rho']:.4f} "
                  f"CI=[{r['boot_lo']:.3f},{r['boot_hi']:.3f}] p={r['placebo_p']:.5f}"
                  f"{' [FLOOR]' if r['placebo_p_is_floor'] else '        '} "
                  f"drop-top5={r['rho_drop_top5_pnl']:.4f} n={r['n']}")

    # ---- (2) OOS: flag toxic by EARLY markout top-decile, measure LATE realized PnL ----
    ea = agg(unit, n_units, in_early, mo, cpnl, notl)
    la = agg(unit, n_units, in_late, mo, cpnl, notl)
    # eligible = wallets with >=K early AND >=K late aggressor fills
    elig = (ea["cnt_mo"] >= K) & (la["cnt"] >= K) & np.isfinite(ea["mean_mo"])
    early_tox = ea["mean_mo"][elig]
    thr = np.quantile(early_tox, TOXIC_Q)
    flag = elig & (ea["mean_mo"] >= thr)
    rest = elig & ~flag
    late_pnl_pd_flag = la["pnl_pd_bps"][flag]
    late_pnl_pd_rest = la["pnl_pd_bps"][rest]
    late_pnl_pd_flag = late_pnl_pd_flag[np.isfinite(late_pnl_pd_flag)]
    late_pnl_pd_rest = late_pnl_pd_rest[np.isfinite(late_pnl_pd_rest)]
    # positive-PnL rate and aggregate realized $ in LATE
    pos_rate_flag = float(np.mean(la["sum_cp"][flag] > 0))
    pos_rate_rest = float(np.mean(la["sum_cp"][rest] > 0))
    agg_pnl_flag = float(la["sum_cp"][flag].sum())
    agg_pnl_rest = float(la["sum_cp"][rest].sum())
    # is the flag's aggregate profit a GROUP property or one whale? (honesty check)
    fv = la["sum_cp"][flag]; order = np.argsort(-fv); tot = float(fv.sum())
    flag_top1_share = float(fv[order[0]] / tot) if tot else None
    flag_top5_share = float(fv[order[:5]].sum() / tot) if tot else None
    flag_agg_excl_top5 = float(tot - fv[order[:5]].sum())
    n_pos_flag = int((fv > 0).sum()); n_flag = int(fv.size)
    # bootstrap CI on the median-PnL/$ gap (flag - rest). Its own stream, named for what
    # it resamples, so it cannot share draws with the rank-agreement bootstrap above.
    rngb = H.rng("ws3", "bootstrap", "oos_median_gap", K)
    gaps = []
    for _ in range(N_BOOT):
        gf = late_pnl_pd_flag[rngb.integers(0, late_pnl_pd_flag.size, late_pnl_pd_flag.size)]
        gr = late_pnl_pd_rest[rngb.integers(0, late_pnl_pd_rest.size, late_pnl_pd_rest.size)]
        gaps.append(np.median(gf) - np.median(gr))
    glo, ghi = np.percentile(gaps, [2.5, 97.5])
    results["oos_validation"] = {
        "n_flag": int(flag.sum()), "n_rest": int(rest.sum()),
        "late_pnl_pd_bps_flag_median": float(np.median(late_pnl_pd_flag)),
        "late_pnl_pd_bps_rest_median": float(np.median(late_pnl_pd_rest)),
        "late_pnl_pd_bps_flag_mean": float(np.mean(late_pnl_pd_flag)),
        "late_pnl_pd_bps_rest_mean": float(np.mean(late_pnl_pd_rest)),
        "median_gap_ci": [float(glo), float(ghi)],
        "late_pos_pnl_rate_flag": pos_rate_flag, "late_pos_pnl_rate_rest": pos_rate_rest,
        "late_agg_realized_usd_flag": agg_pnl_flag, "late_agg_realized_usd_rest": agg_pnl_rest,
        "flag_agg_top1_share": flag_top1_share, "flag_agg_top5_share": flag_top5_share,
        "flag_agg_excl_top5_usd": flag_agg_excl_top5,
        "n_positive_flag": n_pos_flag, "n_flag_total": n_flag,
    }
    o = results["oos_validation"]
    print(f"[oos] early-toxic flag n={o['n_flag']} vs rest n={o['n_rest']}")
    print(f"[oos] LATE realized PnL/$ (bps) median: flag={o['late_pnl_pd_bps_flag_median']:.3f} "
          f"rest={o['late_pnl_pd_bps_rest_median']:.3f} gap CI=[{glo:.3f},{ghi:.3f}]")
    print(f"[oos] LATE positive-PnL rate: flag={pos_rate_flag:.3f} rest={pos_rate_rest:.3f}")
    print(f"[oos] LATE aggregate realized $: flag={agg_pnl_flag:,.0f} rest={agg_pnl_rest:,.0f}")

    # ---- (3) the binned curve the left panel draws, PERSISTED rather than redrawn ----
    # This block computes nothing new: it is the arithmetic that used to live inside the
    # plotting branch, moved up so that its ten points land in the results file. The
    # reason is the figure, not the numbers. While the curve was computed only at drawing
    # time, redrawing the panel meant re-reading the panel and re-aggregating it, which is
    # this node's whole 36.8-second runtime; with the ten points on disk the figure is a
    # pure read of the artifact. Ten bins by decile of toxicity, the same cut as before.
    a_full = agg(unit, n_units, full, mo, cpnl, notl)
    keep = (a_full["cnt_mo"] >= K) & np.isfinite(a_full["mean_mo"]) & np.isfinite(a_full["pnl_pd_bps"])
    x_tox = a_full["mean_mo"][keep]; y_pnl = a_full["pnl_pd_bps"][keep]
    qs = np.quantile(x_tox, np.linspace(0, 1, N_TOXICITY_BINS + 1))
    bin_x = (0.5 * (qs[:-1] + qs[1:])).tolist()
    bin_y, bin_n = [], []
    for i in range(N_TOXICITY_BINS):
        m = (x_tox >= qs[i]) & (x_tox <= qs[i + 1])
        bin_n.append(int(m.sum()))
        # None and not NaN for an empty bin: NaN is not JSON, and a reader that has to
        # guess what a bare null means is told the count beside it.
        bin_y.append(float(np.median(y_pnl[m])) if m.sum() else None)
    results["pnl_vs_toxicity_bins"] = {
        "n_bins": N_TOXICITY_BINS,
        "bin_centre_toxicity_bps": bin_x,
        "bin_median_pnl_per_dollar_bps": bin_y,
        "bin_n_units": bin_n,
        "n_units_binned": int(keep.sum()),
        "what_this_is": (
            "wallet-coin units with at least K aggressor fills, cut into equal-count "
            "bins by their own mean markout; the y value is the median realized PnL per "
            "dollar inside the bin. This is the left panel of ws3_taker_pnl.png and it "
            "is stored so the figure can be redrawn without re-aggregating the panel."),
    }
    print(f"[ws3] toxicity-vs-PnL bins: {N_TOXICITY_BINS} over {int(keep.sum()):,} units")

    # THE READING IS ASSEMBLED LAST, from the payload as it will be written. It used to be
    # typed in the middle of main(), immediately after the out-of-sample block and before
    # the binned curve existed, which is what let it go on describing an arm the file had
    # stopped computing. Built here it can only ever describe the numbers beside it, and it
    # is built from `results` rather than from the local variables so that a key renamed in
    # the payload breaks the sentence loudly instead of leaving it standing over nothing.
    results["interpretation"] = interpretation(results)

    # The output name and directory still come from the module-level OUT_JSON, so a
    # caller that redirects that constant redirects the whole write, as before. Every
    # departure from the declaration is stated in settings_used above and appears in
    # the block's overridden list, so a deliberate difference stays visible instead of
    # reading like a drift.
    artifact.write(os.path.basename(OUT_JSON), results,
                   script=__file__, inputs=[IN_NPZ], scope=scope_block,
                   settings=settings_used, started=t0,
                   out_dir=os.path.dirname(OUT_JSON))
    print(f"[ws3] wrote {os.path.basename(OUT_JSON)}")
    # The figure is NOT drawn here. It is drawn by ws3_plot.py, which reads this very
    # results file and computes nothing. Splitting it out is the fix rather than a
    # tidying: while one node both computed and drew, a figure that failed to be drawn
    # was invisible inside the exit code of a computation that had succeeded, and on
    # this figure that hid a SIGN error on disk for two days.
    print("[ws3] the figure is NOT drawn here. Draw it with:\n"
          "    uv run --no-project --with-requirements requirements.txt python3 "
          "ws3_plot.py")


if __name__ == "__main__":
    main()
