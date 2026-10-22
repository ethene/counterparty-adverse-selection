#!/usr/bin/env bash
# Research-completeness background run.
# Order: light/vectorized mid-only scripts first, then the heavy book-feature build+test.
# Long-running data pass; run directly. check_first.py already ran in the foreground
# (the repro gate). Sentinel: COMPLETENESS_DONE.
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
rm -f COMPLETENESS_DONE
{
  echo "=== $(date) START completeness run ==="
  echo "--- own_size_control.py (mid-only, vectorized) ---"
  $PY identity/own_size_control.py; echo "own_size exit=$?"
  echo "--- temp_perm_decomp.py (mid-only, vectorized) ---"
  $PY markout/temp_perm_decomp.py; echo "temp_perm exit=$?"
  echo "--- i3_book_comparator.py --stage all (HEAVY: l2_cache feats + fill re-parse + OOS) ---"
  $PY identity/i3_book_comparator.py --stage all; echo "i3_book exit=$?"
  echo "=== $(date) DONE ==="
  touch COMPLETENESS_DONE
} 2>&1 | tee completeness_run.log
