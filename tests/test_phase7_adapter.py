"""Phase 7: adapter to the existing generator and TSMTA. Seeds 42..61, tiny config, n_c=1..2."""
import collections
import json
import os

import pytest

from ilp.adapter import TINY_CONFIG, from_existing, from_tsmta_output
from ilp.evaluate import check_solution, evaluate
from ilp.instance import (load_solution, reachable, save_solution, solution_from_dict,
                          solution_to_dict, validate_instance)

SEEDS = list(range(42, 62))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(ROOT, "results")


@pytest.fixture(scope="module")
def built():
    out = {}
    for seed in SEEDS:
        inst, graphs, attrs = from_existing(TINY_CONFIG, seed, n_c=1 + seed % 2, scale=10 ** 5,
                                            alpha=5, beta=10, cache_mode="sample")
        sols = {m: from_tsmta_output(inst, graphs, attrs, k=2, mu_mode=m)
                for m in ("derived", "flag")}
        out[seed] = (inst, graphs, attrs, sols)
    return out


def test_instances_valid(built):
    for seed, (inst, graphs, _, _) in built.items():
        validate_instance(inst)
        for t in range(inst.T):
            assert not any(v == inst.s for _, v in inst.arcs[t])
            assert not any(u in inst.D for u, _ in inst.arcs[t])
            assert set(inst.D) <= reachable(inst.arcs[t], inst.s)
        assert len(inst.C) == 1 + seed % 2 and set(inst.C) <= set(inst.nodes) - {inst.s} - set(inst.D)


def test_quantization_error(built):
    worst_abs, worst_rel = 0.0, 0.0
    for inst, *_ in built.values():
        for t in range(inst.T):
            for (u, v), wi in inst.arcs[t].items():
                wf = inst.meta["w_float"][t][f"{u}->{v}"]
                err = abs(wi / inst.scale - wf)
                assert err <= 0.5 / inst.scale + 1e-12
                worst_abs = max(worst_abs, err)
                worst_rel = max(worst_rel, err / wf)
    os.makedirs(RESULTS, exist_ok=True)
    json.dump({"max_abs_err": worst_abs, "max_rel_err": worst_rel},
              open(os.path.join(RESULTS, "phase7_quantization.json"), "w"))
    assert worst_rel < 1e-4          # report D10: ~1.6e-5 at S=1e5 on the small graph


def test_tsmta_solutions_check_and_report(built):
    """Classify (never repair) violations of TSMTA outputs; written to results/ for PROGRESS.md."""
    stats = {}
    for mode in ("derived", "flag"):
        for variant in ("raw", "optimal"):
            codes, infeasible = collections.Counter(), 0
            for inst, _, _, sols in built.values():
                viol = check_solution(inst, sols[mode][variant])
                infeasible += bool(viol)
                codes.update(x.split(":")[0] for x in viol)
            stats[f"{mode}/{variant}"] = {"infeasible_instances": infeasible,
                                          "total": len(built), "violation_counts": dict(codes)}
    os.makedirs(RESULTS, exist_ok=True)
    json.dump(stats, open(os.path.join(RESULTS, "phase7_violations.json"), "w"), indent=1)
    print(json.dumps(stats, indent=1))


def test_solution_json_roundtrip(built, tmp_path):
    for inst, _, _, sols in built.values():
        for mode in sols:
            for variant, sol in sols[mode].items():
                p = str(tmp_path / "s.json")
                save_solution(sol, p)
                sol2 = load_solution(p)
                assert sol2 == sol and solution_from_dict(solution_to_dict(sol)) == sol
                if not check_solution(inst, sol):
                    assert evaluate(inst, sol2) == evaluate(inst, sol)
