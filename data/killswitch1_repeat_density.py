"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-15
References: Albers, Cucuringu, Howison, Shestopaloff, "An Open Book", Zenodo 10.5281/zenodo.18184441 (2026).
"""

# ---------------------------------------------------------------------------
# KILL-SWITCH 1 — counterparty repeat-density on the Hyperliquid L4 trade stream.
#
# Question this answers: does the December trade tape have a rich repeat tail
# (a few wallets recurring as counterparties many times) or is it dominated by
# one-shot wallets? A rich tail makes a per-wallet effect identifiable: an
# idiosyncratic per-counterparty adverse-selection effect carried by a
# counterparty fixed effect needs each wallet to recur before that effect can be
# separated from noise. A thin tape leaves only the pooled measurement
# identifiable.
#
# Real on-disk format (verified verbatim from the released SCHEMA.md / read_data.py):
#   trades_2025_12.tar  unpacks to a tree:
#       <YYYYMMDD>/<H>.gz        H in 0..23, NOT zero-padded
#   each <H>.gz = gzip-compressed JSON LINES, one trade object per line:
#       {"coin","side","time","px","sz","hash","trade_dir_override","side_info":[a,b]}
#   side_info has EXACTLY two entries (the two counterparties); each entry:
#       {"user","start_pos","oid","twap_id","cloid"}
#   read_data.py flattens these to side0_user / side1_user / side0_start_pos / ...
#   BOTH side_info[0].user and side_info[1].user count as a fill for that wallet.
#
# This script streams that tree (or the raw .tar) without loading it all into RAM.
# Pure stdlib for parsing (tarfile, gzip, json); numpy + matplotlib for output only.
# CLI:  python killswitch1_repeat_density.py <path>
#   <path> may be:
#     - the extracted trades dir (contains <YYYYMMDD>/ subfolders), or
#     - a single <YYYYMMDD> day folder, or
#     - a single <H>.gz hourly file, or
#     - the trades_2025_12.tar archive itself (streamed member-by-member).
# ---------------------------------------------------------------------------

import gzip
import io
import json
import os
import sys
import tarfile
from collections import Counter, defaultdict

import numpy as np

import matplotlib

matplotlib.use("Agg")  # headless; write PNG only
import matplotlib.pyplot as plt

# ---------------------------------------------------------------------------
# DECISION-RULE CONSTANTS  (clearly labelled, tune here)
# ---------------------------------------------------------------------------
# A trade tape is "RICH" (full-identification leg alive) when wallets that the
# tape sees >= REPEAT_FILL_FLOOR times account for at least RICH_VOLUME_SHARE of
# total notional volume. The intuition: the per-counterparty fixed effect is only
# identifiable off wallets that recur, so the recurring wallets must carry a
# materially large share of the flow, not a rounding error.
REPEAT_FILL_FLOOR = 10          # a wallet "recurs" if it appears in >= this many fills
RICH_VOLUME_SHARE = 0.50        # recurring wallets must hold >= 50% of notional volume
# Secondary corroborating floor: at least this many wallets must clear the repeat
# floor, so the tail is a population and not three addresses.
MIN_RECURRING_WALLETS = 200

# Coins to restrict the count to. Set to None to count ALL 250+ perps.
# The lead markets are the three deep ones; the data is heavy-tailed by coin
# so restricting avoids letting illiquid alts dominate the wallet universe.
COIN_FILTER = {"BTC", "ETH", "SOL"}   # set to None for all coins

# Written BESIDE this file, like every other figure this tree produces. Until 2026-08-03
# this was a hard-typed absolute path putting the same file name under the system
# temporary directory, and that one line cost the graph its only missing output:
# build.py declares this node's output under that name, no such file has ever existed
# inside the repository, and a reader who cloned the tree and looked for the figure found
# nothing. The absolute-path guard did not catch it and is not at fault -- its predicate
# looks for a home directory, and the temporary directory is not one -- so the repository
# rule about absolute paths is wider than that predicate, and this was where it was wider.
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_PNG = os.path.join(HERE, "ks1_repeat_density.png")


# ---------------------------------------------------------------------------
# Streaming record source
# ---------------------------------------------------------------------------
def _iter_lines_from_gz_bytes(raw_bytes):
    """Yield decoded JSON-line strings from the bytes of one gzip member/file."""
    # gzip.decompress handles the whole hour at once; hours are a few hundred MB
    # decompressed at most, which is fine. We still avoid holding the whole tar.
    text = gzip.decompress(raw_bytes).decode("utf-8")
    for line in text.split("\n"):
        line = line.strip()
        if line:
            yield line


def _iter_trades_from_path(path):
    """Yield trade dicts from any of the accepted <path> shapes, streaming.

    Accepts: the .tar archive, an extracted trades dir, one day folder, or one
    <H>.gz file. Files inside a day folder are named "<H>.gz" (H = 0..23).
    """
    if os.path.isfile(path) and path.endswith(".tar"):
        # Stream the tar member-by-member; only hourly .gz members are trades.
        with tarfile.open(path, mode="r|*") as tf:  # streaming mode
            for member in tf:
                if not member.isfile():
                    continue
                name = os.path.basename(member.name)
                # accept "<H>.gz" with H = 0..23
                stem = name[:-3] if name.endswith(".gz") else None
                if stem is None or not stem.isdigit():
                    continue
                f = tf.extractfile(member)
                if f is None:
                    continue
                raw = f.read()
                for line in _iter_lines_from_gz_bytes(raw):
                    yield json.loads(line)
        return

    if os.path.isfile(path) and path.endswith(".gz"):
        with open(path, "rb") as fh:
            raw = fh.read()
        for line in _iter_lines_from_gz_bytes(raw):
            yield json.loads(line)
        return

    if os.path.isdir(path):
        # Either an extracted trades dir (subdirs = <YYYYMMDD>) or a day folder.
        entries = sorted(os.listdir(path))
        gz_here = [e for e in entries if e.endswith(".gz") and e[:-3].isdigit()]
        if gz_here:
            # path is itself a day folder of <H>.gz files
            for e in gz_here:
                fp = os.path.join(path, e)
                with open(fp, "rb") as fh:
                    raw = fh.read()
                for line in _iter_lines_from_gz_bytes(raw):
                    yield json.loads(line)
            return
        # otherwise treat subdirs as day folders
        for d in entries:
            day_dir = os.path.join(path, d)
            if not os.path.isdir(day_dir):
                continue
            for e in sorted(os.listdir(day_dir)):
                if not (e.endswith(".gz") and e[:-3].isdigit()):
                    continue
                fp = os.path.join(day_dir, e)
                with open(fp, "rb") as fh:
                    raw = fh.read()
                for line in _iter_lines_from_gz_bytes(raw):
                    yield json.loads(line)
        return

    raise ValueError(
        f"Unrecognized path: {path!r}. Expected a .tar, a .gz hour file, "
        "an extracted trades dir, or a <YYYYMMDD> day folder."
    )


# ---------------------------------------------------------------------------
# Single streaming pass: accumulate per-wallet counters
# ---------------------------------------------------------------------------
def stream_counts(path):
    """One pass over the tape. Returns aggregates without holding trades in RAM.

    Per wallet we keep: fill count and notional volume (px*sz). Both side0_user
    and side1_user of every trade count as one fill for that wallet (a fill links
    two counterparties; each side is credited). We also pick the highest-fill
    wallet and, in a SECOND lightweight pass scoped to that one wallet, count its
    distinct counterparties and how many it faces repeatedly.
    """
    fills = Counter()           # wallet -> number of fills
    volume = defaultdict(float)  # wallet -> notional volume (px*sz)
    total_fills = 0             # counts each (trade, side) once -> 2 per trade
    total_volume = 0.0
    n_trades = 0

    for tr in _iter_trades_from_path(path):
        if COIN_FILTER is not None and str(tr.get("coin", "")).upper() not in COIN_FILTER:
            continue
        si = tr.get("side_info") or []
        if len(si) < 2:
            continue
        try:
            px = float(tr["px"])
            sz = float(tr["sz"])
        except (KeyError, TypeError, ValueError):
            continue
        notional = px * sz
        n_trades += 1
        for entry in (si[0], si[1]):
            w = entry.get("user")
            if not w:
                continue
            fills[w] += 1
            volume[w] += notional
            total_fills += 1
            total_volume += notional

    return fills, volume, total_fills, total_volume, n_trades


def counterparty_profile(path, target_wallet):
    """Second scoped pass: for one wallet, count distinct + repeated counterparties.

    For every trade in which target_wallet is one of the two side_info users, the
    OTHER side's user is a counterparty. We tally how many times each distinct
    counterparty is faced.
    """
    cp = Counter()
    for tr in _iter_trades_from_path(path):
        if COIN_FILTER is not None and str(tr.get("coin", "")).upper() not in COIN_FILTER:
            continue
        si = tr.get("side_info") or []
        if len(si) < 2:
            continue
        u0 = si[0].get("user")
        u1 = si[1].get("user")
        if u0 == target_wallet and u1:
            cp[u1] += 1
        elif u1 == target_wallet and u0:
            cp[u0] += 1
    return cp


# ---------------------------------------------------------------------------
# Reporting + plot + decision
# ---------------------------------------------------------------------------
def main():
    if len(sys.argv) != 2:
        print("usage: python killswitch1_repeat_density.py <trades_path>")
        print("  <trades_path> = trades_2025_12.tar | extracted dir | <YYYYMMDD> | <H>.gz")
        sys.exit(2)

    path = sys.argv[1]
    print(f"[ks1] scanning: {path}")
    print(f"[ks1] coin filter: {sorted(COIN_FILTER) if COIN_FILTER else 'ALL coins'}")

    fills, volume, total_fills, total_volume, n_trades = stream_counts(path)

    n_wallets = len(fills)
    if n_wallets == 0:
        print("[ks1] no fills found — check the path / coin filter.")
        sys.exit(1)

    counts = np.fromiter(fills.values(), dtype=np.int64)
    vols = np.array([volume[w] for w in fills], dtype=np.float64)
    wallets = np.array(list(fills.keys()))

    # ---- (a) histogram of fills-per-wallet (log-scale bins) ----
    cmin, cmax = int(counts.min()), int(counts.max())
    # log-spaced bins from 1 to max (guard cmax==1)
    hi = max(cmax, 2)
    bins = np.unique(np.floor(np.logspace(0, np.log10(hi), num=30)).astype(np.int64))
    bins = np.append(bins, hi + 1)  # right edge

    # ---- (b) top-100 / top-1000 concentration ----
    order = np.argsort(counts)[::-1]
    sorted_fills = counts[order]
    sorted_vols = vols[order]

    def share(arr, k):
        k = min(k, arr.size)
        return float(arr[:k].sum()) / float(arr.sum()) if arr.sum() else 0.0

    top100_fill = share(sorted_fills, 100)
    top1000_fill = share(sorted_fills, 1000)
    top100_vol = share(sorted_vols, 100)
    top1000_vol = share(sorted_vols, 1000)

    # ---- (c) wallets with >= N fills ----
    ge2 = int((counts >= 2).sum())
    ge10 = int((counts >= 10).sum())
    ge100 = int((counts >= 100).sum())

    # ---- volume held by recurring wallets (the decision metric) ----
    recurring_mask = counts >= REPEAT_FILL_FLOOR
    n_recurring = int(recurring_mask.sum())
    recurring_volume = float(vols[recurring_mask].sum())
    recurring_vol_share = recurring_volume / total_volume if total_volume else 0.0

    # ---- (d) candidate market-maker = highest-fill wallet ----
    mm_idx = int(np.argmax(counts))
    mm_wallet = str(wallets[mm_idx])
    mm_fills = int(counts[mm_idx])
    print(f"[ks1] candidate MM (highest-fill wallet): {mm_wallet} with {mm_fills:,} fills")
    print("[ks1] second pass: profiling that wallet's counterparties ...")
    cp = counterparty_profile(path, mm_wallet)
    mm_distinct_cp = len(cp)
    mm_repeat_cp = int(sum(1 for v in cp.values() if v >= 2))
    mm_cp_ge10 = int(sum(1 for v in cp.values() if v >= 10))

    # ---- text summary to stdout ----
    print("\n" + "=" * 70)
    print("KILL-SWITCH 1 — REPEAT-DENSITY SUMMARY")
    print("=" * 70)
    print(f"trades counted (post coin-filter) : {n_trades:,}")
    print(f"total fills (2 per trade)         : {total_fills:,}")
    print(f"total notional volume (px*sz)     : {total_volume:,.2f}")
    print(f"distinct wallets                  : {n_wallets:,}")
    print(f"fills-per-wallet  min/median/max  : "
          f"{cmin} / {int(np.median(counts))} / {cmax}")
    print("-" * 70)
    print("Concentration (share of fills | share of volume):")
    print(f"  top-100  wallets : {top100_fill:6.2%} | {top100_vol:6.2%}")
    print(f"  top-1000 wallets : {top1000_fill:6.2%} | {top1000_vol:6.2%}")
    print("-" * 70)
    print("Wallet tail (count of wallets with >= N fills):")
    print(f"  >=2   : {ge2:,}")
    print(f"  >=10  : {ge10:,}")
    print(f"  >=100 : {ge100:,}")
    print("-" * 70)
    print(f"Recurring wallets (>= {REPEAT_FILL_FLOOR} fills):")
    print(f"  count                  : {n_recurring:,}")
    print(f"  share of total volume  : {recurring_vol_share:6.2%}")
    print("-" * 70)
    print("Candidate market-maker (highest-fill wallet):")
    print(f"  wallet                       : {mm_wallet}")
    print(f"  fills                        : {mm_fills:,}")
    print(f"  distinct counterparties      : {mm_distinct_cp:,}")
    print(f"  counterparties faced >=2x    : {mm_repeat_cp:,}")
    print(f"  counterparties faced >=10x   : {mm_cp_ge10:,}")
    print("=" * 70)

    # ---- plot ----
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    ax = axes[0]
    ax.hist(counts, bins=bins)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("fills per wallet (log)")
    ax.set_ylabel("number of wallets (log)")
    ax.set_title("Fills-per-wallet distribution")

    ax2 = axes[1]
    # cumulative share of volume vs wallet rank (Lorenz-style)
    cum_vol = np.cumsum(sorted_vols) / sorted_vols.sum()
    rank = np.arange(1, sorted_vols.size + 1)
    ax2.plot(rank, cum_vol)
    ax2.set_xscale("log")
    ax2.set_xlabel("wallet rank by fills (log)")
    ax2.set_ylabel("cumulative share of volume")
    ax2.set_title("Volume concentration (top wallets)")
    ax2.axhline(RICH_VOLUME_SHARE, linestyle="--", linewidth=1)
    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=110)
    # Printed relative to this file, so the line names the target without putting a local
    # home directory into the console output or into any log that captures it.
    print(f"[ks1] plot written: {os.path.relpath(OUT_PNG, HERE)}")

    # ---- DECISION RULE ----
    rich = (recurring_vol_share >= RICH_VOLUME_SHARE) and (n_recurring >= MIN_RECURRING_WALLETS)
    print("\n" + "#" * 70)
    if rich:
        print(f"REPEAT-DENSITY: RICH (full-identification leg alive) — "
              f"{recurring_vol_share:.1%} of volume from {n_recurring:,} wallets "
              f"with >= {REPEAT_FILL_FLOOR} fills "
              f"(thresholds: vol-share >= {RICH_VOLUME_SHARE:.0%}, "
              f"wallets >= {MIN_RECURRING_WALLETS}).")
    else:
        print(f"REPEAT-DENSITY: THIN (fall back to measurement version) — "
              f"only {recurring_vol_share:.1%} of volume from {n_recurring:,} "
              f"recurring wallets; below the RICH threshold "
              f"(vol-share >= {RICH_VOLUME_SHARE:.0%} AND wallets >= "
              f"{MIN_RECURRING_WALLETS}).")
    print("#" * 70)


if __name__ == "__main__":
    main()
