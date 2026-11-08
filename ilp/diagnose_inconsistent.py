"""Re-solve one scale-probe instance and report why check_solution / evaluate disagree with CP-SAT.

    python -m ilp.diagnose_inconsistent --n-sats 300 --n-clouds 20 --seed 44 --alpha 1 --beta 100
Dumps the instance, the (inconsistent) solution and the violation list into --out-dir.
"""
import argparse
import os

from .adapter import TINY_CONFIG, from_existing
from .evaluate import check_solution, evaluate
from .instance import save_instance, save_solution
from .model_cpsat import solve


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-sats", type=int, required=True)
    ap.add_argument("--n-clouds", type=int, required=True)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--alpha", type=int, required=True)
    ap.add_argument("--beta", type=int, required=True)
    ap.add_argument("--time-limit", type=float, default=600.0)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out-dir", default="results/scale_inconsistent")
    a = ap.parse_args()
    cfg = dict(TINY_CONFIG, n_sats=a.n_sats, n_dests=3, total_time=4, num_planes=4, n_clouds=a.n_clouds)
    inst, *_ = from_existing(cfg, a.seed, scale=10 ** 5, alpha=a.alpha, beta=a.beta, cache_mode="repo")
    r = solve(inst, time_limit=a.time_limit, workers=a.workers)
    viol = check_solution(inst, r["solution"])
    tag = f"s{a.n_sats}_cl{a.n_clouds}_seed{a.seed}_a{a.alpha}_b{a.beta}"
    os.makedirs(a.out_dir, exist_ok=True)
    save_instance(inst, os.path.join(a.out_dir, tag + "_instance.json"))
    save_solution(r["solution"], os.path.join(a.out_dir, tag + "_solution.json"))
    print(tag, r["status"], "objective", r["objective"], "bound", r["bound"])
    print("violations:", len(viol))
    for v in viol[:10]:
        print("  ", v)
    if not viol:
        ev = evaluate(inst, r["solution"])
        print("evaluate TC_int", ev["TC_int"], "BC", ev["BC_int"], "CC", ev["CC_int"], "RC", ev["RC"],
              "diff", ev["TC_int"] - r["objective"])
    with open(os.path.join(a.out_dir, tag + "_violations.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(viol))


if __name__ == "__main__":
    main()
