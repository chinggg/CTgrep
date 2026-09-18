#!/usr/bin/env python3

import os
import json
import glob
import logging
import argparse
import subprocess
import csv
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional
from utils import construct_cflags, detect_arch_from_filename, get_arch_cflags, run_build_job  # Fix the import path


def setup_logging() -> str:
    """Setup logging configuration."""
    os.makedirs("rootcause_logs", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = f"rootcause_logs/rootcause_{timestamp}.log"
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
        handlers=[logging.FileHandler(log_file), logging.StreamHandler()]
    )
    return log_file

def run_analysis(config_file: str, functions: List[str], optimization: str, arch: str, output_dir: str) -> Optional[str]:
    """Run analysis for multiple functions with CT violations."""
    if not os.path.isfile(config_file):
        logging.error(f"Config file not found: {config_file}")
        return None
        
    # Join function names with commas
    function_list = ",".join(functions)
    
    proj_name = os.path.splitext(os.path.basename(config_file))[0]
    output_file = os.path.join(output_dir, f"{proj_name}_{arch}_{optimization}.json")
    
    if os.path.isfile(output_file):
        return output_file
        
    cmd = f"scripts/run_one.sh {config_file} {function_list}"
    cflags = construct_cflags(optimization, arch)
    env = {**os.environ}
    env["CFLAGS"] = cflags + " " + env.get("CFLAGS", "")
    
    logging.info(f"Running: CFLAGS=\"{env['CFLAGS']}\" {cmd}")
    
    # Run the build job
    retcode, stdout, stderr, duration = run_build_job(cmd, env, timeout=600)
    
    if retcode != 0:
        output_file += f".err{retcode}"
        
    # Save stderr (which contains the JSON output) to output file
    try:
        with open(output_file, 'w') as f:
            f.write(stderr)
    except OSError as e:
        logging.error(f"Failed to write output file {output_file}: {str(e)}")
        return None
    
    return output_file if retcode == 0 and os.path.isfile(output_file) and os.path.getsize(output_file) > 0 else None

def parse_jsonl_file(filepath: str) -> Dict[str, List[dict]]:
    """Parse JSONL file containing optimization results."""
    results = {}
    if not os.path.isfile(filepath):
        logging.error(f"Results file not found: {filepath}")
        return results
        
    try:
        with open(filepath, 'r') as f:
            for line in f:
                opt_record = json.loads(line)
                results[opt_record["optimization"]] = opt_record["cases"]
                
        logging.info(f"Parsed {filepath} - found {len(results)} optimizations")
    except Exception as e:
        logging.error(f"Error parsing {filepath}: {e}")
    return results

def get_result_files(proj_name: str, target_arch: Optional[str] = None, json_path: Optional[str] = None) -> Dict[str, List[str]]:
    """Get mapping of architectures to their result JSON files.
    
    Args:
        proj_name: Name of the project
        target_arch: If specified, only return files matching this architecture
        json_path: Path to either a single JSONL file or directory containing JSONL files
    
    Returns:
        Dict mapping architecture names to lists of JSON file paths
    """
    arch_files = defaultdict(list)
    
    if json_path:
        if os.path.isfile(json_path):
            # Single file case
            arch = detect_arch_from_filename(os.path.basename(json_path))
            if arch:
                arch_files[arch].append(json_path)
            return dict(arch_files)
        elif not os.path.isdir(json_path):
            logging.error(f"JSON path not found: {json_path}")
            return {}
            
        # Directory case - will use this path to look for JSON files
        search_dir = json_path
    else:
        # Default case - use project's res directory
        search_dir = os.path.join(proj_name, "res")
    
    # Find all JSON files in the directory
    pattern = "*.json" if json_path else f"{proj_name}_*.json"
    json_files = glob.glob(os.path.join(search_dir, pattern))
    
    if not json_files:
        logging.error(f"No result files found matching {os.path.join(search_dir, pattern)}")
        return {}
        
    # Group files by detected architecture
    for json_file in json_files:
        arch = detect_arch_from_filename(os.path.basename(json_file))
        if arch and (not target_arch or arch.upper() == target_arch.upper()):
            arch_files[arch].append(json_file)
                
    if target_arch and not arch_files:
        logging.warning(f"No result files found for architecture {target_arch}")
            
    return dict(arch_files)

def append_to_csv(proj_name: str, file_arch: str, opt_name: str, cases: List[dict], output_dir: str) -> None:
    """Append cases for a specific optimization to the CSV file.
    
    Args:
        proj_name: Name of the project
        file_arch: Architecture for these results
        opt_name: Name of the optimization level
        cases: List of case dictionaries to append
        output_dir: Directory to write the CSV file
    """
    csv_file = os.path.join(output_dir, f"{proj_name}_rootcause_{file_arch}.csv")
    
    # Define headers for CSV file
    headers = ["function", "file", "line", "col", "char", "source", "type", "optimization"]
    
    # Add pass-* headers for any potential pass info columns
    pass_headers = ["pass-cond", "pass-select", "pass-cjump", "pass-div", "pass-mdiv", "pass-mem", "pass-mmem"]
    headers.extend(pass_headers)
    
    # Check if file exists to determine if we need to write header
    write_header = not os.path.exists(csv_file)
    
    # Prepare rows to write
    rows = []
    for case in cases:
        # Basic case info
        row = {
            "function": case["function"],
            "file": case["file"],
            "line": case["line"],
            "col": case.get("col", ""),
            "char": case["char"],
            "source": case.get("source", ""),
            "type": case["type"],
            "optimization": opt_name
        }
        
        # Add pass info columns if they exist
        for pass_key in pass_headers:
            if pass_key in case:
                row[pass_key] = json.dumps(case[pass_key])
            else:
                row[pass_key] = ""
        
        rows.append(row)
    
    # Append to CSV file
    if rows:
        with open(csv_file, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=headers, delimiter='\t')
            if write_header:
                writer.writeheader()
                logging.info(f"Created new CSV file: {csv_file}")
            writer.writerows(rows)
        
        logging.info(f"Appended {len(rows)} rows to CSV: {csv_file}")

def save_rootcause_csv(proj_name: str, file_arch: str, enhanced_results: Dict[str, dict], output_dir: str) -> None:
    """Save enhanced results to CSV format, similar to analyzer.py's format.
    
    Args:
        proj_name: Name of the project
        file_arch: Architecture for these results
        enhanced_results: Dictionary of enhanced results with optimization info
        output_dir: Directory to write the CSV file
    """
    # Remove the existing CSV file if it exists
    csv_file = os.path.join(output_dir, f"{proj_name}_rootcause_{file_arch}.csv")
    if os.path.exists(csv_file):
        try:
            os.remove(csv_file)
            logging.info(f"Removed existing CSV file: {csv_file}")
        except OSError as e:
            logging.error(f"Error removing existing CSV file {csv_file}: {e}")
    
    # Process and append each optimization's results
    for opt_name, result in enhanced_results.items():
        append_to_csv(proj_name, file_arch, opt_name, result["cases"], output_dir)
    
    # Generate deduplicated CSV
    generate_unique_csv(proj_name, file_arch, "rootcause", output_dir)

def generate_unique_csv(proj_name: str, arch: str, result_type: str, res_dir: str) -> None:
    """Generate deduplicated CSV by merging optimization levels for same problems.
    
    Args:
        proj_name: Name of the project
        arch: Architecture name
        result_type: Type of results (e.g., 'rootcause')
        res_dir: Directory containing the CSV file
    """
    csv_path = os.path.join(res_dir, f"{proj_name}_{result_type}_{arch}.csv")
    unique_path = os.path.join(res_dir, f"{proj_name}_{result_type}_{arch}_unique.csv")
    
    if not os.path.exists(csv_path):
        logging.warning(f"CSV file not found for deduplication: {csv_path}")
        return
    
    logging.info(f"Generating deduplicated CSV: {unique_path}")
    
    # Group by everything except optimization level using tab delimiter
    problems = defaultdict(set)
    pass_columns = defaultdict(dict)
    
    try:
        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f, delimiter='\t')
            headers = reader.fieldnames
            
            # Extract pass info columns
            pass_headers = [h for h in headers if h.startswith('pass-')]
            
            for row in reader:
                # Create key for deduplication (everything except optimization)
                func = row['function']
                file = row['file']
                line = row['line']
                col = row['col']
                src = row['source']
                char = row['char']
                type_ = row['type']
                opt = row['optimization']
                
                key = (func, file, line, col, src, char, type_)
                problems[key].add(opt)
                
                # Store pass info for each unique problem
                # Collect all pass info across optimization levels
                if pass_headers:
                    if key not in pass_columns:
                        pass_columns[key] = defaultdict(set)
                    for h in pass_headers:
                        if h in row and row[h]:
                            pass_columns[key][h].add(row[h])
                
        # Write deduplicated CSV with merged optimization levels
        with open(unique_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=headers, delimiter='\t')
            writer.writeheader()
            
            for (func, file, line, col, src, char, type_), opts in problems.items():
                merged_opt = '|'.join(sorted(opts))
                row = {
                    'function': func,
                    'file': file,
                    'line': line,
                    'col': col,
                    'source': src,
                    'char': char,
                    'type': type_,
                    'optimization': merged_opt
                }
                
                # Add pass info columns if available
                key = (func, file, line, col, src, char, type_)
                if key in pass_columns:
                    for pass_key, pass_values in pass_columns[key].items():
                        if pass_values:
                            row[pass_key] = '|'.join(sorted(pass_values))
                
                writer.writerow(row)
        
        # Count unique problems
        problem_count = len(problems)
        logging.info(f"Found {problem_count} unique problems after deduplication")
        
    except Exception as e:
        logging.error(f"Error generating unique CSV: {e}")

def append_to_json(proj_name: str, file_arch: str, opt_name: str, cases: List[dict], output_dir: str) -> None:
    """Append optimization results to a JSONL file.
    
    Args:
        proj_name: Name of the project
        file_arch: Architecture for these results
        opt_name: Name of the optimization level
        cases: List of case dictionaries to append
        output_dir: Directory to write the JSONL file
    """
    output_file = os.path.join(output_dir, f"{proj_name}_rootcause_{file_arch}.json")
    
    # Create the record for this optimization
    opt_record = {
        "optimization": opt_name,
        "arch": file_arch,
        "count": len(cases),
        "cases": cases,
    }
    
    # Write this optimization's results to the JSONL file
    with open(output_file, 'a') as f_json:
        f_json.write(json.dumps(opt_record) + '\n')
    
    logging.info(f"Appended optimization '{opt_name}' with {len(cases)} cases to {output_file}")

def analyze_rootcause(proj_name: str, config_file: str, arch: Optional[str] = None, json_path: Optional[str] = None) -> None:
    """Analyze root causes of CT violations from JSONL results."""
    # Get files grouped by architecture
    arch_files = get_result_files(proj_name, arch, json_path)
    if not arch_files:
        return

    output_dir = os.path.join(proj_name, "rootcause")
    os.makedirs(output_dir, exist_ok=True)
    
    # Process files grouped by architecture
    for file_arch, json_files in arch_files.items():
        logging.info(f"Processing {len(json_files)} files for architecture {file_arch}")
        
        # Load and merge results from all files for this architecture
        all_results = {}
        for json_file in json_files:
            results = parse_jsonl_file(json_file)
            all_results.update(results)
            
        if not all_results:
            logging.warning(f"No valid results found for architecture {file_arch}")
            continue
            
        output_file = os.path.join(output_dir, f"{proj_name}_rootcause_{file_arch}.json")
        
        # Process each optimization using this architecture
        for optimization, cases in all_results.items():
            logging.info(f"Processing optimization: {optimization}")
            
            # Group cases by function
            func_cases = defaultdict(list)
            for case in cases:
                func_cases[case["function"]].append(case)
                
            # Run analysis once for all functions under this architecture
            functions = list(func_cases.keys())
            result_file = run_analysis(
                config_file,
                functions,
                optimization,
                file_arch,  # Use architecture for this group of files
                output_dir
            )
                
            if result_file and os.path.isfile(result_file):
                try:
                    with open(result_file, 'r') as f:
                        for line in f:
                            if not line.strip().startswith("{"):
                                continue
                            pass_info = json.loads(line)
                            if "CountInstr" not in pass_info["context"]:
                                function = pass_info.get("function")
                                if function and function in func_cases:
                                    for case in func_cases[function]:
                                        line = case["line"]
                                        char = case["char"]
                                        type = case["type"]
                                        
                                        # Define mapping from case types to their corresponding pass info fields
                                        type_mappings = {
                                            "cjump": [
                                                ("pass-cond", "added_cond_lines", "added_cond_chars"),
                                                ("pass-select", "added_select_lines", "added_select_chars"),
                                                ("pass-cjump", "added_cjump_lines", "added_cjump_chars")
                                            ],
                                            "mdiv": [
                                                ("pass-div", "added_div_lines", "added_div_chars"),
                                                ("pass-mdiv", "added_mdiv_lines", "added_mdiv_chars")
                                            ],
                                            "mmem": [
                                                ("pass-mem", "added_mem_lines", "added_mem_chars"),
                                                ("pass-mmem", "added_mmem_lines", "added_mmem_chars")
                                            ]
                                        }
                                        
                                        if type in type_mappings:
                                            for pass_key, lines_key, chars_key in type_mappings[type]:
                                                added_lines = pass_info.get(lines_key, [])
                                                added_chars = pass_info.get(chars_key, [])
                                                for added_line, added_char in zip(added_lines, added_chars):
                                                    if line == added_line and char == added_char:
                                                        case[pass_key] = pass_info["context"]
                                                        break  # Only break from the zip loop, continue checking other mappings
                except Exception as e:
                    logging.error(f"Error processing {result_file}: {e}")
            
            # Append to JSON and CSV files immediately after processing this optimization
            append_to_json(proj_name, file_arch, optimization, cases, output_dir)
            append_to_csv(proj_name, file_arch, optimization, cases, output_dir)
            
            logging.info(f"Saved results for optimization: {optimization}")
        
        # Generate deduplicated CSV after all optimizations are processed
        generate_unique_csv(proj_name, file_arch, "rootcause", output_dir)
        
        logging.info(f"Enhanced results with rootcause saved to {output_file}")

def main():
    parser = argparse.ArgumentParser(
        description="Localize root cause of constant-time violations in compiler passes"
    )
    parser.add_argument("config", help="Path to project config file")
    parser.add_argument("--json-path", help="Path to JSONL results file or directory")
    parser.add_argument("--arch", help="Target architecture to analyze (e.g. X8664, AArch64)")
    args = parser.parse_args()
    
    proj_name = os.path.splitext(os.path.basename(args.config))[0]
    log_file = setup_logging()
    logging.info(f"Starting root cause analysis for {proj_name}, logfile in {log_file}")
    
    analyze_rootcause(proj_name, args.config, args.arch, args.json_path)

if __name__ == "__main__":
    main()