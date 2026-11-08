"""Scale probe (PLAN Phase 10): how large can CP-SAT prove optimality within the time limit?

    PYTHONUTF8=1 python -m ilp.scale_probe --n-sats 8 12 16 20 30 40 60 80 --seeds 5
Fixed |D|=3, |C|=2, T=4. ILP only (TSMTA not run).
"""
import argparse
import csv
import itertools
import os
import time
from concurrent.futures import ProcessPoolExecutor

COLS = ["n_sats", "n_clouds", "C_size", "n_cloud_in_C", "seed", "alpha", "beta", "n_nodes", "n_arcs", "n_vars", "n_cons", "status",
        "objective", "bound", "gap", "consistent", "t_build", "t_solve", "redraws"]


def probe(p):
    from .adapter import TINY_CONFIG, from_existing
    from .evaluate import check_solution, evaluate
    from .model_cpsat import solve
    cfg = dict(TINY_CONFIG, n_sats=p["n_sats"], n_dests=3, total_time=4,
               num_planes=p["planes"], n_clouds=p["n_clouds"])
    t0 = time.time()
    inst, *_ = from_existing(cfg, p["seed"], n_c=2, scale=10 ** 5, alpha=p["alpha"], beta=p["beta"],
                           cache_mode=p["cache_mode"])
    t_build = time.time() - t0
    t1 = time.time()
    try:
        r = solve(inst, time_limit=p["time_limit"], workers=p["workers"])
    except RuntimeError as e:
        if "UNKNOWN" not in str(e):
            raise
        # no feasible solution within the time limit: record it (size from a rebuilt model), do not abort
        from .model_cpsat import build_model, count_model
        n_vars, n_cons = count_model(build_model(inst)[0])
        return dict(n_sats=p["n_sats"], n_clouds=p["n_clouds"], C_size=inst.meta["C_size"],
                    n_cloud_in_C=inst.meta["n_cloud_in_C"], seed=p["seed"], alpha=p["alpha"],
                    beta=p["beta"], n_nodes=len(inst.nodes), n_arcs=sum(len(a) for a in inst.arcs),
                    n_vars=n_vars, n_cons=n_cons, consistent="", status="UNKNOWN", objective="",
                    bound="", gap="", t_build=round(t_build, 2), t_solve=round(time.time() - t1, 2),
                    redraws=inst.meta["redraws"])
    viol = check_solution(inst, r["solution"])
    why = "; ".join(viol[:5])
    if not viol:
        tc = evaluate(inst, r["solution"], check=False)["TC_int"]
        if tc != r["objective"]:
            why = f"TC_int {tc} != ObjectiveValue {r['objective']} (diff {tc - r['objective']})"
    ok = not why
    if not ok:    # keep a reproduction of every inconsistency
        from .instance import save_instance, save_solution
        d = "results/scale_inconsistent"
        os.makedirs(d, exist_ok=True)
        tag = f"s{p['n_sats']}_cl{p['n_clouds']}_seed{p['seed']}_a{p['alpha']}_b{p['beta']}"
        save_instance(inst, os.path.join(d, tag + "_probe_instance.json"))
        save_solution(r["solution"], os.path.join(d, tag + "_probe_solution.json"))
        with open(os.path.join(d, tag + "_probe_reason.txt"), "w", encoding="utf-8") as fh:
            fh.write(why + chr(10) + chr(10).join(viol))
    S = inst.scale
    obj, bd = r["objective"] / S, r["bound"] / S
    return dict(n_sats=p["n_sats"], n_clouds=p["n_clouds"], C_size=inst.meta["C_size"],
                n_cloud_in_C=inst.meta["n_cloud_in_C"], seed=p["seed"], alpha=p["alpha"], beta=p["beta"],
                n_nodes=len(inst.nodes), n_arcs=sum(len(a) for a in inst.arcs), n_vars=r["n_vars"],
                n_cons=r["n_cons"], consistent=int(ok), status=r["status"], objective=obj, bound=bd,
                gap=(obj - bd) / obj if obj else 0.0, t_build=round(t_build, 2),
                t_solve=round(r["runtime"], 2), redraws=inst.meta["redraws"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-sats", type=int, nargs="+", default=[8, 12, 16, 20, 30, 40])
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--n-clouds", type=int, default=0)
    ap.add_argument("--cache-mode", choices=["repo", "sample"], default="repo")
    ap.add_argument("--planes", type=int, default=4)
    ap.add_argument("--time-limit", type=float, default=600.0)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--out", default="results/scale_probe.csv")
    a = ap.parse_args()
    tasks = [dict(n_sats=n, seed=42 + i, alpha=al, beta=be, planes=a.planes, n_clouds=a.n_clouds, cache_mode=a.cache_mode, time_limit=a.time_limit,
                  workers=a.workers)
             for n, (al, be), i in itertools.product(a.n_sats, [(1, 100), (5, 10)], range(a.seeds))]
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "w", newline="", encoding="utf-8") as fh, ProcessPoolExecutor(a.jobs) as ex:
        w = csv.DictWriter(fh, fieldnames=COLS)
        w.writeheader()
        for row in ex.map(probe, tasks):
            w.writerow(row)
            fh.flush()
            print(row, flush=True)


if __name__ == "__main__":
    main()
