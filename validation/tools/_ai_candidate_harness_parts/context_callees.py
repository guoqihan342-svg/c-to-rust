from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

from .context_callee_behavior import (
    source_backed_behavior,
    source_behavior_disagrees_with_fixture,
)
from .context_bound_source import (
    ensure_bound_source_unchanged,
    read_hash_bound_utf8_source,
    source_file_descriptor,
)
from .context_security import redact_text, sha256_bytes
from .context_source import bytes_hash_match_mode, expected_source_sha256, extract_span
from validation.tools.extract_source_slice import extract_function


MAX_CALLEE_BLOCKS = 24
MAX_CALLEE_FILE_BYTES = 4 * 1024 * 1024
MAX_CALLEE_BLOCK_BYTES = 16 * 1024
MAX_CALLEE_CONTEXT_BYTES = 48 * 1024
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def build_external_callee_source_context(
    spec: dict[str, Any],
    *,
    source_root: Path | None,
    known_roots: tuple[str, ...],
) -> dict[str, Any]:
    declared = spec.get("c_boundary", {}).get("external_direct_callees")
    target_block = _target_behavior_block(
        spec,
        source_root=source_root,
        known_roots=known_roots,
    )
    if not isinstance(declared, list) or not declared:
        dependencies, behavior_rules, behavior_blocked = source_backed_behavior(
            spec,
            blocks=[target_block] if target_block is not None else [],
            source_root=source_root,
            known_roots=known_roots,
        )
        if source_behavior_disagrees_with_fixture(spec, behavior_rules):
            behavior_blocked.append({"reason": "source_behavior_expected_output_mismatch"})
        return _context(
            "not_applicable",
            [],
            behavior_blocked,
            dependencies,
            behavior_rules,
        )
    if len(declared) > MAX_CALLEE_BLOCKS:
        return _context(
            "blocked",
            [],
            [{
                "reason": "callee_count_exceeds_limit",
                "declared_count": len(declared),
                "limit": MAX_CALLEE_BLOCKS,
            }],
            [],
            [],
        )

    blocks: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    total_bytes = 0
    for item in declared:
        if not isinstance(item, dict):
            blocked.append({"reason": "callee_declaration_invalid"})
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name:
            blocked.append({"reason": "callee_name_missing"})
            continue
        try:
            block = _source_block(
                item,
                name=name,
                source_root=source_root,
                known_roots=known_roots,
            )
        except ValueError as error:
            blocked.append({"callee": name, "reason": str(error)})
            continue
        total_bytes += block["source_span"]["size_bytes"]
        if total_bytes > MAX_CALLEE_CONTEXT_BYTES:
            blocked.append({
                "callee": name,
                "reason": "callee_context_exceeds_total_limit",
                "limit": MAX_CALLEE_CONTEXT_BYTES,
            })
            continue
        blocks.append(block)

    dependencies, behavior_rules, behavior_blocked = source_backed_behavior(
        spec,
        blocks=[*blocks, *([target_block] if target_block is not None else [])],
        source_root=source_root,
        known_roots=known_roots,
    )
    if source_behavior_disagrees_with_fixture(spec, behavior_rules):
        behavior_blocked.append({"reason": "source_behavior_expected_output_mismatch"})
    blocked.extend(behavior_blocked)
    status = "bound" if blocks and not blocked else "partial" if blocks else "unavailable"
    return _context(status, blocks, blocked, dependencies, behavior_rules)


def _target_behavior_block(
    spec: dict[str, Any],
    *,
    source_root: Path | None,
    known_roots: tuple[str, ...],
) -> dict[str, Any] | None:
    function_name = spec.get("function_name")
    signatures = spec.get("c_boundary", {}).get("signatures")
    if (
        source_root is None
        or not isinstance(function_name, str)
        or not isinstance(signatures, list)
    ):
        return None
    matching = [
        item
        for item in signatures
        if isinstance(item, dict)
        and item.get("function") == function_name
        and item.get("definition_status") == "real_source_bound"
        and isinstance(item.get("source_span"), dict)
    ]
    if len(matching) != 1:
        return None
    signature = matching[0]
    source_span = signature["source_span"]
    span_sha = source_span.get("sha256")
    if not isinstance(span_sha, str) or SHA256_RE.fullmatch(span_sha) is None:
        return None
    source_path_text = _normalized_declared_path(source_span.get("file"))
    if source_path_text is None:
        return None
    declared_file_sha = expected_source_sha256(spec, source_path_text)
    if not isinstance(declared_file_sha, str) or SHA256_RE.fullmatch(declared_file_sha) is None:
        return None
    try:
        bound = read_hash_bound_utf8_source(
            source_root,
            source_path_text,
            declared_file_sha,
            max_bytes=MAX_CALLEE_FILE_BYTES,
        )
    except ValueError:
        return None
    try:
        content_bytes, coordinates = extract_span(
            bound.path,
            source_span,
            signature.get("c_source"),
        )
    except ValueError:
        return None
    if len(content_bytes) > MAX_CALLEE_BLOCK_BYTES:
        return None
    content_sha = sha256_bytes(content_bytes)
    if bytes_hash_match_mode(content_bytes, span_sha, actual_sha256=content_sha) is None:
        return None
    try:
        content = content_bytes.decode("utf-8-sig")
    except UnicodeError:
        return None
    try:
        ensure_bound_source_unchanged(bound)
    except ValueError:
        return None
    redacted = redact_text(content, known_roots)
    return {
        "callee": function_name,
        "role": "target_function",
        "source_file": source_file_descriptor(bound),
        "source_span": {
            "content": redacted,
            "sha256": content_sha,
            "declared_sha256": span_sha,
            "size_bytes": len(content_bytes),
            "redacted": redacted != content,
            **coordinates,
        },
    }


def callee_source_input_bindings(context: dict[str, Any]) -> list[dict[str, Any]]:
    bindings = []
    for block in context.get("blocks", []):
        binding = _input_binding(block, "external_callee_source", "callee")
        if binding is not None:
            bindings.append(binding)
    for dependency in context.get("dependencies", []):
        binding = _input_binding(
            dependency,
            "external_callee_dependency_source",
            "symbol",
        )
        if binding is not None:
            bindings.append(binding)
    return bindings


def _input_binding(
    value: Any,
    kind: str,
    name_key: str,
) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    source_file = value.get("source_file")
    source_span = value.get("source_span")
    if not isinstance(source_file, dict) or not isinstance(source_span, dict):
        return None
    name = value.get(name_key)
    return {
        "kind": kind,
        "callee": name,
        "name": name,
        "path": source_file.get("path"),
        "sha256": source_file.get("sha256"),
        "declared_sha256": source_file.get("declared_sha256"),
        "hash_match_mode": source_file.get("hash_match_mode"),
        "source_span_sha256": source_span.get("sha256"),
        "line_start": source_span.get("line_start"),
        "line_end": source_span.get("line_end"),
    }


def _source_block(
    item: dict[str, Any],
    *,
    name: str,
    source_root: Path | None,
    known_roots: tuple[str, ...],
) -> dict[str, Any]:
    if source_root is None:
        raise ValueError("source_root_unavailable")
    source_ref = item.get("source_ref")
    if not isinstance(source_ref, str) or source_ref.count("#") != 1:
        raise ValueError("repository_source_ref_required")
    source_path_text, source_symbol = source_ref.split("#", 1)
    if source_symbol != name:
        raise ValueError("source_ref_symbol_mismatch")
    source_path = _relative_source_path(source_path_text)

    source_files = item.get("source_files")
    if not isinstance(source_files, list):
        raise ValueError("source_files_required")
    matching = [
        value
        for value in source_files
        if isinstance(value, dict)
        and _normalized_declared_path(value.get("path")) == source_path
    ]
    if len(matching) != 1:
        raise ValueError("source_ref_file_binding_ambiguous")
    declared_sha256 = matching[0].get("sha256")
    if not isinstance(declared_sha256, str) or SHA256_RE.fullmatch(declared_sha256) is None:
        raise ValueError("source_file_sha256_invalid")

    bound = read_hash_bound_utf8_source(
        source_root,
        source_path,
        declared_sha256,
        max_bytes=MAX_CALLEE_FILE_BYTES,
    )
    try:
        extracted = extract_function(bound.text, name)
    except SystemExit as error:
        raise ValueError("callee_definition_not_found") from error
    ensure_bound_source_unchanged(bound)

    content_bytes = extracted.c_source.encode("utf-8")
    if len(content_bytes) > MAX_CALLEE_BLOCK_BYTES:
        raise ValueError("callee_definition_exceeds_limit")
    redacted = redact_text(extracted.c_source, known_roots)
    return {
        "callee": name,
        "source_ref": source_ref,
        "definition_status": item.get("definition_status"),
        "source_file": source_file_descriptor(bound),
        "source_span": {
            "line_start": extracted.line_start,
            "line_end": extracted.line_end,
            "sha256": sha256_bytes(content_bytes),
            "size_bytes": len(content_bytes),
            "content": redacted,
            "redacted": redacted != extracted.c_source,
        },
        "allowed_use": "candidate_context_only",
        "semantics_verified": False,
    }


def _relative_source_path(value: Any) -> str:
    normalized = _normalized_declared_path(value)
    if normalized is None:
        raise ValueError("repository_source_path_required")
    return normalized


def _normalized_declared_path(value: Any) -> str | None:
    if not isinstance(value, str) or not value or "\\" in value or value.startswith("~"):
        return None
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        return None
    if ":" in path.parts[0]:
        return None
    return path.as_posix()


def _context(
    status: str,
    blocks: list[dict[str, Any]],
    blocked: list[dict[str, Any]],
    dependencies: list[dict[str, Any]],
    behavior_rules: list[dict[str, Any]],
) -> dict[str, Any]:
    behavior_payload = {
        "schema_version": 1,
        "scope": "source_backed_fixture_path",
        "rules": behavior_rules,
        "semantics_verified": False,
    }
    behavior_payload["behavior_sha256"] = sha256_bytes(_canonical_bytes(behavior_payload))
    return {
        "schema_version": 1,
        "status": status,
        "blocks": blocks,
        "blocked": blocked,
        "dependencies": dependencies,
        "source_backed_behavior": behavior_payload,
        "semantics_verified": False,
    }


def _canonical_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf-8")


__all__ = ["build_external_callee_source_context", "callee_source_input_bindings"]
