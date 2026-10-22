"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-21
Clean OUT-OF-TIME persistence of per-counterparty toxicity: TRAIN = Aug+Oct 2025,
TEST = Dec 2025 (months apart, not the messy within-month split the first EB used).
This is the load-bearing property for the taker analysis: does a wallet flagged toxic
on Aug+Oct stay toxic in Dec?

Also doubles as a DATA AUDIT for the four standing questions:
  - same data?  -> per-window fill / wallet counts (are the 3 windows comparable?)
  - correct?    -> cross-window wallet overlap (is the SAME address present across a
                   4-month gap with enough fills?)
  - enough?     -> power: how many wallets are scoreable in both windows + test-vol covered.

Metrics per coin/role: observed cross-window Spearman; method-of-moments reliabilities
(train, test); disattenuated correlation; EB out-of-time MSE (shrunk-train vs grand)
and forecast slope (test ~ shrunk-train). Read-only; light; foreground-safe.
"""
import os
import sys

import numpy as np
from scipy import stats

# The artifact module lives one directory up, so the path is built from this file's own
# location and never from the working directory the run happens to start in. `stats`
# here is SciPy's, not the repository's statistics module: this file draws nothing at
# random and runs none of the three procedures that module owns, so the two never meet
# and the name is left as SciPy's rather than shadowed.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import artifact  # noqa: E402
import panel_io as P  # noqa: E402
import settings as H  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CODE_DIR = os.path.dirname(HERE)
# Located by panel_io rather than joined here, so the one place that knows where the
# markout panels live is the one place that has to change if they move.
PANEL = os.path.join(P.data_root(), "panel_markouts.npz")
OUT_JSON = os.path.join(HERE, "persistence_crosswindow_results.json")
COIN = {0: "BTC", 1: "ETH", 2: "SOL"}
TRAIN = {202508, 202510}
TEST = {202512}
# The two floors this probe sweeps, READ from settings.py and never typed. A wallet
# enters a cell only with at least K fills in BOTH windows, so these are floors on a
# HALF and not the ranking-window floor RANK_FLOOR_FILLS declares. The declaration
# returns the same (20, 50) the published run swept; the list() keeps the type the
# artifact's scope sentence prints, so the sentence is unchanged character for character.
KS = list(H.wallet_fill_floor("persistence_crosswindow", "sweep"))


def wmean(x, w):
    return float(np.sum(w * x) / np.sum(w))


def wvar(x, w):
    mu = wmean(x, w)
    return float(np.sum(w * (x - mu) ** 2) / np.sum(w))


def agg(ids, y, n):
    cnt = np.bincount(ids, minlength=n).astype(np.float64)
    s = np.bincount(ids, weights=y, minlength=n)
    s2 = np.bincount(ids, weights=y * y, minlength=n)
    mean = np.where(cnt > 0, s / np.maximum(cnt, 1), np.nan)
    var = np.where(cnt > 1, np.maximum(s2 / np.maximum(cnt, 1) - mean ** 2, 0.0), np.nan)
    return cnt, mean, var


def role_persist(idraw, y, period, coin, c, role, K):
    sel = coin == c
    ids = np.unique(idraw[sel], return_inverse=True)[1]
    yy = y[sel]; per = period[sel]
    n = ids.max() + 1
    tr = np.isin(per, list(TRAIN)); te = np.isin(per, list(TEST))
    cT, mT, vT = agg(ids[tr], yy[tr], n)
    cE, mE, vE = agg(ids[te], yy[te], n)
    keep = (cT >= K) & (cE >= K)
    nk = int(keep.sum())
    if nk < 20:
        return {"coin": COIN.get(c, c), "role": role, "K": K, "n_both": nk, "note": "underpowered"}
    mTk, vTk, cTk = mT[keep], vT[keep], cT[keep]
    mEk, vEk, cEk = mE[keep], vE[keep], cE[keep]
    obs = float(stats.spearmanr(mTk, mEk).statistic)
    # MoM reliabilities
    def rel(mean, var, cnt):
        samp = wmean(var / np.maximum(cnt, 1), cnt)
        tau2 = max(wvar(mean, cnt) - samp, 0.0)
        return tau2, samp, (tau2 / (tau2 + samp) if (tau2 + samp) > 0 else 0.0)
    tau2T, sampT, relT = rel(mTk, vTk, cTk)
    _, _, relE = rel(mEk, vEk, cEk)
    disatt = obs / np.sqrt(relT * relE) if (relT > 0 and relE > 0) else float("nan")
    disatt = float(min(disatt, 1.0)) if np.isfinite(disatt) else None
    # EB out-of-time
    grand = wmean(mTk, cTk)
    B = tau2T / (tau2T + vTk / np.maximum(cTk, 1))
    shrunk = grand + B * (mTk - grand)
    mse_shrunk = wmean((mEk - shrunk) ** 2, cEk)
    mse_grand = wmean((mEk - grand) ** 2, cEk)
    slope = float(np.cov(shrunk, mEk)[0, 1] / max(np.var(shrunk), 1e-12))
    test_cov = float(cEk.sum() / cE.sum())
    return {
        "coin": COIN.get(c, c), "role": role, "K": K, "n_both": nk,
        "test_fill_coverage": round(test_cov, 4),
        "obs_spearman": round(obs, 4),
        "reliab_train": round(relT, 4), "reliab_test": round(relE, 4),
        "disattenuated": round(disatt, 4) if disatt is not None else None,
        "eb_mse_shrunk": round(mse_shrunk, 4), "eb_mse_grand": round(mse_grand, 4),
        "shrunk_beats_grand": bool(mse_shrunk <= mse_grand),
        "fc_slope": round(slope, 3),
    }


def main():
    t0 = artifact.start_clock()
    # panel_io names the producer to run when the file is absent, so that message
    # is written once for the whole tree; the load itself stays here because
    # build.py derives this script's input edge from the argument of np.load.
    P.require_present("panel", PANEL)
    d = np.load(PANEL, allow_pickle=True)
    period = d["period"].astype(np.int64)
    coin = d["coin"].astype(np.int64)
    # The COMPANION window, asked for by name rather than spelled. panel_io routes the
    # request through settings.companion_print_col(), which returns the same column this
    # line read when it was typed, so the substitution moves no number.
    score_col = P.score_col("panel", H.COMPANION_HORIZON_S)
    y = P.score(d, "panel", H.COMPANION_HORIZON_S)
    fin = np.isfinite(y)
    period, coin, y = period[fin], coin[fin], y[fin]
    taker = d["taker_id"][fin]; maker = d["maker_id"][fin]

    print(f"Probe / cross-window persistence | TRAIN=Aug+Oct, TEST=Dec | "
          f"{score_col} trade-print")
    # DATA AUDIT: per-window sizes
    audit = {}
    for p in sorted(np.unique(period).tolist()):
        mp = period == p
        audit[int(p)] = {"fills": int(mp.sum()),
                         "takers": int(np.unique(taker[mp]).size),
                         "makers": int(np.unique(maker[mp]).size)}
        print(f"  window {p}: fills={audit[int(p)]['fills']:,} "
              f"takers={audit[int(p)]['takers']:,} makers={audit[int(p)]['makers']:,}")

    out = {"audit_per_window": audit, "results": []}
    for role, idraw in (("taker", taker), ("maker", maker)):
        for c in sorted(np.unique(coin).tolist()):
            for K in KS:
                r = role_persist(idraw, y, period, coin, c, role, K)
                out["results"].append(r)
                if "obs_spearman" in r:
                    print(f"  {r['role']:5s} {r['coin']:4s} K{K:>3}: obs_rho={r['obs_spearman']} "
                          f"disatt={r['disattenuated']} relTr={r['reliab_train']} relTe={r['reliab_test']} "
                          f"| EB beats_grand={r['shrunk_beats_grand']} slope={r['fc_slope']} "
                          f"(n_both={r['n_both']}, testcov={r['test_fill_coverage']})")
                else:
                    print(f"  {r['role']:5s} {r['coin']} K{K}: {r['note']} (n={r['n_both']})")

    # The file holds two populations and they are not the same size, which is the thing
    # the scope has to say out loud. audit_per_window counts fills and wallets in EVERY
    # window the panel carries; the persistence numbers under "results" are computed on
    # three of them only, the two training windows against the one test window. A reader
    # who took the audit's window list for the result's window list would read a
    # ten-month claim off a four-month measurement.
    all_windows = sorted(int(p) for p in np.unique(period))
    used = sorted(TRAIN | TEST)
    n_used = int(np.isin(period, used).sum())
    scored = [r for r in out["results"] if "obs_spearman" in r]
    artifact.write(
        os.path.basename(OUT_JSON), out,
        script=__file__, inputs=[PANEL],
        scope={
            "population": (f"{n_used:,} of {int(y.size):,} finite-markout panel fills: "
                           f"those falling in the training or the test window. A wallet "
                           f"enters a cell only with at least K fills in BOTH, at the "
                           f"two floors {KS}, which leaves {len(scored)} of "
                           f"{len(out['results'])} role-coin-K cells estimable. The "
                           f"audit_per_window block is the exception and covers all "
                           f"{len(all_windows)} windows the panel carries"),
            "window": (f"train {sorted(TRAIN)} against test {sorted(TEST)}, months "
                       f"apart and out of time; the panel itself carries "
                       f"{len(all_windows)} windows, {all_windows[0]} to "
                       f"{all_windows[-1]}, and the remaining "
                       f"{len(all_windows) - len(used)} enter the audit block only"),
            "coins": [COIN.get(c, str(c)) for c in sorted(np.unique(coin).tolist())],
        },
        # h is the companion window, read from settings.py rather than typed, so the
        # window this artifact stamps and the column the run actually read cannot drift
        # apart. The value is the same 60 s it has always been.
        settings={"h": H.COMPANION_HORIZON_S, "lens": "print", "rank_floor_fills": KS},
        started=t0, out_dir=os.path.dirname(OUT_JSON))
    print(f"\nwrote probes/{os.path.basename(OUT_JSON)}")


if __name__ == "__main__":
    main()
