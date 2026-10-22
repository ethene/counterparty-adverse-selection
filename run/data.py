#!/usr/bin/env python3
"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-07-31
References: none (repository infrastructure; it computes no quantity of its own).

THE ENTRY POINT OF THE DATA GROUP: step 1 of the pipeline.

What this group answers: what was parsed out of the public archive, over which windows
and coins, and whether the parse still reproduces. Its members are the expensive passes
over the raw archive and the gates on them, and what they write -- the per-fill
intermediates -- is what every other group reads. Nothing here reports a quantity about
the market; everything here is an input to something that does.

This is the group that costs hours rather than seconds, so the price is printed before
anything starts and a run without --run computes nothing at all.

    uv run --no-project --with-requirements requirements.txt python3 run/data.py             # the plan and its price
    uv run --no-project --with-requirements requirements.txt python3 run/data.py --members   # what is in the group and why
    uv run --no-project --with-requirements requirements.txt python3 run/data.py --run       # recompute the group
    uv run --no-project --with-requirements requirements.txt python3 run/data.py --only i4_midmarkout_results.json --run
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import _groups                                                          # noqa: E402

if __name__ == "__main__":
    sys.exit(_groups.main("data"))
