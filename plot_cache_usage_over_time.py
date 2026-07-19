#!/usr/bin/env python3
"""
Plot TSMTA cache usage over time, compared across different alpha values.

Reads the JSON produced by main.py (save_cache_usage_over_time):
    {alpha_tag: {"cc_per_t": [...], "cache_usage_per_t": [...]}}

Usage:
    python plot_cache_usage_over_time.py sats_pdta2_cache_usage_over_time.json
"""
import sys
import os
import json
import argparse
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator

matplotlib.use("Agg")

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

FIG_WIDTH = 8.8
FIG_HEIGHT = 6.8
PNG_DPI = 600

# Fixed categorical color order, assigned by alpha rank (not cycled arbitrarily).
ALPHA_COLORS = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e", "#8c564b"]
ALPHA_MARKERS = ["o", "s", "^", "D", "v", "P"]


def save_figure(output_path):
    plt.savefig(output_path, dpi=PNG_DPI, bbox_inches="tight", pad_inches=0.02)
    pdf_path = os.path.splitext(output_path)[0] + ".pdf"
    plt.savefig(pdf_path, bbox_inches="tight", pad_inches=0.02)
    print(f"📊 Saved PNG: {output_path}")
    print(f"📄 Saved PDF: {pdf_path}")


def sorted_alpha_tags(data: dict) -> list[str]:
    def alpha_key(tag: str) -> float:
        return float(tag.replace("p", "."))
    return sorted(data.keys(), key=alpha_key)


def plot_metric(data: dict, field: str, ylabel: str, output_path: str):
    fig, ax = plt.subplots(figsize=(FIG_WIDTH, FIG_HEIGHT))

    alpha_tags = sorted_alpha_tags(data)

    for i, alpha_tag in enumerate(alpha_tags):
        values = data[alpha_tag][field]
        t = list(range(len(values)))

        ax.plot(
            t,
            values,
            label=f"alpha={alpha_tag.replace('p', '.')}",
            color=ALPHA_COLORS[i % len(ALPHA_COLORS)],
            marker=ALPHA_MARKERS[i % len(ALPHA_MARKERS)],
            linestyle="-",
            markersize=6,
        )

    ax.set_xlabel("Time slot", labelpad=6)
    ax.set_ylabel(ylabel, labelpad=6)
    ax.grid(True, linestyle="--", alpha=0.7)
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    ax.yaxis.set_major_locator(MaxNLocator(nbins=5))
    ax.legend(loc="best")

    plt.tight_layout(pad=0.6)
    save_figure(output_path)


def main():
    parser = argparse.ArgumentParser(
        description="Plot TSMTA cache usage over time, compared across alpha values."
    )
    parser.add_argument("json_path", help="Path to *_cache_usage_over_time.json")
    parser.add_argument(
        "--out-prefix",
        default=None,
        help="Output file prefix (default: derived from the input JSON filename).",
    )
    args = parser.parse_args()

    with open(args.json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    out_prefix = args.out_prefix or os.path.splitext(os.path.basename(args.json_path))[0]

    plot_metric(
        data,
        field="cc_per_t",
        ylabel="Cache Cost (CC)",
        output_path=f"{out_prefix}_cc.png",
    )
    plot_metric(
        data,
        field="cache_usage_per_t",
        ylabel="Cache nodes used",
        output_path=f"{out_prefix}_usage.png",
    )


if __name__ == "__main__":
    main()
