from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any

from validation.tools.replay_call_plan_fixture import _fixture_binding


def render_declarative_replay_cases(
    spec: dict[str, Any],
    plan: dict[str, Any],
    repo_root: Path,
) -> str:
    from validation.tools.replay_call_plan_schema import validate_replay_call_plan

    validate_replay_call_plan(plan)
    fixture = _fixture_binding(spec, repo_root.resolve())
    if fixture["sha256"] != plan["fixture"]["sha256"]:
        raise ValueError("replay fixture binding drifted")
    if plan.get("schema_version") == 2:
        from validation.tools.replay_call_plan_v2 import render_replay_call_plan_v2

        return render_replay_call_plan_v2(plan, fixture["cases"])
    lines: list[str] = []
    for index, case in enumerate(fixture["cases"]):
        variable = f"actual_{_safe_ident(case['id'])}_{index}"
        arguments = [
            _source_literal(item["source"], case["inputs"])
            for item in plan["parameters"]
        ]
        lines.append(
            f"    let {variable}: {plan['return_type']} = "
            f"{plan['api_name']}({', '.join(arguments)});\n"
        )
        for assertion_index, assertion in enumerate(plan["assertions"]):
            actual = variable
            if assertion["actual"] != "return":
                actual += assertion["actual"][len("return") :]
            observed = f"observed_{_safe_ident(case['id'])}_{index}_{assertion_index}"
            expected = _encoded_literal(
                case["expected"][assertion["fixture_field"]],
                assertion["encoding"],
            )
            lines.append(f"    let {observed}: {assertion['rust_type']} = {actual};\n")
            lines.append(
                f"    assert_eq!({observed}, {expected}, "
                f"{json.dumps(case['id'] + ' ' + assertion['fixture_field'] + ' drifted')});\n"
            )
        for assertion in plan.get("fixture_assertions", []):
            actual = _encoded_literal(
                case["expected"][assertion["fixture_field"]], assertion["encoding"]
            )
            expected = _encoded_literal(assertion["expected"], assertion["encoding"])
            lines.append(
                f"    assert_eq!({actual}, {expected}, "
                f"{json.dumps(case['id'] + ' ' + assertion['fixture_field'] + ' metadata drifted')});\n"
            )
    return "".join(lines)


def replay_call_plan_marker(plan: dict[str, Any]) -> str:
    from validation.tools.replay_call_plan_schema import validate_replay_call_plan

    validate_replay_call_plan(plan)
    return f"// ReplayCallPlan-SHA256: {plan['plan_sha256']}\n"


def _source_literal(source: dict[str, Any], payload: dict[str, Any]) -> str:
    field = source["field"]
    if field not in payload:
        raise ValueError(f"fixture input field {field} is missing")
    value = payload[field]
    if value is None and "null_default" in source:
        value = source["null_default"]
    if source["kind"] == "encoded_length":
        return f"{len(_decode_hex(value))}usize"
    return _encoded_literal(value, source["encoding"])


def _encoded_literal(value: Any, encoding: str) -> str:
    if encoding == "u32":
        return f"{_integer(value, 0, 2**32 - 1, encoding)}u32"
    if encoding == "u64":
        return f"{_integer(value, 0, 2**64 - 1, encoding)}u64"
    if encoding == "i32":
        return f"{_integer(value, -(2**31), 2**31 - 1, encoding)}i32"
    if encoding == "usize":
        return f"{_integer(value, 0, 2**64 - 1, encoding)}usize"
    if encoding == "u16":
        return f"{_integer(value, 0, 2**16 - 1, encoding)}u16"
    if encoding == "bool" and isinstance(value, bool):
        return "true" if value else "false"
    if encoding == "string" and isinstance(value, str):
        return json.dumps(value, ensure_ascii=True)
    if encoding == "string_vec" and isinstance(value, list) and len(value) <= 64:
        if not all(isinstance(item, str) for item in value):
            raise ValueError("string_vec fixture field is invalid")
        return "&[" + ", ".join(
            json.dumps(item, ensure_ascii=True) for item in value
        ) + "]"
    if encoding == "hex_bytes":
        return "&[" + ", ".join(f"{item}u8" for item in _decode_hex(value)) + "]"
    if encoding == "u8_array" and isinstance(value, list):
        items = [_integer(item, 0, 255, encoding) for item in value]
        return "&[" + ", ".join(f"{item}u8" for item in items) + "]"
    raise ValueError(f"value does not match replay encoding {encoding}")


def _decode_hex(value: Any) -> bytes:
    if (
        not isinstance(value, str)
        or len(value) % 2
        or not re.fullmatch(r"[0-9a-fA-F]*", value)
    ):
        raise ValueError("hex fixture field is invalid")
    return bytes.fromhex(value)


def _integer(value: Any, minimum: int, maximum: int, label: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not minimum <= value <= maximum
    ):
        raise ValueError(f"value does not match replay encoding {label}")
    return value


def _safe_ident(value: str) -> str:
    result = re.sub(r"[^A-Za-z0-9_]", "_", value)
    return result if result and not result[0].isdigit() else f"case_{result}"


def _plan_sha256(plan: dict[str, Any]) -> str:
    payload = {key: value for key, value in plan.items() if key != "plan_sha256"}
    encoded = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
