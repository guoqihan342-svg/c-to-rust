from __future__ import annotations

import hashlib
import json
from pathlib import PurePosixPath
import re
from typing import Any

from validation.tools.c_oracle_call_plan_direct import _require_printable_ascii


POINTEE_RE = re.compile(r"^(struct [A-Za-z_][A-Za-z0-9_]*) \*$")
SCALAR_C_TYPES = {
    "i32": "int32_t",
    "u16": "uint16_t",
    "u32": "uint32_t",
    "u64": "uint64_t",
    "usize": "size_t",
    "bool": "bool",
}


def output_bindings(
    raw: Any, parameters: dict[str, dict[str, Any]]
) -> dict[str, dict[str, str]]:
    if not isinstance(raw, list) or not raw:
        raise ValueError("C oracle output bindings are missing")
    result: dict[str, dict[str, str]] = {}
    ids: set[str] = set()
    for item in raw:
        require_keys(
            item,
            {"id", "c_parameter", "initializer", "pass_mode"},
            "output binding",
        )
        binding_id = identifier(item["id"], "output binding")
        parameter_name = identifier(item["c_parameter"], "output C parameter")
        if binding_id in ids or parameter_name in result:
            raise ValueError("C oracle output binding is duplicated")
        parameter = parameters.get(parameter_name)
        if parameter is None or parameter.get("direction") not in {"output", "inout"}:
            raise ValueError("C oracle output binding parameter is not writable output")
        match = POINTEE_RE.fullmatch(parameter["c_type"])
        if (
            match is None
            or item["initializer"] != "zero"
            or item["pass_mode"] != "address_of"
        ):
            raise ValueError(
                "C oracle output binding requires zeroed single struct pointee address"
            )
        result[parameter_name] = {"id": binding_id, "c_type": match.group(1)}
        ids.add(binding_id)
    return result


def observations(
    raw: Any, bindings: dict[str, dict[str, str]], maximum_field_bytes: int
) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or not raw:
        raise ValueError("C oracle observations are missing")
    binding_ids = {item["id"] for item in bindings.values()}
    result = []
    fields: set[str] = set()
    for item in raw:
        require_keys(item, {"fixture_field", "encoding", "source"}, "observation")
        field = str(item["fixture_field"])
        _require_printable_ascii(field, "observation fixture field", maximum_field_bytes)
        if field in fields:
            raise ValueError("C oracle observation field is duplicated")
        encoding = str(item["encoding"])
        source = item["source"]
        validate_source(source, binding_ids, encoding, maximum_field_bytes)
        result.append({"fixture_field": field, "encoding": encoding, "source": source})
        fields.add(field)
    return result


def validate_source(
    source: Any,
    binding_ids: set[str],
    encoding: str,
    maximum_field_bytes: int,
) -> None:
    if not isinstance(source, dict):
        raise ValueError("C oracle observation source is invalid")
    kind = source.get("kind")
    if kind == "return":
        require_keys(source, {"kind"}, "return observation")
        if encoding not in SCALAR_C_TYPES:
            raise ValueError("return observation encoding is unsupported")
        return
    if kind == "map_scalar":
        require_keys(
            source, {"kind", "value", "cases", "default"}, "mapped observation"
        )
        if source["value"] != {"kind": "return"} or encoding != "string":
            raise ValueError("mapped observation requires scalar return to string")
        cases = source["cases"]
        if not isinstance(cases, list) or not cases or len(cases) > 16:
            raise ValueError("mapped observation cases are invalid")
        for case in cases:
            require_keys(case, {"equals", "value"}, "mapped observation case")
            if (
                isinstance(case["equals"], bool)
                or not isinstance(case["equals"], int)
                or not -(2**31) <= case["equals"] <= 2**31 - 1
                or not isinstance(case["value"], str)
            ):
                raise ValueError("mapped observation match value is invalid")
            _require_printable_ascii(
                str(case["value"]), "mapped value", maximum_field_bytes
            )
        if not isinstance(source["default"], str):
            raise ValueError("mapped observation default is invalid")
        _require_printable_ascii(source["default"], "mapped default", maximum_field_bytes)
        return
    expected_keys = {"kind", "binding", "path", "width_bytes"}
    if kind == "object_bytes":
        expected_keys = {"kind", "binding", "path", "byte_count", "format"}
    require_keys(source, expected_keys, "field observation")
    if source["binding"] not in binding_ids:
        raise ValueError("field observation binding is unknown")
    path = source["path"]
    if not isinstance(path, list) or not path or len(path) > 4:
        raise ValueError("field observation path is invalid")
    for component in path:
        identifier(component, "field path")
    if kind == "field":
        expected_widths = {
            "bool": {1},
            "u16": {2},
            "i32": {4},
            "u32": {4},
            "u64": {8},
            "usize": {4, 8},
        }
        if (
            encoding not in SCALAR_C_TYPES
            or source["width_bytes"] not in expected_widths[encoding]
        ):
            raise ValueError("scalar field observation is unsupported")
    elif kind == "be_u16":
        if encoding != "u16" or source["width_bytes"] != 2:
            raise ValueError("BE16 field observation is unsupported")
    elif kind == "object_bytes":
        count = source["byte_count"]
        if (
            encoding != "hex_bytes"
            or not isinstance(count, int)
            or not 1 <= count <= 64
        ):
            raise ValueError("object-byte observation is unsupported")
        if source["format"] != "lower_hex":
            raise ValueError("object-byte format is unsupported")
    else:
        raise ValueError("C oracle observation source kind is unsupported")


def field_width_assertions(
    bindings: dict[str, dict[str, str]], observations: list[dict[str, Any]]
) -> list[str]:
    by_id = {item["id"]: item for item in bindings.values()}
    lines = []
    seen: set[tuple[str, tuple[str, ...], int]] = set()
    for observation in observations:
        source = observation["source"]
        if source["kind"] in {"return", "map_scalar"}:
            continue
        width = source.get("width_bytes", source.get("byte_count"))
        key = (source["binding"], tuple(source["path"]), width)
        if key in seen:
            continue
        binding = by_id[source["binding"]]
        field = ".".join(source["path"])
        lines.append(
            f'_Static_assert(sizeof((({binding["c_type"]} *)0)->{field}) == {width}, '
            f'"C oracle field width mismatch");\n'
        )
        seen.add(key)
    return lines


def header_includes(spec: dict[str, Any], raw: Any) -> list[str]:
    if not isinstance(raw, list) or not raw or len(raw) > 16:
        raise ValueError("C oracle contract headers are invalid")
    boundary_headers = [
        PurePosixPath(str(item.get("path") or "")).name
        for item in spec.get("c_boundary", {}).get("files") or []
        if isinstance(item, dict) and item.get("role") == "header"
    ]
    result = []
    seen: set[str] = set()
    for item in raw:
        if (
            not isinstance(item, str)
            or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}", item)
            or boundary_headers.count(item) != 1
            or item in seen
        ):
            raise ValueError("C oracle contract header is not a declared safe header")
        result.append(f'#include "{item}"\n')
        seen.add(item)
    return result


def abi_assertions(
    spec: dict[str, Any], pointer_width: int
) -> list[str]:
    target = spec["build_profile"]["target"]
    int_width = target.get("int_width")
    if int_width not in {16, 32, 64}:
        raise ValueError("C oracle target int width is unsupported")
    return [
        '_Static_assert(CHAR_BIT == 8, "C oracle requires 8-bit bytes");\n',
        f'_Static_assert(sizeof(void *) * CHAR_BIT == {pointer_width}, "C oracle pointer width mismatch");\n',
        f'_Static_assert(sizeof(int) * CHAR_BIT == {int_width}, "C oracle int width mismatch");\n',
    ]


def validate_abi_contract(spec: dict[str, Any], raw: Any) -> None:
    require_keys(raw, {"target_ref", "char_bits"}, "C oracle ABI contract")
    if raw["target_ref"] != "build_profile.target" or raw["char_bits"] != 8:
        raise ValueError("C oracle ABI contract is unsupported")
    target = spec.get("build_profile", {}).get("target")
    if not isinstance(target, dict):
        raise ValueError("C oracle target ABI is missing")


def call_plan_sha(
    spec: dict[str, Any], plan: dict[str, Any], contract: dict[str, Any]
) -> str:
    payload = {
        "schema_version": 1,
        "replay_call_plan_sha256": plan["plan_sha256"],
        "fixture": plan.get("fixture"),
        "target": spec["build_profile"]["target"],
        "contract": contract,
    }
    return hashlib.sha256(
        json.dumps(
            payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True
        ).encode()
    ).hexdigest()


def identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(
        r"[A-Za-z_][A-Za-z0-9_]*", value
    ):
        raise ValueError(f"{label} identifier is invalid")
    return value


def require_keys(value: Any, keys: set[str], label: str) -> None:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{label} fields are invalid")


__all__ = [
    "SCALAR_C_TYPES",
    "abi_assertions",
    "call_plan_sha",
    "field_width_assertions",
    "header_includes",
    "observations",
    "output_bindings",
    "require_keys",
    "validate_abi_contract",
]
