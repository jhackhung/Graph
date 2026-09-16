# 在台灣杉三號跑 sats k=3 實驗

目標：**300 sats / 100 dests / PDTA k=3**，100 個 seed。

一個 Slurm array task = 一個 seed = 一個獨立 process 與獨立工作目錄。
（為什麼要這樣切 → 見〈設計說明〉）

帳號設定已填好：`--account=acd109125`、`--partition` 也已按杉三號實際佇列設定，
腳本可以直接送。

---

## TL;DR

```bash
sbatch nchc/smoke_test.sh     # 1. 冒煙測試(ctest,幾分鐘)
sbatch nchc/probe_k2.sh       # 2. 探測(ct56),量時間與記憶體
                              # 3. 看 probe 結果決定 k=3 是否可行  ← 決策點
sbatch nchc/run_k3.sh         # 4. 正式 100 seed,送一次就好
./nchc/progress.sh            #    看進度
python nchc/merge_results.py --runs runs \
    --out sats_pdta3_beta_10_alpha_5_merged.xlsx --n-sats 300 --pdta-k 3
```

---

## 檔案

| 檔案 | 用途 |
| --- | --- |
| `smoke_test.sh` | 小規模冒煙測試（ctest），確認環境設定正確 |
| `probe_k2.sh` | 1 seed、k=2 探測，量 wall time 與 peak RSS |
| `run_k3.sh` | 100 seed、k=3 的 job array |
| `progress.sh` | 看進度（佇列狀態 + 完成數 + 正在跑的到哪了）|
| `pending_tasks.sh` | 列出還沒跑完的 task id，用來補送 |
| `make_config.py` | 由 base config 產生單一 task 專用的 config |
| `merge_results.py` | 合併各 seed 的 checkpoint，算出正確的 mean/std |

---

## 步驟

### 0. 建環境（登入節點，只做一次）

```bash
module load miniconda3
conda create -n satgraph python=3.12 -y
conda activate satgraph
pip install networkx numpy pandas openpyxl scipy
```

### 1. 上傳專案

`tig_cache_sats/` 裡已經有 seed 42 / n_sats=300 的 TIG cache（約 163 MB），
一併上傳可以讓該 seed 的 task 直接命中、省下整個 TIG build。

```bash
rsync -av --exclude='.git' --exclude='__pycache__' \
      --exclude='experiment*' --exclude='img*' --exclude='output_graphs*' \
      ./ u4342858@t3-login.nchc.org.tw:~/Graph/
```

### 2. 冒煙測試

在丟大 job 前，先用小規模（50 sats、k=1）確認環境、路徑、輸出都對。
跑 `ctest` 佇列，排隊最快：

```bash
sbatch nchc/smoke_test.sh
```

跑完檢查 `runs/smoke_seed42/` 底下有沒有出現
`sats_pdta1_beta_10_alpha_5.xlsx` 與 `checkpoint_*.json`。
有出現就代表設定正確。

### 3. 跑 probe（k=2，單 seed）

```bash
sbatch nchc/probe_k2.sh
```

跑完讀兩個數字：

```bash
grep -E "Elapsed \(wall clock\)|Maximum resident" logs/probe_k2_*.err
```

| 數字 | 用途 |
| --- | --- |
| `Elapsed (wall clock)` | 估 `run_k3.sh` 的 `--time` |
| `Maximum resident set size` (KB) ÷ 1024² | 估 `--mem`，建議設 peak RSS 的 2 倍 |

目前 `--mem=24G` 的依據：本機實測載入 n_sats=300 的 TIG cache 佔 **3.60 GB**。

### 4. 決策點 ← 不要跳過

k=3 在 300 顆的成本目前仍是**外推值**。已知 k=3 的 build 時間：

| n_sats | 每 run build |
| --- | --- |
| 50 | 2,034 s |
| 100 | 31,051 s（**15.3 倍**）|

若 300 顆延續這個超線性趨勢，單一 run 可能**超過 `ct56` 的 96 小時上限**。
那樣的話不管併發度開多少都跑不完，會被 Slurm 直接砍掉，
而且因為 checkpoint 以整個 run 為單位寫，被砍掉的 run 不留部分進度。

看完 probe 的實際時間再決定：直接送、降 seed 數（10~20 個 std 通常就夠穩）、
或改用更小的 n_sats。

### 5. 送正式實驗

```bash
sbatch nchc/run_k3.sh
```

**送一次就好。** `--array=0-99%20` 已經把 100 個 task 全部排進佇列，
`%20` 只是限制同時跑 20 個，其餘 Slurm 會自動遞補。

只想先試幾個 seed，命令列覆蓋即可（不必改檔案）：

```bash
sbatch --array=0-4%5 nchc/run_k3.sh     # 只跑 seed 42~46
sbatch --array=0-99%10 nchc/run_k3.sh   # 併發降到 10
```

### 6. 合併結果

```bash
python nchc/merge_results.py \
    --runs runs \
    --out sats_pdta3_beta_10_alpha_5_merged.xlsx \
    --n-sats 300 --pdta-k 3
```

輸出欄位與既有的 `sats_pdta*.xlsx` 完全一致，`plot_results.py` 不需修改。

---

## 看進度

```bash
./nchc/progress.sh            # 全部
./nchc/progress.sh 1234567    # 指定 JOBID
```

印三段：佇列狀態、已完成 seed 數、正在跑的 task 各自做到哪。

### 手動指令

```bash
squeue -u $USER                      # R=跑中 PD=排隊
tail -f logs/k3_<JOBID>_0.out        # 追某個 task 即時輸出
sacct -j <JOBID> --format=JobID,State,Elapsed,MaxRSS,ReqMem   # 跑完看實際用量
scancel <JOBID>                      # 取消整個 array
scancel <JOBID>_3                    # 只取消第 3 個 task
```

`MaxRSS` 是實際記憶體峰值，可用來判斷 `--mem` 開太大還是太小。

### 進度的粒度限制

`main.py` 在**整個 run 跑完後**才寫 checkpoint。每個 task 只跑 1 run，
所以 checkpoint 對單一 task 只有「沒完成 / 完成了」兩種狀態，沒有中間進度。

想看跑到一半的 task 在做什麼，只能看 log（裡面有 `Build TIG/CTIG`、
`Evaluate beta=...` 等階段訊息）：

```bash
tail -n 20 logs/k3_<JOBID>_0.out
```

k=3 單 run 可能要數十小時，這在判斷「還在跑 vs 卡住了」時很重要。

---

## 補送失敗的 seed

job 被砍掉（超時、節點故障）或某些 seed 失敗時，只送沒跑完的：

```bash
./nchc/pending_tasks.sh                                       # 先看清單
sbatch --array=$(./nchc/pending_tasks.sh)%20 nchc/run_k3.sh   # 只補這些
```

判斷依據是 `runs/k3_seed<SEED>/` 的 checkpoint：`completed_runs >= 1`
才算完成，壞掉的 JSON 一律當未完成。

單一 task 的工作目錄彼此獨立，重送不會影響其他 seed。
`main.py` 本身也有 resume，已完成的 seed 會印
「✅ Checkpoint 顯示所有 run 皆已完成」然後立即結束。

> **不要用 `sbatch nchc/run_k3.sh` 重送整批。** 那會建立另一個全新的
> 100 task job（seed 範圍相同），等於整批重跑，白白消耗額度。

---

## 參考

### 佇列選擇（已用 sinfo 確認）

| 佇列 | TIMELIMIT | 用途 |
| --- | --- | --- |
| `ctest` | 2:00:00 | 冒煙測試。排隊最快，但跑不完正式 job |
| `ct56` | **4-00:00:00** | **正式用這個**。4 天是 ct 系列最長 |
| `ct224` / `ct560` | 4-00:00:00 | 多節點平行用，單核作業用不到 |
| `ct2k` / `ct8k` | 3-00:00:00 | 大規模平行，walltime 反而更短 |

`ct` 後的數字是**核心規模**，不是速度。我們的工作是單執行緒單節點
（TSMTA/PDTA 是 networkx 上的遞迴樹搜尋，沒有平行化程式碼，也用不到 GPU），
需要的是最長 walltime，所以 `ct56` 最合適：時間上限並列最長，
資源需求最小、最容易排到。

`ngs*`、`twb*`、`NCHC_*` 是其他計畫別的專用佇列，與本實驗無關。

### 併發數 `%20` 怎麼調

以 `--mem=24G` 計算：

| 併發 | 同時佔用 | 跑完 100 seed 的波數 |
| --- | --- | --- |
| `%10` | 240 GB | 10 |
| `%20` | 480 GB | 5 |
| `%25` | 600 GB | 4 |
| `%40` | 960 GB | 3 |

拿到 probe 的 peak RSS 後若能調小 `--mem`，併發就可以往上加。
**不要不加 `%`** —— 那代表無上限，100 個 task 同時起來會吃爆記憶體。

### 這樣送會影響主機嗎

不會，這正是 Slurm 的用途。

- **不影響別人**：job 只在配發的節點與核心上跑，超出 `--mem` 是自己的 task
  被砍掉，不會吃到別人的資源。
- **100 個 task 不算多**：`ct56` 有 392 個節點。fair-share 會讓用越多的人
  優先權自動降低，這是設計好的機制。
- **`%20` 保護的是你自己**：避免超出配額、避免一次佔太多名額壓低自己的優先權。

唯一要避免的是重複送同一批 job，那浪費的是自己的計畫額度。

**但不要在登入節點（`lgn302`）直接跑 `python main.py`。**
登入節點是所有人共用的，重運算要一律用 `sbatch` 送進佇列。

---

## 設計說明

### 每個 task 一個獨立目錄

`main.py` 寫出的 Excel（`sats_pdta3_beta_10_alpha_5.xlsx`）與 checkpoint
都是相對 CWD 的固定檔名、**不含 seed**。多個 process 在同一目錄跑會互相覆蓋，
而且 Excel 是 read-modify-write 且無鎖。

所以腳本讓每個 task `cd` 進 `runs/k3_seed<SEED>/`，再用 symlink 把 `*.py` 連進去。

### 合併不能取「平均的平均」

每個 task 只跑 1 run，它自己算出的 mean 就是那一個 run 的值、std 是 0。
把這些 mean 再平均，mean 會對但 **std 會完全錯掉**。

`merge_results.py` 因此從 checkpoint JSON 讀**原始 per-run 值**，
收齊全部 seed 後才算一次統計。

### TIG cache 可以共用

cache 檔名已含 `seed{seed}`，不同 seed 天然不撞檔，
所有 task 共用 `tig_cache_sats/` 是安全的。

（`TIG_Cache.py` 與 `main.py` 的暫存檔名原本是固定的 `.tmp`，
併發時會互相覆寫、讓 `os.replace` 的原子性失效，已改成含 pid。）
