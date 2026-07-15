from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .artifacts import canonical_json_bytes, content_sha256
from .build_ir import is_sha256, stable_build_id, validate_artifact_reference
from .build_ir_external_dependencies import NATIVE_DEPENDENCY_KIND
from .build_ir_validation import validate_build_ir


NATIVE_LINK_CONTEXT_SCHEMA_VERSION = 1
NATIVE_LINK_CONTEXT_KIND = "native-link-model-context"
_PROFILE_VALUES = {"competition", "development"}
_PORTABLE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_+.-]{0,126}\Z")
_TOP_KEYS = {
    "schema_version", "artifact_kind", "status", "profile",
    "build_ir_binding", "requirements", "requirement_count",
    "dependency_count", "model_policy", "claim_boundary", "context_sha256",
}
_BINDING_KEYS = {
    "artifact", "semantic_sha256", "toolchain_abi_sha256",
    "toolchain_record_count", "abi_fact_count",
}
_REQUIREMENT_KEYS = {
    "requirement_id", "portable_name", "library_format",
    "dependency_count", "dependency_set_sha256", "consumer_target_count",
    "consumer_target_set_sha256",
}
_MODEL_POLICY = {
    "input_scope": "grouped-portable-native-identities",
    "allowed_strategies": ["defer", "ffi-boundary", "rustc-link-lib"],
    "absolute_paths_allowed": False,
    "model_may_claim_resolved": False,
}
_MODEL_CONTEXT_KEYS = {
    "schema_version", "artifact_kind", "profile", "context_sha256",
    "toolchain_abi_sha256", "requirements", "model_policy",
}


def build_native_link_context(
    build_ir: Mapping[str, Any], build_ir_reference: Mapping[str, Any], *,
    profile: str,
) -> dict[str, Any]:
    """Build a compact model context without exposing host library paths."""
    validate_artifact_reference(
        build_ir_reference, "native_link_build_ir_reference_invalid",
    )
    if profile not in _PROFILE_VALUES:
        raise ValueError("native_link_profile_invalid")
    requirements = native_link_requirements(build_ir)
    dependency_count = sum(item["dependency_count"] for item in requirements)
    payload = {
        "schema_version": NATIVE_LINK_CONTEXT_SCHEMA_VERSION,
        "artifact_kind": NATIVE_LINK_CONTEXT_KIND,
        "status": "planning-required" if requirements else "not-required",
        "profile": profile,
        "build_ir_binding": {
            "artifact": dict(build_ir_reference),
            "semantic_sha256": build_ir["semantic_sha256"],
            "toolchain_abi_sha256": content_sha256({
                "toolchains": build_ir["toolchains"],
                "abi_facts": build_ir["abi_facts"],
            }),
            "toolchain_record_count": len(build_ir["toolchains"]),
            "abi_fact_count": len(build_ir["abi_facts"]),
        },
        "requirements": requirements,
        "requirement_count": len(requirements),
        "dependency_count": dependency_count,
        "model_policy": dict(_MODEL_POLICY),
        "claim_boundary": _claim_boundary(requirements),
    }
    payload["context_sha256"] = content_sha256(payload)
    validate_native_link_context(payload)
    return payload


def validate_native_link_context(value: Mapping[str, Any]) -> None:
    if not isinstance(value, Mapping) or set(value) != _TOP_KEYS:
        raise ValueError("native_link_context_schema_invalid")
    if (
        value.get("schema_version") != NATIVE_LINK_CONTEXT_SCHEMA_VERSION
        or value.get("artifact_kind") != NATIVE_LINK_CONTEXT_KIND
        or value.get("profile") not in _PROFILE_VALUES
    ):
        raise ValueError("native_link_context_identity_invalid")
    binding = value.get("build_ir_binding")
    if not isinstance(binding, Mapping) or set(binding) != _BINDING_KEYS:
        raise ValueError("native_link_context_binding_invalid")
    validate_artifact_reference(
        binding.get("artifact"), "native_link_context_binding_invalid",
    )
    for field in ("semantic_sha256", "toolchain_abi_sha256"):
        if not is_sha256(binding.get(field)):
            raise ValueError("native_link_context_binding_invalid")
    for field in ("toolchain_record_count", "abi_fact_count"):
        count = binding.get(field)
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError("native_link_context_binding_invalid")
    requirements = validate_native_link_requirements(value.get("requirements"))
    dependency_count = sum(item["dependency_count"] for item in requirements)
    if (
        value.get("requirement_count") != len(requirements)
        or value.get("dependency_count") != dependency_count
        or value.get("status")
        != ("planning-required" if requirements else "not-required")
        or value.get("model_policy") != _MODEL_POLICY
        or value.get("claim_boundary") != _claim_boundary(requirements)
    ):
        raise ValueError("native_link_context_summary_invalid")
    claimed = value.get("context_sha256")
    projection = {key: item for key, item in value.items() if key != "context_sha256"}
    if not is_sha256(claimed) or content_sha256(projection) != claimed:
        raise ValueError("native_link_context_sha256_drift")


def reopen_native_link_context(
    value: Mapping[str, Any], artifact_root: Path,
) -> dict[str, Any]:
    from .orchestration_facts import read_artifact_reference

    validate_native_link_context(value)
    reference = value["build_ir_binding"]["artifact"]
    raw = read_artifact_reference(Path(artifact_root), reference)
    try:
        build_ir = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("native_link_bound_build_ir_invalid") from error
    if not isinstance(build_ir, dict) or canonical_json_bytes(build_ir) != raw:
        raise ValueError("native_link_bound_build_ir_noncanonical")
    expected = build_native_link_context(
        build_ir, reference, profile=str(value["profile"]),
    )
    if canonical_json_bytes(value) != canonical_json_bytes(expected):
        raise ValueError("native_link_context_build_ir_drift")
    return {
        "schema_version": 1,
        "status": "bound",
        "context_sha256": value["context_sha256"],
        "requirement_count": value["requirement_count"],
        "dependency_count": value["dependency_count"],
        "semantic_gate": False,
    }


def model_native_link_context(value: Mapping[str, Any]) -> dict[str, Any]:
    """Return only the grouped facts that a model needs for strategy selection."""
    validate_native_link_context(value)
    return validate_model_native_link_context({
        "schema_version": value["schema_version"],
        "artifact_kind": value["artifact_kind"],
        "profile": value["profile"],
        "context_sha256": value["context_sha256"],
        "toolchain_abi_sha256": value["build_ir_binding"][
            "toolchain_abi_sha256"
        ],
        "requirements": [dict(item) for item in value["requirements"]],
        "model_policy": dict(value["model_policy"]),
    })


def validate_model_native_link_context(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _MODEL_CONTEXT_KEYS:
        raise ValueError("native_link_model_context_schema_invalid")
    result = dict(value)
    requirements = validate_native_link_requirements(result.get("requirements"))
    if (
        result.get("schema_version") != NATIVE_LINK_CONTEXT_SCHEMA_VERSION
        or result.get("artifact_kind") != NATIVE_LINK_CONTEXT_KIND
        or result.get("profile") not in _PROFILE_VALUES
        or not is_sha256(result.get("context_sha256"))
        or not is_sha256(result.get("toolchain_abi_sha256"))
        or result.get("model_policy") != _MODEL_POLICY
    ):
        raise ValueError("native_link_model_context_invalid")
    return {
        **result,
        "requirements": requirements,
        "model_policy": dict(_MODEL_POLICY),
    }


def native_link_requirements(
    build_irs: Mapping[str, Any] | Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    values = [build_irs] if isinstance(build_irs, Mapping) else list(build_irs)
    grouped: dict[tuple[str, str], dict[str, set[str]]] = defaultdict(
        lambda: {"dependencies": set(), "consumers": set()},
    )
    for build_ir in values:
        validate_build_ir(build_ir)
        semantic_sha256 = str(build_ir["semantic_sha256"])
        for dependency in build_ir["external_dependencies"]:
            if dependency.get("kind") != NATIVE_DEPENDENCY_KIND:
                continue
            key = (str(dependency["name"]), str(dependency["format"]))
            grouped[key]["dependencies"].add(stable_build_id(
                "native-link-member",
                {
                    "build_ir_semantic_sha256": semantic_sha256,
                    "dependency_id": dependency["dependency_id"],
                },
            ))
            grouped[key]["consumers"].update(
                stable_build_id("native-link-consumer", {
                    "build_ir_semantic_sha256": semantic_sha256,
                    "target_id": item,
                })
                for item in dependency["consumer_target_ids"]
            )
    result = []
    for (name, library_format), members in grouped.items():
        dependencies = sorted(members["dependencies"])
        consumers = sorted(members["consumers"])
        identity = {"portable_name": name, "library_format": library_format}
        result.append({
            "requirement_id": stable_build_id("native-link-requirement", identity),
            **identity,
            "dependency_count": len(dependencies),
            "dependency_set_sha256": content_sha256(dependencies),
            "consumer_target_count": len(consumers),
            "consumer_target_set_sha256": content_sha256(consumers),
        })
    return sorted(result, key=lambda item: item["requirement_id"])


def validate_native_link_requirements(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("native_link_context_requirements_invalid")
    normalized = [_validate_requirement(item) for item in value]
    if normalized != value or value != sorted(
        value, key=lambda item: item["requirement_id"],
    ):
        raise ValueError("native_link_context_requirements_noncanonical")
    identities = [item["requirement_id"] for item in value]
    if len(identities) != len(set(identities)):
        raise ValueError("native_link_context_requirement_duplicate")
    return normalized


def _claim_boundary(requirements: list[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "artifact_role": "native-link-planning-context",
        "native_link_config_resolved": not requirements,
        "cargo_executed": False,
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
    }


def _validate_requirement(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _REQUIREMENT_KEYS:
        raise ValueError("native_link_context_requirement_invalid")
    result = dict(value)
    name = result.get("portable_name")
    library_format = result.get("library_format")
    expected_id = stable_build_id("native-link-requirement", {
        "portable_name": name, "library_format": library_format,
    })
    if (
        not isinstance(name, str) or _PORTABLE_NAME.fullmatch(name) is None
        or library_format not in {
            "shared-library", "static-archive", "import-or-static-library",
        }
        or result.get("requirement_id") != expected_id
    ):
        raise ValueError("native_link_context_requirement_invalid")
    for field in ("dependency_count", "consumer_target_count"):
        count = result.get(field)
        if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
            raise ValueError("native_link_context_requirement_invalid")
    for field in ("dependency_set_sha256", "consumer_target_set_sha256"):
        if not is_sha256(result.get(field)):
            raise ValueError("native_link_context_requirement_invalid")
    return result


__all__ = [
    "NATIVE_LINK_CONTEXT_KIND", "NATIVE_LINK_CONTEXT_SCHEMA_VERSION",
    "build_native_link_context", "model_native_link_context",
    "native_link_requirements", "reopen_native_link_context",
    "validate_model_native_link_context", "validate_native_link_context",
    "validate_native_link_requirements",
]
