#!/usr/bin/env bash
# 列出「還沒完成」的 array task id,用來補送失敗/被砍掉的 seed。
#
# 判斷依據：runs/k3_seed<SEED>/ 底下有沒有 completed_runs >= 1 的 checkpoint。
# 輸出可以直接餵給 sbatch --array=
#
# 用法:
#   ./nchc/pending_tasks.sh                 # 印出待跑清單
#   sbatch --array=$(./nchc/pending_tasks.sh)%20 nchc/run_k3.sh

set -euo pipefail

BASE_SEED=${BASE_SEED:-42}
N_TASKS=${N_TASKS:-100}
RUNS_DIR=${RUNS_DIR:-runs}

pending=()
for ((i = 0; i < N_TASKS; i++)); do
    seed=$((BASE_SEED + i))
    ckpt=$(ls "${RUNS_DIR}/k3_seed${seed}"/output_graphs_sats/checkpoint_*.json \n            2>/dev/null | head -n1 || true)

    done_flag=0
    if [ -n "$ckpt" ]; then
        # completed_runs >= 1 才算完成；壞掉的 JSON 一律當成未完成
        if python -c "
import json,sys
try:
    sys.exit(0 if json.load(open(sys.argv[1]))['completed_runs'] >= 1 else 1)
except Exception:
    sys.exit(1)
" "$ckpt" 2>/dev/null; then
            done_flag=1
        fi
    fi

    [ "$done_flag" -eq 0 ] && pending+=("$i")
done

if [ ${#pending[@]} -eq 0 ]; then
    echo "所有 task 皆已完成" >&2
    exit 1
fi

# 印成 sbatch --array 能吃的逗號清單
(IFS=,; echo "${pending[*]}")
