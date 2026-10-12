"""Phase 9: paper Fig. 1 (fixture reconstructed from the screenshots by the user, ilp/tests/fixtures/fig1.json).

The fixture does not pin g (g_unknown); we run with the ASSUMPTIONS g=0 and g=1 per (c,t), alpha=beta=1.
Checks 1-3 (BC, RC) do not depend on g.
"""
import json
import os
from dataclasses import replace

import pytest

from ilp.evaluate import build_solution, check_solution, evaluate
from ilp.instance import load_instance, validate_instance
from ilp.model_cpsat import solve

FIX = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ilp", "tests",
                   "fixtures", "fig1.json")


def load(g):
    inst = load_instance(FIX)
    inst = replace(inst, g={(c, t): g for c in inst.C for t in range(inst.T)})
    validate_instance(inst)
    return inst


def strategy(inst, name):
    st = json.load(open(FIX, encoding="utf-8"))["strategies"][name]
    trees = [{tuple(a.split("->")) for a in tr} for tr in st["trees"]]
    mu = {}
    if st["mu_c3"]:
        mu = {("c3", t): v for t, v in enumerate(st["mu_c3"])}
    origin = {(d, t): st["origin"] for d in inst.D for t in range(inst.T)}
    return build_solution(inst, trees, mu, origin), st["expected"]


def slot_bc(inst, sol):
    return [sum(inst.f[t] * inst.arcs[t][a] for a in sol.arcs[t]) for t in range(inst.T)]


NAMES = ["d_min_bandwidth", "e_no_reroute", "f_tsmta_cache_c3"]


@pytest.mark.parametrize("name", NAMES)
def test_strategies_feasible_and_match_paper(name):
    inst = load(1)
    sol, exp = strategy(inst, name)
    assert check_solution(inst, sol) == []
    assert slot_bc(inst, sol) == exp["BC_per_slot"]
    assert evaluate(inst, sol)["RC"] == exp["RC"]
    assert evaluate(inst, sol)["BC"] == sum(exp["BC_per_slot"])


@pytest.mark.parametrize("g", [0, 1])
def test_strategy_f_cc_is_3g(g):
    inst = load(g)
    sol, _ = strategy(inst, "f_tsmta_cache_c3")
    assert evaluate(inst, sol)["CC"] == 3 * g


@pytest.mark.parametrize("g", [0, 1])
def test_ilp_not_worse_than_paper_strategies(g):
    inst = load(g)
    res = solve(inst, workers=1)
    assert res["status"] == "OPTIMAL" and check_solution(inst, res["solution"]) == []
    assert evaluate(inst, res["solution"])["TC_int"] == res["objective"]
    for name in NAMES:
        sol, _ = strategy(inst, name)
        assert res["objective"] <= evaluate(inst, sol)["TC_int"], name
    print(f"g={g}: ILP optimum={res['objective']}",
          {n: evaluate(inst, strategy(inst, n)[0])["TC_int"] for n in NAMES})
