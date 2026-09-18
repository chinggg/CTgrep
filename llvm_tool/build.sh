#!/bin/bash
# Build the two LLVM pass plugins against the clang/LLVM found via
# $LLVM_CONFIG (default: llvm-config on PATH). Must be rebuilt whenever the
# LLVM version changes; the plugin ABI is not stable across majors.
set -euo pipefail
cd "$(dirname "$0")"
LLVM_CONFIG=${LLVM_CONFIG:-llvm-config}
CXX=${CXX:-clang++}
CXXFLAGS="-g -O2 -fPIC -shared $($LLVM_CONFIG --cxxflags) $($LLVM_CONFIG --ldflags)"
echo "Building plugins with $CXX against LLVM $($LLVM_CONFIG --version)"
$CXX $CXXFLAGS IRCountInstr.cpp  -o IRCountInstr.so
$CXX $CXXFLAGS PassViolateCT.cpp -o PassViolateCT.so
ls -l IRCountInstr.so PassViolateCT.so
