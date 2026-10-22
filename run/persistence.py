#!/usr/bin/env python3
"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-07-31
References: none (repository infrastructure; it computes no quantity of its own).

THE ENTRY POINT OF THE PERSISTENCE GROUP: step 3 of the pipeline.

What this group answers: whether the harm is a stable trait of the wallet rather than a
property of one window. A wallet is scored in one window and the score is read again in
a disjoint one -- the second half of the same month, a month two seasons later, a
different coin -- and what survives is what a maker could act on. The group also holds
the decomposition that asks how much of the cross-sectional variance is a per-wallet
component at all, because a score that persists perfectly and explains nothing is worth
as little as one that explains everything and does not persist.

    uv run --no-project --with-requirements requirements.txt python3 run/persistence.py             # the plan and its price
    uv run --no-project --with-requirements requirements.txt python3 run/persistence.py --members   # what is in the group and why
    uv run --no-project --with-requirements requirements.txt python3 run/persistence.py --run       # recompute the group
    uv run --no-project --with-requirements requirements.txt python3 run/persistence.py --only i2_walletfe_results.json --run
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import _groups                                                          # noqa: E402

if __name__ == "__main__":
    sys.exit(_groups.main("persistence"))
