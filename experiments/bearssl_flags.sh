#!/bin/bash
# Reproduction (scaled down): BearSSL under the paper's problematic concrete
# flags for this Clang version (tools/problematic_flags_clangNN.txt, the
# per-version slice of the 218-flag list), each flag on top of each
# optimization level. Set FLAGFILE to run a different list, e.g. the full
# flag space:
#   FLAGFILE=tools/fflags_combined_valid.txt MLLVM_FLAGFILE=tools/mllvmflags18_nouseless.txt \
#     bash experiments/bearssl_flags.sh
set -uo pipefail
source "$(dirname "$0")/common.sh"
require_plugins

ARCHS=${ARCHS:-$PAPER_ARCHS}
LEVELS=${LEVELS:-$PAPER_LEVELS}
DEFAULT_FLAGFILE=${FLAGFILE:-}
FLAGFILE=${FLAGFILE:-tools/problematic_flags_clang${CLANG_MAJOR}.txt}
MLLVM_FLAGFILE=${MLLVM_FLAGFILE:-}
NAME=${NAME:-bearssl_flags_clang${CLANG_MAJOR}}
EXPECTED=reproduce/data/01_all7libs_bearsslflags/res${CLANG_MAJOR}/res${CLANG_MAJOR}_bearssl_filtered
[[ -d "$EXPECTED" ]] || die "recorded BearSSL results not found: $EXPECTED"

[[ -f $FLAGFILE ]] || die "flag file not found: $FLAGFILE"
extra=(--flagfile "$FLAGFILE")
[[ -z "$DEFAULT_FLAGFILE" ]] && extra+=(--concrete-flags)
[[ -n $MLLVM_FLAGFILE ]] && extra+=(--flagfile-mllvm "$MLLVM_FLAGFILE")

run_campaign "$NAME" configs/bearssl.env "$ARCHS" "$LEVELS" "${extra[@]}" || exit $?

log "comparing with recorded results in $EXPECTED"
cat "$FLAGFILE" ${MLLVM_FLAGFILE:+"$MLLVM_FLAGFILE"} > "results/$NAME/tested_flags.txt"
python3 experiments/compare_unique.py "$EXPECTED" "results/${NAME}_filtered" \
    --levels "$LEVELS" --archs "$ARCHS" --mode all --flagfile "results/$NAME/tested_flags.txt"
