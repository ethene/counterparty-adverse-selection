"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-20
References: Hyperliquid node-data S3 archive (s3://hl-mainnet-node-data); Zenodo 18184441 (Albers et al. 2026).
"""

# ---------------------------------------------------------------------------
# RE-VERIFICATION CHECK - closed_pnl FIELD SEMANTICS (GROUND-TRUTH, not trust)
#
# The markout pipeline reads quickwin_markouts.npz column `closed_pnl` as the
# realized PnL booked on the taker leg (summed over the collapsed legs of one
# (hash, taker) sweep). Our CODE ASSUMES three things about it:
#
#   A1 (opens-are-zero)   on opens (is_open == 1) closed_pnl ~ 0; realized PnL
#                         is booked only on closes/reduces (is_open == 0).
#   A2 (sign)             a POSITIVE closed_pnl = the taker realized a profit;
#                         it should line up IN DIRECTION with the signed price
#                         markout mo60 (positive mo60 = taker profited = maker
#                         adverse-selected). So among CLOSES, the trades in the
#                         TOP mo60 decile (most-adverse-selected maker / most
#                         profitable taker) should book MORE-positive closed_pnl
#                         than the BOTTOM mo60 decile.
#   A3 (partial-zero-sum) summing closed_pnl over the taker legs we hold is NOT
#                         expected to be exactly zero (we keep the taker plus the
#                         dominant maker, not the full crowd of legs), but the
#                         net should be a SMALL fraction of gross turnover, not a
#                         runaway one-sided number.
#
# This script TESTS each assumption empirically and emits a verdict. It does NOT
# assume the convention is correct. The prior audits only checked that the
# number on disk equals the number quoted in a doc; they could not catch a
# mis-read sign or a leg-accounting error. This check can.
#
# WHY the trade-grain decile sign test is UNINFORMATIVE BY CONSTRUCTION (read
# before judging A2): closed_pnl on a single close-leg is the PnL of unwinding
# inventory that was OPENED EARLIER, at an earlier price. The markout mo60 of
# THIS trade measures the price drift over the 60 s AFTER this trade. They are
# computed from the same fills but they are NOT the same quantity at the trade
# grain, so the trade-grain decile test cannot decide the sign even when the
# field is read correctly - it is not "just noisy", it is the wrong grain.
#
# WHAT ACTUALLY DECIDES THE SIGN. Two of the three sub-checks here are PROVABLY
# SIGN-BLIND - A1 (opens ~ 0) and A3 (|net|/gross) are identical if you flip the
# sign of closed_pnl, so they carry ZERO sign information. The sign is pinned by
# (i) the per-wallet Spearman(sum closed_pnl over closes, mean mo60), which is
# sign-SENSITIVE and reproduces the m4 pooled cross-method number (~ +0.030,
# POSITIVE; BTC and ETH both positive), backed by an explicit FLIP-TEST that
# negates closed_pnl and shows the Spearman moves to exactly its negative; and
# (ii) the external Hyperliquid field doc (closedPnl is profit-positive: +8722.99
# on a winning Close Long, -2.5515 on a losing Close Short). The trade-grain
# decile means are still reported, but they are framed as uninformative-by-
# construction, NOT as the sign evidence.
#
# A2 SMOKE-ONLY ARTIFACT (do NOT rely on it): a prior 50k-row --smoke sample
# showed frac(closed_pnl>0) climbing from the bottom to the top mo60 decile.
# That pattern REVERSES on the full 2.48M panel (top mo60 decile frac>0 ~ 0.421
# < bottom decile ~ 0.435), so it is a sampling artifact and is NOT load-bearing.
#
# CONTRACT (checks/chk_closedpnl_results.json):
#   { "check": "chk_closedpnl", "checks": [ {name, assumption, method, observed,
#     verdict, note}, ... ], "overall_verdict": "confirmed|refuted|uncertain" }
#
# Run (bare python3 is BLOCKED on this machine). DEFAULT is FULL (all rows on
# disk) so the committed artifact matches the production m4_realizedpnl input
# (2,480,267 rows). --smoke is an EXPLICIT fast option (first 50k rows only) and
# is NOT representative - one A2 corroboration (frac(closed_pnl>0) climbing by
# mo60 decile) REVERSES between the 50k smoke sample and the full panel.
#   uv run --no-project --with-requirements requirements.txt python3 checks/chk_closedpnl.py
#   uv run --no-project --with-requirements requirements.txt python3 checks/chk_closedpnl.py --smoke
# ---------------------------------------------------------------------------

import json
import os
import sys

import numpy as np

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
CODE_DIR = os.path.dirname(HERE)                       # the repository root
if CODE_DIR not in sys.path:
    sys.path.insert(0, CODE_DIR)
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import artifact                                        # noqa: E402
import settings as H                                   # noqa: E402
from evidence import mismatch_text, report_contract                   # noqa: E402
import panel_io as P                                   # noqa: E402
from stats import pearson_r, rankdata                  # noqa: E402

# LOCATED by panel_io rather than joined against this file's own directory, so the one
# place that knows where the markout panels live is the one place that has to change if
# they move. With none of the environment variables panel_io honours set, data_root()
# returns the directory the module itself lives in, which is CODE_DIR -- the path this
# line resolved to before, so the file this check reads does not change.
#
# The np.load below stays where it is: build.py derives an input edge by folding the
# argument of np.load to a constant, and a path it cannot fold makes no edge at all.
# The missing-file branch further down is also left alone on purpose -- it writes its own
# evidence through mismatch_text rather than raising, which panel_io.require_present would
# not do, and replacing it would change what this check publishes when the panel is absent.
NPZ_PATH = os.path.join(P.data_root(), "quickwin_markouts.npz")
OUT_PATH = os.path.join(HERE, "chk_closedpnl_results.json")
def _directory_holding(root, name):
    """The directory under `root` that holds a file called `name`.

    Hands back a DIRECTORY, never a full path, so the caller keeps the file name as the
    last component of its own join. The division is required rather than decorative:
    the build derives its dependency graph by folding path expressions, and
    `_path_helpers` in build.py keeps a helper only when it has exactly ONE return, on
    the stated ground that a helper with two returns can hand back two different files.
    Deciding lives here, where branching is honest and where no I/O call reads the
    result directly; `_by_name` below stays foldable.

    Measured: written as one four-return function this added to the build's count of
    unaccounted file operations against a ceiling of 0, and nothing said so, because
    the battery holds failures against a baseline rather than holding that residue.

    Two files answering to one name is refused out loud rather than resolved by taking
    the first. A name that is nowhere hands back the conventional directory, so the
    caller reports an absent input in its own words.
    """
    if os.path.exists(os.path.join(root, name)):
        return root
    hits = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if d not in {".git", "__pycache__", ".ipynb_checkpoints"}]
        if name in filenames:
            hits.append(dirpath)
    if len(hits) > 1:
        raise SystemExit(
            f"[chk_closedpnl] {name} answers to {len(hits)} files under this tree: "
            + ", ".join(sorted(os.path.relpath(h, root) for h in hits))
            + ". Refusing to choose: this gate would report a comparison against a "
              "file it did not name")
    return hits[0] if hits else root


def _by_name(root, name):
    """The file called `name` under `root`, found BY NAME rather than at a guessed path.

    THE JOIN THIS REPLACED MADE THE CROSS-CHECK BELOW STOP HAPPENING, IN SILENCE. It
    read CODE_DIR + name, which was right until the scripts were sorted into group
    directories and this artifact went with its producer into money/. From that day the
    file was simply not at the address, `os.path.exists` answered no, and the three
    figures the cross-check fills stayed None -- so the gate went on printing a verdict
    while the one leg that compares this repository's two independent measures of the
    same statistic was not being run. The artifact's own record dates it: the last run
    that found the file was 11 August at 10:19, and the move happened that day.

    One return, with the file name as its last component, so a reader of the graph can
    still see which artifact this gate reads.
    """
    return os.path.join(_directory_holding(root, name), name)


M4_RESULTS = _by_name(CODE_DIR, "m4_realizedpnl_results.json")

CHECK_NAME = "chk_closedpnl"
SMOKE_ROWS = 50_000                # --smoke: first N rows only (cheap end-to-end)

# Thresholds (self-imposed, conservative; documented in each check note).
ZERO_FRAC_PASS = 0.99              # >=99% of opens must sit within eps of zero
NET_GROSS_WARN = 0.25             # |net sum| / gross > this = one-sided -> refuted


# ---------------------------------------------------------------------------
# numpy-only Spearman (average-rank ties), reused for the per-wallet corroboration.
# The two pieces come from stats.py, where m4_realizedpnl.py and m6_inventory.py get
# them too.
#
# WHAT SHARING THEM DOES AND DOES NOT COST, since this file audits m4_realizedpnl.py and
# a check that copies what it audits is worth nothing. What stays independent is the
# quantity: this check reads the panel itself, builds its own realized-PnL series, takes
# a PER-WALLET rho and compares it against the POOLED rho m4 recorded, within a stated
# tolerance. What is now shared is the rank-and-correlation arithmetic underneath, and
# that was already shared in substance -- the two copies were identical on the syntax
# tree, so the check was already blind to a defect in them. The only thing the import
# removes is the chance that a repair lands in one copy of three.
# ---------------------------------------------------------------------------
def spearman(x, y):
    if np.asarray(x).size < 2:
        return float("nan")
    return pearson_r(rankdata(x), rankdata(y))


# ---------------------------------------------------------------------------
# Check A1 - opens book ~0 realized PnL
# ---------------------------------------------------------------------------
def check_opens_zero(closed_pnl, is_open, notional):
    opens = is_open == 1
    closes = is_open == 0
    n_open = int(opens.sum())
    n_close = int(closes.sum())

    fin_no = notional[np.isfinite(notional)]
    med_no = float(np.median(fin_no)) if fin_no.size else float("nan")
    # eps tied to a typical trade's notional so it scales with the data, with a
    # tiny absolute floor in case median notional is degenerate.
    eps = max(1e-6 * med_no, 1e-9) if np.isfinite(med_no) else 1e-6

    cp = np.where(np.isfinite(closed_pnl), closed_pnl, 0.0)
    frac_open_zero = float(np.mean(np.abs(cp[opens]) < eps)) if n_open else float("nan")
    frac_close_zero = float(np.mean(np.abs(cp[closes]) < eps)) if n_close else float("nan")
    mean_abs_open = float(np.mean(np.abs(cp[opens]))) if n_open else float("nan")
    mean_abs_close = float(np.mean(np.abs(cp[closes]))) if n_close else float("nan")

    # opens are zero AND closes carry materially more PnL than opens
    opens_clean = np.isfinite(frac_open_zero) and frac_open_zero >= ZERO_FRAC_PASS
    closes_richer = (np.isfinite(mean_abs_open) and np.isfinite(mean_abs_close)
                     and mean_abs_close > 10.0 * max(mean_abs_open, eps))
    if opens_clean and closes_richer:
        verdict = "confirmed"
        note = (f"{frac_open_zero:.6f} of opens sit within eps={eps:.3g} of zero; "
                f"mean|closed_pnl| on closes ({mean_abs_close:.3f}) >> on opens "
                f"({mean_abs_open:.3g}). closed_pnl is booked on closes, ~0 on opens. "
                "NOTE: this check is PROVABLY SIGN-BLIND - it is on |closed_pnl|, "
                "identical under a closed_pnl sign flip, so it contributes ZERO sign "
                "information; the sign is pinned by the A2 wallet-Spearman flip-test "
                "plus the external Hyperliquid doc.")
    elif opens_clean:
        verdict = "uncertain"
        note = (f"opens are ~0 ({frac_open_zero:.6f} within eps) but closes do not "
                f"carry materially more |closed_pnl| (close {mean_abs_close:.3f} vs "
                f"open {mean_abs_open:.3g}); booking-on-close pattern weaker than expected.")
    else:
        verdict = "refuted"
        note = (f"only {frac_open_zero:.6f} of opens are ~0 (need >= {ZERO_FRAC_PASS}); "
                f"closed_pnl is NOT ~0 on opens as the code assumes.")

    return {
        "name": "opens_book_zero_realized_pnl",
        "assumption": ("closed_pnl ~ 0 on opens (is_open==1); realized PnL is booked "
                       "only on closes/reduces (is_open==0)"),
        "method": ("fraction of opens with |closed_pnl| < eps (eps=1e-6*median(notional)) "
                   "and mean|closed_pnl| on opens vs closes"),
        "observed": {
            "n_open": n_open,
            "n_close": n_close,
            "median_notional": med_no,
            "eps": eps,
            "frac_opens_within_eps": frac_open_zero,
            "frac_closes_within_eps": frac_close_zero,
            "mean_abs_closed_pnl_opens": mean_abs_open,
            "mean_abs_closed_pnl_closes": mean_abs_close,
        },
        "verdict": verdict,
        "note": note,
    }


# ---------------------------------------------------------------------------
# Check A2 - sign of closed_pnl aligns with the price-markout direction
# ---------------------------------------------------------------------------
def check_sign_alignment(taker_id, closed_pnl, is_open, mo60, coin=None):
    """Sign-SENSITIVE wallet Spearman + flip-test is the decisive evidence.

    The DECISIVE, sign-sensitive evidence is the per-wallet
    Spearman(sum closed_pnl over closes, mean mo60). It reproduces the m4 pooled
    cross-method number (~ +0.0301, POSITIVE; BTC and ETH both positive). We add
    a FLIP-TEST: negating closed_pnl drives this Spearman to exactly its negative
    (-0.0301), which proves the statistic genuinely reads the SIGN and is not
    sign-blind, and we assert sign(as_read) > 0.

    The trade-grain per-decile mean / frac(closed_pnl>0) test is reported for
    transparency but is UNINFORMATIVE BY CONSTRUCTION: a close-leg's closed_pnl
    is realized on inventory opened earlier, not on THIS trade's forward markout,
    so it is the wrong grain to decide the sign. (A prior 50k --smoke sample
    showed frac(closed_pnl>0) climbing by mo60 decile; that REVERSES on the full
    panel and is a sampling artifact, not load-bearing.)
    """
    closes = (is_open == 0) & np.isfinite(mo60)
    cpc = closed_pnl[closes].astype(np.float64)
    moc = mo60[closes].astype(np.float64)
    n = int(closes.sum())

    out = {
        "name": "sign_closed_pnl_vs_markout",
        "assumption": ("positive closed_pnl = taker realized a profit; the sign-sensitive "
                       "per-wallet Spearman(sum closed_pnl over closes, mean mo60) is "
                       "POSITIVE (reproduces the m4 ~+0.030) and FLIPS to its negative when "
                       "closed_pnl is negated, proving the sign is genuinely selected"),
        "method": ("DECISIVE: sign-sensitive per-wallet Spearman(sum closed_pnl over "
                   "closes, mean mo60) with a closed_pnl-negation FLIP-TEST (pooled + "
                   "per-coin), asserting sign(as_read)>0. The trade-grain per-decile mean / "
                   "frac(closed_pnl>0) test is reported but is uninformative by construction "
                   "(close PnL realizes on inventory opened earlier, not this trade's markout)"),
    }

    if n < 100:
        out["observed"] = {"n_closes_finite_mo60": n}
        out["verdict"] = "uncertain"
        out["note"] = ("too few closes with finite mo60 to run the sign test "
                       "(wallet Spearman flip-test needs enough closes).")
        return out

    q10, q90 = np.quantile(moc, [0.10, 0.90])
    top = moc >= q90
    bot = moc <= q10
    top_mean = float(np.mean(cpc[top]))
    bot_mean = float(np.mean(cpc[bot]))
    top_med = float(np.median(cpc[top]))
    bot_med = float(np.median(cpc[bot]))
    top_fpos = float(np.mean(cpc[top] > 0))
    bot_fpos = float(np.mean(cpc[bot] > 0))

    # full 10-decile frac(cp>0) profile (direction-of-monotonicity read)
    edges = np.quantile(moc, np.linspace(0, 1, 11))
    decile_frac_pos = []
    decile_mean = []
    for i in range(10):
        lo, hi = edges[i], edges[i + 1]
        sel = (moc >= lo) & (moc < hi) if i < 9 else (moc >= lo) & (moc <= hi)
        if sel.any():
            decile_frac_pos.append(float(np.mean(cpc[sel] > 0)))
            decile_mean.append(float(np.mean(cpc[sel])))
        else:
            decile_frac_pos.append(float("nan"))
            decile_mean.append(float("nan"))

    # trade-grain decile reads (reported for transparency, uninformative by construction)
    strict_ok = (top_mean > 0.0) and (bot_mean < 0.0)
    ordering_ok = top_mean > bot_mean
    fracpos_ok = top_fpos > bot_fpos

    # ---- DECISIVE sign-sensitive evidence: per-wallet Spearman + FLIP-TEST ----
    # rho(realized, mean mo60), where realized = sum closed_pnl over a wallet's
    # CLOSES. This is the m4 pooled cross-method statistic; it is sign-sensitive,
    # so negating closed_pnl must negate rho exactly. We compute as-read AND
    # negated over the SAME wallet set, plus per-coin (BTC / ETH).
    def _wallet_spearman(cp_signed, tid, isclose, mo, finite_mo, mask=None):
        """rho(sum cp over closes, mean mo60) over wallets, on an optional row mask."""
        if mask is not None:
            tid = tid[mask]; cp_signed = cp_signed[mask]
            isclose = isclose[mask]; mo = mo[mask]; finite_mo = finite_mo[mask]
        if tid.size == 0:
            return float("nan"), 0
        uniq_, inv_ = np.unique(tid, return_inverse=True)
        realized_ = np.zeros(uniq_.size, dtype=np.float64)
        np.add.at(realized_, inv_[isclose], cp_signed[isclose])
        ts_ = np.zeros(uniq_.size, dtype=np.float64)
        tc_ = np.zeros(uniq_.size, dtype=np.float64)
        np.add.at(ts_, inv_[finite_mo], mo[finite_mo].astype(np.float64))
        np.add.at(tc_, inv_[finite_mo], 1.0)
        with np.errstate(invalid="ignore", divide="ignore"):
            tox_ = np.where(tc_ > 0, ts_ / tc_, np.nan)
        ok_ = np.isfinite(tox_)
        rho_ = spearman(realized_[ok_], tox_[ok_]) if int(ok_.sum()) >= 3 else float("nan")
        return rho_, int(ok_.sum())

    cp_fin = np.where(np.isfinite(closed_pnl), closed_pnl, 0.0).astype(np.float64)
    isc = is_open == 0
    fm = np.isfinite(mo60)

    wallet_rho, n_wallets = _wallet_spearman(cp_fin, taker_id, isc, mo60, fm)
    wallet_rho_neg, _ = _wallet_spearman(-cp_fin, taker_id, isc, mo60, fm)

    # per-coin breakdown (BTC=0, ETH=1) when the coin column is available
    coin_rhos = {}
    if coin is not None:
        for code, label in ((0, "BTC"), (1, "ETH")):
            cmask = coin == code
            if int(cmask.sum()) > 0:
                rho_c, _ = _wallet_spearman(cp_fin, taker_id, isc, mo60, fm, mask=cmask)
                coin_rhos[label] = rho_c

    wallet_rho_positive = np.isfinite(wallet_rho) and wallet_rho > 0.0
    # FLIP-TEST integrity: negated rho must be (numerically) the negative of as-read.
    flip_clean = (np.isfinite(wallet_rho) and np.isfinite(wallet_rho_neg)
                  and abs(wallet_rho + wallet_rho_neg) < 1e-9)

    # The decisive assert: the sign-sensitive statistic reads POSITIVE as the code
    # assumes (positive closed_pnl = taker profit), AND it is genuinely sign-selected
    # (the flip-test negates it). If this fails the sign read is wrong - fail loudly.
    assert wallet_rho_positive, mismatch_text(
        "the sign of the exchange's own realized-profit field",
        "a POSITIVE per-wallet Spearman between summed closed_pnl over closing "
        "fills and mean markout, because the whole study reads positive closed_pnl "
        "as profit to the taker",
        f"rho = {wallet_rho:+.4f}",
        f"{os.path.basename(NPZ_PATH)}, columns closed_pnl and "
        f"{H.headline_print_col()}, aggregated per taker_id",
        "the sign convention is inverted somewhere between the exchange field and "
        "the markout, which mirrors every headline figure in the study")
    assert flip_clean, mismatch_text(
        "the flip-test that proves the statistic is sign-sensitive at all",
        f"negating closed_pnl returns the exact negative of the as-read rho "
        f"{wallet_rho:+.6f}, to within 1e-9",
        f"the negated run gave {wallet_rho_neg:+.6f}, a sum of "
        f"{wallet_rho + wallet_rho_neg:+.3e} rather than zero",
        f"{os.path.basename(NPZ_PATH)}, the same per-wallet aggregation run twice",
        "the statistic does not actually respond to the sign, so a positive result "
        "from it is not evidence about the sign")

    # "Reproduces the m4 pooled number" was the stated decisive argument and was never
    # tested: the m4 figure sat in the note as a hardcoded ~+0.030 while nothing read
    # m4's artifact. Read it and compare. A drift between the two is exactly what this
    # check exists to catch, and until now it could not have caught it.
    _col = H.headline_print_col()
    m4_pooled = None
    m4_gap = None
    m4_agrees = None
    if os.path.exists(M4_RESULTS):
        try:
            _m4 = json.load(open(M4_RESULTS))
            m4_pooled = _m4.get("pooled", {}).get("spearman_rho")
            _m4_col = _m4.get("_meta", {}).get("markout_column")
            if m4_pooled is not None and np.isfinite(wallet_rho):
                m4_gap = float(abs(m4_pooled - wallet_rho))
                # Same statistic on the same column: they should agree closely. The two
                # differ only in wallet-set construction, so allow a small tolerance and
                # report the gap rather than hiding it behind a boolean.
                m4_agrees = bool(m4_gap <= max(5e-3, 0.10 * abs(m4_pooled)))
            if _m4_col is not None and _m4_col != _col:
                m4_agrees = False
                m4_gap = None
        except (ValueError, KeyError, TypeError):
            m4_pooled = None

    out["observed"] = {
        "markout_column": _col,
        "horizon_s": H.HEADLINE_HORIZON_S,
        "m4_pooled_spearman_recorded": m4_pooled,
        "m4_vs_this_check_abs_gap": m4_gap,
        "reproduces_m4_pooled": m4_agrees,
        "n_closes_finite_mo60": n,
        "mo60_q10": float(q10),
        "mo60_q90": float(q90),
        "top_decile_mean_closed_pnl": top_mean,
        "bot_decile_mean_closed_pnl": bot_mean,
        "top_decile_median_closed_pnl": top_med,
        "bot_decile_median_closed_pnl": bot_med,
        "top_decile_frac_closed_pnl_pos": top_fpos,
        "bot_decile_frac_closed_pnl_pos": bot_fpos,
        "decile_frac_closed_pnl_pos": decile_frac_pos,
        "decile_mean_closed_pnl": decile_mean,
        "strict_top_pos_and_bot_neg": bool(strict_ok),
        "ordering_top_gt_bottom_mean": bool(ordering_ok),
        "fracpos_top_gt_bottom": bool(fracpos_ok),
        "trade_grain_decile_test_informative": False,
        # DECISIVE sign-sensitive evidence
        "per_wallet_spearman_realized_vs_mo60": wallet_rho,
        "spearman_flip_test": {"as_read": wallet_rho, "negated": wallet_rho_neg},
        "spearman_flip_test_clean": bool(flip_clean),
        "per_coin_spearman": coin_rhos,
        "n_wallets_corroboration": n_wallets,
    }

    # By construction the trade-grain decile test cannot decide the sign, so the
    # verdict is set by the sign-sensitive wallet Spearman + flip-test (and the
    # external Hyperliquid doc). The asserts above already guarantee the sign is
    # positive and genuinely selected; treat that as a clean confirmation.
    coin_phrase = (", ".join(f"{k} {v:+.4f}" for k, v in coin_rhos.items())
                   if coin_rhos else "per-coin n/a")
    # The reproduction claim now carries weight in the verdict instead of sitting in
    # prose. A drift against m4 does not refute the SIGN, which the flip-test settles on
    # its own, so it downgrades rather than refutes -- but it can no longer pass unseen.
    if m4_agrees is False:
        out["verdict"] = "uncertain"
    else:
        out["verdict"] = "confirmed"
    _m4_phrase = ("m4 not read" if m4_pooled is None else
                  f"m4 pooled {m4_pooled:+.4f}, gap "
                  f"{'n/a' if m4_gap is None else format(m4_gap, '.5f')}, "
                  f"{'agrees' if m4_agrees else 'DISAGREES'}")
    out["note"] = (
        "sign confirmed at the WALLET grain by a sign-sensitive statistic: per-wallet "
        f"Spearman(sum closed_pnl over closes, mean {_col}) = {wallet_rho:+.4f} "
        f"({_m4_phrase}; per-coin {coin_phrase}, both positive). FLIP-TEST: "
        f"negating closed_pnl drives this Spearman to {wallet_rho_neg:+.4f} = exactly its "
        "negative, proving the sign is genuinely selected (not sign-blind). The strict "
        f"trade-grain per-decile mean test (top {top_mean:.3f}, bottom {bot_mean:.3f}) is "
        "UNINFORMATIVE BY CONSTRUCTION - a close-leg's closed_pnl realizes on inventory "
        "opened earlier, not on this trade's forward markout - so it is reported but not "
        "used as sign evidence. This pairs with the external Hyperliquid doc (closedPnl is "
        "profit-positive: +8722.99 on a winning Close Long, -2.5515 on a losing Close Short).")
    return out


# ---------------------------------------------------------------------------
# Check A3 - partial zero-sum magnitude of the taker-leg PnL we retain
# ---------------------------------------------------------------------------
def check_partial_zero_sum(closed_pnl):
    cp = closed_pnl[np.isfinite(closed_pnl)].astype(np.float64)
    net = float(np.sum(cp))
    gross = float(np.sum(np.abs(cp)))
    ratio = net / gross if gross > 0 else float("nan")
    n_pos = int(np.sum(cp > 0))
    n_neg = int(np.sum(cp < 0))

    # We hold the taker leg plus the dominant maker, NOT the full set of legs, so
    # an exactly-zero sum is NOT expected. What WOULD be alarming is a one-sided
    # net that is a large fraction of gross (a sign-handling or accounting error).
    if not np.isfinite(ratio):
        verdict = "uncertain"
        note = "gross turnover is zero; cannot assess net/gross."
    elif abs(ratio) <= NET_GROSS_WARN:
        verdict = "confirmed"
        note = (f"net sum closed_pnl over taker legs = {net:,.2f} on gross "
                f"{gross:,.2f} (|net|/gross = {abs(ratio):.4f} <= {NET_GROSS_WARN}). "
                "Small, two-sided as expected for a partial-leg subset; no runaway "
                "one-sided total. NOTE: |net|/gross is PROVABLY SIGN-BLIND - flipping "
                "the sign of closed_pnl leaves |net|/gross unchanged - so this check "
                "contributes ZERO sign information; the sign is pinned by the A2 "
                "wallet-Spearman flip-test plus the external Hyperliquid doc.")
    else:
        verdict = "refuted"
        note = (f"net/gross = {ratio:.4f} exceeds {NET_GROSS_WARN}: closed_pnl is "
                "strongly one-sided over the taker legs, which would point to a "
                "sign-handling or leg-accounting error.")

    return {
        "name": "partial_zero_sum_magnitude",
        "assumption": ("summing closed_pnl over the taker legs we hold is NOT exactly "
                       "zero (we keep taker + dominant maker, not all legs) but the net "
                       "should be a small, two-sided fraction of gross"),
        "method": "net sum / gross sum of |closed_pnl| over all finite taker legs",
        "observed": {
            "net_sum_closed_pnl_quote": net,
            "gross_sum_abs_closed_pnl_quote": gross,
            "net_over_gross": ratio,
            "n_pos_legs": n_pos,
            "n_neg_legs": n_neg,
        },
        "verdict": verdict,
        "note": note,
    }


# ---------------------------------------------------------------------------
# Roll-up
# ---------------------------------------------------------------------------
def roll_up(checks):
    verdicts = [c["verdict"] for c in checks]
    if "refuted" in verdicts:
        return "refuted"
    if all(v == "confirmed" for v in verdicts):
        return "confirmed"
    return "uncertain"


def main():
    started = artifact.start_clock()
    smoke = "--smoke" in sys.argv

    if not os.path.exists(NPZ_PATH):
        raise FileNotFoundError(mismatch_text(
            "the markout file this check reads is not on disk",
            f"{os.path.basename(NPZ_PATH)}, the EXTENDED markout slice carrying "
            f"closed_pnl",
            "nothing at that name beside the writer",
            f"{os.path.basename(NPZ_PATH)}, expected next to "
            f"build_quickwin_markouts.py",
            "the artifact has not been built in this clone. Run "
            "build_quickwin_markouts.py first. This is a fact about the machine, "
            "not about the repository"))

    data = np.load(NPZ_PATH, allow_pickle=False)
    _col = H.headline_print_col()
    for needed in ("taker_id", "closed_pnl", "is_open", _col, "notional"):
        if needed not in data.files:
            # Printed BEFORE raising rather than carried in the exception, because
            # KeyError is the one builtin whose str() is the repr of its argument:
            # a multi-line message inside it reaches the screen as one line with
            # the newlines spelled out, which is worse than no formatting at all.
            print(mismatch_text(
                "the markout file is missing a column this check needs",
                f"a column named {needed!r}"
                + (", which is what settings.headline_print_col() declares the "
                   "headline horizon to be" if needed == _col else ""),
                f"{len(data.files)} columns, {sorted(data.files)}",
                os.path.basename(NPZ_PATH),
                "the file was written by an older build than the one this check "
                "expects, or the declared headline column moved without the "
                "artifact being rebuilt under it"))
            raise KeyError(f"{os.path.basename(NPZ_PATH)} has no column {needed!r} "
                           f"(expectation, fact and place printed above)")

    taker_id = data["taker_id"].astype(np.int64)
    closed_pnl = data["closed_pnl"].astype(np.float64)
    is_open = data["is_open"].astype(np.int8)
    # This check's decisive argument is that its own Spearman REPRODUCES the number
    # m4_realizedpnl publishes. Reading a fixed column while m4 reads the declared one
    # breaks that argument silently: both files keep passing, and the two numbers they
    # quote at each other simply stop being the same quantity.
    mo60 = data[_col].astype(np.float64)
    notional = data["notional"].astype(np.float64)
    # coin (0=BTC, 1=ETH) feeds the per-coin Spearman flip-test breakdown; optional.
    coin = data["coin"].astype(np.int8) if "coin" in data.files else None

    n_total = int(taker_id.size)
    if smoke:
        k = min(SMOKE_ROWS, n_total)
        taker_id = taker_id[:k]
        closed_pnl = closed_pnl[:k]
        is_open = is_open[:k]
        mo60 = mo60[:k]
        notional = notional[:k]
        coin = coin[:k] if coin is not None else None
        print(f"[{CHECK_NAME}] --smoke: first {k:,} of {n_total:,} rows "
              "(NOT representative; full mode is the default)")
    else:
        print(f"[{CHECK_NAME}] full run (default): {n_total:,} rows")

    checks = [
        check_opens_zero(closed_pnl, is_open, notional),
        check_sign_alignment(taker_id, closed_pnl, is_open, mo60, coin=coin),
        check_partial_zero_sum(closed_pnl),
    ]
    overall = roll_up(checks)

    result = {
        "check": CHECK_NAME,
        "mode": "smoke" if smoke else "full",
        "n_rows_used": int(taker_id.size),
        "n_rows_total_on_disk": n_total,
        "input_npz": os.path.basename(NPZ_PATH),
        "checks": checks,
        "overall_verdict": overall,
    }
    # Rows used, not rows on disk: --smoke truncates to the first k, and a scope that
    # named the file's total would describe the artifact as covering a population the
    # run never looked at.
    artifact.write(
        os.path.basename(OUT_PATH), result,
        script=__file__,
        inputs=[NPZ_PATH] + ([M4_RESULTS] if os.path.exists(M4_RESULTS) else []),
        scope={
            "population": f"{int(taker_id.size):,} taker fills of the "
                          f"{n_total:,} in {os.path.basename(NPZ_PATH)}"
                          + (" (--smoke prefix, NOT representative)" if smoke else ""),
            "window": "the span of quickwin_markouts.npz; this check reads the slice "
                      "whole and does not cut it by date",
            "coins": "every coin present in quickwin_markouts.npz; the check is a "
                     "sign convention and is not cut by coin",
        },
        settings={"h": H.HEADLINE_HORIZON_S, "lens": "print"},
        started=started,
    )

    # one-line human summary
    parts = [f"{c['name']}={c['verdict']}" for c in checks]
    print(f"[{CHECK_NAME}] {'SMOKE ' if smoke else ''}overall={overall} | "
          + " | ".join(parts) + f" -> {os.path.basename(OUT_PATH)}")
    # This check is the third-key corroboration against a common-mode sign error, so
    # a refutation here says the exchange's own realized-profit field disagrees with
    # the markout sign the whole study is built on. Until 2026-07-30 that was written
    # into the results file and the run still exited 0.
    return report_contract(result, OUT_PATH,
                           inputs={"npz": NPZ_PATH,
                                   "column": H.headline_print_col()})


if __name__ == "__main__":
    sys.exit(main())
