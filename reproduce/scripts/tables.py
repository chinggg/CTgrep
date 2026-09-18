"""Table 2 (secret-dependency) and Table 3 (addressed cases).

The detection rows come from the same filtered data as the figures, kept per
architecture. Findings that only appeared in targeted CTGrep runs are added
from the annotation table (rows without mmem evidence). The annotation table
supplies the manual verdicts: leaks_secret (YES/NO) and fixed_upstream (a
commit, pull request, CVE, or not_fixed). A fixed_upstream value starting
with fixed_before_report keeps the finding in Table 2 and drops it from
Table 3.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from filtering import ALWAYS_DROP_ARCHS, process_result

MAINSTREAM_ARCHS = {"X8664", "RISCV", "AArch64"}
FINDING_KEY = ["line", "col", "source", "char", "lib"]
FIXED_BEFORE_REPORT = "fixed_before_report"

_PQC_SCHEMES = [
    ("Falcon", ["falcon", "ntru", "mq_", "zint_", "fpr", "modp", "make_fg"]),
    ("ML-DSA", ["mldsa", "ml-dsa"]),
    ("ML-KEM", ["mlkem", "ml-kem"]),
    ("HQC", ["hqc", "gf.c", "gf2x.c", "reed", "compute_error", "compute_elp"]),
    ("SPHINCS+", ["sphincs"]),
]
# Same precedence as the original generator: ML-DSA, ML-KEM, HQC, SPHINCS+, Falcon; default Falcon.
_PQC_ORDER = ["ML-DSA", "ML-KEM", "HQC", "SPHINCS+", "Falcon"]


def _pqclean_scheme(row) -> str:
    text = " ".join(str(row.get(c, "") or "") for c in ("function", "file", "notes") if c in row).lower()
    kw = dict(_PQC_SCHEMES)
    for scheme in _PQC_ORDER:
        if any(k in text for k in kw[scheme]):
            return f"pqclean/{scheme}"
    return "pqclean/Falcon"


# ── detection table ──────────────────────────────────────────────────────────

def build_detection_table() -> pd.DataFrame:
    """One row per (finding, arch, clangversion) after the paper's filtering."""
    frames = []
    for version in CLANG_VERSIONS:
        suffix = version[-2:]
        for rnd in ROUNDS:
            folder = DATA_DIR / rnd / f"res{suffix}"
            if not folder.is_dir():
                continue
            raw = read_files_and_create_df(folder, version)
            frames.append(process_result(raw, group_rule="per_arch"))
    return pd.concat(frames, ignore_index=True)


def supplement_from_annotations(det: pd.DataFrame, ann_path: Path) -> pd.DataFrame:
    ann = pd.read_csv(ann_path, keep_default_na=False)
    covered = {(tuple(r[k] for k in FINDING_KEY), r["clangversion"]) for _, r in det.iterrows()}
    extra = []
    for _, row in ann.iterrows():
        if "mmem" in str(row.get("type", "")):
            continue
        key = tuple(row[k] for k in FINDING_KEY)
        for arch in str(row.get("arch", "")).split("|"):
            arch = arch.strip()
            if not arch or arch in ALWAYS_DROP_ARCHS:
                continue
            for ver in str(row.get("clangversion", "")).split("|"):
                ver = ver.strip()
                if ver and (key, ver) not in covered:
                    r = row.to_dict()
                    r["arch"], r["clangversion"] = arch, ver
                    extra.append(r)
    if not extra:
        return det
    extra_df = pd.DataFrame(extra)
    for col in det.columns:
        if col not in extra_df.columns:
            extra_df[col] = ""
    return pd.concat([det, extra_df[det.columns]], ignore_index=True)


def attach_annotations(det: pd.DataFrame, ann_path: Path) -> pd.DataFrame:
    ann = pd.read_csv(ann_path, keep_default_na=False)
    keep = FINDING_KEY + ["leaks_secret", "fixed_upstream"] + (["notes"] if "notes" in ann.columns else [])
    ann = ann[keep].drop_duplicates(FINDING_KEY)
    det = det.merge(ann, on=FINDING_KEY, how="left")
    pq = det["lib"] == "pqclean"
    det.loc[pq, "lib"] = det[pq].apply(_pqclean_scheme, axis=1)
    fixed = det["fixed_upstream"].fillna("").astype(str).str.strip()
    det["is_tp"] = det["leaks_secret"] == "YES"
    det["is_fixed"] = ~fixed.isin(["", "not_fixed"])
    det["fixed_before_report"] = fixed.str.startswith(FIXED_BEFORE_REPORT)
    return det


def _collapse(det: pd.DataFrame) -> pd.DataFrame:
    return det.groupby(FINDING_KEY, as_index=False).agg(
        is_tp=("is_tp", "max"),
        is_fixed=("is_fixed", "max"),
        fixed_before_report=("fixed_before_report", "max"),
    )


# ── the two paper tables ─────────────────────────────────────────────────────

def table2_secret_dependency(det: pd.DataFrame) -> dict[str, dict[str, int]]:
    """Table 2: Clang 18, all platforms. Potential violations and secret-dependent count per library/scheme."""
    findings = _collapse(det[det["clangversion"] == "clang18"])
    out = {}
    for lib, grp in findings.groupby("lib"):
        out[lib] = {"potential": int(len(grp)), "secret_dependent": int(grp["is_tp"].sum())}
    return out


def table3_addressed(det: pd.DataFrame) -> dict[str, dict[str, int]]:
    """Table 3: Clang 18, mainstream platforms. Secret-dependent and addressed cases, libraries with fixes only.

    Findings marked fixed_before_report are excluded from both counts.
    """
    sub = det[(det["clangversion"] == "clang18") & det["arch"].isin(MAINSTREAM_ARCHS)]
    findings = _collapse(sub)
    findings = findings[~findings["fixed_before_report"]]
    out = {}
    for lib, grp in findings.groupby("lib"):
        tps = int(grp["is_tp"].sum())
        fixed = int(grp[grp["is_tp"]]["is_fixed"].sum())
        if fixed:
            out[lib] = {"secret_dependent": tps, "addressed": fixed}
    return out



def build_tables(inputs: dict[str, pd.DataFrame], annotations: Path) -> dict:
    det = pd.concat(
        [process_result(frame, group_rule="per_arch") for frame in inputs.values()],
        ignore_index=True,
    )
    det = supplement_from_annotations(det, annotations)
    det = attach_annotations(det, annotations)
    return {
        "table2_secret_dependency": table2_secret_dependency(det),
        "table3_addressed": table3_addressed(det),
    }


def _pct(n: int, d: int) -> str:
    return f"{(n / d * 100 if d else 0):.1f}% ({n})"


def format_tables(tables: dict) -> str:
    t2, t3 = tables["table2_secret_dependency"], tables["table3_addressed"]
    lines = ["Table 2: secret-dependency (Clang 18, all platforms)",
             "| Library | Potential violations | Secret-dependent |", "|---|---|---|"]
    lines += [f"| {lib} | {v['potential']} | {_pct(v['secret_dependent'], v['potential'])} |" for lib, v in t2.items()]
    lines += ["", "Table 3: addressed cases (Clang 18, mainstream platforms)",
              "| Library | Secret-dependent cases | Addressed cases |", "|---|---|---|"]
    lines += [f"| {lib} | {v['secret_dependent']} | {_pct(v['addressed'], v['secret_dependent'])} |" for lib, v in t3.items()]
    return "\n".join(lines)
