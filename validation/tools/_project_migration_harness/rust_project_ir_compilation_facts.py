from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from .artifacts import canonical_json_bytes, checked_relative_path
from .build_facts import is_linklike
from .build_ir import is_sha256, translation_units_for_index
from .c_compilation_fact_bundle import (
    compiler_facts_for_index,
    validate_c_compilation_fact_bundle,
)


MAX_COMPILATION_FACT_BYTES = 64 * 1024 * 1024
_MANIFEST_BINDING_KEYS = {"status", "artifact"}


def manifest_compilation_facts_reference(
    manifest: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Return the exact plan artifact binding, or explicit absence."""
    binding = manifest.get("c_compilation_facts")
    if binding is None:
        return None
    if (
        not isinstance(binding, Mapping)
        or set(binding) != _MANIFEST_BINDING_KEYS
        or binding.get("status") != "bound"
    ):
        raise ValueError("c_compilation_facts_manifest_binding_invalid")
    reference = binding.get("artifact")
    _reference_identity(reference)
    return dict(reference)


def validate_manifest_compilation_facts_binding(value: Any) -> None:
    if value is None:
        return
    if (
        not isinstance(value, Mapping)
        or set(value) != _MANIFEST_BINDING_KEYS
        or value.get("status") != "bound"
    ):
        raise ValueError("c_compilation_facts_manifest_binding_invalid")
    _reference_identity(value.get("artifact"))


def reopen_compilation_facts(
    artifact_root: Path,
    reference: Mapping[str, Any] | None,
    build_irs: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    if reference is None:
        return None
    raw = _read_reference(artifact_root, reference)
    bundle = _strict_bundle(raw)
    if len(build_irs) != 1:
        raise ValueError("c_compilation_facts_build_domain_ambiguous")
    build_ir = build_irs[0]
    units = translation_units_for_index(build_ir)
    facts = compiler_facts_for_index(
        bundle,
        units,
        build_ir_semantic_sha256=str(build_ir.get("semantic_sha256")),
    )
    expected_ids = {str(item["unit_id"]) for item in units}
    observed_ids = set(facts)
    summary = bundle["summary"]
    coverage_complete = (
        observed_ids == expected_ids
        and summary["observed"] == summary["total"] == len(expected_ids)
    )
    return {
        "artifact": dict(reference),
        "bundle_sha256": str(bundle["bundle_sha256"]),
        "build_ir_semantic_sha256": str(bundle["build_ir_semantic_sha256"]),
        "status": str(bundle["status"]),
        "observed": int(summary["observed"]),
        "total": int(summary["total"]),
        "syntax_passed": int(summary["passed"]),
        "coverage_complete": coverage_complete,
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
    }


def reopen_manifest_compilation_facts(
    artifact_root: Path, manifest: Mapping[str, Any],
    ir_reference: Mapping[str, Any] | None,
    build_irs: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    manifest_reference = manifest_compilation_facts_reference(manifest)
    if manifest_reference != (
        None if ir_reference is None else dict(ir_reference)
    ):
        raise ValueError(
            "migration DAG and RustProjectIR bind different C compilation facts"
        )
    return reopen_compilation_facts(artifact_root, ir_reference, build_irs)


def validate_dag_metadata(
    payload: Mapping[str, Any], artifact_identity: Callable[[Any], Any],
) -> None:
    profile = payload.get("profile")
    if profile is not None and profile not in {"competition", "development"}:
        raise ValueError("bound migration DAG profile is invalid")
    boundary = payload.get("claim_boundary")
    if boundary is not None and boundary != {
        "semantic_gate": False, "translation_coverage_numerator": 0,
    }:
        raise ValueError("bound migration DAG claim boundary is invalid")
    validate_manifest_compilation_facts_binding(
        payload.get("c_compilation_facts")
    )
    policy = payload.get("unsafe_policy")
    if policy is not None:
        if not isinstance(policy, Mapping) or set(policy) != {
            "allow_unsafe", "max_total", "max_per_group",
        } or not isinstance(policy.get("allow_unsafe"), bool):
            raise ValueError("bound migration DAG unsafe policy is invalid")
        for key in ("max_total", "max_per_group"):
            limit = policy.get(key)
            if limit is not None and (
                isinstance(limit, bool) or not isinstance(limit, int) or limit < 0
            ):
                raise ValueError("bound migration DAG unsafe policy is invalid")
    generated = payload.get("generated_build_closure")
    if generated is not None:
        if not isinstance(generated, Mapping) or set(generated) != {
            "status", "closure", "verification",
        } or generated.get("status") not in {"bound", "blocked"}:
            raise ValueError(
                "bound migration DAG generated closure binding is invalid"
            )
        artifact_identity(generated.get("closure"))
        artifact_identity(generated.get("verification"))


def _strict_bundle(raw: bytes) -> dict[str, Any]:
    import json

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for key, item in items:
            if key in result:
                raise ValueError("c_compilation_facts_duplicate_key")
            result[key] = item
        return result

    try:
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("c_compilation_facts_json_invalid") from error
    if not isinstance(payload, dict) or canonical_json_bytes(payload) != raw:
        raise ValueError("c_compilation_facts_not_canonical")
    return validate_c_compilation_fact_bundle(payload)


def _read_reference(root: Path, reference: Mapping[str, Any]) -> bytes:
    relative, expected, declared_size = _reference_identity(reference)
    base = Path(root).resolve(strict=True)
    current = base
    for part in PurePosixPath(relative).parts:
        current /= part
        if current.exists() and is_linklike(current):
            raise ValueError("c_compilation_facts_link_forbidden")
    target = current.resolve(strict=True)
    target.relative_to(base)
    if target.stat().st_size != declared_size:
        raise ValueError("c_compilation_facts_size_drifted")
    with target.open("rb") as stream:
        raw = stream.read(MAX_COMPILATION_FACT_BYTES + 1)
    if len(raw) != declared_size or hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("c_compilation_facts_content_drifted")
    return raw


def _reference_identity(value: Any) -> tuple[str, str, int]:
    if not isinstance(value, Mapping) or set(value) != {
        "path", "sha256", "size_bytes",
    }:
        raise ValueError("c_compilation_facts_reference_invalid")
    relative = checked_relative_path(value.get("path"))
    digest = value.get("sha256")
    size = value.get("size_bytes")
    if not is_sha256(digest):
        raise ValueError("c_compilation_facts_reference_invalid")
    if (
        isinstance(size, bool) or not isinstance(size, int)
        or not 0 <= size <= MAX_COMPILATION_FACT_BYTES
    ):
        raise ValueError("c_compilation_facts_reference_invalid")
    return relative, str(digest), size


__all__ = [
    "MAX_COMPILATION_FACT_BYTES",
    "manifest_compilation_facts_reference",
    "reopen_compilation_facts",
    "reopen_manifest_compilation_facts",
    "validate_dag_metadata",
    "validate_manifest_compilation_facts_binding",
]
