"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-21
Probe C2 — the decisive robustness for the maker>>taker finding: is the maker
fixed-effect just OBSERVABLE QUOTING STYLE (wide spread / extreme imbalance /
microprice deviation at the moment the maker is hit), or does it survive after
controlling for entry book state?

Method: on the Dec BTC+ETH book-mid file (the only one carrying entry book state),
(1) remove the common level (demean mo60_mid within coin x day),
(2) ALSO remove observable entry book state (regress on spread_entry_bps, imb_entry,
    micro_dev_bps), giving residual e,
(3) re-run the de-biased two-way decomposition on e and compare the de-biased
    Var(maker) and Var(taker) BEFORE vs AFTER the book-state control.
If Var(maker) barely moves -> the maker effect is NOT explained by observable book
state (real, beyond style). If it collapses -> it was quoting style.

Reuses the verified estimator from kss_decomp_c.py. Read-only; background-safe.
"""
import os
import sys

import numpy as np
from kss_decomp_c import split_correct

# artifact.py lives one directory up, so the path is built from this file's own location
# and never from the working directory the run happens to start in.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import artifact  # noqa: E402
import panel_io as P  # noqa: E402
import settings as H  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CODE_DIR = os.path.dirname(HERE)
# Located by panel_io rather than joined here, so the one place that knows where the
# markout panels live is the one place that has to change if they move.
MID = os.path.join(P.data_root(), "quickwin_markouts_mid.npz")
OUT_JSON = os.path.join(HERE, "c2_bookstate_control_results.json")
# int8 code -> symbol for the QUICKWIN space, which is the file this probe reads, asked
# for by artifact name rather than typed. The panel and the December quickwin artifact
# do not share a code space, so a map typed here would be right for one and wrong for
# the other without raising.
COIN = H.coin_labels("quickwin")
# The split-sample seed of the de-biased estimator, and NOT settings.MASTER_SEED. READ
# from settings.py, which declares 690 for this purpose, so the stream is the one every
# number in this file's results was drawn from and nothing moves. The value stays at 690
# deliberately: both arms below draw their split from it, and the whole result is a
# BEFORE-against-AFTER comparison of two de-biased variances, so the arms have to be
# drawn from the same stream. Rebinding it to MASTER_SEED would move both numbers and the
# ratio between them. It is stated as an override in the artifact fingerprint.
SEED = H.seed_for("c2_bookstate_control")


def demean_within(y, g):
    """remove group (coin x day) mean."""
    gm = np.bincount(g, weights=y, minlength=g.max() + 1) / np.maximum(
        np.bincount(g, minlength=g.max() + 1), 1)
    return y - gm[g]


def main():
    t0 = artifact.start_clock()
    # panel_io names the producer to run when the file is absent, so that message
    # is written once for the whole tree; the load itself stays here because
    # build.py derives this script's input edge from the argument of np.load.
    P.require_present("mid", MID)
    d = np.load(MID, allow_pickle=True)
    # The COMPANION window, asked for by name rather than spelled. panel_io routes the
    # request through settings.companion_mid_col(), which returns the same column this
    # line read when it was typed, so the substitution moves no number and the window
    # now follows the declaration instead of the keystroke.
    y = P.score(d, "mid", H.COMPANION_HORIZON_S)
    coin = d["coin"].astype(np.int64); day = d["day"].astype(np.int64)
    sp = d["spread_entry_bps"].astype(np.float64)
    imb = d["imb_entry"].astype(np.float64)
    mdev = d["micro_dev_bps"].astype(np.float64)
    fin = np.isfinite(y) & np.isfinite(sp) & np.isfinite(imb) & np.isfinite(mdev)
    y, coin, day, sp, imb, mdev = y[fin], coin[fin], day[fin], sp[fin], imb[fin], mdev[fin]
    t = np.unique(d["taker_id"][fin], return_inverse=True)[1]
    m = np.unique(d["maker_id"][fin], return_inverse=True)[1]
    g = np.unique(coin * 100 + day, return_inverse=True)[1]
    nT, nM, nG = t.max() + 1, m.max() + 1, g.max() + 1
    print(f"Probe C2 book-state control | {y.size:,} fills (finite book state) | "
          f"takers={nT:,} makers={nM:,}")

    # baseline: common removed only
    y0 = demean_within(y, g)
    base = split_correct(y0, t, m, g, nT, nM, nG, np.random.default_rng(SEED))
    print(f"  BASELINE (common removed): var_taker={base['var_alpha_debiased']} "
          f"var_maker={base['var_psi_debiased']}")

    # controlled: also remove observable entry book state (standardized linear)
    def z(x):
        s = x.std(); return (x - x.mean()) / (s if s > 0 else 1)
    X = np.column_stack([np.ones_like(y0), z(sp), z(imb), z(np.abs(imb)), z(mdev), z(np.abs(mdev))])
    beta, *_ = np.linalg.lstsq(X, y0, rcond=None)
    e = y0 - X @ beta
    r2 = 1 - np.var(e) / np.var(y0)
    ctrl = split_correct(e, t, m, g, nT, nM, nG, np.random.default_rng(SEED))
    print(f"  book-state R^2 of markout = {r2:.4f}")
    print(f"  CONTROLLED (common+book-state removed): var_taker={ctrl['var_alpha_debiased']} "
          f"var_maker={ctrl['var_psi_debiased']}")

    drop_m = 1 - ctrl["var_psi_debiased"] / max(base["var_psi_debiased"], 1e-9)
    drop_t = 1 - ctrl["var_alpha_debiased"] / max(base["var_alpha_debiased"], 1e-9)
    print(f"  maker var reduced by {drop_m*100:.1f}% ; taker var reduced by {drop_t*100:.1f}%")
    verdict = ("maker effect SURVIVES book-state control (real, beyond observable style)"
               if drop_m < 0.5 else
               "maker effect LARGELY explained by observable book state (quoting style)")
    print(f"  VERDICT: {verdict}")

    out = {"n_fills": int(y.size), "book_state_r2": round(float(r2), 4),
           "baseline": base, "controlled": ctrl,
           "maker_var_reduction": round(float(drop_m), 4),
           "taker_var_reduction": round(float(drop_t), 4), "verdict": verdict}
    # The population is narrower than the file it is read from, and by a stated amount:
    # only fills whose entry book state is finite can enter, because the controlled arm
    # regresses on that state. The count that survives is written into the scope rather
    # than left for a reader to work out from the input's row count.
    days = np.unique(day)
    artifact.write(
        os.path.basename(OUT_JSON), out,
        script=__file__, inputs=[MID],
        scope={
            "population": (f"{int(y.size):,} book-mid fills carrying a finite markout "
                           f"AND a finite entry spread, imbalance and microprice "
                           f"deviation, out of {int(d['coin'].size):,} rows in the "
                           f"input; {nT:,} takers and {nM:,} makers, no fill floor"),
            "window": (f"{days.size} days present in the input, day-of-month "
                       f"{days.min()}-{days.max()}; the calendar dates are declared by "
                       "the input's producer, build_quickwin_markouts.py"),
            "coins": [COIN.get(c, str(c)) for c in sorted(np.unique(coin).tolist())],
        },
        # h is stated as the companion window because that is the column this file
        # reads. Left unstated it would default to the declared headline of 10 s, and
        # the artifact would stamp is_headline_horizon true on numbers computed at the
        # companion window. It is read from settings.py rather than typed, so the stamp
        # and the column can no longer disagree.
        settings={"h": H.COMPANION_HORIZON_S, "lens": "mid", "master_seed": SEED},
        started=t0, out_dir=os.path.dirname(OUT_JSON))
    print(f"wrote probes/{os.path.basename(OUT_JSON)}")


if __name__ == "__main__":
    main()
