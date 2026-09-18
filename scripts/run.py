#!/usr/bin/env python3

import os
import subprocess
import argparse
import logging
import glob
import time
import signal
import sys
from datetime import datetime
from flag_manager import FlagManager
from analyzer import load_json_data, extract_problems, compare_data, save_results
from utils import construct_cflags, get_arch_cflags, run_build_job

logger = logging.getLogger(__name__)

def setup_logging(proj_name):
    """Setup logging to both console and file."""
    log_dir = os.path.join(proj_name, "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"run_{timestamp}.log")
    
    # Configure root logger - this is the key part that affects all modules
    root_logger = logging.getLogger()
    
    # Remove any existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Simple formatter using relative path
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Add handlers with formatter
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    root_logger.setLevel(logging.INFO)
    
    return log_file


def analyze_optimization(base_json, opt_json, opt_name, res_dir, proj_name, arch):
    """Analyze and save results comparing base and optimized builds."""
    opt_data = load_json_data(opt_json)
    
    if not opt_data:
        return
        
    # Determine result_type based on opt_json path
    if "data_flag1" in opt_json:
        result_type = "flag1"
    elif "data_flags" in opt_json:
        result_type = "flags"
    else:
        result_type = "levels"
        
    if base_json:
        # Flag mode: compare against base
        base_data = load_json_data(base_json)
        results = compare_data(base_data, opt_data)
    else:
        # Levels mode: extract problems directly using oracle
        results = extract_problems(opt_data)
        
    if results:
        logger.info(f"[{result_type}] Found {len(results)} problems introduced by {opt_name}. Saving data from {opt_json} to {res_dir}/ dir.")
        save_results(results, proj_name, arch, result_type, opt_name, res_dir)
        return len(results)

def get_build_filenames(proj_name, arch, level, flag_suffix="", error_code=None):
    """Generate consistent filenames for build outputs.
    Returns: (base_filename, buildlog_filename, json_filename)
    """
    base_filename = f"{proj_name}_{arch}_{level}{flag_suffix}"
    buildlog_filename = f"compiler_message_{base_filename}.txt"
    json_filename = f"llvm_message_{base_filename}.json"
    
    if error_code is not None:
        error_suffix = f".error{error_code}"
        buildlog_filename += error_suffix
        json_filename += error_suffix
        
    return base_filename, buildlog_filename, json_filename

def json_exists(json_path):
    """Check if json file exists and has valid content (more than 500 entries)."""
    if os.path.exists(json_path) and os.path.getsize(json_path) > 0:
        try:
            with open(json_path, 'r') as f:
                # if there are more than 100 occurrence of {"function" then just consider valid
                # there may be link error messages so it may not end with }
                data = f.read()
                entry_count = data.count('{"function": ')
                if entry_count >= 500:
                    return True
                else:
                    logger.warning(f"JSON file {json_path} has only {entry_count} < 500 entries")
                    # snippet may have less than 100 entries, but still valid if ends with }
                    if 'snippet' in json_path and data.endswith('}'):
                        return True
        except Exception as e:
            logger.error(f"Error reading file {json_path}: {str(e)}")
            return False
    return False

def run_and_save(config_file, cflags, data_dir, proj_name, arch, level, flag_suffix=""):
    """Run the script with given flags and save output to files"""
    try:
        cmd = f"scripts/run_one.sh {config_file}"
        env = {**os.environ}
        env["CFLAGS"] = cflags + " " + env.get("CFLAGS", "")
        timeout = int(env.get("BUILD_TIMEOUT", 300))
        
        logger.info(f"Running with {timeout=}: CFLAGS=\"{env['CFLAGS']}\" {cmd}")
        retcode, stdout, stderr, duration = run_build_job(cmd, env, timeout=timeout)
        build_log = stdout
        dumped_json = stderr
        
        # Create output filename and paths
        _, buildlog_filename, json_filename = get_build_filenames(
            proj_name, arch, level, flag_suffix, retcode if retcode != 0 else None)
        
        buildlog_path = os.path.join(data_dir, buildlog_filename)
        json_path = os.path.join(data_dir, json_filename)

        # Write output files with retry logic for disk space issues
        max_retries = 3
        retry_count = 0
        retry_wait = 300  # 5 minutes in seconds

        while retry_count <= max_retries:
            try:
                with open(buildlog_path, 'w') as f:
                    f.write(build_log)
                with open(json_path, 'w') as f:
                    f.write(dumped_json)
                break  # Success, exit the retry loop
            except OSError as e:
                logger.error(f"Failed to write output files: {str(e)}")

                if "No space left on device" in str(e):
                    retry_count += 1
                    if retry_count > max_retries:
                        logger.error(f"Maximum retries ({max_retries}) reached. Giving up.")
                        return retcode, build_log, dumped_json, None, duration

                    # Run clean_build to free up space
                    clean_cmd = f". {config_file}; cd $SRC_DIR; clean_build"
                    subprocess.run(clean_cmd, shell=True)
                    logger.warning(f"No space left, just clean build, will retry after {retry_wait}s (attempt {retry_count}/{max_retries})")
                    time.sleep(retry_wait)
                else:
                    raise

        # Get number of lines written
        lines_written = dumped_json.count('\n')
        logger.info(f"Output written to {json_path} ({lines_written} lines)")
        
        return retcode, build_log, dumped_json, json_path, duration

    except Exception as e:
        logger.error(f"Exception running run_one.sh with CFLAGS: {cflags}")
        logger.error(str(e))
        return -1, "", str(e), None, 0

def run_optimization_levels(proj_name, arch, levels, args):
    """Run and/or analyze base optimization levels."""
    data_dir = f"{proj_name}/data_levels"
    res_dir = os.path.join(proj_name, args.resdir)
    os.makedirs(data_dir, exist_ok=True)
    
    logger.info(f"[Levels] Processing optimization levels for {arch}")
    total_levels = len(levels)
    level_durations = []
    
    # Build each level if needed, starting with base level
    current = 1
    for level in levels:
        _, _, json_filename = get_build_filenames(proj_name, arch, level)
        json_path = os.path.join(data_dir, json_filename)
        
        if not args.analyze_only and not json_exists(json_path):
            logger.info(f"[Levels] Building level {level} ({current}/{total_levels})")
            cflags = construct_cflags(level, arch)
            ret = run_and_save(args.config, cflags, data_dir, proj_name, arch, level)
            if ret and ret[0] == 0:  # Only count successful builds
                _, _, _, _, duration = ret
                level_durations.append(duration)
            current += 1
        elif not args.analyze_only:
            logger.info(f"[Levels] Skipping level {level} ({current}/{total_levels}) - output already exists")
            current += 1
            
        # NOTE: now analyze all levels, including O0, no compare with base
        if os.path.exists(json_path):
            analyze_optimization(None, json_path, level, 
                                res_dir, proj_name, arch)
        else:
            logger.error(f"[Levels] JSON file not found: {json_path}")
            return 0, 0
    
    return len(level_durations), sum(level_durations)

def run_optimization_flag1(proj_name, arch, levels, flags, args):
    """Run and/or analyze individual optimization flag."""
    res_dir = os.path.join(proj_name, args.resdir)
    flag_durations = []

    for level in levels:
        data_dir = os.path.join(f"{proj_name}/data_flag1", f"data_{arch}_{level}")
        os.makedirs(data_dir, exist_ok=True)
        
        base_json = os.path.join(f"{proj_name}/data_levels", 
                               f"llvm_message_{proj_name}_{arch}_{level}.json")
        
        if not os.path.exists(base_json):
            logger.error(f"Base JSON file not found: {base_json}")
            continue
        
        # Get flags from existing files if in analyze-only mode
        if args.analyze_only:
            base_prefix = f"llvm_message_{proj_name}_{arch}_{level}"
            json_pattern = os.path.join(data_dir, f"{base_prefix}*.json")
            flag_files = glob.glob(json_pattern)
            # extract flag from filename by finding substr between base_prefix and .json
            # example: llvm_message_bearssl_X8664_O1--chr-bias-threshold=-1.5.json -> --chr-bias-threshold=-1.5
            flags = [os.path.basename(f).removeprefix(base_prefix).split('.json')[0] for f in flag_files]
        total_flags = len(flags)
        logger.info(f"[Flag1] Processing {total_flags} flags for {arch} at {level}")
        
        current = 1
        for flag in flags:
            # here it's just 1 flag so safely use it to construct filename
            _, buildlog_filename, json_filename = get_build_filenames(
                proj_name, arch, level, flag)
            buildlog_path = os.path.join(data_dir, buildlog_filename)
            json_path = os.path.join(data_dir, json_filename)
            
            if not args.analyze_only:
                # Only build if the output doesn't already exist and is valid
                if not json_exists(json_path):
                    logger.info(f"[Flag1] Building flag {flag} ({current}/{total_flags}) at {level}")
                    level_flag = f"-{level}" if level != "O0" else "-O0 -Xclang -disable-O0-optnone"
                    # cflags = f"{get_arch_cflags(arch)} {level_flag} {construct_cflags(flag)}"
                    cflags = construct_cflags(f"{level}{flag}", arch)
                    ret = run_and_save(args.config, cflags, data_dir, proj_name, arch, level, flag)
                    if ret and ret[0] == 0:  # Only count successful builds
                        _, _, _, _, duration = ret
                        flag_durations.append(duration)
                else:
                    logger.info(f"[Flag1] Skipping flag {flag} ({current}/{total_flags}) - output already exists")
                current += 1
                    
            if os.path.exists(json_path):
                analyzed = analyze_optimization(base_json, json_path, f"{level}{flag}",
                                  res_dir, proj_name, arch)
                if not analyzed:
                    logger.info(f"[Flag1] No problems found for {level}{flag} in {json_path}, removing build log and json")
                    try:
                        os.remove(buildlog_path)
                        os.remove(json_path)
                    except OSError as e:
                        logger.error(f"Error removing files {buildlog_path} or {json_path}: {str(e)}")
            else:
                logger.error(f"[Flag1] JSON file not found: {json_path}")
    
    return len(flag_durations), sum(flag_durations)

def main():
    parser = argparse.ArgumentParser(description="Run experiments with different CFLAGS.")
    parser.add_argument("config", help="Path to the configuration file.")
    parser.add_argument("--archs", default="X8664 X8632 AArch64 ARM RISCV MIPS64 MIPS32 MIPS32EL", help="Architectures to test (space-separated).")
    parser.add_argument("--levels", default="O0 O1 O2 O3 Ofast Os Oz", help="Optimization levels to test (space-separated).")
    parser.add_argument("--flagfile-mllvm", help="LLVM flags (-mllvm) to test specified in a file")
    parser.add_argument("--flagfile", help="Regular compiler flags to test specified in a file")
    parser.add_argument("--concrete-flags", action="store_true", help="Flag files already contain concrete values; do not expand boolean variants")
    parser.add_argument("--analyze-only", action="store_true", help="Only analyze existing JSON data without rebuilding")
    parser.add_argument("--resdir", default="res", help="Directory for storing results (relative to project dir)")
    args = parser.parse_args()

    config_file = args.config
    proj_name = os.path.basename(config_file).split('.')[0]
    
    # Setup logging before any operations - this needs to happen before importing other modules
    log_file = setup_logging(proj_name)
    logger.info(f"Logging to {log_file}")
    
    start_time = time.time()
    total_build_time = 0
    build_count = 0
    
    archs = args.archs.split()
    levels = args.levels.split()
    
    flag_manager = FlagManager(args.flagfile_mllvm, args.flagfile, concrete=args.concrete_flags)
    flag_manager.show_flag_info()
    
    for arch in archs:
        os.makedirs(os.path.join(proj_name, args.resdir), exist_ok=True)
        arch_start_time = time.time()
        arch_build_time = 0
        arch_build_count = 0
        
        # Run/analyze optimization levels once per arch
        if not args.analyze_only:
            builds, duration = run_optimization_levels(proj_name, arch, levels, args)
            total_build_time += duration
            arch_build_time += duration
            build_count += builds
            arch_build_count += builds
        else:
            run_optimization_levels(proj_name, arch, levels, args)
        
        # Run/analyze individual flags
        if not args.analyze_only:
            flags = flag_manager.get_arch_flags(arch)
            builds, duration = run_optimization_flag1(proj_name, arch, levels, flags, args)
            total_build_time += duration
            arch_build_time += duration
            build_count += builds
            arch_build_count += builds
        else:
            # Pass empty list for analyze-only mode, flags will be parsed from existing filenames
            run_optimization_flag1(proj_name, arch, levels, [], args)
        
        arch_total_time = time.time() - arch_start_time
        logger.info(f"Architecture {arch} completed:")
        logger.info(f"  Builds: {arch_build_count}")
        logger.info(f"  Build time: {arch_build_time:.2f}s")
        logger.info(f"  Total time: {arch_total_time:.2f}s")
    
    total_time = time.time() - start_time
    logger.info("Build Summary:")
    logger.info(f"Total builds: {build_count}")
    logger.info(f"Total build time: {total_build_time:.2f}s")
    logger.info(f"Total run time: {total_time:.2f}s")
    logger.info(f"Average build time: {(total_build_time/build_count if build_count else 0):.2f}s")

if __name__ == "__main__":
    main()
