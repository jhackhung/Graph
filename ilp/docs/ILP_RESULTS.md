# TAMCS ILP 精確解：結果報告

日期：2026-10-10。環境：Python 3.12.3、ortools 9.15.6755、Windows 11。逐階段紀錄見 `PROGRESS.md`。

## 1. 各階段 Gate 一覽

| 階段 | 內容 | 結果 |
|---|---|---|
| 0 | CP-SAT 熟悉 | 通過（52 個測試） |
| 1 | Instance / 驗證 / JSON | 通過 |
| 2 | 獨立 evaluator；Toy-1 手算表逐格吻合；repo_compat 完全重現 repo 數字 | 通過 |
| 3 | 暴力精確解；Toy-1 A.3 全表吻合；DP 與窮舉對拍 | 通過 |
| 4 | ILP 單 slot 無 cache；Toy-2 = 6；50 張隨機圖等於暴力法 | 通過 |
| 5 | 多 slot + rerouting；Toy-1 `C=∅` 吻合；100+80 張隨機圖等於暴力法 | 通過 |
| 6 | 加入 cache；Toy-1 全表吻合；150+60 張隨機圖等於暴力法；性質與穩定性測試 | 通過 |
| 7 | Adapter；instance 合法；量化誤差在界內 | 通過（TSMTA 解可行性結果見 §3） |
| 8 | 暖啟動與近似比；1280 列不變量全成立 | 通過 |
| 9 | Fig. 1：(d)(e)(f) 的 BC／RC 與論文一致；ILP ≤ 三策略 | 通過；g 為假設值 |
| 10 | 規模探測 | 完成；選用的預處理未做 |

全部測試：887 通過、10 skipped（skip 為性質測試中該隨機圖無可加的額外葉弧）。

## 2. 近似比（TSMTA k=2 vs ILP 最優）

網格：n_sats∈{8,12,16,20} × |D|∈{2,3} × |C|∈{1,2} × T∈{3,4} × (α,β)∈{(1,100),(5,10)} × 20 seed，共 1280 列，S=10^5，ILP 全部 OPTIMAL。
下表只含 TSMTA 解可行的列（Optimal 1091 列），**排除了 189 個不可行的列，有倖存者偏誤**。

| 範圍 | 列數 | 平均 | 最大 |
|---|---|---|---|
| TSMTA-Optimal，全部 | 1091 | 1.137 | 2.055 |
| (α,β)=(1,100) | 512 | 1.070 | 1.876 |
| (α,β)=(5,10) | 579 | 1.196 | 2.055 |
| TSMTA-Raw，全部 | 1091 | 1.136 | 2.248 |

- 約 73–76% 的實例 TSMTA 嚴格劣於最優。
- 依 n_sats（Optimal 平均）：8→1.129、12→1.123、16→1.128、20→1.173。
- ILP 未收斂比例：0%（1280/1280 OPTIMAL）。
- 暖啟動對最優值沒有影響（100% 相同），對速度也沒有可見差別，因為每次本來就在 0.12 秒內解完。

## 3. 發現的 repo 與定義差異

1. **TSMTA 輸出的樹常不可行**：1280 列中 189 列（14.8%）。幾乎都是 `UNREACHABLE`（樹含有跟 s 斷開的節點，例如到 cache 的 trunk 沒接上 s），另有 1 列 Optimal 缺 destination。比例隨規模上升（n_sats=8：5%，20：26%），且 β=100 時（20%）高於 β=10 時（9.5%）。最小重現在 `results/tsmta_infeasible/`。**成因已查明（Phase 13）**：TSMTA 把各條 CTIG／虛擬 s→c 邊獨立展開成最短路徑再併成一棵樹，路徑對同一節點的上下游方向不一致時，「已有 parent 就跳過」與「成環就跳過」兩條防護會丟掉唯一接回 s 的邊，cache 成為孤兒，底下的子樹斷開（480 個實例中 60 個失敗，全部符合此機制；選樹階段 18、展開虛擬邊階段 42）。在 repo 原始未刪弧的圖上同樣發生（n_sats=20：6/10 個 run 有斷開的 slot），所以不是單向刪弧或覆寫 cache 集合造成。repo 的 TSMTA 評估器（`BC_multicast_cache_aware` 只從 src 做 DFS、無可達性檢查）看不到這類斷開，成本因此被低估；SSSP／DMTS 沒有此問題（40 個 slot 全連通）。adapter 端修補（`repair_connectivity`，`from_tsmta_output(repair=True)`）後 Raw、Optimal 的不可行都降到 0（另有 1 列 `VIRTUAL_EDGE_LEFT` 無法修補），修補後近似比平均 1.289、最大 6.286（含修補，非論文 TSMTA 的近似比）。詳見 PROGRESS.md Phase 13。
2. `main.Build_TIG_CTIG` 忽略傳入的 `caches` 參數，改讀 `graphs[0]` 的 `cache` 節點屬性；adapter 因此在複製的圖上改寫該屬性。
3. 沿用 `ILP_reuse_report.md` 的 D1–D6、D14（BC 0.3 折扣、RC 取平均、origin 判斷、Optimal 後旗標遺失、儲存權重等）：新 evaluator 不使用它們，`evaluate_repo_compat` 能完全重現 repo 數字（Raw 79.8572、Optimal 70.6078），確認我們讀懂了 repo 的定義。
4. 量化：S=10^5 時最大相對誤差 6.9e-5（報告 D10 估計 1.6e-5；此處弧權重更小，原因為推測）。
5. ILP 模型比 PLAN 多了 `depth` 變數（防 x 中與 s 斷開的環）。我沒有找到不加它會出錯的實例，是防禦性約束。

## 4. 規模探測

|D|=3、|C|=2、T=4、num_planes=4、每種規模 10 個實例（2 組 α,β × 5 seed）、時限 600 s：

| n_sats | 證明最優 | 變數數（平均） | 限制式（平均） | 最長求解時間 |
|---|---|---|---|---|
| 8 | 10/10 | 606 | 1219 | 0.05 s |
| 20 | 10/10 | 1253 | 2628 | 0.06 s |
| 40 | 10/10 | 2305 | 4860 | 0.11 s |
| 100 | 10/10 | 5640 | 11797 | 0.54 s |
| 200 | 10/10 | 11141 | 23245 | 2.4 s |
| 300 | 10/10 | 16672 | 34724 | 6.2 s |

測到的範圍內沒有出現未收斂的情況。未測 n_sats>300，也未測 |D|>3（論文實驗用到 |D|=100，這個設定下是否仍然容易，尚未知）。

## 5. 待使用者決定

- DEC-1 至 DEC-7 全部採 PLAN 預設值，皆待確認：origin 可為任意 μ=1 祖先、C 只含衛星、每 slot 強制為樹、BC 無 0.3 折扣且 RC 為總和、μ 的推導規則、S 與 (α,β) 組合、時限 600 s。
- Fig. 1 的 g（快取成本）與 v 鏈弧權重；Example 1 的 +1／+3 不一致。
- TSMTA 不可行解：成因已查明並在 adapter 端修補（Phase 13）。待決定：論文實驗中這些輸出如何處理；是否把修補或可達性檢查放進 repo 的 `TVM.py`／評估器（會改變既有圖表數字）；論文規模下 TSMTA 成本被低估的幅度。
- 是否把 `.venv_ilp/` 加進 `.gitignore`（PLAN 規定不改既有檔案，所以我沒動；`results*` 已被既有規則忽略）。

## 6. 重現指令（repo 根目錄）

```
PYTHONUTF8=1 ./.venv_ilp/Scripts/python.exe -m pytest -q tests
PYTHONUTF8=1 ./.venv_ilp/Scripts/python.exe -m ilp.run_ratio --seeds 20 --jobs 10 --workers 2 --out results/ratio_small.csv
PYTHONUTF8=1 ./.venv_ilp/Scripts/python.exe -m ilp.summarize results/ratio_small.csv
PYTHONUTF8=1 ./.venv_ilp/Scripts/python.exe -m ilp.scale_probe --n-sats 8 12 16 20 30 40 60 80 100 150 200 300 --seeds 5
```
