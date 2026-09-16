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
# 非互動式 shell 沒跑過 conda 的 shell hook，`conda activate` 會
# command not found。先 source conda.sh 才能用 activate。
source "$(conda info --base 2>/dev/null || echo ${CONDA_PREFIX:-/opt/conda})/etc/profile.d/conda.sh"
conda activate satgraph
python -c 'import networkx,numpy,pandas,openpyxl' \n    || { echo 'ERROR: conda 環境 satgraph 未就緒或套件缺失' >&2; exit 1; }

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

echo "--- 產出檔 ---"
ls -la *.xlsx
# checkpoint 寫在 main.py 的 DIR_PATH 底下，不是 CWD
ls -la output_graphs_sats/checkpoint_*.json
