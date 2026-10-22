#!/bin/bash
# Phase-1 re-verification: the three checks that require an S3 node_fills re-walk
# (node_fills_by_block is NOT cached locally; only the L2 book is).
# Long-running data pass; run directly. Fastest-first so partial results land early.
# This script lives in checks/ but the paths below are relative to the repository root, so cd there.
set -u
cd "$(dirname "$0")/.." || exit 1
# The pinned environment rather than a bare package name, written once instead of at
# each of the three launches below. --with numpy resolves numpy fresh on the day of the
# run: measured on 2026-08-13 it installed 2.5.2 against the 2.4.6 requirements.txt
# pins, said nothing about the substitution, and did not install matplotlib at all.
# --with-requirements reads the pins, and it is the form README.md already gives for
# every other entry point. The path is relative because the cd above has already moved
# to the directory holding requirements.txt.
PY="uv run --no-project --with-requirements requirements.txt python3"
LOG=checks/verify_s3_run.log
rm -f checks/VERIFY_S3_DONE
echo "START $(date)" > "$LOG"

echo "=== DS7 field-hygiene FULL (3h raw re-walk: silent-drop / sz<=0 / maker-None) ===" >> "$LOG"
$PY checks/chk_field_hygiene.py >> "$LOG" 2>&1
echo "DS7 exit=$? $(date)" >> "$LOG"

echo "=== DS5 determinism FULL (1-day re-parse vs stored slice) ===" >> "$LOG"
$PY checks/chk_rowcounts_determinism.py >> "$LOG" 2>&1
echo "DS5 exit=$? $(date)" >> "$LOG"

echo "=== DS1 side-sign FULL (2-day BTC+ETH gold-standard timestamp leg) ===" >> "$LOG"
$PY checks/chk_side_signconv.py >> "$LOG" 2>&1
echo "DS1 exit=$? $(date)" >> "$LOG"

echo "DONE $(date)" >> "$LOG"
touch checks/VERIFY_S3_DONE
