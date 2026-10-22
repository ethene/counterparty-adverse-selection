"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-21
Probe C robustness — re-run the two-way decomposition against the INDEPENDENT
book-mid markout (Dec BTC+ETH, l2Book reference) to confirm the maker>>taker
finding is not a trade-print artifact. Reuses the verified estimator from
kss_decomp_c.py. Read-only; heavy-ish; run in background.
"""
import os
import sys

import numpy as np
from kss_decomp_c import run_ref, planted_sim  # verified estimator + checks

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
OUT_JSON = os.path.join(HERE, "kss_decomp_c_bookmid_results.json")
# int8 code -> symbol for the QUICKWIN space, which is the file this probe reads, asked
# for by artifact name rather than typed. The panel and the December quickwin artifact
# do not share a code space, so a map typed here would be right for one and wrong for
# the other without raising.
COIN = H.coin_labels("quickwin")
# The split-sample seed of the de-biased estimator, offset per arm below. NOT
# settings.MASTER_SEED. READ from settings.py, which declares 690 for this purpose, so
# every de-biased variance in this file's results still comes off the same streams. The
# value stays at 690: rebinding it to MASTER_SEED would move the numbers rather than
# rename their source. Recorded as an override in the artifact's fingerprint.
SEED = H.seed_for("kss_decomp_c_bookmid")


def main():
    t0 = artifact.start_clock()
    # panel_io names the producer to run when the file is absent, so that message
    # is written once for the whole tree; the load itself stays here because
    # build.py derives this script's input edge from the argument of np.load.
    P.require_present("mid", MID)
    d = np.load(MID, allow_pickle=True)
    coin = d["coin"].astype(np.int64)
    day = d["day"].astype(np.int64)
    t = np.unique(d["taker_id"], return_inverse=True)[1]
    m = np.unique(d["maker_id"], return_inverse=True)[1]
    g = np.unique(coin * 100 + day, return_inverse=True)[1]  # all Dec -> coin x day
    nT, nM, nG = t.max() + 1, m.max() + 1, g.max() + 1
    print(f"Probe C BOOK-MID | {t.size:,} fills | takers={nT:,} makers={nM:,} groups={nG}")

    out = {"n_fills": int(t.size), "n_takers": int(nT), "n_makers": int(nM)}
    print("\n===== planted-signal correctness (book-mid graph) =====")
    sim = planted_sim(t, m, g, nT, nM, nG, np.random.default_rng(SEED + 1))
    out["planted_sim"] = sim
    print(f"  planted Va={sim['planted']['Va']} -> plug-in {sim['plugin_var_alpha']} | "
          f"split {sim['split_var_alpha']}  ::  {sim['VERDICT']}")

    # BOTH RUNGS COME FROM THE DECLARATIONS AND NOT FROM A TYPED PAIR, and the column
    # names come from the same place. That is what makes the horizon this artifact
    # stamps below honest: move either declaration and the column this run reads moves
    # with it, where a typed pair would leave the stamp naming one window while the run
    # read another, silently. The companion window runs FIRST because the fingerprint
    # carries a single horizon field and gives it the rung this file's maker-against-
    # taker finding is quoted at; the headline rung is the robustness arm. Asking
    # settings.py for the column name also refuses, by name, a window the input has no
    # column for, rather than failing later on a missing key.
    rungs = (H.COMPANION_HORIZON_S, H.HEADLINE_HORIZON_S)
    cols = [H.headline_mid_col(h) for h in rungs]

    for h, col in zip(rungs, cols):
        y = d[col].astype(np.float64)
        fin = np.isfinite(y)
        out[col] = run_ref(y[fin], t[fin], m[fin], g[fin], nT, nM, nG,
                           np.random.default_rng(SEED + h),
                           f"{col} (book-mid, {h}s, Dec BTC+ETH)")

    # Both rungs of the ladder are reported, so the scope says both rather than letting
    # the headline one stand for the file. The artifact carries a block per rung under
    # its own key, and the scope below names the rungs by reading the same two lists the
    # loop ran, so a text saying two windows cannot outlive the windows it describes.
    days = np.unique(day)
    artifact.write(
        os.path.basename(OUT_JSON), out,
        script=__file__, inputs=[MID],
        scope={
            "population": (f"{int(t.size):,} book-mid fills, every row of the input; "
                           f"{int(nT):,} takers and {int(nM):,} makers over {int(nG)} "
                           f"coin x day groups, with no fill floor. The de-biased "
                           f"variances are reported at BOTH the {rungs[0]} s and the "
                           f"{rungs[1]} s rung, under keys {cols[0]} and {cols[1]}"),
            "window": (f"{days.size} days present in the input, day-of-month "
                       f"{days.min()}-{days.max()}; the calendar dates are declared by "
                       "the input's producer, build_quickwin_markouts.py"),
            "coins": [COIN.get(c, str(c)) for c in sorted(np.unique(coin).tolist())],
        },
        # The fingerprint holds ONE horizon field and this file reports two rungs, so
        # the field is given the rung the loop ran first, which is the companion window
        # and the one the maker-against-taker finding is quoted at; the other rung is
        # the robustness arm and is named in the scope above. Left unstated the field
        # would default to the declared headline window and stamp is_headline_horizon
        # true on both. The field is the very object the loop iterated, not a second
        # reading of the declaration, so the window this artifact stamps and the column
        # the run read cannot drift apart. The lens is typed because it is a property of
        # the input file this probe opens, the book-mid panel, and not of a declaration:
        # a change of the declared headline lens would not move this file's input.
        settings={"h": rungs[0], "lens": "mid", "master_seed": SEED},
        started=t0, out_dir=os.path.dirname(OUT_JSON))
    print(f"\nwrote probes/{os.path.basename(OUT_JSON)}")


if __name__ == "__main__":
    main()
