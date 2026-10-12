"""Trivial feasible solutions (shortest-path trees, no cache) for tests and sanity checks."""
import heapq

from .evaluate import build_solution
from .instance import Instance


def sp_tree(arcs: dict, s: str, targets) -> set:
    """Union of Dijkstra shortest paths s -> targets (a tree because parents are unique)."""
    adj = {}
    for (u, v), w in arcs.items():
        adj.setdefault(u, []).append((v, w))
    dist, par, heap = {s: 0}, {}, [(0, s)]
    while heap:
        dd, u = heapq.heappop(heap)
        if dd > dist[u]:
            continue
        for v, w in sorted(adj.get(u, ())):
            if v not in dist or dd + w < dist[v]:
                dist[v], par[v] = dd + w, u
                heapq.heappush(heap, (dd + w, v))
    out = set()
    for d in targets:
        while d != s:
            out.add((par[d], d))
            d = par[d]
    return out


def sp_solution(inst: Instance):
    trees = [sp_tree(inst.arcs[t], inst.s, inst.D) for t in range(inst.T)]
    origin = {(d, t): inst.s for d in inst.D for t in range(inst.T)}
    return build_solution(inst, trees, {}, origin)
