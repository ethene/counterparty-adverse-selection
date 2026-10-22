"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-20
References: Easley, Lopez de Prado, O'Hara (2012) VPIN bulk-volume classification;
  Cont, Kukanov, Stoikov (2014) order-flow imbalance; Stoikov (2018) micro-price;
  Hyperliquid L2-book archive (s3://hyperliquid-archive/market_data); Zenodo 18184441 (Albers et al. 2026).
"""

# ---------------------------------------------------------------------------
# OBJECT I3-BOOK - IS PER-COUNTERPARTY TOXICITY RECOVERABLE FROM THE PUBLIC BOOK?
#
# THE HEADLINE QUESTION. i3_nonrecoverability_oos.py bounds non-recoverability
# against the TRADE TAPE only (a wallet's VPIN, signed-flow imbalance, mean size,
# trade intensity). A referee's first move is: "you never gave the anonymous maker
# the ORDER BOOK." A real CEX market maker sees the full public L2 book and can
# compute order-flow imbalance, queue imbalance, book-VPIN, micro-price pressure
# and depth. This script EXTENDS the anonymous baseline to the FULL public book
# and re-asks: does the on-chain counterparty fixed effect STILL add incremental
# out-of-sample predictive lift, ON TOP of the entire public information set?
#
# Three stages, all numpy + stdlib + lz4:
#
#   STAGE 1 (book features). Stream the LOCAL l2_cache lz4 (the same per-record
#   parse i4_l2_mid.py uses, full 20 levels) and build, per snapshot, a PUBLIC /
#   ANONYMOUS feature vector - NO counterparty identity anywhere:
#     - OFI            order-flow imbalance from level-size changes (Cont-Kukanov-
#                      Stoikov 2014), summed over the top levels between snapshots.
#     - qimb_L         multi-level queue imbalance (sum bid sz - sum ask sz) /
#                      (sum bid sz + sum ask sz) over the top L levels, for a few L.
#     - book_vpin      bulk-volume-classified VPIN over snapshots: each snapshot's
#                      signed mid move classifies that snapshot's traded-proxy
#                      volume (|delta depth|) buy vs sell; rolling |buy-sell|/total.
#     - micro_dev_bps  delta-microprice: (microprice - mid)/mid in bps (Stoikov 2018
#                      size-weighted micro-price), the book's lean.
#     - depth_kbps_*   total resting size within k bps of the mid (k in DEPTH_KBPS),
#                      bid+ask, the visible liquidity cushion.
#   Emit book_feats_{COIN}.npz: t_ms int64 SORTED ASC (dup collapsed keep-last) +
#   one float64 column per feature. Honors CAP_DAYS / CAP_HOURS / CAP_COINS so a
#   one-hour smoke slice is possible.
#
#   STAGE 2 (no-lookahead join). For every fill in quickwin_markouts_mid.npz, join
#   the book-feature snapshot AT ENTRY: the LAST snapshot with t_snap <= t_fill
#   (no lookahead), hour-stitched because book_feats is one full-window series per
#   coin. The fill entry timestamp is reconstructed by re-walking parse_day in the
#   EXACT row order of quickwin_markouts_mid.npz (same trick i4_midmarkout uses),
#   so the joined book features line up row-for-row with the markout intermediate.
#
#   STAGE 3 (incremental-lift test). Re-use the i3 OOS harness verbatim (its
#   OOS-by-wallet folds, label-permutation placebo with p-floor 1/(N+1), BH-FDR
#   over the cell family, whale-drop robustness). The ANONYMOUS BASELINE is now
#   i3's trade-tape features (VPIN / flow-imbalance / size / intensity) PLUS the
#   wallet's EARLY-half aggregates of these PUBLIC BOOK features. Model A = the
#   full public info set; Model B = public info set + counterparty history FE.
#   Report whether the FE adds INCREMENTAL OOS R^2 and rank-lift on top of the
#   public book, on the BOOK-MID markout at the two windows settings.py names --
#   the headline one primary, the long companion secondary -- and emit a clear
#   per-cell "fe_adds_over_public_book" boolean.
#
# READING: if the FE STILL adds lift over the full public book (positive
# incremental OOS R^2, small placebo p, survives FDR, whale-robust), then
# per-counterparty toxicity is NOT recoverable even from the complete public book
# - it needs on-chain identity. If the lift VANISHES once the book features are
# in, the book already encoded it and the on-chain-only claim weakens. Either way
# this is the test the trade-tape-only i3 could not run.
#
# numpy + stdlib + lz4 only. NO hardcoded /Users paths (HERE + env/argparse data
# root). Reads the shared mid-markout intermediate; parses raw book locally.
# ---------------------------------------------------------------------------

import argparse
import json
import os
import subprocess
import sys

import numpy as np

# The shared modules sit in the repository root, one directory up from this
# group, and this file also imports from the data group. Both are built from this
# file's own location and never from the working directory the run happens to
# start in.
_CODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_CODE_DIR, os.path.join(_CODE_DIR, "data")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import settings as H

# One place writes a results file, so this artifact records its producer and hash, its
# inputs, its scope and its settings the way every other one does. See artifact.py.
import artifact
# One place owns the multiplicity correction. stats.benjamini_hochberg is the same
# spelling i3_nonrecoverability_oos.benjamini_hochberg uses -- sort ascending,
# q = p*m/rank, running minimum from the largest p downward, clip to one, NaN carried
# through and left out of m -- and stats.py's own self-test runs the two against each
# other on 200 random families with ties and untestable cells. What the module returns
# and the local function does not is the THRESHOLD the correction applied, without which
# "survives FDR" cannot be read: alpha/m here is alpha over a family of 24, and the same
# p corrected over a family of 448 gives the opposite verdict.
import stats
# One place owns where the panels are and which column is the score; see the note beside
# MID_NPZ_PATH for why the load itself stays at the call site.
import panel_io as P
# Re-use the validated i3 OOS harness (folds, placebo, whale-drop, the trade-tape
# anonymous comparator) and the i4 fill-parse / mid-join conventions.
import i3_nonrecoverability_oos as i3
import build_quickwin_markouts as bqm

# -------------------- configuration --------------------
HERE = os.path.dirname(os.path.abspath(__file__))

# Data root holding the raw l2_cache. Resolution order (no /Users hardcode):
#   1. --data-root / CAP_DATA_ROOT  (explicit override; must contain l2_cache/)
#   2. ../02_data beside the repository, inferred relative to this file
# l2_cache layout: <root>/l2_cache/<YYYYMMDD>/<hour 0-23>/l2Book/{BTC,ETH}.lz4
# Two levels up, not one: this script sits in a group directory inside the repository,
# so 02_data is a sibling of the REPOSITORY and not of the group.
DEFAULT_DATA_ROOT = os.path.abspath(os.path.join(_CODE_DIR, "..", "02_data"))

# The shared book-mid panel, located through panel_io so the one module that knows
# where the panels live answers here too. The environment list is EMPTY on purpose: the
# CAP_DATA_ROOT this file reads is the root of the RAW l2_cache above, a different
# directory from the one holding the panels, and this path has never honoured an
# override. Adopting panel_io's five names would let a machine that exports one of them
# feed this script a different panel, which is a change of behaviour and not of code.
# The file name stays a literal inside the join, because build.py derives the input edge
# by folding the argument of np.load to its last literal component and a call there
# would fold to nothing.
PANEL_ROOT_ENV = ()
MID_NPZ_PATH = os.path.join(P.data_root(env_names=PANEL_ROOT_ENV),
                            "quickwin_markouts_mid.npz")
RESULTS_PATH = os.path.join(HERE, "i3_book_nonrecoverability_results.json")

# Cached per-fill entry timestamps written by make_notebook_fills.py, in the SAME
# row order as quickwin_markouts_mid.npz. When this file is present and lines up
# with the mid intermediate, STAGE 2 reads the entry timestamps from it instead of
# re-walking the raw node fills off S3. Both routes feed the identical as-of join,
# so the joined features are the same; the cached route needs no network and no
# requester-pays download, which lets the artifact be regenerated offline.
CACHED_FILLS_PATH = os.path.join(_CODE_DIR, "notebooks", "notebook_fills.npz")

S3_BUCKET = "s3://hyperliquid-archive/market_data"

DEFAULT_DAYS = [
    "20251204", "20251205", "20251206", "20251207", "20251208",
    "20251209", "20251210", "20251211", "20251212", "20251213",
]
DEFAULT_HOURS = list(range(24))
# symbol -> code for THIS artifact family (quickwin carries {0, 1}); asked for by
# artifact name so no file writes its own map. The coin LIST comes from the same map,
# ordered by code, so the two cannot disagree about which coins the artifact holds.
COIN_CODE = H.coin_codes("quickwin")
DEFAULT_COINS = [sym for _, sym in sorted(H.coin_labels("quickwin").items())]

# --- book-feature parameters (all PUBLIC / anonymous) ---------------------
OFI_LEVELS = 5             # levels used for the order-flow-imbalance accumulation
QIMB_LEVELS = (1, 5, 10)   # queue-imbalance depths emitted as separate features
DEPTH_KBPS = (5, 10)       # depth-within-k-bps cushions emitted (bid+ask size)
BVPIN_WINDOW = 50          # rolling snapshots for the book-VPIN running estimate

# --- join guard (matches i4_midmarkout.GAP_MAX_MS) ---
GAP_MAX_MS = 5000.0
MS_PER_S = 1000

# --- test config: book-mid markout, the headline window first then the companion ---
# Both column names are derived: the headline from settings.py, the companion from the
# contrast constant i3_nonrecoverability_oos declares. Nothing here fixes a window.
BOOK_HORIZON_KEYS = {H.HEADLINE_HORIZON_S: P.score_col("mid"),
                     H.COMPANION_HORIZON_S: P.score_col("mid",
                                                        H.COMPANION_HORIZON_S)}
PRIMARY_HORIZON = H.HEADLINE_HORIZON_S

# Seed declared here per the shared contract; the i3 harness carries its own
# RNG_SEED (re-used so folds/placebo are identical to the trade-tape run).
RNG_SEED = i3.RNG_SEED          # 20260619
CAP_BOOK_SEED = 20260620        # this script's own declared seed

# --- fold-seed robustness sweep ---
# Every incremental_oos_r2 in this file is scored on one k-fold split of the
# wallets, and that split comes from a single fold seed. The point estimate moves
# with the seed, so a single draw is not a safe number to quote. The sweep below
# re-scores each cell over SEED_SWEEP_N independent fold seeds and reports the
# median with its range, which is what belongs in prose. The same seed is used
# across coins within a draw, so the per-seed ETH minus BTC difference is paired
# and most of the shared fold noise cancels out of it.
SEED_SWEEP_N = 40               # fold seeds per cell; medians are stable well before this
SEED_SWEEP_SEEDS = tuple(range(1, SEED_SWEEP_N + 1))


# -------------------- env window resolution (smoke slices) --------------------
def _env_list(name, default):
    raw = os.environ.get(name)
    if not raw:
        return list(default)
    return [tok.strip() for tok in raw.split(",") if tok.strip()]


def resolve_window():
    days = _env_list("CAP_DAYS", DEFAULT_DAYS)
    hours_raw = _env_list("CAP_HOURS", [str(h) for h in DEFAULT_HOURS])
    hours = [int(h) for h in hours_raw]
    coins = [c.upper() for c in _env_list("CAP_COINS", DEFAULT_COINS)]
    return days, hours, coins


def resolve_data_root(cli_root=None):
    root = cli_root or os.environ.get("CAP_DATA_ROOT") or DEFAULT_DATA_ROOT
    return os.path.abspath(root)


# -------------------- raw l2Book IO (local-first, lz4) --------------------
def local_l2_path(data_root, day, hour, coin):
    return os.path.join(data_root, "l2_cache", day, str(hour), "l2Book", f"{coin}.lz4")


def ensure_l2_file(data_root, day, hour, coin):
    """Local-first; attempt a single S3 download only if absent. Returns path or None.

    The requester-pays download mirrors i4_l2_mid.ensure_file but stays inside the
    resolved data root, so no absolute machine path is baked in.
    """
    path = local_l2_path(data_root, day, hour, coin)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    s3_uri = f"{S3_BUCKET}/{day}/{hour}/l2Book/{coin}.lz4"
    try:
        subprocess.run(
            ["aws", "s3", "cp", s3_uri, path, "--request-payer", "requester"],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        msg = getattr(exc, "stderr", b"")
        if isinstance(msg, bytes):
            msg = msg.decode("utf-8", "replace").strip()
        print(f"  [warn] l2 download failed {day}/{hour}/{coin}: {msg or exc}",
              file=sys.stderr)
        return None
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    return None


def decompress(path):
    """Decompress an lz4 file to bytes (lz4 CLI, then unlz4, then python lz4)."""
    for cmd in (["lz4", "-dc", path], ["unlz4", "-c", path]):
        try:
            proc = subprocess.run(cmd, check=True, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE)
            return proc.stdout
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
    try:
        import lz4.frame as lz4f  # type: ignore

        with open(path, "rb") as fh:
            return lz4f.decompress(fh.read())
    except Exception as exc:  # noqa: BLE001 - warn, do not crash the whole run
        print(f"  [warn] lz4 decode failed for {path}: {exc}", file=sys.stderr)
        return None


# -------------------- per-snapshot book parsing (full 20 levels) --------------------
def _parse_levels(side):
    """Return parallel float arrays (px, sz) for one book side's level list.

    Robust to malformed level dicts (skip the bad level, keep the rest)."""
    pxs, szs = [], []
    for lvl in side:
        try:
            pxs.append(float(lvl["px"]))
            szs.append(float(lvl["sz"]))
        except (ValueError, KeyError, TypeError):
            continue
    return pxs, szs


def parse_book_file(raw_bytes, acc):
    """Parse one decompressed l2Book file into ordered per-snapshot raw arrays.

    Appends to `acc`, a dict of growing python lists keyed by:
      t, bb_px, ba_px, bb_sz, ba_sz   (best bid/ask px & sz per snapshot)
      bid_px[L], bid_sz[L], ask_px[L], ask_sz[L]  level-L px/sz (L<OFI window)
      sum_bid_top, sum_ask_top        (top-OFI_LEVELS resting size, per snapshot)
      qimb_num[Q], qimb_den[Q]        (queue-imbalance numerator/denominator per Q)
      depth_bid[k], depth_ask[k]      (size within k bps of mid per k)
    Returns rows added. Snapshots are appended IN FILE ORDER; the global sort and
    dup-collapse happens once after all files (so cross-hour stitching is clean).
    """
    added = 0
    for line in raw_bytes.split(b"\n"):
        if not line:
            continue
        try:
            obj = json.loads(line)
            data = obj["raw"]["data"]
            t_ms = int(data["time"])
            levels = data["levels"]
            bids = levels[0]
            asks = levels[1]
            if not bids or not asks:
                continue
        except (ValueError, KeyError, IndexError, TypeError):
            continue

        bpx, bsz = _parse_levels(bids)
        apx, asz = _parse_levels(asks)
        if not bpx or not apx:
            continue

        bb_px, ba_px = bpx[0], apx[0]
        bb_sz, ba_sz = bsz[0], asz[0]
        mid = 0.5 * (bb_px + ba_px)
        if mid <= 0:
            continue

        acc["t"].append(t_ms)
        acc["bb_px"].append(bb_px)
        acc["ba_px"].append(ba_px)
        acc["bb_sz"].append(bb_sz)
        acc["ba_sz"].append(ba_sz)
        acc["mid"].append(mid)

        # micro-price (Stoikov 2018): best level, weighted by OPPOSITE side size
        sz_denom = bb_sz + ba_sz
        micro = ((bb_px * ba_sz + ba_px * bb_sz) / sz_denom) if sz_denom > 0 else mid
        acc["micro"].append(micro)

        # OFI level arrays (top OFI_LEVELS px+sz per side, padded with nan/0)
        for L in range(OFI_LEVELS):
            acc[f"bid_px_{L}"].append(bpx[L] if L < len(bpx) else np.nan)
            acc[f"bid_sz_{L}"].append(bsz[L] if L < len(bsz) else 0.0)
            acc[f"ask_px_{L}"].append(apx[L] if L < len(apx) else np.nan)
            acc[f"ask_sz_{L}"].append(asz[L] if L < len(asz) else 0.0)

        # multi-level queue imbalance numerators/denominators per depth Q
        for Q in QIMB_LEVELS:
            sb = float(sum(bsz[:Q]))
            sa = float(sum(asz[:Q]))
            acc[f"qimb_num_{Q}"].append(sb - sa)
            acc[f"qimb_den_{Q}"].append(sb + sa)

        # depth within k bps of mid (bid+ask resting size inside the band)
        for k in DEPTH_KBPS:
            band = mid * (k / 1e4)
            db = 0.0
            for px, sz in zip(bpx, bsz):
                if px >= mid - band:
                    db += sz
            da = 0.0
            for px, sz in zip(apx, asz):
                if px <= mid + band:
                    da += sz
            acc[f"depth_bid_{k}"].append(db)
            acc[f"depth_ask_{k}"].append(da)

        added += 1
    return added


def _new_acc():
    keys = ["t", "bb_px", "ba_px", "bb_sz", "ba_sz", "mid", "micro"]
    for L in range(OFI_LEVELS):
        keys += [f"bid_px_{L}", f"bid_sz_{L}", f"ask_px_{L}", f"ask_sz_{L}"]
    for Q in QIMB_LEVELS:
        keys += [f"qimb_num_{Q}", f"qimb_den_{Q}"]
    for k in DEPTH_KBPS:
        keys += [f"depth_bid_{k}", f"depth_ask_{k}"]
    return {k: [] for k in keys}


# -------------------- book-feature engineering (vectorized, post-sort) --------------------
def _ofi_series(bid_px, bid_sz, ask_px, ask_sz):
    """Order-flow imbalance (Cont, Kukanov, Stoikov 2014) summed over top levels.

    Per level L the contribution between consecutive snapshots is:
      bid side: +bid_sz if bid_px rose, -prev_bid_sz if it fell, (delta sz) if equal
      ask side: -ask_sz if ask_px rose, +prev_ask_sz if it fell, -(delta sz) if equal
    OFI_t = sum_L (e^bid_L - e^ask_L). First snapshot has no predecessor -> 0.
    All arrays are (n_snap, n_levels); returns a length-n_snap OFI series.
    """
    n = bid_px.shape[0]
    out = np.zeros(n, dtype=np.float64)
    if n < 2:
        return out
    bp, bs = bid_px, bid_sz
    ap, as_ = ask_px, ask_sz
    # previous-row views
    bp0, bp1 = bp[:-1], bp[1:]
    bs0, bs1 = bs[:-1], bs[1:]
    ap0, ap1 = ap[:-1], ap[1:]
    as0, as1 = as_[:-1], as_[1:]
    # bid contribution per level (treat nan px as no-change so it contributes 0)
    e_bid = np.where(bp1 > bp0, bs1,
                     np.where(bp1 < bp0, -bs0, bs1 - bs0))
    e_ask = np.where(ap1 > ap0, -as0,
                     np.where(ap1 < ap0, as1, as1 - as0))
    contrib = np.nan_to_num(e_bid - e_ask, nan=0.0)
    out[1:] = contrib.sum(axis=1)
    return out


def _book_vpin_series(mid, vol_proxy):
    """Bulk-volume-classified VPIN over snapshots (Easley-Lopez de Prado-O'Hara 2012).

    Classification by the SIGN of the snapshot-to-snapshot mid move: an up-move
    classifies that snapshot's volume proxy as buy, a down-move as sell, a flat
    move splits it half/half. book_vpin_t = rolling mean over BVPIN_WINDOW of
    |V_buy - V_sell| / (V_buy + V_sell). vol_proxy is a public, book-derived
    traded-volume proxy (here |change in top-of-book depth|), so NO trade tape and
    NO counterparty identity enter. Returns a length-n running VPIN series.
    """
    n = mid.shape[0]
    out = np.full(n, np.nan, dtype=np.float64)
    if n < 2:
        return out
    dmid = np.zeros(n, dtype=np.float64)
    dmid[1:] = mid[1:] - mid[:-1]
    buy = np.where(dmid > 0, vol_proxy, np.where(dmid < 0, 0.0, 0.5 * vol_proxy))
    sell = np.where(dmid < 0, vol_proxy, np.where(dmid > 0, 0.0, 0.5 * vol_proxy))
    # rolling sums over BVPIN_WINDOW via cumulative differences
    cb = np.concatenate([[0.0], np.cumsum(buy)])
    cs = np.concatenate([[0.0], np.cumsum(sell)])
    for t in range(n):
        lo = max(0, t - BVPIN_WINDOW + 1)
        vb = cb[t + 1] - cb[lo]
        vs = cs[t + 1] - cs[lo]
        tot = vb + vs
        out[t] = (abs(vb - vs) / tot) if tot > 0 else np.nan
    return out


def build_book_features(acc):
    """Turn the raw per-snapshot accumulator into the sorted feature npz payload.

    Returns dict {t_ms: int64 sorted-unique, <feature>: float64 aligned}.
    All features are PUBLIC / anonymous (no counterparty identity anywhere).
    """
    n_raw = len(acc["t"])
    if n_raw == 0:
        return None

    t = np.asarray(acc["t"], dtype=np.int64)
    mid = np.asarray(acc["mid"], dtype=np.float64)
    micro = np.asarray(acc["micro"], dtype=np.float64)

    # OFI level matrices (n_raw, OFI_LEVELS)
    bid_px = np.column_stack([np.asarray(acc[f"bid_px_{L}"], dtype=np.float64)
                              for L in range(OFI_LEVELS)])
    bid_sz = np.column_stack([np.asarray(acc[f"bid_sz_{L}"], dtype=np.float64)
                              for L in range(OFI_LEVELS)])
    ask_px = np.column_stack([np.asarray(acc[f"ask_px_{L}"], dtype=np.float64)
                              for L in range(OFI_LEVELS)])
    ask_sz = np.column_stack([np.asarray(acc[f"ask_sz_{L}"], dtype=np.float64)
                              for L in range(OFI_LEVELS)])

    # SORT ASC by t_ms (stable so the later file/line wins on a tie), then collapse
    # duplicate t_ms keeping the LAST occurrence - exactly as i4_l2_mid does. The
    # time-ordered series is required before the rolling OFI / book-VPIN run.
    order = np.argsort(t, kind="stable")
    t = t[order]
    mid = mid[order]
    micro = micro[order]
    bid_px = bid_px[order]
    bid_sz = bid_sz[order]
    ask_px = ask_px[order]
    ask_sz = ask_sz[order]
    qimb = {Q: (np.asarray(acc[f"qimb_num_{Q}"], dtype=np.float64)[order],
                np.asarray(acc[f"qimb_den_{Q}"], dtype=np.float64)[order])
            for Q in QIMB_LEVELS}
    depth = {k: (np.asarray(acc[f"depth_bid_{k}"], dtype=np.float64)[order],
                 np.asarray(acc[f"depth_ask_{k}"], dtype=np.float64)[order])
             for k in DEPTH_KBPS}

    keep = np.ones(t.shape[0], dtype=bool)
    keep[:-1] = t[1:] != t[:-1]
    t = t[keep]
    mid = mid[keep]
    micro = micro[keep]
    bid_px = bid_px[keep]
    bid_sz = bid_sz[keep]
    ask_px = ask_px[keep]
    ask_sz = ask_sz[keep]
    qimb = {Q: (nb[keep], db[keep]) for Q, (nb, db) in qimb.items()}
    depth = {k: (db[keep], da[keep]) for k, (db, da) in depth.items()}

    # --- engineered features on the clean, sorted series ---
    ofi = _ofi_series(bid_px, bid_sz, ask_px, ask_sz)

    # delta-microprice in bps (book lean)
    with np.errstate(invalid="ignore", divide="ignore"):
        micro_dev_bps = (micro - mid) / np.where(mid > 0, mid, np.nan) * 1e4
    micro_dev_bps = np.nan_to_num(micro_dev_bps, nan=0.0)

    # book-VPIN: volume proxy = |change in best bid+ask resting size| (public)
    top_depth = bid_sz[:, 0] + ask_sz[:, 0]
    vol_proxy = np.zeros(top_depth.shape[0], dtype=np.float64)
    vol_proxy[1:] = np.abs(np.diff(top_depth))
    book_vpin = _book_vpin_series(mid, vol_proxy)
    book_vpin = np.nan_to_num(book_vpin, nan=0.0)

    out = {"t_ms": t.astype(np.int64),
           "ofi": ofi.astype(np.float64),
           "micro_dev_bps": micro_dev_bps.astype(np.float64),
           "book_vpin": book_vpin.astype(np.float64)}

    for Q, (num, den) in qimb.items():
        with np.errstate(invalid="ignore", divide="ignore"):
            qi = num / np.where(den > 0, den, np.nan)
        out[f"qimb_{Q}"] = np.nan_to_num(qi, nan=0.0).astype(np.float64)
    for k, (db, da) in depth.items():
        out[f"depth_bid_{k}bps"] = db.astype(np.float64)
        out[f"depth_ask_{k}bps"] = da.astype(np.float64)

    return out


def book_feature_names():
    """The ordered list of PUBLIC book feature column names (excludes t_ms)."""
    names = ["ofi", "micro_dev_bps", "book_vpin"]
    names += [f"qimb_{Q}" for Q in QIMB_LEVELS]
    for k in DEPTH_KBPS:
        names += [f"depth_bid_{k}bps", f"depth_ask_{k}bps"]
    return names


def stage1_build_book_feats(data_root, days, hours, coins):
    """STAGE 1: stream local l2 lz4 -> book_feats_{COIN}.npz per coin.

    Returns {coin: out_path} for the coins that produced a series.
    """
    written = {}
    for coin in coins:
        print(f"[i3book] STAGE 1 building book features for {coin} ...")
        acc = _new_acc()
        files_ok, files_skip = 0, 0
        for day in days:
            for hour in hours:
                path = ensure_l2_file(data_root, day, hour, coin)
                if path is None:
                    files_skip += 1
                    continue
                raw = decompress(path)
                if raw is None:
                    files_skip += 1
                    continue
                parse_book_file(raw, acc)
                del raw
                files_ok += 1
        feats = build_book_features(acc)
        if feats is None:
            print(f"  [warn] {coin}: no snapshots; skipping book_feats save",
                  file=sys.stderr)
            continue
        out = os.path.join(P.data_root(), f"book_feats_{coin}.npz")
        np.savez_compressed(out, **feats)
        n = feats["t_ms"].size
        print(f"  {coin}: {n:,} snapshots | files ok {files_ok} skip {files_skip} "
              f"| feats {book_feature_names()} -> {os.path.basename(out)}")
        written[coin] = out
    return written


# -------------------- STAGE 2: reconstruct fill t_ms + join book feats --------------------
def _apply_env_overrides_to_bqm(days, coins):
    """Mirror the smoke-test window onto build_quickwin_markouts so parse_day walks
    the SAME fills, in the SAME order, that produced quickwin_markouts_mid.npz."""
    bqm.DAYS = list(days)
    bqm.COINS = tuple(c.upper() for c in coins)


def load_book_feats(coins):
    """Load book_feats_{COIN}.npz into memory, re-asserting the sort/dedup so the
    as-of join is always valid even on a loosely regenerated artifact.

    Returns {coin: {"t_ms": int64, "F": float64[n,k]}}, feature columns in
    book_feature_names() order."""
    feat_names = book_feature_names()
    series = {}
    for coin in coins:
        path = os.path.join(P.data_root(), f"book_feats_{coin}.npz")
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"missing book features for {coin}: {os.path.basename(path)} - "
                f"run STAGE 1 first")
        z = np.load(path, allow_pickle=False)
        t_ms = np.asarray(z["t_ms"], dtype=np.int64)
        cols = [np.asarray(z[name], dtype=np.float64) for name in feat_names]
        F = np.column_stack(cols) if cols else np.empty((t_ms.size, 0))
        if t_ms.size:
            order = np.argsort(t_ms, kind="stable")
            t_ms, F = t_ms[order], F[order]
            keep = np.ones(t_ms.size, dtype=bool)
            keep[:-1] = t_ms[1:] != t_ms[:-1]
            t_ms, F = t_ms[keep], F[keep]
        series[coin] = {"t_ms": t_ms, "F": F}
        print(f"[i3book] loaded book_feats_{coin}: {t_ms.size:,} snapshots, "
              f"{F.shape[1]} features")
    return series


def join_entry_book(t_fill_ms, S):
    """LAST book snapshot with t_snap <= t_fill (no lookahead), hour-stitched.

    Mirrors i4_midmarkout.join_entry: searchsorted side='right' minus 1, gap guard
    against GAP_MAX_MS. Returns (feat[n,k] with nan where invalid, valid mask).
    """
    t_arr = S["t_ms"]
    F = S["F"]
    n_fill = t_fill_ms.shape[0]
    k = F.shape[1]
    out = np.full((n_fill, k), np.nan, dtype=np.float64)
    if t_arr.size == 0 or n_fill == 0:
        return out, np.zeros(n_fill, dtype=bool)
    # STRICTLY EARLIER, matching i4_midmarkout.join_entry. A snapshot stamped with the
    # fill's own millisecond already carries that fill's impact, so it cannot supply the
    # pre-trade book state this function is asked for. Changed 2026-08-02 together with
    # the three other copies of this rule in the tree.
    idx = np.searchsorted(t_arr, t_fill_ms, side="left") - 1
    valid = idx >= 0
    safe = np.where(valid, idx, 0)
    gap = np.full(n_fill, np.inf, dtype=np.float64)
    gap[valid] = np.abs(t_fill_ms[valid] - t_arr[safe[valid]].astype(np.float64))
    valid &= gap <= GAP_MAX_MS
    if valid.any():
        out[valid] = F[safe[valid]]
    return out, valid


def stage2_join_cached(coin, day, expected_rows, book_series):
    """STAGE 2 from the cached fill timestamps rather than a raw S3 re-walk.

    make_notebook_fills.py stores block_time_ms for every fill in the same row
    order as quickwin_markouts_mid.npz. The guard below only accepts the cache when
    its row count and its coin and day columns match the mid intermediate exactly,
    so a cache built over a different window can never be used by mistake. Given
    those timestamps the as-of join is the same searchsorted call stage2_join makes,
    against the same book series, with the same gap guard.

    Returns (book_X, valid, aligned, issues), or None when the cache is absent or
    does not line up, in which case the caller falls back to the raw walk.
    """
    if not os.path.exists(CACHED_FILLS_PATH):
        return None
    z = np.load(CACHED_FILLS_PATH, allow_pickle=False)
    needed = ("block_time_ms", "coin", "day")
    if any(name not in z.files for name in needed):
        return None
    t_ms = np.asarray(z["block_time_ms"], dtype=np.int64)
    if t_ms.size != expected_rows:
        return None
    coin_i = np.asarray(coin, dtype=np.int64)
    if not np.array_equal(np.asarray(z["coin"], dtype=np.int64), coin_i):
        return None
    if not np.array_equal(np.asarray(z["day"], dtype=np.int64),
                          np.asarray(day, dtype=np.int64)):
        return None

    k = len(book_feature_names())
    book_X = np.full((expected_rows, k), np.nan, dtype=np.float64)
    valid = np.zeros(expected_rows, dtype=bool)
    for name, code in COIN_CODE.items():
        S = book_series.get(name)
        if S is None:
            continue
        sel = np.flatnonzero(coin_i == code)
        if sel.size == 0:
            continue
        feat, ok = join_entry_book(t_ms[sel], S)
        book_X[sel] = feat
        valid[sel] = ok
        nd = float(np.mean(~ok)) if ok.size else float("nan")
        print(f"[i3book] STAGE 2 {name}: fills={sel.size:,} "
              f"book-join nan-drop={nd*100:.1f}% (cached entry timestamps)")
    return book_X, valid, True, []


def stage2_join(days, coins, book_series, expected_rows):
    """STAGE 2: rebuild each fill's entry t_ms by re-walking parse_day in the SAME
    row order as quickwin_markouts_mid.npz, then as-of join the public book feats.

    Returns book_X[n_rows, k] aligned row-for-row with the mid-markout intermediate
    (nan where no in-tolerance entry snapshot exists), plus a per-row valid mask.
    """
    _apply_env_overrides_to_bqm(days, coins)
    feat_names = book_feature_names()
    k = len(feat_names)

    book_rows = []          # list of (n_slice, k) float arrays in row order
    valid_rows = []
    n_total = 0
    issues = []
    for day in bqm.DAYS:
        per_coin, _hours = bqm.parse_day(day)
        if per_coin is None:
            issues.append(f"day {day} missing on S3 - skipped (matches mid pass)")
            continue
        for coin in bqm.COINS:
            d = per_coin[coin]
            n_trades = int(d["taker_ts"].size)
            if n_trades == 0 or d["print_ts"].size == 0:
                # build_quickwin SKIPS empty/print-less slices; replicate the skip
                # so the row order stays identical to the mid intermediate.
                continue
            # block_time is NANOSECONDS -> epoch-ms ONCE for the book join.
            t_ms_fill = (d["taker_ts"] // 1_000_000).astype(np.int64)
            S = book_series.get(coin)
            if S is None:
                feat, valid = (np.full((n_trades, k), np.nan), np.zeros(n_trades, bool))
            else:
                feat, valid = join_entry_book(t_ms_fill, S)
            book_rows.append(feat)
            valid_rows.append(valid)
            n_total += n_trades
            nd = float(np.mean(~valid)) if valid.size else float("nan")
            print(f"[i3book] STAGE 2 {coin} {day}: fills={n_trades:,} "
                  f"book-join nan-drop={nd*100:.1f}%")

    book_X = (np.concatenate(book_rows, axis=0) if book_rows
              else np.empty((0, k), dtype=np.float64))
    valid = (np.concatenate(valid_rows) if valid_rows
             else np.empty(0, dtype=bool))

    aligned = (expected_rows is None) or (book_X.shape[0] == expected_rows)
    if not aligned:
        issues.append(
            f"ROW MISALIGNMENT: rebuilt {book_X.shape[0]} fill rows vs "
            f"{expected_rows} in quickwin_markouts_mid.npz - the book join is NOT "
            f"row-aligned (likely a different analysis window than the mid pass used). "
            f"Re-run STAGE 1/2 over the SAME window that built the mid intermediate.")
    return book_X, valid, aligned, issues


# -------------------- STAGE 3: per-wallet aggregation incl. public book feats --------------------
def _aggregate_with_book(taker_id, day, notional, is_buy, mo, book_X, book_valid,
                         early_days, late_days, K):
    """Like i3._aggregate_features but the anonymous predictor block is the trade-
    tape four (VPIN / |imbalance| / size / intensity) PLUS the wallet EARLY-half
    MEAN of every PUBLIC BOOK feature joined at the fill's entry snapshot.

    Returns (wallet_ids, X_public[n, 4+kbook], hist_fe[n], target[n], tot_not[n])
    or None when too few wallets survive for OOS folds. The history FE and target
    are computed EXACTLY as in i3 (EARLY-half mean markout / LATE-half mean markout)
    so the only change versus i3 is the WIDER anonymous baseline.
    """
    early_set = set(early_days)
    late_set = set(late_days)
    valid = ~np.isnan(mo)
    is_early = np.array([d in early_set for d in day]) & valid
    is_late = np.array([d in late_set for d in day]) & valid

    uniq, inv = np.unique(taker_id, return_inverse=True)
    cnt_e = np.bincount(inv[is_early], minlength=uniq.size)
    cnt_l = np.bincount(inv[is_late], minlength=uniq.size)
    eligible = (cnt_e >= K) & (cnt_l >= K)
    if np.where(eligible)[0].size < (i3.N_FOLDS + 2):
        return None

    # EARLY-half tape ordered by (wallet, day) so the rolling trade-tape predictors
    # run along each wallet's own EARLY sequence (identical to i3).
    e_idx = np.where(is_early)[0]
    order = np.lexsort((day[e_idx], inv[e_idx]))
    e_idx = e_idx[order]
    e_inv = inv[e_idx]
    e_notional = notional[e_idx].astype(np.float64)
    e_is_buy = is_buy[e_idx].astype(np.float64)
    e_day = day[e_idx].astype(np.float64)
    e_mo = mo[e_idx].astype(np.float64)
    # book features joined to those same EARLY fills (rows where the entry join was
    # valid contribute; invalid rows are excluded from the wallet mean per feature)
    e_book = book_X[e_idx]
    e_book_ok = book_valid[e_idx]

    k_book = book_X.shape[1]
    n_w = uniq.size
    f_vpin = np.full(n_w, np.nan)
    f_imb = np.full(n_w, np.nan)
    f_size = np.full(n_w, np.nan)
    f_intensity = np.full(n_w, np.nan)
    f_book = np.full((n_w, k_book), np.nan)
    hist_fe = np.full(n_w, np.nan)
    tot_notional = np.zeros(n_w)

    boundaries = np.where(np.diff(e_inv) != 0)[0] + 1
    starts = np.concatenate([[0], boundaries])
    ends = np.concatenate([boundaries, [e_inv.size]])
    for s, en in zip(starts, ends):
        w = e_inv[s]
        if not eligible[w]:
            continue
        seg_not = e_notional[s:en]
        seg_buy = e_is_buy[s:en]
        seg_day = e_day[s:en]
        seg_mo = e_mo[s:en]
        vpin = i3._vpin_series(seg_not, seg_buy)
        imb = i3._rolling_signed_imbalance(seg_buy.astype(np.int64))
        f_vpin[w] = float(np.nanmean(vpin)) if np.isfinite(vpin).any() else 0.0
        f_imb[w] = float(np.mean(np.abs(imb))) if imb.size else 0.0
        f_size[w] = float(np.mean(seg_not)) if seg_not.size else 0.0
        span = (seg_day.max() - seg_day.min()) + 1.0
        f_intensity[w] = seg_not.size / span if span > 0 else float(seg_not.size)
        hist_fe[w] = float(np.mean(seg_mo))
        tot_notional[w] = float(seg_not.sum())
        # PUBLIC BOOK feature means over the wallet's EARLY fills with a valid join
        seg_book = e_book[s:en]
        seg_ok = e_book_ok[s:en]
        if seg_ok.any():
            f_book[w] = np.nanmean(seg_book[seg_ok], axis=0)
        else:
            f_book[w] = 0.0   # no valid book join for this wallet -> neutral zeros

    # LATE-half target (identical to i3)
    l_idx = np.where(is_late)[0]
    l_inv = inv[l_idx]
    l_mo = mo[l_idx].astype(np.float64)
    s_sum = np.bincount(l_inv, weights=l_mo, minlength=n_w)
    s_cnt = np.bincount(l_inv, minlength=n_w)
    with np.errstate(invalid="ignore", divide="ignore"):
        target = np.where(s_cnt > 0, s_sum / np.where(s_cnt > 0, s_cnt, np.nan), np.nan)
    l_not = notional[l_idx].astype(np.float64)
    tot_notional += np.bincount(l_inv, weights=l_not, minlength=n_w)

    finite_book = np.all(np.isfinite(f_book), axis=1)
    keep = (eligible & ~np.isnan(hist_fe) & ~np.isnan(target)
            & ~np.isnan(f_vpin) & ~np.isnan(f_imb) & ~np.isnan(f_size)
            & ~np.isnan(f_intensity) & finite_book)
    pos = np.where(keep)[0]
    if pos.size < (i3.N_FOLDS + 2):
        return None

    X_public = np.column_stack(
        [f_vpin[pos], f_imb[pos], f_size[pos], f_intensity[pos], f_book[pos]])
    return (uniq[pos].astype(np.int64), X_public, hist_fe[pos], target[pos],
            tot_notional[pos])


# -------------------- STAGE 3: the cell-by-cell test --------------------
def _pctile_of(values, x):
    """Percentile position of x inside `values` (midpoint rule for exact ties)."""
    v = np.asarray(values, dtype=np.float64)
    if v.size == 0 or x is None or x != x:
        return None
    return float(100.0 * np.mean(v < x) + 50.0 * np.mean(v == x))


def seed_robustness(design_store, stored_by_cell):
    """Re-score every cell over SEED_SWEEP_N fold seeds and summarise the spread.

    design_store holds the per-cell (X_public, hist_fe, target) already built by
    run_cell, so nothing is re-aggregated here; only the fold split and the two OOS
    fits are repeated. For each cell this reports the median, mean, min, max and
    interquartile range of incremental_oos_r2, plus where the single stored draw
    sits inside that distribution. The paired block reports the per-seed ETH minus
    BTC difference at the primary horizon, which is the quantity that answers
    whether the coins really differ rather than whether one draw happened to.
    """
    per_cell = []
    draws = {}
    for key, (X_public, hist_fe, target) in sorted(design_store.items()):
        coin_label, h, K = key
        vals = np.array([
            i3.incremental_lift(X_public, hist_fe, target,
                                np.random.default_rng(s))["incremental_oos_r2"]
            for s in SEED_SWEEP_SEEDS], dtype=np.float64)
        draws[key] = vals
        q1, q3 = (float(v) for v in np.percentile(vals, [25, 75]))
        stored = stored_by_cell.get(key)
        per_cell.append({
            "coin": coin_label, "horizon_s": h, "K": K,
            "n_wallets": int(target.size),
            "n_seeds": int(vals.size),
            "median": float(np.median(vals)),
            "mean": float(np.mean(vals)),
            "min": float(np.min(vals)),
            "max": float(np.max(vals)),
            "q1": q1, "q3": q3, "iqr": float(q3 - q1),
            "stored_single_seed": stored,
            "stored_percentile": _pctile_of(vals, stored),
            # The sign count and the draws themselves, by the same idiom the paired
            # block below already uses. Without them a sentence of the form "negative
            # on N of the folds" has no home in this file and gets typed by hand from
            # a run that is gone; the summary above bounds N but does not give it.
            # These are FOLD draws, so read them with `scope_of_variation`: they say
            # how the cell moves when the split moves, not how it moves under
            # sampling, and no count of them is a p-value.
            "n_seeds_negative": int(np.sum(vals < 0)),
            "n_seeds_positive": int(np.sum(vals > 0)),
            "per_seed_values": [float(v) for v in vals],
        })

    # Paired ETH minus BTC at the primary horizon, same fold seed on both coins.
    # This is reported in full, including every per-seed draw, because it is the
    # quantity the report quotes directly and a reader should be able to recompute
    # any statistic of it without re-running the sweep.
    paired = {}
    for K in i3.K_LIST:
        ke, kb = ("ETH", PRIMARY_HORIZON, K), ("BTC", PRIMARY_HORIZON, K)
        if ke not in draws or kb not in draws:
            continue
        d = draws[ke] - draws[kb]
        lo, hi = (float(v) for v in np.percentile(d, [2.5, 97.5]))
        dq1, dq3 = (float(v) for v in np.percentile(d, [25, 75]))
        paired[str(K)] = {
            "horizon_s": PRIMARY_HORIZON, "K": K,
            "n_seeds": int(d.size),
            "n_seeds_eth_above_btc": int(np.sum(d > 0)),
            "frac_seeds_eth_above_btc": float(np.mean(d > 0)),
            "median": float(np.median(d)), "mean": float(np.mean(d)),
            "std": float(np.std(d, ddof=1)) if d.size > 1 else 0.0,
            "min": float(np.min(d)), "max": float(np.max(d)),
            "q1": dq1, "q3": dq3, "iqr": float(dq3 - dq1),
            "pctile_2_5": lo, "pctile_97_5": hi,
            "eth_median": float(np.median(draws[ke])),
            "btc_median": float(np.median(draws[kb])),
            "ranges_overlap": bool(np.min(draws[ke]) <= np.max(draws[kb])),
            "per_seed_seeds": [int(s) for s in SEED_SWEEP_SEEDS],
            "per_seed_differences": [float(v) for v in d],
        }

    return {
        "statistic": "incremental_oos_r2",
        "method": "re-score each cell over independent k-fold splits, varying only "
                  "the fold seed; everything upstream of the split is deterministic",
        "n_seeds": SEED_SWEEP_N,
        "seed_rule": f"np.random.default_rng(s) for s = 1..{SEED_SWEEP_N}",
        "stored_seed_rule": "np.random.default_rng(RNG_SEED + K + horizon_s), the "
                            "single draw reported in by_coin / pooled",
        "reporting_rule": "quote the median with its range, not the single stored "
                          "draw; for the coin comparison quote the paired difference",
        "scope_of_variation": (
            "This sweep varies ONE thing: which wallets land in which fold. The "
            "wallet set, the features and the targets are the same in every draw, so "
            "these ranges measure sensitivity to the fold split and NOTHING ELSE. "
            "They are NOT confidence intervals and NOT sampling uncertainty about a "
            "population, because the draws re-split the same data rather than "
            "resampling new data. For the same reason a count like 40 out of 40 "
            "seeds is not a p-value and must not be reported as one; the draws are "
            "not independent evidence. Sampling uncertainty is addressed separately "
            "by the label-permutation placebo (placebo_p) and the whale-drop check."),
        "cells": per_cell,
        "paired_eth_minus_btc": paired,
        "paired_note": "per-seed difference with the same fold seed on both coins, "
                       "so shared fold noise cancels; this is the number that "
                       "answers whether the coins differ rather than whether one "
                       "draw happened to. Read it as: across every fold split tried, "
                       "the ETH increment stayed above the BTC increment by about "
                       "this much. See scope_of_variation for what the interval is "
                       "and is not.",
    }


def run_cell(g_taker, g_day, g_not, g_isbuy, g_mo, book_X, book_valid,
             early_present, late_present, K, h, coin_label, design_store=None):
    """One coin x horizon x K cell: incremental OOS lift of the counterparty FE
    over the FULL PUBLIC INFO SET (trade tape + public book). Re-uses the i3
    incremental_lift / placebo_pvalue / whale_robust_check verbatim."""
    built = _aggregate_with_book(
        g_taker, g_day, g_not, g_isbuy, g_mo, book_X, book_valid,
        early_present, late_present, K)
    row = {"coin": coin_label, "horizon_s": h, "K": K}
    if built is None:
        row.update({
            "n_wallets": 0,
            "n_public_features": int(4 + book_X.shape[1]),
            "oos_r2_public": None,
            "oos_r2_public_plus_fe": None,
            "incremental_oos_r2": None,
            "incremental_spearman": None,
            "placebo_p": None,
            "placebo_p_floor": H.p_floor(i3.N_PERM),
            "placebo_p_is_floor": False,
            "whale_robust": "n/a",
            "fe_adds_over_public_book": False,
            "note": "too few eligible wallets for OOS folds",
        })
        return row

    wallet_ids, X_public, hist_fe, target, tot_not = built
    if design_store is not None:
        # kept so the fold-seed sweep can re-score this cell without re-aggregating
        design_store[(coin_label, h, K)] = (X_public, hist_fe, target)
    lift = i3.incremental_lift(
        X_public, hist_fe, target, np.random.default_rng(RNG_SEED + K + h))
    folds = lift.pop("_folds")
    Xa = lift.pop("_Xa")
    _ = lift.pop("_target")

    p_perm = i3.placebo_pvalue(
        Xa, target, hist_fe, lift["incremental_oos_r2"],
        folds, np.random.default_rng(RNG_SEED * 3 + K + h))
    incr_no_whale, whale_verdict = i3.whale_robust_check(
        X_public, hist_fe, target, tot_not, lift["incremental_oos_r2"],
        np.random.default_rng(RNG_SEED * 7 + K + h))

    # Is the placebo p a measurement, or the smallest value i3.N_PERM draws can
    # express? The number alone cannot say, and only the second reading is available
    # when no draw beat the observed lift.
    p_is_floor = (bool(H.p_is_floored(p_perm, i3.N_PERM))
                  if (p_perm is not None and p_perm == p_perm) else False)
    row.update({
        "n_wallets": int(lift["n_wallets"]),
        "n_public_features": int(X_public.shape[1]),
        "oos_r2_public": lift["oos_r2_anon"],
        "oos_r2_public_plus_fe": lift["oos_r2_anon_plus_fe"],
        "incremental_oos_r2": lift["incremental_oos_r2"],
        "oos_spearman_public": lift["oos_spearman_anon"],
        "oos_spearman_public_plus_fe": lift["oos_spearman_anon_plus_fe"],
        "incremental_spearman": lift["incremental_spearman"],
        "placebo_p": p_perm,
        "placebo_p_floor": H.p_floor(i3.N_PERM),
        "placebo_p_is_floor": p_is_floor,
        "incremental_oos_r2_no_whales": incr_no_whale,
        "whale_robust": whale_verdict,
    })
    # fe_adds_over_public_book is the headline boolean: the on-chain counterparty
    # FE adds OOS information the FULL public book did NOT, only if the incremental
    # R^2 is positive AND the placebo says it is not a label artefact. The FDR
    # survival flag (added in the family pass below) is the multiplicity-corrected
    # version; this per-cell boolean is the raw within-cell verdict.
    incr_r2 = row["incremental_oos_r2"]
    row["fe_adds_over_public_book"] = bool(
        incr_r2 is not None and incr_r2 == incr_r2 and incr_r2 > 0
        and p_perm is not None and p_perm == p_perm and p_perm <= 0.05)

    # Honesty note: a non-positive incremental R^2 with a positive incremental
    # Spearman is underpowered/inconclusive, NOT evidence the book recovers it.
    incr_sp = row["incremental_spearman"]
    short_late = len(late_present) < len(i3.LATE_DAYS)
    if (incr_r2 is not None and incr_r2 == incr_r2 and incr_r2 <= 0
            and incr_sp is not None and incr_sp == incr_sp and incr_sp > 0):
        row["interpretation"] = (
            "INCONCLUSIVE/UNDERPOWERED, not a recoverability finding: incremental "
            f"R^2 {incr_r2:+.4f} <= 0 while incremental Spearman {incr_sp:+.4f} > 0. "
            "The positive rank lift means the counterparty FE still orders future "
            "toxicity out of sample over the public book; the non-positive R^2 is a "
            "level-fit artefact" + (" amplified by a short late half" if short_late
                                    else "") + ". Do NOT read this cell as the public "
            "book recovering toxicity.")
    else:
        row["interpretation"] = None
    return row


# -------------------- main --------------------
def main():
    ap = argparse.ArgumentParser(
        description="I3-BOOK: is per-counterparty toxicity recoverable from the "
                    "PUBLIC ORDER BOOK? Extends i3 from the trade tape to the full "
                    "public L2 book.")
    ap.add_argument("--data-root", default=None,
                    help="root holding l2_cache/ (default: ../02_data, or "
                         "CAP_DATA_ROOT). No /Users path is hardcoded.")
    ap.add_argument("--stage", choices=("all", "feats", "test"), default="all",
                    help="'feats' = STAGE 1 only (build book_feats_{COIN}.npz); "
                         "'test' = STAGE 2+3 only (book feats must already exist); "
                         "'all' = everything (default).")
    args = ap.parse_args()

    t0 = artifact.start_clock()
    data_root = resolve_data_root(args.data_root)
    days, hours, coins = resolve_window()
    print(f"[i3book] window days={len(days)} hours={len(hours)} coins={coins} "
          f"data_root={os.path.basename(data_root)} seed={CAP_BOOK_SEED}")

    # ---------------- STAGE 1: build public book features ----------------
    if args.stage in ("all", "feats"):
        stage1_build_book_feats(data_root, days, hours, coins)
        if args.stage == "feats":
            print("[i3book] STAGE 1 done (--stage feats); stopping before the test.")
            return

    # ---------------- load the shared mid-markout intermediate ----------------
    # panel_io owns both refusals: the missing-FILE message names the producer that
    # writes this gitignored intermediate, and the missing-COLUMN message names what was
    # asked and what the file holds.
    P.require_present("mid", MID_NPZ_PATH, env_names=PANEL_ROOT_ENV)
    z = np.load(MID_NPZ_PATH, allow_pickle=False)
    P.require_columns(z, "mid", "taker_id", "coin", "day", "notional",
                      *BOOK_HORIZON_KEYS.values())
    taker_id = z["taker_id"].astype(np.int64)
    coin = z["coin"].astype(np.int8)
    day = z["day"].astype(np.int64)
    notional = z["notional"].astype(np.float64)
    expected_rows = int(taker_id.size)
    # Each scored column as float64, read through the panel's own lens.
    mo_by_h = {h: P.score(z, "mid", h) for h in BOOK_HORIZON_KEYS}

    # buy/sell side for the trade-tape VPIN / imbalance (real flag preferred)
    if "taker_side" in z.files:
        is_buy_all = (z["taker_side"].astype(np.int64) != 0).astype(np.int64)
        side_source = "taker_side (real aggressor flag)"
    else:
        start_pos = z["start_pos"].astype(np.float64) if "start_pos" in z.files \
            else np.zeros(expected_rows)
        is_open = z["is_open"].astype(np.int64) if "is_open" in z.files \
            else np.zeros(expected_rows, dtype=np.int64)
        is_buy_all = i3._derive_is_buy(start_pos, is_open, taker_id, day)
        side_source = "start_pos-sign proxy (taker_side absent)"

    # ---------------- STAGE 2: join public book features to every fill ----------------
    book_series = load_book_feats(coins)
    cached = stage2_join_cached(coin, day, expected_rows, book_series)
    if cached is not None:
        book_X, book_valid, aligned, join_issues = cached
        stage2_source = (f"cached fill timestamps ({os.path.basename(CACHED_FILLS_PATH)}), "
                         "row-checked against the mid intermediate; no raw re-walk")
    else:
        book_X, book_valid, aligned, join_issues = stage2_join(
            days, coins, book_series, expected_rows)
        stage2_source = ("raw node fills re-walked via "
                         "build_quickwin_markouts.parse_day")

    # resolved EARLY/LATE days actually present in the intermediate
    present_days = set(int(d) for d in np.unique(day))
    early_present = sorted(d for d in i3.EARLY_DAYS if d in present_days)
    late_present = sorted(d for d in i3.LATE_DAYS if d in present_days)
    truncation_issues = []
    if len(early_present) < len(i3.EARLY_DAYS):
        truncation_issues.append(
            f"EARLY half TRUNCATED: requested {list(i3.EARLY_DAYS)}, resolved "
            f"{early_present}.")
    if len(late_present) < len(i3.LATE_DAYS):
        truncation_issues.append(
            f"LATE half TRUNCATED: requested {list(i3.LATE_DAYS)}, resolved "
            f"{late_present}; a short late half is underpowered.")

    feat_names = book_feature_names()
    nan_drop_book = (float(np.mean(~book_valid)) if book_valid.size else float("nan"))

    # What every number in this file was computed under. Passed to artifact.write, which
    # calls settings.fingerprint with it and stamps the block into _meta. It used to sit
    # inside the payload's own scope block and be copied a second time into a hand-built
    # _meta, so one artifact carried the same record twice.
    settings_used = {
        "h": PRIMARY_HORIZON, "lens": "mid",
        "master_seed": RNG_SEED,
        "n_perm": i3.N_PERM,
        "n_boot": None,
        "rank_floor_fills": list(i3.K_LIST),
        "horizons_scored_s": list(BOOK_HORIZON_KEYS.keys()),
        # Read off i3's resolved halves rather than typed, for the reason the note
        # below gives: the tuples this used to spell out are still the right numbers,
        # but they stopped being typed tuples when i3 moved its cut onto
        # settings.split_early_late, and a caption naming the wrong source outlives
        # the parameter change that invalidated it.
        "early_late_split": (f"inherited from i3, which cuts by "
                             f"settings.split_early_late: early {list(i3.EARLY_DAYS)}, "
                             f"late {list(i3.LATE_DAYS)}"),
        "whale_drop_criterion": "notional",
        "fold_seed_sweep": f"1..{SEED_SWEEP_N}, a separate seed family from "
                           f"master_seed; see seed_robustness",
        "book_feature_seed": CAP_BOOK_SEED,
        "p_floor": H.p_floor(i3.N_PERM),
        # The two numbers in this note are BUILT from what the run drew, because the
        # sentence that stood here had gone stale in the one way a fingerprint must
        # not. It read "n_perm 1000 not the declared 2000, so a p at 0.000999 is the
        # floor", and it survived the raise of the budget: this file draws i3.N_PERM,
        # which is the declared 2000, and the p_floor key stamped three lines above it
        # already read 0.000500 = 1/2001. So one block asserted a budget of 1000 beside
        # its own floor for 2000, and a reader taking the prose had the wrong number
        # while every computed key had the right one. The arithmetic survived the
        # parameter change and the caption did not, which is why neither figure is
        # typed here any more.
        "overrides_note": (
            f"master_seed 20260619 is i3's, re-used so the folds and the placebo "
            f"are identical to the trade-tape run, and it is not "
            f"settings.MASTER_SEED 20260620; n_perm is the declared budget "
            f"{i3.N_PERM}, read from settings.py through i3 and no longer typed, so "
            f"a p at {H.p_floor(i3.N_PERM):.6f} is the floor and is a bound rather "
            f"than a measurement, which placebo_p_is_floor records per cell; no "
            f"bootstrap is drawn, so n_boot does not apply; rank_floor_fills "
            f"(50, 100) is i3's per-half eligibility "
            f"floor, not the declared single 50; the halves are cut by the span and "
            f"rule i3 resolves, which is settings.split_early_late over the days its "
            f"inputs carry; whales "
            f"are dropped by NOTIONAL; the fold-seed sweep draws {SEED_SWEEP_N} "
            f"further seeds that vary ONLY which wallets land in which fold"),
    }
    # The files this run read. The book features are per coin; the cached fill
    # timestamps are recorded whether or not STAGE 2 took that route, because
    # present=false is itself the record of which route ran.
    run_inputs = ([MID_NPZ_PATH]
                  + [os.path.join(P.data_root(), f"book_feats_{c}.npz") for c in coins]
                  + [CACHED_FILLS_PATH])

    results = {
        "object": "I3-BOOK - is per-counterparty toxicity recoverable from the "
                  "FULL PUBLIC ORDER BOOK (not only the trade tape)?",
        # Renamed 2026-07-31 from "scope". The shared writer stamps _meta.scope with
        # the population, window and coins these numbers cover, so leaving this block
        # named "scope" would have put two different questions under one name in one
        # file: what the test was designed to do, and whom it was run over. That is
        # the defect this whole pass exists to remove, and the migration was about to
        # create a fresh instance of it. The old name is recorded beside the new one
        # so a reader holding an earlier copy can pair them.
        "scope_renamed_from": "scope, until 2026-07-31; population moved to _meta.scope",
        "test_design": {
            "early_days": early_present,
            "late_days": late_present,
            "horizons_s": list(BOOK_HORIZON_KEYS.keys()),
            "primary_horizon_s": PRIMARY_HORIZON,
            "K_list": list(i3.K_LIST),
            "n_folds": i3.N_FOLDS, "n_perm": i3.N_PERM,
            "p_floor": H.p_floor(i3.N_PERM),
            "p_floor_note": (
                f"{i3.N_PERM} draws cannot express a p below "
                f"{H.p_floor(i3.N_PERM):.6f}; every cell carries placebo_p_is_floor "
                "saying whether its p is a measurement or that floor"),
            "whale_drop_k": i3.WHALE_DROP_K,
            "markout_reference": (
                f"BOOK MID ({H.headline_mid_col()} primary at the headline window "
                f"{H.HEADLINE_HORIZON_S}s, {H.companion_mid_col()} secondary at the "
                f"companion window {H.COMPANION_HORIZON_S}s; both column names built "
                "from settings.py, neither typed here)"),
            # The settings fingerprint used to be copied in here as well. It now lives
            # in exactly one place, _meta["settings_fingerprint"], and the population,
            # window and coins these numbers cover live in _meta["scope"]. This block
            # is the DESIGN of the test and keeps that job.
            "settings_fingerprint_note": (
                "in _meta.settings_fingerprint; the population, window and coins are "
                "in _meta.scope"),
            "public_info_set": "TRADE TAPE (VPIN / signed-flow imbalance / mean "
            "size / trade intensity) PLUS the FULL PUBLIC L2 BOOK features "
            f"{feat_names} (OFI, multi-level queue imbalance, book-VPIN, "
            "delta-microprice, depth within k bps). NO counterparty identity in any "
            "anonymous predictor.",
            "book_feature_names": feat_names,
            "book_params": {"ofi_levels": OFI_LEVELS, "qimb_levels": list(QIMB_LEVELS),
                            "depth_kbps": list(DEPTH_KBPS),
                            "bvpin_window": BVPIN_WINDOW, "gap_max_ms": GAP_MAX_MS},
            "claim": "if the counterparty history FE STILL adds OUT-OF-SAMPLE lift "
            "over this FULL PUBLIC info set (positive incremental R^2, small placebo "
            "p, FDR survival, whale-robust), per-counterparty toxicity is NOT "
            "recoverable from the public book and needs on-chain identity.",
            "side_source": side_source,
            "book_join_nan_drop_frac": nan_drop_book,
            "row_aligned_to_mid_npz": bool(aligned),
            "stage2_entry_timestamp_source": stage2_source,
        },
        "by_coin": [],
        "pooled": [],
        "issues": list(truncation_issues) + list(join_issues),
    }
    for msg in results["issues"]:
        print(f"[i3book] WARNING: {msg}")

    if not aligned:
        # Without row alignment the book join is meaningless; emit the diagnostic
        # JSON and stop rather than reporting a misleading test.
        results["headline"] = {"aborted": True,
                               "reason": "book join not row-aligned to mid npz"}
        artifact.write(
            os.path.basename(RESULTS_PATH), results,
            script=__file__,
            inputs=run_inputs,
            # The scope of an ABORTED run says so in the population. An aborted file
            # carrying the scope of a completed one is exactly how a diagnostic gets
            # read as a result.
            scope={
                "population": ("ABORTED before any cell was tested: the book join is "
                               f"not row-aligned to {os.path.basename(MID_NPZ_PATH)} "
                               f"({expected_rows:,} rows expected). No wallet was "
                               "scored and no p-value in this file is a measurement"),
                "window": (f"early {early_present} / late {late_present}, "
                           f"day-of-month, out of the {len(days)} days requested"),
                "coins": list(coins),
            },
            settings=settings_used,
            extra_meta={"rng_seed": RNG_SEED, "book_seed": CAP_BOOK_SEED,
                        "markout_source": "mid", "aborted": True},
            started=t0)
        print(f"[i3book] ABORTED (row misalignment) -> "
              f"{os.path.basename(RESULTS_PATH)}")
        return

    # ---------------- STAGE 3: incremental-lift test per cell ----------------
    groups = [(0, "BTC"), (1, "ETH"), (-1, "POOLED")]
    design_store = {}
    for code, label in groups:
        sel = np.ones(taker_id.size, dtype=bool) if code == -1 else (coin == code)
        if sel.sum() == 0:
            results["issues"].append(f"{label}: no rows")
            continue
        g_taker = taker_id[sel]
        g_day = day[sel]
        g_not = notional[sel]
        g_isbuy = is_buy_all[sel]
        g_bookX = book_X[sel]
        g_bookV = book_valid[sel]
        for h in BOOK_HORIZON_KEYS:
            g_mo = mo_by_h[h][sel]
            for K in i3.K_LIST:
                row = run_cell(g_taker, g_day, g_not, g_isbuy, g_mo,
                               g_bookX, g_bookV, early_present, late_present,
                               K, h, label, design_store=design_store)
                (results["pooled"] if code == -1 else results["by_coin"]).append(row)
                print(f"[i3book] {label:<6} h={h:>2}s K={K:>3} "
                      f"n={row.get('n_wallets', 0):>5} "
                      f"incrR2={i3._fmt(row.get('incremental_oos_r2'))} "
                      f"incrSp={i3._fmt(row.get('incremental_spearman'))} "
                      f"placebo_p={i3._fmt(row.get('placebo_p'))} "
                      f"fe_adds={row.get('fe_adds_over_public_book')}")

    # ---------------- BH-FDR over the full cell family ----------------
    all_cells = results["by_coin"] + results["pooled"]
    family_p = []
    for r in all_cells:
        p = r.get("placebo_p")
        family_p.append(float("nan") if (p is None or p != p) else float(p))
    fdr = stats.benjamini_hochberg(
        family_p, alpha=i3.FDR_ALPHA,
        family="i3-book cells: coin (BTC, ETH, POOLED) x horizon x wallet floor K")
    qvals = np.array([np.nan if v is None else float(v) for v in fdr["q"]],
                     dtype=np.float64)
    m_tested = int(fdr["family_size"])
    survivors = []
    for r, q in zip(all_cells, qvals):
        if q != q:
            r["bh_qvalue"] = None
            r["survives_fdr"] = False
        else:
            r["bh_qvalue"] = float(q)
            # A q is p * m / rank, so a q on the permutation floor means the p was floored
            # and the cell held the largest rank: the budget, not the effect.
            r["bh_qvalue_at_p_floor"] = bool(H.p_is_floored(q, i3.N_PERM))
            r["survives_fdr"] = bool(q <= i3.FDR_ALPHA)
            if r["survives_fdr"]:
                survivors.append({"coin": r["coin"], "horizon_s": r["horizon_s"],
                                  "K": r["K"], "placebo_p": r.get("placebo_p"),
                                  "placebo_p_is_floor": bool(r.get("placebo_p_is_floor")),
                                  "bh_qvalue": float(q)})
        # FDR-corrected headline boolean: the FE adds over the public book AND the
        # cell survives multiplicity correction.
        r["fe_adds_over_public_book_fdr"] = bool(
            r.get("fe_adds_over_public_book") and r.get("survives_fdr"))

    results["family"] = {
        "method": "Benjamini-Hochberg FDR over the cell family (coin x horizon x K)",
        "procedure": fdr["procedure"],
        "procedure_note": fdr["method"],
        "fdr_alpha": i3.FDR_ALPHA,
        "n_cells_total": len(all_cells),
        "n_cells_tested": m_tested,
        "n_cells_untestable": len(all_cells) - m_tested,
        "n_survivors": len(survivors),
        "survivors": survivors,
        # The BAR, which the local correction never returned and without which a
        # verdict cannot be read: it is not a constant, it falls with the family size,
        # and this family is not the only one in the work.
        "threshold": fdr["threshold"],
        "threshold_meaning": fdr["threshold_meaning"],
        "rank1_threshold": fdr["rank1_threshold"],
        "smallest_p": fdr["smallest_p"],
        "budget_check": stats.budget_check(i3.N_PERM, m_tested, alpha=i3.FDR_ALPHA),
        "n_cells_with_p_at_floor": sum(1 for r in all_cells
                                       if r.get("placebo_p_is_floor")),
        "floor_note": (
            f"a cell whose p sits on the {i3.N_PERM}-draw floor "
            f"{H.p_floor(i3.N_PERM):.6f} says only that no draw beat the observed lift; "
            "its q inherits that and is not evidence of a smaller p"),
    }

    # ---------------- fold-seed robustness of every cell ----------------
    # Each incremental_oos_r2 above is one draw from a fold-seed distribution. The
    # block below reports the median and the spread for every cell, so prose can
    # quote a stable number instead of a single split.
    stored_by_cell = {(r["coin"], r["horizon_s"], r["K"]):
                      r.get("incremental_oos_r2") for r in all_cells}
    results["seed_robustness"] = seed_robustness(design_store, stored_by_cell)

    # ---------------- HEADLINE: report PER-COIN, do NOT pool ----------------
    # The PRIMARY reported result is PER-COIN (headline_by_coin, below), NOT the
    # pooled cell. BTC and ETH have OPPOSITE book-recoverability at the primary
    # cell: the public book leaves ETH toxicity almost unrecovered (incremental
    # OOS R^2 ~0.47, book-blind) while it largely RECOVERS BTC toxicity
    # (incremental OOS R^2 ~0.06). Pooling averages those two opposite regimes
    # into a single ~0.35 number that describes NEITHER coin. Per the
    # reverification conclusion: NEVER POOL this result - report the per-coin lift
    # (this matches the paper, which states 0.47 ETH / 0.06 BTC). The pooled cell
    # is kept only as a diagnostic and its incremental figures are named
    # pooled_diagnostic_* so they cannot be mistaken for the headline.
    def _find_cell(coin_label, horizon_s, k):
        for r in all_cells:
            if (r["coin"] == coin_label and r["horizon_s"] == horizon_s
                    and r["K"] == k):
                return r
        return None

    prim_h = PRIMARY_HORIZON
    prim_k = min(i3.K_LIST)

    # PRIMARY result: per-coin incremental lift at the primary horizon / smallest K.
    headline_by_coin = []
    for coin_label in ("BTC", "ETH"):
        rc = _find_cell(coin_label, prim_h, prim_k)
        headline_by_coin.append({
            "coin": coin_label,
            "horizon_s": prim_h,
            "K": prim_k,
            "found": rc is not None,
            "incremental_oos_r2": (rc.get("incremental_oos_r2") if rc else None),
            "incremental_spearman": (rc.get("incremental_spearman") if rc else None),
            "placebo_p": (rc.get("placebo_p") if rc else None),
            "placebo_p_is_floor": (bool(rc.get("placebo_p_is_floor")) if rc else False),
            "bh_qvalue": (rc.get("bh_qvalue") if rc else None),
            "survives_fdr": (bool(rc.get("survives_fdr")) if rc else False),
            "whale_robust": (rc.get("whale_robust") if rc else None),
            "fe_adds_over_public_book": (bool(rc.get("fe_adds_over_public_book"))
                                         if rc else False),
            "fe_adds_over_public_book_fdr": (bool(rc.get("fe_adds_over_public_book_fdr"))
                                             if rc else False),
        })
    results["headline_by_coin"] = {
        "is_primary_result": True,
        "pre_registered_cell": {"horizon_s": prim_h, "K": prim_k},
        "rationale": "PRIMARY REPORTED RESULT. Per-coin incremental OOS lift at the "
        f"{prim_h}s K={prim_k} book-mid cell. The coins have OPPOSITE book-"
        "recoverability - the public book leaves ETH toxicity almost unrecovered "
        "(book-blind) but largely recovers BTC toxicity - so this is reported PER "
        "COIN and never pooled. The incremental_oos_r2 shown here is ONE fold split "
        "(the paper's 0.47 ETH / 0.06 BTC are these stored draws); seed_robustness "
        "carries the median and the range over the fold-seed sweep, and its "
        "reporting_rule is to quote that median with its range rather than a single "
        "draw. Read the two together.",
        "by_coin": headline_by_coin,
    }

    # Pooled headline cell: DIAGNOSTIC ONLY (kept for continuity with the i3 pre-
    # registration). Pooling two opposite-sign regimes is misleading, so the pooled
    # incremental figures are named pooled_diagnostic_* and MUST NOT be cited as the
    # result - report headline_by_coin instead.
    headline_cell = {"coin": "POOLED", "horizon_s": prim_h, "K": prim_k}
    headline = _find_cell("POOLED", prim_h, prim_k)
    results["headline"] = {
        "primary_result_is": "headline_by_coin",
        "pooled_is_diagnostic_only": True,
        # POOLED IS A DIAGNOSTIC ONLY - report by_coin; the coins have opposite
        # book-recoverability (ETH book-blind ~0.47, BTC book-recovers ~0.06),
        # pooling is misleading; per reverification never pool.
        "diagnostic_note": "POOLED IS A DIAGNOSTIC ONLY - report headline_by_coin. "
        "The coins have opposite book-recoverability (ETH book-blind ~0.47, BTC "
        "book-recovers ~0.06); pooling averages them into a number describing "
        "neither coin. Per reverification: never pool.",
        "pre_registered_cell": headline_cell,
        "rationale": "Pooled book-mid cell, retained as a DIAGNOSTIC ONLY. Pooling "
        "averages ETH's book-blind regime with BTC's book-recovered regime into a "
        "single value that describes neither coin; cite headline_by_coin instead.",
        "found": headline is not None,
        "pooled_diagnostic_incremental_oos_r2": (headline.get("incremental_oos_r2")
                                                 if headline else None),
        "pooled_diagnostic_incremental_spearman": (headline.get("incremental_spearman")
                                                   if headline else None),
        "placebo_p": (headline.get("placebo_p") if headline else None),
        "placebo_p_is_floor": (bool(headline.get("placebo_p_is_floor"))
                               if headline else False),
        "bh_qvalue": (headline.get("bh_qvalue") if headline else None),
        "survives_fdr": (bool(headline.get("survives_fdr")) if headline else False),
        "whale_robust": (headline.get("whale_robust") if headline else None),
        "fe_adds_over_public_book": (bool(headline.get("fe_adds_over_public_book"))
                                     if headline else False),
        "fe_adds_over_public_book_fdr": (bool(headline.get("fe_adds_over_public_book_fdr"))
                                         if headline else False),
    }

    # The population is the WALLETS the cells were scored on, not the fills the file was
    # built from: every number below is a per-wallet incremental lift, and the fill count
    # would name a population none of them is about. The two floors are both reported, so
    # the range is stated rather than a single one being passed off as the whole.
    cell_wallets = [r.get("n_wallets", 0) for r in all_cells if r.get("n_wallets")]
    artifact.write(
        os.path.basename(RESULTS_PATH), results,
        script=__file__,
        inputs=run_inputs,
        scope={
            "population": (
                f"{len(all_cells)} cells over coin x horizon x wallet floor, of which "
                f"{m_tested} were testable; wallets per cell run "
                f"{min(cell_wallets):,} to {max(cell_wallets):,} at the eligibility "
                f"floors K = {list(i3.K_LIST)} fills in EACH half. Built from "
                f"{expected_rows:,} collapsed taker fills"
                if cell_wallets else
                f"{len(all_cells)} cells, none of which held an eligible wallet"),
            "window": (f"early {early_present} / late {late_present}, day-of-month, "
                       f"out of the {len(days)} days requested; "
                       f"{len(hours)} hours per day"),
            # Never an empty list: an empty scope field reads exactly like a scope
            # covering every coin. CAP_COINS can be set to a list of separators only.
            "coins": list(coins) or "n/a: the resolved coin list is empty",
        },
        settings=settings_used,
        extra_meta={
            "rng_seed": RNG_SEED,
            "book_seed": CAP_BOOK_SEED,
            "markout_source": "mid",
        },
        started=t0)
    _print_summary(results)


def _print_summary(results):
    print("\n" + "=" * 80)
    print("OBJECT I3-BOOK - RECOVERABILITY FROM THE PUBLIC ORDER BOOK - SUMMARY")
    print("=" * 80)
    print("  public info set = TRADE TAPE + FULL PUBLIC L2 BOOK (OFI, queue")
    print("  imbalance, book-VPIN, delta-microprice, depth-within-k-bps). The test")
    print("  asks if the on-chain counterparty FE adds OOS lift ON TOP of all that.")
    sc = results.get("test_design", {})
    print(f"  EARLY {sc.get('early_days')} -> LATE {sc.get('late_days')} | "
          f"book-mid markout ({H.headline_mid_col()} primary at the headline "
          f"{H.HEADLINE_HORIZON_S}s, {H.companion_mid_col()} secondary at the "
          f"companion {H.COMPANION_HORIZON_S}s).")
    print(f"  book-join nan-drop = {i3._fmt(sc.get('book_join_nan_drop_frac'))} | "
          f"row-aligned to mid npz = {sc.get('row_aligned_to_mid_npz')}")
    for msg in results.get("issues", []):
        print(f"  [!] {msg}")
    print("-" * 80)
    header = (f"  {'coin':<6} {'h(s)':>4} {'K':>4} {'n_wal':>6} "
              f"{'incrR2':>9} {'incrSp':>9} {'placebo_p':>10} {'floor':>5} "
              f"{'fe_adds':>8} {'fdr':>5}")
    for block, name in ((results["by_coin"], "PER-COIN"),
                        (results["pooled"], "POOLED")):
        if not block:
            continue
        print(f"  [{name}]")
        print(header)
        for r in block:
            print(f"  {r['coin']:<6} {r['horizon_s']:>4} {r['K']:>4} "
                  f"{r.get('n_wallets', 0):>6} "
                  f"{i3._fmt(r.get('incremental_oos_r2')):>9} "
                  f"{i3._fmt(r.get('incremental_spearman')):>9} "
                  f"{i3._fmt(r.get('placebo_p')):>10} "
                  f"{('yes' if r.get('placebo_p_is_floor') else ''):>5} "
                  f"{str(r.get('fe_adds_over_public_book')):>8} "
                  f"{str(r.get('survives_fdr')):>5}")
    fam = results.get("family")
    if fam:
        print("-" * 80)
        print(f"  BH-FDR (alpha={fam['fdr_alpha']}): "
              f"{fam['n_survivors']} survivors of {fam['n_cells_tested']} testable "
              f"({fam['n_cells_total']} cells).")
    # PRIMARY reported result = PER-COIN. Pooling is misleading here (opposite
    # book-recoverability by coin), so lead with headline_by_coin and print the
    # pooled cell only as a labelled diagnostic.
    hbc = results.get("headline_by_coin")
    if hbc:
        pc = hbc["pre_registered_cell"]
        print("-" * 80)
        print(f"  PRE-REGISTERED HEADLINE (PER-COIN, primary result): "
              f"h={pc['horizon_s']}s K={pc['K']} - NEVER POOLED")
        for bc in hbc.get("by_coin", []):
            print(f"    {bc['coin']:<4} incrR2={i3._fmt(bc.get('incremental_oos_r2'))} "
                  f"incrSp={i3._fmt(bc.get('incremental_spearman'))} "
                  f"placebo_p={i3._fmt(bc.get('placebo_p'))} "
                  f"q={i3._fmt(bc.get('bh_qvalue'))} "
                  f"fe_adds_fdr={bc.get('fe_adds_over_public_book_fdr')}")
        print("    READING: identity adds most where the book is BLIND (ETH), "
              "least where the book RECOVERS toxicity (BTC).")

    sr = results.get("seed_robustness")
    if sr:
        print("-" * 80)
        print(f"  FOLD-SEED ROBUSTNESS ({sr['n_seeds']} seeds, {sr['seed_rule']})")
        print(f"  {'coin':<6} {'h(s)':>4} {'K':>4} {'median':>9} {'min':>9} "
              f"{'max':>9} {'IQR':>8} {'stored':>9} {'pctile':>7}")
        for c in sr["cells"]:
            st = i3._fmt(c.get("stored_single_seed"))
            pc = c.get("stored_percentile")
            pc_s = "n/a" if pc is None else f"{pc:.1f}%"
            print(f"  {c['coin']:<6} {c['horizon_s']:>4} {c['K']:>4} "
                  f"{c['median']:>+9.4f} {c['min']:>+9.4f} {c['max']:>+9.4f} "
                  f"{c['iqr']:>8.4f} {st:>9} {pc_s:>7}")
        for K, p in sorted(sr.get("paired_eth_minus_btc", {}).items()):
            print(f"    paired ETH-BTC h={p['horizon_s']}s K={p['K']}: ETH above BTC "
                  f"in {p['n_seeds_eth_above_btc']}/{p['n_seeds']} seeds, "
                  f"median {p['median']:+.4f}, "
                  f"2.5-97.5% [{p['pctile_2_5']:+.4f}, {p['pctile_97_5']:+.4f}]")
        print("    REPORTING: quote the median with its range, not a single draw; "
              "for the coin gap quote the paired difference.")

    hl = results.get("headline")
    if hl and not hl.get("aborted"):
        c = hl["pre_registered_cell"]
        print("-" * 80)
        print(f"  POOLED CELL (DIAGNOSTIC ONLY - do NOT cite as the headline): "
              f"{c['coin']} h={c['horizon_s']}s K={c['K']}")
        print(f"    pooled_diagnostic_incrR2="
              f"{i3._fmt(hl.get('pooled_diagnostic_incremental_oos_r2'))} "
              f"pooled_diagnostic_incrSp="
              f"{i3._fmt(hl.get('pooled_diagnostic_incremental_spearman'))} "
              f"placebo_p={i3._fmt(hl.get('placebo_p'))} "
              f"q={i3._fmt(hl.get('bh_qvalue'))}")
        print(f"    [!] {hl.get('diagnostic_note')}")
    print("=" * 80)
    print(f"  results -> {os.path.basename(RESULTS_PATH)}")


if __name__ == "__main__":
    main()
