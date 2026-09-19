#!/usr/bin/env python3
"""
看實驗的整體進度。

進度來源有三個,互補:
  1. squeue        -> Slurm 層面:誰在跑、誰在排隊
  2. checkpoint    -> 哪些 seed 已經完整跑完
  3. 各 task 的 log -> 正在跑的那些做到哪了

checkpoint 只在整個 run 結束才寫,所以「跑到一半」的進度只能從 log 看。

用法:
    python nchc/progress.py                 # 全部
    python nchc/progress.py --job 2105843   # 指定 job
    python nchc/progress.py --pending       # 只印待跑的 task id(給 sbatch --array 用)
"""
import argparse
import getpass
import glob
import json
import os
import re
import subprocess
import sys
from collections import Counter

# main.py 把 checkpoint 寫在 DIR_PATH 底下,不是工作目錄根部
CHECKPOINT_SUBDIR = "output_graphs_sats"
PROGRESS_PAT = re.compile(r"Build|Evaluate|Run \d+/|TIG|Select")


def seed_dir(runs_dir: str, prefix: str, seed: int) -> str:
    return os.path.join(runs_dir, f"{prefix}{seed}")


def is_done(runs_dir: str, prefix: str, seed: int) -> bool:
    """該 seed 是否已完成:checkpoint 存在且 completed_runs >= 1。"""
    pattern = os.path.join(seed_dir(runs_dir, prefix, seed),
                           CHECKPOINT_SUBDIR, "checkpoint_*.json")
    for path in glob.glob(pattern):
        try:
            with open(path, "r", encoding="utf-8") as f:
                if json.load(f).get("completed_runs", 0) >= 1:
                    return True
        except Exception:
            # 壞掉或寫到一半的 JSON 一律當成未完成
            continue
    return False


def squeue_states(jobid: str | None, user: str) -> Counter | None:
    """回傳 {狀態: 數量};squeue 不存在(例如在本機)時回傳 None。"""
    cmd = ["squeue", "-h", "-o", "%t"]
    cmd += ["-j", jobid] if jobid else ["-u", user]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return Counter()
    return Counter(line.strip() for line in out.stdout.splitlines() if line.strip())


def tail_progress(log_path: str) -> tuple[str, str]:
    """從 log 撈 seed 與最後一行進度訊息。"""
    seed, last = "?", ""
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if seed == "?":
                    m = re.search(r"seed=(\d+)", line)
                    if m:
                        seed = m.group(1)
                if PROGRESS_PAT.search(line):
                    last = line.strip()
    except OSError:
        pass
    return seed, last[:90]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", help="只看這個 JOBID")
    ap.add_argument("--runs", default="runs", help="各 seed 工作目錄的根目錄")
    ap.add_argument("--prefix", default="k3_seed", help="工作目錄前綴")
    ap.add_argument("--base-seed", type=int, default=42)
    ap.add_argument("--n-tasks", type=int, default=100)
    ap.add_argument("--logs", default="logs", help="log 目錄")
    ap.add_argument("--log-glob", default="k3_*.out")
    ap.add_argument("--pending", action="store_true",
                    help="只印待跑的 task id(逗號分隔),給 sbatch --array 用")
    args = ap.parse_args()

    seeds = range(args.base_seed, args.base_seed + args.n_tasks)
    done = [s for s in seeds if is_done(args.runs, args.prefix, s)]
    pending_ids = [i for i, s in enumerate(seeds) if s not in set(done)]

    # --pending: 只輸出 id,方便直接餵給 sbatch
    if args.pending:
        if not pending_ids:
            print("所有 task 皆已完成", file=sys.stderr)
            sys.exit(1)
        print(",".join(str(i) for i in pending_ids))
        return

    print("=" * 20, "Slurm 佇列", "=" * 20)
    states = squeue_states(args.job, getpass.getuser())
    if states is None:
        print("  (找不到 squeue,略過;在登入節點上才看得到)")
    elif not states:
        print("  (佇列中沒有相符的 job,可能已全部結束)")
    else:
        label = {"R": "RUNNING", "PD": "PENDING", "CG": "COMPLETING"}
        for st, n in sorted(states.items()):
            print(f"  {label.get(st, st):<10}: {n}")

    print()
    print("=" * 20, "完成度", "=" * 20)
    pct = len(done) / args.n_tasks * 100 if args.n_tasks else 0.0
    bar_len = 30
    filled = int(bar_len * len(done) / args.n_tasks) if args.n_tasks else 0
    print(f"  [{'#' * filled}{'.' * (bar_len - filled)}] "
          f"{len(done)}/{args.n_tasks} ({pct:.0f}%)")
    if pending_ids and len(pending_ids) <= 20:
        print(f"  待跑 task id: {','.join(str(i) for i in pending_ids)}")

    print()
    print("=" * 12, "正在跑的 task 各自做到哪", "=" * 12)
    logs = sorted(glob.glob(os.path.join(args.logs, args.log_glob)),
                  key=lambda p: os.path.getmtime(p), reverse=True)[:10]
    if not logs:
        print("  (還沒有 log)")
    else:
        for path in logs:
            seed, last = tail_progress(path)
            print(f"  {os.path.basename(path):<24} seed={seed:<6} "
                  f"{last or '(尚無輸出)'}")


if __name__ == "__main__":
    main()
