from __future__ import annotations

from collections.abc import Mapping
import copy
from typing import Any

from .artifacts import content_sha256
from .c_toolchain_schema_identity import (
    is_sha256, string_list, validate_environment, validate_host,
    validate_profile_binding, validate_requests,
)
from .c_toolchain_schema_tools import validate_tools


C_TOOLCHAIN_RAW_ROLE = "c-toolchain-evidence"
C_TOOLCHAIN_ARTIFACT_KIND = "project-migration-c-toolchain-evidence"
C_TOOLCHAIN_PROFILES = ("competition", "development")

_TOP_KEYS = {
    "schema_version", "artifact_kind", "raw_fact_role", "profile",
    "profile_binding", "status", "requests", "host", "environment", "tools",
    "blockers", "claim_boundary", "evidence_sha256",
}


def validate_c_toolchain_evidence(value: Any) -> None:
    if not isinstance(value, Mapping) or set(value) != _TOP_KEYS:
        raise ValueError("c_toolchain_evidence_fields_invalid")
    profile = value.get("profile")
    if (
        value.get("schema_version") != 1
        or value.get("artifact_kind") != C_TOOLCHAIN_ARTIFACT_KIND
        or value.get("raw_fact_role") != C_TOOLCHAIN_RAW_ROLE
        or profile not in C_TOOLCHAIN_PROFILES
    ):
        raise ValueError("c_toolchain_evidence_identity_invalid")
    validate_profile_binding(value.get("profile_binding"), profile)
    requests = validate_requests(value.get("requests"))
    host = validate_host(value.get("host"))
    validate_environment(value.get("environment"))
    tools = validate_tools(value.get("tools"), requests, host["path_flavor"])
    blockers = string_list(
        value.get("blockers"), "c_toolchain_blockers_invalid",
    )
    if blockers != sorted(set(blockers)):
        raise ValueError("c_toolchain_blockers_invalid")
    status = value.get("status")
    if (
        status not in {"ready", "blocked"}
        or (status == "blocked") != bool(blockers)
    ):
        raise ValueError("c_toolchain_status_invalid")
    if profile == "competition" and host["system"] != "linux" and not any(
        item == "competition_host_os_family_mismatch" for item in blockers
    ):
        raise ValueError("c_toolchain_competition_host_policy_invalid")
    if any(tool["status"] == "blocked" for tool in tools) and status != "blocked":
        raise ValueError("c_toolchain_status_invalid")
    if value.get("claim_boundary") != {
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
    }:
        raise ValueError("c_toolchain_claim_boundary_invalid")
    core = {key: value[key] for key in _TOP_KEYS if key != "evidence_sha256"}
    if (
        not is_sha256(value.get("evidence_sha256"))
        or value["evidence_sha256"] != content_sha256(core)
    ):
        raise ValueError("c_toolchain_evidence_sha256_invalid")


def tool_records_by_token(value: Any) -> dict[str, dict]:
    validate_c_toolchain_evidence(value)
    return {
        item["token"]: copy.deepcopy(dict(item))
        for item in value["tools"]
    }


__all__ = [
    "C_TOOLCHAIN_ARTIFACT_KIND", "C_TOOLCHAIN_PROFILES", "C_TOOLCHAIN_RAW_ROLE",
    "tool_records_by_token", "validate_c_toolchain_evidence",
]
