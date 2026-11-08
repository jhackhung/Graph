"""Phase 12 (DEC-2 = cloud counts as cache): adapter cache_mode, per-node g, sample-mode regression."""
import os

import pandas as pd
import pytest

from ilp.adapter import TINY_CONFIG, from_existing, from_tsmta_output
from ilp.evaluate import check_solution, evaluate
from ilp.instance import reachable, validate_instance
from ilp.model_cpsat import solve

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = dict(TINY_CONFIG, n_sats=12, n_clouds=2, n_dests=3, total_time=3)
SEEDS = (42, 43, 44, 45)

# hand-checked: cloud (linear, gamma=1): g = d*1e5 ; satellite (concave, z=0.8, gamma=1.5, size 1): g = 1.5*d*1e5
GOLDEN = {42: {"v0": 105785, "v10": 149146, "v14": 99759},      # d = 1.05785, 0.99431, 0.66506
          43: {"v1": 261671, "v8": 96116, "v17": 218734}}       # d = 2.61671, 0.64077, 1.45823


def _fresh_graphs(cfg, seed, redraws_seed):
    """Regenerate the repo graph for the graph seed the adapter settled on."""
    import random
    from ilp.adapter import _repo
    np, _, _, _, gen = _repo()
    random.seed(redraws_seed)
    np.random.seed(redraws_seed)
    return gen(seed=redraws_seed, **{k: cfg[k] for k in TINY_CONFIG})


@pytest.mark.parametrize("seed", SEEDS)
def test_repo_mode_C_equals_graph_cache_attribute(seed):
    inst, graphs, attrs = from_existing(CFG, seed, cache_mode="repo")
    fresh = _fresh_graphs(CFG, seed, inst.meta["graph_seed"])
    flagged = {n for n, d in fresh[0].nodes(data=True) if d["cache"] is True}
    assert set(inst.C) == flagged and len(inst.C) == len(set(inst.C))
    types = {n: d["type"] for n, d in fresh[0].nodes(data=True)}
    assert {n for n in types if types[n] == "cloud"} <= set(inst.C)          # all clouds are caches
    assert inst.meta["n_cloud_in_C"] == CFG["n_clouds"]
    assert inst.meta["n_sat_in_C"] == len(inst.C) - CFG["n_clouds"]
    assert inst.meta["C_size"] == len(inst.C)
    # the adapter did not rewrite any cache attribute (neither in graphs[0] nor in later slots)
    for t, H in enumerate(graphs):
        for n, d in H.nodes(data=True):
            assert d["cache"] == fresh[t].nodes[n]["cache"], (t, n)
    assert {n for n, d in graphs[0].nodes(data=True) if d["cache"] is True} == set(inst.C)
    assert attrs["v0"]["cache"] is True


@pytest.mark.parametrize("seed", SEEDS[:2])
def test_same_C_reaches_tsmta(seed):
    inst, graphs, attrs = from_existing(CFG, seed, cache_mode="repo")
    sols = from_tsmta_output(inst, graphs, attrs, k=2)       # asserts graph cache attr == inst.C
    for sol in sols.values():
        assert set(c for (c, _) in sol.mu) == set(inst.C)


@pytest.mark.parametrize("seed", sorted(GOLDEN))
def test_g_per_node_per_slot(seed):
    inst, graphs, _ = from_existing(CFG, seed, cache_mode="repo")
    for c, expect in GOLDEN[seed].items():
        for t in range(inst.T):
            assert inst.g[(c, t)] == expect, (seed, c, t)
    # formula check from raw attributes (independent of Algorithm.cost_cache), every (c,t)
    for c in inst.C:
        for t in range(inst.T):
            a = graphs[t].nodes[c]
            if a["type"] == "cloud":
                assert a["storage_model"] == "linear"
                want = a["d"] * 1.0
            else:
                assert a["storage_model"] == "concave"
                want = a["gamma"] * a["d"] * 1.0 ** a["z"]
            assert inst.g[(c, t)] == round(want * inst.scale)
    cloud = {round(inst.g[(c, 0)] / (graphs[0].nodes[c]["d"] * inst.scale), 3) for c in inst.C
             if graphs[0].nodes[c]["type"] == "cloud"}
    sat = {round(inst.g[(c, 0)] / (graphs[0].nodes[c]["d"] * inst.scale), 3) for c in inst.C
           if graphs[0].nodes[c]["type"] == "satellite"}
    assert cloud == {1.0} and sat == {1.5}                     # cloud and satellite formulas differ
    assert len({inst.g[(c, 0)] for c in inst.C}) > 1           # not one shared value


@pytest.mark.parametrize("n_clouds", [1, 2, 5])
@pytest.mark.parametrize("seed", [42, 43, 44])
def test_repo_instance_valid_oneway_reachable(n_clouds, seed):
    cfg = dict(CFG, n_clouds=n_clouds)
    inst, *_ = from_existing(cfg, seed, cache_mode="repo")
    validate_instance(inst)
    assert not set(inst.C) & ({inst.s} | set(inst.D))
    for t in range(inst.T):
        assert not any(v == inst.s for _, v in inst.arcs[t])
        assert not any(u in inst.D for u, _ in inst.arcs[t])
        assert set(inst.D) <= reachable(inst.arcs[t], inst.s)


def test_default_mode_is_repo():
    inst, *_ = from_existing(CFG, 42)
    assert inst.meta["cache_mode"] == "repo"


def test_sample_mode_rejects_clouds():
    with pytest.raises(AssertionError):
        from_existing(CFG, 42, cache_mode="sample")


def _pick_rows():
    df = pd.read_csv(os.path.join(ROOT, "results", "ratio_small.csv"))
    rows = df.iloc[::128]
    bad = df[df.tsmta_opt_feasible == 0].iloc[:2]
    return pd.concat([rows, bad]).drop_duplicates(subset=["n_sats", "n_dests", "n_c", "T", "seed", "alpha", "beta"])


@pytest.mark.parametrize("i", range(len(_pick_rows())))
def test_sample_mode_matches_ratio_small(i):
    row = _pick_rows().iloc[i]
    cfg = dict(TINY_CONFIG, n_sats=int(row.n_sats), n_dests=int(row.n_dests), total_time=int(row["T"]))
    inst, graphs, attrs = from_existing(cfg, int(row.seed), n_c=int(row.n_c), scale=10 ** 5,
                                        alpha=int(row.alpha), beta=int(row.beta), cache_mode="sample")
    assert (len(inst.nodes), sum(len(a) for a in inst.arcs), inst.meta["redraws"]) == \
           (row.n_nodes, row.n_arcs, row.redraws)
    sols = from_tsmta_output(inst, graphs, attrs, k=2)
    for name, col, fcol in (("raw", "TC_raw", "tsmta_raw_feasible"), ("optimal", "TC_opt", "tsmta_opt_feasible")):
        viol = check_solution(inst, sols[name])
        assert int(not viol) == row[fcol]
        if not viol:
            assert evaluate(inst, sols[name])["TC"] == row[col]
    res = solve(inst, time_limit=60, workers=4)
    assert res["objective"] / inst.scale == row.TC_ilp
