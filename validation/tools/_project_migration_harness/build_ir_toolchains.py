from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path, PureWindowsPath
import re
from typing import Any

from .host_tool_binding import classify_tool_basename


MAX_TRANSLATION_UNITS = 4_096
MAX_WRAPPERS_PER_UNIT = 16
MAX_LINK_TARGETS = 4_096
MAX_MAKE_COMMANDS = 4_096
MAX_TOOL_REQUESTS = 128
MAX_TOOL_USES = 80_000
MAX_TOKEN_BYTES = 4_096

TOOL_ROLES = frozenset({
    "archiver",
    "compiler-driver",
    "compiler-wrapper",
    "linker",
    "linker-driver",
    "ranlib",
})

_MAKE_ROLES = {
    "archive": "archiver",
    "compile": "compiler-driver",
    "ranlib": "ranlib",
}
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.+@-]*")


def standard_tool_requests(
    discovery: Mapping[str, Any], closure: Mapping[str, Any],
) -> list[dict[str, str]]:
    """Extract tool roles from already parsed compile and link raw facts."""
    discovery = _mapping(discovery, "build_ir_tool_discovery_invalid")
    closure = _mapping(closure, "build_ir_tool_closure_invalid")
    units = _bounded_list(
        discovery.get("translation_units"),
        "build_ir_tool_translation_units_invalid",
        MAX_TRANSLATION_UNITS,
        allow_empty=False,
    )
    link_closure = _mapping(
        closure.get("target_link_closure"),
        "build_ir_tool_link_closure_invalid",
    )
    targets = _bounded_list(
        link_closure.get("targets"),
        "build_ir_tool_link_targets_invalid",
        MAX_LINK_TARGETS,
        allow_empty=True,
    )

    result: list[dict[str, str]] = []
    for unit in units:
        unit = _mapping(unit, "build_ir_tool_translation_unit_invalid")
        _append_request(result, unit.get("compiler"), "compiler-driver")
        wrappers = _bounded_list(
            unit.get("compiler_wrappers"),
            "build_ir_tool_compiler_wrappers_invalid",
            MAX_WRAPPERS_PER_UNIT,
            allow_empty=True,
        )
        for wrapper in wrappers:
            _append_request(result, wrapper, "compiler-wrapper")

    for target in targets:
        target = _mapping(target, "build_ir_tool_link_target_invalid")
        role = "linker-driver"
        if "archive_operation" in target:
            _bounded_text(
                target.get("archive_operation"),
                "build_ir_tool_archive_operation_invalid",
                64,
            )
            role = "archiver"
        _append_request(result, target.get("driver"), role)
        ranlib_drivers = _bounded_list(
            target.get("ranlib_drivers", []),
            "build_ir_tool_ranlib_drivers_invalid",
            MAX_WRAPPERS_PER_UNIT,
            allow_empty=True,
        )
        for driver in ranlib_drivers:
            _append_request(result, driver, "ranlib")
    return result


def make_tool_requests(report: Mapping[str, Any]) -> list[dict[str, str]]:
    """Extract tool roles from validated Make direct-command facts."""
    report = _mapping(report, "build_ir_make_report_invalid")
    commands = _bounded_list(
        report.get("commands"),
        "build_ir_make_commands_invalid",
        MAX_MAKE_COMMANDS,
        allow_empty=False,
    )
    result: list[dict[str, str]] = []
    for command in commands:
        command = _mapping(command, "build_ir_make_command_invalid")
        _append_request(
            result, command.get("tool"), make_command_tool_role(command),
        )
    return result


def make_command_tool_role(command: Mapping[str, Any]) -> str:
    kind = command.get("kind")
    if kind in _MAKE_ROLES:
        return _MAKE_ROLES[kind]
    if kind != "link":
        raise ValueError("build_ir_make_command_kind_invalid")
    token = _tool_token(command.get("tool"))
    family, _ = classify_tool_basename(token)
    if family in {
        "gnu-compiler", "clang-compiler", "clang-cl-compiler",
        "intel-compiler", "msvc-compiler",
    }:
        return "linker-driver"
    if family in {"linker", "msvc-linker"}:
        return "linker"
    raise ValueError("build_ir_make_link_tool_invalid")


def merge_tool_requests(requests: Any) -> list[dict[str, Any]]:
    """Validate and merge flat token/role requests into a canonical sequence."""
    values = _bounded_list(
        requests,
        "build_ir_tool_requests_invalid",
        MAX_TOOL_USES,
        allow_empty=True,
    )
    by_token: dict[str, set[str]] = {}
    for request in values:
        request = _mapping(request, "build_ir_tool_request_invalid")
        if set(request) != {"token", "role"}:
            raise ValueError("build_ir_tool_request_schema_invalid")
        token = _tool_token(request.get("token"))
        role = request.get("role")
        if not isinstance(role, str) or role not in TOOL_ROLES:
            raise ValueError("build_ir_tool_role_invalid")
        by_token.setdefault(token, set()).add(role)
        if len(by_token) > MAX_TOOL_REQUESTS:
            raise ValueError("build_ir_tool_request_limit_exceeded")
    return [
        {"token": token, "roles": sorted(by_token[token])}
        for token in sorted(by_token)
    ]


def _append_request(result: list[dict[str, str]], token: Any, role: str) -> None:
    if len(result) >= MAX_TOOL_USES:
        raise ValueError("build_ir_tool_request_limit_exceeded")
    result.append({"token": _tool_token(token), "role": role})


def _tool_token(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value.encode("utf-8")) > MAX_TOKEN_BYTES
        or any(character in value for character in "\r\n\x00")
    ):
        raise ValueError("build_ir_tool_token_invalid")
    basename = value.replace("\\", "/").rsplit("/", 1)[-1]
    has_separator = "/" in value or "\\" in value
    absolute = Path(value).is_absolute() or PureWindowsPath(value).is_absolute()
    if (
        not basename or _TOKEN.fullmatch(basename) is None
        or (has_separator and not absolute)
        or (not has_separator and _TOKEN.fullmatch(value) is None)
    ):
        raise ValueError("build_ir_tool_token_invalid")
    return value


def tool_basename(value: str) -> str:
    basename = value.replace("\\", "/").rsplit("/", 1)[-1].lower()
    return basename[:-4] if basename.endswith(".exe") else basename


def _bounded_text(value: Any, code: str, maximum_bytes: int) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value.encode("utf-8")) > maximum_bytes
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError(code)
    return value


def _mapping(value: Any, code: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(code)
    return value


def _bounded_list(
    value: Any, code: str, maximum: int, *, allow_empty: bool,
) -> list[Any]:
    if (
        not isinstance(value, list)
        or (not allow_empty and not value)
        or len(value) > maximum
    ):
        raise ValueError(code)
    return value


__all__ = [
    "MAX_LINK_TARGETS",
    "MAX_MAKE_COMMANDS",
    "MAX_TOKEN_BYTES",
    "MAX_TOOL_REQUESTS",
    "MAX_TOOL_USES",
    "MAX_TRANSLATION_UNITS",
    "MAX_WRAPPERS_PER_UNIT",
    "TOOL_ROLES",
    "make_tool_requests",
    "make_command_tool_role",
    "merge_tool_requests",
    "standard_tool_requests",
    "tool_basename",
]
