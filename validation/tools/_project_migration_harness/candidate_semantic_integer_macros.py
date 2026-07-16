from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .artifacts import checked_relative_path, content_sha256
from .candidate_semantic_integer_literals import macro_expression_text
from .candidate_semantic_integer_macro_expr import resolve_integer_macro_roots
from .candidate_semantic_macro_sources import (
    compile_definitions,
    scan_macro_source,
    validate_cindex_macro_facts,
)


MAX_MACRO_SOURCE_FILES = 64
MAX_MACRO_TOTAL_SOURCE_BYTES = 2 * 1024 * 1024
MAX_MACRO_DEFINITIONS = 512
MAX_MACRO_ROOTS = 128
MAX_MACRO_MAGNITUDES = 32
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*", re.ASCII)


@dataclass(frozen=True)
class IntegerMacroBoundaries:
    magnitudes: tuple[int, ...]
    binding: dict[str, object]


def collect_integer_macro_boundaries(
    *,
    function_source: bytes,
    source_path: str,
    source_bytes: bytes,
    function_byte_start: int,
    node_id: str,
    unit_id: str,
    header_sources: Sequence[tuple[str, bytes]] = (),
    cindex_macro_facts: Sequence[Mapping[str, Any]] = (),
    compile_arguments: Sequence[str] = (),
) -> IntegerMacroBoundaries:
    units = [(source_path, source_bytes, "translation_unit"), *(
        (path, data, "header") for path, data in header_sources
    )]
    _validate_inputs(
        units, function_source, function_byte_start, node_id, unit_id,
    )
    compile_macros = compile_definitions(
        compile_arguments, max_definitions=MAX_MACRO_DEFINITIONS + 1,
    )
    input_binding = _input_binding(
        function_source, units, function_byte_start,
        cindex_macro_facts, compile_macros,
    )
    total_bytes = sum(len(data) for _, data, _ in units)
    if len(units) > MAX_MACRO_SOURCE_FILES or total_bytes > MAX_MACRO_TOTAL_SOURCE_BYTES:
        return _finish(input_binding, (), {}, 0, 0, "source_budget_exceeded")

    records: list[dict[str, Any]] = []
    structure_invalid = False
    for path, data, origin in units:
        scanned, invalid, budget_exceeded = scan_macro_source(
            path, data, origin,
            max_records=MAX_MACRO_DEFINITIONS - len(records) + 1,
        )
        records.extend(scanned)
        structure_invalid = structure_invalid or invalid
        if budget_exceeded or len(records) > MAX_MACRO_DEFINITIONS:
            return _finish(
                input_binding, (), {}, len(records) + len(compile_macros), 0,
                "definition_budget_exceeded",
            )
    main_records = [item for item in records if item["origin"] == "translation_unit"]
    if len(records) + len(compile_macros) > MAX_MACRO_DEFINITIONS:
        return _finish(
            input_binding, (), {}, len(records) + len(compile_macros), 0,
            "definition_budget_exceeded",
        )
    validate_cindex_macro_facts(
        cindex_macro_facts, main_records, source_path, source_bytes,
        node_id, unit_id,
    )
    if structure_invalid:
        return _finish(
            input_binding, (), {}, len(records) + len(compile_macros), 0,
            "preprocessor_structure_invalid",
        )

    definitions: dict[str, list[str]] = defaultdict(list)
    blocked: dict[str, set[str]] = defaultdict(set)
    for record in records:
        name = record["name"]
        if (
            record["origin"] == "translation_unit"
            and int(record["byte_offset"]) >= function_byte_start
        ):
            continue
        reason = record.get("blocked_reason")
        if reason is not None:
            blocked[name].add(str(reason))
        else:
            definitions[name].append(str(record["replacement"]))
    for name, replacement in compile_macros:
        definitions[name].append(replacement)
    for name, values in definitions.items():
        if len(values) != 1:
            blocked[name].add("redefined")
    proven = {
        name: values[0] for name, values in definitions.items()
        if len(values) == 1 and name not in blocked
    }

    roots = _referenced_macro_names(function_source, set(proven) | set(blocked))
    if len(roots) > MAX_MACRO_ROOTS:
        return _finish(
            input_binding, (), {}, len(records), len(roots),
            "root_budget_exceeded",
        )
    resolution = resolve_integer_macro_roots(proven, roots)
    failures = dict(resolution.failures)
    for root in roots:
        if root in blocked:
            failures[root] = sorted(blocked[root])[0]
    magnitudes: list[int] = []
    seen: set[int] = set()
    for root in roots:
        value = resolution.values.get(root)
        if value is None or root in failures:
            continue
        magnitude = abs(value)
        if magnitude not in seen:
            magnitudes.append(magnitude)
            seen.add(magnitude)
    if len(magnitudes) > MAX_MACRO_MAGNITUDES:
        failures["<budget>"] = "magnitude_budget_truncated"
        magnitudes = magnitudes[:MAX_MACRO_MAGNITUDES]
    return _finish(
        input_binding, tuple(magnitudes), failures,
        len(records) + len(compile_macros), len(roots), None,
    )


def _validate_inputs(
    units: Sequence[tuple[str, bytes, str]], function_source: bytes,
    function_start: int, node_id: str, unit_id: str,
) -> None:
    if not isinstance(function_source, bytes) or type(function_start) is not int:
        raise ValueError("macro binding function source is invalid")
    if (
        not isinstance(node_id, str) or not node_id
        or not isinstance(unit_id, str) or not unit_id
        or not 0 <= function_start <= len(units[0][1])
    ):
        raise ValueError("macro binding function identity is invalid")
    function_end = function_start + len(function_source)
    if units[0][1][function_start:function_end] != function_source:
        raise ValueError("macro function source is not source bound")
    paths = []
    for path, data, _ in units:
        if not isinstance(path, str) or not isinstance(data, bytes):
            raise ValueError("macro binding source is invalid")
        paths.append(checked_relative_path(path))
    if len(paths) != len(set(paths)):
        raise ValueError("macro binding source paths are duplicated")


def _input_binding(
    function_source: bytes, units: Sequence[tuple[str, bytes, str]],
    function_start: int, facts: Sequence[Mapping[str, Any]],
    compile_macros: Sequence[tuple[str, str]],
) -> dict[str, object]:
    return {
        "function_source_sha256": hashlib.sha256(function_source).hexdigest(),
        "function_byte_start": function_start,
        "sources": [
            {"path": path, "sha256": hashlib.sha256(data).hexdigest(),
             "size_bytes": len(data), "kind": kind}
            for path, data, kind in sorted(units)
        ],
        "cindex_macro_facts_sha256": content_sha256(
            sorted((dict(item) for item in facts), key=content_sha256),
        ),
        "compile_definitions_sha256": content_sha256(
            list(compile_macros),
        ),
    }


def _referenced_macro_names(source: bytes, known: set[str]) -> tuple[str, ...]:
    try:
        visible = macro_expression_text(source.decode("utf-8"))
    except UnicodeError as error:
        raise ValueError("macro function source is not UTF-8") from error
    result = []
    for matched in _IDENTIFIER.finditer(visible):
        if matched.end() < len(visible) and visible[matched.end()] == "\x00":
            continue
        name = matched.group()
        if name in known and name not in result:
            result.append(name)
    return tuple(result)


def _finish(
    input_binding: Mapping[str, object], magnitudes: tuple[int, ...],
    failures: Mapping[str, str], definition_count: int, root_count: int,
    global_blocker: str | None,
) -> IntegerMacroBoundaries:
    reasons = Counter(failures.values())
    if global_blocker is not None:
        reasons[global_blocker] += 1
    status = "blocked" if global_blocker else (
        "ready_with_ignored" if reasons else "ready"
    )
    payload: dict[str, object] = {
        "schema_version": 1,
        "strategy": "bound-object-like-integer-macros-v1",
        "status": status,
        "input_sha256": content_sha256(dict(input_binding)),
        "definition_count": definition_count,
        "referenced_root_count": root_count,
        "accepted_magnitude_count": len(magnitudes),
        "blocker_counts": dict(sorted(reasons.items())),
        "magnitudes_sha256": content_sha256(list(magnitudes)),
    }
    payload["binding_sha256"] = content_sha256(payload)
    return IntegerMacroBoundaries(magnitudes, payload)


__all__ = [
    "IntegerMacroBoundaries", "MAX_MACRO_DEFINITIONS",
    "MAX_MACRO_TOTAL_SOURCE_BYTES", "collect_integer_macro_boundaries",
]
