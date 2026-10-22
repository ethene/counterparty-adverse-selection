"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-22
References: [Hyperliquid L4 (Zenodo 18184441, Albers et al. 2026); node_fills_by_block]
"""

# ===========================================================================
# PROBE F — HLP-vault-as-counterparty (PART 1) + liquidation negative control
# (PART 2). Two parts, one script. Adapts m8_makerside.py; reuses the
# kss_decomp_c.py two-way solver and the eb_scoring.py shrinkage idea.
#
# ---------------------------------------------------------------------------
# PART 1 — HLP protocol-vault flow (runs NOW on the panel shards, HEAVY).
# ---------------------------------------------------------------------------
# Question. The Hyperliquid Provider (HLP) vault is the protocol-owned market
# maker / backstop. We DO NOT claim it is the top-of-book quoter (it is not --
# the dominant makers are other codes). The honest claim is: how
# adverse-selected is the protocol-vault flow relative to non-HLP maker flow?
# A backstop that absorbs toxic flow should face a HIGHER (more positive) mo60
# markout than the ordinary maker population.
#
# HLP identity. The two HLP market-making sub-vaults are:
#     code/addr A : 0x010461c14e146ac35fe42271bdc1134ee31c703a  (HLP Strategy A)
#     code/addr B : 0x31ca8395cf837de08b24da3f660e77761dfb974b  (HLP Strategy B)
# CRITICAL data-space note (verified 2026-06-22). The integer maker_id in
# panel_markouts.npz is a GLOBAL first-seen RE-CODE produced by panel_build.py,
# which is a DIFFERENT code space from maker_map.json (built by
# build_quickwin_markouts.py). In the panel, code 168 != HLP-A and code 12 !=
# HLP-B (row counts disagree: 5551 vs 3140, 18903 vs 2265). maker_map.json's
# 168/12 = HLP only in the QUICKWIN space. So PART 1 identifies HLP by RAW
# WALLET ADDRESS from the per-coin checkpoint shards (panel_ckpt/shard_*.npz,
# which retain maker_addr), NOT by trusting any integer code. This also buys
# full panel coverage (3 coins x 8 windows) instead of quickwin's Dec BTC+ETH.
# A documented (untrusted) cross-check on the maker_map codes is printed so the
# mis-alignment is on the record, never relied upon.
#
# Reference-mid rule (HARD CONSTRAINT 3). mo60 here is the TRADE-PRINT markout
# (execution-cost lens, includes spread). HLP-vs-rest is read as a RANKING /
# contrast in that single consistent reference, never as an absolute book-mid
# level. The HL oracle/mark is never used (circular: stake-weighted CEX median).
#
# Markout sign (HARD CONSTRAINT 6). mo60 > 0 = taker profited = the maker that
# filled was adverse-selected. A maker faces the SAME signed number, so a higher
# mean mo60 faced => that maker set is more adverse-selected. We aggregate mo60
# per maker AS IS (matches m8_makerside.py).
#
# What PART 1 reports, per coin and pooled:
#   * HLP set vs non-HLP makers: mean signed mo60 faced (equal- and
#     notional-weighted), fill counts, HLP share of all maker fills, HLP share
#     of DOMINANT-maker fills (top makers by notional);
#   * a two-way (taker x maker) FE maker-side variance share contrasting HLP vs
#     the rest (reuse the kss_decomp_c.py alternating-projection solver + the
#     split-half de-bias), reported as the HLP-collapsed psi vs the full psi;
#   * an Empirical-Bayes contrast: HLP's shrunk per-vault score vs the non-HLP
#     maker prior (reuse the eb_scoring.py shrink-to-prior recipe).
#
# Pre-registered KILL-CRITERION (PART 1). If HLP-set mean mo60 faced is NOT
# reliably MORE POSITIVE than the non-HLP maker mean (i.e. the gap's
# label-shuffle placebo p > 0.05 OR the sign flips after whale-drop), then "HLP
# flow is more adversely-selected than ordinary maker flow" is NOT supported --
# report it as a null and frame HLP as an ordinary (or spread-earning) maker.
#
# Placebo  : shuffle the HLP label across makers (preserve the HLP fill count,
#            break identity); the HLP-vs-rest gap must vanish.
# Whale-drop: drop the top-5 NON-HLP makers by notional (and, separately, the
#            top-5 takers); the HLP-vs-rest sign must survive.
# Per-coin : every statistic reported per coin AND pooled (never pooled-only).
#
# ---------------------------------------------------------------------------
# PART 2 — liquidation negative/positive control (GATED).
# ---------------------------------------------------------------------------
# The `liquidation` marker (node_fills_by_block nested object: liquidatedUser +
# markPx + method) was DROPPED at npz-persist, so it is NOT in the current
# panel/quickwin npz. PART 2 reads an is_liq / liquidation column IF the npz has
# been re-pulled with it; else it exits that section cleanly with
#     GATED: needs block_time+liquidation re-pull
# Question (when ungated): is liquidation-driven flow systematically MORE or LESS
# toxic (mo60 markout) than normal flow? Forced liquidations are mechanically-
# triggered, not informed, so they should be a NEGATIVE control (markout near
# zero or negative = NOT toxic) -- a clean placebo for the toxicity construct.
#
# INTERIM (optional, --zenodo-interim): a single one-hour Zenodo-tar pass that
# extracts ONE small member from ../02_data/raw/trades_2025_12.tar and
# splits trades by trade_dir_override == "LiquidatedMarket" vs "Na", reporting
# the sign of the buy-aggressor forward return as a coarse markout proxy. This
# is a sanity peek only (no startPos book-mid; one hour), clearly labelled.
#
# numpy/scipy only. Heavy => run PART 1 in background. Read-only on data.
# Writes probe_F_hlp_liq_results.json. No plotting.
# ===========================================================================

import argparse
import glob
import gzip
import json           # still needed to READ maker_map.json and the Zenodo jsonl lines;
import os             # the results file itself is written by artifact.write, not here
import sys
import tarfile

import numpy as np

# ---------------------------------------------------------------------------
# Paths / config
# ---------------------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
CODE_DIR = os.path.dirname(HERE)                              # the repository root

# The settings module lives one directory up, so the path is built from this file's own
# location and never from the working directory the run happens to start in.
sys.path.insert(0, CODE_DIR)
import artifact  # noqa: E402
import settings as H  # noqa: E402
import stats  # noqa: E402
SHARD_GLOB = os.path.join(CODE_DIR, "panel_ckpt", "shard_*.npz")
PANEL_NPZ = os.path.join(CODE_DIR, "panel_markouts.npz")     # for the maker_map cross-check + PART 2
PANEL_NPZ_V2 = os.path.join(CODE_DIR, "panel_markouts_v2.npz")  # re-pulled w/ block_time_ns + is_liq (PART 2 prefers this)
MAKER_MAP_PATH = os.path.join(CODE_DIR, "maker_map.json")
ZENODO_TAR = os.path.join(CODE_DIR, "..", "02_data", "raw", "trades_2025_12.tar")
OUT_PATH = os.path.join(HERE, "probe_F_hlp_liq_results.json")

# int8 code -> symbol for the PANEL space, which is what this probe reads. The map is a
# property of the FILE (panel_markouts.npz carries {0, 1, 2}, the December quickwin
# artifact {0, 1}), so it is asked for by artifact name and never written out here.
COIN_NAME = H.coin_labels("panel")

# HLP market-making sub-vault wallet addresses (lowercase hex). These are the
# ONLY trustworthy HLP identifiers across data spaces; resolve by address.
HLP_A = "0x010461c14e146ac35fe42271bdc1134ee31c703a"   # HLP Strategy A
HLP_B = "0x31ca8395cf837de08b24da3f660e77761dfb974b"   # HLP Strategy B
HLP_SET = {HLP_A, HLP_B}
# Liquidator sub-vault + assistance fund: NOT maker-makers, excluded from HLP set.
HLP_LIQUIDATOR = "0x2e3d94f0562703b25c83308a05046ddaf9a8dd14"
ASSISTANCE_FUND = "0xfefefefefefefefefefefefefefefefefefefefe"

# expected quickwin-space codes (DOCUMENTED, never trusted on the panel)
QUICKWIN_HLP_CODES = {168: HLP_A, 12: HLP_B}

# The label-shuffle seed, READ from settings.py and no longer typed. It is NOT
# settings.MASTER_SEED and rebinding it to MASTER_SEED is still refused: each per-coin
# contrast opens its OWN generator at SEED + 10 + coin and the pooled one at SEED + 99,
# so this value is the origin of a family of streams rather than one stream, and moving
# it would move every placebo p in the file at once. What changed here is the HOME and
# not the value -- 690 is what this probe and six others draw, so it is declared per
# purpose in settings.SEED_BY_PURPOSE. Proved equal before the move: the literal here
# was 690 and seed_for("probe_F_hlp_liq") returns 690. Recorded as an override against
# MASTER_SEED in the artifact's fingerprint.
#
# Note for whoever migrates this further: the `rng = np.random.default_rng(SEED)` opened
# at the top of run_part1 is DEAD -- nothing reads it, because every contrast builds its
# own. It is left in place rather than deleted so this pass moves no number, but it
# reads as if one stream were threaded through PART 1, and it is not. The second-part
# control at the bottom of the file opened a third copy of the same value inline; it now
# binds this name, so the file holds the value in one place.
SEED = H.seed_for("probe_F_hlp_liq")

# THE WINDOW THIS PROBE SCORES ON, ASKED FOR RATHER THAN SPELLED. Five places in this
# file used to write the bare literal "mo60": three in the shard loader (the column it
# reads from each shard, and the key it packs its own dict under), one where that dict is
# unpacked, and one in the second-part liquidation control that reads the v2 panel. A
# column name IS the window, so each of those five fixed a 60 s horizon that no search
# for the word "horizon" could find -- the defect checks/chk_headline_horizon.py exists
# to catch. settings.companion_print_col() returns "mo60" today, so every one of the five
# reads the same column it read before and no number moves; what changes is that the five
# can no longer drift apart from each other or from the declaration.
#
# It is the COMPANION window and not the headline one, deliberately: this probe contrasts
# HLP-vault flow against ordinary maker flow at the long window the shards carry, and
# swapping it for the 10 s headline would be a different measurement, not a rename.
MARKOUT_COL = H.companion_print_col()
TOP_MAKERS_FOR_DOMINANCE = 20      # "dominant makers" = top-N by notional
# Label-shuffle placebo draws, READ from settings.py and no longer typed. The budget
# fixes the p-value floor at 1/(N+1), and a floor is only worth reporting if it can
# clear the multiplicity correction it will be judged against.
#
# What the literal cost. This file declared 1000. Benjamini-Hochberg compares the
# smallest p in a family against alpha/m, which for the declared family of 48 at the
# 0.05 level is 0.001042. A budget of 1000 has a floor of 0.000999, so it cleared that
# bar by four percent: every p sitting on the floor had its verdict decided by the last
# digit of the correction rather than by the evidence. settings.PERM_FLOOR_MARGIN is
# declared as 2 precisely to forbid that position, and settings.min_perm_draws returns
# 1919 as the smallest budget that satisfies it -- so 1000 was below the declared
# minimum, not merely below the declared value. At settings.N_PERM the floor is 0.0005
# and clears the bar by the declared factor of two.
#
# The same budget now feeds the second-part liquidation control at the bottom of the
# file, which used to draw 200. That one could not clear the rank-one bar AT ANY EFFECT
# SIZE: its floor was 0.00498, nearly five times the bar.
N_PERM = H.N_PERM                  # label-shuffle placebo permutations
WHALE_K = 5                        # drop top-5 (HARD CONSTRAINT 5)
EB_KMIN = 30                       # min fills to score a maker in EB
EB_EARLY_MAX_DAY = 8               # early = day <= 8, late = day >= 9
NO_MAKER = -1


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def _low(x):
    """Lowercase a wallet string; '' for None/missing."""
    if x is None:
        return ""
    if isinstance(x, bytes):
        return x.decode("utf-8", "ignore").lower()
    return str(x).lower()


def _wmean(x, w):
    w = np.asarray(w, dtype=np.float64)
    x = np.asarray(x, dtype=np.float64)
    sw = w.sum()
    return float(np.sum(w * x) / sw) if sw > 0 else float("nan")


def _describe(v):
    v = np.asarray(v, dtype=np.float64)
    v = v[np.isfinite(v)]
    if v.size == 0:
        return {"n": 0, "mean": float("nan"), "p50": float("nan")}
    return {"n": int(v.size), "mean": float(v.mean()),
            "p50": float(np.percentile(v, 50)),
            "frac_positive": float(np.mean(v > 0))}


# ---------------------------------------------------------------------------
# PART 1 — load the panel shards (address-resolved HLP)
# ---------------------------------------------------------------------------
def load_panel_shards():
    """Concatenate per-coin checkpoint shards keeping maker_addr/taker_addr,
    coin, day, period, mo60, notional. Returns a dict of aligned arrays plus an
    is_hlp boolean (resolved by RAW ADDRESS, the only trustworthy identifier).

    Why shards (not panel_markouts.npz): the shards retain the raw wallet
    strings, so HLP is identified by address; the merged npz only has the
    re-coded integer maker_id whose code space does not match maker_map.json.
    """
    files = sorted(glob.glob(SHARD_GLOB))
    if not files:
        raise FileNotFoundError(
            f"no panel shards at {SHARD_GLOB}. Build them with "
            "panel_build.py / panel_persistence.py --build first.")

    coin_l, day_l, period_l, mo60_l, notl_l = [], [], [], [], []
    maker_addr_l, taker_addr_l = [], []
    for f in files:
        z = np.load(f, allow_pickle=True)
        n = z[MARKOUT_COL].shape[0]
        coin_l.append(z["coin"].astype(np.int8))
        day_l.append(z["day"].astype(np.int64))
        period_l.append(z["period"].astype(np.int64))
        mo60_l.append(z[MARKOUT_COL].astype(np.float64))
        notl_l.append(z["notional"].astype(np.float64))
        maker_addr_l.append(np.array([_low(x) for x in z["maker_addr"]], dtype=object))
        taker_addr_l.append(np.array([_low(x) for x in z["taker_addr"]], dtype=object))
        assert (z["coin"].shape[0] == n and z["day"].shape[0] == n
                and z["maker_addr"].shape[0] == n), f"shard {f} arrays misaligned"

    maker_addr = np.concatenate(maker_addr_l)
    taker_addr = np.concatenate(taker_addr_l)
    out = {
        "coin": np.concatenate(coin_l),
        "day": np.concatenate(day_l),
        "period": np.concatenate(period_l),
        MARKOUT_COL: np.concatenate(mo60_l),
        "notional": np.concatenate(notl_l),
        "maker_addr": maker_addr,
        "taker_addr": taker_addr,
    }
    # HLP membership by ADDRESS (the trustworthy route)
    out["is_hlp"] = np.array([a in HLP_SET for a in maker_addr], dtype=bool)
    # drop rows with no maker leg (empty address) up front
    has_maker = maker_addr != ""
    for k in list(out.keys()):
        out[k] = out[k][has_maker]
    out["n_no_maker"] = int((~has_maker).sum())
    out["n_files"] = len(files)
    return out


def maker_map_crosscheck():
    """DOCUMENTED-ONLY: confirm maker_map.json maps 168->HLP-A, 12->HLP-B (the
    quickwin space) AND that the PANEL npz integer codes do NOT match HLP by
    row-count. Never used to identify HLP -- only to record the data-space gap.
    """
    note = {"maker_map_path": os.path.basename(MAKER_MAP_PATH)}
    if os.path.exists(MAKER_MAP_PATH):
        with open(MAKER_MAP_PATH) as fh:
            m = json.load(fh).get("map", {})
        rev = {int(v): k for k, v in m.items()}
        note["quickwin_code168_addr"] = rev.get(168)
        note["quickwin_code12_addr"] = rev.get(12)
        note["quickwin_168_is_hlp_A"] = (rev.get(168, "").lower() == HLP_A)
        note["quickwin_12_is_hlp_B"] = (rev.get(12, "").lower() == HLP_B)
    if os.path.exists(PANEL_NPZ):
        d = np.load(PANEL_NPZ)
        mid = d["maker_id"]
        note["panel_code168_rows"] = int((mid == 168).sum())
        note["panel_code12_rows"] = int((mid == 12).sum())
        note["WARNING"] = (
            "panel maker_id is a separate global re-code; code 168/12 are NOT "
            "HLP in the panel space. HLP resolved by ADDRESS from the shards.")
    return note


# ---------------------------------------------------------------------------
# PART 1 — HLP vs rest contrast in one slice
# ---------------------------------------------------------------------------
def hlp_vs_rest(mo60, notional, is_hlp, maker_addr, rng, slice_name="unnamed"):
    """HLP-set vs non-HLP maker mo60 contrast for one slice, with a
    label-shuffle placebo and a top-5 non-HLP whale-drop.

    slice_name only NAMES the cell in the recorded procedure block; it seeds nothing,
    because the draws come from the generator the caller opens.
    """
    fin = np.isfinite(mo60) & np.isfinite(notional) & (notional >= 0)
    mo = mo60[fin]
    notl = notional[fin]
    hlp = is_hlp[fin]
    addr = maker_addr[fin]
    n = mo.size
    if n == 0 or hlp.sum() == 0:
        return {"n": int(n), "n_hlp_fills": int(hlp.sum()),
                "note": "no HLP fills in this slice"}

    hlp_eq = float(mo[hlp].mean())
    rest_eq = float(mo[~hlp].mean())
    hlp_nw = _wmean(mo[hlp], notl[hlp])
    rest_nw = _wmean(mo[~hlp], notl[~hlp])
    gap_eq = hlp_eq - rest_eq                       # +ve => HLP more adverse-selected
    gap_nw = hlp_nw - rest_nw

    # HLP share of all maker fills + of dominant-maker fills (top-N by notional)
    uadr, inv = np.unique(addr, return_inverse=True)
    notl_by_maker = np.zeros(uadr.size)
    np.add.at(notl_by_maker, inv, notl)
    dom_order = np.argsort(notl_by_maker)[::-1][:TOP_MAKERS_FOR_DOMINANCE]
    dom_addr = set(uadr[dom_order].tolist())
    is_dom = np.array([a in dom_addr for a in addr])
    hlp_share_all = float(hlp.mean())
    hlp_share_dom = (float(hlp[is_dom].mean()) if is_dom.any() else float("nan"))
    hlp_in_dom = bool(any(a in dom_addr for a in HLP_SET))

    # ---- label-shuffle placebo: shuffle which makers are "HLP" (same count) ---
    k_hlp = int(hlp.sum())
    null_gaps = np.empty(N_PERM)
    for i in range(N_PERM):
        pick = rng.choice(n, size=k_hlp, replace=False)
        mask = np.zeros(n, dtype=bool)
        mask[pick] = True
        null_gaps[i] = mo[mask].mean() - mo[~mask].mean()
    # Two-sided p for |gap| under the random-label null, counted by stats.py rather
    # than here. The counting rule is unchanged and is stated so it can be checked:
    # the observed labelling is itself one of the arrangements the null describes, so
    # it counts in both numerator and denominator, and without that +1 a permutation p
    # reads as exactly 0, which no permutation test can produce. What the module owns
    # is the count, the floor and the record; the draws above stay here, because WHAT
    # is permuted is the substance of this test.
    #
    # TWO ARGUMENTS ARE PASSED SO THE ARITHMETIC IS THE ARITHMETIC THIS FILE ALREADY
    # RAN, not the module's default. abs_tol=0.0 keeps the bare `>=` this line has
    # always used -- the module's relative slack would count a draw an ulp below the
    # observed gap, which is the better rule and a DIFFERENT number, owed its own
    # recompute. n_requested=N_PERM is the budget asked for; every draw here is finite
    # by construction, so n_draws_dropped in the block below reads 0 and the module's
    # usable-count denominator is the N_PERM this file divided by. That field is the
    # check, not a comment: if a draw ever fails, the block says so instead of the p
    # quietly claiming a resolution the run did not have.
    perm = stats.permutation_p(gap_eq, null_gaps, side="two_sided", abs_tol=0.0,
                               n_requested=N_PERM,
                               cell=("hlp_vs_rest_gap_eq", slice_name))
    p_placebo = perm["p"]

    # ---- whale-drop: drop the top-5 NON-HLP makers by notional; re-contrast ----
    # uadr and notl_by_maker are already aligned (uadr = unique addrs, notl_by_maker
    # indexed by uadr position), so rank non-HLP makers vectorised — NOT an O(U^2)
    # per-maker np.where scan (U ~ 64k makers pooled would be ~4e9 comparisons).
    uadr_is_hlp = np.array([a in HLP_SET for a in uadr], dtype=bool)
    nh_notl_arr = notl_by_maker.copy()
    nh_notl_arr[uadr_is_hlp] = -np.inf            # never drop an HLP vault
    drop_pos = np.argsort(nh_notl_arr)[::-1][:WHALE_K]
    drop = set(uadr[drop_pos].tolist())
    keep = np.array([a not in drop for a in addr])
    wd_gap_eq = float("nan")
    if keep.any() and hlp[keep].any() and (~hlp[keep]).any():
        wd_gap_eq = float(mo[keep & hlp].mean() - mo[keep & ~hlp].mean())

    kill = "PASS"
    # `p_placebo is not None` is a guard and not a change of rule: the module returns
    # None where a cell has no usable draw or a non-finite observed gap, which is the
    # honest answer for a cell that was never tested. The line this file ran before
    # could not produce that case, and where it cannot the two readings agree.
    if not (gap_eq > 0 and p_placebo is not None and p_placebo < 0.05):
        kill = "NULL: HLP not reliably more adverse-selected than rest"
    elif np.isfinite(wd_gap_eq) and wd_gap_eq <= 0:
        kill = "FRAGILE: HLP>rest sign flips after non-HLP whale-drop"

    return {
        "n": int(n),
        "n_hlp_fills": k_hlp,
        "hlp_mean_mo60_eq": hlp_eq,
        "rest_mean_mo60_eq": rest_eq,
        "hlp_mean_mo60_nw": hlp_nw,
        "rest_mean_mo60_nw": rest_nw,
        "gap_eq_bps": gap_eq,
        "gap_nw_bps": gap_nw,
        "hlp_share_of_all_maker_fills": hlp_share_all,
        "hlp_share_of_dominant_maker_fills": hlp_share_dom,
        "hlp_in_top20_makers_by_notional": hlp_in_dom,
        "placebo_label_shuffle_p": p_placebo,
        # The procedure beside its result. A p with no draw count, no side and no floor
        # next to it cannot be read: 0.0005 from 2000 draws and 0.0005 from 2000 draws
        # of which 1600 failed are the same digits and different evidence.
        "placebo_permutation": perm,
        "placebo_null_gap_mean": float(null_gaps.mean()),
        "placebo_null_gap_sd": float(null_gaps.std()),
        "whale_drop_top5_nonhlp_gap_eq_bps": wd_gap_eq,
        "kill_criterion": kill,
    }


# ---------------------------------------------------------------------------
# PART 1 — maker-side variance share, HLP collapsed vs full (reuse kss solver)
# ---------------------------------------------------------------------------
def _solve_twoway(y, t, m, g, nT, nM, nG, max_iter=500, tol=1e-5):
    """Alternating-projection two-way FE (copied convention from kss_decomp_c.py).
    t,m,g contiguous 0-based codes; alpha/psi recentred each step."""
    ct = np.maximum(np.bincount(t, minlength=nT), 1).astype(np.float64)
    cm = np.maximum(np.bincount(m, minlength=nM), 1).astype(np.float64)
    cg = np.maximum(np.bincount(g, minlength=nG), 1).astype(np.float64)
    a = np.zeros(nT); p = np.zeros(nM); mu = np.zeros(nG)
    for it in range(max_iter):
        a2 = np.bincount(t, weights=y - p[m] - mu[g], minlength=nT) / ct
        p2 = np.bincount(m, weights=y - a2[t] - mu[g], minlength=nM) / cm
        mu2 = np.bincount(g, weights=y - a2[t] - p2[m], minlength=nG) / cg
        am, pm = a2.mean(), p2.mean()
        a2 -= am; p2 -= pm; mu2 += am + pm
        delta = max(np.abs(a2 - a).max(), np.abs(p2 - p).max(), np.abs(mu2 - mu).max())
        a, p, mu = a2, p2, mu2
        if delta < tol:
            break
    return a, p, mu


def maker_variance_hlp_contrast(mo60, notional, maker_addr, taker_addr,
                                coin, day, is_hlp):
    """Two-way (taker x maker) FE plug-in variance shares, then the SHARE of the
    maker-effect variance attributable to the HLP sub-vaults vs the rest. Uses a
    coin x day common term. Plug-in only here (the split-half de-bias lives in
    kss_decomp_c.py for the headline taker object; this is a maker-side
    contrast, so a plug-in psi decomposition with an explicit HLP-vs-rest split
    is the right, cheap read)."""
    fin = np.isfinite(mo60) & np.isfinite(notional)
    y = mo60[fin]
    t = np.unique(taker_addr[fin], return_inverse=True)[1]
    m = np.unique(maker_addr[fin], return_inverse=True)[1]
    gkey = coin[fin].astype(np.int64) * 100 + day[fin].astype(np.int64)
    g = np.unique(gkey, return_inverse=True)[1]
    hlp = is_hlp[fin]
    nT, nM, nG = t.max() + 1, m.max() + 1, g.max() + 1
    a, p, mu = _solve_twoway(y, t, m, g, nT, nM, nG)
    psi = p[m]                                       # per-fill maker effect
    vy = float(np.var(y))
    var_psi = float(np.var(psi))
    # HLP-attributable maker variance: variance carried by HLP-maker fills'
    # psi (centred on the overall psi mean), vs the rest.
    psi_c = psi - psi.mean()
    frac_hlp_fills = float(hlp.mean())
    contrib_hlp = float(np.mean((psi_c[hlp]) ** 2)) if hlp.any() else float("nan")
    contrib_rest = float(np.mean((psi_c[~hlp]) ** 2)) if (~hlp).any() else float("nan")
    # mean maker effect for HLP vs rest (signed bps): +ve => structurally picked off
    mean_psi_hlp = float(psi[hlp].mean()) if hlp.any() else float("nan")
    mean_psi_rest = float(psi[~hlp].mean()) if (~hlp).any() else float("nan")
    return {
        "n_fills": int(y.size), "n_takers": int(nT), "n_makers": int(nM),
        "var_y": vy,
        "share_maker_psi": float(var_psi / vy) if vy > 0 else float("nan"),
        "share_taker_alpha": float(np.var(a[t]) / vy) if vy > 0 else float("nan"),
        "frac_fills_hlp": frac_hlp_fills,
        "mean_maker_effect_hlp_bps": mean_psi_hlp,
        "mean_maker_effect_rest_bps": mean_psi_rest,
        "psi_msq_hlp": contrib_hlp,
        "psi_msq_rest": contrib_rest,
        "psi_msq_ratio_hlp_over_rest": (contrib_hlp / contrib_rest
                                        if (np.isfinite(contrib_rest)
                                            and contrib_rest > 0) else float("nan")),
        "note": ("plug-in psi decomposition with HLP-vs-rest split; +ve "
                 "mean_maker_effect => that set is structurally adverse-selected"),
    }


# ---------------------------------------------------------------------------
# PART 1 — Empirical-Bayes contrast: HLP shrunk score vs non-HLP prior
# ---------------------------------------------------------------------------
def eb_hlp_contrast(mo60, notional, maker_addr, day, is_hlp):
    """Shrink each maker's mo60 toward the non-HLP prior (eb_scoring.py recipe),
    OOS early->late, and report where the two HLP vaults land vs the prior."""
    fin = np.isfinite(mo60)
    y = mo60[fin]; addr = maker_addr[fin]; dd = day[fin]; hlp = is_hlp[fin]
    ids = np.unique(addr, return_inverse=True)[1]
    nE = ids.max() + 1
    early = dd <= EB_EARLY_MAX_DAY
    late = ~early

    def agg(mask):
        i = ids[mask]; v = y[mask]
        cnt = np.bincount(i, minlength=nE).astype(np.float64)
        s = np.bincount(i, weights=v, minlength=nE)
        s2 = np.bincount(i, weights=v * v, minlength=nE)
        mean = np.where(cnt > 0, s / np.maximum(cnt, 1), np.nan)
        var = np.where(cnt > 1, s2 / np.maximum(cnt, 1) - mean ** 2, np.nan)
        return cnt, mean, np.maximum(var, 0.0)

    cE, mE, vE = agg(early)
    cL, mL, _ = agg(late)
    keep = (cE >= EB_KMIN) & (cL >= EB_KMIN)
    if int(keep.sum()) < 20:
        return {"note": "too few makers with KMIN fills in both halves"}
    # which kept makers are HLP (by address)
    uadr = np.unique(addr)
    hlp_id = {int(np.where(uadr == a)[0][0]) for a in HLP_SET if a in set(uadr.tolist())}

    cEk, mEk, vEk = cE[keep], mE[keep], vE[keep]
    keep_idx = np.where(keep)[0]
    is_hlp_kept = np.array([k in hlp_id for k in keep_idx])
    # prior from NON-HLP makers only
    nh = ~is_hlp_kept
    grand = _wmean(mEk[nh], cEk[nh]) if nh.any() else _wmean(mEk, cEk)
    s2 = vEk / np.maximum(cEk, 1)
    between = float(np.sum(cEk[nh] * (mEk[nh] - grand) ** 2) / np.sum(cEk[nh])) if nh.any() else 0.0
    mean_samp = _wmean(s2[nh], cEk[nh]) if nh.any() else _wmean(s2, cEk)
    tau2 = max(between - mean_samp, 0.0)
    B = tau2 / (tau2 + s2)
    shrunk = grand + B * (mEk - grand)
    return {
        "n_scored": int(keep.sum()),
        "nonhlp_prior_bps": grand,
        "tau2": tau2,
        "hlp_makers_scored": int(is_hlp_kept.sum()),
        "hlp_shrunk_scores_bps": [float(x) for x in shrunk[is_hlp_kept]],
        "hlp_raw_early_bps": [float(x) for x in mEk[is_hlp_kept]],
        "hlp_above_prior": [bool(x > grand) for x in shrunk[is_hlp_kept]],
        "note": ("HLP shrunk score above the non-HLP prior => HLP flow is "
                 "more adverse-selected than ordinary maker flow (OOS-shrunk)"),
    }


# ---------------------------------------------------------------------------
# PART 1 driver
# ---------------------------------------------------------------------------
def run_part1():
    rng = np.random.default_rng(SEED)
    D = load_panel_shards()
    coin = D["coin"]; day = D["day"]; mo60 = D[MARKOUT_COL]; notl = D["notional"]
    maker_addr = D["maker_addr"]; taker_addr = D["taker_addr"]; is_hlp = D["is_hlp"]

    res = {
        "_meta": {
            "part": "PART 1 — HLP-vault-as-counterparty",
            "source": "panel_ckpt/shard_*.npz (address-resolved HLP)",
            "n_files": D["n_files"],
            "n_rows_with_maker": int(mo60.size),
            "n_rows_no_maker_dropped": D["n_no_maker"],
            "n_hlp_maker_rows_total": int(is_hlp.sum()),
            "hlp_share_total": float(is_hlp.mean()),
            "reference": "trade-print mo60 (execution-cost lens, includes spread); "
                         "HLP-vs-rest read as a RANKING/contrast, not a level",
            "sign": "mo60>0 = taker profited = maker adverse-selected",
            "hlp_addresses": sorted(HLP_SET),
            "seed": SEED, "n_perm": N_PERM, "whale_k": WHALE_K,
            "p_floor": 1.0 / (N_PERM + 1),
            "p_convention": "placebo p = (#{|null gap| >= |observed gap|} + 1) / "
                            "(n_perm + 1); a value AT the floor means 'no permutation "
                            "reached the observed gap', not p = 0",
        },
        "maker_map_crosscheck": maker_map_crosscheck(),
    }

    # per-coin + pooled HLP-vs-rest
    for c in sorted(np.unique(coin).tolist()):
        sel = coin == c
        res[COIN_NAME.get(c, str(c))] = hlp_vs_rest(
            mo60[sel], notl[sel], is_hlp[sel], maker_addr[sel],
            np.random.default_rng(SEED + 10 + c),
            slice_name=COIN_NAME.get(c, str(c)))
    res["pooled"] = hlp_vs_rest(mo60, notl, is_hlp, maker_addr,
                                np.random.default_rng(SEED + 99),
                                slice_name="pooled")

    # maker-side variance share, HLP contrast (pooled + per-coin)
    res["maker_variance_contrast"] = {}
    for c in sorted(np.unique(coin).tolist()):
        sel = coin == c
        res["maker_variance_contrast"][COIN_NAME.get(c, str(c))] = \
            maker_variance_hlp_contrast(mo60[sel], notl[sel], maker_addr[sel],
                                        taker_addr[sel], coin[sel], day[sel],
                                        is_hlp[sel])
    res["maker_variance_contrast"]["pooled"] = maker_variance_hlp_contrast(
        mo60, notl, maker_addr, taker_addr, coin, day, is_hlp)

    # EB contrast (pooled + per-coin)
    res["eb_contrast"] = {}
    for c in sorted(np.unique(coin).tolist()):
        sel = coin == c
        res["eb_contrast"][COIN_NAME.get(c, str(c))] = eb_hlp_contrast(
            mo60[sel], notl[sel], maker_addr[sel], day[sel], is_hlp[sel])
    res["eb_contrast"]["pooled"] = eb_hlp_contrast(
        mo60, notl, maker_addr, day, is_hlp)
    return res


# ---------------------------------------------------------------------------
# PART 2 — liquidation control (GATED) + optional Zenodo interim
# ---------------------------------------------------------------------------
def run_part2_liquidation_column():
    """If the npz carries an is_liq/liquidation column (post re-pull), compare
    mo60 markout of liquidation-driven vs normal flow; else GATE cleanly."""
    # WHICH PANEL THIS READS IS DECLARED, NOT DISCOVERED. This line used to be
    # `PANEL_NPZ_V2 if os.path.exists(PANEL_NPZ_V2) else PANEL_NPZ`, which let the
    # state of the filesystem choose the input. The two panels are not
    # interchangeable: they differ by 14,020 rows, one hour of trading on
    # 2025-11-10 that the v2 pull did not retrieve, and only v2 carries the
    # liquidation column this block is about. So the same script on the same machine
    # returned a different population before and after a file was deleted, and the
    # result did not say which it had read. The v2 panel is REQUIRED here, because
    # without its column there is nothing to measure; if it is absent the block
    # gates, and the artifact records the file by basename either way.
    path = PANEL_NPZ_V2
    if not os.path.exists(path):
        return {"status": "GATED",
                "message": "GATED: needs block_time+liquidation re-pull",
                "reason": f"{os.path.basename(path)} not found",
                "panel_read": None,
                "panel_required": os.path.basename(PANEL_NPZ_V2)}
    d = np.load(path)
    liq_key = None
    for cand in ("is_liq", "liquidation", "is_liquidation", "liq"):
        if cand in d.files:
            liq_key = cand
            break
    if liq_key is None:
        return {
            "status": "GATED",
            "message": "GATED: needs block_time+liquidation re-pull",
            "reason": ("no liquidation column in the npz; the `liquidation` "
                       "object was dropped at persist. Re-pull node_fills_by_block "
                       "keeping block_time + the nested liquidation marker, then "
                       "re-run this section."),
            "npz_keys": list(d.files), "source": os.path.basename(path),
        }
    # ungated path
    is_liq = d[liq_key].astype(bool)
    mo60 = d[MARKOUT_COL].astype(np.float64)
    coin = d["coin"].astype(np.int64)
    period = d["period"].astype(np.int64) if "period" in d.files else np.zeros_like(coin)
    day = d["day"].astype(np.int64) if "day" in d.files else np.zeros_like(coin)
    fin = np.isfinite(mo60)
    mo60, is_liq, coin, period, day = mo60[fin], is_liq[fin], coin[fin], period[fin], day[fin]

    # coin x period x day demeaning: liquidations cluster on volatile days where ALL
    # markout is mechanically larger, so the RAW liq-vs-normal gap is confounded by
    # timing. The within-cell (demeaned) gap removes that -> the clean control.
    cell = coin.astype(np.int64) * 1_000_000 + period * 100 + day
    _, inv = np.unique(cell, return_inverse=True)
    cell_mean = np.bincount(inv, weights=mo60) / np.maximum(np.bincount(inv), 1)
    mo60_dm = mo60 - cell_mean[inv]

    def _gap(mask_liq, y):
        a = y[mask_liq]; b = y[~mask_liq]
        return (float(a.mean()) - float(b.mean())) if (a.size and b.size) else None

    # The same value the module binds above, asked for by name rather than typed a
    # second time. 690 was written here inline, so the file held one value in two
    # places; SEED is seed_for("probe_F_hlp_liq") and returns 690, so this generator
    # opens on the identical integer and the control's draws do not move.
    rng = np.random.default_rng(SEED)
    out = {"status": "ok", "source": os.path.basename(path), "liq_column": liq_key,
           "n_liq": int(is_liq.sum()), "n_total": int(fin.sum()),
           # The draw count is interpolated, never typed. It used to read "(200)" as
           # prose beside a loop that drew 200, and prose beside a number is how a
           # caption goes stale the moment the number moves -- which is exactly what
           # has just happened to it.
           "control": (f"raw + coin x period x day demeaned; label-shuffle placebo "
                       f"({N_PERM})"),
           # Recorded under a key a census can actually see. The count used to live
           # only inside the sentence above, so a sweep for n_perm over the artifacts
           # reported this block as carrying no budget at all.
           "n_perm": N_PERM,
           "p_floor": 1.0 / (N_PERM + 1),
           "per_coin": {}}
    for c in sorted(np.unique(coin).tolist()):
        sel = coin == c
        ll = is_liq[sel]
        raw = _gap(ll, mo60[sel])
        dm = _gap(ll, mo60_dm[sel])
        ydm = mo60_dm[sel]
        null = np.asarray([g for g in (_gap(rng.permutation(ll), ydm)
                                       for _ in range(N_PERM))
                           if g is not None])
        # Counted by stats.py, with THIS block's own two conventions preserved rather
        # than replaced. abs_tol=0.0 keeps the bare `>=`. The denominator is the count
        # of draws that came back, which is what the comprehension above already
        # produces by dropping a degenerate permutation instead of scoring it: passing
        # n_requested=N_PERM lets the module report the two counts separately, so the
        # artifact records how many draws were dropped instead of hiding the gap inside
        # a smaller denominator. The other permutation in this file divides by the
        # budget, and those are two different denominators on purpose.
        perm = (stats.permutation_p(dm, null, side="two_sided", abs_tol=0.0,
                                    n_requested=N_PERM,
                                    cell=("liq_demeaned_gap", COIN_NAME.get(c, str(c))))
                if (dm is not None and null.size) else None)
        p = perm["p"] if perm is not None else None
        out["per_coin"][COIN_NAME.get(c, str(c))] = {
            "raw_gap_bps": raw, "demeaned_gap_bps": dm, "placebo_p": p,
            "placebo_permutation": perm,
            "n_liq": int(ll.sum()),
            "liq_mean_mo60": (float(mo60[sel][ll].mean()) if ll.any() else None),
            "normal_mean_mo60": (float(mo60[sel][~ll].mean()) if (~ll).any() else None),
        }
    out["pooled"] = {"raw_gap_bps": _gap(is_liq, mo60),
                     "demeaned_gap_bps": _gap(is_liq, mo60_dm)}
    out["interpretation"] = (
        "Clean control = the coin x period x day DEMEANED gap (removes the confound "
        "that liquidations cluster on volatile days where all markout is larger). "
        "Demeaned gap near zero / negative => forced liquidations are NOT "
        "informationally toxic = a clean negative control for the toxicity construct. "
        "A large positive demeaned gap would instead mean liquidation flow is itself "
        "toxic (not a clean control).")
    return out


def run_zenodo_interim():
    """Extract ONE small Zenodo tar member (one hour) and split BTC trades by
    trade_dir_override == 'LiquidatedMarket' vs 'Na'. Coarse markout proxy = the
    sign of the next-print return after a buy-aggressor (no book mid, one hour).
    Sanity peek only; clearly labelled."""
    if not os.path.exists(ZENODO_TAR):
        return {"status": "skipped",
                "reason": f"{os.path.basename(ZENODO_TAR)} not found"}
    member = "20251204/23.gz"      # one calm hour, BTC present, symbols not aliased
    rows = []
    try:
        with tarfile.open(ZENODO_TAR, "r") as tf:
            try:
                fh = tf.extractfile(member)
            except KeyError:
                return {"status": "skipped", "reason": f"member {member} absent"}
            if fh is None:
                return {"status": "skipped", "reason": "member not a file"}
            raw = gzip.decompress(fh.read()).decode("utf-8", "ignore")
        for line in raw.splitlines():
            if '"BTC"' not in line:
                continue
            o = json.loads(line)
            if o.get("coin") != "BTC":
                continue
            rows.append((o.get("time"), o.get("side"), float(o.get("px")),
                         o.get("trade_dir_override", "Na")))
    except Exception as e:                                   # noqa: BLE001
        return {"status": "error", "reason": repr(e)}
    if not rows:
        return {"status": "empty", "member": member}
    rows.sort(key=lambda r: r[0])
    px = np.array([r[2] for r in rows], dtype=np.float64)
    side = np.array([1 if r[1] == "B" else -1 for r in rows])     # taker dir
    ovr = np.array([r[3] for r in rows], dtype=object)
    # coarse markout proxy: signed next-print return (bps), + = taker profited
    fwd = np.full(px.size, np.nan)
    fwd[:-1] = (px[1:] - px[:-1]) / px[:-1] * 1e4
    mk = side * fwd
    is_liq = ovr == "LiquidatedMarket"
    fin = np.isfinite(mk)
    return {
        "status": "ok (interim sanity peek, one hour, no book mid)",
        "member": member, "n_btc_trades": int(px.size),
        "n_liquidated_market": int(is_liq.sum()),
        "liq_mean_signed_nextprint_bps": (float(mk[fin & is_liq].mean())
                                          if (fin & is_liq).any() else None),
        "normal_mean_signed_nextprint_bps": (float(mk[fin & ~is_liq].mean())
                                             if (fin & ~is_liq).any() else None),
        "caveat": ("proxy = signed NEXT-PRINT return, not a horizon markout vs "
                   "book mid; one hour only; for direction-of-effect sanity, not "
                   "a result. trade_dir_override has no per-leg detail."),
    }


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Probe F — HLP + liquidation control")
    ap.add_argument("--part", choices=["1", "2", "both"], default="both",
                    help="run PART 1 (HLP, heavy), PART 2 (liq control, gated), or both")
    ap.add_argument("--zenodo-interim", action="store_true",
                    help="run the optional one-hour Zenodo trade_dir_override peek")
    args = ap.parse_args()

    t0 = artifact.start_clock()
    results = {}
    if args.part in ("1", "both"):
        print("=" * 80)
        print("PROBE F PART 1 — HLP-vault-as-counterparty (heavy, panel shards)")
        print("=" * 80)
        results["part1_hlp"] = run_part1()
        m = results["part1_hlp"]["_meta"]
        print(f"rows w/ maker: {m['n_rows_with_maker']:,}  HLP rows: "
              f"{m['n_hlp_maker_rows_total']:,} ({m['hlp_share_total']*100:.2f}%)")
        for key in ("BTC", "ETH", "SOL", "pooled"):
            r = results["part1_hlp"].get(key, {})
            if "gap_eq_bps" in r:
                print(f"  {key:6s} HLP={r['hlp_mean_mo60_eq']:+.3f} "
                      f"rest={r['rest_mean_mo60_eq']:+.3f} "
                      f"gap={r['gap_eq_bps']:+.3f} bps  p_placebo={r['placebo_label_shuffle_p']:.4f} "
                      f"wd_gap={r['whale_drop_top5_nonhlp_gap_eq_bps']:+.3f}  "
                      f"hlp_share_dom={r['hlp_share_of_dominant_maker_fills']}  "
                      f"[{r['kill_criterion']}]")
            elif "note" in r:
                print(f"  {key:6s} {r['note']}")

    if args.part in ("2", "both"):
        print("=" * 80)
        print("PROBE F PART 2 — liquidation negative control (gated)")
        print("=" * 80)
        results["part2_liquidation"] = run_part2_liquidation_column()
        print(f"  liquidation-column status: {results['part2_liquidation']['status']}")
        if results["part2_liquidation"]["status"] != "ok":
            print(f"  {results['part2_liquidation']['message']}")
        if args.zenodo_interim:
            print("  running optional Zenodo one-hour interim peek...")
            results["part2_zenodo_interim"] = run_zenodo_interim()
            print(f"  zenodo interim status: {results['part2_zenodo_interim']['status']}")

    # THE SCOPE IS BUILT FROM WHAT THIS INVOCATION ACTUALLY RAN, not from what the file
    # is capable of running. Three populations can land in one results file here and
    # they are nothing like each other in size: PART 1 reads every panel shard, PART 2
    # reads the whole v2 panel or gates without reading anything, and the optional
    # Zenodo peek reads ONE HOUR. This project has already published a verdict taken
    # from a check that had run over a single hour, so which of the three is present is
    # written out rather than left to a reader who sees three blocks and one file name.
    parts, populations = [], []
    p1 = results.get("part1_hlp")
    if p1 is not None:
        m1 = p1["_meta"]
        parts.append("part1_hlp")
        populations.append(
            f"PART 1 on {m1['n_rows_with_maker']:,} shard rows carrying a maker, of "
            f"which {m1['n_hlp_maker_rows_total']:,} are HLP-vault fills "
            f"({m1['hlp_share_total'] * 100:.2f}%), read from {m1['n_files']} panel "
            f"shards with {m1['n_rows_no_maker_dropped']:,} maker-less rows dropped")
    p2 = results.get("part2_liquidation")
    if p2 is not None:
        parts.append("part2_liquidation")
        populations.append(
            f"PART 2 status {p2['status']}: "
            + (f"{p2['n_liq']:,} liquidation-driven of {p2['n_total']:,} "
               f"finite-markout rows of {p2['source']}"
               if p2["status"] == "ok" else
               f"nothing was measured, {p2.get('reason', 'no reason recorded')}"))
    pz = results.get("part2_zenodo_interim")
    if pz is not None:
        parts.append("part2_zenodo_interim")
        populations.append(
            f"ZENODO INTERIM PEEK status {pz['status']}: ONE HOUR of raw trades, a "
            f"direction-of-effect sanity check on a next-print proxy and NOT a result "
            f"over the array; no verdict about the panel may be read from it")
    artifact.write(
        os.path.basename(OUT_PATH), results,
        script=__file__,
        # The shard glob is EXPANDED here rather than recorded as a pattern. A pattern
        # would be stored as one input named shard_*.npz with present=false, which reads
        # as a missing file; the expansion records each shard with its own size and
        # hash, which is what makes "did the input move" answerable. Twenty-four shards
        # of about 680 MB in total cost well under a second to hash.
        inputs=sorted(glob.glob(SHARD_GLOB))
        + [PANEL_NPZ, PANEL_NPZ_V2, MAKER_MAP_PATH]
        + ([ZENODO_TAR] if pz is not None else []),
        scope={
            "population": ("; ".join(populations)
                           or "n/a: no part was requested, so nothing was computed"),
            "window": (f"blocks present in this run: {parts or 'none'}. PART 1 and "
                       f"PART 2 cover every window their input carries, which the "
                       f"panel's producer declares; the Zenodo peek, when present, "
                       f"covers one hour and only that hour"),
            "coins": ([COIN_NAME[c] for c in sorted(COIN_NAME)] if p1 is not None
                      else "n/a: PART 1 did not run, so no per-coin contrast exists"),
        },
        # The horizon is the one MARKOUT_COL names, taken from the declaration for the
        # reason given beside it, and it returns the 60 that used to be typed here. A
        # fingerprint that states a window the code no longer reads is worse than none.
        settings={"h": H.COMPANION_HORIZON_S, "lens": "print", "master_seed": SEED,
                  "n_perm": N_PERM, "rank_floor_fills": EB_KMIN},
        started=t0, out_dir=os.path.dirname(OUT_PATH))
    print(f"\n[probe F] wrote {os.path.basename(OUT_PATH)}")


if __name__ == "__main__":
    main()
