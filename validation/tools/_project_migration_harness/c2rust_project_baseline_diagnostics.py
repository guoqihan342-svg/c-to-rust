from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping, Sequence


_ANSI_ESCAPE = re.compile(rb"\x1b\[[0-?]*[ -/]*[@-~]")
_ERROR_DIAGNOSTIC = re.compile(rb"^[ \t]*error(?:\[[^\r\n]*\])?[ \t]*:", re.MULTILINE)
_NONSEMANTIC_NEXT = {"-MF", "-MJ", "-MQ", "-MT", "-o", "--output"}
_NONSEMANTIC_PREFIX = ("-MF", "-MJ", "-MQ", "-MT", "--output=")


def has_multi_configuration_source(entries: Sequence[Mapping[str, Any]]) -> bool:
    variants: dict[str, set[tuple[str, tuple[str, ...]]]] = {}
    for entry in entries:
        source = entry.get("file")
        directory = entry.get("directory")
        arguments = entry.get("arguments")
        if (
            not isinstance(source, str) or not isinstance(directory, str)
            or not isinstance(arguments, list)
            or any(not isinstance(item, str) for item in arguments)
        ):
            raise ValueError("c2rust_compile_database_normalized_entry_invalid")
        signature = (directory, tuple(_semantic_arguments(arguments)))
        variants.setdefault(source, set()).add(signature)
    return any(len(configurations) > 1 for configurations in variants.values())


def has_transpiler_error_diagnostics(
    out_root: Path, stderr_ref: Mapping[str, Any],
) -> bool:
    root = Path(out_root).resolve(strict=True)
    relative = stderr_ref.get("path")
    expected_sha = stderr_ref.get("sha256")
    expected_size = stderr_ref.get("size_bytes")
    if (
        not isinstance(relative, str) or not relative or "\\" in relative
        or PurePosixPath(relative).is_absolute()
        or ".." in PurePosixPath(relative).parts
        or not isinstance(expected_sha, str)
        or type(expected_size) is not int or expected_size < 0
    ):
        raise ValueError("c2rust_transpile_stderr_binding_invalid")
    try:
        path = root.joinpath(*PurePosixPath(relative).parts).resolve(strict=True)
        path.relative_to(root)
        data = path.read_bytes()
    except (OSError, ValueError) as error:
        raise ValueError("c2rust_transpile_stderr_binding_invalid") from error
    if len(data) != expected_size or hashlib.sha256(data).hexdigest() != expected_sha:
        raise ValueError("c2rust_transpile_stderr_binding_invalid")
    return _ERROR_DIAGNOSTIC.search(_ANSI_ESCAPE.sub(b"", data)) is not None


def _semantic_arguments(arguments: list[str]) -> list[str]:
    result: list[str] = []
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument in _NONSEMANTIC_NEXT:
            index += 2
            continue
        if any(
            argument.startswith(prefix) and len(argument) > len(prefix)
            for prefix in _NONSEMANTIC_PREFIX
        ):
            index += 1
            continue
        result.append(argument)
        index += 1
    return result


__all__ = [
    "has_multi_configuration_source", "has_transpiler_error_diagnostics",
]
