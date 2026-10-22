"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-21
Settling test for an estimability confound: makers average 313 fills/wallet vs 69 for
takers, so the maker FE is more precisely estimable. Re-run the de-biased two-way
decomposition on fills where BOTH the taker AND the maker have a GLOBAL fill count
in [50, 500] -> precision is matched across the two sides. If maker>>taker survives
at equal precision, the gap is not an estimability artifact. Reuses the verified
estimator. Read-only; background-safe.
"""
import os
import sys

import numpy as np
from kss_decomp_c import split_correct, decomp, solve_twoway

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
PANEL = os.path.join(P.data_root(), "panel_markouts.npz")
OUT_JSON = os.path.join(HERE, "c_matched_precision_results.json")
# int8 code -> symbol for the PANEL space, asked for by artifact name rather than typed.
# The two artifacts do not share a code space -- the panel carries three coins and the
# December quickwin file two -- so a map typed here would be right for one input and
# silently wrong for the other.
COIN = H.coin_labels("panel")
LO, HI = 50, 500
# The split-sample seed of the de-biased estimator. NOT settings.MASTER_SEED. READ from
# settings.py, which declares 690 for this purpose, so the split is the one every number
# in c_matched_precision_results.json was computed on and nothing moves. The value stays
# at 690 deliberately: binding it to MASTER_SEED would move the de-biased variances
# rather than merely rename their source. It is recorded as a stated override in the
# artifact's fingerprint, so the difference is visible in the file instead of being
# invisible in the code.
SEED = H.seed_for("c_matched_precision")


def main():
    t0 = artifact.start_clock()
    # panel_io names the producer to run when the file is absent, so that message
    # is written once for the whole tree; the load itself stays here because
    # build.py derives this script's input edge from the argument of np.load.
    P.require_present("panel", PANEL)
    d = np.load(PANEL, allow_pickle=True)
    # The COMPANION window, asked for by name rather than spelled. panel_io routes the
    # request through settings.companion_print_col(), which returns the same column this
    # line read when it was typed, so the substitution moves no number.
    y = P.score(d, "panel", H.COMPANION_HORIZON_S)
    coin = d["coin"].astype(np.int64); day = d["day"].astype(np.int64)
    period = d["period"].astype(np.int64)
    tk = d["taker_id"]; mk = d["maker_id"]
    fin = np.isfinite(y)
    y, coin, day, period, tk, mk = y[fin], coin[fin], day[fin], period[fin], tk[fin], mk[fin]

    ct = np.bincount(np.unique(tk, return_inverse=True)[1])
    cm = np.bincount(np.unique(mk, return_inverse=True)[1])
    ti0 = np.unique(tk, return_inverse=True)[1]
    mi0 = np.unique(mk, return_inverse=True)[1]
    keep = (ct[ti0] >= LO) & (ct[ti0] <= HI) & (cm[mi0] >= LO) & (cm[mi0] <= HI)
    print(f"matched-precision [{LO},{HI}] fills both sides: kept {keep.sum():,} / {y.size:,} "
          f"({keep.mean()*100:.1f}%)")

    t = np.unique(tk[keep], return_inverse=True)[1]
    m = np.unique(mk[keep], return_inverse=True)[1]
    gkey = period[keep] * 1000 + coin[keep] * 100 + day[keep]
    g = np.unique(gkey, return_inverse=True)[1]
    yy = y[keep]
    nT, nM, nG = t.max() + 1, m.max() + 1, g.max() + 1
    # mean fills/wallet now (should be similar)
    print(f"  takers={nT:,} (avg {keep.sum()/nT:.0f} fills) makers={nM:,} (avg {keep.sum()/nM:.0f} fills)")

    a, p, mu, it, dl = solve_twoway(yy, t, m, g, nT, nM, nG)
    pin = decomp(yy, a, p, mu, t, m, g)
    spl = split_correct(yy, t, m, g, nT, nM, nG, np.random.default_rng(SEED))
    print(f"  PLUG-IN: taker={pin['share_taker_alpha']} maker={pin['share_maker_psi']}")
    print(f"  SPLIT (de-biased): taker={spl['share_taker_alpha']} maker={spl['share_maker_psi']} "
          f"(var_taker={spl['var_alpha_debiased']} var_maker={spl['var_psi_debiased']})")
    ratio = spl["var_psi_debiased"] / max(spl["var_alpha_debiased"], 1e-9)
    print(f"  maker/taker variance ratio at matched precision = {ratio:.1f}x")
    verdict = ("maker>>taker SURVIVES at matched precision (fully REAL, not estimability)"
               if ratio > 2 else "gap shrinks at matched precision (was partly precision)")
    print(f"  VERDICT: {verdict}")

    out = {"window": [LO, HI], "kept_fills": int(keep.sum()),
           "plugin": pin, "split": spl, "maker_taker_var_ratio": round(float(ratio), 2),
           "verdict": verdict}
    # The top-level key "window" holds the FILL-COUNT band [50, 500], not a calendar
    # span. It keeps its name so no number moves under a reader who already quotes it,
    # but the calendar window now sits beside it under its own name in the scope block,
    # where a reader looking for dates will find dates.
    periods = sorted(int(p) for p in np.unique(period[keep]))
    artifact.write(
        os.path.basename(OUT_JSON), out,
        script=__file__, inputs=[PANEL],
        scope={
            "population": (f"{int(keep.sum()):,} of {int(y.size):,} finite-markout panel "
                           f"fills: those where the taker AND the maker each have a "
                           f"GLOBAL panel fill count in [{LO}, {HI}], which is what "
                           f"matches estimation precision across the two sides; "
                           f"{nT:,} takers and {nM:,} makers survive the band"),
            "window": (f"{len(periods)} monthly windows pooled, {periods[0]} to "
                       f"{periods[-1]}; grouping is period x coin x day"),
            "coins": [COIN.get(c, str(c))
                      for c in sorted(np.unique(coin[keep]).tolist())],
        },
        # h is stated as the companion window because that is the column this file
        # reads. Left unstated it would default to the declared headline of 10 s, and
        # the artifact would stamp is_headline_horizon true on numbers computed at the
        # companion window -- a false statement in the very block a reader consults to
        # check the file. It is read from settings.py rather than typed, so the stamp
        # and the column can no longer disagree.
        settings={"h": H.COMPANION_HORIZON_S, "lens": "print", "master_seed": SEED},
        started=t0, out_dir=os.path.dirname(OUT_JSON))
    print(f"wrote probes/{os.path.basename(OUT_JSON)}")


if __name__ == "__main__":
    main()
