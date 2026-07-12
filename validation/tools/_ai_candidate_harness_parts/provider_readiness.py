from __future__ import annotations

import re
from typing import Any

from .context_replay import count_rust_function_calls
from .context_security import sha256_bytes


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
READY_SOURCE_SPAN_STATUSES = frozenset(
    {"real_source_bound", "inline_slice_spec", "inline_translation_carrier_bound"}
)
BLOCKED_SOURCE_SPAN_STATUSES = frozenset(
    {
        "blocked_path_outside_source_root",
        "source_file_missing",
        "blocked_source_hash_mismatch",
        "source_span_too_large",
        "source_span_empty",
        "source_span_coordinates_missing",
        "blocked_span_hash_mismatch",
        "omitted_too_large",
        "unsupported_source_encoding",
        "source_span_unavailable",
        "blocked_translation_carrier_contract",
        "source_binding_incomplete",
        "source_root_not_ready",
        "source_file_changed_during_read",
    }
)


def evaluate_provider_readiness(context_pack: dict[str, Any]) -> dict[str, str]:
    """Return a bounded source-span admission result before provider invocation."""
    if not isinstance(context_pack, dict) or context_pack.get("schema_version") != 4:
        return {"status": "blocked", "source_span_status": "invalid_context_shape"}
    source_root = context_pack.get("source_root") if isinstance(context_pack, dict) else None
    source_root_status = source_root.get("status") if isinstance(source_root, dict) else None
    source = context_pack.get("source") if isinstance(context_pack, dict) else None
    span = source.get("span") if isinstance(source, dict) else None
    raw_status = span.get("status") if isinstance(span, dict) else None
    response_file_status = response_file_contract_status(context_pack)
    callee_context_status = required_callee_context_status(context_pack)
    replay_contract_status = replay_api_contract_status(context_pack)
    source_admitted = (
        raw_status == "inline_slice_spec"
        and source_root_status == "unavailable"
        and inline_span_is_bound(span)
    ) or (
        raw_status in {"real_source_bound", "inline_translation_carrier_bound"}
        and source_root_status in {"explicit", "slice_spec_relative"}
        and bound_project_span_is_complete(source, span)
    )
    if not source_admitted:
        if raw_status in READY_SOURCE_SPAN_STATUSES:
            reason = (
                "source_root_not_ready"
                if source_root_status not in {"unavailable", "explicit", "slice_spec_relative"}
                else "source_binding_incomplete"
            )
            return {"status": "blocked", "source_span_status": reason}
        source_span_status = (
            raw_status if raw_status in BLOCKED_SOURCE_SPAN_STATUSES else "invalid_context_shape"
        )
        return {"status": "blocked", "source_span_status": source_span_status}
    if response_file_status in {"blocked", "invalid"}:
        return {
            "status": "blocked",
            "source_span_status": raw_status,
            "compile_context_status": "response_file_invalid",
        }
    if callee_context_status != "ready":
        return {
            "status": "blocked",
            "source_span_status": raw_status,
            "context_boundary_status": "required_callee_context_incomplete",
        }
    if replay_contract_status != "bound":
        return {
            "status": "blocked",
            "source_span_status": raw_status,
            "replay_api_contract_status": replay_contract_status,
        }
    return {"status": "ready", "source_span_status": raw_status}


def inline_span_is_bound(span: dict[str, Any]) -> bool:
    return is_sha256(span.get("sha256")) and isinstance(span.get("content"), str)


def bound_project_span_is_complete(source: Any, span: dict[str, Any]) -> bool:
    source_input = source.get("input") if isinstance(source, dict) else None
    if not isinstance(source_input, dict) or not isinstance(span.get("content"), str):
        return False
    if not all(
        is_sha256(source_input.get(field))
        for field in ("sha256", "declared_sha256")
    ) or source_input.get("hash_match_mode") not in {"exact", "newline_equivalent"}:
        return False
    if not all(is_sha256(span.get(field)) for field in ("sha256", "declared_sha256")):
        return False
    if raw_hash_mode_invalid(span):
        return False
    if span.get("status") == "inline_translation_carrier_bound":
        fragment = span.get("real_source_fragment")
        return (
            isinstance(fragment, dict)
            and all(is_sha256(fragment.get(field)) for field in ("sha256", "declared_sha256"))
            and fragment.get("sha256") == fragment.get("declared_sha256")
            and isinstance(fragment.get("content"), str)
        )
    return True


def raw_hash_mode_invalid(span: dict[str, Any]) -> bool:
    return span.get("hash_match_mode") not in {"exact", "newline_equivalent"}


def response_file_contract_status(context_pack: dict[str, Any]) -> str:
    compile_context = context_pack.get("compile_context")
    selected = compile_context.get("selected_entry") if isinstance(compile_context, dict) else None
    response_files = selected.get("response_files") if isinstance(selected, dict) else None
    if response_files is None:
        return "not_present"
    if not isinstance(response_files, dict):
        return "invalid"
    if response_files.get("status") == "blocked":
        return "blocked"
    files = response_files.get("files")
    bindings = context_pack.get("bindings")
    inputs = bindings.get("inputs") if isinstance(bindings, dict) else None
    if response_files.get("status") != "expanded" or not isinstance(files, list) or not isinstance(inputs, list):
        return "invalid"
    limits = response_files.get("limits")
    if limits != {
        "max_depth": 4,
        "max_files": 16,
        "max_file_bytes": 65_536,
        "max_total_bytes": 262_144,
        "max_arguments": 4_096,
    }:
        return "invalid"
    if (
        response_files.get("contract_version") != 1
        or response_files.get("dialect") != "gnu-v1"
        or response_files.get("unique_file_count") != len(files)
        or not isinstance(response_files.get("expansion_count"), int)
        or response_files["expansion_count"] < len(files)
        or response_files["expansion_count"] > 16
        or not isinstance(response_files.get("expanded_argument_count"), int)
        or response_files["expanded_argument_count"] > 4_096
        or not is_sha256(response_files.get("original_argv_sha256"))
        or not is_sha256(response_files.get("expanded_argv_sha256"))
    ):
        return "invalid"
    paths: set[str] = set()
    for item in files:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("path"), str)
            or not item["path"].startswith("<source-root>/")
            or item["path"] in paths
            or not is_sha256(item.get("sha256"))
            or not isinstance(item.get("size_bytes"), int)
            or not 0 <= item["size_bytes"] <= 65_536
            or not isinstance(item.get("depth"), int)
            or not 1 <= item["depth"] <= 4
        ):
            return "invalid"
        paths.add(item["path"])
    expected = sorted(files, key=lambda item: str(item.get("path")) if isinstance(item, dict) else "")
    actual = sorted(
        ({key: value for key, value in item.items() if key != "kind"} for item in inputs if isinstance(item, dict) and item.get("kind") == "compile_response_file"),
        key=lambda item: str(item.get("path")),
    )
    return "expanded" if expected == actual else "invalid"


def required_callee_context_status(context_pack: dict[str, Any]) -> str:
    c_boundary = context_pack.get("c_boundary")
    if not isinstance(c_boundary, dict):
        return "ready"
    required = c_boundary.get("required_callee_sections")
    missing = c_boundary.get("missing_required_callee_sections")
    if required is None and missing is None:
        return "ready"
    if not isinstance(required, list) or not isinstance(missing, list):
        return "invalid"
    return "ready" if not missing else "incomplete"


def replay_api_contract_status(context_pack: dict[str, Any]) -> str:
    contract = context_pack.get("replay_api_contract")
    if not isinstance(contract, dict):
        return "invalid"
    status = contract.get("status")
    if status != "bound":
        return status if isinstance(status, str) and status else "invalid"
    source = contract.get("source")
    requirements = contract.get("requirements")
    bindings = context_pack.get("bindings")
    inputs = bindings.get("inputs") if isinstance(bindings, dict) else None
    if (
        contract.get("schema_version") != 1
        or contract.get("contract_kind") != "generated_replay_rust_source"
        or not isinstance(contract.get("function_name"), str)
        or contract.get("function_name") != context_pack.get("function_name")
        or not isinstance(contract.get("call_count"), int)
        or contract["call_count"] < 1
        or not isinstance(source, dict)
        or not isinstance(requirements, dict)
        or not isinstance(inputs, list)
    ):
        return "invalid"
    path = source.get("path")
    content = source.get("content")
    if (
        not isinstance(path, str)
        or not path
        or path != f"l3-{context_pack.get('slice_id')}-rust-replay-test-draft.rs"
        or "/" in path
        or "\\" in path
        or path in {".", ".."}
        or not is_sha256(source.get("sha256"))
        or not isinstance(source.get("size_bytes"), int)
        or not 1 <= source["size_bytes"] <= 65_536
        or not isinstance(content, str)
        or len(content.encode("utf-8")) != source["size_bytes"]
        or sha256_bytes(content.encode("utf-8")) != source["sha256"]
        or count_rust_function_calls(content, contract["function_name"])
        != contract["call_count"]
        or requirements
        != {
            "candidate_defines_function": True,
            "all_call_sites_typecheck": True,
            "parameter_count_and_order": "as_invoked_by_generated_replay",
            "return_type": "as_constrained_by_generated_replay",
        }
    ):
        return "invalid"
    expected_input = {
        "kind": "generated_replay_contract",
        "path": path,
        "sha256": source["sha256"],
        "size_bytes": source["size_bytes"],
    }
    return "bound" if expected_input in inputs else "invalid"


def is_sha256(value: Any) -> bool:
    return isinstance(value, str) and SHA256_RE.fullmatch(value) is not None


__all__ = [
    "BLOCKED_SOURCE_SPAN_STATUSES",
    "READY_SOURCE_SPAN_STATUSES",
    "evaluate_provider_readiness",
]
