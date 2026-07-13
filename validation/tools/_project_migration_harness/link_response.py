from __future__ import annotations

import shlex
from pathlib import Path

from .build_facts import resolve_repository_path
from .closure_paths import bind_repository_artifact


MAX_RESPONSE_DEPTH = 4


def expand_link_response_files(
    root: Path, base: Path, argv: list[str], depth: int = 0
) -> tuple[list[str], list[dict[str, object]]]:
    if depth > MAX_RESPONSE_DEPTH:
        raise ValueError("link_response_depth_exceeded")
    expanded: list[str] = []
    bindings: list[dict[str, object]] = []
    for argument in argv:
        if not argument.startswith("@") or len(argument) == 1:
            expanded.append(argument)
            continue
        value = argument[1:]
        binding = bind_repository_artifact(root, value, base=base, kind="file")
        path = resolve_repository_path(root, value, base=base)
        nested = shlex.split(path.read_text(encoding="utf-8-sig"), posix=True)
        nested_argv, nested_bindings = expand_link_response_files(
            root, base, nested, depth + 1
        )
        bindings.extend([binding, *nested_bindings])
        expanded.extend(nested_argv)
    by_path = {str(item["path"]): item for item in bindings}
    return expanded, [by_path[path] for path in sorted(by_path)]


def take_link_output(arguments: list[str]) -> tuple[str | None, list[str]]:
    remaining: list[str] = []
    output: str | None = None
    index = 0
    while index < len(arguments):
        item = arguments[index]
        if item == "-o" and index + 1 < len(arguments):
            if output is not None:
                return None, arguments
            output = arguments[index + 1]
            index += 2
            continue
        if item.startswith("-o") and len(item) > 2:
            if output is not None:
                return None, arguments
            output = item[2:]
            index += 1
            continue
        if item.upper().startswith("/OUT:"):
            if output is not None:
                return None, arguments
            output = item[5:]
            index += 1
            continue
        remaining.append(item)
        index += 1
    return output, remaining


__all__ = ["expand_link_response_files", "take_link_output"]
