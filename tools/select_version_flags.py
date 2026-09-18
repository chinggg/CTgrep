#!/usr/bin/env python3
"""Write the per-Clang-version problematic concrete flag lists.

Reads the paper's problematic-flag table (default: tools/problematic_flags.tsv,
218 concrete flags) and writes tools/problematic_flags_clang{14,18,20}.txt, one concrete flag per
line in the format scripts/flag_manager.py reads. Also writes the union as
tools/problematic_flags_all.txt.
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_paper_flags import CLANG_VERSIONS, MANUAL_FALSE_POSITIVES  # noqa: E402

TOOLS = Path(__file__).resolve().parent
TABLE = TOOLS / "problematic_flags.tsv"


def main() -> None:
    table = Path(sys.argv[1]) if len(sys.argv) > 1 else TABLE
    rows = [r for r in csv.DictReader(table.open(newline=""), delimiter="\t")
            if r["Flag"] not in MANUAL_FALSE_POSITIVES]
    union = sorted({r["Flag"] for r in rows})
    (TOOLS / "problematic_flags_all.txt").write_text("\n".join(union) + "\n")
    print(f"problematic_flags_all.txt: {len(union)} flags")
    for v in CLANG_VERSIONS:
        flags = sorted({r["Flag"] for r in rows if v in r["Versions"].split("|")})
        out = TOOLS / f"problematic_flags_clang{v}.txt"
        out.write_text("\n".join(flags) + "\n")
        print(f"{out.name}: {len(flags)} flags")


if __name__ == "__main__":
    main()
