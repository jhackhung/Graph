import networkx as nx
from typing import Set
import Debug
import Algorithm

INF = float("inf")
def _attach_parent_edge(
    r: str,
    v: str,
    child_tree: nx.DiGraph,
    G: nx.DiGraph,
):
    """
    Make a child subtree rooted at v become a valid subtree rooted at r
    by adding r, v, and edge r -> v.
    """
    T = child_tree.copy()

    if r not in T:
        T.add_node(r, **G.nodes[r])
    else:
        T.nodes[r].update(G.nodes[r])

    if v not in T:
        T.add_node(v, **G.nodes[v])
    else:
        T.nodes[v].update(G.nodes[v])

    T.add_edge(r, v, **G[r][v])
    return T


def _served_dests(T: nx.DiGraph, terminals: Set[str], G: nx.DiGraph):
    return {
        n for n in T.nodes
        if n in terminals and G.nodes[n].get("type") == "dest"
    }
    
def PDTA_Density(G: nx.DiGraph, Beta: float, terminals: Set[str], interval_len: int = 1):
    if G.number_of_edges() == 0:
        return INF
    local_terms = set(terminals)
    D_T = 0
    total = 0
    for u, v, d in G.edges(data=True):
        if v in local_terms:
            local_terms.remove(v)
            D_T += 1
        total += d["cost_traffic"]

    if D_T == 0:
        return INF
    else:
        return (total + Beta * D_T / interval_len) / D_T

def PDTA_Origin(level: int, r: str, m: int, terminals: Set[str], G: nx.DiGraph) -> nx.DiGraph:
    T_return = nx.DiGraph()
    T_terminals = set(terminals)

    if m <= 0 or not T_terminals or level < 1:
        return T_return

    if level == 1:
        edges_sorted = sorted(
            [(u, v, d) for u, v, d in G.edges(data=True) if (u == r and v in T_terminals)],
            key=lambda x: x[2]["cost_traffic"],
            reverse=False
        )
        
        T_return.add_node(r, **G.nodes[r])
        for u, v, d in edges_sorted:
            T_return.add_node(v, **G.nodes[v])
            T_return.add_edge(u, v, **d)
        return T_return
        
    D_current = set()
    while len(D_current) < m and T_terminals:
        T_min = nx.DiGraph()
        d_T_min = INF
        tmp: nx.DiGraph
        D_min = set()

        for v in G.successors(r):
            for n in range(1, len(T_terminals) + 1):
                if v in T_terminals:
                    T_terminals.remove(v)
                tmp = PDTA_Origin(level-1, v, n, T_terminals, G)
                tmp.add_node(r, **G.nodes[r])
                tmp.add_node(v, **G.nodes[v])
                tmp.add_edge(r, v, **G[r][v])

                d_tmp = PDTA_Density(tmp, 1, T_terminals) 
                if d_tmp < d_T_min:
                    T_min = tmp
                    d_T_min = d_tmp
            if G.nodes[v]["type"] == "dest":
                T_terminals.add(v)

        D_min = {n for n in T_min.nodes if G.nodes[n].get("type") == "dest"}
        if not D_min:
            return T_return
        D_current |= D_min
        T_terminals -= D_min
        T_return = Algorithm.union_graphs(T_return, T_min)

    return T_return

def PDTA(level: int, r: str, m: int, terminals: Set[str], G: nx.DiGraph, interval_len: int = 1):
    T_return = nx.DiGraph()
    T_terminals = set(terminals)
    d_T_min_return = INF
    T_record = {}

    if r not in G:
        return T_return, d_T_min_return, T_record

    dist = dict(nx.single_source_shortest_path(G, r, cutoff=level))
    reachable = set(dist.keys())
    T_terminals = T_terminals & reachable

    if m <= 0 or not T_terminals or level < 1:
        return T_return, d_T_min_return, T_record

    # =====================================================
    # Base case: one-hop tree rooted at r
    # =====================================================
    if level == 1:
        edges_sorted = sorted(
            [
                (u, v, d)
                for u, v, d in G.edges(data=True)
                if u == r and v in T_terminals
            ],
            key=lambda x: x[2]["cost_traffic"],
            reverse=False
        )

        T_return.add_node(r, **G.nodes[r])

        served_count = 0
        for u, v, d in edges_sorted:
            if served_count >= m:
                break

            T_return.add_node(v, **G.nodes[v])
            T_return.add_edge(u, v, **d)
            served_count += 1

        D_min = _served_dests(T_return, T_terminals, G)

        if not D_min:
            return nx.DiGraph(), INF, {}

        d_T_min_return = PDTA_Density(T_return, 1, T_terminals, interval_len)
        T_record[(d_T_min_return, len(D_min))] = T_return.copy()

        # Invariant: any non-empty PDTA result must contain root r.
        assert r in T_return, f"[PDTA] root {r} missing in level=1 result"

        return T_return, d_T_min_return, T_record

    # =====================================================
    # Recursive case
    # =====================================================
    D_current = set()

    while len(D_current) < m and T_terminals:
        T_min = nx.DiGraph()
        d_T_min = INF

        # Try each outgoing child v of current root r
        for v in sorted(G.successors(r), key=str):
            # -------------------------------------------------
            # Candidate 1:
            # recursive child tree, then attach r -> v
            # -------------------------------------------------
            child_tree, density, records = PDTA(
                level - 1,
                v,
                min(len(T_terminals), m),
                T_terminals,
                G,
                interval_len
            )

            candidate = _attach_parent_edge(r, v, child_tree, G)
            d_tmp = PDTA_Density(candidate, 1, T_terminals, interval_len)

            D_tmp = _served_dests(candidate, T_terminals, G)

            if D_tmp and d_tmp < d_T_min:
                T_min = candidate
                d_T_min = d_tmp

            # -------------------------------------------------
            # Candidate 2:
            # combinations of child records.
            #
            # Important:
            # records are rooted at child v, not current root r.
            # Therefore every combined record must be attached
            # back to r using edge r -> v.
            # -------------------------------------------------
            sorted_records = sorted(records.items(), key=lambda x: x[0])
            total_dests = sum(key[1] for key, _ in sorted_records)

            combo = nx.DiGraph()
            cnt = 0
            ptr = 0

            for n in range(1, min(len(T_terminals), m) + 1):
                if n > total_dests:
                    break
                if cnt >= n:
                    continue

                while cnt < n and ptr < len(sorted_records):
                    key, G_sub = sorted_records[ptr]
                    combo = Algorithm.union_graphs(combo, G_sub)
                    cnt += key[1]
                    ptr += 1

                if combo.number_of_edges() == 0:
                    continue

                candidate = _attach_parent_edge(r, v, combo, G)
                d_tmp = PDTA_Density(candidate, 1, T_terminals, interval_len)

                D_tmp = _served_dests(candidate, T_terminals, G)

                if D_tmp and d_tmp < d_T_min:
                    T_min = candidate
                    d_T_min = d_tmp

        D_min = _served_dests(T_min, T_terminals, G)

        if not D_min:
            break

        # Invariant: every selected tree must contain current root.
        assert r in T_min, (
            f"[PDTA] root {r} missing in selected T_min. "
            f"level={level}, m={m}, served={len(D_min)}"
        )

        D_current |= D_min
        T_terminals -= D_min
        T_return = Algorithm.union_graphs(T_return, T_min)
        d_T_min_return = d_T_min

        T_record[(d_T_min, len(D_min))] = T_min.copy()

    if T_return.number_of_edges() == 0:
        return nx.DiGraph(), INF, {}

    # Final invariant.
    assert r in T_return, (
        f"[PDTA] root {r} missing in final T_return. "
        f"level={level}, m={m}"
    )

    return T_return, d_T_min_return, T_record