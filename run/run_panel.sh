#!/usr/bin/env bash
# Multi-month panel run (BTC/ETH/SOL x Aug/Oct/Dec 2025, trade-print markout).
# Builder = panel_persistence.py --build (downloads each calendar day ONCE for all coins,
# ~14.5 GB egress, stream-and-discard keeps peak disk ~0.5 GB).
# Long-running data pass; run directly. Sentinel: PANEL_DONE.
set -uo pipefail
# This runner moved into run/ on 2026-08-30, beside the nine entry points it
# belongs with. Every path below is relative to the REPOSITORY ROOT, so the
# cd climbs one level out of this directory. Without the climb the move is
# silent and total: dirname "$0" would land in run/, requirements.txt and
# every script path would miss, and the run would fail on its first line
# rather than say why.
cd "$(dirname "$0")/.."
# The pinned environment rather than a bare package name. --with numpy resolves numpy
# fresh on the day of the run: measured on 2026-08-13 it installed 2.5.2 against the
# 2.4.6 requirements.txt pins, said nothing about the substitution, and did not install
# matplotlib at all. --with-requirements reads the pins, and it is the form README.md
# already gives for every other entry point. The path is relative because this script
# has already cd'd to the directory holding it.
PY="uv run --no-project --with-requirements requirements.txt python3"
rm -f PANEL_DONE
{
  echo "=== $(date) PANEL START ==="
  echo "--- step 1: build panel_markouts.npz (single all-coins pull, ~30-50 min) ---"
  $PY data/panel_persistence.py --build; echo "build exit=$?"
  echo "--- step 2: cross-month persistence ---"
  $PY data/panel_persistence.py --analyze; echo "persistence exit=$?"
  echo "--- step 3: common-vs-idiosyncratic decomposition ---"
  $PY persistence/panel_common_idio.py; echo "common_idio exit=$?"
  echo "--- step 4: per-regime re-run (i3 non-recoverability + t3 economic) ---"
  $PY persistence/panel_analyze.py; echo "analyze exit=$?"
  echo "=== $(date) PANEL DONE ==="
  touch PANEL_DONE
} 2>&1 | tee panel_run.log
