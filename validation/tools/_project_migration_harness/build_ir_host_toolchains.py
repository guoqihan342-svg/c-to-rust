from __future__ import annotations

from collections.abc import Mapping, Sequence
import copy
import re
from typing import Any

from .build_ir import is_sha256, stable_build_id
from .build_ir_toolchains import tool_basename
from .c_toolchain_schema import (
    C_TOOLCHAIN_PROFILES, C_TOOLCHAIN_RAW_ROLE,
    tool_records_by_token, validate_c_toolchain_evidence,
)
from .c_toolchain_profile import validate_profile_binding
from .host_tool_binding import classify_tool_basename, validate_role_family


HOST_TOOLCHAIN_IDENTITY = "host-probed-c-toolchain-v1"
MAX_PROJECTED_TOOLCHAINS = 1_024
_ROLES = {
    "archiver", "compiler-driver", "compiler-wrapper", "linker", "linker-driver",
    "ranlib",
}
_RECORD_KEYS = {
    "toolchain_id", "identity", "profile", "role", "driver", "wrappers",
    "language", "evidence_sha256", "profile_binding", "host_fingerprint",
    "environment_fingerprint", "tools", "provenance",
}
_TOOL_KEYS = {
    "token", "relation", "roles", "family", "basename", "resolved_path",
    "binary", "probe_policy", "version", "target", "sysroot",
    "resource_dir",
}
_PROBE_KEYS = {"status", "value", "stdout_sha256", "stderr_sha256"}
_TEXT = re.compile(r"[^\r\n\x00]{1,4096}\Z")


class HostToolchainProjection:
    """Project one immutable host-evidence artifact into BuildIR toolchains."""

    def __init__(self, evidence: Mapping[str, Any]) -> None:
        validate_c_toolchain_evidence(evidence)
        if evidence.get("status") != "ready":
            raise ValueError("build_ir_c_toolchain_evidence_blocked")
        self._evidence = copy.deepcopy(dict(evidence))
        self._tools = tool_records_by_token(evidence)
        self._records: dict[str, dict[str, Any]] = {}
        for request in evidence["requests"]:
            for role in request["roles"]:
                language = "c" if role == "compiler-driver" else "build"
                self._bundle(request["token"], role, [], language)

    def compile(self, driver: Any, wrappers: Any, language: Any) -> str:
        if not isinstance(wrappers, list) or not all(
            isinstance(item, str) for item in wrappers
        ):
            raise ValueError("build_ir_compiler_wrappers_invalid")
        if not isinstance(language, str) or not language:
            raise ValueError("build_ir_compiler_language_invalid")
        return self._bundle(driver, "compiler-driver", wrappers, language)

    def command(self, driver: Any, role: str) -> str:
        return self._bundle(driver, role, [], "build")

    def records(self) -> list[dict[str, Any]]:
        return [copy.deepcopy(self._records[key]) for key in sorted(self._records)]

    @property
    def profile(self) -> str:
        return str(self._evidence["profile"])

    def _bundle(
        self, driver: Any, role: str, wrappers: Sequence[str], language: str,
    ) -> str:
        if not isinstance(driver, str) or role not in _ROLES:
            raise ValueError("build_ir_c_toolchain_bundle_invalid")
        primary = self._required_tool(driver, role)
        wrapper_tools = [
            self._required_tool(token, "compiler-wrapper") for token in wrappers
        ]
        selected_driver = primary["token"]
        selected_wrappers = [item["token"] for item in wrapper_tools]
        related = []
        if role == "linker-driver":
            related = sorted(
                (
                    value for value in self._tools.values()
                    if selected_driver in value["derived_from_tokens"]
                    and value["roles"] == ["linker"]
                ),
                key=lambda value: value["token"],
            )
            if not related:
                raise ValueError("build_ir_c_toolchain_linker_missing")
        summaries = [
            *(
                _tool_summary(value, "wrapper")
                for value in wrapper_tools
            ),
            _tool_summary(primary, "driver"),
            *(_tool_summary(value, "derived-linker") for value in related),
        ]
        core = {
            "identity": HOST_TOOLCHAIN_IDENTITY,
            "profile": self._evidence["profile"],
            "role": role,
            "driver": selected_driver,
            "wrappers": selected_wrappers,
            "language": language,
            "evidence_sha256": self._evidence["evidence_sha256"],
            "profile_binding": copy.deepcopy(self._evidence["profile_binding"]),
            "host_fingerprint": self._evidence["host"]["fingerprint"],
            "environment_fingerprint": self._evidence["environment"]["fingerprint"],
            "tools": summaries,
        }
        identifier = stable_build_id("toolchain", core)
        record = {
            "toolchain_id": identifier,
            **core,
            "provenance": {"raw_fact_role": C_TOOLCHAIN_RAW_ROLE},
        }
        previous = self._records.get(identifier)
        if previous is not None and previous != record:
            raise ValueError("build_ir_c_toolchain_id_collision")
        if previous is None and len(self._records) >= MAX_PROJECTED_TOOLCHAINS:
            raise ValueError("build_ir_c_toolchain_limit_exceeded")
        self._records[identifier] = record
        return identifier

    def _required_tool(self, token: str, role: str) -> Mapping[str, Any]:
        value = self._tools.get(token)
        if value is None and isinstance(token, str):
            candidates = [
                item for item in self._tools.values()
                if item.get("basename") == tool_basename(token)
                and role in item.get("roles", [])
            ]
            if len(candidates) == 1:
                value = candidates[0]
            elif candidates:
                raise ValueError("build_ir_c_toolchain_selection_ambiguous")
        if value is None or value.get("status") != "ready" or role not in value["roles"]:
            raise ValueError("build_ir_c_toolchain_role_unbound")
        return value


def validate_host_bound_toolchains(value: Any) -> None:
    if (
        not isinstance(value, list) or not value
        or len(value) > MAX_PROJECTED_TOOLCHAINS
    ):
        raise ValueError("build_ir_host_toolchains_invalid")
    identifiers = []
    evidence_ids = set()
    for record in value:
        if not isinstance(record, Mapping) or set(record) != _RECORD_KEYS:
            raise ValueError("build_ir_host_toolchain_fields_invalid")
        _validate_record(record)
        identifiers.append(record["toolchain_id"])
        evidence_ids.add(record["evidence_sha256"])
    if identifiers != sorted(set(identifiers)) or len(evidence_ids) != 1:
        raise ValueError("build_ir_host_toolchains_order_invalid")


def _tool_summary(value: Mapping[str, Any], relation: str) -> dict[str, Any]:
    probes = {item["kind"]: item for item in value["probes"]}
    return {
        "token": value["token"],
        "relation": relation,
        "roles": list(value["roles"]),
        "family": value["family"],
        "basename": value["basename"],
        "resolved_path": value["resolved_path"],
        "binary": copy.deepcopy(value["binary"]),
        "probe_policy": value["probe_policy"],
        "version": _probe_summary(probes["version"]),
        "target": _probe_summary(probes["target"]),
        "sysroot": _probe_summary(probes["sysroot"]),
        "resource_dir": _probe_summary(probes["resource-dir"]),
    }


def _probe_summary(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": value["status"],
        "value": value["value"],
        "stdout_sha256": value["stdout_sha256"],
        "stderr_sha256": value["stderr_sha256"],
    }


def _validate_record(value: Mapping[str, Any]) -> None:
    core = {key: value[key] for key in _RECORD_KEYS - {"toolchain_id", "provenance"}}
    if (
        value.get("identity") != HOST_TOOLCHAIN_IDENTITY
        or value.get("profile") not in C_TOOLCHAIN_PROFILES
        or value.get("role") not in _ROLES
        or not _text(value.get("driver"))
        or not isinstance(value.get("wrappers"), list)
        or any(not _text(item) for item in value["wrappers"])
        or not _text(value.get("language"))
        or not is_sha256(value.get("evidence_sha256"))
        or not is_sha256(value.get("host_fingerprint"))
        or not is_sha256(value.get("environment_fingerprint"))
        or value.get("provenance") != {"raw_fact_role": C_TOOLCHAIN_RAW_ROLE}
        or value.get("toolchain_id") != stable_build_id("toolchain", core)
    ):
        raise ValueError("build_ir_host_toolchain_identity_invalid")
    binding = value.get("profile_binding")
    if binding is not None:
        try:
            validate_profile_binding(binding)
        except ValueError as error:
            raise ValueError("build_ir_host_toolchain_profile_invalid") from error
    elif value["profile"] == "competition":
        raise ValueError("build_ir_host_toolchain_profile_invalid")
    tools = value.get("tools")
    if not isinstance(tools, list) or not tools:
        raise ValueError("build_ir_host_toolchain_tools_invalid")
    for tool in tools:
        _validate_tool_summary(tool)
    drivers = [item for item in tools if item["relation"] == "driver"]
    wrappers = [item for item in tools if item["relation"] == "wrapper"]
    linkers = [item for item in tools if item["relation"] == "derived-linker"]
    if (
        len(drivers) != 1 or drivers[0]["token"] != value["driver"]
        or value["role"] not in drivers[0]["roles"]
        or [item["token"] for item in wrappers] != value["wrappers"]
        or any(item["roles"] != ["compiler-wrapper"] for item in wrappers)
        or any(item["roles"] != ["linker"] for item in linkers)
        or (value["role"] == "linker-driver") != bool(linkers)
    ):
        raise ValueError("build_ir_host_toolchain_tools_invalid")


def _validate_tool_summary(value: Any) -> None:
    if not isinstance(value, Mapping) or set(value) != _TOOL_KEYS:
        raise ValueError("build_ir_host_tool_summary_fields_invalid")
    binary = value.get("binary")
    if (
        not _text(value.get("token"))
        or value.get("relation") not in {"driver", "wrapper", "derived-linker"}
        or not isinstance(value.get("roles"), list) or not value["roles"]
        or not _text(value.get("family")) or not _text(value.get("basename"))
        or not _text(value.get("resolved_path"))
        or not isinstance(binary, Mapping) or set(binary) != {"sha256", "size_bytes"}
        or not is_sha256(binary.get("sha256"))
        or type(binary.get("size_bytes")) is not int or binary["size_bytes"] < 0
        or value.get("probe_policy") not in {"fixed-probes", "hash-only-wrapper"}
    ):
        raise ValueError("build_ir_host_tool_summary_invalid")
    try:
        family, basename = classify_tool_basename(value["basename"])
        validate_role_family(value["roles"], value["family"])
    except (KeyError, ValueError) as error:
        raise ValueError("build_ir_host_tool_summary_invalid") from error
    if family != value["family"] or basename != value["basename"]:
        raise ValueError("build_ir_host_tool_summary_invalid")
    for key in ("version", "target", "sysroot", "resource_dir"):
        probe = value.get(key)
        if (
            not isinstance(probe, Mapping) or set(probe) != _PROBE_KEYS
            or not _text(probe.get("status"))
            or (probe.get("value") is not None and not _text(probe["value"]))
            or not is_sha256(probe.get("stdout_sha256"))
            or not is_sha256(probe.get("stderr_sha256"))
        ):
            raise ValueError("build_ir_host_tool_probe_invalid")


def _text(value: Any) -> bool:
    return isinstance(value, str) and _TEXT.fullmatch(value) is not None


__all__ = [
    "HOST_TOOLCHAIN_IDENTITY", "HostToolchainProjection",
    "MAX_PROJECTED_TOOLCHAINS", "validate_host_bound_toolchains",
]
