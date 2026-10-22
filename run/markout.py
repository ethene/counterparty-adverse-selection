#!/usr/bin/env python3
"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-07-31
References: none (repository infrastructure; it computes no quantity of its own).

THE ENTRY POINT OF THE MARKOUT GROUP: step 2 of the pipeline, the harm of one trade.

What this group answers: how large the harm to the maker who filled a trade is, and how
it is shaped -- over the horizon, over the trade size, over the taker's pre-trade
inventory and over the side. It is the measurement the whole argument stands on, and it
is deliberately narrower than the argument: nothing here says the wallet behind the
trade behaves the same way a month later, and nothing here says what the wallet's
identity adds. Those are the two groups after this one.

    uv run --no-project --with-requirements requirements.txt python3 run/markout.py             # the plan and its price
    uv run --no-project --with-requirements requirements.txt python3 run/markout.py --members   # what is in the group and why
    uv run --no-project --with-requirements requirements.txt python3 run/markout.py --run       # recompute the group
    uv run --no-project --with-requirements requirements.txt python3 run/markout.py --only m5_termstructure_results.json --run
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import _groups                                                          # noqa: E402

if __name__ == "__main__":
    sys.exit(_groups.main("markout"))
