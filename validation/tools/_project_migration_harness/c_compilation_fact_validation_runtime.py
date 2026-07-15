from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any

from .artifacts import content_sha256
from .build_ir import is_sha256
from .host_tool_binding import classify_tool_basename, validate_role_family
from .sandbox_contract import contract_from_payload
from .sandbox_probe import (
    probe_receipt_from_payload, validate_probe_receipt,
)
from .sandbox_toolchain import MAX_TOOL_BYTES


_SANDBOX_FIELDS = {
    "contract", "contract_sha256", "probe", "probe_sha256",
}
_TOOLCHAIN_FIELDS = {
    "schema_version", "artifact_kind", "toolchain_id", "family",
    "basename", "binary", "target", "version", "binding_sha256",
}
_PROBE_FIELDS = {"status", "value", "stdout_sha256", "stderr_sha256"}
_TEXT = re.compile(r"[^\r\n\x00]{1,4096}\Z")


def validate_compilation_runtime(
    sandbox: Any, toolchains: Any,
) -> tuple[dict[str, dict[str, Any]], str]:
    if not isinstance(toolchains, list) or not toolchains:
        raise ValueError("c_compilation_fact_toolchains_invalid")
    checked = [_validate_toolchain(item) for item in toolchains]
    identifiers = [item["toolchain_id"] for item in checked]
    if identifiers != sorted(set(identifiers)):
        raise ValueError("c_compilation_fact_toolchains_order_invalid")
    if not isinstance(sandbox, Mapping) or set(sandbox) != _SANDBOX_FIELDS:
        raise ValueError("c_compilation_fact_bundle_sandbox_invalid")
    try:
        contract = contract_from_payload(sandbox.get("contract"))
        probe = probe_receipt_from_payload(sandbox.get("probe"))
        validate_probe_receipt(probe, contract, contract.requirements)
    except (TypeError, ValueError) as error:
        raise ValueError("c_compilation_fact_sandbox_binding_invalid") from error
    if (
        sandbox.get("contract_sha256") != contract.sha256
        or sandbox.get("probe_sha256") != probe.sha256
        or contract.toolchain_sha256 != content_sha256(checked)
    ):
        raise ValueError("c_compilation_fact_sandbox_binding_invalid")
    return {item["toolchain_id"]: item for item in checked}, probe.sha256


def _validate_toolchain(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _TOOLCHAIN_FIELDS:
        raise ValueError("c_compilation_fact_toolchain_fields_invalid")
    binding = dict(value)
    core = {key: binding[key] for key in _TOOLCHAIN_FIELDS - {"binding_sha256"}}
    binary = binding.get("binary")
    if (
        binding.get("schema_version") != 1
        or binding.get("artifact_kind") != "c-compiler-portable-binding"
        or not _text(binding.get("toolchain_id"))
        or not isinstance(binary, Mapping)
        or set(binary) != {"sha256", "size_bytes"}
        or not is_sha256(binary.get("sha256"))
        or type(binary.get("size_bytes")) is not int
        or not 0 < binary["size_bytes"] <= MAX_TOOL_BYTES
        or binding.get("binding_sha256") != content_sha256(core)
    ):
        raise ValueError("c_compilation_fact_toolchain_invalid")
    try:
        family, basename = classify_tool_basename(binding.get("basename"))
        validate_role_family(("compiler-driver",), family)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("c_compilation_fact_toolchain_invalid") from error
    if family != binding.get("family") or basename != binding.get("basename"):
        raise ValueError("c_compilation_fact_toolchain_invalid")
    _validate_probe(binding.get("target"))
    _validate_probe(binding.get("version"))
    return binding


def _validate_probe(value: Any) -> None:
    if (
        not isinstance(value, Mapping)
        or set(value) != _PROBE_FIELDS
        or value.get("status") != "reported"
        or not _text(value.get("value"))
        or not is_sha256(value.get("stdout_sha256"))
        or not is_sha256(value.get("stderr_sha256"))
    ):
        raise ValueError("c_compilation_fact_toolchain_probe_invalid")


def _text(value: Any) -> bool:
    return isinstance(value, str) and _TEXT.fullmatch(value) is not None


__all__ = ["validate_compilation_runtime"]
