"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-20
References: Hyperliquid node-data S3 archive (s3://hl-mainnet-node-data); Zenodo 18184441 (Albers et al. 2026).

PURPOSE (re-verification, NOT a re-audit of internal consistency)
-----------------------------------------------------------------
The prior audits only checked number-on-disk == number-in-doc; they could not
catch a mis-read field or a non-reproducible build. This script GROUND-TRUTHS
the row-level provenance of the three markout artifacts EMPIRICALLY:

  (a) row counts of quickwin / quickwin_mid / panel. HARD ASSERTS (raise on
      mismatch, run first incl. under --smoke) now pin: quickwin == 2,480,267,
      panel total == 10,455,129, per-coin BTC/ETH/SOL == 3,736,972 / 4,356,836 /
      2,361,321, panel periods == {202508,202510,202512}, and quickwin vs _mid
      equal length + element-wise identical taker_id/coin/day. These make the
      documented counts CODE-ENFORCED, not merely measured. The panel's `period`
      on-disk dtype (int64, from the canonical builder panel_persistence.py) is
      also recorded.
  (b) panel coin value-counts (does SOL==2 actually exist and carry rows?) and
      per (coin, period) counts; and whether the panel's December BTC/ETH slice
      reproduces the 2-coin quickwin numbers exactly.
  (c) row-alignment of quickwin vs quickwin_mid: same length, and the ID/key
      columns (taker_id, coin, day) element-wise identical -- the _mid build
      ASSUMES this alignment ("SAME order as quickwin_markouts.npz") but never
      validates it. We test it.
  (d) DETERMINISM: re-walk ONE December day for ONE coin through the ORIGINAL
      build_quickwin_markouts.parse_day (the real parser, not a re-implementation),
      recompute the load-bearing columns the same way main() does, and check the
      re-parse reproduces that day/coin slice of the stored npz. The comparison is
      a JOINT-TUPLE (lexicographic) multiset over ALL load-bearing columns -- both
      sides are lexsorted by the same tolerance-quantized key and compared
      ROW-BY-ROW, so cross-column row-pairing is preserved (a per-column multiset
      compare would silently pass a row-assembly scramble). Under --smoke the
      re-parse is SKIPPED and its verdict is 'uncertain' (NOT proven).

Each check emits {assumption, method, observed, verdict, note}. The overall
verdict is the worst of the per-check verdicts.

CONTRACT: writes chk_rowcounts_determinism_results.json next to this script:
  { "check": "...", "checks": [ {name, assumption, method, observed, verdict, note}, ... ],
    "overall_verdict": "confirmed|refuted|uncertain" }

RUN (bare python3 is BLOCKED on this machine):
  uv run --no-project --with-requirements requirements.txt python3 checks/chk_rowcounts_determinism.py
  uv run --no-project --with-requirements requirements.txt python3 checks/chk_rowcounts_determinism.py --smoke

--smoke processes shapes only and SKIPS the S3 re-parse (the heavy step), so a
reviewer can validate the contract end-to-end cheaply.
"""

import hashlib
import json
import os
import sys

import numpy as np

# -------------------- paths --------------------
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
if os.path.dirname(HERE) not in sys.path:
    sys.path.insert(0, os.path.dirname(HERE))
CODE_DIR = os.path.dirname(HERE)                       # the repository root
# The parser the determinism leg re-walks a day through lives in a pipeline group rather
# than beside the tree root, so the group directory has to be on the path as well: adding
# the root is not enough once a module is one level down. Named per group rather than
# globbed, so that a module moving to a group not listed here fails loudly at import
# instead of resolving by luck.
for _group in ("data",):
    _p = os.path.join(CODE_DIR, _group)
    if _p not in sys.path:
        sys.path.insert(0, _p)

import artifact                                                       # noqa: E402
import build_quickwin_markouts as bqm                                 # noqa: E402
import settings as H                                                  # noqa: E402
from evidence import mismatch_text, report_contract                   # noqa: E402

QUICKWIN = os.path.join(CODE_DIR, "quickwin_markouts.npz")
QUICKWIN_MID = os.path.join(CODE_DIR, "quickwin_markouts_mid.npz")
PANEL = os.path.join(CODE_DIR, "panel_markouts.npz")
# The parser source is located by ASKING the imported module where it is, not by
# rebuilding a path from a directory this check assumes. It moved into a pipeline group
# on 2026-08-11 and the rebuilt path went on pointing at the root, where the file no
# longer is. The cost was not a loud failure: the import inside the determinism leg
# raised FileNotFoundError, the leg caught it, recorded 'uncertain' and wrote a note
# offering "e.g. S3 unavailable" as the reason -- while the tape was on disk and two
# sibling checks re-read the same day minutes later. The path was also declared as an
# input, so the artifact recorded present=false, kind=absent for a file that exists. A
# module knows its own address; a check rebuilding it is resolving by path instead of by
# content, and this is the same repair chk_field_hygiene.py already carries.
BUILD_SRC = os.path.abspath(bqm.__file__)
OUT_JSON = os.path.join(HERE, "chk_rowcounts_determinism_results.json")

CHECK_NAME = "rowcounts_determinism"

# documented / claimed numbers we are TESTING against (not trusting)
QUICKWIN_EXPECTED = 2_480_267          # asserted in code/docs -> HARD assert
# The code map, asked for BY ARTIFACT rather than typed. All three uses of this map in
# this file read panel_markouts.npz -- the per-coin canonical counts, the coin value
# counts and the per-period breakdown -- so the artifact it belongs to is the panel,
# which carries {0, 1, 2}. Naming the artifact is what stops the quickwin map, which
# carries {0, 1}, from being read here: a code valid in both files relabels a coin
# without raising. Proved equal before the move: the literal here was
# {0: "BTC", 1: "ETH", 2: "SOL"} and coin_labels("panel") returns the same map.
COIN_LABEL = H.coin_labels("panel")

# Code-enforced ground truth (HARD asserts, raise on mismatch). These pin the
# row-level shape of the three artifacts so the counts are enforced, not merely
# measured-and-reported. They run in --smoke too (local npz only). The canonical
# panel builder is panel_persistence.py (run_panel.sh uses --build via it because
# panel_build.py re-downloads ~44GB per coin); panel_build.py is the older path.
#
# SCOPE -- the distinction this file used to conflate. panel_markouts.npz was
# later REBUILT from the original 3 windows to 8 (Aug 2025 .. May 2026), so the
# artifact holds MORE rows than the reported panel uses. The three panel readers
# (panel_persistence.py, panel_analyze.py, panel_common_idio.py) each pin
# CANONICAL_PERIODS = (202508, 202510, 202512) and restrict their load to it, so
# the ANALYSED population is that canonical subset. The asserts below therefore
# pin the CANONICAL SUBSET exactly and require only that the artifact CONTAINS
# those windows. Asserting the artifact TOTAL instead -- which this file did --
# turns every legitimate panel extension into an AssertionError, and did: after
# the 8-window rebuild the check raised on `panel total 26,035,902 != 10,455,129`
# while its own committed results JSON still read "confirmed".
PANEL_CANONICAL_ROWS = 10_455_129      # rows in the analysed (3-window) subset
PANEL_CANONICAL_PERCOIN = {"BTC": 3_736_972, "ETH": 4_356_836, "SOL": 2_361_321}
PANEL_PERIODS_ANALYSED = {202508, 202510, 202512}
PANEL_PERIOD_DTYPE_ONDISK = "int64"    # panel_persistence.py writes int64 (canonical)

# determinism re-parse target (light: ONE December day, ONE coin)
REPARSE_DAY = "20251204"               # day-of-month 4
REPARSE_COIN = "BTC"
REPARSE_DAY_NUM = int(REPARSE_DAY[6:8])


def _verdict_rank(v):
    return {"confirmed": 0, "uncertain": 1, "refuted": 2}.get(v, 1)


def _worst(verdicts):
    if not verdicts:
        return "uncertain"
    return max(verdicts, key=_verdict_rank)


def _load(npz_path):
    return np.load(npz_path, allow_pickle=False)


def _to_native(x):
    """Make numpy scalars JSON-serialisable."""
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating,)):
        return float(x)
    if isinstance(x, (np.bool_,)):
        return bool(x)
    return x


# ---------------------------------------------------------------------------
# (0) HARD asserts -- code-enforced ground truth (raise on mismatch).
#     These run FIRST (incl. under --smoke) and use the local npz files only.
# ---------------------------------------------------------------------------
def hard_asserts(checks):
    """Raise immediately on any row-count / period / alignment drift.

    Makes the documented counts code-enforced rather than just measured: a
    mismatch aborts the check with a clear AssertionError instead of being
    softened into a JSON verdict. Records a passing 'hard_asserts' entry once
    all asserts hold so the contract still shows the enforced numbers.
    """
    z_q = _load(QUICKWIN)
    z_m = _load(QUICKWIN_MID)
    z_p = _load(PANEL)

    n_q = int(len(z_q["taker_id"]))
    n_m = int(len(z_m["taker_id"]))
    n_p = int(len(z_p["taker_id"]))

    # quickwin row count
    assert n_q == QUICKWIN_EXPECTED, mismatch_text(
        "quickwin row count",
        f"{QUICKWIN_EXPECTED:,} rows, the documented count this study reports on",
        f"{n_q:,} rows, a difference of {n_q - QUICKWIN_EXPECTED:+,}",
        f"{os.path.basename(QUICKWIN)}, column taker_id",
        "the artifact on disk is not the one the reported numbers were taken from; "
        "either it was rebuilt under different settings or the documented count is "
        "stale. Do not update the constant until the producer has been re-run.")

    # panel: the artifact may legitimately hold MORE windows than the reported
    # analysis uses (see SCOPE above), so we assert the CANONICAL SUBSET, not the
    # artifact total. Containment first, then the subset's exact shape.
    p_coin = z_p["coin"]
    p_period = z_p["period"]
    periods_present = {int(p) for p in np.unique(p_period)}
    assert PANEL_PERIODS_ANALYSED <= periods_present, mismatch_text(
        "panel contains every analysed window",
        f"the panel holds at least the windows {sorted(PANEL_PERIODS_ANALYSED)}; "
        f"it may hold more, and extra windows are not a defect",
        f"windows {sorted(periods_present)} are present, so "
        f"{sorted(PANEL_PERIODS_ANALYSED - periods_present)} is absent",
        f"{os.path.basename(PANEL)}, column period",
        "a window the study reports on is not in the artifact, so its numbers "
        "cannot have come from this file")

    canon = np.isin(p_period, sorted(PANEL_PERIODS_ANALYSED))
    n_p_canon = int(canon.sum())
    assert n_p_canon == PANEL_CANONICAL_ROWS, mismatch_text(
        "panel row count on the analysed windows",
        f"{PANEL_CANONICAL_ROWS:,} rows across windows "
        f"{sorted(PANEL_PERIODS_ANALYSED)}",
        f"{n_p_canon:,} rows, a difference of "
        f"{n_p_canon - PANEL_CANONICAL_ROWS:+,} (the file holds {n_p:,} in total)",
        f"{os.path.basename(PANEL)}, rows where period is in "
        f"{sorted(PANEL_PERIODS_ANALYSED)}",
        "the analysed subset is not the size the study reports, so the panel was "
        "rebuilt under a setting that changed which rows survive")

    # panel per-coin, on the canonical subset
    percoin = {}
    for code, label in COIN_LABEL.items():
        percoin[label] = int((p_coin[canon] == code).sum())
    for label, want in PANEL_CANONICAL_PERCOIN.items():
        assert percoin.get(label, 0) == want, mismatch_text(
            f"panel {label} row count on the analysed windows",
            f"{want:,} {label} rows",
            f"{percoin.get(label, 0):,}, a difference of "
            f"{percoin.get(label, 0) - want:+,}; the full breakdown is {percoin}",
            f"{os.path.basename(PANEL)}, rows where coin is {label} and period is "
            f"in {sorted(PANEL_PERIODS_ANALYSED)}",
            "the per-coin split moved while the total may not have, which is the "
            "shape a coin-filter change leaves behind")

    # quickwin vs _mid: equal length AND element-wise identical taker_id/coin/day
    assert n_m == n_q, mismatch_text(
        "the print-price and mid-price slices are the same rows",
        f"{os.path.basename(QUICKWIN_MID)} holds exactly the {n_q:,} rows of "
        f"{os.path.basename(QUICKWIN)}",
        f"{n_m:,} rows, a difference of {n_m - n_q:+,}",
        f"{os.path.basename(QUICKWIN_MID)} against "
        f"{os.path.basename(QUICKWIN)}, column taker_id",
        "the two price conventions were built over different populations, so any "
        "figure quoting one against the other compares two different samples")
    for col in ("taker_id", "coin", "day"):
        assert np.array_equal(z_q[col], z_m[col]), mismatch_text(
            f"the two slices agree row for row on {col}",
            f"{col} is element-wise identical in both files",
            f"{col} differs in "
            f"{int(np.sum(z_q[col] != z_m[col])):,} of {n_q:,} rows",
            f"{os.path.basename(QUICKWIN_MID)} against "
            f"{os.path.basename(QUICKWIN)}, column {col}",
            "the two files are the same length but not the same rows, so joining "
            "them by position pairs one trade's print price with another's mid")

    z_q.close(); z_m.close(); z_p.close()

    checks.append({
        "name": "hard_asserts",
        "assumption": ("documented counts are code-enforced: quickwin=="
                       f"{QUICKWIN_EXPECTED}; the panel CONTAINS the analysed "
                       f"windows {sorted(PANEL_PERIODS_ANALYSED)} and their subset "
                       f"is exactly {PANEL_CANONICAL_ROWS} rows, per-coin "
                       f"{PANEL_CANONICAL_PERCOIN}; quickwin/_mid share "
                       "taker_id/coin/day element-wise"),
        "method": ("runtime assert (raise on mismatch) on local npz only; "
                   "runs under --smoke too; panel asserts are scoped to the "
                   "canonical windows, the artifact total is recorded not pinned"),
        "observed": {
            "quickwin_rows": n_q,
            "panel_rows_on_disk": n_p,
            "panel_rows_analysed": n_p_canon,
            "panel_per_coin_analysed": percoin,
            "panel_periods_on_disk": sorted(periods_present),
            "panel_periods_analysed": sorted(PANEL_PERIODS_ANALYSED),
            "mid_rows": n_m,
        },
        "verdict": "confirmed",
        "note": "all hard asserts passed -> the analysed counts are enforced, "
                "not merely measured; the artifact may hold extra windows",
    })


# ---------------------------------------------------------------------------
# (a) row counts + the one hard assert
# ---------------------------------------------------------------------------
def check_rowcounts(checks):
    z_q = _load(QUICKWIN)
    z_m = _load(QUICKWIN_MID)
    z_p = _load(PANEL)
    n_q = int(len(z_q["taker_id"]))
    n_m = int(len(z_m["taker_id"]))
    n_p = int(len(z_p["taker_id"]))
    z_q.close(); z_m.close(); z_p.close()

    # HARD assert on the documented quickwin count -- this is the one number the
    # build code/docs commit to, so a mismatch is a refutation, not a soft note.
    quickwin_ok = (n_q == QUICKWIN_EXPECTED)
    assert quickwin_ok, mismatch_text(
        "quickwin row count, the second and softer read of the same number",
        f"{QUICKWIN_EXPECTED:,} rows, the one count the build code and the "
        f"documents both commit to",
        f"{n_q:,} rows, a difference of {n_q - QUICKWIN_EXPECTED:+,}",
        f"{os.path.basename(QUICKWIN)}, column taker_id",
        "hard_asserts above reads the same number and would have fired first; "
        "reaching this line means it was skipped")

    checks.append({
        "name": "quickwin_row_count_assert",
        "assumption": f"quickwin_markouts.npz has exactly {QUICKWIN_EXPECTED} rows",
        "method": "len(taker_id) of quickwin_markouts.npz; hard assert == documented",
        "observed": {"rows": n_q, "expected": QUICKWIN_EXPECTED},
        "verdict": "confirmed" if quickwin_ok else "refuted",
        "note": "documented count reproduced exactly" if quickwin_ok
                else "row count does not match the documented value",
    })

    # The panel artifact holds every window ever built; the reported analysis reads
    # only the canonical three. Report BOTH so a reader cannot mistake one for the
    # other, and judge the check on the analysed subset (the number the paper uses).
    z_p2 = _load(PANEL)
    period = z_p2["period"]
    n_p_canon = int(np.isin(period, sorted(PANEL_PERIODS_ANALYSED)).sum())
    periods_on_disk = sorted({int(p) for p in np.unique(period)})
    z_p2.close()
    panel_ok = (n_p_canon == PANEL_CANONICAL_ROWS)
    checks.append({
        "name": "panel_row_count_measured",
        "assumption": (f"the ANALYSED panel (windows {sorted(PANEL_PERIODS_ANALYSED)}) "
                       f"has {PANEL_CANONICAL_ROWS} rows; the artifact on disk may "
                       "hold additional windows from a later rebuild"),
        "method": ("len(taker_id) of panel_markouts.npz, and the same count "
                   "restricted to the canonical windows the readers pin"),
        "observed": {"rows_on_disk": n_p, "rows_analysed": n_p_canon,
                     "expected_analysed": PANEL_CANONICAL_ROWS,
                     "periods_on_disk": periods_on_disk,
                     "matches_claim": panel_ok},
        "verdict": "confirmed" if panel_ok else "refuted",
        "note": ("analysed-subset count equals the reported number; the artifact "
                 f"holds {len(periods_on_disk)} window(s) in total" if panel_ok
                 else "analysed-subset count differs from the reported number"),
    })

    checks.append({
        "name": "quickwin_mid_row_count",
        "assumption": "quickwin_markouts_mid.npz is one aligned row per quickwin trade",
        "method": "len(taker_id) of quickwin_markouts_mid.npz vs quickwin",
        "observed": {"rows_mid": n_m, "rows_quickwin": n_q, "equal_length": n_m == n_q},
        "verdict": "confirmed" if n_m == n_q else "refuted",
        "note": ("mid file has the same number of rows as quickwin" if n_m == n_q
                 else "mid file length differs from quickwin -> not row-aligned"),
    })
    return n_q, n_m, n_p


# ---------------------------------------------------------------------------
# (b) panel coin value-counts + per (coin, period) + Dec BTC/ETH vs quickwin
# ---------------------------------------------------------------------------
def check_panel_breakdown(checks):
    z_p = _load(PANEL)
    coin = z_p["coin"]; period = z_p["period"]; day = z_p["day"]
    z_q = _load(QUICKWIN)
    qcoin = z_q["coin"]

    # ---- panel `period` on-disk dtype (documentation-vs-artifact reconciliation) ----
    # The canonical builder panel_persistence.py writes `period` as int64; the older
    # panel_build.py and its manifest schema_note say int32. Both readers cast to
    # int64 and the values {202508,202510,202512} fit either, so this is a docs/dtype
    # drift, NOT a data error. We record the dtype actually on disk so the artifact
    # is the source of truth.
    period_dtype = str(period.dtype)
    dtype_ok = (period_dtype == PANEL_PERIOD_DTYPE_ONDISK)
    checks.append({
        "name": "panel_period_dtype",
        "assumption": ("panel_markouts.npz stores `period` as "
                       f"{PANEL_PERIOD_DTYPE_ONDISK} (canonical builder "
                       "panel_persistence.py)"),
        "method": "read panel_markouts.npz['period'].dtype",
        "observed": {"period_dtype_on_disk": period_dtype,
                     "expected": PANEL_PERIOD_DTYPE_ONDISK,
                     "canonical_builder": "panel_persistence.py",
                     "note_on_drift": ("panel_build.py / manifest schema_note say "
                                       "int32 -- documentation drift only; readers "
                                       "cast to int64 and the YYYYMM values fit both")},
        "verdict": "confirmed" if dtype_ok else "refuted",
        "note": (f"panel `period` is {period_dtype} on disk, matching the canonical "
                 "panel_persistence.py output" if dtype_ok
                 else f"panel `period` dtype {period_dtype} != expected "
                      f"{PANEL_PERIOD_DTYPE_ONDISK}"),
    })

    coin_vals, coin_cnts = np.unique(coin, return_counts=True)
    coin_counts = {COIN_LABEL.get(int(v), str(int(v))): int(c)
                   for v, c in zip(coin_vals, coin_cnts)}
    sol_rows = int((coin == 2).sum())

    per_vals = np.unique(period)
    per_coin_period = {}
    for prd in per_vals:
        ps = period == prd
        sub = {}
        for v in np.unique(coin[ps]):
            sub[COIN_LABEL.get(int(v), str(int(v)))] = int((coin[ps] == v).sum())
        per_coin_period[int(prd)] = sub

    # SOL presence check
    checks.append({
        "name": "panel_coin_has_sol",
        "assumption": "panel includes coin==2 (SOL) with a positive row count",
        "method": "np.unique(coin) value-counts on panel_markouts.npz",
        "observed": {"coin_counts": coin_counts, "sol_rows": sol_rows,
                     "periods": [int(p) for p in per_vals],
                     "per_coin_period": per_coin_period},
        "verdict": "confirmed" if sol_rows > 0 else "refuted",
        "note": (f"SOL present with {sol_rows} rows across "
                 f"{len(per_vals)} periods" if sol_rows > 0
                 else "no SOL (coin==2) rows found in panel"),
    })

    # December BTC/ETH slice of the panel must reproduce the 2-coin quickwin
    # numbers exactly (the panel's Dec slice should be the same parse as quickwin).
    dec = period == 202512
    panel_dec_btc = int(((coin == 0) & dec).sum())
    panel_dec_eth = int(((coin == 1) & dec).sum())
    q_btc = int((qcoin == 0).sum())
    q_eth = int((qcoin == 1).sum())
    z_p.close(); z_q.close()

    match_btc = panel_dec_btc == q_btc
    match_eth = panel_dec_eth == q_eth
    both = match_btc and match_eth
    has_dec = bool(dec.any())
    if not has_dec:
        verdict = "refuted"
        note = "panel has no 202512 (December) period -> cannot reconcile with quickwin"
    elif both:
        verdict = "confirmed"
        note = "panel December BTC/ETH counts reproduce the 2-coin quickwin numbers exactly"
    else:
        verdict = "refuted"
        note = "panel December BTC/ETH counts do NOT match the quickwin 2-coin numbers"

    checks.append({
        "name": "panel_december_matches_quickwin",
        "assumption": ("panel's December (202512) BTC+ETH rows equal the standalone "
                       "quickwin BTC+ETH counts (same parse)"),
        "method": "per-(coin) count on panel period==202512 vs quickwin per-coin count",
        "observed": {
            "panel_dec_BTC": panel_dec_btc, "quickwin_BTC": q_btc, "BTC_match": match_btc,
            "panel_dec_ETH": panel_dec_eth, "quickwin_ETH": q_eth, "ETH_match": match_eth,
        },
        "verdict": verdict,
        "note": note,
    })


# ---------------------------------------------------------------------------
# (c) row-alignment quickwin vs _mid: ID/key columns element-wise identical
# ---------------------------------------------------------------------------
def check_alignment(checks):
    z_q = _load(QUICKWIN)
    z_m = _load(QUICKWIN_MID)
    n_q = len(z_q["taker_id"]); n_m = len(z_m["taker_id"])

    if n_q != n_m:
        z_q.close(); z_m.close()
        checks.append({
            "name": "quickwin_mid_alignment",
            "assumption": "quickwin and _mid share taker_id/coin/day element-wise",
            "method": "length compare (short-circuit before element compare)",
            "observed": {"rows_quickwin": int(n_q), "rows_mid": int(n_m)},
            "verdict": "refuted",
            "note": "unequal lengths -> element-wise alignment is impossible",
        })
        return

    per_col = {}
    all_equal = True
    for col in ("taker_id", "coin", "day"):
        eq = bool(np.array_equal(z_q[col], z_m[col]))
        n_mismatch = int(np.count_nonzero(z_q[col] != z_m[col]))
        per_col[col] = {"identical": eq, "n_mismatch": n_mismatch}
        all_equal = all_equal and eq
    z_q.close(); z_m.close()

    checks.append({
        "name": "quickwin_mid_alignment",
        "assumption": ("quickwin_markouts_mid.npz is in the SAME row order as quickwin "
                       "(taker_id/coin/day identical element-wise) -- assumed by the "
                       "_mid build, never validated"),
        "method": "np.array_equal on taker_id, coin, day across the two files",
        "observed": {"rows": int(n_q), "columns": per_col},
        "verdict": "confirmed" if all_equal else "refuted",
        "note": ("all three key columns are element-wise identical -> the files are "
                 "row-aligned" if all_equal
                 else "at least one key column differs -> the two files are NOT row-aligned; "
                      "any join-by-position between them is unsafe"),
    })


# ---------------------------------------------------------------------------
# (d) DETERMINISM: re-walk ONE Dec day/coin via the ORIGINAL parse_day
# ---------------------------------------------------------------------------
def _import_builder():
    """Return the ORIGINAL builder module, so the re-parse calls the REAL parse_day.

    The module is imported at load time (top of this file) by NAME off the pipeline
    group, rather than executed here from a path rebuilt out of the tree root. Two
    things follow, and both were defects before. An address that no longer exists now
    fails at import, loudly and before any check runs, instead of surfacing two hundred
    lines later as a caught FileNotFoundError that reads as an unreachable S3. And the
    module is loaded ONCE under its own name, so the re-parse and the hash in BUILD_SRC
    are demonstrably the same file rather than two copies that happen to agree.
    """
    return bqm


def check_determinism(checks, smoke):
    if smoke:
        # A skipped re-parse must NOT read as proven determinism. Verdict is
        # 'uncertain' and the note states the re-parse did not run, so the overall
        # (worst-of) verdict cannot claim determinism on a smoke pass.
        checks.append({
            "name": "determinism_reparse",
            "assumption": ("re-walking a December day through the original parse_day "
                           "reproduces the stored npz slice for that day/coin"),
            "method": "SKIPPED under --smoke (S3 re-parse is the heavy step)",
            "observed": {"skipped": True, "reparse_day": REPARSE_DAY,
                         "reparse_coin": REPARSE_COIN},
            "verdict": "uncertain",
            "note": ("determinism re-parse NOT run (smoke); determinism is NOT "
                     "established -- run full mode to ground-truth it"),
        })
        return

    # ---- stored slice from the canonical npz ----
    z_q = _load(QUICKWIN)
    coin = z_q["coin"]; day = z_q["day"]
    coin_code = {"BTC": 0, "ETH": 1}[REPARSE_COIN]
    sel = (coin == coin_code) & (day == REPARSE_DAY_NUM)
    stored_n = int(sel.sum())
    z_q.close()

    # ---- re-parse the SAME day via the ORIGINAL builder ----
    # Re-parse, retrying until the FULL 24 hours land. download_day will "salvage"
    # a partial pull (>=20 hours), and a partial day legitimately undercounts the
    # collapsed sweeps -- that is an environmental hiccup, NOT a non-deterministic
    # build. So we require all 24 hours before treating any mismatch as a real
    # refutation; a stubbornly-partial pull is reported as uncertain instead.
    FULL_HOURS = 24
    MAX_TRIES = 3
    try:
        bq = _import_builder()
        per_coin, hours_ok = None, []
        for _try in range(1, MAX_TRIES + 1):
            per_coin, hours_ok = bq.parse_day(REPARSE_DAY)
            if per_coin is None or len(hours_ok) >= FULL_HOURS:
                break
    except Exception as exc:
        checks.append({
            "name": "determinism_reparse",
            "assumption": ("re-walking a December day through the original parse_day "
                           "reproduces the stored npz slice for that day/coin"),
            "method": "bq.parse_day(REPARSE_DAY) then recompute load-bearing columns",
            "observed": {"error": repr(exc), "reparse_day": REPARSE_DAY,
                         "reparse_coin": REPARSE_COIN},
            "verdict": "uncertain",
            "note": "could not re-parse (e.g. S3 unavailable); determinism not established",
        })
        return

    if per_coin is not None and len(hours_ok) < FULL_HOURS:
        checks.append({
            "name": "determinism_reparse",
            "assumption": ("re-walking a December day through the original parse_day "
                           "reproduces the stored npz slice for that day/coin"),
            "method": ("bq.parse_day(REPARSE_DAY); require all 24 hourly files before "
                       "judging determinism"),
            "observed": {"hours_reparsed": len(hours_ok), "needed": FULL_HOURS,
                         "tries": MAX_TRIES, "reparse_day": REPARSE_DAY,
                         "reparse_coin": REPARSE_COIN},
            "verdict": "uncertain",
            "note": ("S3 re-download stayed partial after retries (a partial day "
                     "undercounts sweeps); environmental, not a build defect -- rerun "
                     "the full check when the pull completes"),
        })
        return

    if per_coin is None or REPARSE_COIN not in per_coin:
        checks.append({
            "name": "determinism_reparse",
            "assumption": "parse_day returns the requested coin for a present December day",
            "method": "bq.parse_day(REPARSE_DAY)",
            "observed": {"per_coin_none": per_coin is None, "hours_ok": hours_ok,
                         "reparse_day": REPARSE_DAY, "reparse_coin": REPARSE_COIN},
            "verdict": "refuted" if per_coin is None else "uncertain",
            "note": "re-parse did not yield the target coin/day slice",
        })
        return

    d = per_coin[REPARSE_COIN]
    # recompute the load-bearing columns EXACTLY as main() does
    mo = bq.compute_markouts_all(d["taker_ts"], d["taker_px"], d["taker_dir"],
                                 d["print_ts"], d["print_px"])
    reparse_n = int(d["taker_ts"].size)

    # stored slice
    z_q2 = _load(QUICKWIN)
    coin2 = z_q2["coin"]; day2 = z_q2["day"]
    sel2 = (coin2 == coin_code) & (day2 == REPARSE_DAY_NUM)

    # ---- JOINT-TUPLE (lexicographic) multiset comparison (determinism test) ----
    # The earlier version sorted EACH column independently and compared per-column
    # multisets. That silently passes a cross-column row-ASSEMBLY scramble: if a
    # faithless build kept every column's value-multiset but paired the wrong
    # entry_px with the wrong mo60, the per-column compare would not notice. So we
    # now compare the WHOLE-ROW multiset: sort both sides by the SAME lexicographic
    # key over ALL load-bearing columns, then compare row-by-row. This preserves
    # cross-column row-pairing without needing the global taker_id (which is coded
    # globally in the npz but only locally on a standalone re-parse).
    #
    # Float32 robustness: the npz stores markouts/start_pos as float32, so the
    # recomputed float64 values are downcast before comparing. To make the lexsort
    # tie-break stable under the per-column tolerance, the sort KEY is each column
    # QUANTIZED to its tolerance grid (a tol-difference must not change row order);
    # the element-wise compare afterwards still runs on the raw f32 values at the
    # documented tolerance. NaNs map to a sentinel so their COUNTS must also match.
    F32_NAN = np.float32(1e30)

    # column order is fixed and load-bearing; (re-parse, stored) value pairs.
    col_pairs = {
        "entry_px": (d["taker_px"], z_q2["entry_px"][sel2]),
        "mo1": (mo[1], z_q2["mo1"][sel2]),
        "mo10": (mo[10], z_q2["mo10"][sel2]),
        "mo60": (mo[60], z_q2["mo60"][sel2]),
        "start_pos": (d["taker_spos"], z_q2["start_pos"][sel2]),
        "taker_side": (d["taker_side"], z_q2["taker_side"][sel2]),
    }
    COL_ORDER = ("entry_px", "mo1", "mo10", "mo60", "start_pos", "taker_side")
    # markouts/entry compared at <=1e-2 bps (float32 storage + f64->f32 downcast);
    # start_pos at <=1e-3 (size units); taker_side exact.
    tol = {"entry_px": 1e-2, "mo1": 1e-2, "mo10": 1e-2, "mo60": 1e-2,
           "start_pos": 1e-3, "taker_side": 0.0}
    # quantization step for the SORT key (NOT the compare). 0 tol -> exact key.
    qstep = {k: (v if v > 0 else 1.0) for k, v in tol.items()}

    def _f32_nan(a):
        a = np.asarray(a).astype(np.float32)
        n_nan = int(np.isnan(a).sum())
        a = np.where(np.isnan(a), F32_NAN, a)
        return a, n_nan

    # build per-column f32 arrays + NaN counts for each side
    r_cols, s_cols, nan_counts = {}, {}, {}
    lengths_ok = True
    for name in COL_ORDER:
        ra, r_nan = _f32_nan(col_pairs[name][0])
        sa, s_nan = _f32_nan(col_pairs[name][1])
        r_cols[name] = ra
        s_cols[name] = sa
        nan_counts[name] = (r_nan, s_nan)
        if ra.size != sa.size:
            lengths_ok = False

    def _joint_sort(cols):
        """lexsort over tolerance-quantized keys; return the row permutation.
        np.lexsort takes keys LAST-is-primary, so reverse COL_ORDER."""
        n = cols[COL_ORDER[0]].size
        keys = []
        for name in reversed(COL_ORDER):
            q = np.round(cols[name].astype(np.float64) / qstep[name])
            keys.append(q)
        return np.lexsort(keys) if n else np.empty(0, dtype=np.intp)

    col_report = {}
    all_cols_ok = True
    if lengths_ok and reparse_n == stored_n:
        r_perm = _joint_sort(r_cols)
        s_perm = _joint_sort(s_cols)
        for name in COL_ORDER:
            rs = r_cols[name][r_perm]
            ss = s_cols[name][s_perm]
            # element-wise (row-paired) max abs diff after the JOINT sort
            maxdiff = float(np.max(np.abs(rs - ss))) if rs.size else 0.0
            vals_ok = maxdiff <= tol[name]
            r_nan, s_nan = nan_counts[name]
            nan_ok = (r_nan == s_nan)
            col_ok = vals_ok and nan_ok
            all_cols_ok = all_cols_ok and col_ok
            col_report[name] = {
                "reparse_n_nan": r_nan, "stored_n_nan": s_nan, "nan_match": nan_ok,
                "max_joint_paired_abs_diff": maxdiff, "tol": tol[name],
                "values_identical": vals_ok, "ok": col_ok,
            }
    else:
        all_cols_ok = False
        for name in COL_ORDER:
            r_nan, s_nan = nan_counts[name]
            col_report[name] = {
                "reparse_n_nan": r_nan, "stored_n_nan": s_nan,
                "nan_match": (r_nan == s_nan),
                "max_joint_paired_abs_diff": None, "tol": tol[name],
                "values_identical": False, "ok": False,
            }
    z_q2.close()

    count_match = (reparse_n == stored_n)
    ok = count_match and all_cols_ok

    # Compact reproducible digest over the JOINTLY-sorted rows. The structured
    # array is rounded to the per-column tolerance grid so a faithful build yields
    # EQUAL digests for both sides; this is a convenience fingerprint -- the binding
    # evidence is `all_columns_match` + `max_joint_paired_abs_diff` above. The
    # signed-zero normalization (`+ 0.0`) is applied HERE ONLY, for the cosmetic
    # digest, so two byte-different-but-equal-valued zeros do not split it.
    def _digest(cols):
        h = hashlib.sha256()
        n = cols[COL_ORDER[0]].size
        perm = _joint_sort(cols) if n else np.empty(0, dtype=np.intp)
        for name in COL_ORDER:
            arr = cols[name][perm].astype(np.float64)
            r = np.round(arr / qstep[name]) * qstep[name] + 0.0
            h.update(name.encode())
            h.update(r.tobytes())
        return h.hexdigest()

    digest_r = _digest(r_cols) if (lengths_ok and reparse_n == stored_n) else "len-mismatch"
    digest_s = _digest(s_cols) if (lengths_ok and reparse_n == stored_n) else "len-mismatch"

    checks.append({
        "name": "determinism_reparse",
        "assumption": ("re-walking December day {0} / {1} through the ORIGINAL "
                       "build_quickwin_markouts.parse_day reproduces the stored npz "
                       "slice (row count + WHOLE-ROW joint multiset of the "
                       "load-bearing columns)").format(REPARSE_DAY, REPARSE_COIN),
        "method": ("bq.parse_day -> bq.compute_markouts_all, then compare (1) row count "
                   "and (2) the JOINT-TUPLE multiset over the load-bearing columns "
                   "(entry_px, mo1/mo10/mo60, start_pos, taker_side): both sides are "
                   "lexsorted by the SAME tolerance-quantized key over ALL columns and "
                   "compared ROW-BY-ROW, so cross-column row-pairing is preserved and a "
                   "row-assembly scramble cannot pass; rows are NOT keyed by taker_id "
                   "(global in the npz, local on a standalone re-parse)"),
        "observed": {
            "reparse_day": REPARSE_DAY, "reparse_coin": REPARSE_COIN,
            "stored_rows": stored_n, "reparse_rows": reparse_n, "count_match": count_match,
            "hours_reparsed": len(hours_ok),
            "columns": col_report,
            "all_columns_match": all_cols_ok,
            "comparison": "joint-tuple lexicographic multiset (row-paired)",
            "reparse_joint_sha256": digest_r[:16],
            "stored_joint_sha256": digest_s[:16],
        },
        "verdict": "confirmed" if ok else "refuted",
        "note": ("re-parse reproduced the stored day/coin slice exactly: identical row "
                 "count and an identical WHOLE-ROW joint multiset over every load-bearing "
                 "column (NaN counts match) -> the stored npz IS a deterministic product "
                 "of parse_day" if ok else
                 ("row count differs ({0} vs {1})".format(reparse_n, stored_n)
                  if not count_match else
                  "row count matches but the joint-tuple multiset differs -> the stored "
                  "npz is NOT a faithful deterministic product of parse_day (a per-column "
                  "compare could have missed a cross-column row scramble; the joint "
                  "compare catches it)")),
    })


# ---------------------------------------------------------------------------
def main():
    started = artifact.start_clock()
    smoke = "--smoke" in sys.argv
    checks = []

    # HARD asserts first (raise on mismatch; local npz only, runs under --smoke too)
    hard_asserts(checks)
    check_rowcounts(checks)
    check_panel_breakdown(checks)
    check_alignment(checks)
    check_determinism(checks, smoke)

    overall = _worst([c["verdict"] for c in checks])

    # JSON-serialise (numpy scalars -> native)
    def _clean(o):
        if isinstance(o, dict):
            return {k: _clean(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [_clean(v) for v in o]
        return _to_native(o)

    result = {"check": CHECK_NAME, "checks": _clean(checks),
              "overall_verdict": overall, "smoke": smoke}
    # The parser source is an input alongside the three slices, because the
    # determinism leg re-parses a day THROUGH it: a change in that file moves the
    # answer exactly as a change in the data would.
    artifact.write(
        os.path.basename(OUT_JSON), result,
        script=__file__,
        inputs=[QUICKWIN, QUICKWIN_MID, PANEL, BUILD_SRC],
        scope={
            "population": "the row counts of the three markout slices named in "
                          "inputs, plus one re-parsed day compared against the "
                          "stored slice of it",
            "window": "the span each slice carries; the determinism leg re-parses "
                      "one day of it"
                      + (" (--smoke: the re-parse is shortened)" if smoke else ""),
            "coins": "every coin present in the slices; the counts are compared "
                     "per coin and are not restricted to one",
        },
        started=started,
    )

    confirmed = sum(1 for c in checks if c["verdict"] == "confirmed")
    refuted = sum(1 for c in checks if c["verdict"] == "refuted")
    uncertain = sum(1 for c in checks if c["verdict"] == "uncertain")
    print("[chk_rowcounts_determinism] overall={0} | confirmed={1} refuted={2} "
          "uncertain={3} | smoke={4} -> {5}".format(
              overall, confirmed, refuted, uncertain, smoke,
              os.path.basename(OUT_JSON)))
    # A refutation here says re-parsing a day does not reproduce the stored slice,
    # which is the reproducibility claim in miniature: a newcomer runs it and gets the same
    # numbers. It stops the run, and it names the row count expected against the row
    # count found rather than the word "refuted" on its own.
    return report_contract(result, OUT_JSON,
                           inputs={"quickwin": QUICKWIN, "panel": PANEL,
                                   "mode": "smoke" if smoke else "full"})


if __name__ == "__main__":
    sys.exit(main())
