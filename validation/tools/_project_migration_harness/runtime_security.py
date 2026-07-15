from __future__ import annotations

import json
import hashlib
import re
import threading
from collections.abc import Callable, Mapping
from typing import Any

from .context_contracts import canonical as canonical_context_bytes
from .ledger_security import assert_no_secrets
from .rust_candidate_facts import derive_rust_metadata
from .rust_ffi_facts import derive_boundary_manifest


VALUE_KEYS = {
    "actual", "expected", "fixture", "fixture_value", "fixture_values",
    "observed", "oracle", "oracle_value", "oracle_values", "raw_output",
}
VALUE_LANGUAGE = re.compile(
    r"\b(?:actual|expected|fixture|observed|oracle|received|raw output)\b",
    re.IGNORECASE,
)
SHA256 = re.compile(r"^[0-9a-f]{64}$")
TOOL_EVENT = {
    "function-call", "function_call", "tool", "tool-call", "tool-result",
    "tool-use", "tool_call", "tool_result", "tool_use",
}
PAGE_KEYS = {
    "classification", "dependency_count", "dependency_set_sha256", "facts",
    "part_index", "scc_id", "wave_index",
}
FACT_PAYLOAD_KEYS = {
    "build_target": {
        "dependency_target_ids", "kind", "name", "ordered_input_target_ids",
        "ordered_link_arguments", "output_paths", "target_id",
    },
    "build_target_membership": {
        "consumer_target_ids", "object_target_id", "unit_id", "variant",
    },
    "compile_define": {"name", "unit_id", "value"},
    "compile_include": {"kind", "path", "scope", "unit_id"},
    "compile_semantic_flag": {"index", "unit_id", "value"},
    "compile_unit": {
        "compiler", "language", "redacted_define_count", "unit_id",
        "working_directory",
    },
    "compiler_fact_binding": {
        "unit_id", "status", "reason_code", "source_sha256",
        "expanded_argv_sha256", "toolchain_id", "toolchain_binding_sha256",
        "compile_context_sha256", "plan_sha256", "receipt_sha256",
        "command_started", "syntax_passed", "diagnostics_sha256",
        "diagnostic_bytes", "evidence_scope", "semantic_gate",
        "compiler_basename", "compiler_binary_sha256",
        "compiler_binary_size_bytes",
        "translation_coverage_numerator",
    },
    "context_retrieval_summary": {
        "omitted_fact_count", "scc_id", "selected_fact_count",
        "selection_receipt_sha256", "selection_status",
        "required_fact_query_count", "unresolved_required_fact_count",
        "visibility",
    },
    "external_call": {"caller_node_id", "candidate_node_ids", "status", "symbol"},
    "function": {"linkage", "node_id", "node_kind", "symbol", "unit_id"},
    "function_source": {"chunk_count", "chunk_index", "content", "node_id"},
    "function_signature": {"chunk_count", "chunk_index", "content", "node_id"},
    "global": {"global_id", "linkage", "symbol", "unit_id"},
    "global_source": {"chunk_count", "chunk_index", "content", "owner_id"},
    "global_source_binding": {"owner_id", "source"},
    "global_reference": {"global_ids", "node_id", "status", "symbol"},
    "header_source": {"chunk_count", "chunk_index", "content", "owner_id"},
    "header_source_binding": {"owner_id", "source"},
    "include_binding": {
        "body", "byte_offset", "from_path", "kind", "path", "sha256",
        "status", "style", "target", "unit_id",
    },
    "parser_boundary": {
        "byte_offset", "evidence_set_sha256", "kind", "occurrence_count", "unit_id",
    },
    "resolved_call": {"callee_node_id", "caller_node_id", "symbol"},
    "scc_dependency": {"dependency_scc_id", "scc_id"},
    "source_binding": {"node_id", "source"},
    "source_macro_definition": {
        "node_id", "unit_id", "name", "parameters", "replacement",
        "source_path", "source_sha256", "directive_sha256", "byte_offset",
        "conditional_depth", "activation_status",
    },
    "top_level_source": {"chunk_count", "chunk_index", "content", "owner_id"},
    "top_level_source_binding": {"owner_id", "source"},
    "translation_unit_coverage": {
        "function_span_count", "source_size_bytes", "status",
        "top_level_projection_sha256", "uncovered_range_count", "unit_id",
    },
    "translation_unit_function_spans": {
        "chunk_count", "chunk_index", "spans", "unit_id",
    },
    "translation_unit_uncovered_ranges": {
        "chunk_count", "chunk_index", "ranges", "unit_id",
    },
}
FACT_OPTIONAL_KEYS = {
    "include_binding": {"path", "style"},
    "parser_boundary": {"byte_offset", "evidence_set_sha256", "occurrence_count"},
}


def assert_model_payload_safe(value: Any, path: str = "model_payload") -> None:
    assert_no_secrets(value, path)
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = re.sub(r"[^a-z0-9]+", "_", str(key).lower()).strip("_")
            if normalized in VALUE_KEYS:
                raise ValueError(f"value-bearing model field is forbidden: {path}.{key}")
            assert_model_payload_safe(child, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            assert_model_payload_safe(child, f"{path}[{index}]")


def validate_context_page(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != PAGE_KEYS:
        raise ValueError("context page fields are not allowlisted")
    if not isinstance(value.get("facts"), list):
        raise ValueError("context page facts must be an array")
    for fact in value["facts"]:
        if not isinstance(fact, Mapping) or set(fact) != {"sha256", "kind", "payload"}:
            raise ValueError("context fact fields are not allowlisted")
        kind = fact.get("kind")
        payload = fact.get("payload")
        if kind not in FACT_PAYLOAD_KEYS or not isinstance(payload, Mapping):
            raise ValueError("context fact kind/payload is invalid")
        allowed = FACT_PAYLOAD_KEYS[str(kind)]
        required = allowed - FACT_OPTIONAL_KEYS.get(str(kind), set())
        if set(payload) - allowed or not required <= set(payload):
            raise ValueError(f"context fact payload is not allowlisted: {kind}")
        if not isinstance(fact.get("sha256"), str) or SHA256.fullmatch(fact["sha256"]) is None:
            raise ValueError("context fact SHA-256 is invalid")
        if hashlib.sha256(canonical_context_bytes({
            "kind": kind, "payload": dict(payload),
        })).hexdigest() != fact["sha256"]:
            raise ValueError("context fact SHA-256 does not match its payload")
    assert_model_payload_safe(value, "context_page")
    return dict(value)


def reject_value_bearing_text(value: str, label: str) -> None:
    if VALUE_LANGUAGE.search(value):
        raise ValueError(f"{label} contains withheld value language")


def reject_forbidden_tool_events(stdout: str) -> None:
    for line in stdout.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError("OpenCode output is not complete JSONL") from error
        if not isinstance(event, Mapping) or _contains_tool_event(event):
            raise ValueError("OpenCode project worker used a forbidden tool event")


def _contains_tool_event(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized_key = re.sub(r"[^a-z0-9]+", "_", str(key).lower()).strip("_")
            if normalized_key in {"tool", "tool_call", "tool_calls", "tool_use"}:
                if child not in (None, "", [], {}):
                    return True
            if normalized_key == "type" and isinstance(child, str):
                normalized = child.lower().replace(" ", "-")
                if normalized in TOOL_EVENT or normalized.replace("_", "-") in TOOL_EVENT:
                    return True
            if _contains_tool_event(child):
                return True
    elif isinstance(value, list):
        return any(_contains_tool_event(item) for item in value)
    return False


def heartbeat_runner(
    runner: Callable[[list[str], int], Any], heartbeat: Callable[[], None],
    *, interval_seconds: float,
) -> Callable[[list[str], int], Any]:
    if interval_seconds <= 0:
        raise ValueError("heartbeat interval must be positive")

    def run(argv: list[str], timeout_seconds: int) -> Any:
        stopped = threading.Event()
        failures: list[BaseException] = []

        def pulse() -> None:
            while not stopped.wait(interval_seconds):
                try:
                    heartbeat()
                except BaseException as error:  # captured and surfaced after the command.
                    failures.append(error)
                    return

        heartbeat()
        thread = threading.Thread(target=pulse, name="project-worker-lease-heartbeat", daemon=True)
        thread.start()
        try:
            result = runner(argv, timeout_seconds)
        finally:
            stopped.set()
            thread.join(timeout=max(1.0, interval_seconds * 2))
        if failures:
            raise RuntimeError("project worker lease heartbeat failed") from failures[0]
        heartbeat()
        return result

    return run


__all__ = [
    "assert_model_payload_safe", "derive_boundary_manifest", "derive_rust_metadata",
    "heartbeat_runner", "reject_forbidden_tool_events", "reject_value_bearing_text",
    "validate_context_page",
]
