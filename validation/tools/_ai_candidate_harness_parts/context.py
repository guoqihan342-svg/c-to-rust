from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .context_artifacts import (
    CONTEXT_ARTIFACT_SUFFIXES,
    MAX_ARTIFACT_BYTES,
    load_context_artifacts as _load_context_artifacts,
)
from .context_compile import build_compile_context
from .context_scope import value_has_facts
from .context_security import (
    atomic_write_bytes,
    atomic_write_json,
    bounded_value,
    canonical_json_bytes,
    is_absolute_any_platform,
    sanitize_value as _sanitize_value,
    sensitive_key,
    sha256_bytes,
    sha256_path,
)
from .context_source import build_source_context


MAX_CONTEXT_BYTES = 128_000
MAX_SLICE_SPEC_BYTES = 4 * 1024 * 1024
MAX_BOUNDARY_CONTEXT_BYTES = 16_000


def build_context_pack(
    slice_spec_path: Path,
    *,
    source_root: Path | None = None,
    deterministic_evidence_dir: Path | None = None,
) -> dict[str, Any]:
    spec_bytes = slice_spec_path.read_bytes()
    if len(spec_bytes) > MAX_SLICE_SPEC_BYTES:
        raise ValueError(f"slice spec exceeds {MAX_SLICE_SPEC_BYTES} bytes")
    spec = json.loads(spec_bytes.decode("utf-8-sig"))
    if not isinstance(spec, dict):
        raise ValueError("slice spec must be a JSON object")
    target_id = required_string(spec, "target_id")
    slice_id = required_string(spec, "slice_id")
    function_name = required_string(spec, "function_name")
    resolved_source_root, source_root_status = resolve_source_root(
        slice_spec_path,
        spec,
        explicit_source_root=source_root,
    )
    declared_root = source_root_from_spec(spec)
    known_roots = tuple(
        value
        for value in (
            str(resolved_source_root) if resolved_source_root is not None else None,
            declared_root if declared_root and is_absolute_any_platform(declared_root) else None,
        )
        if value
    )

    source_context, source_file = build_source_context(
        spec,
        source_root=resolved_source_root,
        known_roots=known_roots,
    )
    compile_context = build_compile_context(
        spec,
        source_root=resolved_source_root,
        source_file=source_file,
        known_roots=known_roots,
    )
    raw_c_boundary = spec.get("c_boundary", {})
    c_boundary = boundary_context(
        raw_c_boundary,
        keys=(
            "files",
            "functions",
            "signatures",
            "direct_dependencies",
            "external_direct_callees",
            "call_expression_contract",
            "scalar_arithmetic_contract",
            "target_abi_contract",
        ),
        known_roots=known_roots,
    )
    bind_required_callee_sections(c_boundary, raw_c_boundary)
    rust_boundary = boundary_context(
        spec.get("rust_boundary", {}),
        keys=("crate", "module", "public_api", "raw_pointer_policy", "unsafe_policy"),
        known_roots=known_roots,
    )
    artifacts = load_context_artifacts(deterministic_evidence_dir, known_roots)
    context: dict[str, Any] = {
        "schema_version": 3,
        "target_id": target_id,
        "slice_id": slice_id,
        "function_name": function_name,
        "source_root": {"status": source_root_status, "path": "<source-root>" if resolved_source_root else None},
        "source": source_context,
        "compile_context": compile_context,
        "c_boundary": c_boundary,
        "rust_boundary": rust_boundary,
        "deterministic_artifacts": artifacts,
        "bindings": {
            "slice_spec_sha256": sha256_bytes(spec_bytes),
            "slice_spec": {
                "path": slice_spec_path.name,
                "sha256": sha256_bytes(spec_bytes),
                "size_bytes": len(spec_bytes),
            },
            "inputs": collect_input_bindings(source_context, compile_context, artifacts),
        },
        "claim_boundary": {
            "semantic_gate": False,
            "translation_coverage_numerator": 0,
            "note": "ContextPack is bounded model input and provenance only.",
        },
    }
    context["bindings"]["context_payload_hash_scope"] = "canonical_context_without_context_payload_sha256"
    enforce_context_budget(context)
    payload_without_self_hash = canonical_json_bytes(context)
    context["bindings"]["context_payload_sha256"] = sha256_bytes(payload_without_self_hash)
    encoded = canonical_json_bytes(context)
    if len(encoded) > MAX_CONTEXT_BYTES:
        raise ValueError(f"AI ContextPack exceeds {MAX_CONTEXT_BYTES} bytes")
    return context


def resolve_source_root(
    slice_spec_path: Path,
    spec: dict[str, Any],
    *,
    explicit_source_root: Path | None,
) -> tuple[Path | None, str]:
    if explicit_source_root is not None:
        resolved = explicit_source_root.resolve()
        if not resolved.is_dir():
            raise ValueError("explicit source root must be an existing directory")
        return resolved, "explicit"
    declared = source_root_from_spec(spec)
    if not declared or declared.startswith("<"):
        return None, "unavailable"
    declared_path = Path(declared)
    if declared_path.is_absolute() or ".." in declared_path.parts:
        return None, "rejected_untrusted_absolute_or_parent_path"
    repo_root = discover_repo_root(slice_spec_path)
    if repo_root is None:
        return None, "repository_root_unavailable"
    resolved = (repo_root / declared_path).resolve()
    try:
        resolved.relative_to(repo_root.resolve())
    except ValueError:
        return None, "rejected_path_outside_repository"
    if not resolved.is_dir():
        return None, "declared_source_root_missing"
    return resolved, "slice_spec_relative"


def discover_repo_root(path: Path) -> Path | None:
    for parent in (path.resolve().parent, *path.resolve().parents):
        if (parent / ".git").exists():
            return parent
    return None


def boundary_context(
    value: Any,
    *,
    keys: tuple[str, ...],
    known_roots: tuple[str, ...],
) -> dict[str, Any]:
    if not isinstance(value, dict):
        value = {}
    selected = {key: value[key] for key in keys if key in value}
    sanitized = sanitize_value(selected, known_roots)
    payload, truncated = bounded_value(sanitized, max_bytes=MAX_BOUNDARY_CONTEXT_BYTES)
    return {
        "sha256": sha256_bytes(canonical_json_bytes(sanitized)),
        "truncated": truncated,
        "payload": payload,
    }


def bind_required_callee_sections(boundary: dict[str, Any], raw_value: Any) -> None:
    raw_boundary = raw_value if isinstance(raw_value, dict) else {}
    required = [
        key
        for key in ("external_direct_callees", "call_expression_contract")
        if value_has_facts(raw_boundary.get(key))
    ]
    payload = boundary.get("payload")
    missing = [
        key
        for key in required
        if not isinstance(payload, dict) or not value_has_facts(payload.get(key))
    ]
    if required and boundary.get("truncated") is True:
        missing.append("c_boundary_truncated")
    boundary["required_callee_sections"] = required
    boundary["missing_required_callee_sections"] = missing


def collect_input_bindings(
    source_context: dict[str, Any],
    compile_context: dict[str, Any],
    artifacts: dict[str, Any],
) -> list[dict[str, Any]]:
    bindings: list[dict[str, Any]] = []
    source_input = source_context.get("input")
    if isinstance(source_input, dict):
        bindings.append({"kind": "source_file", **source_input})
    compile_input = compile_context.get("input")
    if isinstance(compile_input, dict):
        bindings.append({"kind": "compile_commands", **compile_input})
    selected_entry = compile_context.get("selected_entry")
    response_files = selected_entry.get("response_files") if isinstance(selected_entry, dict) else None
    response_file_items = response_files.get("files") if isinstance(response_files, dict) else None
    if isinstance(response_file_items, list):
        for response_file in response_file_items:
            if isinstance(response_file, dict):
                bindings.append({"kind": "compile_response_file", **response_file})
    for name, artifact in sorted(artifacts.items()):
        artifact_input = artifact.get("input") if isinstance(artifact, dict) else None
        if isinstance(artifact_input, dict):
            bindings.append({"kind": "deterministic_artifact", "name": name, **artifact_input})
    return sorted(bindings, key=lambda item: (str(item.get("kind")), str(item.get("path")), str(item.get("name", ""))))


def enforce_context_budget(context: dict[str, Any]) -> None:
    if len(canonical_json_bytes(context)) <= MAX_CONTEXT_BYTES - 256:
        return
    artifacts = context.get("deterministic_artifacts")
    if isinstance(artifacts, dict):
        for artifact in artifacts.values():
            if isinstance(artifact, dict):
                artifact.pop("context_excerpt", None)
                artifact.pop("context_excerpt_truncated", None)
    if len(canonical_json_bytes(context)) <= MAX_CONTEXT_BYTES - 256:
        return
    for key in ("c_boundary", "rust_boundary"):
        boundary = context.get(key)
        if isinstance(boundary, dict):
            boundary["payload"] = {"status": "omitted_for_context_budget"}
            boundary["truncated"] = True
            if key == "c_boundary" and boundary.get("required_callee_sections"):
                missing = set(boundary.get("missing_required_callee_sections", []))
                missing.update(boundary["required_callee_sections"])
                missing.add("c_boundary_truncated")
                boundary["missing_required_callee_sections"] = sorted(missing)
    if len(canonical_json_bytes(context)) > MAX_CONTEXT_BYTES - 256:
        raise ValueError(f"AI ContextPack exceeds {MAX_CONTEXT_BYTES} bytes")


def source_root_from_spec(spec: dict[str, Any]) -> str | None:
    value = spec.get("source_root")
    if not isinstance(value, str):
        source = spec.get("source")
        value = source.get("source_root") if isinstance(source, dict) else None
    return value if isinstance(value, str) and value else None


def sanitize_value(value: Any, source_root: str | Path | tuple[str, ...] | None = None) -> Any:
    return _sanitize_value(value, normalize_roots(source_root))


def load_context_artifacts(
    directory: Path | None,
    source_root: str | Path | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    return _load_context_artifacts(directory, normalize_roots(source_root))


def normalize_roots(value: str | Path | tuple[str, ...] | None) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, tuple):
        return tuple(str(item) for item in value if item)
    return (str(value),)


def required_string(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"slice spec requires non-empty {field}")
    return value


__all__ = [
    "MAX_ARTIFACT_BYTES",
    "MAX_CONTEXT_BYTES",
    "CONTEXT_ARTIFACT_SUFFIXES",
    "atomic_write_bytes",
    "atomic_write_json",
    "build_context_pack",
    "canonical_json_bytes",
    "load_context_artifacts",
    "sanitize_value",
    "sensitive_key",
    "sha256_bytes",
    "sha256_path",
]
