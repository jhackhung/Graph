"""Re-score TSMTA and ILP solutions with the repo's own cost definition (evaluate_repo_compat).

    PYTHONUTF8=1 python -m ilp.rescore_repo --seeds 20 --out results/rescore_repo.csv

Caveat: the ILP still minimises the paper-style objective (ilp.evaluate), so its solution is NOT optimal
for the repo objective. ratio_repo = TC_repo(TSMTA) / TC_repo(ILP solution) is therefore only a lower bound
on the true repo-definition approximation ratio, and can be < 1. Arc weights are the true quantised
weights (w_int / S), not the weights stored inside TSMTA's trees.
"""
from __future__ import annotations

import argparse
import csv
import itertools
import os
import sys
from concurrent.futures import ProcessPoolExecutor

COLS = ["n_sats", "n_dests", "n_c", "T", "seed", "alpha", "beta", "tsmta_feasible",
        "paper_TC_tsmta", "paper_TC_ilp", "paper_ratio",
        "repo_BC_tsmta", "repo_CC_tsmta", "repo_RC_tsmta", "repo_TC_tsmta",
        "repo_BC_ilp", "repo_CC_ilp", "repo_RC_ilp", "repo_TC_ilp", "repo_ratio"]


def to_repo_trees(inst, sol, selected):
    """selected[t] = {cache: g_float} that count as cache_selected in slot t."""
    S = inst.scale
    trees = []
    for t in range(inst.T):
        edges = [[u, v, inst.arcs[t][(u, v)] / S] for (u, v) in sorted(sol.arcs[t])]
        trees.append({"edges": edges, "dests": list(inst.D), "cache_selected": selected[t]})
    return trees


def repo_score(inst, sol, selected):
    from .evaluate import evaluate_repo_compat
    return evaluate_repo_compat(to_repo_trees(inst, sol, selected), inst.C, inst.s,
                                inst.alpha, inst.beta)


def run_one(p):
    from .adapter import TINY_CONFIG, from_existing, from_tsmta_output
    from .evaluate import check_solution, evaluate
    from .model_cpsat import solve

    cfg = dict(TINY_CONFIG, n_sats=p["n_sats"], n_dests=p["n_dests"], total_time=p["T"])
    inst, graphs, attrs = from_existing(cfg, p["seed"], n_c=p["n_c"], scale=p["scale"],
                                        alpha=p["alpha"], beta=p["beta"], cache_mode="sample")
    # flag mode: mu = TSMTA's own cache_selected flags, the closest match to what the repo scores
    ts = from_tsmta_output(inst, graphs, attrs, k=2, mu_mode="flag")["optimal"]
    res = solve(inst, time_limit=p["time_limit"], workers=p["workers"])
    il = res["solution"]
    S = inst.scale

    def sel(sol):
        return [{c: inst.g[(c, t)] / S for c in inst.C if sol.mu.get((c, t), 0) == 1}
                for t in range(inst.T)]

    row = {c: "" for c in COLS}
    row.update({k: p[k] for k in ("n_sats", "n_dests", "n_c", "T", "seed", "alpha", "beta")})
    feas = not check_solution(inst, ts)
    row["tsmta_feasible"] = int(feas)
    if feas:
        row["paper_TC_tsmta"] = evaluate(inst, ts)["TC"]
    row["paper_TC_ilp"] = res["objective"] / S
    if feas:
        row["paper_ratio"] = row["paper_TC_tsmta"] / row["paper_TC_ilp"]
    # the repo score does not check feasibility, so infeasible TSMTA trees are scored too
    b, c, r, tc = repo_score(inst, ts, sel(ts))
    row.update(repo_BC_tsmta=b, repo_CC_tsmta=c, repo_RC_tsmta=r, repo_TC_tsmta=tc)
    b, c, r, tc = repo_score(inst, il, sel(il))
    row.update(repo_BC_ilp=b, repo_CC_ilp=c, repo_RC_ilp=r, repo_TC_ilp=tc)
    row["repo_ratio"] = row["repo_TC_tsmta"] / row["repo_TC_ilp"]
    return row


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=20)
    ap.add_argument("--first-seed", type=int, default=42)
    ap.add_argument("--n-sats", type=int, nargs="+", default=[8, 12, 16, 20])
    ap.add_argument("--n-dests", type=int, nargs="+", default=[2, 3])
    ap.add_argument("--n-c", type=int, nargs="+", default=[1, 2])
    ap.add_argument("--T", type=int, nargs="+", default=[3, 4])
    ap.add_argument("--ab", type=int, nargs="+", default=[1, 100, 5, 10])
    ap.add_argument("--scale", type=int, default=10 ** 5)
    ap.add_argument("--time-limit", type=float, default=600.0)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--out", default="results/rescore_repo.csv")
    a = ap.parse_args(argv)
    abs_ = list(zip(a.ab[0::2], a.ab[1::2]))
    tasks = [dict(n_sats=ns, n_dests=nd, n_c=nc, T=T, seed=a.first_seed + i, alpha=al, beta=be,
                  scale=a.scale, time_limit=a.time_limit, workers=a.workers)
             for ns, nd, nc, T, (al, be) in itertools.product(a.n_sats, a.n_dests, a.n_c, a.T, abs_)
             for i in range(a.seeds)]
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with ProcessPoolExecutor(max_workers=a.jobs) as ex:
        rows = list(ex.map(run_one, tasks, chunksize=1))
    with open(a.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {a.out}: {len(rows)} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
