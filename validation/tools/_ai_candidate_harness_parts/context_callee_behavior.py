from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

from .context_bound_source import (
    BoundSourceFile,
    read_hash_bound_utf8_source,
    source_file_descriptor,
)
from .context_security import redact_text, sha256_bytes
from validation.tools.extract_source_slice import mask_comments_and_strings


MAX_CALLEE_FILE_BYTES = 4 * 1024 * 1024
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
NEGATED_GUARD_RE = re.compile(
    r"\bif\s*\(\s*!\s*(?P<guard>[A-Za-z_]\w*)\s*\(\s*(?P<argument>[A-Za-z_]\w*)\s*\)\s*\)"
    r"\s*\{(?P<body>.*?)\breturn\s+(?P<result>[A-Za-z_]\w*)\s*;",
    re.DOTALL,
)


def source_backed_behavior(
    spec: dict[str, Any],
    *,
    blocks: list[dict[str, Any]],
    source_root: Path | None,
    known_roots: tuple[str, ...],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    if source_root is None:
        return [], [], []
    guard_uses: dict[str, set[str]] = {}
    result_symbols: set[str] = set()
    matches_by_callee: dict[str, list[re.Match[str]]] = {}
    for block in blocks:
        content = str(block.get("source_span", {}).get("content") or "")
        matches = list(NEGATED_GUARD_RE.finditer(mask_comments_and_strings(content)))
        if not matches:
            continue
        matches_by_callee[str(block["callee"])] = matches
        for match in matches:
            guard_uses.setdefault(match.group("guard"), set()).add(match.group("argument"))
            result_symbols.add(match.group("result"))
    if not matches_by_callee:
        return [], [], []

    sources = _verified_declared_sources(spec, source_root)
    dependencies: list[dict[str, Any]] = []
    macros: dict[str, dict[str, Any]] = {}
    constants: dict[str, dict[str, Any]] = {}
    blocked: list[dict[str, Any]] = []
    for guard in sorted(guard_uses):
        dependency = _find_macro_dependency(guard, sources, source_root, known_roots)
        if dependency is None:
            blocked.append({"symbol": guard, "reason": "guard_macro_definition_not_found"})
        else:
            dependencies.append(dependency)
            macros[guard] = dependency
    for symbol in sorted(result_symbols):
        dependency = _find_enum_dependency(symbol, sources, source_root, known_roots)
        if dependency is None:
            blocked.append({"symbol": symbol, "reason": "return_constant_definition_not_found"})
        else:
            dependencies.append(dependency)
            constants[symbol] = dependency

    rules = []
    for callee, matches in sorted(matches_by_callee.items()):
        for match in matches:
            guard = macros.get(match.group("guard"))
            result = constants.get(match.group("result"))
            if guard is None or result is None:
                continue
            rule = {
                "callee": callee,
                "scope": "source_backed_early_return",
                "when": {
                    "kind": "binding_bool_field_equals",
                    "callee_parameter": match.group("argument"),
                    "field_path": [guard["projection_field"]],
                    "value": False,
                },
                "effect": {
                    "kind": "return_source_constant",
                    "symbol": result["symbol"],
                    "resolved_integer": result["resolved_integer"],
                    "resolution": "c_enum_ordinal_v1",
                },
                "source_span_sha256": sorted({
                    str(guard["source_span"]["sha256"]),
                    str(result["source_span"]["sha256"]),
                    str(next(
                        block["source_span"]["sha256"]
                        for block in blocks
                        if block["callee"] == callee
                    )),
                }),
                "whole_callee_semantics": False,
                "semantics_verified": False,
            }
            rule["rule_sha256"] = sha256_bytes(_canonical_bytes(rule))
            rules.append(rule)
    return dependencies, rules, blocked


def source_behavior_disagrees_with_fixture(
    spec: dict[str, Any],
    rules: list[dict[str, Any]],
) -> bool:
    resolved = {
        rule.get("effect", {}).get("resolved_integer")
        for rule in rules
        if isinstance(rule, dict) and isinstance(rule.get("effect"), dict)
    }
    if len(resolved) != 1:
        return False
    replay = spec.get("replay_contract")
    return_contract = replay.get("return") if isinstance(replay, dict) else None
    field = return_contract.get("fixture_field") if isinstance(return_contract, dict) else None
    fixture = spec.get("fixture_contract")
    cases = fixture.get("cases") if isinstance(fixture, dict) else None
    if not isinstance(field, str) or not isinstance(cases, list) or not cases:
        return False
    source_value = next(iter(resolved))
    expected_values = []
    for case in cases:
        expected = case.get("expected_outputs") if isinstance(case, dict) else None
        if not isinstance(expected, dict) or field not in expected:
            return False
        expected_values.append(expected[field])
    return any(value != source_value for value in expected_values)


def _verified_declared_sources(
    spec: dict[str, Any],
    source_root: Path,
) -> list[tuple[str, BoundSourceFile]]:
    source = spec.get("source")
    hashes = source.get("source_file_hashes") if isinstance(source, dict) else None
    if not isinstance(hashes, dict):
        hashes = spec.get("source_file_hashes")
    if not isinstance(hashes, dict):
        return []
    verified = []
    for raw_path, raw_sha in sorted(hashes.items(), key=lambda item: str(item[0])):
        path = _normalized_declared_path(raw_path)
        if path is None or not isinstance(raw_sha, str) or SHA256_RE.fullmatch(raw_sha) is None:
            continue
        try:
            bound = read_hash_bound_utf8_source(
                source_root,
                path,
                raw_sha,
                max_bytes=MAX_CALLEE_FILE_BYTES,
            )
        except ValueError:
            continue
        verified.append((path, bound))
    return verified


def _find_macro_dependency(
    symbol: str,
    sources: list[tuple[str, BoundSourceFile]],
    source_root: Path,
    known_roots: tuple[str, ...],
) -> dict[str, Any] | None:
    pattern = re.compile(
        rf"^[ \t]*#[ \t]*define[ \t]+{re.escape(symbol)}[ \t]*\([^)]*\)[ \t]*(?P<body>[^\n]*(?:\\\r?\n[^\n]*)*)",
        re.MULTILINE,
    )
    matches = []
    for path, bound in sources:
        for match in pattern.finditer(bound.text):
            projection = re.search(r"->\s*([A-Za-z_]\w*)", match.group("body"))
            if projection is not None:
                matches.append((path, bound, match, projection.group(1)))
    if len(matches) != 1:
        return None
    path, bound, match, field = matches[0]
    return _dependency(
        kind="function_like_macro_projection",
        symbol=symbol,
        bound=bound,
        start=match.start(),
        end=match.end(),
        known_roots=known_roots,
        extra={"projection_field": field},
    )


def _find_enum_dependency(
    symbol: str,
    sources: list[tuple[str, BoundSourceFile]],
    source_root: Path,
    known_roots: tuple[str, ...],
) -> dict[str, Any] | None:
    enum_pattern = re.compile(
        r"(?:typedef\s+)?enum(?:\s+[A-Za-z_]\w*)?\s*\{(?P<body>.*?)\}\s*(?:[A-Za-z_]\w*\s*)?;",
        re.DOTALL,
    )
    matches = []
    for path, bound in sources:
        masked = mask_comments_and_strings(bound.text)
        for match in enum_pattern.finditer(masked):
            resolved_value = _enum_member_value(match.group("body"), symbol)
            if resolved_value is not None:
                matches.append((path, bound, match, resolved_value))
    if len(matches) != 1:
        return None
    path, bound, match, value = matches[0]
    return _dependency(
        kind="enum_constant",
        symbol=symbol,
        bound=bound,
        start=match.start(),
        end=match.end(),
        known_roots=known_roots,
        extra={"resolved_integer": value, "resolution": "c_enum_ordinal_v1"},
    )


def _enum_member_value(body: str, target: str) -> int | None:
    current = -1
    for raw_item in body.split(","):
        item = raw_item.strip()
        if not item or item.startswith("#"):
            continue
        name, separator, expression = item.partition("=")
        name = name.strip()
        if not re.fullmatch(r"[A-Za-z_]\w*", name):
            return None
        if separator:
            literal = expression.strip()
            if not re.fullmatch(r"[-+]?(?:0[xX][0-9A-Fa-f]+|[0-9]+)", literal):
                return None
            current = int(literal, 0)
        else:
            current += 1
        if name == target:
            return current
    return None


def _dependency(
    *,
    kind: str,
    symbol: str,
    bound: BoundSourceFile,
    start: int,
    end: int,
    known_roots: tuple[str, ...],
    extra: dict[str, Any],
) -> dict[str, Any]:
    text = bound.text
    content = text[start:end]
    data = content.encode("utf-8")
    return {
        "kind": kind,
        "symbol": symbol,
        "source_file": source_file_descriptor(bound),
        "source_span": {
            "line_start": text.count("\n", 0, start) + 1,
            "line_end": text.count("\n", 0, end) + 1,
            "sha256": sha256_bytes(data),
            "size_bytes": len(data),
            "content": redact_text(content, known_roots),
        },
        **extra,
    }


def _normalized_declared_path(value: Any) -> str | None:
    if not isinstance(value, str) or not value or "\\" in value or value.startswith("~"):
        return None
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        return None
    if ":" in path.parts[0]:
        return None
    return path.as_posix()


def _canonical_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf-8")


__all__ = ["source_backed_behavior", "source_behavior_disagrees_with_fixture"]
