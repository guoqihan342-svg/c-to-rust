from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from .gate_evidence import (
    read_content_addressed_json, require_content_addressed_reference,
    write_content_addressed_json,
)
from .ledger_security import LedgerError


def write_clang_derived_evidence(
    out_root: Path, *, plan_sha256: str, evidence: Mapping[str, Any],
) -> dict[str, Any]:
    reference = write_content_addressed_json(
        Path(out_root), f"derived/clang-fact/{plan_sha256}", evidence,
    )
    return validate_clang_derived_reference(reference, plan_sha256=plan_sha256)


def read_clang_derived_evidence(
    ledger_path: Path, reference: Mapping[str, Any], *, plan_sha256: str,
) -> dict[str, Any]:
    bound = validate_clang_derived_reference(reference, plan_sha256=plan_sha256)
    return read_content_addressed_json(
        Path(ledger_path), bound["path"], bound["sha256"],
    )


def validate_clang_derived_reference(
    value: Any, *, plan_sha256: str,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("clang_fact_derived_reference_invalid")
    reference = dict(value)
    try:
        require_content_addressed_reference(reference)
    except LedgerError as error:
        raise ValueError("clang_fact_derived_reference_invalid") from error
    parts = PurePosixPath(str(reference["path"])).parts
    expected = (
        "verification", "derived", "clang-fact", plan_sha256,
        f"{reference['sha256']}.json",
    )
    if parts != expected:
        raise ValueError("clang_fact_derived_reference_path_invalid")
    return reference


__all__ = [
    "read_clang_derived_evidence", "validate_clang_derived_reference",
    "write_clang_derived_evidence",
]
