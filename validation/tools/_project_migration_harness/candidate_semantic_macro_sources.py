from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from typing import Any

from .c_index_macros import logical_directives


_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*", re.ASCII)


def scan_macro_source(
    path: str, data: bytes, origin: str, *, max_records: int,
) -> tuple[list[dict[str, Any]], bool, bool]:
    if type(max_records) is not int or max_records < 1:
        raise ValueError("macro source record budget is invalid")
    result: list[dict[str, Any]] = []
    depth = 0
    invalid = False
    for directive in logical_directives(data):
        kind = directive["kind"]
        if kind == "endif":
            invalid = invalid or depth == 0
            depth = max(0, depth - 1)
        elif kind in {"elif", "else"}:
            invalid = invalid or depth == 0
        if kind == "define":
            parsed = _parse_define(str(directive["body"]))
            if parsed is None:
                invalid = True
            else:
                name, parameters, replacement = parsed
                reason = (
                    "conditional_definition" if depth
                    else "function_like" if parameters is not None
                    else None
                )
                result.append({
                    "name": name, "parameters": parameters,
                    "replacement": replacement,
                    "byte_offset": directive["byte_offset"],
                    "directive_sha256": directive["sha256"],
                    "conditional_depth": depth,
                    "activation_status": (
                        "unconditional" if depth == 0 else "conditional_unknown"
                    ),
                    "origin": origin, "source_path": path,
                    "blocked_reason": reason,
                })
        elif kind == "undef":
            matched = _IDENTIFIER.fullmatch(str(directive["body"]).strip())
            if matched is not None:
                result.append({
                    "name": matched.group(), "replacement": "",
                    "byte_offset": directive["byte_offset"],
                    "origin": origin, "source_path": path,
                    "blocked_reason": "undefined_or_redefined",
                })
            else:
                invalid = True
        if len(result) >= max_records:
            return result, invalid, True
        if kind in {"if", "ifdef", "ifndef"}:
            depth += 1
    return result, invalid or depth != 0, False


def compile_definitions(
    arguments: Sequence[str], *, max_definitions: int,
) -> tuple[tuple[str, str | None], ...]:
    if type(max_definitions) is not int or max_definitions < 1:
        raise ValueError("macro compile definition budget is invalid")
    result: list[tuple[str, str | None]] = []
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if not isinstance(argument, str):
            raise ValueError("macro compile argument is invalid")
        if argument in {"-D", "-U"}:
            index += 1
            if index >= len(arguments) or not isinstance(arguments[index], str):
                raise ValueError("macro compile definition is invalid")
            operand = arguments[index]
            option = argument
        elif argument.startswith("-D") or argument.startswith("-U"):
            option, operand = argument[:2], argument[2:]
        else:
            index += 1
            continue
        name, separator, value = operand.partition("=")
        if (
            _IDENTIFIER.fullmatch(name) is None
            or option == "-U" and separator
        ):
            raise ValueError("macro compile definition is invalid")
        result.append((name, None if option == "-U" else value if separator else "1"))
        if len(result) >= max_definitions:
            break
        index += 1
    return tuple(result)


def validate_cindex_macro_facts(
    facts: Sequence[Mapping[str, Any]], records: Sequence[Mapping[str, Any]],
    source_path: str, source_bytes: bytes, node_id: str, unit_id: str,
) -> None:
    by_offset = {
        item["byte_offset"]: item
        for item in records if "directive_sha256" in item
    }
    source_sha = hashlib.sha256(source_bytes).hexdigest()
    for fact in facts:
        offset = fact.get("byte_offset")
        actual = by_offset.get(offset)
        expected_parameters = None if actual is None else actual.get("parameters")
        if (
            actual is None or fact.get("node_id") != node_id
            or fact.get("unit_id") != unit_id
            or fact.get("source_path") != source_path
            or fact.get("source_sha256") != source_sha
            or fact.get("name") != actual.get("name")
            or fact.get("parameters") != expected_parameters
            or fact.get("replacement") != actual.get("replacement")
            or fact.get("directive_sha256") != actual.get("directive_sha256")
            or fact.get("conditional_depth") != actual.get("conditional_depth")
            or fact.get("activation_status") != actual.get("activation_status")
        ):
            raise ValueError("CIndex macro fact is not source bound")


def _parse_define(value: str) -> tuple[str, list[str] | None, str] | None:
    stripped = value.lstrip()
    matched = _IDENTIFIER.match(stripped)
    if matched is None:
        return None
    name, rest = matched.group(), stripped[matched.end():]
    if not rest.startswith("("):
        return name, None, rest.strip()
    close = rest.find(")", 1)
    if close < 0:
        return None
    raw = rest[1:close]
    parameters = [item.strip() for item in raw.split(",") if item.strip()]
    if any(_IDENTIFIER.fullmatch(item) is None for item in parameters):
        parameters = []
    return name, parameters, rest[close + 1:].strip()


__all__ = [
    "compile_definitions", "scan_macro_source", "validate_cindex_macro_facts",
]
