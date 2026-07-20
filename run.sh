#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 3 ]; then
    echo "用法: ./run_sweep.sh <sats|dests|both> <次數> <config.json> [all|dmts|sssp|offpa|tsmta|逗號多選]"
    echo "範例:"
    echo "  ./run_sweep.sh sats 5 config.json"
    echo "  ./run_sweep.sh dests 5 config.json"
    echo "  ./run_sweep.sh both 5 config.json tsmta"
    exit 1
fi

MODE=$1
N=$2
CONFIG=$3
ALGO=${4:-all}

if [ "$MODE" != "sats" ] && [ "$MODE" != "dests" ] && [ "$MODE" != "both" ]; then
    echo "錯誤: MODE 只能是 sats、dests 或 both"
    exit 1
fi

if ! command -v jq &> /dev/null; then
    echo "錯誤: 未安裝 jq，請先執行 sudo apt install jq"
    exit 1
fi

# =========================================================
# 從 config 讀實驗參數
# =========================================================

# config 寫法：
# "pdta_levels": [1, 2, 3]
# 或只寫：
# "pdta_level": 2
readarray -t PDTA_LEVELS < <(jq -r '.pdta_levels // [.pdta_level // 2] | .[]' "$CONFIG")

# config 寫法：
# "beta_values": [1, 10, 50, 100]
BETA_VALUES=$(jq -c '.beta_values // [1,10,50,100]' "$CONFIG")
BASE_SEED=$(jq -r '.base_seed // 42' "$CONFIG")

# 是否清掉舊結果，仍然先放 bash 控制
# 重新跑完整實驗建議 KEEP=0
# 補跑才改 KEEP=1
KEEP=0

echo "MODE=$MODE"
echo "N=$N"
echo "CONFIG=$CONFIG"
echo "PDTA_LEVELS=${PDTA_LEVELS[*]}"
echo "BETA_VALUES=$BETA_VALUES"
echo "BASE_SEED=$BASE_SEED"
echo "ALGO=$ALGO"

if [ "$ALGO" != "all" ]; then
    echo "補跑 (ALGO=$ALGO): 保留既有 xlsx,結果將以 upsert 方式更新"
elif [ "$KEEP" -eq 0 ]; then
    # =========================================================
    # 清掉舊結果
    # =========================================================
    if [ "$MODE" = "sats" ] || [ "$MODE" = "both" ]; then
        rm -f sats_pdta*_beta_*.xlsx
        rm -f sats_beta_*.xlsx
    fi

    if [ "$MODE" = "dests" ] || [ "$MODE" = "both" ]; then
        rm -f dests_pdta*_beta_*.xlsx
        rm -f dests_beta_*.xlsx
    fi
fi

# =========================================================
# Function: run sats sweep
# =========================================================
run_sats() {
    local PDTA_K=$1

    BASE_NSATS=$(jq -r '.start_sats // .n_sats' "$CONFIG")
    STEP_NSATS=$(jq -r '.step_sats // 50' "$CONFIG")

    echo "======================================"
    echo "開始跑 sats sweep | PDTA k=$PDTA_K"
    echo "======================================"

    for ((i=1; i<=N; i++))
    do
        NSATS=$((BASE_NSATS + STEP_NSATS * (i - 1)))
        TMP_CONFIG=$(mktemp /tmp/config_sats.XXXXXX.json)

        jq \
          --argjson nsats "$NSATS" \
          --argjson seed "$BASE_SEED" \
          --argjson pdta_k "$PDTA_K" \
          --argjson beta_values "$BETA_VALUES" \
          --arg algos "$ALGO" \
          '.n_sats=$nsats
           | .sweep_x="sats"
           | .base_seed=$seed
           | .pdta_level=$pdta_k
           | .beta_values=$beta_values
           | .algos=$algos' \
          "$CONFIG" > "$TMP_CONFIG"

        echo "=== sats | PDTA k=$PDTA_K | 第 $i 次 === n_sats=$NSATS config=$TMP_CONFIG"

        python main.py "$TMP_CONFIG"

        rm -f "$TMP_CONFIG"
    done
}

# =========================================================
# Function: run dests sweep
# =========================================================
run_dests() {
    local PDTA_K=$1

    BASE_NDESTS=$(jq -r '.start_dests // .n_dests // 50' "$CONFIG")
    STEP_NDESTS=$(jq -r '.step_dests // 50' "$CONFIG")

    echo "======================================"
    echo "開始跑 dests sweep | PDTA k=$PDTA_K"
    echo "======================================"

    for ((i=1; i<=N; i++))
    do
        NDESTS=$((BASE_NDESTS + STEP_NDESTS * (i - 1)))
        TMP_CONFIG=$(mktemp /tmp/config_dests.XXXXXX.json)

        jq \
          --argjson ndests "$NDESTS" \
          --argjson seed "$BASE_SEED" \
          --argjson pdta_k "$PDTA_K" \
          --argjson beta_values "$BETA_VALUES" \
          --arg algos "$ALGO" \
          '.n_dests=$ndests
           | .sweep_x="dests"
           | .base_seed=$seed
           | .pdta_level=$pdta_k
           | .beta_values=$beta_values
           | .algos=$algos' \
          "$CONFIG" > "$TMP_CONFIG"

        echo "=== dests | PDTA k=$PDTA_K | 第 $i 次 === n_dests=$NDESTS config=$TMP_CONFIG"

        python main.py "$TMP_CONFIG"

        rm -f "$TMP_CONFIG"
    done
}

# =========================================================
# Main loop
# =========================================================
for PDTA_K in "${PDTA_LEVELS[@]}"
do
    if [ "$MODE" = "sats" ]; then
        run_sats "$PDTA_K"
    elif [ "$MODE" = "dests" ]; then
        run_dests "$PDTA_K"
    elif [ "$MODE" = "both" ]; then
        run_sats "$PDTA_K"
        run_dests "$PDTA_K"
    fi
done

echo "所有實驗執行完畢！"