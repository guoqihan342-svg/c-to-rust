from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .artifacts import checked_relative_path, content_sha256
from .build_ir import is_sha256
from .clang_toolchain_binding import validate_clang_toolchain_receipt


DOMAIN_KIND = "project-interface-validation-domain"
DOMAIN_SCOPE = "project-interface-validation-domain"
CLAIM_BOUNDARY = {
    "interface_closure": False,
    "semantic_gate": False,
    "semantic_pass": False,
    "translation_coverage_numerator": 0,
}
_TOP_KEYS = {
    "schema_version", "artifact_kind", "status", "run", "rust_project_ir",
    "source_domain", "candidate_set", "candidate_project_verification",
    "clang_toolchain", "clang_fact_plans", "claim_boundary", "domain_sha256",
}


def validate_project_interface_validation_domain(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _TOP_KEYS:
        raise ValueError("interface_validation_domain_fields_invalid")
    payload = dict(value)
    if (
        payload.get("schema_version") != 1
        or payload.get("artifact_kind") != DOMAIN_KIND
        or payload.get("status") != "ready"
        or payload.get("claim_boundary") != CLAIM_BOUNDARY
    ):
        raise ValueError("interface_validation_domain_identity_invalid")
    _run(payload.get("run"))
    _rust_project_ir(payload.get("rust_project_ir"))
    _source_domain(payload.get("source_domain"))
    _candidate_set(payload.get("candidate_set"))
    _candidate_verification(payload.get("candidate_project_verification"))
    _clang_toolchain(payload.get("clang_toolchain"))
    _clang_plans(payload.get("clang_fact_plans"))
    core = {key: payload[key] for key in payload if key != "domain_sha256"}
    if payload.get("domain_sha256") != content_sha256(core):
        raise ValueError("interface_validation_domain_sha256_invalid")
    return payload


def artifact_reference(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "path", "sha256", "size_bytes",
    }:
        raise ValueError("interface_validation_domain_reference_invalid")
    try:
        path = checked_relative_path(value.get("path"))
    except ValueError as error:
        raise ValueError("interface_validation_domain_reference_invalid") from error
    digest, size = value.get("sha256"), value.get("size_bytes")
    if not is_sha256(digest) or type(size) is not int or size <= 0:
        raise ValueError("interface_validation_domain_reference_invalid")
    return {"path": path, "sha256": digest, "size_bytes": size}


def _run(value: Any) -> None:
    if not isinstance(value, Mapping) or set(value) != {
        "run_id", "run_context_sha256", "dag_sha256", "integration_manifest",
    }:
        raise ValueError("interface_validation_domain_run_invalid")
    if (
        not isinstance(value.get("run_id"), str) or not value["run_id"]
        or not is_sha256(value.get("run_context_sha256"))
        or not is_sha256(value.get("dag_sha256"))
    ):
        raise ValueError("interface_validation_domain_run_invalid")
    artifact_reference(value.get("integration_manifest"))


def _rust_project_ir(value: Any) -> None:
    if not isinstance(value, Mapping) or set(value) != {
        "reference", "ir_sha256", "interface_sha256", "binding_sha256",
    } or not all(is_sha256(value.get(key)) for key in (
        "ir_sha256", "interface_sha256", "binding_sha256",
    )):
        raise ValueError("interface_validation_domain_ir_invalid")
    artifact_reference(value.get("reference"))


def _source_domain(value: Any) -> None:
    keys = {
        "domain_sha256", "source_repository_binding_sha256", "dag_sha256",
        "build_ir_set_sha256", "build_ir_count", "translation_unit_count",
        "candidate_source_set_sha256", "candidate_count",
    }
    if not isinstance(value, Mapping) or set(value) != keys:
        raise ValueError("interface_validation_domain_sources_invalid")
    hashes = keys - {"build_ir_count", "translation_unit_count", "candidate_count"}
    counts = ("build_ir_count", "translation_unit_count", "candidate_count")
    if (
        any(not is_sha256(value.get(key)) for key in hashes)
        or any(type(value.get(key)) is not int or value[key] <= 0 for key in counts)
    ):
        raise ValueError("interface_validation_domain_sources_invalid")


def _candidate_set(value: Any) -> None:
    if not isinstance(value, Mapping) or set(value) != {
        "sha256", "manifest_sha256", "scope", "member_count",
    } or not all(is_sha256(value.get(key)) for key in (
        "sha256", "manifest_sha256",
    )) or value.get("scope") not in {"project-final", "wave-provisional"} or (
        type(value.get("member_count")) is not int or value["member_count"] <= 0
    ):
        raise ValueError("interface_validation_domain_candidate_set_invalid")


def _candidate_verification(value: Any) -> None:
    if not isinstance(value, Mapping) or set(value) != {
        "reference", "status", "verification_context_sha256",
        "generation_sha256", "cargo_fact_binding_sha256",
    } or value.get("status") != "candidate-verified" or not all(
        is_sha256(value.get(key)) for key in (
            "verification_context_sha256", "generation_sha256",
            "cargo_fact_binding_sha256",
        )
    ):
        raise ValueError("interface_validation_domain_b2a_invalid")
    artifact_reference(value.get("reference"))


def _clang_toolchain(value: Any) -> None:
    if not isinstance(value, Mapping) or set(value) != {
        "receipt", "receipt_sha256", "portable_binding_sha256", "target",
        "binary_sha256",
    }:
        raise ValueError("interface_validation_domain_clang_invalid")
    receipt = validate_clang_toolchain_receipt(value.get("receipt"))
    portable = receipt["portable_binding"]
    if (
        value.get("receipt_sha256") != receipt["receipt_sha256"]
        or value.get("portable_binding_sha256") != portable["binding_sha256"]
        or value.get("target") != portable["target"]["value"]
        or value.get("binary_sha256") != portable["binary"]["sha256"]
    ):
        raise ValueError("interface_validation_domain_clang_invalid")


def _clang_plans(value: Any) -> None:
    if not isinstance(value, Mapping) or set(value) != {
        "plan_count", "translation_unit_count", "plan_set_sha256",
        "target_context_set_sha256",
    } or any(type(value.get(key)) is not int or value[key] <= 0 for key in (
        "plan_count", "translation_unit_count",
    )) or not all(is_sha256(value.get(key)) for key in (
        "plan_set_sha256", "target_context_set_sha256",
    )):
        raise ValueError("interface_validation_domain_clang_plans_invalid")
    if value["plan_count"] != value["translation_unit_count"] * 2:
        raise ValueError("interface_validation_domain_clang_plan_coverage_invalid")


__all__ = [
    "CLAIM_BOUNDARY", "DOMAIN_KIND", "DOMAIN_SCOPE", "artifact_reference",
    "validate_project_interface_validation_domain",
]
