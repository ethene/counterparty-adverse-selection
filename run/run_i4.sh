#!/usr/bin/env bash
#
# run_i4.sh  -  Counterparty adverse selection on Hyperliquid | I4 mid-markout runner
#
# Orchestrates the I4 mid-price maker-adverse-selection markout pipeline end to end:
#   cache sync (L2 book) -> mid series -> mid markouts -> OOS non-recoverability
#   -> 10-day persistence -> depth control. Idempotent and re-runnable: cache sync
#   is incremental (aws s3 sync), each python step rewrites its own *_results.json,
#   and a terminal I4_DONE sentinel is touched on success.
#
# Window: days 20251204..20251213, coins BTC,ETH, horizons {1,10,60}s.
# All output is tee'd to i4_run.log. Long-running data pass; run directly.

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
#      for exactly this idea: the root that HOLDS l2_cache. It is deliberately only
#      READ here and never exported, because panel_io.py reads the same name for a
#      different directory, the one holding the .npz panels, and exporting it would
#      point every panel reader in this run at the raw cache.
#   2. the 02_data directory beside the repository, which is where a full checkout of
#      the parent workspace keeps it. This is what this script used to demand.
#   3. a directory inside the repository itself, which is the branch a reader who
#      cloned this repository ON ITS OWN takes: 02_data is a sibling of the
#      repository and does not travel with the clone.
# The resolved directory is then created, because a cache directory that does not
# exist yet is the normal state of a first run and not an error.
#
# WHY THIS IS NINE LINES AND NOT ONE. It was one line, and the line was
# DATA_DIR="$(cd "$CODE/../02_data" && pwd)". Under set -e that cd ends the script
# on its fourth line, before a single character is printed, for anyone whose 02_data
# is not there -- which is everyone who cloned this repository by itself. Measured on
# a fresh clone: cd: .../02_data: No such file or directory, exit 1, nothing else.
# checks/chk_input_freshness.py states the same fact about a lone clone and builds
# its own fixture around it. run_step1_data.sh and run_panel_l2.sh carry the same
# block, and all three resolve to the same directory because all three compute it
# from the same repository root.
if [ -n "${CAP_DATA_ROOT:-}" ]; then
  DATA_DIR="$CAP_DATA_ROOT"
elif [ -d "$CODE/../02_data" ]; then
  DATA_DIR="$CODE/../02_data"
else
  DATA_DIR="$CODE/data_cache"
fi
mkdir -p "$DATA_DIR"
DATA_DIR="$(cd "$DATA_DIR" && pwd)"

# The pinned environment rather than a bare package name. --with numpy resolves numpy
# fresh on the day of the run: measured on 2026-08-13 it installed 2.5.2 against the
# 2.4.6 requirements.txt pins, said nothing about the substitution, and did not install
# matplotlib at all. --with-requirements reads the pins, and it is the form README.md
# already gives for every other entry point.
RUNPY='uv run --no-project --with-requirements requirements.txt python3'
LOG="$CODE/i4_run.log"
CACHE_ROOT="$DATA_DIR/l2_cache"
DAYS="20251204 20251205 20251206 20251207 20251208 20251209 20251210 20251211 20251212 20251213"

# Start a fresh log for this run.
: > "$LOG"

banner() {
  # Timestamped step banner -> stdout + log.
  echo "" | tee -a "$LOG"
  echo "================================================================" | tee -a "$LOG"
  echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] $*" | tee -a "$LOG"
  echo "================================================================" | tee -a "$LOG"
}

# ---------------------------------------------------------------------------
# (1) Cache sync: pull only the L2 book BTC/ETH lz4 files for the window.
# ---------------------------------------------------------------------------
banner "STEP 1/7  cache sync (s3 l2Book BTC,ETH -> $CACHE_ROOT)"
for d in $DAYS; do
  echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] sync day $d" | tee -a "$LOG"
  aws s3 sync \
    "s3://hyperliquid-archive/market_data/$d/" \
    "$CACHE_ROOT/$d/" \
    --request-payer requester \
    --exclude '*' \
    --include '*/l2Book/BTC.lz4' \
    --include '*/l2Book/ETH.lz4' \
    --only-show-errors 2>&1 | tee -a "$LOG"
done

# ---------------------------------------------------------------------------
# (2) Build mid series artifact (mid_series_{COIN}.npz).
# ---------------------------------------------------------------------------
banner "STEP 2/7  i4_l2_mid.py  (mid_series_{BTC,ETH}.npz)"
# The cache the sync above just filled is named to the reader instead of being left to
# coincide with its default. i4_l2_mid.py falls back to ../02_data/l2_cache when
# CAP_L2_CACHE is unset, which is the same directory as CACHE_ROOT only while 02_data
# is where the resolution above landed; on a lone clone it is not, and the step would
# then read an empty directory that the step before had just filled elsewhere.
CAP_L2_CACHE="$CACHE_ROOT" $RUNPY data/i4_l2_mid.py 2>&1 | tee -a "$LOG"

# ---------------------------------------------------------------------------
# (3) Build mid markouts (quickwin_markouts_mid.npz, row-aligned to quickwin).
# ---------------------------------------------------------------------------
banner "STEP 3/7  i4_midmarkout.py  (quickwin_markouts_mid.npz)"
$RUNPY data/i4_midmarkout.py 2>&1 | tee -a "$LOG"

# ---------------------------------------------------------------------------
# (4) OOS non-recoverability on the mid markouts.
# ---------------------------------------------------------------------------
banner "STEP 4/7  i3_nonrecoverability_oos.py --source mid"
$RUNPY identity/i3_nonrecoverability_oos.py --source mid 2>&1 | tee -a "$LOG"

# ---------------------------------------------------------------------------
# (5) 10-day persistence on the mid markouts.
# ---------------------------------------------------------------------------
banner "STEP 5/7  ks2_persistence_10day.py --source mid"
$RUNPY persistence/ks2_persistence_10day.py --source mid 2>&1 | tee -a "$LOG"

# ---------------------------------------------------------------------------
# (6) Depth control.
# ---------------------------------------------------------------------------
banner "STEP 6/7  i3_depth_control.py"
$RUNPY identity/i3_depth_control.py 2>&1 | tee -a "$LOG"

# ---------------------------------------------------------------------------
# (7) Done sentinel.
# ---------------------------------------------------------------------------
banner "STEP 7/7  touch I4_DONE"
touch "$CODE/I4_DONE"
echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] I4 pipeline complete." | tee -a "$LOG"
