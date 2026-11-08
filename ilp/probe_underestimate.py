"""Measure how much the repo evaluator under-charges disconnected TSMTA trees at paper scale (PROGRESS Phase 13 step 5).
Run from repo root: PYTHONUTF8=1 python ilp/probe_underestimate.py <n_sats> <n_dests> <seed> [k]  (n_clouds=20, T=10, planes=72, alpha=5, beta=10)
Uses main.py's flow on the unfiltered graphs; prints one RESULT json line."""
import sys, io, contextlib, random, time, json
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import networkx as nx
from ilp.adapter import _repo, TINY_CONFIG, repair_connectivity
np_, Algorithm, TVM, repo_main, gen = _repo()

def stats(trees, s, D, T):
    bad = miss = orph = 0
    for t in range(T):
        G = trees[(0, t)]
        reach = (nx.descendants(G, s) | {s}) if s in G else set()
        m = [d for d in D if d not in reach]
        bad += bool(m); miss += len(m); orph += sum(1 for e in G.edges if e[0] not in reach)
    return bad, miss, orph

def run(n_sats, n_dests, seed, alpha=5, beta=10, k=2):
    cfg = dict(TINY_CONFIG, n_sats=n_sats, n_clouds=20, n_dests=n_dests, total_time=10, num_planes=72)
    random.seed(seed); np_.random.seed(seed)
    graphs = gen(seed=seed, **{kk: cfg[kk] for kk in TINY_CONFIG})
    s = [n for n,d in graphs[0].nodes(data=True) if d.get("type")=="src"][0]
    Dall = [n for n,d in graphs[0].nodes(data=True) if d.get("type")=="dest"]
    C = [n for n,d in graphs[0].nodes(data=True) if d.get("cache") is True]
    D = {d for d in Dall if nx.has_path(graphs[0], s, d)}
    attrs = {n: dict(d) for n,d in graphs[0].nodes(data=True)}
    T = len(graphs)
    out = dict(n_sats=n_sats, n_dests=len(D), seed=seed, C=len(C))
    t0 = time.time()
    with contextlib.redirect_stdout(io.StringIO()):
        TIG, CTIG, TEM, CEM = repo_main.Build_TIG_CTIG(graphs, [s], C, alpha=alpha)
        base,_ = repo_main.Run_TSMTA_Select(TIG, CTIG, TEM, CEM, [s], C, D, attrs, T, pdta_level=k, beta=beta)
        sssp = repo_main.Execute_SSSP_Union(graphs, T, [s], D)
        dmts = repo_main.Execute_DMTS(graphs, T)
        ev = lambda n, tr: TVM.evaluate_algorithm(n, tr, [s], C, T, beta=beta, alpha=alpha, output=False)
        out["SSSP"] = ev("SSSP", sssp)[3]; out["DMTS"] = ev("DMTS", dmts)[3]
        out["sssp_bad"] = stats(sssp, s, D, T)[0]
        raw = repo_main.copy_tree_sequence(base)
        TVM.expand_virtual_edges(T_i_t=raw, TIG_Interval=TIG, TIG_Edges_Map=TEM, srcs=[s], caches=C, total_time=T)
        opt = repo_main.copy_tree_sequence(base)
        TVM.expand_virtual_edges(T_i_t=opt, TIG_Interval=TIG, TIG_Edges_Map=TEM, srcs=[s], caches=C, total_time=T)
        TVM.Optimal(opt, [s], C, TIG, T, 100, node_attr_map=attrs, beta=beta, alpha=alpha)
        for name, tr in (("raw", raw), ("opt", opt)):
            bad, miss, orph = stats(tr, s, D, T)
            e0 = ev("TSMTA", tr)
            nrep = repair_connectivity(tr, graphs, s)
            bad2 = stats(tr, s, D, T)[0]
            e1 = ev("TSMTA", tr)
            out[name] = dict(bad_slots=bad, miss=miss, orphan_arcs=orph, rep_arcs=nrep, bad_after=bad2,
                             BC0=e0[0], CC0=e0[1], RC0=e0[2], T0=e0[3], BC1=e1[0], CC1=e1[1], RC1=e1[2], T1=e1[3])
    out["T"] = T; out["nD_total"] = len(D) * T; out["sec"] = round(time.time() - t0)
    return out

if __name__ == "__main__":
    n_sats, n_dests, seed = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
    k = int(sys.argv[4]) if len(sys.argv) > 4 else 2
    r = run(n_sats, n_dests, seed, k=k)
    print("RESULT " + json.dumps(r))
