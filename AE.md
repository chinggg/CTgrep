# Artifact Evaluation

This document accompanies the paper *CTgrep: Analyzing Compiler-induced
Constant-time Violations with Compiler at Scale* (IEEE S&P 2027). We apply
for the Available, Functional and Reproduced badges.

The artifact runs inside a Docker image that contains our patched Clang/LLVM,
the cross toolchains for the six target platforms, and the analysis
pipeline. We recommend an x86-64 machine running Ubuntu or Debian with
Docker, especially for the full experiment campaigns. The main workflow
also supports local evaluation on macOS using Docker.

Steps 1–3 of this guide are the main evaluation workflow: set up the container, run
CTgrep on test programs and BearSSL, and reproduce the paper's figures and
tables from the recorded experimental results with `make reproduce`.
[Step 4](#4-rerun-experiments-optional) contains optional experiment reruns, which are not required to reproduce the paper's figures and tables from the recorded experimental results.

| Stage | Commands | Expected Time | Expected Disk Usage |
| --- | --- | --- | --- |
| Download image | `make pull-image` | depends on connection speed | a few GB |
| Build image (optional) | `make image` | tens of minutes (LLVM compilation) | tens of GB during the build, a few GB afterwards |
| Kick the tires | `make kick-tires` | seconds | negligible |
| Functional | `make bearssl-levels`, `make rootcause` | about a minute | well under 1 GB |
| Reproduce figures/tables | `make reproduce` | seconds | negligible |
| BearSSL flag sweep (optional) | `make bearssl-flags` | hours | around 10 GB |
| Full study (optional) | `make phase1`, `make phase2` | days to weeks | depends on library and parallelism |

The short stages were measured on a MacBook M5 Pro; the two long runs are
extrapolated from the measured time of one build and depend heavily on the
core count.

## Evaluation overview

| Task | Paper | AE guide |
| --- | --- | --- |
| Run the ground-truth tests | Paper §4.5 and Appendix "Ground Truth Validation Test Cases" | [Step 2.1](#21-run-the-ground-truth-tests) — `make kick-tires` |
| Run BearSSL across optimization levels | Paper §4 detection workflow and §6 library analysis | [Step 2.2](#22-run-bearssl-across-optimization-levels) — `make bearssl-levels` |
| Locate the responsible compiler passes | Paper §4.4 and Table 4 | [Step 2.3](#23-locate-the-responsible-compiler-passes) — `make rootcause` |
| Reproduce figures and tables from the recorded experimental results | Paper §§6 and 8 (Figures 4, 6–8), appendix figures, and Tables 2–3 | [Step 3](#3-reproduce-paper-figures-and-tables-from-the-recorded-experimental-results) — `make reproduce` |
| Rerun BearSSL with problematic flags (optional) | Paper §6: BearSSL flag experiments | [Step 4.1](#41-rerun-bearssl-with-problematic-flags) — `make bearssl-flags` |
| Run the full-scale experiments (optional) | Paper §5 experiment setup and §6 library results | [Step 4.2](#42-rerun-the-full-two-phase-library-study) — `make phase1`, `make phase2` |

The paper's Table 1 (ClangOver configurations) and Table 4 (problematic passes) have no
generating script. Table 1 summarizes configuration experiments; Table 4
was compiled by hand from root-cause outputs.

## 1 Set up the evaluation environment

### 1.1 Get the Docker image

Extract the artifact archive and enter its top-level directory (containing
`Makefile`). Alternatively, clone the repository:

```sh
git clone --branch artifact https://github.com/chinggg/CTgrep.git ctgrep
cd ctgrep
```

Download the prebuilt image:

```sh
make pull-image  # docker pull ghcr.io/chinggg/ctgrep:clang18 && docker tag ghcr.io/chinggg/ctgrep:clang18 ctgrep:clang18
```

The image includes the patched compiler, cross toolchains, plugins and artifact
sources. Clang 18 is sufficient for this guide; add `LLVM_VERSION=14` or
`LLVM_VERSION=20` to the Make commands to use another version.

**Optional: build the image from source.** Skip this if you pulled the prebuilt image.

```sh
make image  # docker build -t ctgrep:clang18 .
```

### 1.2 Enter the Docker container

```sh
make shell  # mkdir -p results work && docker run --rm -it -v "$PWD/results:/ctgrep/results" -v "$PWD/work:/ctgrep/work" ctgrep:clang18
```

The working directory is `/ctgrep`. The two `-v` options bind-mount the host's
`results/` and `work/` directories there, preserving results and build caches.
Use a local filesystem for these directories: NFS `root_squash` can prevent
writes from the container, which runs as root.

Run the following evaluation steps inside the container. Each step has one
Make command; it runs the underlying scripts and builds plugins as needed.
The script examples in README.md explain implementation and customization;
they are not additional evaluation steps.

## 2 Run CTgrep

### 2.1 Run the ground-truth tests

```sh
make kick-tires
```

The 19 programs in `groundtruth/snippets/` are the test cases listed in
the appendix "Ground Truth Validation Test Cases" of the paper: small functions from BearSSL, Botan, HACL\*, wolfSSL and the examples of
Daniel et al., Lai et al. and Zhang and Barthe, each of which prior work
showed to be compiled into a secret-dependent branch or memory access. The
file names carry the library, the function and the platform of the original
report. The command compiles all of them under seven optimization levels
for eight platforms, applies the oracles and the false-positive filter, and
compares the `cjump` locations with the run we recorded for the same Clang version.
It takes seconds and ends with

```
file                                         recorded reproduced    new
badsnippets_levels_AArch64_unique.csv               7          7      0
badsnippets_levels_ARM_unique.csv                   6          6      0
badsnippets_levels_MIPS32EL_unique.csv              7          7      0
badsnippets_levels_MIPS32_unique.csv                7          7      0
badsnippets_levels_MIPS64_unique.csv                7          7      0
badsnippets_levels_RISCV_unique.csv                10         10      0
badsnippets_levels_X8632_unique.csv                26         26      0
badsnippets_levels_X8664_unique.csv                14         14      0

cjump locations: 84/84 recorded locations reproduced, 0 new
```

Each line compares one platform's conditional-branch (`cjump`) locations:
how many were recorded, how many were reproduced, and how many are new.
The comparison checks source locations, not the complete set of triggering
compiler configurations; any recorded branch location not reproduced is
listed explicitly.

The short functional checks focus on `cjump`. The paper also studies
data-flow findings (`mmem`), retaining them only at source locations where
`cjump` is detected under another compiler configuration (Paper §4.3).
Their filtering therefore depends on the configurations explored; standalone
`mmem` counts are not a target of these short comparisons. The tool also
records division instructions (`mdiv`), which are outside the paper's scope
(Paper §4.2). These auxiliary records remain in the result files.
[Step 3](#3-reproduce-paper-figures-and-tables-from-the-recorded-experimental-results) reproduces the paper's figures and tables with its full filtering rules.

To see what a detected violation looks like, open one of the result tables,
for example `results/badsnippets_clang18_filtered/badsnippets_levels_X8664_unique.csv`.
It is tab-separated with one row per violation location:

```
function      file                              line  col  source                                           char  type   optimization
check_scalar  bearssl-check_scalar-riscv64.c    67    31   c |= -(int32_t)EQ0(c) & CMP(k[u], P256_N[u]);   &     cjump  O1|O2|O3|Ofast|Os|Oz
```

This row says that in `check_scalar`, the bitwise selection on line 67 was
compiled into a conditional jump (`cjump`) at every optimization level
from `-O1` on. The `type` column identifies this as a conditional-branch
finding (`cjump`). The `optimization` column lists all configurations that
trigger the violation.

The paper's claim is that all 19 violations are recovered under the
compiler configuration of the original report. Several of those reports
name Clang 13 or 15, and the corresponding violation does not always appear
with Clang 14, 18 or 20; our recorded sets for these three versions
therefore contain 12, 16 and 17 of the 19 functions, and the check above
compares the branch locations for its version; it does not revalidate all
19 original reports under their original compiler configurations.

### 2.2 Run BearSSL across optimization levels

```sh
make bearssl-levels
```

This fetches BearSSL at the commit analyzed in the paper (`3c04036`),
builds it under the six optimization levels for the six platforms (36
builds, platforms in parallel, a few seconds each), runs the oracles and the
filter, and compares the `cjump` locations with the BearSSL results we recorded for
Clang 18 (`reproduce/data/01_all7libs_bearsslflags/res18/res18_bearssl_filtered/`). It takes about a minute. Expected
ending:

```
file                                         recorded reproduced    new
bearssl_levels_AArch64_unique.csv                   6          6      0
bearssl_levels_ARM_unique.csv                       4          4      0
bearssl_levels_MIPS32EL_unique.csv                  4          4      0
bearssl_levels_MIPS64_unique.csv                    5          5      0
bearssl_levels_RISCV_unique.csv                    19         19      0
bearssl_levels_X8664_unique.csv                    12         12      0

cjump locations: 50/50 recorded locations reproduced, 0 new
```

For a concrete BearSSL finding, open
`results/bearssl_levels_clang18_filtered/bearssl_levels_X8664_unique.csv`:

```
br_i15_muladd_small  src/int/i15_muladd.c  44  15  x -= (-ctl) & d;  &  cjump  O2
```

The constant-time idiom `x -= (-ctl) & d` in BearSSL's big-integer code
is compiled into a conditional jump at `-O2` on x86-64.

### 2.3 Locate the responsible compiler passes

```sh
make rootcause
```

For every violation found in [Step 2.1](#21-run-the-ground-truth-tests) on
x86-64, this recompiles the
affected function with `-mllvm --mfpass-dump` and the `PassViolateCT`
plugin, which print the instructions each optimization pass adds or
removes, and records the pass that introduced the offending instruction. It
takes seconds and writes
`results/rootcause_clang18/badsnippets_rootcause_X8664.json`, where each case
now carries a `pass-<type>` field, for instance

```
"pass-select": "InstCombinePass"                     (the select in check_scalar that later becomes a branch)
```

This is the mechanism behind the paper's Table 4; the table itself aggregates such
outputs over all libraries.

## 3 Reproduce paper figures and tables from the recorded experimental results

```sh
make reproduce
```

Running the full two-phase campaign again (three discovery libraries with
all candidates, four further libraries with the problematic shortlist, three
Clang versions and six platforms) would take weeks of server time, so the
artifact ships its outcome: `reproduce/data/` contains the filtered
detection results of every run behind the paper (466 result tables in the
format shown above, grouped by collection round), together with the manual
secret-dependency annotations behind Tables 2 and 3. `make reproduce`
regenerates Figure 4 (Paper §6), Figures 6–8 (Paper §8), and Figures 9–10
(Paper Appendix C) from these results, prints Tables 2 and 3, and compares every plotted
and tabulated number with the values in the paper. It runs in seconds and
ends with

```
Verification PASSED: every figure and table value matches the paper
```

The figures are written to `reproduce/figures/` as PDF.
`reproduce/README.md` lists, for each figure and table, the claim it
supports and the data folders it is computed from, and describes the
filtering steps that turn the raw detection tables into the paper's counts.

## 4 Rerun experiments (optional)

These runs generate fresh experimental results and are not necessary to
reproduce the figures and tables from the recorded experimental results in
[Step 3](#3-reproduce-paper-figures-and-tables-from-the-recorded-experimental-results).

### 4.1 Rerun BearSSL with problematic flags

```sh
make bearssl-flags
```

To check that the recorded experimental results can be regenerated and not only replotted,
this applies the Phase 2 shortlist to BearSSL for Clang 18 (a discovery
library, rather than one of the four Phase 2 libraries): the 139
problematic concrete flags of that version
(`tools/problematic_flags_clang18.txt`), each on top of each of the six
optimization levels, for the six platforms. That is about 5,000 builds,
which we expect to take a few hours on an eight-core machine. The final
comparison restricts the recorded results to the flags and levels that were run and reports the
recorded, reproduced and new `cjump` locations, as in [Step 2.2](#22-run-bearssl-across-optimization-levels).
To run only x86-64: `ARCHS=X8664 make bearssl-flags`.

### 4.2 Rerun the full two-phase library study

The flag lists are included in `tools/`, ready to run:

- **All flags:** `tools/all_flags_clang18.txt` (3,802 concrete flags).
- **Problematic flags:** `tools/problematic_flags_clang18.txt` (139 concrete flags).

Replace `18` with `14` or `20` for the other compiler versions. The complete
218-flag problematic list across versions is
[`tools/problematic_flags_all.txt`](tools/problematic_flags_all.txt).

To run the two phases for every library with the current compiler:

```sh
make phase1  # all flags: BearSSL, MbedTLS, PQClean
make phase2  # problematic flags: Libgcrypt, Libsodium, wolfSSL, OpenSSL
```

Repeat in each Clang 14, 18 and 20 container. These commands select the matching
flag file automatically. Results go to
`results/phase1_<library>_clang<version>_filtered/` and
`results/phase2_<library>_clang<version>_filtered/`.

Fresh-run counts may vary with build timeouts under different machine loads;
`BUILD_TIMEOUT` (default: 300 seconds per build) can be increased if needed.

## Reference: runtime settings

The experiment scripts read these environment variables:

| Variable | Meaning | Default |
| --- | --- | --- |
| `ARCHS` | platforms to build | the paper's six (`X8664 AArch64 ARM RISCV MIPS64 MIPS32EL`); [Step 2.1](#21-run-the-ground-truth-tests) also uses `X8632` and `MIPS32` |
| `LEVELS` | optimization levels | `O0 O1 O2 O3 Os Oz` |
| `PARALLEL_ARCHS` | platforms built at the same time | all listed |
| `JOBS` | `make -j` inside one build | `nproc / PARALLEL_ARCHS` |
| `BUILD_TIMEOUT` | seconds before a build is killed | 300 |
| `FLAGFILE`, `MLLVM_FLAGFILE` | flag lists for `make bearssl-flags` | the per-version problematic list |

On a four-core machine, `PARALLEL_ARCHS=2 JOBS=2` keeps the builds from
competing. Interrupted runs continue where they stopped; deleting
`work/<name>` and `results/<name>*` starts a run over. Per-platform build
logs are in `results/<name>/logs/`.

## Reference: hardware and measured runtimes

The campaign of the paper ran on one AMD Ryzen Threadripper PRO 7995WX (96
cores, 256 GB RAM) and two AMD EPYC 7713P (64 cores, 256 GB RAM) under
Ubuntu 22.04. Ubuntu/Debian on x86-64 is the recommended evaluation
environment. On a MacBook M5 Pro with 15 cores and 16 GB of memory assigned
to Docker: the image build took about a quarter of an hour and the image is about 4 GB;
`make kick-tires`, `make reproduce` and the root cause run each took
seconds and `make bearssl-levels` under a minute.
