# Shared helpers for the experiment scripts. Source, do not execute.
# All scripts run from the artifact root; results land in results/.

ARTIFACT_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ARTIFACT_ROOT"

CC=${CC:-clang}
export CC CXX=${CXX:-clang++}
CLANG_MAJOR=$($CC --version | sed -nE 's/.*clang version ([0-9]+).*/\1/p' | head -1)
[[ -n "$CLANG_MAJOR" ]] || { echo "error: cannot determine clang version from CC=$CC" >&2; exit 1; }

# Platforms evaluated in the paper (Sec. 5). X8632 and MIPS32 also work but
# are not part of the paper's tables.
PAPER_ARCHS="X8664 AArch64 ARM RISCV MIPS64 MIPS32EL"
PAPER_LEVELS="O0 O1 O2 O3 Os Oz"

log()  { printf '\n[%s] %s\n' "$(date +%H:%M:%S)" "$*"; }
die()  { echo "error: $*" >&2; exit 1; }

require_plugins() {
  [[ -f llvm_tool/IRCountInstr.so && -f llvm_tool/PassViolateCT.so ]] \
    || die "plugins missing; run 'make plugins' (needs the patched clang on PATH)"
  # the instrumentation flag only exists in the patched compiler
  echo 'int main(){return 0;}' > /tmp/ctgrep_probe.c
  $CC -c -O1 -mllvm --enable-mf-count-instr /tmp/ctgrep_probe.c -o /tmp/ctgrep_probe.o 2>/tmp/ctgrep_probe.err \
    || { cat /tmp/ctgrep_probe.err; die "CC=$CC is not the patched clang (no --enable-mf-count-instr)"; }
}

# Run scripts/run.py for several architectures concurrently. Each architecture
# gets its own working directory under work/<name>/<arch>/ with a private copy
# of the library source (builds are in-tree and would otherwise collide);
# result files are then collected into results/<name>/ and filtered.
#
#   run_campaign <name> <config.env> "<archs>" "<levels>" [extra run.py args...]
#
# Environment: PARALLEL_ARCHS (concurrent architectures, default: all listed),
# JOBS (make -j inside each build, default: nproc / PARALLEL_ARCHS).
run_campaign() {
  local name=$1 conf=$2 archs=$3 levels=$4; shift 4
  local extra=("$@")
  local proj; proj=$(basename "$conf" .env)
  local n_archs; n_archs=$(wc -w <<<"$archs")
  local parallel=${PARALLEL_ARCHS:-$n_archs}
  local ncpu; ncpu=$(nproc)
  export JOBS=${JOBS:-$(( ncpu / parallel > 0 ? ncpu / parallel : 1 ))}
  local resdir="res${CLANG_MAJOR}"

  # fetch library source once, then copy per architecture
  if [[ ! -d $proj ]]; then
    log "fetching $proj source"
    ( set +u; source "$conf"; pull_source ) || die "pull_source failed for $conf"
  fi

  log "campaign '$name': $proj, clang $CLANG_MAJOR, archs [$archs], levels [$levels]"
  log "$parallel architecture(s) in parallel, make -j$JOBS each, extra args: ${extra[*]:-none}"
  mkdir -p "work/$name" "results/$name/logs"

  run_one_arch() {
    local arch=$1 wd="work/$name/$1"
    mkdir -p "$wd"
    for d in scripts configs tools llvm_tool; do ln -sfn "$ARTIFACT_ROOT/$d" "$wd/$d"; done
    [[ -d "$wd/$proj" ]] || cp -r "$proj" "$wd/$proj"
    ( cd "$wd" && python3 scripts/run.py "$conf" --archs="$arch" --levels="$levels" \
        --resdir="$resdir" "${extra[@]}" ) > "results/$name/logs/$arch.log" 2>&1
    local rc=$?
    echo "  $arch finished (exit $rc), log: results/$name/logs/$arch.log"
    return $rc
  }
  export -f run_one_arch log
  export name conf proj levels resdir ARTIFACT_ROOT
  export EXTRA_ARGS="${extra[*]}"
  local failed=0
  printf '%s\n' $archs | xargs -P "$parallel" -I{} bash -c 'extra=($EXTRA_ARGS); run_one_arch {}' || failed=1

  log "collecting results into results/$name/"
  for arch in $archs; do
    cp "work/$name/$arch/$proj/$resdir"/* "results/$name/" 2>/dev/null || true
  done
  log "applying the paper's false-positive filter (scripts/filteres.py)"
  python3 scripts/filteres.py "results/$name" > "results/$name/logs/filteres.log" 2>&1 \
    || die "filteres.py failed, see results/$name/logs/filteres.log"
  echo "filtered results: results/${name}_filtered/"
  return $failed
}
