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
