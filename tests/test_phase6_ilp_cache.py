"""Phase 6: full ILP with caches. Random seeds 3000..3149 (|C| 1-2, T 2-3, beta {0,1,5,50}, alpha {1,5})."""
from dataclasses import replace

import pytest

from ilp.gen_random import gen_instance
from ilp.make_toys import toy1
from ilp.model_cpsat import solve
from tests.ilp_helpers import check_ilp

A3 = {(2, 0): 15, (2, 1): 17, (2, 2): 19, (2, 10): 19, (2, 100): 19, (100, 10): 22, (100, 100): 22}
BETAS = [0, 1, 5, 50]


def rand_inst(seed, **kw):
    return gen_instance(seed, nC=1 + seed % 2, T=2 + (seed // 2) % 2, alpha=(1, 5)[seed % 2],
                        beta=BETAS[(seed // 4) % 4], **kw)


@pytest.mark.parametrize("ab", sorted(A3))
def test_toy1_full_table(ab):
    inst = replace(toy1(), alpha=ab[0], beta=ab[1])
    res, _ = check_ilp(inst, use_cache=True)
    assert res["objective"] == A3[ab]


@pytest.mark.parametrize("seed", range(3000, 3150))
def test_random_matches_brute(seed):
    check_ilp(rand_inst(seed), use_cache=True)


@pytest.mark.parametrize("seed", range(3200, 3260))
def test_heavy_perturbation_matches_brute(seed):
    inst = gen_instance(seed, nC=1 + seed % 2, T=2 + seed % 2, alpha=(1, 5)[(seed // 2) % 2],
                        beta=(1, 2, 5, 10)[seed % 4], n_change=6)
    check_ilp(inst, use_cache=True)


def test_cache_is_actually_used_sometimes():
    used = 0
    for seed in range(3000, 3150):
        inst = rand_inst(seed)
        used += any(solve(inst)["solution"].mu.values())
    assert used >= 10


@pytest.mark.parametrize("seed", range(3300, 3340))
def test_properties(seed):
    inst = rand_inst(seed)
    with_cache = solve(inst, use_cache=True)["objective"]
    no_cache = solve(inst, use_cache=False)["objective"]
    assert with_cache <= no_cache
    # alpha huge -> never cache, same value as no cache (needs g > 0: a free cache may be used on ties)
    hi = replace(inst, alpha=10 ** 6, g={k: max(v, 1) for k, v in inst.g.items()})
    r = solve(hi, use_cache=True)
    assert not any(r["solution"].mu.values()) and r["objective"] == no_cache
    # beta = 0 -> caches are useless
    b0 = replace(inst, beta=0)
    assert solve(b0, use_cache=True)["objective"] == solve(b0, use_cache=False)["objective"]
    # relaxing the tree requirement can only help
    assert solve(inst, use_cache=True, enforce_tree=False)["objective"] <= with_cache


@pytest.mark.parametrize("seed", range(3400, 3415))
def test_solver_stability(seed):
    inst = rand_inst(seed)
    a = solve(inst, workers=1, seed=0)["objective"]
    b = solve(inst, workers=8, seed=7)["objective"]
    assert a == b
