#!/usr/bin/env python3
"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-07-31
References: none (repository infrastructure; it computes no quantity of its own).

THE ENTRY POINT OF THE MONEY GROUP: step 6 of the pipeline.

What this group answers: what the harm is worth in currency. How large the maker's gross
loss to adverse selection is over the window, how much of it sits in a small set of
wallets, what a policy that widens against those wallets recovers on the real fee
schedule, and what it gives up on the benign flow it turns away. Every number here is a
cost or a reduction in a cost, never an alpha, and the volume forgone is reported beside
every improvement.

This group holds the two longest analysis runs in the tree, so --members is worth
reading before --run.

    uv run --no-project --with-requirements requirements.txt python3 run/money.py             # the plan and its price
    uv run --no-project --with-requirements requirements.txt python3 run/money.py --members   # what is in the group and why
    uv run --no-project --with-requirements requirements.txt python3 run/money.py --run       # recompute the group
    uv run --no-project --with-requirements requirements.txt python3 run/money.py --only t3_results.json --run
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import _groups                                                          # noqa: E402

if __name__ == "__main__":
    sys.exit(_groups.main("money"))
