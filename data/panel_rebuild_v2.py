"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-22
References:
  - Hyperliquid node-data S3 archive (node_fills_by_block/hourly), s3://hl-mainnet-node-data.
  - Avellaneda, M., Stoikov, S. (2008). "High-frequency trading in a limit order book."
    Quantitative Finance 8(3), 217-224.
  - Cartea, A., Jaimungal, S., et al. Toxic-flow / adverse-selection market-making literature.
  - Zenodo 18184441 (Albers et al. 2026).
"""

# ---------------------------------------------------------------------------
# PANEL RE-PULL v2 - the verified panel PLUS two per-row fields the original
# build computed transiently and then DROPPED at persist:
#
#   block_time_ns : int64 NATIVE nanosecond block_time of the taker leg (the
#                   earliest-block_time crossed=true leg of each collapsed
#                   (hash, taker) sweep). The original pipeline parses this for
#                   the as-of markout join but only keeps `day` (day-of-month).
#   is_liq        : int8 1 if the collapsed trade carries the nested
#                   `liquidation` object on any of its legs, else 0. The
#                   `liquidation` object {liquidatedUser, markPx, method} is
#                   present ONLY on liquidation fills and rides BOTH legs of a
#                   liquidation trade (verified on raw 2025-12-04 H23 bytes:
#                   45 taker + 45 maker legs, 14 hashes, both legs each).
#
# EVERYTHING ELSE is identical to panel_persistence.py --build: SAME 8 windows
# {202508,202509,202510,202511,202512,202601,202603,202605}, SAME coins
# BTC/ETH/SOL, SAME sweep-collapse (one obs per (hash, taker), size-weighted
# VWAP entry), SAME no-lookahead as-of markout (last-at-or-before entry, first-
# at-or-after horizon at 1/10/60 s on the native block_time clock), SAME maker
# resolution, SAME columns and dtypes, SAME first-seen integer coding.
#
# WHY a local parse_day_v2 instead of bq.parse_day: bq.parse_day already returns
# the taker block_time (it IS d["taker_ts"]), but it does NOT track the
# `liquidation` marker anywhere - that object is read straight off the raw fill
# and never stored. To carry is_liq we must touch the per-leg scan, so this file
# RE-IMPLEMENTS parse_day VERBATIM from build_quickwin_markouts.parse_day (the
# single source of truth) with exactly two additive changes:
#   (a) the taker collapse record carries an is_liq flag (OR-ed across legs);
#   (b) per_coin emits taker_block_ns (= the same min-block_time used as
#       taker_ts) and taker_isliq alongside the existing fields.
# Every other line - the print-reference VWAP path, the crossed=true / =false
# split, the earliest-leg dir/start_pos/side/dir_code carry, the closedPnl sum,
# the dominant-maker resolution, the stream-and-discard - is copied unchanged so
# the BTC/ETH/SOL markout numbers reproduce the verified panel byte-for-byte.
#
# Markout / download / coin-map / horizons are REUSED from
# build_quickwin_markouts (imported, not re-derived):
#   bq.download_day            hardened S3 pull (retry + count assert + ls-confirm)
#   bq.iter_local_hour_lines   stream-decompress one .lz4
#   bq.compute_markouts_all    signed taker markout in bps (+ = maker adverse-selected)
#   bq.COINS / bq.COIN_CODE    coin filter + codes (SOL injected additively)
#   bq.ZERO_HASH / bq.OPEN_DIRS / bq.DIR_CODE / bq.DIR_UNKNOWN / bq.NS_PER_S
#
# Window/coin config is REUSED from panel_persistence (imported):
#   pp.PERIOD_DAYS / pp.PERIODS / pp.PANEL_COINS / pp.PANEL_COIN_CODE /
#   pp.PANEL_COIN_LABEL / pp.ensure_panel_coins()
#
# OUTPUT - NEW PATHS ONLY (the existing panel is never touched):
#   panel_markouts_v2.npz
#   panel_ckpt_v2/shard_{COIN}_{YYYYMM}.npz
#   panel_taker_map_v2.json
# All three are gitignored intermediates, and where they live is asked of
# panel_io.data_root() -- the same call persistence/three_coin_persistence.py,
# data/step1_inventory.py and notebook_build/make_notebook_fills.py make to find them, so the
# writer and its readers cannot drift apart again. Today that resolves to the repository
# root. PANEL_V2_DATA_ROOT names a different directory outright, and it is the only
# environment name this file answers to; _v2_data_root below carries the measurement
# behind both decisions. The manifest is the one output that does NOT follow them: it is
# a .json written through the shared artifact writer, which puts a result beside its
# producer, so it sits in this directory.
#
# DECLARED DEBT, opened 2026-08-04: THE OUTPUT ON DISK IS OLDER THAN THIS FILE AND NO
# GATE CAN SAY SO. On 4 August 2026 the day teardown below moved from an outright
# deletion to the declared CAP_KEEP_RAW branch, which moves this file's bytes and
# therefore ought to make its output stale. It does not register anywhere, and the
# reason is a property of the artifacts rather than of the change: panel_markouts_v2.npz
# carries no _meta block at all, so it records no producer hash to compare against, and
# panel_taker_map_v2.json sits outside the provenance census population. The freshness
# gate reads 0 older-than-its-code both before and after the edit. Zero there is the
# instrument's blind spot, not a clean bill.
#
# THE SAME BLIND SPOT THEN HID SOMETHING LARGER, AND IT WAS FOUND BY READING THE
# ADDRESSES RATHER THAN BY ANY GATE. When the scripts were sorted into pipeline groups on
# 11 August 2026 this file moved into data/ while its three outputs, being gitignored
# intermediates, stayed in the repository root. The address lines did not change by one
# byte -- they were derived from the file's own location, and the file had moved -- so
# from that day the builder looked for its checkpoint one directory below the shards and
# would have written its panel one directory below every reader of it. Repaired on 21
# August 2026 by resolving the three names by looking for them; _v2_data_root carries the
# measurement. The output on disk is untouched by the repair and is once again at the
# address the code names, which is the address it was written at on 4 August, before the
# move. The debt above is unchanged: it is still a rerun that closes it, and no
# instrument in this tree can date these bytes against this file.
#
# THE PRICE, and why it is a lower bound rather than a figure. This node has no runtime
# recorded, because it writes no artifact of the shape that would record one -- so the
# honest statement is "not recorded", and nothing is put in its place. The nearest
# measured relative is ten days of the same tape parsed with the download included at
# 1291.5 s (measured 2026-08-02). This node covers eight windows of ten days, so eighty
# days, giving about 10332 s. That is a FLOOR twice over: it parses three coins where
# the relative parses two, and it retains eight extra per-row fields.
#
# What closes the debt: one full run, whose output should be written through the shared
# artifact writer so the next such question can be answered by a hash instead of by this
# comment. Until then no figure standing on panel_markouts_v2.npz may be published as
# having been produced by the file as it now reads.
#
# WHICH FILE WRITES WHICH, since three files in this directory build a panel npz.
# panel_markouts.npz has TWO writers, panel_persistence.py --build (the canonical
# one, whose output is the file on disk) and panel_build.py (the legacy
# orchestrator); those two emit the same fifteen column names in a different key
# order, in a different row order, and - the difference that matters - with
# different wallet-id semantics, so they are not interchangeable. THIS file is not
# one of them. It writes panel_markouts_v2.npz and never panel_markouts.npz, so
# nothing it does can be confused with either of the other two, and its checkpoint
# dir is v2-suffixed so a shard cannot be picked up by the wrong assembler.
# Relative to panel_persistence.py --build, whose wallet coding it copies (global
# first-seen over the wallet HEX across every shard, one code per wallet in every
# month and coin), this file adds two per-row columns and changes nothing else. It
# stamps its own name into the file it writes, as the other two now do.
#
# SMOKE override (mirrors the other scripts): set CAP_DAYS / CAP_COINS to scope
# a one-day single-coin build, e.g.
#   CAP_DAYS=20251204 CAP_COINS=BTC AWS_PROFILE=default \
#     uv run --no-project --with-requirements requirements.txt python3 data/panel_rebuild_v2.py
#
# FULL run (no env override -> all 8 windows x BTC/ETH/SOL):
#   AWS_PROFILE=default \
#     uv run --no-project --with-requirements requirements.txt python3 data/panel_rebuild_v2.py
# bare python3 is BLOCKED on this machine - always go through uv.
# ---------------------------------------------------------------------------

import json
import os
import shutil
import sys

import numpy as np

# Reuse the validated December builder verbatim (markout, hardened download,
# coin map, constants) and the panel window/coin config. Importing
# panel_persistence runs its ensure_panel_coins() at import time, so SOL is
# already injected into bq.COINS / bq.COIN_CODE when this module loads.
# artifact.py, settings.py and the other shared modules sit in the
# repository root, one directory up from this group, so the path is built
# from this file's own location and never from the working directory the
# run happens to start in.
_CODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CODE_DIR not in sys.path:
    sys.path.insert(0, _CODE_DIR)

import artifact
import build_quickwin_markouts as bq
import panel_io as P
import panel_persistence as pp
import settings as H

# Make doubly sure every panel coin is registered in the reused builder's coin
# globals (idempotent; panel_persistence already calls this at import).
pp.ensure_panel_coins()

# -------------------- panel configuration (REUSED verbatim from panel_persistence) --------------------
PERIOD_DAYS = pp.PERIOD_DAYS                     # the fixed 8-window panel
PERIODS = pp.PERIODS                             # (202508, ..., 202605)
PANEL_COINS = pp.PANEL_COINS                     # ("BTC", "ETH", "SOL")
PANEL_COIN_CODE = pp.PANEL_COIN_CODE             # {"BTC":0,"ETH":1,"SOL":2}
PANEL_COIN_LABEL = pp.PANEL_COIN_LABEL

# -------------------- smoke override (mirrors build_quickwin / panel scripts) --------------------
# CAP_DAYS  = comma/space-separated YYYYMMDD list -> restrict the build to those
#             day labels (only days that fall inside a configured window are kept).
# CAP_COINS = comma/space-separated coin list -> restrict the build to those coins.
# Unset = the full 8-window x BTC/ETH/SOL pull (the main loop's job).
def _parse_env_list(name):
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    parts = [p for p in raw.replace(",", " ").split() if p]
    return parts or None


SMOKE_DAYS = _parse_env_list("CAP_DAYS")                 # e.g. ["20251204"]
SMOKE_COINS = _parse_env_list("CAP_COINS")               # e.g. ["BTC"]
if SMOKE_COINS is not None:
    SMOKE_COINS = [c.upper() for c in SMOKE_COINS]
    bad = [c for c in SMOKE_COINS if c not in PANEL_COINS]
    if bad:
        raise SystemExit(f"[panel_v2] CAP_COINS has non-panel coin(s) {bad}; "
                         f"panel coins = {PANEL_COINS}")

# -------------------- output layout (NEW v2 PATHS ONLY) --------------------
# There is deliberately no constant here for "the directory this script sits in". One
# stood here until the addresses were repaired and nothing reads it now, and the reason
# to delete rather than leave it is that its name is the whole defect in miniature: it
# said where the CODE is and was being read as where the DATA is, which was the same
# answer only for as long as the two lived together. The manifest, which genuinely does
# belong beside its producer, gets that directory from the shared artifact writer out of
# the script path it is handed, so nothing here needs to name it.

# The three things this file writes, named once. The checkpoint dir is v2-suffixed so
# it can NEVER collide with panel_ckpt/, and the two files carry the same suffix for the
# same reason.
PANEL_NPZ_NAME = "panel_markouts_v2.npz"
PANEL_TAKER_MAP_NAME = "panel_taker_map_v2.json"
CKPT_DIR_NAME = "panel_ckpt_v2"

# Directories that hold copies rather than the thing itself, so a walk that looked into
# them would report an ambiguity that does not exist.
_SKIP_DIRS = {".git", "__pycache__", ".ipynb_checkpoints", "node_modules"}


# The three names, in the shape the walk below wants them: what to look for and whether
# it is a file or a directory.
_WANTED = ((PANEL_NPZ_NAME, "file"),
           (PANEL_TAKER_MAP_NAME, "file"),
           (CKPT_DIR_NAME, "dir"))

# WHICH ENVIRONMENT NAME THIS BUILDER ANSWERS TO, AND WHY IT IS ONLY ONE OF THE FIVE.
# panel_io.py holds the tree's list of names for "the directory the intermediates live
# in" and honours all five, first one set winning, so that a script migrated onto it
# keeps speaking whatever name it spoke before. Handing that list over unchanged is the
# tidier call and it is measurably the wrong one here. CONFIG.md records why two of the
# names exist separately -- PANEL_DATA_ROOT and PANEL_V2_DATA_ROOT are "kept separate so
# the two cannot overwrite each other" -- and on the shared list a tree that set
# PANEL_DATA_ROOT alone, to relocate the FIRST panel, relocates this build on top of it.
# Reordering the list does not save it either: putting this file's name in front only
# decides which wins when BOTH are set, and the collision needs only one. That was
# measured rather than reasoned about, on a run that set PANEL_DATA_ROOT by itself and
# watched this builder follow it.
#
# So the name is one name, the one this file has always answered to and the one CONFIG.md
# assigns it. What comes from panel_io is the part that genuinely should have one home:
# the DEFAULT, its own directory, which is the answer its readers get.
DATA_ROOT_ENV = ("PANEL_V2_DATA_ROOT",)


def _v2_data_root():
    """The directory this file's three outputs live in.

    THIS USED TO BE THE DIRECTORY THIS SCRIPT ITSELF SITS IN, AND THAT SILENTLY MOVED
    EVERY ONE OF THE THREE ADDRESSES. The line read
    os.environ.get("PANEL_V2_DATA_ROOT", HERE) and it was right for as long as this file
    sat in the repository root, because then HERE was the root and the root is where the
    data is. When the scripts were sorted into pipeline groups the file went into data/
    and the three large outputs, which are gitignored intermediates rather than
    repository content, stayed where they were. The five lines did not change by one
    byte; HERE changed under them, and took all three addresses with it.

    Measured on this tree before the repair: panel_markouts_v2.npz at 572 MB,
    panel_taker_map_v2.json at 16 MB and panel_ckpt_v2/ with all twenty-four shards sit
    in the repository root, while the code resolved all three one directory down, where
    none of them exists. Nothing reported it, and the reason is the one this file's
    debt note already gives -- an .npz has nowhere to keep a _meta block, so there is no
    producer hash for a freshness gate to compare and no gate whose range covers it.

    THE TWO FAILURES ARE DIFFERENT AND THE QUIETER ONE IS THE EXPENSIVE ONE. The
    checkpoint dir is READ before it is written: _cell_done skips a cell whose shard is
    already present, which is what lets a rerun that reuses all twenty-four be minutes
    rather than hours. Pointed at a directory that does not exist, every cell reads "not
    done" and a default run reparses eighty days of tape -- a floor of about 10332 s by
    the estimate in the header. The two file outputs fail the other way, and worse in
    kind: the run does not fail at all, it succeeds into the wrong directory, leaving a
    second panel and a second taker map that no reader opens while every consumer goes
    on reading the pair in the root.

    THE ANSWER HAS ONE HOME AND IT IS panel_io.data_root(), which is the same call
    persistence/three_coin_persistence.py, data/step1_inventory.py and
    notebook_build/make_notebook_fills.py make to find these very files. That is the whole
    repair: the disagreement was never about the rule, it was that the writer derived
    its answer from its OWN location while the readers derived theirs from panel_io's,
    and only one of the two moved in August. Asking the same question of the same module
    is what makes writer and readers move together from here on, whatever happens to
    this file.

    THE WALK BELOW DECIDES NOTHING; IT ONLY EXPLAINS A REFUSAL. Having a second
    mechanism silently pick a directory would put the answer back in two homes, and the
    writer being cleverer than its readers is not an improvement -- it would write where
    nothing looks. So when the resolved root turns out to hold none of the three names
    and some other directory does, this stops and says which, rather than choosing. The
    walk costs one millisecond over 19 directories and 383 files.

    A DIRECTORY NAMED OUTRIGHT IS NOT SECOND-GUESSED, and this is written down because
    the first draft of this function got it wrong and a calibration run caught it. An
    override pointing at an empty directory is the ordinary way to start a build
    somewhere else, so treating an empty override as the "resolved root holds none of
    them" case turned a legitimate request into a refusal. Whoever sets the variable has
    already answered the question the walk exists to ask.

    Names that are nowhere at all are the ordinary state of a fresh clone, where all
    three are gitignored and the producer has not run yet. That is not an error and does
    not stop anything: the resolved root stands, and the first run creates them there.
    """
    root = P.data_root(env_names=DATA_ROOT_ENV)
    if (os.environ.get(DATA_ROOT_ENV[0]) or "").strip():
        return root
    if any(_holds(root, name, kind) for name, kind in _WANTED):
        return root
    found = _look_for_them()
    if found:
        detail = "; ".join(
            f"{name} in " + ", ".join(sorted(os.path.relpath(d, _CODE_DIR)
                                             for d in found[name]))
            for name, _kind in _WANTED if name in found)
        raise SystemExit(
            f"[panel_v2] the v2 panel, its taker map and its shards are not in "
            f"{os.path.relpath(root, _CODE_DIR)}, which is the directory this "
            f"repository resolves the intermediates to, but they are here: {detail}. "
            f"Refusing to choose between the two: this builder WRITES all three, and "
            f"guessing wrong costs a 572 MB panel in a directory no reader opens plus "
            f"the tape reparse to produce it. Move them to the resolved directory, or "
            f"name the one they are in with PANEL_V2_DATA_ROOT.")
    return root


def _holds(directory, name, kind):
    """Whether `directory` holds `name` as the kind of thing it is supposed to be."""
    path = os.path.join(directory, name)
    return os.path.isdir(path) if kind == "dir" else os.path.isfile(path)


def _look_for_them():
    """Every directory under the repository answering to any of the three names."""
    found = {}
    for dirpath, dirnames, filenames in os.walk(_CODE_DIR):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for name, kind in _WANTED:
            if name in (dirnames if kind == "dir" else filenames):
                found.setdefault(name, []).append(dirpath)
    return found


DATA_ROOT = _v2_data_root()
# The NAME stays the last component of each join, which is not a matter of taste. The
# build graph derives an input edge from the folded argument of a read and an output
# edge from the folded argument of a write, and it folds a helper call only when the
# helper has exactly one return. A resolver that refuses an ambiguity has several, so
# handing back a DIRECTORY and joining the name here is what keeps these three writes
# inside the graph instead of adding them to its residue of unaccounted I/O.
PANEL_NPZ_PATH = os.path.join(DATA_ROOT, PANEL_NPZ_NAME)
PANEL_TAKER_MAP_PATH = os.path.join(DATA_ROOT, PANEL_TAKER_MAP_NAME)
CKPT_DIR = os.path.join(DATA_ROOT, CKPT_DIR_NAME)

# The name this builder stamps into the file it writes. Three files in this
# directory assemble a panel npz and the artifacts used to carry no producer name,
# so a file could only be attributed by comparing key orders and row counts.
BUILDER_NAME = ("panel_rebuild_v2.py (the eight-window panel PLUS block_time_ns "
                "and is_liq; writes panel_markouts_v2.npz, never "
                "panel_markouts.npz)")
BUILDER_WALLET_ID_SCOPE = (
    "taker_id and maker_id are GLOBAL first-seen codes over the wallet HEX STRING "
    "across every shard in panel_ckpt_v2/, the same rule panel_persistence.py "
    "--build uses, so one wallet carries ONE code in every month and every coin and "
    "the cross-month join is valid. panel_build.py's ids are per-cell composites and "
    "do NOT have this property; its file supports no wallet-level hold-out.")
# A pure BUILD computes no statistic, so none of the four migrating declarations
# H.fingerprint tracks applies to it. Naming them beats letting them read as
# unanswered in the block.
BUILD_SETTINGS_OVERRIDES = {
    "settings_not_used": ["master_seed", "n_perm", "n_boot", "rank_floor_fills"]}

BUILDER_DIFF_FROM_V1 = (
    "Identical to panel_persistence.py --build in windows, coins, sweep collapse, "
    "as-of markout, maker resolution, columns, dtypes and coding, plus exactly two "
    "additive per-row columns: block_time_ns (int64 native ns block_time of the "
    "taker leg, which the v1 build computes and then drops in favour of day) and "
    "is_liq (int8, 1 when any leg of the collapsed sweep carries the nested "
    "liquidation object).")


# ===========================================================================
# parse_day_v2 - VERBATIM build_quickwin_markouts.parse_day + two additive fields
# ===========================================================================
# The body below is a line-for-line copy of bq.parse_day; the ONLY changes are
# marked `# v2:` and add (a) is_liq tracking through the sweep collapse and
# (b) taker_block_ns / taker_isliq in the emitted per_coin dict. The print-
# reference path, crossed split, earliest-leg carries, closedPnl sum, and
# dominant-maker resolution are unchanged, so BTC/ETH/SOL markouts reproduce
# the verified panel exactly.
def parse_day_v2(day):
    """Parse panel-coin fills for `day`, collapsing taker sweeps to one trade,
    carrying the native taker block_time AND a liquidation marker.

    Identical to build_quickwin_markouts.parse_day except the collapse record
    also OR-accumulates `is_liq` (1 if any leg of the (hash, taker) sweep carries
    the nested `liquidation` object), and per_coin additionally returns
    taker_block_ns (the earliest-leg native ns block_time, == taker_ts) and
    taker_isliq.
    """
    day_dir = bq.download_day(day)
    if day_dir is None:
        return None, []

    print_ts_by_hash = {c: {} for c in bq.COINS}
    print_pxsz_by_hash = {c: {} for c in bq.COINS}
    taker_collapsed = {c: {} for c in bq.COINS}
    maker_size_by_hash = {c: {} for c in bq.COINS}
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
            for raw in bq.iter_local_hour_lines(path):
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
                    if h == bq.ZERO_HASH or h is None:
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
                        d_str = f.get("dir")
                        is_open = 1 if d_str in bq.OPEN_DIRS else 0
                        dir_code = bq.DIR_CODE.get(d_str, bq.DIR_UNKNOWN)
                        sp_raw = f.get("startPosition")
                        try:
                            start_pos = float(sp_raw) if sp_raw is not None else float("nan")
                        except (TypeError, ValueError):
                            start_pos = float("nan")
                        cp_raw = f.get("closedPnl")
                        try:
                            closed_pnl = float(cp_raw) if cp_raw is not None else 0.0
                        except (TypeError, ValueError):
                            closed_pnl = 0.0
                        side_b = 1 if f.get("side") == "B" else 0
                        # v2: liquidation marker on THIS taker leg. The nested
                        # `liquidation` object {liquidatedUser, markPx, method} is
                        # present ONLY on liquidation fills (verified on raw bytes);
                        # detect by key presence, robust to a null payload.
                        leg_liq = 1 if (f.get("liquidation") is not None) else 0
                        tc = taker_collapsed[coin]
                        if key not in tc:
                            # [pxsz_sum, sz_sum, min_bt_ns, dir(+1/-1),
                            #  is_open(at min_bt), start_pos(at min_bt), side_b,
                            #  closed_pnl_sum, dir_code(at min_bt), is_liq(OR)]   # v2
                            tc[key] = [px * sz, sz, bt_ns,
                                       1 if f.get("side") == "B" else -1,
                                       is_open, start_pos, side_b,
                                       closed_pnl, dir_code, leg_liq]   # v2
                        else:
                            rec = tc[key]
                            rec[0] += px * sz
                            rec[1] += sz
                            rec[7] += closed_pnl   # accumulate realized PnL over legs
                            rec[9] = rec[9] | leg_liq   # v2: OR liq across legs
                            # keep is_open/start_pos/side/dir_code from earliest leg
                            if bt_ns < rec[2]:
                                rec[2] = bt_ns
                                rec[4] = is_open
                                rec[5] = start_pos
                                rec[6] = side_b
                                rec[8] = dir_code
                    elif f.get("crossed") is False:
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
            print(f"[panel_v2] {day} {hf}: parse error {exc}")
    # Deletion is the DEFAULT and it is DECLARED, not wired into the code. Both keys are
    # read through build_quickwin_markouts so the rule keeps one home -- CAP_RAW_CACHE
    # says where a fetched day lives, CAP_KEEP_RAW says whether it survives the run --
    # and restating either of them here would be a second copy that goes stale the first
    # time the rule changes there. The day this file walks is the same directory
    # bq.download_day filled, so a day kept here is a day the other tape walkers read
    # instead of fetching again. The line prints either way, so the run log says which
    # happened rather than leaving it to be inferred from a missing directory.
    if bq.keep_raw_days():
        print(f"[panel_v2] {day}: raw kept on disk (CAP_KEEP_RAW; see CAP_RAW_CACHE)")
    else:
        shutil.rmtree(day_dir, ignore_errors=True)
        print(f"[panel_v2] {day}: raw deleted (default; set CAP_KEEP_RAW=1 to keep)")

    per_coin = {}
    for c in bq.COINS:
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
        t_size = np.empty(n, dtype=np.float64)
        t_side = np.empty(n, dtype=np.int8)
        t_cpnl = np.empty(n, dtype=np.float64)
        t_dcode = np.empty(n, dtype=np.int8)
        t_maddr = np.empty(n, dtype=object)
        t_isliq = np.empty(n, dtype=np.int8)          # v2: liquidation marker
        for i, (rec, key) in enumerate(zip(recs, keys)):
            (pxsz, szsum, ts, d, is_open, start_pos, side_b,
             closed_pnl, dir_code, is_liq) = rec       # v2: 10-field record
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
            t_maddr[i] = dominant_maker.get(key[0])
            t_isliq[i] = is_liq                        # v2
        per_coin[c] = {"taker_ts": t_ts, "taker_px": t_px, "taker_dir": t_dir,
                       "taker_addr": t_addr, "taker_open": t_open,
                       "taker_spos": t_spos, "taker_size": t_size,
                       "taker_side": t_side,
                       "taker_cpnl": t_cpnl, "taker_dcode": t_dcode,
                       "maker_addr": t_maddr,
                       # v2 additive outputs. taker_block_ns is identical to
                       # taker_ts (the earliest-leg native ns block_time); it is
                       # surfaced under its own name so persist keeps it as the
                       # block_time_ns column instead of dropping it for `day`.
                       "taker_block_ns": t_ts.copy(),
                       "taker_isliq": t_isliq,
                       "print_ts": print_ts, "print_px": print_px}
    return per_coin, hours_ok


# ===========================================================================
# BUILDER (parse the coin-month cells -> panel_markouts_v2.npz)
# ===========================================================================
def _cell_shard_path(coin, period):
    return os.path.join(CKPT_DIR, f"shard_{coin}_{period}.npz")


def _cell_done(coin, period):
    """A cell is done iff its shard .npz exists, loads, AND carries the v2 columns.

    The v2-column check means a shard left over from a hypothetical non-v2 run
    can never be mistaken for done; only a shard with block_time_ns + is_liq
    counts (defensive - panel_ckpt_v2/ is a fresh dir anyway)."""
    p = _cell_shard_path(coin, period)
    if not os.path.exists(p):
        return False
    try:
        with np.load(p, allow_pickle=True) as _z:
            _ = _z["taker_addr"]
            _ = _z["block_time_ns"]      # v2 column must be present
            _ = _z["is_liq"]             # v2 column must be present
        return True
    except Exception:
        return False


def _build_one_period(period, days, coins):
    """Parse every day of one window and write a per-(coin,month) v2 shard.

    Mirrors panel_persistence._build_one_period: per-cell checkpoint (a present
    shard SKIPS the cell), parse via parse_day_v2 (hardened download inside),
    markout via bq.compute_markouts_all, accumulate per-coin day columns, save
    one shard per (coin, period). Adds block_time_ns + is_liq to every shard.
    """
    os.makedirs(CKPT_DIR, exist_ok=True)

    pending = [c for c in coins if not _cell_done(c, period)]
    if not pending:
        print(f"[panel_v2] period {period}: all cells present, SKIP "
              f"({', '.join(coins)})")
        return {c: "skipped" for c in coins}

    acc = {c: {k: [] for k in
               ("addr", "coin", "day", "entry_px", "mo1", "mo10", "mo60",
                "notional", "is_open", "start_pos", "taker_side", "closed_pnl",
                "dir_code", "maker_addr",
                "block_time_ns", "is_liq")} for c in pending}     # v2 keys
    issues = []
    resolved = []

    for day in days:
        day_num = int(day[6:8])
        per_coin, hours_ok = parse_day_v2(day)     # hardened download + parse inside
        if per_coin is None:
            issues.append(f"{period} day {day} missing on S3 - skipped")
            print(f"[panel_v2] {period} day {day} MISSING on S3 - skipped")
            continue
        resolved.append(day)
        if len(hours_ok) < 24:
            issues.append(f"{period} {day}: {len(hours_ok)}/24 hours")

        for coin in pending:
            d = per_coin.get(coin)
            if d is None:
                continue
            n_trades = int(d["taker_ts"].size)
            if n_trades == 0 or d["print_ts"].size == 0:
                issues.append(f"{coin} {period} {day}: empty")
                print(f"[panel_v2] SLICE {coin} {period} {day}: empty")
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
            a["block_time_ns"].extend(d["taker_block_ns"].tolist())   # v2
            a["is_liq"].extend(d["taker_isliq"].tolist())             # v2
            g60 = mo[60][~np.isnan(mo[60])]
            n_liq = int(np.sum(d["taker_isliq"]))
            print(f"[panel_v2] SLICE {coin} {period} {day}: trades={n_trades:,} "
                  f"mo60={(float(np.mean(g60)) if g60.size else float('nan')):+.4f} "
                  f"is_liq={n_liq}")

    status = {}
    for coin in pending:
        a = acc[coin]
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
            block_time_ns=np.asarray(a["block_time_ns"], dtype=np.int64),   # v2
            is_liq=np.asarray(a["is_liq"], dtype=np.int8),                  # v2
            _resolved_days=np.asarray(resolved, dtype=object),
            _issues=np.asarray(issues, dtype=object),
        )
        n_liq_cell = int(np.sum(np.asarray(a["is_liq"], dtype=np.int8))) if a["is_liq"] else 0
        status[coin] = (f"built ({len(a['addr']):,} rows, {len(resolved)} days, "
                        f"is_liq={n_liq_cell})")
        print(f"[panel_v2] CELL {coin} {period}: {status[coin]}")
    return status


def build_panel(coins, periods_to_build, only_days=None, started=None):
    """Build the requested (coin, month) shards, then assemble panel_markouts_v2.npz.

    Mirrors panel_persistence.build_panel. only_days restricts each window to a
    subset of its day labels (the CAP_DAYS smoke path). Shards already on disk
    are SKIPPED. The final npz is the verified panel schema PLUS block_time_ns
    and is_liq, written ONLY to v2 paths.
    """
    print(f"[panel_v2] BUILD coins={coins} periods={periods_to_build} "
          f"days={only_days or 'ALL'} data_root={os.path.basename(DATA_ROOT)}")
    for period in periods_to_build:
        days = PERIOD_DAYS[period]
        if only_days is not None:
            req = set(only_days)
            days = [d for d in days if d in req]
            if not days:
                print(f"[panel_v2] period {period}: none of {sorted(req)} in "
                      f"window - SKIP")
                continue
        _build_one_period(period, days, coins)
    # The clock is handed down from the caller so the manifest's runtime covers the
    # parsing as well as the assembly. A shard already on disk is skipped, so a run
    # that reuses all twenty-four is minutes rather than hours, and the recorded
    # runtime says which of the two happened without anyone having to remember.
    return assemble_panel_npz(started)


def assemble_panel_npz(started=None):
    """Concatenate every present v2 shard into panel_markouts_v2.npz with a
    shared first-seen taker/maker integer coding (one code per wallet across all
    months - what makes the cross-month join valid). Carries block_time_ns +
    is_liq. Writes ONLY v2 paths."""
    started = artifact.start_clock() if started is None else started
    if not os.path.isdir(CKPT_DIR):
        raise SystemExit(f"[panel_v2] no checkpoint dir "
                         f"{os.path.basename(CKPT_DIR)} - run a build first.")
    shard_files = sorted(f for f in os.listdir(CKPT_DIR)
                         if f.startswith("shard_") and f.endswith(".npz"))
    if not shard_files:
        raise SystemExit("[panel_v2] no shards present - nothing to assemble.")

    cols = {k: [] for k in
            ("taker_addr", "coin", "day", "period", "entry_px", "mo1", "mo10",
             "mo60", "notional", "is_open", "start_pos", "taker_side",
             "closed_pnl", "dir_code", "maker_addr",
             "block_time_ns", "is_liq")}                        # v2 keys
    resolved_all, issues_all = {}, []
    for sf in shard_files:
        with np.load(os.path.join(CKPT_DIR, sf), allow_pickle=True) as z:
            n = int(z["coin"].shape[0])
            if n == 0:
                rd = [str(x) for x in z["_resolved_days"].tolist()]
                resolved_all[sf] = rd
                issues_all.extend(str(x) for x in z["_issues"].tolist())
                continue
            for k in cols:
                cols[k].extend(z[k].tolist())
            resolved_all[sf] = [str(x) for x in z["_resolved_days"].tolist()]
            issues_all.extend(str(x) for x in z["_issues"].tolist())

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
        period=np.asarray(cols["period"], dtype=np.int64),
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
        block_time_ns=np.asarray(cols["block_time_ns"], dtype=np.int64),   # v2
        is_liq=np.asarray(cols["is_liq"], dtype=np.int8),                  # v2
        # ---- provenance, written LAST so the seventeen data columns keep their
        # positions for a reader that indexes z.files instead of naming a key ----
        _builder=np.asarray(BUILDER_NAME),
        _builder_wallet_id_scope=np.asarray(BUILDER_WALLET_ID_SCOPE),
        _builder_diff_from_v1=np.asarray(BUILDER_DIFF_FROM_V1),
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

    n_liq = int(np.sum(np.asarray(cols["is_liq"], dtype=np.int8)))
    print(f"[panel_v2] assembled {PANEL_NPZ_NAME}: rows={taker_id.size:,} "
          f"takers={len(wallet_to_code):,} "
          f"is_liq={n_liq} ({(100.0 * n_liq / max(taker_id.size, 1)):.4f}%) "
          f"periods={sorted(set(int(p) for p in cols['period']))}")
    summary = {"rows": int(taker_id.size), "n_takers": len(wallet_to_code),
               "n_liq": n_liq, "resolved_by_shard": resolved_all,
               "issues": issues_all}
    _write_manifest(started, shard_files, summary, sorted(
        set(int(p) for p in cols["period"])))
    return summary


# ---------------------------------------------------------------------------
# THE SIDECAR, AND WHY A RECOMPUTE COULD NEVER HAVE REPLACED IT
#
# Added 2026-08-04. The debt this file carried since that morning said the way to make
# the v2 panel answerable was one full run through the shared artifact writer. That was
# wrong about the mechanism, and the measurement that showed it is cheap: the output is
# an .npz, which is a zip of arrays and has nowhere to keep a _meta block, so no run of
# any length can give it a producer hash. The two freshness gates read .json and count
# every .npz, .png, .csv and .parquet in the tree as outside their range entirely --
# seven files on 2026-08-04, this panel among them. A three-hour rerun would have
# changed the bytes and left the question exactly as unanswerable as before.
#
# What answers it is a companion record that IS a .json and IS written by the shared
# writer: the producer and its hash, the twenty-four shards as declared inputs each with
# its own hash, and the assembled panel's hash and size as the quantity. From then on
# "has this panel moved" and "was it built by the code on disk" are both hash
# comparisons, and the arrays keep the internal provenance keys they already carried for
# a reader who opens the npz itself.
#
# WHAT THE SHARDS ARE HERE AND WHAT THEY ARE NOT. They are INPUTS to this assembly, not
# products of it: a cell whose shard is already on disk is skipped, so the shards may
# well have been parsed by an older revision of this file. Hashing them records that
# state instead of hiding it, and a shard reparsed later moves its hash and marks this
# panel stale, which is the behaviour the tape half of the debt actually needed.
# ---------------------------------------------------------------------------

MANIFEST_NAME = "panel_v2_manifest.json"


def _write_manifest(started, shard_files, summary, periods):
    """The companion record that makes an .npz answerable to the freshness gates."""
    payload = {
        "panel": {
            "file": PANEL_NPZ_NAME,
            "sha256": artifact.sha256_file(PANEL_NPZ_PATH),
            "bytes": os.path.getsize(PANEL_NPZ_PATH),
            "rows": summary["rows"],
            "n_takers": summary["n_takers"],
            "n_liq": summary["n_liq"],
            "periods_assembled": periods,
        },
        "taker_map": {
            "file": os.path.basename(PANEL_TAKER_MAP_PATH),
            "sha256": artifact.sha256_file(PANEL_TAKER_MAP_PATH),
            "bytes": os.path.getsize(PANEL_TAKER_MAP_PATH),
            "why_it_is_not_in_the_census": "matched by the panel_taker_map* ignore "
                                           "rule, so the provenance census drops it; "
                                           "its hash is recorded here instead",
        },
        "shards": [
            {"file": name,
             "sha256": artifact.sha256_file(os.path.join(CKPT_DIR, name)),
             "bytes": os.path.getsize(os.path.join(CKPT_DIR, name))}
            for name in shard_files
        ],
        "issues": summary["issues"],
    }
    artifact.write(
        MANIFEST_NAME, payload,
        script=__file__,
        # The shards are handed over at the address they were actually read from, not as
        # a bare relative name, and the difference is whether this record depends on
        # where the run was launched from. artifact.input_record tries a relative spec
        # against the PRODUCER's own directory first and the working directory second.
        # Once this file moved into a group directory the first candidate pointed one
        # level below the shards, so the record was decided entirely by the second, and
        # measured on this tree the same shard came out present=true when the run was
        # launched from the repository root and present=false from either the directory
        # named in the run line at the top of this file or from this file's own
        # directory. That is the exact defect input_record's docstring says it exists to
        # prevent -- one producer recording a hash from one place and an absence from
        # another -- and an absolute spec, tried before both, ends it. Nothing local
        # leaks into the artifact by passing the full path: artifact._record_name
        # collapses a local path to its basename precisely so that the directory, which
        # names the machine and reproduces nowhere, stays out of a published record.
        inputs=[os.path.join(CKPT_DIR, name) for name in shard_files],
        scope={
            "population": f"{summary['rows']} taker fills assembled from "
                          f"{len(shard_files)} per (coin, month) shards",
            "window": f"{len(periods)} ten-day windows: {periods}",
            "coins": list(PANEL_COINS),
        },
        started=started,
        extra_meta={"builder": BUILDER_NAME,
                    "what_this_record_is_for":
                        "the assembled panel is an .npz and can carry no _meta block, "
                        "so this companion .json holds its hash and the hashes of "
                        "every shard it was built from"},
    )
    print(f"[panel_v2] wrote {MANIFEST_NAME}: panel sha256 "
          f"{payload['panel']['sha256'][:12]}, {len(shard_files)} shards hashed")


# ===========================================================================
# main
# ===========================================================================
def main():
    coins = SMOKE_COINS if SMOKE_COINS is not None else list(PANEL_COINS)
    # Restrict periods to those that contain a requested smoke day (keeps the
    # smoke from touching unrelated windows); else build all panel windows.
    if SMOKE_DAYS is not None:
        req = set(SMOKE_DAYS)
        periods_to_build = tuple(p for p in PERIODS
                                 if any(d in req for d in PERIOD_DAYS[p]))
        if not periods_to_build:
            raise SystemExit(f"[panel_v2] CAP_DAYS={SMOKE_DAYS} matches no day "
                             f"in any configured window {PERIODS}")
        only_days = SMOKE_DAYS
        print(f"[panel_v2] SMOKE: CAP_DAYS={SMOKE_DAYS} CAP_COINS={coins} "
              f"-> periods {periods_to_build}")
    else:
        periods_to_build = PERIODS
        only_days = None

    build_panel(coins, periods_to_build, only_days=only_days,
                started=artifact.start_clock())


if __name__ == "__main__":
    main()
