from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .context_security import bounded_value, compact_json_bytes, sanitize_value, sha256_bytes


MAX_ARTIFACT_BYTES = 32_000
MAX_ARTIFACT_CONTEXT_BYTES = 12_000
CONTEXT_ARTIFACT_SUFFIXES = (
    "-clang-lowering-report.json",
    "-type-map.json",
    "-cfg.json",
    "-pointer-graph.json",
    "-blocked-repairs.json",
)
FAILURE_KEYS = {
    "blocked",
    "blocked_reason",
    "diagnostic",
    "diagnostics",
    "error",
    "errors",
    "failure",
    "failures",
    "gap",
    "gaps",
    "reason",
    "root_cause",
    "root_causes",
    "status",
    "unsupported",
}
EXCERPT_KEYS = {
    "blocks",
    "call_edges",
    "edges",
    "fields",
    "nodes",
    "pointer_nodes",
    "records",
    "signatures",
    "typedefs",
    "types",
}


def load_context_artifacts(directory: Path | None, known_roots: tuple[str, ...]) -> dict[str, Any]:
    if directory is None or not directory.is_dir():
        return {}
    root = directory.resolve()
    artifacts: dict[str, Any] = {}
    for path in sorted(directory.glob("*.json"), key=lambda item: item.name):
        if not path.name.endswith(CONTEXT_ARTIFACT_SUFFIXES):
            continue
        try:
            resolved = path.resolve()
            resolved.relative_to(root)
        except (OSError, ValueError):
            artifacts[path.name] = {"status": "omitted_path_outside_evidence_root"}
            continue
        data = resolved.read_bytes()
        binding = {"path": path.name, "sha256": sha256_bytes(data), "size_bytes": len(data)}
        if len(data) > MAX_ARTIFACT_BYTES:
            artifacts[path.name] = {"status": "omitted_too_large", "input": binding}
            continue
        try:
            payload = json.loads(data.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            artifacts[path.name] = {"status": "omitted_invalid_json", "input": binding}
            continue
        sanitized = sanitize_value(payload, known_roots)
        failure_summary = collect_failure_summary(sanitized)
        excerpt_source = (
            {key: value for key, value in sanitized.items() if key in EXCERPT_KEYS}
            if isinstance(sanitized, dict)
            else {}
        )
        excerpt, truncated = bounded_value(excerpt_source, max_bytes=MAX_ARTIFACT_CONTEXT_BYTES // 2)
        result: dict[str, Any] = {
            "status": "loaded",
            "input": binding,
            "failure_summary": failure_summary,
        }
        if excerpt_source:
            result["context_excerpt"] = excerpt
            result["context_excerpt_truncated"] = truncated
        bounded, _ = bounded_value(result, max_bytes=MAX_ARTIFACT_CONTEXT_BYTES)
        if isinstance(bounded, dict) and "input" in bounded:
            result = bounded
        else:
            result.pop("context_excerpt", None)
            result.pop("context_excerpt_truncated", None)
            result["failure_summary"] = result["failure_summary"][:12]
        if len(compact_json_bytes(result)) > MAX_ARTIFACT_BYTES:
            raise ValueError("bounded deterministic artifact exceeded artifact limit")
        artifacts[path.name] = result
    return artifacts


def collect_failure_summary(value: Any, path: str = "$") -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        for key, item in sorted(value.items(), key=lambda pair: str(pair[0])):
            child_path = f"{path}.{key}"
            if str(key).lower() in FAILURE_KEYS and scalar_or_small_list(item):
                found.append({"path": child_path, "value": item})
            if len(found) < 24:
                found.extend(collect_failure_summary(item, child_path)[: 24 - len(found)])
    elif isinstance(value, list):
        for index, item in enumerate(value[:24]):
            if len(found) >= 24:
                break
            found.extend(collect_failure_summary(item, f"{path}[{index}]")[: 24 - len(found)])
    return found[:24]


def scalar_or_small_list(value: Any) -> bool:
    if value is None or isinstance(value, (str, int, float, bool)):
        return True
    return isinstance(value, list) and len(value) <= 12 and all(
        item is None or isinstance(item, (str, int, float, bool)) for item in value
    )
