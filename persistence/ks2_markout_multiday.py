"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-19
References:
  - Hyperliquid node-data S3 archive (node_fills_by_block/hourly), s3://hl-mainnet-node-data.
  - Avellaneda, M., Stoikov, S. (2008). "High-frequency trading in a limit order book."
    Quantitative Finance 8(3), 217-224.
  - Cartea, A., Jaimungal, S., et al. Toxic-flow / adverse-selection market-making literature.
"""

# ---------------------------------------------------------------------------
# KILL-SWITCH 2 (multi-day, two-asset, TRADE-WEIGHTED rebuild).
#
# This upgrades the lean per-fill KS2 in three ways:
#
#   (1) SWEEP-WEIGHT FIX. The lean script counted every crossed=true leg
#       separately. A multi-level taker sweep prints SEVERAL crossed=true legs
#       under the SAME hash + same block_time + same taker address (one per
#       price level it ate). That over-counts a single economic decision ~3.4x
#       and lets a wide sweep dominate the markout average. Here we COLLAPSE to
#       ONE observation per (hash, taker_address): the entry price is the
#       size-weighted VWAP over that taker's legs in the hash, total size is the
#       leg-size sum, the block_time and taker direction are shared. Markout is
#       computed ONCE per collapsed taker trade.
#
#   (2) SCOPE. Three days (2025-12-04/05/06) x two coins (BTC, ETH). Each
#       hourly node_fills file is ALL-COIN, so one download per hour serves both
#       coins; we filter to {BTC,ETH} in memory and, by default, delete each
#       hour before fetching the next. That default is the declared key
#       CAP_KEEP_RAW, read from build_quickwin_markouts, and CAP_RAW_CACHE says
#       where a kept hour lives.
#
#   (3) PERSISTENCE TEST. Per coin we measure whether per-counterparty toxicity
#       is a stable trait: the Spearman rank correlation of each taker's mean
#       collapsed-trade markout at the scoring window settings.py declares,
#       across day pairs (04 vs 05, 05 vs 06) and a pooled early(04+05) vs
#       late(06) check, restricted to takers with >= K fills in BOTH legs.
#       Positive + significant => persistent counterparty toxicity (not one-day
#       luck). The descriptive table beside it reports every rung of the ladder,
#       the companion window included.
#
# The reference price path is UNCHANGED from the lean script: one VWAP print per
# distinct trade hash, ascending by block_time, with an as-of (last-at-or-before)
# join at t+h. Native nanosecond block_time clock, no book reconstruction.
#
# A DEBT THAT WAS OPENED AND IS NOW PAID, kept here because the shape of it recurs.
# ks2_multiday_results.json was first written 2026-07-30 in the older results shape, with
# no _meta block: it named no producer and recorded no hash, so the freshness question
# could not be PUT to it at all, let alone answered. Two moves followed -- the write
# became a call to the shared artifact writer, and the hourly teardown became the
# declared CAP_KEEP_RAW branch with the fetched hour landing where the other tape
# walkers look -- and the run of 2026-08-11 rewrote the artifact through that writer.
# It now names this file and carries its sha256, so the question is a hash comparison.
#
# THE PRICE, both figures recorded rather than guessed. The 30 July run wrote 1210.7 s
# into its own results file: three days, twenty-four hours each, download included. The
# 2026-08-11 run wrote 63.801 s for the same three days with the hours already on disk.
# The gap between them is the download, and it is the reason CAP_KEEP_RAW exists.
#
# WHAT IS STILL NOT ANSWERABLE, and it is not the producer. All three declared inputs of
# this node are hourly prefixes of the raw archive, recorded with sha256 null. A node
# whose input cannot be hashed cannot be PROVEN unchanged, only assumed, so no comparison
# of producer bytes closes the question by itself. Keeping the parsed days under
# CAP_KEEP_RAW is what turns that assumption back into a measurement.
# ---------------------------------------------------------------------------

import json
import os
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
import settings as H
import stats
# Imported for the raw-input SETTING only -- where a fetched hour lives and whether it
# survives the run. Both keys are read through this module so the declaration has one
# home; nothing else of it is used here, and this file keeps its own parse.
import build_quickwin_markouts as bqm

# -------------------- configuration --------------------
DAYS = ["20251204", "20251205", "20251206"]
FALLBACK_DAYS = ["20251207", "20251208", "20251209"]  # if a target day is missing
# The coins this window covers, ordered by their code in the quickwin space: this run
# parses the same two coins the quickwin artifact holds, so the list is taken from that
# artifact's declared map rather than typed a second time.
COINS = tuple(sym for _, sym in sorted(H.coin_labels("quickwin").items()))
HORIZONS_S = H.LADDER_S              # every rung an artifact carries a column for
NS_PER_S = 1_000_000_000
ZERO_HASH = "0x" + "0" * 64          # sentinel hash; not a joinable trade
S3_BUCKET = "hl-mainnet-node-data"
# No local TMP_DIR constant here on purpose: where a fetched hour lands is the declared
# setting CAP_RAW_CACHE, and it is read through build_quickwin_markouts.raw_cache_dir()
# so that one file holds the default. A constant here would be a second home for it.
# One floor gates two different populations here: the per-day heterogeneity read,
# where it is the declared per-day floor, and the pooled early-vs-late pairs, where
# the declared persistence floor is higher. The second use is stamped as a
# fingerprint override so the artifact says which population it gated.
FILL_THRESHOLD_K = H.DAY_FLOOR_FILLS
N_PERM_CORR = H.N_PERM               # permutation draws for the correlation p-values
MAX_RETRIES = 2

# THE TWO PERMUTATION BUDGETS IN THIS FILE ARE DIFFERENT QUANTITIES, WHICH IS WHY THEY
# ARE READ FROM DIFFERENT PLACES AND WHY THE SMALLER ONE IS NOT A SHORTFALL.
#
# N_PERM_CORR above is settings.N_PERM, and it is the budget of draws that BECOME a
# p-value. That budget is not chosen: settings.min_perm_draws computes it from the level
# and the family size, because the p-value floor 1/(N+1) has to survive the multiplicity
# correction or no cell can be significant at any effect size.
#
# N_PERM below is 1000 and answers a different question, so the inequality that sizes the
# budget above has nothing to bind on here. These draws are averaged into v_perm, and
# v_perm is the DENOMINATOR of the variance ratio V_real / V_perm. No threshold is applied
# to that ratio and no p is reported from it, so what the draws buy is the precision of a
# denominator rather than the resolution of a p-value. It is therefore read from the
# per-purpose map, under the name of what it is for, and not from the headline budget.
N_PERM = H.perm_draws("ks2_markout_per_day_variance_ratio")
# The one setting this run still does NOT take from settings.py, because adopting a
# declaration would move a published number and therefore needs its own recompute rather
# than a rename. It is stamped as a fingerprint override below, so the difference is
# visible in the artifact instead of looking like drift.
#
# It cannot be read yet for a second reason that is worth stating plainly: settings.py
# declares a seed per named PURPOSE, and there is no purpose declared for this file's
# correlation null. The value 424242 that stands here is also what
# panel_persistence.py's correlation null draws, but the two are different consumers and
# reading one consumer's seed under another consumer's name is the confusion the
# per-purpose map exists to prevent. Closing this site means adding an entry to
# settings.SEED_BY_PURPOSE, not pointing this line at somebody else's entry.
SEED_CORR_NULL = 424242              # the persistence permutation null's own seed

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS_PATH = os.path.join(HERE, "ks2_multiday_results.json")


def markout_stat_fields(mo_stats):
    """Per-window descriptive fields for one slice row, keyed through settings.py.

    Why a loop and not a written-out block. The block this replaces named two rungs
    with typed keys and built the third from the headline constant. Once that constant
    became the same window as one of the typed keys, the built key EQUALLED the typed
    one, the second write won, and the companion window's mean, median and count left
    the results file without raising anything. A loop over the declared ladder cannot
    collide: one key per rung, every key built by settings.field_name, no window typed
    anywhere. This file measures against the trade print only, so the lens is not part
    of the key; it is stamped once in the fingerprint.

    `mo_stats` maps horizon -> (mean, median, n); a rung missing from it yields NaN
    with a count of zero, which is what a slice with no joinable trade carries.
    """
    out = {}
    for h in HORIZONS_S:
        mean, median, n = mo_stats.get(h, (float("nan"), float("nan"), 0))
        out[H.field_name("markout_mean_bps", h)] = mean
        out[H.field_name("markout_median_bps", h)] = median
        out[H.field_name("n_markout", h)] = n
    return out


def settings_used():
    """What this run USED, in the form artifact.write hands to settings.fingerprint().

    settings.fingerprint() refuses to assert a setting the tree is still migrating
    onto unless the caller says what its own run used, so all four of those are stated
    here from this script's own constants. The variance-ratio null draws fewer
    permutations than the inferential families do, and the permutation seeds are this
    script's literals rather than the declared master seed, because adopting it would
    redraw every p-value; both differences are deliberate. The bootstrap budget is
    stated as not drawn, because this script builds no bootstrap interval at all.
    Both wallet floors are the per-day one, and the pooled floor is passed too: it is
    asserted directly by the block, so leaving it out would have the artifact claim
    the declared floor gated its pairs when the per-day floor did.

    THE TWO PERMUTATION BUDGETS ARE STATED SEPARATELY AND MUST STAY THAT WAY. They
    answer different questions. N_PERM_CORR feeds a p-value, so its size fixes the
    smallest p the run can express and it is sized for the multiplicity correction.
    N_PERM feeds ratio_real_over_perm, which has no threshold at all: the draws there
    form the DENOMINATOR of a variance ratio, and 1000 is what that denominator needs
    to be precise. Collapsing them to one number would change one of the two.

    Returned as keyword arguments rather than as the finished block so the block is
    built by the one function that writes artifacts.
    """
    return {
        "h": H.HEADLINE_HORIZON_S, "lens": "print",
        "n_perm": {"persistence_correlation_null": N_PERM_CORR,
                   "per_day_variance_ratio_null": N_PERM},
        "n_boot": "not drawn: this run builds no bootstrap interval",
        "master_seed": {"persistence_correlation_null": SEED_CORR_NULL,
                        "per_day_variance_ratio_null":
                            "int(day) + (0 for BTC, 1 for ETH)"},
        "rank_floor_fills": FILL_THRESHOLD_K,
        "persistence_floor_fills": [FILL_THRESHOLD_K],
    }


# -------------------- S3 fetch + decompress (streamed) --------------------
def s3_day_has_files(day):
    """Return True if the S3 hourly folder for `day` exists and is non-empty."""
    key = f"s3://{S3_BUCKET}/node_fills_by_block/hourly/{day}/"
    r = subprocess.run(
        ["aws", "s3", "ls", "--request-payer", "requester", key],
        capture_output=True, text=True,
    )
    return r.returncode == 0 and bool(r.stdout.strip())


def fetch_hour_lines(day, hour):
    """Fetch one hourly .lz4, stream-decompress, yield JSON block-line strings.

    WHERE THE FILE LANDS AND WHETHER IT SURVIVES ARE THE SAME DECLARED SETTING THE
    OTHER TAPE WALKERS READ, and both are taken from build_quickwin_markouts rather
    than restated here, so the rule has one home. Deletion stays the DEFAULT, because
    an unattended run should not quietly fill a disk; CAP_KEEP_RAW=1 turns it off and
    CAP_RAW_CACHE says where. Keeping the day is what makes the raw input hashable at
    the moment the artifact is written, which is the only way a node that walks the
    tape can be PROVED unchanged rather than assumed so.

    THE DIRECTORY NAME IS SHARED WITH build_quickwin_markouts ON PURPOSE, and this file
    used to be the exception. It wrote one flat `hl_<day>_<hour>.lz4` into /tmp, so an
    hour already on disk from another walker was invisible to it and an hour it kept was
    invisible to them -- three nodes covering overlapping days paid three downloads of
    identical bytes. The three days here sit inside the ten those nodes walk, so the hour
    now goes to `quickwin_<day>/<hour>.lz4` under the declared cache root, which is the
    layout their download_day builds and reads.

    Raises on failure so the caller can retry/skip.
    """
    key = f"s3://{S3_BUCKET}/node_fills_by_block/hourly/{day}/{hour}.lz4"
    day_dir = os.path.join(bqm.raw_cache_dir(), f"quickwin_{day}")
    os.makedirs(day_dir, exist_ok=True)
    lz4_path = os.path.join(day_dir, f"{hour}.lz4")

    if os.path.exists(lz4_path) and os.path.getsize(lz4_path) > 0:
        # The note names the hour and the setting, never the directory: a cache path is
        # absolute on whatever machine ran the pull, and this tree's gate forbids an
        # absolute path in any tracked file with an exception list that stays empty.
        print(f"[ks2] {day}/{hour}: reused local .lz4 already on disk (CAP_RAW_CACHE)")
    else:
        cp = subprocess.run(
            ["aws", "s3", "cp", "--request-payer", "requester", "--quiet",
             key, lz4_path],
            capture_output=True, text=True,
        )
        if cp.returncode != 0:
            # A partial object left behind would be "already on disk" to the next
            # attempt, and all three retries would then read the same broken bytes.
            try:
                os.remove(lz4_path)
            except OSError:
                pass
            raise RuntimeError(f"s3 cp failed {day}/{hour}: {cp.stderr.strip()[:200]}")

    readable = True
    try:
        proc = subprocess.Popen(
            ["lz4", "-dc", lz4_path],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
            bufsize=1 << 20,
        )
        for line in proc.stdout:
            line = line.strip()
            if line:
                yield line
        proc.wait()
        if proc.returncode not in (0, None):
            raise RuntimeError(f"lz4 decompress failed {day}/{hour}")
    except Exception:
        # A file that will not decompress is not a cache entry, so it goes even when the
        # keep key is set. This is cleanup after a failure, not a second copy of the
        # deletion rule: the rule still decides every case where the read succeeded, and
        # the branch below still asks it by calling it.
        readable = False
        raise
    finally:
        # Deletion is the DEFAULT and it is DECLARED. The key is CALLED in the test
        # rather than read into a variable further up, because a gate written as a bare
        # name is a gate no reader of this file -- and no instrument over it -- can tie
        # to the setting it stands for. Printed either way, so the run log says which
        # happened rather than leaving it to be inferred from a file that is not there.
        if readable and bqm.keep_raw_days():
            print(f"[ks2] {day}/{hour}: raw kept on disk "
                  f"(CAP_KEEP_RAW; see CAP_RAW_CACHE)")
        else:
            try:
                os.remove(lz4_path)
            except OSError:
                pass
            print(f"[ks2] {day}/{hour}: raw deleted "
                  + ("(default; set CAP_KEEP_RAW=1 to keep)" if readable
                     else "(it would not decompress, so it is not a cache entry)"))


# -------------------- per-(day, coin) parse + collapse --------------------
def parse_day(day):
    """Parse all BTC+ETH fills for `day`, collapsing taker sweeps to one trade.

    For each coin, returns a dict with collapsed taker-trade arrays and the
    distinct-hash reference price path. The collapse: a taker sweep prints
    several crossed=true legs under one (hash, taker_address); we accumulate
    sum(px*sz) and sum(sz) per (hash, taker) key and emit ONE trade with
    entry = VWAP = sum(px*sz)/sum(sz), shared block_time, shared direction.

    Returns:
      per_coin[coin] = {
        "taker_ts":  int64[n]   block_time ns per collapsed taker trade
        "taker_px":  float64[n] VWAP entry price
        "taker_dir": int8[n]    +1 if side=='B' else -1
        "taker_sz":  float64[n] total swept size
        "taker_addr":object[n]  taker address
        "print_ts":  int64[m]   ascending block_time ns of each distinct print
        "print_px":  float64[m] VWAP price of that print
      }
      hours_ok[coin] is shared (same files); also a few sample collapsed trades.
    """
    # reference print path (one VWAP per hash) -- per coin
    print_ts_by_hash = {c: {} for c in COINS}
    print_pxsz_by_hash = {c: {} for c in COINS}
    # collapsed taker trades keyed by (hash, taker_addr) -- per coin
    # value = [sum(px*sz), sum(sz), block_ts_ns, dir, addr]
    taker_collapsed = {c: {} for c in COINS}
    hours_ok = []
    samples = []

    for hour in range(24):
        ok = False
        for attempt in range(MAX_RETRIES + 1):
            n_blocks = 0
            n_fill = {c: 0 for c in COINS}
            try:
                for raw in fetch_hour_lines(day, hour):
                    block = json.loads(raw)
                    bt = block.get("block_time")
                    if bt is None:
                        continue
                    bt_ns = int(np.datetime64(bt, "ns").astype("int64"))
                    for ev in block.get("events", []):
                        f = ev[1]
                        coin = f.get("coin")
                        if coin not in print_ts_by_hash:  # not BTC/ETH
                            continue
                        h = f.get("hash")
                        if h == ZERO_HASH or h is None:
                            continue
                        n_fill[coin] += 1
                        px = float(f["px"])
                        sz = float(f["sz"])
                        # reference print path (one VWAP per hash, all legs)
                        pt = print_ts_by_hash[coin]
                        if h not in pt:
                            pt[h] = bt_ns
                            print_pxsz_by_hash[coin][h] = [px * sz, sz]
                        else:
                            acc = print_pxsz_by_hash[coin][h]
                            acc[0] += px * sz
                            acc[1] += sz
                        # collapse taker legs by (hash, taker) -> one trade
                        if f.get("crossed") is True:
                            addr = ev[0]
                            key = (h, addr)
                            tc = taker_collapsed[coin]
                            if key not in tc:
                                tc[key] = [px * sz, sz, bt_ns,
                                           1 if f.get("side") == "B" else -1, addr]
                            else:
                                rec = tc[key]
                                rec[0] += px * sz
                                rec[1] += sz
                                # keep earliest block ts (legs share it anyway)
                                if bt_ns < rec[2]:
                                    rec[2] = bt_ns
                            if len(samples) < 6:
                                samples.append({
                                    "day": day, "coin": coin,
                                    "block_time": bt, "block_time_ns": bt_ns,
                                    "taker_address": addr, "px_leg": px,
                                    "sz_leg": sz, "side": f.get("side"),
                                    "crossed": f.get("crossed"), "hash": h,
                                })
                    n_blocks += 1
                ok = True
                hours_ok.append(hour)
                cum = {c: len(taker_collapsed[c]) for c in COINS}
                print(f"[ks2] {day} hour {hour:>2}: {n_blocks:,} blocks | "
                      f"BTC fills={n_fill['BTC']:,} ETH fills={n_fill['ETH']:,} | "
                      f"cum collapsed BTC={cum['BTC']:,} ETH={cum['ETH']:,}")
                break
            except Exception as exc:
                print(f"[ks2] {day} hour {hour:>2} attempt {attempt + 1} failed: {exc}")
                time.sleep(2 * (attempt + 1))
        if not ok:
            print(f"[ks2] {day} hour {hour:>2}: SKIPPED after {MAX_RETRIES + 1} attempts")

    per_coin = {}
    for c in COINS:
        # reference print path
        hashes = list(print_ts_by_hash[c].keys())
        if hashes:
            p_ts = np.fromiter((print_ts_by_hash[c][h] for h in hashes),
                               dtype=np.int64, count=len(hashes))
            p_px = np.fromiter((print_pxsz_by_hash[c][h][0] / print_pxsz_by_hash[c][h][1]
                                for h in hashes),
                               dtype=np.float64, count=len(hashes))
            order = np.argsort(p_ts, kind="stable")
            print_ts = p_ts[order]
            print_px = p_px[order]
        else:
            print_ts = np.empty(0, dtype=np.int64)
            print_px = np.empty(0, dtype=np.float64)

        # collapsed taker trades
        recs = list(taker_collapsed[c].values())
        n = len(recs)
        t_ts = np.empty(n, dtype=np.int64)
        t_px = np.empty(n, dtype=np.float64)
        t_dir = np.empty(n, dtype=np.int8)
        t_sz = np.empty(n, dtype=np.float64)
        t_addr = np.empty(n, dtype=object)
        for i, rec in enumerate(recs):
            pxsz, szsum, ts, d, addr = rec
            t_px[i] = pxsz / szsum
            t_sz[i] = szsum
            t_ts[i] = ts
            t_dir[i] = d
            t_addr[i] = addr

        per_coin[c] = {
            "taker_ts": t_ts, "taker_px": t_px, "taker_dir": t_dir,
            "taker_sz": t_sz, "taker_addr": t_addr,
            "print_ts": print_ts, "print_px": print_px,
        }
    return per_coin, hours_ok, samples


# -------------------- markout --------------------
def price_at(print_ts, print_px, query_ns):
    """Last trade print at-or-before query_ns (as-of join; -1 -> NaN)."""
    idx = np.searchsorted(print_ts, query_ns, side="right") - 1
    out = np.full(query_ns.shape, np.nan, dtype=np.float64)
    valid = idx >= 0
    out[valid] = print_px[idx[valid]]
    return out


def compute_markouts(taker_ts, taker_px, taker_dir, print_ts, print_px):
    """markout_h (bps) per collapsed taker trade at each horizon.

    markout = dir * (ref(t+h) - vwap_entry) / vwap_entry * 1e4. Trades whose
    t+h exceeds the last available print are dropped (NaN). Positive => taker
    profited over h => resting maker bore adverse selection.
    """
    if print_ts.size == 0:
        return {h: np.full(taker_ts.shape, np.nan) for h in HORIZONS_S}
    last_print_ns = print_ts[-1]
    markouts = {}
    for h in HORIZONS_S:
        tq = taker_ts + h * NS_PER_S
        ref = price_at(print_ts, print_px, tq)
        ref[tq > last_print_ns] = np.nan
        mo = taker_dir.astype(np.float64) * (ref - taker_px) / taker_px * 1e4
        markouts[h] = mo
    return markouts


# -------------------- idiosyncratic heterogeneity read --------------------
def idiosyncratic_read(taker_addr, mo_score, rng):
    """V_real / V_perm for the SCORED markout over takers with >= K collapsed trades.

    The caller passes the markout at the window settings.py declares, so this
    function names no window of its own.

    V_real = variance across per-taker mean scored markout (eligible takers). The
    null shuffles taker labels across trades and recomputes that variance N_PERM
    times; V_perm is the mean. ratio >> 1 => real per-counterparty heterogeneity.

    The relabelling is stats.shuffled with no strata, which is the null "wallet
    identity carries no signal at all" and is the same draw this loop always made.
    THE BUDGET HERE IS N_PERM AND NOT N_PERM_CORR, on purpose: these draws are the
    denominator of a ratio that no threshold is applied to, so what 1000 buys is the
    precision of V_perm, not the resolution of a p-value. The correlation null next
    door reports a p and is sized for the correction instead.
    """
    valid = ~np.isnan(mo_score)
    addr = taker_addr[valid]
    vals = mo_score[valid]
    if addr.size == 0:
        return 0, float("nan"), float("nan"), float("nan")

    uniq, inv = np.unique(addr, return_inverse=True)
    counts = np.bincount(inv)
    eligible = np.where(counts >= FILL_THRESHOLD_K)[0]
    n_takers_geK = int(eligible.size)

    def grouped_var(labels):
        sums = np.bincount(labels, weights=vals, minlength=uniq.size)
        cnts = np.bincount(labels, minlength=uniq.size)
        means = sums[eligible] / cnts[eligible]
        return float(np.var(means))

    if n_takers_geK < 2:
        return n_takers_geK, float("nan"), float("nan"), float("nan")

    v_real = grouped_var(inv)
    perms = np.empty(N_PERM, dtype=np.float64)
    for i in range(N_PERM):
        perms[i] = grouped_var(stats.shuffled(inv, rng))
    v_perm = float(np.mean(perms))
    ratio = v_real / v_perm if v_perm > 0 else float("nan")
    return n_takers_geK, v_real, v_perm, ratio


# -------------------- persistence (Spearman) --------------------
def _rankdata(a):
    """Average-rank of a 1-D array (ties get the mean rank). Pure numpy."""
    a = np.asarray(a, dtype=np.float64)
    order = np.argsort(a, kind="stable")
    ranks = np.empty(a.size, dtype=np.float64)
    sa = a[order]
    i = 0
    n = a.size
    while i < n:
        j = i + 1
        while j < n and sa[j] == sa[i]:
            j += 1
        avg = (i + j - 1) / 2.0 + 1.0  # 1-based average rank over the tie block
        ranks[order[i:j]] = avg
        i = j
    return ranks


def spearman(x, y):
    """Spearman rho between x and y (equal length). Returns (rho, n)."""
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    n = x.size
    if n < 3:
        return float("nan"), n
    rx = _rankdata(x)
    ry = _rankdata(y)
    rx -= rx.mean()
    ry -= ry.mean()
    denom = np.sqrt((rx * rx).sum() * (ry * ry).sum())
    if denom == 0:
        return float("nan"), n
    return float((rx * ry).sum() / denom), n


def spearman_perm_pvalue(x, y, rng, cell, n_perm=N_PERM_CORR):
    """Two-sided permutation p-value for Spearman rho (shuffle y labels).

    Returns (p, block). The draws are built here because the null is this test's own
    -- one relabelling of the second ranking -- and the COUNTING is stats.permutation_p,
    which owns the floor, the side and the record of how many draws were usable. The
    p that comes back is the number this loop always produced: every draw is finite by
    construction, because the permuted denominator is the same sum of squares as the
    observed one, so the module's usable-draw denominator equals the requested budget
    here. The comparison slack is passed as the absolute 1e-12 this test has always
    used rather than left to the module's relative default, which at a correlation
    bounded by one would be a slightly smaller number and is not this file's to change.

    THE BUDGET IS N_PERM_CORR, the inferential one. The variance-ratio null in
    idiosyncratic_read draws N_PERM instead, and the two are not interchangeable: this
    one sets the smallest p the run can express, that one sets the precision of a
    denominator.
    """
    rho0, n = spearman(x, y)
    if n < 3 or rho0 != rho0:
        return float("nan"), None
    rx = _rankdata(x)
    rx -= rx.mean()
    ry = _rankdata(y)
    ry -= ry.mean()
    denom_x = np.sqrt((rx * rx).sum())
    draws = np.empty(int(n_perm), dtype=np.float64)
    for i in range(int(n_perm)):
        ryp = stats.shuffled(ry, rng)
        d = denom_x * np.sqrt((ryp * ryp).sum())
        draws[i] = (rx * ryp).sum() / d if d > 0 else 0.0
    block = stats.permutation_p(rho0, draws, side="two_sided", abs_tol=1e-12,
                                n_requested=int(n_perm), cell=cell)
    return block["p"], block


def per_taker_day_mean(coin_day_store, coin, day):
    """Return dict addr -> mean scored markout for takers with >= K trades that day."""
    store = coin_day_store[(coin, day)]
    addr = store["addr"]
    mo_score = store["mo_score"]
    valid = ~np.isnan(mo_score)
    addr = addr[valid]
    mo_score = mo_score[valid]
    if addr.size == 0:
        return {}
    uniq, inv = np.unique(addr, return_inverse=True)
    sums = np.bincount(inv, weights=mo_score, minlength=uniq.size)
    cnts = np.bincount(inv, minlength=uniq.size)
    out = {}
    for k in range(uniq.size):
        if cnts[k] >= FILL_THRESHOLD_K:
            out[uniq[k]] = sums[k] / cnts[k]
    return out


def persistence_pair(coin_day_store, coin, day_a, day_b, rng, label):
    """Spearman of per-taker mean scored markout between two day-sets.

    day_a / day_b are each a LIST of days (pooled). A taker must have >= K
    trades in the pooled set on EACH side to enter.
    """
    means_a = pooled_taker_means(coin_day_store, coin, day_a)
    means_b = pooled_taker_means(coin_day_store, coin, day_b)
    common = sorted(set(means_a) & set(means_b))
    if len(common) < 3:
        return {
            "coin": coin, "pair": label, "n_counterparties": len(common),
            "spearman": float("nan"), "pvalue": None,
        }
    xa = np.array([means_a[a] for a in common], dtype=np.float64)
    xb = np.array([means_b[a] for a in common], dtype=np.float64)
    rho, n = spearman(xa, xb)
    pval, perm = spearman_perm_pvalue(
        xa, xb, rng, cell=("day_pair_rank_persistence", coin, label),
        n_perm=N_PERM_CORR)
    return {
        "coin": coin, "pair": label, "n_counterparties": int(n),
        "spearman": rho, "pvalue": pval,
        # The procedure beside the number: the side, both draw counts, the slack and
        # the floor. A p with no draw count next to it cannot be read at all.
        "permutation": perm,
    }


def pooled_taker_means(coin_day_store, coin, days):
    """addr -> mean scored markout pooled over `days`, takers with >= K pooled trades."""
    addr_parts = []
    mo_parts = []
    for d in days:
        store = coin_day_store.get((coin, d))
        if store is None:
            continue
        valid = ~np.isnan(store["mo_score"])
        addr_parts.append(store["addr"][valid])
        mo_parts.append(store["mo_score"][valid])
    if not addr_parts:
        return {}
    addr = np.concatenate(addr_parts)
    mo_score = np.concatenate(mo_parts)
    if addr.size == 0:
        return {}
    uniq, inv = np.unique(addr, return_inverse=True)
    sums = np.bincount(inv, weights=mo_score, minlength=uniq.size)
    cnts = np.bincount(inv, minlength=uniq.size)
    out = {}
    for k in range(uniq.size):
        if cnts[k] >= FILL_THRESHOLD_K:
            out[uniq[k]] = sums[k] / cnts[k]
    return out


# -------------------- main --------------------
def main():
    t_start = artifact.start_clock()
    print(f"[ks2] multi-day trade-weighted | days={DAYS} coins={COINS} "
          f"horizons={HORIZONS_S}s K={FILL_THRESHOLD_K} perms={N_PERM}")

    # resolve days (substitute a fallback if a target day folder is missing)
    resolved_days = []
    day_notes = []
    fb_iter = iter(FALLBACK_DAYS)
    for d in DAYS:
        if s3_day_has_files(d):
            resolved_days.append(d)
        else:
            sub = None
            for cand in fb_iter:
                if cand not in resolved_days and s3_day_has_files(cand):
                    sub = cand
                    break
            if sub is None:
                day_notes.append(f"day {d} missing and no fallback available")
                continue
            day_notes.append(f"day {d} missing -> substituted {sub}")
            resolved_days.append(sub)
    print(f"[ks2] resolved days: {resolved_days}  notes={day_notes}")

    issues = list(day_notes)
    slices = []
    coin_day_store = {}    # (coin, day) -> {"addr","mo_score"} for persistence
    hours_by_day = {}
    samples_all = []

    for day in resolved_days:
        per_coin, hours_ok, samples = parse_day(day)
        hours_by_day[day] = hours_ok
        if len(samples_all) < 6:
            samples_all.extend(samples[: 6 - len(samples_all)])
        if len(hours_ok) < 24:
            issues.append(f"{day}: only {len(hours_ok)}/24 hours covered {hours_ok}")

        for coin in COINS:
            d = per_coin[coin]
            n_trades = int(d["taker_ts"].size)
            if n_trades == 0 or d["print_ts"].size == 0:
                issues.append(f"{coin} {day}: no collapsed trades / empty print path")
                coin_day_store[(coin, day)] = {
                    "addr": np.empty(0, dtype=object),
                    "mo_score": np.empty(0, dtype=np.float64),
                }
                slices.append({
                    "coin": coin, "day": day, "n_trades": 0,
                    "n_takers": 0, "n_takers_geK": 0,
                    **markout_stat_fields({}),
                    "var_real": float("nan"), "var_perm_mean": float("nan"),
                    "ratio_real_over_perm": float("nan"),
                })
                continue

            markouts = compute_markouts(
                d["taker_ts"], d["taker_px"], d["taker_dir"],
                d["print_ts"], d["print_px"])

            mo_stats = {}
            for h in HORIZONS_S:
                good = markouts[h][~np.isnan(markouts[h])]
                mo_stats[h] = (
                    float(np.mean(good)) if good.size else float("nan"),
                    float(np.median(good)) if good.size else float("nan"),
                    int(good.size),
                )

            rng = np.random.default_rng(int(day) + (0 if coin == "BTC" else 1))
            n_takers_geK, v_real, v_perm, ratio = idiosyncratic_read(
                d["taker_addr"], markouts[H.HEADLINE_HORIZON_S], rng)
            n_takers = int(np.unique(d["taker_addr"]).size)

            coin_day_store[(coin, day)] = {
                "addr": d["taker_addr"], "mo_score": markouts[H.HEADLINE_HORIZON_S],
            }

            slices.append({
                "coin": coin, "day": day, "n_trades": n_trades,
                "n_takers": n_takers, "n_takers_geK": n_takers_geK,
                **markout_stat_fields(mo_stats),
                "var_real": v_real, "var_perm_mean": v_perm,
                "ratio_real_over_perm": ratio,
            })
            head, comp = H.HEADLINE_HORIZON_S, H.COMPANION_HORIZON_S
            print(f"[ks2] SLICE {coin} {day}: n_trades={n_trades:,} "
                  f"takers={n_takers:,} >=K={n_takers_geK} "
                  f"{H.headline_print_col(head)} mean={mo_stats[head][0]:+.4f} "
                  f"med={mo_stats[head][1]:+.4f} "
                  f"{H.headline_print_col(comp)} mean={mo_stats[comp][0]:+.4f} "
                  f"med={mo_stats[comp][1]:+.4f} "
                  f"ratio={ratio:.2f}")

    # -------------------- persistence --------------------
    persistence = []
    rng_p = np.random.default_rng(SEED_CORR_NULL)
    for coin in COINS:
        present = [d for d in resolved_days if (coin, d) in coin_day_store]
        # adjacent-day pairs
        for a, b in zip(present, present[1:]):
            persistence.append(
                persistence_pair(coin_day_store, coin, [a], [b], rng_p,
                                 f"{a}->{b}"))
        # pooled early vs late (first two vs last)
        if len(present) >= 3:
            early = present[:2]
            late = [present[2]]
            persistence.append(
                persistence_pair(coin_day_store, coin, early, late, rng_p,
                                 f"pooled({'+'.join(early)})->{late[0]}"))

    for p in persistence:
        pv = "n/a" if p["pvalue"] is None else f"{p['pvalue']:.4f}"
        rho = p["spearman"]
        rho_s = "nan" if rho != rho else f"{rho:+.4f}"
        print(f"[ks2] PERSIST {p['coin']} {p['pair']}: "
              f"spearman={rho_s} n={p['n_counterparties']} p={pv}")

    # -------------------- persist results --------------------
    # What the numbers cover. The three keys artifact.write requires come first; the
    # rest is what this script has always recorded about its own run, kept here so
    # nothing a reader used to find in the scope block has moved out of it. The two
    # permutation budgets are both named, because one file carrying one key called
    # n_perm could only be right about one of them.
    n_trades_total = sum(int(s["n_trades"]) for s in slices)
    scope = {
        "population": (f"{n_trades_total:,} collapsed taker trades, one per (block "
                       f"hash, taker) at a size-weighted VWAP entry; the heterogeneity "
                       f"ratio and the day-pair correlations both gate takers at "
                       f"{FILL_THRESHOLD_K} fills in each leg"),
        "window": (f"{len(resolved_days)} days resolved of {len(DAYS)} requested: "
                   f"{resolved_days}"),
        "coins": list(COINS),
        "days_requested": DAYS, "days_resolved": resolved_days,
        "horizons_s": list(HORIZONS_S),
        "fill_threshold_K": FILL_THRESHOLD_K,
        "n_perm_varratio": N_PERM,
        "n_perm_corr": N_PERM_CORR,
        "p_floor_corr": stats.p_floor(N_PERM_CORR),
        "clock_source": "native block_time (ns ISO-8601), node_fills_by_block",
        "dedup": "collapsed to one obs per (hash, taker) with size-weighted VWAP entry",
    }
    results = {
        "hours_by_day": hours_by_day,
        "slices": slices,
        "persistence": persistence,
        "sample_collapsed_trades": sample_collapsed(coin_day_store, resolved_days),
        "sample_raw_legs": samples_all,
        "issues": issues,
    }
    # artifact.write records the producer with the hash of its own bytes, the inputs,
    # the scope, the settings block and the runtime in one shape. The inputs are named as
    # the S3 prefixes actually read, because by DEFAULT each hour is deleted the moment it
    # is parsed and there is no local file left to hash by the time this line runs. That
    # default is the declared setting CAP_KEEP_RAW, not a property of this code: set it
    # and the hours stay where CAP_RAW_CACHE puts them, which is what makes the raw input
    # of this node hashable and therefore provable rather than assumed.
    out_path = artifact.write(
        os.path.basename(RESULTS_PATH), results, script=__file__,
        inputs=[f"s3://{S3_BUCKET}/node_fills_by_block/hourly/{d}/"
                for d in resolved_days],
        scope=scope, started=t_start, settings=settings_used(),
        out_dir=os.path.dirname(RESULTS_PATH))
    runtime_s = artifact.read_meta(out_path)["run"]["runtime_s"]

    # -------------------- summary --------------------
    print("\n" + "=" * 72)
    print("KILL-SWITCH 2 (multi-day, two-asset, TRADE-WEIGHTED) - SUMMARY")
    print("=" * 72)
    print(f"  days   : requested {DAYS} -> resolved {resolved_days}")
    print(f"  coins  : {COINS}   K={FILL_THRESHOLD_K}   perms={N_PERM}")
    print(f"  dedup  : ONE obs per (hash, taker), size-weighted VWAP entry")
    print("-" * 72)
    head_col = H.headline_print_col()
    mean_key = H.field_name("markout_mean_bps")
    med_key = H.field_name("markout_median_bps")
    print(f"  {'coin':<4} {'day':<9} {'n_trades':>9} {'takers':>7} {'>=K':>5} "
          f"{head_col + ' mean':>10} {head_col + ' med':>9} {'ratio':>7}")
    for s in slices:
        print(f"  {s['coin']:<4} {s['day']:<9} {s['n_trades']:>9,} "
              f"{s['n_takers']:>7,} {s['n_takers_geK']:>5} "
              f"{s[mean_key]:>+10.4f} "
              f"{s[med_key]:>+9.4f} "
              f"{s['ratio_real_over_perm']:>7.2f}")
    print("-" * 72)
    print(f"  PERSISTENCE (Spearman of per-taker mean {head_col} markout across days)")
    for p in persistence:
        pv = "n/a" if p["pvalue"] is None else f"{p['pvalue']:.4f}"
        rho = p["spearman"]
        rho_s = "nan" if rho != rho else f"{rho:+.4f}"
        print(f"    {p['coin']:<4} {p['pair']:<26} rho={rho_s} "
              f"n={p['n_counterparties']:>4} p={pv}")
    print("-" * 72)
    if issues:
        print("  ISSUES:")
        for it in issues:
            print(f"    - {it}")
    else:
        print("  ISSUES: none")
    print("=" * 72)
    print(f"  results -> {os.path.basename(RESULTS_PATH)}")
    print(f"  runtime  -> {runtime_s}s")


def sample_collapsed(coin_day_store, resolved_days):
    """A few collapsed-trade rows for the results file: taker plus its scored markout.

    The markout stored per trade is the one the study scores on, so the row's key is
    built for the declared scoring window rather than typed.
    """
    out = []
    key = H.field_name("markout_bps")
    for coin in COINS:
        for day in resolved_days:
            store = coin_day_store.get((coin, day))
            if store is None or store["addr"].size == 0:
                continue
            for i in range(min(2, store["addr"].size)):
                out.append({
                    "coin": coin, "day": day,
                    "taker_address": store["addr"][i],
                    key: (None if np.isnan(store["mo_score"][i])
                          else float(store["mo_score"][i])),
                })
            if len(out) >= 8:
                return out
    return out


if __name__ == "__main__":
    main()
