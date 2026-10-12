"""Shared assertions for ILP-vs-bruteforce tests."""
from dataclasses import replace

from ilp.brute_force import solve_brute
from ilp.evaluate import check_solution, evaluate
from ilp.model_cpsat import solve


def slot_instance(inst, t):
    """Single-slot sub-instance of slot t."""
    return replace(inst, T=1, arcs=[inst.arcs[t]], f=[inst.f[t]],
                   g={(c, 0): v for (c, tt), v in inst.g.items() if tt == t})


def check_ilp(inst, use_cache, brute=True):
    """Solve, verify status/validate/feasibility/objective consistency, compare with brute force."""
    res = solve(inst, use_cache=use_cache)
    assert res["status"] == "OPTIMAL"
    assert res["validate"] == ""
    assert check_solution(inst, res["solution"]) == []
    ev = evaluate(inst, res["solution"])
    assert ev["TC_int"] == res["objective"], (ev, res["objective"])
    if brute:
        assert res["objective"] == solve_brute(inst, use_cache)[0]
    return res, ev
