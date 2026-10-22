"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-20
References: Hyperliquid market-data L2 book S3 archive (s3://hyperliquid-archive/market_data); Zenodo 18184441 (Albers et al. 2026).
"""

# ---------------------------------------------------------------------------
# I4 ARTIFACT 1 - mid_series_{COIN}.npz
#
# Streams the Hyperliquid L2 book snapshots for BTC and ETH over the Dec 4-13
# 2025 window, and builds a per-coin time series of mid / spread / top-5 imbalance
# / micro-price that the markout joiner (i4_midmarkout.py) consumes.
#
# Per the shared data contract, each output .npz holds arrays SORTED ASC by t_ms
# with duplicate t_ms collapsed (keep last):
#   t_ms   int64   snapshot epoch-ms = raw.data.time
#   mid    float64 (best_bid_px + best_ask_px)/2
#   spread float64 best_ask_px - best_bid_px
#   imb    float64 (sumBidSz_top5 - sumAskSz_top5)/(sumBidSz_top5 + sumAskSz_top5)
#   micro  float64 (best_bid_px*best_ask_sz + best_ask_px*best_bid_sz)/(best_bid_sz + best_ask_sz)
#
# Streaming discipline: one l2Book lz4 file is decompressed and parsed at a time,
# its per-snapshot rows appended into growing python lists, and the raw text is
# released before the next file. Numpy arrays are materialised once at the end.
# A missing/empty hour file is skipped with a warning (download is attempted
# first per the contract).
# ---------------------------------------------------------------------------

import json
import os
import subprocess
import sys

import numpy as np

# artifact.py, settings.py and the other shared modules sit in the
# repository root, one directory up from this group, so the path is built
# from this file's own location and never from the working directory the
# run happens to start in.
_CODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CODE_DIR not in sys.path:
    sys.path.insert(0, _CODE_DIR)
import settings as H  # noqa: E402

SEED = H.MASTER_SEED  # the declared seed; this file already ran on it, so reading it
                      # from settings.py moves no number
np.random.seed(SEED)  # deterministic; no RNG is used but the seed is fixed per contract.

# --- paths / window from the shared contract ------------------------------
CODE_DIR = os.path.dirname(os.path.abspath(__file__))
# CAP_L2_CACHE lets the panel driver point at its own cache dir so a multi-window
# pull cannot disturb the December cache. Default is the December location, which sits
# beside the repository rather than inside it: the climb starts at the repository root
# and not at this file's group directory, or it would name a directory of the code.
L2_CACHE = os.environ.get(
    "CAP_L2_CACHE", os.path.join(_CODE_DIR, "..", "02_data", "l2_cache"))
S3_BUCKET = "s3://hyperliquid-archive/market_data"

DEFAULT_DAYS = [
    "20251204", "20251205", "20251206", "20251207", "20251208",
    "20251209", "20251210", "20251211", "20251212", "20251213",
]
DEFAULT_HOURS = list(range(24))  # 0..23, no zero pad
# The coins this builder walks, asked for by STORE rather than typed. What it opens is
# l2_cache/<day>/<hour>/l2Book/<COIN>.lz4, so the store has no integer codes and the
# question is which SYMBOLS its leaves carry; settings.coin_symbols is the accessor for
# that question and a code map inverted here would be an empty set. It stays a list
# because CAP_COINS overrides it with one. Proved equal before the move: the literal
# here was ["BTC", "ETH"] and coin_symbols("l2_cache") returns ("BTC", "ETH").
DEFAULT_COINS = list(H.coin_symbols("l2_cache"))


def _env_list(name, default):
    raw = os.environ.get(name)
    if not raw:
        return default
    return [tok.strip() for tok in raw.split(",") if tok.strip()]


def resolve_window():
    days = _env_list("CAP_DAYS", DEFAULT_DAYS)
    hours_raw = _env_list("CAP_HOURS", [str(h) for h in DEFAULT_HOURS])
    hours = [int(h) for h in hours_raw]
    coins = _env_list("CAP_COINS", DEFAULT_COINS)
    return days, hours, coins


def local_path(day, hour, coin):
    return os.path.join(L2_CACHE, day, str(hour), "l2Book", f"{coin}.lz4")


def ensure_file(day, hour, coin):
    """Read local-first; download the single missing l2Book lz4 per contract.
    Returns the path if present (after any download), else None."""
    path = local_path(day, hour, coin)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    s3_uri = f"{S3_BUCKET}/{day}/{hour}/l2Book/{coin}.lz4"
    try:
        subprocess.run(
            ["aws", "s3", "cp", s3_uri, path, "--request-payer", "requester"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        msg = getattr(exc, "stderr", b"")
        if isinstance(msg, bytes):
            msg = msg.decode("utf-8", "replace").strip()
        print(f"  [warn] download failed {day}/{hour}/{coin}: {msg or exc}", file=sys.stderr)
        return None
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    print(f"  [warn] file missing after download attempt: {path}", file=sys.stderr)
    return None


def decompress(path):
    """Decompress an lz4 file to bytes. Try the lz4 CLI; fall back to unlz4,
    then to the python lz4 module if importable. Returns bytes or None."""
    for cmd in (["lz4", "-dc", path], ["unlz4", "-c", path]):
        try:
            proc = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return proc.stdout
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
    try:
        import lz4.frame as lz4f  # type: ignore

        with open(path, "rb") as fh:
            return lz4f.decompress(fh.read())
    except Exception as exc:  # noqa: BLE001 - want to warn, not crash the whole run.
        print(f"  [warn] lz4 decode failed for {path}: {exc}", file=sys.stderr)
        return None


def parse_file(raw_bytes, t_list, mid_list, spr_list, imb_list, mic_list):
    """Parse one decompressed l2Book file, appending one row per valid snapshot.
    Mutates the passed lists in place. Returns the number of rows added."""
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
            bb_px = float(bids[0]["px"])
            ba_px = float(asks[0]["px"])
            bb_sz = float(bids[0]["sz"])
            ba_sz = float(asks[0]["sz"])
        except (ValueError, KeyError, IndexError, TypeError):
            continue

        mid = 0.5 * (bb_px + ba_px)
        spread = ba_px - bb_px

        # top-5 depth imbalance
        sum_bid = 0.0
        for lvl in bids[:5]:
            try:
                sum_bid += float(lvl["sz"])
            except (ValueError, KeyError, TypeError):
                pass
        sum_ask = 0.0
        for lvl in asks[:5]:
            try:
                sum_ask += float(lvl["sz"])
            except (ValueError, KeyError, TypeError):
                pass
        denom = sum_bid + sum_ask
        imb = (sum_bid - sum_ask) / denom if denom > 0 else 0.0

        # micro-price weights each side by the OPPOSITE size (contract formula)
        sz_denom = bb_sz + ba_sz
        if sz_denom > 0:
            micro = (bb_px * ba_sz + ba_px * bb_sz) / sz_denom
        else:
            micro = mid

        t_list.append(t_ms)
        mid_list.append(mid)
        spr_list.append(spread)
        imb_list.append(imb)
        mic_list.append(micro)
        added += 1
    return added


def build_coin(coin, days, hours):
    t_list, mid_list, spr_list, imb_list, mic_list = [], [], [], [], []
    files_ok = 0
    files_skipped = 0
    for day in days:
        for hour in hours:
            path = ensure_file(day, hour, coin)
            if path is None:
                files_skipped += 1
                continue
            raw = decompress(path)
            if raw is None:
                files_skipped += 1
                continue
            n = parse_file(raw, t_list, mid_list, spr_list, imb_list, mic_list)
            del raw  # release the decompressed text before the next file
            if n == 0:
                print(f"  [warn] no parseable snapshots in {day}/{hour}/{coin}", file=sys.stderr)
            files_ok += 1

    if not t_list:
        print(f"  [warn] {coin}: no snapshots collected; skipping save", file=sys.stderr)
        return None, files_ok, files_skipped

    t_ms = np.asarray(t_list, dtype=np.int64)
    mid = np.asarray(mid_list, dtype=np.float64)
    spread = np.asarray(spr_list, dtype=np.float64)
    imb = np.asarray(imb_list, dtype=np.float64)
    micro = np.asarray(mic_list, dtype=np.float64)

    # SORT ASC by t_ms; stable so that for equal t_ms the later file/line wins
    # after we collapse-keeping-last below.
    order = np.argsort(t_ms, kind="stable")
    t_ms = t_ms[order]
    mid = mid[order]
    spread = spread[order]
    imb = imb[order]
    micro = micro[order]

    # collapse duplicate t_ms keeping LAST occurrence. With ascending stable sort,
    # the last index of each run is the one whose next neighbour differs (or the end).
    keep = np.ones(t_ms.shape[0], dtype=bool)
    keep[:-1] = t_ms[1:] != t_ms[:-1]
    t_ms = t_ms[keep]
    mid = mid[keep]
    spread = spread[keep]
    imb = imb[keep]
    micro = micro[keep]

    # CAP_MID_SUFFIX lets a non-December window write beside the December artifact
    # instead of overwriting it (e.g. "_202508" -> mid_series_BTC_202508.npz). Empty
    # by default, so the December BTC/ETH build is byte-identical to before.
    suffix = os.environ.get("CAP_MID_SUFFIX", "")
    # Under the declared data root, which stayed at the top of the repository when the
    # producers were grouped into directories, and where every reader of this family
    # looks for it. The file name stays the last component of the join, because that is
    # what build.py folds this script's output edge out of.
    out = os.path.join(_CODE_DIR, f"mid_series_{coin}{suffix}.npz")
    np.savez(out, t_ms=t_ms, mid=mid, spread=spread, imb=imb, micro=micro)

    # --- per-coin summary --------------------------------------------------
    if t_ms.shape[0] > 1:
        gaps_s = np.diff(t_ms) / 1000.0
        med_gap = float(np.median(gaps_s))
    else:
        med_gap = float("nan")
    print(
        f"  {coin}: {t_ms.shape[0]} snapshots "
        f"(raw {len(t_list)}, dropped {len(t_list) - t_ms.shape[0]} dup t_ms) | "
        f"files ok {files_ok} skipped {files_skipped}"
    )
    print(
        f"  {coin}: median gap {med_gap:.3f} s | "
        f"price range [{mid.min():.2f}, {mid.max():.2f}] | "
        f"t_ms [{int(t_ms.min())}, {int(t_ms.max())}] | saved {out}"
    )
    return out, files_ok, files_skipped


def main():
    days, hours, coins = resolve_window()
    print(
        f"[i4_l2_mid] window days={len(days)} hours={len(hours)} coins={coins} seed={SEED}"
    )
    for coin in coins:
        print(f"[i4_l2_mid] building {coin} ...")
        build_coin(coin, days, hours)
    print("[i4_l2_mid] done")


if __name__ == "__main__":
    main()
