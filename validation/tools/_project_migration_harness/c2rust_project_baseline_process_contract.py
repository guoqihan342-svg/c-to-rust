from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
import re


RUNTIME_OVERRIDE_KEYS = frozenset({
    "CARGO_HOME", "RUSTUP_HOME", "RUSTC_BOOTSTRAP",
})
REQUIRED_ENVIRONMENT_KEYS = frozenset({
    "CARGO_HOME", "CARGO_NET_OFFLINE", "CARGO_TARGET_DIR",
    "CARGO_TERM_COLOR", "HOME", "LANG", "LC_ALL", "PATH", "RUSTC",
    "TMPDIR",
})


def validated_command(value: Sequence[str]) -> list[str]:
    if (
        isinstance(value, (str, bytes)) or not value
        or any(
            not isinstance(item, str) or not item or "\0" in item
            for item in value
        )
    ):
        raise ValueError("c2rust_process_argv_invalid")
    return list(value)


def validated_portable_command(value: Sequence[str]) -> list[str]:
    command = validated_command(value)
    for token in command:
        if (
            Path(token).is_absolute()
            or re.match(r"^[A-Za-z]:[/\\]", token)
            or token.startswith(("/", "\\\\"))
        ):
            raise ValueError("c2rust_process_portable_argv_invalid")
    return command


def validated_portable_path(value: str) -> str:
    if (
        not isinstance(value, str) or not value or "\\" in value
        or Path(value).is_absolute() or ".." in Path(value).parts
    ):
        raise ValueError("c2rust_process_portable_working_directory_invalid")
    return Path(value).as_posix()


def validated_environment(
    value: Mapping[str, str], allowed_environment_keys: Sequence[str],
) -> dict[str, str]:
    allowed = _validated_environment_keys(allowed_environment_keys)
    if (
        not isinstance(value, Mapping)
        or not REQUIRED_ENVIRONMENT_KEYS <= set(value)
        or set(value) - REQUIRED_ENVIRONMENT_KEYS - RUNTIME_OVERRIDE_KEYS - allowed
        or any(
            type(key) is not str or type(item) is not str
            for key, item in value.items()
        )
        or value.get("CARGO_NET_OFFLINE") != "true"
        or value.get("CARGO_TERM_COLOR") != "never"
    ):
        raise ValueError("c2rust_process_environment_invalid")
    return dict(value)


def validated_stdin(value: bytes, *, limit: int) -> bytes:
    if type(value) is not bytes or len(value) > limit:
        raise ValueError("c2rust_process_stdin_invalid")
    return value


def validated_expected_returncodes(value: Sequence[int]) -> list[int]:
    if (
        isinstance(value, (str, bytes)) or not value
        or any(type(item) is not int or not -255 <= item <= 255 for item in value)
    ):
        raise ValueError("c2rust_process_expected_returncodes_invalid")
    result = sorted(set(value))
    if len(result) != len(value):
        raise ValueError("c2rust_process_expected_returncodes_invalid")
    return result


def _validated_environment_keys(value: Sequence[str]) -> set[str]:
    if (
        isinstance(value, (str, bytes))
        or any(
            not isinstance(item, str)
            or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", item) is None
            for item in value
        )
    ):
        raise ValueError("c2rust_process_environment_key_invalid")
    result = set(value)
    if (
        len(result) != len(value)
        or result & (RUNTIME_OVERRIDE_KEYS | REQUIRED_ENVIRONMENT_KEYS)
    ):
        raise ValueError("c2rust_process_environment_key_invalid")
    return result


__all__ = [
    "REQUIRED_ENVIRONMENT_KEYS", "RUNTIME_OVERRIDE_KEYS", "validated_command",
    "validated_environment", "validated_expected_returncodes",
    "validated_portable_command", "validated_portable_path", "validated_stdin",
]
