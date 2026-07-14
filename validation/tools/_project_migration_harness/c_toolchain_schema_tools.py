from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .c_toolchain_output import (
    EMPTY_SHA256, decode_probe_streams, reported_value,
)
from .c_toolchain_probe import PROBE_KINDS, probe_plans
from .c_toolchain_runner import MAX_PROBE_STREAM_BYTES
from .c_toolchain_schema_identity import (
    basename, is_absolute, is_sha256, is_text, string_list,
)
from .host_tool_binding import (
    MAX_TOOL_BYTES, MAX_TOOL_RECORDS, TOOL_ROLES, classify_tool_basename,
    resolved_tool_family_compatible, validate_role_family,
)


_TOOL_KEYS = {
    "token", "roles", "requested", "derived_from_tokens", "status", "family",
    "basename", "resolved_path", "resolution", "binary", "probe_policy",
    "probes", "blockers",
}
_PROBE_KEYS = {
    "kind", "arguments", "interpretation", "status", "returncode", "value",
    "stdout_b64", "stdout_sha256", "stdout_size_bytes", "stderr_b64",
    "stderr_sha256", "stderr_size_bytes",
}
_PROBE_STATUSES = {
    "reported", "reported-empty/default", "not-applicable", "failed",
    "timed-out", "output-flood",
}


def validate_tools(
    value: Any, requests: list[Mapping[str, Any]], path_flavor: str,
) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ValueError("c_toolchain_tools_invalid")
    if len(value) > MAX_TOOL_RECORDS:
        raise ValueError("c_toolchain_tools_limit_exceeded")
    if any(not isinstance(item, Mapping) for item in value):
        raise ValueError("c_toolchain_tool_fields_invalid")
    requested = {item["token"]: item for item in requests}
    for item in value:
        _validate_tool(item, requested, path_flavor)
    tokens = [item["token"] for item in value]
    if tokens != sorted(set(tokens)):
        raise ValueError("c_toolchain_tool_order_invalid")
    if not set(requested).issubset(tokens):
        raise ValueError("c_toolchain_requested_tool_missing")
    for item in value:
        if any(parent not in requested for parent in item["derived_from_tokens"]):
            raise ValueError("c_toolchain_derived_parent_invalid")
        if not item["requested"] and not item["derived_from_tokens"]:
            raise ValueError("c_toolchain_derived_parent_invalid")
    return value


def _validate_tool(
    value: Any, requested: Mapping[str, Mapping[str, Any]], path_flavor: str,
) -> None:
    if not isinstance(value, Mapping) or set(value) != _TOOL_KEYS:
        raise ValueError("c_toolchain_tool_fields_invalid")
    token, roles = value.get("token"), value.get("roles")
    if (
        not is_text(token)
        or not isinstance(roles, list)
    ):
        raise ValueError("c_toolchain_tool_identity_invalid")
    if any(type(role) is not str or role not in TOOL_ROLES for role in roles):
        raise ValueError("c_toolchain_tool_identity_invalid")
    if roles != sorted(set(roles)):
        raise ValueError("c_toolchain_tool_identity_invalid")
    family, token_basename = classify_tool_basename(basename(token))
    validate_role_family(roles, family)
    if value.get("family") != family or value.get("basename") != token_basename:
        raise ValueError("c_toolchain_tool_family_invalid")
    is_requested = token in requested
    if value.get("requested") is not is_requested:
        raise ValueError("c_toolchain_tool_request_binding_invalid")
    if is_requested and roles != requested[token]["roles"]:
        raise ValueError("c_toolchain_tool_request_binding_invalid")
    if not is_requested and roles != ["linker"]:
        raise ValueError("c_toolchain_derived_role_invalid")
    parents = string_list(
        value.get("derived_from_tokens"), "c_toolchain_derived_parent_invalid",
    )
    if parents != sorted(set(parents)):
        raise ValueError("c_toolchain_derived_parent_invalid")
    _validate_resolution(value.get("resolution"))
    blockers = string_list(
        value.get("blockers"), "c_toolchain_tool_blockers_invalid",
    )
    if blockers != sorted(set(blockers)):
        raise ValueError("c_toolchain_tool_blockers_invalid")
    if (
        value.get("status") not in {"ready", "blocked"}
        or (value["status"] == "blocked") != bool(blockers)
    ):
        raise ValueError("c_toolchain_tool_status_invalid")
    if value.get("resolved_path") is None:
        _validate_unresolved(value, blockers)
        return
    _validate_resolved(value, family, roles, path_flavor)


def _validate_resolution(value: Any) -> None:
    if (
        not isinstance(value, Mapping)
        or set(value) != {"mode", "path_snapshot_sha256"}
        or value.get("mode") not in {"absolute", "path-search"}
        or not is_sha256(value.get("path_snapshot_sha256"))
    ):
        raise ValueError("c_toolchain_resolution_invalid")


def _validate_unresolved(value: Mapping[str, Any], blockers: list[str]) -> None:
    if (
        value.get("binary") is not None
        or value.get("probe_policy") != "not-started"
        or value.get("probes") != []
        or not blockers
    ):
        raise ValueError("c_toolchain_unresolved_tool_invalid")


def _validate_resolved(
    value: Mapping[str, Any], family: str, roles: list[str], path_flavor: str,
) -> None:
    if not is_absolute(value["resolved_path"], path_flavor):
        raise ValueError("c_toolchain_resolved_path_invalid")
    resolved_family, resolved_basename = classify_tool_basename(
        basename(value["resolved_path"]),
    )
    if not resolved_tool_family_compatible(
        family,
        str(value["basename"]),
        resolved_family,
        resolved_basename,
    ):
        raise ValueError("c_toolchain_resolved_path_invalid")
    binary = value.get("binary")
    if (
        not isinstance(binary, Mapping)
        or set(binary) != {"sha256", "size_bytes"}
        or not is_sha256(binary.get("sha256"))
        or type(binary.get("size_bytes")) is not int
        or not 0 <= binary["size_bytes"] <= MAX_TOOL_BYTES
    ):
        raise ValueError("c_toolchain_binary_invalid")
    expected_policy = (
        "hash-only-wrapper" if family == "compiler-wrapper" else "fixed-probes"
    )
    if value.get("probe_policy") != expected_policy:
        raise ValueError("c_toolchain_probe_policy_invalid")
    _validate_probes(value.get("probes"), family, roles)


def _validate_probes(value: Any, family: str, roles: list[str]) -> None:
    if not isinstance(value, list) or len(value) != len(PROBE_KINDS):
        raise ValueError("c_toolchain_probes_invalid")
    plans = probe_plans(family, roles)
    for record, plan in zip(value, plans, strict=True):
        if not isinstance(record, Mapping) or set(record) != _PROBE_KEYS:
            raise ValueError("c_toolchain_probe_fields_invalid")
        if (
            record.get("kind") != plan.kind
            or record.get("arguments") != list(plan.arguments)
            or record.get("interpretation") != plan.interpretation
            or record.get("status") not in _PROBE_STATUSES
        ):
            raise ValueError("c_toolchain_probe_contract_invalid")
        _validate_probe_result(record, plan.applicable, family)


def _validate_probe_result(
    value: Mapping[str, Any], applicable: bool, family: str,
) -> None:
    stdout, stderr = decode_probe_streams(value)
    status = value["status"]
    if not applicable:
        if (
            status != "not-applicable"
            or value.get("returncode") is not None
            or value.get("value") is not None
            or value.get("stdout_b64") != ""
            or value.get("stderr_b64") != ""
            or value.get("stdout_sha256") != EMPTY_SHA256
            or value.get("stderr_sha256") != EMPTY_SHA256
        ):
            raise ValueError("c_toolchain_probe_not_applicable_invalid")
        return
    if status == "not-applicable":
        raise ValueError("c_toolchain_probe_contract_invalid")
    if value.get("returncode") is not None and type(value["returncode"]) is not int:
        raise ValueError("c_toolchain_probe_returncode_invalid")
    if status in {"reported", "reported-empty/default"}:
        try:
            parsed = reported_value(value["kind"], stdout, stderr, family)
        except UnicodeDecodeError as error:
            raise ValueError("c_toolchain_probe_output_utf8_invalid") from error
        if status == "reported" and (
            not is_text(value.get("value")) or value["value"] != parsed
        ):
            raise ValueError("c_toolchain_probe_value_invalid")
        accepts_nonzero = family.startswith("msvc-") and value["kind"] in {
            "version", "target",
        }
        if status == "reported" and (
            type(value.get("returncode")) is not int
            or (value["returncode"] != 0 and not accepts_nonzero)
        ):
            raise ValueError("c_toolchain_probe_returncode_invalid")
        if status == "reported-empty/default" and (
            value.get("kind") != "sysroot"
            or value.get("returncode") != 0
            or value.get("value") is not None
            or parsed is not None
        ):
            raise ValueError("c_toolchain_probe_empty_default_invalid")
    elif value.get("value") is not None:
        raise ValueError("c_toolchain_probe_value_invalid")
    if status == "output-flood" and max(len(stdout), len(stderr)) <= MAX_PROBE_STREAM_BYTES:
        raise ValueError("c_toolchain_probe_output_flood_invalid")


__all__ = ["validate_tools"]
