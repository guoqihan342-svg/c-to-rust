from __future__ import annotations

import json
from typing import Any

from validation.tools._ai_candidate_harness_parts.context_security import (
    redact_metadata_text,
)
from validation.tools.linker_diagnostic_parser import (
    parse_rustc_linker_diagnostic,
)


def cargo_diagnostics(stdout: str, command: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        message = event.get("message") if isinstance(event, dict) else None
        if not isinstance(message, dict) or event.get("reason") != "compiler-message":
            continue
        if message.get("level") != "error":
            continue
        linker = parse_rustc_linker_diagnostic(message)
        if linker.blocker_code is not None:
            result.append({
                "code": linker.blocker_code,
                "stage": f"cargo-{command}",
                "message": "Linker diagnostics exceeded the bounded parser contract",
            })
            continue
        if linker.symbols:
            for symbol in linker.symbols:
                if len(result) >= 64:
                    return [_overflow(command)]
                result.append({
                    "code": "linker-undefined-symbol",
                    "stage": f"cargo-{command}",
                    "message": f"undefined linker symbol `{symbol}`",
                    "linker_symbol": symbol,
                    "level": "error",
                    "origin": "rustc-linker-message",
                })
            continue
        if len(result) >= 64:
            return [_overflow(command)]
        code = message.get("code")
        code_value = code.get("code") if isinstance(code, dict) else None
        diagnostic = {
            "code": _code(code_value),
            "stage": f"cargo-{command}",
            "message": _message(message.get("message")),
            "level": "error",
            "origin": "rustc-compiler-message",
        }
        diagnostic.update(_location(message.get("spans")))
        result.append(diagnostic)
    return result


def cargo_check_diagnostics(
    stdout: str, command: str, returncode: int,
) -> list[dict[str, Any]]:
    diagnostics = cargo_diagnostics(stdout, command)
    if returncode != 0 and not diagnostics:
        return [{
            "code": "cargo_command_failed",
            "stage": f"cargo-{command}",
            "message": f"cargo {command} exited with code {returncode}",
        }]
    return diagnostics


def _code(value: Any) -> str:
    if isinstance(value, str) and len(value) <= 32 and all(
        char.isalnum() or char in "_-" for char in value
    ):
        return value.lower().replace("_", "-")
    return "rustc-diagnostic"


def _overflow(command: str) -> dict[str, str]:
    return {
        "code": "cargo_diagnostic_overflow",
        "stage": f"cargo-{command}",
        "message": "Cargo emitted more than 64 compiler errors",
    }


def _message(value: Any) -> str:
    text = redact_metadata_text(value if isinstance(value, str) else "Rust compiler diagnostic")
    return text[:512]


def _location(value: Any) -> dict[str, Any]:
    if not isinstance(value, list):
        return {}
    primary = next(
        (item for item in value if isinstance(item, dict) and item.get("is_primary") is True),
        None,
    )
    if not isinstance(primary, dict):
        return {}
    filename = primary.get("file_name")
    if not isinstance(filename, str) or not filename.startswith("/workspace/"):
        return {}
    relative = filename.removeprefix("/workspace/")
    parts = relative.split("/")
    if (
        not relative
        or len(relative) > 256
        or any(part in {"", ".", ".."} for part in parts)
        or any(not all(char.isalnum() or char in "._-" for char in part) for part in parts)
    ):
        return {}
    result: dict[str, Any] = {"file": relative}
    for source, target in (("line_start", "line"), ("column_start", "column")):
        number = primary.get(source)
        if isinstance(number, int) and not isinstance(number, bool) and number > 0:
            result[target] = number
    return result


__all__ = ["cargo_check_diagnostics", "cargo_diagnostics"]
