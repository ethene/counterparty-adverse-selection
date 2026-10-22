"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-21
References: Albers et al. "An Open Book" (Zenodo 18184441 / SSRN 6465720); internal
           data_acquisition_log.md verified field semantics.

PROBE A1 — print-vs-book-mid markout calibration (the scope decision).

Question: does trade-print markout track book-mid markout closely enough that the
trade-print proxy can be trusted on the wider panel (Aug/Oct, SOL, the 250-perp
cross-section) where NO reconstructed book exists?

Data (row-aligned, content-verified by check_first.py):
  quickwin_markouts.npz      -> mo1/mo10/mo60        (trade-print reference)
  quickwin_markouts_mid.npz  -> mo1_mid/.../mo60_mid (book-mid reference)
  Dec 4-13, BTC+ETH, 2,480,267 rows.

Decisive metric = per-COUNTERPARTY RANKING agreement (the toxicity claim rests on the
cross-sectional ranking, not the level; the book-mid LEVEL is inflated by own-spread-
crossing per the I4 caveat). If Spearman(rank_by_print, rank_by_mid) is high at 60s,
the proxy is trustworthy and the wide panel is in scope.

Read-only: writes calib_print_vs_mid_results.json + prints a summary. No side effects.
"""
import os
import sys

import numpy as np
from scipy import stats

# The settings and artifact modules live one directory up, so the path is built from
# this file's own location and never from the working directory the run happens to start
# in. `stats` here is SciPy's and not the repository's statistics module: this file runs
# no permutation, no bootstrap and no multiplicity correction, so the two never meet,
# and the name is left as SciPy's rather than shadowed.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import artifact  # noqa: E402
import panel_io as P  # noqa: E402
import settings as H  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CODE_DIR = os.path.dirname(HERE)
# Located by panel_io rather than joined here, so the one place that knows where the
# markout panels live is the one place that has to change if they move.
IN_PRINT = os.path.join(P.data_root(), "quickwin_markouts.npz")
IN_MID = os.path.join(P.data_root(), "quickwin_markouts_mid.npz")
OUT_JSON = os.path.join(HERE, "calib_print_vs_mid_results.json")
COIN = {0: "BTC", 1: "ETH", 2: "SOL"}
HORIZONS = list(H.LADDER_S)   # every rung the quickwin artifacts carry a column for
K_THRESH = [20, 50, 100]


def load():
    # panel_io names the producer to run when a file is absent, so that message is
    # written once for the whole tree; the loads stay here because build.py derives
    # this script's input edges from the arguments of np.load.
    P.require_present("print", IN_PRINT)
    P.require_present("mid", IN_MID)
    a = np.load(IN_PRINT, allow_pickle=True)
    b = np.load(IN_MID, allow_pickle=True)
    # The row count is taken off the companion rung of each file, asked for by name
    # rather than spelled. Any rung would answer the same question -- this is a length
    # test, not a measurement -- but a typed one would fix a window here for no reason.
    n = a[P.score_col("print", H.COMPANION_HORIZON_S)].shape[0]
    assert b[P.score_col("mid", H.COMPANION_HORIZON_S)].shape[0] == n, \
        "row counts differ -> not aligned"
    # sanity: shared columns must match (they are content-verified, re-assert cheaply)
    assert np.array_equal(a["taker_id"], b["taker_id"]), "taker_id misaligned"
    assert np.array_equal(a["maker_id"], b["maker_id"]), "maker_id misaligned"
    return a, b, n


def finite_mask(*arrs):
    m = np.ones(arrs[0].shape[0], dtype=bool)
    for x in arrs:
        m &= np.isfinite(x)
    return m


def group_mean(ids, vals, w=None):
    """EW (w=None) or weighted group mean + count, returned as dict id->(mean,count,wsum)."""
    uid, inv = np.unique(ids, return_inverse=True)
    cnt = np.bincount(inv, minlength=uid.size).astype(np.float64)
    if w is None:
        s = np.bincount(inv, weights=vals, minlength=uid.size)
        mean = s / np.maximum(cnt, 1)
    else:
        sw = np.bincount(inv, weights=w, minlength=uid.size)
        swv = np.bincount(inv, weights=w * vals, minlength=uid.size)
        mean = swv / np.maximum(sw, 1e-12)
    return uid, mean, cnt


def cp_rank_corr(ids, print_v, mid_v, notional, kmin):
    """Per-counterparty Spearman between print-markout and mid-markout, EW and VW."""
    out = {}
    # EW
    uid, m_print, cnt = group_mean(ids, print_v)
    _, m_mid, _ = group_mean(ids, mid_v)
    keep = cnt >= kmin
    nkeep = int(keep.sum())
    if nkeep >= 5:
        rho_ew, p_ew = stats.spearmanr(m_print[keep], m_mid[keep])
        pear_ew, _ = stats.pearsonr(m_print[keep], m_mid[keep])
    else:
        rho_ew = p_ew = pear_ew = float("nan")
    # VW
    _, mw_print, _ = group_mean(ids, print_v, w=notional)
    _, mw_mid, _ = group_mean(ids, mid_v, w=notional)
    if nkeep >= 5:
        rho_vw, _ = stats.spearmanr(mw_print[keep], mw_mid[keep])
    else:
        rho_vw = float("nan")
    return {
        "n_counterparties_ge_k": nkeep,
        "spearman_ew": _r(rho_ew),
        "pearson_ew": _r(pear_ew),
        "spearman_vw": _r(rho_vw),
        "p_ew": _r(p_ew),
    }


def _r(x, nd=4):
    try:
        if x is None or not np.isfinite(x):
            return None
        return round(float(x), nd)
    except Exception:
        return None


def main():
    t0 = artifact.start_clock()
    a, b, n = load()
    coin = a["coin"]
    notional = a["notional"].astype(np.float64)
    taker = a["taker_id"]
    maker = a["maker_id"]

    res = {"n_rows": int(n), "by_coin": {}}
    print(f"Probe A1 print-vs-mid calibration | {n:,} rows")

    for c in sorted(np.unique(coin).tolist()):
        cname = COIN.get(c, str(c))
        cm = coin == c
        res["by_coin"][cname] = {"n": int(cm.sum()), "horizons": {}}
        print(f"\n=== {cname}  (n={int(cm.sum()):,}) ===")
        for h in HORIZONS:
            pv = a[f"mo{h}"].astype(np.float64)
            mv = b[f"mo{h}_mid"].astype(np.float64)
            m = cm & finite_mask(pv, mv)
            pvh, mvh = pv[m], mv[m]
            note = notional[m]
            tak, mak = taker[m], maker[m]
            nval = pvh.size
            # trade-level
            if nval >= 100:
                pear, _ = stats.pearsonr(pvh, mvh)
                spear, _ = stats.spearmanr(pvh, mvh)
            else:
                pear = spear = float("nan")
            # level inflation: how much bigger is the mid-markout level
            mean_print = float(np.average(pvh, weights=note)) if nval else float("nan")
            mean_mid = float(np.average(mvh, weights=note)) if nval else float("nan")
            lvl_ratio = (mean_mid / mean_print) if (nval and abs(mean_print) > 1e-9) else None
            hrec = {
                "n_valid": int(nval),
                "trade_pearson": _r(pear),
                "trade_spearman": _r(spear),
                "vw_mean_print_bps": _r(mean_print),
                "vw_mean_mid_bps": _r(mean_mid),
                "mid_over_print_level_ratio": _r(lvl_ratio),
                "taker_rank": {f"K{k}": cp_rank_corr(tak, pvh, mvh, note, k) for k in K_THRESH},
                "maker_rank": {f"K{k}": cp_rank_corr(mak, pvh, mvh, note, k) for k in K_THRESH},
            }
            res["by_coin"][cname]["horizons"][f"h{h}"] = hrec
            tk = hrec["taker_rank"]["K50"]
            mk = hrec["maker_rank"]["K50"]
            print(
                f"  h{h:>2}s: trade rho={hrec['trade_spearman']}  "
                f"lvl(mid/print)={hrec['mid_over_print_level_ratio']}  "
                f"| taker-rank K50 rho_ew={tk['spearman_ew']} (n={tk['n_counterparties_ge_k']})  "
                f"maker-rank K50 rho_ew={mk['spearman_ew']} (n={mk['n_counterparties_ge_k']})"
            )

    # verdict at 60s, taker-side, K50, EW
    verdict = {}
    for cname, cd in res["by_coin"].items():
        h60 = cd["horizons"].get("h60", {})
        rk = h60.get("taker_rank", {}).get("K50", {})
        verdict[cname] = rk.get("spearman_ew")
    res["verdict_taker_rank_spearman_h60_K50_ew"] = verdict
    res["interpretation"] = (
        "rank rho >= ~0.8 at 60s -> trade-print proxy preserves the per-counterparty "
        "toxicity RANKING -> wide panel (Aug/Oct/SOL/cross-section) usable for the "
        "decomposition. Lower -> restrict headline to Dec book-mid; print-panel = robustness."
    )

    # The scope names the fill floor as a LIST, because this probe reports the rank
    # agreement at three of them and no single one of the three is the file's answer.
    # It also names the rung the verdict is read at, which is 60 s and is not the
    # horizon the rest of the work scores at; the key carries that in its own name.
    days = np.unique(a["day"])
    artifact.write(
        os.path.basename(OUT_JSON), res,
        script=__file__, inputs=[IN_PRINT, IN_MID],
        scope={
            "population": (f"{n:,} row-aligned fills carried by both the trade-print "
                           f"and the book-mid file; the trade-level correlations use "
                           f"every row with a finite markout on both sides, and the "
                           f"per-counterparty rank correlations use wallets at the "
                           f"{K_THRESH} fill floors, taker side and maker side "
                           f"separately"),
            "window": (f"{days.size} days present in the input, day-of-month "
                       f"{days.min()}-{days.max()}; every rung of the declared ladder "
                       f"{HORIZONS} s is reported, and the headline verdict key is read "
                       f"at 60 s, which is the companion rung and not the "
                       f"{H.HEADLINE_HORIZON_S} s the work scores at"),
            "coins": [COIN.get(c, str(c)) for c in sorted(np.unique(coin).tolist())],
        },
        # h is the companion window, read from settings.py rather than typed: this
        # file reports every rung and its verdict key is taken at the companion one.
        settings={"h": H.COMPANION_HORIZON_S, "lens": "mid",
                  "rank_floor_fills": K_THRESH},
        started=t0, out_dir=os.path.dirname(OUT_JSON))
    print("\nVERDICT taker-rank Spearman @60s K50 EW:", verdict)
    print(f"wrote probes/{os.path.basename(OUT_JSON)}")


if __name__ == "__main__":
    main()
