"""Phase 3: brute-force exact solver. Random seeds 0..29 (nodes<=7, |D|<=3, |C|<=2, T<=2)."""
from dataclasses import replace

import pytest

from ilp.brute_force import solve_brute, solve_exhaustive
from ilp.evaluate import check_solution, evaluate
from ilp.gen_random import gen_instance
from ilp.make_toys import toy1, toy2

# PLAN appendix A.3: (alpha, beta) -> optimum with cache
A3 = {(2, 0): 15, (2, 1): 17, (2, 2): 19, (2, 10): 19, (2, 100): 19, (100, 10): 22, (100, 100): 22}


@pytest.mark.parametrize("ab", sorted(A3))
def test_toy1_table(ab):
    inst = replace(toy1(), alpha=ab[0], beta=ab[1])
    tc, sol = solve_brute(inst)
    assert tc == A3[ab]
    assert check_solution(inst, sol) == []
    assert evaluate(inst, sol)["TC_int"] == tc


@pytest.mark.parametrize("beta", range(0, 7))
def test_toy1_no_cache(beta):
    inst = replace(toy1(), beta=beta)
    tc, _ = solve_brute(inst, use_cache=False)
    assert tc == min(22, 15 + 2 * beta)


def test_toy2():
    tc, _ = solve_brute(toy2())
    assert tc == 6


@pytest.mark.parametrize("seed", range(30))
@pytest.mark.parametrize("use_cache", [True, False])
def test_dp_matches_exhaustive(seed, use_cache):
    inst = gen_instance(seed, T=2)
    tc, sol = solve_brute(inst, use_cache)
    assert check_solution(inst, sol) == []
    assert evaluate(inst, sol)["TC_int"] == tc
    assert solve_exhaustive(inst, use_cache) == tc
