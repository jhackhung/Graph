import os
import networkx as nx
import numpy as np
import pandas as pd

UPSERT_KEYS = ["graph", "algo", "beta", "alpha", "PDTA_k"]
FAIRNESS_KEYS = ["base_seed", "num_runs"]

def row_matches(df: pd.DataFrame, result_row: dict) -> pd.Series:
    """回傳 boolean mask:df 中與 result_row 的 upsert key 全部相符的 rows。"""
    mask = pd.Series(True, index=df.index)
    for key in UPSERT_KEYS:
        if key not in df.columns:
            # 舊格式檔案缺 key 欄位視為不相符, 使用 append
            return pd.Series(False, index=df.index)
        col = df[key]
        val = result_row[key]
        if isinstance(val, float):
            mask &= np.isclose(col.astype(float), val, rtol=1e-9, atol=1e-12)
        else:
            mask &= (col.astype(str) == str(val))
    return mask

def save_graph_sequence_to_txt(graph_seq, dir_path="output_graphs"):
    """
    儲存一串時間序列的 DiGraph
    - 每個 time slot 存成一段
    - Node / Edge 的所有 attr 都會完整保存
    - 存檔格式是 Python dict，可直接 eval 還原
    """
    os.makedirs(dir_path, exist_ok=True)
    count = sum(1 for f in os.listdir(dir_path)
                if f.startswith("graph_testbed") and f.endswith(".txt"))
    filename = os.path.join(dir_path, f"graph_testbed{count+1}.txt")

    with open(filename, "w") as f:
        for G in graph_seq:
            t = G.graph.get("time", None)
            if t is None:
                raise ValueError("Graph has no graph-level time")

            f.write(f"# Time {t}\n")

            # === Nodes ===
            f.write("# Nodes\n")
            for n, attr in G.nodes(data=True):
                f.write(f"{n} {repr(dict(attr))}\n")

            # === Edges ===
            f.write("# Edges\n")
            for u, v, attr in G.edges(data=True):
                f.write(f"{u} {v} {repr(dict(attr))}\n")

    return filename


def load_graph_sequence_from_txt(path: str, idx: int | None = None) -> list[nx.DiGraph]:
    """
    從 save_graph_sequence_to_txt 存的檔案讀取回 List[DiGraph]
    """
    if idx is None:
        filename = path
    else:
        if not os.path.isdir(path):
            raise NotADirectoryError(f"期望資料夾但拿到：{path}")
        filename = os.path.join(path, f"graph_testbed{idx}.txt")

    if not os.path.isfile(filename):
        raise FileNotFoundError(f"找不到檔案：{filename}")
    
    graphs = []
    G = None
    mode = None

    with open(filename, "r") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue

            if line.startswith("#"):
                if line.startswith("# Time"):
                    # 收前一張圖
                    if G is not None:
                        graphs.append(G)
                    try:
                        t = int(line.split()[-1])
                    except:
                        t = -1
                    G = nx.DiGraph(time=t)
                    mode = None
                elif line == "# Nodes":
                    mode = "node"
                elif line == "# Edges":
                    mode = "edge"
                continue

            if mode == "node":
                name, attr_repr = line.split(" ", 1)
                attrs = eval(attr_repr)  # 直接還原成 dict
                G.add_node(name, **attrs)

            elif mode == "edge":
                u, v, attr_repr = line.split(" ", 2)
                attrs = eval(attr_repr)  # 直接還原成 dict
                G.add_edge(u, v, **attrs)

    # 收最後一張圖
    if G is not None:
        graphs.append(G)

    return graphs

def save_result_to_excel(excel_path: str, result_row: dict):
    """
    Upsert: 若已存在相同 (graph, algo, beta, alpha, PDTA_k) 的 row 就整列覆蓋,
    否則 append。覆蓋時沿用原 experiment_id,只更新內容與 timestamp。
    """
    if not os.path.exists(excel_path):
        result_row["experiment_id"] = 1
        df = pd.DataFrame([result_row])
        df.to_excel(excel_path, index=False)
        print(f"[Excel] created: {excel_path}")
        return
    
    df = pd.read_excel(excel_path)
    mask = row_matches(df, result_row)
    matched = df.index[mask]
    
    if len(matched) > 0:
        # 警告：base_seed/num_runs 不同
        for fk in FAIRNESS_KEYS:
            if fk in df.columns and fk in result_row:
                old_val = df.loc[matched[0], fk]
                if pd.notna(old_val) and float(old_val) != float(result_row[fk]):
                    print(
                        f"[Excel] ⚠ WARNING: {fk} mismatch for "
                        f"({result_row['graph']}, {result_row['algo']}): "
                        f"old={old_val}, new={result_row[fk]} — "
                        f"此演算法用的圖集與其他演算法不同,比較可能不公平!"
                    )

        old_id = df.loc[matched[0], "experiment_id"] if "experiment_id" in df.columns else None
        result_row["experiment_id"] = old_id
        
        if len(matched) > 1:
            print(f"[Excel] ⚠ Found {len(matched)} duplicate rows for the same key, collapsing to 1.")
            df = df.drop(index=matched[1:])
            mask = row_matches(df, result_row)

        for col, val in result_row.items():
            if col not in df.columns:
                df[col] = pd.NA  # 舊檔案補新欄位(如 base_seed/num_runs)
            df.loc[mask, col] = val

        df.to_excel(excel_path, index=False)
        print(f"[Excel] updated row ({result_row['graph']}, {result_row['algo']}) → {excel_path}")
    else:
        if "experiment_id" in df.columns:
            last_id = df["experiment_id"].max()
            last_id = 0 if pd.isna(last_id) else last_id
        else:
            last_id = 0

        result_row["experiment_id"] = last_id + 1

        df = pd.concat([df, pd.DataFrame([result_row])], ignore_index=True)
        df.to_excel(excel_path, index=False)
        print(f"[Excel] appended row (id={last_id+1}) → {excel_path}")
