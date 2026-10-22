#!/usr/bin/env bash
#
# run_step1_data.sh
#
# Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin
# Author: Dmitry Stakhin | Date: 2026-07-29
# Academic Integrity: This work represents my own effort. Sources cited below.
# References: Hyperliquid node-data S3 archive (s3://hl-mainnet-node-data, fills);
# Hyperliquid market-data L2 book S3 archive (s3://hyperliquid-archive/market_data);
# Zenodo 18184441 (Albers, Cucuringu, Howison and Shestopaloff, "An Open Book", 2026).
# Drives, without altering, build_quickwin_markouts.py, panel_persistence.py,
# panel_rebuild_v2.py, i4_l2_mid.py, i4_midmarkout.py, run_panel_l2.sh and the
# read-only inventory in step1_inventory.py.
#
# ---------------------------------------------------------------------------
# WHAT THIS IS. The single entry point for the data acquisition stage. Every
# individual piece of that stage was already committed, but the order they run in
# and the state they expect lived in one person's head. This script writes both
# down and makes them executable, so a reviewer with their own AWS credentials
# runs one command and ends up with our inputs, and is told plainly when what they
# got does not match what we describe.
#
# TWO MODES.
#   verify  (default)  Downloads nothing. Opens what is on disk, prints one
#                      inventory table per coin and window, and compares every
#                      figure against the values recorded in step1_inventory.py.
#                      This is the cheap thing to run first.
#   build              Performs the acquisition in dependency order. Each stage is
#                      skipped when its outputs already exist, so an interrupted
#                      run resumes instead of re-paying for bytes already fetched.
#
# YOU ALMOST CERTAINLY DO NOT NEED BUILD MODE. The reproducibility notebook in
# notebooks/ recomputes every reported number from our published dataset with no
# AWS account and no payment. Build mode exists for someone rebuilding the inputs
# from the archive itself.
#
# COST. Both buckets are requester-pays, so the caller's own AWS account is billed
# for the GET requests and the egress. Measured on 2026-07-29 for the book, scaled
# from the recorded panel build for the fills:
#   December book   480 objects, about 0.6 GB.
#   Panel book      5,760 objects, about 7.6 GB and about 90 minutes on a home
#                   connection.
#   Fills           far larger. An hourly node_fills file carries every coin, so a
#                   calendar day is pulled once no matter how many coins are read.
#                   The recorded three-window panel pull moved about 14.5 GB over
#                   30 calendar days, which puts the eight-window panel plus
#                   December on the order of 40 GB. That figure is scaled from the
#                   recorded run, not measured end to end.
#   The book-mid join re-parses the December fills through
#   build_quickwin_markouts.parse_day, so it pays that ten-day fills egress a
#   second time even though quickwin_markouts.npz already exists.
#
# DISK. The finished artifacts occupy about 4 GB. On top of that the pull needs
# transient room: the fills stream one day at a time and discard it, and the panel
# book deletes each window's raw cache once that window is parsed, which holds the
# transient peak near 1 GB. Build mode refuses to start when free space is below
# what the stages it still has to run require.
#
# COMPLETENESS OVER RETRIES. i4_l2_mid.py skips a missing hour with a warning and
# emits a short series that is indistinguishable from a complete one, and this
# project has already been bitten once by a dropped connection silently marking
# three December days absent. So each stage is gated on completeness before
# anything derived is built: a missing hour stops that window instead of quietly
# shortening it.
#
# Run, from the repository root, which is the form README.md gives for every
# entry point:
#   bash run/run_step1_data.sh          inventory only, nothing is downloaded
#   bash run/run_step1_data.sh build    acquire what is missing, then inventory
#   bash run/run_step1_data.sh --help
# ---------------------------------------------------------------------------

set -euo pipefail

# This runner moved into run/ on 2026-08-30, beside the nine entry points it
# belongs with. Every path below is relative to the REPOSITORY ROOT, so the
# cd climbs one level out of this directory. Without the climb the move is
# silent and total: dirname "$0" would land in run/, requirements.txt and
# every script path would miss, and the run would fail on its first line
# rather than say why.
cd "$(dirname "$0")/.."
CODE="$(pwd)"
# The pinned environment rather than a bare package name. --with numpy resolves numpy
# fresh on the day of the run: measured on 2026-08-13 it installed 2.5.2 against the
# 2.4.6 requirements.txt pins, said nothing about the substitution, and did not install
# matplotlib at all. --with-requirements reads the pins, and it is the form README.md
# already gives for every other entry point.
RUNPY="uv run --no-project --with-requirements requirements.txt python3"
LOG="$CODE/step1_data_run.log"

BOOK_BUCKET="s3://hyperliquid-archive/market_data"
# DEC_CACHE is resolved in the BUILD section below rather than here, because it is the
# only thing here that depends on a directory outside the repository and verify mode
# does not read it at all. Resolving it here is what used to make --help and verify
# fail on a clone.
DEC_DAYS="20251204 20251205 20251206 20251207 20251208 20251209 20251210 20251211 20251212 20251213"
DEC_COINS="BTC ETH"
PANEL_PERIODS="202508 202509 202510 202511 202512 202601 202603 202605"
PANEL_COINS="BTC ETH SOL"

# Free space each stage needs, in MB: its own outputs plus its transient cache
# plus headroom. Only the stages that still have work to do are counted.
NEED_DEC_FILLS=1000
NEED_PANEL_FILLS=3500
NEED_DEC_BOOK=1000
NEED_PANEL_BOOK=2500
NEED_BOOK_MID=700

MODE="${1:-verify}"

case "$MODE" in
  -h|--help|help)
    # Print the header comment block, whatever length it has grown to: every line
    # after the shebang up to the first line that is not a comment.
    awk 'NR > 1 { if ($0 !~ /^#/) exit; sub(/^# ?/, ""); print }' "$0"
    exit 0
    ;;
  verify|build) ;;
  *)
    echo "run_step1_data.sh: unknown mode '$MODE'. Use verify (default) or build." >&2
    exit 2
    ;;
esac

banner() {
  echo ""
  echo "================================================================"
  echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] $*"
  echo "================================================================"
}

# ---------------------------------------------------------------------------
# VERIFY: read-only, and the default. Its exit status is this script's.
# ---------------------------------------------------------------------------
if [ "$MODE" = "verify" ]; then
  exec $RUNPY data/step1_inventory.py
fi

# ---------------------------------------------------------------------------
# BUILD. Everything below fetches bytes you pay for.
# ---------------------------------------------------------------------------
exec > >(tee -a "$LOG") 2>&1

# --- where the data directory is -------------------------------------------
# Resolution order, first hit wins, and nothing absolute is written down:
#   1. CAP_DATA_ROOT, which is the name identity/i3_book_comparator.py already reads
#      for exactly this idea: the root that HOLDS l2_cache. It is only READ here and
#      never exported, because panel_io.py reads the same name for a different
#      directory, the one holding the .npz panels, and exporting it would point every
#      panel reader in the five stages below at the raw cache instead.
#   2. the 02_data directory beside the repository, which is where a full checkout of
#      the parent workspace keeps it. This is what this script used to demand.
#   3. a directory inside the repository itself, which is the branch a reader who
#      cloned this repository ON ITS OWN takes: 02_data is a sibling of the
#      repository and does not travel with the clone.
# The resolved directory is then created, because a cache directory that does not
# exist yet is the normal state of a first run and not an error.
#
# WHY THIS IS NINE LINES AND NOT ONE, AND WHY IT SITS HERE AND NOT WITH THE OTHER
# CONSTANTS. It was one line up there, and the line was
# DATA_DIR="$(cd "$CODE/../02_data" && pwd)". Under set -e that cd ends the script on
# its fourth line for anyone whose 02_data is not there, and because it stood above
# the mode check it took --help and verify mode down with it -- so the one mode that
# downloads nothing, reads nothing outside the repository and exists to be run first
# could not run at all on a clone. Measured on a fresh clone, the default run and --help:
# cd: .../02_data: No such file or directory, exit 1, nothing else printed.
# checks/chk_input_freshness.py states the same fact about a lone clone and builds
# its own fixture around it. run_i4.sh and run_panel_l2.sh carry the same block, and
# run_panel_l2.sh is called whole by stage 4 below, so both resolve the directory
# from the same repository root and both land on the same one.
if [ -n "${CAP_DATA_ROOT:-}" ]; then
  DATA_DIR="$CAP_DATA_ROOT"
elif [ -d "$CODE/../02_data" ]; then
  DATA_DIR="$CODE/../02_data"
else
  DATA_DIR="$CODE/data_cache"
fi
mkdir -p "$DATA_DIR"
DATA_DIR="$(cd "$DATA_DIR" && pwd)"
DEC_CACHE="$DATA_DIR/l2_cache"

# --- which stages still have work to do -----------------------------------
have_dec_fills()  { [ -f "$CODE/quickwin_markouts.npz" ]; }
have_panel_fills() {
  [ -f "$CODE/panel_markouts.npz" ] && [ -f "$CODE/panel_markouts_v2.npz" ]
}
have_dec_book() {
  for c in $DEC_COINS; do
    [ -f "$CODE/mid_series_${c}.npz" ] || return 1
  done
  return 0
}
have_panel_book() {
  for p in $PANEL_PERIODS; do
    for c in $PANEL_COINS; do
      [ -f "$CODE/mid_series_${c}_${p}.npz" ] || return 1
    done
  done
  return 0
}
have_book_mid() { [ -f "$CODE/quickwin_markouts_mid.npz" ]; }

need_mb=0
pending=""
have_dec_fills   || { need_mb=$((need_mb + NEED_DEC_FILLS));   pending="$pending december-fills"; }
have_panel_fills || { need_mb=$((need_mb + NEED_PANEL_FILLS)); pending="$pending panel-fills"; }
have_dec_book    || { need_mb=$((need_mb + NEED_DEC_BOOK));    pending="$pending december-book"; }
have_panel_book  || { need_mb=$((need_mb + NEED_PANEL_BOOK));  pending="$pending panel-book"; }
have_book_mid    || { need_mb=$((need_mb + NEED_BOOK_MID));    pending="$pending book-mid-join"; }

banner "run_step1_data BUILD"
echo "Both S3 buckets are requester-pays. Your own AWS account is billed for the"
echo "GET requests and the egress this run makes. The reproducibility notebook in"
echo "notebooks/ reproduces every reported number for free; you need this path only"
echo "to rebuild the inputs from the archive."
echo ""
if [ -z "$pending" ]; then
  echo "Every stage output is already on disk. Nothing will be downloaded."
else
  echo "Stages still to run:$pending"
  echo "Estimated free space needed: ${need_mb} MB."
fi

free_mb=$(df -Pk "$CODE" | awk 'END {print int($4 / 1024)}')
echo "Free space on this volume: ${free_mb} MB."
if [ "$need_mb" -gt 0 ] && [ "$free_mb" -lt "$need_mb" ]; then
  echo ""
  echo "REFUSING TO START: ${free_mb} MB free is under the ${need_mb} MB the pending"
  echo "stages need. A pull that runs out of room mid-window leaves a short series"
  echo "that looks complete, which is the one failure this runner exists to prevent."
  echo "Free space, or run a subset by letting the finished stages stay on disk."
  exit 1
fi

# --- stage 1: December fills ----------------------------------------------
if have_dec_fills; then
  banner "STAGE 1/5  December fills - quickwin_markouts.npz present, skipped"
else
  banner "STAGE 1/5  December fills  (s3://hl-mainnet-node-data, 10 days, BTC+ETH)"
  $RUNPY data/build_quickwin_markouts.py
  banner "STAGE 1/5  completeness gate"
  if ! $RUNPY data/step1_inventory.py --hours-gate december; then
    echo "December fills are short of a full day. Stopping before anything derived"
    echo "is built. Re-run this script to retry the stage."
    exit 1
  fi
fi

# --- stage 2: panel fills --------------------------------------------------
# panel_persistence.py --build checkpoints one shard per (coin, window) and skips
# shards already on disk, so a mid-pull failure resumes rather than re-pulling.
# panel_rebuild_v2.py re-parses the same grid carrying block_time_ns and is_liq.
if have_panel_fills; then
  banner "STAGE 2/5  panel fills - panel_markouts.npz and _v2 present, skipped"
else
  if [ ! -f "$CODE/panel_markouts.npz" ]; then
    banner "STAGE 2/5  panel fills  (8 windows x BTC/ETH/SOL, trade-print markout)"
    $RUNPY data/panel_persistence.py --build
  else
    echo "[stage 2] panel_markouts.npz present, building only the v2 rebuild."
  fi
  if [ ! -f "$CODE/panel_markouts_v2.npz" ]; then
    banner "STAGE 2/5  panel fills v2  (adds block_time_ns and is_liq)"
    $RUNPY data/panel_rebuild_v2.py
  fi
  banner "STAGE 2/5  completeness gate"
  if ! $RUNPY data/step1_inventory.py --hours-gate panel; then
    echo "A panel window is short of a full day. Its row counts will not match the"
    echo "recorded values and any measure built on it is short. Delete that window's"
    echo "shard and re-run this script to re-pull it."
    exit 1
  fi
fi

# --- stage 3: December book -----------------------------------------------
# i4_l2_mid.py downloads a single missing hour itself, but one object at a time.
# Syncing the window in bulk first is cheaper in requests and lets the file count
# be asserted before any series is built.
if have_dec_book; then
  banner "STAGE 3/5  December book - mid_series_{BTC,ETH}.npz present, skipped"
else
  banner "STAGE 3/5  December book sync  ($BOOK_BUCKET -> l2_cache)"
  for d in $DEC_DAYS; do
    for attempt in 1 2 3 4; do
      echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] sync day $d (attempt $attempt)"
      if aws s3 sync \
          "$BOOK_BUCKET/$d/" \
          "$DEC_CACHE/$d/" \
          --request-payer requester \
          --exclude '*' \
          --include '*/l2Book/BTC.lz4' \
          --include '*/l2Book/ETH.lz4' \
          --only-show-errors; then
        break
      fi
      echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] day $d attempt $attempt failed, retrying"
      sleep 20
    done
  done

  # Completeness gate: 10 days x 24 hours x 2 coins = 480 files, no exceptions.
  # The count is guarded rather than piped straight from find, because under
  # pipefail a find over a cache directory that no sync ever created returns
  # non-zero and would end the run here with nothing printed.
  n_files=0
  if [ -d "$DEC_CACHE" ]; then
    n_files=$(find "$DEC_CACHE" -name '*.lz4' | wc -l | tr -d ' ')
  fi
  want=$(( $(echo $DEC_DAYS | wc -w | tr -d ' ') * 24 * $(echo $DEC_COINS | wc -w | tr -d ' ') ))
  echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] December book cache holds $n_files of $want expected files"
  if [ "$n_files" -ne "$want" ]; then
    echo "December book cache is incomplete ($n_files/$want). NOT building the mid"
    echo "series: a missing hour would produce a short series that reads as complete."
    echo "The raw cache is kept so a re-run resumes."
    exit 1
  fi

  banner "STAGE 3/5  i4_l2_mid.py  (mid_series_{BTC,ETH}.npz)"
  # The cache the sync above just filled is named to the reader instead of being left
  # to coincide with its default. i4_l2_mid.py falls back to ../02_data/l2_cache when
  # CAP_L2_CACHE is unset, which equals DEC_CACHE only while 02_data is where the
  # resolution above landed; on a lone clone it is not, and this stage would read an
  # empty directory that the sync had just filled elsewhere. Set per invocation and
  # not exported, so stage 4 keeps its own separate panel cache.
  CAP_L2_CACHE="$DEC_CACHE" $RUNPY data/i4_l2_mid.py
fi

# --- stage 4: panel book ---------------------------------------------------
# run_panel_l2.sh carries its own per-day retries, its own 720-file gate per
# window, and its own per-window skip, and it deletes each window's raw cache once
# that window is parsed. It is called whole rather than reimplemented.
#
# It is named through CODE rather than by a bare name, because the cd at the top
# left this shell in the REPOSITORY ROOT and not in run/ where both scripts live,
# so a bare name resolves against the root and misses. That is exactly how the
# move into run/ broke this line, and it broke it silently: the branch is only
# entered when the panel is NOT built, so every machine that already holds the 24
# mid_series_{COIN}_{PERIOD}.npz walks past it and sees nothing. Measured in a
# copy of the tree with those outputs absent: bash run_panel_l2.sh printed
# "No such file or directory" and ended the run at exit 127.
if have_panel_book; then
  banner "STAGE 4/5  panel book - all 24 mid_series_{COIN}_{PERIOD}.npz present, skipped"
else
  banner "STAGE 4/5  panel book  (8 windows x BTC/ETH/SOL, about 7.6 GB, about 90 min)"
  bash "$CODE/run/run_panel_l2.sh"
  missing=""
  for p in $PANEL_PERIODS; do
    for c in $PANEL_COINS; do
      [ -f "$CODE/mid_series_${c}_${p}.npz" ] || missing="$missing ${c}_${p}"
    done
  done
  if [ -n "$missing" ]; then
    echo "Panel book windows still missing:$missing"
    echo "run_panel_l2.sh skips a window whose cache did not reach 720 files rather"
    echo "than building a short series. Re-run this script to retry those windows."
    exit 1
  fi
fi

# --- stage 5: book-mid join ------------------------------------------------
if have_book_mid; then
  banner "STAGE 5/5  book-mid join - quickwin_markouts_mid.npz present, skipped"
else
  banner "STAGE 5/5  i4_midmarkout.py  (quickwin_markouts_mid.npz, the headline measure)"
  $RUNPY data/i4_midmarkout.py
fi

# --- close with the inventory ---------------------------------------------
banner "INVENTORY"
if $RUNPY data/step1_inventory.py; then
  echo "run_step1_data BUILD complete: every cell matches the recorded values."
  exit 0
fi
echo "run_step1_data BUILD finished, but the inventory found a divergence. Read the"
echo "status column above before trusting any number built on the affected cells."
exit 1
