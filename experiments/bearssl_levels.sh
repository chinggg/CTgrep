#!/bin/bash
# Functional check: BearSSL under the six optimization levels on the six
# paper platforms (no individual flags). Compares with the recorded
# results for this Clang version.
set -uo pipefail
source "$(dirname "$0")/common.sh"
require_plugins

ARCHS=${ARCHS:-$PAPER_ARCHS}
LEVELS=${LEVELS:-$PAPER_LEVELS}
NAME=bearssl_levels_clang${CLANG_MAJOR}
EXPECTED=reproduce/data/01_all7libs_bearsslflags/res${CLANG_MAJOR}/res${CLANG_MAJOR}_bearssl_filtered
[[ -d "$EXPECTED" ]] || die "recorded BearSSL results not found: $EXPECTED"

run_campaign "$NAME" configs/bearssl.env "$ARCHS" "$LEVELS" || exit $?

log "comparing with recorded results in $EXPECTED"
python3 experiments/compare_unique.py "$EXPECTED" "results/${NAME}_filtered" \
    --levels "$LEVELS" --archs "$ARCHS" --mode levels
