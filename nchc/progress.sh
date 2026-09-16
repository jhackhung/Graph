#!/usr/bin/env bash
# 看 k=3 實驗的整體進度。
#
# 進度來源有兩個,互補:
#   1. squeue  -> Slurm 層面:誰在跑、誰在排隊
#   2. 各 task 的 log -> 程式層面:正在跑的那些做到哪了
#
# 用法: ./nchc/progress.sh [JOBID]

set -uo pipefail

USER=${USER:-$(whoami)}
BASE_SEED=${BASE_SEED:-42}
N_TASKS=${N_TASKS:-100}
RUNS_DIR=${RUNS_DIR:-runs}
JOBID=${1:-}

echo "==================== Slurm 佇列 ===================="
if [ -n "$JOBID" ]; then
    squeue -j "$JOBID" -h -o "%t" 2>/dev/null | sort | uniq -c | while read -r n st; do
        case "$st" in
            R)  echo "  RUNNING  : $n" ;;
            PD) echo "  PENDING  : $n" ;;
            *)  echo "  $st       : $n" ;;
        esac
    done
    [ -z "$(squeue -j "$JOBID" -h 2>/dev/null)" ] && echo "  (佇列中已無此 job,可能已全部結束)"
else
    squeue -u "$USER" -h -o "%t" 2>/dev/null | sort | uniq -c | while read -r n st; do
        echo "  $st : $n"
    done
    [ -z "$(squeue -u "$USER" -h 2>/dev/null)" ] && echo "  (佇列中沒有你的 job)"
fi

echo
echo "==================== 完成度 ===================="
done_n=0
for ((i = 0; i < N_TASKS; i++)); do
    seed=$((BASE_SEED + i))
    ckpt=$(ls "${RUNS_DIR}/k3_seed${seed}"/checkpoint_*.json 2>/dev/null | head -n1 || true)
    if [ -n "$ckpt" ] && python -c "
import json,sys
try:
    sys.exit(0 if json.load(open(sys.argv[1]))['completed_runs'] >= 1 else 1)
except Exception:
    sys.exit(1)
" "$ckpt" 2>/dev/null; then
        done_n=$((done_n + 1))
    fi
done
echo "  已完成 seed: ${done_n} / ${N_TASKS}"

echo
echo "============ 正在跑的 task 各自做到哪 ============"
# checkpoint 只在整個 run 跑完才寫,所以「跑到一半」的進度只能看 log。
shopt -s nullglob
logs=(logs/k3_*.out)
if [ ${#logs[@]} -eq 0 ]; then
    echo "  (還沒有 log)"
else
    for f in $(ls -t "${logs[@]}" | head -n 10); do
        seed_line=$(grep -o "seed=[0-9]*" "$f" 2>/dev/null | head -n1)
        last=$(grep -E "Build|Evaluate|Run [0-9]+/|TIG" "$f" 2>/dev/null | tail -n1 | cut -c1-90)
        printf "  %-22s %-10s %s\n" "$(basename "$f")" "${seed_line:-?}" "${last:-(尚無輸出)}"
    done
fi
