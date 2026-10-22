#!/usr/bin/env python3
"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-07-31
References: none (repository infrastructure; it computes no quantity of its own).

THE ENTRY POINT OF THE NOTEBOOK GROUP: step 8, the build and the repository.

What this group answers: what the reproducibility notebook downloads and what it asserts
against. A reader with no archive access and no repository beside them opens one file,
runs it, and is told per number whether the recomputation came out the same. That is the
path a reproducible study owes its reader, and these two scripts are what puts the numbers in
front of it: one builds the published per-fill file, the other extracts the assert
targets out of the committed results files, so the notebook compares against generated
values rather than hand-typed ones.

This group runs LAST and not first, which is why it is not in the data group. Its
expectations are copied out of the committed results of nearly every other group, so
asking for it plans most of the tree. That is the honest price and it is printed before
anything starts.

    uv run --no-project --with-requirements requirements.txt python3 run/notebook.py             # the plan and its price
    uv run --no-project --with-requirements requirements.txt python3 run/notebook.py --members   # what is in the group and why
    uv run --no-project --with-requirements requirements.txt python3 run/notebook.py --run       # recompute the group
    uv run --no-project --with-requirements requirements.txt python3 run/notebook.py --only notebook_expected.json --run
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import _groups                                                          # noqa: E402

if __name__ == "__main__":
    sys.exit(_groups.main("notebook"))
