"""Phase 0: CP-SAT smoke tests (seeds 0..29 for shortest path, 0..19 for knapsack)."""
import itertools
import random

import networkx as nx
import pytest
from ortools.sat.python import cp_model


def _solve(model, workers=1):
    solver = cp_model.CpSolver()
    solver.parameters.num_workers = workers
    solver.parameters.random_seed = 0
    status = solver.Solve(model)
    return solver, status


def test_tiny_cover():
    m = cp_model.CpModel()
    x, y = m.NewBoolVar("x"), m.NewBoolVar("y")
    m.Add(x + y >= 1)
    m.Minimize(3 * x + 2 * y)
    solver, status = _solve(m)
    assert solver.StatusName(status) == "OPTIMAL"
    assert solver.ObjectiveValue() == 2
    assert (solver.Value(x), solver.Value(y)) == (0, 1)


@pytest.mark.parametrize("seed", range(30))
def test_shortest_path_flow_vs_networkx(seed):
    rng = random.Random(seed)
    n = rng.randint(5, 9)
    g = nx.DiGraph()
    g.add_nodes_from(range(n))
    for u in range(n):
        for v in range(n):
            if u != v and rng.random() < 0.4:
                g.add_edge(u, v, w=rng.randint(1, 9))
    # guarantee reachability 0 -> n-1
    for i in range(n - 1):
        if not g.has_edge(i, i + 1):
            g.add_edge(i, i + 1, w=rng.randint(1, 9))
    src, dst = 0, n - 1
    m = cp_model.CpModel()
    x = {(u, v): m.NewBoolVar(f"x{u}_{v}") for u, v in g.edges}
    for v in g.nodes:
        out = sum(x[(v, w)] for w in g.successors(v))
        inn = sum(x[(u, v)] for u in g.predecessors(v))
        m.Add(out - inn == (1 if v == src else -1 if v == dst else 0))
    m.Minimize(sum(g.edges[e]["w"] * x[e] for e in g.edges))
    solver, status = _solve(m)
    assert solver.StatusName(status) == "OPTIMAL"
    assert solver.ObjectiveValue() == nx.shortest_path_length(g, src, dst, weight="w")


@pytest.mark.parametrize("seed", range(20))
def test_knapsack_vs_bruteforce(seed):
    rng = random.Random(seed)
    n = rng.randint(4, 10)
    vals = [rng.randint(1, 20) for _ in range(n)]
    wts = [rng.randint(1, 10) for _ in range(n)]
    cap = sum(wts) // 2
    m = cp_model.CpModel()
    x = [m.NewBoolVar(f"x{i}") for i in range(n)]
    m.Add(sum(w * xi for w, xi in zip(wts, x)) <= cap)
    m.Maximize(sum(v * xi for v, xi in zip(vals, x)))
    solver, status = _solve(m)
    best = max(
        sum(v for v, b in zip(vals, bits) if b)
        for bits in itertools.product((0, 1), repeat=n)
        if sum(w for w, b in zip(wts, bits) if b) <= cap
    )
    assert solver.StatusName(status) == "OPTIMAL"
    assert solver.ObjectiveValue() == best


def test_solver_api_surface():
    m = cp_model.CpModel()
    x, y = m.NewBoolVar("x"), m.NewBoolVar("y")
    m.Add(x + y >= 1)
    m.Minimize(3 * x + 2 * y)
    m.AddHint(x, 0)
    m.AddHint(y, 1)
    assert m.Validate() == ""
    solver, status = _solve(m)
    assert solver.StatusName(status) == "OPTIMAL"
    assert solver.ObjectiveValue() == 2
    assert solver.BestObjectiveBound() == 2
