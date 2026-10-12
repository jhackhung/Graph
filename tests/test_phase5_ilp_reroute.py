"""Phase 5: ILP, multi-slot, no cache, rerouting. Random seeds 2000..2099 (T=2..3, beta in {0,1,5,50})."""
from dataclasses import replace

import pytest

from ilp.brute_force import solve_brute
from ilp.evaluate import evaluate
from ilp.gen_random import gen_instance
from ilp.make_toys import toy1
from tests.ilp_helpers import check_ilp, slot_instance
from ilp.model_cpsat import solve

BETAS = [0, 1, 5, 50]


@pytest.mark.parametrize("beta,expect", [(0, 15), (1, 17), (2, 19), (3, 21), (10, 22)])
def test_toy1_no_cache(beta, expect):
    inst = replace(toy1(), C=[], g={}, beta=beta)
    res, _ = check_ilp(inst, use_cache=False)
    assert res["objective"] == expect
    inst2 = replace(toy1(), beta=beta)                         # C kept but use_cache=False
    assert solve(inst2, use_cache=False)["objective"] == expect


@pytest.mark.parametrize("seed", range(2000, 2100))
def test_random_matches_brute(seed):
    inst = gen_instance(seed, T=2 + seed % 2, beta=BETAS[seed % 4])
    check_ilp(inst, use_cache=False)


@pytest.mark.parametrize("seed", range(2100, 2115))
def test_beta0_is_sum_of_independent_slots(seed):
    inst = gen_instance(seed, T=3, beta=0)
    total = sum(solve(slot_instance(inst, t), use_cache=False)["objective"] for t in range(inst.T))
    assert solve(inst, use_cache=False)["objective"] == total


@pytest.mark.parametrize("seed", range(2200, 2215))
def test_beta_monotone_and_large_beta_min_rc(seed):
    base = gen_instance(seed, T=3, beta=0)
    prev_tc, prev_rc = -1, 10 ** 9
    for beta in (0, 1, 2, 5, 20, 50):
        inst = replace(base, beta=beta)
        _, ev = check_ilp(inst, use_cache=False, brute=False)
        assert ev["TC_int"] >= prev_tc
        assert ev["RC"] <= prev_rc
        prev_tc, prev_rc = ev["TC_int"], ev["RC"]
    big = sum(w for x in base.arcs for w in x.values()) + 1       # exceeds any BC difference
    inst = replace(base, beta=big)
    _, ev = check_ilp(inst, use_cache=False, brute=False)
    bt, bsol = solve_brute(inst, False)
    assert ev["RC"] == evaluate(inst, bsol)["RC"]


@pytest.mark.parametrize("seed", range(2300, 2380))
def test_random_heavy_perturbation_matches_brute(seed):
    """Weights change a lot between slots, so rerouting actually matters (see test below)."""
    inst = gen_instance(seed, T=2 + seed % 2, beta=(0, 1, 2, 3)[seed % 4], n_change=6)
    check_ilp(inst, use_cache=False)


def test_heavy_perturbation_exercises_rerouting():
    n_rc = 0
    for seed in range(2300, 2380):
        inst = gen_instance(seed, T=2 + seed % 2, beta=(0, 1, 2, 3)[seed % 4], n_change=6)
        n_rc += solve(inst, use_cache=False)["solution"] is not None and \
            evaluate(inst, solve(inst, use_cache=False)["solution"])["RC"] > 0
    assert n_rc >= 10
