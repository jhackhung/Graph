#!/usr/bin/env bash
set -euo pipefail

# =========================================================
# plot.sh - 依需求組出 xlsx 檔名並呼叫 plot_results.py 畫圖
#
# 用法:
#   ./plot.sh --x sats  --file <xlsx>                          [--break-ratio R]
#   ./plot.sh --x dests --file <xlsx>                          [--break-ratio R]
#   ./plot.sh --x beta  --fixed-type sats|dests --fixed N --pdta K [--alpha A] [--break-ratio R]
#   ./plot.sh --x alpha --fixed-type sats|dests --fixed N --pdta K [--beta B]  [--break-ratio R]
#   ./plot.sh --all [--out-dir DIR]
#
# 共用選項:
#   --out-dir DIR   所有圖直接存到 DIR (不分子資料夾)
#   --pdf-only      只存 PDF，不存 PNG
#
# --all: 一次畫論文用的 5 組圖 (dests / sats / alpha / beta / bar)，
#        只存 PDF，全部放到同一個資料夾 (預設 paper_figs/)。
#        要改場景參數請改下方 run_all() 裡的 ALL_* 變數。
#
# 範例:
#   ./plot.sh --x sats --file results_ns300_nc20_nd50_p72_t10_avg_std.xlsx --break-ratio 1
#   ./plot.sh --x beta  --fixed-type sats --fixed 300 --pdta 2
#   ./plot.sh --x alpha --fixed-type sats --fixed 50  --pdta 1 --beta 10
#
# 檔名慣例 (main.py 產生):
#   {sats|dests}_pdta{K}_beta_{B}_alpha_{A}.xlsx
# =========================================================

usage() {
    grep '^#' "$0" | sed -e 's/^# \{0,1\}//' -e '/^!\/usr/d'
    exit 1
}

X_TYPE=""
FIXED_TYPE=""
FIXED=""
PDTA=""
BETA=""
ALPHA="1"
FILE=""
BREAK_RATIO=""
OUT_DIR=""
PDF_ONLY=0
RUN_ALL=0

run_all() {
    # ===== --all 的場景參數 =====
    local ALL_PDTA=2
    local ALL_BETA=10
    local ALL_ALPHA=5
    local ALL_FIXED_TYPE=dests
    local ALL_FIXED=100
    local ALL_BAR_SATS=300   # bar 圖的 sats 數，三個 sats_pdta{1,2,3} 檔都要有這個 graph_N
    local ALL_BAR_DESTS=100
    local ALL_OUT="${OUT_DIR:-paper_figs}"
    local COMMON=(--out-dir "$ALL_OUT" --pdf-only)

    mkdir -p "$ALL_OUT"

    echo "=== [1/5] x=dests ==="
    python plot_results.py "dests_pdta${ALL_PDTA}_beta_${ALL_BETA}_alpha_${ALL_ALPHA}.xlsx" \
        --x dests --x-start 100 --x-end 500 --x-step 100 --break-ratio 1 "${COMMON[@]}"

    echo "=== [2/5] x=sats ==="
    python plot_results.py "sats_pdta${ALL_PDTA}_beta_${ALL_BETA}_alpha_${ALL_ALPHA}.xlsx" \
        --x sats --x-start 100 --x-end 500 --x-step 100 --break-ratio 1 "${COMMON[@]}"

    echo "=== [3/5] x=alpha ==="
    python plot_results.py ${ALL_FIXED_TYPE}_pdta${ALL_PDTA}_beta_${ALL_BETA}_alpha_*.xlsx \
        --x alpha --fixed-type "$ALL_FIXED_TYPE" --fixed "$ALL_FIXED" --break-ratio 5 "${COMMON[@]}"

    echo "=== [4/5] x=beta ==="
    python plot_results.py ${ALL_FIXED_TYPE}_pdta${ALL_PDTA}_beta_*_alpha_${ALL_ALPHA}.xlsx \
        --x beta --fixed-type "$ALL_FIXED_TYPE" --fixed "$ALL_FIXED" --break-ratio 5 "${COMMON[@]}"

    # bar: 每個 PDTA_k 一個檔; --sats/--dests 設同一個值，避免 graph_N 誤配 (見 load_scenario_excels)
    echo "=== [5/5] bar (x=PDTA_k) ==="
    python plot_results.py sats_pdta*_beta_${ALL_BETA}_alpha_${ALL_ALPHA}.xlsx \
        --mode bar --sats "$ALL_BAR_SATS" --dests "$ALL_BAR_DESTS" --alpha "$ALL_ALPHA" --beta "$ALL_BETA" "${COMMON[@]}"

    echo "完成！PDF 都在 $ALL_OUT/"
}

while [ $# -gt 0 ]; do
    case "$1" in
        --all)
            RUN_ALL=1; shift ;;
        --out-dir)
            OUT_DIR="$2"; shift 2 ;;
        --pdf-only)
            PDF_ONLY=1; shift ;;
        --x)
            X_TYPE="$2"; shift 2 ;;
        --fixed-type)
            FIXED_TYPE="$2"; shift 2 ;;
        --fixed)
            FIXED="$2"; shift 2 ;;
        --pdta)
            PDTA="$2"; shift 2 ;;
        --beta)
            BETA="$2"; shift 2 ;;
        --alpha)
            ALPHA="$2"; shift 2 ;;
        --file)
            FILE="$2"; shift 2 ;;
        --break-ratio)
            BREAK_RATIO="$2"; shift 2 ;;
        -h|--help)
            usage ;;
        *)
            echo "未知參數: $1"
            usage ;;
    esac
done

if [ "$RUN_ALL" -eq 1 ]; then
    run_all
    exit 0
fi

if [ -z "$X_TYPE" ]; then
    echo "錯誤: 必須指定 --x sats|dests|beta|alpha 或 --all"
    usage
fi

EXTRA_ARGS=()
if [ -n "$BREAK_RATIO" ]; then
    EXTRA_ARGS+=(--break-ratio "$BREAK_RATIO")
fi
if [ -n "$OUT_DIR" ]; then
    EXTRA_ARGS+=(--out-dir "$OUT_DIR")
fi
if [ "$PDF_ONLY" -eq 1 ]; then
    EXTRA_ARGS+=(--pdf-only)
fi

case "$X_TYPE" in
    sats|dests)
        if [ -z "$FILE" ]; then
            echo "錯誤: --x $X_TYPE 需要 --file <xlsx>"
            usage
        fi
        echo "=== 畫圖: x=$X_TYPE  file=$FILE ==="
        python plot_results.py "$FILE" --x "$X_TYPE" "${EXTRA_ARGS[@]}"
        ;;

    beta)
        if [ -z "$FIXED_TYPE" ] || [ -z "$FIXED" ] || [ -z "$PDTA" ]; then
            echo "錯誤: --x beta 需要 --fixed-type sats|dests、--fixed N、--pdta K"
            usage
        fi

        PATTERN="${FIXED_TYPE}_pdta${PDTA}_beta_*_alpha_${ALPHA}.xlsx"
        FILES=( $PATTERN )

        if [ ! -e "${FILES[0]}" ]; then
            echo "錯誤: 找不到符合的檔案: $PATTERN"
            exit 1
        fi

        echo "=== 畫圖: x=beta  fixed-type=$FIXED_TYPE  fixed=$FIXED  pdta=$PDTA  alpha=$ALPHA ==="
        echo "檔案: ${FILES[*]}"

        python plot_results.py "${FILES[@]}" \
            --x beta \
            --fixed-type "$FIXED_TYPE" \
            --fixed "$FIXED" \
            "${EXTRA_ARGS[@]}"
        ;;

    alpha)
        if [ -z "$FIXED_TYPE" ] || [ -z "$FIXED" ] || [ -z "$PDTA" ]; then
            echo "錯誤: --x alpha 需要 --fixed-type sats|dests、--fixed N、--pdta K"
            usage
        fi
        if [ -z "$BETA" ]; then
            echo "錯誤: --x alpha 需要 --beta B (固定 beta 值)"
            usage
        fi

        PATTERN="${FIXED_TYPE}_pdta${PDTA}_beta_${BETA}_alpha_*.xlsx"
        FILES=( $PATTERN )

        if [ ! -e "${FILES[0]}" ]; then
            echo "錯誤: 找不到符合的檔案: $PATTERN"
            exit 1
        fi

        echo "=== 畫圖: x=alpha  fixed-type=$FIXED_TYPE  fixed=$FIXED  pdta=$PDTA  beta=$BETA ==="
        echo "檔案: ${FILES[*]}"

        python plot_results.py "${FILES[@]}" \
            --x alpha \
            --fixed-type "$FIXED_TYPE" \
            --fixed "$FIXED" \
            "${EXTRA_ARGS[@]}"
        ;;

    *)
        echo "錯誤: --x 必須是 sats、dests、beta 或 alpha"
        usage
        ;;
esac

echo "完成！"
