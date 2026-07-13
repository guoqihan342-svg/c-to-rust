from __future__ import annotations

from pathlib import Path
from typing import Any

from .build_facts import is_source_argument, summarize_path
from .compile_security import (
    safe_define,
    safe_semantic_flag,
    safe_semantic_pair,
)


INCLUDE_FLAGS = {
    "-I": "user",
    "/I": "user",
    "-isystem": "system",
    "-iquote": "quote",
    "-idirafter": "after",
    "-include": "forced",
    "-imacros": "macros",
}
SEMANTIC_PAIR_FLAGS = {"-x", "-target", "--target", "--sysroot", "-isysroot", "-U"}
SEMANTIC_PREFIXES = (
    "-std=", "/std:", "-O", "/O", "-m", "-f", "-pthread", "-nostdinc",
    "-undef", "--target=", "--sysroot=", "-U", "-Xclang", "-Wp,",
)
DEPENDENCY_PAIR_FLAGS = {"-MF", "-MT", "-MQ", "-MJ"}


def extract_arguments(
    argv: list[str],
    compiler_at: int,
    repo_root: Path,
    working_directory: Path,
    source_path: Path,
) -> dict[str, Any]:
    includes: list[dict[str, Any]] = []
    defines: list[dict[str, str]] = []
    semantic_flags: list[str] = []
    output: dict[str, str] | None = None
    redacted_define_count = 0
    index = compiler_at + 1
    while index < len(argv):
        argument = argv[index]
        following = argv[index + 1] if index + 1 < len(argv) else None
        include = _matched_value(argument, following, INCLUDE_FLAGS)
        if include is not None:
            kind, value, consumed = include
            includes.append({"kind": kind, **summarize_path(value, repo_root, working_directory)})
            index += consumed + 1
            continue
        define = _matched_define(argument, following)
        if define is not None:
            value, consumed = define
            name, separator, assigned = value.partition("=")
            safe = safe_define(name, assigned if separator else "1")
            if safe is None:
                redacted_define_count += 1
            else:
                defines.append(safe)
            index += consumed + 1
            continue
        command_output = _matched_output(argument, following)
        if command_output is not None:
            value, consumed = command_output
            output = summarize_path(value, repo_root, working_directory)
            index += consumed + 1
            continue
        if argument in DEPENDENCY_PAIR_FLAGS:
            index += 2 if following is not None else 1
            continue
        if argument in SEMANTIC_PAIR_FLAGS and following is not None:
            semantic_flags.extend(
                safe_semantic_pair(argument, following, repo_root, working_directory)
            )
            index += 2
            continue
        if is_source_argument(argument, repo_root, working_directory, source_path):
            index += 1
            continue
        if argument not in {"-c", "/c"} and argument.startswith(SEMANTIC_PREFIXES):
            semantic_flags.append(safe_semantic_flag(argument))
        index += 1
    return {
        "includes": includes,
        "defines": defines,
        "redacted_define_count": redacted_define_count,
        "semantic_flags": semantic_flags,
        "output": output,
    }


def _matched_value(
    argument: str,
    following: str | None,
    flags: dict[str, str],
) -> tuple[str, str, int] | None:
    for flag, kind in flags.items():
        if argument == flag and following is not None:
            return kind, following, 1
        if argument.startswith(flag) and len(argument) > len(flag):
            return kind, argument[len(flag):], 0
    return None


def _matched_define(argument: str, following: str | None) -> tuple[str, int] | None:
    if argument in {"-D", "/D"} and following is not None:
        return following, 1
    if argument.startswith(("-D", "/D")) and len(argument) > 2:
        return argument[2:], 0
    return None


def _matched_output(argument: str, following: str | None) -> tuple[str, int] | None:
    if argument in {"-o", "/Fo"} and following is not None:
        return following, 1
    if argument.startswith("-o") and len(argument) > 2:
        return argument[2:], 0
    if argument.startswith("/Fo") and len(argument) > 3:
        return argument[3:], 0
    return None


__all__ = ["extract_arguments"]
