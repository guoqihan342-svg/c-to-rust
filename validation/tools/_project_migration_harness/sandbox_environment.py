from __future__ import annotations

from collections.abc import Mapping
from typing import Any


ENVIRONMENT_ALLOWLIST = (
    "CARGO_ENCODED_RUSTFLAGS",
    "CARGO_HOME",
    "CARGO_NET_OFFLINE",
    "CARGO_TARGET_DIR",
    "CARGO_TERM_COLOR",
    "HOME",
    "LANG",
    "LC_ALL",
    "PATH",
    "RUSTC",
    "RUSTDOC",
    "TMPDIR",
)

_TOOL_DIRECTORY = "/toolchain/bin"
_TRACE_FLAGS = (
    "--force-warn=linker-messages",
    "-C",
    "linker=/usr/bin/cc",
    "-C",
    "link-arg=-Wl,-t,-t",
)


def cargo_guest_environment(*, native_link_trace: bool = False) -> dict[str, str]:
    if type(native_link_trace) is not bool:
        raise ValueError("native_link_trace must be a boolean")
    values = {
        "CARGO_ENCODED_RUSTFLAGS": (
            "\x1f".join(_TRACE_FLAGS) if native_link_trace else ""
        ),
        "CARGO_HOME": "/runtime/cargo-home",
        "CARGO_NET_OFFLINE": "true",
        "CARGO_TARGET_DIR": "/runtime/target",
        "CARGO_TERM_COLOR": "never",
        "HOME": "/home/sandbox",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": f"{_TOOL_DIRECTORY}:/usr/bin:/bin",
        "RUSTC": f"{_TOOL_DIRECTORY}/rustc",
        "RUSTDOC": f"{_TOOL_DIRECTORY}/rustdoc",
        "TMPDIR": "/tmp",
    }
    if tuple(sorted(values)) != ENVIRONMENT_ALLOWLIST:
        raise RuntimeError("sandbox environment policy is inconsistent")
    return values


def canonical_environment_items(
    value: Mapping[str, Any],
) -> tuple[tuple[str, str], ...]:
    if set(value) != set(ENVIRONMENT_ALLOWLIST):
        raise ValueError("sandbox environment keys must match the fixed set")
    items = tuple(sorted(value.items()))
    if any(type(key) is not str or type(item) is not str for key, item in items):
        raise ValueError("sandbox environment values must be strings")
    return items


def bubblewrap_environment_args(
    environment: tuple[tuple[str, str], ...],
) -> list[str]:
    canonical = canonical_environment_items(dict(environment))
    if canonical != environment:
        raise ValueError("sandbox environment must be canonical")
    return [
        item
        for key, value in canonical
        for item in ("--setenv", key, value)
    ]


__all__ = [
    "ENVIRONMENT_ALLOWLIST",
    "bubblewrap_environment_args",
    "canonical_environment_items",
    "cargo_guest_environment",
]
