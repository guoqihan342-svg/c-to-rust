from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .artifacts import content_sha256
from .gate_evidence import require_content_addressed_reference
from .project_diagnostic_contract import (
    MAX_PROJECT_DIAGNOSTIC_INTAKES, intake_project_diagnostics,
    validate_project_diagnostic_intake,
)


PROJECT_DIAGNOSTIC_INTAKE_SET_SHA256_FIELD = (
    "project_diagnostic_intake_set_sha256"
)
PROJECT_DIAGNOSTIC_INTAKES_FIELD = "project_diagnostic_intakes"
PROJECT_VERIFIER_DIAGNOSTIC_SHA256S_FIELD = (
    "project_verifier_diagnostic_sha256s"
)


@dataclass(frozen=True, slots=True)
class VerifierReceiptInputs:
    references: list[dict[str, Any]]
    diagnostics: list[dict[str, Any]]
    intake_set_sha256: str | None
    diagnostic_sha256s: list[str]


def normalize_verifier_receipt_inputs(
    rust_project_ir: Mapping[str, Any],
    wrappers: Sequence[Mapping[str, Any]],
) -> VerifierReceiptInputs:
    if not wrappers:
        return VerifierReceiptInputs([], [], None, [])
    if len(wrappers) > MAX_PROJECT_DIAGNOSTIC_INTAKES:
        raise ValueError("project diagnostic intake count is unbounded")
    references: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    for wrapper in wrappers:
        if not isinstance(wrapper, Mapping) or set(wrapper) != {"artifact", "intake"}:
            raise ValueError("project diagnostic intake wrapper is invalid")
        artifact = dict(wrapper["artifact"])
        require_content_addressed_reference(artifact)
        intake = validate_project_diagnostic_intake(wrapper["intake"])
        if (
            intake["rust_project_ir_sha256"] != rust_project_ir.get("ir_sha256")
            or intake["rust_project_interface_sha256"]
            != rust_project_ir.get("interface_sha256")
        ):
            raise ValueError("project diagnostic intake changed RustProjectIR")
        references.append(artifact)
        diagnostics.extend(intake_project_diagnostics(intake))
    references.sort(key=lambda item: (item["path"], item["sha256"]))
    identities = [(item["path"], item["sha256"]) for item in references]
    if len(set(identities)) != len(identities):
        raise ValueError("project diagnostic intake references are duplicated")
    hashes = [item["diagnostic_sha256"] for item in diagnostics]
    if len(set(hashes)) != len(hashes):
        raise ValueError("project verifier diagnostics are duplicated")
    diagnostics.sort(key=lambda item: item["diagnostic_sha256"])
    return VerifierReceiptInputs(
        references, diagnostics, content_sha256(references), sorted(hashes),
    )


def receipt_project_diagnostic_references(
    receipt: Mapping[str, Any],
) -> list[dict[str, Any]]:
    if receipt.get("schema_version") != 2:
        return []
    raw = receipt.get(PROJECT_DIAGNOSTIC_INTAKES_FIELD)
    if not isinstance(raw, list):
        raise ValueError("project verifier receipt intake references are invalid")
    return [dict(item) for item in raw]


def verifier_diagnostic_detail(
    wrappers: Sequence[Mapping[str, Any]], diagnostic_sha256: str,
) -> dict[str, Any] | None:
    matches = []
    for wrapper in wrappers:
        intake = validate_project_diagnostic_intake(wrapper["intake"])
        matches.extend(
            dict(item) for item in intake["diagnostics"]
            if item["project_diagnostic"]["diagnostic_sha256"]
            == diagnostic_sha256
        )
    if len(matches) > 1:
        raise ValueError("project verifier diagnostic detail is ambiguous")
    return None if not matches else matches[0]


__all__ = [
    "PROJECT_DIAGNOSTIC_INTAKES_FIELD",
    "PROJECT_DIAGNOSTIC_INTAKE_SET_SHA256_FIELD", "VerifierReceiptInputs",
    "PROJECT_VERIFIER_DIAGNOSTIC_SHA256S_FIELD",
    "normalize_verifier_receipt_inputs", "receipt_project_diagnostic_references",
    "verifier_diagnostic_detail",
]
