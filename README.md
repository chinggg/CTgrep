# CTgrep

CTgrep finds constant-time violations that Clang/LLVM introduces while
optimizing cryptographic code. It compiles a program once per compiler
configuration with an instrumented Clang and reports potential
compiler-induced control-flow and data-flow violations. The paper focuses
on conditional branches and on conditional memory accesses at source
locations that also exhibit a branch under another compiler configuration.

This repository is the artifact of the following paper. Artifact evaluators
should start with [AE.md](AE.md).

```bibtex
@inproceedings{SP27-ctgrep,
  author       = {Liu, Jing and Gavier, Luc{\'i}a Martinez and Zhang, Zhiyuan and B{\"o}hme, Marcel and Barthe, Gilles},
  title        = {Analyzing Compiler-induced Constant-time Violations with Compiler at Scale},
  year         = {2027},
  booktitle    = {IEEE Symposium on Security and Privacy},
  series       = {IEEE S\&P'27},
}
```

The code has two parts. The **differential analysis** is the technique of
the paper: a patched compiler plus two pass plugins that observe a single
compilation, and an analyzer that applies the constant-time oracles to what
they observed. The **experiment infrastructure** applies that analysis to
whole libraries across compiler flags, Clang versions and target platforms,
filters the results, and produces the paper's figures and tables. The first
part is what you need to analyze one program; the second is what you need
to repeat or extend the study.

Requirements: a Clang/LLVM development environment (the patched compiler,
its headers and `llvm-config`, see the Dockerfile for the exact build) and
Python 3.10. Analyzing platforms other than the host needs the matching
cross toolchain, on Ubuntu the `crossbuild-essential-*` packages. The
Dockerfile assembles all of this; `make image` builds it.

Use the prebuilt image to get started without compiling LLVM:

```sh
make pull-image  # docker pull ghcr.io/chinggg/ctgrep:clang18 && docker tag ghcr.io/chinggg/ctgrep:clang18 ctgrep:clang18
make shell  # mkdir -p results work && docker run --rm -it -v "$PWD/results:/ctgrep/results" -v "$PWD/work:/ctgrep/work" ctgrep:clang18
```

`make pull-image` downloads `ghcr.io/chinggg/ctgrep:clang18` and tags it locally
as `ctgrep:clang18`. Use `LLVM_VERSION=14` or `LLVM_VERSION=20` for those versions. `GHCR_IMAGE` can also specify a release tag or an image digest.

## Part 1: differential analysis of one compilation

```
source ─► Clang ─► LLVM IR ─► middle-end passes ─► back-end passes ─► machine code
                     │                                    │
          IRCountInstr.so                  MachineFunctionCountInstr
          (pass plugin, runs before         (added to LLVM, runs right
           any optimization)                 before code emission)
                     └───────────────┬────────────────────┘
                              scripts/analyzer.py
                     oracles per (function, source file)
```

A compilation with the flags

```
-g -mllvm --enable-mf-count-instr -fpass-plugin=llvm_tool/IRCountInstr.so
```

prints two JSON records per function to stderr. The IR record, produced by
the `IRCountInstr` plugin at the start of the pass pipeline, lists the
source lines of conditional branches, selects and memory accesses in the
unoptimized IR. The MIR record, produced by `MachineFunctionCountInstr` in
the patched LLVM just before code emission, lists the conditional jumps,
division instructions, conditional moves and memory accesses in the final
machine code. Every instruction carries the `file:line:column` of its debug
location, which is how the two records are related to each other and to the
source.

`scripts/analyzer.py` joins the records of each function. The paper uses
the following two detection types:

| Type | Reported when |
| --- | --- |
| `cjump` | a conditional jump in the machine code is on a source line that has no conditional branch anywhere in the unoptimized IR of the same file (the whole file is used so that inlined code is matched against its own origin) |
| `mmem` | the back-end reports a potential dependence between a conditional move and a memory access, and they share a source line and column |

The `mmem` analysis uses a relaxed operand check on ARM/MIPS; the filter
retains a finding only where a `cjump` is also detected under another
compiler configuration. The analyzer additionally records hardware division
instructions as `mdiv`, an auxiliary diagnostic outside the paper's scope.
The short AE comparisons report `cjump` only; other types can be inspected
explicitly with `experiments/compare_unique.py --types "cjump mmem mdiv"`.

Every report names the function, the source location, the source text, the
character under the column and the type. A report from a build at some
optimization level is a violation introduced by that level; a report from a
build with an additional flag is compared with the report of the level-only
build, so that a flag is only blamed for what it adds.

`scripts/rootcause_localize.py` answers which pass is responsible: it
recompiles an affected function with `-mllvm --mfpass-dump` and the second
plugin, `PassViolateCT.so`, which together print the instructions each
middle-end and back-end pass adds or removes, and records the first pass
that introduces the offending instruction.

Files of this part:

```
llvm_tool/IRCountInstr.cpp     IR recorder (new pass manager plugin)
llvm_tool/PassViolateCT.cpp    per-pass instruction diff for root cause localization
llvm_tool/build.sh             compiles both plugins against llvm-config
scripts/analyzer.py            oracles and differential comparison
scripts/rootcause_localize.py  pass attribution
scripts/utils.py               target triples, CFLAGS construction, source heuristics
```

The patched compiler adds `MachineFunctionCountInstr` and the hooks for
`--mfpass-dump` (~1k LOC, available as self-contained patches in
`patches/ct-backend-<major>.patch` applied onto upstream LLVM `release/<major>.x`,
or via branch `ct-backend-<major>` of `github.com/chinggg/llvm-project` for LLVM
14, 18 and 20). Machine function passes have no plugin interface in these LLVM
versions, which is why this backend part cannot be an out-of-tree plugin. The
classification of machine instructions uses generic properties for branches
and memory accesses, the generic division opcodes plus target opcode names for
divisions, and a per-target table of conditional-move opcode names (`cmov*` on
x86, `csel`/`csinc`/`csinv`/`csneg` on AArch64, `movn`/`movz` on MIPS, `movcc`
on ARM).

## Part 2: experiment infrastructure

The study applies the analysis to seven libraries, three Clang versions,
six platforms, six optimization levels and about 4,000 concrete compiler
flags. This part turns one compilation into that matrix.

```
configs/<lib>.env        how to fetch and build each library with our CC/CFLAGS
tools/*.txt              the flag lists (search space and problematic flags)
scripts/flag_manager.py  expands raw flags into concrete flags, per platform
scripts/run.py           driver: levels and flags × platforms for one library
scripts/run_one.sh       one build: sets CC and CFLAGS, calls the profile's hooks
scripts/filteres.py      false-positive filter and CSV export
experiments/             evaluator-facing runs with comparison against recorded results
reproduce/               figures and tables of the paper from the recorded results
groundtruth/             the 19 ground-truth test cases and their recorded results
reproduce/data/          recorded library results, also used by the run comparisons
```

**Library profiles.** `configs/<name>.env` is a shell file with the source
location, a pinned commit, and four functions: `pull_source`, `pre_build`,
`build_target` and `clean_build`. `run_one.sh` sources the profile, exports
`CC`, `CXX` and `CFLAGS`, and calls the hooks; the profile's job is to make
the library's build system use those variables and not add its own
optimization level. The compiler's stderr, which carries the JSON records,
is captured by `run.py` and stored next to the build log.

**Driver.** `run.py <profile>` builds the library under every optimization
level for every platform (`--archs`, `--levels`) and, when a flag list is
given (`--flagfile` for Clang flags, `--flagfile-mllvm` for LLVM flags),
every concrete flag on top of every level. Results go to
`<lib>/<resdir>/<lib>_<levels|flag1>_<arch>.json`, one line per
configuration. A build whose output already exists is skipped, so an
interrupted run resumes, and in flag mode the raw output of builds without
new violations is deleted to bound disk use. `BUILD_TIMEOUT` bounds one
build in seconds and `JOBS` is the `make -j` value inside a build.

```sh
make plugins
python3 scripts/run.py configs/bearssl.env --archs="X8664" --levels="O0 O1 O2 O3 Os Oz"
python3 scripts/filteres.py bearssl/res            # writes bearssl/res_filtered/
```

**Flags.** Use `tools/all_flags_clang<version>.txt` for all flags or
`tools/problematic_flags_clang<version>.txt` for problematic flags, where
`<version>` is `14`, `18`, or `20`. Both are ready-to-run lists: pass
`--flagfile=<file> --concrete-flags` to `scripts/run.py`.
The complete 218-flag union is `tools/problematic_flags_all.txt`.
[AE.md Section 4.2](AE.md#42-rerun-the-full-two-phase-library-study) gives the run commands.

**Filtering.** Reports are complete by design and filtered once, by
`filteres.py`: source heuristics remove branches that exist in the source
(`if`, loops, `&&`, `||`, calls), `mmem` reports are kept only where a
`cjump` report exists at the same location, and a flag whose cases are
identical to the level-only cases is dropped. The output is a tab-separated
`.csv` with one row per case and a `_unique.csv` with one row per location
whose `optimization` column lists all triggering configurations. The
paper's numbers are computed from the `_unique.csv` files; `reproduce/`
does that computation and `experiments/compare_unique.py` compares fresh
tables with recorded ones.

**Running many platforms.** Builds are in-tree, so two platforms cannot
share one checkout. `run_campaign` in `experiments/common.sh` copies the
checkout per platform under `work/`, runs the platforms concurrently, and
merges and filters the results; the `experiments/*.sh` scripts wrap it.

**Data formats.** A raw record looks like

```json
{"function": "br_i31_muladd_small", "file": "...", "context": "MFCountInstr",
 "cjump_count": 2, "cjump_lines": [53, 53], "cjump_cols": [2, 2], "cjump_insts": [...], "cjump_srcs": [...], ...}
```

and an analyzer result line like

```json
{"optimization": "O2", "count": 1, "cases": [
  {"function": "br_i15_muladd_small", "file": "src/int/i15_muladd.c", "line": 44, "col": 15,
   "source": "  x -= (-ctl) & d;", "char": "&", "type": "cjump", "arch": "X8664"}]}
```

where `optimization` is `O2` for a level, `O2--fast-isel` for an LLVM flag
on top of `-O2`, and `O2-fvectorize` for a Clang flag.

## Reusability and Extensibility

The core methodology of CTgrep—**differential analysis between unoptimized
intermediate representations and machine code**—is fundamentally compiler-agnostic.
It requires only two primitive capabilities:
1. Recording control/memory semantics in an unoptimized early representation.
2. Intercepting final instructions immediately before machine code emission.

### Architectural Rationale: Middle-end vs. Backend Inspection

In CTgrep, middle-end inspection is implemented as a standard dynamic pass plugin
(`llvm_tool/IRCountInstr.cpp`) via Clang's `-fpass-plugin`. However, backend
machine-function tracking requires patching LLVM directly (adding ~988 LOC across
LLVM 14, 18, and 20).

This is due to an architectural constraint in LLVM's current CodeGen pipeline: while
the middle-end IR pipeline transitioned to the New Pass Manager (NPM), the backend
(`MachineFunctionPass` / MIR) largely remains on the legacy pass manager
(`TargetPassConfig`). As documented in LLVM community RFCs, a standardized dynamic
plugin infrastructure for CodeGen is planned around the ongoing `MachinePassManager`
migration. Once CodeGen NPM plugin interfaces mature in future LLVM releases,
CTgrep's backend tracking could conceptually decouple into an out-of-tree plugin.
Similarly, exploring whether this differential approach can be adapted to other
compiler frameworks (such as GCC, via its GIMPLE and RTL pass hooks) is a promising
direction for future research.

### 1. Adding a new cryptographic library

CTgrep analyzes arbitrary C codebases without source modifications. Adding a library
only requires a configuration profile (`configs/<name>.env`) defining its fetch,
build, and clean hooks:

```sh
PROJ_NAME=Foo
SRC_DIR=${PROJ_NAME,,}
URL_GIT=https://github.com/example/foo
COMMIT=abcdef0
pull_source() { git clone $URL_GIT $SRC_DIR && (cd $SRC_DIR && git checkout $COMMIT); }
pre_build()   { sed -i '/^CFLAGS *=/d' Makefile; clean_build; }    # runs inside SRC_DIR
build_target(){ make -j${JOBS:-$(nproc)} --output-sync lib; }       # $1 is the target triple, or empty
clean_build() { make clean; }
```

The build must take `CC`, `CXX` and `CFLAGS` from the environment without adding
an optimization level of its own; `configs/pqclean.env` shows how to strip them
from Makefiles. Build only the library, not tests or benchmarks. `clean_build`
runs after every build, including failed ones. Try one platform first and check
that the JSON output has thousands of records; fewer than 500 is treated as a
failed build by `run.py`. If the library uses idioms that the source heuristics
misclassify, extend `utils.src_has_branch` or the exclusion lists in
`reproduce/scripts/filtering.py`; the oracles themselves should not change.

**CI/CD Regression Testing**: Because CTgrep inspects code directly
during compilation with negligible overhead over a standard build, it is naturally
suited for continuous integration. A CI pipeline could run CTgrep on each incoming
pull request and diff the reported violation locations against the main branch
baseline, automatically flagging potential compiler-induced constant-time
violations (such as unexpected branches or variable-latency instructions
on candidate sensitive paths) newly introduced before code is merged.

### 2. Porting to new compiler releases

Porting CTgrep across compiler major versions (demonstrated on Clang 14, 18, and 20)
is straightforward because the changes are confined to compiler API maintenance:
1. Rebase the backend patch onto the new release tag (handling routine LLVM header
   relocations and API renames like `StringRef::starts_with`). Export the diff to
   `patches/ct-backend-NN.patch` (or alternatively, point `LLVM_REPO` and `LLVM_BRANCH`
   to your custom remote branch).
2. Build the image with `make image LLVM_VERSION=NN` and compile plugins with
   `make plugins`. The plugins use the new-pass-manager plugin API; a compile
   error there is the first sign of an API change.
3. Extract candidate optimization flags from the new compiler: frontend flags via
   `clang-NN --help-hidden` (passed via `--flagfile`) and backend flags via
   `llc-NN --help-list-hidden` (passed via `--flagfile-mllvm`, e.g. saved to
   `tools/mllvmflagsNN_nouseless.txt`), filtering out unrelated options with
   keywords (see `BLOCK_FLAG_KWDS` in `tools/flagcounts.py`).
4. Run CTgrep on `groundtruth/snippets/` to generate detection results for the
   new compiler, inspect and verify the outputs, and store them as the baseline in
   `groundtruth/expected/clangNN/`. Future regression checks can then be run via `make kick-tires`.

### 3. Supporting new target architectures

The differential backend framework supports cross-compilation out of the box.
Adding an architecture requires:
1. Registering the target triple in `utils.get_arch_cflags` and platform detection
   in `detect_arch_from_filename`.
2. Adding the matching `crossbuild-essential-*` package and LLVM target back-end
   to the Dockerfile.
3. Adding the architecture's conditional-move instruction mnemonics to the
   instruction classification table in `MachineFunctionCountInstr`.
4. Mapping target-specific flag families in `flag_manager.arch_keywords`.

### 4. Standalone and custom flag exploration

The experiment driver can be invoked directly outside preset benchmarks to test
arbitrary flag sets on any configured library:

```sh
python3 scripts/run.py configs/bearssl.env \
    --flagfile=tools/all_flags_clang18.txt --concrete-flags \
    --archs="X8664 AArch64 ARM RISCV MIPS64 MIPS32EL" \
    --levels="O0 O1 O2 O3 Os Oz" --resdir=allflags_clang18
python3 scripts/filteres.py bearssl/allflags_clang18
```

To use problematic flags, select `tools/problematic_flags_clang18.txt` instead
and give the run a different `--resdir`. Change the profile to select a library.
