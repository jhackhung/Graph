"""Exact solver by enumeration, independent of ILP/CP-SAT (PLAN.md Phase 3). Tiny instances only.

Per slot we enumerate every candidate (tree, mu, origin assignment) and then combine slots with a DP
over the rerouting cost.

Why enumerating only pruned trees is enough: all weights are positive integers, so deleting a leaf
that is neither a destination nor a cache with mu=1 strictly lowers BC and changes neither any
origin->d path (so RC is unchanged) nor mu (so CC is unchanged). An optimal solution therefore never
has such a leaf. Caches with mu=1 are allowed as leaves because they are paid for through CC and
need their trunk.
"""
from __future__ import annotations

import itertools

from .evaluate import build_solution, parent_map, tree_path
from .instance import Instance, Solution


def _trees(inst: Instance, t: int):
    """Yield parent dicts (child -> parent) of trees rooted at s that contain all of D."""
    ins: dict[str, list[str]] = {}
    for (u, v) in inst.arcs[t]:
        ins.setdefault(v, []).append(u)
    nodes = [n for n in inst.nodes if n != inst.s]
    dset = set(inst.D)
    options = [([None] if n not in dset else []) + sorted(ins.get(n, [])) for n in nodes]
    for choice in itertools.product(*options):
        par = {n: p for n, p in zip(nodes, choice) if p is not None}
        ok = True
        for n in par:                       # every chosen node must reach s without cycling
            seen, x = set(), n
            while x != inst.s:
                if x in seen or x not in par:
                    ok = False
                    break
                seen.add(x)
                x = par[x]
            if not ok:
                break
        if ok:
            yield par


def slot_candidates(inst: Instance, t: int, use_cache: bool = True):
    """Return a list of dicts: arcs, mu, origin, cost (BC+alpha*CC, int), sig (path sets per d)."""
    out = []
    Cset = set(inst.C)
    for par in _trees(inst, t):
        arcs = frozenset((p, n) for n, p in par.items())
        bc = sum(inst.f[t] * inst.arcs[t][a] for a in arcs)
        in_tree_c = sorted(c for c in inst.C if c in par) if use_cache else []
        has_child = set(par.values())
        leaves = {n for n in par if n not in has_child}
        mandatory_leaf = leaves - set(inst.D)          # non-D leaves must be mu=1 caches
        if not mandatory_leaf <= Cset | set():
            continue
        for bits in itertools.product((0, 1), repeat=len(in_tree_c)):
            on = {c for c, b in zip(in_tree_c, bits) if b}
            if not mandatory_leaf <= on:
                continue
            cc = sum(inst.g[(c, t)] for c in on)
            anc = {}
            for d in inst.D:
                chain = [a[0] for a in tree_path(par, inst.s, d)]     # s, ..., parent(d)
                anc[d] = [inst.s] + [x for x in chain[1:] if x in on]
            for combo in itertools.product(*(anc[d] for d in inst.D)):
                origin = dict(zip(inst.D, combo))
                sig = []
                for d in inst.D:
                    full = tree_path(par, inst.s, d)
                    o = origin[d]
                    sig.append(frozenset(full if o == inst.s else full[len(tree_path(par, inst.s, o)):]))
                out.append({"arcs": arcs, "mu": on, "origin": origin, "sig": tuple(sig),
                            "cost": bc + inst.alpha * cc})
    return out


def _to_solution(inst, picks) -> Solution:
    mu = {(c, t): int(c in p["mu"]) for t, p in enumerate(picks) for c in inst.C}
    origin = {(d, t): p["origin"][d] for t, p in enumerate(picks) for d in inst.D}
    return build_solution(inst, [set(p["arcs"]) for p in picks], mu, origin)


def solve_brute(inst: Instance, use_cache: bool = True):
    """Exact optimum via per-slot enumeration + DP. Returns (TC_int, Solution)."""
    bs = inst.beta * inst.scale
    # collapse candidates with identical signature to the cheapest one
    layers = []
    for t in range(inst.T):
        best = {}
        for c in slot_candidates(inst, t, use_cache):
            if c["sig"] not in best or c["cost"] < best[c["sig"]]["cost"]:
                best[c["sig"]] = c
        layers.append(best)
    dp = [{sig: (c["cost"], None) for sig, c in layers[0].items()}]
    for t in range(1, inst.T):
        cur = {}
        for sig, c in layers[t].items():
            bestv, arg = None, None
            for psig, (pv, _) in dp[t - 1].items():
                rc = sum(1 for a, b in zip(psig, sig) if a != b)
                v = pv + bs * rc
                if bestv is None or v < bestv:
                    bestv, arg = v, psig
            cur[sig] = (bestv + c["cost"], arg)
        dp.append(cur)
    sig = min(dp[-1], key=lambda k: dp[-1][k][0])
    total = dp[-1][sig][0]
    picks = []
    for t in range(inst.T - 1, -1, -1):
        picks.append(layers[t][sig])
        sig = dp[t][sig][1]
    picks.reverse()
    return total, _to_solution(inst, picks)


def solve_exhaustive(inst: Instance, use_cache: bool = True):
    """Cartesian product of all slot candidates, each scored whole by evaluate(). No DP.
    Only for T <= 2 and very small instances. Returns the optimal TC_int."""
    from .evaluate import evaluate
    cands = [slot_candidates(inst, t, use_cache) for t in range(inst.T)]
    best = None
    for picks in itertools.product(*cands):
        tc = evaluate(inst, _to_solution(inst, picks), check=False)["TC_int"]
        if best is None or tc < best:
            best = tc
    return best
