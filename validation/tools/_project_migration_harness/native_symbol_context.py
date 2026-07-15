from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
import re
from typing import Any

from .artifacts import canonical_json_bytes, content_sha256
from .build_ir import is_sha256, stable_build_id
from .native_link_context import validate_native_link_context
from .native_link_model import (
    validate_native_link_candidate, validate_native_link_proposal,
)
from .rust_project_ir_validation import validate_rust_project_ir


NATIVE_SYMBOL_CONTEXT_KIND = "native-symbol-model-context"
_TOP_KEYS = {
    "schema_version", "artifact_kind", "status", "profile", "bindings",
    "symbols", "symbol_count", "providers", "provider_count",
    "model_policy", "claim_boundary", "context_sha256",
}
_BINDING_KEYS = {
    "rust_project_ir_sha256", "native_link_context_sha256",
    "native_link_candidate_sha256",
}
_SYMBOL_KEYS = {
    "symbol_id", "link_name", "abi", "declaration_count",
    "declaration_set_sha256",
}
_PROVIDER_KEYS = {
    "requirement_id", "portable_name", "library_format", "strategy",
    "rustc_link_name", "rustc_link_kind",
}
_MODEL_POLICY = {
    "input_scope": "grouped-rust-ffi-imports-and-native-requirements",
    "allowed_provider_kinds": ["defer", "native-requirement", "runtime"],
    "exact_symbol_coverage_required": True,
    "invented_symbols_allowed": False,
    "model_may_claim_resolved": False,
}
_CLAIM_BOUNDARY = {
    "artifact_role": "native-symbol-planning-context",
    "symbol_assignments_resolved": False,
    "native_exports_verified": False,
    "semantic_gate": False,
    "translation_coverage_numerator": 0,
}
_PORTABLE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_+.-]{0,126}\Z", re.ASCII)


def build_native_symbol_context(
    rust_project_ir: Mapping[str, Any],
    native_link_context: Mapping[str, Any],
    native_link_candidate: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a path-free AI context for bounded FFI symbol attribution."""
    _validate_inputs(
        rust_project_ir, native_link_context, native_link_candidate,
    )
    symbols = _imported_symbols(rust_project_ir)
    providers = _providers(native_link_context, native_link_candidate)
    payload = {
        "schema_version": 1,
        "artifact_kind": NATIVE_SYMBOL_CONTEXT_KIND,
        "status": "planning-required" if symbols else "not-required",
        "profile": native_link_context["profile"],
        "bindings": {
            "rust_project_ir_sha256": rust_project_ir["ir_sha256"],
            "native_link_context_sha256": native_link_context["context_sha256"],
            "native_link_candidate_sha256": native_link_candidate[
                "candidate_sha256"
            ],
        },
        "symbols": symbols,
        "symbol_count": len(symbols),
        "providers": providers,
        "provider_count": len(providers),
        "model_policy": dict(_MODEL_POLICY),
        "claim_boundary": dict(_CLAIM_BOUNDARY),
    }
    payload["context_sha256"] = content_sha256(payload)
    validate_native_symbol_context(payload)
    return payload


def validate_native_symbol_context(
    value: Any,
    rust_project_ir: Mapping[str, Any] | None = None,
    native_link_context: Mapping[str, Any] | None = None,
    native_link_candidate: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _TOP_KEYS:
        raise ValueError("native_symbol_context_schema_invalid")
    bindings = value.get("bindings")
    if not isinstance(bindings, Mapping) or set(bindings) != _BINDING_KEYS:
        raise ValueError("native_symbol_context_binding_invalid")
    if any(not is_sha256(bindings.get(field)) for field in _BINDING_KEYS):
        raise ValueError("native_symbol_context_binding_invalid")
    symbols = _validate_symbols(value.get("symbols"))
    providers = _validate_providers(value.get("providers"))
    if (
        value.get("schema_version") != 1
        or value.get("artifact_kind") != NATIVE_SYMBOL_CONTEXT_KIND
        or value.get("profile") not in {"competition", "development"}
        or value.get("status")
        != ("planning-required" if symbols else "not-required")
        or value.get("symbol_count") != len(symbols)
        or value.get("provider_count") != len(providers)
        or value.get("model_policy") != _MODEL_POLICY
        or value.get("claim_boundary") != _CLAIM_BOUNDARY
    ):
        raise ValueError("native_symbol_context_summary_invalid")
    claimed = value.get("context_sha256")
    projection = {key: item for key, item in value.items() if key != "context_sha256"}
    if not is_sha256(claimed) or claimed != content_sha256(projection):
        raise ValueError("native_symbol_context_sha256_drift")
    if rust_project_ir is not None:
        if native_link_context is None or native_link_candidate is None:
            raise ValueError("native_symbol_context_reopen_inputs_incomplete")
        expected = build_native_symbol_context(
            rust_project_ir, native_link_context, native_link_candidate,
        )
        if canonical_json_bytes(value) != canonical_json_bytes(expected):
            raise ValueError("native_symbol_context_input_drift")
    return {
        **dict(value), "bindings": dict(bindings),
        "symbols": symbols, "providers": providers,
    }


def model_native_symbol_context(value: Mapping[str, Any]) -> dict[str, Any]:
    validated = validate_native_symbol_context(value)
    return {
        "schema_version": 1,
        "artifact_kind": NATIVE_SYMBOL_CONTEXT_KIND,
        "profile": validated["profile"],
        "context_sha256": validated["context_sha256"],
        "symbols": validated["symbols"],
        "providers": validated["providers"],
        "model_policy": dict(_MODEL_POLICY),
    }


def _validate_inputs(
    rust_project_ir: Mapping[str, Any],
    native_link_context: Mapping[str, Any],
    native_link_candidate: Mapping[str, Any],
) -> None:
    validate_rust_project_ir(rust_project_ir)
    validate_native_link_context(native_link_context)
    validate_native_link_candidate(native_link_candidate, native_link_context)
    if native_link_context["build_ir_binding"]["artifact"] not in (
        rust_project_ir["bindings"]["build_ir"]
    ):
        raise ValueError("native_symbol_context_build_ir_binding_mismatch")
    if canonical_json_bytes(native_link_context["requirements"]) != (
        canonical_json_bytes(rust_project_ir["native_link_requirements"])
    ):
        raise ValueError("native_symbol_context_requirement_mismatch")


def _imported_symbols(value: Mapping[str, Any]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], set[str]] = defaultdict(set)
    for item in value["ffi_boundaries"]:
        direction = item["direction"]
        if direction not in {"import", "export", "import-export"}:
            raise ValueError("native_symbol_context_ffi_direction_invalid")
        if direction in {"import", "import-export"}:
            grouped[(item["link_name"], item["abi"])].add(
                item["declaration_id"],
            )
    result = []
    for (link_name, abi), declarations in grouped.items():
        _bounded_text(link_name, "link_name", 512)
        _bounded_text(abi, "abi", 64)
        identity = {"link_name": link_name, "abi": abi}
        result.append({
            "symbol_id": stable_build_id("native-symbol", identity),
            **identity,
            "declaration_count": len(declarations),
            "declaration_set_sha256": content_sha256(sorted(declarations)),
        })
    return sorted(result, key=lambda item: item["symbol_id"])


def _providers(
    context: Mapping[str, Any], candidate: Mapping[str, Any],
) -> list[dict[str, Any]]:
    proposals = {item["requirement_id"]: item for item in candidate["proposals"]}
    return [{
        "requirement_id": item["requirement_id"],
        "portable_name": item["portable_name"],
        "library_format": item["library_format"],
        "strategy": proposals[item["requirement_id"]]["strategy"],
        "rustc_link_name": proposals[item["requirement_id"]]["rustc_link_name"],
        "rustc_link_kind": proposals[item["requirement_id"]]["rustc_link_kind"],
    } for item in context["requirements"]]


def _validate_symbols(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("native_symbol_context_symbols_invalid")
    result = []
    for item in value:
        if not isinstance(item, Mapping) or set(item) != _SYMBOL_KEYS:
            raise ValueError("native_symbol_context_symbol_invalid")
        record = dict(item)
        identity = {
            "link_name": _bounded_text(record.get("link_name"), "link_name", 512),
            "abi": _bounded_text(record.get("abi"), "abi", 64),
        }
        if (
            record.get("symbol_id") != stable_build_id("native-symbol", identity)
            or type(record.get("declaration_count")) is not int
            or record["declaration_count"] <= 0
            or not is_sha256(record.get("declaration_set_sha256"))
        ):
            raise ValueError("native_symbol_context_symbol_invalid")
        result.append(record)
    if result != sorted(result, key=lambda item: item["symbol_id"]) or len({
        item["symbol_id"] for item in result
    }) != len(result):
        raise ValueError("native_symbol_context_symbols_noncanonical")
    return result


def _validate_providers(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("native_symbol_context_providers_invalid")
    result = []
    for item in value:
        if not isinstance(item, Mapping) or set(item) != _PROVIDER_KEYS:
            raise ValueError("native_symbol_context_provider_invalid")
        record = dict(item)
        proposal = {
            key: record[key] for key in (
                "requirement_id", "strategy", "rustc_link_name",
                "rustc_link_kind",
            )
        }
        if (
            not isinstance(record.get("portable_name"), str)
            or _PORTABLE_NAME.fullmatch(record["portable_name"]) is None
            or record.get("library_format") not in {
                "shared-library", "static-archive", "import-or-static-library",
            }
        ):
            raise ValueError("native_symbol_context_provider_invalid")
        expected_id = stable_build_id("native-link-requirement", {
            "portable_name": record["portable_name"],
            "library_format": record["library_format"],
        })
        if record.get("requirement_id") != expected_id:
            raise ValueError("native_symbol_context_provider_invalid")
        try:
            validate_native_link_proposal(proposal)
        except ValueError as error:
            raise ValueError("native_symbol_context_provider_invalid") from error
        result.append(record)
    if result != sorted(result, key=lambda item: item["requirement_id"]) or len({
        item["requirement_id"] for item in result
    }) != len(result):
        raise ValueError("native_symbol_context_providers_noncanonical")
    return result


def _bounded_text(value: Any, label: str, limit: int) -> str:
    if (
        not isinstance(value, str) or not value
        or len(value.encode("utf-8")) > limit
        or "/" in value or "\\" in value
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise ValueError(f"native_symbol_context_{label}_invalid")
    return value


__all__ = [
    "NATIVE_SYMBOL_CONTEXT_KIND", "build_native_symbol_context",
    "model_native_symbol_context", "validate_native_symbol_context",
]
