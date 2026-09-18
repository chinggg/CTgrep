#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy>=1.26,<3", "pandas>=2.2,<4", "matplotlib>=3.8,<4", "matplotlib-venn>=1.1,<2"]
# ///
"""Reproduce and verify the paper's result figures and Tables 2 and 3."""

from __future__ import annotations

import contextlib
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("MPLBACKEND", "Agg")

import pandas as pd


ROOT = Path(__file__).resolve().parent
SCRIPT_DIR = ROOT / "scripts"
DATA_DIR = ROOT / "data"
FIGURE_DIR = ROOT / "figures"
EXPECTED_PATH = ROOT / "expected_results.json"
RESULTS_PATH = ROOT / "reproduced_results.json"
ANNOTATIONS_PATH = DATA_DIR / "findings_table_complete.csv"
LOG_PATH = ROOT / "reproduce.log"

sys.path.insert(0, str(SCRIPT_DIR))

from data_loading import read_file, read_files_and_create_df  # noqa: E402
from filtering import process_result  # noqa: E402
from plotting import (  # noqa: E402
    analyze_architecture,
    analyze_difference_between_versions,
    analyze_flag,
    analyze_general_libs,
)
from plotting._common import CLANG_VERSIONS, sets_per_clang_version  # noqa: E402
from plotting.flags import _BAR_STYLE, _classify_flag, _flag_counts  # noqa: E402
from plotting.general_libs import _count_by_lib  # noqa: E402
from tables import build_tables, format_tables  # noqa: E402


def _load_files(files: list[Path], clang_version: str) -> pd.DataFrame:
    frames = [read_file(str(path)) for path in files]
    if not frames:
        return pd.DataFrame()
    result = pd.concat(frames, ignore_index=True)
    result["clangversion"] = clang_version
    return result


def load_inputs() -> dict[str, pd.DataFrame]:
    """Load baseline data and the reviewed append-only experiment data."""
    loaded: dict[str, pd.DataFrame] = {}
    for version in CLANG_VERSIONS:
        suffix = version[-2:]
        baseline = read_files_and_create_df(DATA_DIR / "01_all7libs_bearsslflags" / f"res{suffix}", version)
        allflags = sorted((DATA_DIR / "02_mbedtls_pqclean_allflags" / f"res{suffix}").glob("*_unique.csv"))
        rerun78 = sorted((DATA_DIR / "03_other4libs_new78flags" / f"res{suffix}").glob("*_unique.csv"))
        additions = _load_files(allflags + rerun78, version)
        loaded[version] = pd.concat([baseline, additions], ignore_index=True)
        print(
            f"{version}: baseline rows={len(baseline)}, "
            f"addition files={len(allflags) + len(rerun78)}, addition rows={len(additions)}"
        )
    return loaded


def _venn_regions(df: pd.DataFrame) -> dict[str, int]:
    sets = sets_per_clang_version(df)
    s14, s18, s20 = (sets[v] for v in CLANG_VERSIONS)
    return {
        "clang14_only": len(s14 - s18 - s20),
        "clang18_only": len(s18 - s14 - s20),
        "clang20_only": len(s20 - s14 - s18),
        "clang14_and_18_only": len((s14 & s18) - s20),
        "clang14_and_20_only": len((s14 & s20) - s18),
        "clang18_and_20_only": len((s18 & s20) - s14),
        "all_three": len(s14 & s18 & s20),
    }


def _library_counts(df: pd.DataFrame) -> dict[str, dict[str, int]]:
    libraries = sorted(df["lib"].unique())
    counts = _count_by_lib(df, libraries)
    return {
        lib: {
            "flag_only": int(counts[lib]["flag1_only"]),
            "level_triggered": int(counts[lib]["levels_only"] + counts[lib]["both"]),
            "total": int(counts[lib]["total"]),
        }
        for lib in libraries
    }


def _architecture_counts(df: pd.DataFrame) -> dict[str, dict[str, int]]:
    total: dict[str, int] = {}
    flag_only: dict[str, int] = {}
    for row in df.itertuples(index=False):
        total[row.arch] = total.get(row.arch, 0) + 1
        if all(kind == "flag1" for kind in row.opt.split("|")):
            flag_only[row.arch] = flag_only.get(row.arch, 0) + 1
    return {
        arch: {
            "flag_only": flag_only.get(arch, 0),
            "level_triggered": total[arch] - flag_only.get(arch, 0),
            "total": total[arch],
        }
        for arch in sorted(total)
    }


def _optimization_counts(df: pd.DataFrame) -> dict[str, int]:
    counts = {label: 0 for label, _, _ in _BAR_STYLE}
    for flag, count in _flag_counts(df).itertuples(index=False):
        bucket = _classify_flag(flag)
        if bucket in counts:
            counts[bucket] += int(count)
    return counts


def build_results(
    inputs: dict[str, pd.DataFrame],
) -> tuple[dict, dict[str, pd.DataFrame], pd.DataFrame, pd.DataFrame]:
    by_version = {
        version: process_result(frame, group_rule="merge_arch")
        for version, frame in inputs.items()
    }
    combined = pd.concat(inputs.values(), ignore_index=True)
    union = process_result(combined, group_rule="merge_arch")
    per_arch = process_result(combined, group_rule="per_arch")
    levels = union[union["opt"].str.contains("levels", na=False)]
    flags = union[~union["opt"].str.contains("levels", na=False)]

    results = {
        "processed_cases": {
            **{version: len(frame) for version, frame in by_version.items()},
            "all_versions_merge_arch": len(union),
            "all_versions_per_arch": len(per_arch),
        },
        "library_figures": {
            version: _library_counts(frame)
            for version, frame in by_version.items()
        },
        "compiler_version_figure": {
            "optimization_levels": _venn_regions(levels),
            "optimization_flags": _venn_regions(flags),
        },
        "platform_figure": _architecture_counts(per_arch),
        "optimization_configuration_figure": _optimization_counts(union),
    }
    return results, by_version, union, per_arch


def _diff(expected, actual, path="") -> list[str]:
    if isinstance(expected, dict) and isinstance(actual, dict):
        messages = []
        for key in sorted(set(expected) | set(actual)):
            here = f"{path}.{key}" if path else key
            if key not in expected:
                messages.append(f"unexpected {here}={actual[key]!r}")
            elif key not in actual:
                messages.append(f"missing {here}; expected {expected[key]!r}")
            else:
                messages.extend(_diff(expected[key], actual[key], here))
        return messages
    if expected != actual:
        return [f"{path}: expected {expected!r}, reproduced {actual!r}"]
    return []


def verify(results: dict) -> None:
    expected = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))
    differences = _diff(expected, results)
    if differences:
        print("\nVerification FAILED:", file=sys.stderr)
        for difference in differences:
            print(f"  - {difference}", file=sys.stderr)
        raise SystemExit(1)
    print("Verification PASSED: every figure and table value matches the paper (expected_results.json)")


def generate_figures(
    inputs: dict[str, pd.DataFrame],
    by_version: dict[str, pd.DataFrame],
    union: pd.DataFrame,
    per_arch: pd.DataFrame,
) -> None:
    FIGURE_DIR.mkdir(exist_ok=True)
    previous_dir = Path.cwd()
    os.chdir(FIGURE_DIR)
    try:
        for version in CLANG_VERSIONS:
            analyze_general_libs(
                inputs,
                config={
                    "clang_version": version,
                    "output_suffix": f"_{version}",
                    "write_grouped": False,
                    "write_stacked": True,
                    "lift_top_labels": (
                        ["libsodium", "libgcrypt", "mbedtls"]
                        if version == "clang14"
                        else "auto"
                    ),
                },
            )
            generated = Path(f"artifact_general_libs_stacked_{version}.pdf")
            generated.replace(Path(f"artifact_general_libs_{version}.pdf"))
        analyze_flag(union, by_version)
        analyze_architecture(per_arch)
        analyze_difference_between_versions(union)
    finally:
        os.chdir(previous_dir)


def main() -> None:
    # Detailed processing output goes to reproduce.log; the terminal gets the summary.
    with LOG_PATH.open("w", encoding="utf-8") as log, contextlib.redirect_stdout(log):
        inputs = load_inputs()
        results, by_version, union, per_arch = build_results(inputs)
        results["tables"] = build_tables(inputs, ANNOTATIONS_PATH)
        generate_figures(inputs, by_version, union, per_arch)
    RESULTS_PATH.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(format_tables(results["tables"]))
    print()
    print(f"Figures written to {FIGURE_DIR.relative_to(ROOT)}/")
    for name in sorted(p.name for p in FIGURE_DIR.glob("*.pdf")):
        print(f"  {name}")
    print()
    verify(results)


if __name__ == "__main__":
    main()
