# ILP 精確解：現有 TAMCS/TSMTA 模擬程式重用評估報告

- 檢查日期：2026-10-06；檢查方式：唯讀（repo 內除本檔外未新增／修改任何檔案；試跑在 scratchpad 的程式副本中進行）
- 環境：Windows 11、Python 3.12.3、networkx 3.3、numpy 1.26.4、pandas 2.2.2、openpyxl 3.1.5、matplotlib 3.9.2、psutil 5.9.0、scipy 1.12.0、pytest 7.4.4
- **ortools 未安裝**（`import ortools` 失敗），只記錄、未安裝。
- 標註「不確定」處都附依據；我手上沒有論文原文（repo 內也沒有論文檔），所有「與論文是否一致」的判斷只能以你在任務中給的定義為準。

---

## 1. 一頁摘要

1. **圖與參數產生器可直接重用，TSMTA 可當黑盒呼叫。** `Random_Orbit.generate_graph_sequence_realistic()` 回傳 `list[nx.DiGraph]`（每 slot 一張，邊與權重會隨 slot 變），`main.py` 的 `Build_TIG_CTIG → Run_TSMTA_Select → expand_virtual_edges → Optimal` 流程在 13 節點、T=3 的小圖上 5 秒內跑完（TSMTA 本體約 0.04 秒，另有 0.5 秒是程式內的 `time.sleep`）。
2. **現有成本函式不能當 ILP 的驗證器，必須另寫 evaluate。** 與你給的定義有多處實質不同（見第 3 節 D1–D6、D14）：BC 對 cache 下游的弧乘 0.3；RC 除以 (T−1) 取平均；Optimal 之後 `cache_selected` 旗標遺失導致 CC 少算；BC 讀的是樹上「儲存的權重」而不是該 slot 的真實權重；中繼用的 cache 沒付 CC 卻照樣享受 BC 折扣與 RC 截斷。
3. **有向弧規則（source 只出、destination 只進）完全沒有實作。** 圖中 source 有進入弧、destination 有外出弧；試跑中 TSMTA 的樹真的把 destination 當中繼（t=0：`v1→v2→v10→v3`）。若 ILP 強制單向，必須在跑 TSMTA 之前就把這些弧刪掉，否則兩邊的可行集合不同。
4. **τ(e)、σ(c)、FIFO 都沒有被建模。** 頻寬恆為 1000（`Random_Orbit.py:202-203`），σ 以 `capacity` 欄位存在但演算法從未讀取，程式內沒有任何 FIFO 邏輯；你原本預期的 FIFO 語意在這份程式裡不存在。
5. **沒有單元測試，也沒有論文 Fig. 1 的測試資料**；cache 集合 C 是「每顆衛星 60% 機率」隨機產生，加上所有 cloud 恆為 cache，`|C|` 無法由 config 控制（試跑 `|C|=5`）。

- **重用比例估計：約 50–60%**（依「ILP 比較所需能力」加權；以程式碼行數看，要重用的既有程式約 1,900 行，新寫約 600–800 行）。依據見第 6 節。
- **最大風險：成本語意不一致。** 若不處理 D1–D6，ILP 最優值與 TSMTA 的「成本」是在兩套不同定義下算的，量出來的近似比沒有意義。試跑中同一棵樹在 repo 定義下 TC=70.61，在你的定義下粗估約 131（BC 96.71、RC 3；這只是量級參考，尚未處理 D2、D3、D14）。

---

## 2. 元件盤點表

評級：直接可用／小改可用／需重寫／不存在。

| # | 項目 | 位置 | 資料結構 | 重用評級 | 備註 |
|---|------|------|----------|----------|------|
| 1 | 衛星軌道／星座產生 | `Random_Orbit.py:145-179`（`generate_walker_meta`）、`:181-200`（`get_pos`）、常數 `:14-16` | 回傳 `list[dict]` meta；`get_pos(meta,t)->(x,y,z)` ECEF km | 直接可用 | 高度 550 km、傾角 53°、Walker 相位參數 `f_phasing_param` 皆為參數。同軌道面衛星間隔固定 18°（`:150`）；`i%num_planes` 分面，`n_sats=8,num_planes=4` 時每面 2 顆。最小仰角 30°（`:15`、`:436`，不可由 config 改）。**角速度 `w` 是「每個 slot 轉 w 弧度」**（`phi0 + w*t`，`:187`；config 用 0.2），不是 rad/s，config `_comment` 寫的 0.00105 rad/s 與實際用法不同。constellation 本身無隨機性。 |
| 2 | 每 slot 拓樸建立 | `Random_Orbit.py:394-516` | `list[nx.DiGraph]`，節點 attr：`type`(src/dest/cloud/satellite)、`pos`、`cache`、`capacity`、`d/z/gamma`、`req_size`、`data_size`、`region`；邊 attr：`latency, bandwidth, used_bandwidth, cost_traffic, virtual` | 直接可用 | ISL：同軌道面前後相鄰＋相鄰面同 index（`:444-474`，會被地球遮擋檢查 `is_earth_blocking`）；地面—衛星：仰角>30° 才連（`:434-442`）；cloud—cloud、src—cloud 以距離門檻連（`:476-495`）；孤立節點補 lifeline 邊（`:497-513`、`ensure_strongly_connected :119-143`，權重×10）。region 抽象只用於 OffPA（`:205-224`）。 |
| 3 | 連結權重 w(e) | `Random_Orbit.py:18-31`（`get_cost_traffic_by_distance`）、`:33-50` | `float`，邊 attr `cost_traffic` | 小改可用 | `w = (距離km/10)*0.001*類型係數`，係數：sat–sat 1.0、涉及 cloud 但不含 satellite 0.5、其餘含 satellite 1.2；lifeline ×10。**浮點、非整數、不是純粹正比於距離**（依端點類型加係數）。範圍：小圖 0.2165–11.29；300 衛星/100 dest 大圖 0.039–6.71。需自行縮放取整（見 D10、建議 S=10^4～10^5）。 |
| 4 | 連結容量 τ(e) | `Random_Orbit.py:202-203`（`_sample_edge_bw` 恆回傳 1000）、`:47`（`used_bandwidth=0`） | 邊 attr `bandwidth` | 小改可用（值可讀，但無意義） | 恆為 1000；`used_bandwidth` 從未更新；TSMTA/PDTA/TVM 全都不讀 `bandwidth`（grep 驗證）。只有 DMTS（`DMTS.py:7-11`、`MBBSP.py`）用它。等同「無限容量」。 |
| 5 | source / destination / cache 選取 | `Random_Orbit.py:226-392`；`main.py:669-676` | node attr；`main.py` 取 `type`/`cache` 組成 `list[str]` | 小改可用 | 位置：`pos_seed = seed-42`（`:235`，硬編碼 hack）決定 src/dest/cloud 座標；dest 為 K=max(2,min(5,n_dests//5)) 個叢集（`:301-309`）；src 隨機。`rng_node=Random(seed+99991)`（`:232`）決定衛星 `cache`（60% 機率，`:344`）、`capacity`、`d`、dest `req_size`。**cloud 恆為 cache（`:378`），所以 C 含 cloud**，與「cache 衛星」不同。dest 可達性只在 slot 0 檢查（`main.py:676`）。`|C|`、`|D|` 中只有 `n_dests` 可直接指定。 |
| 6 | f、g、σ | f：`src["data_size"]=1.0`（`:383`）；g：`Algorithm.py:20-39`（`cost_cache`）；σ：`capacity`（`:345`、`:378`） | f：`float`；g：`float = α·γ·d·size^z`（衛星 concave、cloud linear）；σ：`float` | 小改可用 | f 對所有 slot 恆為 1.0；g 是**每個 cache 節點各自的值**（d∈[0.5,1.5] 衛星／[1,3] cloud，γ=1.5 衛星／1 cloud），不是只依 `a^t`；σ 衛星 500–1500、cloud 5000–20000，**從未被任何演算法讀取**。 |
| 7 | 有向弧規則 | 無 | — | 不存在 | 圖中 `G.edges` 全是雙向（試跑：30/30 條弧的反向弧存在且同權重）；src 有進入弧 4 條、dest 有外出弧 6–7 條。建樹時只有 src 作為樹根，所以 src 進入弧不會被樹用到；**dest 外出弧會被用**（D6）。 |
| 8 | TSMTA 實作 | TIG/CTIG：`TVM.py:37-151`（`TIG_CTIG`）；虛擬 s→c 邊：`:91-120`；主迴圈（TMTA 選樹）：`TVM.py:200-408`（`TSMTA`）；樹／密度演算法：`PDTA.py:114-293`（`PDTA/_PDTA_impl`）、`:43-58`（`PDTA_Density`）；展開虛擬邊：`TVM.py:152-198`；RCL：`TVM.py:761-953`（`Optimal`，變數 `RCL` 在 `:799`） | TIG/CTIG：`dict[(src_idx,i,j)] -> nx.DiGraph`；輸出 `T_i_t: dict[(src_idx,t)] -> nx.DiGraph` | 直接可用（黑盒） | **程式中沒有 EGD、RLDT、TMTA 這些識別字**（grep：只有 `RCL`、plot 的標籤 `TSMTA-TMTA`＝`TSMTA-Optimal`，`plot_results.py:177`）。對應關係我只能推測：TIG/CTIG＝`TIG_CTIG`；PDTA＝`PDTA.PDTA`；RCL＝`Optimal`；EGD/RLDT/TMTA 的對應**不確定**，需你確認。`pdta_level`(k=1/2/3) 是 PDTA 遞迴深度。 |
| 9 | 輸出格式 | TSMTA：`TVM.py:408`；DMTS：`main.py:69-96`；SSSP：`main.py:26-66`；OffPA：`OffPA.py:324` | 見下 | 小改可用 | **TSMTA／DMTS／SSSP**：`dict[(0,t)] -> nx.DiGraph`（樹的弧，邊 attr 帶 `cost_traffic/BC/CC/virtual`）。TSMTA 的 cache 決策 μ 以**節點 attr `cache_selected=True`** 存在樹上（`TVM.py:165`，只在 `expand_virtual_edges` 之後有，且 Optimal 後會遺失，見 D3）。destination 的 path / origin **沒有顯式輸出**，要沿 predecessor 往上走自己推（`TVM._dest_effective_edges :529-547` 是同樣邏輯）。**OffPA**：`dict[(0,t)] -> DiGraph`，但資訊放在 `DG.graph`：`selected_caches`、`distribution_paths`（cache→s 路徑）、`assigned_req_paths`（dest→cache 路徑）、`CT_*`；它是 per-request unicast，不是 multicast tree，BC 以 `req_size`(200–800) 加權，數值（試跑 37,814）與其他演算法不可比。 |
| 10 | 成本函式 | `TVM.py:410-640`（BC/CC/RC）、`:735-759`（`evaluate_algorithm`） | `evaluate_algorithm(name, T_i_t, src_nodes, caches, total_time, alpha, beta) -> (bc, cc, rc, total)` | 需重寫（另寫獨立 evaluate） | 不獨立於演算法：依 `name` 分支、依樹上節點 attr（`cache_selected`）與邊 attr（儲存的權重）計算；與你的定義有 D1–D6、D14 的差異。詳見 E.3。 |
| 11 | 批次腳本 | `main.py:580-839`（`main`）、`run.sh`、`nchc/*`（Slurm）、`TIG_Cache.py` | JSON config（`n_sats, n_dests, total_time, num_planes, altitude_km, inclination_deg, f_phasing_param, base_angular_velocity, thr_cloud_to_cloud, region_dist_thr, alpha_values, beta_values, pdta_level, num_runs, base_seed, algos, use_tig_cache`）；結果存 Excel（`Save_And_Read_Graphs.py:114-169`）與 checkpoint JSON（`main.py:550-573`） | 小改可用（參考其模式） | seed：`current_seed = base_seed + run_idx`（`main.py:644`）。掃 β、α（config 陣列）、`n_sats`/`n_dests`（`run.sh` 以 jq 改 config 後逐次呼叫 `main.py`）。**結果只存 BC/CC/RC/Total 的統計，不存樹**，所以舊實驗無法回推解，只能重跑。`run.sh` 需要 bash + jq。 |
| 12 | 單元測試／Fig. 1 範例 | 無 | — | 不存在 | repo 內沒有 `test_*.py`、沒有 pytest 設定、沒有任何把論文 Fig. 1 寫成資料的檔案（grep `Fig`、`example`、`test` 皆無相關）。pytest 7.4.4 已安裝。 |

另：`Save_And_Read_Graphs.load_graph_sequence_from_txt`（`:57-112`）用 `eval()` 讀圖檔，可存／讀整串 `list[nx.DiGraph]`；ILP 用的 instance 建議自己存 JSON，不要沿用。

---

## 3. 定義差異清單

影響欄：高＝會改變 TC 數值／結論；中＝影響可行集合或公平性；低＝記錄即可。

| 編號 | 差異（含出處） | 影響 | 建議處理方式 |
|------|----------------|------|--------------|
| **D1** | **BC 對 cache 下游的弧乘 0.3。** `BC_multicast_cache_aware(..., cache_hit_factor=0.3)`（`TVM.py:432-463`，TSMTA 分支 `:613-620`）：DFS 走樹，一旦經過 `caches` 內的節點，之後每條弧成本 ×0.3。你的定義 BC = Σ f·w，沒有這個折扣。試跑：repo BC=51.30，無折扣 BC=96.71。論文是否有類似折扣我**不確定**。 | 高 | 新 evaluator 預設用你的定義（無折扣）；另提供 `repo_compat=True` 選項重現 repo 數字，僅做回歸測試。請你確認論文立場（決策 Q1）。 |
| **D2** | **「cache」＝樹上任何屬於 `caches` 集合的節點，不論有沒有被選用（μ）。** D1 的折扣與 RC 的 origin 截斷（`_dest_effective_edges`，`TVM.py:529-547`，`u in caches` 即停）都用集合成員判斷；CC 卻只算 `cache_selected` 的節點（`TVM.py:466-492`）。試跑：t=0 的樹經過 cache `v10` 當中繼，`cache_selected=[]`，卻享受 0.3 折扣、且 `v10` 被當成 dest `v3`、`v4` 的 origin，沒付 CC。 | 高 | 新 evaluator 的 origin 只認 μ(c,t)=1 的 cache（見 E.1 的 μ 推導規則）。 |
| **D3** | **`Optimal` 之後 `cache_selected` 旗標遺失，CC 被少算。** `Optimal` 以 `Algorithm.shortest_path_tree` 建新樹（新 `DiGraph`，無節點 attr，`TVM.py:907`），再用 `node_attr_map` 補靜態屬性（`:913-916`），而還原旗標的程式碼被註解掉（`TVM.py:774-780`、`:918-922`）。試跑 t=1：Raw 的 `cache_selected=['v10']`，Optimal 後為空，但樹仍含 `v1→v10` 的 trunk 弧；整體 CC 由 1.72 降到 0.86，「Optimal 改善」有一部分可能只是旗標遺失。 | 高 | 不要改 repo；adapter 從樹重新推導 μ（E.1），並在 evaluator 一律用推導出的 μ。另請在論文／實驗紀錄中確認 TSMTA-Optimal 的 CC 是否受影響（我只在 1 個 13 節點實例上驗證，**不確定**是否普遍）。 |
| **D4** | **RC 是「平均」而不是「總和」，且 β 乘在平均上。** `RC_multicast` 回傳 `total_cost/transition_count*beta`（`TVM.py:571-572`），呼叫時未傳 `beta`（`:623`，預設 1.0），之後 `total = bc + alpha*cc + beta*rc`（`:635`）。所以實際 RC 項 = β·(變動次數)/(T−1)。試跑：變動共 3 次、2 次轉換 → RC=1.50（輸出 `RC=1.50`）；你的定義 Σ 為 3。T=10 時 repo 的有效 β 是 β/9。 | 高 | 新 evaluator 用總和；若要和歷史實驗對照，換算 β_eff=β/(T−1)。 |
| **D5** | **RC 的比較對象。** `_dest_effective_edges` 沿 predecessor 往上走，遇到第一個 `caches` 內的節點停止，回傳「origin→d 的弧集合」；s→cache 的 trunk 不算。這與你的定義（path 為 origin→d）一致，但 origin 判斷受 D2 影響。比較用 `frozenset` 弧集合不等價於節點序列，但在樹上等價。dest 若只在其中一個 slot 出現會被算為變動（`dests = dests1 | dests2`）。 | 中 | 沿用「origin→d 弧集合比較」的語意，origin 改用 μ。 |
| **D6** | **有向弧規則未實作；dest 可被當中繼。** 見盤點 #7。試跑 t=0：`v1→v2→v10→v3`、`v1→v2→v10→v6→v4` 都穿過 dest `v2`。lifeline 邊（`:497-513`）也是雙向。 | 高（可行集合不同） | 在 `from_existing` 中：把進入 s 的弧、離開 D 的弧刪掉，**再**把刪過的圖餵給 TSMTA（TIG_CTIG 之前）。注意刪弧可能使某 dest 不可達，需要重抽 seed（決策 Q3）。 |
| **D7** | **τ(e) 不生效。** 見盤點 #4。 | 低 | ILP 先不加頻寬約束（或加一個永不綁死的 τ），並在報告註明；若要啟用需定義 f 的單位（決策 Q6）。 |
| **D8** | **σ(c) 與 FIFO 不存在。** `capacity`（`Random_Orbit.py:345,378`）與 `storage_used`（`:414`）只在建圖時寫入，全 repo grep 沒有任何讀取或更新；沒有 FIFO、沒有「cache 滿了」的處理。`σ`(500–20000) 遠大於 f=1，即使實作也不會綁死。cache 成本 CC 是**逐 slot** 計（每個 (c,t) 若被選用就付一次 g），而不是整段時間總量。你問的「FIFO 與 μ[c,t] 語意相容性」在此無對象可比。 | 中 | ILP v1 不加容量約束；若論文的 σ 限制是「同一時刻最多存 σ(c) 個 view」，單一內容、f=1 時為恆成立（決策 Q6）。 |
| **D9** | **f、g 的形式。** f 恆為 1.0；g 為每節點各自的 `α·γ·d·size^z`（`Algorithm.py:20-39`）。建 TIG 時 α 已乘進虛擬邊 CC（`TVM.py:103-110`），評估時 `cc` 用 α=1.0 算再乘 α（`TVM.py:622,635`）——兩者一致，但整合時要小心 α 不要乘兩次。 | 低 | Instance 內存 `g[c,t]`（不含 α），α 單獨存。 |
| **D10** | **權重為浮點，且不嚴格正比於距離。** 見盤點 #3。量化誤差實測（`seed=42`）：小圖 S=10^3 → 最大相對誤差 2.1e-3；S=10^4 → 1.7e-4；S=10^5 → 1.6e-5；大圖（300 衛星、100 dest）S=10^4 → 1.25e-3、S=10^5 → 1.25e-4。最大整數係數 S=10^5 時約 1.1×10^6，CP-SAT 完全沒問題。 | 中 | 建議 S=10^5（小圖可 10^4）；每個 slot 的總誤差上界 ≤ 弧數×0.5/S；驗證時以「未量化浮點權重」重算 TSMTA 與 ILP 兩邊成本，並報告量化造成的最大偏差。β 乘 S 後仍為整數（β 為整數時）。 |
| **D11** | **種子語意與 |C| 不可控。** `pos_seed = seed - 42`（`Random_Orbit.py:235`）使 seed=42 時位置種子為 0；`seed` 另決定節點屬性。衛星 cache 為 Bernoulli(0.6)，cloud 恆為 cache，所以 `|C|` 隨機。試跑 `|C|=5`（1 cloud＋4 衛星），超過你要的 1–2。 | 中 | adapter 以自己的 `random.Random(seed+k)` 從候選集合抽 `|C|` 個，並把這個清單當作 `caches` 參數傳給所有演算法（所有函式都接受外部傳入的 `caches`，不必改 repo）。 |
| **D12** | **時間編號與目標函式。** slot 為 0-based，`t=0..T-1`（`Random_Orbit.py:395`）；RC 轉換為 `t→t+1`，`t=0..T-2`（`TVM.py:556`），等價你的「t≥2」（1-based），**無 off-by-one**。但 PDTA 的密度 `(cost + β·D_T/interval_len)/D_T`（`PDTA.py:58`）對第一個 interval 也收 β，而評估時第 1 個 slot 不收 RC——只影響 TSMTA 選樹的 heuristic，不影響評估。 | 低 | 記錄即可。 |
| **D13** | **每 slot 的圖確實不同。** 試跑：t0→t1 移除 4、新增 6 條弧；t1→t2 移除 6、新增 4；30 條弧中 16 條權重隨 slot 改變；節點集合固定。 | — | 無需處理；Instance 以 `arcs[t]` 分 slot 存。 |
| **D14** | **BC 讀的是樹上儲存的權重，不是該 slot 的真實權重。** 樹的邊 attr 複製自 `TIG_Interval[(·,i,j)]`（區間內「平均權重×data_size」，`TVM.py:86`、`:378`）；`Optimal` 還會把 t1 的邊權重複製到 t_l..t_r（`TVM.py:898-901`、`:929`）。試跑：Optimal 樹的弧 `v6→v4` 儲存值 5.1351 在 t=0/1/2 的真實權重分別是 5.3192/5.0026/5.0834；以真實權重重算 BC 為 51.1985，repo 為 51.2975（差 0.2%）。區間內弧不變時總和相等，但 Optimal 之後不保證。 | 中 | 新 evaluator 一律以 `Instance.arcs[t][(u,v)]` 的真實權重計算。 |
| **D15** | **α、β 預設值與論文設定（α=1, β=100）不一致。** `main.py:596-597` 預設 α、β 皆為 `[1,10,50,100]`；`configs/realistic_54sats.json:17-18` 與 notes 的實驗為 α=5、β=10；只有 `TVM.evaluate_algorithm` 的函式預設值是 α=1、β=100（`:741-742`）。加上 D4，實驗中的 β 有效值遠小於論文。 | 中 | ILP 比較請明確指定 (α,β)，建議同時跑 (1,100) 與 (5,10)。 |
| **D16** | **論文 Fig. 1 與正文疑似筆誤。** 我沒有論文原文，也沒有 Fig. 1 的資料，**無法逐項核對（不確定）**。可提供的是程式實際行為（以此為準）：RC=平均而非總和（D4）；BC 有 0.3 折扣（D1）；origin 為「最近的 cache 祖先」且 trunk 不計 RC（D5）；trunk 在 BC 內以全額計費（試跑 t=2：`v1→v10` 全額，其後弧 ×0.3）。 | — | 請你拿這四點對照論文 Fig. 1 的數字，有出入的地方告訴我，我再把 Fig. 1 做成測試資料。 |

共用 link 只算一次（你的項目 C.2）：**成立**。樹是 `nx.DiGraph` 且每個節點只有一個 parent，BC 沿樹各弧只加一次（`TVM.py:427`、`:452-461`）；DMTS/SSSP 的 `BC_multicast` 也是對弧集合各加一次。唯一例外是 OffPA（per-request 單播加總，`OffPA.py:127-138`）。另提醒：repo 的可行解必須是**樹（in-degree ≤ 1）**；若 ILP 只要求弧的聯集覆蓋所有 dest，可行集合更大（DAG），算出的最優值可能低於任何「樹」解（決策 Q4）。

「destination 可由 cache 或 source 供應」（C.6）：**成立**。origin＝樹上最近的 cache 祖先，沒有則為 s（`TVM.py:529-547`）；但 cache 是否「被選用」見 D2。

---

## 4. 試跑紀錄

**目的**：驗證能否在小圖上跑完整流程、並把輸出還原成 ILP 需要的結構。**方法**：把 11 個 `.py` 複製到 scratchpad（`.../scratchpad/trial/`），在副本中跑，不動 repo；`PYTHONDONTWRITEBYTECODE=1`。

**環境問題（非程式邏輯）**：第一次執行 `UnicodeEncodeError: 'cp950' codec can't encode character '\U0001f4cc'`，因為 `main.py` 的 print 含 emoji、Windows 主控台為 cp950。設 `PYTHONUTF8=1 PYTHONIOENCODING=utf-8` 後正常。

**設定**（`tiny.json`）：`n_sats=8, n_clouds=1, n_srcs=1, n_dests=3, total_time=3, num_planes=4, altitude_km=550, inclination_deg=53, f_phasing_param=1, base_angular_velocity=0.2, thr_cloud_to_cloud=3200, region_dist_thr=1000, alpha=5, beta=10, pdta_level=2, base_seed=42, num_runs=1, use_tig_cache=false`。

**指令**：`PYTHONUTF8=1 python main.py tiny.json sats all`（在副本目錄內）。

**結果**：成功，總 wall time 約 5 秒（TIG/CTIG 建置 0.011 s；TSMTA Select 0.535 s，其中 `TVM.py:407` 有 `time.sleep(0.5)`；Optimal 0.040 s）。

| 演算法 | BC | CC | RC | Total |
|---|---|---|---|---|
| DMTS | 101.92 | 0 | 7.00 | 171.92 |
| OffPA | 37814.43 | 3.84 | 3.00 | 37863.64 |
| SSSP | 95.97 | 0 | 9.00 | 185.97 |
| TSMTA-Raw | 51.24 | 1.72 | 2.00 | 79.86 |
| TSMTA-Optimal | 51.30 | 0.86 | 1.50 | 70.61 |

**圖與節點**：13 節點；src=`v1`、dest=`v2,v3,v4`、cloud=`v0`、衛星 `v5..v12`；`caches=[v0(cloud), v7, v10, v11, v12]`（`|C|=5`）。每 slot 弧數 30/32/30，頻寬集合 `{1000}`，權重 0.2165–11.29。

**樹與 cache 決策是否能還原**：能。`T_i_t[(0,t)]` 是 `nx.DiGraph`，`Optimal` 後三個 slot 的弧集合：

- t=0：`v1→v2, v2→v10, v10→v3, v10→v6, v6→v4`
- t=1：`v1→v10, v10→v6, v6→v2, v6→v4, v2→v12, v12→v5, v5→v9, v9→v3`（Raw 為 `v10→v2` 而非 `v6→v2`）
- t=2：`v1→v10, v10→v6, v6→v2, v6→v4, v4→v9, v9→v3`

每個 dest 的路徑可沿 predecessor 走回根（例如 t=2 的 `v3`：`v1→v10→v6→v4→v9→v3`，origin=`v10`）。**但 μ（cache 決策）只能部分還原**：`cache_selected` 在 Raw 為 t=1: `[v10]`、t=2: `[v10]`；Optimal 後 t=1 變為空（D3）。t=0、t=1 的樹經過 `v10`、`v12` 但未被標記為選用（D2）。樹中沒有殘留虛擬邊。

**同一組解，兩種定義比較**（Optimal 樹）：

| 定義 | BC | CC | RC | TC |
|---|---|---|---|---|
| repo `TVM.evaluate_algorithm`（α=5, β=10） | 51.30 | 0.86 | 1.50（平均） | 70.61 |
| 你的定義（我在試跑腳本內獨立重算：BC 無折扣（沿用樹上儲存的權重）、CC 用 `cache_selected`、RC 總和且 origin 沿用「最近的 cache 祖先」） | 96.71 | 0.86 | 3 | 131.02 |

（上列右表僅作量級參考：BC 用樹上儲存的權重、CC 沿用 Optimal 後的旗標，故尚未解決 D2、D3、D14，不是最終 evaluator 的輸出。）

試跑腳本 `inspect_run.py`、`quant.py` 留在 scratchpad，不在 repo 內。

---

## 5. Adapter 設計

### 5.1 資料模型（新寫，不依賴 networkx）

```python
@dataclass(frozen=True)
class Instance:
    T: int                                   # slot 數，t = 0..T-1
    nodes: list[str]
    s: str
    D: list[str]
    C: list[str]
    arcs: list[dict[tuple[str, str], int]]   # arcs[t][(u,v)] = 量化後 w(e)；已套用單向規則
    tau: list[dict[tuple[str, str], float]]  # 可為空：頻寬（恆 1000，ILP v1 不用）
    f: list[int]                             # f[t]：view 大小，已乘 scale（repo 恆為 1.0）
    g: dict[tuple[str, int], int]            # g[(c,t)]：快取成本（不含 α），已乘 scale
    sigma: dict[str, float]                  # σ(c)（repo 未使用）
    alpha: float
    beta: float
    scale: int                               # 權重縮放倍率 S
    meta: dict                               # seed、config、原始浮點權重（供驗證）

@dataclass
class Solution:
    arcs: list[set[tuple[str, str]]]         # T^t：每 slot 的樹弧
    mu: dict[tuple[str, int], int]           # μ(c,t) ∈ {0,1}
    origin: dict[tuple[str, int], str]       # (d,t) -> s 或 cache
    path: dict[tuple[str, int], list[tuple[str, str]]]   # (d,t) -> origin→d 的弧序列
```

### 5.2 `from_existing(config, seed) -> Instance`

| 欄位 | 來源 | 需新寫的轉換 |
|---|---|---|
| 圖序列 | `Random_Orbit.generate_graph_sequence_realistic(seed=..., **config 參數)`（參數對照 `main.py:653-667`）→ `list[nx.DiGraph]` | 無（直接呼叫）。建議用 `n_clouds=0` 避免 cloud 被當 cache（決策 Q2） |
| `T` | `len(graphs)`（`main.py:673`） | — |
| `s` | `type=="src"` 的第一個節點（`main.py:669`） | — |
| `D` | `type=="dest"`；`main.py:676` 的做法是只檢查 slot 0 可達 | 改成「所有 slot 在刪弧後皆可達」才保留 |
| `C` | `cache is True`（`main.py:671`） | 以 `random.Random(seed+k)` 從候選集合抽 `|C|` 個（可指定 1–2），結果以參數傳給 TSMTA／OffPA／evaluator |
| `arcs[t]` | `G.edges(data=True)` 的 `cost_traffic`（`Random_Orbit.py:43-50`） | 刪除 `v==s` 的弧與 `u∈D` 的弧；`round(w*scale)`；保留原浮點權重於 `meta` |
| `tau[t]` | 邊 attr `bandwidth`（恆 1000） | 直接讀即可 |
| `f[t]` | `G.nodes[s]["data_size"]`（`Random_Orbit.py:383,420`） | ×scale |
| `g[(c,t)]` | `Algorithm.cost_cache(G.nodes[c], f, alpha=1.0)`（`Algorithm.py:20-39`） | ×scale；注意用 α=1.0 以免與 α 重複計入（D9） |
| `sigma[c]` | `G.nodes[c]["capacity"]` | 直接讀；ILP v1 不使用 |
| `alpha, beta` | 呼叫參數（不要用 config 的陣列） | — |

另需回傳**刪弧後的 `list[nx.DiGraph]`**（`from_existing` 回傳 `(Instance, graphs_filtered, node_attr_map)`），供 TSMTA 使用——這是新寫的部分：對每張圖 `copy()` 後 `remove_edges_from`，並確認 `TIG_CTIG` 所需的邊 attr（`cost_traffic`、`virtual`）未被破壞。

### 5.3 `from_tsmta_output(instance, graphs_filtered, tsmta_result) -> Solution`

流程（全部沿用 `main.py:328-450` 的呼叫）：`Build_TIG_CTIG → Run_TSMTA_Select → copy_tree_sequence → expand_virtual_edges → [Optimal]`，得到 `T_i_t: dict[(0,t)] -> nx.DiGraph`。

| 欄位 | 取得方式 | 需新寫的轉換 |
|---|---|---|
| `arcs[t]` | `set(T_i_t[(0,t)].edges())` | 先 `expand_virtual_edges`（Raw 與 Optimal 都要），再斷言無 `virtual=True` 的邊、根唯一、in-degree≤1 |
| `path[(d,t)]` | 沿 `G.predecessors` 往上走到根 | 新寫（~15 行；同 `TVM._dest_effective_edges`） |
| `origin[(d,t)]` | 路徑上離 d 最近、且 μ=1 的節點，否則 s | 新寫 |
| `mu[(c,t)]` | **不能直接用 `cache_selected`**（D3）。建議規則：μ(c,t)=1 當且僅當 c∈C 且 c 是某個 d 的最近 cache 祖先（「被用到才付 CC」）。另提供模式 `mu_mode="flag"`（Raw 的 `cache_selected`）作對照 | 新寫；此規則是我的設計，是否合乎論文**不確定**，列入決策 Q5 |
| 其他 baseline | DMTS／SSSP：同上（`dict[(0,t)] -> DiGraph`）；OffPA：讀 `DG.graph["assigned_req_paths"]`／`["distribution_paths"]` | OffPA 不是樹，只能轉為「每 dest 路徑」，通常不納入 ILP 比較 |

### 5.4 ILP 暖啟動

CP-SAT 用 `model.AddHint(var, value)`：`x[t,e]=1 if e∈arcs[t]`、`mu[c,t]`、以及路徑／origin 指派變數。暖啟動前先用 evaluator 驗證該解可行（滿足單向規則、樹、所有 dest 可達），否則 hint 會被忽略或造成誤導。

### 5.5 建議新增檔案（僅列出，未建立）

```
ILP_reuse_report.md                 # 本檔（已建立）
ilp/__init__.py
ilp/instance.py                     # Instance / Solution、JSON 讀寫
ilp/adapter.py                      # from_existing、from_tsmta_output、sys.path 處理
ilp/evaluate.py                     # 獨立 evaluate(instance, solution)；repo_compat 回歸模式
ilp/model_cpsat.py                  # OR-Tools CP-SAT 模型、暖啟動
ilp/run_ratio.py                    # 批次：seed 迴圈、近似比、輸出 CSV/JSON
tests/test_evaluate.py              # 手算小例、repo_compat 對照 TVM.evaluate_algorithm
tests/test_adapter.py               # 單向規則、μ 推導、虛擬邊展開
tests/data/fig1_instance.json       # 論文 Fig. 1（待你提供數字）
```

repo 為扁平結構（`import TVM` 等），在 repo 根目錄用 `python -m ilp.run_ratio` 執行即可 import 到既有模組，不需動既有檔案。

### 5.6 現有成本函式能否直接當驗證器（E.3）

**不能。** 原因：(1) 依 `name` 分支，行為不同（D1、D4）；(2) 依樹上節點／邊 attr（`cache_selected`、儲存權重）而不是 Instance（D2、D3、D14）；(3) 無單向規則檢查、無樹性／可達性檢查；(4) 平均 RC。

**最小修改方案**：不改 `TVM.py`，新寫 `ilp/evaluate.py`（約 60–80 行）：輸入 `(Instance, Solution)`，BC＝Σ_t Σ_{e∈T^t} f[t]·w_t(e)，CC＝Σ μ·g，RC＝Σ_{d,t≥1}[origin→d 弧集合不同]。加 `repo_compat=True` 參數（BC 折扣 0.3、RC 取平均、origin 用「cache 集合成員」）並以 `TVM.evaluate_algorithm("TSMTA", ...)` 在試跑樹上對拍（預期 Raw=(51.2366, 1.7241, 2.0, 79.8572)、Optimal=(51.2975, 0.8621, 1.5, 70.6078)，這組數字可直接寫成回歸測試）。若你偏好「改既有檔」，則是在 `TVM.py` 為 `BC_multicast_cache_aware` 加 factor=1.0 選項、為 `RC_multicast` 加 `average=False` 選項，但這會動到已發表實驗的程式，不建議。

---

## 6. 新寫 vs 重用的工作量粗估

估計依據：既有檔案的實際行數（`Random_Orbit.py` 571、`TVM.py` 954、`PDTA.py` 293、`Algorithm.py` 330、`main.py` 845）與各項的新寫行數估計；每小時產出以含測試與除錯約 20–30 行有效程式碼計。**這是粗估，非保證。**

| 項目 | 重用／新寫 | 規模 | 估計時數 |
|---|---|---|---|
| 圖產生、座標、權重、拓樸 | 重用（呼叫） | 0 新行；adapter 內 ~40 行抽取 | 2–3 h |
| TSMTA（TIG/CTIG/PDTA/展開/Optimal） | 重用（黑盒） | 0 新行；包成函式 ~50 行 | 2 h |
| 單向弧過濾、|C| 抽樣、可達性重抽 | 新寫 | ~60 行 | 3–4 h |
| Instance／Solution／JSON | 新寫 | ~80 行 | 2 h |
| 獨立 evaluator＋repo_compat＋回歸測試 | 新寫 | ~100 行＋測試 | 5–6 h |
| `from_tsmta_output`（含 μ 推導） | 新寫 | ~60 行 | 3–4 h |
| ILP 模型（CP-SAT：每 slot 樹、origin 指派、μ、RC 指示變數、暖啟動） | 新寫 | ~200–300 行 | 10–16 h |
| 批次、seed、近似比輸出 | 新寫（參考 `main.py` 的 checkpoint 模式） | ~100 行 | 3–4 h |
| Fig. 1 測試資料與測試 | 新寫（需你提供數字） | ~50 行 | 2–3 h |
| **合計** | | 新寫 ~650–800 行 | **約 32–44 h** |

若完全不重用（自己重寫圖產生器與 TSMTA）估計再增加 25–35 h，所以重用省下約 40–45% 的總工作量；以「能力」計重用約 50–60%，以「行數」計，被呼叫而不必重寫的既有程式約 1,900 行，新寫約 650–800 行。**ILP 模型本體與 evaluator 完全無法重用。**

---

## 7. 需要你決定的問題（最多 10 項）

| # | 問題 | 我的建議預設值 |
|---|------|----------------|
| Q1 | 論文的 BC 是否有「cache 下游 ×0.3」之類的折扣（D1）？ | 沒有。ILP 與 evaluator 依你給的定義（無折扣）；repo 定義只作回歸測試 |
| Q2 | C 是否只含衛星？repo 的 cloud 恆為 cache（`Random_Orbit.py:378`） | 只含衛星；小圖設 `n_clouds=0`，`|C|` 由 adapter 抽 1–2 個 |
| Q3 | 單向弧規則：在圖上刪弧後再跑 TSMTA（兩邊同一可行集合），還是保留雙向圖、對違規的 TSMTA 解另外處理？ | 刪弧後再跑 TSMTA；刪弧導致 dest 不可達時換 seed 重抽 |
| Q4 | ILP 是否強制每 slot 的 T^t 為樹（每節點 in-degree≤1）？ | 強制（與 TSMTA 可行集合一致，近似比才有意義）；可另跑「不強制」版本當下界 |
| Q5 | μ 的定義：只要被當 origin 才算 μ=1（我的推導規則），還是沿用 repo 的 `cache_selected` 旗標？ | 用 origin 推導規則，並報告兩種模式的差異 |
| Q6 | σ(c) 的語意與是否建模（單位、是否逐 slot）；τ(e) 是否啟用（需定義 f 的單位） | v1 都不建模（單一內容、f=1 時 σ 與 τ 都不會綁死）；等你確認論文語意再加 |
| Q7 | 權重縮放倍率 S | S=10^5（小圖 10^4 亦可）；以未量化浮點權重重算並報告偏差 |
| Q8 | α、β 組合與比較對象 | (α,β)∈{(1,100),(5,10)}；TSMTA 取 k=2 的 Optimal 為主、同時報 Raw、k=1/3 |
| Q9 | 精確解未證明最優時（CP-SAT 超時）怎麼報？ | 時限 600 s；報告時以 CP-SAT 的下界計算「近似比上界」並標示未收斂 |
| Q10 | 論文 Fig. 1 與正文疑似筆誤的確切位置；以及 EGD／RLDT／TMTA 與程式的對應 | 請你提供 Fig. 1 的數值與演算法名稱對照，我再補成測試資料與註解 |

---

## 8. 結論：擴充現有程式，或另開獨立模組

**建議另開獨立模組（`ilp/`），只 import 既有程式，不修改既有檔案。**

- 現有成本函式與你的定義差異過大（第 3 節 D1–D6、D14），而且這些函式已被已發表的實驗使用；直接改它們會讓舊結果無法重現。
- 圖產生器與 TSMTA 可以原樣呼叫，用 adapter 轉換即可；不需要動它們。
- 專案是扁平的 script 風格（`import TVM`、全域 `DIR_PATH`、固定 Excel 檔名），把 ILP 放進去會與 `main.py` 的 checkpoint／Excel 流程互相牽扯。
- 獨立 evaluator 同時是 ILP 與 TSMTA 的唯一計分標準，只有這樣量到的近似比才一致。
