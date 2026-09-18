import csv
import os
import re
import argparse
from collections import defaultdict


BLOCK_FLAG_KWDS = [
    'fstack-protect', 'profil', 'stack-protect', '-ftrapv', 'force-vector-width',
    'force-vector-interleave', 'force-target-instruction-cost', 'instrument-functions',
    '--expand-div-rem-bits', '-fwrapv', '--scalar-evolution-huge-expr-threshold',
    '--jump-threading-threshold', '--enable-nontrivial-unswitch', '--scev-cheap-expansion-budget',
    '-ffreestanding', '-fno-builtin', '-fforce-enable-int128'
]

# Root-cause pass columns expected in rootcause CSVs (in output order).
PASS_FIELDS = ["pass-select", "pass-cond", "pass-cjump", "pass-div", "pass-mdiv"]

FILE_RE = re.compile(r"^(.*?)_(flag1|rootcause)_(.*?)_unique\.csv$")


def extract_version(dirpath):
    match = re.search(r'(?:res|rootcause)(\d+)', os.path.basename(os.path.normpath(dirpath)))
    return match.group(1) if match else ""


def _parse_pass_cell(raw):
    """Split a pass-* cell (e.g. '"X"|"Y"') into a set of unique pass names."""
    if not raw:
        return set()
    return {v.strip().strip('"') for v in raw.split("|") if v.strip().strip('"')}


def collect_flag_data(search_dirs, flag_type=None, merge_values=False, include_projs=None,
                      exclude_archs=None, no_block=False):
    """Scan all source files and return (flag_data, scanned_projects, scanned_versions, scanned_kinds, has_pass).

    The CSV "kind" (flag1 or rootcause) is inferred from each filename — files named
    *_rootcause_*_unique.csv are treated as rootcause input, *_flag1_*_unique.csv as flag1.
    Both can be mixed across the input directories; pass-* columns are emitted when any
    rootcause file is processed.
    """
    def new_entry():
        d = {"values": set(), "count": 0, "types": set(), "levels": set(),
             "projs": set(), "archs": set(), "versions": set()}
        d.update({p: set() for p in PASS_FIELDS})
        return d
    flag_data = defaultdict(new_entry)
    scanned_projects = set()
    scanned_versions = set()
    scanned_kinds = set()
    has_pass = False

    if isinstance(search_dirs, str):
        search_dirs = [search_dirs]

    for search_dir in search_dirs:
        version = extract_version(search_dir)
        matched = []
        for f in os.listdir(search_dir):
            m = FILE_RE.match(f)
            if not m:
                continue
            matched.append((f, m))
        print(f"Processing {len(matched)} files in '{search_dir}' (version={version or '?'})")

        if version:
            scanned_versions.add(version)

        for file, m in matched:
            proj, kind, arch = m.group(1), m.group(2), m.group(3)
            if exclude_archs and arch in exclude_archs:
                continue
            if include_projs and proj not in include_projs:
                continue
            scanned_projects.add(proj)
            scanned_kinds.add(kind)

            with open(os.path.join(search_dir, file), "r") as f:
                reader = csv.DictReader(f, delimiter="\t")
                fieldnames = reader.fieldnames or []
                file_pass_fields = [p for p in PASS_FIELDS if p in fieldnames]
                if file_pass_fields:
                    has_pass = True
                for row in reader:
                    opts = row["optimization"].split("|")
                    problem_type = row["type"]
                    if flag_type and problem_type != flag_type:
                        continue

                    row_passes = {p: _parse_pass_cell(row.get(p, "")) for p in file_pass_fields}

                    for opt in opts:
                        level_match = re.match(r"^O(0|1|2|3|s|z|fast)", opt)
                        level = level_match.group(0) if level_match else ""
                        raw_flag = re.sub(r"^O(0|1|2|3|s|z|fast)", "", opt)

                        if not raw_flag:
                            # bare O<level> with no extra flag — keep the level as the flag name
                            flag_name = level
                        elif merge_values and '=' in raw_flag:
                            flag_name, flag_value = raw_flag.split('=', 1)
                            flag_data[flag_name]["values"].add(flag_value)
                        else:
                            flag_name = raw_flag
                        if not no_block and any(kwd in flag_name for kwd in BLOCK_FLAG_KWDS):
                            continue

                        entry = flag_data[flag_name]
                        entry["count"] += 1
                        entry["types"].add(problem_type)
                        entry["levels"].add(level)
                        entry["projs"].add(proj)
                        entry["archs"].add(arch)
                        if version:
                            entry["versions"].add(version)
                        for p, vs in row_passes.items():
                            entry[p] |= vs

    return flag_data, scanned_projects, scanned_versions, scanned_kinds, has_pass


def write_flags(flag_data, output_file, merge_values=False, has_pass=False):
    with open(output_file, "w", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        header = ["Flag", "Count", "Types", "Levels", "Archs", "Projs", "Versions"]
        if has_pass:
            header += PASS_FIELDS
        writer.writerow(header)
        for flag_name, data in sorted(flag_data.items(), key=lambda item: item[1]["count"], reverse=True):
            if merge_values and data["values"]:
                flag_display = f"{flag_name}={'/'.join(sorted(data['values']))}"
            else:
                flag_display = flag_name
            row = [
                flag_display,
                data["count"],
                "|".join(sorted(data["types"])),
                "|".join(sorted(data["levels"])),
                "|".join(sorted(data["archs"])),
                "|".join(sorted(data["projs"])),
                "|".join(sorted(data["versions"])),
            ]
            if has_pass:
                row += ["|".join(sorted(data[p])) for p in PASS_FIELDS]
            writer.writerow(row)
    print(f"  {len(flag_data)} flags → {output_file}")


def process_files(search_dirs, flag_type=None, merge_values=False, output_file=None,
                  include_projs=None, exclude_archs=None, no_block=False):
    """Collect all flag data and write a single output file."""
    flag_data, scanned_projects, scanned_versions, scanned_kinds, has_pass = collect_flag_data(
        search_dirs, flag_type, merge_values, include_projs, exclude_archs, no_block)
    total_flags = len(flag_data)
    print(f"Total flags: {total_flags}, projects: {', '.join(sorted(scanned_projects))}, kinds: {', '.join(sorted(scanned_kinds)) or '-'}")

    if output_file is None:
        version_prefix = f"{next(iter(scanned_versions))}" if len(scanned_versions) == 1 else ""
        mid = f"rootcause{total_flags}" if "rootcause" in scanned_kinds else f"flag{total_flags}"
        output_file = f"problematic{version_prefix}_{mid}_{'+'.join(sorted(scanned_projects))}_{flag_type or 'all'}{'_merged' if merge_values else ''}.csv"
    write_flags(flag_data, output_file, merge_values, has_pass)
    print(f"Output written to: {output_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process flag data from CSV files.")
    parser.add_argument("dirs", nargs="+", help="One or more directories to search for CSV files.")
    parser.add_argument("--type", type=str, help="Filter by problem type (e.g., cjump).")
    parser.add_argument("--merge-values", action="store_true", help="Merge flags with different values into one row.")
    parser.add_argument("--output", type=str, help="Output file name.")
    parser.add_argument("--proj", nargs="+", metavar="PROJ", help="Only include these projects (e.g. --proj bearssl mbedtls).")
    parser.add_argument("--no-arch", nargs="+", metavar="ARCH", help="Exclude these architectures (e.g. --no-arch I686 X8632).")
    parser.add_argument("--no-block", action="store_true", help="Disable BLOCK_FLAG_KWDS filter (include all flags).")
    args = parser.parse_args()

    process_files(
        search_dirs=args.dirs,
        flag_type=args.type,
        merge_values=args.merge_values,
        output_file=args.output,
        include_projs=set(args.proj) if args.proj else None,
        exclude_archs=set(args.no_arch) if args.no_arch else None,
        no_block=args.no_block,
    )

