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

while [ $# -gt 0 ]; do
    case "$1" in
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

if [ -z "$X_TYPE" ]; then
    echo "錯誤: 必須指定 --x sats|dests|beta|alpha"
    usage
fi

EXTRA_ARGS=()
if [ -n "$BREAK_RATIO" ]; then
    EXTRA_ARGS+=(--break-ratio "$BREAK_RATIO")
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
