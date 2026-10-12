# TAMCS ILP 精確解實作計畫（給 Claude Code 執行）

建立日期：2026-10-10
目標：用 OR-Tools CP-SAT 實作 TAMCS 的整數規劃精確解，從極小圖開始，逐階段驗證，最後量測 TSMTA 的實際近似比 TC(TSMTA)/TC(OPT)。
前置資料：`ILP_reuse_report.md`（已完成的 repo 檢查報告，D1–D16 與 Q1–Q10 皆出自該報告）。

---

## 0. 如何執行本計畫

1. 一次只做一個階段。每階段結束必須通過該階段的 **Gate**（全部測試綠燈＋列出的檢查項），才能進入下一階段。
2. 開工前先用 TaskCreate 把第 5 節的階段建成任務清單；每階段完成後 TaskUpdate。
3. 每階段結束，在 `ilp/PROGRESS.md` 追加一段：階段名、日期、執行的指令、測試結果（通過數／總數）、實際得到的關鍵數字、遇到的問題與處理。這份檔案是使用者驗證每一步的依據，不可省略、不可事後改寫。
4. 遇到 Gate 失敗：依第 8 節處理。**禁止為了通過而放寬測試、改期望值或跳過測試**。
5. 遇到本計畫沒定義、或與 repo 實際行為衝突的地方：停下來，把問題與你的建議寫進 `PROGRESS.md` 並回報使用者，不要自行假設後繼續。

---

## 1. 硬性規則

- **不得修改、刪除、重新格式化 repo 既有檔案**（`Random_Orbit.py`、`TVM.py`、`PDTA.py`、`Algorithm.py`、`main.py` 等）。所有新程式放在 `ilp/` 與 `tests/`。
- 允許在專案專用的虛擬環境（`.venv_ilp/`）中安裝 `ortools`；不得更動 repo 既有的相依套件清單。
- 既有程式只能 import 後呼叫（扁平結構，在 repo 根目錄執行 `python -m ...` 即可 import）。
- **`ilp/evaluate.py` 是唯一計分標準**：ILP、TSMTA、暴力法的解都交給它算成本，不得使用 repo 的 `TVM.evaluate_algorithm` 作為正式分數（只可在 `repo_compat` 回歸測試中使用）。
- 全部隨機性要有固定 seed；測試要可重現。
- Windows 環境：執行 Python 時設 `PYTHONUTF8=1`（repo 的 print 含 emoji，cp950 主控台會出錯）。
- 不得執行任何破壞性指令；不確定的結論標「不確定」並附依據。

---

## 2. 已定案的問題定義（evaluator、暴力法、ILP 三處必須完全一致）

### 2.1 Instance

- 時間 slot：`t = 0..T-1`（0-based）。
- 每個 slot 有向弧集合 `arcs[t]: dict[(u,v)] -> w_int`（正整數）。
- 節點：source `s`、目的地 `D`、cache 衛星 `C`，三者互不相交；其他為一般節點。
- **單向規則**：`arcs[t]` 中不得有進入 `s` 的弧，也不得有離開任何 `d∈D` 的弧（`validate_instance` 檢查）。
- 每個 slot 中，每個 `d∈D` 必須從 `s` 可達。
- 參數：`f[t]`（正整數，預設 1）、`g[(c,t)]`（非負整數，單位 1/S）、`alpha`、`beta`（**皆為整數**，`validate_instance` 斷言）、`scale S`。
- 浮點權重量化：`w_int = round(w_float * S)`，原浮點值存在 `meta` 供驗證。v1 不建模 `τ(e)`、`σ(c)`。

### 2.2 Solution（可行解的完整描述）

- `arcs[t]`：slot t 的樹弧集合 `T^t`。
- `mu[(c,t)] ∈ {0,1}`。
- `origin[(d,t)] ∈ {s} ∪ {c : mu[(c,t)]=1}`。
- `path[(d,t)]`：由樹唯一決定的 `origin → d` 弧序列。

### 2.3 可行性（`check_solution` 必須逐條檢查並回報違規）

1. `arcs[t] ⊆ instance.arcs[t]`。
2. `arcs[t]` 構成以 `s` 為根的有向樹：每個非根節點入度 ≤ 1、根無入弧、樹中所有節點都能從 `s` 到達（無環、無孤立分量）。
3. 每個 `d∈D` 在樹中。
4. 若 `mu[(c,t)]=1`，則 `c` 在樹中（trunk `s→c` 即為樹上唯一路徑）。
5. `origin[(d,t)]` 是 `s` 或某個 `mu=1` 的 cache，且**必須是 d 在樹上的祖先**。**不要求是「最近的」μ=1 祖先**（論文定義為「任何儲存 a^t 的 cache」；此為本計畫的決策 DEC-1，見第 3 節）。
6. `path[(d,t)]` = 樹上從 `origin` 到 `d` 的唯一路徑。

### 2.4 成本

```
BC = Σ_t Σ_{e ∈ T^t} f[t] · w_t(e)          # 樹上每條弧只算一次；以 instance 的真實 slot 權重計，不用樹上儲存的權重
CC = Σ_{c,t} mu[(c,t)] · g[(c,t)]
RC = Σ_{d∈D, t≥1} [ set(path[(d,t-1)]) != set(path[(d,t)]) ]   # 只比 origin→d；s→c 的 trunk 不算
TC = BC + alpha·CC + beta·RC
```

整數化：`TC_int = BC_int + alpha·CC_int + beta·S·RC`，其中 `BC_int` 用 `w_int`、`CC_int` 用 `g_int`。`TC = TC_int / S`。
`evaluate()` 回傳 dict：`BC, CC, RC, TC, TC_int`。若解中樹含「未被任何 path 或 trunk 使用的弧」，仍照實計入 BC，並額外回報 `pruned_TC`（修剪後的成本）供參考。

### 2.5 repo_compat 模式（僅供回歸測試）

重現 repo 的行為：BC 對 cache 集合下游的弧乘 0.3、RC 取平均（`/(T-1)` 並乘 β）、origin 用「樹上最近的 `caches` 集合成員」、BC 讀樹上儲存的權重（須由 fixture 提供）。僅在 `tests/test_evaluate_repo_compat.py` 使用。

---

## 3. 待使用者確認的決策（先用預設值進行，並在 PROGRESS.md 標註「待確認」）

| 編號 | 決策 | 預設 |
|---|---|---|
| DEC-1 | origin 可為任意 μ=1 的祖先（不強制最近）。此為論文「path 從 source 或儲存 a^t 的 cache 出發」的直接讀法，且讓 ILP 與暴力法可精確對拍 | 如左 |
| DEC-2 | C 只含衛星；小圖用 `n_clouds=0`，`|C|` 由 adapter 以固定 seed 抽 1–2 個 | 如左 |
| DEC-3 | 每 slot 強制為樹（入度 ≤ 1） | 如左；另提供 `enforce_tree=False` 選項當下界 |
| DEC-4 | BC 無 0.3 折扣、RC 為總和 | 如左（若論文實驗實際用 repo 定義，使用者自行處理） |
| DEC-5 | μ 的推導規則（TSMTA 解轉換用）：c 是某個 d 的最近 cache 祖先才算 μ=1；另提供 `mu_mode="flag"` 對照 | 如左 |
| DEC-6 | S = 10^5（小圖可 10^4）；(α,β) ∈ {(1,100),(5,10)}；TSMTA 以 k=2 的 Optimal 為主，另報 Raw | 如左 |
| DEC-7 | CP-SAT 時限 600 s；未證明最優時用下界報告「近似比上界」 | 如左 |

---

## 4. 檔案結構

```
.venv_ilp/                 # 虛擬環境（不進版控）
ilp/__init__.py
ilp/instance.py            # Instance / Solution / validate_instance / JSON 讀寫
ilp/evaluate.py            # check_solution / evaluate / prune / repo_compat
ilp/brute_force.py         # 與 ILP 完全獨立的窮舉精確解（極小圖）
ilp/model_cpsat.py         # build_model / solve / extract_solution / hint
ilp/adapter.py             # from_existing / from_tsmta_output
ilp/gen_random.py          # 隨機極小圖產生器（固定 seed）
ilp/run_ratio.py           # 批次實驗
ilp/PROGRESS.md            # 逐階段紀錄（必填）
tests/conftest.py
tests/fixtures/toy1.json   # 見附錄 A
tests/fixtures/toy2.json   # 見附錄 B
tests/fixtures/fig1.json   # 使用者提供後才有
tests/fixtures/repo_trial_seed42.json
tests/test_phase0_smoke.py ... tests/test_phase9_*.py
```

---

## 5. 階段計畫

### Phase 0：環境與 CP-SAT 熟悉

**做法**：建 `.venv_ilp`，安裝 `ortools`（記錄版本）。寫 `tests/test_phase0_smoke.py`。
**測試**：
1. `x+y≥1, min 3x+2y` → OPTIMAL，目標 2，選 y。
2. 流量守恆最短路徑（`out−in = +1/−1/0`）對 `networkx.shortest_path_length`，30 張隨機有向圖（固定 seed）全部相等。
3. 0/1 背包對暴力枚舉，20 個隨機例子相等。
4. 確認 `CpSolver` 的 `StatusName`、`ObjectiveValue`、`BestObjectiveBound`、`AddHint` 可用（新舊版方法名以實際安裝版本為準）。

**Gate**：全部通過；`PROGRESS.md` 記錄 Python 與 ortools 版本。

### Phase 1：Instance / Solution / 驗證 / JSON

**做法**：實作第 2 節的資料結構與 `validate_instance`（單向規則、正整數權重、α/β 為整數、D 可達、三集合互斥）。JSON 讀寫（tuple key 用 `"u->v"` 字串編碼）。
**測試**：
- 讀寫 round-trip 後 `==` 原物件（對 Toy-1、Toy-2 與 20 張隨機圖）。
- 故意違規的 instance 各一個（進入 s 的弧、離開 d 的弧、非整數 β、不可達 d、C 與 D 相交）都必須被 `validate_instance` 拒絕。

**Gate**：全部通過。

### Phase 2：獨立 evaluator（整個專案最關鍵的一步）

**做法**：實作 `check_solution`、`evaluate`、`prune`、`repo_compat`（第 2.3–2.5 節）。**不得 import ortools，也不得 import repo 既有演算法程式**（`repo_compat` 的回歸測試除外，且該測試不依賴 ortools）。
**測試**：
1. **手算對照（附錄 A）**：Toy-1 的解 S1、S2、S3、S4 的 BC/CC/RC/TC 必須與附錄 A 的手算值完全相等。
2. **必須被拒絕的不可行解**（每項一個測試，且斷言違規訊息指出正確原因）：入度 2、含環、有弧不在該 slot 的圖中、目的地不在樹中、`mu=1` 的 c 不在樹中、origin 是 `mu=0` 的 cache、origin 不是 d 的祖先、樹中有從 s 不可達的節點。
3. **性質測試**（隨機）：
   - 把 `T^t` 多加一條 d 之外的葉弧：BC 增加、`pruned_TC` 不變。
   - 兩個 d 共用弧：該弧只算一次（Toy-2）。
   - 縮放不變性：所有權重與 g 同乘 k，且 β·S 的 RC 項同比例，TC_int 同乘 k。
   - 節點更名不改變成本。
4. **repo_compat 回歸**：用 fixture `repo_trial_seed42.json`（由 `ILP_reuse_report.md` 第 4 節的試跑重新產生，見下）重現：
   - TSMTA-Raw：(BC, CC, RC, TC) = (51.2366, 1.7241, 2.0, 79.8572)
   - TSMTA-Optimal：(51.2975, 0.8621, 1.5, 70.6078)
   - 容許誤差 1e-3。fixture 產生方式：在 scratchpad 的程式**副本**中以 `tiny.json` 設定（`n_sats=8, n_clouds=1, n_srcs=1, n_dests=3, total_time=3, num_planes=4, base_seed=42, alpha=5, beta=10, pdta_level=2`）跑 TSMTA，輸出每 slot 樹弧、樹上儲存的權重、`cache_selected`、`caches` 清單。若無法重現報告中的數字，**不要調整 evaluator 去湊**，記錄差異並回報。

**Gate**：1–3 全部通過；4 通過或已回報差異原因。

### Phase 3：暴力精確解（獨立於 ILP 與 CP-SAT 的第二意見）

**做法**：`brute_force.py`，只適用極小圖（節點 ≤ 7、`|D|≤3`、`|C|≤2`、`T≤3`）。
1. 對每個 slot 窮舉所有候選 `(樹, μ, origin 指派)`：枚舉每個非根節點「選一個父節點或不入樹」，過濾出以 s 為根、含所有 D、且 μ 與 origin 滿足 2.3 的組合。允許只保留「葉子 ⊆ D ∪ {μ=1 的 c}」的樹（修剪後的樹，因成本為正，最優解必在其中；在程式註解中寫明此論證）。
2. 以 `evaluate` 為每個候選計 `BC+α·CC`，轉換成 slot 內成本。
3. 以動態規劃跨 slot 合併：`dp[t][k] = min_j(dp[t-1][j] + β·S·RC(j→k)) + cost[t][k]`，RC 為 `evaluate` 同義的路徑集合比較。
4. 回傳最優 TC_int 與一組最優解。

**測試**：
- Toy-1 全表（附錄 A.3）逐格相等；Toy-2 為 6·S。
- 暴力法回傳的最優解丟給 `check_solution` 必須可行，且 `evaluate` 的 TC_int 等於 DP 值。
- 隨機 30 張極小圖：用「完全不經過 DP 的最簡窮舉」（T≤2 時，直接枚舉所有 slot 候選的笛卡兒積並用 `evaluate` 整體計分）對拍 DP，數值必須相等。

**Gate**：全部通過。

### Phase 4：ILP 階段 A —— 單 slot、無 cache（Steiner 樹）

**做法**：`model_cpsat.py` 的最小版本：變數 `x`、`y`（origin 固定為 s）；限制 C3（流量守恆）、C5（x ≥ y）、C6（入度 ≤ 1）。詳細規格見第 6 節，以 `use_cache=False, T=1` 呼叫。
**測試**：
1. Toy-2：最優值 = 6·S（共用 link 只算一次）；若得 8·S 表示成本算在 y 上而不是 x 上。
2. 50 張隨機極小圖（節點 5–7，`|D|` 1–3，固定 seed）：ILP 最優值 == 暴力法。
3. 對每個解：`extract_solution` → `check_solution` 可行，且 `evaluate().TC_int == solver.ObjectiveValue()`（精確整數相等）。
4. `model.Validate()` 為空字串；狀態為 OPTIMAL。

**Gate**：全部通過。

### Phase 5：ILP 階段 B —— 多 slot、無 cache、加入 rerouting

**做法**：加入 `r[t,d]` 與 C7；`use_cache=False, T≥2`。
**測試**：
1. Toy-1 設 `C=∅`（或 α 極大）：β=0 → 15·S；β=1 → 17·S；β=2 → 19·S；β=10 → 22·S（附錄 A.3）。
2. 100 張隨機極小圖（T=2–3，β ∈ {0,1,5,50}）：ILP == 暴力法。
3. 性質：β=0 時 TC 等於各 slot 獨立求解之和；β 遞增時 TC 單調不減、RC 單調不增；β 極大時（≥ 所有 BC 差異總和）每個 d 在所有 slot 路徑相同（若圖允許）。
4. 同 Phase 4 的第 3、4 項檢查。

**Gate**：全部通過。

### Phase 6：ILP 階段 C —— 加入 cache

**做法**：加入 `mu`、`h`、`z` 與 C1、C2、C4。`use_cache=True`。
**測試**：
1. Toy-1 完整表（附錄 A.3，含 α、β 各組合）逐格相等。
2. 150 張隨機極小圖（`|C|` 1–2，T=2–3，β ∈ {0,1,5,50}，α ∈ {1,5}）：ILP == 暴力法。
3. 性質：
   - 允許 cache 的最優值 ≤ 不允許 cache 的最優值（Phase 5 同圖）。
   - α 極大時，最優解 μ 全為 0，值等於無 cache 的最優值。
   - β=0 時最優解不需要 cache（值等於無 cache 的最優值）。
   - `enforce_tree=False` 的最優值 ≤ `enforce_tree=True` 的最優值。
4. 穩定性：同一 instance 以 `num_workers=1,random_seed=0` 與 `num_workers=8,random_seed=7` 各解一次，最優值必須相同。
5. 同 Phase 4 的第 3、4 項檢查。

**Gate**：全部通過。這是 ILP 模型正確性的最終判定；通過前不得進入 adapter 與實驗。

### Phase 7：Adapter（接上現有 TSMTA）

**做法**：`adapter.py`，依 `ILP_reuse_report.md` 第 5 節設計：
- `from_existing(config, seed, n_c, scale)`：呼叫 `Random_Orbit.generate_graph_sequence_realistic`（`n_clouds=0`）；以 `random.Random(seed+k)` 抽 `|C|`；**刪除進入 s 與離開 D 的弧**；重新檢查每 slot 所有 d 可達，否則換 seed 重抽（記錄重抽次數）；量化權重；回傳 `(Instance, graphs_filtered, node_attr_map)`。
- `from_tsmta_output`：以刪弧後的圖呼叫 `Build_TIG_CTIG → Run_TSMTA_Select → copy_tree_sequence → expand_virtual_edges → [Optimal]`；重新推導 μ 與 origin（DEC-5）；輸出 `Solution`。呼叫所有函式時 `caches` 參數都傳入 adapter 抽出的 C。
- 指令需在 repo 根目錄、`PYTHONUTF8=1` 執行；`TVM.py` 內的 `time.sleep(0.5)` 不要動。

**測試**：
1. 轉換後的 instance 通過 `validate_instance`（無進入 s、無離開 D 的弧、全可達）。
2. 量化誤差：每條弧 `|w_int/S − w_float| ≤ 0.5/S`；記錄最大相對誤差並與報告 D10 的量級（S=10^5 約 1.6e-5）比較。
3. 20 個 seed：TSMTA（Raw 與 Optimal）轉出的解**全部通過 `check_solution`**。若有違規，逐一列出違規類型與次數寫入 `PROGRESS.md`（這本身是有價值的發現，例如 D3 旗標遺失、樹含多餘弧），**不要在 adapter 內偷偷修補**；經使用者同意前，只可套用已在 DEC-5 定義的 μ 推導。
4. 對同一 instance，`Solution` 經 JSON 儲存再讀回，`evaluate` 結果不變。

**Gate**：1、2、4 通過；3 的結果完整記錄。

### Phase 8：暖啟動與近似比實驗

**做法**：
- `model_cpsat.add_hint(model, vars, solution)`：提供**完整** hint（`x, mu, h, y, z, r` 全部；y 由 path 推導，z 由 s→c 樹路徑推導，r 由相鄰 slot 路徑比較推導），否則 CP-SAT 可能忽略。
- `run_ratio.py`：對 seed 集合、(α,β) ∈ {(1,100),(5,10)}、規模網格（`n_sats` 8–20，`|D|` 2–3，`|C|` 1–2，`T` 3–4），各 20 個 seed：建立 instance → TSMTA（Raw、Optimal；k=2，另可選 k=1/3）→ evaluate → ILP（hint 與不 hint 各一次，時限 600 s）→ 記錄 `TC_TSMTA, TC_ILP, bound, status, runtime, ratio, ratio_upper`（未收斂時 `ratio_upper = TC_TSMTA / bound`）→ 寫入 CSV。

**自動不變量（每一列都要檢查，違反即中止並回報）**：
1. `TC_ILP ≤ TC_TSMTA`（OPTIMAL 時；FEASIBLE 時 `bound ≤ TC_TSMTA`）。違反表示模型、adapter 或 evaluator 有 bug。
2. ILP 解經 `check_solution` 可行，且 `evaluate().TC_int == ObjectiveValue()`。
3. 加 hint 後的初始解值（log 中第一個 solution）≤ `TC_TSMTA`（hint 可行時應相等或更好）。
4. `ratio ≥ 1`。

**Gate**：不變量全部成立；產出 `results/ratio_small.csv`。

### Phase 9：Fig. 1 驗證（等使用者提供數字）

**前置**：使用者提供每個 slot 的邊與權重後建立 `tests/fixtures/fig1.json`（節點：s、v1–v5、c1–c5、d1–d3；T=3；α=β=1；f=1）。若尚未提供，將這些測試標 `xfail(reason="waiting for Fig.1 data")` 並在 `PROGRESS.md` 註明，**不要自行猜測圖上的數字**。
**測試**：
1. 論文策略 (d)：每 slot BC = 9、RC = 6。
2. 論文策略 (e)：BC = 10/10/14、RC = 0。
3. 論文策略 (f)（TSMTA，從 c3 快取）：RC = 0。
4. ILP 最優值 ≤ 上述三策略各自的 TC（以 evaluator 計）。
5. 若與論文敘述不符（論文文字中 Fig. 1(e)/(f) 的 rerouting 說明疑有筆誤），逐項列出差異與可能原因，交使用者判斷，不要改 evaluator。

**Gate**：1–4 通過或已完整回報差異。

### Phase 10：規模探測與最終報告

- 規模探測：固定 `|D|=3,|C|=2,T=4`，逐步增加 `n_sats`（8、12、16、20、30、40），記錄 600 s 內是否證明最優、runtime、變數與限制式數量、最終 gap。找出「可證明最優」的最大規模。
- 預處理（可選，只有在 Phase 6 的測試全過之後才做，且做完要重跑 Phase 4–6 的全部測試）：刪除不在任何 `s→d` 路徑上的弧、不屬於任何 `s→c→d` 的 trunk 弧。
- 產出 `ILP_RESULTS.md`：各階段 Gate 摘要、近似比表（平均／最大／ILP 未收斂比例）、規模探測表、所有已發現的 repo 與定義差異、待使用者決策清單。

---

## 6. ILP 模型規格（CP-SAT）

### 6.1 集合

`T = 0..T-1`；`A[t] = instance.arcs[t]`；`O = {s} ∪ C`；`out[t][v]`、`in[t][v]` 為 slot t 的出／入弧索引。

### 6.2 變數（全為 BoolVar）

| 變數 | 範圍 | 意義 |
|---|---|---|
| `x[t,a]` | a∈A[t] | 弧 a 在 `T^t` 中 |
| `mu[c,t]` | c∈C | c 在 t 快取（`use_cache=False` 時不建） |
| `h[t,d,o]` | o∈O | t 時 d 由 o 供應（`use_cache=False` 時只有 o=s，可直接常數化） |
| `y[t,d,a]` | a∈A[t] | 弧 a 在 `path(d,a^t)`（origin→d）上 |
| `z[t,c,a]` | a∈A[t] | 弧 a 在 trunk `s→c` 上（無 cache 時不建） |
| `r[t,d]` | t≥1 | t 時 d 發生 reroute（β=0 時不建） |

> CP-SAT 沒有連續變數，所以 `r` 設為 BoolVar（不影響正確性）。

### 6.3 限制式

```python
# C1 恰選一個 origin
model.AddExactlyOne(h[t,d,o] for o in O)
# C2 沒快取不能當 origin
model.AddImplication(h[t,d,c], mu[c,t])           # 等價 h <= mu
# C3 y 的流量守恆（對每個 t, d, v）
#   out_y(v) - in_y(v) == (h[t,d,v] if v in O else 0) - (1 if v == d else 0)
# C4 z 的流量守恆（對每個 t, c）
#   out_z(v) - in_z(v) == (mu[c,t] if v==s else 0) - (mu[c,t] if v==c else 0)
# C5 成本綁定到 x
model.Add(x[t,a] >= y[t,d,a]);  model.Add(x[t,a] >= z[t,c,a])   # 用 AddImplication 亦可
# C6 樹：每個非根節點至多一個父節點（enforce_tree=True）
model.Add(sum(x[t,a] for a in in_arcs[t][v]) <= 1)   # for v != s
# C7 rerouting（t>=1，對 A[t] ∪ A[t-1] 中的每條弧 a；不存在於某 slot 的 y 視為 0）
model.Add(r[t,d] >= y[t,d,a] - y[t-1,d,a])
model.Add(r[t,d] >= y[t-1,d,a] - y[t,d,a])
```

### 6.4 目標式（整數）

```python
model.Minimize(
    sum(f[t] * w_int[t][a] * x[t,a] ...)
  + alpha * sum(g_int[c,t] * mu[c,t] ...)
  + beta * S * sum(r[t,d] ...)
)
```

### 6.5 實作要點

- 先斷言所有係數為 Python `int`；`beta`、`alpha` 為整數。
- 求解參數：測試用 `num_workers=1, random_seed=0`；實驗用 `num_workers=8`、`max_time_in_seconds=600`、`log_search_progress` 視需要。
- 結果狀態只接受 `OPTIMAL`（證明最優）與 `FEASIBLE`（取 `BestObjectiveBound` 計 gap）；`INFEASIBLE`、`MODEL_INVALID`、`UNKNOWN` 一律視為錯誤並回報。
- **解的讀取**：只讀 `x`、`mu`、`h`，再沿樹自行走出 `path`；**不要信任 `y`、`z`、`r` 的值**。計分一律交給 `evaluate`。這樣若 `y` 的限制有漏洞，兩邊的差異會在 `TC_int == ObjectiveValue()` 的檢查中暴露。
- 變數數估計：`T·|D|·|A|`（y）＋ `T·|C|·|A|`（z）。極小圖約數百至數千個。

---

## 7. 全域回歸與不變量

- 每個階段結束，**重跑之前所有階段的測試**（`pytest -q`），任何舊測試變紅即停。
- `PROGRESS.md` 每階段記錄累計測試數與通過數。
- 全程不變量：`evaluate(ILP解).TC_int == ObjectiveValue()`；`ILP 最優 ≤ 暴力法以外任何可行解的 TC`；`暴力法 == ILP`（OPTIMAL 時）。
- 若使用者之後更改 DEC-1 到 DEC-5 的任一項，須同步修改 `evaluate`、`brute_force`、`model_cpsat` 三處，並重跑 Phase 2–6 全部測試。

---

## 8. 失敗處理

| 現象 | 優先檢查 |
|---|---|
| ILP 值 < 暴力法 | 模型漏了限制（入度、`x ≥ y/z`、origin 必須在樹上祖先）；或暴力法漏枚舉 |
| ILP 值 > 暴力法 | 模型過度限制（flow 供應量、`h ≤ mu`）；或暴力法放寬了條件 |
| `TC_int ≠ ObjectiveValue` | 解的讀取方式；目標式漏項；β·S 的縮放；CC 的 g 單位 |
| INFEASIBLE | instance 中某 slot 的 d 不可達；單向規則刪弧後斷線；flow 供應量總和不為 0 |
| 路徑含環 | `x ≥ y` 缺漏；權重為 0 的弧（權重必須為正整數） |
| TSMTA 解不可行 | 先分類違規類型再回報；不要修補後當作正常資料 |
| 跑很慢 | 先確認是不是還沒做預處理刪弧；先降規模，不要先調參數 |

處理規則：同一個 Gate 嘗試修復最多 3 輪；仍失敗則停下，在 `PROGRESS.md` 寫明症狀、已排除的原因、最小重現 instance（存成 JSON），回報使用者。

---

## 9. 完成定義與最終回報

完成條件：Phase 0–8 的 Gate 全過、Phase 9 通過或已回報差異、`ILP_RESULTS.md` 產出。
最終對話中回報：
1. 各階段 Gate 結果一覽（通過／待確認）。
2. 近似比摘要（平均、最大、未收斂比例）與可證明最優的最大規模。
3. 發現的 repo 與定義差異清單（含 TSMTA 解不可行的統計）。
4. 仍待使用者決定的事項（至少 DEC-1 至 DEC-7，以及 Fig. 1 數據）。

---

## 附錄 A：Toy-1（手算驗證用，所有權重為整數，S=1）

節點：`s, v, c, d1, d2`；`D={d1,d2}`、`C={c}`；T=2；`f=1`；`g[(c,t)]=1`。

**Slot 0 的弧**：`s→c:2, s→v:8, v→c:1, c→d1:1, c→d2:1, s→d1:10, s→d2:10`
**Slot 1 的弧**：同 slot 0，但**沒有** `s→c`。

### A.1 手算解

| 解 | 描述 | BC | CC | RC |
|---|---|---|---|---|
| S1 | 兩 slot 都走 `s→v→c→{d1,d2}`；μ=0，origin=s | 11+11=**22** | 0 | 0 |
| S2 | slot0 走 `s→c→{d1,d2}`（4）、slot1 走 `s→v→c→{d1,d2}`（11）；μ(c,0)=μ(c,1)=1；origin=c | **15** | 2 | 0（兩 slot 的 origin→d 都是 `{c→d_i}`） |
| S3 | 與 S2 同樹；μ=0；origin=s | **15** | 0 | 2（d1、d2 的路徑在兩 slot 不同） |
| S4 | 與 S2 同樹；μ(c,0)=0、μ(c,1)=1；slot0 origin=s、slot1 origin=c | **15** | 1 | 2 |

`TC = BC + α·CC + β·RC`，期望值（evaluator 必須逐格吻合）：

| 解 | α=2, β=10 | α=2, β=1 | α=100, β=10 |
|---|---|---|---|
| S1 | 22 | 22 | 22 |
| S2 | **19** | 19 | 15+200+0=215 |
| S3 | 15+0+20=35 | 15+2=17 | 35 |
| S4 | 15+2+20=37 | 15+2+2=19 | 15+100+20=135 |

### A.2 必須被拒絕的變體（`check_solution`）

- S2 但 `origin[(d1,0)]=c` 而 `mu[(c,0)]=0`。
- S2 但 slot1 的樹少了 `v→c`（c 不在樹中，卻 μ=1）。
- 在 slot0 同時放 `s→c` 與 `v→c`（c 入度 2）。

### A.3 全域最優值（暴力法與 ILP 必須相等）

| α | β | 最優 TC | 最優解型態 |
|---|---|---|---|
| 2 | 0 | 15 | 兩 slot 各自最便宜樹，無 cache（S3 型，RC 不計價） |
| 2 | 1 | 17 | S3 型（15+2） |
| 2 | 2 | 19 | S2 與 S3 型並列（19） |
| 2 | 10 | 19 | S2 型（用 cache 換掉 RC） |
| 2 | 100 | 19 | S2 型 |
| 100 | 10 | 22 | S1 型（不用 cache、不切換路線） |
| 100 | 100 | 22 | S1 型 |

`C=∅`（或 α 極大）時，最優 = min(22, 15+2β)：β=0 → 15、β=1 → 17、β=2 → 19、β=3 → 21、β≥4 → 22。

> 手算依據：cache 的價值在於「s→c 的 trunk 在兩個 slot 不同，但 c→d 的下游路徑不變」。slot1 沒有 `s→c`，trunk 必須繞 `s→v→c`；不用 cache 時要嘛兩 slot 都繞遠路（22），要嘛切換路線付 2β。若 `s→d_i` 直連（10）也不划算：兩個目的地直連 BC = 20，高於任何一組含 c 的樹（4 或 11）。若實作的最優值與此表不同，**先檢查 Toy-1 的手算是否有誤，再檢查程式**，兩邊都要有結論後才能繼續。

## 附錄 B：Toy-2（共用 link 只算一次）

節點：`s, a, d1, d2`；T=1；C=∅；α、β 任意。
弧：`s→a:2, a→d1:2, a→d2:2, s→d1:5, s→d2:5`。
最優解：樹 `{s→a, a→d1, a→d2}`，**BC = 6**（若把共用弧按每個目的地各計一次會得到 8，代表成本算錯位置）。

## 附錄 C：隨機極小圖產生器規格（`gen_random.py`）

- 參數：`n_nodes ∈ [5,7]`、`|D| ∈ [1,3]`、`|C| ∈ [0,2]`、`T ∈ [1,3]`、`seed`。
- 每個 slot 以機率 0.5 加入一般節點間的雙向弧，另加入 `s→任意非 D 節點`、`任意非 s 節點→d` 的單向弧；權重為 1–9 的隨機整數；每個 slot 的弧集合與權重需有差異（至少改變 1–2 條弧，才會測到 rerouting）。
- 產生後必須通過 `validate_instance`（可達性不過就丟棄重抽，並計數）。
- 同一 seed 永遠產生相同 instance；測試使用的 seed 範圍寫在測試檔頂端。