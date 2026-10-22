#!/usr/bin/env python3
"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-07-31
References: none (repository infrastructure; it computes no quantity of its own).

THE ENTRY POINT OF THE GATES GROUP: step 7 of the pipeline, the other half of it.

What this group answers: whether the raw parse is right byte for byte, and whether the
repository still holds against its own rules. The two kinds are worth telling apart. The
first re-derives a field of the public archive without the project parser, so a mis-read
side or an upside-down book cannot survive. The second guards the tree against itself:
one home per setting, no absolute path, every results file still matching the code that
wrote it.

WHY THIS ONE FILE IS A VIEW AND NOT A RUNNER. The gates already had a runner before the
pipeline groups were written down: checks/run_all_checks.py registers every check under a
name and a group -- clean-clone local, ignored derived data, small live fetch, or a walk
of the raw archive -- and that grouping is by what each check NEEDS, which is a
distinction the dependency graph does not hold and should not. So --run here hands over
to that runner rather than
starting the checks a second way, and the list of checks stays in one place. What this
file adds is the question the runner cannot answer: which gates the build considers
stale, and what re-running them would cost. Those are printed by default, and they
compute nothing.

WHAT --census RETURNS, AND WHY IT IS NOT ALWAYS ZERO. Until 2026-08-29 the census
printed every finding it had and exited zero whatever it found, so a disagreement
between the group table and this runner's own registry of checks stood on the screen
for fourteen days under a closing line that reads like an all-clear. The rule now sorts
its findings in two. A REFUSAL is a self-contradiction -- the table and the runner
disagree about which gates exist, the table names a node the graph does not hold, two
groups claim one node, or the cross-check could not be made at all -- and it exits
non-zero, because one of two documents is then wrong and no count is worth reading
until it is known which. A DEBT is a coverage gap with a size: a producer node no group
claims is a real node and nothing about the table is wrong, so it is printed against a
declared ceiling that may only ever be lowered, and it exits zero while it holds. The
rule, both ceilings and the pair of opposite cases that calibrate them live beside the
census in run/_groups.py, and every one of the nine entry points gets them.

A gate is also the one thing in this tree that should not be skipped. Every other group's
output is a quantity, and a quantity whose producer and inputs have not moved is the same
quantity. A gate's output is a verdict about the tree as it stands now, and a verdict
carried forward because nothing hashable moved is a verdict about a tree nobody looked
at. Hence: the plan below says what is stale, and the runner runs them all anyway.

    uv run --no-project --with-requirements requirements.txt python3 run/gates.py                     # which gates are stale, and the cost
    uv run --no-project --with-requirements requirements.txt python3 run/gates.py --members           # what is in the group and why
    uv run --no-project --with-requirements requirements.txt python3 run/gates.py --census            # every group against the graph
    uv run --no-project --with-requirements requirements.txt python3 run/gates.py --run               # run the offline gates
    uv run --no-project --with-requirements requirements.txt python3 run/gates.py --run --argv --data
    uv run --no-project --with-requirements requirements.txt python3 run/gates.py --run --argv --network
    uv run --no-project --with-requirements requirements.txt python3 run/gates.py --run --argv --only settings_home
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import _groups                                                          # noqa: E402

if __name__ == "__main__":
    sys.exit(_groups.main("gates"))
