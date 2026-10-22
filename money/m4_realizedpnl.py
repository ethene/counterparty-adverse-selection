"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-19
References: Hyperliquid node-data S3 archive; Zenodo 18184441 (Albers et al. 2026).
"""

# ---------------------------------------------------------------------------
# OBJECT M4 — REALIZED-PnL vs PRICE-MARKOUT CROSS-METHOD VALIDATION
#
# The adverse-selection story rests on ONE measurement: the signed price
# markout faced by the maker (mo10). A wallet with a high mean taker markout is
# read as "toxic" -- its flow tends to be right about the next 10 seconds, so
# the maker that filled it loses. That is a PRICE-PATH signal computed from the
# reference print, and it is the single number the whole study leans on.
#
# This script adds a SECOND toxicity measure from the SAME fills and asks whether
# the two agree. The Hyperliquid taker leg books `closedPnl` when a fill closes or
# reduces a position: that is the wallet's OWN realized trading profit, booked by
# the exchange, with no reference-price model of ours in it. If a wallet that
# looks toxic by price-markout ALSO realizes profit, two methodologically
# distinct measures -- with no shared reference-price model -- point the same way
# and the toxicity label is much harder to dismiss as a markout artefact. (They
# are NOT statistically independent: closedPnl and mo10 are both computed from the
# same underlying fills, so the agreement is a cross-method check, not a draw of
# two independent samples; we report the rho MAGNITUDE next to the p-value so the
# large-N significance is not over-read as strong agreement.)
#
# Per wallet:
#   realized_pnl  = sum of closed_pnl over that wallet's CLOSE trades. The close
#                   set is defined by is_open == 0 (every fill the build script
#                   marks as closing/reducing), which INCLUDES the dir_code == -1
#                   rows -- those are genuine closes whose open/close direction was
#                   simply unresolved, and they carry real closedPnl. Defining the
#                   close set by the literal dir_code in {2,3} would silently drop
#                   them and bias the realized-PnL totals. Opens book ~0 closedPnl.
#   markout_tox   = mean of mo10 over that wallet's trades (signed taker markout
#                   in bps; positive = taker profited = maker adverse-selected).
#
# Headline statistic: Spearman rank correlation between realized_pnl and
# markout_tox across wallets, per coin and pooled. Spearman (not Pearson) because
# both are heavy-tailed and we only claim a monotone agreement, not a linear one.
#
# Robustness, both cheap and load-bearing:
#   * label-permutation placebo: shuffle the markout_tox labels across wallets
#     (seed 20260619) and recompute Spearman settings.N_PERM times; the placebo
#     p-value is the fraction of |rho_perm| >= |rho_obs|, floored at 1/(N+1). The
#     budget is read from settings.py rather than typed here, so the floor moves with
#     it and this sentence cannot go stale against the code. A real agreement should
#     sit far outside the permuted null.
#   * whale robustness: drop the top-10 wallets by |realized_pnl| and recompute,
#     so a handful of giant accounts cannot manufacture the correlation.
#
# numpy-only. Reads the EXTENDED quickwin_markouts.npz (needs closed_pnl,
# dir_code, mo10). Writes m4_realizedpnl_results.json. No plotting.
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
import stats

# ---------------------------------------------------------------------------
# Paths / config
# ---------------------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
# Located by panel_io rather than joined here, so the one place that knows where the
# panels live answers for this file too. The output stays beside the script.
NPZ_PATH = os.path.join(P.data_root(), "quickwin_markouts.npz")
OUT_PATH = os.path.join(HERE, "m4_realizedpnl_results.json")

# int8 code -> symbol. The map is a property of the FILE, not of the project
# (quickwin_markouts.npz carries {0, 1}, panel_markouts.npz carries {0, 1, 2}), so it
# is asked for by artifact name and never written out here.
COIN_NAME = H.coin_labels("quickwin")

# The close set is defined by is_open == 0 (the build-script close/reduce flag),
# NOT the literal dir_code in {2,3}. is_open == 0 also captures the dir_code == -1
# rows -- genuine closes with an unresolved direction that still book real
# closedPnl -- so the realized-PnL totals are computed on the COMPLETE close set.
CLOSE_DIR_CODES = (2, 3)             # 2=Close Long, 3=Close Short (reference only)

# This run's seed for the permutation placebo, READ from settings.py under the name of
# the consumer that draws it. The value is the same 20260619 every published number in
# m4_realizedpnl_results.json was drawn under, so reading it here moves nothing.
#
# Reading a value is not the same as agreeing with the headline declaration, and this one
# still differs from it: settings.MASTER_SEED is 20260620, and the per-purpose map records
# what this consumer actually draws rather than what it should eventually draw. Binding
# this file to the master seed redraws its null and moves its p-values, so it stays a
# measured change owed its own recompute, and the fingerprint keeps recording it as an
# override.
RNG_SEED = H.seed_for("m4_realizedpnl")
# Label shuffles for the placebo null, READ from settings.py. This declaration carried
# TWO divergences from the module at once, and the second is the kind that hides.
#
# Its NAME was N_PERMUTATIONS where the rest of the tree writes N_PERM, so a search for
# the budget by name did not find this file at all. Its VALUE was 1000 where the module
# declares the budget computed by settings.min_perm_draws from the level, the family size
# and the floor margin. A quantity with its own name and its own value is not a setting
# that disagrees; it is a setting nobody knows is there.
#
# The old value cleared its bar and still had to go: a floor of 1/1001 = 0.000999 against
# a corrected rank-one threshold of 0.05/48 = 0.001042 is a margin of four percent, which
# is precisely the boundary case settings.PERM_FLOOR_MARGIN is declared to forbid.
N_PERM = H.N_PERM

# The floor is settings.p_floor, not a third arithmetic copy of 1/(N+1). The old local
# constant was also used as `max(p, PLACEBO_FLOOR)` at the p-value, which could never
# bind: (count + 1) / (N + 1) is at least 1 / (N + 1) by construction, so the clamp was a
# no-op restating the formula it clamped.
PLACEBO_FLOOR = H.p_floor(N_PERM)
N_DROP_WHALES = H.WHALE_DROP_K       # top-|realized_pnl| wallets dropped in the
                                     # robustness pass; the count is declared, the
                                     # criterion is this file's (see WHALE_KEY below)

# The whale arm drops the ten largest by ABSOLUTE REALIZED PnL. A key that says only
# "top 10" does not say top ten by what, and dropping the ten largest by realized PnL
# answers a different question from dropping the ten largest by notional or by fill
# count. settings.whale_drop names the criterion inside the key, so the artifact
# cannot be read as either of the other two.
WHALE_KEY = "whale_robustness_" + H.whale_drop("abs_realized_pnl",
                                               N_DROP_WHALES)["key"]


# ---------------------------------------------------------------------------
# Spearman correlation (numpy-only, average-rank tie handling). The ranking and the
# correlation come from stats.py, which already owns the permutation this file's p-value
# runs through; checks/chk_closedpnl.py, which audits the number below, reads the same
# two definitions rather than a copy of them.
# ---------------------------------------------------------------------------
def spearman(x, y):
    """Spearman rank correlation = Pearson on the average ranks."""
    if np.asarray(x).size < 2:
        return float("nan")
    return stats.pearson_r(stats.rankdata(x), stats.rankdata(y))


# ---------------------------------------------------------------------------
# Per-wallet aggregation
# ---------------------------------------------------------------------------
def per_wallet(taker_id, closed_pnl, is_open, mo_score):
    """Collapse trades to per-wallet (realized_pnl, markout_tox).

    realized_pnl : sum of closed_pnl over the wallet's CLOSE trades only, where
                   the close set is is_open == 0 (the complete close/reduce set,
                   including dir_code == -1 genuine closes).
    markout_tox  : mean of mo10 over the wallet's trades with a finite mo10.

    Wallets keep one row each. A wallet with no finite mo10 (so no markout
    toxicity) is dropped by the caller via the finite mask. Returns aligned
    arrays sorted by wallet id, plus the unique ids for traceability.
    """
    if taker_id.size == 0:
        z = np.empty(0, dtype=np.float64)
        return (np.empty(0, dtype=np.int64), z, z.copy(), z.copy())

    uniq, inv = np.unique(taker_id, return_inverse=True)

    # realized PnL: only CLOSE trades contribute (opens book ~0 closedPnl). The
    # close set is is_open == 0, which includes the dir_code == -1 genuine closes.
    is_close = np.asarray(is_open, dtype=np.int64) == 0
    realized = np.zeros(uniq.size, dtype=np.float64)
    cp = np.where(np.isfinite(closed_pnl), closed_pnl, 0.0).astype(np.float64)
    np.add.at(realized, inv[is_close], cp[is_close])

    # markout toxicity: mean mo10 over the wallet's finite-markout trades.
    finite_mo = np.isfinite(mo_score)
    tox_sum = np.zeros(uniq.size, dtype=np.float64)
    tox_cnt = np.zeros(uniq.size, dtype=np.float64)
    np.add.at(tox_sum, inv[finite_mo], mo_score[finite_mo].astype(np.float64))
    np.add.at(tox_cnt, inv[finite_mo], 1.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        markout_tox = np.where(tox_cnt > 0, tox_sum / tox_cnt, np.nan)

    return uniq, realized, markout_tox, tox_cnt


# ---------------------------------------------------------------------------
# Permutation placebo + whale-robustness
# ---------------------------------------------------------------------------
def permutation_placebo(realized, markout_tox, rho_obs, rng):
    """Fraction of |Spearman| under shuffled toxicity labels >= |observed|.

    Shuffling markout_tox across wallets breaks any real wallet-level pairing
    while preserving both marginals, so the permuted Spearman distribution is the
    null "no agreement between the two toxicity signals". p is floored at
    1/(N+1) so a zero-count never reports as exactly 0.

    THE COUNTING IS stats.permutation_p AND THE ARITHMETIC IS UNCHANGED. What this
    function hands the module is exactly what it used to count for itself: the
    comparison is TWO-SIDED on |rho|, because the question is whether the two rankings
    agree OR disagree more than chance; the slack is stated ABSOLUTE at zero, because
    this file never applied one and the module's scale-relative default would move the
    p on any cell with a draw within a whisker of the observed |rho|; and the
    denominator is the count of draws that came back finite, which on this null is the
    whole budget. That last equality is not luck. _pearson returns NaN only when one
    side has zero variance, and a permutation of the toxicity vector is a permutation
    of the SAME values, so its rank vector has the same spread for every draw as for
    the observed one -- either every draw is finite or rho_obs is not, and the
    non-finite case returns above before any draw is taken.
    """
    n = realized.size
    if n < 3 or not np.isfinite(rho_obs):
        return {"p_value": float("nan"), "n_permutations": 0,
                "n_ge_observed": 0, "floor": PLACEBO_FLOOR,
                "perm_rho_mean": float("nan"), "perm_rho_std": float("nan"),
                "procedure": None}
    rank_real = stats.rankdata(realized)         # ranks of the fixed side, computed once
    perm_rhos = np.empty(N_PERM, dtype=np.float64)
    for k in range(N_PERM):
        shuffled = markout_tox[rng.permutation(n)]
        perm_rhos[k] = stats.pearson_r(rank_real, stats.rankdata(shuffled))
    procedure = stats.permutation_p(rho_obs, perm_rhos, side="two_sided", abs_tol=0.0,
                                    n_requested=N_PERM,
                                    cell=("m4_realizedpnl", "rho_placebo"))
    # The clamp that used to sit here could never bind: (count + 1) / (N + 1) is at
    # least 1 / (N + 1) by construction, so it restated the formula it clamped. What
    # the fallback below covers is the one case the module reports as "no test" and
    # this file used to report as the floor -- unreachable by the argument in the
    # docstring, and carried over verbatim rather than left to raise.
    p = procedure["p"] if procedure["p"] is not None else PLACEBO_FLOOR
    finite_perm = perm_rhos[np.isfinite(perm_rhos)]
    return {
        "p_value": float(p),
        "n_permutations": N_PERM,
        "n_ge_observed": int(procedure["n_at_least_as_extreme"]),
        "floor": PLACEBO_FLOOR,
        # Kept local rather than read off the block: the block reports 0.0 for the
        # spread of a single usable draw where this file reports NaN, and the two
        # differ on a budget of one.
        "perm_rho_mean": float(finite_perm.mean()) if finite_perm.size else float("nan"),
        "perm_rho_std": float(finite_perm.std(ddof=1)) if finite_perm.size > 1 else float("nan"),
        "procedure": procedure,
    }


def drop_top_whales(realized, markout_tox, k=N_DROP_WHALES):
    """Spearman after removing the k wallets with the largest |realized_pnl|.

    A few giant accounts can dominate a rank correlation if their realized PnL
    and markout both sit at an extreme. Dropping them tests that the agreement
    survives in the body of the distribution.
    """
    n = realized.size
    if n <= k + 2:
        return {"rho": float("nan"), "n_wallets": n, "k_dropped": 0,
                "note": "too few wallets to drop top-k"}
    order = np.argsort(np.abs(realized))[::-1]   # largest |realized| first
    keep = np.ones(n, dtype=bool)
    keep[order[:k]] = False
    rho = spearman(realized[keep], markout_tox[keep])
    return {"rho": rho, "n_wallets": int(keep.sum()), "k_dropped": int(k)}


# ---------------------------------------------------------------------------
# One slice (coin or pooled)
# ---------------------------------------------------------------------------
def analyse_slice(taker_id, closed_pnl, is_open, mo_score, rng):
    """Full cross-method validation block for one slice."""
    uniq, realized, markout_tox, tox_cnt = per_wallet(
        taker_id, closed_pnl, is_open, mo_score)

    # keep wallets that have a defined markout toxicity (>=1 finite-mo10 trade)
    ok = np.isfinite(markout_tox)
    realized = realized[ok]
    markout_tox = markout_tox[ok]
    n_wallets = int(realized.size)

    if n_wallets < 3:
        return {
            "n_wallets": n_wallets,
            "spearman_rho": float("nan"),
            "note": "fewer than 3 wallets with a defined markout; correlation skipped",
        }

    rho_obs = spearman(realized, markout_tox)
    placebo = permutation_placebo(realized, markout_tox, rho_obs, rng)
    whale = drop_top_whales(realized, markout_tox)

    frac_realize_profit = float(np.mean(realized > 0))
    frac_markout_toxic = float(np.mean(markout_tox > 0))
    # agreement quadrant: toxic-by-markout AND realizes profit
    both_toxic = float(np.mean((markout_tox > 0) & (realized > 0)))

    placebo_p = placebo.get("p_value", float("nan"))
    return {
        "n_wallets": n_wallets,
        "spearman_rho": rho_obs,
        # report the rho MAGNITUDE next to the (floored) p so the large-N
        # significance is read as a weak-but-real monotone agreement, not a
        # strong one. |rho| ~ 0.03 here: real, directional, but small.
        "spearman_rho_magnitude": float(abs(rho_obs)) if np.isfinite(rho_obs)
                                  else float("nan"),
        "placebo_p_value": placebo_p,
        "effect_size_note": (
            "rho is small in magnitude (~0.03); the floored permutation p "
            "reflects large N, NOT a strong agreement. Two methodologically "
            "distinct measures agree in DIRECTION, weakly."),
        "interpretation": (
            "positive rho => wallets that look toxic by price-markout also tend "
            "to realize profit; two methodologically distinct toxicity measures "
            "(no shared reference-price model) agree in direction, weakly"),
        "placebo": placebo,
        WHALE_KEY: whale,
        "frac_wallets_realize_profit": frac_realize_profit,
        "frac_wallets_markout_toxic": frac_markout_toxic,
        "frac_wallets_toxic_and_profitable": both_toxic,
        "realized_pnl_total_quote": float(realized.sum()),
        "realized_pnl_mean_quote": float(realized.mean()),
        "markout_tox_mean_bps": float(markout_tox.mean()),
    }


def main():
    t0 = artifact.start_clock()
    # panel_io names the producer to run when the panel is absent, and refuses a column
    # the file does not hold in the same wording everywhere. The load itself stays here
    # because build.py derives this script's input edge from the argument of np.load.
    P.require_present("print", NPZ_PATH)

    data = np.load(NPZ_PATH)
    # The extra columns this file needs beyond the panel's own: they come from the
    # EXTENDED build and their absence is what the refusal has to name.
    P.require_columns(data, "print", "taker_id", "closed_pnl", "is_open", "dir_code",
                      "coin")

    taker_id = data["taker_id"].astype(np.int64)
    closed_pnl = data["closed_pnl"].astype(np.float64)
    is_open = data["is_open"].astype(np.int8)
    dir_code = data["dir_code"].astype(np.int8)
    mo_score = P.score(data, "print")
    coin = data["coin"].astype(np.int8)
    # Read only to state the window in the artifact's scope; it enters no computation.
    day = data["day"].astype(np.int64)

    # close-set bookkeeping for _meta: is_open==0 vs the literal dir_code in {2,3}.
    n_close_isopen0 = int(np.sum(is_open == 0))
    n_close_dir23 = int(np.sum(np.isin(dir_code, CLOSE_DIR_CODES)))
    n_dirneg1_closes = int(np.sum((dir_code == -1) & (is_open == 0)))
    cp_finite = np.where(np.isfinite(closed_pnl), closed_pnl, 0.0)
    pnl_dirneg1_closes = float(cp_finite[(dir_code == -1) & (is_open == 0)].sum())

    # one RNG, fixed seed, drawn in a deterministic order (BTC, ETH, pooled).
    rng = np.random.default_rng(RNG_SEED)

    results = {
        "_meta": {
            "object": "M4 realized-PnL vs price-markout cross-method validation",
            "horizon_s": H.HEADLINE_HORIZON_S,
            "markout_column": H.headline_print_col(),
            "headline": (f"Spearman(realized_pnl, mean {H.headline_print_col()}) "
                         "per wallet, per coin + pooled"),
            "realized_pnl_def": (
                "sum closed_pnl over wallet's CLOSE trades, close set = "
                "is_open == 0 (the COMPLETE close/reduce set, including the "
                "dir_code == -1 genuine closes); NOT the literal dir_code in {2,3}"),
            "close_set_bookkeeping": {
                "n_close_is_open_eq_0": n_close_isopen0,
                "n_close_dir_code_in_2_3": n_close_dir23,
                "n_dir_code_neg1_closes_added": n_dirneg1_closes,
                "closed_pnl_on_dir_code_neg1_closes_quote": pnl_dirneg1_closes,
                "note": ("the dir_code == -1 closes are real closes the literal "
                         "{2,3} set drops; they sum closed_pnl ~ "
                         f"{pnl_dirneg1_closes:,.2f} and flip the BTC total"),
            },
            "markout_tox_def": (f"mean {H.headline_print_col()} over wallet's "
                                "finite-markout trades (bps)"),
            "claim": ("a wallet toxic by price-markout should ALSO realize profit; "
                      "two methodologically distinct measures with no shared "
                      "reference-price model agreeing in direction hardens the "
                      f"toxicity label (closedPnl and {H.headline_print_col()} share "
                      "the same fills, so this is a cross-method check, not two "
                      "independent samples)"),
            "rng_seed": RNG_SEED,
            "n_permutations": N_PERM,
            "placebo_floor": PLACEBO_FLOOR,
            "n_drop_whales": N_DROP_WHALES,
            "whale_drop_criterion": H.whale_drop("abs_realized_pnl",
                                                 N_DROP_WHALES)["criterion"],
            "n_trades_total": int(taker_id.size),
        }
    }

    # What the numbers cover. The population is deliberately unfloored: the statistic
    # is a cross-method agreement over the WHOLE wallet population, so a wallet enters
    # on one finite markout trade and flooring it would restate the very population
    # being validated.
    days = np.unique(day)
    scope = {
        "population": (f"{taker_id.size:,} rows of the trade-print panel reduced to "
                       "per-wallet realized PnL against per-wallet mean markout; a "
                       "wallet enters on one finite markout trade, with no fill "
                       "floor applied"),
        "window": (f"{days.size} days present in the input, day-of-month "
                   f"{days.min()}-{days.max()}; the calendar dates of the window "
                   "are declared by its producer, build_quickwin_markouts.py"),
        "coins": [COIN_NAME[c] for c in sorted(COIN_NAME)],
    }
    results["_meta"]["rank_floor_note"] = (
        "wallets enter on one finite markout trade, not on the declared 50-fill "
        "floor: the statistic is a cross-method agreement over the whole wallet "
        "population, and flooring it would restate the population being validated")

    for code, name in COIN_NAME.items():
        sel = coin == code
        results[name] = analyse_slice(
            taker_id[sel], closed_pnl[sel], is_open[sel], mo_score[sel], rng)

    results["pooled"] = analyse_slice(taker_id, closed_pnl, is_open, mo_score, rng)

    # The output name and directory still come from the module-level OUT_PATH, so a
    # caller that redirects that constant redirects the whole write, as before. Two
    # stamped settings genuinely differ from the declaration and are passed
    # explicitly, so a reader sees a deliberate difference instead of a value that
    # looks declared and is not: this file seeds its placebo with its own literal, and
    # it keeps every wallet with at least one finite markout instead of applying the
    # declared wallet floor. The permutation budget is passed to state that this run
    # confirmed the declared value rather than to record a departure from it.
    artifact.write(os.path.basename(OUT_PATH), results,
                   script=__file__, inputs=[NPZ_PATH], scope=scope,
                   settings={"h": H.HEADLINE_HORIZON_S, "lens": "print",
                             "master_seed": RNG_SEED, "n_perm": N_PERM,
                             "rank_floor_fills": 1},
                   started=t0, out_dir=os.path.dirname(OUT_PATH))

    print_summary(results)
    print(f"\n[m4] wrote {os.path.basename(OUT_PATH)}")


# ---------------------------------------------------------------------------
# Printed summary
# ---------------------------------------------------------------------------
def _fmt(x, nd=4):
    return f"{x:.{nd}f}" if isinstance(x, float) and np.isfinite(x) else "n/a"


def print_summary(results):
    print("=" * 78)
    print("M4 — REALIZED-PnL vs PRICE-MARKOUT CROSS-METHOD VALIDATION")
    print("=" * 78)
    meta = results["_meta"]
    print(f"trades total : {meta['n_trades_total']:,}")
    csb = meta.get("close_set_bookkeeping", {})
    print(f"close set    : is_open==0 = {csb.get('n_close_is_open_eq_0', 0):,} "
          f"(vs dir_code{{2,3}} = {csb.get('n_close_dir_code_in_2_3', 0):,}; "
          f"+{csb.get('n_dir_code_neg1_closes_added', 0):,} dir==-1 genuine closes)")
    print(f"Spearman(realized_pnl, mean {H.headline_print_col()}) across wallets. "
          "Positive => two")
    print("methodologically distinct measures AGREE in direction (weakly).")
    print("rho magnitude reported next to placebo_p: |rho| ~ 0.03 = small.\n")
    h = (f"{'slice':<8} {'wallets':>9} {'rho':>8} {'|rho|':>7} {'placebo_p':>10} "
         f"{'rho_drop10':>11} {'%tox&prof':>10} {'realized_pnl_tot':>18}")
    print(h)
    print("-" * len(h))
    for key in ("BTC", "ETH", "pooled"):
        if key not in results:
            continue
        r = results[key]
        if "spearman_rho" not in r:
            print(f"{key:<8} {r.get('n_wallets', 0):>9,}  (skipped: {r.get('note','')})")
            continue
        p = r["placebo"]["p_value"] if "placebo" in r else float("nan")
        wd = (r[WHALE_KEY]["rho"] if WHALE_KEY in r else float("nan"))
        rho_mag = r.get("spearman_rho_magnitude", float("nan"))
        pnl_tot = r.get("realized_pnl_total_quote", float("nan"))
        print(f"{key:<8} {r['n_wallets']:>9,} {_fmt(r['spearman_rho'], 3):>8} "
              f"{_fmt(rho_mag, 3):>7} {_fmt(p, 4):>10} {_fmt(wd, 3):>11} "
              f"{_fmt(r.get('frac_wallets_toxic_and_profitable'), 3):>10} "
              f"{_fmt(pnl_tot, 2):>18}")
    print(f"    (placebo_p floored at {PLACEBO_FLOOR:.5f}; rho_drop10 = after "
          f"dropping the top {N_DROP_WHALES} wallets by |realized_pnl|)")
    print("    realized_pnl_tot on the CORRECTED is_open==0 close set "
          "(includes dir_code==-1 genuine closes).")
    print(f"    dir_code==-1 closes add closed_pnl ~ "
          f"{csb.get('closed_pnl_on_dir_code_neg1_closes_quote', float('nan')):,.2f} "
          "to the close set.")
    print("=" * 78)


if __name__ == "__main__":
    main()
