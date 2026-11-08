"""Batch experiment: TSMTA (Raw / Optimal) vs exact ILP on small instances (PLAN Phase 8).

Run from the repo root:
    PYTHONUTF8=1 python -m ilp.run_ratio --seeds 20 --jobs 8 --out results/ratio_cloud.csv
Every row is checked against the invariants of PLAN 8; any violation aborts after the CSV is written.
"""
from __future__ import annotations

import argparse
import csv
import itertools
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

COLS = ["n_sats", "n_clouds", "cache_mode", "C_size", "n_cloud_in_C", "n_dests", "n_c", "T", "seed", "alpha", "beta", "k", "redraws",
        "n_nodes", "n_arcs", "tsmta_raw_feasible", "tsmta_opt_feasible",
        "TC_raw", "TC_opt", "RC_raw", "RC_opt", "TC_ilp", "TC_ilp_hint", "bound", "bound_hint",
        "status", "status_hint", "t_ilp", "t_ilp_hint", "first_hint", "n_vars", "n_cons",
        "ratio_opt", "ratio_raw", "ratio_upper_opt", "tsmta_violations", "invariant_errors",
        "prune_feasible_raw", "prune_feasible_opt", "dest_disconnected_raw", "dest_disconnected_opt",
        "rep_raw_feasible", "rep_opt_feasible", "TC_raw_rep", "TC_opt_rep", "ratio_raw_rep", "ratio_opt_rep",
        "repair_arcs_raw", "repair_arcs_opt"]


def run_one(p: dict) -> dict:
    from .adapter import TINY_CONFIG, from_existing, from_tsmta_output
    from .evaluate import check_solution, evaluate, prune
    from .instance import reachable, save_instance, save_solution
    from .model_cpsat import solve

    cfg = dict(TINY_CONFIG, n_sats=p["n_sats"], n_dests=p["n_dests"], total_time=p["T"],
               n_clouds=p["n_clouds"])
    inst, graphs, attrs = from_existing(cfg, p["seed"], n_c=p["n_c"], scale=p["scale"],
                                        alpha=p["alpha"], beta=p["beta"], cache_mode=p["cache_mode"])
    sols = from_tsmta_output(inst, graphs, attrs, k=p["k"], mu_mode="derived", collect_errors=True)
    errors = sols.pop("errors")
    row = {c: "" for c in COLS}
    row.update({k: p[k] for k in ("n_sats", "n_clouds", "cache_mode", "n_dests", "n_c", "T", "seed",
                                  "alpha", "beta", "k")})
    row.update(C_size=inst.meta["C_size"], n_cloud_in_C=inst.meta["n_cloud_in_C"])
    row.update(redraws=inst.meta["redraws"], n_nodes=len(inst.nodes),
               n_arcs=sum(len(a) for a in inst.arcs))
    errs, tv = [], []
    ev = {}
    for name, why in errors.items():       # TSMTA produced no usable tree: count as infeasible, not repaired
        row[f"tsmta_{'raw' if name == 'raw' else 'opt'}_feasible"] = 0
        tv.append(f"{name}:{why}")
    for name, sol in sols.items():
        viol = check_solution(inst, sol)
        row[f"tsmta_{'raw' if name == 'raw' else 'opt'}_feasible"] = int(not viol)
        if viol:
            # diagnostic only (never merged into the main table): does pruning make it feasible?
            try:
                row[f"prune_feasible_{'raw' if name == 'raw' else 'opt'}"] = int(
                    not check_solution(inst, prune(inst, sol)))
            except Exception:
                row[f"prune_feasible_{'raw' if name == 'raw' else 'opt'}"] = "error"
            # diagnostic: some destination is not reachable from s inside the TSMTA tree of some slot
            # (pruning can never repair that, it only removes arcs)
            row[f"dest_disconnected_{'raw' if name == 'raw' else 'opt'}"] = int(any(
                not set(inst.D) <= reachable(sol.arcs[t], inst.s) for t in range(inst.T)))
            # a finding, not an invariant failure: classify, record, dump a reproduction, never repair
            tv.append(f"{name}:" + "+".join(sorted({x.split(':')[0] for x in viol})))
            if p.get("dump_dir"):
                os.makedirs(p["dump_dir"], exist_ok=True)
                tag = f"s{p['n_sats']}_cl{p['n_clouds']}_d{p['n_dests']}_c{p['n_c']}_T{p['T']}_seed{p['seed']}_a{p['alpha']}_b{p['beta']}_{name}"
                save_instance(inst, os.path.join(p["dump_dir"], tag + "_instance.json"))
                save_solution(sol, os.path.join(p["dump_dir"], tag + "_solution.json"))
                with open(os.path.join(p["dump_dir"], tag + "_violations.txt"), "w", encoding="utf-8") as fh:
                    fh.write(chr(10).join(viol))
        else:
            ev[name] = evaluate(inst, sol)
    if "raw" in ev:
        row.update(TC_raw=ev["raw"]["TC"], RC_raw=ev["raw"]["RC"])
    if "optimal" in ev:
        row.update(TC_opt=ev["optimal"]["TC"], RC_opt=ev["optimal"]["RC"])

    res = solve(inst, time_limit=p["time_limit"], workers=p["workers"])
    hint = sols["optimal"] if "optimal" in ev else None
    resh = solve(inst, time_limit=p["time_limit"], workers=p["workers"], hint=hint) if hint else None
    S = inst.scale
    row.update(TC_ilp=res["objective"] / S, bound=res["bound"] / S, status=res["status"],
               t_ilp=round(res["runtime"], 3), n_vars=res["n_vars"], n_cons=res["n_cons"])
    if resh:
        row.update(TC_ilp_hint=resh["objective"] / S, bound_hint=resh["bound"] / S,
                   status_hint=resh["status"], t_ilp_hint=round(resh["runtime"], 3),
                   first_hint=(resh["first_objective"] or 0) / S)

    # ---- invariants (PLAN 8)
    for r in [res] + ([resh] if resh else []):
        if check_solution(inst, r["solution"]):
            errs.append("ILP solution infeasible")
        elif evaluate(inst, r["solution"])["TC_int"] != r["objective"]:
            errs.append("evaluate(ILP).TC_int != ObjectiveValue")
    for name in ev:
        tc_int = ev[name]["TC_int"]
        for r in [res] + ([resh] if resh else []):
            if r["status"] == "OPTIMAL" and r["objective"] > tc_int:
                errs.append(f"ILP optimum {r['objective']} > TSMTA-{name} {tc_int}")
            if r["bound"] > tc_int + 1e-6 and r["status"] != "OPTIMAL":
                errs.append(f"bound {r['bound']} > TSMTA-{name} {tc_int}")
    if resh and "optimal" in ev:
        if resh["first_objective"] is None or resh["first_objective"] > ev["optimal"]["TC_int"]:
            errs.append(f"first hinted solution {resh['first_objective']} > TSMTA {ev['optimal']['TC_int']}")
    if "optimal" in ev and res["status"] == "OPTIMAL":
        row["ratio_opt"] = ev["optimal"]["TC_int"] / res["objective"]
        if row["ratio_opt"] < 1 - 1e-12:
            errs.append("ratio < 1")
    if "raw" in ev and res["status"] == "OPTIMAL":
        row["ratio_raw"] = ev["raw"]["TC_int"] / res["objective"]
    if "optimal" in ev and res["bound"] > 0:
        row["ratio_upper_opt"] = ev["optimal"]["TC_int"] / res["bound"]
    if p.get("repair"):
        # adapter-side connectivity repair (separate run of the same deterministic TSMTA); the columns above
        # stay the un-repaired result
        rsols = from_tsmta_output(inst, graphs, attrs, k=p["k"], mu_mode="derived", collect_errors=True,
                                  repair=True)
        reps = rsols.pop("repairs")
        rsols.pop("errors")
        row.update(repair_arcs_raw=reps.get("raw", 0), repair_arcs_opt=reps.get("optimal_pre", 0) + reps.get("optimal", 0))
        for name, sol in rsols.items():
            short = "raw" if name == "raw" else "opt"
            viol = check_solution(inst, sol)
            row[f"rep_{short}_feasible"] = int(not viol)
            if viol:
                errs.append(f"repaired {name} still infeasible")
                continue
            e = evaluate(inst, sol)
            row[f"TC_{short}_rep"] = e["TC"]
            if res["status"] == "OPTIMAL":
                row[f"ratio_{short}_rep"] = e["TC_int"] / res["objective"]
                if e["TC_int"] < res["objective"]:
                    errs.append(f"repaired {name} TC {e['TC_int']} < ILP optimum {res['objective']}")
    row["tsmta_violations"] = " ".join(tv)
    row["invariant_errors"] = " | ".join(errs)
    return row


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=20)
    ap.add_argument("--first-seed", type=int, default=42)
    ap.add_argument("--n-sats", type=int, nargs="+", default=[8, 12, 16, 20])
    ap.add_argument("--n-dests", type=int, nargs="+", default=[2, 3])
    ap.add_argument("--n-c", type=int, nargs="+", default=[1, 2], help="only for --cache-mode sample")
    ap.add_argument("--n-clouds", type=int, nargs="+", default=[1, 2, 5])
    ap.add_argument("--cache-mode", choices=["repo", "sample"], default="repo")
    ap.add_argument("--T", type=int, nargs="+", default=[3, 4])
    ap.add_argument("--ab", type=int, nargs="+", default=[1, 100, 5, 10], help="alpha beta pairs flat")
    ap.add_argument("--ks", type=int, nargs="+", default=[2])
    ap.add_argument("--scale", type=int, default=10 ** 5)
    ap.add_argument("--time-limit", type=float, default=600.0)
    ap.add_argument("--workers", type=int, default=4, help="CP-SAT workers per solve")
    ap.add_argument("--jobs", type=int, default=4, help="parallel instances")
    ap.add_argument("--out", default="results/ratio_cloud.csv")
    ap.add_argument("--repair", action="store_true", help="also run TSMTA with adapter-side connectivity repair")
    ap.add_argument("--dump-dir", default="results/tsmta_infeasible")
    a = ap.parse_args(argv)
    abs_ = list(zip(a.ab[0::2], a.ab[1::2]))
    # repo mode: C comes from the graph (n_c unused); sample mode: n_clouds is forced to 0
    ncs, nclouds = ([0], a.n_clouds) if a.cache_mode == "repo" else (a.n_c, [0])
    tasks = [dict(n_sats=ns, n_clouds=ncl, cache_mode=a.cache_mode, n_dests=nd, n_c=nc, T=T, seed=a.first_seed + i, alpha=al, beta=be, k=k,
                  scale=a.scale, time_limit=a.time_limit, workers=a.workers, dump_dir=a.dump_dir, repair=a.repair)
             for ns, ncl, nd, nc, T, (al, be), k in itertools.product(a.n_sats, nclouds, a.n_dests, ncs, a.T,
                                                                      abs_, a.ks)
             for i in range(a.seeds)]
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    t0, rows = time.time(), []
    with ProcessPoolExecutor(max_workers=a.jobs) as ex:
        for i, row in enumerate(ex.map(run_one, tasks, chunksize=1), 1):
            rows.append(row)
            if i % 20 == 0 or i == len(tasks):
                print(f"[{i}/{len(tasks)}] {time.time() - t0:.0f}s", flush=True)
    with open(a.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    bad = [r for r in rows if r["invariant_errors"]]
    print(f"wrote {a.out}: {len(rows)} rows, {len(bad)} with invariant errors")
    for r in bad[:10]:
        print("  ", {k: r[k] for k in ("n_sats", "n_clouds", "n_dests", "n_c", "T", "seed", "alpha", "beta")}, r["invariant_errors"])
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
