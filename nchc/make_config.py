#!/usr/bin/env python3
"""
從 base config 產生單一 task 專用的 config。

每個 Slurm task 只跑一個 seed (num_runs=1)，輸出寫進自己的工作目錄，
藉此避開 main.py 裡 Excel / checkpoint 以固定檔名寫入所造成的競爭。
"""
import argparse
import json


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True, help="base config json")
    ap.add_argument("--out", required=True, help="輸出的 config 路徑")
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--n-sats", type=int, required=True)
    ap.add_argument("--n-dests", type=int, required=True)
    ap.add_argument("--pdta-level", type=int, required=True)
    ap.add_argument("--beta", type=float, default=10.0)
    ap.add_argument("--alpha", type=float, default=5.0)
    ap.add_argument("--algos", default="all")
    ap.add_argument("--tig-cache-dir", default=None,
                    help="不給就沿用 base config 的設定")
    args = ap.parse_args()

    with open(args.base, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    # base config 裡那串很長的 _comment 對執行沒有用，去掉讓 log 好讀
    cfg.pop("_comment", None)

    cfg.update(
        n_sats=args.n_sats,
        n_dests=args.n_dests,
        sweep_x="sats",
        pdta_level=args.pdta_level,
        beta_values=[args.beta],
        alpha_values=[args.alpha],
        algos=args.algos,
        # 一個 task 一個 seed：base_seed 就是這個 seed，只跑 1 run
        base_seed=args.seed,
        num_runs=1,
    )
    # run.sh 用的 sweep 欄位在單點實驗沒有意義，移掉避免誤導
    for key in ("pdta_levels", "start_sats", "step_sats", "start_dests", "step_dests"):
        cfg.pop(key, None)

    if args.tig_cache_dir:
        cfg["tig_cache_dir"] = args.tig_cache_dir

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

    print(f"[make_config] seed={args.seed} n_sats={args.n_sats} "
          f"n_dests={args.n_dests} k={args.pdta_level} algos={args.algos} -> {args.out}")


if __name__ == "__main__":
    main()
