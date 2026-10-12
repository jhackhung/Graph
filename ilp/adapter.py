"""Adapter between the existing simulator / TSMTA code and ilp.Instance / ilp.Solution (PLAN Phase 7).

Run from the repo root so the flat repo modules import; repo files are never modified.
Repo modules are imported lazily so that ilp.instance / ilp.evaluate need none of its dependencies.
"""
from __future__ import annotations

import os
import random
import sys

from .instance import Instance, Solution, validate_instance, reachable

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TINY_CONFIG = dict(n_sats=8, n_clouds=0, n_srcs=1, n_dests=3, total_time=3, num_planes=4,
                   altitude_km=550, inclination_deg=53, f_phasing_param=1,
                   base_angular_velocity=0.2, thr_cloud_to_cloud=3200, region_dist_thr=1000)

MAX_REDRAW = 50


def _repo():
    """Import repo modules lazily (repo root must be importable)."""
    if _ROOT not in sys.path:
        sys.path.insert(0, _ROOT)
    import numpy as np
    import Algorithm
    import TVM
    import main as repo_main
    from Random_Orbit import generate_graph_sequence_realistic
    return np, Algorithm, TVM, repo_main, generate_graph_sequence_realistic


def from_existing(config: dict, seed: int, n_c: int = 2, scale: int = 10 ** 5,
                  alpha: int = 5, beta: int = 10):
    """Build (Instance, graphs_filtered, node_attr_map) from the repo's graph generator.

    - n_clouds must be 0 (C contains satellites only, DEC-2).
    - arcs entering the source and leaving a destination are deleted (single-direction rule).
    - if some destination becomes unreachable in some slot, the graph seed is redrawn.
    - C: n_c satellites drawn with random.Random(seed + 7919).
    Returns graphs whose node attribute `cache` is True exactly on C.
    """
    np, Algorithm, TVM, repo_main, gen = _repo()
    assert config.get("n_clouds", 0) == 0, "use n_clouds=0 (C = satellites only)"
    redraws = 0
    while True:
        gseed = seed + 100000 * redraws
        random.seed(gseed)
        np.random.seed(gseed)
        graphs = gen(seed=gseed, **{k: config[k] for k in TINY_CONFIG})
        s = [n for n, d in graphs[0].nodes(data=True) if d.get("type") == "src"][0]
        D = [n for n, d in graphs[0].nodes(data=True) if d.get("type") == "dest"]
        sats = [n for n, d in graphs[0].nodes(data=True) if d.get("type") == "satellite"]
        C = sorted(random.Random(seed + 7919).sample(sats, n_c))
        filtered = []
        for G in graphs:
            H = G.copy()
            H.remove_edges_from([(u, v) for u, v in G.edges if v == s or u in set(D)])
            for n in H.nodes:
                H.nodes[n]["cache"] = n in C
            filtered.append(H)
        ok = all(all(d in reachable(H.edges, s) for d in D) for H in filtered)
        if ok:
            break
        redraws += 1
        if redraws > MAX_REDRAW:
            raise RuntimeError("no seed with all destinations reachable after arc deletion")
    arcs, wfloat = [], []
    for H in filtered:
        a, wf = {}, {}
        for u, v, attr in H.edges(data=True):
            w = float(attr["cost_traffic"])
            wi = round(w * scale)
            if wi < 1:
                raise ValueError(f"weight {w} of {u}->{v} quantizes to {wi}")
            a[(u, v)] = wi
            wf[f"{u}->{v}"] = w
        arcs.append(a)
        wfloat.append(wf)
    size = float(filtered[0].nodes[s].get("data_size", 1.0))
    assert size == 1.0, "f=1 assumes data_size == 1.0"
    g = {(c, t): round(Algorithm.cost_cache(filtered[t].nodes[c], size, 1.0) * scale)
         for c in C for t in range(len(filtered))}
    inst = Instance(T=len(filtered), nodes=list(filtered[0].nodes), s=s, D=D, C=C, arcs=arcs,
                    f=[1] * len(filtered), g=g, alpha=alpha, beta=beta, scale=scale,
                    meta={"seed": seed, "graph_seed": gseed, "redraws": redraws,
                          "config": dict(config), "w_float": wfloat})
    validate_instance(inst)
    node_attr_map = {n: dict(d) for n, d in filtered[0].nodes(data=True)}
    return inst, filtered, node_attr_map


def _parent_chain(par: dict, s: str, node: str):
    """Ancestor list of node (excluding node), nearest first, up to s; guards against cycles."""
    chain, seen = [], {node}
    x = node
    while x in par:
        x = par[x]
        if x in seen:
            break
        seen.add(x)
        chain.append(x)
        if x == s:
            break
    return chain


def _tree_to_solution(inst: Instance, trees, flags, mu_mode: str) -> Solution:
    """trees[t] = nx.DiGraph; flags[t] = set of cache_selected nodes. Never repairs the tree."""
    Cset = set(inst.C)
    arcs = [set(G.edges()) for G in trees]
    mu = {(c, t): 0 for c in inst.C for t in range(inst.T)}
    origin, path = {}, {}
    for t in range(inst.T):
        par = {v: u for u, v in arcs[t]}
        if mu_mode == "flag":
            for c in flags[t] & Cset:
                mu[(c, t)] = 1
        for d in inst.D:
            chain = _parent_chain(par, inst.s, d)
            if mu_mode == "derived":
                o = next((x for x in chain if x in Cset), inst.s)       # nearest cache ancestor
                if o in Cset:
                    mu[(o, t)] = 1
            else:
                o = next((x for x in chain if x in Cset and mu[(x, t)] == 1), inst.s)
            origin[(d, t)] = o
            p, x = [], d
            while x != o and x in par and len(p) <= len(inst.nodes):
                p.append((par[x], x))
                x = par[x]
            p.reverse()
            path[(d, t)] = p
    return Solution(arcs=arcs, mu=mu, origin=origin, path=path)


def from_tsmta_output(inst: Instance, graphs_filtered, node_attr_map, k: int = 2,
                      mu_mode: str = "derived") -> dict:
    """Run the repo's TSMTA on the filtered graphs; return {"raw": Solution, "optimal": Solution}.

    Same call chain as main.py: Build_TIG_CTIG -> Run_TSMTA_Select -> copy_tree_sequence ->
    expand_virtual_edges -> [Optimal]. The produced solutions are NOT repaired: callers must run
    evaluate.check_solution on them.
    """
    np, Algorithm, TVM, repo_main, gen = _repo()
    s, C, T = inst.s, list(inst.C), inst.T
    TIG, CTIG, TEM, CEM = repo_main.Build_TIG_CTIG(graphs_filtered, [s], C, alpha=inst.alpha)
    base, _ = repo_main.Run_TSMTA_Select(TIG, CTIG, TEM, CEM, [s], C, set(inst.D), node_attr_map,
                                        T, pdta_level=k, beta=inst.beta)

    def finish(trees):
        for G in trees.values():
            assert not any(a.get("virtual") for _, _, a in G.edges(data=True)), "virtual edge left"
        seq = [trees[(0, t)] for t in range(T)]
        flags = [{n for n, d in G.nodes(data=True) if d.get("cache_selected", False)} for G in seq]
        return _tree_to_solution(inst, seq, flags, mu_mode)

    raw = repo_main.copy_tree_sequence(base)
    TVM.expand_virtual_edges(T_i_t=raw, TIG_Interval=TIG, TIG_Edges_Map=TEM, srcs=[s], caches=C,
                             total_time=T)
    out = {"raw": finish(raw)}
    opt = repo_main.copy_tree_sequence(base)
    TVM.expand_virtual_edges(T_i_t=opt, TIG_Interval=TIG, TIG_Edges_Map=TEM, srcs=[s], caches=C,
                             total_time=T)
    TVM.Optimal(opt, [s], C, TIG, T, 100, node_attr_map=node_attr_map, beta=inst.beta,
                alpha=inst.alpha)
    out["optimal"] = finish(opt)
    return out
