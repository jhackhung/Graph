"""Phase 1: Instance validation and JSON round-trip. Random seeds 0..19."""
import copy
import os

import pytest

from ilp.gen_random import gen_instance
from ilp.instance import (InstanceError, Solution, instance_from_dict, instance_to_dict,
                          load_instance, save_instance, solution_from_dict, solution_to_dict,
                          validate_instance)
from ilp.make_toys import toy1, toy2

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def test_toys_valid_and_fixture_files_match():
    for name, inst in (("toy1", toy1()), ("toy2", toy2())):
        validate_instance(inst)
        assert load_instance(os.path.join(FIX, name + ".json")) == inst


@pytest.mark.parametrize("seed", range(20))
def test_random_roundtrip(seed, tmp_path):
    inst = gen_instance(seed)
    validate_instance(inst)
    assert instance_from_dict(instance_to_dict(inst)) == inst
    p = tmp_path / "i.json"
    save_instance(inst, str(p))
    assert load_instance(str(p)) == inst
    assert gen_instance(seed) == inst          # deterministic


def test_toy_roundtrip(tmp_path):
    for inst in (toy1(), toy2()):
        p = tmp_path / "x.json"
        save_instance(inst, str(p))
        assert load_instance(str(p)) == inst


def test_solution_roundtrip():
    sol = Solution(arcs=[{("s", "c"), ("c", "d1")}], mu={("c", 0): 1},
                   origin={("d1", 0): "c"}, path={("d1", 0): [("c", "d1")]})
    assert solution_from_dict(solution_to_dict(sol)) == sol


def _mut(fn, base=toy1):
    inst = copy.deepcopy(base())
    fn(inst)
    return inst


BAD = {
    "arc_into_source": lambda i: i.arcs[0].__setitem__(("v", "s"), 1),
    "arc_out_of_dest": lambda i: i.arcs[0].__setitem__(("d1", "v"), 1),
    "non_int_beta": lambda i: setattr(i, "beta", 2.5),
    "non_int_alpha": lambda i: setattr(i, "alpha", 2.0),
    "unreachable_dest": lambda i: [i.arcs[1].pop(k) for k in [("c", "d1"), ("s", "d1")]],
    "C_intersects_D": lambda i: i.C.append("d1"),
    "zero_weight": lambda i: i.arcs[0].__setitem__(("s", "v"), 0),
    "float_weight": lambda i: i.arcs[0].__setitem__(("s", "v"), 1.5),
    "negative_g": lambda i: i.g.__setitem__(("c", 0), -1),
    "missing_g": lambda i: i.g.pop(("c", 1)),
    "unknown_node": lambda i: i.arcs[0].__setitem__(("s", "zz"), 1),
}


@pytest.mark.parametrize("name", sorted(BAD))
def test_invalid_instances_rejected(name):
    with pytest.raises(InstanceError):
        validate_instance(_mut(BAD[name]))
