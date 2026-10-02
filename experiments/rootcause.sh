#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/common.sh"
require_plugins
input="results/badsnippets_clang${CLANG_MAJOR}_filtered"
if [[ ! -d "$input" || ! -d badsnippets ]]; then
    bash experiments/kick_tires.sh
fi
ARCHS=${ARCHS:-X8664}
# Check every requested input before starting any attribution.
for arch in $ARCHS; do
    [[ -s "$input/badsnippets_levels_${arch}.json" ]] \
        || die "missing input for $arch; run ARCHS=\"$ARCHS\" make kick-tires first"
done
for arch in $ARCHS; do
    python3 scripts/rootcause_localize.py configs/breakingbad/badsnippets.env \
        --json-path "$input" --arch "$arch"
done
mkdir -p results/rootcause_clang${CLANG_MAJOR}
cp -R badsnippets/rootcause/. results/rootcause_clang${CLANG_MAJOR}/
