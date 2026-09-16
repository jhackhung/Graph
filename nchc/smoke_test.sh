#!/bin/bash
#SBATCH --job-name=sats_smoke
#SBATCH --account=acd109125
#SBATCH --partition=ctest
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=24G
#SBATCH --time=2:00:00
#SBATCH --output=logs/smoke_%j.out
#SBATCH --error=logs/smoke_%j.err
#
# 冒煙測試：用小規模 (50 sats, k=1) 確認環境、路徑、輸出、合併流程都正確。
# 跑在 ctest 佇列(上限 2 小時,排隊最快),目的不是量效能,而是及早抓到
# 「conda 環境沒裝好 / module 名稱錯 / 路徑寫錯」這類設定問題。

set -euo pipefail

module purge
module load miniconda3
conda activate satgraph

cd "$SLURM_SUBMIT_DIR"
mkdir -p logs

SEED=42
WORKDIR="runs/smoke_seed${SEED}"
rm -rf "$WORKDIR"
mkdir -p "$WORKDIR"

python nchc/make_config.py \
    --base configs/realistic_54sats.json \
    --out "$WORKDIR/config.json" \
    --seed "$SEED" \
    --n-sats 50 \
    --n-dests 100 \
    --pdta-level 1 \
    --beta 10 --alpha 5 \
    --algos all \
    --tig-cache-dir "$SLURM_SUBMIT_DIR/tig_cache_smoke"

cd "$WORKDIR"
for f in "$SLURM_SUBMIT_DIR"/*.py; do ln -sf "$f" .; done

export PYTHONHASHSEED=$SEED
export PYTHONUNBUFFERED=1

echo "=== smoke start $(date -Is) ==="
/usr/bin/time -v python main.py config.json
echo "=== smoke done $(date -Is) ==="

ls -la *.xlsx checkpoint_*.json
