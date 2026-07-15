from __future__ import annotations

import copy
import re
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from .artifacts import canonical_json_bytes, content_sha256
from .c_toolchain_reopen import collect_c_toolchain_evidence, reopen_c_toolchain_evidence
from .c_toolchain_schema import (
    C_TOOLCHAIN_PROFILES, tool_records_by_token, validate_c_toolchain_evidence,
)
from .c_toolchain_schema_identity import is_sha256, validate_profile_binding
from .clang_fact_commands import CLANG_TOOLCHAIN_BINDING_KIND
from .gate_evidence import (
    read_content_addressed_json, require_host_raw_reference,
    write_content_addressed_json,
)
from .ledger_security import LedgerError


CLANG_REQUEST = {"token": "clang", "roles": ["compiler-driver"]}
CLANG_HOST_EVIDENCE_SCOPE = "raw/clang-toolchain-host"
CLANG_HOST_RECEIPT_KIND = "clang-toolchain-host-receipt"
_BINDING_KEYS = {"schema_version", "artifact_kind", "status", "family",
                 "basename", "binary", "version", "target", "resource_dir",
                 "sysroot", "binding_sha256"}
_RECEIPT_KEYS = {"schema_version", "artifact_kind", "status", "portable_binding",
                 "profile", "profile_binding", "host_evidence", "section_closure",
                 "semantic_gate", "translation_coverage_numerator", "receipt_sha256"}
_VALUE_PROBE_KEYS = {"status", "value", "stdout_sha256", "stderr_sha256"}
_PATH_PROBE_KEYS = {"status", "stdout_sha256", "stderr_sha256"}
_EXPECTED_PROBES = {
    "version": (["--no-default-config", "--version"], "reported"),
    "target": (["--no-default-config", "-print-target-triple"], "reported"),
    "sysroot": ([], "not-applicable"),
    "resource-dir": (["--no-default-config", "-print-resource-dir"],
                     "reported"),
}

def collect_clang_host_evidence(
    *, profile: str = "competition",
    environment: Mapping[str, str] | None = None,
    resolver: Any = None,
    runner: Any = None,
    profile_binding: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    evidence = collect_c_toolchain_evidence(
        [CLANG_REQUEST], profile=profile, environment=environment,
        resolver=resolver, runner=runner, profile_binding=profile_binding,
    )
    _clang_tool(evidence)
    return evidence

def collect_clang_toolchain_binding(**kwargs: Any) -> dict[str, Any]:
    return _portable_binding(collect_clang_host_evidence(**kwargs))

def persist_clang_toolchain_binding(
    out_root: Path,
    host_evidence: Mapping[str, Any] | None = None,
    *, profile: str = "competition",
    environment: Mapping[str, str] | None = None,
    resolver: Any = None,
    runner: Any = None,
    profile_binding: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    evidence = (
        collect_clang_host_evidence(
            profile=profile, environment=environment, resolver=resolver,
            runner=runner, profile_binding=profile_binding,
        )
        if host_evidence is None else copy.deepcopy(dict(host_evidence))
    )
    _clang_tool(evidence)
    reference = write_content_addressed_json(
        Path(out_root), CLANG_HOST_EVIDENCE_SCOPE, evidence,
    )
    return validate_clang_toolchain_receipt(_receipt(evidence, reference))

def validate_clang_toolchain_binding(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _BINDING_KEYS:
        raise ValueError("clang_toolchain_binding_fields_invalid")
    binding = copy.deepcopy(dict(value))
    binary = binding.get("binary")
    core = {key: binding[key] for key in binding if key != "binding_sha256"}
    if (
        binding.get("schema_version") != 1
        or binding.get("artifact_kind") != CLANG_TOOLCHAIN_BINDING_KIND
        or binding.get("status") != "ready"
        or binding.get("family") != "clang-compiler"
        or binding.get("basename") != "clang"
        or not isinstance(binary, Mapping)
        or set(binary) != {"sha256", "size_bytes"}
        or not is_sha256(binary.get("sha256"))
        or type(binary.get("size_bytes")) is not int
        or binary["size_bytes"] <= 0
        or binding.get("binding_sha256") != content_sha256(core)
    ):
        raise ValueError("clang_toolchain_binding_invalid")
    version = _value_probe(binding.get("version"), "version")
    target = _value_probe(binding.get("target"), "target")
    if re.search(r"\bclang version [0-9]", version["value"], re.I) is None:
        raise ValueError("clang_toolchain_version_invalid")
    if re.fullmatch(r"[a-z0-9][a-z0-9_.+]*(?:-[a-z0-9][a-z0-9_.+]*)+", target["value"]) is None:
        raise ValueError("clang_toolchain_target_invalid")
    _path_probe(binding.get("resource_dir"), "resource_dir", {"reported"})
    _path_probe(
        binding.get("sysroot"), "sysroot",
        {"reported", "reported-empty/default", "not-applicable"},
    )
    return binding

def validate_clang_toolchain_receipt(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _RECEIPT_KEYS:
        raise ValueError("clang_toolchain_receipt_fields_invalid")
    receipt = copy.deepcopy(dict(value))
    profile = receipt.get("profile")
    if profile not in C_TOOLCHAIN_PROFILES:
        raise ValueError("clang_toolchain_receipt_profile_invalid")
    validate_profile_binding(receipt.get("profile_binding"), str(profile))
    validate_clang_toolchain_binding(receipt.get("portable_binding"))
    _validate_host_reference(receipt.get("host_evidence"))
    core = {key: receipt[key] for key in receipt if key != "receipt_sha256"}
    if (
        receipt.get("schema_version") != 1
        or receipt.get("artifact_kind") != CLANG_HOST_RECEIPT_KIND
        or receipt.get("status") != "ready"
        or receipt.get("section_closure") is not False
        or receipt.get("semantic_gate") is not False
        or type(receipt.get("translation_coverage_numerator")) is not int
        or receipt["translation_coverage_numerator"] != 0
        or receipt.get("receipt_sha256") != content_sha256(core)
    ):
        raise ValueError("clang_toolchain_receipt_invalid")
    return receipt

def reopen_clang_toolchain_binding(
    ledger_path: Path,
    value: Mapping[str, Any],
    *, environment: Mapping[str, str] | None = None,
    resolver: Any = None,
    runner: Any = None,
    profile_binding: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    receipt = validate_clang_toolchain_receipt(value)
    database = _fixed_ledger_path(ledger_path)
    reference = receipt["host_evidence"]
    evidence = read_content_addressed_json(
        database, reference["path"], reference["sha256"],
    )
    if len(canonical_json_bytes(evidence)) != reference["size_bytes"]:
        raise LedgerError("Clang host evidence size drifted")
    _clang_tool(evidence)
    if _receipt(evidence, reference) != receipt:
        raise LedgerError("Clang toolchain receipt drifted")
    expected_profile = receipt["profile_binding"]
    if profile_binding is not None and dict(profile_binding) != expected_profile:
        raise LedgerError("Clang toolchain profile binding drifted")
    try:
        current = reopen_c_toolchain_evidence(
            evidence, environment=environment, resolver=resolver, runner=runner,
            profile_binding=expected_profile,
        )
    except (OSError, TypeError, ValueError) as error:
        raise LedgerError("Clang toolchain live evidence drifted") from error
    if current != evidence or _receipt(current, reference) != receipt:
        raise LedgerError("Clang toolchain live evidence drifted")
    return receipt

reopen_and_validate_clang_toolchain_binding = reopen_clang_toolchain_binding
reopen_clang_toolchain_receipt = reopen_clang_toolchain_binding

def _clang_tool(evidence: Any) -> dict[str, Any]:
    validate_c_toolchain_evidence(evidence)
    if evidence.get("requests") != [CLANG_REQUEST]:
        raise ValueError("clang_toolchain_fixed_request_required")
    records = tool_records_by_token(evidence)
    if set(records) != {"clang"}:
        raise ValueError("clang_toolchain_tool_set_invalid")
    tool = records["clang"]
    if (
        evidence.get("status") != "ready"
        or tool.get("status") != "ready"
        or tool.get("family") != "clang-compiler"
        or tool.get("basename") != "clang"
        or tool.get("roles") != ["compiler-driver"]
    ):
        raise ValueError("clang_toolchain_ready_clang_required")
    probes = {item["kind"]: item for item in tool["probes"]}
    for kind, (arguments, status) in _EXPECTED_PROBES.items():
        probe = probes.get(kind)
        if not isinstance(probe, Mapping) or (
            probe.get("arguments") != arguments or probe.get("status") != status
        ):
            raise ValueError(f"clang_toolchain_{kind}_probe_invalid")
    version = probes["version"].get("value")
    if type(version) is not str or re.search(r"\bclang version [0-9]", version, re.I) is None:
        raise ValueError("clang_toolchain_version_family_mismatch")
    return tool

def _portable_binding(evidence: Mapping[str, Any]) -> dict[str, Any]:
    tool = _clang_tool(evidence)
    probes = {item["kind"]: item for item in tool["probes"]}
    core = {
        "schema_version": 1,
        "artifact_kind": CLANG_TOOLCHAIN_BINDING_KIND,
        "status": "ready",
        "family": "clang-compiler",
        "basename": "clang",
        "binary": copy.deepcopy(tool["binary"]),
        "version": _value_projection(probes["version"]),
        "target": _value_projection(probes["target"]),
        "resource_dir": _path_projection(probes["resource-dir"]),
        "sysroot": _path_projection(probes["sysroot"]),
    }
    return {**core, "binding_sha256": content_sha256(core)}

def _receipt(
    evidence: Mapping[str, Any], reference: Mapping[str, Any],
) -> dict[str, Any]:
    core = {
        "schema_version": 1,
        "artifact_kind": CLANG_HOST_RECEIPT_KIND,
        "status": "ready",
        "portable_binding": _portable_binding(evidence),
        "profile": evidence["profile"],
        "profile_binding": copy.deepcopy(evidence["profile_binding"]),
        "host_evidence": dict(reference),
        "section_closure": False,
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
    }
    return {**core, "receipt_sha256": content_sha256(core)}

def _value_projection(probe: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": probe["status"], "value": probe["value"],
        "stdout_sha256": probe["stdout_sha256"],
        "stderr_sha256": probe["stderr_sha256"],
    }

def _path_projection(probe: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": probe["status"], "stdout_sha256": probe["stdout_sha256"],
        "stderr_sha256": probe["stderr_sha256"],
    }

def _value_probe(value: Any, name: str) -> dict[str, str]:
    if (
        not isinstance(value, Mapping) or set(value) != _VALUE_PROBE_KEYS
        or value.get("status") != "reported"
        or type(value.get("value")) is not str or not value["value"]
        or not all(is_sha256(value.get(key)) for key in ("stdout_sha256", "stderr_sha256"))
    ):
        raise ValueError(f"clang_toolchain_{name}_probe_invalid")
    return dict(value)

def _path_probe(value: Any, name: str, statuses: set[str]) -> None:
    if (
        not isinstance(value, Mapping) or set(value) != _PATH_PROBE_KEYS
        or value.get("status") not in statuses
        or not all(is_sha256(value.get(key)) for key in ("stdout_sha256", "stderr_sha256"))
    ):
        raise ValueError(f"clang_toolchain_{name}_probe_invalid")

def _validate_host_reference(value: Any) -> None:
    if not isinstance(value, Mapping):
        raise ValueError("clang_toolchain_host_reference_invalid")
    try:
        require_host_raw_reference(value, "clang-toolchain-host")
    except LedgerError as error:
        raise ValueError("clang_toolchain_host_reference_invalid") from error
    parts = PurePosixPath(str(value["path"])).parts
    expected = (
        "verification", "raw", "clang-toolchain-host",
        f"{value['sha256']}.json",
    )
    if parts != expected:
        raise ValueError("clang_toolchain_host_reference_path_invalid")

def _fixed_ledger_path(value: Path) -> Path:
    database = Path(value).resolve()
    if database.name != "project-migration.sqlite3" or database.parent.name != "state":
        raise LedgerError("Clang toolchain requires the fixed ledger state path")
    return database

__all__ = [
    "CLANG_HOST_EVIDENCE_SCOPE", "CLANG_HOST_RECEIPT_KIND", "CLANG_REQUEST",
    "collect_clang_host_evidence", "collect_clang_toolchain_binding",
    "persist_clang_toolchain_binding", "reopen_clang_toolchain_binding",
    "reopen_and_validate_clang_toolchain_binding",
    "reopen_clang_toolchain_receipt", "validate_clang_toolchain_binding",
    "validate_clang_toolchain_receipt",
]
