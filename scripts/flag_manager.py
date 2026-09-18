import ast
import logging
from typing import Dict, List, Set, Tuple
from dataclasses import dataclass
from functools import cached_property

logger = logging.getLogger(__name__)
arch_keywords = {
    "x8664": "x86",
    "x8632": "x86",
    "i686": "x86",
    "aarch64": "aarch64",
    "arm": "arm",
    "riscv": "riscv",
    "mips64": "mips",
    "mips32": "mips",
    "mips32el": "mips"
}


@dataclass
class LLVMFlag:
    name: str
    type: str = "bool"  # "bool", "uint", "int", "long", "ulong", "number", "x", "N", "value", "fixed"
    prefix: str = ""  # For distinguishing between -mllvm and regular flags
    description: str = ""
    values: List = None  # For value type, store possible values or fixed values for fixed type
    
    def __post_init__(self):
        if self.values is None:
            self.values = []

class FlagManager:
    def __init__(self, mllvm_flag_file: str = None, flag_file: str = None, concrete: bool = False):
        """Initialize with flag file paths and parse raw flags."""
        self.flags: Dict[str, LLVMFlag] = {}
        self.concrete = concrete
        self._concrete_flags = []
        
        if mllvm_flag_file:
            self._parse_raw_flags(mllvm_flag_file, "-mllvm ")  # Backend flags need -mllvm prefix
            
        if flag_file:
            self._parse_raw_flags(flag_file, "")  # Frontend flags don't need prefix
            
    def _parse_raw_flags(self, flag_file: str, prefix: str):
        """Parse raw flags from file into LLVMFlag objects."""
        with open(flag_file) as f:
            for line in f:
                flag = line.strip()
                if not flag or flag.startswith('#'):
                    continue
                    
                if self.concrete:
                    self._concrete_flags.append(flag.split(maxsplit=1)[0])
                parts = flag.split(maxsplit=1)  # should split on whitespace including tab in case flagfile is tab-seperated csv
                flag_name = parts[0]  # Keep leading dash(es)
                flag_desc = parts[1] if len(parts) > 1 else ""

                if '=<' in flag_name:
                    base_flag = flag_name[:flag_name.find('=')]
                    type_str = flag_name[flag_name.find('<')+1:flag_name.find('>')]
                    self.flags[base_flag] = LLVMFlag(base_flag, type_str, prefix, flag_desc)
                elif '=' in flag_name:
                    base_flag, value = flag_name.split('=')
                    try:
                        value = float(value) if '.' in value else int(value)
                    except ValueError:
                        value = value  # Keep as string if not numeric
                    
                    if base_flag in self.flags:
                        self.flags[base_flag].values.append(value)
                    else:
                        self.flags[base_flag] = LLVMFlag(base_flag, "fixed", prefix, flag_desc, values=[value])
                else:
                    self.flags[flag_name] = LLVMFlag(flag_name, "bool", prefix, flag_desc)

    def _parse_value_options(self, flag_desc: str) -> List[str]:
        """Parse possible values from dictionary format after =<value>."""
        if "{'" not in flag_desc:
            return []
        try:
            dict_str = flag_desc[flag_desc.find("{"):flag_desc.rfind("}")+1]
            value_dict = ast.literal_eval(dict_str)
            return list(value_dict.keys())
        except:
            return []

    def _get_numeric_values(self, type_str: str) -> List[float]:
        """Get predefined values for numeric flag types."""
        # unsigned_ints = [0, 1, 2, 4, 16, 32, 64, 128, 256, 512, 1024]
        unsigned_ints = [0, 50, 100]
        # floats = [0.0, 0.1, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 4.0, 8.0]
        floats = [0.0, 0.5, 1.0]
        
        type_values = {
            "uint": unsigned_ints,
            "ulong": unsigned_ints,
            "int": unsigned_ints + [-1],
            "long": unsigned_ints + [-1],
            "number": floats + [-1.0],
            "x": floats + [-1.0],
            "N": unsigned_ints
        }
        return type_values.get(type_str, [])

    def get_flags_by_type(self, flag_type: str = None) -> List[LLVMFlag]:
        """Get flags filtered by type."""
        if flag_type is None:
            return list(self.flags.values())
        return [f for f in self.flags.values() if f.type == flag_type]

    def show_flag_info(self):
        """Display information about parsed flags and constructed real flags."""
        # Count raw flags by type
        type_counts = {}
        for flag in self.flags.values():
            type_counts[flag.type] = type_counts.get(flag.type, 0) + 1
            
        logger.info(f"Parsed {len(self.flags)} flags from files:")
        for ftype, count in sorted(type_counts.items()):
            logger.info(f"  {ftype}: {count} flags")
            
        # Count constructed real flags by type
        real_type_counts = {}
        for flag in self.real_flags:
            if '=' in flag:
                flag_name = flag[:flag.find('=')]
                flag_type = self.flags[flag_name].type
            else:
                flag_type = 'bool'
            real_type_counts[flag_type] = real_type_counts.get(flag_type, 0) + 1
            
        logger.info(f"\nConstructed {len(self.real_flags)} concrete flags:")
        for ftype, count in sorted(real_type_counts.items()):
            logger.info(f"  {ftype}: {count} variants")

    def get_arch_flags(self, arch: str) -> List[str]:
        """Get flags compatible with given architecture (case-insensitive)."""
        arch = arch.lower()  # Convert to lowercase to match arch_keywords keys
        if arch not in arch_keywords:
            raise ValueError(f"Unknown architecture: {arch}")
            
        keyword = arch_keywords[arch]
        all_keywords = set(arch_keywords.values())
        
        return [
            flag for flag in self.real_flags 
            if (not any(kw in flag.lower() for kw in all_keywords)) or  # arch-independent flags
               (keyword in flag.lower())  # arch-specific flags for target arch
        ]

    @cached_property 
    def real_flags(self) -> List[str]:
        """Return flags in compact form with original dashes but without prefixes."""
        if self.concrete:
            return list(dict.fromkeys(self._concrete_flags))
        result = []
        
        for flag in self.flags.values():
            if flag.type == "bool":
                result.append(flag.name)
                # NOTE: flags leading with --disable- or --enable- can additionally pass =false (eg. --disable-select-optimize=false)
                if not self.concrete and (flag.name.startswith("--disable-") or flag.name.startswith("--enable-")):
                    result.append(f"{flag.name}=false")
            elif flag.type == "fixed":
                result.extend(f"{flag.name}={val}" for val in flag.values)
            elif flag.type == "value":
                values = self._parse_value_options(flag.description)
                values = values or self._get_numeric_values("int")  # NOTE: -fflags=<value> don't have enum dict, just hardcode int
                result.extend(f"{flag.name}={val}" for val in values)
            elif flag.type in ("uint", "int", "long", "ulong", "number", "x", "N"):
                values = self._get_numeric_values(flag.type)
                result.extend(f"{flag.name}={val}" for val in values)
                
        return result


if __name__ == "__main__":
    # accept flag file and show flag info
    import argparse
    logger.setLevel(logging.INFO)
    logger.addHandler(logging.StreamHandler())
    parser = argparse.ArgumentParser(description="Parse LLVM flags and show information.")
    parser.add_argument("--flagfile-mllvm", type=str, help="Path to the LLVM -mllvm flag file.")
    parser.add_argument("--flagfile", type=str, help="Path to the regular flag file.")
    parser.add_argument("--archs", default="X8664 X8632 AArch64 ARM RISCV MIPS64 MIPS32 MIPS32EL", help="Architectures to test (space-separated).")
    parser.add_argument("--type", type=str, help="Type of flags to filter.")
    args = parser.parse_args()
    flag_manager = FlagManager(args.flagfile_mllvm, args.flagfile)
    flag_manager.show_flag_info()
    if args.archs:
        archs = args.archs.split()
        for arch in archs:
            arch_flags = flag_manager.get_arch_flags(arch)
            logger.info(f"{arch}: {len(arch_flags)} flags")

