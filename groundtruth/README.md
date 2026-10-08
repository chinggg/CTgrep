# Ground-truth configurations

The 19 sources are in `snippets/`. `compiler_configs.json` saves the original
Compiler Explorer compiler IDs, versions, language, target settings and flags,
retrieved on 2026-10-08 through its
[API](https://github.com/compiler-explorer/compiler-explorer/blob/main/docs/API.md).
The saved source text was checked against each shipped snippet. No network
access is needed to read these settings or run the tests.

To generate assembly with the original options, provide the corresponding
compiler locally, for example:

```sh
python3 groundtruth/replay.py binsec-ct_select_u32_v1-x8664.c \
    --compiler /path/to/clang-18.1.0 --output /tmp/snippet.s
```

`replay.py` preserves the saved language, target options and user flags.
`target_options` makes the original architecture explicit, including x86-64
where Compiler Explorer relied on its host default.
Some `.c` snippets were originally compiled as C++; the script uses `-x`
accordingly. Compiler Explorer's installation-specific defaults are also saved
as `compiler_defaults`; local GCC toolchain/sysroot paths can be supplied with
`--extra-flags`. For RISC-V, provide the matching cross toolchain/sysroot.
Use the listed compiler version to check the original report; a different
version can produce different assembly.

For CTgrep's recorded Clang 14/18/20 checks, run `make kick-tires` instead.
Its platforms and optimization levels are set in `experiments/kick_tires.sh`,
and per-snippet build options are in `configs/breakingbad/Makefile`.
