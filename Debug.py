from matplotlib import pyplot as plt
import networkx as nx

def print_graph(G: nx.DiGraph):
    print("Nodes:")
    for n, attr in G.nodes(data=True):
        print(f"  {n}:")
        for k, v in attr.items():
            print(f"    {k} = {v}")
    # print("Edges:")
    # for u, v, attr in G.edges(data=True):
    #     print(f"  {u} -> {v}:")
    #     for k, v in attr.items():
    #         print(f"    {k} = {v}")

def print_graphs(graphs: nx.DiGraph):
    if isinstance(graphs, nx.DiGraph):
        graphs = [graphs]
    elif isinstance(graphs, dict):
        graphs = graphs.items()

    for t, G in graphs:
        print(f"\n=== Time t = {t} ===")
        print_graph(G)

def are_graphs_equal(seq1: list[nx.DiGraph], seq2: list[nx.DiGraph]) -> bool:
    if len(seq1) != len(seq2):
        print(f"Length mismatch: {len(seq1)} vs {len(seq2)}")
        return False

    all_match = True
    for t, (G1, G2) in enumerate(zip(seq1, seq2)):
        # 比對節點
        if set(G1.nodes) != set(G2.nodes):
            print(f"Node set mismatch at t={t}")
            all_match = False
        else:
            for n in G1.nodes:
                if G1.nodes[n] != G2.nodes[n]:
                    print(f"Node attr mismatch at t={t}, node={n}")
                    print("  G1:", G1.nodes[n])
                    print("  G2:", G2.nodes[n])
                    all_match = False

        # 比對邊
        if set(G1.edges) != set(G2.edges):
            print(f"Edge set mismatch at t={t}")
            all_match = False
        else:
            for e in G1.edges:
                if G1.edges[e] != G2.edges[e]:
                    print(f"Edge attr mismatch at t={t}, edge={e}")
                    print("  G1:", G1.edges[e])
                    print("  G2:", G2.edges[e])
                    all_match = False

    return all_match

def draw_graph(G: nx.DiGraph, src: str, time: int, attr="cost_traffic", elev=25, azim=45):
    fig = plt.figure(figsize=(8, 6))
    ax = fig.add_subplot(111, projection="3d")
    ax.set_title(f"Graph (src={src}, t={time})")
    ax.set_box_aspect([1, 1, 1])  
    ax.view_init(elev=elev, azim=azim)  

    # 用 spring_layout 產生 3D 座標
    pos = nx.spring_layout(G, dim=3, seed=42, k=20)

    # 畫節點 (src 紅色)
    xs, ys, zs, colors = [], [], [], []
    for n in G.nodes():
        xs.append(pos[n][0])
        ys.append(pos[n][1])
        zs.append(pos[n][2])
        colors.append("red" if n == src else "skyblue")

    ax.scatter(xs, ys, zs, c=colors, s=120, edgecolors="k", alpha=0.9)

    # 畫節點標籤
    for n in G.nodes():
        ax.text(pos[n][0], pos[n][1], pos[n][2], f"{n}, {G.nodes[n]["type"]}", fontsize=8)

    # 畫邊 + 箭頭 + 屬性標籤
    for u, v in G.edges():
        x0, y0, z0 = pos[u]
        x1, y1, z1 = pos[v]

        # 畫邊
        ax.plot([x0, x1], [y0, y1], [z0, z1], color="gray", alpha=0.3, linewidth=0.6)

        # 畫箭頭
        ax.quiver(x0, y0, z0,
                  x1 - x0, y1 - y0, z1 - z0,
                  arrow_length_ratio=0.1,
                  color="gray", alpha=0.6, linewidth=0.6)

        # 邊的中點位置
        xm, ym, zm = (x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2

        # 取邊的屬性值
        cost = G[u][v].get(attr, None)
        if cost is not None:
            ax.text(xm, ym, zm, str(cost), color="blue", fontsize=7)

    plt.show()

def draw_graph_2d(G: nx.DiGraph, src: str, time: int, attr="cost_traffic"):
    plt.figure(figsize=(8, 6))
    plt.title(f"Graph (src={src}, t={time})")

    # 用 spring_layout 產生 2D 座標
    pos = nx.spring_layout(G, dim=2, seed=42, k=1.5)  # k 控制節點間距

    # 畫節點 (src 紅色)
    node_colors = ["red" if n == src else "skyblue" for n in G.nodes()]
    nx.draw_networkx_nodes(G, pos, node_color=node_colors, node_size=600, edgecolors="k", alpha=0.9)

    # 畫節點標籤
    labels = {n: f"{n}, {G.nodes[n].get('type', '')}" for n in G.nodes()}
    nx.draw_networkx_labels(G, pos, labels=labels, font_size=8)

    # 畫邊
    nx.draw_networkx_edges(G, pos, edge_color="gray", arrows=True, alpha=0.5)

    # 邊的屬性標籤
    edge_labels = {}
    for u, v in G.edges():
        cost = G[u][v].get(attr, None)
        if cost is not None:
            edge_labels[(u, v)] = str(cost)

    nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, font_size=7, font_color="blue")

    plt.axis("off")
    plt.show()
    
def check_no_conflicting_parent(G: nx.DiGraph, label:str):
    """檢查是否有節點被超過一個 parent 指向，這是環/非樹結構的前兆。"""
    bad = [n for n in G.nodes() if G.in_degree(n) > 1]
    if bad:
        print(f"[STRUCTURE-CHECK] {label}: 發現 in-degree > 1 的節點: {bad[:10]}", flush=True)
    return bad