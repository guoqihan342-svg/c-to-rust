from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any


class StrictJsonError(ValueError):
    pass


class JsonObjectRequiredError(StrictJsonError):
    pass


_LINKER_STDOUT_PREFIX = "linker stdout: "


def load_strict_json(line: str) -> Any:
    def object_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise StrictJsonError("duplicate JSON key")
            result[key] = item
        return result

    def reject_constant(_value: str) -> None:
        raise StrictJsonError("non-standard JSON constant")

    return json.loads(
        line, object_pairs_hook=object_hook, parse_constant=reject_constant,
    )


def required_json_object(line: str) -> dict[str, Any]:
    value = load_strict_json(line)
    if not isinstance(value, dict):
        raise JsonObjectRequiredError("JSON object required")
    return value


def optional_json_object(line: str) -> dict[str, Any] | None:
    try:
        value = load_strict_json(line)
    except (json.JSONDecodeError, StrictJsonError):
        return None
    return value if isinstance(value, dict) else None


def trusted_linker_stdout(event: Mapping[str, Any]) -> str | None:
    if event.get("reason") != "compiler-message":
        return None
    message = event.get("message")
    if not isinstance(message, Mapping) or message.get("level") != "warning":
        return None
    code = message.get("code")
    if not isinstance(code, Mapping) or code.get("code") != "linker_messages":
        return None
    text = message.get("message")
    if not isinstance(text, str) or not text.startswith(_LINKER_STDOUT_PREFIX):
        return None
    return text[len(_LINKER_STDOUT_PREFIX):]


__all__ = [
    "JsonObjectRequiredError", "StrictJsonError", "optional_json_object",
    "required_json_object", "trusted_linker_stdout",
]
