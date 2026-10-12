"""CP-SAT model of TAMCS (PLAN.md section 6).

Variables (all Bool unless noted): x[t,a] tree arc, mu[c,t] cache, h[t,d,o] origin choice,
y[t,d,a] arc on path(origin->d), z[t,c,a] arc on trunk s->c, r[t,d] rerouting indicator,
plus integer depth[t,v] (only when enforce_tree) which forbids cycles inside x.

Why depth: in-degree <= 1 alone still allows a cycle of x-arcs detached from the source. y could then
carry a circulation on that cycle, letting the model "pad" y so two different paths look equal and
dodge the rerouting cost. depth[v] >= depth[u]+1 on every chosen arc removes every x-cycle, so y is a
simple path and r is exact.
"""
from __future__ import annotations

import time

from ortools.sat.python import cp_model

from .evaluate import build_solution, parent_map, tree_path
from .instance import Instance, Solution


def _check_int_coeffs(inst: Instance) -> None:
    for t in range(inst.T):
        assert isinstance(inst.f[t], int)
        for w in inst.arcs[t].values():
            assert isinstance(w, int) and not isinstance(w, bool)
    for gv in inst.g.values():
        assert isinstance(gv, int)
    assert isinstance(inst.alpha, int) and isinstance(inst.beta, int) and isinstance(inst.scale, int)


def build_model(inst: Instance, use_cache: bool = True, enforce_tree: bool = True):
    """Return (model, vars). vars keys: x, mu, h, y, z, r, depth."""
    _check_int_coeffs(inst)
    m = cp_model.CpModel()
    T, s = inst.T, inst.s
    C = list(inst.C) if use_cache else []
    O = [s] + C
    A = [sorted(inst.arcs[t]) for t in range(T)]
    outa = [{} for _ in range(T)]
    ina = [{} for _ in range(T)]
    for t in range(T):
        for a in A[t]:
            outa[t].setdefault(a[0], []).append(a)
            ina[t].setdefault(a[1], []).append(a)

    x = {(t, a): m.NewBoolVar(f"x_{t}_{a[0]}_{a[1]}") for t in range(T) for a in A[t]}
    mu = {(c, t): m.NewBoolVar(f"mu_{c}_{t}") for c in C for t in range(T)}
    h = {(t, d, o): m.NewBoolVar(f"h_{t}_{d}_{o}") for t in range(T) for d in inst.D for o in O}
    y = {(t, d, a): m.NewBoolVar(f"y_{t}_{d}_{a[0]}_{a[1]}")
         for t in range(T) for d in inst.D for a in A[t]}
    z = {(t, c, a): m.NewBoolVar(f"z_{t}_{c}_{a[0]}_{a[1]}")
         for t in range(T) for c in C for a in A[t]}

    for t in range(T):
        for d in inst.D:
            m.AddExactlyOne(h[(t, d, o)] for o in O)                           # C1
            for c in C:
                m.AddImplication(h[(t, d, c)], mu[(c, t)])                     # C2
            for v in inst.nodes:                                               # C3
                lhs = sum(y[(t, d, a)] for a in outa[t].get(v, [])) - \
                    sum(y[(t, d, a)] for a in ina[t].get(v, []))
                rhs = (h[(t, d, v)] if v in O else 0) - (1 if v == d else 0)
                m.Add(lhs == rhs)
            for a in A[t]:                                                     # C5
                m.AddImplication(y[(t, d, a)], x[(t, a)])
        for c in C:
            for v in inst.nodes:                                               # C4
                lhs = sum(z[(t, c, a)] for a in outa[t].get(v, [])) - \
                    sum(z[(t, c, a)] for a in ina[t].get(v, []))
                rhs = (mu[(c, t)] if v == s else 0) - (mu[(c, t)] if v == c else 0)
                m.Add(lhs == rhs)
            for a in A[t]:                                                     # C5
                m.AddImplication(z[(t, c, a)], x[(t, a)])

    depth = {}
    if enforce_tree:
        N = len(inst.nodes)
        for t in range(T):
            for v in inst.nodes:                                               # C6
                if v != s and ina[t].get(v):
                    m.Add(sum(x[(t, a)] for a in ina[t][v]) <= 1)
            for v in inst.nodes:
                depth[(t, v)] = m.NewIntVar(0, N, f"depth_{t}_{v}")
            for a in A[t]:
                m.Add(depth[(t, a[1])] >= depth[(t, a[0])] + 1).OnlyEnforceIf(x[(t, a)])

    r = {}
    if inst.beta > 0:
        for t in range(1, T):
            for d in inst.D:
                r[(t, d)] = m.NewBoolVar(f"r_{t}_{d}")
                for a in set(A[t]) | set(A[t - 1]):                            # C7
                    yt = y[(t, d, a)] if a in inst.arcs[t] else 0
                    yp = y[(t - 1, d, a)] if a in inst.arcs[t - 1] else 0
                    m.Add(r[(t, d)] >= yt - yp)
                    m.Add(r[(t, d)] >= yp - yt)

    obj = sum(inst.f[t] * inst.arcs[t][a] * x[(t, a)] for t in range(T) for a in A[t])
    if C:
        obj += inst.alpha * sum(inst.g[(c, t)] * mu[(c, t)] for c in C for t in range(T))
    if r:
        obj += inst.beta * inst.scale * sum(r.values())
    m.Minimize(obj)
    return m, {"x": x, "mu": mu, "h": h, "y": y, "z": z, "r": r, "depth": depth}


def extract_solution(inst: Instance, solver: cp_model.CpSolver, vs: dict) -> Solution:
    """Read only x, mu, h; paths are re-derived from the tree (y, z, r are not trusted)."""
    trees = [set() for _ in range(inst.T)]
    for (t, a), var in vs["x"].items():
        if solver.Value(var):
            trees[t].add(a)
    mu = {(c, t): solver.Value(v) for (c, t), v in vs["mu"].items()}
    origin = {}
    for t in range(inst.T):
        for d in inst.D:
            origin[(d, t)] = inst.s
            for (tt, dd, o), var in vs["h"].items():
                if tt == t and dd == d and solver.Value(var):
                    origin[(d, t)] = o
    return build_solution(inst, trees, mu, origin)


def count_model(model: cp_model.CpModel) -> tuple[int, int]:
    p = model.Proto()
    return len(p.variables), len(p.constraints)


class _FirstSolution(cp_model.CpSolverSolutionCallback):
    """Records the objective of the first solution found (to check that a hint is accepted)."""

    def __init__(self):
        super().__init__()
        self.first = None
        self.first_time = None
        self.n = 0
        self._t0 = time.time()

    def on_solution_callback(self):
        self.n += 1
        if self.first is None:
            self.first = int(round(self.ObjectiveValue()))
            self.first_time = time.time() - self._t0


def solve(inst: Instance, use_cache: bool = True, enforce_tree: bool = True,
          time_limit: float = 600.0, workers: int = 1, seed: int = 0, hint: Solution | None = None,
          log: bool = False, extract: bool = True) -> dict:
    """Solve and return a dict: status, objective, bound, solution, runtime, n_vars, n_cons."""
    model, vs = build_model(inst, use_cache, enforce_tree)
    if hint is not None:
        add_hint(model, vs, inst, hint)
    solver = cp_model.CpSolver()
    solver.parameters.num_workers = workers
    solver.parameters.random_seed = seed
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.log_search_progress = log
    cb = _FirstSolution()
    t0 = time.time()
    status = solver.Solve(model, cb)
    name = solver.StatusName(status)
    if name not in ("OPTIMAL", "FEASIBLE"):
        raise RuntimeError(f"CP-SAT returned {name}")
    n_vars, n_cons = count_model(model)
    sol = extract_solution(inst, solver, vs) if (extract and enforce_tree) else None
    return {"status": name, "objective": int(round(solver.ObjectiveValue())),
            "bound": solver.BestObjectiveBound(), "solution": sol,
            "runtime": time.time() - t0, "n_vars": n_vars, "n_cons": n_cons,
            "validate": model.Validate(), "first_objective": cb.first,
            "first_time": cb.first_time, "n_solutions": cb.n}


def add_hint(model, vs, inst: Instance, sol: Solution) -> None:
    """Complete hint for every variable (x, mu, h, y, z, r, depth) from a feasible Solution.

    y comes from the origin->d path, z from the tree path s->c of each cache with mu=1, r from
    comparing consecutive paths, depth from the tree. Partial hints may be ignored by CP-SAT.
    """
    S = inst.s
    for t in range(inst.T):
        par = parent_map(sol.arcs[t])
        in_tree = {S} | {n for a in sol.arcs[t] for n in a}
        for (tt, a), var in vs["x"].items():
            if tt == t:
                model.AddHint(var, int(a in sol.arcs[t]))
        trunk = {c: set(tree_path(par, S, c)) for c in inst.C
                 if sol.mu.get((c, t), 0) == 1 and c in in_tree}
        for (tt, c, a), var in vs["z"].items():
            if tt == t:
                model.AddHint(var, int(a in trunk.get(c, ())))
        for (tt, d, a), var in vs["y"].items():
            if tt == t:
                model.AddHint(var, int(a in sol.path[(d, t)]))
        for (tt, d, o), var in vs["h"].items():
            if tt == t:
                model.AddHint(var, int(sol.origin[(d, t)] == o))
        for (c, tt), var in vs["mu"].items():
            if tt == t:
                model.AddHint(var, int(sol.mu.get((c, t), 0)))
        for (tt, v), var in vs["depth"].items():
            if tt == t:
                k, x = 0, v
                while x in par and k <= len(inst.nodes):
                    x = par[x]
                    k += 1
                model.AddHint(var, k if v in in_tree else 0)
    for (t, d), var in vs["r"].items():
        model.AddHint(var, int(set(sol.path[(d, t - 1)]) != set(sol.path[(d, t)])))
