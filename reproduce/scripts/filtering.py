import pandas as pd


# Architectures we never analyze, regardless of mode.
ALWAYS_DROP_ARCHS = ["MIPS32", "I686", "X8632"]

# Additional architectures dropped when arch_filter == "mainstream".
NON_MAINSTREAM_ARCHS = ["ARM", "MIPS32EL", "MIPS64"]

# Per-library file-path or function substrings whose rows are always dropped.
# The match is case-insensitive, scoped to the named library.
EXCLUDED_PATTERNS_BY_LIB = {
    "pqclean": "mceliece",
}

# Control-flow keywords in `source` that indicate the row is a structural branch,
# not a value-dependent comparison we care about.
CONTROL_FLOW_KEYWORDS_RE = r'\b(?:for|while|if|else|do|switch|case)\b'

# Substrings in the `optimization` column that mark flags known to be either
# noise (no value-dependent branch) or known false positives. Centralised so
# the list is easy to audit/extend.
NOISE_OPTIMIZATION_SUBSTRINGS = [
    "profil",
    "stack-protect",
    "-ftrapv",
    "force-vector-width",
    "force-vector-interleave",
    "force-target-instruction-cost",
    "instrument-functions",  # double-check this
    "--expand-div-rem-bits",
    "-fwrapv",
    "--scalar-evolution-huge-expr-threshold",
    "--jump-threading-threshold",
    "--enable-nontrivial-unswitch",
    "--scev-cheap-expansion-budget",
    "-ffreestanding",
    "-fno-builtin",
    "-fforce-enable-int128",
]

# These flags change MbedTLS preprocessor feature detection and produced only
# false-positive branch attributions in the manual review. Remove their
# individual trigger tokens, but keep a row when another valid trigger remains.
EXCLUDED_TP_FLAG_SUBSTRINGS = [
    "-fgnuc-version=0",
    "-fms-compatibility",
]

# Chars in the `char` column that are likely false positives (we keep only
# real operator characters). Note the deliberate omission of <, >, |, & — those
# are validated separately by the neighbour-character checks below.
LIKELY_FP_CHAR_RE = r'[a-zA-Z0-9()\[\]{}=_/%!]'

# Group keys for the deduplication step. "merge_arch" merges architectures into
# one row; "per_arch" keeps them separate.
GROUP_KEYS = {
    "merge_arch": ["line", "col", "source", "char", "lib"],
    "per_arch": ["line", "col", "source", "char", "lib", "arch"],
}

# Columns aggregated by joining unique values with '|'.
PIPE_JOIN_COLUMNS = ["file", "function", "optimization", "opt", "arch", "clangversion", "type"]

# Columns whose pipe-joined values are deduplicated after grouping.
DEDUPE_COLUMNS = ["function", "optimization", "opt", "arch"]


def _drop_when_next_char(df, char, expected, must_match):
    """Drop rows where df['char'] == char and source[col] {==, !=} expected.

    Used for the `||` / `&&` / `>>` checks. The `<<` check looks at a
    different offset and is handled inline.
    """
    next_char = df.apply(
        lambda row: row["source"][row["col"]] if len(row["source"]) > row["col"] else "",
        axis=1,
    )
    in_bounds = df["source"].str.len() > df["col"]
    cmp = (next_char == expected) if must_match else (next_char != expected)
    return df[~((df["char"] == char) & in_bounds & cmp)]


def _remove_duplicates(flags):
    """Split a '|'-joined string, de-duplicate, and rejoin."""
    if pd.isna(flags):
        return flags
    return '|'.join(sorted(set(flags.split('|'))))


def _strip_excluded_trigger_tokens(value):
    """Remove manually rejected flag triggers from a pipe-joined cell."""
    if pd.isna(value):
        return value
    kept = [
        token
        for token in value.split("|")
        if not any(excluded in token for excluded in EXCLUDED_TP_FLAG_SUBSTRINGS)
    ]
    return "|".join(kept)


def filter_rows(df, library_name="", specific_arch="", arch_filter="", drop_noise_flags=True):
    """Apply all row-level filtering (no grouping/merging).

    This is the part of the pipeline shared by `process_result` and by any
    caller that wants the cleaned rows without the architecture-merging
    groupby. mmem (dataflow) rows are kept; whether to drop mmem-only findings
    is a post-grouping decision left to the caller.

    `drop_noise_flags` drops rows whose optimization flag is on the noise list;
    callers auditing those flags (e.g. noise_flags.py) pass False to keep them.
    """
    # Select leakage types of interest. mmem (dataflow) rows are kept here so
    # they can be merged into matching cjump groups during the groupby; the
    # post-groupby step then drops any group that is mmem-only.
    newdf = df[df["type"].isin(["cjump", "mmem"])].copy()

    # Apply the manually reviewed false-positive exclusion at trigger-token
    # granularity.  Empty rows are discarded; rows with another valid trigger
    # remain available to the normal grouping and deduplication pipeline.
    newdf["optimization"] = newdf["optimization"].apply(_strip_excluded_trigger_tokens)
    newdf = newdf[newdf["optimization"].fillna("") != ""]

    # Architecture filtering.
    drop_archs = ALWAYS_DROP_ARCHS + (NON_MAINSTREAM_ARCHS if arch_filter == "mainstream" else [])
    newdf = newdf[~newdf["arch"].isin(drop_archs)]
    if specific_arch:
        newdf = newdf[newdf["arch"] == specific_arch]
    if library_name:
        newdf = newdf[newdf["lib"] == library_name]

    # Drop per-library patterns (e.g. pqclean/mceliece*) before any merging step.
    for lib, pattern in EXCLUDED_PATTERNS_BY_LIB.items():
        is_lib = newdf["lib"] == lib
        in_file = newdf["file"].str.contains(pattern, case=False, na=False)
        in_func = newdf["function"].str.contains(pattern, case=False, na=False)
        excluded = is_lib & (in_file | in_func)
        if excluded.any():
            print(f"Removed {excluded.sum()} rows from {lib} matching pattern '{pattern}' in file or function")
        newdf = newdf[~excluded]

    print("Analyzing Libs: ", newdf["lib"].unique())

    # Drop structural branches and broken-across-lines branch statements.
    newdf = newdf[~newdf["source"].str.contains(CONTROL_FLOW_KEYWORDS_RE, na=False)]
    newdf = newdf[~newdf["source"].str.endswith("{", na=False)]

    # Drop rows whose optimization flag is on the noise list.
    if drop_noise_flags:
        for substring in NOISE_OPTIMIZATION_SUBSTRINGS:
            newdf = newdf[~newdf["optimization"].str.contains(substring, na=False)]

    # Drop rows with no detected operator character.
    newdf = newdf[~newdf["char"].isnull()]

    # Drop `||` (when single `|` flagged but next char is also `|`), `&&` similarly,
    # and solitary `>` (keep only `>>`).
    newdf = _drop_when_next_char(newdf, "|", expected="|", must_match=True)
    newdf = _drop_when_next_char(newdf, "&", expected="&", must_match=True)
    newdf = _drop_when_next_char(newdf, ">", expected=">", must_match=False)
    # `<` is special: looks two chars back, with its own bounds check (preserved from original).
    prev_char = newdf.apply(
        lambda row: row["source"][row["col"] - 2] if row["col"] - 2 >= 0 else "",
        axis=1,
    )
    newdf = newdf[~((newdf["char"] == "<") & (newdf["col"] > 0) & (prev_char != "<"))]

    # Drop likely-FP operator characters.
    newdf = newdf[~newdf["char"].str.contains(LIKELY_FP_CHAR_RE, na=False)]

    # Drop rows whose only optimization is Ofast (the split+len+[0] check reduces to == "Ofast").
    ofast_only = newdf["optimization"] == "Ofast"
    if ofast_only.any():
        print(f"Removed {ofast_only.sum()} rows with Ofast-only optimization")
    newdf = newdf[~ofast_only]

    return newdf


def process_result(df, group_rule="merge_arch", library_name="", specific_arch="", arch_filter=""):
    newdf = filter_rows(df, library_name=library_name, specific_arch=specific_arch, arch_filter=arch_filter)

    # Group and aggregate.
    if group_rule not in GROUP_KEYS:
        raise ValueError(f"Unknown group rule: {group_rule!r}. Expected one of {list(GROUP_KEYS)}.")
    agg = {col: lambda x: '|'.join(x.unique()) for col in PIPE_JOIN_COLUMNS}
    newdf = newdf.groupby(GROUP_KEYS[group_rule], as_index=False).agg(agg)

    # Deduplicate pipe-joined values where order doesn't matter.
    for col in DEDUPE_COLUMNS:
        newdf[col] = newdf[col].apply(_remove_duplicates)

    # Keep a dataflow (mmem) finding only if it co-occurs with a branch (cjump)
    # under the same group key — i.e. the joined `type` is "cjump" or "cjump|mmem".
    # An mmem with no accompanying cjump is almost always a false positive: a
    # value-dependent memory access that never feeds a control-flow decision.
    newdf = newdf[newdf["type"].fillna("") != "mmem"]

    print(f"Number of rows after processing: {len(newdf)}")
    return newdf
