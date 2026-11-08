# ILP 實作進度紀錄

指令皆在 repo 根目錄執行：`PYTHONUTF8=1 ./.venv_ilp/Scripts/python.exe -m pytest -q tests`

## 待確認決策（目前皆採 PLAN 預設值）
DEC-1（origin 可為任意 μ=1 祖先）、DEC-2、DEC-3、DEC-4、DEC-5、DEC-6、DEC-7 —— **待確認**。

## 環境備註
- `.venv_ilp/` 尚未列入 `.gitignore`（PLAN 規定不得改既有檔案；請使用者自行加入 `.venv_ilp/`）。
- `.venv_ilp` 只裝了 ortools、networkx、pytest；repo 既有程式需要 numpy/matplotlib/pandas 等，本機系統 Python（3.12.3）已有，Phase 7 的 adapter 需用系統 Python 或在 venv 補裝（待 Phase 7 決定）。
- `fig1.json` 目前放在 `ilp/tests/fixtures/fig1.json`（PLAN 預期在 `tests/fixtures/`），Phase 9 再處理。

---

## Phase 0：環境與 CP-SAT 熟悉（2026-10-10）
- Python 3.12.3、ortools 9.15.6755、networkx 3.7、pytest 9.1.1（皆在 `.venv_ilp`）。
- 測試：`tests/test_phase0_smoke.py`，52 通過／52。涵蓋：x+y≥1 最小化、30 張隨機圖最短路徑對 networkx、20 個背包對暴力、`StatusName/ObjectiveValue/BestObjectiveBound/AddHint/Validate` 皆可用。
- Gate：通過。

## Phase 1：Instance / Solution / 驗證 / JSON（2026-10-10）
- 檔案：`ilp/instance.py`、`ilp/gen_random.py`（附錄 C 產生器，提前於此階段寫以供 round-trip 測試）、`ilp/make_toys.py`（產生 `tests/fixtures/toy1.json`、`toy2.json`）。
- 測試：`tests/test_phase1_instance.py`。累計 86 通過／86。round-trip（Toy-1、Toy-2、隨機 seed 0–19）全相等；11 種違規 instance（入 s 的弧、離開 d 的弧、非整數 β/α、不可達 d、C∩D、零權重、浮點權重、負 g、缺 g、未知節點）皆被拒絕。
- Gate：通過。

## Phase 2：獨立 evaluator（2026-10-10）
- 檔案：`ilp/evaluate.py`（`check_solution / evaluate / prune / build_solution / relabel / evaluate_repo_compat`）、`ilp/baseline.py`（最短路徑樹可行解）。未 import ortools，亦未 import repo 演算法。
- 測試：`tests/test_phase2_evaluate.py`、`tests/test_evaluate_repo_compat.py`。累計 221 通過、10 skipped（skip 來自「額外葉弧」性質測試中，該隨機圖已無可加的葉弧，共 10/40 個 seed）。
  - Toy-1 的 S1–S4 在 (α,β)=(2,10)、(2,1)、(100,10) 與附錄 A.1 手算表逐格相等（BC/CC/RC/TC）。
  - Toy-2 BC=6。
  - 不可行解被拒絕且代碼正確：INDEGREE、CYCLE、ARC_NOT_IN_SLOT、DEST_MISSING、MU_NOT_IN_TREE、ORIGIN_MU0、ORIGIN_NOT_ANCESTOR、UNREACHABLE，以及 A.2 的三個變體。
  - 性質（seed 0–39）：多加葉弧 BC 增加且 pruned 不變；權重／g／S 同乘 7 則 TC_int 同乘 7；節點更名不變。
  - repo_compat 回歸：fixture 由 scratchpad 副本重跑（`tiny` 設定，seed 42，α=5，β=10，k=2）產生，**完全重現**報告數字：Raw (51.2366, 1.7241, 2.0, 79.8572)、Optimal (51.2975, 0.8621, 1.5, 70.6078)，也與 `TVM.evaluate_algorithm` 的輸出一致（誤差 <1e-9）。
- 備註：fixture 假設 src 的 `data_size=1.0`（報告所述）；g 值直接取自 `Algorithm.cost_cache(..., α=1)`。
- Gate：通過。

## Phase 3：暴力精確解（2026-10-10）
- 檔案：`ilp/brute_force.py`（逐 slot 窮舉「樹 × μ × origin」，以路徑集合簽章合併，再 DP 跨 slot；`solve_exhaustive` 為不經 DP 的笛卡兒積對拍）。修剪論證寫在檔頭註解。
- 測試：`tests/test_phase3_brute.py`。累計 296 通過、10 skipped。
  - Toy-1 附錄 A.3 七格全部吻合（15/17/19/19/19/22/22）；`C=∅` 時 β=0..6 吻合 min(22, 15+2β)；Toy-2 = 6。
  - 回傳解 `check_solution` 可行且 `evaluate` 的 TC_int 等於 DP 值；30 張隨機圖（T=2，use_cache 真／假各一次）DP == 笛卡兒積窮舉。
- Gate：通過。

## Phase 4：ILP 單 slot 無 cache（2026-10-10）
- 檔案：`ilp/model_cpsat.py`（Phase 4–6 的模型一次寫完，以 `use_cache`、`enforce_tree` 控制；各階段測試依序執行）。
- 與 PLAN 第 6 節的差異：多加整數變數 `depth[t,v]` 與 `x ⇒ depth[v] ≥ depth[u]+1`（僅 `enforce_tree`）。理由：只有入度 ≤1 時，x 可含一個與 s 斷開的環，y 可沿該環加 circulation，理論上能「墊高」y 使兩 slot 路徑集合看似相同而少付 β。**我沒有找到實際會出錯的實例**（拿掉 depth 後 300 張隨機圖最優值皆相同），所以這是防禦性約束，不是被測試證實的修正；若覺得多餘可移除（需重跑 Phase 4–6）。
- 測試：`tests/test_phase4_ilp_single.py`，51 通過。Toy-2 = 6；50 張隨機圖 ILP == 暴力法；每個解 `check_solution` 可行、`evaluate().TC_int == ObjectiveValue()`、`Validate()==""`、OPTIMAL。
- Gate：通過。

## Phase 5：多 slot 無 cache + rerouting（2026-10-10）
- 測試：`tests/test_phase5_ilp_reroute.py`，累計 216 個測試（本檔）通過。Toy-1 `C=∅` β=0/1/2/3/10 → 15/17/19/21/22；100 張隨機（T=2–3，β∈{0,1,5,50}）ILP == 暴力。
- 發現：原產生器的 slot 間擾動太小，100 張中只有 13 張最優解 RC>0，rerouting 測不夠。我在 `gen_random.gen_instance` 加了選用參數 `n_change`（預設行為與 seed 對應不變），另加 80 張「大擾動」隨機圖（β∈{0,1,2,3}），至少 10 張最優解 RC>0（有測試斷言）。
- 性質：β=0 時等於各 slot 獨立最優值之和（15 張）；β 遞增 TC 不減、RC 不增；β 極大時 RC 等於暴力法最優解的 RC（各 15 張）。
- Gate：通過。

## Phase 6：加入 cache（2026-10-10）
- 測試：`tests/test_phase6_ilp_cache.py`。全部測試累計 836 通過、10 skipped。
  - Toy-1 附錄 A.3 七格全部吻合。
  - 150 張隨機圖（|C|=1–2，T=2–3，α∈{1,5}，β∈{0,1,5,50}）＋60 張大擾動圖：ILP == 暴力法。最優解實際使用 cache 的實例 ≥10 張（有斷言）。
  - 性質（40 張）：cache 最優 ≤ 無 cache；α=10^6 時 μ 全 0 且值等於無 cache；β=0 時值等於無 cache；`enforce_tree=False` ≤ `enforce_tree=True`。穩定性（15 張）：`workers=1,seed=0` 與 `workers=8,seed=7` 最優值相同。
- 測試自身的錯誤：原本「α 極大 ⇒ μ 全 0」未排除 g=0 的 cache（免費 cache 在平手時可被選），6 個 seed 失敗。這是性質陳述不精確而非模型錯誤，已改為先把 g 設成 ≥1 再測。沒有放寬任何期望值。
- Gate：通過（ILP 模型正確性最終判定）。

## Phase 7：Adapter（2026-10-10）
- 檔案：`ilp/adapter.py`（`from_existing`、`from_tsmta_output`）。呼叫鏈同 `main.py`：`Build_TIG_CTIG → Run_TSMTA_Select → copy_tree_sequence → expand_virtual_edges → [Optimal]`，`n_clouds=0`，k=2。`.venv_ilp` 另補裝 numpy/pandas/openpyxl/matplotlib/scipy/psutil 以便 import repo（不影響 repo 檔案）。
- 實作注意：`main.Build_TIG_CTIG` 會無視傳入的 `caches`，改讀 `graphs[0]` 節點的 `cache` 屬性，所以 adapter 在**複製後的圖**上把 `cache` 屬性改成恰好等於抽出的 C（repo 檔案未動）。
- 測試：`tests/test_phase7_adapter.py`（seed 42–61，20 個，n_c=1 或 2）。4 通過。
  1. instance 皆通過 `validate_instance`：無進入 s／離開 D 的弧、每 slot 全可達、|C| 正確。
  2. 量化誤差（S=10^5）：最大絕對誤差 5.0e-6（≤0.5/S）；最大相對誤差 **6.9e-5**，比報告 D10 的 1.6e-5 大，原因推測為此處弧權重更小（單向規則刪弧後、n_clouds=0），相對誤差由小權重主導（推測，未另行驗證）。
  3. 20 個 seed × {Raw, Optimal} × {μ 推導, flag 旗標} 的 TSMTA 解全部通過 `check_solution`（0 個違規）。
  4. Solution JSON 儲存再讀回相等，`evaluate` 結果不變。
  - 重抽：因刪弧使 D 不可達而換 seed 的次數，20 seed 中平均約 2.8 次、最多 25 次（見 Phase 8 的 `redraws` 欄）。
- Gate：通過（第 3 項結果：20/20 可行；但 Phase 8 的較大實例出現不可行，見下）。

## Phase 8：暖啟動與近似比實驗（2026-10-10）
- 檔案：`ilp/model_cpsat.add_hint`（x, mu, h, y, z, r, depth 全部提供）、`ilp/run_ratio.py`、`ilp/summarize.py`。
- 指令：`PYTHONUTF8=1 ./.venv_ilp/Scripts/python.exe -m ilp.run_ratio --seeds 20 --jobs 10 --workers 2 --out results/ratio_small.csv`，約 90 秒。
- 網格：n_sats∈{8,12,16,20}（num_planes=4）× |D|∈{2,3} × |C|∈{1,2} × T∈{3,4} × (α,β)∈{(1,100),(5,10)} × 20 seed（42–61）＝1280 列；S=10^5；TSMTA k=2；`n_clouds=0`。
- 單元測試 `tests/test_phase8_hint.py`：40 張隨機圖，以最短路徑解與暴力最優解當 hint，第一個解的目標值 ≤ hint 的 TC（皆通過）。
- 不變量：**1280 列全部通過**（OPTIMAL 時 TC_ILP ≤ TC_TSMTA；ILP 解可行且 `evaluate().TC_int == ObjectiveValue()`；hint 後首個解 ≤ TSMTA；ratio ≥ 1）。ILP 1280/1280 皆 OPTIMAL，單次最長 0.12 秒；hint 與否的最優值 100% 相同（hint 對速度無可見影響，因為本來就瞬間解完）。
- **發現：TSMTA 輸出不可行**。1280 列中 Raw 189 列（14.8%）、Optimal 189 列不可行；違規類型 Raw：UNREACHABLE 189；Optimal：UNREACHABLE 188 + DEST_MISSING 1。例：n_sats=20, |D|=3, |C|=2, T=4, seed=42, (α,β)=(1,100)：最後一個 slot 的樹有 7 條弧與 8 個節點跟 s 斷開（到 cache v19/v20 的 trunk 沒有接上 s）。最小重現檔（instance／solution／違規訊息）在 `results/tsmta_infeasible/`。未做任何修補。**原因未查明**：未驗證是否與本計畫的單向刪弧／覆寫 cache 集合有關，也未在 repo 原始（雙向）圖上比對。
- 近似比（只含 TSMTA 可行的列，即有倖存者偏誤；Optimal，TC_TSMTA/TC_ILP）：整體平均 1.137、最大 2.055；(α,β)=(1,100) 平均 1.070／最大 1.876；(5,10) 平均 1.196／最大 2.055；Raw 平均 1.136／最大 2.248。約 73–76% 的實例 TSMTA 嚴格劣於最優。依 n_sats：8→1.129、12→1.123、16→1.128、20→1.173。
- Gate：通過（不變量全成立，`results/ratio_small.csv` 已產出）。

## Phase 9：Fig. 1 驗證（2026-10-10）
- 資料：使用者提供的 `ilp/tests/fixtures/fig1.json`（由截圖重建；PLAN 預期放 `tests/fixtures/`，我沒有搬動它，測試直接讀原位置）。fixture 的 `g` 未定（`g_unknown`），測試以**假設** g=0 與 g=1（每個 (c,t)）、α=β=1 執行；BC／RC 的檢查與 g 無關。
- 測試：`tests/test_phase9_fig1.py`，7 通過。
  1. 策略 (d)：每 slot BC=9、RC=6。吻合。
  2. 策略 (e)：BC=10/10/14、RC=0。吻合。
  3. 策略 (f)：RC=0；CC=3g。吻合。三個策略都通過 `check_solution`。
  4. ILP 最優 ≤ 三策略的 TC：g=0 時 ILP=30，策略 (d)(e)(f)=33/34/30；g=1 時 ILP=32，策略=33/34/33（此時 ILP 比論文的 (f) 便宜 1）。
- 與論文敘述不符處：fixture meta 已指出 Example 1 的 c1 快取成本寫成 +1（22=5+7+9+1），但 W(e_{s,c}) 公式每 slot 各加 αg，三個 slot 應為 +3。我沒有論文原文，未重查；g 的設定仍待使用者確認。fixture 的 v 鏈弧權重（2–4 皆通過檢查，取 3）亦屬重建值。
- Gate：通過。

## Phase 10：規模探測（2026-10-10）
- 指令：`python -m ilp.scale_probe --n-sats 8 12 16 20 30 40 60 80 100 150 200 300 --seeds 5`（|D|=3、|C|=2、T=4、num_planes=4、(α,β)∈{(1,100),(5,10)}、每組 5 seed、時限 600 s、4 workers）。每個解皆通過 `check_solution` 且 `TC_int == ObjectiveValue()`。
- 結果：全部 120 個實例在 6.2 秒內證明最優（gap=0）；n_sats=300 時平均 4.6 秒、約 1.7 萬個變數、3.5 萬條限制式。因此「可證明最優的最大規模」在本掃描範圍內沒有找到上限（未測 n_sats>300，也未測 |D| 大於 3）。
- 預處理（刪除不在任何 s→d 路徑的弧）：未做（選用項目，現況已不需要）。

## Phase 12：DEC-2 改為「cloud 算 cache，與 repo 一致」（2026-10-12，使用者已確認）
注意：本環境沒有 TaskCreate 工具，任務清單改以本節逐步紀錄代替。PLAN.md 的 DEC-2 已改寫。

### 步驟 1：adapter `cache_mode`
- `from_existing(..., cache_mode="repo"|"sample")`，預設 `"repo"`：C = 圖上 `cache` 屬性為 True 的節點（全部 cloud + 被 repo 標為 cache 的衛星，排序後使用）；不改寫圖屬性，`n_c` 被忽略。`"sample"` 維持原行為（`n_clouds=0`、抽 `n_c` 個、覆寫複本的 cache 屬性）。`from_tsmta_output` 新增斷言：傳給 `Build_TIG_CTIG` 的圖上 cache 屬性集合必須等於 `inst.C`。
- `inst.meta` 新增 `cache_mode, C_size, n_cloud_in_C, n_sat_in_C`。`g[(c,t)]` 仍逐節點逐 slot 由 `Algorithm.cost_cache(filtered[t].nodes[c], …)` 讀取。
- 舊呼叫點（`tests/test_phase7_adapter.py`、`ilp/rescore_repo.py`）明確加上 `cache_mode="sample"` 以保留原語意（未改期望值）。
- 測試：`tests/test_phase12_cache_mode.py` 31 通過。(1) C == 重新生成之原圖的 cache 屬性集合，且每個 slot 每個節點的 cache 屬性未被改動、所有 cloud 都在 C；(2) g 手算核對：seed 42 的 v0(cloud)=105785、v10(衛星)=149146、v14(衛星)=99759；seed 43 的 v1(cloud)=261671、v8(衛星)=96116、v17(衛星)=218734（cloud: d；衛星: 1.5·d），並以原始屬性公式驗證每個 (c,t)；(3) sample 模式對 `results/ratio_small.csv` 抽樣 13 列（含 2 列 TSMTA 不可行）：n_nodes/n_arcs/redraws、可行旗標、TC_raw、TC_opt、TC_ilp 完全相同；(4) validate_instance、單向規則、可達性在 n_clouds∈{1,2,5} × 3 seeds 成立。
- 觀察（非推論）：節點屬性不隨 slot 變，所以同一節點的 g 在各 slot 相同；不同節點（cloud vs 衛星、不同 d）的 g 不同。
- Gate：通過。

### 步驟 2：ILP 對不均勻 g
- 檢查：`gen_random.gen_instance` 已對每個 (c,t) 獨立抽 g∈{0,1,2,3}，不需擴充。
- 測試：`tests/test_phase12_g_nonuniform.py` 102 通過：seed 5000–5099（|C|∈{1,2}、T∈{2,3}、|D|∈{1,2}）ILP == brute_force（含 check_solution、TC_int == ObjectiveValue、Validate()==""）；≥80/100 張的 g 值不全相同；g 全體加 10^6 時最優值不下降。
- 全部測試：`PYTHONUTF8=1 .venv_ilp/Scripts/python.exe -m pytest -q` → **1020 通過、10 skipped**（skip 同 Phase 2）。
- Gate：通過。

### 步驟 3：近似比重跑（cache_mode="repo"）
- 指令：`PYTHONUTF8=1 .venv_ilp/Scripts/python.exe -m ilp.run_ratio --seeds 20 --jobs 10 --workers 2 --out results/ratio_cloud.csv --dump-dir results/tsmta_infeasible_cloud`；統計：`python -m ilp.summarize_cloud results/ratio_cloud.csv`。
- 網格：n_sats∈{8,12,16,20} × n_clouds∈{1,2,5} × |D|∈{2,3} × T∈{3,4} × (α,β)∈{(1,100),(5,10)} × 20 seed（42–61）＝**1920 列**；k=2；S=10^5。新增欄位 `n_clouds, cache_mode, C_size, n_cloud_in_C, prune_feasible_*, dest_disconnected_*`。C_size 平均 11.0（n_clouds=1/2/5 時平均 9.3/10.6/13.2；範圍 3–22）。
- 問題與處理（第一次執行中止）：1000 列左右 `from_tsmta_output` 的 `assert "virtual edge left"` 觸發，整批中止。這是 TSMTA 輸出（Optimal 路徑展開後仍殘留虛擬邊）而非 ILP 問題；改為 `collect_errors=True` 時把該解記為不可行（違規類型 `VIRTUAL_EDGE_LEFT`），不修補、不重試。另發現 dump 檔名未含 n_clouds 會互相覆蓋，已加 `_cl{n_clouds}`。修正後重跑，兩次結果（除 runtime）逐欄相同。
- Gate：**不變量 1920 列全部成立**（TC_ILP ≤ TC_TSMTA、ILP 解可行、`evaluate().TC_int == ObjectiveValue()`、hint 後首解 ≤ TSMTA、ratio ≥ 1）；ILP **1920/1920 皆 OPTIMAL**（未收斂 0%），最長 0.93 s。
- 近似比（只含 TSMTA-Optimal 可行的 1517 列；與 n_clouds=0 的 Phase 8 對照：平均 1.137／最大 2.055）：整體平均 **1.303**、最大 **2.971**，96.2% 的列嚴格 >1。
  - 依 (α,β)：(1,100) n=706 平均 1.084／最大 1.680；(5,10) n=811 平均 1.493／最大 2.971。
  - 依 n_clouds：1→1.280／2.762，2→1.321／2.936，5→1.308／2.971。
  - 依 C_size：≤8→1.241／2.936，9–12→1.313／2.728，13–16→1.354／2.971，≥17→1.359／2.147。
  - 依 n_sats：8→1.253，12→1.287，16→1.342，20→1.358。Raw 的平均／最大見 `summarize_cloud` 輸出（與 Optimal 接近）。
- TSMTA 不可行：Raw **20.94%**（402/1920）、Optimal **20.99%**（403/1920）；n_clouds=0（Phase 8）為 14.8%（189/1280）。
  - 依 (α,β)：(1,100) 26.4%；(5,10) 15.5%。依 n_clouds：1→19.1%、2→20.5%、5→23.4%。依 C_size：≤8→5.0%、9–12→20.6%、13–16→31.8%、≥17→39.8%。依 n_sats：8→3.5%、12→12.1%、16→30.0%、20→38.3%。依 |D|：2→14.9%、3→27.1%；依 T：3→17.7%、4→24.3%。
  - 原因分類：Raw 402 列全為 UNREACHABLE。Optimal：UNREACHABLE 399、DEST_MISSING 6（其中 3 列同時有 UNREACHABLE）、VIRTUAL_EDGE_LEFT 1。
- prune 診斷（僅診斷，未併入主表）：Raw 402 列中 **1 列**、Optimal 403 列中 **1 列**在 `prune` 後變可行；其餘 401 列 `prune` 本身拋 KeyError（路徑／trunk 走到不在 s 連通分量內的節點），這 401 列都有目的地在樹中與 s 斷開，prune 只刪弧所以不可能修復。（Optimal 另有 1 列為 VIRTUAL_EDGE_LEFT，無解可 prune。）

### 步驟 4：cache_mode 對 TSMTA 不可行比例（只報數字，不推論原因，也未修補 TSMTA／adapter）
- 指令：`... -m ilp.run_ratio --seeds 20 --jobs 10 --workers 2 --n-clouds 0 --cache-mode repo --out results/ratio_repo_nocloud.csv`（640 列，不變量全成立）；比較：`python -m ilp.summarize_cloud compare results/ratio_small.csv results/ratio_cloud.csv results/ratio_repo_nocloud.csv`。
- Optimal 不可行率：sample（n_clouds=0，|C|=n_c；1280 列）**14.77%**（n_c=1：12.8%、n_c=2：16.7%）；repo 且 n_clouds=0（C=repo 標為 cache 的衛星；640 列）**17.19%**；repo 且 n_clouds∈{1,2,5}（1920 列）**20.99%**。
- 同一張圖（相同 n_sats、|D|、T、α、β、seed，n_clouds=0）逐格配對 640 格：sample 14.77% vs repo 17.19%；sample 較高 38 格、repo 較高 54 格、相同 548 格。
- 依 n_sats（sample / repo-n0 / repo-cloud）：8→5.0/4.4/3.5%，12→12.2/13.8/12.1%，16→16.3/21.3/30.0%，20→25.6/29.4/38.3%。依 (α,β)：(1,100) 20.0/24.1/26.5%，(5,10) 9.5/10.3/15.5%。

### 步驟 5：規模探測（cache_mode="repo"；|D|=3、T=4、num_planes=4、(α,β)∈{(1,100),(5,10)} × 5 seed＝每種 10 個實例，時限 600 s，4 jobs × 4 workers）
指令：`python -m ilp.scale_probe --n-sats ... --n-clouds {5|20} --seeds 5 --jobs 4 --workers 4 --time-limit 600`。結果：`results/scale_probe_cloud5_all.csv`、`results/scale_probe_cloud20_final.csv`（300 衛星那組為重跑；原始輸出在 `scale_probe_cloud5*.csv`、`scale_probe_cloud20.csv`）。

n_clouds=5：
| n_sats | C_size 平均 | 變數 | 限制式 | OPTIMAL/10 | 最長求解(s) | 最大 gap |
|---|---|---|---|---|---|---|
| 8 | 9.2 | 1,780 | 3,113 | 10 | 0.06 | 0 |
| 20 | 16.4 | 4,938 | 8,248 | 10 | 0.19 | 0 |
| 40 | 29.0 | 13,422 | 21,519 | 10 | 0.62 | 0 |
| 100 | 60.2 | 59,626 | 91,342 | 10 | 22.6 | 0 |
| 200 | 116.6 | 216,502 | 324,515 | **5** | 603 | 4.4% |
| 300 | 176.8 | 481,215 | 715,279 | **0** | 608 | 35.9% |

n_clouds=20（論文設定）：
| n_sats | C_size 平均（範圍） | 變數 | 限制式 | OPTIMAL/10 | 最長求解(s) | 最大 gap |
|---|---|---|---|---|---|---|
| 50 | 50.2（41–56） | 34,214 | 52,862 | 10 | 2.6 | 0 |
| 100 | 76.6（66–83） | 87,675 | 132,162 | 10 | 101.6 | 0 |
| 300 | 191.4（179–205） | 565,532 | 830,807 | **0** | 617 | 55.1%（中位 24.8%） |

- 「可證明最優」的最大規模：n_clouds=5 時 n_sats≈100 全部證明、200 約一半；n_clouds=20 時 n_sats=100（C≈77）全部證明、300 全部未證明（gap 大，(5,10) 組尤其大）。
- 問題 1：第一次 n_clouds=5、n_sats=300 的批次中有 1 個實例 CP-SAT 在 600 s 內沒有找到任何可行解（UNKNOWN），`solve()` 拋 RuntimeError 使批次中止；`scale_probe` 改為記錄 UNKNOWN 並繼續。重跑後該組 10 個實例皆為 FEASIBLE（多 worker 求解不具決定性）。
- 問題 2（**未解決，需使用者知悉**）：n_clouds=20、n_sats=300 的第一次批次中，10 個實例有 **2 個**（seed 44 (1,100)；seed 43 (5,10)）的 `consistent=0`，即該 FEASIBLE 解未通過 `check_solution`或 `evaluate().TC_int != ObjectiveValue()`；當時沒有存下解與原因。之後：(a) 以 `ilp.diagnose_inconsistent` 重解這兩個實例（8 workers）→ 0 違規、TC_int == ObjectiveValue；(b) 整組重跑 10 個實例（已加入不一致時自動 dump 的程式）→ 10/10 一致。共 12 次重試皆未重現，**原因不明**（不排除與時限到時取出的未證明最優解、或當時並行負載有關，但未驗證）。已達 3 輪，依 PLAN 第 8 節停止，不再追查。所有 OPTIMAL 的實例（含 Phase 12 步驟 3 的 1920 列）不變量皆成立；此現象只在 n_sats=300 的 FEASIBLE 解出現過。
- 全部測試（含新增 Phase 12 測試）：**1020 通過、10 skipped**。未改 evaluate／brute_force／model_cpsat，repo 既有檔案未動。

## Phase 13：TSMTA 不可行的成因與 adapter 端修補（2026-10-13）

### 步驟 1：成因（診斷腳本只讀 repo，未改任何 repo 檔）
- 方法：把 TSMTA 拆成「選樹（`TVM.TSMTA` 內把 CTIG 邊展開成實體路徑）」與「`expand_virtual_edges`」兩段，各自檢查每個 slot 的樹是否所有節點從 s 可達。實例：n_sats∈{8,12,16} × n_clouds∈{0,1} × |D|∈{2,3} × T∈{3,4} × (α,β)∈{(1,100),(5,10)} × 10 seed＝480 個，cache_mode="repo"。
- 結果：60/480 失敗，**選樹階段 18、展開虛擬邊階段 42**，`Optimal` 沒有造成新的不可行（0）。60 個全部符合同一機制，沒有例外。
- 機制：TSMTA 對每條 CTIG 邊／虛擬 s→c 邊各自取一條最短實體路徑，再併成同一棵樹。各路徑對同一節點的上下游方向不一致時，併入時的兩條防護（「節點已有 parent 就跳過」「加邊會成環就跳過」，`TVM.py` 展開迴圈與 `expand_virtual_edges`）會把唯一能接回 s 的那條邊丟掉，cache 變成沒有 parent 的孤兒，底下的子樹與 destination 全部從 s 斷開，即 `UNREACHABLE`。
  - 展開虛擬邊例（n_sats=8, |D|=2, T=3, seed=57, α=1, β=100）：樹含 s→v7、v7→v3；slot 1 起 s→v7 的最短路徑改成 s→v3→v7，v3 是 v7 的子孫，s→v3 因 v3 已有 parent 被跳過，v3→v7 因成環被跳過，v7 無 parent。
  - 選樹階段例（n_sats=8, |D|=3, T=4, seed=45, α=1, β=100）：CTIG 邊 v0→v4 展開成 v0→v8→v4，同一棵樹的 v4→v3 展開成 v4→v8→v3，v8 先掛在 v4 下，v0→v8 與 v8→v4 都被跳過，v4 成孤兒。
  - 機器檢查：所有 60 個失敗的孤兒根，其展開路徑都穿過它自己的子孫。
- 圖的角色：圖只提供觸發條件（ISL 為雙向、各 slot 拓撲不同使最短路徑換路），所以失敗率隨 n_sats、C_size、T 上升。每個失敗實例的 ILP 都有可行解，不是無解。
- 與論文的關係：Definition 1 要求每個 destination 有路徑連到 s 或 cache、每個存內容的 cache 有路徑連到 s，所以不可行輸出不是論文意義下的解。論文可行性只要求連通，成本是對連結集合加總；沒有規定入度為 1，也沒說明展開時路徑衝突如何處理。入度為 1 與環防護是 repo 的實作選擇。

### 步驟 2：先前實驗為什麼沒發現
- **原始（未刪弧）的 repo 圖上同樣發生**，所以不是 adapter 單向刪弧造成。照 `main.py` 流程（未過濾圖、destination 取 `nx.has_path` 可達者、TSMTA-Raw）跑：
  - n_sats=20、n_clouds=1、|D|=3、T=4、10 seed：6/10 個 run 至少一個 slot 斷開，40 個 slot 中 13 個、120 個 (destination, slot) 中 39 個不可達。
  - n_sats=50、n_clouds=5、|D|=10、T=5、num_planes=8、5 seed：4/5 個 run 斷開，25 個 slot 中 7 個、250 個 (destination, slot) 中 64 個不可達。
  - 非論文實驗規模（無法在此跑 n_sats=300／|D|=100），只證明在原始圖上也會發生。
- **repo 的評估器看不到**：`TVM.evaluate_multicast_algorithm` 對 TSMTA 用 `BC_multicast_cache_aware`，只從 src 做 DFS 計費，孤兒弧與斷開的 destination 不被計入，也沒有可達性檢查；`RC` 的 `_dest_effective_edges` 沿 parent 往上走到沒有 parent 就停。因此不可行的樹得到一個偏低的成本。同一批原始圖樹，修補後用 repo 自己的評估器重算：Total 由 49.0→58.4、38.3→44.2、33.2→45.6、29.4→42.5（tiny，6 個斷開的 run），109.2→116.4、119.7→133.7、112.7→117.4、99.1→102.2（mid，4 個）；BC 增加是因為斷開的 destination 原本沒被計費。也就是說先前 TSMTA 的成本在這些 run 上被低估。
- **baseline 沒有這個問題**：SSSP／DMTS 在 10 seed × 4 slot（n_sats=20, |D|=3）的 40 個 slot 全部連通。兩者都是以 s 為根的最短路徑聯集，不需要把獨立路徑再拼成一棵樹。
- ILP 端能發現，是因為 `check_solution` 明確檢查 `UNREACHABLE`、`INDEGREE`、`CYCLE`。
- 未驗證：論文規模（n_sats=300、|D|=100、T=10）的失敗率，以及先前論文圖表中 TSMTA 數字被低估的幅度。

### 步驟 3：adapter 端修補（`ilp/adapter.py`；repo 其他檔案未動）
- 新增 `repair_connectivity(trees, graphs_filtered, s)`；`from_tsmta_output(..., repair=False)` 新參數，預設關閉，舊行為不變。開啟時在 `expand_virtual_edges` 後（Raw），以及 `Optimal` 前後（Optimal）各修補一次，補的弧數放在 `out["repairs"]`。
- 做法（TSMTA 選哪些 cache／destination 都不動）：對每個 slot，(1) 入度 0 的孤兒根，從已連通部分用該 slot 圖的最便宜路徑接過去，中繼點只能是樹外的新節點，入度維持 1、不會成環；(2) 若根只能經過自己的子樹才連得到，或整塊是環（沒有根），把能接上的未連通節點改接到連通側並移除它原本的入弧。補上的弧都是該 slot 真實圖中的弧，計入 BC。
- 480 個實例（上列網格）驗證：Raw、Optimal 各由 60 個不可行降為 0；原本可行的 420＋420 個解 `TC_int` 完全不變。
- `ilp/run_ratio.py` 新增 `--repair`：額外跑一次帶修補的 TSMTA，新增欄位 `rep_raw_feasible, rep_opt_feasible, TC_raw_rep, TC_opt_rep, ratio_raw_rep, ratio_opt_rep, repair_arcs_raw, repair_arcs_opt`；原有欄位仍是未修補結果。修補後的 TC 若低於 ILP 最優值或仍不可行，記為 `invariant_errors`。

### 步驟 4：近似比重跑（修補前／後，與 ILP 比較）
- 指令：`PYTHONUTF8=1 .venv_ilp/Scripts/python.exe -m ilp.run_ratio --seeds 20 --jobs 10 --workers 2 --repair --out results/ratio_cloud_repair.csv --dump-dir results/tsmta_infeasible_cloud_repair`；網格同 Phase 12 步驟 3（1920 列）。
- 不變量 1920 列全部成立；ILP 1920/1920 OPTIMAL；沒有任何一列「修補後 TC < ILP 最優」。
- 可行性：Raw 不可行 402（20.94%）→ 0；Optimal 403（20.99%）→ 0，另 **1 列 Optimal 為 `VIRTUAL_EDGE_LEFT`（Optimal 後殘留虛擬邊，無樹可修補），仍無結果**，所以修補後 `ratio_opt_rep` 有 1919 列。被修補的 402 列正好是原本不可行的 402 列，平均補 5.4 條弧。
- 近似比（Optimal，TC_TSMTA/TC_ILP）：修補前只含可行列（1517 列）平均 1.303、最大 2.971；修補後全部（1919 列）平均 1.289、中位數 1.176、最大 6.286。原本就可行的 1517 列修補後仍是平均 1.303。原本不可行、修補後才有值的 402 列：平均 1.236、中位數 1.051、最大 6.286。Raw 修補後平均 1.298、最大 6.286。96.4% 的列嚴格 >1。
- 依 n_sats（修補前→後平均）：8: 1.253→1.252；12: 1.287→1.284；16: 1.342→1.286；20: 1.358→1.332。依 α：α=1: 1.084→1.089；α=5: 1.493→1.488。
- 解讀限制：修補後的數字是「TSMTA 加上接回 s 的最便宜路徑」，**不是論文中 TSMTA 的近似比**，報告時必須標註含 adapter 修補。補回的 402 列平均較好（1.236 < 1.303）是這些列的組成所致，不代表修補讓 TSMTA 變好；先前只算可行列的近似比有倖存者偏誤。最大值從 2.971 變成 6.286，表示有少數實例的 TSMTA 展開結果離最優很遠，尚未逐例檢查是修補還是 TSMTA 本身造成。
- 未做：論文規模的失敗率與成本低估幅度；修補前後 BC/CC/RC 拆項比較；`VIRTUAL_EDGE_LEFT` 那 1 列；修補的回歸測試（上述 seed 57、seed 45 兩例）。

### 步驟 5：論文規模下 repo 評估器低估 TSMTA 成本的幅度（2026-10-13；腳本 `ilp/probe_underestimate.py`，原始輸出 `results/paper_scale/*.log`）
- 方法：照 `main.py` 流程（未過濾的原圖；destination 取 slot 0 中 s 可達者；TSMTA k=2；n_clouds=20、T=10、num_planes=72、α=5、β=10），建出 TSMTA-Raw 與 TSMTA-Optimal 的樹，先用 repo 自己的 `evaluate_algorithm` 評分（＝先前實驗的算法），再對同一批樹做 `repair_connectivity` 後用同一個評估器重算。差距即評估器對斷開的樹少收的成本。每個設定每個 seed 只跑一次。SSSP／DMTS 一併計算作為對照。
- 設定與結果（Total 為 repo 評估器 BC＋α·CC＋β·RC；修補前→修補後）：

| 設定 | seed | 斷開的 slot | 不可達的 (dest,slot) | BC | Total | Total 倍數 | TSMTA/DMTS |
|---|---|---|---|---|---|---|---|
| n_sats=300, \|D\|=100 | 42 | 10/10 | 994/1000 | 3.6→187.5 | 804.8→1000.9 | 1.24 | 0.22→0.27 |
| | 43 | 10/10 | 999/1000 | 44.0→258.1 | 829.2→1067.7 | 1.29 | 0.25→0.32 |
| | 44 | 10/10 | 1000/1000 | 6.6→292.2 | 795.9→1080.4 | 1.36 | 0.23→0.31 |
| n_sats=100, \|D\|=30 | 43 | 8/10 | 240/300 | 100.9→241.1 | 351.6→494.0 | 1.41 | 0.24→0.33 |
| | 44 | 9/10 | 270/300 | 65.2→240.9 | 330.7→512.0 | 1.55 | 0.19→0.30 |
| | 45 | 6/10 | 180/300 | 182.1→295.4 | 463.6→578.0 | 1.25 | 0.27→0.34 |
| | 46 | 9/10 | 270/300 | 46.2→234.7 | 319.2→512.2 | 1.60 | 0.20→0.32 |

  （上表為 Raw；Optimal 幾乎相同，Total 倍數 1.24–1.61。另有 n_sats=100、\|D\|=30、seed 42 的探測：BC 23.7→169.2、Total 341.5→492.6。）
- 觀察：
  - 論文規模下**幾乎所有 destination 在幾乎所有 slot 都與 s 斷開**（n_sats=300 的三個 seed：2993/3000 個 (dest,slot)）。BC 被低估一個數量級以上（3.6 對 187.5）；CC、RC 幾乎不變，所以 Total 只被低估 24%–61%。
  - 修補後 TSMTA 仍比 DMTS 便宜（TSMTA/DMTS 0.27–0.34，修補前 0.19–0.27），也就是在這些 seed 上排名沒有變，但優勢明顯縮小。
  - 例（n_sats=100, \|D\|=30, seed 44, slot 0）：s 的出度 1，連通部分 34 個節點，30 個 destination 全掛在一個孤兒 cache v138 底下（其子孫 45 個）；v138 的展開路徑 …→v140→v139→v138 經過它自己的子孫 v140、v139，與步驟 1 的機制相同。destination 越多，一個樹幹斷掉就讓越多 destination 一起斷開，所以這個規模下是幾乎全斷。
  - 修補後 Raw 全部連通；Optimal 在 n_sats=100、seed 42 的探測中仍有 1 個 slot 不連通（其餘設定為 0），原因未查（可能是 slot 0 可達的 destination 在其他 slot 無路徑，未驗證）。
- 限制：只有 3＋4 個 seed、單一 (α,β)=(5,10)、k=2，沒有用論文的 k=3 與完整 100 run；修補後的成本是 TSMTA 解加最便宜接回路徑，是「真實成本」的一個上界估計，不是 TSMTA 該有的值；我沒有確認論文圖表實際使用的評估路徑是否就是這個 `evaluate_algorithm`，只確認 `main.py` 是。
