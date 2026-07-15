from __future__ import annotations

from collections.abc import Mapping
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any, Callable, TypeVar

from .c2rust_project_baseline_process_contract import validated_portable_command


MAX_CONTRACT_BYTES = 32 * 1024 * 1024
MAX_ARGV_ITEMS = 256
MAX_ARG_BYTES = 4096
MAX_ARGV_BYTES = 128 * 1024
MAX_ENVIRONMENT_ITEMS = 64
MAX_ENVIRONMENT_BYTES = 128 * 1024
MAX_STDIN_BYTES = 4 * 1024 * 1024
MAX_TIMEOUT_SECONDS = 3600
_SCENARIO_FIELDS = frozenset({
    "id", "argv", "working_directory", "environment", "stdin_utf8",
    "expected_exit", "timeout_seconds",
})
_SCENARIO_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_ENVIRONMENT_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}\Z")
_RESERVED_ENVIRONMENT_KEYS = frozenset({
    "CARGO_HOME", "CARGO_NET_OFFLINE", "CARGO_TARGET_DIR",
    "CARGO_TERM_COLOR", "HOME", "LANG", "LC_ALL", "PATH", "RUSTC",
    "RUSTC_BOOTSTRAP", "RUSTUP_HOME", "TMPDIR",
})

T = TypeVar("T")
ErrorFactory = type[ValueError]


def load_scenario_contract_json(
    repo_root: Path, contract_path: Path, error_type: ErrorFactory,
) -> tuple[Any, bytes, str]:
    root = _repo_root(repo_root, error_type)
    target = _inside_existing_file(root, contract_path, error_type)
    try:
        with target.open("rb") as handle:
            data = handle.read(MAX_CONTRACT_BYTES + 1)
    except OSError as error:
        raise error_type("c2rust_scenario_contract_read_failed") from error
    if not data or len(data) > MAX_CONTRACT_BYTES:
        raise error_type("c2rust_scenario_contract_size_invalid")

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise error_type("c2rust_scenario_contract_duplicate_key")
            result[key] = value
        return result

    try:
        value = json.loads(
            data.decode("utf-8"), object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
        )
    except error_type:
        raise
    except (UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as error:
        raise error_type("c2rust_scenario_contract_json_invalid") from error
    return value, data, target.relative_to(root).as_posix()


def parse_scenario(
    repo_root: Path, value: Any, factory: Callable[..., T],
    error_type: ErrorFactory,
) -> T:
    if not isinstance(value, Mapping) or set(value) != _SCENARIO_FIELDS:
        raise error_type("c2rust_scenario_fields_invalid")
    identifier = value["id"]
    if not isinstance(identifier, str) or _SCENARIO_ID.fullmatch(identifier) is None:
        raise error_type("c2rust_scenario_id_invalid")
    working_directory = _relative_path(
        value["working_directory"], allow_dot=True, error_type=error_type,
    )
    _inside_existing_directory(repo_root, working_directory, error_type)
    expected_exit = value["expected_exit"]
    timeout = value["timeout_seconds"]
    if type(expected_exit) is not int or not -255 <= expected_exit <= 255:
        raise error_type("c2rust_scenario_expected_exit_invalid")
    if type(timeout) is not int or not 1 <= timeout <= MAX_TIMEOUT_SECONDS:
        raise error_type("c2rust_scenario_timeout_invalid")
    stdin = _bounded_text(
        value["stdin_utf8"], MAX_STDIN_BYTES, "stdin", error_type,
    ).encode("utf-8")
    return factory(
        identifier, _argv(value["argv"], error_type), working_directory,
        _environment(value["environment"], error_type), stdin,
        expected_exit, timeout,
    )


def _argv(value: Any, error_type: ErrorFactory) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > MAX_ARGV_ITEMS:
        raise error_type("c2rust_scenario_argv_invalid")
    result = []
    total = 0
    for raw in value:
        item = _bounded_text(raw, MAX_ARG_BYTES, "argv", error_type)
        total += len(item.encode("utf-8"))
        if total > MAX_ARGV_BYTES:
            raise error_type("c2rust_scenario_argv_limit_exceeded")
        result.append(item)
    try:
        validated_portable_command(["scenario", *result])
    except ValueError as error:
        raise error_type("c2rust_scenario_argv_invalid") from error
    return tuple(result)


def _environment(
    value: Any, error_type: ErrorFactory,
) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, Mapping) or len(value) > MAX_ENVIRONMENT_ITEMS:
        raise error_type("c2rust_scenario_environment_invalid")
    result = []
    total = 0
    for key in sorted(value):
        if (
            not isinstance(key, str) or _ENVIRONMENT_KEY.fullmatch(key) is None
            or key in _RESERVED_ENVIRONMENT_KEYS
        ):
            raise error_type("c2rust_scenario_environment_key_invalid")
        item = _bounded_text(value[key], 4096, "environment", error_type)
        total += len(key.encode("utf-8")) + len(item.encode("utf-8"))
        if total > MAX_ENVIRONMENT_BYTES:
            raise error_type("c2rust_scenario_environment_limit_exceeded")
        result.append((key, item))
    return tuple(result)


def _repo_root(value: Path, error_type: ErrorFactory) -> Path:
    try:
        root = Path(value).resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise error_type("c2rust_scenario_repo_root_invalid") from error
    if not root.is_dir():
        raise error_type("c2rust_scenario_repo_root_invalid")
    return root


def _inside_existing_file(
    root: Path, value: Path, error_type: ErrorFactory,
) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        try:
            if candidate.is_symlink():
                raise error_type("c2rust_scenario_contract_path_invalid")
            relative = candidate.resolve(strict=True).relative_to(root)
        except (OSError, ValueError) as error:
            raise error_type("c2rust_scenario_contract_path_invalid") from error
    else:
        relative = PurePosixPath(_relative_path(
            candidate.as_posix(), allow_dot=False, error_type=error_type,
        ))
    target = root.joinpath(*relative.parts)
    try:
        if target.is_symlink() or not target.resolve(strict=True).is_file():
            raise error_type("c2rust_scenario_contract_path_invalid")
        target.resolve(strict=True).relative_to(root)
    except (OSError, RuntimeError, ValueError) as error:
        raise error_type("c2rust_scenario_contract_path_invalid") from error
    return target.resolve(strict=True)


def _inside_existing_directory(
    root: Path, relative: str, error_type: ErrorFactory,
) -> None:
    target = root if relative == "." else root.joinpath(*PurePosixPath(relative).parts)
    try:
        resolved = target.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError) as error:
        raise error_type("c2rust_scenario_working_directory_invalid") from error
    if not resolved.is_dir():
        raise error_type("c2rust_scenario_working_directory_invalid")


def _relative_path(
    value: Any, *, allow_dot: bool, error_type: ErrorFactory,
) -> str:
    if not isinstance(value, str) or not value or "\0" in value or "\\" in value:
        raise error_type("c2rust_scenario_relative_path_invalid")
    if value == ".":
        if allow_dot:
            return value
        raise error_type("c2rust_scenario_relative_path_invalid")
    path = PurePosixPath(value)
    if (
        path.is_absolute() or ".." in path.parts or path.as_posix() != value
        or path.parts[0].startswith("~") or ":" in path.parts[0]
    ):
        raise error_type("c2rust_scenario_relative_path_invalid")
    return value


def _bounded_text(
    value: Any, limit: int, label: str, error_type: ErrorFactory,
) -> str:
    if not isinstance(value, str) or "\0" in value:
        raise error_type(f"c2rust_scenario_{label}_invalid")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeError as error:
        raise error_type(f"c2rust_scenario_{label}_invalid") from error
    if size > limit:
        raise error_type(f"c2rust_scenario_{label}_invalid")
    return value


__all__ = [
    "MAX_CONTRACT_BYTES", "load_scenario_contract_json", "parse_scenario",
]
