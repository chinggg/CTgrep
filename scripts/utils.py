import json
import re
import os
import time
import signal
import logging
import subprocess
from typing import Tuple, Optional, Dict

# Define architecture-specific triplets
X8664_HOST = "x86_64-linux-gnu"
X8632_HOST = "i386-linux-gnu -m32 -march=i386"  # see https://godbolt.org/z/qM9KT31vz
I686_HOST = "i686-linux-gnu -m32 -march=i686"
AArch64_HOST = "aarch64-linux-gnu"
ARM_HOST = "arm-linux-gnueabihf"
RISCV_HOST = "riscv64-linux-gnu"
MIPS64_HOST = "mips64-linux-gnu"
MIPS32_HOST = "mips-linux-gnu"
MIPS32EL_HOST = "mipsel-linux-gnu"
NONE_HOST = " "  # do not specify -target

def get_arch_cflags(arch: str) -> str:
    """Get CFLAGS to compile on the given architecture."""
    host_triplets = {
        "X8664": X8664_HOST,
        "X8632": X8632_HOST,
        "I686": I686_HOST,
        "AARCH64": AArch64_HOST,
        "ARM": ARM_HOST,
        "RISCV": RISCV_HOST,
        "MIPS64": MIPS64_HOST,
        "MIPS32": MIPS32_HOST,
        "MIPS32EL": MIPS32EL_HOST,
        "NONE": NONE_HOST
    }
    host_triplet = host_triplets.get(arch.upper())
    if host_triplet is None:
        raise ValueError(f"Unknown architecture: {arch}")
    return "-target " + host_triplet

def detect_arch_from_filename(filename: str) -> Optional[str]:
    """Detect architecture from a filename by looking for known architecture identifiers."""
    known_archs = [
        "X8664", "X8632", "I686", "AARCH64", "ARM", 
        "RISCV", "MIPS32EL", "MIPS32", "MIPS64"
    ]
    
    filename_upper = filename.upper()
    
    for arch in known_archs:
        if arch in filename_upper:
            return arch
            
    if "X86_64" in filename_upper or "X86-64" in filename_upper:
        return "X8664"
    if "X86" in filename_upper and ("32" in filename or "386" in filename_upper):
        return "X8632"
    
    return None

def construct_cflags(optimization: str, arch: Optional[str] = None) -> str:
    """Construct CFLAGS string from optimization string.
    
    Args:
        optimization: String can be:
            - Just flags: "something" or "--something" or "-fsomething"
            - Opt level only: "O2"
            - Opt level with flag: "O2-fsomething" 
            - Multiple flags: "-flag1,--someflag2"
            - Opt level with multiple flags: "O2-flag1,-flag2,-flag3"
        arch: Optional target architecture (X8664, AArch64, etc.)
    
    Returns:
        CFLAGS string like "-target x86_64-linux-gnu -O2 -mllvm --something"
    """
    # Start with arch-specific flags if arch is provided
    result = [get_arch_cflags(arch)] if arch else []
    
    # First split by ',' to separate multiple flags
    parts = optimization.strip().split(',')
    
    # Handle first part specially - it may contain opt level
    first_part = parts[0]
    if first_part.startswith('O'):
        # Split on first '-' to separate opt level from flag
        opt_parts = first_part.split('-', 1)
        opt_level = opt_parts[0]
        result.append(f"-{opt_level}")
        if opt_level == "O0":
            result.append("-Xclang -disable-O0-optnone")
        # Add flag if present
        if len(opt_parts) > 1:
            flag = "-" + opt_parts[1]
            if flag.startswith('--'):
                result.append(f"-mllvm {flag}")
            else:
                result.append(flag)
    else:
        # First part is just a flag
        if first_part.startswith('--'):
            result.append(f"-mllvm {first_part}")
        else:
            result.append(first_part)
    
    # Handle remaining flags
    for flag in parts[1:]:
        if flag.startswith('--'):
            result.append(f"-mllvm {flag}")
        else:
            result.append(flag)
            
    return " ".join(result)

# return true if it contains "include/", "test" or ends with ".h"
def is_trivial(s: str):
    s = s.lower()
    trivial_keywords = [".h", "include/", "third_party", "third-party", "fuzz", "test", "helper"]
    trivial_keywords += ["benchmark", "example", "demo", "docs"]
    # project-specific trivial keywords manually found in results
    return any(keyword in s for keyword in trivial_keywords)

# check if C source has branch semantic, like if, switch, ==, !=, >, < &&, || etc.
def src_has_branch(s: str, col: Optional[int] = None):
    """Check if C source has branch semantic."""
    logic_ops = ["&&", "||"]
    branch_keywords = ["if (", "else {", "switch (", "for (", "while (", "do {"]
    # Use raw strings for regex patterns
    branch_regexes = [r"if\s*\(", r"else\s*\{", r"switch\s*\(", r"for\s*\(",
                     r"while\s*\(", r"\?.*\:"]
    if col is not None and col <= len(s):
        s2 = s[col-1:col+1].strip().replace("_", "")  # get substr at col and next char
        ch_prev = s[col-2:col-1].strip() if col > 1 else ""
        if s2 in logic_ops:
            return True
        s6 = s[col-1:col+5]
        if s6 == "return" or s6 == "throw ":
            return True
        if s[col-1:col+6] == "} catch":
            return True
        if any(keyword in s for keyword in branch_keywords) \
            or any(re.search(keyword, s) for keyword in branch_regexes):
            return True  # char not always reliable, so just be strict and assume branch
            # at branch keyword, end/beginning of loop body
            if s2.isalnum() or s2 in ['+)', '++'] or ch_prev == '(':
                return True
            # branch at } for do {} while 
            if s[col-1:col+6] == '} while':
                return True
        # Check for function/macro calls and see if col is within the match
        # \w+ is function/macro name, \S* can be any leading non-whitespace like -> *
        for match in re.finditer(r"\S*\w+\(", s):
            start, end = match.span()
            # Convert to 1-indexed and check if col is within the match
            if start + 1 <= col <= end:
                return True
    # false positive: flags like -fstack-protector-all can produce cjump on simple src like { or }
    if s.strip() in ["{", "}"]:
        return True
    return False

# Deprecated. no longer filter memop with src, but later filter to keep those same loc with potential cjump
def src_has_memop(s: str, col: Optional[int] = None):
    """Check if C source has memory operation semantic."""
    """assuming s is single char, return True if it's alphabet or =, otherwise False"""
    # col is 1-indexed, get substr at col and next char
    mem_chars = ['=', '*', '{', '}', '(', ')', '[', ']']
    if col is not None and col <= len(s):
        # col is 1-indexed, get substr at col and next char
        s2 = s[col-1:col+1].strip().replace("_", "").replace(",", "")  # underscore can be part of varname
        # varname, return or assignment/index/call
        if s2.isalnum() or any(c in s2 for c in mem_chars):
            return True
    # don't check if col is not provided
    return False

def src_valid(s: str):
# valid if s contains any alphanumeric character
    return any(c.isalnum() for c in s)

class CustomJSONEncoder(json.JSONEncoder):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.indentation_level = 0
        # Default to 2 spaces if indent is None
        self.indent :int = kwargs.get('indent', 2) or 2

    def encode(self, o):
        """Encode JSON object *o* with respect to single line lists."""

        if isinstance(o, (list, tuple)):
            if self._is_single_line_list(o):
                return "[" + ", ".join(json.dumps(el) for el in o) + "]"
            else:
                self.indentation_level += 1
                output = [self.indent_str + self.encode(el) for el in o]
                self.indentation_level -= 1
                return "[\n" + ",\n".join(output) + "\n" + self.indent_str + "]"

        elif isinstance(o, dict):
            self.indentation_level += 1
            output = [self.indent_str + f"{json.dumps(k)}: {self.encode(v)}" for k, v in o.items()]
            self.indentation_level -= 1
            return "{\n" + ",\n".join(output) + "\n" + self.indent_str + "}"

        else:
            return json.dumps(o)

    def _is_single_line_list(self, o):
        if isinstance(o, (list, tuple)):
            return not any(isinstance(el, (list, tuple, dict)) for el in o)\
                   and all(isinstance(el, (int, float, bool))  for el in o)\
                   and len(str(o)) <= 256

    @property
    def indent_str(self) -> str:
        # Now self.indent is guaranteed to be an integer
        return " " * (self.indentation_level * self.indent)
    
    def iterencode(self, o, **kwargs):
        """Required to also work with `json.dump`."""
        return self.encode(o)

def check_link_fail(s: str) -> Optional[str]:
    """Check if the string indicates a link failure, return matching keyword, otherwise None."""
    keywords = ["linker command failed", "link failed", "ld returned 1", "/usr/bin/ld: "]
    keywords += ["error: unable to rename temporary"]
    for keyword in keywords:
        if keyword in s:
            return keyword
    return None

def run_build_job(cmd: str, env: Optional[Dict[str, str]] = None, timeout: int = 300) -> Tuple[int, str, str, float]:
    """Run a build command with proper error handling and timeout.
    
    Args:
        cmd: Command to run
        env: Environment variables dictionary
        timeout: Timeout in seconds (default 5 minutes)
        
    Returns:
        Tuple of (return code, stdout, stderr, duration)
    """
    start_time = time.time()
    
    try:
        # Start process in new session so we can kill the whole group if needed
        process = subprocess.Popen(
            cmd,
            env=env or os.environ,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=True,
            start_new_session=True
        )
        
        try:
            # Wait for process with timeout
            stdout, stderr = process.communicate(timeout=timeout)
            retcode = process.returncode
            duration = time.time() - start_time
            
            if retcode != 0:
                # Check if it's a link failure that we should treat as success
                link_err = check_link_fail(stderr)
                if link_err:
                    logging.warning(f"Linker command failed with '{link_err}' after {duration:.2f}s, treating as success, faking retcode {retcode} -> 0")
                    retcode = 0
                else:
                    logging.error(f"Build failed with return code {retcode} after {duration:.2f}s")
            else:
                logging.info(f"Build completed successfully in {duration:.2f} seconds")
                
        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            logging.error(f"Build timed out after {duration:.2f} seconds")
            
            try:
                # Kill the entire process group
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                
                # Try to collect any output that was produced before timeout
                stdout, stderr = process.communicate(timeout=2)
            except Exception as e:
                logging.error(f"Error killing process group: {str(e)}")
                stdout = ""
                stderr = ""
            
            retcode = 124  # Standard timeout exit code
            
    except Exception as e:
        duration = time.time() - start_time
        logging.error(f"Exception running command: {str(e)}")
        stdout = ""
        stderr = str(e)
        retcode = 1
        
    return retcode, stdout.strip(), stderr.strip(), duration
