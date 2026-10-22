#!/usr/bin/env bash
#
# run_panel_l2.sh  -  Counterparty adverse selection on Hyperliquid
#
# Builds the L2 book-mid series for EVERY panel window and coin, so the panel can be
# re-run on the SAME measure the December headline uses.
#
# WHY THIS EXISTS. The headline adverse-selection results are measured against the
# BOOK MID (mid_series_{BTC,ETH}.npz, December 4-13). The multi-window panel, which
# is the answer to "is this just December?", was built from node_fills only and is
# therefore read on the TRADE-PRINT markout. Two different instruments: the panel
# does not currently corroborate the headline measure, only a relative of it. The
# book snapshots for every panel window exist in the same public archive and were
# simply never pulled. This script pulls them.
#
# WINDOWS (identical to PERIOD_DAYS in panel_persistence.py): eight 10-day windows,
# 2025-08 .. 2026-05, coins BTC / ETH / SOL = 240 coin-days.
#
# DISK DISCIPLINE. The full raw pull is ~7.6 GB compressed and the machine this was
# built on had under 10 GB free, so the loop is per-window: sync one window's three
# coins, build that window's mid series, delete that window's raw cache. Peak raw
# footprint stays near 1 GB.
#
# OUTPUT: mid_series_{COIN}_{PERIOD}.npz next to this script, one per coin-window
# (via CAP_MID_SUFFIX in i4_l2_mid.py, which leaves the December artifact untouched).
#
# COST: the book archive is requester-pays; ~7.6 GB of egress plus ~5,760 GET
# requests, i.e. under one dollar at current S3 pricing. Credentials come from the
# ambient AWS profile; nothing is read from or written to this repository.
#
# Run, from the repository root, which is the form README.md gives for every
# entry point:
#       bash run/run_panel_l2.sh                         (all eight windows)
#       PANEL_L2_PERIODS="202508 202512" bash ...        (a subset)

set -euo pipefail

# This runner moved into run/ on 2026-08-30, beside the nine entry points it
# belongs with. Every path below is relative to the REPOSITORY ROOT, so the
# cd climbs one level out of this directory. Without the climb the move is
# silent and total: dirname "$0" would land in run/, requirements.txt and
# every script path would miss, and the run would fail on its first line
# rather than say why.
cd "$(dirname "$0")/.."
CODE="$(pwd)"

# --- where the data directory is -------------------------------------------
# Resolution order, first hit wins, and nothing absolute is written down:
#   1. CAP_DATA_ROOT, which is the name identity/i3_book_comparator.py already reads
#      for exactly this idea: the root that HOLDS the book caches. It is only READ
#      here and never exported, because panel_io.py reads the same name for a
#      different directory, the one holding the .npz panels.
#   2. the 02_data directory beside the repository, which is where a full checkout of
#      the parent workspace keeps it. This is what this script used to demand.
#   3. a directory inside the repository itself, which is the branch a reader who
#      cloned this repository ON ITS OWN takes: 02_data is a sibling of the
#      repository and does not travel with the clone.
# The resolved directory is then created, because a cache directory that does not
# exist yet is the normal state of a first run and not an error.
#
# WHY THIS IS NINE LINES AND NOT ONE. It was one line, and the line was
# DATA_DIR="$(cd "$CODE/../02_data" && pwd)". Under set -e that cd ends the script on
# its fourth line, before the START banner, for anyone whose 02_data is not there.
# Measured on a fresh clone: cd: .../02_data: No such file or directory, exit 1.
# run_step1_data.sh and run_i4.sh carry the same block, which matters here because
# run_step1_data.sh calls this script as a whole rather than reimplementing it: both
# compute the directory from the same repository root, so both land on the same one.
#
# The panel cache is a SEPARATE directory from the December one on purpose, so an
# eight-window pull cannot disturb the December cache the headline is measured on.
# That is also why CAP_L2_CACHE is set per invocation below and never exported.
if [ -n "${CAP_DATA_ROOT:-}" ]; then
  DATA_DIR="$CAP_DATA_ROOT"
elif [ -d "$CODE/../02_data" ]; then
  DATA_DIR="$CODE/../02_data"
else
  DATA_DIR="$CODE/data_cache"
fi
mkdir -p "$DATA_DIR"
DATA_DIR="$(cd "$DATA_DIR" && pwd)"

CACHE_ROOT="$DATA_DIR/l2_cache_panel"
LOG="$CODE/panel_l2_run.log"
# The pinned environment rather than a bare package name. --with numpy resolves numpy
# fresh on the day of the run: measured on 2026-08-13 it installed 2.5.2 against the
# 2.4.6 requirements.txt pins, said nothing about the substitution, and did not install
# matplotlib at all. --with-requirements reads the pins, and it is the form README.md
# already gives for every other entry point.
RUNPY="uv run --no-project --with-requirements requirements.txt python3"
BUCKET="s3://hyperliquid-archive/market_data"
COINS="BTC ETH SOL"

ALL_PERIODS="202508 202509 202510 202511 202512 202601 202603 202605"
PERIODS="${PANEL_L2_PERIODS:-$ALL_PERIODS}"

days_for() {
  case "$1" in
    202508) echo 20250804 20250805 20250806 20250807 20250808 20250809 20250810 20250811 20250812 20250813 ;;
    202509) echo 20250904 20250905 20250906 20250907 20250908 20250909 20250910 20250911 20250912 20250913 ;;
    202510) echo 20251006 20251007 20251008 20251009 20251010 20251011 20251012 20251013 20251014 20251015 ;;
    202511) echo 20251104 20251105 20251106 20251107 20251108 20251109 20251110 20251111 20251112 20251113 ;;
    202512) echo 20251204 20251205 20251206 20251207 20251208 20251209 20251210 20251211 20251212 20251213 ;;
    202601) echo 20260104 20260105 20260106 20260107 20260108 20260109 20260110 20260111 20260112 20260113 ;;
    202603) echo 20260304 20260305 20260306 20260307 20260308 20260309 20260310 20260311 20260312 20260313 ;;
    202605) echo 20260504 20260505 20260506 20260507 20260508 20260509 20260510 20260511 20260512 20260513 ;;
    *) echo "" ;;
  esac
}

banner() {
  echo "" | tee -a "$LOG"
  echo "================================================================" | tee -a "$LOG"
  echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] $*" | tee -a "$LOG"
  echo "================================================================" | tee -a "$LOG"
}

: > "$LOG"
banner "run_panel_l2 START | periods: $PERIODS | coins: $COINS"

for p in $PERIODS; do
  DAYS="$(days_for "$p")"
  if [ -z "$DAYS" ]; then
    echo "[run_panel_l2] unknown period $p - skipped" | tee -a "$LOG"
    continue
  fi

  # Idempotence: a window whose three outputs already exist is skipped, so an
  # interrupted run resumes instead of re-paying for the same bytes.
  have=0
  for c in $COINS; do
    [ -f "$CODE/mid_series_${c}_${p}.npz" ] && have=$((have + 1))
  done
  if [ "$have" -eq 3 ]; then
    echo "[run_panel_l2] $p already built (3/3 outputs) - skipped" | tee -a "$LOG"
    continue
  fi

  # A transient network fault must not end the run or, worse, leave a window that
  # LOOKS built. Two guards. Each day's sync is retried until it reports success,
  # because `aws s3 sync` returns non-zero on a partial transfer and `set -e`
  # would otherwise abort the whole eight-window pull at the first dropped file
  # (observed: an intercepting proxy answered S3 with an unrelated certificate and
  # killed the run mid-November). Then the window's file count is asserted before
  # anything is built, because i4_l2_mid.py skips a missing hour with a warning and
  # would emit a short series indistinguishable from a complete one. The project
  # has already been bitten once by exactly that: a dropped connection silently
  # marked three December days absent.
  banner "$p  STEP 1/3  sync l2Book BTC,ETH,SOL -> $CACHE_ROOT"
  for d in $DAYS; do
    for attempt in 1 2 3 4; do
      echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] sync day $d (attempt $attempt)" | tee -a "$LOG"
      if aws s3 sync \
          "$BUCKET/$d/" \
          "$CACHE_ROOT/$d/" \
          --request-payer requester \
          --exclude '*' \
          --include '*/l2Book/BTC.lz4' \
          --include '*/l2Book/ETH.lz4' \
          --include '*/l2Book/SOL.lz4' \
          --only-show-errors 2>&1 | tee -a "$LOG"; then
        break
      fi
      echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] day $d attempt $attempt failed, retrying" | tee -a "$LOG"
      sleep 20
    done
  done

  # Completeness gate: 10 days x 24 hours x 3 coins = 720 files, no exceptions.
  n_files=$(find "$CACHE_ROOT" -name '*.lz4' 2>/dev/null | wc -l | tr -d ' ')
  want=$(( $(echo $DAYS | wc -w | tr -d ' ') * 24 * 3 ))
  echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] $p cache holds $n_files of $want expected files" | tee -a "$LOG"
  if [ "$n_files" -ne "$want" ]; then
    echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] $p INCOMPLETE ($n_files/$want) - NOT building, raw cache kept for a re-run" | tee -a "$LOG"
    continue
  fi

  banner "$p  STEP 2/3  i4_l2_mid.py -> mid_series_{BTC,ETH,SOL}_$p.npz"
  CAP_DAYS="$(echo $DAYS | tr ' ' ',')" \
  CAP_COINS="BTC,ETH,SOL" \
  CAP_MID_SUFFIX="_$p" \
  CAP_L2_CACHE="$CACHE_ROOT" \
    $RUNPY data/i4_l2_mid.py 2>&1 | tee -a "$LOG"

  banner "$p  STEP 3/3  drop this window's raw cache"
  for d in $DAYS; do
    rm -rf "${CACHE_ROOT:?}/$d"
  done
  df -h "$CODE" | tail -1 | tee -a "$LOG"
done

banner "run_panel_l2 DONE"
ls -la "$CODE"/mid_series_*_2*.npz 2>/dev/null | tee -a "$LOG" || true
