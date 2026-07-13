from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from .context_security import redact_metadata_text


MAX_COMPILER_DIAGNOSTICS = 8
MAX_CODE_BYTES = 32
MAX_MESSAGE_BYTES = 1_024
CODE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
LINKER_FAILURE_PATTERN = re.compile(
    r"^linking with `[A-Za-z0-9_.+-]{1,32}` failed: exit status: [1-9][0-9]*$"
)
UNDEFINED_SYMBOL_PATTERN = re.compile(
    r"^rust-lld: error: undefined symbol: (?P<symbol>[A-Za-z_][A-Za-z0-9_]*)$",
    re.MULTILINE,
)


def normalize_compiler_diagnostics(result: Mapping[str, Any]) -> list[dict[str, str]]:
    entries = result.get("errors")
    if not isinstance(entries, list):
        entries = _json_diagnostics(
            result.get("compile_stderr")
            if isinstance(result.get("compile_stderr"), str)
            else result.get("stderr")
        )
    diagnostics: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for entry in entries:
        for normalized in _normalize_diagnostics(entry):
            identity = (normalized["code"], normalized["message"])
            if identity in seen:
                continue
            seen.add(identity)
            diagnostics.append(normalized)
            if len(diagnostics) >= MAX_COMPILER_DIAGNOSTICS:
                return diagnostics
    return diagnostics


def compiler_failure_fact(
    kind: str,
    message: str,
    result: Mapping[str, Any],
) -> dict[str, Any]:
    fact: dict[str, Any] = {"kind": kind, "message": message}
    diagnostics = normalize_compiler_diagnostics(result)
    if diagnostics:
        fact["details"] = {"compiler_diagnostics": diagnostics}
    return fact


def validated_compiler_diagnostic_details(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    entries = value.get("compiler_diagnostics")
    if not isinstance(entries, list) or not entries:
        return None
    normalized: list[dict[str, str]] = []
    for entry in entries[:MAX_COMPILER_DIAGNOSTICS]:
        diagnostic = _normalize_diagnostic(entry, require_error_level=False)
        if diagnostic is None:
            return None
        normalized.append(diagnostic)
    return {"compiler_diagnostics": normalized}


def _json_diagnostics(value: Any) -> list[Any]:
    if not isinstance(value, str):
        return []
    entries = []
    for line in value.splitlines():
        if not line.startswith("{"):
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        entries.append(entry)
    return entries


def _normalize_diagnostic(
    value: Any, *, require_error_level: bool = True
) -> dict[str, str] | None:
    if not isinstance(value, Mapping):
        return None
    if require_error_level and value.get("level") != "error":
        return None
    code_value = value.get("code")
    if isinstance(code_value, Mapping):
        code_value = code_value.get("code")
    code = str(code_value or "compile_error")
    message = value.get("message")
    if not CODE_PATTERN.fullmatch(code) or not isinstance(message, str):
        return None
    message = _bounded_text(redact_metadata_text(message), MAX_MESSAGE_BYTES)
    if not message:
        return None
    return {
        "code": _bounded_text(code, MAX_CODE_BYTES),
        "message": message,
    }


def _normalize_diagnostics(value: Any) -> list[dict[str, str]]:
    linker_symbols = _linker_undefined_symbols(value)
    if linker_symbols:
        return [
            {
                "code": "linker_undefined_symbol",
                "message": f"undefined external symbol `{symbol}`",
            }
            for symbol in linker_symbols
        ]
    normalized = _normalize_diagnostic(value)
    return [normalized] if normalized is not None else []


def _linker_undefined_symbols(value: Any) -> list[str]:
    if (
        not isinstance(value, Mapping)
        or value.get("level") != "error"
        or value.get("code") is not None
        or not isinstance(value.get("message"), str)
        or LINKER_FAILURE_PATTERN.fullmatch(value["message"]) is None
    ):
        return []
    children = value.get("children")
    if not isinstance(children, list):
        return []
    symbols: list[str] = []
    for child in children[:32]:
        if not isinstance(child, Mapping) or child.get("level") != "note":
            continue
        message = child.get("message")
        if not isinstance(message, str):
            continue
        for match in UNDEFINED_SYMBOL_PATTERN.finditer(message):
            symbol = match.group("symbol")
            if symbol not in symbols:
                symbols.append(symbol)
                if len(symbols) >= MAX_COMPILER_DIAGNOSTICS:
                    return symbols
    return symbols


def _bounded_text(value: str, maximum: int) -> str:
    encoded = value.strip().encode("utf-8")
    if len(encoded) <= maximum:
        return encoded.decode("utf-8")
    suffix = b"..."
    return (
        encoded[: maximum - len(suffix)].decode("utf-8", errors="ignore").rstrip()
        + "..."
    )


__all__ = [
    "compiler_failure_fact",
    "normalize_compiler_diagnostics",
    "validated_compiler_diagnostic_details",
]
