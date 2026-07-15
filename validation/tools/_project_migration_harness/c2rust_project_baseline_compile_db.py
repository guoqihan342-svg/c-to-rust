from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shlex
from typing import Any


MAX_COMPILE_DATABASE_BYTES = 32 * 1024 * 1024
MAX_COMPILE_DATABASE_ENTRIES = 100_000
MAX_BOUND_SOURCE_BYTES = 512 * 1024 * 1024
_PATH_NEXT = {
    "-I", "-L", "-T", "-include", "-imacros", "-iquote", "-isystem",
    "-o", "-MF", "--sysroot", "--include-directory",
}
_PATH_PREFIX = (
    "--include-directory=", "--sysroot=", "-isystem", "-iquote",
    "-imacros", "-include", "-MF", "-I", "-L", "-T", "-o",
)
_PATH_SUFFIXES = {
    ".a", ".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".i",
    ".ii", ".o", ".obj", ".s", ".so", ".S",
}


@dataclass(frozen=True, slots=True)
class NormalizedCompilationDatabase:
    entries: tuple[dict[str, Any], ...]
    sources: tuple[dict[str, Any], ...]

    def payload(self) -> list[dict[str, Any]]:
        return [dict(entry) for entry in self.entries]


def normalize_compilation_database(
    repo_root: Path, compile_commands: Path,
) -> NormalizedCompilationDatabase:
    root = _repository_root(repo_root)
    database = _existing_inside(root, compile_commands, "compile_database")
    if not database.is_file() or database.stat().st_size > MAX_COMPILE_DATABASE_BYTES:
        raise ValueError("c2rust_compile_database_invalid")
    raw = _strict_json(database.read_bytes())
    if (
        not isinstance(raw, list) or not raw
        or len(raw) > MAX_COMPILE_DATABASE_ENTRIES
    ):
        raise ValueError("c2rust_compile_database_entries_invalid")
    entries: list[dict[str, Any]] = []
    sources: dict[str, dict[str, Any]] = {}
    for value in raw:
        entry, binding = _normalize_entry(root, value)
        entries.append(entry)
        sources.setdefault(binding["path"], binding)
    return NormalizedCompilationDatabase(
        tuple(entries), tuple(sources[key] for key in sorted(sources)),
    )


def _normalize_entry(
    root: Path, value: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(value, dict):
        raise ValueError("c2rust_compile_database_entry_invalid")
    directory_value = value.get("directory")
    file_value = value.get("file")
    if not isinstance(directory_value, str) or not isinstance(file_value, str):
        raise ValueError("c2rust_compile_database_path_invalid")
    directory = _safe_path(directory_value, root, root, must_exist=True)
    if not directory.is_dir():
        raise ValueError("c2rust_compile_database_directory_invalid")
    source = _safe_path(file_value, directory, root, must_exist=True)
    if not source.is_file():
        raise ValueError("c2rust_compile_database_source_invalid")
    argv = _entry_argv(value)
    normalized_argv = _normalize_argv(argv, directory, root, source)
    result: dict[str, Any] = {
        "directory": directory.as_posix(),
        "file": source.as_posix(),
        "arguments": normalized_argv,
    }
    output = value.get("output")
    if output is not None:
        if not isinstance(output, str) or not output:
            raise ValueError("c2rust_compile_database_output_invalid")
        result["output"] = _safe_path(
            output, directory, root, must_exist=False,
        ).as_posix()
    return result, _source_binding(root, source)


def _entry_argv(value: dict[str, Any]) -> list[str]:
    arguments = value.get("arguments")
    command = value.get("command")
    if arguments is not None and command is not None:
        raise ValueError("c2rust_compile_database_command_ambiguous")
    if arguments is not None:
        if (
            not isinstance(arguments, list) or not arguments
            or any(not isinstance(item, str) or not item or "\0" in item for item in arguments)
        ):
            raise ValueError("c2rust_compile_database_argv_invalid")
        return list(arguments)
    if not isinstance(command, str) or not command or "\0" in command:
        raise ValueError("c2rust_compile_database_command_invalid")
    try:
        parsed = shlex.split(command, posix=os.name != "nt")
    except ValueError as error:
        raise ValueError("c2rust_compile_database_command_invalid") from error
    if not parsed:
        raise ValueError("c2rust_compile_database_command_invalid")
    return parsed


def _normalize_argv(
    argv: list[str], directory: Path, root: Path, source: Path,
) -> list[str]:
    result = [argv[0]]
    source_seen = False
    index = 1
    while index < len(argv):
        token = argv[index]
        if token in _PATH_NEXT:
            if index + 1 >= len(argv):
                raise ValueError("c2rust_compile_database_argv_path_missing")
            path = _safe_path(argv[index + 1], directory, root, must_exist=False)
            result.extend((token, path.as_posix()))
            source_seen = source_seen or path == source
            index += 2
            continue
        attached = _attached_path(token)
        if attached is not None:
            prefix, raw_path = attached
            path = _safe_path(raw_path, directory, root, must_exist=False)
            result.append(prefix + path.as_posix())
            source_seen = source_seen or path == source
        elif token.startswith("@") and len(token) > 1:
            path = _safe_path(token[1:], directory, root, must_exist=True)
            result.append("@" + path.as_posix())
        elif _looks_like_path(token):
            path = _safe_path(token, directory, root, must_exist=False)
            result.append(path.as_posix())
            source_seen = source_seen or path == source
        else:
            result.append(token)
        index += 1
    if not source_seen:
        result.append(source.as_posix())
    return result


def _attached_path(token: str) -> tuple[str, str] | None:
    for prefix in _PATH_PREFIX:
        if token.startswith(prefix) and len(token) > len(prefix):
            return prefix, token[len(prefix):]
    return None


def _looks_like_path(value: str) -> bool:
    return (
        Path(value).is_absolute() or "/" in value or "\\" in value
        or value.startswith(".") or Path(value).suffix in _PATH_SUFFIXES
    )


def _safe_path(
    value: str, base: Path, root: Path, *, must_exist: bool,
) -> Path:
    if not value or "\0" in value:
        raise ValueError("c2rust_project_path_invalid")
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = base / candidate
    try:
        resolved = candidate.resolve(strict=must_exist)
        resolved.relative_to(root)
    except (OSError, ValueError) as error:
        raise ValueError("c2rust_project_path_escapes_repository") from error
    return resolved


def _existing_inside(root: Path, value: Path, label: str) -> Path:
    try:
        path = Path(value).resolve(strict=True)
        path.relative_to(root)
    except (OSError, ValueError) as error:
        raise ValueError(f"c2rust_{label}_escapes_repository") from error
    return path


def _repository_root(value: Path) -> Path:
    root = Path(value).resolve(strict=True)
    if not root.is_dir() or root == root.parent:
        raise ValueError("c2rust_repository_invalid")
    return root


def _source_binding(root: Path, source: Path) -> dict[str, Any]:
    size = source.stat().st_size
    if size > MAX_BOUND_SOURCE_BYTES:
        raise ValueError("c2rust_source_too_large")
    digest = hashlib.sha256()
    with source.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "path": source.relative_to(root).as_posix(),
        "sha256": digest.hexdigest(),
        "size_bytes": size,
    }


def _strict_json(data: bytes) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("c2rust_compile_database_duplicate_key")
            result[key] = value
        return result
    try:
        return json.loads(data.decode("utf-8-sig"), object_pairs_hook=pairs)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("c2rust_compile_database_json_invalid") from error


__all__ = [
    "NormalizedCompilationDatabase", "normalize_compilation_database",
]
