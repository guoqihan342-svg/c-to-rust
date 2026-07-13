from __future__ import annotations

import hashlib
import json
from typing import Any


MAX_STRING_BYTES = 16 * 1024
MAX_ARRAY_ITEMS = 16_384
MAX_TARGETS = 10_000
MAX_OPTIONS = 4_096
MAX_DEPENDENCIES = 4_096
MAX_PATH_REFERENCES = 100_000
MAX_COMPILERS = 128
MAX_BUILDSYSTEM_FILES = 16_384


class MesonSchemaError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def strict_json(raw: bytes, label: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise MesonSchemaError(f"meson_{label}_duplicate_key")
            result[key] = value
        return result

    def constant(_value: str) -> None:
        raise MesonSchemaError(f"meson_{label}_non_finite_number")

    try:
        text = raw.decode("utf-8")
        return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    except MesonSchemaError:
        raise
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise MesonSchemaError(f"meson_{label}_json_invalid") from error


def object_value(value: Any, code: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise MesonSchemaError(code)
    return value


def array_value(value: Any, code: str, limit: int) -> list[Any]:
    if not isinstance(value, list):
        raise MesonSchemaError(code)
    if len(value) > limit:
        suffix = "_limit_exceeded" if code.endswith("_invalid") else "_too_large"
        raise MesonSchemaError(code.removesuffix("_invalid") + suffix)
    return value


def string_value(value: Any, code: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or "\0" in value:
        raise MesonSchemaError(code)
    if (not value and not allow_empty) or len(value.encode("utf-8")) > MAX_STRING_BYTES:
        raise MesonSchemaError(code)
    return value


def string_array(value: Any, code: str, *, limit: int = MAX_ARRAY_ITEMS) -> list[str]:
    return [string_value(item, code) for item in array_value(value, code, limit)]


def string_list(value: Any, code: str) -> list[str]:
    return [string_value(value, code)] if isinstance(value, str) else string_array(
        value, code
    )


def boolean_value(value: Any, code: str) -> bool:
    if not isinstance(value, bool):
        raise MesonSchemaError(code)
    return value


def command_value(value: Any, code: str = "meson_command_invalid") -> list[str]:
    if isinstance(value, str):
        return [string_value(value, code)]
    return string_array(value, code)


def summarizable(value: Any, code: str) -> Any:
    if isinstance(value, (str, bool, int)) and not isinstance(value, float):
        return string_value(value, code, allow_empty=True) if isinstance(value, str) else value
    if isinstance(value, list):
        return string_array(value, code)
    raise MesonSchemaError(code)


def summary(value: Any) -> dict[str, Any]:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return {
        "count": len(value) if isinstance(value, (list, dict)) else 1,
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "value_kind": "array" if isinstance(value, list) else type(value).__name__,
    }


__all__ = [
    "MAX_ARRAY_ITEMS", "MAX_BUILDSYSTEM_FILES", "MAX_COMPILERS",
    "MAX_DEPENDENCIES", "MAX_OPTIONS", "MAX_PATH_REFERENCES", "MAX_TARGETS",
    "MesonSchemaError", "array_value", "boolean_value", "command_value",
    "object_value", "strict_json", "string_array", "string_list", "string_value",
    "summarizable", "summary",
]
