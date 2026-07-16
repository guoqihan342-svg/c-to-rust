from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from .artifacts import content_sha256
from .project_test_inventory_meson_binding import (
    MAX_MESON_TEST_OUTPUT_BYTES, MAX_MESON_TEST_STDERR_BYTES,
    MESON_TEST_ADAPTER, validate_meson_test_build_binding,
)
from .sandbox_contract import contract_from_payload


MAX_PROJECT_TESTS = 10_000
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_OBSERVATION_KEYS = {
    "schema_version", "artifact_kind", "adapter_version", "command",
    "build_directory", "build_binding", "tool", "sandbox_launcher",
    "sandbox_contract", "sandbox_contract_sha256", "timeout_seconds",
    "returncode", "stdout_sha256", "stdout_size_bytes", "stderr_sha256",
    "stderr_size_bytes", "payload", "payload_sha256", "tests_executed",
    "semantic_gate", "observation_sha256",
}


def valid_meson_test_observation(value: Any) -> bool:
    try:
        if (
            not isinstance(value, Mapping) or set(value) != _OBSERVATION_KEYS
            or value.get("schema_version") != 1
            or value.get("artifact_kind")
            != "meson-introspect-tests-v1-observation"
            or value.get("adapter_version") != MESON_TEST_ADAPTER
            or value.get("tests_executed") is not False
            or value.get("semantic_gate") is not False
            or value.get("returncode") != 0
            or value.get("observation_sha256") != content_sha256({
                key: item for key, item in value.items()
                if key != "observation_sha256"
            })
        ):
            return False
        validate_meson_test_build_binding(value.get("build_binding"))
        build = value.get("build_directory")
        if value.get("command") != ["meson", "introspect", "--tests", build]:
            return False
        if value["build_binding"].get("build_directory") != build:
            return False
        payload = value.get("payload")
        if (
            not isinstance(payload, list) or len(payload) > MAX_PROJECT_TESTS
            or value.get("payload_sha256") != content_sha256(payload)
        ):
            return False
        tool, launcher = value.get("tool"), value.get("sandbox_launcher")
        if not _valid_identity(tool) or not _valid_identity(launcher):
            return False
        contract = contract_from_payload(value.get("sandbox_contract"))
        if (
            contract.sha256 != value.get("sandbox_contract_sha256")
            or contract.toolchain_sha256 != tool.get("sha256")
            or contract.launcher_sha256 != launcher.get("sha256")
        ):
            return False
        timeout = value.get("timeout_seconds")
        return (
            isinstance(timeout, int) and not isinstance(timeout, bool)
            and 5 <= timeout <= 120
            and _valid_output(value, "stdout", MAX_MESON_TEST_OUTPUT_BYTES)
            and _valid_output(value, "stderr", MAX_MESON_TEST_STDERR_BYTES)
        )
    except (TypeError, ValueError):
        return False


def _valid_identity(value: Any) -> bool:
    size = value.get("size_bytes") if isinstance(value, Mapping) else None
    return (
        isinstance(value, Mapping)
        and set(value) == {"basename", "sha256", "size_bytes"}
        and isinstance(value.get("basename"), str) and bool(value["basename"])
        and "/" not in value["basename"] and "\\" not in value["basename"]
        and _SHA256.fullmatch(str(value.get("sha256"))) is not None
        and isinstance(size, int) and not isinstance(size, bool)
        and 0 < size <= 1024 * 1024 * 1024
    )


def _valid_output(value: Mapping[str, Any], prefix: str, maximum: int) -> bool:
    size = value.get(f"{prefix}_size_bytes")
    return (
        _SHA256.fullmatch(str(value.get(f"{prefix}_sha256"))) is not None
        and isinstance(size, int) and not isinstance(size, bool)
        and 0 <= size <= maximum
    )


__all__ = ["MAX_PROJECT_TESTS", "valid_meson_test_observation"]
