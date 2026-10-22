"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-07-10
References: Hyperliquid node-data S3 archive (s3://hl-mainnet-node-data); Hyperliquid
  L2-book archive (s3://hyperliquid-archive/market_data); Zenodo 18184441 (Albers,
  Cucuringu, Howison, Shestopaloff, "An Open Book", 2026).

Build the raw-ish per-fill file the reproducibility notebook recomputes from.

The notebook no longer reads a slice with markout precomputed. Instead it downloads
this per-fill file plus the order-book series (notebook_book_BTC.npz /
notebook_book_ETH.npz, packed by make_notebook_book.py out of the working series
i4_l2_mid.py writes) and RECOMPUTES the book-mid markout and the order-book features
itself, with a no-lookahead as-of join. So the shipped inputs carry no derived markout
for the book branch; only the raw ingredients travel.

notebook_fills.npz holds, per collapsed trade (2,480,267 rows, BTC+ETH, Dec 4-13):
  block_time_ms  the native node clock (epoch-ms) the markout join uses
  entry_px       the trade price
  taker_side     1 buy / 0 sell by the aggressor
  coin, day      market and day
  notional       size in dollars
  start_pos      the aggressor's signed position before the trade
  is_open        1 opens/adds, 0 closes
  taker_code     pseudonymous counterparty code (re-indexed, address map not shipped)
  maker_code     pseudonymous resting-wallet code
  mo1/mo10/mo60  the trade-print markout, carried as a committed column (its only
                 difference from a live recompute is an economically-null
                 within-block print-tie ordering, so the notebook uses this column)
  closed_pnl     the realised profit the fill closes out, zero on a fill that opens
                 or adds; carried because the counterparty's own profit ranks wallets
                 differently from the maker's cost, and that divergence is a reported
                 result the notebook has to be able to recompute

The codes are pseudonyms, not anonymised identifiers. They are re-indexed contiguous
integers and hold no address information on their own, and the hex-to-id address map
stays unpublished, so the linkage between a code and an on-chain address is not
distributed from here. Re-deriving it remains open to a reader: the public source
data carry the same fills with their addresses -- the Hyperliquid node data the fills
were built from, and the open deposit of the same trades by Albers et al. (Zenodo
18184441) -- so codes can be matched back on coin, timestamp, price and size. That follows from the source
being open, not from anything this builder does.

The per-fill fields come from the gitignored intermediate quickwin_markouts.npz
(build_quickwin_markouts.py); the native block_time_ns is carried through the panel
rebuild (panel_rebuild_v2.py, December BTC+ETH shards) and converted once to ms.

Run: uv run --no-project --with-requirements ../requirements.txt python3 make_notebook_fills.py
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

# The one place that writes a results file and stamps what produced it. The hash of a
# file's bytes comes from there too, so this builder no longer carries its own copy of
# the chunked reader.
import artifact  # noqa: E402
import panel_io as P  # noqa: E402

# Located by panel_io rather than joined here, so the one place that knows where the
# markout panels live is the one place that has to change if they move.
QW = os.path.join(P.data_root(), "quickwin_markouts.npz")
SHARD = {0: os.path.join(P.data_root(), "panel_ckpt_v2", "shard_BTC_202512.npz"),
         1: os.path.join(P.data_root(), "panel_ckpt_v2", "shard_ETH_202512.npz")}
OUT_NPZ = os.path.join(_CODE_DIR, "notebooks", "notebook_fills.npz")
OUT_META = os.path.join(_CODE_DIR, "notebooks", "notebook_fills_meta.json")


def main():
    t0 = artifact.start_clock()
    # The refusal is panel_io's, so a missing panel is worded the same way everywhere and
    # the message names the producer that writes it. It also replaces a message that
    # interpolated the FULL path: it is absolute at run time, so the old wording put the
    # local account name of whoever ran it into the console and into any log that
    # captured it. panel_io prints the basename and its parent's basename only. The shard
    # check below keeps its own message, because a checkpoint shard is not a panel.
    P.require_present("print", QW)
    z = np.load(QW)
    coin = z["coin"]
    n = coin.size

    # native block_time (ns) per fill, from the December panel shards, keyed by coin.
    # The shard rows are the same collapsed trades in the same order as the print
    # intermediate; assert that alignment on the shared columns before trusting it.
    block_time_ms = np.empty(n, np.int64)
    for c, path in SHARD.items():
        if not os.path.exists(path):
            sys.exit(f"ERROR: missing {path} (needed for the native block_time clock).")
        s = np.load(path)
        m = coin == c
        for k in ("day", "entry_px", "notional", "taker_side"):
            a = z[k][m].astype(np.float64)
            b = s[k].astype(np.float64)
            if a.shape != b.shape or not np.allclose(a, b, atol=1e-4, equal_nan=True):
                sys.exit(f"ERROR: shard alignment failed for coin {c} on '{k}'.")
        block_time_ms[m] = (s["block_time_ns"] // 1_000_000).astype(np.int64)

    # re-index counterparty and maker ids to contiguous pseudonymous codes.
    # np.unique(return_inverse) is grouping-invariant, so every per-wallet result is
    # unchanged; the hex address map (quickwin_taker_map.json) stays unpublished, so
    # the linkage is not distributed from here, though a reader holding the open
    # source tape can re-derive it.
    _, taker_code = np.unique(z["taker_id"], return_inverse=True)
    _, maker_code = np.unique(z["maker_id"], return_inverse=True)

    out = dict(
        block_time_ms=block_time_ms,
        entry_px=z["entry_px"].astype(np.float64),
        taker_code=taker_code.astype(np.int32),
        maker_code=maker_code.astype(np.int32),
        coin=coin.astype(np.int8),
        day=z["day"].astype(np.int16),
        notional=z["notional"].astype(np.float32),
        taker_side=z["taker_side"].astype(np.int8),
        start_pos=z["start_pos"].astype(np.float32),
        is_open=z["is_open"].astype(np.int8),
        mo1=z["mo1"].astype(np.float32),
        mo10=z["mo10"].astype(np.float32),
        mo60=z["mo60"].astype(np.float32),
        # Appended after mo60 rather than placed beside the other per-fill fields, so
        # the thirteen columns that shipped before keep their bytes and a reader can
        # diff the two releases column by column. The source column is already f32, so
        # nothing is lost here: the width is the source's, not a choice made now.
        closed_pnl=z["closed_pnl"].astype(np.float32),
    )
    os.makedirs(os.path.dirname(OUT_NPZ), exist_ok=True)
    np.savez_compressed(OUT_NPZ, **out)

    meta = {
        "object": "Raw-ish per-fill inputs for the reproducibility notebook; the "
                  "notebook recomputes markout and book features from these plus "
                  "the L2 mid series, so no markout is precomputed here.",
        "author": "Dmitry Stakhin",
        "companion_files": ["notebook_book_BTC.npz", "notebook_book_ETH.npz"],
        "window": {"coins": ["BTC", "ETH"], "days_dec2025": [4, 13]},
        "n_rows": int(n),
        "n_takers": int(taker_code.max() + 1),
        "n_makers": int(maker_code.max() + 1),
        "deidentified": "taker_code and maker_code are pseudonyms, re-indexed "
                        "contiguous integers; the hex address map is not shipped, so "
                        "the linkage to on-chain addresses is not distributed here, "
                        "but a reader holding the public source data can re-derive it, "
                        "because the Hyperliquid node data the fills were built from, "
                        "and the open deposit of the same trades by Albers et al. "
                        "(Zenodo 18184441), carry the same fills with their addresses",
        "columns": {k: str(v.dtype) for k, v in out.items()},
        "sha256": artifact.sha256_file(OUT_NPZ),
        "size_mb": round(os.path.getsize(OUT_NPZ) / 1e6, 1),
        "doi": "10.5281/zenodo.23540388",
        "zenodo_url": "https://zenodo.org/records/23540388/files/notebook_fills.npz?download=1",
    }
    # What the shipped file covers. Stated rather than inferred, and the day span is
    # read off the column the file actually carries rather than repeated from the
    # window literal above, so the two cannot drift apart in silence.
    day_lo, day_hi = int(out["day"].min()), int(out["day"].max())
    artifact.write(
        os.path.basename(OUT_META), meta, script=__file__,
        inputs=[QW] + [SHARD[c] for c in sorted(SHARD)],
        scope={"population": (f"{n:,} collapsed taker trades, one per (block hash, "
                              f"taker), carrying {int(taker_code.max() + 1):,} taker "
                              f"and {int(maker_code.max() + 1):,} maker pseudonyms"),
               "window": f"December 2025, days {day_lo} to {day_hi}",
               "coins": ["BTC", "ETH"]},
        started=t0, out_dir=os.path.dirname(OUT_META))

    print(f"wrote {OUT_NPZ} ({meta['size_mb']} MB, {n:,} rows)")
    print(f"  sha256 {meta['sha256']}")
    print(f"  block_time_ms span days {(block_time_ms.max() - block_time_ms.min()) / 86400000:.1f}")
    print(f"wrote {OUT_META}")


if __name__ == "__main__":
    main()
