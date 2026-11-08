"""Tables for Phase 12: python -m ilp.summarize_cloud results/ratio_cloud.csv [compare ...]."""
import sys

import pandas as pd

BINS = [0, 8, 12, 16, 1000]
LABELS = ["C<=8", "9-12", "13-16", ">=17"]


def load(path):
    df = pd.read_csv(path)
    if "C_size" not in df or df.C_size.isna().all():
        df["C_size"] = df.n_c
    df["C_bin"] = pd.cut(df.C_size, BINS, labels=LABELS)
    df["infeas_raw"] = (df.tsmta_raw_feasible == 0)
    df["infeas_opt"] = (df.tsmta_opt_feasible == 0)
    return df


def _ratio(ok, keys):
    g = ok.groupby(keys, observed=True).agg(n=("ratio_opt", "size"), mean_opt=("ratio_opt", "mean"),
                                           max_opt=("ratio_opt", "max"), mean_raw=("ratio_raw", "mean"),
                                           max_raw=("ratio_raw", "max"))
    return g.round(4).to_string()


def _infeas(df, keys):
    g = df.groupby(keys, observed=True).agg(n=("infeas_opt", "size"), infeas_raw=("infeas_raw", "mean"),
                                           infeas_opt=("infeas_opt", "mean"))
    return g.round(4).to_string()


def summarize(path):
    df = load(path)
    out = [f"== {path}: rows={len(df)}",
           f"ILP status: {df.status.value_counts().to_dict()}  "
           f"(not OPTIMAL: {(df.status != 'OPTIMAL').mean():.2%}; hinted: {df.status_hint.value_counts().to_dict()})",
           f"invariant errors: {int((df.invariant_errors.fillna('') != '').sum())}",
           f"C_size: mean={df.C_size.mean():.1f} min={df.C_size.min()} max={df.C_size.max()}; "
           f"max ILP runtime={df.t_ilp.max():.2f}s hinted={df.t_ilp_hint.max():.2f}s"]
    ok = df[df.ratio_opt.notna() & df.ratio_raw.notna()]
    out.append(f"-- a. ratio (TSMTA-feasible rows only; opt & raw both feasible: n={len(ok)} "
               f"of {len(df)}); overall mean_opt={df.ratio_opt.mean():.4f} max_opt={df.ratio_opt.max():.4f}"
               f" (opt-feasible n={df.ratio_opt.notna().sum()})")
    okopt = df[df.ratio_opt.notna()]
    for keys in (["alpha", "beta"], ["n_clouds"], ["C_bin"]):
        out.append(f"by {keys} (Optimal ratio; raw ratio uses rows with raw feasible):")
        g = okopt.groupby(keys, observed=True).agg(
            n=("ratio_opt", "size"), mean_opt=("ratio_opt", "mean"), max_opt=("ratio_opt", "max"),
            frac_gt1=("ratio_opt", lambda x: (x > 1 + 1e-9).mean()), mean_raw=("ratio_raw", "mean"),
            max_raw=("ratio_raw", "max"))
        out.append(g.round(4).to_string())
    out.append(f"-- b. TSMTA infeasible: raw={df.infeas_raw.mean():.2%} ({int(df.infeas_raw.sum())}) "
               f"optimal={df.infeas_opt.mean():.2%} ({int(df.infeas_opt.sum())})   [n_clouds=0 baseline: 14.8% / 189 of 1280]")
    for keys in (["alpha", "beta"], ["n_clouds"], ["C_bin"], ["n_sats"], ["n_dests"], ["T"]):
        out.append(f"by {keys}:\n" + _infeas(df, keys))
    for tag, col in (("raw", "tsmta_raw_feasible"), ("optimal", "tsmta_opt_feasible")):
        pass
    v = df.tsmta_violations.fillna("")
    kinds = {"raw": {}, "optimal": {}}
    for s in v:
        for part in s.split():
            name, _, ks = part.partition(":")
            for k in ks.split("+"):
                kinds[name][k] = kinds[name].get(k, 0) + 1
    out.append(f"-- c. violation kinds (rows containing each kind): {kinds}")
    combos = v[v != ""].str.replace(r"(raw|optimal):", r"\1=", regex=True).value_counts()
    out.append("   violation combos per row:\n" + combos.head(10).to_string())
    pr = {}
    for tag in ("raw", "opt"):
        col = df[f"prune_feasible_{tag}"]
        bad = df[~df[f"tsmta_{tag}_feasible"].astype(bool)]
        b = bad[f"prune_feasible_{tag}"]
        pr[tag] = dict(infeasible=len(bad), prune_feasible=int((b.astype(str) == "1").sum()),
                       dest_disconnected_from_s=int((bad[f"dest_disconnected_{tag}"] == 1).sum()),
                       prune_error=int((b.astype(str) == "error").sum()))
    out.append(f"-- d. prune diagnostic (not merged into the tables above): {pr}")
    return "\n".join(out)


def compare(small, cloud, cloud0):
    """Step 4: infeasible fraction, sample vs repo, same (n_sats, |D|, T, alpha, beta, seed)."""
    a, b, c = load(small), load(cloud), load(cloud0)
    a = a.assign(setting="sample(n_clouds=0, |C|=n_c)")
    b = b.assign(setting="repo(n_clouds>0)")
    c = c.assign(setting="repo(n_clouds=0)")
    allr = pd.concat([a, b, c], ignore_index=True)
    out = ["== step 4: infeasible rate by setting"]
    g = allr.groupby("setting").agg(n=("infeas_opt", "size"), raw=("infeas_raw", "mean"), opt=("infeas_opt", "mean"))
    out.append(g.round(4).to_string())
    for keys in (["n_sats"], ["n_dests"], ["T"], ["alpha", "beta"]):
        t = allr.groupby(["setting"] + keys).infeas_opt.mean().unstack(0).round(4)
        out.append(f"by {keys} (Optimal infeasible rate):\n" + t.to_string())
    t = allr.groupby(["setting", "n_c", "n_clouds"], dropna=False).infeas_opt.agg(["size", "mean"]).round(4)
    out.append("by setting x n_c x n_clouds:\n" + t.to_string())
    key = ["n_sats", "n_dests", "T", "alpha", "beta", "seed"]
    ac = a.groupby(key).infeas_opt.mean().rename("sample")
    cc = c.groupby(key).infeas_opt.mean().rename("repo0")
    m = pd.concat([ac, cc], axis=1).dropna()
    out.append(f"paired on identical graph (same seed, n_clouds=0): cells={len(m)}  "
               f"sample-infeasible-rate={m['sample'].mean():.4f}  repo-infeasible-rate={m.repo0.mean():.4f}  "
               f"both feasible/infeasible per cell: sample>repo in {(m['sample'] > m.repo0).sum()}, "
               f"repo>sample in {(m.repo0 > m['sample']).sum()}, equal in {(m.repo0 == m['sample']).sum()}")
    return "\n".join(out)


if __name__ == "__main__":
    if sys.argv[1] == "compare":
        print(compare(*sys.argv[2:5]))
    else:
        print(summarize(sys.argv[1]))
