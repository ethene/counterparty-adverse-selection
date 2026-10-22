"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-20
References: Hyperliquid node-data S3 archive (s3://hl-mainnet-node-data); Hyperliquid
  L2-book archive (s3://hyperliquid-archive/market_data); Zenodo 18184441 (Albers et al. 2026).
"""

# ---------------------------------------------------------------------------
# chk_side_signconv.py  - RAW-DATA RE-VERIFICATION (the critical sign test)
#
# WHAT OUR CODE ASSUMES (these are TESTED here, not trusted):
#   - taker_side == 1 means a BUY-aggressor ("B", lifts the ask);
#     taker_side == 0 means a SELL-aggressor ("A", hits the bid).
#   - the signed markout uses taker_dir = +1 if side=="B" else -1, with
#         markout = taker_dir * (ref - entry)/entry * 1e4,
#     so POSITIVE = taker profited = maker adverse-selected.
#   - L2 levels[0]=bids, levels[1]=asks (so spread = ask - bid > 0).
#
# These conventions are baked into build_quickwin_markouts.py and i4_midmarkout.py.
# Prior audits only checked number-on-disk == number-in-doc; they could NOT catch a
# mis-read of the `side` field. This script grounds the semantics EMPIRICALLY,
# INDEPENDENTLY of the markout formula, and emits a verdict.
#
# INDEPENDENT ANCHOR (3 legs):
# (1) GOLD STANDARD forward-return test. Re-walk bqm.parse_day for a small
#     BTC+ETH December sample (mirrors i4_midmarkout.py: it imports
#     build_quickwin_markouts and reuses parse_day verbatim). Per collapsed fill we
#     recover taker entry timestamp (block_time ns -> epoch ms, exactly as
#     i4_midmarkout does: taker_ts // 1_000_000), taker_side, entry_px. We load the
#     SAME mid_series the pipeline joins against and, with the SAME no-lookahead
#     joins (entry = searchsorted side='right' minus 1; horizon = searchsorted
#     side='left'), compute the UNSIGNED forward mid return
#         r_h = (mid(t+h) - mid(t)) / mid(t)
#     at h in {1,10,60}s. We then split mean r_h by taker_side.
#     The `side==1 == buy-aggressor` convention holds IFF buy-side forward returns
#     sit systematically ABOVE sell-side forward returns - informed aggressors push
#     price in their own direction. We report the gap and its sign per horizon.
#
# (2) ENTRY-PRICE anchor. A buy-aggressor crosses UP to the ask, so its fill price
#     should be >= the contemporaneous mid; a sell-aggressor hits the bid, so
#     <= mid. We report the fraction of taker_side==1 fills with entry_px >= mid and
#     of taker_side==0 fills with entry_px <= mid (entry snapshot = same as-of join).
#
# (3) MARKOUT-SIGN reproduction. We re-derive the signed mid markout the pipeline
#     stores, from the UNSIGNED return times the assumed taker_dir
#         mo_h = sign_taker * r_h * 1e4,  sign_taker = +1 if side==1 else -1,
#     and confirm the SIGN of its sample mean reproduces the SIGN of the stored
#     mo*_mid mean in quickwin_markouts_mid.npz over the same coins. (Exact
#     row-by-row equality is not asserted because re-deriving the first-seen integer
#     coding row-for-row is out of scope; the aggregate sign is what the convention
#     turns on.)
#
# BONUS (orientation): we record the fraction of mid_series snapshots with
#   spread > 0 over the sampled coins as direct evidence that levels[0]=bids,
#   levels[1]=asks (a refuted orientation would flip the spread sign).
#
# VERDICT:
#   confirmed - (1) buy>sell forward-return gap AND (2) both entry-price fractions
#               clearly favour the assumed side, AND (3) signs reproduce.
#   refuted   - (1) and (2) point the OPPOSITE way (convention inverted).
#   uncertain - flat / mixed / ambiguous.
#
# OUTPUT (the shared check contract):
#   checks/chk_side_signconv_results.json
#
# Run (bare python3 is BLOCKED on this machine):
#   FULL  : uv run --no-project --with-requirements requirements.txt python3 checks/chk_side_signconv.py
#   SMOKE : uv run --no-project --with-requirements requirements.txt python3 checks/chk_side_signconv.py --smoke
#           (--smoke = 1 day, BTC only; re-walks a single December day -> light)
# ---------------------------------------------------------------------------

import json
import os
import sys

import numpy as np

# import the production parser so we re-walk the SAME parse_day the pipeline uses
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
CODE_DIR = os.path.dirname(THIS_DIR)          # the repository root
if CODE_DIR not in sys.path:
    sys.path.insert(0, CODE_DIR)
if THIS_DIR not in sys.path:
    sys.path.insert(0, THIS_DIR)
# The parser this gate calls lives in its pipeline group rather than beside it, so the
# group directory goes on the path too: the tree root alone does not resolve a module
# one level down. Named per group rather than globbed, so a later move fails loudly.
for _group in ("data", "persistence"):
    _p = os.path.join(CODE_DIR, _group)
    if _p not in sys.path:
        sys.path.insert(0, _p)

import artifact                        # noqa: E402
import build_quickwin_markouts as bqm  # noqa: E402
import settings as H                   # noqa: E402
from evidence import mismatch_text, report_contract   # noqa: E402

OUT_JSON = os.path.join(THIS_DIR, "chk_side_signconv_results.json")
# The parser is located by asking the module it just imported where it is, never by
# rebuilding a path from a directory this check assumes. It was rebuilt as
# CODE_DIR/build_quickwin_markouts.py until 2026-08-12, and the file moved into its
# pipeline group on 2026-08-11: the import still resolved, because the group directory
# is on the path above, so nothing failed -- the declaration simply recorded the parser
# as absent, with a null hash, under a verdict of confirmed. That is the direction of
# error this project treats as the dangerous one. The work stayed honest, since the walk
# runs through the imported module; only the RECORD of what was read went false, and a
# declared input carrying no hash cannot stale this artifact when the parser is edited,
# so the freshness gate had nothing to compare and said nothing.
BQM_SRC = os.path.abspath(bqm.__file__)
MID_PATH = {c: os.path.join(CODE_DIR, f"mid_series_{c}.npz") for c in ("BTC", "ETH")}
MID_NPZ = os.path.join(CODE_DIR, "quickwin_markouts_mid.npz")
QWM_NPZ = os.path.join(CODE_DIR, "quickwin_markouts.npz")

# dir_code -> implied taker buy/sell. A buy-aggressor (taker_side==1, "B", lifts the
# ask) either opens/extends a LONG or closes/covers a SHORT; a sell-aggressor
# (taker_side==0, "A", hits the bid) opens/extends a SHORT or closes a LONG. So with
# DIR_CODE = {Open Long:0, Open Short:1, Close Long:2, Close Short:3} (read from
# build_quickwin_markouts.py), Open Long(0) and Close Short(3) are BUYS while
# Open Short(1) and Close Long(2) are SELLS. dir_code==-1 (unknown) is excluded.
DIR_IMPLIED_BUY = {0, 3}      # Open Long, Close Short
DIR_IMPLIED_SELL = {1, 2}     # Open Short, Close Long

# Every rung this check re-derives a markout at, read from settings.py rather than
# typed. It has to be the whole ladder and not the headline alone: the sign convention
# is asserted at each rung separately, and a rung with no column in the artifact cannot
# be re-derived at all. Proved equal before the move: the literal here was (1, 10, 60)
# and settings.LADDER_S is (1, 10, 60).
HORIZONS_S = H.LADDER_S
MS_PER_S = 1000
GAP_MAX_MS = 5000.0           # same join tolerance the pipeline uses

# FULL sample: a 2-day BTC+ETH window (light re-walk, sanctioned by the brief).
FULL_DAYS = ["20251204", "20251205"]
FULL_COINS = ("BTC", "ETH")
# SMOKE: 1 day, BTC only.
SMOKE_DAYS = ["20251204"]
SMOKE_COINS = ("BTC",)


# -------------------- mid series loader (same de-dup discipline as pipeline) ---
def load_mid_series(coins):
    series = {}
    for coin in coins:
        path = MID_PATH.get(coin)
        if path is None or not os.path.exists(path):
            raise FileNotFoundError(mismatch_text(
                f"the mid-price series this check re-derives {coin} against",
                f"a built mid series for {coin} beside the producer",
                "no file at that name" if path else
                "no path is declared for this coin at all",
                os.path.basename(path) if path else f"MID_PATH has no entry for {coin}",
                "the artifact has not been built in this clone: run i4_l2_mid.py "
                "first. This is a fact about the machine, not about the repository"))
        z = np.load(path, allow_pickle=False)
        t_ms = np.asarray(z["t_ms"], dtype=np.int64)
        mid = np.asarray(z["mid"], dtype=np.float64)
        spread = np.asarray(z["spread"], dtype=np.float64)
        if t_ms.size:
            order = np.argsort(t_ms, kind="stable")
            t_ms, mid, spread = t_ms[order], mid[order], spread[order]
            keep = np.ones(t_ms.size, dtype=bool)
            keep[:-1] = t_ms[1:] != t_ms[:-1]      # runs of equal t_ms -> keep last
            t_ms, mid, spread = t_ms[keep], mid[keep], spread[keep]
        series[coin] = {"t_ms": t_ms, "mid": mid, "spread": spread}
    return series


# -------------------- no-lookahead joins: CALLED, not copied --------------------
# This block used to re-implement i4_midmarkout.join_entry and describe itself as the
# "verbatim sense" of it. On 2026-08-02 the two drifted: the producer moved to a strictly
# earlier snapshot, because one stamped with the fill's own millisecond already carries
# that fill's impact, and this copy stayed on the old rule. A check that copies the logic
# it checks cannot catch the logic changing -- it can only start disagreeing for reasons
# that look like a finding and are not. So the rule is now called from its one home.
import i4_midmarkout as I4                                       # noqa: E402


def join_entry(t_fill_ms, S):
    """LAST snapshot STRICTLY EARLIER than t_fill, from the producer's own function."""
    return I4.join_entry(t_fill_ms, S)


def join_horizon(t_fill_ms, h_s, S):
    """FIRST snapshot with snapshot_t >= t_fill + h*1000."""
    t_arr = S["t_ms"]
    n = t_arr.size
    target = t_fill_ms + h_s * MS_PER_S
    idx = np.searchsorted(t_arr, target, side="left")
    valid = idx < n
    gap = np.full(t_fill_ms.shape, np.inf, dtype=np.float64)
    safe = np.where(valid, idx, 0)
    gap[valid] = np.abs(
        t_arr[safe[valid]].astype(np.float64) - target[valid].astype(np.float64))
    valid &= gap <= GAP_MAX_MS
    return idx, gap, valid


# -------------------- re-walk parse_day and harvest the sample ----------------
def harvest_sample(days, coins):
    """Re-walk bqm.parse_day for the requested days/coins, returning per coin:
       t_fill_ms, taker_side (int8), entry_px (float64).  Mirrors i4_midmarkout."""
    # constrain the imported module to exactly the requested days/coins so the
    # SAME fills are parsed (parse_day reads whole days; coin filter is applied here)
    bqm.DAYS = list(days)
    bqm.COINS = tuple(coins)

    acc = {c: {"t_ms": [], "side": [], "px": []} for c in coins}
    walked_days = []
    for day in days:
        per_coin, _hours = bqm.parse_day(day)
        if per_coin is None:
            continue
        walked_days.append(day)
        for coin in coins:
            d = per_coin.get(coin)
            if d is None or int(d["taker_ts"].size) == 0:
                continue
            # EXACT reconstruction i4_midmarkout uses: block_time ns -> epoch ms
            t_ms = (np.asarray(d["taker_ts"], dtype=np.int64) // 1_000_000).astype(np.int64)
            acc[coin]["t_ms"].append(t_ms)
            acc[coin]["side"].append(np.asarray(d["taker_side"], dtype=np.int8))
            acc[coin]["px"].append(np.asarray(d["taker_px"], dtype=np.float64))

    out = {}
    for coin in coins:
        if acc[coin]["t_ms"]:
            out[coin] = {
                "t_ms": np.concatenate(acc[coin]["t_ms"]),
                "side": np.concatenate(acc[coin]["side"]),
                "px": np.concatenate(acc[coin]["px"]),
            }
        else:
            out[coin] = {"t_ms": np.empty(0, np.int64),
                         "side": np.empty(0, np.int8),
                         "px": np.empty(0, np.float64)}
    return out, walked_days


# -------------------- the three legs on the harvested sample ------------------
def run_checks(sample, mid_series, coins):
    # pool fills across the sampled coins, joining each coin to its own mid series.
    # per-horizon accumulators of UNSIGNED forward return and the side label.
    r_by_h = {h: [] for h in HORIZONS_S}
    side_by_h = {h: [] for h in HORIZONS_S}
    # entry-price anchor accumulators
    buy_ge_mid = 0          # taker_side==1 fills with entry_px >= mid
    buy_total = 0
    sell_le_mid = 0         # taker_side==0 fills with entry_px <= mid
    sell_total = 0
    n_fills_total = 0
    n_joined_entry = 0

    for coin in coins:
        s = sample[coin]
        S = mid_series[coin]
        n = s["t_ms"].size
        n_fills_total += int(n)
        if n == 0 or S["t_ms"].size == 0:
            continue
        t_ms = s["t_ms"]
        side = s["side"]
        px = s["px"]

        e_idx, _e_gap, e_valid = join_entry(t_ms, S)
        e_safe = np.where(e_valid, e_idx, 0)
        mid_entry = S["mid"][e_safe]
        n_joined_entry += int(e_valid.sum())

        # ENTRY-PRICE anchor (leg 2) - only where the entry snapshot joined
        ev = e_valid & np.isfinite(mid_entry) & (mid_entry > 0) & np.isfinite(px)
        is_buy = (side == 1) & ev
        is_sell = (side == 0) & ev
        buy_ge_mid += int(np.sum(px[is_buy] >= mid_entry[is_buy]))
        buy_total += int(np.sum(is_buy))
        sell_le_mid += int(np.sum(px[is_sell] <= mid_entry[is_sell]))
        sell_total += int(np.sum(is_sell))

        # GOLD-STANDARD forward return (leg 1)
        for h in HORIZONS_S:
            h_idx, _h_gap, h_valid = join_horizon(t_ms, h, S)
            h_safe = np.where(h_valid, h_idx, 0)
            mid_h = S["mid"][h_safe]
            ok = e_valid & h_valid & np.isfinite(mid_entry) & (mid_entry > 0) & np.isfinite(mid_h)
            r = (mid_h[ok] - mid_entry[ok]) / mid_entry[ok]   # UNSIGNED forward return
            r_by_h[h].append(r)
            side_by_h[h].append(side[ok])

    # ---- assemble leg-1 stats ----
    fwd = {}
    for h in HORIZONS_S:
        r = np.concatenate(r_by_h[h]) if r_by_h[h] else np.empty(0)
        sd = np.concatenate(side_by_h[h]) if side_by_h[h] else np.empty(0, np.int8)
        buy = r[sd == 1]
        sell = r[sd == 0]
        mean_buy = float(np.mean(buy)) if buy.size else float("nan")
        mean_sell = float(np.mean(sell)) if sell.size else float("nan")
        gap = mean_buy - mean_sell
        fwd[h] = {
            "n_buy": int(buy.size), "n_sell": int(sell.size),
            "mean_fwd_ret_buy": mean_buy,        # raw return units (not bps)
            "mean_fwd_ret_sell": mean_sell,
            "buy_minus_sell": float(gap),
            "buy_minus_sell_bps": float(gap * 1e4),
            "buy_above_sell": bool(np.isfinite(gap) and gap > 0),
        }

    # ---- leg-2 stats ----
    frac_buy_ge = (buy_ge_mid / buy_total) if buy_total else float("nan")
    frac_sell_le = (sell_le_mid / sell_total) if sell_total else float("nan")

    # ---- leg-3: reproduce the stored mid-markout SIGN ----
    # re-derived signed markout on the sample: sign_taker * r_h * 1e4
    # take the 10s horizon as the reference (the pipeline's headline mo10_mid).
    rederived_mo10_sign = None
    rederived_mo10_mean_bps = float("nan")
    r10 = np.concatenate(r_by_h[10]) if r_by_h[10] else np.empty(0)
    sd10 = np.concatenate(side_by_h[10]) if side_by_h[10] else np.empty(0, np.int8)
    if r10.size:
        sign_taker = np.where(sd10 == 1, 1.0, -1.0)
        mo10_rederived = sign_taker * r10 * 1e4
        rederived_mo10_mean_bps = float(np.mean(mo10_rederived))
        rederived_mo10_sign = int(np.sign(rederived_mo10_mean_bps))

    # stored mo10_mid mean SIGN over the same coins (from quickwin_markouts_mid.npz)
    stored_mo10_mean_bps = float("nan")
    stored_mo10_sign = None
    if os.path.exists(MID_NPZ):
        zz = np.load(MID_NPZ, allow_pickle=False)
        coin_codes = {bqm.COIN_CODE[c] for c in coins if c in bqm.COIN_CODE}
        coin_arr = np.asarray(zz["coin"], dtype=np.int64)
        sel = np.isin(coin_arr, list(coin_codes))
        m10 = np.asarray(zz["mo10_mid"], dtype=np.float64)[sel]
        m10 = m10[np.isfinite(m10)]
        if m10.size:
            stored_mo10_mean_bps = float(np.mean(m10))
            stored_mo10_sign = int(np.sign(stored_mo10_mean_bps))

    sign_reproduced = (
        rederived_mo10_sign is not None
        and stored_mo10_sign is not None
        and rederived_mo10_sign == stored_mo10_sign
        and rederived_mo10_sign != 0
    )

    # ---- bonus: spread orientation over the sampled coins ----
    spread_pos_frac = {}
    for coin in coins:
        sp = mid_series[coin]["spread"]
        spread_pos_frac[coin] = float(np.mean(sp > 0)) if sp.size else float("nan")

    return {
        "n_fills_sampled": n_fills_total,
        "n_entry_joined": n_joined_entry,
        "forward_return": fwd,
        "entry_price_anchor": {
            "frac_buy_entry_ge_mid": float(frac_buy_ge),
            "frac_sell_entry_le_mid": float(frac_sell_le),
            "n_buy": buy_total, "n_sell": sell_total,
        },
        "markout_sign": {
            "rederived_mo10_mean_bps": rederived_mo10_mean_bps,
            "rederived_mo10_sign": rederived_mo10_sign,
            "stored_mo10_mid_mean_bps": stored_mo10_mean_bps,
            "stored_mo10_mid_sign": stored_mo10_sign,
            "sign_reproduced": bool(sign_reproduced),
        },
        "spread_pos_frac": spread_pos_frac,
    }


# -------------------- dir_code vs taker_side agreement (local npz) -------------
def dir_vs_takerside_check():
    """INDEPENDENT side-semantics anchor on quickwin_markouts.npz.

    dir_code (from the raw `dir` string) and taker_side (from the raw `side`
    field) are two DIFFERENT raw keys. For every fill whose buy/sell direction is
    implied by dir_code (Open Long / Close Short => buy; Open Short / Close Long
    => sell), the implied direction must equal taker_side (1=buy, 0=sell). This is
    a STRONGER independent confirmation than the forward-return leg because it uses
    a different raw key and covers ETH directly (the markout legs above also do,
    but this anchor needs no mid series and no as-of join). dir_code==-1 (unknown)
    rows are excluded. We assert the agreement fraction == 1.0 (the audit found
    ZERO mismatches across BTC ~1.18M and ETH ~1.26M rows).
    """
    if not os.path.exists(QWM_NPZ):
        return {
            "name": "dir_code_vs_taker_side_agreement",
            "assumption": "dir_code-implied buy/sell (Open Long/Close Short=buy, "
                          "Open Short/Close Long=sell) must equal taker_side "
                          "(1=buy, 0=sell).",
            "method": "load quickwin_markouts.npz; cross dir_code-implied direction "
                      "against taker_side over rows with a known dir_code.",
            "observed": {"path": QWM_NPZ, "exists": False},
            "verdict": "uncertain",
            "note": "quickwin_markouts.npz not found; cannot run the dir-vs-side "
                    "agreement anchor.",
        }

    z = np.load(QWM_NPZ, allow_pickle=False)
    dir_code = np.asarray(z["dir_code"], dtype=np.int64)
    taker_side = np.asarray(z["taker_side"], dtype=np.int64)
    coin = np.asarray(z["coin"], dtype=np.int64) if "coin" in z.files else None

    implied_buy = np.isin(dir_code, list(DIR_IMPLIED_BUY))
    implied_sell = np.isin(dir_code, list(DIR_IMPLIED_SELL))
    known = implied_buy | implied_sell          # exclude dir_code==-1 (unknown)
    implied_side = np.where(implied_buy, 1, 0)   # 1=buy, 0=sell on the known rows

    agree = (implied_side[known] == taker_side[known])
    n_known = int(known.sum())
    n_agree = int(agree.sum())
    n_mismatch = n_known - n_agree
    agreement_frac = (n_agree / n_known) if n_known else float("nan")

    # the hardening assert the audit asked for: ZERO mismatches.
    assert n_mismatch == 0, mismatch_text(
        "dir_code and taker_side say the same thing about every fill",
        f"the side implied by dir_code equals taker_side on all {n_known:,} rows "
        f"whose direction is known, an agreement fraction of exactly 1.0",
        f"{n_mismatch:,} rows disagree, an agreement fraction of "
        f"{agreement_frac:.6f}",
        f"{os.path.basename(QWM_NPZ)}, columns dir_code and taker_side",
        "the two raw keys carry different side semantics, so which of them a "
        "producer happened to read decides the sign of its result")

    # per-coin breakdown (covers ETH explicitly, per the audit).
    per_coin = {}
    coin_name = {0: "BTC", 1: "ETH"}
    if coin is not None:
        for code in np.unique(coin[known]):
            m = known & (coin == code)
            nk = int(m.sum())
            na = int((implied_side[m] == taker_side[m]).sum())
            per_coin[coin_name.get(int(code), f"coin_{int(code)}")] = {
                "n_known": nk,
                "n_agree": na,
                "n_mismatch": nk - na,
                "agreement_frac": (na / nk) if nk else float("nan"),
            }

    verdict = "confirmed" if (n_known > 0 and n_mismatch == 0) else "uncertain"
    return {
        "name": "dir_code_vs_taker_side_agreement",
        "assumption": "dir_code-implied buy/sell (Open Long/Close Short=buy, "
                      "Open Short/Close Long=sell) must equal taker_side "
                      "(1=buy, 0=sell). Independent of the forward-return / "
                      "entry-price legs because it reads a DIFFERENT raw key.",
        "method": "Loaded quickwin_markouts.npz; mapped dir_code to an implied "
                  "buy/sell (Open Long 0 / Close Short 3 => buy; Open Short 1 / "
                  "Close Long 2 => sell), excluded dir_code==-1, and compared the "
                  "implied direction to taker_side row-by-row, pooled and per coin. "
                  "Asserts agreement_frac == 1.0.",
        "observed": {
            "n_known_dir": n_known,
            "n_agree": n_agree,
            "n_mismatch": n_mismatch,
            "agreement_frac": agreement_frac,
            "per_coin": per_coin,
        },
        "verdict": verdict,
        "note": ("dir_code-implied side equals taker_side on every known-dir fill "
                 "(zero mismatches) across the coins present -> the buy/sell "
                 "semantics agree across two independent raw keys, ETH included."
                 if verdict == "confirmed" else
                 "no known-dir rows to test; agreement anchor inconclusive."),
    }


# -------------------- verdict logic + contract assembly -----------------------
def build_contract(stats, days, coins, smoke):
    fwd = stats["forward_return"]
    epa = stats["entry_price_anchor"]
    msg = stats["markout_sign"]

    # leg-1 verdict: buy>sell at the horizons that have data.
    gaps = [fwd[h]["buy_minus_sell_bps"] for h in HORIZONS_S
            if np.isfinite(fwd[h]["buy_minus_sell_bps"]) and fwd[h]["n_buy"] > 0
            and fwd[h]["n_sell"] > 0]
    if not gaps:
        leg1 = "uncertain"
    elif all(g > 0 for g in gaps):
        leg1 = "confirmed"
    elif all(g < 0 for g in gaps):
        leg1 = "refuted"
    else:
        leg1 = "uncertain"

    # leg-2 verdict: both directional fractions should clearly exceed 0.5
    # (buys at/above mid, sells at/below mid). >=0.90 = clean, <=0.10 = inverted.
    fbg = epa["frac_buy_entry_ge_mid"]
    fsl = epa["frac_sell_entry_le_mid"]
    if not (np.isfinite(fbg) and np.isfinite(fsl)):
        leg2 = "uncertain"
    elif fbg >= 0.90 and fsl >= 0.90:
        leg2 = "confirmed"
    elif fbg <= 0.10 and fsl <= 0.10:
        leg2 = "refuted"
    elif fbg > 0.5 and fsl > 0.5:
        leg2 = "confirmed"          # both favour the assumed side, just not razor-clean
    elif fbg < 0.5 and fsl < 0.5:
        leg2 = "refuted"
    else:
        leg2 = "uncertain"

    # dir_code-vs-taker_side agreement anchor (local npz, independent raw key).
    dir_side = dir_vs_takerside_check()
    leg_dirside = dir_side["verdict"]

    # overall (min-tier combine over the legs that produce a directional verdict):
    # confirmed iff leg1, leg2 AND the dir-vs-side anchor all confirm; refuted iff
    # any leg refutes; uncertain otherwise.
    leg_verdicts = [leg1, leg2, leg_dirside]
    if "refuted" in leg_verdicts:
        overall = "refuted"
    elif all(v == "confirmed" for v in leg_verdicts):
        overall = "confirmed"
    else:
        overall = "uncertain"

    checks = []

    # ---- check 1 ----
    h_lines = "; ".join(
        f"{h}s buy={fwd[h]['mean_fwd_ret_buy']*1e4:+.3f}bps "
        f"sell={fwd[h]['mean_fwd_ret_sell']*1e4:+.3f}bps "
        f"gap={fwd[h]['buy_minus_sell_bps']:+.3f}bps"
        for h in HORIZONS_S if fwd[h]["n_buy"] > 0 and fwd[h]["n_sell"] > 0)
    checks.append({
        "name": "gold_standard_forward_return_by_side",
        "assumption": "taker_side==1 is a BUY-aggressor (lifts ask); informed buys "
                      "push the mid UP, so mean forward mid return for side==1 must "
                      "exceed that for side==0.",
        "method": "Re-walked bqm.parse_day for the sample, recovered per-fill entry "
                  "timestamp (block_time ns//1e6), taker_side, entry_px (same as "
                  "i4_midmarkout). Joined the SAME mid_series with the SAME "
                  "no-lookahead as-of joins (entry side='right'-1, horizon side='left') "
                  "and computed UNSIGNED r_h=(mid(t+h)-mid(t))/mid(t) at 1/10/60s; "
                  "split mean r_h by taker_side. Independent of the markout formula.",
        "observed": {
            "by_horizon": {str(h): fwd[h] for h in HORIZONS_S},
            "summary": h_lines,
        },
        "verdict": leg1,
        "note": ("buy-side forward return is above sell-side at every horizon -> "
                 "side==1 behaves as a buy-aggressor."
                 if leg1 == "confirmed" else
                 "buy-side forward return is BELOW sell-side -> the side label is "
                 "INVERTED relative to the assumption."
                 if leg1 == "refuted" else
                 "forward-return gap is flat/mixed across horizons - inconclusive."),
    })

    # ---- check 2 ----
    checks.append({
        "name": "entry_price_vs_mid_by_side",
        "assumption": "A buy-aggressor (side==1) crosses up to the ask so entry_px>=mid; "
                      "a sell-aggressor (side==0) hits the bid so entry_px<=mid.",
        "method": "On the same re-walked fills, joined the entry mid snapshot "
                  "(last-at-or-before) and measured the fraction of side==1 fills with "
                  "entry_px>=mid and side==0 fills with entry_px<=mid.",
        "observed": {
            "frac_buy_entry_ge_mid": fbg,
            "frac_sell_entry_le_mid": fsl,
            "n_buy": epa["n_buy"], "n_sell": epa["n_sell"],
        },
        "verdict": leg2,
        "note": ("both directional fractions favour the assumed side (buys at/above "
                 "mid, sells at/below mid)." if leg2 == "confirmed" else
                 "fractions point the OPPOSITE way - side label inverted."
                 if leg2 == "refuted" else
                 "fractions are mixed (one side favours, the other does not)."),
    })

    # ---- check 3 ----
    checks.append({
        "name": "markout_sign_reproduction",
        "assumption": "stored mo*_mid = sign_taker*(mid(t+h)-mid(t))/mid(t)*1e4 with "
                      "sign_taker=+1 if side==1 else -1; POSITIVE mean = taker profited "
                      "= maker adverse-selected.",
        "method": "Re-derived mo10 on the sample as sign_taker*r_10*1e4 from the "
                  "UNSIGNED return and the assumed taker_dir, and compared the SIGN of "
                  "its mean to the SIGN of the stored mo10_mid mean in "
                  "quickwin_markouts_mid.npz over the same coins.",
        "observed": msg,
        "verdict": "confirmed" if msg["sign_reproduced"] else
                   ("uncertain" if msg["rederived_mo10_sign"] is None
                    or msg["stored_mo10_mid_sign"] is None else "refuted"),
        "note": ("re-derived markout-sign matches the stored mo10_mid sign."
                 if msg["sign_reproduced"] else
                 "re-derived markout-sign does NOT match the stored mo10_mid sign."),
    })

    # ---- bonus orientation check ----
    sp = stats["spread_pos_frac"]
    sp_ok = all(np.isfinite(v) and v >= 0.999 for v in sp.values()) and len(sp) > 0
    checks.append({
        "name": "l2_levels_orientation_spread_sign",
        "assumption": "L2 levels[0]=bids, levels[1]=asks, so spread=ask-bid>0.",
        "method": "Fraction of mid_series snapshots with spread>0 over the sampled coins.",
        "observed": {"spread_pos_frac": sp},
        "verdict": "confirmed" if sp_ok else
                   ("refuted" if (sp and all(np.isfinite(v) and v <= 0.001
                                             for v in sp.values())) else "uncertain"),
        "note": ("spread is positive on ~all snapshots -> bids/asks not swapped."
                 if sp_ok else
                 "spread is non-positive on a material fraction of snapshots - "
                 "levels orientation suspect."),
    })

    # ---- dir_code vs taker_side agreement (independent raw key, local npz) ----
    checks.append(dir_side)

    contract = {
        "check": "side_signconv",
        "mode": "smoke" if smoke else "full",
        "config": {
            "days_walked": list(days),
            "coins": list(coins),
            "horizons_s": list(HORIZONS_S),
            "gap_max_ms": GAP_MAX_MS,
            "n_fills_sampled": stats["n_fills_sampled"],
            "n_entry_joined": stats["n_entry_joined"],
        },
        "checks": checks,
        "overall_verdict": overall,
    }
    return contract


# -------------------- main --------------------
def main():
    started = artifact.start_clock()
    smoke = "--smoke" in sys.argv
    days = SMOKE_DAYS if smoke else FULL_DAYS
    coins = SMOKE_COINS if smoke else FULL_COINS

    print(f"[chk_side_signconv] mode={'smoke' if smoke else 'full'} "
          f"days={days} coins={coins}")

    mid_series = load_mid_series(coins)
    sample, walked = harvest_sample(days, coins)
    days_used = walked if walked else days
    stats = run_checks(sample, mid_series, coins)
    contract = build_contract(stats, days_used, coins, smoke)

    # `days_used` rather than `days`: the walk keeps the days it actually reached,
    # and a scope naming the days REQUESTED would describe a window this run did not
    # cover whenever an hour was unavailable. The mid series are hashed; the hourly
    # tape objects the walk reads are deleted as it goes and cannot be.
    artifact.write(
        os.path.basename(OUT_JSON), contract,
        script=__file__,
        inputs=[MID_PATH[c] for c in sorted(MID_PATH)] + [BQM_SRC],
        scope={
            "population": f"the fills sampled from {len(days_used)} re-walked "
                          f"day(s) across {len(coins)} coin(s), compared against "
                          f"the mid series named in inputs",
            "window": f"{len(days_used)} days: {sorted(days_used)}"
                      + (" (--smoke)" if smoke else ""),
            "coins": sorted(coins),
        },
        started=started,
    )

    # one-line human summary
    fwd = stats["forward_return"]
    epa = stats["entry_price_anchor"]
    g10 = fwd[10]["buy_minus_sell_bps"]
    dvs = next((c for c in contract["checks"]
                if c["name"] == "dir_code_vs_taker_side_agreement"), None)
    dvs_frac = dvs["observed"].get("agreement_frac") if dvs else float("nan")
    print(
        f"[chk_side_signconv] OVERALL={contract['overall_verdict'].upper()} | "
        f"fwd-ret(10s) buy-sell gap={g10:+.3f}bps | "
        f"buy>=mid={epa['frac_buy_entry_ge_mid']:.3f} "
        f"sell<=mid={epa['frac_sell_entry_le_mid']:.3f} | "
        f"sign_reproduced={stats['markout_sign']['sign_reproduced']} | "
        f"dir-vs-side agree={dvs_frac:.6f} "
        f"-> {os.path.basename(OUT_JSON)}"
    )
    # The markout sign convention is what makes a positive number mean harm to the
    # taker rather than to the maker. A refutation inverts the meaning of every
    # headline figure in the study, so it stops the run and prints the buy-minus-sell
    # gap it expected beside the one it measured.
    return report_contract(contract, OUT_JSON,
                           inputs={"days": list(days_used), "coins": list(coins),
                                   "mode": "smoke" if smoke else "full"})


if __name__ == "__main__":
    sys.exit(main())
