from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any

from .build_ir import safe_posix_path
from .compile_security import safe_define


_INCLUDES = {
    "user": "-I", "system": "-isystem", "quote": "-iquote",
    "after": "-idirafter", "forced": "-include", "macros": "-imacros",
}
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_TRIPLE = re.compile(r"[a-z0-9][a-z0-9_.+]*(?:-[a-z0-9][a-z0-9_.+]*)+\Z")
_UNSAFE = re.compile(r"[\x00-\x1f\x7f;&|<>`]|\$\(")
_SINGLE = re.compile(
    r"(?:-std=(?:(?:c|gnu)(?:89|90|99|11|17|18|2x|23|2y)|iso9899:[0-9]{4})"
    r"|-O(?:0|1|2|3|s|z|g|fast)|-m(?:16|32|64|x32)"
    r"|-m(?:arch|cpu|tune|abi|fpu|float-abi|code-model|tls-dialect)=[A-Za-z0-9_.+-]+"
    r"|-m(?:no-)?(?:mmx|sse[0-9.]*|avx[0-9]*|aes|sha|fma|neon|thumb|crc|"
    r"bmi[0-9]*|popcnt|lzcnt|cx16|red-zone|stackrealign|soft-float)"
    r"|-f(?:no-)?(?:common|signed-char|unsigned-char|short-enums|short-wchar|"
    r"freestanding|hosted|builtin|strict-aliasing|wrapv|trapv|strict-overflow|"
    r"delete-null-pointer-checks|ms-extensions|blocks|plan9-extensions|pic|PIC|"
    r"pie|PIE|omit-frame-pointer)|-fvisibility=(?:default|hidden|protected|internal)"
    r"|-fpack-struct(?:=(?:1|2|4|8|16))?|-fms-compatibility-version=[0-9.]+"
    r"|-pthread|-nostdinc|-undef)\Z"
)
_OS = {
    "aix", "android", "darwin", "dragonfly", "freebsd", "fuchsia",
    "haiku", "linux", "netbsd", "none", "openbsd", "solaris", "wasi",
    "windows",
}


def rebuild_clang_compile_context(unit: Mapping[str, Any]) -> dict[str, Any]:
    source = unit.get("source")
    arguments = unit.get("compile_arguments")
    if not isinstance(source, Mapping) or not isinstance(arguments, Mapping):
        raise ValueError("clang_fact_compile_context_invalid")
    if unit.get("compiler_wrappers") or arguments.get("response_files"):
        raise ValueError("clang_fact_compile_replay_forbidden")
    if unit.get("redacted_define_count") != 0:
        raise ValueError("clang_fact_redacted_define_forbidden")
    semantic, explicit = _semantic_arguments(
        arguments.get("semantic_flags"), unit.get("language"),
    )
    includes, include_argv = _include_arguments(unit.get("includes"))
    defines, define_argv = _define_arguments(unit.get("defines"))
    return {
        "source_path": _repo_path(source.get("path"), "source"),
        "working_directory": _working_directory(unit.get("working_directory")),
        "semantic_arguments": semantic,
        "explicit_targets": explicit,
        "includes": includes,
        "defines": defines,
        "argv": [*semantic, *include_argv, *define_argv],
    }


def compatible_clang_targets(left: str, right: str) -> bool:
    return _target_key(left) == _target_key(right)


def safe_clang_text(value: Any, code: str) -> str:
    if (
        not isinstance(value, str) or not value or value != value.strip()
        or _UNSAFE.search(value) or "\\" in value
    ):
        raise ValueError(code)
    return value


def _semantic_arguments(value: Any, language: Any) -> tuple[list[str], list[str]]:
    if not isinstance(value, list) or language not in {"c", "c-cpp-output"}:
        raise ValueError("clang_fact_semantic_arguments_invalid")
    result, targets, index = [], [], 0
    while index < len(value):
        token = _argument(value[index])
        if token in {"-x", "-target", "--target", "-U"}:
            if index + 1 >= len(value):
                raise ValueError("clang_fact_semantic_operand_missing")
            operand = _argument(value[index + 1])
            if token == "-x" and operand not in {language, "c", "cpp-output"}:
                raise ValueError("clang_fact_language_drifted")
            if token in {"-target", "--target"}:
                _target_key(operand)
                targets.append(operand)
            elif token == "-U" and _NAME.fullmatch(operand) is None:
                raise ValueError("clang_fact_undef_invalid")
            result.extend((token, operand))
            index += 2
            continue
        prefix = next((item for item in ("--target=", "-target=")
                       if token.startswith(item)), None)
        if prefix:
            target = token[len(prefix):]
            _target_key(target)
            targets.append(target)
        elif token.startswith("-U") and len(token) > 2:
            if _NAME.fullmatch(token[2:]) is None:
                raise ValueError("clang_fact_undef_invalid")
        elif _SINGLE.fullmatch(token) is None:
            raise ValueError("clang_fact_semantic_argument_unsupported")
        result.append(token)
        index += 1
    if len(set(targets)) != len(targets):
        raise ValueError("clang_fact_target_duplicate")
    return result, targets


def _include_arguments(value: Any) -> tuple[list[dict[str, str]], list[str]]:
    if not isinstance(value, list):
        raise ValueError("clang_fact_includes_invalid")
    projected, argv = [], []
    for item in value:
        if (
            not isinstance(item, Mapping)
            or set(item) != {"kind", "path", "scope"}
            or item.get("kind") not in _INCLUDES
            or item.get("scope") != "repository"
        ):
            raise ValueError("clang_fact_include_invalid")
        path, kind = _repo_path(item.get("path"), "include"), str(item["kind"])
        projected.append({"kind": kind, "path": path})
        argv += [_INCLUDES[kind], f"/workspace/{path}"]
    return projected, argv


def _define_arguments(value: Any) -> tuple[list[dict[str, str]], list[str]]:
    if not isinstance(value, list):
        raise ValueError("clang_fact_defines_invalid")
    projected, argv = [], []
    for item in value:
        if not isinstance(item, Mapping) or set(item) != {"name", "value"}:
            raise ValueError("clang_fact_define_invalid")
        name, assigned = item.get("name"), item.get("value")
        if (
            not isinstance(name, str) or not isinstance(assigned, str)
            or safe_define(name, assigned) != dict(item)
        ):
            raise ValueError("clang_fact_define_invalid")
        safe_clang_text(assigned, "clang_fact_define_injection")
        projected.append({"name": name, "value": assigned})
        argv.append(f"-D{name}={assigned}")
    return projected, argv


def _argument(value: Any) -> str:
    result = safe_clang_text(value, "clang_fact_argument_injection")
    if result.startswith("@") or len(result.encode()) > 4096:
        raise ValueError("clang_fact_response_argument_forbidden")
    return result


def _repo_path(value: Any, name: str) -> str:
    if not safe_posix_path(value) or value == "." or str(value).startswith("@"):
        raise ValueError(f"clang_fact_{name}_path_invalid")
    return str(value)


def _working_directory(value: Any) -> str:
    if value != "." and not safe_posix_path(value):
        raise ValueError("clang_fact_working_directory_invalid")
    return str(value)


def _target_key(value: Any) -> tuple[str, str, str]:
    target = safe_clang_text(value, "clang_fact_target_invalid")
    if target != target.lower() or _TRIPLE.fullmatch(target) is None:
        raise ValueError("clang_fact_target_invalid")
    parts = target.split("-")
    arch = {"amd64": "x86_64", "arm64": "aarch64"}.get(parts[0], parts[0])
    if len(parts) == 2:
        return arch, parts[1], ""
    return (
        (arch, parts[1], "-".join(parts[2:])) if parts[1] in _OS
        else (arch, parts[2], "-".join(parts[3:]))
    )


__all__ = [
    "compatible_clang_targets", "rebuild_clang_compile_context",
    "safe_clang_text",
]
