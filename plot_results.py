#!/usr/bin/env python3
import sys
import os
import re
import argparse
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator

matplotlib.use("Agg")  # Use non-interactive backend for PNG/PDF output

# Existing modes:
#   python plot_results_beta.py results_ns300_nc20_nd50_p72_t10_avg_std.xlsx --x sats --break-ratio 1
#   python plot_results_beta.py results_ns300_nc20_nd50_p72_t10_avg_std.xlsx --x dests --break-ratio 1
#
# New beta mode: fixed satellites or fixed destinations, x-axis = beta
#   python plot_results_beta.py sats_beta_*.xlsx  --x beta --fixed-type sats  --fixed 300 --break-ratio 1
#   python plot_results_beta.py dests_beta_*.xlsx --x beta --fixed-type dests --fixed 50  --break-ratio 1

# ===== Global font settings =====
plt.rcParams.update({
    "font.size": 25,
    "axes.titlesize": 30,
    "axes.labelsize": 30,
    "xtick.labelsize": 25,
    "ytick.labelsize": 25,
    "legend.fontsize": 22,
    "lines.linewidth": 2.4,
    "axes.linewidth": 1.1,
    "xtick.major.width": 1.0,
    "ytick.major.width": 1.0,
    "xtick.major.size": 4,
    "ytick.major.size": 4,
    "pdf.fonttype": 42,
    "ps.fonttype": 42
})

# ===== Default x-axis range for original sats/dests mode =====
X_START = 50
X_END = 450
X_STEP = 100

# OffPA must be this many times larger than other methods to use broken y-axis
BREAK_RATIO = 5.0

# ===== Figure output settings =====
FIG_WIDTH = 8.8
FIG_HEIGHT = 6.8
PNG_DPI = 600

STYLES = {
    "DMTS": {
        "color": "blue",
        "marker": "o",
        "linestyle": "-",
        "linewidth": 2.6,
        "markersize": 6
    },
    "TSMTA": {
        "color": "red",
        "marker": "s",
        "linestyle": "--",
        "linewidth": 2.6,
        "markersize": 6
    },
    "SSSP": {
        "color": "green",
        "marker": "^",
        "linestyle": "-.",
        "linewidth": 2.6,
        "markersize": 6
    },
    "OffPA": {
        "color": "orange",
        "marker": "D",
        "linestyle": ":",
        "linewidth": 2.6,
        "markersize": 6
    }
}


def get_x_config(x_type):
    if x_type == "sats":
        return {
            "x_col": "sat_num",
            "x_label": "Number of Satellites"
        }

    if x_type == "dests":
        return {
            "x_col": "dest_num",
            "x_label": "Number of Destinations"
        }

    if x_type == "beta":
        return {
            "x_col": "beta_pos",
            "x_label": "Beta (β)"
        }
    
    if x_type == "alpha":
        return {
            "x_col": "alpha_pos",
            "x_label": "Alpha (α)"
        }

    raise ValueError("x_type must be 'sats', 'dests', 'beta', or 'alpha'.")


def format_number_label(value):
    """Format 1.0 as '1', but keep non-integers such as 0.5."""
    try:
        value_float = float(value)
        if value_float.is_integer():
            return str(int(value_float))
        return str(value_float)
    except Exception:
        return str(value)


def extract_beta_from_path(path):
    """
    Extract beta value from names like:
        sats_beta_1.xlsx, dests_beta_10.xlsx, xxx_beta_50_avg.xlsx
    """
    basename = os.path.basename(path)
    match = re.search(r"beta_([0-9]+(?:\.[0-9]+)?)", basename)
    if not match:
        raise ValueError(f"Cannot extract beta from filename: {basename}")
    return float(match.group(1))

def extract_alpha_from_path(path):
    """
    Extract alpha value from names like:
        sats_alpha_1.xlsx, dests_alpha_10.xlsx, xxx_alpha_50_avg.xlsx
    目前假設傳入資料為固定 beta 的 excel 檔案，並且檔名中包含 alpha_ 數值
    """
    basename = os.path.basename(path)
    match = re.search(r"alpha_([0-9]+(?:\.[0-9]+)?)", basename)
    if not match:
        raise ValueError(f"Cannot extract alpha from filename: {basename}")
    return float(match.group(1))

def extract_pdta_from_path(path):
    """
    Extract pdta level from names like:
        sats_pdta3_beta_100_alpha_1.xlsx
    """
    basename = os.path.basename(path)
    match = re.search(r"pdta(\d+)", basename)
    if not match:
        raise ValueError(f"Cannot extract pdta level from filename: {basename}")
    return int(match.group(1))


def infer_fixed_type_from_paths(paths):
    basenames = [os.path.basename(p).lower() for p in paths]
    if all(name.startswith("sats_") for name in basenames):
        return "sats"
    if all(name.startswith("dests_") for name in basenames):
        return "dests"
    return None


def parse_graph_num(df, output_col):
    """
    Parse graph count from graph column.
    Supports graph_50, graph_50_avg1, graph_300_avg_std, etc.
    """
    extracted = df["graph"].astype(str).str.extract(r"graph_(\d+)")[0]
    if extracted.isna().any():
        bad_values = df.loc[extracted.isna(), "graph"].head(5).tolist()
        raise ValueError(f"Cannot parse graph number from graph values: {bad_values}")
    df[output_col] = extracted.astype(int)
    return df


def load_single_excel_for_original_mode(excel_path, x_col):
    df = pd.read_excel(excel_path)
    df = parse_graph_num(df, x_col)
    return df


def load_beta_excels(excel_paths, fixed_type, fixed_value):
    """
    New beta mode:
      - Read multiple beta files.
      - Extract beta from filename.
      - Extract graph number from graph column.
      - Keep only rows where graph number == fixed_value.
      - Map beta values to equally spaced categorical x positions.
    """
    fixed_col = "sat_num" if fixed_type == "sats" else "dest_num"
    frames = []

    for path in excel_paths:
        if not os.path.exists(path):
            raise FileNotFoundError(path)

        beta = extract_beta_from_path(path)
        df = pd.read_excel(path)
        df = parse_graph_num(df, fixed_col)
        df["beta"] = beta
        df["source_file"] = os.path.basename(path)

        df_fixed = df[df[fixed_col] == fixed_value].copy()
        if df_fixed.empty:
            print(f"⚠ Warning: {os.path.basename(path)} has no {fixed_col} == {fixed_value}")
            continue

        frames.append(df_fixed)

    if not frames:
        raise ValueError(
            f"No rows found after filtering fixed {fixed_type} value = {fixed_value}."
        )

    merged = pd.concat(frames, ignore_index=True)
    beta_values = sorted(merged["beta"].unique())
    beta_to_pos = {beta: idx for idx, beta in enumerate(beta_values)}

    merged["beta_pos"] = merged["beta"].map(beta_to_pos)

    x_ticks = [beta_to_pos[beta] for beta in beta_values]
    x_tick_labels = [format_number_label(beta) for beta in beta_values]

    print(f"📌 Fixed {fixed_type}: {fixed_value}")
    print(f"📌 Beta values: {x_tick_labels}")

    return merged, x_ticks, x_tick_labels

def load_alpha_excels(excel_paths, fixed_type, fixed_value):
    """
    New alpha mode:
      - Read multiple alpha files.
      - Extract alpha from filename.
      - Extract graph number from graph column.
      - Keep only rows where graph number == fixed_value.
      - Map alpha values to equally spaced categorical x positions.
    """
    fixed_col = "sat_num" if fixed_type == "sats" else "dest_num"
    frames = []

    for path in excel_paths:
        if not os.path.exists(path):
            raise FileNotFoundError(path)

        alpha = extract_alpha_from_path(path)
        df = pd.read_excel(path)
        df = parse_graph_num(df, fixed_col)
        df["alpha"] = alpha
        df["source_file"] = os.path.basename(path)

        df_fixed = df[df[fixed_col] == fixed_value].copy()
        if df_fixed.empty:
            print(f"⚠ Warning: {os.path.basename(path)} has no {fixed_col} == {fixed_value}")
            continue

        frames.append(df_fixed)

    if not frames:
        raise ValueError(
            f"No rows found after filtering fixed {fixed_type} value = {fixed_value}."
        )

    merged = pd.concat(frames, ignore_index=True)
    alpha_values = sorted(merged["alpha"].unique())
    alpha_to_pos = {alpha: idx for idx, alpha in enumerate(alpha_values)}

    merged["alpha_pos"] = merged["alpha"].map(alpha_to_pos)

    x_ticks = [alpha_to_pos[alpha] for alpha in alpha_values]
    x_tick_labels = [format_number_label(alpha) for alpha in alpha_values]

    print(f"📌 Fixed {fixed_type}: {fixed_value}")
    print(f"📌 Alpha values: {x_tick_labels}")

    return merged, x_ticks, x_tick_labels

def collect_plot_data(df, metric, x_col, selected_points):
    low_algos = ["DMTS", "TSMTA", "SSSP"]
    high_algos = ["OffPA"]
    algos = low_algos + high_algos

    std_col = f"{metric}_Std"
    plot_data = {}

    for algo in algos:
        df_algo = df[df["algo"] == algo].sort_values(x_col)
        df_algo = df_algo[df_algo[x_col].isin(selected_points)]

        if df_algo.empty:
            print(f"⚠ Warning: No data for {algo} in {metric}")
            continue

        x = df_algo[x_col]
        y = df_algo[metric] / 1000.0

        if std_col in df_algo.columns and df_algo[std_col].notna().any():
            y_err = (df_algo[std_col] / 1000.0).fillna(0.0)
        else:
            y_err = None

        plot_data[algo] = {
            "x": x,
            "y": y,
            "y_err": y_err
        }

    return plot_data


def should_use_broken_axis(plot_data, break_ratio):
    """
    Use broken y-axis only when OffPA is clearly separated from
    DMTS / TSMTA / SSSP.

    Condition:
        min(OffPA) / max(DMTS, TSMTA, SSSP) >= break_ratio
    """
    low_algos = ["DMTS", "TSMTA", "SSSP"]

    low_values = []
    high_values = []

    for algo in low_algos:
        if algo in plot_data:
            low_values.extend(list(plot_data[algo]["y"]))

    if "OffPA" in plot_data:
        high_values.extend(list(plot_data["OffPA"]["y"]))

    if not low_values or not high_values:
        return False

    low_max = max(low_values)
    high_min = min(high_values)

    if low_max <= 0:
        return False

    ratio = high_min / low_max
    print(f"🔎 OffPA separation ratio = {ratio:.2f}")

    return ratio >= break_ratio


def add_top_legend(fig, axes):
    """Merge legends from all axes and place it at the top of the figure."""
    handles = []
    labels = []

    for ax in axes:
        h, l = ax.get_legend_handles_labels()
        handles.extend(h)
        labels.extend(l)

    unique = dict(zip(labels, handles))

    fig.legend(
        unique.values(),
        unique.keys(),
        loc="upper center",
        bbox_to_anchor=(0.53, 1.02),
        ncol=4,
        frameon=True,
        fontsize=19,
        markerscale=1.5,
        handlelength=2.5,
        handletextpad=0.7,
        columnspacing=1.1,
        borderpad=0.45,
        labelspacing=0.4
    )


def save_figure(output_path):
    plt.savefig(output_path, dpi=PNG_DPI, bbox_inches="tight", pad_inches=0.02)

    pdf_path = os.path.splitext(output_path)[0] + ".pdf"
    plt.savefig(pdf_path, bbox_inches="tight", pad_inches=0.02)

    print(f"📊 Saved PNG: {output_path}")
    print(f"📄 Saved PDF: {pdf_path}")

    plt.close()


def configure_x_axis(ax, x_ticks, x_tick_labels, x_label):
    if len(x_ticks) == 1:
        margin = 0.5
    else:
        margin = max(0.5, (max(x_ticks) - min(x_ticks)) * 0.05)

    ax.set_xlim(min(x_ticks) - margin, max(x_ticks) + margin)
    ax.set_xticks(x_ticks)
    ax.set_xticklabels(x_tick_labels)
    ax.set_xlabel(x_label, labelpad=6)


def plot_metric_normal(
    plot_data,
    metric,
    output_path,
    x_ticks,
    x_tick_labels,
    x_label
):
    """Normal y-axis figure."""
    fig, ax = plt.subplots(figsize=(FIG_WIDTH, FIG_HEIGHT))

    algos = ["DMTS", "TSMTA", "SSSP", "OffPA"]

    for algo in algos:
        if algo not in plot_data:
            continue

        data = plot_data[algo]

        ax.errorbar(
            data["x"],
            data["y"],
            yerr=data["y_err"],
            label=algo,
            capsize=4,
            elinewidth=1.3,
            markeredgewidth=0.9,
            **STYLES[algo]
        )

    configure_x_axis(ax, x_ticks, x_tick_labels, x_label)
    ax.set_ylabel(f"{metric} (K)", labelpad=6)

    ax.grid(True, linestyle="--", alpha=0.7)
    ax.tick_params(axis="both", which="major", labelsize=25)
    ax.yaxis.set_major_locator(MaxNLocator(nbins=5))

    add_top_legend(fig, [ax])
    plt.tight_layout(rect=(0.02, 0.02, 1, 0.93), pad=0.6)

    save_figure(output_path)


def plot_metric_broken(
    plot_data,
    metric,
    output_path,
    x_ticks,
    x_tick_labels,
    x_label
):
    """
    Broken y-axis version:
    - ax_bottom: DMTS / TSMTA / SSSP
    - ax_top: OffPA
    """
    fig, (ax_top, ax_bottom) = plt.subplots(
        2, 1,
        sharex=True,
        figsize=(FIG_WIDTH, FIG_HEIGHT),
        gridspec_kw={
            "height_ratios": [1, 3],
            "hspace": 0.08
        }
    )

    low_algos = ["DMTS", "TSMTA", "SSSP"]

    for algo in low_algos:
        if algo not in plot_data:
            continue

        data = plot_data[algo]

        ax_bottom.errorbar(
            data["x"],
            data["y"],
            yerr=data["y_err"],
            label=algo,
            capsize=4,
            elinewidth=1.3,
            markeredgewidth=0.9,
            **STYLES[algo]
        )

    if "OffPA" in plot_data:
        data = plot_data["OffPA"]

        ax_top.errorbar(
            data["x"],
            data["y"],
            yerr=data["y_err"],
            label="OffPA",
            capsize=4,
            elinewidth=1.3,
            markeredgewidth=0.9,
            **STYLES["OffPA"]
        )

    low_values = []
    high_values = []

    for algo in low_algos:
        if algo in plot_data:
            low_values.extend(list(plot_data[algo]["y"]))

    if "OffPA" in plot_data:
        high_values.extend(list(plot_data["OffPA"]["y"]))

    if not low_values:
        raise ValueError(f"No low-value algorithm data found for metric {metric}.")
    if not high_values:
        raise ValueError(f"No OffPA data found for metric {metric}.")

    low_min = min(low_values)
    low_max = max(low_values)
    high_min = min(high_values)
    high_max = max(high_values)

    low_range = low_max - low_min
    high_range = high_max - high_min

    if low_range == 0:
        low_range = max(abs(low_max), 1) * 0.1

    if high_range == 0:
        high_range = max(abs(high_max), 1) * 0.1

    bottom_lower = max(0, low_min - 0.20 * low_range)
    bottom_upper = low_max + 0.25 * low_range
    ax_bottom.set_ylim(bottom_lower, bottom_upper)

    top_lower = max(
        high_min - 0.05 * high_range,
        high_min * 0.80,
        0
    )
    top_upper = high_max + 0.10 * high_range
    ax_top.set_ylim(top_lower, top_upper)

    ax_top.yaxis.set_major_locator(MaxNLocator(nbins=2, prune="lower"))
    ax_bottom.yaxis.set_major_locator(MaxNLocator(nbins=4))

    configure_x_axis(ax_bottom, x_ticks, x_tick_labels, x_label)

    fig.text(
        0.015, 0.5,
        f"{metric} (K)",
        va="center",
        rotation="vertical",
        fontsize=30
    )

    for ax in [ax_top, ax_bottom]:
        ax.grid(True, linestyle="--", alpha=0.7)
        ax.tick_params(axis="both", which="major", labelsize=25)

    ax_top.spines["bottom"].set_visible(False)
    ax_bottom.spines["top"].set_visible(False)

    ax_top.tick_params(labeltop=False)
    ax_bottom.xaxis.tick_bottom()

    d = 0.012

    kwargs = dict(
        transform=ax_top.transAxes,
        color="k",
        clip_on=False,
        linewidth=1.2
    )

    ax_top.plot((-d, +d), (-d, +d), **kwargs)
    ax_top.plot((1 - d, 1 + d), (-d, +d), **kwargs)

    kwargs.update(transform=ax_bottom.transAxes)

    ax_bottom.plot((-d, +d), (1 - d, 1 + d), **kwargs)
    ax_bottom.plot((1 - d, 1 + d), (1 - d, 1 + d), **kwargs)

    add_top_legend(fig, [ax_bottom, ax_top])
    plt.tight_layout(rect=(0.06, 0.02, 1, 0.93), pad=0.6)

    save_figure(output_path)


def plot_metric_auto(
    df,
    metric,
    output_path,
    x_col,
    x_ticks,
    x_tick_labels,
    x_label,
    break_ratio
):
    plot_data = collect_plot_data(
        df=df,
        metric=metric,
        x_col=x_col,
        selected_points=x_ticks
    )

    use_broken = should_use_broken_axis(plot_data, break_ratio)

    if use_broken:
        print(f"✂ Using broken y-axis for {metric}")
        plot_metric_broken(
            plot_data=plot_data,
            metric=metric,
            output_path=output_path,
            x_ticks=x_ticks,
            x_tick_labels=x_tick_labels,
            x_label=x_label
        )
    else:
        print(f"📈 Using normal y-axis for {metric}")
        plot_metric_normal(
            plot_data=plot_data,
            metric=metric,
            output_path=output_path,
            x_ticks=x_ticks,
            x_tick_labels=x_tick_labels,
            x_label=x_label
        )


def main():
    parser = argparse.ArgumentParser(
        description="Plot simulation results with automatic broken y-axis, including beta and alpha sweep modes."
    )

    parser.add_argument(
        "excel_paths",
        nargs="+",
        help="Path(s) to result Excel file(s). Use multiple files for --x beta."
    )

    parser.add_argument(
        "--x",
        choices=["sats", "dests", "beta", "alpha"],
        required=True,
        help="Choose x-axis type: sats, dests, beta, or alpha."
    )

    parser.add_argument(
        "--fixed-type",
        choices=["sats", "dests"],
        default=None,
        help="Only for --x beta. Fixed dimension represented by graph number. Can often be inferred from filename prefix."
    )

    parser.add_argument(
        "--fixed",
        type=int,
        default=None,
        help="Only for --x beta. Fixed sat/dest value, e.g., --fixed 300 or --fixed 50."
    )

    parser.add_argument(
        "--x-start",
        type=int,
        default=X_START,
        help="Start value of x-axis for original sats/dests mode."
    )

    parser.add_argument(
        "--x-end",
        type=int,
        default=X_END,
        help="End value of x-axis for original sats/dests mode."
    )

    parser.add_argument(
        "--x-step",
        type=int,
        default=X_STEP,
        help="Step size of x-axis for original sats/dests mode."
    )

    parser.add_argument(
        "--break-ratio",
        type=float,
        default=BREAK_RATIO,
        help="Use broken y-axis only when min(OffPA) / max(other methods) >= this ratio."
    )

    args = parser.parse_args()

    for path in args.excel_paths:
        if not os.path.exists(path):
            print(f"❌ File not found: {path}")
            sys.exit(1)

    x_config = get_x_config(args.x)
    x_col = x_config["x_col"]
    x_label = x_config["x_label"]

    print(f"📌 X-axis mode: {args.x}")
    print(f"📌 X-axis label: {x_label}")
    print(f"📌 Break ratio threshold: {args.break_ratio}")

    if args.x == "beta":
        if args.fixed is None:
            print("❌ --fixed is required when --x beta")
            sys.exit(1)

        fixed_type = args.fixed_type or infer_fixed_type_from_paths(args.excel_paths)
        if fixed_type is None:
            print("❌ Cannot infer --fixed-type. Please provide --fixed-type sats or --fixed-type dests.")
            sys.exit(1)

        print(f"📘 Loading beta Excel files: {', '.join(os.path.basename(p) for p in args.excel_paths)}")

        df, x_ticks, x_tick_labels = load_beta_excels(
            excel_paths=args.excel_paths,
            fixed_type=fixed_type,
            fixed_value=args.fixed
        )
        
        pdta_levels_in_files = {extract_pdta_from_path(p) for p in args.excel_paths}
        if len(pdta_levels_in_files) > 1:
            raise ValueError(f"Mixed PDTA levels in input files: {pdta_levels_in_files}. Use only one pdta level per plot.")
        pdta_level = pdta_levels_in_files.pop()

        base_name = f"beta_{fixed_type}_pdta{pdta_level}_fixed_{args.fixed}"
        base_dir = f"img/{base_name}"

    elif args.x == "alpha":
        if args.fixed is None:
            print("❌ --fixed is required when --x alpha")
            sys.exit(1)
        fixed_type = args.fixed_type or infer_fixed_type_from_paths(args.excel_paths)
        if fixed_type is None:
            print("❌ Cannot infer --fixed-type. Please provide --fixed-type sats or --fixed-type dests.")
            sys.exit(1)

        print(f"📘 Loading alpha Excel files: {', '.join(os.path.basename(p) for p in args.excel_paths)}")
        df, x_ticks, x_tick_labels = load_alpha_excels(
            excel_paths=args.excel_paths,
            fixed_type=fixed_type,
            fixed_value=args.fixed
        )
        
        beta = extract_beta_from_path(args.excel_paths[0])
        pdta_levels_in_files = {extract_pdta_from_path(p) for p in args.excel_paths}
        if len(pdta_levels_in_files) > 1:
            raise ValueError(f"Mixed PDTA levels in input files: {pdta_levels_in_files}. Use only one pdta level per plot.")
        pdta_level = pdta_levels_in_files.pop()
        
        base_name = f"alpha_{fixed_type}_pdta{pdta_level}_fixed_{args.fixed}_beta_{format_number_label(beta)}"
        base_dir = f"img/{base_name}"
    
    else:
        if len(args.excel_paths) != 1:
            print("❌ Original sats/dests mode accepts exactly one Excel file. Use --x beta for multiple files.")
            sys.exit(1)

        excel_path = args.excel_paths[0]
        print(f"📘 Loading Excel: {excel_path}")

        df = load_single_excel_for_original_mode(excel_path, x_col)

        x_ticks = list(range(args.x_start, args.x_end + 1, args.x_step))
        x_tick_labels = [str(v) for v in x_ticks]

        excel_name = os.path.splitext(os.path.basename(excel_path))[0]
        base_dir = f"img/{excel_name}_{args.x}"

    os.makedirs(base_dir, exist_ok=True)

    metrics = ["Total", "BC", "CC", "RC"]

    for metric in metrics:
        metric_dir = os.path.join(base_dir, metric)
        os.makedirs(metric_dir, exist_ok=True)

        filename = f"{os.path.basename(base_dir)}_{metric}.png"
        output_path = os.path.join(metric_dir, filename)

        plot_metric_auto(
            df=df,
            metric=metric,
            output_path=output_path,
            x_col=x_col,
            x_ticks=x_ticks,
            x_tick_labels=x_tick_labels,
            x_label=x_label,
            break_ratio=args.break_ratio
        )

    print("🎉 All plots generated successfully!")


if __name__ == "__main__":
    main()

    
# 固定sats/dests然後x軸用beta, y用BC, RC, CC, total

# python plot_results.py dests_beta_100.xlsx --x dests --break-ratio 1
# python plot_results.py sats_beta_*.xlsx --x beta --fixed-type sats --fixed 300 --break-ratio 5