"""Shared plotting helpers and constants.

Every helper here exists because the same block of code was repeated across
at least two analyze_* functions. If a value is only used in one place,
keep it local to that function rather than adding it here.
"""

import matplotlib.pyplot as plt
import numpy as np


# Clang versions appear in 4 places (versions.py, riscv_x8632.py) — central
# definition lets the analyses agree on what's compared.
CLANG_VERSIONS = ["clang14", "clang18", "clang20"]
CLANG_VERSION_LABELS = ["Clang 14", "Clang 18", "Clang 20"]

# Semantic palette for the recurring "triggered by flag only" vs "triggered
# by optimization level" comparison (general_libs and architecture plots).
COLOR_FLAG = '#FF6B6B'
COLOR_LEVELS = '#45B7D1'
HATCH_FLAG = '///'
HATCH_LEVELS = '...'
LABEL_FLAG = 'Can Only be Triggered by Flag(s)'
LABEL_LEVELS = 'Triggered by Optimization Levels'


def make_figure(figsize):
    """Create a fig/ax with the project's default white background."""
    plt.style.use('default')
    fig, ax = plt.subplots(figsize=figsize)
    fig.patch.set_facecolor('white')
    ax.set_facecolor('white')
    return fig, ax


def style_axes(ax):
    """Apply the recurring axes styling: light grid, dark spines, grid behind data."""
    ax.grid(True, alpha=0.2, linestyle='-', linewidth=0.5, color='gray')
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_edgecolor('black')
        spine.set_linewidth(0.8)


def save_figure(path, pad_inches=0.02):
    """Persist the current figure with the project's standard parameters."""
    plt.tight_layout()
    plt.savefig(path, dpi=300, bbox_inches='tight', facecolor='white', pad_inches=pad_inches)
    print(f"Figure saved as {path}")


def add_bar_value_labels(ax, bars, dy=0.5, fontsize=9, zorder=None):
    """Annotate each bar with its integer height. Skips bars with height 0."""
    text_kwargs = dict(ha='center', va='bottom', fontweight='bold', fontsize=fontsize)
    if zorder is not None:
        text_kwargs['zorder'] = zorder
    for bar in bars:
        height = bar.get_height()
        if height > 0:
            ax.text(bar.get_x() + bar.get_width() / 2., height + dy, f'{int(height)}', **text_kwargs)


def row_identity(row):
    """Identity used to compare a leakage finding across clang versions."""
    return f"{row['file']}|{row['line']}|{row['col']}|{row['source']}|{row['char']}"


def sets_per_clang_version(df):
    """Map each clang version to the set of distinct row identities seen for it."""
    return {
        v: set(df[df["clangversion"].str.contains(v, na=False)].apply(row_identity, axis=1))
        for v in CLANG_VERSIONS
    }


def grouped_flag_vs_levels_bar(ax, x, flag_values, level_values, width=0.35, gap=0.0):
    """The two side-by-side bars used by both general_libs and architecture plots.

    `gap` adds extra horizontal space between the two bars within each group,
    which keeps their value labels from colliding when both are narrow.
    """
    offset = width / 2 + gap / 2
    bars_flag = ax.bar(
        x - offset, flag_values, width, label=LABEL_FLAG,
        color=COLOR_FLAG, alpha=0.8, edgecolor='white', linewidth=1.2, hatch=HATCH_FLAG,
    )
    bars_levels = ax.bar(
        x + offset, level_values, width, label=LABEL_LEVELS,
        color=COLOR_LEVELS, alpha=0.8, edgecolor='white', linewidth=1.2, hatch=HATCH_LEVELS,
    )
    return bars_flag, bars_levels
