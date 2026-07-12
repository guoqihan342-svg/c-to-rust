from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import stat
from typing import Any

from .context_security import (
    is_absolute_any_platform,
    logical_path,
    sha256_bytes,
)


MAX_RESPONSE_DEPTH = 4
MAX_RESPONSE_FILES = 16
MAX_RESPONSE_FILE_BYTES = 64 * 1024
MAX_RESPONSE_TOTAL_BYTES = 256 * 1024
MAX_EXPANDED_ARGUMENTS = 4_096


@dataclass
class ExpansionState:
    files: dict[Path, dict[str, Any]] = field(default_factory=dict)
    active: set[Path] = field(default_factory=set)
    total_bytes: int = 0
    expansion_count: int = 0


def expand_response_files(
    argv: list[str],
    *,
    source_root: Path,
    working_directory: Path,
    compiler: str | None,
) -> tuple[list[str] | None, dict[str, Any] | None]:
    original_sha256 = argv_sha256(argv)
    if len(argv) > MAX_EXPANDED_ARGUMENTS:
        return None, blocked_report("initial_argument_count_exceeded", ExpansionState(), original_sha256)
    if not any(argument.startswith("@") for argument in argv):
        return argv, None
    dialect = response_dialect(compiler)
    if dialect is None:
        return None, blocked_report("response_file_dialect_unsupported", ExpansionState(), original_sha256)
    state = ExpansionState()
    try:
        expanded = _expand(
            argv,
            source_root=source_root,
            working_directory=working_directory,
            depth=0,
            state=state,
        )
    except ValueError as error:
        return None, blocked_report(str(error), state, original_sha256, dialect=dialect)
    return expanded, {
        "status": "expanded",
        "contract_version": 1,
        "dialect": dialect,
        "limits": limits(),
        "files": sorted(state.files.values(), key=lambda item: item["path"]),
        "expansion_count": state.expansion_count,
        "unique_file_count": len(state.files),
        "expanded_argument_count": len(expanded),
        "total_bytes": state.total_bytes,
        "original_argv_sha256": original_sha256,
        "expanded_argv_sha256": argv_sha256(expanded),
    }


def _expand(
    argv: list[str],
    *,
    source_root: Path,
    working_directory: Path,
    depth: int,
    state: ExpansionState,
) -> list[str]:
    if depth > MAX_RESPONSE_DEPTH:
        raise ValueError("response_file_depth_exceeded")
    result: list[str] = []
    for argument in argv:
        if not argument.startswith("@"):
            result.append(argument)
        else:
            reference = argument[1:]
            if not reference or is_absolute_any_platform(reference):
                raise ValueError("response_file_path_invalid")
            try:
                path = resolve_response_path(
                    source_root,
                    working_directory,
                    reference,
                )
            except (OSError, ValueError) as error:
                raise ValueError("response_file_path_outside_source_root") from error
            if path in state.active:
                raise ValueError("response_file_cycle")
            data = read_bounded_regular_file(path)
            state.expansion_count += 1
            if state.expansion_count > MAX_RESPONSE_FILES:
                raise ValueError("response_file_count_exceeded")
            state.total_bytes += len(data)
            if state.total_bytes > MAX_RESPONSE_TOTAL_BYTES:
                raise ValueError("response_file_total_bytes_exceeded")
            if path not in state.files:
                state.files[path] = {
                    "path": logical_path(source_root, path),
                    "sha256": sha256_bytes(data),
                    "size_bytes": len(data),
                    "depth": depth + 1,
                }
            try:
                text = data.decode("utf-8-sig")
            except UnicodeDecodeError as error:
                raise ValueError("response_file_encoding_invalid") from error
            if "\x00" in text:
                raise ValueError("response_file_nul_invalid")
            try:
                nested = tokenize_gnu_response(text)
            except ValueError as error:
                raise ValueError("response_file_parse_invalid") from error
            state.active.add(path)
            try:
                result.extend(
                    _expand(
                        nested,
                        source_root=source_root,
                        working_directory=working_directory,
                        depth=depth + 1,
                        state=state,
                    )
                )
            finally:
                state.active.remove(path)
        if len(result) > MAX_EXPANDED_ARGUMENTS:
            raise ValueError("response_file_argument_count_exceeded")
    return result


def response_dialect(compiler: str | None) -> str | None:
    normalized = (compiler or "").lower().removesuffix(".exe")
    if normalized in {"cc", "c++", "gcc", "g++", "clang", "clang++"} or normalized.endswith(
        ("-gcc", "-g++", "-clang", "-clang++")
    ):
        return "gnu-v1"
    return None


def tokenize_gnu_response(text: str) -> list[str]:
    tokens: list[str] = []
    current: list[str] = []
    quote: str | None = None
    token_started = False
    index = 0
    while index < len(text):
        character = text[index]
        if quote is None and character.isspace():
            if token_started:
                tokens.append("".join(current))
                current = []
                token_started = False
        elif character in {"'", '"'}:
            if quote is None:
                quote = character
                token_started = True
            elif quote == character:
                quote = None
            else:
                current.append(character)
        elif character == "\\" and index + 1 < len(text):
            token_started = True
            following = text[index + 1]
            if following.isspace() or following in {"'", '"', "\\"}:
                current.append(following)
                index += 1
            else:
                current.append(character)
        else:
            token_started = True
            current.append(character)
        index += 1
    if quote is not None:
        raise ValueError("unterminated quote")
    if token_started:
        tokens.append("".join(current))
    return tokens


def read_bounded_regular_file(path: Path) -> bytes:
    if path.is_symlink():
        raise ValueError("response_file_missing_or_linked")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise ValueError("response_file_missing_or_linked") from error
    with os.fdopen(descriptor, "rb") as handle:
        metadata = os.fstat(handle.fileno())
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("response_file_not_regular")
        if metadata.st_size > MAX_RESPONSE_FILE_BYTES:
            raise ValueError("response_file_size_exceeded")
        data = handle.read(MAX_RESPONSE_FILE_BYTES + 1)
    if len(data) > MAX_RESPONSE_FILE_BYTES:
        raise ValueError("response_file_size_exceeded")
    return data


def resolve_response_path(
    source_root: Path,
    working_directory: Path,
    reference: str,
) -> Path:
    root = source_root.resolve()
    current = working_directory.resolve()
    for part in Path(reference.replace("\\", "/")).parts:
        if part in {"", "."}:
            continue
        if part == "..":
            current = current.parent
        else:
            current = current / part
            if is_linklike(current):
                raise ValueError("response file path contains a link")
        try:
            current.relative_to(root)
        except ValueError as error:
            raise ValueError("response file path escapes source root") from error
    return current.resolve()


def is_linklike(path: Path) -> bool:
    is_junction = getattr(path, "is_junction", None)
    return path.is_symlink() or (callable(is_junction) and is_junction())


def argv_sha256(argv: list[str]) -> str:
    return sha256_bytes(
        json.dumps(argv, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )


def limits() -> dict[str, int]:
    return {
        "max_depth": MAX_RESPONSE_DEPTH,
        "max_files": MAX_RESPONSE_FILES,
        "max_file_bytes": MAX_RESPONSE_FILE_BYTES,
        "max_total_bytes": MAX_RESPONSE_TOTAL_BYTES,
        "max_arguments": MAX_EXPANDED_ARGUMENTS,
    }


def blocked_report(
    reason: str,
    state: ExpansionState,
    original_sha256: str,
    *,
    dialect: str | None = None,
) -> dict[str, Any]:
    return {
        "status": "blocked",
        "contract_version": 1,
        "dialect": dialect or "unsupported",
        "reason": reason,
        "limits": limits(),
        "files": sorted(state.files.values(), key=lambda item: item["path"]),
        "expansion_count": state.expansion_count,
        "unique_file_count": len(state.files),
        "total_bytes": state.total_bytes,
        "original_argv_sha256": original_sha256,
    }


def command_parse_failure_report(command: str) -> dict[str, Any]:
    return blocked_report(
        "command_argument_parse_invalid",
        ExpansionState(),
        sha256_bytes(command.encode("utf-8")),
    )


__all__ = ["command_parse_failure_report", "expand_response_files"]
