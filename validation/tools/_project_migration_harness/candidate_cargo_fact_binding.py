from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from .artifacts import canonical_json_bytes, checked_relative_path, content_sha256
from .build_ir import is_sha256
from .candidate_cargo_fact_sources import (
    candidate_cargo_fact_source_references,
    captured_candidate_cargo_fact_sources,
    read_candidate_cargo_fact_sources,
)
from .cargo_compiler_artifact_evidence import (
    parse_cargo_compiler_artifact_evidence,
    validate_cargo_compiler_artifact_evidence,
)
from .cargo_metadata_fact_evidence import (
    parse_cargo_metadata_fact_evidence,
    validate_cargo_metadata_fact_evidence,
)
from .gate_evidence import (
    read_content_addressed_json,
    require_content_addressed_reference,
    write_content_addressed_json,
)
from .ledger_security import LedgerError


_CLAIM_BOUNDARY = {
    "interface_closure": False,
    "semantic_gate": False,
    "translation_coverage_numerator": 0,
}
_BINDING_KEYS = {
    "schema_version", "status", "cargo_metadata", "compiler_artifacts",
    "claim_boundary", "binding_sha256",
}
_METADATA_KEYS = {"status", "facts_sha256", "source", "evidence"}
_COMPILER_KEYS = {
    "artifact_count", "artifact_set_sha256", "source", "evidence",
}


def parse_captured_candidate_cargo_facts(
    execution: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    sources = captured_candidate_cargo_fact_sources(execution)
    return {
        "cargo_metadata": parse_cargo_metadata_fact_evidence(
            sources["cargo_metadata"]
        ),
        "compiler_artifacts": parse_cargo_compiler_artifact_evidence(
            sources["compiler_artifacts"]
        ),
    }


def write_candidate_cargo_fact_binding(
    *, parsed: Mapping[str, Mapping[str, Any]],
    execution: Mapping[str, Any], observations: Mapping[str, Any],
    out_root: Path, out_root_rel: str,
) -> dict[str, Any]:
    metadata = validate_cargo_metadata_fact_evidence(parsed["cargo_metadata"])
    compiler = validate_cargo_compiler_artifact_evidence(
        parsed["compiler_artifacts"]
    )
    metadata_ref = _write_evidence(
        out_root, out_root_rel, "cargo-metadata", metadata,
    )
    compiler_ref = _write_evidence(
        out_root, out_root_rel, "compiler-artifacts", compiler,
    )
    sources = candidate_cargo_fact_source_references(execution, observations)
    binding = _binding(
        metadata, compiler, sources, metadata_ref, compiler_ref,
    )
    return validate_candidate_cargo_fact_binding(
        binding, execution=execution, observations=observations,
    )


def validate_candidate_cargo_fact_binding(
    value: Any, *, execution: Mapping[str, Any], observations: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _BINDING_KEYS:
        raise ValueError("candidate_cargo_fact_binding_schema_invalid")
    binding = dict(value)
    metadata = _item(binding, "cargo_metadata", _METADATA_KEYS)
    compiler = _item(binding, "compiler_artifacts", _COMPILER_KEYS)
    sources = candidate_cargo_fact_source_references(execution, observations)
    if (
        binding.get("schema_version") != 1
        or binding.get("status") not in {"ready", "blocked"}
        or binding.get("status") != metadata.get("status")
        or metadata.get("status") not in {"ready", "blocked"}
        or not is_sha256(metadata.get("facts_sha256"))
        or type(compiler.get("artifact_count")) is not int
        or compiler["artifact_count"] <= 0
        or not is_sha256(compiler.get("artifact_set_sha256"))
        or binding.get("claim_boundary") != _CLAIM_BOUNDARY
        or metadata.get("source") != sources["cargo_metadata"]
        or compiler.get("source") != sources["compiler_artifacts"]
    ):
        raise ValueError("candidate_cargo_fact_binding_invalid")
    _evidence_reference(metadata.get("evidence"), "cargo-metadata")
    _evidence_reference(compiler.get("evidence"), "compiler-artifacts")
    core = {key: binding[key] for key in binding if key != "binding_sha256"}
    if binding.get("binding_sha256") != content_sha256(core):
        raise ValueError("candidate_cargo_fact_binding_sha256_drifted")
    return binding


def reopen_candidate_cargo_fact_binding(
    ledger_path: Path, value: Mapping[str, Any], *,
    execution: Mapping[str, Any], observations: Mapping[str, Any],
) -> dict[str, Any]:
    return reopen_candidate_cargo_fact_payloads(
        ledger_path, value, execution=execution, observations=observations,
    )["binding"]


def reopen_candidate_cargo_fact_payloads(
    ledger_path: Path, value: Mapping[str, Any], *,
    execution: Mapping[str, Any], observations: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        binding = validate_candidate_cargo_fact_binding(
            value, execution=execution, observations=observations,
        )
        sources = read_candidate_cargo_fact_sources(
            ledger_path, execution, observations,
        )
        metadata = validate_cargo_metadata_fact_evidence(
            _read_evidence(ledger_path, binding["cargo_metadata"]["evidence"]),
            sources["cargo_metadata"],
        )
        compiler = validate_cargo_compiler_artifact_evidence(
            _read_evidence(
                ledger_path, binding["compiler_artifacts"]["evidence"],
            ),
            sources["compiler_artifacts"],
        )
        expected = _binding(
            metadata,
            compiler,
            candidate_cargo_fact_source_references(execution, observations),
            binding["cargo_metadata"]["evidence"],
            binding["compiler_artifacts"]["evidence"],
        )
    except (KeyError, OSError, TypeError, ValueError, LedgerError) as error:
        raise LedgerError("candidate Cargo fact evidence is invalid") from error
    if binding != expected:
        raise LedgerError("candidate Cargo fact evidence binding drifted")
    return {
        "binding": binding,
        "cargo_metadata": metadata,
        "compiler_artifacts": compiler,
    }


def _binding(
    metadata: Mapping[str, Any], compiler: Mapping[str, Any],
    sources: Mapping[str, Mapping[str, Any]],
    metadata_ref: Mapping[str, Any], compiler_ref: Mapping[str, Any],
) -> dict[str, Any]:
    core = {
        "schema_version": 1,
        "status": metadata["status"],
        "cargo_metadata": {
            "status": metadata["status"],
            "facts_sha256": metadata["facts_sha256"],
            "source": dict(sources["cargo_metadata"]),
            "evidence": dict(metadata_ref),
        },
        "compiler_artifacts": {
            "artifact_count": compiler["artifact_count"],
            "artifact_set_sha256": compiler["artifact_set_sha256"],
            "source": dict(sources["compiler_artifacts"]),
            "evidence": dict(compiler_ref),
        },
        "claim_boundary": dict(_CLAIM_BOUNDARY),
    }
    return {**core, "binding_sha256": content_sha256(core)}


def _write_evidence(
    root: Path, root_rel: str, kind: str, value: Mapping[str, Any],
) -> dict[str, Any]:
    reference = write_content_addressed_json(
        root, f"candidate-cargo-facts/{kind}", value,
    )
    prefix = checked_relative_path(root_rel)
    return {**reference, "path": f"{prefix}/{reference['path']}"}


def _evidence_reference(value: Any, kind: str) -> None:
    if not isinstance(value, Mapping):
        raise ValueError("candidate_cargo_fact_evidence_reference_invalid")
    try:
        require_content_addressed_reference(value)
    except LedgerError as error:
        raise ValueError("candidate_cargo_fact_evidence_reference_invalid") from error
    parts = PurePosixPath(str(value["path"])).parts
    expected = ("verification", "candidate-cargo-facts", kind)
    if not any(
        tuple(parts[index:index + 3]) == expected
        for index in range(len(parts) - 2)
    ):
        raise ValueError("candidate_cargo_fact_evidence_scope_invalid")


def _read_evidence(
    ledger_path: Path, reference: Mapping[str, Any],
) -> dict[str, Any]:
    evidence = read_content_addressed_json(
        ledger_path, str(reference["path"]), str(reference["sha256"]),
    )
    if len(canonical_json_bytes(evidence)) != reference.get("size_bytes"):
        raise LedgerError("candidate Cargo fact evidence size drifted")
    return evidence


def _item(value: Mapping[str, Any], key: str, keys: set[str]) -> dict[str, Any]:
    item = value.get(key)
    if not isinstance(item, Mapping) or set(item) != keys:
        raise ValueError("candidate_cargo_fact_binding_item_invalid")
    return dict(item)


__all__ = [
    "parse_captured_candidate_cargo_facts",
    "reopen_candidate_cargo_fact_binding",
    "reopen_candidate_cargo_fact_payloads",
    "validate_candidate_cargo_fact_binding",
    "write_candidate_cargo_fact_binding",
]
