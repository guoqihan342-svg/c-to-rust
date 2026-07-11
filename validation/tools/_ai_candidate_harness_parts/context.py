from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any


MAX_CONTEXT_BYTES = 128_000
MAX_ARTIFACT_BYTES = 32_000
CONTEXT_ARTIFACT_SUFFIXES = (
    "-clang-lowering-report.json",
    "-type-map.json",
    "-cfg.json",
    "-pointer-graph.json",
    "-blocked-repairs.json",
)
SENSITIVE_KEY_PARTS = ("api_key", "apikey", "credential", "password", "secret", "token")
HOST_PATH_PATTERN = re.compile(r"(?i)(?:[a-z]:[\\/]|/mnt/[a-z]/|/home/|/root/)[^\s\"']+")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_path(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def atomic_write_json(path: Path, payload: Any) -> None:
    atomic_write_bytes(path, canonical_json_bytes(payload))


def build_context_pack(
    slice_spec_path: Path,
    *,
    deterministic_evidence_dir: Path | None = None,
) -> dict[str, Any]:
    spec_bytes = slice_spec_path.read_bytes()
    spec = json.loads(spec_bytes.decode("utf-8-sig"))
    if not isinstance(spec, dict):
        raise ValueError("slice spec must be a JSON object")
    target_id = required_string(spec, "target_id")
    slice_id = required_string(spec, "slice_id")
    source_root = source_root_from_spec(spec)
    context = {
        "schema_version": 1,
        "target_id": target_id,
        "slice_id": slice_id,
        "function_name": required_string(spec, "function_name"),
        "source": sanitize_value(
            {
                "c_source": spec.get("c_source", ""),
                "source_file": spec.get("source_file") or spec.get("source", {}).get("source_file"),
                "source_commit": spec.get("source_commit") or spec.get("source", {}).get("source_commit"),
                "function_source_span": spec.get("function_source_span"),
                "source_file_hashes": spec.get("source_file_hashes", {}),
            },
            source_root,
        ),
        "compile_context": sanitize_value(spec.get("build_profile", {}), source_root),
        "c_boundary": sanitize_value(spec.get("c_boundary", {}), source_root),
        "rust_boundary": sanitize_value(spec.get("rust_boundary", {}), source_root),
        "deterministic_artifacts": load_context_artifacts(deterministic_evidence_dir, source_root),
        "bindings": {
            "slice_spec_sha256": sha256_bytes(spec_bytes),
        },
        "claim_boundary": {
            "semantic_gate": False,
            "translation_coverage_numerator": 0,
            "note": "ContextPack is model input and provenance only.",
        },
    }
    encoded = canonical_json_bytes(context)
    if len(encoded) > MAX_CONTEXT_BYTES:
        raise ValueError(f"AI ContextPack exceeds {MAX_CONTEXT_BYTES} bytes")
    context["bindings"]["context_payload_sha256"] = sha256_bytes(encoded)
    return context


def load_context_artifacts(directory: Path | None, source_root: str | None) -> dict[str, Any]:
    if directory is None or not directory.is_dir():
        return {}
    artifacts: dict[str, Any] = {}
    for path in sorted(directory.glob("*.json")):
        if not path.name.endswith(CONTEXT_ARTIFACT_SUFFIXES):
            continue
        data = path.read_bytes()
        if len(data) > MAX_ARTIFACT_BYTES:
            artifacts[path.name] = {
                "status": "omitted_too_large",
                "sha256": sha256_bytes(data),
                "size_bytes": len(data),
            }
            continue
        try:
            payload = json.loads(data.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            artifacts[path.name] = {
                "status": "omitted_invalid_json",
                "sha256": sha256_bytes(data),
            }
            continue
        artifacts[path.name] = sanitize_value(payload, source_root)
    return artifacts


def source_root_from_spec(spec: dict[str, Any]) -> str | None:
    value = spec.get("source_root")
    if not isinstance(value, str):
        source = spec.get("source")
        value = source.get("source_root") if isinstance(source, dict) else None
    return value if isinstance(value, str) and value else None


def sanitize_value(value: Any, source_root: str | None) -> Any:
    if isinstance(value, dict):
        return {
            str(key): sanitize_value(item, source_root)
            for key, item in value.items()
            if not sensitive_key(str(key))
        }
    if isinstance(value, list):
        return [sanitize_value(item, source_root) for item in value]
    if not isinstance(value, str):
        return value
    sanitized = value.replace(source_root, "<source-root>") if source_root else value
    return HOST_PATH_PATTERN.sub("<host-path>", sanitized)


def sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in SENSITIVE_KEY_PARTS)


def required_string(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"slice spec requires non-empty {field}")
    return value
