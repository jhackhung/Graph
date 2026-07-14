from datetime import datetime
import json
import os
import sys
import time
import random

import networkx as nx
import numpy as np

from Random_Orbit import generate_graph_sequence_realistic
from Save_And_Read_Graphs import save_result_to_excel
import TVM
import DMTS
import OffPA

DIR_PATH = "output_graphs"


# =========================================================
# Algorithm runners
# =========================================================

def Execute_SSSP_Union(
    graphs: list[nx.Graph],
    time_slots: int,
    src_nodes: list[str],
    dest_nodes: set[str],
    weight: str = "cost_traffic",
) -> dict[tuple[int, int], nx.DiGraph]:
    """Build one shortest-path-union multicast tree per time slot."""
    s = src_nodes[0]
    results: list[nx.DiGraph] = []

    for idx, graph in enumerate(graphs):
        _, paths = nx.single_source_dijkstra(graph, source=s, weight=weight)
        T = nx.DiGraph()

        if s in graph:
            T.add_node(s, **dict(graph.nodes[s]))
        else:
            T.add_node(s)

        for d in dest_nodes:
            if d not in paths:
                raise nx.NetworkXNoPath(f"[t={idx}] No path from {s} to dest {d}")

            path = paths[d]
            for u, v in zip(path[:-1], path[1:]):
                if u not in T:
                    T.add_node(u, **dict(graph.nodes[u]))
                if v not in T:
                    T.add_node(v, **dict(graph.nodes[v]))

                edge_attr = dict(graph[u][v])

                if not T.has_edge(u, v):
                    T.add_edge(u, v, **edge_attr)
                else:
                    T[u][v].update(edge_attr)

        results.append(T)

    return {(0, i): results[i] for i in range(time_slots)}


def Execute_DMTS(graphs: list[nx.Graph], time_slots: int) -> dict[tuple[int, int], nx.DiGraph]:
    """Run DMTS baseline once. This tree does not depend on beta."""
    start_time = time.time()
    T = []

    # DMTS paper setting: LMBBSP alpha=0.2 and c=5 candidates.
    alpha = 0.2
    DMTS_candidates = 5

    for _, G in enumerate(graphs):
        src_nodes = [node for node, attr in G.nodes(data=True) if attr["type"] == "src"]
        dest_nodes = [node for node, attr in G.nodes(data=True) if attr["type"] == "dest"]
        T.append(
            DMTS.LMBBSP_multicast(
                G,
                src_nodes[0],
                dest_nodes,
                alpha=alpha,
                c=DMTS_candidates,
            )
        )

    results = DMTS.DMTS(time_slots=time_slots, graphs=T)
    T_i_t = {(0, i): results[i] for i in range(time_slots)}

    total_time = time.time() - start_time
    print(f"Total execution time: {total_time:.4f}s")
    return T_i_t


def Execute_OffPA(
    graphs: list[nx.Graph],
    caches: list[str],
    time_slots: int,
    alpha: float = 1.0
) -> dict[tuple[int, int], nx.DiGraph]:
    """Run OffPA / STARFRONT baseline once. This tree does not depend on beta."""
    start_time = time.time()
    results = OffPA.STARFRONT_sequences(graphs, caches, alpha=alpha)
    T_i_t = {(0, i): results[i] for i in range(time_slots)}

    total_time = time.time() - start_time
    print(f"Total execution time: {total_time:.4f}s")
    return T_i_t


def Execute_TSMTA(
    graphs: list[nx.Graph],
    src_nodes: list[str],
    caches: list[str],
    dest_nodes: set[str],
    node_attr_map: dict,
    time_slots: int,
    pdta_level: int = 2,
    alpha: float = 1.0
) -> tuple[dict[tuple[int, int], nx.DiGraph], dict, dict]:
    """
    Run TSMTA base once.

    Note:
    - TSMTA base tree does not depend on beta.
    - TVM.Optimal may depend on beta, so it is applied later on a copy.
    """
    start_time = time.time()

    caches = [n for n, d in graphs[0].nodes(data=True) if d.get("cache") is True]
    TIG, CTIG, TIG_Edges_Map, CTIG_Edges_Map = TVM.TIG_CTIG(graphs, src_nodes, caches, alpha=alpha)

    dests_set = {}
    for idx, _ in enumerate(src_nodes):
        for i in range(time_slots):
            for j in range(i, time_slots):
                # Important: every interval needs an independent set.
                # TVM.TSMTA mutates these sets in-place.
                dests_set[(idx, i, j)] = set(dest_nodes)

    T_i_t = TVM.TSMTA(
        TIG,
        CTIG,
        TIG_Edges_Map,
        CTIG_Edges_Map,
        src_nodes,
        caches,
        dests_set,
        time_slots,
        node_attr_map,
        pdta_level=pdta_level,
    )

    tsmta_build_runtime_sec = time.time() - start_time

    print(
        f"[TSMTA Build] PDTA_k={pdta_level}, "
        f"runtime={tsmta_build_runtime_sec:.4f}s"
    )

    return T_i_t, TIG, TIG_Edges_Map, tsmta_build_runtime_sec


# =========================================================
# Utility functions
# =========================================================

def float_to_tag(f: float | int) -> str:
    ff = float(f)
    if ff.is_integer():
        return str(int(ff))
    return str(ff).replace(".", "p")



def copy_tree_sequence(
    T_i_t: dict[tuple[int, int], nx.DiGraph],
) -> dict[tuple[int, int], nx.DiGraph]:
    """
    Copy a time-indexed tree sequence before running TVM.Optimal.
    TVM.Optimal mutates T_i_t in-place, so every beta must start from the same base tree.
    """
    return {key: graph.copy(as_view=False) for key, graph in T_i_t.items()}


def calc_mean_std(values: list[float], num_runs: int) -> tuple[float, float]:
    mean_val = float(np.mean(values)) if values else 0.0

    # num_runs = 1 with ddof=1 gives nan, so force std=0.
    if num_runs > 1 and len(values) > 1:
        std_val = float(np.std(values, ddof=1))
    else:
        std_val = 0.0

    return mean_val, std_val


def get_graph_name(cfg: dict, sweep_x: str, num_runs: int) -> str:
    """
    The plotter reads graph_XXX to know the fixed x value.
    - sweep_x='sats'  => graph_XXX means n_sats
    - sweep_x='dests' => graph_XXX means n_dests
    """
    if sweep_x == "sats":
        graph_value = cfg["n_sats"]
    elif sweep_x == "dests":
        graph_value = cfg["n_dests"]
    else:
        raise ValueError("sweep_x must be either 'sats' or 'dests'.")

    return f"graph_{graph_value}_avg{num_runs}"


def make_empty_results(beta_values: list[float], alpha_values: list[float], algo_names: list[str]) -> dict:
    return {
        float_to_tag(beta): {
            float_to_tag(alpha): {
                algo: {
                    "BC": [],
                    "CC": [],
                    "RC": [],
                    "Total": [],
                    "Build_Runtime_sec": [],
                    "Beta_Runtime_sec": [],
                }
                for algo in algo_names
            }
            for alpha in alpha_values
        }
        for beta in beta_values
    }


def append_result(
    all_results: dict,
    beta: float,
    alpha: float,
    algo: str,
    bc: float,
    cc: float,
    rc: float,
    total: float,
    build_runtime_sec: float = 0.0,
    beta_runtime_sec: float = 0.0,
) -> None:
    beta_tag = float_to_tag(beta)
    alpha_tag = float_to_tag(alpha)
    all_results[beta_tag][alpha_tag][algo]["BC"].append(bc)
    all_results[beta_tag][alpha_tag][algo]["CC"].append(cc)
    all_results[beta_tag][alpha_tag][algo]["RC"].append(rc)
    all_results[beta_tag][alpha_tag][algo]["Total"].append(total)
    all_results[beta_tag][alpha_tag][algo]["Build_Runtime_sec"].append(build_runtime_sec)
    all_results[beta_tag][alpha_tag][algo]["Beta_Runtime_sec"].append(beta_runtime_sec)


def evaluate_fixed_tree_algorithms_for_beta(
    all_results: dict,
    beta: float,
    alpha: float,
    T_DMTS: dict[tuple[int, int], nx.DiGraph],
    T_OffPA: dict[tuple[int, int], nx.DiGraph],
    T_SSSP: dict[tuple[int, int], nx.DiGraph],
    src_nodes: list[str],
    caches: list[str],
    time_slots: int,
) -> None:
    """DMTS / OffPA / SSSP do not depend on beta, so only re-evaluate RC/Total."""
    bc, cc, rc, total = TVM.evaluate_algorithm(
        "DMTS",
        T_DMTS,
        src_nodes,
        caches,
        time_slots,
        beta=beta,
        alpha=alpha
    )
    append_result(all_results, beta, alpha, "DMTS", bc, cc, rc, total)

    bc, cc, rc, total = TVM.evaluate_algorithm(
        "OffPA",
        T_OffPA,
        src_nodes,
        caches,
        time_slots,
        beta=beta,
        alpha=alpha
    )
    append_result(all_results, beta, alpha, "OffPA", bc, cc, rc, total)

    bc, cc, rc, total = TVM.evaluate_algorithm(
        "SSSP",
        T_SSSP,
        src_nodes,
        caches,
        time_slots,
        beta=beta,
        alpha=alpha
    )
    append_result(all_results, beta, alpha, "SSSP", bc, cc, rc, total)


def evaluate_tsmta_for_beta(
    all_results: dict,
    beta: float,
    alpha: float,
    T_TSMTA_base: dict[tuple[int, int], nx.DiGraph],
    TIG: dict,
    TIG_Edges_Map: dict,
    src_nodes: list[str],
    caches: list[str],
    node_attr_map: dict,
    time_slots: int,
    cfg: dict,
    current_seed: int,
    tsmta_build_runtime_sec: float = 0.0,
) -> None:
    """
    TSMTA base tree is fixed, but Optimal can use beta in the Total objective.
    Therefore each beta gets its own copy of the same base TSMTA tree.
    """
    beta_start_time = time.time()

    T_TSMTA = copy_tree_sequence(T_TSMTA_base)

    TVM.Optimal(
        T_TSMTA,
        src_nodes,
        caches,
        TIG,
        time_slots,
        100,
        node_attr_map=node_attr_map,
        beta=beta,
        alpha=alpha,
    )

    TVM.expand_virtual_edges(
        T_i_t=T_TSMTA,
        TIG_Interval=TIG,
        TIG_Edges_Map=TIG_Edges_Map,
        srcs=src_nodes,
        caches=caches,
        total_time=time_slots,
    )

    bc, cc, rc, total = TVM.evaluate_algorithm(
        "TSMTA",
        T_TSMTA,
        src_nodes,
        caches,
        time_slots,
        beta=beta,
        alpha=alpha
    )

    beta_runtime_sec = time.time() - beta_start_time

    pdta_level = int(cfg.get("pdta_level", 2))

    print(
        f"[RAW TSMTA] PDTA_k={pdta_level} "
        f"beta={beta} "
        f"alpha={alpha} "
        f"sweep_n_sats={cfg['n_sats']} "
        f"sweep_n_dests={cfg['n_dests']} "
        f"seed={current_seed} "
        f"BC={bc:.2f}, CC={cc:.2f}, RC={rc:.2f}, Total={total:.2f}, "
        f"BuildRuntime={tsmta_build_runtime_sec:.4f}s, "
        f"BetaRuntime={beta_runtime_sec:.4f}s"
    )

    append_result(
        all_results,
        beta,
        alpha,
        "TSMTA",
        bc,
        cc,
        rc,
        total,
        build_runtime_sec=tsmta_build_runtime_sec,
        beta_runtime_sec=beta_runtime_sec,
    )


def save_all_beta_results(
    all_results: dict,
    beta_values: list[float],
    alpha_values: list[float],
    algo_names: list[str],
    cfg: dict,
    num_runs: int,
    sweep_x: str,
) -> None:
    graph_name = get_graph_name(cfg, sweep_x, num_runs)
    pdta_level = int(cfg.get("pdta_level", 2))

    for beta in beta_values:
        for alpha in alpha_values:
            beta_tag = float_to_tag(beta)
            alpha_tag = float_to_tag(alpha)
            
            excel_path = f"{sweep_x}_pdta{pdta_level}_beta_{beta_tag}_alpha_{alpha_tag}.xlsx"

            print(f"\n=== Writing beta={beta} alpha={alpha} results to Excel: {excel_path} ===")

            for algo in algo_names:
                vals_bc = all_results[beta_tag][alpha_tag][algo]["BC"]
                vals_cc = all_results[beta_tag][alpha_tag][algo]["CC"]
                vals_rc = all_results[beta_tag][alpha_tag][algo]["RC"]
                vals_total = all_results[beta_tag][alpha_tag][algo]["Total"]
                vals_build_runtime = all_results[beta_tag][alpha_tag][algo]["Build_Runtime_sec"]
                vals_beta_runtime = all_results[beta_tag][alpha_tag][algo]["Beta_Runtime_sec"]

                mean_bc, std_bc = calc_mean_std(vals_bc, num_runs)
                mean_cc, std_cc = calc_mean_std(vals_cc, num_runs)
                mean_rc, std_rc = calc_mean_std(vals_rc, num_runs)
                mean_total, std_total = calc_mean_std(vals_total, num_runs)
                mean_build_runtime, std_build_runtime = calc_mean_std(vals_build_runtime, num_runs)
                mean_beta_runtime, std_beta_runtime = calc_mean_std(vals_beta_runtime, num_runs)

                row = {
                    "experiment_id": None,
                    "timestamp": datetime.now().isoformat(timespec="seconds"),
                    "graph": graph_name,
                    "algo": algo,
                    "BC": mean_bc,
                    "CC": mean_cc,
                    "RC": mean_rc,
                    "Total": mean_total,
                    "BC_Std": std_bc,
                    "CC_Std": std_cc,
                    "RC_Std": std_rc,
                    "Total_Std": std_total,
                    "Build_Runtime_sec": mean_build_runtime,
                    "Build_Runtime_Std": std_build_runtime,
                    "Beta_Runtime_sec": mean_beta_runtime,
                    "Beta_Runtime_Std": std_beta_runtime,
                    "beta": float(beta),
                    "alpha": float(alpha),
                    "PDTA_k": pdta_level,
                    "Total_Runtime_sec": mean_build_runtime + mean_beta_runtime,
                }

                save_result_to_excel(excel_path, row)
                print(
                    f"Saved beta={beta} alpha={alpha} {algo}: "
                    f"BC={mean_bc:.2f}, CC={mean_cc:.2f}, "
                    f"RC={mean_rc:.2f}, Total={mean_total:.2f}"
                )


# =========================================================
# Main experiment flow
# =========================================================

def main() -> None:
    if len(sys.argv) < 2:
        print("用法: python main.py <config.json> [sats|dests]")
        sys.exit(1)

    config_path = sys.argv[1]
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    os.makedirs(DIR_PATH, exist_ok=True)

    # config 可設定：
    # "beta_values": [1, 10, 50, 100]
    # "sweep_x": "sats" or "dests"
    # "num_runs": 1
    # "base_seed": 42
    alpha_values = [float(x) for x in cfg.get("alpha_values", [1, 10, 50, 100])]
    beta_values = [float(x) for x in cfg.get("beta_values", [1, 10, 50, 100])]
    pdta_level = int(cfg.get("pdta_level", 2))
    sweep_x = sys.argv[2] if len(sys.argv) >= 3 else cfg.get("sweep_x", "sats")
    num_runs = int(cfg.get("num_runs", 1))
    base_seed = int(cfg.get("base_seed", 42))

    if sweep_x not in ("sats", "dests"):
        raise ValueError("sweep_x must be either 'sats' or 'dests'.")

    algo_names = ["DMTS", "OffPA", "SSSP", "TSMTA"]
    all_results = make_empty_results(beta_values, alpha_values, algo_names)

    print(f"📌 sweep_x = {sweep_x}")
    print(f"📌 beta_values = {beta_values}")
    print(f"📌 alpha_values = {alpha_values}")
    print(f"📌 num_runs = {num_runs}")
    print(f"📌 base_seed = {base_seed}")
    print("核心流程：建樹每個 run 只跑一次；DMTS/OffPA/SSSP 只重算 evaluate；TSMTA 對 copy 跑 Optimal(beta)。")

    for run_idx in range(num_runs):
        current_seed = base_seed + run_idx
        print("\n" + "=" * 70)
        print(f"🚀 Run {run_idx + 1}/{num_runs}, seed={current_seed}")
        print("=" * 70)

        random.seed(current_seed)
        np.random.seed(current_seed)
        os.environ["PYTHONHASHSEED"] = str(current_seed)

        graphs = generate_graph_sequence_realistic(
            seed=current_seed,
            n_sats=cfg["n_sats"],
            n_clouds=cfg["n_clouds"],
            n_srcs=cfg["n_srcs"],
            n_dests=cfg["n_dests"],
            total_time=cfg["total_time"],
            num_planes=cfg["num_planes"],
            altitude_km=cfg["altitude_km"],
            inclination_deg=cfg["inclination_deg"],
            f_phasing_param=cfg["f_phasing_param"],
            base_angular_velocity=cfg["base_angular_velocity"],
            thr_cloud_to_cloud=cfg["thr_cloud_to_cloud"],
            region_dist_thr=cfg["region_dist_thr"],
        )

        src_nodes = [n for n, d in graphs[0].nodes(data=True) if d.get("type") == "src"]
        dest_nodes_all = [n for n, d in graphs[0].nodes(data=True) if d.get("type") == "dest"]
        caches = [n for n, d in graphs[0].nodes(data=True) if d.get("cache") is True]
        node_attr_map = {n: dict(d) for n, d in graphs[0].nodes(data=True)}
        time_slots = len(graphs)
        src = src_nodes[0]

        reachable_dests = [d for d in dest_nodes_all if nx.has_path(graphs[0], src, d)]
        dest_nodes = set(reachable_dests)

        print(
            f"Graph info: n_sats={cfg['n_sats']}, "
            f"n_dests={cfg['n_dests']}, "
            f"reachable_dests={len(dest_nodes)}, "
            f"time_slots={time_slots}"
        )

        # ==================================================
        # Build each algorithm once per run.
        # ==================================================
        print("\n--- Build DMTS once ---")
        T_DMTS = Execute_DMTS(graphs, time_slots)

        print("\n--- Build SSSP once ---")
        T_SSSP = Execute_SSSP_Union(graphs, time_slots, src_nodes, dest_nodes)

        # ==================================================
        # beta loop
        # ==================================================
        for alpha in alpha_values:
            print("\n--- Build OffPA once ---")
            T_OffPA = Execute_OffPA(graphs, caches, time_slots, alpha=alpha)

            print("\n--- Build TSMTA base once ---")
            T_TSMTA_base, TIG, TIG_Edges_Map, tsmta_build_runtime_sec = Execute_TSMTA(
                graphs,
                src_nodes,
                caches,
                dest_nodes,
                node_attr_map,
                time_slots,
                pdta_level=pdta_level,
                alpha=alpha,
            )
        
            for beta in beta_values:
                print("\n" + "-" * 60)
                print(f"📌 Evaluate beta = {beta}")
                print(f"\n📌 Evaluate alpha = {alpha} ---")
                print("-" * 60)
  
                evaluate_fixed_tree_algorithms_for_beta(
                    all_results=all_results,
                    beta=beta,
                    alpha=alpha,
                    T_DMTS=T_DMTS,
                    T_OffPA=T_OffPA,
                    T_SSSP=T_SSSP,
                    src_nodes=src_nodes,
                    caches=caches,
                    time_slots=time_slots,
                )
                
                evaluate_tsmta_for_beta(
                    all_results=all_results,
                    beta=beta,
                    alpha=alpha,
                    T_TSMTA_base=T_TSMTA_base,
                    TIG=TIG,
                    TIG_Edges_Map=TIG_Edges_Map,
                    src_nodes=src_nodes,
                    caches=caches,
                    node_attr_map=node_attr_map,
                    time_slots=time_slots,
                    cfg=cfg,
                    current_seed=current_seed,
                    tsmta_build_runtime_sec=tsmta_build_runtime_sec,
                )

    save_all_beta_results(
        all_results=all_results,
        beta_values=beta_values,
        alpha_values=alpha_values,
        algo_names=algo_names,
        cfg=cfg,
        num_runs=num_runs,
        sweep_x=sweep_x,
    )

    print("\n🎉 All beta experiments finished!")


if __name__ == "__main__":
    main()

# 跑k = 1~3, dests = 100的圖去比較證明可以使用k=2就好