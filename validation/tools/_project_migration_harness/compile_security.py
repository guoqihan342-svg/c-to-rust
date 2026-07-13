from __future__ import annotations

from pathlib import Path
import re

from validation.tools._ai_candidate_harness_parts.context_security import (
    redact_metadata_text,
)

from .build_facts import (
    compiler_name,
    is_absolute_any_platform,
    is_source_argument,
    summarize_path,
)


_CORE_COMPILER = r"(?:cc|c\+\+|gcc|g\+\+|clang(?:\+\+)?)(?:-\d+(?:\.\d+)*)?"
_CROSS_COMPILER = rf"(?:[a-z0-9_+.]+-){{1,4}}{_CORE_COMPILER}"
SUPPORTED_COMPILER = re.compile(
    rf"^(?:{_CORE_COMPILER}|{_CROSS_COMPILER}|clang-cl|cl)$",
    re.IGNORECASE,
)
SENSITIVE_NAME = re.compile(
    r"(?:^|_)(?:api_?)?(?:key|token|secret|password|passwd|auth|credential)(?:_|$)",
    re.IGNORECASE,
)
SENSITIVE_ASSIGNMENT = re.compile(
    r"(?:key|token|secret|password|passwd|auth|credential)\s*=",
    re.IGNORECASE,
)
DEFINE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SHELL_SYNTAX = re.compile(r"(?:&&|\|\||[;|<>`]|\$\(|\r|\n|\x00)")
WINDOWS_COMMAND = re.compile(r"(?:^|\s)(?:[A-Za-z]:\\|\\\\)")


def validate_compiler(argv: list[str], compiler_at: int) -> tuple[str, str]:
    compiler = compiler_name(argv[compiler_at]).lower()
    if not SUPPORTED_COMPILER.fullmatch(compiler):
        raise ValueError("compiler_unsupported")
    dialect = "msvc" if compiler in {"cl", "clang-cl"} else "gnu"
    return compiler, dialect


def validate_command_text(command: str) -> None:
    if SHELL_SYNTAX.search(command):
        raise ValueError("command_shell_syntax_unsupported")
    if WINDOWS_COMMAND.search(command):
        raise ValueError("windows_command_requires_arguments")


def validate_compile_contract(
    argv: list[str],
    compiler_at: int,
    repo_root: Path,
    working_directory: Path,
    source_path: Path,
    dialect: str,
) -> None:
    if not any(item == "-c" or item.lower() == "/c" for item in argv[compiler_at + 1:]):
        raise ValueError("compile_only_flag_missing")
    if not _contains_source(
        argv[compiler_at + 1:], repo_root, working_directory, source_path
    ):
        raise ValueError("source_argument_missing")
    if dialect == "msvc" and any(item.startswith("@") for item in argv):
        raise ValueError("response_file_compiler_unsupported")


def _contains_source(
    arguments: list[str],
    repo_root: Path,
    working_directory: Path,
    source_path: Path,
) -> bool:
    for index, argument in enumerate(arguments):
        if is_source_argument(argument, repo_root, working_directory, source_path):
            return True
        lowered = argument.lower()
        if lowered in {"/tc", "/tp"} and index + 1 < len(arguments):
            value = arguments[index + 1]
        elif lowered.startswith(("/tc", "/tp")) and len(argument) > 3:
            value = argument[3:]
        else:
            continue
        try:
            summary = summarize_path(value, repo_root, working_directory)
        except (OSError, ValueError):
            continue
        if summary["scope"] == "repository":
            expected = summarize_path(str(source_path), repo_root, working_directory)
            if summary["path"] == expected["path"]:
                return True
    return False


def default_output(
    compiler: str,
    source_path: Path,
    repo_root: Path,
    working_directory: Path,
) -> dict[str, str]:
    suffix = ".obj" if compiler in {"cl", "clang-cl"} else ".o"
    return summarize_path(source_path.stem + suffix, repo_root, working_directory)


def safe_define(name: str, value: str) -> dict[str, str] | None:
    if not DEFINE_NAME.fullmatch(name) or SENSITIVE_NAME.search(name):
        return None
    if (
        len(value.encode("utf-8")) > 512
        or SENSITIVE_ASSIGNMENT.search(value)
        or redact_metadata_text(value) != value
    ):
        return None
    return {"name": name, "value": value}


def safe_semantic_pair(
    flag: str,
    value: str,
    repo_root: Path,
    working_directory: Path,
) -> list[str]:
    if flag in {"--sysroot", "-isysroot"}:
        summary = summarize_path(value, repo_root, working_directory)
        return [flag, summary["path"]]
    return [flag, safe_semantic_flag(value)]


def safe_semantic_flag(argument: str) -> str:
    if SENSITIVE_ASSIGNMENT.search(argument):
        return "<redacted-sensitive-flag>"
    for prefix in ("--sysroot=", "-isysroot="):
        if argument.startswith(prefix):
            value = argument[len(prefix):]
            if is_absolute_any_platform(value):
                return prefix + "<external-path>"
    if re.search(r"(?:^|[,=])(?:[A-Za-z]:\\|/|\\\\)", argument):
        return "<redacted-semantic-path>"
    return argument


__all__ = [
    "default_output",
    "safe_define",
    "safe_semantic_flag",
    "safe_semantic_pair",
    "validate_command_text",
    "validate_compile_contract",
    "validate_compiler",
]
