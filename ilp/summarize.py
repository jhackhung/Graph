"""Summarize results/ratio_*.csv into text tables (used for PROGRESS.md / ILP_RESULTS.md)."""
import sys

import pandas as pd


def summarize(path):
    df = pd.read_csv(path)
    n = len(df)
    out = [f"rows={n}"]
    out.append(f"ILP status: {df.status.value_counts().to_dict()}")
    out.append(f"TSMTA infeasible: raw={int((df.tsmta_raw_feasible == 0).sum())} "
               f"optimal={int((df.tsmta_opt_feasible == 0).sum())}")
    viol = df.tsmta_violations.fillna("").str.split().explode()
    out.append(f"violation kinds: {viol[viol != ''].value_counts().to_dict()}")
    ok = df[df.ratio_opt.notna()].copy()
    ok["ratio_opt_gt1"] = ok.ratio_opt > 1 + 1e-9
    g = ok.groupby(["alpha", "beta"]).agg(n=("ratio_opt", "size"), mean_opt=("ratio_opt", "mean"),
                                           max_opt=("ratio_opt", "max"),
                                           mean_raw=("ratio_raw", "mean"), max_raw=("ratio_raw", "max"),
                                           frac_gt1=("ratio_opt_gt1", "mean"))
    out.append("by (alpha,beta):\n" + g.round(4).to_string())
    g = ok.groupby("n_sats").agg(n=("ratio_opt", "size"), mean_opt=("ratio_opt", "mean"),
                                 max_opt=("ratio_opt", "max"), mean_raw=("ratio_raw", "mean"),
                                 max_raw=("ratio_raw", "max"), t_ilp=("t_ilp", "max"),
                                 vars_=("n_vars", "mean"))
    out.append("by n_sats:\n" + g.round(4).to_string())
    out.append(f"overall: mean_opt={ok.ratio_opt.mean():.4f} max_opt={ok.ratio_opt.max():.4f} "
               f"mean_raw={ok.ratio_raw.mean():.4f} max_raw={ok.ratio_raw.max():.4f}")
    hint = df[df.status_hint.notna()]
    out.append(f"hint: mean t_ilp={hint.t_ilp.mean():.3f}s vs hinted={hint.t_ilp_hint.mean():.3f}s; "
               f"objective equal in {(abs(hint.TC_ilp - hint.TC_ilp_hint) < 1e-9).mean():.3%}")
    out.append(f"max ILP runtime={df.t_ilp.max():.2f}s; redraws mean={df.redraws.mean():.2f} max={df.redraws.max()}")
    return "\n".join(out)


if __name__ == "__main__":
    print(summarize(sys.argv[1]))
