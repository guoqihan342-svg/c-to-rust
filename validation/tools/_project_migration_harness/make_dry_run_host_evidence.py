from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any

from .artifacts import canonical_json_bytes, content_sha256
from .build_ir import is_sha256


MAKE_PREFLIGHT_KIND = "project-migration-make-host-preflight"
MAKE_REQUIRED_CAPABILITIES = (
    "child-process-containment", "cpu-limit", "environment-allowlist",
    "exit-cleanup", "file-size-limit", "independent-output-root",
    "memory-limit", "network-isolation", "open-files-limit", "output-limit",
    "privileges-dropped", "process-count-limit", "project-read-only",
    "temporary-isolated", "toolchain-read-only", "user-namespace",
    "wall-timeout",
)
MAKE_ENVIRONMENT = (
    ("HOME", "/home/sandbox"),
    ("LANG", "C.UTF-8"),
    ("LC_ALL", "C.UTF-8"),
    ("MAKEFLAGS", ""),
    ("PATH", "/toolchain/bin:/usr/bin:/bin"),
    ("TMPDIR", "/tmp"),
    ("TZ", "UTC"),
)
MAKE_RESOURCE_LIMITS = (
    ("address_space_bytes", 4 * 1024 * 1024 * 1024),
    ("cpu_seconds", 300),
    ("file_size_bytes", 64 * 1024 * 1024),
    ("open_files", 256),
    ("process_count", 64),
)
_BACKEND = re.compile(r"[a-z][a-z0-9_.-]{0,63}\Z", re.ASCII)
_VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}\Z", re.ASCII)
_FIELDS = {
    "schema_version", "artifact_kind", "status", "backend", "backend_version",
    "plan_sha256", "toolchain_sha256", "launcher_sha256", "make_sha256",
    "probe_observation_sha256", "capability_results", "environment",
    "resource_limits", "cleanup_ready", "semantic_gate",
    "translation_coverage_numerator", "preflight_sha256",
}


def create_make_host_preflight(
    *, backend: str, backend_version: str, plan_sha256: str,
    toolchain_sha256: str, launcher_sha256: str, make_sha256: str,
    probe_observation_sha256: str,
    capability_results: Mapping[str, bool], cleanup_ready: bool,
) -> dict[str, Any]:
    core = {
        "schema_version": 2,
        "artifact_kind": MAKE_PREFLIGHT_KIND,
        "status": "passed",
        "backend": backend,
        "backend_version": backend_version,
        "plan_sha256": plan_sha256,
        "toolchain_sha256": toolchain_sha256,
        "launcher_sha256": launcher_sha256,
        "make_sha256": make_sha256,
        "probe_observation_sha256": probe_observation_sha256,
        "capability_results": dict(sorted(capability_results.items())),
        "environment": dict(MAKE_ENVIRONMENT),
        "resource_limits": dict(MAKE_RESOURCE_LIMITS),
        "cleanup_ready": cleanup_ready,
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
    }
    return validate_make_host_preflight({
        **core, "preflight_sha256": content_sha256(core),
    })


def validate_make_host_preflight(
    value: Any, *, expected_plan_sha256: str | None = None,
    expected_toolchain_sha256: str | None = None,
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _FIELDS:
        raise ValueError("make_host_preflight_fields_invalid")
    capabilities = value.get("capability_results")
    if (
        value.get("schema_version") != 2
        or value.get("artifact_kind") != MAKE_PREFLIGHT_KIND
        or value.get("status") != "passed"
        or not isinstance(value.get("backend"), str)
        or _BACKEND.fullmatch(value["backend"]) is None
        or not isinstance(value.get("backend_version"), str)
        or _VERSION.fullmatch(value["backend_version"]) is None
        or not is_sha256(value.get("plan_sha256"))
        or not is_sha256(value.get("toolchain_sha256"))
        or not is_sha256(value.get("launcher_sha256"))
        or not is_sha256(value.get("make_sha256"))
        or not is_sha256(value.get("probe_observation_sha256"))
        or not isinstance(capabilities, Mapping)
        or list(capabilities) != list(MAKE_REQUIRED_CAPABILITIES)
        or any(capabilities.get(name) is not True for name in MAKE_REQUIRED_CAPABILITIES)
        or value.get("environment") != dict(MAKE_ENVIRONMENT)
        or value.get("resource_limits") != dict(MAKE_RESOURCE_LIMITS)
        or value.get("cleanup_ready") is not True
        or value.get("semantic_gate") is not False
        or value.get("translation_coverage_numerator") != 0
    ):
        raise ValueError("make_host_preflight_policy_invalid")
    if expected_plan_sha256 is not None and value["plan_sha256"] != expected_plan_sha256:
        raise ValueError("make_host_preflight_plan_drift")
    if (
        expected_toolchain_sha256 is not None
        and value["toolchain_sha256"] != expected_toolchain_sha256
    ):
        raise ValueError("make_host_preflight_toolchain_drift")
    core = {key: value[key] for key in _FIELDS if key != "preflight_sha256"}
    if value.get("preflight_sha256") != content_sha256(core):
        raise ValueError("make_host_preflight_sha256_invalid")
    return dict(value)


def canonical_make_host_preflight_bytes(value: Any) -> bytes:
    return canonical_json_bytes(validate_make_host_preflight(value))


__all__ = [
    "MAKE_ENVIRONMENT", "MAKE_REQUIRED_CAPABILITIES", "MAKE_RESOURCE_LIMITS",
    "canonical_make_host_preflight_bytes", "create_make_host_preflight",
    "validate_make_host_preflight",
]
