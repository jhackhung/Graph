"""Phase 12 step 2: ILP indexes g[(c,t)] correctly. gen_random already draws every (c,t) independently
from {0,1,2,3}; here 100 fresh seeds (5000-5099) with |C| in {1,2}, T in {2,3} are checked against brute force."""
import random

import pytest

from ilp.gen_random import gen_instance
from ilp.model_cpsat import solve
from ilp_helpers import check_ilp

SEEDS = list(range(5000, 5100))


def _inst(seed):
    r = random.Random(seed)
    return gen_instance(seed, nC=r.randint(1, 2), T=r.randint(2, 3), nD=r.randint(1, 2))


def test_g_is_nonuniform_over_ct():
    nonconst = 0
    for seed in SEEDS:
        inst = _inst(seed)
        assert all(0 <= v <= 3 for v in inst.g.values())
        assert set(inst.g) == {(c, t) for c in inst.C for t in range(inst.T)}
        nonconst += len(set(inst.g.values())) > 1
    assert nonconst >= 80, nonconst


@pytest.mark.parametrize("seed", SEEDS)
def test_ilp_equals_bruteforce_nonuniform_g(seed):
    check_ilp(_inst(seed), use_cache=True)


def test_raising_every_g_never_lowers_optimum():
    """Monotonicity in g, and caches are actually used in >=5 of the 40 instances."""
    used = 0
    for seed in SEEDS[:40]:
        inst = _inst(seed)
        res = solve(inst)
        used += sum(res["solution"].mu.values()) > 0
        hi = type(inst)(**{**inst.__dict__, "g": {k: v + 10 ** 6 for k, v in inst.g.items()}})
        res_hi = solve(hi)
        assert res_hi["objective"] >= res["objective"]
    assert used >= 5
