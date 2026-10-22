#!/usr/bin/env python3
"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-07-31
References: none (repository infrastructure; it computes no quantity of its own).

THE ENTRY POINT OF THE IDENTITY GROUP: step 4 of the pipeline, with step 4A beside it.

What this group answers: whether a maker who sees only public information could have
recovered what the counterparty's identity gives. The public information set is widened
in stages -- the anonymous trade tape first, then the whole order book -- and the
question each time is what adding the wallet's own history changes out of sample. The
group also holds the controls that would explain the identity term away if they could:
the book state the wallet trades into, its trade size and style, the direction of the
position it is building.

This is the group where a negative result is load-bearing. The claim is that identity
adds something the public book does not carry, and that claim is only worth as much as
the tests that could have refuted it and did not.

    uv run --no-project --with-requirements requirements.txt python3 run/identity.py             # the plan and its price
    uv run --no-project --with-requirements requirements.txt python3 run/identity.py --members   # what is in the group and why
    uv run --no-project --with-requirements requirements.txt python3 run/identity.py --run       # recompute the group
    uv run --no-project --with-requirements requirements.txt python3 run/identity.py --only i3_results.json --run
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import _groups                                                          # noqa: E402

if __name__ == "__main__":
    sys.exit(_groups.main("identity"))
