"""
Counterparty adverse selection on Hyperliquid | Author: Dmitry Stakhin | Date: 2026-06-21
References: Abowd-Kramarz-Margolis (1999) Econometrica; Kline-Saggio-Solvsten (2020)
           Econometrica 88(5):1859-1898 (DOI 10.3982/ECTA16410); internal
           data_acquisition_log.md verified field semantics.

PROBE B1 — connected-set / mobility diagnostics on the bipartite taker x maker
fill graph. This is the GATE for the KSS two-way fixed-effects decomposition (Probe C):
it decides whether the two-way FE markout = taker_FE + maker_FE is identified off
genuine mobility, or whether the graph is hub-dominated (one maker, e.g. HLP, fills
~everyone) so the decomposition leans on a hub and we must fall back to one-way FE
+ a Korajczyk-Sadka factor / grouped FE.

A fill = an edge (taker-node, maker-node). Roles are SEPARATE node namespaces
(a wallet's taker-FE and maker-FE are distinct), so taker_id and maker_id are
re-factorized independently within each cell. FE are identified on the largest
connected component (LCC); a taker's relative FE is identified only if it faces
>= 2 distinct makers (mobility). The decisive check is mobility NET OF the single
dominant hub maker: if most takers reach >= 2 distinct makers only by counting the
hub, identification is fragile.

Estimation cells: per coin (pooling months) is the primary unit; per coin-period
and global are also reported. Read-only: writes JSON + prints a summary.
"""
import os
import sys

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

# artifact.py lives one directory up, so the path is built from this file's own location
# and never from the working directory the run happens to start in.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import artifact  # noqa: E402
import panel_io as P  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CODE_DIR = os.path.dirname(HERE)
# Located by panel_io rather than joined here, so the one place that knows where the
# markout panels live is the one place that has to change if they move.
PANEL = os.path.join(P.data_root(), "panel_markouts.npz")
OUT_JSON = os.path.join(HERE, "connected_set_b1_results.json")
COIN = {0: "BTC", 1: "ETH", 2: "SOL"}


def gini(x):
    x = np.asarray(x, dtype=np.float64)
    if x.size == 0 or x.sum() == 0:
        return None
    xs = np.sort(x)
    n = xs.size
    cum = np.cumsum(xs)
    # G = (2*sum(i*x_i))/(n*sum x) - (n+1)/n , i = 1..n
    idx = np.arange(1, n + 1)
    g = (2.0 * np.sum(idx * xs)) / (n * cum[-1]) - (n + 1.0) / n
    return round(float(g), 4)


def distinct_per(left, right, n_left):
    """For each left node, count of distinct right nodes (over unique left-right pairs)."""
    key = left.astype(np.int64) * (right.max() + 1) + right.astype(np.int64)
    upairs = np.unique(key)
    pl = (upairs // (right.max() + 1)).astype(np.int64)
    cnt = np.bincount(pl, minlength=n_left)
    return cnt  # index = left node id


def diagnose(taker_id, maker_id):
    n = taker_id.size
    # re-factorize roles independently within this cell
    ut, ti = np.unique(taker_id, return_inverse=True)
    um, mi = np.unique(maker_id, return_inverse=True)
    nT, nM = ut.size, um.size

    # --- connected components on the bipartite graph (takers 0..nT-1, makers nT..) ---
    rows = ti
    cols = mi + nT
    N = nT + nM
    data = np.ones(n, dtype=np.int8)
    A = coo_matrix((data, (rows, cols)), shape=(N, N))
    ncomp, labels = connected_components(A, directed=False, connection="weak")
    # largest component
    comp_sizes = np.bincount(labels, minlength=ncomp)
    lcc = int(comp_sizes.argmax())
    in_lcc_node = labels == lcc
    takers_in_lcc = int(in_lcc_node[:nT].sum())
    makers_in_lcc = int(in_lcc_node[nT:].sum())
    # share of fills with BOTH endpoints in LCC (bipartite => taker in LCC <=> maker in LCC, but check)
    fill_in_lcc = in_lcc_node[ti] & in_lcc_node[mi + nT]
    lcc_fill_share = float(fill_in_lcc.mean())

    # --- mobility ---
    dmk = distinct_per(ti, mi, nT)          # distinct makers per taker
    dtk = distinct_per(mi, ti, nM)          # distinct takers per maker
    movers = int((dmk >= 2).sum())
    mover_share = movers / nT

    # --- hub dominance ---
    maker_deg = np.bincount(mi, minlength=nM)   # fills per maker
    taker_deg = np.bincount(ti, minlength=nT)
    order = np.argsort(maker_deg)[::-1]
    top1 = int(order[0])
    top1_fill_share = float(maker_deg[top1] / n)
    top5_fill_share = float(maker_deg[order[:5]].sum() / n)
    maker_gini = gini(maker_deg)
    taker_gini = gini(taker_deg)

    # --- mobility NET OF the dominant hub maker (the decisive KSS check) ---
    keep = mi != top1
    if keep.sum() > 0:
        ti2, mi2 = ti[keep], mi[keep]
        # re-count distinct makers per taker excluding the hub
        dmk_nohub = distinct_per(ti2, mi2, nT)
    else:
        dmk_nohub = np.zeros(nT, dtype=np.int64)
    movers_nohub = int((dmk_nohub >= 2).sum())
    mover_share_nohub = movers_nohub / nT
    # takers that ONLY connect via the hub (>=1 maker, but <2 once hub removed)
    only_via_hub = int(((dmk >= 1) & (dmk_nohub < 2) & (dmk >= 2)).sum())

    return {
        "n_fills": int(n),
        "n_takers": nT,
        "n_makers": nM,
        "n_edges_distinct": int(np.unique(ti.astype(np.int64) * (nM) + mi).size),
        "lcc": {
            "n_components": int(ncomp),
            "lcc_fill_share": round(lcc_fill_share, 4),
            "takers_in_lcc": takers_in_lcc,
            "makers_in_lcc": makers_in_lcc,
            "takers_in_lcc_share": round(takers_in_lcc / nT, 4),
        },
        "mobility": {
            "median_makers_per_taker": int(np.median(dmk)),
            "p90_makers_per_taker": int(np.percentile(dmk, 90)),
            "mover_share_ge2_makers": round(mover_share, 4),
            "median_takers_per_maker": int(np.median(dtk)),
        },
        "hub": {
            "top1_maker_fill_share": round(top1_fill_share, 4),
            "top5_maker_fill_share": round(top5_fill_share, 4),
            "maker_degree_gini": maker_gini,
            "taker_degree_gini": taker_gini,
        },
        "mobility_net_of_hub": {
            "mover_share_ge2_makers_excl_top1": round(mover_share_nohub, 4),
            "takers_only_connected_via_hub": only_via_hub,
            "fragility_drop": round(mover_share - mover_share_nohub, 4),
        },
    }


def verdict(d):
    """GO two-way KSS vs fallback."""
    lcc_ok = d["lcc"]["lcc_fill_share"] >= 0.90
    mob_ok = d["mobility_net_of_hub"]["mover_share_ge2_makers_excl_top1"] >= 0.20
    hub_bad = d["hub"]["top1_maker_fill_share"] >= 0.50
    if lcc_ok and mob_ok and not hub_bad:
        return "GO two-way KSS (mobility survives hub removal)"
    if lcc_ok and mob_ok and hub_bad:
        return "GO with CAUTION (mobility survives but a dominant hub exists; report hub-excl robustness)"
    return "FALLBACK to one-way FE + Korajczyk-Sadka factor / grouped FE (mobility too hub-dependent)"


def main():
    t0 = artifact.start_clock()
    # panel_io names the producer to run when the file is absent, so that message
    # is written once for the whole tree; the load itself stays here because
    # build.py derives this script's input edge from the argument of np.load.
    P.require_present("panel", PANEL)
    d = np.load(PANEL, allow_pickle=True)
    coin = d["coin"]
    period = d["period"]
    taker = d["taker_id"]
    maker = d["maker_id"]
    n = coin.size
    print(f"Probe B1 connected-set | panel {n:,} rows")

    out = {"panel_rows": int(n), "cells": {}}

    # global
    print("\n=== GLOBAL (all coins/periods pooled) ===")
    g = diagnose(taker, maker)
    g["verdict"] = verdict(g)
    out["cells"]["GLOBAL"] = g
    _print_cell("GLOBAL", g)

    # per coin (pool months) — the primary estimation unit
    for c in sorted(np.unique(coin).tolist()):
        cname = COIN.get(c, str(c))
        m = coin == c
        cell = diagnose(taker[m], maker[m])
        cell["verdict"] = verdict(cell)
        out["cells"][cname] = cell
        _print_cell(cname, cell)

    # per coin-period (summary line each)
    out["cells_coin_period"] = {}
    for c in sorted(np.unique(coin).tolist()):
        for p in sorted(np.unique(period).tolist()):
            m = (coin == c) & (period == p)
            if m.sum() < 1000:
                continue
            key = f"{COIN.get(c, c)}_{int(p)}"
            cell = diagnose(taker[m], maker[m])
            cell["verdict"] = verdict(cell)
            out["cells_coin_period"][key] = cell
            mh = cell["mobility_net_of_hub"]["mover_share_ge2_makers_excl_top1"]
            print(
                f"  {key}: LCC={cell['lcc']['lcc_fill_share']} "
                f"mover_excl_hub={mh} top1_hub={cell['hub']['top1_maker_fill_share']} "
                f"-> {cell['verdict'].split(' (')[0]}"
            )

    # What these numbers cover, stated rather than inferred. This probe reads the fill
    # GRAPH only -- taker, maker, coin and period -- and no markout column at all, so no
    # scoring horizon enters it and its verdict is unchanged by the horizon the rest of
    # the work scores at. Said in the scope rather than added as a payload key, so the
    # file's own keys are exactly what they were before this pass.
    periods = sorted(int(p) for p in np.unique(period))
    artifact.write(
        os.path.basename(OUT_JSON), out,
        script=__file__, inputs=[PANEL],
        scope={
            "population": (f"{n:,} panel fills as edges of the taker x maker graph; "
                           f"{np.unique(taker).size:,} distinct takers and "
                           f"{np.unique(maker).size:,} distinct makers, with roles "
                           "re-factorised inside every cell and no fill floor"),
            "window": (f"{len(periods)} monthly windows pooled, {periods[0]} to "
                       f"{periods[-1]}; the calendar dates of each are declared by the "
                       "panel's producer, panel_build.py"),
            "coins": [COIN.get(c, str(c)) for c in sorted(np.unique(coin).tolist())],
            "markout_horizon": ("none: no markout column is read, so this probe has no "
                                "scoring horizon. The horizon_s field of the "
                                "fingerprint block below carries the declared default "
                                "and is not a property of this run"),
        },
        started=t0, out_dir=os.path.dirname(OUT_JSON))
    print(f"\nwrote probes/{os.path.basename(OUT_JSON)}")


def _print_cell(name, c):
    print(
        f"\n[{name}] fills={c['n_fills']:,} takers={c['n_takers']:,} makers={c['n_makers']:,}\n"
        f"  LCC fill-share={c['lcc']['lcc_fill_share']}  takers_in_lcc={c['lcc']['takers_in_lcc_share']}\n"
        f"  mover_share(>=2 makers)={c['mobility']['mover_share_ge2_makers']}  "
        f"net-of-hub={c['mobility_net_of_hub']['mover_share_ge2_makers_excl_top1']}  "
        f"(fragility drop={c['mobility_net_of_hub']['fragility_drop']})\n"
        f"  hub: top1={c['hub']['top1_maker_fill_share']} top5={c['hub']['top5_maker_fill_share']} "
        f"maker_gini={c['hub']['maker_degree_gini']}\n"
        f"  VERDICT: {c['verdict']}"
    )


if __name__ == "__main__":
    main()
