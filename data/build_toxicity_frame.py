#!/usr/bin/env python3
"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-08-02
References: Hyperliquid node-data S3 archive (s3://hl-mainnet-node-data); Zenodo 18184441 (Albers et al. 2026).

THE COUNTERPARTY-TOXICITY TRAINING FRAME, BUILT BY A NAMED PRODUCER.

WHY, BEFORE HOW. A classifier of counterparty toxicity trains on one row per counterparty:
behaviour observed in an early window, a toxicity label taken from a disjoint later
window. That frame existed as a file with no producer. Three places named it -- the
model script, its README and the reproducing notebook -- and no script built it, so a
reader who cloned the repository could not rebuild the frame at all, and neither could
anyone checking the work. The classifier itself is not published in this repository;
the frame is, because it is built from the same panel as every other result here. A file nobody can rebuild is not a result; it is a copy.

It also sat on the wrong quantity, and that mattered more than the missing producer.
Its markout columns were the SIXTY-second markout taken against the TRADE PRINT, while
the headline of this work is the ten-second markout against the BOOK MID. Those are not
two readings of one number: a different window and a different price reference make a
different quantity, so the classifier was answering a question the rest of the paper does
not ask. The frame predates settings.HEADLINE_HORIZON_S by three weeks -- before that
declaration existed there was no single window for anything to agree with, and two parts
of the work drifted apart without anyone choosing it.

WHAT WAS MEASURED, NOT ASSUMED. The old frame's `mean_mo60_early` was tested against
four candidate columns over the wallets it shares with the panel: the ten-second book
mid correlates 0.4237, the sixty-second book mid 0.9910, the ten-second print 0.4329,
and the sixty-second print 1.0000 with identical medians to four places. So the column
held the sixty-second print, exactly as the classifier's own results file declared, and the
note in the notebook saying the value "is at the scoring window" and only the NAME
carries the 60 was wrong. That note is the dangerous kind: it tells a reader the naming
is cosmetic and so stops the check that would have caught it.

EVERY COLUMN IS NAMED FOR WHAT IT HOLDS. The markout columns take their name from
settings.headline_mid_col(), so a window change renames them and cannot leave a stale
number under a confident name. That is the whole reason the old naming could lie.

THE SPLIT. Days are sorted and cut in half: the earlier half carries the features, the
later half carries the label, and no fill contributes to both. The halves are reported
in the artifact rather than assumed by a reader.
"""

import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
# artifact.py, settings.py and the other shared modules sit in the
# repository root, one directory up from this group, so the path is built
# from this file's own location and never from the working directory the
# run happens to start in.
_CODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CODE_DIR not in sys.path:
    sys.path.insert(0, _CODE_DIR)

import artifact                     # noqa: E402
import panel_io as P                # noqa: E402
import settings as H                # noqa: E402

FRAME_NAME = "wallet_toxicity_frame.csv"
# Beside the notebook, which is where the file it replaces lived. The location is kept so
# that a classifier reading the frame from there needs no edit to find it -- only its
# feature list changes, because the columns are now named for the window they hold.
FRAME_DIR = os.path.join(_CODE_DIR, "notebooks")

COIN_NAME = H.COIN_SYMBOLS_BY_ARTIFACT.get("quickwin", {0: "BTC", 1: "ETH"}) \
    if hasattr(H, "COIN_SYMBOLS_BY_ARTIFACT") else {0: "BTC", 1: "ETH"}

SCORE_COL = H.headline_mid_col()          # e.g. "mo10_mid"
MO = SCORE_COL.replace("_mid", "")        # e.g. "mo10", for the column names below


def _group_mean(keys, vals):
    """Per-key mean over finite values. Returns (unique_keys, means, counts)."""
    ok = np.isfinite(vals)
    k, v = keys[ok], vals[ok]
    u, inv = np.unique(k, return_inverse=True)
    n = np.bincount(inv)
    s = np.bincount(inv, weights=v)
    return u, s / n, n


def _group_std(keys, vals, u, means):
    """Per-key population standard deviation, aligned to `u`."""
    ok = np.isfinite(vals)
    k, v = keys[ok], vals[ok]
    pos = np.searchsorted(u, k)
    n = np.bincount(pos, minlength=u.size)
    s2 = np.bincount(pos, weights=(v - means[pos]) ** 2, minlength=u.size)
    out = np.full(u.size, np.nan)
    nz = n > 0
    out[nz] = np.sqrt(s2[nz] / n[nz])
    return out


def build():
    started = artifact.start_clock()
    npz_path = P.panel_path("mid")
    z = np.load(npz_path, allow_pickle=False)

    taker = z["taker_id"].astype(np.int64)
    coin = z["coin"].astype(np.int8)
    day = z["day"].astype(np.int64)
    score = P.score(z, "mid")                       # the declared window and lens
    notional = z["notional"].astype(np.float64)
    imb = z["imb_entry"].astype(np.float64)
    start_pos = z["start_pos"].astype(np.float64)

    days = np.unique(day)
    half = days.size // 2
    early_days, late_days = days[:half], days[half:]
    early = np.isin(day, early_days)
    late = np.isin(day, late_days)

    rows = []
    for code in sorted(np.unique(coin).tolist()):
        cname = COIN_NAME.get(int(code), str(int(code)))
        me, ml = early & (coin == code), late & (coin == code)

        u_e, mean_e, n_e = _group_mean(taker[me], score[me])
        std_e = _group_std(taker[me], score[me], u_e, mean_e)
        # The three behaviour features share the early mask, so they are grouped on the
        # same wallets; a wallet with no finite score has no row at all, which is why
        # they are aligned to u_e rather than grouped independently.
        def aligned(vals):
            # vals arrives UNMASKED; the keys are already masked, so it must be masked
            # here or the boolean index below is taken over a different population.
            k, v = taker[me], vals[me]
            ok = np.isfinite(v)
            pos = np.searchsorted(u_e, k[ok])
            inside = (pos < u_e.size) & (u_e[np.minimum(pos, u_e.size - 1)] == k[ok])
            n = np.bincount(pos[inside], minlength=u_e.size)
            s = np.bincount(pos[inside], weights=v[ok][inside], minlength=u_e.size)
            out = np.full(u_e.size, np.nan)
            nz = n > 0
            out[nz] = s[nz] / n[nz]
            return out

        notl_e, imb_e, pos_e = aligned(notional), aligned(imb), aligned(start_pos)
        u_l, mean_l, _ = _group_mean(taker[ml], score[ml])
        late_by_taker = dict(zip(u_l.tolist(), mean_l.tolist()))

        for i, w in enumerate(u_e.tolist()):
            if w not in late_by_taker:
                continue                     # no label window: the row would be unusable
            lab = late_by_taker[w]
            rows.append((w, cname, int(n_e[i]), float(mean_e[i]), float(std_e[i]),
                         float(notl_e[i]), float(imb_e[i]), float(pos_e[i]),
                         lab, int(lab > 0.0)))

    header = ["wallet", "coin", "fills_early",
              f"mean_{MO}_mid_early", f"std_{MO}_mid_early",
              "mean_notional_early", "mean_imb_early", "mean_start_pos_early",
              f"label_{MO}_mid_late", "label_toxic_late"]

    os.makedirs(FRAME_DIR, exist_ok=True)
    out_csv = os.path.join(FRAME_DIR, FRAME_NAME)
    with open(out_csv, "w", encoding="utf-8") as fh:
        fh.write(",".join(header) + "\n")
        for r in rows:
            fh.write(",".join(str(x) for x in r) + "\n")
    print(f"[frame] wrote {len(rows):,} rows to notebooks/{FRAME_NAME}")

    pos_rate = float(np.mean([r[-1] for r in rows])) if rows else float("nan")
    payload = {
        "n_rows": len(rows),
        "columns": header,
        "score_column_in_panel": SCORE_COL,
        "positive_label_rate": pos_rate,
        "by_coin": {
            c: int(sum(1 for r in rows if r[1] == c))
            for c in sorted({r[1] for r in rows})
        },
        "label_definition": (
            f"label_toxic_late = 1 when the counterparty's mean {SCORE_COL} over the "
            "late half of the days is above zero. Cost-blind by construction: it counts "
            "wallets, not dollars, so a wallet doing one harmful fill and a wallet doing "
            "a thousand weigh the same. The continuous label in the column beside it is "
            "the economically meaningful target and is kept for that reason."
        ),
        "leakage_note": (
            "The day halves are disjoint, so no fill feeds both a feature and the label. "
            "That blocks label leakage and NOT counterparty leakage: a wallet appears in "
            "both halves by design, which is the whole point of the question, so any "
            "held-out evaluation must split on the wallet or on the coin."
        ),
        "why_this_window": (
            f"Named from settings.headline_mid_col(), so the column names move with the "
            f"declaration and cannot hold one window under another window's name. The "
            f"frame this replaces carried the 60 s TRADE-PRINT markout under names ending "
            f"mo60, which is a different quantity from the {H.HEADLINE_HORIZON_S} s book "
            f"mid this work reports on."
        ),
    }
    artifact.write(
        "toxicity_frame_results.json", payload,
        script=__file__,
        inputs=[npz_path],
        scope={
            "population": "one row per (counterparty, coin) with at least one finite "
                          "score in each half of the day range",
            "window": (f"features on days {early_days.min()}-{early_days.max()}, "
                       f"label on days {late_days.min()}-{late_days.max()}; the two "
                       f"halves are disjoint so no fill feeds both"),
            "early_days": [int(d) for d in early_days],
            "late_days": [int(d) for d in late_days],
            "coins": sorted(COIN_NAME.get(int(c), str(int(c)))
                            for c in np.unique(coin).tolist()),
            "lens": H.HEADLINE_LENS,
            "horizon_s": H.HEADLINE_HORIZON_S,
        },
        started=started,
    )
    return out_csv, len(rows)


if __name__ == "__main__":
    build()
