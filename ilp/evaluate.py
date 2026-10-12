"""Independent scorer for TAMCS solutions (PLAN.md section 2.3-2.5).

The single source of truth for cost. Imports neither ortools nor any repo algorithm.
"""
from __future__ import annotations

from dataclasses import replace

from .instance import Arc, Instance, Solution


class InfeasibleSolution(ValueError):
    def __init__(self, violations):
        super().__init__("; ".join(violations))
        self.violations = violations


# ---------------------------------------------------------------- tree helpers

def parent_map(arcs) -> dict[str, str]:
    """child -> parent. Only meaningful for in-degree<=1 arc sets."""
    return {v: u for u, v in arcs}


def tree_path(parent: dict[str, str], s: str, node: str) -> list[Arc]:
    """Arcs on the tree path s -> node (empty if node == s). Assumes a valid tree."""
    out: list[Arc] = []
    while node != s:
        p = parent[node]
        out.append((p, node))
        node = p
    out.reverse()
    return out


def _origin_path(par, s, o, d) -> list[Arc]:
    full = tree_path(par, s, d)
    return full if o == s else full[len(tree_path(par, s, o)):]


def build_solution(inst: Instance, tree_arcs, mu: dict, origin: dict) -> Solution:
    """Assemble a Solution, deriving path[(d,t)] = tree path origin -> d."""
    arcs = [set(a) for a in tree_arcs]
    full_mu = {(c, t): int(mu.get((c, t), 0)) for c in inst.C for t in range(inst.T)}
    path = {}
    for t in range(inst.T):
        par = parent_map(arcs[t])
        for d in inst.D:
            path[(d, t)] = _origin_path(par, inst.s, origin[(d, t)], d)
    return Solution(arcs=arcs, mu=full_mu, origin=dict(origin), path=path)


# ---------------------------------------------------------------- feasibility

def check_solution(inst: Instance, sol: Solution) -> list[str]:
    """Return a list of violations; each message starts with an upper-case code."""
    v: list[str] = []
    Cset = set(inst.C)
    if len(sol.arcs) != inst.T:
        return [f"BAD_SHAPE: expected {inst.T} slots, got {len(sol.arcs)}"]
    for (c, t), val in sol.mu.items():
        if c not in Cset or not (0 <= t < inst.T) or val not in (0, 1):
            v.append(f"MU_INVALID: mu[({c},{t})]={val}")
    for t in range(inst.T):
        arcs = set(sol.arcs[t])
        for a in sorted(arcs - set(inst.arcs[t])):
            v.append(f"ARC_NOT_IN_SLOT: slot {t} arc {a[0]}->{a[1]} not in instance")
        indeg: dict[str, int] = {}
        for a in arcs:
            indeg[a[1]] = indeg.get(a[1], 0) + 1
        if indeg.get(inst.s, 0):
            v.append(f"ROOT_INARC: slot {t} has an arc entering the source")
        for n, k in sorted(indeg.items()):
            if k > 1 and n != inst.s:
                v.append(f"INDEGREE: slot {t} node {n} has in-degree {k}")
        in_tree = {inst.s} | {n for a in arcs for n in a}
        adj: dict[str, list[str]] = {}
        for a in arcs:
            adj.setdefault(a[0], []).append(a[1])
        seen, stack = {inst.s}, [inst.s]
        while stack:
            u = stack.pop()
            for w in adj.get(u, ()):
                if w not in seen:
                    seen.add(w)
                    stack.append(w)
        stray = in_tree - seen
        if stray:
            # peel stray nodes that have no in-arc from other stray nodes;
            # whatever remains lies on, or downstream of, a cycle
            indg = {n: 0 for n in stray}
            for a in arcs:
                if a[0] in stray and a[1] in stray:
                    indg[a[1]] += 1
            q = [n for n, k in indg.items() if k == 0]
            while q:
                n = q.pop()
                indg.pop(n)
                for w in adj.get(n, ()):
                    if w in indg:
                        indg[w] -= 1
                        if indg[w] == 0:
                            q.append(w)
            if indg:
                v.append(f"CYCLE: slot {t} nodes {sorted(indg)} lie on or behind a cycle")
            rest = sorted(stray - set(indg))
            if rest:
                v.append(f"UNREACHABLE: slot {t} nodes {rest} not reachable from source")
        for d in inst.D:
            if d not in in_tree:
                v.append(f"DEST_MISSING: slot {t} destination {d} not in tree")
        for c in inst.C:
            if sol.mu.get((c, t), 0) == 1 and c not in in_tree:
                v.append(f"MU_NOT_IN_TREE: slot {t} cache {c} has mu=1 but is not in the tree")
        # origin / path checks need a structurally valid tree
        if stray or any(k > 1 for k in indeg.values()) or indeg.get(inst.s, 0):
            continue
        par = parent_map(arcs)
        for d in inst.D:
            if d not in in_tree:
                continue
            if (d, t) not in sol.origin:
                v.append(f"ORIGIN_MISSING: no origin for ({d},{t})")
                continue
            o = sol.origin[(d, t)]
            if o != inst.s and o not in Cset:
                v.append(f"ORIGIN_INVALID: origin of ({d},{t}) is {o}, neither source nor cache")
                continue
            if o != inst.s and sol.mu.get((o, t), 0) != 1:
                v.append(f"ORIGIN_MU0: origin {o} of ({d},{t}) has mu=0")
                continue
            full = tree_path(par, inst.s, d)
            if o != inst.s and o not in {a[0] for a in full}:
                v.append(f"ORIGIN_NOT_ANCESTOR: origin {o} is not an ancestor of {d} in slot {t}")
                continue
            if (d, t) in sol.path and list(sol.path[(d, t)]) != _origin_path(par, inst.s, o, d):
                v.append(f"PATH_MISMATCH: path of ({d},{t}) differs from tree path {o}->{d}")
    return v


# ---------------------------------------------------------------- cost

def _paths(inst: Instance, sol: Solution) -> dict:
    out = {}
    for t in range(inst.T):
        par = parent_map(sol.arcs[t])
        for d in inst.D:
            out[(d, t)] = _origin_path(par, inst.s, sol.origin[(d, t)], d)
    return out


def prune(inst: Instance, sol: Solution) -> Solution:
    """Drop tree arcs not on any origin->d path nor on the trunk s->c of a mu=1 cache."""
    paths = _paths(inst, sol)
    arcs = []
    for t in range(inst.T):
        par = parent_map(sol.arcs[t])
        keep: set[Arc] = set()
        for d in inst.D:
            keep.update(paths[(d, t)])
            o = sol.origin[(d, t)]
            if o != inst.s:
                keep.update(tree_path(par, inst.s, o))
        for c in inst.C:
            if sol.mu.get((c, t), 0) == 1:
                keep.update(tree_path(par, inst.s, c))
        arcs.append(keep)
    return Solution(arcs=arcs, mu=dict(sol.mu), origin=dict(sol.origin), path=paths)


def _cost(inst: Instance, sol: Solution, paths: dict) -> dict:
    bc = sum(inst.f[t] * inst.arcs[t][a] for t in range(inst.T) for a in sol.arcs[t])
    cc = sum(sol.mu.get((c, t), 0) * inst.g[(c, t)] for c in inst.C for t in range(inst.T))
    rc = sum(1 for d in inst.D for t in range(1, inst.T)
             if set(paths[(d, t - 1)]) != set(paths[(d, t)]))
    tc = bc + inst.alpha * cc + inst.beta * inst.scale * rc
    S = inst.scale
    return {"BC": bc / S, "CC": cc / S, "RC": rc, "TC": tc / S,
            "BC_int": bc, "CC_int": cc, "TC_int": tc}


def evaluate(inst: Instance, sol: Solution, check: bool = True) -> dict:
    """Return BC, CC, RC, TC, TC_int (+ BC_int, CC_int, pruned_TC, pruned_TC_int)."""
    if check:
        viol = check_solution(inst, sol)
        if viol:
            raise InfeasibleSolution(viol)
    paths = _paths(inst, sol)
    res = _cost(inst, sol, paths)
    pres = _cost(inst, prune(inst, sol), paths)
    res["pruned_TC"] = pres["TC"]
    res["pruned_TC_int"] = pres["TC_int"]
    return res


# ---------------------------------------------------------------- helper for tests

def relabel(inst: Instance, sol: Solution, m: dict[str, str]):
    """Rename nodes via m; returns (Instance, Solution)."""
    def r(n):
        return m.get(n, n)

    def ra(a):
        return (r(a[0]), r(a[1]))

    i2 = replace(inst, nodes=[r(n) for n in inst.nodes], s=r(inst.s),
                 D=[r(n) for n in inst.D], C=[r(n) for n in inst.C],
                 arcs=[{ra(a): w for a, w in x.items()} for x in inst.arcs],
                 g={(r(c), t): x for (c, t), x in inst.g.items()})
    s2 = Solution(arcs=[{ra(a) for a in x} for x in sol.arcs],
                  mu={(r(c), t): x for (c, t), x in sol.mu.items()},
                  origin={(r(d), t): r(o) for (d, t), o in sol.origin.items()},
                  path={(r(d), t): [ra(a) for a in p] for (d, t), p in sol.path.items()})
    return i2, s2


# ---------------------------------------------------------------- repo_compat (regression only)

def evaluate_repo_compat(trees: list[dict], caches, src: str, alpha, beta, hit_factor: float = 0.3):
    """Re-implement TVM.evaluate_algorithm("TSMTA") on a plain-data snapshot (PLAN 2.5).

    trees[t] = {"edges": [[u, v, stored_weight], ...], "dests": [...],
                "cache_selected": {node: g_value}}.
    Differences from evaluate(): BC multiplies arcs below any node in `caches` by hit_factor and
    reads stored weights; CC uses the cache_selected flags; origin = nearest ancestor in `caches`;
    RC is the per-transition average. Returns (BC, CC, RC, TC).
    """
    caches = set(caches)
    T = len(trees)
    bc = cc = 0.0
    eff = []
    for tr in trees:
        children, parent, w = {}, {}, {}
        for u, v, x in tr["edges"]:
            children.setdefault(u, []).append(v)
            parent[v] = u
            w[(u, v)] = x
        stack = [(src, False)]
        while stack:
            u, passed = stack.pop()
            for v in children.get(u, ()):
                bc += w[(u, v)] * (hit_factor if passed else 1.0)
                stack.append((v, passed or v in caches))
        cc += sum(tr["cache_selected"].values())
        per = {}
        for d in tr["dests"]:
            edges, v = [], d
            while v in parent:
                u = parent[v]
                edges.append((u, v))
                if u in caches:
                    break
                v = u
            per[d] = frozenset(edges)
        eff.append(per)
    changed = 0
    for t in range(T - 1):
        for d in set(eff[t]) | set(eff[t + 1]):
            if eff[t].get(d, frozenset()) != eff[t + 1].get(d, frozenset()):
                changed += 1
    rc = changed / max(T - 1, 1)
    return bc, cc, rc, bc + alpha * cc + beta * rc
