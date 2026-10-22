"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-20
References:
  - Hyperliquid node-data S3 archive (node_fills_by_block/hourly), s3://hl-mainnet-node-data.
  - Avellaneda, M., Stoikov, S. (2008). "High-frequency trading in a limit order book."
    Quantitative Finance 8(3), 217-224.
  - Cartea, A., Jaimungal, S., et al. Toxic-flow / adverse-selection market-making literature.
  - Spearman-Brown reliability; classical errors-in-variables disattenuation;
    Benjamini, Y., Hochberg, Y. (1995) FDR.
  - Zenodo 18184441 (Albers et al. 2026).
"""

# ---------------------------------------------------------------------------
# PANEL CROSS-MONTH PERSISTENCE - the strongest regime-stability evidence.
#
# The December KS2 run (ks2_persistence_10day.py) established that per-counterparty
# idiosyncratic 10s-markout toxicity persists across an EARLY-vs-LATE split WITHIN
# one 10-day December window. A within-month early/late split can still be carried
# by a single slow-moving regime. This panel asks the strictly harder question:
#
#   Does a wallet's toxicity in ONE MONTH predict its toxicity in ANOTHER MONTH
#   (OUT-OF-MONTH, weeks-to-months apart), across a market-structure change?
#
# It EXTENDS the validated December pipeline to three 10-day windows that straddle
# very different conditions, and adds SOL alongside BTC/ETH:
#
#     period 202508 : 2025-08-04 .. 2025-08-13
#     period 202510 : 2025-10-06 .. 2025-10-15   (spans the Oct-10 stress episode)
#     period 202512 : 2025-12-04 .. 2025-12-13   (the original KS2 window)
#   coins {BTC, ETH, SOL} x 3 windows = 9 coin-month cells, 90 coin-days.
#
# SCOPE vs ARTIFACT. Those three are what THIS analysis reads, not what the data
# holds. panel_markouts.npz was later rebuilt to eight windows {202508, 202509,
# 202510, 202511, 202512, 202601, 202603, 202605}, 26,035,902 rows, and _load_panel
# pins CANONICAL_PERIODS below so the committed results keep reproducing. Quote
# 26,035,902 when describing COVERAGE and 10,455,129 when describing a RESULT from
# this file; they are different quantities and the project has confused them before.
# panel_extended.py runs the same estimators over the wider window set and any
# horizon column, writing to its own results file.
#
# DATA SOURCE = node_fills_by_block ONLY (trade-print markout on the native
# nanosecond block_time clock). No l2Book parse, no book-mid here - the book-mid
# refinement is a documented FOLLOW-ON (i4_*), not this run. node_fills coverage
# starts 2025-07-27 so all three windows are present.
#
# This file is BOTH the panel builder AND the cross-month analysis:
#   --build    : parse the 9 coin-month cells into panel_markouts.npz (the December
#                quickwin schema PLUS an int 'period'=YYYYMM column). Per-(coin,month)
#                checkpoint so a failure at hour 3 does not lose hours 1-2; hardened
#                download (retry 3x + per-day hourly-count assert + ls-confirm-empty);
#                stream-and-discard raw lz4 to stay within ~19 GB free disk.
#
# THIS FILE IS NOW THE ONLY WRITER OF panel_markouts.npz. panel_build.py used to emit
# the same filename and does not produce the same file; it now writes
# panel_markouts_legacy3w.npz, so a legacy run can no longer replace the canonical
# artifact in place. That rename is the repair, and stamping was not, for two reasons.
# A _builder field only reaches a file that is REBUILT, and the artifact on disk
# predates the stamping: np.load lists its fifteen data columns and no underscore field
# at all, and re-stamping it costs a fresh multi-day pull from S3. And a stamp records
# an overwrite rather than preventing one, which for two files carrying identical
# columns and dtypes is a warning read after the damage.
#
# identify_builder() below is what answers the question for the file already on disk,
# from the file's own evidence rather than from a stamp it does not carry. What THIS
# builder produces:
#
#   * ALL EIGHT windows of PERIOD_DAYS (202508 .. 202605), because it assembles
#     every shard present in panel_ckpt/. panel_build.py's PANEL_WINDOWS is three
#     windows and its merge only takes the cells of the run that produced them.
#   * key order taker_id, coin, day, PERIOD, entry_px, mo1, mo10, mo60, notional,
#     is_open, start_pos, taker_side, closed_pnl, dir_code, maker_id - `period`
#     fourth. panel_build.py writes the same fifteen names with `period` LAST.
#   * row order coin-major (shard filenames sorted: BTC 202508.. then ETH.. then
#     SOL..). panel_build.py's merge is period-major.
#   * taker_id / maker_id are GLOBAL over the wallet HEX STRING, first seen across
#     every shard, so one wallet has ONE code in every month and coin. This is the
#     property the cross-month join depends on and it is the material difference:
#     panel_build.py keys its ids on a (period, coin, per-cell code) composite, so
#     the same wallet gets a DIFFERENT id in each cell and no cross-month join is
#     possible from its output at all.
#   * a companion panel_taker_map.json (hex -> code), which panel_build.py does not
#     write, so its integer ids cannot even be traced back to a wallet.
#
# The two are NOT merged, and the wallet-identity line is why one producer with a
# parameter would not serve: the difference is in what the SHARDS keep. panel_ckpt/
# shards hold the wallet hex, panel_cells/ shards hold only a per-cell integer, so the
# global coding is not a switch the other file could be given -- the key it needs was
# discarded before its merge ran. This one is the canonical path run_panel.sh uses, and
# the other is kept as the legacy record of the first panel pull.
#   --analyze  : read panel_markouts.npz, compute for each ORDERED period pair (A,B)
#                and POOLED-across-pairs the cross-month Spearman of per-wallet mean
#                10s markout in A vs B (wallets with >= K fills in BOTH months), with
#                split-half reliability + Spearman-Brown disattenuation, a label-
#                permutation null (p-floor 1/(N+1)), BH-FDR across the
#                (period-pair x K) family, and a whale-drop robustness check. Writes
#                panel_persistence_results.json and HONESTLY FLAGS any pair that is a
#                low-volume / low-reliability outlier.
#   (default, no flag) = --build then --analyze.
#
# REUSE (verbatim, single source of truth - do not re-derive):
#   build_quickwin_markouts.py : parse_day / sweep-collapse / markout / taker_side /
#                                COIN_CODE / the HARDENED download_day with retry.
#   ks2_persistence_10day.py   : split-half reliability (Spearman-Brown), the
#                                disattenuated Spearman, permutation null + p-floor
#                                1/(N+1), Benjamini-Hochberg.
#   i3_nonrecoverability_oos.py: whale-drop pattern (drop top-k wallets by notional).
#
# GUARDS: sign convention positive = taker profited = maker adverse-selected;
# vectorized only (bincount / argsort / analytic - NO per-trade x1000 bootstrap
# loops); master seeds in header constants and every randomised statistic drawn
# from a stream derived from its CELL IDENTITY (see cell_rng), so one cell run on
# its own reproduces the same p-value it has inside the full grid; BH-FDR across
# cells; the OOM hold-out is BY WALLET (a wallet must clear K in BOTH months) never
# by row; no hardcoded /Users paths; only os.path.basename written into the JSON.
#
# Run (bare python3 is BLOCKED on this machine):
#   uv run --no-project --with-requirements requirements.txt python3 data/panel_persistence.py --build
#   uv run --no-project --with-requirements requirements.txt python3 data/panel_persistence.py --analyze
# The full 90-cell pull is a SEPARATE background step; the reviewer does a 1-cell smoke.
# ---------------------------------------------------------------------------

import argparse
import hashlib
import itertools
import json
import os
import shutil
import sys

import numpy as np

# The shared modules sit in the repository root, one directory up from this
# group, and this file also imports from the persistence group. Both are built from this
# file's own location and never from the working directory the run happens to
# start in.
_CODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_CODE_DIR, os.path.join(_CODE_DIR, "persistence")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import artifact
import panel_io as P
import settings as H
import stats

# Reuse the validated December builder verbatim (parse, markout, hardened download,
# coin map). We extend its module-level config ADDITIVELY (SOL, periods) without
# editing the source file, so the BTC/ETH numbers stay byte-identical to KS2.
import build_quickwin_markouts as bq

# -------------------- panel configuration (the fixed panel window) --------------------
# Three 10-day windows x {BTC, ETH, SOL}. period = int YYYYMM. The day labels in the
# npz stay day-of-month (4..15) exactly as the December schema; `period` disambiguates.
PERIOD_DAYS = {
    202508: ["20250804", "20250805", "20250806", "20250807", "20250808",
             "20250809", "20250810", "20250811", "20250812", "20250813"],
    202509: ["20250904", "20250905", "20250906", "20250907", "20250908",
             "20250909", "20250910", "20250911", "20250912", "20250913"],
    202510: ["20251006", "20251007", "20251008", "20251009", "20251010",
             "20251011", "20251012", "20251013", "20251014", "20251015"],
    202511: ["20251104", "20251105", "20251106", "20251107", "20251108",
             "20251109", "20251110", "20251111", "20251112", "20251113"],
    202512: ["20251204", "20251205", "20251206", "20251207", "20251208",
             "20251209", "20251210", "20251211", "20251212", "20251213"],
    202601: ["20260104", "20260105", "20260106", "20260107", "20260108",
             "20260109", "20260110", "20260111", "20260112", "20260113"],
    202603: ["20260304", "20260305", "20260306", "20260307", "20260308",
             "20260309", "20260310", "20260311", "20260312", "20260313"],
    202605: ["20260504", "20260505", "20260506", "20260507", "20260508",
             "20260509", "20260510", "20260511", "20260512", "20260513"],
}
PERIODS = tuple(sorted(PERIOD_DAYS))          # all 8 build windows now: 202508, 202509,
                                              # 202510, 202511, 202512, 202601, 202603,
                                              # 202605 (PERIOD_DAYS was extended past the
                                              # original 3). --build can populate any of
                                              # them; the ANALYSIS is pinned below.
# The paper reports the Aug/Oct/Dec 3-window cross-month panel. panel_markouts.npz was
# later rebuilt to hold all 8 windows, so _load_panel restricts the loaded fills to these
# three so a re-run reproduces the committed panel_persistence_results.json.
CANONICAL_PERIODS = (202508, 202510, 202512)
# Coins in the panel, ordered by their code in the PANEL space. The map belongs to the
# FILE (panel_markouts.npz carries {0, 1, 2}, the quickwin artifact {0, 1}), so the list
# and SOL's code come from that one declaration rather than being typed here.
PANEL_COINS = tuple(sym for _, sym in sorted(H.coin_labels("panel").items()))
SOL_CODE = H.coin_codes("panel")["SOL"]        # additive; BTC=0, ETH=1 preserved


def ensure_panel_coins():
    """Additively register every PANEL_COINS coin in the REUSED module's maps.

    THE PANEL-SOL BUG THIS FIXES: bq.parse_day filters the node_fills tape on the
    MODULE-LEVEL tuple bq.COINS. It builds its per-coin accumulators with
    `{c: {} for c in COINS}` and then drops every fill whose `coin` is not already
    a key (`if coin not in print_ts_by_hash: continue`), and finally emits per_coin
    ONLY for `for c in COINS`. bq.COIN_CODE is NOT read inside parse_day at all
    (it is used only in bq.main()). So extending a LOCAL copy of bq.COIN_CODE - as
    this file used to do - never reaches parse_day, and SOL came back as 0 rows in
    every window even though SOL trades exist on the tape (panel_build.py's smoke
    found 62,830 SOL rows on 2025-08-04).

    The fix is to inject SOL into bq.COINS (the tuple parse_day iterates) BEFORE any
    parse_day call, additively, never disturbing the existing BTC=0/ETH=1 codes or
    the byte-identical December artefacts. We also keep bq.COIN_CODE in sync (so
    bq.main() and any code reading bq.COIN_CODE see the same SOL=2), even though
    parse_day itself does not consume it. Idempotent: safe to call more than once.
    """
    if "SOL" not in bq.COIN_CODE:
        bq.COIN_CODE["SOL"] = SOL_CODE
    for c in PANEL_COINS:
        if c not in bq.COIN_CODE:
            bq.COIN_CODE[c] = max(bq.COIN_CODE.values()) + 1
    # bq.COINS is the tuple parse_day iterates to build its accumulators AND the
    # set it filters fills against (line `if coin not in print_ts_by_hash`); make
    # sure every panel coin is in it (additive; preserves the original order).
    existing = tuple(bq.COINS)
    extra = tuple(c for c in PANEL_COINS if c not in existing)
    if extra:
        bq.COINS = existing + extra


# Inject SOL into the reused builder's coin globals at import time, so EVERY
# bq.parse_day call (smoke or full build) extracts SOL alongside BTC/ETH.
ensure_panel_coins()

# Keep PANEL_COIN_CODE consistent with bq's (now-extended) map. Built AFTER the
# injection so SOL=2 is present; BTC=0/ETH=1 stay untouched.
PANEL_COIN_CODE = dict(bq.COIN_CODE)          # {"BTC":0,"ETH":1,"SOL":2}
for _c in PANEL_COINS:
    if _c not in PANEL_COIN_CODE:
        PANEL_COIN_CODE[_c] = max(PANEL_COIN_CODE.values()) + 1
PANEL_COIN_LABEL = {v: k for k, v in PANEL_COIN_CODE.items()}

# -------------------- analysis configuration --------------------
HEADLINE_HORIZON_S = H.HEADLINE_HORIZON_S  # cross-month persistence is read on the
                                           # headline markout, same window the study ranks on

# What the CURRENT run is actually measuring. These start at this file's own
# defaults and exist so that a caller which substitutes _load_panel (panel_extended.py
# does exactly that, to read a different markout column or a book-mid series) can
# say so, and have the scope block of the results file say so too. Before these
# existed the scope block printed the constants regardless, so a 10 s run wrote
# "horizon_s: 60" into its own artifact and a book-mid run described itself as
# trade-print. Anything lifted out of scope was then wrong about the run it came
# from. A substituting caller MUST set all three (the third is below).
ACTIVE_HORIZON_S = HEADLINE_HORIZON_S
ACTIVE_CLOCK_SOURCE = "native block_time (ns), node_fills_by_block (trade-print)"
# The npz column the substituted loader actually read. None = "this file's own
# loader ran", which always reads the mo{HEADLINE_HORIZON_S} column. A caller that
# reads a different column MUST set this. The in-file store key is now the
# horizon-free "mo_score", so it names no window at all and cannot go stale; the
# key name is therefore NOT evidence of what was loaded, and never was.
ACTIVE_MARKOUT_COLUMN = None
# The reference price the loaded column is measured against. This file's own loader
# reads the trade print. A caller substituting a book-mid series MUST set this too:
# without it the descriptive keys would carry the print spelling over mid values,
# which is the same class of defect as a 60 s value under a 10 s name and has
# already happened once in this project (ks2_persistence_10day.py built its
# book-mid key from the print column accessor).
ACTIVE_LENS = "print"


def active_markout_column():
    """Name of the npz column the current run loaded, for LABELLING only.

    WHY THIS EXISTS. The per-period descriptive slice used to emit the literal
    keys "mo60_mean_bps" / "mo60_median_bps" whatever column was loaded, and the
    scope block used to describe the object as "60s" the same way. A 1 s run
    therefore shipped its 1 s means under a name that says 60 s, in a file whose
    scope also said 60 s, and nothing inside the artifact contradicted it. Every
    label that names a horizon now comes from here or from ACTIVE_HORIZON_S.

    Falls back to mo{ACTIVE_HORIZON_S} so a caller that sets only the horizon (the
    contract before this function existed) still gets a truthful label, and asserts
    the two agree when both are set - a mismatch means the loader and the scope
    stamp disagree about the run, which is exactly the defect this closes.
    """
    derived = (H.headline_print_col(ACTIVE_HORIZON_S) if ACTIVE_LENS == "print"
               else H.headline_mid_col(ACTIVE_HORIZON_S))
    if ACTIVE_MARKOUT_COLUMN is None:
        return derived
    if ACTIVE_MARKOUT_COLUMN != derived:
        raise SystemExit(
            f"[panel] scope inconsistency: loader read "
            f"{ACTIVE_MARKOUT_COLUMN!r} but ACTIVE_HORIZON_S={ACTIVE_HORIZON_S} "
            f"implies {derived!r}. Set both to the same run or neither.")
    return ACTIVE_MARKOUT_COLUMN


# Every setting below that settings.py declares is now READ from there rather than
# re-typed, so this file cannot hold a value that disagrees with the declaration.
# Each was checked against what this file used to carry and every one is identical,
# so adopting the declaration moves no number here. The one exception is named
# below and is passed to the fingerprint as an override.
K_POOL = H.PERSISTENCE_FLOOR_FILLS   # (50, 100) min fills in BOTH months of a pair
N_PERM_CORR = H.N_PERM               # 2000 permutation draws (p-floor 1/2001)
WHALE_DROP_K = H.WHALE_DROP_K        # drop top-k wallets by total notional
# MASTER seeds. Neither is used as a single stream: each randomised statistic
# derives its own generator from the master seed PLUS the identity of the cell it
# belongs to (see cell_rng). One shared stream would make every cell's p-value a
# function of its position in the loop.
RNG_RELIABILITY = H.RELIABILITY_SEED  # 20240601, the split-half reliability seed
# The correlation permutation null keeps its OWN seed, which is NOT the declared
# MASTER_SEED. It is an override, not a drift: this value is what every published
# cross-month p-value in panel_persistence_results.json was drawn under, and the
# seed enters through cell_rng, so changing it would move all 96 of them at once
# for no gain. It appears in the fingerprint under corr_seed.
#
# It is now READ from settings.py rather than typed, under the name of the STREAM it
# belongs to and not of this file. That distinction is the reason the map has an entry
# this specific: this file draws two randomised quantities, and the other one binds
# RELIABILITY_SEED above, so a seed named for the file would have to stand for both. The
# value is unchanged, so no published p-value moves.
RNG_CORR_SEED = H.seed_for("panel_persistence_correlation_null")
FDR_ALPHA = H.FDR_ALPHA        # BH level over the (period-pair x K) family

# Honest outlier flags: a pair-cell is flagged a low-power outlier if its
# common-wallet count is thin OR either-month reliability is at/under this floor.
MIN_N_COUNTERPARTIES = H.MIN_COMMON_WALLETS  # 30; below this the Spearman is noise
LOW_RELIABILITY_FLOOR = 0.10   # reliability <= this -> disattenuation is unstable
                               # (a property of the disattenuation step, declared
                               # here because no other file has an opinion on it)

# The settings this file genuinely runs on that differ from the declaration, passed
# to H.fingerprint so a deliberate difference is visible in the artifact instead of
# being indistinguishable from a stale value.
# H.fingerprint asserts a MIGRATING declaration only when the caller states what its
# run used, so this states the ones this run has, and names the ones it has no use
# for instead of leaving them to read as unanswered. There is no master seed in play
# here: the two streams are the reliability seed (in force) and the correlation seed
# below, and nothing in this file bootstraps or ranks on a fill floor.
SETTINGS_OVERRIDES = {"corr_seed": RNG_CORR_SEED,
                      "low_reliability_floor": LOW_RELIABILITY_FLOOR,
                      "n_perm": N_PERM_CORR,
                      "min_common_wallets": MIN_N_COUNTERPARTIES,
                      "settings_not_used": ["master_seed", "n_boot",
                                            "rank_floor_fills"]}

# What a pure BUILD stamps. --build computes no statistic at all: it parses, marks
# out and concatenates, so none of the four migrating declarations applies to it.
BUILD_SETTINGS_OVERRIDES = {
    "settings_not_used": ["master_seed", "n_perm", "n_boot", "rank_floor_fills"]}


def cell_rng(base_seed, *identity):
    """A generator seeded by the CELL'S IDENTITY, never by its position in a loop.

    WHY THIS EXISTS. Every randomised statistic below (the label-permutation null
    and the split-half reliability) used to draw from ONE generator threaded
    through the whole nested loop. With a shared stream the draws a cell receives
    depend on how many draws every earlier cell happened to consume, so the
    p-value of a given cell is a function of the coin order, the pair order, the
    K grid and of whether an optional branch (the whale-drop) fired earlier in the
    run. Add a coin, drop a window, or run one cell on its own to check it, and
    every downstream p-value moves. The point estimates never move, only the
    p-values - which is exactly the failure a reviewer re-running this file sees.

    THE RULE. seed = SHA-256(base_seed | identity fields), folded to 64 bits.
    The identity is the tuple that names the cell, e.g.
    (coin, period_a, period_b, K, statistic-tag), so the seed is a pure function
    of WHICH cell is being computed. Consequences:
      - running one cell alone gives the same p-value as running all of them;
      - adding coins, windows or K values leaves every existing cell untouched;
      - each statistic within a cell carries its own tag, so skipping the
        whale-drop cannot move the headline p-value.
    SHA-256 rather than Python's hash(): hash() of a str is salted per process
    (PYTHONHASHSEED) and would make the seeds differ between runs.
    """
    key = "|".join([str(base_seed)] + [str(p) for p in identity]).encode("utf-8")
    return np.random.default_rng(
        int.from_bytes(hashlib.sha256(key).digest()[:8], "big"))


HERE = os.path.dirname(os.path.abspath(__file__))

# WHICH ENVIRONMENT NAME THIS FILE ANSWERS TO, AND WHY IT IS ONLY ONE OF THE FIVE.
# panel_io.py holds the tree's list of names for "the directory the intermediates live
# in" and honours all five, the first one set winning, so that a script migrated onto it
# keeps speaking whatever name it spoke before. Handing that list over unchanged is the
# tidier call and it is the wrong one here. CONFIG.md records why two of the names exist
# separately -- PANEL_DATA_ROOT and PANEL_V2_DATA_ROOT are "kept separate so the two
# cannot overwrite each other" -- and on the shared list a tree that set
# PANEL_V2_DATA_ROOT alone, to relocate the REBUILT panel, relocates this file's inputs
# on top of it. So the name is one name, the one this file has always answered to and
# the one CONFIG.md assigns it. What comes from panel_io is the part that genuinely
# should have one home: the DEFAULT.
DATA_ROOT_ENV = ("PANEL_DATA_ROOT",)

# Data root for the panel inputs this file reads: the checkpoint shards, the panel npz
# and the taker map. Overridable via PANEL_DATA_ROOT so a reviewer can run an ISOLATED
# single-(coin,day) SOL smoke in a scratch dir without touching the real BTC/ETH
# December checkpoints. Never a hardcoded /Users path.
#
# THE DEFAULT USED TO BE THIS FILE'S OWN DIRECTORY, AND THAT WAS THE DEFECT. The line
# read os.environ.get("PANEL_DATA_ROOT", HERE), and it was right for as long as this
# file sat in the repository root, because then HERE was the root and the root is where
# the data is. When the scripts were sorted into pipeline groups this one went into
# data/ while the two large gitignored intermediates stayed where the builder wrote
# them. The line did not change by one byte; HERE changed under it, and took every
# address built from it along. What the resolvers below then had to do on every run --
# walk the whole repository to correct a guess -- is not free of consequence either: a
# walk finds every copy, so a shortcut left beside a reader made two paths answer to one
# name and the run refused to choose rather than compute.
#
# THE ANSWER HAS ONE HOME AND IT IS panel_io.data_root(), which is the same call
# data/panel_rebuild_v2.py, persistence/three_coin_persistence.py and
# data/step1_inventory.py make to find these very files. The disagreement was never
# about the rule: this file derived its answer from its OWN location while the readers
# derived theirs from panel_io's, and only one of the two moved in August. Asking the
# same question of the same module is what makes them move together from here on.
DATA_ROOT = P.data_root(env_names=DATA_ROOT_ENV)
# Whether that root was ASKED FOR or merely defaulted to, which the line above cannot
# tell apart once it has answered. The two cases must not behave alike. An explicit
# root is an instruction about which panel to read, and the search below is switched
# off under it; a defaulted root is the repository's convention about where the
# intermediates sit, and the search is what corrects it when they are not there.
DATA_ROOT_IS_EXPLICIT = bool((os.environ.get(DATA_ROOT_ENV[0]) or "").strip())

# Directories that hold copies rather than the file itself, or hold no panel at all,
# so a walk descending into them would report an ambiguity that does not exist.
_SKIP_DIRS = {".git", "__pycache__", ".ipynb_checkpoints", "node_modules"}


def _input_root(name):
    """The directory holding the panel input called `name`, found BY NAME.

    THE JOIN THIS REPLACED POINTED BOTH OF THIS FILE'S INPUTS AT A DIRECTORY THAT HOLDS
    NEITHER OF THEM. The two are large gitignored intermediates and they sit at the
    repository root, where the builder that made them ran; this script was later sorted
    into a group directory with the rest of the data stage, and DATA_ROOT then defaulted
    to the script's own directory, so the join went looking one level too deep. Measured
    on the tree: panel_markouts.npz and panel_taker_map.json both answered `exists=False`
    at the joined address while both were on disk one directory up, at 482 MB and 16 MB.

    THAT DEFAULT IS NOW REPAIRED AT ITS BINDING, and this function keeps its job for a
    different reason than the one it was written for. DATA_ROOT comes from
    panel_io.data_root(), which is the address every reader of these two files already
    resolves, so the direct join above hits on an untouched tree and the walk never
    runs. What the walk is for from here on is the tree where it does NOT hit: a
    reviewer who built the panel somewhere else, or a clone where the producer has not
    run yet. Leaving the correction in place while removing the thing it was correcting
    is deliberate, because the walk is also the only thing in this file that would
    NOTICE a second panel appearing beside the first -- and it noticed one: measured on
    2026-08-29, shortcuts left in two group directories made this name answer to two
    paths and the refusal below fired on a tree where nothing was actually ambiguous.

    What that cost is worse than a missing file, because of the order the analysis asks
    its two questions in. `analyze_panel` calls `identify_builder` before `_load_panel`,
    deliberately, so that no number is computed before the builder of the input has been
    established -- and `identify_builder` opens the file with a bare np.load. So a
    default `--analyze` died with `FileNotFoundError: ... panel_markouts.npz` out of
    numpy, and the worded refusal `_load_panel` carries for exactly this case, the one
    that says `run with --build first`, was never reached. The reading a person got was
    that the file is broken rather than that it is elsewhere.

    A name identifies and a path guesses. The direct join is still tried first, because
    it is right whenever nothing has moved and it costs one stat; only then does the
    walk run, and it starts at the REPOSITORY ROOT rather than at this file's directory,
    since the whole defect is that the input is above the searcher and never below it.

    WHY THIS HANDS BACK A DIRECTORY WHERE THE OTHER TWO OF ITS KIND HAND BACK A FULL
    PATH. check_first._resolve and chk_closedpnl._by_name both return the file, and both
    are read-only. This file WRITES the two names it resolves, and the write edges of the
    dependency graph are derived from the syntax tree: the first argument of a write call
    is folded to a constant, and a path that does not fold makes no edge at all. The fold
    keeps only helpers with exactly ONE return, on the ground that a helper with two can
    hand back two different files -- and a by-name resolver has three returns by nature,
    since finding, not finding and refusing are three answers. Binding the constants to
    such a call would therefore have folded to nothing and deleted this file's writes of
    panel_markouts.npz and panel_taker_map.json from the graph, leaving two artifacts
    with no producer anywhere. Returning the DIRECTORY keeps the file name where the fold
    reads it, as the last component of the join at the binding, so the edges survive the
    repair. Measured before and after: the same three writes, the same two unresolved
    reads, both of which are declared by hand and were before.

    Two files answering to one name is refused out loud rather than resolved by taking
    the first. Silently picking one would put a cross-month number in the artifact about
    a panel this file did not name, which is the same class of defect one layer down. It
    is not a hypothetical risk for this name in particular: the header above records that
    panel_markouts.npz had TWO writers emitting the same filename with the same fifteen
    columns and incompatible wallet ids, and the repair was to rename the other one's
    output. Searching by name would revive exactly that collision if a second copy ever
    appeared, so the search refuses instead, and identify_builder still interrogates
    whatever single file it does return. A name that is nowhere returns the conventional
    root, so the caller reports an absent input in its own words instead of this function
    deciding what an absence means.
    """
    if DATA_ROOT_IS_EXPLICIT:
        # An explicit root is the whole point of the isolated smoke: it says READ HERE
        # AND NOWHERE ELSE. Falling through to the search would let a smoke run against
        # an empty scratch directory quietly adopt the real multi-hundred-megabyte panel
        # at the repository root, which is the one outcome the flag exists to prevent.
        return DATA_ROOT
    if os.path.exists(os.path.join(DATA_ROOT, name)):
        return DATA_ROOT
    hits = []
    for dirpath, dirnames, filenames in os.walk(_CODE_DIR):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        if name in filenames:
            hits.append(dirpath)
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        raise SystemExit(
            f"[panel] {name} answers to {len(hits)} files under this repository, in "
            + ", ".join(sorted(os.path.relpath(h, _CODE_DIR) + os.sep for h in hits))
            + ". Refusing to choose: this analysis would report cross-month numbers "
              "about a panel it did not name. Set PANEL_DATA_ROOT to the directory "
              "holding the one to read.")
    return DATA_ROOT


# The names lead and the paths are built from them, rather than the paths leading and
# the names being read back off with basename. The name is the identifier -- it is what
# _input_root is asked for, what the artifact records as its input, and what the fold
# reads off the join -- so it is the thing that should be typed once and stated first.
PANEL_NPZ_NAME = "panel_markouts.npz"
PANEL_NPZ_PATH = os.path.join(_input_root(PANEL_NPZ_NAME), PANEL_NPZ_NAME)
PANEL_TAKER_MAP_NAME = "panel_taker_map.json"
PANEL_TAKER_MAP_PATH = os.path.join(_input_root(PANEL_TAKER_MAP_NAME),
                                    PANEL_TAKER_MAP_NAME)
# The results file is NOT resolved by name, and the difference is the direction it
# travels. The two above are inputs this run has to find wherever the builder left them;
# this one is the output this run creates, and an output has no existing copy to search
# for.
#
# IT ALSO DOES NOT FOLLOW THE INPUTS, and that is the half of the repair that is easy to
# lose. Moving DATA_ROOT off this file's directory and onto the repository's answer is
# right for the inputs, which live where the builder left them, and wrong for the
# output, which is a tracked repository file with a committed address beside the script
# -- the same address run/_groups.py schedules and the same one every consumer opens. A
# root override relocates the OUTPUT as readily as the input, and a run that succeeds
# into a directory nobody reads, leaving the committed copy untouched at its old
# timestamp, reports nothing on the screen to distinguish it from the run that was
# asked for. So the two directions are named separately: the output sits beside the
# script by default, and follows an EXPLICIT root, which is what keeps an isolated smoke
# writing into its own scratch directory exactly as before.
RESULTS_DIR = DATA_ROOT if DATA_ROOT_IS_EXPLICIT else HERE
RESULTS_PATH = os.path.join(RESULTS_DIR, "panel_persistence_results.json")
RESULTS_NAME = os.path.basename(RESULTS_PATH)

def _checkpoint_root(name):
    """The directory holding the checkpoint directory called `name`, found BY NAME.

    THE SAME DEFECT AS THE TWO INPUTS ABOVE, AND THE EXPENSIVE ONE OF THE THREE. The
    join under DATA_ROOT resolved to a directory that does not exist, while panel_ckpt
    with all twenty-four shards sits at the repository root beside the panel those
    shards were assembled into. Measured on the tree: `data/panel_ckpt` exists=False,
    `panel_ckpt` holds 24 shards.

    What it cost, and it is not a missing file this time but a silent redo. A run of
    this script with no flag is build-then-analyze by the header above. `_build_one_period`
    calls os.makedirs(CKPT_DIR, exist_ok=True), so it would have CREATED an empty
    directory at the wrong address, read every one of the twenty-four cells as not-done
    because `_cell_done` asks whether the shard is there, and re-parsed the tape from the
    beginning. The sibling builder prices a full parse at a floor of about 10332 seconds
    and says the floor is generous. The checkpoint exists exactly to make that impossible,
    and pointing it away from the shards disarmed it while leaving it in place, which is
    worse than not having it: a guard that cannot see what it guards still reads as a
    guard.

    Resolved as a DIRECTORY rather than a file, which is why this is a sibling of
    `_input_root` and not a call to it: that one asks whether `name` is among the
    filenames of a walk, and a checkpoint directory is never a filename. Everything else
    is the same and deliberately so -- an explicit root still wins outright, the direct
    address is still tried first, an ambiguity is still refused out loud, and a name that
    is nowhere still hands back the conventional address, which is what lets a first run
    on a fresh clone create the checkpoint where it belongs instead of adopting somebody
    else's.

    One return, so the fold that derives this file's write edges from its syntax tree
    keeps working; the reasoning is written out at `_input_root` and is the same here.
    """
    if DATA_ROOT_IS_EXPLICIT:
        return DATA_ROOT
    if os.path.isdir(os.path.join(DATA_ROOT, name)):
        return DATA_ROOT
    hits = []
    for dirpath, dirnames, filenames in os.walk(_CODE_DIR):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        if name in dirnames:
            hits.append(dirpath)
    if len(hits) > 1:
        raise SystemExit(
            f"[panel] {name} answers to {len(hits)} directories under this repository, "
            "in " + ", ".join(sorted(os.path.relpath(h, _CODE_DIR) + os.sep
                                     for h in hits))
            + ". Refusing to choose: a build would read some cells as done from one of "
              "them and write the rest into it, mixing two panels in one checkpoint. "
              "Set PANEL_DATA_ROOT to the directory holding the one to use.")
    return hits[0] if hits else DATA_ROOT


# Per-cell checkpoint dir: one marker + one .npz shard per (coin, month). A shard
# present means that cell is done; --build SKIPS it so a mid-pull failure never
# re-pulls completed cells. Found by name, for the reason written out just above; an
# explicit PANEL_DATA_ROOT still scopes an isolated smoke to its own directory.
CKPT_NAME = "panel_ckpt"
CKPT_DIR = os.path.join(_checkpoint_root(CKPT_NAME), CKPT_NAME)


# ===========================================================================
# PART 1 - BUILDER (parse the 9 coin-month cells -> panel_markouts.npz)
# ===========================================================================
def _cell_shard_path(coin, period):
    return os.path.join(CKPT_DIR, f"shard_{coin}_{period}.npz")


def _cell_done(coin, period):
    """A cell is done iff its shard .npz exists and loads. (Marker = the shard.)"""
    p = _cell_shard_path(coin, period)
    if not os.path.exists(p):
        return False
    try:
        with np.load(p, allow_pickle=True) as _z:
            _ = _z["taker_addr"]
        return True
    except Exception:
        return False


def _build_one_period(period, days, only_coin=None):
    """Parse every day of one window and write a per-(coin,month) shard for each coin.

    For each day we call build_quickwin_markouts.parse_day (which itself does the
    hardened download_day, sweep-collapse, native-block_time markout, taker_side,
    and stream-and-discard of the raw lz4). Days for a coin are concatenated and
    saved as one checkpoint shard per (coin, period). Re-running SKIPS coins whose
    shard already exists, so a failure at day 3 keeps days 1-2.

    only_coin (e.g. "BTC") limits the smoke run to a single coin's shard; the
    parse still reads all panel coins from the tape but only that coin is written.
    """
    os.makedirs(CKPT_DIR, exist_ok=True)
    coins = PANEL_COINS if only_coin is None else (only_coin,)

    # Which coins of this period still need building?
    pending = [c for c in coins if not _cell_done(c, period)]
    if not pending:
        print(f"[panel] period {period}: all cells present, SKIP "
              f"({', '.join(coins)})")
        return {c: "skipped" for c in coins}

    # accumulate per-coin day columns (only for the pending coins)
    acc = {c: {k: [] for k in
               ("addr", "coin", "day", "entry_px", "mo1", "mo10", "mo60",
                "notional", "is_open", "start_pos", "taker_side", "closed_pnl",
                "dir_code", "maker_addr")} for c in pending}
    hours_by_day = {}
    issues = []
    resolved = []

    for day in days:
        day_num = int(day[6:8])
        per_coin, hours_ok = bq.parse_day(day)     # hardened download + parse inside
        if per_coin is None:
            issues.append(f"{period} day {day} missing on S3 - skipped")
            print(f"[panel] {period} day {day} MISSING on S3 - skipped")
            continue
        resolved.append(day)
        hours_by_day[day] = hours_ok
        if len(hours_ok) < 24:
            issues.append(f"{period} {day}: {len(hours_ok)}/24 hours")

        for coin in pending:
            d = per_coin.get(coin)
            if d is None:
                # With ensure_panel_coins() injecting SOL into bq.COINS, parse_day
                # now yields every panel coin, so this only fires if a coin is
                # genuinely absent from the tape that day (a real, auditable gap).
                continue
            n_trades = int(d["taker_ts"].size)
            if n_trades == 0 or d["print_ts"].size == 0:
                issues.append(f"{coin} {period} {day}: empty")
                print(f"[panel] SLICE {coin} {period} {day}: empty")
                continue
            mo = bq.compute_markouts_all(d["taker_ts"], d["taker_px"], d["taker_dir"],
                                         d["print_ts"], d["print_px"])
            notional = d["taker_size"] * d["taker_px"]
            a = acc[coin]
            a["addr"].extend(d["taker_addr"].tolist())
            a["coin"].extend([PANEL_COIN_CODE[coin]] * n_trades)
            a["day"].extend([day_num] * n_trades)
            a["entry_px"].extend(d["taker_px"].tolist())
            a["mo1"].extend(mo[1].tolist())
            a["mo10"].extend(mo[10].tolist())
            a["mo60"].extend(mo[60].tolist())
            a["notional"].extend(notional.tolist())
            a["is_open"].extend(d["taker_open"].tolist())
            a["start_pos"].extend(d["taker_spos"].tolist())
            a["taker_side"].extend(d["taker_side"].tolist())
            a["closed_pnl"].extend(d["taker_cpnl"].tolist())
            a["dir_code"].extend(d["taker_dcode"].tolist())
            a["maker_addr"].extend(d["maker_addr"].tolist())
            g60 = mo[60][~np.isnan(mo[60])]
            print(f"[panel] SLICE {coin} {period} {day}: trades={n_trades:,} "
                  f"mo60={(float(np.mean(g60)) if g60.size else float('nan')):+.4f}")

    status = {}
    for coin in pending:
        a = acc[coin]
        # Save a shard even if empty so the cell is marked done (an empty window
        # is a real, auditable result, not a reason to keep re-pulling S3).
        np.savez_compressed(
            _cell_shard_path(coin, period),
            taker_addr=np.asarray(a["addr"], dtype=object),
            coin=np.asarray(a["coin"], dtype=np.int8),
            day=np.asarray(a["day"], dtype=np.int16),
            period=np.full(len(a["addr"]), period, dtype=np.int64),
            entry_px=np.asarray(a["entry_px"], dtype=np.float64),
            mo1=np.asarray(a["mo1"], dtype=np.float32),
            mo10=np.asarray(a["mo10"], dtype=np.float32),
            mo60=np.asarray(a["mo60"], dtype=np.float32),
            notional=np.asarray(a["notional"], dtype=np.float32),
            is_open=np.asarray(a["is_open"], dtype=np.int8),
            start_pos=np.asarray(a["start_pos"], dtype=np.float32),
            taker_side=np.asarray(a["taker_side"], dtype=np.int8),
            closed_pnl=np.asarray(a["closed_pnl"], dtype=np.float32),
            dir_code=np.asarray(a["dir_code"], dtype=np.int8),
            maker_addr=np.asarray(a["maker_addr"], dtype=object),
            _resolved_days=np.asarray(resolved, dtype=object),
            _issues=np.asarray(issues, dtype=object),
        )
        status[coin] = f"built ({len(a['addr']):,} rows, {len(resolved)} days)"
        print(f"[panel] CELL {coin} {period}: {status[coin]}")
    return status


def build_panel(only_coin=None, only_period=None, only_days=None):
    """Build all (coin, month) shards, then assemble panel_markouts.npz.

    only_coin / only_period restrict the build to one coin / one window. only_days
    further restricts each built window to a subset of its day labels (e.g.
    ["20250804"]) so the reviewer's SINGLE-(coin,day) SOL smoke pulls exactly one
    day. Shards already on disk are SKIPPED. The final npz is the December quickwin
    schema PLUS an int 'period' column, with takers integer-coded in a single
    first-seen map shared across all periods.

    A reviewer can prove SOL extraction on ONE day without the full pull, e.g.:
        PANEL_DATA_ROOT=/tmp/sol_smoke \\
          uv run --no-project --with-requirements ../requirements.txt python3 panel_persistence.py \\
          --build --coin SOL --period 202508 --days 20250804
    """
    periods = PERIODS if only_period is None else (only_period,)
    print(f"[panel] BUILD coins={only_coin or PANEL_COINS} periods={periods} "
          f"days={only_days or 'ALL'} data_root={os.path.basename(DATA_ROOT)}")
    for period in periods:
        days = PERIOD_DAYS[period]
        if only_days is not None:
            req = set(only_days)
            days = [d for d in days if d in req]
            if not days:
                print(f"[panel] period {period}: none of {sorted(req)} in window - "
                      f"SKIP")
                continue
        _build_one_period(period, days, only_coin=only_coin)
    return assemble_panel_npz()


# The name this builder stamps into the file it writes, and the one-line statement
# of what makes its output different from the other builder's. Both strings go INTO
# panel_markouts.npz, so the artifact answers "which builder made me" on its own.
BUILDER_NAME = "panel_persistence.py --build (canonical; run_panel.sh uses this)"
BUILDER_WALLET_ID_SCOPE = (
    "taker_id and maker_id are GLOBAL first-seen codes over the wallet HEX STRING "
    "across every shard in panel_ckpt/, so one wallet carries ONE code in every "
    "month and every coin. The cross-month join depends on exactly this. The other "
    "builder of this filename, panel_build.py, keys its ids on a (period, coin, "
    "per-cell code) composite instead, which gives the same wallet a different id "
    "in each cell and supports no cross-month join at all.")
BUILDER_ROW_ORDER = ("coin-major: shards are concatenated in sorted-filename order "
                     "(BTC 202508.. then ETH.. then SOL..). panel_build.py's merge "
                     "is period-major.")


# The three properties that tell the two builders apart in a file that carries no
# stamp, in the order they are cheap to read. Each is a consequence of how the writer
# assembles, so none of them can be true of the other builder by accident.
#
#   key order   this file writes `period` FOURTH (it names the columns in that order
#               in np.savez_compressed); panel_build.py writes PANEL_COLUMNS, which is
#               the quickwin fourteen plus `period` LAST.
#   windows     this file assembles every shard in panel_ckpt/, so it can hold all
#               eight of PERIOD_DAYS; panel_build.py's PANEL_WINDOWS is three and its
#               merge takes only the cells of the run that produced them, so more than
#               three windows in one file cannot have come from it.
#   row order   this file concatenates shards in sorted-filename order, which is
#               coin-major: over three coins the coin column changes twice. The other
#               builder loops period-major, so its coin column changes on every cell.
BUILDER_SIGNATURE_PERIOD_INDEX = 3          # zero-based position of `period` in z.files
PANEL_LEGACY_NPZ_NAME = "panel_markouts_legacy3w.npz"


def identify_builder(npz_path):
    """Which builder wrote a panel npz, from the file's own evidence.

    WHY THIS IS NOT JUST A READ OF THE `_builder` FIELD. The artifact this analysis
    runs on was written before either builder stamped itself, so the field is absent
    and cannot be added without rebuilding from S3. A verdict that depended on the
    stamp would therefore be "unknown" for the one file that matters. So the stamp is
    read FIRST when it is there, and the three structural properties above are read
    when it is not; they are properties of how each writer assembles and are available
    in a file that says nothing about itself.

    Returns a mapping with the verdict, the evidence behind it, and whether the file
    supports a cross-month wallet join. The verdict is never inferred from the FILENAME,
    which is exactly the assumption that made the collision invisible.
    """
    z = np.load(npz_path, allow_pickle=False)
    keys = list(z.files)
    stamped = str(z["_builder"]) if "_builder" in keys else None
    period_index = keys.index("period") if "period" in keys else None
    windows = sorted(int(p) for p in np.unique(z["period"])) if "period" in keys else []
    coin = z["coin"] if "coin" in keys else None
    coin_changes = int((np.diff(coin.astype(np.int64)) != 0).sum()) if coin is not None \
        else None
    n_coins = int(np.unique(coin).size) if coin is not None else 0
    evidence = {
        "stamped_builder": stamped,
        "period_key_index": period_index,
        "n_windows": len(windows),
        "windows": windows,
        "coin_column_changes": coin_changes,
        "n_coins": n_coins,
        "row_order": (None if coin_changes is None else
                      ("coin-major" if coin_changes <= max(n_coins - 1, 0)
                       else "period-major or interleaved")),
    }
    if stamped:
        verdict = next((n for n in ("panel_persistence.py", "panel_rebuild_v2.py",
                                    "panel_build.py") if n.split(".")[0] in stamped),
                       "undetermined")
        basis = "the file stamps its own builder"
    elif "block_time_ns" in keys and "is_liq" in keys:
        # A third writer of a panel, under its own name (panel_markouts_v2.npz). Its
        # ids are global over the wallet hex like this file's, so it supports the join,
        # but attributing its output to this script would be a false claim about which
        # code made a number. The two additive columns are its signature.
        verdict = "panel_rebuild_v2.py"
        basis = ("no stamp; the file carries the two additive v2 columns "
                 "block_time_ns and is_liq, which only that builder writes")
    elif period_index == BUILDER_SIGNATURE_PERIOD_INDEX and len(windows) > 3:
        verdict = "panel_persistence.py"
        basis = (f"no stamp; `period` sits at key index {period_index} where the legacy "
                 f"builder puts it last, and the file holds {len(windows)} windows "
                 f"where the legacy builder can produce at most three")
    elif period_index == len(keys) - 1:
        verdict = "panel_build.py"
        basis = "no stamp; `period` is the last key, which is PANEL_COLUMNS's order"
    else:
        verdict = "undetermined"
        basis = ("no stamp, and the key order and window count do not match either "
                 "builder's signature")
    return {
        "npz": os.path.basename(npz_path),
        "builder": verdict,
        "basis": basis,
        "evidence": evidence,
        # The property every downstream claim of this file rests on. It is a
        # CONSEQUENCE of the builder and not a separate measurement: only the global
        # first-seen coding over the wallet hex gives one wallet one id in every month,
        # and two of the three builders do that. panel_build.py's per-cell composite
        # does not, and "undetermined" is not a yes.
        "supports_cross_month_wallet_join": verdict in ("panel_persistence.py",
                                                        "panel_rebuild_v2.py"),
    }


def assemble_panel_npz():
    """Concatenate every present shard into panel_markouts.npz with a shared,
    first-seen taker/maker integer coding (so a wallet has ONE code across all
    months - that single shared code is what makes the cross-month join valid).

    Two files can write this filename (see the header). Every field this function
    emits beyond the fifteen data columns starts with an underscore, matching the
    shard convention (_resolved_days / _issues), so a reader that treats the npz as
    a table of row-aligned columns can tell metadata from data by the name alone.
    """
    if not os.path.isdir(CKPT_DIR):
        raise SystemExit(f"[panel] no checkpoint dir {os.path.basename(CKPT_DIR)} - "
                         f"run with --build first.")
    shard_files = sorted(f for f in os.listdir(CKPT_DIR)
                         if f.startswith("shard_") and f.endswith(".npz"))
    if not shard_files:
        raise SystemExit("[panel] no shards present - nothing to assemble.")

    cols = {k: [] for k in
            ("taker_addr", "coin", "day", "period", "entry_px", "mo1", "mo10",
             "mo60", "notional", "is_open", "start_pos", "taker_side",
             "closed_pnl", "dir_code", "maker_addr")}
    resolved_all, issues_all = {}, []
    for sf in shard_files:
        with np.load(os.path.join(CKPT_DIR, sf), allow_pickle=True) as z:
            n = int(z["coin"].shape[0])
            if n == 0:
                # still record its resolved-day bookkeeping
                rd = [str(x) for x in z["_resolved_days"].tolist()]
                resolved_all[sf] = rd
                issues_all.extend(str(x) for x in z["_issues"].tolist())
                continue
            for k in cols:
                cols[k].extend(z[k].tolist())
            resolved_all[sf] = [str(x) for x in z["_resolved_days"].tolist()]
            issues_all.extend(str(x) for x in z["_issues"].tolist())

    # integer-code takers in ONE first-seen map shared across all months/coins
    wallet_to_code, maker_to_code = {}, {}
    taker_id = np.empty(len(cols["taker_addr"]), dtype=np.int32)
    for i, w in enumerate(cols["taker_addr"]):
        c = wallet_to_code.get(w)
        if c is None:
            c = len(wallet_to_code); wallet_to_code[w] = c
        taker_id[i] = c
    maker_id = np.empty(len(cols["maker_addr"]), dtype=np.int32)
    for i, w in enumerate(cols["maker_addr"]):
        if w is None:
            maker_id[i] = -1; continue
        c = maker_to_code.get(w)
        if c is None:
            c = len(maker_to_code); maker_to_code[w] = c
        maker_id[i] = c

    np.savez_compressed(
        PANEL_NPZ_PATH,
        taker_id=taker_id,
        coin=np.asarray(cols["coin"], dtype=np.int8),
        day=np.asarray(cols["day"], dtype=np.int16),
        # CANONICAL panel builder (run_panel.sh uses this --build path): `period`
        # is int64 on disk. panel_build.py is the older/heavier path and now matches.
        period=np.asarray(cols["period"], dtype=np.int64),     # NEW int YYYYMM column
        entry_px=np.asarray(cols["entry_px"], dtype=np.float64),
        mo1=np.asarray(cols["mo1"], dtype=np.float32),
        mo10=np.asarray(cols["mo10"], dtype=np.float32),
        mo60=np.asarray(cols["mo60"], dtype=np.float32),
        notional=np.asarray(cols["notional"], dtype=np.float32),
        is_open=np.asarray(cols["is_open"], dtype=np.int8),
        start_pos=np.asarray(cols["start_pos"], dtype=np.float32),
        taker_side=np.asarray(cols["taker_side"], dtype=np.int8),
        closed_pnl=np.asarray(cols["closed_pnl"], dtype=np.float32),
        dir_code=np.asarray(cols["dir_code"], dtype=np.int8),
        maker_id=maker_id,
        # ---- provenance, written LAST so the fifteen data columns keep their
        # positions for any reader that indexes z.files rather than naming a key ----
        _builder=np.asarray(BUILDER_NAME),
        _builder_wallet_id_scope=np.asarray(BUILDER_WALLET_ID_SCOPE),
        _builder_row_order=np.asarray(BUILDER_ROW_ORDER),
        _builder_shards=np.asarray(json.dumps(shard_files)),
        _settings_fingerprint=np.asarray(json.dumps(H.fingerprint(
            h=H.HEADLINE_HORIZON_S, lens="print",
            markout_columns=[H.headline_print_col(h) for h in H.LADDER_S],
            windows_assembled=sorted(set(int(p) for p in cols["period"])),
            **BUILD_SETTINGS_OVERRIDES))),
    )
    with open(PANEL_TAKER_MAP_PATH, "w") as fh:
        json.dump({"_direction": "taker wallet (hex) -> int32 code (first-seen, "
                                 "shared across all panel months)",
                   "_builder": BUILDER_NAME,
                   "_settings_fingerprint": H.fingerprint(
                       h=H.HEADLINE_HORIZON_S, lens="print",
                       **BUILD_SETTINGS_OVERRIDES),
                   "map": wallet_to_code}, fh)

    print(f"[panel] assembled {PANEL_NPZ_NAME}: rows={taker_id.size:,} "
          f"takers={len(wallet_to_code):,} "
          f"periods={sorted(set(int(p) for p in cols['period']))}")
    return {"rows": int(taker_id.size), "n_takers": len(wallet_to_code),
            "resolved_by_shard": resolved_all, "issues": issues_all}


# ===========================================================================
# PART 2 - ANALYSIS (cross-month persistence on panel_markouts.npz)
# ===========================================================================
# Correlation / reliability / FDR machinery is the SAME source as ks2 - imported,
# not re-implemented, so the panel numbers are produced by the identical estimator
# the December run was validated on.
from ks2_persistence_10day import (        # noqa: E402  (import after config block)
    spearman as ks2_spearman,
    spearman_perm_pvalue as ks2_spearman_perm_pvalue,
    split_half_reliability as ks2_split_half_reliability,
    taker_means as ks2_taker_means,
)
# The step-up correction is no longer imported from ks2: it lives in stats.py, whose
# self-test asserts that spelling and this one give identical q on 200 random families.


def _load_panel(npz_path):
    """Load panel_markouts.npz into the per-(coin, period) store the cross-month
    analysis consumes: store[(coin_label, period)] = {addr, mo_score, notional}.

    addr is the integer taker_id (a hashable per-wallet key shared across months -
    exactly what taker_means / split_half_reliability expect). mo_score is the headline
    trade-print markout. notional rides along for the whale-drop ranking.
    """
    if not os.path.exists(npz_path):
        raise SystemExit(f"[panel] panel npz not found: {os.path.basename(npz_path)}"
                         f"\n      run with --build first.")
    z = np.load(npz_path, allow_pickle=False)
    taker_id = z["taker_id"].astype(np.int64)
    coin = z["coin"].astype(np.int8)
    period = z["period"].astype(np.int64)
    mo_score = z[H.headline_print_col(HEADLINE_HORIZON_S)].astype(np.float64)
    notional = z["notional"].astype(np.float64)

    # ---- pin to the paper's canonical Aug/Oct/Dec windows (CANONICAL_PERIODS) ----
    # panel_markouts.npz was rebuilt from 3 to 8 windows; this loader groups by whatever
    # periods are present, so restrict the loaded fills to the three canonical windows so
    # the cross-month analysis reproduces the committed results. Idempotent: a no-op when
    # the npz already holds only those three.
    _keep = np.isin(period, np.asarray(CANONICAL_PERIODS, dtype=np.int64))
    if not bool(_keep.all()):
        taker_id = taker_id[_keep]
        coin = coin[_keep]
        period = period[_keep]
        mo_score = mo_score[_keep]
        notional = notional[_keep]

    store, present = {}, []
    for code in np.unique(coin):
        clabel = PANEL_COIN_LABEL.get(int(code), f"coin{int(code)}")
        for per in np.unique(period[coin == code]):
            sel = (coin == code) & (period == per)
            store[(clabel, int(per))] = {
                "addr": taker_id[sel],
                "mo_score": mo_score[sel],
                "notional": notional[sel],
            }
            present.append((clabel, int(per)))
    return store, present


def _pooled_addr_arrays(store, coin, period):
    """(addr, mo_score, notional) for one (coin, period), NaN markouts dropped."""
    s = store.get((coin, period))
    if s is None:
        return (np.empty(0, dtype=np.int64), np.empty(0, dtype=np.float64),
                np.empty(0, dtype=np.float64))
    valid = ~np.isnan(s["mo_score"])
    return s["addr"][valid], s["mo_score"][valid], s["notional"][valid]


def _means_and_notional(addr, mo_score, notional, K):
    """Per-wallet mean 10s markout AND total notional for wallets with >= K fills."""
    if addr.size == 0:
        return {}, {}
    uniq, inv = np.unique(addr, return_inverse=True)
    s = np.bincount(inv, weights=mo_score, minlength=uniq.size)
    c = np.bincount(inv, minlength=uniq.size)
    nt = np.bincount(inv, weights=notional, minlength=uniq.size)
    means = {int(uniq[k]): s[k] / c[k] for k in range(uniq.size) if c[k] >= K}
    notl = {int(uniq[k]): nt[k] for k in range(uniq.size) if c[k] >= K}
    return means, notl


def _restrict_to_takers(addr, mo_score, keep):
    """Subset (addr, mo_score) to observations whose taker is in `keep` (a set)."""
    if addr.size == 0:
        return addr, mo_score
    mask = np.isin(addr, np.fromiter(keep, dtype=np.int64, count=len(keep))) \
        if keep else np.zeros(addr.size, dtype=bool)
    return addr[mask], mo_score[mask]


def cross_month_cell(store, coin, per_a, per_b, K, rel_lookup):
    """Observed + disattenuated CROSS-MONTH Spearman for one (coin, A, B, K) cell.

    SEEDING. The permutation null draws from cell_rng(RNG_CORR_SEED, coin, A, B,
    K, tag) - a generator seeded by this cell's identity, not by a stream shared
    with the other cells - so this cell's p-value is the same whether the cell is
    computed alone or inside the full grid. The whale-drop null carries its own
    tag for the same reason.

    rho_obs   = Spearman of per-wallet mean 10s markout in month A vs month B over
                wallets with >= K fills in BOTH months (the out-of-month hold-out is
                BY WALLET: a wallet must clear K independently in each month).
    rho_disatt= rho_obs / sqrt(rel_A * rel_B), reliabilities read from rel_lookup
                (the SAME stored split-half values reported in the reliability table,
                estimated on the common-wallet set, one fixed seed) so the headline
                disattenuated number can never drift from what is published.
    whale-drop= drop the top-WHALE_DROP_K common wallets by combined A+B notional and
                recompute rho_obs; reports whether sign + significance survive.
    """
    aa, am, ant = _pooled_addr_arrays(store, coin, per_a)
    ba, bm, bnt = _pooled_addr_arrays(store, coin, per_b)
    means_a, notl_a = _means_and_notional(aa, am, ant, K)
    means_b, notl_b = _means_and_notional(ba, bm, bnt, K)
    common = sorted(set(means_a) & set(means_b))

    out = {
        "coin": coin, "period_a": per_a, "period_b": per_b, "K": K,
        "pair": f"{per_a}->{per_b}",
        "n_counterparties": len(common),
        "spearman_obs": float("nan"), "pvalue": None,
        "rel_a": float("nan"), "rel_b": float("nan"),
        "spearman_disattenuated": float("nan"),
        "spearman_obs_no_whales": float("nan"),
        "pvalue_no_whales": None,
        "whale_robust": "n/a",
        "outlier_flag": False, "outlier_reasons": [],
    }
    if len(common) < 3:
        out["outlier_flag"] = True
        out["outlier_reasons"].append(f"too few common wallets (n={len(common)})")
        return out

    xa = np.array([means_a[w] for w in common], dtype=np.float64)
    xb = np.array([means_b[w] for w in common], dtype=np.float64)
    rho, n = ks2_spearman(xa, xb)
    out["spearman_obs"] = rho
    out["n_counterparties"] = int(n)
    out["pvalue"], out["permutation"] = ks2_spearman_perm_pvalue(
        xa, xb, cell_rng(RNG_CORR_SEED, coin, per_a, per_b, K, "corr"),
        cell=("cross_month_rank_persistence", coin, per_a, per_b, int(K)),
        n_perm=N_PERM_CORR)

    rel_a = rel_lookup.get((coin, per_a, per_b, "a", K), float("nan"))
    rel_b = rel_lookup.get((coin, per_a, per_b, "b", K), float("nan"))
    out["rel_a"], out["rel_b"] = rel_a, rel_b
    if rel_a == rel_a and rel_b == rel_b and rel_a > 0 and rel_b > 0:
        out["spearman_disattenuated"] = rho / np.sqrt(rel_a * rel_b)

    # whale-drop robustness (reuse the i3 pattern: drop top-k by total notional)
    if len(common) > WHALE_DROP_K + 3:
        tot_nt = np.array([notl_a[w] + notl_b[w] for w in common], dtype=np.float64)
        drop = np.argsort(tot_nt)[::-1][:WHALE_DROP_K]
        keep = np.ones(len(common), dtype=bool)
        keep[drop] = False
        rho_nw, n_nw = ks2_spearman(xa[keep], xb[keep])
        out["spearman_obs_no_whales"] = rho_nw
        if n_nw >= 3:
            out["pvalue_no_whales"], out["permutation_no_whales"] = \
                ks2_spearman_perm_pvalue(
                    xa[keep], xb[keep],
                    cell_rng(RNG_CORR_SEED, coin, per_a, per_b, K,
                             "corr_no_whales"),
                    cell=("cross_month_rank_persistence_no_whales", coin, per_a,
                          per_b, int(K)),
                    n_perm=N_PERM_CORR)
        # robust = same (non-trivial) sign survives the whale drop
        if rho == rho and rho_nw == rho_nw and rho != 0:
            out["whale_robust"] = bool(np.sign(rho_nw) == np.sign(rho)
                                       and abs(rho_nw) > 1e-6)

    # honest low-power outlier flags
    if out["n_counterparties"] < MIN_N_COUNTERPARTIES:
        out["outlier_flag"] = True
        out["outlier_reasons"].append(
            f"low common-wallet count (n={out['n_counterparties']} < "
            f"{MIN_N_COUNTERPARTIES})")
    if (rel_a == rel_a and rel_a <= LOW_RELIABILITY_FLOOR) or \
       (rel_b == rel_b and rel_b <= LOW_RELIABILITY_FLOOR):
        out["outlier_flag"] = True
        out["outlier_reasons"].append(
            f"low reliability (rel_a={rel_a:.3f}, rel_b={rel_b:.3f} <= "
            f"{LOW_RELIABILITY_FLOOR}) - disattenuation unstable")
    if not (rel_a == rel_a) or not (rel_b == rel_b):
        out["outlier_flag"] = True
        out["outlier_reasons"].append("undefined reliability in one month")
    return out


def write_results(results, started, settings=None, extra_meta=None, inputs=None):
    """Write the analysis payload through artifact.write. One writer, one shape.

    A module function rather than three lines inside analyze_panel, because
    panel_extended.py runs these same estimators over a wider window set and has to
    write the SAME shape. Before this existed it let analyze_panel write the file and
    then rewrote it with two extra fields, so the artifact was produced twice and the
    second pass had to know what the first had put in _meta. One writer removes that.

    The scope triple is DERIVED from what the run actually loaded -- the per-slice trade
    and wallet counts, the periods present and the coins present -- and never from this
    module's constants, because those describe the default run and panel_extended's run
    is not the default one.
    """
    sc = results["scope"]
    slices = results.get("slices", [])
    n_rows = sum(int(s["n_trades"]) for s in slices)
    periods = list(sc["periods"])
    windows = sc.get("period_windows", {})
    spans = ", ".join(
        f"{p} ({windows[str(p)][0]}..{windows[str(p)][-1]})" if str(p) in windows
        else str(p) for p in periods)
    if settings is None:
        settings = dict(h=sc["horizon_s"], lens=sc["lens"],
                        markout_column=sc["markout_column"], **SETTINGS_OVERRIDES)
    return artifact.write(
        RESULTS_NAME, results,
        script=__file__,
        inputs=[PANEL_NPZ_PATH] if inputs is None else list(inputs),
        scope={
            "population": (
                f"{n_rows} taker fills over {len(slices)} coin-window cells; the "
                f"cross-month cells hold out BY WALLET, a wallet clearing "
                f"{list(sc['K_pool'])} fills in BOTH months of a pair"),
            "window": f"{len(periods)} ten-day windows: {spans}",
            "coins": list(sc["coins"]),
        },
        settings=settings,
        extra_meta=extra_meta,
        # RESULTS_PATH is overridable (panel_extended.py repoints it), so the directory
        # comes from it rather than from this script's own location.
        out_dir=os.path.dirname(RESULTS_PATH) or HERE,
        started=started)


def analyze_panel(npz_path=PANEL_NPZ_PATH, started=None, settings=None,
                  extra_meta=None):
    """Cross-month persistence across all ordered period pairs + pooled, per coin
    and pooled-across-coins, at each K. Writes panel_persistence_results.json.

    The last three arguments exist for panel_extended.py, which runs these estimators
    over a wider window set and at a chosen horizon. It used to let this function write
    the file and then rewrite it with its own blocks, so every artifact of that script
    was produced twice and the second pass had to reproduce what the first had put in
    _meta. Passing them through means one write and one _meta.

    started     artifact.start_clock() from a caller whose set-up should count in the
                recorded runtime.
    settings    keyword arguments for the fingerprint. A substituting caller MUST pass
                its own: this function's default describes the default run, and a
                --horizon 60 arm stamping the declared headline would be a false
                statement in the very block a reader consults to check the number.
    extra_meta  descriptive fields for _meta beyond the records artifact.write owns.
    """
    started = artifact.start_clock() if started is None else started
    # WHICH BUILDER WROTE THE INPUT, asserted before anything is computed from it. The
    # whole cross-month claim rests on a wallet carrying ONE id in every month, and that
    # is a property of the builder rather than of the filename: the legacy builder emits
    # the same fifteen columns with the same dtypes and ids that are per-cell composites,
    # so an analysis run on its output would produce a full set of plausible p-values
    # about wallets that do not exist across months. The guard sits here rather than in
    # _load_panel because panel_extended.py substitutes that function, and a guard a
    # caller can replace is not one.
    builder = identify_builder(npz_path)
    if not builder["supports_cross_month_wallet_join"]:
        raise SystemExit(
            f"[panel] {builder['npz']} was written by {builder['builder']} "
            f"({builder['basis']}). Its wallet ids do not carry across months, so a "
            f"cross-month persistence read of it would be a number about nothing. "
            f"Rebuild with panel_persistence.py --build, whose ids are global "
            f"first-seen codes over the wallet hex.")
    print(f"[panel] input builder: {builder['builder']} -- {builder['basis']}")

    store, present = _load_panel(npz_path)
    present_periods = sorted({p for (_c, p) in present})
    present_coins = sorted({c for (c, _p) in present})
    pairs = [(a, b) for a, b in itertools.permutations(present_periods, 2)]
    column = active_markout_column()
    print(f"[panel] ANALYZE coins={present_coins} periods={present_periods} "
          f"ordered_pairs={len(pairs)} K_pool={K_POOL} "
          f"horizon={ACTIVE_HORIZON_S}s (column {column}) n_perm={N_PERM_CORR} "
          f"(p-floor=1/{N_PERM_CORR + 1})")

    # ---- per-period descriptive slice (for the honest low-volume flagging) ----
    # The two markout keys are BUILT by settings.field_name from the horizon AND the
    # lens the run actually used, not typed and not derived from the npz column name.
    # They used to be spelled f"{column}_mean_bps", e.g. mo10_mean_bps. That named
    # the window but never the lens, so a book-mid run - which this file supports by
    # loader substitution - would have shipped mid values under the print spelling.
    # Under settings.FIELD_SUFFIX_STYLE = "explicit" the names are now
    # markout_mean_bps_<h>s_<lens> and markout_median_bps_<h>s_<lens>. The npz column
    # that was read is still recorded, once, in scope.markout_column.
    mean_key = H.field_name("markout_mean_bps", ACTIVE_HORIZON_S, lens=ACTIVE_LENS)
    median_key = H.field_name("markout_median_bps", ACTIVE_HORIZON_S, lens=ACTIVE_LENS)
    slices = []
    for coin in present_coins:
        for per in present_periods:
            s = store.get((coin, per))
            if s is None:
                continue
            g_score = s["mo_score"][~np.isnan(s["mo_score"])]
            slices.append({
                "coin": coin, "period": per,
                "n_trades": int(s["addr"].size),
                "n_takers": int(np.unique(s["addr"]).size),
                mean_key: float(np.mean(g_score)) if g_score.size else float("nan"),
                median_key: (float(np.median(g_score)) if g_score.size
                             else float("nan")),
            })

    # ---- SINGLE RELIABILITY SOURCE (per coin x ordered-pair x month, one seed) ----
    # For each (coin, A, B, K) we estimate split-half reliability of the per-wallet
    # mean SEPARATELY in month A and month B, on the COMMON-wallet set (the wallets
    # entering rho_obs). The disattenuation divisor reads from this same dictionary
    # so it cannot drift from the reported reliability.
    #
    # SEEDING: the split-half draw is seeded from the cell's identity too. The same
    # shared-stream defect applied here - reliability, and therefore every
    # disattenuated Spearman, depended on the loop position - and it is fixed the
    # same way. RNG_RELIABILITY stays the master seed; each (coin, pair, K, month)
    # split gets its own derived stream.
    reliability = []
    rel_lookup = {}
    for coin in present_coins:
        for per_a, per_b in pairs:
            aa, am, _ant = _pooled_addr_arrays(store, coin, per_a)
            ba, bm, _bnt = _pooled_addr_arrays(store, coin, per_b)
            for K in K_POOL:
                common = set(ks2_taker_means(aa, am, K)) & set(ks2_taker_means(ba, bm, K))
                aa_c, am_c = _restrict_to_takers(aa, am, common)
                ba_c, bm_c = _restrict_to_takers(ba, bm, common)
                rel_a, n_a, rh_a = ks2_split_half_reliability(
                    aa_c, am_c, K,
                    cell_rng(RNG_RELIABILITY, coin, per_a, per_b, K, "rel_a"))
                rel_b, n_b, rh_b = ks2_split_half_reliability(
                    ba_c, bm_c, K,
                    cell_rng(RNG_RELIABILITY, coin, per_a, per_b, K, "rel_b"))
                rel_lookup[(coin, per_a, per_b, "a", K)] = rel_a
                rel_lookup[(coin, per_a, per_b, "b", K)] = rel_b
                reliability.append({
                    "coin": coin, "pair": f"{per_a}->{per_b}", "K": K,
                    "rel_a": rel_a, "rel_b": rel_b,
                    "n_takers_a": n_a, "n_takers_b": n_b,
                    "r_half_a": rh_a, "r_half_b": rh_b,
                    "taker_set": "common (A-and-B intersection)",
                    "seed": RNG_RELIABILITY})

    # ---- per-coin per-pair cross-month persistence (the decisive cells) ----
    cells = []
    for coin in present_coins:
        for per_a, per_b in pairs:
            for K in K_POOL:
                res = cross_month_cell(store, coin, per_a, per_b, K, rel_lookup)
                cells.append(res)
                dis = res["spearman_disattenuated"]
                dis_s = "nan" if dis != dis else f"{dis:+.3f}"
                pv = "n/a" if res["pvalue"] is None else f"{res['pvalue']:.4f}"
                flag = " OUTLIER" if res["outlier_flag"] else ""
                print(f"[panel] XMONTH {coin} {res['pair']} K={K}: "
                      f"obs={res['spearman_obs']:+.4f} disatt={dis_s} "
                      f"n={res['n_counterparties']} p={pv} "
                      f"whale_ok={res['whale_robust']}{flag}")

    # ---- POOLED across coins, per ordered pair (stack common wallets of all coins) ----
    # Pool each coin's common-wallet (A-mean, B-mean) points so a single rho summarises
    # the whole panel for that pair. Reliability pooled the same way; disattenuation
    # from the pooled reliability so the pooled headline cannot drift either.
    # Seeded per (pair, K) from the "POOLED" identity, on the same rule as the
    # per-coin cells: a pooled cell's p-value does not depend on how many per-coin
    # cells ran before it, nor on which pooled cells ran before it.
    pooled_cells = []
    pooled_reliability = []
    for per_a, per_b in pairs:
        for K in K_POOL:
            xa_parts, xb_parts, nt_parts = [], [], []
            aa_all, am_all, ba_all, bm_all = [], [], [], []   # for pooled reliability
            for coin in present_coins:
                aa, am, ant = _pooled_addr_arrays(store, coin, per_a)
                ba, bm, bnt = _pooled_addr_arrays(store, coin, per_b)
                means_a, notl_a = _means_and_notional(aa, am, ant, K)
                means_b, notl_b = _means_and_notional(ba, bm, bnt, K)
                common = sorted(set(means_a) & set(means_b))
                if common:
                    xa_parts.append(np.array([means_a[w] for w in common]))
                    xb_parts.append(np.array([means_b[w] for w in common]))
                    nt_parts.append(np.array([notl_a[w] + notl_b[w] for w in common]))
                    # restrict raw obs to common for pooled reliability (offset codes
                    # per coin so wallets from different coins never collide)
                    base = (PANEL_COIN_CODE[coin] + 1) * 10_000_000_000
                    aa_c, am_c = _restrict_to_takers(aa, am, set(common))
                    ba_c, bm_c = _restrict_to_takers(ba, bm, set(common))
                    aa_all.append(aa_c + base); am_all.append(am_c)
                    ba_all.append(ba_c + base); bm_all.append(bm_c)
            cell = {"coin": "POOLED", "period_a": per_a, "period_b": per_b, "K": K,
                    "pair": f"{per_a}->{per_b}", "n_counterparties": 0,
                    "spearman_obs": float("nan"), "pvalue": None,
                    "rel_a": float("nan"), "rel_b": float("nan"),
                    "spearman_disattenuated": float("nan"),
                    "spearman_obs_no_whales": float("nan"),
                    "pvalue_no_whales": None, "whale_robust": "n/a",
                    "outlier_flag": False, "outlier_reasons": []}
            if xa_parts:
                xa = np.concatenate(xa_parts); xb = np.concatenate(xb_parts)
                tot_nt = np.concatenate(nt_parts)
                rho, n = ks2_spearman(xa, xb)
                cell["spearman_obs"] = rho
                cell["n_counterparties"] = int(n)
                if n >= 3:
                    cell["pvalue"], cell["permutation"] = \
                        ks2_spearman_perm_pvalue(
                            xa, xb,
                            cell_rng(RNG_CORR_SEED, "POOLED", per_a, per_b, K,
                                     "corr"),
                            cell=("cross_month_rank_persistence_pooled", per_a,
                                  per_b, int(K)),
                            n_perm=N_PERM_CORR)
                # pooled reliability on the stacked common wallets
                if aa_all:
                    aa_s = np.concatenate(aa_all); am_s = np.concatenate(am_all)
                    ba_s = np.concatenate(ba_all); bm_s = np.concatenate(bm_all)
                    rel_a, _na, _ra = ks2_split_half_reliability(
                        aa_s, am_s, K,
                        cell_rng(RNG_RELIABILITY, "POOLED", per_a, per_b, K, "rel_a"))
                    rel_b, _nb, _rb = ks2_split_half_reliability(
                        ba_s, bm_s, K,
                        cell_rng(RNG_RELIABILITY, "POOLED", per_a, per_b, K, "rel_b"))
                    cell["rel_a"], cell["rel_b"] = rel_a, rel_b
                    pooled_reliability.append({"pair": f"{per_a}->{per_b}", "K": K,
                                               "rel_a": rel_a, "rel_b": rel_b})
                    if rel_a == rel_a and rel_b == rel_b and rel_a > 0 and rel_b > 0:
                        cell["spearman_disattenuated"] = rho / np.sqrt(rel_a * rel_b)
                if n > WHALE_DROP_K + 3:
                    drop = np.argsort(tot_nt)[::-1][:WHALE_DROP_K]
                    keep = np.ones(n, dtype=bool); keep[drop] = False
                    rho_nw, n_nw = ks2_spearman(xa[keep], xb[keep])
                    cell["spearman_obs_no_whales"] = rho_nw
                    if n_nw >= 3:
                        cell["pvalue_no_whales"], cell["permutation_no_whales"] = \
                            ks2_spearman_perm_pvalue(
                                xa[keep], xb[keep],
                                cell_rng(RNG_CORR_SEED, "POOLED", per_a, per_b, K,
                                         "corr_no_whales"),
                                cell=("cross_month_rank_persistence_pooled_no_whales",
                                      per_a, per_b, int(K)),
                                n_perm=N_PERM_CORR)
                    if rho == rho and rho_nw == rho_nw and rho != 0:
                        cell["whale_robust"] = bool(np.sign(rho_nw) == np.sign(rho)
                                                    and abs(rho_nw) > 1e-6)
                if cell["n_counterparties"] < MIN_N_COUNTERPARTIES:
                    cell["outlier_flag"] = True
                    cell["outlier_reasons"].append(
                        f"low pooled common-wallet count (n={cell['n_counterparties']})")
            else:
                cell["outlier_flag"] = True
                cell["outlier_reasons"].append("no common wallets across any coin")
            pooled_cells.append(cell)
            dis = cell["spearman_disattenuated"]
            dis_s = "nan" if dis != dis else f"{dis:+.3f}"
            pv = "n/a" if cell["pvalue"] is None else f"{cell['pvalue']:.4f}"
            print(f"[panel] XMONTH POOLED {cell['pair']} K={K}: "
                  f"obs={cell['spearman_obs']:+.4f} disatt={dis_s} "
                  f"n={cell['n_counterparties']} p={pv}")

    # ---- BH-FDR across the full (period-pair x K) family ----
    # The family = every per-coin cell PLUS the pooled cells (all the cross-month
    # correlation p-values). One BH pass; each cell gets a q-value; the summary
    # reports how many survive q<=alpha. None/NaN p-values are excluded from m.
    all_cells = cells + pooled_cells
    # The correction comes from stats.py rather than from the copy in ks2, and the move
    # costs no number: stats._legacy_bh_loop is that copy, and the self-test there runs
    # the two against each other on 200 random families with ties and untestable cells
    # and asserts identical q. What the module adds is the CUTOFF the q-values were
    # judged against, which the local copy did not return.
    bh = stats.benjamini_hochberg(
        [c["pvalue"] for c in all_cells], alpha=FDR_ALPHA,
        family="cross-month persistence Spearman p-values (per-coin + pooled cells, "
               "ordered period pairs x K)")
    q_all = bh["q"]
    n_survive = 0
    for c, q in zip(all_cells, q_all):
        c["q_value_bh"] = q
        if q is not None and q == q and q <= FDR_ALPHA:
            n_survive += 1
    family_size = int(sum(1 for c in all_cells
                          if c["pvalue"] is not None and c["pvalue"] == c["pvalue"]))
    # The family runs over ORDERED pairs, so every comparison appears twice: the
    # Spearman is symmetric and rho(A,B) equals rho(B,A) to the bit, as does its
    # p-value. Doubling every p also doubles its rank, so the BH rejection SET is
    # unchanged and no cell is called significant that would not be otherwise.
    # What is not invariant is the COUNT: a sentence saying "n of m comparisons"
    # built on family_size overstates both by a factor of two. The distinct count
    # is recorded beside it so nothing has to be halved by hand later.
    n_distinct = int(sum(1 for c in all_cells
                         if c["pvalue"] is not None and c["pvalue"] == c["pvalue"]
                         and int(c["period_a"]) < int(c["period_b"])))
    fdr_summary = {
        "family": "cross-month persistence Spearman p-values (per-coin + pooled "
                  "cells, ordered period pairs x K)",
        "family_size": family_size,
        "n_distinct_comparisons": n_distinct,
        "count_note": "family_size counts ordered pairs and therefore counts every "
                      "comparison twice; quote n_distinct_comparisons in prose. The "
                      "BH rejection set is identical either way.",
        "method": bh["method"],
        "alpha": FDR_ALPHA,
        "n_survive_q_le_alpha": n_survive,
        "n_survive_distinct": int(n_survive // 2) if n_survive % 2 == 0 else None,
        "n_perm_corr": N_PERM_CORR,
        "p_floor": H.p_floor(N_PERM_CORR),
        # The bar the p-values were actually judged against. A verdict of "survives the
        # correction" cannot be read without it, and it is not a constant: it depends on
        # the family size, which across this work runs from 4 to 448 at one alpha.
        # .get, because a family with no testable cell carries a note instead of a
        # cutoff, and a KeyError there would turn an empty family into a crash.
        "threshold": bh.get("threshold"),
        "threshold_meaning": bh.get("threshold_meaning", bh.get("note")),
        "rank1_threshold": bh.get("rank1_threshold"),
        "smallest_p": bh.get("smallest_p"),
    }
    print(f"[panel] BH-FDR over {family_size} cross-month cells: "
          f"{n_survive} survive q<={FDR_ALPHA} "
          f"(p-floor={fdr_summary['p_floor']:.5f})")

    # ---- collect the honest outlier register ----
    outliers = [{"coin": c["coin"], "pair": c["pair"], "K": c["K"],
                 "n_counterparties": c["n_counterparties"],
                 "rel_a": c["rel_a"], "rel_b": c["rel_b"],
                 "reasons": c["outlier_reasons"]}
                for c in all_cells if c["outlier_flag"]]

    results = {
        "scope": {
            "object": f"cross-month (out-of-month) persistence of per-wallet "
                      f"{ACTIVE_HORIZON_S}s adverse-selection toxicity",
            "periods": present_periods,
            "period_windows": {str(p): PERIOD_DAYS[p] for p in PERIODS
                               if p in present_periods},
            "coins": present_coins,
            "coin_code": PANEL_COIN_CODE,
            "ordered_pairs": [f"{a}->{b}" for a, b in pairs],
            "K_pool": list(K_POOL),
            "horizon_s": ACTIVE_HORIZON_S,
            "lens": ACTIVE_LENS,
            "markout_column": column,
            "slice_keys": [mean_key, median_key],
            "field_suffix_style": H.FIELD_SUFFIX_STYLE,
            "markout_sign": "positive = taker profited = maker adverse-selected",
            "clock_source": ACTIVE_CLOCK_SOURCE,
            "dedup": "one obs per (hash, taker), size-weighted VWAP entry",
            "holdout": "BY WALLET - a wallet must clear K fills in BOTH months of a pair",
            "n_perm_corr": N_PERM_CORR,
            "p_floor_corr": H.p_floor(N_PERM_CORR),
            "whale_drop_k": WHALE_DROP_K,
            "reliability_seed": RNG_RELIABILITY,
            "corr_seed": RNG_CORR_SEED,
            "seed_rule": (
                "per-cell: seed = first 8 bytes of SHA-256 of "
                "'<master_seed>|<coin>|<period_a>|<period_b>|<K>|<statistic tag>', "
                "tags corr / corr_no_whales / rel_a / rel_b, coin='POOLED' for the "
                "pooled cells. The seed is a pure function of the cell's identity, "
                "not of its position in the loop, so a cell computed on its own "
                "reproduces the p-value it has inside the full grid and adding a "
                "coin, a window or a K leaves existing cells unchanged."),
            "reliability_taker_set": "common (A-and-B intersection)",
            "fdr_alpha": FDR_ALPHA,
            "method": "split-half (Spearman-Brown) reliability + disattenuated "
                      "cross-month Spearman; permutation null; BH-FDR; whale-drop",
            "outlier_rule": {
                "min_n_counterparties": MIN_N_COUNTERPARTIES,
                "low_reliability_floor": LOW_RELIABILITY_FLOOR},
            # The settings block used to be built here as well as in _meta, so the
            # same record stood in two places in one file. It is now built once, by
            # artifact.write, from the keywords write_results passes; a reader of this
            # block goes to _meta.settings_fingerprint for it.
            "settings_fingerprint_at": "_meta.settings_fingerprint",
        },
        "slices": slices,
        "reliability": reliability,
        "pooled_reliability": pooled_reliability,
        "cross_month_cells": cells,
        "cross_month_pooled": pooled_cells,
        "cross_month_fdr": fdr_summary,
        "outliers": outliers,
        "outliers_note": (
            "Pairs listed here are LOW-POWER / LOW-RELIABILITY outliers (thin "
            "common-wallet count or near-zero split-half reliability). Their "
            "disattenuated Spearman is unstable - read the observed rho and n, NOT "
            "the disattenuated value, and do not let them carry the cross-month "
            "claim. The decisive read is the pooled cells with BH-FDR survival."),
        # The four records artifact.write owns -- the producer, the inputs, the scope
        # triple and the settings fingerprint -- used to be spelled out here, three of
        # them under names the module reserves. They are passed as parameters below
        # instead, so each lives in exactly one place. What stays in the payload is the
        # descriptive `scope` block above, which is this file's own object and is a
        # superset of the triple; _meta["scope"] states the triple and points at it.
        "_meta": {"panel_npz": PANEL_NPZ_NAME,
                  "input_builder": builder,
                  "n_perm_corr": N_PERM_CORR,
                  "p_floor_corr": H.p_floor(N_PERM_CORR)},
    }
    write_results(results, started, settings=settings, extra_meta=extra_meta,
                  inputs=[npz_path])

    # ----- console summary -----
    print("\n" + "=" * 78)
    print("PANEL CROSS-MONTH PERSISTENCE - SUMMARY")
    print("=" * 78)
    print(f"  periods : {present_periods}   coins: {present_coins}")
    print(f"  ordered pairs: {[f'{a}->{b}' for a, b in pairs]}   K_pool={K_POOL}")
    print("-" * 78)
    print(f"  POOLED cross-month persistence (decisive; n_perm={N_PERM_CORR}, "
          f"p-floor=1/{N_PERM_CORR + 1}):")
    for c in pooled_cells:
        dis = c["spearman_disattenuated"]
        dis_s = "nan" if dis != dis else f"{dis:+.3f}"
        pv = "n/a" if c["pvalue"] is None else f"{c['pvalue']:.4f}"
        qv = c.get("q_value_bh")
        qs = "n/a" if (qv is None or qv != qv) else f"{qv:.4f}"
        print(f"    {c['pair']} K={c['K']:<3} obs={c['spearman_obs']:+.4f} "
              f"disatt={dis_s} n={c['n_counterparties']} p={pv} q_bh={qs} "
              f"whale_ok={c['whale_robust']}")
    print(f"  BH-FDR: {n_survive} of {family_size} cross-month cells survive "
          f"q<={FDR_ALPHA}")
    if outliers:
        print("-" * 78)
        print(f"  LOW-POWER OUTLIERS (do NOT carry the claim): {len(outliers)}")
        for o in outliers[:12]:
            print(f"    {o['coin']} {o['pair']} K={o['K']}: "
                  f"n={o['n_counterparties']} relA={o['rel_a']:.3f} "
                  f"relB={o['rel_b']:.3f} - {'; '.join(o['reasons'])}")
    print("=" * 78)
    print(f"  results -> {RESULTS_NAME}")
    return results


# ===========================================================================
# main
# ===========================================================================
def main():
    ap = argparse.ArgumentParser(
        description="Panel cross-month persistence (build + analyze). The full "
                    "90-cell pull is a separate background step; a reviewer SOL "
                    "smoke proves one (coin,day) in an isolated PANEL_DATA_ROOT: "
                    "PANEL_DATA_ROOT=/tmp/sol_smoke python3 panel_persistence.py "
                    "--build --coin SOL --period 202508 --days 20250804.")
    ap.add_argument("--build", action="store_true",
                    help="parse the coin-month cells into panel_markouts.npz "
                         "(per-cell checkpoint; hardened download).")
    ap.add_argument("--analyze", action="store_true",
                    help="run cross-month persistence on panel_markouts.npz -> "
                         "panel_persistence_results.json.")
    ap.add_argument("--coin", choices=PANEL_COINS, default=None,
                    help="restrict --build to one coin, e.g. SOL (smoke).")
    ap.add_argument("--period", type=int, choices=PERIODS, default=None,
                    help="restrict --build to one period YYYYMM (smoke).")
    ap.add_argument("--days", nargs="+", default=None, metavar="YYYYMMDD",
                    help="restrict --build to a subset of day labels within the "
                         "chosen period(s), e.g. --days 20250804 for a single-day "
                         "SOL smoke. Days not in a window are ignored.")
    args = ap.parse_args()

    do_build = args.build or not (args.build or args.analyze)
    do_analyze = args.analyze or not (args.build or args.analyze)

    if do_build:
        build_panel(only_coin=args.coin, only_period=args.period,
                    only_days=args.days)
    if do_analyze:
        analyze_panel()


if __name__ == "__main__":
    main()
