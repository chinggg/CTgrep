import pandas as pd
import numpy as np

from ._common import (
    add_bar_value_labels,
    grouped_flag_vs_levels_bar,
    make_figure,
    save_figure,
    style_axes,
)


def _count_by_arch(df):
    """Return (total_by_arch, flag_only_by_arch). A row is "flag-only" if every
    entry in its `opt` column is `flag1` (no optimization level triggered it)."""
    total = {}
    flag_only = {}
    for _, row in df.iterrows():
        arch = row["arch"]
        total[arch] = total.get(arch, 0) + 1
        if all(flag == "flag1" for flag in row["opt"].split("|")):
            flag_only[arch] = flag_only.get(arch, 0) + 1
    return total, flag_only


def analyze_architecture(df):
    total, flag_only = _count_by_arch(df)
    level_only = {arch: total[arch] - flag_only.get(arch, 0) for arch in total}

    print("Unique architectures and their counts:")
    print(pd.DataFrame(list(total.items()), columns=["Architecture", "Count"]))
    print("Architectures with only flag1 and their counts:")
    print(pd.DataFrame(list(flag_only.items()), columns=["Architecture", "Count"]))
    print("Architectures with optimization levels and their counts:")
    print(pd.DataFrame(list(level_only.items()), columns=["Architecture", "Count"]))

    archs = sorted(total.keys())
    flag_vals = [flag_only.get(a, 0) for a in archs]
    level_vals = [level_only[a] for a in archs]
    x = np.arange(len(archs))

    fig, ax = make_figure(figsize=(8, 3.5))
    bars_flag, bars_levels = grouped_flag_vs_levels_bar(ax, x, flag_vals, level_vals)
    add_bar_value_labels(ax, bars_flag, fontsize=12)
    add_bar_value_labels(ax, bars_levels, fontsize=12)

    ax.set_xlabel('Platforms', fontsize=15, fontweight='bold')
    ax.set_ylabel('Number of Cases', fontsize=15, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(archs, fontsize=14, rotation=45, ha='right')
    ax.tick_params(axis='y', labelsize=14)
    ax.set_ylim(0, max(max(flag_vals), max(level_vals)) * 1.15)
    legend = ax.legend(loc='upper left', fontsize=12, frameon=True, fancybox=True, shadow=False, framealpha=0.5)
    legend.get_frame().set_facecolor('white')
    style_axes(ax)
    save_figure("artifact_platform_analysis.pdf", pad_inches=0.01)
