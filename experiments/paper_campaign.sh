#!/bin/bash
# One compiler version per container; see AE.md Section 4.2.
set -euo pipefail
source "$(dirname "$0")/common.sh"
case "$CLANG_MAJOR" in 14|18|20) ;; *) die "expected patched Clang 14, 18 or 20" ;; esac
case "${1:-}" in
  phase1)
    libraries="bearssl mbedtls pqclean"
    extra=(--flagfile "$ARTIFACT_ROOT/tools/all_flags_clang${CLANG_MAJOR}.txt" --concrete-flags)
    ;;
  phase2)
    libraries="libgcrypt libsodium wolfssl openssl"
    extra=(--flagfile "$ARTIFACT_ROOT/tools/problematic_flags_clang${CLANG_MAJOR}.txt" --concrete-flags)
    ;;
  *) die "usage: bash experiments/paper_campaign.sh phase1|phase2" ;;
esac
require_plugins
for lib in $libraries; do
  run_campaign "${1}_${lib}_clang${CLANG_MAJOR}" "configs/$lib.env" \
    "${ARCHS:-$PAPER_ARCHS}" "${LEVELS:-$PAPER_LEVELS}" "${extra[@]}"
done
