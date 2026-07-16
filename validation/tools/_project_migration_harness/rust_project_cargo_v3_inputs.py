from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from . import cargo_project
from .orchestration_facts import read_artifact_reference
from .rust_candidate_facts import derive_rust_metadata
from .rust_project_ir_records import ffi_records, public_records, unsafe_records
from .rust_project_ir_source_facts import derive_bound_candidate_source_facts


MAX_TOTAL_SOURCE_BYTES = 8_000_000
MAX_UNSAFE_OBLIGATIONS = 4_096


def load_v3_candidate_sources(
    ir: Mapping[str, Any], artifact_root: Path, *, max_source_bytes: int,
) -> dict[str, dict[str, Any]]:
    """Reopen every v3 candidate once and recompute source-bound IR facts."""
    if (
        isinstance(max_source_bytes, bool)
        or not isinstance(max_source_bytes, int)
        or not 1 <= max_source_bytes <= cargo_project.MAX_SOURCE_BYTES
    ):
        _fail("candidate_size_limit_invalid", "candidate")
    result: dict[str, dict[str, Any]] = {}
    total = 0
    for reference in ir["bindings"]["candidates"]:
        unit_id = str(reference["unit_id"])
        try:
            raw = read_artifact_reference(artifact_root, reference["source"])
            source = raw.decode("utf-8")
        except (OSError, UnicodeError, TypeError, ValueError) as error:
            _fail("candidate_source_unreadable", "candidate", unit_id, error)
        total += len(raw)
        if len(raw) > max_source_bytes or total > MAX_TOTAL_SOURCE_BYTES:
            _fail("candidate_sources_too_large", "candidate", unit_id)
        metadata = derive_rust_metadata(source)
        facts = derive_bound_candidate_source_facts(
            source, metadata["public_symbols"],
        )
        result[unit_id] = {
            "unit_id": unit_id,
            "artifact_id": str(reference["artifact_id"]),
            "source_path": str(reference["source"]["path"]),
            "sha256": str(reference["source"]["sha256"]),
            "source": raw,
            "text": source,
            "metadata": metadata,
            "source_facts": facts,
        }
    if len(result) != len(ir["bindings"]["candidates"]):
        _fail("candidate_unit_duplicate", "candidate")
    _validate_source_bound_records(ir, result)
    return result


def accepted_groups(
    candidates: Mapping[str, Mapping[str, Any]],
    dependencies: Mapping[str, list[str] | tuple[str, ...]],
) -> list[dict[str, Any]]:
    groups = []
    for unit_id in sorted(candidates):
        candidate = candidates[unit_id]
        metadata = candidate["metadata"]
        groups.append({
            "group_id": unit_id,
            "dependencies": list(dependencies.get(unit_id, ())),
            "source": {
                "path": candidate["source_path"],
                "sha256": candidate["sha256"],
                "size_bytes": len(candidate["source"]),
            },
            "public_symbols": list(metadata["public_symbols"]),
            "required_symbols": list(metadata["required_symbols"]),
            "unsafe_count": int(metadata["unsafe_count"]),
        })
    return groups


def unsafe_policy(
    candidates: Mapping[str, Mapping[str, Any]], raw_policy: Any = None,
) -> dict[str, Any]:
    values = [
        cargo_project.CandidateSource(
            group_id=unit_id,
            status="accepted",
            source_path=str(item["source_path"]),
            sha256=str(item["sha256"]),
            source=item["source"],
            public_symbols=tuple(item["metadata"]["public_symbols"]),
            required_symbols=tuple(item["metadata"]["required_symbols"]),
            unsafe_count=int(item["metadata"]["unsafe_count"]),
        )
        for unit_id, item in sorted(candidates.items())
    ]
    return cargo_project._unsafe_policy(raw_policy, values)


def _validate_source_bound_records(
    ir: Mapping[str, Any], candidates: Mapping[str, Mapping[str, Any]],
) -> None:
    build_shas = list(ir["workspace"]["evidence"]["build_ir_sha256s"])
    expected_public: list[dict[str, Any]] = []
    expected_ffi: list[dict[str, Any]] = []
    expected_unsafe: list[dict[str, Any]] = []
    for module in ir["modules"]:
        unit_id = str(module["unit_id"])
        candidate = candidates.get(unit_id)
        if candidate is None:
            _fail("rust_project_ir_module_candidate_missing", "rust_project_ir", unit_id)
        module_id = str(module["module_id"])
        metadata = candidate["metadata"]
        expected_public.extend(public_records(
            module_id, unit_id, str(candidate["sha256"]), build_shas,
            metadata["public_symbols"], candidate["source_facts"],
        ))
        expected_ffi.extend(ffi_records(
            module_id, unit_id, str(candidate["sha256"]), build_shas,
            str(candidate["text"]),
        ))
        try:
            expected_unsafe.extend(unsafe_records(
                module_id, unit_id, str(candidate["sha256"]), build_shas,
                int(metadata["unsafe_count"]),
                max_count=MAX_UNSAFE_OBLIGATIONS,
                target_scoped_identity=True,
            ))
        except ValueError as error:
            _fail("candidate_unsafe_obligations_unbounded", "candidate", unit_id, error)
    comparisons = (
        ("public_api", expected_public, "rust_project_ir_public_api_drift"),
        ("ffi_boundaries", expected_ffi, "rust_project_ir_ffi_boundary_drift"),
        ("unsafe_obligations", expected_unsafe,
         "rust_project_ir_unsafe_obligation_drift"),
    )
    for section, expected, code in comparisons:
        identity = "obligation_id" if section == "unsafe_obligations" else "declaration_id"
        if sorted(ir[section], key=lambda item: item[identity]) != sorted(
            expected, key=lambda item: item[identity],
        ):
            _fail(code, "rust_project_ir")


def _fail(
    code: str, stage: str, group_id: str | None = None,
    detail: Exception | None = None,
) -> None:
    del detail
    raise cargo_project.ProjectInputError(code, stage, group_id)


__all__ = [
    "accepted_groups", "load_v3_candidate_sources", "unsafe_policy",
]
