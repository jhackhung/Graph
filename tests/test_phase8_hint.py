"""Phase 8 (unit part): a complete hint is accepted - the first solution is no worse than the hint."""
import pytest

from ilp.baseline import sp_solution
from ilp.brute_force import solve_brute
from ilp.evaluate import evaluate
from ilp.model_cpsat import solve
from tests.test_phase6_ilp_cache import rand_inst


@pytest.mark.parametrize("seed", range(3500, 3540))
def test_hint_first_solution_not_worse(seed):
    inst = rand_inst(seed)
    for sol in (sp_solution(inst), solve_brute(inst)[1]):
        tc = evaluate(inst, sol)["TC_int"]
        res = solve(inst, hint=sol, workers=1)
        assert res["first_objective"] is not None and res["first_objective"] <= tc
        assert res["objective"] <= tc
