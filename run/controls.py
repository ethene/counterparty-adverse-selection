#!/usr/bin/env python3
"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-07-31
References: none (repository infrastructure; it computes no quantity of its own).

THE ENTRY POINT OF THE CONTROLS GROUP: step 7 of the pipeline, the probes.

What this group answers: whether each result is explained by something other than what
it is claimed to be explained by. What makes a member of this group a control rather
than one more measurement is that the right answer is named before the run: a class of
trades that should carry no information has to score near zero, a quoter that cannot see
identity has to be unmoved by permuting the labels, a signal planted in the data has to
come back out at the size it was planted. None of these produces a headline number, and
that is why they are the part of the work that persuades.

The other half of step 7 is the gates, which ask a different question -- whether the raw
data was read correctly rather than whether the conclusion survives -- and they have
their own entry point in run/gates.py.

    uv run --no-project --with-requirements requirements.txt python3 run/controls.py             # the plan and its price
    uv run --no-project --with-requirements requirements.txt python3 run/controls.py --members   # what is in the group and why
    uv run --no-project --with-requirements requirements.txt python3 run/controls.py --run       # recompute the group
    uv run --no-project --with-requirements requirements.txt python3 run/controls.py --only decay_curve_results.json --run
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import _groups                                                          # noqa: E402

if __name__ == "__main__":
    sys.exit(_groups.main("controls"))
