"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-20
References: Hyperliquid node-data S3 archive (s3://hl-mainnet-node-data, node_fills_by_block);
Zenodo 18184441 (Albers et al. 2026); validated December pipeline build_quickwin_markouts.py.
"""

# ---------------------------------------------------------------------------
# PANEL ORCHESTRATOR  (the heavy producer).
#
# This EXTENDS the validated December trade-print pipeline
# (build_quickwin_markouts.py) to a fixed multi-month panel and to a third coin
# (SOL). It re-runs the SAME HARDENED download, the SAME parse + sweep-collapse,
# and the SAME native-block_time trade-print markout at 1/10/60s - reused
# VERBATIM from build_quickwin_markouts; nothing about the markout is
# re-derived here. Each output row is tagged with two new keys:
#
#   period  int64   YYYYMM of the window the row belongs to (e.g. 202512)
#   coin    int8    the coin code (BTC=0, ETH=1, SOL=2; from the reused map)
#
# and persisted into panel_markouts.npz with EXACTLY the quickwin_markouts.npz
# columns PLUS the new 'period' column. The four downstream writers
# (ks2_persistence_10day, i2_walletfe, i3_nonrecoverability_oos, t3_capacity)
# code against that quickwin schema, so the panel only ADDS a column; it never
# renames or drops one.
#
# THIS BUILDER NO LONGER WRITES panel_markouts.npz. It writes
# panel_markouts_legacy3w.npz, and the rename is the point of this paragraph.
#
# Both this file and panel_persistence.py --build used to emit panel_markouts.npz, and
# they do not produce the same file. A _builder field was added to both to close that,
# and stamping did not close it, for two reasons that are worth stating because the
# same repair will be reached for again. First, a stamp only reaches a file that is
# REBUILT: the artifact on disk was written before the stamping existed, np.load shows
# it carries the fifteen data columns and no underscore field at all, and re-stamping
# it means a fresh multi-day pull from S3. Second, and worse, a stamp is a record after
# the event. While both writers aim at one path, a run of this legacy builder REPLACES
# the canonical file in place, and every consumer that needs a cross-month wallet join
# then reads ids that cannot support one -- silently, because the columns and dtypes are
# identical. A distinct name makes that impossible instead of detectable, so this file
# takes its own and panel_persistence.py keeps panel_markouts.npz.
#
# The on-disk panel_markouts.npz is panel_persistence.py's, and it says so without any
# stamp: `period` sits fourth in its key order where this builder puts it last, it
# carries all eight windows where this builder's PANEL_WINDOWS is three, and its rows
# run coin-major (2 coin changes against 23 period changes over 26,035,902 rows) where
# this builder's merge is period-major. panel_persistence.identify_builder() is the
# function that reads those three properties back.
#
# What THIS file produces, and how it differs, field by field:
#
#   * WINDOWS: three (PANEL_WINDOWS = 202508 / 202510 / 202512), and merge_panel
#     only takes the cells built in the same run. panel_persistence.py assembles
#     EVERY shard present in panel_ckpt/, which is all eight windows of its
#     PERIOD_DAYS. A file with 26,035,902 rows cannot have come from here.
#   * KEY ORDER: the same fifteen names, with `period` LAST (PANEL_COLUMNS =
#     QUICKWIN_COLUMNS + ("period",)). panel_persistence.py writes `period` fourth.
#     Same names, same dtypes, different order, so the two files are not
#     byte-equivalent even on identical input.
#   * ROW ORDER: period-major (for each window, BTC then ETH then SOL).
#     panel_persistence.py is coin-major, because it concatenates shards in
#     sorted-filename order.
#   * WALLET IDENTITY - the material difference, and a defect of this path. Shards
#     here store only the PER-CELL integer code, not the wallet hex, so merge_panel
#     can only build a global id from the (period, coin, per-cell code) composite.
#     That composite is unique per wallet WITHIN a cell and different for the same
#     wallet in another cell, so a wallet that trades in August and December gets
#     two ids and the cross-month join is impossible from this output.
#     panel_persistence.py keeps the hex in its shards and codes first-seen over the
#     hex across all of them, so one wallet carries one code everywhere - which is
#     what the cross-month persistence analysis and the wallet-level hold-out both
#     require. Anything that holds out a WALLET must read the other builder's file.
#   * COMPANION FILE: panel_persistence.py also writes panel_taker_map.json (hex ->
#     code). This path writes none, so its integer ids cannot be traced to a wallet
#     at all. It writes panel_build_manifest.json instead, which the other does not.
#
# The two are deliberately NOT merged, and the wallet-identity line above is why a
# parameter on one producer would not serve either. The two paths differ in what their
# SHARDS keep: panel_ckpt/ shards hold the wallet hex, panel_cells/ shards hold only a
# per-cell integer, so the global coding is not a switch this file could be given -- the
# key it would need was thrown away before the merge. Merging them means rewriting this
# file's checkpoint format, which is the same as deleting it, and it is kept as the
# legacy record of the first panel pull. Both dtypes agree (`period` int64 in both), so
# the manifest's schema note below is accurate for either.
#
# PANEL WINDOW as this legacy path defines it: coins {BTC, ETH, SOL} x three
# 10-day windows
#   2025-08-04 .. 2025-08-13   period 202508
#   2025-10-06 .. 2025-10-15   period 202510
#   2025-12-04 .. 2025-12-13   period 202512
# = 9 coin-month cells, 90 coin-days. node_fills_by_block coverage starts
# 2025-07-27, so all three windows are present.
#
# SUPERSEDED. The panel actually on disk is EIGHT windows {202508, 202509, 202510,
# 202511, 202512, 202601, 202603, 202605} x the same three coins = 24 cells and
# 26,035,902 rows, built by panel_persistence.py --build and re-pulled with two
# extra columns by panel_rebuild_v2.py. Read the window list from PERIOD_DAYS in
# panel_persistence.py, which is the live definition; the three windows above are
# the original set the reported cross-month analysis still pins to. DATA SOURCE is
# node_fills_by_block ONLY (trade-print markout on the native nanosecond
# block_time); l2Book / book-mid is a documented FOLLOW-ON and is NOT touched
# in this panel run.
#
# WHY A SEPARATE ORCHESTRATOR (not a re-run of build_quickwin_markouts):
#   * build_quickwin_markouts processes ONE 10-day December window in a single
#     in-memory pass and writes the whole npz at the end. The panel is 9x bigger
#     and a transient drop at hour 3 of cell 7 must NOT discard the first six
#     cells. So this orchestrator CHECKPOINTS per (coin, month) cell: each cell
#     writes its own shard + a marker, and a re-run SKIPS any cell already done.
#   * a transient internet drop ONCE silently mislabeled Dec 11-13 as MISSING in
#     the original December run. We therefore inherit the HARDENED download_day
#     (retry x3, per-day hourly-file-count assert, ls-confirm-empty before
#     declaring a gap) directly from build_quickwin_markouts - NOT a weaker
#     hand-rolled copy - and additionally assert each resolved cell is non-empty
#     and records how many of its 10 days actually resolved.
#
# CHECKPOINTING (per coin-month cell):
#   panel_cells/<coin>_<period>.npz       per-cell shard (quickwin schema + period)
#   panel_cells/<coin>_<period>.done.json per-cell marker (row count, days resolved)
#   A cell whose marker exists is SKIPPED on re-run (no S3 re-pull). After all
#   requested cells are present, the shards are concatenated into
#   panel_markouts.npz and panel_build_manifest.json is written.
#
# DISK: stream-and-discard. parse_day already rmtree's each day's raw .lz4 after
# parsing it; this orchestrator holds only ONE cell's collapsed arrays in memory
# at a time and frees them after the shard is written, to stay within ~19 GB
# free disk across the 90 coin-days.
#
# SMOKE OVERRIDE (for the reviewer): a SINGLE (coin, single-day) cell can be run
# without the full 90-cell pull, via env or argparse:
#   PANEL_SMOKE_COIN=BTC PANEL_SMOKE_DAY=20251204 \
#     uv run --no-project --with-requirements requirements.txt python3 data/panel_build.py
#   or
#   uv run --no-project --with-requirements requirements.txt python3 data/panel_build.py \
#     --smoke-coin BTC --smoke-day 20251204
# The smoke run writes a smoke shard + manifest only; it does NOT overwrite the
# real panel_markouts.npz.
#
# GUARDS (inherited + panel-level):
#   * markout sign: positive = taker profited = maker adverse-selected (the
#     compute_markouts_all convention, reused unchanged).
#   * vectorised only: bincount / reduceat / argsort / analytic-CLT CIs - NO
#     per-trade x1000 bootstrap loops (they hang). The only cross-cell test here
#     (a per-cell mean-markout label-permutation null with p-floor 1/(N+1), then
#     BH-FDR across the 9 cells) is fully vectorised.
#   * seeds declared in a header constant (RNG_SEED) and re-asserted onto the
#     reused module so any incidental randomness is deterministic.
#   * reproducibility: no hardcoded /Users paths (HERE = dirname(abspath(file));
#     data root overridable by env/argparse); only os.path.basename is written
#     into the manifest JSON; numpy + stdlib (+ aws / lz4 CLI via the reused
#     download) only.
#
# Run command (bare python3 is BLOCKED on this machine):
#   uv run --no-project --with-requirements requirements.txt python3 data/panel_build.py
# Do NOT run the full 90-cell pull inline; it is a background step. The reviewer
# runs a 1-cell smoke only.
# ---------------------------------------------------------------------------

import argparse
import json
import os
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

import artifact
import settings as H
import stats

# Reuse the validated December pipeline VERBATIM. We import the hardened
# download, the parse + sweep-collapse, the native-block_time markout, and the
# coin map; we do NOT re-derive any of that logic here.
import build_quickwin_markouts as bqm

# -------------------- panel configuration (the fixed SPEC) --------------------
# Each window is a 10-day inclusive range; period = int YYYYMM. Days are the
# YYYYMMDD strings download_day / parse_day expect.
PANEL_WINDOWS = (
    # (period, [YYYYMMDD, ...])  -- 10 days each, inclusive.
    (202508, [f"202508{d:02d}" for d in range(4, 14)]),    # 2025-08-04..08-13
    (202510, [f"202510{d:02d}" for d in range(6, 16)]),    # 2025-10-06..10-15
    (202512, [f"202512{d:02d}" for d in range(4, 14)]),    # 2025-12-04..12-13
)

# Coins in the panel, ordered by their code in the PANEL space. The map belongs to the
# FILE this builder writes (panel_markouts.npz carries {0, 1, 2} where the quickwin
# artifact carries {0, 1}), so both the list and SOL's code are read from that one
# declaration; SOL is still added ADDITIVELY below so the reused parse_day yields all
# three without touching the BTC/ETH codes.
PANEL_COINS = tuple(sym for _, sym in sorted(H.coin_labels("panel").items()))
SOL_CODE = H.coin_codes("panel")["SOL"]   # additive extension; BTC=0, ETH=1 preserved

# Fixed seed: re-assert the reused module's seed so any incidental randomness in
# the parse stays deterministic, and seed our own permutation null. Read from
# settings rather than typed; the value there is the one this file already carried,
# so adopting the declaration changes nothing this file computes.
RNG_SEED = H.MASTER_SEED                 # 20260620

# The name this builder stamps into the file it writes, so the artifact answers
# "which of the two builders made me" without anyone having to compare key orders.
BUILDER_NAME = ("panel_build.py (legacy orchestrator; three windows, period-major; "
                "writes panel_markouts_legacy3w.npz, never panel_markouts.npz)")
BUILDER_WALLET_ID_SCOPE = (
    "taker_id and maker_id are coded from a (period, coin, per-cell code) COMPOSITE, "
    "because the shards this path writes keep only the per-cell integer and not the "
    "wallet hex. A wallet therefore carries a DIFFERENT id in each coin-month cell, "
    "so this file supports no cross-month or cross-coin wallet join and no "
    "wallet-level hold-out. panel_persistence.py --build codes first-seen over the "
    "wallet HEX across all shards and does support both; read its file for anything "
    "that holds out a wallet rather than a row.")
BUILDER_ROW_ORDER = ("period-major: for each window, BTC then ETH then SOL. "
                     "panel_persistence.py's assemble is coin-major.")

HORIZONS_S = bqm.HORIZONS_S              # (1, 10, 60), reused
NS_PER_S = bqm.NS_PER_S

# Draws in the per-cell label-permutation null. Read from settings; the value there
# is the 2000 this file's own default already used, so nothing it computes moves.
CELL_PERM_DRAWS = H.N_PERM               # 2000, p floored at 1/2001

# Window-bearing manifest field names, BUILT and never typed. The per-cell record
# used to spell them mo1_mean_bps / mo60_mean_bps / perm_pvalue_mo60, naming the
# window through an npz column name. That is the spelling settings.py exists to
# stop: the window then travels as part of a string a reader has to decode, and a
# file that switched columns would keep the old name. The permutation null is run
# on the COMPANION window, which these names now state.
def _f(base, h):
    return H.field_name(base, h)


K_MEAN_BPS = {h: _f("markout_mean_bps", h) for h in H.LADDER_S}
PERM_WINDOW_S = H.COMPANION_HORIZON_S    # the window the cell-level null is run on
K_PERM_STAT = _f("perm_stat", PERM_WINDOW_S)
K_PERM_P = _f("perm_pvalue", PERM_WINDOW_S)
K_PERM_Q = _f("perm_qvalue_bh", PERM_WINDOW_S)

# H.fingerprint asserts a MIGRATING declaration only when the caller states what its
# run used, so a script still on 200 draws cannot stamp the declared 2000 into its own
# artifact. This file uses the declared master seed and 2000 permutation draws; it
# bootstraps nothing and ranks on no fill floor, and says so rather than leaving those
# two to read as unanswered.
SETTINGS_OVERRIDES = {"master_seed": RNG_SEED, "n_perm": CELL_PERM_DRAWS,
                      "settings_not_used": ["n_boot", "rank_floor_fills"]}

HERE = os.path.dirname(os.path.abspath(__file__))
# Data root: where per-cell shards / markers / manifest land. Overridable so a
# reviewer can point the panel at a scratch dir without editing the file. Never
# a hardcoded /Users path.
DATA_ROOT = os.environ.get("PANEL_DATA_ROOT", HERE)
CELL_DIR = os.path.join(DATA_ROOT, "panel_cells")
# A NAME OF ITS OWN, and this is the whole repair for the two-writer collision at the
# head of this file. The canonical panel_markouts.npz belongs to panel_persistence.py
# --build; this builder cannot overwrite it, so a legacy run can no longer replace a
# file whose wallet ids support the cross-month join with ids that do not.
PANEL_NPZ_NAME = "panel_markouts_legacy3w.npz"
PANEL_NPZ_PATH = os.path.join(DATA_ROOT, PANEL_NPZ_NAME)
MANIFEST_NAME = "panel_build_manifest.json"
MANIFEST_PATH = os.path.join(DATA_ROOT, MANIFEST_NAME)

# The exact quickwin_markouts.npz column set the four downstream writers read.
# The panel preserves ALL of these and appends 'period'. Kept as an explicit
# list so the shard <-> merge contract is auditable and a future schema drift in
# the producer is caught by the assert in _save_cell_shard.
QUICKWIN_COLUMNS = (
    "taker_id", "coin", "day", "entry_px",
    "mo1", "mo10", "mo60", "notional",
    "is_open", "start_pos", "taker_side",
    "closed_pnl", "dir_code", "maker_id",
)
PANEL_COLUMNS = QUICKWIN_COLUMNS + ("period",)

# Rough per-coin-day egress note (S3 requester-pays). node_fills_by_block hourly
# is ~order-of-GB per coin-day across all coins in a day; we report the count of
# coin-days actually pulled and a coarse per-day estimate so the manifest carries
# an auditable egress figure without pretending to a precise byte count.
APPROX_GB_PER_DAY_ALLCOINS = 1.2         # coarse; node_fills hourly, all coins, one day


# -------------------- additive coin-map extension --------------------
def ensure_panel_coins():
    """Additively register every PANEL_COINS coin in the reused module's maps.

    build_quickwin_markouts.COIN_CODE ships {BTC:0, ETH:1}. parse_day builds its
    per-coin accumulators from bqm.COINS and emits the codes in bqm.COIN_CODE, so
    to make the reused parser yield SOL we extend BOTH maps in place WITHOUT
    disturbing the existing BTC/ETH codes. SOL takes the fixed code 2; any other
    panel coin not already present is appended at the next free code.
    """
    if "SOL" not in bqm.COIN_CODE:
        bqm.COIN_CODE["SOL"] = SOL_CODE
    for c in PANEL_COINS:
        if c not in bqm.COIN_CODE:
            bqm.COIN_CODE[c] = max(bqm.COIN_CODE.values()) + 1
    # bqm.COINS is the tuple parse_day iterates to build its accumulators; make
    # sure every panel coin is in it (additive; preserves order of the originals).
    existing = tuple(bqm.COINS)
    extra = tuple(c for c in PANEL_COINS if c not in existing)
    if extra:
        bqm.COINS = existing + extra
    # re-assert the deterministic seed on the reused module and locally.
    bqm.RNG_SEED = RNG_SEED
    np.random.seed(RNG_SEED)


# -------------------- BH-FDR across cells --------------------
# The step-up correction this file used to define itself now comes from stats.py, and
# the move costs no number: stats._legacy_bh_vectorised is a copy of the spelling that
# stood here, and the self-test in that module runs both against its own on 200 random
# families including ties and untestable cells and asserts identical q. What the module
# adds is the THRESHOLD the q-values were judged against, which no local copy returned
# and which a verdict cannot be read without: alpha/m depends on the family size, and
# across this work that size runs from 4 to 448.


def cell_permutation_pvalue(mo60, taker_side, n_perm=CELL_PERM_DRAWS):
    """Label-permutation p-value for the cell mean companion-window markout.

    Null: the taker-aggressor side carries no markout signal, so shuffling the
    side label leaves the side-signed cell mean at zero in expectation. Statistic
    = |mean over the cell of (2*side-1) * mo60|. We permute the side label
    n_perm times in ONE matrix op (no per-trade loop) and compare. p uses the
    1/(N+1) floor so a permutation null can never report exactly zero.

    Returns (observed_stat, pvalue). NaN/empty cells -> (nan, None).
    """
    m = np.asarray(mo60, dtype=np.float64)
    s = np.asarray(taker_side, dtype=np.float64)
    finite = ~np.isnan(m)
    m = m[finite]
    s = s[finite]
    n = m.size
    if n == 0:
        return float("nan"), None
    sign = 2.0 * s - 1.0                      # side in {0,1} -> {-1,+1}
    obs = abs(float(np.mean(sign * m)))
    rng = np.random.default_rng(RNG_SEED)
    # permute the sign labels as a matrix: (n_perm, n). argsort of random keys
    # gives a permutation per row; vectorised, no Python loop over trades.
    keys = rng.random((n_perm, n))
    perm = np.argsort(keys, axis=1)
    perm_stats = np.abs((sign[perm] * m).mean(axis=1))
    # NOT ROUTED THROUGH stats.permutation_p, and the reason is a difference in the
    # counting rather than a preference. This line compares with NO tolerance, where
    # stats.py counts `draw >= observed - tol`. The two are not the same test: a draw
    # that reproduces the observed grouping recomputes the mean through a different
    # summation order and lands one unit in the last place BELOW the observed value, so
    # without the tolerance it counts as not extreme and the p is biased DOWN, towards
    # significance, exactly on the cells where the evidence is thinnest. Adopting the
    # module here would therefore MOVE every per-cell p in the manifest, which is a
    # measured change owed its own recompute and not part of a consolidation. Recorded
    # here rather than repaired quietly, and the repair is one keyword: pass
    # abs_tol=0.0 to keep this arithmetic, or drop it to take the module's.
    #
    # The generator is the second difference and it is one this file owns: the draws
    # come from a literal-seeded np.random.default_rng(RNG_SEED) rather than from a
    # per-cell stream, so every cell draws its keys from one sequence and two cells of
    # the same size share a null. stats.rng derives a stream from the cell identity and
    # would move the p again.
    hits = int(np.sum(perm_stats >= obs))
    pval = (hits + 1) / (n_perm + 1)          # 1/(N+1) floor
    return obs, float(pval)


# -------------------- per-cell shard I/O + checkpoint --------------------
def _cell_paths(coin, period, smoke=False):
    tag = "smoke_" if smoke else ""
    shard = os.path.join(CELL_DIR, f"{tag}{coin}_{period}.npz")
    marker = os.path.join(CELL_DIR, f"{tag}{coin}_{period}.done.json")
    return shard, marker


def _save_cell_shard(coin, period, cols):
    """Write one (coin, period) shard with the quickwin schema + period column.

    `cols` is a dict of the aligned 1-D arrays (already the panel dtypes). We
    assert the quickwin column set is present and complete BEFORE writing, so a
    drift in the reused producer schema fails loudly at the cell that produced it
    rather than silently at the merge.
    """
    missing = [c for c in QUICKWIN_COLUMNS if c not in cols]
    assert not missing, f"cell {coin} {period}: shard missing columns {missing}"
    n = cols["taker_id"].size
    for c in PANEL_COLUMNS:
        assert cols[c].size == n, (
            f"cell {coin} {period}: column {c} len {cols[c].size} != {n} (rows misaligned)"
        )
    shard, _ = _cell_paths(coin, period, smoke=cols.get("_smoke", False))
    np.savez_compressed(shard, **{c: cols[c] for c in PANEL_COLUMNS})


def _load_marker(coin, period, smoke=False):
    _, marker = _cell_paths(coin, period, smoke=smoke)
    if os.path.exists(marker):
        try:
            with open(marker) as fh:
                return json.load(fh)
        except (ValueError, OSError):
            return None
    return None


def build_cell(coin, period, days, smoke=False):
    """Resolve ONE (coin, period) cell: parse each day, markout, tag, shard.

    Reuses bqm.parse_day (hardened download + sweep-collapse) and
    bqm.compute_markouts_all (native-block_time 1/10/60s markout) per day, keeps
    only THIS coin's slice, frees each day's arrays after appending, writes the
    shard, and returns the per-cell manifest record. A day that parse_day reports
    as missing/absent is recorded but does not abort the cell.

    CHECKPOINT: if the marker already exists AND its shard is on disk, the cell is
    SKIPPED (no S3 re-pull) and the stored record is returned with skipped=True.
    """
    shard, marker = _cell_paths(coin, period, smoke=smoke)
    prior = _load_marker(coin, period, smoke=smoke)
    if prior is not None and os.path.exists(shard):
        prior = dict(prior)
        prior["skipped"] = True
        print(f"[panel] CELL {coin} {period}: already done "
              f"({prior.get('rows', '?')} rows) - SKIP")
        return prior

    coin_code = bqm.COIN_CODE[coin]
    cell_addr = []          # raw taker wallet strings (coded to int at cell end)
    cell_maker_addr = []    # raw maker wallet strings or None
    acc = {c: [] for c in (
        "day", "entry_px", "mo1", "mo10", "mo60", "notional",
        "is_open", "start_pos", "taker_side", "closed_pnl", "dir_code",
    )}

    days_resolved = []
    days_missing = []
    day_row_counts = {}
    short_notes = []

    for day in days:
        per_coin, hours_ok = bqm.parse_day(day)
        if per_coin is None:
            days_missing.append(day)
            short_notes.append(f"{day}: parse_day returned MISSING (S3 ls-confirmed)")
            continue
        days_resolved.append(day)
        if len(hours_ok) < 24:
            short_notes.append(f"{day}: {len(hours_ok)}/24 hours")

        d = per_coin.get(coin)
        if d is None or int(d["taker_ts"].size) == 0 or int(d["print_ts"].size) == 0:
            day_row_counts[day] = 0
            short_notes.append(f"{coin} {day}: empty slice")
            # free and continue
            per_coin = None
            continue

        mo = bqm.compute_markouts_all(
            d["taker_ts"], d["taker_px"], d["taker_dir"], d["print_ts"], d["print_px"]
        )
        notional = d["taker_size"] * d["taker_px"]
        n_rows = int(d["taker_ts"].size)
        day_num = int(day[6:8])

        cell_addr.extend(d["taker_addr"].tolist())
        cell_maker_addr.extend(d["maker_addr"].tolist())
        acc["day"].extend([day_num] * n_rows)
        acc["entry_px"].extend(d["taker_px"].tolist())
        acc["mo1"].extend(mo[1].tolist())
        acc["mo10"].extend(mo[10].tolist())
        acc["mo60"].extend(mo[60].tolist())
        acc["notional"].extend(notional.tolist())
        acc["is_open"].extend(d["taker_open"].tolist())
        acc["start_pos"].extend(d["taker_spos"].tolist())
        acc["taker_side"].extend(d["taker_side"].tolist())
        acc["closed_pnl"].extend(d["taker_cpnl"].tolist())
        acc["dir_code"].extend(d["taker_dcode"].tolist())
        day_row_counts[day] = n_rows

        # stream-and-discard: free this day's arrays before the next pull.
        d = None
        per_coin = None

    n = len(cell_addr)

    # integer-code wallets / makers PER CELL (first-seen order). Codes are
    # per-cell-local; the canonical cross-panel wallet identity for the wallet-FE
    # decomposition is rebuilt at merge time so a wallet keeps ONE id across all
    # of its cells (see merge_panel). taker_side guard is preserved as-is.
    taker_id = np.empty(n, dtype=np.int32)
    w2c = {}
    for i, w in enumerate(cell_addr):
        c = w2c.get(w)
        if c is None:
            c = len(w2c)
            w2c[w] = c
        taker_id[i] = c
    maker_id = np.empty(n, dtype=np.int32)
    m2c = {}
    for i, w in enumerate(cell_maker_addr):
        if w is None:
            maker_id[i] = -1
            continue
        c = m2c.get(w)
        if c is None:
            c = len(m2c)
            m2c[w] = c
        maker_id[i] = c

    cols = {
        "taker_id": taker_id,
        "coin": np.full(n, coin_code, dtype=np.int8),
        "day": np.asarray(acc["day"], dtype=np.int16),
        "entry_px": np.asarray(acc["entry_px"], dtype=np.float64),
        "mo1": np.asarray(acc["mo1"], dtype=np.float32),
        "mo10": np.asarray(acc["mo10"], dtype=np.float32),
        "mo60": np.asarray(acc["mo60"], dtype=np.float32),
        "notional": np.asarray(acc["notional"], dtype=np.float32),
        "is_open": np.asarray(acc["is_open"], dtype=np.int8),
        "start_pos": np.asarray(acc["start_pos"], dtype=np.float32),
        "taker_side": np.asarray(acc["taker_side"], dtype=np.int8),
        "closed_pnl": np.asarray(acc["closed_pnl"], dtype=np.float32),
        "dir_code": np.asarray(acc["dir_code"], dtype=np.int8),
        "maker_id": maker_id,
        # int64 to match the canonical builder panel_persistence.py (the artifact
        # on disk is int64); YYYYMM fits either, both readers cast to int64.
        "period": np.full(n, period, dtype=np.int64),
        "_smoke": smoke,
    }

    # HARDENED-cell assert: a resolved cell with days present must not be silently
    # empty. If EVERY requested day resolved yet produced zero rows, that is the
    # exact failure mode the December mislabel created, so we surface it (do not
    # raise; record it as a failed/short cell so the panel run continues).
    cell_failed = None
    if n == 0:
        if days_resolved:
            cell_failed = (
                f"cell {coin} {period}: {len(days_resolved)}/{len(days)} days "
                f"resolved but 0 rows - investigate (coin absent in node_fills?)"
            )
        else:
            cell_failed = (
                f"cell {coin} {period}: 0/{len(days)} days resolved on S3 - "
                f"all days MISSING after hardened retries"
            )
        print(f"[panel] {cell_failed}")

    _save_cell_shard(coin, period, cols)

    # per-cell permutation null + observed mean markouts (vectorised; for the
    # cross-cell BH-FDR assembled at merge time).
    obs_stat, pval = cell_permutation_pvalue(cols["mo60"], cols["taker_side"])

    def _mean(a):
        a = np.asarray(a, dtype=np.float64)
        a = a[~np.isnan(a)]
        return float(np.mean(a)) if a.size else float("nan")

    record = {
        "coin": coin,
        "period": period,
        "rows": int(n),
        "days_requested": len(days),
        "days_resolved": len(days_resolved),
        "days_resolved_list": days_resolved,
        "days_missing": days_missing,
        "day_row_counts": day_row_counts,
        **{K_MEAN_BPS[h]: _mean(cols[H.headline_print_col(h)])
           for h in H.LADDER_S},
        K_PERM_STAT: obs_stat,
        K_PERM_P: pval,
        "short_notes": short_notes,
        "failed": cell_failed,
        "skipped": False,
        "shard": os.path.basename(shard),
    }
    with open(marker, "w") as fh:
        json.dump(record, fh, indent=2)
    print(f"[panel] CELL {coin} {period}: rows={n:,} "
          f"days={len(days_resolved)}/{len(days)} "
          f"{PERM_WINDOW_S}s markout={record[K_MEAN_BPS[PERM_WINDOW_S]]:+.4f} bps")
    return record


# -------------------- merge shards -> panel_markouts.npz --------------------
def merge_panel(records):
    """Concatenate all present cell shards into panel_markouts.npz.

    Re-codes taker_id and maker_id into ids that are unique across the concatenated
    panel, scanning cells in panel order, so two different wallets never share an id.

    THE LIMIT OF THAT, STATED PLAINLY. Shards written by this path store only the
    per-cell integer code, never the wallet hex, so the only key available at merge
    time is the (period, coin, per_cell_code) composite. That composite is unique per
    wallet WITHIN a cell and DIFFERENT for the same wallet in any other cell. So one
    wallet that trades BTC in August and BTC in December receives two ids here, and
    one that trades BTC and ETH in the same month receives two more. The comment
    that used to sit here claimed this "keeps the wallet holdout coherent across
    cells"; it does not, and cannot, because there is nothing in a shard that ties
    the same wallet's two cells together.

    CONSEQUENCE. Anything that holds out a WALLET rather than a row - the
    between-wallet variance decomposition (i2_walletfe), the OOS-by-wallet holdout
    (i3), and the whole cross-month persistence analysis, which requires a wallet to
    clear its fill floor in BOTH months - must read the file written by
    panel_persistence.py --build, which codes first-seen over the wallet hex across
    every shard and does give one wallet one id everywhere. The npz this function
    writes now says so in its own _builder_wallet_id_scope field.
    """
    present = []
    for r in records:
        coin, period = r["coin"], r["period"]
        shard, _ = _cell_paths(coin, period, smoke=False)
        if os.path.exists(shard) and r.get("rows", 0) > 0:
            present.append((coin, period, shard))
    if not present:
        return 0, {}

    parts = {c: [] for c in PANEL_COLUMNS}
    # global wallet identity keyed by (period, coin, per_cell_taker_code).
    global_taker = {}
    global_maker = {}
    g_take_arrs = []
    g_make_arrs = []
    for coin, period, shard in present:
        z = np.load(shard, allow_pickle=False)
        n = int(z["taker_id"].size)
        ccode = int(bqm.COIN_CODE[coin])
        # remap per-cell taker codes to global ids
        local_t = z["taker_id"].astype(np.int64)
        gt = np.empty(n, dtype=np.int32)
        for i in range(n):
            key = (period, ccode, int(local_t[i]))
            gid = global_taker.get(key)
            if gid is None:
                gid = len(global_taker)
                global_taker[key] = gid
            gt[i] = gid
        # remap per-cell maker codes to global ids (-1 stays -1)
        local_m = z["maker_id"].astype(np.int64)
        gm = np.empty(n, dtype=np.int32)
        for i in range(n):
            lm = int(local_m[i])
            if lm < 0:
                gm[i] = -1
                continue
            key = (period, ccode, lm)
            gid = global_maker.get(key)
            if gid is None:
                gid = len(global_maker)
                global_maker[key] = gid
            gm[i] = gid
        g_take_arrs.append(gt)
        g_make_arrs.append(gm)
        for c in PANEL_COLUMNS:
            if c in ("taker_id", "maker_id"):
                continue
            parts[c].append(z[c])

    merged = {}
    for c in PANEL_COLUMNS:
        if c == "taker_id":
            merged[c] = np.concatenate(g_take_arrs)
        elif c == "maker_id":
            merged[c] = np.concatenate(g_make_arrs)
        else:
            merged[c] = np.concatenate(parts[c])

    total = int(merged["taker_id"].size)
    # Provenance, written after the fifteen data columns so their positions do not
    # move for a reader that indexes z.files rather than naming a key. Every one of
    # these starts with an underscore, matching the shard convention, so metadata is
    # distinguishable from data by the name alone.
    np.savez_compressed(
        PANEL_NPZ_PATH, **merged,
        _builder=np.asarray(BUILDER_NAME),
        _builder_wallet_id_scope=np.asarray(BUILDER_WALLET_ID_SCOPE),
        _builder_row_order=np.asarray(BUILDER_ROW_ORDER),
        _builder_windows=np.asarray(json.dumps([p for p, _ in PANEL_WINDOWS])),
        _settings_fingerprint=np.asarray(json.dumps(H.fingerprint(
            h=H.HEADLINE_HORIZON_S, lens="print",
            markout_columns=[H.headline_print_col(h) for h in H.LADDER_S],
            schema=list(PANEL_COLUMNS), **SETTINGS_OVERRIDES))))
    counts = {
        "n_unique_takers": len(global_taker),
        "n_unique_makers": len(global_maker),
        "n_rows_no_maker": int((merged["maker_id"] == -1).sum()),
    }
    return total, counts


# -------------------- manifest --------------------
def write_manifest(records, total_rows, merge_counts, started, smoke=False):
    cells = []
    cross_p = []
    for r in records:
        cells.append({k: v for k, v in r.items() if k != "day_row_counts" or True})
        cross_p.append(r.get(K_PERM_P))
    # BH-FDR across the cells' per-cell permutation p-values (q-values aligned).
    # The whole correction block is kept, not only the q-values: it carries the family
    # it was taken over and the cutoff it applied, and a cell marked significant with
    # neither of those on the page cannot be checked.
    fdr = stats.benjamini_hochberg(
        cross_p, alpha=H.FDR_ALPHA,
        family=f"per-cell {PERM_WINDOW_S}s markout permutation p over the "
               f"{len(cross_p)} coin-month cells of this build")
    for r, q in zip(cells, fdr["q"]):
        r[K_PERM_Q] = q

    failed = [r for r in records if r.get("failed")]
    short = [r for r in records
             if r.get("rows", 0) > 0 and r.get("days_resolved", 0) < r.get("days_requested", 0)]
    total_coin_days = sum(r.get("days_requested", 0) for r in records)
    resolved_coin_days = sum(r.get("days_resolved", 0) for r in records)

    described = {
            "object": "panel orchestrator manifest - node_fills_by_block trade-print markouts",
            "extends": "build_quickwin_markouts.py (validated December pipeline)",
            "data_source": "node_fills_by_block ONLY (native block_time, 1/10/60s trade-print markout)",
            "panel_windows": [
                {"period": p, "days": [d for d in days]} for p, days in PANEL_WINDOWS
            ],
            "coins": list(PANEL_COINS),
            "coin_code": {k: int(v) for k, v in bqm.COIN_CODE.items()},
            "schema": list(PANEL_COLUMNS),
            "schema_note": (
                "exactly the quickwin_markouts.npz columns PLUS int64 'period' "
                "(YYYYMM), with 'period' LAST; downstream writers read the quickwin "
                "subset unchanged. panel_persistence.py, which builds the canonical "
                "panel_markouts.npz, writes the same fifteen names with 'period' "
                "FOURTH, so the two files carry identical columns and dtypes in a "
                "different order and are not byte-equivalent. Since this builder took "
                "a filename of its own the two can no longer overwrite each other"
            ),
            "builder": BUILDER_NAME,
            "builder_wallet_id_scope": BUILDER_WALLET_ID_SCOPE,
            "builder_row_order": BUILDER_ROW_ORDER,
            "markout_sign": "positive = taker profited = maker adverse-selected",
            "rng_seed": RNG_SEED,
            "perm_pfloor": "1/(N+1)",
            "fdr": fdr,
            "smoke_run": smoke,
            "panel_npz_path": PANEL_NPZ_NAME,
            "cell_dir": os.path.basename(CELL_DIR),
    }
    manifest = {
        "cells": cells,
        "total_rows": int(total_rows),
        "merge_counts": merge_counts,
        "coin_days_requested": int(total_coin_days),
        "coin_days_resolved": int(resolved_coin_days),
        "cells_failed": [r["failed"] for r in failed],
        "cells_short": [
            f"{r['coin']} {r['period']}: {r['days_resolved']}/{r['days_requested']} days"
            for r in short
        ],
        "egress_note": (
            f"~{APPROX_GB_PER_DAY_ALLCOINS} GB/day all-coins node_fills hourly (coarse); "
            f"{resolved_coin_days} coin-days resolved across "
            f"{len([r for r in records if not r.get('skipped')])} freshly pulled cells; "
            f"raw .lz4 streamed-and-discarded per day (parse_day rmtree), peak "
            f"disk = one cell's collapsed arrays"
        ),
    }
    # The runtime that used to sit here as a top-level key is gone: artifact.write puts
    # it inside _meta["run"] together with the finishing timestamp and the interpreter,
    # which is the one container a leaf-by-leaf comparison of two runs skips. Two homes
    # for the same number is what makes such a comparison report a difference on every
    # single run and then stop being read.
    #
    # The shards are the inputs and they are named individually rather than as a
    # directory, so a re-run can tell which cells moved. A shard that is not on disk is
    # recorded present=false rather than raising, which is the honest record for a smoke
    # run and for a build stopped part way.
    artifact.write(
        MANIFEST_NAME, manifest,
        script=__file__,
        inputs=[_cell_paths(r["coin"], r["period"], smoke=smoke)[0] for r in records],
        scope={
            "population": (
                f"{int(total_rows)} taker fills over "
                f"{len(records)} coin-month cells, "
                f"{sum(r.get('days_resolved', 0) for r in records)} of "
                f"{sum(r.get('days_requested', 0) for r in records)} coin-days resolved"
                + (" (SMOKE: one cell of one day, not the panel)" if smoke else "")),
            "window": ("smoke run: a single day inside one panel window" if smoke else
                       ", ".join(f"{p} ({days[0]}..{days[-1]})"
                                 for p, days in PANEL_WINDOWS)),
            "coins": sorted({r["coin"] for r in records}),
        },
        settings=dict(
            h=H.HEADLINE_HORIZON_S, lens="print",
            markout_columns=[H.headline_print_col(h) for h in H.LADDER_S],
            windows=[p for p, _ in PANEL_WINDOWS],
            **SETTINGS_OVERRIDES),
        extra_meta=described,
        # Not the default (this script's own directory), because DATA_ROOT is
        # overridable so a reviewer can run an isolated smoke without touching the real
        # checkpoints. The value is never recorded; only the bare name is.
        out_dir=DATA_ROOT,
        started=started)
    return manifest


# -------------------- drivers --------------------
def resolve_smoke(args):
    """Return (coin, period, [day]) for a single-cell smoke run, or None.

    Precedence: argparse --smoke-coin/--smoke-day, then env PANEL_SMOKE_COIN /
    PANEL_SMOKE_DAY. The day must fall inside one of the panel windows so its
    period is unambiguous.
    """
    coin = args.smoke_coin or os.environ.get("PANEL_SMOKE_COIN")
    day = args.smoke_day or os.environ.get("PANEL_SMOKE_DAY")
    if not coin and not day:
        return None
    if not (coin and day):
        raise SystemExit("[panel] smoke run needs BOTH a coin and a day "
                         "(--smoke-coin/--smoke-day or PANEL_SMOKE_COIN/PANEL_SMOKE_DAY)")
    coin = coin.upper()
    if coin not in PANEL_COINS:
        raise SystemExit(f"[panel] smoke coin {coin} not in panel {PANEL_COINS}")
    period = None
    for p, days in PANEL_WINDOWS:
        if day in days:
            period = p
            break
    if period is None:
        allowed = sorted(d for _, days in PANEL_WINDOWS for d in days)
        raise SystemExit(f"[panel] smoke day {day} not in any panel window; "
                         f"choose one of {allowed}")
    return coin, period, [day]


def main():
    ap = argparse.ArgumentParser(
        description="Panel orchestrator: multi-month + SOL trade-print markout panel."
    )
    ap.add_argument("--smoke-coin", default=None,
                    help="single-cell smoke: coin (BTC/ETH/SOL)")
    ap.add_argument("--smoke-day", default=None,
                    help="single-cell smoke: day YYYYMMDD inside a panel window")
    ap.add_argument("--no-merge", action="store_true",
                    help="build cells only; skip the panel_markouts.npz merge")
    args = ap.parse_args()

    t0 = artifact.start_clock()
    os.makedirs(CELL_DIR, exist_ok=True)
    ensure_panel_coins()

    smoke = resolve_smoke(args)
    if smoke is not None:
        coin, period, days = smoke
        print(f"[panel] SMOKE single cell: {coin} {period} day(s)={days}")
        rec = build_cell(coin, period, days, smoke=True)
        manifest = write_manifest([rec], rec.get("rows", 0), {}, t0,
                                  smoke=True)
        print("\n" + "=" * 76)
        print("PANEL SMOKE - SUMMARY")
        print("=" * 76)
        print(f"  cell        : {coin} {period}")
        print(f"  rows        : {rec.get('rows', 0):,}")
        print(f"  days        : {rec.get('days_resolved', 0)}/{rec.get('days_requested', 0)}")
        print(f"  {PERM_WINDOW_S}s mean   : "
              f"{rec.get(K_MEAN_BPS[PERM_WINDOW_S], float('nan')):+.4f} bps")
        if rec.get("failed"):
            print(f"  FAILED      : {rec['failed']}")
        print(f"  manifest    -> {os.path.basename(MANIFEST_PATH)}")
        print(f"  smoke shard -> panel_cells/smoke_{coin}_{period}.npz")
        print("=" * 76)
        return

    print(f"[panel] FULL panel | coins={PANEL_COINS} "
          f"windows={[p for p, _ in PANEL_WINDOWS]}")
    records = []
    for period, days in PANEL_WINDOWS:
        for coin in PANEL_COINS:
            records.append(build_cell(coin, period, days, smoke=False))

    total_rows, merge_counts = (0, {})
    if not args.no_merge:
        total_rows, merge_counts = merge_panel(records)

    manifest = write_manifest(records, total_rows, merge_counts, t0,
                              smoke=False)

    print("\n" + "=" * 76)
    print("PANEL BUILD - SUMMARY")
    print("=" * 76)
    print(f"  cells         : {len(records)} (= {len(PANEL_COINS)} coins x "
          f"{len(PANEL_WINDOWS)} windows)")
    print(f"  coin-days     : {manifest['coin_days_resolved']}/"
          f"{manifest['coin_days_requested']} resolved")
    print(f"  total rows    : {total_rows:,}")
    if manifest["cells_failed"]:
        print(f"  FAILED cells  : {len(manifest['cells_failed'])}")
        for f in manifest["cells_failed"]:
            print(f"     - {f}")
    if manifest["cells_short"]:
        print(f"  SHORT cells   : {'; '.join(manifest['cells_short'])}")
    print(f"  manifest      -> {os.path.basename(MANIFEST_PATH)}")
    print(f"  panel npz     -> {os.path.basename(PANEL_NPZ_PATH)}")
    print(f"  runtime       -> {round(time.time() - t0, 1)}s")
    print("=" * 76)


if __name__ == "__main__":
    main()
