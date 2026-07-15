from enum import Enum
import math
import os
import sys
import time
import networkx as nx
import heapq
import psutil
import Algorithm
import PDTA
from collections import OrderedDict
class LRUCache(OrderedDict):
    """
    有容量上限的快取，當超過 capacity 時，會自動刪除最久沒使用的項目。
    """
    def __init__(self, capacity: int = 128):
        super().__init__()
        self.capacity = capacity
    def __getitem__(self, key):
        value = super().__getitem__(key)
        self.move_to_end(key)
        return value
    def __setitem__(self, key, value):
        if key in self:
            self.move_to_end(key)
        super().__setitem__(key, value)
        if len(self) > self.capacity:
            self.popitem(last=False)
INF = float("inf")
class TVM(Enum):
    WEIGHT = "cost_traffic"
    USER = "dest"
def TIG_CTIG(G_sequence: list[nx.DiGraph], srcs: list[str], caches: list[str], alpha: float = 1.0):
    T = len(G_sequence)
    E_sets = [set(G.edges()) for G in G_sequence]
    TIG_Interval: dict[tuple[int, int, int], nx.DiGraph] = {}
    CTIG_Interval: dict[tuple[int, int, int], nx.DiGraph] = {}
    TIG_Edges_Map: dict[tuple[int, int, int], dict[str, list[str]]] = {}
    CTIG_Edges_Map: dict[tuple[int, int, int], dict[str, list[str]]] = {}
    for idx, si in enumerate(srcs):
        dists: dict = {}
        parents: dict = {}
        for t, G in enumerate(G_sequence):
            dist, paths = Algorithm.dijkstra_min_edges(G, source=si, weight=TVM.WEIGHT.value)
            dists[t] = {v: cost for v, (cost, hops) in dist.items()}
            parent = {}
            for v, path in paths.items():
                if len(path) >= 2:
                    parent[v] = path[-2]
                else:
                    parent[v] = None
            parents[t] = parent
        for i in range(T):
            current_edges = set(E_sets[i])
            sum_cost: dict[tuple[str, str], float] = {
                e: 0 for e in current_edges
            }
            base_attrs: dict[tuple[str, str], dict] = {
                e: {k: v for k, v in G_sequence[i][e[0]][e[1]].items() if k != TVM.WEIGHT.value}
                for e in current_edges
            }
            for j in range(i, T):        
                current_edges = current_edges & E_sets[j]
                sum_cost = {e: sum_cost[e] for e in current_edges}
                base_attrs = {e: base_attrs[e] for e in current_edges}
                for (u, v) in sorted(current_edges, key=lambda e: (str(e[0]), str(e[1]))):
                    if v in caches and i != j:
                        continue
                    sum_cost[(u, v)] += float(G_sequence[j][u][v][TVM.WEIGHT.value]) * G_sequence[j].nodes[si]["data_size"]
                G_j = G_sequence[j]
                TIG_i_j = nx.DiGraph()
                TIG_i_j.add_nodes_from((n, dict(attrs)) for n, attrs in G_j.nodes(data=True))
                for (u, v) in sorted(current_edges, key=lambda e: (str(e[0]), str(e[1]))):
                    attrs = dict(base_attrs[(u, v)])
                    attrs["BC"] = sum_cost[(u, v)] / (j - i + 1)
                    if v in caches:
                        attrs["CC"] = Algorithm.cost_cache(
                            G_sequence[j].nodes[v],
                            G_sequence[j].nodes[si]["data_size"],
                            alpha=alpha
                        )
                    else:
                        attrs["CC"] = 0
                    attrs[TVM.WEIGHT.value] = attrs["BC"] + attrs["CC"]
                    TIG_i_j.add_edge(u, v, **attrs)
                TIG_Interval[(idx, i, j)] = TIG_i_j
                K = nx.DiGraph()
                K.add_nodes_from((n, dict(attrs)) for n, attrs in TIG_i_j.nodes(data=True))
                for u in sorted(K.nodes(), key=str):
                    dist, paths = Algorithm.dijkstra_min_edges(
                        TIG_i_j,
                        source=u,
                        weight=TVM.WEIGHT.value
                    )
                    CTIG_Edges_Map[(u, i, j)] = paths
                    for v, (cost, hops) in sorted(dist.items(), key=lambda kv: str(kv[0])):
                        if u == v:
                            continue
                        path = paths.get(v, None)
                        if not path or len(path) < 2:
                            continue
                        bc_sum = 0.0
                        cc_sum = 0.0
                        for a, b in zip(path[:-1], path[1:]):
                            edge_attr = TIG_i_j[a][b]
                            bc_sum += edge_attr.get("BC", 0.0)
                            cc_sum += edge_attr.get("CC", 0.0)
                        K.add_edge(u, v, **{TVM.WEIGHT.value: float(cost),
                                            "BC": bc_sum,
                                            "CC": cc_sum,
                                            "virtual": True,
                                        }
                            )
                CTIG_Interval[(idx, i, j)] = K
    return TIG_Interval, CTIG_Interval, TIG_Edges_Map, CTIG_Edges_Map
def expand_virtual_edges(T_i_t: dict[tuple[int, int], nx.DiGraph], TIG_Interval: dict[tuple[int, int, int], nx.DiGraph], TIG_Edges_Map: dict[tuple[int, int], dict[str, list[str]]], srcs: list[str], caches: list[str], total_time:int):
    for idx, si in enumerate(srcs):
        for t in range(total_time):
            for v in caches:
                if not T_i_t[(idx, t)].has_edge(si, v):
                    continue
                if not T_i_t[(idx, t)][si][v]["virtual"]:
                    continue
                key = (idx, t)
                if key not in TIG_Edges_Map:
                    continue
                if v not in TIG_Edges_Map[key]:
                    continue
                real_path = TIG_Edges_Map[key][v]
                print(f"Virtual edge ({si}->{v}) 展開路徑: {real_path}")
                T_i_t[(idx, t)].remove_edge(si, v)
                for x, y in zip(real_path, real_path[1:]):
                    if TIG_Interval[(idx, t, t)].has_edge(x, y):
                        edge_attr = TIG_Interval[(idx, t, t)][x][y]
                        T_i_t[(idx, t)].add_edge(x, y, **edge_attr)
                    else:
                        raise KeyError(
                            f"❌ Edge ({x} -> {y}) not found in TIG_Interval[{idx}, {t}, {t}]"
                        )
def TSMTA(
    TIG: dict[tuple[int, int, int], nx.DiGraph],
    CTIG: dict[tuple[int, int, int], nx.DiGraph],
    TIG_Edges_Map: dict[tuple[int, int], dict[str, list[str]]],
    CTIG_Edges_Map: dict[tuple[int, int, int], dict[str, list[str]]],
    srcs: list[str],
    caches: list[str],
    dests: dict[tuple[int, int, int], set[str]],
    total_time: int,
    node_attr_map: dict = None,
    pdta_level: int = 2,
):
    p = psutil.Process(os.getpid())
    def mem_mb():
        return p.memory_info().rss / 1024 / 1024
    T_i_t: dict[tuple[int, int], nx.DiGraph] = {}
    PDTA_cache = LRUCache(capacity=4096)
    Choosing_cache = LRUCache(capacity=4096)
    pdta_memo: dict = {}
    pdta_calls = 0
    cache_hits = 0
    time_pdta = 0.0
    time_cache = 0.0
    TIG_Interval = {k: v.copy() for k, v in TIG.items()}
    CTIG_Interval = {k: v.copy() for k, v in CTIG.items()}
    while dests:
        T_best = nx.DiGraph()
        i_best = 1
        t1_best = 1
        t2_best = 1
        T_Density_min = INF
        for idx, si in enumerate(srcs):
            test_time = time.time()
            for i in range(total_time):
                local_dests = dests.get((idx, i, i), set())
                cnt = 0
                for j in range(i, total_time, 5):
                    local_dests = (local_dests & dests.get((idx, j, j), set()))
                    dcount = len(local_dests)
                    G = CTIG_Interval[(idx, i, j)]
                    sig = Algorithm.graph_signature(G)
                    cache_key = (pdta_level, sig, si, dcount)
                    t0 = time.time()
                    if cache_key in PDTA_cache:
                        cache_hits += 1
                        t0 = time.time()
                        tmp_k, tmp_min, records = PDTA_cache[cache_key]
                        time_cache += time.time() - t0
                    else:
                        pdta_calls += 1
                        tmp_k, tmp_min, records = PDTA.PDTA(pdta_level, si, dcount, local_dests, G, interval_len=j - i + 1, _memo=pdta_memo)
                        time_pdta += time.time() - t0
                        PDTA_cache[cache_key] = (tmp_k, tmp_min, records)
                    if tmp_min < T_Density_min:
                        if tmp_k.number_of_edges() > 0 and si not in tmp_k:
                            raise AssertionError(
                                f"[TSMTA] PDTA returned invalid tree without source. "
                                f"PDTA_k={pdta_level}, src={si}, interval=({i},{j}), "
                                f"nodes={list(tmp_k.nodes())[:20]}"
                            )

                        T_Density_min, T_best, i_best, t1_best, t2_best = (
                            tmp_min,
                            tmp_k.copy(),
                            idx,
                            i,
                            j,
                        )
                    else:
                        cnt+=1
                    if cnt >= 1:
                        break
                    sorted_records = sorted(records.items(), key=lambda x: x[0])
                    total_dests = sum(key[1] for key, _ in sorted_records)
                    tmp_k = nx.DiGraph()
                    tmp_k_cnt, ptr = 0, 0
                    for k in range(1, len(local_dests)):
                        if k > total_dests:
                            break
                        cache_key = (pdta_level, sig, si, k)
                        t0 = time.time()
                        if cache_key in Choosing_cache:
                            cache_hits += 1
                            tmp_k, tmp_min = Choosing_cache[cache_key]
                            time_cache += time.time() - t0
                        else:
                            if tmp_k_cnt >= k:
                                continue
                            while tmp_k_cnt < k:
                                key, G_sub = sorted_records[ptr]
                                tmp_k = Algorithm.union_graphs(tmp_k, G_sub)
                                tmp_k_cnt += key[1]
                                ptr += 1
                            tmp_min = PDTA.PDTA_Density(tmp_k, 1, local_dests, interval_len=j - i + 1)
                            Choosing_cache[cache_key] = (tmp_k, tmp_min)
                            if tmp_min < T_Density_min:
                                if tmp_k.number_of_edges() > 0 and si not in tmp_k:
                                    raise AssertionError(
                                        f"[TSMTA] Choosing_cache produced invalid tree without source. "
                                        f"PDTA_k={pdta_level}, src={si}, interval=({i},{j}), "
                                        f"k={k}, nodes={list(tmp_k.nodes())[:20]}"
                                    )

                                T_Density_min, T_best, i_best, t1_best, t2_best = (
                                    tmp_min,
                                    tmp_k.copy(),
                                    idx,
                                    i,
                                    j,
                                )
        remove = [n for n, d in T_best.nodes(data=True) if d["type"] == TVM.USER.value]
        if len(remove) == 0:
            break 
        edges_to_process = list(T_best.edges())
        for u, v in edges_to_process:
            paths_dict = CTIG_Edges_Map.get((u, t1_best, t2_best), [])
            if v not in paths_dict:
                continue
            real_path = paths_dict[v]
            if T_best.has_edge(u, v):
                T_best.remove_edge(u, v)
            for x, y in zip(real_path, real_path[1:]):
                if x not in T_best:
                    T_best.add_node(x, **node_attr_map.get(x, {}))
                if y not in T_best:
                    T_best.add_node(y, **node_attr_map.get(y, {}))
                if TIG_Interval[(i_best, t1_best, t2_best)].has_edge(x, y):
                    edge_attr = TIG_Interval[(i_best, t1_best, t2_best)][x][y]
                    T_best.add_edge(x, y, **edge_attr)
                else:
                    raise KeyError(
                        f"❌ Edge ({x} -> {y}) not found in TIG_Interval[{i_best}, {t1_best}, {t2_best}]"
                    )
        for i in range(t1_best, t2_best + 1):
            T_i_t[(i_best, i)] = Algorithm.union_graphs(T_i_t.get((i_best, i), None), T_best)
            for j in range(i, t2_best + 1):
                key = (i_best, i, j)
                dests[key] = dests.get(key, set()) - set(remove)
                if not dests[(i_best, i, j)]:
                    del dests[(i_best, i, j)]
                for u, v in T_best.edges():
                    if TIG_Interval[(i_best, i, j)].has_edge(u, v):
                        TIG_Interval[(i_best, i, j)][u][v][TVM.WEIGHT.value] = 0.0
                    if CTIG_Interval[(i_best, i, j)].has_edge(u, v):
                        CTIG_Interval[(i_best, i, j)][u][v][TVM.WEIGHT.value] = 0.0
    print(f"[{i}] RSS = {mem_mb():.2f} MB")
    print(
        f"[PDTA memo] hits={PDTA.memo_stats['hits']}, "
        f"misses={PDTA.memo_stats['misses']}, "
        f"memo_size={len(pdta_memo)}, "
        f"outer_cache_hits={cache_hits}, outer_pdta_calls={pdta_calls}"
    )
    time.sleep(0.5)
    return T_i_t

def BC_multicast(T_i_t: dict[tuple[int, int], nx.DiGraph],
                 src_nodes: list[str],
                 total_time: int) -> float:
    """
    Bandwidth-like cost for multicast-tree baselines.
    For each source/time graph, every edge in the tree is charged once
    with the source content size.
    """
    total_cost = 0.0
    for idx, si in enumerate(src_nodes):
        for t in range(total_time):
            G = T_i_t.get((idx, t))
            if G is None or si not in G.nodes:
                continue

            size = float(G.nodes[si].get("data_size", 0.0))

            for _, _, attrs in G.edges(data=True):
                total_cost += float(attrs.get("cost_traffic", 0.0)) * size

    return total_cost

def BC_multicast_cache_aware(T_i_t, src_nodes, caches, total_time, cache_hit_factor=0.3):
    total_cost = 0.0

    for idx, si in enumerate(src_nodes):
        for t in range(total_time):
            G = T_i_t.get((idx, t))
            if G is None or si not in G.nodes:
                continue

            size = float(G.nodes[si].get("data_size", 1.0))

            stack = [(si, False)]
            visited = set()

            while stack:
                u, passed_cache = stack.pop()
                if (u, passed_cache) in visited:
                    continue
                visited.add((u, passed_cache))

                for v in G.successors(u):
                    edge_cost = float(G[u][v].get("cost_traffic", 0.0)) * size

                    next_passed_cache = passed_cache or (v in caches)

                    if passed_cache:
                        edge_cost *= cache_hit_factor

                    total_cost += edge_cost
                    stack.append((v, next_passed_cache))

    return total_cost


def CC_multicast(T_i_t: dict[tuple[int, int], nx.DiGraph],
                 src_nodes: list[str],
                 caches: list[str],
                 total_time: int,
                 alpha: float = 1.0) -> float:
    """
    Cache cost for multicast-tree baselines.
    Only use this if your baseline definition really wants cache cost.
    """
    total_cost = 0.0
    for idx, si in enumerate(src_nodes):
        for t in range(total_time):
            G = T_i_t.get((idx, t))
            if G is None or si not in G.nodes:
                continue

            size = float(G.nodes[si].get("data_size", 0.0))

            for c in caches:
                if c not in G.nodes:
                    continue
                node_attr = G.nodes[c]
                total_cost += Algorithm.cost_cache(node_attr, size, alpha)

    return total_cost


def RC_multicast(T_i_t, src_nodes, total_time, beta=1.0):
    """
    Reconfiguration / handover-like cost for multicast-tree baselines.

    Normalized version:
    use the average number of changed edges between consecutive time slices,
    instead of summing all transitions directly.
    """
    total_cost = 0.0
    transition_count = 0

    for idx, _ in enumerate(src_nodes):
        for t in range(total_time - 1):
            G1 = T_i_t.get((idx, t))
            G2 = T_i_t.get((idx, t + 1))

            if G1 is None or G2 is None:
                continue

            edges1 = set(G1.edges())
            edges2 = set(G2.edges())

            total_cost += len(edges1.symmetric_difference(edges2))
            transition_count += 1

    avg_rc = total_cost / max(transition_count, 1)
    return avg_rc * beta


def evaluate_multicast_algorithm(name: str,
                                 T_i_t: dict[tuple[int, int], nx.DiGraph],
                                 src_nodes: list[str],
                                 caches: list[str],
                                 total_time: int,
                                 alpha: float = 1.0,
                                 beta: float = 50.0,
                                 output: bool = True):
    """
    For DMTS / SSSP / TSMTA.
    """
    if name == "TSMTA":
        bc = BC_multicast_cache_aware(
            T_i_t,
            src_nodes,
            caches,
            total_time,
            cache_hit_factor=0.3
        )
        cc = CC_multicast(T_i_t, src_nodes, caches, total_time, alpha)

    elif name in ("DMTS", "SSSP"):
        bc = BC_multicast(T_i_t, src_nodes, total_time)
        cc = 0.0

    else:
        bc = BC_multicast(T_i_t, src_nodes, total_time)
        cc = CC_multicast(T_i_t, src_nodes, caches, total_time, alpha)

    rc = RC_multicast(T_i_t, src_nodes, total_time, beta)
    total = bc + cc + rc
    
    if output:
        print(f"[{name}] BC={bc:.2f}, CC={cc:.2f}, RC={rc:.2f}, Total={total:.2f}")

    return bc, cc, rc, total


# =========================================================
# OffPA / STARFRONT
# =========================================================

def RC_offpa_from_graph_diff(T_i_t: dict[tuple[int, int], nx.DiGraph],
                             beta: float = 10.0) -> float:
    """
    Surrogate RC for OffPA:
    use edge symmetric difference between adjacent time slots.

    Note:
    This is NOT OffPA's original cost definition.
    It is a post-hoc reconfiguration metric for presentation consistency.
    """
    if not isinstance(T_i_t, dict):
        raise TypeError("For OffPA, result must be T_i_t: dict[(idx,t)] -> nx.DiGraph.")

    total_cost = 0.0

    # 先把同一個 src_idx 的時間序列整理出來
    src_groups: dict[int, list[tuple[int, nx.DiGraph]]] = {}
    for (src_idx, t), DG in T_i_t.items():
        src_groups.setdefault(src_idx, []).append((t, DG))

    for src_idx, seq in src_groups.items():
        seq.sort(key=lambda x: x[0])  # sort by time

        for i in range(len(seq) - 1):
            _, G1 = seq[i]
            _, G2 = seq[i + 1]

            edges1 = set(G1.edges())
            edges2 = set(G2.edges())

            total_cost += len(edges1.symmetric_difference(edges2))

    return total_cost * beta


def evaluate_offpa(T_i_t: dict[tuple[int, int], nx.DiGraph],
                   beta: float = 10.0,
                   alpha: float = 1.0,
                   output: bool = True):
    """
    Hard-split OffPA into BC / RC / CC for presentation consistency.

    Mapping:
        BC = CT_dist + CT_access
        CC = CT_storage
        RC = graph-difference-based surrogate reconfiguration cost
    """
    if not isinstance(T_i_t, dict):
        raise TypeError("For OffPA, result must be T_i_t: dict[(idx,t)] -> nx.DiGraph.")

    ct_dist = 0.0
    ct_access = 0.0
    ct_storage = 0.0

    for key, DG in T_i_t.items():
        if not isinstance(DG, nx.DiGraph):
            raise TypeError(f"OffPA T_i_t[{key}] is not an nx.DiGraph.")

        ct_dist += float(DG.graph.get("CT_dist", 0.0))
        ct_access += float(DG.graph.get("CT_access", 0.0))
        ct_storage += float(DG.graph.get("CT_storage", 0.0))

    bc = ct_dist + ct_access
    cc = ct_storage
    rc = RC_offpa_from_graph_diff(T_i_t, beta=beta)
    total = bc + cc + rc

    if output:
        print(f"[OffPA] BC={bc:.2f}, CC={cc:.2f}, RC={rc:.2f}, Total={total:.2f}")
        print(
            f"        (CT_dist={ct_dist:.2f}, "
            f"CT_access={ct_access:.2f}, "
            f"CT_storage={ct_storage:.2f}, "
            f"RC_surrogate={rc:.2f})"
        )

    return bc, cc, rc, total


def evaluate_algorithm(name: str,
                       result,
                       src_nodes: list[str],
                       caches: list[str],
                       total_time: int,
                       alpha: float = 1.0,
                       beta: float = 100.0,
                       output: bool = True):

    if name == "OffPA":
        return evaluate_offpa(result, beta=beta, alpha=alpha, output=output)

    if not isinstance(result, dict):
        raise TypeError(f"For {name}, result must be T_i_t: dict[(idx,t)] -> nx.DiGraph.")

    return evaluate_multicast_algorithm(
        name=name,
        T_i_t=result,
        src_nodes=src_nodes,
        caches=caches,
        total_time=total_time,
        alpha=alpha,
        beta=beta,
        output=output
    )

def Optimal(
    T_i_t: dict[tuple[int, int], nx.DiGraph],
    srcs: list[str],
    caches: list[str],
    TIG_Interval: dict[tuple[int, int, int], nx.DiGraph],
    total_time: int,
    candidates_amount: int,
    node_attr_map=None,
    beta: float = 100.0,
    alpha: float = 1.0
):
    print("Start Optimal")

    intervals: dict[int, list[tuple[int, int]]] = {}
    G: nx.DiGraph

    for idx, si in enumerate(srcs):
        start = 0
        G = T_i_t[(idx, start)]
        intervals[idx] = []

        for j in range(total_time):
            if not Algorithm.are_graphs_equal(G, T_i_t[(idx, j)]):
                intervals[idx].append((start, j - 1))
                start = j
                G = T_i_t[(idx, start)]

        intervals[idx].append((start, total_time - 1))

    for idx, si in enumerate(srcs):
        RCL: list = []
        iv_list = intervals[idx]

        for j, (t1, t2) in enumerate(iv_list):
            interval_graph = T_i_t[(idx, t1)]
            base_pack, base_path = Algorithm.dijkstra_min_edges(
                interval_graph,
                si,
                weight=TVM.WEIGHT.value,
            )
            base_dists = {v: cost for v, (cost, _) in base_pack.items()}
            dest_nodes = {
                n for n, d in interval_graph.nodes(data=True)
                if d.get("type") == "dest"
            }

            TIG_list = []
            G_cur = TIG_Interval[(idx, t1, t2)].copy()
            TIG_list.append(G_cur)

            if j > 0:
                t1_prev = iv_list[j - 1][0]
                G_prev = TIG_Interval.get((idx, t1_prev, t2))
                if G_prev is not None:
                    TIG_list.append(G_prev.copy())

            if j + 1 < len(iv_list):
                t2_next = iv_list[j + 1][1]
                G_next = TIG_Interval.get((idx, t1, t2_next))
                if G_next is not None:
                    TIG_list.append(G_next.copy())

            for TIG_t1_t2 in TIG_list:
                for d in dest_nodes:
                    pd = base_path.get(d)
                    if pd and len(pd) >= 2:
                        u, v = pd[-2], pd[-1]
                        if TIG_t1_t2.has_edge(u, v):
                            TIG_t1_t2.remove_edge(u, v)

                new_pack, new_path = Algorithm.dijkstra_min_edges(
                    TIG_t1_t2,
                    si,
                    weight=TVM.WEIGHT.value,
                )
                new_dists = {v: cost for v, (cost, _) in new_pack.items()}

                for d in dest_nodes:
                    if d in base_dists and d in new_dists:
                        delta = new_dists[d] - base_dists[d]
                        RCL.append(
                            (
                                delta,
                                base_path.get(d),
                                new_path.get(d),
                                (t1, t2),
                            )
                        )

        RCL_sorted = sorted(
            RCL,
            key=lambda x: (
                round(x[0], 12),
                tuple(map(str, x[1] or ())),
                tuple(map(str, x[2] or ())),
                x[3],
            ),
        )

        for i in range(min(candidates_amount, len(RCL_sorted))):
            dist, path, new_path, (t1, t2) = RCL_sorted[i]

            if not path or len(path) < 2:
                continue
            if not new_path or len(new_path) < 2:
                continue

            cache = {}

            # 重要：Optimal 的比較目標也要使用外面傳進來的 beta
            bc, cc, rc, total = evaluate_algorithm(
                "TSMTA",
                T_i_t,
                srcs,
                caches,
                total_time,
                beta=beta,
                alpha=alpha,
                output=False,
            )

            cache[t1] = T_i_t[(idx, t1)].copy(as_view=False)
            new_T_i_t = T_i_t[(idx, t1)].copy()

            if new_T_i_t.has_edge(path[-2], path[-1]):
                new_T_i_t.remove_edge(path[-2], path[-1])

            add_edges = list(zip(new_path[:-1], new_path[1:]))

            for u, v in add_edges:
                if TIG_Interval[(idx, t1, t1)].has_edge(u, v):
                    edge_attr = TIG_Interval[(idx, t1, t1)][u][v]
                    new_T_i_t.add_edge(u, v, **edge_attr)
                else:
                    raise KeyError(
                        f"❌ Edge ({u}->{v}) not found in TIG_Interval[{idx}, {t1}, {t1}]"
                    )

            new_T_i_t = Algorithm.shortest_path_tree(
                new_T_i_t,
                si,
                weight=TVM.WEIGHT.value,
            )

            if node_attr_map is not None:
                for n in list(new_T_i_t.nodes()):
                    if n in node_attr_map:
                        new_T_i_t.nodes[n].update(node_attr_map[n])

            min_val = total
            l_ch, r_ch = -1, 0

            for t_l in range(t1, t2 + 1):
                for t_r in range(t_l, t2 + 1):
                    T_i_t[(idx, t_r)] = new_T_i_t.copy()

                    # 重要：這裡也要使用同一個 beta
                    bc, cc, rc, val = evaluate_algorithm(
                        "TSMTA",
                        T_i_t,
                        srcs,
                        caches,
                        total_time,
                        beta=beta,
                        alpha=alpha,
                        output=False,
                    )

                    if val < min_val:
                        min_val = val
                        l_ch = t_l
                        r_ch = t_r

                for t_r in range(t_l, t2 + 1):
                    T_i_t[(idx, t_r)] = cache[t1].copy(as_view=False)

            if min_val < total:
                for t in range(l_ch, r_ch + 1):
                    T_i_t[(idx, t)] = new_T_i_t.copy(as_view=False)
