#!/usr/bin/env python3
"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-07-31
References: none (repository infrastructure; it computes no quantity of its own).

THE ENTRY POINT OF THE QUOTERS GROUP: step 5 of the pipeline.

What this group answers: what the standard quoting models do on this fill set, and what
the counterparty-resolved term changes about the quote they set. The Avellaneda-Stoikov
closed form is the inventory-only, counterparty-blind baseline the whole extension is
measured against, and the Glosten-Milgrom quoter is in the comparison precisely because
its signal is market-level flow with no counterparty in it at all. What a member of this
group produces is a spread and an inventory rule. What a maker ends up with in currency
is the next group.

    uv run --no-project --with-requirements requirements.txt python3 run/quoters.py             # the plan and its price
    uv run --no-project --with-requirements requirements.txt python3 run/quoters.py --members   # what is in the group and why
    uv run --no-project --with-requirements requirements.txt python3 run/quoters.py --run       # recompute the group
    uv run --no-project --with-requirements requirements.txt python3 run/quoters.py --only mm_bakeoff_results.json --run
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import _groups                                                          # noqa: E402

if __name__ == "__main__":
    sys.exit(_groups.main("quoters"))
