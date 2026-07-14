from __future__ import annotations

from collections.abc import Mapping
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any

from .c_toolchain_files import read_stable_file


COMPETITION_PROFILE_PATH = "config/competition-env/environment.json"
MAX_PROFILE_BYTES = 1024 * 1024

_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)


def repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def competition_profile_file() -> Path:
    return repository_root().joinpath(*PurePosixPath(COMPETITION_PROFILE_PATH).parts)


def competition_profile_binding() -> dict[str, Any]:
    data, identity = read_stable_file(
        competition_profile_file(), MAX_PROFILE_BYTES,
    )
    profile = _parse_profile(data)
    return validate_profile_binding({
        "path": COMPETITION_PROFILE_PATH,
        "sha256": identity["sha256"],
        "size_bytes": identity["size_bytes"],
        "profile_id": profile["profile_id"],
    })


def validate_profile_binding(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "path", "sha256", "size_bytes", "profile_id",
    }:
        raise ValueError("c_toolchain_profile_binding_fields_invalid")
    if value.get("path") != COMPETITION_PROFILE_PATH:
        raise ValueError("c_toolchain_profile_path_invalid")
    size = value.get("size_bytes")
    if type(size) is not int or not 0 < size <= MAX_PROFILE_BYTES:
        raise ValueError("c_toolchain_profile_size_invalid")
    digest = value.get("sha256")
    if type(digest) is not str or not _SHA256.fullmatch(digest):
        raise ValueError("c_toolchain_profile_sha256_invalid")
    profile_id = value.get("profile_id")
    if (
        type(profile_id) is not str
        or not profile_id
        or len(profile_id.encode("utf-8")) > 4096
    ):
        raise ValueError("c_toolchain_profile_id_invalid")
    return {
        key: value[key]
        for key in ("path", "sha256", "size_bytes", "profile_id")
    }


def reopen_profile_binding(
    value: Any,
) -> tuple[dict[str, Any], dict[str, str]]:
    binding = validate_profile_binding(value)
    data, identity = read_stable_file(
        competition_profile_file(), MAX_PROFILE_BYTES,
    )
    if identity != {
        "sha256": binding["sha256"],
        "size_bytes": binding["size_bytes"],
    }:
        raise ValueError("c_toolchain_profile_binding_drift")
    profile = _parse_profile(data)
    if profile["profile_id"] != binding["profile_id"]:
        raise ValueError("c_toolchain_profile_binding_drift")
    return binding, {
        "os_name": profile["os"]["name"],
        "gcc_version": profile["toolchain"]["gcc"],
    }


def _parse_profile(data: bytes) -> Mapping[str, Any]:
    try:
        profile = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("c_toolchain_profile_json_invalid") from error
    if not isinstance(profile, Mapping):
        raise ValueError("c_toolchain_profile_schema_invalid")
    os_value = profile.get("os")
    toolchain = profile.get("toolchain")
    if (
        profile.get("schema_version") != 1
        or profile.get("status") != "required"
        or profile.get("canonical_path") != COMPETITION_PROFILE_PATH
        or type(profile.get("profile_id")) is not str
        or not profile["profile_id"]
        or not isinstance(os_value, Mapping)
        or not _bounded_text(os_value.get("name"))
        or not isinstance(toolchain, Mapping)
        or not _bounded_text(toolchain.get("gcc"))
    ):
        raise ValueError("c_toolchain_profile_schema_invalid")
    return profile


def _bounded_text(value: Any) -> bool:
    return (
        type(value) is str
        and bool(value)
        and "\x00" not in value
        and "\r" not in value
        and "\n" not in value
        and len(value.encode("utf-8")) <= 4096
    )


__all__ = [
    "COMPETITION_PROFILE_PATH", "MAX_PROFILE_BYTES",
    "competition_profile_binding", "competition_profile_file",
    "reopen_profile_binding", "repository_root", "validate_profile_binding",
]
