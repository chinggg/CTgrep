#!/bin/bash

# build target program with specific architectures and optimization pssed by with CFLAGS
# machine function pass will dump output to stderr, Python script is responsible for directing it to file for further processing
# JSON example:
# {"function": "br_i62_modpow_opt", "file": "bearssl-modpow_opt-x86i386.c", "context": "MFCountInstr", "select_count": 1, "select_lines": [35], "select_insts": ["  %28 = select i1 %24, i32 %27, i32 0, !dbg !81"], "select_srcs": ["            t2[v] |= mask & base[v];"], "cjump_count": 4, "cjump_lines": [30, 30, 34, 35], "cjump_insts": ["JCC_1 %bb.1, 6, implicit $eflags, debug-location !53; bearssl-modpow_opt-x86i386.c:30:5", "JCC_1 %bb.7, 5, implicit $eflags, debug-location !53; bearssl-modpow_opt-x86i386.c:30:5", "JCC_1 %bb.6, 4, implicit $eflags, debug-location !71; bearssl-modpow_opt-x86i386.c:34:9", "JCC_1 %bb.5, 5, implicit $eflags, debug-location !81; bearssl-modpow_opt-x86i386.c:35:27"], "cjump_srcs": ["    for (size_t u = 1; u < ((uint32_t)1 << k); u ++) {", "    for (size_t u = 1; u < ((uint32_t)1 << k); u ++) {", "        for (size_t v = 1; v < mwlen; v ++) {", "            t2[v] |= mask & base[v];"]}

# this script returns err code if build fails, but will do clean_build in any case
# set -e

conf=$1
func=$2
source $conf

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

export CC=${CC:-clang}
# export CC=/llvm-project/build_15/bin/clang
# see https://stackoverflow.com/questions/74543715/usr-bin-ld-cannot-find-lstdc-no-such-file-or-directory-on-running-flutte/74605488#74605488
# export CXX="clang++ --gcc-install-dir=/usr/lib/gcc/x86_64-linux-gnu/11"
export CXX=${CXX:-clang++}
# export CXX=/llvm-project/build_15/bin/clang++

# if $func is not specified by $2, we only dump every function's final cjump instructions
# JSON print instructions when emitting backend machine code
EXTRA_CFLAGS="-mllvm -enable-mf-count-instr"
EXTRA_CFLAGS+=" -fpass-plugin=$SCRIPT_DIR/../llvm_tool/IRCountInstr.so"
if [[ -n $func ]]; then  # dump more info when each pass changes IR of $func
  # built-in option to only print IR for matched function(s)
  EXTRA_CFLAGS+=" -mllvm -filter-print-funcs=$func"
  # built-in option to print changed IR in diff mode
  # EXTRA_CFLAGS+=" -mllvm -print-changed=diff-quiet"
  # custom option, JSON print instructions added/removed by each machine function pass
  EXTRA_CFLAGS+=" -mllvm -mfpass-dump"
  # custom pass plugin, JSON print instructions added/removed by each function pass
  EXTRA_CFLAGS+=" -fpass-plugin=$SCRIPT_DIR/../llvm_tool/PassViolateCT.so"
fi
# BASE_CFLAGS="-g -fno-inline $EXTRA_CFLAGS"
BASE_CFLAGS="-g $EXTRA_CFLAGS"

# if $SRC_DIR doesn't exist, call pull_source
[[ ! -d $SRC_DIR ]] && pull_source && [[ ! -d $SRC_DIR ]] && echo "Failed to pull source" && exit 1 || pushd $SRC_DIR

# parse triplet from passed $CFLAGS after -target
triplet=$(echo $CFLAGS | grep -oP '(?<=-target )\S+' || true)
# optflags+=" -mllvm -ir-dump-directory=irdump_$level -mllvm -print-changed=quiet"
export CFLAGS="$BASE_CFLAGS $CFLAGS"
export CXXFLAGS="$CFLAGS"
# export LDFLAGS="$CFLAGS"  # clang14 may complain "option: may only occur zero or one times!"

echo "Building $PROJ_NAME in $SRC_DIR with CC=$CC CXX=$CXX CFLAGS=$CFLAGS"
pre_build
build_target $triplet
build_status=$?
clean_build

popd

exit $build_status
