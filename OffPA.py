from collections import defaultdict
from enum import Enum
from typing import Any, Dict, List, Set, Tuple
import networkx as nx
import Algorithm

INF = float("inf")


class OffPA(Enum):
    USER = "dest"
    SAT = "satellite"
    CLOUD = "cloud"
    SRC = "src"
    REGION = "region"
    WEIGHT = "latency"


def Setting_Starfront_Thd(G: nx.DiGraph, default_thd: float = 50.0):
    rset: Set[Any] = set()
    for _, d in G.nodes(data=True):
        if d["type"] != OffPA.USER.value:
            continue
        r = d.get(OffPA.REGION.value)
        if r is not None:
            rset.add(r)
    return {r: default_thd for r in sorted(rset)}


def STARFRONT_sequences(
    graphs: List[nx.DiGraph],
    caches: List[str],
    Thd_Latency: Dict[str, float] | None = None,
    alpha: float = 1.0
):
    if not graphs:
        return []

    if not Thd_Latency:
        Thd_Latency = Setting_Starfront_Thd(graphs[0])

    res: List[nx.DiGraph] = []
    for i in range(len(graphs)):
        res.append(STARFRONT(G=graphs[i], Thd_Latency=Thd_Latency, caches=caches, alpha=alpha))
    return res


def STARFRONT(G: nx.DiGraph, Thd_Latency: Dict[str, float], caches: List[str], alpha: float = 1.0) -> nx.DiGraph:
    """
    Revised OffPA-style STARFRONT:
    - access cost: per-request full-path cost
    - distribution cost: per-selected-cache full-path cost
    - storage cost: only selected cache nodes, not all relay nodes in DG
    """

    # ---------------------------
    # Helpers
    # ---------------------------
    def is_cache_node(n: str) -> bool:
        return G.nodes[n].get("type") in (OffPA.CLOUD.value, OffPA.SAT.value)

    def edge_cost(u: str, v: str) -> float:
        if G.has_edge(u, v):
            return float(G[u][v].get("cost_traffic", 0.0))
        return 0.0

    def path_cost(path: List[str], flow_size: float) -> float:
        if not path or len(path) < 2:
            return 0.0
        total = 0.0
        for u, v in zip(path[:-1], path[1:]):
            total += flow_size * edge_cost(u, v)
        return total

    def pick_best_src_to_cache_path(cache_node: str, src_nodes: List[str]) -> Tuple[str, List[str], float]:
        """
        Pick the cheapest src -> cache path by latency weight.
        """
        best_src = None
        best_path = None
        best_dist = INF

        for s in src_nodes:
            try:
                dist = nx.shortest_path_length(G, s, cache_node, weight=OffPA.WEIGHT.value)
                path = nx.shortest_path(G, s, cache_node, weight=OffPA.WEIGHT.value)
                if dist < best_dist:
                    best_dist = dist
                    best_src = s
                    best_path = path
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                continue

        if best_src is None or best_path is None:
            raise ValueError(f"No source-to-cache path found for cache {cache_node}")

        return best_src, best_path, best_dist

    def add_path_with_attrs(DG: nx.DiGraph, path: List[str]) -> nx.DiGraph:
        if not path:
            return DG
        nodes = list(path)
        edges = list(zip(path[:-1], path[1:]))

        return Algorithm.add_nodes_edges_with_attrs(
            DG, G,
            nodes=nodes,
            edges=edges,
            nodes_attr={n: dict(G.nodes[n]) for n in nodes},
            edges_attr={(u, v): dict(G[u][v]) for u, v in edges}
        )

    def CT_dist_from_paths(distribution_paths: Dict[str, List[str]]) -> float:
        """
        Sum distribution cost for each selected cache.
        cache_j -> path(src -> ... -> cache_j)
        """
        total = 0.0
        for cache_j, path in distribution_paths.items():
            if not path:
                continue
            src = path[0]
            data_size = float(G.nodes[src].get("data_size", 0.0))
            total += path_cost(path, data_size)
        return total

    def CT_access_from_paths(assigned_req_paths: Dict[str, List[str]]) -> float:
        """
        Sum access cost for each request independently.
        req -> path(req -> ... -> assigned_cache)
        """
        total = 0.0
        for req, path in assigned_req_paths.items():
            if not path:
                continue
            req_size = float(G.nodes[req].get("req_size", 0.0))
            total += path_cost(path, req_size)
        return total

    def CT_storage(selected_caches: Set[str], alpha: float = 1.0) -> float:
        """
        Only selected cache servers incur storage cost.
        Relay satellites/clouds on paths do NOT.
        """
        total = 0.0

        # Total content size from all sources
        W_total = sum(
            float(d.get("data_size", 0.0))
            for _, d in G.nodes(data=True)
            if d.get("type") == OffPA.SRC.value
        )

        for n in selected_caches:
            if not is_cache_node(n):
                continue
            attr = G.nodes[n]
            total += Algorithm.cost_cache(attr, W_total, alpha=alpha)
        return total

    def CT(
        selected_caches: Set[str],
        distribution_paths: Dict[str, List[str]],
        assigned_req_paths: Dict[str, List[str]],
        alpha: float = 1.0
    ) -> float:
        return (
            CT_dist_from_paths(distribution_paths)
            + CT_storage(selected_caches, alpha=alpha)
            + CT_access_from_paths(assigned_req_paths)
        )

    # ---------------------------
    # Initialization
    # ---------------------------
    RQ_remain = {
        n for n, d in G.nodes(data=True)
        if d.get("type") == OffPA.USER.value
    }

    srcs = [
        n for n, d in G.nodes(data=True)
        if d.get("type") == OffPA.SRC.value
    ]

    if not srcs:
        raise ValueError("No source nodes found in graph.")

    DG = nx.DiGraph()

    # Explicit states for cost accounting
    selected_caches: Set[str] = set()              # chosen cache servers only
    distribution_paths: Dict[str, List[str]] = {}  # cache -> path(src->cache)
    assigned_req_paths: Dict[str, List[str]] = {}  # req -> path(req->cache)

    cnt = 0

    # ---------------------------
    # Main greedy loop
    # ---------------------------
    while RQ_remain:
        candidate: Dict[str, Dict[str, float]] = defaultdict(dict)
        candidate_paths: Dict[str, Dict[str, List[str]]] = defaultdict(dict)
        size_j: Dict[str, float] = {}

        # Only consider cache candidates that are valid cache nodes
        valid_caches = [j for j in caches if j in G.nodes and is_cache_node(j)]

        # Stage I: find candidate requests for each cache j
        for j in valid_caches:
            try:
                res = Algorithm.multi_src_to_one_dest_subgraph(
                    G,
                    srcs=list(RQ_remain),
                    dest=j,
                    weight=OffPA.WEIGHT.value,
                    with_attrs=True,
                )
            except Exception:
                continue

            for req_r, item in res.get("paths", {}).items():
                if not item:
                    continue

                dist_rj, path_rj = item
                region = G.nodes[req_r].get(OffPA.REGION.value)
                thd = Thd_Latency.get(region, INF)

                if path_rj and dist_rj <= thd:
                    candidate[j][req_r] = float(dist_rj)
                    candidate_paths[j][req_r] = list(path_rj)

        # Stage II: total request size served by each j
        for j in valid_caches:
            size_j[j] = sum(
                float(G.nodes[r].get("req_size", 0.0))
                for r in candidate[j].keys()
            )

        # Stage III: choose j with maximum utility
        j_bar = None
        j_bar_val = -INF
        best_new_DG = None
        best_selected_caches = None
        best_distribution_paths = None
        best_assigned_req_paths = None

        current_CT = CT(selected_caches, distribution_paths, assigned_req_paths, alpha=alpha)

        for j in valid_caches:
            if not candidate[j]:
                continue

            tmp_DG = DG.copy()
            tmp_selected_caches = set(selected_caches)
            tmp_distribution_paths = dict(distribution_paths)
            tmp_assigned_req_paths = dict(assigned_req_paths)

            # This cache becomes a selected cache server
            tmp_selected_caches.add(j)

            # Add request->cache paths for all candidate requests
            for req in candidate[j].keys():
                req_path = candidate_paths[j][req]
                tmp_assigned_req_paths[req] = req_path
                tmp_DG = add_path_with_attrs(tmp_DG, req_path)

            # Add source->cache distribution path once if not yet selected before
            if j not in tmp_distribution_paths:
                try:
                    _, src_to_j_path, _ = pick_best_src_to_cache_path(j, srcs)
                    tmp_distribution_paths[j] = src_to_j_path
                    tmp_DG = add_path_with_attrs(tmp_DG, src_to_j_path)
                except ValueError:
                    # if no source path exists, cannot use this cache
                    continue

            new_CT = CT(tmp_selected_caches, tmp_distribution_paths, tmp_assigned_req_paths, alpha=alpha)
            dCT = new_CT - current_CT

            if dCT <= 0:
                utility = -INF
            else:
                utility = size_j[j] / dCT

            if utility > j_bar_val:
                j_bar_val = utility
                j_bar = j
                best_new_DG = tmp_DG
                best_selected_caches = tmp_selected_caches
                best_distribution_paths = tmp_distribution_paths
                best_assigned_req_paths = tmp_assigned_req_paths

        if j_bar is None:
            raise ValueError(
                f"No feasible cache can serve remaining requests: {sorted(RQ_remain)}"
            )

        new_RQ_remain = RQ_remain - set(candidate[j_bar].keys())

        if new_RQ_remain == RQ_remain:
            raise ValueError(
                f"Greedy selection stalled at iteration {cnt}. "
                f"Remaining requests: {sorted(RQ_remain)}"
            )

        DG = best_new_DG
        selected_caches = best_selected_caches
        distribution_paths = best_distribution_paths
        assigned_req_paths = best_assigned_req_paths
        RQ_remain = new_RQ_remain
        cnt += 1

    # Optional: attach debug/accounting info to graph metadata
    DG.graph["selected_caches"] = sorted(selected_caches)
    DG.graph["distribution_paths"] = {k: list(v) for k, v in distribution_paths.items()}
    DG.graph["assigned_req_paths"] = {k: list(v) for k, v in assigned_req_paths.items()}
    DG.graph["CT_dist"] = CT_dist_from_paths(distribution_paths)
    DG.graph["CT_access"] = CT_access_from_paths(assigned_req_paths)
    DG.graph["CT_storage"] = CT_storage(selected_caches, alpha)
    DG.graph["CT_total"] = CT(selected_caches, distribution_paths, assigned_req_paths, alpha=alpha)

    return DG
# offpa
# 表格橫軸種軸
# 不用比較baseline之間
# 6-1要有參考