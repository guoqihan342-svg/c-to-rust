from __future__ import annotations

from collections.abc import Mapping
import hashlib
import os
import platform
from typing import Any

from .artifacts import content_sha256
from .host_tool_binding import ENVIRONMENT_ALLOWLIST


MAX_ENVIRONMENT_VALUE_BYTES = 256 * 1024


def environment_values(value: Mapping[str, str] | None) -> dict[str, str]:
    source = os.environ if value is None else value
    if not isinstance(source, Mapping):
        raise ValueError("c_toolchain_environment_invalid")
    result: dict[str, str] = {}
    for name in ENVIRONMENT_ALLOWLIST:
        item = _environment_value(source, name)
        if item is None:
            continue
        if (
            type(item) is not str
            or len(item.encode("utf-8")) > MAX_ENVIRONMENT_VALUE_BYTES
            or "\x00" in item
        ):
            raise ValueError("c_toolchain_environment_value_invalid")
        result[name] = item
    return result


def environment_binding(value: Mapping[str, str]) -> dict[str, Any]:
    variables = [
        {"name": name, "value_sha256": _text_sha256(item)}
        for name, item in sorted(value.items())
    ]
    path = value.get("PATH", "")
    flavor = host_binding(value)["path_flavor"]
    separator = ";" if flavor == "windows" else ":"
    entries = path.split(separator) if path else []
    path_snapshot = {
        "entry_count": len(entries),
        "value_sha256": _text_sha256(path),
        "fingerprint": content_sha256({
            "path_flavor": flavor,
            "entries": entries,
        }),
    }
    core = {"variables": variables, "path_snapshot": path_snapshot}
    return {**core, "fingerprint": content_sha256(core)}


def host_binding(environment: Mapping[str, str]) -> dict[str, Any]:
    system = platform.system().strip().lower() or "unknown"
    machine = platform.machine().strip().lower() or "unknown"
    wsl = system == "linux" and (
        "microsoft" in platform.release().lower()
        or "WSL_DISTRO_NAME" in environment
        or "WSL_INTEROP" in environment
    )
    distro = environment.get("WSL_DISTRO_NAME")
    core = {
        "system": system,
        "machine": machine,
        "wsl": wsl,
        "wsl_distribution_sha256": _text_sha256(distro) if distro else None,
        "path_flavor": "windows" if system == "windows" else "posix",
    }
    return {**core, "fingerprint": content_sha256(core)}


def _environment_value(
    value: Mapping[str, str], name: str,
) -> str | None:
    if name in value:
        return value[name]
    if os.name == "nt":
        folded = name.casefold()
        return next(
            (item for key, item in value.items() if str(key).casefold() == folded),
            None,
        )
    return None


def _text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


__all__ = ["environment_binding", "environment_values", "host_binding"]
