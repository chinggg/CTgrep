#!/bin/bash
# Kick-the-tires: compile the 19 test cases of the paper's appendix
# "Ground Truth Validation Test Cases" under every optimization level and
# platform, and check that the recorded cjump locations for this Clang version
# are all found again.
set -uo pipefail
source "$(dirname "$0")/common.sh"
require_plugins

ARCHS=${ARCHS:-"X8664 X8632 AArch64 ARM RISCV MIPS64 MIPS32 MIPS32EL"}
LEVELS=${LEVELS:-"O0 O1 O2 O3 Ofast Os Oz"}
NAME=badsnippets_clang${CLANG_MAJOR}
EXPECTED=groundtruth/expected/clang${CLANG_MAJOR}

rm -rf "work/$NAME" "results/$NAME" "results/${NAME}_filtered"
run_campaign "$NAME" configs/breakingbad/badsnippets.env "$ARCHS" "$LEVELS"

[[ -d $EXPECTED ]] || die "no recorded results for clang $CLANG_MAJOR (have: $(ls groundtruth/expected))"
log "comparing with recorded results in $EXPECTED"
python3 experiments/compare_unique.py "$EXPECTED" "results/${NAME}_filtered" \
    --levels "$LEVELS" --archs "$ARCHS" --mode levels
