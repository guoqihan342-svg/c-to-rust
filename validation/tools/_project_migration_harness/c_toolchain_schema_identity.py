from __future__ import annotations

from collections.abc import Mapping
from pathlib import PurePosixPath, PureWindowsPath
import re
from typing import Any

from .artifacts import content_sha256
from .host_tool_binding import (
    COMPETITION_PROFILE_PATH, ENVIRONMENT_ALLOWLIST, MAX_PROFILE_BYTES,
    MAX_TOOL_REQUESTS, TOOL_ROLES, classify_tool_basename,
    validate_role_family,
)


_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_TEXT = re.compile(r"[^\r\n\x00]{1,4096}\Z")
_REQUEST_KEYS = {"token", "roles"}
_HOST_KEYS = {
    "system", "machine", "wsl", "wsl_distribution_sha256", "path_flavor",
    "fingerprint",
}
_ENV_KEYS = {"variables", "path_snapshot", "fingerprint"}
_PATH_KEYS = {"entry_count", "value_sha256", "fingerprint"}


def validate_profile_binding(value: Any, profile: str) -> None:
    if value is None:
        if profile == "competition":
            raise ValueError("c_toolchain_competition_profile_binding_required")
        return
    if not isinstance(value, Mapping) or set(value) != {
        "path", "sha256", "size_bytes", "profile_id",
    }:
        raise ValueError("c_toolchain_profile_binding_fields_invalid")
    if (
        value.get("path") != COMPETITION_PROFILE_PATH
        or not is_sha256(value.get("sha256"))
        or type(value.get("size_bytes")) is not int
        or not 0 < value["size_bytes"] <= MAX_PROFILE_BYTES
        or not is_text(value.get("profile_id"))
    ):
        raise ValueError("c_toolchain_profile_binding_invalid")


def validate_requests(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ValueError("c_toolchain_requests_invalid")
    if len(value) > MAX_TOOL_REQUESTS:
        raise ValueError("c_toolchain_requests_limit_exceeded")
    tokens: list[str] = []
    for item in value:
        if not isinstance(item, Mapping) or set(item) != _REQUEST_KEYS:
            raise ValueError("c_toolchain_request_fields_invalid")
        token, roles = item.get("token"), item.get("roles")
        if not is_text(token) or not isinstance(roles, list) or not roles:
            raise ValueError("c_toolchain_request_invalid")
        if any(type(role) is not str or role not in TOOL_ROLES for role in roles):
            raise ValueError("c_toolchain_request_invalid")
        if roles != sorted(set(roles)):
            raise ValueError("c_toolchain_request_invalid")
        family, _ = classify_tool_basename(basename(token))
        validate_role_family(roles, family)
        tokens.append(token)
    if tokens != sorted(set(tokens)):
        raise ValueError("c_toolchain_request_order_invalid")
    return value


def validate_host(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _HOST_KEYS:
        raise ValueError("c_toolchain_host_fields_invalid")
    if (
        not is_text(value.get("system"))
        or not is_text(value.get("machine"))
        or type(value.get("wsl")) is not bool
        or value.get("path_flavor") not in {"posix", "windows"}
        or (value["system"] == "windows")
        != (value["path_flavor"] == "windows")
        or (
            value.get("wsl_distribution_sha256") is not None
            and not is_sha256(value["wsl_distribution_sha256"])
        )
    ):
        raise ValueError("c_toolchain_host_invalid")
    core = {key: value[key] for key in _HOST_KEYS if key != "fingerprint"}
    if value.get("fingerprint") != content_sha256(core):
        raise ValueError("c_toolchain_host_fingerprint_invalid")
    return value


def validate_environment(value: Any) -> None:
    if not isinstance(value, Mapping) or set(value) != _ENV_KEYS:
        raise ValueError("c_toolchain_environment_fields_invalid")
    variables = value.get("variables")
    if not isinstance(variables, list):
        raise ValueError("c_toolchain_environment_invalid")
    names = []
    for item in variables:
        if not isinstance(item, Mapping) or set(item) != {
            "name", "value_sha256",
        }:
            raise ValueError("c_toolchain_environment_variable_invalid")
        if (
            item.get("name") not in ENVIRONMENT_ALLOWLIST
            or not is_sha256(item.get("value_sha256"))
        ):
            raise ValueError("c_toolchain_environment_variable_invalid")
        names.append(item["name"])
    if names != sorted(set(names)):
        raise ValueError("c_toolchain_environment_order_invalid")
    snapshot = value.get("path_snapshot")
    if (
        not isinstance(snapshot, Mapping)
        or set(snapshot) != _PATH_KEYS
        or type(snapshot.get("entry_count")) is not int
        or not 0 <= snapshot["entry_count"] <= 65536
        or not is_sha256(snapshot.get("value_sha256"))
        or not is_sha256(snapshot.get("fingerprint"))
    ):
        raise ValueError("c_toolchain_path_snapshot_invalid")
    core = {"variables": variables, "path_snapshot": snapshot}
    if value.get("fingerprint") != content_sha256(core):
        raise ValueError("c_toolchain_environment_fingerprint_invalid")


def string_list(value: Any, code: str) -> list[str]:
    if not isinstance(value, list) or any(not is_text(item) for item in value):
        raise ValueError(code)
    return value


def basename(value: str) -> str:
    return value.replace("\\", "/").rsplit("/", 1)[-1]


def is_absolute(value: Any, flavor: str) -> bool:
    if not is_text(value):
        return False
    path = PureWindowsPath(value) if flavor == "windows" else PurePosixPath(value)
    return path.is_absolute() and ".." not in path.parts


def is_sha256(value: Any) -> bool:
    return type(value) is str and _SHA256.fullmatch(value) is not None


def is_text(value: Any) -> bool:
    return type(value) is str and _TEXT.fullmatch(value) is not None


__all__ = [
    "basename", "is_absolute", "is_sha256", "is_text", "string_list",
    "validate_environment", "validate_host", "validate_profile_binding",
    "validate_requests",
]
