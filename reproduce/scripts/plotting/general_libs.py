import pandas as pd
import numpy as np

from filtering import process_result
from ._common import (
    COLOR_FLAG,
    COLOR_LEVELS,
    HATCH_FLAG,
    HATCH_LEVELS,
    LABEL_FLAG,
    LABEL_LEVELS,
    add_bar_value_labels,
    grouped_flag_vs_levels_bar,
    make_figure,
    save_figure,
    style_axes,
)


# === Config ============================================================
# Toggle these to change what data feeds into this plot
#   clang_version: any of CLANG_VERSIONS ("clang14"/"clang18"/"clang20"), or
#                  "all" to combine all versions into a single dataframe.
#   platforms:     "all"        — every retained arch (after ALWAYS_DROP_ARCHS).
#                  "mainstream" — only RISCV / AArch64 / X8664.
#                  "<arch>"     — restrict to a single arch (e.g. "RISCV").
#   stacked_top:   which segment sits on top in the stacked bar chart.
#                  "auto"   — larger total segment goes on the bottom.
#                  "flag"   — pink (Flag-only) on top of blue (Levels).
#                  "levels" — blue (Levels) on top of pink (Flag-only).
#   output_suffix: optional filename suffix, e.g. "_14".
#   write_grouped/write_stacked: choose which chart files to write.
#   lift_top_labels: in the stacked chart, which bars draw the top segment's
#                  number lifted just above the bar (separated) instead of
#                  centered inside the segment.
#                  "auto"       — lift only when the top segment is too thin
#                                 (the previous automatic behavior).
#                  [<lib>, ...] — lift exactly these libraries, e.g.
#                                 ["libgcrypt", "mbedtls"]. Use [] for none.
PLOT_CONFIG = {
    "clang_version": "clang18",
    "platforms": "all",
    "stacked_top": "auto",
    "lift_top_labels": ["libsodium", "libgcrypt", "mbedtls",],
    "output_suffix": "",
    "write_grouped": True,
    "write_stacked": True,
}


# Pretty-cased names used on the x-axis. Falls back to the raw lib name.
LIB_DISPLAY_NAMES = {
    'bearssl': 'BearSSL',
    'libgcrypt': 'Libgcrypt',
    'libsodium': 'Libsodium',
    'mbedtls': 'MbedTLS',
    'openssl': 'OpenSSL',
    'pqclean': 'PQClean',
    'wolfssl': 'wolfSSL',
}


def _build_input(dfs, config):
    """Apply PLOT_CONFIG to the per-version dfs dict and return one ready dataframe."""
    if config["clang_version"] == "all":
        raw = pd.concat(dfs.values())
    else:
        raw = dfs[config["clang_version"]]

    platforms = config["platforms"]
    if platforms == "all":
        return process_result(raw, group_rule="merge_arch")
    if platforms == "mainstream":
        return process_result(raw, group_rule="merge_arch", arch_filter="mainstream")
    return process_result(raw, group_rule="merge_arch", specific_arch=platforms)


def _classify_opt(opt):
    """Bucket a row by its `opt` field. Returns one of: flag1_only, levels_only, both, other."""
    parts = set(opt.split('|')) if not pd.isna(opt) else set()
    if parts == {'flag1'}:
        return 'flag1_only'
    if parts == {'levels'}:
        return 'levels_only'
    if 'flag1' in parts and 'levels' in parts:
        return 'both'
    return 'other'


def _count_by_lib(df, lib_names):
    counts = {lib: {'flag1_only': 0, 'levels_only': 0, 'both': 0, 'other': 0, 'total': 0}
              for lib in lib_names}
    for _, row in df.iterrows():
        if row["lib"] in counts:
            counts[row["lib"]][_classify_opt(row["opt"])] += 1
            counts[row["lib"]]['total'] += 1
    return counts


def _print_counts_table(lib_names, counts):
    print("Function counts (general libs analysis):")
    print(f"{'Library':<15} {'Total':<6} {'Flag1 Only':<10} {'Levels Only':<12} {'Both':<6} {'Other':<6}")
    print("-" * 70)
    for lib in lib_names:
        c = counts[lib]
        print(f"{lib:<15} {c['total']:<6} {c['flag1_only']:<10} {c['levels_only']:<12} {c['both']:<6} {c['other']:<6}")


def _annotate_stacked(ax, x, bottom_vals, top_vals, top_ylim, lib_names, lift_top_labels):
    """Label each stacked bar's two segments, centered within the segment.

    The top segment's number can instead be lifted just above the top of the bar
    (separated), so the two numbers don't crowd together. `lift_top_labels`
    controls which bars get this:
      "auto"       — lift only when the top segment is too thin to clear the
                     bottom label (e.g. libsodium).
      [<lib>, ...] — lift exactly these libraries (e.g. ["libgcrypt", "mbedtls"]).
    """
    min_gap = 0.09 * top_ylim
    lift_set = None if lift_top_labels == "auto" else set(lift_top_labels)
    for xi, lib, bottom_val, top_val in zip(x, lib_names, bottom_vals, top_vals):
        if bottom_val > 0:
            ax.text(xi, bottom_val / 2, f'{int(bottom_val)}', ha='center', va='center',
                    fontweight='bold', fontsize=12, zorder=10)
        if top_val > 0:
            top_y = bottom_val + top_val / 2
            if lift_set is None:
                lift = top_y - bottom_val / 2 < min_gap
            else:
                lift = lib in lift_set
            if lift:
                ax.text(xi, bottom_val + top_val + 0.5, f'{int(top_val)}', ha='center',
                        va='bottom', fontweight='bold', fontsize=12, zorder=10)
            else:
                ax.text(xi, top_y, f'{int(top_val)}', ha='center', va='center',
                        fontweight='bold', fontsize=12, zorder=10)


def analyze_general_libs(dfs, config=None):
    cfg = {**PLOT_CONFIG, **(config or {})}
    print(f"general_libs plot config: {cfg}")
    df = _build_input(dfs, cfg)
    lib_names = sorted(df["lib"].unique())
    counts = _count_by_lib(df, lib_names)
    _print_counts_table(lib_names, counts)

    display_labels = [LIB_DISPLAY_NAMES.get(lib, lib) for lib in lib_names]
    flag1_only = [counts[lib]['flag1_only'] for lib in lib_names]
    levels = [counts[lib]['levels_only'] + counts[lib]['both'] for lib in lib_names]
    x = np.arange(len(lib_names))

    suffix = cfg.get("output_suffix", "")

    # --- Grouped bar chart -------------------------------------------------
    if cfg.get("write_grouped", True):
        fig, ax = make_figure(figsize=(8, 3.5))
        bars_flag, bars_levels = grouped_flag_vs_levels_bar(ax, x, flag1_only, levels, gap=0.12)
        add_bar_value_labels(ax, bars_flag, fontsize=12, zorder=10)
        add_bar_value_labels(ax, bars_levels, fontsize=12, zorder=10)

        ax.set_xlabel('Cryptographic Libraries', fontsize=15, fontweight='bold')
        ax.set_ylabel('Number of Cases', fontsize=15, fontweight='bold')
        ax.set_xticks(x)
        ax.set_xticklabels(display_labels, fontsize=14, rotation=45, ha='right')
        ax.tick_params(axis='y', labelsize=14)
        ax.set_ylim(0, max(max(flag1_only), max(levels)) * 1.15)
        legend = ax.legend(loc='upper left', fontsize=12, frameon=True, fancybox=True, shadow=False, framealpha=0.5)
        legend.set_zorder(5)
        legend.get_frame().set_facecolor('white')
        style_axes(ax)
        save_figure(f"artifact_general_libs{suffix}.pdf")

    # --- Stacked bar chart -------------------------------------------------
    if not cfg.get("write_stacked", True):
        return

    fig2, ax2 = make_figure(figsize=(8, 3.5))
    width2 = 0.6
    # Pick which segment goes on top of the stack (see PLOT_CONFIG["stacked_top"]).
    flag_seg = (flag1_only, COLOR_FLAG, LABEL_FLAG, HATCH_FLAG)
    levels_seg = (levels, COLOR_LEVELS, LABEL_LEVELS, HATCH_LEVELS)
    stacked_top = cfg.get("stacked_top", "auto")
    if stacked_top == "auto":
        flag_total = sum(flag1_only)
        levels_total = sum(levels)
        if flag_total >= levels_total:
            bottom_seg, top_seg = flag_seg, levels_seg
        else:
            bottom_seg, top_seg = levels_seg, flag_seg
    elif stacked_top == "flag":
        bottom_seg, top_seg = levels_seg, flag_seg
    elif stacked_top == "levels":
        bottom_seg, top_seg = flag_seg, levels_seg
    else:
        raise ValueError(f"unknown stacked_top: {stacked_top!r}")
    bottom_vals, bottom_color, bottom_label, bottom_hatch = bottom_seg
    top_vals, top_color, top_label, top_hatch = top_seg

    bars_bottom = ax2.bar(x, bottom_vals, width2, label=bottom_label,
                          color=bottom_color, alpha=0.8, edgecolor='white', linewidth=1.2, hatch=bottom_hatch)
    bars_top = ax2.bar(x, top_vals, width2, bottom=bottom_vals, label=top_label,
                       color=top_color, alpha=0.8, edgecolor='white', linewidth=1.2, hatch=top_hatch)

    top_ylim = max(b + t for b, t in zip(bottom_vals, top_vals)) * 1.15
    _annotate_stacked(ax2, x, bottom_vals, top_vals, top_ylim,
                      lib_names, cfg.get("lift_top_labels", "auto"))

    ax2.set_xlabel('Cryptographic Libraries', fontsize=15, fontweight='bold')
    ax2.set_ylabel('Number of Cases', fontsize=15, fontweight='bold')
    ax2.set_xticks(x)
    ax2.set_xticklabels(display_labels, fontsize=14, rotation=45, ha='right')
    ax2.tick_params(axis='y', labelsize=14)
    ax2.set_ylim(0, top_ylim)
    # Match the vertical stack: top legend entry describes the top segment.
    legend2 = ax2.legend([bars_top, bars_bottom], [top_label, bottom_label],
                         loc='upper left', fontsize=12, frameon=True,
                         fancybox=True, shadow=False, framealpha=0.5)
    legend2.set_zorder(5)
    legend2.get_frame().set_facecolor('white')
    style_axes(ax2)
    save_figure(f"artifact_general_libs_stacked{suffix}.pdf")
