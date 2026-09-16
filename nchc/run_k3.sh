#!/bin/bash
#SBATCH --job-name=sats_k3
#SBATCH --account=acd109125
#SBATCH --partition=ct56
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=24G
#SBATCH --time=4-00:00:00
#SBATCH --array=0-99%20
#SBATCH --output=logs/k3_%A_%a.out
#SBATCH --error=logs/k3_%A_%a.err
#
# 100 seed x (300 sats, 100 dests, k=3)
# 一個 array task = 一個 seed = 一個獨立 process/目錄。
#
# --time 與 --mem 請先用 probe_k2.sh 的實測值校正後再送。
# %20 限制同時併發數：每個 task 峰值記憶體數 GB,開太多會吃爆節點。

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

BASE_SEED=42
SEED=$((BASE_SEED + SLURM_ARRAY_TASK_ID))
NSATS=300
NDESTS=100
WORKDIR="runs/k3_seed${SEED}"

mkdir -p "$WORKDIR"

python nchc/make_config.py \
    --base configs/realistic_54sats.json \
    --out "$WORKDIR/config.json" \
    --seed "$SEED" \
    --n-sats "$NSATS" \
    --n-dests "$NDESTS" \
    --pdta-level 3 \
    --beta 10 --alpha 5 \
    --algos all \
    --tig-cache-dir "$SLURM_SUBMIT_DIR/tig_cache_sats"

cd "$WORKDIR"
for f in "$SLURM_SUBMIT_DIR"/*.py; do ln -sf "$f" .; done

export PYTHONHASHSEED=$SEED
export PYTHONUNBUFFERED=1

echo "=== start $(date -Is) | task=$SLURM_ARRAY_TASK_ID seed=$SEED n_sats=$NSATS k=3 ==="
srun python main.py config.json
echo "=== done  $(date -Is) | seed=$SEED ==="
