#!/usr/bin/env python3
"""
把各 seed 的 checkpoint 合併成一份 Excel。

為什麼不直接合併各 task 的 xlsx:
每個 task 只跑 1 run,它寫出的 mean 就是那一個 run 的值、std 是 0。
把這些 mean 再平均雖然能得到正確的 mean,std 卻會完全錯掉。
所以這裡改從 checkpoint JSON 讀「原始 per-run 值」,收齊之後再一次算統計。
"""
import argparse
import glob
import json
import os
import statistics
import sys
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from Save_And_Read_Graphs import save_result_to_excel  # noqa: E402

METRICS = ["BC", "CC", "RC", "Total", "Build_Runtime_sec", "Beta_Runtime_sec"]


def collect(runs_glob: str):
    """掃各 seed 目錄的 checkpoint,把 per-run 原始值串起來。"""
    # pooled[(beta, alpha, algo)][metric] = [每個 seed 的值...]
    pooled = defaultdict(lambda: defaultdict(list))
    seeds_seen = []

    paths = sorted(glob.glob(os.path.join(runs_glob, "**", "checkpoint_*.json"),
                             recursive=True))
    if not paths:
        raise SystemExit(f"找不到任何 checkpoint: {runs_glob}")

    for path in paths:
        # 只跳過壞掉的檔,其他 seed 照常合併
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception as e:
            print(f"  ! 跳過損毀的 checkpoint {path}: {type(e).__name__}: {e}")
            continue

        completed = payload.get("completed_runs", 0)
        if completed < 1:
            print(f"  ! 跳過未完成的 {path} (completed_runs={completed})")
            continue

        seeds_seen.append(path)
        results = payload["all_results"]
        for beta_tag, by_alpha in results.items():
            for alpha_tag, by_algo in by_alpha.items():
                for algo, metrics in by_algo.items():
                    for m in METRICS:
                        vals = metrics.get(m) or []
                        pooled[(beta_tag, alpha_tag, algo)][m].extend(vals)

    return pooled, seeds_seen


def mean_std(vals):
    if not vals:
        return 0.0, 0.0
    mean = statistics.fmean(vals)
    std = statistics.stdev(vals) if len(vals) > 1 else 0.0
    return mean, std


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default="runs", help="各 seed 工作目錄的根目錄")
    ap.add_argument("--out", required=True, help="輸出 xlsx")
    ap.add_argument("--n-sats", type=int, required=True)
    ap.add_argument("--pdta-k", type=int, required=True)
    ap.add_argument("--base-seed", type=int, default=42)
    args = ap.parse_args()

    pooled, sources = collect(args.runs)
    print(f"合併了 {len(sources)} 個 checkpoint")

    if os.path.exists(args.out):
        raise SystemExit(f"{args.out} 已存在,請先移走以免混入舊資料")

    for (beta_tag, alpha_tag, algo), metrics in sorted(pooled.items()):
        n = len(metrics.get("BC") or [])
        if n == 0:
            continue

        row = {
            "experiment_id": None,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "graph": f"graph_{args.n_sats}_avg{n}",
            "algo": algo,
            "beta": float(beta_tag.replace("p", ".")),
            "alpha": float(alpha_tag.replace("p", ".")),
            "PDTA_k": args.pdta_k,
            "base_seed": args.base_seed,
            "num_runs": n,
        }

        for m in METRICS:
            mean, std = mean_std(metrics.get(m) or [])
            row[m] = mean
            # 欄名沿用既有 xlsx 的慣例,plot_results.py 才讀得到
            std_key = {
                "BC": "BC_Std", "CC": "CC_Std", "RC": "RC_Std",
                "Total": "Total_Std",
                "Build_Runtime_sec": "Build_Runtime_Std",
                "Beta_Runtime_sec": "Beta_Runtime_Std",
            }[m]
            row[std_key] = std

        row["Total_Runtime_sec"] = row["Build_Runtime_sec"] + row["Beta_Runtime_sec"]

        save_result_to_excel(args.out, row)
        print(f"  {algo:16s} beta={beta_tag} alpha={alpha_tag} "
              f"n={n:3d} Total={row['Total']:.2f} ± {row['Total_Std']:.2f}")

    print(f"\n完成 -> {args.out}")


if __name__ == "__main__":
    main()
