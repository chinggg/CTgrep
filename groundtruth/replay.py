#!/usr/bin/env python3
"""Compile a ground-truth snippet with its saved Compiler Explorer options."""

import argparse
import json
from pathlib import Path
import shlex
import subprocess


def main():
    root = Path(__file__).resolve().parent
    configs = json.loads((root / "compiler_configs.json").read_text())
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snippet", choices=[entry["snippet"] for entry in configs])
    parser.add_argument("--compiler", required=True, help="Path to the compiler listed in compiler_configs.json")
    parser.add_argument("--output", default="snippet.s", help="Assembly output path")
    parser.add_argument("--extra-flags", default="", help="Local toolchain or sysroot options")
    args = parser.parse_args()
    config = next(entry for entry in configs if entry["snippet"] == args.snippet)
    command = [args.compiler, "-x", config["language"], "-S"]
    command += shlex.split(config["target_options"])
    command += shlex.split(config["options"])
    command += shlex.split(args.extra_flags)
    command += [str(root / "snippets" / args.snippet), "-o", args.output]
    print(f"Original compiler: {config['compiler_name']}", flush=True)
    print(shlex.join(command), flush=True)
    subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
