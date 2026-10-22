"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-19
References: Hyperliquid node-data S3 archive (s3://hl-mainnet-node-data); Zenodo 18184441 (Albers et al. 2026).
"""

# ---------------------------------------------------------------------------
# QUICK-WIN BATCH - single expensive pass.
#
# Reads Hyperliquid node-data (node_fills_by_block/hourly), computes per-fill
# counterparty-resolved adverse-selection markout on the native block_time clock,
# and persists ONE shared intermediate that several cheap consumer scripts read.
#
# The parse, sweep-collapse, and markout are REUSED VERBATIM from
# ks2_persistence_10day.py so the numbers stay consistent with the validated
# persistence run: one observation per (hash, taker) with size-weighted VWAP
# entry; reference price = one VWAP print per distinct hash; native-block_time
# as-of (last-at-or-before) join at t+h for h in {1, 10, 60} seconds.
#
# This script EXTENDS that parse to also carry, per collapsed taker trade:
#   - the fill direction `dir` (Open Long / Open Short / Close Long / Close Short)
#     reduced to is_open in {0, 1},
#   - the signed pre-trade inventory `startPosition`, and
#   - the taker aggressor side `side` reduced to taker_side in {0, 1}
#     (1 if "B" / buy-aggressor, 0 if "A" / sell-aggressor; consistent across legs),
# all taken from the FIRST leg of each (hash, taker) sweep (the leg that opened
# the taker's interaction in that print, by earliest block_time).
#
# It ALSO carries three NEW fields (added for the M4 realized-PnL cross-check and
# the M8 maker-side incidence study):
#   - closed_pnl : SUM of the taker leg's `closedPnl` over the collapsed legs
#     (realized PnL booked when a fill closes/reduces a position; ~0 on opens).
#     Summed across legs so a sweep that closes inventory in several prints books
#     one total realized PnL per collapsed trade.
#   - dir_code   : the fill `dir` of the earliest-block_time leg, mapped to
#     {Open Long:0, Open Short:1, Close Long:2, Close Short:3}; -1 if unknown.
#     (is_open above is just dir_code in {0,1}; dir_code keeps the long/short and
#     open/close detail so M4 can select CLOSE trades.)
#   - maker_id   : integer code of the MAKER-side counterparty = the `crossed=false`
#     leg sharing the same `hash`. A Hyperliquid taker sweep that crosses several
#     resting orders prints one maker leg per crossed order; we keep the maker that
#     supplied the MOST size to this (hash, taker) sweep (size-weighted dominant
#     maker), coded against a separate first-seen maker map (maker_map.json).
#     -1 if no crossed=false leg shared the hash within the parsed hours.
#
# OUTPUT npz schema (quickwin_markouts.npz), one aligned row per collapsed trade:
#   taker_id   int32   integer-coded wallet (first-seen order)
#   coin       int8    0=BTC, 1=ETH
#   day        int16   day-of-month 4..13
#   entry_px   float64 size-weighted VWAP entry price
#   mo1/mo10/mo60  float32  signed taker markout in bps at 1/10/60s
#   notional   float32 total swept size * entry_px (quote units)
#   is_open    int8    1 if dir opens/extends a position, else 0
#   start_pos  float32 signed pre-trade inventory (startPosition)
#   taker_side int8    1 if "B" (buy-aggressor), 0 if "A" (sell-aggressor)
#   closed_pnl float32 sum of taker-leg closedPnl over the collapsed legs
#   dir_code   int8    0=Open Long,1=Open Short,2=Close Long,3=Close Short,-1=unknown
#   maker_id   int32   integer-coded dominant maker-side wallet (crossed=false, same hash); -1 if none
#
# OUTPUT maps:
#   quickwin_taker_map.json  wallet (hex) -> taker int code (first-seen)
#   maker_map.json           wallet (hex) -> maker int code (first-seen)
#
# Run command (bare python3 is BLOCKED on this machine):
#   uv run --no-project --with-requirements requirements.txt python3 data/build_quickwin_markouts.py
# ---------------------------------------------------------------------------

import json
import os
import shutil
import subprocess
import sys
import time

import numpy as np

# artifact.py, settings.py and the other shared modules sit in the
# repository root, one directory up from this group, so the path is built
# from this file's own location and never from the working directory the
# run happens to start in.
_CODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CODE_DIR not in sys.path:
    sys.path.insert(0, _CODE_DIR)
# One place writes a results file, so the pass summary records its producer and hash,
# its inputs, its scope and its settings the way every other artifact does. The two
# wallet maps written beside it are NOT routed through it: they are gitignored lookup
# tables carrying raw hex addresses, not results, and they are deliberately unpublished.
import artifact  # noqa: E402
import panel_io as P  # noqa: E402
import settings as H  # noqa: E402

# -------------------- configuration (the SHARED SPEC) --------------------
DAYS = ["20251204", "20251205", "20251206", "20251207", "20251208",
        "20251209", "20251210", "20251211", "20251212", "20251213"]
# The coin code map is a property of the FILE this builder writes: quickwin_markouts.npz
# carries {0, 1} where panel_markouts.npz carries {0, 1, 2}. Both the list and the map
# come from that one declaration, so the output codes and the coins parsed cannot
# disagree. COIN_CODE is a fresh dict, which matters because the panel drivers extend it
# with SOL at import time and must not reach back into settings.py.
COINS = tuple(sym for _, sym in sorted(H.coin_labels("quickwin").items()))
COIN_CODE = H.coin_codes("quickwin")    # int8 coin code in the output
HORIZONS_S = H.LADDER_S                 # every rung this builder writes a column for
NS_PER_S = 1_000_000_000
ZERO_HASH = "0x" + "0" * 64
S3_BUCKET = "hl-mainnet-node-data"
TMP_DIR = "/tmp"
OPEN_DIRS = {"Open Long", "Open Short"}  # dir values that open/extend a position

# dir string -> int8 code carried as dir_code (so M4 can pick CLOSE trades).
DIR_CODE = {"Open Long": 0, "Open Short": 1, "Close Long": 2, "Close Short": 3}
DIR_UNKNOWN = -1

# Fixed seed so any incidental randomness is deterministic across runs, read from
# settings.py rather than typed. It is NOT settings.MASTER_SEED and is not meant to be:
# 20260619 is the value quickwin_markouts.npz was built under, and nine consumers share
# it, so it is declared per purpose in settings.SEED_BY_PURPOSE and asked for by name.
# Proved equal before the move: the literal here was 20260619 and
# seed_for("build_quickwin_markouts") returns 20260619, so nothing this builder writes
# changes and no stream is redrawn.
RNG_SEED = H.seed_for("build_quickwin_markouts")
np.random.seed(RNG_SEED)

HERE = os.path.dirname(os.path.abspath(__file__))
# The arrays and the two wallet maps live under the declared data root, which stayed at
# the top of the repository when the producers were grouped into directories. The pass
# summary is a results file and stays beside its producer, the way every artifact does.
NPZ_PATH = os.path.join(P.data_root(), "quickwin_markouts.npz")
MAP_PATH = os.path.join(P.data_root(), "quickwin_taker_map.json")
MAKER_MAP_PATH = os.path.join(P.data_root(), "maker_map.json")
SUMMARY_PATH = os.path.join(HERE, "quickwin_pass_summary.json")

# Bare filenames for the paths recorded in _meta / summary. Nothing in this
# repository may carry an absolute path: it names the machine it was run on,
# it is not reproducible for anyone else, and checks/chk_no_abs_paths.py fails
# the build if one appears.
NPZ_NAME = os.path.basename(NPZ_PATH)
MAP_NAME = os.path.basename(MAP_PATH)
MAKER_MAP_NAME = os.path.basename(MAKER_MAP_PATH)
SUMMARY_NAME = os.path.basename(SUMMARY_PATH)


# -------------------- S3 fetch (hardened: retry + file-count assert) --------------------
# A full day = 24 hourly .lz4. A flaky connection can make `aws s3 cp --recursive`
# exit non-zero (or land only a few hours) on a transient failure; the old code
# treated that as "day absent" and silently dropped it. We now (1) retry the copy,
# (2) assert ~24 hourly files landed before accepting the day, and (3) only call a
# day MISSING after retries are exhausted AND a direct `aws s3 ls` confirms the
# prefix is genuinely empty.
S3_RETRIES = 3                 # total attempts at the recursive copy
S3_BACKOFF_S = (5, 15)         # sleep before retry 2 and retry 3 (seconds)
FULL_DAY_FILES = 24            # a complete day = 24 hourly .lz4
MIN_DAY_FILES = 20             # fewer than this = partial pull -> retry

# filled by download_day so main() can report what was retried / how many resolved
DOWNLOAD_NOTES = []            # human-readable per-day notes (retries, partials)
RETRIED_DAYS = []              # days that needed more than one attempt


def _count_lz4(dst):
    return [f for f in os.listdir(dst) if f.endswith(".lz4")] if os.path.isdir(dst) else []


def _s3_prefix_empty(key):
    """True if `aws s3 ls <key>` lists no .lz4 objects (prefix genuinely absent).

    On a listing error (transient), return False so we do NOT mislabel as MISSING.
    """
    try:
        ls = subprocess.run(
            ["aws", "s3", "ls", key, "--request-payer", "requester"],
            capture_output=True, text=True,
        )
    except Exception:
        return False
    if ls.returncode != 0:
        return False
    return ".lz4" not in ls.stdout


def raw_cache_dir():
    """Where a downloaded day lives. CAP_RAW_CACHE overrides; default is the temp dir.

    Declared rather than hard-coded because whether the raw input survives a run is a
    SETTING, not a property of the code. See keep_raw_days()."""
    return os.environ.get("CAP_RAW_CACHE", TMP_DIR)


def keep_raw_days():
    """True when a parsed day is kept on disk instead of deleted. Default False.

    WHY THIS IS A KEY AND NOT A CONSTANT. Deleting each day the moment it is parsed was
    written in when disk was treated as the binding constraint and the tape as freely
    re-fetchable. That made the raw input of this node unhashable -- by the time the
    artifact is written there is nothing left to fingerprint -- so a node walking the
    tape could never be PROVED unchanged, only assumed. It also makes three tape-walking
    nodes in one recompute batch pay three separate downloads of the same ten days.

    Reproducibility is checked by re-running with the inputs present, so the input has to
    be allowed to stay. Deletion remains the DEFAULT, because an unattended run should
    not quietly fill a disk; CAP_KEEP_RAW=1 turns it off, and CAP_RAW_CACHE says where.
    Set both and a day already on disk is reused instead of re-fetched."""
    return os.environ.get("CAP_KEEP_RAW", "").strip() in ("1", "true", "yes", "on")


def download_day(day):
    """Fetch all hourly .lz4 for `day`, with retry + count assert. Reuses a complete
    local copy when one is present, so a second walker over the same day pays nothing.

    Returns the local dir path (containing <H>.lz4) or None only when the day is
    genuinely absent on S3 (confirmed by a direct `aws s3 ls`).
    """
    dst = os.path.join(raw_cache_dir(), f"quickwin_{day}")
    key = f"s3://{S3_BUCKET}/node_fills_by_block/hourly/{day}/"

    # A complete day already on disk is the same bytes S3 would hand back. The count
    # test is the same one that accepts a fresh pull below, so a partial leftover is
    # NOT reused -- it falls through to the retry loop and is re-fetched.
    have = _count_lz4(dst)
    if len(have) >= MIN_DAY_FILES:
        # The note names the COUNT and the setting, never the directory. A cache path is
        # absolute on whatever machine ran the pull, and this note is copied verbatim into
        # the artifact, so writing the path here puts a local absolute path into a results
        # file of a repository whose gate forbids exactly that -- with an exception list
        # that is empty and stays empty. Measured the moment it happened: the first run
        # with the cache enabled wrote a full home-directory path into two of its arrays.
        DOWNLOAD_NOTES.append(
            f"{day}: reused {len(have)} local .lz4 already on disk (CAP_RAW_CACHE)")
        return dst

    last_n = 0
    for attempt in range(1, S3_RETRIES + 1):
        if os.path.isdir(dst):
            shutil.rmtree(dst, ignore_errors=True)
        os.makedirs(dst, exist_ok=True)
        r = subprocess.run(
            ["aws", "s3", "cp", "--recursive", "--request-payer", "requester",
             "--quiet", key, dst],
            capture_output=True, text=True,
        )
        files = _count_lz4(dst)
        last_n = len(files)
        # Accept the day once enough hourly files landed (a clean exit with the
        # full 24, or at least MIN_DAY_FILES so a single dropped hour is tolerated).
        if last_n >= MIN_DAY_FILES:
            if last_n < FULL_DAY_FILES:
                note = f"{day}: accepted partial {last_n}/{FULL_DAY_FILES} files"
                DOWNLOAD_NOTES.append(note)
                print(f"[quickwin] {note}")
            if attempt > 1:
                RETRIED_DAYS.append(day)
                print(f"[quickwin] {day}: recovered on attempt {attempt} "
                      f"({last_n} files)")
            return dst
        # Not enough files -> transient/partial. Retry with backoff if attempts remain.
        if attempt < S3_RETRIES:
            sleep_s = S3_BACKOFF_S[min(attempt - 1, len(S3_BACKOFF_S) - 1)]
            print(f"[quickwin] {day}: attempt {attempt}/{S3_RETRIES} got "
                  f"{last_n}/{FULL_DAY_FILES} files (rc={r.returncode}) - "
                  f"retrying in {sleep_s}s")
            time.sleep(sleep_s)

    # Retries exhausted. Distinguish a truly-absent prefix from a persistent
    # transient failure via a direct listing.
    if day not in RETRIED_DAYS:
        RETRIED_DAYS.append(day)
    if _s3_prefix_empty(key):
        shutil.rmtree(dst, ignore_errors=True)
        note = f"{day}: confirmed ABSENT on S3 (ls empty after {S3_RETRIES} attempts)"
        DOWNLOAD_NOTES.append(note)
        print(f"[quickwin] {note}")
        return None
    # Prefix is NOT empty but we could not pull a full day -> transient, not missing.
    note = (f"{day}: pull FAILED ({last_n}/{FULL_DAY_FILES} files) after "
            f"{S3_RETRIES} attempts but prefix is NON-EMPTY - transient, "
            f"NOT labeling MISSING")
    DOWNLOAD_NOTES.append(note)
    print(f"[quickwin] {note}")
    if last_n > 0:
        # Salvage whatever landed rather than discarding a non-empty partial day.
        return dst
    shutil.rmtree(dst, ignore_errors=True)
    return None


def iter_local_hour_lines(path):
    """Stream-decompress a local .lz4 and yield non-empty JSON block-line strings."""
    proc = subprocess.Popen(
        ["lz4", "-dc", path], stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, text=True, bufsize=1 << 20,
    )
    for line in proc.stdout:
        line = line.strip()
        if line:
            yield line
    proc.wait()


# -------------------- per-day parse + sweep collapse --------------------
def parse_day(day):
    """Parse BTC+ETH fills for `day`, collapsing taker sweeps to one trade.

    Collapse (REUSED from ks2): a taker sweep prints several crossed=true legs
    under one (hash, taker_address); accumulate sum(px*sz)/sum(sz) per
    (hash, taker) and emit ONE trade with VWAP entry, shared block_time, shared
    direction. The reference print path is one VWAP per distinct hash.

    Extension: per (hash, taker) also retain `dir` and `startPosition` from the
    EARLIEST-block_time leg of that taker's sweep (the leg that set the shared
    block_time), so the collapsed trade carries one is_open flag and one signed
    pre-trade inventory consistent with the VWAP entry.

    Further extension (M4 / M8): per (hash, taker) also SUM the taker leg's
    `closedPnl` across the collapsed legs (realized PnL booked on close fills),
    keep the `dir` of the earliest leg as a 4-way dir_code, and resolve the
    MAKER-side counterparty. The maker side is the crossed=false leg(s) under the
    same `hash`; a single taker sweep can cross several resting makers, so we
    accumulate size per maker address PER HASH and, after the hour scan, attach
    to each (hash, taker) trade the maker that supplied the most size to that
    hash (the size-weighted dominant maker).
    """
    day_dir = download_day(day)
    if day_dir is None:
        return None, []

    print_ts_by_hash = {c: {} for c in COINS}
    print_pxsz_by_hash = {c: {} for c in COINS}
    taker_collapsed = {c: {} for c in COINS}
    # maker-side accumulation: per coin, per hash, address -> summed maker size.
    # crossed=false legs sharing a hash are the resting makers a taker swept; we
    # keep the dominant (most-size) maker per hash once the hour scan finishes.
    maker_size_by_hash = {c: {} for c in COINS}
    hours_ok = []

    hour_files = sorted(
        (f for f in os.listdir(day_dir) if f.endswith(".lz4")),
        key=lambda f: int(f.split(".")[0]) if f.split(".")[0].isdigit() else 99,
    )
    for hf in hour_files:
        hour = hf.split(".")[0]
        path = os.path.join(day_dir, hf)
        n_blocks = 0
        try:
            for raw in iter_local_hour_lines(path):
                block = json.loads(raw)
                bt = block.get("block_time")
                if bt is None:
                    continue
                bt_ns = int(np.datetime64(bt, "ns").astype("int64"))
                for ev in block.get("events", []):
                    f = ev[1]
                    coin = f.get("coin")
                    if coin not in print_ts_by_hash:
                        continue
                    h = f.get("hash")
                    if h == ZERO_HASH or h is None:
                        continue
                    px = float(f["px"])
                    sz = float(f["sz"])
                    pt = print_ts_by_hash[coin]
                    if h not in pt:
                        pt[h] = bt_ns
                        print_pxsz_by_hash[coin][h] = [px * sz, sz]
                    else:
                        acc = print_pxsz_by_hash[coin][h]
                        acc[0] += px * sz
                        acc[1] += sz
                    if f.get("crossed") is True:
                        addr = ev[0]
                        key = (h, addr)
                        # is_open / start_pos / dir_code read from THIS leg
                        d_str = f.get("dir")
                        is_open = 1 if d_str in OPEN_DIRS else 0
                        dir_code = DIR_CODE.get(d_str, DIR_UNKNOWN)
                        sp_raw = f.get("startPosition")
                        try:
                            start_pos = float(sp_raw) if sp_raw is not None else float("nan")
                        except (TypeError, ValueError):
                            start_pos = float("nan")
                        # realized PnL booked on this taker leg (closedPnl). Present
                        # on close fills, ~0 on opens; missing/garbage -> 0 so the
                        # per-trade sum stays a clean number.
                        cp_raw = f.get("closedPnl")
                        try:
                            closed_pnl = float(cp_raw) if cp_raw is not None else 0.0
                        except (TypeError, ValueError):
                            closed_pnl = 0.0
                        # taker aggressor side: 1 if "B" (bid/buy-aggressor),
                        # 0 if "A" (ask/sell-aggressor); consistent across the sweep.
                        side_b = 1 if f.get("side") == "B" else 0
                        tc = taker_collapsed[coin]
                        if key not in tc:
                            # [pxsz_sum, sz_sum, min_bt_ns, dir(+1/-1),
                            #  is_open(at min_bt), start_pos(at min_bt), side_b,
                            #  closed_pnl_sum, dir_code(at min_bt)]
                            tc[key] = [px * sz, sz, bt_ns,
                                       1 if f.get("side") == "B" else -1,
                                       is_open, start_pos, side_b,
                                       closed_pnl, dir_code]
                        else:
                            rec = tc[key]
                            rec[0] += px * sz
                            rec[1] += sz
                            rec[7] += closed_pnl   # accumulate realized PnL over legs
                            # keep is_open/start_pos/side/dir_code from earliest leg
                            #
                            # rec[3] IS PART OF "side", AND UNTIL 2026-08-02 IT WAS NOT
                            # UPDATED HERE. The comment above has always said side is
                            # carried from the earliest leg, and rec[6] (side_b) was; but
                            # the sign in rec[3] was left at whatever the FIRST leg seen
                            # in scan order happened to set, which is not the earliest leg
                            # unless the two coincide. rec[3] is the one that leaves this
                            # function as taker_dir and multiplies the trade-print markout,
                            # so a stale sign there flips the sign of a fill's measured
                            # harm on the print lens while the book lens, which reads the
                            # maintained side_b, stays correct. Two fields for one fact is
                            # the defect; keeping both on the same leg is the fix.
                            if bt_ns < rec[2]:
                                rec[2] = bt_ns
                                rec[3] = 1 if side_b else -1
                                rec[4] = is_open
                                rec[5] = start_pos
                                rec[6] = side_b
                                rec[8] = dir_code
                    elif f.get("crossed") is False:
                        # MAKER-side leg: a resting order the taker swept. Accumulate
                        # this maker's supplied size under the shared hash; the
                        # dominant maker per hash is resolved after the hour scan.
                        m_addr = ev[0]
                        msb = maker_size_by_hash[coin]
                        bucket = msb.get(h)
                        if bucket is None:
                            bucket = {}
                            msb[h] = bucket
                        bucket[m_addr] = bucket.get(m_addr, 0.0) + sz
                n_blocks += 1
            hours_ok.append(hour)
        except Exception as exc:
            print(f"[quickwin] {day} {hf}: parse error {exc}")
    # Deletion is the default and is DECLARED, not wired in: see keep_raw_days(). The
    # line is printed either way, so a reader of the run log can tell which happened
    # without inferring it from a missing directory.
    if keep_raw_days():
        print(f"[quickwin] {day}: raw kept on disk (CAP_KEEP_RAW; see CAP_RAW_CACHE)")
    else:
        shutil.rmtree(day_dir, ignore_errors=True)
        print(f"[quickwin] {day}: raw deleted (default; set CAP_KEEP_RAW=1 to keep)")

    per_coin = {}
    for c in COINS:
        hashes = list(print_ts_by_hash[c].keys())
        if hashes:
            p_ts = np.fromiter((print_ts_by_hash[c][h] for h in hashes),
                               dtype=np.int64, count=len(hashes))
            p_px = np.fromiter((print_pxsz_by_hash[c][h][0] / print_pxsz_by_hash[c][h][1]
                                for h in hashes), dtype=np.float64, count=len(hashes))
            order = np.argsort(p_ts, kind="stable")
            print_ts, print_px = p_ts[order], p_px[order]
        else:
            print_ts = np.empty(0, dtype=np.int64)
            print_px = np.empty(0, dtype=np.float64)

        # resolve the dominant maker per hash: the crossed=false address that
        # supplied the most size under that hash. One per hash, reused for every
        # (hash, taker) collapsed trade. None if no maker leg shared the hash.
        msb = maker_size_by_hash[c]
        dominant_maker = {}
        for hh, bucket in msb.items():
            dominant_maker[hh] = max(bucket.items(), key=lambda kv: kv[1])[0]

        recs = list(taker_collapsed[c].values())
        keys = list(taker_collapsed[c].keys())
        n = len(recs)
        t_ts = np.empty(n, dtype=np.int64)
        t_px = np.empty(n, dtype=np.float64)
        t_dir = np.empty(n, dtype=np.int8)
        t_addr = np.empty(n, dtype=object)
        t_open = np.empty(n, dtype=np.int8)
        t_spos = np.empty(n, dtype=np.float64)
        t_size = np.empty(n, dtype=np.float64)        # total swept size per trade
        t_side = np.empty(n, dtype=np.int8)           # 1 if "B", 0 if "A"
        t_cpnl = np.empty(n, dtype=np.float64)        # summed taker closedPnl
        t_dcode = np.empty(n, dtype=np.int8)          # 4-way dir_code (-1 unknown)
        t_maddr = np.empty(n, dtype=object)           # dominant maker addr or None
        for i, (rec, key) in enumerate(zip(recs, keys)):
            pxsz, szsum, ts, d, is_open, start_pos, side_b, closed_pnl, dir_code = rec
            t_px[i] = pxsz / szsum
            t_ts[i] = ts
            t_dir[i] = d
            t_addr[i] = key[1]
            t_open[i] = is_open
            t_spos[i] = start_pos
            t_size[i] = szsum
            t_side[i] = side_b
            t_cpnl[i] = closed_pnl
            t_dcode[i] = dir_code
            t_maddr[i] = dominant_maker.get(key[0])   # key[0] = hash; None if none
        per_coin[c] = {"taker_ts": t_ts, "taker_px": t_px, "taker_dir": t_dir,
                       "taker_addr": t_addr, "taker_open": t_open,
                       "taker_spos": t_spos, "taker_size": t_size,
                       "taker_side": t_side,
                       "taker_cpnl": t_cpnl, "taker_dcode": t_dcode,
                       "maker_addr": t_maddr,
                       "print_ts": print_ts, "print_px": print_px}
    return per_coin, hours_ok


# -------------------- markout (REUSED verbatim from ks2) --------------------
def price_at(print_ts, print_px, query_ns):
    idx = np.searchsorted(print_ts, query_ns, side="right") - 1
    out = np.full(query_ns.shape, np.nan, dtype=np.float64)
    valid = idx >= 0
    out[valid] = print_px[idx[valid]]
    return out


def compute_markouts_all(taker_ts, taker_px, taker_dir, print_ts, print_px):
    """Signed taker markout in bps at each horizon (REUSED from ks2).

    Positive = taker profited = maker bore adverse selection.
    """
    out = {}
    if print_ts.size == 0:
        return {h: np.full(taker_ts.shape, np.nan) for h in HORIZONS_S}
    last_print_ns = print_ts[-1]
    for h in HORIZONS_S:
        tq = taker_ts + h * NS_PER_S
        ref = price_at(print_ts, print_px, tq)
        ref[tq > last_print_ns] = np.nan
        out[h] = taker_dir.astype(np.float64) * (ref - taker_px) / taker_px * 1e4
    return out


# -------------------- main --------------------
def main():
    t0 = artifact.start_clock()
    print(f"[quickwin] single expensive pass | days={DAYS} coins={COINS} "
          f"horizons={HORIZONS_S}s")

    # accumulators for the aligned 1-D output columns (one row per collapsed trade)
    col_addr = []        # raw wallet string (mapped to int code at the end)
    col_coin = []        # int8 coin code
    col_day = []         # int16 day-of-month (4..13)
    col_entry_px = []    # float64 VWAP entry
    col_mo1 = []         # float32 bps
    col_mo10 = []        # float32 bps
    col_mo60 = []        # float32 bps
    col_notional = []    # float32 size * entry_px (quote units)
    col_is_open = []     # int8
    col_start_pos = []   # float32 signed pre-trade inventory
    col_taker_side = []  # int8: 1 if "B" (buy-aggressor), 0 if "A" (sell-aggressor)
    col_closed_pnl = []  # float32 summed taker-leg closedPnl over collapsed legs
    col_dir_code = []    # int8 4-way dir code (-1 unknown)
    col_maker_addr = []  # raw maker wallet string or None (mapped to int at the end)

    pass_slices = []     # per coin-day diagnostics for the summary
    hours_by_day = {}
    issues = []
    resolved = []

    for day in DAYS:
        day_num = int(day[6:8])          # 4..13
        per_coin, hours_ok = parse_day(day)
        if per_coin is None:
            issues.append(f"day {day} missing on S3 - skipped")
            print(f"[quickwin] day {day} MISSING on S3 - skipped")
            continue
        resolved.append(day)
        hours_by_day[day] = hours_ok
        if len(hours_ok) < 24:
            issues.append(f"{day}: {len(hours_ok)}/24 hours")

        for coin in COINS:
            d = per_coin[coin]
            n_trades = int(d["taker_ts"].size)
            if n_trades == 0 or d["print_ts"].size == 0:
                pass_slices.append({"coin": coin, "day": day_num,
                                    "collapsed_trades": 0, "rows_kept": 0})
                issues.append(f"{coin} {day}: empty")
                print(f"[quickwin] SLICE {coin} {day}: empty")
                continue

            mo = compute_markouts_all(d["taker_ts"], d["taker_px"], d["taker_dir"],
                                      d["print_ts"], d["print_px"])
            mo1, mo10, mo60 = mo[1], mo[10], mo[60]

            # notional in quote units = total swept size * VWAP entry price.
            notional = d["taker_size"] * d["taker_px"]

            n_rows = n_trades
            col_addr.extend(d["taker_addr"].tolist())
            col_coin.extend([COIN_CODE[coin]] * n_rows)
            col_day.extend([day_num] * n_rows)
            col_entry_px.extend(d["taker_px"].tolist())
            col_mo1.extend(mo1.tolist())
            col_mo10.extend(mo10.tolist())
            col_mo60.extend(mo60.tolist())
            col_notional.extend(notional.tolist())
            col_is_open.extend(d["taker_open"].tolist())
            col_start_pos.extend(d["taker_spos"].tolist())
            col_taker_side.extend(d["taker_side"].tolist())
            col_closed_pnl.extend(d["taker_cpnl"].tolist())
            col_dir_code.extend(d["taker_dcode"].tolist())
            col_maker_addr.extend(d["maker_addr"].tolist())

            # slice diagnostics
            g1 = mo1[~np.isnan(mo1)]
            g10 = mo10[~np.isnan(mo10)]
            g60 = mo60[~np.isnan(mo60)]
            pass_slices.append({
                "coin": coin, "day": day_num,
                "collapsed_trades": n_trades, "rows_kept": n_rows,
                "mo1_mean_bps": float(np.mean(g1)) if g1.size else float("nan"),
                "mo10_mean_bps": float(np.mean(g10)) if g10.size else float("nan"),
                "mo60_mean_bps": float(np.mean(g60)) if g60.size else float("nan"),
            })
            print(f"[quickwin] SLICE {coin} {day}: trades={n_trades:,} "
                  f"mo1={pass_slices[-1]['mo1_mean_bps']:+.4f} "
                  f"mo10={pass_slices[-1]['mo10_mean_bps']:+.4f} "
                  f"mo60={pass_slices[-1]['mo60_mean_bps']:+.4f}")

    # ---- integer-code the wallets (deterministic: first-seen order) ----
    wallet_to_code = {}
    taker_id = np.empty(len(col_addr), dtype=np.int32)
    for i, w in enumerate(col_addr):
        code = wallet_to_code.get(w)
        if code is None:
            code = len(wallet_to_code)
            wallet_to_code[w] = code
        taker_id[i] = code

    # ---- integer-code the MAKERS in a SEPARATE first-seen map ----
    # A None maker (no crossed=false leg shared the hash) codes to -1 and is NOT
    # added to the map. Maker codes are independent of taker codes by design.
    maker_to_code = {}
    maker_id = np.empty(len(col_maker_addr), dtype=np.int32)
    for i, w in enumerate(col_maker_addr):
        if w is None:
            maker_id[i] = -1
            continue
        code = maker_to_code.get(w)
        if code is None:
            code = len(maker_to_code)
            maker_to_code[w] = code
        maker_id[i] = code

    # ---- assemble aligned 1-D arrays with the SPEC dtypes ----
    coin_arr = np.asarray(col_coin, dtype=np.int8)
    day_arr = np.asarray(col_day, dtype=np.int16)
    entry_px_arr = np.asarray(col_entry_px, dtype=np.float64)
    mo1_arr = np.asarray(col_mo1, dtype=np.float32)
    mo10_arr = np.asarray(col_mo10, dtype=np.float32)
    mo60_arr = np.asarray(col_mo60, dtype=np.float32)
    notional_arr = np.asarray(col_notional, dtype=np.float32)
    is_open_arr = np.asarray(col_is_open, dtype=np.int8)
    start_pos_arr = np.asarray(col_start_pos, dtype=np.float32)
    taker_side_arr = np.asarray(col_taker_side, dtype=np.int8)
    closed_pnl_arr = np.asarray(col_closed_pnl, dtype=np.float32)
    dir_code_arr = np.asarray(col_dir_code, dtype=np.int8)

    np.savez_compressed(
        NPZ_PATH,
        taker_id=taker_id,
        coin=coin_arr,
        day=day_arr,
        entry_px=entry_px_arr,
        mo1=mo1_arr,
        mo10=mo10_arr,
        mo60=mo60_arr,
        notional=notional_arr,
        is_open=is_open_arr,
        start_pos=start_pos_arr,
        taker_side=taker_side_arr,
        closed_pnl=closed_pnl_arr,
        dir_code=dir_code_arr,
        maker_id=maker_id,
    )

    # OUTPUT 2: taker map. Direction documented in the JSON itself.
    taker_map = {
        "_direction": "wallet (hex string) -> integer code (int32, first-seen order)",
        "map": wallet_to_code,
    }
    with open(MAP_PATH, "w") as fh:
        json.dump(taker_map, fh)

    # OUTPUT 3: maker map (separate code space; -1 in the array means no maker leg).
    maker_map = {
        "_direction": "maker wallet (hex string) -> integer code (int32, first-seen "
                       "order); array value -1 = no crossed=false leg shared the hash",
        "map": maker_to_code,
    }
    with open(MAKER_MAP_PATH, "w") as fh:
        json.dump(maker_map, fh)

    # ---- per-coin sanity means over the full output ----
    total_rows = int(taker_id.size)
    per_coin_summary = {}
    for coin, code in COIN_CODE.items():
        sel = coin_arr == code
        n_c = int(sel.sum())
        m1 = mo1_arr[sel]
        m10 = mo10_arr[sel]
        m60 = mo60_arr[sel]

        def _mean(a):
            a = a[~np.isnan(a)]
            return float(np.mean(a)) if a.size else float("nan")

        per_coin_summary[coin] = {
            "rows": n_c,
            "mo1_mean_bps": _mean(m1),
            "mo10_mean_bps": _mean(m10),
            "mo60_mean_bps": _mean(m60),
        }

    # ---- fold in the S3 retry/partial bookkeeping so truncation is auditable ----
    for note in DOWNLOAD_NOTES:
        if note not in issues:
            issues.append(note)

    # Kept for the console line only. The recorded elapsed time now lives in exactly one
    # place, _meta["run"]["runtime_s"], which is the container a leaf-by-leaf comparison
    # of two runs skips; a second copy in the payload would make every recompute differ
    # outside that container and stop the comparison being read.
    runtime_s = round(time.time() - t0, 1)
    summary = {
        "config": {
            "days_requested": DAYS,
            "days_resolved": resolved,
            "n_days_resolved": len(resolved),
            "days_retried": sorted(set(RETRIED_DAYS)),
            "download_notes": DOWNLOAD_NOTES,
            "coins": list(COINS),
            "coin_code": COIN_CODE,
            "horizons_s": list(HORIZONS_S),
            "clock_source": "native block_time (ns), node_fills_by_block",
            "dedup": "one obs per (hash, taker), size-weighted VWAP entry",
            "markout_sign": "signed taker markout bps; positive = taker profited = maker adverse-selected",
            "rng_seed": RNG_SEED,
            "npz_path": NPZ_NAME,
            "map_path": MAP_NAME,
            "maker_map_path": MAKER_MAP_NAME,
            "summary_path": SUMMARY_NAME,
            "extra_fields": {
                "closed_pnl": "sum of taker-leg closedPnl over collapsed legs (float32)",
                "dir_code": "0=Open Long,1=Open Short,2=Close Long,3=Close Short,-1=unknown",
                "maker_id": "first-seen maker code (crossed=false, same hash); -1 if none",
            },
        },
        "hours_by_day": hours_by_day,
        "slices": pass_slices,
        "total_rows": total_rows,
        "rows_per_coin": {c: per_coin_summary[c]["rows"] for c in COIN_CODE},
        "n_unique_takers": len(wallet_to_code),
        "n_unique_makers": len(maker_to_code),
        "n_rows_no_maker": int((maker_id == -1).sum()),
        "per_coin": per_coin_summary,
        "issues": issues,
    }
    # The hourly directories this pass pulled are deleted the moment they are parsed --
    # the system disk cannot hold ten days of them -- so what identifies an input here
    # is the bucket key, which artifact.input_record keeps whole for that reason. The
    # local files it reads are none: everything comes off S3 and is discarded.
    artifact.write(
        SUMMARY_NAME, summary,
        script=__file__,
        inputs=[f"s3://{S3_BUCKET}/node_fills_by_block/hourly/{d}/" for d in resolved],
        scope={
            "population": (
                f"{total_rows:,} collapsed taker trades, one row per (hash, taker) "
                f"sweep with a size-weighted VWAP entry, over "
                f"{len(wallet_to_code):,} distinct taker wallets and "
                f"{len(maker_to_code):,} distinct makers; no wallet floor and no "
                f"eligibility filter is applied by this pass"),
            "window": (f"{len(resolved)} of {len(DAYS)} requested days resolved: "
                       f"{', '.join(resolved) if resolved else 'none'}"),
            "coins": list(COINS),
        },
        # A PRODUCER: it writes a column for every rung of settings.LADDER_S and selects
        # no scoring window, so horizon_s is stamped at the headline for reference only
        # and horizons_written_s is the list that describes the artifact.
        settings={
            "h": H.HEADLINE_HORIZON_S, "lens": "print",
            "master_seed": RNG_SEED,
            "horizons_written_s": list(HORIZONS_S),
            "n_perm": None,
            "n_boot": None,
            "rank_floor_fills": None,
            "override_reasons": {
                "horizon_s": ("this pass marks every rung and scores at none; the "
                              "headline window is stamped so the artifact can be "
                              "compared with the analysis files that do score, and "
                              "horizons_written_s is what the npz actually carries"),
                "master_seed": (f"the module fixes numpy's global seed at {RNG_SEED}, "
                                f"not the declared {H.MASTER_SEED}. Nothing in this "
                                f"pass draws from it -- the parse, the collapse and the "
                                f"markout join are deterministic -- so it is recorded "
                                f"as what the run set rather than as what it used"),
                "n_perm": "no permutation test and no bootstrap run in this pass",
                "n_boot": "see n_perm",
                "rank_floor_fills": ("no wallet floor applies: this pass emits every "
                                     "collapsed trade and the consumers gate their own "
                                     "populations"),
            },
        },
        started=t0)

    # ---- concise console summary ----
    print("\n" + "=" * 76)
    print("QUICK-WIN MARKOUT PASS - SUMMARY")
    print("=" * 76)
    print(f"  days resolved : {len(resolved)}/{len(DAYS)} -> {resolved}")
    if RETRIED_DAYS:
        print(f"  days retried  : {sorted(set(RETRIED_DAYS))}")
    print(f"  total rows    : {total_rows:,}")
    for coin in COIN_CODE:
        pc = per_coin_summary[coin]
        print(f"  {coin}: rows={pc['rows']:,}  "
              f"mo1={pc['mo1_mean_bps']:+.4f}  "
              f"mo10={pc['mo10_mean_bps']:+.4f}  "
              f"mo60={pc['mo60_mean_bps']:+.4f}  (bps)")
    print(f"  unique takers : {len(wallet_to_code):,}")
    print(f"  unique makers : {len(maker_to_code):,}  "
          f"(rows w/o maker: {int((maker_id == -1).sum()):,})")
    if issues:
        print("  ISSUES        :", "; ".join(issues))
    print("-" * 76)
    print(f"  npz       -> {NPZ_NAME}")
    print(f"  taker map -> {MAP_NAME}")
    print(f"  maker map -> {MAKER_MAP_NAME}")
    print(f"  summary   -> {SUMMARY_NAME}")
    print(f"  runtime   -> {runtime_s}s")
    print("=" * 76)


if __name__ == "__main__":
    main()
