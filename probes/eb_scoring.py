"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-21
Probe C stage 3 — Empirical-Bayes per-counterparty toxicity SCORING under low
reliability, with out-of-sample temporal validation. References:
Morris (1983) JASA 78:47-65; Chetty-Friedman-Rockoff (2014) AER 104(9);
Kane-Staiger (2008) NBER w14607.

For each role (taker = aggressor, maker = provider) and each coin, shrink each
entity's RAW mean markout toward a per-coin prior with weight B_i = tau2/(tau2+s_i2)
(tau2 = signal variance via method-of-moments; s_i2 = sampling var = within/n_i).
Whales (big n) keep their score; noisy small wallets collapse to the prior -> exactly
the tail behaviour wanted. OOS check: estimate on EARLY days, predict LATE days;
shrunk score must beat raw mean AND the grand mean (MSE), and the late-on-shrunk
slope should be ~1 (forecast unbiasedness). Read-only; light. Background-safe.
"""
import os
import sys

import numpy as np

# artifact.py and settings.py live one directory up, so the path is built from this
# file's own location and never from the working directory the run happens to start in.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import artifact  # noqa: E402
import panel_io as P  # noqa: E402
import settings as H  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CODE_DIR = os.path.dirname(HERE)
# Located by panel_io rather than joined here, so the one place that knows where the
# markout panels live is the one place that has to change if they move.
PANEL = os.path.join(P.data_root(), "panel_markouts.npz")
OUT_JSON = os.path.join(HERE, "eb_scoring_results.json")
COIN = {0: "BTC", 1: "ETH", 2: "SOL"}
EARLY_MAX_DAY = 8     # early = days <= 8, late = days >= 9 (pooled over coin/period)
# Minimum fills in BOTH halves for a wallet to be scored, READ from settings.py. It is
# 30 there and it was 30 here, so no reliability and no out-of-sample MSE below moves.
# The declaration it reads is deliberately not RANK_FLOOR_FILLS, which is 50: that floor
# is on the RANKING window and this one is on a HALF, so they are two quantities rather
# than one setting at two values. The gap stays legible as an override in the artifact's
# fingerprint.
KMIN = H.wallet_fill_floor("eb_scoring", "both_halves")


def wmean(x, w):
    return float(np.sum(w * x) / np.sum(w))


def wvar(x, w):
    mu = wmean(x, w)
    return float(np.sum(w * (x - mu) ** 2) / np.sum(w))


def role_eb(idraw, y, day, coin, c, role):
    sel = coin == c
    ids = np.unique(idraw[sel], return_inverse=True)[1]
    yy = y[sel]; dd = day[sel]
    nE = ids.max() + 1
    early = dd <= EARLY_MAX_DAY
    late = ~early

    def agg(mask):
        i = ids[mask]; v = yy[mask]
        cnt = np.bincount(i, minlength=nE).astype(np.float64)
        s = np.bincount(i, weights=v, minlength=nE)
        s2 = np.bincount(i, weights=v * v, minlength=nE)
        mean = np.where(cnt > 0, s / np.maximum(cnt, 1), np.nan)
        var = np.where(cnt > 1, s2 / np.maximum(cnt, 1) - mean ** 2, np.nan)
        return cnt, mean, np.maximum(var, 0.0)

    cE, mE, vE = agg(early)
    cL, mL, _ = agg(late)
    keep = (cE >= KMIN) & (cL >= KMIN)
    nkeep = int(keep.sum())
    if nkeep < 20:
        return {"coin": COIN.get(c, c), "role": role, "n_scored": nkeep, "note": "too few"}

    cEk, mEk, vEk, cLk, mLk = cE[keep], mE[keep], vE[keep], cL[keep], mL[keep]
    grand = wmean(mEk, cEk)                       # per-coin prior (fill-weighted early)
    s2 = vEk / np.maximum(cEk, 1)                 # sampling var of each early mean
    between = wvar(mEk, cEk)
    mean_samp = wmean(s2, cEk)
    tau2 = max(between - mean_samp, 0.0)          # method-of-moments signal var
    B = tau2 / (tau2 + s2)
    shrunk = grand + B * (mEk - grand)
    reliability = tau2 / (tau2 + mean_samp) if (tau2 + mean_samp) > 0 else 0.0

    # OOS (predict late), entity-weighted by late fills
    def mse(pred):
        return wmean((mLk - pred) ** 2, cLk)
    mse_shrunk = mse(shrunk); mse_raw = mse(mEk); mse_grand = mse(np.full_like(mLk, grand))
    # forecast-unbiasedness slope: late ~ a + b*shrunk
    b_slope = float(np.cov(shrunk, mLk)[0, 1] / max(np.var(shrunk), 1e-12))

    return {
        "coin": COIN.get(c, c), "role": role, "n_scored": nkeep,
        "tau2": round(tau2, 4), "reliability": round(reliability, 4),
        "mean_B_shrinkage": round(float(np.average(B, weights=cEk)), 4),
        "mse_shrunk": round(mse_shrunk, 4), "mse_raw": round(mse_raw, 4),
        "mse_grand": round(mse_grand, 4),
        "shrunk_beats_raw": bool(mse_shrunk <= mse_raw),
        "shrunk_beats_grand": bool(mse_shrunk <= mse_grand),
        "fc_slope_late_on_shrunk": round(b_slope, 3),
    }


def main():
    t0 = artifact.start_clock()
    # panel_io names the producer to run when the file is absent, so that message
    # is written once for the whole tree; the load itself stays here because
    # build.py derives this script's input edge from the argument of np.load.
    P.require_present("panel", PANEL)
    d = np.load(PANEL, allow_pickle=True)
    coin = d["coin"].astype(np.int64)
    day = d["day"].astype(np.int64)
    # The COMPANION window, asked for by name rather than spelled. panel_io routes the
    # request through settings.companion_print_col(), which returns the same column this
    # line read when it was typed, so the substitution moves no number.
    score_col = P.score_col("panel", H.COMPANION_HORIZON_S)
    y = P.score(d, "panel", H.COMPANION_HORIZON_S)
    fin = np.isfinite(y)
    coin, day, y = coin[fin], day[fin], y[fin]
    taker = d["taker_id"][fin]; maker = d["maker_id"][fin]
    print(f"Probe C / EB scoring | {score_col} trade-print | early day<={EARLY_MAX_DAY}, "
          f"late day>={EARLY_MAX_DAY + 1} | KMIN={KMIN}")

    out = {"early_max_day": EARLY_MAX_DAY, "kmin": KMIN, "results": []}
    for role, idraw in (("taker", taker), ("maker", maker)):
        for c in sorted(np.unique(coin).tolist()):
            r = role_eb(idraw, y, day, coin, c, role)
            out["results"].append(r)
            if "tau2" in r:
                print(f"  {r['role']:5s} {r['coin']:4s}: tau2={r['tau2']} reliab={r['reliability']} "
                      f"shrink={r['mean_B_shrinkage']} | MSE shrunk={r['mse_shrunk']} raw={r['mse_raw']} "
                      f"grand={r['mse_grand']}  beats_raw={r['shrunk_beats_raw']} "
                      f"beats_grand={r['shrunk_beats_grand']} slope={r['fc_slope_late_on_shrunk']} "
                      f"(n={r['n_scored']})")
            else:
                print(f"  {r['role']:5s} {r['coin']}: {r['note']} (n={r['n_scored']})")

    # The early/late split is pooled over coin AND period, so the window this probe
    # covers is every monthly window the panel carries and not one of them. Read here
    # only to say so; the period column enters no computation above, and a reader who
    # met "early days 4-8" without this sentence would take the split for a single month.
    periods = sorted(int(p) for p in np.unique(d["period"]))
    days = np.unique(day)
    n_scored = sum(int(r.get("n_scored", 0)) for r in out["results"])
    artifact.write(
        os.path.basename(OUT_JSON), out,
        script=__file__, inputs=[PANEL],
        scope={
            "population": (f"{int(y.size):,} panel fills with a finite markout; a "
                           f"wallet enters a cell only with at least {KMIN} fills in "
                           f"BOTH halves, which leaves {n_scored:,} scored wallet-cells "
                           f"summed over the two roles and every coin"),
            "window": (f"{len(periods)} monthly windows POOLED, {periods[0]} to "
                       f"{periods[-1]}, each contributing day-of-month "
                       f"{days.min()}-{days.max()}; early is day <= {EARLY_MAX_DAY} and "
                       f"late is the rest, taken inside every window at once"),
            "coins": [COIN.get(c, str(c)) for c in sorted(np.unique(coin).tolist())],
        },
        # h is stated as the companion window because that is the column this file
        # reads. Left unstated it would default to the declared headline of 10 s, and
        # the artifact would stamp is_headline_horizon true on numbers computed at the
        # companion window. It is read from settings.py rather than typed, so the stamp
        # and the column can no longer disagree.
        settings={"h": H.COMPANION_HORIZON_S, "lens": "print",
                  "rank_floor_fills": KMIN},
        started=t0, out_dir=os.path.dirname(OUT_JSON))
    print(f"\nwrote probes/{os.path.basename(OUT_JSON)}")


if __name__ == "__main__":
    main()
