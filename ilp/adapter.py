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
                  alpha: int = 5, beta: int = 10, cache_mode: str = "repo"):
    """Build (Instance, graphs_filtered, node_attr_map) from the repo's graph generator.

    - arcs entering the source and leaving a destination are deleted (single-direction rule).
    - if some destination becomes unreachable in some slot, the graph seed is redrawn.
    - cache_mode="repo" (DEC-2, confirmed by the user): C = nodes whose `cache` attribute is True
      in the generated graph (all clouds + the satellites the repo flagged). Node attributes are
      NEVER rewritten, so the same C reaches every algorithm; `n_c` is ignored.
    - cache_mode="sample" (old behaviour, for regression only): n_clouds must be 0; n_c satellites
      drawn with random.Random(seed + 7919); the `cache` attribute of the copies is overwritten.
    - g[(c,t)] is read per node and per slot from that slot's node attributes.
    """
    np, Algorithm, TVM, repo_main, gen = _repo()
    assert cache_mode in ("repo", "sample"), cache_mode
    if cache_mode == "sample":
        assert config.get("n_clouds", 0) == 0, "cache_mode='sample' requires n_clouds=0"
    redraws = 0
    while True:
        gseed = seed + 100000 * redraws
        random.seed(gseed)
        np.random.seed(gseed)
        graphs = gen(seed=gseed, **{k: config[k] for k in TINY_CONFIG})
        s = [n for n, d in graphs[0].nodes(data=True) if d.get("type") == "src"][0]
        D = [n for n, d in graphs[0].nodes(data=True) if d.get("type") == "dest"]
        sats = [n for n, d in graphs[0].nodes(data=True) if d.get("type") == "satellite"]
        if cache_mode == "sample":
            C = sorted(random.Random(seed + 7919).sample(sats, n_c))
        else:
            C = sorted(n for n, d in graphs[0].nodes(data=True) if d.get("cache") is True)
        filtered = []
        for G in graphs:
            H = G.copy()
            H.remove_edges_from([(u, v) for u, v in G.edges if v == s or u in set(D)])
            if cache_mode == "sample":
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
                          "config": dict(config), "w_float": wfloat, "cache_mode": cache_mode,
                          "C_size": len(C),
                          "n_cloud_in_C": sum(graphs[0].nodes[c]["type"] == "cloud" for c in C),
                          "n_sat_in_C": sum(graphs[0].nodes[c]["type"] == "satellite" for c in C)})
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


def repair_connectivity(trees: dict, graphs_filtered, s: str) -> int:
    """Re-attach subtrees that TSMTA's path expansion left disconnected from s (adapter-side repair).

    TSMTA expands CTIG / virtual s->c edges into independently chosen shortest paths; when two of them
    disagree on orientation, the in-degree-1 and cycle guards drop the only link of a cache or a
    destination trunk and its whole subtree is orphaned. For each slot, every orphan root r (in-degree
    0, not s) is hooked to the connected part by the cheapest path in that slot's graph whose interior
    nodes are not yet in the tree (so in-degree stays 1 and no cycle can form). Selection of caches and
    destinations is untouched. Returns the number of arcs added.
    """
    import heapq
    import networkx as nx
    added = 0
    for (idx, t), G in trees.items():
        H = graphs_filtered[t]
        while True:
            reach = nx.descendants(G, s) | {s}
            lost = [n for n in G.nodes if n not in reach]
            if not lost:
                break
            roots = [n for n in lost if G.in_degree(n) == 0]
            # Pass 1: hook an orphan root (in-degree 0). Pass 2 (roots only reachable through their own
            # subtree, or a cycle component with no root): re-parent any unreachable node, which cuts
            # its old in-arc, so the part below it joins the connected side.
            for targets in (set(roots), set(lost)):
                dist = {n: 0.0 for n in reach}
                prev, pq = {}, [(0.0, str(n), n) for n in reach]
                heapq.heapify(pq)
                best = None                       # (cost, str(x), x, u)
                while pq:
                    d, _, u = heapq.heappop(pq)
                    if d > dist.get(u, float("inf")):
                        continue
                    for _, v, a in H.out_edges(u, data=True):
                        nd = d + float(a["cost_traffic"])
                        if v in targets:
                            if best is None or (nd, str(v)) < best[:2]:
                                best = (nd, str(v), v, u)
                        elif v not in G and nd < dist.get(v, float("inf")):
                            dist[v], prev[v] = nd, u      # relays must be new nodes: in-degree stays 1
                            heapq.heappush(pq, (nd, str(v), v))
                if best is not None:
                    break
            if best is None:
                break                             # genuinely unreachable in this slot's graph
            _, _, x, u = best
            for old in list(G.predecessors(x)):
                G.remove_edge(old, x)
            while True:
                if x not in G:
                    G.add_node(x, **dict(H.nodes[x]))
                if u not in G:
                    G.add_node(u, **dict(H.nodes[u]))
                G.add_edge(u, x, **dict(H[u][x]))
                added += 1
                if u in reach:
                    break
                x, u = u, prev[u]
    return added


def from_tsmta_output(inst: Instance, graphs_filtered, node_attr_map, k: int = 2,
                      mu_mode: str = "derived", collect_errors: bool = False,
                      repair: bool = False) -> dict:
    """Run the repo's TSMTA on the filtered graphs; return {"raw": Solution, "optimal": Solution}.

    Same call chain as main.py: Build_TIG_CTIG -> Run_TSMTA_Select -> copy_tree_sequence ->
    expand_virtual_edges -> [Optimal]. The produced solutions are NOT repaired: callers must run
    evaluate.check_solution on them. A TSMTA tree that still holds a virtual edge cannot be turned
    into a Solution: it raises AssertionError, or with collect_errors=True the name is left out of
    the result and out["errors"][name] = "VIRTUAL_EDGE_LEFT".
    """
    np, Algorithm, TVM, repo_main, gen = _repo()
    s, C, T = inst.s, list(inst.C), inst.T
    # Build_TIG_CTIG ignores its `caches` argument and reads the graph attribute; make sure that is C.
    assert {n for n, d in graphs_filtered[0].nodes(data=True) if d.get("cache") is True} == set(C)
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
    out, errors = {}, {}
    n_rep = {}
    if repair:
        n_rep["raw"] = repair_connectivity(raw, graphs_filtered, s)

    def attempt(name, trees):
        try:
            out[name] = finish(trees)
        except AssertionError as e:
            if not collect_errors:
                raise
            errors[name] = "VIRTUAL_EDGE_LEFT" if "virtual edge" in str(e) else "ASSERTION"

    attempt("raw", raw)
    opt = repo_main.copy_tree_sequence(base)
    TVM.expand_virtual_edges(T_i_t=opt, TIG_Interval=TIG, TIG_Edges_Map=TEM, srcs=[s], caches=C,
                             total_time=T)
    if repair:
        n_rep["optimal_pre"] = repair_connectivity(opt, graphs_filtered, s)
    TVM.Optimal(opt, [s], C, TIG, T, 100, node_attr_map=node_attr_map, beta=inst.beta,
                alpha=inst.alpha)
    if repair:
        n_rep["optimal"] = repair_connectivity(opt, graphs_filtered, s)
    attempt("optimal", opt)
    if collect_errors:
        out["errors"] = errors
    if repair:
        out["repairs"] = n_rep
    return out
