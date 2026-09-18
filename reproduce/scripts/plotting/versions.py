import matplotlib.pyplot as plt
from matplotlib_venn import venn3

from ._common import CLANG_VERSIONS, CLANG_VERSION_LABELS, row_identity, sets_per_clang_version


# Per-circle colours for the 3-version venn diagram.
_VENN_COLORS = {'100': '#9B59B6', '010': '#F39C12', '001': '#16A085'}


def _plot_venn(sets, save_to):
    for v in CLANG_VERSIONS:
        print(f"{v} unique rows: {len(sets[v])}")

    plt.figure(figsize=(3, 3))
    v_obj = venn3([sets[v] for v in CLANG_VERSIONS], set_labels=tuple(CLANG_VERSION_LABELS))
    for region, color in _VENN_COLORS.items():
        v_obj.get_patch_by_id(region).set_color(color)
    for region in ('110', '101', '011', '111'):
        patch = v_obj.get_patch_by_id(region)
        if patch:
            patch.set_alpha(0.5)
    plt.tight_layout()
    plt.savefig(save_to, dpi=300, bbox_inches='tight', facecolor='white', pad_inches=0.02)
    print(f"Venn diagram saved as {save_to}")


def _report_clang14_only_riscv(levels_df, sets):
    """Print how many Clang14-exclusive leakages are triggered on RISCV only.

    The Clang14-only venn region is `clang14 - clang18 - clang20`. For those
    rows, an `arch` of exactly "RISCV" (no other arch pipe-joined in) means the
    finding is triggered on RISCV alone.
    """
    clang14_only = sets["clang14"] - sets["clang18"] - sets["clang20"]
    rows = levels_df.assign(_ident=levels_df.apply(row_identity, axis=1))
    rows = rows[rows["_ident"].isin(clang14_only)].drop_duplicates("_ident")
    riscv_only = (rows["arch"] == "RISCV").sum()
    print(f"Clang14-only leakages: {len(clang14_only)}; RISCV-only among them: {riscv_only}")


def analyze_difference_between_versions(final_df):
    levels_df = final_df[final_df['opt'].str.contains('levels', na=False)]
    flags_df = final_df[~final_df['opt'].str.contains('levels', na=False)]

    levels_sets = sets_per_clang_version(levels_df)
    _plot_venn(levels_sets, "artifact_clang_version_opt_comparison.pdf")
    _report_clang14_only_riscv(levels_df, levels_sets)

    print("data with flag len", flags_df.shape[0])
    _plot_venn(sets_per_clang_version(flags_df), "artifact_clang_version_flag_comparison.pdf")
