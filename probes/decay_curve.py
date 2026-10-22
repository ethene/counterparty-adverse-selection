"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-22
Toxicity persistence DECAY CURVE over Aug 2025 -> May 2026 (8 windows).
v2: reports the RAW OBSERVED Spearman (estimator-free, robust primary) AND a
split-half-reliability disattenuation that is CONSISTENT with KS2 (Spearman-Brown),
so the within-window point is directly comparable to the prior ~0.5 KS2 number.
This resolves the v1 inconsistency (v1 used method-of-moments reliability, which
disagreed with KS2's split-half). Read-only; foreground-safe.

gaps: intra (~5d, early days 4-8 vs late 9-13 within a window) + cross-window 1..9 months.
"""
import os
import sys

import numpy as np
from scipy import stats

# The settings and artifact modules live one directory up, so the path is built from
# this file's own location and never from the working directory the run happens to start
# in. `stats` here is SciPy's, not the repository's statistics module: the two would
# collide under one name, and this file's only draw is the split-half coin toss below,
# which is not one of the three procedures that module owns.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import artifact  # noqa: E402
import panel_io as P  # noqa: E402
import settings as H  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CODE_DIR = os.path.dirname(HERE)
# Located by panel_io rather than joined here, so the one place that knows where the
# markout panels live is the one place that has to change if they move.
PANEL = os.path.join(P.data_root(), "panel_markouts.npz")
OUT_JSON = os.path.join(HERE, "decay_curve_results.json")
COIN = {0: "BTC", 1: "ETH", 2: "SOL"}
KMIN = H.RANK_FLOOR_FILLS   # min fills for a window's per-wallet mean to be a
                            # measurement of that wallet; the declared floor, which is
                            # the value this probe already ran on
MONTH_IDX = {202508: 0, 202509: 1, 202510: 2, 202511: 3, 202512: 4,
             202601: 5, 202603: 7, 202605: 9}


def agg(ids, y, n):
    cnt = np.bincount(ids, minlength=n).astype(np.float64)
    s = np.bincount(ids, weights=y, minlength=n)
    mean = np.where(cnt > 0, s / np.maximum(cnt, 1), np.nan)
    return cnt, mean


def splithalf_reliability(ids, y, n, rng, kmin):
    """Spearman-Brown reliability of a window's per-entity mean (KS2 method)."""
    h = rng.random(y.size) < 0.5
    c1, m1 = agg(ids[h], y[h], n)
    c2, m2 = agg(ids[~h], y[~h], n)
    keep = (c1 >= kmin / 2) & (c2 >= kmin / 2)
    if keep.sum() < 25:
        return float("nan")
    r = stats.spearmanr(m1[keep], m2[keep]).statistic
    if not np.isfinite(r) or r <= -1:
        return float("nan")
    return 2 * r / (1 + r)  # Spearman-Brown full-length


def pair(idsA, yA, idsB, yB, n, rng):
    cA, mA = agg(idsA, yA, n)
    cB, mB = agg(idsB, yB, n)
    keep = (cA >= KMIN) & (cB >= KMIN)
    nk = int(keep.sum())
    if nk < 25:
        return None
    obs = float(stats.spearmanr(mA[keep], mB[keep]).statistic)
    relA = splithalf_reliability(idsA, yA, n, rng, KMIN)
    relB = splithalf_reliability(idsB, yB, n, rng, KMIN)
    if relA > 0 and relB > 0 and np.isfinite(relA) and np.isfinite(relB):
        dis = min(obs / np.sqrt(relA * relB), 1.0)
    else:
        dis = None
    return {"obs": round(obs, 4),
            "disatt_SB": round(dis, 4) if dis is not None else None,
            "relA": round(relA, 3) if np.isfinite(relA) else None,
            "relB": round(relB, 3) if np.isfinite(relB) else None,
            "n": nk}


def main():
    t0 = artifact.start_clock()
    # panel_io names the producer to run when the file is absent, so that message
    # is written once for the whole tree; the load itself stays here because
    # build.py derives this script's input edge from the argument of np.load.
    P.require_present("panel", PANEL)
    d = np.load(PANEL, allow_pickle=True)
    period = d["period"].astype(np.int64); coin = d["coin"].astype(np.int64)
    # The COMPANION window, asked for by name rather than spelled. panel_io routes the
    # request through settings.companion_print_col(), which returns the same column this
    # line read when it was typed, so the substitution moves no number.
    day = d["day"].astype(np.int64); y = P.score(d, "panel", H.COMPANION_HORIZON_S)
    fin = np.isfinite(y)
    period, coin, day, y = period[fin], coin[fin], day[fin], y[fin]
    taker = d["taker_id"][fin]
    periods = sorted(np.unique(period).tolist())
    # The split-half coin toss. The seed is NOT settings.MASTER_SEED and the VALUE is
    # left alone: one generator is threaded through every window pair below, so every
    # reliability and every disattenuated point in this file's results is a successive
    # state of this one stream. Rebinding it to the declared seed would move the whole
    # curve. What changed on 2026-07-31 is where the value is read from, not what it is:
    # seed_for("decay_curve") returns the same 690 this probe has always drawn, shared
    # with the seven other probes. It is stated as an override in the fingerprint.
    rng = np.random.default_rng(H.seed_for("decay_curve"))
    print(f"decay curve v2 | periods {periods} | KMIN={KMIN} | obs (robust) + SB-disatt (KS2-consistent)")

    curve = {}
    # intra (~5d): early(4-8) vs late(9-13) within each window
    for p in periods:
        for c in sorted(np.unique(coin).tolist()):
            sel = (period == p) & (coin == c)
            ids = np.unique(taker[sel], return_inverse=True)[1]
            yy = y[sel]; dd = day[sel]; n = ids.max() + 1
            e = dd <= 8; l = dd >= 9
            r = pair(ids[e], yy[e], ids[l], yy[l], n, rng)
            if r:
                curve.setdefault("intra_~5d", []).append((COIN[c], p, r))
    # cross-window: every ordered pair, gap in months
    for i, pa in enumerate(periods):
        for pb in periods[i + 1:]:
            gap = MONTH_IDX[pb] - MONTH_IDX[pa]
            for c in sorted(np.unique(coin).tolist()):
                sa = (period == pa) & (coin == c); sb = (period == pb) & (coin == c)
                allid = np.concatenate([taker[sa], taker[sb]])
                base, inv = np.unique(allid, return_inverse=True)
                na = int(sa.sum())
                r = pair(inv[:na], y[sa], inv[na:], y[sb], base.size, rng)
                if r:
                    curve.setdefault(f"{gap}mo", []).append((COIN[c], f"{pa}->{pb}", r))

    out = {"periods": periods, "kmin": KMIN, "by_gap": {}}
    order = ["intra_~5d"] + sorted((k for k in curve if k != "intra_~5d"),
                                   key=lambda s: int(s[:-2]))
    print("\ngap        med_OBS  med_disattSB   med_reliab   n_est")
    for gap in order:
        rows = [r for _, _, r in curve[gap]] if gap == "intra_~5d" else [r for _, _, r in curve[gap]]
        obs = [r["obs"] for r in rows]
        dis = [r["disatt_SB"] for r in rows if r["disatt_SB"] is not None]
        rel = [r["relA"] for r in rows if r["relA"] is not None] + \
              [r["relB"] for r in rows if r["relB"] is not None]
        mo = round(float(np.median(obs)), 4) if obs else None
        md = round(float(np.median(dis)), 4) if dis else None
        mr = round(float(np.median(rel)), 3) if rel else None
        out["by_gap"][gap] = {"median_obs": mo, "median_disatt_SB": md,
                              "median_reliability": mr, "n_estimates": len(obs),
                              "detail": [{"coin": x[0], "pair": x[1], **x[2]} for x in curve[gap]]}
        print(f"  {gap:9s}  {mo}    {md}        {mr}      {len(obs)}")

    n_est = sum(v["n_estimates"] for v in out["by_gap"].values())
    days = np.unique(day)
    artifact.write(
        os.path.basename(OUT_JSON), out,
        script=__file__, inputs=[PANEL],
        scope={
            "population": (f"{int(y.size):,} panel fills with a finite markout, "
                           f"aggregated to per-wallet means; a wallet enters a pair "
                           f"only with at least {KMIN} fills on BOTH sides of the gap, "
                           f"and a pair is reported only with at least 25 such wallets, "
                           f"which leaves {n_est} correlation estimates over "
                           f"{len(out['by_gap'])} gap buckets"),
            "window": (f"{len(periods)} monthly windows, {periods[0]} to "
                       f"{periods[-1]}, each contributing day-of-month "
                       f"{days.min()}-{days.max()}; the intra-window gap is early days "
                       f"up to 8 against late days from 9, and the cross-window gaps "
                       f"run 1 to 9 months"),
            "coins": [COIN.get(c, str(c)) for c in sorted(np.unique(coin).tolist())],
        },
        # h is the companion window, read from settings.py rather than typed, so the
        # window this artifact stamps and the column the run actually read cannot drift
        # apart. The value is the same 60 s it has always been.
        settings={"h": H.COMPANION_HORIZON_S, "lens": "print", "master_seed": 690,
                  "rank_floor_fills": KMIN},
        started=t0, out_dir=os.path.dirname(OUT_JSON))
    print(f"\nwrote probes/{os.path.basename(OUT_JSON)}")


if __name__ == "__main__":
    main()
