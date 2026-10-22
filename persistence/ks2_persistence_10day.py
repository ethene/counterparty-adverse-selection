"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-19
References:
  - Hyperliquid node-data S3 archive (node_fills_by_block/hourly), s3://hl-mainnet-node-data.
  - Avellaneda, M., Stoikov, S. (2008). "High-frequency trading in a limit order book."
    Quantitative Finance 8(3), 217-224.
  - Cartea, A., Jaimungal, S., et al. Toxic-flow / adverse-selection market-making literature.
  - Spearman-Brown reliability; classical errors-in-variables disattenuation.
"""

# ---------------------------------------------------------------------------
# KILL-SWITCH 2 - DECISIVE persistence test.
#
# The 3-day trade-weighted run found per-counterparty markout toxicity does not
# visibly persist day-to-day, BUT that test was UNDERPOWERED: a per-taker daily
# mean over about K_DAY trades has reliability only ~0.4-0.7, so the attenuation
# ceiling on any day-over-day correlation is ~0.4-0.64 and a latent persistence
# below ~0.3 is invisible. This run settles it with adequate power. The window
# both runs score is the one settings.py declares, so neither this comment nor
# any field below states a window of its own.
#
#   (1) 10 trading days (2025-12-04..13) x {BTC, ETH}, sweep legs collapsed to
#       one obs per (hash, taker) with size-weighted VWAP entry (the fix).
#   (2) WITHIN-PERIOD SPLIT-HALF RELIABILITY: split each taker's trades odd/even,
#       correlate the two half-means across takers, Spearman-Brown up to the full
#       reliability of a period mean. This measures the noise directly.
#   (3) POOLED early(04-08) vs late(09-13) persistence at each K in K_POOL pooled
#       trades per taker per half, with the DISATTENUATED correlation
#       rho_corrected = rho_obs / sqrt(rel_early * rel_late). The reliability in
#       that divisor is the SAME stored value reported in the reliability table
#       (single source, one fixed seed, estimated on the common-taker set), so
#       the headline disattenuated band cannot drift from what is published.
#       Correlation p-values across the {BTC,ETH} x K_POOL family are corrected
#       with a hand-rolled Benjamini-Hochberg (numpy-only) q-value. If the
#       disattenuated persistence is still ~0 with adequate n, the per-counterparty
#       component of markout toxicity does not carry across the split and only the
#       pooled measurement is identifiable; if it is bounded away from zero, that
#       component is identifiable and a wallet's score on one period informs its
#       score on the next.
#   (4) Adjacent-day pairs at K_DAY kept for continuity with the 3-day run, but
#       they are DESCRIPTIVE ONLY (no p-values, some pairs negative) and must NOT
#       be read as a significance panel.
#
# Native nanosecond block_time clock, no book reconstruction. Reference price =
# one VWAP print per distinct hash, as-of (last-at-or-before) join at t+h.
# ---------------------------------------------------------------------------

import argparse
import json
import os
import shutil
import subprocess
import sys
import time

import numpy as np

# The shared modules sit in the repository root, one directory up from this
# group, and this file also imports from the data group. Both are built from this
# file's own location and never from the working directory the run happens to
# start in.
_CODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_CODE_DIR, os.path.join(_CODE_DIR, "data")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import artifact
import panel_io as P
import settings as H
import stats
# Imported for the raw-input SETTING only -- where a downloaded day lives and whether it
# survives the run. Both are read through this module so the declaration has one home;
# nothing else of it is used here, and this file keeps its own parse.
import build_quickwin_markouts as bqm

# -------------------- configuration --------------------
DAYS = ["20251204", "20251205", "20251206", "20251207", "20251208",
        "20251209", "20251210", "20251211", "20251212", "20251213"]
# The coins this window covers, ordered by their code in the quickwin space (see
# COIN_CODES below): the list and the map come from one declaration, so they cannot
# disagree about which coins the artifact holds.
COINS = tuple(sym for _, sym in sorted(H.coin_labels("quickwin").items()))
HORIZONS_S = H.LADDER_S     # every rung an artifact carries a column for
NS_PER_S = 1_000_000_000
ZERO_HASH = "0x" + "0" * 64
S3_BUCKET = "hl-mainnet-node-data"
TMP_DIR = "/tmp"
K_DAY = H.DAY_FLOOR_FILLS       # per-day heterogeneity ratio + adjacent-day persistence
K_POOL = H.PERSISTENCE_FLOOR_FILLS   # pooled early-vs-late persistence thresholds
N_PERM_CORR = H.N_PERM          # permutation draws for the correlation p-values
RNG_RELIABILITY = H.RELIABILITY_SEED  # odd/even reliability split, one fixed seed

# The per-day variance-ratio null draws its own budget, which is NOT the inferential
# N_PERM_CORR above and must not be collapsed into it: those draws are the DENOMINATOR
# of a variance ratio that no threshold is applied to, and 1000 is what that denominator
# needs to be precise. It is read from the declaration under its own purpose name, which
# holds that same 1000, so the budget has one home while staying a separate quantity.
N_PERM = H.perm_draws("ks2_persistence_per_day_variance_ratio")
# One setting this run does NOT take from settings.py, because adopting the declaration
# would move a published number and therefore needs its own recompute rather than a
# rename. It is stamped as a fingerprint override below, so the difference is visible in
# the artifact instead of looking like drift.
SEED_CORR_NULL = 424242    # the correlation permutation null's own seed

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS_PATH = os.path.join(HERE, "ks2_persistence_10day_results.json")
MID_RESULTS_PATH = os.path.join(HERE, "ks2_persistence_mid_results.json")
MID_NPZ_PATH = os.path.join(P.data_root(), "quickwin_markouts_mid.npz")
# The code -> coin map belongs to the FILE, and the mid intermediate is row-aligned
# with the quickwin artifact, so it carries the quickwin map.
COIN_CODES = H.coin_labels("quickwin")


def markout_stat_fields(stats, lens):
    """Per-window descriptive fields for one slice row, keyed through settings.py.

    Why a loop and not a written-out block. The block this replaces named two rungs
    with typed keys and built a third from the headline constant. Once that constant
    became the same window as one of the typed keys, the built key EQUALLED the typed
    one, the second write won, and the companion window's descriptive left the results
    file without raising anything. A loop over the declared ladder cannot collide: one
    key per rung, every key built by settings.field_name, no window typed anywhere.

    `stats` maps horizon -> (mean, median); a rung missing from it yields NaN. `lens`
    says which reference price the values were measured against, and it is part of
    every key because this script writes BOTH lenses into two different files.
    """
    out = {}
    for h in HORIZONS_S:
        mean, median = stats.get(h, (float("nan"), float("nan")))
        out[H.field_name("markout_mean_bps", h, lens=lens)] = mean
        out[H.field_name("markout_median_bps", h, lens=lens)] = median
    return out


def settings_used(lens):
    """What this run USED, in the form artifact.write hands to settings.fingerprint().

    settings.fingerprint() refuses to assert a setting the tree is still migrating
    onto unless the caller says what its own run used, so all four of those are stated
    here from this script's own constants. Two of the four differ from the declaration
    and the difference is deliberate: the per-day variance-ratio null draws fewer
    permutations than the inferential families do, which is why it reads its own
    purpose entry rather than N_PERM, and the correlation null's seed is this script's
    literal rather than the declared master seed, because adopting it would redraw
    every p-value. The wallet floor is the per-day one, which gates a different
    population from the pooled persistence floor. The bootstrap budget is stated as
    not drawn, because this script builds no bootstrap interval at all, and a reader
    should not have to infer that from the declaration.

    Returned as keyword arguments rather than as the finished block so that both of
    this file's two runs state their settings in one place, and so that the block is
    built by the one function that writes artifacts.

    THE TWO PERMUTATION BUDGETS ARE STATED SEPARATELY AND MUST STAY THAT WAY. They
    answer different questions. N_PERM_CORR feeds the correlation p-values, so its size
    fixes the smallest p this run can express and it is sized for the multiplicity
    correction the same p-values then go through. N_PERM feeds ratio_real_over_perm,
    which no threshold is applied to: those draws are the DENOMINATOR of a variance
    ratio, and 1000 is what that denominator needs to be precise. Collapsing the two to
    one number would change one of them.
    """
    return {
        "h": H.HEADLINE_HORIZON_S, "lens": lens,
        "n_perm": {"correlation_null": N_PERM_CORR,
                   "per_day_variance_ratio_null": N_PERM},
        "n_boot": "not drawn: this run builds no bootstrap interval",
        "master_seed": {"correlation_permutation_null": SEED_CORR_NULL,
                        "per_day_variance_ratio_null":
                            "int(day) * 4 + (0 for BTC, 2 for ETH)"},
        "rank_floor_fills": K_DAY,
    }


# -------------------- S3 fetch (hardened: retry + file-count assert) --------------------
# A full day = 24 hourly .lz4. A flaky connection can make `aws s3 cp --recursive`
# exit non-zero (or land only a few hours) on a transient failure; the old code
# treated that as "day absent" and silently dropped it. We now (1) retry the copy,
# (2) assert ~24 hourly files landed before accepting the day, and (3) only call a
# day MISSING after retries are exhausted AND a direct `aws s3 ls` confirms the
# prefix is genuinely empty. (Additive only: the parse/markout/output are unchanged.)
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


def download_day(day):
    """Fetch all hourly .lz4 for `day`, with retry + count assert. Reuses a complete
    local copy when one is present.

    Returns the local dir path (containing <H>.lz4) or None only when the day is
    genuinely absent on S3 (confirmed by a direct `aws s3 ls`).

    THE DIRECTORY NAME IS SHARED WITH build_quickwin_markouts ON PURPOSE. This node and
    that one walk the SAME ten days of the SAME prefix; naming their local copies apart
    (`ks2day_` here against `quickwin_` there) meant one recompute batch downloaded the
    same bytes twice for no reason other than the two names. One name, one copy, and
    whichever node runs first pays for both. The two keys are read through build_quickwin_markouts so
    the declaration has one home: CAP_RAW_CACHE says where, CAP_KEEP_RAW says whether it
    survives the run, and deletion stays the default.
    """
    dst = os.path.join(bqm.raw_cache_dir(), f"quickwin_{day}")
    key = f"s3://{S3_BUCKET}/node_fills_by_block/hourly/{day}/"

    have = [f for f in os.listdir(dst) if f.endswith(".lz4")] if os.path.isdir(dst) else []
    if len(have) >= MIN_DAY_FILES:
        print(f"[ks2] {day}: reused {len(have)} local .lz4 already on disk (CAP_RAW_CACHE)")
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
                print(f"[ks2] {note}")
            if attempt > 1:
                RETRIED_DAYS.append(day)
                print(f"[ks2] {day}: recovered on attempt {attempt} "
                      f"({last_n} files)")
            return dst
        # Not enough files -> transient/partial. Retry with backoff if attempts remain.
        if attempt < S3_RETRIES:
            sleep_s = S3_BACKOFF_S[min(attempt - 1, len(S3_BACKOFF_S) - 1)]
            print(f"[ks2] {day}: attempt {attempt}/{S3_RETRIES} got "
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
        print(f"[ks2] {note}")
        return None
    # Prefix is NOT empty but we could not pull a full day -> transient, not missing.
    note = (f"{day}: pull FAILED ({last_n}/{FULL_DAY_FILES} files) after "
            f"{S3_RETRIES} attempts but prefix is NON-EMPTY - transient, "
            f"NOT labeling MISSING")
    DOWNLOAD_NOTES.append(note)
    print(f"[ks2] {note}")
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

    Collapse: a taker sweep prints several crossed=true legs under one
    (hash, taker_address); accumulate sum(px*sz)/sum(sz) per (hash, taker) and
    emit ONE trade with VWAP entry, shared block_time, shared direction. The
    reference print path is one VWAP per distinct hash.
    """
    day_dir = download_day(day)
    if day_dir is None:
        return None, []

    print_ts_by_hash = {c: {} for c in COINS}
    print_pxsz_by_hash = {c: {} for c in COINS}
    taker_collapsed = {c: {} for c in COINS}
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
                        tc = taker_collapsed[coin]
                        if key not in tc:
                            tc[key] = [px * sz, sz, bt_ns,
                                       1 if f.get("side") == "B" else -1]
                        else:
                            rec = tc[key]
                            rec[0] += px * sz
                            rec[1] += sz
                            if bt_ns < rec[2]:
                                rec[2] = bt_ns
                n_blocks += 1
            hours_ok.append(hour)
        except Exception as exc:
            print(f"[ks2] {day} {hf}: parse error {exc}")
    # Same declared setting as build_quickwin_markouts, read from the one home.
    if bqm.keep_raw_days():
        print(f"[ks2] {day}: raw kept on disk (CAP_KEEP_RAW; see CAP_RAW_CACHE)")
    else:
        shutil.rmtree(day_dir, ignore_errors=True)
        print(f"[ks2] {day}: raw deleted (default; set CAP_KEEP_RAW=1 to keep)")

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

        recs = list(taker_collapsed[c].values())
        keys = list(taker_collapsed[c].keys())
        n = len(recs)
        t_ts = np.empty(n, dtype=np.int64)
        t_px = np.empty(n, dtype=np.float64)
        t_dir = np.empty(n, dtype=np.int8)
        t_addr = np.empty(n, dtype=object)
        for i, (rec, key) in enumerate(zip(recs, keys)):
            pxsz, szsum, ts, d = rec
            t_px[i] = pxsz / szsum
            t_ts[i] = ts
            t_dir[i] = d
            t_addr[i] = key[1]
        per_coin[c] = {"taker_ts": t_ts, "taker_px": t_px, "taker_dir": t_dir,
                       "taker_addr": t_addr, "print_ts": print_ts, "print_px": print_px}
    return per_coin, hours_ok


# -------------------- markout --------------------
def price_at(print_ts, print_px, query_ns):
    idx = np.searchsorted(print_ts, query_ns, side="right") - 1
    out = np.full(query_ns.shape, np.nan, dtype=np.float64)
    valid = idx >= 0
    out[valid] = print_px[idx[valid]]
    return out


def compute_markout60(taker_ts, taker_px, taker_dir, print_ts, print_px):
    if print_ts.size == 0:
        return np.full(taker_ts.shape, np.nan)
    last_print_ns = print_ts[-1]
    tq = taker_ts + 60 * NS_PER_S
    ref = price_at(print_ts, print_px, tq)
    ref[tq > last_print_ns] = np.nan
    return taker_dir.astype(np.float64) * (ref - taker_px) / taker_px * 1e4


def compute_markouts_all(taker_ts, taker_px, taker_dir, print_ts, print_px):
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


# -------------------- per-day heterogeneity ratio --------------------
def heterogeneity_ratio(addr, mo_score, K, rng):
    """V_real / V_perm for the scored markout over takers with >= K trades that day.

    The relabelling is stats.shuffled with no strata, the null "wallet identity carries
    no signal at all", which is the draw this loop always made. THE BUDGET IS N_PERM
    AND NOT N_PERM_CORR: these draws are the denominator of a ratio no threshold is
    applied to, so 1000 buys the precision of V_perm rather than the resolution of a
    p-value. The correlation null next door reports a p and is sized for the correction.
    """
    valid = ~np.isnan(mo_score)
    a, v = addr[valid], mo_score[valid]
    if a.size == 0:
        return 0, float("nan")
    uniq, inv = np.unique(a, return_inverse=True)
    counts = np.bincount(inv)
    eligible = np.where(counts >= K)[0]
    if eligible.size < 2:
        return int(eligible.size), float("nan")

    def gv(labels):
        s = np.bincount(labels, weights=v, minlength=uniq.size)
        c = np.bincount(labels, minlength=uniq.size)
        m = s[eligible] / c[eligible]
        return float(np.var(m))

    v_real = gv(inv)
    perms = np.fromiter((gv(stats.shuffled(inv, rng)) for _ in range(N_PERM)),
                        dtype=np.float64, count=N_PERM)
    v_perm = float(np.mean(perms))
    return int(eligible.size), (v_real / v_perm if v_perm > 0 else float("nan"))


# -------------------- reliability + persistence --------------------
def _rankdata(a):
    a = np.asarray(a, dtype=np.float64)
    order = np.argsort(a, kind="stable")
    ranks = np.empty(a.size, dtype=np.float64)
    sa = a[order]
    i, n = 0, a.size
    while i < n:
        j = i + 1
        while j < n and sa[j] == sa[i]:
            j += 1
        ranks[order[i:j]] = (i + j - 1) / 2.0 + 1.0
        i = j
    return ranks


def spearman(x, y):
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    n = x.size
    if n < 3:
        return float("nan"), n
    rx, ry = _rankdata(x), _rankdata(y)
    rx -= rx.mean(); ry -= ry.mean()
    denom = np.sqrt((rx * rx).sum() * (ry * ry).sum())
    return (float("nan"), n) if denom == 0 else (float((rx * ry).sum() / denom), n)


def spearman_perm_pvalue(x, y, rng, cell, n_perm=N_PERM_CORR):
    """Two-sided permutation p for Spearman rho. Returns (p, block).

    The draws are built here, because the null is this test's own -- one relabelling of
    the late ranking -- and the COUNTING is stats.permutation_p, which owns the floor,
    the side and the record of how many draws were usable. The p that comes back is the
    number this loop always produced: every draw is finite by construction, since a
    permutation of the centred late ranks has the same sum of squares as the observed
    one, so the denominator is constant and positive and the module's usable count
    equals the requested budget. The slack is passed as the absolute 1e-12 this test
    has always applied rather than the module's relative default.

    THE BUDGET IS N_PERM_CORR, the inferential one, and the p it produces goes through
    the multiplicity correction below. The variance-ratio null in heterogeneity_ratio
    draws N_PERM instead; the two are not interchangeable.
    """
    rho0, n = spearman(x, y)
    if n < 3 or rho0 != rho0:
        return float("nan"), None
    rx = _rankdata(x); rx -= rx.mean()
    ry = _rankdata(y); ry -= ry.mean()
    dx = np.sqrt((rx * rx).sum())
    draws = np.empty(int(n_perm), dtype=np.float64)
    for i in range(int(n_perm)):
        ryp = stats.shuffled(ry, rng)
        d = dx * np.sqrt((ryp * ryp).sum())
        draws[i] = (rx * ryp).sum() / d if d > 0 else 0.0
    block = stats.permutation_p(rho0, draws, side="two_sided", abs_tol=1e-12,
                                n_requested=int(n_perm), cell=cell)
    return block["p"], block


def pooled_addr_arrays(store, coin, days):
    """Concatenate (addr, mo_score) over `days` for one coin (NaN markouts dropped)."""
    a_parts, m_parts = [], []
    for d in days:
        s = store.get((coin, d))
        if s is None:
            continue
        valid = ~np.isnan(s["mo_score"])
        a_parts.append(s["addr"][valid]); m_parts.append(s["mo_score"][valid])
    if not a_parts:
        return np.empty(0, dtype=object), np.empty(0, dtype=np.float64)
    return np.concatenate(a_parts), np.concatenate(m_parts)


def taker_means(addr, mo_score, K):
    """addr -> mean markout for takers with >= K observations."""
    if addr.size == 0:
        return {}
    uniq, inv = np.unique(addr, return_inverse=True)
    s = np.bincount(inv, weights=mo_score, minlength=uniq.size)
    c = np.bincount(inv, minlength=uniq.size)
    return {uniq[k]: s[k] / c[k] for k in range(uniq.size) if c[k] >= K}


def split_half_reliability(addr, mo_score, K, rng):
    """Spearman-Brown reliability of a per-taker mean (odd/even within-taker split).

    For takers with >= K obs, randomly split each taker's obs into two halves,
    correlate the two half-means across takers (Spearman), then Spearman-Brown to
    the full-length reliability. Returns (reliability, n_takers, r_half).
    """
    if addr.size == 0:
        return float("nan"), 0, float("nan")
    order = rng.permutation(addr.size)          # randomize before the halving
    a = addr[order]; m = mo_score[order]
    uniq, inv = np.unique(a, return_inverse=True)
    counts = np.bincount(inv, minlength=uniq.size)
    eligible = counts >= K
    # cumulative within-taker index to split each taker's stream in two halves
    o2 = np.argsort(inv, kind="stable")
    inv_s = inv[o2]; m_s = m[o2]
    within = np.zeros(inv_s.size, dtype=np.int64)
    # position of each obs within its taker group
    starts = np.zeros(uniq.size, dtype=np.int64)
    starts[1:] = np.cumsum(counts)[:-1]
    within = np.arange(inv_s.size) - starts[inv_s]
    half = (counts[inv_s] // 2)
    first_half = within < half
    h1_sum = np.bincount(inv_s[first_half], weights=m_s[first_half], minlength=uniq.size)
    h1_cnt = np.bincount(inv_s[first_half], minlength=uniq.size)
    h2_sum = np.bincount(inv_s[~first_half], weights=m_s[~first_half], minlength=uniq.size)
    h2_cnt = np.bincount(inv_s[~first_half], minlength=uniq.size)
    ok = eligible & (h1_cnt > 0) & (h2_cnt > 0)
    if ok.sum() < 3:
        return float("nan"), int(ok.sum()), float("nan")
    x = h1_sum[ok] / h1_cnt[ok]
    y = h2_sum[ok] / h2_cnt[ok]
    r_half, n = spearman(x, y)
    if r_half != r_half:
        return float("nan"), n, float("nan")
    rel = 2 * r_half / (1 + r_half) if (1 + r_half) != 0 else float("nan")
    return rel, n, r_half


def _restrict_to_takers(addr, mo_score, keep):
    """Subset (addr, mo_score) to the observations whose taker is in `keep` (a set)."""
    if addr.size == 0:
        return addr, mo_score
    mask = np.fromiter((a in keep for a in addr), dtype=bool, count=addr.size)
    return addr[mask], mo_score[mask]


def persistence_pooled(store, coin, early, late, K, rel_lookup, rng):
    """Observed + disattenuated day-over-day persistence, early vs late pooled.

    SINGLE RELIABILITY SOURCE: the disattenuation divisor is read from
    `rel_lookup`, the SAME dictionary that feeds the published `reliability`
    table, so the divisor can never silently drift from the reported value.
    Reliability is keyed (coin, half, K) and was estimated on the common-taker
    set (the early-and-late intersecting wallets) used for rho_obs, with ONE
    fixed seed.
    """
    ea, em = pooled_addr_arrays(store, coin, early)
    la, lm = pooled_addr_arrays(store, coin, late)
    means_e = taker_means(ea, em, K)
    means_l = taker_means(la, lm, K)
    common = sorted(set(means_e) & set(means_l))
    out = {"coin": coin, "K": K, "n_counterparties": len(common),
           "spearman_obs": float("nan"), "pvalue": None,
           "rel_early": float("nan"), "rel_late": float("nan"),
           "spearman_disattenuated": float("nan")}
    if len(common) < 3:
        return out
    xe = np.array([means_e[a] for a in common], dtype=np.float64)
    xl = np.array([means_l[a] for a in common], dtype=np.float64)
    rho, n = spearman(xe, xl)
    out["spearman_obs"] = rho
    out["n_counterparties"] = int(n)
    out["pvalue"], out["permutation"] = spearman_perm_pvalue(
        xe, xl, rng, cell=("early_late_rank_persistence", coin, int(K)))
    # divisor is the SAME stored value as the published reliability table
    rel_e = rel_lookup.get((coin, "early", K), float("nan"))
    rel_l = rel_lookup.get((coin, "late", K), float("nan"))
    out["rel_early"], out["rel_late"] = rel_e, rel_l
    # ---- LOW-RELIABILITY GUARD --------------------------------------------
    # The Spearman-Brown reliability rel = 2*r_half/(1+r_half) BLOWS UP for a
    # negative split-half correlation (r_half=-0.9 -> rel=-18), and the
    # disattenuation divides by sqrt(rel_e*rel_l). When a reliability is non-
    # positive, or the underlying split-half r_half is below a small floor, the
    # division is meaningless (sqrt of a non-positive number, or a wildly
    # inflated estimate). In those cases we suppress the disattenuated value
    # (NaN) and emit a flag with the reason instead of dividing. In the current
    # data every r_half is positive and well above the floor (0.18-0.54), so the
    # guard never fires and the published outputs are unchanged.
    R_HALF_FLOOR = 0.1
    rh_e = rel_lookup.get((coin, "early", K, "r_half"), float("nan"))
    rh_l = rel_lookup.get((coin, "late", K, "r_half"), float("nan"))
    rel_ok = (rel_e == rel_e and rel_l == rel_l and rel_e > 0 and rel_l > 0)
    rhalf_ok = (
        (rh_e != rh_e or rh_e > R_HALF_FLOOR)
        and (rh_l != rh_l or rh_l > R_HALF_FLOOR))
    if rel_ok and rhalf_ok:
        out["spearman_disattenuated"] = rho / np.sqrt(rel_e * rel_l)
        out["disatt_suppressed"] = False
    else:
        out["spearman_disattenuated"] = float("nan")
        out["disatt_suppressed"] = True
        if not rel_ok:
            reason = (f"non-positive reliability "
                      f"(rel_early={rel_e}, rel_late={rel_l})")
        else:
            reason = (f"split-half r_half below floor {R_HALF_FLOOR} "
                      f"(r_half_early={rh_e}, r_half_late={rh_l})")
        out["disatt_suppressed_reason"] = reason
    return out


# -------------------- multiple-testing correction --------------------
def fdr_over_persistence(persistence):
    """Correct the persistence family, write each cell its q, and return the summary.

    The step-up correction itself is stats.benjamini_hochberg. The loop this replaces
    was one of six copies of the same procedure in this tree, and the six agree: the
    module's self-test runs this exact spelling against it on 200 random families
    including ties and untestable cells, so the consolidation is shown to move no
    q-value rather than assumed to.

    What the module adds is the THRESHOLD. A verdict without its bar cannot be read at
    all -- "survives correction" means nothing until the number the p was compared
    against is on the page -- and the bar is not a constant: it depends on the family
    size, which is four here and 448 elsewhere in this work at the same level.

    Every key the summary carried before is carried still, with the value it had, so a
    reader loses nothing; threshold, rank1_threshold and n_rejected are new.
    """
    family = stats.benjamini_hochberg(
        [p["pvalue"] for p in persistence], alpha=H.FDR_ALPHA,
        family="persistence_pooled correlation p-values")
    n_survive = 0
    for cell, q in zip(persistence, family["q"]):
        cell["q_value_bh"] = q
        if q is not None and q <= H.FDR_ALPHA:
            n_survive += 1
    return {
        "family": family["family"],
        "family_size": family["family_size"],
        "method": "Benjamini-Hochberg (numpy-only, step-up)",
        "method_detail": family["method"],
        "alpha": family["alpha"],
        "n_survive_q_le_0.05": n_survive,
        "n_perm_corr": N_PERM_CORR,
        "p_floor": stats.p_floor(N_PERM_CORR),
        # The bar the p-values were actually held to, and the bar a single cell has to
        # clear on its own. The permutation budget above is sized against the second.
        "threshold": family["threshold"],
        "rank1_threshold": family["rank1_threshold"],
        "n_rejected": family["n_rejected"],
    }


# -------------------- mid-source store builder (no S3 parse) --------------------
def build_store_from_mid(npz_path):
    """Build the (coin, day) -> {addr, mo_score} store from the L2-mid intermediate.

    For --source mid the heavy S3 parse / sweep-collapse / native-clock markout is
    NOT re-run. Instead the pre-joined mid-price markouts are read from
    quickwin_markouts_mid.npz, which is ROW-ALIGNED with quickwin_markouts.npz.
    The scored column is the book-mid markout at the headline window, named by
    settings.headline_mid_col(), and it replaces the trade-print column of the same
    window used downstream; the persistence / reliability / FDR machinery is
    otherwise identical.

    Returns (store, resolved, slices, issues). `resolved` is the sorted list of
    day-strings ("YYYYMMDD") present in the npz so the early/late split matches the
    trade path's calendar semantics. `addr` is the integer taker_id (a hashable
    per-wallet key, exactly what the persistence code needs).
    """
    if not os.path.exists(npz_path):
        raise SystemExit(
            f"[ks2] mid intermediate not found: {npz_path}\n"
            f"      build quickwin_markouts_mid.npz (i4_midmarkout.py) first.")
    z = np.load(npz_path, allow_pickle=False)
    taker_id = z["taker_id"].astype(np.int64)
    coin = z["coin"].astype(np.int8)
    day = z["day"].astype(np.int64)            # day-of-month 4..13
    # Every rung is named through settings.py, so no column string is typed here, and
    # the whole ladder is read rather than the headline alone: the descriptive table
    # reports the companion window beside the scored one. The scored column is one of
    # these rungs, so it is read once and referred to by the declared horizon.
    cols = {h: z[H.headline_mid_col(h)].astype(np.float64) for h in HORIZONS_S}

    store, slices, issues = {}, [], []
    resolved_set = set()
    for code, clabel in COIN_CODES.items():
        csel = coin == code
        if not csel.any():
            continue
        for dom in np.unique(day[csel]):
            daystr = f"202512{int(dom):02d}"
            resolved_set.add(daystr)
            sel = csel & (day == dom)
            addr = taker_id[sel]
            mo_score = cols[H.HEADLINE_HORIZON_S][sel]   # the scored column
            store[(clabel, daystr)] = {"addr": addr, "mo_score": mo_score}
            # per-day descriptive slice (nan-aware), mirroring the trade path
            stats = {}
            for h in HORIZONS_S:
                g = cols[h][sel]
                g = g[~np.isnan(g)]
                stats[h] = (float(np.mean(g)) if g.size else float("nan"),
                            float(np.median(g)) if g.size else float("nan"))
            rng = np.random.default_rng(int(daystr) * 4 + (0 if clabel == "BTC" else 2))
            n_geK, ratio = heterogeneity_ratio(addr, mo_score, K_DAY, rng)
            slices.append({
                "coin": clabel, "day": daystr, "n_trades": int(addr.size),
                "n_takers": int(np.unique(addr).size),
                "n_takers_geKday": n_geK,
                **markout_stat_fields(stats, lens="mid"),
                "ratio_real_over_perm": ratio,
            })
            print(f"[ks2] SLICE(mid) {clabel} {daystr}: trades={addr.size:,} "
                  f">=K={n_geK} "
                  f"{H.headline_mid_col()}={stats[H.HEADLINE_HORIZON_S][0]:+.4f} "
                  f"{H.companion_mid_col()}={stats[H.COMPANION_HORIZON_S][0]:+.4f} "
                  f"ratio={ratio:.2f}")
    resolved = sorted(resolved_set)
    return store, resolved, slices, issues


# -------------------- main --------------------
def main(source="trade"):
    if source == "mid":
        return main_mid()
    t0 = artifact.start_clock()
    print(f"[ks2] DECISIVE persistence | days={DAYS} coins={COINS} "
          f"K_day={K_DAY} K_pool={K_POOL} "
          f"n_perm_varratio={N_PERM} n_perm_corr={N_PERM_CORR} "
          f"(p-floor=1/{N_PERM_CORR + 1})")

    store = {}            # (coin, day) -> {"addr","mo_score"}
    slices = []
    hours_by_day = {}
    issues = []
    resolved = []

    for day in DAYS:
        per_coin, hours_ok = parse_day(day)
        if per_coin is None:
            issues.append(f"day {day} missing on S3 - skipped")
            continue
        resolved.append(day)
        hours_by_day[day] = hours_ok
        if len(hours_ok) < 24:
            issues.append(f"{day}: {len(hours_ok)}/24 hours")
        for coin in COINS:
            d = per_coin[coin]
            n_trades = int(d["taker_ts"].size)
            if n_trades == 0 or d["print_ts"].size == 0:
                store[(coin, day)] = {"addr": np.empty(0, dtype=object),
                                      "mo_score": np.empty(0, dtype=np.float64)}
                issues.append(f"{coin} {day}: empty")
                continue
            mo = compute_markouts_all(d["taker_ts"], d["taker_px"], d["taker_dir"],
                                      d["print_ts"], d["print_px"])
            mo_score = mo[H.HEADLINE_HORIZON_S]
            store[(coin, day)] = {"addr": d["taker_addr"], "mo_score": mo_score}
            rng = np.random.default_rng(int(day) * 4 + (0 if coin == "BTC" else 2))
            n_geK, ratio = heterogeneity_ratio(d["taker_addr"], mo_score, K_DAY, rng)
            stat = {}
            for h in HORIZONS_S:
                g = mo[h][~np.isnan(mo[h])]
                stat[h] = (float(np.mean(g)) if g.size else float("nan"),
                           float(np.median(g)) if g.size else float("nan"))
            slices.append({
                "coin": coin, "day": day, "n_trades": n_trades,
                "n_takers": int(np.unique(d["taker_addr"]).size),
                "n_takers_geKday": n_geK,
                **markout_stat_fields(stat, lens="print"),
                "ratio_real_over_perm": ratio,
            })
            print(f"[ks2] SLICE {coin} {day}: trades={n_trades:,} "
                  f">=K={n_geK} {H.headline_print_col()}="
                  f"{stat[H.HEADLINE_HORIZON_S][0]:+.4f} ratio={ratio:.2f}")

    # split halves of the resolved window
    half = len(resolved) // 2
    early, late = resolved[:half], resolved[half:]
    print(f"[ks2] early={early} late={late}")

    # ---- SINGLE RELIABILITY SOURCE ----------------------------------------
    # Reliability is estimated ONCE, with ONE fixed seed (RNG_RELIABILITY), on
    # the SAME common-taker set used for rho_obs (the early-and-late intersecting
    # wallets), and stored in rel_lookup. The published `reliability` table and
    # the disattenuation divisor both read from this one dictionary, so the
    # divisor can never drift from the reported value. Estimating on the common
    # set (rather than each full half) keeps the reliability and the observed
    # correlation defined on identical wallets.
    reliability = []
    rel_lookup = {}                      # (coin, half, K) -> stored reliability
    rng_rel = np.random.default_rng(RNG_RELIABILITY)
    for coin in COINS:
        ea_all, em_all = pooled_addr_arrays(store, coin, early)
        la_all, lm_all = pooled_addr_arrays(store, coin, late)
        for K in K_POOL:
            # common-taker set at this K (the wallets entering rho_obs)
            common = set(taker_means(ea_all, em_all, K)) & set(taker_means(la_all, lm_all, K))
            ea_c, em_c = _restrict_to_takers(ea_all, em_all, common)
            la_c, lm_c = _restrict_to_takers(la_all, lm_all, common)
            for label, (ac, mc) in (("early", (ea_c, em_c)), ("late", (la_c, lm_c))):
                rel, n_t, r_half = split_half_reliability(ac, mc, K, rng_rel)
                rel_lookup[(coin, label, K)] = rel
                # store r_half under a 4-tuple key so the low-reliability guard
                # in persistence_pooled can read the underlying split-half corr
                # without altering the (coin, label, K) -> rel divisor lookup
                rel_lookup[(coin, label, K, "r_half")] = r_half
                reliability.append({"coin": coin, "half": label, "K": K,
                                    "reliability": rel, "n_takers": n_t,
                                    "r_half": r_half,
                                    "taker_set": "common (early-and-late intersection)",
                                    "seed": RNG_RELIABILITY})
                print(f"[ks2] RELIAB {coin} {label} K={K}: rel={rel:.3f} "
                      f"n={n_t} r_half={r_half:+.3f} (common-set, seed={RNG_RELIABILITY})")

    # pooled early-vs-late persistence (the decisive test). The disattenuation
    # divisor is read from rel_lookup above (single source); only the correlation
    # permutation null uses this RNG (N_PERM_CORR draws).
    persistence = []
    rng_p = np.random.default_rng(SEED_CORR_NULL)
    for coin in COINS:
        for K in K_POOL:
            res = persistence_pooled(store, coin, early, late, K, rel_lookup, rng_p)
            persistence.append(res)
            dis = res["spearman_disattenuated"]
            dis_s = "nan" if dis != dis else f"{dis:+.3f}"
            pv = "n/a" if res["pvalue"] is None else f"{res['pvalue']:.4f}"
            print(f"[ks2] PERSIST-POOLED {coin} K={K}: obs={res['spearman_obs']:+.4f} "
                  f"disatt={dis_s} relE={res['rel_early']:.3f} relL={res['rel_late']:.3f} "
                  f"n={res['n_counterparties']} p={pv}")

    # ---- BH-FDR over the 4 persistence_pooled cells -----------------------
    # The correlation p-values across the {BTC,ETH} x K_POOL family are corrected
    # step-up. Each cell gets a q-value; the summary reports how many survive q<=alpha
    # and the bar they were held to.
    fdr_summary = fdr_over_persistence(persistence)
    print(f"[ks2] BH-FDR over {fdr_summary['family_size']} persistence cells: "
          f"{fdr_summary['n_survive_q_le_0.05']} survive q<=0.05 "
          f"(p-floor={fdr_summary['p_floor']:.5f}, "
          f"rank-one bar={fdr_summary['rank1_threshold']:.5f})")

    # adjacent-day pairs at K_DAY for continuity
    adjacent = []
    for coin in COINS:
        present = [d for d in resolved if (coin, d) in store]
        for a_d, b_d in zip(present, present[1:]):
            aa, am = pooled_addr_arrays(store, coin, [a_d])
            ba, bm = pooled_addr_arrays(store, coin, [b_d])
            me, ml = taker_means(aa, am, K_DAY), taker_means(ba, bm, K_DAY)
            common = sorted(set(me) & set(ml))
            if len(common) < 3:
                adjacent.append({"coin": coin, "pair": f"{a_d}->{b_d}",
                                 "n": len(common), "spearman": float("nan")})
                continue
            xe = np.array([me[a] for a in common]); xl = np.array([ml[a] for a in common])
            rho, n = spearman(xe, xl)
            adjacent.append({"coin": coin, "pair": f"{a_d}->{b_d}", "n": int(n),
                             "spearman": rho})

    # ---- fold in the S3 retry/partial bookkeeping so truncation is auditable ----
    for note in DOWNLOAD_NOTES:
        if note not in issues:
            issues.append(note)

    # What the numbers cover. The three keys artifact.write requires come first; the
    # rest is what this script has always recorded about its own run and is kept, so
    # nothing a reader used to find here has moved out of the block.
    scope = {"population": (f"counterparties on {len(resolved)} parsed days of the "
                            f"node-fills tape, deduplicated to one observation per "
                            f"(block hash, taker) at a size-weighted VWAP entry; the "
                            f"per-day reads need >= {K_DAY} fills in the day and the "
                            f"pooled early-vs-late reads >= {K_POOL} fills in EACH "
                            f"half"),
             "window": (f"{len(resolved)} days resolved of {len(DAYS)} requested, "
                        f"{resolved[0] if resolved else 'none'} to "
                        f"{resolved[-1] if resolved else 'none'}; early={early}, "
                        f"late={late}"),
             "coins": list(COINS),
             "days_requested": DAYS, "days_resolved": resolved,
             "n_days_resolved": len(resolved),
             "days_retried": sorted(set(RETRIED_DAYS)),
             "download_notes": DOWNLOAD_NOTES,
             "K_day": K_DAY, "K_pool": list(K_POOL),
             # Both permutation counts recorded explicitly, because one key called
             # n_perm could only be right about one of them.
             "n_perm_varratio": N_PERM,        # per-day variance-ratio null
             "n_perm_corr": N_PERM_CORR,       # early-vs-late correlation null
             "p_floor_corr": stats.p_floor(N_PERM_CORR),
             "early": early, "late": late,
             "reliability_seed": RNG_RELIABILITY,
             "reliability_taker_set": "common (early-and-late intersection)",
             "clock_source": "native block_time (ns), node_fills_by_block",
             "dedup": "one obs per (hash, taker), size-weighted VWAP entry",
             "method": "split-half (Spearman-Brown) reliability + disattenuated early-vs-late Spearman"}

    results = {
        "hours_by_day": hours_by_day,
        "slices": slices,
        "reliability": reliability,
        "persistence_pooled": persistence,
        "persistence_pooled_fdr": fdr_summary,
        "persistence_adjacent": adjacent,
        "persistence_adjacent_note": (
            "DESCRIPTIVE ONLY - no p-values are computed for adjacent-day pairs. "
            "These single-day-to-single-day correlations are noisy (3 of 18 pairs "
            "are negative, including BTC 12/05->12/06 = -0.20) and must NOT be read "
            "as a significance panel. The decisive inference is the pooled "
            "early-vs-late test with BH-FDR correction."),
        "_meta": {"n_perm_varratio": N_PERM,
                  "n_perm_corr": N_PERM_CORR,
                  "p_floor_corr": stats.p_floor(N_PERM_CORR)},
        "issues": issues,
    }
    # artifact.write records the producer, the inputs, the scope, the settings block
    # and the runtime in one shape. The inputs are named as the S3 prefixes actually
    # read: the hourly directory of each parsed day is deleted the moment the day is
    # parsed, to stay inside the disk budget, so there is no local file left to hash.
    out_path = artifact.write(
        os.path.basename(RESULTS_PATH), results, script=__file__,
        inputs=[f"s3://{S3_BUCKET}/node_fills_by_block/hourly/{d}/" for d in resolved],
        scope=scope, started=t0, settings=settings_used("print"),
        out_dir=os.path.dirname(RESULTS_PATH))
    runtime_s = artifact.read_meta(out_path)["run"]["runtime_s"]

    # ----- summary -----
    print("\n" + "=" * 76)
    print("KILL-SWITCH 2 - DECISIVE PERSISTENCE (10-day, disattenuated) - SUMMARY")
    print("=" * 76)
    print(f"  days resolved: {len(resolved)}/{len(DAYS)} -> {resolved}")
    if RETRIED_DAYS:
        print(f"  days retried : {sorted(set(RETRIED_DAYS))}")
    print(f"  early={early}  late={late}  K_pool={K_POOL}")
    print("-" * 76)
    print(f"  POOLED early-vs-late persistence (the decisive numbers; "
          f"n_perm_corr={N_PERM_CORR}, p-floor=1/{N_PERM_CORR + 1}):")
    for p in persistence:
        dis = p["spearman_disattenuated"]
        dis_s = "nan" if dis != dis else f"{dis:+.3f}"
        pv = "n/a" if p["pvalue"] is None else f"{p['pvalue']:.4f}"
        qv = p.get("q_value_bh")
        qs = "n/a" if qv is None else f"{qv:.4f}"
        print(f"    {p['coin']} K={p['K']:<3} obs_rho={p['spearman_obs']:+.4f} "
              f"disattenuated={dis_s} (relE={p['rel_early']:.3f} relL={p['rel_late']:.3f}) "
              f"n={p['n_counterparties']} p={pv} q_bh={qs}")
    print(f"  BH-FDR: {fdr_summary['n_survive_q_le_0.05']} of "
          f"{fdr_summary['family_size']} cells survive q<=0.05")
    print("-" * 76)
    print("  adjacent-day pairs: DESCRIPTIVE ONLY (no p-values; not a "
          "significance panel - see persistence_adjacent_note)")
    print("-" * 76)
    print("  per-day heterogeneity ratio (V_real/V_perm):")
    head_key = H.field_name("markout_mean_bps", lens="print")
    for s in slices:
        print(f"    {s['coin']} {s['day']} ratio={s['ratio_real_over_perm']:.2f} "
              f"{head_key}={s[head_key]:+.4f} "
              f"(>=K={s['n_takers_geKday']})")
    if issues:
        print("-" * 76)
        print("  ISSUES:", "; ".join(issues))
    print("=" * 76)
    print(f"  results -> {os.path.basename(RESULTS_PATH)}   "
          f"runtime {runtime_s}s")


# -------------------- main (mid source) --------------------
def main_mid():
    """--source mid: identical persistence machinery on the L2-mid markout.

    Reads quickwin_markouts_mid.npz, scoring on the book-mid column at the headline
    window (settings.headline_mid_col()), builds the same (coin, day) store the trade
    path builds, then runs the SAME reliability, pooled early-vs-late persistence,
    adjacent-day, and BH-FDR steps. Writes ks2_persistence_mid_results.json, whose
    descriptive keys carry the mid lens; the trade output path is untouched.
    """
    t0 = artifact.start_clock()
    print(f"[ks2] DECISIVE persistence (SOURCE=mid) | "
          f"npz={os.path.basename(MID_NPZ_PATH)} coins={COINS} "
          f"K_day={K_DAY} K_pool={K_POOL} "
          f"n_perm_varratio={N_PERM} n_perm_corr={N_PERM_CORR} "
          f"(p-floor=1/{N_PERM_CORR + 1})")

    store, resolved, slices, issues = build_store_from_mid(MID_NPZ_PATH)
    if not resolved:
        raise SystemExit("[ks2] mid intermediate produced no resolved days.")

    half = len(resolved) // 2
    early, late = resolved[:half], resolved[half:]
    print(f"[ks2] early={early} late={late}")

    # ---- SINGLE RELIABILITY SOURCE (common-taker set, one fixed seed) ----
    reliability = []
    rel_lookup = {}
    rng_rel = np.random.default_rng(RNG_RELIABILITY)
    for coin in COINS:
        ea_all, em_all = pooled_addr_arrays(store, coin, early)
        la_all, lm_all = pooled_addr_arrays(store, coin, late)
        for K in K_POOL:
            common = set(taker_means(ea_all, em_all, K)) & set(taker_means(la_all, lm_all, K))
            ea_c, em_c = _restrict_to_takers(ea_all, em_all, common)
            la_c, lm_c = _restrict_to_takers(la_all, lm_all, common)
            for label, (ac, mc) in (("early", (ea_c, em_c)), ("late", (la_c, lm_c))):
                rel, n_t, r_half = split_half_reliability(ac, mc, K, rng_rel)
                rel_lookup[(coin, label, K)] = rel
                # store r_half under a 4-tuple key so the low-reliability guard
                # in persistence_pooled can read the underlying split-half corr
                # without altering the (coin, label, K) -> rel divisor lookup
                rel_lookup[(coin, label, K, "r_half")] = r_half
                reliability.append({"coin": coin, "half": label, "K": K,
                                    "reliability": rel, "n_takers": n_t,
                                    "r_half": r_half,
                                    "taker_set": "common (early-and-late intersection)",
                                    "seed": RNG_RELIABILITY})
                print(f"[ks2] RELIAB(mid) {coin} {label} K={K}: rel={rel:.3f} "
                      f"n={n_t} r_half={r_half:+.3f} (common-set, seed={RNG_RELIABILITY})")

    # pooled early-vs-late persistence (decisive)
    persistence = []
    rng_p = np.random.default_rng(SEED_CORR_NULL)
    for coin in COINS:
        for K in K_POOL:
            res = persistence_pooled(store, coin, early, late, K, rel_lookup, rng_p)
            persistence.append(res)
            dis = res["spearman_disattenuated"]
            dis_s = "nan" if dis != dis else f"{dis:+.3f}"
            pv = "n/a" if res["pvalue"] is None else f"{res['pvalue']:.4f}"
            print(f"[ks2] PERSIST-POOLED(mid) {coin} K={K}: "
                  f"obs={res['spearman_obs']:+.4f} disatt={dis_s} "
                  f"relE={res['rel_early']:.3f} relL={res['rel_late']:.3f} "
                  f"n={res['n_counterparties']} p={pv}")

    fdr_summary = fdr_over_persistence(persistence)
    print(f"[ks2] BH-FDR over {fdr_summary['family_size']} persistence cells: "
          f"{fdr_summary['n_survive_q_le_0.05']} survive q<=0.05 "
          f"(p-floor={fdr_summary['p_floor']:.5f}, "
          f"rank-one bar={fdr_summary['rank1_threshold']:.5f})")

    # adjacent-day pairs (descriptive only)
    adjacent = []
    for coin in COINS:
        present = [d for d in resolved if (coin, d) in store]
        for a_d, b_d in zip(present, present[1:]):
            aa, am = pooled_addr_arrays(store, coin, [a_d])
            ba, bm = pooled_addr_arrays(store, coin, [b_d])
            me, ml = taker_means(aa, am, K_DAY), taker_means(ba, bm, K_DAY)
            common = sorted(set(me) & set(ml))
            if len(common) < 3:
                adjacent.append({"coin": coin, "pair": f"{a_d}->{b_d}",
                                 "n": len(common), "spearman": float("nan")})
                continue
            xe = np.array([me[a] for a in common]); xl = np.array([ml[a] for a in common])
            rho, n = spearman(xe, xl)
            adjacent.append({"coin": coin, "pair": f"{a_d}->{b_d}", "n": int(n),
                             "spearman": rho})

    # What the numbers cover, in the shape artifact.write requires, with everything the
    # mid run has always recorded about itself kept beside the three required keys.
    n_rows_mid = sum(int(s["n_trades"]) for s in slices)
    scope = {"population": (f"{n_rows_mid:,} fills of the row-aligned book-mid "
                            f"intermediate; the per-day reads gate takers at {K_DAY} "
                            f"fills in the day and the pooled early-vs-late reads at "
                            f"{K_POOL} fills in EACH half"),
             "window": (f"{len(resolved)} days resolved, "
                        f"{resolved[0]} to {resolved[-1]}; early={early}, late={late}"),
             "coins": list(COINS),
             "days_requested": DAYS, "days_resolved": resolved,
             "n_days_resolved": len(resolved),
             "markout_source": "mid",
             "input_npz": os.path.basename(MID_NPZ_PATH),
             "K_day": K_DAY, "K_pool": list(K_POOL),
             # Both permutation counts recorded explicitly, because one key called
             # n_perm could only be right about one of them.
             "n_perm_varratio": N_PERM,
             "n_perm_corr": N_PERM_CORR,
             "p_floor_corr": stats.p_floor(N_PERM_CORR),
             "early": early, "late": late,
             "reliability_seed": RNG_RELIABILITY,
             "reliability_taker_set": "common (early-and-late intersection)",
             "clock_source": (f"L2-mid markout ({H.headline_mid_col()}), "
                              "quickwin_markouts_mid.npz"),
             "dedup": "row-aligned with quickwin_markouts.npz (one obs per fill)",
             "method": "split-half (Spearman-Brown) reliability + disattenuated early-vs-late Spearman"}

    results = {
        "slices": slices,
        "reliability": reliability,
        "persistence_pooled": persistence,
        "persistence_pooled_fdr": fdr_summary,
        "persistence_adjacent": adjacent,
        "persistence_adjacent_note": (
            "DESCRIPTIVE ONLY - no p-values are computed for adjacent-day pairs. "
            "The decisive inference is the pooled early-vs-late test with BH-FDR."),
        "_meta": {"markout_source": "mid",
                  "n_perm_varratio": N_PERM,
                  "n_perm_corr": N_PERM_CORR,
                  "p_floor_corr": stats.p_floor(N_PERM_CORR)},
        "issues": issues,
    }
    # The same writer as the trade path, so the two lenses produce two artifacts of one
    # shape and a reader can compare them cell for cell. The input is the row-aligned
    # book-mid intermediate, hashed here, which is the whole input this arm reads: the
    # mid path re-parses nothing from the tape.
    out_path = artifact.write(
        os.path.basename(MID_RESULTS_PATH), results, script=__file__,
        inputs=[os.path.basename(MID_NPZ_PATH)], scope=scope, started=t0,
        settings=settings_used("mid"), out_dir=os.path.dirname(MID_RESULTS_PATH))
    runtime_s = artifact.read_meta(out_path)["run"]["runtime_s"]

    print("\n" + "=" * 76)
    print("KILL-SWITCH 2 - PERSISTENCE (SOURCE=mid, disattenuated) - SUMMARY")
    print("=" * 76)
    print(f"  days resolved: {len(resolved)} -> {resolved}")
    print(f"  early={early}  late={late}  K_pool={K_POOL}")
    print("-" * 76)
    print(f"  POOLED early-vs-late persistence (mid markout; "
          f"n_perm_corr={N_PERM_CORR}, p-floor=1/{N_PERM_CORR + 1}):")
    for p in persistence:
        dis = p["spearman_disattenuated"]
        dis_s = "nan" if dis != dis else f"{dis:+.3f}"
        pv = "n/a" if p["pvalue"] is None else f"{p['pvalue']:.4f}"
        qv = p.get("q_value_bh")
        qs = "n/a" if qv is None else f"{qv:.4f}"
        print(f"    {p['coin']} K={p['K']:<3} obs_rho={p['spearman_obs']:+.4f} "
              f"disattenuated={dis_s} (relE={p['rel_early']:.3f} relL={p['rel_late']:.3f}) "
              f"n={p['n_counterparties']} p={pv} q_bh={qs}")
    print(f"  BH-FDR: {fdr_summary['n_survive_q_le_0.05']} of "
          f"{fdr_summary['family_size']} cells survive q<=0.05")
    if issues:
        print("-" * 76)
        print("  ISSUES:", "; ".join(issues))
    print("=" * 76)
    print(f"  results -> {os.path.basename(MID_RESULTS_PATH)}   "
          f"runtime {runtime_s}s")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="KS2 10-day persistence test.")
    ap.add_argument("--source", choices=("trade", "mid"), default="trade",
                    help="markout reference: 'trade' (default, S3 parse -> "
                         "ks2_persistence_10day_results.json) or 'mid' (reads "
                         "quickwin_markouts_mid.npz mo*_mid -> "
                         "ks2_persistence_mid_results.json).")
    args = ap.parse_args()
    main(source=args.source)
