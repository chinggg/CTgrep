#!/usr/bin/env python3
"""Reproduce the flag-count numbers used in ``experiment_setting.tex``.

The script has two jobs:

1. Recompute paper-facing counts from source files, including keyword-filtered
   raw flags, concrete flags expanded by ``flag_manager.py``, Phase 1 analysis
   totals, and scanner-shortlisted problematic flags.
2. Write inspectable ``*_filtered.txt`` and ``*_concrete.txt`` files next to the
   source flag files, so the counted sets can be reviewed directly.

Only the experiment dimensions below are handwritten constants.  All flag
counts are recomputed from inputs on every run.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

TOOLS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_DIR.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
# The manuscript source is not part of the artifact; when it is absent the
# consistency check is skipped and only the derivation report is printed.
EXPERIMENT_TEX = Path(
    os.environ.get("CTGREP_EXPERIMENT_TEX", REPO_ROOT / "paper" / "experiment_setting.tex")
)

sys.path.insert(0, str(TOOLS_DIR))
sys.path.insert(0, str(SCRIPTS_DIR))

from flagcounts import BLOCK_FLAG_KWDS
from flag_manager import FlagManager


EXPERIMENT_ARCHS = 6  # AArch64, RISC-V (64-bit), x86-64, ARM (32-bit), MIPS32EL, and MIPS64.
EXPERIMENT_OPT_LEVELS = 6  # -O0, -O1, -O2, -O3, -Os, and -Oz.
PHASE1_DISCOVERY_LIBRARIES = 3  # BearSSL, MbedTLS, and PQClean.
CLANG_VERSIONS = ("14", "18", "20")
# Order in which Phase 1 libraries were added when the manuscript reports
# incremental discoveries ("121 with BearSSL, +59 with PQClean, +39 with MbedTLS").
PHASE1_LIBRARY_ORDER = ("bearssl", "pqclean", "mbedtls")
# Scanner-shortlisted concrete flags that were removed by manual review before
# the manuscript count. problematic_flags.tsv already excludes them; the set is
# kept so that a raw scanner table can be passed with --problematic-flags.
MANUAL_FALSE_POSITIVES = {
    "-fgnuc-version=0",  # only changes __GNUC__ predefines; the hits are not flag-induced
}


@dataclass(frozen=True)
class DerivedFlagFile:
    """Counts and output paths derived from one source flag file."""

    label: str
    source_path: Path
    filtered_path: Path
    concrete_path: Path
    source_candidate_count: int
    filtered_count: int
    concrete_count: int


@dataclass(frozen=True)
class VersionFlagSet:
    """Concrete flags used by one Clang version in Phase 1."""

    version: str
    mllvm: DerivedFlagFile
    common_fflags_concrete_count: int
    total_concrete_count: int


@dataclass(frozen=True)
class ProblematicCounts:
    """Problematic concrete-flag counts read from the scanner TSV."""

    source_path: Path
    scanner_row_count: int
    excluded_flags: list[str]
    union_concrete_count: int
    union_family_count: int
    concrete_by_version: dict[str, int]
    family_by_version: dict[str, int]
    incremental_by_library: dict[str, int]


@dataclass(frozen=True)
class PaperNumbers:
    """All computed numbers that are expected to appear in the paper text."""

    common_fflags: DerivedFlagFile
    combined_mllvm: DerivedFlagFile
    per_version_flags: list[VersionFlagSet]
    problematic: ProblematicCounts

    @property
    def filtered_raw_total(self) -> int:
        """Total raw flags after applying ``BLOCK_FLAG_KWDS``."""
        return self.common_fflags.filtered_count + self.combined_mllvm.filtered_count

    @property
    def concrete_union_total(self) -> int:
        """Total concrete flags from the combined middle/back-end flag sets."""
        return self.common_fflags.concrete_count + self.combined_mllvm.concrete_count

    @property
    def phase1_one_library_analyses(self) -> int:
        """Nominal Phase 1 matrix size before target filtering and build failures."""
        flags_per_version = sum(
            version.total_concrete_count for version in self.per_version_flags
        )
        return flags_per_version * EXPERIMENT_ARCHS * EXPERIMENT_OPT_LEVELS

    @property
    def phase1_total_analyses(self) -> int:
        """Nominal Phase 1 matrix size for all discovery libraries."""
        return self.phase1_one_library_analyses * PHASE1_DISCOVERY_LIBRARIES

    @property
    def phase1_total_approx(self) -> str:
        """Manuscript-style rounded Phase 1 count."""
        return approx_millions(self.phase1_total_analyses)


def suffixed_path(path: Path, suffix: str, output_dir: Path | None = None) -> Path:
    """Return ``path`` with ``_<suffix>`` inserted before the extension."""
    base_dir = output_dir if output_dir is not None else path.parent
    return base_dir / f"{path.stem}_{suffix}{path.suffix}"


def rel(path: Path) -> Path:
    """Render paths relative to the repository root when possible."""
    try:
        return path.relative_to(REPO_ROOT)
    except ValueError:
        return path


def non_comment_flag_lines(path: Path) -> list[str]:
    """Read non-empty, non-comment lines from a flag file."""
    lines: list[str] = []
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            lines.append(stripped)
    return lines


def passes_keyword_filter(flag_line: str) -> bool:
    """Apply the same keyword filter used by ``flagcounts.py``."""
    flag_name = flag_line.split(maxsplit=1)[0]
    return not any(keyword in flag_name for keyword in BLOCK_FLAG_KWDS)


def write_lines(path: Path, lines: Sequence[str]) -> None:
    """Write a newline-terminated text file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + ("\n" if lines else ""))


def expand_concrete_flags(filtered_path: Path, *, is_mllvm: bool) -> list[str]:
    """Expand a filtered flag file through ``FlagManager.real_flags``."""
    if is_mllvm:
        manager = FlagManager(mllvm_flag_file=str(filtered_path))
    else:
        manager = FlagManager(flag_file=str(filtered_path))
    return list(manager.real_flags)


def expand_combined_concrete_flags(
    fflags_filtered_path: Path,
    mllvm_filtered_path: Path,
) -> list[str]:
    """Expand one common front/middle-end set plus one LLVM back-end set."""
    manager = FlagManager(
        flag_file=str(fflags_filtered_path),
        mllvm_flag_file=str(mllvm_filtered_path),
    )
    return list(manager.real_flags)


def derive_flag_file(
    label: str,
    source_path: Path,
    *,
    is_mllvm: bool,
    output_dir: Path | None = None,
) -> DerivedFlagFile:
    """Filter one flag file, expand concrete flags, and write both outputs."""
    source_lines = non_comment_flag_lines(source_path)
    filtered_lines = [line for line in source_lines if passes_keyword_filter(line)]

    filtered_path = suffixed_path(source_path, "filtered", output_dir)
    write_lines(filtered_path, filtered_lines)

    concrete_flags = expand_concrete_flags(filtered_path, is_mllvm=is_mllvm)
    concrete_path = suffixed_path(source_path, "concrete", output_dir)
    write_lines(concrete_path, concrete_flags)

    return DerivedFlagFile(
        label=label,
        source_path=source_path,
        filtered_path=filtered_path,
        concrete_path=concrete_path,
        source_candidate_count=len(source_lines),
        filtered_count=len(filtered_lines),
        concrete_count=len(concrete_flags),
    )


def flag_family(flag: str) -> str:
    """Fold value-bearing flags to their flag-name family."""
    return flag.split("=", 1)[0]


def read_problematic_counts(path: Path) -> ProblematicCounts:
    """Count scanner-shortlisted concrete flags from the problematic-flag TSV."""
    with path.open(newline="") as f:
        scanner_rows = list(csv.DictReader(f, delimiter="\t"))

    excluded = sorted(
        row["Flag"] for row in scanner_rows if row["Flag"] in MANUAL_FALSE_POSITIVES
    )
    rows = [row for row in scanner_rows if row["Flag"] not in MANUAL_FALSE_POSITIVES]

    # Incremental discovery: flags first seen when each library was added.
    seen: set[str] = set()
    incremental_by_library: dict[str, int] = {}
    for library in PHASE1_LIBRARY_ORDER:
        found = {
            row["Flag"] for row in rows if library in row["Projs"].split("|")
        }
        incremental_by_library[library] = len(found - seen)
        seen |= found

    concrete_by_version: dict[str, int] = {}
    family_by_version: dict[str, int] = {}
    for version in CLANG_VERSIONS:
        version_rows = [
            row for row in rows
            if version in row["Versions"].split("|")
        ]
        concrete_by_version[version] = len(version_rows)
        family_by_version[version] = len(
            {flag_family(row["Flag"]) for row in version_rows}
        )

    return ProblematicCounts(
        source_path=path,
        scanner_row_count=len(scanner_rows),
        excluded_flags=excluded,
        union_concrete_count=len(rows),
        incremental_by_library=incremental_by_library,
        union_family_count=len({flag_family(row["Flag"]) for row in rows}),
        concrete_by_version=concrete_by_version,
        family_by_version=family_by_version,
    )


def derive_all_numbers(args: argparse.Namespace) -> PaperNumbers:
    """Compute every number that the report maps back to the manuscript."""
    common_fflags = derive_flag_file(
        "common GCC/Clang flags",
        args.fflags,
        is_mllvm=False,
        output_dir=args.output_dir,
    )
    combined_mllvm = derive_flag_file(
        "combined LLVM back-end flags",
        args.mllvmflags,
        is_mllvm=True,
        output_dir=args.output_dir,
    )

    per_version_flags: list[VersionFlagSet] = []
    for version in CLANG_VERSIONS:
        mllvm_source_path = getattr(args, f"mllvmflags{version}")
        mllvm = derive_flag_file(
            f"Clang {version} LLVM back-end flags",
            mllvm_source_path,
            is_mllvm=True,
            output_dir=args.output_dir,
        )

        # Phase 1 combines common GCC/Clang flags with version-specific
        # mllvmflags{14,18,20}_nouseless.txt rather than the combined union.
        version_concrete_flags = expand_combined_concrete_flags(
            common_fflags.filtered_path,
            mllvm.filtered_path,
        )
        per_version_flags.append(
            VersionFlagSet(
                version=version,
                mllvm=mllvm,
                common_fflags_concrete_count=common_fflags.concrete_count,
                total_concrete_count=len(version_concrete_flags),
            )
        )

    return PaperNumbers(
        common_fflags=common_fflags,
        combined_mllvm=combined_mllvm,
        per_version_flags=per_version_flags,
        problematic=read_problematic_counts(args.problematic_flags),
    )


def approx_millions(value: int) -> str:
    """Format an integer count as the one-decimal M notation used in prose."""
    return f"{value / 1_000_000:.1f}M"


def english_list(values: Sequence[int]) -> str:
    """Format three manuscript counts as ``x, y, and z``."""
    strings = [str(value) for value in values]
    return ", ".join(strings[:-1]) + f", and {strings[-1]}"


def version_total_counts(numbers: PaperNumbers) -> list[int]:
    """Return Clang 14/18/20 concrete-flag totals in manuscript order."""
    return [version.total_concrete_count for version in numbers.per_version_flags]


def version_totals_expr(numbers: PaperNumbers) -> str:
    """Return the exact per-version flag-count sum used in the Phase 1 formula."""
    return " + ".join(str(count) for count in version_total_counts(numbers))


def problematic_concrete_values(numbers: PaperNumbers) -> list[int]:
    """Return problematic concrete-flag counts in Clang 14/18/20 order."""
    return [
        numbers.problematic.concrete_by_version[version]
        for version in CLANG_VERSIONS
    ]


def problematic_family_values(numbers: PaperNumbers) -> list[int]:
    """Return family-folded problematic counts in Clang 14/18/20 order."""
    return [
        numbers.problematic.family_by_version[version]
        for version in CLANG_VERSIONS
    ]


def find_line(path: Path, needle: str) -> int | None:
    """Find the first 1-based line number containing ``needle``."""
    if not path.exists():
        return None
    for lineno, line in enumerate(path.read_text().splitlines(), 1):
        if needle in line:
            return lineno
    return None


def line_ref(path: Path, needle: str) -> str:
    """Return a compact file:line reference, or a missing-snippet marker."""
    lineno = find_line(path, needle)
    if lineno is None:
        return f"{rel(path)}:? (missing: {needle})"
    return f"{rel(path)}:{lineno}"


def check_snippets(path: Path, snippets: Sequence[str]) -> list[str]:
    """Return manuscript snippets that are absent from ``path``."""
    text = path.read_text() if path.exists() else ""
    return [snippet for snippet in snippets if snippet not in text]


def generated_files(numbers: PaperNumbers) -> list[tuple[str, Path, int]]:
    """List generated files in the same order as the report prints them."""
    derived_files = [
        numbers.common_fflags,
        numbers.combined_mllvm,
        *(version.mllvm for version in numbers.per_version_flags),
    ]

    generated: list[tuple[str, Path, int]] = []
    for derived in derived_files:
        generated.append(
            (f"{derived.label} filtered", derived.filtered_path, derived.filtered_count)
        )
        generated.append(
            (f"{derived.label} concrete", derived.concrete_path, derived.concrete_count)
        )
    return generated


def print_constants() -> None:
    """Print the handwritten dimensions, separate from computed counts."""
    print("=== Handwritten experiment dimensions ===")
    print(f"discovery libraries     {PHASE1_DISCOVERY_LIBRARIES}  BearSSL, MbedTLS, PQClean")
    print(f"target platforms        {EXPERIMENT_ARCHS}")
    print(f"optimization levels     {EXPERIMENT_OPT_LEVELS}")
    print(f"Clang versions          {', '.join(CLANG_VERSIONS)}")
    print("All flag counts below are recomputed from files; they are not stored as constants.")


def print_stage_report(numbers: PaperNumbers) -> None:
    """Print the data-flow stages that produce the paper-facing numbers."""
    print("\n=== Stage 1: keyword filter from flagcounts.py ===")
    print(f"filter keywords         {len(BLOCK_FLAG_KWDS)}  BLOCK_FLAG_KWDS")
    for derived in [numbers.common_fflags, numbers.combined_mllvm]:
        print(
            f"{derived.label:<31} "
            f"{derived.source_candidate_count:>5} input flags -> "
            f"{derived.filtered_count:>5} after filter  {rel(derived.source_path)}"
        )
    print(
        "paper raw total         "
        f"{numbers.filtered_raw_total} = "
        f"{numbers.common_fflags.filtered_count} + {numbers.combined_mllvm.filtered_count}"
    )

    print("\n=== Stage 2: concrete expansion from flag_manager.py ===")
    for derived in [numbers.common_fflags, numbers.combined_mllvm]:
        print(
            f"{derived.label:<31} "
            f"{derived.filtered_count:>5} filtered -> "
            f"{derived.concrete_count:>5} concrete  {rel(derived.concrete_path)}"
        )
    print(
        "paper concrete total    "
        f"{numbers.concrete_union_total} = "
        f"{numbers.common_fflags.concrete_count} + {numbers.combined_mllvm.concrete_count}"
    )

    print("\n=== Stage 3: version-specific Phase 1 flag sets ===")
    print("common GCC/Clang concrete flags are reused for every Clang version.")
    for version_set in numbers.per_version_flags:
        print(
            f"Clang {version_set.version:<2} total concrete "
            f"{version_set.total_concrete_count:>5} = "
            f"{version_set.common_fflags_concrete_count} common + "
            f"{version_set.mllvm.concrete_count} LLVM back-end"
        )
    print(
        "Phase 1 nominal matrix  "
        f"{numbers.phase1_total_analyses:,} ~= {numbers.phase1_total_approx} = "
        f"{PHASE1_DISCOVERY_LIBRARIES} libraries x {EXPERIMENT_ARCHS} archs x "
        f"{EXPERIMENT_OPT_LEVELS} opt levels x ({version_totals_expr(numbers)}) flags"
    )
    print(f"one-library nominal     {numbers.phase1_one_library_analyses:,}")

    print("Target filtering and failed builds reduce completed analyses below this nominal matrix.")
    print("\n=== Stage 4: counts of supplied shortlist (not rediscovery) ===")
    print(f"source                  {rel(numbers.problematic.source_path)}")
    print(f"scanner rows            {numbers.problematic.scanner_row_count}")
    print(
        "manual false positives  "
        f"{len(numbers.problematic.excluded_flags)}  "
        f"{', '.join(numbers.problematic.excluded_flags) or '-'}"
    )
    print(f"union concrete flags    {numbers.problematic.union_concrete_count}")
    print(
        "incremental by library  "
        + ", ".join(
            f"{library} +{count}"
            for library, count in numbers.problematic.incremental_by_library.items()
        )
        + f" = {sum(numbers.problematic.incremental_by_library.values())}"
    )
    print(
        "by Clang version        "
        f"{english_list(problematic_concrete_values(numbers))} concrete rows for "
        f"{', '.join('Clang ' + version for version in CLANG_VERSIONS)}"
    )
    print(
        "family-folded check     "
        f"{english_list(problematic_family_values(numbers))} by version; "
        f"{numbers.problematic.union_family_count} union families"
    )


def print_generated_files(numbers: PaperNumbers) -> None:
    """Print the concrete files written by this run."""
    print("\n=== Generated provenance files ===")
    for label, path, count in generated_files(numbers):
        print(f"{label:<38} {count:>6}  {rel(path)}")


def print_manuscript_map(numbers: PaperNumbers) -> None:
    """Map computed values to their locations in ``experiment_setting.tex``."""
    problematic_list = english_list(problematic_concrete_values(numbers))

    print("\n=== Manuscript number map ===")
    print(f"{line_ref(EXPERIMENT_TEX, f'{numbers.filtered_raw_total} optimization')}")
    print(
        "  computed as filtered raw flags: "
        f"{numbers.filtered_raw_total} = "
        f"{numbers.common_fflags.filtered_count} GCC/Clang + "
        f"{numbers.combined_mllvm.filtered_count} LLVM back-end"
    )

    print(
        f"{line_ref(EXPERIMENT_TEX, f'{numbers.common_fflags.filtered_count} flags configure')}"
    )
    print(
        "  computed as split after BLOCK_FLAG_KWDS filtering: "
        f"{numbers.common_fflags.filtered_count} and {numbers.combined_mllvm.filtered_count}"
    )

    print(f"{line_ref(EXPERIMENT_TEX, f'{numbers.concrete_union_total} concrete flags')}")
    print(
        "  computed as concrete expansion of combined files: "
        f"{numbers.concrete_union_total} = "
        f"{numbers.common_fflags.concrete_count} + {numbers.combined_mllvm.concrete_count}"
    )

    print(f"{line_ref(EXPERIMENT_TEX, numbers.phase1_total_approx)}")
    print(
        "  computed as Phase 1 discovery scale: "
        f"{numbers.phase1_total_analyses:,} ~= {numbers.phase1_total_approx}"
    )
    print(
        "  exact formula: "
        f"{PHASE1_DISCOVERY_LIBRARIES} * {EXPERIMENT_ARCHS} * {EXPERIMENT_OPT_LEVELS} * "
        f"({version_totals_expr(numbers)})"
    )

    print(f"{line_ref(EXPERIMENT_TEX, problematic_list)}")
    print(
        "  computed from TSV rows and Versions column: "
        f"{numbers.problematic.union_concrete_count} union; "
        f"{problematic_list} by version"
    )

    print(f"{line_ref(EXPERIMENT_TEX, 'about 160 per compiler version')}")
    print("  paper approximation of the problematic concrete-flag count per compiler version")

    inc = numbers.problematic.incremental_by_library
    print(f"{line_ref(EXPERIMENT_TEX, f'{inc[PHASE1_LIBRARY_ORDER[0]]} problematic flags using')}")
    print(
        "  computed as incremental discovery by library: "
        + ", ".join(f"{lib} +{n}" for lib, n in inc.items())
        + " (after removing manual false positives)"
    )


def manuscript_snippets(numbers: PaperNumbers) -> list[str]:
    """Return computed snippets that should appear in ``experiment_setting.tex``."""
    return [
        f"{numbers.filtered_raw_total} optimization",
        f"{numbers.common_fflags.filtered_count} flags configure",
        f"{numbers.combined_mllvm.filtered_count} flags configure",
        f"{numbers.concrete_union_total} concrete flags",
        f"{numbers.common_fflags.concrete_count} from",
        f"{numbers.combined_mllvm.concrete_count} from",
        numbers.phase1_total_approx,
        f"{PHASE1_DISCOVERY_LIBRARIES} \\text{{ libraries}}",
        "4\\mathrm{k}",
        f"{numbers.phase1_total_approx} analyses",
        f"{numbers.problematic.union_concrete_count} problematic concrete flags",
        english_list(problematic_concrete_values(numbers)),
        "about 160 per compiler version",
        "four remaining libraries",
        f"{numbers.problematic.incremental_by_library['bearssl']} problematic flags using",
        f"additional {numbers.problematic.incremental_by_library['pqclean']} and "
        f"{numbers.problematic.incremental_by_library['mbedtls']} after adding",
    ]


def print_consistency_check(numbers: PaperNumbers) -> bool:
    """Verify that computed paper-facing values occur in the manuscript."""
    print("\n=== Manuscript consistency check ===")
    if not EXPERIMENT_TEX.exists():
        print(f"SKIPPED: {EXPERIMENT_TEX} not found (set CTGREP_EXPERIMENT_TEX to check a manuscript)")
        return True
    missing = check_snippets(EXPERIMENT_TEX, manuscript_snippets(numbers))
    if missing:
        print("FAIL")
        for snippet in missing:
            print(f"  missing in {rel(EXPERIMENT_TEX)}: {snippet}")
        return False
    print("OK: all computed paper-facing numbers were found in experiment_setting.tex.")
    return True


def print_report(numbers: PaperNumbers, *, check: bool = True) -> bool:
    """Print the full provenance report and optionally validate the manuscript."""
    print_constants()
    print_stage_report(numbers)
    print_generated_files(numbers)
    print_manuscript_map(numbers)
    if check:
        return print_consistency_check(numbers)
    return True


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Reproduce paper flag counts, write derived files, and print manuscript provenance."
    )
    parser.add_argument(
        "--fflags",
        type=Path,
        default=TOOLS_DIR / "fflags_combined_valid.txt",
        help="Input GCC/Clang flag file.",
    )
    parser.add_argument(
        "--mllvmflags",
        type=Path,
        default=TOOLS_DIR / "mllvmflags_combined.txt",
        help="Input LLVM back-end flag file.",
    )
    for version in CLANG_VERSIONS:
        parser.add_argument(
            f"--mllvmflags{version}",
            type=Path,
            default=TOOLS_DIR / f"mllvmflags{version}_nouseless.txt",
            help=f"Input LLVM back-end flag file used for Clang {version}.",
        )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "results" / "flag_provenance",
        help="Directory for the generated *_filtered/*_concrete files (default: results/flag_provenance).",
    )
    parser.add_argument(
        "--problematic-flags",
        type=Path,
        default=TOOLS_DIR / "problematic_flags.tsv",
        help="Problematic concrete flag TSV (default: the paper's 218-flag table).",
    )
    parser.add_argument(
        "--no-check",
        action="store_true",
        help="Do not verify that computed numbers appear in experiment_setting.tex.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    """CLI entry point."""
    args = parse_args(argv)
    numbers = derive_all_numbers(args)
    ok = print_report(numbers, check=not args.no_check)
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
