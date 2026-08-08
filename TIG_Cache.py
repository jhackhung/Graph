"""
TIG/CTIG 磁碟快取。

TIG/CTIG 只由「圖序列」與 alpha 決定，不依賴 beta、pdta_level 或演算法選擇。
圖序列本身由 seed + topology 參數決定(generate_graph_sequence_realistic
是 deterministic 的)。因此只要 (seed, topology 參數, alpha) 相同，重跑不同 beta /
pdta_level / algos 的實驗時就可以直接載入先前算好的 TIG/CTIG，省去最耗時的
dijkstra 重建。

快取檔名帶一段 config hash,所以 sweep n_sats / n_dests 時不會誤用到別的
topology 算出來的圖。
"""

import gzip
import hashlib
import json
import os
import pickle
import time

# 影響 generate_graph_sequence_realistic 輸出的所有參數。
# 若日後 Random_Orbit 新增會影響拓樸的參數,務必同步加進來,
# 否則舊快取會被誤判為可用。
TOPOLOGY_KEYS = [
    "n_sats",
    "n_clouds",
    "n_srcs",
    "n_dests",
    "total_time",
    "num_planes",
    "altitude_km",
    "inclination_deg",
    "f_phasing_param",
    "base_angular_velocity",
    "thr_cloud_to_cloud",
    "region_dist_thr",
]

# 快取格式版本。TIG_CTIG 的計算邏輯若有變動(權重定義、虛擬邊規則等)需更改
CACHE_VERSION = 1


def _topology_signature(cfg: dict) -> tuple[str, dict]:
    """回傳 (短 hash, 實際用到的參數 dict)。"""
    payload = {k: cfg[k] for k in TOPOLOGY_KEYS if k in cfg}
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]
    return digest, payload


def get_cache_path(cfg: dict, seed: int, alpha: float, cache_dir: str = "tig_cache") -> str:
    """(seed, topology, alpha) → 快取檔路徑。"""
    digest, _ = _topology_signature(cfg)
    # alpha 用 repr 以免 1 和 1.0 產生不同檔名
    alpha_tag = f"{float(alpha):g}"
    return os.path.join(
        cache_dir,
        f"tigctig_v{CACHE_VERSION}_{digest}_seed{seed}_alpha{alpha_tag}.pkl.gz",
    )


def load(path: str, cfg: dict, seed: int, alpha: float):
    """
    載入快取。成功回傳 (TIG, CTIG, TIG_Edges_Map, CTIG_Edges_Map);
    檔案不存在、損毀或 metadata 不符時回傳 None(呼叫端就重建)。
    """
    if not os.path.exists(path):
        return None

    start = time.time()
    try:
        with gzip.open(path, "rb") as f:
            blob = pickle.load(f)
    except Exception as e:
        # 半寫入的檔案 / pickle 版本不合 → 當作沒有快取,重建後覆蓋。
        print(f"[TIG Cache] 讀取失敗,將重建: {path} ({type(e).__name__}: {e})")
        return None

    meta = blob.get("meta", {})
    _, expected_topology = _topology_signature(cfg)
    if (
        meta.get("version") != CACHE_VERSION
        or int(meta.get("seed", -1)) != int(seed)
        or float(meta.get("alpha", float("nan"))) != float(alpha)
        or meta.get("topology") != expected_topology
    ):
        # 理論上 hash 已經擋掉了,這裡是 hash 碰撞 / 手動改檔名的最後一道防線。
        print(f"[TIG Cache] metadata 不符,將重建: {path}")
        return None

    size_mb = os.path.getsize(path) / (1024 * 1024)
    print(
        f"[TIG Cache] HIT seed={seed}, alpha={alpha}, "
        f"{size_mb:.1f}MB, load={time.time() - start:.2f}s"
    )
    return (
        blob["TIG"],
        blob["CTIG"],
        blob["TIG_Edges_Map"],
        blob["CTIG_Edges_Map"],
    )


def save(
    path: str,
    cfg: dict,
    seed: int,
    alpha: float,
    TIG: dict,
    CTIG: dict,
    TIG_Edges_Map: dict,
    CTIG_Edges_Map: dict,
    compresslevel: int = 1,
) -> None:
    """
    存快取。先寫 .tmp 再 os.replace,避免中途被中斷時留下半個檔案
    讓下次執行讀到壞資料。

    compresslevel 預設 1:TIG/CTIG 很大,gzip 高壓縮比帶來的時間成本
    通常超過省下的磁碟成本,而我們的目的是省時間。
    """
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    _, topology = _topology_signature(cfg)

    blob = {
        "meta": {
            "version": CACHE_VERSION,
            "seed": int(seed),
            "alpha": float(alpha),
            "topology": topology,
        },
        "TIG": TIG,
        "CTIG": CTIG,
        "TIG_Edges_Map": TIG_Edges_Map,
        "CTIG_Edges_Map": CTIG_Edges_Map,
    }

    start = time.time()
    tmp_path = path + ".tmp"
    try:
        with gzip.open(tmp_path, "wb", compresslevel=compresslevel) as f:
            pickle.dump(blob, f, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp_path, path)
    except Exception as e:
        # 存快取失敗不該讓整個實驗掛掉 —— 演算法結果仍然是對的。
        print(f"[TIG Cache] 寫入失敗(略過快取): {type(e).__name__}: {e}")
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        return

    size_mb = os.path.getsize(path) / (1024 * 1024)
    print(
        f"[TIG Cache] SAVED seed={seed}, alpha={alpha}, "
        f"{size_mb:.1f}MB, dump={time.time() - start:.2f}s → {path}"
    )
