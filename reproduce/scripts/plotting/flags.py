import pandas as pd
import numpy as np

from ._common import add_bar_value_labels, make_figure, save_figure, style_axes


# Prefix-based classification for optimization flags. Ordered so that the
# match is unambiguous (all entries are mutually-disjoint prefixes).
OPT_PREFIXES = ['O0', 'O1', 'O2', 'O3', 'Os', 'Ofast', 'Oz']

# Per-bar styling for the optimization-config chart. One entry per category.
_BAR_STYLE = [
    ('O0',         '#45B7D1', '...'),
    ('O1',         '#FF6B6B', '///'),
    ('O2',         '#9B59B6', 'xxx'),
    ('O3',         '#F4D03F', '\\\\\\'),
    ('Os',         '#5DADE2', '++'),
    ('Oz',         '#E67E22', '**'),
    ('Clang Flag', '#34495E', '||'),
    ('LLVM Flag',  '#A569BD', ''),
]


def _explode_optimization_flags(df):
    """Yield individual flag strings from the pipe-joined optimization column,
    dropping anything attached to an Ofast level (we don't analyze Ofast here)."""
    for flag_string in df["optimization"]:
        if pd.isna(flag_string):
            continue
        for part in flag_string.split("|"):
            if '--' in part:
                level, flag = part.split('--', 1)
                if level == 'Ofast':
                    continue
                yield '--' + flag
            elif '-f' in part:
                _, flag = part.split('-f', 1)
                yield '-f' + flag
            elif part != "Ofast":
                yield part


def _classify_flag(flag):
    """Map a flag to its bucket label (matches _BAR_STYLE keys), or None."""
    for prefix in OPT_PREFIXES:
        if flag.startswith(prefix):
            return prefix
    if flag.startswith('--'):
        return 'LLVM Flag'
    if flag.startswith('-f'):
        return 'Clang Flag'
    return None


def _print_o0_archs(df):
    """When O0 shows up, list the architectures responsible — useful for debugging."""
    archs = []
    for row in df.itertuples():
        parts = row.optimization.split("|") if row.optimization else []
        if 'O0' in parts:
            archs.extend(row.arch.split("|") if row.arch else [])
    print("Number of each architecture that has O0:")
    print(pd.Series(archs).value_counts())


def _flag_counts(df):
    """Count flags after stripping parameter values (=...) so '--foo=1' and
    '--foo=2' collapse together. Returns a Flag/Count dataframe sorted by Count."""
    flag_counts = pd.Series(list(_explode_optimization_flags(df))).value_counts().reset_index()
    flag_counts.columns = ['Flag', 'Count']
    flag_counts['Flag'] = flag_counts['Flag'].str.replace(r'=[-+]?[a-zA-Z0-9_]+', '', regex=True)
    flag_counts = flag_counts.groupby('Flag', as_index=False).sum()
    flag_counts = flag_counts.sort_values(by='Count', ascending=False).reset_index(drop=True)
    return flag_counts


def analyze_flag(df, per_version=None):
    source_count = df["source"].value_counts().reset_index()
    source_count.columns = ['Source', 'Count']
    print("Unique sources and their counts:")
    print(source_count)

    _print_o0_archs(df)

    flag_counts = _flag_counts(df)
    print("Unique optimization flags after merging:")
    print(flag_counts)

    # Per-version breakdowns: only the top 25 flags for each clang version.
    if per_version:
        for version, version_df in per_version.items():
            print(f"\nTop 25 optimization flags for {version}:")
            print(_flag_counts(version_df).head(25))

    # Bucket each flag by its category. Dict-based replaces the original's
    # 9 separate O0_count/O1_count/... variables and the O(n²) elif chain.
    bucket_counts = {label: 0 for label, _, _ in _BAR_STYLE}
    for flag, count in flag_counts.itertuples(index=False):
        bucket = _classify_flag(flag)
        if bucket in bucket_counts:
            bucket_counts[bucket] += count

    print("Optimization level counts:")
    for label, _, _ in _BAR_STYLE:
        print(f"-{label}: {bucket_counts[label]}")
    # The original always printed Ofast too, even though it's always 0 here.
    print(f"-Ofast: 0")

    # --- Plot --------------------------------------------------------------
    labels = [label for label, _, _ in _BAR_STYLE]
    counts = [bucket_counts[label] for label in labels]
    x = np.arange(len(labels))

    fig, ax = make_figure(figsize=(8, 3.5))
    width = 0.6
    all_bars = []
    for i, (label, color, hatch) in enumerate(_BAR_STYLE):
        container = ax.bar(x[i], counts[i], width, color=color, alpha=0.85,
                           edgecolor='white', linewidth=1.2, hatch=hatch, label=label)
        all_bars.extend(container)
    add_bar_value_labels(ax, all_bars, fontsize=12)

    ax.set_xlabel('Compiler Optimization Configurations', fontsize=15, fontweight='bold')
    ax.set_ylabel('Number of Cases', fontsize=15, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=14, rotation=45, ha='right')
    ax.tick_params(axis='y', labelsize=14)
    ax.set_ylim(0, max(counts) * 1.15)
    ax.legend(loc='upper left', fontsize=11, frameon=True, fancybox=True, shadow=False, framealpha=0.5, ncol=4)
    style_axes(ax)
    save_figure("artifact_optimization_flags.pdf")
