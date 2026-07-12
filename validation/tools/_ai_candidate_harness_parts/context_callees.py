from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

from .context_callee_behavior import (
    source_backed_behavior,
    source_behavior_disagrees_with_fixture,
)
from .context_security import logical_path, redact_text, sha256_bytes, sha256_path
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
    if not isinstance(declared, list) or not declared:
        return _context("not_applicable", [], [], [], [])
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
        blocks=blocks,
        source_root=source_root,
        known_roots=known_roots,
    )
    if source_behavior_disagrees_with_fixture(spec, behavior_rules):
        behavior_blocked.append({"reason": "source_behavior_expected_output_mismatch"})
    blocked.extend(behavior_blocked)
    status = "bound" if blocks and not blocked else "partial" if blocks else "unavailable"
    return _context(status, blocks, blocked, dependencies, behavior_rules)


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

    resolved_root = source_root.resolve()
    resolved = (resolved_root / PurePosixPath(source_path)).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as error:
        raise ValueError("source_path_outside_root") from error
    if not resolved.is_file():
        raise ValueError("source_file_missing")
    if resolved.stat().st_size > MAX_CALLEE_FILE_BYTES:
        raise ValueError("source_file_exceeds_limit")

    full_sha256 = sha256_path(resolved)
    if full_sha256 != declared_sha256:
        raise ValueError("source_file_sha256_mismatch")
    try:
        text = resolved.read_text(encoding="utf-8-sig")
    except UnicodeError as error:
        raise ValueError("source_file_not_utf8") from error
    try:
        extracted = extract_function(text, name)
    except SystemExit as error:
        raise ValueError("callee_definition_not_found") from error
    if sha256_path(resolved) != full_sha256:
        raise ValueError("source_file_changed_during_read")

    content_bytes = extracted.c_source.encode("utf-8")
    if len(content_bytes) > MAX_CALLEE_BLOCK_BYTES:
        raise ValueError("callee_definition_exceeds_limit")
    redacted = redact_text(extracted.c_source, known_roots)
    return {
        "callee": name,
        "source_ref": source_ref,
        "definition_status": item.get("definition_status"),
        "source_file": {
            "path": logical_path(resolved_root, resolved),
            "sha256": full_sha256,
            "size_bytes": resolved.stat().st_size,
        },
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
