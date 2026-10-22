"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-21
References: Abowd, Kramarz & Margolis (1999) Econometrica 67(2):251-333;
           Kline, Saggio & Solvsten (2020) Econometrica 88(5):1859-1898
           (DOI 10.3982/ECTA16410); Bonhomme-Lamadon-Manresa (2019). Internal:
           data_acquisition_log.md verified field semantics; connected_set_b1 (gate).

PROBE C (decomposition) — two-way (taker x maker) fixed-effects variance
decomposition of per-fill adverse selection (markout), with a SAMPLE-SPLIT
leave-out correction (the transparent analog of the KSS leave-out; full JLA-KSS
is a further refinement).

Model, per fill f:   y_f = mu_{coin x day}(f) + alpha_{taker}(f) + psi_{maker}(f) + eps_f
  y      = markout in bps (mo60 primary; trade-print reference, full panel).
  alpha  = taker (aggressor) effect = persistent per-counterparty toxicity (the
           CEX-impossible idiosyncratic object this study measures).
  psi    = maker (liquidity-provider) effect = which makers get systematically
           picked off (a bonus object).
  mu     = coin x day common/systematic adverse-selection level.

Reports Var shares of: common(mu), taker(alpha), maker(psi), 2*Cov(alpha,psi),
residual. Two estimates side by side:
  PLUG-IN   = naive OLS two-way FE variance (UPWARD biased by limited mobility).
  SPLIT     = sample-split cross-half covariance (de-biased: noise in the two
              random halves is independent, so only true signal survives).
  The gap PLUG-IN - SPLIT = the limited-mobility bias (a reportable number).

Validation built in: (1) planted-signal simulation on the REAL wallet graph with
KNOWN variances -> plug-in must over-state, split must recover; (2) maker-label
placebo -> split maker share must collapse to ~0; (3) whale-drop robustness.

Heavy numpy: run in background. Writes JSON + prints a summary. Read-only on data.
"""
import os
import sys

import numpy as np

# artifact.py lives one directory up, so the path is built from this file's own location
# and never from the working directory the run happens to start in. Two other probes
# import the estimator from this file, so the insert has to work whichever of the three
# is the one being launched.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import artifact  # noqa: E402
import settings as H  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CODE_DIR = os.path.dirname(HERE)
PANEL = os.path.join(CODE_DIR, "panel_markouts.npz")
OUT_JSON = os.path.join(HERE, "kss_decomp_c_results.json")
COIN = {0: "BTC", 1: "ETH", 2: "SOL"}
# The split-sample and placebo seed, offset per arm below, and NOT settings.MASTER_SEED.
# Its VALUE is left alone on purpose: every de-biased variance and every placebo share
# this file reports was drawn from these streams, and two other probes import this
# module's estimator and pass their own generator into it, so 690 is the identity of the
# draw rather than a default. What changed is only where the 690 is read from -- the
# declaration under this file's own purpose name, which is a different declaration from
# MASTER_SEED and holds the same value. Recorded as an override in the artifact's
# fingerprint, which is still true: the override is against MASTER_SEED.
SEED = H.seed_for("kss_decomp_c")


# ----------------------------------------------------------------------------- solver
def solve_twoway(y, t, m, g, nT, nM, nG, max_iter=800, tol=1e-5):
    """OLS two-way FE via alternating projections (Gauss-Seidel).
    t,m,g = contiguous 0-based codes. Returns (alpha, psi, mu, niter, delta).
    alpha/psi recentered to mean 0 each step (variances are normalization-invariant;
    recentering only keeps the iteration from drifting and makes halves comparable)."""
    ct = np.maximum(np.bincount(t, minlength=nT), 1).astype(np.float64)
    cm = np.maximum(np.bincount(m, minlength=nM), 1).astype(np.float64)
    cg = np.maximum(np.bincount(g, minlength=nG), 1).astype(np.float64)
    a = np.zeros(nT); p = np.zeros(nM); mu = np.zeros(nG)
    delta = np.nan
    for it in range(max_iter):
        a2 = np.bincount(t, weights=y - p[m] - mu[g], minlength=nT) / ct
        p2 = np.bincount(m, weights=y - a2[t] - mu[g], minlength=nM) / cm
        mu2 = np.bincount(g, weights=y - a2[t] - p2[m], minlength=nG) / cg
        am, pm = a2.mean(), p2.mean()
        a2 -= am; p2 -= pm; mu2 += am + pm
        delta = max(np.abs(a2 - a).max(), np.abs(p2 - p).max(), np.abs(mu2 - mu).max())
        a, p, mu = a2, p2, mu2
        if delta < tol:
            break
    return a, p, mu, it + 1, float(delta)


def decomp(y, a, p, mu, t, m, g):
    """Fill-level plug-in variance decomposition into shares of Var(y)."""
    af, pf, gf = a[t], p[m], mu[g]
    vy = float(np.var(y))
    va, vp, vg = float(np.var(af)), float(np.var(pf)), float(np.var(gf))
    cap = float(np.cov(af, pf)[0, 1])
    resid = y - af - pf - gf
    vr = float(np.var(resid))
    return {
        "var_y": round(vy, 4),
        "share_common_mu": round(vg / vy, 4),
        "share_taker_alpha": round(va / vy, 4),
        "share_maker_psi": round(vp / vy, 4),
        "share_2cov_alpha_psi": round(2 * cap / vy, 4),
        "share_residual": round(vr / vy, 4),
        "corr_alpha_psi": round(cap / np.sqrt(max(va * vp, 1e-12)), 4),
        "_raw": {"var_alpha": round(va, 4), "var_psi": round(vp, 4),
                 "cov": round(cap, 4), "var_common": round(vg, 4), "var_resid": round(vr, 4)},
    }


def split_correct(y, t, m, g, nT, nM, nG, rng):
    """Sample-split cross-half covariance: de-biased Var(alpha), Var(psi), Cov."""
    half = rng.random(y.size) < 0.5
    aA, pA, _, itA, dA = solve_twoway(y[half], t[half], m[half], g[half], nT, nM, nG)
    aB, pB, _, itB, dB = solve_twoway(y[~half], t[~half], m[~half], g[~half], nT, nM, nG)
    # takers/makers present in BOTH halves
    cTa = np.bincount(t[half], minlength=nT); cTb = np.bincount(t[~half], minlength=nT)
    cMa = np.bincount(m[half], minlength=nM); cMb = np.bincount(m[~half], minlength=nM)
    bothT = (cTa > 0) & (cTb > 0)
    bothM = (cMa > 0) & (cMb > 0)
    nfull = np.bincount(t, minlength=nT).astype(np.float64)  # fill weights
    mfull = np.bincount(m, minlength=nM).astype(np.float64)

    def wcov(x, y_, w, keep):
        w = w[keep]; x = x[keep]; y_ = y_[keep]
        W = w.sum()
        mx = (w * x).sum() / W; my = (w * y_).sum() / W
        return float((w * (x - mx) * (y_ - my)).sum() / W)

    var_a = wcov(aA, aB, nfull, bothT)   # unbiased fill-weighted Var(alpha_true)
    var_p = wcov(pA, pB, mfull, bothM)   # unbiased Var(psi_true)
    # cross term: alpha from A, psi from B (independent noise) over fills in both sets
    keepf = bothT[t] & bothM[m]
    af = aA[t[keepf]]; pf = pB[m[keepf]]
    cov_ap = float(np.mean(af * pf) - af.mean() * pf.mean())
    vy = float(np.var(y))
    return {
        "coverage_fills": round(float(keepf.mean()), 4),
        "var_alpha_debiased": round(var_a, 4),
        "var_psi_debiased": round(var_p, 4),
        "cov_debiased": round(cov_ap, 4),
        "share_taker_alpha": round(var_a / vy, 4),
        "share_maker_psi": round(var_p / vy, 4),
        "share_2cov": round(2 * cov_ap / vy, 4),
        "iters": [itA, itB], "deltas": [round(dA, 6), round(dB, 6)],
    }


# ----------------------------------------------------------------------------- checks
def planted_sim(t, m, g, nT, nM, nG, rng, Va=4.0, Vp=2.0, Ve=80.0):
    """Generate y with KNOWN variances on the REAL graph; check recovery."""
    astar = rng.normal(0, np.sqrt(Va), nT)
    pstar = rng.normal(0, np.sqrt(Vp), nM)
    y = astar[t] + pstar[m] + rng.normal(0, np.sqrt(Ve), t.size)
    a, p, mu, _, _ = solve_twoway(y, t, m, g, nT, nM, nG)
    pin = decomp(y, a, p, mu, t, m, g)["_raw"]
    spl = split_correct(y, t, m, g, nT, nM, nG, rng)
    return {
        "planted": {"Va": Va, "Vp": Vp, "Ve": Ve},
        "plugin_var_alpha": pin["var_alpha"], "plugin_var_psi": pin["var_psi"],
        "split_var_alpha": spl["var_alpha_debiased"], "split_var_psi": spl["var_psi_debiased"],
        "VERDICT": ("PASS: split recovers planted (plug-in over-states)"
                    if abs(spl["var_alpha_debiased"] - Va) < 0.35 * Va
                    and pin["var_alpha"] > spl["var_alpha_debiased"]
                    else "CHECK: recovery off"),
    }


def placebo_maker(y, t, m, g, nT, nM, nG, rng):
    """Shuffle which maker each fill is assigned (preserves counts, breaks identity).
    True maker signal is destroyed -> split maker share must collapse to ~0."""
    mperm = rng.permutation(m)
    a, p, mu, _, _ = solve_twoway(y, t, mperm, g, nT, nM, nG)
    pin = decomp(y, a, p, mu, t, mperm, g)
    spl = split_correct(y, t, mperm, g, nT, nM, nG, rng)
    return {"plugin_share_maker": pin["share_maker_psi"],
            "split_share_maker": spl["share_maker_psi"]}


def whale_drop(y, t, m, g, nT, nM, nG, rng, k=10):
    """Drop top-k takers and top-k makers by fill count; re-decompose (split)."""
    ct = np.bincount(t, minlength=nT); cm = np.bincount(m, minlength=nM)
    drop_t = set(np.argsort(ct)[::-1][:k].tolist())
    drop_m = set(np.argsort(cm)[::-1][:k].tolist())
    keep = ~(np.isin(t, list(drop_t)) | np.isin(m, list(drop_m)))
    tt, mm, gg, yy = t[keep], m[keep], g[keep], y[keep]
    # refactor
    tt = np.unique(tt, return_inverse=True)[1]
    mm = np.unique(mm, return_inverse=True)[1]
    gg = np.unique(gg, return_inverse=True)[1]
    spl = split_correct(yy, tt, mm, gg, tt.max() + 1, mm.max() + 1, gg.max() + 1, rng)
    return {"dropped_top_k": k, "kept_fill_share": round(float(keep.mean()), 4),
            "split_share_taker": spl["share_taker_alpha"],
            "split_share_maker": spl["share_maker_psi"]}


# ----------------------------------------------------------------------------- main
def run_ref(y, t, m, g, nT, nM, nG, rng, label):
    print(f"\n########## {label} ##########")
    a, p, mu, it, dl = solve_twoway(y, t, m, g, nT, nM, nG)
    print(f"  solver: {it} iters, delta={dl:.2e}")
    pin = decomp(y, a, p, mu, t, m, g)
    print(f"  PLUG-IN shares: common={pin['share_common_mu']} taker={pin['share_taker_alpha']} "
          f"maker={pin['share_maker_psi']} 2cov={pin['share_2cov_alpha_psi']} "
          f"resid={pin['share_residual']} (corr a,p={pin['corr_alpha_psi']})")
    spl = split_correct(y, t, m, g, nT, nM, nG, rng)
    print(f"  SPLIT (de-biased) shares: taker={spl['share_taker_alpha']} "
          f"maker={spl['share_maker_psi']} 2cov={spl['share_2cov']} "
          f"(coverage={spl['coverage_fills']})")
    plc = placebo_maker(y, t, m, g, nT, nM, nG, rng)
    print(f"  PLACEBO maker (shuffled): plug-in maker share={plc['plugin_share_maker']} "
          f"-> split maker share={plc['split_share_maker']} (should be ~0)")
    wd = whale_drop(y, t, m, g, nT, nM, nG, rng, k=10)
    print(f"  WHALE-DROP top10: taker share {spl['share_taker_alpha']}->{wd['split_share_taker']} "
          f"maker {spl['share_maker_psi']}->{wd['split_share_maker']} "
          f"(kept {wd['kept_fill_share']})")
    return {"plugin": pin, "split": spl, "placebo_maker": plc, "whale_drop": wd,
            "solver": {"iters": it, "delta": dl}}


def main():
    t0 = artifact.start_clock()
    # The panel is an intermediate the repository does not carry: absent in a fresh
    # clone by design, not by fault. Without this line the probe dies inside np.load
    # with a traceback that names neither the file nor the command that writes it.
    if not os.path.exists(PANEL):
        raise SystemExit(
            f"[kss] refusing to run: {os.path.basename(PANEL)} is not on disk. It is "
            f"an intermediate the repository does not carry, and it is written by "
            f"data/panel_persistence.py. Build it with: "
            f"python3 data/panel_persistence.py --build")
    d = np.load(PANEL, allow_pickle=True)
    coin = d["coin"].astype(np.int64)
    day = d["day"].astype(np.int64)
    period = d["period"].astype(np.int64)
    t = np.unique(d["taker_id"], return_inverse=True)[1]
    m = np.unique(d["maker_id"], return_inverse=True)[1]
    gkey = period * 1000 + coin * 100 + day
    g = np.unique(gkey, return_inverse=True)[1]
    nT, nM, nG = t.max() + 1, m.max() + 1, g.max() + 1
    rng = np.random.default_rng(SEED)
    print(f"Probe C | panel {t.size:,} fills | takers={nT:,} makers={nM:,} groups(coinxday)={nG}")

    out = {"n_fills": int(t.size), "n_takers": int(nT), "n_makers": int(nM), "n_groups": int(nG)}

    # correctness sim FIRST (on the real graph)
    print("\n===== planted-signal correctness check =====")
    sim = planted_sim(t, m, g, nT, nM, nG, np.random.default_rng(SEED + 1))
    out["planted_sim"] = sim
    print(f"  planted Va={sim['planted']['Va']} -> plug-in {sim['plugin_var_alpha']} | "
          f"split {sim['split_var_alpha']}  ::  {sim['VERDICT']}")
    print(f"  planted Vp={sim['planted']['Vp']} -> plug-in {sim['plugin_var_psi']} | "
          f"split {sim['split_var_psi']}")

    # BOTH WINDOWS ARE ASKED FOR, NOT SPELLED. Four lines below used to name the panel
    # column and the output key as the bare literals "mo60" and "mo10". A column name IS
    # the window -- it fixes the horizon exactly as firmly as a constant would -- and no
    # search for the word "horizon" finds it, which is the defect
    # checks/chk_headline_horizon.py exists to catch. Both names now come from
    # settings.py: companion_print_col() returns "mo60" and headline_print_col() returns
    # "mo10" today, so this reads the same two columns, writes the same two keys, and
    # moves no number. What it buys is that the two windows can no longer drift apart
    # from the declaration, and that the disagreement recorded in that gate -- this file
    # calls 60 s its primary outcome while the repository declares the headline to be
    # 10 s -- is now legible in the code rather than hidden inside a string.
    companion_col = H.companion_print_col()
    headline_col = H.headline_print_col()

    # primary outcome: the companion window, trade-print, full panel
    y60 = d[companion_col].astype(np.float64)
    fin = np.isfinite(y60)
    out[companion_col] = run_ref(
        y60[fin], t[fin], m[fin], g[fin], nT, nM, nG,
        np.random.default_rng(SEED + 2),
        f"{companion_col} (trade-print, {H.COMPANION_HORIZON_S}s, FULL PANEL)")

    # robustness horizon: the declared headline window
    y10 = d[headline_col].astype(np.float64)
    fin = np.isfinite(y10)
    out[headline_col] = run_ref(
        y10[fin], t[fin], m[fin], g[fin], nT, nM, nG,
        np.random.default_rng(SEED + 3),
        f"{headline_col} (trade-print, {H.HEADLINE_HORIZON_S}s, FULL PANEL)")

    # Both rungs are reported and the scope says so, because the two keys mo60 and mo10
    # are not a headline and a footnote here: the file runs the same estimator twice and
    # a reader quoting one of them has to know which window it is.
    periods = sorted(int(p) for p in np.unique(period))
    days = np.unique(day)
    artifact.write(
        os.path.basename(OUT_JSON), out,
        script=__file__, inputs=[PANEL],
        scope={
            "population": (f"{int(t.size):,} panel fills, every row of the input; "
                           f"{int(nT):,} takers and {int(nM):,} makers over {int(nG)} "
                           f"period x coin x day groups, no fill floor. The de-biased "
                           f"decomposition is reported at BOTH rungs, under the keys "
                           f"{companion_col} and {headline_col}, each on its own "
                           f"finite-markout subset"),
            "window": (f"{len(periods)} monthly windows pooled, {periods[0]} to "
                       f"{periods[-1]}, each contributing day-of-month "
                       f"{days.min()}-{days.max()}"),
            "coins": [COIN.get(c, str(c)) for c in sorted(np.unique(coin).tolist())],
        },
        # The fingerprint holds ONE horizon field and this file reports two rungs, so
        # the field is given the COMPANION window, the rung the file itself calls the
        # primary outcome; the headline rung is its robustness arm and is named in the
        # scope above. Left unstated the field would default to the declared headline,
        # which would stamp is_headline_horizon true on a file whose primary number is
        # at the longer window. Taken from the declaration rather than typed, for the
        # reason given at the two column names above; it returns the 60 that stood here.
        settings={"h": H.COMPANION_HORIZON_S, "lens": "print", "master_seed": SEED},
        started=t0, out_dir=os.path.dirname(OUT_JSON))
    print(f"\nwrote probes/{os.path.basename(OUT_JSON)}")


if __name__ == "__main__":
    main()
