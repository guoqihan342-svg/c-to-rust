"""Project a verified native build closure into translator-safe metadata."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .native_build_closure import resolve_native_build_closure


_WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:[\\/]")
_FORBIDDEN_KEYS = {
    "argv",
    "command",
    "arguments",
    "working_directory",
    "output",
    "output_path",
}


def resolve_native_build_context(
    spec: Mapping[str, Any] | Any,
    repo_root: str | Path,
) -> dict[str, Any] | None:
    """Return a strict, harness-independent translator projection.

    The native closure resolver remains the source of truth for schema, path,
    hash, and artifact verification. Command construction fields are discarded.
    """

    root = Path(repo_root).absolute()
    contract = resolve_native_build_closure(
        spec,
        root,
        root,
        root / ".native-build-context-probe.c",
    )
    if contract is None:
        return None

    projection = {
        "schema_version": 1,
        "mode": contract["mode"],
        "closure_manifest": _copy_ref(contract["closure_manifest"]),
        "source_root": _copy_ref(contract["source_root_ref"]),
        "compile_database": _copy_ref(contract["compile_database"]),
        "defines": list(contract["defines"]),
        "source_include_dirs": [
            _copy_ref(item) for item in contract["source_include_dirs"]
        ],
        "generated_include_dirs": [
            _copy_ref(item) for item in contract["generated_include_dirs"]
        ],
        "include_paths": list(contract["resolved_include_paths"]),
        "target_abi": dict(contract["target_abi"]),
        "toolchain": dict(contract["toolchain"]),
        "build_config": {
            **contract["build_config"],
            "configure_defines": list(
                contract["build_config"]["configure_defines"]
            ),
        },
        "symbol_bindings": [
            {
                "source_symbol": item["source_symbol"],
                "linked_symbol": item["linked_symbol"],
                "artifact": _copy_ref(item["artifact"]),
            }
            for item in contract["symbol_bindings"]
        ],
    }
    _reject_unsafe_projection(projection)
    return projection


def _copy_ref(value: Mapping[str, Any]) -> dict[str, str]:
    return {"path": str(value["path"]), "sha256": str(value["sha256"])}


def _reject_unsafe_projection(value: Any, label: str = "native_build_context") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key in _FORBIDDEN_KEYS:
                raise ValueError(f"{label}.{key} is not translator-safe metadata")
            _reject_unsafe_projection(item, f"{label}.{key}")
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            _reject_unsafe_projection(item, f"{label}[{index}]")
        return
    if isinstance(value, str) and _is_host_absolute(value):
        raise ValueError(f"{label} must not contain a host-absolute path")


def _is_host_absolute(value: str) -> bool:
    return (
        value.startswith("/")
        or value.startswith("\\")
        or _WINDOWS_ABSOLUTE.match(value) is not None
    )


__all__ = ["resolve_native_build_context"]
