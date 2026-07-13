from __future__ import annotations

import json
import re
from typing import Any

from .context_security import sha256_bytes


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def external_callee_source_context_status(context_pack: dict[str, Any]) -> str:
    c_boundary = context_pack.get("c_boundary")
    required = c_boundary.get("required_callee_sections") if isinstance(c_boundary, dict) else []
    if not isinstance(required, list) or "external_direct_callees" not in required:
        return "ready"
    boundary_payload = c_boundary.get("payload")
    if not isinstance(boundary_payload, dict):
        boundary_payload = c_boundary
    declared = boundary_payload.get("external_direct_callees")
    if not isinstance(declared, list):
        return "invalid"
    required_source_names = {
        item.get("name")
        for item in declared
        if isinstance(item, dict)
        and item.get("definition_status") == "real_source_bound"
        and isinstance(item.get("name"), str)
    }
    if not required_source_names:
        return "ready"
    context = context_pack.get("external_callee_source_context")
    if not isinstance(context, dict):
        return "invalid"
    if context.get("status") not in {"bound", "partial"}:
        return "incomplete"
    if not isinstance(context.get("blocks"), list) or not context["blocks"]:
        return "incomplete"
    bound_source_names = {
        item.get("callee")
        for item in context["blocks"]
        if isinstance(item, dict) and isinstance(item.get("callee"), str)
    }
    if not required_source_names.issubset(bound_source_names):
        return "incomplete"
    inputs = context_pack.get("bindings", {}).get("inputs")
    if not isinstance(inputs, list):
        return "invalid"
    source_bindings = {
        _callee_binding_identity(item)
        for item in inputs
        if isinstance(item, dict)
        and item.get("kind")
        in {"external_callee_source", "external_callee_dependency_source"}
    }
    known_span_hashes: set[str] = set()
    dependencies = context.get("dependencies")
    if not isinstance(dependencies, list):
        return "invalid"
    source_items = [
        *((item, "external_callee_source", "callee") for item in context["blocks"]),
        *((item, "external_callee_dependency_source", "symbol") for item in dependencies),
    ]
    for item, kind, name_key in source_items:
        identity = _context_source_identity(item, kind, name_key)
        if identity is None or identity not in source_bindings:
            return "invalid"
        known_span_hashes.add(item["source_span"]["sha256"])
    source_span = context_pack.get("source", {}).get("span")
    if isinstance(source_span, dict):
        for key in ("sha256", "declared_sha256"):
            value = source_span.get(key)
            if _is_sha256(value):
                known_span_hashes.add(value)
    critical_reasons = {
        "source_file_sha256_mismatch",
        "source_file_changed_during_read",
        "guard_macro_definition_not_found",
        "return_constant_definition_not_found",
        "source_behavior_expected_output_mismatch",
        "callee_context_exceeds_total_limit",
    }
    blocked = context.get("blocked")
    if not isinstance(blocked, list) or any(
        isinstance(item, dict) and item.get("reason") in critical_reasons
        for item in blocked
    ):
        return "incomplete"
    return _behavior_status(context, known_span_hashes)


def _behavior_status(context: dict[str, Any], known_span_hashes: set[str]) -> str:
    behavior = context.get("source_backed_behavior")
    if not isinstance(behavior, dict) or behavior.get("semantics_verified") is not False:
        return "invalid"
    behavior_hash = behavior.get("behavior_sha256")
    if not _is_sha256(behavior_hash):
        return "invalid"
    behavior_payload = dict(behavior)
    behavior_payload.pop("behavior_sha256", None)
    if sha256_bytes(_canonical_bytes(behavior_payload)) != behavior_hash:
        return "invalid"
    rules = behavior.get("rules")
    if not isinstance(rules, list):
        return "invalid"
    for rule in rules:
        if not isinstance(rule, dict) or not _is_sha256(rule.get("rule_sha256")):
            return "invalid"
        rule_payload = dict(rule)
        rule_hash = rule_payload.pop("rule_sha256")
        if sha256_bytes(_canonical_bytes(rule_payload)) != rule_hash:
            return "invalid"
        spans = rule.get("source_span_sha256")
        if not isinstance(spans, list) or not spans or not set(spans).issubset(known_span_hashes):
            return "invalid"
    return "ready"


def _context_source_identity(
    item: Any,
    kind: str,
    name_key: str,
) -> tuple[Any, ...] | None:
    if not isinstance(item, dict):
        return None
    source_file = item.get("source_file")
    source_span = item.get("source_span")
    name = item.get(name_key)
    if (
        not isinstance(name, str)
        or not isinstance(source_file, dict)
        or not isinstance(source_span, dict)
        or not isinstance(source_file.get("path"), str)
        or not _is_sha256(source_file.get("sha256"))
        or not _is_sha256(source_file.get("declared_sha256"))
        or source_file.get("hash_match_mode") not in {"exact", "newline_equivalent"}
        or not _is_sha256(source_span.get("sha256"))
        or not isinstance(source_span.get("line_start"), int)
        or not isinstance(source_span.get("line_end"), int)
    ):
        return None
    return (
        kind,
        name,
        source_file["path"],
        source_file["sha256"],
        source_file["declared_sha256"],
        source_file["hash_match_mode"],
        source_span["line_start"],
        source_span["sha256"],
        source_span["line_end"],
    )


def _callee_binding_identity(item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        item.get("kind"),
        item.get("name"),
        item.get("path"),
        item.get("sha256"),
        item.get("declared_sha256"),
        item.get("hash_match_mode"),
        item.get("line_start"),
        item.get("source_span_sha256"),
        item.get("line_end"),
    )


def _canonical_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf-8")


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and SHA256_RE.fullmatch(value) is not None


__all__ = ["external_callee_source_context_status"]
