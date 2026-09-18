# Reproducing the paper's figures and tables

Regenerates the four result figures and Tables 2 and 3 of the paper from the
recorded detection data, and checks every number against the paper.

## Run

```sh
uv run reproduce.py
```

Needs [uv](https://docs.astral.sh/uv/); dependencies are declared in the
script. Without uv: `pip install -r requirements.txt && python3 reproduce.py`
(Python 3.10+). Runtime is about two minutes.

The output is Table 2 and Table 3, the list of PDFs written to `figures/`,
and the final line

```
Verification PASSED: every figure and table value matches the paper
```

On a mismatch the script exits nonzero and lists the differing values.

## Claims

| Claim | Paper | Checked statement | Output |
| --- | --- | --- | --- |
| C1 | Figure 4 (`cryptolib_overview`) | Violations per library for Clang 18 (Libsodium 8, MbedTLS 17, OpenSSL 89, 311 total) | `figures/artifact_general_libs_clang18.pdf` |
| C2 | Figure 6 (`compiler-version-comparison`) | Newer Clang induces more violations, mainly through flags; Clang 14 has 128 level-only cases | `figures/artifact_clang_version_opt_comparison.pdf`, `figures/artifact_clang_version_flag_comparison.pdf` |
| C3 | Figure 7 (`quant-platform`) | AArch64, RISC-V and x86-64 are affected most | `figures/artifact_platform_analysis.pdf` |
| C4 | Figure 8 (`quant-config`) | -O1 to -O3 are similar, -O0 induces 12, LLVM flags induce far more than Clang flags | `figures/artifact_optimization_flags.pdf` |
| C5 | Table 2 | Secret-dependency per library: 225 of 311 Clang-18 cases | terminal output |
| C6 | Table 3 | 48 of 59 secret-dependent cases addressed upstream | terminal output |

The appendix per-library figures for Clang 14 and 20 are written as well
(Figures 9 and 10 in Appendix C: `figures/artifact_general_libs_clang14.pdf`, `..._clang20.pdf`).

Table 1, Table 4, the appendix flag-ranking tables and the diagrams are
hand-written and have no data pipeline.

## Inputs

`data/` holds the filtered detection results (`*_unique.csv`, one file per
library, optimization mode and architecture) from three collection rounds,
each with a `res14/`, `res18/`, `res20/` folder per Clang version:

| Folder | Libraries | Flags tested |
| --- | --- | --- |
| `01_all7libs_bearsslflags/` | all seven | problematic flags identified on BearSSL |
| `02_mbedtls_pqclean_allflags/` | MbedTLS, PQClean | full Clang and LLVM flag space (78 new problematic flags found) |
| `03_other4libs_new78flags/` | Libgcrypt, Libsodium, OpenSSL, wolfSSL | the 78 new flags |

`data/findings_table_complete.csv` is the manual annotation table behind
Tables 2 and 3: one row per finding with `leaks_secret` (YES/NO) and
`fixed_upstream` (upstream commit, pull request, CVE, or `not_fixed`). The
wolfSSL finding at `sp_int.c:18272` is marked `fixed_before_report`: wolfSSL
fixed it in PR #9618 before the disclosure, so it counts in Table 2 and is
left out of Table 3.

## Method

`scripts/filtering.py` applies the paper's post-processing before counting:

1. Keep branch (`cjump`) records; keep data-flow (`mmem`) records only where
   a branch exists at the same source location.
2. Drop known-noise flags (profiling, stack protector, `-ftrapv`, forced
   vectorization widths, and similar) and the two trigger tokens
   `-fgnuc-version=0` and `-fms-compatibility`, which only change MbedTLS
   feature detection.
3. Drop false-positive operator characters and excluded source patterns.
4. Group by `(line, column, source, character, library)`; the platform
   figure also keeps the architecture.

Verification compares the plotted integers with `expected_results.json`.

## Files

| Path | Role |
| --- | --- |
| `reproduce.py` | the whole reproduction |
| `scripts/` | loading, filtering, plotting, tables |
| `data/` | inputs |
| `expected_results.json` | numbers from the paper |
| `figures/`, `reproduced_results.json`, `reproduce.log` | generated outputs |
