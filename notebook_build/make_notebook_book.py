"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-08-10
References: Hyperliquid market-data L2 book S3 archive
  (s3://hyperliquid-archive/market_data); Zenodo 18184441 (Albers, Cucuringu,
  Howison, Shestopaloff, "An Open Book", 2026).

Pack the shipped order-book series the reproducibility notebook downloads.

The notebook already receives the mid series (mid, micro, spread, imb, t_ms, written
by i4_l2_mid.py). What it could not receive until now is the order-book feature block
the identity-versus-book comparison runs on, so that comparison was the one reported
result a reader could read but not recompute. This packer joins the two on the book
clock and writes one compressed file per coin.

What travels, and why it is this list and not another. The comparison node states its
own feature list in book_feature_names(), and that list is imported here rather than
retyped, so the shipped block cannot drift away from the block the published figure
was measured on. Two of its ten names are not shipped, because they are already
recoverable to the last bit from columns the mid series has always carried:

  micro_dev_bps  equals (micro - mid) / mid * 1e4, deviation exactly 0
  qimb_5         equals imb, deviation 4.44e-16

Shipping either one would put a single quantity in two places under two names, which
is the arrangement that lets two copies of one number drift apart. Both identities are
re-measured here on every run and the packer refuses to write if either stops holding,
so the notebook may derive them instead of carrying them.

The remaining eight are shipped in single precision. That is a width, not a rounding
choice made here: the notebook consumes each feature through a mean over a wallet's
early fills, and against the scale of each feature the worst error that width can
introduce sits in the seventh significant digit. Half precision is not admissible and
is not offered, because it moves the fourth digit of published figures.

The shipped copy is deliberately NOT called mid_series_{COIN}.npz, which is the name of
the working series this packer reads. They are different files now: the working one holds
five arrays, the shipped one thirteen. A reader running the notebook from the repository
root would otherwise be handed the five-array file by name and get a refusal, and the
freshness gate resolves a declared input by basename before it resolves it by content, so
one name over two files is a hazard in two places at once.

The book clock is not resampled and no row is dropped, so the notebook does its own
as-of join at read time. That matters for what the comparison claims: the objection to
"the public book does not recover what identity gives" is "you read the book at the
wrong instant", and a reader can only answer it by doing the join themselves.

Run: uv run --no-project --with-requirements requirements.txt python3 make_notebook_book.py
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
# The shared modules sit in the repository root, one directory up from this
# group, and this file also imports from the identity group. Both are built from this
# file's own location and never from the working directory the run happens to
# start in.
_CODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_CODE_DIR, os.path.join(_CODE_DIR, "identity")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import artifact  # noqa: E402
import panel_io as P  # noqa: E402
import settings as H  # noqa: E402
from i3_book_comparator import book_feature_names  # noqa: E402

# Read rather than retyped, for the same reason the feature list above is imported: the
# coins this packer covers are the coins of the L2 cache the two inputs are cut from, and
# a literal here would be a second home for that fact and free to drift from the first.
COINS = H.coin_symbols("l2_cache")

# Recoverable from the mid series the notebook already holds; see the module docstring.
DERIVED = ("micro_dev_bps", "qimb_5")

# The mid-series columns that travel unchanged.
MID_COLS = ("t_ms", "mid", "micro", "spread", "imb")

OUT_DIR = os.path.join(_CODE_DIR, "notebooks")
OUT_META = os.path.join(OUT_DIR, "notebook_book_meta.json")


def _require(path, why):
    if not os.path.exists(path):
        sys.exit(f"ERROR: missing {os.path.basename(path)} ({why}).")


def main():
    t0 = artifact.start_clock()
    names = list(book_feature_names())
    ship = [n for n in names if n not in DERIVED]
    if len(ship) + len(DERIVED) != len(names):
        sys.exit(f"ERROR: {DERIVED} are not all in book_feature_names() = {names}.")

    os.makedirs(OUT_DIR, exist_ok=True)
    inputs, per_coin, checks = [], {}, {}

    for coin in COINS:
        # Both are written under the declared data root by their producers, which sit
        # in other groups now; this packer only reads them.
        src_mid = os.path.join(P.data_root(), f"mid_series_{coin}.npz")
        src_bk = os.path.join(P.data_root(), f"book_feats_{coin}.npz")
        _require(src_mid, "the L2 mid series, written by i4_l2_mid.py")
        _require(src_bk, "the order-book feature block the comparison runs on")
        inputs += [src_mid, src_bk]

        m = np.load(src_mid)
        b = np.load(src_bk)

        # One clock or no file. The two are written by different producers on different
        # days, so a silent misalignment here would put every feature one snapshot away
        # from the price it is read beside, and nothing downstream would notice.
        if m["t_ms"].shape != b["t_ms"].shape:
            sys.exit(f"ERROR: {coin} clock lengths differ, "
                     f"mid {m['t_ms'].shape} against book {b['t_ms'].shape}.")
        if not np.array_equal(m["t_ms"], b["t_ms"]):
            d = np.flatnonzero(m["t_ms"] != b["t_ms"])
            sys.exit(f"ERROR: {coin} clocks differ at {d.size} of {m['t_ms'].size} "
                     f"snapshots, first at index {d[0]}: mid {m['t_ms'][d[0]]} "
                     f"against book {b['t_ms'][d[0]]}.")

        # The two identities that buy the right not to ship two of the ten. Measured
        # every run rather than asserted once, because the moment either stops holding
        # the notebook would be deriving a different feature under the right name.
        mid, micro = m["mid"].astype(np.float64), m["micro"].astype(np.float64)
        dev_micro = float(np.max(np.abs(
            b["micro_dev_bps"].astype(np.float64) - (micro - mid) / mid * 1e4)))
        dev_qimb = float(np.max(np.abs(
            b["qimb_5"].astype(np.float64) - m["imb"].astype(np.float64))))
        if dev_micro > 1e-9 or dev_qimb > 1e-12:
            sys.exit(f"ERROR: {coin} derived-feature identity broke; the notebook is "
                     f"told it may rebuild micro_dev_bps and qimb_5 from the mid "
                     f"series, and that is no longer true. micro_dev_bps deviates by "
                     f"{dev_micro:.3e} (tolerated 1e-9), qimb_5 by {dev_qimb:.3e} "
                     f"(tolerated 1e-12). Ship all ten, or find why they moved.")
        checks[coin] = {"micro_dev_bps_max_abs": dev_micro,
                        "qimb_5_max_abs": dev_qimb}

        out = {k: m[k] for k in MID_COLS}
        out.update({n: b[n].astype(np.float32) for n in ship})
        dst = os.path.join(OUT_DIR, f"notebook_book_{coin}.npz")
        np.savez_compressed(dst, **out)

        per_coin[coin] = {
            "file": os.path.basename(dst),
            "n_snapshots": int(m["t_ms"].size),
            "t_ms_span_days": round(
                float(m["t_ms"].max() - m["t_ms"].min()) / 86_400_000, 2),
            "columns": {k: str(v.dtype) for k, v in out.items()},
            "sha256": artifact.sha256_file(dst),
            "size_mb": round(os.path.getsize(dst) / 1e6, 1),
        }
        print(f"wrote {dst} ({per_coin[coin]['size_mb']} MB, "
              f"{per_coin[coin]['n_snapshots']:,} snapshots, {len(out)} columns)")
        print(f"  sha256 {per_coin[coin]['sha256']}")

    meta = {
        "object": "The order-book series the reproducibility notebook downloads: the "
                  "L2 mid series unchanged, plus the feature block the identity-"
                  "versus-book comparison is measured on, on the book clock and "
                  "un-resampled so the notebook performs its own as-of join.",
        "author": "Dmitry Stakhin",
        "companion_files": ["notebook_fills.npz"],
        "feature_list_source": "i3_book_comparator.book_feature_names(), imported "
                               "rather than retyped",
        "features_declared": names,
        "features_shipped": ship,
        "features_derived_by_the_notebook": {
            "micro_dev_bps": "(micro - mid) / mid * 1e4",
            "qimb_5": "imb",
        },
        "derived_identity_max_abs_deviation": checks,
        "precision": "the eight shipped features are float32; the mid-series columns "
                     "keep the width they were written at",
        "coins": per_coin,
        "doi": "10.5281/zenodo.23540388",
        "zenodo_url": "https://zenodo.org/records/23540388/files/"
                      "notebook_book_{COIN}.npz?download=1",
    }
    artifact.write(
        os.path.basename(OUT_META), meta, script=__file__, inputs=inputs,
        scope={"population": f"{sum(v['n_snapshots'] for v in per_coin.values()):,} "
                             f"order-book snapshots across "
                             f"{len(COINS)} coins, un-resampled",
               "window": "December 2025",
               "coins": list(COINS)},
        started=t0, out_dir=OUT_DIR)
    print(f"wrote {OUT_META}")


if __name__ == "__main__":
    main()
