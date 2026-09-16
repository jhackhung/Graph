#!/bin/bash
#SBATCH --job-name=sats_k2_probe
#SBATCH --account=acd109125
#SBATCH --partition=ct56
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=24G
#SBATCH --time=2-00:00:00
#SBATCH --output=logs/probe_k2_%j.out
#SBATCH --error=logs/probe_k2_%j.err
#
# 單 seed / k=2 探測：目的是量出 300 sats 下的
#   (1) 單 run wall time
#   (2) peak RSS
# 這兩個數字用來校正 k=3 正式腳本的 --time 與 --mem。

set -euo pipefail

module purge
module load miniconda3
# 非互動式 shell 沒跑過 conda 的 shell hook，直接 `conda activate`
# 會 command not found。先 source conda.sh 才能用。
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate satgraph
python -c 'import networkx,numpy,pandas,openpyxl' \n    || { echo 'ERROR: conda 環境 satgraph 未就緒或套件缺失' >&2; exit 1; }

cd "$SLURM_SUBMIT_DIR"
mkdir -p logs

SEED=42
NSATS=300
NDESTS=100
WORKDIR="runs/probe_k2_seed${SEED}"

rm -rf "$WORKDIR"
mkdir -p "$WORKDIR"

python nchc/make_config.py \
    --base configs/realistic_54sats.json \
    --out "$WORKDIR/config.json" \
    --seed "$SEED" \
    --n-sats "$NSATS" \
    --n-dests "$NDESTS" \
    --pdta-level 2 \
    --beta 10 --alpha 5 \
    --algos all \
    --tig-cache-dir "$SLURM_SUBMIT_DIR/tig_cache_sats"

# 每個 task 在自己的目錄下跑：main.py 的 Excel 與 checkpoint 都是
# 相對 CWD 的固定檔名,換目錄才能避免互相覆蓋。
cd "$WORKDIR"
for f in "$SLURM_SUBMIT_DIR"/*.py; do ln -sf "$f" .; done

export PYTHONHASHSEED=$SEED
export PYTHONUNBUFFERED=1

echo "=== start $(date -Is) | seed=$SEED n_sats=$NSATS k=2 ==="
/usr/bin/time -v python main.py config.json
echo "=== done  $(date -Is) ==="
