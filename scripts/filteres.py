import json
import os
import shutil
import sys
import logging
import shutil
import glob
from collections import defaultdict
from utils import src_has_branch, src_has_memop

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

global_cjump_locs = set()  # store (file, line, col) cjump tuples for later mmem filter

def apply_src_filter_to_json(json_path):
    """Apply src-based filtering to a JSON file in place."""
    if not os.path.exists(json_path):
        logger.warning(f"JSON file not found: {json_path}")
        return

    filtered_records = []
    total_cases_before = 0
    total_cases_after = 0
    
    try:
        with open(json_path, 'r') as f:
            for line_num, jsonline in enumerate(f, 1):
                if not jsonline.strip():
                    continue
                    
                try:
                    record = json.loads(jsonline)
                    cases = record.get("cases", [])
                    total_cases_before += len(cases)
                    
                    # Filter cases based on source semantics
                    filtered_cases = []
                    for case in cases:
                        src = case.get("source", "")
                        line = case.get("line", 0)
                        col = case.get("col", 0)
                        case_type = case.get("type", "")
                        file = case.get("file", "")

                        # skip if source empty or line/col is 0
                        if not src or not line or not col:
                            continue
                        
                        # Apply semantic filters based on case type
                        keep_case = False
                        if case_type == "cjump":
                            # For cjump, keep only if source have no branch semantics
                            keep_case = src and not src_has_branch(src, col)
                            if keep_case:
                                global_cjump_locs.add((file, line, col))
                        elif case_type == "mmem":
                            # (Deprecated) For mmem, keep only if source have no memory operation semantics
                            # keep_case = src and not src_has_memop(src, col)
                            # For mmem, later run filter to keep only those with potential cjump leakage at same loc
                            keep_case = True
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
    
    # Write filtered results to output file
    try:
        with open(json_path, 'w') as f:
            for record in filtered_records:
                f.write(json.dumps(record) + '\n')
        
        removed_cases = total_cases_before - total_cases_after
        logger.info(f"\tSrc-based filter on {json_path}: before {total_cases_before}, after {total_cases_after}, removed {removed_cases}")
        
    except Exception as e:
        logger.error(f"Error writing filtered results to {json_path}: {e}")

def filter_mmem_with_cjump_loc(json_path):
    """Filter mmem cases to keep only those with cjump leakage at same loc."""
    if not os.path.exists(json_path):
        return
    filtered_records = []
    total_cases_before = 0
    total_cases_after = 0
    try:
        with open(json_path, 'r') as f:
            for line_num, jsonline in enumerate(f, 1):
                if not jsonline.strip():
                    continue
                try:
                    record = json.loads(jsonline)
                    cases = record.get("cases", [])
                    total_cases_before += len(cases)
                    # Filter mmem cases based on global_cjump_locs
                    filtered_cases = []
                    for case in cases:
                        src = case.get("source", "")
                        line = case.get("line", 0)
                        col = case.get("col", 0)
                        case_type = case.get("type", "")
                        file = case.get("file", "")
                        # Skip if source empty or line/col is 0
                        if not src or not line or not col:
                            continue
                        # Keep mmem cases only if cjump location exists
                        if case_type == "mmem":
                            if (file, line, col) in global_cjump_locs:
                                filtered_cases.append(case)
                        else:
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

    # Write filtered results to output file
    try:
        with open(json_path, 'w') as f:
            for record in filtered_records:
                f.write(json.dumps(record) + '\n')
        removed_cases = total_cases_before - total_cases_after
        logger.info(f"\tFilter mmem with same jump loc on {json_path}: before {total_cases_before}, after {total_cases_after}, removed {removed_cases}")
    except Exception as e:
        logger.error(f"Error writing filtered results to {json_path}: {e}")

def json_to_csv(json_path, csv_path):
    """Convert JSON results to CSV format."""
    if not os.path.exists(json_path):
        return
    
    logger.info(f"Converting JSON {json_path} to CSV {csv_path}")
    
    # First scan to check if any pass-* data exists
    has_pass_data = False
    try:
        with open(json_path, 'r') as json_f:
            for line in json_f:
                if not line.strip():
                    continue
                
                record = json.loads(line)
                cases = record.get("cases", [])
                
                for case in cases:
                    # Check if any pass-* fields have data
                    if (case.get("pass-cond") or case.get("pass-select") or 
                        case.get("pass-cjump") or case.get("pass-div") or 
                        case.get("pass-mdiv") or case.get("pass-mem") or 
                        case.get("pass-mmem")):
                        has_pass_data = True
                        break
                
                if has_pass_data:
                    break
    except Exception as e:
        logger.error(f"Error pre-scanning JSON for pass data: {e}")
    
    with open(csv_path, 'w') as f:
        # Write header with conditional pass-* columns
        header = "function\tfile\tline\tcol\tsource\tchar\ttype\toptimization"
        if has_pass_data:
            header += "\tpass-cond\tpass-select\tpass-cjump\tpass-div\tpass-mdiv\tpass-mem\tpass-mmem"
        f.write(header + "\n")
        
        try:
            with open(json_path, 'r') as json_f:
                for line in json_f:
                    if not line.strip():
                        continue
                    
                    record = json.loads(line)
                    opt_name = record.get("optimization", "unknown")
                    cases = record.get("cases", [])
                    
                    for case in cases:
                        function = case.get("function", "")
                        filepath = case.get("file", "")
                        line_num = case.get("line", "")
                        col = case.get("col", "")
                        source = case.get("source", "")
                        char = case.get("char", "")
                        case_type = case.get("type", "")
                        
                        # Create basic CSV line
                        csv_line = f"{function}\t{filepath}\t{line_num}\t{col}\t{source}\t{char}\t{case_type}\t{opt_name}"
                        
                        # Add pass-* data only if any exists
                        if has_pass_data:
                            pass_cond = case.get("pass-cond", "")
                            pass_select = case.get("pass-select", "")
                            pass_cjump = case.get("pass-cjump", "")
                            pass_div = case.get("pass-div", "")
                            pass_mdiv = case.get("pass-mdiv", "")
                            pass_mem = case.get("pass-mem", "")
                            pass_mmem = case.get("pass-mmem", "")
                            csv_line += f"\t{pass_cond}\t{pass_select}\t{pass_cjump}\t{pass_div}\t{pass_mdiv}\t{pass_mem}\t{pass_mmem}"
                        
                        f.write(csv_line + "\n")
        
        except Exception as e:
            logger.error(f"Error converting JSON to CSV: {e}")

def csv_to_unique_csv(csv_path, unique_csv_path):
    """Generate deduplicated CSV by merging optimization levels for same problems."""
    if not os.path.exists(csv_path):
        return
    
    # Group by everything except optimization level
    problems = defaultdict(list)
    headers = []
    count_before = 0
    
    try:
        with open(csv_path, 'r') as f:
            header_line = next(f).strip()
            headers = header_line.split('\t')
            
            # Check if we have at least the basic columns needed
            if len(headers) < 8:
                logger.error(f"CSV header missing required columns: {header_line}")
                return
                
            # Find the optimization column index
            opt_index = 7  # default index for optimization
            if "optimization" in headers:
                opt_index = headers.index("optimization")
            
            # Track additional columns (pass-* etc.)
            additional_cols = len(headers) - opt_index - 1
            
            for csv_line in f:
                parts = csv_line.strip().split('\t')
                if len(parts) >= 8:
                    # Split into key columns (everything before optimization)
                    key_parts = parts[:opt_index]
                    opt = parts[opt_index]
                    
                    # Save any additional columns after optimization
                    additional_values = parts[opt_index+1:] if len(parts) > opt_index+1 else []
                    
                    # Use key parts as the key for deduplication
                    key = tuple(key_parts)
                    
                    # Store optimization and additional values
                    problems[key].append((opt, additional_values))
                    count_before += 1
    except Exception as e:
        logger.error(f"Error reading CSV {csv_path}: {e}")
        return

    # Write deduplicated CSV with merged optimizations
    try:
        with open(unique_csv_path, 'w') as f:
            # Write header
            f.write(header_line + '\n')
            
            for key, opt_entries in problems.items():
                # Merge optimizations
                opts = set(entry[0] for entry in opt_entries)
                merged_opt = '|'.join(sorted(opts))
                
                # For additional columns, take the first non-empty value for each column
                additional_values = []
                
                # Get the max length of additional values
                max_additional = max((len(entry[1]) for entry in opt_entries), default=0)
                
                if max_additional > 0:
                    # Initialize with empty strings
                    additional_values = [''] * max_additional
                    
                    # For each column position, find the first non-empty value
                    for col_idx in range(max_additional):
                        for opt, add_vals in opt_entries:
                            if col_idx < len(add_vals) and add_vals[col_idx]:
                                additional_values[col_idx] = add_vals[col_idx]
                                break
                
                # Create the output line
                output_line = '\t'.join(list(key) + [merged_opt] + additional_values)
                f.write(output_line + '\n')

        logger.info(f"\tMade unique CSV {unique_csv_path} containing {len(problems)} unique cases from {count_before} total cases")

    except Exception as e:
        logger.error(f"Error writing unique CSV {unique_csv_path}: {e}")

def dedup_json_cases(json_path):
    """Deduplicate redundant cases within a JSON file."""
    if not os.path.exists(json_path):
        logger.warning(f"JSON file not found: {json_path}")
        return
    
    try:
        dedup_records = []
        count_before = 0
        count_after = 0
        with open(json_path, 'r') as f:
            for line_num, jsonline in enumerate(f, 1):
                if not jsonline.strip():
                    continue
                
                try:
                    record = json.loads(jsonline)
                    cases = record.get("cases", [])
                    
                    # Deduplicate cases based on their content
                    unique_cases = {json.dumps(case) for case in cases}
                    dedup_cases = [json.loads(case) for case in unique_cases]
                    
                    # Update record with deduplicated cases
                    count_before += len(cases)
                    count_after += len(dedup_cases)
                    record["cases"] = dedup_cases
                    record["count"] = len(dedup_cases)
                    dedup_records.append(record)
                
                except json.JSONDecodeError as e:
                    logger.error(f"Error parsing JSON at line {line_num}: {e}")
                    continue
        
        # Overwrite the original JSON file with deduplicated records
        with open(json_path, 'w') as f:
            for record in dedup_records:
                f.write(json.dumps(record) + '\n')

        count_removed = count_before - count_after
        logger.info(f"\tDeduplicated JSON cases in {json_path}: before {count_before}, after {count_after}, removed {count_removed}")

    except Exception as e:
        logger.error(f"Error deduplicating JSON {json_path}: {e}")

def exclude_unreal_flag(flag_json, levels_json):
    """
    Compare cases in flag_json with corresponding level cases in levels_json.
    Remove cases from flag_json that are already in levels_json with the same key fields.
    If all cases are removed from an optimization entry, remove that entry.
    """
    if not os.path.exists(flag_json) or not os.path.exists(levels_json):
        logger.warning(f"Missing files for flag comparison: {os.path.basename(flag_json)} or {os.path.basename(levels_json)}")
        return
    
    logger.info(f"Comparing flag JSON with levels: {os.path.basename(flag_json)}")

    def make_key(item):  # fields to uniquely identify a case as function/file may vary
        return (item["line"], item["source"], item["char"], item["col"], item["type"])
    
    level_cases = defaultdict(set)
    try:
        with open(levels_json, 'r') as f:
            for jsonline in f:
                if not jsonline.strip():
                    continue
                record = json.loads(jsonline)
                opt_level = record.get("optimization")
                if not opt_level:
                    logger.warning(f"Skipping record without optimization: {record}")
                    continue
                for case in record.get("cases", []):
                    level_cases[opt_level].add(make_key(case))
    except Exception as e:
        logger.error(f"Error reading levels JSON {levels_json}: {e}")
        return
    
    # Process flag JSON and filter out redundant cases
    flag_records = []
    count_before = 0
    count_after = 0
    unreal_opt = []
    try:
        with open(flag_json, 'r') as f:
            for jsonline in f:
                if not jsonline.strip():
                    continue
                record = json.loads(jsonline)
                opt = record.get("optimization")
                opt_level = opt.split('-')[0]
                if not opt or not opt_level:
                    logger.warning(f"Skipping record without optimization: {record}")
                    continue
                cases = record.get("cases", [])
                # Filter out cases that already exist in levels
                real_cases = []
                for case in cases:
                    key = make_key(case)
                    if key not in level_cases[opt_level]:
                        real_cases.append(case)
                # If we still have cases after filtering, keep the record
                if real_cases:
                    record["cases"] = real_cases
                    record["count"] = len(real_cases)
                    flag_records.append(record)
                else:
                    unreal_opt.append(opt)
                count_before += len(cases)
                count_after += len(real_cases)
        
        # Rewrite the flag JSON with filtered records
        with open(flag_json, 'w') as f:
            for record in flag_records:
                f.write(json.dumps(record) + '\n')
        logger.info(f"\tExcluded {len(unreal_opt)} unreal flags: {unreal_opt}, removed {count_before - count_after} cases")

    except Exception as e:
        logger.error(f"Error filtering flag JSON {flag_json}: {e}")

def process_directory(input_dir):
    """Accept a directory containing result files and store filtered results in _filtered."""
    if not os.path.isdir(input_dir):
        logger.error(f"Input directory not found: {input_dir}")
        return
    
    # Copy input directory to output directory
    output_dir = input_dir.rstrip('/') + "_filtered"
    shutil.copytree(input_dir, output_dir, dirs_exist_ok=True)
    logger.info(f"Processing directory: {input_dir}")
    logger.info(f"Output directory: {output_dir}")
    
    # Find all JSON files
    json_files = glob.glob(os.path.join(output_dir, "*.json"))
    if not json_files:
        logger.warning(f"No JSON files found in {output_dir}")
        return
    logger.info(f"Found {len(json_files)} JSON files to process")
    
    logger.info("Step 1: Deduplicating redundant cases and apply src-based filter in all JSON files")
    for json_path in sorted(json_files):
        dedup_json_cases(json_path)
        apply_src_filter_to_json(json_path)
    for json_path in sorted(json_files):
        # filter mmem to keep only cases where cjump leakage exists
        filter_mmem_with_cjump_loc(json_path)
    
    logger.info("Step 2: Compare flag1/levels JSON files to exclude flag reporting same problems with just different function names")
    # group JSON file project_(flag1/levels)_arch.json and compare
    flag1_jsons = [f for f in json_files if 'flag1' in os.path.basename(f)]
    levels_jsons = [f.replace('flag1', 'levels') for f in flag1_jsons]
    for flag_json, level_json in zip(flag1_jsons, levels_jsons):
        exclude_unreal_flag(flag_json, level_json)
    
    logger.info("Step 3: Generating all CSV and unique CSV files from JSON")
    for json_path in sorted(json_files):
        # Generate CSV from filtered JSON
        csv_path = json_path.replace('.json', '.csv')
        json_to_csv(json_path, csv_path)
        # Generate unique CSV
        unique_csv_path = csv_path.replace('.csv', '_unique.csv')
        csv_to_unique_csv(csv_path, unique_csv_path)
    
    logger.info(f"Processing completed. Results saved to: {output_dir}")

def main():
    if len(sys.argv) != 2:
        logger.error("Usage: python filteres.py <input_directory>")
        logger.error("  Input directory should contain JSON result files")
        sys.exit(1)
    
    input_dir = sys.argv[1]
    process_directory(input_dir)

if __name__ == "__main__":
    main()
