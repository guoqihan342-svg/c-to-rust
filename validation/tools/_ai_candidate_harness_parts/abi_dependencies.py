from __future__ import annotations

import re
from typing import Any

from .context_security import canonical_json_bytes, sha256_bytes


TARGET_EXECUTION_PROOF = "target_execution"
LAYOUT_PROOF = "layout_or_ffi"


DEPENDENCY_PATTERNS = (
    (
        "repr_c",
        LAYOUT_PROOF,
        re.compile(r"#\s*\[\s*repr\s*\([^\r\n\]]*\bC\b", re.MULTILINE),
    ),
    (
        "repr_layout_modifier",
        LAYOUT_PROOF,
        re.compile(
            r"#\s*\[\s*repr\s*\([^\r\n\]]*"
            r"(?:\btransparent\b|\bpacked\b|\balign\s*\(|\b[ui](?:8|16|32|64|128)\b)",
            re.MULTILINE,
        ),
    ),
    ("raw_pointer", LAYOUT_PROOF, re.compile(r"\*\s*(?:const|mut)\b")),
    (
        "extern_abi",
        LAYOUT_PROOF,
        re.compile(r'\bextern\s+(?:"[A-Za-z0-9_-]+"\s*)?(?:fn|\{)'),
    ),
    (
        "linkage_attribute",
        LAYOUT_PROOF,
        re.compile(
            r"#\s*\[[^\r\n\]]*\b(?:no_mangle|export_name|link_name|link_section|link)\b"
        ),
    ),
    ("target_width_integer", TARGET_EXECUTION_PROOF, re.compile(r"\b(?:usize|isize)\b")),
    (
        "pointer_integer_cast",
        TARGET_EXECUTION_PROOF,
        re.compile(r"\bas\s+(?:usize|isize)\b"),
    ),
    (
        "target_cfg",
        TARGET_EXECUTION_PROOF,
        re.compile(r"\b(?:cfg|cfg_attr)\s*!?\s*\([^)]*\btarget_[a-z_]+\b", re.DOTALL),
    ),
    (
        "native_endian",
        TARGET_EXECUTION_PROOF,
        re.compile(r"\b(?:to_ne_bytes|from_ne_bytes)\b"),
    ),
    (
        "ffi_platform_type",
        TARGET_EXECUTION_PROOF,
        re.compile(
            r"\b(?:(?:core|std)\s*::\s*ffi\s*::\s*c_[A-Za-z0-9_]+|"
            r"std\s*::\s*os\s*::\s*raw\s*::\s*c_[A-Za-z0-9_]+|"
            r"libc\s*::\s*[A-Za-z_][A-Za-z0-9_]*)"
        ),
    ),
    (
        "layout_intrinsic",
        LAYOUT_PROOF,
        re.compile(
            r"\b(?:size_of|size_of_val|align_of|align_of_val|offset_of)"
            r"\s*!?\s*(?:::\s*)?(?:<|\()"
        ),
    ),
    (
        "transmute",
        LAYOUT_PROOF,
        re.compile(r"\b(?:transmute|transmute_copy)\s*(?:::\s*<|\()"),
    ),
    ("union_layout", LAYOUT_PROOF, re.compile(r"\bunion\s+[A-Za-z_][A-Za-z0-9_]*")),
    ("assembly", LAYOUT_PROOF, re.compile(r"\b(?:asm|global_asm)\s*!")),
)


def classify_abi_dependencies(masked_source: str) -> dict[str, Any]:
    dependencies = []
    for kind, proof_requirement, pattern in DEPENDENCY_PATTERNS:
        count = sum(1 for _match in pattern.finditer(masked_source))
        if count:
            dependencies.append(
                {
                    "kind": kind,
                    "proof_requirement": proof_requirement,
                    "count": count,
                }
            )
    payload = {
        "schema_version": 1,
        "required": bool(dependencies),
        "dependencies": dependencies,
    }
    payload["analysis_sha256"] = sha256_bytes(canonical_json_bytes(payload))
    return payload


def dependency_kinds(
    analysis: dict[str, Any], proof_requirement: str | None = None
) -> list[str]:
    return [
        item["kind"]
        for item in analysis["dependencies"]
        if proof_requirement is None
        or item["proof_requirement"] == proof_requirement
    ]


__all__ = [
    "LAYOUT_PROOF",
    "TARGET_EXECUTION_PROOF",
    "classify_abi_dependencies",
    "dependency_kinds",
]
