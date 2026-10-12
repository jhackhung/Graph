"""Phase 2: independent evaluator. Random property seeds 0..39."""
import copy
from dataclasses import replace

import pytest

from ilp.baseline import sp_solution
from ilp.evaluate import (InfeasibleSolution, build_solution, check_solution, evaluate,
                          prune, relabel)
from ilp.gen_random import gen_instance
from ilp.make_toys import toy1, toy2

S0 = {("s", "c"), ("c", "d1"), ("c", "d2")}                       # slot0 via cache, BC 4
S1_VIA_V = {("s", "v"), ("v", "c"), ("c", "d1"), ("c", "d2")}     # BC 11


def sol(inst, trees, mu, origin_per_slot):
    origin = {(d, t): origin_per_slot[t] for d in inst.D for t in range(inst.T)}
    return build_solution(inst, trees, mu, origin)


def make(name):
    both = {("c", 0): 1, ("c", 1): 1}
    return {
        "S1": ([S1_VIA_V, S1_VIA_V], {}, ["s", "s"]),
        "S2": ([S0, S1_VIA_V], both, ["c", "c"]),
        "S3": ([S0, S1_VIA_V], {}, ["s", "s"]),
        "S4": ([S0, S1_VIA_V], {("c", 1): 1}, ["s", "c"]),
    }[name]


# (BC, CC, RC) by hand; TC table from PLAN appendix A.1
HAND = {"S1": (22, 0, 0), "S2": (15, 2, 0), "S3": (15, 0, 2), "S4": (15, 1, 2)}
TC = {  # (alpha, beta) -> {sol: TC}
    (2, 10): {"S1": 22, "S2": 19, "S3": 35, "S4": 37},
    (2, 1): {"S1": 22, "S2": 19, "S3": 17, "S4": 19},
    (100, 10): {"S1": 22, "S2": 215, "S3": 35, "S4": 135},
}


@pytest.mark.parametrize("name", sorted(HAND))
@pytest.mark.parametrize("ab", sorted(TC))
def test_toy1_hand_values(name, ab):
    inst = replace(toy1(), alpha=ab[0], beta=ab[1])
    r = evaluate(inst, sol(inst, *make(name)[:2], make(name)[2]))
    assert (r["BC"], r["CC"], r["RC"]) == HAND[name]
    assert r["TC"] == TC[ab][name] and r["TC_int"] == TC[ab][name]


def test_toy2_shared_link_once():
    inst = toy2()
    trees = [{("s", "a"), ("a", "d1"), ("a", "d2")}]
    r = evaluate(inst, build_solution(inst, trees, {}, {("d1", 0): "s", ("d2", 0): "s"}))
    assert r["BC"] == 6


# ------------------------------------------------------------ infeasible solutions

def _viol(inst, s_):
    return check_solution(inst, s_)


def _has(viol, code):
    return any(x.startswith(code) for x in viol)


def _base():
    inst = toy1()
    return inst, sol(inst, *make("S2")[:2], make("S2")[2])


def test_reject_indegree2():
    inst, s_ = _base()
    s_.arcs[0] = s_.arcs[0] | {("s", "v"), ("v", "c")}
    v = _viol(inst, s_)
    assert _has(v, "INDEGREE") and "node c" in " ".join(v)


def test_reject_cycle():
    inst = toy1()
    s_ = sol(inst, *make("S3")[:2], make("S3")[2])
    inst.arcs[0][("c", "v")] = 1          # allow a cycle v->c->v disjoint from the tree? make one
    s_.arcs[0] = {("s", "d1"), ("s", "d2"), ("v", "c"), ("c", "v")}
    s_.path = {k: [] for k in s_.path}
    v = _viol(inst, s_)
    assert _has(v, "CYCLE")


def test_reject_arc_not_in_slot():
    inst, s_ = _base()
    s_.arcs[1] = s_.arcs[1] | {("s", "c")}        # s->c does not exist in slot 1
    assert _has(_viol(inst, s_), "ARC_NOT_IN_SLOT")


def test_reject_dest_missing():
    inst, s_ = _base()
    s_.arcs[0] = {("s", "c"), ("c", "d1")}
    assert _has(_viol(inst, s_), "DEST_MISSING")


def test_reject_mu1_cache_not_in_tree():            # A.2 (b)
    inst, s_ = _base()
    s_.arcs[1] = {("s", "d1"), ("s", "d2")}
    v = _viol(inst, s_)
    assert _has(v, "MU_NOT_IN_TREE")


def test_reject_origin_mu0():                       # A.2 (a)
    inst, s_ = _base()
    s_.mu[("c", 0)] = 0
    v = _viol(inst, s_)
    assert _has(v, "ORIGIN_MU0")


def test_reject_origin_not_ancestor():
    inst = toy1()
    s_ = sol(inst, [{("s", "d1"), ("s", "d2"), ("s", "v"), ("v", "c")}, S1_VIA_V],
             {("c", 0): 1}, ["s", "s"])
    s_.origin[("d1", 0)] = "c"                      # c is in tree but d1 hangs off s
    assert _has(_viol(inst, s_), "ORIGIN_NOT_ANCESTOR")


def test_reject_unreachable_node():
    inst = toy1()
    s_ = sol(inst, *make("S3")[:2], make("S3")[2])
    s_.arcs[1] = s_.arcs[1] | {("v", "c")} - {("s", "v")}      # v->c hangs in the air
    s_.arcs[1] = {("s", "d1"), ("s", "d2"), ("v", "c")}
    v = _viol(inst, s_)
    assert _has(v, "UNREACHABLE")


def test_reject_two_arcs_into_c_variant_A2c():      # A.2 (c)
    inst, s_ = _base()
    s_.arcs[0] = S0 | {("s", "v"), ("v", "c")}
    assert _has(_viol(inst, s_), "INDEGREE")


def test_evaluate_raises_on_infeasible():
    inst, s_ = _base()
    s_.mu[("c", 0)] = 0
    with pytest.raises(InfeasibleSolution):
        evaluate(inst, s_)


# ------------------------------------------------------------ properties

def _extra_leaf(inst, s_):
    """Find (t, arc) adding a leaf outside the tree; None if impossible."""
    for t in range(inst.T):
        nodes = {n for a in s_.arcs[t] for n in a}
        for (u, v), w in sorted(inst.arcs[t].items()):
            if u in nodes and v not in nodes and v not in inst.D:
                return t, (u, v), w
    return None


@pytest.mark.parametrize("seed", range(40))
def test_extra_leaf_raises_bc_not_pruned(seed):
    inst = gen_instance(seed)
    s_ = sp_solution(inst)
    assert check_solution(inst, s_) == []
    base = evaluate(inst, s_)
    assert base["pruned_TC_int"] == base["TC_int"]
    leaf = _extra_leaf(inst, s_)
    if leaf is None:
        pytest.skip("no spare leaf arc")
    t, a, w = leaf
    s2 = copy.deepcopy(s_)
    s2.arcs[t].add(a)
    r = evaluate(inst, s2)
    assert r["BC_int"] == base["BC_int"] + inst.f[t] * w
    assert r["pruned_TC_int"] == base["TC_int"]
    assert prune(inst, s2).arcs == s_.arcs


@pytest.mark.parametrize("seed", range(40))
def test_scale_invariance(seed):
    inst = gen_instance(seed)
    s_ = sp_solution(inst)
    k = 7
    big = replace(inst, scale=inst.scale * k,
                  arcs=[{a: w * k for a, w in x.items()} for x in inst.arcs],
                  g={key: v * k for key, v in inst.g.items()})
    r0, r1 = evaluate(inst, s_), evaluate(big, s_)
    assert r1["TC_int"] == k * r0["TC_int"]
    assert r1["TC"] == pytest.approx(r0["TC"]) and r1["RC"] == r0["RC"]


@pytest.mark.parametrize("seed", range(40))
def test_relabel_invariance(seed):
    inst = gen_instance(seed)
    s_ = sp_solution(inst)
    m = {n: f"z_{n[::-1]}" for n in inst.nodes}
    i2, s2 = relabel(inst, s_, m)
    assert check_solution(i2, s2) == []
    assert evaluate(i2, s2) == evaluate(inst, s_)
