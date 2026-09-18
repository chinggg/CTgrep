#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/common.sh"
require_plugins
input="results/badsnippets_clang${CLANG_MAJOR}_filtered"
if [[ ! -d "$input" || ! -d badsnippets ]]; then
    bash experiments/kick_tires.sh
fi
python3 scripts/rootcause_localize.py configs/breakingbad/badsnippets.env \
    --json-path "$input" --arch X8664
mkdir -p results/rootcause_clang${CLANG_MAJOR}
cp -R badsnippets/rootcause/. results/rootcause_clang${CLANG_MAJOR}/
