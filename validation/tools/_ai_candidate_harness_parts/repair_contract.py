from __future__ import annotations

import json
import math
from typing import Any

from .context import HOST_PATH_PATTERN, canonical_json_bytes, sha256_bytes
from .provider import assistant_text_from_jsonl


MAX_FAILURE_FACTS_BYTES = 64_000
MAX_REPAIR_RESPONSE_BYTES = 512_000
FAILURE_FACT_KEYS = frozenset({"gate", "kind", "message", "location", "expected", "actual", "details"})
SENSITIVE_DETAIL_KEYS = ("api_key", "apikey", "password", "secret", "credential", "access_token", "refresh_token")


def normalize_validation_result(payload: Any, *, require_failed: bool = False) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("validation result must be an object")
    if set(payload) != {"schema_version", "status", "failures"}:
        raise ValueError("validation result requires only schema_version, status, and failures")
    if payload.get("schema_version") != 1:
        raise ValueError("validation result schema_version must be 1")
    status = payload.get("status")
    if status not in {"failed", "passed"}:
        raise ValueError("validation result status must be failed or passed")
    if require_failed and status != "failed":
        raise ValueError("repair requires an initial failed validation result")
    failures = payload.get("failures")
    if not isinstance(failures, list):
        raise ValueError("validation result failures must be an array")
    if status == "failed" and not failures:
        raise ValueError("failed validation result requires at least one failure fact")
    if status == "passed" and failures:
        raise ValueError("passed validation result cannot contain failure facts")

    normalized = {
        "schema_version": 1,
        "status": status,
        "failures": [normalize_failure_fact(fact) for fact in failures],
    }
    if len(canonical_json_bytes(normalized)) > MAX_FAILURE_FACTS_BYTES:
        raise ValueError(f"validation result exceeds {MAX_FAILURE_FACTS_BYTES} bytes")
    return normalized


def normalize_failure_fact(fact: Any) -> dict[str, Any]:
    if not isinstance(fact, dict):
        raise ValueError("each failure fact must be an object")
    unknown = set(fact) - FAILURE_FACT_KEYS
    if unknown:
        raise ValueError(f"failure fact contains unsupported fields: {', '.join(sorted(unknown))}")
    for field in ("gate", "kind", "message"):
        value = fact.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"failure fact requires non-empty {field}")
    normalized = {key: json_compatible(value, field=key) for key, value in fact.items()}
    return {key: normalized[key] for key in FAILURE_FACT_KEYS if key in normalized}


def json_compatible(value: Any, *, field: str) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"failure fact {field} cannot contain non-finite numbers")
    if isinstance(value, str):
        return HOST_PATH_PATTERN.sub("<host-path>", value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, list):
        return [json_compatible(item, field=field) for item in value]
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"failure fact {field} object keys must be strings")
            lowered = key.lower()
            if any(sensitive in lowered for sensitive in SENSITIVE_DETAIL_KEYS):
                raise ValueError(f"failure fact {field} cannot contain sensitive field {key}")
            normalized[key] = json_compatible(item, field=field)
        return normalized
    raise ValueError(f"failure fact {field} must contain only JSON values")


def validation_result_sha256(payload: dict[str, Any]) -> str:
    return sha256_bytes(canonical_json_bytes(payload))


def parse_repair_response(stdout: str) -> dict[str, Any]:
    if len(stdout.encode("utf-8")) > MAX_REPAIR_RESPONSE_BYTES:
        raise ValueError(f"repair response exceeds {MAX_REPAIR_RESPONSE_BYTES} bytes")
    text = assistant_text_from_jsonl(stdout).strip()
    if not text:
        raise ValueError("OpenCode repair response contained no assistant text")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"repair assistant text is not one JSON object: {error.msg}") from error
    if not isinstance(payload, dict):
        raise ValueError("repair response must be an object")
    if set(payload) != {"schema_version", "repair", "assumptions"}:
        raise ValueError("repair response requires only schema_version, repair, and assumptions")
    if payload.get("schema_version") != 1:
        raise ValueError("repair response schema_version must be 1")
    assumptions = payload.get("assumptions")
    if not isinstance(assumptions, list) or not all(isinstance(item, str) for item in assumptions):
        raise ValueError("repair response assumptions must be a string array")
    repair = payload.get("repair")
    if not isinstance(repair, dict):
        raise ValueError("repair response requires one repair object")
    kind = repair.get("kind")
    if kind == "candidate":
        if set(repair) != {"kind", "language", "source"}:
            raise ValueError("candidate repair requires only kind, language, and source")
        if repair.get("language") != "rust":
            raise ValueError("candidate repair language must be rust")
        source = repair.get("source")
        if not isinstance(source, str) or not source.strip():
            raise ValueError("candidate repair source must be non-empty")
    elif kind == "patch":
        if set(repair) != {"kind", "format", "content"}:
            raise ValueError("patch repair requires only kind, format, and content")
        if repair.get("format") != "unified_diff":
            raise ValueError("patch repair format must be unified_diff")
        content = repair.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("patch repair content must be non-empty")
    else:
        raise ValueError("repair kind must be candidate or patch")
    return payload
