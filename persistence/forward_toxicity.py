"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-23
References:
  Avellaneda, M. and S. Stoikov (2008). High-Frequency Trading in a Limit Order Book.
  Easley, D., M. Lopez de Prado and M. O'Hara (2012). Flow Toxicity and Liquidity.
  Albers, J., M. Cucuringu, S. Howison and A. Shestopaloff (2026). An Open Book
    (Hyperliquid L4), Zenodo 10.5281/zenodo.18184441.

forward_toxicity.py

Out-of-design forward-window confirmation of counterparty toxicity.

The toxicity decomposition was designed and estimated on a December 2025 window.
This script re-tests it on a strictly later, out-of-design window of Hyperliquid
trade prints collected from the public trades feed (BTC, ETH, SOL), which did not
exist when the method was fixed. It answers two questions a referee raises against
any in-sample finding:

  (1) WITHIN-WINDOW persistence: in the forward window itself, is per-counterparty
      toxicity (signed forward print markout) stable from an early half to a late
      half? (the persistence claim, re-run on fresh data)

  (2) CROSS-WINDOW carry: do the wallets flagged toxic back in December stay more
      toxic in the forward window than the rest? This is the cleanest "you overfit
      December" rebuttal, because the toxic set is frozen from the old window and
      tested on data recorded months later.

The forward feed carries trade prints only (no book, no pre-trade inventory), so
the markout here is a print-to-print forward return, coarser than the book-mid
markout used in the main study. It is a confirmation exhibit, not a re-estimation.

Sign convention (matches the main study): side "B" = buy-aggressor (taker lifts the
ask, taker_dir = +1), side "A" = sell-aggressor (taker_dir = -1). The taker is the
aggressor; markout = taker_dir * (price_future - price_now) / price_now, in bps,
positive when the taker profited (the resting maker was adversely selected). A
built-in sanity check requires buy-aggressor forward returns to be positive and
sell-aggressor negative before any wallet-level result is reported.

Data: forward trade prints live in CAP_FORWARD_DIR (default ./forward_data), one
gzipped ndjson file per day. December per-wallet toxicity and the wallet hex map
come from the on-disk quickwin_markouts.npz and quickwin_taker_map.json.

Run:
  CAP_FORWARD_DIR=/path/to/forward python3 forward_toxicity.py
  (uv run --no-project --with-requirements ../requirements.txt python3 forward_toxicity.py)

DECLARED DEBT, opened 2026-08-04: THIS NODE CANNOT RUN ON THIS MACHINE, AND THE REASON
IS THE INPUT RATHER THAN THE CODE. A recompute was launched at 03:26 UTC and stopped
after 0.3 s with FileNotFoundError on the forward directory. Measured, not supposed:
there are ZERO files matching *.ndjson.gz anywhere in this repository or under the home
directory, and no directory named forward* exists in either. The forward feed is a LIVE
recording made by a separate recorder over four days, 2026-06-20 to 2026-06-23, and its
size is on file in the artifact this node last wrote: 894 015 prints on BTC, 348 853 on
ETH, 289 168 on SOL.

WHAT THAT MAKES THE ARTIFACT. forward_toxicity_results.json is in the older results
shape, with no _meta block, so it names no producer and records no hash, and both
freshness gates report it as an artifact whose origin cannot be asked. That will stay
true until the node runs, and the node cannot run until the recording is back on disk.
The standing decision of 2026-07-31 -- everything a recompute needs is kept locally,
because reproducibility with a missing input is not checked at all -- names this as the
exact debt it was written about.

WHAT WOULD CLOSE IT, and the second way is NOT equivalent to the first. Either the four
days of recording are brought back from the machine that made them, and this node is run
unchanged; or the same four days are cut out of the S3 archive the rest of the study
reads. The second is a DIFFERENT QUANTITY and may not be substituted silently: the point
of this exhibit is that the window was recorded forward, live, out of sample and from a
different source than the archive, and a version rebuilt from the archive shares neither
the source nor the out-of-sample property. If it is ever done that way, it needs its own
name and its own entry, not this one.

WHAT NOTHING HERE BLOCKS, measured 2026-08-04. The body of the report stands on
thirteen artifacts and this is not one of them. No published figure is taken from this
file, so the debt costs provenance coverage and no published figure.
"""

import gzip
import json
import os
import sys

import numpy as np

# One place writes a results file, so this artifact records its producer, its inputs
# with their hashes, its scope and its settings the same way every other one does.
# See artifact.py.
# artifact.py, settings.py and the other shared modules sit in the
# repository root, one directory up from this group, so the path is built
# from this file's own location and never from the working directory the
# run happens to start in.
_CODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CODE_DIR not in sys.path:
    sys.path.insert(0, _CODE_DIR)

import artifact
import panel_io as P
import settings as H

HERE = os.path.dirname(os.path.abspath(__file__))
# The recorded tape and the two decision-window arrays sit under the declared data root,
# which stayed at the top of the repository when the producers were grouped. The results
# file stays beside its producer.
FORWARD_DIR = os.environ.get("CAP_FORWARD_DIR",
                             os.path.join(P.data_root(), "forward_data"))
NPZ_DEC = os.path.join(P.data_root(), "quickwin_markouts.npz")
TAKER_MAP = os.path.join(P.data_root(), "quickwin_taker_map.json")
OUT_JSON = os.path.join(HERE, "forward_toxicity_results.json")

HORIZONS_MS = {"mo1": 1000, "mo10": 10000, "mo60": 60000}
COINS = ("BTC", "ETH", "SOL")
MIN_FILLS_FWD = 10        # wallet needs this many forward fills to be ranked
MIN_FILLS_HALF = 5        # per-half minimum for within-window persistence
DEC_TOXIC_Q = 0.90        # December top-decile = frozen toxic set
DEC_MIN_FILLS = 10
EARLY_DAYS = ("2026-06-20", "2026-06-21")
LATE_DAYS = ("2026-06-22", "2026-06-23")
NPERM = 1000
# The stream this window's placebo draws. READ from settings.py and never typed:
# seed_for("forward_toxicity") returns 20260623, the value the published forward run was
# drawn under, so reading it moves nothing here. It is NOT settings.MASTER_SEED, which is
# 20260620, and the difference is stamped as a stated override in this file's fingerprint.
RNG_SEED = H.seed_for("forward_toxicity")


# ---------------------------------------------------------------------------
# Forward feed
# ---------------------------------------------------------------------------
def parse_forward():
    """Read all daily ndjson.gz files. Return per-coin dict of arrays sorted by
    time, plus a per-trade record table (taker hex, side, day, time, px).

    Returns (per_coin, files_read). The file list is returned rather than rebuilt by
    the caller so that the artifact's inputs record is the same set of files the parse
    actually opened, decided by one predicate instead of two that can drift apart.
    """
    files = sorted(f for f in os.listdir(FORWARD_DIR) if f.endswith(".ndjson.gz"))
    if not files:
        raise SystemExit("no .ndjson.gz in %s" % FORWARD_DIR)
    rows = {c: {"time": [], "px": [], "side": [], "taker": [], "day": []} for c in COINS}
    per_file = []
    for fn in files:
        day = fn[:10]
        # A still-open daily file (the live recorder) can be a truncated gzip
        # stream; read what is there and stop cleanly at the broken tail.
        read_here, ended_cleanly, how_it_broke = 0, True, None
        try:
            with gzip.open(os.path.join(FORWARD_DIR, fn), "rt") as fh:
                for line in fh:
                    try:
                        r = json.loads(line)
                    except ValueError:
                        continue
                    c = r.get("coin")
                    if c not in rows:
                        continue
                    side = r.get("side")
                    users = r.get("users") or []
                    if side not in ("A", "B") or len(users) != 2:
                        continue
                    # taker = aggressor: buyer (users[0]) if side B, seller (users[1]) if side A
                    taker = users[0] if side == "B" else users[1]
                    try:
                        px = float(r["px"]); t = int(r["time"])
                    except (KeyError, ValueError, TypeError):
                        continue
                    d = rows[c]
                    d["time"].append(t); d["px"].append(px); d["side"].append(1 if side == "B" else 0)
                    d["taker"].append(taker); d["day"].append(day)
                    read_here += 1
        except (EOFError, OSError, gzip.BadGzipFile) as exc:
            ended_cleanly, how_it_broke = False, f"{type(exc).__name__}: {exc}"
        per_file.append({"file": fn, "day": day, "rows_read": read_here,
                         "ended_cleanly": ended_cleanly,
                         "how_it_broke": how_it_broke})

    _refuse_on_a_short_read(per_file)
    out = {}
    for c in COINS:
        d = rows[c]
        if not d["time"]:
            continue
        t = np.array(d["time"], dtype=np.int64)
        order = np.argsort(t, kind="mergesort")
        out[c] = {
            "time": t[order],
            "px": np.array(d["px"], dtype=np.float64)[order],
            "side": np.array(d["side"], dtype=np.int8)[order],
            "taker": np.array(d["taker"], dtype=object)[order],
            "day": np.array(d["day"], dtype=object)[order],
        }
    return out, [os.path.join(FORWARD_DIR, fn) for fn in files], per_file


# ---------------------------------------------------------------------------
# A SHORT READ IS A FINDING, NOT A TAIL TO BE SWALLOWED
#
# Established 2026-08-04 by measurement, and it cost this probe its published
# conclusion. Until today the loop above ended with `except (...): pass` and the comment
# "truncated tail of a still-open daily file; keep what was read". That tolerance is
# right for the ONE file the live recorder is still appending to, and it is wrong for
# every other case, because a gzip stream also breaks when the copy is incomplete -- and
# an incomplete copy is exactly what this probe ran on.
#
# THE MECHANISM, MEASURED RATHER THAN SUPPOSED. The committed artifact recorded 894 015
# BTC prints, 348 853 ETH and 289 168 SOL, total 1 532 036. Reading the four recovered
# days in order and stopping at that total returns those three counts EXACTLY, to the
# unit, at the 74 631st trade of 2026-06-23: three complete days plus a tenth of the
# fourth. The whole window is 2 159 569 prints, so the published figures stood on 71 per
# cent of the window, and nothing said so -- not the artifact, which carried no _meta
# block at all, and not the run, which printed no warning.
#
# WHAT IT COST. The old numbers said the December-toxic set carried a forward gap of
# 0.1561 bps at p = 0.2348 on 111 wallets: a null result, and it was published as one.
# The complete window says 1.1307 bps at p = 0.0010 on 188 wallets. The probe does not
# merely move, it changes sign of conclusion, and it did so because of a transfer that
# was never finished rather than because of anything about the market.
#
# THE RULE THIS ENFORCES. A short read stops the run and prints the expectation, the
# fact and the place, because a check that cannot print those three is not a check. The
# tolerance still exists, because the live recorder's open file is a real case, but it
# is now an announced key with its size written into the artifact rather than a silent
# branch. It may only ever be turned on deliberately.
# ---------------------------------------------------------------------------

ALLOW_OPEN_TAIL = os.environ.get("CAP_ALLOW_OPEN_TAIL", "").strip() in (
    "1", "true", "yes", "on")


def _refuse_on_a_short_read(per_file):
    """Stop unless every daily file was read to a clean end."""
    broken = [r for r in per_file if not r["ended_cleanly"]]
    if not broken:
        return
    lines = ["", "=" * 78,
             "  A DAILY FILE ENDED IN A BROKEN GZIP STREAM", "=" * 78,
             "  expectation : every .ndjson.gz in the forward directory decompresses to "
             "its end,",
             "                because a closed day is a finished file and a broken one "
             "is an incomplete copy",
             "  fact        :"]
    for r in broken:
        lines.append(f"                {r['file']}: {r['rows_read']} rows read, then "
                     f"{r['how_it_broke']}")
    lines += [f"  place       : {os.path.basename(FORWARD_DIR.rstrip('/'))}/, read by "
              f"parse_forward in {os.path.basename(__file__)}",
              "  what to do  : re-fetch the day from the recorder that wrote it. The "
              "host, the path and the",
              "                exact command are in the data-acquisition log kept "
              "alongside this repository.",
              "                If this really is the live recorder's still-open file "
              "for today, say so",
              "                deliberately with CAP_ALLOW_OPEN_TAIL=1; the count of "
              "rows kept is then",
              "                written into the artifact so nobody has to guess how "
              "much of the day it saw.",
              "=" * 78]
    text = "\n".join(lines)
    if ALLOW_OPEN_TAIL:
        print(text)
        print("  CAP_ALLOW_OPEN_TAIL=1: proceeding on a short read BY DECLARATION")
        return
    raise SystemExit(text)


def forward_markouts(coindata):
    """Per-trade signed forward print markout (bps) at each horizon, no-lookahead.
    markout = taker_dir * (px[t+H] - px[t]) / px[t] * 1e4, where px[t+H] is the
    first print at or after t+H. Trades with no later print at the horizon are NaN."""
    t = coindata["time"]; px = coindata["px"]; side = coindata["side"]
    n = t.size
    taker_dir = np.where(side == 1, 1.0, -1.0)
    mo = {}
    for h, ms in HORIZONS_MS.items():
        idx = np.searchsorted(t, t + ms, side="left")
        valid = idx < n
        fut = np.full(n, np.nan)
        fut[valid] = px[idx[valid]]
        ret = (fut - px) / px * 1e4
        mo[h] = taker_dir * ret
    return mo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def per_wallet_mean(takers, vals, min_fills):
    """Mean of vals per wallet hex over non-NaN entries; keep wallets with
    >= min_fills valid entries. Returns dict hex -> (mean, count)."""
    good = ~np.isnan(vals)
    takers = takers[good]; vals = vals[good]
    acc = {}
    for w, v in zip(takers, vals):
        a = acc.get(w)
        if a is None:
            acc[w] = [v, 1]
        else:
            a[0] += v; a[1] += 1
    return {w: (s / c, c) for w, (s, c) in acc.items() if c >= min_fills}


def spearman(x, y):
    if x.size < 3:
        return float("nan")
    rx = np.argsort(np.argsort(x)); ry = np.argsort(np.argsort(y))
    rx = rx - rx.mean(); ry = ry - ry.mean()
    d = np.sqrt((rx * rx).sum() * (ry * ry).sum())
    return float((rx * ry).sum() / d) if d > 0 else float("nan")


def demean_by_coin(per_coin_mo):
    """Concatenate per-coin markouts after subtracting each coin's mean, so a
    pooled toxic-vs-rest gap is within-coin. Returns dict horizon -> (takers, demeaned, day)."""
    out = {}
    for h in HORIZONS_MS:
        tk, val, dy = [], [], []
        for c, d in per_coin_mo.items():
            v = d["mo"][h]
            good = ~np.isnan(v)
            if good.sum() == 0:
                continue
            vv = v[good].copy()
            vv = vv - vv.mean()
            tk.append(d["taker"][good]); val.append(vv); dy.append(d["day"][good])
        out[h] = (np.concatenate(tk), np.concatenate(val), np.concatenate(dy))
    return out


# ---------------------------------------------------------------------------
# December frozen toxic set
# ---------------------------------------------------------------------------
def december_toxic_hexes():
    """Top-decile December wallets by per-coin mean headline markout, mapped to hex addresses."""
    d = np.load(NPZ_DEC, allow_pickle=True)
    code2hex = {}
    with open(TAKER_MAP) as fh:
        m = json.load(fh)
    # file is {"_direction": "...", "map": {hex: code}}; tolerate a flat dict too
    hexmap = m.get("map", m) if isinstance(m, dict) else m
    for hexa, code in hexmap.items():
        if isinstance(code, int):
            code2hex[code] = hexa
    tid = d["taker_id"].astype(np.int64)
    coin = d["coin"].astype(np.int64)
    mo_score = d[H.headline_print_col()].astype(np.float64)
    toxic = set()
    for cc in np.unique(coin):
        sel = (coin == cc) & ~np.isnan(mo_score)
        t = tid[sel]; v = mo_score[sel]
        order = np.argsort(t, kind="mergesort")
        t = t[order]; v = v[order]
        uniq, start = np.unique(t, return_index=True)
        sums = np.add.reduceat(v, start)
        counts = np.diff(np.append(start, t.size))
        means = sums / counts
        keep = counts >= DEC_MIN_FILLS
        if keep.sum() < 10:
            continue
        thr = np.quantile(means[keep], DEC_TOXIC_Q)
        for code, mn, cnt in zip(uniq[keep], means[keep], counts[keep]):
            if mn >= thr:
                h = code2hex.get(int(code))
                if h is not None:
                    toxic.add(h)
    all_dec = set()
    for code in np.unique(tid):
        h = code2hex.get(int(code))
        if h is not None:
            all_dec.add(h)
    return toxic, all_dec


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
def main():
    t0 = artifact.start_clock()
    # NOT stats.rng. The generator, the denominator and the comparison tolerance in the
    # placebo below all differ from what stats.py does, and the differences move the
    # p-value, so the block is left as it is and the difference is recorded rather than
    # translated. See the note above the placebo loop.
    rng = np.random.default_rng(RNG_SEED)
    fwd, forward_files, per_file = parse_forward()
    results = {"config": {"forward_dir": os.path.basename(FORWARD_DIR.rstrip("/")),
                          # THE POPULATION, PER FILE, AND IT IS NOT A DIAGNOSTIC. Had
                          # this table been written when the probe first ran, the short
                          # read that cost it its conclusion would have been one line in
                          # its own output rather than a discovery six weeks later.
                          "days_read": per_file,
                          "prints_read_total": sum(r["rows_read"] for r in per_file),
                          "every_day_ended_cleanly": all(r["ended_cleanly"]
                                                         for r in per_file),
                          "open_tail_allowed_by_declaration": ALLOW_OPEN_TAIL,
                          "coins": list(fwd.keys()), "horizons_ms": HORIZONS_MS,
                          "min_fills_fwd": MIN_FILLS_FWD, "dec_toxic_q": DEC_TOXIC_Q,
                          "early_days": EARLY_DAYS, "late_days": LATE_DAYS,
                          "nperm": NPERM, "rng_seed": RNG_SEED},
               "n_trades": {}, "sanity": {}, "within_persistence": {},
               "cross_window": {}}

    per_coin_mo = {}
    for c, d in fwd.items():
        mo = forward_markouts(d)
        per_coin_mo[c] = {"mo": mo, "taker": d["taker"], "side": d["side"], "day": d["day"]}
        results["n_trades"][c] = int(d["time"].size)

    # --- SANITY: buy-aggressor forward return positive, sell negative ---
    for c, d in per_coin_mo.items():
        side = d["side"]; sane = {}
        for h in HORIZONS_MS:
            mo = d["mo"][h]
            # undo taker_dir to get raw forward return by side
            raw = mo * np.where(side == 1, 1.0, -1.0)
            b = raw[(side == 1) & ~np.isnan(raw)]
            a = raw[(side == 0) & ~np.isnan(raw)]
            sane[h] = {"buy_fwd_ret_bps": float(b.mean()) if b.size else float("nan"),
                       "sell_fwd_ret_bps": float(a.mean()) if a.size else float("nan")}
        results["sanity"][c] = sane
    # hard check on the BTC headline rung (best-powered): buy>0>sell expected
    _hcol = H.headline_print_col()
    btc = results["sanity"].get("BTC", {}).get(_hcol, {})
    sane_ok = (btc.get("buy_fwd_ret_bps", -1) > 0 > btc.get("sell_fwd_ret_bps", 1))
    results["sanity"][f"BTC_{_hcol}_sign_ok"] = bool(sane_ok)

    dem = demean_by_coin(per_coin_mo)

    # --- WITHIN-WINDOW persistence (early half vs late half) ---
    early = set(EARLY_DAYS); late = set(LATE_DAYS)
    for h in HORIZONS_MS:
        tk, val, dy = dem[h]
        e_mask = np.array([x in early for x in dy]); l_mask = np.array([x in late for x in dy])
        em = per_wallet_mean(tk[e_mask], val[e_mask], MIN_FILLS_HALF)
        lm = per_wallet_mean(tk[l_mask], val[l_mask], MIN_FILLS_HALF)
        common = sorted(set(em) & set(lm))
        if len(common) >= 5:
            xe = np.array([em[w][0] for w in common]); xl = np.array([lm[w][0] for w in common])
            rho = spearman(xe, xl)
        else:
            rho = float("nan")
        results["within_persistence"][h] = {"n_wallets_common": len(common),
                                            "spearman_early_late": rho}

    # --- CROSS-WINDOW: December-toxic vs rest, in the forward window ---
    dec_toxic, dec_all = december_toxic_hexes()
    results["cross_window"]["n_dec_toxic_wallets"] = len(dec_toxic)
    results["cross_window"]["n_dec_all_wallets"] = len(dec_all)
    for h in HORIZONS_MS:
        tk, val, dy = dem[h]
        wm = per_wallet_mean(tk, val, MIN_FILLS_FWD)   # per-wallet forward toxicity
        wallets = np.array(sorted(wm.keys()), dtype=object)
        if wallets.size < 20:
            results["cross_window"][h] = {"note": "too few forward wallets"}
            continue
        wvals = np.array([wm[w][0] for w in wallets])
        is_tox = np.array([w in dec_toxic for w in wallets])
        is_decseen = np.array([w in dec_all for w in wallets])
        # compare Dec-toxic vs Dec-seen-but-not-toxic (controls for "was active in Dec")
        rest_mask = is_decseen & ~is_tox
        gtox = wvals[is_tox]; grest = wvals[rest_mask]
        gap = (float(gtox.mean()) - float(grest.mean())) if (gtox.size and grest.size) else float("nan")
        # Label-shuffle placebo: permute the toxic label among Dec-seen wallets.
        #
        # NOT ROUTED THROUGH stats.permutation_p, and the reason is that three things
        # here disagree with what that function does, each of which moves this p:
        #   the STREAM is np.random.default_rng(20260623) drawn once and shared by all
        #   three horizons in loop order, where stats.rng derives a separate stream per
        #   named cell from settings.MASTER_SEED 20260620;
        #   the DENOMINATOR is the requested NPERM, where stats divides by the draws
        #   that came back finite;
        #   the COMPARISON is null >= gap with no slack, where stats counts a draw
        #   within a relative tolerance of the observed value as extreme, so a draw
        #   reproducing the observed grouping to the last bit is counted here as not
        #   extreme and this p is biased DOWN, towards significance.
        # Translating any of them is a change of number and belongs to a recompute, not
        # to a consolidation.
        pool_mask = is_decseen
        pool_vals = wvals[pool_mask]
        k = int(is_tox.sum())
        null = np.empty(NPERM)
        if pool_vals.size > k > 0:
            for i in range(NPERM):
                perm = rng.permutation(pool_vals.size)
                gt = pool_vals[perm[:k]].mean()
                gr = pool_vals[perm[k:]].mean()
                null[i] = gt - gr
            p = (1 + (null >= gap).sum()) / (1 + NPERM) if not np.isnan(gap) else float("nan")
        else:
            p = float("nan")
        results["cross_window"][h] = {
            "n_dec_toxic_in_fwd": int(gtox.size),
            "n_dec_rest_in_fwd": int(grest.size),
            "dec_toxic_fwd_markout_bps": float(gtox.mean()) if gtox.size else float("nan"),
            "dec_rest_fwd_markout_bps": float(grest.mean()) if grest.size else float("nan"),
            "gap_bps": gap,
            "placebo_p": float(p),
            "null_gap_mean": float(np.nanmean(null)) if pool_vals.size > k > 0 else float("nan"),
        }

    # Days present in the forward feed, taken from the parsed rows rather than from the
    # EARLY_DAYS / LATE_DAYS declaration: a recorder that stopped early leaves the
    # declaration intact and the data short, and the scope has to say what was READ.
    fwd_days = sorted({str(x) for d in fwd.values() for x in d["day"]})
    n_fwd_trades = int(sum(int(d["time"].size) for d in fwd.values()))

    artifact.write(
        os.path.basename(OUT_JSON), results,
        script=__file__,
        inputs=[NPZ_DEC, TAKER_MAP] + forward_files,
        scope={
            "population": (
                f"{n_fwd_trades:,} forward trade prints; wallets ranked at a "
                f"{MIN_FILLS_FWD}-fill forward floor and {MIN_FILLS_HALF} per half for "
                f"the within-window read. The frozen December set is "
                f"{len(dec_toxic):,} wallets, the top {int((1 - DEC_TOXIC_Q) * 100)} "
                f"percent by per-coin mean headline markout at a {DEC_MIN_FILLS}-fill "
                f"December floor, out of {len(dec_all):,} wallets seen in December"),
            "window": (
                f"forward days read: {', '.join(fwd_days) if fwd_days else 'none'}; "
                f"the toxic set is frozen from the December 2025 design window and is "
                f"never re-estimated here"),
            # Never an empty list: an empty scope field reads exactly like a scope
            # covering every coin, which is the opposite of what an empty feed means.
            "coins": (list(fwd.keys())
                      or "n/a: no coin of the forward feed carried a parsable trade"),
        },
        settings={
            "h": H.HEADLINE_HORIZON_S, "lens": "print",
            "master_seed": RNG_SEED,
            "n_perm": NPERM,
            "n_boot": None,
            "rank_floor_fills": MIN_FILLS_FWD,
            "december_floor_fills": DEC_MIN_FILLS,
            "override_reasons": {
                "lens": ("the forward feed carries trade prints only -- no book, so no "
                         "mid -- and the December set is frozen off the trade-print "
                         "column; this exhibit has no book-mid arm at all"),
                "master_seed": (f"the placebo stream is np.random.default_rng({RNG_SEED}) "
                                f"drawn once and shared across the three horizons, not "
                                f"settings.MASTER_SEED {H.MASTER_SEED} and not a "
                                f"per-cell stream; adopting either re-draws every "
                                f"placebo p in this file"),
                "n_perm": (f"{NPERM} draws, not the declared {H.N_PERM}. The floor is "
                           f"1/{NPERM + 1} = {1.0 / (NPERM + 1):.6f}, and the "
                           f"denominator here is the REQUESTED budget rather than the "
                           f"count of finite draws"),
                "n_boot": "no bootstrap is drawn in this file",
                "rank_floor_fills": (f"{MIN_FILLS_FWD} forward fills, not the declared "
                                     f"{H.RANK_FLOOR_FILLS}: the forward window is four "
                                     f"days against December's ten, so the December "
                                     f"floor would empty the ranked set"),
            },
        },
        started=t0)

    print("=== forward out-of-design toxicity confirmation ===")
    print("n_trades:", results["n_trades"])
    _hcol = H.headline_print_col()
    print(f"sanity BTC {_hcol} buy/sell fwd ret bps:",
          results["sanity"].get("BTC", {}).get(_hcol),
          "sign_ok:", results["sanity"][f"BTC_{_hcol}_sign_ok"])
    print("within-window persistence (early vs late Spearman):")
    for h, v in results["within_persistence"].items():
        print("  %-5s rho=%s n=%d" % (h, v["spearman_early_late"], v["n_wallets_common"]))
    print("cross-window Dec-toxic vs Dec-rest, forward markout (bps):")
    print("  dec_toxic wallets=%d, dec_all=%d" % (len(dec_toxic), len(dec_all)))
    for h in HORIZONS_MS:
        v = results["cross_window"].get(h, {})
        if "gap_bps" in v:
            print("  %-5s toxic=%+.3f rest=%+.3f gap=%+.3f p=%.3f (n_tox=%d n_rest=%d)" % (
                h, v["dec_toxic_fwd_markout_bps"], v["dec_rest_fwd_markout_bps"],
                v["gap_bps"], v["placebo_p"], v["n_dec_toxic_in_fwd"], v["n_dec_rest_in_fwd"]))
    print("wrote", os.path.basename(OUT_JSON))


if __name__ == "__main__":
    main()
