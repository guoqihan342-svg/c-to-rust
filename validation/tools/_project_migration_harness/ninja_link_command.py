from __future__ import annotations

import shlex

from .archive_closure import is_archiver_command, is_ranlib_command
from .build_facts import compiler_name
from .compile_security import SUPPORTED_COMPILER


def parse_ninja_link_command(
    command: str,
) -> tuple[list[str] | None, list[list[str]]]:
    segments = _segments(shlex.split(command, posix=True))
    matches = [part for part in segments if _is_primary(part)]
    if len(matches) > 1:
        raise ValueError("ninja_link_command_ambiguous")
    ranlib = [part for part in segments if is_ranlib_command(part)]
    return (matches[0] if matches else None), ranlib


def _segments(argv: list[str]) -> list[list[str]]:
    result: list[list[str]] = [[]]
    for value in argv:
        if value == "&&":
            result.append([])
        elif value in {";", "|", "||", ">", "<"}:
            raise ValueError("ninja_shell_operator_unsupported")
        else:
            result[-1].append(value)
    return [item for item in result if item]


def _is_primary(part: list[str]) -> bool:
    return bool(
        is_archiver_command(part)
        or (
            part
            and SUPPORTED_COMPILER.fullmatch(compiler_name(part[0])) is not None
            and "-c" not in part
            and any(
                item == "-o" or item.startswith(("-o", "/OUT:"))
                for item in part[1:]
            )
        )
    )


__all__ = ["parse_ninja_link_command"]
