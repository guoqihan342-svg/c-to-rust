from __future__ import annotations

import shlex

from .archive_closure import is_archiver_command, is_ranlib_command
from .build_facts import compiler_name
from .compile_security import SUPPORTED_COMPILER


def parse_ninja_link_command(
    command: str,
) -> tuple[list[str] | None, list[list[str]]]:
    segments, has_unsupported_operator = _segments(_tokenize(command))
    matches = [part for part in segments if _is_primary(part)]
    if len(matches) > 1:
        raise ValueError("ninja_link_command_ambiguous")
    ranlib = [part for part in segments if is_ranlib_command(part)]
    if has_unsupported_operator and any(_contains_link_tool(part) for part in segments):
        raise ValueError("ninja_shell_operator_unsupported")
    return (matches[0] if matches else None), ranlib


def _tokenize(command: str) -> list[str]:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|<>`()")
    lexer.whitespace_split = True
    lexer.commenters = ""
    return list(lexer)


def _segments(argv: list[str]) -> tuple[list[list[str]], bool]:
    result: list[list[str]] = [[]]
    has_unsupported_operator = False
    for value in argv:
        if value == "&&":
            result.append([])
        elif _unsupported_operator(value):
            has_unsupported_operator = True
            result.append([])
        else:
            result[-1].append(value)
    return [item for item in result if item], has_unsupported_operator


def _unsupported_operator(value: str) -> bool:
    return bool(
        value != "&&"
        and (
            all(character in ";&|<>`()" for character in value)
            or "$(" in value
            or "`" in value
        )
    )


def _contains_link_tool(part: list[str]) -> bool:
    return any(
        SUPPORTED_COMPILER.fullmatch(compiler_name(value)) is not None
        or is_archiver_command([value])
        or is_ranlib_command([value])
        for value in part
    )


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
