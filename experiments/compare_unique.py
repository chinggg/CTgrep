#!/usr/bin/env python3
"""Compare freshly produced ``*_unique.csv`` result files with recorded ones.

A unique CSV has one row per distinct violation location
(function, file, line, col, source, char, type) and an ``optimization``
column listing every configuration that triggered it, ``|``-separated
(``O2``, ``O1--fast-isel``, ...).

This reports recorded, reproduced and new violation locations, restricted
to configurations selected for this run. It does not compare the full mapping
from configurations to locations. The default comparison covers cjump, the
focus of the AE functional checks. Use --types to inspect auxiliary types
explicitly. There is no acceptance threshold.

Exit status: 0 when the comparison was reported, 2 on usage or missing-input errors.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

KEY = ("function", "file", "line", "col", "type")
LEVEL_RE = re.compile(r"^(O0|O1|O2|O3|Ofast|Os|Oz)")


def split_config(config: str) -> tuple[str, str]:
    """Split ``O1--fast-isel`` into level ``O1`` and flag ``--fast-isel``."""
    m = LEVEL_RE.match(config)
    if not m:
        return "", config
    return m.group(1), config[m.end():]


def read_unique(path: Path) -> dict[tuple, set[str]]:
    rows: dict[tuple, set[str]] = {}
    with path.open(newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            key = tuple(row[k] for k in KEY)
            rows.setdefault(key, set()).update(
                c for c in row["optimization"].split("|") if c
            )
    return rows


def config_was_run(config: str, levels: set[str], flags: set[str] | None) -> bool:
    level, flag = split_config(config)
    if level and level not in levels:
        return False
    if flag == "":
        return True  # levels-only configuration; the level was run
    return flags is not None and flag in flags


def compare_pair(expected: Path, actual: Path | None, levels: set[str],
                 flags: set[str] | None, types: set[str]
                 ) -> tuple[int, int, int, list[str]]:
    exp = read_unique(expected)
    act = read_unique(actual) if actual and actual.exists() else {}

    run = {
        key for key, configs in exp.items()
        if any(config_was_run(c, levels, flags) for c in configs)
    }
    relevant = {k for k in run if k[4] in types}
    found = {key for key in relevant if key in act}
    extra = {k for k in act if k not in exp and k[4] in types}
    missing_lines = [
        f"    NOT REPRODUCED {k[0]} {k[1]}:{k[2]}:{k[3]} {k[4]}  ({'|'.join(sorted(exp[k]))})"
        for k in sorted(relevant - found)
    ]
    return len(relevant), len(found), len(extra), missing_lines


def load_flags(path: Path | None) -> set[str] | None:
    if path is None:
        return None
    flags: set[str] = set()
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("Flag\t"):
            continue
        flags.add(line.split()[0])
    return flags


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("expected_dir", type=Path, help="directory of recorded *_unique.csv")
    ap.add_argument("actual_dir", type=Path, help="directory of new *_unique.csv")
    ap.add_argument("--levels", default="O0 O1 O2 O3 Os Oz",
                    help="optimization levels that were run (space-separated)")
    ap.add_argument("--flagfile", type=Path,
                    help="flag list that was run; omit for a levels-only run")
    ap.add_argument("--archs", default="",
                    help="only compare files for these architectures (space-separated)")
    ap.add_argument("--mode", choices=["levels", "flag1", "all"], default="all",
                    help="which result files to compare")
    ap.add_argument("--types", default="cjump",
                    help="violation types to compare (default: cjump)")
    args = ap.parse_args()

    for directory in (args.expected_dir, args.actual_dir):
        if not directory.is_dir():
            print(f"result dir not found: {directory}", file=sys.stderr)
            return 2
    levels = set(args.levels.split())
    flags = load_flags(args.flagfile)
    archs = set(args.archs.split())
    types = set(args.types.split())

    total_rel = total_found = total_extra = 0
    all_missing: list[str] = []
    compared = 0
    print(f"{'file':<44} {'recorded':>8} {'reproduced':>10} {'new':>6}")
    for expected in sorted(args.expected_dir.glob("*_unique.csv")):
        name = expected.name
        mode = "flag1" if "_flag1_" in name else "levels"
        if args.mode != "all" and mode != args.mode:
            continue
        if mode == "flag1" and flags is None:
            continue
        arch = name.split("_")[2]
        if archs and arch not in archs:
            continue
        actual = args.actual_dir / name
        rel, found, extra, missing = compare_pair(
            expected, actual, levels, flags if mode == "flag1" else None, types)
        if rel == 0:
            continue
        compared += 1
        status = "" if found == rel else "  <-- incomplete"
        print(f"{name:<44} {rel:>8} {found:>10} {extra:>6}{status}")
        all_missing += missing
        total_rel += rel
        total_found += found
        total_extra += extra

    if compared == 0:
        print("no comparable result files found", file=sys.stderr)
        return 2
    print(f"\n{'/'.join(sorted(types))} locations: {total_found}/{total_rel} recorded locations reproduced, "
          f"{total_extra} new")
    if total_found != total_rel:
        print(f"{total_rel - total_found} recorded locations not reproduced (details below)")
    if all_missing:
        print("\n".join(all_missing[:50]))
        if len(all_missing) > 50:
            print(f"    ... {len(all_missing) - 50} more")
    return 0



if __name__ == "__main__":
    sys.exit(main())
