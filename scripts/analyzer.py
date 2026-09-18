import json
import os
import sys
import logging
from collections import defaultdict
from utils import src_has_branch, src_has_memop, is_trivial

# While this creates a module logger, it inherits from root logger
logger = logging.getLogger(__name__)

def load_json_data(filepath):
    """Load and parse LLVM message JSON data."""
    data = defaultdict(dict)
    try:
        with open(filepath, 'r') as f:
            for line_num, line in enumerate(f, 1):
                if not line.startswith('{'):
                    continue
                try:
                    obj = json.loads(line, strict=False)
                    context = obj.get("context")
                    key = (obj["function"], obj["file"])
                    data[context][key] = obj
                except Exception as e:
                    logger.error(f"Error parsing line {line_num} in {filepath}: {e}")
                    logger.error(f"Line content: {line.strip()}")
    except Exception as e:
        logger.error(f"Error loading {filepath}: {e}")
        return None
    return data

def extract_problems(data):
    """Extract problems from a single dataset using oracle approach.
    Returns: dict with key (function, file) -> dict in final result format
    """
    problems = {}
    if not data:
        return problems
        
    data_ir = data.get("IRCountInstr", {})
    data_mf = data.get("MFCountInstr", {})
    cond_lines_by_file = defaultdict(set)
    
    for key, ir_obj in data_ir.items():
        function, filepath = key
        cond_lines = ir_obj.get("cond_lines", [])
        cond_lines_by_file[filepath].update(cond_lines)

    for key, mf_obj in data_mf.items():
        # check data_ir not empty first as IRCountInstr may not work on edge cases, eg. clang14 -flegacy-pass-manager
        if not data_ir or (data_ir and key not in data_ir):
            continue
            
        ir_obj = data_ir[key]
        function, filepath = key
        if is_trivial(function) or is_trivial(filepath):
            # Skip trivial functions or files
            continue
        
        # Get data using oracle approach
        # NOTE: thought about accurate to loc, but many FP and no more foundings
        # see https://godbolt.org/z/q4MYKrhra -Os can locate cjump char on loop condition end instead of start
        cond_lines = cond_lines_by_file[filepath] or ir_obj.get("cond_lines", [])
        # NOTE: backend cjump lines may contain code inlined from other functions which do not exist at all in IR, causing FP
        # solution: maintain all IR cond_lines for each file, then check new cjump lines against whole file instead of within ir_obj for single func
        # reduced many obvious FP on if/for/while, still a few when inlined from other files
        cjump_lines = mf_obj.get("cjump_lines", [])
        mdivs = mf_obj.get("mdiv_insts", [])
        
        # get unique mmem locations, in format of "line:col"
        mem_lines = ir_obj.get("mem_lines", [])
        mem_cols = ir_obj.get("mem_cols", [])
        mem_locs = [f"{line}:{col}" for line, col in zip(mem_lines, mem_cols)]
        mmem_lines = mf_obj.get("mmem_lines", [])
        mmem_cols = mf_obj.get("mmem_cols", [])
        mmem_locs = [f"{line}:{col}" for line, col in zip(mmem_lines, mmem_cols)]
        cmov_lines = mf_obj.get("cmov_lines", [])
        cmov_cols = mf_obj.get("cmov_cols", [])
        cmov_locs = [f"{line}:{col}" for line, col in zip(cmov_lines, cmov_cols)]
        
        # Oracle for cjump: MIR has new cjump_lines beyond IR cond_lines (whole file since cjump_lines contain inlined code from other funcs)
        # Oracle for mdiv: any mdiv_insts in MIR is non-CT
        ## (Deprecated) Oracle for mmem: MIR has new mmems (on unique location) beyond IR, and fewer mmem_insts than IR mem_insts
        # Oracle for mmem: MIR has mmems using cmov def reg as address, and located on same source loc
        new_cjumps = set(cjump_lines) - set(cond_lines)
        new_mdivs = set(mdivs)
        # new_mmems = set(mmem_locs) - set(mem_locs)  # Deprecated, check cmov instead
        # intersection of cmov_locs and mmem_locs
        new_mmems = set()
        for i, (cmov_line, mmem_line) in enumerate(zip(cmov_lines, mmem_lines)):
            # NOTE: found no TP at different loc, so also need to ensure same column
            # TP: x[u] = (mask1 & x[u]) | (mask2 & t1[u]);  // both cmov/mmem at |
            # FP: t2[v] |= mask & base[v];  // csel at &, str at |=, always access same mem
            cmov_col, mmem_col = cmov_cols[i], mmem_cols[i]
            if cmov_line == mmem_line and cmov_col == mmem_col:
                new_mmems.add(mmem_locs[i])
        # Get corresponding source lines and instructions for new cjumps
        cjump_candidates = []
        for line in new_cjumps:
            try:
                # line may have muliple occurance, find all indices where this line appears
                indices = [i for i, x in enumerate(cjump_lines) if x == line]
                for idx in indices:
                    src = mf_obj["cjump_srcs"][idx]
                    inst = mf_obj["cjump_insts"][idx]
                    char = mf_obj["cjump_chars"][idx]
                    col = mf_obj["cjump_cols"][idx]
                    # cjump FP filter: corresponding source no branch semantic
                    # NOTE: disable src-based filter to make csv complete, allow flexible post-processing
                    if src:# and not src_has_branch(src, col):
                        cjump_candidates.append((line, src, inst, char, col))
            except (IndexError):
                continue

        mdiv_candidates = []
        for inst in new_mdivs:
            try:
                idx = mdivs.index(inst)
                src = mf_obj["mdiv_srcs"][idx]
                line = mf_obj["mdiv_lines"][idx]
                char = mf_obj["mdiv_chars"][idx]
                col = mf_obj["mdiv_cols"][idx]
                mdiv_candidates.append((line, src, inst, char, col))
            except (ValueError, IndexError):
                continue
        
        mmem_candidates = []
        for loc in new_mmems:
            try:
                idx = mmem_locs.index(loc)
                src = mf_obj["mmem_srcs"][idx]
                line = mf_obj["mmem_lines"][idx]
                inst = mf_obj["mmem_insts"][idx]
                char = mf_obj["mmem_chars"][idx]
                col = mf_obj["mmem_cols"][idx]
                # if "implicit-def" in inst:
                #     continue
                # # stricter filter: consider leak only if the line has fewer unique mmem locs than mem locs
                # unique_mmem_locs_this_line = set(loc for loc in mmem_locs if loc.startswith(f"{line}:"))
                # unique_mem_locs_this_line = set(loc for loc in mem_locs if loc.startswith(f"{line}:"))
                # if len(unique_mmem_locs_this_line) >= len(unique_mem_locs_this_line):
                #     continue
                # # mmem FP filter: corresponding source no memory operation semantic
                # NOTE: disable src-based filter to make csv complete, allow flexible post-processing
                if src:# and not src_has_memop(src, col):
                    mmem_candidates.append((line, src, inst, char, col))
            except (ValueError, IndexError):
                continue
        
        if cjump_candidates or mdiv_candidates or mmem_candidates:
            result = {
                "function": function,
                "file": filepath,
                "base_obj": None,  # Will be set later if needed
                "opt_obj": mf_obj,
            }
            
            if cjump_candidates:
                result["introduced_cjumps"] = [
                    {"line": line, "source": src, "char": char, "inst": inst, "col": col}
                    for line, src, inst, char, col in cjump_candidates
                ]
            if mdiv_candidates:
                result["introduced_mdivs"] = [
                    {"line": line, "source": src, "char": char, "inst": inst, "col": col}
                    for line, src, inst, char, col in mdiv_candidates
                ]
            if mmem_candidates:
                result["introduced_mmems"] = [
                    {"line": line, "source": src, "char": char, "inst": inst, "col": col}
                    for line, src, inst, char, col in mmem_candidates
                ]
            
            problems[key] = result
    
    return problems

def compare_data(base_data, opt_data):
    """Compare two sets of LLVM message data to find optimization-introduced problems."""
    # Extract problems from optimized data
    opt_problems = extract_problems(opt_data)
    
    if base_data:
        # Flag mode: need to compare optimized data against base data
        base_problems = extract_problems(base_data)
        
        # Keep only problems that are new in opt_data (not in base_data)
        results = {}
        for key, opt_problem in opt_problems.items():
            if key not in base_problems:
                # Function/file not in base, keep all problems
                results[key] = opt_problem
            else:
                # Function/file exists in base, filter out existing problems
                base_problem = base_problems[key]
                
                # Compare using (line, source, char) only - exclude inst due to text representation differences
                def make_comparable_key(item):
                    return (item["line"], item["source"], item["char"], item["col"])
                
                # Get comparable sets for base problems
                base_cjumps = {make_comparable_key(c) for c in base_problem.get("introduced_cjumps", [])}
                base_mdivs = {make_comparable_key(d) for d in base_problem.get("introduced_mdivs", [])}
                base_mmems = {make_comparable_key(m) for m in base_problem.get("introduced_mmems", [])}
                
                # Find problems that are truly new
                new_cjumps = [c for c in opt_problem.get("introduced_cjumps", []) 
                            if make_comparable_key(c) not in base_cjumps]
                new_mdivs = [d for d in opt_problem.get("introduced_mdivs", []) 
                            if make_comparable_key(d) not in base_mdivs]
                new_mmems = [m for m in opt_problem.get("introduced_mmems", []) 
                            if make_comparable_key(m) not in base_mmems]
                
                if new_cjumps or new_mdivs or new_mmems:
                    # Create result with only new issues
                    result = {
                        "function": opt_problem["function"],
                        "file": opt_problem["file"],
                        "base_obj": base_problem["opt_obj"],
                        "opt_obj": opt_problem["opt_obj"],
                    }
                    
                    if new_cjumps:
                        result["introduced_cjumps"] = new_cjumps
                    if new_mdivs:
                        result["introduced_mdivs"] = new_mdivs
                    if new_mmems:
                        result["introduced_mmems"] = new_mmems
                    
                    results[key] = result
    else:
        # Levels mode: use oracle-based detection within single dataset
        results = opt_problems
    
    return results

def save_results(results, proj_name, arch, result_type, opt_name, res_dir):
    """Save analysis results to per-architecture JSONL and CSV files."""
    os.makedirs(res_dir, exist_ok=True)
    
    # Save/update JSONL results (each line is a JSON object)
    json_path = os.path.join(res_dir, f"{proj_name}_{result_type}_{arch}.json")

    # Collect all cases for this optimization
    cases = []
    for (function, filepath), value in results.items():
        for problem_type in ["cjump", "mdiv", "mmem"]:
            for problem in value.get(f"introduced_{problem_type}s", []):
                case = {
                    "function": function,
                    "file": filepath,
                    "line": problem["line"],
                    "col": problem["col"],
                    "source": problem["source"],
                    "char": problem["char"],
                    "type": problem_type,
                    "arch": arch
                }
                cases.append(case)
            
    if cases:
        # Create optimization record with count, primary key should be "optimization"
        opt_record = {
            "optimization": opt_name,
            "count": len(cases),
            "cases": cases,
            "arch": arch
        }
        
        # Append the new record to the JSONL file
        with open(json_path, 'a') as f:
            f.write(json.dumps(opt_record) + '\n')

    # Append to CSV using tab as delimiter
    csv_path = os.path.join(res_dir, f"{proj_name}_{result_type}_{arch}.csv")
    write_header = not os.path.exists(csv_path)
    added_rows = 0
    with open(csv_path, 'a') as f:
        if write_header:
            logger.info(f"Creating new CSV file: {csv_path}")
            f.write("function\tfile\tline\tcol\tsource\tchar\ttype\toptimization\n")
        for key, data in results.items():
            function, filepath = key if isinstance(key, tuple) else (data["function"], data["file"])
            
            for problem_type in ["cjump", "mdiv", "mmem"]:
                for problem in data.get(f"introduced_{problem_type}s", []):
                    line = str(problem["line"])
                    col = problem["col"]
                    source = problem["source"]
                    char = problem["char"]
                    f.write(f"{function}\t{filepath}\t{line}\t{col}\t{source}\t{char}\t{problem_type}\t{opt_name}\n")
                    added_rows += 1
    
    if added_rows:
        logger.info(f"Added {added_rows} new problems to {csv_path}")
    
    # Generate deduplicated CSV periodically
    generate_unique_csv(proj_name, arch, result_type, res_dir)
    
    logger.info(f"Updated results in {json_path} and {csv_path}")

def generate_unique_csv(proj_name, arch, result_type, res_dir):
    """Generate deduplicated CSV by merging optimization levels for same problems."""
    csv_path = os.path.join(res_dir, f"{proj_name}_{result_type}_{arch}.csv")
    unique_path = os.path.join(res_dir, f"{proj_name}_{result_type}_{arch}_unique.csv")
    
    if not os.path.exists(csv_path):
        return
    
    logger.info(f"Generating deduplicated CSV: {unique_path}")
    # Group by everything except optimization level using tab delimiter
    problems = defaultdict(set)
    with open(csv_path) as f:
        header = next(f)
        for csv_line in f:
            func, file, line, col, src, char, type_, opt = csv_line.strip().split('\t')
            key = (func, file, line, col, src, char, type_)
            problems[key].add(opt)
            
    # Write deduplicated CSV with merged optimization levels
    with open(unique_path, 'w') as f:
        f.write("function\tfile\tline\tcol\tsource\tchar\ttype\toptimization\n")
        for (func, file, line, col, src, char, type_), opts in problems.items():
            merged_opt = '|'.join(sorted(opts))
            f.write(f"{func}\t{file}\t{line}\t{col}\t{src}\t{char}\t{type_}\t{merged_opt}\n")
    
    # Count unique problems
    problem_count = len(problems)
    logger.info(f"Found {problem_count} unique problems after deduplication")

def remove_redundant_flag_problems(flag_csv_path):
    """Remove problems from flag CSV that already exist in corresponding levels CSV."""
    import re
    
    # Parse flag CSV filename to get project and arch
    filename = os.path.basename(flag_csv_path)
    match = re.match(r'(.+)_flag1_(.+)_unique\.csv$', filename)
    if not match:
        logger.error(f"Invalid flag CSV filename format: {filename}")
        return
    
    proj_name, arch = match.groups()
    
    # Construct corresponding levels CSV path
    levels_csv_path = os.path.join(os.path.dirname(flag_csv_path), f"{proj_name}_levels_{arch}_unique.csv")
    
    if not os.path.exists(levels_csv_path):
        logger.warning(f"Corresponding levels CSV not found: {levels_csv_path}")
        return
    
    # Load levels CSV and create set of (line, source, char, type) tuples
    levels_problems = set()
    try:
        with open(levels_csv_path, 'r') as f:
            header = next(f)  # Skip header
            for line in f:
                parts = line.strip().split('\t')
                if len(parts) >= 8:
                    _func, _file, line_num, col, source, char, type_ = parts[:7]
                    levels_problems.add((line_num, col, source, char, type_))
    except Exception as e:
        logger.error(f"Error reading levels CSV {levels_csv_path}: {e}")
        return
    
    # Load flag CSV and filter out redundant problems
    filtered_rows = []
    removed_count = 0
    try:
        with open(flag_csv_path, 'r') as f:
            header = next(f)
            filtered_rows.append(header.strip())
            
            for line in f:
                parts = line.strip().split('\t')
                if len(parts) >= 7:
                    _func, _file, line_num, col, source, char, type_ = parts[:7]
                    problem_key = (line_num, col, source, char, type_)
                    
                    if problem_key not in levels_problems:
                        filtered_rows.append(line.strip())
                    else:
                        removed_count += 1
                        logger.debug(f"Removed redundant problem: {problem_key}")
    except Exception as e:
        logger.error(f"Error reading flag CSV {flag_csv_path}: {e}")
        return
    
    # Create output filename with dedup suffix
    dedup_csv_path = flag_csv_path.replace('_unique.csv', '_dedup.csv')
    
    # Write filtered results to new dedup CSV file
    try:
        with open(dedup_csv_path, 'w') as f:
            for row in filtered_rows:
                f.write(row + '\n')
        
        logger.info(f"Removed {removed_count} redundant problems")
        logger.info(f"Remaining problems: {len(filtered_rows) - 1}")  # -1 for header
        logger.info(f"Deduplicated results written to: {dedup_csv_path}")
        
    except Exception as e:
        logger.error(f"Error writing dedup CSV {dedup_csv_path}: {e}")

def filter_results_by_source(json_path):
    """Filter results in a JSON file by applying src-based semantic checks.
    
    Args:
        json_path: Path to the JSONL results file to filter
    """
    if not os.path.exists(json_path):
        logger.error(f"JSON file not found: {json_path}")
        return
    
    logger.info(f"Applying src-based filtering to: {json_path}")
    
    # Read all records from the JSONL file
    filtered_records = []
    total_cases_before = 0
    total_cases_after = 0
    
    try:
        with open(json_path, 'r') as f:
            for line_num, line in enumerate(f, 1):
                if not line.strip():
                    continue
                    
                try:
                    record = json.loads(line)
                    cases = record.get("cases", [])
                    total_cases_before += len(cases)
                    
                    # Filter cases based on source semantics
                    filtered_cases = []
                    for case in cases:
                        src = case.get("source", "")
                        col = case.get("col", 0)
                        case_type = case.get("type", "")
                        
                        # Apply semantic filters based on case type
                        keep_case = False
                        if case_type == "cjump":
                            # For cjump, keep only if source has branch semantics
                            keep_case = src and src_has_branch(src, col)
                        elif case_type == "mmem":
                            # For mmem, keep only if source has memory operation semantics
                            keep_case = src and src_has_memop(src, col)
                        elif case_type == "mdiv":
                            # For mdiv, keep all cases (no src-based filter needed)
                            keep_case = True
                        
                        if keep_case:
                            filtered_cases.append(case)
                    
                    # Update record with filtered cases
                    if filtered_cases:
                        record["cases"] = filtered_cases
                        record["count"] = len(filtered_cases)
                        filtered_records.append(record)
                        total_cases_after += len(filtered_cases)
                    
                except json.JSONDecodeError as e:
                    logger.error(f"Error parsing JSON at line {line_num}: {e}")
                    continue
                    
    except Exception as e:
        logger.error(f"Error reading {json_path}: {e}")
        return
    
    # Write filtered results back to file
    try:
        with open(json_path, 'w') as f:
            for record in filtered_records:
                f.write(json.dumps(record) + '\n')
        
        removed_cases = total_cases_before - total_cases_after
        logger.info(f"Src-based filtering completed:")
        logger.info(f"  Total cases before: {total_cases_before}")
        logger.info(f"  Total cases after: {total_cases_after}")
        logger.info(f"  Cases removed: {removed_cases}")
        logger.info(f"  Records remaining: {len(filtered_records)}")
        
    except Exception as e:
        logger.error(f"Error writing filtered results to {json_path}: {e}")


if __name__ == "__main__":
    # Configure logging for direct execution
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Example usage
    if len(sys.argv) < 2:
        logger.error("Usage: python analyzer.py <flag_csv_path_or_directory_or_json_path>")
        logger.error("  For CSV deduplication: provide flag CSV path or directory")
        logger.error("  For src-based filtering: provide JSON results path")
        sys.exit(1)
    
    input_path = sys.argv[1]
    
    # Check if input is a JSON file for src-based filtering
    if input_path.endswith('.json') and os.path.isfile(input_path):
        filter_results_by_source(input_path)
        sys.exit(0)
    
    # Check if input is a directory or single file for CSV processing
    if os.path.isdir(input_path):
        # Process all *flag1*_unique.csv files in the directory
        import glob
        pattern = os.path.join(input_path, "*flag1*_unique.csv")
        flag_csv_files = glob.glob(pattern)
        
        if not flag_csv_files:
            logger.error(f"No *flag1*_unique.csv files found in directory: {input_path}")
            sys.exit(1)
        
        logger.info(f"Found {len(flag_csv_files)} flag CSV files to process")
        
        for flag_csv_path in sorted(flag_csv_files):
            logger.info(f"Processing: {os.path.basename(flag_csv_path)}")
            remove_redundant_flag_problems(flag_csv_path)
            
    elif os.path.isfile(input_path):
        # Process single file
        if '_flag1_' in os.path.basename(input_path) and input_path.endswith('_unique.csv'):
            remove_redundant_flag_problems(input_path)
        else:
            logger.error("Please provide a flag CSV file with format: *_flag1_*_unique.csv")
            sys.exit(1)
    else:
        logger.error(f"Invalid path: {input_path} (not a file or directory)")
        sys.exit(1)
