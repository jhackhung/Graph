# ilp/：TAMCS 的整數規劃（ILP）精確解

這個資料夾用 OR-Tools CP-SAT 求出 TAMCS 問題的**最優解**，用來量測 repo 內啟發式演算法 TSMTA 的**實際近似比**：

```
近似比 = TC(TSMTA) / TC(OPT)
```

repo 既有檔案（`Random_Orbit.py`、`TVM.py`、`Algorithm.py`、`main.py` 等）完全沒有修改；`ilp/` 只 import 它們來產生測試圖與 TSMTA 的解。

---

## 1. 求解的問題

### 輸入（`Instance`）

| 項目 | 說明 |
|---|---|
| 時間 slot `t = 0..T-1` | 每個 slot 有一張有向圖 `arcs[t]`，弧權重為正整數 |
| `s` | 來源節點 |
| `D` | 目的地集合 |
| `C` | 可以快取資料的衛星集合 |
| `f[t]` | slot t 的流量係數 |
| `g[(c,t)]` | 在 slot t 讓 c 快取的成本 |
| `alpha`、`beta` | 快取成本、改道（rerouting）成本的權重，皆為整數 |
| `scale` S | 浮點權重量化成整數的倍率（實驗用 10^5） |

單向規則：沒有進入 `s` 的弧，也沒有離開任何 `d ∈ D` 的弧。

### 決策（`Solution`）

每個 slot 要決定：

1. **樹 `T^t`**：以 `s` 為根、包含所有 `D` 的有向樹（每個非根節點入度 ≤ 1）。
2. **快取 `mu[c,t] ∈ {0,1}`**：c 在這個 slot 是否快取資料；c 必須在樹上。
3. **來源 `origin[d,t]`**：d 的資料由 `s` 或某個 `mu=1` 的 cache 供應，且必須是 d 在樹上的祖先。

### 目標：最小化總成本

```
BC = Σ_t Σ_{e∈T^t} f[t]·w_t(e)                # 頻寬成本，樹上每條弧只算一次
CC = Σ_{c,t} mu[c,t]·g[c,t]                   # 快取成本
RC = Σ_{d,t≥1} [ path(d,t-1) ≠ path(d,t) ]    # 改道次數，只比較 origin→d 這一段
TC = BC + α·CC + β·RC
```

直覺上的取捨：用 cache 可以讓下游路徑跨 slot 保持不變（省下 β·RC），但要付 α·CC，而且 trunk（`s→c`）也要算頻寬。

---

## 2. 檔案說明

### 核心程式

| 檔案 | 用途 |
|---|---|
| [instance.py](instance.py) | `Instance`／`Solution` 資料結構、`validate_instance`（檢查單向規則、整數權重、可達性等）、JSON 讀寫 |
| [evaluate.py](evaluate.py) | **唯一的計分標準**。`check_solution` 逐條檢查可行性並回報違規代碼，`evaluate` 計算 BC/CC/RC/TC。另有 `prune`、`relabel`、`evaluate_repo_compat`（重現 repo 自己的算法，僅供回歸測試）。不依賴 ortools 與 repo 演算法 |
| [model_cpsat.py](model_cpsat.py) | CP-SAT 模型：`build_model`、`solve`、`add_hint`（暖啟動）。變數有 `x`（樹弧）、`mu`、`h`（origin 選擇）、`y`（origin→d 路徑）、`z`（trunk）、`r`（改道），另有防環用的 `depth` |
| [brute_force.py](brute_force.py) | 與 ILP 完全獨立的窮舉精確解（逐 slot 枚舉樹×μ×origin，再用 DP 跨 slot），只適用極小圖，用來驗證 ILP 的正確性 |
| [adapter.py](adapter.py) | 接上 repo：`from_existing` 用 repo 的圖產生器建 `Instance`（刪除違反單向規則的弧、量化權重、抽 cache）；`from_tsmta_output` 把 TSMTA 的輸出轉成 `Solution` |
| [baseline.py](baseline.py) | 最短路徑樹（無 cache）的簡單可行解，測試用 |

### 資料與實驗腳本

| 檔案 | 用途 |
|---|---|
| [gen_random.py](gen_random.py) | 隨機極小圖產生器（固定 seed 可重現），供 ILP 與暴力法對拍 |
| [make_toys.py](make_toys.py) | 產生手算驗證用的 `tests/fixtures/toy1.json`、`toy2.json` |
| [run_ratio.py](run_ratio.py) | 批次實驗：對一組參數網格比較 TSMTA（Raw/Optimal）與 ILP，輸出 CSV，並逐列檢查不變量 |
| [summarize.py](summarize.py) | 把 `run_ratio` 的 CSV 彙整成統計表 |
| [scale_probe.py](scale_probe.py) | 規模探測：逐步加大 `n_sats`，看 CP-SAT 在時限內能否證明最優 |

### 文件

| 檔案 | 用途 |
|---|---|
| [docs/PLAN.md](docs/PLAN.md) | 實作計畫：問題的正式定義、決策 DEC-1～7、各階段 Gate、ILP 模型規格 |
| [docs/PROGRESS.md](docs/PROGRESS.md) | 逐階段執行紀錄（指令、測試數、實際數字、遇到的問題） |
| [docs/ILP_RESULTS.md](docs/ILP_RESULTS.md) | 最終結果報告：近似比、規模探測、發現的差異 |
| [docs/ILP_reuse_report.md](docs/ILP_reuse_report.md) | 動工前對 repo 的檢查報告（哪些部分能重用、repo 與論文定義的差異 D1–D16） |
| `tests/fixtures/` | 測試用 fixture（Toy-1、Toy-2、Fig. 1、repo 回歸資料） |

測試本身在 repo 根目錄的 `tests/`（`test_phase0` 到 `test_phase9`，加 `test_evaluate_repo_compat`）。

---

## 3. 整體流程

```
        Random_Orbit（repo 的衛星圖產生器）
                 │
                 ▼
   adapter.from_existing ──► Instance（整數權重、單向、可達）
                 │
      ┌──────────┼───────────────────────┐
      ▼          ▼                       ▼
 repo 的 TSMTA   model_cpsat（ILP）      brute_force（極小圖）
      │          │                       │
 adapter.from_   solve → extract         最優 TC_int
 tsmta_output    → Solution
      │          │                       │
      └──────────┴────────┬──────────────┘
                          ▼
              evaluate.check_solution（可行性）
              evaluate.evaluate（BC/CC/RC/TC）
                          │
                          ▼
              ratio = TC(TSMTA) / TC(ILP)
```

關鍵設計：**所有解都交給同一個 `evaluate` 計分**。ILP 讀解時只讀 `x`、`mu`、`h`，自己沿樹走出路徑，並斷言 `evaluate().TC_int == solver.ObjectiveValue()`。如果模型的限制式有漏洞，兩邊的數字就會對不上。

### 驗證層次（PLAN 的 Phase 0–10）

1. **evaluator 先行**：用附錄的 Toy-1 手算值（BC/CC/RC/TC 逐格比對）、各種不可行解必須被拒絕、`evaluate_repo_compat` 要能完全重現 repo 的數字。
2. **暴力法當第二意見**：與 ILP 無關、與 evaluator 以外無共用邏輯。
3. **ILP 分階段加功能**：單 slot 無 cache → 多 slot + rerouting → 加入 cache。每階段都與暴力法在數百張隨機極小圖上比對最優值。
4. **接上 TSMTA**：adapter 轉換，TSMTA 的解同樣用 `check_solution` 檢查。
5. **批次實驗**：1280 個實例，每列都檢查 `TC_ILP ≤ TC_TSMTA`、ILP 解可行、`ratio ≥ 1` 等不變量。

---

## 4. 如何執行

指令都在 **repo 根目錄**執行；Windows 需設 `PYTHONUTF8=1`（repo 的 print 含 emoji）。

```bash
# 全部測試
PYTHONUTF8=1 ./.venv_ilp/Scripts/python.exe -m pytest -q tests

# 近似比批次實驗
PYTHONUTF8=1 ./.venv_ilp/Scripts/python.exe -m ilp.run_ratio --seeds 20 --jobs 10 --workers 2 --out results/ratio_small.csv

# 彙整統計
PYTHONUTF8=1 ./.venv_ilp/Scripts/python.exe -m ilp.summarize results/ratio_small.csv

# 規模探測
PYTHONUTF8=1 ./.venv_ilp/Scripts/python.exe -m ilp.scale_probe --n-sats 8 12 16 20 30 40 --seeds 5
```

`.venv_ilp/` 是專案專用虛擬環境（ortools、networkx、pytest，以及 import repo 需要的 numpy/pandas/matplotlib 等）。

---

## 5. 主要結果摘要

詳見 [ILP_RESULTS.md](docs/ILP_RESULTS.md)。

- **近似比**：TSMTA-Optimal（k=2）平均約 1.137、最大約 2.055（只含 TSMTA 解可行的列，有倖存者偏誤）。約 73–76% 的實例 TSMTA 嚴格劣於最優。
- **規模**：|D|=3、|C|=2、T=4 時，`n_sats` 到 300 都能在數秒內證明最優。
- **發現**：TSMTA 輸出的樹在 1280 列中有 189 列（14.8%）不可行，主要是樹含有與 `s` 斷開的節點（到 cache 的 trunk 沒接上 `s`）。原因尚未查明，未做任何修補。

## 6. 注意事項與待確認項目

- 預設決策 DEC-1～7（例如 origin 可為任意 μ=1 的祖先、BC 沒有 0.3 折扣、RC 為總和、每 slot 強制為樹）尚待使用者確認；若更改，`evaluate`、`brute_force`、`model_cpsat` 三處要同步修改並重跑測試。
- 這裡的成本定義與 repo 的 `TVM.evaluate_algorithm` 不同（repo 有 0.3 折扣、RC 取平均），所以 `evaluate` 的數字不能直接和 repo 印出的 TC 相比。
- Fig. 1 的 fixture 由截圖重建，快取成本 `g` 為假設值。
- `depth` 變數是防禦性約束，目前沒有找到不加它會出錯的實例。
